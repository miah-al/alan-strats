"""
api/marketdata/options.py — expirations and the option chain, with greeks and IV.

A chain is merged across providers, field group by field group. The strikes and symbols come from the
first provider that answers: tastytrade (its REST chain, one request per underlying, cached 30 min),
else yfinance, else Polygon. Then per contract: bid / ask from tastytrade's streamer (live, or the
session's last quotes after hours), else yfinance's chain; IV and greeks from the streamer, else
Polygon's snapshot, else yfinance (Black-Scholes on its IV); open interest and volume likewise. A
secondary provider is only asked when the first ones leave a group uncovered (under 90% of the
contracts). Polygon's plan here has no option bid/ask, so it never supplies quotes. Chains are
cached 15 s and expirations 5 min per underlying and provider.
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


def _streamed_chain(hub: MarketDataHub, p, u: str, expiry: _dt.date, spot: Optional[float], n: int,
                    linger: float = CHAIN_LINGER_S) -> Optional[dict]:
    contracts = p.chain_contracts(u, expiry)
    if not contracts:
        return None
    picked = _pick([k for k, _, _ in contracts], spot, n)
    picked = [c for c in contracts if c[0] in picked]
    syms = [s for _, c, pt in picked for s in (c, pt)]
    owner = f"chain:{u}:{expiry.isoformat()}:{time.monotonic()}"
    hub.watch(owner, syms)
    # keep them subscribed a while after the request (the client usually streams them next), then let go
    if linger > 0:
        with hub._lock:
            deadline = time.monotonic() + linger
            for s in syms:
                hub.linger[s] = max(hub.linger.get(s, 0.0), deadline)
    try:
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
                                 "vega": m.get("vega"), "oi": m.get("oi"), "volume": m.get("volume"), "symbol": s,
                                 "quote_time": m.get("time") if m.get("bid") is not None else None}
                rows.append(row)
    finally:
        hub.unwatch(owner, syms)
    return {"rows": rows, "source": p.name}


def _pick(strikes: list[float], spot: Optional[float], n: int) -> set:
    ks = sorted(set(strikes))
    mid = len(ks) // 2 if spot is None else next((i for i, k in enumerate(ks) if k > spot), len(ks))
    return set(ks[max(0, mid - n): min(len(ks), mid + n)])


# Which provider a field comes from, in order (a provider's ``chain_ranks``, lower first; a streaming
# provider without one ranks first): quotes from the broker's stream (live, or the session's last after
# hours), then yfinance's chain; greeks and IV from the stream, then Polygon's snapshot, then yfinance
# (Black-Scholes on its IV). A provider whose option quotes are known to be empty (Polygon here) is left
# out of the quote order.
GROUPS = ("skeleton", "quotes", "greeks", "sizes")


def _orders(provs: list) -> dict[str, list[str]]:
    def rank(p, g):
        r = (getattr(p, "chain_ranks", None) or {}).get(g)
        return r if r is not None else (0 if p.streaming else 5)
    out = {g: [p.name for p in sorted(provs, key=lambda p: rank(p, g))] for g in GROUPS}
    out["quotes"] = [n for n in out["quotes"] if getattr(next(p for p in provs if p.name == n), "option_quotes", None)
                     is not False]
    return out
_QUOTE_F = ("bid", "ask")
_GREEK_F = ("iv", "delta", "gamma", "theta", "vega")
#: a secondary source is fetched when fewer than this share of the contracts have the field group
COVERAGE = 0.9
STALE_QUOTE_S = 120.0


def _two_sided(q: dict) -> bool:
    b, a = q.get("bid"), q.get("ask")
    return b is not None and a is not None and a > 0 and a >= b


def _coverage(rows: list[dict], test) -> float:
    sides = [r.get(s) or {} for r in rows for s in ("call", "put")]
    return (sum(1 for q in sides if test(q)) / len(sides)) if sides else 0.0


def _source_rows(hub: MarketDataHub, p, u: str, exp: _dt.date, spot: Optional[float], n: int) -> Optional[list]:
    if p.streaming:
        got = _streamed_chain(hub, p, u, exp, spot, n)
    else:
        got = cached(("chain", p.name, u, exp, n, round(spot or 0, 0)), CHAIN_TTL, lambda: p.chain(u, exp, spot, n))
    return (got or {}).get("rows") or None


def _merge(skeleton: list[dict], sources: dict[str, list[dict]], orders: dict[str, list[str]]) -> list[dict]:
    """Rows on the skeleton's strikes; each side's quote / greeks / size fields from the first source in
    that group's order that has them for the contract (matched by strike and side)."""
    by = {name: {round(float(r["strike"]), 4): r for r in rows} for name, rows in sources.items()}
    QUOTE_ORDER, GREEK_ORDER, SIZE_ORDER = orders["quotes"], orders["greeks"], orders["sizes"]
    out = []
    for base in skeleton:
        k = round(float(base["strike"]), 4)
        row = {"strike": base["strike"]}
        for side in ("call", "put"):
            c = {name: ((by[name].get(k) or {}).get(side) or {}) for name in by}
            sym = (base.get(side) or {}).get("symbol") or next((q.get("symbol") for q in c.values() if q.get("symbol")), None)
            qsrc = next((n for n in QUOTE_ORDER if n in c and _two_sided(c[n])), None)
            gsrc = next((n for n in GREEK_ORDER if n in c and c[n].get("iv") is not None), None)
            m = {"symbol": sym,
                 "bid": c[qsrc].get("bid") if qsrc else None, "ask": c[qsrc].get("ask") if qsrc else None,
                 "quote_time": c[qsrc].get("quote_time") if qsrc else None,
                 "last": next((c[n].get("last") for n in QUOTE_ORDER if n in c and c[n].get("last") is not None), None),
                 "quote_source": qsrc, "greeks_source": gsrc}
            for f in _GREEK_F:
                v = c[gsrc].get(f) if gsrc else None
                if v is None and gsrc:                 # IV without that greek there: the next source's
                    v = next((c[n].get(f) for n in GREEK_ORDER if n in c and c[n].get(f) is not None), None)
                m[f] = v
            for f in ("oi", "volume"):
                m[f] = next((c[n].get(f) for n in SIZE_ORDER if n in c and c[n].get(f) is not None), None)
            row[side] = m
        out.append(row)
    return out


