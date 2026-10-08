"""
api/services/pair_charts.py — charts for trading one index against another (2026-10-07; the owner: "build another chart
for ratio of just ndx vs spx ratio ... I should be able to change to any ticker ... call it ratio", and the spread-vs-
spread combo of the NDX/SPX structure "like the one I gave you" from TOS).

``ratio(a, b, ...)``  any two tickers' 1-minute closes for the session (the service's intraday bars), their ratio A/B,
                      its EMA and the ±z lines: X = (ln A − ln B) × A's first close, EMA over X, the population sd of the
                      last ``sd`` one-minute changes of X, each line turned back into ratio units. Those are the formulas of
                      a pair strategy's stretch (ndx_spx_ratio), so on its pair the lines are where it enters. Any paper
                      pair runner's trades on that pair today are returned as markers.
``combo(...)``        a pair strategy's structure as ONE price through the session, like a custom spread in TOS: each leg's
                      1-minute closes (last trades) from the broker's candle feed (DXLink: market data, no REST budget),
                      carried forward, summed with the structure's signs and sizes. The legs' own verticals come too.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import math
import os
import threading
import time
from typing import Callable, Optional

import pandas as pd

logger = logging.getLogger("alan_trader.api.pair_charts")

NY = "America/New_York"
CANDLE_TTL = 15.0


# ── the stretch ───────────────────────────────────────────────────────────────

def ratio_series(a: list, b: list, ema_len: int = 15, sd_window: int = 60, z: float = 3.0) -> dict:
    """ratio, its EMA and the entry lines (ratio units) and z, minute by minute; None before there is history."""
    n = min(len(a), len(b))
    out = {"ratio": [], "ema": [], "upper": [], "lower": [], "z": []}
    if n == 0:
        return out
    a0 = float(a[0])
    k = 2.0 / (int(ema_len) + 1.0)
    xs: list = []
    ema = None
    for i in range(n):
        A, B = float(a[i]), float(b[i])
        x = (math.log(A) - math.log(B)) * a0
        ema = x if ema is None else k * x + (1.0 - k) * ema
        xs.append(x)
        out["ratio"].append(A / B)
        out["ema"].append(math.exp(ema / a0))
        if i < 1:
            for key in ("upper", "lower", "z"):
                out[key].append(None)
            continue
        lo = max(1, i - int(sd_window) + 1)
        d = [xs[j] - xs[j - 1] for j in range(lo, i + 1)]
        mu = sum(d) / len(d)
        sd = math.sqrt(sum((v - mu) ** 2 for v in d) / len(d))
        out["upper"].append(math.exp((ema + float(z) * sd) / a0))
        out["lower"].append(math.exp((ema - float(z) * sd) / a0))
        out["z"].append((x - ema) / (sd + 1e-6))
    return out


def _closes(frame: dict) -> pd.Series:
    """An intraday answer ({t: [...], c: [...]}) as a close series by naive-ET minute."""
    t, c = frame.get("t") or [], frame.get("c") or []
    s = pd.Series([float(x) if x is not None else float("nan") for x in c],
                  index=pd.to_datetime(pd.Index([str(x) for x in t])), dtype=float)
    if getattr(s.index, "tz", None) is not None:
        s.index = s.index.tz_convert(NY).tz_localize(None)
    return s[~s.index.duplicated(keep="last")].dropna().sort_index()


def _state_files(day: _dt.date) -> list:
    try:
        from paper.views import state_dirs
        dirs = list(state_dirs())
    except Exception:  # noqa: BLE001
        dirs = []
    out = []
    for d in dirs:
        try:
            out += sorted(d.glob(f"*_{day.isoformat()}.json"))
        except OSError:
            continue
    return [f for f in out if not f.name.startswith(("heartbeat_", "broker_calls_"))]


def pair_states(day: _dt.date, a: Optional[str] = None, b: Optional[str] = None) -> list[tuple[str, dict]]:
    """(slug, saved state) of the paper pair runners of ``day`` (on the pair a/b when given, either order)."""
    out = []
    for f in _state_files(day):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        pair = [str(x).upper() for x in (d.get("pair") or [])]
        if len(pair) != 2:
            continue
        if a and b and sorted(pair) != sorted([a.upper(), b.upper()]):
            continue
        out.append((f.stem.rsplit("_", 1)[0], d))
    return out


def trade_markers(states: list[tuple[str, dict]], day: _dt.date) -> list[dict]:
    """The open / close fills of the pair runners' saved states, as chart markers."""
    out = []
    for slug, d in states:
        for f in ((d.get("state") or {}).get("fills") or []):
            if f.get("kind") not in ("open", "close"):
                continue
            m = int(f.get("m", 0))
            ts = _dt.datetime.combine(day, _dt.time(0, 0)) + _dt.timedelta(minutes=m)
            vs = list(f.get("verticals") or [])
            out.append({"strategy": slug, "time": ts.isoformat(timespec="minutes"), "kind": f["kind"],
                        "direction": f.get("direction"), "px": f.get("px"), "z": f.get("z"),
                        "reason": str(f.get("reason", ""))[:300],
                        "verticals": [{"index": v.get("index"), "kind": v.get("kind"), "kl": v.get("kl"), "kh": v.get("kh"),
                                       "qty": v.get("qty"), "px": v.get("px")} for v in vs]})
    return sorted(out, key=lambda r: r["time"])


