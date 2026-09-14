"""The paper runner in replay mode must reproduce the market-priced backtest for the same day:
same quotes (print -/+ half spread), same engine, so the same fills. Skips without the database
or the strategy plugin."""
from __future__ import annotations

from datetime import date

import pytest

pytestmark = pytest.mark.filterwarnings("ignore")

SLUG = "ndx_0dte_tasty"


def _db():
    try:
        from db.client import get_engine, get_option_minute_coverage
        eng = get_engine()
        cov = get_option_minute_coverage(eng, "NDX")
        if not cov:
            pytest.skip("no option minute bars stored")
        return eng
    except Exception as exc:
        pytest.skip(f"database unavailable: {exc}")


def _strategy():
    from strategy_api import registry as R
    try:
        s = R.get_strategy(SLUG)
    except Exception as exc:
        pytest.skip(f"strategy not available: {exc}")
    if not s.live_instrument():
        pytest.skip("strategy exposes no live session")
    return s


def test_vertical_quote_from_legs():
    from datetime import datetime
    from paper.providers import LegQuote, vertical_quote
    now = datetime(2026, 8, 26, 13, 30)
    long_leg = LegQuote("L", bid=170.0, ask=172.0, last=171.0, last_time=datetime(2026, 8, 26, 13, 29), updated=now)
    short_leg = LegQuote("S", bid=108.0, ask=110.0, last=109.5, last_time=datetime(2026, 8, 26, 13, 25), updated=now)
    q = vertical_quote(long_leg, short_leg, now)
    assert q.bid == 60.0 and q.ask == 64.0 and q.last == 61.5 and q.age == 5
    assert vertical_quote(LegQuote("L", None, None, None, None, None), short_leg, now) is None
    stale = LegQuote("S", 108.0, 110.0, None, None, datetime(2026, 8, 26, 12, 0))
    assert vertical_quote(long_leg, stale, now, carry_min=30) is None


def test_replay_matches_backtest_for_a_stored_day(tmp_path):
    eng = _db()
    s = _strategy()
    day = date(2026, 8, 26)
    from paper.providers import ReplayProvider
    from paper.runner import PaperSession
    prov = ReplayProvider(eng, "NDX", day, half_spread=0.5)
    if not prov.has_option_data():
        pytest.skip("no option prints for the test day")
    ps = PaperSession(SLUG, prov, eng, write_ledger=False, log_dir=tmp_path, state_dir=tmp_path / "state")
    res = ps.run_replay(day)
    assert res.bars == len(prov.bars)
    # the backtest of the same day with the same assumptions
    import pandas as pd
    from db.client import get_minute_bars, get_option_minute_bars
    from alan_trader_strategies.strategies.ndx_0dte_tasty.strategy import simulate_day
    from alan_trader_strategies.strategies.ndx_0dte_tasty.pricing import MarketPricer
    p = type(s.params).from_kwargs(s.params, fill_model="taker", half_spread_pts=0.5, pricing="market")
    bars = get_minute_bars(eng, "NDX", day, day); bars["bar_min"] = 1
    pr = MarketPricer.from_frame(get_option_minute_bars(eng, "NDX", day, day, expiry=day), half_spread=0.5, stale_min=p.stale_min, carry_min=p.carry_min)
    bt = simulate_day(bars, day, pr, p, blocked_reason=res.reason if res.blocked else "")
    key = lambda t: (t["entry_time"], t["exit_time"], t["k_low"], t["k_high"], round(t["entry_px"], 2), round(t["exit_px"], 2), t["exit_reason"])
    assert [key(t) for t in res.trades] == [key(t) for t in bt["trades"]]
    assert abs(res.day_pnl - bt["day_pnl"]) < 1e-6
    # the paper log has one row per event and the state file can be restored
    log = pd.read_csv(res.log_path)
    assert len(log) == len(res.fills)
    assert (log.event.isin(["rest", "open", "add", "close", "cancel"])).all()
    import json
    st = json.loads(open(res.state_path, encoding="utf-8").read())
    restored = type(s.live_session(day)).from_dict(s.params, st["state"])
    assert len(restored.trades) == len(res.trades) and restored.day_pnl == res.day_pnl
