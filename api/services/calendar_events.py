"""
api/services/calendar_events.py — what is coming up: earnings, macro releases, option expirations.

  macro     data/macro_calendar.json (checked in: 2026 FOMC, CPI, NFP, PCE, GDP with their US/Eastern times)
  opex      computed: the third Friday of each month (the Thursday before when the exchange is closed that
            Friday), quarterly in March / June / September / December
  other     exchange holidays and early closes (db/seed/events/exchange.csv)
  earnings  yfinance's calendar per requested symbol (api/services/earnings.py, cached a day)

``events(days, symbols)`` answers the window [today, today + days], sorted by date and time.
"""
from __future__ import annotations

import csv
import datetime as _dt
import json
import logging
from concurrent.futures import ThreadPoolExecutor, wait
from functools import lru_cache
from pathlib import Path
from typing import Optional

from api.bootstrap import WORKING_COPY
from api.marketdata import symbols as SYM

logger = logging.getLogger("alan_trader.api.calendar")

MACRO_FILE = WORKING_COPY / "data" / "macro_calendar.json"
EXCHANGE_FILE = WORKING_COPY / "db" / "seed" / "events" / "exchange.csv"
MAX_SYMBOLS = 40
MAX_DAYS = 366
EARNINGS_WAIT_S = 20.0
KINDS = ("earnings", "fomc", "cpi", "nfp", "pce", "gdp", "opex", "other")
_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="earnings")


@lru_cache(maxsize=1)
def _macro() -> tuple:
    try:
        doc = json.loads(Path(MACRO_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("macro calendar unreadable: %s", exc)
        return ()
    return tuple(doc.get("events") or ())


@lru_cache(maxsize=1)
def _exchange() -> tuple:
    try:
        with open(EXCHANGE_FILE, encoding="utf-8") as fh:
            return tuple(csv.DictReader(fh))
    except OSError:
        return ()


def holidays() -> set[_dt.date]:
    return {_dt.date.fromisoformat(r["date"]) for r in _exchange() if r.get("kind") == "holiday"}


def opex_dates(start: _dt.date, end: _dt.date) -> list[tuple[_dt.date, bool]]:
    """(expiration day, quarterly) for the monthly equity options between ``start`` and ``end``."""
    out = []
    hol = holidays()
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        first = _dt.date(y, m, 1)
        friday = first + _dt.timedelta(days=(4 - first.weekday()) % 7 + 14)
        day = friday - _dt.timedelta(days=1) if friday in hol else friday
        if start <= day <= end:
            out.append((day, m in (3, 6, 9, 12)))
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def events(days: int = 14, symbols: Optional[list[str]] = None,
           today: Optional[_dt.date] = None) -> tuple[list[dict], list[str]]:
    """(events, warnings)."""
    if not 0 <= int(days) <= MAX_DAYS:
        raise ValueError(f"days must be between 0 and {MAX_DAYS}")
    syms: list[str] = []
    for s in symbols or []:
        try:
            c = SYM.normalize(s)
        except ValueError:
            raise ValueError(f"not a symbol: {s!r}")
        if not SYM.is_option(c) and c not in syms:
            syms.append(c)
    if len(syms) > MAX_SYMBOLS:
        raise ValueError(f"at most {MAX_SYMBOLS} symbols")
    start = today or _dt.date.today()
    end = start + _dt.timedelta(days=int(days))
    out: list[dict] = []
    warnings: list[str] = []
    macro = _macro()
    years = {int(e["date"][:4]) for e in macro}
    for y in range(start.year, end.year + 1):
        if y not in years:
            warnings.append(f"no macro calendar for {y} (data/macro_calendar.json)")
    for e in macro:
        d = _dt.date.fromisoformat(e["date"])
        if start <= d <= end:
            out.append({"date": d, "time": e.get("time"), "kind": e["kind"] if e["kind"] in KINDS else "other",
                        "symbol": None, "title": e["title"], "source": e.get("source")})
    for d, quarterly in opex_dates(start, end):
        out.append({"date": d, "time": "16:00", "kind": "opex", "symbol": None,
                    "title": ("Quarterly options expiration (triple witching)" if quarterly
                              else "Monthly options expiration"), "source": "computed"})
    for r in _exchange():
        d = _dt.date.fromisoformat(r["date"])
        if start <= d <= end:
            out.append({"date": d, "time": "13:00" if r["kind"] == "early_close" else None, "kind": "other",
                        "symbol": None,
                        "title": (f"Market holiday: {r['label']}" if r["kind"] == "holiday" else f"Early close: {r['label']}"),
                        "source": r.get("source") or "NYSE"})
    if syms:
        from api.services.earnings import earnings_dates
        futures = {s: _POOL.submit(earnings_dates, s) for s in syms}
        done, pending = wait(futures.values(), timeout=EARNINGS_WAIT_S)
        for s, f in futures.items():
            if f not in done:
                warnings.append(f"earnings for {s} still loading; ask again shortly")
                continue
            try:
                dates = f.result()
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"earnings for {s} unavailable: {exc}")
                continue
            for d in dates:
                if start <= d <= end:
                    out.append({"date": d, "time": None, "kind": "earnings", "symbol": s,
                                "title": f"{s} earnings" + (" (date range: unconfirmed)" if len(dates) > 1 else ""),
                                "source": "yfinance"})
    out.sort(key=lambda e: (e["date"], e["time"] or "99:99", e["kind"], e["symbol"] or ""))
    return out, warnings
