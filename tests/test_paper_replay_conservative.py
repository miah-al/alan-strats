"""The 16k trap must not come back.

2026-09-24: the replay of ndx_0dte_tasty showed +$16,384 on 24 trades; the live paper runner made -$1,117 on 2.
The replay had paired each leg's last print with the other leg's, up to 30 minutes apart, at a flat half point of
spread. A replay is now CONSERVATIVE by default -- both legs must have printed in the same minute, the spread is the
calibrated live one, the taker crosses it -- and the day comes out where live did.

Two parts: the provider's own behaviour on synthetic prints (no database), and the regression on the stored day
(skips without the database or the strategy plugin).
"""
from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:      # only the checkout: its parent holds the live alan_trader (conftest binds ours by path)
    sys.path.insert(0, str(REPO))

from api.bootstrap import bootstrap  # noqa: E402

bootstrap()                         # the strategy plugin by path (ALAN_TRADER_STRATEGIES_DIR or the sibling checkout)

pytestmark = pytest.mark.filterwarnings("ignore")

SLUG = "ndx_0dte_tasty"
DAY = date(2026, 9, 24)
LIVE_DAY_PNL = -1117.0            # what the paper runner made on 2026-09-24 (2 trades)
LIVE_TRADES = 2
PHANTOM_REPLAY_PNL = 16384.0      # what the optimistic replay claimed (24 trades)


# ── the provider on synthetic prints ────────────────────────────────────────────

def _frames():
    day = date(2026, 9, 24)
    ts = lambda hh, mm: pd.Timestamp(datetime(day.year, day.month, day.day, hh, mm))
    bars = pd.DataFrame([{"ts": ts(11, m), "open": 30250.0, "high": 30251.0, "low": 30249.0, "close": 30250.0} for m in range(0, 10)])
    rows = []
    def pr(right, k, hh, mm, px):
        rows.append({"expiry": day, "right": right, "strike": float(k), "ts": ts(hh, mm), "close": px})
    # 11:00 (minute 661): both put legs print -> a synchronous vertical worth 80 - 57 = 23 on a 50-wide
    pr("P", 30300, 11, 0, 80.0); pr("P", 30250, 11, 0, 57.0)
    # 11:03 (664): only the long leg prints, 6 points higher -- with carry 30 the old replay paired it with the 11:00
    # short leg and "saw" the spread jump to 29; the short leg had simply not traded
    pr("P", 30300, 11, 3, 86.0)
    # 11:05 (666): the CALL side prints synchronously; parity gives the put vertical as 50 - (C(30250) - C(30300))
    pr("C", 30250, 11, 5, 30.0); pr("C", 30300, 11, 5, 9.0)
    return bars, pd.DataFrame(rows)


def test_replay_provider_is_conservative_by_default_and_labels_the_optimistic_run():
    from paper.providers import ReplayProvider
    bars, prints = _frames()
    prov = ReplayProvider.from_frames("NDX", DAY, bars, prints)
    assert prov.carry == 0 and prov.mode == "conservative" and prov.describe().startswith("CONSERVATIVE")
    q = prov.quote_vertical("put", 30250.0, 30300.0, 661, 30250.0)
    assert q is not None and q.last == 23.0 and q.age == 0
    assert q.ask - q.bid == pytest.approx(2 * (6.25 + 2.0))           # the live model: long put 50 in, short at the money
    assert prov.quote_vertical("put", 30250.0, 30300.0, 661).ask - q.bid < 2 * 8.25 + 1e-9   # without spot: the value fallback
    assert prov.quote_vertical("put", 30250.0, 30300.0, 664) is None  # a fresh long leg and a stale short leg: no quote
    assert prov.quote_vertical("put", 30250.0, 30300.0, 665) is None
    q = prov.quote_vertical("put", 30250.0, 30300.0, 666, 30250.0)    # parity from the other right, same minute: fine
    assert q is not None and q.last == pytest.approx(50.0 - 21.0) and q.age == 0
    q = prov.quote_vertical("call", 30250.0, 30300.0, 666, 30250.0)
    assert q is not None and q.last == pytest.approx(21.0)
    # the old behaviour, on request, is labelled
    old = ReplayProvider.from_frames("NDX", DAY, bars, prints, half_spread=0.5, carry_min=30)
    assert old.mode == "optimistic" and "OPTIMISTIC" in old.describe() and old.h == 0.5
    q = old.quote_vertical("put", 30250.0, 30300.0, 664)
    assert q is not None and q.last == 29.0 and q.age == 3 and q.ask - q.bid == 1.0    # the phantom move
    # a flat bracket no narrower than the measured crossing cost, with carry 0, still counts as conservative
    assert ReplayProvider.from_frames("NDX", DAY, bars, prints, half_spread=1.5).mode == "conservative"
    assert ReplayProvider.from_frames("NDX", DAY, bars, prints, half_spread=0.5).mode == "optimistic"


