"""
Bond pricing — YTM solve, Macaulay/Modified/Effective duration, DV01, convexity.
Supports pricing from a ZeroCurve or from a single YTM.

Frequencies: 1 (annual), 2 (semi), 4 (quarterly), 12 (monthly).
YTM convention: compounded at the payment frequency (semi-annual compounding by default).
"""
from __future__ import annotations

from typing import Optional

import numpy as np
from scipy.optimize import brentq

from .curves import ZeroCurve


def bond_cashflows(face: float, coupon_rate: float, freq: int, maturity: float,
                   ) -> tuple[np.ndarray, np.ndarray]:
    """Returns (times, amounts). Amounts include principal at maturity."""
    n = int(round(maturity * freq))
    if n < 1: n = 1
    times = np.arange(1, n + 1) / freq
    coupon = face * coupon_rate / freq
    amounts = np.full(n, coupon)
    amounts[-1] += face
    return times, amounts


def bond_price_ytm(face: float, coupon_rate: float, freq: int, maturity: float,
                   ytm: float, settle: float = 0.0) -> dict:
    """Price a bond given YTM (compounded at `freq`).
    Returns dict(clean, dirty, accrued, pv, cashflows=(times, amounts)).
    `settle` is years since last coupon (0 = clean, right after coupon)."""
    times, amounts = bond_cashflows(face, coupon_rate, freq, maturity)
    periods = times * freq
    dfs = (1 + ytm / freq) ** (-periods)
    pv = float(np.dot(amounts, dfs))
    accrued = face * coupon_rate * settle / 1.0  # if settle in years and rate annualised
    # Simpler: accrued = coupon * (fraction of period since last coupon)
    frac = settle * freq  # periods
    coupon_per_period = face * coupon_rate / freq
    accrued = coupon_per_period * frac
    dirty = pv
    clean = dirty - accrued
    return {
        "pv":     pv,
        "dirty":  dirty,
        "clean":  clean,
        "accrued": accrued,
        "times":  times,
        "amounts": amounts,
    }


def bond_price_curve(curve: ZeroCurve, face: float, coupon_rate: float,
                     freq: int, maturity: float) -> dict:
    """Price a bond by discounting cashflows on the zero curve."""
    times, amounts = bond_cashflows(face, coupon_rate, freq, maturity)
    dfs = np.array([float(curve.df(t)) for t in times])
    pv = float(np.dot(amounts, dfs))
    # Implied YTM that reproduces this PV
    ytm = ytm_solve(pv, face, coupon_rate, freq, maturity)
    return {
        "pv": pv, "ytm": ytm,
        "times": times, "amounts": amounts, "dfs": dfs,
    }


def ytm_solve(price: float, face: float, coupon_rate: float,
              freq: int, maturity: float) -> float:
    """Solve for YTM that makes PV of cashflows equal to `price`."""
    def obj(y):
        return bond_price_ytm(face, coupon_rate, freq, maturity, y)["pv"] - price
    try:
        return float(brentq(obj, -0.99, 2.0, xtol=1e-10, maxiter=200))
    except ValueError:
        return float("nan")


def durations(face: float, coupon_rate: float, freq: int, maturity: float,
              ytm: float) -> dict:
    """
    Returns dict with:
        macaulay:  sum(t * PV_CF) / price
        modified:  macaulay / (1 + y/freq)
        convexity: sum(t*(t + 1/freq) * PV_CF) / price / (1 + y/freq)^2
        dv01:      price change for 1bp yield move (positive number ≈ $)
    """
    times, amounts = bond_cashflows(face, coupon_rate, freq, maturity)
    periods = times * freq
    dfs = (1 + ytm / freq) ** (-periods)
    pv_cf = amounts * dfs
    price = float(pv_cf.sum())
    if price == 0:
        return {"macaulay": 0.0, "modified": 0.0, "dv01": 0.0, "convexity": 0.0}
    mac = float(np.dot(times, pv_cf) / price)
    mod = mac / (1 + ytm / freq)
    # Convexity (Macaulay, in years²)
    conv_years2 = float(np.dot(times ** 2 + times / freq, pv_cf) / price
                        / (1 + ytm / freq) ** 2)
    # DV01: −dP/dy for 1bp = mod_dur · price · 1e-4
    dv01 = mod * price * 1e-4
    return {
        "macaulay":  mac,
        "modified":  mod,
        "convexity": conv_years2,
        "dv01":      dv01,
    }


def key_rate_durations(curve: ZeroCurve, face: float, coupon_rate: float,
                        freq: int, maturity: float,
                        key_tenors: list[float] | None = None,
                        bump_bp: float = 1.0) -> dict:
    """
    Partial / key-rate durations: bump one curve node at a time by ±bump_bp,
    reprice, take symmetric difference → KRD at that tenor.
    Sum of KRDs should approximate parallel effective duration.
    """
    if key_tenors is None:
        key_tenors = [t for t in (0.5, 1, 2, 3, 5, 7, 10, 20, 30)
                      if t <= curve.tenors.max() + 1e-6]
    dy = bump_bp / 10_000.0
    p0 = bond_price_curve(curve, face, coupon_rate, freq, maturity)["pv"]
    krds = {}
    for t_node in key_tenors:
        zeros_up = curve.zeros.copy()
        zeros_dn = curve.zeros.copy()
        idx = int(np.argmin(np.abs(curve.tenors - t_node)))
        zeros_up[idx] += dy
        zeros_dn[idx] -= dy
        c_up = ZeroCurve(curve.tenors.copy(), zeros_up, interp=curve.interp)
        c_dn = ZeroCurve(curve.tenors.copy(), zeros_dn, interp=curve.interp)
        p_up = bond_price_curve(c_up, face, coupon_rate, freq, maturity)["pv"]
        p_dn = bond_price_curve(c_dn, face, coupon_rate, freq, maturity)["pv"]
        krd = (p_dn - p_up) / (2 * p0 * dy) if p0 > 0 else 0.0
        krds[float(t_node)] = float(krd)
    return krds


def effective_duration(curve: ZeroCurve, face: float, coupon_rate: float,
                       freq: int, maturity: float,
                       bump_bp: float = 25) -> dict:
    """
    Effective duration & convexity via ±bump_bp parallel curve shift.
        D_eff = (P_- - P_+) / (2 · P_0 · Δy)
        C_eff = (P_+ + P_- - 2·P_0) / (P_0 · Δy²)
    """
    dy = bump_bp / 10_000.0
    p0 = bond_price_curve(curve, face, coupon_rate, freq, maturity)["pv"]
    p_up = bond_price_curve(curve.shift(bump_bp), face, coupon_rate, freq, maturity)["pv"]
    p_dn = bond_price_curve(curve.shift(-bump_bp), face, coupon_rate, freq, maturity)["pv"]
    dur = (p_dn - p_up) / (2 * p0 * dy) if p0 > 0 else 0.0
    conv = (p_up + p_dn - 2 * p0) / (p0 * dy * dy) if p0 > 0 else 0.0
    return {"effective_duration": float(dur),
            "effective_convexity": float(conv),
            "dv01": float(dur * p0 * 1e-4)}
