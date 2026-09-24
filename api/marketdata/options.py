"""
api/marketdata/options.py — expirations and the option chain, with greeks and IV.

Providers in preference order: tastytrade (the chain's strikes and symbols from its REST API — one
request per underlying, cached 30 min — and live quotes, greeks and IV for the visible strikes from
the DXLink streamer), then Polygon (one options chain snapshot per request, greeks from Polygon),
then yfinance (one option_chain request, greeks from Black-Scholes on its IV). Chains are cached
15 s and expirations 5 min per underlying, whichever provider answered.
"""
from __future__ import annotations

import datetime as _dt
import logging
import time
from typing import Optional

from api.marketdata import symbols as SYM
from api.marketdata.cache import CHAIN_TTL, EXPIRATIONS_TTL, cached
from api.marketdata.hub import MarketDataHub
from api.serialize import table_from_rows, to_jsonable
from data.request_gate import ProviderUnavailable

logger = logging.getLogger("alan_trader.api.marketdata.options")

SIDE_FIELDS = ["bid", "ask", "mid", "last", "iv", "delta", "gamma", "theta", "vega", "oi", "volume", "symbol"]
#: how long a chain's streamed contracts stay subscribed after the last request for them
CHAIN_LINGER_S = 120.0
#: a fresh subscription's quotes arrive within a second; its greeks a few seconds later
CHAIN_WAIT_S = 8.0


class NoChain(LookupError):
    """No provider could produce the chain; routers answer 422 with the reasons."""


def _spot(hub: MarketDataHub, underlying: str) -> Optional[float]:
    try:
        return hub.price(underlying, wait=3.0)
    except Exception:
        return None


def _chain_providers(hub: MarketDataHub):
    return [p for p in hub.providers if "chain" in p.capabilities and p.available()]


def expirations(hub: MarketDataHub, underlying: str) -> dict:
    u = SYM.normalize(underlying)
    if SYM.is_option(u):
        raise ValueError(f"{underlying!r} is an option; ask for its underlying's expirations")
    spot = _spot(hub, u)
    notes: list[str] = []
    for p in _chain_providers(hub):
        if p.name == "tastytrade" and not getattr(p, "connected", False):
            notes.append("tastytrade: not connected")
            continue
        try:
            exps = cached(("expirations", p.name, u), EXPIRATIONS_TTL, lambda p=p: p.expirations(u, spot=spot)
                          if p.name != "tastytrade" else p.expirations(u))
        except (ProviderUnavailable, NotImplementedError) as exc:
            notes.append(f"{p.name}: {getattr(exc, 'reason', exc) or type(exc).__name__}")
            continue
        except Exception as exc:  # noqa: BLE001
            notes.append(f"{p.name}: {type(exc).__name__}: {exc}")
            continue
        if not exps:
            notes.append(f"{p.name}: no expirations")
            continue
        today = _dt.date.today()
        return to_jsonable({"underlying": u, "spot": spot, "source": p.name,
                            "expirations": [{"expiry": d, "dte": (d - today).days} for d in exps],
                            "warnings": notes})
    raise NoChain(f"No option expirations for {u}: " + ("; ".join(notes) or "no chain provider available"))


def _streamed_chain(hub: MarketDataHub, p, u: str, expiry: _dt.date, spot: Optional[float], n: int) -> Optional[dict]:
    contracts = p.chain_contracts(u, expiry)
    if not contracts:
        return None
    ks = [k for k, _, _ in contracts]
    if spot is None:
        mid = len(ks) // 2
    else:
        mid = next((i for i, k in enumerate(ks) if k > spot), len(ks))
    picked = contracts[max(0, mid - n): min(len(ks), mid + n)]
    syms = [s for _, c, pt in picked for s in (c, pt)]
    owner = f"chain:{u}:{expiry.isoformat()}"
    hub.watch(owner, syms)
    # keep them subscribed a while after the request (the client usually streams them next), then let go
    with hub._lock:
        deadline = time.monotonic() + CHAIN_LINGER_S
        for s in syms:
            hub.linger[s] = max(hub.linger.get(s, 0.0), deadline)
    hub.unwatch(owner, syms)
    end = time.monotonic() + CHAIN_WAIT_S
    with hub._cond:
        while time.monotonic() < end:
            priced = sum(1 for s in syms if s in hub.quotes and hub.quotes[s].has_price)
            greeks = sum(1 for s in syms if s in hub.quotes and hub.quotes[s].values.get("iv") is not None)
            if priced >= 0.9 * len(syms) and greeks >= 0.9 * len(syms):
                break
            hub._cond.wait(timeout=0.2)
    rows = []
    with hub._lock:
        for k, c, pt in picked:
            row = {"strike": k}
            for side, s in (("call", c), ("put", pt)):
                q = hub.quotes.get(s)
                m = q.to_message() if q is not None else {}
                row[side] = {"bid": m.get("bid"), "ask": m.get("ask"), "last": m.get("last"), "iv": m.get("iv"),
                             "delta": m.get("delta"), "gamma": m.get("gamma"), "theta": m.get("theta"),
                             "vega": m.get("vega"), "oi": m.get("oi"), "volume": m.get("volume"), "symbol": s}
            rows.append(row)
    return {"rows": rows, "source": p.name}


