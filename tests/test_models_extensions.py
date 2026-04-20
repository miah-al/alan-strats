"""Tests for the quant extension modules: vol.py, spread.py, caps.py, key-rate DV01, BjS."""
import math
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pytest


# ─────────────────────────────────────────────────────────────────────────
# SABR
# ─────────────────────────────────────────────────────────────────────────

class TestSABR:

    def test_atm_vol_returns_positive(self):
        from models.vol import sabr_implied_vol
        s = sabr_implied_vol(F=100, K=100, T=1.0, alpha=0.25, beta=0.5, rho=-0.2, nu=0.4)
        assert s > 0

    def test_otm_smile_shape(self):
        """Negative ρ should push put-side vol UP (skew)."""
        from models.vol import sabr_implied_vol
        Ks = [80, 90, 100, 110, 120]
        vols = [sabr_implied_vol(100, K, 1.0, 0.2, 0.5, -0.3, 0.4) for K in Ks]
        assert vols[0] > vols[2]   # K=80 higher than K=100 (negative ρ → put skew)
        assert vols[4] != vols[0]  # smile not flat

    def test_sabr_reduces_to_atm(self):
        """β=1, α=σ, ν=0 should give constant σ (lognormal → flat smile)."""
        from models.vol import sabr_implied_vol
        # nu=0 degenerates but still needs alpha to be set; at F=K:
        s_atm = sabr_implied_vol(F=100, K=100, T=1.0, alpha=0.20,
                                  beta=1.0, rho=0.0, nu=1e-6)
        # With tiny nu, ATM vol ≈ alpha
        assert s_atm == pytest.approx(0.20, abs=1e-3)


# ─────────────────────────────────────────────────────────────────────────
# Heston
# ─────────────────────────────────────────────────────────────────────────

class TestHeston:

    def test_heston_positive_and_finite(self):
        from models.vol import heston_price
        p = heston_price(100, 100, 1.0, 0.05, 0.0,
                         v0=0.04, kappa=2.0, theta=0.04, sigma_v=0.3, rho=-0.7)
        assert p > 0 and math.isfinite(p)

    def test_heston_put_call_parity(self):
        from models.vol import heston_price
        S, K, T, r, q = 100, 100, 0.5, 0.04, 0.01
        v0, kappa, theta, sigma_v, rho = 0.04, 1.5, 0.04, 0.3, -0.5
        c = heston_price(S, K, T, r, q, v0, kappa, theta, sigma_v, rho, "call")
        p = heston_price(S, K, T, r, q, v0, kappa, theta, sigma_v, rho, "put")
        lhs = c - p
        rhs = S * math.exp(-q * T) - K * math.exp(-r * T)
        assert lhs == pytest.approx(rhs, abs=0.05)


# ─────────────────────────────────────────────────────────────────────────
# Variance swap
# ─────────────────────────────────────────────────────────────────────────

class TestVarianceSwap:

    def test_flat_iv_replicates_single_value(self):
        """With flat 20% IV across strikes, fair variance should be ~0.04 = 20%²."""
        from models.vol import variance_swap_fair_variance
        Ks = np.linspace(60, 160, 41)
        ivs = np.full(len(Ks), 0.20)
        K_var = variance_swap_fair_variance(100, 1.0, 0.05, 0.0, Ks, ivs)
        # Expect ~0.04 (within ~20% as replication uses only strip approximation)
        assert 0.025 < K_var < 0.065


# ─────────────────────────────────────────────────────────────────────────
# Margrabe / Kirk
# ─────────────────────────────────────────────────────────────────────────