def ratio(a: str, b: str, ema: int = 15, sd: int = 60, z: float = 3.0, hub=None, agg=None,
          intraday_fn: Optional[Callable] = None) -> dict:
    """The ratio chart: both tickers' session minutes, aligned on the minute (the last close carried over a gap)."""
    from api.services import intraday as I
    a, b = a.strip().upper(), b.strip().upper()
    if not a or not b or a == b:
        raise ValueError("give two different tickers")
    fn = intraday_fn or (lambda s: I.intraday(s, 390, 1, hub=hub, agg=agg))
    fa, fb = fn(a), fn(b)
    sa, sb = _closes(fa), _closes(fb)
    if sa.empty or sb.empty:
        missing = ", ".join(t for t, s in ((a, sa), (b, sb)) if s.empty)
        raise LookupError(f"no 1-minute bars for {missing} this session")
    idx = sa.index.union(sb.index)
    both = pd.DataFrame({"a": sa.reindex(idx).ffill(), "b": sb.reindex(idx).ffill()}).dropna()
    if both.empty:
        raise LookupError(f"{a} and {b} have no minute in common this session")
    ser = ratio_series(both["a"].tolist(), both["b"].tolist(), ema, sd, z)
    day = both.index[-1].date()
    out = {"a": a, "b": b, "session": str(day), "times": [t.isoformat(timespec="minutes") for t in both.index],
           "a_close": [round(x, 4) for x in both["a"]], "b_close": [round(x, 4) for x in both["b"]],
           "params": {"ema": int(ema), "sd": int(sd), "z": float(z)},
           "sources": {"a": fa.get("source") or fa.get("vendor"), "b": fb.get("source") or fb.get("vendor")},
           "delayed_minutes": max([x for x in (fa.get("delayed_minutes"), fb.get("delayed_minutes")) if x is not None] or [0]),
           "trades": trade_markers(pair_states(day, a, b), day)}
    for k, v in ser.items():
        out[k] = [None if x is None else round(float(x), 6 if k != "z" else 3) for x in v]
    return out


# ── the combo (spread vs spread) ──────────────────────────────────────────────

def option_streamer_symbol(root: str, expiry: _dt.date, cp: str, strike: float) -> str:
    """DXLink's option symbol: .NDXP261008C31090, .SPXW261008P7812.5"""
    k = float(strike)
    ks = str(int(k)) if k.is_integer() else (f"{k:.3f}".rstrip("0").rstrip("."))
    return f".{root.upper()}{expiry:%y%m%d}{cp.upper()[0]}{ks}"


