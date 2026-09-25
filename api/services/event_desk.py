"""
api/services/event_desk.py — the event desk: a manual event log, the war-regime switch, the playbooks
evaluated on today's signals, the open event trades, and the post-close SIGNAL LOG.

Playbooks (api/services/event_signals.py supplies the numbers; oil_study / crypto_study are the sources):
  oil_fade    crude spike ≥ 2% (or a 2σ move) in the last 5 sessions -> fade with a USO put vertical AFTER
              the first down close, when no barrels were lost, OVX < 60, not three higher closes running,
              and (war regime off, or an explicit de-escalation logged). Add on the first de-escalation.
              Leave alone: barrels lost, OVX ≥ 60, three higher closes. EXPERIMENTAL: the rules-based fade
              lost out of sample (crude_vix study, ≈ −$8 per spread); the allocator is a research tool.
  btc_dip     a logged risk-off event with BTC ≥ 2% under its pre-shock close (or a −3% 24-h drop) -> buy IBIT
              at the next NYSE open, out after 1–3 sessions, at −4%, or when BTC is back at the pre-shock
              price. EXPERIMENTAL (n = 22 episodes).
  vix_note    VIX 2σ high -> a note only: VIX options price off the futures, which already carry the
              reversion (no trade).
  crypto_flush  api/services/crypto_flush.py (the OKX poller); shown here.

The signal log (SignalLogJob, armed like an allocator at 16:15 ET): each day USO's move is ≥ 2σ, VIX's
level is 2σ high, or BTC is down ≥ 3% on the day, one row with the move, VIX / OVX and the 20-day baselines;
the trader tags it that evening (iran_headline | other_geopolitical | supply_loss | macro | none), before
the outcome; the job back-fills each row's r3 / r10 / r20 and whether half the move was given back (and
after how many sessions), so the "geopolitical spikes revert" claim is tested forward, without hindsight.

Stores: memory under ALAN_TRADER_ARMS=memory (the test suite), else app.EventLog / app.EventDeskSetting /
app.EventDeskLog / app.EventSignalLog (api/services/appdb.py).
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import math
import threading
from typing import Callable, Optional

import pandas as pd

from api.services import event_signals as ES

logger = logging.getLogger("alan_trader.api.event_desk")

NY = "America/New_York"
KINDS = ("escalation", "de-escalation", "supply_loss", "policy", "post")
BARRELS = ("Y", "P", "N", "unknown")
TAGS = ("iran_headline", "other_geopolitical", "supply_loss", "macro", "none")
PLAYBOOKS = ("oil_fade", "btc_dip", "vix_note", "crypto_flush")
SHOCK_KINDS = ("escalation", "supply_loss", "policy")       # what counts as a risk-off shock for BTC
ESCALATION_KINDS = ("escalation", "supply_loss", "post")     # what a crude spike is attributed to
LEDGER = {"oil_fade": "event:oil_fade", "btc_dip": "event:btc_dip"}

OIL_PARAMS = {
    "spike_pct": 2.0, "spike_z": 2.0, "spike_lookback": 5, "ovx_leave": 60.0, "ovx_better": 45.0,
    "higher_streak_leave": 3, "deescalation_sessions": 3,
    "dte_min": 21, "dte_max": 42, "dte_target": 30, "short_pct": 0.06, "strike_step": 1.0, "spreads": 1,
    "slippage": 0.05, "max_sessions": 10, "stop_pct": 0.50, "min_nights": 1, "max_adds": 1,
}
BTC_PARAMS = {
    "dip_pct": 2.0, "drop_24h_pct": -3.0, "event_sessions": 3, "dollars": 5000.0, "vehicle": "shares",
    "short_pct": 0.06, "dte_min": 21, "dte_max": 42, "dte_target": 30, "strike_step": 1.0, "slippage": 0.02,
    "max_sessions": 3, "stop_pct": 0.04, "min_nights": 1,
}
VIX_PARAMS = {"z": 2.0}
SIGNAL_LOG_RULES = {"USO": ("move_z20", 2.0, "abs"), "VIX": ("z20", 2.0, "ge"), "BTC": ("change_pct", -3.0, "le")}


class EventError(ValueError):
    """A request the desk cannot accept (422)."""


# ── time helpers ──────────────────────────────────────────────────────────────

def now_et() -> pd.Timestamp:
    return pd.Timestamp.now(tz=NY)


def to_utc_naive(ts, default_tz: str = NY) -> _dt.datetime:
    t = pd.Timestamp(ts)
    if pd.isna(t):
        raise EventError("ts is not a timestamp")
    t = t.tz_localize(default_tz) if t.tzinfo is None else t
    return t.tz_convert("UTC").to_pydatetime().replace(tzinfo=None)


def et_iso(utc_naive) -> Optional[str]:
    if utc_naive is None or (isinstance(utc_naive, float) and math.isnan(utc_naive)):
        return None
    t = pd.Timestamp(utc_naive)
    t = t.tz_localize("UTC") if t.tzinfo is None else t
    return t.tz_convert(NY).isoformat(timespec="seconds")


def et_date(utc_naive) -> _dt.date:
    t = pd.Timestamp(utc_naive)
    t = t.tz_localize("UTC") if t.tzinfo is None else t
    return t.tz_convert(NY).date()


def _utcnow() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)


def trading_day(d: _dt.date) -> bool:
    from api.services.arms import trading_day as td
    return td(d)


def next_trading_day(d: _dt.date) -> _dt.date:
    n = d + _dt.timedelta(days=1)
    while not trading_day(n):
        n += _dt.timedelta(days=1)
    return n


def sessions_between(a: _dt.date, b: _dt.date) -> int:
    """Trading sessions after ``a`` up to and including ``b`` (0 when b <= a)."""
    n, d = 0, a
    while d < b:
        d += _dt.timedelta(days=1)
        if trading_day(d):
            n += 1
    return n


def next_nyse_open(now: pd.Timestamp) -> _dt.date:
    d = now.date()
    if trading_day(d) and now.time() < _dt.time(9, 30):
        return d
    return next_trading_day(d)


# ── the event log ─────────────────────────────────────────────────────────────

def parse_event(body: dict, now: Optional[pd.Timestamp] = None) -> dict:
    if not isinstance(body, dict):
        raise EventError("an event is a JSON object")
    kind = str(body.get("kind") or "").strip().lower()
    kind = {"deescalation": "de-escalation", "de_escalation": "de-escalation", "supply-loss": "supply_loss"}.get(kind, kind)
    if kind not in KINDS:
        raise EventError(f"kind must be one of {', '.join(KINDS)}")
    text = str(body.get("text") or "").strip()
    if not text:
        raise EventError("text is required")
    bl = body.get("barrels_lost")
    bl = "unknown" if bl in (None, "") else str(bl).strip()
    bl = {"y": "Y", "p": "P", "n": "N", "yes": "Y", "no": "N", "partial": "P", "unknown": "unknown"}.get(bl.lower(), bl)
    if bl not in BARRELS:
        raise EventError("barrels_lost must be Y, P, N or unknown")
    ts = body.get("ts")
    try:
        when = to_utc_naive(ts) if ts not in (None, "") else to_utc_naive(now or now_et())
    except (ValueError, TypeError, EventError):
        raise EventError(f"ts {ts!r} is not an ISO-8601 timestamp")
    region = body.get("region")
    source = body.get("source")
    return {"ts": when, "kind": kind, "region": (str(region).strip()[:80] or None) if region not in (None, "") else None,
            "text": text[:1000], "barrels_lost": bl,
            "source": (str(source).strip()[:400] or None) if source not in (None, "") else None}


def event_view(r: dict) -> dict:
    return {"id": r["id"], "ts": et_iso(r["ts"]), "kind": r["kind"], "region": r.get("region"), "text": r["text"],
            "barrels_lost": r.get("barrels_lost") or "unknown", "source": r.get("source"),
            "created": et_iso(r.get("created"))}


def parse_tag(body: dict) -> dict:
    if not isinstance(body, dict):
        raise EventError("a tag is a JSON object")
    tag = body.get("tag")
    tag = None if tag in (None, "") else str(tag).strip().lower()
    if tag is not None and tag not in TAGS:
        raise EventError(f"tag must be one of {', '.join(TAGS)} (or null to clear)")
    note = body.get("note")
    return {"tag": tag, "note": (str(note).strip()[:400] or None) if note not in (None, "") else None}


def parse_regime(body: dict) -> dict:
    if not isinstance(body, dict) or "war" not in body:
        raise EventError("regime is {war: bool, note?: string}")
    war = body.get("war")
    if isinstance(war, str):
        war = war.strip().lower() in ("1", "true", "yes", "on")
    note = body.get("note")
    return {"war": bool(war), "note": (str(note).strip()[:200] or None) if note not in (None, "") else None}


# ── stores ────────────────────────────────────────────────────────────────────

SIGNAL_COLS = ("id", "date", "symbol", "close", "change_pct", "move_z", "level_z", "mean20", "sd20", "vix", "vix_change_pct",
               "ovx", "tag", "note", "tagged_at", "half_back", "half_back_days", "r3", "r10", "r20", "outcome_asof",
               "created")


class MemoryEventStore:
    def __init__(self):
        self._lock = threading.Lock()
        self.events: list[dict] = []
        self.settings: dict[str, dict] = {}
        self.decisions: list[dict] = []
        self.signal_rows: list[dict] = []
        self._ids = {"event": 0, "signal": 0}

    # events
    def add_event(self, row: dict) -> dict:
        with self._lock:
            self._ids["event"] += 1
            r = dict(row, id=self._ids["event"], created=_utcnow())
            self.events.append(r)
            return dict(r)

    def events_since(self, since: _dt.datetime) -> list[dict]:
        with self._lock:
            return sorted((dict(r) for r in self.events if r["ts"] >= since), key=lambda r: (r["ts"], r["id"]), reverse=True)

    def delete_event(self, event_id: int) -> bool:
        with self._lock:
            n = len(self.events)
            self.events = [r for r in self.events if r["id"] != event_id]
            return len(self.events) < n

    # settings
    def get_setting(self, name: str) -> Optional[dict]:
        with self._lock:
            v = self.settings.get(name)
            return dict(v) if v else None

    def put_setting(self, name: str, value: dict) -> dict:
        with self._lock:
            self.settings[name] = dict(value, updated=_utcnow())
            return dict(self.settings[name])

    # allocator decisions
    def decided(self, playbook: str, day: _dt.date) -> Optional[dict]:
        with self._lock:
            return next((dict(r) for r in self.decisions if r["playbook"] == playbook and r["date"] == day), None)

    def add_decision(self, row: dict) -> bool:
        with self._lock:
            if any(r["playbook"] == row["playbook"] and r["date"] == row["date"] for r in self.decisions):
                return False
            self.decisions.append(dict(row, decided_at=_utcnow()))
            return True

    def decisions_since(self, since: _dt.date, playbook: Optional[str] = None) -> list[dict]:
        with self._lock:
            rows = [dict(r) for r in self.decisions if r["date"] >= since and (playbook is None or r["playbook"] == playbook)]
        return sorted(rows, key=lambda r: (r["date"].toordinal(), r["playbook"]), reverse=True)

    # the signal log
    def add_signal(self, row: dict) -> Optional[dict]:
        with self._lock:
            if any(r["date"] == row["date"] and r["symbol"] == row["symbol"] for r in self.signal_rows):
                return None
            self._ids["signal"] += 1
            r = {k: None for k in SIGNAL_COLS}
            r.update(row, id=self._ids["signal"], created=_utcnow())
            self.signal_rows.append(r)
            return dict(r)

    def signal(self, signal_id: int) -> Optional[dict]:
        with self._lock:
            return next((dict(r) for r in self.signal_rows if r["id"] == signal_id), None)

    def signals_since(self, since: _dt.date) -> list[dict]:
        with self._lock:
            rows = [dict(r) for r in self.signal_rows if r["date"] >= since]
        return sorted(rows, key=lambda r: (r["date"].toordinal(), r["symbol"]), reverse=True)

    def pending_signals(self) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self.signal_rows if r.get("r20") is None]

    def update_signal(self, signal_id: int, **cols) -> Optional[dict]:
        with self._lock:
            r = next((r for r in self.signal_rows if r["id"] == signal_id), None)
            if r is None:
                return None
            r.update(cols)
            return dict(r)


class DbEventStore:
    def _eng(self):
        from api.services.db import require_db
        return require_db()

    @staticmethod
    def _date(v):
        return v.date() if isinstance(v, _dt.datetime) else v

    # events
    _EV = "EventId, Ts, Kind, Region, EventText, BarrelsLost, Source, CreatedAt"

    @staticmethod
    def _ev_row(r) -> dict:
        d = dict(zip(("id", "ts", "kind", "region", "text", "barrels_lost", "source", "created"), r))
        return d

    def add_event(self, row: dict) -> dict:
        from sqlalchemy import text
        from api.services import appdb
        appdb.ensure("EventLog")
        with self._eng().begin() as c:
            r = c.execute(text("INSERT INTO app.EventLog (Ts, Kind, Region, EventText, BarrelsLost, Source) OUTPUT INSERTED.EventId "
                               "VALUES (:ts, :k, :rg, :tx, :bl, :src)"),
                          {"ts": row["ts"], "k": row["kind"], "rg": row.get("region"), "tx": row["text"],
                           "bl": row.get("barrels_lost") or "unknown", "src": row.get("source")}).fetchone()
            got = c.execute(text(f"SELECT {self._EV} FROM app.EventLog WHERE EventId = :id"), {"id": int(r[0])}).fetchone()
        return self._ev_row(got)

    def events_since(self, since: _dt.datetime) -> list[dict]:
        from sqlalchemy import text
        from api.services import appdb
        if not appdb.exists("EventLog"):
            return []
        with self._eng().connect() as c:
            rows = c.execute(text(f"SELECT {self._EV} FROM app.EventLog WHERE Ts >= :s ORDER BY Ts DESC, EventId DESC"),
                             {"s": since}).fetchall()
        return [self._ev_row(r) for r in rows]

    def delete_event(self, event_id: int) -> bool:
        from sqlalchemy import text
        from api.services import appdb
        if not appdb.exists("EventLog"):
            return False
        with self._eng().begin() as c:
            return c.execute(text("DELETE FROM app.EventLog WHERE EventId = :id"), {"id": int(event_id)}).rowcount > 0

    # settings
    def get_setting(self, name: str) -> Optional[dict]:
        from sqlalchemy import text
        from api.services import appdb
        if not appdb.exists("EventDeskSetting"):
            return None
        with self._eng().connect() as c:
            r = c.execute(text("SELECT ValueJson, UpdatedAt FROM app.EventDeskSetting WHERE Name = :n"), {"n": name}).fetchone()
        if not r:
            return None
        return dict(json.loads(r[0]), updated=r[1])

    def put_setting(self, name: str, value: dict) -> dict:
        from sqlalchemy import text
        from api.services import appdb
        appdb.ensure("EventDeskSetting")
        body = json.dumps({k: v for k, v in value.items() if k != "updated"}, default=str)
        with self._eng().begin() as c:
            n = c.execute(text("UPDATE app.EventDeskSetting SET ValueJson = :j, UpdatedAt = SYSUTCDATETIME() WHERE Name = :n"),
                          {"j": body, "n": name}).rowcount
            if not n:
                c.execute(text("INSERT INTO app.EventDeskSetting (Name, ValueJson) VALUES (:n, :j)"), {"n": name, "j": body})
        return self.get_setting(name)

    # decisions
    _DEC = ("Playbook, TradeDate, Status, Verdict, Action, TradeGroupId, Summary, DetailJson, DecidedAt")

    def _dec_row(self, r) -> dict:
        d = dict(zip(("playbook", "date", "status", "verdict", "action", "trade_group_id", "summary", "detail", "decided_at"), r))
        d["detail"] = json.loads(d["detail"]) if d["detail"] else {}
        d["date"] = self._date(d["date"])
        return d

    def decided(self, playbook: str, day: _dt.date) -> Optional[dict]:
        from sqlalchemy import text
        from api.services import appdb
        if not appdb.exists("EventDeskLog"):
            return None
        with self._eng().connect() as c:
            r = c.execute(text(f"SELECT {self._DEC} FROM app.EventDeskLog WHERE Playbook = :p AND TradeDate = :d"),
                          {"p": playbook, "d": day}).fetchone()
        return self._dec_row(r) if r else None

    def add_decision(self, row: dict) -> bool:
        from sqlalchemy import text
        from sqlalchemy.exc import IntegrityError
        from api.services import appdb
        appdb.ensure("EventDeskLog")
        try:
            with self._eng().begin() as c:
                c.execute(text("INSERT INTO app.EventDeskLog (Playbook, TradeDate, Status, Verdict, Action, TradeGroupId, Summary, "
                               "DetailJson) VALUES (:p, :d, :st, :v, :a, :tg, :s, :det)"),
                          {"p": row["playbook"], "d": row["date"], "st": row["status"], "v": row.get("verdict"),
                           "a": row.get("action"), "tg": row.get("trade_group_id"), "s": (row.get("summary") or "")[:400],
                           "det": json.dumps(row.get("detail") or {}, default=str)})
            return True
        except IntegrityError:
            return False

    def decisions_since(self, since: _dt.date, playbook: Optional[str] = None) -> list[dict]:
        from sqlalchemy import text
        from api.services import appdb
        if not appdb.exists("EventDeskLog"):
            return []
        where = "TradeDate >= :d" + (" AND Playbook = :p" if playbook else "")
        with self._eng().connect() as c:
            rows = c.execute(text(f"SELECT {self._DEC} FROM app.EventDeskLog WHERE {where} ORDER BY TradeDate DESC, Playbook"),
                             {"d": since, "p": playbook}).fetchall()
        return [self._dec_row(r) for r in rows]

    # the signal log
    _SIG_DB = ("Id", "TradeDate", "Symbol", "ClosePx", "ChangePct", "MoveZ", "LevelZ", "Mean20", "Sd20", "VixClose",
               "VixChangePct", "Ovx", "Tag", "Note", "TaggedAt", "HalfBack", "HalfBackDays", "R3", "R10", "R20",
               "OutcomeAsOf", "CreatedAt")
    _SIG_MAP = dict(zip(SIGNAL_COLS, _SIG_DB))

    def _sig_row(self, r) -> dict:
        d = dict(zip(SIGNAL_COLS, r))
        d["date"] = self._date(d["date"])
        d["outcome_asof"] = self._date(d["outcome_asof"])
        if d["half_back"] is not None:
            d["half_back"] = bool(d["half_back"])
        return d

    def add_signal(self, row: dict) -> Optional[dict]:
        from sqlalchemy import text
        from sqlalchemy.exc import IntegrityError
        from api.services import appdb
        appdb.ensure("EventSignalLog")
        cols = [k for k in SIGNAL_COLS if k in row and k not in ("id", "created")]
        try:
            with self._eng().begin() as c:
                r = c.execute(text(f"INSERT INTO app.EventSignalLog ({', '.join(self._SIG_MAP[k] for k in cols)}) OUTPUT INSERTED.Id "
                                   f"VALUES ({', '.join(':' + k for k in cols)})"), {k: row[k] for k in cols}).fetchone()
            return self.signal(int(r[0]))
        except IntegrityError:
            return None

    def signal(self, signal_id: int) -> Optional[dict]:
        from sqlalchemy import text
        from api.services import appdb
        if not appdb.exists("EventSignalLog"):
            return None
        with self._eng().connect() as c:
            r = c.execute(text(f"SELECT {', '.join(self._SIG_DB)} FROM app.EventSignalLog WHERE Id = :id"),
                          {"id": int(signal_id)}).fetchone()
        return self._sig_row(r) if r else None

    def signals_since(self, since: _dt.date) -> list[dict]:
        from sqlalchemy import text
        from api.services import appdb
        if not appdb.exists("EventSignalLog"):
            return []
        with self._eng().connect() as c:
            rows = c.execute(text(f"SELECT {', '.join(self._SIG_DB)} FROM app.EventSignalLog WHERE TradeDate >= :d "
                                  f"ORDER BY TradeDate DESC, Symbol"), {"d": since}).fetchall()
        return [self._sig_row(r) for r in rows]

    def pending_signals(self) -> list[dict]:
        from sqlalchemy import text
        from api.services import appdb
        if not appdb.exists("EventSignalLog"):
            return []
        with self._eng().connect() as c:
            rows = c.execute(text(f"SELECT {', '.join(self._SIG_DB)} FROM app.EventSignalLog WHERE R20 IS NULL")).fetchall()
        return [self._sig_row(r) for r in rows]

    def update_signal(self, signal_id: int, **cols) -> Optional[dict]:
        from sqlalchemy import text
        sets = ", ".join(f"{self._SIG_MAP[k]} = :{k}" for k in cols if k in self._SIG_MAP)
        if sets:
            with self._eng().begin() as c:
                c.execute(text(f"UPDATE app.EventSignalLog SET {sets} WHERE Id = :id"), {**cols, "id": int(signal_id)})
        return self.signal(signal_id)


def make_store():
    from api.services.arms import enabled_store
    m = enabled_store()
    return MemoryEventStore() if m == "memory" else (None if m == "off" else DbEventStore())


# ── structures (pure) ─────────────────────────────────────────────────────────

def third_friday(year: int, month: int) -> _dt.date:
    d = _dt.date(year, month, 15)
    while d.weekday() != 4:
        d += _dt.timedelta(days=1)
    return d


def pick_expiry(today: _dt.date, expirations: Optional[list], dte_min: int, dte_max: int, target: int) -> Optional[_dt.date]:
    """The listed expiry with dte in [dte_min, dte_max] nearest ``target``; without a list, the first monthly
    (third Friday) at least ``dte_min`` out."""
    if expirations:
        cands = []
        for e in expirations:
            d = e if isinstance(e, _dt.date) else _dt.date.fromisoformat(str(e)[:10])
            dte = (d - today).days
            if dte_min <= dte <= dte_max:
                cands.append((abs(dte - target), d))
        if cands:
            return min(cands)[1]
    y, m = today.year, today.month
    for _ in range(4):
        d = third_friday(y, m)
        if (d - today).days >= dte_min:
            return d
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return None


def _round_step(x: float, step: float) -> float:
    return round(round(x / step) * step, 4)


def suggest_vertical(kind: str, underlying: str, spot: Optional[float], today: _dt.date, expirations: Optional[list],
                     short_pct: float, dte_min: int, dte_max: int, dte_target: int, step: float = 1.0,
                     mids: Optional[dict] = None, n: int = 1, hold_rule: str = "") -> Optional[dict]:
    """A defined-risk vertical: long ~ATM, short ``short_pct`` away (below for a put spread, above for a
    call spread). ``mids``: {occ symbol: mid} when the chain is quoted (else prices are null)."""
    if not spot or spot <= 0:
        return None
    from api.marketdata import symbols as SYM
    exp = pick_expiry(today, expirations, dte_min, dte_max, dte_target)
    if exp is None:
        return None
    long_k = _round_step(spot, step)
    short_k = _round_step(spot * (1 - short_pct) if kind == "put" else spot * (1 + short_pct), step)
    if short_k == long_k:
        short_k = long_k - step if kind == "put" else long_k + step
    right = "P" if kind == "put" else "C"
    long_sym = SYM.make_option(underlying, exp, right, long_k).occ
    short_sym = SYM.make_option(underlying, exp, right, short_k).occ
    width = abs(long_k - short_k)
    debit = None
    if mids and mids.get(long_sym) is not None and mids.get(short_sym) is not None:
        debit = round(float(mids[long_sym]) - float(mids[short_sym]), 2)
    legs = [{"type": kind, "side": "buy", "strike": long_k, "expiry": exp.isoformat(), "quantity": n, "symbol": long_sym},
            {"type": kind, "side": "sell", "strike": short_k, "expiry": exp.isoformat(), "quantity": n, "symbol": short_sym}]
    return {"structure": f"{underlying} {kind} vertical", "underlying": underlying, "kind": kind,
            "legs": f"+{right}{long_k:g} −{right}{short_k:g} {exp.isoformat()}", "expiry": exp.isoformat(),
            "dte": (exp - today).days, "long_strike": long_k, "short_strike": short_k, "width": width,
            "quantity": n, "est_debit": debit,
            "max_loss": round(debit * 100 * n, 2) if debit is not None else None,
            "max_profit": round((width - debit) * 100 * n, 2) if debit is not None else None,
            "order_legs": legs, "hold_rule": hold_rule}


# ── the playbooks (pure) ──────────────────────────────────────────────────────

def _pct(v, signed=True) -> str:
    if v is None:
        return "n/a"
    return f"{v:+.1f}%" if signed else f"{v:.1f}%"


def _ev_date(ev: dict) -> _dt.date:
    ts = ev.get("ts")
    if isinstance(ts, str):
        return pd.Timestamp(ts).date() if pd.Timestamp(ts).tzinfo is None else pd.Timestamp(ts).tz_convert(NY).date()
    return et_date(ts)


def _ev_date_utc(ev: dict) -> _dt.date:
    """The event's UTC date: BTC's daily closes are UTC days, so the pre-shock close is the last one dated before it."""
    ts = ev.get("ts")
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize("UTC") if not isinstance(ts, str) else t.tz_localize(NY)
    return t.tz_convert("UTC").date()


def _short(ev: dict, n: int = 60) -> str:
    t = str(ev.get("text") or "")
    return f"{_ev_date(ev).isoformat()}: {t[:n]}{'…' if len(t) > n else ''}"


def evaluate_crude(cl: dict, closes_cl, ovx_last: Optional[float], events: list[dict], war: bool,
                   open_trades: list[dict], today: _dt.date, params: Optional[dict] = None,
                   trade: Optional[dict] = None) -> dict:
    p = dict(OIL_PARAMS, **(params or {}))
    checklist: list[dict] = []
    reasons: list[str] = []
    spike = ES.recent_spike(closes_cl, p["spike_pct"], p["spike_z"], p["spike_lookback"])
    checklist.append({"label": f"Spike ≥ {p['spike_pct']:g}% or move z ≥ {p['spike_z']:g} (last {p['spike_lookback']} sessions)",
                      "ok": spike is not None,
                      "value": (f"{_pct(spike['change_pct'])} on {spike['date']} (z {spike['move_z20'] if spike['move_z20'] is not None else 'n/a'})"
                                if spike else f"last move {_pct(cl.get('change_pct'))}, z {cl.get('move_z20') if cl.get('move_z20') is not None else 'n/a'}")})
    mine = [t for t in open_trades if t.get("playbook") == "oil_fade"]
    out = {"id": "oil_fade", "title": "Crude spike fade", "verdict": "none", "headline": "", "reasons": reasons,
           "checklist": checklist, "trade": None, "armed": False, "experimental": True,
           "detail": {"spike": spike, "war": war, "ovx": ovx_last, "open_trades": len(mine)}}
    if spike is None:
        out["headline"] = (f"No crude spike in the last {p['spike_lookback']} sessions (last move {_pct(cl.get('change_pct'))}, "
                           f"crude {cl.get('last')})")
        if mine:
            out["headline"] += f"; {len(mine)} open spread(s) managed by the exit rules"
        return out
    spike_day = _dt.date.fromisoformat(spike["date"])
    window = [e for e in events if spike_day - _dt.timedelta(days=1) <= _ev_date(e) <= today]
    esc = [e for e in window if e["kind"] in ESCALATION_KINDS]
    lost = [e for e in window if e.get("barrels_lost") == "Y"]
    partial = [e for e in window if e.get("barrels_lost") == "P"]
    if lost:
        checklist.append({"label": "No barrels lost", "ok": False, "value": _short(lost[0])})
    elif partial:
        checklist.append({"label": "No barrels lost", "ok": True, "value": "partial: " + _short(partial[0])})
    elif esc:
        checklist.append({"label": "No barrels lost", "ok": True, "value": _short(esc[0])})
    else:
        checklist.append({"label": "No barrels lost", "ok": None, "value": "no event logged for this spike"})
    ovx_ok = None if ovx_last is None else ovx_last < p["ovx_leave"]
    checklist.append({"label": f"OVX < {p['ovx_leave']:g} (better < {p['ovx_better']:g})", "ok": ovx_ok,
                      "value": f"{ovx_last:.1f}" if ovx_last is not None else "n/a"})
    streak = int(cl.get("higher_streak") or 0)
    checklist.append({"label": f"Not closed higher {p['higher_streak_leave']} sessions running", "ok": streak < p["higher_streak_leave"],
                      "value": f"{streak} higher close(s) running"})
    checklist.append({"label": "First down close since the spike", "ok": bool(spike["down_close_since"]),
                      "value": spike["first_down_close"] or f"none yet ({spike['sessions_ago']} session(s) since the spike)"})
    deesc = sorted((e for e in window if e["kind"] == "de-escalation" and _ev_date(e) > spike_day), key=_ev_date)
    within = [e for e in deesc if sessions_between(spike_day, _ev_date(e)) <= p["deescalation_sessions"]]
    checklist.append({"label": f"De-escalation seen within {p['deescalation_sessions']} sessions", "ok": bool(within),
                      "value": _short(within[0]) if within else (_short(deesc[0]) + " (later)" if deesc else "none logged")})
    checklist.append({"label": "War regime off", "ok": not war, "value": "war regime ON" if war else "off"})
    # ── the verdict ──
    leave = []
    if lost:
        leave.append("barrels reported lost: fades lost on average when supply really went (+3.8%, +9.1% ex partial)")
    if ovx_ok is False:
        leave.append(f"OVX {ovx_last:.0f} ≥ {p['ovx_leave']:g}: spikes starting in a crude-vol panic did not come back")
    if streak >= p["higher_streak_leave"]:
        leave.append(f"closed higher {streak} sessions running: a spike that keeps closing up is a supply shock, not a threat")
    if leave:
        out["verdict"] = "leave"
        reasons.extend(leave)
        out["headline"] = "Leave crude alone: " + leave[0].split(":")[0]
        if mine:
            reasons.append(f"{len(mine)} open spread(s): the exit rules apply (stop / time / mean)")
        return out
    if not esc:
        out["verdict"] = "wait"
        reasons.append("no escalation logged for this spike: log the event and mark whether barrels were lost")
        out["headline"] = f"Crude spiked {_pct(spike['change_pct'])} on {spike['date']}: log the event before acting"
        return out
    if mine and deesc:
        first_open = min(t.get("opened") or "9999" for t in mine)
        after_open = [e for e in deesc if _ev_date(e).isoformat() > str(first_open)[:10]]
        if after_open and len(mine) <= p["max_adds"]:
            out["verdict"] = "add"
            reasons.append(f"first de-escalation after the entry ({_short(after_open[0])}): add one spread, do not initiate")
            out["headline"] = "Add to the crude fade on the de-escalation statement"
            out["trade"] = trade
            return out
    if mine:
        out["verdict"] = "wait"
        reasons.append(f"{len(mine)} spread(s) already open: one position at a time")
        out["headline"] = "Crude fade is on; managed by the exit rules"
        return out
    if not spike["down_close_since"]:
        out["verdict"] = "wait"
        reasons.append("enter after the first down close, not on the spike day")
        out["headline"] = f"Crude spiked {_pct(spike['change_pct'])} on {spike['date']}: wait for the first down close"
        return out
    if war and not deesc:
        out["verdict"] = "wait"
        reasons.append("war regime: 2026 fades lost on average (+1.6%, worst +18%); only on an explicit de-escalation")
        out["headline"] = "Threat-only spike, but the war regime is on: wait for a de-escalation statement"
        return out
    out["verdict"] = "fade"
    reasons.append("threat-only spike (no barrels lost), first down close seen: the fade won 25/37 pre-2026, mean −2.8%")
    if ovx_last is not None and ovx_last < p["ovx_better"]:
        reasons.append(f"OVX {ovx_last:.0f} < {p['ovx_better']:g}: the better cohort (17/20 reverted)")
    if deesc:
        reasons.append(f"de-escalation logged ({_short(deesc[0])}): 12/14 reverted, mean −4.6%")
    if war:
        reasons.append("war regime on, but a de-escalation was logged")
    reasons.append("experimental: the rules-based fade lost out of sample (≈ −$8 per spread); 1 spread, defined risk")
    out["headline"] = f"Fade the {_pct(spike['change_pct'])} crude spike of {spike['date']} with a USO put vertical"
    out["trade"] = trade
    return out


def evaluate_btc(btc: dict, closes_btc, events: list[dict], open_trades: list[dict], now: pd.Timestamp,
                 params: Optional[dict] = None, trade: Optional[dict] = None) -> dict:
    p = dict(BTC_PARAMS, **(params or {}))
    today = now.date()
    checklist: list[dict] = []
    reasons: list[str] = []
    s = ES.clean_closes(closes_btc)
    last = btc.get("last")
    shocks = sorted((e for e in events if e["kind"] in SHOCK_KINDS
                     and sessions_between(_ev_date(e), today) <= p["event_sessions"] and _ev_date(e) <= today),
                    key=_ev_date, reverse=True)
    pre_shock, shock = None, None
    if shocks:
        shock = shocks[0]
        before = s[[d < _ev_date_utc(shock) for d in s.index]]
        pre_shock = float(before.iloc[-1]) if len(before) else None
    checklist.append({"label": f"Risk-off event logged (≤ {p['event_sessions']} sessions)", "ok": bool(shocks),
                      "value": _short(shock) if shock else "none"})
    dip_pct = (last / pre_shock - 1) * 100 if (pre_shock and last) else None
    dip_ok = dip_pct is not None and dip_pct <= -p["dip_pct"]
    checklist.append({"label": f"BTC ≥ {p['dip_pct']:g}% below the pre-shock close", "ok": (dip_ok if dip_pct is not None else None),
                      "value": f"{_pct(dip_pct)} vs {pre_shock:,.0f}" if dip_pct is not None else "n/a"})
    chg = btc.get("change_pct")
    drop_ok = chg is not None and chg <= p["drop_24h_pct"]
    checklist.append({"label": f"or a 24-h drop ≤ {p['drop_24h_pct']:g}%", "ok": drop_ok if chg is not None else None,
                      "value": _pct(chg)})
    mine = [t for t in open_trades if t.get("playbook") == "btc_dip"]
    checklist.append({"label": "No btc_dip position open", "ok": not mine, "value": f"{len(mine)} open" if mine else "none"})
    open_day = next_nyse_open(now)
    checklist.append({"label": "Next NYSE open", "ok": None, "value": open_day.isoformat()})
    out = {"id": "btc_dip", "title": "BTC geopolitical dip", "verdict": "none", "headline": "", "reasons": reasons,
           "checklist": checklist, "trade": None, "armed": False, "experimental": True, "action": None,
           "detail": {"pre_shock": pre_shock, "dip_pct": round(dip_pct, 3) if dip_pct is not None else None,
                      "shock_event_id": shock.get("id") if shock else None, "next_open": open_day.isoformat(),
                      "open_trades": len(mine), "btc_last": last}}
    if mine:
        out["verdict"] = "wait"
        reasons.append(f"{len(mine)} IBIT position(s) open: out after 1–3 sessions, at −4%, or at the pre-shock price")
        out["headline"] = "BTC dip trade is on; managed by the exit rules"
        return out
    if dip_ok or drop_ok:
        out["verdict"], out["action"] = "fade", "buy_dip"
        why = (f"BTC {_pct(dip_pct)} under its pre-shock close after {_short(shock)}" if dip_ok
               else f"BTC {_pct(chg)} on the day")
        reasons.append(why + ": buy at the next NYSE open (+1.7% mean at 1 day [+0.1, +3.4], n = 22)")
        reasons.append("experimental: 41% still under water at 7 days; a logged experiment, not evidence")
        out["headline"] = f"Buy the BTC dip via IBIT at the {open_day.isoformat()} open"
        out["trade"] = trade
        return out
    if shocks:
        out["verdict"] = "wait"
        reasons.append(f"shock logged but BTC only {_pct(dip_pct)} vs the pre-shock close (needs ≤ −{p['dip_pct']:g}%)")
        out["headline"] = "Risk-off event logged; BTC has not dipped enough"
        return out
    out["headline"] = f"No risk-off shock: BTC {_pct(chg)} on the day, nothing logged"
    return out


def evaluate_vix(vix: dict, vix3m: Optional[dict] = None, params: Optional[dict] = None) -> dict:
    p = dict(VIX_PARAMS, **(params or {}))
    z = vix.get("z20")
    spike = z is not None and z >= p["z"]
    last, m3 = vix.get("last"), (vix3m or {}).get("last")
    ratio = (last / m3) if (last and m3) else None
    checklist = [{"label": f"VIX level z20 ≥ {p['z']:g}", "ok": spike if z is not None else None,
                  "value": f"{last} (z {z})" if z is not None else "n/a"},
                 {"label": "VIX above VIX3M (backwardation)", "ok": (ratio > 1) if ratio else None,
                  "value": f"VIX/VIX3M {ratio:.2f}" if ratio else "n/a"}]
    reasons = []
    if spike:
        reasons.append("VIX is 2σ high: note only. VIX options price off the same-expiry future, which already sits "
                       "2–6 points under spot; the fade lost −$36 per spread out of sample")
    return {"id": "vix_note", "title": "VIX spike (note only)", "verdict": "none",
            "headline": (f"VIX {last} is {z}σ above its 20-day mean: no trade (priced into the futures)" if spike
                         else f"VIX {last}: nothing to note" + (f" (z {z})" if z is not None else "")),
            "reasons": reasons, "checklist": checklist, "trade": None, "armed": False, "experimental": False,
            "detail": {"z20": z, "ratio_vix_vix3m": round(ratio, 3) if ratio else None}}


# ── the open event trades ─────────────────────────────────────────────────────

EXIT_RULES = {
    "oil_fade": "≥ 1 night; out when crude is back at its 20-day mean, after 10 sessions, or at −50% of the debit",
    "btc_dip": "≥ 1 night; out after 3 sessions, at −4%, or when BTC is back at the pre-shock price",
}


def open_event_trades(hub=None, today: Optional[_dt.date] = None) -> list[dict]:
    """The paper account's open positions under the event desk's ledger strategies, in the desk's shape."""
    from api.services import paper as P
    today = today or _dt.date.today()
    by_ledger = {v: k for k, v in LEDGER.items()}
    out = []
    table = P.positions("open", hub=hub)
    for r in table.get("rows", []):
        pb = by_ledger.get(str(r.get("strategy") or ""))
        if pb is None:
            continue
        opened = str(r.get("opened") or "")[:10] or None
        n = r.get("contracts")
        mult = 100.0 if r.get("expiry") else 1.0
        entry_net = r.get("entry_net")
        entry = (round(-float(entry_net) / (float(n) * mult), 4) if (n and entry_net is not None) else None)
        out.append({"playbook": pb, "trade_group_id": r.get("trade_group_id"), "opened": opened,
                    "description": r.get("structure") or r.get("underlying"), "underlying": r.get("underlying"),
                    "expiry": r.get("expiry"), "quantity": n, "entry": entry, "entry_net": entry_net,
                    "mark": r.get("mark"), "pnl": r.get("pnl"), "pnl_pct": r.get("pnl_pct"),
                    "days_held": sessions_between(_dt.date.fromisoformat(opened), today) if opened else None,
                    "nights_held": (today - _dt.date.fromisoformat(opened)).days if opened else None,
                    "exit_rule": EXIT_RULES.get(pb, ""), "priced_by": r.get("priced_by")})
    return out


