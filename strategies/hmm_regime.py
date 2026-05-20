"""
HMM Regime Classifier — regime-conditional defined-risk options structures.

THESIS
------
Hamilton (1989) "A New Approach to the Economic Analysis of Nonstationary Time
Series and the Business Cycle" introduced regime-switching models for macro time
series. Ang & Bekaert (2002) "Regime Switches in Interest Rates" and
Guidolin & Timmermann (2007) "Asset allocation under multivariate regime
switching" established empirically that the joint distribution of equity
returns and volatility is bimodal/trimodal — a low-vol drift state, a normal
trending state, and a high-vol crisis state — and that a Gaussian HMM on
returns + vol observations recovers these regimes with high stability.

A 3-state Gaussian HMM applied to a 3-dim observation vector
    (SPY log return, VIX level, 20-day realized volatility)
recovers the canonical regimes:

    State 0 — low-vol bull / drift  : vol over-priced → SHORT vol
    State 1 — chop / mean-reversion : range-bound    → SHORT gamma (IC)
    State 2 — high-vol bear / crisis: vol under-priced vs realized → LONG vol

The edge is NOT predicting regimes (regime forecasts are weak); it is matching
the option structure to the inferred *current* regime. We therefore use a
filter (forward algorithm) to compute P(state_i | obs_0:t), never a smoother
that peeks forward, and we re-fit / re-label states only at scheduled retrain
points (monthly cadence).

WALK-FORWARD
------------
- Warmup        : 252 bars (one full vol cycle is the minimum to identify
                   the high-vol crisis state cleanly)
- Retrain       : every 30 bars (monthly)
- At each bar i ≥ warmup we compute P(state | obs_0:i) using only the EM
  parameters fit on data ≤ last retrain. No future data ever enters the
  feature set, the labels (we have no labels — HMM is unsupervised) or the
  emission means / covariances.
- State re-labeling: at every retrain we sort the fitted hidden states by the
  marginal mean of the realized-vol observation dimension. State 0 is always
  the lowest-vol cluster; state 2 the highest. This is the standard fix for
  the "label-switching" problem in EM-based mixture models and is what keeps
  the regime → trade-structure mapping stable across retrains.

OBSERVATION FEATURES (3-dim — minimal by design)
-----------------------------------------------
HMMs overfit aggressively with too many features. We use only:
    log_return : log(close_t / close_{t-1})
    vix_level  : closing VIX
    rv20       : realized vol over the last 20 trading days, annualized

These three are sufficient to discriminate the 3 canonical regimes (the same
features used in Ang/Bekaert and Guidolin/Timmermann's reduced-form
specifications).

TRADE STRUCTURES (defined-risk only)
-----------------------------------
State 0 (low-vol bull) : bull put credit spread
    - Short put at 20-delta, long put 5% wider (defined max-loss)
    - DTE 30, profit target 50% of credit, stop 2× credit
State 1 (chop)         : iron condor
    - Short legs at 16-delta, wings 5% of spot, defined max-loss
    - DTE 35, profit target 50%, stop 2× credit, DTE-exit 21
State 2 (bear/crisis)  : long put debit spread
    - Long put at -30 delta, short put 5% lower, defined max-cost
    - DTE 45, profit target 100% of debit, stop 50% of debit

ENTRY GATING
------------
- P(dominant state) ≥ regime_confidence_min (default 0.60)
- VIX ≤ vix_ceiling (default 40 — skip during dislocation)
- Max 1 concurrent trade — the HMM produces one regime view at a time

MODEL CHOICE
------------
Primary: hmmlearn.GaussianHMM(n_components=3, covariance_type="full"). If
hmmlearn is unavailable we fall back to sklearn.mixture.GaussianMixture on
the same 3-dim observation vector. This is a *degenerate* HMM (no transition
matrix, treats observations as i.i.d.) but preserves all other quant rigor
(walk-forward, state-relabel, regime-conditional structures). The fallback
is logged loudly so the operator knows.

REFERENCES
----------
[1] Hamilton, J. D. (1989). A New Approach to the Economic Analysis of
    Nonstationary Time Series and the Business Cycle. Econometrica 57(2).
[2] Ang, A. & Bekaert, G. (2002). Regime Switches in Interest Rates.
    J. Business & Econ. Statistics 20(2).
[3] Guidolin, M. & Timmermann, A. (2007). Asset allocation under multivariate
    regime switching. J. Economic Dynamics & Control 31(11).
[4] Rabiner, L. R. (1989). A tutorial on Hidden Markov Models. Proc. IEEE 77(2).
"""

from __future__ import annotations

import logging
import math
import pickle
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy.stats import norm

from alan_trader.strategies.base import (
    BaseStrategy,
    BacktestResult,
    SignalResult,
    StrategyStatus,
    StrategyType,
)
from alan_trader.backtest.engine import bs_price
from alan_trader.risk.metrics import compute_all_metrics

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Try-import HMM backend
# ─────────────────────────────────────────────────────────────────────────────
_HMM_BACKEND = "none"
try:                                                                # pragma: no cover
    from hmmlearn.hmm import GaussianHMM as _GaussianHMM            # type: ignore
    _HMM_BACKEND = "hmmlearn"
except ImportError:
    try:
        from sklearn.mixture import GaussianMixture as _GaussianMixture
        _HMM_BACKEND = "sklearn_gmm"
    except ImportError:
        _GaussianMixture = None                                      # type: ignore

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────
_RISK_FREE_RATE   = 0.045
_DEFAULT_DIVIDEND = 0.013      # SPY trailing-12-month yield ~1.3% — pass through to bs_price
_WARMUP_BARS      = 252        # 1 yr — minimum to identify the crisis state cleanly
_RETRAIN_EVERY    = 30         # ~monthly
_SAVED_MODELS_DIR = Path(__file__).parent / "saved_models"

# State → trade-type mapping (states are sorted by realized-vol mean ascending)
_STATE_LABELS = {
    0: "low_vol_bull",
    1: "chop",
    2: "high_vol_bear",
}
_STATE_TRADE = {
    0: "bull_put_spread",
    1: "iron_condor",
    2: "long_put_spread",
}


# ─────────────────────────────────────────────────────────────────────────────
# Greek / strike helpers
# ─────────────────────────────────────────────────────────────────────────────

def _bs_delta(S: float, K: float, T: float, r: float, sigma: float,
              option_type: str, q: float = 0.0) -> float:
    """Black-Scholes delta with optional continuous dividend yield q."""
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return (1.0 if S > K else 0.0) if option_type == "call" else (-1.0 if S < K else 0.0)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    disc_q = math.exp(-q * T)
    return float(disc_q * norm.cdf(d1)) if option_type == "call" \
        else float(disc_q * (norm.cdf(d1) - 1.0))


def _strike_for_delta(S: float, T: float, r: float, sigma: float,
                      target_delta: float, option_type: str,
                      q: float = 0.0) -> float:
    """Invert BS for a target |delta| strike, accounting for dividend yield q.
    Returns spot on degenerate inputs."""
    if T <= 0 or sigma <= 0 or S <= 0:
        return S
    sign = 1.0 if option_type == "call" else -1.0
    target_abs = abs(target_delta)

    def obj(K: float) -> float:
        return abs(_bs_delta(S, K, T, r, sigma, option_type, q=q)) - target_abs

    try:
        return float(brentq(obj, S * 0.40, S * 1.60, xtol=0.01, maxiter=60))
    except (ValueError, RuntimeError):
        return S * math.exp(sign * sigma * math.sqrt(T))


