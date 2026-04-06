"""
generate_sample_data.py
-----------------------
Generates a realistic sample training dataset for the Iron Condor AI strategy.

Produces ~755 rows of daily SPY data from 2022-01-03 to 2024-12-31 with all
17 features used by IronCondorAI._build_feature_matrix(), plus date, ticker,
close_price, and label.

Run from the alan_trader project root:
    python data/generate_sample_data.py

Output:
    data/sample_ic_training_data.csv
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path

# ── Reproducibility ────────────────────────────────────────────────────────────
RNG = np.random.default_rng(42)

# ── Output path ───────────────────────────────────────────────────────────────
OUTPUT_PATH = Path(__file__).parent / "sample_ic_training_data.csv"


# ── 1. Trading calendar ───────────────────────────────────────────────────────
def build_trading_dates(start: str = "2022-01-03", end: str = "2024-12-31") -> pd.DatetimeIndex:
    return pd.bdate_range(start=start, end=end, freq="B")


# ── 2. SPY price path ─────────────────────────────────────────────────────────
def build_spy_price(dates: pd.DatetimeIndex) -> pd.Series:
    """
    Piecewise realistic SPY path:
      Jan 2022: ~460
      Oct 2022: ~360  (bear market, -22%)
      Jul 2023: ~450  (recovery)
      Dec 2024: ~500  (bull continuation)
    Daily returns driven by a regime-aware drift + vol model.
    """
    n = len(dates)
    prices = np.zeros(n)
    prices[0] = 460.0

    # Define regime breakpoints (indices) and their (daily_drift, daily_vol) parameters
    # Dates are approximate; convert to index fractions
    total = n
    regimes = [
        # (end_frac, drift_ann, vol_ann)
        (0.18,  -0.28, 0.22),   # Jan–Mar 2022: drawdown begins, -7% per yr equiv accelerated
        (0.37,  -0.45, 0.28),   # Apr–Sep 2022: acceleration of bear market
        (0.42,   0.30, 0.25),   # Oct 2022: sharp reversal / bear market low
        (0.60,   0.20, 0.18),   # Nov 2022 – Jun 2023: recovery
        (0.72,   0.22, 0.14),   # Jul–Nov 2023: continued recovery, lower vol
        (0.85,   0.18, 0.12),   # Dec 2023 – Jun 2024: bull, low vol
        (1.00,   0.20, 0.14),   # Jul–Dec 2024: moderate bull
    ]

    prev_end = 0
    for end_frac, drift_ann, vol_ann in regimes:
        end_idx = min(int(end_frac * total), total - 1)
        count = end_idx - prev_end
        if count <= 0:
            continue
        daily_drift = drift_ann / 252
        daily_vol = vol_ann / np.sqrt(252)
        returns = RNG.normal(daily_drift, daily_vol, count)
        for j in range(count):
            idx = prev_end + j + 1
            if idx < total:
                prices[idx] = prices[prev_end + j] * (1 + returns[j])
        prev_end = end_idx

    return pd.Series(prices, index=dates, name="close_price")


# ── 3. Realistic High/Low from Close ─────────────────────────────────────────
def build_high_low(close: pd.Series, vix_level: pd.Series):
    """High/low derived from close ± intraday range proportional to VIX."""
    intraday_range_frac = (vix_level / 100.0) / np.sqrt(252) * 1.5
    noise_h = RNG.uniform(0.3, 0.7, len(close))
    noise_l = 1.0 - noise_h
    half = close * intraday_range_frac
    high = close + half * noise_h
    low  = close - half * noise_l
    return high, low


# ── 4. Synthetic VIX path ─────────────────────────────────────────────────────
def build_vix(dates: pd.DatetimeIndex, close: pd.Series) -> pd.Series:
    """
    VIX inversely correlated with SPY returns, with regime-specific levels:
      2022 bear:   VIX 25–38
      2023 recov:  VIX 18–25 → 13–18
      2024 bull:   VIX 12–17
    """
    n = len(dates)
    ret = close.pct_change().fillna(0).values

    # Base VIX from piecewise mean
    total = n
    vix_base = np.zeros(n)
    regimes = [
        (0.18, 22.0),   # early 2022
        (0.37, 30.0),   # mid-2022 bear
        (0.42, 33.0),   # Oct 2022 peak fear
        (0.55, 24.0),   # late 2022 / early 2023
        (0.65, 19.0),   # mid-2023
        (0.72, 15.0),   # late 2023
        (0.85, 13.5),   # early-mid 2024
        (1.00, 14.5),   # late 2024 (slight uptick)
    ]
    prev_end = 0
    prev_level = 18.0
    for end_frac, level in regimes:
        end_idx = min(int(end_frac * total), total - 1)
        count = end_idx - prev_end
        if count <= 0:
            continue
        vix_base[prev_end:end_idx] = np.linspace(prev_level, level, count)
        prev_level = level
        prev_end = end_idx

    # Add return-shock component: large negative returns spike VIX
    shock = np.where(ret < -0.01, (-ret / 0.02) * 5.0, 0.0)  # shock in VIX points
    shock = np.clip(shock, 0, 20)

    # Add AR(1) noise
    ar_noise = np.zeros(n)
    ar_noise[0] = 0.0
    for i in range(1, n):
        ar_noise[i] = 0.85 * ar_noise[i - 1] + RNG.normal(0, 0.8)

    vix_raw = vix_base + shock + ar_noise
    vix_raw = np.clip(vix_raw, 10.0, 80.0)

    return pd.Series(vix_raw, index=dates, name="vix_level")


# ── 5. 10Y rate path ──────────────────────────────────────────────────────────
def build_rate10y(dates: pd.DatetimeIndex) -> pd.Series:
    """
    10Y yield path (as decimal):
      Jan 2022: ~1.7%
      Oct 2022: ~4.2%  (Fed hiking cycle)
      Dec 2023: ~3.9%
      Dec 2024: ~4.3%
    """
    n = len(dates)
    total = n
    segments = [
        (0.00, 0.017),
        (0.37, 0.042),
        (0.55, 0.038),
        (0.72, 0.039),
        (0.85, 0.043),
        (1.00, 0.043),
    ]
    rate = np.interp(
        np.linspace(0, 1, n),
        [s[0] for s in segments],
        [s[1] for s in segments],
    )
    noise = RNG.normal(0, 0.0008, n)
    ar_noise = np.zeros(n)
    for i in range(1, n):
        ar_noise[i] = 0.90 * ar_noise[i - 1] + noise[i]
    rate = np.clip(rate + ar_noise, 0.01, 0.06)
    return pd.Series(rate, index=dates, name="rate_10y")


# ── 6. 2Y rate path ───────────────────────────────────────────────────────────
def build_rate2y(dates: pd.DatetimeIndex, rate10y: pd.Series) -> pd.Series:
    """
    2Y tracks Fed closely; inverts in 2022-2023, then gradually un-inverts.
    """
    n = len(dates)
    spread_target = np.interp(
        np.linspace(0, 1, n),
        [0.00, 0.15, 0.42, 0.72, 0.85, 1.00],
        [0.010, -0.002, -0.012, -0.010, -0.004, 0.005],
    )
    noise = RNG.normal(0, 0.0005, n)
    ar_noise = np.zeros(n)
    for i in range(1, n):
        ar_noise[i] = 0.92 * ar_noise[i - 1] + noise[i]
    spread = spread_target + ar_noise
    rate2y = rate10y.values - spread
    rate2y = np.clip(rate2y, 0.005, 0.060)
    return pd.Series(rate2y, index=dates, name="rate_2y")


# ── 7. Compute all 17 features ────────────────────────────────────────────────
def compute_features(
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    vix: pd.Series,
    rate10y: pd.Series,
    rate2y: pd.Series,
) -> pd.DataFrame:
    iv_prx = vix / 100.0

    # IVR: VIX rank over trailing 252d window
    roll_low  = vix.rolling(252, min_periods=60).min()
    roll_high = vix.rolling(252, min_periods=60).max()
    rng_v = roll_high - roll_low
    ivr = ((vix - roll_low) / rng_v.replace(0, np.nan)).clip(0.0, 1.0)

    # Realized vol 20d
    realized_vol = close.pct_change().rolling(20, min_periods=10).std() * np.sqrt(252)

    # VRP
    vrp = iv_prx - realized_vol

    # ATR
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    atr = tr.rolling(14, min_periods=7).mean()
    atr_pct = atr / close.replace(0, np.nan)

    # Returns
    ret_5d  = close.pct_change(5)
    ret_20d = close.pct_change(20)

    # Distance from MA50
    ma50           = close.rolling(50, min_periods=20).mean()
    dist_from_ma50 = (close - ma50) / ma50.replace(0, np.nan)

    # VIX features
    vix_5d_change = vix.pct_change(5)
    vix_ma20      = vix.rolling(20, min_periods=10).mean()
    vix_ma_ratio  = vix / vix_ma20.replace(0, np.nan)

    # IV term slope proxy: VIX 5d diff / 5
    iv_term_slope = vix.diff(5) / 5.0

    # Put/call skew proxy: 1m vol / 3m vol
    vol_1m = close.pct_change().rolling(21, min_periods=10).std()
    vol_3m = close.pct_change().rolling(63, min_periods=20).std()
    put_call_skew = (vol_1m / vol_3m.replace(0, np.nan)).clip(0.5, 2.0)

    # Yield curve
    yield_curve = rate10y - rate2y

    # Calendar: trading days to month end
    days_to_month_end = pd.Series(
        [int((pd.Timestamp(d) + pd.offsets.MonthEnd(0) - pd.Timestamp(d)).days) for d in close.index],
        index=close.index,
        dtype=float,
    )

    df = pd.DataFrame({
        "ivr":               ivr,
        "iv_term_slope":     iv_term_slope,
        "put_call_skew":     put_call_skew,
        "atm_iv":            iv_prx,
        "realized_vol_20d":  realized_vol,
        "vrp":               vrp,
        "atr_pct":           atr_pct,
        "ret_5d":            ret_5d,
        "ret_20d":           ret_20d,
        "dist_from_ma50":    dist_from_ma50,
        "vix_level":         vix,
        "vix_5d_change":     vix_5d_change,
        "vix_ma_ratio":      vix_ma_ratio,
        "rate_10y":          rate10y,
        "yield_curve_2y10y": yield_curve,
        "days_to_month_end": days_to_month_end,
        "oi_put_call_proxy": put_call_skew,   # same proxy as put_call_skew per strategy code
        "close_price":       close,
    })
    return df.ffill().bfill()


# ── 8. Label construction (mirrors _build_labels in iron_condor_ai.py) ────────
def build_labels(close: pd.Series, realized_vol: pd.Series, n_forward: int = 45) -> pd.Series:
    """
    1 if max price excursion over next n_forward days ≤ 1-sigma N-day move.
    Mirrors the exact logic in iron_condor_ai._build_labels().
    """
    n = len(close)
    labels = np.full(n, np.nan)
    close_vals = close.values
    rv_vals    = realized_vol.values

    for i in range(n - n_forward):
        ann_vol = rv_vals[i]
        if np.isnan(ann_vol) or ann_vol <= 0:
            continue
        sigma_n = ann_vol * np.sqrt(n_forward / 252.0)
        entry_px = close_vals[i]
        if entry_px <= 0:
            continue
        fwd = close_vals[i + 1: i + 1 + n_forward]
        high_ret = (fwd.max() - entry_px) / entry_px
        low_ret  = (entry_px - fwd.min()) / entry_px
        max_exc  = max(high_ret, low_ret)
        labels[i] = 1.0 if max_exc <= sigma_n else 0.0

    return pd.Series(labels, index=close.index, name="label")


# ── 9. Assemble and write CSV ─────────────────────────────────────────────────
def main():
    print("Building trading dates…")
    dates = build_trading_dates()

    print(f"  {len(dates)} trading days from {dates[0].date()} to {dates[-1].date()}")

    print("Building SPY price path…")
    close = build_spy_price(dates)

    print("Building VIX path…")
    vix = build_vix(dates, close)

    print("Building rate paths…")
    rate10y = build_rate10y(dates)
    rate2y  = build_rate2y(dates, rate10y)

    print("Building high/low series…")
    high, low = build_high_low(close, vix)

    print("Computing features…")
    features = compute_features(close, high, low, vix, rate10y, rate2y)

    print("Building labels (N=45 days forward)…")
    labels = build_labels(features["close_price"], features["realized_vol_20d"], n_forward=45)

    print("Assembling final DataFrame…")
    out = pd.DataFrame()
    out["date"]       = dates
    out["ticker"]     = "SPY"
    out["close_price"] = features["close_price"].values

    feature_cols = [
        "ivr", "iv_term_slope", "put_call_skew", "atm_iv", "realized_vol_20d",
        "vrp", "atr_pct", "ret_5d", "ret_20d", "dist_from_ma50",
        "vix_level", "vix_5d_change", "vix_ma_ratio", "rate_10y",
        "yield_curve_2y10y", "days_to_month_end", "oi_put_call_proxy",
    ]
    for col in feature_cols:
        out[col] = features[col].values

    out["label"] = labels.values

    # Round for readability
    float_cols = [c for c in out.columns if c not in ("date", "ticker", "label", "days_to_month_end")]
    out[float_cols] = out[float_cols].round(6)
    out["days_to_month_end"] = out["days_to_month_end"].round(0).astype("Int64")
    out["label"] = out["label"].round(0)

    # Drop rows where label is NaN (last n_forward rows + early warmup NaNs)
    out_clean = out.dropna(subset=["label"]).reset_index(drop=True)

    print(f"\nWriting {len(out_clean)} rows to {OUTPUT_PATH}")
    out_clean.to_csv(OUTPUT_PATH, index=False)

    # ── Summary stats ─────────────────────────────────────────────────────────
    label_dist = out_clean["label"].value_counts().sort_index()
    positive_rate = out_clean["label"].mean()
    print(f"\nLabel distribution:\n{label_dist.to_string()}")
    print(f"Positive rate (IC profitable): {positive_rate:.1%}")
    print(f"\nColumn count: {len(out_clean.columns)} columns")
    print(f"Columns: {list(out_clean.columns)}")

    print(f"\nSPY close range: ${out_clean['close_price'].min():.1f} – ${out_clean['close_price'].max():.1f}")
    print(f"VIX range: {out_clean['vix_level'].min():.1f} – {out_clean['vix_level'].max():.1f}")
    print(f"IVR range: {out_clean['ivr'].min():.2f} – {out_clean['ivr'].max():.2f}")
    print(f"\nDone. File written to: {OUTPUT_PATH.resolve()}")


if __name__ == "__main__":
    main()
