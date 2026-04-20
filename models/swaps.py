"""
Vanilla interest rate swaps — NPV, par rate, DV01, cashflow ladder.

Convention:
    - Pay-fixed receive-float is the "payer" side. NPV = PV(float) − PV(fixed).
    - Float leg is valued using forward rates implied by the zero curve.
    - Day-count ACT/365 with uniform period lengths (teaching simplification).
"""
from __future__ import annotations

import numpy as np

from .curves import ZeroCurve


def _schedule(tenor: float, freq: int) -> np.ndarray:
    n = int(round(tenor * freq))
    if n < 1: n = 1
    return np.arange(1, n + 1) / freq


def swap_npv(curve: ZeroCurve, notional: float, fixed_rate: float,
             tenor: float, fix_freq: int = 2, flt_freq: int = 4,
             pay_fixed: bool = True) -> float:
    """
    NPV of a fixed-for-float swap.
        Float leg PV  = notional · (1 − df(T_N))
        Fixed leg PV  = notional · fixed_rate · Σ Δ_i · df(t_i)
    pay_fixed=True → NPV = PV(float) − PV(fixed) (positive = in the money for payer)
    """
    fix_sched = _schedule(tenor, fix_freq)
    delta_fix = 1.0 / fix_freq

    df_fix = np.array([float(curve.df(t)) for t in fix_sched])
    fixed_pv = notional * fixed_rate * delta_fix * df_fix.sum()
    float_pv = notional * (1.0 - float(curve.df(fix_sched[-1])))

    npv = float_pv - fixed_pv
    return float(npv if pay_fixed else -npv)


def par_swap_rate(curve: ZeroCurve, tenor: float, freq: int = 2) -> float:
    """Fixed rate making a fresh swap NPV = 0 (same as ZeroCurve.par_swap_rate)."""
    return curve.par_swap_rate(tenor, freq)


def swap_dv01(curve: ZeroCurve, notional: float, fixed_rate: float,
              tenor: float, fix_freq: int = 2, flt_freq: int = 4,
              pay_fixed: bool = True, bump_bp: float = 1.0) -> float:
    """NPV change for a 1bp parallel curve shift (by default)."""
    npv_up = swap_npv(curve.shift(+bump_bp), notional, fixed_rate, tenor,
                      fix_freq, flt_freq, pay_fixed)
    npv_dn = swap_npv(curve.shift(-bump_bp), notional, fixed_rate, tenor,
                      fix_freq, flt_freq, pay_fixed)
    return float((npv_dn - npv_up) / 2)   # positive dollar DV01 for receiver when rates drop


def swap_cashflows(curve: ZeroCurve, notional: float, fixed_rate: float,
                   tenor: float, fix_freq: int = 2, flt_freq: int = 4,
                   pay_fixed: bool = True) -> dict:
    """
    Expected cashflows (fixed leg = deterministic, float leg = forward-implied).
    Returns dict with fixed_times, fixed_amounts, float_times, float_amounts.
    """
    fix_sched = _schedule(tenor, fix_freq)
    flt_sched = _schedule(tenor, flt_freq)
    delta_fix = 1.0 / fix_freq
    delta_flt = 1.0 / flt_freq

    fixed_amounts = np.full(len(fix_sched), fixed_rate * delta_fix * notional)
    # Float legs: forward rate from t_{i-1} to t_i
    flt_starts = np.concatenate([[0.0], flt_sched[:-1]])
    flt_amounts = np.array([
        curve.simple_forward(s, e) * delta_flt * notional
        for s, e in zip(flt_starts, flt_sched)
    ])

    sign = 1 if pay_fixed else -1
    return {
        "fixed_times":   fix_sched,
        "fixed_amounts": -sign * fixed_amounts,   # outflow for payer
        "float_times":   flt_sched,
        "float_amounts": +sign * flt_amounts,     # inflow for payer
    }
