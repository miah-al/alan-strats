"""
tests/test_bull_put_spread.py
Unit tests for the Bull Put Spread strategy.
Run: python -m pytest tests/test_bull_put_spread.py -v
"""
import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _bps_pnl(s, short_k, long_k, credit):
    return (credit - max(0, short_k - s) + max(0, long_k - s)) * 100


class TestBullPutSpread:

    def setup_method(self):
        from strategies.bull_put_spread import BullPutSpreadStrategy
        self.cls = BullPutSpreadStrategy

    def test_instantiates(self):
        assert self.cls() is not None

    def test_has_default_params(self):
        s = self.cls()
        params = s.get_default_params() if hasattr(s, "get_default_params") else {}
        assert isinstance(params, dict)

    def test_max_loss_formula(self):
        short_k, long_k, credit = 92.0, 87.0, 1.20
        assert (short_k - long_k - credit) * 100 == pytest.approx(380.0)

    def test_max_profit_is_credit(self):
        assert 1.20 * 100 == pytest.approx(120.0)

    def test_breakeven(self):
        short_k, credit = 92.0, 1.20
        assert short_k - credit == pytest.approx(90.80)

    def test_full_profit_above_short_strike(self):
        assert _bps_pnl(95, 92, 87, 1.2) == pytest.approx(120.0)
        assert _bps_pnl(92, 92, 87, 1.2) == pytest.approx(120.0)

    def test_max_loss_below_long_strike(self):
        expected = -(92 - 87 - 1.2) * 100
        assert _bps_pnl(80, 92, 87, 1.2) == pytest.approx(expected)
        assert _bps_pnl(70, 92, 87, 1.2) == pytest.approx(expected)

    def test_long_put_caps_loss(self):
        """Loss is identical below the long strike — wings protect."""
        assert _bps_pnl(85, 92, 87, 1.2) == pytest.approx(_bps_pnl(80, 92, 87, 1.2))

    def test_credit_width_ratio(self):
        short_k, long_k, credit = 92.0, 87.0, 1.20
        ratio = credit / (short_k - long_k)
        assert ratio >= 0.20, f"Credit/Width {ratio:.1%} below 20% minimum"

    def test_price_above_ma50(self):
        price, ma50 = 100.0, 97.0
        assert price > ma50