# ── the desk ──────────────────────────────────────────────────────────────────

class ChainInputs:
    """Expirations and option mids from the hub (cached briefly); nothing without a hub provider."""

    def __init__(self, hub):
        self.hub = hub
        self._exp: dict[str, tuple[float, list]] = {}

    def spot(self, symbol: str) -> Optional[float]:
        if self.hub is None or not getattr(self.hub, "providers", None):
            return None
        try:
            return self.hub.price(symbol, wait=2.0)
        except Exception:  # noqa: BLE001
            return None

    def expirations(self, underlying: str) -> Optional[list]:
        if self.hub is None or not getattr(self.hub, "providers", None):
            return None
        import time
        got = self._exp.get(underlying)
        if got and time.monotonic() - got[0] < 3600:
            return got[1]
        try:
            from api.marketdata.options import expirations
            exps = [_dt.date.fromisoformat(str(e["expiry"])[:10]) for e in expirations(self.hub, underlying)["expirations"]]
        except Exception as exc:  # noqa: BLE001
            logger.info("%s expirations unavailable: %s", underlying, exc)
            return None
        self._exp[underlying] = (time.monotonic(), exps)
        return exps

    def mids(self, symbols: list[str]) -> dict:
        if self.hub is None or not getattr(self.hub, "providers", None) or not symbols:
            return {}
        try:
            return {q["symbol"]: q.get("mid") for q in self.hub.snapshot(symbols, wait=3.0)}
        except Exception as exc:  # noqa: BLE001
            logger.info("option mids unavailable: %s", exc)
            return {}


