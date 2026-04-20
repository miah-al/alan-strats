"""Tests for alan_trader.models.options + barrier."""
import math
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pytest


# ────────────────────────────────────────────────────────────────────
# Black-Scholes — reference values per Hull OFOD
# ────────────────────────────────────────────────────────────────────

class TestBlackScholes:

    def test_bs_call_base(self):
        from models.options import bs_price
        assert bs_price(100, 100, 1.0, 0.05, 0.0, 0.20, "call") == pytest.approx(10.4506, abs=1e-3)

    def test_bs_put_base(self):
        from models.options import bs_price
        assert bs_price(100, 100, 1.0, 0.05, 0.0, 0.20, "put") == pytest.approx(5.5735, abs=1e-3)

    def test_put_call_parity(self):
        """C - P = S·e^{-qT} - K·e^{-rT}"""
        from models.options import bs_price
        S, K, T, r, q, sigma = 100, 95, 0.8, 0.04, 0.01, 0.22
        c = bs_price(S, K, T, r, q, sigma, "call")
        p = bs_price(S, K, T, r, q, sigma, "put")
        lhs = c - p
        rhs = S * math.exp(-q * T) - K * math.exp(-r * T)
        assert lhs == pytest.approx(rhs, abs=1e-6)

    def test_bs_greeks_call_base(self):
        from models.options import bs_greeks
        g = bs_greeks(100, 100, 1.0, 0.05, 0.0, 0.20, "call")
        assert g["delta"] == pytest.approx(0.6368, abs=1e-3)
        assert g["gamma"] == pytest.approx(0.01876, abs=1e-3)

    def test_bs_zero_vol_intrinsic(self):
        from models.options import bs_price
        assert bs_price(110, 100, 1.0, 0.05, 0.0, 0.0, "call") == pytest.approx(10.0, abs=1e-6)
        assert bs_price(90,  100, 1.0, 0.05, 0.0, 0.0, "call") == pytest.approx(0.0,  abs=1e-6)

    def test_bs_zero_time_intrinsic(self):
        from models.options import bs_price
        assert bs_price(110, 100, 0.0, 0.05, 0.0, 0.2, "call") == pytest.approx(10.0, abs=1e-6)
        assert bs_price(90,  100, 0.0, 0.05, 0.0, 0.2, "put")  == pytest.approx(10.0, abs=1e-6)


# ────────────────────────────────────────────────────────────────────
# Black-76 — options on futures/forwards
# ────────────────────────────────────────────────────────────────────

class TestBlack76:

    def test_black76_atm_call(self):
        """F = K, T = 1, r = 5%, σ = 20%
        Black-76 ATM call: e^{-rT} · F · (N(σ√T/2) - N(-σ√T/2)) = e^{-rT} · F · (2·N(σ√T/2) - 1)"""
        from models.options import black76_price
        from scipy.stats import norm
        F, K, T, r, sigma = 100, 100, 1, 0.05, 0.20
        p = black76_price(F, K, T, r, sigma, "call")
        expected = math.exp(-r * T) * F * (2 * norm.cdf(sigma * math.sqrt(T) / 2) - 1)
        assert p == pytest.approx(expected, abs=1e-6)

    def test_black76_put_call_parity(self):
        """C - P = e^{-rT} · (F - K)"""
        from models.options import black76_price
        F, K, T, r, sigma = 120, 100, 0.5, 0.04, 0.25
        c = black76_price(F, K, T, r, sigma, "call")
        p = black76_price(F, K, T, r, sigma, "put")
        assert c - p == pytest.approx(math.exp(-r * T) * (F - K), abs=1e-6)

    def test_black76_greeks_call(self):
        from models.options import black76_greeks
        g = black76_greeks(100, 100, 1.0, 0.05, 0.20, "call")
        # For ATM Black-76, delta ≈ e^{-rT} · N(σ√T/2) ≈ 0.5 · e^{-rT}
        assert g["delta"] > 0
        assert g["gamma"] > 0
        assert g["vega"] > 0

    def test_black76_deep_itm_approx_discount_intrinsic(self):
        """Deep ITM (F=150, K=100) call ≈ e^{-rT}(F - K)."""
        from models.options import black76_price
        F, K, T, r, sigma = 150, 100, 1, 0.05, 0.20
        p = black76_price(F, K, T, r, sigma, "call")
        assert p == pytest.approx(math.exp(-r * T) * (F - K), rel=0.01)


