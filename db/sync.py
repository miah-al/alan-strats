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
    source_symbol: Optional[str] = None,
) -> dict:
    """Fetch daily OHLCV from yfinance and store in mkt.PriceBar.

    yfinance is the canonical stock-data source. The Polygon stock aggregates
    endpoint is rate-limited to 5/min on this plan and frequently returns 0 bars,
    which silently left many universe tickers (QQQ/IWM/GLD/EEM…) with no history.
    `api_key` is retained for signature/UI compatibility and is unused here.
    `source_symbol` is the yfinance ticker when it differs from the stored symbol
    (index levels: NDX <- ^NDX, VXN <- ^VXN); YF_INDEX_SYMBOLS supplies it by default.
    """
    to_date = to_date or date.today()
    engine  = get_engine()
    yf_symbol = source_symbol or YF_INDEX_SYMBOLS.get(symbol.upper(), symbol)

    # Incremental: re-sync last date (delete + re-insert) then continue forward
    from sqlalchemy import text as _t
    last = get_last_sync_date(engine, "PriceBar", symbol)
    if last:
        # Use whichever is earlier — allows backfilling further back than last sync
        from_date = min(from_date, last)
        from alan_trader.db.client import get_ticker_id
        _tid = get_ticker_id(engine, symbol)
        if _tid:
            with engine.begin() as _conn:
                _conn.execute(_t("DELETE FROM mkt.PriceBar WHERE TickerId = :tid AND BarDate = :d"),
                              {"tid": _tid, "d": last})

    if from_date > to_date:
        return {"status": "up_to_date", "rows": 0}

    if progress_cb:
        progress_cb(f"Fetching {symbol} price bars {from_date} -> {to_date} (yfinance)...")

    try:
        from alan_trader.data.stock_data import yf_daily_bars
        n_days = (date.today() - from_date).days + 5
        df = yf_daily_bars(yf_symbol, n_days=max(n_days, 30))
        if df is not None and not df.empty:
            df = df.copy()
            df["date"] = pd.to_datetime(df["date"]).dt.date
            df = df[(df["date"] >= from_date) & (df["date"] <= to_date)]
        if df is None or df.empty:
            log_sync(engine, "PriceBar", to_date, 0, symbol)
            return {"status": "no_data", "rows": 0,
                    "detail": f"yfinance returned 0 bars for {symbol} ({from_date} → {to_date})"}

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


