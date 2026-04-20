"""
Two-asset spread options — Margrabe (exchange) closed-form + Kirk approximation.
"""
from __future__ import annotations

import math

from scipy.stats import norm


def margrabe_exchange(S1: float, S2: float, T: float, sigma1: float, sigma2: float,
                       rho: float, q1: float = 0.0, q2: float = 0.0) -> float:
    """
    Exchange option — pays max(S1 − S2, 0) at expiry.
    Margrabe (1978) closed-form:
        σ_eff = √(σ₁² − 2ρσ₁σ₂ + σ₂²)
        d1    = [ln(S1/S2) + (q2 − q1 + σ_eff²/2)T] / (σ_eff √T)
        price = S1·e^{-q1 T}·N(d1) − S2·e^{-q2 T}·N(d1 − σ_eff √T)
    """
    if T <= 0:
        return float(max(S1 - S2, 0.0))
    se = math.sqrt(max(sigma1 ** 2 - 2 * rho * sigma1 * sigma2 + sigma2 ** 2, 1e-12))
    d1 = (math.log(S1 / S2) + (q2 - q1 + 0.5 * se * se) * T) / (se * math.sqrt(T))
    d2 = d1 - se * math.sqrt(T)
    return float(S1 * math.exp(-q1 * T) * norm.cdf(d1)
                 - S2 * math.exp(-q2 * T) * norm.cdf(d2))


def kirk_spread(S1: float, S2: float, K: float, T: float, r: float,
                 sigma1: float, sigma2: float, rho: float,
                 q1: float = 0.0, q2: float = 0.0, cp: str = "call") -> float:
    """
    Kirk's approximation for option on spread S1 − S2 with strike K ≠ 0.
    Transforms into an equivalent single-asset Black call/put on X = S1 / (S2 + K·e^{-rT}),
    using blended σ based on F2 ≡ S2 · e^{(r-q2)T}.
    """
    if T <= 0:
        w = 1 if cp.lower().startswith("c") else -1
        return float(max(w * (S1 - S2 - K), 0.0))

    F1 = S1 * math.exp((r - q1) * T)
    F2 = S2 * math.exp((r - q2) * T)

    b = F2 / (F2 + K)
    # Blended vol
    sigma = math.sqrt(max(sigma1 ** 2 - 2 * rho * sigma1 * sigma2 * b + (sigma2 * b) ** 2, 1e-12))
    F = F1 / (F2 + K)           # "effective forward"
    X = 1.0                     # "effective strike"
    sqT = math.sqrt(T)
    d1 = (math.log(F / X) + 0.5 * sigma * sigma * T) / (sigma * sqT)
    d2 = d1 - sigma * sqT

    disc = math.exp(-r * T)
    if cp.lower().startswith("c"):
        return float(disc * (F2 + K) * (F * norm.cdf(d1) - X * norm.cdf(d2)))
    else:
        return float(disc * (F2 + K) * (X * norm.cdf(-d2) - F * norm.cdf(-d1)))
