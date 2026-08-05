"""
Dedicated tests for the 12-Month (time-series / absolute) Momentum strategy.

All deterministic and offline — synthetic price series, no network / DB. Focus:
  * the momentum rule (positive trailing N-month return -> long, else cash)
  * NO look-ahead: the position on day d uses only closes strictly before d, and
    in particular never trades on the very month-end bar used to make the decision
  * a synthetic backtest that runs and yields a sane BacktestResult
  * interface / schema checks (SignalResult, BacktestResult, params)
"""
import numpy as np
import pandas as pd
import pytest

from alan_trader.strategies.ts_momentum import (
    tsmom_position, current_tsmom_signal, TSMomentumStrategy,
)
from alan_trader.strategies.base import (
    SignalResult, BacktestResult, StrategyType, StrategyStatus,
)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _ramp(n, start=100.0, step=0.5, freq="B"):
    idx = pd.date_range("2020-01-01", periods=n, freq=freq)
    return pd.Series(start + np.arange(n) * step, index=idx)


def _up_then_down(n_up=320, n_dn=260, step=0.5):
    up = _ramp(n_up, step=step)
    dn = pd.Series(up.iloc[-1] - np.arange(1, n_dn + 1) * step,
                   index=pd.date_range(up.index[-1] + pd.offsets.BDay(1),
                                       periods=n_dn, freq="B"))
    return pd.concat([up, dn])


# --------------------------------------------------------------------------- #
# the rule
# --------------------------------------------------------------------------- #
def test_position_long_when_trailing_return_positive():
    up = _ramp(400)                       # ~1.5y of steadily rising prices
    pos = tsmom_position(up, 12)
    assert pos.iloc[-1] == 1.0            # positive 12-month return -> long
    assert set(pos.unique()) <= {0.0, 1.0}


def test_position_goes_to_cash_after_sustained_decline():
    close = _up_then_down(320, 320)       # long rise then a long fall (a 'crash')
    pos = tsmom_position(close, 12)
    assert pos.iloc[-1] == 0.0            # trailing return turned negative -> cash


def test_position_only_zero_or_one():
    close = _up_then_down()
    pos = tsmom_position(close, 12)
    assert pos.index.equals(close.index)
    assert pos.isin([0.0, 1.0]).all()
    assert not pos.isna().any()


# --------------------------------------------------------------------------- #
# NO look-ahead — the load-bearing tests
# --------------------------------------------------------------------------- #
def test_no_lookahead_future_prices_cannot_change_past_positions():
    """Causality: perturbing prices from day k onward must not alter any position
    on day <= k. This is the strongest, assumption-free leakage check."""
    idx = pd.date_range("2020-01-01", periods=700, freq="B")
    base = pd.Series(100 + np.cumsum(np.random.RandomState(0).randn(700)), index=idx)
    k = 450
    bumped = base.copy()
    bumped.iloc[k + 1:] += 40.0           # change the FUTURE only

    p_base = tsmom_position(base, 12)
    p_bump = tsmom_position(bumped, 12)
    # positions through day k must be byte-for-byte identical
    assert np.array_equal(p_base.iloc[:k + 1].values, p_bump.iloc[:k + 1].values)
    # and the perturbation must actually matter somewhere later (test isn't vacuous)
    assert not np.array_equal(p_base.values, p_bump.values)


def test_no_trade_on_the_decision_bar():
    """When a calendar month-end is itself a trading day, that day's close is what
    decides the verdict — so the position must NOT already reflect it on that bar.
    It must equal the prior bar's position (the shifted, lagged verdict)."""
    # daily (calendar) index so many month-ends ARE trading days
    idx = pd.date_range("2018-01-01", "2024-01-01", freq="B")
    close = pd.Series(100 + np.cumsum(np.random.RandomState(7).randn(len(idx))),
                      index=idx)
    pos = tsmom_position(close, 12)
    m_end = close.resample("ME").last()
    raw = (m_end.pct_change(12) > 0).astype(float)
    checked = 0
    for lbl, verdict in raw.dropna().items():
        days = close.index[(close.index.year == lbl.year) &
                           (close.index.month == lbl.month)]
        if len(days) == 0:
            continue
        last_trading_day = days[-1]
        prev = pos.index.get_loc(last_trading_day)
        if prev == 0:
            continue
        # position ON the decision bar == position on the bar BEFORE it (i.e. it has
        # NOT yet acted on today's verdict). This is the shift(1) guarantee.
        assert pos.iloc[prev] == pos.iloc[prev - 1]
        checked += 1
    assert checked > 10                   # we actually exercised the invariant


