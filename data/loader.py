"""
Real market data loader — Polygon.io + FRED.

Polygon Pro plan budget per full training/backtest fetch:
  SPY daily bars  : 1 request
  VIX daily bars  : 1 request
  News (≤500)     : 1–2 requests
  ─────────────────────────────
  Total           : ~3–4 requests

2Y / 10Y Treasury rates come from FRED (free CSV, no key needed).
Results are cached to disk for 24 h to avoid repeat calls on refresh.
"""

import logging
import pickle
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import requests

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent.parent / ".data_cache"
CACHE_TTL_HOURS = 24


# ---------------------------------------------------------------------------
# Disk cache helpers
# ---------------------------------------------------------------------------

def _cache_path(key: str) -> Path:
    CACHE_DIR.mkdir(exist_ok=True)
    return CACHE_DIR / f"{key}.pkl"


def _load_cache(key: str):
    p = _cache_path(key)
    if p.exists():
        try:
            with open(p, "rb") as f:
                ts, data = pickle.load(f)
            if datetime.now() - ts < timedelta(hours=CACHE_TTL_HOURS) and data is not None:
                logger.debug(f"Cache hit: {key}")
                return data
        except Exception:
            pass
    return None


def _save_cache(key: str, data) -> None:
    try:
        with open(_cache_path(key), "wb") as f:
            pickle.dump((datetime.now(), data), f)
    except Exception as e:
        logger.warning(f"Cache write failed for {key}: {e}")


# ---------------------------------------------------------------------------
# FRED rates  (free, no API key)
# ---------------------------------------------------------------------------

def _fetch_fred_series(series_id: str, from_date: str, to_date: str) -> pd.DataFrame:
    """Download a FRED series as a daily close DataFrame."""
    key = f"fred_{series_id}_{from_date}_{to_date}"
    cached = _load_cache(key)
    if cached is not None:
        return cached

    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"FRED fetch failed for {series_id}: {e}")
        return pd.DataFrame(columns=["close"])

    df = pd.read_csv(StringIO(resp.text))
    # FRED CSV date column may be "DATE" or "date"
    date_col = next((c for c in df.columns if c.strip().upper() in ("DATE", "OBSERVATION_DATE")), None)
    if date_col is None:
        logger.error(f"No date column found in FRED CSV for {series_id}. Columns: {df.columns.tolist()}")
        return pd.DataFrame(columns=["close"])
    df[date_col] = pd.to_datetime(df[date_col])
    df = df.set_index(date_col)
    df.index = df.index.date
    df.index.name = "date"
    df.columns = ["close"]
    df["close"] = pd.to_numeric(df["close"], errors="coerce").dropna()
    df["close"] = df["close"] / 100  # FRED returns %, convert to decimal

    from_d = pd.to_datetime(from_date).date()
    to_d   = pd.to_datetime(to_date).date()
    df = df.loc[(df.index >= from_d) & (df.index <= to_d)].dropna()

    _save_cache(key, df)
    return df


