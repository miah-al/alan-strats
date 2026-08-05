"""
Tests for crypto_etf_vrp.

The defect classes these guard against are the ones the 2026-08-01 edge review
found across the existing book: fabricated P&L that ignores the underlying,
costs charged on one side only, cash accounting that destroys the entry
principal, look-ahead via future-data guards, and equity curves that never mark
to market (which makes MaxDD structurally zero).
"""

import numpy as np
import pandas as pd
import pytest

from alan_trader.strategies.crypto_etf_vrp import (
    CryptoETFVRPStrategy, realized_vol, vol_rank, _strike_for_put_delta,
    _put_delta,
)
from alan_trader.strategies.base import BacktestResult, StrategyStatus


def _bars(n=400, start=40.0, vol=0.60, seed=0, drift=0.0004):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2024-01-02", periods=n)
    steps = rng.normal(drift, vol / np.sqrt(252), n)
    close = start * np.exp(np.cumsum(steps))
    return pd.DataFrame(
        {"open": close, "high": close * 1.02, "low": close * 0.98,
         "close": close, "volume": 1e6},
        index=idx,
    )


# ── indicators ────────────────────────────────────────────────────────────────

def test_realized_vol_recovers_the_generating_volatility():
    bars = _bars(n=1200, vol=0.60, seed=3)
    rv = realized_vol(bars["close"], 60).dropna()
    assert 0.45 < rv.median() < 0.75


def test_vol_rank_is_bounded_and_trailing_only():
    rv = realized_vol(_bars(n=600)["close"], 20)
    vr = vol_rank(rv).dropna()
    assert ((vr >= 0) & (vr <= 1)).all()
    # Truncating the series must not change earlier ranks — no future leakage.
    full = vol_rank(rv)
    trunc = vol_rank(rv.iloc[:400])
    common = trunc.dropna().index
    pd.testing.assert_series_equal(full.loc[common], trunc.loc[common])


# ── strike selection ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("target", [0.10, 0.25, 0.40])
def test_strike_for_delta_hits_its_target(target):
    S, T, r, sigma = 40.0, 45 / 365, 0.045, 0.60
    k = _strike_for_put_delta(S, T, r, sigma, target)
    assert abs(abs(_put_delta(S, k, T, r, sigma)) - target) < 0.02


def test_lower_delta_means_further_out_of_the_money():
    S, T, r, sigma = 40.0, 45 / 365, 0.045, 0.60
    assert (_strike_for_put_delta(S, T, r, sigma, 0.10)
            < _strike_for_put_delta(S, T, r, sigma, 0.30) < S)


# ── backtest integrity ────────────────────────────────────────────────────────

def test_backtest_returns_a_well_formed_result():
    res = CryptoETFVRPStrategy().backtest(_bars(), {"ticker": "IBIT"})
    assert isinstance(res, BacktestResult)
    assert len(res.equity_curve) == 400
    assert isinstance(res.equity_curve.index, pd.DatetimeIndex)
    for key in ("total_return_pct", "annualized_return_pct", "sharpe",
                "max_drawdown_pct", "exposure_pct"):
        assert key in res.metrics


def test_pnl_depends_on_the_underlying_path():
    """
    The review found four strategies whose P&L was a constant times a made-up
    credit — the spot price never entered the payoff. Different price paths must
    produce different results.
    """
    s = CryptoETFVRPStrategy()
    a = s.backtest(_bars(seed=1), {"ticker": "IBIT"}).metrics["total_return_pct"]
    b = s.backtest(_bars(seed=2), {"ticker": "IBIT"}).metrics["total_return_pct"]
    assert a != b


def test_a_crash_produces_losses():
    """A put seller must lose money when the underlying collapses."""
    bars = _bars(n=400, seed=5)
    bars.loc[bars.index[250:], "close"] *= np.linspace(1.0, 0.45, len(bars) - 250)
    res = CryptoETFVRPStrategy().backtest(bars, {"ticker": "IBIT"})
    if not res.trades.empty:
        assert (res.trades["pnl"] < 0).any(), "short puts survived a 55% crash"
        assert res.metrics["max_drawdown_pct"] < 0


def test_equity_curve_marks_open_positions_to_market():
    """
    Strategies that only move equity on close produce a step function, making
    MaxDD structurally 0.00 and Sharpe meaningless.
    """
    bars = _bars(n=400, seed=7)
    bars.loc[bars.index[200:260], "close"] *= np.linspace(1.0, 0.70, 60)
    res = CryptoETFVRPStrategy().backtest(bars, {"ticker": "IBIT"})
    if not res.trades.empty:
        assert res.metrics["max_drawdown_pct"] < 0, "no drawdown despite a 30% fall"


def test_costs_reduce_pnl_and_are_charged_both_sides():
    """Widening per-leg friction must strictly reduce the result."""
    from alan_trader.strategies import crypto_etf_vrp as mod

    bars = _bars(seed=11)
    base = CryptoETFVRPStrategy().backtest(bars, {"ticker": "IBIT"})
    original = mod.DEFAULT_COMMISSION_PER_LEG
    try:
        mod.DEFAULT_COMMISSION_PER_LEG = original * 20
        costly = CryptoETFVRPStrategy().backtest(bars, {"ticker": "IBIT"})
    finally:
        mod.DEFAULT_COMMISSION_PER_LEG = original

    if not base.trades.empty:
        assert (costly.metrics["total_return_pct"]
                < base.metrics["total_return_pct"])


