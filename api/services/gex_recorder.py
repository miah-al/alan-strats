"""
api/services/gex_recorder.py — record live dealer GEX so a history accumulates (``app.GexHistory``).

There is no stored option history with open interest for most tickers (IBIT, ETHA, QQQ, NDX, SPX have
none; SPY's stored snapshots are monthly expiries without OI), so the service records its own:

  eod        once per trading day after 16:10 ET, for every ticker, from whatever the market-data hub can
             serve (the broker's stream, else yfinance / Polygon through the request gate)
  intraday   every 30 minutes from 10:00 to 15:30 ET — only while the broker's streamer is connected
             (streamed OI and greeks cost no request budget; the fallbacks would), unless forced on

Each row is ``/api/market/gex/{ticker}?source=hub``'s figures: the same live chain for every ticker (the
first week's expiries and Fridays to 60 days, strikes ±1.5% dense and sampled to ±8%). A slot already
recorded (by this or another service process) is skipped before any request is made; the table's
unique key stops a duplicate.

Environment: ``ALAN_TRADER_GEX_RECORD`` (``1``; ``0`` off — the test suite's default),
``ALAN_TRADER_GEX_TICKERS`` (``IBIT,ETHA,SPY,QQQ,NDX,SPX``), ``ALAN_TRADER_GEX_INTRADAY``
(``auto`` = only while streaming | ``on`` | ``off``).
"""
from __future__ import annotations

import datetime as _dt
import logging
import os
import threading
from typing import Optional

import pandas as pd

from api.services.db import require_db

logger = logging.getLogger("alan_trader.api.gex_recorder")

NY = "America/New_York"
DEFAULT_TICKERS = "IBIT,ETHA,SPY,QQQ,NDX,SPX"
EOD_AFTER = _dt.time(16, 10)
FIRST_SLOT, LAST_SLOT = _dt.time(10, 0), _dt.time(15, 30)


def enabled() -> bool:
    return os.environ.get("ALAN_TRADER_GEX_RECORD", "1").strip().lower() not in ("0", "off", "false", "no")


def tickers() -> list[str]:
    raw = os.environ.get("ALAN_TRADER_GEX_TICKERS", DEFAULT_TICKERS)
    return [t.strip().upper() for t in raw.split(",") if t.strip()]


def intraday_mode() -> str:
    m = os.environ.get("ALAN_TRADER_GEX_INTRADAY", "auto").strip().lower()
    return m if m in ("auto", "on", "off") else "auto"


def trading_day(d: _dt.date) -> bool:
    if d.weekday() >= 5:
        return False
    try:
        from api.services.calendar_events import holidays
        return d not in holidays()
    except Exception:
        return True


def due_slots(now: pd.Timestamp, streaming: bool, mode: str = "auto") -> list[tuple[str, _dt.datetime]]:
    """[(kind, slot start as naive ET)] that are due at ``now`` (ET): the current 30-minute intraday slot and,
    after the close, the day's EOD slot."""
    d = now.date()
    if not trading_day(d):
        return []
    out = []
    t = now.time()
    if mode == "on" or (mode == "auto" and streaming):
        if FIRST_SLOT <= t < _dt.time(16, 0):
            minute = 0 if t.minute < 30 else 30
            slot = _dt.datetime.combine(d, _dt.time(t.hour, minute))
            if slot.time() <= LAST_SLOT:
                out.append(("intraday", slot))
    if t >= EOD_AFTER:
        out.append(("eod", _dt.datetime.combine(d, _dt.time(16, 0))))
    return out


def recorded(ticker: str, kind: str, slot: _dt.datetime) -> bool:
    from sqlalchemy import text
    from api.services import appdb
    if not appdb.exists("GexHistory"):
        return False
    with require_db().connect() as c:
        return c.execute(text("SELECT 1 FROM app.GexHistory WHERE Ticker = :t AND Kind = :k AND SlotTs = :s"),
                         {"t": ticker, "k": kind, "s": slot}).fetchone() is not None


