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
