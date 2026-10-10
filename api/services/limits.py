"""
api/services/limits.py — the limits the trader sets, database driven (app.TradeLimit, every change in
app.TradeLimitChange: old value, new value, who, why).

Three kinds of scope:
  desk      Claude's desks (scripts/claude_desk.py): lots, risk per position, open positions, the day stop, the
            entry window, the flat time. The desk reads them (GET /api/limits/<scope>) before every order and on
            every guard poll, so a change applies at once.
  strategy  every armed strategy: those of its own parameters that act as limits (a daily loss cap, adds into a
            loser, stops, lots, the entry window), found by name among the strategy's parameter specs, so no
            strategy is named here. A runner reads its parameters when it starts: a change applies from its next
            session, the arm launcher passing the stored values as ``--param`` (api/services/arms.py).
  system    the broker's daily call cap (from the next runner launch) and the tournament's kill rule (a rule the
            trader reviews each evening; nothing enforces it automatically, and the row says so).

A limit's value is the stored one, else its default (a desk's catalogue below, a strategy's parameter default).
PUT validates the value against the limit's range (a time as HH:MM) and writes the change row in the same
transaction. Usage — today's P&L against a loss limit, open positions, the largest open risk, the broker calls
spent — comes from the paper book, with a status: ok | near (80%) | hit.

Stores: memory under ALAN_TRADER_ARMS=memory (the test suite), none when off, else the database.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import re
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger("alan_trader.api.limits")


class LimitError(ValueError):
    pass


def _lim(name, label, unit, default, lo, hi, applies, help_, kind="number"):
    return {"name": name, "label": label, "unit": unit, "default": default, "min": lo, "max": hi,
            "applies": applies, "help": help_, "kind": kind}


# Claude's desks: the rails each one enforces (scripts/claude_desk.py). Defaults are the values in force on 2026-09-29.
DESKS: dict[str, dict] = {
    "claude_discretionary": {"label": "Claude · NDX desk", "limits": [
        _lim("max_lots", "Lots per position", "lots", 2, 1, 10, "now", "The most contracts in one position."),
        _lim("max_risk", "Risk per position", "$", 2500, 100, 20000, "now", "The most a position may lose at expiry (its max loss)."),
        _lim("max_positions", "Open positions", "positions", 1, 1, 5, "now", "How many positions may be open at once."),
        _lim("max_trades", "Trades per day", "trades", 3, 1, 20, "now",
             "New positions opened per day (a trim or a close is not one); the desk refuses an open past it. Proposed at 3 "
             "on 2026-09-30 after nine trades in a range day cost more than they made."),
        _lim("premium_only", "Premium only", "0 / 1", 1, 0, 1, "now",
             "1 = the desk only sells premium (condors, credit spreads outside the day's range) and refuses a debit; 0 = any "
             "defined-risk structure. Agreed on 2026-10-01 after three sessions of 0DTE debit direction calls lost $1.6k "
             "(37% won)."),
        _lim("day_stop", "Day stop", "$", -2500, -20000, -100, "now", "At this day P&L (realised + open) everything is closed and the desk is done for the day."),
        _lim("entry_start", "First entry", "ET", "09:45", "09:30", "15:59", "now", "No new position before this time.", "time"),
        _lim("entry_end", "Last entry", "ET", "15:30", "09:31", "15:59", "now", "No new position after this time.", "time"),
        _lim("flat_at", "Flat by", "ET", "15:55", "09:31", "16:00", "now", "Anything still open is closed at this time.", "time"),
    ]},
    "claude_events": {"label": "Claude · news desk", "limits": [
        _lim("max_risk", "Risk per trade", "$", 1000, 100, 10000, "now", "The most a trade may lose at its stop (shares) or at expiry (a spread)."),
        _lim("max_notional", "Size per position", "$", 10000, 1000, 100000, "now", "The most money in one position (shares at cost)."),
        _lim("max_positions", "Open positions", "positions", 2, 1, 5, "now", "How many event positions may be open at once."),
        _lim("day_stop", "Day stop", "$", -1500, -20000, -100, "now", "At this day P&L the desk stops opening trades."),
        _lim("entry_start", "First entry", "ET", "09:35", "09:30", "15:59", "now", "No new position before this time.", "time"),
        _lim("entry_end", "Last entry", "ET", "15:50", "09:31", "15:59", "now", "No new position after this time.", "time"),
    ]},
}

SYSTEM_SCOPE = "system"

# The supervisor's controls, on every strategy scope (paper/supervisor.py; from 2026-09-30 Claude supervises the armed
# strategies and may only take risk off). The runner reads them every poll; each counts only on the day it was set.
SUPERVISOR: list[dict] = [
    _lim("sup_entries", "Supervisor: new entries", "on/off", 1, 0, 1, "now",
         "1 = the rules open positions; 0 = no new entries today (a resting entry is cancelled). Today only."),
    _lim("sup_adds", "Supervisor: adds", "on/off", 1, 0, 1, "now",
         "1 = the rules add to a loser as written; 0 = no adds today. Today only."),
    _lim("sup_close", "Supervisor: close now", "request", 0, 0, 9_999_999_999, "now",
         "Each new value closes every open position at the next poll, at the strategy's forced-exit price; the rules "
         "carry on afterwards unless entries are off."),
]
_SUP_NAMES = frozenset(l["name"] for l in SUPERVISOR)


def _sup_today(st: Optional[dict]) -> bool:
    """Whether a stored supervisor control was set today (New York): one set on an earlier day is not in force."""
    at = (st or {}).get("updated_at")
    if not isinstance(at, _dt.datetime):
        return False
    from paper.supervisor import et_naive
    return et_naive(at).date() == _dt.datetime.now(tz=_dt.timezone.utc).astimezone(_ET()).date()


def _ET():
    from zoneinfo import ZoneInfo
    return ZoneInfo("America/New_York")


def _in_force(scope: str, name: str, stored: dict) -> Optional[dict]:
    """The stored row of (scope, name) when it is in force: always for a limit, only today's for a supervisor control."""
    st = stored.get((scope, name))
    if st is not None and name in _SUP_NAMES and not _sup_today(st):
        return None
    return st


