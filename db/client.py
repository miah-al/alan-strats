"""
alan-strats  |  SQL Server database client.
Handles connection, upserts, and incremental sync tracking.
"""

import os
import logging
from contextlib import contextmanager
from datetime import date, timedelta
from typing import Optional

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

# ── Connection ────────────────────────────────────────────────────────────────

_DEFAULT_SERVER = r"localhost\SQLEXPRESS"
_DEFAULT_DB     = "AlanStrats"

def _build_connection_string(server: str = _DEFAULT_SERVER,
                              database: str = _DEFAULT_DB) -> str:
    driver = "ODBC Driver 17 for SQL Server"
    return (
        f"mssql+pyodbc://{server}/{database}"
        f"?driver={driver.replace(' ', '+')}"
        f"&trusted_connection=yes"
        f"&TrustServerCertificate=yes"
    )


def get_engine(server: str = _DEFAULT_SERVER,
               database: str = _DEFAULT_DB) -> Engine:
    conn_str = _build_connection_string(server, database)
    return create_engine(conn_str, fast_executemany=True)


@contextmanager
def get_conn(engine: Engine):
    with engine.connect() as conn:
        yield conn


# ── Ticker ────────────────────────────────────────────────────────────────────

def get_ticker_id(engine: Engine, symbol: str) -> Optional[int]:
    """Return TickerId for a symbol, or None if not found."""
    with get_conn(engine) as conn:
        row = conn.execute(
            text("SELECT TickerId FROM mkt.Ticker WHERE Symbol = :sym"),
            {"sym": symbol.upper()},
        ).fetchone()
    return int(row[0]) if row else None


