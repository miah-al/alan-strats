"""
api/marketdata/surface.py — an implied-volatility surface (expiry × moneyness) from one chain snapshot.

For each expiry the out-of-the-money contracts give the smile — puts below spot, calls above, the two
averaged at a strike equal to spot — and their IVs are interpolated linearly in strike onto a K/S
grid, never extrapolated past the lowest or highest listed strike (those cells are null). IVs come
out in percent. At most ``MAX_EXPIRIES`` expiries (the nearest twelve, then evenly spaced), each
needing at least ``MIN_POINTS`` usable contracts.

Sources: Polygon's options snapshot (one paginated snapshot of the OTM contracts in the band, IV per
contract), else tastytrade — the chain's strikes plus the streamer's greeks for a coarse subset (at
most ~25 strikes per expiry), which is thinner and says so. The snapshot is cached 2 minutes per
underlying and band; the grid itself is cheap.
"""
from __future__ import annotations

import datetime as _dt
import math
import time
from typing import Optional

import numpy as np

from api.marketdata import symbols as SYM
from api.marketdata.cache import cached
from api.serialize import to_jsonable
from data.request_gate import ProviderUnavailable

MAX_EXPIRIES = 24
MIN_POINTS = 3
SNAPSHOT_TTL = 120.0
MAX_IV = 5.0                 # 500%: anything above is a bad print, not a smile
STREAM_STRIKES = 25
STREAM_WAIT_S = 8.0


class NoSurface(LookupError):
    pass


def moneyness_grid(lo: float, hi: float, step: float) -> list[float]:
    if not (0.2 <= lo < 1.0 < hi <= 3.0):
        raise ValueError("need 0.2 <= lo < 1 < hi <= 3")
    if not (0.001 <= step <= 0.25):
        raise ValueError("step must be between 0.001 and 0.25")
    n = int(round((hi - lo) / step))
    if n > 1000:
        raise ValueError("the grid would have more than 1000 points")
    return [round(lo + i * step, 6) for i in range(n + 1) if lo + i * step <= hi + 1e-9]


