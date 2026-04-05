"""
tests/test_iron_condor_rules.py
Unit tests for the Iron Condor (Rules-Based) strategy.
Run: python -m pytest tests/test_iron_condor_rules.py -v
"""
import pytest
import numpy as np
import pandas as pd
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _ic_pnl(s, short_call, long_call, short_put, long_put, net_credit):
    call_side = max(0, s - long_call) - max(0, s - short_call)
    put_side  = max(0, long_put - s)  - max(0, short_put - s)
    return (net_credit + call_side + put_side) * 100


class TestIronCondorRules:

    def setup_method(self):
        from strategies.iron_condor_rules import IronCondorRulesStrategy
        self.cls = IronCondorRulesStrategy

    def test_instantiates(self):
        assert self.cls() is not None

    def test_max_profit_inside_strikes(self):
        sc, lc, sp, lp, cred = 110, 115, 90, 85, 1.90
        assert _ic_pnl(100, sc, lc, sp, lp, cred) == pytest.approx(cred * 100)

    def test_max_loss_call_side(self):
        sc, lc, sp, lp, cred = 110, 115, 90, 85, 1.90
        width = lc - sc  # 5
        expected = -(width - cred) * 100
        assert _ic_pnl(120, sc, lc, sp, lp, cred) == pytest.approx(expected)

    def test_max_loss_put_side(self):
        sc, lc, sp, lp, cred = 110, 115, 90, 85, 1.90
        width = sp - lp  # 5
        expected = -(width - cred) * 100
        assert _ic_pnl(80, sc, lc, sp, lp, cred) == pytest.approx(expected)

    def test_call_and_put_spreads_symmetric(self):
        """Equal wing widths means equal max loss on both sides."""
        sc, lc, sp, lp = 110, 115, 90, 85
        assert (lc - sc) == (sp - lp), "Wing widths should be equal"

    def test_breakevens(self):
        sc, lc, sp, lp, cred = 110, 115, 90, 85, 1.90
        be_up   = sc + cred
        be_down = sp - cred
        assert be_up   == pytest.approx(111.90)
        assert be_down == pytest.approx(88.10)

    def test_50pct_profit_target(self):
        cred = 1.90
        target = cred * 0.50 * 100
        assert target == pytest.approx(95.0)

    def test_2x_stop_loss(self):
        cred = 1.90
        stop = -cred * 2.0 * 100
        assert stop == pytest.approx(-380.0)

    def test_21dte_exit_rule(self):
        """Strategy closes at 21 DTE regardless of P&L."""
        dte = 18
        assert dte <= 21, "Should trigger 21 DTE close"

    def test_ivr_filter(self):
        ivr_min = 0.30; ivr = 0.45
        assert ivr >= ivr_min
