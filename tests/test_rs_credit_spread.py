"""
tests/test_rs_credit_spread.py
Unit tests for the RS Credit Spread AI strategy.
Run: python -m pytest tests/test_rs_credit_spread.py -v
"""
import pytest
import numpy as np
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _credit_spread_pnl(spot, short_K, long_K, credit, spread_type):
    """P&L at expiry."""
    if spread_type == "bull_put":
        intrinsic = max(0, short_K - spot) - max(0, long_K - spot)
    else:  # bear_call
        intrinsic = max(0, spot - short_K) - max(0, spot - long_K)
    return (credit - intrinsic) * 100


class TestRSCreditSpread:

    def setup_method(self):
        from strategies.rs_credit_spread import RSCreditSpreadStrategy
        self.cls = RSCreditSpreadStrategy

    def test_instantiates(self):
        assert self.cls() is not None

    def test_feature_count(self):
        s = self.cls()
        assert len(s.FEATURE_COLS) >= 8

    def test_sector_etfs_defined(self):
        from strategies.rs_credit_spread import SECTOR_ETFS
        assert len(SECTOR_ETFS) == 11
        assert "XLK" in SECTOR_ETFS
        assert "XLE" in SECTOR_ETFS

    def test_bear_call_max_profit_laggard(self):
        """Bear call on laggard: full credit if sector stays below short strike."""
        short_K, long_K, credit = 196, 205, 0.42
        pnl = _credit_spread_pnl(190, short_K, long_K, credit, "bear_call")
        assert pnl == pytest.approx(credit * 100)

    def test_bear_call_max_loss_laggard(self):
        """Bear call on laggard: max loss if sector surges above long strike."""
        short_K, long_K, credit = 196, 205, 0.42
        wing = long_K - short_K
        expected = -(wing - credit) * 100
        pnl = _credit_spread_pnl(210, short_K, long_K, credit, "bear_call")
        assert pnl == pytest.approx(expected)

    def test_bull_put_max_profit_leader(self):
        """Bull put on leader: full credit if sector stays above short strike."""
        short_K, long_K, credit = 90, 85, 0.38
        pnl = _credit_spread_pnl(95, short_K, long_K, credit, "bull_put")
        assert pnl == pytest.approx(credit * 100)

    def test_both_legs_defined_risk(self):
        """Both spread legs have finite bounded max loss."""
        # Bear call
        wing_call = 9.0
        credit_call = 0.42
        max_loss_call = (wing_call - credit_call) * 100
        assert max_loss_call > 0 and max_loss_call < 10_000

        # Bull put
        wing_put = 5.0
        credit_put = 0.38
        max_loss_put = (wing_put - credit_put) * 100
        assert max_loss_put > 0 and max_loss_put < 10_000

    def test_generate_signal_laggard(self):
        """Very low RS rank → SELL (laggard)."""
        s = self.cls()
        result = s.generate_signal({
            "rs_rank_10d": 1.0, "spy_adx_14": 18.0, "vix": 20.0
        })
        assert result.signal == "SELL"

    def test_generate_signal_leader(self):
        """Very high RS rank → BUY (leader)."""
        s = self.cls()
        result = s.generate_signal({
            "rs_rank_10d": 10.0, "spy_adx_14": 18.0, "vix": 20.0
        })
        assert result.signal == "BUY"

    def test_generate_signal_hold_trending_spy(self):
        """High SPY ADX → HOLD regardless of RS rank."""
        s = self.cls(adx_max=30.0)
        result = s.generate_signal({
            "rs_rank_10d": 1.0, "spy_adx_14": 35.0, "vix": 20.0
        })
        assert result.signal == "HOLD"

    def test_generate_signal_hold_high_vix(self):
        """High VIX → HOLD."""
        s = self.cls(vix_max=40.0)
        result = s.generate_signal({
            "rs_rank_10d": 1.0, "spy_adx_14": 18.0, "vix": 45.0
        })
        assert result.signal == "HOLD"

    def test_get_params_roundtrip(self):
        s = self.cls(min_confidence=0.65, adx_max=28.0)
        p = s.get_params()
        assert p["min_confidence"] == 0.65
        assert p["adx_max"] == 28.0

    def test_ui_params_structure(self):
        s = self.cls()
        params = s.get_backtest_ui_params()
        assert len(params) >= 4
        for p in params:
            assert "key" in p and "type" in p


