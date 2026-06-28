"""
strategies/indicators.py — shared technical indicators + option pricing.

These helpers were previously copy-pasted (with small parameter drift) across
~10 strategy files: `_compute_ivr` had 4 near-identical copies, `_compute_adx`
3, `_compute_atr` 2, and `_bs_price` 5. That is how a fix lands in one file and
silently misses the others. This module is the single source.

Each function is parameterised so every prior per-strategy variant is reproduced
*exactly* — proven by tests/test_indicators.py (numerical-equivalence gate). The
only real differences between the old copies were:
  • compute_ivr  — the cold-start `min_periods` (60 vs 126)
  • compute_adx  — the warmup fill value (0.0 vs 20.0)

Black-Scholes lives in backtest/engine.py (the engine's pricer, with an optional
dividend yield q); we re-export it here so strategies have one pricer. The old
local `_bs_price` copies were exactly this with q=0 (the default).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Single canonical Black-Scholes. Old `_bs_price(S,K,T,r,sigma,ot)` == this with q=0.
from backtest.engine import bs_price  # noqa: F401  (re-exported)


def compute_ivr(vix: pd.Series, window: int = 252, min_periods: int = 60) -> pd.Series:
    """Rolling IV Rank: (vix − Nd_low) / (Nd_high − Nd_low), clipped to [0, 1].

    `min_periods` is the cold-start floor; below it the result is NaN (a short
    window inflates IVR because a 30-day range is far narrower than the true
    52-week range). Old call sites used 60 (iron_condor_*, fomc) or 126
    (ivr_credit_spread); pass the matching value to reproduce them.
    """
    roll_low  = vix.rolling(window, min_periods=min_periods).min()
    roll_high = vix.rolling(window, min_periods=min_periods).max()
    rng = roll_high - roll_low
    return ((vix - roll_low) / rng.replace(0, np.nan)).clip(0.0, 1.0)


def compute_atr(high: pd.Series, low: pd.Series, close: pd.Series,
                period: int = 14) -> pd.Series:
    """Average True Range — SMA of the true range over `period`
    (min_periods=period//2)."""
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=period // 2).mean()


def compute_adx(high: pd.Series, low: pd.Series, close: pd.Series,
                period: int = 14, warmup_fill: float = 20.0) -> pd.Series:
    """Average Directional Index — trend strength (not direction).

    `warmup_fill` is the value used where ADX is still undefined (the warmup
    window). Old call sites used 20.0 (earnings_vol_crush, iron_condor_ai) or
    0.0 (iron_condor_rules); pass the matching value to reproduce them.
    """
    prev_high  = high.shift(1)
    prev_low   = low.shift(1)
    prev_close = close.shift(1)

    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)

    plus_dm  = (high - prev_high).clip(lower=0.0).where((high - prev_high) > (prev_low - low), 0.0)
    minus_dm = (prev_low - low).clip(lower=0.0).where((prev_low - low) > (high - prev_high), 0.0)

    atr_s    = tr.rolling(period, min_periods=period // 2).mean()
    plus_di  = 100.0 * plus_dm.rolling(period,  min_periods=period // 2).mean() / atr_s.replace(0, np.nan)
    minus_di = 100.0 * minus_dm.rolling(period, min_periods=period // 2).mean() / atr_s.replace(0, np.nan)
    dx       = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.rolling(period, min_periods=period // 2).mean().fillna(warmup_fill)