def test_no_lookahead_truncation_invariance():
    """
    Re-running on a truncated series must reproduce the overlapping equity
    exactly. A guard like `(n - i) > dte` — the leak found in
    iron_condor_rules — breaks this.
    """
    bars = _bars(n=500, seed=13)
    s = CryptoETFVRPStrategy()
    full = s.backtest(bars, {"ticker": "IBIT"}).equity_curve
    short = s.backtest(bars.iloc[:380], {"ticker": "IBIT"}).equity_curve
    overlap = short.index[:-1]          # last bar force-closes, so exclude it
    np.testing.assert_allclose(
        full.loc[overlap].to_numpy(), short.loc[overlap].to_numpy(), rtol=1e-9,
    )


def test_null_hypothesis_has_no_manufactured_edge():
    """
    With vrp_multiplier = 1.0 options are priced at realized vol, so there is no
    premium to harvest. A positive result here would mean the backtest is
    inventing one.
    """
    bars = _bars(n=600, seed=17, drift=0.0)
    res = CryptoETFVRPStrategy(vrp_multiplier=1.0).backtest(bars, {"ticker": "IBIT"})
    assert res.metrics["total_return_pct"] < 5.0


def test_trend_filter_suppresses_selling_into_a_downtrend():
    """
    The filter is price-above-a-rising-average, which is lagging by design — at
    60% vol a downtrend still contains real multi-week rallies, so an absolute
    trade count is the wrong assertion. What must hold is that the gate binds:
    materially fewer entries down than up.
    """
    s = CryptoETFVRPStrategy()
    up = s.backtest(_bars(n=400, seed=19, drift=0.004), {"ticker": "IBIT"})
    down = s.backtest(_bars(n=400, seed=19, drift=-0.004), {"ticker": "IBIT"})
    assert len(down.trades) < len(up.trades) * 0.75, (
        f"trend filter barely binds: {len(down.trades)} trades down "
        f"vs {len(up.trades)} up"
    )


def test_rising_average_requirement_binds():
    """Price above a *falling* average must not qualify — that is a bear rally."""
    n = 320
    idx = pd.bdate_range("2024-01-02", periods=n)
    # Steady decline, then a sharp rally that lifts price over a still-falling MA.
    close = np.concatenate([np.linspace(100, 50, 240), np.linspace(50, 95, n - 240)])
    bars = pd.DataFrame({"open": close, "high": close * 1.02,
                         "low": close * 0.98, "close": close,
                         "volume": 1e6}, index=idx)

    close_s = pd.Series(close, index=idx)
    ma = close_s.rolling(50).mean()
    # Bars where price is above the average but the average is still falling —
    # precisely the bear-market-rally trap the extra condition exists to block.
    trap = idx[(close_s > ma) & (ma < ma.shift(10))]
    assert len(trap) > 0, "fixture failed to produce a bear-rally trap"

    res = CryptoETFVRPStrategy().backtest(bars, {"ticker": "IBIT"})
    if not res.trades.empty:
        entered = set(pd.to_datetime(res.trades["entry_date"]))
        assert not (entered & set(trap)), (
            "entered on a bear-market rally above a falling average"
        )


def test_max_concurrent_is_enforced():
    """`max_concurrent` was dead code in iron_condor_rules — 21 open vs a cap of 5."""
    bars = _bars(n=700, seed=23)
    s = CryptoETFVRPStrategy(max_concurrent=1, vol_rank_min=0.0)
    res = s.backtest(bars, {"ticker": "IBIT"})
    if not res.trades.empty:
        t = res.trades.copy()
        events = [(d, 1) for d in t["entry_date"]] + [(d, -1) for d in t["exit_date"]]
        events.sort(key=lambda e: (e[0], e[1]))
        live = peak = 0
        for _, delta in events:
            live += delta
            peak = max(peak, live)
        assert peak <= 1


def test_starting_capital_is_respected():
    """Four strategies silently hardcoded 100_000 and dropped this argument."""
    res = CryptoETFVRPStrategy().backtest(_bars(), {"ticker": "IBIT"},
                                          starting_capital=50_000)
    assert res.equity_curve.iloc[0] == pytest.approx(50_000, rel=0.05)


# ── signal + registry wiring ──────────────────────────────────────────────────

def test_generate_signal_returns_a_valid_result():
    bars = _bars()
    res = CryptoETFVRPStrategy().generate_signal(
        {"price_data": bars, "price": float(bars["close"].iloc[-1])}
    )
    assert res.signal in ("BUY", "SELL", "HOLD")
    assert 0.0 <= res.confidence <= 1.0


def test_signal_holds_without_enough_history():
    res = CryptoETFVRPStrategy().generate_signal({"price_data": _bars(n=10)})
    assert res.signal == "HOLD"


def test_registered_and_active():
    from alan_trader.strategies.registry import STRATEGY_METADATA, get_strategy

    meta = STRATEGY_METADATA["crypto_etf_vrp"]
    assert meta["status"] == "active"
    strategy = get_strategy("crypto_etf_vrp")
    assert isinstance(strategy, CryptoETFVRPStrategy)
    assert strategy.status == StrategyStatus.ACTIVE


def test_ui_params_are_well_formed():
    for p in CryptoETFVRPStrategy().get_backtest_ui_params():
        assert {"key", "label", "type", "default"} <= set(p)
