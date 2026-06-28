"""engine/screener.py — UI-agnostic scoring and data-fetch logic extracted from dashboard/tabs/strategy_screener.py"""

from __future__ import annotations

import calendar
import logging
import math as _math
import pickle
from datetime import date, timedelta
from pathlib import Path as _Path
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── Universes ──────────────────────────────────────────────────────────────────

UNIVERSES: dict[str, list[str]] = {
    "ETF Core":   ["SPY", "QQQ", "IWM", "GLD", "TLT", "EEM", "XLF", "XLE", "XLK", "XLV"],
    "Index ETFs": ["SPY", "QQQ", "DIA", "IWM", "MDY", "VTI", "VEA", "VWO"],
    "Mega Cap":   ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "JPM"],
    "High IV":    ["TSLA", "NVDA", "MSTR", "COIN", "PLTR", "ARKK", "SOXL", "TQQQ"],
}

# ── Iron Condor AI model constants ─────────────────────────────────────────────

_IC_AI_MODELS_DIR = _Path(__file__).parent.parent / "saved_models"
_IC_AI_FEATURE_COLS = [
    "ivr", "iv_term_slope", "put_call_skew", "atm_iv", "realized_vol_20d",
    "vrp", "atr_pct", "ret_5d", "ret_20d", "dist_from_ma50",
    "vix_level", "vix_5d_change", "vix_ma_ratio", "rate_10y",
    "yield_curve_2y10y", "days_to_month_end", "oi_put_call_proxy",
]

# ── Default params ─────────────────────────────────────────────────────────────

_DEFAULT_PARAMS = {
    "iron_condor_rules": {
        "ivr_min": 0.20, "vix_min": 14.0, "vix_max": 45.0,
        "adx_max": 35.0, "atr_pct_max": 0.030,
    },
    "iron_condor_ai": {
        "ivr_min": 0.20, "vix_min": 14.0, "vix_max": 45.0,
        "adx_max": 35.0, "atr_pct_max": 0.030,
    },
    "ivr_credit_spread": {
        "ivr_min": 0.40, "vix_max": 50.0,
    },
    "broken_wing_butterfly": {
        "ivr_max": 0.35, "adx_max": 28.0, "vix_max": 30.0,
    },
    "calendar_spread": {
        "adx_max": 22.0, "vix_min": 14.0, "vix_max": 25.0,
        "hv_iv_spread_min": 0.03,
    },
    "earnings_straddle": {
        "ivr_min": 0.60, "atm_iv_min": 0.40, "implied_move_min": 0.05,
        "dte_to_earnings_min": 5, "dte_to_earnings_max": 10,
    },
    "wheel_strategy": {
        "ivr_min": 0.40, "adx_min": 15.0, "adx_max": 30.0, "vix_max": 35.0,
    },
    "bull_put_spread": {
        "ivr_min": 0.40, "adx_max": 30.0, "vix_max": 35.0,
    },
    "vix_term_structure": {
        "vix_max": 45.0, "threshold_short": 0.40, "threshold_long": 0.60,
    },
    "earnings_vol_crush": {
        "min_gap_pct": 0.03, "min_confidence": 0.60, "vix_max": 45.0,
    },
    "momentum_regime_spread": {
        "confidence_threshold": 0.55, "vix_max": 40.0,
    },
    "covered_call_ai": {
        "min_ivr": 0.30, "aggressive_delta": 0.30, "conservative_delta": 0.15,
    },
    "rs_credit_spread": {
        "min_confidence": 0.60, "adx_max": 30.0, "vix_max": 40.0,
    },
    "put_steal": {
        "nii_threshold": 0.01, "itm_pct": 0.10, "vix_max": 40.0, "iv_max": 0.60,
    },
    "hmm_regime": {
        "vix_ceiling": 40.0, "regime_confidence_min": 0.55,
    },
    "expiry_max_pain": {
        "vix_ceiling": 25.0, "min_dist_pct": 0.005, "max_dist_pct": 0.035,
    },
    "short_squeeze_detector": {
        "max_vix": 32.0, "volume_ratio_min": 2.5, "short_int_min": 0.20,
        "signal_threshold": 0.55,
    },
    "tail_risk_put_spread": {
        "vix_max_at_entry": 35.0, "long_otm_pct": 0.07, "short_otm_pct": 0.18,
        "dte_target": 75,
    },
    "news_sentiment_nlp": {
        "vix_max": 35.0, "sentiment_z_threshold": 2.0, "min_article_count": 5,
        "signal_threshold": 0.55,
    },
}

# ── Indicator helpers (price-only, no options needed) ─────────────────────────

