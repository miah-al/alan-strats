"""
Strategy-specific opportunity screener.

Architecture
------------
- VIX history  : mkt.VixBar (DB) — fallback IVR only
- Price OHLCV  : Polygon aggregates API — last 60 bars per ticker
- Per-ticker IV: Polygon options snapshot — ATM IV, IVR, VRP via iv_metrics.py
- No mkt.PriceBar dependency

Scan flow
---------
1. Load VIX from DB (one query — for fallback IVR and VIX level)
2. Fetch last 60 daily OHLCV bars from Polygon per ticker (HV20, ADX, ATR%)
3. Run iv_metrics batch: per-ticker ATM IV → IVR, VRP  (2-3 API calls/ticker)
4. Score each ticker against strategy filters
5. Rank and display

Supported strategies
--------------------
- iron_condor_rules / iron_condor_ai  : full 4-leg IC screener with payoff chart
- vix_spike_fade                       : VIX spike + 200-MA filter, bull call spread
- vol_arbitrage                        : skew + VRP > 0, shows 5-leg vol arb setup
- ivr_credit_spread                    : IVR ≥ 0.40, bull put or bear call spread
- iv_skew_momentum                     : put-call skew signal table
- gamma_flip_breakout                  : GEX signal table
- earnings_iv_crush                    : earnings pre/post IV signal table
- earnings_post_drift                  : post-earnings drift signal
- vol_calendar_spread                  : calendar spread signal
- everything else                      : stub "not yet configured"
"""

from __future__ import annotations

import logging
import math as _math
from datetime import date, timedelta
from typing import Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

logger = logging.getLogger(__name__)

# ── Universes ──────────────────────────────────────────────────────────────────

UNIVERSES: dict[str, list[str]] = {
    "ETF Core":   ["SPY", "QQQ", "IWM", "GLD", "TLT", "EEM", "XLF", "XLE", "XLK", "XLV"],
    "Index ETFs": ["SPY", "QQQ", "DIA", "IWM", "MDY", "VTI", "VEA", "VWO"],
    "Mega Cap":   ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "JPM"],
    "High IV":    ["TSLA", "NVDA", "MSTR", "COIN", "PLTR", "ARKK", "SOXL", "TQQQ"],
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
    from alan_trader.data.polygon_client import PolygonClient
    to_dt   = date.today().isoformat()
    from_dt = (date.today() - timedelta(days=bars * 2)).isoformat()
    try:
        df = PolygonClient(api_key=api_key).get_aggregates(ticker, from_dt, to_dt)
        return df.tail(bars) if not df.empty else pd.DataFrame()
    except Exception as e:
        logger.warning(f"Polygon OHLCV failed for {ticker}: {e}")
        return pd.DataFrame()


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

# ── Formatting helpers ─────────────────────────────────────────────────────────

def _ok(v: bool) -> str:
    return "✅" if v else "❌"

def _bar(score: float, mx: float = 100.0) -> str:
    n = int(round(score / mx * 10))
    return "█" * n + "░" * (10 - n)

def _pct(v) -> str:
    return f"{v*100:.1f}%" if v is not None else "—"

def _f2(v) -> str:
    return f"{v:.2f}" if v is not None else "—"


# ── VIX banner ─────────────────────────────────────────────────────────────────

def _render_vix_banner(vix_series: pd.Series, slug: str) -> None:
    current_vix = float(vix_series.iloc[-1]) if not vix_series.empty else 0.0
    current_ivr = _vix_ivr(vix_series)
    vix_as_of   = vix_series.index[-1] if hasattr(vix_series.index[-1], "date") else "?"
    vix_20d_avg = _vix_20d_avg(vix_series)

    vix_color = "#ef4444" if current_vix > 35 else "#f59e0b" if current_vix > 25 else "#10b981"

    if slug in ("iron_condor_rules", "iron_condor_ai"):
        status = (
            "🟢 VIX in IC sweet spot (14–45)"   if 14 <= current_vix <= 45 else
            "🔴 VIX > 45 — fear regime, ICs risky" if current_vix > 45 else
            "⚠️ VIX < 14 — premium too thin"
        )
    elif slug == "vix_spike_fade":
        ratio = current_vix / max(vix_20d_avg, 0.01)
        status = (
            f"🔴 VIX spike: {ratio:.1f}× above 20d avg — spike fade signal ACTIVE"
            if ratio >= 1.3 else
            f"⚠️ VIX / 20d avg = {ratio:.1f}× — no spike yet (need ≥ 1.3×)"
        )
    else:
        status = f"VIX 20d avg: {vix_20d_avg:.1f}"

    st.markdown(
        f"""<div style="display:flex;gap:32px;padding:10px 16px;background:#111827;
                border-radius:8px;border:1px solid #1f2937;margin-bottom:12px">
          <div><div style="color:#6b7280;font-size:11px">VIX (as of {vix_as_of})</div>
               <div style="color:{vix_color};font-size:1.3rem;font-weight:700">{current_vix:.2f}</div></div>
          <div><div style="color:#6b7280;font-size:11px">VIX 20d avg</div>
               <div style="color:#f9fafb;font-size:1.3rem;font-weight:700">{vix_20d_avg:.2f}</div></div>
          <div><div style="color:#6b7280;font-size:11px">VIX-IVR (52-wk rank)</div>
               <div style="color:#f9fafb;font-size:1.3rem;font-weight:700">{current_ivr:.2f}</div></div>
          <div><div style="color:#6b7280;font-size:11px">VIX data points</div>
               <div style="color:#f9fafb;font-size:1.3rem;font-weight:700">{len(vix_series)}</div></div>
          <div style="flex:1;align-self:center;color:#9ca3af;font-size:12px">{status}</div>
        </div>""", unsafe_allow_html=True,
    )


# ── Options chain helper ────────────────────────────────────────────────────────

def _get_options_chain(ticker: str, api_key: str, spot: float,
                       dte_target: int = 45, dte_lo: int = 30, dte_hi: int = 60):
    """Fetch options chain from Polygon. Returns (chain_df, best_exp, dte_used) or None."""
    from alan_trader.data.polygon_client import PolygonClient
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


# ── Payoff chart helpers ───────────────────────────────────────────────────────

def _ic_payoff_chart(
    ticker: str,
    spot: float,
    short_call_k: float,
    long_call_k: float,
    short_put_k: float,
    long_put_k: float,
    net_credit: float,
    dte_used: int,
    best_exp: str,
    atm_iv: float,
    params: dict,
) -> go.Figure:
    """Build Iron Condor payoff chart with strategy exit lines and BS today-line."""
    profit_target_pct = params.get("profit_target", 0.50)
    stop_loss_mult    = params.get("stop_loss_mult", 2.0)

    profit_close  = net_credit * profit_target_pct * 100
    stop_loss_val = -net_credit * stop_loss_mult * 100

    be_upper = short_call_k + net_credit
    be_lower = short_put_k  - net_credit

    prices = np.linspace(spot * 0.75, spot * 1.25, 400)

    def ic_pnl_expiry(S):
        call_spread = np.minimum(0, short_call_k - S) + np.maximum(0, S - long_call_k)
        put_spread  = np.minimum(0, S - short_put_k)  + np.maximum(0, long_put_k - S)
        return (net_credit + call_spread + put_spread) * 100

    def ic_pnl_today(S_arr):
        T_now = max(dte_used / 252, 0.001)
        r     = 0.045
        iv    = max(atm_iv, 0.01)
        pnl_arr = []
        for S in S_arr:
            sc = _bs_price(S, short_call_k, T_now, iv, r, "call")
            lc = _bs_price(S, long_call_k,  T_now, iv, r, "call")
            sp = _bs_price(S, short_put_k,  T_now, iv, r, "put")
            lp = _bs_price(S, long_put_k,   T_now, iv, r, "put")
            pnl_arr.append((net_credit + (-sc + lc - sp + lp)) * 100)
        return np.array(pnl_arr)

    pnl_expiry = ic_pnl_expiry(prices)
    pnl_today  = ic_pnl_today(prices)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=prices, y=np.where(pnl_expiry >= 0, pnl_expiry, 0),
        fill="tozeroy", fillcolor="rgba(16,185,129,0.10)",
        line=dict(width=0), showlegend=False, hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=prices, y=np.where(pnl_expiry < 0, pnl_expiry, 0),
        fill="tozeroy", fillcolor="rgba(239,68,68,0.10)",
        line=dict(width=0), showlegend=False, hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=prices, y=pnl_expiry,
        line=dict(color="#6366f1", width=2),
        name="P&L at expiry",
        hovertemplate="$%{x:.2f} → $%{y:.0f}<extra>At expiry</extra>",
    ))
    fig.add_trace(go.Scatter(
        x=prices, y=pnl_today,
        line=dict(color="#10b981", width=1.5, dash="dot"),
        name="P&L today (BS estimate)",
        hovertemplate="$%{x:.2f} → $%{y:.0f}<extra>Today</extra>",
    ))

    fig.add_hline(
        y=profit_close,
        line=dict(color="#10b981", width=1.5, dash="dash"),
        annotation_text=f"✅ 50% target: close +${profit_close:.0f}",
        annotation_position="top left",
        annotation_font_color="#10b981",
    )
    fig.add_hline(
        y=stop_loss_val,
        line=dict(color="#ef4444", width=1.5, dash="dash"),
        annotation_text=f"🛑 2× stop: close −${abs(stop_loss_val):.0f}",
        annotation_position="bottom left",
        annotation_font_color="#ef4444",
    )
    fig.add_hline(y=0, line=dict(color="#374151", width=1))

    fig.add_vline(x=spot,     line=dict(color="#f59e0b", width=1.5, dash="dash"),
                  annotation_text=f"Spot ${spot:.0f}", annotation_position="top right",
                  annotation_font_color="#f59e0b")
    fig.add_vline(x=be_upper, line=dict(color="#9ca3af", width=1, dash="dot"),
                  annotation_text=f"BE ${be_upper:.0f}", annotation_font_color="#9ca3af")
    fig.add_vline(x=be_lower, line=dict(color="#9ca3af", width=1, dash="dot"),
                  annotation_text=f"BE ${be_lower:.0f}", annotation_font_color="#9ca3af")

    fig.update_layout(
        title=dict(
            text=f"{ticker} Iron Condor — P&L Profile  |  Exp {best_exp} ({dte_used} DTE)  |  "
                 f"Exit: 50% profit · 2× stop · 21 DTE",
            font=dict(size=13),
        ),
        xaxis_title="Underlying Price",
        yaxis_title="P&L per Contract ($)",
        height=380,
        margin=dict(l=0, r=0, t=50, b=0),
        paper_bgcolor="#0a0e1a",
        plot_bgcolor="#111827",
        font=dict(color="#9ca3af", size=12),
        xaxis=dict(gridcolor="#1f2937", tickformat="$,.0f"),
        yaxis=dict(gridcolor="#1f2937", tickformat="$,.0f", zeroline=False),
        legend=dict(bgcolor="rgba(0,0,0,0)", orientation="h", y=-0.15),
    )
    return fig


