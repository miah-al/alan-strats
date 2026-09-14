"""
alan-strats  |  SQL Server database client.
Handles connection, upserts, and incremental sync tracking.
"""

import os
import logging
from contextlib import contextmanager
from datetime import date, datetime, timedelta
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


# Module-level engine cache — one engine per (server, database) pair.
# create_engine() is cheap but pyodbc connection pool setup is not.
_ENGINE_CACHE: dict[tuple, Engine] = {}


def get_engine(server: str = _DEFAULT_SERVER,
               database: str = _DEFAULT_DB) -> Engine:
    key = (server, database)
    if key not in _ENGINE_CACHE:
        conn_str = _build_connection_string(server, database)
        _ENGINE_CACHE[key] = create_engine(
            conn_str,
            fast_executemany=True,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
        )
    return _ENGINE_CACHE[key]


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
            # IF NOT EXISTS…INSERT returns rowcount -1 for the skipped (already
            # present) case; clamp so the "rows inserted" tally never goes
            # negative (otherwise the Sync UI shows nonsense like "-404 rows").
            inserted += max(result.rowcount, 0)
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


# ── Dividends ─────────────────────────────────────────────────────────────────

def get_dividends(engine: Engine, symbol: str,
                  from_date: date, to_date: date) -> pd.DataFrame:
    """Return dividend history for symbol — ex_date and div_per_share."""
    tid = get_ticker_id(engine, symbol)
    if tid is None:
        return pd.DataFrame()
    query = text("""
        SELECT ExDate AS ex_date, CashAmount AS div_per_share
        FROM   mkt.Dividend
        WHERE  TickerId = :tid
          AND  ExDate BETWEEN :from_d AND :to_d
        ORDER  BY ExDate
    """)
    with get_conn(engine) as conn:
        result = conn.execute(query, {"tid": tid, "from_d": from_date, "to_d": to_date})
        df = pd.DataFrame(result.fetchall(), columns=result.keys())
    if not df.empty:
        df["ex_date"] = pd.to_datetime(df["ex_date"]).dt.date
        df["div_per_share"] = pd.to_numeric(df["div_per_share"], errors="coerce")
        df = df.dropna(subset=["div_per_share"])
    return df


# ── Earnings calendar ─────────────────────────────────────────────────────────

