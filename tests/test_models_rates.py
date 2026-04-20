"""Tests for alan_trader.models.{curves, bonds, swaps}."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pytest


# ────────────────────────────────────────────────────────────────────
# Zero curve
# ────────────────────────────────────────────────────────────────────

class TestZeroCurve:

    def test_flat_curve_df_consistent(self):
        from models.curves import flat_curve
        c = flat_curve(0.05)
        # df(t) = exp(-0.05 * t)
        assert c.df(1.0) == pytest.approx(np.exp(-0.05), abs=1e-6)
        assert c.df(5.0) == pytest.approx(np.exp(-0.25), abs=1e-6)

    def test_forward_rate_flat_curve(self):
        from models.curves import flat_curve
        c = flat_curve(0.04)
        # Forward from 2y to 5y on a flat 4% curve should be 4%
        assert c.forward(2.0, 5.0) == pytest.approx(0.04, abs=1e-6)

    def test_par_swap_rate_flat_curve(self):
        """On a flat 4% curve (continuous), the par swap rate (semi-compounded)
        should be close to the equivalent semi-annual rate."""
        from models.curves import flat_curve
        c = flat_curve(0.04)
        pr = c.par_swap_rate(5, freq=2)
        # Equivalent semi-annual rate: 2*(exp(0.04/2) - 1) = 0.04040
        expected = 2 * (np.exp(0.04 / 2) - 1)
        assert pr == pytest.approx(expected, abs=5e-4)

    def test_parallel_shift(self):
        from models.curves import flat_curve
        c0 = flat_curve(0.05)
        c1 = c0.shift(50)      # +50bp
        assert c1.zero(1.0) == pytest.approx(0.055, abs=1e-6)

    def test_bootstrap_roundtrip(self):
        """Bootstrap par swap rates → curve → recompute par rates → should match.
        Dense tenor grid aligned with 6-month payment schedule → tighter match."""
        from models.curves import bootstrap_from_swaps
        tenors = [0.5, 1, 1.5, 2, 2.5, 3, 4, 5, 7, 10]
        par    = [0.045, 0.043, 0.0425, 0.042, 0.0415, 0.041, 0.040, 0.0395, 0.039, 0.038]
        curve = bootstrap_from_swaps(tenors, par, freq=2)
        # With intermediate interpolation unavoidable for some tenors, allow ~10bp
        for t, p in zip(tenors, par):
            reconstructed = curve.par_swap_rate(t, freq=2)
            assert reconstructed == pytest.approx(p, abs=1.5e-3)


# ────────────────────────────────────────────────────────────────────
# Bonds
# ────────────────────────────────────────────────────────────────────

class TestBond:

    def test_par_bond_price(self):
        """A 5y 5% semi-annual coupon bond at YTM=5% should price at par."""
        from models.bonds import bond_price_ytm
        r = bond_price_ytm(face=100, coupon_rate=0.05, freq=2, maturity=5, ytm=0.05)
        assert r["pv"] == pytest.approx(100.0, abs=1e-6)

    def test_zero_coupon_10y_5pct(self):
        """Zero-coupon 10y at 5% semi-annual: price = 100 / (1.025)^20."""
        from models.bonds import bond_price_ytm
        r = bond_price_ytm(face=100, coupon_rate=0.0, freq=2, maturity=10, ytm=0.05)
        assert r["pv"] == pytest.approx(100 / (1.025 ** 20), abs=1e-6)

    def test_bond_duration_standard(self):
        """5y 5% semi par bond — Mac duration ≈ 4.4845 years, Mod ≈ 4.3751 years.
        (The often-cited '4.376' figure is the MODIFIED duration, not Macaulay.)"""
        from models.bonds import durations
        d = durations(face=100, coupon_rate=0.05, freq=2, maturity=5, ytm=0.05)
        assert d["macaulay"] == pytest.approx(4.4845, abs=0.01)
        assert d["modified"] == pytest.approx(4.3751, abs=0.01)

    def test_bond_dv01(self):
        """DV01 ≈ mod_dur · price · 0.0001 ≈ 0.04375 for the par 5y 5% bond."""
        from models.bonds import durations
        d = durations(face=100, coupon_rate=0.05, freq=2, maturity=5, ytm=0.05)
        assert d["dv01"] == pytest.approx(0.04375, abs=0.001)

    def test_ytm_solve_roundtrip(self):
        """YTM solve should recover the original yield."""
        from models.bonds import bond_price_ytm, ytm_solve
        price = bond_price_ytm(100, 0.04, 2, 10, 0.045)["pv"]
        ytm = ytm_solve(price, 100, 0.04, 2, 10)
        assert ytm == pytest.approx(0.045, abs=1e-6)

    def test_effective_duration_curve(self):
        """Effective duration via curve bump should match modified duration at par."""
        from models.curves import flat_curve
        from models.bonds import effective_duration, durations
        c = flat_curve(0.05)
        eff = effective_duration(c, 100, 0.05, 2, 5)
        an  = durations(100, 0.05, 2, 5, 0.05)
        # Should be in the same ballpark (flat curve → close to analytic mod dur)
        assert eff["effective_duration"] == pytest.approx(an["modified"], rel=0.03)


# ────────────────────────────────────────────────────────────────────
# Swaps
# ────────────────────────────────────────────────────────────────────

class TestSwap:

    def test_swap_npv_at_par_is_zero(self):
        from models.curves import flat_curve
        from models.swaps import swap_npv, par_swap_rate
        c = flat_curve(0.04)
        par = par_swap_rate(c, 5, freq=2)
        npv = swap_npv(c, notional=10_000_000, fixed_rate=par, tenor=5,
                       fix_freq=2, flt_freq=4, pay_fixed=True)
        assert abs(npv) < 1.0  # essentially zero

    def test_swap_dv01_positive(self):
        """DV01 magnitude for $10M 5y swap should be a few $K."""
        from models.curves import flat_curve
        from models.swaps import par_swap_rate, swap_dv01
        c = flat_curve(0.04)
        par = par_swap_rate(c, 5, freq=2)
        dv01 = swap_dv01(c, 10_000_000, par, 5, 2, 4, pay_fixed=True)
        assert 3000 < abs(dv01) < 6000

    def test_swap_cashflows_structure(self):
        from models.curves import flat_curve
        from models.swaps import swap_cashflows
        c = flat_curve(0.04)
        cf = swap_cashflows(c, 10_000_000, 0.04, 5, 2, 4, pay_fixed=True)
        assert len(cf["fixed_times"]) == 10
        assert len(cf["float_times"]) == 20
        # Payer of fixed → fixed amounts negative, float amounts positive
        assert (cf["fixed_amounts"] < 0).all()
        assert (cf["float_amounts"] > 0).all()
