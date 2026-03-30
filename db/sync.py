"""
alan-strats  |  Data sync: Polygon -> SQL Server.
Handles backfill and incremental updates for all data types.
"""

import logging
import math
from datetime import date, timedelta
from typing import Callable, Optional

import pandas as pd

from alan_trader.db.client import (
    get_engine, ensure_ticker,
    upsert_price_bars, upsert_option_snapshots,
    upsert_vix_bars, upsert_macro_bars,
    get_price_coverage, get_option_coverage,
    get_last_sync_date, log_sync,
)
from alan_trader.data.polygon_client import PolygonClient

logger = logging.getLogger(__name__)

# Two years back from today — matches Polygon Options Starter plan
DEFAULT_START = date.today() - timedelta(days=730)


# ── Price Bars ────────────────────────────────────────────────────────────────

def sync_price_bars(
    symbol: str,
    api_key: str,
    from_date: date = DEFAULT_START,
    to_date:   date = None,
    progress_cb: Callable[[str], None] = None,
) -> dict:
    """Fetch daily OHLCV from Polygon and store in mkt.PriceBar."""
    to_date = to_date or date.today()
    engine  = get_engine()
    client  = PolygonClient(api_key=api_key)

    # Incremental: re-sync last date (delete + re-insert) then continue forward
    from sqlalchemy import text as _t
    last = get_last_sync_date(engine, "PriceBar", symbol)
    if last:
        from_date = last
        from alan_trader.db.client import get_ticker_id
        _tid = get_ticker_id(engine, symbol)
        if _tid:
            with engine.begin() as _conn:
                _conn.execute(_t("DELETE FROM mkt.PriceBar WHERE TickerId = :tid AND BarDate = :d"),
                              {"tid": _tid, "d": last})

    if from_date > to_date:
        return {"status": "up_to_date", "rows": 0}

    if progress_cb:
        progress_cb(f"Fetching {symbol} price bars {from_date} -> {to_date}...")

    try:
        df = client.get_aggregates(symbol, str(from_date), str(to_date))
        if df.empty:
            log_sync(engine, "PriceBar", to_date, 0, symbol)
            return {"status": "no_data", "rows": 0,
                    "detail": f"Polygon returned 0 bars for {symbol} ({from_date} → {to_date})"}

        df = df.reset_index()  # date becomes a column
        if progress_cb:
            progress_cb(f"Fetched {len(df):,} rows — writing to database...")

        def _upsert_cb(done, total, current_date=None):
            if progress_cb:
                date_str = f"  •  {current_date}" if current_date else ""
                progress_cb(f"Inserting price bars: {done:,} / {total:,} rows{date_str}")

        rows = upsert_price_bars(engine, symbol, df, progress_cb=_upsert_cb)
        log_sync(engine, "PriceBar", to_date, rows, symbol)
        return {"status": "ok", "rows": rows}
    except Exception as e:
        log_sync(engine, "PriceBar", to_date, 0, symbol, error=str(e))
        raise


# ── Black-Scholes mid-price estimator ────────────────────────────────────────

def _bs_mid(S: float, K: float, T: float, r: float, iv: float, opt: str) -> float:
    """Return Black-Scholes theoretical mid price. opt = 'call' or 'put'."""
    if T <= 0 or iv <= 0 or S <= 0 or K <= 0:
        return float("nan")
    try:
        d1 = (math.log(S / K) + (r + 0.5 * iv * iv) * T) / (iv * math.sqrt(T))
        d2 = d1 - iv * math.sqrt(T)
        try:
            from scipy.stats import norm as _norm
            cdf = _norm.cdf
        except ImportError:
            cdf = lambda x: 0.5 * (1 + math.erf(x / math.sqrt(2)))
        if opt == "call":
            return S * cdf(d1) - K * math.exp(-r * T) * cdf(d2)
        else:
            return K * math.exp(-r * T) * cdf(-d2) - S * cdf(-d1)
    except Exception:
        return float("nan")


def bs_price_chain(df: pd.DataFrame, S: float, r: float = 0.045) -> pd.DataFrame:
    """
    Recalculate bid/ask/mid for every row using Black-Scholes with the given
    spot price S and stored IV.  Overwrites existing bid/ask — used at load
    time so each snapshot date gets historically-correct option prices even
    though Polygon stores current prices for all dates.
    """
    if df.empty:
        return df
    df = df.copy()
    for col in ("iv", "dte", "strike", "type"):
        if col not in df.columns:
            return df

    for idx in df.index:
        iv  = df.at[idx, "iv"]
        K   = float(df.at[idx, "strike"])
        dte = float(df.at[idx, "dte"] or 0)
        opt = str(df.at[idx, "type"] or "").lower()
        if not iv or iv != iv or float(iv) <= 0 or float(iv) > 3.0:
            continue
        if opt not in ("call", "put") or dte <= 0:
            continue
        T   = dte / 252.0
        mid = _bs_mid(S, K, T, r, float(iv), opt)
        if math.isnan(mid) or mid <= 0:
            continue
        spread_pct = 0.04 if mid < 1 else 0.02
        spread = max(0.01, mid * spread_pct)
        df.at[idx, "bid"] = round(mid - spread / 2, 4)
        df.at[idx, "ask"] = round(mid + spread / 2, 4)
    return df


# Mapping from treasury ticker symbol → approximate DTE (trading days)
_TENOR_DTE = {
    "rate_3m":  63,
    "rate_6m":  126,
    "rate_1y":  252,
    "rate_2y":  504,
    "rate_5y":  1260,
    "rate_10y": 2520,
    "rate_30y": 7560,
}


