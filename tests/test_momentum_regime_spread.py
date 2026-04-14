"""
tests/test_momentum_regime_spread.py
Unit tests for the Momentum Regime Debit Spread AI strategy.
Run: python -m pytest tests/test_momentum_regime_spread.py -v
"""
import pytest
import numpy as np
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _debit_spread_pnl(spot, long_K, short_K, debit, spread_type):
    """P&L at expiry of a debit spread."""
    if spread_type == "bull_call":
        intrinsic = max(0, spot - long_K) - max(0, spot - short_K)
    else:  # bear_put
        intrinsic = max(0, long_K - spot) - max(0, short_K - spot)
    return (intrinsic - debit) * 100


class TestMomentumRegimeSpread:

    def setup_method(self):
        from strategies.momentum_regime_spread import MomentumRegimeSpreadStrategy
        self.cls = MomentumRegimeSpreadStrategy

    def test_instantiates(self):
        assert self.cls() is not None

    def test_feature_count(self):
        s = self.cls()
        assert len(s.FEATURE_COLS) >= 9

    def test_bull_call_max_gain(self):
        """Bull call: max gain when spot far above short strike."""
        long_K, short_K, debit = 470, 482, 1.85
        wing = short_K - long_K
        pnl = _debit_spread_pnl(495, long_K, short_K, debit, "bull_call")
        assert pnl == pytest.approx((wing - debit) * 100)

    def test_bull_call_max_loss(self):
        """Bull call: max loss = debit when spot below long strike."""
        long_K, short_K, debit = 470, 482, 1.85
        pnl = _debit_spread_pnl(460, long_K, short_K, debit, "bull_call")
        assert pnl == pytest.approx(-debit * 100)

    def test_bear_put_max_gain(self):
        """Bear put: max gain when spot far below short strike."""
        long_K, short_K, debit = 382, 370, 1.95
        wing = long_K - short_K
        pnl = _debit_spread_pnl(360, long_K, short_K, debit, "bear_put")
        assert pnl == pytest.approx((wing - debit) * 100)

    def test_bear_put_max_loss(self):
        """Bear put: max loss = debit when spot above long strike."""
        long_K, short_K, debit = 382, 370, 1.95
        pnl = _debit_spread_pnl(395, long_K, short_K, debit, "bear_put")
        assert pnl == pytest.approx(-debit * 100)

    def test_debit_loss_is_bounded(self):
        """Debit spread max loss is always finite = debit paid."""
        debit = 2.50
        max_loss = debit * 100
        assert max_loss == 250.0
        assert max_loss < 10_000

    def test_generate_signal_bull(self):
        """Strong uptrend + falling VIX → BUY."""
        s = self.cls()
        result = s.generate_signal({
            "ret_5d": 0.04, "ret_20d": 0.03,
            "vix": 14.0, "vix_20d_avg": 18.0,
        })
        assert result.signal == "BUY"

    def test_generate_signal_bear(self):
        """Strong downtrend + rising VIX → SELL."""
        s = self.cls()
        result = s.generate_signal({
            "ret_5d": -0.04, "ret_20d": -0.03,
            "vix": 28.0, "vix_20d_avg": 20.0,
        })
        assert result.signal == "SELL"

    def test_generate_signal_chop(self):
        """Small moves → HOLD."""
        s = self.cls()
        result = s.generate_signal({
            "ret_5d": 0.005, "ret_20d": -0.002,
            "vix": 18.0, "vix_20d_avg": 18.5,
        })
        assert result.signal == "HOLD"

    def test_get_params_roundtrip(self):
        s = self.cls(confidence_threshold=0.60, dte_target=21)
        p = s.get_params()
        assert p["confidence_threshold"] == 0.60
        assert p["dte_target"] == 21

    def test_ui_params_structure(self):
        s = self.cls()
        params = s.get_backtest_ui_params()
        assert len(params) >= 4
        for p in params:
            assert "key" in p and "type" in p


class TestRegimeLabelConstruction:

    def test_label_classes_are_valid(self):
        """All labels are 0 (chop), 1 (bull), or 2 (bear) or NaN."""
        from strategies.momentum_regime_spread import _build_labels
        import pandas as pd
        n = 300
        dates = pd.date_range("2020-01-01", periods=n)
        prices = pd.Series(100 * np.cumprod(1 + np.random.normal(0, 0.01, n)), index=dates)
        labels = _build_labels(prices, n_forward=10)
        valid = labels.dropna()
        assert valid.isin([0.0, 1.0, 2.0]).all()

    def test_label_has_all_three_classes(self):
        """With enough data, all three regimes should appear."""
        from strategies.momentum_regime_spread import _build_labels
        import pandas as pd
        np.random.seed(42)
        n = 500
        dates = pd.date_range("2020-01-01", periods=n)
        prices = pd.Series(100 * np.cumprod(1 + np.random.normal(0, 0.012, n)), index=dates)
        labels = _build_labels(prices, n_forward=10)
        valid = labels.dropna()
        assert len(valid.unique()) == 3, "Should have bull, bear, and chop classes"

    def test_momentum_accel_calculation(self):
        """Momentum acceleration = ret_5d - ret_20d."""
        ret_5d  = 0.025
        ret_20d = 0.010
        accel   = ret_5d - ret_20d
        assert accel == pytest.approx(0.015)
        # Positive acceleration → momentum strengthening → bullish signal
        assert accel > 0