def get_earnings_calendar(engine: Engine, symbol: str,
                          from_date: date, to_date: date) -> pd.DataFrame:
    """Return earnings announcements for `symbol` between dates.

    Date precedence: FiledDate (SEC filing date — best available in the current
    schema) ▸ PeriodOfReport (fiscal period end — least accurate). Strategies
    should treat `release_date` as the trading-day timestamp of the announcement.
    (There is no AnnouncementDate column in mkt.Earnings; FiledDate is the
    closest proxy for the actual release date.)

    Returned columns:
        ticker          uppercase symbol
        release_date    pd.Timestamp — announcement / best-available date
        date            alias of release_date (for legacy strategies)
        eps_actual      reported EPS (nullable)
        eps_estimate    consensus EPS estimate (nullable)
        eps_surprise    eps_actual - eps_estimate (nullable)
        revenue_usd     quarterly revenue (nullable)
        net_income_usd  quarterly net income (nullable)

    Returns an empty DataFrame if the ticker is unknown or no rows match.
    """
    tid = get_ticker_id(engine, symbol)
    if tid is None:
        return pd.DataFrame()
    # NB: mkt.Earnings has no AnnouncementDate column — the best-available
    # release date is FiledDate (SEC filing date), falling back to
    # PeriodOfReport (fiscal-period end) when the filing date is null.
    query = text("""
        SELECT
            COALESCE(FiledDate, PeriodOfReport) AS release_date,
            EpsBasic        AS eps_actual,
            EpsEstimate     AS eps_estimate,
            RevenueUSD      AS revenue_usd,
            NetIncomeUSD    AS net_income_usd
        FROM   mkt.Earnings
        WHERE  TickerId = :tid
          AND  COALESCE(FiledDate, PeriodOfReport)
                 BETWEEN :from_d AND :to_d
        ORDER  BY release_date
    """)
    with get_conn(engine) as conn:
        result = conn.execute(query, {"tid": tid, "from_d": from_date, "to_d": to_date})
        df = pd.DataFrame(result.fetchall(), columns=result.keys())
    if df.empty:
        return pd.DataFrame()
    df.columns       = [c.lower() for c in df.columns]
    df["ticker"]     = symbol.upper()
    df["release_date"] = pd.to_datetime(df["release_date"])
    df["date"]       = df["release_date"]
    for c in ("eps_actual", "eps_estimate", "revenue_usd", "net_income_usd"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df["eps_surprise"] = df["eps_actual"] - df["eps_estimate"]
    return df[["ticker", "release_date", "date",
               "eps_actual", "eps_estimate", "eps_surprise",
               "revenue_usd", "net_income_usd"]]


# ── Short interest ────────────────────────────────────────────────────────────

def get_short_interest(engine: Engine, symbol: str,
                       from_date: date, to_date: date) -> pd.DataFrame:
    """Return bi-monthly (or daily, depending on feed) short-interest snapshots.

    Output is shaped for direct use as `auxiliary_data["short_interest"]` by
    the short_squeeze_detector strategy:

        index                       pd.DatetimeIndex (SettlementDate)
        short_interest_pct_float    short interest / public float (0..1+)
        days_to_cover               short interest / avg daily volume
        utilization                 borrowed shares / lendable supply (0..1)

    Returns an empty DataFrame if the ticker is unknown or no rows match —
    the strategy then runs in its 7-feature fallback mode without crashing.
    """
    tid = get_ticker_id(engine, symbol)
    if tid is None:
        return pd.DataFrame()
    query = text("""
        SELECT  SettlementDate,
                ShortInterestPctFloat AS short_interest_pct_float,
                DaysToCover           AS days_to_cover,
                Utilization           AS utilization
        FROM    mkt.ShortInterest
        WHERE   TickerId = :tid
          AND   SettlementDate BETWEEN :from_d AND :to_d
        ORDER   BY SettlementDate
    """)
    try:
        with get_conn(engine) as conn:
            result = conn.execute(query, {"tid": tid, "from_d": from_date, "to_d": to_date})
            df = pd.DataFrame(result.fetchall(), columns=result.keys())
    except Exception as exc:
        # Table may not exist on stale schemas — treat as "no data" rather than crash.
        logger.debug(f"get_short_interest: query failed ({exc}); returning empty")
        return pd.DataFrame()
    if df.empty:
        return df
    df.columns = [c.lower() for c in df.columns]
    df = df.rename(columns={"settlementdate": "date"})
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    for c in ("short_interest_pct_float", "days_to_cover", "utilization"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
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
        # SQL Server returns NUMERIC/DECIMAL columns as decimal.Decimal objects.
        # Cast all numeric-like columns to float so arithmetic works in pandas.
        _numeric_cols = ["strike", "bid", "ask", "mid", "last", "iv",
                         "delta", "gamma", "theta", "vega"]
        for col in _numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def upsert_option_snapshots(engine: Engine, symbol: str,
                             snapshot_date: date, df: pd.DataFrame,
                             overwrite: bool = False) -> int:
    """
    Insert option snapshot rows, skipping duplicates.

    `overwrite=False` (default) is insert-only: an existing (ticker, date,
    expiry, strike, type) row is left untouched. That is right for incremental
    syncs, but it means a re-sync can never CORRECT a stored value — which is
    why `sync_option_snapshots(force=True)` appeared to succeed while changing
    nothing: it re-fetched and re-computed every row, then discarded the result
    at this insert. It also means `force`'s documented "backfill greeks on
    previously-synced dates" never worked.

    `overwrite=True` updates the priced columns in place, for exactly that
    corrective case (e.g. after the option-IV clock fix in db/sync.py).

    df must match Polygon options chain schema (see polygon_client.get_options_chain).
    Returns number of rows inserted or updated.
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

    if overwrite:
        # Standard SQL Server upsert: try the UPDATE first, INSERT only if the
        # row was absent. Keeps the natural key stable while letting a
        # corrective re-sync actually replace stale prices/greeks.
        sql = text("""
            UPDATE mkt.OptionSnapshot
               SET Bid = :bid, Ask = :ask, Mid = :mid, LastPrice = :last,
                   ImpliedVol = :iv, Delta = :delta, Gamma = :gamma,
                   Theta = :theta, Vega = :vega,
                   OpenInterest = :open_interest, Volume = :volume
             WHERE TickerId       = :ticker_id
               AND SnapshotDate   = :snapshot_date
               AND ExpirationDate = :expiration
               AND Strike         = :strike
               AND ContractType   = :contract_type;
            IF @@ROWCOUNT = 0
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
    else:
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
            inserted += max(result.rowcount, 0)
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
            # IF NOT EXISTS…INSERT returns rowcount -1 for the skipped (already
            # present) case; clamp so the "rows inserted" tally never goes
            # negative (otherwise the Sync UI shows nonsense like "-404 rows").
            inserted += max(result.rowcount, 0)
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
            inserted += max(result.rowcount, 0)
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


def get_news_sentiment_daily(engine: Engine, symbol: str,
                              from_date: date, to_date: date) -> pd.DataFrame:
    """Return per-day aggregated sentiment for `symbol` between dates.

    Aggregates raw `mkt.News` rows into the shape the news_sentiment_nlp
    strategy expects via ``auxiliary_data["news_sentiment"]``:

        index           pd.DatetimeIndex (one row per published date)
        ticker          uppercase symbol
        sentiment_score mean of mkt.News.Sentiment (VADER, [-1, +1])
                        for the day; NaN-rows ignored
        article_count   number of scored articles that day
        source_weight   1.0 (mkt.News does not yet track provider quality;
                        upgrade this loader when source-weighting is added)

    Returns an empty DataFrame if the ticker is unknown, no rows match,
    or every article in range has NULL sentiment.
    """
    raw = get_news(engine, symbol, from_date, to_date)
    if raw.empty or "sentiment" not in raw.columns:
        return pd.DataFrame()
    scored = raw.dropna(subset=["sentiment"]).copy()
    if scored.empty:
        return pd.DataFrame()
    scored["date"] = pd.to_datetime(scored["date"])
    daily = scored.groupby("date").agg(
        sentiment_score=("sentiment", "mean"),
        article_count=("sentiment", "size"),
    )
    daily["source_weight"] = 1.0
    daily["ticker"]        = symbol.upper()
    daily.index.name       = "date"
    return daily[["ticker", "sentiment_score", "article_count", "source_weight"]]


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
            # IF NOT EXISTS…INSERT returns rowcount -1 for the skipped (already
            # present) case; clamp so the "rows inserted" tally never goes
            # negative (otherwise the Sync UI shows nonsense like "-404 rows").
            inserted += max(result.rowcount, 0)
            if progress_cb and (i + 1) % 50 == 0:
                progress_cb(i + 1, total, row.get("date"))
    if progress_cb:
        progress_cb(total, total, rows[-1].get("date") if rows else None)
    return inserted


# ── MinuteBar ─────────────────────────────────────────────────────────────────

def replace_minute_bars(engine: Engine, symbol: str, df: pd.DataFrame,
                        source: str = "polygon", asset_class: str = "index") -> int:
    """Write 1-minute bars for symbol, replacing whatever the table holds in
    df's [min ts, max ts] range. df columns: ts (naive US/Eastern bar START),
    open, high, low, close, optional volume. Returns rows written."""
    if df is None or df.empty:
        return 0
    tid = ensure_ticker(engine, symbol, asset_class=asset_class)
    df = df.copy()
    df.columns = [c.lower() for c in df.columns]
    df["ts"] = pd.to_datetime(df["ts"])
    df = df.sort_values("ts").drop_duplicates("ts")
    if "volume" not in df.columns:
        df["volume"] = None
    lo, hi = df["ts"].min().to_pydatetime(), df["ts"].max().to_pydatetime()
    rows = [(tid, r.ts.to_pydatetime(), float(r.open), float(r.high), float(r.low), float(r.close),
             (int(r.volume) if pd.notna(r.volume) else None), source)
            for r in df.itertuples(index=False)]
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM mkt.MinuteBar WHERE TickerId = :tid AND BarTs BETWEEN :lo AND :hi"),
                     {"tid": tid, "lo": lo, "hi": hi})
        cur = conn.connection.cursor()
        cur.fast_executemany = True
        cur.executemany(
            "INSERT INTO mkt.MinuteBar (TickerId, BarTs, [Open], High, Low, [Close], Volume, Source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
    return len(rows)


def get_minute_bars(engine: Engine, symbol: str,
                    from_date: Optional[date] = None,
                    to_date: Optional[date] = None) -> pd.DataFrame:
    """1-minute bars for symbol: ts (naive US/Eastern bar START), open, high, low,
    close, volume. Dates inclusive. Empty frame when the ticker or rows are missing."""
    cols = ["ts", "open", "high", "low", "close", "volume"]
    tid = get_ticker_id(engine, symbol)
    if tid is None:
        return pd.DataFrame(columns=cols)
    q = ("SELECT BarTs AS ts, [Open] AS [open], High AS high, Low AS low, [Close] AS [close], Volume AS volume "
         "FROM mkt.MinuteBar WHERE TickerId = :tid")
    params: dict = {"tid": tid}
    if from_date is not None:
        q += " AND BarTs >= :lo"; params["lo"] = datetime.combine(from_date, datetime.min.time())
    if to_date is not None:
        q += " AND BarTs < :hi"; params["hi"] = datetime.combine(to_date + timedelta(days=1), datetime.min.time())
    q += " ORDER BY BarTs"
    with get_conn(engine) as conn:
        result = conn.execute(text(q), params)
        df = pd.DataFrame(result.fetchall(), columns=result.keys())
    if df.empty:
        return pd.DataFrame(columns=cols)
    df["ts"] = pd.to_datetime(df["ts"])
    for c in ("open", "high", "low", "close"):
        df[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
    return df


def get_minute_bar_coverage(engine: Engine, symbol: str) -> Optional[tuple[date, date, int]]:
    """(first session, last session, number of sessions) with minute bars, or None."""
    tid = get_ticker_id(engine, symbol)
    if tid is None:
        return None
    with get_conn(engine) as conn:
        row = conn.execute(text(
            "SELECT MIN(BarTs), MAX(BarTs), COUNT(DISTINCT CAST(BarTs AS date)) "
            "FROM mkt.MinuteBar WHERE TickerId = :tid"), {"tid": tid}).fetchone()
    if row is None or row[0] is None:
        return None
    return row[0].date(), row[1].date(), int(row[2])


def get_minute_bar_months(engine: Engine, symbol: str) -> set[tuple[int, int]]:
    """{(year, month)} that already hold minute bars for symbol."""
    tid = get_ticker_id(engine, symbol)
    if tid is None:
        return set()
    with get_conn(engine) as conn:
        rows = conn.execute(text(
            "SELECT DISTINCT YEAR(BarTs), MONTH(BarTs) FROM mkt.MinuteBar WHERE TickerId = :tid"),
            {"tid": tid}).fetchall()
    return {(int(y), int(m)) for y, m in rows}


# ── EventCalendar ─────────────────────────────────────────────────────────────

# ── OptionMinuteBar (per-contract 1-minute trade aggregates) ─────────────────

_OMB_COLS = ["expiry", "right", "strike", "ts", "open", "high", "low", "close", "volume", "trades", "vwap"]


def get_minute_bar_sessions(engine: Engine, symbol: str,
                            from_date: Optional[date] = None,
                            to_date: Optional[date] = None) -> list[date]:
    """Distinct session dates with 1-minute bars for symbol, ascending, dates inclusive."""
    tid = get_ticker_id(engine, symbol)
    if tid is None:
        return []
    q = "SELECT DISTINCT CAST(BarTs AS date) AS d FROM mkt.MinuteBar WHERE TickerId = :tid"
    params: dict = {"tid": tid}
    if from_date is not None:
        q += " AND BarTs >= :lo"; params["lo"] = datetime.combine(from_date, datetime.min.time())
    if to_date is not None:
        q += " AND BarTs < :hi"; params["hi"] = datetime.combine(to_date + timedelta(days=1), datetime.min.time())
    q += " ORDER BY d"
    with get_conn(engine) as conn:
        rows = conn.execute(text(q), params).fetchall()
    return [r[0] if isinstance(r[0], date) else pd.Timestamp(r[0]).date() for r in rows]


def replace_option_minute_bars(engine: Engine, symbol: str, expiry: date, df: pd.DataFrame,
                               root: str = "NDXP", source: str = "polygon",
                               asset_class: str = "index") -> int:
    """Write per-contract 1-minute bars for ONE expiry of the underlying `symbol`,
    replacing every row the table holds for that (underlying, expiry). df columns:
    right (C|P), strike, ts (naive US/Eastern bar START), open, high, low, close,
    optional volume, trades, vwap. Returns rows written."""
    tid = ensure_ticker(engine, symbol, asset_class=asset_class)
    rows: list = []
    if df is not None and not df.empty:
        d = df.copy()
        d.columns = [c.lower() for c in d.columns]
        for c in ("volume", "trades", "vwap"):
            if c not in d.columns:
                d[c] = None
        d["ts"] = pd.to_datetime(d["ts"])
        d = d.sort_values(["right", "strike", "ts"]).drop_duplicates(["right", "strike", "ts"])
        rows = [(tid, expiry, str(r.right).upper()[0], float(r.strike), r.ts.to_pydatetime(),
                 float(r.open), float(r.high), float(r.low), float(r.close),
                 (int(r.volume) if pd.notna(r.volume) else None),
                 (int(r.trades) if pd.notna(r.trades) else None),
                 (float(r.vwap) if pd.notna(r.vwap) else None), root, source)
                for r in d.itertuples(index=False)]
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM mkt.OptionMinuteBar WHERE TickerId = :tid AND ExpirationDate = :exp"),
                     {"tid": tid, "exp": expiry})
        if rows:
            cur = conn.connection.cursor()
            cur.fast_executemany = True
            cur.executemany(
                "INSERT INTO mkt.OptionMinuteBar (TickerId, ExpirationDate, ContractType, Strike, BarTs, "
                "[Open], High, Low, [Close], Volume, Trades, Vwap, Root, Source) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    return len(rows)


def get_option_minute_bars(engine: Engine, symbol: str,
                           from_date: Optional[date] = None,
                           to_date: Optional[date] = None,
                           expiry: Optional[date] = None,
                           strikes: Optional[list[float]] = None) -> pd.DataFrame:
    """Per-contract 1-minute bars for the underlying `symbol`: expiry, right, strike, ts,
    open, high, low, close, volume, trades, vwap. Bar dates inclusive; optional expiry and
    strike-list filters. Empty frame when nothing is stored."""
    tid = get_ticker_id(engine, symbol)
    if tid is None:
        return pd.DataFrame(columns=_OMB_COLS)
    q = ("SELECT ExpirationDate AS expiry, ContractType AS [right], Strike AS strike, BarTs AS ts, "
         "[Open] AS [open], High AS high, Low AS low, [Close] AS [close], Volume AS volume, "
         "Trades AS trades, Vwap AS vwap FROM mkt.OptionMinuteBar WHERE TickerId = :tid")
    params: dict = {"tid": tid}
    if from_date is not None:
        q += " AND BarTs >= :lo"; params["lo"] = datetime.combine(from_date, datetime.min.time())
    if to_date is not None:
        q += " AND BarTs < :hi"; params["hi"] = datetime.combine(to_date + timedelta(days=1), datetime.min.time())
    if expiry is not None:
        q += " AND ExpirationDate = :exp"; params["exp"] = expiry
    if strikes:
        names = []
        for i, k in enumerate(strikes):
            names.append(f":k{i}"); params[f"k{i}"] = float(k)
        q += f" AND Strike IN ({', '.join(names)})"
    q += " ORDER BY ExpirationDate, ContractType, Strike, BarTs"
    with get_conn(engine) as conn:
        result = conn.execute(text(q), params)
        df = pd.DataFrame(result.fetchall(), columns=result.keys())
    if df.empty:
        return pd.DataFrame(columns=_OMB_COLS)
    df["ts"] = pd.to_datetime(df["ts"])
    df["expiry"] = pd.to_datetime(df["expiry"]).dt.date
    df["right"] = df["right"].astype(str).str.strip()
    for c in ("strike", "open", "high", "low", "close", "vwap"):
        df[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
    for c in ("volume", "trades"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df[_OMB_COLS]


def upsert_option_minute_session(engine: Engine, symbol: str, session: date, expiry: date, *,
                                 root: str, ref_level: Optional[float], strike_lo: Optional[float],
                                 strike_hi: Optional[float], strike_step: Optional[int],
                                 contracts: int, with_prints: int, bars: int,
                                 source: str = "polygon", asset_class: str = "index") -> None:
    """Record (or replace) the pull manifest row for one (underlying, session, expiry)."""
    tid = ensure_ticker(engine, symbol, asset_class=asset_class)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM mkt.OptionMinuteSession WHERE TickerId = :tid AND SessionDate = :s "
                          "AND ExpirationDate = :e"), {"tid": tid, "s": session, "e": expiry})
        conn.execute(text(
            "INSERT INTO mkt.OptionMinuteSession (TickerId, SessionDate, ExpirationDate, Root, RefLevel, StrikeLo, "
            "StrikeHi, StrikeStep, Contracts, ContractsWithPrints, Bars, Source) VALUES (:tid, :s, :e, :root, :ref, "
            ":lo, :hi, :step, :n, :np, :bars, :src)"),
            {"tid": tid, "s": session, "e": expiry, "root": root, "ref": ref_level, "lo": strike_lo,
             "hi": strike_hi, "step": strike_step, "n": int(contracts), "np": int(with_prints),
             "bars": int(bars), "src": source})


def get_option_minute_sessions(engine: Engine, symbol: str) -> pd.DataFrame:
    """The pull manifest for symbol: session, expiry, root, ref_level, strike_lo, strike_hi,
    strike_step, contracts, with_prints, bars, pulled_at (ascending by session)."""
    cols = ["session", "expiry", "root", "ref_level", "strike_lo", "strike_hi", "strike_step",
            "contracts", "with_prints", "bars", "pulled_at"]
    tid = get_ticker_id(engine, symbol)
    if tid is None:
        return pd.DataFrame(columns=cols)
    with get_conn(engine) as conn:
        result = conn.execute(text(
            "SELECT SessionDate, ExpirationDate, Root, RefLevel, StrikeLo, StrikeHi, StrikeStep, Contracts, "
            "ContractsWithPrints, Bars, PulledAt FROM mkt.OptionMinuteSession WHERE TickerId = :tid "
            "ORDER BY SessionDate, ExpirationDate"), {"tid": tid})
        df = pd.DataFrame(result.fetchall(), columns=cols)
    if df.empty:
        return pd.DataFrame(columns=cols)
    for c in ("session", "expiry"):
        df[c] = pd.to_datetime(df[c]).dt.date
    for c in ("ref_level", "strike_lo", "strike_hi"):
        df[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
    return df


def get_option_minute_coverage(engine: Engine, symbol: str) -> Optional[dict]:
    """{'first', 'last', 'sessions', 'contracts', 'bars'} over mkt.OptionMinuteBar for symbol, or None."""
    tid = get_ticker_id(engine, symbol)
    if tid is None:
        return None
    with get_conn(engine) as conn:
        row = conn.execute(text(
            "SELECT MIN(ExpirationDate), MAX(ExpirationDate), COUNT(DISTINCT ExpirationDate), "
            "COUNT(DISTINCT CONCAT(ExpirationDate, ContractType, Strike)), COUNT(*) "
            "FROM mkt.OptionMinuteBar WHERE TickerId = :tid"), {"tid": tid}).fetchone()
    if row is None or row[0] is None:
        return None
    return {"first": row[0], "last": row[1], "sessions": int(row[2]), "contracts": int(row[3]), "bars": int(row[4])}


def replace_event_calendar(engine: Engine, rows: list[dict]) -> int:
    """Replace mkt.EventCalendar with rows of {'date','kind','label','source'}."""
    data = [(pd.Timestamp(r["date"]).date(), str(r["kind"]).strip().lower()[:20],
             (r.get("label") or "")[:200], (r.get("source") or "")[:100]) for r in rows if r.get("date")]
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM mkt.EventCalendar"))
        if data:
            cur = conn.connection.cursor()
            cur.fast_executemany = True
            cur.executemany("INSERT INTO mkt.EventCalendar (EventDate, Kind, Label, Source) VALUES (?, ?, ?, ?)", data)
    return len(data)


def get_event_calendar(engine: Engine, from_date: Optional[date] = None,
                       to_date: Optional[date] = None) -> pd.DataFrame:
    """Event flags: columns date, kind, label, source. Empty frame when none."""
    cols = ["date", "kind", "label", "source"]
    q = "SELECT EventDate AS [date], Kind AS kind, Label AS label, Source AS source FROM mkt.EventCalendar"
    where, params = [], {}
    if from_date is not None:
        where.append("EventDate >= :lo"); params["lo"] = from_date
    if to_date is not None:
        where.append("EventDate <= :hi"); params["hi"] = to_date
    if where:
        q += " WHERE " + " AND ".join(where)
    q += " ORDER BY EventDate, Kind"
    with get_conn(engine) as conn:
        result = conn.execute(text(q), params)
        df = pd.DataFrame(result.fetchall(), columns=result.keys())
    if df.empty:
        return pd.DataFrame(columns=cols)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


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