def _bull_call_spread_chart(
    ticker: str,
    spot: float,
    long_call_k: float,
    short_call_k: float,
    net_debit: float,
    dte_used: int,
    best_exp: str,
    atm_iv: float,
) -> go.Figure:
    """Bull call spread payoff chart."""
    max_profit = (short_call_k - long_call_k - net_debit) * 100
    max_loss   = net_debit * 100
    be         = long_call_k + net_debit

    prices = np.linspace(spot * 0.75, spot * 1.30, 400)

    def pnl(S):
        long_payoff  = np.maximum(S - long_call_k, 0)
        short_payoff = np.maximum(S - short_call_k, 0)
        return (long_payoff - short_payoff - net_debit) * 100

    pnl_exp = pnl(prices)

    def pnl_today(S_arr):
        T   = max(dte_used / 252, 0.001)
        r   = 0.045
        iv  = max(atm_iv, 0.01)
        res = []
        for S in S_arr:
            lc = _bs_price(S, long_call_k,  T, iv, r, "call")
            sc = _bs_price(S, short_call_k, T, iv, r, "call")
            res.append((lc - sc - net_debit) * 100)
        return np.array(res)

    pnl_t = pnl_today(prices)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=prices, y=np.where(pnl_exp >= 0, pnl_exp, 0),
        fill="tozeroy", fillcolor="rgba(16,185,129,0.10)",
        line=dict(width=0), showlegend=False, hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=prices, y=np.where(pnl_exp < 0, pnl_exp, 0),
        fill="tozeroy", fillcolor="rgba(239,68,68,0.10)",
        line=dict(width=0), showlegend=False, hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(x=prices, y=pnl_exp, line=dict(color="#6366f1", width=2),
                             name="P&L at expiry",
                             hovertemplate="$%{x:.2f} → $%{y:.0f}<extra>Expiry</extra>"))
    fig.add_trace(go.Scatter(x=prices, y=pnl_t, line=dict(color="#10b981", width=1.5, dash="dot"),
                             name="P&L today (BS)",
                             hovertemplate="$%{x:.2f} → $%{y:.0f}<extra>Today</extra>"))

    fig.add_hline(y=0, line=dict(color="#374151", width=1))
    fig.add_hline(y=max_profit * 0.50, line=dict(color="#10b981", width=1.5, dash="dash"),
                  annotation_text=f"50% target: ${max_profit*0.50:.0f}",
                  annotation_font_color="#10b981", annotation_position="top left")
    fig.add_vline(x=be, line=dict(color="#9ca3af", width=1, dash="dot"),
                  annotation_text=f"BE ${be:.0f}", annotation_font_color="#9ca3af")
    fig.add_vline(x=spot, line=dict(color="#f59e0b", width=1.5, dash="dash"),
                  annotation_text=f"Spot ${spot:.0f}", annotation_position="top right",
                  annotation_font_color="#f59e0b")

    fig.update_layout(
        title=f"{ticker} Bull Call Spread  |  Exp {best_exp} ({dte_used} DTE)",
        xaxis_title="Underlying Price", yaxis_title="P&L per Contract ($)",
        height=360, margin=dict(l=0, r=0, t=50, b=0),
        paper_bgcolor="#0a0e1a", plot_bgcolor="#111827",
        font=dict(color="#9ca3af", size=12),
        xaxis=dict(gridcolor="#1f2937", tickformat="$,.0f"),
        yaxis=dict(gridcolor="#1f2937", tickformat="$,.0f", zeroline=False),
        legend=dict(bgcolor="rgba(0,0,0,0)", orientation="h", y=-0.15),
    )
    return fig


def _credit_spread_chart(
    ticker: str,
    spot: float,
    short_k: float,
    long_k: float,
    net_credit: float,
    spread_type: str,
    dte_used: int,
    best_exp: str,
    atm_iv: float,
) -> go.Figure:
    """Bull put or bear call credit spread payoff chart."""
    is_bull_put = "Put" in spread_type
    opt_type    = "put" if is_bull_put else "call"

    if is_bull_put:
        width      = short_k - long_k
        max_loss   = (width - net_credit) * 100
        max_profit = net_credit * 100
        be         = short_k - net_credit
    else:
        width      = long_k - short_k
        max_loss   = (width - net_credit) * 100
        max_profit = net_credit * 100
        be         = short_k + net_credit

    prices = np.linspace(spot * 0.75, spot * 1.25, 400)

    def pnl(S_arr):
        res = []
        for S in S_arr:
            if is_bull_put:
                short_payoff = max(short_k - S, 0)
                long_payoff  = max(long_k - S, 0)
            else:
                short_payoff = max(S - short_k, 0)
                long_payoff  = max(S - long_k, 0)
            res.append((net_credit - short_payoff + long_payoff) * 100)
        return np.array(res)

    def pnl_today(S_arr):
        T  = max(dte_used / 252, 0.001)
        r  = 0.045
        iv = max(atm_iv, 0.01)
        res = []
        for S in S_arr:
            sv = _bs_price(S, short_k, T, iv, r, opt_type)
            lv = _bs_price(S, long_k,  T, iv, r, opt_type)
            res.append((net_credit - sv + lv) * 100)
        return np.array(res)

    pnl_exp = pnl(prices)
    pnl_t   = pnl_today(prices)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=prices, y=np.where(pnl_exp >= 0, pnl_exp, 0),
        fill="tozeroy", fillcolor="rgba(16,185,129,0.10)",
        line=dict(width=0), showlegend=False, hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=prices, y=np.where(pnl_exp < 0, pnl_exp, 0),
        fill="tozeroy", fillcolor="rgba(239,68,68,0.10)",
        line=dict(width=0), showlegend=False, hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(x=prices, y=pnl_exp, line=dict(color="#6366f1", width=2),
                             name="P&L at expiry",
                             hovertemplate="$%{x:.2f} → $%{y:.0f}<extra>Expiry</extra>"))
    fig.add_trace(go.Scatter(x=prices, y=pnl_t, line=dict(color="#10b981", width=1.5, dash="dot"),
                             name="P&L today (BS)",
                             hovertemplate="$%{x:.2f} → $%{y:.0f}<extra>Today</extra>"))

    fig.add_hline(y=0, line=dict(color="#374151", width=1))
    fig.add_hline(y=max_profit * 0.50, line=dict(color="#10b981", width=1.5, dash="dash"),
                  annotation_text=f"50% target: ${max_profit*0.50:.0f}",
                  annotation_font_color="#10b981", annotation_position="top left")
    fig.add_vline(x=be, line=dict(color="#9ca3af", width=1, dash="dot"),
                  annotation_text=f"BE ${be:.0f}", annotation_font_color="#9ca3af")
    fig.add_vline(x=spot, line=dict(color="#f59e0b", width=1.5, dash="dash"),
                  annotation_text=f"Spot ${spot:.0f}", annotation_position="top right",
                  annotation_font_color="#f59e0b")

    fig.update_layout(
        title=f"{ticker} {spread_type}  |  Exp {best_exp} ({dte_used} DTE)",
        xaxis_title="Underlying Price", yaxis_title="P&L per Contract ($)",
        height=360, margin=dict(l=0, r=0, t=50, b=0),
        paper_bgcolor="#0a0e1a", plot_bgcolor="#111827",
        font=dict(color="#9ca3af", size=12),
        xaxis=dict(gridcolor="#1f2937", tickformat="$,.0f"),
        yaxis=dict(gridcolor="#1f2937", tickformat="$,.0f", zeroline=False),
        legend=dict(bgcolor="rgba(0,0,0,0)", orientation="h", y=-0.15),
    )
    return fig


