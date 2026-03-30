"""
Per-ticker Implied Volatility metrics for Iron Condor screening.

Provides get_ticker_iv_metrics() which returns atm_iv, ivr, vrp, hv20,
iv_over_hv and the data source label for every ticker in the screener.

Design decisions
----------------
ATM IV
  Fetched from Polygon's /v3/snapshot/options/{ticker} snapshot with a tight
  strike filter (spot ± 5%) and a DTE window of 21-45 days.  The pre-computed
  `implied_volatility` field on each contract is used directly — it is derived
  from the bid/ask mid by Polygon and is more reliable than recomputing from
  stale last-sale prices.  The ATM IV is the arithmetic mean of the nearest
  in-the-money call IV and the nearest out-of-the-money put IV at the closest
  strike to spot.  Averaging put and call removes the put-skew directional bias
  in the single IV estimate.

IVR (IV Rank)
  True IVR requires a historical IV range.  Rather than 252 separate dated API
  calls per ticker, we fetch ONE historical snapshot from ~252 calendar days ago
  and ONE from ~126 days ago, giving three data points (past_252, past_126,
  today) from which we estimate a plausible 52-week IV range.  This costs 2
  extra API calls per ticker, is fast, and avoids the circular artifacts of
  VIX-proxy IVR.

  IVR = (IV_today - IV_low_est) / (IV_high_est - IV_low_est)

  where IV_low_est  = min(IV_today, IV_past_252, IV_past_126)
        IV_high_est = max(IV_today, IV_past_252, IV_past_126)

  Limitation: 3 points is a thin sample.  If all three are within a narrow
  band, IVR will be either 0 or 1 depending on where today lands —
  essentially noise.  The `ivr_confidence` field flags when the range is
  narrow (< 0.05 in decimal IV) so callers can decide how much to trust it.

HV20 (20-day historical / realized volatility)
  Close-to-close log-return annualized standard deviation over the most
  recent 20 trading days.  Computed from the 60-bar OHLCV DataFrame that the
  screener already fetches — zero extra API calls.

VRP (Variance Risk Premium)
  VRP = IV_today - HV20  (both on 0-1 decimal annualized scale).
  Positive VRP means implied vol exceeds recent realized vol — premium is rich,
  which is the fundamental rationale for selling Iron Condors.
  Note: using variance difference (IV² - HV²) is more theoretically correct
  because variance is additive, but the vol-difference form is more intuitive
  and the numerical difference is small for typical equity IVs.

IV/HV ratio
  iv_over_hv = IV_today / HV20.  Values > 1.3 indicate meaningfully rich
  premium relative to realized vol.  More stable than VRP for comparing across
  tickers with different absolute vol levels.

Fallback hierarchy (iv_source field)
  1. "options_chain_30dte"  — live ATM IV from 30±15 DTE options snapshot
  2. "options_chain_any_dte" — live ATM IV but no 21-45 DTE expiry available
                               (used whatever DTE was closest to 30)
  3. "no_options_data"      — Polygon returned no options for this ticker;
                               atm_iv is None and ivr/vrp are computed from
                               hv20 only (ivr will be None).

API call budget per ticker
  - 1 call: current options snapshot (narrow strike + DTE filter)
  - 1 call: historical snapshot 252 days ago (same filter)  [only if current succeeded]
  - 1 call: historical snapshot 126 days ago (same filter)  [only if current succeeded]
  - 0 calls: OHLCV already fetched by screener; passed in as price_df
  Total: 2-3 calls per ticker, well within Polygon Starter (5 calls/min) and
  above with higher tiers.
"""

from __future__ import annotations

import logging
import math
from datetime import date, timedelta
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_TRADING_DAYS_PER_YEAR = 252
_DTE_MIN = 21          # minimum DTE to consider for ATM IV
_DTE_MAX = 45          # maximum DTE to consider (Iron Condor target window)
_STRIKE_PCT = 0.05     # fetch strikes within ±5% of spot
_MIN_ATM_IV = 0.04     # 4% floor — below this the data is suspect (e.g. stale)
_NARROW_RANGE_THRESHOLD = 0.05  # IVR confidence warning if IV range < 5 points


# ── Core function ─────────────────────────────────────────────────────────────

