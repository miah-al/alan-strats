"""
Stochastic-vol & implied-vol-parameterisation models.

    * SABR implied-vol (Hagan 2002)           → vol smile / skew shape
    * Heston (Lewis/Lipton characteristic-fn) → true stochastic vol
    * Variance swap fair-variance replication → log-contract / VIX intuition
"""
from __future__ import annotations

import math
from typing import Callable

import numpy as np
from scipy.integrate import quad

from .options import bs_price


# ═══════════════════════════════════════════════════════════════════════════
# SABR — Hagan 2002 asymptotic expansion for implied Black vol σ_B(K, F)
# ═══════════════════════════════════════════════════════════════════════════

def sabr_implied_vol(F: float, K: float, T: float, alpha: float, beta: float,
                     rho: float, nu: float) -> float:
    """
    Hagan-Kumar-Lesniewski-Woodward (2002) SABR implied-vol approximation.
    Returns the Black volatility σ_B such that Black-76 price matches SABR price.
    """
    if F <= 0 or K <= 0 or T <= 0 or alpha <= 0:
        return 0.0
    if abs(F - K) < 1e-12:
        # ATM shortcut (avoid log singularity)
        FK_b = F ** (1 - beta)
        term1 = alpha / FK_b
        corr = (
            ((1 - beta) ** 2 / 24) * (alpha ** 2) / (FK_b ** 2)
            + 0.25 * rho * beta * nu * alpha / FK_b
            + ((2 - 3 * rho ** 2) / 24) * nu ** 2
        )
        return float(term1 * (1 + corr * T))

    logFK = math.log(F / K)
    FK_pow = (F * K) ** ((1 - beta) / 2)
    z = (nu / alpha) * FK_pow * logFK
    # χ(z)
    try:
        x_z = math.log((math.sqrt(1 - 2 * rho * z + z * z) + z - rho) / (1 - rho))
    except ValueError:
        x_z = 1e-12
    if abs(x_z) < 1e-12:
        x_z = 1e-12

    denom = FK_pow * (1
                      + ((1 - beta) ** 2 / 24) * logFK ** 2
                      + ((1 - beta) ** 4 / 1920) * logFK ** 4)
    pref = alpha / denom
    corr = (
        ((1 - beta) ** 2 / 24) * (alpha ** 2) / (FK_pow ** 2)
        + 0.25 * rho * beta * nu * alpha / FK_pow
        + ((2 - 3 * rho ** 2) / 24) * nu ** 2
    )
    sigma_b = pref * (z / x_z) * (1 + corr * T)
    return float(sigma_b)


def sabr_price(F: float, K: float, T: float, alpha: float, beta: float,
               rho: float, nu: float, r: float, cp: str = "call") -> float:
    """SABR price via implied vol → Black-76."""
    from .options import black76_price
    sig_b = sabr_implied_vol(F, K, T, alpha, beta, rho, nu)
    return black76_price(F, K, T, r, max(sig_b, 1e-6), cp)


def sabr_smile(F: float, T: float, strikes: np.ndarray,
               alpha: float, beta: float, rho: float, nu: float) -> np.ndarray:
    """Vectorised implied-vol smile across strikes."""
    return np.array([sabr_implied_vol(F, K, T, alpha, beta, rho, nu) for K in strikes])


# ═══════════════════════════════════════════════════════════════════════════
# Heston (1993) — closed-form via characteristic-function integration
# ═══════════════════════════════════════════════════════════════════════════