# ── Save paper trade helpers ────────────────────────────────────────────────────

def _save_options_paper_trade(
    ticker: str,
    strategy_name: str,
    slug: str,
    expiry: str,
    legs: list[tuple],  # (direction, strike, opt_type, price, leg_type)
    qty: int,
) -> None:
    """Generic multi-leg options paper trade saver."""
    import uuid
    from alan_trader.db.client import get_engine
    from sqlalchemy import text

    trade_group = f"{slug[:4].upper()}-{ticker}-{str(uuid.uuid4())[:8].upper()}"
    today       = date.today()
    multiplier  = 100

    try:
        engine = get_engine()
        with engine.begin() as conn:
            for direction, strike, opt_type, price, leg_type in legs:
                exp_dt     = expiry.replace("-", "")[2:]
                cp         = "C" if opt_type == "call" else "P"
                strike_int = int(round(strike * 1000))
                symbol     = f"{ticker}{exp_dt}{cp}{strike_int:08d}"

                sec_row = conn.execute(text(
                    "SELECT SecurityId FROM portfolio.Security WHERE Symbol = :s"
                ), {"s": symbol}).fetchone()

                if sec_row is None:
                    sec_row = conn.execute(text("""
                        INSERT INTO portfolio.Security
                            (Symbol, SecurityType, Underlying, OptionType, Strike,
                             Expiration, Multiplier)
                        OUTPUT INSERTED.SecurityId
                        VALUES (:sym, 'option', :ul, :ot, :k, :exp, :mult)
                    """), {
                        "sym":  symbol,
                        "ul":   ticker,
                        "ot":   opt_type,
                        "k":    strike,
                        "exp":  expiry,
                        "mult": multiplier,
                    }).fetchone()

                sec_id = sec_row[0]

                conn.execute(text("""
                    INSERT INTO portfolio.[Transaction]
                        (BusinessDate, AccountId, TradeGroupId, StrategyName,
                         SecurityId, Direction, Quantity, TransactionPrice,
                         Commission, LegType, Source, Notes)
                    VALUES
                        (:bd, 1, :tg, :strat,
                         :sid, :dir, :qty, :px,
                         1.0, :lt, 'Screener', :notes)
                """), {
                    "bd":    today,
                    "tg":    trade_group,
                    "strat": strategy_name,
                    "sid":   sec_id,
                    "dir":   direction,
                    "qty":   qty,
                    "px":    price,
                    "lt":    leg_type,
                    "notes": f"{ticker} {slug} {expiry} | {leg_type} ${strike:.0f}",
                })

        # Net credit/debit summary
        net = sum(
            (-p if d == "BUY" else p)
            for d, _k, _t, p, _lt in legs
        ) * qty * multiplier

        label = "credit" if net >= 0 else "debit"
        st.toast(
            f"✅ {ticker} {strategy_name} saved — {qty} contract(s) · "
            f"Net {label}: ${abs(net):.0f}",
            icon="✅",
        )

    except Exception as e:
        st.error(f"Failed to save paper trade: {e}")


# ── IC display formatter ────────────────────────────────────────────────────────

def _fmt_ic(df: pd.DataFrame, params: dict, compact: bool = False) -> pd.DataFrame:
    rows = []
    for _, r in df.iterrows():
        vrp_str = f"{r['VRP']*100:+.1f}%" if r["VRP"] is not None else "—"
        ivh_str = f"{r['IV/HV']:.2f}×"   if r["IV/HV"] is not None else "—"
        conf    = r.get("IVR conf", "")
        conf_badge = " ⚠️" if "low" in str(conf) else ""
        row = {
            "Ticker":      r["Ticker"],
            "Price":       f"${r['Price']:.2f}",
            "ATM IV":      _pct(r["ATM IV"]),
            "IVR":         f"{r['IVR']:.2f}{conf_badge} {_ok(r['ivr_ok'])}",
            "VRP":         vrp_str,
            "HV20":        _pct(r["HV20"]),
            "IV/HV":       ivh_str,
            "VIX":         f"{r['VIX']:.1f} {_ok(r['vix_ok'])}",
            "ADX":         f"{r['ADX']:.1f} {_ok(r['adx_ok'])}",
            "ATR%":        f"{r['ATR%']:.2f}% {_ok(r['atr_ok'])}",
            "~Credit/shr": f"${r['~Credit']:.2f}",
        }
        if not compact:
            row["Score"] = f"{_bar(r['score'])} {r['score']:.0f}"
            row["IV src"] = r.get("IV source", "—")
        rows.append(row)
    return pd.DataFrame(rows)


# ── IC trade setup renderer ────────────────────────────────────────────────────

def _render_ic_trade_setup(ticker: str, row, api_key: str, params: dict, kp, slug: str) -> None:
    """Fetch real options chain and show the 4 IC legs with strikes, credits, breakevens."""
    spot   = row["Price"]
    atm_iv = row.get("ATM IV") or (row.get("VIX", 25) / 100)
    adx_ok = row.get("adx_ok", False)

    target_delta = 0.16 if adx_ok else 0.10
    delta_note   = "16-delta (normal)" if adx_ok else "10-delta (wider — ADX trending, more buffer needed)"
    st.caption(f"Strike target: {delta_note}")

    wing_pct = params.get("wing_width", 0.05)

    with st.spinner(f"Fetching {ticker} options chain…"):
        exp_chain, best_exp, dte_used, err = _get_options_chain(ticker, api_key, spot)

    if err or exp_chain is None or exp_chain.empty:
        st.warning(err or "No options data returned from Polygon for this ticker/expiration window.")
        return

    calls = exp_chain[exp_chain["type"].str.lower() == "call"].sort_values("strike")
    puts  = exp_chain[exp_chain["type"].str.lower() == "put"].sort_values("strike", ascending=False)

    short_call_k, short_call_mid = _find_strike(calls, "call", spot, target_delta)
    short_put_k,  short_put_mid  = _find_strike(puts,  "put",  spot, target_delta)

    if short_call_k is None or short_put_k is None:
        st.warning("Could not find suitable strikes — options chain may be sparse.")
        return

    wing_w = round(spot * wing_pct, 0)
    long_call_k_target = short_call_k + wing_w
    long_put_k_target  = short_put_k  - wing_w

    long_call_mid, long_call_k_actual = _get_chain_mid(calls, long_call_k_target)
    long_put_mid,  long_put_k_actual  = _get_chain_mid(puts,  long_put_k_target)

    def _m(v):
        return v if v is not None else 0.0

    net_credit   = _m(short_call_mid) + _m(short_put_mid) - _m(long_call_mid) - _m(long_put_mid)
    call_width   = long_call_k_actual - short_call_k
    put_width    = short_put_k - long_put_k_actual
    max_loss     = min(call_width, put_width) - net_credit
    be_upper     = short_call_k + net_credit
    be_lower     = short_put_k  - net_credit
    profit_target = net_credit * 0.50

    st.markdown(f"**Expiration: {best_exp}** ({dte_used} DTE) &nbsp;·&nbsp; Spot: ${spot:.2f}")

    leg_data = [
        {"Leg": "Long call (wing)",  "Strike": f"${long_call_k_actual:.0f}",  "Mid": f"${_m(long_call_mid):.2f}",  "Action": "BUY",  "Note": "Caps upside loss"},
        {"Leg": "Short call",        "Strike": f"${short_call_k:.0f}",        "Mid": f"${_m(short_call_mid):.2f}", "Action": "SELL", "Note": f"~{target_delta:.0%} delta"},
        {"Leg": "Short put",         "Strike": f"${short_put_k:.0f}",         "Mid": f"${_m(short_put_mid):.2f}",  "Action": "SELL", "Note": f"~{target_delta:.0%} delta"},
        {"Leg": "Long put (wing)",   "Strike": f"${long_put_k_actual:.0f}",   "Mid": f"${_m(long_put_mid):.2f}",  "Action": "BUY",  "Note": "Caps downside loss"},
    ]
    st.dataframe(pd.DataFrame(leg_data), hide_index=True, width="stretch")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Net Credit/shr",   f"${net_credit:.2f}")
    c2.metric("Max Loss/shr",     f"${max_loss:.2f}")
    c3.metric("50% Target",       f"${profit_target:.2f}")
    c4.metric("Upper Breakeven",  f"${be_upper:.2f}")
    c5.metric("Lower Breakeven",  f"${be_lower:.2f}")

    if net_credit > 0:
        rr_str = f"1:{max_loss/net_credit:.1f}" if max_loss > 0 else "—"
        st.caption(
            f"Credit/contract: **${net_credit*100:.0f}** · "
            f"Max loss/contract: **${max_loss*100:.0f}** · "
            f"Risk/reward: **{rr_str}** · "
            f"Close at 50% profit = **${profit_target*100:.0f}** credit captured"
        )
    else:
        st.warning("Net credit is zero or negative — options chain data may be stale or illiquid.")

    if not adx_ok:
        st.warning(
            f"⚠️ ADX filter failing — market is trending. "
            f"Strikes widened to {target_delta:.0%}-delta for extra buffer. "
            "Consider waiting for ADX to drop below 35 before entering."
        )

    if net_credit > 0:
        fig = _ic_payoff_chart(
            ticker, spot,
            short_call_k, long_call_k_actual,
            short_put_k, long_put_k_actual,
            net_credit, dte_used, best_exp, atm_iv, params,
        )
        st.plotly_chart(fig, width="stretch")
        st.caption(
            "Solid purple = P&L at expiry · Dotted green = P&L today (BS) · "
            "Green dashed = 50% profit target · Red dashed = 2× stop loss"
        )

    st.markdown("---")
    _c1, _c2 = st.columns([2, 3])
    qty = _c1.number_input("Contracts", min_value=1, max_value=50, value=1, step=1,
                            key=kp(f"ss_qty_{ticker}"))
    _confirm_key = kp(f"ss_confirm_{ticker}")
    strategy_name = "Iron Condor — Rules" if "rules" in slug else "Iron Condor — AI"
    net_credit_show = _m(short_call_mid) + _m(short_put_mid) - _m(long_call_mid) - _m(long_put_mid)

    if not st.session_state.get(_confirm_key):
        if _c2.button(f"💾 Save {ticker} Iron Condor", type="primary", key=kp(f"ss_save_{ticker}")):
            st.session_state[_confirm_key] = True
            st.rerun()
    else:
        st.warning(
            f"Confirm: **{qty} × {ticker} Iron Condor** expiring {best_exp} · "
            f"Net credit ${net_credit_show:.2f}/shr (${net_credit_show*qty*100:.0f} total)"
        )
        _ok_col, _no_col = st.columns(2)
        if _ok_col.button("✅ Confirm Save", type="primary", key=kp(f"ss_confirm_yes_{ticker}")):
            legs = [
                ("SELL", short_call_k,       "call", _m(short_call_mid), "ShortCall"),
                ("BUY",  long_call_k_actual, "call", _m(long_call_mid),  "LongCall"),
                ("SELL", short_put_k,        "put",  _m(short_put_mid),  "ShortPut"),
                ("BUY",  long_put_k_actual,  "put",  _m(long_put_mid),   "LongPut"),
            ]
            _save_options_paper_trade(ticker, strategy_name, slug, best_exp, legs, qty)
            st.session_state.pop(_confirm_key, None)
        if _no_col.button("✗ Cancel", key=kp(f"ss_confirm_no_{ticker}")):
            st.session_state.pop(_confirm_key, None)
            st.rerun()