def get_ticker_iv_metrics(
    ticker: str,
    api_key: str,
    price_df: Optional[pd.DataFrame] = None,
    spot: Optional[float] = None,
    fetch_ivr_history: bool = True,
) -> dict:
    """
    Compute per-ticker IV metrics for Iron Condor screening.

    Parameters
    ----------
    ticker : str
        Equity ticker symbol (e.g. "SPY").
    api_key : str
        Polygon.io API key.
    price_df : pd.DataFrame, optional
        OHLCV DataFrame already fetched by the screener (indexed by date,
        with a 'close' column).  If provided, HV20 is computed from it at
        zero extra API cost.  If None, HV20 will be None.
    spot : float, optional
        Current spot price for strike filtering.  If None, estimated from
        price_df.close.iloc[-1] or fetched as a fallback.
    fetch_ivr_history : bool
        If True (default), fetch 2 historical snapshots to estimate the
        52-week IV range for IVR.  Set False to save API calls when only
        atm_iv and vrp are needed.

    Returns
    -------
    dict with keys:
        atm_iv         : float | None  — current ATM IV, annualized, decimal
        ivr            : float | None  — IV Rank 0-1 (None if history unavailable)
        ivr_confidence : str           — "high" / "low" / "none"
        vrp            : float | None  — IV - HV20 (None if either is unavailable)
        iv_over_hv     : float | None  — IV / HV20 ratio
        hv20           : float | None  — 20-day realized vol, annualized decimal
        iv_source      : str           — provenance label
        atm_strike     : float | None  — the strike used for ATM IV
        dte_used       : int | None    — DTE of the expiration used
        error          : str | None    — human-readable error if data missing
    """
    result: dict = {
        "atm_iv":         None,
        "ivr":            None,
        "ivr_confidence": "none",
        "vrp":            None,
        "iv_over_hv":     None,
        "hv20":           None,
        "iv_source":      "no_options_data",
        "atm_strike":     None,
        "dte_used":       None,
        "error":          None,
    }

    # ── Step 1: Resolve spot price ────────────────────────────────────────────
    if spot is None and price_df is not None and not price_df.empty:
        spot = float(price_df["close"].iloc[-1])

    if spot is None or spot <= 0:
        result["error"] = "No spot price available — pass price_df or spot"
        return result

    # ── Step 2: Compute HV20 from price_df (zero extra API calls) ────────────
    hv20 = _compute_hv20(price_df)
    result["hv20"] = hv20

    # ── Step 3: Fetch current ATM IV from Polygon options snapshot ────────────
    try:
        from alan_trader.data.polygon_client import PolygonClient
        client = PolygonClient(api_key=api_key)
    except Exception as e:
        result["error"] = f"PolygonClient init failed: {e}"
        return result

    atm_iv, atm_strike, dte_used, iv_source = _fetch_atm_iv(
        client, ticker, spot, as_of=None
    )

    result["atm_iv"]    = atm_iv
    result["atm_strike"] = atm_strike
    result["dte_used"]   = dte_used
    result["iv_source"]  = iv_source

    # ── Step 4: Compute VRP if we have both IV and HV ─────────────────────────
    if atm_iv is not None and hv20 is not None and hv20 > 0:
        result["vrp"]       = round(atm_iv - hv20, 4)
        result["iv_over_hv"] = round(atm_iv / hv20, 3)

    # ── Step 5: Fetch historical IV to compute IVR ────────────────────────────
    if atm_iv is not None and fetch_ivr_history:
        ivr, ivr_confidence = _compute_ivr(
            client, ticker, spot, atm_iv
        )
        result["ivr"]            = ivr
        result["ivr_confidence"] = ivr_confidence

    return result


# ── ATM IV extraction ─────────────────────────────────────────────────────────

