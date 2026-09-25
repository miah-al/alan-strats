"""
api/services/gex_recorder.py — record live dealer GEX so a history accumulates (``app.GexHistory``).

There is no stored option history with open interest for most tickers (IBIT, ETHA, QQQ, NDX, SPX have
none; SPY's stored snapshots are monthly expiries without OI), so the service records its own:

  eod        once per trading day after 16:10 ET, for every ticker (the regime "at the prior close" for the
             next session). If the service was not running then, it is recorded at the next start before the
             next session's 09:30 open — valued at the session's stored close — and reads ``late``. Only the
             last completed session can be recorded that way: a day the service missed entirely stays missing.
  session    once per trading day at the strategies' decision time, 10:55 ET (due until 11:30), for NDX, SPX
             and SPY — whether or not the broker is streaming
  intraday   every 30 minutes from 10:00 to 15:30 ET — only while the broker's streamer is connected
             (streamed OI and greeks cost no request budget; the fallbacks would), unless forced on

``late`` (derived from when the row was written, so it holds for every row ever recorded): an eod row written
after 16:40 ET on its session day, a session row written after 11:05 ET, an intraday row written after its
30 minutes.

Each row is ``/api/market/gex/{ticker}?source=hub``'s figures: the same live chain for every ticker (the
first week's expiries and Fridays to 60 days, strikes ±1.5% dense and sampled to ±8%). A slot already
recorded (by this or another service process) is skipped before any request is made; the table's
unique key stops a duplicate. A slot that fails is retried at most three times, 15 minutes apart.

Environment: ``ALAN_TRADER_GEX_RECORD`` (``1``; ``0`` off — the test suite's default),
``ALAN_TRADER_GEX_TICKERS`` (``IBIT,ETHA,SPY,QQQ,NDX,SPX``), ``ALAN_TRADER_GEX_SESSION_TICKERS``
(``NDX,SPX,SPY``), ``ALAN_TRADER_GEX_INTRADAY`` (``auto`` = only while streaming | ``on`` | ``off``).
"""
from __future__ import annotations

import datetime as _dt
import logging
import os
import threading
import time
from typing import Optional

import pandas as pd

from api.services.db import require_db

logger = logging.getLogger("alan_trader.api.gex_recorder")

NY = "America/New_York"
DEFAULT_TICKERS = "IBIT,ETHA,SPY,QQQ,NDX,SPX"
DEFAULT_SESSION_TICKERS = "NDX,SPX,SPY"
OPEN = _dt.time(9, 30)
EOD_AFTER = _dt.time(16, 10)
EOD_ON_TIME_UNTIL = _dt.time(16, 40)
SESSION_AT = _dt.time(10, 55)
SESSION_ON_TIME_UNTIL = _dt.time(11, 5)
SESSION_UNTIL = _dt.time(11, 30)
FIRST_SLOT, LAST_SLOT = _dt.time(10, 0), _dt.time(15, 30)
RETRY_S = 900.0
MAX_TRIES = 3
KINDS = ("eod", "session", "intraday")


def enabled() -> bool:
    return os.environ.get("ALAN_TRADER_GEX_RECORD", "1").strip().lower() not in ("0", "off", "false", "no")


def _list(name: str, default: str) -> list[str]:
    return [t.strip().upper() for t in os.environ.get(name, default).split(",") if t.strip()]


def tickers() -> list[str]:
    """Every ticker's end-of-day row (and intraday rows): ``ALAN_TRADER_GEX_TICKERS`` plus the session tickers."""
    out = _list("ALAN_TRADER_GEX_TICKERS", DEFAULT_TICKERS)
    return out + [t for t in session_tickers() if t not in out]


def session_tickers() -> list[str]:
    return _list("ALAN_TRADER_GEX_SESSION_TICKERS", DEFAULT_SESSION_TICKERS)


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


def previous_trading_day(d: _dt.date) -> _dt.date:
    p = d - _dt.timedelta(days=1)
    while not trading_day(p):
        p -= _dt.timedelta(days=1)
    return p


def eod_session(now: pd.Timestamp) -> Optional[_dt.date]:
    """The session whose end-of-day row can be recorded at ``now`` (ET): today's after 16:10; before the next
    session opens (overnight, a weekend, a holiday), the last completed one's; none while a session is open."""
    d, t = now.date(), now.time()
    if trading_day(d):
        if t >= EOD_AFTER:
            return d
        if t >= OPEN:
            return None
    return previous_trading_day(d)