def test_runner_script_replay_defaults(monkeypatch):
    """scripts/paper_runner.py --replay: carry 0, the live spread, taker unless the strategy declares maker, and an
    optimistic column that is labelled."""
    import importlib.util
    # by path: another test binds ``scripts`` to a stand-in, and this must be THIS checkout's runner
    spec = importlib.util.spec_from_file_location("_paper_runner_under_test", REPO / "scripts" / "paper_runner.py")
    PR = importlib.util.module_from_spec(spec); spec.loader.exec_module(PR)

    class S:
        def get_params(self):
            return {"carry_min": 30, "stale_min": 5, "fill_model": "maker", "spread_model": "live", "half_spread_pts": 0.5, "width": 50.0}
    s = S()
    assert PR.default_fill_model(s) == "maker"
    assert PR.replay_params(s, 0, "taker", None) == {"carry_min": 0, "stale_min": 0, "fill_model": "taker", "spread_model": "live"}
    assert PR.replay_params(s, 0, "maker", 2.0) == {"carry_min": 0, "stale_min": 0, "fill_model": "maker", "spread_model": "flat", "half_spread_pts": 2.0}
    assert PR.optimistic_params(s) == {"carry_min": 30, "stale_min": 5, "spread_model": "flat", "half_spread_pts": 0.5}

    class T(S):
        OPTIMISTIC_PARAMS = {"fill_model": "mid", "entry_slippage_pts": 1.5, "stale_min": 5, "carry_min": 30}
        def get_params(self):
            return {"carry_min": 0, "stale_min": 0, "fill_model": "taker", "entry_slippage_pts": 1.5}
    assert PR.default_fill_model(T()) == "taker"
    assert PR.optimistic_params(T()) == {"fill_model": "mid", "entry_slippage_pts": 1.5, "stale_min": 5, "carry_min": 30}
    help_text = PR.__doc__
    assert "OPTIMISTIC" in help_text and "conservative" in help_text.lower()


# ── the stored day ──────────────────────────────────────────────────────────────

def _db():
    try:
        from db.client import get_engine, get_option_minute_sessions
        eng = get_engine()
        s = get_option_minute_sessions(eng, "NDX")
        if s.empty or DAY not in set(s["session"]):
            pytest.skip(f"no option prints stored for {DAY}")
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
    if "spread_model" not in s.get_params():
        pytest.skip("the loaded strategy predates the conservative execution parameters")
    return s


#: the parameters the live paper runner logged on 2026-09-24 (its runner.log), minus the fill settings under test
V22_LIVE_PARAMS = {"width": 50.0, "itm_offset": 24.0, "target_pts": 5.0, "min_prior_move": 15.0, "lookback_min": 30,
                   "counter_trend": False, "entry_start": "11:00", "entry_end": "14:00", "max_reentries": 3,
                   "reentry_window_min": 15, "reentry_discount": 5.0, "entry_ttl_min": 2, "stop_pts": 60.0, "max_adds": 2,
                   "add_trigger_pts": 10.0, "max_units": 1, "max_hold_min": 60, "maxhold_ends_day": True,
                   "hold_to_settlement": True, "daily_stop_cap": 2, "daily_loss_cap": 15000.0, "weekly_stop_days": 3,
                   "min_vxn_prev": 20.0, "lots": 1, "pricing": "market", "ai_gate": "shadow"}


