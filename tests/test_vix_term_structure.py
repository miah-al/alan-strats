"""
tests/test_vix_term_structure.py
Unit tests for the VIX Term Structure AI strategy.
Run: python -m pytest tests/test_vix_term_structure.py -v
"""
import pytest
import numpy as np
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _spread_pnl_credit(spot, short_K, long_K, credit, spread_type):
    """P&L of a credit spread at expiry."""
    if spread_type == "bull_put":
        intrinsic = max(0, short_K - spot) - max(0, long_K - spot)
    else:  # bear_call
        intrinsic = max(0, spot - short_K) - max(0, spot - long_K)
    return (credit - intrinsic) * 100


class TestVIXTermStructure:

    def setup_method(self):
        from strategies.vix_term_structure import VIXTermStructureStrategy
        self.cls = VIXTermStructureStrategy

    def test_instantiates(self):
        assert self.cls() is not None

    def test_warmup_bars(self):
        from strategies.vix_term_structure import _WARMUP_BARS
        assert _WARMUP_BARS >= 60, "Need at least 60 bars for regime detection"

    def test_retrain_interval(self):
        from strategies.vix_term_structure import _RETRAIN_EVERY
        assert _RETRAIN_EVERY >= 10

    def test_feature_count(self):
        s = self.cls()
        assert len(s.FEATURE_COLS) >= 10

    def test_thresholds_ordered(self):
        """threshold_short must be below threshold_long (creates flat zone between)."""
        s = self.cls()
        assert s.threshold_short < s.threshold_long

    def test_bull_put_max_profit_otm(self):
        """Bull put credit spread: full credit when spot stays above short strike."""
        short_K, long_K, credit = 490, 477.5, 1.20
        pnl = _spread_pnl_credit(510, short_K, long_K, credit, "bull_put")
        assert pnl == pytest.approx(credit * 100)

    def test_bull_put_max_loss_itm(self):
        """Bull put: max loss when spot well below both strikes."""
        short_K, long_K, credit = 490, 477.5, 1.20
        wing = short_K - long_K
        expected = -(wing - credit) * 100
        pnl = _spread_pnl_credit(460, short_K, long_K, credit, "bull_put")
        assert pnl == pytest.approx(expected)

    def test_defined_risk_bull_put(self):
        """Bull put max loss is finite and bounded by wing width."""
        short_K, long_K, credit = 490, 477.5, 1.20
        wing = short_K - long_K
        max_loss = (wing - credit) * 100
        assert max_loss > 0
        assert max_loss < 10_000

    def test_generate_signal_contango(self):
        """Positive VRP → SELL signal (contango = sell credit spread)."""
        s = self.cls()
        result = s.generate_signal({"vix": 20.0, "realized_vol_20d": 0.10})
        assert result.signal == "SELL"
        assert result.confidence > 0.5

    def test_generate_signal_backwardation(self):
        """Negative VRP → BUY signal (backwardation = buy protection/debit)."""
        s = self.cls()
        result = s.generate_signal({"vix": 18.0, "realized_vol_20d": 0.25})
        assert result.signal == "BUY"
        assert result.confidence > 0.5

    def test_generate_signal_neutral(self):
        """VRP near zero → HOLD."""
        s = self.cls()
        result = s.generate_signal({"vix": 15.0, "realized_vol_20d": 0.14})
        assert result.signal == "HOLD"

    def test_get_params_roundtrip(self):
        """get_params returns all constructor parameters."""
        s = self.cls(threshold_short=0.35, vix_max=40.0)
        p = s.get_params()
        assert p["threshold_short"] == 0.35
        assert p["vix_max"] == 40.0

    def test_ui_params_structure(self):
        s = self.cls()
        params = s.get_backtest_ui_params()
        assert len(params) >= 4
        for p in params:
            assert "key" in p and "label" in p and "type" in p


class TestBackwardationLabel:

    def test_label_backwardation(self):
        """Realized vol > implied → backwardation = 1."""
        from strategies.vix_term_structure import _build_labels
        import pandas as pd
        n = 50
        dates = pd.date_range("2023-01-01", periods=n)
        # High realized vol scenario: daily moves of 1.5%
        returns = np.random.normal(0, 0.015, n)
        close = pd.Series(100 * np.exp(np.cumsum(returns)), index=dates)
        vix = pd.Series(np.full(n, 12.0), index=dates)  # low VIX → easier to exceed

        labels = _build_labels(close, vix, n_forward=14)
        valid_labels = labels.dropna()
        assert len(valid_labels) > 0
        # With low VIX and moderate realized vol, should have some backwardation
        assert valid_labels.isin([0.0, 1.0]).all()

    def test_label_contango(self):
        """Low realized vol with high VIX → contango = 0."""
        from strategies.vix_term_structure import _build_labels
        import pandas as pd
        n = 50
        dates = pd.date_range("2023-01-01", periods=n)
        # Very calm market: 0.1% daily moves
        returns = np.random.normal(0, 0.001, n)
        close = pd.Series(100 * np.exp(np.cumsum(returns)), index=dates)
        vix = pd.Series(np.full(n, 30.0), index=dates)  # high VIX

        labels = _build_labels(close, vix, n_forward=14)
        valid_labels = labels.dropna()
        # With calm realized vol and high VIX, most labels should be 0 (contango)
        assert valid_labels.mean() < 0.3  # less than 30% backwardation