def _bs_greeks(S: float, K: float, T: float, r: float, iv: float, opt: str):
    """Return (delta, gamma) under Black-Scholes for the reconstructed IV.

    Polygon's Starter plan gives no historical greeks, so we derive delta/gamma
    analytically from the same IV we invert from the option's traded price. This
    lets gamma/delta-driven strategies (dealer_gamma_regime, expiry_max_pain,
    sizing on delta) see real, self-consistent greeks instead of NULLs.
    """
    if T <= 0 or iv <= 0 or S <= 0 or K <= 0:
        return None, None
    try:
        from scipy.stats import norm as _norm
        cdf, pdf = _norm.cdf, _norm.pdf
    except ImportError:
        cdf = lambda x: 0.5 * (1 + math.erf(x / math.sqrt(2)))
        pdf = lambda x: math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)
    try:
        d1 = (math.log(S / K) + (r + 0.5 * iv * iv) * T) / (iv * math.sqrt(T))
        delta = cdf(d1) if opt == "call" else cdf(d1) - 1.0
        gamma = pdf(d1) / (S * iv * math.sqrt(T))
        return round(float(delta), 6), round(float(gamma), 8)
    except Exception:
        return None, None


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
    force: bool = False,            # re-fetch even dates already synced (adds new DTE bands / greeks)
    monthly_only: bool = False,     # keep only 3rd-Friday monthly expiries (feasible ≥45-DTE backfill)
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

    # Optionally keep only standard monthly expiries (3rd Friday). SPY lists
    # daily + weekly + monthly series, so a full per-contract OHLC backfill is
    # O(10k) contracts even for a few weeks. Calendar / skew strategies only
    # need the monthly ladder, so this cuts the fetch ~10-20× and makes a
    # multi-month ≥45-DTE backfill feasible.
    if monthly_only:
        def _is_third_friday(dstr: str) -> bool:
            d = date.fromisoformat(dstr)
            return d.weekday() == 4 and 15 <= d.day <= 21
        all_contracts = [c for c in all_contracts
                         if _is_third_friday(c.get("expiration_date", ""))]
        if not all_contracts:
            return {"status": "error", "message": "No monthly (3rd-Friday) contracts in range."}

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

    # Pre-load already-synced dates so we can skip them on resume. With
    # force=True we intentionally do NOT skip — this lets a re-sync widen the
    # DTE band (e.g. add 23–60 DTE rows) and backfill greeks on dates that were
    # previously synced with a narrower window. The upsert is idempotent
    # (IF NOT EXISTS INSERT) so existing rows are never duplicated.
    from alan_trader.db.client import get_ticker_id as _get_tid
    # The resume key MUST include contract type. Keying on date alone is a
    # date-level test applied inside a contract-level loop: `all_contracts`
    # lists every call before every put, so once the calls have covered each
    # snapshot date, every single put contract matches "already synced" and is
    # skipped. That silently produced a 63,010-row, calls-only surface with
    # zero puts — which quietly breaks every credit-spread, condor and
    # put-based strategy downstream.
    _tid = _get_tid(engine, symbol)
    synced_keys: set[tuple] = set()
    if _tid and not force:
        with engine.connect() as _conn:
            from sqlalchemy import text as _t
            _rows = _conn.execute(_t("""
                SELECT DISTINCT SnapshotDate, ContractType FROM mkt.OptionSnapshot
                WHERE TickerId = :tid AND SnapshotDate BETWEEN :from_d AND :to_d
            """), {"tid": _tid, "from_d": from_date, "to_d": to_date}).fetchall()
            synced_keys = {
                ((r[0] if isinstance(r[0], date) else r[0].date()),
                 str(r[1] or "").upper()[:1])
                for r in _rows
            }
    synced_dates = {k[0] for k in synced_keys}   # kept for progress reporting

    if synced_dates and progress_cb:
        progress_cb(
            f"Resuming — {len(synced_dates)} dates already synced, skipping those…",
            0, len(all_contracts), 0,
        )

    # Step 2: for each contract, fetch daily OHLC and build per-date chain rows.
    # Flush to DB every FLUSH_EVERY contracts so progress is saved incrementally.
    FLUSH_EVERY  = 500
    rows_by_date: dict[date, list[dict]] = {}
    total_rows   = 0
    errors       = []

    from scipy.optimize import brentq as _brentq

    def _flush_to_db():
        """Write all accumulated rows to DB, update synced_dates."""
        for snap_date, date_rows in sorted(rows_by_date.items()):
            try:
                # force=True means "recompute and REPLACE", so the write must
                # overwrite. Without this the insert-only upsert silently drops
                # every corrected value and a corrective re-sync is a no-op.
                n = upsert_option_snapshots(engine, symbol, snap_date,
                                            pd.DataFrame(date_rows),
                                            overwrite=force)
                total_rows_ref[0] += n
                synced_dates.add(snap_date)
                for _r in date_rows:
                    synced_keys.add((snap_date,
                                     str(_r.get("type") or "").upper()[:1]))
            except Exception as e:
                errors.append(f"{snap_date}: {e}")
        rows_by_date.clear()

    # Mutable container so _flush_to_db can update the outer total_rows
    total_rows_ref = [0]

    for i, contract in enumerate(all_contracts):
        ticker     = contract["ticker"]
        K          = float(contract["strike_price"])
        exp_str    = contract["expiration_date"]
        opt_type   = contract["contract_type"]   # "call" or "put"
        exp_date   = date.fromisoformat(exp_str)

        if progress_cb:
            progress_cb(f"[{i+1}/{len(all_contracts)}] {ticker}", i + 1, len(all_contracts), total_rows_ref[0])

        # Skip contract entirely if all its possible bar dates are already synced
        contract_start = max(from_date, exp_date - timedelta(days=dte_max))
        contract_end   = min(to_date,   exp_date - timedelta(days=dte_min))
        if contract_start > contract_end:
            continue
        # Check if every trading date in this contract's window is already synced
        _ct_key = str(opt_type or "").upper()[:1]     # 'C' or 'P'
        relevant_spot_dates = [d for d in spot_dates if contract_start <= d <= contract_end]
        if relevant_spot_dates and all((d, _ct_key) in synced_keys
                                       for d in relevant_spot_dates):
            continue  # this side of the chain is covered — skip the API call

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
            # Must be keyed on contract type, like the contract-level skip
            # above. A bare date test drops every put bar on any date the calls
            # already covered — which silently produced a calls-only surface
            # even after the contract-level skip was fixed.
            if (bar_date, _ct_key) in synced_keys:
                continue  # this side of the chain already committed to DB

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

            # `dte` is CALENDAR days, so the year fraction must use a calendar
            # year. Dividing calendar days by the 252 trading-day year made T
            # 365/252 = 1.45x too large; because IV is found by inverting
            # Black-Scholes against the observed price, an over-large T forces a
            # correspondingly SMALLER sigma to reproduce that price. Every
            # stored ImpliedVol was therefore ~15% too low
            # (predicted sqrt(252/365) = 0.831; measured stored/correct = 0.851
            # across 22,747 SPY puts), and _bs_greeks inherits the same T so
            # Delta and Gamma carry it too.
            #
            # NOTE: this corrects future syncs only. Rows already in
            # mkt.OptionSnapshot keep the old values until re-synced with
            # `python -m scripts.bootstrap_market_data --options-only`.
            T = dte / 365.0
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
            delta, gamma = _bs_greeks(S, K, T, r, iv, opt_type)
            rows_by_date.setdefault(bar_date, []).append({
                "expiration":    exp_str,
                "type":          opt_type,
                "strike":        K,
                "bid":           round(close_price - spread / 2, 4),
                "ask":           round(close_price + spread / 2, 4),
                "iv":            round(iv, 6),
                "delta":         delta,
                "gamma":         gamma,
                "theta":         None,
                "vega":          None,
                "open_interest": None,
                "volume":        int(row.get("volume") or 0),
            })

        # Flush to DB every FLUSH_EVERY contracts
        if (i + 1) % FLUSH_EVERY == 0 and rows_by_date:
            _flush_to_db()

    # Step 3: final flush for any remaining rows
    if rows_by_date:
        _flush_to_db()

    total_rows = total_rows_ref[0]

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
        from_date = min(from_date, last)
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
            from_date = min(from_date, last)
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
        from_date = min(from_date, last)
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
        from_date = min(from_date, last)

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
            inserted += max(res.rowcount, 0)

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
        from_date = min(from_date, last)

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
            inserted += max(res.rowcount, 0)

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

    # Ensure EpsEstimate / AnnouncementDate columns exist (idempotent — also handled
    # by schema.sql migrations, but kept here so this function works on stale schemas).
    with engine.begin() as conn:
        conn.execute(_t("""
            IF NOT EXISTS (
                SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = 'mkt' AND TABLE_NAME = 'Earnings'
                  AND COLUMN_NAME = 'EpsEstimate'
            )
            ALTER TABLE mkt.Earnings ADD EpsEstimate FLOAT NULL
        """))
        conn.execute(_t("""
            IF NOT EXISTS (
                SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = 'mkt' AND TABLE_NAME = 'Earnings'
                  AND COLUMN_NAME = 'AnnouncementDate'
            )
            ALTER TABLE mkt.Earnings ADD AnnouncementDate DATE NULL
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

            # Alpha Vantage's `reportedDate` IS the actual earnings announcement
            # date — what strategies need for trade timing. Polygon's `filing_date`
            # is the SEC filing date, often weeks later. Always populate
            # AnnouncementDate from reportedDate when available.
            announce_str = row.get("reportedDate") or None

            # Try UPDATE first — most periods already exist from Polygon sync.
            # Only overwrite AnnouncementDate when we have a non-null value to
            # avoid wiping a previously-set date with NULL.
            res = conn.execute(_t("""
                UPDATE mkt.Earnings
                SET EpsEstimate     = :est,
                    AnnouncementDate = COALESCE(:announce, AnnouncementDate)
                WHERE TickerId = :tid AND PeriodOfReport = :period
            """), {"est": est, "announce": announce_str,
                   "tid": tid, "period": period_str})

            if res.rowcount > 0:
                updated += max(res.rowcount, 0)
            else:
                # Row not in DB yet — insert with minimal fields. Set both
                # AnnouncementDate and FiledDate to reportedDate as a best-effort
                # fallback (Polygon sync, when it lands later, will overwrite
                # FiledDate with the SEC filing date but leave AnnouncementDate alone).
                conn.execute(_t("""
                    INSERT INTO mkt.Earnings
                        (TickerId, PeriodOfReport, EpsBasic, EpsEstimate,
                         FiledDate, AnnouncementDate)
                    VALUES (:tid, :period, :eps, :est, :announce, :announce)
                """), {"tid": tid, "period": period_str,
                       "eps": act, "est": est,
                       "announce": announce_str})
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
        from_date = min(from_date, last)

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
            total_inserted += max(res.rowcount, 0)

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
            inserted += max(res.rowcount, 0)

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
        from_date = min(from_date, last)
        with engine.begin() as conn:
            conn.execute(_t("DELETE FROM mkt.TreasuryBar WHERE BarDate = :d"), {"d": last})

    if progress_cb:
        progress_cb(f"Fetching Treasury yield curve from FRED {from_date} → {to_date}…")

    series_dfs = {}
    for col, series_id in _TREASURY_SERIES.items():
        if progress_cb:
            progress_cb(f"Fetching {series_id} from FRED…")
        try:
            url  = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&observation_start={from_date}"
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
            inserted += max(res.rowcount, 0)
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
        from_date = min(from_date, last)
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
                    total_inserted += max(res.rowcount, 0)
        except Exception as e:
            logger.warning(f"CPI sync {series_id}: {e}")

    log_sync(engine, "CpiBar", to_date, total_inserted)
    if progress_cb:
        progress_cb(f"Done — {total_inserted:,} CPI rows inserted.")
    return {"status": "ok" if total_inserted else "no_data", "rows": total_inserted}


# ── Coverage summary ──────────────────────────────────────────────────────────

# ── Intraday minute bars (Polygon aggregates) ────────────────────────────────

#: Symbols served by Polygon's index feed (ticker prefix "I:") rather than the stock feed.
INDEX_SYMBOLS = {"NDX", "SPX", "RUT", "DJI", "VIX", "VXN", "OEX", "XSP"}

#: Daily bars for index levels come from yfinance under a caret symbol; the DB keeps the plain one.
YF_INDEX_SYMBOLS = {"NDX": "^NDX", "VXN": "^VXN", "SPX": "^GSPC", "VIX": "^VIX", "RUT": "^RUT"}

MINUTE_BARS_DEFAULT_START = date(2023, 10, 1)      # Polygon I:NDX 1-minute history starts here on this plan


def polygon_ticker_for(symbol: str) -> str:
    return f"I:{symbol}" if symbol.upper() in INDEX_SYMBOLS else symbol.upper()


def _polygon_minute_aggs(polygon_ticker: str, start: date, end: date, api_key: str) -> pd.DataFrame:
    """All 1-minute aggregates for [start, end] (inclusive), regular session only, as a frame
    ts (naive US/Eastern bar START), open, high, low, close, volume, trades, vwap (the last two
    are None for index feeds). Works for index (I:NDX), stock and option (O:NDXP...) tickers.
    Paginates next_url, backs off on 429."""
    import time
    import requests
    url = f"https://api.polygon.io/v2/aggs/ticker/{polygon_ticker}/range/1/minute/{start}/{end}"
    params = {"adjusted": "false", "sort": "asc", "limit": 50000, "apiKey": api_key}
    rows: list = []
    while url:
        resp = None
        for attempt in range(6):
            resp = requests.get(url, params=params, timeout=60)
            if resp.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            break
        payload = resp.json()
        rows += payload.get("results") or []
        url = payload.get("next_url")
        params = {"apiKey": api_key}
    if not rows:
        return pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume", "trades", "vwap"])
    raw = pd.DataFrame(rows)
    ts = pd.to_datetime(raw["t"], unit="ms", utc=True).dt.tz_convert("US/Eastern").dt.tz_localize(None)
    df = pd.DataFrame({"ts": ts, "open": raw["o"], "high": raw["h"], "low": raw["l"], "close": raw["c"],
                       "volume": raw["v"] if "v" in raw.columns else None,
                       "trades": raw["n"] if "n" in raw.columns else None,
                       "vwap": raw["vw"] if "vw" in raw.columns else None})
    minute = df["ts"].dt.hour * 60 + df["ts"].dt.minute
    df = df[(minute >= 9 * 60 + 30) & (minute < 16 * 60) & (df["ts"].dt.weekday < 5)]
    return df.sort_values("ts").drop_duplicates("ts").reset_index(drop=True)


def sync_minute_bars(
    symbol: str,
    api_key: str,
    from_date: date = MINUTE_BARS_DEFAULT_START,
    to_date: Optional[date] = None,
    refresh: bool = False,
    progress_cb: Callable[[str], None] = None,
) -> dict:
    """Pull 1-minute bars for symbol from Polygon into mkt.MinuteBar, one calendar month at a
    time. Months already present are skipped unless refresh=True; the current month is always
    re-pulled. Index symbols (NDX, SPX, ...) use Polygon's I: feed. Returns rows, sessions, months."""
    import calendar as _cal
    import time
    from alan_trader.db.client import replace_minute_bars, get_minute_bar_months, get_minute_bar_coverage
    if not api_key:
        return {"status": "error", "rows": 0, "detail": "POLYGON_API_KEY missing"}
    engine = get_engine()
    to_date = to_date or date.today()
    pticker = polygon_ticker_for(symbol)
    asset_class = "index" if symbol.upper() in INDEX_SYMBOLS else "etf"
    have = set() if refresh else get_minute_bar_months(engine, symbol)
    today = date.today()
    y, m = from_date.year, from_date.month
    total_rows, months_pulled, empty_months = 0, 0, []
    while (y, m) <= (to_date.year, to_date.month):
        current = (y, m) == (today.year, today.month)
        if (y, m) in have and not current:
            m += 1
            if m == 13:
                y, m = y + 1, 1
            continue
        start = max(from_date, date(y, m, 1))
        end = min(to_date, date(y, m, _cal.monthrange(y, m)[1]))
        if progress_cb:
            progress_cb(f"{symbol} minute bars {y}-{m:02d} ({pticker})…")
        df = pd.DataFrame()
        for attempt in range(3):                       # Polygon occasionally returns an empty page
            df = _polygon_minute_aggs(pticker, start, end, api_key)
            if len(df):
                break
            time.sleep(3)
        if len(df):
            n = replace_minute_bars(engine, symbol, df, source="polygon", asset_class=asset_class)
            total_rows += n
            months_pulled += 1
            if progress_cb:
                progress_cb(f"{symbol} {y}-{m:02d}: {n:,} bars, {df['ts'].dt.date.nunique()} sessions")
        else:
            empty_months.append(f"{y}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    log_sync(engine, "MinuteBar", to_date, total_rows, symbol)
    cov = get_minute_bar_coverage(engine, symbol)
    return {"status": "ok" if total_rows or cov else "no_data", "rows": total_rows, "months": months_pulled,
            "empty_months": empty_months,
            "coverage": (f"{cov[0]} .. {cov[1]}, {cov[2]} sessions" if cov else "none")}


# ── Option minute bars (per-contract trade aggregates, Polygon) ──────────────

OPTION_MINUTE_DEFAULT_START = date(2024, 10, 1)     # Options Starter: about two years of option minute bars

#: Option root for the same-day (PM-settled) expiries of each index underlying.
OPTION_ROOTS = {"NDX": "NDXP", "SPX": "SPXW", "RUT": "RUTW", "XSP": "XSP"}


def parse_option_ticker(ticker: str) -> tuple[str, date, str, float]:
    """'O:NDXP260826C29270000' -> ('NDXP', date(2026, 8, 26), 'C', 29270.0). OCC 21-character body."""
    body = ticker.split(":", 1)[1] if ":" in ticker else ticker
    i = 0
    while i < len(body) and not body[i].isdigit():
        i += 1
    root, rest = body[:i], body[i:]
    yy, mm, dd = int(rest[0:2]), int(rest[2:4]), int(rest[4:6])
    right = rest[6].upper()
    strike = int(rest[7:15]) / 1000.0
    return root, date(2000 + yy, mm, dd), right, strike


def select_option_strikes(strikes, ref_level: float, band: float = 400.0, step: int = 25) -> list[float]:
    """Strikes within +-band of ref_level that sit on the `step` grid, ascending, deduplicated."""
    out = set()
    for k in strikes:
        k = float(k)
        if abs(k - ref_level) <= band and (step <= 0 or abs(k / step - round(k / step)) < 1e-9):
            out.add(k)
    return sorted(out)


def _polygon_option_contracts(underlying: str, expiry: date, api_key: str) -> pd.DataFrame:
    """Every listed option contract on `underlying` expiring on `expiry` (as of that day), as a
    frame ticker, root, strike, right, expiry. Paginates next_url, backs off on 429."""
    import time
    import requests
    url = "https://api.polygon.io/v3/reference/options/contracts"
    params: dict = {"underlying_ticker": underlying.upper(), "expiration_date": expiry.isoformat(),
                    "as_of": expiry.isoformat(), "limit": 1000, "apiKey": api_key}
    if expiry < date.today():
        params["expired"] = "true"
    rows: list = []
    while url:
        resp = None
        for attempt in range(6):
            resp = requests.get(url, params=params, timeout=60)
            if resp.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            break
        payload = resp.json()
        rows += payload.get("results") or []
        url = payload.get("next_url")
        params = {"apiKey": api_key}
    if not rows:
        return pd.DataFrame(columns=["ticker", "root", "strike", "right", "expiry"])
    out = []
    for r in rows:
        try:
            root, exp, right, strike = parse_option_ticker(r["ticker"])
        except Exception:
            continue
        out.append({"ticker": r["ticker"], "root": root, "strike": float(r.get("strike_price", strike)),
                    "right": (r.get("contract_type") or right)[0].upper(), "expiry": exp})
    return pd.DataFrame(out)


def _session_ref_level(engine, symbol: str, day: date, ref_time: str = "13:00") -> Optional[float]:
    """The underlying's close at `ref_time` on `day` from mkt.MinuteBar (first bar at or after it,
    else the session's last close). None when the session has no bars."""
    from alan_trader.db import client as _client
    bars = _client.get_minute_bars(engine, symbol, day, day)
    if bars.empty:
        return None
    hh, mm = (int(x) for x in ref_time.split(":"))
    minute = bars["ts"].dt.hour * 60 + bars["ts"].dt.minute
    at = bars[minute >= hh * 60 + mm]
    return float(at["close"].iloc[0]) if len(at) else float(bars["close"].iloc[-1])


def sync_option_minute_bars(
    symbol: str,
    api_key: str,
    from_date: date = OPTION_MINUTE_DEFAULT_START,
    to_date: Optional[date] = None,
    band: float = 400.0,
    step: int = 25,
    ref_time: str = "13:00",
    root: Optional[str] = None,
    refresh: bool = False,
    max_sessions: Optional[int] = None,
    progress_cb: Callable[[str], None] = None,
) -> dict:
    """Pull per-contract 1-minute trade bars for the SAME-DAY expiry of `symbol` into
    mkt.OptionMinuteBar, one session at a time, for the strikes on the `step` grid within
    +-band of the underlying's `ref_time` level (from mkt.MinuteBar, which must be filled
    first). Sessions already in mkt.OptionMinuteSession are skipped unless refresh=True.
    About 60 to 70 requests per session on NDX; resumable. Returns rows, sessions, coverage."""
    from alan_trader.db.client import (get_minute_bar_sessions, replace_option_minute_bars,
                                       upsert_option_minute_session, get_option_minute_sessions,
                                       get_option_minute_coverage)
    if not api_key:
        return {"status": "error", "rows": 0, "detail": "POLYGON_API_KEY missing"}
    engine = get_engine()
    to_date = to_date or date.today()
    root = (root or OPTION_ROOTS.get(symbol.upper(), symbol.upper())).upper()
    sessions = get_minute_bar_sessions(engine, symbol, from_date, to_date)
    if not sessions:
        return {"status": "error", "rows": 0,
                "detail": f"no mkt.MinuteBar sessions for {symbol} in {from_date}..{to_date}; pull the index bars first"}
    have = set() if refresh else set(get_option_minute_sessions(engine, symbol)["session"].tolist())
    todo = [d for d in sessions if d not in have]
    if max_sessions:
        todo = todo[:max_sessions]
    total_rows, done, failed = 0, 0, []
    for day in todo:
        if progress_cb:
            progress_cb(f"{symbol} option minutes {day} ({root})…")
        try:
            ref = _session_ref_level(engine, symbol, day, ref_time)
            contracts = _polygon_option_contracts(symbol, day, api_key)
            sel = contracts[contracts["root"] == root] if len(contracts) else contracts
            strikes = select_option_strikes(sel["strike"].tolist(), ref, band, step) if (ref is not None and len(sel)) else []
            sel = sel[sel["strike"].isin(strikes)]
            frames, with_prints = [], 0
            for c in sel.itertuples(index=False):
                bars = _polygon_minute_aggs(c.ticker, day, day, api_key)
                if len(bars):
                    with_prints += 1
                    frames.append(bars.assign(right=c.right, strike=float(c.strike)))
            df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
            n = replace_option_minute_bars(engine, symbol, day, df, root=root)
            upsert_option_minute_session(engine, symbol, day, day, root=root, ref_level=ref,
                                         strike_lo=(min(strikes) if strikes else None),
                                         strike_hi=(max(strikes) if strikes else None), strike_step=step,
                                         contracts=len(sel), with_prints=with_prints, bars=n)
            total_rows += n
            done += 1
            if progress_cb:
                progress_cb(f"{symbol} {day}: {len(sel)} contracts, {with_prints} with prints, {n:,} bars")
        except Exception as exc:                        # one bad session must not end a three-hour pull
            failed.append((day.isoformat(), str(exc)[:120]))
            if progress_cb:
                progress_cb(f"{symbol} {day}: FAILED {str(exc)[:80]}")
    log_sync(engine, "OptionMinuteBar", to_date, total_rows, symbol,
             error=(f"{len(failed)} sessions failed" if failed else None))
    cov = get_option_minute_coverage(engine, symbol)
    return {"status": "ok" if (done or cov) else "no_data", "rows": total_rows, "sessions": done,
            "skipped": len(sessions) - len(todo), "failed": failed,
            "coverage": (f"{cov['first']} .. {cov['last']}, {cov['sessions']} sessions, "
                         f"{cov['contracts']:,} contracts, {cov['bars']:,} bars" if cov else "none")}


# ── Event calendar (trading-day filters) ─────────────────────────────────────

EVENT_SEED_DIR = None   # resolved lazily: <repo>/db/seed/events


def _event_seed_dir():
    import os
    return EVENT_SEED_DIR or os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed", "events")


def _third_fridays(start: date, end: date):
    y, m = start.year, start.month
    while date(y, m, 1) <= end:
        d = date(y, m, 15)
        while d.weekday() != 4:
            d += timedelta(days=1)
        if start <= d <= end:
            yield d
        m += 1
        if m == 13:
            y, m = y + 1, 1


def sync_event_calendar(
    from_date: date = date(2024, 1, 1),
    to_date: date = date(2026, 12, 31),
    seed_dir: Optional[str] = None,
    progress_cb: Callable[[str], None] = None,
) -> dict:
    """Rebuild mkt.EventCalendar for [from_date, to_date] from: FOMC decision dates in
    mkt.FomcCalendar; the hand-kept seed CSVs in db/seed/events (bls: cpi/nfp, bea: pce,
    exchange: holiday/early_close, megacap: earnings reactions); and computed monthly third
    Fridays (opex). Kinds are lower-cased; one row per (date, kind)."""
    import csv
    import os
    from sqlalchemy import text as _t
    from alan_trader.db.client import replace_event_calendar
    engine = get_engine()
    rows: list[dict] = []
    with engine.connect() as conn:
        for (d,) in conn.execute(_t("SELECT MeetingDate FROM mkt.FomcCalendar WHERE IsRateDecision = 1 ORDER BY MeetingDate")).fetchall():
            rows.append({"date": str(d)[:10], "kind": "fomc", "label": "FOMC decision", "source": "mkt.FomcCalendar"})
    sdir = seed_dir or _event_seed_dir()
    seeds_read = {}
    for name in ("bls", "bea", "exchange", "megacap"):
        p = os.path.join(sdir, f"{name}.csv")
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8", newline="") as fh:
            got = [r for r in csv.DictReader(fh) if r.get("date")]
        seeds_read[name] = len(got)
        rows += got
    rows += [{"date": str(d), "kind": "opex", "label": "Third Friday", "source": "computed"} for d in _third_fridays(from_date, to_date)]
    rows = [r for r in rows if from_date <= date.fromisoformat(str(r["date"])[:10]) <= to_date]
    seen, out = set(), []
    for r in sorted(rows, key=lambda r: (str(r["date"]), str(r["kind"]).lower())):
        key = (str(r["date"])[:10], str(r["kind"]).strip().lower())
        if key in seen:
            continue
        seen.add(key)
        out.append({"date": key[0], "kind": key[1], "label": r.get("label", ""), "source": r.get("source", "")})
    n = replace_event_calendar(engine, out)
    by_kind: dict[str, int] = {}
    for r in out:
        by_kind[r["kind"]] = by_kind.get(r["kind"], 0) + 1
    log_sync(engine, "EventCalendar", to_date, n)
    if progress_cb:
        progress_cb(f"EventCalendar: {n} rows {by_kind}")
    return {"status": "ok" if n else "no_data", "rows": n, "by_kind": by_kind, "seeds": seeds_read}


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