def _system_catalogue() -> list[dict]:
    try:
        from paper.providers import DEFAULT_BROKER_DAY_CAP as cap
    except Exception:
        cap = 8000
    return [
        _lim("broker_day_cap", "Broker calls per day", "calls", cap, 1000, 50000, "next_launch",
             "The day's cap on broker REST calls across every runner; runners launched after a change use it."),
        _lim("kill_after_sessions", "Kill rule: sessions", "sessions", 20, 5, 200, "review",
             "After this many live sessions a strategy with negative P&L per day is dropped (reviewed, not automatic)."),
        _lim("kill_day_loss_per_lot", "Kill rule: worst day per lot", "$", 3000, 500, 20000, "review",
             "A day worse than this per lot drops a strategy at once (reviewed, not automatic)."),
        _lim("account_day_stop", "Account day stop ($, 0 = none)", "$", 1000, 0, 50000, "now",
             "When the whole paper account is this far down on the day (its equity now against its equity at the last "
             "close, every strategy and desk), every armed strategy's new entries go off for the rest of the day (the "
             "supervisor's control, set by the service); open positions keep their own exits (api/services/day_stop.py)."),
    ]


# A strategy parameter is a limit when its key says so: a cap, a max, a stop, a loss, lots or contracts, the entry window.
_LIMIT_KEY = re.compile(r"(cap|max_|stop|limit|lots|contracts|loss|^entry_start$|^entry_end$)")


def _live_values(slug: str) -> dict:
    """The strategy's own parameter values (``get_params()``): what its runner starts with. The UI specs' defaults can
    lag them (2026-09-29: Friend's spec said a 15,000 loss cap while its params, and so its runner, said 5,000)."""
    try:
        from api.services.strategies import _strategy
        p = _strategy(slug).get_params()
        return dict(p) if isinstance(p, dict) else {}
    except Exception:
        return {}