def _term_rate(dte: float, yield_curve: dict) -> float:
    """
    Interpolate risk-free rate for a given DTE (trading days) from the yield curve.
    yield_curve: {dte_trading_days: rate_decimal}
    Falls back to 0.045 if curve is empty.
    """
    if not yield_curve:
        return 0.045
    tenors = sorted(yield_curve.keys())
    vals   = [yield_curve[t] for t in tenors]
    if len(tenors) == 1:
        return vals[0]
    import numpy as _np
    return float(_np.interp(dte, tenors, vals))


def _compute_iv_from_prices(df: pd.DataFrame, S: float,
                             yield_curve: dict = None) -> pd.DataFrame:
    """
    Compute real historical IV by inverting BS on the actual option close price.

    Polygon's `implied_volatility` field is frozen — it reflects today's IV regardless
    of the snapshot date.  But `day.close` (captured in bid/ask via mid_proxy in
    get_options_chain) is the actual option price on that historical date.
    Inverting BS on that price gives the true historical implied volatility.

    Only overwrites rows that have valid bid/ask (i.e. rows where historical price
    data was available).  Rows with no price data keep the Polygon IV as fallback.
    """
    try:
        from scipy.optimize import brentq as _brentq
    except ImportError:
        return df

    if df.empty or S <= 0:
        return df

    df = df.copy()
    for idx in df.index:
        bid = df.at[idx, "bid"]
        ask = df.at[idx, "ask"]
        # Only process rows that have a real historical price
        if not (bid == bid and ask == ask and float(bid) > 0 and float(ask) > 0):
            continue
        mid = (float(bid) + float(ask)) / 2
        K   = float(df.at[idx, "strike"] or 0)
        dte = float(df.at[idx, "dte"]    or 0)
        opt = str(df.at[idx, "type"]     or "").lower()
        if K <= 0 or dte <= 0 or opt not in ("call", "put"):
            continue
        T = dte / 252.0
        r = _term_rate(dte, yield_curve or {})
        # Skip if price is at or below intrinsic (can't solve IV)
        intrinsic = max(0.0, S - K) if opt == "call" else max(0.0, K - S)
        if mid <= intrinsic * 1.001:
            continue
        try:
            iv = _brentq(
                lambda v: _bs_mid(S, K, T, r, v, opt) - mid,
                1e-4, 10.0, xtol=1e-5, maxiter=50,
            )
            if 0.01 <= iv <= 5.0:  # sanity: 1% – 500%
                df.at[idx, "iv"] = round(float(iv), 6)
        except (ValueError, RuntimeError):
            pass  # keep Polygon IV as fallback if solver fails
    return df


def _fill_bid_ask_from_iv(df: pd.DataFrame, S: float,
                           yield_curve: dict = None) -> pd.DataFrame:
    """
    For rows where bid/ask are NaN but ImpliedVol is available, compute
    Black-Scholes theoretical mid using a term-matched risk-free rate and
    estimate a bid/ask spread around it.
    yield_curve: {dte_trading_days: rate_decimal} — if None, falls back to 4.5%.
    """
    if df.empty:
        return df
    df = df.copy()
    for col in ("bid", "ask", "iv", "dte", "strike", "type"):
        if col not in df.columns:
            return df  # can't reconstruct without these

    needs_fill = df["bid"].isna() & df["ask"].isna() & df["iv"].notna() & (df["iv"] > 0)
    if not needs_fill.any():
        return df

    for idx in df.index[needs_fill]:
        iv  = float(df.at[idx, "iv"])
        K   = float(df.at[idx, "strike"])
        dte = float(df.at[idx, "dte"] or 30)
        opt = str(df.at[idx, "type"] or "").lower()
        if opt not in ("call", "put") or iv > 3.0 or dte <= 0:
            continue
        T   = dte / 252.0
        r   = _term_rate(dte, yield_curve or {})
        mid = _bs_mid(S, K, T, r, iv, opt)
        if math.isnan(mid) or mid <= 0:
            continue
        spread_pct = 0.04 if mid < 1 else 0.02
        spread = max(0.01, mid * spread_pct)
        df.at[idx, "bid"] = round(mid - spread / 2, 4)
        df.at[idx, "ask"] = round(mid + spread / 2, 4)
    return df


# ── Option Snapshots ──────────────────────────────────────────────────────────