def ensure_ticker(engine: Engine, symbol: str, name: str = "",
                  asset_class: str = "equity") -> int:
    """Return TickerId, inserting the ticker if it doesn't exist."""
    tid = get_ticker_id(engine, symbol)
    if tid is not None:
        return tid
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO mkt.Ticker (Symbol, Name, AssetClass)
                VALUES (:sym, :name, :cls)
            """),
            {"sym": symbol.upper(), "name": name, "cls": asset_class},
        )
    return get_ticker_id(engine, symbol)


# ── PriceBar ──────────────────────────────────────────────────────────────────

def get_price_bars(engine: Engine, symbol: str,
                   from_date: date, to_date: date) -> pd.DataFrame:
    """Return OHLCV bars for symbol between dates (inclusive)."""
    tid = get_ticker_id(engine, symbol)
    if tid is None:
        return pd.DataFrame()
    query = text("""
        SELECT BarDate, [Open], High, Low, [Close], Volume, Vwap
        FROM   mkt.PriceBar
        WHERE  TickerId = :tid
          AND  BarDate BETWEEN :from_d AND :to_d
        ORDER  BY BarDate
    """)
    with get_conn(engine) as conn:
        result = conn.execute(query, {"tid": tid, "from_d": from_date, "to_d": to_date})
        df = pd.DataFrame(result.fetchall(), columns=result.keys())
    if not df.empty:
        df.columns = [c.lower() for c in df.columns]
        df = df.rename(columns={"bardate": "date"})
        for col in ["open", "high", "low", "close", "volume", "vwap"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def upsert_price_bars(engine: Engine, symbol: str, df: pd.DataFrame,
                      progress_cb=None) -> int:
    """
    Insert price bars, skipping rows that already exist.
    df must have columns: date, open, high, low, close, volume, vwap (optional).
    Returns number of rows inserted.
    progress_cb(inserted, total) called every 50 rows if provided.
    """
    if df.empty:
        return 0
    tid = ensure_ticker(engine, symbol)

    df = df.copy()
    df.columns = [c.lower() for c in df.columns]
    if "date" not in df.columns and df.index.name == "date":
        df = df.reset_index()

    df["ticker_id"] = tid
    if "vwap" not in df.columns:
        df["vwap"] = None

    sql = text("""
        IF NOT EXISTS (
            SELECT 1 FROM mkt.PriceBar WHERE TickerId = :ticker_id AND BarDate = :date
        )
        INSERT INTO mkt.PriceBar (TickerId, BarDate, [Open], High, Low, [Close], Volume, Vwap)
        VALUES (:ticker_id, :date, :open, :high, :low, :close, :volume, :vwap)
    """)

    _out = df[["ticker_id","date","open","high","low","close","volume","vwap"]].copy()
    _out = _out.astype(object).where(pd.notnull(_out), other=None)
    rows = _out.to_dict("records")
    inserted = 0
    total = len(rows)
    with engine.begin() as conn:
        for i, row in enumerate(rows):
            result = conn.execute(sql, row)
            inserted += result.rowcount
            if progress_cb and (i + 1) % 50 == 0:
                progress_cb(i + 1, total, row.get("date"))
    if progress_cb:
        progress_cb(total, total, rows[-1].get("date") if rows else None)
    return inserted


def get_price_coverage(engine: Engine, symbol: str) -> Optional[tuple[date, date]]:
    """Return (min_date, max_date) of stored price bars, or None if empty."""
    tid = get_ticker_id(engine, symbol)
    if tid is None:
        return None
    with get_conn(engine) as conn:
        row = conn.execute(
            text("SELECT MIN(BarDate), MAX(BarDate) FROM mkt.PriceBar WHERE TickerId = :tid"),
            {"tid": tid},
        ).fetchone()
    if row and row[0]:
        return row[0].date() if hasattr(row[0], 'date') else row[0], \
               row[1].date() if hasattr(row[1], 'date') else row[1]
    return None


def get_vix_bars(engine: Engine, from_date: date, to_date: date) -> pd.DataFrame:
    """Return VIX daily bars between dates, indexed by date with open/high/low/close columns."""
    query = text("""
        SELECT BarDate, [Open], High, Low, [Close]
        FROM   mkt.VixBar
        WHERE  BarDate BETWEEN :from_d AND :to_d
        ORDER  BY BarDate
    """)
    with get_conn(engine) as conn:
        result = conn.execute(query, {"from_d": from_date, "to_d": to_date})
        df = pd.DataFrame(result.fetchall(), columns=result.keys())
    if not df.empty:
        df.columns = [c.lower() for c in df.columns]
        df = df.rename(columns={"bardate": "date"})
        df["date"] = pd.to_datetime(df["date"]).dt.date
        df = df.set_index("date")
        for col in ["open", "high", "low", "close"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def get_macro_bars(engine: Engine, from_date: date, to_date: date) -> pd.DataFrame:
    """Return macro bars between dates, indexed by date, with feature-ready column names."""
    query = text("""
        SELECT BarDate, Rate2Y, Rate10Y, Rate3M, Rate6M,
               Rate1Y, Rate5Y, Rate30Y, Sofr, JoblessClaims
        FROM   mkt.MacroBar
        WHERE  BarDate BETWEEN :from_d AND :to_d
        ORDER  BY BarDate
    """)
    with get_conn(engine) as conn:
        result = conn.execute(query, {"from_d": from_date, "to_d": to_date})
        df = pd.DataFrame(result.fetchall(), columns=result.keys())
    if not df.empty:
        df.columns = [c.lower() for c in df.columns]
        df = df.rename(columns={
            "bardate": "date", "rate2y": "rate_2y", "rate10y": "rate_10y",
            "rate3m": "rate_3m", "rate6m": "rate_6m", "rate1y": "rate_1y",
            "rate5y": "rate_5y", "rate30y": "rate_30y", "joblessclaims": "jobless_claims",
        })
        df["date"] = pd.to_datetime(df["date"]).dt.date
        df = df.set_index("date")
        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


# ── OptionSnapshot ────────────────────────────────────────────────────────────

def get_option_snapshots(engine: Engine, symbol: str,
                         snapshot_date: date) -> pd.DataFrame:
    """Return all option contracts for symbol on a given snapshot date."""
    tid = get_ticker_id(engine, symbol)
    if tid is None:
        return pd.DataFrame()
    query = text("""
        SELECT SnapshotDate AS snapshot_date,
               ExpirationDate AS expiration, Strike AS strike,
               ContractType AS contract_type,
               Bid AS bid, Ask AS ask, Mid AS mid, LastPrice AS last,
               ImpliedVol AS iv, Delta AS delta, Gamma AS gamma,
               Theta AS theta, Vega AS vega,
               OpenInterest AS open_interest, Volume AS volume
        FROM   mkt.OptionSnapshot
        WHERE  TickerId     = :tid
          AND  SnapshotDate = :snap
        ORDER  BY ExpirationDate, Strike, ContractType
    """)
    with get_conn(engine) as conn:
        result = conn.execute(query, {"tid": tid, "snap": snapshot_date})
        df = pd.DataFrame(result.fetchall(), columns=result.keys())
    if not df.empty:
        df.columns = [c.lower() for c in df.columns]
    return df


def upsert_option_snapshots(engine: Engine, symbol: str,
                             snapshot_date: date, df: pd.DataFrame) -> int:
    """
    Insert option snapshot rows, skipping duplicates.
    df must match Polygon options chain schema (see polygon_client.get_options_chain).
    Returns number of rows inserted.
    """
    if df.empty:
        return 0
    tid = ensure_ticker(engine, symbol)

    df = df.copy()
    df.columns = [c.lower() for c in df.columns]
    df["ticker_id"]     = tid
    df["snapshot_date"] = snapshot_date
    df["contract_type"] = df["type"].str.upper().str[:1]   # C | P
    _bid = pd.to_numeric(df["bid"], errors="coerce") if "bid" in df.columns else pd.Series(float("nan"), index=df.index)
    _ask = pd.to_numeric(df["ask"], errors="coerce") if "ask" in df.columns else pd.Series(float("nan"), index=df.index)
    # Mid is NULL when both sides are missing — don't substitute 0
    df["mid"] = (_bid + _ask) / 2

    for col in ["bid","ask","mid","last","iv","delta","gamma","theta","vega"]:
        if col not in df.columns:
            df[col] = None
    for col in ["open_interest","volume"]:
        if col not in df.columns:
            df[col] = None

    sql = text("""
        IF NOT EXISTS (
            SELECT 1 FROM mkt.OptionSnapshot
            WHERE  TickerId        = :ticker_id
              AND  SnapshotDate    = :snapshot_date
              AND  ExpirationDate  = :expiration
              AND  Strike          = :strike
              AND  ContractType    = :contract_type
        )
        INSERT INTO mkt.OptionSnapshot (
            TickerId, SnapshotDate, ExpirationDate, Strike, ContractType,
            Bid, Ask, Mid, LastPrice, ImpliedVol,
            Delta, Gamma, Theta, Vega, OpenInterest, Volume
        ) VALUES (
            :ticker_id, :snapshot_date, :expiration, :strike, :contract_type,
            :bid, :ask, :mid, :last, :iv,
            :delta, :gamma, :theta, :vega, :open_interest, :volume
        )
    """)

    cols = ["ticker_id","snapshot_date","expiration","strike","contract_type",
            "bid","ask","mid","last","iv","delta","gamma","theta","vega",
            "open_interest","volume"]

    # Map DataFrame columns to expected names
    rename = {"expiration_date": "expiration", "implied_volatility": "iv",
              "open_interest": "open_interest", "last_price": "last"}
    df = df.rename(columns=rename)

    _out = df[cols].copy()
    _out = _out.astype(object).where(pd.notnull(_out), other=None)
    rows = _out.to_dict("records")
    inserted = 0
    with engine.begin() as conn:
        for row in rows:
            result = conn.execute(sql, row)
            inserted += result.rowcount
    return inserted


def get_option_coverage(engine: Engine, symbol: str) -> Optional[tuple[date, date]]:
    """Return (min_date, max_date) of stored option snapshots, or None if empty."""
    tid = get_ticker_id(engine, symbol)
    if tid is None:
        return None
    with get_conn(engine) as conn:
        row = conn.execute(
            text("SELECT MIN(SnapshotDate), MAX(SnapshotDate) FROM mkt.OptionSnapshot WHERE TickerId = :tid"),
            {"tid": tid},
        ).fetchone()
    if row and row[0]:
        return row[0].date() if hasattr(row[0], 'date') else row[0], \
               row[1].date() if hasattr(row[1], 'date') else row[1]
    return None


# ── MacroBar ──────────────────────────────────────────────────────────────────

def upsert_macro_bars(engine: Engine, df: pd.DataFrame, progress_cb=None) -> int:
    """Insert macro rows, skipping duplicates. Accepts full macro df from fetch_macro().
    progress_cb(inserted, total) called every 50 rows if provided."""
    if df.empty:
        return 0
    df = df.copy()
    df.columns = [c.lower() for c in df.columns]
    if "date" not in df.columns and df.index.name == "date":
        df = df.reset_index()

    ALL_COLS = ["rate_2y","rate_10y","rate_3m","rate_6m","rate_1y","rate_5y","rate_30y",
                "sofr","jobless_claims"]
    for col in ALL_COLS:
        if col not in df.columns:
            df[col] = None

    df["yield_spread"]     = df["rate_10y"].fillna(0) - df["rate_2y"].fillna(0)
    df["curve_3m10y"]      = df["rate_10y"].fillna(0) - df["rate_3m"].fillna(0)
    df["curve_5y30y"]      = df["rate_30y"].fillna(0) - df["rate_5y"].fillna(0)
    df["curve_butterfly"]  = df["rate_2y"].fillna(0)  - \
                             (0.5 * df["rate_3m"].fillna(0) + 0.5 * df["rate_10y"].fillna(0))

    sql = text("""
        IF NOT EXISTS (SELECT 1 FROM mkt.MacroBar WHERE BarDate = :date)
        INSERT INTO mkt.MacroBar (
            BarDate, Rate2Y, Rate10Y, YieldSpread,
            Rate3M, Rate6M, Rate1Y, Rate5Y, Rate30Y,
            Curve3m10y, Curve5y30y, CurveButterfly,
            Sofr, JoblessClaims
        ) VALUES (
            :date, :rate_2y, :rate_10y, :yield_spread,
            :rate_3m, :rate_6m, :rate_1y, :rate_5y, :rate_30y,
            :curve_3m10y, :curve_5y30y, :curve_butterfly,
            :sofr, :jobless_claims
        )
    """)
    cols = ["date","rate_2y","rate_10y","yield_spread",
            "rate_3m","rate_6m","rate_1y","rate_5y","rate_30y",
            "curve_3m10y","curve_5y30y","curve_butterfly",
            "sofr","jobless_claims"]
    out = df[cols].copy()
    # Convert to object dtype so pandas NaN becomes None (not float nan)
    out = out.astype(object).where(pd.notnull(out), other=None)
    rows = out.to_dict("records")

    inserted = 0
    total = len(rows)
    with engine.begin() as conn:
        for i, row in enumerate(rows):
            result = conn.execute(sql, row)
            inserted += result.rowcount
            if progress_cb and (i + 1) % 50 == 0:
                progress_cb(i + 1, total, row.get("date"))
    if progress_cb:
        progress_cb(total, total, rows[-1].get("date") if rows else None)
    return inserted


# ── News ─────────────────────────────────────────────────────────────────────

def upsert_news(engine: Engine, symbol: str, df: pd.DataFrame,
                progress_cb=None) -> int:
    """
    Insert news articles, skipping duplicates by (TickerId, ArticleId).
    df columns: id (Polygon article id), published_utc, title, description.
    progress_cb(inserted, total) called every 50 rows if provided.
    """
    if df.empty:
        return 0
    tid = ensure_ticker(engine, symbol)
    df  = df.copy()
    df.columns = [c.lower() for c in df.columns]

    # Polygon news df may have 'id' or derive it from url
    if "id" not in df.columns:
        if "url" in df.columns:
            df["id"] = df["url"].apply(lambda u: str(hash(u))[:20] if u else "")
        elif "amp_url" in df.columns:
            df["id"] = df["amp_url"].apply(lambda u: str(hash(u))[:20] if u else "")
        else:
            df["id"] = (df.get("title", pd.Series([""] * len(df))).fillna("") +
                        df.get("published_utc", pd.Series([""] * len(df))).astype(str)
                        ).apply(lambda s: str(hash(s))[:20])

    if "description" not in df.columns:
        df["description"] = None
    # Coerce non-string description/title to None (NaN floats from Polygon)
    df["description"] = df["description"].apply(lambda v: v if isinstance(v, str) else None)
    if "title" in df.columns:
        df["title"] = df["title"].apply(lambda v: v if isinstance(v, str) else None)

    # Compute sentiment from title + description using VADER
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        _sia = SentimentIntensityAnalyzer()
        def _score(row):
            title = row.get("title") or ""
            desc  = row.get("description") or ""
            if not isinstance(title, str): title = ""
            if not isinstance(desc,  str): desc  = ""
            text = f"{title} {desc}".strip()
            return round(_sia.polarity_scores(text)["compound"], 4) if text else None
        df["sentiment"] = df.apply(_score, axis=1)
    except ImportError:
        df["sentiment"] = None

    df["ticker_id"]      = tid
    df["published_date"] = pd.to_datetime(df["published_utc"]).dt.date

    sql = text("""
        IF NOT EXISTS (
            SELECT 1 FROM mkt.News WHERE TickerId = :ticker_id AND ArticleId = :id
        )
            INSERT INTO mkt.News (TickerId, ArticleId, PublishedAt, PublishedDate, Title, Description, Sentiment)
            VALUES (:ticker_id, :id, :published_utc, :published_date, :title, :description, :sentiment)
        ELSE
            UPDATE mkt.News
               SET Sentiment = :sentiment
             WHERE TickerId = :ticker_id AND ArticleId = :id AND Sentiment IS NULL
    """)
    rows = df[["ticker_id","id","published_utc","published_date",
               "title","description","sentiment"]].to_dict("records")
    inserted = 0
    total = len(rows)
    with engine.begin() as conn:
        for i, row in enumerate(rows):
            result = conn.execute(sql, row)
            inserted += result.rowcount
            if progress_cb and (i + 1) % 50 == 0:
                progress_cb(i + 1, total)
    if progress_cb:
        progress_cb(total, total)
    return inserted


def get_news(engine: Engine, symbol: str,
             from_date: date, to_date: date) -> pd.DataFrame:
    """Return stored news articles for symbol between dates."""
    tid = get_ticker_id(engine, symbol)
    if tid is None:
        return pd.DataFrame()
    query = text("""
        SELECT PublishedDate, Title, Description, Sentiment
        FROM   mkt.News
        WHERE  TickerId = :tid
          AND  PublishedDate BETWEEN :from_d AND :to_d
        ORDER  BY PublishedDate
    """)
    with get_conn(engine) as conn:
        result = conn.execute(query, {"tid": tid, "from_d": from_date, "to_d": to_date})
        df = pd.DataFrame(result.fetchall(), columns=result.keys())
    if not df.empty:
        df.columns = [c.lower() for c in df.columns]
        df = df.rename(columns={"publisheddate": "date"})
        if "sentiment" in df.columns:
            df["sentiment"] = pd.to_numeric(df["sentiment"], errors="coerce")
    return df


# ── VixBar ────────────────────────────────────────────────────────────────────

def upsert_vix_bars(engine: Engine, df: pd.DataFrame, progress_cb=None) -> int:
    """Insert VIX bars, skipping duplicates.
    progress_cb(inserted, total) called every 50 rows if provided."""
    if df.empty:
        return 0
    df = df.copy()
    df.columns = [c.lower() for c in df.columns]
    if "date" not in df.columns and df.index.name == "date":
        df = df.reset_index()

    sql = text("""
        IF NOT EXISTS (SELECT 1 FROM mkt.VixBar WHERE BarDate = :date)
        INSERT INTO mkt.VixBar (BarDate, [Open], High, Low, [Close])
        VALUES (:date, :open, :high, :low, :close)
    """)
    rows = df[["date","open","high","low","close"]].to_dict("records")
    inserted = 0
    total = len(rows)
    with engine.begin() as conn:
        for i, row in enumerate(rows):
            result = conn.execute(sql, row)
            inserted += result.rowcount
            if progress_cb and (i + 1) % 50 == 0:
                progress_cb(i + 1, total, row.get("date"))
    if progress_cb:
        progress_cb(total, total, rows[-1].get("date") if rows else None)
    return inserted


# ── SyncLog ───────────────────────────────────────────────────────────────────

def get_last_sync_date(engine: Engine, data_type: str,
                       symbol: Optional[str] = None) -> Optional[date]:
    """Return the most recent LastSyncDate for a given data type + ticker."""
    tid = get_ticker_id(engine, symbol) if symbol else None
    query = text("""
        SELECT TOP 1 LastSyncDate
        FROM   mkt.SyncLog
        WHERE  DataType  = :dt
          AND  ErrorMessage IS NULL
          AND  (:tid IS NULL OR TickerId = :tid)
        ORDER  BY SyncedAt DESC
    """)
    with get_conn(engine) as conn:
        row = conn.execute(query, {"dt": data_type, "tid": tid}).fetchone()
    if row and row[0]:
        return row[0].date() if hasattr(row[0], 'date') else row[0]
    return None


def log_sync(engine: Engine, data_type: str, last_sync_date: date,
             rows_inserted: int = 0, symbol: Optional[str] = None,
             error: Optional[str] = None) -> None:
    """Record a sync event in SyncLog."""
    tid = get_ticker_id(engine, symbol) if symbol else None
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO mkt.SyncLog (TickerId, DataType, LastSyncDate, RowsInserted, ErrorMessage)
                VALUES (:tid, :dt, :last_date, :rows, :err)
            """),
            {"tid": tid, "dt": data_type, "last_date": last_sync_date,
             "rows": rows_inserted, "err": error},
        )


