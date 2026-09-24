"""
db/sync_jobs.py — one entry point for every data sync in db/sync.py, headless.

``SYNC_TYPES`` lists what can be synced (the Tools → Data Manager buttons, plus the intraday and
calendar jobs the bootstrap script runs); ``run_sync(data_type, ticker, from_date, to_date, ...)``
runs one of them and returns a normalised result ``{"status", "rows", "detail", "raw"}`` with
``status`` one of ``ok | up_to_date | no_data | error``. The service's ``/api/data/sync`` jobs and
the Dash Data Manager both come through here.

``progress(message, fraction_or_None)`` is called with whatever the sync reports. ``force`` (the
Data Manager's "Force full re-sync") first deletes the ticker's stored price bars or option
snapshots and their sync log — destructive, so only the Dash page offers it.
"""
from __future__ import annotations

import logging
import os
from datetime import date
from typing import Callable, Optional

logger = logging.getLogger(__name__)

Progress = Optional[Callable[[str, Optional[float]], None]]

#: data_type -> (label, needs_ticker, source)
SYNC_TYPES: dict[str, tuple[str, bool, str]] = {
    "price":              ("Daily price bars → mkt.PriceBar", True, "yfinance"),
    "options":            ("Option snapshots (historical IV surface) → mkt.OptionSnapshot", True, "polygon"),
    "news":               ("News with sentiment → mkt.News", True, "polygon"),
    "divs":               ("Dividends → mkt.Dividend", True, "polygon"),
    "earnings":           ("Earnings → mkt.Earnings", True, "polygon"),
    "eps_estimates":      ("EPS estimates → mkt.Earnings", True, "alphavantage"),
    "minute_bars":        ("1-minute bars → mkt.MinuteBar", True, "polygon"),
    "option_minute_bars": ("Same-day-expiry option 1-minute bars → mkt.OptionMinuteBar", True, "polygon"),
    "treasury":           ("Treasury yields → mkt.TreasuryBar", False, "fred"),
    "vix":                ("VIX daily bars → mkt.VixBar", False, "cboe"),
    "macro":              ("Macro rates → mkt.MacroBar", False, "fred"),
    "cpi":                ("CPI → mkt.CpiBar", False, "fred"),
    "fomc":               ("FOMC calendar → mkt.FomcCalendar", False, "static"),
    "event_calendar":     ("Event calendar (FOMC, CPI, NFP, opex, holidays) → mkt.EventCalendar", False, "local"),
}


def sync_types() -> list[dict]:
    return [{"data_type": k, "label": v[0], "needs_ticker": v[1], "source": v[2]} for k, v in SYNC_TYPES.items()]


def _cb(progress: Progress):
    """db/sync progress callbacks take (message) or (message, done, total, ...): one adapter for both."""
    if progress is None:
        return None

    def cb(*args):
        msg = str(args[0]) if args else ""
        frac = None
        if len(args) >= 3:
            try:
                done, total = float(args[1]), float(args[2])
                frac = done / total if total else None
            except (TypeError, ValueError):
                frac = None
        progress(msg, frac)
    return cb


def _force_reset(data_type: str, ticker: str) -> None:
    from sqlalchemy import text as _t
    from db.client import get_engine, get_ticker_id
    engine = get_engine()
    tid = get_ticker_id(engine, ticker)
    if not tid:
        return
    tbl, dtype = {"price": ("mkt.PriceBar", "PriceBar"), "options": ("mkt.OptionSnapshot", "OptionSnapshot")}[data_type]
    with engine.begin() as c:
        c.execute(_t(f"DELETE FROM {tbl} WHERE TickerId=:tid"), {"tid": tid})
        c.execute(_t("DELETE FROM mkt.SyncLog WHERE DataType=:dt AND TickerId=:tid"), {"dt": dtype, "tid": tid})