def sync_option_snapshots(
    symbol: str,
    api_key: str,
    from_date: date = DEFAULT_START,
    to_date:   date = None,
    dte_min:   int  = 7,
    dte_max:   int  = 90,
    spot_range_pct: float = 0.25,   # fetch strikes within ±25% of spot
    progress_cb: Callable[[str, int, int, int], None] = None,
) -> dict:
    """
    Build a real historical IV surface from per-contract daily OHLC data.

    Unlike the snapshot endpoint (which always returns today's chain with fake
    historical dates), this approach:
      1. Queries reference/options/contracts with expired=true to get ALL
         contracts that existed in the target date range.
      2. For each contract, fetches daily OHLC via the aggregates endpoint —
         actual prices on each day it traded.
      3. Reconstructs bid/ask from the closing price and computes real historical
         IV by inverting BS against the actual option price and underlying spot.
      4. Stores into mkt.OptionSnapshot with the real trade date as SnapshotDate.

    This is the only way to get genuine historical IV on the Polygon Starter plan.
    """
    to_date = to_date or date.today() - timedelta(days=1)
    engine  = get_engine()
    client  = PolygonClient(api_key=api_key)

    # Get spot price series for the underlying (already in DB)
    with engine.connect() as conn:
        from sqlalchemy import text
        spot_rows = conn.execute(text("""
            SELECT pb.BarDate, pb.[Close]
            FROM   mkt.PriceBar pb
            JOIN   mkt.Ticker   t ON t.TickerId = pb.TickerId
            WHERE  t.Symbol = :sym
              AND  pb.BarDate BETWEEN :from_d AND :to_d
            ORDER  BY pb.BarDate
        """), {"sym": symbol, "from_d": from_date, "to_d": to_date}).fetchall()
    if not spot_rows:
        return {"status": "error", "message": f"No price bars for {symbol} — sync price bars first."}
    spot_series = {r[0]: float(r[1]) for r in spot_rows}
    spot_dates  = sorted(spot_series.keys())

    # Rough ATM range across the full period
    avg_spot    = sum(spot_series.values()) / len(spot_series)
    strike_lo   = round(avg_spot * (1 - spot_range_pct), 2)
    strike_hi   = round(avg_spot * (1 + spot_range_pct), 2)

    if progress_cb:
        progress_cb(f"Fetching contract list for {symbol}...", 0, 0, 0)

    # Step 1: enumerate all contracts in the date range (including expired)
    all_contracts = []
    for contract_type in ("call", "put"):
        url = "/v3/reference/options/contracts"
        params = {
            "underlying_ticker":   symbol,
            "contract_type":       contract_type,
            "expiration_date.gte": str(from_date + timedelta(days=dte_min)),
            "expiration_date.lte": str(to_date   + timedelta(days=dte_max)),
            "strike_price.gte":    strike_lo,
            "strike_price.lte":    strike_hi,
            "expired":             "true",
            "limit":               1000,
        }
        while url:
            data = client._get(url, params)
            all_contracts.extend(data.get("results", []))
            url = (data.get("next_url") or "").replace(client.BASE, "") or None
            params = {}

    if not all_contracts:
        return {"status": "error", "message": "No contracts found for given parameters."}

    if progress_cb:
        progress_cb(f"Found {len(all_contracts)} contracts — fetching daily OHLC...", 0, len(all_contracts), 0)

    # Build yield curve helper
    def _get_rate(snap_d):
        with engine.connect() as _c:
            from sqlalchemy import text as _t
            rows = _c.execute(_t("""
                SELECT t.Symbol, pb.[Close]
                FROM   mkt.PriceBar pb
                JOIN   mkt.Ticker   t ON t.TickerId = pb.TickerId
                WHERE  t.Symbol IN ('rate_3m','rate_6m','rate_1y','rate_2y',
                                    'rate_5y','rate_10y','rate_30y')
                  AND  pb.BarDate = (
                        SELECT MAX(pb2.BarDate) FROM mkt.PriceBar pb2
                        JOIN   mkt.Ticker t2 ON t2.TickerId = pb2.TickerId
                        WHERE  t2.Symbol = t.Symbol AND pb2.BarDate <= :d)
            """), {"d": snap_d}).fetchall()
        return {_TENOR_DTE[r[0]]: float(r[1]) / 100 for r in rows if r[1] is not None}

    # Step 2: for each contract, fetch daily OHLC and build per-date chain rows
    # Accumulate rows by snapshot date for batch upsert
    rows_by_date: dict[date, list[dict]] = {}
    total_rows   = 0
    errors       = []

    from scipy.optimize import brentq as _brentq

    for i, contract in enumerate(all_contracts):
        ticker     = contract["ticker"]
        K          = float(contract["strike_price"])
        exp_str    = contract["expiration_date"]
        opt_type   = contract["contract_type"]   # "call" or "put"
        exp_date   = date.fromisoformat(exp_str)

        if progress_cb:
            progress_cb(f"[{i+1}/{len(all_contracts)}] {ticker}", i + 1, len(all_contracts), total_rows)

        try:
            bars = client.get_aggregates(ticker, str(from_date), str(to_date))
        except Exception as e:
            errors.append(f"{ticker}: {e}")
            continue

        if bars.empty:
            continue

        for bar_date, row in bars.iterrows():
            if not isinstance(bar_date, date):
                bar_date = bar_date.date()
            if bar_date < from_date or bar_date > to_date:
                continue

            S = spot_series.get(bar_date)
            if not S:
                # find nearest spot
                nearest = min(spot_dates, key=lambda d: abs((d - bar_date).days))
                if abs((nearest - bar_date).days) > 5:
                    continue
                S = spot_series[nearest]

            close_price = float(row.get("close") or 0)
            if close_price <= 0:
                continue

            dte = (exp_date - bar_date).days
            if not (dte_min <= dte <= dte_max):
                continue

            T = dte / 252.0
            yc = _get_rate(bar_date)
            r  = _term_rate(dte, yc)

            # Compute real historical IV from actual option close price
            intrinsic = max(0.0, S - K) if opt_type == "call" else max(0.0, K - S)
            iv = None
            if close_price > intrinsic * 1.001:
                try:
                    iv = _brentq(
                        lambda v: _bs_mid(S, K, T, r, v, opt_type) - close_price,
                        1e-4, 10.0, xtol=1e-5, maxiter=50,
                    )
                    if not (0.01 <= iv <= 5.0):
                        iv = None
                except (ValueError, RuntimeError):
                    iv = None

            if iv is None:
                continue

            spread = max(0.01, close_price * (0.04 if close_price < 1 else 0.02))
            rows_by_date.setdefault(bar_date, []).append({
                "expiration":    exp_str,
                "type":          opt_type,
                "strike":        K,
                "bid":           round(close_price - spread / 2, 4),
                "ask":           round(close_price + spread / 2, 4),
                "iv":            round(iv, 6),
                "delta":         None,
                "gamma":         None,
                "theta":         None,
                "vega":          None,
                "open_interest": None,
                "volume":        int(row.get("volume") or 0),
            })

    # Step 3: upsert each date's rows into mkt.OptionSnapshot
    for snap_date, date_rows in sorted(rows_by_date.items()):
        try:
            df = pd.DataFrame(date_rows)
            n  = upsert_option_snapshots(engine, symbol, snap_date, df)
            total_rows += n
        except Exception as e:
            errors.append(f"{snap_date}: {e}")

    log_sync(engine, "OptionSnapshot", to_date, total_rows, symbol,
             error="; ".join(errors) if errors else None)

    return {
        "status":    "ok" if not errors else "partial",
        "rows":      total_rows,
        "contracts": len(all_contracts),
        "dates":     len(rows_by_date),
        "errors":    errors[:10],
    }


