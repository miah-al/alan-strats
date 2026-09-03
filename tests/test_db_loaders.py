from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
"""
tests/test_earnings_calendar_loader.py

Unit tests for db.client.get_earnings_calendar and its compatibility with the
five earnings-data strategies that consume it (earnings_pin_risk,
earnings_iv_crush, earnings_post_drift, earnings_vol_crush, news_sentiment_nlp).

The DB is mocked — these tests run without a SQL Server connection.

Run: python -m pytest tests/test_earnings_calendar_loader.py -v
"""

import os
import sys
from contextlib import contextmanager
from datetime import date
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── Mock helpers ─────────────────────────────────────────────────────────────

def _mock_engine_with_rows(rows, columns):
    """Build a MagicMock engine that returns the given rows for any execute()."""
    engine = MagicMock(name="engine")
    conn   = MagicMock(name="conn")

    @contextmanager
    def _conn_ctx(_eng=None):
        yield conn

    result = MagicMock(name="result")
    result.fetchall.return_value = rows
    result.keys.return_value     = columns
    conn.execute.return_value    = result
    return engine, conn


class TestGetEarningsCalendar:
    """Logic of db.client.get_earnings_calendar with mocked SQL results."""
    def test_returns_empty_when_ticker_unknown(self):
        from db.client import get_earnings_calendar
        with patch("db.client.get_ticker_id", return_value=None):
            df = get_earnings_calendar(MagicMock(), "ZZZZ",
                                       date(2024, 1, 1), date(2024, 12, 31))
        assert df.empty
    def test_returns_empty_on_zero_rows(self):
        from db.client import get_earnings_calendar
        engine, _conn = _mock_engine_with_rows(rows=[], columns=[
            "release_date", "eps_actual", "eps_estimate",
            "revenue_usd", "net_income_usd"
        ])
        with patch("db.client.get_ticker_id", return_value=42), \
             patch("db.client.get_conn") as mock_get_conn:
            mock_get_conn.return_value.__enter__.return_value = _conn
            df = get_earnings_calendar(engine, "AAPL",
                                       date(2024, 1, 1), date(2024, 12, 31))
        assert df.empty
    def test_columns_and_surprise_calc(self):
        """Loader output schema + eps_surprise = eps_actual − eps_estimate."""
        from db.client import get_earnings_calendar
        rows = [
            (pd.Timestamp("2024-02-01"), 1.50, 1.20, 100.0e9, 25.0e9),
            (pd.Timestamp("2024-05-02"), 1.40, 1.45, 110.0e9, 24.0e9),
            (pd.Timestamp("2024-08-01"), None, 1.30, 120.0e9, 26.0e9),  # eps_actual NULL
        ]
        cols = ["release_date", "eps_actual", "eps_estimate",
                "revenue_usd", "net_income_usd"]
        engine, conn = _mock_engine_with_rows(rows=rows, columns=cols)
        with patch("db.client.get_ticker_id", return_value=42), \
             patch("db.client.get_conn") as mock_get_conn:
            mock_get_conn.return_value.__enter__.return_value = conn
            df = get_earnings_calendar(engine, "AAPL",
                                       date(2024, 1, 1), date(2024, 12, 31))

        # Schema
        for c in ("ticker", "release_date", "date",
                  "eps_actual", "eps_estimate", "eps_surprise",
                  "revenue_usd", "net_income_usd"):
            assert c in df.columns, f"missing column {c!r}"

        # Ticker uppercased
        assert (df["ticker"] == "AAPL").all()

        # release_date and date alias
        assert pd.api.types.is_datetime64_any_dtype(df["release_date"])
        assert (df["release_date"] == df["date"]).all()

        # eps_surprise computed correctly; NaN when eps_actual is missing
        assert df.loc[0, "eps_surprise"] == pytest.approx(0.30)
        assert df.loc[1, "eps_surprise"] == pytest.approx(-0.05)
        assert pd.isna(df.loc[2, "eps_surprise"])

        # Numeric columns coerced
        assert pd.api.types.is_numeric_dtype(df["eps_actual"])
        assert pd.api.types.is_numeric_dtype(df["eps_estimate"])