def fetch_rates(from_date: str, to_date: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (rate_2y_df, rate_10y_df) from FRED DGS2 / DGS10."""
    rate2y  = _fetch_fred_series("DGS2",  from_date, to_date)
    rate10y = _fetch_fred_series("DGS10", from_date, to_date)
    return rate2y, rate10y


# FRED series ids for the full macro dataset
_MACRO_SERIES = {
    # Full yield curve (Treasury constant-maturity)
    "rate_3m":  "DGS3MO",
    "rate_6m":  "DGS6MO",
    "rate_1y":  "DGS1",
    "rate_2y":  "DGS2",
    "rate_5y":  "DGS5",
    "rate_10y": "DGS10",
    "rate_30y": "DGS30",
    # Overnight risk-free rate (BS pricing rate, LIBOR replacement)
    "sofr":     "SOFR",
    # Labour market — weekly initial jobless claims (most timely jobs indicator)
    "jobless_claims": "ICSA",
}


def fetch_macro(from_date: str, to_date: str) -> pd.DataFrame:
    """
    Fetch full macro dataset: yield curve (3M→30Y), SOFR, jobless claims.
    Returns a single DataFrame indexed by date, forward-filled to daily.

    FRED series used (all free, no key needed):
      DGS3MO  — 3-month Treasury yield
      DGS6MO  — 6-month Treasury yield
      DGS1    — 1-year  Treasury yield
      DGS2    — 2-year  Treasury yield
      DGS5    — 5-year  Treasury yield
      DGS10   — 10-year Treasury yield
      DGS30   — 30-year Treasury yield
      SOFR    — Secured Overnight Financing Rate (overnight risk-free)
      ICSA    — Initial Jobless Claims (weekly, in thousands)
    """
    key = f"macro_{from_date}_{to_date}"
    cached = _load_cache(key)
    if cached is not None:
        return cached

    frames = {}
    for col_name, series_id in _MACRO_SERIES.items():
        df = _fetch_fred_series(series_id, from_date, to_date)
        if not df.empty:
            frames[col_name] = df["close"]

    if not frames:
        return pd.DataFrame()

    macro = pd.DataFrame(frames)

    # Jobless claims are in thousands; normalize to millions for scale consistency
    if "jobless_claims" in macro.columns:
        macro["jobless_claims"] = macro["jobless_claims"] * 1000   # FRED: raw number

    # Forward-fill gaps (weekends, holidays, weekly/monthly releases)
    macro = macro.ffill().infer_objects(copy=False)

    _save_cache(key, macro)
    return macro


# ---------------------------------------------------------------------------
# Polygon helpers
# ---------------------------------------------------------------------------

def _fetch_polygon_aggs(client, ticker: str, from_date: str, to_date: str) -> pd.DataFrame:
    key = f"aggs_{ticker}_{from_date}_{to_date}"
    cached = _load_cache(key)
    if cached is not None:
        return cached

    logger.info(f"Polygon: fetching {ticker} bars {from_date}→{to_date}")
    df = client.get_aggregates(ticker, from_date, to_date)
    _save_cache(key, df)
    return df


def fetch_live_vol_surface(
    client,
    ticker: str,
    spot_price: float,
    min_dte: int = 7,
    max_dte: int = 180,
    step_pct: float = 0.05,
) -> "pd.DataFrame | None":
    """
    Fetch real IV surface from Polygon options chain, sampled at step_pct strike steps.

    Calls only, strike range ±30% of spot, DTE between min_dte and max_dte.
    Uses Polygon's implied_volatility field — no local BS computation needed.
    Returns DataFrame with columns: strike, dte, iv  (cached 2 h).
    """
    from datetime import date, timedelta

    today     = date.today()
    strike_lo = round(spot_price * 0.70, 2)
    strike_hi = round(spot_price * 1.30, 2)
    exp_from  = (today + timedelta(days=min_dte)).strftime("%Y-%m-%d")
    exp_to    = (today + timedelta(days=max_dte)).strftime("%Y-%m-%d")

    cache_key = f"volsurf_{ticker}_{today}_{int(spot_price)}_{min_dte}_{max_dte}"
    cached = _load_cache(cache_key)
    if cached is not None:
        return cached

    results = []
    url = f"/v3/snapshot/options/{ticker}"
    params = {
        "expiration_date.gte": exp_from,
        "expiration_date.lte": exp_to,
        "strike_price.gte":    strike_lo,
        "strike_price.lte":    strike_hi,
        "contract_type":       "call",
        "limit":               250,
    }
    while url:
        data = client._get(url, params)
        results.extend(data.get("results", []))
        next_url = (data.get("next_url") or "").replace(client.BASE, "")
        url      = next_url or None
        params   = {}

    # If empty (e.g. weekend / after-hours), retry without strike filter — wider net
    if not results:
        data = client._get(f"/v3/snapshot/options/{ticker}", {
            "expiration_date.gte": exp_from,
            "expiration_date.lte": exp_to,
            "contract_type": "call",
            "limit": 10,
        })
        if not data.get("results"):
            # Nothing at all — surface unavailable (market closed or plan restriction)
            raise ValueError(
                f"No options data from Polygon for {ticker}. "
                "This endpoint requires an Options plan. "
                "If markets are closed, data from the last session will be unavailable via snapshot."
            )
        # Wider results exist — relax strike range and retry
        params = {
            "expiration_date.gte": exp_from,
            "expiration_date.lte": exp_to,
            "contract_type": "call",
            "limit": 250,
        }
        url = f"/v3/snapshot/options/{ticker}"
        results = []
        while url:
            data = client._get(url, params)
            results.extend(data.get("results", []))
            next_url = (data.get("next_url") or "").replace(client.BASE, "")
            url    = next_url or None
            params = {}

    if not results:
        return None

    rows = []
    no_iv_count  = 0
    dte_miss     = 0
    for r in results:
        d  = r.get("details", {})
        iv = r.get("implied_volatility")
        strike = d.get("strike_price")
        exp    = d.get("expiration_date", "")
        if not strike or not exp:
            continue
        dte = (pd.to_datetime(exp).date() - today).days
        if dte < min_dte or dte > max_dte:
            dte_miss += 1
            continue
        if not iv or float(iv) < 0.01:
            no_iv_count += 1
            continue
        rows.append({"strike": float(strike), "dte": int(dte), "iv": float(iv)})

    if not rows:
        if no_iv_count > 0 and dte_miss == 0:
            raise ValueError(
                f"Polygon returned {no_iv_count} options for {ticker} but implied_volatility "
                "is null on all of them. This typically happens outside market hours — "
                "IV is only populated in live snapshots during trading sessions. "
                "Try again during market hours (9:30 AM – 4:00 PM ET, Mon–Fri)."
            )
        if dte_miss > 0 and no_iv_count == 0:
            raise ValueError(
                f"Options exist for {ticker} but none fall in the {min_dte}–{max_dte} DTE range. "
                "Try widening the DTE sliders."
            )
        raise ValueError(
            f"No usable options data for {ticker} "
            f"({no_iv_count} missing IV, {dte_miss} outside DTE range)."
        )

    df = pd.DataFrame(rows)
    df = df.groupby(["strike", "dte"])["iv"].median().reset_index()

    if df is not None and not df.empty:
        _save_cache(cache_key, df)
    return df


def _fetch_polygon_news(client, ticker: str, from_date: str, to_date: str,
                        limit: int = 500) -> pd.DataFrame:
    key = f"news_{ticker}_{from_date}_{to_date}"
    cached = _load_cache(key)
    if cached is not None:
        return cached

    logger.info(f"Polygon: fetching news for {ticker}")
    df = client.get_news(ticker, from_date, to_date, limit=limit)
    _save_cache(key, df)
    return df


# ---------------------------------------------------------------------------
# Options chain snapshot  (live — not cached)
# ---------------------------------------------------------------------------

def fetch_options_snapshot(client, ticker: str,
                           min_dte: int = 10, max_dte: int = 60) -> pd.DataFrame:
    """
    Fetch current options chain snapshot from Polygon.
    Filters to expirations between min_dte and max_dte.
    Returns DataFrame with columns: strike, type, expiration, dte,
      bid, ask, mid, iv, delta, gamma, theta, vega, open_interest, volume.
    """
    today = datetime.now().date()
    exp_from = (today + timedelta(days=min_dte)).strftime("%Y-%m-%d")
    exp_to   = (today + timedelta(days=max_dte)).strftime("%Y-%m-%d")

    results = []
    url = f"/v3/snapshot/options/{ticker}"
    params = {
        "expiration_date.gte": exp_from,
        "expiration_date.lte": exp_to,
        "limit": 250,
    }
    while url:
        data = client._get(url, params)
        results.extend(data.get("results", []))
        url = (data.get("next_url") or "").replace(client.BASE, "") or None
        params = {}

    if not results:
        return pd.DataFrame()

    rows = []
    for r in results:
        d  = r.get("details",    {})
        g  = r.get("greeks",     {})
        q  = r.get("last_quote", {})
        bid = q.get("bid", 0) or 0
        ask = q.get("ask", 0) or 0
        exp = d.get("expiration_date", "")
        dte = (pd.to_datetime(exp).date() - today).days if exp else None
        rows.append({
            "strike":        d.get("strike_price"),
            "type":          d.get("contract_type", "").lower(),   # "call" / "put"
            "expiration":    exp,
            "dte":           dte,
            "bid":           round(bid, 3),
            "ask":           round(ask, 3),
            "mid":           round((bid + ask) / 2, 3),
            "iv":            r.get("implied_volatility"),           # already computed by Polygon
            "delta":         g.get("delta"),
            "gamma":         g.get("gamma"),
            "theta":         g.get("theta"),
            "vega":          g.get("vega"),
            "open_interest": r.get("open_interest"),
            "volume":        r.get("day", {}).get("volume"),
        })
    return pd.DataFrame(rows).dropna(subset=["strike", "type"])


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def load_real_data(ticker: str = "SPY", n_days: int = 756,
                   api_key: Optional[str] = None) -> dict:
    """
    Fetch all data needed for build_feature_matrix from real sources.

    Returns dict with keys matching simulator output:
      spy, vix, rate2y, rate10y, news
    """
    from alan_trader.data.polygon_client import PolygonClient

    client = PolygonClient(api_key=api_key)

    to_date  = datetime.now().date()
    # Buffer: n_days trading days ≈ n_days × 1.45 calendar days
    from_date = to_date - timedelta(days=int(n_days * 1.5) + 30)
    from_str  = from_date.strftime("%Y-%m-%d")
    to_str    = to_date.strftime("%Y-%m-%d")

    spy    = _fetch_polygon_aggs(client, ticker, from_str, to_str)
    vix    = _fetch_polygon_aggs(client, "I:VIX", from_str, to_str)
    rate2y, rate10y = fetch_rates(from_str, to_str)
    macro  = fetch_macro(from_str, to_str)   # yield curve + SOFR + jobless claims
    news   = _fetch_polygon_news(client, ticker, from_str, to_str, limit=500)

    # Trim to the requested number of trading days
    spy = spy.tail(n_days) if len(spy) > n_days else spy

    if spy.empty:
        raise ValueError(f"No price data returned for {ticker}. Check API key and ticker symbol.")

    return {
        "spy":     spy,
        "vix":     vix,
        "rate2y":  rate2y,
        "rate10y": rate10y,
        "macro":   macro,
        "news":    news,
    }


def get_live_quote(client, ticker: str) -> dict:
    """Get latest price snapshot for a ticker."""
    try:
        snap = client.get_snapshot(ticker)
        day  = snap.get("day", {})
        prev = snap.get("prevDay", {})
        return {
            "price":   snap.get("lastTrade", {}).get("p") or day.get("c"),
            "open":    day.get("o"),
            "change":  day.get("c", 0) - prev.get("c", 0),
            "change_pct": (day.get("c", 1) / (prev.get("c", 1) or 1) - 1) * 100,
            "volume":  day.get("v"),
            "vwap":    day.get("vw"),
            "high":    day.get("h"),
            "low":     day.get("l"),
        }
    except Exception as e:
        logger.warning(f"Live quote failed for {ticker}: {e}")
        return {}