def _flatten(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        flat = {"strike": r["strike"]}
        for side in ("call", "put"):
            q = r.get(side) or {}
            b, a = q.get("bid"), q.get("ask")
            mid = (b + a) / 2.0 if (b is not None and a is not None and a >= b and a > 0) else None
            for f in SIDE_FIELDS:
                flat[f"{side}_{f}"] = mid if f == "mid" else q.get(f)
        out.append(flat)
    return out


_TYPES = {"strike": "number", **{f"{s}_{f}": ("string" if f == "symbol" else "number")
                                  for s in ("call", "put") for f in SIDE_FIELDS}}
_FORMATS = {"strike": "price", **{f"{s}_{f}": fmt for s in ("call", "put")
                                   for f, fmt in (("bid", "price"), ("ask", "price"), ("mid", "price"),
                                                  ("last", "price"), ("iv", "ratio"), ("oi", "int"),
                                                  ("volume", "int"))}}
_HEADERS = {"strike": "Strike", **{f"{s}_{f}": f"{s.title()} {f.upper() if f in ('iv', 'oi') else f.title()}"
                                    for s in ("call", "put") for f in SIDE_FIELDS}}


def chain(hub: MarketDataHub, underlying: str, expiry: str, strikes: int = 30) -> dict:
    u = SYM.normalize(underlying)
    try:
        exp = _dt.date.fromisoformat(str(expiry)[:10])
    except ValueError:
        raise ValueError("expiry must be an ISO date (YYYY-MM-DD)")
    if exp < _dt.date.today():
        raise ValueError(f"{exp} has expired")
    n = max(1, min(int(strikes), 200))
    spot = _spot(hub, u)
    notes: list[str] = []
    got = None
    for p in _chain_providers(hub):
        try:
            if p.streaming:
                if not getattr(p, "connected", False):
                    notes.append(f"{p.name}: not connected")
                    continue
                got = _streamed_chain(hub, p, u, exp, spot, n)
            else:
                got = cached(("chain", p.name, u, exp, n, round(spot or 0, 0)), CHAIN_TTL,
                             lambda p=p: p.chain(u, exp, spot, n))
        except (ProviderUnavailable, NotImplementedError) as exc:
            notes.append(f"{p.name}: {getattr(exc, 'reason', exc) or type(exc).__name__}")
            got = None
            continue
        except Exception as exc:  # noqa: BLE001
            notes.append(f"{p.name}: {type(exc).__name__}: {exc}")
            got = None
            continue
        if got and got.get("rows"):
            break
        notes.append(f"{p.name}: no contracts for {exp}")
        got = None
    if not got:
        raise NoChain(f"No option chain for {u} {exp}: " + ("; ".join(notes) or "no chain provider available"))
    rows = _flatten(got["rows"])
    fields = list(_TYPES)
    table = table_from_rows(rows, field_order=fields, headers=_HEADERS, formats=_FORMATS, types=_TYPES)
    today = _dt.date.today()
    return to_jsonable({"underlying": u, "spot": spot, "expiry": exp, "dte": (exp - today).days,
                        "asof": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
                        "source": got["source"], "strikes": n, "table": table,
                        "units": {"iv": "fraction", "theta": "per day", "vega": "per 1 vol point"},
                        "warnings": notes})
