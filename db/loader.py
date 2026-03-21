"""
alan-strats  |  DB-based training data loader.

Loads all training data from SQL Server instead of calling Polygon/FRED APIs.
Returns the same dict structure as data.loader.load_real_data() so the rest
of the pipeline (features, trainer, backtest) is unchanged.
"""

import logging
from datetime import date, timedelta
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

DEFAULT_LOOKBACK_DAYS = 730  # 2 years — matches Polygon Options Starter plan


# ── Main loader ───────────────────────────────────────────────────────────────

def load_training_data(
    ticker: str = "HOOD",
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
) -> dict:
    """
    Load all training data from SQL Server.

    Returns dict with same keys as data.loader.load_real_data():
      "spy"     — daily OHLCV for the ticker (indexed by date)
      "vix"     — daily VIX OHLCV (indexed by date, 'close' column used)
      "rate2y"  — 2Y Treasury yield series (indexed by date, 'close' column)
      "rate10y" — 10Y Treasury yield series (indexed by date, 'close' column)
      "macro"   — full yield curve + SOFR + jobless claims (indexed by date)
      "news"    — news articles with pre-computed sentiment (flat DataFrame)
    """
    from alan_trader.db.client import (
        get_engine, get_price_bars, get_vix_bars, get_macro_bars, get_news,
    )

    engine    = get_engine()
    to_date   = to_date   or date.today()
    from_date = from_date or (to_date - timedelta(days=DEFAULT_LOOKBACK_DAYS))

    # ── Price bars ───────────────────────────────────────────────────────────
    price_df = get_price_bars(engine, ticker, from_date, to_date)
    if not price_df.empty:
        price_df["date"] = pd.to_datetime(price_df["date"]).dt.date
        price_df = price_df.set_index("date")
        price_df = _clean_price_bars(price_df, ticker)

    # ── VIX bars ─────────────────────────────────────────────────────────────
    vix_df = get_vix_bars(engine, from_date, to_date)

    # ── Macro bars ───────────────────────────────────────────────────────────
    macro_df = get_macro_bars(engine, from_date, to_date)

    # ── Separate rate series (for merge_rates compatibility) ─────────────────
    rate2y_df = rate10y_df = pd.DataFrame()
    if not macro_df.empty:
        if "rate_2y" in macro_df.columns:
            rate2y_df  = macro_df[["rate_2y"]].rename(columns={"rate_2y": "close"}).dropna()
        if "rate_10y" in macro_df.columns:
            rate10y_df = macro_df[["rate_10y"]].rename(columns={"rate_10y": "close"}).dropna()

    # ── News ─────────────────────────────────────────────────────────────────
    news_df = get_news(engine, ticker, from_date, to_date)

    return {
        "spy":     price_df,
        "vix":     vix_df,
        "rate2y":  rate2y_df,
        "rate10y": rate10y_df,
        "macro":   macro_df,
        "news":    news_df,
    }


# ── Data quality ──────────────────────────────────────────────────────────────

def _clean_price_bars(df: pd.DataFrame, ticker: str = "") -> pd.DataFrame:
    """Remove rows with invalid close prices."""
    n_before = len(df)
    df = df[(df["close"] > 0) & df["close"].notna()]
    dropped = n_before - len(df)
    if dropped:
        logger.warning(f"[{ticker}] Dropped {dropped} bad price bar rows (zero/null close)")
    return df


# ── Validation ────────────────────────────────────────────────────────────────

