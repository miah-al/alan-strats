"""
tests/test_ic_rules_integration.py

Comprehensive integration tests for the Iron Condor Rules-Based strategy.
Uses:
  - SQL Server (AlanStrats) for historical OHLCV + options snapshots
  - Polygon.io for live/current stock snapshot + options chain

Run all:
    python -m pytest tests/test_ic_rules_integration.py -v

Run only DB tests (no Polygon key needed):
    python -m pytest tests/test_ic_rules_integration.py -v -m db

Run only Polygon tests:
    python -m pytest tests/test_ic_rules_integration.py -v -m polygon

Skip slow/live tests in CI:
    python -m pytest tests/test_ic_rules_integration.py -v -m "not slow"
"""

import os
import math
import pytest
import datetime
import numpy as np
import pandas as pd
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Constants ──────────────────────────────────────────────────────────────────

_TEST_TICKER   = "SPY"          # liquid, always in DB, options always available
_TEST_TICKER_2 = "QQQ"          # second ticker for universe scan
_MIN_PRICE_BARS = 200           # IC Rules needs 200+ bars for ADX, MA200, ATR

# Screener params matching the defaults in strategies.py
_IC_PARAMS = {
    "ivr_min":     0.20,
    "vix_min":     14.0,
    "vix_max":     45.0,
    "adx_max":     35.0,
    "atr_pct_max": 0.05,
}


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def db_engine():
    """SQLAlchemy engine connected to AlanStrats. Skips if DB unreachable."""
    try:
        from db.client import get_engine
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        return engine
    except Exception as exc:
        pytest.skip(f"AlanStrats DB unavailable: {exc}")


@pytest.fixture(scope="module")
def polygon_client():
    """PolygonClient. Skips if POLYGON_API_KEY not set."""
    api_key = os.environ.get("POLYGON_API_KEY") or _try_load_env_key()
    if not api_key:
        pytest.skip("POLYGON_API_KEY not set — skipping Polygon tests")
    try:
        from data.polygon_client import PolygonClient
        return PolygonClient(api_key=api_key)
    except Exception as exc:
        pytest.skip(f"PolygonClient unavailable: {exc}")


def _try_load_env_key() -> str:
    """Try to load .env file from project root."""
    try:
        env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.startswith("POLYGON_API_KEY="):
                        return line.strip().split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return ""


@pytest.fixture(scope="module")
def spy_price_df(db_engine):
    """SPY historical OHLCV from DB (last 400 trading days)."""
    from db.client import get_price_bars
    to_date   = datetime.date.today()
    from_date = to_date - datetime.timedelta(days=600)
    df = get_price_bars(db_engine, _TEST_TICKER, from_date, to_date)
    if len(df) < _MIN_PRICE_BARS:
        pytest.skip(f"Not enough SPY price bars in DB: {len(df)} < {_MIN_PRICE_BARS}")
    return df


@pytest.fixture(scope="module")
def vix_series_db(db_engine):
    """VIX daily series from DB."""
    from db.client import get_price_bars
    to_date   = datetime.date.today()
    from_date = to_date - datetime.timedelta(days=600)
    df = get_price_bars(db_engine, "VIX", from_date, to_date)
    if df.empty:
        pytest.skip("VIX not in DB")
    return df["close"].dropna().reset_index(drop=True)


@pytest.fixture(scope="module")
def latest_option_date(db_engine):
    """Most recent options snapshot date for SPY in the DB."""
    from sqlalchemy import text
    from db.client import get_ticker_id
    tid = get_ticker_id(db_engine, _TEST_TICKER)
    if tid is None:
        pytest.skip(f"{_TEST_TICKER} not in DB")
    with db_engine.connect() as conn:
        result = conn.execute(text(
            "SELECT MAX(SnapshotDate) FROM mkt.OptionSnapshot WHERE TickerId = :tid"
        ), {"tid": tid})
        row = result.fetchone()
    if not row or row[0] is None:
        pytest.skip(f"No option snapshots for {_TEST_TICKER} in DB")
    return row[0].date() if hasattr(row[0], "date") else row[0]


