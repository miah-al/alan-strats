"""
tests/test_earnings_calendar_loader.py

Unit tests for db.client.get_earnings_calendar and its compatibility with the
five earnings-data strategies that consume it (earnings_pin_risk,
earnings_iv_crush, earnings_post_drift, earnings_vol_crush, news_sentiment_nlp).

The DB is mocked — these tests run without a SQL Server connection.

Run: python -m pytest tests/test_earnings_calendar_loader.py -v
"""
from __future__ import annotations

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


# ── Tests for get_earnings_calendar ───────────────────────────────────────────

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


# ── Loader-output ↔ strategy contract tests ──────────────────────────────────

class TestLoaderStrategyContract:
    """The DataFrame shape produced by the loader must satisfy each strategy."""

    @staticmethod
    def _synth_loader_df(release_dates, ticker="ABC"):
        """Produce a DataFrame matching get_earnings_calendar's exact schema."""
        n = len(release_dates)
        eps_actual   = [1.0 + 0.05 * i for i in range(n)]
        eps_estimate = [0.95 + 0.05 * i for i in range(n)]
        df = pd.DataFrame({
            "ticker":       [ticker.upper()] * n,
            "release_date": pd.to_datetime(release_dates),
            "date":         pd.to_datetime(release_dates),
            "eps_actual":   eps_actual,
            "eps_estimate": eps_estimate,
            "eps_surprise": [a - e for a, e in zip(eps_actual, eps_estimate)],
            "revenue_usd":  [100e9 + 5e9 * i for i in range(n)],
            "net_income_usd": [25e9 + 1e9 * i for i in range(n)],
        })
        return df

    @staticmethod
    def _synth_prices(n_days=400, start="2023-01-02", seed=7):
        rng = np.random.default_rng(seed)
        idx = pd.bdate_range(start=start, periods=n_days)
        rets = rng.normal(0.0003, 0.012, n_days)
        close = 100.0 * np.exp(np.cumsum(rets))
        df = pd.DataFrame({
            "open":  close * (1 + rng.normal(0, 0.001, n_days)),
            "high":  close * 1.005,
            "low":   close * 0.995,
            "close": close,
            "volume": rng.integers(1_000_000, 5_000_000, n_days),
        }, index=idx)
        return df

    def test_pin_risk_accepts_loader_shape(self):
        """earnings_pin_risk.backtest accepts the loader DataFrame unmodified."""
        from strategies.earnings_pin_risk import EarningsPinRiskStrategy

        prices = self._synth_prices(n_days=400)
        # 4 earnings events in the price window
        rels = [prices.index[110], prices.index[180],
                prices.index[260], prices.index[340]]
        cal  = self._synth_loader_df(rels, ticker="ABC")

        s = EarningsPinRiskStrategy(
            pin_threshold=0.05, ivr_max=1.0, vix_max=99.0,
            position_size_pct=0.02,
        )
        res = s.backtest(prices, {"earnings_calendar": cal},
                         ticker="ABC", starting_capital=100_000)
        # Equity curve well-formed
        assert res.equity_curve is not None
        assert len(res.equity_curve) == len(prices)
        assert res.equity_curve.notna().all()
        # No look-ahead — exit dates strictly after release dates for all closed trades
        if not res.trades.empty:
            for _, t in res.trades.iterrows():
                assert pd.Timestamp(t["exit_date"]) > pd.Timestamp(t["release_date"]), \
                    f"trade exits on/before its release: {t.to_dict()}"

    def test_iv_crush_accepts_loader_shape(self):
        """earnings_iv_crush reads 'date' column → loader's alias works."""
        from strategies.earnings_iv_crush import EarningsIVCrushStrategy

        prices = self._synth_prices(n_days=400)
        rels = [prices.index[150], prices.index[230], prices.index[320]]
        cal  = self._synth_loader_df(rels, ticker="ABC")

        s = EarningsIVCrushStrategy()
        res = s.backtest(
            prices,
            {"earnings": cal,
             "stock_prices": {"ABC": prices}},
            starting_capital=100_000,
        )
        # Strategy must not crash; equity curve well-formed.
        assert res.equity_curve is not None
        assert len(res.equity_curve) == len(prices)

    def test_post_drift_accepts_loader_shape(self):
        from strategies.earnings_post_drift import EarningsPostDriftStrategy

        prices = self._synth_prices(n_days=400)
        rels = [prices.index[150], prices.index[230], prices.index[320]]
        cal  = self._synth_loader_df(rels, ticker="ABC")

        s = EarningsPostDriftStrategy()
        res = s.backtest(
            prices,
            {"earnings": cal,
             "stock_prices": {"ABC": prices}},
            starting_capital=100_000,
        )
        assert res.equity_curve is not None
        assert len(res.equity_curve) == len(prices)

    def test_news_sentiment_accepts_series_form(self):
        """news_sentiment_nlp expects a Series indexed by release_date."""
        prices = self._synth_prices(n_days=400)
        rels = [prices.index[150], prices.index[230], prices.index[320]]
        cal_series = pd.Series(1.0, index=pd.to_datetime(rels))
        # Just exercise the index-iteration code path — full strategy backtest
        # requires news_sentiment data which is out of scope for this test.
        from strategies.news_sentiment_nlp import _build_feature_matrix

        sentiment = pd.DataFrame({
            "sentiment_score": np.zeros(len(prices)),
            "article_count":   np.ones(len(prices)),
        }, index=prices.index)
        vix = pd.Series(20.0, index=prices.index)
        feats = _build_feature_matrix(
            close=prices["close"],
            volume=prices["volume"].astype(float),
            vix=vix,
            sentiment=sentiment,
            earnings_calendar=cal_series,
        )
        assert "days_to_next_earnings" in feats.columns
        # Days-to-earnings should be finite and non-negative everywhere
        dte = feats["days_to_next_earnings"]
        assert dte.notna().all()
        assert (dte >= 0).all()


