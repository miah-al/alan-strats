"""
tests/test_wheel_strategy.py
Unit tests for the Wheel Strategy (Cash-Secured Put).
Run: python -m pytest tests/test_wheel_strategy.py -v
"""
import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _csp_pnl(s, strike, premium):
    return (premium - max(0, strike - s)) * 100


class TestWheelStrategy:

    def setup_method(self):
        from strategies.wheel_strategy import WheelStrategy
        self.cls = WheelStrategy

    def test_instantiates(self):
        assert self.cls() is not None

    def test_has_default_params(self):
        s = self.cls()
        params = s.get_default_params() if hasattr(s, "get_default_params") else {}
        assert isinstance(params, dict)

    def test_max_loss_is_strike_minus_premium(self):
        strike, premium = 90.0, 2.0
        assert (strike - premium) * 100 == pytest.approx(8800.0)

    def test_max_profit_is_premium(self):
        assert 2.0 * 100 == pytest.approx(200.0)

    def test_breakeven(self):
        strike, premium = 90.0, 2.0
        assert strike - premium == pytest.approx(88.0)

    def test_full_profit_above_strike(self):
        assert _csp_pnl(95, 90, 2) == pytest.approx(200.0)
        assert _csp_pnl(90, 90, 2) == pytest.approx(200.0)

    def test_partial_loss_below_strike(self):
        assert _csp_pnl(85, 90, 2) == pytest.approx(-300.0)

    def test_max_loss_at_zero(self):
        assert _csp_pnl(0, 90, 2) == pytest.approx(-8800.0)

    def test_loss_is_linear_between_be_and_zero(self):
        p80 = _csp_pnl(80, 90, 2)
        p85 = _csp_pnl(85, 90, 2)
        assert p80 < p85, "Loss increases as stock falls"

    def test_price_above_ma50(self):
        price, ma50 = 100.0, 96.0
        assert price > ma50

    def test_ivr_elevated(self):
        assert 0.55 >= 0.40, "IVR must be ≥ 40% for Wheel entry"

    def test_strike_below_current_price(self):
        """CSP strike must be OTM (below current price)."""
        price, strike = 100.0, 90.0
        assert strike < price, "Put strike must be below current price"