def _strategy_catalogue(slug: str, specs_for: Optional[Callable[[str], list]] = None,
                        values_for: Optional[Callable[[str], dict]] = None) -> list[dict]:
    if specs_for is None:
        from engine.strategy_backtest import backtest_param_specs as specs_for
    live = (values_for or _live_values)(slug) or {}
    out = []
    for p in specs_for(slug) or []:
        key = str(p.get("key") or "")
        if not key or not _LIMIT_KEY.search(key) or ("default" not in p and key not in live):
            continue
        d = live.get(key, p.get("default"))
        kind = "time" if isinstance(d, str) and re.fullmatch(r"\d{1,2}:\d{2}", d) else "number"
        if kind == "number" and not isinstance(d, (int, float)):
            continue
        out.append(_lim(key, str(p.get("label") or key), "", d, p.get("min"), p.get("max"), "next_session",
                        str(p.get("help") or ""), kind))
    return out


# ── stores ────────────────────────────────────────────────────────────────────

def _utcnow() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)


class MemoryLimitStore:
    def __init__(self):
        self._lock = threading.Lock()
        self.values: dict[tuple[str, str], dict] = {}
        self.changes: list[dict] = []

    def all(self) -> dict[tuple[str, str], dict]:
        with self._lock:
            return {k: dict(v) for k, v in self.values.items()}

    def put(self, scope: str, name: str, value, by: Optional[str], reason: Optional[str]) -> None:
        with self._lock:
            old = self.values.get((scope, name))
            self.values[(scope, name)] = {"value": value, "updated_by": by, "updated_at": _utcnow()}
            self.changes.append({"id": len(self.changes) + 1, "scope": scope, "name": name,
                                 "old": old["value"] if old else None, "new": value, "by": by, "reason": reason,
                                 "at": _utcnow()})

    def recent_changes(self, n: int = 30) -> list[dict]:
        with self._lock:
            return [dict(c) for c in reversed(self.changes[-n:])]


class DbLimitStore:
    def _eng(self):
        from api.services.db import require_db
        return require_db()

    def all(self) -> dict[tuple[str, str], dict]:
        from sqlalchemy import text
        from api.services import appdb
        if not appdb.exists("TradeLimit"):
            return {}
        with self._eng().connect() as c:
            rows = c.execute(text("SELECT Scope, Name, ValueJson, UpdatedBy, UpdatedAt FROM app.TradeLimit")).fetchall()
        return {(r[0], r[1]): {"value": json.loads(r[2]), "updated_by": r[3], "updated_at": r[4]} for r in rows}

    def put(self, scope: str, name: str, value, by: Optional[str], reason: Optional[str]) -> None:
        from sqlalchemy import text
        from api.services import appdb
        appdb.ensure("TradeLimit", "TradeLimitChange")
        body = json.dumps(value)
        with self._eng().begin() as c:
            old = c.execute(text("SELECT ValueJson FROM app.TradeLimit WHERE Scope = :s AND Name = :n"),
                            {"s": scope, "n": name}).fetchone()
            if old is None:
                c.execute(text("INSERT INTO app.TradeLimit (Scope, Name, ValueJson, UpdatedBy) VALUES (:s, :n, :v, :b)"),
                          {"s": scope, "n": name, "v": body, "b": by})
            else:
                c.execute(text("UPDATE app.TradeLimit SET ValueJson = :v, UpdatedBy = :b, UpdatedAt = SYSUTCDATETIME() "
                               "WHERE Scope = :s AND Name = :n"), {"s": scope, "n": name, "v": body, "b": by})
            c.execute(text("INSERT INTO app.TradeLimitChange (Scope, Name, OldJson, NewJson, ChangedBy, Reason) "
                           "VALUES (:s, :n, :o, :v, :b, :r)"),
                      {"s": scope, "n": name, "o": old[0] if old else None, "v": body, "b": by, "r": (reason or "")[:400] or None})

    def recent_changes(self, n: int = 30) -> list[dict]:
        from sqlalchemy import text
        from api.services import appdb
        if not appdb.exists("TradeLimitChange"):
            return []
        with self._eng().connect() as c:
            rows = c.execute(text(f"SELECT TOP {int(n)} Id, Scope, Name, OldJson, NewJson, ChangedBy, Reason, ChangedAt "
                                  "FROM app.TradeLimitChange ORDER BY Id DESC")).fetchall()
        return [{"id": r[0], "scope": r[1], "name": r[2], "old": json.loads(r[3]) if r[3] else None,
                 "new": json.loads(r[4]), "by": r[5], "reason": r[6], "at": r[7]} for r in rows]