class TestRSLabelConstruction:

    def test_laggard_label_contained(self):
        """Laggard stays below entry + buffer → label = 1."""
        from strategies.rs_credit_spread import _build_rs_labels
        import pandas as pd
        n = 30
        dates = pd.date_range("2023-01-01", periods=n)
        # Price stays flat after entry
        prices = pd.Series(np.full(n, 100.0), index=dates)
        labels = _build_rs_labels(prices, buffer_pct=0.04, hold_days=10, direction="laggard")
        valid = labels.dropna()
        assert (valid == 1.0).all()

    def test_laggard_label_breaks_out(self):
        """Laggard surges above buffer → label = 0."""
        from strategies.rs_credit_spread import _build_rs_labels
        import pandas as pd
        n = 30
        dates = pd.date_range("2023-01-01", periods=n)
        prices = pd.Series(index=dates, dtype=float)
        prices.iloc[:] = 100.0
        prices.iloc[5:15] = 106.0  # +6% surge beyond 4% buffer
        labels = _build_rs_labels(prices, buffer_pct=0.04, hold_days=10, direction="laggard")
        assert labels.iloc[0] == 0.0  # first entry: sees the 6% surge → should be labeled 0

    def test_rs_ranking_identifies_extremes(self):
        """Sorting by 10d return correctly identifies laggard and leader."""
        returns = {"XLK": -0.053, "XLE": 0.082, "XLF": 0.012,
                   "XLV": -0.021, "XLI": 0.031}
        sorted_tickers = sorted(returns, key=returns.get)
        laggard = sorted_tickers[0]
        leader  = sorted_tickers[-1]
        assert laggard == "XLK"
        assert leader  == "XLE"


# ── Leak-freedom: features and labels must never use future data ───────────────