def pick_expiries(exps: list[_dt.date], limit: int = MAX_EXPIRIES) -> list[_dt.date]:
    exps = sorted(set(exps))
    if len(exps) <= limit:
        return exps
    head = exps[: limit // 2]
    rest = exps[limit // 2:]
    k = limit - len(head)
    idx = sorted({round(i * (len(rest) - 1) / (k - 1)) for i in range(k)}) if k > 1 else [len(rest) - 1]
    return head + [rest[i] for i in idx]


def smile(contracts: list[dict], spot: float) -> tuple[np.ndarray, np.ndarray]:
    """(strikes, IVs as fractions) for one expiry from its OTM contracts; K == spot averages both sides."""
    puts = {float(c["strike"]): float(c["iv"]) for c in contracts
            if c.get("type") == "put" and _ok_iv(c.get("iv")) and float(c["strike"]) <= spot}
    calls = {float(c["strike"]): float(c["iv"]) for c in contracts
             if c.get("type") == "call" and _ok_iv(c.get("iv")) and float(c["strike"]) >= spot}
    pts: dict[float, float] = {}
    for k, v in puts.items():
        pts[k] = v
    for k, v in calls.items():
        pts[k] = (pts[k] + v) / 2.0 if k in pts else v
    ks = np.array(sorted(pts), dtype=float)
    return ks, np.array([pts[k] for k in ks], dtype=float)


def _ok_iv(v) -> bool:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return False
    return math.isfinite(f) and 0.0 < f < MAX_IV


def _after_close() -> bool:
    import pandas as pd
    now = pd.Timestamp.now(tz="America/New_York")
    return now.time() >= _dt.time(16, 0)


def build_surface(contracts: list[dict], spot: float, grid: list[float], max_dte: int,
                  today: Optional[_dt.date] = None, include_today: Optional[bool] = None) -> dict:
    """contracts: [{"expiry": date, "strike", "type": call|put, "iv": fraction}] → the surface payload
    (without underlying / source). Today's expiry is left out after the 16:00 close (it has expired;
    its last IVs are noise)."""
    today = today or _dt.date.today()
    if include_today is None:
        include_today = not _after_close()
    min_dte = 0 if include_today else 1
    by_exp: dict[_dt.date, list[dict]] = {}
    for c in contracts:
        e = c["expiry"] if isinstance(c["expiry"], _dt.date) else _dt.date.fromisoformat(str(c["expiry"])[:10])
        if min_dte <= (e - today).days <= max_dte:
            by_exp.setdefault(e, []).append(c)
    warnings = []
    usable = []
    for e in sorted(by_exp):
        ks, ivs = smile(by_exp[e], spot)
        if len(ks) >= MIN_POINTS:
            usable.append((e, ks, ivs))
    chosen = set(pick_expiries([e for e, _, _ in usable]))
    if len(usable) > len(chosen):
        warnings.append(f"{len(usable)} expiries in range; showing {len(chosen)}")
    targets = np.array(grid, dtype=float) * spot
    rows, atm, exps = [], [], []
    for e, ks, ivs in usable:
        if e not in chosen:
            continue
        inside = (targets >= ks[0] - 1e-9) & (targets <= ks[-1] + 1e-9)
        vals = np.interp(targets, ks, ivs)
        rows.append([round(float(v) * 100.0, 3) if ok else None for v, ok in zip(vals, inside)])
        a = float(np.interp(spot, ks, ivs)) if ks[0] <= spot <= ks[-1] else None
        atm.append(round(a * 100.0, 3) if a is not None else None)
        exps.append({"expiry": e, "dte": (e - today).days})
    return {"spot": spot, "expiries": exps, "moneyness": grid, "iv": rows, "atm_iv": atm, "warnings": warnings}


# ── sources ───────────────────────────────────────────────────────────────────

def _streamed(hub, p, u: str, spot: float, max_dte: int, lo: float, hi: float) -> list[dict]:
    today = _dt.date.today()
    exps = pick_expiries([e for e in p.expirations(u) if 0 <= (e - today).days <= max_dte])
    syms: dict[str, tuple] = {}
    for e in exps:
        con = [c for c in p.chain_contracts(u, e) if spot * lo <= c[0] <= spot * hi]
        if not con:
            continue
        step = max(1, len(con) // STREAM_STRIKES)
        for k, call, put in con[::step]:
            if k <= spot:
                syms[put] = (e, k, "put")
            if k >= spot:
                syms[call] = (e, k, "call")
    if not syms:
        return []
    owner = f"surface:{u}"
    hub.watch(owner, list(syms))
    with hub._lock:
        deadline = time.monotonic() + 120.0
        for s in syms:
            hub.linger[s] = max(hub.linger.get(s, 0.0), deadline)
    hub.unwatch(owner, list(syms))
    end = time.monotonic() + STREAM_WAIT_S
    with hub._cond:
        while time.monotonic() < end:
            got = sum(1 for s in syms if s in hub.quotes and hub.quotes[s].values.get("iv") is not None)
            if got >= 0.9 * len(syms):
                break
            hub._cond.wait(timeout=0.25)
    out = []
    with hub._lock:
        for s, (e, k, t) in syms.items():
            q = hub.quotes.get(s)
            iv = q.values.get("iv") if q is not None else None
            if iv is not None:
                out.append({"expiry": e, "strike": k, "type": t, "iv": iv})
    return out


def surface(hub, underlying: str, max_dte: int = 180, lo: float = 0.80, hi: float = 1.20, step: float = 0.01) -> dict:
    u = SYM.normalize(underlying)
    if SYM.is_option(u):
        raise ValueError(f"{underlying!r} is an option; ask for its underlying's surface")
    if not 1 <= int(max_dte) <= 1100:
        raise ValueError("max_dte must be between 1 and 1100")
    grid = moneyness_grid(float(lo), float(hi), float(step))
    spot = None
    try:
        spot = hub.price(u, wait=3.0)
    except Exception:
        spot = None
    notes: list[str] = []
    # Polygon first: one snapshot carries every contract's IV; the streamer needs a subscription per contract
    for p in sorted(hub.providers, key=lambda p: {"polygon": 0, "tastytrade": 1}.get(p.name, 9)):
        if not p.available():
            continue
        try:
            if p.name == "polygon":
                if not spot:
                    notes.append("polygon: no spot price to centre the band on")
                    continue
                key = ("surface-snapshot", p.name, u, int(max_dte), round(lo, 4), round(hi, 4))
                contracts = cached(key, SNAPSHOT_TTL, lambda p=p: p.surface_contracts(u, spot, int(max_dte), lo, hi))
            elif p.name == "tastytrade" and getattr(p, "connected", False):
                if not spot:
                    notes.append("tastytrade: no spot price")
                    continue
                key = ("surface-stream", u, int(max_dte), round(lo, 4), round(hi, 4))
                contracts = cached(key, SNAPSHOT_TTL, lambda p=p: _streamed(hub, p, u, spot, int(max_dte), lo, hi))
                if contracts:
                    notes.append(f"tastytrade: a coarse grid from streamed greeks ({len(contracts)} contracts)")
            else:
                continue
        except ProviderUnavailable as exc:
            notes.append(f"{p.name}: {exc.reason}")
            continue
        except Exception as exc:  # noqa: BLE001
            notes.append(f"{p.name}: {type(exc).__name__}: {exc}")
            continue
        if not contracts:
            notes.append(f"{p.name}: no contracts with an IV in the band")
            continue
        s = build_surface(contracts, float(spot), grid, int(max_dte))
        if not s["expiries"]:
            notes.append(f"{p.name}: no expiry with {MIN_POINTS}+ usable contracts")
            continue
        return to_jsonable({"underlying": u, "source": p.name,
                            "asof": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
                            "units": "pct", **s, "warnings": notes + s["warnings"]})
    raise NoSurface(f"No IV surface for {u}: " + ("; ".join(notes) or "no provider with option IVs available"))
