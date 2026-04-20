"""
Hull-White 1-factor short-rate trinomial tree + callable/puttable bond
pricing + OAS solver.

Reference: Hull & White (1994), Hull's OFOD Ch. 32 two-stage construction:
  Stage 1: Build auxiliary trinomial tree for r* = r - α(t), with drift -a·r*·Δt
  Stage 2: Shift by α(t) to match initial term structure (df[t])
"""
from __future__ import annotations

import math
from typing import Iterable

import numpy as np
from scipy.optimize import brentq

from .curves import ZeroCurve
from .bonds  import bond_cashflows


def hw_trinomial_build(curve: ZeroCurve, sigma: float, a: float, T: float,
                       steps: int = 50) -> dict:
    """
    Build the Hull-White trinomial tree fitted to `curve`.
    Returns dict with:
        dt:     time step
        r:      full rate grid (steps+1, 2M+1)  — NaN where node doesn't exist
        pu/pm/pd: branching probabilities arrays
        alpha:  fitted shift function α(t_i)
        j_max:  tree width limit
    """
    dt = T / steps
    dr = sigma * math.sqrt(3 * dt)
    # Max j to avoid negative probabilities
    j_max = int(math.ceil(0.184 / (a * dt))) if a * dt > 0 else steps
    size = 2 * j_max + 1    # j ranges from -j_max..+j_max

    # Branching probabilities (function of j)
    pu = np.zeros(size); pm = np.zeros(size); pd = np.zeros(size)
    for k, j in enumerate(range(-j_max, j_max + 1)):
        a_j = a * j * dt
        if j == j_max:        # special case: up-branch capped
            pu[k] = 7/6 + (a_j * a_j + 3 * a_j) / 2
            pm[k] = -1/3 - a_j * a_j - 2 * a_j
            pd[k] = 1/6 + (a_j * a_j + a_j) / 2
        elif j == -j_max:     # special case: down-branch capped
            pu[k] = 1/6 + (a_j * a_j - a_j) / 2
            pm[k] = -1/3 - a_j * a_j + 2 * a_j
            pd[k] = 7/6 + (a_j * a_j - 3 * a_j) / 2
        else:                 # normal case
            pu[k] = 1/6 + (a_j * a_j - a_j) / 2
            pm[k] = 2/3 - a_j * a_j
            pd[k] = 1/6 + (a_j * a_j + a_j) / 2
    # Clip to [0,1] against numerical drift
    pu = np.clip(pu, 0, 1); pm = np.clip(pm, 0, 1); pd = np.clip(pd, 0, 1)

    # Time grid and r* grid
    times = np.arange(steps + 1) * dt
    r_grid = np.full((steps + 1, size), np.nan)

    # r*[i, j] = j * dr (before shift)
    for i in range(steps + 1):
        half = min(i, j_max)
        for j in range(-half, half + 1):
            r_grid[i, j + j_max] = j * dr

    # Stage 2: compute α(t_i) so that discount matches curve
    # Arrow-Debreu prices Q[i, j] = PV of $1 paid only at node (i, j)
    Q = np.zeros((steps + 1, size))
    center = j_max
    Q[0, center] = 1.0
    alpha = np.zeros(steps + 1)
    alpha[0] = curve.zero(dt) if dt > 0 else 0.0   # first-step override below

    # Iteratively compute α[i] from Q[i, .] and the curve's df at t_{i+1}
    # Using: df(t_{i+1}) = sum_j Q[i, j] * exp(-(α[i] + r*_i[j]) * dt)
    # Solve α[i]: α[i] = ln(sum Q * exp(-r* * dt)) / dt  − ln(df)/dt
    for i in range(steps + 1):
        ti = times[i]
        ti1 = ti + dt
        if i == 0:
            num = 1.0   # Q[0, center] = 1
            df_next = float(curve.df(ti1))
            alpha[i] = -math.log(df_next) / dt if dt > 0 else 0.0
        else:
            # Already computed α[i] via forward induction below
            pass

        if i < steps:
            # Forward induction: Q[i+1, k+shift]
            for k_j, j in enumerate(range(-j_max, j_max + 1)):
                if np.isnan(r_grid[i, k_j]):
                    continue
                if Q[i, k_j] <= 0:
                    continue
                r_full = alpha[i] + r_grid[i, k_j]
                disc = math.exp(-r_full * dt)
                # Where does node (i, j) branch to at i+1?
                if j == j_max:         # j, j-1, j-2
                    dests = (j, j - 1, j - 2)
                elif j == -j_max:      # j+2, j+1, j
                    dests = (j + 2, j + 1, j)
                else:
                    dests = (j + 1, j, j - 1)
                probs = (pu[k_j], pm[k_j], pd[k_j])
                for p_, j_next in zip(probs, dests):
                    idx = j_next + j_max
                    if 0 <= idx < size:
                        Q[i + 1, idx] += Q[i, k_j] * p_ * disc

            # Determine α[i+1] from Q[i+1] and target df(t_{i+2})
            ti2 = ti1 + dt
            df_t2 = float(curve.df(ti2))
            r_row = r_grid[i + 1]
            q_row = Q[i + 1]
            mask = ~np.isnan(r_row) & (q_row > 0)
            if mask.any():
                num = float(np.sum(q_row[mask] * np.exp(-r_row[mask] * dt)))
                # df_t2 = num * exp(-α[i+1] * dt)
                if num > 0 and df_t2 > 0:
                    alpha[i + 1] = math.log(num / df_t2) / dt

    # Full rate grid = α[i] + r*[i, j]
    r_full = np.full_like(r_grid, np.nan)
    for i in range(steps + 1):
        r_full[i] = alpha[i] + r_grid[i]

    return {
        "dt": dt, "times": times,
        "r": r_full, "r_star": r_grid,
        "pu": pu, "pm": pm, "pd": pd,
        "alpha": alpha, "j_max": j_max,
        "Q": Q,
    }


