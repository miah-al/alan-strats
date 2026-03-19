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

    # Incremental: start from day after last sync
    last = get_last_sync_date(engine, "PriceBar", symbol)
    if last:
        from_date = last + timedelta(days=1)

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
        rows = upsert_price_bars(engine, symbol, df)
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

    last = get_last_sync_date(engine, "VixBar")
    if last:
        from_date = last + timedelta(days=1)

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

        rows = upsert_vix_bars(engine, df)
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

    last = get_last_sync_date(engine, "MacroBar")
    if last:
        # Verify data actually exists — SyncLog can be ahead of actual data
        with engine.connect() as conn:
            from sqlalchemy import text as _text
            count = conn.execute(_text("SELECT COUNT(*) FROM mkt.MacroBar")).scalar()
        if count == 0:
            last = None  # Force full resync
        else:
            from_date = last + timedelta(days=1)

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
        rows = upsert_macro_bars(engine, macro)
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

    last = get_last_sync_date(engine, "News", symbol)
    if last:
        from_date = last + timedelta(days=1)

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
        rows = upsert_news(engine, symbol, df)
        log_sync(engine, "News", to_date, rows, symbol)
        return {"status": "ok", "rows": rows}
    except Exception as e:
        log_sync(engine, "News", to_date, 0, symbol, error=str(e))
        raise


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
