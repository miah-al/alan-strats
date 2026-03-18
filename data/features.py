"""
Feature engineering: price-based technicals, VIX, rates, news sentiment.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Price-based technical features
# ---------------------------------------------------------------------------

def add_price_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add returns, momentum, volatility, and candle features to OHLCV df."""
    df = df.copy()

    # Log returns
    df["ret_1d"] = np.log(df["close"] / df["close"].shift(1))
    df["ret_5d"] = np.log(df["close"] / df["close"].shift(5))
    df["ret_10d"] = np.log(df["close"] / df["close"].shift(10))
    df["ret_20d"] = np.log(df["close"] / df["close"].shift(20))

    # Realized volatility (rolling std of daily log returns)
    df["rvol_5d"] = df["ret_1d"].rolling(5).std() * np.sqrt(252)
    df["rvol_10d"] = df["ret_1d"].rolling(10).std() * np.sqrt(252)
    df["rvol_20d"] = df["ret_1d"].rolling(20).std() * np.sqrt(252)

    # Simple moving averages
    for w in [5, 10, 20, 50, 200]:
        df[f"sma_{w}"] = df["close"].rolling(w).mean()

    # Price relative to moving averages (normalized)
    for w in [5, 10, 20, 50, 200]:
        df[f"price_vs_sma{w}"] = (df["close"] - df[f"sma_{w}"]) / df[f"sma_{w}"]

    # RSI (manual, since polygon RSI may not cover full history easily)
    df["rsi_14"] = _rsi(df["close"], 14)
    df["rsi_7"] = _rsi(df["close"], 7)

    # MACD
    ema12 = df["close"].ewm(span=12, adjust=False).mean()
    ema26 = df["close"].ewm(span=26, adjust=False).mean()
    df["macd"] = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]

    # Bollinger Bands
    bb_mid = df["close"].rolling(20).mean()
    bb_std = df["close"].rolling(20).std()
    df["bb_upper"] = bb_mid + 2 * bb_std
    df["bb_lower"] = bb_mid - 2 * bb_std
    df["bb_pct"] = (df["close"] - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"] + 1e-9)

    # ATR
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift(1)).abs(),
        (df["low"] - df["close"].shift(1)).abs(),
    ], axis=1).max(axis=1)
    df["atr_14"] = tr.rolling(14).mean()
    df["atr_pct"] = df["atr_14"] / df["close"]

    # Volume features
    df["vol_sma20"] = df["volume"].rolling(20).mean()
    df["vol_ratio"] = df["volume"] / (df["vol_sma20"] + 1)

    # Stochastic Oscillator (%K, %D)
    lo14 = df["low"].rolling(14).min()
    hi14 = df["high"].rolling(14).max()
    df["stoch_k"] = (df["close"] - lo14) / (hi14 - lo14 + 1e-9) * 100
    df["stoch_d"] = df["stoch_k"].rolling(3).mean()

    # Williams %R
    df["williams_r"] = (hi14 - df["close"]) / (hi14 - lo14 + 1e-9) * -100

    # Rate of Change
    for w in [5, 10, 20]:
        df[f"roc_{w}"] = df["close"].pct_change(w) * 100

    # ADX (trend strength)
    df["adx_14"], df["adx_plus_di"], df["adx_minus_di"] = _adx(df, 14)

    # Chaikin Money Flow (20-day)
    mf_mult = ((df["close"] - df["low"]) - (df["high"] - df["close"])) / (df["high"] - df["low"] + 1e-9)
    df["cmf_20"] = (mf_mult * df["volume"]).rolling(20).sum() / (df["volume"].rolling(20).sum() + 1)

    # Realized return skewness (fat-tail / directional bias)
    df["ret_skew_20d"] = df["ret_1d"].rolling(20).skew()

    # Vol term structure: short-term vs long-term realized vol ratio
    df["rvol_ratio"] = df["rvol_5d"] / (df["rvol_20d"] + 1e-9)

    # Distance from 52-week high/low (breakout/support signals)
    df["dist_52w_high"] = (df["close"] / df["close"].rolling(252, min_periods=60).max()) - 1
    df["dist_52w_low"]  = (df["close"] / df["close"].rolling(252, min_periods=60).min()) - 1

    # Drop intermediate columns
    sma_cols = [f"sma_{w}" for w in [5, 10, 20, 50, 200]]
    df = df.drop(columns=sma_cols + ["bb_upper", "bb_lower", "vol_sma20"])

    return df