class EventDesk:
    def __init__(self, hub=None, store=None, signals: Optional[ES.Signals] = None,
                 clock: Optional[Callable[[], pd.Timestamp]] = None, armed: Optional[Callable[[str], bool]] = None,
                 trades: Optional[Callable[[], list]] = None, chain: Optional[ChainInputs] = None,
                 oil_params: Optional[dict] = None, btc_params: Optional[dict] = None, crypto_flush=None):
        self.hub = hub
        self.store = store if store is not None else make_store()
        self.clock = clock or now_et
        self.signals = signals or ES.Signals(clock=self.clock, live_hub=hub)
        self.armed = armed or (lambda s: False)
        self.trades = trades or (lambda: open_event_trades(hub, self.clock().date()))
        self.chain = chain or ChainInputs(hub)
        self.oil_params = dict(OIL_PARAMS, **(oil_params or {}))
        self.btc_params = dict(BTC_PARAMS, **(btc_params or {}))
        self.crypto_flush = crypto_flush

    # ── event log ─────────────────────────────────────────────────────────────
    def _need_store(self):
        if self.store is None:
            raise EventError("the event desk's store is off (ALAN_TRADER_ARMS=off)")
        return self.store

    def log_event(self, body: dict) -> dict:
        row = parse_event(body, self.clock())
        return event_view(self._need_store().add_event(row))

    def events(self, days: int = 14) -> list[dict]:
        if self.store is None:
            return []
        since = to_utc_naive(self.clock() - pd.Timedelta(days=int(days)))
        return [event_view(r) for r in self.store.events_since(since)]

    def delete_event(self, event_id: int) -> bool:
        return self._need_store().delete_event(int(event_id))

    # ── regime ────────────────────────────────────────────────────────────────
    def regime(self) -> dict:
        v = self.store.get_setting("regime") if self.store is not None else None
        if not v:
            return {"war": False, "note": None, "updated": None}
        return {"war": bool(v.get("war")), "note": v.get("note"), "updated": et_iso(v.get("updated"))}

    def set_regime(self, body: dict) -> dict:
        self._need_store().put_setting("regime", parse_regime(body))
        return self.regime()

    # ── signal log ────────────────────────────────────────────────────────────
    def signal_log(self, days: int = 90) -> list[dict]:
        if self.store is None:
            return []
        return [signal_view(r) for r in self.store.signals_since(self.clock().date() - _dt.timedelta(days=int(days)))]

    def tag_signal(self, signal_id: int, body: dict) -> Optional[dict]:
        t = parse_tag(body)
        r = self._need_store().update_signal(int(signal_id), tag=t["tag"], note=t["note"],
                                             tagged_at=_utcnow() if t["tag"] is not None else None)
        return signal_view(r) if r else None

    def decisions(self, days: int = 30, playbook: Optional[str] = None) -> list[dict]:
        if self.store is None:
            return []
        rows = self.store.decisions_since(self.clock().date() - _dt.timedelta(days=int(days)), playbook)
        return [dict(r, decided_at=et_iso(r.get("decided_at"))) for r in rows]

    # ── evaluation ────────────────────────────────────────────────────────────
    def context(self, force: bool = False) -> dict:
        now = self.clock()
        sig = self.signals.snapshot(ES.KEYS, force=force)
        closes = {k: self.signals.closes(k) for k in ("CL", "BTC")}
        try:
            trades = self.trades()
        except Exception as exc:  # noqa: BLE001
            logger.warning("open event trades unavailable: %s", exc)
            trades = []
        raw_events = self.store.events_since(to_utc_naive(now - pd.Timedelta(days=14))) if self.store is not None else []
        return {"now": now, "signals": sig, "closes": closes, "events": raw_events, "trades": trades,
                "regime": self.regime()}

    def _oil_trade(self, ctx: dict, want: bool) -> Optional[dict]:
        if not want:
            return None
        p = self.oil_params
        uso = ctx["signals"]["USO"]
        spot = uso.get("last") or self.chain.spot("USO")
        t = suggest_vertical("put", "USO", spot, ctx["now"].date(), self.chain.expirations("USO"), p["short_pct"],
                             p["dte_min"], p["dte_max"], p["dte_target"], p["strike_step"], None, p["spreads"],
                             EXIT_RULES["oil_fade"])
        if t is not None:
            mids = self.chain.mids([l["symbol"] for l in t["order_legs"]])
            if mids:
                t = suggest_vertical("put", "USO", spot, ctx["now"].date(), self.chain.expirations("USO"), p["short_pct"],
                                     p["dte_min"], p["dte_max"], p["dte_target"], p["strike_step"], mids, p["spreads"],
                                     EXIT_RULES["oil_fade"])
        return t

    def _btc_trade(self, ctx: dict, want: bool) -> Optional[dict]:
        if not want:
            return None
        p = self.btc_params
        ibit = ctx["signals"]["IBIT"]
        spot = ibit.get("last") or self.chain.spot("IBIT")
        if p.get("vehicle") == "call_vertical":
            t = suggest_vertical("call", "IBIT", spot, ctx["now"].date(), self.chain.expirations("IBIT"), p["short_pct"],
                                 p["dte_min"], p["dte_max"], p["dte_target"], p["strike_step"], None, 1, EXIT_RULES["btc_dip"])
            if t is not None:
                mids = self.chain.mids([l["symbol"] for l in t["order_legs"]])
                if mids:
                    t = suggest_vertical("call", "IBIT", spot, ctx["now"].date(), self.chain.expirations("IBIT"), p["short_pct"],
                                         p["dte_min"], p["dte_max"], p["dte_target"], p["strike_step"], mids, 1,
                                         EXIT_RULES["btc_dip"])
            return t
        if not spot:
            return None
        shares = int(math.floor(p["dollars"] / spot))
        return {"structure": "IBIT shares", "underlying": "IBIT", "legs": f"+{shares} IBIT", "expiry": None,
                "quantity": shares, "est_debit": round(spot, 2), "max_loss": round(shares * spot, 2), "max_profit": None,
                "order_legs": [{"type": "stock", "side": "buy", "quantity": shares}], "hold_rule": EXIT_RULES["btc_dip"]}

    def playbook(self, pid: str, ctx: Optional[dict] = None) -> dict:
        ctx = ctx or self.context()
        s, now = ctx["signals"], ctx["now"]
        if pid == "oil_fade":
            dry = evaluate_crude(s["CL"], ctx["closes"]["CL"], s["OVX"].get("last"), ctx["events"], ctx["regime"]["war"],
                                 ctx["trades"], now.date(), self.oil_params)
            trade = self._oil_trade(ctx, dry["verdict"] in ("fade", "add"))
            pb = evaluate_crude(s["CL"], ctx["closes"]["CL"], s["OVX"].get("last"), ctx["events"], ctx["regime"]["war"],
                                ctx["trades"], now.date(), self.oil_params, trade)
        elif pid == "btc_dip":
            dry = evaluate_btc(s["BTC"], ctx["closes"]["BTC"], ctx["events"], ctx["trades"], now, self.btc_params)
            trade = self._btc_trade(ctx, dry["verdict"] == "fade")
            pb = evaluate_btc(s["BTC"], ctx["closes"]["BTC"], ctx["events"], ctx["trades"], now, self.btc_params, trade)
        elif pid == "vix_note":
            pb = evaluate_vix(s["VIX"], s["VIX3M"])
        elif pid == "crypto_flush":
            if self.crypto_flush is None:
                return {"id": "crypto_flush", "title": "Crypto liquidation flush", "verdict": "none",
                        "headline": "crypto_flush poller is not running in this service", "reasons": [], "checklist": [],
                        "trade": None, "armed": False, "experimental": False}
            pb = self.crypto_flush.playbook(now)
        else:
            raise EventError(f"unknown playbook {pid!r}; one of {', '.join(PLAYBOOKS)}")
        pb["armed"] = bool(self.armed(pid))
        return pb

    def desk(self) -> dict:
        from api.serialize import to_jsonable
        ctx = self.context()
        warnings = []
        for k in ES.KEYS:
            warnings += [f"{k}: {w}" for w in ctx["signals"][k].get("warnings") or []]
        playbooks = []
        for pid in PLAYBOOKS:
            try:
                playbooks.append(self.playbook(pid, ctx))
            except Exception as exc:  # noqa: BLE001 — one broken playbook must not hide the others
                logger.exception("playbook %s failed", pid)
                playbooks.append({"id": pid, "title": pid, "verdict": "none", "headline": f"failed: {type(exc).__name__}: {exc}"[:200],
                                  "reasons": [], "checklist": [], "trade": None, "armed": bool(self.armed(pid)),
                                  "experimental": pid in ("oil_fade", "btc_dip")})
        signal_rows = self.signal_log(400)[:20]
        return to_jsonable({
            "as_of": ctx["now"].isoformat(timespec="seconds"),
            "regime": ctx["regime"],
            "signals": [ctx["signals"][k] for k in ES.KEYS],
            "playbooks": playbooks,
            "open_trades": ctx["trades"],
            "events": [event_view(r) for r in ctx["events"]],
            "signal_log": signal_rows,
            "crypto_flush": self.crypto_flush.status() if self.crypto_flush is not None else None,
            "params": {"oil_fade": self.oil_params, "btc_dip": self.btc_params, "vix_note": VIX_PARAMS,
                       "signal_log": {k: {"field": f, "threshold": t, "test": h} for k, (f, t, h) in SIGNAL_LOG_RULES.items()}},
            "warnings": warnings,
        })


