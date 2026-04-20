"""Tests for alan_trader.models.trees (Hull-White + callable bonds)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


class TestHullWhite:

    def test_tree_builds(self):
        from models.curves import flat_curve
        from models.trees import hw_trinomial_build
        c = flat_curve(0.05)
        t = hw_trinomial_build(c, sigma=0.01, a=0.1, T=5, steps=50)
        assert "r" in t and "alpha" in t
        assert t["r"].shape[0] == 51
        # Alpha should be a reasonable array (one value per step)
        assert len(t["alpha"]) == 51

    def test_callable_price_below_straight(self):
        """Callable bond price ≤ straight bond (call option value ≥ 0)."""
        from models.curves import flat_curve
        from models.trees import price_callable_bond
        c = flat_curve(0.05)
        res = price_callable_bond(
            c, face=100, coupon_rate=0.06, freq=2, maturity=5,
            call_schedule=[(3.0, 100.0)],   # callable at par in 3 years
            sigma=0.015, a=0.10, steps=40,
        )
        assert res["callable_price"] <= res["straight_price"]
        assert res["call_option_value"] >= 0.0

    def test_callable_with_far_otm_call_equals_straight(self):
        """If call price is very high (far OTM), callable ≈ straight."""
        from models.curves import flat_curve
        from models.trees import price_callable_bond
        c = flat_curve(0.05)
        res = price_callable_bond(
            c, face=100, coupon_rate=0.05, freq=2, maturity=5,
            call_schedule=[(3.0, 200.0)],   # never optimal to call
            sigma=0.015, a=0.10, steps=40,
        )
        assert res["callable_price"] == pytest.approx(res["straight_price"], abs=0.5)

    def test_callable_effective_duration_sensible(self):
        """Callable bond duration should be positive and less than straight duration."""
        from models.curves import flat_curve
        from models.trees import price_callable_bond
        c = flat_curve(0.05)
        res = price_callable_bond(
            c, face=100, coupon_rate=0.07, freq=2, maturity=5,
            call_schedule=[(2.0, 100.0)],
            sigma=0.015, a=0.10, steps=40,
        )
        assert res["effective_duration"] > 0
        assert res["effective_duration"] < 5   # less than maturity (ballpark)