def due_slots(now: pd.Timestamp, streaming: bool, mode: str = "auto") -> list[tuple[str, _dt.datetime]]:
    """[(kind, slot as naive ET)] that are due at ``now`` (ET): the current 30-minute intraday slot, the
    session's decision-time slot, and the end-of-day slot that can still be recorded."""
    d, t = now.date(), now.time()
    out = []
    if trading_day(d):
        if mode == "on" or (mode == "auto" and streaming):
            if FIRST_SLOT <= t < _dt.time(16, 0):
                minute = 0 if t.minute < 30 else 30
                slot = _dt.datetime.combine(d, _dt.time(t.hour, minute))
                if slot.time() <= LAST_SLOT:
                    out.append(("intraday", slot))
        if SESSION_AT <= t < SESSION_UNTIL:
            out.append(("session", _dt.datetime.combine(d, SESSION_AT)))
    p = eod_session(now)
    if p is not None:
        out.append(("eod", _dt.datetime.combine(p, _dt.time(16, 0))))
    return out


def is_late(kind: str, slot: _dt.datetime, at: _dt.datetime) -> bool:
    """Whether a row for ``slot`` written at ``at`` (both naive ET) is late."""
    if kind == "eod":
        return at > _dt.datetime.combine(slot.date(), EOD_ON_TIME_UNTIL)
    if kind == "session":
        return at > _dt.datetime.combine(slot.date(), SESSION_ON_TIME_UNTIL)
    return at >= slot + _dt.timedelta(minutes=30)


def et_naive(ts_utc) -> Optional[_dt.datetime]:
    """A naive UTC timestamp (the table's RecordedAt) as naive ET."""
    if ts_utc is None or pd.isna(ts_utc):
        return None
    return pd.Timestamp(ts_utc).tz_localize("UTC").tz_convert(NY).tz_localize(None).to_pydatetime()


def session_close(ticker: str, day: _dt.date, hub=None) -> Optional[float]:
    """``ticker``'s close on ``day``: the stored daily bar (topped up first when missing), else, for an index —
    which does not trade outside the session — its last level. None when neither is there."""
    from api.marketdata import symbols as SYM
    und = SYM.underlying_and_root(ticker)[0]
    try:
        from api.services.bars_topup import top_up
        top_up(und, day)
    except Exception as exc:  # noqa: BLE001
        logger.info("daily bars for %s not topped up: %s", und, exc)
    try:
        from db.client import get_price_bars
        df = get_price_bars(require_db(), und, day, day)
        if df is not None and not df.empty and pd.notna(df["close"].iloc[-1]):
            return float(df["close"].iloc[-1])
    except Exception as exc:  # noqa: BLE001
        logger.info("stored close for %s on %s unavailable: %s", und, day, exc)
    if SYM.is_index(und):
        from api.services import market as M
        return M.gex_spot(und, hub)
    return None


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


ROW_COLS = ["Ticker", "Kind", "SlotTs", "TradeDate", "Spot", "NetGex", "CallGex", "PutGex", "Flip", "CallWall",
            "PutWall", "DistToFlipPct", "Regime", "MaxPain", "Contracts", "Source", "RecordedAt"]


def rows(ticker: str, kind: str, from_date: _dt.date, to_date: Optional[_dt.date] = None) -> pd.DataFrame:
    """The recorded rows of one ticker and kind with TradeDate in [from_date, to_date], oldest first, plus
    ``Late`` (see is_late)."""
    from sqlalchemy import text
    from api.services import appdb
    if not appdb.exists("GexHistory"):
        return pd.DataFrame(columns=ROW_COLS + ["Late"])
    sql = (f"SELECT {', '.join(ROW_COLS)} FROM app.GexHistory WHERE Ticker = :t AND Kind = :k AND TradeDate >= :f"
           + (" AND TradeDate <= :to" if to_date else "") + " ORDER BY SlotTs")
    with require_db().connect() as c:
        got = c.execute(text(sql), {"t": ticker, "k": kind, "f": from_date, "to": to_date}).fetchall()
    df = pd.DataFrame(got, columns=ROW_COLS)
    df["Late"] = [bool(at is not None and is_late(kind, pd.Timestamp(s).to_pydatetime(), at))
                  for s, at in zip(df["SlotTs"], (et_naive(x) for x in df["RecordedAt"]))]
    return df


def history_rows(ticker: str, kind: str, since: _dt.date) -> pd.DataFrame:
    return rows(ticker, kind, since)


