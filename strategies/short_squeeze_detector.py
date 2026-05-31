"""
Short Squeeze Detector — AI Strategy.

THESIS
------
A short squeeze is a self-reinforcing forced-buying event. When a heavily-shorted
stock (short interest > 20% of float, days-to-cover < 5, utilization > 80%) meets
a catalyst (earnings beat, social-media surge, unusual call sweep, insider buy)
that produces an outsized volume print, short sellers' stop-losses fire and prime
brokers issue margin calls, generating a wave of mechanical buying that has no
relation to fundamentals. Long out-of-the-money calls capture the convex upside
of these events with strictly defined downside (the premium paid).

LITERATURE
----------
* D'Avolio (2002), "The market for borrowing stock", J. Financial Economics 66.
    Shows utilization and rebate-rate are necessary preconditions for squeeze
    pressure: limited supply of borrow + high demand → forced covers under stress.
* Diamond & Verrecchia (1987), "Constraints on short-selling and asset price
    adjustment", J. Financial Economics 18. Short-selling constraints predict
    overvaluation; relaxation of those constraints (forced covering) is the
    mechanism that resolves the dislocation rapidly.
* Boehmer, Jones & Zhang (2008), "Which Shorts Are Informed?", J. Finance 63.
    Distinguishes informed shorts (who don't squeeze — they double down on the
    fundamental view) from uninformed shorts (the squeeze fuel). Empirically,
    high-utilization + small-cap + recent volume spike skews towards uninformed
    flow — the configuration this strategy seeks.
* Pedersen (2022) and the broader retail-flow literature post-GME (2021): when
    catalysts are amplified by retail coordination, the convex payoff of OTM
    calls dominates linear stock exposure.

DIFFERENTIATOR FROM short_squeeze_vol_expansion
-----------------------------------------------
short_squeeze_vol_expansion (sibling strategy):
  * trades a BULL CALL SPREAD (defined upside, capped at spread width)
  * uses ONLY options-chain features (call OI concentration, vol/OI ratio, ATM IV)
  * never touches FINRA short-interest data
  * targets a +7% move (modest catalyst-driven repricing)

short_squeeze_detector (THIS strategy):
  * trades LONG CALLS — uncapped upside, lottery-ticket payoff per the existing
    quant guide (dash_app/guide_articles/short_squeeze_detector.md).
  * PRIMARY signal is FINRA-style short-interest data when provided in
    auxiliary_data["short_interest"]: short_interest_pct_float, days_to_cover,
    utilization. These features are the empirical preconditions identified in
    D'Avolio (2002) and the GME / VW case studies.
  * Falls back to an options-only "weak-form" detector when short-interest is
    absent, with reduced confidence and an explicit metadata flag so the user
    knows the model is operating without its primary signal.
  * Targets a +15% move (long calls need bigger moves to overcome time decay).

WALK-FORWARD TRAINING
---------------------
  * Expanding window — model only ever sees data up to and including bar i-1.
  * 90-bar warmup before the first prediction.
  * Retrain every 30 bars.
  * sklearn GradientBoostingClassifier with class_weight='balanced'-equivalent
    (sample_weight when the sklearn version doesn't accept class_weight).
  * Labels are masked for the last `horizon` bars to prevent label leakage.

FEATURE SET
-----------
Full set (11 features, when short_interest provided):
  short_interest_pct_float, days_to_cover, utilization,
  call_oi_concentration, otm_call_vol_5d_change, atm_iv,
  volume_ratio, return_5d, return_20d, vix_level, spy_return_5d

Fallback set (7 features, options + price only):
  call_oi_concentration, otm_call_vol_5d_change, atm_iv,
  volume_ratio, return_5d, return_20d, vix_level

LABEL
-----
squeeze_15pct_5d = 1 if max forward-5d high return ≥ +15% from entry close.
Computed only on bars i where i + horizon < n (otherwise masked = -1 and
excluded from training, eliminating right-edge leakage).

ENTRY GATING
------------
* Model probability ≥ signal_threshold (default 0.55).
* AND volume_ratio > 2.5 (catalyst confirmation — guide checklist).
* AND vix < max_vix (default 32 — broader-market panic kills setups).
* AND when short_interest provided: short_interest_pct > short_int_min (0.20)
       AND days_to_cover < dte_max (7).
* AND fewer than max_concurrent open trades.

TRADE STRUCTURE
---------------
* Long calls otm_pct OTM (default 12%), 30–60 DTE (default 45).
* Position-size by premium-at-risk: contracts ≤ floor(capital * pos_sz / (prem * 100)).
* Hard cap at floor(capital * 0.05 / (prem * 100)) for safety (5% absolute risk).
* Max concurrent: 3 (squeezes are correlated).

COSTS & PRICING
---------------
* Legs priced with the engine's skew-aware pricer (bs_price_skew) when
  available so the OTM call strike reflects the volatility smirk; flat-IV
  Black-Scholes fallback. Because OTM calls sit on the lower-vol wing, skew
  pricing makes the lottery ticket cheaper-but-honest vs. a flat-IV mark.
* Per-leg slippage + commission applied on BOTH entry AND exit, scaled by
  contracts (1 leg per long call) via DEFAULT_SLIPPAGE_PER_LEG /
  DEFAULT_COMMISSION_PER_LEG.

EXITS
-----
* Profit target: +100% on the call premium → close fully.
* Stop loss: −50% on premium.
* Time stop: ≤ 7 DTE.
* Stock-move exit: stock up +30% from entry → close fully (squeeze exhausted).
* End-of-data: close at last bar.
"""

from __future__ import annotations

import logging
import math
import pickle
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
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

# Transaction-cost constants and the skew-aware pricer live in the backtest
# engine. Import them defensively so the module stays importable even if the
# engine API drifts; fall back to conservative defaults / flat IV in that case.
try:  # pragma: no cover - import shim
    from alan_trader.backtest.engine import (
        DEFAULT_SLIPPAGE_PER_LEG,
        DEFAULT_COMMISSION_PER_LEG,
    )
except Exception:  # pragma: no cover
    try:
        from backtest.engine import (
            DEFAULT_SLIPPAGE_PER_LEG,
            DEFAULT_COMMISSION_PER_LEG,
        )
    except Exception:
        DEFAULT_SLIPPAGE_PER_LEG   = 0.05   # per-share adverse fill per leg
        DEFAULT_COMMISSION_PER_LEG = 0.65   # $ per contract per leg