def make_store():
    from api.services.arms import enabled_store
    m = enabled_store()
    return MemoryLimitStore() if m == "memory" else (None if m == "off" else DbLimitStore())


# The service's store, for the arm launcher (api/services/arms.py), which has no app state to hand.
STORE = None


def install(store) -> None:
    global STORE
    STORE = store


# ── values ────────────────────────────────────────────────────────────────────

def validate(lim: dict, value):
    """The value, coerced to the limit's kind, or LimitError: a number within [min, max], a time as HH:MM."""
    if lim["kind"] == "time":
        s = str(value).strip()
        if not re.fullmatch(r"\d{1,2}:\d{2}", s):
            raise LimitError(f"{lim['label']}: a time as HH:MM, not {value!r}")
        h, m = (int(x) for x in s.split(":"))
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise LimitError(f"{lim['label']}: {value!r} is not a time")
        s = f"{h:02d}:{m:02d}"
        lo, hi = lim.get("min"), lim.get("max")
        if (lo and s < str(lo)) or (hi and s > str(hi)):
            raise LimitError(f"{lim['label']}: {s} is outside {lo}-{hi}")
        return s
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise LimitError(f"{lim['label']}: a number, not {value!r}") from None
    if v != v or v in (float("inf"), float("-inf")):
        raise LimitError(f"{lim['label']}: a finite number")
    lo, hi = lim.get("min"), lim.get("max")
    if (lo is not None and v < float(lo)) or (hi is not None and v > float(hi)):
        raise LimitError(f"{lim['label']}: {v:g} is outside {lo}..{hi}")
    return int(v) if float(v).is_integer() and isinstance(lim.get("default"), int) else v


class Limits:
    """The catalogue (desks, armed strategies, system) joined with the stored values and today's usage."""

    def __init__(self, store, *, strategies: Optional[Callable[[], list[str]]] = None,
                 specs_for: Optional[Callable[[str], list]] = None, usage: Optional[Callable[[], dict]] = None,
                 values_for: Optional[Callable[[str], dict]] = None):
        self.store = store
        self._strategies = strategies or (lambda: [])
        self._specs_for = specs_for
        self._values_for = values_for
        self._usage = usage
        self._cat_cache: dict[str, tuple[float, list]] = {}

    # the catalogue
    def catalogue(self, scope: str) -> list[dict]:
        if scope in DESKS:
            return DESKS[scope]["limits"]
        if scope == SYSTEM_SCOPE:
            return _system_catalogue()
        hit = self._cat_cache.get(scope)
        if hit and time.monotonic() - hit[0] < 300:
            return hit[1]
        cat = _strategy_catalogue(scope, self._specs_for, self._values_for or (_live_values if self._specs_for is None else (lambda _s: {})))
        if cat or scope in set(self._strategies()):          # a strategy (not a stray name): it can be supervised
            cat = cat + SUPERVISOR
        self._cat_cache[scope] = (time.monotonic(), cat)
        return cat

    def scopes(self) -> list[tuple[str, str, str]]:
        """(scope, kind, label): the desks, every armed strategy and any strategy with a stored limit, the system."""
        out = [(s, "desk", d["label"]) for s, d in DESKS.items()]
        stored = {s for (s, _n) in (self.store.all() if self.store else {})}
        for s in sorted(set(self._strategies()) | (stored - set(DESKS) - {SYSTEM_SCOPE})):
            out.append((s, "strategy", s))
        out.append((SYSTEM_SCOPE, "system", "System"))
        return out

    def values(self, scope: str) -> dict:
        """{name: value} in force for one scope: the stored value, else the default."""
        stored = self.store.all() if self.store else {}
        return {l["name"]: (_in_force(scope, l["name"], stored) or {}).get("value", l["default"]) for l in self.catalogue(scope)}

    def overrides(self, scope: str) -> dict:
        """{name: value} only for what the trader has set (the launcher passes these, nothing else). Never the
        supervisor's controls: the runner reads those itself, and they are no strategy parameter."""
        stored = self.store.all() if self.store else {}
        names = {l["name"] for l in self.catalogue(scope)} - _SUP_NAMES
        return {n: v["value"] for (s, n), v in stored.items() if s == scope and n in names}

    def set(self, scope: str, name: str, value, *, by: Optional[str] = None, reason: Optional[str] = None) -> dict:
        if self.store is None:
            raise LimitError("the limits store is off (ALAN_TRADER_ARMS=off)")
        lim = next((l for l in self.catalogue(scope) if l["name"] == name), None)
        if lim is None:
            raise LimitError(f"{scope} has no limit {name!r}")
        v = validate(lim, value)
        self.store.put(scope, name, v, (by or "user")[:40], reason)
        logger.info("limit %s.%s set to %r by %s%s", scope, name, v, by or "user", f" ({reason})" if reason else "")
        return next(r for r in self.table(scope_filter=scope)["scopes"][0]["limits"] if r["name"] == name)

    # the table
    def table(self, scope_filter: Optional[str] = None) -> dict:
        stored = self.store.all() if self.store else {}
        try:
            usage = self._usage() if self._usage else {}
        except Exception:
            logger.exception("limits: usage failed")
            usage = {}
        scopes = []
        for scope, kind, label in self.scopes():
            if scope_filter and scope != scope_filter:
                continue
            rows = []
            for l in self.catalogue(scope):
                st = _in_force(scope, l["name"], stored)
                value = st["value"] if st else l["default"]
                used, status = _usage_of(l["name"], value, usage.get(scope, {}), usage)
                rows.append({**l, "value": value, "is_default": st is None,
                             "updated_by": st.get("updated_by") if st else None,
                             "updated_at": st.get("updated_at") if st else None,
                             "used": used, "status": status})
            scopes.append({"scope": scope, "kind": kind, "label": label, "limits": rows,
                           "day_pnl": usage.get(scope, {}).get("day_pnl")})
        return {"asof": _dt.datetime.now().isoformat(timespec="seconds"), "scopes": scopes,
                "changes": self.store.recent_changes(30) if self.store else []}


