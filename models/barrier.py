"""
Barrier options — Reiner-Rubinstein closed-form + Broadie-Glasserman-Kou
discrete-monitoring adjustment + Monte Carlo verification.

Barrier taxonomy:
    in_out   : 'in'   (knock-in)  or 'out' (knock-out)
    up_down  : 'up'   (barrier above spot)  or 'down' (barrier below)
    cp       : 'call' or 'put'
    → 8 combinations: UIC, UOC, DIC, DOC, UIP, UOP, DIP, DOP
"""
from __future__ import annotations

import math
from typing import Literal

import numpy as np
from scipy.stats import norm

from .options import bs_price, _cp_sign


def _phi(S, K, H, T, r, q, sigma, phi_sign, eta_sign):
    """Reiner-Rubinstein component function (Haug, 1997)."""
    mu    = (r - q - 0.5 * sigma * sigma) / (sigma * sigma)
    lam   = math.sqrt(mu * mu + 2 * r / (sigma * sigma))
    sqT   = math.sqrt(T)
    x1    = math.log(S / K) / (sigma * sqT) + (1 + mu) * sigma * sqT
    x2    = math.log(S / H) / (sigma * sqT) + (1 + mu) * sigma * sqT
    y1    = math.log(H * H / (S * K)) / (sigma * sqT) + (1 + mu) * sigma * sqT
    y2    = math.log(H / S) / (sigma * sqT) + (1 + mu) * sigma * sqT
    z     = math.log(H / S) / (sigma * sqT) + lam * sigma * sqT

    A = phi_sign * S * math.exp(-q * T) * norm.cdf(phi_sign * x1) \
        - phi_sign * K * math.exp(-r * T) * norm.cdf(phi_sign * x1 - phi_sign * sigma * sqT)
    B = phi_sign * S * math.exp(-q * T) * norm.cdf(phi_sign * x2) \
        - phi_sign * K * math.exp(-r * T) * norm.cdf(phi_sign * x2 - phi_sign * sigma * sqT)
    C = phi_sign * S * math.exp(-q * T) * (H / S) ** (2 * (mu + 1)) * norm.cdf(eta_sign * y1) \
        - phi_sign * K * math.exp(-r * T) * (H / S) ** (2 * mu) \
          * norm.cdf(eta_sign * y1 - eta_sign * sigma * sqT)
    D = phi_sign * S * math.exp(-q * T) * (H / S) ** (2 * (mu + 1)) * norm.cdf(eta_sign * y2) \
        - phi_sign * K * math.exp(-r * T) * (H / S) ** (2 * mu) \
          * norm.cdf(eta_sign * y2 - eta_sign * sigma * sqT)
    return A, B, C, D, mu, lam, x2, y2, z


def rr_barrier(S: float, K: float, H: float, T: float, r: float, q: float,
               sigma: float, cp: str, in_out: str, up_down: str,
               rebate: float = 0.0) -> float:
    """
    Reiner-Rubinstein closed-form for continuously-monitored single barrier.

    Returns the option value. `rebate` is paid at expiry on knock-in failure
    or at hit for knock-out (simplified: assume rebate paid at expiry).
    """
    cp = cp.lower().strip()
    in_out  = in_out.lower().strip()
    up_down = up_down.lower().strip()
    if in_out not in ("in", "out"):
        raise ValueError("in_out must be 'in' or 'out'")
    if up_down not in ("up", "down"):
        raise ValueError("up_down must be 'up' or 'down'")

    # Special cases
    if T <= 0:
        # At expiry the barrier game is over; knock-out value = vanilla if barrier not hit,
        # knock-in value = rebate if not in-the-money
        return bs_price(S, K, T, r, q, sigma, cp) if in_out == "out" else rebate

    # Vanilla reference
    vanilla = bs_price(S, K, T, r, q, sigma, cp)

    # Trivial cases: if barrier already breached
    if up_down == "up" and S >= H:
        if in_out == "in":  return vanilla    # already knocked in → vanilla
        else:               return rebate     # already knocked out
    if up_down == "down" and S <= H:
        if in_out == "in":  return vanilla
        else:               return rebate

    phi_sign = 1 if cp.startswith("c") else -1
    eta_sign = -1 if up_down == "up" else 1

    A, B, C, D, mu, lam, x2, y2, z = _phi(S, K, H, T, r, q, sigma, phi_sign, eta_sign)

    # Rebate terms (simplified: payable at expiry if triggered)
    sqT = math.sqrt(T)
    F = rebate * math.exp(-r * T) * (
        norm.cdf(eta_sign * x2 - eta_sign * sigma * sqT)
        - (H / S) ** (2 * mu) * norm.cdf(eta_sign * y2 - eta_sign * sigma * sqT)
    )
    E = rebate * (
        (H / S) ** (mu + lam) * norm.cdf(eta_sign * z)
        + (H / S) ** (mu - lam) * norm.cdf(eta_sign * z - 2 * eta_sign * lam * sigma * sqT)
    )

    # Formula switching depends on (call/put, up/down, in/out) and K vs H
    # Following Haug's cookbook (8 cases).
    c_or_p = cp[0]   # 'c' or 'p'

    if (c_or_p, up_down, in_out) == ("c", "down", "in"):
        if K > H:   return max(0.0, C + E)
        else:       return max(0.0, A - B + D + E)
    if (c_or_p, up_down, in_out) == ("c", "up", "in"):
        if K > H:   return max(0.0, A + E)
        else:       return max(0.0, B - C + D + E)
    if (c_or_p, up_down, in_out) == ("c", "down", "out"):
        if K > H:   return max(0.0, A - C + F)
        else:       return max(0.0, B - D + F)
    if (c_or_p, up_down, in_out) == ("c", "up", "out"):
        if K > H:   return max(0.0, F)
        else:       return max(0.0, A - B + C - D + F)
    if (c_or_p, up_down, in_out) == ("p", "down", "in"):
        if K > H:   return max(0.0, B - C + D + E)
        else:       return max(0.0, A + E)
    if (c_or_p, up_down, in_out) == ("p", "up", "in"):
        if K > H:   return max(0.0, A - B + D + E)
        else:       return max(0.0, C + E)
    if (c_or_p, up_down, in_out) == ("p", "down", "out"):
        if K > H:   return max(0.0, A - B + C - D + F)
        else:       return max(0.0, F)
    if (c_or_p, up_down, in_out) == ("p", "up", "out"):
        if K > H:   return max(0.0, B - D + F)
        else:       return max(0.0, A - C + F)
    return float("nan")


