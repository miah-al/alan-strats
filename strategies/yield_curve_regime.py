"""
Yield Curve Regime — AI Strategy.

THESIS
------
The shape and slope of the U.S. Treasury yield curve is one of the most robustly
documented leading indicators of equity-regime transitions. The 2y10y spread leads
the equity cycle by roughly 6-18 months: each of the last seven U.S. recessions was
preceded by a 2y10y inversion, and equity bear markets typically begin 6-12 months
after the inversion clears (Estrella & Mishkin 1998). Ang, Piazzesi & Wei (2006)
formalised the term-structure → growth link in a no-arbitrage VAR; Adrian, Crump &
Moench (2013) decomposed the curve into expectations and term-premium components and
showed the term-premium itself loads on equity risk premia. Stock & Watson (1989)
embedded the slope in the canonical leading-indicator factor model.

The CORE EDGE traded here is NOT direct rates exposure (that is the domain of the
existing TLT/SPY rotation strategies). Instead, a 3-class gradient-boosting classifier
takes 8 yield-curve and credit-stress features and predicts the FORWARD 60-DAY
equity regime (bull / chop / bear). The strategy then expresses that conditional
view through DEFINED-RISK SPY OPTIONS structures — credit spreads when bullish,
iron condors when chop is forecast, debit spreads when bearish. Max loss is bounded
to wing-width minus credit (or to debit paid).

DIFFERENTIATOR vs. rates_spy_rotation / rates_spy_rotation_options
------------------------------------------------------------------
- rates_spy_rotation: rotates SPY/TLT cash positions on rates-momentum regimes.
- rates_spy_rotation_options: long calls/puts on SPY+TLT keyed to rate-equity regime.
- yield_curve_regime: trades SPY OPTIONS SPREADS (defined-risk) on the PREDICTED
  forward-equity regime derived from yield-curve features. No TLT exposure, no
  outright long premium, no asset rotation.

WALK-FORWARD TRAINING
---------------------
- Warmup: 252 bars (one full year — captures yield-curve seasonality and at least
  one quarterly term-premium reset cycle).
- Retrain every 60 bars (roughly each macro quarter).
- Labels are masked over the trailing 60-bar forward window so future returns
  can never leak into the training slice.

FEATURE SET (8 features) — derived from auxiliary_data["macro"]
----------------------------------------------------------------
- yield_2y10y_spread        : current 10y - 2y spread (level)
- yield_2y10y_z_score_252d  : z-score of 2y10y over trailing year
- yield_2y10y_change_30d    : 30-day change in the 2y10y (slope momentum)
- yield_3m10y_spread        : 10y - 3m (alternative recession indicator favoured by NY Fed)
- yield_5y_minus_10y        : curve concavity (negative when curve is humped)
- ted_spread_proxy          : negative of 30-day change in 2y yield — proxies funding stress
- vix_level                 : equity-vol regime
- vix_ma_ratio              : vix / vix_20d_ma — VIX dislocation

LABEL — 3-class forward 60-day regime
--------------------------------------
+1 (BULL) : forward 60d return >= +5% AND realised 60d vol <  20%
 0 (CHOP) : forward 60d return in [-3%, +5%] OR  realised 60d vol >= 20%
-1 (BEAR) : forward 60d return < -3%

TRADE STRUCTURES (defined risk only)
------------------------------------
- BULL predicted : bull put credit spread on SPY (short put -0.20 delta, long put 5% wider)
- CHOP predicted : iron condor on SPY (16-delta wings, 5% wing width)
- BEAR predicted : bear put debit spread on SPY (long put +0.30 delta, short put 5% lower)

DTE 30, profit target 50% of credit / 100% of debit, stop loss 2x credit / 50% of debit.

ENTRY GATING
------------
- P(predicted regime) >= regime_confidence (default 0.55)
- VIX <= vix_max (default 35) to skip dislocations
- max_concurrent open positions enforced (default 2)
"""

from __future__ import annotations

import logging
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

# ── Constants ────────────────────────────────────────────────────────────────
_RISK_FREE_RATE   = 0.045
_FORWARD_DAYS     = 60       # label horizon
_SAVED_MODELS_DIR = Path(__file__).parent.parent / "saved_models"

_LABEL_BULL =  1
_LABEL_CHOP =  0
_LABEL_BEAR = -1


# ── Black-Scholes delta + strike-from-delta helpers ──────────────────────────

def _bs_delta(S: float, K: float, T: float, r: float, sigma: float, option_type: str) -> float:
    if T <= 0 or sigma <= 0 or S <= 0:
        if option_type == "call":
            return 1.0 if S > K else 0.0
        return -1.0 if S < K else 0.0
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    return float(norm.cdf(d1)) if option_type == "call" else float(norm.cdf(d1) - 1.0)