try:  # pragma: no cover - import shim
    from alan_trader.backtest.engine import bs_price_skew
    _HAS_SKEW = True
except Exception:  # pragma: no cover
    try:
        from backtest.engine import bs_price_skew
        _HAS_SKEW = True
    except Exception:
        bs_price_skew = None
        _HAS_SKEW = False

logger = logging.getLogger(__name__)

_MODEL_DIR = Path(__file__).parent.parent / "saved_models"
_MODEL_DIR.mkdir(exist_ok=True)

_RISK_FREE_RATE = 0.045
_WARMUP_BARS    = 90
_RETRAIN_EVERY  = 30
_LABEL_HORIZON  = 5     # forward-bar horizon for the squeeze label
_LABEL_MOVE     = 0.15  # +15% high-return bar threshold

# Per-leg round-trip cost in *contract* dollars (slippage × 100 + commission),
# applied on BOTH entry and exit, scaled by contracts. A long call is a single
# leg, so the per-contract cost is one _LEG_COST each way.
_LEG_COST = DEFAULT_SLIPPAGE_PER_LEG * 100.0 + DEFAULT_COMMISSION_PER_LEG


# ── Helpers ────────────────────────────────────────────────────────────────────

def _round_to_increment(strike: float, spot: float) -> float:
    """Round strike to nearest $1 if spot < $100, else $5."""
    inc = 1.0 if spot < 100.0 else 5.0
    return round(round(strike / inc) * inc, 2)


def _bs_delta(S: float, K: float, T: float, r: float, sigma: float,
              option_type: str) -> float:
    """Black-Scholes delta. Closed-form fallback at boundary."""
    if T <= 0 or sigma <= 0 or S <= 0:
        return (1.0 if S > K else 0.0) if option_type == "call" else (-1.0 if S < K else 0.0)
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    return float(norm.cdf(d1)) if option_type == "call" else float(norm.cdf(d1) - 1.0)


def _leg_price(S: float, K: float, T: float, r: float, iv: float,
               option_type: str) -> float:
    """
    Price a single option leg. Uses the engine's skew-aware pricer when
    available so OTM call strikes (this strategy's only structure) reflect the
    equity-index volatility smirk — OTM calls sit on the LOWER-vol side of the
    skew, so flat-IV pricing would systematically OVER-pay for them and flatter
    the lottery payoff. Falls back to flat-IV Black-Scholes when the engine
    pricer is unavailable. bs_price_skew(S, K, T, r, atm_iv, option_type)
    applies the moneyness skew internally, so we pass the ATM IV directly.
    """
    if _HAS_SKEW:
        try:
            return float(bs_price_skew(S, K, T, r, iv, option_type))
        except Exception:
            pass
    return float(bs_price(S, K, T, r, iv, option_type))


def _normalise_iv(iv_val: float) -> float:
    """ImpliedVol may be stored as 0.40 or 40.0 — return the percent form (40.0)."""
    if not np.isfinite(iv_val) or iv_val <= 0:
        return 0.0
    return iv_val * 100.0 if iv_val < 5.0 else iv_val