def price_callable_bond(curve: ZeroCurve, face: float, coupon_rate: float,
                        freq: int, maturity: float,
                        call_schedule: list[tuple[float, float]],
                        sigma: float = 0.01, a: float = 0.10,
                        steps: int = 100) -> dict:
    """
    Price a callable bond (issuer's call option).
    call_schedule: list of (call_time, call_price). Before each call_time
    the issuer may call at the stated price. Tree nodes at those times
    take max(continuation, -call_price) — wait, for the BOND HOLDER the
    issuer's optimal call caps value at call_price, so node = min(continuation, call_price).

    Returns: dict(callable_price, straight_price, call_option_value,
                  effective_duration, effective_convexity)
    """
    tree = hw_trinomial_build(curve, sigma, a, maturity, steps)
    dt   = tree["dt"]
    r    = tree["r"]
    pu, pm, pd = tree["pu"], tree["pm"], tree["pd"]
    j_max = tree["j_max"]
    size  = 2 * j_max + 1

    # Cashflows mapped onto tree steps
    times_cf, amounts_cf = bond_cashflows(face, coupon_rate, freq, maturity)
    # Build a per-step cashflow vector (amount paid at end of each step)
    cf_per_step = np.zeros(steps + 1)
    for t_cf, amt in zip(times_cf, amounts_cf):
        i = int(round(t_cf / dt))
        if 0 <= i <= steps:
            cf_per_step[i] += amt

    # Call schedule → {step_index: call_price}
    call_map = {}
    for t_call, p_call in call_schedule:
        i = int(round(t_call / dt))
        if 0 <= i <= steps:
            call_map[i] = p_call

    # Backward induction: value = cf_at_step + discounted expected continuation
    V_call = np.zeros(size)       # callable
    V_str  = np.zeros(size)       # straight (same bond, no call)

    # Terminal: bond pays its terminal cashflow
    V_call[:] = cf_per_step[steps]
    V_str[:]  = cf_per_step[steps]

    for i in range(steps - 1, -1, -1):
        V_call_new = np.full(size, np.nan)
        V_str_new  = np.full(size, np.nan)
        r_i = r[i]
        for k_j, j in enumerate(range(-j_max, j_max + 1)):
            if np.isnan(r_i[k_j]):
                continue
            disc = math.exp(-r_i[k_j] * dt)
            if j == j_max:
                dests = (j, j - 1, j - 2)
            elif j == -j_max:
                dests = (j + 2, j + 1, j)
            else:
                dests = (j + 1, j, j - 1)
            ps = (pu[k_j], pm[k_j], pd[k_j])

            exp_call = 0.0
            exp_str  = 0.0
            for p_, j_n in zip(ps, dests):
                idx = j_n + j_max
                if 0 <= idx < size and not np.isnan(V_call[idx]):
                    exp_call += p_ * V_call[idx]
                    exp_str  += p_ * V_str[idx]
            cont_call = disc * exp_call + cf_per_step[i]
            cont_str  = disc * exp_str  + cf_per_step[i]

            if i in call_map:
                V_call_new[k_j] = min(cont_call, call_map[i])
            else:
                V_call_new[k_j] = cont_call
            V_str_new[k_j] = cont_str
        V_call = np.where(np.isnan(V_call_new), V_call, V_call_new)
        V_str  = np.where(np.isnan(V_str_new),  V_str,  V_str_new)

    callable_price = float(V_call[j_max])
    straight_price = float(V_str[j_max])

    # Effective duration / convexity via parallel shift
    def price_at_shift(bp):
        tc = curve.shift(bp)
        tree_s = hw_trinomial_build(tc, sigma, a, maturity, steps)
        return _callable_bwd_induction(tree_s, cf_per_step, call_map, steps, size, j_max)

    try:
        p_up = price_at_shift(+25)
        p_dn = price_at_shift(-25)
        dy = 25e-4
        dur  = (p_dn - p_up) / (2 * callable_price * dy) if callable_price > 0 else 0.0
        conv = (p_up + p_dn - 2 * callable_price) / (callable_price * dy * dy) \
               if callable_price > 0 else 0.0
    except Exception:
        dur, conv = float("nan"), float("nan")

    return {
        "callable_price":     callable_price,
        "straight_price":     straight_price,
        "call_option_value":  straight_price - callable_price,
        "effective_duration": float(dur),
        "effective_convexity": float(conv),
        "tree":               tree,
    }