def _adx(df: pd.DataFrame, period: int = 14) -> tuple:
    """Return (adx, plus_di, minus_di) Series."""
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift(1)).abs(),
        (df["low"]  - df["close"].shift(1)).abs(),
    ], axis=1).max(axis=1)
    high_diff = df["high"].diff()
    low_diff  = -df["low"].diff()
    plus_dm  = high_diff.where((high_diff > low_diff) & (high_diff > 0), 0.0)
    minus_dm = low_diff.where((low_diff > high_diff) & (low_diff > 0), 0.0)
    atr      = tr.ewm(alpha=1 / period, adjust=False).mean()
    plus_di  = 100 * plus_dm.ewm(alpha=1 / period, adjust=False).mean()  / (atr + 1e-9)
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / (atr + 1e-9)
    dx  = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9)
    adx = dx.ewm(alpha=1 / period, adjust=False).mean()
    return adx, plus_di, minus_di


def _rsi(series: pd.Series, period: int) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / (loss + 1e-9)
    return 100 - 100 / (1 + rs)


# ---------------------------------------------------------------------------
# VIX and yield curve features
# ---------------------------------------------------------------------------

def merge_vix(spy_df: pd.DataFrame, vix_df: pd.DataFrame) -> pd.DataFrame:
    """Merge VIX close into SPY df and add derived features."""
    vix = vix_df[["close"]].rename(columns={"close": "vix"})
    df = spy_df.join(vix, how="left")
    df["vix"] = df["vix"].ffill()

    df["vix_chg_1d"] = df["vix"].pct_change(1)
    df["vix_chg_5d"] = df["vix"].pct_change(5)
    df["vix_sma10"] = df["vix"].rolling(10).mean()
    df["vix_vs_sma"] = (df["vix"] - df["vix_sma10"]) / (df["vix_sma10"] + 1e-9)

    # VIX regime (low < 15, mid 15-25, high > 25)
    df["vix_regime"] = pd.cut(df["vix"], bins=[0, 15, 25, 100], labels=[0, 1, 2]).astype(float)

    # IV Rank (0–100): where current VIX sits in its trailing 252-day range
    # High IV Rank → vol is rich → favours selling premium (iron condor, credit spreads)
    vix_min = df["vix"].rolling(252, min_periods=60).min()
    vix_max = df["vix"].rolling(252, min_periods=60).max()
    df["iv_rank"] = (df["vix"] - vix_min) / (vix_max - vix_min + 1e-9) * 100

    # IV Premium: implied vol (VIX) minus recent realised vol
    # Positive = options are "rich" → premium-selling strategies expected to profit
    if "rvol_20d" in df.columns:
        df["iv_rv_spread"] = df["vix"] - df["rvol_20d"] * 100   # both in % annualised
    else:
        df["iv_rv_spread"] = 0.0

    df = df.drop(columns=["vix_sma10"])
    return df


def merge_rates(df: pd.DataFrame, rate2y_df: pd.DataFrame, rate10y_df: pd.DataFrame) -> pd.DataFrame:
    """Merge 2Y/10Y yield data and add spread features."""
    df = df.join(rate2y_df[["close"]].rename(columns={"close": "rate_2y"}),  how="left")
    df = df.join(rate10y_df[["close"]].rename(columns={"close": "rate_10y"}), how="left")
    df["rate_2y"]  = df["rate_2y"].ffill()
    df["rate_10y"] = df["rate_10y"].ffill()

    df["yield_spread"]   = df["rate_10y"] - df["rate_2y"]
    df["rate_10y_chg5d"] = df["rate_10y"].diff(5)
    df["rate_2y_chg5d"]  = df["rate_2y"].diff(5)
    return df


