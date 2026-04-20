"""
Shared Monte Carlo helpers — vectorised GBM path generator with common
variance-reduction utilities (antithetic variates, control variates).
"""
from __future__ import annotations

import numpy as np


def gbm_paths(S0: float, r: float, q: float, sigma: float, T: float,
              steps: int, paths: int, *,
              antithetic: bool = True, seed: int | None = 42) -> np.ndarray:
    """
    Simulate GBM paths under risk-neutral measure.
        dS/S = (r-q)dt + σ dW
    Returns array of shape (paths, steps+1) with S[:, 0] = S0.
    When antithetic=True, paths is rounded up to even and half the paths use -Z.
    """
    rng = np.random.default_rng(seed)
    dt  = T / steps
    drift = (r - q - 0.5 * sigma * sigma) * dt
    vol   = sigma * np.sqrt(dt)

    if antithetic:
        half = (paths + 1) // 2
        z    = rng.standard_normal((half, steps))
        z    = np.vstack([z, -z])[:paths]
    else:
        z = rng.standard_normal((paths, steps))

    log_ret = drift + vol * z
    log_s   = np.cumsum(log_ret, axis=1)
    out     = np.empty((paths, steps + 1))
    out[:, 0]  = S0
    out[:, 1:] = S0 * np.exp(log_s)
    return out


def apply_control_variate(payoffs: np.ndarray, cv_payoffs: np.ndarray,
                          cv_expected: float) -> tuple[float, float]:
    """Standard linear CV: adjusted = payoff - b*(cv - E[cv]).
    Returns (mean, standard_error)."""
    cov = np.cov(payoffs, cv_payoffs, ddof=1)
    var_cv = cov[1, 1]
    b = cov[0, 1] / var_cv if var_cv > 0 else 0.0
    adj = payoffs - b * (cv_payoffs - cv_expected)
    return float(adj.mean()), float(adj.std(ddof=1) / np.sqrt(len(adj)))


def discount(value: float | np.ndarray, r: float, T: float) -> float | np.ndarray:
    return np.exp(-r * T) * value
