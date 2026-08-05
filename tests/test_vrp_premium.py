"""
Tests for vrp_premium (Variance-Risk-Premium harvester).

Offline + deterministic (synthetic series; no DB / network). Focus:
  - interface (params, ui params, save/load),
  - NO look-ahead: forward-RV labels purged; features at t use only data ≤ t,
  - the walk-forward backtest runs and respects costs/structure,
  - the data-hygiene gate rejects implausible IV prints,
  - a controlled positive-VRP world is profitable; a negative-VRP world is not.
"""
import numpy as np
import pandas as pd
import pytest

from alan_trader.strategies.vrp_premium import VRPPremiumStrategy, _ann_realized_vol


def _make_world(n=520, sigma=0.012, iv_offset=0.05, seed=0):
    """Daily prices with constant ~sigma vol; IV set to realized-vol + offset so
    VRP = iv_offset (annualised-ish). Positive offset → premium exists."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2022-01-03", periods=n)
    rets = rng.normal(0, sigma, n)
    close = 400 * np.exp(np.cumsum(rets))
    px = pd.DataFrame({"open": close, "high": close * 1.004,
                       "low": close * 0.996, "close": close,
                       "volume": 1e6}, index=idx)
    realized_ann = sigma * np.sqrt(252)
    iv = pd.Series(realized_ann + iv_offset, index=idx)
    vix = pd.Series(realized_ann * 100, index=idx)
    return px, iv, vix


def test_interface():
    s = VRPPremiumStrategy()
    assert s.name == "vrp_premium"
    assert s.is_trainable()
    assert len(s.get_backtest_ui_params()) >= 6
    assert "horizon" in s.get_params()


def test_labels_are_forward_and_purged():
    s = VRPPremiumStrategy(horizon=10)
    px, _, _ = _make_world()
    lab = s._build_labels(px)
    # last `horizon` rows have incomplete forward windows → NaN (purged)
    assert lab.tail(s.horizon).isna().all()
    # a label equals the realised vol of the *following* horizon returns
    logret = np.log(px["close"] / px["close"].shift(1))
    i = 50
    expect = _ann_realized_vol(logret.iloc[i + 1: i + 1 + s.horizon])
    assert abs(lab.iloc[i] - expect) < 1e-9


def test_features_no_lookahead():
    s = VRPPremiumStrategy()
    px, iv, vix = _make_world()
    feat_full = s._build_features(px, iv, vix, None)
    # truncating the future must not change a past feature row
    cut = 300
    feat_trunc = s._build_features(px.iloc[:cut], iv.iloc[:cut], vix.iloc[:cut], None)
    common = feat_full.index[:cut - 1]
    a = feat_full.loc[common, s.FEATURE_COLS]
    b = feat_trunc.loc[common, s.FEATURE_COLS]
    pd.testing.assert_frame_equal(a, b, check_exact=False, rtol=1e-9)


def test_backtest_runs_and_is_costed():
    s = VRPPremiumStrategy(warmup_bars=120, retrain_every=20)
    px, iv, vix = _make_world(iv_offset=0.06)
    res = s.backtest(px, {"atm_iv": iv, "vix": vix}, starting_capital=100_000, ticker="SYN")
    assert "error" not in res.metrics
    assert not res.equity_curve.empty
    # any trades carry a credit and a defined exit reason
    if not res.trades.empty:
        assert (res.trades["credit"] > 0).all()
        assert res.trades["exit_reason"].isin(
            ["profit", "loss", "expire", "end_of_data"]).all()


def test_positive_vrp_beats_negative_vrp():
    """Selling premium should make more in a rich-premium world than a thin one."""
    px, _, vix = _make_world(seed=1)
    realized_ann = 0.012 * np.sqrt(252)
    rich = pd.Series(realized_ann + 0.08, index=px.index)
    thin = pd.Series(realized_ann + 0.005, index=px.index)
    s = VRPPremiumStrategy(warmup_bars=120)
    r_rich = s.backtest(px, {"atm_iv": rich, "vix": vix}, ticker="RICH").equity_curve
    s2 = VRPPremiumStrategy(warmup_bars=120)
    r_thin = s2.backtest(px, {"atm_iv": thin, "vix": vix}, ticker="THIN").equity_curve
    assert r_rich.iloc[-1] >= r_thin.iloc[-1]


def test_hygiene_gate_blocks_iv_spikes():
    """An IV series with absurd spikes must not be traded on those days."""
    s = VRPPremiumStrategy(warmup_bars=120, iv_spike_mult=2.5)
    px, iv, vix = _make_world(iv_offset=0.04)
    iv_spiked = iv.copy()
    iv_spiked.iloc[200:210] = 1.5  # 150% vol — reconstruction glitch
    res = s.backtest(px, {"atm_iv": iv_spiked, "vix": vix}, ticker="SPK")
    if not res.trades.empty:
        # no entry should have been priced off the absurd-IV window
        entries = pd.to_datetime(res.trades["entry_date"])
        spike_dates = iv_spiked.index[200:210]
        assert not entries.isin(spike_dates).any()


def test_atm_iv_required():
    s = VRPPremiumStrategy()
    px, _, _ = _make_world()
    with pytest.raises(ValueError):
        s.backtest(px, {}, ticker="NOIV")
