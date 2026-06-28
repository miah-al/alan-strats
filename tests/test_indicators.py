"""
Numerical-equivalence gate for the consolidated strategies/indicators.py.

Before strategies/indicators.py existed, each indicator was copy-pasted across
~10 strategy files. This test re-implements every *old* variant verbatim and
asserts the new canonical function reproduces it bit-for-bit on synthetic data.
If a future edit to indicators.py changes any strategy's numbers, this fails.
"""
import numpy as np
import pandas as pd
import pytest

from strategies.indicators import compute_ivr, compute_atr, compute_adx, bs_price


# ── deterministic synthetic OHLC + VIX ────────────────────────────────────────
def _data(n=400, seed=7):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2021-01-01", periods=n, freq="B")
    close = pd.Series(100 + np.cumsum(rng.normal(0, 1.0, n)), index=idx).abs() + 5
    high  = close + rng.uniform(0.1, 2.0, n)
    low   = close - rng.uniform(0.1, 2.0, n)
    vix   = pd.Series(15 + 8 * np.abs(rng.normal(0, 1, n)), index=idx)
    return high, low, close, vix


def _eq(a: pd.Series, b: pd.Series):
    np.testing.assert_allclose(a.values, b.values, rtol=1e-12, atol=1e-12, equal_nan=True)


# ── OLD variants, copied verbatim from the pre-refactor strategy files ────────
def _old_ivr(vix, window, min_periods):
    roll_low  = vix.rolling(window, min_periods=min_periods).min()
    roll_high = vix.rolling(window, min_periods=min_periods).max()
    rng = roll_high - roll_low
    ivr = (vix - roll_low) / rng.replace(0, np.nan)
    return ivr.clip(0.0, 1.0)


def _old_atr(high, low, close, period=14):
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=period // 2).mean()


def _old_adx_others(high, low, close, period=14):   # earnings_vol_crush / iron_condor_ai
    ph, pl, pc = high.shift(1), low.shift(1), close.shift(1)
    tr  = pd.concat([high - low, (high - pc).abs(), (low - pc).abs()], axis=1).max(axis=1)
    dmp = (high - ph).clip(lower=0.0).where((high - ph) > (pl - low), 0.0)
    dmm = (pl - low).clip(lower=0.0).where((pl - low) > (high - ph), 0.0)
    atr_s = tr.rolling(period, min_periods=period // 2).mean()
    dip   = 100 * dmp.rolling(period, min_periods=period // 2).mean() / atr_s.replace(0, np.nan)
    dim   = 100 * dmm.rolling(period, min_periods=period // 2).mean() / atr_s.replace(0, np.nan)
    dx    = 100 * (dip - dim).abs() / (dip + dim).replace(0, np.nan)
    return dx.rolling(period, min_periods=period // 2).mean().fillna(20.0)


def _old_adx_rules(high, low, close, period=14):    # iron_condor_rules
    prev_high, prev_low, prev_close = high.shift(1), low.shift(1), close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    dm_plus  = (high - prev_high).clip(lower=0.0)
    dm_minus = (prev_low - low).clip(lower=0.0)
    dm_plus  = dm_plus.where(dm_plus > dm_minus, 0.0)
    dm_minus = dm_minus.where(dm_minus > dm_plus, 0.0)
    atr   = tr.rolling(period, min_periods=period // 2).mean()
    di_plus  = 100.0 * dm_plus.rolling(period, min_periods=period // 2).mean() / atr.replace(0, np.nan)
    di_minus = 100.0 * dm_minus.rolling(period, min_periods=period // 2).mean() / atr.replace(0, np.nan)
    dx = 100.0 * (di_plus - di_minus).abs() / (di_plus + di_minus).replace(0, np.nan)
    adx = dx.rolling(period, min_periods=period // 2).mean()
    return adx.fillna(0.0)


def _old_bs(S, K, T, r, sigma, option_type):
    from scipy.stats import norm
    if T <= 0 or sigma <= 0 or S <= 0:
        return max(0.0, (S - K) if option_type == "call" else (K - S))
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    if option_type == "call":
        return float(S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2))
    return float(K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1))


# ── equivalence assertions ────────────────────────────────────────────────────
@pytest.mark.parametrize("min_periods", [60, 126])
def test_ivr_matches_old(min_periods):
    _, _, _, vix = _data()
    _eq(compute_ivr(vix, 252, min_periods), _old_ivr(vix, 252, min_periods))


def test_atr_matches_old():
    high, low, close, _ = _data()
    _eq(compute_atr(high, low, close), _old_atr(high, low, close))


def test_adx_matches_others_variant():
    high, low, close, _ = _data()
    _eq(compute_adx(high, low, close, warmup_fill=20.0), _old_adx_others(high, low, close))


def test_adx_matches_rules_variant():
    high, low, close, _ = _data()
    _eq(compute_adx(high, low, close, warmup_fill=0.0), _old_adx_rules(high, low, close))


def test_bs_price_matches_old():
    grid = [(100, 95, 0.25, 0.04, 0.20, "call"), (100, 105, 0.5, 0.04, 0.30, "put"),
            (50, 50, 0.08, 0.045, 0.15, "call"), (200, 180, 1.0, 0.03, 0.40, "put"),
            (100, 100, 0.0, 0.04, 0.2, "call"), (100, 100, 0.25, 0.04, 0.0, "put")]
    for S, K, T, r, sig, ot in grid:
        assert abs(bs_price(S, K, T, r, sig, ot) - _old_bs(S, K, T, r, sig, ot)) < 1e-9