def get_missing_dates(engine: Engine, data_type: str, symbol: str,
                      start_date: date, end_date: date) -> list[date]:
    """
    Return trading dates between start_date and end_date that are not yet
    stored for the given data type and symbol.
    Uses PriceBar as the trading calendar reference.
    """
    tid = get_ticker_id(engine, symbol)
    if tid is None:
        return []

    if data_type == "OptionSnapshot":
        covered_query = text("""
            SELECT DISTINCT SnapshotDate FROM mkt.OptionSnapshot
            WHERE TickerId = :tid AND SnapshotDate BETWEEN :from_d AND :to_d
        """)
    else:
        covered_query = text("""
            SELECT DISTINCT BarDate FROM mkt.PriceBar
            WHERE TickerId = :tid AND BarDate BETWEEN :from_d AND :to_d
        """)

    with get_conn(engine) as conn:
        covered = set(
            row[0].date() if hasattr(row[0], 'date') else row[0]
            for row in conn.execute(covered_query,
                                    {"tid": tid, "from_d": start_date, "to_d": end_date})
        )
        # Trading calendar: use SPY price bars as reference
        cal_query = text("""
            SELECT DISTINCT pb.BarDate
            FROM   mkt.PriceBar pb
            JOIN   mkt.Ticker   t ON t.TickerId = pb.TickerId
            WHERE  t.Symbol = 'SPY'
              AND  pb.BarDate BETWEEN :from_d AND :to_d
            ORDER  BY pb.BarDate
        """)
        trading_days = [
            row[0].date() if hasattr(row[0], 'date') else row[0]
            for row in conn.execute(cal_query,
                                    {"from_d": start_date, "to_d": end_date})
        ]

    return [d for d in trading_days if d not in covered]
