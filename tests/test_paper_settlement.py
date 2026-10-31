"""A day's PM-settled index options settle on the index's official close, not on the last poll before 16:00.
2026-10-05: the 15:59 bar closed at 31,058.25, NDX's official close was 31,076.44 (recorded from 16:00:14), and the
runner settled a 31025/31075 put spread at 16.75 instead of 0 (-593 booked, -5,618 real). Offline: a scripted clock,
stub providers and a stub engine; no broker, no database, no plugin."""
from __future__ import annotations

from datetime import date, datetime, time as dtime, timedelta
from types import SimpleNamespace

import pandas as pd

from paper.providers import Bar, LegQuote, QuoteReplayProvider
from strategy_api.live import Quote

DAY = date(2026, 10, 5)


def _clock(start: dtime):
    t = [datetime.combine(DAY, start)]

    def now_fn():
        return t[0]

    def sleep_fn(sec):
        t[0] = t[0] + timedelta(seconds=sec)
    return t, now_fn, sleep_fn


class _Index:
    """``index_last`` by the clock: the 15:59:59 print, then the official close from 16:00:14."""

    def __init__(self, now_fn, path):
        self.now_fn = now_fn
        self.path = path              # [(from time, level)], the last entry at or before now applies
        self.reads: list[tuple[datetime, float]] = []

    def index_last(self):
        now = self.now_fn()
        px = None
        for at, level in self.path:
            if now.time() >= at:
                px = level
        self.reads.append((now, px))
        return px


CLOSE_PATH = [(dtime(15, 59, 59), 31078.13), (dtime(16, 0, 14), 31076.44)]


def test_the_settlement_waits_for_a_steady_reading_after_the_close():
    from paper.runner import settlement_spot
    _, now_fn, sleep_fn = _clock(dtime(16, 0, 7))          # the final bar is processed on the first poll after 16:00
    prov = _Index(now_fn, CLOSE_PATH)
    px, source = settlement_spot(prov, 31058.25, now_fn, sleep_fn)
    assert px == 31076.44 and source == "the official close"
    assert prov.reads[0][0].time() >= dtime(16, 0, 10)      # nothing read before the close could be published
    assert now_fn().time() < dtime(16, 1)                   # settled within the minute


def test_no_steady_reading_takes_the_latest_at_the_deadline_and_no_reading_the_last_bar():
    from paper.runner import SETTLE_DEADLINE, settlement_spot
    _, now_fn, sleep_fn = _clock(dtime(16, 0, 7))
    ticking = SimpleNamespace(n=0)

    def index_last():
        ticking.n += 1
        return 31070.0 + ticking.n                          # never the same twice
    px, source = settlement_spot(SimpleNamespace(index_last=index_last), 31058.25, now_fn, sleep_fn)
    assert source.startswith("the index level at the deadline") and px == 31070.0 + ticking.n
    assert now_fn().time() >= SETTLE_DEADLINE

    _, now_fn, sleep_fn = _clock(dtime(16, 0, 7))

    def down():
        raise RuntimeError("feed down")
    px, source = settlement_spot(SimpleNamespace(index_last=down), 31058.25, now_fn, sleep_fn)
    assert px == 31058.25 and source.startswith("the last bar")
    # a provider that cannot read the index (the print replay) keeps the last bar, without waiting
    _, now_fn, sleep_fn = _clock(dtime(16, 0, 7))
    assert settlement_spot(SimpleNamespace(), 31058.25, now_fn, sleep_fn) == (31058.25, "the last bar")
    assert now_fn().time() == dtime(16, 0, 7)


def _recorded(levels: list[tuple[str, float]]) -> pd.DataFrame:
    rows = []
    for ts, level in levels:
        rows.append(dict(ts=f"2026-10-05T{ts}-04:00", underlying=level, symbol="NDXP  261005P31075000", right="P",
                         strike=31075.0, bid=1.0, ask=1.2, bid_size=1, ask_size=1, last=1.1, volume=10,
                         quote_time=f"2026-10-05T{ts}-04:00"))
    return pd.DataFrame(rows)


def test_the_quote_replay_settles_on_the_level_recorded_after_the_close():
    frame = _recorded([("15:59:44", 31065.31), ("15:59:59", 31078.13), ("16:00:14", 31076.44), ("16:00:59", 31076.44)])
    prov = QuoteReplayProvider(DAY, frame=frame)
    assert prov.settle_close == 31076.44
    assert list(prov.bars.close) == [31078.13] and prov.bars.ts.iloc[-1].time() == dtime(15, 59)   # bars stop at 15:59
    from paper.runner import settlement_spot
    assert settlement_spot(prov, 31078.13) == (31076.44, "the recorded close")
    # a recording that stopped at the close has nothing to settle on but the last bar
    early = QuoteReplayProvider(DAY, frame=_recorded([("15:59:44", 31065.31), ("15:59:59", 31078.13)]))
    assert early.settle_close is None