def _flatten(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        flat = {"strike": r["strike"]}
        for side in ("call", "put"):
            q = r.get(side) or {}
            mid = (q["bid"] + q["ask"]) / 2.0 if _two_sided(q) else None
            for f in SIDE_FIELDS:
                flat[f"{side}_{f}"] = mid if f == "mid" else q.get(f)
            flat[f"{side}_quote_source"] = q.get("quote_source")
            flat[f"{side}_greeks_source"] = q.get("greeks_source")
        out.append(flat)
    return out


_EXTRA = [f"{s}_{f}" for s in ("call", "put") for f in ("quote_source", "greeks_source")]
_TYPES = {"strike": "number", **{f"{s}_{f}": ("string" if f == "symbol" else "number")
                                  for s in ("call", "put") for f in SIDE_FIELDS},
          **{f: "string" for f in _EXTRA}}
_FORMATS = {"strike": "price", **{f"{s}_{f}": fmt for s in ("call", "put")
                                   for f, fmt in (("bid", "price"), ("ask", "price"), ("mid", "price"),
                                                  ("last", "price"), ("iv", "ratio"), ("oi", "int"),
                                                  ("volume", "int"))}}
_HEADERS = {"strike": "Strike", **{f"{s}_{f}": f"{s.title()} {f.upper() if f in ('iv', 'oi') else f.title()}"
                                    for s in ("call", "put") for f in SIDE_FIELDS},
            **{f: f.replace("_", " ").title() for f in _EXTRA}}


def _market_open(now=None) -> bool:
    import pandas as pd
    now = now or pd.Timestamp.now(tz="America/New_York")
    return now.weekday() < 5 and _dt.time(9, 30) <= now.time() < _dt.time(16, 0)


def merged_chain(hub: MarketDataHub, u: str, exp: _dt.date, spot: Optional[float], n: int,
                 notes: list[str], linger: bool = True) -> tuple[list[dict], list[str]]:
    """The chain's rows for ``n`` strikes either side of spot, merged across providers. Returns
    (rows, sources used). Secondary sources are fetched only for a field group the first ones lack."""
    provs = {p.name: p for p in _chain_providers(hub)}
    orders = _orders(list(provs.values()))
    sources: dict[str, list[dict]] = {}
    skeleton = None
    wide = n * 2 + 10                      # a secondary on another strike grid still covers the skeleton's range

    def fetch(name: str, count: int) -> Optional[list]:
        p = provs.get(name)
        if p is None:
            return None
        if p.streaming and not getattr(p, "connected", False):
            notes.append(f"{name}: not connected")
            return None
        try:
            rows = _source_rows(hub, p, u, exp, spot, count) if (not p.streaming or linger) else \
                (_streamed_chain(hub, p, u, exp, spot, count, linger=0) or {}).get("rows")
        except (ProviderUnavailable, NotImplementedError) as exc:
            notes.append(f"{name}: {getattr(exc, 'reason', exc) or type(exc).__name__}")
            return None
        except Exception as exc:  # noqa: BLE001
            notes.append(f"{name}: {type(exc).__name__}: {exc}")
            return None
        if not rows:
            notes.append(f"{name}: no contracts for {exp}")
        return rows

    for name in orders["skeleton"]:                          # the first that answers gives the strikes
        if name not in provs or name in sources:
            continue
        rows = fetch(name, n)
        if rows:
            sources[name] = rows
            picked = _pick([r["strike"] for r in rows], spot, n)
            skeleton = [r for r in rows if r["strike"] in picked]
            break
    if skeleton is None:
        return [], []
    # walk each group's order: ask the next provider only while the better-ranked ones leave the group
    # under-covered (yfinance's IVs do not stand in for Polygon's greeks just because it was asked first)
    for group, test in (("quotes", _two_sided), ("greeks", lambda q: q.get("iv") is not None)):
        order = orders[group]
        for i, name in enumerate(order):
            better = {n: sources[n] for n in order[:i] if n in sources}
            if better and _coverage(_merge(skeleton, better, orders), test) >= COVERAGE:
                break
            if name in sources:
                continue
            rows = fetch(name, wide)
            if rows:
                sources[name] = rows
    return _merge(skeleton, sources, _orders(list(provs.values()))), list(sources)


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
    rows, used = merged_chain(hub, u, exp, spot, n, notes)
    if not rows:
        raise NoChain(f"No option chain for {u} {exp}: " + ("; ".join(notes) or "no chain provider available"))
    flat = _flatten(rows)
    sides = [r.get(s) or {} for r in rows for s in ("call", "put")]
    qsrc = [q.get("quote_source") for q in sides if q.get("quote_source")]
    gsrc = [q.get("greeks_source") for q in sides if q.get("greeks_source")]
    quote_source = max(set(qsrc), key=qsrc.count) if qsrc else None
    greeks_source = max(set(gsrc), key=gsrc.count) if gsrc else None
    quoted = len(qsrc)
    times = [q.get("quote_time") for q in sides if q.get("quote_time")]
    quotes_asof = max(times) if times else None
    stale = False
    if quoted == 0:
        notes.append("no bid/ask from any provider for this chain")
    elif quoted < len(sides):
        notes.append(f"{len(sides) - quoted} of {len(sides)} contracts have no two-sided quote")
    if not _market_open():
        stale = True
        notes.append("market closed: bid/ask are the last quotes of the session"
                     + (f" (latest {quotes_asof[11:16]})" if quotes_asof else ""))
    elif quotes_asof:
        age = (_dt.datetime.now().astimezone() - _dt.datetime.fromisoformat(quotes_asof)).total_seconds()
        if age > STALE_QUOTE_S:
            stale = True
            notes.append(f"quotes are {age / 60:.0f} min old")
    if quote_source == "yfinance":
        notes.append("bid/ask from yfinance (about 15 minutes delayed)")
    table = table_from_rows(flat, field_order=list(_TYPES), headers=_HEADERS, formats=_FORMATS, types=_TYPES)
    today = _dt.date.today()
    return to_jsonable({"underlying": u, "spot": spot, "expiry": exp, "dte": (exp - today).days,
                        "asof": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
                        "source": used[0] if used else None, "sources": used,
                        "quote_source": quote_source, "greeks_source": greeks_source,
                        "quotes_asof": quotes_asof, "stale": stale, "quoted": quoted, "contracts": len(sides),
                        "strikes": n, "table": table,
                        "units": {"iv": "fraction", "theta": "per day", "vega": "per 1 vol point"},
                        "warnings": notes})
