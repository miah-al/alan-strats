"""The supervisor's controls (paper/supervisor.py; from 2026-09-30 Claude supervises the armed strategies and may only
take risk off): which controls are in force, how the live loop hands them to an engine's ``supervise`` / ``flatten``
hooks, and how they sit among the trader's limits. Offline: a scripted clock, a stub provider and stub engines."""
from __future__ import annotations

import datetime as dt
from datetime import date, datetime, time as dtime, timedelta

import pandas as pd

from api.services import limits as LIM
from paper import supervisor as SUP
from paper.providers import Bar, LegQuote
from strategy_api.live import Quote

DAY = date(2026, 9, 30)


def utc(h, m, day=DAY):
    """A stored UpdatedAt (UTC, naive) for h:m New York time on ``day`` (EDT: +4 hours)."""
    return datetime.combine(day, dtime(h, m)) + timedelta(hours=4)


# ── which controls are in force ────────────────────────────────────────────────

def test_nothing_stored_leaves_the_rules_in_charge():
    c = SUP.effective({}, DAY)
    assert c.entries and c.adds and c.close_at is None and c.reason == ""


def test_todays_controls_count_and_earlier_days_do_not():
    rows = {"sup_entries": {"value": 0, "at": utc(12, 40), "reason": "FOMC at 14:00"},
            "sup_adds": {"value": 0, "at": utc(15, 0, DAY - timedelta(days=1)), "reason": "yesterday's trend"},
            "sup_close": {"value": 1759250000, "at": utc(12, 41), "reason": "cut before the Fed"}}
    c = SUP.effective(rows, DAY)
    assert c.entries is False and c.adds is True                       # yesterday's "no adds" has lapsed
    assert c.close_at == datetime.combine(DAY, dtime(12, 41)) and c.reason == "cut before the Fed"
    assert SUP.effective(rows, DAY + timedelta(days=1)) == SUP.Controls()


def test_read_controls_without_a_database_is_empty():
    assert SUP.read_controls(None, "ndx_0dte_friend") == {}


# ── the live loop ───────────────────────────────────────────────────────────────

class _Prov:
    name = "fake-live"
    underlying = "NDX"
    root = "NDXP"
    poll_seconds = 20
    expiry = DAY

    def __init__(self, clock):
        self.clock = clock

    def load_chain(self, day):
        return 64

    def leg_symbols(self, kind, k_low, k_high):
        cp = "C" if kind == "call" else "P"
        return f"NDXP260930{cp}{int(k_low):08d}", f"NDXP260930{cp}{int(k_high):08d}"

    def fetch(self, syms):
        now = self.clock()
        out = {"NDX": LegQuote("NDX", None, None, 30300.0, now, now)}
        for s in syms:
            out[s] = LegQuote(s, 10.0, 12.0, 11.0, now, now)
        return out

    def sample_underlying(self, quotes, when):
        return 30300.0

    def close_minute(self, minute_start):
        return Bar(minute_start, 30300.0, 30300.0, 30300.0, 30300.0)

    def quote_vertical(self, kind, k_low, k_high, quotes, now, carry_min=30):
        return Quote(bid=40.0, ask=44.0, last=42.0, age=0)


class _Params:
    lookback_min = 0
    entry_start_min = 24 * 60

    def as_dict(self):
        return {}


class _Pos:
    direction, kind, k_low, k_high, units, avg_px, last_mark = "bull", "call", 30250.0, 30350.0, 1, 50.0, None


class _Engine:
    """Holds one bull call spread from the start; counts bars."""

    def __init__(self, blocked_reason=""):
        self.fills, self.trades, self.closes = [], [], []
        self.positions = [_Pos()]
        self.pending = None
        self.blocked_reason = blocked_reason
        self.last_minute = 0
        self.bars = 0

    def on_bar(self, minute, S, quote_fn, is_last=False, high=None, low=None):
        self.closes.append(S); self.last_minute = minute; self.bars += 1

    @property
    def day_pnl(self):
        return float(sum(t["pnl"] for t in self.trades))

    def marked(self):
        return 0.0

    def to_dict(self):
        return {"bars": self.bars}