def table_counts() -> dict:
    """{"rows", "by_kind": {kind: rows}, "by_ticker": {ticker: rows}, "last_recorded": UTC iso} (read only)."""
    from sqlalchemy import text
    from api.services import appdb
    if not appdb.exists("GexHistory"):
        return {"rows": 0, "by_kind": {}, "by_ticker": {}, "last_recorded": None, "last_trade_date": None}
    with require_db().connect() as c:
        kinds = c.execute(text("SELECT Kind, COUNT(*) FROM app.GexHistory GROUP BY Kind")).fetchall()
        tick = c.execute(text("SELECT Ticker, COUNT(*) FROM app.GexHistory GROUP BY Ticker")).fetchall()
        last = c.execute(text("SELECT MAX(RecordedAt), MAX(TradeDate) FROM app.GexHistory")).fetchone()
    from api.services.orders import _iso_utc
    return {"rows": int(sum(n for _, n in kinds)), "by_kind": {k: int(n) for k, n in kinds},
            "by_ticker": {t: int(n) for t, n in tick}, "last_recorded": _iso_utc(last[0]) if last else None,
            "last_trade_date": last[1] if last else None}


class GexRecorder:
    def __init__(self, hub):
        self.hub = hub
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._have: set[tuple[str, str, _dt.datetime]] = set()
        self._failed: dict[tuple[str, str, _dt.datetime], tuple[int, float, str]] = {}
        self.last: dict = {}
        self.recorded = 0
        self.ticks = 0
        self.last_tick: Optional[str] = None
        self.started: Optional[str] = None

    def start(self) -> None:
        if not enabled():
            logger.info("GEX recorder off (ALAN_TRADER_GEX_RECORD)")
            return
        self.started = pd.Timestamp.now(tz=NY).isoformat(timespec="seconds")
        self._thread = threading.Thread(target=self._run, name="gex-recorder", daemon=True)
        self._thread.start()
        logger.info("GEX recorder on: end of day %s; decision time %s %s; intraday %s",
                    ",".join(tickers()), SESSION_AT.strftime("%H:%M"), ",".join(session_tickers()), intraday_mode())

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
        self.ticks += 1
        self.last_tick = now.isoformat(timespec="seconds")
        n = 0
        for kind, slot in due_slots(now, self._streaming(), intraday_mode()):
            for t in (session_tickers() if kind == "session" else tickers()):
                if self._stop.is_set():
                    return n
                key = (t, kind, slot)
                if key in self._have:
                    continue
                failed = self._failed.get(key)
                if failed is not None and (failed[0] >= MAX_TRIES or time.monotonic() < failed[1]):
                    continue
                try:
                    if recorded(t, kind, slot):
                        self._have.add(key)
                        continue
                    late = is_late(kind, slot, now.tz_convert(NY).tz_localize(None).to_pydatetime())
                    spot = None
                    if kind == "eod" and late:
                        spot = session_close(t, slot.date(), self.hub)
                        if spot is None:
                            raise LookupError(f"no close for {t} on {slot.date()} (nothing stored), so a late "
                                              f"end-of-day row cannot be valued at it")
                    with patience(300.0):
                        g = M.gex(t, "hub", hub=self.hub, spot=spot)
                    if spot is not None:
                        g = {**g, "source": f"{g.get('source') or ''} spot=close"}
                    if save(t, kind, slot, g):
                        n += 1
                        self.recorded += 1
                        self.last[t] = {"kind": kind, "slot": slot.isoformat(), "net_gex": g.get("net_gex"),
                                        "regime": g.get("regime"), "late": late}
                        logger.info("GEX %s %s %s recorded%s: %s", t, kind, slot, " (late)" if late else "",
                                    g.get("regime"))
                    self._have.add(key)
                    self._failed.pop(key, None)
                except Exception as exc:  # noqa: BLE001 — a missed slot is logged and retried a few times
                    tries = (failed[0] if failed else 0) + 1
                    self._failed[key] = (tries, time.monotonic() + RETRY_S, f"{type(exc).__name__}: {exc}"[:200])
                    logger.info("GEX %s %s %s not recorded (try %d of %d): %s", t, kind, slot, tries, MAX_TRIES, exc)
        return n

    def status(self) -> dict:
        now = pd.Timestamp.now(tz=NY)
        return {"enabled": enabled(), "running": bool(self._thread is not None and self._thread.is_alive()),
                "started": self.started, "ticks": self.ticks, "last_tick": self.last_tick,
                "recorded_by_this_process": self.recorded, "last": self.last,
                "failed": [{"ticker": t, "kind": k, "slot": s.isoformat(), "tries": f[0], "error": f[2]}
                           for (t, k, s), f in self._failed.items()],
                "streaming": self._streaming(), "intraday_mode": intraday_mode(),
                "tickers": tickers(), "session_tickers": session_tickers(),
                "due_now": [{"kind": k, "slot": s.isoformat()} for k, s in due_slots(now, self._streaming(),
                                                                                  intraday_mode())]}

    def _run(self) -> None:
        while not self._stop.wait(60.0):
            try:
                self.tick()
            except Exception:
                logger.exception("GEX recorder tick failed")