def merge_macro(df: pd.DataFrame, macro_df: pd.DataFrame) -> pd.DataFrame:
    """
    Merge full macro dataset: yield curve (3M→30Y), SOFR, jobless claims.

    Derived features:
      curve_3m10y    — 10Y − 3M spread (classic recession predictor)
      curve_5y30y    — 30Y − 5Y (long-end steepness)
      curve_butterfly — 2×5Y − (2Y + 10Y) (curvature)
      sofr_spread    — 2Y rate − SOFR (market premium over overnight)
      claims_ma4w    — 4-week smoothed jobless claims level
      claims_chg4w   — deviation from 4-week MA (acceleration signal)
    """
    if macro_df is None or macro_df.empty:
        return df

    available = [c for c in [
        "rate_3m", "rate_6m", "rate_1y", "rate_5y", "rate_30y", "sofr", "jobless_claims"
    ] if c in macro_df.columns]

    if not available:
        return df

    df = df.join(macro_df[available], how="left")
    for c in available:
        df[c] = df[c].ffill()

    if "rate_3m" in df.columns and "rate_10y" in df.columns:
        df["curve_3m10y"] = df["rate_10y"] - df["rate_3m"]
    if "rate_5y" in df.columns and "rate_30y" in df.columns:
        df["curve_5y30y"] = df["rate_30y"] - df["rate_5y"]
    if all(c in df.columns for c in ["rate_2y", "rate_5y", "rate_10y"]):
        df["curve_butterfly"] = 2 * df["rate_5y"] - df["rate_2y"] - df["rate_10y"]
    if "sofr" in df.columns and "rate_2y" in df.columns:
        df["sofr_spread"] = df["rate_2y"] - df["sofr"]
    if "jobless_claims" in df.columns:
        df["claims_ma4w"]  = df["jobless_claims"].rolling(20).mean()
        df["claims_chg4w"] = df["jobless_claims"] - df["claims_ma4w"]

    return df


# ---------------------------------------------------------------------------
# News sentiment
# ---------------------------------------------------------------------------

def compute_sentiment(news_df: pd.DataFrame) -> pd.Series:
    """
    Compute daily average sentiment from news titles/descriptions.
    Uses a simple VADER-style approach or falls back to keyword scoring.
    Returns a Series indexed by date.
    """
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        analyzer = SentimentIntensityAnalyzer()

        def _score(row):
            text = f"{row.get('title', '')} {row.get('description', '')}"
            return analyzer.polarity_scores(text)["compound"]

        news_df = news_df.copy()
        news_df["sentiment"] = news_df.apply(_score, axis=1)
    except ImportError:
        logger.warning("vaderSentiment not installed — using keyword fallback. pip install vaderSentiment")
        news_df = news_df.copy()
        news_df["sentiment"] = news_df["title"].fillna("").apply(_keyword_sentiment)

    daily = news_df.groupby("date")["sentiment"].mean()
    return daily.rename("news_sentiment")


def _keyword_sentiment(text: str) -> float:
    text = text.lower()
    bull_words = ["rally", "surge", "gain", "growth", "beat", "record", "rise", "up", "bullish", "strong"]
    bear_words = ["crash", "drop", "plunge", "fear", "recession", "loss", "fall", "weak", "bearish", "down"]
    score = sum(1 for w in bull_words if w in text) - sum(1 for w in bear_words if w in text)
    return np.clip(score / 3, -1, 1)


def merge_sentiment(df: pd.DataFrame, sentiment: pd.Series) -> pd.DataFrame:
    df = df.join(sentiment, how="left")
    df["news_sentiment"] = df["news_sentiment"].fillna(0)
    df["sentiment_ma5"] = df["news_sentiment"].rolling(5).mean()
    return df


# ---------------------------------------------------------------------------
# Target label engineering
# ---------------------------------------------------------------------------

def create_labels(df: pd.DataFrame, forward_days: int = 5, threshold: float = 0.01) -> pd.DataFrame:
    """Legacy: 3-class direction labels (bear=0, neutral=1, bull=2)."""
    return create_labels_for_spread_type(df, "bull_call", forward_days, threshold)