# ── VIX Spike Fade trade setup renderer ────────────────────────────────────────

def _render_vix_spike_fade_setup(ticker: str, row, api_key: str, kp, slug: str) -> None:
    """Bull call spread setup for VIX spike fade strategy."""
    spot   = row["Price"]
    atm_iv = row.get("ATM IV") or (row.get("VIX", 25) / 100)

    st.caption(
        f"VIX: {row.get('VIX', 0):.1f}  |  20d avg: {row.get('VIX 20d avg', 0):.1f}  |  "
        f"Ratio: {row.get('VIX / 20d', 0):.2f}×  |  "
        f"Above 200-MA: {'✅' if row.get('above_ma200') else '❌'}  |  "
        f"Signal: {'✅ ACTIVE' if row.get('vix_spike_ok') else '⚠️ No spike'}"
    )

    if not row.get("all_pass"):
        st.warning("Not all filters pass — review signals above before entering.")

    with st.spinner(f"Fetching {ticker} options chain…"):
        exp_chain, best_exp, dte_used, err = _get_options_chain(
            ticker, api_key, spot, dte_target=30, dte_lo=21, dte_hi=45
        )

    if err or exp_chain is None or exp_chain.empty:
        st.warning(err or "No options data returned from Polygon.")
        return

    calls = exp_chain[exp_chain["type"].str.lower() == "call"].sort_values("strike")

    # Long ATM call, short OTM call (~10-15% OTM)
    long_call_k, long_call_mid = _find_strike(calls, "call", spot, 0.50)   # ATM
    short_call_k, short_call_mid = _find_strike(calls, "call", spot, 0.25)  # ~10% OTM

    if long_call_k is None or short_call_k is None:
        st.warning("Could not find suitable strikes.")
        return

    def _m(v): return v if v is not None else 0.0

    net_debit  = _m(long_call_mid) - _m(short_call_mid)
    max_profit = (short_call_k - long_call_k - net_debit) * 100
    max_loss   = net_debit * 100
    be         = long_call_k + net_debit

    st.markdown(f"**Expiration: {best_exp}** ({dte_used} DTE) &nbsp;·&nbsp; Spot: ${spot:.2f}")
    st.caption("Bull Call Spread — buy ATM call, sell OTM call to finance, profit if VIX fades and price recovers")

    leg_data = [
        {"Leg": "Long call (ATM)",  "Strike": f"${long_call_k:.0f}",  "Mid": f"${_m(long_call_mid):.2f}",  "Action": "BUY",  "Note": "ATM ~50Δ"},
        {"Leg": "Short call (OTM)", "Strike": f"${short_call_k:.0f}", "Mid": f"${_m(short_call_mid):.2f}", "Action": "SELL", "Note": "~25Δ cap"},
    ]
    st.dataframe(pd.DataFrame(leg_data), hide_index=True, width="stretch")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Net Debit/shr",  f"${net_debit:.2f}")
    c2.metric("Max Profit/shr", f"${max_profit/100:.2f}" if max_profit > 0 else "—")
    c3.metric("Max Loss/shr",   f"-${net_debit:.2f}")
    c4.metric("Breakeven",      f"${be:.2f}")

    if max_profit > 0:
        fig = _bull_call_spread_chart(
            ticker, spot, long_call_k, short_call_k,
            net_debit, dte_used, best_exp, atm_iv,
        )
        st.plotly_chart(fig, width="stretch")
        st.caption("Solid purple = P&L at expiry · Dotted green = P&L today (BS)")

    st.markdown("---")
    _c1, _c2 = st.columns([2, 3])
    qty = _c1.number_input("Contracts", min_value=1, max_value=50, value=1, step=1,
                            key=kp(f"ss_qty_{ticker}"))
    _confirm_key = kp(f"ss_confirm_{ticker}")
    if not st.session_state.get(_confirm_key):
        if _c2.button(f"💾 Save {ticker} Bull Call Spread", type="primary", key=kp(f"ss_save_{ticker}")):
            st.session_state[_confirm_key] = True
            st.rerun()
    else:
        st.warning(f"Confirm: **{qty} × {ticker} Bull Call Spread** expiring {best_exp} · Debit ${net_debit:.2f}/shr")
        _ok_col, _no_col = st.columns(2)
        if _ok_col.button("✅ Confirm Save", type="primary", key=kp(f"ss_confirm_yes_{ticker}")):
            legs = [
                ("BUY",  long_call_k,  "call", _m(long_call_mid),  "LongCallATK"),
                ("SELL", short_call_k, "call", _m(short_call_mid), "ShortCall"),
            ]
            _save_options_paper_trade(ticker, "VIX Spike Fade", slug, best_exp, legs, qty)
            st.session_state.pop(_confirm_key, None)
        if _no_col.button("✗ Cancel", key=kp(f"ss_confirm_no_{ticker}")):
            st.session_state.pop(_confirm_key, None)
            st.rerun()


# ── Vol Arbitrage trade setup renderer ─────────────────────────────────────────

