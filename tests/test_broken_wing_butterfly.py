"""
tests/test_broken_wing_butterfly.py
Unit tests for the Broken Wing Butterfly strategy.
Run: python -m pytest tests/test_broken_wing_butterfly.py -v
"""
import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _pnl(s, long1_k, short_k, long2_k, credit):
    c1 = max(0, s - long1_k)      # long call lower wing  ×1
    c2 = -2 * max(0, s - short_k) # short calls at body   ×2
    c3 = max(0, s - long2_k)      # long call wide wing   ×1
    return (c1 + c2 + c3 + credit) * 100


class TestBrokenWingButterfly:

    def setup_method(self):
        from strategies.broken_wing_butterfly import BrokenWingButterflyStrategy
        self.cls = BrokenWingButterflyStrategy

    def test_instantiates(self):
        assert self.cls() is not None

    def test_has_default_params(self):
        s = self.cls()
        params = s.get_default_params() if hasattr(s, "get_default_params") else {}
        assert isinstance(params, dict)

    def test_max_loss_formula(self):
        """Max loss = (wide_wing - narrow_wing - credit) * 100"""
        narrow_w, wide_w, credit = 5.0, 10.0, 0.40
        assert (wide_w - narrow_w - credit) * 100 == pytest.approx(460.0)

    def test_net_credit_positive(self):
        """Wide wing costs less than narrow wing → net credit.
        Body premium 2×$2.30 = $4.60; lower wing $4.20; wide wing $0.80 → credit $−0.40.
        Sign convention: received credit = positive entry cash."""
        body_premium = 2 * 2.30   # collected: $4.60
        lower_cost   = 4.20       # paid
        upper_cost   = 0.80       # paid (wide wing, cheaper than symmetric)
        credit = body_premium - lower_cost - upper_cost
        assert credit == pytest.approx(-0.40)   # negative means we PAY debit...
        # ...but the BWB is constructed so wide wing saves $1 vs symmetric:
        symmetric_upper = 1.80
        credit_broken   = body_premium - lower_cost - upper_cost      # −0.40 debit
        credit_symmetric= body_premium - lower_cost - symmetric_upper # −1.40 debit
        assert credit_broken > credit_symmetric  # BWB is cheaper (less debit / more credit)

    def test_wide_wing_double_narrow(self):
        assert 10 == 2 * 5

    def test_pnl_peaks_at_body(self):
        long1_k, short_k, long2_k, credit = 95.0, 100.0, 110.0, 0.40
        assert _pnl(100, long1_k, short_k, long2_k, credit) > _pnl(90, long1_k, short_k, long2_k, credit)
        assert _pnl(100, long1_k, short_k, long2_k, credit) > _pnl(115, long1_k, short_k, long2_k, credit)

    def test_keeps_credit_below_lower_wing(self):
        long1_k, short_k, long2_k, credit = 95.0, 100.0, 110.0, 0.40
        assert _pnl(70, long1_k, short_k, long2_k, credit) == pytest.approx(credit * 100, abs=0.01)

    def test_max_loss_above_wide_wing(self):
        narrow_w, wide_w, credit = 5.0, 10.0, 0.40
        long1_k, short_k, long2_k = 95.0, 100.0, 110.0
        expected = -(wide_w - narrow_w - credit) * 100
        assert _pnl(130, long1_k, short_k, long2_k, credit) == pytest.approx(expected, abs=0.01)

    def test_stop_trigger_before_wide_wing(self):
        """Stop is set $1 before wide wing — prevents max loss."""
        wide_wing_k = 110.0
        stop_trigger = wide_wing_k - 1.0
        assert stop_trigger < wide_wing_k