def create_labels_for_spread_type(
    df: pd.DataFrame,
    spread_type: str = "bull_call",
    forward_days: int = 5,
    threshold: float = 0.01,
) -> pd.DataFrame:
    """
    Create labels tailored to the profitability condition of each spread type.

    All spread types use the same 3-class encoding:
      2 = ENTER  — conditions strongly favour this spread
      1 = SKIP   — uncertain / borderline
      0 = AVOID  — conditions unfavourable (would likely lose)

    The engine always enters when the model predicts class 2.

    Spread-specific logic
    ─────────────────────
    bull_call   debit  : enter when underlying moves UP   > +threshold
    bear_put    debit  : enter when underlying moves DOWN  < -threshold
    bull_put    credit : enter when underlying stays flat/up (doesn't fall past sold put)
    bear_call   credit : enter when underlying stays flat/down (doesn't rally past sold call)
    iron_condor credit : enter when move is SMALL and IV rank is HIGH (IV crush play)
    """
    df = df.copy()
    fwd_ret = np.log(df["close"].shift(-forward_days) / df["close"])
    df["fwd_ret"] = fwd_ret
    df["label"] = 1  # default: skip

    if spread_type == "bull_call":
        df.loc[fwd_ret > threshold, "label"] = 2
        df.loc[fwd_ret < -threshold, "label"] = 0

    elif spread_type == "bear_put":
        df.loc[fwd_ret < -threshold, "label"] = 2
        df.loc[fwd_ret > threshold, "label"] = 0

    elif spread_type == "bull_put":
        # Credit spread: profit if price stays above sold put → flat or up is good
        df.loc[fwd_ret > -threshold, "label"] = 2
        df.loc[fwd_ret < -2 * threshold, "label"] = 0   # big drop = full loss

    elif spread_type == "bear_call":
        # Credit spread: profit if price stays below sold call → flat or down is good
        df.loc[fwd_ret < threshold, "label"] = 2
        df.loc[fwd_ret > 2 * threshold, "label"] = 0    # big rally = full loss

    elif spread_type == "iron_condor":
        # 4-leg credit: profit if price stays range-bound AND IV is elevated
        condor_thresh = threshold * 2.5
        iv_rank = df["iv_rank"] if "iv_rank" in df.columns else pd.Series(50, index=df.index)
        enter = (fwd_ret.abs() < condor_thresh) & (iv_rank > 50)
        avoid = fwd_ret.abs() > condor_thresh * 2
        df.loc[enter, "label"] = 2
        df.loc[avoid, "label"] = 0

    elif spread_type == "long_straddle":
        # Debit: buy call + put; profit from big moves when vol is cheap
        iv_rank = df["iv_rank"] if "iv_rank" in df.columns else pd.Series(50, index=df.index)
        enter = (fwd_ret.abs() > threshold * 2) & (iv_rank < 40)
        avoid = (fwd_ret.abs() < threshold * 0.5) & (iv_rank > 60)
        df.loc[enter, "label"] = 2
        df.loc[avoid, "label"] = 0

    elif spread_type == "short_strangle":
        # Credit: sell OTM call + put; profit when price stays range-bound and IV is rich
        iv_rank = df["iv_rank"] if "iv_rank" in df.columns else pd.Series(50, index=df.index)
        enter = (fwd_ret.abs() < threshold * 1.5) & (iv_rank > 55)
        avoid = fwd_ret.abs() > threshold * 3
        df.loc[enter, "label"] = 2
        df.loc[avoid, "label"] = 0

    elif spread_type == "call_butterfly":
        # Debit: buy lower call, sell 2 mid calls, buy upper call; profit from mild bullish move
        enter = (fwd_ret > 0) & (fwd_ret < threshold * 2)
        avoid = (fwd_ret < -threshold) | (fwd_ret > threshold * 3)
        df.loc[enter, "label"] = 2
        df.loc[avoid, "label"] = 0

    else:
        df.loc[fwd_ret > threshold, "label"] = 2
        df.loc[fwd_ret < -threshold, "label"] = 0

    return df


# ---------------------------------------------------------------------------
# Final assembly
# ---------------------------------------------------------------------------