# ─────────────────────────────────────────────────────────────────────────────
# Observation matrix builder (no lookahead)
# ─────────────────────────────────────────────────────────────────────────────

def _build_observation_matrix(close: pd.Series, vix: pd.Series) -> pd.DataFrame:
    """
    Build the (n × 3) observation matrix from price + VIX series.

    Columns:
        log_return : log(close_t / close_{t-1})  -- bar t already realized at close
        vix_level  : VIX at close of bar t
        rv20       : annualized stdev of log_returns over [t-20+1, t]

    All quantities are computed using only data available at or before bar t.
    The HMM consumes the matrix sliced as obs[:i+1] when predicting at bar i,
    so this is an O(1) "no-lookahead" guarantee.
    """
    log_ret = np.log(close / close.shift(1))
    rv20    = log_ret.rolling(20, min_periods=10).std() * math.sqrt(252)
    vix_aligned = vix.reindex(close.index).ffill().fillna(20.0)

    obs = pd.DataFrame({
        "log_return": log_ret,
        "vix_level":  vix_aligned,
        "rv20":       rv20,
    }, index=close.index)
    # Forward-fill within the warmup ramp — once 20 bars have accrued rv20 is
    # well-defined; before then we leave NaN and the consumer must drop those.
    return obs


# ─────────────────────────────────────────────────────────────────────────────
# HMM fit + state-relabel (the no-lookahead heart of the strategy)
# ─────────────────────────────────────────────────────────────────────────────

class _RegimeModel:
    """
    Thin wrapper around hmmlearn.GaussianHMM (or sklearn GMM fallback).
    Tracks the relabel permutation so callers always see state 0 = low-vol,
    state 2 = high-vol regardless of EM's internal ordering.

    Warm-start: pass `prior_sorted_means` from a previous fit's `sorted_means()`
    into `fit(...)` and EM is seeded from the previous solution. This greatly
    reduces fit-to-fit posterior jitter at retrain boundaries.
    """

    def __init__(self, n_components: int = 3, random_state: int = 42):
        self.n_components = n_components
        self.random_state = random_state
        self.backend      = _HMM_BACKEND
        self._raw_model   = None        # underlying hmmlearn / sklearn object
        self._perm        = None        # raw_state -> sorted_state map
        self._fitted      = False

    # ── Fit ────────────────────────────────────────────────────────────────
    def fit(self, X: np.ndarray, prior_sorted_means: Optional[np.ndarray] = None) -> None:
        """X: (n × 3) observation matrix, no NaNs.

        prior_sorted_means: if provided, a (k × 3) matrix of means from a
        previous fit (sorted by ascending rv20). Used as `means_init` to
        warm-start EM and stabilise the posterior between retrains.
        """
        if X.shape[0] < self.n_components * 5:
            raise ValueError(f"Need ≥ {self.n_components * 5} clean obs, got {X.shape[0]}")

        if self.backend == "hmmlearn":                              # pragma: no cover
            m = _GaussianHMM(
                n_components=self.n_components,
                covariance_type="full",
                n_iter=100,
                tol=1e-3,
                random_state=self.random_state,
                init_params="stmc" if prior_sorted_means is None else "stc",
            )
            if prior_sorted_means is not None and prior_sorted_means.shape == (
                self.n_components, X.shape[1]
            ):
                m.means_ = prior_sorted_means.astype(np.float64).copy()
            # hmmlearn expects 2-D contiguous float64
            m.fit(np.ascontiguousarray(X, dtype=np.float64))
            raw_means = m.means_                                    # (k, 3)
        elif self.backend == "sklearn_gmm":
            m = _GaussianMixture(
                n_components=self.n_components,
                covariance_type="full",
                max_iter=100,
                tol=1e-3,
                random_state=self.random_state,
                reg_covar=1e-4,
                means_init=(
                    prior_sorted_means.astype(np.float64)
                    if (prior_sorted_means is not None
                        and prior_sorted_means.shape == (self.n_components, X.shape[1]))
                    else None
                ),
            )
            m.fit(np.ascontiguousarray(X, dtype=np.float64))
            raw_means = m.means_
        else:
            raise RuntimeError(
                "No HMM backend available — install hmmlearn or scikit-learn."
            )

        # ── State relabel by ascending rv20 (column index 2) ──────────────
        # raw_means is (k, 3); column 2 is the rv20 mean of each cluster.
        order = np.argsort(raw_means[:, 2])
        # perm[raw_idx] = sorted_idx
        perm = np.empty(self.n_components, dtype=int)
        for sorted_idx, raw_idx in enumerate(order):
            perm[raw_idx] = sorted_idx

        self._raw_model = m
        self._perm      = perm
        self._fitted    = True

    # ── State posterior at bar i ──────────────────────────────────────────
    def predict_proba(self, X_upto_i: np.ndarray) -> np.ndarray:
        """
        Return P(state | obs_0:i) for the *last* row of X_upto_i — the
        relabeled probabilities (state 0 = low-vol cluster, etc.).
        """
        if not self._fitted:
            raise RuntimeError("Model not fitted")

        if self.backend == "hmmlearn":                              # pragma: no cover
            # GaussianHMM.predict_proba returns (n × k) gamma values from the
            # forward-backward algorithm; we want the LAST row.
            try:
                gamma = self._raw_model.predict_proba(np.ascontiguousarray(X_upto_i))
                last  = gamma[-1, :]
            except Exception as e:
                logger.warning(f"hmm predict_proba failed, using uniform: {e}")
                last = np.ones(self.n_components) / self.n_components
        else:
            # sklearn GMM: predict_proba on a single point gives the cluster
            # responsibilities under the assumption observations are iid (no
            # transition matrix — degenerate HMM).
            last = self._raw_model.predict_proba(X_upto_i[-1:].astype(np.float64))[0]

        # Relabel
        relabeled = np.zeros(self.n_components, dtype=float)
        for raw_idx in range(self.n_components):
            relabeled[self._perm[raw_idx]] = last[raw_idx]
        return relabeled

    # ── Sorted means (for diagnostics / state validation) ─────────────────
    def sorted_means(self) -> np.ndarray:
        if not self._fitted:
            raise RuntimeError("Model not fitted")
        raw_means = self._raw_model.means_
        sorted_means = np.empty_like(raw_means)
        for raw_idx in range(self.n_components):
            sorted_means[self._perm[raw_idx]] = raw_means[raw_idx]
        return sorted_means

    # ── Sorted transition matrix (hmmlearn backend only) ──────────────────
    def sorted_transmat(self) -> Optional[np.ndarray]:
        """Return the relabeled transition matrix or None for backends without one.

        sklearn-GMM is iid (no transition matrix) and returns None — callers
        should fall back to the spot posterior in that case.
        """
        if not self._fitted or self.backend != "hmmlearn":
            return None
        raw_A = getattr(self._raw_model, "transmat_", None)
        if raw_A is None:
            return None
        k = self.n_components
        sorted_A = np.empty((k, k), dtype=float)
        for i_raw in range(k):
            for j_raw in range(k):
                sorted_A[self._perm[i_raw], self._perm[j_raw]] = raw_A[i_raw, j_raw]
        return sorted_A

    def expected_posterior(self, X_upto_i: np.ndarray, horizon: int) -> np.ndarray:
        """E[P(state) | obs_0:i] after `horizon` daily transitions.

        For the hmmlearn backend: `posterior @ A^horizon`. For the iid fallback
        (no transition matrix) we degrade to the spot posterior — the strategy
        layer interprets the degraded value with caution.
        """
        spot = self.predict_proba(X_upto_i)
        A = self.sorted_transmat()
        if A is None or horizon <= 0:
            return spot
        from numpy.linalg import matrix_power
        return spot @ matrix_power(A, int(horizon))