def _usage_of(name: str, value, u: dict, usage: dict) -> tuple[Optional[float], str]:
    """(used, status) of one limit given its scope's usage {day_pnl, open_positions, max_open_risk}."""
    def grade(used: float, cap: float) -> str:
        if cap <= 0:
            return "ok"
        return "hit" if used >= cap - 1e-9 else ("near" if used >= 0.8 * cap else "ok")
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None, "ok"
    if name == "broker_day_cap":
        calls = usage.get(SYSTEM_SCOPE, {}).get("broker_calls")
        return (calls, grade(calls, v)) if calls is not None else (None, "ok")
    if name == "account_day_stop":
        sysu = usage.get(SYSTEM_SCOPE, {})
        acct = sysu.get("account_day") if sysu.get("account_day") is not None else sysu.get("day_pnl")
        return (acct, grade(max(0.0, -acct), abs(v))) if acct is not None and v > 0 else (acct, "ok")
    pnl = u.get("day_pnl")
    if name == "day_stop" and pnl is not None:            # negative: -2,500
        loss = max(0.0, -pnl)
        return pnl, grade(loss, abs(v))
    if "loss" in name and "cap" in name and pnl is not None and v > 0:    # a strategy's daily loss cap: 5,000
        return pnl, grade(max(0.0, -pnl), v)
    if name == "max_positions" and u.get("open_positions") is not None:
        n = float(u["open_positions"])
        return n, ("hit" if n >= v else "ok")
    if name == "max_risk" and u.get("max_open_risk") is not None:
        r = float(u["max_open_risk"])
        return r, ("hit" if r > v + 1e-6 else ("near" if r >= 0.8 * v else "ok"))
    return None, "ok"


# ── usage from the paper book ────────────────────────────────────────────────