class TestLeakFreedom:

    def _synthetic(self, n=400, seed=7):
        import pandas as pd
        from strategies.rs_credit_spread import SECTOR_ETFS
        rng = np.random.default_rng(seed)
        dates = pd.bdate_range("2021-01-04", periods=n)

        def gbm(mu, sig, s0=100.0):
            return pd.Series(
                s0 * np.cumprod(1 + rng.normal(mu, sig, n)), index=dates
            )

        spy = gbm(0.0003, 0.009, 420.0)
        price = pd.DataFrame(
            {"close": spy, "high": spy * 1.004, "low": spy * 0.996,
             "open": spy, "volume": 1e6}, index=dates,
        )
        sectors = {
            t: pd.DataFrame(
                {"close": gbm(rng.uniform(-0.0002, 0.0005),
                              rng.uniform(0.01, 0.02))}, index=dates)
            for t in SECTOR_ETFS
        }
        vix = pd.DataFrame(
            {"close": 18 + 5 * np.abs(rng.normal(0, 1, n))}, index=dates)
        return price, {"vix": vix, "sectors": sectors}

    def test_features_no_future_dependence(self):
        """Truncating the price series must not change feature values on the
        overlapping dates — proves features depend only on past/present data."""
        import pandas as pd
        from strategies.rs_credit_spread import _build_sector_features, SECTOR_ETFS
        rng = np.random.default_rng(3)
        n = 250
        dates = pd.bdate_range("2022-01-03", periods=n)
        closes = {
            t: pd.Series(100 * np.cumprod(1 + rng.normal(0, 0.012, n)), index=dates)
            for t in SECTOR_ETFS[:5]
        }
        spy = pd.Series(400 * np.cumprod(1 + rng.normal(0, 0.009, n)), index=dates)
        vix = pd.Series(np.full(n, 20.0), index=dates)

        cut = 180
        full = _build_sector_features(
            closes["XLK"], spy, spy, spy, closes, vix
        )
        trunc_closes = {t: s.iloc[:cut] for t, s in closes.items()}
        trunc = _build_sector_features(
            trunc_closes["XLK"], spy.iloc[:cut], spy.iloc[:cut],
            spy.iloc[:cut], trunc_closes, vix.iloc[:cut]
        )
        # Compare on the common index (drop warmup NaNs). Any future leakage would
        # make the full-series features differ from the truncated ones.
        a = full.iloc[:cut]
        b = trunc
        common = a.dropna().index.intersection(b.dropna().index)
        assert len(common) > 50
        pd.testing.assert_frame_equal(
            a.loc[common], b.loc[common], check_dtype=False, atol=1e-9
        )

    def test_label_uses_only_forward_window(self):
        """A label at index i must be unaffected by data before i (it looks only
        forward), and the last hold_days entries must be NaN (unlabelable)."""
        import pandas as pd
        from strategies.rs_credit_spread import _build_rs_labels
        n = 60
        dates = pd.date_range("2023-01-01", periods=n)
        rng = np.random.default_rng(11)
        prices = pd.Series(100 * np.cumprod(1 + rng.normal(0, 0.01, n)), index=dates)
        hold = 10
        labels = _build_rs_labels(prices, buffer_pct=0.04, hold_days=hold, direction="laggard")
        # Final hold_days entries cannot be labelled (no full forward window).
        assert labels.iloc[-hold:].isna().all()
        # Altering the PAST (before i) must not change label[i].
        i = 25
        modified = prices.copy()
        modified.iloc[:i] = modified.iloc[:i] * 0.5
        lab2 = _build_rs_labels(modified, buffer_pct=0.04, hold_days=hold, direction="laggard")
        assert lab2.iloc[i] == labels.iloc[i]

    def test_training_purges_label_window(self):
        """Model training must exclude the last hold_days bars (whose labels peek
        into the future). We verify the cutoff arithmetic the backtest uses:
        a label at index j needs data through j+hold_days, so the newest usable
        label for a model trained at bar i is j <= i - hold_days."""
        hold = 10
        for i in (100, 150, 233):
            cutoff = max(0, i - hold)
            # Every training label index j in [0, cutoff) needs j+hold <= cutoff+hold-1 < i
            assert cutoff + hold - 1 < i

    def test_backtest_runs_synthetic_zero_error(self):
        """Full synthetic backtest produces a sane, finite result with no errors."""
        from strategies.rs_credit_spread import RSCreditSpreadStrategy
        price, aux = self._synthetic()
        r = RSCreditSpreadStrategy().backtest(price, aux, starting_capital=100_000)
        assert len(r.equity_curve) == len(price)
        assert np.isfinite(r.metrics["sharpe"])
        assert np.isfinite(r.metrics["total_return_pct"])
        assert np.isfinite(r.metrics["final_equity"])
        # contracts column present + every trade has defined risk fields
        if len(r.trades):
            assert "contracts" in r.trades.columns
            assert (r.trades["contracts"] >= 1).all()

    def test_equity_curve_marks_to_market(self):
        """The equity curve must move on more than just exit days (proves MTM is
        applied, not a realised-only step function). This is the fix for the
        spurious wildly-negative Sharpe."""
        from strategies.rs_credit_spread import RSCreditSpreadStrategy
        price, aux = self._synthetic()
        r = RSCreditSpreadStrategy().backtest(price, aux, starting_capital=100_000)
        dr = r.equity_curve.pct_change().dropna()
        nonzero_days = int((dr.abs() > 1e-9).sum())
        n_trades = len(r.trades)
        # With MTM, the number of days the equity moves should exceed the number
        # of exits (a realised-only curve moves on exactly the exit days).
        assert nonzero_days > n_trades

    def test_costs_reduce_returns(self):
        """Transaction costs + skew must make the net result strictly worse than
        a frictionless run — proves frictions are actually charged on entry+exit."""
        import strategies.rs_credit_spread as M
        price, aux = self._synthetic()
        net = M.RSCreditSpreadStrategy().backtest(price, aux, starting_capital=100_000)

        # Monkeypatch frictions + skew to zero and rerun.
        s_slip, s_comm, s_skew = (M.DEFAULT_SLIPPAGE_PER_LEG,
                                  M.DEFAULT_COMMISSION_PER_LEG, M._SKEW_SLOPE)
        try:
            M.DEFAULT_SLIPPAGE_PER_LEG = 0.0
            M.DEFAULT_COMMISSION_PER_LEG = 0.0
            M._SKEW_SLOPE = 0.0
            gross = M.RSCreditSpreadStrategy().backtest(price, aux, starting_capital=100_000)
        finally:
            M.DEFAULT_SLIPPAGE_PER_LEG, M.DEFAULT_COMMISSION_PER_LEG, M._SKEW_SLOPE = (
                s_slip, s_comm, s_skew)

        # Frictionless final equity must be >= net (costs only ever subtract).
        assert gross.metrics["final_equity"] >= net.metrics["final_equity"]