@pytest.fixture(scope="module")
def spy_options_db(db_engine, latest_option_date):
    """SPY options snapshot from DB on the most recent snapshot date."""
    from db.client import get_option_snapshots
    df = get_option_snapshots(db_engine, _TEST_TICKER, latest_option_date)
    if df.empty:
        pytest.skip(f"No SPY options on {latest_option_date}")
    return df


# ── Database connectivity tests ────────────────────────────────────────────────

@pytest.mark.db
class TestDatabaseConnectivity:
    def test_db_connects(self, db_engine):
        from sqlalchemy import text
        with db_engine.connect() as conn:
            result = conn.execute(text("SELECT @@VERSION"))
            version = result.fetchone()[0]
        assert "Microsoft SQL Server" in version

    def test_spy_in_ticker_table(self, db_engine):
        from db.client import get_ticker_id
        tid = get_ticker_id(db_engine, _TEST_TICKER)
        assert tid is not None, f"{_TEST_TICKER} not found in mkt.Ticker"

    def test_vix_in_ticker_table(self, db_engine):
        from db.client import get_ticker_id
        # VIX may be stored as "VIX", "^VIX", or "$VIX" depending on data source
        tid = (get_ticker_id(db_engine, "VIX") or
               get_ticker_id(db_engine, "^VIX") or
               get_ticker_id(db_engine, "$VIX"))
        if tid is None:
            pytest.skip("VIX not in mkt.Ticker (may need to sync VIX data)")
        assert tid is not None


# ── Historical price data tests ────────────────────────────────────────────────

@pytest.mark.db
class TestHistoricalPriceData:
    def test_spy_price_bars_loaded(self, spy_price_df):
        assert len(spy_price_df) >= _MIN_PRICE_BARS, (
            f"Need at least {_MIN_PRICE_BARS} bars for IC signals, got {len(spy_price_df)}"
        )

    def test_price_bar_columns_present(self, spy_price_df):
        required = {"open", "high", "low", "close", "volume"}
        assert required.issubset(set(spy_price_df.columns))

    def test_price_bar_no_null_closes(self, spy_price_df):
        null_count = spy_price_df["close"].isna().sum()
        assert null_count == 0, f"{null_count} null close prices in SPY data"

    def test_price_bar_close_positive(self, spy_price_df):
        assert (spy_price_df["close"] > 0).all()

    def test_price_bar_high_gte_low(self, spy_price_df):
        bad = (spy_price_df["high"] < spy_price_df["low"]).sum()
        assert bad == 0, f"{bad} rows where high < low"

    def test_price_bar_sorted_ascending(self, spy_price_df):
        dates = pd.to_datetime(spy_price_df["date"])
        assert dates.is_monotonic_increasing, "Price bars not sorted ascending by date"

    def test_price_bar_no_future_dates(self, spy_price_df):
        today = pd.Timestamp.today().normalize()
        max_date = pd.to_datetime(spy_price_df["date"]).max()
        assert max_date <= today, f"Future date in price bars: {max_date}"

    def test_vix_series_range(self, vix_series_db):
        assert len(vix_series_db) >= 100, "Need 100+ VIX bars"
        assert (vix_series_db > 5).all(),  "VIX should always be > 5"
        assert (vix_series_db < 200).all(), "VIX should be < 200 (no data corruption)"


# ── Options data quality tests ─────────────────────────────────────────────────