def _strike_for_delta(S: float, T: float, r: float, sigma: float,
                       target_delta: float, option_type: str) -> float:
    if T <= 0 or sigma <= 0 or S <= 0:
        return S
    sign = 1.0 if option_type == "call" else -1.0
    def obj(K: float) -> float:
        return abs(_bs_delta(S, K, T, r, sigma, option_type)) - target_delta
    lo, hi = S * 0.40, S * 1.60
    try:
        return float(brentq(obj, lo, hi, xtol=0.01, maxiter=60))
    except (ValueError, RuntimeError):
        return S * np.exp(sign * sigma * np.sqrt(T))


# ── Feature construction (yield-curve features) ─────────────────────────────

def _build_yield_features(
    close:   pd.Series,
    vix:     pd.Series,
    macro:   pd.DataFrame,
) -> pd.DataFrame:
    """
    Build the 8 yield-curve / vol features. macro must contain rate_2y, rate_10y,
    rate_3m, rate_5y columns. All ffilled to the price index. No look-ahead.
    """
    idx = close.index

    # Re-align macro to price index — ffill (yields publish at most daily)
    rate_2y  = macro["rate_2y" ].reindex(idx).ffill()
    rate_10y = macro["rate_10y"].reindex(idx).ffill()
    rate_3m  = macro["rate_3m" ].reindex(idx).ffill() if "rate_3m" in macro.columns else rate_2y
    rate_5y  = macro["rate_5y" ].reindex(idx).ffill() if "rate_5y" in macro.columns else (rate_2y + rate_10y) / 2.0

    spread_2y10y = rate_10y - rate_2y
    spread_3m10y = rate_10y - rate_3m
    five_minus_ten = rate_5y - rate_10y

    # Z-score of 2y10y over trailing 252 bars (no look-ahead — rolling window)
    rolling_mean = spread_2y10y.rolling(252, min_periods=60).mean()
    rolling_std  = spread_2y10y.rolling(252, min_periods=60).std()
    z_2y10y = (spread_2y10y - rolling_mean) / rolling_std.replace(0, np.nan)

    # 30-day slope momentum
    chg_30d = spread_2y10y - spread_2y10y.shift(30)

    # TED-spread proxy: rising 2y yield = funding stress; we invert sign so
    # high values flag stress (positive change in 2y when 10y stable → curve flattening
    # via funding-rate move).
    ted_proxy = -(rate_2y - rate_2y.shift(30))

    vix_ma20     = vix.rolling(20, min_periods=10).mean()
    vix_ma_ratio = (vix / vix_ma20.replace(0, np.nan)).clip(0.5, 2.5)

    feats = pd.DataFrame({
        "yield_2y10y_spread":       spread_2y10y,
        "yield_2y10y_z_score_252d": z_2y10y,
        "yield_2y10y_change_30d":   chg_30d,
        "yield_3m10y_spread":       spread_3m10y,
        "yield_5y_minus_10y":       five_minus_ten,
        "ted_spread_proxy":         ted_proxy,
        "vix_level":                vix,
        "vix_ma_ratio":             vix_ma_ratio,
    }, index=idx)

    return feats


def _build_regime_labels(close: pd.Series, n_forward: int = _FORWARD_DAYS) -> pd.Series:
    """
    3-class forward-regime label with vol gate.
      +1 BULL : fwd_ret >= +5%  AND realised fwd vol < 20%
       0 CHOP : fwd_ret in [-3%, +5%] OR realised fwd vol >= 20%
      -1 BEAR : fwd_ret < -3%

    Last n_forward rows are NaN (no future return available — no look-ahead).
    """
    n = len(close)
    labels = pd.Series(np.nan, index=close.index, dtype=float)
    if n <= n_forward:
        return labels

    log_ret = np.log(close / close.shift(1))

    for i in range(n - n_forward):
        entry = float(close.iloc[i])
        exit_ = float(close.iloc[i + n_forward])
        if entry <= 0 or np.isnan(exit_):
            continue
        fwd_ret = (exit_ / entry) - 1.0

        window = log_ret.iloc[i + 1: i + 1 + n_forward].dropna()
        if window.empty:
            continue
        ann_vol = float(window.std() * np.sqrt(252))

        if fwd_ret >= 0.05 and ann_vol < 0.20:
            labels.iloc[i] = float(_LABEL_BULL)
        elif fwd_ret < -0.03:
            labels.iloc[i] = float(_LABEL_BEAR)
        else:
            labels.iloc[i] = float(_LABEL_CHOP)

    return labels


# ── Strategy class ──────────────────────────────────────────────────────────