def _render_vol_arb_setup(ticker: str, row, api_key: str, kp, slug: str) -> None:
    """Vol arb: short ATM straddle + long OTM strangle for skew capture."""
    spot   = row["Price"]
    atm_iv = row.get("ATM IV") or 0.25
    hv20   = row.get("HV20") or 0.20
    vrp    = row.get("VRP") or 0.0

    st.caption(
        f"ATM IV: {_pct(atm_iv)}  |  HV20: {_pct(hv20)}  |  "
        f"VRP: {vrp*100:+.1f}%  |  IV/HV: {row.get('IV/HV', 0):.2f}×  |  "
        f"Signal: {'✅ IV > HV (sell vol)' if row.get('vrp_ok') else '⚠️ No VRP premium'}"
    )

    with st.spinner(f"Fetching {ticker} options chain…"):
        exp_chain, best_exp, dte_used, err = _get_options_chain(ticker, api_key, spot)

    if err or exp_chain is None or exp_chain.empty:
        st.warning(err or "No options data returned from Polygon.")
        return

    calls = exp_chain[exp_chain["type"].str.lower() == "call"].sort_values("strike")
    puts  = exp_chain[exp_chain["type"].str.lower() == "put"].sort_values("strike", ascending=False)

    # Short ATM straddle: short ATM call + short ATM put
    atm_call_k, atm_call_mid = _find_strike(calls, "call", spot, 0.50)
    atm_put_k,  atm_put_mid  = _find_strike(puts,  "put",  spot, 0.50)
    # Long OTM strangle: long 10-delta call + long 10-delta put (wing protection)
    otm_call_k, otm_call_mid = _find_strike(calls, "call", spot, 0.10)
    otm_put_k,  otm_put_mid  = _find_strike(puts,  "put",  spot, 0.10)

    if atm_call_k is None or atm_put_k is None:
        st.warning("Could not find ATM strikes.")
        return

    def _m(v): return v if v is not None else 0.0

    net_credit = (
        _m(atm_call_mid) + _m(atm_put_mid)
        - _m(otm_call_mid) - _m(otm_put_mid)
    )

    st.markdown(f"**Expiration: {best_exp}** ({dte_used} DTE) &nbsp;·&nbsp; Spot: ${spot:.2f}")
    st.caption("Short Iron Butterfly / Condor — sell ATM straddle, buy OTM strangle for protection. Profits if IV contracts toward HV.")

    leg_data = [
        {"Leg": "Long OTM call (wing)", "Strike": f"${otm_call_k:.0f}" if otm_call_k else "—", "Mid": f"${_m(otm_call_mid):.2f}", "Action": "BUY",  "Note": "10Δ wing"},
        {"Leg": "Short ATM call",       "Strike": f"${atm_call_k:.0f}", "Mid": f"${_m(atm_call_mid):.2f}", "Action": "SELL", "Note": "50Δ short"},
        {"Leg": "Short ATM put",        "Strike": f"${atm_put_k:.0f}",  "Mid": f"${_m(atm_put_mid):.2f}",  "Action": "SELL", "Note": "50Δ short"},
        {"Leg": "Long OTM put (wing)",  "Strike": f"${otm_put_k:.0f}"  if otm_put_k else "—",  "Mid": f"${_m(otm_put_mid):.2f}",  "Action": "BUY",  "Note": "10Δ wing"},
    ]
    st.dataframe(pd.DataFrame(leg_data), hide_index=True, width="stretch")

    c1, c2, c3 = st.columns(3)
    c1.metric("Net Credit/shr", f"${net_credit:.2f}")
    c2.metric("VRP premium",    f"{vrp*100:+.1f}%" if vrp else "—")
    c3.metric("IV/HV ratio",    f"{row.get('IV/HV', 0):.2f}×")

    if net_credit > 0:
        st.info(
            f"VRP = {vrp*100:+.1f}% — implied vol is {vrp*100:.1f}pp above realized. "
            "This short-vol structure profits as IV contracts toward HV. "
            "Target: close at 50% of credit when IV normalizes."
        )

    st.markdown("---")
    qty = st.number_input("Contracts", min_value=1, max_value=50, value=1, step=1,
                          key=kp(f"ss_qty_{ticker}"))

    build_legs = []
    if otm_call_k:
        build_legs.append(("BUY",  otm_call_k, "call", _m(otm_call_mid), "LongCall"))
    if atm_call_k:
        build_legs.append(("SELL", atm_call_k, "call", _m(atm_call_mid), "ShortCall"))
    if atm_put_k:
        build_legs.append(("SELL", atm_put_k,  "put",  _m(atm_put_mid),  "ShortPut"))
    if otm_put_k:
        build_legs.append(("BUY",  otm_put_k,  "put",  _m(otm_put_mid),  "LongPut"))

    _confirm_key = kp(f"ss_confirm_{ticker}")
    _c1, _c2 = st.columns([2, 3])
    if not st.session_state.get(_confirm_key):
        if _c2.button(f"💾 Save {ticker} Vol Arb", type="primary", key=kp(f"ss_save_{ticker}")):
            if build_legs:
                st.session_state[_confirm_key] = True
                st.rerun()
            else:
                st.error("No legs to save — check options chain data.")
    else:
        st.warning(f"Confirm: **{qty} × {ticker} Vol Arb** expiring {best_exp} · Net credit ${net_credit:.2f}/shr")
        _ok_col, _no_col = st.columns(2)
        if _ok_col.button("✅ Confirm Save", type="primary", key=kp(f"ss_confirm_yes_{ticker}")):
            _save_options_paper_trade(ticker, "Vol Arbitrage", slug, best_exp, build_legs, qty)
            st.session_state.pop(_confirm_key, None)
        if _no_col.button("✗ Cancel", key=kp(f"ss_confirm_no_{ticker}")):
            st.session_state.pop(_confirm_key, None)
            st.rerun()


# ── IVR Credit Spread trade setup renderer ─────────────────────────────────────

def _render_ivr_credit_spread_setup(ticker: str, row, api_key: str, kp, slug: str) -> None:
    """Bull put or bear call spread based on trend direction."""
    spot        = row["Price"]
    atm_iv      = row.get("ATM IV") or 0.25
    spread_type = row.get("Spread Type", "Bull Put Spread")
    is_bull_put = "Put" in spread_type

    st.caption(
        f"IVR: {row.get('IVR', 0):.2f}  |  ATM IV: {_pct(atm_iv)}  |  "
        f"Trend: {row.get('Trend', '—')}  |  "
        f"Suggested: **{spread_type}**"
    )

    with st.spinner(f"Fetching {ticker} options chain…"):
        exp_chain, best_exp, dte_used, err = _get_options_chain(ticker, api_key, spot)

    if err or exp_chain is None or exp_chain.empty:
        st.warning(err or "No options data returned from Polygon.")
        return

    opt_type = "put" if is_bull_put else "call"
    all_opts = exp_chain[exp_chain["type"].str.lower() == opt_type].copy()
    if is_bull_put:
        all_opts = all_opts.sort_values("strike", ascending=False)
    else:
        all_opts = all_opts.sort_values("strike")

    # Short ~16-delta, long ~10-delta (one strike further OTM)
    short_k, short_mid = _find_strike(all_opts, opt_type, spot, 0.16)
    long_k,  long_mid  = _find_strike(all_opts, opt_type, spot, 0.10)

    if short_k is None or long_k is None:
        st.warning("Could not find suitable strikes.")
        return

    def _m(v): return v if v is not None else 0.0

    net_credit = _m(short_mid) - _m(long_mid)
    width      = abs(short_k - long_k)
    max_loss   = (width - net_credit) * 100
    max_profit = net_credit * 100
    be         = (short_k - net_credit) if is_bull_put else (short_k + net_credit)

    st.markdown(f"**Expiration: {best_exp}** ({dte_used} DTE) &nbsp;·&nbsp; Spot: ${spot:.2f}")

    if is_bull_put:
        leg_data = [
            {"Leg": "Short put (OTM)",     "Strike": f"${short_k:.0f}", "Mid": f"${_m(short_mid):.2f}", "Action": "SELL", "Note": "~16Δ short"},
            {"Leg": "Long put (further OTM)", "Strike": f"${long_k:.0f}",  "Mid": f"${_m(long_mid):.2f}",  "Action": "BUY",  "Note": "~10Δ wing"},
        ]
    else:
        leg_data = [
            {"Leg": "Short call (OTM)",      "Strike": f"${short_k:.0f}", "Mid": f"${_m(short_mid):.2f}", "Action": "SELL", "Note": "~16Δ short"},
            {"Leg": "Long call (further OTM)", "Strike": f"${long_k:.0f}", "Mid": f"${_m(long_mid):.2f}",  "Action": "BUY",  "Note": "~10Δ wing"},
        ]
    st.dataframe(pd.DataFrame(leg_data), hide_index=True, width="stretch")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Net Credit/shr", f"${net_credit:.2f}")
    c2.metric("Max Loss/shr",   f"${max_loss/100:.2f}")
    c3.metric("50% Target",     f"${net_credit*0.5:.2f}")
    c4.metric("Breakeven",      f"${be:.2f}")

    if net_credit > 0:
        fig = _credit_spread_chart(
            ticker, spot, short_k, long_k,
            net_credit, spread_type, dte_used, best_exp, atm_iv,
        )
        st.plotly_chart(fig, width="stretch")
        st.caption("Solid purple = P&L at expiry · Dotted green = P&L today (BS)")

    if is_bull_put:
        lt_short, lt_long = "ShortPut", "LongPut"
    else:
        lt_short, lt_long = "ShortCall", "LongCall"
    legs = [
        ("SELL", short_k, opt_type, _m(short_mid), lt_short),
        ("BUY",  long_k,  opt_type, _m(long_mid),  lt_long),
    ]

    st.markdown("---")
    _c1, _c2 = st.columns([2, 3])
    qty = _c1.number_input("Contracts", min_value=1, max_value=50, value=1, step=1,
                            key=kp(f"ss_qty_{ticker}"))
    _confirm_key = kp(f"ss_confirm_{ticker}")
    if not st.session_state.get(_confirm_key):
        if _c2.button(f"💾 Save {ticker} {spread_type}", type="primary", key=kp(f"ss_save_{ticker}")):
            st.session_state[_confirm_key] = True
            st.rerun()
    else:
        st.warning(f"Confirm: **{qty} × {ticker} {spread_type}** expiring {best_exp} · Net credit ${net_credit:.2f}/shr")
        _ok_col, _no_col = st.columns(2)
        if _ok_col.button("✅ Confirm Save", type="primary", key=kp(f"ss_confirm_yes_{ticker}")):
            _save_options_paper_trade(ticker, f"IVR Credit Spread ({spread_type})", slug, best_exp, legs, qty)
            st.session_state.pop(_confirm_key, None)
        if _no_col.button("✗ Cancel", key=kp(f"ss_confirm_no_{ticker}")):
            st.session_state.pop(_confirm_key, None)
            st.rerun()


