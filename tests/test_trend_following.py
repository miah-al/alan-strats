"""
Tests for the validated trend-following / time-series momentum strategies.

Uses deterministic synthetic price series (no network / DB) so they run fast and
offline. Focus: correctness of the rule, NO look-ahead, and that the backtest
produces a sane BacktestResult.
"""
import numpy as np
import pandas as pd
import pytest

from alan_trader.strategies.trend_following import (
    trend_position, current_trend_signal, TrendFollowingStrategy, _clean_close,
)
from alan_trader.strategies.ts_momentum import (
    tsmom_position, current_tsmom_signal, TSMomentumStrategy,
)


def _ramp(n, start=100.0, step=0.5):
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    return pd.Series(start + np.arange(n) * step, index=idx)


def _series_up_then_down(n_up=300, n_dn=300):
    up = _ramp(n_up)
    dn = pd.Series(up.iloc[-1] - np.arange(1, n_dn + 1) * 0.5,
                   index=pd.date_range(up.index[-1] + pd.offsets.BDay(1), periods=n_dn, freq="B"))
    return pd.concat([up, dn])


def test_trend_position_long_in_uptrend():
    close = _ramp(300)
    pos = trend_position(close, ma_window=200)
    # steadily rising → price stays above its MA → long once warmed up
    assert pos.iloc[250] == 1.0


def test_trend_position_exits_in_downtrend():
    close = _series_up_then_down()
    pos = trend_position(close, ma_window=200)
    # by the end of a long decline, price is below MA → cash
    assert pos.iloc[-1] == 0.0


def test_trend_no_lookahead():
    """Position on day i must use only data through day i-1 (shifted)."""
    close = _ramp(250)
    ma = close.rolling(200).mean()
    pos = trend_position(close, 200)
    # pos today equals yesterday's (close>ma) — i.e. it's the shifted signal
    raw = (close > ma).astype(float)
    assert pos.iloc[210] == raw.iloc[209]


def test_trend_no_lookahead_exhaustive():
    """For EVERY day, position[i] must equal the raw (close>MA) signal from i-1,
    and the first day must be flat (no signal can exist before any history)."""
    close = _series_up_then_down(260, 200)
    raw = (close > close.rolling(200).mean()).astype(float)
    pos = trend_position(close, 200)
    expected = raw.shift(1, fill_value=0.0)
    assert (pos.values == expected.values).all()
    assert pos.iloc[0] == 0.0          # day-0 is always cash


def test_trend_perturbing_future_does_not_change_past():
    """Changing a future close must not alter any earlier position — the
    definitive no-look-ahead property."""
    close = _ramp(260)
    pos_a = trend_position(close, 200)
    bumped = close.copy()
    bumped.iloc[230:] *= 1.5           # perturb only the tail
    pos_b = trend_position(bumped, 200)
    # positions up to and including day 230 must be identical
    assert (pos_a.iloc[:231].values == pos_b.iloc[:231].values).all()


def test_trend_ffill_only_no_bfill():
    """A gap (NaN) is forward-filled, never back-filled: a leading NaN stays
    un-fillable (no future value pulled back), an interior NaN inherits the
    PRIOR close, not the next one."""
    idx = pd.date_range("2020-01-01", periods=6, freq="B")
    s = pd.Series([100.0, np.nan, 102.0, np.nan, 104.0, 105.0], index=idx)
    cleaned = _clean_close(s)
    # interior NaN at position 1 takes the prior value (100), NOT the next (102)
    assert cleaned.iloc[1] == 100.0
    assert cleaned.iloc[3] == 102.0
    # a leading NaN must remain NaN (nothing earlier to carry forward, no bfill)
    s2 = pd.Series([np.nan, 100.0, 101.0], index=idx[:3])
    assert pd.isna(_clean_close(s2).iloc[0])


def test_trend_dedups_and_sorts():
    """Out-of-order, duplicated dates are sorted and deduped (keep last)."""
    idx = pd.to_datetime(["2020-01-03", "2020-01-01", "2020-01-02", "2020-01-02"])
    s = pd.Series([3.0, 1.0, 2.0, 99.0], index=idx)
    cleaned = _clean_close(s)
    assert list(cleaned.index) == sorted(cleaned.index)
    assert cleaned.loc["2020-01-02"] == 99.0      # keep last duplicate
    assert len(cleaned) == 3


def test_current_trend_signal_buy_and_hold():
    up = _ramp(260)
    sig = current_trend_signal(up, 200)
    assert sig["signal"] == "BUY" and sig["pct_vs_ma"] > 0
    dn = _series_up_then_down()
    assert current_trend_signal(dn, 200)["signal"] == "HOLD"


def test_current_trend_signal_insufficient_history():
    assert current_trend_signal(_ramp(50), 200)["signal"] == "UNKNOWN"


def test_tsmom_position_and_signal():
    up = _ramp(400)                     # ~1.5y of rising daily prices
    pos = tsmom_position(up, 12)
    assert pos.iloc[-1] == 1.0          # positive 12m return → long
    sig = current_tsmom_signal(up, 12)
    assert sig["signal"] == "BUY" and sig["ret_lookback_pct"] > 0


def test_backtest_returns_valid_result():
    close = _series_up_then_down(320, 260)
    price_df = pd.DataFrame({"close": close.values}, index=close.index)
    for cls in (TrendFollowingStrategy, TSMomentumStrategy):
        res = cls().backtest(price_df, {"ticker": "TEST"}, starting_capital=10_000)
        assert not res.equity_curve.empty
        assert res.equity_curve.iloc[0] > 0
        # trades frame has the expected schema (may be empty for short samples)
        if not res.trades.empty:
            for c in ("entry_date", "exit_date", "pnl", "winner"):
                assert c in res.trades.columns


def test_trend_strategy_interface():
    """Conforms to the BaseStrategy interface used by the app: get_params,
    generate_signal -> SignalResult, backtest -> BacktestResult with metrics."""
    from alan_trader.strategies.base import SignalResult, BacktestResult
    s = TrendFollowingStrategy()
    assert s.name == "trend_following"
    p = s.get_params()
    assert {"ma_window", "cash_yield", "ticker"} <= set(p)

    close = _ramp(260)
    sig = s.generate_signal({"close": close, "ticker": "TEST"})
    assert isinstance(sig, SignalResult)
    assert sig.signal in ("BUY", "HOLD")
    assert 0.0 <= sig.position_size_pct <= 1.0

    price_df = pd.DataFrame({"close": close.values}, index=close.index)
    res = s.backtest(price_df, {"ticker": "TEST"}, starting_capital=10_000)
    assert isinstance(res, BacktestResult)
    for k in ("total_return_pct", "sharpe", "max_drawdown_pct", "final_equity"):
        assert k in res.metrics
    # benchmark equity is surfaced for the chart overlay
    assert "benchmark_equity" in res.extra


def test_trend_beats_buyhold_drawdown():
    """The whole point: trend filter must cut drawdown vs buy-hold on a crash."""
    close = _series_up_then_down(300, 300)   # big round-trip = a 'crash'
    price_df = pd.DataFrame({"close": close.values}, index=close.index)
    res = TrendFollowingStrategy().backtest(price_df, {"ticker": "TEST"}, starting_capital=10_000)
    eq = res.equity_curve
    trend_dd = (eq / eq.cummax() - 1).min()
    bh = 10_000 * (1 + close.pct_change().fillna(0)).cumprod()
    bh_dd = (bh / bh.cummax() - 1).min()
    assert trend_dd > bh_dd   # less negative = shallower drawdown