def barrier_discrete_adjust(H: float, sigma: float, T: float,
                            n_obs: int, up: bool = True) -> float:
    """
    Broadie-Glasserman-Kou continuity correction for discrete monitoring.
        H_adj = H · exp(±0.5826 · σ · √(T/n))
        +  for up-barriers (H moved UP → less likely to trigger)
        −  for down-barriers (H moved DOWN → less likely to trigger)
    """
    beta = 0.5826    # = -ζ(1/2)/√(2π)
    shift = beta * sigma * math.sqrt(T / max(1, n_obs))
    return H * math.exp(shift) if up else H * math.exp(-shift)


def barrier_mc(S: float, K: float, H: float, T: float, r: float, q: float,
               sigma: float, cp: str, in_out: str, up_down: str,
               rebate: float = 0.0, paths: int = 10_000, steps: int = 252,
               seed: int = 42) -> tuple[float, float]:
    """MC pricing (useful for verification + discrete monitoring + exotic payoffs)."""
    from .mc import gbm_paths
    w = _cp_sign(cp)
    pa = gbm_paths(S, r, q, sigma, T, steps, paths, seed=seed)

    if up_down == "up":
        hit = (pa >= H).any(axis=1)
    else:
        hit = (pa <= H).any(axis=1)

    terminal = pa[:, -1]
    vanilla_payoff = np.maximum(w * (terminal - K), 0.0)

    if in_out == "in":
        payoff = np.where(hit, vanilla_payoff, rebate)
    else:
        payoff = np.where(hit, rebate, vanilla_payoff)

    disc_pv = math.exp(-r * T) * payoff
    return float(disc_pv.mean()), float(disc_pv.std(ddof=1) / math.sqrt(paths))


def prob_hit_barrier(S: float, H: float, T: float, r: float, q: float,
                     sigma: float, up: bool = True) -> float:
    """
    Closed-form probability that GBM hits the barrier H before T.
    Derived from first-passage time of GBM. Use continuous monitoring.
    """
    if T <= 0 or sigma <= 0 or S <= 0 or H <= 0:
        return 0.0
    if up and S >= H:    return 1.0
    if not up and S <= H: return 1.0

    mu = r - q - 0.5 * sigma * sigma
    x  = math.log(H / S)
    sqT = sigma * math.sqrt(T)
    if up:
        # P(max S_t >= H)
        p1 = norm.cdf((-x + mu * T) / sqT)
        p2 = math.exp(2 * mu * x / (sigma * sigma)) * norm.cdf((-x - mu * T) / sqT)
        # This formula assumes mu > 0 direction; for both directions simplified:
        p = norm.cdf((math.log(H / S) - mu * T) / sqT)   # placeholder not used
        # Use exact drift-adjusted formula:
        p = norm.cdf((mu * T - x) / sqT) + math.exp(2 * mu * x / (sigma * sigma)) \
            * norm.cdf(-(mu * T + x) / sqT)
        return float(min(max(p, 0.0), 1.0))
    else:
        x = math.log(S / H)  # flip sign
        p = norm.cdf((-mu * T - x) / sqT) + math.exp(-2 * mu * x / (sigma * sigma)) \
            * norm.cdf((-mu * T + x) / sqT)
        return float(min(max(p, 0.0), 1.0))