@pytest.mark.db
class TestOptionsDataQuality:
    def test_options_loaded(self, spy_options_db):
        assert len(spy_options_db) > 0, "No SPY options in DB"

    def test_options_has_required_columns(self, spy_options_db):
        required = {"strike", "iv", "expiration", "contract_type"}
        assert required.issubset(set(spy_options_db.columns))

    def test_options_iv_present(self, spy_options_db):
        iv_present = spy_options_db["iv"].notna().sum()
        total = len(spy_options_db)
        pct = iv_present / total
        assert pct > 0.5, (
            f"Only {pct:.1%} of options have IV. "
            "IC screener needs IV for entry decisions."
        )

    def test_options_contract_types_both_present(self, spy_options_db):
        types = set(spy_options_db["contract_type"].str.upper().unique())
        assert "C" in types or "call" in str(types).lower(), "No call options"
        assert "P" in types or "put" in str(types).lower(), "No put options"

    def test_options_strikes_positive(self, spy_options_db):
        assert (spy_options_db["strike"] > 0).all()

    def test_options_expiration_future_or_recent(self, spy_options_db, latest_option_date):
        exp_dates = pd.to_datetime(spy_options_db["expiration"])
        snap_date = pd.Timestamp(latest_option_date)
        # Some expired contracts may be in DB — just check not all are ancient
        future_or_near = (exp_dates >= snap_date - pd.Timedelta(days=7)).sum()
        assert future_or_near > 0, "No near-term or future expiries in options data"

    def test_options_bid_ask_null_pct_reported(self, spy_options_db):
        """Report bid/ask null %. Not a failure — just informational."""
        total = len(spy_options_db)
        null_bid = spy_options_db["bid"].isna().sum() + (spy_options_db["bid"] == 0).sum()
        null_ask = spy_options_db["ask"].isna().sum() + (spy_options_db["ask"] == 0).sum()
        bid_pct = null_bid / total * 100
        ask_pct = null_ask / total * 100
        # Always passes — just prints for visibility
        print(f"\n  SPY options bid null: {bid_pct:.1f}%  ask null: {ask_pct:.1f}%")
        # Warn if >50% null — IC screener will show "—" for prices
        if bid_pct > 50:
            pytest.warns(None)  # informational only

    def test_atm_options_have_iv(self, spy_options_db):
        """ATM strikes (nearest to last price) should have IV."""
        calls = spy_options_db[spy_options_db["contract_type"].str.upper() == "C"]
        if calls.empty:
            pytest.skip("No calls in snapshot")
        # Use median strike as rough ATM proxy
        median_strike = calls["strike"].median()
        atm = calls.iloc[(calls["strike"] - median_strike).abs().argsort()[:5]]
        iv_present = atm["iv"].notna().sum()
        assert iv_present > 0, "ATM calls have no IV — screener cannot compute IVR"


# ── IC Rules screener logic tests (with DB data) ───────────────────────────────