def save(ticker: str, kind: str, slot: _dt.datetime, g: dict) -> bool:
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError
    from api.services import appdb
    appdb.ensure("GexHistory")
    try:
        with require_db().begin() as c:
            c.execute(text("""
                INSERT INTO app.GexHistory (Ticker, Kind, SlotTs, TradeDate, Spot, NetGex, CallGex, PutGex, Flip,
                    CallWall, PutWall, DistToFlipPct, Regime, MaxPain, NetGex0Dte, Contracts, Source)
                VALUES (:t, :k, :s, :d, :spot, :net, :cg, :pg, :flip, :cw, :pw, :dist, :reg, :mp, :n0, :n, :src)"""),
                {"t": ticker, "k": kind, "s": slot, "d": slot.date(), "spot": g.get("spot"), "net": g.get("net_gex"),
                 "cg": g.get("call_gex"), "pg": g.get("put_gex"), "flip": g.get("flip"), "cw": g.get("call_wall"),
                 "pw": g.get("put_wall"), "dist": g.get("dist_to_flip_pct"), "reg": g.get("regime"),
                 "mp": g.get("max_pain"), "n0": g.get("net_gex_0dte"), "n": g.get("contracts"),
                 "src": str(g.get("source") or "")[:60]})
        return True
    except IntegrityError:
        return False


def history_rows(ticker: str, kind: str, since: _dt.date) -> pd.DataFrame:
    from sqlalchemy import text
    from api.services import appdb
    cols = ["SlotTs", "Spot", "NetGex", "CallGex", "PutGex", "Flip", "CallWall", "PutWall", "DistToFlipPct", "Regime",
            "MaxPain", "Contracts", "Source"]
    if not appdb.exists("GexHistory"):
        return pd.DataFrame(columns=cols)
    with require_db().connect() as c:
        rows = c.execute(text(f"SELECT {', '.join(cols)} FROM app.GexHistory WHERE Ticker = :t AND Kind = :k "
                              f"AND TradeDate >= :d ORDER BY SlotTs"), {"t": ticker, "k": kind, "d": since}).fetchall()
    return pd.DataFrame(rows, columns=cols)


class GexRecorder:
    def __init__(self, hub):
        self.hub = hub
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.last: dict = {}
        self.recorded = 0

    def start(self) -> None:
        if not enabled():
            logger.info("GEX recorder off (ALAN_TRADER_GEX_RECORD)")
            return
        self._thread = threading.Thread(target=self._run, name="gex-recorder", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _streaming(self) -> bool:
        p = getattr(self.hub, "by_name", {}).get("tastytrade") if self.hub is not None else None
        return bool(p is not None and getattr(p, "connected", False))

    def tick(self, now: Optional[pd.Timestamp] = None) -> int:
        """Record what is due now; returns rows written."""
        from api.marketdata.limits import patience
        from api.services import market as M
        now = now or pd.Timestamp.now(tz=NY)
        n = 0
        for kind, slot in due_slots(now, self._streaming(), intraday_mode()):
            for t in tickers():
                if self._stop.is_set():
                    return n
                try:
                    if recorded(t, kind, slot):
                        continue
                    with patience(300.0):
                        g = M.gex(t, "hub", hub=self.hub)
                    if save(t, kind, slot, g):
                        n += 1
                        self.recorded += 1
                        self.last[t] = {"kind": kind, "slot": slot.isoformat(), "net_gex": g.get("net_gex"),
                                        "regime": g.get("regime")}
                except Exception as exc:  # noqa: BLE001 — a missed slot is logged, the next one is tried
                    logger.info("GEX %s %s %s not recorded: %s", t, kind, slot, exc)
        return n

    def _run(self) -> None:
        while not self._stop.wait(60.0):
            try:
                self.tick()
            except Exception:
                logger.exception("GEX recorder tick failed")
