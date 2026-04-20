"""
Options pricing — Black-Scholes (European), Black-76 (futures/forwards),
Cox-Ross-Rubinstein binomial (American + European check), and closed-form
exotics (digital, geometric Asian, lookback).

All rates are continuously compounded. σ is annualised. T in years.
Convention: cp = 'call' or 'put'; flexible on case and abbreviations.
"""
from __future__ import annotations

import math
from functools import lru_cache
from typing import Literal

import numpy as np
from scipy.stats import norm


CallPut = Literal["call", "put"]


def _cp_sign(cp: str) -> int:
    cp = cp.lower().strip()
    if cp in ("c", "call"):  return 1
    if cp in ("p", "put"):   return -1
    raise ValueError(f"cp must be 'call' or 'put', got {cp!r}")


# ═══════════════════════════════════════════════════════════════════════════
# Black-Scholes — European options on spot asset with continuous dividend q
# ═══════════════════════════════════════════════════════════════════════════

def _bs_d1_d2(S, K, T, r, q, sigma):
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return None, None
    sqT = math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / (sigma * sqT)
    d2 = d1 - sigma * sqT
    return d1, d2


@lru_cache(maxsize=1024)
def bs_price(S: float, K: float, T: float, r: float, q: float,
             sigma: float, cp: str = "call") -> float:
    """Black-Scholes European option on an asset paying continuous dividend q."""
    w = _cp_sign(cp)
    if T <= 0 or sigma <= 0:
        return float(max(w * (S - K), 0.0))
    d1, d2 = _bs_d1_d2(S, K, T, r, q, sigma)
    return float(
        w * (S * math.exp(-q * T) * norm.cdf(w * d1) -
             K * math.exp(-r * T) * norm.cdf(w * d2))
    )


