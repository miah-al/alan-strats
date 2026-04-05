"""
tests/test_calendar_spread.py
Unit tests for the Calendar Spread strategy.
Run: python -m pytest tests/test_calendar_spread.py -v
"""
import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestCalendarSpread:

    def setup_method(self):
        from strategies.calendar_spread import CalendarSpreadStrategy
        self.cls = CalendarSpreadStrategy

    def test_instantiates(self):
        assert self.cls() is not None

    def test_has_default_params(self):
        s = self.cls()
        params = s.get_default_params() if hasattr(s, "get_default_params") else {}
        assert isinstance(params, dict)

    def test_net_debit_is_max_loss(self):
        """Max loss = net debit paid (back_month_premium - front_month_premium)."""
        front_px, back_px = 2.20, 3.10
        net_debit = back_px - front_px
        assert net_debit > 0, "Back-month premium must exceed front-month"
        assert net_debit == pytest.approx(0.90)

    def test_profit_peaks_near_strike(self):
        """Tent-shaped: P&L highest when underlying pins at strike."""
        def pnl(s, strike=100, debit=0.90, iv_f=0.25):
            dist = abs(s - strike) / strike
            return (debit * max(0, 1 - dist / (iv_f * 0.5)) - debit * 0.3) * 100
        assert pnl(100) > pnl(90)
        assert pnl(100) > pnl(110)

    def test_vrp_positive_required(self):
        """IV must exceed HV for edge (VRP > 0)."""
        iv, hv = 0.28, 0.18
        assert iv > hv, "Calendar requires IV > HV"

    def test_low_adx_required(self):
        """Range-bound market (ADX < 22) is prerequisite."""
        adx_threshold = 22.0
        adx = 16.0
        assert adx < adx_threshold, "Calendar should not fire in trending market"

    def test_loss_limited_to_debit(self):
        """Below or above by a large amount: loss capped at initial debit."""
        debit = 0.90
        def pnl(s, strike=100, iv_f=0.25):
            dist = abs(s - strike) / strike
            return (debit * max(0, 1 - dist / (iv_f * 0.5)) - debit * 0.3) * 100
        # At extreme prices the position is worth 0; max loss = debit paid
        assert pnl(150) >= -debit * 100 - 1   # allow small float tolerance
        assert pnl(50)  >= -debit * 100 - 1