class YieldCurveRegimeStrategy(BaseStrategy):
    """
    Yield-Curve Regime AI strategy.

    A gradient-boosting classifier reads 8 yield-curve / credit-stress / vol
    features and predicts the forward-60-day SPY regime in {bull, chop, bear}.
    The strategy then opens DEFINED-RISK option structures on SPY:

      bull  -> bull put credit spread (-0.20Δ short, 5% wider long)
      chop  -> iron condor (16-delta wings, 5% wide)
      bear  -> bear put debit spread (+0.30Δ long, 5% lower short)

    Walk-forward: 252-bar warmup, retrain every 60 bars, no look-ahead in
    features or labels. Macro auxiliary data is REQUIRED — no synthetic yields.
    """

    name                 = "yield_curve_regime"
    display_name         = "Yield Curve Regime"
    strategy_type        = StrategyType.AI_DRIVEN
    status               = StrategyStatus.ACTIVE
    description          = (
        "GBM classifier on 8 yield-curve / vol features predicts forward 60-day SPY "
        "regime (bull / chop / bear). Trades DEFINED-RISK SPY option spreads keyed to "
        "the predicted regime — credit spreads, iron condors, or debit spreads. "
        "Walk-forward, 252-bar warmup, retrain every 60 bars. Requires FRED daily "
        "yields (rate_2y, rate_10y, rate_3m, rate_5y) in auxiliary_data['macro']."
    )
    asset_class          = "equities_options"
    typical_holding_days = 21
    target_sharpe        = 1.2

    FEATURE_COLS = [
        "yield_2y10y_spread",
        "yield_2y10y_z_score_252d",
        "yield_2y10y_change_30d",
        "yield_3m10y_spread",
        "yield_5y_minus_10y",
        "ted_spread_proxy",
        "vix_level",
        "vix_ma_ratio",
    ]

    _FEATURE_DEFAULTS = {
        "yield_2y10y_spread":       0.005,
        "yield_2y10y_z_score_252d": 0.0,
        "yield_2y10y_change_30d":   0.0,
        "yield_3m10y_spread":       0.005,
        "yield_5y_minus_10y":       0.0,
        "ted_spread_proxy":         0.0,
        "vix_level":                20.0,
        "vix_ma_ratio":             1.0,
    }

    _CRITICAL_FEATURES = {"yield_2y10y_spread", "vix_level"}

    def __init__(
        self,
        regime_confidence:  float = 0.55,
        vix_max:            float = 35.0,
        dte_target:         int   = 30,
        profit_target_pct:  float = 0.50,
        stop_loss_mult:     float = 2.0,
        position_size_pct:  float = 0.025,
        max_concurrent:     int   = 2,
        n_estimators:       int   = 80,
        max_depth:          int   = 4,
        learning_rate:      float = 0.05,
        retrain_every:      int   = 60,
        warmup_bars:        int   = 252,
        wing_width_pct:     float = 0.05,
        commission_per_leg: float = 0.65,
    ):
        self.regime_confidence  = regime_confidence
        self.vix_max            = vix_max
        self.dte_target         = dte_target
        self.profit_target_pct  = profit_target_pct
        self.stop_loss_mult     = stop_loss_mult
        self.position_size_pct  = position_size_pct
        self.max_concurrent     = max_concurrent
        self.n_estimators       = n_estimators
        self.max_depth          = max_depth
        self.learning_rate      = learning_rate
        self.retrain_every      = retrain_every
        self.warmup_bars        = warmup_bars
        self.wing_width_pct     = wing_width_pct
        self.commission_per_leg = commission_per_leg
        self._model             = None
        self._classes           = None  # cached label classes seen at training

    # ── Trainable contract ───────────────────────────────────────────────────

    def is_trainable(self) -> bool:
        return True

    def get_params(self) -> dict:
        return {
            "regime_confidence":  self.regime_confidence,
            "vix_max":            self.vix_max,
            "dte_target":         self.dte_target,
            "profit_target_pct":  self.profit_target_pct,
            "stop_loss_mult":     self.stop_loss_mult,
            "position_size_pct":  self.position_size_pct,
            "max_concurrent":     self.max_concurrent,
            "n_estimators":       self.n_estimators,
            "max_depth":          self.max_depth,
            "learning_rate":      self.learning_rate,
            "retrain_every":      self.retrain_every,
            "warmup_bars":        self.warmup_bars,
            "wing_width_pct":     self.wing_width_pct,
            "commission_per_leg": self.commission_per_leg,
        }

    def get_backtest_ui_params(self) -> list:
        return [
            {"key": "regime_confidence", "label": "Regime confidence",
             "type": "slider", "min": 0.45, "max": 0.80, "default": 0.55, "step": 0.05,
             "col": 0, "row": 0,
             "help": "Min P(predicted regime) to trade — higher = fewer, higher-conviction entries"},
            {"key": "vix_max",           "label": "VIX ceiling",
             "type": "slider", "min": 25.0, "max": 50.0, "default": 35.0, "step": 1.0,
             "col": 1, "row": 0,
             "help": "Skip new entries when VIX is above this — avoid dislocations"},
            {"key": "dte_target",        "label": "Target DTE",
             "type": "slider", "min": 21, "max": 60, "default": 30, "step": 1,
             "col": 2, "row": 0,
             "help": "Days-to-expiry at entry"},
            {"key": "wing_width_pct",    "label": "Wing width (% spot)",
             "type": "slider", "min": 0.03, "max": 0.10, "default": 0.05, "step": 0.01,
             "col": 0, "row": 1,
             "help": "Width of credit/debit spreads as % of SPY spot"},
            {"key": "profit_target_pct", "label": "Profit target (% credit)",
             "type": "slider", "min": 0.25, "max": 0.75, "default": 0.50, "step": 0.05,
             "col": 1, "row": 1,
             "help": "Close credit spreads at this fraction of max credit captured"},
            {"key": "position_size_pct", "label": "Position size",
             "type": "slider", "min": 0.01, "max": 0.05, "default": 0.025, "step": 0.005,
             "col": 2, "row": 1,
             "help": "Capital at risk per trade as fraction of equity"},
            {"key": "max_concurrent",    "label": "Max concurrent",
             "type": "slider", "min": 1, "max": 4, "default": 2, "step": 1,
             "col": 0, "row": 2,
             "help": "Maximum open spreads at any time"},
            {"key": "n_estimators",      "label": "GBM trees",
             "type": "slider", "min": 40, "max": 160, "default": 80, "step": 20,
             "col": 1, "row": 2,
             "help": "Gradient-boosting tree count"},
        ]

    # ── Persistence ──────────────────────────────────────────────────────────

    def save_model(self, ticker: str = "SPY") -> str:
        _SAVED_MODELS_DIR.mkdir(parents=True, exist_ok=True)
        path = _SAVED_MODELS_DIR / f"yield_curve_regime_{ticker.lower()}.pkl"
        with open(path, "wb") as f:
            pickle.dump({"model": self._model, "classes": self._classes}, f)
        logger.info(f"yield_curve_regime: model saved to {path}")
        return str(path)

    def load_model(self, ticker: str = "SPY") -> bool:
        path = _SAVED_MODELS_DIR / f"yield_curve_regime_{ticker.lower()}.pkl"
        if not path.exists():
            return False
        with open(path, "rb") as f:
            payload = pickle.load(f)
        if isinstance(payload, dict):
            self._model   = payload.get("model")
            self._classes = payload.get("classes")
        else:
            self._model = payload
        logger.info(f"yield_curve_regime: model loaded from {path}")
        return True

    # ── Feature-row preparation ──────────────────────────────────────────────

    @classmethod
    def _prepare_feat_row(cls, df_slice: pd.DataFrame) -> pd.DataFrame:
        row = df_slice[cls.FEATURE_COLS].copy()
        row = row.ffill()
        for col, default in cls._FEATURE_DEFAULTS.items():
            if col in row.columns:
                row[col] = row[col].fillna(default)
        return row

    # ── Live signal ──────────────────────────────────────────────────────────

    def generate_signal(self, market_snapshot: dict) -> SignalResult:
        vix         = float(market_snapshot.get("vix", 20.0))
        features_df = market_snapshot.get("features_df")

        # Macro data is REQUIRED for inference. Without features_df / model → HOLD.
        if features_df is None or features_df.empty or self._model is None:
            return SignalResult(
                strategy_name=self.name,
                signal="HOLD",
                confidence=0.0,
                position_size_pct=0.0,
                metadata={"reason": "no model or features available"},
            )

        if vix > self.vix_max:
            return SignalResult(
                strategy_name=self.name,
                signal="HOLD",
                confidence=0.0,
                position_size_pct=0.0,
                metadata={"reason": "vix above ceiling", "vix": vix},
            )

        try:
            feat_row = self._prepare_feat_row(features_df.iloc[-1:])
            critical_nan = feat_row[list(self._CRITICAL_FEATURES)].isna().any(axis=1).iloc[0]
            if critical_nan:
                return SignalResult(self.name, "HOLD", 0.0, 0.0,
                                    metadata={"reason": "critical features NaN"})
            proba = self._model.predict_proba(feat_row.values)[0]
            classes = self._classes if self._classes is not None else list(range(len(proba)))
            prob_map = {int(c): float(p) for c, p in zip(classes, proba)}
        except Exception as e:
            logger.warning(f"yield_curve_regime live signal failed: {e}")
            return SignalResult(self.name, "HOLD", 0.0, 0.0,
                                metadata={"reason": f"inference error: {e}"})

        p_bull = prob_map.get(_LABEL_BULL, 0.0)
        p_bear = prob_map.get(_LABEL_BEAR, 0.0)
        p_chop = prob_map.get(_LABEL_CHOP, 0.0)

        # Pick most-likely class with confidence gate
        best_label, best_p = max(
            ((_LABEL_BULL, p_bull), (_LABEL_CHOP, p_chop), (_LABEL_BEAR, p_bear)),
            key=lambda kv: kv[1],
        )

        if best_p < self.regime_confidence:
            return SignalResult(self.name, "HOLD", round(best_p, 3), 0.0,
                                metadata={"reason": "confidence below threshold",
                                          "p_bull": round(p_bull, 3),
                                          "p_chop": round(p_chop, 3),
                                          "p_bear": round(p_bear, 3)})

        if best_label == _LABEL_BULL:
            signal, structure = "SELL", "bull_put_spread"  # net credit = SELL premium
        elif best_label == _LABEL_BEAR:
            signal, structure = "BUY", "bear_put_spread"   # net debit = BUY premium
        else:
            signal, structure = "SELL", "iron_condor"      # net credit

        return SignalResult(
            strategy_name=self.name,
            signal=signal,
            confidence=round(best_p, 3),
            position_size_pct=self.position_size_pct,
            metadata={
                "structure": structure,
                "predicted_regime": int(best_label),
                "p_bull":  round(p_bull, 3),
                "p_chop":  round(p_chop, 3),
                "p_bear":  round(p_bear, 3),
                "vix":     vix,
            },
        )

    # ── Backtest ─────────────────────────────────────────────────────────────

    def backtest(
        self,
        price_data:        pd.DataFrame,
        auxiliary_data:    dict,
        starting_capital:  float = 100_000,
        regime_confidence: Optional[float] = None,
        vix_max:           Optional[float] = None,
        dte_target:        Optional[int]   = None,
        wing_width_pct:    Optional[float] = None,
        profit_target_pct: Optional[float] = None,
        position_size_pct: Optional[float] = None,
        max_concurrent:    Optional[int]   = None,
        n_estimators:      Optional[int]   = None,
        **kwargs,
    ) -> BacktestResult:
        """Walk-forward yield-curve-regime backtest with inline retraining."""

        try:
            from sklearn.ensemble import GradientBoostingClassifier
            from sklearn.preprocessing import StandardScaler
            from sklearn.pipeline import Pipeline
        except ImportError as e:
            raise ImportError("scikit-learn required: pip install scikit-learn") from e

        # ── Resolve params ───────────────────────────────────────────────────
        conf      = regime_confidence if regime_confidence is not None else self.regime_confidence
        vmax      = vix_max           if vix_max           is not None else self.vix_max
        dte_tgt   = dte_target        if dte_target        is not None else self.dte_target
        ww_pct    = wing_width_pct    if wing_width_pct    is not None else self.wing_width_pct
        pt        = profit_target_pct if profit_target_pct is not None else self.profit_target_pct
        pos_sz    = position_size_pct if position_size_pct is not None else self.position_size_pct
        max_conc  = max_concurrent    if max_concurrent    is not None else self.max_concurrent
        n_est     = n_estimators      if n_estimators      is not None else self.n_estimators
        sl_mult   = self.stop_loss_mult
        comm      = self.commission_per_leg
        warmup    = self.warmup_bars
        retrain_every = self.retrain_every
        r         = _RISK_FREE_RATE

        # ── Validate macro data (REQUIRED — no fabrication) ──────────────────
        macro = auxiliary_data.get("macro") if auxiliary_data is not None else None
        if macro is None or (isinstance(macro, pd.DataFrame) and macro.empty):
            raise ValueError(
                "yield_curve_regime: auxiliary_data['macro'] is REQUIRED — "
                "must contain rate_2y, rate_10y, rate_3m, rate_5y daily series. "
                "Sync FRED yields in Data Manager → Macro Bars."
            )
        required_cols = {"rate_2y", "rate_10y"}
        missing = required_cols - set(macro.columns)
        if missing:
            raise ValueError(
                f"yield_curve_regime: macro DataFrame missing required columns: {sorted(missing)}. "
                "Need rate_2y and rate_10y at minimum (rate_3m, rate_5y recommended)."
            )

        macro = macro.copy()
        macro.index = pd.to_datetime(macro.index)
        macro = macro.sort_index()

        # ── Align price data ─────────────────────────────────────────────────
        price_data = price_data.copy()
        price_data.index = pd.to_datetime(price_data.index)
        price_data = price_data.sort_index()
        close = price_data["close"]

        # ── VIX (optional but recommended) ───────────────────────────────────
        vix_df = auxiliary_data.get("vix", pd.DataFrame())
        if vix_df is None or (isinstance(vix_df, pd.DataFrame) and vix_df.empty):
            vix = pd.Series(20.0, index=close.index)
        else:
            vix_df = vix_df.copy()
            vix_df.index = pd.to_datetime(vix_df.index)
            vix = vix_df["close"].reindex(close.index).ffill().fillna(20.0)

        # ── Build feature matrix + labels ────────────────────────────────────
        feat_df = _build_yield_features(close, vix, macro)
        labels  = _build_regime_labels(close, n_forward=_FORWARD_DAYS)

        all_dates = list(price_data.index)
        n         = len(all_dates)

        capital         = float(starting_capital)
        reserved_margin = 0.0
        equity_curve    = []
        cash_curve      = []
        unreal_curve    = []
        open_trades:   list[dict] = []
        closed_trades: list[dict] = []
        signal_ledger: list[dict] = []
        regime_series_l: list[dict] = []

        model_pipeline = None
        classes_seen   = None
        last_retrain   = -retrain_every

        for i, dt in enumerate(all_dates):
            spot    = float(close.iloc[i])
            vix_val = float(vix.iloc[i])
            iv_val  = max(vix_val / 100.0, 0.05)

            # ── 1. Manage open trades ────────────────────────────────────────
            still_open: list[dict] = []
            unrealized = 0.0
            for trade in open_trades:
                dte_rem = max(trade["expiry_idx"] - i, 0)
                T_now   = max(dte_rem / 252.0, 1e-6)
                struct  = trade["structure"]

                # Compute current value & PnL per spread
                cur_val, pnl_per = _spread_value_and_pnl(spot, T_now, r, iv_val, trade)
                pnl_tot   = pnl_per * trade["contracts"] * 100
                close_comm = trade["legs"] * comm * trade["contracts"]

                exit_reason = None
                if struct == "bear_put_spread":
                    # Debit structure: PT = +100% of debit (i.e. value doubled),
                    # SL = -50% of debit (i.e. value halved).
                    debit = trade["debit"]
                    if cur_val >= debit * 2.0:
                        exit_reason = "profit_target"
                    elif cur_val <= debit * (1.0 - 0.5):
                        exit_reason = "stop_loss"
                else:
                    # Credit structures: PT = capture pt of credit (cost down to 50% credit).
                    # SL = cur_cost >= sl_mult * credit.
                    credit = trade["credit"]
                    if pnl_per >= pt * credit:
                        exit_reason = "profit_target"
                    elif cur_val >= sl_mult * credit:
                        exit_reason = "stop_loss"

                if exit_reason is None and dte_rem <= 1:
                    exit_reason = "expiry"
                if exit_reason is None and i == n - 1:
                    exit_reason = "end_of_data"

                if exit_reason is not None:
                    net_pnl = round(pnl_tot - close_comm, 2)
                    reserved_margin -= trade["margin_reserved"]
                    capital         += net_pnl
                    closed_trades.append({
                        "entry_date":      trade["entry_date"].date(),
                        "exit_date":       dt.date(),
                        "structure":       struct,
                        "predicted_regime": trade["predicted_regime"],
                        "model_prob":      round(trade["model_prob"], 3),
                        "credit_or_debit": round(trade.get("credit", trade.get("debit", 0.0)), 4),
                        "contracts":       trade["contracts"],
                        "margin_reserved": round(trade["margin_reserved"], 2),
                        "pnl":             net_pnl,
                        "exit_reason":     exit_reason,
                        "dte_held":        trade["dte_entry"] - dte_rem,
                        "winner":          net_pnl > 0,
                    })
                else:
                    still_open.append(trade)
                    unrealized += pnl_tot

            open_trades = still_open
            mtm_equity  = capital + unrealized
            equity_curve.append(mtm_equity)
            cash_curve.append(capital - reserved_margin)
            unreal_curve.append(unrealized)

            # ── 2. Retrain (no look-ahead: labels already masked over n_fwd) ─
            if i >= warmup and (i - last_retrain) >= retrain_every:
                # Cutoff training samples whose labels could leak future info:
                # labels are nan for the trailing _FORWARD_DAYS rows, so cap at i - _FORWARD_DAYS.
                train_cutoff = max(0, i - _FORWARD_DAYS)
                X_train = feat_df[self.FEATURE_COLS].iloc[:train_cutoff].values
                y_train = labels.iloc[:train_cutoff].values
                mask    = ~np.isnan(X_train).any(axis=1) & ~np.isnan(y_train)
                X_tr, y_tr = X_train[mask], y_train[mask].astype(int)

                if len(X_tr) >= 50 and len(np.unique(y_tr)) >= 2:
                    try:
                        pipe = Pipeline([
                            ("scaler", StandardScaler()),
                            ("clf", GradientBoostingClassifier(
                                n_estimators=n_est,
                                max_depth=self.max_depth,
                                learning_rate=self.learning_rate,
                                min_samples_leaf=10,
                                subsample=0.8,
                                random_state=42,
                            )),
                        ])
                        pipe.fit(X_tr, y_tr)
                        model_pipeline = pipe
                        classes_seen   = list(pipe.named_steps["clf"].classes_)
                        last_retrain   = i
                        logger.debug(
                            f"yield_curve_regime: retrained at bar {i} ({dt.date()}) "
                            f"on {len(X_tr)} samples, classes={classes_seen}"
                        )
                    except Exception as e:
                        logger.warning(f"yield_curve_regime: retrain failed at bar {i}: {e}")

            # ── 3. Predict + entry decision ──────────────────────────────────
            enough_history = i >= warmup
            enough_room    = (n - i) > dte_tgt
            ready          = model_pipeline is not None and enough_history

            p_bull = p_chop = p_bear = 0.0
            best_label = None
            best_p     = 0.0
            if ready:
                try:
                    feat_row = self._prepare_feat_row(feat_df.iloc[i:i+1])
                    if not feat_row[list(self._CRITICAL_FEATURES)].isna().any(axis=1).iloc[0]:
                        proba = model_pipeline.predict_proba(feat_row.values)[0]
                        prob_map = {int(c): float(p) for c, p in zip(classes_seen, proba)}
                        p_bull = prob_map.get(_LABEL_BULL, 0.0)
                        p_chop = prob_map.get(_LABEL_CHOP, 0.0)
                        p_bear = prob_map.get(_LABEL_BEAR, 0.0)
                        best_label, best_p = max(
                            ((_LABEL_BULL, p_bull), (_LABEL_CHOP, p_chop), (_LABEL_BEAR, p_bear)),
                            key=lambda kv: kv[1],
                        )
                except Exception:
                    pass

            regime_series_l.append({
                "date":   dt.date(),
                "vix":    round(vix_val, 2),
                "p_bull": round(p_bull, 3),
                "p_chop": round(p_chop, 3),
                "p_bear": round(p_bear, 3),
                "regime": "BULL" if best_label == _LABEL_BULL
                          else "BEAR" if best_label == _LABEL_BEAR
                          else "CHOP" if best_label == _LABEL_CHOP
                          else "NA",
                "n_open": len(open_trades),
            })

            can_enter = (
                ready
                and enough_room
                and best_label is not None
                and best_p >= conf
                and vix_val <= vmax
                and len(open_trades) < max_conc
                and spot > 0
            )
            if not can_enter:
                continue

            # ── 4. Build the regime-conditional spread ──────────────────────
            T_entry    = dte_tgt / 252.0
            wing_dollar = max(spot * ww_pct, 1.0)

            new_trade = _build_spread_trade(
                spot=spot, T=T_entry, r=r, iv=iv_val,
                wing_dollar=wing_dollar,
                regime=best_label,
            )
            if new_trade is None:
                continue

            # Position sizing — risk per trade = pos_sz * capital
            risk_per_spread = new_trade["max_loss_per_spread"] * 100
            if risk_per_spread <= 0:
                continue
            contracts = max(1, int(capital * pos_sz / risk_per_spread))
            contracts = min(contracts, 20)
            margin_needed = risk_per_spread * contracts

            # Skip if margin would breach available capital
            if margin_needed + reserved_margin > capital:
                continue

            open_comm = new_trade["legs"] * comm * contracts
            expiry_idx = min(i + dte_tgt, n - 1)

            new_trade.update({
                "entry_date":      dt,
                "expiry_idx":      expiry_idx,
                "dte_entry":       dte_tgt,
                "contracts":       contracts,
                "margin_reserved": margin_needed,
                "model_prob":      best_p,
                "predicted_regime": int(best_label),
            })
            open_trades.append(new_trade)
            reserved_margin += margin_needed
            capital -= open_comm

            signal_ledger.append({
                "date":            dt.date(),
                "spot":            round(spot, 2),
                "structure":       new_trade["structure"],
                "predicted_regime": int(best_label),
                "p_bull":          round(p_bull, 3),
                "p_chop":          round(p_chop, 3),
                "p_bear":          round(p_bear, 3),
                "credit_or_debit": round(new_trade.get("credit", new_trade.get("debit", 0.0)), 4),
                "contracts":       contracts,
                "vix":             round(vix_val, 2),
            })

        # ── Build outputs ────────────────────────────────────────────────────
        eq          = pd.Series(equity_curve, index=all_dates, dtype=float)
        cash_s      = pd.Series(cash_curve,   index=all_dates, dtype=float)
        unreal_s    = pd.Series(unreal_curve, index=all_dates, dtype=float)
        daily_ret   = eq.pct_change().dropna()
        trades_df   = pd.DataFrame(closed_trades) if closed_trades else pd.DataFrame()
        signal_df   = pd.DataFrame(signal_ledger) if signal_ledger else pd.DataFrame()
        regime_df   = pd.DataFrame(regime_series_l) if regime_series_l else pd.DataFrame()

        # Buy-hold benchmark for compute_all_metrics
        bh_ret = close.pct_change().reindex(eq.index).dropna()
        metrics = compute_all_metrics(
            equity_curve=eq,
            trades_df=trades_df if not trades_df.empty else None,
            benchmark_returns=bh_ret if not bh_ret.empty else None,
        )

        # Save model for live signalling
        self._model   = model_pipeline
        self._classes = classes_seen
        if model_pipeline is not None:
            try:
                self.save_model(auxiliary_data.get("ticker", "SPY"))
            except Exception as e:
                logger.warning(f"yield_curve_regime: model save failed: {e}")

        if not trades_df.empty:
            n_trades  = len(trades_df)
            n_winners = int(trades_df["winner"].sum())
            logger.info(
                f"yield_curve_regime: {n_trades} trades, "
                f"{n_winners}/{n_trades} winners ({100*n_winners/n_trades:.1f}%), "
                f"final ${capital:,.0f}"
            )
        else:
            logger.warning("yield_curve_regime: 0 trades — check confidence / warmup / data")

        feature_importance = {}
        if model_pipeline is not None:
            try:
                feature_importance = dict(zip(
                    self.FEATURE_COLS,
                    model_pipeline.named_steps["clf"].feature_importances_
                ))
            except Exception:
                feature_importance = {}

        return BacktestResult(
            strategy_name = self.name,
            equity_curve  = eq,
            daily_returns = daily_ret,
            trades        = trades_df,
            metrics       = metrics,
            params        = self.get_params(),
            extra         = {
                "signal_ledger":      signal_df,
                "regime_series":      regime_df,
                "feature_importance": feature_importance,
                "n_open_at_end":      len(open_trades),
                "cash_curve":         cash_s,
                "unrealized_curve":   unreal_s,
                "classes_seen":       classes_seen,
            },
        )


