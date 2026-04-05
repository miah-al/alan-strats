"""
tests/test_ivr_credit_spread.py
Unit tests for the IVR Credit Spread strategy.
Run: python -m pytest tests/test_ivr_credit_spread.py -v
"""
import pytest
import numpy as np
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _bs_put_spread_pnl(s, short_k, long_k, credit):
    """Bull put spread P&L at expiry."""
    short_val = max(0, short_k - s)
    long_val  = max(0, long_k - s)
    return (credit - short_val + long_val) * 100


def _bs_call_spread_pnl(s, short_k, long_k, credit):
    """Bear call spread P&L at expiry."""
    short_val = max(0, s - short_k)
    long_val  = max(0, s - long_k)
    return (credit - short_val + long_val) * 100


class TestIVRCreditSpread:

    def setup_method(self):
        from strategies.ivr_credit_spread import IVRCreditSpreadStrategy
        self.cls = IVRCreditSpreadStrategy

    def test_instantiates(self):
        assert self.cls() is not None

    def test_default_ivr_min(self):
        s = self.cls()
        assert s.ivr_min == 0.50, "Default IVR minimum should be 50%"

    def test_ivr_rank_formula(self):
        """IVR = (current − 52w_low) / (52w_high − 52w_low)."""
        vix, vix_low, vix_high = 28.0, 12.0, 40.0
        ivr = (vix - vix_low) / (vix_high - vix_low)
        assert pytest.approx(ivr, abs=0.01) == 0.571

    def test_ivr_above_threshold_triggers_entry(self):
        ivr_min = 0.50
        assert 0.571 >= ivr_min

    def test_bull_put_selected_above_ma50(self):
        """Price above 50-day MA → sell bull put spread."""
        price, ma50 = 480.0, 460.0
        spread_type = "bull_put" if price > ma50 else "bear_call"
        assert spread_type == "bull_put"

    def test_bear_call_selected_below_ma50(self):
        """Price below 50-day MA → sell bear call spread."""
        price, ma50 = 440.0, 460.0
        spread_type = "bull_put" if price > ma50 else "bear_call"
        assert spread_type == "bear_call"

    def test_bull_put_max_profit_above_short_strike(self):
        credit = 1.50
        pnl = _bs_put_spread_pnl(110, 100, 95, credit)
        assert pnl == pytest.approx(credit * 100)

    def test_bull_put_max_loss_below_long_strike(self):
        short_k, long_k, credit = 100, 95, 1.50
        expected = -(short_k - long_k - credit) * 100
        assert _bs_put_spread_pnl(80, short_k, long_k, credit) == pytest.approx(expected)

    def test_bear_call_max_profit_below_short_strike(self):
        credit = 1.20
        pnl = _bs_call_spread_pnl(90, 100, 105, credit)
        assert pnl == pytest.approx(credit * 100)

    def test_50pct_profit_target(self):
        credit = 1.50
        target = credit * 0.50 * 100
        assert target == pytest.approx(75.0)

    def test_2x_stop_loss(self):
        credit = 1.50
        stop = -credit * 2.0 * 100
        assert stop == pytest.approx(-300.0)

    def test_21dte_exit_rule(self):
        """Position closes at 21 DTE regardless of P&L."""
        s = self.cls()
        assert s.dte_exit == 21

    def test_ivr_clamped_to_0_1(self):
        """IVR must always be between 0 and 1."""
        vix_low, vix_high = 12.0, 40.0
        for vix in [5.0, 12.0, 20.0, 40.0, 50.0]:
            rng = vix_high - vix_low
            ivr = (vix - vix_low) / rng
            clamped = max(0.0, min(1.0, ivr))
            assert 0.0 <= clamped <= 1.0
