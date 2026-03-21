"""
alan-strats  |  Data sync: Polygon -> SQL Server.
Handles backfill and incremental updates for all data types.
"""

import logging
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
            return {"status": "no_data", "rows": 0}

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


# ── Option Snapshots ──────────────────────────────────────────────────────────

def sync_option_snapshots(
    symbol: str,
    api_key: str,
    from_date: date = DEFAULT_START,
    to_date:   date = None,
    progress_cb: Callable[[str, int, int], None] = None,
) -> dict:
    """
    Fetch EOD options snapshots from Polygon for each trading day and store
    in mkt.OptionSnapshot.  Uses SPY price bars as the trading calendar.
    """
    to_date = to_date or date.today() - timedelta(days=1)  # yesterday = last complete EOD
    engine  = get_engine()
    client  = PolygonClient(api_key=api_key)

    # Build trading calendar from stored SPY price bars
    with engine.connect() as conn:
        from sqlalchemy import text
        rows = conn.execute(text("""
            SELECT pb.BarDate
            FROM   mkt.PriceBar pb
            JOIN   mkt.Ticker   t ON t.TickerId = pb.TickerId
            WHERE  t.Symbol = 'SPY'
              AND  pb.BarDate BETWEEN :from_d AND :to_d
            ORDER  BY pb.BarDate
        """), {"from_d": from_date, "to_d": to_date}).fetchall()
    trading_days = [r[0].date() if hasattr(r[0], 'date') else r[0] for r in rows]

    if not trading_days:
        return {"status": "no_calendar", "rows": 0,
                "message": "No SPY price bars found — sync SPY price bars first."}

    # Find already-covered dates
    with engine.connect() as conn:
        from sqlalchemy import text
        tid_row = conn.execute(
            text("SELECT TickerId FROM mkt.Ticker WHERE Symbol = :s"), {"s": symbol}
        ).fetchone()
        if tid_row:
            covered = set(
                r[0].date() if hasattr(r[0], 'date') else r[0]
                for r in conn.execute(text("""
                    SELECT DISTINCT SnapshotDate FROM mkt.OptionSnapshot
                    WHERE TickerId = :tid AND SnapshotDate BETWEEN :from_d AND :to_d
                """), {"tid": tid_row[0], "from_d": from_date, "to_d": to_date})
            )
        else:
            covered = set()

    # Re-sync the most recent covered date (delete + re-fetch) in case it was partial
    if covered and tid_row:
        last_covered = max(covered)
        covered.discard(last_covered)
        with engine.begin() as _conn:
            from sqlalchemy import text as _t2
            _conn.execute(_t2("DELETE FROM mkt.OptionSnapshot WHERE TickerId = :tid AND SnapshotDate = :d"),
                          {"tid": tid_row[0], "d": last_covered})

    missing = [d for d in trading_days if d not in covered]
    if not missing:
        return {"status": "up_to_date", "rows": 0}

    total_rows = 0
    errors     = []

    for i, snap_date in enumerate(missing):
        if progress_cb:
            progress_cb(f"Fetching {symbol} options for {snap_date}...", i + 1, len(missing), total_rows)
        try:
            df = client.get_options_chain(symbol, snapshot_date=str(snap_date))
            if df.empty:
                continue

            # Normalise column names to match upsert expectation
            df = df.rename(columns={
                "expiration":    "expiration",
                "type":          "type",
                "strike":        "strike",
                "bid":           "bid",
                "ask":           "ask",
                "iv":            "iv",
                "delta":         "delta",
                "gamma":         "gamma",
                "theta":         "theta",
                "vega":          "vega",
                "open_interest": "open_interest",
                "volume":        "volume",
            })

            rows = upsert_option_snapshots(engine, symbol, snap_date, df)
            total_rows += rows

        except Exception as e:
            logger.warning(f"Options sync failed for {symbol} on {snap_date}: {e}")
            errors.append(f"{snap_date}: {e}")

    log_sync(engine, "OptionSnapshot", to_date, total_rows, symbol,
             error="; ".join(errors) if errors else None)

    return {
        "status":  "ok" if not errors else "partial",
        "rows":    total_rows,
        "dates":   len(missing),
        "errors":  errors,
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