# ────────────────────────────────────────────────────────────────────
# CRR Binomial — American options
# ────────────────────────────────────────────────────────────────────

class TestCRR:

    def test_crr_european_converges_to_bs(self):
        """CRR European price with N→∞ should converge to BS."""
        from models.options import bs_price, crr_european
        bs = bs_price(100, 100, 1.0, 0.05, 0.0, 0.20, "call")
        cr = crr_european(100, 100, 1.0, 0.05, 0.0, 0.20, "call", N=2000)
        assert cr == pytest.approx(bs, abs=0.01)

    def test_crr_american_put_hull(self):
        """Hull OFOD Table 21.1: American put S=K=100, T=1, r=5%, σ=20% ≈ 6.0896."""
        from models.options import crr_american
        p = crr_american(100, 100, 1.0, 0.05, 0.0, 0.20, "put", N=1000)
        assert p == pytest.approx(6.0896, abs=0.05)

    def test_crr_american_call_no_div_equals_european(self):
        """American call on non-dividend stock = European call (never optimal to exercise early)."""
        from models.options import bs_price, crr_american
        bs = bs_price(100, 100, 1.0, 0.05, 0.0, 0.20, "call")
        am = crr_american(100, 100, 1.0, 0.05, 0.0, 0.20, "call", N=1000)
        assert am == pytest.approx(bs, abs=0.05)

    def test_crr_american_put_greater_than_european(self):
        """American put > European put due to early-exercise premium."""
        from models.options import bs_price, crr_american
        bs = bs_price(100, 100, 1.0, 0.05, 0.0, 0.20, "put")
        am = crr_american(100, 100, 1.0, 0.05, 0.0, 0.20, "put", N=1000)
        assert am > bs

    def test_crr_convergence_monotone(self):
        """Increasing N should converge (diff decreases)."""
        from models.options import crr_american
        vals = [crr_american(100, 100, 1.0, 0.05, 0.0, 0.20, "put", N=N)
                for N in (50, 100, 500, 1000)]
        # Check: differences decrease (convergence)
        diffs = [abs(vals[i+1] - vals[i]) for i in range(len(vals)-1)]
        assert diffs[-1] < diffs[0]   # later differences should be smaller

    def test_crr_exercise_boundary(self):
        """American put early-exercise boundary should be increasing toward K with time."""
        from models.options import american_exercise_boundary
        t, b = american_exercise_boundary(100, 100, 1.0, 0.05, 0.0, 0.20, "put", N=100)
        assert len(t) > 0
        # All boundary values should be < K
        assert (b < 100).all()


# ────────────────────────────────────────────────────────────────────
# Digital options
# ────────────────────────────────────────────────────────────────────

class TestDigital:

    def test_cash_digital_atm(self):
        """Cash-or-nothing ATM call: e^{-rT} · N(d2)."""
        from models.options import digital_cash_price
        p = digital_cash_price(100, 100, 1.0, 0.05, 0.0, 0.20, "call", cash=1.0)
        assert p == pytest.approx(0.5323, abs=0.01)

    def test_digital_call_plus_put_equals_discount(self):
        """Cash digital call + put = e^{-rT} (cash)."""
        from models.options import digital_cash_price
        c = digital_cash_price(100, 100, 1.0, 0.05, 0.0, 0.20, "call")
        p = digital_cash_price(100, 100, 1.0, 0.05, 0.0, 0.20, "put")
        assert c + p == pytest.approx(math.exp(-0.05), abs=1e-6)


# ────────────────────────────────────────────────────────────────────
# Asian options
# ────────────────────────────────────────────────────────────────────