class _SupEngine(_Engine):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.sup_calls: list = []
        self.flattens: list = []

    def supervise(self, entries, adds, reason=""):
        self.sup_calls.append((entries, adds, reason))

    def flatten(self, minute, S, quote_fn, reason="supervisor"):
        n = 0
        for pos in list(self.positions):
            q = quote_fn(S, pos.k_low, pos.k_high, pos.kind, minute)
            self.fills.append(dict(m=minute, kind="close", direction=pos.direction, kl=pos.k_low, kh=pos.k_high,
                                   px=q.last, lots=1, cash=q.last * 100, reason=reason))
            self.trades.append({"pnl": (q.last - pos.avg_px) * 100})
            self.positions.remove(pos); n += 1
        self.flattens.append((minute, S, reason, n))
        return n


class _Strategy:
    def __init__(self, engine_cls):
        self.params = _Params()
        self.engine_cls = engine_cls
        self.session = None

    def live_instrument(self):
        return {"underlying": "NDX", "root": "NDXP"}

    def session_gate(self, day, events=None):
        return False, ""

    def live_session(self, day, blocked_reason="", bar_min=1):
        self.session = self.engine_cls(blocked_reason=blocked_reason)
        return self.session


def _run(tmp_path, monkeypatch, strategy, controls_fn, minutes=4, start=dtime(12, 40, 5)):
    from paper import runner as RU
    monkeypatch.setattr(RU.R, "get_strategy", lambda slug: strategy)
    monkeypatch.setattr(RU.R, "find_guide", lambda slug: None)
    monkeypatch.setattr(RU.R, "tests_dir_for", lambda slug: None)
    t = [datetime.combine(DAY, start)]

    def now_fn():
        return t[0]

    def sleep_fn(sec):
        t[0] = t[0] + timedelta(seconds=20)

    alerts: list = []
    ps = RU.PaperSession("stub", _Prov(now_fn), None, write_ledger=False, log_dir=tmp_path / "log",
                         state_dir=tmp_path / "state", controls_fn=lambda slug: controls_fn(now_fn()))
    monkeypatch.setattr(ps, "_alert", lambda text: alerts.append(text))
    until = (datetime.combine(DAY, start) + timedelta(minutes=minutes)).time()
    res = ps.run_live(day=DAY, poll_seconds=20, until=until, now_fn=now_fn, sleep_fn=sleep_fn)
    return ps, res, alerts


def _controls(entries_off_at=None, close_at=None):
    """A store as the clock moves: entries off from ``entries_off_at``, a close request made at ``close_at`` (ET)."""
    def fn(now):
        rows = {}
        if entries_off_at and now.time() >= entries_off_at:
            rows["sup_entries"] = {"value": 0, "at": utc(entries_off_at.hour, entries_off_at.minute), "reason": "FOMC at 14:00"}
        if close_at and now.time() >= close_at:
            rows["sup_close"] = {"value": 1, "at": utc(close_at.hour, close_at.minute), "reason": "trend day, cut it"}
        return rows
    return fn


def test_controls_reach_the_engine_once_and_a_close_request_flattens_once(tmp_path, monkeypatch):
    strat = _Strategy(_SupEngine)
    ps, res, alerts = _run(tmp_path, monkeypatch, strat, _controls(entries_off_at=dtime(12, 41), close_at=dtime(12, 42)))
    eng = strat.session
    assert ps.halted is None and eng.bars >= 3
    assert eng.sup_calls == [(False, True, "FOMC at 14:00")]             # handed over when it changed, not every poll
    assert len(eng.flattens) == 1 and eng.flattens[0][2] == "supervisor" and eng.flattens[0][3] == 1
    assert eng.flattens[0][1] == 30300.0 and not eng.positions
    log = pd.read_csv(tmp_path / "log" / f"{DAY.isoformat()}.csv")      # the close went to the log like any fill
    assert list(log.event) == ["close"] and log.reason.iloc[0] == "supervisor"
    assert (tmp_path / "state" / f"stub_{DAY.isoformat()}.json").exists()
    assert any("entries OFF" in a for a in alerts) and any("close" in a and "supervisor" in a for a in alerts)