def _heston_char_fn(phi: complex, S: float, K: float, T: float, r: float, q: float,
                    v0: float, kappa: float, theta: float, sigma_v: float, rho: float,
                    j: int) -> complex:
    """Heston characteristic function (Schoutens simplified form)."""
    if j == 1:
        u = 0.5
        b = kappa - rho * sigma_v
    else:
        u = -0.5
        b = kappa
    a = kappa * theta
    d = np.sqrt((rho * sigma_v * phi * 1j - b) ** 2 - sigma_v ** 2
                * (2 * u * phi * 1j - phi * phi))
    g = (b - rho * sigma_v * phi * 1j + d) / (b - rho * sigma_v * phi * 1j - d)
    C = (r - q) * phi * 1j * T + (a / sigma_v ** 2) * (
        (b - rho * sigma_v * phi * 1j + d) * T
        - 2 * np.log((1 - g * np.exp(d * T)) / (1 - g))
    )
    D = ((b - rho * sigma_v * phi * 1j + d) / sigma_v ** 2) \
        * ((1 - np.exp(d * T)) / (1 - g * np.exp(d * T)))
    return np.exp(C + D * v0 + 1j * phi * math.log(S))


def heston_price(S: float, K: float, T: float, r: float, q: float,
                 v0: float, kappa: float, theta: float, sigma_v: float, rho: float,
                 cp: str = "call",
                 upper: float = 100.0) -> float:
    """
    Heston European call via numerical inversion of characteristic function.
    P_j = 0.5 + (1/π) ∫₀^∞ Re[e^{-iφ ln K} · f_j(φ) / (iφ)] dφ
    call = S·e^{-qT}·P₁ − K·e^{-rT}·P₂;  put via parity.
    """
    lnK = math.log(K)

    def integrand(phi, j):
        f = _heston_char_fn(phi, S, K, T, r, q, v0, kappa, theta, sigma_v, rho, j)
        val = np.exp(-1j * phi * lnK) * f / (1j * phi)
        return float(val.real)

    P1, _ = quad(integrand, 1e-6, upper, args=(1,), limit=200)
    P2, _ = quad(integrand, 1e-6, upper, args=(2,), limit=200)
    P1 = 0.5 + P1 / math.pi
    P2 = 0.5 + P2 / math.pi

    call = S * math.exp(-q * T) * P1 - K * math.exp(-r * T) * P2
    if cp.lower().startswith("c"):
        return float(max(call, 0.0))
    # put via parity: P = C - S·e^{-qT} + K·e^{-rT}
    return float(max(call - S * math.exp(-q * T) + K * math.exp(-r * T), 0.0))


# ═══════════════════════════════════════════════════════════════════════════
# Variance swap — replication via log-contract + vanilla strip
# ═══════════════════════════════════════════════════════════════════════════

def variance_swap_fair_variance(S0: float, T: float, r: float, q: float,
                                 strikes: np.ndarray, ivs: np.ndarray,
                                 S_star: float | None = None) -> float:
    """
    Fair variance (annualised σ²) of a variance swap replicated by:
      - Short 1/S* forward + cash  +  long 1/K² puts (K<S*) + 1/K² calls (K>S*)
    S_star: reference strike (default = F = S0 · e^(r-q)T)

    Returns K_var = fair variance. The fair vol-swap strike ≈ √K_var (biased).
    """
    S0 = float(S0); T = float(T); r = float(r); q = float(q)
    F = S0 * math.exp((r - q) * T)
    if S_star is None:
        S_star = F

    # Forward-adjusted base term (Demeterfi-Derman-Kamal-Zou eq. A.2)
    base = (2.0 / T) * (
        r * T - (S0 / S_star) * math.exp(r * T) + 1.0 - math.log(S_star / S0)
    )

    # Replication integral ≈ Σ (ΔK / K²) · PV_option(K, iv(K)) · e^{rT}
    strikes = np.asarray(strikes, float)
    ivs     = np.asarray(ivs,     float)
    order = np.argsort(strikes)
    strikes = strikes[order]; ivs = ivs[order]
    dk = np.gradient(strikes)

    replication = 0.0
    for K, iv, delta_k in zip(strikes, ivs, dk):
        if iv <= 0 or K <= 0 or delta_k <= 0:
            continue
        if K <= S_star:
            opt_type = "put"
        else:
            opt_type = "call"
        price = bs_price(S0, K, T, r, q, iv, opt_type)
        replication += (delta_k / (K * K)) * price
    replication *= (2.0 / T) * math.exp(r * T)

    return float(base + replication)