def _compute_atm_iv(snap_df: pd.DataFrame, spot: float) -> Optional[float]:
    """Median ATM IV (percent). Returns None when no usable rows."""
    if snap_df is None or snap_df.empty:
        return None
    df = snap_df.copy()
    for col in ("StrikePrice", "ImpliedVol"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "ImpliedVol" not in df.columns or "StrikePrice" not in df.columns:
        return None
    band = df[(df["StrikePrice"] >= spot * 0.95) & (df["StrikePrice"] <= spot * 1.05)]
    if band.empty:
        band = df[(df["StrikePrice"] >= spot * 0.90) & (df["StrikePrice"] <= spot * 1.10)]
    if band.empty:
        return None
    iv_vals = band["ImpliedVol"].dropna()
    iv_vals = iv_vals[iv_vals > 0]
    if iv_vals.empty:
        return None
    return _normalise_iv(float(iv_vals.median()))


# ─────────────────────────────────────────────────────────────────────────────
# Strategy class
# ─────────────────────────────────────────────────────────────────────────────

class ShortSqueezeDetectorStrategy(BaseStrategy):
    """
    AI-driven short-squeeze detector that trades long out-of-the-money calls.

    When auxiliary_data["short_interest"] is provided (FINRA-style date-indexed
    DataFrame with short_interest_pct_float, days_to_cover, utilization), the
    model uses the full 11-feature set including the squeeze preconditions.
    Otherwise it falls back to a 7-feature options-only "weak-form" detector
    and flags the degraded mode in metadata.
    """

    name                 = "short_squeeze_detector"
    display_name         = "Short Squeeze Detector"
    strategy_type        = StrategyType.AI_DRIVEN
    status               = StrategyStatus.ACTIVE
    description          = (
        "GBM classifier scores squeeze potential from FINRA short-interest, days-to-cover, "
        "utilization (when available) plus options-chain features (call OI concentration, "
        "OTM call sweep velocity, ATM IV) and price/volume action. Trades long OTM calls "
        "(30–60 DTE) for convex lottery-ticket payoff with strictly defined max loss. "
        "Walk-forward training: 90-bar warmup, retrain every 30 bars."
    )
    asset_class          = "equities_options"
    typical_holding_days = 10
    target_sharpe        = 1.6

    # ── Feature columns ────────────────────────────────────────────────────────
    FEATURE_COLS_FULL = [
        "short_interest_pct_float",
        "days_to_cover",
        "utilization",
        "call_oi_concentration",
        "otm_call_vol_5d_change",
        "atm_iv",
        "volume_ratio",
        "return_5d",
        "return_20d",
        "vix_level",
        "spy_return_5d",
    ]

    FEATURE_COLS_FALLBACK = [
        "call_oi_concentration",
        "otm_call_vol_5d_change",
        "atm_iv",
        "volume_ratio",
        "return_5d",
        "return_20d",
        "vix_level",
    ]

    _FEATURE_DEFAULTS = {
        "short_interest_pct_float": 0.10,
        "days_to_cover":            5.0,
        "utilization":              0.50,
        "call_oi_concentration":    0.30,
        "otm_call_vol_5d_change":   0.0,
        "atm_iv":                   40.0,
        "volume_ratio":             1.0,
        "return_5d":                0.0,
        "return_20d":               0.0,
        "vix_level":                20.0,
        "spy_return_5d":            0.0,
    }

    def __init__(
        self,
        signal_threshold:    float = 0.55,   # P(squeeze) ≥ this to enter
        position_size_pct:   float = 0.015,  # capital fraction risked per trade (premium)
        max_vix:             float = 32.0,
        profit_target_pct:   float = 1.00,   # +100% on premium → exit
        stop_loss_pct:       float = 0.50,   # -50% on premium → exit
        dte_entry:           int   = 45,     # target DTE at entry
        dte_time_stop:       int   = 7,      # exit when ≤ this DTE
        stock_move_exit:     float = 0.30,   # +30% stock move → exit
        otm_pct:             float = 0.12,   # call strike = spot × (1 + otm_pct)
        n_estimators:        int   = 80,
        max_depth:           int   = 4,
        max_concurrent:      int   = 3,
        short_int_min:       float = 0.20,   # min SI/float when SI provided
        dtc_max:             float = 7.0,    # max days-to-cover when SI provided
        utilization_min:     float = 0.0,    # set 0.80 to enforce — off by default
        volume_ratio_min:    float = 2.5,    # min today/20d-avg volume
        commission_per_leg:  float = 0.65,   # retained for back-compat; transaction
                                             # costs now use engine _LEG_COST
                                             # (slippage + commission), see backtest()
        absolute_risk_cap:   float = 0.05,   # hard cap on capital risked per trade
    ):
        self.signal_threshold    = signal_threshold
        self.position_size_pct   = position_size_pct
        self.max_vix             = max_vix
        self.profit_target_pct   = profit_target_pct
        self.stop_loss_pct       = stop_loss_pct
        self.dte_entry           = dte_entry
        self.dte_time_stop       = dte_time_stop
        self.stock_move_exit     = stock_move_exit
        self.otm_pct             = otm_pct
        self.n_estimators        = n_estimators
        self.max_depth           = max_depth
        self.max_concurrent      = max_concurrent
        self.short_int_min       = short_int_min
        self.dtc_max             = dtc_max
        self.utilization_min     = utilization_min
        self.volume_ratio_min    = volume_ratio_min
        self.commission_per_leg  = commission_per_leg
        self.absolute_risk_cap   = absolute_risk_cap

        self._model              = None
        self._feature_cols       = self.FEATURE_COLS_FULL
        self._has_short_interest = False
        self._model_meta: dict   = {}

    # ── Public-state helpers ──────────────────────────────────────────────────

    def is_trainable(self) -> bool:
        return True

    def get_params(self) -> dict:
        return {
            "signal_threshold":   self.signal_threshold,
            "position_size_pct":  self.position_size_pct,
            "max_vix":            self.max_vix,
            "profit_target_pct":  self.profit_target_pct,
            "stop_loss_pct":      self.stop_loss_pct,
            "dte_entry":          self.dte_entry,
            "dte_time_stop":      self.dte_time_stop,
            "stock_move_exit":    self.stock_move_exit,
            "otm_pct":            self.otm_pct,
            "n_estimators":       self.n_estimators,
            "max_depth":          self.max_depth,
            "max_concurrent":     self.max_concurrent,
            "short_int_min":      self.short_int_min,
            "dtc_max":            self.dtc_max,
            "utilization_min":    self.utilization_min,
            "volume_ratio_min":   self.volume_ratio_min,
            "commission_per_leg": self.commission_per_leg,
            "absolute_risk_cap":  self.absolute_risk_cap,
        }

    def get_backtest_ui_params(self) -> list:
        return [
            {"key": "signal_threshold",  "label": "Signal threshold (P)", "type": "slider",
             "min": 0.45, "max": 0.80, "default": 0.55, "step": 0.05,
             "col": 0, "row": 0,
             "help": "Minimum model probability to enter a long-call position"},
            {"key": "max_vix",           "label": "Max VIX",              "type": "slider",
             "min": 20.0, "max": 45.0, "default": 32.0, "step": 1.0,
             "col": 1, "row": 0,
             "help": "Squeezes are killed by broader-market panic"},
            {"key": "volume_ratio_min",  "label": "Volume spike min",     "type": "slider",
             "min": 1.5, "max": 5.0, "default": 2.5, "step": 0.5,
             "col": 2, "row": 0,
             "help": "Catalyst confirmation: today's volume ≥ N × 20-day average"},
            {"key": "dte_entry",         "label": "Target DTE",           "type": "slider",
             "min": 21, "max": 60, "default": 45, "step": 1,
             "col": 0, "row": 1,
             "help": "Days-to-expiry of the call at entry"},
            {"key": "otm_pct",           "label": "OTM strike %",         "type": "slider",
             "min": 0.05, "max": 0.20, "default": 0.12, "step": 0.01,
             "col": 1, "row": 1,
             "help": "Call strike = spot × (1 + this %)"},
            {"key": "position_size_pct", "label": "Position size %",      "type": "slider",
             "min": 0.005, "max": 0.04, "default": 0.015, "step": 0.005,
             "col": 2, "row": 1,
             "help": "Premium-at-risk per trade as fraction of capital"},
            {"key": "profit_target_pct", "label": "Profit target",        "type": "slider",
             "min": 0.50, "max": 2.00, "default": 1.00, "step": 0.10,
             "col": 0, "row": 2,
             "help": "Close fully when premium gain reaches this %"},
            {"key": "stop_loss_pct",     "label": "Stop loss",            "type": "slider",
             "min": 0.30, "max": 0.80, "default": 0.50, "step": 0.05,
             "col": 1, "row": 2,
             "help": "Close when premium loses this fraction"},
            {"key": "max_concurrent",    "label": "Max concurrent",       "type": "slider",
             "min": 1, "max": 6, "default": 3, "step": 1,
             "col": 2, "row": 2,
             "help": "Cap on simultaneous open trades — squeezes are correlated"},
        ]

    def save_model(self, ticker: str = "default") -> str:
        path = _MODEL_DIR / f"short_squeeze_detector_{ticker.lower()}.pkl"
        with open(path, "wb") as f:
            pickle.dump({
                "model":               self._model,
                "feature_cols":        self._feature_cols,
                "has_short_interest":  self._has_short_interest,
                "meta":                self._model_meta,
            }, f)
        return str(path)

    def load_model(self, ticker: str = "default") -> bool:
        path = _MODEL_DIR / f"short_squeeze_detector_{ticker.lower()}.pkl"
        if not path.exists():
            return False
        with open(path, "rb") as f:
            data = pickle.load(f)
        self._model              = data.get("model")
        self._feature_cols       = data.get("feature_cols", self.FEATURE_COLS_FULL)
        self._has_short_interest = data.get("has_short_interest", False)
        self._model_meta         = data.get("meta", {})
        return True

    # ── Feature engineering ───────────────────────────────────────────────────

    @staticmethod
    def _classify_calls_puts(snap_df: pd.DataFrame):
        """Return (calls_df, puts_df) with numeric columns coerced. None if malformed."""
        if snap_df is None or snap_df.empty:
            return None, None
        df = snap_df.copy()
        for col in ("StrikePrice", "ImpliedVol", "OpenInterest", "Delta", "DTE", "Volume"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        if "OptionType" not in df.columns:
            return None, None
        ot = df["OptionType"].astype(str).str.lower()
        calls = df[ot.str.startswith("c")].dropna(subset=["StrikePrice"])
        puts  = df[ot.str.startswith("p")].dropna(subset=["StrikePrice"])
        return calls, puts

    @staticmethod
    def _otm_call_volume(calls: pd.DataFrame, spot: float) -> float:
        """Sum of call Volume on strikes >= 1.05*spot. Used for sweep detection."""
        if calls is None or calls.empty or "Volume" not in calls.columns:
            return 0.0
        otm = calls[calls["StrikePrice"] >= spot * 1.05]
        if otm.empty:
            return 0.0
        return float(otm["Volume"].fillna(0).sum())

    @staticmethod
    def _call_oi_concentration(calls: pd.DataFrame) -> float:
        """Top-3 strikes' open interest / total call open interest. 0..1."""
        if calls is None or calls.empty or "OpenInterest" not in calls.columns:
            return 0.0
        oi = calls.dropna(subset=["OpenInterest"])
        total = float(oi["OpenInterest"].sum())
        if total <= 0:
            return 0.0
        top3 = float(
            oi.groupby("StrikePrice")["OpenInterest"].sum().nlargest(3).sum()
        )
        return float(top3 / total)

    def _build_feature_matrix(
        self,
        snap_by_date:    dict,
        price_data:      pd.DataFrame,
        vix_series:      pd.Series,
        spy_data:        Optional[pd.DataFrame],
        short_interest:  Optional[pd.DataFrame],
        ticker:          str,
    ) -> pd.DataFrame:
        """
        Build a date-indexed feature matrix. Lookahead-free: every row at date t
        uses only data observed by close of t.
        """
        rows: list[dict] = []
        otm_vol_history: list[tuple[pd.Timestamp, float]] = []  # (date, OTM call vol)

        si_df = None
        if short_interest is not None and not short_interest.empty:
            si_df = short_interest.copy()
            si_df.index = pd.to_datetime(si_df.index)
            si_df = si_df.sort_index()

        dates_sorted = sorted(snap_by_date.keys())
        for d in dates_sorted:
            ts = pd.Timestamp(d)
            if ts not in price_data.index:
                continue
            price_slice = price_data.loc[:ts].tail(60)
            if len(price_slice) < 22:
                continue
            spot = float(price_slice["close"].iloc[-1])
            if spot <= 0:
                continue

            calls, _ = self._classify_calls_puts(snap_by_date[d])
            if calls is None:
                continue

            atm_iv = _compute_atm_iv(snap_by_date[d], spot)
            if atm_iv is None:
                # heuristic from VIX as last resort to keep the matrix populated
                vix_at = float(vix_series.loc[:ts].iloc[-1]) if ts >= vix_series.index.min() else 20.0
                atm_iv = max(vix_at * 1.5, 15.0)  # single-name IV ≈ 1.5× VIX is a coarse proxy

            call_oi_conc = self._call_oi_concentration(calls)

            # OTM call volume → 5-day change
            otm_vol_today = self._otm_call_volume(calls, spot)
            otm_vol_history.append((ts, otm_vol_today))
            otm_vol_5d_change = 0.0
            if len(otm_vol_history) >= 6:
                vol_5d_ago = otm_vol_history[-6][1]
                if vol_5d_ago > 0:
                    otm_vol_5d_change = (otm_vol_today - vol_5d_ago) / vol_5d_ago

            # Price returns
            close_arr = price_slice["close"].values
            ret_5d  = float((close_arr[-1] - close_arr[-6])  / close_arr[-6])  if len(close_arr) >= 6  else 0.0
            ret_20d = float((close_arr[-1] - close_arr[-21]) / close_arr[-21]) if len(close_arr) >= 21 else 0.0

            # Volume ratio
            vol_ratio = 1.0
            if "volume" in price_slice.columns:
                vol_ser = pd.to_numeric(price_slice["volume"], errors="coerce").dropna()
                if len(vol_ser) >= 2:
                    avg = float(vol_ser.iloc[-min(20, len(vol_ser)):-1].mean())
                    today = float(vol_ser.iloc[-1])
                    if avg > 0:
                        vol_ratio = today / avg

            # VIX — use the most recent observation up to (and including) ts
            vix_val = 20.0
            if vix_series is not None and not vix_series.empty:
                vix_at = vix_series.loc[:ts]
                if not vix_at.empty:
                    vix_val = float(vix_at.iloc[-1])

            # SPY 5-day return
            spy_5d = 0.0
            if spy_data is not None and not spy_data.empty and ticker.upper() != "SPY":
                spy_slice = spy_data.loc[:ts].tail(10)
                if len(spy_slice) >= 6:
                    spy_close = spy_slice["close"].values
                    spy_5d = float((spy_close[-1] - spy_close[-6]) / spy_close[-6])

            # Short-interest features (asof — only data published by ts)
            si_pct = self._FEATURE_DEFAULTS["short_interest_pct_float"]
            dtc    = self._FEATURE_DEFAULTS["days_to_cover"]
            util   = self._FEATURE_DEFAULTS["utilization"]
            if si_df is not None:
                # asof match — last row whose index ≤ ts
                asof = si_df.loc[:ts]
                if not asof.empty:
                    last_si = asof.iloc[-1]
                    if "short_interest_pct_float" in last_si:
                        v = last_si["short_interest_pct_float"]
                        if pd.notna(v):
                            si_pct = float(v)
                    if "days_to_cover" in last_si:
                        v = last_si["days_to_cover"]
                        if pd.notna(v):
                            dtc = float(v)
                    if "utilization" in last_si:
                        v = last_si["utilization"]
                        if pd.notna(v):
                            util = float(v)

            rows.append({
                "date":                     ts,
                "short_interest_pct_float": si_pct,
                "days_to_cover":            dtc,
                "utilization":              util,
                "call_oi_concentration":    call_oi_conc,
                "otm_call_vol_5d_change":   otm_vol_5d_change,
                "atm_iv":                   atm_iv,
                "volume_ratio":             vol_ratio,
                "return_5d":                ret_5d,
                "return_20d":               ret_20d,
                "vix_level":                vix_val,
                "spy_return_5d":            spy_5d,
            })

        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows).set_index("date").sort_index()

    # ── Labels ────────────────────────────────────────────────────────────────

    @staticmethod
    def _build_labels(
        price_data: pd.DataFrame,
        feat_index: pd.Index,
        horizon:    int = _LABEL_HORIZON,
        threshold:  float = _LABEL_MOVE,
    ) -> pd.Series:
        """
        squeeze_15pct_5d = 1 if any high in (i, i+horizon] ≥ 1.15 × close[i].
        Labels for the last `horizon` bars are -1 (masked) — these are excluded
        from training to eliminate forward-looking leakage.
        """
        if "high" in price_data.columns:
            highs = pd.to_numeric(price_data["high"], errors="coerce")
        else:
            highs = pd.to_numeric(price_data["close"], errors="coerce")
        close = pd.to_numeric(price_data["close"], errors="coerce")

        labels = np.full(len(feat_index), -1, dtype=int)
        for i, dt in enumerate(feat_index):
            if dt not in close.index:
                continue
            try:
                idx = close.index.get_loc(dt)
            except KeyError:
                continue
            if isinstance(idx, slice):
                idx = idx.start
            fwd_end = idx + horizon
            if fwd_end >= len(close):
                # Cannot observe full forward window → mask
                continue
            entry_px = float(close.iloc[idx])
            if entry_px <= 0 or not np.isfinite(entry_px):
                continue
            window = highs.iloc[idx + 1: fwd_end + 1]
            if window.empty:
                continue
            max_fwd = float(window.max())
            move = (max_fwd - entry_px) / entry_px
            labels[i] = 1 if move >= threshold else 0
        return pd.Series(labels, index=feat_index, name="label", dtype=int)

    # ── Model training ────────────────────────────────────────────────────────

    def _get_classifier(self):
        """sklearn GradientBoostingClassifier (no LightGBM dependency)."""
        from sklearn.ensemble import GradientBoostingClassifier
        return GradientBoostingClassifier(
            n_estimators  = self.n_estimators,
            max_depth     = self.max_depth,
            learning_rate = 0.05,
            subsample     = 0.85,
            random_state  = 42,
        )

    @staticmethod
    def _balanced_sample_weight(y: np.ndarray) -> np.ndarray:
        """Compute class-balanced sample weights (sklearn 'balanced' formula)."""
        y = np.asarray(y).astype(int)
        classes = np.unique(y)
        n_total = float(len(y))
        weights = np.ones_like(y, dtype=float)
        for c in classes:
            n_c = float((y == c).sum())
            if n_c > 0:
                weights[y == c] = n_total / (len(classes) * n_c)
        return weights

    def _train_model(self, X: np.ndarray, y: np.ndarray):
        clf = self._get_classifier()
        sw = self._balanced_sample_weight(y)
        try:
            clf.fit(X, y, sample_weight=sw)
        except Exception as e:
            logger.debug(f"GBC fit with weights failed ({e}); retrying without weights")
            clf = self._get_classifier()
            clf.fit(X, y)
        return clf

    # ── Live signal ───────────────────────────────────────────────────────────

    def generate_signal(self, market_snapshot: dict) -> SignalResult:
        """
        Live signal. Honors hard gates regardless of model state.

        Required snapshot keys (all optional; missing → conservative default):
          vix, volume_ratio, short_interest_pct_float, days_to_cover, utilization,
          call_oi_concentration, otm_call_vol_5d_change, atm_iv,
          return_5d, return_20d, spy_return_5d
        """
        vix          = float(market_snapshot.get("vix", 20.0))
        vol_ratio    = float(market_snapshot.get("volume_ratio", 1.0))
        si_pct       = market_snapshot.get("short_interest_pct_float")
        dtc_val      = market_snapshot.get("days_to_cover")
        util_val     = market_snapshot.get("utilization")
        si_provided  = si_pct is not None and pd.notna(si_pct)

        # Hard gates — fire BEFORE the model
        if vix >= self.max_vix:
            return SignalResult(
                strategy_name=self.name, signal="HOLD",
                confidence=0.0, position_size_pct=0.0,
                metadata={"reason": f"VIX {vix:.1f} ≥ max_vix {self.max_vix}"},
            )
        if vol_ratio < self.volume_ratio_min:
            return SignalResult(
                strategy_name=self.name, signal="HOLD",
                confidence=0.0, position_size_pct=0.0,
                metadata={"reason": f"volume_ratio {vol_ratio:.2f} < min {self.volume_ratio_min}",
                          "volume_ratio": round(vol_ratio, 3)},
            )
        if si_provided:
            if float(si_pct) < self.short_int_min:
                return SignalResult(
                    strategy_name=self.name, signal="HOLD",
                    confidence=0.0, position_size_pct=0.0,
                    metadata={"reason": f"short_interest {float(si_pct):.2%} < min {self.short_int_min:.0%}"},
                )
            if dtc_val is not None and pd.notna(dtc_val) and float(dtc_val) > self.dtc_max:
                return SignalResult(
                    strategy_name=self.name, signal="HOLD",
                    confidence=0.0, position_size_pct=0.0,
                    metadata={"reason": f"days_to_cover {float(dtc_val):.1f} > max {self.dtc_max}"},
                )
            if (self.utilization_min > 0 and util_val is not None and pd.notna(util_val)
                    and float(util_val) < self.utilization_min):
                return SignalResult(
                    strategy_name=self.name, signal="HOLD",
                    confidence=0.0, position_size_pct=0.0,
                    metadata={"reason": f"utilization {float(util_val):.2%} < min {self.utilization_min:.0%}"},
                )

        # Model-less heuristic fallback — modest confidence based on gating only
        if self._model is None:
            heur_conf = 0.0
            if si_provided and float(si_pct) >= self.short_int_min and vol_ratio >= self.volume_ratio_min:
                heur_conf = min(0.4 + float(si_pct), 0.7)
            return SignalResult(
                strategy_name=self.name, signal="HOLD",
                confidence=round(heur_conf, 3), position_size_pct=0.0,
                metadata={"reason": "model not trained — heuristic only",
                          "mode":   "heuristic_no_model",
                          "short_interest_provided": si_provided},
            )

        # Build feature row matching the model's columns
        row = []
        for c in self._feature_cols:
            v = market_snapshot.get(c)
            if v is None or (isinstance(v, float) and not np.isfinite(v)):
                v = self._FEATURE_DEFAULTS.get(c, 0.0)
            row.append(float(v))
        X = np.array([row], dtype=float)

        try:
            proba = self._model.predict_proba(X)[0]
            prob_squeeze = float(proba[1]) if len(proba) > 1 else 0.0
        except Exception as e:
            logger.debug(f"short_squeeze_detector live predict failed: {e}")
            prob_squeeze = 0.0

        if prob_squeeze >= self.signal_threshold:
            return SignalResult(
                strategy_name=self.name, signal="BUY",
                confidence=round(prob_squeeze, 4),
                position_size_pct=self.position_size_pct,
                metadata={
                    "trade_type":             "long_call",
                    "prob_squeeze":           round(prob_squeeze, 4),
                    "vix":                    round(vix, 2),
                    "volume_ratio":           round(vol_ratio, 3),
                    "short_interest_provided": si_provided,
                    "feature_set":            "full" if self._has_short_interest else "fallback",
                },
            )
        return SignalResult(
            strategy_name=self.name, signal="HOLD",
            confidence=round(prob_squeeze, 4), position_size_pct=0.0,
            metadata={"prob_squeeze": round(prob_squeeze, 4),
                      "reason":       "below threshold",
                      "feature_set":  "full" if self._has_short_interest else "fallback"},
        )

    # ── Backtest ──────────────────────────────────────────────────────────────

    def backtest(
        self,
        price_data:        pd.DataFrame,
        auxiliary_data:    dict,
        starting_capital:  float = 100_000,
        ticker:            str   = "UNKNOWN",
        signal_threshold:  Optional[float] = None,
        position_size_pct: Optional[float] = None,
        max_vix:           Optional[float] = None,
        dte_entry:         Optional[int]   = None,
        otm_pct:           Optional[float] = None,
        profit_target_pct: Optional[float] = None,
        stop_loss_pct:     Optional[float] = None,
        max_concurrent:    Optional[int]   = None,
        volume_ratio_min:  Optional[float] = None,
        **kwargs,
    ) -> BacktestResult:
        """
        Walk-forward backtest. No look-ahead.

        auxiliary_data:
          option_snapshots : DataFrame with SnapshotDate, StrikePrice, OptionType,
                             ImpliedVol, OpenInterest, Delta, DTE, Volume — REQUIRED
          vix              : DataFrame date-indexed with 'close' column — REQUIRED
          short_interest   : DataFrame date-indexed with columns
                             ['short_interest_pct_float', 'days_to_cover',
                              'utilization'] — OPTIONAL
          spy_price        : DataFrame date-indexed with 'close' — OPTIONAL
        """
        # ── Resolve effective params ─────────────────────────────────────────
        thresh   = signal_threshold  if signal_threshold  is not None else self.signal_threshold
        pos_sz   = position_size_pct if position_size_pct is not None else self.position_size_pct
        vix_max  = max_vix           if max_vix           is not None else self.max_vix
        dte_eff  = dte_entry         if dte_entry         is not None else self.dte_entry
        otm_eff  = otm_pct           if otm_pct           is not None else self.otm_pct
        pt_eff   = profit_target_pct if profit_target_pct is not None else self.profit_target_pct
        sl_eff   = stop_loss_pct     if stop_loss_pct     is not None else self.stop_loss_pct
        mc_eff   = max_concurrent    if max_concurrent    is not None else self.max_concurrent
        vr_min   = volume_ratio_min  if volume_ratio_min  is not None else self.volume_ratio_min
        dte_stop = self.dte_time_stop
        move_ex  = self.stock_move_exit
        risk_cap = self.absolute_risk_cap
        r        = _RISK_FREE_RATE

        # ── Validate inputs ──────────────────────────────────────────────────
        snap_raw = auxiliary_data.get("option_snapshots")
        if snap_raw is None or (isinstance(snap_raw, pd.DataFrame) and snap_raw.empty):
            raise ValueError(
                "option_snapshots is required. Sync options data in Data Manager → Options."
            )
        if "SnapshotDate" not in snap_raw.columns:
            raise ValueError("option_snapshots must have a 'SnapshotDate' column.")

        vix_df = auxiliary_data.get("vix")
        if vix_df is None or (isinstance(vix_df, pd.DataFrame) and vix_df.empty):
            raise ValueError("VIX data is required. Sync in Data Manager → Macro Bars.")

        # ── Align price_data ─────────────────────────────────────────────────
        price_data = price_data.copy()
        price_data.index = pd.to_datetime(price_data.index)
        price_data = price_data.sort_index()

        vix_df = vix_df.copy()
        vix_df.index = pd.to_datetime(vix_df.index)
        vix_series = vix_df["close"].reindex(price_data.index).ffill().fillna(20.0)

        spy_data = auxiliary_data.get("spy_price")
        if spy_data is not None and isinstance(spy_data, pd.DataFrame) and not spy_data.empty:
            spy_data = spy_data.copy()
            spy_data.index = pd.to_datetime(spy_data.index)
        else:
            spy_data = None

        # ── Decide feature set ───────────────────────────────────────────────
        si_raw = auxiliary_data.get("short_interest")
        has_si = (
            si_raw is not None
            and isinstance(si_raw, pd.DataFrame)
            and not si_raw.empty
            and "short_interest_pct_float" in si_raw.columns
        )
        self._has_short_interest = bool(has_si)
        self._feature_cols = self.FEATURE_COLS_FULL if has_si else self.FEATURE_COLS_FALLBACK
        if has_si:
            logger.info(f"short_squeeze_detector: full feature set ({len(self._feature_cols)} cols) — short interest provided")
        else:
            logger.info(f"short_squeeze_detector: fallback feature set ({len(self._feature_cols)} cols) — no short interest")

        # ── Group option snapshots by date ───────────────────────────────────
        snap_df = snap_raw.copy()
        snap_df["SnapshotDate"] = pd.to_datetime(snap_df["SnapshotDate"])
        snap_by_date = {ts: grp for ts, grp in snap_df.groupby("SnapshotDate")}

        # ── Build feature matrix ─────────────────────────────────────────────
        feature_df = self._build_feature_matrix(
            snap_by_date   = snap_by_date,
            price_data     = price_data,
            vix_series     = vix_series,
            spy_data       = spy_data,
            short_interest = si_raw if has_si else None,
            ticker         = ticker,
        )

        if feature_df.empty:
            return BacktestResult(
                strategy_name = self.name,
                equity_curve  = pd.Series([starting_capital], dtype=float),
                daily_returns = pd.Series(dtype=float),
                trades        = pd.DataFrame(),
                metrics       = {"error": "Feature matrix is empty — insufficient option snapshots"},
                params        = self.get_params(),
                extra         = {"feature_set": "full" if has_si else "fallback"},
            )

        # ── Build labels (lookahead-free) ────────────────────────────────────
        labels = self._build_labels(price_data, feature_df.index)

        all_dates = list(feature_df.index)
        n         = len(all_dates)

        capital        = float(starting_capital)
        equity_list:   list[float] = []
        open_trades:   list[dict]  = []
        closed_trades: list[dict]  = []
        regime_log:    list[dict]  = []
        signal_ledger: list[dict]  = []
        train_events:  list[dict]  = []
        current_model              = None
        n_trains                   = 0

        for fi, dt in enumerate(all_dates):
            feat_row = feature_df.iloc[fi]
            spot     = float(price_data["close"].reindex([dt]).iloc[0]) if dt in price_data.index else float("nan")
            if not np.isfinite(spot) or spot <= 0:
                equity_list.append(capital)
                continue
            atm_iv  = float(feat_row.get("atm_iv", 40.0))
            vix_val = float(feat_row.get("vix_level", 20.0))
            vol_r   = float(feat_row.get("volume_ratio", 1.0))
            si_pct  = float(feat_row.get("short_interest_pct_float", 0.0)) if has_si else None
            dtc_val = float(feat_row.get("days_to_cover", 99.0))            if has_si else None

            # ── Train / retrain model — STRICTLY using data up to bar fi-1 ──
            if fi >= _WARMUP_BARS and (
                current_model is None or (fi - _WARMUP_BARS) % _RETRAIN_EVERY == 0
            ):
                # Past slice: features and labels for bars [0, cutoff). We must
                # NOT look at row fi yet (it's the live decision bar), AND we
                # must PURGE the last _LABEL_HORIZON bars: each label at row j
                # peeks at highs[j+1 : j+horizon+1], so a row at j carries
                # information up to bar j+horizon. Training on rows
                # j > fi-horizon-1 would leak prices at/after the decision bar fi
                # into the model (walk-forward look-ahead). cutoff keeps only
                # rows whose forward label window closed strictly before fi.
                cutoff    = max(0, fi - _LABEL_HORIZON)
                X_past_df = feature_df[self._feature_cols].iloc[:cutoff]
                y_past    = labels.iloc[:cutoff]
                valid_mask = (y_past >= 0) & ~X_past_df.isna().any(axis=1)
                X_tr = X_past_df[valid_mask].values.astype(float)
                y_tr = y_past[valid_mask].values.astype(int)
                if len(X_tr) >= 30 and len(np.unique(y_tr)) >= 2 and y_tr.sum() >= 3:
                    try:
                        current_model = self._train_model(X_tr, y_tr)
                        n_trains += 1
                        train_events.append({
                            "date":        dt.date() if hasattr(dt, "date") else dt,
                            "n_samples":   int(len(X_tr)),
                            "n_positives": int(y_tr.sum()),
                        })
                    except Exception as e:
                        logger.debug(f"short_squeeze_detector: retrain failed at bar {fi}: {e}")

            # ── Exits ────────────────────────────────────────────────────────
            still_open: list[dict] = []
            for trade in open_trades:
                dte_rem = max(trade["expiry_idx"] - fi, 0)
                T_now   = max(dte_rem / 252.0, 1e-6)
                iv_dec  = max(atm_iv / 100.0, 0.05)

                cur_prem = _leg_price(spot, trade["strike"], T_now, r, iv_dec, "call")
                pnl_per  = cur_prem - trade["debit"]
                pnl_tot  = pnl_per * trade["contracts"] * 100
                stock_move = (spot - trade["entry_spot"]) / trade["entry_spot"] if trade["entry_spot"] > 0 else 0.0

                exit_reason: Optional[str] = None
                if trade["debit"] > 0 and pnl_per >= pt_eff * trade["debit"]:
                    exit_reason = "profit_target"
                elif trade["debit"] > 0 and pnl_per <= -sl_eff * trade["debit"]:
                    exit_reason = "stop_loss"
                elif dte_rem <= dte_stop:
                    exit_reason = "dte_stop"
                elif stock_move >= move_ex:
                    exit_reason = "stock_move_exit"
                elif fi == n - 1:
                    exit_reason = "end_of_data"

                if exit_reason:
                    # Exit-side round-trip cost: 1 leg × contracts (the entry-side
                    # cost was already deducted from capital at entry).
                    exit_cost = _LEG_COST * trade["contracts"]
                    net_pnl   = round(pnl_tot - exit_cost, 2)
                    capital  += net_pnl
                    closed_trades.append({
                        "entry_date":  trade["entry_date"].date() if hasattr(trade["entry_date"], "date") else trade["entry_date"],
                        "exit_date":   dt.date() if hasattr(dt, "date") else dt,
                        "trade_type":  "long_call",
                        "strike":      round(trade["strike"], 2),
                        "debit":       round(trade["debit"], 4),
                        "contracts":   trade["contracts"],
                        "pnl":         net_pnl,
                        "exit_reason": exit_reason,
                        "dte_held":    trade["dte_entry"] - dte_rem,
                        "model_prob":  trade.get("model_prob", float("nan")),
                        "winner":      net_pnl > 0,
                    })
                else:
                    still_open.append(trade)
            open_trades = still_open

            # ── Predict ──────────────────────────────────────────────────────
            prob = 0.0
            if current_model is not None:
                X_live = feature_df[self._feature_cols].iloc[fi:fi+1].values.astype(float)
                if not np.isnan(X_live).any():
                    try:
                        proba = current_model.predict_proba(X_live)[0]
                        prob  = float(proba[1]) if len(proba) > 1 else 0.0
                    except Exception:
                        prob = 0.0

            # ── Entry gates ──────────────────────────────────────────────────
            si_pass  = (not has_si) or (si_pct is not None and si_pct >= self.short_int_min and dtc_val is not None and dtc_val <= self.dtc_max)
            can_enter = (
                fi >= _WARMUP_BARS
                and current_model is not None
                and vix_val < vix_max
                and vol_r >= vr_min
                and si_pass
                and prob >= thresh
                and len(open_trades) < mc_eff
                and (n - fi) > dte_stop + 2          # need room before time stop
                and spot > 0
            )

            regime_log.append({
                "date":         dt.date() if hasattr(dt, "date") else dt,
                "spot":         round(spot, 2),
                "vix":          round(vix_val, 2),
                "vol_ratio":    round(vol_r, 3),
                "prob":         round(prob, 4),
                "si_pct":       round(si_pct, 4) if si_pct is not None else None,
                "dtc":          round(dtc_val, 2) if dtc_val is not None else None,
                "n_open":       len(open_trades),
                "decision":     "ENTER" if can_enter else "SKIP",
            })

            entered_this_bar = False
            if can_enter:
                T_entry = dte_eff / 252.0
                iv_dec  = max(atm_iv / 100.0, 0.05)
                strike  = _round_to_increment(spot * (1.0 + otm_eff), spot)
                premium = _leg_price(spot, strike, T_entry, r, iv_dec, "call")

                # Premium-at-risk sizing with absolute cap
                risk_per_contract = premium * 100.0 if premium > 0 else float("inf")
                desired_contracts  = math.floor(capital * pos_sz   / risk_per_contract) if risk_per_contract > 0 else 0
                hard_cap_contracts = math.floor(capital * risk_cap / risk_per_contract) if risk_per_contract > 0 else 0
                contracts = max(0, min(desired_contracts, hard_cap_contracts))
                # Entry-side round-trip cost: 1 leg × contracts.
                entry_cost = _LEG_COST * contracts
                cost       = premium * contracts * 100 + entry_cost

                # All entry-side validity checks gathered into one boolean
                viable = (
                    premium > 0.05
                    and contracts >= 1
                    and cost <= capital
                )
                if viable:
                    entered_this_bar = True
                    capital -= cost
                    expiry_idx = min(fi + dte_eff, n - 1)
                    trade = {
                        "entry_date":  dt,
                        "expiry_idx":  expiry_idx,
                        "dte_entry":   dte_eff,
                        "strike":      strike,
                        "debit":       premium,
                        "contracts":   contracts,
                        "entry_spot":  spot,
                        "model_prob":  prob,
                    }
                    open_trades.append(trade)
                    signal_ledger.append({
                        "date":          dt.date() if hasattr(dt, "date") else dt,
                        "spot":          round(spot, 2),
                        "strike":        round(strike, 2),
                        "premium":       round(premium, 4),
                        "contracts":     contracts,
                        "model_prob":    round(prob, 4),
                        "vix":           round(vix_val, 2),
                        "vol_ratio":     round(vol_r, 3),
                        "si_pct":        round(si_pct, 4) if si_pct is not None else None,
                    })

            # ── Mark-to-market ──────────────────────────────────────────────
            mtm = 0.0
            iv_dec_mtm = max(atm_iv / 100.0, 0.05)
            for ot in open_trades:
                dte_rem = max(ot["expiry_idx"] - fi, 0)
                T_mtm   = max(dte_rem / 252.0, 1e-6)
                cv      = _leg_price(spot, ot["strike"], T_mtm, r, iv_dec_mtm, "call")
                mtm    += (cv - ot["debit"]) * ot["contracts"] * 100
            equity_list.append(capital + mtm)

        # ── Build outputs ────────────────────────────────────────────────────
        equity = pd.Series(equity_list, index=all_dates, dtype=float)
        daily  = equity.pct_change().dropna()
        bh     = price_data["close"].pct_change().reindex(equity.index).dropna()

        trades_df = (
            pd.DataFrame(closed_trades)
            if closed_trades else
            pd.DataFrame(columns=[
                "entry_date", "exit_date", "trade_type", "strike", "debit",
                "contracts", "pnl", "exit_reason", "dte_held", "model_prob", "winner",
            ])
        )

        metrics = compute_all_metrics(
            equity_curve      = equity,
            trades_df         = trades_df if not trades_df.empty else None,
            benchmark_returns = bh,
        )

        # Feature importance (final model only)
        feat_imp: dict = {}
        if current_model is not None:
            try:
                fi_vals = current_model.feature_importances_
                feat_imp = {c: round(float(v), 6) for c, v in zip(self._feature_cols, fi_vals)}
            except AttributeError:
                pass

        self._model = current_model
        self._model_meta = {
            "feature_set":             "full" if has_si else "fallback",
            "n_features":              len(self._feature_cols),
            "n_trainings":              n_trains,
            "warmup_bars":             _WARMUP_BARS,
            "retrain_every":           _RETRAIN_EVERY,
            "label_horizon":           _LABEL_HORIZON,
            "label_threshold":         _LABEL_MOVE,
            "n_feature_rows":          int(len(feature_df)),
            "n_labelled":              int((labels >= 0).sum()),
            "n_positives":             int((labels == 1).sum()),
            "short_interest_provided": bool(has_si),
        }

        return BacktestResult(
            strategy_name = self.name,
            equity_curve  = equity,
            daily_returns = daily,
            trades        = trades_df,
            metrics       = metrics,
            params        = {
                **self.get_params(),
                "signal_threshold":  thresh,
                "position_size_pct": pos_sz,
                "max_vix":           vix_max,
                "dte_entry":         dte_eff,
                "otm_pct":           otm_eff,
                "profit_target_pct": pt_eff,
                "stop_loss_pct":     sl_eff,
                "max_concurrent":    mc_eff,
                "volume_ratio_min":  vr_min,
                "ticker":            ticker,
            },
            extra = {
                "model_meta":         self._model_meta,
                "feature_importance": feat_imp,
                "regime_log":         pd.DataFrame(regime_log) if regime_log else pd.DataFrame(),
                "signal_ledger":      pd.DataFrame(signal_ledger) if signal_ledger else pd.DataFrame(),
                "train_events":       pd.DataFrame(train_events) if train_events else pd.DataFrame(),
                "feature_df":         feature_df,
                "n_open_at_end":      len(open_trades),
                "feature_set":        "full" if has_si else "fallback",
            },
        )