def _fetch_atm_iv(
    client,
    ticker: str,
    spot: float,
    as_of: Optional[str] = None,
) -> tuple[Optional[float], Optional[float], Optional[int], str]:
    """
    Fetch the ATM IV for `ticker` using Polygon's options snapshot.

    Returns (atm_iv, atm_strike, dte_used, iv_source).

    Strategy:
    1. Fetch options snapshot filtered to 21-45 DTE and strikes within ±5% of spot.
    2. Pick the expiration with DTE closest to 30 (the 30-day constant-maturity
       convention).
    3. Within that expiration, find the strike nearest to spot.
    4. Average the IV of the ATM call and ATM put at that strike (or the two
       nearest bracketing strikes if no exact ATM strike exists).
    5. If that fails (null IVs, empty chain), broaden DTE window to ±60 days
       and retry once.
    """
    strike_lo = round(spot * (1 - _STRIKE_PCT), 2)
    strike_hi = round(spot * (1 + _STRIKE_PCT), 2)

    today_ts = pd.Timestamp(as_of) if as_of else pd.Timestamp.today().normalize()
    exp_lo = (today_ts + pd.Timedelta(days=_DTE_MIN)).strftime("%Y-%m-%d")
    exp_hi = (today_ts + pd.Timedelta(days=_DTE_MAX)).strftime("%Y-%m-%d")

    try:
        chain = client.get_options_chain(
            underlying=ticker,
            snapshot_date=as_of,
            expiration_date_gte=exp_lo,
            expiration_date_lte=exp_hi,
            strike_price_gte=strike_lo,
            strike_price_lte=strike_hi,
        )
    except Exception as e:
        logger.warning(f"{ticker}: options snapshot failed: {e}")
        return None, None, None, "no_options_data"

    if chain.empty:
        # Retry with wider DTE window (no 21-45 DTE expiry available)
        exp_lo_wide = (today_ts + pd.Timedelta(days=7)).strftime("%Y-%m-%d")
        exp_hi_wide = (today_ts + pd.Timedelta(days=60)).strftime("%Y-%m-%d")
        try:
            chain = client.get_options_chain(
                underlying=ticker,
                snapshot_date=as_of,
                expiration_date_gte=exp_lo_wide,
                expiration_date_lte=exp_hi_wide,
                strike_price_gte=strike_lo,
                strike_price_lte=strike_hi,
            )
        except Exception:
            return None, None, None, "no_options_data"

        if chain.empty:
            return None, None, None, "no_options_data"
        iv_source_label = "options_chain_any_dte"
    else:
        iv_source_label = "options_chain_30dte"

    # Filter to rows that have a valid IV
    chain = chain.dropna(subset=["iv"])
    chain = chain[chain["iv"].astype(float) >= _MIN_ATM_IV]
    if chain.empty:
        return None, None, None, "no_options_data"

    # Convert types defensively
    chain = chain.copy()
    chain["iv"]     = pd.to_numeric(chain["iv"], errors="coerce")
    chain["strike"] = pd.to_numeric(chain["strike"], errors="coerce")
    chain["dte"]    = pd.to_numeric(chain["dte"], errors="coerce")
    chain = chain.dropna(subset=["iv", "strike", "dte"])

    # Pick the expiration closest to 30 DTE
    expirations = chain.groupby("expiration")["dte"].first()
    best_exp = expirations.sub(30).abs().idxmin()
    dte_used = int(expirations[best_exp])

    exp_chain = chain[chain["expiration"] == best_exp].copy()

    # Find ATM strike(s)
    atm_iv, atm_strike = _extract_atm_iv_from_expiry(exp_chain, spot)

    if atm_iv is None:
        return None, None, None, "no_options_data"

    return round(float(atm_iv), 4), atm_strike, dte_used, iv_source_label


def _extract_atm_iv_from_expiry(
    exp_chain: pd.DataFrame,
    spot: float,
) -> tuple[Optional[float], Optional[float]]:
    """
    From a single-expiration chain (with iv, strike, type columns),
    return (atm_iv, atm_strike).

    Method:
    - Find the unique strike nearest to spot.
    - Average the call IV and put IV at that strike.
    - If only one side has a valid IV, use that side alone.
    - If no IV at the nearest strike, try the next-nearest.
    """
    strikes = sorted(exp_chain["strike"].unique())
    if not strikes:
        return None, None

    for candidate_strike in sorted(strikes, key=lambda k: abs(k - spot)):
        row = exp_chain[exp_chain["strike"] == candidate_strike]

        call_rows = row[row["type"].str.lower() == "call"]["iv"].dropna()
        put_rows  = row[row["type"].str.lower() == "put"]["iv"].dropna()

        ivs = []
        if len(call_rows) > 0:
            iv_c = float(call_rows.iloc[0])
            if iv_c >= _MIN_ATM_IV:
                ivs.append(iv_c)
        if len(put_rows) > 0:
            iv_p = float(put_rows.iloc[0])
            if iv_p >= _MIN_ATM_IV:
                ivs.append(iv_p)

        if ivs:
            return float(np.mean(ivs)), float(candidate_strike)

    return None, None


# ── Historical IV for IVR ─────────────────────────────────────────────────────

