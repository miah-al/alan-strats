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
    trend_position, current_trend_signal, TrendFollowingStrategy,
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