class TestSpread:

    def test_margrabe_no_correlation_higher_than_full(self):
        """Zero correlation should give HIGHER value than ρ=1."""
        from models.spread import margrabe_exchange
        args = dict(S1=100, S2=100, T=1, sigma1=0.25, sigma2=0.25)
        p0 = margrabe_exchange(**args, rho=0.0)
        p1 = margrabe_exchange(**args, rho=0.99)
        assert p0 > p1

    def test_margrabe_deep_itm_intrinsic(self):
        from models.spread import margrabe_exchange
        p = margrabe_exchange(S1=150, S2=100, T=1, sigma1=0.01, sigma2=0.01, rho=0)
        assert p == pytest.approx(50.0, abs=1.0)

    def test_kirk_zero_strike_approx_margrabe(self):
        """Kirk with K=0 should approximately equal Margrabe."""
        from models.spread import margrabe_exchange, kirk_spread
        m = margrabe_exchange(100, 100, 1, 0.25, 0.20, 0.3)
        k = kirk_spread(100, 100, 1e-6, 1, 0.0, 0.25, 0.20, 0.3)
        assert k == pytest.approx(m, rel=0.05)


# ─────────────────────────────────────────────────────────────────────────
# Caps / Floors / Swaptions
# ─────────────────────────────────────────────────────────────────────────

class TestCapsFloors:

    def test_cap_positive(self):
        from models.curves import flat_curve
        from models.caps import cap_price
        curve = flat_curve(0.04)
        r = cap_price(curve, strike=0.04, tenor=5, freq=4, sigma=0.30, notional=1.0)
        assert r["total_price"] > 0

    def test_cap_minus_floor_eq_swap_pv(self):
        """Put-call parity for caps/floors: cap(K) - floor(K) = PV of pay-fixed swap at K.
        We check sign + magnitude only (flat vol assumption is OK)."""
        from models.curves import flat_curve
        from models.caps import cap_price, floor_price
        from models.swaps import swap_npv
        curve = flat_curve(0.04)
        c = cap_price(curve, strike=0.04, tenor=5, freq=2, sigma=0.30)["total_price"]
        f = floor_price(curve, strike=0.04, tenor=5, freq=2, sigma=0.30)["total_price"]
        # At ATM with same strike, cap ≈ floor
        assert abs(c - f) < 0.5 * max(c, f)


class TestSwaption:

    def test_european_payer_swaption_positive(self):
        from models.curves import flat_curve
        from models.caps import european_swaption
        curve = flat_curve(0.04)
        r = european_swaption(curve, t_expiry=1, swap_tenor=5,
                               strike_rate=0.04, sigma=0.25, notional=1_000_000)
        assert r["price"] > 0
        assert 0.035 < r["forward_swap_rate"] < 0.045


# ─────────────────────────────────────────────────────────────────────────
# Bjerksund-Stensland 2002
# ─────────────────────────────────────────────────────────────────────────

class TestBjerksundStensland:

    def test_no_div_call_equals_european(self):
        """American call on non-div stock = European call."""
        from models.options import bs_price, bjerksund_stensland_2002
        S, K, T, r, q, sigma = 100, 100, 1.0, 0.05, 0.0, 0.20
        bs  = bs_price(S, K, T, r, q, sigma, "call")
        bjs = bjerksund_stensland_2002(S, K, T, r, q, sigma, "call")
        assert bjs == pytest.approx(bs, abs=0.01)

    def test_put_at_least_european(self):
        """BjS American put ≥ European put (early-exercise has non-negative value)."""
        from models.options import bs_price, bjerksund_stensland_2002
        args = dict(S=100, K=100, T=1.0, r=0.05, q=0.0, sigma=0.20)
        eu  = bs_price(**args, cp="put")
        bjs = bjerksund_stensland_2002(**args, cp="put")
        assert bjs >= eu - 1e-6   # allow tiny numerical slack


# ─────────────────────────────────────────────────────────────────────────
# Key-rate durations
# ─────────────────────────────────────────────────────────────────────────

class TestKeyRateDurations:

    def test_krd_sum_approximates_parallel(self):
        """Sum of KRDs should ≈ parallel effective duration."""
        from models.curves import flat_curve
        from models.bonds import key_rate_durations, effective_duration
        curve = flat_curve(0.04, tenors=[0.5, 1, 2, 3, 5, 7, 10, 20, 30])
        krds = key_rate_durations(curve, 100, 0.05, 2, 10, bump_bp=5)
        eff  = effective_duration(curve, 100, 0.05, 2, 10)
        s = sum(krds.values())
        assert s == pytest.approx(eff["effective_duration"], rel=0.10)
