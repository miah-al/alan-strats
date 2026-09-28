"""
api/services/alerts.py — price / change / IV alerts evaluated on the market-data hub's quotes.

An alert is ``{"symbol", "field": last|change_pct|iv, "op": ">"|"<"|"crosses_above"|"crosses_below",
"value", "note", "once", "active"}``, kept in ``app.Alert``. The engine watches every active alert's
symbol on the hub (one upstream subscription however many alerts share it) and evaluates each quote
it pushes:

  ``>`` / ``<``                   fires when the condition becomes true (a level alert fires on the
                                  transition, not on every quote while it stays true)
  ``crosses_above`` / ``_below``  fires when the value moves from one side of ``value`` to the other;
                                  the first value seen only sets the baseline

``last`` is the last trade (the mid when there is none); ``change_pct`` the change on the previous
close in percent; ``iv`` an option's implied volatility (fraction) from its quote, or for a stock /
index its ATM IV from the IV metrics (refreshed every 5 minutes, through the request gate). A
``once`` alert deactivates when it fires. A firing is recorded (TriggeredAt, LastValue, the count)
and pushed on ``/api/events`` as ``{"type": "alert", "alert": {...}, "value", "time"}``.
"""
from __future__ import annotations

import datetime as _dt
import logging
import queue
import threading
import time
from typing import Callable, Optional

from api.marketdata import symbols as SYM
from api.serialize import to_jsonable
from api.services.db import require_db

logger = logging.getLogger("alan_trader.api.alerts")

FIELDS = ("last", "change_pct", "iv")
OPS = (">", "<", "crosses_above", "crosses_below")
IV_REFRESH_S = 300.0
_COLS = ["AlertId", "Symbol", "Field", "Op", "Value", "Note", "OnceOnly", "Active", "CreatedAt", "TriggeredAt",
         "LastValue", "TriggerCount"]


class AlertError(ValueError):
    pass


class UnknownAlert(KeyError):
    pass


def _row(r) -> dict:
    from api.services.orders import _iso_utc
    d = dict(zip(_COLS, r))
    return {"id": int(d["AlertId"]), "symbol": d["Symbol"], "field": d["Field"], "op": d["Op"], "value": float(d["Value"]),
            "note": d["Note"] or "", "once": bool(d["OnceOnly"]), "active": bool(d["Active"]),
            "created": _iso_utc(d["CreatedAt"]), "triggered": _iso_utc(d["TriggeredAt"]),
            "last_value": d["LastValue"], "trigger_count": int(d["TriggerCount"] or 0)}


def validate(body: dict) -> dict:
    if not isinstance(body, dict):
        raise AlertError("an alert is a JSON object")
    try:
        sym = SYM.normalize(body.get("symbol") or "")
    except ValueError as exc:
        raise AlertError(f"symbol: {exc}")
    field = str(body.get("field") or "last").strip().lower()
    if field not in FIELDS:
        raise AlertError(f"field must be one of {list(FIELDS)}")
    op = str(body.get("op") or "").strip().lower()
    if op not in OPS:
        raise AlertError(f"op must be one of {list(OPS)}")
    try:
        value = float(body.get("value"))
    except (TypeError, ValueError):
        raise AlertError("value must be a number")
    if value != value or value in (float("inf"), float("-inf")):
        raise AlertError("value must be finite")
    return {"symbol": sym, "field": field, "op": op, "value": value, "note": str(body.get("note") or "")[:400],
            "once": bool(body.get("once", True)), "active": bool(body.get("active", True))}


