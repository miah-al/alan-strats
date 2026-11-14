"""
api/services/close_mark.py — the paper account's equity at each close, recorded from the live marks.

The equity history (``api/services/paper.equity``) is rebuilt from the ledger and each holding's DAILY CLOSE, and an
option's daily close is its last TRADE of the day: for a thin contract that can be hours old. On 2026-11-12 that put
the account's close $677 under what the live marks showed at the bell (six puts whose last trade came long before it),
so through the whole next session "Day P&L" (net liq now minus the last close) read $677 too high, and the account day
stop measured the day from the same wrong start.

So the service keeps its own record. On a trading day, from 16:00 to 16:20 New York time, ``CloseMark`` stores the
account's equity and cash as the summary shows them (open positions at their live marks), replacing the day's entry on
each tick: the entry that stays is the last one, taken after the day's settlements are booked. ``apply`` then puts a
recorded close in place of the rebuilt figure for its day and carries it over the non-trading days that follow, which
is where the app and the day stop read "the last close" from.

A recorded close is used only while the ledger still agrees with it: the cash it was taken with must equal the
ledger's cash through that day. A backfill or a restatement of that day, or of an earlier one, changes that cash, and
the rebuilt figure is used again. A day the service was not running at the close has no record and is rebuilt as before.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import threading
from pathlib import Path
from typing import Callable, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger("alan_trader.api.close_mark")

ET = ZoneInfo("America/New_York")
TICK_S = 30.0
WINDOW = (_dt.time(16, 0), _dt.time(16, 20))      # New York time, both minutes included
CASH_TOL = 0.005                                  # dollars: the ledger's cash must match the record's to the cent
FILE = "close_marks.json"


def is_trading_day(day: _dt.date) -> bool:
    """A weekday that is not an exchange holiday (the service's own calendar; weekdays alone if it cannot be read)."""
    if day.weekday() >= 5:
        return False
    try:
        from api.services.calendar_events import holidays
        return day not in holidays()
    except Exception:  # noqa: BLE001 — no calendar: every weekday
        return True


class CloseMarkStore:
    """``{account id: {day: {"equity", "cash", "at", "live_marks"}}}`` in one JSON file in the service's state folder."""

    def __init__(self, path: Optional[Path] = None):
        if path is None:
            from api.config import service_state_dir
            path = service_state_dir() / FILE
        self.path = Path(path)
        self._lock = threading.Lock()

    def _load(self) -> dict:
        try:
            doc = json.loads(self.path.read_text(encoding="utf-8"))
            return doc if isinstance(doc, dict) else {}
        except (OSError, ValueError):
            return {}

    def read(self, account: int) -> dict[_dt.date, dict]:
        out: dict[_dt.date, dict] = {}
        for day, rec in (self._load().get(str(account)) or {}).items():
            try:
                out[_dt.date.fromisoformat(day)] = {"equity": float(rec["equity"]), "cash": float(rec["cash"]),
                                                    "at": rec.get("at"), "live_marks": bool(rec.get("live_marks"))}
            except (AttributeError, KeyError, TypeError, ValueError):
                continue                           # a damaged entry is no record: that day is rebuilt
        return out

    def put(self, account: int, day: _dt.date, equity: float, cash: float, at: str, live_marks: bool) -> dict:
        rec = {"equity": round(float(equity), 2), "cash": round(float(cash), 2), "at": at, "live_marks": bool(live_marks)}
        with self._lock:
            doc = self._load()
            doc.setdefault(str(account), {})[day.isoformat()] = rec
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(self.path.name + ".tmp")
            tmp.write_text(json.dumps(doc, indent=1, sort_keys=True), encoding="utf-8")
            os.replace(tmp, self.path)             # a reader never sees half a file
        return rec


_STORE: Optional[CloseMarkStore] = None


def store() -> CloseMarkStore:
    global _STORE
    if _STORE is None:
        _STORE = CloseMarkStore()
    return _STORE


def apply(equity, cash, marks: dict, trading_day: Callable[[_dt.date], bool] = is_trading_day):
    """``equity`` (a daily pandas Series, one point per calendar day) with each recorded close in place of the rebuilt
    figure for its day, carried over the non-trading days after it. ``cash`` is the ledger's daily cash on the same
    days; a record whose cash differs from it is stale (the ledger was changed since) and is ignored, and a record
    stops being carried the day the cash moves. Returns ``(series, the days that used a record)``."""
    if equity is None or cash is None or not marks or len(equity) == 0:
        return equity, []
    out = equity.astype(float).copy()
    cash = cash.reindex(out.index).ffill()
    used: list[_dt.date] = []
    carried: Optional[dict] = None
    for ts in out.index:
        day = ts.date()
        c = cash.get(ts)
        ok = c is not None and c == c              # not missing, not NaN
        if trading_day(day):
            m = marks.get(day)
            carried = m if (m is not None and ok and abs(float(m["cash"]) - float(c)) <= CASH_TOL) else None
        elif carried is not None and not (ok and abs(float(carried["cash"]) - float(c)) <= CASH_TOL):
            carried = None                         # the ledger moved on a non-trading day: back to the rebuilt figure
        if carried is not None:
            out.loc[ts] = float(carried["equity"])
            used.append(day)
    return out, used


class CloseMark:
    """The job: record the account's equity at the close, from the summary's live marks."""

    def __init__(self, summary_fn: Callable[[], dict], account_fn: Callable[[], int],
                 store: Optional[CloseMarkStore] = None, clock: Optional[Callable[[], _dt.datetime]] = None,
                 tick_s: float = TICK_S, trading_day: Callable[[_dt.date], bool] = is_trading_day):
        self._summary_fn = summary_fn              # -> api.services.paper.summary(hub): {equity, cash, live_marks, ...}
        self._account_fn = account_fn              # -> the paper account's id
        self._store = store
        self._clock = clock or (lambda: _dt.datetime.now(ET).replace(tzinfo=None))
        self._tick_s = tick_s
        self._trading_day = trading_day
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.last: Optional[dict] = None           # the latest record written

    def tick(self) -> Optional[dict]:
        now = self._clock()
        if not (WINDOW[0] <= now.time().replace(second=0, microsecond=0) <= WINDOW[1]):
            return None
        if not self._trading_day(now.date()):
            return None
        s = self._summary_fn() or {}
        equity, cash = s.get("equity"), s.get("cash")
        if equity is None or cash is None:
            return None
        # With positions open, only live marks make a close worth keeping: a fallback price is what this replaces.
        if int(s.get("open_positions") or 0) > 0 and not s.get("live_marks"):
            return None
        rec = (self._store or store()).put(int(self._account_fn()), now.date(), float(equity), float(cash),
                                           at=now.isoformat(timespec="seconds"), live_marks=bool(s.get("live_marks")))
        self.last = {"day": now.date().isoformat(), **rec}
        return self.last

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="close-mark", daemon=True)
        self._thread.start()
        logger.info("close mark on (the account's equity is recorded %s-%s New York time on trading days)",
                    WINDOW[0].strftime("%H:%M"), WINDOW[1].strftime("%H:%M"))

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        logged: Optional[str] = None
        while not self._stop.wait(self._tick_s):
            try:
                rec = self.tick()
                if rec and rec["day"] != logged:
                    logged = rec["day"]
                    logger.info("close mark %s: equity %.2f, cash %.2f (the entry is replaced until %s)",
                                rec["day"], rec["equity"], rec["cash"], WINDOW[1].strftime("%H:%M"))
            except Exception:  # noqa: BLE001
                logger.exception("close mark: tick failed")
