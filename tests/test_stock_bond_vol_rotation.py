"""
Tests for stock_bond_vol_rotation. Offline + deterministic. Focus on the NEW
behaviour over VRPPremiumStrategy: dual-asset selection by richer forecast VRP
and correlation-regime sizing. (Leak-freedom / pricing inherited & tested in
test_vrp_premium.py.)
"""
import numpy as np
import pandas as pd
import pytest

from alan_trader.strategies.stock_bond_vol_rotation import StockBondVolRotationStrategy


def _asset(n=420, sigma=0.011, seed=0, start=400.0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2022-06-01", periods=n)
    close = start * np.exp(np.cumsum(rng.normal(0, sigma, n)))
    px = pd.DataFrame({"open": close, "high": close * 1.004, "low": close * 0.996,
                       "close": close, "volume": 1e6}, index=idx)
    return px, idx


def test_corr_sizing_monotone():
    s = StockBondVolRotationStrategy(corr_neg_size_mult=1.0, corr_pos_size_mult=0.4)
    # negative correlation → larger size than positive correlation
    assert s._corr_size_mult(-0.3) > s._corr_size_mult(0.0) > s._corr_size_mult(0.3)
    assert s._corr_size_mult(-0.3) == pytest.approx(1.0, abs=1e-6)
    assert s._corr_size_mult(0.3) == pytest.approx(0.4, abs=1e-6)


def test_requires_both_assets_and_ivs():
    s = StockBondVolRotationStrategy()
    spy, _ = _asset(seed=1)
    with pytest.raises(ValueError):
        s.backtest(spy, {"tlt": spy}, ticker="X")   # missing IVs


def test_backtest_runs_and_splits_by_asset():
    spy, idx = _asset(seed=1, start=400)
    tlt, _ = _asset(seed=2, start=95)
    realized = 0.011 * np.sqrt(252)
    iv_spy = pd.Series(realized + 0.05, index=idx)
    iv_tlt = pd.Series(realized + 0.05, index=tlt.index)
    vix = pd.Series(realized * 100, index=idx)
    s = StockBondVolRotationStrategy(warmup_bars=120, retrain_every=20)
    res = s.backtest(spy, {"tlt": tlt, "atm_iv_spy": iv_spy, "atm_iv_tlt": iv_tlt,
                           "vix": vix}, ticker="SPY_TLT")
    assert "error" not in res.metrics
    if not res.trades.empty:
        assert set(res.trades["asset"].unique()).issubset({"SPY", "TLT"})
        assert (res.trades["credit"] > 0).all()


def test_richer_vrp_asset_is_preferred():
    """If TLT carries a much richer premium than SPY, most trades go to TLT."""
    spy, idx = _asset(seed=3, start=400)
    tlt, _ = _asset(seed=4, start=95)
    realized = 0.011 * np.sqrt(252)
    iv_spy = pd.Series(realized + 0.01, index=idx)       # thin
    iv_tlt = pd.Series(realized + 0.12, index=tlt.index)  # rich
    vix = pd.Series(realized * 100, index=idx)
    s = StockBondVolRotationStrategy(warmup_bars=120)
    res = s.backtest(spy, {"tlt": tlt, "atm_iv_spy": iv_spy, "atm_iv_tlt": iv_tlt,
                           "vix": vix}, ticker="SPY_TLT")
    if not res.trades.empty:
        share_tlt = (res.trades["asset"] == "TLT").mean()
        assert share_tlt > 0.5