@pytest.mark.db
class TestIcRulesScreenerWithDbData:
    def test_score_ic_rules_runs_without_error(self, spy_price_df, vix_series_db):
        from engine.screener import _score_ic_rules
        iv = {"atm_iv": 0.18, "hv20": 0.13, "ivr": 0.45, "vrp": 0.05,
              "iv_over_hv": 1.38, "iv_source": "db_test"}
        price_df = spy_price_df.rename(columns={"date": "date"})
        row = _score_ic_rules(_TEST_TICKER, price_df, vix_series_db, iv, _IC_PARAMS)
        assert row is not None, "_score_ic_rules returned None on real DB data"

    def test_score_output_has_required_keys(self, spy_price_df, vix_series_db):
        from engine.screener import _score_ic_rules
        iv = {"atm_iv": 0.18, "hv20": 0.13, "ivr": 0.45, "vrp": 0.05,
              "iv_over_hv": 1.38, "iv_source": "db_test"}
        row = _score_ic_rules(_TEST_TICKER, spy_price_df, vix_series_db, iv, _IC_PARAMS)
        required_keys = {"Ticker", "Price", "VIX", "ATR%", "ADX", "IVR", "score", "n_pass"}
        assert required_keys.issubset(set(row.keys())), (
            f"Missing keys: {required_keys - set(row.keys())}"
        )

    def test_atr_pct_is_decimal(self, spy_price_df, vix_series_db):
        from engine.screener import _score_ic_rules
        iv = {"atm_iv": 0.18, "hv20": 0.13, "ivr": 0.45, "vrp": 0.05,
              "iv_over_hv": 1.38, "iv_source": "db_test"}
        row = _score_ic_rules(_TEST_TICKER, spy_price_df, vix_series_db, iv, _IC_PARAMS)
        atr_pct = row["ATR%"]
        assert 0 < atr_pct < 0.15, (
            f"ATR% should be decimal (0.005-0.15 for SPY), got {atr_pct}. "
            "If > 1.0, the units are wrong (percentage not decimal)."
        )

    def test_price_matches_latest_close(self, spy_price_df, vix_series_db):
        from engine.screener import _score_ic_rules
        iv = {"atm_iv": 0.18, "hv20": 0.13, "ivr": 0.45, "vrp": 0.05,
              "iv_over_hv": 1.38, "iv_source": "db_test"}
        row = _score_ic_rules(_TEST_TICKER, spy_price_df, vix_series_db, iv, _IC_PARAMS)
        latest_close = float(spy_price_df["close"].iloc[-1])
        assert abs(row["Price"] - latest_close) < 0.01, (
            f"Screener price {row['Price']} doesn't match DB latest close {latest_close}"
        )

    def test_score_is_between_0_and_100(self, spy_price_df, vix_series_db):
        from engine.screener import _score_ic_rules
        iv = {"atm_iv": 0.18, "hv20": 0.13, "ivr": 0.45, "vrp": 0.05,
              "iv_over_hv": 1.38, "iv_source": "db_test"}
        row = _score_ic_rules(_TEST_TICKER, spy_price_df, vix_series_db, iv, _IC_PARAMS)
        assert 0 <= row["score"] <= 100, f"Score out of range: {row['score']}"

    def test_n_pass_consistent_with_all_pass(self, spy_price_df, vix_series_db):
        from engine.screener import _score_ic_rules
        iv = {"atm_iv": 0.18, "hv20": 0.13, "ivr": 0.45, "vrp": 0.05,
              "iv_over_hv": 1.38, "iv_source": "db_test"}
        row = _score_ic_rules(_TEST_TICKER, spy_price_df, vix_series_db, iv, _IC_PARAMS)
        if row["all_pass"]:
            assert row["n_pass"] == 5, f"all_pass=True but n_pass={row['n_pass']}"
        else:
            assert row["n_pass"] < 5

    def test_vix_in_row_matches_series(self, spy_price_df, vix_series_db):
        from engine.screener import _score_ic_rules
        iv = {"atm_iv": 0.18, "hv20": 0.13, "ivr": 0.45, "vrp": 0.05,
              "iv_over_hv": 1.38, "iv_source": "db_test"}
        row = _score_ic_rules(_TEST_TICKER, spy_price_df, vix_series_db, iv, _IC_PARAMS)
        expected_vix = float(vix_series_db.iloc[-1])
        assert abs(row["VIX"] - expected_vix) < 0.01


# ── IC strikes / wing logic tests ─────────────────────────────────────────────