def _replay(eng, tmp_path, tag, prov_kw, params):
    from paper.providers import ReplayProvider
    from paper.runner import PaperSession
    prov = ReplayProvider(eng, "NDX", DAY, **prov_kw)
    if not prov.has_option_data():
        pytest.skip("no option prints for the day")
    ps = PaperSession(SLUG, prov, eng, write_ledger=False, log_dir=tmp_path / tag, state_dir=tmp_path / f"state_{tag}",
                      params={**V22_LIVE_PARAMS, **params})
    return prov, ps.run_replay(DAY)


@pytest.mark.slow
def test_the_16k_trap_does_not_come_back_on_2026_09_24(tmp_path):
    eng = _db()
    _strategy()
    # the conservative defaults: carry 0, the live spread, taker -- the headline
    prov, cons = _replay(eng, tmp_path, "conservative", {}, {"carry_min": 0, "stale_min": 0, "spread_model": "live", "fill_model": "taker"})
    assert prov.mode == "conservative"
    assert cons.day_pnl <= 0.0, f"conservative replay of {DAY} shows a profit: {cons.day_pnl:+,.0f} on {len(cons.trades)} trades"
    assert len(cons.trades) <= 4
    # maker: no better than a small profit, nowhere near the phantom
    _, maker = _replay(eng, tmp_path, "maker", {}, {"carry_min": 0, "stale_min": 0, "spread_model": "live", "fill_model": "maker"})
    assert maker.day_pnl < 0.25 * PHANTOM_REPLAY_PNL and len(maker.trades) <= 6
    # the optimistic settings reproduce the trap, and are labelled so
    prov_o, opt = _replay(eng, tmp_path, "optimistic", {"half_spread": 0.5, "carry_min": 30},
                          {"carry_min": 30, "stale_min": 5, "spread_model": "flat", "half_spread_pts": 0.5, "fill_model": "taker"})
    assert prov_o.mode == "optimistic"
    assert opt.day_pnl > 5000.0 and len(opt.trades) >= 10, (opt.day_pnl, len(opt.trades))
    assert opt.day_pnl > cons.day_pnl


@pytest.mark.slow
def test_conservative_replay_matches_the_conservative_backtest(tmp_path):
    """Same prints, same spread model, same carry: the paper runner's replay and the strategy's own backtest must
    produce the same trades, so the Backtest tab and a replay cannot disagree about what conservative means."""
    eng = _db()
    s = _strategy()
    prov, res = _replay(eng, tmp_path, "parity", {}, {"carry_min": 0, "stale_min": 0, "spread_model": "live", "fill_model": "taker"})
    from db.client import get_minute_bars, get_option_minute_bars
    from alan_trader_strategies.strategies.ndx_0dte_tasty.strategy import simulate_day
    from alan_trader_strategies.strategies.ndx_0dte_tasty.pricing import MarketPricer, spread_for
    p = type(s.params).from_kwargs(s.params, **V22_LIVE_PARAMS, carry_min=0, stale_min=0, spread_model="live", fill_model="taker")
    bars = get_minute_bars(eng, "NDX", DAY, DAY); bars["bar_min"] = 1
    pr = MarketPricer.from_frame(get_option_minute_bars(eng, "NDX", DAY, DAY, expiry=DAY), half_spread=spread_for(p),
                                 stale_min=p.stale_min, carry_min=p.carry_min)
    bt = simulate_day(bars, DAY, pr, p, blocked_reason=res.reason if res.blocked else "")
    key = lambda t: (t["entry_time"], t["exit_time"], t["k_low"], t["k_high"], round(t["entry_px"], 2), round(t["exit_px"], 2), t["exit_reason"])
    assert [key(t) for t in res.trades] == [key(t) for t in bt["trades"]]
    assert abs(res.day_pnl - bt["day_pnl"]) < 1e-6