def _callable_bwd_induction(tree, cf_per_step, call_map, steps, size, j_max):
    """Helper for shifted-curve callable price (duplicates induction above)."""
    r = tree["r"]
    pu, pm, pd = tree["pu"], tree["pm"], tree["pd"]
    dt = tree["dt"]
    V = np.zeros(size) + cf_per_step[steps]
    for i in range(steps - 1, -1, -1):
        V_new = np.full(size, np.nan)
        r_i = r[i]
        for k_j, j in enumerate(range(-j_max, j_max + 1)):
            if np.isnan(r_i[k_j]):
                continue
            disc = math.exp(-r_i[k_j] * dt)
            if j == j_max:
                dests = (j, j - 1, j - 2)
            elif j == -j_max:
                dests = (j + 2, j + 1, j)
            else:
                dests = (j + 1, j, j - 1)
            ps = (pu[k_j], pm[k_j], pd[k_j])
            exp_ = 0.0
            for p_, j_n in zip(ps, dests):
                idx = j_n + j_max
                if 0 <= idx < size and not np.isnan(V[idx]):
                    exp_ += p_ * V[idx]
            cont = disc * exp_ + cf_per_step[i]
            V_new[k_j] = min(cont, call_map[i]) if i in call_map else cont
        V = np.where(np.isnan(V_new), V, V_new)
    return float(V[j_max])


def solve_oas(market_price: float, curve: ZeroCurve, face: float,
              coupon_rate: float, freq: int, maturity: float,
              call_schedule: list[tuple[float, float]],
              sigma: float = 0.01, a: float = 0.10,
              steps: int = 60) -> float:
    """
    Solve for the option-adjusted spread (OAS, in decimal, continuous)
    such that adjusting the zero curve by +OAS reproduces market_price.
    """
    def obj(oas_bp):
        shifted = curve.shift(oas_bp)
        p = price_callable_bond(shifted, face, coupon_rate, freq, maturity,
                                call_schedule, sigma, a, steps)["callable_price"]
        return p - market_price
    try:
        return float(brentq(obj, -500, 500, xtol=0.1, maxiter=50)) / 10_000
    except Exception:
        return float("nan")