def test_position_is_one_trading_day_lag_of_monthly_verdict():
    """Structural check: pos == ffill(month-end verdict).shift(1). Confirms the
    decision is applied the *next* trading day, not the same bar and not a whole
    extra month later."""
    close = _ramp(500)
    m_end = close.resample("ME").last()
    raw = (m_end.pct_change(12) > 0).astype(float)
    expected = raw.reindex(close.index, method="ffill").shift(1).fillna(0.0)
    pd.testing.assert_series_equal(tsmom_position(close, 12), expected,
                                   check_names=False)


def test_no_bfill_only_ffill():
    """A leading gap must stay 0 (cash), never back-filled from a future verdict."""
    close = _ramp(400)
    pos = tsmom_position(close, 12)
    # the first ~12 months have no defined trailing return -> must be cash, not
    # something inferred from later data
    assert pos.iloc[0] == 0.0
    assert (pos.iloc[:60] == 0.0).all()


# --------------------------------------------------------------------------- #
# live signal
# --------------------------------------------------------------------------- #
def test_current_signal_buy_in_uptrend_hold_in_downtrend():
    up = _ramp(400)
    sig = current_tsmom_signal(up, 12)
    assert sig["signal"] == "BUY" and sig["ret_lookback_pct"] > 0
    assert sig["state"].startswith("IN")

    dn = _up_then_down(320, 320)
    sig_dn = current_tsmom_signal(dn, 12)
    assert sig_dn["signal"] == "HOLD" and sig_dn["state"].startswith("OUT")


def test_current_signal_insufficient_history():
    out = current_tsmom_signal(_ramp(50), 12)
    assert out["signal"] == "UNKNOWN"
    out2 = current_tsmom_signal(pd.Series(dtype=float), 12)
    assert out2["signal"] == "UNKNOWN"


# --------------------------------------------------------------------------- #
# backtest + interface
# --------------------------------------------------------------------------- #
def test_synthetic_backtest_runs_and_is_sane():
    close = _up_then_down(360, 300)
    price_df = pd.DataFrame({"close": close.values}, index=close.index)
    res = TSMomentumStrategy().backtest(price_df, {"ticker": "TEST"},
                                        starting_capital=10_000)
    assert isinstance(res, BacktestResult)
    assert not res.equity_curve.empty
    assert res.equity_curve.iloc[0] > 0
    assert np.isfinite(res.equity_curve.iloc[-1])
    # metrics present
    for key in ("total_return_pct", "sharpe", "max_drawdown_pct", "num_trades"):
        assert key in res.metrics
    # trades schema (may be empty for very short samples)
    if not res.trades.empty:
        for c in ("entry_date", "exit_date", "entry_px", "exit_px", "pnl", "winner"):
            assert c in res.trades.columns
    # benchmark + current verdict travel in extra
    assert "benchmark_equity" in res.extra
    assert "current" in res.extra


def test_backtest_cuts_drawdown_vs_buy_hold_on_a_crash():
    """The point of the overlay: sitting in cash through the decline must produce a
    shallower drawdown than buy-and-hold over a full round-trip."""
    close = _up_then_down(360, 360)       # rise then equal-sized fall
    price_df = pd.DataFrame({"close": close.values}, index=close.index)
    res = TSMomentumStrategy().backtest(price_df, {"ticker": "TEST"},
                                        starting_capital=10_000)
    eq = res.equity_curve
    strat_dd = (eq / eq.cummax() - 1).min()
    bh = 10_000 * (1 + close.pct_change().fillna(0)).cumprod()
    bh_dd = (bh / bh.cummax() - 1).min()
    assert strat_dd > bh_dd               # less negative == shallower drawdown


def test_strategy_interface():
    s = TSMomentumStrategy()
    assert s.name == "ts_momentum"
    assert s.strategy_type == StrategyType.RULE_BASED
    assert s.status == StrategyStatus.ACTIVE
    params = s.get_params()
    assert {"lookback_months", "cash_yield", "ticker"} <= set(params)
    ui = s.get_backtest_ui_params()
    assert isinstance(ui, list) and all("key" in p for p in ui)


def test_generate_signal_returns_signalresult():
    close = _ramp(400)
    s = TSMomentumStrategy()
    res = s.generate_signal({"close": close, "ticker": "TEST"})
    assert isinstance(res, SignalResult)
    assert res.strategy_name == "ts_momentum"
    assert res.signal in ("BUY", "HOLD")
    assert 0.0 <= res.position_size_pct <= 1.0


def test_backtest_lookback_param_override():
    """Passing lookback_months to backtest() must override the instance default."""
    close = _ramp(500)
    price_df = pd.DataFrame({"close": close.values}, index=close.index)
    res = TSMomentumStrategy(lookback_months=12).backtest(
        price_df, {"ticker": "TEST"}, starting_capital=10_000, lookback_months=6)
    assert res.params["lookback_months"] == 6
