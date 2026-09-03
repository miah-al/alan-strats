"""engine/screener.py — generic screener infrastructure.

Universes, price-only indicator helpers, OHLCV/VIX fetch and the options-chain
helpers shared by every strategy screener. Strategy-specific scorers live in the
strategy plugins and build on these."""

from __future__ import annotations

import logging
import math as _math
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
    """Rough two-leg OTM credit: spot × IV × √(45/252) × 0.38 (BS proxy)."""
    return price * iv * np.sqrt(45 / 252) * 0.38


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


# ── Calendar helpers ───────────────────────────────────────────────────────────

def _next_monthly_friday(days_out: int = 35) -> str:
    """Return the nearest Friday on or after (today + days_out) as YYYY-MM-DD."""
    import datetime as _dt
    target = _dt.date.today() + _dt.timedelta(days=days_out)
    # weekday(): Mon=0 … Fri=4 … Sun=6
    days_to_friday = (4 - target.weekday()) % 7
    return (target + _dt.timedelta(days=days_to_friday)).strftime("%Y-%m-%d")


# ── Spread builders (real strikes from a live chain) ──────────────────────────

def fetch_iron_condor_strikes(ticker: str, api_key: str, spot: float, adx_ok: bool = True,
                              target_delta: Optional[float] = None, wing_pct: float = 0.05,
                              min_credit: float = 0.05) -> tuple[dict | None, str | None]:
    """Pick a four-leg iron condor from the live chain: short strikes at the
    target delta (0.16, or 0.10 when the trend gate failed), wings `wing_pct`
    of spot further out. Returns (chain_dict, err). chain is None on failure."""
    if target_delta is None:
        target_delta = 0.16 if adx_ok else 0.10

    exp_chain, best_exp, dte_used, err = _get_options_chain(ticker, api_key, spot)
    if err:
        return None, err
    if exp_chain is None or exp_chain.empty:
        return None, "Polygon returned no contracts in the 30–60 DTE window"

    calls = exp_chain[exp_chain["type"].str.lower() == "call"].sort_values("strike")
    puts  = exp_chain[exp_chain["type"].str.lower() == "put"].sort_values("strike", ascending=False)

    short_call_k, short_call_mid = _find_strike(calls, "call", spot, target_delta)
    short_put_k,  short_put_mid  = _find_strike(puts,  "put",  spot, target_delta)
    if short_call_k is None or short_put_k is None:
        n_calls = len(calls); n_puts = len(puts)
        return None, f"Could not find {target_delta:.0%}-delta strikes (chain had {n_calls} calls, {n_puts} puts in window)"

    wing_w = round(spot * wing_pct, 0)

    # Long call wing must be ABOVE short call (further OTM).
    calls_above = calls[calls["strike"] > short_call_k]
    if calls_above.empty:
        return None, f"No call strikes above short call ${short_call_k:.0f} — chain too narrow"
    long_call_mid, long_call_k = _get_chain_mid(calls_above, short_call_k + wing_w,
                                                 exclude_strike=short_call_k)
    if long_call_k <= short_call_k:
        return None, f"Call wing ${long_call_k:.0f} ≤ short call ${short_call_k:.0f} — invalid spread"

    # Long put wing must be BELOW short put (further OTM).
    puts_below = puts[puts["strike"] < short_put_k]
    if puts_below.empty:
        return None, f"No put strikes below short put ${short_put_k:.0f} — chain too narrow"
    long_put_mid, long_put_k = _get_chain_mid(puts_below, short_put_k - wing_w,
                                               exclude_strike=short_put_k)
    if long_put_k >= short_put_k:
        return None, f"Put wing ${long_put_k:.0f} ≥ short put ${short_put_k:.0f} — invalid spread"

    def _m(v): return v if v is not None else 0.0

    net_credit    = _m(short_call_mid) + _m(short_put_mid) - _m(long_call_mid) - _m(long_put_mid)
    call_width    = long_call_k  - short_call_k
    put_width     = short_put_k  - long_put_k
    max_loss      = min(call_width, put_width) - net_credit

    # An iron condor MUST collect a credit. A non-positive net credit means the
    # wings priced richer than the shorts — only happens on illiquid/garbage
    # quotes — so reject rather than surface an un-tradeable (debit) "condor".
    if net_credit <= min_credit:
        return None, (f"Illiquid chain — net credit ${net_credit:.2f}/share is not positive "
                      f"(wings priced richer than shorts). Try a more liquid underlying.")

    return {
        "short_call_k":   short_call_k,
        "long_call_k":    long_call_k,
        "short_put_k":    short_put_k,
        "long_put_k":     long_put_k,
        "short_call_mid": _m(short_call_mid),
        "long_call_mid":  _m(long_call_mid),
        "short_put_mid":  _m(short_put_mid),
        "long_put_mid":   _m(long_put_mid),
        "net_credit":     net_credit,
        "max_loss":       max_loss,
        "best_exp":       best_exp,
        "dte_used":       dte_used,
        "target_delta":   target_delta,
    }, None


def fetch_put_spread_strikes(ticker: str, api_key: str, spot: float,
                             itm_pct: float = 0.05, wing_pct: float = 0.04) -> tuple[dict | None, str | None]:
    """Pick a two-leg put spread from the live chain:
    short put target spot × (1 - itm_pct), long put target short × (1 - wing_pct).
    Returns (chain_dict, err)."""
    exp_chain, best_exp, dte_used, err = _get_options_chain(ticker, api_key, spot)
    if err:
        return None, err
    if exp_chain is None or exp_chain.empty:
        return None, "No contracts in 15–45 DTE window"

    puts = exp_chain[exp_chain["type"].str.lower() == "put"].sort_values("strike", ascending=False)
    if puts.empty:
        return None, "No put contracts found"

    target_short = spot * (1.0 - itm_pct)
    target_long  = target_short * (1.0 - wing_pct)

    puts_sorted_short = puts.copy()
    puts_sorted_short["_dist"] = (puts_sorted_short["strike"] - target_short).abs()
    best_short = puts_sorted_short.nsmallest(1, "_dist")
    if best_short.empty:
        return None, "Could not find short put strike"
    short_put_k   = float(best_short["strike"].iloc[0])
    short_put_mid = float(best_short["mid"].iloc[0]) if not best_short["mid"].isna().iloc[0] else None

    puts_below = puts[puts["strike"] < short_put_k].copy()
    if puts_below.empty:
        return None, f"No put strikes below short put ${short_put_k:.0f}"
    long_put_mid, long_put_k = _get_chain_mid(puts_below, target_long, exclude_strike=short_put_k)

    if long_put_k >= short_put_k:
        return None, f"Long put ${long_put_k:.0f} ≥ short put ${short_put_k:.0f}"

    def _m(v): return v if v is not None else 0.0

    net_credit = _m(short_put_mid) - _m(long_put_mid)
    put_width  = short_put_k - long_put_k
    max_loss   = put_width - net_credit

    return {
        "short_put_k":   short_put_k,
        "long_put_k":    long_put_k,
        "short_put_mid": _m(short_put_mid),
        "long_put_mid":  _m(long_put_mid),
        "net_credit":    net_credit,
        "put_width":     put_width,
        "max_loss":      max_loss,
        "best_exp":      best_exp,
        "dte_used":      dte_used,
    }, None