FEATURE_COLS = [
    # ── Returns & momentum ──────────────────────────────────────────────────
    "ret_1d", "ret_5d", "ret_10d", "ret_20d",
    "roc_5", "roc_10", "roc_20",
    # ── Realized volatility ─────────────────────────────────────────────────
    "rvol_5d", "rvol_10d", "rvol_20d",
    "rvol_ratio",           # vol term structure: short / long realized vol
    "ret_skew_20d",         # directional fat-tail bias
    # ── Oscillators ─────────────────────────────────────────────────────────
    "rsi_14", "rsi_7",
    "stoch_k", "stoch_d",
    "williams_r",
    "macd", "macd_signal", "macd_hist",
    # ── Trend & bands ───────────────────────────────────────────────────────
    "bb_pct",
    "atr_pct",
    "adx_14", "adx_plus_di", "adx_minus_di",
    "price_vs_sma5", "price_vs_sma10", "price_vs_sma20", "price_vs_sma50", "price_vs_sma200",
    "dist_52w_high", "dist_52w_low",
    # ── Volume / money flow ─────────────────────────────────────────────────
    "vol_ratio",
    "cmf_20",
    # ── Volatility / options signals ────────────────────────────────────────
    "vix", "vix_chg_1d", "vix_chg_5d", "vix_vs_sma", "vix_regime",
    "iv_rank", "iv_rv_spread",
    # ── Rates: 2Y / 10Y ─────────────────────────────────────────────────────
    "rate_2y", "rate_10y", "yield_spread", "rate_10y_chg5d", "rate_2y_chg5d",
    # ── Macro: full yield curve, SOFR, labour ───────────────────────────────
    "rate_3m", "rate_5y", "rate_30y",
    "curve_3m10y", "curve_5y30y", "curve_butterfly",
    "sofr", "sofr_spread",
    "jobless_claims", "claims_chg4w",
    # ── News sentiment ──────────────────────────────────────────────────────
    "news_sentiment", "sentiment_ma5",
]

# Human-readable names for spread types (for UI dropdowns)
SPREAD_TYPE_OPTIONS: dict[str, str] = {
    "bull_call":      "Bull Call Spread   (debit,  directional up)",
    "bear_put":       "Bear Put Spread    (debit,  directional down)",
    "bull_put":       "Bull Put Spread    (credit, neutral/bullish)",
    "bear_call":      "Bear Call Spread   (credit, neutral/bearish)",
    "iron_condor":    "Iron Condor        (credit, range-bound / IV crush)",
    "long_straddle":  "Long Straddle      (debit,  big move / vol expansion)",
    "short_strangle": "Short Strangle     (credit, range-bound / premium selling)",
    "call_butterfly": "Call Butterfly     (debit,  mild bullish / pin target)",
}


# ---------------------------------------------------------------------------
# Spread price regression target
# ---------------------------------------------------------------------------

def _bs_call(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Black-Scholes call price (scalar, no scipy import at module level)."""
    if T <= 0 or sigma <= 0:
        return max(0.0, S - K)
    from scipy.stats import norm
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    return float(S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2))


def add_spread_price_target(df: pd.DataFrame, spread_width: float = 5.0) -> pd.DataFrame:
    """
    Compute the theoretical ATM bull-call spread entry cost at each row using
    Black-Scholes (30-day DTE, ATM long call / ATM+width short call).

    Adds column 'spread_price_target'. Requires columns: close, vix, rate_10y.
    """
    df = df.copy()
    prices = np.empty(len(df))
    for i, (_, row) in enumerate(df.iterrows()):
        S  = float(row["close"])
        iv = float(row.get("vix", 18.0)) / 100.0
        r  = float(row.get("rate_10y", 0.045))
        T  = 30.0 / 252.0
        atm = round(S / 5.0) * 5.0
        otm = atm + spread_width
        prices[i] = max(0.0, _bs_call(S, atm, T, r, iv) - _bs_call(S, otm, T, r, iv))
    df["spread_price_target"] = prices
    return df


def build_feature_matrix(
    spy_df: pd.DataFrame,
    vix_df: pd.DataFrame,
    rate2y_df: pd.DataFrame,
    rate10y_df: pd.DataFrame,
    news_df: pd.DataFrame,
    forward_days: int = 5,
    threshold: float = 0.01,
    spread_type: str = "bull_call",
    macro_df: pd.DataFrame = None,
) -> pd.DataFrame:
    """Full pipeline: returns df with FEATURE_COLS + label, dropna."""
    df = add_price_features(spy_df)
    df = merge_vix(df, vix_df)
    df = merge_rates(df, rate2y_df, rate10y_df)
    if macro_df is not None and not macro_df.empty:
        df = merge_macro(df, macro_df)

    sentiment = compute_sentiment(news_df) if not news_df.empty else pd.Series(dtype=float, name="news_sentiment")
    df = merge_sentiment(df, sentiment)

    df = create_labels_for_spread_type(df, spread_type, forward_days, threshold)

    available = [c for c in FEATURE_COLS if c in df.columns]
    df = df[available + ["label", "fwd_ret", "close"]].dropna()
    return df