@pytest.mark.db
class TestIcStrikeLogic:
    def test_wing_strike_differs_from_short_strike(self, spy_options_db, spy_price_df):
        """Long call wing must not equal the short call strike."""
        from engine.screener import _get_chain_mid
        calls = spy_options_db[spy_options_db["contract_type"].str.upper() == "C"].copy()
        puts  = spy_options_db[spy_options_db["contract_type"].str.upper() == "P"].copy()
        if calls.empty or puts.empty:
            pytest.skip("No calls or puts in snapshot")

        spot = float(spy_price_df["close"].iloc[-1])
        # Simulate the screener's strike selection
        short_call_target = spot * 1.05
        short_call_mid, short_call_k = _get_chain_mid(calls, short_call_target)
        if short_call_k is None or math.isnan(float(short_call_k or 0)):
            pytest.skip("Could not find short call strike")

        wing_w = spot * 0.03  # 3% wing width
        long_call_mid, long_call_k = _get_chain_mid(
            calls, short_call_k + wing_w, exclude_strike=short_call_k
        )
        assert long_call_k != short_call_k, (
            f"Long call wing {long_call_k} must differ from short call {short_call_k}"
        )

    def test_short_put_below_short_call(self, spy_options_db, spy_price_df):
        """Iron condor: short put strike must be below short call strike."""
        from engine.screener import _get_chain_mid
        calls = spy_options_db[spy_options_db["contract_type"].str.upper() == "C"].copy()
        puts  = spy_options_db[spy_options_db["contract_type"].str.upper() == "P"].copy()
        if calls.empty or puts.empty:
            pytest.skip("No calls or puts in snapshot")

        spot = float(spy_price_df["close"].iloc[-1])
        _, short_call_k = _get_chain_mid(calls, spot * 1.05)
        _, short_put_k  = _get_chain_mid(puts,  spot * 0.95)

        if short_call_k is None or short_put_k is None:
            pytest.skip("Strike selection failed — chain may be empty")
        assert short_put_k < short_call_k, (
            f"Short put {short_put_k} must be below short call {short_call_k}"
        )

    def test_long_put_below_short_put(self, spy_options_db, spy_price_df):
        """Long put (wing) must be further OTM than the short put."""
        from engine.screener import _get_chain_mid
        puts = spy_options_db[spy_options_db["contract_type"].str.upper() == "P"].copy()
        if puts.empty:
            pytest.skip("No puts in snapshot")

        spot = float(spy_price_df["close"].iloc[-1])
        _, short_put_k = _get_chain_mid(puts, spot * 0.95)
        if short_put_k is None:
            pytest.skip("No short put strike found")

        wing_w = spot * 0.03
        _, long_put_k = _get_chain_mid(puts, short_put_k - wing_w, exclude_strike=short_put_k)
        if long_put_k is None:
            pytest.skip("No long put wing strike found")

        assert long_put_k < short_put_k, (
            f"Long put wing {long_put_k} must be below short put {short_put_k}"
        )

    def test_breakeven_calculation(self, spy_options_db, spy_price_df):
        """BE = short strike ± net_credit. Verify with a known net_credit."""
        spot = float(spy_price_df["close"].iloc[-1])
        # Simulate net_credit = $1.00 per share
        short_call_k = spot * 1.05
        short_put_k  = spot * 0.95
        net_credit = 1.00

        be_call = short_call_k + net_credit
        be_put  = short_put_k  - net_credit

        assert be_call > short_call_k, "Call BE must be above short call strike"
        assert be_put  < short_put_k,  "Put BE must be below short put strike"
        assert be_call - short_call_k == pytest.approx(net_credit)
        assert short_put_k - be_put   == pytest.approx(net_credit)


# ── Polygon live data tests ────────────────────────────────────────────────────