class CandleSource:
    """1-minute candles (closes) for a handful of symbols from the broker's DXLink candle feed, from 09:30 of ``day``.
    Market data, not a REST call: it costs nothing from the broker's day budget. One OAuth session, reused; one pull at
    a time; each symbol set cached for CANDLE_TTL seconds."""

    def __init__(self):
        self._lock = threading.Lock()
        self._session = None
        self._cache: dict = {}

    def _session_obj(self):
        if self._session is None:
            try:
                from engine.env import load_env
                load_env()
            except Exception:  # noqa: BLE001
                pass
            secret, refresh = os.environ.get("TT_SECRET"), os.environ.get("TT_REFRESH")
            if not secret or not refresh:
                raise RuntimeError("tastytrade credentials missing (TT_SECRET / TT_REFRESH)")
            from tastytrade import Session
            self._session = Session(secret, refresh)
        return self._session

    def closes(self, symbols: list, day: _dt.date) -> dict:
        key = (tuple(sorted(symbols)), day)
        now = time.monotonic()
        hit = self._cache.get(key)
        if hit is not None and now - hit[0] < CANDLE_TTL:
            return hit[1]
        with self._lock:
            hit = self._cache.get(key)
            if hit is not None and time.monotonic() - hit[0] < CANDLE_TTL:
                return hit[1]
            try:
                got = self._pull(list(symbols), day)
            except Exception as exc:  # noqa: BLE001 - one retry on a fresh session (an expired token)
                logger.warning("candle pull failed (%s); retrying on a new session", exc)
                self._session = None
                got = self._pull(list(symbols), day)
            self._cache[key] = (time.monotonic(), got)
            return got

    def _pull(self, symbols: list, day: _dt.date) -> dict:
        import asyncio

        async def pull():
            import anyio
            from tastytrade import DXLinkStreamer
            from tastytrade.dxfeed import Candle
            start = _dt.datetime.combine(day, _dt.time(9, 30))
            end = _dt.datetime.combine(day, _dt.time(16, 1))
            rows: dict = {s: {} for s in symbols}
            async with DXLinkStreamer(self._session_obj()) as st:
                await st.subscribe_candle(list(symbols), "1m", start_time=start)
                quiet = 0
                while quiet < 12:
                    await anyio.sleep(0.25)
                    fresh = False
                    c = st.get_event_nowait(Candle)
                    while c is not None:
                        if c.time and c.close:
                            sym = str(c.event_symbol).split("{")[0]
                            ts = _dt.datetime.fromtimestamp(c.time / 1000)
                            if sym in rows and start <= ts < end:
                                rows[sym][ts] = float(c.close)
                                fresh = True
                        c = st.get_event_nowait(Candle)
                    quiet = 0 if fresh else quiet + 1
            return {s: sorted(v.items()) for s, v in rows.items()}

        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(pull())
        finally:
            loop.close()


_CANDLES: Optional[CandleSource] = None


def candle_source() -> CandleSource:
    global _CANDLES
    if _CANDLES is None:
        _CANDLES = CandleSource()
    return _CANDLES


def combo_legs(inst: dict, k: list) -> list[dict]:
    """The structure's legs from a pair strategy's live_instrument() and each vertical's long strike: [{index, root, cp,
    strike, sign, qty}] in long-structure terms (a call vertical is long k / short k + width; a put vertical long k / short
    k - width)."""
    legs = []
    for leg, kl in zip(inst.get("legs") or [], k):
        kind, w, q = str(leg["kind"]), float(leg["width"]), int(leg.get("per_structure", 1))
        cp = "C" if kind == "call" else "P"
        k_long = float(kl)
        k_short = k_long + w if kind == "call" else k_long - w
        legs.append(dict(index=str(leg["index"]).upper(), root=str(leg["root"]).upper(), cp=cp, strike=k_long, sign=1, qty=q))
        legs.append(dict(index=str(leg["index"]).upper(), root=str(leg["root"]).upper(), cp=cp, strike=k_short, sign=-1, qty=q))
    return legs


def default_strikes(strategy, states: list[tuple[str, dict]], spots: dict) -> tuple[list, str]:
    """The strikes to chart when none are given: the open structure's, else the day's last trade's, else the structure
    the strategy would open at the latest levels."""
    for _, d in states:
        fills = [f for f in ((d.get("state") or {}).get("fills") or []) if f.get("kind") in ("open", "close")]
        opens = [f for f in fills if f["kind"] == "open"]
        if opens:
            last = opens[-1]
            vs = last.get("verticals") or []
            ks = [(float(v["kl"]) if v.get("kind") == "call" else float(v["kh"])) for v in vs]
            still = len([f for f in fills if f["kind"] == "open"]) > len([f for f in fills if f["kind"] == "close"])
            return ks, ("the open structure" if still else "the day's last trade")
    if hasattr(strategy, "check_structures") and all(spots.get(i) for i in ("NDX", "SPX")):
        cs = strategy.check_structures(spots["NDX"], spots["SPX"])
        ks = [(float(kl) if kind == "call" else float(kh)) for _, kind, kl, kh, _ in cs]
        return ks, "centred on the latest levels"
    raise LookupError("no strikes given, no trade today and no index levels to centre a structure on")