def bs_greeks(S: float, K: float, T: float, r: float, q: float,
              sigma: float, cp: str = "call") -> dict:
    """Returns dict of analytic greeks. Theta in per-year units."""
    w = _cp_sign(cp)
    if T <= 0 or sigma <= 0:
        return {k: 0.0 for k in ("delta","gamma","vega","theta","rho",
                                  "vanna","vomma","charm")}
    d1, d2 = _bs_d1_d2(S, K, T, r, q, sigma)
    pdf_d1 = norm.pdf(d1)
    sqT    = math.sqrt(T)
    disc_q = math.exp(-q * T)
    disc_r = math.exp(-r * T)

    delta = w * disc_q * norm.cdf(w * d1)
    gamma = disc_q * pdf_d1 / (S * sigma * sqT)
    vega  = S * disc_q * pdf_d1 * sqT
    theta = (-S * disc_q * pdf_d1 * sigma / (2 * sqT)
             - w * r * K * disc_r * norm.cdf(w * d2)
             + w * q * S * disc_q * norm.cdf(w * d1))
    rho   = w * K * T * disc_r * norm.cdf(w * d2)

    # Second-order
    vanna = -disc_q * pdf_d1 * d2 / sigma
    vomma = vega * d1 * d2 / sigma
    charm = (w * q * disc_q * norm.cdf(w * d1)
             - disc_q * pdf_d1
             * (2 * (r - q) * T - d2 * sigma * sqT) / (2 * T * sigma * sqT))

    return {
        "delta": float(delta), "gamma": float(gamma),
        "vega":  float(vega),  "theta": float(theta),
        "rho":   float(rho),
        "vanna": float(vanna), "vomma": float(vomma), "charm": float(charm),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Black-76 — European options on FUTURES / FORWARDS
# ═══════════════════════════════════════════════════════════════════════════

@lru_cache(maxsize=1024)
def black76_price(F: float, K: float, T: float, r: float, sigma: float,
                  cp: str = "call") -> float:
    """
    Black-76: options on forward/futures. Useful for commodity options,
    caplets/floorlets, swaptions.
        price = e^{-rT} · [w·F·N(w·d1) - w·K·N(w·d2)]
        d1 = [ln(F/K) + 0.5σ²T] / (σ√T), d2 = d1 - σ√T
    """
    w = _cp_sign(cp)
    if T <= 0 or sigma <= 0:
        return float(math.exp(-r * T) * max(w * (F - K), 0.0))
    sqT = math.sqrt(T)
    d1  = (math.log(F / K) + 0.5 * sigma * sigma * T) / (sigma * sqT)
    d2  = d1 - sigma * sqT
    disc = math.exp(-r * T)
    return float(disc * (w * F * norm.cdf(w * d1) - w * K * norm.cdf(w * d2)))


def black76_greeks(F: float, K: float, T: float, r: float, sigma: float,
                   cp: str = "call") -> dict:
    w = _cp_sign(cp)
    if T <= 0 or sigma <= 0:
        return {k: 0.0 for k in ("delta","gamma","vega","theta","rho")}
    sqT = math.sqrt(T)
    d1  = (math.log(F / K) + 0.5 * sigma * sigma * T) / (sigma * sqT)
    d2  = d1 - sigma * sqT
    disc = math.exp(-r * T)
    pdf_d1 = norm.pdf(d1)

    # Delta w.r.t. forward price F (not spot)
    delta = w * disc * norm.cdf(w * d1)
    gamma = disc * pdf_d1 / (F * sigma * sqT)
    vega  = disc * F * pdf_d1 * sqT
    theta = (-disc * F * pdf_d1 * sigma / (2 * sqT)
             - r * w * disc * (F * norm.cdf(w * d1) - K * norm.cdf(w * d2)))
    rho   = -T * disc * (w * F * norm.cdf(w * d1) - w * K * norm.cdf(w * d2))
    return {"delta": float(delta), "gamma": float(gamma),
            "vega": float(vega), "theta": float(theta), "rho": float(rho)}


# ═══════════════════════════════════════════════════════════════════════════
# Cox-Ross-Rubinstein Binomial — American options
# ═══════════════════════════════════════════════════════════════════════════

def crr_american(S: float, K: float, T: float, r: float, q: float,
                 sigma: float, cp: str = "put", N: int = 500,
                 return_tree: bool = False):
    """
    CRR binomial pricing for American options on a dividend-paying asset.
        u = exp(σ√Δt), d = 1/u, p = (e^{(r-q)Δt} - d) / (u - d)
    Returns: price (float) or (price, tree) where tree is the value grid
             (N+1 × N+1) used for early-exercise boundary extraction.
    """
    w  = _cp_sign(cp)
    if N < 2:  N = 2
    dt = T / N
    u  = math.exp(sigma * math.sqrt(dt))
    d  = 1.0 / u
    disc = math.exp(-r * dt)
    p  = (math.exp((r - q) * dt) - d) / (u - d)
    if not (0.0 < p < 1.0):
        raise ValueError(f"CRR risk-neutral p out of range: {p}")

    # Terminal spot prices
    j = np.arange(N + 1)
    S_T = S * (u ** (N - j)) * (d ** j)
    V = np.maximum(w * (S_T - K), 0.0)

    tree = np.zeros((N + 1, N + 1)) if return_tree else None
    if return_tree:
        tree[:, N] = V

    # Backward induction
    for step in range(N - 1, -1, -1):
        V = disc * (p * V[:-1] + (1 - p) * V[1:])
        S_step = S * (u ** (step - np.arange(step + 1))) * (d ** np.arange(step + 1))
        intrinsic = np.maximum(w * (S_step - K), 0.0)
        V = np.maximum(V, intrinsic)
        if return_tree:
            tree[:step + 1, step] = V

    price = float(V[0])
    return (price, tree) if return_tree else price


def crr_european(S: float, K: float, T: float, r: float, q: float,
                 sigma: float, cp: str = "call", N: int = 500) -> float:
    """CRR European (for BS convergence sanity check)."""
    w  = _cp_sign(cp)
    dt = T / N
    u  = math.exp(sigma * math.sqrt(dt))
    d  = 1.0 / u
    disc = math.exp(-r * dt)
    p  = (math.exp((r - q) * dt) - d) / (u - d)

    j = np.arange(N + 1)
    S_T = S * (u ** (N - j)) * (d ** j)
    V = np.maximum(w * (S_T - K), 0.0)
    for _ in range(N):
        V = disc * (p * V[:-1] + (1 - p) * V[1:])
    return float(V[0])


def crr_greeks_fd(S: float, K: float, T: float, r: float, q: float,
                  sigma: float, cp: str = "put", N: int = 500,
                  bump_pct: float = 0.01) -> dict:
    """Finite-difference greeks on the CRR tree. Bump central."""
    dS = S * bump_pct
    p0 = crr_american(S, K, T, r, q, sigma, cp, N)
    pU = crr_american(S + dS, K, T, r, q, sigma, cp, N)
    pD = crr_american(S - dS, K, T, r, q, sigma, cp, N)
    delta = (pU - pD) / (2 * dS)
    gamma = (pU - 2 * p0 + pD) / (dS * dS)

    dS2 = sigma * 0.01   # 1 vol point
    pV_up = crr_american(S, K, T, r, q, sigma + dS2, cp, N)
    pV_dn = crr_american(S, K, T, r, q, max(1e-6, sigma - dS2), cp, N)
    vega  = (pV_up - pV_dn) / (2 * dS2) / 100   # per 1 vol point

    dT = min(1.0 / 365, T / 2)
    pT = crr_american(S, K, max(1e-6, T - dT), r, q, sigma, cp, N)
    theta = (pT - p0) / dT
    return {"delta": delta, "gamma": gamma, "vega": vega, "theta": theta}


def american_exercise_boundary(S: float, K: float, T: float, r: float, q: float,
                                sigma: float, cp: str = "put",
                                N: int = 200) -> tuple[np.ndarray, np.ndarray]:
    """
    Returns (times, boundary_prices) — the critical stock price where early
    exercise becomes optimal at each step. For an American put, boundary
    is the highest S where immediate exercise beats continuation.
    """
    w  = _cp_sign(cp)
    dt = T / N
    u  = math.exp(sigma * math.sqrt(dt))
    d  = 1.0 / u
    disc = math.exp(-r * dt)
    p  = (math.exp((r - q) * dt) - d) / (u - d)

    # Build terminal values
    j = np.arange(N + 1)
    S_T = S * (u ** (N - j)) * (d ** j)
    V = np.maximum(w * (S_T - K), 0.0)

    times, boundary = [], []
    for step in range(N - 1, -1, -1):
        V_cont = disc * (p * V[:-1] + (1 - p) * V[1:])
        S_step = S * (u ** (step - np.arange(step + 1))) * (d ** np.arange(step + 1))
        intrinsic = np.maximum(w * (S_step - K), 0.0)
        exercise_mask = intrinsic > V_cont
        if exercise_mask.any():
            ex_S = S_step[exercise_mask]
            # Boundary: for put, max S where exercising is optimal; for call, min
            if cp.lower().startswith("p"):
                boundary.append(float(ex_S.max()))
            else:
                boundary.append(float(ex_S.min()))
            times.append(float(step * dt))
        V = np.maximum(V_cont, intrinsic)
    # Reverse to chronological order
    return np.array(times[::-1]), np.array(boundary[::-1])


# ═══════════════════════════════════════════════════════════════════════════
# Digital / Binary options
# ═══════════════════════════════════════════════════════════════════════════

def digital_cash_price(S: float, K: float, T: float, r: float, q: float,
                       sigma: float, cp: str = "call", cash: float = 1.0) -> float:
    """Cash-or-nothing digital. Pays `cash` if S_T > K (call) or S_T < K (put)."""
    w = _cp_sign(cp)
    if T <= 0 or sigma <= 0:
        return float(cash * math.exp(-r * T)) if w * (S - K) > 0 else 0.0
    _, d2 = _bs_d1_d2(S, K, T, r, q, sigma)
    return float(cash * math.exp(-r * T) * norm.cdf(w * d2))


def digital_asset_price(S: float, K: float, T: float, r: float, q: float,
                        sigma: float, cp: str = "call") -> float:
    """Asset-or-nothing digital. Pays S_T if ITM."""
    w = _cp_sign(cp)
    if T <= 0 or sigma <= 0:
        return float(S * math.exp(-q * T)) if w * (S - K) > 0 else 0.0
    d1, _ = _bs_d1_d2(S, K, T, r, q, sigma)
    return float(S * math.exp(-q * T) * norm.cdf(w * d1))


# ═══════════════════════════════════════════════════════════════════════════
# Asian options — geometric closed-form (Kemna-Vorst)
# ═══════════════════════════════════════════════════════════════════════════

def asian_geometric_price(S: float, K: float, T: float, r: float, q: float,
                          sigma: float, cp: str = "call",
                          n_fix: int = 12) -> float:
    """
    Kemna-Vorst closed-form for discretely-sampled geometric-average Asian.
    Uses adjusted volatility and drift derived from log-price average variance.
    """
    if n_fix < 1:  n_fix = 1
    # Equally-spaced fixings at t_i = i*T/n_fix for i = 1..n_fix
    i = np.arange(1, n_fix + 1)
    t = i * T / n_fix
    sigma_adj_sq = (sigma ** 2) / (n_fix ** 2) * float((t * (2 * i - 1)).sum()) / T
    sigma_adj = math.sqrt(max(sigma_adj_sq, 1e-12))
    # Adjusted dividend/drift term
    avg_t = float(t.mean())
    q_adj = r - ((r - q - 0.5 * sigma ** 2) * avg_t + 0.5 * sigma_adj_sq * T) / T
    return bs_price(S, K, T, r, q_adj, sigma_adj, cp)


def asian_arithmetic_mc(S: float, K: float, T: float, r: float, q: float,
                        sigma: float, cp: str = "call",
                        n_fix: int = 12, paths: int = 10_000,
                        control_variate: bool = True,
                        seed: int = 42) -> tuple[float, float]:
    """Arithmetic Asian price via MC with geometric Asian as control variate.
    Returns (price, standard_error)."""
    from .mc import gbm_paths, apply_control_variate
    w = _cp_sign(cp)
    # Simulate paths with n_fix steps (fixings at each step end)
    paths_arr = gbm_paths(S, r, q, sigma, T, n_fix, paths, seed=seed)
    # Fixings = paths_arr[:, 1:]
    fixings = paths_arr[:, 1:]
    arith_avg = fixings.mean(axis=1)
    arith_payoff = np.maximum(w * (arith_avg - K), 0.0) * math.exp(-r * T)

    if control_variate:
        geo_avg = np.exp(np.log(fixings).mean(axis=1))
        geo_payoff = np.maximum(w * (geo_avg - K), 0.0) * math.exp(-r * T)
        geo_expected = asian_geometric_price(S, K, T, r, q, sigma, cp, n_fix)
        price, se = apply_control_variate(arith_payoff, geo_payoff, geo_expected)
        return price, se
    return float(arith_payoff.mean()), float(arith_payoff.std(ddof=1) / math.sqrt(paths))


# ═══════════════════════════════════════════════════════════════════════════
# Lookback options — fixed and floating strike closed-forms
# ═══════════════════════════════════════════════════════════════════════════

def lookback_floating(S: float, T: float, r: float, q: float,
                      sigma: float, cp: str = "call",
                      S_max: float | None = None, S_min: float | None = None) -> float:
    """
    Floating-strike lookback (Conze-Viswanathan, Goldman-Sosin-Gatto).
    Call payoff at expiry: S_T - min(S_t); Put: max(S_t) - S_T.
    Valid for continuous monitoring.
    """
    if T <= 0 or sigma <= 0:
        return 0.0
    sqT = math.sqrt(T)
    b   = r - q    # carry
    a1  = (math.log(S / (S_min if S_min else S)) + (b + 0.5 * sigma ** 2) * T) / (sigma * sqT) \
          if cp.lower().startswith("c") else None
    # Use canonical S_min = S_max = S0 (freshly-issued) if not provided
    if S_max is None:  S_max = S
    if S_min is None:  S_min = S
    disc_r = math.exp(-r * T)
    disc_q = math.exp(-q * T)

    if cp.lower().startswith("c"):
        m = S_min
        a1 = (math.log(S / m) + (b + 0.5 * sigma ** 2) * T) / (sigma * sqT)
        a2 = a1 - sigma * sqT
        if abs(b) < 1e-12:
            term = sigma * sqT * (norm.pdf(a1) - a1 * (1 - norm.cdf(a1)))
            return float(S * disc_q * norm.cdf(a1)
                         - m * disc_r * norm.cdf(a2)
                         + S * disc_q * term)
        a3 = a1 - (2 * b / sigma) * sqT
        return float(
            S * disc_q * norm.cdf(a1)
            - m * disc_r * norm.cdf(a2)
            + S * disc_r * (sigma ** 2) / (2 * b)
              * ((S / m) ** (-2 * b / sigma ** 2) * norm.cdf(-a3)
                 - math.exp(b * T) * norm.cdf(-a1))
        )
    else:
        M = S_max
        b1 = (math.log(M / S) - (b + 0.5 * sigma ** 2) * T) / (sigma * sqT)
        b2 = b1 + sigma * sqT
        if abs(b) < 1e-12:
            term = sigma * sqT * (norm.pdf(b1) + b1 * norm.cdf(b1))
            return float(M * disc_r * norm.cdf(b2)
                         - S * disc_q * norm.cdf(b1)
                         + S * disc_q * term)
        b3 = b1 + (2 * b / sigma) * sqT
        return float(
            M * disc_r * norm.cdf(b2)
            - S * disc_q * norm.cdf(b1)
            + S * disc_r * (sigma ** 2) / (2 * b)
              * (-(S / M) ** (-2 * b / sigma ** 2) * norm.cdf(b3)
                 + math.exp(b * T) * norm.cdf(b1))
        )


def lookback_fixed_mc(S: float, K: float, T: float, r: float, q: float,
                     sigma: float, cp: str = "call",
                     steps: int = 252, paths: int = 10_000,
                     seed: int = 42) -> tuple[float, float]:
    """
    Fixed-strike lookback via MC. Call = max(max_t(S_t) - K, 0),
    Put = max(K - min_t(S_t), 0). Closed forms exist (Conze) but MC
    is simpler and fast enough for teaching.
    """
    from .mc import gbm_paths
    w = _cp_sign(cp)
    pa = gbm_paths(S, r, q, sigma, T, steps, paths, seed=seed)
    if w > 0:
        extrema = pa.max(axis=1)
        payoff  = np.maximum(extrema - K, 0.0)
    else:
        extrema = pa.min(axis=1)
        payoff  = np.maximum(K - extrema, 0.0)
    disc = math.exp(-r * T) * payoff
    return float(disc.mean()), float(disc.std(ddof=1) / math.sqrt(paths))


# ═══════════════════════════════════════════════════════════════════════════
# Implied volatility solver (Newton-Raphson on Black-Scholes)
# ═══════════════════════════════════════════════════════════════════════════

def bjerksund_stensland_2002(S: float, K: float, T: float, r: float,
                             q: float, sigma: float, cp: str = "put") -> float:
    """
    Bjerksund-Stensland 2002 closed-form American option approximation.
    ~100x faster than CRR; accepted industry standard on equity desks.
    Handles American call with continuous dividend q, and American put via
    the B-S put→call transformation: P_am(S,K,r,q,T,σ) = C_am(K,S,q,r,T,σ).
    """
    w = _cp_sign(cp)
    if T <= 0 or sigma <= 0:
        return float(max(w * (S - K), 0.0))

    if w < 0:  # put — transform to call via symmetry
        return bjerksund_stensland_2002(S=K, K=S, T=T, r=q, q=r, sigma=sigma, cp="call")

    # ── American call (B-S 2002) ─────────────────────────────────────────
    if q == 0:
        # Early exercise never optimal on non-div stock
        return bs_price(S, K, T, r, q, sigma, "call")

    b = r - q
    v2 = sigma * sigma
    # Time-split at T/2 per B-S 2002
    t1 = 0.5 * (math.sqrt(5) - 1) * T

    beta = (0.5 - b / v2) + math.sqrt((b / v2 - 0.5) ** 2 + 2 * r / v2)
    B_inf = beta / (beta - 1) * K
    B0 = max(K, r / max(q, 1e-12) * K)
    ht1 = -(b * t1 + 2 * sigma * math.sqrt(t1)) * (K * K) / ((B_inf - B0) * B0)
    ht2 = -(b * T  + 2 * sigma * math.sqrt(T)) * (K * K) / ((B_inf - B0) * B0)
    I1 = B0 + (B_inf - B0) * (1 - math.exp(ht1))
    I2 = B0 + (B_inf - B0) * (1 - math.exp(ht2))

    if S >= I2:
        return max(0.0, S - K)

    alpha1 = (I1 - K) * I1 ** (-beta)
    alpha2 = (I2 - K) * I2 ** (-beta)

    def _phi(S, T_, gamma, H, X):
        lam = (-r + gamma * b + 0.5 * gamma * (gamma - 1) * v2) * T_
        d = -(math.log(S / H) + (b + (gamma - 0.5) * v2) * T_) / (sigma * math.sqrt(T_))
        kappa = 2 * b / v2 + (2 * gamma - 1)
        return (math.exp(lam) * (S ** gamma)
                * (norm.cdf(d) - (X / S) ** kappa
                   * norm.cdf(d - 2 * math.log(X / S) / (sigma * math.sqrt(T_)))))

    def _psi(S, T2, gamma, H2, H1, I1_, I2_, t1_):
        e1 = (math.log(S / I1_) + (b + (gamma - 0.5) * v2) * t1_) / (sigma * math.sqrt(t1_))
        e2 = (math.log((I2_ ** 2) / (S * I1_)) + (b + (gamma - 0.5) * v2) * t1_) / (sigma * math.sqrt(t1_))
        e3 = (math.log(S / I1_) - (b + (gamma - 0.5) * v2) * t1_) / (sigma * math.sqrt(t1_))
        e4 = (math.log((I2_ ** 2) / (S * I1_)) - (b + (gamma - 0.5) * v2) * t1_) / (sigma * math.sqrt(t1_))
        f1 = (math.log(S / H1) + (b + (gamma - 0.5) * v2) * T2) / (sigma * math.sqrt(T2))
        f2 = (math.log((I2_ ** 2) / (S * H1)) + (b + (gamma - 0.5) * v2) * T2) / (sigma * math.sqrt(T2))
        f3 = (math.log((I1_ ** 2) / (S * H1)) + (b + (gamma - 0.5) * v2) * T2) / (sigma * math.sqrt(T2))
        f4 = (math.log(S * I1_ ** 2 / (H1 * I2_ ** 2)) + (b + (gamma - 0.5) * v2) * T2) / (sigma * math.sqrt(T2))
        rho = math.sqrt(t1_ / T2)
        from scipy.stats import multivariate_normal as mvn
        mvn_cdf = lambda a, bv, rho_: mvn.cdf([a, bv], mean=[0, 0], cov=[[1, rho_], [rho_, 1]])
        lam = -r + gamma * b + 0.5 * gamma * (gamma - 1) * v2
        kappa = 2 * b / v2 + (2 * gamma - 1)
        return (math.exp(lam * T2) * (S ** gamma)
                * (mvn_cdf(-e1, -f1, rho)
                   - ((I2_ / S) ** kappa) * mvn_cdf(-e2, -f2, rho)
                   - ((I1_ / S) ** kappa) * mvn_cdf(-e3, -f3, -rho)
                   + ((I1_ / I2_) ** kappa) * mvn_cdf(-e4, -f4, -rho)))

    try:
        val = (alpha2 * (S ** beta)
               - alpha2 * _phi(S, t1, beta, I2, I2)
               + _phi(S, t1, 1.0, I2, I2)
               - _phi(S, t1, 1.0, I1, I2)
               - K * _phi(S, t1, 0.0, I2, I2)
               + K * _phi(S, t1, 0.0, I1, I2)
               + alpha1 * _phi(S, t1, beta, I1, I2)
               - alpha1 * _psi(S, T, beta, I1, I2, I1, I2, t1)
               + _psi(S, T, 1.0, I1, I2, I1, I2, t1)
               - _psi(S, T, 1.0, K,  I2, I1, I2, t1)
               - K * _psi(S, T, 0.0, I1, I2, I1, I2, t1)
               + K * _psi(S, T, 0.0, K,  I2, I1, I2, t1))
        return float(max(val, bs_price(S, K, T, r, q, sigma, "call")))
    except Exception:
        # Fall back to European if approximation fails (e.g. pathological inputs)
        return bs_price(S, K, T, r, q, sigma, "call")


def implied_vol_bs(price: float, S: float, K: float, T: float, r: float,
                   q: float, cp: str = "call", tol: float = 1e-6,
                   max_iter: int = 100) -> float:
    """Newton-Raphson solver for BS implied vol. Returns np.nan if no convergence."""
    w = _cp_sign(cp)
    intrinsic = max(w * (S * math.exp(-q * T) - K * math.exp(-r * T)), 0.0)
    if price < intrinsic - 1e-8:
        return float("nan")
    sigma = 0.3
    for _ in range(max_iter):
        p = bs_price(S, K, T, r, q, sigma, cp)
        if T > 0 and sigma > 0:
            d1, _ = _bs_d1_d2(S, K, T, r, q, sigma)
            vega_ = S * math.exp(-q * T) * norm.pdf(d1) * math.sqrt(T)
        else:
            vega_ = 1e-8
        diff = p - price
        if abs(diff) < tol:
            return sigma
        if vega_ < 1e-10:
            break
        sigma = max(1e-6, sigma - diff / vega_)
    return sigma if abs(bs_price(S, K, T, r, q, sigma, cp) - price) < 1e-3 else float("nan")
