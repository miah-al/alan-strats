"""
Caps, floors, European swaptions — Black-76 on forward rates / swap rates.

A cap = Σ caplets; each caplet is Black-76 on the forward rate L(T_{i-1}, T_i)
set at T_{i-1} and paid at T_i, accrual δ.

European swaption = Black's formula on the forward swap rate, using the
annuity df-weighted sum as numeraire.
"""
from __future__ import annotations

import math

from scipy.stats import norm

from .curves import ZeroCurve
from .options import black76_price


def caplet_price(curve: ZeroCurve, strike: float, t_start: float, t_end: float,
                 sigma: float, notional: float = 1.0) -> float:
    """
    Caplet payoff: notional · δ · max(L(T_{i-1}, T_i) − strike, 0) paid at T_i.
    Discount and forward computed from `curve`; volatility is flat Black vol.
    """
    delta = t_end - t_start
    if delta <= 0 or t_start <= 0:
        return 0.0
    L = curve.simple_forward(t_start, t_end)
    # Black-76 on L with T_option = t_start, discounted to t_end
    bs = black76_price(L, strike, t_start, 0.0, sigma, "call")
    df_end = float(curve.df(t_end))
    return float(notional * delta * bs * df_end / max(math.exp(-0.0 * t_start), 1e-12))


def floorlet_price(curve: ZeroCurve, strike: float, t_start: float, t_end: float,
                   sigma: float, notional: float = 1.0) -> float:
    delta = t_end - t_start
    if delta <= 0 or t_start <= 0:
        return 0.0
    L = curve.simple_forward(t_start, t_end)
    bs = black76_price(L, strike, t_start, 0.0, sigma, "put")
    df_end = float(curve.df(t_end))
    return float(notional * delta * bs * df_end)


def cap_price(curve: ZeroCurve, strike: float, tenor: float, freq: int,
               sigma: float, notional: float = 1.0) -> dict:
    """
    Cap = Σ caplets. First period (0 → 1/freq) is not a caplet (already set).
    Returns dict with total_price and per-caplet breakdown.
    """
    delta = 1.0 / freq
    n = int(round(tenor * freq))
    times = [i * delta for i in range(1, n + 1)]
    caplet_prices = []
    per_caplet_vega = []   # for the ladder chart
    bump = 0.001
    for i in range(1, n):   # skip the first reset (already fixed)
        t_s = times[i - 1]
        t_e = times[i]
        p  = caplet_price(curve, strike, t_s, t_e, sigma, notional)
        pv = caplet_price(curve, strike, t_s, t_e, sigma + bump, notional)
        caplet_prices.append(p)
        per_caplet_vega.append((pv - p) / bump)
    return {
        "total_price": float(sum(caplet_prices)),
        "caplet_times": times[1:],
        "caplet_prices": caplet_prices,
        "caplet_vegas": per_caplet_vega,
    }


def floor_price(curve: ZeroCurve, strike: float, tenor: float, freq: int,
                sigma: float, notional: float = 1.0) -> dict:
    delta = 1.0 / freq
    n = int(round(tenor * freq))
    times = [i * delta for i in range(1, n + 1)]
    floorlet_prices = []
    for i in range(1, n):
        t_s = times[i - 1]
        t_e = times[i]
        floorlet_prices.append(floorlet_price(curve, strike, t_s, t_e, sigma, notional))
    return {"total_price": float(sum(floorlet_prices)),
            "floorlet_times": times[1:], "floorlet_prices": floorlet_prices}


# ═══════════════════════════════════════════════════════════════════════════
# European swaption (Black's formula on forward swap rate)
# ═══════════════════════════════════════════════════════════════════════════

def _annuity(curve: ZeroCurve, t_start: float, tenor: float, freq: int) -> float:
    """Annuity numeraire: A = δ · Σ df(T_i) for swap starting at t_start."""
    delta = 1.0 / freq
    n = int(round(tenor * freq))
    times = [t_start + i * delta for i in range(1, n + 1)]
    return float(delta * sum(curve.df(t) for t in times))


def forward_swap_rate(curve: ZeroCurve, t_start: float, tenor: float,
                       freq: int = 2) -> float:
    """Forward par swap rate for a swap starting at t_start with `tenor`."""
    A = _annuity(curve, t_start, tenor, freq)
    if A <= 0:
        return float("nan")
    df_start = float(curve.df(t_start))
    df_end   = float(curve.df(t_start + tenor))
    return float((df_start - df_end) / A)


def european_swaption(curve: ZeroCurve, t_expiry: float, swap_tenor: float,
                       strike_rate: float, sigma: float, notional: float = 1.0,
                       freq: int = 2, payer: bool = True) -> dict:
    """
    European payer/receiver swaption via Black's formula on the forward swap rate.
        V = A · Black(F, K, T, σ; call if payer else put) · notional
    """
    F = forward_swap_rate(curve, t_expiry, swap_tenor, freq)
    A = _annuity(curve, t_expiry, swap_tenor, freq)
    b = black76_price(F, strike_rate, t_expiry, 0.0, sigma,
                      "call" if payer else "put")
    return {
        "price": float(A * b * notional),
        "forward_swap_rate": F,
        "annuity": A,
        "black_component": b,
    }