def combo(slug: str, day: Optional[_dt.date] = None, k: Optional[list] = None, closes_fn: Optional[Callable] = None,
          spot_fn: Optional[Callable] = None) -> dict:
    """The pair strategy's structure as one price through ``day``'s session (default: today), from its legs' candles."""
    from strategy_api import registry as R
    strategy = R.get_strategy(slug)
    inst = strategy.live_instrument() or {}
    if not inst.get("pair"):
        raise ValueError(f"{slug} is not a pair strategy")
    day = day or pd.Timestamp.now(tz=NY).date()
    states = pair_states(day)
    states = [(s, d) for s, d in states if s == slug]
    why = "the strikes asked for"
    if not k:
        spots = {}
        for _, d in states:
            st = d.get("state") or {}
            if st.get("ndx") and st.get("spx"):
                spots = {"NDX": float(st["ndx"][-1]), "SPX": float(st["spx"][-1])}
        if not spots and spot_fn is not None:
            spots = spot_fn() or {}
        k, why = default_strikes(strategy, states, spots)
    legs = combo_legs(inst, k)
    for leg in legs:
        leg["symbol"] = option_streamer_symbol(leg["root"], day, leg["cp"], leg["strike"])
    fn = closes_fn or (lambda syms: candle_source().closes(syms, day))
    raw = fn([leg["symbol"] for leg in legs])
    series = {}
    for leg in legs:
        pts = raw.get(leg["symbol"]) or []
        if not pts:
            continue
        s = pd.Series([p for _, p in pts], index=pd.to_datetime([t for t, _ in pts]), dtype=float)
        series[leg["symbol"]] = s[~s.index.duplicated(keep="last")].sort_index()
    missing = [leg["symbol"] for leg in legs if leg["symbol"] not in series]
    if missing:
        raise LookupError("no prints yet for " + ", ".join(missing))
    idx = sorted(set().union(*[set(s.index) for s in series.values()]))
    frame = pd.DataFrame({sym: s.reindex(idx).ffill() for sym, s in series.items()}).dropna()
    if frame.empty:
        raise LookupError("the legs have not all printed yet")
    total = sum(leg["sign"] * leg["qty"] * frame[leg["symbol"]] for leg in legs)
    verts = []
    for i in range(0, len(legs), 2):
        lo, sh = legs[i], legs[i + 1]
        v = frame[lo["symbol"]] - frame[sh["symbol"]]
        verts.append({"label": f"{lo['index']} {lo['strike']:.0f}/{sh['strike']:.0f}{lo['cp']}" + (f" x{lo['qty']}" if lo["qty"] != 1 else ""),
                      "index": lo["index"], "qty": lo["qty"], "values": [round(float(x), 2) for x in v]})
    label = " + ".join(x["label"] for x in verts)
    markers = []
    for m in trade_markers(states, day):
        mine = [(float(v["kl"]) if v.get("kind") == "call" else float(v["kh"])) for v in m["verticals"]]
        m["on_this_combo"] = bool(mine) and all(abs(x - y) < 1e-6 for x, y in zip(mine, k))
        markers.append(m)
    return {"strategy": slug, "session": str(day), "label": label, "why": why, "strikes": [float(x) for x in k],
            "legs": [{kk: leg[kk] for kk in ("symbol", "index", "cp", "strike", "sign", "qty")} for leg in legs],
            "times": [t.isoformat(timespec="minutes") for t in frame.index], "combo": [round(float(x), 2) for x in total],
            "verticals": verts, "trades": markers,
            "source": "the broker's 1-minute candles (last trades), each leg carried forward"}