# ── Spread builders / valuation ──────────────────────────────────────────────

def _build_spread_trade(*, spot: float, T: float, r: float, iv: float,
                         wing_dollar: float, regime: int) -> dict | None:
    """
    Build a defined-risk spread keyed to predicted regime.
      regime  +1 (BULL) -> bull put credit spread:  short put -0.20Δ, long put 5% lower
      regime  -1 (BEAR) -> bear put debit  spread:  long  put +0.30Δ, short put 5% lower
      regime   0 (CHOP) -> iron condor:             16-delta wings, 5% wing width
    Returns a dict ready to push into open_trades; None if the structure is
    uneconomic (negative credit / debit too low / wing inverted).
    """
    if regime == _LABEL_BULL:
        short_put_K = _strike_for_delta(spot, T, r, iv, 0.20, "put")
        long_put_K  = max(short_put_K - wing_dollar, 1.0)
        if long_put_K >= short_put_K:
            return None
        credit = (
            bs_price(spot, short_put_K, T, r, iv, "put")
            - bs_price(spot, long_put_K,  T, r, iv, "put")
        )
        if credit <= 0.05:
            return None
        wing = short_put_K - long_put_K
        max_loss = wing - credit
        if max_loss <= 0:
            return None
        return {
            "structure":           "bull_put_spread",
            "short_put_K":         short_put_K,
            "long_put_K":          long_put_K,
            "credit":              credit,
            "wing":                wing,
            "max_loss_per_spread": max_loss,
            "legs":                2,
        }

    if regime == _LABEL_BEAR:
        long_put_K  = _strike_for_delta(spot, T, r, iv, 0.30, "put")
        short_put_K = max(long_put_K - wing_dollar, 1.0)
        if short_put_K >= long_put_K:
            return None
        debit = (
            bs_price(spot, long_put_K,  T, r, iv, "put")
            - bs_price(spot, short_put_K, T, r, iv, "put")
        )
        if debit <= 0.05:
            return None
        wing = long_put_K - short_put_K
        max_loss = debit  # capped at debit paid
        return {
            "structure":           "bear_put_spread",
            "long_put_K":          long_put_K,
            "short_put_K":         short_put_K,
            "debit":               debit,
            "wing":                wing,
            "max_loss_per_spread": max_loss,
            "legs":                2,
        }

    # CHOP -> iron condor
    short_call_K = _strike_for_delta(spot, T, r, iv, 0.16, "call")
    short_put_K  = _strike_for_delta(spot, T, r, iv, 0.16, "put")
    long_call_K  = short_call_K + wing_dollar
    long_put_K   = max(short_put_K - wing_dollar, 1.0)
    if long_put_K >= short_put_K or short_call_K >= long_call_K:
        return None
    credit = (
        bs_price(spot, short_call_K, T, r, iv, "call")
        - bs_price(spot, long_call_K,  T, r, iv, "call")
        + bs_price(spot, short_put_K,  T, r, iv, "put")
        - bs_price(spot, long_put_K,   T, r, iv, "put")
    )
    if credit <= 0.10:
        return None
    wing = wing_dollar
    max_loss = wing - credit
    if max_loss <= 0:
        return None
    return {
        "structure":           "iron_condor",
        "short_call_K":        short_call_K,
        "long_call_K":         long_call_K,
        "short_put_K":         short_put_K,
        "long_put_K":          long_put_K,
        "credit":              credit,
        "wing":                wing,
        "max_loss_per_spread": max_loss,
        "legs":                4,
    }


