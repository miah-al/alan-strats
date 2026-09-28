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
    # last is the MIDPOINT, not last(long) - last(short). Those two prints are four minutes apart
    # here, and in live data the gap can be hours with no timestamp to reveal it; differencing them
    # produced vertical prices that cannot exist. The mid is defined at every instant, and is where
    # multi-leg orders were measured to transact.
    assert q.bid == 60.0 and q.ask == 64.0 and q.last == 62.0 and q.age == 5
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
    assert (log.event == "features").sum() == 1                      # one ex-ante feature row per session
    events = log[log.event != "features"]
    assert len(events) == len(res.fills)
    assert (events.event.isin(["rest", "open", "add", "close", "cancel"])).all()
    import json as _json
    feats = _json.loads(log[log.event == "features"].note.iloc[0])
    assert {"am_range_pct", "gap_pct", "vxn_prev"} <= set(feats)
    ai = feats.get("ai") or {}
    assert ai.get("mode") in ("shadow", "on", "off")
    if ai.get("mode") != "off" and ai.get("model"):
        assert ai.get("verdict") in ("trade", "skip") and 0.0 <= float(ai.get("p")) <= 1.0
        assert "vxn_prev" in (feats.get("ai_features") or {})
    import json
    st = json.loads(open(res.state_path, encoding="utf-8").read())
    restored = type(s.live_session(day)).from_dict(s.params, st["state"])
    assert len(restored.trades) == len(res.trades) and restored.day_pnl == res.day_pnl


def test_vertical_quote_bounds_the_midpoint_and_scales_the_width_cap():
    """Every decision reads the vertical's midpoint -- the target through ``last``, the engine's mark,
    add trigger and loss cap through (bid + ask) / 2 -- so the midpoint is what must respect arbitrage
    (0 <= value <= strike width), and the two must agree. Width is capped at 60% of the strike width."""
    from datetime import datetime
    from paper.providers import LegQuote, vertical_quote
    now = datetime(2026, 9, 23, 13, 0)
    def q(l, s, w):
        return vertical_quote(LegQuote("L", *l, None, None, now), LegQuote("S", *s, None, None, now), now, max_width=w)
    v = q((94.8, 104.7), (59.1, 67.3), 50)                     # in range: untouched
    assert (v.bid, v.ask) == (27.5, 45.6) and abs(v.last - 36.55) < 1e-9
    v = q((102.0, 110.0), (52.0, 58.0), 50)                    # raw mid 51 on a 50-wide: bounded to 50
    assert v.last == 50.0 and abs((v.bid + v.ask) / 2 - 50.0) < 1e-9 and abs((v.ask - v.bid) - 14.0) < 1e-9
    v = q((1.0, 3.0), (2.0, 4.0), 50)                          # raw mid -1: bounded to 0
    assert v.last == 0.0 and abs((v.bid + v.ask) / 2) < 1e-9
    assert q((60.0, 90.5), (40.0, 40.0), 50) is None           # 30.5 wide on a 50-wide: over the 30-point cap
    assert q((60.0, 89.5), (40.0, 40.0), 50) is not None       # 29.5 wide: usable
    assert q((60.0, 81.0), (40.0, 40.0), None) is None         # no width known: the flat 20-point cap