# ── Generic signal table renderers ─────────────────────────────────────────────

def _render_generic_signal_table(results: list[dict], slug: str) -> None:
    """Show a basic signal table for strategies without a dedicated setup renderer."""
    if not results:
        return
    df = pd.DataFrame(results)
    # Format numeric columns
    fmt_cols = {}
    for col in df.columns:
        sample = df[col].dropna()
        if sample.empty:
            continue
        val = sample.iloc[0]
        if col in ("ATM IV", "HV20", "VRP") and isinstance(val, float):
            df[col] = df[col].apply(lambda v: f"{v*100:.1f}%" if v is not None else "—")
        elif col == "IV/HV" and isinstance(val, float):
            df[col] = df[col].apply(lambda v: f"{v:.2f}×" if v is not None else "—")
        elif col == "Price" and isinstance(val, float):
            df[col] = df[col].apply(lambda v: f"${v:.2f}" if v is not None else "—")
        elif col == "ATR%" and isinstance(val, float):
            df[col] = df[col].apply(lambda v: f"{v:.2f}%" if v is not None else "—")
    st.dataframe(df, hide_index=True, width="stretch")


def _render_iv_skew_momentum(results: list[dict]) -> None:
    st.markdown("#### IV Skew Momentum Signals")
    st.caption("Screens for put/call IV skew anomalies. Buy calls when put IV > call IV at same strike (put-rich relative to call).")
    if results:
        _render_generic_signal_table(results, "iv_skew_momentum")
    st.info(
        "Full skew signal requires put/call IV at matched strikes. "
        "IVR and VRP data shown above. For detailed skew chart, open a position in Paper Trading."
    )


def _render_gamma_flip_breakout(results: list[dict]) -> None:
    st.markdown("#### Gamma Flip / Breakout Signals")
    st.caption("Screens for gamma exposure flip points where dealer hedging could accelerate moves.")
    if results:
        _render_generic_signal_table(results, "gamma_flip_breakout")
    st.info(
        "Full gamma flip analysis requires GEX (Gamma Exposure) data from options open interest. "
        "ADX and ATR signals shown above as directional proxies."
    )


def _render_earnings_iv_crush(results: list[dict]) -> None:
    st.markdown("#### Earnings IV Crush Signals")
    st.caption("Screens for tickers approaching earnings where IV is elevated (IV crush opportunity post-earnings).")
    if results:
        _render_generic_signal_table(results, "earnings_iv_crush")
    st.info(
        "Full earnings IV crush signal requires earnings date calendar. "
        "IV/HV ratio above 1.5× suggests elevated IV that may collapse after earnings. "
        "Consider short straddle or iron condor positioned to expire just after earnings."
    )


def _render_earnings_post_drift(results: list[dict]) -> None:
    st.markdown("#### Earnings Post-Drift Signals")
    st.caption("Screens for tickers showing post-earnings price drift patterns.")
    if results:
        _render_generic_signal_table(results, "earnings_post_drift")
    st.info(
        "Post-earnings drift strategy: after a large earnings move, stocks often continue "
        "drifting in the same direction for 5-20 days. Look for high ADX + direction signal."
    )


def _render_vol_calendar_spread(results: list[dict], api_key: str, kp) -> None:
    st.markdown("#### Vol Calendar Spread Signals")
    st.caption("Screens for term structure opportunities — buy near-term IV, sell far-term IV (or vice versa).")
    if results:
        _render_generic_signal_table(results, "vol_calendar_spread")
    st.info(
        "Calendar spread profits from time decay differences between near and far expiry. "
        "Ideal when near-term IV < far-term IV (normal backwardation). "
        "Full implementation requires multi-expiry IV comparison."
    )


def _render_short_squeeze(results: list[dict]) -> None:
    st.markdown("#### Short Squeeze / Vol Expansion Signals")
    st.caption("Screens for tickers with high short interest + rising IV (potential squeeze candidates).")
    if results:
        _render_generic_signal_table(results, "short_squeeze_vol_expansion")
    st.info(
        "Short squeeze signal requires short interest data (not available from Polygon basic tier). "
        "Rising ATR% and IV expansion shown above as proxy signals."
    )


def _render_oi_imbalance(results: list[dict]) -> None:
    st.markdown("#### OI Imbalance / Put Fade Signals")
    st.caption("Screens for large put open interest imbalances (contrarian put-fade opportunity).")
    if results:
        _render_generic_signal_table(results, "oi_imbalance_put_fade")
    st.info(
        "Full OI imbalance requires open interest by strike from options chain. "
        "High IVR with downward price pressure shown above as proxy signal. "
        "A put/call OI ratio > 1.5 at strikes below spot is the primary entry trigger."
    )


def _render_vol_term_structure(results: list[dict]) -> None:
    st.markdown("#### Vol Term Structure Regime Signals")
    st.caption("Screens for VIX term structure regime changes (contango vs backwardation).")
    if results:
        _render_generic_signal_table(results, "vol_term_structure_regime")
    st.info(
        "VIX term structure (VIX vs VIX3M vs VIX6M) drives regime classification. "
        "Backwardation (VIX > VIX3M) signals fear/stress. "
        "VIX-IVR and current VIX/20d-avg ratio shown above as proxies."
    )


# ── Phase 1-3: Data loading pipeline ───────────────────────────────────────────

def _run_data_pipeline(tickers: list[str], api_key: str, fetch_ivr_history: bool):
    """
    Run VIX DB load + Polygon OHLCV + IV metrics.
    Returns (vix_series, price_dfs, iv_all, errors) or raises on fatal error.
    """
    from alan_trader.db.client import get_engine, get_vix_bars
    from alan_trader.dashboard.tabs.iv_metrics import get_iv_metrics_batch

    # Phase 1 — VIX
    with st.spinner("Loading VIX history from DB…"):
        try:
            engine      = get_engine()
            vix_df      = get_vix_bars(engine, date.today() - timedelta(days=400), date.today())
            if vix_df.empty:
                st.error("No VIX data in DB. Run a data sync first (Tools → Data).")
                return None, None, None, None
            vix_series = vix_df["close"].astype(float)
        except Exception as e:
            st.error(f"DB error: {e}")
            return None, None, None, None

    # Phase 2 — OHLCV
    price_dfs: dict[str, pd.DataFrame] = {}
    all_errors: list[dict] = []
    prog1 = st.progress(0.0, text="Fetching price data from Polygon…")
    for i, ticker in enumerate(tickers):
        prog1.progress((i + 1) / len(tickers), text=f"Prices: {ticker}…")
        df = _fetch_ohlcv(ticker, api_key)
        if df.empty:
            all_errors.append({"Ticker": ticker, "Issue": "No Polygon price data"})
        else:
            price_dfs[ticker] = df
    prog1.empty()

    if not price_dfs:
        st.error("Could not fetch price data for any ticker. Check your API key.")
        return None, None, None, None

    # Phase 3 — IV metrics
    prog2 = st.progress(0.0, text="Fetching options IV from Polygon…")
    iv_all = get_iv_metrics_batch(
        tickers=list(price_dfs.keys()),
        api_key=api_key,
        price_dfs=price_dfs,
        fetch_ivr_history=fetch_ivr_history,
        on_progress=lambda t, i, n: prog2.progress((i + 1) / n, text=f"IV metrics: {t}…"),
    )
    prog2.empty()

    return vix_series, price_dfs, iv_all, all_errors


# ── Main render ────────────────────────────────────────────────────────────────