# ── VIX Bars ──────────────────────────────────────────────────────────────────

def sync_vix_bars(
    from_date: date = DEFAULT_START,
    to_date:   date = None,
    progress_cb: Callable[[str], None] = None,
) -> dict:
    """Fetch VIX daily bars from CBOE free CSV (no API key needed)."""
    import requests
    from io import StringIO

    to_date = to_date or date.today()
    engine  = get_engine()

    from sqlalchemy import text as _t
    last = get_last_sync_date(engine, "VixBar")
    if last:
        from_date = last
        with engine.begin() as _conn:
            _conn.execute(_t("DELETE FROM mkt.VixBar WHERE BarDate = :d"), {"d": last})

    if from_date > to_date:
        return {"status": "up_to_date", "rows": 0}

    if progress_cb:
        progress_cb("Fetching VIX history from CBOE...")

    try:
        url  = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()

        df = pd.read_csv(StringIO(resp.text))
        df.columns = [c.strip().lower() for c in df.columns]
        df["date"]  = pd.to_datetime(df["date"]).dt.date
        df = df.rename(columns={"vix open": "open", "vix high": "high",
                                 "vix low": "low",  "vix close": "close"})
        # CBOE CSV uses plain OPEN/HIGH/LOW/CLOSE
        for old, new in [("open","open"),("high","high"),("low","low"),("close","close")]:
            if old not in df.columns:
                df[old] = df.get(new)

        df = df[["date","open","high","low","close"]].dropna()
        df = df[(df["date"] >= from_date) & (df["date"] <= to_date)]

        if df.empty:
            return {"status": "no_data", "rows": 0}

        if progress_cb:
            progress_cb(f"Fetched {len(df):,} VIX rows — writing to database...")

        def _upsert_cb(done, total, current_date=None):
            if progress_cb:
                date_str = f"  •  {current_date}" if current_date else ""
                progress_cb(f"Inserting VIX bars: {done:,} / {total:,} rows{date_str}")

        rows = upsert_vix_bars(engine, df, progress_cb=_upsert_cb)
        log_sync(engine, "VixBar", to_date, rows)
        return {"status": "ok", "rows": rows}
    except Exception as e:
        log_sync(engine, "VixBar", to_date, 0, error=str(e))
        raise


# ── Macro Bars (FRED — free) ──────────────────────────────────────────────────

def sync_macro_bars(
    from_date: date = DEFAULT_START,
    to_date:   date = None,
    progress_cb: Callable[[str], None] = None,
) -> dict:
    """Fetch full macro dataset from FRED and store in mkt.MacroBar."""
    to_date = to_date or date.today()
    engine  = get_engine()

    from sqlalchemy import text as _t
    last = get_last_sync_date(engine, "MacroBar")
    if last:
        # Verify data actually exists — SyncLog can be ahead of actual data
        with engine.connect() as conn:
            count = conn.execute(_t("SELECT COUNT(*) FROM mkt.MacroBar")).scalar()
        if count == 0:
            last = None  # Force full resync
        else:
            from_date = last
            with engine.begin() as _conn:
                _conn.execute(_t("DELETE FROM mkt.MacroBar WHERE BarDate = :d"), {"d": last})

    if from_date > to_date:
        return {"status": "up_to_date", "rows": 0}

    if progress_cb:
        progress_cb(f"Fetching macro data from FRED {from_date} -> {to_date}...")

    try:
        from alan_trader.data.loader import fetch_macro
        macro = fetch_macro(str(from_date), str(to_date))
        if macro.empty:
            return {"status": "no_data", "rows": 0}
        macro = macro.reset_index()
        if progress_cb:
            progress_cb(f"Fetched {len(macro):,} macro rows — writing to database...")

        def _upsert_cb(done, total, current_date=None):
            if progress_cb:
                date_str = f"  •  {current_date}" if current_date else ""
                progress_cb(f"Inserting macro bars: {done:,} / {total:,} rows{date_str}")

        rows = upsert_macro_bars(engine, macro, progress_cb=_upsert_cb)
        log_sync(engine, "MacroBar", to_date, rows)
        return {"status": "ok", "rows": rows}
    except Exception as e:
        log_sync(engine, "MacroBar", to_date, 0, error=str(e))
        raise


# ── News (Polygon) ────────────────────────────────────────────────────────────