# ── the live loop, end to end ─────────────────────────────────────────────────

class _Prov:
    """The broker as the runner sees it: the index polls 31,058.25 through 15:59, then the close is published."""
    name = "fake-live"
    underlying = "NDX"
    root = "NDXP"
    poll_seconds = 15
    expiry = DAY

    def __init__(self, clock):
        self.clock = clock
        self._samples = []
        self.index = _Index(clock, CLOSE_PATH)

    def load_chain(self, day):
        return 64

    def leg_symbols(self, kind, k_low, k_high):
        cp = "C" if kind == "call" else "P"
        return f"NDXP261005{cp}{int(k_low):08d}", f"NDXP261005{cp}{int(k_high):08d}"

    def _level(self):
        return 31058.25 if self.clock().time() < dtime(16, 0) else 31076.44

    def fetch(self, syms):
        now = self.clock()
        out = {"NDX": LegQuote("NDX", None, None, self._level(), now, now)}
        for s in syms:
            out[s] = LegQuote(s, 16.0, 17.5, 16.75, now, now)
        return out

    def index_last(self):
        return self.index.index_last()

    def sample_underlying(self, quotes, when):
        px = quotes["NDX"].last
        self._samples.append((when, px))
        return px

    def close_minute(self, minute_start):
        end = minute_start + timedelta(minutes=1)
        s = [px for t, px in self._samples if minute_start <= t < end]
        self._samples = [(t, px) for t, px in self._samples if t >= end]
        return Bar(minute_start, s[0], max(s), min(s), s[-1]) if s else None

    def quote_vertical(self, kind, k_low, k_high, quotes, now, carry_min=30):
        return Quote(bid=16.0, ask=17.5, last=16.75, age=0)


class _Params:
    lookback_min = 0
    entry_start_min = 24 * 60

    def as_dict(self):
        return {}


class _Engine:
    """Holds a 31025/31075 put spread into the close and settles it at intrinsic on the last bar's close."""

    def __init__(self, blocked_reason="", holding=True):
        self.fills, self.trades, self.closes = [], [], []
        self.positions = [SimpleNamespace(kind="put", direction="bear", k_low=31025.0, k_high=31075.0, lots=3,
                                          avg_px=18.69, last_mark=None)] if holding else []
        self.pending = None
        self.blocked_reason = blocked_reason
        self.last_minute = 0
        self.settled_at = None
        self.by_minute: dict[int, float] = {}

    def on_bar(self, minute, S, quote_fn, is_last=False, high=None, low=None):
        self.closes.append(S); self.last_minute = minute; self.by_minute[minute] = S
        if is_last and self.positions:
            self.settled_at = S
            self.positions = []

    @property
    def day_pnl(self):
        return 0.0

    def marked(self):
        return 0.0

    def to_dict(self):
        return {}


class _Strategy:
    def __init__(self, holding=True):
        self.params = _Params()
        self.holding = holding
        self.session = None

    def live_instrument(self):
        return {"underlying": "NDX", "root": "NDXP"}

    def session_gate(self, day, events=None):
        return False, ""

    def live_session(self, day, blocked_reason="", bar_min=1):
        self.session = _Engine(blocked_reason=blocked_reason, holding=self.holding)
        return self.session


def _run_close(tmp_path, monkeypatch, holding=True):
    from paper import runner as RU
    strat = _Strategy(holding)
    monkeypatch.setattr(RU.R, "get_strategy", lambda slug: strat)
    monkeypatch.setattr(RU.R, "find_guide", lambda slug: None)
    monkeypatch.setattr(RU.R, "tests_dir_for", lambda slug: None)
    _, now_fn, sleep_fn = _clock(dtime(15, 58, 2))
    prov = _Prov(now_fn)
    ps = RU.PaperSession("stub", prov, None, write_ledger=False, log_dir=tmp_path / "log", state_dir=tmp_path / "state")
    ps.run_live(day=DAY, poll_seconds=15, until=dtime(16, 1), now_fn=now_fn, sleep_fn=sleep_fn)
    return strat.session, prov


def test_the_live_loop_settles_an_open_position_on_the_official_close(tmp_path, monkeypatch):
    eng, prov = _run_close(tmp_path, monkeypatch)
    assert eng.by_minute[15 * 60 + 59] == 31058.25          # the 15:58 bar, as polled
    assert eng.by_minute[16 * 60] == eng.settled_at == 31076.44 and not eng.positions   # the 15:59 bar: the close
    assert prov.index.reads and all(at.time() >= dtime(16, 0, 10) for at, _ in prov.index.reads)


def test_a_flat_session_does_not_wait_for_the_close(tmp_path, monkeypatch):
    eng, prov = _run_close(tmp_path, monkeypatch, holding=False)
    assert eng.settled_at is None and eng.by_minute[16 * 60] == 31058.25 and prov.index.reads == []
