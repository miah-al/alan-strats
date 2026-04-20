"""
Zero-rate curve + discount factor interpolation + forward-rate computation
+ par-swap-rate bootstrap.

All rates are continuously compounded. Tenors are in years.
"""
from __future__ import annotations

from typing import Literal

import numpy as np


InterpKind = Literal["linear_zero", "log_df", "cubic_zero"]


class ZeroCurve:
    """
    Zero-rate curve with multiple interpolation schemes.

    Usage:
        curve = ZeroCurve(tenors=[0.25, 1, 5, 10],
                          zeros=[0.043, 0.0425, 0.0395, 0.041])
        curve.df(2.5)          # discount factor at t=2.5
        curve.zero(2.5)        # zero rate
        curve.forward(2, 5)    # simple forward from t=2 to t=5
        curve.par_swap_rate(5, freq=2)
    """

    def __init__(self, tenors, zeros, interp: InterpKind = "log_df"):
        t = np.asarray(tenors, dtype=float)
        z = np.asarray(zeros,  dtype=float)
        if t.ndim != 1 or len(t) != len(z):
            raise ValueError("tenors/zeros must be 1-D arrays of equal length")
        order = np.argsort(t)
        self.tenors = t[order]
        self.zeros  = z[order]
        self.interp = interp

    # ── Core interpolants ───────────────────────────────────────────────

    def zero(self, t) -> float | np.ndarray:
        """Zero (continuous) rate at tenor t."""
        t = np.atleast_1d(np.asarray(t, dtype=float))
        if self.interp == "linear_zero":
            out = np.interp(t, self.tenors, self.zeros)
        elif self.interp == "log_df":
            # Interpolate linearly in log discount-factor space
            dfs = np.exp(-self.zeros * self.tenors)
            log_dfs = np.log(dfs)
            t_safe = np.where(t > 1e-12, t, 1e-12)
            log_df_at_t = np.interp(t, self.tenors, log_dfs)
            out = -log_df_at_t / t_safe
        elif self.interp == "cubic_zero":
            from scipy.interpolate import PchipInterpolator
            f = PchipInterpolator(self.tenors, self.zeros, extrapolate=True)
            out = f(t)
        else:
            raise ValueError(f"unknown interp: {self.interp}")
        return float(out[0]) if np.isscalar(t) or out.size == 1 else out

    def df(self, t) -> float | np.ndarray:
        """Discount factor to time t."""
        t_arr = np.atleast_1d(np.asarray(t, dtype=float))
        z = self.zero(t_arr)
        z_arr = np.atleast_1d(z)
        df = np.exp(-z_arr * t_arr)
        return float(df[0]) if df.size == 1 else df

    def forward(self, t1: float, t2: float) -> float:
        """Continuously-compounded forward rate from t1 to t2."""
        if t2 <= t1:
            raise ValueError("t2 must be > t1")
        df1 = float(self.df(t1))
        df2 = float(self.df(t2))
        return float(np.log(df1 / df2) / (t2 - t1))

    def simple_forward(self, t1: float, t2: float) -> float:
        """Simple (discrete) forward rate = (df1/df2 - 1) / (t2 - t1)."""
        df1 = float(self.df(t1))
        df2 = float(self.df(t2))
        return (df1 / df2 - 1.0) / (t2 - t1)

    # ── Swap-rate / par-rate helpers ────────────────────────────────────

    def par_swap_rate(self, tenor: float, freq: int = 2) -> float:
        """Par fixed rate that makes a fresh fixed-for-float swap NPV = 0."""
        n = int(round(tenor * freq))
        if n < 1:  n = 1
        delta = 1.0 / freq
        times = np.arange(1, n + 1) * delta
        dfs   = np.array([float(self.df(t)) for t in times])
        annuity = delta * dfs.sum()
        if annuity <= 0:
            return float("nan")
        return (1.0 - float(self.df(times[-1]))) / annuity

    def shift(self, bp: float) -> "ZeroCurve":
        """Parallel shift (in basis points). Returns a new curve."""
        return ZeroCurve(self.tenors.copy(), self.zeros + bp / 10_000.0,
                         interp=self.interp)

    def __repr__(self):
        return (f"ZeroCurve(n={len(self.tenors)}, interp={self.interp}, "
                f"zeros[{self.tenors[0]:.2f}y..{self.tenors[-1]:.2f}y] = "
                f"{self.zeros[0]:.3%}..{self.zeros[-1]:.3%})")


# ═══════════════════════════════════════════════════════════════════════════
# Bootstrap: par swap rates → zero curve
# ═══════════════════════════════════════════════════════════════════════════

def bootstrap_from_swaps(tenors, par_rates, freq: int = 2,
                         interp: InterpKind = "log_df") -> ZeroCurve:
    """
    Sequentially bootstrap a ZeroCurve from a set of par-swap rates.
        For each target tenor t_k with par rate c_k:
            Sum_{j<k} c_k * delta * df(t_j) + (1 + c_k * delta) * df(t_k) = 1
        Solve for df(t_k) given df(t_j) from prior steps.
    """
    tenors = np.asarray(tenors, dtype=float)
    par    = np.asarray(par_rates, dtype=float)
    order  = np.argsort(tenors)
    tenors, par = tenors[order], par[order]
    delta = 1.0 / freq

    # Build a running list of (t, df)
    t_nodes = [0.0]
    df_nodes = [1.0]
    for tk, ck in zip(tenors, par):
        # Payment schedule: t_1, ..., t_N where t_N = tk
        n = int(round(tk * freq))
        if n < 1: n = 1
        sched = np.arange(1, n + 1) * delta
        # Interpolate df at intermediate schedule points from existing curve
        curr = ZeroCurve(t_nodes, np.array([-np.log(d) / (t if t > 1e-12 else 1.0)
                                             for t, d in zip(t_nodes, df_nodes)]),
                         interp=interp) if len(t_nodes) > 1 else None
        prior_sum = 0.0
        for s in sched[:-1]:
            if curr is None:
                df_s = 1.0 - ck * s   # flat approximation
            else:
                df_s = float(curr.df(s))
            prior_sum += ck * delta * df_s
        # solve for df(tk)
        df_tk = (1.0 - prior_sum) / (1.0 + ck * delta)
        if df_tk <= 0:
            raise ValueError(f"bootstrap failed at tenor {tk}: df={df_tk}")
        t_nodes.append(float(tk))
        df_nodes.append(float(df_tk))

    # Convert (t, df) to (t, zero)
    t_arr  = np.array(t_nodes[1:])     # skip the t=0 node
    df_arr = np.array(df_nodes[1:])
    zeros  = -np.log(df_arr) / t_arr
    return ZeroCurve(t_arr, zeros, interp=interp)


def flat_curve(rate: float, tenors=None) -> ZeroCurve:
    """Convenience constructor for a flat curve at the given continuous rate."""
    if tenors is None:
        tenors = [0.25, 0.5, 1, 2, 3, 5, 7, 10, 20, 30]
    return ZeroCurve(tenors, [rate] * len(tenors), interp="linear_zero")