def sync_news(
    symbol: str,
    api_key: str,
    from_date: date = DEFAULT_START,
    to_date:   date = None,
    progress_cb: Callable[[str], None] = None,
) -> dict:
    """Fetch news articles from Polygon and store in mkt.News."""
    to_date = to_date or date.today()
    engine  = get_engine()
    client  = PolygonClient(api_key=api_key)

    from sqlalchemy import text as _t
    last = get_last_sync_date(engine, "News", symbol)
    if last:
        from_date = last
        from alan_trader.db.client import get_ticker_id as _gtid
        _tid = _gtid(engine, symbol)
        if _tid:
            with engine.begin() as _conn:
                _conn.execute(_t("DELETE FROM mkt.News WHERE TickerId = :tid AND PublishedDate = :d"),
                              {"tid": _tid, "d": last})

    if from_date > to_date:
        return {"status": "up_to_date", "rows": 0}

    if progress_cb:
        progress_cb(f"Fetching {symbol} news {from_date} -> {to_date}...")

    try:
        df = client.get_news(symbol, str(from_date), str(to_date))
        if df.empty:
            log_sync(engine, "News", to_date, 0, symbol)
            return {"status": "no_data", "rows": 0}
        from alan_trader.db.client import upsert_news
        if progress_cb:
            progress_cb(f"Fetched {len(df):,} articles — scoring sentiment and writing to database...")

        def _upsert_cb(done, total):
            if progress_cb:
                progress_cb(f"Inserting news: {done:,} / {total:,} articles…")

        rows = upsert_news(engine, symbol, df, progress_cb=_upsert_cb)
        log_sync(engine, "News", to_date, rows, symbol)
        return {"status": "ok", "rows": rows}
    except Exception as e:
        log_sync(engine, "News", to_date, 0, symbol, error=str(e))
        raise


# ── Dividends (Polygon) ───────────────────────────────────────────────────────

