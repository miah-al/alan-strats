"""
api/services/earnings.py — the next earnings date per symbol, from yfinance's calendar, cached a day.

One yfinance request per symbol per day (through the request gate); indices are skipped without a
request, and a symbol with no calendar (an ETF) is remembered as having none for the day. Used by
``/api/market/vol-stats`` (``next_earnings``) and ``/api/market/events`` (earnings rows).
"""
from __future__ import annotations

import datetime as _dt
import logging
import threading
from typing import Optional

from api.marketdata import symbols as SYM

logger = logging.getLogger("alan_trader.api.earnings")

_CACHE: dict[str, tuple[_dt.date, list[_dt.date]]] = {}
_LOCK = threading.Lock()


def earnings_dates(symbol: str) -> list[_dt.date]:
    """Upcoming (and today's) earnings dates yfinance lists for ``symbol`` (usually one; a range when
    the company has not confirmed the day)."""
    sym = SYM.normalize(symbol)
    if SYM.is_index(sym) or SYM.is_option(sym):
        return []
    today = _dt.date.today()
    with _LOCK:
        hit = _CACHE.get(sym)
        if hit is not None and hit[0] == today:
            return list(hit[1])
    out: list[_dt.date] = []
    try:
        import yfinance as yf
        cal = yf.Ticker(SYM.to_yfinance(sym)).calendar or {}
        raw = cal.get("Earnings Date") if isinstance(cal, dict) else None
        for d in raw or []:
            try:
                d = d if isinstance(d, _dt.date) else _dt.date.fromisoformat(str(d)[:10])
            except ValueError:
                continue
            if isinstance(d, _dt.datetime):
                d = d.date()
            if d >= today:
                out.append(d)
    except Exception as exc:  # noqa: BLE001 — no calendar is an answer, not an error
        logger.info("earnings calendar for %s unavailable: %s", sym, exc)
        return []                               # not cached: a failure may be transient
    out = sorted(set(out))
    with _LOCK:
        _CACHE[sym] = (today, out)
    return out


def next_earnings(symbol: str) -> Optional[_dt.date]:
    d = earnings_dates(symbol)
    return d[0] if d else None
