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
        atr_pct      = latest_atr / latest_price * 100 if latest_price > 0 else 0.0

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
        atr_ok = atr_pct    <= params["atr_pct_max"] * 100

        n_pass = sum([ivr_ok, vix_ok, adx_ok, atr_ok])

        score = (
            ivr * 40
            + max(0, 1 - latest_adx / 50) * 30
            + max(0, 1 - atr_pct / 3)     * 20
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
        atr_pct      = latest_atr / latest_price * 100 if latest_price > 0 else 0.0

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
        atr_pct      = latest_atr / latest_price * 100 if latest_price > 0 else 0.0

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
        atr_pct      = latest_atr / latest_price * 100 if latest_price > 0 else 0.0

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

        score = (
            max(0, vrp or 0) * 100
            + (min(iv_over_hv or 1.0, 2.0) - 1.0) * 50
        )

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
        atr_pct      = latest_atr / latest_price * 100 if latest_price > 0 else 0.0

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
    from data.polygon_client import PolygonClient
    to_dt   = date.today().isoformat()
    from_dt = (date.today() - timedelta(days=bars * 2)).isoformat()
    try:
        df = PolygonClient(api_key=api_key).get_aggregates(ticker, from_dt, to_dt)
        return df.tail(bars) if not df.empty else pd.DataFrame()
    except Exception as e:
        logger.warning(f"Polygon OHLCV failed for {ticker}: {e}")
        return pd.DataFrame()


# ── Options chain helpers ──────────────────────────────────────────────────────

def _get_options_chain(ticker: str, api_key: str, spot: float,
                       dte_target: int = 45, dte_lo: int = 30, dte_hi: int = 60):
    """Fetch options chain from Polygon. Returns (chain_df, best_exp, dte_used) or None."""
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
            strike_price_gte=spot * 0.80,
            strike_price_lte=spot * 1.20,
        )
    except Exception as e:
        return None, None, None, str(e)

    if chain is None or chain.empty:
        return None, None, None, "No options data returned from Polygon"

    chain = chain.dropna(subset=["strike", "dte"]).copy()
    for col in ["strike", "dte", "iv", "bid", "ask", "delta"]:
        if col in chain.columns:
            chain[col] = pd.to_numeric(chain[col], errors="coerce")
    chain["mid"] = (chain["bid"] + chain["ask"]) / 2

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


def _get_chain_mid(df: pd.DataFrame, strike: float):
    """Look up mid price for a specific strike, or nearest."""
    if df.empty:
        return None, strike
    row = df[df["strike"] == strike]
    if row.empty:
        row = df.iloc[(df["strike"] - strike).abs().argsort()[:1]]
    m   = float(row["mid"].iloc[0]) if not row.empty and not pd.isna(row["mid"].iloc[0]) else None
    k   = float(row["strike"].iloc[0]) if not row.empty else strike
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
            atr_pct      = latest_atr / latest_price * 100 if latest_price > 0 else 0.0
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


# ── Calendar helpers ───────────────────────────────────────────────────────────

def _next_monthly_friday(days_out: int = 35) -> str:
    """Return the nearest Friday on or after (today + days_out) as YYYY-MM-DD."""
    import datetime as _dt
    target = _dt.date.today() + _dt.timedelta(days=days_out)
    # weekday(): Mon=0 … Fri=4 … Sun=6
    days_to_friday = (4 - target.weekday()) % 7
    return (target + _dt.timedelta(days=days_to_friday)).strftime("%Y-%m-%d")
