"""The live loop's optional per-poll hook (strategy_api.live: ``on_poll``, ``watch_structures``,
``max_fills_per_session``) and the legs' prints on a vertical quote. Offline: a scripted clock, a stub provider
and a stub strategy; no broker, no database, no plugin. An engine without the hooks must see the loop exactly as
before: one ``on_bar`` per minute and nothing else."""
from __future__ import annotations

from datetime import date, datetime, time as dtime, timedelta

import pandas as pd
import pytest

from paper.providers import Bar, LegQuote, vertical_quote
from strategy_api.live import Quote

DAY = date(2026, 9, 24)
NOW = datetime(2026, 9, 24, 13, 30)


def _leg(sym, bid, ask, last=None, last_age_min=0):
    return LegQuote(sym, bid, ask, last, (NOW - timedelta(minutes=last_age_min)) if last is not None else None, NOW)


def test_a_vertical_quote_carries_each_legs_last_print_and_a_plain_quote_has_none():
    q = vertical_quote(_leg("L", 170, 172, 171.0, 1), _leg("S", 108, 110, 109.5, 0), NOW)
    assert q is not None and q.bid == 60 and q.ask == 64 and q.legs == ((170.0, 172.0, 1), (108.0, 110.0, 0))
    assert q.prints == ((171.0, NOW - timedelta(minutes=1)), (109.5, NOW))
    q2 = vertical_quote(_leg("L", 170, 172), _leg("S", 108, 110), NOW)          # no trade reported: None entries
    assert q2 is not None and q2.prints == ((None, None), (None, None))
    assert Quote(1.0, 2.0, 1.5).prints is None and Quote(1.0, 2.0, 1.5, 0).legs is None


# ── stubs ─────────────────────────────────────────────────────────────────────

class _Prov:
    name = "fake-live"
    underlying = "NDX"
    root = "NDXP"
    poll_seconds = 20
    expiry = DAY

    def __init__(self, clock):
        self.clock = clock
        self._samples = []
        self.fetches: list[list[str]] = []

    def load_chain(self, day):
        return 64

    def leg_symbols(self, kind, k_low, k_high):
        cp = "C" if kind == "call" else "P"
        return f"NDXP260924{cp}{int(k_low):08d}", f"NDXP260924{cp}{int(k_high):08d}"

    def fetch(self, syms):
        self.fetches.append(list(syms))
        now = self.clock()
        out = {"NDX": LegQuote("NDX", None, None, 29100.0, now, now)}
        for s in syms:
            out[s] = LegQuote(s, 10.0, 12.0, 11.0, now, now)
        return out

    def sample_underlying(self, quotes, when):
        self._samples.append((when, 29100.0)); return 29100.0

    def close_minute(self, minute_start):
        return Bar(minute_start, 29100.0, 29100.0, 29100.0, 29100.0)

    def quote_vertical(self, kind, k_low, k_high, quotes, now, carry_min=30):
        return Quote(bid=1.0, ask=3.0, last=2.0, age=0)


class _Params:
    lookback_min = 0
    target_pts = 5.0
    entry_start_min = 24 * 60          # never reached: no `features` row in the log, only the engine's own events

    def as_dict(self):
        return {}


class _Engine:
    """A minimal LiveSession: counts bars."""

    def __init__(self, blocked_reason=""):
        self.fills, self.trades, self.positions, self.closes = [], [], [], []
        self.pending = None
        self.blocked_reason = blocked_reason
        self.last_minute = 0
        self.bars = 0

    def on_bar(self, minute, S, quote_fn, is_last=False, high=None, low=None):
        self.closes.append(S); self.last_minute = minute; self.bars += 1

    @property
    def day_pnl(self):
        return 0.0

    def marked(self):
        return 0.0

    def to_dict(self):
        return {"bars": self.bars}


class _PollEngine(_Engine):
    """... and works resting orders on every poll: fills on the third poll, asks for one more structure's legs."""
    max_fills_per_session = 5

    def __init__(self, fills_per_poll=0, **kw):
        super().__init__(**kw)
        self.polls: list = []
        self.fills_per_poll = fills_per_poll

    def on_poll(self, now, spot, quote_fn):
        q = quote_fn(spot, 29100.0, 29200.0, "call", now.hour * 60 + now.minute)
        self.polls.append((now, spot, q))
        if len(self.polls) == 3:
            self.fills.append(dict(m=now.hour * 60 + now.minute, kind="open", direction="bull", kl=29100.0, kh=29200.0,
                                   px=2.0, lots=1, cash=-202.0, reason=f"poll fill at {now:%H:%M:%S}"))
        for _ in range(self.fills_per_poll):
            self.fills.append(dict(m=now.hour * 60 + now.minute, kind="rest", direction="bull", kl=29100.0, kh=29200.0,
                                   px=2.0, lots=1, cash=0.0, reason="rest"))

    def watch_structures(self):
        return [("put", 29100.0, 29200.0)]