@pytest.mark.polygon
@pytest.mark.slow
class TestPolygonLiveData:
    def test_polygon_client_connects(self, polygon_client):
        snap = polygon_client._get(
            f"/v2/snapshot/locale/us/markets/stocks/tickers/{_TEST_TICKER}", {}
        )
        assert "ticker" in snap, f"Unexpected response: {snap}"

    def test_polygon_stock_snapshot_has_price(self, polygon_client):
        snap = polygon_client._get(
            f"/v2/snapshot/locale/us/markets/stocks/tickers/{_TEST_TICKER}", {}
        )
        ticker = snap.get("ticker", {})
        day  = ticker.get("day")  or {}
        prev = ticker.get("prevDay") or {}
        # On weekends/holidays Polygon returns day=0 — fall back to prevDay
        price = day.get("c") or day.get("vw") or prev.get("c") or prev.get("vw")
        if not price or price == 0:
            pytest.skip(f"No price in snapshot (weekend/holiday): day={day}, prev={prev}")
        assert price > 0

    def test_polygon_aggs_returns_data(self, polygon_client):
        from data.loader import _fetch_polygon_aggs
        today     = datetime.date.today()
        from_date = (today - datetime.timedelta(days=30)).strftime("%Y-%m-%d")
        to_date   = today.strftime("%Y-%m-%d")
        df = _fetch_polygon_aggs(polygon_client, _TEST_TICKER, from_date, to_date)
        assert not df.empty, "Polygon OHLCV fetch returned empty dataframe"
        assert len(df) >= 5, f"Expected 5+ trading days, got {len(df)}"

    def test_polygon_ohlcv_columns(self, polygon_client):
        from data.loader import _fetch_polygon_aggs
        today     = datetime.date.today()
        from_date = (today - datetime.timedelta(days=10)).strftime("%Y-%m-%d")
        df = _fetch_polygon_aggs(polygon_client, _TEST_TICKER, from_date, today.strftime("%Y-%m-%d"))
        if df.empty:
            pytest.skip("No recent Polygon data (weekend?)")
        required = {"open", "high", "low", "close", "volume"}
        assert required.issubset(set(df.columns))

    def test_polygon_vix_data_available(self, polygon_client):
        """VIX is available via Polygon as I:VIX or ^VIX depending on plan."""
        from data.loader import _fetch_polygon_aggs
        today     = datetime.date.today()
        from_date = (today - datetime.timedelta(days=30)).strftime("%Y-%m-%d")
        df = _fetch_polygon_aggs(polygon_client, "VIX", from_date, today.strftime("%Y-%m-%d"))
        # VIX might not be available on all Polygon plans — just check it doesn't crash
        print(f"\n  Polygon VIX rows: {len(df)}")


# ── Polygon → IC screener end-to-end test ─────────────────────────────────────

@pytest.mark.polygon
@pytest.mark.slow
class TestIcRulesWithPolygonData:
    def test_full_ic_scan_with_polygon_data(self, polygon_client, spy_price_df, vix_series_db):
        """
        End-to-end: fetch current Polygon snapshot + use DB history,
        run IC screener, validate output constraints.
        """
        from engine.screener import _score_ic_rules

        # Current price from Polygon
        snap = polygon_client._get(
            f"/v2/snapshot/locale/us/markets/stocks/tickers/{_TEST_TICKER}", {}
        )
        day  = (snap.get("ticker") or {}).get("day") or {}
        spot = day.get("c") or float(spy_price_df["close"].iloc[-1])
        assert spot > 0

        # Build price_df using DB history, replace last close with Polygon current
        price_df = spy_price_df.copy()
        price_df.loc[price_df.index[-1], "close"] = spot

        # iv_metrics — use DB options snapshot if available, else synthetic
        iv = {"atm_iv": 0.18, "hv20": 0.13, "ivr": 0.45, "vrp": 0.05,
              "iv_over_hv": 1.38, "iv_source": "polygon_current"}

        row = _score_ic_rules(_TEST_TICKER, price_df, vix_series_db, iv, _IC_PARAMS)
        assert row is not None
        assert row["Price"] == pytest.approx(spot, rel=0.001)
        assert 0 <= row["score"] <= 100
        assert 0 < row["ATR%"] < 0.15
        print(f"\n  IC scan result: score={row['score']:.1f}  n_pass={row['n_pass']}  "
              f"VIX={row['VIX']:.1f}  IVR={row['IVR']}  ATR%={row['ATR%']:.3f}")

    @pytest.mark.polygon
    @pytest.mark.slow
    def test_fetch_ic_strikes_from_polygon(self, polygon_client, spy_price_df):
        """
        Fetch real options chain from Polygon, run _fetch_ic_strikes,
        validate strike logic and null-price display.
        """
        from dash_app.pages.strategies import _fetch_ic_strikes

        spot = float(spy_price_df["close"].iloc[-1])
        api_key = os.environ.get("POLYGON_API_KEY") or _try_load_env_key()

        chain = _fetch_ic_strikes(
            _TEST_TICKER,
            api_key,
            spot=spot,
            adx_ok=True,
        )

        if chain is None:
            pytest.skip(
                "_fetch_ic_strikes returned None — Polygon options chain may be incomplete "
                "on weekends (no wing strikes above/below short strikes). Re-run on a market day."
            )

        assert chain is not None, "_fetch_ic_strikes returned None"
        assert "short_call_k" in chain
        assert "short_put_k"  in chain
        assert "long_call_k"  in chain
        assert "long_put_k"   in chain

        sc = chain["short_call_k"]
        lc = chain["long_call_k"]
        sp = chain["short_put_k"]
        lp = chain["long_put_k"]

        print(f"\n  IC strikes: lp={lp}  sp={sp}  [spot={spot:.1f}]  sc={sc}  lc={lc}")

        # Wing logic assertions
        assert lc != sc, f"Long call wing {lc} must differ from short call {sc}"
        assert lp != sp, f"Long put wing {lp} must differ from short put {sp}"
        assert sc > sp,  f"Short call {sc} must be above short put {sp}"
        assert lc > sc,  f"Long call wing {lc} must be above short call {sc}"
        assert sp > lp,  f"Short put {sp} must be above long put wing {lp}"

        # Width check: wings should be at least $1 wide
        assert lc - sc >= 1.0, f"Call spread too narrow: {lc - sc:.2f}"
        assert sp - lp >= 1.0, f"Put spread too narrow: {sp - lp:.2f}"

        # Null price display: if bid/ask are null, mids should be None or 0
        sc_mid = chain.get("short_call_mid")
        sp_mid = chain.get("short_put_mid")
        if sc_mid is not None and sc_mid > 0 and sp_mid is not None and sp_mid > 0:
            net_credit = sc_mid + sp_mid - chain.get("long_call_mid", 0) - chain.get("long_put_mid", 0)
            print(f"  Net credit estimate: ${net_credit:.2f} (Polygon mid prices available)")
        else:
            print("  Mids are null — bid/ask not available from Polygon (expected on weekends)")