# ─────────────────────────────────────────────────────────────────────────────
# Strategy class
# ─────────────────────────────────────────────────────────────────────────────

class HMMRegimeStrategy(BaseStrategy):
    """
    Three-state Gaussian HMM on (log_return, VIX, realized vol). State 0 → bull
    put credit spread (short vol). State 1 → iron condor (short gamma). State 2
    → long put debit spread (long vol). Defined-risk on every leg, walk-forward
    fit with monthly retrain, no lookahead. See module docstring for thesis.
    """

    name                 = "hmm_regime"
    display_name         = "HMM Regime Classifier"
    strategy_type        = StrategyType.AI_DRIVEN
    status               = StrategyStatus.ACTIVE
    description          = (
        "3-state Gaussian HMM on (log return, VIX, realized vol) infers the "
        "current regime. State 0 (low-vol bull) → bull put credit spread. "
        "State 1 (chop) → iron condor. State 2 (high-vol bear) → long put "
        "debit spread. Defined-risk only. Walk-forward, monthly retrain, "
        "states relabeled by ascending vol mean (no label drift)."
    )
    asset_class          = "equities_options"
    typical_holding_days = 21
    target_sharpe        = 1.4

    # Observation feature layout (column index in obs matrix)
    OBS_COLS = ["log_return", "vix_level", "rv20"]

    def __init__(
        self,
        # Regime detection
        regime_confidence_min: float = 0.60,
        vix_ceiling:           float = 40.0,
        n_components:          int   = 3,
        retrain_every:         int   = 30,
        warmup_bars:           int   = 252,
        # Backend + pricing
        dividend_yield:        float = _DEFAULT_DIVIDEND,   # SPY ~1.3% by default
        allow_gmm_fallback:    bool  = False,               # explicit opt-in for iid fallback
        use_transition_matrix: bool  = True,                # forward posterior over option life
        forward_horizon_bars:  Optional[int] = None,        # None → DTE/2 for the active state
        # State 0 — bull put credit spread
        dte_bull_put:        int   = 30,
        bull_put_short_delta: float = 0.20,
        bull_put_wing_pct:   float = 0.05,
        # State 1 — iron condor
        dte_condor:          int   = 35,
        condor_short_delta:  float = 0.16,
        condor_wing_pct:     float = 0.05,
        condor_dte_exit:     int   = 21,
        bull_put_dte_exit:   int   = 7,
        long_put_dte_exit:   int   = 7,
        # State 2 — long put debit spread
        dte_long_put:        int   = 45,
        long_put_long_delta: float = 0.30,
        long_put_short_pct:  float = 0.05,
        # State 2 entry gates (added 2026-05 after backtest diagnosis showed
        # state-2 trades won only 15% of the time and accounted for the entire
        # -38% drawdown). Two complementary defenses:
        #   (a) require VIX to be DESCENDING from a recent peak before entering
        #       long-vol — the strategy is designed for the RECOVERY side of a
        #       vol spike, not the run-up.
        #   (b) size state-2 trades smaller than state-0 / state-1 since the
        #       Kelly fraction at a 15% win rate is negative.
        state2_require_vix_descending: bool  = True,
        state2_vix_descent_pct:        float = 0.15,   # VIX must be >=15% off 5-bar peak
        state2_vix_descent_lookback:   int   = 5,      # bars over which to find the peak
        state2_size_multiplier:        float = 0.5,    # half-size state 2 entries
        # Risk / exits — short-vol structures
        profit_target_pct:   float = 0.50,
        stop_loss_mult:      float = 2.0,
        # Risk / exits — long-vol structure (debit)
        debit_profit_target: float = 1.00,
        debit_stop_loss_pct: float = 0.50,
        # Position sizing
        position_size_pct:   float = 0.03,
        max_concurrent:      int   = 1,
        # Costs
        commission_per_leg:  float = 0.65,
        slippage_per_leg:    float = 0.05,
    ):
        self.regime_confidence_min = regime_confidence_min
        self.vix_ceiling           = vix_ceiling
        self.n_components          = n_components
        self.retrain_every         = retrain_every
        self.warmup_bars           = warmup_bars

        self.dividend_yield        = float(dividend_yield)
        self.allow_gmm_fallback    = bool(allow_gmm_fallback)
        self.use_transition_matrix = bool(use_transition_matrix)
        self.forward_horizon_bars  = forward_horizon_bars

        if _HMM_BACKEND == "sklearn_gmm" and not self.allow_gmm_fallback:
            logger.warning(
                "hmm_regime: hmmlearn unavailable; sklearn-GMM fallback is iid "
                "(no transition matrix) and posteriors will flicker. Pass "
                "allow_gmm_fallback=True to acknowledge and proceed."
            )

        self.dte_bull_put          = dte_bull_put
        self.bull_put_short_delta  = bull_put_short_delta
        self.bull_put_wing_pct     = bull_put_wing_pct

        self.dte_condor            = dte_condor
        self.condor_short_delta    = condor_short_delta
        self.condor_wing_pct       = condor_wing_pct
        self.condor_dte_exit       = condor_dte_exit
        self.bull_put_dte_exit     = bull_put_dte_exit
        self.long_put_dte_exit     = long_put_dte_exit

        self.dte_long_put          = dte_long_put
        self.long_put_long_delta   = long_put_long_delta
        self.long_put_short_pct    = long_put_short_pct

        self.state2_require_vix_descending = bool(state2_require_vix_descending)
        self.state2_vix_descent_pct        = float(state2_vix_descent_pct)
        self.state2_vix_descent_lookback   = int(state2_vix_descent_lookback)
        self.state2_size_multiplier        = float(state2_size_multiplier)

        self.profit_target_pct     = profit_target_pct
        self.stop_loss_mult        = stop_loss_mult
        self.debit_profit_target   = debit_profit_target
        self.debit_stop_loss_pct   = debit_stop_loss_pct

        self.position_size_pct     = position_size_pct
        self.max_concurrent        = max_concurrent

        self.commission_per_leg    = commission_per_leg
        self.slippage_per_leg      = slippage_per_leg

        self._model: Optional[_RegimeModel] = None

    # ═══════════════════════════════════════════════════════════════════════
    # Params / UI
    # ═══════════════════════════════════════════════════════════════════════

    def get_params(self) -> dict:
        return {
            "regime_confidence_min": self.regime_confidence_min,
            "vix_ceiling":           self.vix_ceiling,
            "n_components":          self.n_components,
            "retrain_every":         self.retrain_every,
            "warmup_bars":           self.warmup_bars,
            "dte_bull_put":          self.dte_bull_put,
            "bull_put_short_delta":  self.bull_put_short_delta,
            "bull_put_wing_pct":     self.bull_put_wing_pct,
            "dte_condor":            self.dte_condor,
            "condor_short_delta":    self.condor_short_delta,
            "condor_wing_pct":       self.condor_wing_pct,
            "condor_dte_exit":       self.condor_dte_exit,
            "bull_put_dte_exit":     self.bull_put_dte_exit,
            "long_put_dte_exit":     self.long_put_dte_exit,
            "dte_long_put":          self.dte_long_put,
            "long_put_long_delta":   self.long_put_long_delta,
            "long_put_short_pct":    self.long_put_short_pct,
            "state2_require_vix_descending": self.state2_require_vix_descending,
            "state2_vix_descent_pct":        self.state2_vix_descent_pct,
            "state2_vix_descent_lookback":   self.state2_vix_descent_lookback,
            "state2_size_multiplier":        self.state2_size_multiplier,
            "profit_target_pct":     self.profit_target_pct,
            "stop_loss_mult":        self.stop_loss_mult,
            "debit_profit_target":   self.debit_profit_target,
            "debit_stop_loss_pct":   self.debit_stop_loss_pct,
            "position_size_pct":     self.position_size_pct,
            "max_concurrent":        self.max_concurrent,
            "commission_per_leg":    self.commission_per_leg,
            "slippage_per_leg":      self.slippage_per_leg,
            "dividend_yield":        self.dividend_yield,
            "allow_gmm_fallback":    self.allow_gmm_fallback,
            "use_transition_matrix": self.use_transition_matrix,
            "forward_horizon_bars":  self.forward_horizon_bars,
        }

    def get_backtest_ui_params(self) -> list[dict]:
        return [
            {"key": "regime_confidence_min", "label": "Min P(state)",  "type": "slider",
             "min": 0.40, "max": 0.90, "default": 0.60, "step": 0.05,
             "col": 0, "row": 0,
             "help": "Posterior probability of dominant state required to enter"},
            {"key": "vix_ceiling",          "label": "Max VIX",        "type": "slider",
             "min": 25.0, "max": 60.0, "default": 40.0, "step": 1.0,
             "col": 1, "row": 0},
            {"key": "retrain_every",        "label": "Retrain every (bars)", "type": "slider",
             "min": 10,   "max": 90,   "default": 30,   "step": 5,
             "col": 2, "row": 0,
             "help": "Bars between EM refits (~monthly default)"},

            {"key": "bull_put_short_delta", "label": "Bull-put short Δ", "type": "slider",
             "min": 0.10, "max": 0.30, "default": 0.20, "step": 0.01,
             "col": 0, "row": 1},
            {"key": "condor_short_delta",   "label": "Condor short Δ",   "type": "slider",
             "min": 0.10, "max": 0.25, "default": 0.16, "step": 0.01,
             "col": 1, "row": 1},
            {"key": "long_put_long_delta",  "label": "Long-put long Δ",  "type": "slider",
             "min": 0.20, "max": 0.45, "default": 0.30, "step": 0.01,
             "col": 2, "row": 1},

            {"key": "dte_bull_put",         "label": "Bull-put DTE",    "type": "slider",
             "min": 14,  "max": 60,  "default": 30, "step": 1,
             "col": 0, "row": 2},
            {"key": "dte_condor",           "label": "Condor DTE",      "type": "slider",
             "min": 21,  "max": 60,  "default": 35, "step": 1,
             "col": 1, "row": 2},
            {"key": "dte_long_put",         "label": "Long-put DTE",    "type": "slider",
             "min": 21,  "max": 90,  "default": 45, "step": 1,
             "col": 2, "row": 2},

            {"key": "profit_target_pct",    "label": "Credit PT (%)",   "type": "slider",
             "min": 0.25, "max": 0.75, "default": 0.50, "step": 0.05,
             "col": 0, "row": 3},
            {"key": "position_size_pct",    "label": "Position size",   "type": "slider",
             "min": 0.01, "max": 0.10, "default": 0.03, "step": 0.01,
             "col": 1, "row": 3},

            # State-2 (long put debit spread) defensive controls — added 2026-05.
            # Diagnosis showed 15% win rate, single biggest source of drawdown.
            {"key": "state2_vix_descent_pct", "label": "State-2: VIX dropoff (%)",
             "type": "slider", "min": 0.0, "max": 0.30, "default": 0.15, "step": 0.05,
             "col": 2, "row": 3,
             "help": "Require VIX to be this far below its 5-bar peak before entering "
                     "state-2 long-vol trades. 0 disables the gate."},
            {"key": "state2_size_multiplier", "label": "State-2: size multiplier",
             "type": "slider", "min": 0.0, "max": 1.0, "default": 0.5, "step": 0.1,
             "col": 0, "row": 4,
             "help": "Multiplier on position_size_pct for state-2 trades. "
                     "0 disables state-2 entries entirely (cash in crisis)."},
        ]

    # ═══════════════════════════════════════════════════════════════════════
    # Model persistence
    # ═══════════════════════════════════════════════════════════════════════

    def save_model(self, ticker: str = "default") -> str:
        _SAVED_MODELS_DIR.mkdir(parents=True, exist_ok=True)
        path = _SAVED_MODELS_DIR / f"hmm_regime_{ticker.lower()}.pkl"
        with open(path, "wb") as f:
            pickle.dump(self._model, f)
        logger.info(f"hmm_regime: model saved to {path}")
        return str(path)

    def load_model(self, ticker: str = "default") -> bool:
        path = _SAVED_MODELS_DIR / f"hmm_regime_{ticker.lower()}.pkl"
        if path.exists():
            with open(path, "rb") as f:
                self._model = pickle.load(f)
            logger.info(f"hmm_regime: model loaded from {path}")
            return True
        return False

    def is_trainable(self) -> bool:
        return True

    # ═══════════════════════════════════════════════════════════════════════
    # Live signal
    # ═══════════════════════════════════════════════════════════════════════

    def generate_signal(self, market_snapshot: dict) -> SignalResult:
        """
        Snapshot keys consumed:
            price            : float (required)
            vix              : float (required)
            features_df      : pd.DataFrame with columns ['log_return','vix_level','rv20']
                               (last ≥ 252 rows). If absent, falls back to a VIX-percentile
                               heuristic.
        """
        spot = market_snapshot.get("price") or market_snapshot.get("spot")
        vix  = market_snapshot.get("vix")

        if spot is None or vix is None:
            return SignalResult(self.name, "HOLD", 0.0, 0.0,
                                metadata={"reason": "missing price or vix"})

        spot, vix = float(spot), float(vix)

        if vix > self.vix_ceiling:
            return SignalResult(self.name, "HOLD", 0.0, 0.0,
                                metadata={"reason": f"vix {vix:.1f} > ceiling {self.vix_ceiling}"})

        features_df = market_snapshot.get("features_df")

        # ── Heuristic fallback (no model loaded or insufficient feature history) ──
        if (
            self._model is None
            or features_df is None
            or (isinstance(features_df, pd.DataFrame) and len(features_df) < self.warmup_bars)
        ):
            return self._heuristic_signal(spot, vix)

        # ── Full posterior path ───────────────────────────────────────────
        try:
            obs = features_df[self.OBS_COLS].dropna().values.astype(float)
            if obs.shape[0] < self.warmup_bars:
                return self._heuristic_signal(spot, vix)
            posterior = self._model.predict_proba(obs)
        except Exception as e:
            logger.warning(f"hmm_regime: live posterior failed ({e}); using heuristic")
            return self._heuristic_signal(spot, vix)

        state = int(np.argmax(posterior))
        p     = float(posterior[state])

        if p < self.regime_confidence_min:
            return SignalResult(self.name, "HOLD", round(p, 3), 0.0,
                                metadata={"reason": "posterior below confidence floor",
                                          "state": state, "p_state": round(p, 3),
                                          "posterior": [round(x, 3) for x in posterior]})

        signal, trade_type = self._signal_for_state(state)
        return SignalResult(
            strategy_name     = self.name,
            signal            = signal,
            confidence        = round(p, 3),
            position_size_pct = self.position_size_pct,
            metadata={
                "state":      state,
                "state_name": _STATE_LABELS[state],
                "p_state":    round(p, 3),
                "trade_type": trade_type,
                "posterior":  [round(x, 3) for x in posterior],
                "vix":        vix,
                "mode":       "model",
            },
        )

    def _heuristic_signal(self, spot: float, vix: float) -> SignalResult:
        """
        VIX-percentile fallback when the model is unloaded. Approximates the
        regime via VIX bucketing — well-known stylized fact:
            VIX < 15 → quiet drift (state 0-like)
            VIX 15–22 → normal/chop (state 1-like)
            VIX > 22 → elevated/crisis (state 2-like)
        """
        if vix < 15.0:
            state = 0
        elif vix < 22.0:
            state = 1
        else:
            state = 2

        signal, trade_type = self._signal_for_state(state)
        confidence = 0.55  # below model min — caller may still HOLD if they want strict
        return SignalResult(
            strategy_name     = self.name,
            signal            = signal,
            confidence        = confidence,
            position_size_pct = self.position_size_pct * 0.5,   # half-size in heuristic mode
            metadata={
                "state":      state,
                "state_name": _STATE_LABELS[state],
                "p_state":    confidence,
                "trade_type": trade_type,
                "mode":       "heuristic",
                "vix":        vix,
            },
        )

    @staticmethod
    def _signal_for_state(state: int) -> tuple[str, str]:
        if state == 0:
            return "SELL", _STATE_TRADE[0]   # short vol via credit spread
        if state == 1:
            return "SELL", _STATE_TRADE[1]   # short gamma via condor
        return "BUY", _STATE_TRADE[2]        # long vol via debit spread

    # ═══════════════════════════════════════════════════════════════════════
    # Backtest
    # ═══════════════════════════════════════════════════════════════════════

    def backtest(
        self,
        price_data:       pd.DataFrame,
        auxiliary_data:   dict,
        starting_capital: float = 100_000,
        ticker:           str   = "SPY",
        progress_callback = None,
        **kwargs,
    ) -> BacktestResult:
        """
        Walk-forward HMM regime backtest.

        At each bar i ≥ warmup:
            * If (i - last_retrain) >= retrain_every: refit HMM on obs[:i+1]
            * Predict P(state | obs[:i+1]) using ONLY data up to and including i
            * Open at most 1 trade keyed to dominant state (if confidence ≥ floor)
            * Manage open trade: BS-priced close, profit target / stop / DTE-exit

        No future data ever enters the fit, the labels (none) or the posterior.
        """
        if _HMM_BACKEND == "none":
            raise RuntimeError(
                "No HMM backend available — install hmmlearn or scikit-learn."
            )
        if _HMM_BACKEND == "sklearn_gmm" and not self.allow_gmm_fallback:
            raise RuntimeError(
                "hmm_regime: hmmlearn missing; iid sklearn-GMM fallback is "
                "disabled by default. Either `pip install hmmlearn` or pass "
                "allow_gmm_fallback=True to the strategy explicitly."
            )

        # ── Resolve param overrides ───────────────────────────────────────
        p = {**self.get_params(), **{k: v for k, v in kwargs.items() if k in self.get_params()}}

        # ── Validate / align inputs ───────────────────────────────────────
        if price_data is None or price_data.empty:
            raise ValueError("hmm_regime: price_data is required and must be non-empty")

        vix_df = auxiliary_data.get("vix") if auxiliary_data else None
        if vix_df is None or (isinstance(vix_df, pd.DataFrame) and vix_df.empty):
            raise ValueError(
                "hmm_regime: VIX data required. Pass auxiliary_data={'vix': df}."
            )

        price_data = price_data.copy()
        price_data.index = pd.to_datetime(price_data.index)
        price_data = price_data.sort_index()

        if isinstance(vix_df, pd.DataFrame):
            vix_df = vix_df.copy()
            vix_df.index = pd.to_datetime(vix_df.index)
            vix_series = vix_df["close"] if "close" in vix_df.columns else vix_df.iloc[:, 0]
        else:
            vix_series = pd.Series(vix_df)
        vix_series = vix_series.reindex(price_data.index).ffill().fillna(20.0)

        close = price_data["close"]
        n     = len(close)

        # ── Per-ticker IV series (auxiliary_data["atm_iv"]) — overrides VIX proxy ─
        #
        # If the caller supplies an `atm_iv` series in `auxiliary_data`, it is
        # used for BS pricing instead of VIX/100. This matters for non-SPY
        # tickers whose own IV surface diverges from the broad-market VIX.
        # The series must be indexed by date and contain IV as a decimal
        # (e.g. 0.18 for 18% annualised). Falls back to VIX/100 if absent.
        atm_iv_series = None
        if auxiliary_data:
            _atm_iv_raw = auxiliary_data.get("atm_iv")
            if _atm_iv_raw is not None:
                try:
                    if isinstance(_atm_iv_raw, pd.DataFrame):
                        _atm_iv_raw = (
                            _atm_iv_raw["atm_iv"] if "atm_iv" in _atm_iv_raw.columns
                            else _atm_iv_raw.iloc[:, 0]
                        )
                    _s = pd.Series(_atm_iv_raw)
                    _s.index = pd.to_datetime(_s.index)
                    atm_iv_series = _s.reindex(price_data.index).ffill()
                    logger.info(
                        f"hmm_regime: using per-ticker ATM IV from auxiliary_data "
                        f"({atm_iv_series.notna().sum()} bars populated)"
                    )
                except Exception as e:
                    logger.warning(f"hmm_regime: atm_iv parse failed ({e}); falling back to VIX/100")
                    atm_iv_series = None

        # ── Build observation matrix ──────────────────────────────────────
        obs_df = _build_observation_matrix(close, vix_series)

        # ── Walk-forward state ────────────────────────────────────────────
        capital         = float(starting_capital)
        reserved_margin = 0.0    # tracks margin tied up in open credit spreads
        equity_curve    = []
        regime_log      = []
        trades:         list[dict] = []
        open_trade:     Optional[dict] = None

        model           = _RegimeModel(n_components=p["n_components"])
        last_retrain    = -p["retrain_every"]   # force fit at first warmup point
        last_posterior  = None

        comm   = p["commission_per_leg"]
        slip   = p["slippage_per_leg"]
        r      = _RISK_FREE_RATE
        q      = float(p.get("dividend_yield", _DEFAULT_DIVIDEND))
        prior_means: Optional[np.ndarray] = None

        for i, dt in enumerate(price_data.index):
            spot   = float(close.iloc[i])
            vix    = float(vix_series.iloc[i])
            # IV: prefer per-ticker ATM IV if provided; otherwise VIX/100 proxy
            if atm_iv_series is not None:
                _iv_val = atm_iv_series.iloc[i] if i < len(atm_iv_series) else float("nan")
                if pd.isna(_iv_val) or _iv_val <= 0:
                    iv = max(vix / 100.0, 0.05)
                else:
                    iv = max(float(_iv_val), 0.05)
            else:
                iv = max(vix / 100.0, 0.05)

            if spot <= 0:
                equity_curve.append({"date": dt, "equity": capital + self._mtm(open_trade, spot, dt, iv, r, q)})
                continue

            # ── Retrain at scheduled cadence, no lookahead ────────────────
            if (
                i >= p["warmup_bars"]
                and (i - last_retrain) >= p["retrain_every"]
            ):
                # SLICE: only data ≤ i (inclusive). predict_proba below uses
                # the SAME slice, so the fit and the inference cannot peek past i.
                X = obs_df.iloc[: i + 1].dropna().values.astype(float)
                if X.shape[0] >= p["n_components"] * 5:
                    try:
                        model.fit(X, prior_sorted_means=prior_means)
                        last_retrain = i
                        sm = model.sorted_means()
                        prior_means = sm   # warm-start the NEXT refit from these
                        logger.debug(
                            f"hmm_regime: refit at bar {i} ({dt.date()}); "
                            f"sorted rv means = {[round(x, 3) for x in sm[:, 2]]}"
                        )
                    except Exception as e:
                        logger.warning(f"hmm_regime: refit failed at {dt.date()}: {e}")

            # ── Posterior for current bar (no lookahead) ──────────────────
            posterior = None
            if model._fitted and i >= p["warmup_bars"]:
                try:
                    X_now = obs_df.iloc[: i + 1].dropna().values.astype(float)
                    if X_now.shape[0] >= p["n_components"] * 5:
                        posterior = model.predict_proba(X_now)
                        last_posterior = posterior
                except Exception as e:
                    logger.debug(f"hmm_regime: posterior failed at {dt.date()}: {e}")
                    posterior = last_posterior

            # ── 1. Manage open trade (exit checks) ────────────────────────
            if open_trade is not None:
                exit_now, exit_reason, pnl = self._evaluate_exit(
                    open_trade, spot, dt, iv, r, q, p, comm, slip, end_of_data=(i == n - 1)
                )
                if exit_now:
                    capital += pnl
                    # Release margin reserved for this trade
                    reserved_margin -= float(open_trade.get("margin", 0.0))
                    trades.append({
                        **{k: open_trade.get(k) for k in (
                            "entry_date", "trade_type", "state", "p_state",
                            "contracts", "credit_or_debit", "max_loss",
                        )},
                        "exit_date":   dt,
                        "exit_reason": exit_reason,
                        "pnl":         round(pnl, 2),
                        "winner":      pnl > 0,
                    })
                    open_trade = None

            # ── 2. Regime log ─────────────────────────────────────────────
            regime_log.append({
                "date":      dt,
                "spot":      round(spot, 2),
                "vix":       round(vix, 2),
                "p_state0":  round(float(posterior[0]), 3) if posterior is not None else None,
                "p_state1":  round(float(posterior[1]), 3) if posterior is not None else None,
                "p_state2":  round(float(posterior[2]), 3) if posterior is not None else None,
                "state":     int(np.argmax(posterior)) if posterior is not None else None,
                "p_state":   round(float(np.max(posterior)), 3) if posterior is not None else None,
                "n_open":    1 if open_trade is not None else 0,
            })

            # ── 3. Entry ──────────────────────────────────────────────────
            # Forward posterior (expected regime distribution over the option's
            # life). With hmmlearn we have a transition matrix and project
            # posterior @ A^H; with the iid fallback we degrade to the spot
            # posterior. Confirming agreement between spot and forward suppresses
            # entries at unstable regime boundaries — the highest-leverage
            # signal-quality fix from the v1.1 review.
            fwd_posterior = None
            if posterior is not None and p.get("use_transition_matrix", True):
                state_now = int(np.argmax(posterior))
                horizon_default = max(p["dte_bull_put"], p["dte_condor"], p["dte_long_put"]) // 2
                horizon = int(p.get("forward_horizon_bars") or horizon_default)
                try:
                    X_now = obs_df.iloc[: i + 1].dropna().values.astype(float)
                    fwd_posterior = model.expected_posterior(X_now, horizon)
                except Exception as e:
                    logger.debug(f"hmm_regime: expected_posterior failed at {dt.date()}: {e}")
                    fwd_posterior = posterior

            gating_post = fwd_posterior if fwd_posterior is not None else posterior

            free_capital = capital - reserved_margin
            base_can_enter = (
                posterior is not None
                and gating_post is not None
                and open_trade is None
                and vix <= p["vix_ceiling"]
                and float(np.max(gating_post)) >= p["regime_confidence_min"]
                and int(np.argmax(gating_post)) == int(np.argmax(posterior))   # spot/forward agree
                and (n - i) > max(p["dte_bull_put"], p["dte_condor"], p["dte_long_put"]) + 5
                and free_capital > 0   # must have free capital after margin reserves
            )

            # ── State-2 defensive gates (added after 2026-05 backtest diagnosis) ──
            # The HMM correctly classifies the crisis state but stays sticky on
            # state 2 for weeks after vol mean-reverts. Two gates:
            #   1. VIX must be descending from its lookback peak (RECOVERY side).
            #   2. State-2 size multiplier (separate parameter, applied below).
            # Setting state2_size_multiplier=0 disables state-2 entries entirely.
            can_enter = base_can_enter
            state2_skip_reason = None
            if base_can_enter and int(np.argmax(posterior)) == 2:
                # Gate 1: VIX descent from lookback peak
                if p.get("state2_require_vix_descending", True):
                    lookback = int(p.get("state2_vix_descent_lookback", 5))
                    descent_pct = float(p.get("state2_vix_descent_pct", 0.15))
                    if descent_pct > 0:
                        lo = max(0, i - lookback)
                        vix_peak = float(vix_series.iloc[lo:i + 1].max())
                        vix_threshold = vix_peak * (1.0 - descent_pct)
                        if vix > vix_threshold:
                            can_enter = False
                            state2_skip_reason = (
                                f"vix {vix:.2f} > peak {vix_peak:.2f} × "
                                f"(1-{descent_pct:.0%}) = {vix_threshold:.2f}"
                            )
                # Gate 2: size multiplier == 0 disables state 2 entirely
                if can_enter and float(p.get("state2_size_multiplier", 0.5)) <= 0.0:
                    can_enter = False
                    state2_skip_reason = "state2_size_multiplier=0 (state 2 disabled)"

            if state2_skip_reason is not None:
                logger.debug(f"hmm_regime: skip state-2 entry at {dt.date()} - {state2_skip_reason}")

            if can_enter:
                state = int(np.argmax(posterior))
                p_st  = float(gating_post[state])
                # Per-state size multiplier (state 2 is half-sized by default)
                size_mult = 1.0
                if state == 2:
                    size_mult = float(p.get("state2_size_multiplier", 0.5))
                # Size against free_capital × size_mult
                sizing_capital = free_capital * size_mult
                trade = self._open_trade(state, p_st, spot, iv, r, q, dt, sizing_capital, p, comm, slip)
                if trade is not None:
                    # Verify margin fits within free capital before opening
                    margin_needed = float(trade.get("margin", 0.0))
                    if margin_needed <= free_capital:
                        open_trade = trade
                        reserved_margin += margin_needed
                        capital -= trade.get("entry_cash_out", 0.0)
                        capital -= trade.get("open_commission", 0.0)
                    else:
                        logger.debug(
                            f"hmm_regime: skip entry at {dt.date()} - margin "
                            f"${margin_needed:,.0f} > free ${free_capital:,.0f}"
                        )

            # ── MTM ───────────────────────────────────────────────────────
            equity = capital + self._mtm(open_trade, spot, dt, iv, r, q)
            equity_curve.append({"date": dt, "equity": equity})

            if progress_callback and i % 50 == 0:
                progress_callback(i / max(1, n), f"HMM regime sim {i}/{n}")

        # ── Build output frames ───────────────────────────────────────────
        eq_df = pd.DataFrame(equity_curve).set_index("date")["equity"].astype(float)
        eq_df = eq_df[~eq_df.index.duplicated(keep="last")]
        daily_returns = eq_df.pct_change().dropna()

        trades_df = pd.DataFrame(trades) if trades else pd.DataFrame()
        regime_df = pd.DataFrame(regime_log)

        bench = price_data["close"].pct_change().reindex(daily_returns.index).dropna() \
            if "close" in price_data.columns else None
        metrics = compute_all_metrics(
            eq_df, trades_df if not trades_df.empty else None, bench
        )

        # Cache trained model for live use
        self._model = model if model._fitted else None

        # Feature 'importance' for an HMM = posterior-mean of each state across the run
        feat_importance = {}
        if not regime_df.empty and "p_state0" in regime_df.columns:
            feat_importance = {
                "mean_p_state0": float(regime_df["p_state0"].mean(skipna=True) or 0.0),
                "mean_p_state1": float(regime_df["p_state1"].mean(skipna=True) or 0.0),
                "mean_p_state2": float(regime_df["p_state2"].mean(skipna=True) or 0.0),
            }

        if not trades_df.empty:
            n_t = len(trades_df)
            n_w = int(trades_df["winner"].sum())
            logger.info(
                f"hmm_regime: {n_t} trades, {n_w} winners "
                f"({100*n_w/n_t:.1f}%), final ${capital:,.0f}"
            )
        else:
            logger.warning("hmm_regime: 0 trades — check confidence floor / data length")

        return BacktestResult(
            strategy_name = self.name,
            equity_curve  = eq_df,
            daily_returns = daily_returns,
            trades        = trades_df,
            metrics       = metrics,
            params        = self.get_params(),
            extra={
                "regime_log":         regime_df,
                "feature_importance": feat_importance,
                "n_open_at_end":      1 if open_trade is not None else 0,
                "hmm_backend":        _HMM_BACKEND,
                "ticker":             ticker,
            },
        )

    # ═══════════════════════════════════════════════════════════════════════
    # Trade open / close primitives — defined-risk, BS-priced
    # ═══════════════════════════════════════════════════════════════════════

    def _open_trade(
        self, state: int, p_state: float, spot: float, iv: float, r: float,
        q: float, dt: pd.Timestamp, capital: float, p: dict, comm: float, slip: float,
    ) -> Optional[dict]:
        if state == 0:
            return self._open_bull_put(spot, iv, r, q, dt, capital, p, comm, slip, p_state)
        if state == 1:
            return self._open_iron_condor(spot, iv, r, q, dt, capital, p, comm, slip, p_state)
        if state == 2:
            return self._open_long_put_spread(spot, iv, r, q, dt, capital, p, comm, slip, p_state)
        return None

    def _open_bull_put(self, spot, iv, r, q, dt, capital, p, comm, slip, p_state):
        T = p["dte_bull_put"] / 365.0
        short_K = _strike_for_delta(spot, T, r, iv, p["bull_put_short_delta"], "put", q=q)
        long_K  = short_K * (1 - p["bull_put_wing_pct"])
        if long_K <= 0:
            return None

        # Credit = short put price - long put price (with slippage adverse)
        sp = bs_price(spot, short_K, T, r, iv, "put", q=q) - slip
        lp = bs_price(spot, long_K,  T, r, iv, "put", q=q) + slip
        credit_per = max(0.01, sp - lp)
        max_loss_per = max(0.01, (short_K - long_K) - credit_per)

        contracts = max(1, int((capital * p["position_size_pct"]) / (max_loss_per * 100)))
        contracts = min(contracts, 50)
        margin    = max_loss_per * contracts * 100
        credit    = credit_per * contracts * 100
        open_comm = 2 * comm * contracts

        return {
            "type":             "bull_put_spread",
            "trade_type":       "bull_put_spread",
            "state":            0,
            "p_state":          p_state,
            "entry_date":       dt,
            "entry_dte":        p["dte_bull_put"],
            "entry_iv":         iv,
            "short_K":          short_K,
            "long_K":           long_K,
            "credit":           credit,                 # dollars
            "credit_or_debit":  round(credit, 2),
            "contracts":        contracts,
            "max_loss":         round(margin, 2),
            "margin":           margin,
            "entry_cash_out":   0.0,                    # credit spread: cash IN, margin reserved separately
            "credit_received":  credit,
            "open_commission":  open_comm,
        }

    def _open_iron_condor(self, spot, iv, r, q, dt, capital, p, comm, slip, p_state):
        T = p["dte_condor"] / 365.0
        call_short_K = _strike_for_delta(spot, T, r, iv, p["condor_short_delta"], "call", q=q)
        put_short_K  = _strike_for_delta(spot, T, r, iv, p["condor_short_delta"], "put", q=q)
        wing = spot * p["condor_wing_pct"]
        call_long_K = call_short_K + wing
        put_long_K  = max(0.01, put_short_K - wing)

        cs = bs_price(spot, call_short_K, T, r, iv, "call", q=q) - slip
        cl = bs_price(spot, call_long_K,  T, r, iv, "call", q=q) + slip
        ps = bs_price(spot, put_short_K,  T, r, iv, "put",  q=q) - slip
        pl = bs_price(spot, put_long_K,   T, r, iv, "put",  q=q) + slip
        credit_per = max(0.01, (cs - cl) + (ps - pl))
        wing_width = max(call_long_K - call_short_K, put_short_K - put_long_K)
        max_loss_per = max(0.01, wing_width - credit_per)

        contracts = max(1, int((capital * p["position_size_pct"]) / (max_loss_per * 100)))
        contracts = min(contracts, 50)
        credit    = credit_per * contracts * 100
        margin    = max_loss_per * contracts * 100
        open_comm = 4 * comm * contracts

        return {
            "type":             "iron_condor",
            "trade_type":       "iron_condor",
            "state":            1,
            "p_state":          p_state,
            "entry_date":       dt,
            "entry_dte":        p["dte_condor"],
            "entry_iv":         iv,
            "call_short_K":     call_short_K,
            "call_long_K":      call_long_K,
            "put_short_K":      put_short_K,
            "put_long_K":       put_long_K,
            "credit":           credit,
            "credit_or_debit":  round(credit, 2),
            "contracts":        contracts,
            "max_loss":         round(margin, 2),
            "margin":           margin,
            "entry_cash_out":   0.0,
            "credit_received":  credit,
            "open_commission":  open_comm,
        }

    def _open_long_put_spread(self, spot, iv, r, q, dt, capital, p, comm, slip, p_state):
        T = p["dte_long_put"] / 365.0
        long_K  = _strike_for_delta(spot, T, r, iv, p["long_put_long_delta"], "put", q=q)
        short_K = max(0.01, long_K * (1 - p["long_put_short_pct"]))

        lp = bs_price(spot, long_K,  T, r, iv, "put", q=q) + slip
        sp = bs_price(spot, short_K, T, r, iv, "put", q=q) - slip
        debit_per = max(0.01, lp - sp)
        max_loss_per = debit_per   # debit spread: max loss = debit paid

        contracts = max(1, int((capital * p["position_size_pct"]) / (max_loss_per * 100)))
        contracts = min(contracts, 50)
        debit     = debit_per * contracts * 100
        open_comm = 2 * comm * contracts

        return {
            "type":             "long_put_spread",
            "trade_type":       "long_put_spread",
            "state":            2,
            "p_state":          p_state,
            "entry_date":       dt,
            "entry_dte":        p["dte_long_put"],
            "entry_iv":         iv,
            "long_K":           long_K,
            "short_K":          short_K,
            "debit":            debit,
            "credit_or_debit":  round(-debit, 2),
            "contracts":        contracts,
            "max_loss":         round(debit, 2),
            "margin":           0.0,
            # Cash-flow note: leaving entry_cash_out at 0 so the debit is paid
            # entirely through realised P&L at exit (pnl = cur_val - debit -
            # close_comm). Setting it to `debit` here would double-count the
            # debit because the exit's `pnl` already subtracts it — that bug
            # in v1 produced spurious -$300+ avg losses on state-2 trades.
            "entry_cash_out":   0.0,
            "credit_received":  0.0,
            "open_commission":  open_comm,
        }

    # ── Exit logic ────────────────────────────────────────────────────────
    def _evaluate_exit(self, trade, spot, now, iv, r, q, p, comm, slip, end_of_data):
        days_held = max(0, (now - trade["entry_date"]).days)
        dte_rem   = max(0, trade["entry_dte"] - days_held)
        T         = max(dte_rem, 1) / 365.0

        if trade["type"] == "bull_put_spread":
            sp = bs_price(spot, trade["short_K"], T, r, iv, "put", q=q) + slip
            lp = bs_price(spot, trade["long_K"],  T, r, iv, "put", q=q) - slip
            cur_cost = max(0.0, sp - lp) * 100 * trade["contracts"]
            credit   = trade["credit_received"]
            pnl      = credit - cur_cost
            close_comm = 2 * comm * trade["contracts"]

            tp = pnl >= p["profit_target_pct"] * credit
            sl = cur_cost >= p["stop_loss_mult"] * credit
            dte_ex = dte_rem <= p["bull_put_dte_exit"]
            if tp or sl or dte_ex or end_of_data:
                reason = "profit_target" if tp else "stop_loss" if sl else "dte_exit" if dte_ex else "end_of_data"
                return True, reason, pnl - close_comm
            return False, None, 0.0

        if trade["type"] == "iron_condor":
            cs = bs_price(spot, trade["call_short_K"], T, r, iv, "call", q=q) + slip
            cl = bs_price(spot, trade["call_long_K"],  T, r, iv, "call", q=q) - slip
            ps = bs_price(spot, trade["put_short_K"],  T, r, iv, "put",  q=q) + slip
            pl = bs_price(spot, trade["put_long_K"],   T, r, iv, "put",  q=q) - slip
            cur_cost = max(0.0, (cs - cl) + (ps - pl)) * 100 * trade["contracts"]
            credit   = trade["credit_received"]
            pnl      = credit - cur_cost
            close_comm = 4 * comm * trade["contracts"]

            tp = pnl >= p["profit_target_pct"] * credit
            sl = cur_cost >= p["stop_loss_mult"] * credit
            dte_ex = dte_rem <= p["condor_dte_exit"]
            if tp or sl or dte_ex or end_of_data:
                reason = "profit_target" if tp else "stop_loss" if sl else "dte_exit" if dte_ex else "end_of_data"
                return True, reason, pnl - close_comm
            return False, None, 0.0

        if trade["type"] == "long_put_spread":
            lp = bs_price(spot, trade["long_K"],  T, r, iv, "put", q=q) - slip
            sp = bs_price(spot, trade["short_K"], T, r, iv, "put", q=q) + slip
            cur_val = max(0.0, lp - sp) * 100 * trade["contracts"]
            debit   = trade["debit"]
            pnl     = cur_val - debit
            close_comm = 2 * comm * trade["contracts"]

            tp = pnl >= p["debit_profit_target"] * debit
            sl = cur_val <= (1 - p["debit_stop_loss_pct"]) * debit
            dte_ex = dte_rem <= p["long_put_dte_exit"]
            if tp or sl or dte_ex or end_of_data:
                reason = "profit_target" if tp else "stop_loss" if sl else "dte_exit" if dte_ex else "end_of_data"
                return True, reason, pnl - close_comm
            return False, None, 0.0

        return False, None, 0.0

    # ── Mark-to-market ────────────────────────────────────────────────────
    def _mtm(self, trade, spot, now, iv, r, q: float = 0.0) -> float:
        if trade is None:
            return 0.0
        days_held = max(0, (now - trade["entry_date"]).days)
        dte_rem   = max(1, trade["entry_dte"] - days_held)
        T         = dte_rem / 365.0

        if trade["type"] == "bull_put_spread":
            sp = bs_price(spot, trade["short_K"], T, r, iv, "put", q=q)
            lp = bs_price(spot, trade["long_K"],  T, r, iv, "put", q=q)
            cur_cost = max(0.0, sp - lp) * 100 * trade["contracts"]
            return trade["credit_received"] - cur_cost

        if trade["type"] == "iron_condor":
            cs = bs_price(spot, trade["call_short_K"], T, r, iv, "call", q=q)
            cl = bs_price(spot, trade["call_long_K"],  T, r, iv, "call", q=q)
            ps = bs_price(spot, trade["put_short_K"],  T, r, iv, "put",  q=q)
            pl = bs_price(spot, trade["put_long_K"],   T, r, iv, "put",  q=q)
            cur_cost = max(0.0, (cs - cl) + (ps - pl)) * 100 * trade["contracts"]
            return trade["credit_received"] - cur_cost

        if trade["type"] == "long_put_spread":
            lp = bs_price(spot, trade["long_K"],  T, r, iv, "put", q=q)
            sp = bs_price(spot, trade["short_K"], T, r, iv, "put", q=q)
            cur_val = max(0.0, lp - sp) * 100 * trade["contracts"]
            return cur_val - trade["debit"]

        return 0.0
