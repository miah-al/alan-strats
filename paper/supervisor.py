"""
paper/supervisor.py — the supervisor's controls over a running strategy (from 2026-09-30: Claude supervises every
armed strategy, and may only take risk off).

Three controls per strategy, stored with the trader's limits (app.TradeLimit, scope = the strategy's slug; every
change in app.TradeLimitChange with who and why; api/services/limits.py lists them):

  sup_entries  1 = the rules open positions; 0 = no new entries today (a resting entry is cancelled)
  sup_adds     1 = the rules add to losers as they are written; 0 = no adds today
  sup_close    a request, not a state: each new value closes every open position at the next poll, at the
               strategy's forced-exit price; the rules carry on afterwards unless entries are off

A control counts only on the day it was set (its UpdatedAt, in New York time): each session starts with the rules
in charge. The paper runner (paper/runner.py) reads them every poll and hands them to the engine's optional hooks
``supervise(entries, adds, reason)`` and ``flatten(minute, S, quote_fn, reason)`` (strategy_api/live.py). An engine
without the hooks is left alone, and its runner says so once.
"""
from __future__ import annotations

import datetime as _dt
import logging
from dataclasses import dataclass
from typing import Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger("paper.supervisor")

SUP_ENTRIES = "sup_entries"
SUP_ADDS = "sup_adds"
SUP_CLOSE = "sup_close"
NAMES = (SUP_ENTRIES, SUP_ADDS, SUP_CLOSE)
ET = ZoneInfo("America/New_York")


def et_naive(at_utc: _dt.datetime) -> _dt.datetime:
    """A stored UpdatedAt (UTC, naive: SYSUTCDATETIME) as New York wall time, naive (the runner's clock)."""
    return at_utc.replace(tzinfo=_dt.timezone.utc).astimezone(ET).replace(tzinfo=None)


@dataclass(frozen=True)
class Controls:
    entries: bool = True
    adds: bool = True
    close_at: Optional[_dt.datetime] = None      # when the latest close request was made (ET, naive)
    reason: str = ""                              # the latest reason given for any control in force


def effective(rows: dict, day: _dt.date) -> Controls:
    """The controls in force on ``day`` from ``rows`` = {name: {"value", "at" (UTC naive), "reason"}}: a row set on
    another day counts as unset."""
    today = {n: r for n, r in (rows or {}).items() if n in NAMES and r.get("at") is not None and et_naive(r["at"]).date() == day}

    def on(name: str) -> bool:
        r = today.get(name)
        try:
            return True if r is None else float(r.get("value")) >= 0.5
        except (TypeError, ValueError):
            return True
    close = today.get(SUP_CLOSE)
    latest = max(today.values(), key=lambda r: r["at"], default=None)
    return Controls(entries=on(SUP_ENTRIES), adds=on(SUP_ADDS),
                    close_at=et_naive(close["at"]) if close is not None else None,
                    reason=str((latest or {}).get("reason") or ""))


def read_controls(engine, slug: str) -> dict:
    """{name: {"value", "at", "by", "reason"}} of ``slug``'s stored controls (app.TradeLimit, the reason from the latest
    app.TradeLimitChange row); {} when there is no database, no table or nothing stored."""
    if engine is None:
        return {}
    from sqlalchemy import text
    import json
    with engine.connect() as c:
        if c.execute(text("SELECT OBJECT_ID('app.TradeLimit', 'U')")).scalar() is None:
            return {}
        rows = c.execute(text("SELECT t.Name, t.ValueJson, t.UpdatedBy, t.UpdatedAt, "
                              "(SELECT TOP 1 ch.Reason FROM app.TradeLimitChange ch WHERE ch.Scope = t.Scope AND ch.Name = t.Name "
                              " ORDER BY ch.Id DESC) FROM app.TradeLimit t "
                              "WHERE t.Scope = :s AND t.Name IN ('sup_entries', 'sup_adds', 'sup_close')"), {"s": slug}).fetchall()
    out = {}
    for name, value, by, at, reason in rows:
        try:
            v = json.loads(value)
        except (TypeError, ValueError):
            v = value
        out[str(name)] = {"value": v, "by": by, "at": at, "reason": reason or ""}
    return out