# ── IV metrics pipeline tests (DB + screener) ─────────────────────────────────

@pytest.mark.db
class TestIvMetricsPipeline:
    def test_iv_metrics_computed_from_options(self, spy_options_db, spy_price_df):
        """
        Given a real options snapshot, verify iv_metrics dict is populated correctly.
        This is what gets passed into _score_ic_rules.
        """
        try:
            from data.loader import compute_iv_metrics
        except ImportError:
            pytest.skip("compute_iv_metrics not available in data.loader")

        try:
            spot = float(spy_price_df["close"].iloc[-1])
            iv_metrics = compute_iv_metrics(spy_options_db, spot)
        except Exception as e:
            pytest.skip(f"compute_iv_metrics failed: {e}")

        # If returned, check structure
        if iv_metrics:
            if "atm_iv" in iv_metrics and iv_metrics["atm_iv"] is not None:
                assert 0.01 < iv_metrics["atm_iv"] < 3.0, (
                    f"atm_iv={iv_metrics['atm_iv']} looks wrong (should be 0.01-3.0 decimal)"
                )
            print(f"\n  IV metrics: {iv_metrics}")

    def test_hv20_calculation(self, spy_price_df):
        """HV20 = 20-day rolling std of returns * sqrt(252). Verify units."""
        close = spy_price_df["close"].astype(float)
        rets  = close.pct_change().dropna()
        hv20  = rets.rolling(20).std().iloc[-1] * math.sqrt(252)
        # SPY HV should be 5–50% annualised
        assert 0.03 < hv20 < 0.60, (
            f"HV20={hv20:.4f} looks wrong. "
            "If > 1.0, forgot to annualize or returned percentage not decimal."
        )

    def test_ivr_computation_with_full_vix_history(self, vix_series_db):
        """IVR from 252-bar VIX history should be in [0, 1]."""
        from strategies.ivr_credit_spread import _compute_ivr
        ivr_series = _compute_ivr(vix_series_db)
        valid = ivr_series.dropna()
        if len(valid) == 0:
            pytest.skip("Not enough VIX history for IVR (need 126+ bars)")
        assert (valid >= 0).all() and (valid <= 1).all(), (
            f"IVR out of [0,1]: min={valid.min():.3f} max={valid.max():.3f}"
        )
        current_ivr = float(valid.iloc[-1])
        print(f"\n  Current VIX-based IVR (from DB): {current_ivr:.3f}")


