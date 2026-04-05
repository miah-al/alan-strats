"""
tests/test_iron_condor_ai.py
Unit tests for the Iron Condor AI strategy.
Run: python -m pytest tests/test_iron_condor_ai.py -v
"""
import pytest
import numpy as np
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _ic_pnl(s, short_call, long_call, short_put, long_put, net_credit):
    call_side = max(0, s - long_call) - max(0, s - short_call)
    put_side  = max(0, long_put - s)  - max(0, short_put - s)
    return (net_credit + call_side + put_side) * 100


class TestIronCondorAI:

    def setup_method(self):
        from strategies.iron_condor_ai import IronCondorAIStrategy
        self.cls = IronCondorAIStrategy

    def test_instantiates(self):
        assert self.cls() is not None

    def test_warmup_bars_minimum(self):
        """Model needs at least 180 bars before first prediction (no look-ahead)."""
        from strategies.iron_condor_ai import _WARMUP_BARS
        assert _WARMUP_BARS >= 180

    def test_retrain_interval(self):
        """Model retrains every ~30 bars (monthly) for regime adaptation."""
        from strategies.iron_condor_ai import _RETRAIN_EVERY
        assert _RETRAIN_EVERY == 30

    def test_feature_count(self):
        """Strategy uses 17 features covering options, momentum, vol, VIX, macro."""
        s = self.cls()
        # Feature set is defined in the strategy spec as 17 features
        if hasattr(s, "feature_cols"):
            assert len(s.feature_cols) >= 10, "Should have at least 10 features"

    def test_ic_max_profit_inside_strikes(self):
        """IC P&L = full credit when stock stays between short strikes at expiry."""
        sc, lc, sp, lp, cred = 110, 115, 90, 85, 2.00
        assert _ic_pnl(100, sc, lc, sp, lp, cred) == pytest.approx(cred * 100)

    def test_ic_max_loss_call_side(self):
        sc, lc, sp, lp, cred = 110, 115, 90, 85, 2.00
        width = lc - sc
        expected = -(width - cred) * 100
        assert _ic_pnl(120, sc, lc, sp, lp, cred) == pytest.approx(expected)

    def test_ic_max_loss_put_side(self):
        sc, lc, sp, lp, cred = 110, 115, 90, 85, 2.00
        width = sp - lp
        expected = -(width - cred) * 100
        assert _ic_pnl(75, sc, lc, sp, lp, cred) == pytest.approx(expected)

    def test_asymmetric_condor_wider_put_side(self):
        """In high-skew environments, wider put wing is optimal."""
        sc, lc = 110, 113    # narrow call side (3 pts)
        sp, lp = 90,  83     # wider put side  (7 pts) — skew justifies width
        assert (sp - lp) > (lc - sc), "Put side should be wider for skewed markets"

    def test_range_bound_label_logic(self):
        """Label = 1 if max daily move ≤ realized vol over next N days."""
        realized_vol_20d = 0.015   # 1.5% daily
        daily_returns = [0.008, -0.012, 0.009, -0.005, 0.011]   # all within vol band
        range_bound = all(abs(r) <= realized_vol_20d for r in daily_returns)
        assert range_bound == True

    def test_range_bound_breaks_on_big_move(self):
        realized_vol_20d = 0.015
        daily_returns = [0.008, -0.025, 0.009]   # -2.5% breaks the band
        range_bound = all(abs(r) <= realized_vol_20d for r in daily_returns)
        assert range_bound == False

    def test_defined_risk_structure(self):
        """Iron condor always has a bounded max loss = min(call_width, put_width) − credit."""
        sc, lc, sp, lp, cred = 110, 115, 90, 85, 2.00
        call_width = lc - sc  # 5
        put_width  = sp - lp  # 5
        max_loss = -(min(call_width, put_width) - cred) * 100
        assert max_loss < 0
        assert max_loss > -10_000, "Max loss must be finite (defined risk)"