def test_a_close_requested_before_the_run_started_is_not_acted_on(tmp_path, monkeypatch):
    strat = _Strategy(_SupEngine)
    ps, res, _ = _run(tmp_path, monkeypatch, strat, _controls(close_at=dtime(12, 30)))
    assert strat.session.flattens == [] and strat.session.positions


def test_an_engine_without_the_hooks_is_left_alone_and_the_runner_says_so_once(tmp_path, monkeypatch):
    strat = _Strategy(_Engine)
    ps, res, alerts = _run(tmp_path, monkeypatch, strat, _controls(entries_off_at=dtime(12, 41), close_at=dtime(12, 42)))
    assert ps.halted is None and strat.session.bars >= 3 and strat.session.positions
    assert sum("cannot be supervised" in a for a in alerts) == 1


def test_unreadable_controls_leave_the_rules_in_charge(tmp_path, monkeypatch):
    def broken(now):
        raise RuntimeError("database away")
    strat = _Strategy(_SupEngine)
    ps, res, _ = _run(tmp_path, monkeypatch, strat, broken)
    assert ps.halted is None and strat.session.bars >= 3 and strat.session.sup_calls == [] and strat.session.positions


# ── among the trader's limits ────────────────────────────────────────────────

def _limits():
    specs = [{"key": "daily_loss_cap", "label": "Daily loss cap", "type": "slider", "min": 0, "max": 20000, "default": 5000}]
    return LIM.Limits(LIM.MemoryLimitStore(), strategies=lambda: ["demo_strategy"], specs_for=lambda slug: specs)


def test_every_strategy_scope_carries_the_controls_and_they_apply_now():
    cat = {l["name"]: l for l in _limits().catalogue("demo_strategy")}
    assert {"sup_entries", "sup_adds", "sup_close"} <= set(cat) and cat["sup_entries"]["applies"] == "now"
    assert not any(l["name"].startswith("sup_") for l in _limits().catalogue("claude_discretionary"))


def test_setting_a_control_is_validated_logged_and_never_a_launch_param():
    lim = _limits()
    row = lim.set("demo_strategy", "sup_entries", 0, by="claude", reason="FOMC at 14:00")
    assert row["value"] == 0 and row["updated_by"] == "claude" and row["is_default"] is False
    lim.set("demo_strategy", "daily_loss_cap", 4000, by="user")
    assert lim.overrides("demo_strategy") == {"daily_loss_cap": 4000}      # no --param sup_entries=0 at launch
    assert lim.table()["changes"][1]["reason"] == "FOMC at 14:00"
    for scope, name, value in (("demo_strategy", "sup_entries", 2), ("claude_discretionary", "sup_close", 1)):
        try:
            lim.set(scope, name, value)
        except LIM.LimitError:
            continue
        raise AssertionError(f"{scope}.{name}={value} was accepted")


def test_a_control_set_on_an_earlier_day_shows_as_the_default():
    lim = _limits()
    lim.set("demo_strategy", "sup_adds", 0, by="claude", reason="trend day")
    k = ("demo_strategy", "sup_adds")
    lim.store.values[k]["updated_at"] = lim.store.values[k]["updated_at"] - dt.timedelta(days=1)
    assert lim.values("demo_strategy")["sup_adds"] == 1
    row = next(r for r in lim.table()["scopes"] if r["scope"] == "demo_strategy")
    assert next(l for l in row["limits"] if l["name"] == "sup_adds")["is_default"] is True