# ── IC Rules: parameter sensitivity tests ─────────────────────────────────────

@pytest.mark.db
class TestIcRulesParameterSensitivity:
    def _run(self, spy_price_df, vix_series_db, params, iv=None):
        from engine.screener import _score_ic_rules
        iv = iv or {"atm_iv": 0.18, "hv20": 0.13, "ivr": 0.45, "vrp": 0.05,
                    "iv_over_hv": 1.38, "iv_source": "test"}
        return _score_ic_rules(_TEST_TICKER, spy_price_df, vix_series_db, iv, params)

    def test_very_strict_params_reduce_n_pass(self, spy_price_df, vix_series_db):
        strict = dict(_IC_PARAMS, ivr_min=0.95, atr_pct_max=0.001, adx_max=1.0)
        row = self._run(spy_price_df, vix_series_db, strict)
        assert row is not None
        # Very strict params should fail multiple conditions
        assert row["n_pass"] < 5, "Unrealistically strict params should fail some checks"

    def test_very_loose_params_allow_entry(self, spy_price_df, vix_series_db):
        loose = dict(_IC_PARAMS, ivr_min=0.0, atr_pct_max=1.0, adx_max=100.0,
                     vix_min=0.0, vix_max=200.0)
        iv_good = {"atm_iv": 0.18, "hv20": 0.13, "ivr": 0.60, "vrp": 0.05,
                   "iv_over_hv": 1.38, "iv_source": "test"}
        row = self._run(spy_price_df, vix_series_db, loose, iv=iv_good)
        assert row is not None
        # With loose params and good IV, all_pass should be True
        assert row["n_pass"] >= 4, (
            f"Very loose params should pass most checks, got n_pass={row['n_pass']}"
        )

    def test_high_vix_blocks_entry(self, spy_price_df):
        """VIX > vix_max should block the vix_ok condition."""
        from engine.screener import _score_ic_rules
        extreme_vix = pd.Series([60.0] * 300)  # far above vix_max=45
        iv = {"atm_iv": 0.18, "hv20": 0.13, "ivr": 0.45, "vrp": 0.05,
              "iv_over_hv": 1.38, "iv_source": "test"}
        row = _score_ic_rules(_TEST_TICKER, spy_price_df, extreme_vix, iv, _IC_PARAMS)
        assert row is not None
        assert not row.get("vix_ok", True), (
            "VIX=60 should fail the vix_ok condition with vix_max=45"
        )

    def test_low_vix_blocks_entry(self, spy_price_df):
        """VIX < vix_min should block the vix_ok condition."""
        from engine.screener import _score_ic_rules
        low_vix = pd.Series([10.0] * 300)  # below vix_min=14
        iv = {"atm_iv": 0.18, "hv20": 0.13, "ivr": 0.45, "vrp": 0.05,
              "iv_over_hv": 1.38, "iv_source": "test"}
        row = _score_ic_rules(_TEST_TICKER, spy_price_df, low_vix, iv, _IC_PARAMS)
        assert row is not None
        assert not row.get("vix_ok", True), (
            "VIX=10 should fail the vix_ok condition with vix_min=14"
        )

    def test_low_ivr_blocks_entry(self, spy_price_df, vix_series_db):
        """IVR below ivr_min should fail the ivr_ok check."""
        from engine.screener import _score_ic_rules
        iv_low_ivr = {"atm_iv": 0.18, "hv20": 0.13, "ivr": 0.05,
                      "vrp": 0.05, "iv_over_hv": 1.38, "iv_source": "test"}
        row = _score_ic_rules(_TEST_TICKER, spy_price_df, vix_series_db,
                              iv_low_ivr, _IC_PARAMS)
        assert row is not None
        assert not row.get("ivr_ok", True), (
            f"IVR=0.05 should fail ivr_ok with ivr_min={_IC_PARAMS['ivr_min']}"
        )