class AlertEngine:
    def __init__(self, hub, publish: Optional[Callable[[dict], None]] = None):
        self.hub = hub
        self.publish = publish
        self._lock = threading.RLock()
        self._alerts: dict[int, dict] = {}              # active alerts by id
        self._prev: dict[int, Optional[float]] = {}     # last value seen per alert
        self._state: dict[int, Optional[bool]] = {}     # a level alert's last condition
        self._iv: dict[str, tuple[float, Optional[float]]] = {}
        self._q: "queue.Queue[tuple[str, dict]]" = queue.Queue(maxsize=10000)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.fired = 0

    # ── lifecycle ─────────────────────────────────────────────────────────────
    def start(self) -> None:
        if self.hub is not None:
            self.hub.listeners.append(self.on_quote)
        self._thread = threading.Thread(target=self._run, name="alerts", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self.hub is not None:
            try:
                self.hub.listeners.remove(self.on_quote)
            except ValueError:
                pass

    def _load(self) -> None:
        from sqlalchemy import text
        try:
            with require_db().connect() as c:
                if c.execute(text("SELECT OBJECT_ID('app.Alert', 'U')")).scalar() is None:
                    return
                rows = c.execute(text(f"SELECT {', '.join(_COLS)} FROM app.Alert WHERE Active = 1")).fetchall()
        except Exception as exc:
            logger.warning("alerts not loaded: %s", exc)
            return
        for r in rows:
            self._track(_row(r))

    def _track(self, a: dict) -> None:
        with self._lock:
            self._alerts[a["id"]] = a
            self._prev.pop(a["id"], None)
            self._state.pop(a["id"], None)
        if self.hub is not None:
            self.hub.watch(f"alert:{a['id']}", [a["symbol"]])

    def _untrack(self, alert_id: int) -> None:
        with self._lock:
            self._alerts.pop(alert_id, None)
            self._prev.pop(alert_id, None)
            self._state.pop(alert_id, None)
        if self.hub is not None:
            self.hub.unwatch_all(f"alert:{alert_id}")

    # ── CRUD ──────────────────────────────────────────────────────────────────
    def list(self) -> list[dict]:
        from sqlalchemy import text
        from api.services import appdb
        if not appdb.exists("Alert"):
            return []
        with require_db().connect() as c:
            rows = c.execute(text(f"SELECT {', '.join(_COLS)} FROM app.Alert ORDER BY AlertId DESC")).fetchall()
        return [_row(r) for r in rows]

    def get(self, alert_id: int) -> Optional[dict]:
        from sqlalchemy import text
        from api.services import appdb
        if not appdb.exists("Alert"):
            return None
        with require_db().connect() as c:
            r = c.execute(text(f"SELECT {', '.join(_COLS)} FROM app.Alert WHERE AlertId = :id"), {"id": int(alert_id)}).fetchone()
        return _row(r) if r is not None else None

    def create(self, body: dict) -> dict:
        from sqlalchemy import text
        from api.services import appdb
        a = validate(body)
        appdb.ensure("Alert")
        with require_db().begin() as c:
            r = c.execute(text("INSERT INTO app.Alert (Symbol, Field, Op, Value, Note, OnceOnly, Active) "
                               "OUTPUT INSERTED.AlertId VALUES (:s, :f, :o, :v, :n, :once, :act)"),
                          {"s": a["symbol"], "f": a["field"], "o": a["op"], "v": a["value"], "n": a["note"],
                           "once": 1 if a["once"] else 0, "act": 1 if a["active"] else 0}).fetchone()
        created = self.get(int(r[0]))
        if created["active"]:
            self._track(created)
        return created

    def delete(self, alert_id: int) -> None:
        from sqlalchemy import text
        from api.services import appdb
        if not appdb.exists("Alert"):
            raise UnknownAlert(alert_id)
        with require_db().begin() as c:
            if c.execute(text("DELETE FROM app.Alert WHERE AlertId = :id"), {"id": int(alert_id)}).rowcount == 0:
                raise UnknownAlert(alert_id)
        self._untrack(int(alert_id))

    def active_count(self) -> int:
        with self._lock:
            return len(self._alerts)

    # ── evaluation ────────────────────────────────────────────────────────────
    def on_quote(self, symbol: str, msg: dict) -> None:
        """Hub listener (event loop): hand the quote to the worker; nothing slow here."""
        with self._lock:
            if not any(a["symbol"] == symbol for a in self._alerts.values()):
                return
        try:
            self._q.put_nowait((symbol, msg))
        except queue.Full:
            pass

    def _value(self, a: dict, msg: dict) -> Optional[float]:
        f = a["field"]
        if f == "last":
            v = msg.get("last") if msg.get("last") is not None else msg.get("mid")
        elif f == "change_pct":
            v = msg.get("change_pct")
        else:
            v = msg.get("iv")
            if v is None and not SYM.is_option(a["symbol"]):
                v = self._underlying_iv(a["symbol"])
        return float(v) if v is not None else None

    def _underlying_iv(self, symbol: str) -> Optional[float]:
        hit = self._iv.get(symbol)
        if hit is not None and time.monotonic() - hit[0] < IV_REFRESH_S:
            return hit[1]
        val = None
        try:
            from api.marketdata.cache import DAILY_TTL, cached
            from api.services import market as M
            m = cached(("iv", symbol), DAILY_TTL, lambda: M.iv(symbol), cache_errors=(M.MissingData,))
            val = m.get("atm_iv")
            val = float(val) if val is not None else None
        except Exception as exc:
            logger.info("IV for alert on %s unavailable: %s", symbol, exc)
        self._iv[symbol] = (time.monotonic(), val)
        return val

    @staticmethod
    def check(op: str, threshold: float, prev: Optional[float], cur: float, was: Optional[bool]) -> tuple[bool, Optional[bool]]:
        """(fires, new level state) — the rule, testable on its own."""
        if op == ">":
            now = cur > threshold
            return (now and was is not True), now
        if op == "<":
            now = cur < threshold
            return (now and was is not True), now
        if prev is None:
            return False, None
        if op == "crosses_above":
            return (prev <= threshold < cur), None
        return (prev >= threshold > cur), None

    def evaluate(self, symbol: str, msg: dict) -> list[dict]:
        fired = []
        with self._lock:
            alerts = [a for a in self._alerts.values() if a["symbol"] == symbol]
        for a in alerts:
            cur = self._value(a, msg)
            if cur is None:
                continue
            with self._lock:
                prev, was = self._prev.get(a["id"]), self._state.get(a["id"])
                fires, state = self.check(a["op"], a["value"], prev, cur, was)
                self._prev[a["id"]] = cur
                self._state[a["id"]] = state
            if fires:
                fired.append(self._fire(a, cur))
        return fired

    def _fire(self, a: dict, value: float) -> dict:
        from sqlalchemy import text
        now = _dt.datetime.now().astimezone()
        try:
            with require_db().begin() as c:
                c.execute(text("UPDATE app.Alert SET TriggeredAt = SYSUTCDATETIME(), LastValue = :v, "
                               "TriggerCount = TriggerCount + 1, Active = CASE WHEN OnceOnly = 1 THEN 0 ELSE Active END "
                               "WHERE AlertId = :id"), {"v": value, "id": a["id"]})
            stored = self.get(a["id"]) or a
        except Exception as exc:
            logger.warning("alert %s fired but was not recorded: %s", a["id"], exc)
            stored = dict(a, triggered=now.isoformat(timespec="seconds"), last_value=value)
        if a["once"]:
            self._untrack(a["id"])
        self.fired += 1
        logger.info("alert %s: %s %s %s %s — now %s", a["id"], a["symbol"], a["field"], a["op"], a["value"], value)
        msg = {"type": "alert", "alert": to_jsonable(stored), "value": value,
               "time": now.isoformat(timespec="seconds")}
        if self.publish is not None:
            try:
                self.publish(msg)
            except Exception:
                logger.debug("alert publish failed", exc_info=True)
        return msg

    def _run(self) -> None:
        self._load()
        while not self._stop.is_set():
            try:
                symbol, msg = self._q.get(timeout=1.0)
            except queue.Empty:
                continue
            try:
                self.evaluate(symbol, msg)
            except Exception:
                logger.exception("alert evaluation failed for %s", symbol)