class TestGetNewsSentimentDaily:
    """Daily aggregation of raw mkt.News rows into the strategy contract shape."""
    def test_aggregates_multiple_articles_per_day(self):
        from db import client as dbc

        raw_news = pd.DataFrame({
            "date":      pd.to_datetime([
                "2024-03-01", "2024-03-01", "2024-03-01",  # 3 articles
                "2024-03-02",                              # 1 article
                "2024-03-04", "2024-03-04",                # 2 articles
            ]),
            "title":     ["a"] * 6,
            "description": ["b"] * 6,
            "sentiment": [0.8, 0.6, 0.4,  -0.2,  0.0, 0.5],
        })

        with patch("db.client.get_news", return_value=raw_news):
            df = dbc.get_news_sentiment_daily(MagicMock(), "AAPL",
                                              date(2024, 3, 1), date(2024, 3, 31))

        # Schema
        for c in ("ticker", "sentiment_score", "article_count", "source_weight"):
            assert c in df.columns

        # 3 distinct days
        assert len(df) == 3

        # Mean per day
        assert df.loc[pd.Timestamp("2024-03-01"), "sentiment_score"] == pytest.approx(0.6)
        assert df.loc[pd.Timestamp("2024-03-02"), "sentiment_score"] == pytest.approx(-0.2)
        assert df.loc[pd.Timestamp("2024-03-04"), "sentiment_score"] == pytest.approx(0.25)

        # Counts
        assert df.loc[pd.Timestamp("2024-03-01"), "article_count"] == 3
        assert df.loc[pd.Timestamp("2024-03-02"), "article_count"] == 1
        assert df.loc[pd.Timestamp("2024-03-04"), "article_count"] == 2

        # All ticker values match
        assert (df["ticker"] == "AAPL").all()
    def test_empty_when_all_sentiment_null(self):
        from db import client as dbc
        raw_news = pd.DataFrame({
            "date":        pd.to_datetime(["2024-03-01", "2024-03-02"]),
            "title":       ["a", "b"],
            "description": [None, None],
            "sentiment":   [np.nan, np.nan],   # never scored
        })
        with patch("db.client.get_news", return_value=raw_news):
            df = dbc.get_news_sentiment_daily(MagicMock(), "AAPL",
                                              date(2024, 3, 1), date(2024, 3, 31))
        assert df.empty


class TestGetShortInterest:
    """Loader of bi-monthly FINRA-style snapshots."""
    def test_returns_empty_when_ticker_unknown(self):
        from db.client import get_short_interest
        with patch("db.client.get_ticker_id", return_value=None):
            df = get_short_interest(MagicMock(), "ZZZZ",
                                    date(2024, 1, 1), date(2024, 12, 31))
        assert df.empty
    def test_returns_empty_when_table_missing(self):
        """If mkt.ShortInterest doesn't exist (stale schema), loader returns
        empty rather than crashing — strategy then runs in fallback mode."""
        from db.client import get_short_interest

        engine, conn = _mock_engine_with_rows(rows=[], columns=[])
        conn.execute.side_effect = RuntimeError("Invalid object name 'mkt.ShortInterest'")

        with patch("db.client.get_ticker_id", return_value=42), \
             patch("db.client.get_conn") as mock_get_conn:
            mock_get_conn.return_value.__enter__.return_value = conn
            df = get_short_interest(engine, "GME",
                                    date(2024, 1, 1), date(2024, 12, 31))
        assert df.empty
    def test_returns_indexed_frame_with_strategy_columns(self):
        from db.client import get_short_interest
        rows = [
            (pd.Timestamp("2024-02-15"), 0.25, 4.5, 0.85),
            (pd.Timestamp("2024-02-29"), 0.30, 5.1, 0.90),
            (pd.Timestamp("2024-03-15"), 0.22, 3.8, 0.80),
        ]
        cols = ["SettlementDate", "short_interest_pct_float",
                "days_to_cover", "utilization"]
        engine, conn = _mock_engine_with_rows(rows=rows, columns=cols)
        with patch("db.client.get_ticker_id", return_value=42), \
             patch("db.client.get_conn") as mock_get_conn:
            mock_get_conn.return_value.__enter__.return_value = conn
            df = get_short_interest(engine, "GME",
                                    date(2024, 1, 1), date(2024, 12, 31))

        # Strategy contract: date-indexed with these three columns
        assert isinstance(df.index, pd.DatetimeIndex)
        for c in ("short_interest_pct_float", "days_to_cover", "utilization"):
            assert c in df.columns
            assert pd.api.types.is_numeric_dtype(df[c])
        assert len(df) == 3
        assert df.iloc[0]["short_interest_pct_float"] == pytest.approx(0.25)