# ── the signal log ────────────────────────────────────────────────────────────

def signal_view(r: dict) -> dict:
    d = {k: r.get(k) for k in SIGNAL_COLS}
    d["date"] = d["date"].isoformat() if isinstance(d["date"], _dt.date) else d["date"]
    d["outcome_asof"] = d["outcome_asof"].isoformat() if isinstance(d["outcome_asof"], _dt.date) else d["outcome_asof"]
    d["tagged_at"], d["created"] = et_iso(d.get("tagged_at")), et_iso(d.get("created"))
    d["complete"] = d.get("r20") is not None
    return d


def signal_candidates(signals: dict, day: _dt.date, rules: Optional[dict] = None) -> list[dict]:
    """The rows the day's closes earn: USO |move z| ≥ 2, VIX level z ≥ 2, BTC change ≤ −3% (each row carries the
    USO move, VIX / OVX and the 20-day baselines)."""
    rules = rules or SIGNAL_LOG_RULES
    vix, ovx = signals.get("VIX") or {}, signals.get("OVX") or {}
    out = []
    for sym, (field, thr, how) in rules.items():
        s = signals.get(sym) or {}
        v = s.get(field)
        # BTC never closes: its UTC day is still open at 16:15 ET, so the day's partial (its ``last``) is scored and
        # the outcome back-fill later reads the UTC close for the day
        partial = (sym in ES.ALWAYS_OPEN and "partial" in str(s.get("mark_source") or "")
                   and s.get("close_date") != day.isoformat())
        if v is None or (s.get("close_date") != day.isoformat() and not partial):
            continue
        hit = (abs(v) >= thr) if how == "abs" else (v >= thr if how == "ge" else v <= thr)
        if not hit:
            continue
        out.append({"date": day, "symbol": sym, "close": s.get("last") if partial else s.get("close"), "change_pct": s.get("change_pct"),
                    "move_z": s.get("move_z20"), "level_z": s.get("z20"), "mean20": s.get("mean20"), "sd20": s.get("sd20_pct"),
                    "vix": vix.get("close"), "vix_change_pct": vix.get("change_pct"), "ovx": ovx.get("close")})
    return out


