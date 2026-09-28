"""
api/services/bars_topup.py — keep stored daily bars current.

``top_up(ticker, until)``: when mkt.PriceBar's last bar for ``ticker`` is older than the last completed trading day
(or there are none), pull the missing days with the platform's own daily sync (``db.sync_jobs`` "price": yfinance,
through the service's request gate) and store them. A ticker is tried at most once an hour whatever the outcome, so
an unknown symbol or a vendor outage never turns into a request loop.

``NightlyBars``: after 16:30 ET on each trading day, one ``sync`` job (visible in /api/jobs) tops up the crypto ETPs
(``ALAN_TRADER_DAILY_SYNC``, default IBIT, ETHA, FBTC, GBTC, ETHE, BITO) and every stock / ETF / index in the
watchlists. Tickers already current cost nothing. ``ALAN_TRADER_NIGHTLY_SYNC=0`` turns it off (the test suite does).
"""
from __future__ import annotations

import datetime as _dt
import logging
import os
import threading
import time
from typing import Optional

import pandas as pd

logger = logging.getLogger("alan_trader.api.bars_topup")

NY = "America/New_York"
RETRY_S = 3600.0
NEW_TICKER_DAYS = 400
DEFAULT_NIGHTLY = "IBIT,ETHA,FBTC,GBTC,ETHE,BITO"
NIGHTLY_AFTER = _dt.time(16, 30)
_TRIED: dict[str, float] = {}
_LOCK = threading.Lock()


def last_completed_session(now: Optional[pd.Timestamp] = None) -> _dt.date:
    """The last trading day whose daily bar is final (after 16:15 ET the day's own; weekends and exchange holidays
    skipped)."""
    from api.services.gex_recorder import trading_day
    now = now or pd.Timestamp.now(tz=NY)
    d = now.date()
    if not (trading_day(d) and now.time() >= _dt.time(16, 15)):
        d -= _dt.timedelta(days=1)
        while not trading_day(d):
            d -= _dt.timedelta(days=1)
    return d


def top_up(ticker: str, until: Optional[_dt.date] = None, force: bool = False) -> dict:
    """{"status": current | topped_up | skipped | failed, "rows", "last"}. Never raises."""
    from api.marketdata import symbols as SYM
    if not force and os.environ.get("ALAN_TRADER_BARS_TOPUP", "1").strip().lower() in ("0", "off", "false", "no"):
        return {"status": "skipped", "rows": 0, "detail": "top-ups off (ALAN_TRADER_BARS_TOPUP)"}
    from api.services.db import require_db
    try:
        sym = SYM.normalize(ticker)
    except ValueError:
        return {"status": "skipped", "rows": 0, "detail": "not a symbol"}
    if SYM.is_option(sym) or sym in ("VIX", "^VIX", "I:VIX"):
        return {"status": "skipped", "rows": 0, "detail": "not a daily-bar symbol"}
    need = last_completed_session()
    if until is not None:
        need = min(need, until)
    try:
        from db.client import get_price_coverage
        cov = get_price_coverage(require_db(), sym)
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed", "rows": 0, "detail": f"{type(exc).__name__}: {exc}"}
    last = cov[1] if cov else None
    if last is not None and last >= need:
        return {"status": "current", "rows": 0, "last": last}
    with _LOCK:
        tried = _TRIED.get(sym)
        if not force and tried is not None and time.monotonic() - tried < RETRY_S:
            return {"status": "skipped", "rows": 0, "last": last, "detail": "tried within the hour"}
        _TRIED[sym] = time.monotonic()
    from api.marketdata.limits import patience
    from db.sync_jobs import run_sync
    start = last if last is not None else need - _dt.timedelta(days=NEW_TICKER_DAYS)
    with patience(60.0):
        r = run_sync("price", sym, start, need)
    ok = r["status"] in ("ok", "up_to_date")
    logger.info("daily bars for %s %s: %s (%s rows since %s)", sym, "topped up" if ok else "not topped up",
                r["status"], r["rows"], start)
    return {"status": "topped_up" if ok and r["rows"] else ("current" if ok else "failed"), "rows": r["rows"],
            "last": last, "detail": r.get("detail") or ""}


def nightly_symbols() -> list[str]:
    from api.marketdata import symbols as SYM
    from api.services import watchlists as W
    out = [s.strip().upper() for s in os.environ.get("ALAN_TRADER_DAILY_SYNC", DEFAULT_NIGHTLY).split(",") if s.strip()]
    try:
        for w in W.list_all():
            out += [s for s in w["symbols"] if not SYM.is_option(s)]
    except Exception as exc:  # noqa: BLE001
        logger.info("watchlists unavailable for the nightly sync: %s", exc)
    seen, uniq = set(), []
    for s in out:
        if s not in seen:
            seen.add(s)
            uniq.append(s)
    return uniq


class NightlyBars:
    def __init__(self, jobs):
        self.jobs = jobs
        self._stop = threading.Event()
        self._done: Optional[_dt.date] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if os.environ.get("ALAN_TRADER_NIGHTLY_SYNC", "1").strip().lower() in ("0", "off", "false", "no"):
            logger.info("nightly daily-bars sync off (ALAN_TRADER_NIGHTLY_SYNC)")
            return
        self._thread = threading.Thread(target=self._run, name="nightly-bars", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def due(self, now: pd.Timestamp) -> bool:
        from api.services.gex_recorder import trading_day
        return trading_day(now.date()) and now.time() >= NIGHTLY_AFTER and self._done != now.date()

    def run_once(self) -> Optional[str]:
        syms = nightly_symbols()

        def job(ctx):
            out = []
            for i, s in enumerate(syms):
                ctx.progress(i / max(len(syms), 1), f"daily bars {s}")
                out.append({"ticker": s, **top_up(s, force=True)})
            return {"results": out, "topped_up": sum(1 for r in out if r["status"] == "topped_up"),
                    "failed": sum(1 for r in out if r["status"] == "failed")}

        j = self.jobs.submit("sync", f"Nightly daily bars ({len(syms)} symbols)", job,
                             params={"symbols": syms})
        return j.id

    def _run(self) -> None:
        while not self._stop.wait(300.0):
            now = pd.Timestamp.now(tz=NY)
            if self.due(now):
                self._done = now.date()
                try:
                    self.run_once()
                except Exception:
                    logger.exception("nightly daily-bars sync failed to start")