def _atr(high: pd.Series, low: pd.Series, close: pd.Series, p: int = 14) -> float:
    prev = close.shift(1)
    tr   = pd.concat([high - low, (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
    s    = tr.rolling(p, min_periods=max(1, p // 2)).mean()
    return float(s.iloc[-1]) if not s.empty else 0.0


def _adx(high: pd.Series, low: pd.Series, close: pd.Series, p: int = 14) -> float:
    ph, pl, pc = high.shift(1), low.shift(1), close.shift(1)
    tr  = pd.concat([high - low, (high - pc).abs(), (low - pc).abs()], axis=1).max(axis=1)
    dmp = (high - ph).clip(lower=0.0)
    dmm = (pl - low).clip(lower=0.0)
    dmp = dmp.where(dmp > dmm, 0.0)
    dmm = dmm.where(dmm > dmp, 0.0)
    atr_s = tr.rolling(p,  min_periods=max(1, p // 2)).mean()
    dip   = 100.0 * dmp.rolling(p, min_periods=max(1, p // 2)).mean() / atr_s.replace(0, np.nan)
    dim   = 100.0 * dmm.rolling(p, min_periods=max(1, p // 2)).mean() / atr_s.replace(0, np.nan)
    dx    = 100.0 * (dip - dim).abs() / (dip + dim).replace(0, np.nan)
    adx_s = dx.rolling(p, min_periods=max(1, p // 2)).mean().fillna(0.0)
    return float(adx_s.iloc[-1])


def _ma200(close: pd.Series) -> Optional[float]:
    if len(close) < 20:
        return None
    window = min(200, len(close))
    return float(close.rolling(window, min_periods=20).mean().iloc[-1])


def _vix_ivr(vix_series: pd.Series, window: int = 252) -> float:
    """Fallback IVR from VIX when options data unavailable."""
    if len(vix_series) < 30:
        return 0.0
    lo  = vix_series.rolling(window, min_periods=60).min()
    hi  = vix_series.rolling(window, min_periods=60).max()
    rng = float(hi.iloc[-1]) - float(lo.iloc[-1])
    return float(np.clip((vix_series.iloc[-1] - lo.iloc[-1]) / rng, 0.0, 1.0)) if rng > 0 else 0.0


def _vix_20d_avg(vix_series: pd.Series) -> float:
    if len(vix_series) < 5:
        return float(vix_series.mean()) if not vix_series.empty else 20.0
    return float(vix_series.tail(20).mean())


def _approx_credit(price: float, iv: float) -> float:
    """Rough IC credit: spot × IV × √(45/252) × 0.38  (2-leg OTM BS proxy)."""
    return price * iv * np.sqrt(45 / 252) * 0.38


# ── Scoring functions ──────────────────────────────────────────────────────────

def _score_ic_rules(
    ticker: str,
    price_df: pd.DataFrame,
    vix_series: pd.Series,
    iv_metrics: dict,
    params: dict,
) -> Optional[dict]:
    if price_df.empty or len(price_df) < 20:
        return None
    try:
        close = price_df["close"].astype(float)
        high  = price_df.get("high",  close).astype(float)
        low   = price_df.get("low",   close).astype(float)

        latest_price = float(close.iloc[-1])
        latest_vix   = float(vix_series.iloc[-1]) if not vix_series.empty else 0.0
        latest_adx   = _adx(high, low, close)
        latest_atr   = _atr(high, low, close)
        atr_pct      = latest_atr / latest_price if latest_price > 0 else 0.0  # decimal (0.0176 = 1.76%)

        atm_iv         = iv_metrics.get("atm_iv")
        ivr            = iv_metrics.get("ivr")
        ivr_confidence = iv_metrics.get("ivr_confidence", "none")
        vrp            = iv_metrics.get("vrp")
        hv20           = iv_metrics.get("hv20")
        iv_over_hv     = iv_metrics.get("iv_over_hv")
        iv_source      = iv_metrics.get("iv_source", "no_options_data")

        if atm_iv is None:
            atm_iv = latest_vix / 100.0
        if ivr is None:
            ivr            = _vix_ivr(vix_series)
            ivr_confidence = "low (VIX fallback)"

        ivr_ok = ivr  >= params["ivr_min"]
        vix_ok = params["vix_min"] <= latest_vix <= params["vix_max"]
        adx_ok = latest_adx <= params["adx_max"]
        atr_ok = atr_pct    <= params["atr_pct_max"]

        n_pass = sum([ivr_ok, vix_ok, adx_ok, atr_ok])

        score = (
            ivr * 40
            + max(0, 1 - latest_adx / 50)          * 30
            + max(0, 1 - atr_pct / 0.03)            * 20
            + (10 if vix_ok else 0)
        )

        return {
            "Ticker":       ticker,
            "Price":        latest_price,
            "ATM IV":       atm_iv,
            "IVR":          ivr,
            "IVR conf":     ivr_confidence,
            "VRP":          vrp,
            "HV20":         hv20,
            "IV/HV":        iv_over_hv,
            "VIX":          latest_vix,
            "ADX":          latest_adx,
            "ATR%":         atr_pct,
            "~Credit":      _approx_credit(latest_price, atm_iv),
            "IV source":    iv_source,
            "ivr_ok":       ivr_ok,
            "vix_ok":       vix_ok,
            "adx_ok":       adx_ok,
            "atr_ok":       atr_ok,
            "n_pass":       n_pass,
            "all_pass":     n_pass == 4,
            "score":        score,
        }
    except Exception as e:
        logger.warning(f"Score error for {ticker}: {e}")
        return None


# ── Iron Condor AI — model helpers ────────────────────────────────────────────

def _score_ic_ai(
    ticker: str,
    price_df: pd.DataFrame,
    vix_series: pd.Series,
    iv_metrics: dict,
    params: dict,
) -> Optional[dict]:
    """AI iron-condor score.

    Reuses _score_ic_rules for the displayed metric columns (IVR/VIX/ADX/ATR),
    then OVERRIDES the Score and gate with the gradient-boosting model's
    P(range-bound). The feature row is built with the strategy's OWN
    _build_feature_matrix and scored via its generate_signal(), so screener
    features are guaranteed identical to what the model was trained on — no
    separate feature list to drift out of sync. When no trained model exists
    the strategy's heuristic fallback is used and flagged via _ai_mode.
    """
    base = _score_ic_rules(ticker, price_df, vix_series, iv_metrics, params)
    if base is None:
        return None
    try:
        from strategies.iron_condor_ai import IronCondorAIStrategy, _build_feature_matrix

        idx   = pd.to_datetime(price_df.index)
        close = pd.Series(price_df["close"].astype(float).values, index=idx)
        high  = pd.Series(price_df.get("high", price_df["close"]).astype(float).values, index=idx)
        low   = pd.Series(price_df.get("low",  price_df["close"]).astype(float).values, index=idx)

        if vix_series is not None and not vix_series.empty:
            vix_al = (pd.Series(vix_series.values, index=pd.to_datetime(vix_series.index))
                        .reindex(idx).ffill().bfill())
        else:
            vix_al = pd.Series(20.0, index=idx)

        feat_df = _build_feature_matrix(close, high, low, vix_al, None, None)

        strat  = IronCondorAIStrategy()
        loaded = strat.load_model(ticker) or strat.load_model("default")
        snap   = {"vix": float(vix_al.iloc[-1]), "price": float(close.iloc[-1]),
                  "features_df": feat_df}
        sig    = strat.generate_signal(snap)

        prob = float(sig.confidence)
        mode = sig.metadata.get("mode", "model" if loaded else "heuristic")
        ai_pass = (sig.signal == "SELL")

        base["score"]         = round(prob * 100, 1)
        base["all_pass"]      = bool(ai_pass)
        base["n_pass"]        = 4 if ai_pass else (1 if prob > 0 else 0)
        base["_ai_prob"]      = prob
        base["_ai_mode"]      = mode
        base["_ai_threshold"] = strat.signal_threshold
    except Exception as e:
        logger.warning(f"IC-AI score error for {ticker}: {e}")
        base["_ai_mode"] = "error"
        base["score"]    = 0.0
        base["all_pass"] = False
        base["n_pass"]   = 0
    return base


def _ic_ai_any_model_exists() -> bool:
    return _IC_AI_MODELS_DIR.exists() and any(_IC_AI_MODELS_DIR.glob("iron_condor_ai_*.pkl"))


def _load_ic_ai_model(ticker: str):
    """Load saved IC AI model for ticker, then default. Returns (model, saved_at_str) or (None, None)."""
    import datetime as _dt
    for name in [f"iron_condor_ai_{ticker.lower()}.pkl", "iron_condor_ai_default.pkl"]:
        p = _IC_AI_MODELS_DIR / name
        if p.exists():
            saved_at = _dt.datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            with open(p, "rb") as f:
                return pickle.load(f), saved_at
    return None, None


def _build_ic_ai_feat_row(
    price_df: pd.DataFrame, vix_series: pd.Series, iv_metrics: dict
) -> pd.DataFrame:
    """Build 1-row feature DataFrame for IC AI model from screener data."""
    close = price_df["close"].astype(float)
    high  = price_df.get("high", close).astype(float)
    low   = price_df.get("low",  close).astype(float)
    spot  = float(close.iloc[-1])

    ret_5d    = float(close.iloc[-1] / close.iloc[-6]  - 1) if len(close) >= 6  else 0.0
    ret_20d   = float(close.iloc[-1] / close.iloc[-21] - 1) if len(close) >= 21 else 0.0
    ma50      = float(close.rolling(50, min_periods=20).mean().iloc[-1]) if len(close) >= 20 else spot
    dist_ma50 = (spot - ma50) / ma50 if ma50 > 0 else 0.0
    atr_pct   = _atr(high, low, close) / spot if spot > 0 else 0.0

    log_ret = np.log(close / close.shift(1)).dropna()
    rv20    = float(log_ret.tail(20).std() * np.sqrt(252)) if len(log_ret) >= 10 else 0.0

    vix_val   = float(vix_series.iloc[-1])  if not vix_series.empty else 20.0
    vix_5d_ch = float(vix_series.iloc[-1] / vix_series.iloc[-6] - 1) if len(vix_series) >= 6 else 0.0
    vix_ma20  = float(vix_series.tail(20).mean()) if len(vix_series) >= 10 else vix_val
    vix_ma_r  = vix_val / vix_ma20 if vix_ma20 > 0 else 1.0

    atm_iv = float(iv_metrics.get("atm_iv") or vix_val / 100)
    ivr    = float(iv_metrics.get("ivr")    or float(np.clip((vix_val - 12) / 28, 0, 1)))
    vrp_v  = iv_metrics.get("vrp")
    vrp    = float(vrp_v) if vrp_v is not None else float(atm_iv - rv20)

    today   = pd.Timestamp.today()
    last_d  = calendar.monthrange(today.year, today.month)[1]
    days_me = (pd.Timestamp(today.year, today.month, last_d) - today).days

    return pd.DataFrame([{
        "ivr":               ivr,
        "iv_term_slope":     0.0,
        "put_call_skew":     1.0,
        "atm_iv":            atm_iv,
        "realized_vol_20d":  rv20,
        "vrp":               vrp,
        "atr_pct":           atr_pct,
        "ret_5d":            ret_5d,
        "ret_20d":           ret_20d,
        "dist_from_ma50":    dist_ma50,
        "vix_level":         vix_val,
        "vix_5d_change":     vix_5d_ch,
        "vix_ma_ratio":      vix_ma_r,
        "rate_10y":          0.0,
        "yield_curve_2y10y": 0.0,
        "days_to_month_end": float(days_me),
        "oi_put_call_proxy": 1.0,
    }])[_IC_AI_FEATURE_COLS]


def _score_vix_spike_fade(
    ticker: str,
    price_df: pd.DataFrame,
    vix_series: pd.Series,
    iv_metrics: dict,
) -> Optional[dict]:
    """Screen for VIX > 25 AND VIX > 1.3× 20d-avg, underlying above 200-MA."""
    if price_df.empty or len(price_df) < 20:
        return None
    try:
        close = price_df["close"].astype(float)
        high  = price_df.get("high",  close).astype(float)
        low   = price_df.get("low",   close).astype(float)

        latest_price = float(close.iloc[-1])
        latest_vix   = float(vix_series.iloc[-1]) if not vix_series.empty else 0.0
        vix_20d_avg  = _vix_20d_avg(vix_series)
        ma200_val    = _ma200(close)
        latest_atr   = _atr(high, low, close)
        atr_pct      = latest_atr / latest_price if latest_price > 0 else 0.0  # decimal (0.0176 = 1.76%)

        atm_iv    = iv_metrics.get("atm_iv")
        hv20      = iv_metrics.get("hv20")
        ivr       = iv_metrics.get("ivr")
        iv_source = iv_metrics.get("iv_source", "no_options_data")

        vix_spike_ok = latest_vix > 25 and latest_vix > (vix_20d_avg * 1.3)
        above_ma200  = (latest_price > ma200_val) if ma200_val is not None else False
        n_pass       = sum([vix_spike_ok, above_ma200])

        score = (
            (min(latest_vix, 60) / 60) * 50
            + (min(latest_vix / max(vix_20d_avg, 1), 2.0) / 2.0) * 30
            + (20 if above_ma200 else 0)
        )

        return {
            "Ticker":       ticker,
            "Price":        latest_price,
            "VIX":          latest_vix,
            "VIX 20d avg":  vix_20d_avg,
            "VIX / 20d":    latest_vix / max(vix_20d_avg, 0.01),
            "ATM IV":       atm_iv,
            "HV20":         hv20,
            "IVR":          ivr,
            "ATR%":         atr_pct,
            "MA200":        ma200_val,
            "above_ma200":  above_ma200,
            "vix_spike_ok": vix_spike_ok,
            "n_pass":       n_pass,
            "all_pass":     n_pass == 2,
            "score":        score,
            "IV source":    iv_source,
        }
    except Exception as e:
        logger.warning(f"VixSpikeFade score error for {ticker}: {e}")
        return None


def _score_ivr_credit_spread(
    ticker: str,
    price_df: pd.DataFrame,
    vix_series: pd.Series,
    iv_metrics: dict,
    params: dict,
) -> Optional[dict]:
    """Screen for IVR >= 0.40, determine bull-put or bear-call based on trend."""
    if price_df.empty or len(price_df) < 20:
        return None
    try:
        close = price_df["close"].astype(float)
        high  = price_df.get("high",  close).astype(float)
        low   = price_df.get("low",   close).astype(float)

        latest_price = float(close.iloc[-1])
        latest_vix   = float(vix_series.iloc[-1]) if not vix_series.empty else 0.0
        latest_adx   = _adx(high, low, close)
        latest_atr   = _atr(high, low, close)
        atr_pct      = latest_atr / latest_price if latest_price > 0 else 0.0  # decimal (0.0176 = 1.76%)

        atm_iv         = iv_metrics.get("atm_iv")
        ivr            = iv_metrics.get("ivr")
        ivr_confidence = iv_metrics.get("ivr_confidence", "none")
        vrp            = iv_metrics.get("vrp")
        hv20           = iv_metrics.get("hv20")
        iv_over_hv     = iv_metrics.get("iv_over_hv")
        iv_source      = iv_metrics.get("iv_source", "no_options_data")

        if ivr is None:
            ivr            = _vix_ivr(vix_series)
            ivr_confidence = "low (VIX fallback)"
        if atm_iv is None:
            atm_iv = latest_vix / 100.0

        ivr_min = params.get("ivr_min", 0.40)
        ivr_ok  = ivr >= ivr_min
        vix_ok  = latest_vix <= params.get("vix_max", 50)

        # Trend: use 20-period EMA direction for spread type selection
        ema20 = float(close.ewm(span=20, min_periods=10).mean().iloc[-1])
        bullish = latest_price > ema20
        spread_type = "Bull Put Spread" if bullish else "Bear Call Spread"

        n_pass = sum([ivr_ok, vix_ok])

        score = ivr * 50 + max(0, 1 - latest_adx / 50) * 30 + (20 if vix_ok else 0)

        return {
            "Ticker":       ticker,
            "Price":        latest_price,
            "ATM IV":       atm_iv,
            "IVR":          ivr,
            "IVR conf":     ivr_confidence,
            "VRP":          vrp,
            "HV20":         hv20,
            "IV/HV":        iv_over_hv,
            "VIX":          latest_vix,
            "ADX":          latest_adx,
            "ATR%":         atr_pct,
            "EMA20":        ema20,
            "Trend":        "Bullish" if bullish else "Bearish",
            "Spread Type":  spread_type,
            "IV source":    iv_source,
            "ivr_ok":       ivr_ok,
            "vix_ok":       vix_ok,
            "n_pass":       n_pass,
            "all_pass":     n_pass == 2,
            "score":        score,
        }
    except Exception as e:
        logger.warning(f"IVR credit spread score error for {ticker}: {e}")
        return None


def _score_broken_wing_butterfly(
    ticker: str,
    price_df: pd.DataFrame,
    vix_series: pd.Series,
    iv_metrics: dict,
    params: dict,
) -> Optional[dict]:
    """Screen for low-IV, range-bound setups for BWB net-credit entry."""
    if price_df.empty or len(price_df) < 20:
        return None
    try:
        close = price_df["close"].astype(float)
        high  = price_df.get("high", close).astype(float)
        low   = price_df.get("low",  close).astype(float)

        latest_price = float(close.iloc[-1])
        latest_vix   = float(vix_series.iloc[-1]) if not vix_series.empty else 0.0
        latest_adx   = _adx(high, low, close)
        atm_iv         = iv_metrics.get("atm_iv")
        ivr            = iv_metrics.get("ivr")
        iv_source      = iv_metrics.get("iv_source", "no_options_data")

        if ivr is None:
            ivr = _vix_ivr(vix_series)
        if atm_iv is None:
            atm_iv = latest_vix / 100.0

        ivr_ok = ivr  <= params["ivr_max"]
        adx_ok = latest_adx <= params["adx_max"]
        vix_ok = latest_vix <= params["vix_max"]
        n_pass = sum([ivr_ok, adx_ok, vix_ok])

        score = (
            (1.0 - ivr / max(params["ivr_max"], 0.01)) * 40
            + (1.0 - latest_adx / max(params["adx_max"], 1)) * 35
            + (25 if vix_ok else 0)
        )

        narrow_w = round(latest_price * 0.05, 0)
        wide_w   = narrow_w * 2.0

        return {
            "Ticker":       ticker,
            "Price":        latest_price,
            "ATM IV":       atm_iv,
            "IVR":          ivr,
            "VIX":          latest_vix,
            "ADX":          latest_adx,
            "Narrow Wing":  narrow_w,
            "Wide Wing":    wide_w,
            "IV source":    iv_source,
            "ivr_ok":       ivr_ok,
            "adx_ok":       adx_ok,
            "vix_ok":       vix_ok,
            "n_pass":       n_pass,
            "all_pass":     n_pass == 3,
            "score":        score,
        }
    except Exception as e:
        logger.warning(f"BWB score error for {ticker}: {e}")
        return None


def _score_calendar_spread(
    ticker: str,
    price_df: pd.DataFrame,
    vix_series: pd.Series,
    iv_metrics: dict,
    params: dict,
) -> Optional[dict]:
    """Screen for range-bound, stable-IV setups for calendar spread entry."""
    if price_df.empty or len(price_df) < 25:
        return None
    try:
        close = price_df["close"].astype(float)
        high  = price_df.get("high", close).astype(float)
        low   = price_df.get("low",  close).astype(float)

        latest_price = float(close.iloc[-1])
        latest_vix   = float(vix_series.iloc[-1]) if not vix_series.empty else 0.0
        latest_adx   = _adx(high, low, close)
        atm_iv       = iv_metrics.get("atm_iv")
        hv20         = iv_metrics.get("hv20")
        ivr          = iv_metrics.get("ivr")
        iv_source    = iv_metrics.get("iv_source", "no_options_data")

        if atm_iv is None:
            atm_iv = latest_vix / 100.0
        if hv20 is None:
            ret  = close.pct_change()
            hv20 = float(ret.rolling(20).std().iloc[-1]) * (252 ** 0.5)
        if ivr is None:
            ivr = _vix_ivr(vix_series)

        vrp_ok = (atm_iv - hv20) >= params["hv_iv_spread_min"] if atm_iv and hv20 else False
        adx_ok = latest_adx <= params["adx_max"]
        vix_ok = params["vix_min"] <= latest_vix <= params["vix_max"]
        n_pass = sum([vrp_ok, adx_ok, vix_ok])

        score = (
            (1.0 - latest_adx / max(params["adx_max"], 1)) * 40
            + min((atm_iv - hv20) / 0.05, 1.0) * 35 if atm_iv and hv20 else 0
            + (25 if vix_ok else 0)
        )

        return {
            "Ticker":    ticker,
            "Price":     latest_price,
            "ATM IV":    atm_iv,
            "HV20":      round(hv20, 4) if hv20 else None,
            "VRP":       round(atm_iv - hv20, 4) if atm_iv and hv20 else None,
            "IVR":       ivr,
            "VIX":       latest_vix,
            "ADX":       latest_adx,
            "IV source": iv_source,
            "vrp_ok":    vrp_ok,
            "adx_ok":    adx_ok,
            "vix_ok":    vix_ok,
            "n_pass":    n_pass,
            "all_pass":  n_pass == 3,
            "score":     score,
        }
    except Exception as e:
        logger.warning(f"CalendarSpread score error for {ticker}: {e}")
        return None


def _score_earnings_straddle(
    ticker: str,
    price_df: pd.DataFrame,
    vix_series: pd.Series,
    iv_metrics: dict,
    params: dict,
    days_to_earnings: Optional[int] = None,
) -> Optional[dict]:
    """Screen for pre-earnings IV crush candidates."""
    if price_df.empty or len(price_df) < 20:
        return None
    try:
        close = price_df["close"].astype(float)
        latest_price = float(close.iloc[-1])
        latest_vix   = float(vix_series.iloc[-1]) if not vix_series.empty else 0.0
        atm_iv       = iv_metrics.get("atm_iv")
        ivr          = iv_metrics.get("ivr")
        iv_source    = iv_metrics.get("iv_source", "no_options_data")

        if atm_iv is None:
            atm_iv = latest_vix / 100.0
        if ivr is None:
            ivr = _vix_ivr(vix_series)

        dte_ok  = (days_to_earnings is not None
                   and params["dte_to_earnings_min"] <= days_to_earnings <= params["dte_to_earnings_max"])
        ivr_ok  = ivr >= params["ivr_min"]
        iv_ok   = atm_iv >= params["atm_iv_min"]
        impl_move = atm_iv * (max(1, days_to_earnings or 7) / 252) ** 0.5 if atm_iv else 0
        move_ok = impl_move >= params["implied_move_min"]
        n_pass  = sum([dte_ok, ivr_ok, iv_ok, move_ok])

        score = (
            ivr * 40
            + min(atm_iv / 0.80, 1.0) * 35
            + (25 if dte_ok else 0)
        )

        return {
            "Ticker":           ticker,
            "Price":            latest_price,
            "ATM IV":           atm_iv,
            "IVR":              ivr,
            "Days to Earnings": days_to_earnings,
            "Impl. Move":       round(impl_move, 4),
            "Straddle Credit":  round(latest_price * impl_move, 2) if latest_price else None,
            "VIX":              latest_vix,
            "IV source":        iv_source,
            "dte_ok":           dte_ok,
            "ivr_ok":           ivr_ok,
            "iv_ok":            iv_ok,
            "move_ok":          move_ok,
            "n_pass":           n_pass,
            "all_pass":         n_pass == 4,
            "score":            score,
        }
    except Exception as e:
        logger.warning(f"EarningsStraddle score error for {ticker}: {e}")
        return None


def _score_wheel_strategy(
    ticker: str,
    price_df: pd.DataFrame,
    vix_series: pd.Series,
    iv_metrics: dict,
    params: dict,
) -> Optional[dict]:
    """Screen for Wheel strategy: IVR > 40, price above MA50, ADX 15–30."""
    if price_df.empty or len(price_df) < 55:
        return None
    try:
        close = price_df["close"].astype(float)
        high  = price_df.get("high", close).astype(float)
        low   = price_df.get("low",  close).astype(float)

        latest_price = float(close.iloc[-1])
        latest_vix   = float(vix_series.iloc[-1]) if not vix_series.empty else 0.0
        latest_adx   = _adx(high, low, close)
        ma50         = float(close.rolling(50, min_periods=20).mean().iloc[-1])
        atm_iv       = iv_metrics.get("atm_iv")
        ivr          = iv_metrics.get("ivr")
        iv_source    = iv_metrics.get("iv_source", "no_options_data")

        if ivr is None:
            ivr = _vix_ivr(vix_series)
        if atm_iv is None:
            atm_iv = latest_vix / 100.0

        ivr_ok   = ivr >= params["ivr_min"]
        adx_ok   = params["adx_min"] <= latest_adx <= params["adx_max"]
        vix_ok   = latest_vix <= params["vix_max"]
        trend_ok = latest_price > ma50

        n_pass = sum([ivr_ok, adx_ok, vix_ok, trend_ok])

        dte_frac   = 28 / 252
        put_delta  = 0.30
        put_strike = round(latest_price * (1.0 - put_delta * atm_iv * (dte_frac ** 0.5)), 0)
        premium    = latest_price * atm_iv * (dte_frac ** 0.5) * put_delta * 0.8

        score = (
            ivr * 40
            + (1.0 - latest_adx / max(params["adx_max"], 1)) * 30
            + (20 if trend_ok else 0)
            + (10 if vix_ok else 0)
        )

        return {
            "Ticker":       ticker,
            "Price":        latest_price,
            "MA50":         round(ma50, 2),
            "ATM IV":       atm_iv,
            "IVR":          ivr,
            "VIX":          latest_vix,
            "ADX":          latest_adx,
            "Put Strike":   put_strike,
            "~Premium":     round(premium, 2),
            "IV source":    iv_source,
            "ivr_ok":       ivr_ok,
            "adx_ok":       adx_ok,
            "vix_ok":       vix_ok,
            "trend_ok":     trend_ok,
            "n_pass":       n_pass,
            "all_pass":     n_pass == 4,
            "score":        score,
        }
    except Exception as e:
        logger.warning(f"Wheel score error for {ticker}: {e}")
        return None


def _score_bull_put_spread(
    ticker: str,
    price_df: pd.DataFrame,
    vix_series: pd.Series,
    iv_metrics: dict,
    params: dict,
) -> Optional[dict]:
    """Screen for bullish, high-IVR setups for bull put spread entry."""
    if price_df.empty or len(price_df) < 55:
        return None
    try:
        close = price_df["close"].astype(float)
        high  = price_df.get("high", close).astype(float)
        low   = price_df.get("low",  close).astype(float)

        latest_price = float(close.iloc[-1])
        latest_vix   = float(vix_series.iloc[-1]) if not vix_series.empty else 0.0
        latest_adx   = _adx(high, low, close)
        ma50         = float(close.rolling(50, min_periods=20).mean().iloc[-1])
        atm_iv       = iv_metrics.get("atm_iv")
        ivr          = iv_metrics.get("ivr")
        iv_source    = iv_metrics.get("iv_source", "no_options_data")

        if ivr is None:
            ivr = _vix_ivr(vix_series)
        if atm_iv is None:
            atm_iv = latest_vix / 100.0

        ivr_ok   = ivr >= params["ivr_min"]
        adx_ok   = latest_adx <= params["adx_max"]
        vix_ok   = latest_vix <= params["vix_max"]
        trend_ok = latest_price > ma50

        n_pass = sum([ivr_ok, adx_ok, vix_ok, trend_ok])

        dte_frac     = 30 / 252
        short_delta  = 0.30
        long_delta   = 0.15
        width        = round(latest_price * 0.05, 0)
        short_k      = round(latest_price * (1.0 - short_delta * atm_iv * (dte_frac ** 0.5)), 0)
        long_k       = short_k - width
        credit       = latest_price * atm_iv * (dte_frac ** 0.5) * (short_delta - long_delta) * 0.85
        credit_ratio = credit / width if width > 0 else 0

        score = (
            ivr * 45
            + (1.0 - latest_adx / max(params["adx_max"], 1)) * 30
            + (15 if trend_ok else 0)
            + (10 if vix_ok else 0)
        )

        return {
            "Ticker":        ticker,
            "Price":         latest_price,
            "MA50":          round(ma50, 2),
            "ATM IV":        atm_iv,
            "IVR":           ivr,
            "VIX":           latest_vix,
            "ADX":           latest_adx,
            "Short Strike":  short_k,
            "Long Strike":   long_k,
            "Width":         width,
            "~Credit":       round(credit, 2),
            "Credit/Width":  round(credit_ratio, 3),
            "IV source":     iv_source,
            "ivr_ok":        ivr_ok,
            "adx_ok":        adx_ok,
            "vix_ok":        vix_ok,
            "trend_ok":      trend_ok,
            "n_pass":        n_pass,
            "all_pass":      n_pass == 4,
            "score":         score,
        }
    except Exception as e:
        logger.warning(f"BullPutSpread score error for {ticker}: {e}")
        return None


def _score_vol_arbitrage(
    ticker: str,
    price_df: pd.DataFrame,
    vix_series: pd.Series,
    iv_metrics: dict,
) -> Optional[dict]:
    """Screen for VRP > 0 (IV > HV) and available options data."""
    if price_df.empty or len(price_df) < 20:
        return None
    try:
        close = price_df["close"].astype(float)
        high  = price_df.get("high",  close).astype(float)
        low   = price_df.get("low",   close).astype(float)

        latest_price = float(close.iloc[-1])
        latest_vix   = float(vix_series.iloc[-1]) if not vix_series.empty else 0.0
        latest_atr   = _atr(high, low, close)
        atr_pct      = latest_atr / latest_price if latest_price > 0 else 0.0  # decimal (0.0176 = 1.76%)

        atm_iv    = iv_metrics.get("atm_iv")
        ivr       = iv_metrics.get("ivr")
        vrp       = iv_metrics.get("vrp")
        hv20      = iv_metrics.get("hv20")
        iv_over_hv = iv_metrics.get("iv_over_hv")
        iv_source = iv_metrics.get("iv_source", "no_options_data")

        if atm_iv is None or hv20 is None:
            return None  # Vol arb requires real options data

        vrp_ok     = vrp is not None and vrp > 0
        iv_hv_ok   = iv_over_hv is not None and iv_over_hv > 1.1
        n_pass     = sum([vrp_ok, iv_hv_ok])

        # VRP term: only positive VRP scores; cap at 0.50 (50 vol pts) → max 50 pts
        # IV/HV term: only when IV > HV (ratio > 1); cap at 2× → max 50 pts
        # Total range: 0–100
        score = min(100, max(0, (
            min(max(0, vrp or 0), 0.50) * 100
            + max(0, min(iv_over_hv or 1.0, 2.0) - 1.0) * 50
        )))

        return {
            "Ticker":    ticker,
            "Price":     latest_price,
            "ATM IV":    atm_iv,
            "HV20":      hv20,
            "IV/HV":     iv_over_hv,
            "VRP":       vrp,
            "IVR":       ivr,
            "VIX":       latest_vix,
            "ATR%":      atr_pct,
            "IV source": iv_source,
            "vrp_ok":    vrp_ok,
            "iv_hv_ok":  iv_hv_ok,
            "n_pass":    n_pass,
            "all_pass":  n_pass == 2,
            "score":     score,
        }
    except Exception as e:
        logger.warning(f"VolArb score error for {ticker}: {e}")
        return None


def _score_generic(
    ticker: str,
    price_df: pd.DataFrame,
    vix_series: pd.Series,
    iv_metrics: dict,
) -> Optional[dict]:
    """Generic signal row: just collect all available metrics."""
    if price_df.empty or len(price_df) < 10:
        return None
    try:
        close = price_df["close"].astype(float)
        high  = price_df.get("high",  close).astype(float)
        low   = price_df.get("low",   close).astype(float)

        latest_price = float(close.iloc[-1])
        latest_vix   = float(vix_series.iloc[-1]) if not vix_series.empty else 0.0
        latest_adx   = _adx(high, low, close)
        latest_atr   = _atr(high, low, close)
        atr_pct      = latest_atr / latest_price if latest_price > 0 else 0.0  # decimal (0.0176 = 1.76%)

        return {
            "Ticker":  ticker,
            "Price":   latest_price,
            "ATM IV":  iv_metrics.get("atm_iv"),
            "IVR":     iv_metrics.get("ivr"),
            "VRP":     iv_metrics.get("vrp"),
            "HV20":    iv_metrics.get("hv20"),
            "IV/HV":   iv_metrics.get("iv_over_hv"),
            "VIX":     latest_vix,
            "ADX":     latest_adx,
            "ATR%":    atr_pct,
            "IV src":  iv_metrics.get("iv_source", "—"),
        }
    except Exception as e:
        logger.warning(f"Generic score error for {ticker}: {e}")
        return None


# ── Polygon helpers ────────────────────────────────────────────────────────────

def _fetch_ohlcv(ticker: str, api_key: str, bars: int = 60) -> pd.DataFrame:
    """Daily OHLCV bars for a stock/ETF via yfinance (free, no per-minute cap).

    Per the data architecture, ALL stock data comes from yfinance — the Polygon
    stock endpoint is rate-limited to 5/min and silently starves larger universe
    scans. Returns a DataFrame indexed by date with open/high/low/close/volume/
    vwap columns (matching the prior Polygon shape). `api_key` is kept for
    signature compatibility and is unused.
    """
    try:
        from data.stock_data import yf_daily_bars
        df = yf_daily_bars(ticker, n_days=bars)
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.copy()
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        keep = [c for c in ("open", "high", "low", "close", "volume", "vwap") if c in df.columns]
        return df[keep].tail(bars)
    except Exception as e:
        logger.warning(f"yfinance OHLCV failed for {ticker}: {e}")
        return pd.DataFrame()


# ── Options chain helpers ──────────────────────────────────────────────────────

def _get_options_chain(ticker: str, api_key: str, spot: float,
                       dte_target: int = 45, dte_lo: int = 30, dte_hi: int = 60,
                       strike_lo_pct: float = 0.85, strike_hi_pct: float = 1.15):
    """Fetch options chain from Polygon. Returns (chain_df, best_exp, dte_used) or None.

    The strike window defaults to spot×[0.85, 1.15]. The previous ±30% band
    pulled ~900 contracts/expiry for index ETFs — so many that the paginated
    snapshot fetch could exhaust before reaching the near-the-money strikes a
    credit spread needs, leaving the chain truncated just above the money (e.g.
    SPY capping at ~+1.6%). Credit-spread short strikes sit ~5-6% OTM with wings
    ~10-11% out, so ±15% covers every leg with margin and far fewer contracts.
    """
    from data.polygon_client import PolygonClient
    today  = date.today()
    exp_lo = (today + timedelta(days=dte_lo)).isoformat()
    exp_hi = (today + timedelta(days=dte_hi)).isoformat()

    try:
        client = PolygonClient(api_key=api_key)
        chain  = client.get_options_chain(
            underlying=ticker,
            expiration_date_gte=exp_lo,
            expiration_date_lte=exp_hi,
            strike_price_gte=spot * strike_lo_pct,
            strike_price_lte=spot * strike_hi_pct,
        )
    except Exception as e:
        return None, None, None, str(e)

    if chain is None or chain.empty:
        return None, None, None, "No options data returned from Polygon"

    chain = chain.dropna(subset=["strike", "dte"]).copy()
    chain["dte"] = pd.to_numeric(chain["dte"], errors="coerce")

    # Pick the best expiry, then RE-FETCH just that one expiration for a complete
    # strike ladder. Two subtleties drive the selection:
    #   1. Nearest-to-DTE-target alone is wrong — a far-dated WEEKLY (e.g. 43 DTE)
    #      often lists only a thin ±2% band of strikes, far too narrow for a
    #      ~16-delta condor with wings ~10% OTM. The standard MONTHLY (3rd Friday)
    #      a bit further out carries the deep ladder. So prefer expiries whose
    #      ladder already spans at least spot±10%, then pick nearest the target.
    #   2. The single-expiration refetch guarantees full coverage even if the
    #      ranged, paginated snapshot truncated a later-sorted expiry.
    try:
        _bid = pd.to_numeric(chain["bid"], errors="coerce")
        _ask = pd.to_numeric(chain["ask"], errors="coerce")
        chain["_quoted"] = (_bid > 0) & (_ask > 0)
        g = chain.groupby("expiration")
        exp_stats = pd.DataFrame({
            "dte":  g["dte"].first(),
            "kmin": g["strike"].min(),
            "kmax": g["strike"].max(),
            "nq":   g["_quoted"].sum(),   # # of legs with a real two-sided quote
        })
        # Prefer expiries that (a) span ≥ spot±10% (deep ladder, not a thin weekly)
        # and (b) actually have two-sided quotes (liquidity), then nearest the DTE
        # target. Falls back gracefully so a selection is always made.
        wide = exp_stats[(exp_stats["kmin"] <= spot * 0.90) &
                         (exp_stats["kmax"] >= spot * 1.10)]
        pool = wide if not wide.empty else exp_stats
        liquid = pool[pool["nq"] >= 4]
        pool = liquid if not liquid.empty else pool
        best_exp = (pool["dte"] - dte_target).abs().idxmin()
        single = client.get_options_chain(
            underlying=ticker,
            expiration_date=best_exp,
            strike_price_gte=spot * strike_lo_pct,
            strike_price_lte=spot * strike_hi_pct,
        )
        if single is not None and not single.empty:
            chain = single.dropna(subset=["strike", "dte"]).copy()
    except Exception:
        pass  # fall back to the ranged chain already fetched

    for col in ["strike", "dte", "iv", "bid", "ask", "delta"]:
        if col in chain.columns:
            chain[col] = pd.to_numeric(chain[col], errors="coerce")
    # Mid from the quoted market ONLY when there is a genuine two-sided market
    # (bid>0 AND ask>0 AND ask>=bid). Illiquid far-OTM wings frequently quote
    # bid=0 / one-sided, so a naive (bid+ask)/2 yields a nonsense price — e.g. a
    # further-OTM wing pricing ABOVE a nearer short strike, turning an iron
    # condor's credit negative. Everything without a real two-sided market falls
    # back to a Black-Scholes theoretical price, which is monotonic in strike and
    # therefore keeps wings cheaper than the shorts they protect.
    bid = chain["bid"]
    ask = chain["ask"]
    two_sided = (bid > 0) & (ask > 0) & (ask >= bid)
    chain["mid"] = np.where(two_sided, (bid + ask) / 2.0, np.nan)

    need_bs = chain["mid"].isna()
    if need_bs.any():
        r = 0.045
        iv_med = pd.to_numeric(chain["iv"], errors="coerce").replace(0, np.nan).median()
        iv_fallback = float(iv_med) if np.isfinite(iv_med) and iv_med > 0 else 0.25
        for idx in chain[need_bs].index:
            row   = chain.loc[idx]
            T     = float(row["dte"]) / 365.0
            iv_r  = row["iv"]
            iv    = float(iv_r) if pd.notna(iv_r) and float(iv_r) > 0 else iv_fallback
            K     = float(row["strike"])
            otype = str(row.get("type", "call")).lower()
            if T > 0 and K > 0:
                chain.at[idx, "mid"] = max(_bs_price(spot, K, T, iv, r, otype), 0.0)

    exps     = chain.groupby("expiration")["dte"].first()
    best_exp = exps.sub(dte_target).abs().idxmin()
    dte_used = int(exps[best_exp])
    exp_chain = chain[chain["expiration"] == best_exp].copy()

    return exp_chain, best_exp, dte_used, None


def _find_strike(df: pd.DataFrame, opt_type: str, spot: float, target_delta: float):
    """Find strike closest to target delta. Falls back to moneyness proxy."""
    if df.empty:
        return None, None
    df = df.copy()
    if "delta" in df.columns:
        df["delta_num"] = pd.to_numeric(df["delta"], errors="coerce")
    else:
        df["delta_num"] = np.nan

    if df["delta_num"].notna().sum() >= 2:
        df["delta_diff"] = (df["delta_num"].abs() - target_delta).abs()
    else:
        if opt_type == "call":
            df["delta_diff"] = (df["strike"] - spot * (1 + target_delta)).abs()
        else:
            df["delta_diff"] = (df["strike"] - spot * (1 - target_delta)).abs()

    best = df.loc[df["delta_diff"].idxmin()]
    mid  = best["mid"] if not pd.isna(best.get("mid", np.nan)) else None
    return float(best["strike"]), mid


def _get_chain_mid(df: pd.DataFrame, strike: float, exclude_strike: float | None = None):
    """Look up mid price for a specific strike, or nearest.
    exclude_strike: if set, skip any row whose strike equals this value (prevents
    wing collapsing onto the short strike when no further OTM strike exists).
    """
    if df.empty:
        return None, strike
    candidates = df[df["strike"] != exclude_strike] if exclude_strike is not None else df
    if candidates.empty:
        return None, strike
    row = candidates[candidates["strike"] == strike]
    if row.empty:
        row = candidates.iloc[(candidates["strike"] - strike).abs().argsort()[:1]]
    if row.empty:
        return None, strike
    m = float(row["mid"].iloc[0]) if not pd.isna(row["mid"].iloc[0]) else None
    k = float(row["strike"].iloc[0])
    return m, k


# ── BS helpers ─────────────────────────────────────────────────────────────────

def _bs_price(S: float, K: float, T: float, sigma: float, r: float, opt_type: str) -> float:
    from scipy.stats import norm as _norm
    if T <= 0 or sigma <= 0:
        return max(0.0, (S - K) if opt_type == "call" else (K - S))
    d1 = (_math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * _math.sqrt(T))
    d2 = d1 - sigma * _math.sqrt(T)
    if opt_type == "call":
        return S * _norm.cdf(d1) - K * _math.exp(-r * T) * _norm.cdf(d2)
    return K * _math.exp(-r * T) * _norm.cdf(-d2) - S * _norm.cdf(-d1)


# ── GEX Positioning screener helpers ───────────────────────────────────────────

# Regime thresholds (match gex_positioning.py defaults)
_GEX_VIX_BANDS = [
    # (regime_key, vix_lo, vix_hi, spy_weight, color)
    ("HighPositive", 0.0,  15.0, 0.90, "#10b981"),
    ("MildPositive", 15.0, 18.0, 0.80, "#34d399"),
    ("Neutral",      18.0, 22.0, 0.60, "#f59e0b"),
    ("Negative",     22.0, 30.0, 0.35, "#f97316"),
    ("DeepNegative", 30.0, 999., 0.15, "#ef4444"),
]

_GEX_REGIME_LABELS = {
    "HighPositive": "High Positive GEX — vol-suppressed",
    "MildPositive": "Mild Positive GEX — calm",
    "Neutral":      "Neutral / Gamma Flip Zone",
    "Negative":     "Negative GEX — volatile",
    "DeepNegative": "Deep Negative GEX — crash dynamics",
}

_GEX_REGIME_COLORS = {
    "HighPositive": "#10b981",
    "MildPositive": "#34d399",
    "Neutral":      "#f59e0b",
    "Negative":     "#f97316",
    "DeepNegative": "#ef4444",
}


def _classify_vix_regime(vix_val: float) -> str:
    for regime, lo, hi, _, _ in _GEX_VIX_BANDS:
        if lo <= vix_val < hi:
            return regime
    return "DeepNegative"


def _score_gex_positioning(
    tickers: list[str],
    api_key: str,
    vix_series: pd.Series,
    price_dfs: dict[str, pd.DataFrame],
    params: dict,
) -> list[dict]:
    """
    Score each ticker for GEX Positioning strategy.

    NOTE: Live per-ticker GEX requires options OI data which is not universally
    available.  This function uses VIX as a GEX proxy (clearly labelled).
    VIX is shared across all tickers; individual ticker price data provides
    ATR and momentum context.
    """
    current_vix = float(vix_series.iloc[-1]) if not vix_series.empty else 20.0
    regime      = _classify_vix_regime(current_vix)
    spy_weight  = dict(zip(
        [b[0] for b in _GEX_VIX_BANDS],
        [b[3] for b in _GEX_VIX_BANDS],
    ))[regime]
    signal = "BUY" if spy_weight >= 0.75 else ("SELL" if spy_weight <= 0.35 else "HOLD")

    results = []
    for ticker in tickers:
        price_df = price_dfs.get(ticker)
        if price_df is None or price_df.empty or len(price_df) < 10:
            continue
        try:
            close        = price_df["close"].astype(float)
            high         = price_df.get("high",  close).astype(float)
            low          = price_df.get("low",   close).astype(float)
            latest_price = float(close.iloc[-1])
            latest_atr   = _atr(high, low, close)
            atr_pct      = latest_atr / latest_price if latest_price > 0 else 0.0  # decimal (0.0176 = 1.76%)
            ret_5d       = float(close.pct_change(5).iloc[-1]) if len(close) >= 6 else 0.0

            results.append({
                "Ticker":        ticker,
                "Price":         latest_price,
                "VIX":           current_vix,
                "Regime":        regime,
                "Regime Label":  _GEX_REGIME_LABELS[regime],
                "SPY Weight":    spy_weight,
                "Signal":        signal,
                "ATR%":          atr_pct,
                "5d Return":     ret_5d,
                "GEX Source":    "VIX proxy (live GEX requires options OI)",
            })
        except Exception as e:
            logger.warning(f"GEX score error for {ticker}: {e}")

    return results


# ── TLT/SPY Rotation screener ─────────────────────────────────────────────────

_ROTATION_REGIMES = {
    "Growth":     {"color": "#22c55e", "emoji": "📈", "spy": 0.80, "tlt": 0.10, "cash": 0.10,
                   "label": "Growth — Rates Rising + Stocks Rising",
                   "why": "Economy expanding, Fed hiking slowly. Overweight equities; underweight bonds (rising rates hurt TLT).",
                   "play": "BUY SPY, minimal TLT, hold small cash buffer."},
    "Inflation":  {"color": "#ef4444", "emoji": "🔥", "spy": 0.40, "tlt": 0.05, "cash": 0.55,
                   "label": "Inflation — Rates Rising + Stocks Falling",
                   "why": "Fed hiking aggressively. BOTH equities and bonds fall — 2022 scenario. Shift to cash/commodities.",
                   "play": "Reduce SPY, exit TLT, move to cash (or XLE/TIP/GLD if available)."},
    "Fear":       {"color": "#a855f7", "emoji": "😨", "spy": 0.20, "tlt": 0.70, "cash": 0.10,
                   "label": "Fear — Rates Falling + Stocks Falling",
                   "why": "Recession/panic. Flight to safety. TLT is the hedge — this is the only regime where bonds protect equities.",
                   "play": "Maximum TLT; minimal SPY; hold GLD as secondary hedge."},
    "Risk-On":    {"color": "#3b82f6", "emoji": "🚀", "spy": 0.70, "tlt": 0.20, "cash": 0.10,
                   "label": "Risk-On — Rates Falling + Stocks Rising",
                   "why": "Goldilocks: Fed cutting, earnings growing. Both SPY and TLT rise simultaneously.",
                   "play": "Maximum SPY weight; also long TLT (both rise). Best regime for the strategy."},
    "Transition": {"color": "#f59e0b", "emoji": "⏳", "spy": 0.60, "tlt": 0.30, "cash": 0.10,
                   "label": "Transition — Ambiguous Signal",
                   "why": "Rate and equity directions don't clearly align. Regime shift may be imminent.",
                   "play": "Hold current allocation. Wait for 3+ consecutive days of the same regime before rebalancing."},
}


def _classify_rotation_regime(
    spy_ret_20d: float,
    tlt_ret_20d: float,
    yield_threshold: float = 0.03,
    return_threshold: float = 0.03,
) -> str:
    """
    TLT 20-day return as a yield proxy:
      TLT rising  → rates falling (bond prices up = yields down)
      TLT falling → rates rising  (bond prices down = yields up)
    """
    rates_rising  = tlt_ret_20d < -yield_threshold   # TLT falling = rates rising
    rates_falling = tlt_ret_20d >  yield_threshold   # TLT rising  = rates falling
    stocks_up     = spy_ret_20d >  return_threshold
    stocks_down   = spy_ret_20d < -return_threshold

    if   rates_rising  and stocks_up:   return "Growth"
    elif rates_rising  and stocks_down: return "Inflation"
    elif rates_falling and stocks_down: return "Fear"
    elif rates_falling and stocks_up:   return "Risk-On"
    else:                               return "Transition"


# ── New AI strategy screener functions (2026-04-06) ─────────────────────────

def _score_vix_term_structure(
    ticker: str,
    price_df: pd.DataFrame,
    vix_series: pd.Series,
    params: Optional[dict] = None,
) -> dict:
    """Score a ticker for VIX Term Structure AI strategy."""
    p = {**_DEFAULT_PARAMS.get("vix_term_structure", {}), **(params or {})}
    if price_df.empty or len(vix_series) < 30:
        return {"Score": 0, "Status": "No data", "Regime": "—", "VRP": "—", "RV20": "—"}

    close   = price_df["close"]
    vix_now = float(vix_series.iloc[-1])
    rv20    = float(close.pct_change().rolling(20, min_periods=10).std().iloc[-1] * (252 ** 0.5))
    vrp     = vix_now / 100.0 - rv20
    vix_5d  = float(vix_series.pct_change(5).iloc[-1]) if len(vix_series) >= 5 else 0.0

    # Vol-of-vol: std of VIX daily changes over 10d
    vix_vov = float(vix_series.diff().rolling(10, min_periods=5).std().iloc[-1]) if len(vix_series) >= 10 else 0.5

    if vix_now > p.get("vix_max", 45.0):
        return {"Score": 0, "Status": "VIX too high", "Regime": "—", "VRP": f"{vrp:.3f}", "RV20": f"{rv20:.1%}"}

    # Heuristic regime score (before ML model is trained)
    if vrp < -0.03:
        regime = "Backwardation"
        score  = min(100, int(50 + abs(vrp) * 400))
    elif vrp > 0.03:
        regime = "Contango"
        score  = min(100, int(50 + vrp * 400))
    else:
        regime = "Neutral"
        score  = 30

    # Penalise if VIX spiking fast (regime shift risk)
    if vix_5d > 0.30:
        score = max(0, score - 20)

    status = "BUY" if regime == "Contango" and score >= 50 else \
             "SELL" if regime == "Backwardation" and score >= 50 else "FLAT"

    return {
        "Score":   score,
        "Status":  status,
        "Regime":  regime,
        "VIX":     f"{vix_now:.1f}",
        "VRP":     f"{vrp:+.3f}",
        "RV20":    f"{rv20:.1%}",
        "VoV":     f"{vix_vov:.2f}",
        "5d Chg":  f"{vix_5d:+.1%}",
    }


def _score_earnings_vol_crush(
    ticker: str,
    price_df: pd.DataFrame,
    vix_series: pd.Series,
    params: Optional[dict] = None,
) -> dict:
    """Score a ticker for Earnings Vol Crush AI strategy."""
    if price_df.empty or len(price_df) < 5:
        return {"Score": 0, "Status": "No data", "Gap%": "—", "IVR": "—"}

    close    = price_df["close"]
    gap_pct  = float(close.pct_change().iloc[-1]) if len(close) >= 2 else 0.0
    abs_gap  = abs(gap_pct)
    vix_now  = float(vix_series.iloc[-1]) if not vix_series.empty else 20.0
    rv20     = float(close.pct_change().rolling(20, min_periods=10).std().iloc[-1] * (252 ** 0.5))
    ivr_raw  = _vix_ivr(vix_series)

    min_gap  = (params or {}).get("min_gap_pct", 0.03)

    if abs_gap < min_gap:
        return {"Score": 0, "Status": "No earnings gap", "Gap%": f"{gap_pct:.1%}", "IVR": f"{ivr_raw:.2f}"}

    # Score based on gap size and IVR (more premium = higher score)
    gap_score = min(50, int(abs_gap * 800))
    ivr_score = min(50, int(ivr_raw * 60))
    score     = gap_score + ivr_score

    direction = "Gap Up → Bear Call" if gap_pct > 0 else "Gap Down → Bull Put"
    status    = "ENTER" if score >= 60 else "WEAK"

    return {
        "Score":     score,
        "Status":    status,
        "Gap%":      f"{gap_pct:+.1%}",
        "Gap Type":  direction,
        "IVR":       f"{ivr_raw:.2f}",
        "VIX":       f"{vix_now:.1f}",
        "RV20":      f"{rv20:.1%}",
    }


def _score_momentum_regime_spread(
    ticker: str,
    price_df: pd.DataFrame,
    vix_series: pd.Series,
    params: Optional[dict] = None,
) -> dict:
    """Score a ticker for Momentum Regime Debit Spread AI strategy."""
    if price_df.empty or len(price_df) < 25:
        return {"Score": 0, "Status": "No data", "Regime": "—", "5d Ret": "—", "20d Ret": "—"}

    close   = price_df["close"]
    ret_5d  = float(close.pct_change(5).iloc[-1])  if len(close) >= 5  else 0.0
    ret_20d = float(close.pct_change(20).iloc[-1]) if len(close) >= 20 else 0.0
    vix_now = float(vix_series.iloc[-1]) if not vix_series.empty else 20.0
    vix_ma  = float(vix_series.rolling(20, min_periods=5).mean().iloc[-1]) if len(vix_series) >= 5 else vix_now
    vix_rat = vix_now / max(vix_ma, 0.01)
    accel   = ret_5d - ret_20d / 4.0

    vix_max = (params or {}).get("vix_max", 40.0)
    if vix_now > vix_max:
        return {"Score": 0, "Status": "VIX too high", "Regime": "—",
                "5d Ret": f"{ret_5d:.1%}", "20d Ret": f"{ret_20d:.1%}"}

    if ret_5d > 0.025 and ret_20d > 0.005 and vix_rat < 1.15:
        regime = "Bull"
        score  = min(100, int(50 + abs(ret_5d) * 1000 + accel * 500))
        status = "BUY (Bull Call)"
    elif ret_5d < -0.025 and ret_20d < -0.005 and vix_rat > 0.90:
        regime = "Bear"
        score  = min(100, int(50 + abs(ret_5d) * 1000 + abs(accel) * 500))
        status = "BUY (Bear Put)"
    else:
        regime = "Chop"
        score  = 20
        status = "FLAT"

    return {
        "Score":    score,
        "Status":   status,
        "Regime":   regime,
        "5d Ret":   f"{ret_5d:+.1%}",
        "20d Ret":  f"{ret_20d:+.1%}",
        "Accel":    f"{accel:+.3f}",
        "VIX":      f"{vix_now:.1f}",
        "VIX/MA":   f"{vix_rat:.2f}",
    }


def _score_covered_call_ai(
    ticker: str,
    price_df: pd.DataFrame,
    vix_series: pd.Series,
    params: Optional[dict] = None,
) -> dict:
    """Score a ticker for Covered Call Optimizer AI strategy."""
    if price_df.empty or len(price_df) < 25:
        return {"Score": 0, "Status": "No data", "IVR": "—", "Delta Mode": "—"}

    close   = price_df["close"]
    spot    = float(close.iloc[-1])
    ivr_now = _vix_ivr(vix_series)
    vix_now = float(vix_series.iloc[-1]) if not vix_series.empty else 20.0
    ret_20d = float(close.pct_change(20).iloc[-1]) if len(close) >= 20 else 0.0
    rv20    = float(close.pct_change().rolling(20, min_periods=10).std().iloc[-1] * (252 ** 0.5))
    vrp     = vix_now / 100.0 - rv20

    min_ivr = (params or {}).get("min_ivr", 0.30)

    if ivr_now < min_ivr:
        return {"Score": 0, "Status": "IVR too low (skip)", "IVR": f"{ivr_now:.2f}",
                "Delta Mode": "—", "VRP": f"{vrp:+.3f}"}

    # Delta mode selection
    if ret_20d > 0.08:
        delta_mode = "Conservative (0.15δ)"
        mode_score = 50
    else:
        delta_mode = "Aggressive (0.30δ)"
        mode_score = 70

    ivr_score = min(30, int(ivr_now * 50))
    score     = mode_score + ivr_score
    status    = "WRITE CC" if score >= 70 else "MARGINAL"

    return {
        "Score":      score,
        "Status":     status,
        "IVR":        f"{ivr_now:.2f}",
        "Delta Mode": delta_mode,
        "VRP":        f"{vrp:+.3f}",
        "20d Ret":    f"{ret_20d:+.1%}",
        "VIX":        f"{vix_now:.1f}",
    }


def _score_rs_credit_spread(
    ticker: str,
    price_df: pd.DataFrame,
    vix_series: pd.Series,
    params: Optional[dict] = None,
) -> dict:
    """Score a ticker for RS Credit Spread AI strategy.
    Ticker here represents a sector ETF; score based on its RS rank."""
    if price_df.empty or len(price_df) < 12:
        return {"Score": 0, "Status": "No data", "RS Rank": "—", "10d Ret": "—"}

    close    = price_df["close"]
    ret_10d  = float(close.pct_change(10).iloc[-1]) if len(close) >= 10 else 0.0
    vix_now  = float(vix_series.iloc[-1]) if not vix_series.empty else 20.0
    ivr_now  = _vix_ivr(vix_series)

    adx_max = (params or {}).get("adx_max", 30.0)
    high = price_df.get("high",  close)
    low  = price_df.get("low",   close)
    adx_now = _adx(high, low, close) if len(close) >= 20 else 20.0

    if adx_now > adx_max:
        return {"Score": 0, "Status": "SPY trending (skip)", "RS Rank": "—",
                "10d Ret": f"{ret_10d:+.1%}", "ADX": f"{adx_now:.1f}"}

    # Score based on extreme RS position
    abs_ret = abs(ret_10d)
    score = min(100, int(abs_ret * 1000))

    if ret_10d <= -0.04:
        role   = "Laggard (Bear Call)"
        status = "SHORT PREMIUM"
    elif ret_10d >= 0.04:
        role   = "Leader (Bull Put)"
        status = "SHORT PREMIUM"
    else:
        role   = "Middle — skip"
        status = "FLAT"
        score  = max(0, score - 20)

    return {
        "Score":   score,
        "Status":  status,
        "Role":    role,
        "10d Ret": f"{ret_10d:+.1%}",
        "IVR":     f"{ivr_now:.2f}",
        "VIX":     f"{vix_now:.1f}",
        "ADX":     f"{adx_now:.1f}",
    }


def _score_put_steal(
    ticker: str,
    price_df: pd.DataFrame,
    vix_series: pd.Series,
    iv_metrics: dict,
    params: dict,
) -> Optional[dict]:
    """
    Screen for Put Steal (Short Stock Interest Arbitrage) candidates.

    Conditions for a positive NII signal:
      1. NII = X(1-e^{-rT}) - call(S,X,T) > nii_threshold  [early exercise edge]
      2. Stock is not in panic vol (IV < iv_max, VIX < vix_max)
      3. Not already in a strong downtrend (ADX gives context)

    Note: NII is only meaningfully positive when puts are deep ITM.
    itm_pct=0.10 means we price a strike 10% above current spot (put is 10% ITM).
    """
    if price_df.empty or len(price_df) < 30:
        return None
    try:
        from scipy.stats import norm as _norm

        close = price_df["close"].astype(float)
        high  = price_df.get("high", close).astype(float)
        low   = price_df.get("low",  close).astype(float)

        spot    = float(close.iloc[-1])
        vix_now = float(vix_series.iloc[-1]) if not vix_series.empty else 18.0
        adx_now = _adx(high, low, close)

        atm_iv = iv_metrics.get("atm_iv")
        ivr    = iv_metrics.get("ivr")
        iv_src = iv_metrics.get("iv_source", "no_options_data")

        if atm_iv is None:
            atm_iv = vix_now / 100.0
        if ivr is None:
            ivr = _vix_ivr(vix_series)

        # Risk-free rate proxy: current VIX/100 * 0.5 as crude rate; use 4.3% default
        r   = 0.043
        itm = params.get("itm_pct", 0.10)
        nii_thr = params.get("nii_threshold", 0.01)
        vix_mx  = params.get("vix_max", 40.0)
        iv_mx   = params.get("iv_max", 0.60)
        dte     = 21
        T       = dte / 365.0

        # Strike X = spot × (1 + itm): a put at X is itm% in-the-money
        X = spot * (1.0 + itm)

        def _bs_call(S, K, Tt, rr, sig):
            if Tt <= 0 or sig <= 0 or S <= 0 or K <= 0:
                return max(0.0, S - K)
            d1 = (np.log(S / K) + (rr + 0.5 * sig ** 2) * Tt) / (sig * np.sqrt(Tt))
            d2 = d1 - sig * np.sqrt(Tt)
            return float(S * _norm.cdf(d1) - K * np.exp(-rr * Tt) * _norm.cdf(d2))

        interest_income = X * (1.0 - np.exp(-r * T))
        call_val        = _bs_call(spot, X, T, r, max(atm_iv, 0.01))
        nii             = interest_income - call_val

        vix_ok = vix_now <= vix_mx
        iv_ok  = atm_iv <= iv_mx
        nii_ok = nii >= nii_thr

        n_pass = sum([vix_ok, iv_ok, nii_ok])

        # Strikes for the bull put spread
        short_k = round(spot * (1.0 - itm * 0.5), 2)   # slightly ITM short put
        long_k  = round(short_k * 0.96, 2)              # 4% wing below short

        short_p = max(0.0, _bs_call(spot, short_k, T, r, atm_iv) -
                     spot + short_k * np.exp(-r * T))   # approximate put via parity
        long_p  = max(0.0, _bs_call(spot, long_k,  T, r, atm_iv) -
                     spot + long_k  * np.exp(-r * T))
        credit  = max(0.0, short_p - long_p)

        # Score: weighted NII signal + low-vol bonus (max = 8+30+15+15 = 68... scale to 100)
        nii_strength = min(nii / max(nii_thr, 0.001), 5.0) * 8   # 0-40 (5 × 8 = 40 max)
        score = min(100, round(
            nii_strength
            + (40 if nii_ok else 0)
            + (30 if vix_ok else 0)
            + (30 if iv_ok  else 0)
        ))

        return {
            "Ticker":       ticker,
            "Price":        spot,
            "NII":          round(nii, 3),
            "Strike X":     round(X, 2),
            "Short Put":    short_k,
            "Long Put":     long_k,
            "~Credit":      round(credit, 2),
            "~Long Premium": round(long_p, 2),
            "ATM IV":       atm_iv,
            "IVR":          round(ivr, 2),
            "VIX":          round(vix_now, 1),
            "ADX":          round(adx_now, 1),
            "IV source":    iv_src,
            "nii_ok":       nii_ok,
            "vix_ok":       vix_ok,
            "iv_ok":        iv_ok,
            "n_pass":       n_pass,
            "all_pass":     n_pass == 3,
            "score":        score,
        }
    except Exception as e:
        logger.warning(f"PutSteal score error for {ticker}: {e}")
        return None


# ── New strategy screener functions (2026-05-01) ──────────────────────────────

def _score_hmm_regime(
    ticker: str,
    price_df: pd.DataFrame,
    vix_series: pd.Series,
    iv_metrics: dict,
    params: Optional[dict] = None,
) -> Optional[dict]:
    """Heuristic-fallback HMM regime classifier (no model loaded).

    Mirrors HMMRegimeStrategy._heuristic_signal: VIX-bucket → state →
    {SELL bull put, SELL iron condor, BUY long put}. Cheap (< 5 ms).
    """
    if price_df.empty or len(price_df) < 20:
        return None
    try:
        p = {**_DEFAULT_PARAMS.get("hmm_regime", {}), **(params or {})}
        close = price_df["close"].astype(float)
        spot  = float(close.iloc[-1])
        vix   = float(vix_series.iloc[-1]) if not vix_series.empty else 20.0

        atm_iv = iv_metrics.get("atm_iv") or vix / 100.0
        ivr    = iv_metrics.get("ivr")
        if ivr is None:
            ivr = _vix_ivr(vix_series)

        vix_ceiling = float(p.get("vix_ceiling", 40.0))
        conf_min    = float(p.get("regime_confidence_min", 0.55))

        ret_5d  = float(close.pct_change(5).iloc[-1])  if len(close) >= 6  else 0.0
        ret_20d = float(close.pct_change(20).iloc[-1]) if len(close) >= 21 else 0.0
        rv20    = float(close.pct_change().rolling(20, min_periods=10).std().iloc[-1]
                        * (252 ** 0.5)) if len(close) >= 10 else 0.0

        if vix > vix_ceiling:
            return {
                "Ticker": ticker, "Price": spot, "VIX": vix, "IVR": ivr,
                "Regime": "—", "P(state)": 0.0,
                "Trade": "HOLD", "Signal": "HOLD",
                "5d Ret": ret_5d, "20d Ret": ret_20d, "RV20": rv20,
                "ATM IV": atm_iv,
                "Status": f"VIX {vix:.1f} > ceiling {vix_ceiling:.0f}",
                "vix_ok": False, "conf_ok": False,
                "n_pass": 0, "all_pass": False, "score": 0.0,
                "Mode": "heuristic",
            }

        # Heuristic bucket — same as strategy.HMMRegime._heuristic_signal
        if vix < 15.0:
            state, regime, trade, signal = 0, "Low-Vol Bull", "Bull Put Credit Spread", "SELL"
        elif vix < 22.0:
            state, regime, trade, signal = 1, "Chop / Mean-Rev", "Iron Condor", "SELL"
        else:
            state, regime, trade, signal = 2, "High-Vol Bear", "Long Put Debit Spread", "BUY"

        # Heuristic confidence — fixed 0.55 to match strategy fallback
        p_state = 0.55
        conf_ok = p_state >= conf_min
        vix_ok  = vix <= vix_ceiling
        n_pass  = sum([vix_ok, conf_ok])

        # Score: regime conviction × IVR / VIX context
        score = min(100.0, p_state * 60 + (ivr or 0) * 30 + (10 if vix_ok else 0))

        return {
            "Ticker":   ticker,
            "Price":    spot,
            "VIX":      vix,
            "IVR":      ivr,
            "ATM IV":   atm_iv,
            "Regime":   regime,
            "State":    state,
            "P(state)": p_state,
            "Trade":    trade,
            "Signal":   signal,
            "5d Ret":   ret_5d,
            "20d Ret":  ret_20d,
            "RV20":     rv20,
            "Status":   "Heuristic — train HMM for full posterior",
            "Mode":     "heuristic",
            "vix_ok":   vix_ok,
            "conf_ok":  conf_ok,
            "n_pass":   n_pass,
            "all_pass": n_pass == 2,
            "score":    score,
        }
    except Exception as e:
        logger.warning(f"HMMRegime score error for {ticker}: {e}")
        return None


def _score_expiry_max_pain(
    ticker: str,
    price_df: pd.DataFrame,
    vix_series: pd.Series,
    iv_metrics: dict,
    params: Optional[dict] = None,
) -> Optional[dict]:
    """OpEx Max-Pain Pin screener — calendar + VIX gating only.

    Real signal requires options chain (max-pain strike + GEX), so this surfaces
    the calendar/VIX preconditions and tells the user to open the Backtest tab
    for a full analysis.
    """
    if price_df.empty or len(price_df) < 10:
        return None
    try:
        p = {**_DEFAULT_PARAMS.get("expiry_max_pain", {}), **(params or {})}
        close = price_df["close"].astype(float)
        spot  = float(close.iloc[-1])
        vix   = float(vix_series.iloc[-1]) if not vix_series.empty else 20.0

        atm_iv = iv_metrics.get("atm_iv") or vix / 100.0
        ivr    = iv_metrics.get("ivr")
        if ivr is None:
            ivr = _vix_ivr(vix_series)

        vix_ceiling = float(p.get("vix_ceiling", 25.0))
        ts          = pd.Timestamp.today().normalize()

        # Inline OpEx-week helpers (avoid importing strategy module which uses
        # absolute `alan_trader.*` imports incompatible with this layout)
        def _third_friday(year: int, month: int) -> pd.Timestamp:
            first  = pd.Timestamp(year=year, month=month, day=1)
            offset = (4 - first.weekday()) % 7
            return pd.Timestamp(year=year, month=month, day=1 + offset + 14)

        tf_this        = _third_friday(ts.year, ts.month).normalize()
        monday_of_opex = tf_this - pd.Timedelta(days=tf_this.weekday())
        friday_of_opex = monday_of_opex + pd.Timedelta(days=4)
        opex_week      = bool(monday_of_opex <= ts <= friday_of_opex)
        if ts <= tf_this:
            dte_to_opex = int((tf_this - ts).days)
        else:
            if ts.month == 12:
                nxt = _third_friday(ts.year + 1, 1).normalize()
            else:
                nxt = _third_friday(ts.year, ts.month + 1).normalize()
            dte_to_opex = int((nxt - ts).days)

        vix_ok    = vix <= vix_ceiling
        opex_ok   = opex_week and (2 <= dte_to_opex <= 5)
        n_pass    = sum([vix_ok, opex_ok])

        # Score: OpEx-window proximity + low-vol bonus
        if opex_ok:
            window_score = max(0.0, 1.0 - abs(dte_to_opex - 3) / 3.0) * 60
        else:
            window_score = 0.0
        vol_score = max(0.0, 1.0 - vix / 30.0) * 30 if vix_ok else 0.0
        ivr_score = (1.0 - min(ivr or 0, 1.0)) * 10  # prefer LOW IVR (pin works in chop)
        score = min(100.0, window_score + vol_score + ivr_score)

        if not opex_week:
            status = f"Not OpEx week (next OpEx in {dte_to_opex}d)"
        elif not opex_ok:
            status = f"OpEx wk but DTE {dte_to_opex} outside [2,5]"
        elif not vix_ok:
            status = f"VIX {vix:.1f} > ceiling {vix_ceiling:.0f}"
        else:
            status = "Calendar OK — open Backtest for chain"

        return {
            "Ticker":      ticker,
            "Price":       spot,
            "VIX":         vix,
            "ATM IV":      atm_iv,
            "IVR":         ivr,
            "OpEx Week":   "Yes" if opex_week else "No",
            "DTE to OpEx": dte_to_opex,
            "Structure":   "Iron Butterfly (short)",
            "Status":      status,
            "Mode":        "needs_chain",
            "vix_ok":      vix_ok,
            "opex_ok":     opex_ok,
            "n_pass":      n_pass,
            "all_pass":    n_pass == 2,
            "score":       score,
        }
    except Exception as e:
        logger.warning(f"ExpiryMaxPain score error for {ticker}: {e}")
        return None


def _score_short_squeeze_detector(
    ticker: str,
    price_df: pd.DataFrame,
    vix_series: pd.Series,
    iv_metrics: dict,
    params: Optional[dict] = None,
) -> Optional[dict]:
    """Short-squeeze ML detector — heuristic-fallback (no .pkl loaded).

    Without short-interest / utilization data we cannot fire the GBM model,
    so we surface the cheap proxies: VIX ceiling, recent volume spike,
    20-day return momentum. Tells user to open Backtest for full features.
    """
    if price_df.empty or len(price_df) < 25:
        return None
    try:
        p = {**_DEFAULT_PARAMS.get("short_squeeze_detector", {}), **(params or {})}
        close = price_df["close"].astype(float)
        vol   = price_df.get("volume", pd.Series(dtype=float)).astype(float)

        spot    = float(close.iloc[-1])
        vix     = float(vix_series.iloc[-1]) if not vix_series.empty else 20.0
        ret_5d  = float(close.pct_change(5).iloc[-1])  if len(close) >= 6  else 0.0
        ret_20d = float(close.pct_change(20).iloc[-1]) if len(close) >= 21 else 0.0

        # Volume ratio — today's volume / 20-day average
        if len(vol) >= 20 and vol.iloc[-21:-1].mean() > 0:
            vol_ratio = float(vol.iloc[-1] / vol.iloc[-21:-1].mean())
        else:
            vol_ratio = 1.0

        atm_iv = iv_metrics.get("atm_iv") or vix / 100.0
        ivr    = iv_metrics.get("ivr")
        if ivr is None:
            ivr = _vix_ivr(vix_series)

        max_vix      = float(p.get("max_vix", 32.0))
        vol_min      = float(p.get("volume_ratio_min", 2.5))
        signal_thr   = float(p.get("signal_threshold", 0.55))

        vix_ok = vix < max_vix
        vol_ok = vol_ratio >= vol_min
        # No SI data in screener → can't actually fire BUY; report heuristic confidence
        # similar to strategy._heuristic mode (0.4..0.7 range)
        if not vix_ok:
            heur_conf = 0.0
            status    = f"VIX {vix:.1f} ≥ max {max_vix:.0f}"
        elif not vol_ok:
            heur_conf = 0.0
            status    = f"Vol ratio {vol_ratio:.1f}× < min {vol_min:.1f}×"
        else:
            # Volume spike + positive momentum → modest squeeze prior
            momentum_bonus = max(0.0, min(ret_20d, 0.30)) * 1.5
            heur_conf = min(0.65, 0.40 + (vol_ratio - vol_min) * 0.05 + momentum_bonus)
            status    = "Volume spike — needs SI/chain (Backtest)"

        n_pass = sum([vix_ok, vol_ok])
        score  = min(100.0, heur_conf * 60 + (vol_ratio / 5.0) * 25 + max(0, ret_20d) * 50)

        return {
            "Ticker":     ticker,
            "Price":      spot,
            "VIX":        vix,
            "ATM IV":     atm_iv,
            "IVR":        ivr,
            "Vol Ratio":  vol_ratio,
            "5d Ret":     ret_5d,
            "20d Ret":    ret_20d,
            "P(squeeze)": heur_conf,
            "Signal Thr": signal_thr,
            "Structure":  "Long OTM Call",
            "Status":     status,
            "Mode":       "heuristic_no_model",
            "vix_ok":     vix_ok,
            "vol_ok":     vol_ok,
            "n_pass":     n_pass,
            "all_pass":   n_pass == 2,
            "score":      score,
        }
    except Exception as e:
        logger.warning(f"ShortSqueezeDetector score error for {ticker}: {e}")
        return None


def _score_tail_risk_put_spread(
    ticker: str,
    price_df: pd.DataFrame,
    vix_series: pd.Series,
    iv_metrics: dict,
    params: Optional[dict] = None,
) -> Optional[dict]:
    """Tail Risk Put Spread (SPY only) — calendar/VIX gates + indicative
    spread strikes & cost.

    Strategy is a mechanical scheduled buyer, so live screener simply confirms
    the VIX gate is open and shows what the next purchase would look like.
    """
    if price_df.empty or len(price_df) < 10:
        return None
    try:
        p = {**_DEFAULT_PARAMS.get("tail_risk_put_spread", {}), **(params or {})}
        close = price_df["close"].astype(float)
        spot  = float(close.iloc[-1])
        vix   = float(vix_series.iloc[-1]) if not vix_series.empty else 20.0

        atm_iv = iv_metrics.get("atm_iv") or max(0.05, vix / 100.0)
        ivr    = iv_metrics.get("ivr")
        if ivr is None:
            ivr = _vix_ivr(vix_series)

        vix_max  = float(p.get("vix_max_at_entry", 35.0))
        long_pct = float(p.get("long_otm_pct", 0.07))
        short_pct= float(p.get("short_otm_pct", 0.18))
        dte_tgt  = int(p.get("dte_target", 75))

        long_K   = round(spot * (1.0 - long_pct),  2)
        short_K  = round(spot * (1.0 - short_pct), 2)
        width    = round(long_K - short_K, 2)

        # Rough debit estimate: scaled BS-ish proxy using VIX as IV
        T          = dte_tgt / 365.0
        iv_long    = atm_iv * 1.20
        iv_short   = atm_iv * 1.10
        # crude OTM put price ≈ spot × IV × √T × delta_proxy
        long_prem  = spot * iv_long  * (T ** 0.5) * 0.18
        short_prem = spot * iv_short * (T ** 0.5) * 0.06
        debit      = max(0.05, long_prem - short_prem)

        vix_ok   = vix <= vix_max
        n_pass   = 1 if vix_ok else 0
        status   = ("Gate OPEN — calendar may trigger entry"
                    if vix_ok else f"VIX {vix:.1f} > {vix_max:.0f} (skip dislocated)")

        # Score: low-VIX bonus (cheap hedge) + spread economics
        vix_score   = max(0.0, 1.0 - vix / vix_max) * 60 if vix_ok else 0.0
        debit_score = max(0.0, 1.0 - debit / max(spot * 0.01, 0.5)) * 25
        ivr_score   = (1.0 - min(ivr or 0, 1.0)) * 15  # prefer LOW IVR for cheap hedge
        score = min(100.0, vix_score + debit_score + ivr_score)

        return {
            "Ticker":      ticker,
            "Price":       spot,
            "VIX":         vix,
            "ATM IV":      atm_iv,
            "IVR":         ivr,
            "Long Strike": long_K,
            "Short Strike": short_K,
            "Width":       width,
            "DTE":         dte_tgt,
            "~Debit":      round(debit, 3),
            "Max Payout":  round(width - debit, 2),
            "Structure":   "Bear Put Debit Spread",
            "Status":      status,
            "vix_ok":      vix_ok,
            "n_pass":      n_pass,
            "all_pass":    n_pass == 1,
            "score":       score,
        }
    except Exception as e:
        logger.warning(f"TailRiskPutSpread score error for {ticker}: {e}")
        return None


def _score_news_sentiment_nlp(
    ticker: str,
    price_df: pd.DataFrame,
    vix_series: pd.Series,
    iv_metrics: dict,
    params: Optional[dict] = None,
) -> Optional[dict]:
    """News-Sentiment NLP — heuristic-fallback (no model + no live news feed).

    Without sentiment_z + article_count from a news feed, we cannot fire BUY
    or SELL. We surface the cheap macro gate (VIX) and 5-day price drift as
    a sentiment proxy, and tell the user to open Backtest for full sentiment.
    """
    if price_df.empty or len(price_df) < 10:
        return None
    try:
        p = {**_DEFAULT_PARAMS.get("news_sentiment_nlp", {}), **(params or {})}
        close = price_df["close"].astype(float)
        spot  = float(close.iloc[-1])
        vix   = float(vix_series.iloc[-1]) if not vix_series.empty else 20.0

        atm_iv = iv_metrics.get("atm_iv") or vix / 100.0
        ivr    = iv_metrics.get("ivr")
        if ivr is None:
            ivr = _vix_ivr(vix_series)

        ret_1d  = float(close.pct_change(1).iloc[-1])  if len(close) >= 2  else 0.0
        ret_5d  = float(close.pct_change(5).iloc[-1])  if len(close) >= 6  else 0.0
        ret_20d = float(close.pct_change(20).iloc[-1]) if len(close) >= 21 else 0.0

        vix_max     = float(p.get("vix_max", 35.0))
        z_threshold = float(p.get("sentiment_z_threshold", 2.0))
        signal_thr  = float(p.get("signal_threshold", 0.55))

        vix_ok = vix <= vix_max
        # Price-drift proxy for sentiment z (gap normalized by 20-day vol)
        rv20   = float(close.pct_change().rolling(20, min_periods=10).std().iloc[-1]) \
                 if len(close) >= 10 else 0.01
        sentiment_proxy = ret_1d / max(rv20, 0.005)  # crude z-score

        if not vix_ok:
            status = f"VIX {vix:.1f} > max {vix_max:.0f} (macro override)"
            signal = "HOLD"
        elif abs(sentiment_proxy) >= z_threshold:
            status = "Price-proxy z >= threshold — needs news feed"
            signal = "BUY (proxy)" if sentiment_proxy > 0 else "SELL (proxy)"
        else:
            status = "Insufficient drift — needs news feed (Backtest)"
            signal = "HOLD"

        n_pass = sum([vix_ok, abs(sentiment_proxy) >= z_threshold])

        # Score: combine drift strength + low-VIX bonus
        z_score    = min(abs(sentiment_proxy) / max(z_threshold, 0.1), 2.0) * 40
        vix_bonus  = max(0.0, 1.0 - vix / vix_max) * 30 if vix_ok else 0.0
        ivr_bonus  = (ivr or 0) * 30  # higher IVR → richer spread
        score      = min(100.0, z_score + vix_bonus + ivr_bonus)

        return {
            "Ticker":     ticker,
            "Price":      spot,
            "VIX":        vix,
            "ATM IV":     atm_iv,
            "IVR":        ivr,
            "1d Ret":     ret_1d,
            "5d Ret":     ret_5d,
            "20d Ret":    ret_20d,
            "z (proxy)":  sentiment_proxy,
            "z thresh":   z_threshold,
            "Signal":     signal,
            "Structure":  "Debit Spread",
            "Status":     status,
            "Mode":       "heuristic_no_model",
            "vix_ok":     vix_ok,
            "z_ok":       abs(sentiment_proxy) >= z_threshold,
            "n_pass":     n_pass,
            "all_pass":   n_pass == 2,
            "score":      score,
        }
    except Exception as e:
        logger.warning(f"NewsSentimentNLP score error for {ticker}: {e}")
        return None


# ── Calendar helpers ───────────────────────────────────────────────────────────

def _next_monthly_friday(days_out: int = 35) -> str:
    """Return the nearest Friday on or after (today + days_out) as YYYY-MM-DD."""
    import datetime as _dt
    target = _dt.date.today() + _dt.timedelta(days=days_out)
    # weekday(): Mon=0 … Fri=4 … Sun=6
    days_to_friday = (4 - target.weekday()) % 7
    return (target + _dt.timedelta(days=days_to_friday)).strftime("%Y-%m-%d")