def outcome(closes, day: _dt.date, horizons=(3, 10, 20)) -> dict:
    """What the closes did after ``day``: r3 / r10 / r20 (% from the day's close, null until observed),
    half_back (half of the day's move given back within 20 sessions: true / false / null while pending) and
    half_back_days (the first session it happened)."""
    s = ES.clean_closes(closes)
    dates = list(s.index)
    if day not in dates:
        return {}
    i = dates.index(day)
    c = s.values
    out = {"outcome_asof": dates[-1]}
    c0 = float(c[i])
    for h in horizons:
        out[f"r{h}"] = round((float(c[i + h]) / c0 - 1) * 100, 3) if i + h < len(c) else None
    if i == 0:
        out.update(half_back=None, half_back_days=None)
        return out
    move = c0 - float(c[i - 1])
    half = c0 - 0.5 * move
    after = c[i + 1:i + 21]
    hit = None
    for k, v in enumerate(after, start=1):
        if (move > 0 and v <= half) or (move < 0 and v >= half):
            hit = k
            break
    out["half_back_days"] = hit
    out["half_back"] = True if hit is not None else (False if len(after) >= 20 else None)
    return out


class SignalLogJob:
    """Armed like an allocator (``event_signal_log`` at 16:15 ET): records the day's signal rows and back-fills
    the outcomes of the rows still pending."""

    def __init__(self, desk: EventDesk, store=None, publish: Optional[Callable[[dict], None]] = None,
                 clock: Optional[Callable[[], pd.Timestamp]] = None):
        self.desk = desk
        self.store = store if store is not None else desk.store
        self.publish = publish
        self.clock = clock or desk.clock
        self._lock = threading.Lock()

    def run(self, variant: str = "", now: Optional[pd.Timestamp] = None) -> dict:
        if self.store is None:
            raise RuntimeError("the event desk's store is off (ALAN_TRADER_ARMS=off)")
        now = now or self.clock()
        day = now.date()
        with self._lock:
            sig = self.desk.signals.snapshot(ES.KEYS, force=True, live=False)   # closes only: the session is over
            added, dup = [], []
            for row in signal_candidates(sig, day):
                r = self.store.add_signal(row)
                (added if r else dup).append(row["symbol"])
            filled = self.backfill()
            summary = (f"{day}: " + (f"logged {', '.join(added)}" if added else "no signal") +
                       (f"; already logged {', '.join(dup)}" if dup else "") + f"; back-filled {filled}")
            res = {"date": day, "status": "ran", "logged": added, "already": dup, "backfilled": filled, "summary": summary,
                   "signals": {k: {f: sig[k].get(f) for f in ("close", "change_pct", "move_z20", "z20")} for k in SIGNAL_LOG_RULES}}
        logger.info("event signal log %s", summary)
        if self.publish is not None:
            try:
                from api.serialize import to_jsonable
                self.publish(to_jsonable({"type": "event_signal_log", **res}))
            except Exception:
                logger.debug("signal log publish failed", exc_info=True)
        return res

    def backfill(self) -> int:
        n = 0
        closes_cache: dict[str, pd.Series] = {}
        for r in self.store.pending_signals():
            sym = r["symbol"]
            if sym not in closes_cache:
                try:
                    closes_cache[sym] = self.desk.signals.closes(sym)
                except Exception as exc:  # noqa: BLE001
                    logger.info("no closes to back-fill %s: %s", sym, exc)
                    closes_cache[sym] = pd.Series(dtype=float)
            o = outcome(closes_cache[sym], r["date"])
            if not o:
                continue
            changed = {k: v for k, v in o.items() if k != "outcome_asof" and v is not None and v != r.get(k)}
            if changed:
                self.store.update_signal(r["id"], **o)
                n += 1
        return n

    def status(self, variant: str = "") -> dict:
        rows = self.store.signals_since(self.clock().date() - _dt.timedelta(days=400)) if self.store is not None else []
        return {"rows": len(rows), "pending": sum(1 for r in rows if r.get("r20") is None),
                "untagged": sum(1 for r in rows if not r.get("tag")),
                "last": signal_view(rows[0]) if rows else None}

    def log(self, days: int = 30) -> dict:
        return {"days": int(days), "rows": self.desk.signal_log(days)}