def sync_dividends(
    symbol: str,
    api_key: str,
    from_date: date = DEFAULT_START,
    to_date:   date = None,
    progress_cb: Callable[[str], None] = None,
) -> dict:
    """Fetch cash dividend history from Polygon and store in mkt.Dividend."""
    import requests
    from sqlalchemy import text as _t
    to_date = to_date or date.today()
    engine  = get_engine()

    last = get_last_sync_date(engine, "Dividend", symbol)
    if last:
        from_date = last

    if from_date > to_date:
        return {"status": "up_to_date", "rows": 0}

    if progress_cb:
        progress_cb(f"Fetching {symbol} dividends from Polygon…")

    try:
        resp = requests.get(
            "https://api.polygon.io/v3/reference/dividends",
            params={"ticker": symbol, "ex_dividend_date.gte": str(from_date),
                    "ex_dividend_date.lte": str(to_date), "limit": 1000, "apiKey": api_key},
            timeout=30,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
    except Exception as e:
        raise RuntimeError(f"Polygon dividends error: {e}")

    if not results:
        log_sync(engine, "Dividend", to_date, 0, symbol)
        return {"status": "no_data", "rows": 0}

    tid = ensure_ticker(engine, symbol)
    inserted = 0
    with engine.begin() as conn:
        for r in results:
            res = conn.execute(_t("""
                IF NOT EXISTS (SELECT 1 FROM mkt.Dividend WHERE TickerId=:tid AND ExDate=:ex_date)
                INSERT INTO mkt.Dividend (TickerId,ExDate,PayDate,DeclaredDate,RecordDate,
                                          CashAmount,DividendType,Frequency)
                VALUES (:tid,:ex_date,:pay_date,:declared,:record,:cash,:dtype,:freq)
            """), {"tid": tid, "ex_date": r.get("ex_dividend_date"),
                   "pay_date": r.get("pay_date"), "declared": r.get("declaration_date"),
                   "record": r.get("record_date"), "cash": r.get("cash_amount"),
                   "dtype": r.get("dividend_type"), "freq": r.get("frequency")})
            inserted += res.rowcount

    if progress_cb:
        progress_cb(f"Done — {inserted} dividend rows inserted.")
    log_sync(engine, "Dividend", to_date, inserted, symbol)
    return {"status": "ok", "rows": inserted}


# ── Earnings (Polygon) ────────────────────────────────────────────────────────

def sync_earnings(
    symbol: str,
    api_key: str,
    from_date: date = DEFAULT_START,
    to_date:   date = None,
    progress_cb: Callable[[str], None] = None,
) -> dict:
    """Fetch quarterly financials from Polygon and store in mkt.Earnings."""
    import requests
    from sqlalchemy import text as _t
    to_date = to_date or date.today()
    engine  = get_engine()

    last = get_last_sync_date(engine, "Earnings", symbol)
    if last:
        from_date = last

    if progress_cb:
        progress_cb(f"Fetching {symbol} earnings from Polygon…")

    results = []
    url = "https://api.polygon.io/vX/reference/financials"
    params = {"ticker": symbol, "filing_date.gte": str(from_date),
              "filing_date.lte": str(to_date), "timeframe": "quarterly",
              "limit": 100, "apiKey": api_key}
    try:
        while url:
            resp = requests.get(url if url.startswith("http") else f"https://api.polygon.io{url}",
                                params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            results.extend(data.get("results", []))
            next_url = data.get("next_url", "")
            url = next_url if next_url else None
            params = {"apiKey": api_key} if url else {}
    except Exception as e:
        raise RuntimeError(f"Polygon earnings error: {e}")

    if not results:
        log_sync(engine, "Earnings", to_date, 0, symbol)
        return {"status": "no_data", "rows": 0}

    tid = ensure_ticker(engine, symbol)
    inserted = 0
    with engine.begin() as conn:
        for r in results:
            fin = r.get("financials", {})
            inc = fin.get("income_statement", {})
            period = r.get("end_date") or r.get("period_of_report_date")
            if not period:
                continue
            res = conn.execute(_t("""
                IF NOT EXISTS (SELECT 1 FROM mkt.Earnings WHERE TickerId=:tid AND PeriodOfReport=:period)
                INSERT INTO mkt.Earnings (TickerId,PeriodOfReport,FiscalYear,FiscalPeriod,
                                          RevenueUSD,NetIncomeUSD,EpsBasic,FiledDate)
                VALUES (:tid,:period,:fy,:fp,:rev,:net,:eps,:filed)
            """), {"tid": tid, "period": period,
                   "fy": r.get("fiscal_year"), "fp": r.get("fiscal_period"),
                   "rev": inc.get("revenues", {}).get("value"),
                   "net": inc.get("net_income_loss", {}).get("value"),
                   "eps": inc.get("basic_earnings_per_share", {}).get("value"),
                   "filed": r.get("filing_date")})
            inserted += res.rowcount

    if progress_cb:
        progress_cb(f"Done — {inserted} earnings rows inserted.")
    log_sync(engine, "Earnings", to_date, inserted, symbol)
    return {"status": "ok", "rows": inserted}


# ── EPS Estimates (Alpha Vantage free) ────────────────────────────────────────

def sync_eps_estimates(
    symbol: str,
    av_api_key: str,
    progress_cb: Callable[[str], None] = None,
) -> dict:
    """
    Fetch consensus EPS estimates from Alpha Vantage EARNINGS endpoint and
    write them into mkt.Earnings.EpsEstimate.

    Alpha Vantage free tier: 25 requests/day, covers major tickers.
    Endpoint: GET https://www.alphavantage.co/query?function=EARNINGS&symbol=X&apikey=Y
    Returns quarterlyEarnings[] with estimatedEPS, reportedEPS, fiscalDateEnding.

    The function matches rows by TickerId + PeriodOfReport (= fiscalDateEnding).
    Rows that exist in Alpha Vantage but not yet in mkt.Earnings are inserted
    with NULL for columns not available from this source.
    """
    import requests
    from sqlalchemy import text as _t

    engine = get_engine()

    # Ensure EpsEstimate column exists (idempotent)
    with engine.begin() as conn:
        conn.execute(_t("""
            IF NOT EXISTS (
                SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = 'mkt' AND TABLE_NAME = 'Earnings'
                  AND COLUMN_NAME = 'EpsEstimate'
            )
            ALTER TABLE mkt.Earnings ADD EpsEstimate FLOAT NULL
        """))

    if progress_cb:
        progress_cb(f"Fetching {symbol} EPS estimates from Alpha Vantage…")

    url = "https://www.alphavantage.co/query"
    params = {"function": "EARNINGS", "symbol": symbol, "apikey": av_api_key}
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        raise RuntimeError(f"Alpha Vantage request failed: {e}")

    if "Information" in data:
        raise RuntimeError(f"Alpha Vantage rate limit or plan restriction: {data['Information']}")
    if "Error Message" in data:
        raise RuntimeError(f"Alpha Vantage error: {data['Error Message']}")

    quarterly = data.get("quarterlyEarnings", [])
    if not quarterly:
        return {"status": "no_data", "rows": 0,
                "detail": "Alpha Vantage returned no quarterly earnings for this ticker."}

    tid = ensure_ticker(engine, symbol)
    updated = 0
    inserted = 0

    with engine.begin() as conn:
        for row in quarterly:
            period_str = row.get("fiscalDateEnding")
            if not period_str:
                continue
            est_str = row.get("estimatedEPS")
            act_str = row.get("reportedEPS")
            if est_str in (None, "None", ""):
                continue
            try:
                est = float(est_str)
            except (TypeError, ValueError):
                continue
            try:
                act = float(act_str) if act_str not in (None, "None", "") else None
            except (TypeError, ValueError):
                act = None

            # Try UPDATE first — most periods already exist from Polygon sync
            res = conn.execute(_t("""
                UPDATE mkt.Earnings
                SET EpsEstimate = :est
                WHERE TickerId = :tid AND PeriodOfReport = :period
            """), {"est": est, "tid": tid, "period": period_str})

            if res.rowcount > 0:
                updated += res.rowcount
            else:
                # Row not in DB yet — insert with minimal fields
                filed_str = row.get("reportedDate")
                conn.execute(_t("""
                    INSERT INTO mkt.Earnings
                        (TickerId, PeriodOfReport, EpsBasic, EpsEstimate, FiledDate)
                    VALUES (:tid, :period, :eps, :est, :filed)
                """), {"tid": tid, "period": period_str,
                       "eps": act, "est": est,
                       "filed": filed_str})
                inserted += 1

    total = updated + inserted
    if progress_cb:
        progress_cb(f"Done — {updated} rows updated, {inserted} new rows inserted.")
    return {"status": "ok", "rows": total, "updated": updated, "inserted": inserted}


# ── VIX Futures (CBOE free) ───────────────────────────────────────────────────

def sync_vix_futures(
    from_date: date = DEFAULT_START,
    to_date:   date = None,
    progress_cb: Callable[[str], None] = None,
) -> dict:
    """
    Fetch VIX front-month continuous futures (VX=F) via yfinance.
    Free, ~2 years of daily OHLCV history.
    """
    import yfinance as yf
    from sqlalchemy import text as _t

    to_date = to_date or date.today()
    engine  = get_engine()

    last = get_last_sync_date(engine, "VixFuture")
    if last:
        from_date = last

    if progress_cb:
        progress_cb("Fetching VIX front-month futures (VX=F) via yfinance…")

    try:
        df = yf.download(
            "VX=F",
            start=from_date.strftime("%Y-%m-%d"),
            end=to_date.strftime("%Y-%m-%d"),
            auto_adjust=True,
            progress=False,
        )
    except Exception as e:
        raise RuntimeError(f"yfinance VX=F download failed: {e}")

    if df is None or df.empty:
        return {"status": "no_data", "rows": 0}

    df = df.reset_index()
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df["trade_date"]   = pd.to_datetime(df["Date"]).dt.date
    df["expiry_month"] = df["trade_date"].apply(lambda d: f"{d.year}-{d.month:02d}")
    df = df.rename(columns={"Open": "open", "High": "high", "Low": "low",
                             "Close": "close", "Volume": "volume"})
    df["settle"] = df["close"]

    total_inserted = 0
    rows = df[["trade_date", "expiry_month", "open", "high", "low",
               "close", "settle", "volume"]].to_dict("records")

    with engine.begin() as conn:
        for row in rows:
            res = conn.execute(_t("""
                IF NOT EXISTS (SELECT 1 FROM mkt.VixFuture
                               WHERE TradeDate=:td AND ExpiryMonth=:em)
                INSERT INTO mkt.VixFuture (TradeDate, ExpiryMonth, [Open], High, Low,
                                           [Close], Settle, Volume)
                VALUES (:td, :em, :o, :h, :l, :c, :s, :v)
            """), {"td": row["trade_date"], "em": row["expiry_month"],
                   "o": row.get("open"),  "h": row.get("high"),
                   "l": row.get("low"),   "c": row.get("close"),
                   "s": row.get("settle"),"v": row.get("volume")})
            total_inserted += res.rowcount

    log_sync(engine, "VixFuture", to_date, total_inserted)
    return {"status": "ok" if total_inserted else "no_data", "rows": total_inserted}


# ── FOMC Calendar (hardcoded Fed dates) ──────────────────────────────────────

_FOMC_DATES = [
    # 2024
    date(2024,1,31), date(2024,3,20), date(2024,5,1),  date(2024,6,12),
    date(2024,7,31), date(2024,9,18), date(2024,11,7), date(2024,12,18),
    # 2025
    date(2025,1,29), date(2025,3,19), date(2025,5,7),  date(2025,6,18),
    date(2025,7,30), date(2025,9,17), date(2025,10,29),date(2025,12,10),
    # 2026
    date(2026,1,28), date(2026,3,18), date(2026,4,29), date(2026,6,17),
    date(2026,7,29), date(2026,9,16), date(2026,10,28),date(2026,12,9),
]

def sync_fomc_calendar(
    progress_cb: Callable[[str], None] = None,
) -> dict:
    """Insert FOMC meeting dates into mkt.FomcCalendar (upsert all known dates)."""
    from sqlalchemy import text as _t
    engine = get_engine()

    if progress_cb:
        progress_cb("Upserting FOMC calendar…")

    inserted = 0
    with engine.begin() as conn:
        for d in _FOMC_DATES:
            res = conn.execute(_t("""
                IF NOT EXISTS (SELECT 1 FROM mkt.FomcCalendar WHERE MeetingDate=:d)
                INSERT INTO mkt.FomcCalendar (MeetingDate, IsRateDecision) VALUES (:d, 1)
            """), {"d": d})
            inserted += res.rowcount

    log_sync(engine, "FomcCalendar", date.today(), inserted)
    if progress_cb:
        progress_cb(f"Done — {inserted} new FOMC dates inserted.")
    return {"status": "ok" if inserted else "up_to_date", "rows": inserted}


# ── Treasury Yield Curve (FRED free) ─────────────────────────────────────────

_TREASURY_SERIES = {
    "rate_3m":  "DGS3MO",
    "rate_6m":  "DGS6MO",
    "rate_1y":  "DGS1",
    "rate_2y":  "DGS2",
    "rate_5y":  "DGS5",
    "rate_10y": "DGS10",
    "rate_30y": "DGS30",
    "sofr":     "SOFR",
}


def sync_treasury_bars(
    from_date: date = DEFAULT_START,
    to_date:   date = None,
    progress_cb: Callable[[str], None] = None,
) -> dict:
    """Fetch Treasury yield curve from FRED (free) into mkt.TreasuryBar."""
    import requests
    from io import StringIO
    from sqlalchemy import text as _t

    to_date = to_date or date.today()
    engine  = get_engine()

    last = get_last_sync_date(engine, "TreasuryBar")
    if last:
        from_date = last
        with engine.begin() as conn:
            conn.execute(_t("DELETE FROM mkt.TreasuryBar WHERE BarDate = :d"), {"d": last})

    if progress_cb:
        progress_cb(f"Fetching Treasury yield curve from FRED {from_date} → {to_date}…")

    series_dfs = {}
    for col, series_id in _TREASURY_SERIES.items():
        if progress_cb:
            progress_cb(f"Fetching {series_id} from FRED…")
        try:
            url  = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            df = pd.read_csv(StringIO(resp.text))
            df.columns = [c.strip() for c in df.columns]
            df.columns = ["date", col]
            df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
            df[col]    = pd.to_numeric(df[col], errors="coerce")
            df = df.dropna(subset=["date"])
            df = df.set_index("date")
            series_dfs[col] = df
        except Exception as e:
            logger.warning(f"Treasury {series_id}: {e}")

    if not series_dfs:
        return {"status": "no_data", "rows": 0}

    # Merge all series on date
    merged = None
    for col, df in series_dfs.items():
        merged = df if merged is None else merged.join(df, how="outer")

    merged = merged.reset_index()
    merged = merged[(merged["date"] >= from_date) & (merged["date"] <= to_date)]
    merged = merged.sort_values("date").dropna(subset=["rate_2y", "rate_10y"], how="all")

    if merged.empty:
        return {"status": "no_data", "rows": 0}

    # Compute spreads
    merged["spread_2s10s"] = (
        pd.to_numeric(merged.get("rate_10y"), errors="coerce") -
        pd.to_numeric(merged.get("rate_2y"),  errors="coerce")
    )
    merged["spread_3m10y"] = (
        pd.to_numeric(merged.get("rate_10y"), errors="coerce") -
        pd.to_numeric(merged.get("rate_3m"),  errors="coerce")
    )

    cols_order = ["date", "rate_3m", "rate_6m", "rate_1y", "rate_2y", "rate_5y",
                  "rate_10y", "rate_30y", "sofr", "spread_2s10s", "spread_3m10y"]
    for c in cols_order:
        if c not in merged.columns:
            merged[c] = None
    rows = merged[cols_order].astype(object).where(pd.notnull(merged[cols_order]), other=None).to_dict("records")

    inserted = 0
    total    = len(rows)
    with engine.begin() as conn:
        for i, row in enumerate(rows):
            res = conn.execute(_t("""
                IF NOT EXISTS (SELECT 1 FROM mkt.TreasuryBar WHERE BarDate=:date)
                INSERT INTO mkt.TreasuryBar
                    (BarDate,Rate3M,Rate6M,Rate1Y,Rate2Y,Rate5Y,Rate10Y,Rate30Y,
                     Sofr,Spread2s10s,Spread3m10y)
                VALUES
                    (:date,:rate_3m,:rate_6m,:rate_1y,:rate_2y,:rate_5y,:rate_10y,:rate_30y,
                     :sofr,:spread_2s10s,:spread_3m10y)
            """), row)
            inserted += res.rowcount
            if progress_cb and (i + 1) % 50 == 0:
                progress_cb(f"Inserting yield curve: {i+1:,}/{total:,} rows  •  {row['date']}")

    log_sync(engine, "TreasuryBar", to_date, inserted)
    if progress_cb:
        progress_cb(f"Done — {inserted:,} yield curve rows inserted.")
    return {"status": "ok" if inserted else "no_data", "rows": inserted}


# ── CPI (FRED free) ──────────────────────────────────────────────────────────

# Series to sync: headline + core + energy + food
_CPI_SERIES = {
    "CPIAUCSL":  "CPI All Urban Consumers (headline)",
    "CPILFESL":  "Core CPI (ex food & energy)",
    "CPIENGSL":  "CPI Energy",
    "CPIFABSL":  "CPI Food & Beverages",
}


def sync_cpi(
    from_date: date = DEFAULT_START,
    to_date:   date = None,
    progress_cb: Callable[[str], None] = None,
) -> dict:
    """Fetch monthly CPI series from FRED (free, no API key) into mkt.CpiBar."""
    import requests
    from io import StringIO
    from sqlalchemy import text as _t

    to_date = to_date or date.today()
    engine  = get_engine()

    last = get_last_sync_date(engine, "CpiBar")
    if last:
        from_date = last
        with engine.begin() as conn:
            conn.execute(_t("DELETE FROM mkt.CpiBar WHERE BarDate = :d"), {"d": last})

    total_inserted = 0
    for i, (series_id, label) in enumerate(_CPI_SERIES.items()):
        if progress_cb:
            progress_cb(f"Fetching {series_id} ({label}) from FRED… ({i+1}/{len(_CPI_SERIES)})")
        try:
            url  = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            df = pd.read_csv(StringIO(resp.text))
            df.columns = [c.strip().lower() for c in df.columns]
            date_col  = df.columns[0]
            value_col = df.columns[1]
            df["bar_date"] = pd.to_datetime(df[date_col], errors="coerce").dt.date
            df["value"]    = pd.to_numeric(df[value_col], errors="coerce")
            df = df.dropna(subset=["bar_date", "value"])
            df = df[(df["bar_date"] >= from_date) & (df["bar_date"] <= to_date)]
            if df.empty:
                continue
            with engine.begin() as conn:
                for row in df.itertuples():
                    res = conn.execute(_t("""
                        IF NOT EXISTS (SELECT 1 FROM mkt.CpiBar WHERE BarDate=:d AND SeriesId=:sid)
                        INSERT INTO mkt.CpiBar (BarDate, SeriesId, Value) VALUES (:d, :sid, :v)
                    """), {"d": row.bar_date, "sid": series_id, "v": row.value})
                    total_inserted += res.rowcount
        except Exception as e:
            logger.warning(f"CPI sync {series_id}: {e}")

    log_sync(engine, "CpiBar", to_date, total_inserted)
    if progress_cb:
        progress_cb(f"Done — {total_inserted:,} CPI rows inserted.")
    return {"status": "ok" if total_inserted else "no_data", "rows": total_inserted}


# ── Coverage summary ──────────────────────────────────────────────────────────

def get_coverage_summary(symbols: list[str]) -> pd.DataFrame:
    """Return a DataFrame with data coverage per ticker for display in the UI."""
    engine = get_engine()
    rows = []
    for sym in symbols:
        price   = get_price_coverage(engine, sym)
        options = get_option_coverage(engine, sym)

        price_str   = f"{price[0]}  ->  {price[1]}"     if price   else "No data"
        options_str = f"{options[0]}  ->  {options[1]}" if options else "No data"

        # Count rows
        from sqlalchemy import text
        with engine.connect() as conn:
            tid_row = conn.execute(
                text("SELECT TickerId FROM mkt.Ticker WHERE Symbol = :s"), {"s": sym}
            ).fetchone()
            if tid_row:
                p_count = conn.execute(
                    text("SELECT COUNT(*) FROM mkt.PriceBar WHERE TickerId = :tid"),
                    {"tid": tid_row[0]}
                ).scalar()
                o_count = conn.execute(
                    text("SELECT COUNT(*) FROM mkt.OptionSnapshot WHERE TickerId = :tid"),
                    {"tid": tid_row[0]}
                ).scalar()
            else:
                p_count = o_count = 0

        rows.append({
            "Ticker":        sym,
            "Price Bars":    price_str,
            "Price Rows":    p_count,
            "Options":       options_str,
            "Option Rows":   o_count,
        })
    return pd.DataFrame(rows)