# ── Tests for get_news_sentiment_daily ───────────────────────────────────────

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

    def test_strategy_consumes_loader_output(self):
        """News-sentiment strategy accepts the daily-aggregated DataFrame."""
        from db import client as dbc
        from strategies.news_sentiment_nlp import _normalise_sentiment_df

        idx = pd.date_range("2024-01-01", periods=60, freq="B")
        raw_news = pd.DataFrame({
            "date":        np.repeat(idx[:30], 2),
            "title":       ["t"] * 60,
            "description": ["d"] * 60,
            "sentiment":   np.random.default_rng(0).uniform(-1, 1, 60),
        })

        with patch("db.client.get_news", return_value=raw_news):
            daily = dbc.get_news_sentiment_daily(MagicMock(), "AAPL",
                                                 date(2024, 1, 1), date(2024, 3, 1))

        # _normalise_sentiment_df must accept it without error and produce
        # the canonical 3-column frame aligned to the price index.
        target_idx = pd.DatetimeIndex(idx)
        aligned = _normalise_sentiment_df(daily, "AAPL", target_idx)

        assert list(aligned.columns) == ["sentiment_score", "article_count", "source_weight"]
        assert len(aligned) == len(target_idx)
        assert aligned["sentiment_score"].notna().all()


# ── Tests for get_short_interest ─────────────────────────────────────────────

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

    def test_strategy_runs_in_fallback_when_si_empty(self):
        """short_squeeze_detector must complete a backtest with empty SI
        (7-feature fallback path) without crashing."""
        from strategies.short_squeeze_detector import ShortSqueezeDetectorStrategy

        # Synth price data
        rng = np.random.default_rng(11)
        idx = pd.bdate_range("2023-01-02", periods=300)
        rets = rng.normal(0.0005, 0.025, len(idx))
        close = 50.0 * np.exp(np.cumsum(rets))
        prices = pd.DataFrame({
            "open":   close * (1 + rng.normal(0, 0.001, len(idx))),
            "high":   close * 1.02,
            "low":    close * 0.98,
            "close":  close,
            "volume": rng.integers(1_000_000, 10_000_000, len(idx)),
        }, index=idx)

        # Synthetic option snapshots — 6 strikes × 2 types × every 5 trading days
        snap_rows = []
        for d in idx[::5]:
            spot = float(prices.loc[d, "close"])
            for k_pct in (-0.10, -0.05, 0.00, 0.05, 0.10, 0.20):
                strike = round(spot * (1 + k_pct), 2)
                for opt_type in ("call", "put"):
                    snap_rows.append({
                        "SnapshotDate":   d,
                        "StrikePrice":    strike,
                        "OptionType":     opt_type,
                        "iv":             45.0,
                        "OpenInterest":   500,
                        "Delta":          0.30 if opt_type == "call" else -0.30,
                        "Gamma":          0.01,
                        "Bid":            1.0,
                        "Ask":            1.1,
                        "DTE":            45,
                        "ExpirationDate": d + pd.Timedelta(days=45),
                    })
        snap_df = pd.DataFrame(snap_rows)
        vix_df = pd.DataFrame({"close": np.full(len(idx), 18.0)}, index=idx)

        s = ShortSqueezeDetectorStrategy()
        res = s.backtest(
            prices,
            {
                "option_snapshots": snap_df,
                "vix":              vix_df,
                "short_interest":   pd.DataFrame(),  # empty → fallback path
            },
            ticker="GME",
            starting_capital=100_000,
        )
        # Fallback path declared in extra
        assert res.extra.get("feature_set") == "fallback"
        # Equity curve is finite
        assert res.equity_curve is not None
        assert res.equity_curve.notna().all()