def run_sync(data_type: str, ticker: Optional[str] = None, from_date: Optional[date] = None,
             to_date: Optional[date] = None, *, api_key: Optional[str] = None, av_key: Optional[str] = None,
             force: bool = False, progress: Progress = None) -> dict:
    """Run one sync; never raises for a sync that fails (``status: error`` with the reason) —
    except for a cancellation (a BaseException from ``progress``), which propagates."""
    from db import sync as S
    from engine.env import get_polygon_api_key

    if data_type not in SYNC_TYPES:
        return {"status": "error", "rows": 0, "detail": f"unknown data type {data_type!r}", "raw": None}
    label, needs_ticker, _src = SYNC_TYPES[data_type]
    if needs_ticker and not ticker:
        return {"status": "error", "rows": 0, "detail": "a ticker is required", "raw": None}
    api_key = api_key or get_polygon_api_key()
    cb = _cb(progress)
    kw: dict = {}
    if from_date is not None:
        kw["from_date"] = from_date
    if to_date is not None:
        kw["to_date"] = to_date
    try:
        if force and data_type in ("price", "options") and ticker:
            _force_reset(data_type, ticker)
        if data_type == "eps_estimates":
            key = av_key or os.environ.get("ALPHA_VANTAGE_API_KEY", "") or os.environ.get("AV_API_KEY", "")
            if not key:
                return {"status": "error", "rows": 0, "detail": "an Alpha Vantage key is required "
                        "(ALPHA_VANTAGE_API_KEY in .env)", "raw": None}
            r = S.sync_eps_estimates(ticker, key, progress_cb=cb)
            r = dict(r or {}, rows=(r or {}).get("updated", 0) + (r or {}).get("inserted", 0))
        elif data_type == "price":
            r = S.sync_price_bars(ticker, api_key, progress_cb=cb, **kw)
        elif data_type == "options":
            r = S.sync_option_snapshots(ticker, api_key, progress_cb=cb, **kw)
        elif data_type == "news":
            r = S.sync_news(ticker, api_key, progress_cb=cb, **kw)
        elif data_type == "divs":
            r = S.sync_dividends(ticker, api_key, progress_cb=cb, **kw)
        elif data_type == "earnings":
            r = S.sync_earnings(ticker, api_key, progress_cb=cb, **kw)
        elif data_type == "minute_bars":
            r = S.sync_minute_bars(ticker, api_key, progress_cb=cb, **kw)
        elif data_type == "option_minute_bars":
            r = S.sync_option_minute_bars(ticker, api_key, progress_cb=cb, **kw)
        elif data_type == "treasury":
            r = S.sync_treasury_bars(progress_cb=cb, **kw)
        elif data_type == "vix":
            r = S.sync_vix_bars(progress_cb=cb, **kw)
        elif data_type == "macro":
            r = S.sync_macro_bars(progress_cb=cb, **kw)
        elif data_type == "cpi":
            r = S.sync_cpi(progress_cb=cb, **kw)
        elif data_type == "fomc":
            r = S.sync_fomc_calendar(progress_cb=cb)
        else:                                               # event_calendar
            r = S.sync_event_calendar(progress_cb=cb, **kw)
    except Exception as exc:  # noqa: BLE001 — a failed sync is a result, not a crash
        logger.warning("sync %s %s failed: %s", data_type, ticker or "", exc)
        return {"status": "error", "rows": 0, "detail": f"{type(exc).__name__}: {exc}", "raw": None}
    r = dict(r or {})
    st = str(r.get("status", "ok"))
    status = ("up_to_date" if st == "up_to_date" else "no_data" if st in ("no_data", "no_calendar")
              else "error" if st == "error" else "ok")
    return {"status": status, "rows": int(r.get("rows", 0) or 0),
            "detail": str(r.get("detail") or r.get("message") or r.get("error") or ""), "raw": r}


def describe(result: dict) -> str:
    """The Data Manager's one-line status for a result."""
    st = result.get("status")
    if st == "up_to_date":
        return "Already up to date"
    if st == "no_data":
        return f"No data: {result.get('detail', '')}"
    if st == "error":
        return f"Error: {result.get('detail', '')}"
    return f"Done — {int(result.get('rows', 0)):,} rows"