def render(slug: str, api_key: str = "", key_prefix: str = "") -> None:
    def kp(k: str) -> str:
        return f"{key_prefix}{k}" if key_prefix else k

    from alan_trader.strategies.registry import STRATEGY_METADATA
    meta         = STRATEGY_METADATA.get(slug, {})
    display_name = meta.get("display_name", slug)

    st.markdown(f"### 🔍 {display_name} — Opportunity Scanner")
    st.caption("Per-ticker IV from Polygon options · VIX history from DB · No mkt.PriceBar needed")

    # ── Stub: unknown strategies ──────────────────────────────────────────────
    _SUPPORTED = {
        "iron_condor_rules", "iron_condor_ai",
        "vix_spike_fade", "vol_arbitrage", "ivr_credit_spread",
        "iv_skew_momentum", "gamma_flip_breakout",
        "earnings_iv_crush", "earnings_post_drift",
        "vol_calendar_spread", "short_squeeze_vol_expansion",
        "oi_imbalance_put_fade", "vol_term_structure_regime",
    }
    if slug not in _SUPPORTED:
        st.info(f"Screener not yet configured for strategy: **{display_name}** (`{slug}`)")
        st.caption(
            "The signal data pipeline and scoring criteria for this strategy are under development. "
            "Use the Strategy Selector tab to run a backtest instead."
        )
        return

    if not api_key:
        st.warning("Enter your **Polygon API key** in the sidebar to use the scanner.")
        return

    # ── Universe ──────────────────────────────────────────────────────────────
    c1, c2 = st.columns([2, 4])
    univ = c1.selectbox("Universe", ["Custom"] + list(UNIVERSES.keys()), key=kp("ss_univ"))
    if univ == "Custom":
        raw     = c2.text_input("Tickers (comma-separated)", value="SPY,QQQ,IWM,GLD,TLT", key=kp("ss_custom"))
        tickers = [t.strip().upper() for t in raw.split(",") if t.strip()]
    else:
        tickers = UNIVERSES[univ]
        c2.caption(f"{len(tickers)} tickers: {', '.join(tickers)}")

    # ── Filter thresholds (IC / IVR strategies only) ──────────────────────────
    params = dict(_DEFAULT_PARAMS.get(slug, {}))
    if slug in ("iron_condor_rules", "iron_condor_ai"):
        with st.expander("⚙️ Filter thresholds", expanded=True):
            p1, p2, p3, p4 = st.columns(4)
            params["ivr_min"]     = p1.slider("Min IVR",  0.05, 0.60, params["ivr_min"],     0.05,  key=kp("ss_ivr"))
            params["adx_max"]     = p2.slider("Max ADX",  15.0, 60.0, params["adx_max"],     1.0,   key=kp("ss_adx"))
            params["vix_max"]     = p3.slider("Max VIX",  25.0, 60.0, params["vix_max"],     1.0,   key=kp("ss_vmax"))
            params["atr_pct_max"] = p4.slider("Max ATR%", 0.01, 0.06, params["atr_pct_max"], 0.005, key=kp("ss_atr"),
                                               format="%.3f")
    elif slug == "ivr_credit_spread":
        with st.expander("⚙️ Filter thresholds", expanded=True):
            p1, p2 = st.columns(2)
            params["ivr_min"] = p1.slider("Min IVR", 0.20, 0.80, params.get("ivr_min", 0.40), 0.05, key=kp("ss_ivr"))
            params["vix_max"] = p2.slider("Max VIX", 25.0, 70.0, params.get("vix_max", 50.0), 1.0,  key=kp("ss_vmax"))

    # ── Speed vs accuracy toggle ───────────────────────────────────────────────
    fetch_ivr_history = st.toggle(
        "Full IVR (2 extra API calls/ticker — slower but accurate)",
        value=True, key=kp("ss_ivr_hist"),
    )

    # ── Scan button ───────────────────────────────────────────────────────────
    _cache_key = kp("ss_scan_cache")
    _has_cache = _cache_key in st.session_state
    scan_clicked = st.button(
        "🔍 Scan for Opportunities", type="primary", key=kp("ss_run"),
    )
    if _has_cache:
        if st.button("🗑 Clear results", key=kp("ss_clear")):
            st.session_state.pop(_cache_key, None)
            st.rerun()

    if scan_clicked:
        # Run pipeline and cache results
        vix_series, price_dfs, iv_all, all_errors = _run_data_pipeline(tickers, api_key, fetch_ivr_history)
        if vix_series is None:
            return
        st.session_state[_cache_key] = {
            "vix_series": vix_series,
            "price_dfs":  price_dfs,
            "iv_all":     iv_all,
            "all_errors": all_errors,
            "params":     params,
        }

    if _cache_key not in st.session_state:
        st.info("Select a universe and click **Scan for Opportunities**.")
        return

    # Restore cached scan
    _cached      = st.session_state[_cache_key]
    vix_series   = _cached["vix_series"]
    price_dfs    = _cached["price_dfs"]
    iv_all       = _cached["iv_all"]
    all_errors   = _cached["all_errors"]
    params       = _cached.get("params", params)   # use params from when scan ran

    # ── VIX context banner ────────────────────────────────────────────────────
    _render_vix_banner(vix_series, slug)

    # ── Strategy-specific scoring and display ──────────────────────────────────
    results, score_errors = [], []

    if slug in ("iron_condor_rules", "iron_condor_ai"):
        for ticker, price_df in price_dfs.items():
            m = _score_ic_rules(ticker, price_df, vix_series, iv_all.get(ticker, {}), params)
            if m is None:
                score_errors.append({"Ticker": ticker, "Issue": "Insufficient price data"})
            else:
                results.append(m)

        all_errors = (all_errors or []) + score_errors
        if not results:
            st.error("No results — check API key or universe.")
            if all_errors:
                st.dataframe(pd.DataFrame(all_errors), hide_index=True)
            return

        df = pd.DataFrame(results).sort_values("score", ascending=False)
        ready   = df[df["all_pass"]]
        partial = df[~df["all_pass"] & (df["n_pass"] >= 2)]
        blocked = df[df["n_pass"] < 2]

        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("✅ Trade-Ready",   len(ready))
        k2.metric("⚠️ Partial (2-3)", len(partial))
        k3.metric("❌ Blocked",       len(blocked))
        k4.metric("Scanned",          len(df))
        k5.metric("Avg IVR",          f"{df['IVR'].mean():.2f}")

        st.markdown("---")

        def _render_ic_section(section_df: pd.DataFrame, label: str):
            if section_df.empty:
                return
            st.markdown(f"#### {label}")
            st.dataframe(_fmt_ic(section_df, params), hide_index=True, width="stretch")
            for _, row in section_df.iterrows():
                ticker = row["Ticker"]
                with st.expander(f"📋 {ticker} — Trade Setup & Save", expanded=False):
                    _render_ic_trade_setup(ticker, row, api_key, params, kp, slug)

        if not ready.empty:
            _render_ic_section(ready, "✅ Trade-Ready — all 4 filters pass")
        else:
            st.info("No tickers pass all 4 filters. Try loosening thresholds or a different universe.")

        if not partial.empty:
            with st.expander(f"⚠️ Partial matches ({len(partial)} tickers)", expanded=True):
                _render_ic_section(partial, "⚠️ Partial matches")

        if not blocked.empty:
            with st.expander(f"❌ Blocked ({len(blocked)} tickers)"):
                st.dataframe(_fmt_ic(blocked, params, compact=True), hide_index=True, width="stretch")

        st.caption(
            f"Filters: IVR ≥ {params['ivr_min']:.2f} | "
            f"VIX {params['vix_min']:.0f}–{params['vix_max']:.0f} | "
            f"ADX ≤ {params['adx_max']:.0f} | ATR% ≤ {params['atr_pct_max']*100:.1f}% | "
            "IVR = per-ticker options-based (VIX fallback when options unavailable) | "
            "~Credit is a BS proxy, not live quotes"
        )

    elif slug == "vix_spike_fade":
        for ticker, price_df in price_dfs.items():
            m = _score_vix_spike_fade(ticker, price_df, vix_series, iv_all.get(ticker, {}))
            if m is None:
                score_errors.append({"Ticker": ticker, "Issue": "Insufficient price data"})
            else:
                results.append(m)

        all_errors = (all_errors or []) + score_errors
        if not results:
            st.error("No results.")
            return

        df = pd.DataFrame(results).sort_values("score", ascending=False)
        ready   = df[df["all_pass"]]
        partial = df[~df["all_pass"] & (df["n_pass"] >= 1)]

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("✅ Both filters pass",  len(ready))
        k2.metric("⚠️ Partial",            len(partial))
        k3.metric("Scanned",               len(df))
        current_vix = float(vix_series.iloc[-1])
        vix_20d_avg = _vix_20d_avg(vix_series)
        k4.metric("VIX / 20d avg",         f"{current_vix/max(vix_20d_avg,0.01):.2f}×")

        st.markdown("---")

        def _fmt_vix_spike(df: pd.DataFrame) -> pd.DataFrame:
            rows = []
            for _, r in df.iterrows():
                rows.append({
                    "Ticker":       r["Ticker"],
                    "Price":        f"${r['Price']:.2f}",
                    "VIX":          f"{r['VIX']:.1f}",
                    "VIX 20d avg":  f"{r['VIX 20d avg']:.1f}",
                    "VIX / 20d":    f"{r['VIX / 20d']:.2f}× {_ok(r['vix_spike_ok'])}",
                    "Above 200-MA": f"{'Yes' if r['above_ma200'] else 'No'} {_ok(r['above_ma200'])}",
                    "ATM IV":       _pct(r["ATM IV"]),
                    "HV20":         _pct(r["HV20"]),
                    "IVR":          _f2(r["IVR"]),
                    "ATR%":         f"{r['ATR%']:.2f}%",
                    "Score":        f"{r['score']:.0f}",
                })
            return pd.DataFrame(rows)

        if not ready.empty:
            st.markdown("#### ✅ Both filters pass — VIX spike + above 200-MA")
            st.dataframe(_fmt_vix_spike(ready), hide_index=True, width="stretch")
            for _, row in ready.iterrows():
                with st.expander(f"📋 {row['Ticker']} — Bull Call Spread setup", expanded=False):
                    _render_vix_spike_fade_setup(row["Ticker"], row, api_key, kp, slug)
        else:
            st.info(
                "No tickers pass both filters (VIX > 25 AND VIX > 1.3× 20d avg AND price above 200-MA). "
                "Partial matches below."
            )

        if not partial.empty:
            with st.expander(f"⚠️ Partial matches ({len(partial)} tickers)", expanded=True):
                st.dataframe(_fmt_vix_spike(partial), hide_index=True, width="stretch")
                for _, row in partial.iterrows():
                    with st.expander(f"📋 {row['Ticker']} — partial signal", expanded=False):
                        _render_vix_spike_fade_setup(row["Ticker"], row, api_key, kp, slug)

    elif slug == "vol_arbitrage":
        for ticker, price_df in price_dfs.items():
            m = _score_vol_arbitrage(ticker, price_df, vix_series, iv_all.get(ticker, {}))
            if m is None:
                score_errors.append({"Ticker": ticker, "Issue": "No options data or insufficient price data"})
            else:
                results.append(m)

        all_errors = (all_errors or []) + score_errors
        if not results:
            st.error("No results — vol arb requires real options IV data (no VIX fallback).")
            st.info("Try a universe with liquid options like 'ETF Core' or 'Mega Cap'.")
            if all_errors:
                st.dataframe(pd.DataFrame(all_errors), hide_index=True)
            return

        df = pd.DataFrame(results).sort_values("score", ascending=False)
        ready   = df[df["all_pass"]]
        partial = df[~df["all_pass"] & (df["n_pass"] >= 1)]

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("✅ VRP + IV/HV pass", len(ready))
        k2.metric("⚠️ Partial",          len(partial))
        k3.metric("Scanned",             len(df))
        avg_vrp = df["VRP"].mean()
        k4.metric("Avg VRP",             f"{avg_vrp*100:+.1f}%" if avg_vrp is not None else "—")

        def _fmt_vol_arb(df: pd.DataFrame) -> pd.DataFrame:
            rows = []
            for _, r in df.iterrows():
                rows.append({
                    "Ticker":  r["Ticker"],
                    "Price":   f"${r['Price']:.2f}",
                    "ATM IV":  _pct(r["ATM IV"]),
                    "HV20":    _pct(r["HV20"]),
                    "IV/HV":   f"{r['IV/HV']:.2f}× {_ok(bool(r.get('iv_hv_ok')))}",
                    "VRP":     f"{(r['VRP'] or 0)*100:+.1f}% {_ok(bool(r.get('vrp_ok')))}",
                    "IVR":     _f2(r["IVR"]),
                    "VIX":     f"{r['VIX']:.1f}",
                    "ATR%":    f"{r['ATR%']:.2f}%",
                    "Score":   f"{r['score']:.0f}",
                })
            return pd.DataFrame(rows)

        st.markdown("---")
        if not ready.empty:
            st.markdown("#### ✅ Vol Arb candidates — VRP > 0 + IV/HV > 1.1")
            st.dataframe(_fmt_vol_arb(ready), hide_index=True, width="stretch")
            for _, row in ready.iterrows():
                with st.expander(f"📋 {row['Ticker']} — Vol Arb setup", expanded=False):
                    _render_vol_arb_setup(row["Ticker"], row, api_key, kp, slug)
        else:
            st.info("No tickers pass both VRP > 0 and IV/HV > 1.1 filters.")

        if not partial.empty:
            with st.expander(f"⚠️ Partial matches ({len(partial)} tickers)", expanded=True):
                st.dataframe(_fmt_vol_arb(partial), hide_index=True, width="stretch")
                for _, row in partial.iterrows():
                    with st.expander(f"📋 {row['Ticker']} — Vol Arb setup (partial signal)", expanded=False):
                        _render_vol_arb_setup(row["Ticker"], row, api_key, kp, slug)

    elif slug == "ivr_credit_spread":
        for ticker, price_df in price_dfs.items():
            m = _score_ivr_credit_spread(ticker, price_df, vix_series, iv_all.get(ticker, {}), params)
            if m is None:
                score_errors.append({"Ticker": ticker, "Issue": "Insufficient price data"})
            else:
                results.append(m)

        all_errors = (all_errors or []) + score_errors
        if not results:
            st.error("No results.")
            return

        df = pd.DataFrame(results).sort_values("score", ascending=False)
        ready   = df[df["all_pass"]]
        partial = df[~df["all_pass"] & (df["n_pass"] >= 1)]

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("✅ IVR ≥ threshold", len(ready))
        k2.metric("⚠️ Partial",         len(partial))
        k3.metric("Scanned",            len(df))
        k4.metric(f"IVR threshold",     f"{params.get('ivr_min', 0.40):.0%}")

        def _fmt_ivr_cs(df: pd.DataFrame) -> pd.DataFrame:
            rows = []
            for _, r in df.iterrows():
                rows.append({
                    "Ticker":      r["Ticker"],
                    "Price":       f"${r['Price']:.2f}",
                    "ATM IV":      _pct(r["ATM IV"]),
                    "IVR":         f"{r['IVR']:.2f} {_ok(r['ivr_ok'])}",
                    "VRP":         f"{(r['VRP'] or 0)*100:+.1f}%",
                    "Trend":       r.get("Trend", "—"),
                    "Spread":      r.get("Spread Type", "—"),
                    "ADX":         f"{r['ADX']:.1f}",
                    "ATR%":        f"{r['ATR%']:.2f}%",
                    "Score":       f"{r['score']:.0f}",
                })
            return pd.DataFrame(rows)

        st.markdown("---")
        if not ready.empty:
            st.markdown(f"#### ✅ IVR Credit Spread candidates — IVR ≥ {params.get('ivr_min', 0.40):.0%}")
            st.dataframe(_fmt_ivr_cs(ready), hide_index=True, width="stretch")
            for _, row in ready.iterrows():
                with st.expander(f"📋 {row['Ticker']} — {row.get('Spread Type', 'Credit Spread')} setup", expanded=False):
                    _render_ivr_credit_spread_setup(row["Ticker"], row, api_key, kp, slug)
        else:
            st.info(f"No tickers pass IVR ≥ {params.get('ivr_min', 0.40):.0%} filter.")

        if not partial.empty:
            with st.expander(f"⚠️ Partial matches ({len(partial)} tickers)", expanded=True):
                st.dataframe(_fmt_ivr_cs(partial), hide_index=True, width="stretch")
                for _, row in partial.iterrows():
                    with st.expander(f"📋 {row['Ticker']} — {row.get('Spread Type', 'Credit Spread')} setup (partial signal)", expanded=False):
                        _render_ivr_credit_spread_setup(row["Ticker"], row, api_key, kp, slug)

    else:
        # Generic strategies: collect metrics, show signal tables
        for ticker, price_df in price_dfs.items():
            m = _score_generic(ticker, price_df, vix_series, iv_all.get(ticker, {}))
            if m is None:
                score_errors.append({"Ticker": ticker, "Issue": "Insufficient price data"})
            else:
                results.append(m)

        if not results:
            st.error("No results.")
            return

        # Sort by IV/HV descending where available
        def _sort_key(r):
            v = r.get("IV/HV")
            return -(v if v is not None else 0.0)
        results.sort(key=_sort_key)

        if slug == "iv_skew_momentum":
            _render_iv_skew_momentum(results)
        elif slug == "gamma_flip_breakout":
            _render_gamma_flip_breakout(results)
        elif slug == "earnings_iv_crush":
            _render_earnings_iv_crush(results)
        elif slug == "earnings_post_drift":
            _render_earnings_post_drift(results)
        elif slug == "vol_calendar_spread":
            _render_vol_calendar_spread(results, api_key, kp)
        elif slug == "short_squeeze_vol_expansion":
            _render_short_squeeze(results)
        elif slug == "oi_imbalance_put_fade":
            _render_oi_imbalance(results)
        elif slug == "vol_term_structure_regime":
            _render_vol_term_structure(results)
        else:
            st.markdown("#### Signal Table")
            _render_generic_signal_table(results, slug)

    # ── Errors summary ────────────────────────────────────────────────────────
    if all_errors:
        with st.expander(f"⚠️ {len(all_errors)} errors / skipped tickers"):
            st.dataframe(pd.DataFrame(all_errors), hide_index=True)
