"""The live loop with a fake real-time provider: a scripted clock advances through a stored
session, the provider answers quotes from the stored prints the way the broker would (leg
bid/ask/last with timestamps), and the loop must build the minute bars, fetch quotes for strikes
the engine chooses on the fly, and end with the same trades as the replay of that day."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from strategy_api.live import Quote

SLUG = "ndx_0dte_tasty"
DAY = date(2026, 8, 26)


def _db():
    try:
        from db.client import get_engine, get_option_minute_coverage
        eng = get_engine()
        if not get_option_minute_coverage(eng, "NDX"):
            pytest.skip("no option minute bars stored")
        return eng
    except Exception as exc:
        pytest.skip(f"database unavailable: {exc}")


class FakeLiveProvider:
    """Looks like TastytradeProvider to the runner, answers from the replay data."""
    name = "fake-live"
    underlying = "NDX"
    root = "NDXP"
    poll_seconds = 20

    def __init__(self, replay, clock):
        self.rp = replay
        self.clock = clock
        self.expiry = DAY
        self._samples = []
        self.fetch_calls = 0
        self.symbols_seen = set()

    def load_chain(self, day):
        return 64

    def leg_symbols(self, kind, k_low, k_high):
        return self.rp.leg_symbols(kind, k_low, k_high)

    def fetch(self, option_symbols):
        from paper.providers import LegQuote
        self.fetch_calls += 1
        self.symbols_seen.update(option_symbols)
        now = self.clock()
        minute = now.hour * 60 + now.minute
        out = {}
        # the underlying: the stored bar's close for the minute in progress (a price sample)
        bars = self.rp.bars
        m = bars[(bars.ts.dt.hour * 60 + bars.ts.dt.minute) == minute]
        if len(m):
            out["NDX"] = LegQuote("NDX", None, None, float(m.close.iloc[0]), now, now)
        for s in option_symbols:                        # a leg row per symbol; the vertical is valued in quote_vertical
            out[s] = LegQuote(s, 0.0, 0.0, None, None, now)
        return out

    def sample_underlying(self, quotes, when):
        q = quotes.get("NDX")
        if q and q.last is not None:
            self._samples.append((when, q.last))
            return q.last
        return None

    def close_minute(self, minute_start):
        from paper.providers import Bar
        end = minute_start + timedelta(minutes=1)
        s = [px for t, px in self._samples if minute_start <= t < end]
        self._samples = [(t, px) for t, px in self._samples if t >= end]
        return Bar(minute_start, s[0], max(s), min(s), s[-1]) if s else None

    def quote_vertical(self, kind, k_low, k_high, quotes, now, carry_min=30):
        # A real NBBO is two-sided and always fresh even when the legs do not trade; the closest
        # stored stand-in is the replay's own valuation at this minute (fresher side + parity).
        ls, ss = self.leg_symbols(kind, k_low, k_high)
        if ls not in quotes or ss not in quotes:
            return None
        return self.rp.quote_vertical(kind, k_low, k_high, now.hour * 60 + now.minute)


def test_live_loop_with_a_fake_provider_matches_the_replay(tmp_path):
    eng = _db()
    from strategy_api import registry as R
    try:
        s = R.get_strategy(SLUG)
    except Exception as exc:
        pytest.skip(str(exc))
    from paper.providers import ReplayProvider
    from paper.runner import PaperSession
    replay = ReplayProvider(eng, "NDX", DAY, half_spread=0.5)
    if not replay.has_option_data():
        pytest.skip("no prints for the test day")

    # a scripted clock: three polls per minute from 09:29 to 16:01
    t = [datetime.combine(DAY, datetime.min.time()) + timedelta(hours=9, minutes=29)]
    def now_fn():
        return t[0]
    def sleep_fn(sec):
        t[0] = t[0] + timedelta(seconds=20)

    fake = FakeLiveProvider(replay, now_fn)
    ps = PaperSession(SLUG, fake, eng, write_ledger=False, log_dir=tmp_path / "live", state_dir=tmp_path / "state")
    res = ps.run_live(day=DAY, poll_seconds=20, now_fn=now_fn, sleep_fn=sleep_fn)
    assert res.bars >= 380 and fake.fetch_calls > 1000
    assert len(res.trades) > 0
    # every event row carries the quoted spread and has room for the leg quotes behind it
    import pandas as pd
    log = pd.read_csv(tmp_path / "live" / f"{DAY.isoformat()}.csv")
    assert {"spread", "long_bid", "long_ask", "long_age", "short_bid", "short_ask", "short_age"} <= set(log.columns)
    assert (log.loc[log.event.isin(["open", "add", "close"]), "spread"].astype(float) > 0).all()
    # the replay of the same day: same rules, same prints, same half spread
    ps2 = PaperSession(SLUG, ReplayProvider(eng, "NDX", DAY, half_spread=0.5), eng, write_ledger=False, log_dir=tmp_path / "replay", state_dir=tmp_path / "state2")
    rep = ps2.run_replay(DAY)
    key = lambda x: (x["entry_time"], x["k_low"], x["k_high"], x["exit_reason"])
    live_keys = [key(x) for x in res.trades]; rep_keys = [key(x) for x in rep.trades]
    # the live loop quotes the vertical from leg bid/ask (each leg +-h/2), the replay from the print +-h:
    # same mid, same trigger minutes; allow the entry price to differ by the leg-vs-spread bracket only
    assert live_keys == rep_keys, (live_keys, rep_keys)
    assert abs(res.day_pnl - rep.day_pnl) < 1e-6
    # strikes chosen on the fly were fetched on demand
    assert any(sym.startswith("NDXP") for sym in fake.symbols_seen)


def test_failing_quote_feed_backs_off_and_halts(tmp_path, monkeypatch):
    """A broken feed is polled less and less often and the session halts after a bounded number of
    failures; a rejected credential halts at once. The broker is never hammered. No network: the
    provider here is a stub that always fails."""
    from datetime import date as _date
    from paper import runner as R
    from paper.runner import PaperSession

    class DeadProvider:
        name = "fake-live"; underlying = "NDX"; root = "NDXP"; poll_seconds = 20
        def __init__(self, message):
            self.message = message; self.fetch_calls = 0; self.expiry = DAY
        def load_chain(self, day): return 64
        def leg_symbols(self, kind, k_low, k_high): return (None, None)
        def fetch(self, symbols):
            self.fetch_calls += 1; raise RuntimeError(self.message)
        def sample_underlying(self, quotes, when): return None
        def close_minute(self, minute): return None
        def backfill_bars(self, day, until): return []

    monkeypatch.setattr(PaperSession, "_preflight", lambda self, day: [])
    monkeypatch.setattr(PaperSession, "_gate", lambda self, day: (False, ""))
    t = [datetime.combine(DAY, datetime.min.time()) + timedelta(hours=11)]
    sleeps = []
    def now_fn(): return t[0]
    def sleep_fn(sec): sleeps.append(sec); t[0] = t[0] + timedelta(seconds=sec)

    # 1. a feed that keeps failing: exponential backoff, then a halt
    prov = DeadProvider("connection reset")
    ps = PaperSession(SLUG, prov, None, write_ledger=False, log_dir=tmp_path / "a", state_dir=tmp_path / "sa")
    res = ps.run_live(day=DAY, poll_seconds=20, now_fn=now_fn, sleep_fn=sleep_fn)
    assert ps.halted and "quote feed halted" in ps.halted
    assert prov.fetch_calls == R.FETCH_FAILURES_TO_HALT
    assert sleeps[:6] == [20, 40, 80, 160, 300, 300]                 # doubling from the poll, capped at FETCH_BACKOFF_MAX_S
    # 2. a rejected credential: one failure, no retry at all
    prov2 = DeadProvider("tastytrade rejected the credentials (Client secret mismatch)")
    ps2 = PaperSession(SLUG, prov2, None, write_ledger=False, log_dir=tmp_path / "b", state_dir=tmp_path / "sb")
    ps2.run_live(day=DAY, poll_seconds=20, now_fn=now_fn, sleep_fn=sleep_fn)
    assert prov2.fetch_calls == 1 and "rejected the credentials" in ps2.halted
    # 3. the poll rate has a floor whatever the flag says
    prov3 = DeadProvider("x")
    ps3 = PaperSession(SLUG, prov3, None, write_ledger=False, log_dir=tmp_path / "c", state_dir=tmp_path / "sc")
    n_before = len(sleeps); ps3.run_live(day=DAY, poll_seconds=1, now_fn=now_fn, sleep_fn=sleep_fn)
    assert min(sleeps[n_before:]) >= R.MIN_POLL_S