class _Strategy:
    def __init__(self, engine_cls=_Engine, **kw):
        self.params = _Params()
        self.engine_cls = engine_cls
        self.kw = kw
        self.session = None

    def live_instrument(self):
        return {"underlying": "NDX", "root": "NDXP"}

    def session_gate(self, day, events=None):
        return False, ""

    def live_session(self, day, blocked_reason="", bar_min=1):
        self.session = self.engine_cls(blocked_reason=blocked_reason, **self.kw)
        return self.session


def _run(tmp_path, monkeypatch, strategy, minutes=4):
    from paper import runner as RU
    monkeypatch.setattr(RU.R, "get_strategy", lambda slug: strategy)
    monkeypatch.setattr(RU.R, "find_guide", lambda slug: None)
    monkeypatch.setattr(RU.R, "tests_dir_for", lambda slug: None)
    t = [datetime.combine(DAY, dtime(9, 30, 5))]

    def now_fn():
        return t[0]

    def sleep_fn(sec):
        t[0] = t[0] + timedelta(seconds=20)

    prov = _Prov(now_fn)
    ps = RU.PaperSession("stub", prov, None, write_ledger=False, log_dir=tmp_path / "log", state_dir=tmp_path / "state")
    res = ps.run_live(day=DAY, poll_seconds=20, until=dtime(9, 30 + minutes), now_fn=now_fn, sleep_fn=sleep_fn)
    return ps, prov, res


def test_an_engine_without_the_hooks_sees_the_loop_as_before(tmp_path, monkeypatch):
    strat = _Strategy(_Engine)
    ps, prov, res = _run(tmp_path, monkeypatch, strat)
    eng = strat.session
    assert eng.bars == res.bars >= 3 and not eng.fills and ps.halted is None
    assert all(f == [] for f in prov.fetches)                     # nothing open, nothing pending: only the underlying
    assert not (tmp_path / "log" / f"{DAY.isoformat()}.csv").exists()


def test_on_poll_runs_every_poll_with_the_quotes_and_its_fills_are_logged_and_saved(tmp_path, monkeypatch):
    strat = _Strategy(_PollEngine)
    ps, prov, res = _run(tmp_path, monkeypatch, strat)
    eng = strat.session
    assert ps.halted is None and eng.bars >= 3
    # three polls a minute, every one of them seen by the engine, with the spot and a quote in hand
    assert len(eng.polls) > eng.bars * 2
    assert all(spot == 29100.0 and q is not None and q.bid == 1.0 for _, spot, q in eng.polls)
    # the extra structure's legs were fetched with everything else, once each
    assert any("NDXP260924P00029100" in f and "NDXP260924P00029200" in f for f in prov.fetches)
    assert all(len(f) == len(set(f)) for f in prov.fetches)
    # the poll's fill went to the CSV log and the state, between bar closes
    log = pd.read_csv(tmp_path / "log" / f"{DAY.isoformat()}.csv")
    assert list(log.event) == ["open"] and log.reason.iloc[0].startswith("poll fill at 09:3")
    assert (tmp_path / "state" / f"stub_{DAY.isoformat()}.json").exists() and res.n_fills_written == 1
    assert len(res.fills) == 1


def test_the_engines_own_fill_ceiling_replaces_the_runaway_guard(tmp_path, monkeypatch):
    strat = _Strategy(_PollEngine, fills_per_poll=1)              # a rest row every poll: past 5 within two minutes
    ps, prov, res = _run(tmp_path, monkeypatch, strat)
    assert ps.halted and ps.halted.startswith("runaway guard") and len(strat.session.fills) == 6


def test_an_engine_error_in_on_poll_halts_the_session(tmp_path, monkeypatch):
    class Bad(_PollEngine):
        def on_poll(self, now, spot, quote_fn):
            raise RuntimeError("boom")
    strat = _Strategy(Bad)
    ps, prov, res = _run(tmp_path, monkeypatch, strat)
    assert ps.halted and "boom" in ps.halted and "(poll)" in ps.halted