def _spread_value_and_pnl(spot: float, T: float, r: float, iv: float,
                           trade: dict) -> tuple[float, float]:
    """
    Returns (current_value_per_spread, pnl_per_spread).
    For credit structures, value = current cost to close (always >= 0). PnL = credit - cost.
    For debit structures, value = current spread mark. PnL = current_value - debit.
    """
    struct = trade["structure"]
    if struct == "bull_put_spread":
        cost = max(
            bs_price(spot, trade["short_put_K"], T, r, iv, "put")
            - bs_price(spot, trade["long_put_K"],  T, r, iv, "put"),
            0.0,
        )
        return cost, trade["credit"] - cost
    if struct == "bear_put_spread":
        val = max(
            bs_price(spot, trade["long_put_K"],  T, r, iv, "put")
            - bs_price(spot, trade["short_put_K"], T, r, iv, "put"),
            0.0,
        )
        return val, val - trade["debit"]
    # iron condor
    cost = max(
        bs_price(spot, trade["short_call_K"], T, r, iv, "call")
        - bs_price(spot, trade["long_call_K"],  T, r, iv, "call")
        + bs_price(spot, trade["short_put_K"],  T, r, iv, "put")
        - bs_price(spot, trade["long_put_K"],   T, r, iv, "put"),
        0.0,
    )
    return cost, trade["credit"] - cost