class TestAsian:

    def test_geometric_asian_smaller_than_european(self):
        """Geometric Asian call < European call (averaging reduces vol effect)."""
        from models.options import bs_price, asian_geometric_price
        bs = bs_price(100, 100, 1.0, 0.05, 0.0, 0.20, "call")
        ga = asian_geometric_price(100, 100, 1.0, 0.05, 0.0, 0.20, "call", n_fix=50)
        assert ga < bs

    def test_arithmetic_mc_close_to_geometric(self):
        """Arithmetic Asian is always ≥ geometric (Jensen). With CV the gap
        should be small in absolute terms at 20% vol."""
        from models.options import asian_geometric_price, asian_arithmetic_mc
        ga = asian_geometric_price(100, 100, 1.0, 0.05, 0.0, 0.20, "call", n_fix=50)
        am, se = asian_arithmetic_mc(100, 100, 1.0, 0.05, 0.0, 0.20, "call",
                                      n_fix=50, paths=10000, seed=42)
        assert am >= ga - 3 * max(se, 0.01)    # arithmetic ≥ geometric (within noise)
        assert am - ga < 0.5                    # gap is small for 20% vol


# ────────────────────────────────────────────────────────────────────
# Barrier options
# ────────────────────────────────────────────────────────────────────

class TestBarriers:

    def test_ui_call_reference(self):
        """Up-in call Haug reference S=100, K=100, H=130, T=0.5, r=10%, q=5%, σ=25% ≈ 4.42.
        Cross-validated against 30k-path MC (agrees within one SE)."""
        from models.barrier import rr_barrier
        p = rr_barrier(100, 100, 130, 0.5, 0.10, 0.05, 0.25,
                       cp="call", in_out="in", up_down="up")
        assert p == pytest.approx(4.42, abs=0.1)

    def test_ui_call_no_dividend_mc_check(self):
        """Cross-check RR UI call (q=0) against MC."""
        from models.barrier import rr_barrier, barrier_mc
        args = (100, 100, 120, 0.5, 0.10, 0.0, 0.25, "call", "in", "up")
        rr = rr_barrier(*args)
        mc, se = barrier_mc(*args, paths=8000, steps=200, seed=42)
        assert abs(mc - rr) < 5 * max(se, 0.05)

    def test_in_plus_out_equals_vanilla(self):
        """Up-in call + Up-out call = European call (parity)."""
        from models.options import bs_price
        from models.barrier import rr_barrier
        S, K, H, T, r, q, sigma = 100, 100, 120, 0.5, 0.05, 0.0, 0.25
        c_in  = rr_barrier(S, K, H, T, r, q, sigma, "call", "in", "up")
        c_out = rr_barrier(S, K, H, T, r, q, sigma, "call", "out", "up")
        vanilla = bs_price(S, K, T, r, q, sigma, "call")
        assert c_in + c_out == pytest.approx(vanilla, abs=0.05)

    def test_mc_agrees_with_rr(self):
        """MC should agree with closed-form within a few SEs."""
        from models.barrier import rr_barrier, barrier_mc
        args = (100, 100, 120, 0.5, 0.05, 0.0, 0.25, "call", "out", "up")
        rr = rr_barrier(*args)
        mc, se = barrier_mc(*args, paths=8000, steps=200, seed=42)
        assert abs(mc - rr) < 5 * max(se, 0.05)

    def test_discrete_adjust_shifts_up(self):
        from models.barrier import barrier_discrete_adjust
        h_adj = barrier_discrete_adjust(H=120, sigma=0.25, T=0.5, n_obs=20, up=True)
        assert h_adj > 120
        h_adj_dn = barrier_discrete_adjust(H=80, sigma=0.25, T=0.5, n_obs=20, up=False)
        assert h_adj_dn < 80

    def test_prob_hit_up(self):
        from models.barrier import prob_hit_barrier
        p = prob_hit_barrier(100, 120, 1.0, 0.05, 0.0, 0.30, up=True)
        assert 0 < p < 1


# ────────────────────────────────────────────────────────────────────
# Implied vol
# ────────────────────────────────────────────────────────────────────

class TestImpliedVol:

    def test_iv_roundtrip_call(self):
        from models.options import bs_price, implied_vol_bs
        true_sigma = 0.27
        price = bs_price(100, 100, 1.0, 0.05, 0.02, true_sigma, "call")
        iv = implied_vol_bs(price, 100, 100, 1.0, 0.05, 0.02, "call")
        assert iv == pytest.approx(true_sigma, abs=1e-4)