def validate_training_data(ticker: str = "HOOD") -> dict:
    """
    Check DB coverage for a ticker before training.

    Returns:
      {
        "ok":       bool,          # False if any blocking issues exist
        "issues":   [str],         # blockers — training will fail
        "warnings": [str],         # non-fatal — training degrades gracefully
        "coverage": {              # {label: (min_date, max_date, row_count)}
          "Price Bars": (...),
          "VIX Bars":   (...),
          ...
        }
      }
    """
    from alan_trader.db.client import get_engine, get_price_coverage, get_ticker_id
    from sqlalchemy import text

    engine   = get_engine()
    issues   = []
    warnings = []
    coverage = {}

    # ── Price bars ───────────────────────────────────────────────────────────
    price_cov = get_price_coverage(engine, ticker)
    if not price_cov:
        issues.append(f"No price bars for {ticker} — sync price bars first")
    else:
        tid = get_ticker_id(engine, ticker)
        with engine.connect() as conn:
            count = conn.execute(
                text("SELECT COUNT(*) FROM mkt.PriceBar WHERE TickerId = :tid"),
                {"tid": tid},
            ).scalar()
        coverage["Price Bars"] = (price_cov[0], price_cov[1], count)
        if count < 200:
            issues.append(f"Only {count} price bar rows — need ≥ 200 for training")

    # ── VIX bars ─────────────────────────────────────────────────────────────
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT MIN(BarDate), MAX(BarDate), COUNT(*) FROM mkt.VixBar")
        ).fetchone()
    if row and row[2] and row[2] > 0:
        coverage["VIX Bars"] = (row[0], row[1], row[2])
    else:
        warnings.append("No VIX data — VIX regime/IV-rank features will be zero/NaN")

    # ── Macro bars ───────────────────────────────────────────────────────────
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT MIN(BarDate), MAX(BarDate), COUNT(*) FROM mkt.MacroBar")
        ).fetchone()
    if row and row[2] and row[2] > 0:
        coverage["Macro Bars"] = (row[0], row[1], row[2])
    else:
        warnings.append("No macro data — yield curve / rate features will be zero/NaN")

    # ── News + sentiment ─────────────────────────────────────────────────────
    tid = get_ticker_id(engine, ticker)
    if tid:
        with engine.connect() as conn:
            row = conn.execute(text("""
                SELECT MIN(PublishedDate), MAX(PublishedDate),
                       COUNT(*),
                       SUM(CASE WHEN Sentiment IS NULL THEN 1 ELSE 0 END)
                FROM   mkt.News
                WHERE  TickerId = :tid
            """), {"tid": tid}).fetchone()
        if row and row[2] and row[2] > 0:
            coverage["News"] = (row[0], row[1], row[2])
            null_sent = int(row[3] or 0)
            if null_sent > 0:
                warnings.append(
                    f"{null_sent:,} news articles missing sentiment — re-sync news to score them"
                )
        else:
            warnings.append(f"No news for {ticker} — sentiment features will be zero")

    # ── Option chain ─────────────────────────────────────────────────────────
    from alan_trader.db.client import get_option_coverage
    opt_cov = get_option_coverage(engine, ticker)
    if opt_cov:
        _tid_opt = get_ticker_id(engine, ticker)
        with engine.connect() as conn:
            opt_count = conn.execute(
                text("SELECT COUNT(*) FROM mkt.OptionSnapshot WHERE TickerId = :tid"),
                {"tid": _tid_opt},
            ).scalar()
        coverage["Option Chain"] = (opt_cov[0], opt_cov[1], opt_count)
    else:
        coverage["Option Chain"] = ("MISSING", "MISSING", 0)
        warnings.append(
            f"No option chain data for {ticker} — strategies that use real option pricing "
            f"(e.g. TLT/SPY Rotation Options) will not be able to backtest. "
            f"Go to Data Manager → Options Snapshots to sync."
        )

    # ── Price bar gap check ───────────────────────────────────────────────────
    if "Price Bars" in coverage and coverage["Price Bars"][2] > 50:
        tid = get_ticker_id(engine, ticker)
        with engine.connect() as conn:
            gap_row = conn.execute(text("""
                SELECT TOP 1
                    DATEDIFF(day, LAG(BarDate) OVER (ORDER BY BarDate), BarDate) AS gap_days,
                    BarDate
                FROM   mkt.PriceBar
                WHERE  TickerId = :tid
                ORDER  BY gap_days DESC
            """), {"tid": tid}).fetchone()
        if gap_row and gap_row[0] and gap_row[0] > 7:
            warnings.append(
                f"Largest price bar gap: {gap_row[0]} calendar days ending {gap_row[1]}"
            )

    return {
        "ok":       len(issues) == 0,
        "issues":   issues,
        "warnings": warnings,
        "coverage": coverage,
    }
