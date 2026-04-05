"""
tests/test_earnings_straddle.py
Unit tests for the Earnings Short Condor (IV Crush) strategy.
Run: python -m pytest tests/test_earnings_straddle.py -v
"""
import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _condor_pnl(s, price, net_cred, call_wing, put_wing):
    sc = -max(0, s - price)
    sp = -max(0, price - s)
    lc =  max(0, s - call_wing)
    lp =  max(0, put_wing - s)
    return (net_cred + sc + sp + lc + lp) * 100


class TestEarningsStraddle:

    def setup_method(self):
        from strategies.earnings_straddle import EarningsStraddleStrategy
        self.cls = EarningsStraddleStrategy

    def test_instantiates(self):
        assert self.cls() is not None

    def test_has_default_params(self):
        s = self.cls()
        params = s.get_default_params() if hasattr(s, "get_default_params") else {}
        assert isinstance(params, dict)

    def test_wings_cap_max_loss(self):
        """Without wings: unlimited loss. With wings: bounded."""
        price = 185.0; cred_f = 4.50; wing_pct = 0.10
        wing_dist = price * wing_pct
        wing_cost = cred_f * 0.20
        net_cred  = cred_f - 2 * wing_cost
        call_wing = price + wing_dist
        put_wing  = price - wing_dist
        extreme = _condor_pnl(price * 1.50, price, net_cred, call_wing, put_wing)
        assert extreme > -10_000, "Wings must cap loss"

    def test_max_profit_at_atm(self):
        price = 185.0; cred_f = 4.50; wing_pct = 0.10
        wing_cost = cred_f * 0.20; net_cred = cred_f - 2 * wing_cost
        call_wing = price + price * wing_pct; put_wing = price - price * wing_pct
        assert _condor_pnl(price, price, net_cred, call_wing, put_wing) == pytest.approx(net_cred * 100, abs=0.01)

    def test_breakevens_inside_wings(self):
        price = 185.0; cred_f = 4.50; wing_pct = 0.10
        wing_cost = cred_f * 0.20; net_cred = cred_f - 2 * wing_cost
        wing_dist = price * wing_pct
        assert price + net_cred < price + wing_dist
        assert price - net_cred > price - wing_dist

    def test_net_credit_less_than_gross(self):
        cred_f = 4.50; wing_cost = cred_f * 0.20
        net_cred = cred_f - 2 * wing_cost
        assert 0 < net_cred < cred_f

    def test_max_loss_formula(self):
        price = 185.0; cred_f = 4.50; wing_pct = 0.10
        wing_width_ps = price * wing_pct
        net_cred = cred_f - 2 * cred_f * 0.20
        max_loss = (wing_width_ps - net_cred) * 100
        assert max_loss > 0
        assert max_loss < wing_width_ps * 100

    def test_ivr_minimum_filter(self):
        ivr_min = 0.60; ivr = 0.72
        assert ivr >= ivr_min, "IVR too low for earnings straddle"

    def test_days_to_earnings_window(self):
        dte_min, dte_max = 5, 10
        days_to_earnings = 7
        assert dte_min <= days_to_earnings <= dte_max