def _compute_ivr(
    client,
    ticker: str,
    spot: float,
    atm_iv_today: float,
) -> tuple[Optional[float], str]:
    """
    Estimate IVR using two historical snapshots (252 and 126 days ago).

    Returns (ivr, confidence_label) where:
      ivr               : float 0-1, or None if history unavailable
      confidence_label  : "high" if IV range >= 0.05, "low" if narrower,
                          "none" if historical data unavailable
    """
    today = date.today()
    lookback_dates = [
        (today - timedelta(days=252)).isoformat(),
        (today - timedelta(days=126)).isoformat(),
    ]

    historical_ivs: list[float] = [atm_iv_today]

    for snap_date in lookback_dates:
        iv_hist, _, _, source = _fetch_atm_iv(client, ticker, spot, as_of=snap_date)
        if iv_hist is not None and iv_hist >= _MIN_ATM_IV:
            historical_ivs.append(iv_hist)
        # If a historical snapshot fails, skip it silently — partial data is
        # better than returning None for IVR entirely.

    if len(historical_ivs) < 2:
        # Only today's data point — cannot form a range
        return None, "none"

    iv_low  = min(historical_ivs)
    iv_high = max(historical_ivs)
    iv_range = iv_high - iv_low

    if iv_range < 1e-6:
        # Degenerate: all sampled IVs identical
        return 0.5, "low"

    ivr = (atm_iv_today - iv_low) / iv_range
    ivr = float(np.clip(ivr, 0.0, 1.0))

    confidence = "high" if iv_range >= _NARROW_RANGE_THRESHOLD else "low"

    return round(ivr, 3), confidence


# ── Realized volatility ───────────────────────────────────────────────────────

def _compute_hv20(price_df: Optional[pd.DataFrame], window: int = 20) -> Optional[float]:
    """
    Compute 20-day close-to-close annualized historical volatility.

    Uses log returns: HV = std(log(C_t / C_{t-1})) * sqrt(252)
    Requires at least (window + 1) bars.  Returns None if data insufficient.
    """
    if price_df is None or price_df.empty:
        return None
    if "close" not in price_df.columns:
        return None

    closes = price_df["close"].astype(float).dropna()
    if len(closes) < window + 1:
        return None

    log_returns = np.log(closes / closes.shift(1)).dropna()
    if len(log_returns) < window:
        return None

    # Use the most recent `window` log returns
    recent_returns = log_returns.iloc[-window:]
    hv = float(recent_returns.std(ddof=1) * math.sqrt(_TRADING_DAYS_PER_YEAR))

    if hv <= 0 or not math.isfinite(hv):
        return None

    return round(hv, 4)


# ── Batch screener helper ─────────────────────────────────────────────────────

def get_iv_metrics_batch(
    tickers: list[str],
    api_key: str,
    price_dfs: Optional[dict[str, pd.DataFrame]] = None,
    spots: Optional[dict[str, float]] = None,
    fetch_ivr_history: bool = True,
    on_progress=None,
) -> dict[str, dict]:
    """
    Run get_ticker_iv_metrics for a list of tickers.

    Parameters
    ----------
    tickers       : list of ticker symbols
    api_key       : Polygon API key
    price_dfs     : dict mapping ticker -> OHLCV DataFrame (optional)
    spots         : dict mapping ticker -> spot price (optional)
    fetch_ivr_history : passed through to get_ticker_iv_metrics
    on_progress   : optional callable(ticker, i, n) for progress reporting

    Returns
    -------
    dict mapping ticker -> iv_metrics_dict
    """
    results = {}
    n = len(tickers)

    for i, ticker in enumerate(tickers):
        if on_progress:
            try:
                on_progress(ticker, i, n)
            except Exception:
                pass

        pdfs = price_dfs or {}
        spts = spots or {}

        try:
            metrics = get_ticker_iv_metrics(
                ticker=ticker,
                api_key=api_key,
                price_df=pdfs.get(ticker),
                spot=spts.get(ticker),
                fetch_ivr_history=fetch_ivr_history,
            )
        except Exception as e:
            logger.warning(f"IV metrics failed for {ticker}: {e}")
            metrics = {
                "atm_iv": None, "ivr": None, "ivr_confidence": "none",
                "vrp": None, "iv_over_hv": None, "hv20": None,
                "iv_source": "error", "atm_strike": None,
                "dte_used": None, "error": str(e),
            }

        results[ticker] = metrics

    return results