def paper_usage(hub=None, broker_calls: Optional[Callable[[], Optional[int]]] = None) -> dict:
    """{scope: {day_pnl, open_positions, max_open_risk}, "system": {broker_calls}} for today, from the paper book."""
    from api.services import paper as P
    today = _dt.date.today().isoformat()
    out: dict[str, dict] = {}
    for status in ("open", "closed"):
        for r in P.positions(status, hub=hub).get("rows", []):
            s = str(r.get("strategy") or "")
            if not s:
                continue
            if status == "closed" and str(r.get("closed") or "")[:10] != today:
                continue
            u = out.setdefault(s, {"day_pnl": 0.0, "open_positions": 0, "max_open_risk": 0.0})
            u["day_pnl"] += float(r.get("pnl") or 0.0)
            if status == "open":
                u["open_positions"] += 1
                ml = r.get("max_loss")
                if ml is not None:
                    u["max_open_risk"] = max(u["max_open_risk"], abs(float(ml)))
    out[SYSTEM_SCOPE] = {"broker_calls": (broker_calls or broker_calls_today)(),
                         "day_pnl": round(sum(u["day_pnl"] for u in out.values()), 2),   # the scopes summed (since entry)
                         "account_day": account_day_change(hub)}                          # the account's real day
    return out


_PRIOR_EQUITY: dict = {}                      # {date: the equity at the last close before it} (fixed for the day)
_PRIOR_FAILED: dict = {}                      # {date: monotonic time of the last failed attempt}
PRIOR_RETRY_S = 600.0                         # a failed read of the last close is retried at most every 10 minutes


def account_day_change(hub=None, today: Optional[_dt.date] = None) -> Optional[float]:
    """The paper account's P&L today: its equity now (live marks) minus its equity at the last close before today.

    The scopes' ``day_pnl`` counts an open position's whole P&L since entry, so multi-day holdings (the rotation, BTC
    momentum, the cash sleeve) would make a quiet day look like a big one; the account day stop reads this instead.
    None when either number is unavailable (the caller then falls back to the scopes' sum)."""
    from api.services import paper as P
    today = today or _dt.date.today()
    try:
        if today not in _PRIOR_EQUITY:
            failed = _PRIOR_FAILED.get(today)
            if failed is not None and time.monotonic() - failed < PRIOR_RETRY_S:
                return None                   # the equity series is slow (prices per holding): don't hammer it
            _PRIOR_FAILED[today] = time.monotonic()
            e = P.equity((today - _dt.timedelta(days=14)).isoformat(), today.isoformat())
            ser = next((x for x in (e or {}).get("series", []) if x.get("name") == "equity"), None)
            prior = [float(v) for t, v in zip((ser or {}).get("t", []), (ser or {}).get("v", []))
                     if str(t)[:10] < today.isoformat() and v is not None]
            if not prior:
                return None
            _PRIOR_EQUITY.clear()
            _PRIOR_EQUITY[today] = prior[-1]
            _PRIOR_FAILED.pop(today, None)
        now = P.summary(hub).get("equity")
        return round(float(now) - float(_PRIOR_EQUITY[today]), 2) if now is not None else None
    except Exception as exc:  # noqa: BLE001 — the stop falls back to the scopes' sum
        logger.info("account day change unavailable: %s", exc)
        return None


def broker_calls_today() -> Optional[int]:
    """Today's broker REST calls, this checkout's count plus the other checkouts' (paper_state/broker_calls_<day>.json)."""
    from pathlib import Path
    from api.bootstrap import WORKING_COPY
    dirs = [WORKING_COPY / "paper_state"]
    try:
        from api.config import external_state_dirs
        dirs += [Path(d) for d in external_state_dirs()]
    except Exception:
        pass
    total, seen = 0, False
    for d in dict.fromkeys(dirs):
        f = Path(d) / f"broker_calls_{_dt.date.today().isoformat()}.json"
        try:
            total += int(json.loads(f.read_text(encoding="utf-8"))["calls"])
            seen = True
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return total if seen else None


def launch_params(strategy: str) -> dict:
    """The stored limits of ``strategy`` for its runner's command line (--param key=value); {} when none or no store."""
    if STORE is None:
        return {}
    try:
        return Limits(STORE).overrides(strategy)
    except Exception:
        logger.exception("limits: launch params for %s", strategy)
        return {}


def launch_broker_cap() -> Optional[int]:
    """The stored broker day cap, for the launched runners' environment; None when unset."""
    if STORE is None:
        return None
    try:
        v = STORE.all().get((SYSTEM_SCOPE, "broker_day_cap"))
        return int(v["value"]) if v else None
    except Exception:
        logger.exception("limits: broker cap")
        return None
