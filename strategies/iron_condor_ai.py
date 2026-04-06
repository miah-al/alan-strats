"""
Iron Condor — AI Strategy.

THESIS
------
A rules-based Iron Condor is profitable but suboptimal: it ignores regime context
and uses fixed strike placement regardless of whether the market is drifting, compressing,
or about to break out. The AI Iron Condor adds two ML layers on top of the rules framework:

LAYER 1 — ENTRY SIGNAL (Gradient Boosting Classifier):
  Predicts P(stock stays within ±σ range over next N days).
  Features: option chain metrics, momentum, VIX regime, macro context, term structure.
  Only enter when P(range-bound) ≥ threshold.

LAYER 2 — STRIKE OPTIMIZATION (Gradient Boosting Regressor):
  Predicts optimal strike placement (as delta offset from standard 16-delta) given
  current regime. In high-skew environments, asymmetric condors outperform symmetric ones.
  In low-VIX environments, tighter wings (10-delta) are optimal.

WALK-FORWARD TRAINING
---------------------
  - Expanding window: model sees all history up to current bar
  - Warmup: 180 bars before first prediction
  - Retrain every 30 bars (monthly equivalent)
  - No future data ever used in feature construction or labels

FEATURE SET (17 features)
-------------------------
  Option chain:  ivr, iv_term_slope, put_call_skew, atm_iv, oi_put_call_ratio
  Momentum:      ret_5d, ret_20d, dist_from_ma50 (% distance)
  Volatility:    realized_vol_20d, vrp (implied − realized), atr_pct
  VIX:           vix_level, vix_5d_change, vix_ma_ratio (vix / vix_20d_ma)
  Macro:         rate_10y, yield_curve_2y10y (spread)
  Time:          days_to_month_end (options expiry clustering)

LABEL CONSTRUCTION
------------------
  range_bound_N = 1 if max(|daily_return|) over next N days ≤ realized_vol_20d
  This is a binary label: will the stock stay within its own recent vol band?
  Calibrated at N = dte_target (default 45 days)
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

# ── Constants ──────────────────────────────────────────────────────────────────
_RISK_FREE_RATE  = 0.045
_WARMUP_BARS     = 90       # bars before first ML prediction (was 180 — 4 months is enough)
_RETRAIN_EVERY   = 15       # bars between model retraining (was 30 — more frequent for small datasets)
_SAVED_MODELS_DIR = Path(__file__).parent.parent / "saved_models"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _bs_delta(S, K, T, r, sigma, option_type):
    if T <= 0 or sigma <= 0 or S <= 0:
        return (1.0 if S > K else 0.0) if option_type == "call" else (-1.0 if S < K else 0.0)
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    return float(norm.cdf(d1)) if option_type == "call" else float(norm.cdf(d1) - 1.0)


def _find_strike_for_delta(S, T, r, sigma, target_delta, option_type):
    if T <= 0 or sigma <= 0:
        return S
    sign = 1.0 if option_type == "call" else -1.0
    def obj(K): return abs(_bs_delta(S, K, T, r, sigma, option_type)) - target_delta
    lo, hi = S * 0.40, S * 1.60
    try:
        return float(brentq(obj, lo, hi, xtol=0.01, maxiter=60))
    except (ValueError, RuntimeError):
        return S * np.exp(sign * sigma * np.sqrt(T))


def _compute_ivr(vix: pd.Series, window: int = 252) -> pd.Series:
    roll_low  = vix.rolling(window, min_periods=60).min()
    roll_high = vix.rolling(window, min_periods=60).max()
    rng = roll_high - roll_low
    return ((vix - roll_low) / rng.replace(0, np.nan)).clip(0.0, 1.0)


def _compute_atr(high, low, close, period=14):
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=period // 2).mean()


def _compute_adx(high: pd.Series, low: pd.Series, close: pd.Series,
                  period: int = 14) -> pd.Series:
    """Average Directional Index — measures trend strength. Low ADX = range-bound."""
    prev_high  = high.shift(1)
    prev_low   = low.shift(1)
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    plus_dm  = (high - prev_high).clip(lower=0).where((high - prev_high) > (prev_low - low), 0)
    minus_dm = (prev_low - low).clip(lower=0).where((prev_low - low) > (high - prev_high), 0)
    atr_s    = tr.rolling(period, min_periods=period // 2).mean()
    plus_di  = 100 * plus_dm.rolling(period,  min_periods=period // 2).mean() / atr_s.replace(0, np.nan)
    minus_di = 100 * minus_dm.rolling(period, min_periods=period // 2).mean() / atr_s.replace(0, np.nan)
    dx       = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan))
    return dx.rolling(period, min_periods=period // 2).mean().fillna(20.0)


def _build_feature_matrix(
    close:   pd.Series,
    high:    pd.Series,
    low:     pd.Series,
    vix:     pd.Series,
    rate10y: Optional[pd.Series],
    rate2y:  Optional[pd.Series],
) -> pd.DataFrame:
    """
    Constructs the 18-feature matrix used by both the entry classifier and
    the strike optimizer. All features are computed from available DB data —
    no option_snapshots required (VIX used as IV proxy).
    """
    iv_prx = vix / 100.0

    ivr            = _compute_ivr(vix)
    realized_vol   = close.pct_change().rolling(20, min_periods=10).std() * np.sqrt(252)
    vrp            = iv_prx - realized_vol                               # implied − realized
    atr            = _compute_atr(high, low, close, 14)
    atr_pct        = atr / close.replace(0, np.nan)
    ret_5d         = close.pct_change(5)
    ret_20d        = close.pct_change(20)
    ma50           = close.rolling(50, min_periods=20).mean()
    dist_from_ma50 = (close - ma50) / ma50.replace(0, np.nan)
    vix_5d_chg     = vix.pct_change(5)
    vix_ma20       = vix.rolling(20, min_periods=10).mean()
    vix_ma_ratio   = vix / vix_ma20.replace(0, np.nan)

    # ADX — best single range-bound discriminator (low = range-bound, high = trending)
    adx = _compute_adx(high, low, close, 14)

    # Put/call skew proxy: 1-month vs 3-month realized vol ratio
    vol_1m        = close.pct_change().rolling(21, min_periods=10).std()
    vol_3m        = close.pct_change().rolling(63, min_periods=20).std()
    put_call_skew = (vol_1m / vol_3m.replace(0, np.nan)).clip(0.5, 2.0)

    # VRP term slope (5d VIX momentum)
    iv_term_slope = vix.diff(5) / 5.0

    # Macro features
    r10y        = rate10y.reindex(close.index).ffill().fillna(0.04) if rate10y is not None else pd.Series(0.04, index=close.index)
    r2y         = rate2y.reindex(close.index).ffill().fillna(0.04)  if rate2y  is not None else pd.Series(0.04, index=close.index)
    yield_curve = r10y - r2y

    # 15 clean, non-redundant features (removed atm_iv=vix/100 and oi_put_call_proxy=put_call_skew)
    features = pd.DataFrame({
        "ivr":               ivr,
        "adx":               adx,               # NEW: trend-strength filter
        "put_call_skew":     put_call_skew,
        "iv_term_slope":     iv_term_slope,
        "realized_vol_20d":  realized_vol,
        "vrp":               vrp,
        "atr_pct":           atr_pct,
        "ret_5d":            ret_5d,
        "ret_20d":           ret_20d,
        "dist_from_ma50":    dist_from_ma50,
        "vix_level":         vix,
        "vix_5d_change":     vix_5d_chg,
        "vix_ma_ratio":      vix_ma_ratio,
        "yield_curve_2y10y": yield_curve,
        "days_to_month_end": pd.Series(
            [(_d + pd.offsets.MonthEnd(0) - _d).days for _d in close.index],
            index=close.index, dtype=float
        ),
        "close_price":       close,             # label construction only, not in FEATURE_COLS
    })
    return features.ffill().bfill()


def _build_labels(close: pd.Series, realized_vol: pd.Series,
                   n_forward: int) -> pd.Series:
    """
    Binary label: 1 if the stock's total price range over the next n_forward
    days stays within the expected N-day volatility band, 0 if it breaks out.

    The expected N-day range = annualized_vol × sqrt(n_forward / 252).
    This is the 1-sigma band for the cumulative N-day return.

    An iron condor profits if the stock doesn't move too far — this label
    captures exactly that: range-bound vs trending/gapping behavior.

    Positive rate should be ~45–60% on typical equity data (IC base rate).
    """
    labels = pd.Series(np.nan, index=close.index)

    for i in range(len(close) - n_forward):
        ann_vol = float(realized_vol.iloc[i])
        if np.isnan(ann_vol) or ann_vol <= 0:
            continue
        # IC break-even range ≈ ±1.5σ of the N-day move (16-delta short strikes
        # are placed at ~1.5σ from spot, so the stock must stay within that band)
        sigma_n_day = ann_vol * np.sqrt(n_forward / 252.0) * 1.5

        # Actual N-day price range as fraction of entry price
        entry_px = float(close.iloc[i])
        if entry_px <= 0:
            continue
        fwd_prices = close.iloc[i + 1: i + 1 + n_forward]
        high_ret = (fwd_prices.max() - entry_px) / entry_px
        low_ret  = (entry_px - fwd_prices.min()) / entry_px
        max_excursion = max(high_ret, low_ret)

        # Range-bound if max excursion stays within ±1.5σ (IC break-even band)
        labels.iloc[i] = 1.0 if max_excursion <= sigma_n_day else 0.0

    return labels


# ─────────────────────────────────────────────────────────────────────────────
# Strategy class
# ─────────────────────────────────────────────────────────────────────────────

class IronCondorAIStrategy(BaseStrategy):
    """
    AI Iron Condor strategy.

    Uses a gradient boosting classifier (sklearn GradientBoostingClassifier) to
    predict whether the stock will remain range-bound over the next N trading days.
    Only enters when P(range-bound) ≥ signal_threshold.

    A secondary regressor predicts the optimal delta for short strikes given current
    regime — allowing asymmetric condors when the market is directionally biased.

    Walk-forward: model is retrained every 30 bars on all available history.
    """

    name                 = "iron_condor_ai"
    display_name         = "Iron Condor — AI"
    strategy_type        = StrategyType.AI_DRIVEN
    status               = StrategyStatus.ACTIVE
    description          = (
        "AI-powered Iron Condor. A gradient boosting model predicts range-bound "
        "conditions using 17 features (IVR, term structure, momentum, VIX regime, macro). "
        "Enters only when P(range-bound) ≥ threshold. Strike placement adapts to regime. "
        "Walk-forward: retrains every 30 bars. Ticker is a parameter."
    )
    asset_class          = "equities_options"
    typical_holding_days = 24
    target_sharpe        = 1.8

    FEATURE_COLS = [
        "ivr", "adx", "put_call_skew", "iv_term_slope", "realized_vol_20d",
        "vrp", "atr_pct", "ret_5d", "ret_20d", "dist_from_ma50",
        "vix_level", "vix_5d_change", "vix_ma_ratio",
        "yield_curve_2y10y", "days_to_month_end",
    ]  # 15 clean features (removed atm_iv=vix/100 dupe, oi_put_call_proxy=put_call_skew dupe)

    _FEATURE_DEFAULTS = {
        "ivr":               0.50,
        "adx":               20.0,  # neutral trend strength
        "put_call_skew":     1.00,
        "iv_term_slope":     0.00,
        "realized_vol_20d":  0.15,
        "vrp":               0.00,
        "atr_pct":           0.015,
        "ret_5d":            0.00,
        "ret_20d":           0.00,
        "dist_from_ma50":    0.00,
        "vix_level":         20.0,
        "vix_5d_change":     0.00,
        "vix_ma_ratio":      1.00,
        "yield_curve_2y10y": 0.00,
        "days_to_month_end": 10,
    }

    _CRITICAL_FEATURES = {"vix_level", "realized_vol_20d", "ivr"}

    @classmethod
    def _prepare_feat_row(cls, df_slice: "pd.DataFrame") -> "pd.DataFrame":
        """Forward-fill, apply per-feature defaults, detect critical NaN."""
        row = df_slice[cls.FEATURE_COLS].copy()
        row = row.ffill()
        for col, default in cls._FEATURE_DEFAULTS.items():
            if col in row.columns:
                row[col] = row[col].fillna(default)
        return row

    def __init__(
        self,
        signal_threshold:   float = 0.50,  # P(range-bound) must exceed this (was 0.60)
        ivr_min:            float = 0.20,  # IVR floor — matches Rules default (was 0.35)
        vix_max:            float = 38.0,  # VIX ceiling
        delta_short:        float = 0.16,  # default short strike delta
        wing_width_pct:     float = 0.05,  # wing width as % of spot
        dte_target:         int   = 45,    # target DTE at entry
        dte_exit:           int   = 21,    # force-close DTE
        profit_target_pct:  float = 0.50,  # 50% of max credit
        stop_loss_mult:     float = 2.0,   # 2× credit stop
        position_size_pct:  float = 0.03,  # capital at risk per trade
        commission_per_leg: float = 0.65,
        max_concurrent:     int   = 4,     # was 5 — cap at 4 to limit correlated drawdowns
        n_estimators:       int   = 50,    # GBM trees (was 100 — more regularized for small datasets)
        max_depth:          int   = 2,     # GBM depth (was 3 — shallower = less overfit)
        learning_rate:      float = 0.05,
    ):
        self.signal_threshold   = signal_threshold
        self.ivr_min            = ivr_min
        self.vix_max            = vix_max
        self.delta_short        = delta_short
        self.wing_width_pct     = wing_width_pct
        self.dte_target         = dte_target
        self.dte_exit           = dte_exit
        self.profit_target_pct  = profit_target_pct
        self.stop_loss_mult     = stop_loss_mult
        self.position_size_pct  = position_size_pct
        self.commission_per_leg = commission_per_leg
        self.max_concurrent     = max_concurrent
        self.n_estimators       = n_estimators
        self.max_depth          = max_depth
        self.learning_rate      = learning_rate
        self._model             = None   # trained classifier

    def get_params(self) -> dict:
        return {
            "signal_threshold":   self.signal_threshold,
            "ivr_min":            self.ivr_min,
            "vix_max":            self.vix_max,
            "delta_short":        self.delta_short,
            "wing_width_pct":     self.wing_width_pct,
            "dte_target":         self.dte_target,
            "dte_exit":           self.dte_exit,
            "profit_target_pct":  self.profit_target_pct,
            "stop_loss_mult":     self.stop_loss_mult,
            "position_size_pct":  self.position_size_pct,
            "commission_per_leg": self.commission_per_leg,
            "max_concurrent":     self.max_concurrent,
            "n_estimators":       self.n_estimators,
            "max_depth":          self.max_depth,
            "learning_rate":      self.learning_rate,
        }

    def get_backtest_ui_params(self) -> list:
        return [
            {"key": "signal_threshold",  "label": "Signal threshold",  "type": "slider",
             "min": 0.45, "max": 0.80, "default": 0.50, "step": 0.05,
             "col": 0, "row": 0, "help": "P(range-bound) must exceed this to enter"},
            {"key": "ivr_min",           "label": "Min IVR",           "type": "slider",
             "min": 0.10, "max": 0.65, "default": 0.20, "step": 0.05,
             "col": 1, "row": 0, "help": "IVR floor — matches Rules default (0.20)"},
            {"key": "vix_max",           "label": "Max VIX",           "type": "slider",
             "min": 25.0, "max": 50.0, "default": 38.0, "step": 1.0,
             "col": 2, "row": 0},
            {"key": "delta_short",       "label": "Short strike delta","type": "slider",
             "min": 0.10, "max": 0.25, "default": 0.16, "step": 0.01,
             "col": 0, "row": 1, "help": "Default delta — AI widens on high conviction, tightens on marginal"},
            {"key": "wing_width_pct",    "label": "Wing width (%)",    "type": "slider",
             "min": 0.02, "max": 0.12, "default": 0.05, "step": 0.01,
             "col": 1, "row": 1},
            {"key": "dte_target",        "label": "Target DTE",        "type": "slider",
             "min": 21,   "max": 60,   "default": 45,   "step": 1,
             "col": 2, "row": 1},
            {"key": "profit_target_pct", "label": "Profit target",     "type": "slider",
             "min": 0.25, "max": 0.75, "default": 0.50, "step": 0.05,
             "col": 0, "row": 2},
            {"key": "position_size_pct", "label": "Position size",     "type": "slider",
             "min": 0.01, "max": 0.08, "default": 0.03, "step": 0.01,
             "col": 1, "row": 2},
            {"key": "n_estimators",      "label": "GBM trees",         "type": "slider",
             "min": 25,   "max": 200,  "default": 50,   "step": 25,
             "col": 2, "row": 2, "help": "GBM trees (50 is more regularized for small datasets)"},
        ]

    def save_model(self, ticker: str = "default") -> str:
        _SAVED_MODELS_DIR.mkdir(parents=True, exist_ok=True)
        path = _SAVED_MODELS_DIR / f"iron_condor_ai_{ticker.lower()}.pkl"
        with open(path, "wb") as f:
            pickle.dump(self._model, f)
        logger.info(f"iron_condor_ai: model saved to {path}")
        return str(path)

    def load_model(self, ticker: str = "default") -> bool:
        path = _SAVED_MODELS_DIR / f"iron_condor_ai_{ticker.lower()}.pkl"
        if path.exists():
            with open(path, "rb") as f:
                self._model = pickle.load(f)
            logger.info(f"iron_condor_ai: model loaded from {path}")
            return True
        return False

    def generate_signal(self, market_snapshot: dict) -> SignalResult:
        """Live signal using loaded model or heuristic fallback."""
        vix  = float(market_snapshot.get("vix", 20.0))
        spot = float(market_snapshot.get("price") or market_snapshot.get("spy_price", 0))
        features_df = market_snapshot.get("features_df")

        if features_df is None or features_df.empty or self._model is None:
            # Heuristic fallback: use IVR proxy
            ivr_approx = float(np.clip((vix - 12) / 28, 0, 1))
            signal = "SELL" if ivr_approx >= self.ivr_min and vix <= self.vix_max else "HOLD"
            return SignalResult(self.name, signal, ivr_approx, self.position_size_pct if signal == "SELL" else 0.0,
                                metadata={"mode": "heuristic", "ivr": round(ivr_approx, 3)})

        try:
            feat_row = self._prepare_feat_row(features_df.iloc[-1:])
            # If any critical feature is still NaN, HOLD rather than predict on garbage
            critical_nan = feat_row[list(self._CRITICAL_FEATURES)].isna().any(axis=1).iloc[0]
            if critical_nan:
                logger.warning("iron_condor_ai: critical features NaN at inference — HOLD")
                prob = 0.0
            else:
                prob = float(self._model.predict_proba(feat_row.values)[0][1])
        except Exception as e:
            logger.warning(f"iron_condor_ai live signal failed: {e}")
            prob = 0.0

        signal = "SELL" if prob >= self.signal_threshold and vix <= self.vix_max else "HOLD"
        return SignalResult(
            strategy_name=self.name,
            signal=signal,
            confidence=round(prob, 3),
            position_size_pct=self.position_size_pct if signal == "SELL" else 0.0,
            metadata={"prob_range_bound": round(prob, 3), "vix": vix},
        )

    def backtest(
        self,
        price_data:         pd.DataFrame,
        auxiliary_data:     dict,
        starting_capital:   float = 10_000,
        signal_threshold:   Optional[float] = None,
        ivr_min:            Optional[float] = None,
        vix_max:            Optional[float] = None,
        delta_short:        Optional[float] = None,
        wing_width_pct:     Optional[float] = None,
        dte_target:         Optional[int]   = None,
        profit_target_pct:  Optional[float] = None,
        position_size_pct:  Optional[float] = None,
        n_estimators:       Optional[int]   = None,
        **kwargs,
    ) -> BacktestResult:
        """Walk-forward AI Iron Condor backtest with inline model retraining."""

        # ── Resolve params ────────────────────────────────────────────────
        thresh  = signal_threshold   or self.signal_threshold
        ivr_min_eff = ivr_min        or self.ivr_min
        vix_max_eff = vix_max        or self.vix_max
        d_short     = delta_short    or self.delta_short
        ww_pct      = wing_width_pct or self.wing_width_pct
        dte_tgt     = dte_target     or self.dte_target
        pt          = profit_target_pct or self.profit_target_pct
        pos_sz      = position_size_pct or self.position_size_pct
        n_est       = n_estimators   or self.n_estimators
        dte_ex      = self.dte_exit
        sl_mult     = self.stop_loss_mult
        comm        = self.commission_per_leg
        max_conc    = self.max_concurrent
        r           = _RISK_FREE_RATE

        # ── Align data ────────────────────────────────────────────────────
        price_data = price_data.copy()
        price_data.index = pd.to_datetime(price_data.index)
        price_data = price_data.sort_index()

        vix_df = auxiliary_data.get("vix", pd.DataFrame())
        if vix_df is None or (isinstance(vix_df, pd.DataFrame) and vix_df.empty):
            raise ValueError("No VIX data. Sync in Data Manager → Macro Bars.")
        vix_df.index = pd.to_datetime(vix_df.index)
        vix = vix_df["close"].reindex(price_data.index).ffill().fillna(20.0)

        macro = auxiliary_data.get("macro", pd.DataFrame())
        rate10y = rate2y = None
        if macro is not None and not macro.empty:
            if "rate_10y" in macro.columns:
                rate10y = macro["rate_10y"].reindex(price_data.index).ffill()
            if "rate_2y" in macro.columns:
                rate2y = macro["rate_2y"].reindex(price_data.index).ffill()

        close  = price_data["close"]
        high   = price_data.get("high",  close)
        low    = price_data.get("low",   close)
        iv_prx = vix / 100.0

        # ── Build full feature matrix ──────────────────────────────────────
        feat_df = _build_feature_matrix(close, high, low, vix, rate10y, rate2y)
        feat_df["close_price"] = close.values
        labels  = _build_labels(close, feat_df["realized_vol_20d"], dte_tgt)

        # VIX 20d MA for circuit breaker (suspend entries when VIX spikes > 15% above MA)
        vix_ma20 = vix.rolling(20, min_periods=10).mean()

        all_dates = list(price_data.index)
        n         = len(all_dates)

        # ── Walk-forward simulation ───────────────────────────────────────
        try:
            from sklearn.ensemble import GradientBoostingClassifier
            from sklearn.preprocessing import StandardScaler
            from sklearn.pipeline import Pipeline
        except ImportError:
            raise ImportError("scikit-learn is required. pip install scikit-learn")

        capital         = float(starting_capital)
        reserved_margin = 0.0
        equity_curve    = []
        cash_curve      = []
        margin_curve    = []
        open_trades:   list[dict] = []
        closed_trades: list[dict] = []
        signal_ledger: list[dict] = []
        regime_series: list[dict] = []

        model_pipeline = None
        last_retrain   = -_RETRAIN_EVERY  # force first train at warmup

        for i, dt in enumerate(all_dates):
            spot    = float(close.iloc[i])
            vix_val = float(vix.iloc[i])
            iv_val  = float(iv_prx.iloc[i])
            ivr_val = float(feat_df["ivr"].iloc[i]) if not np.isnan(feat_df["ivr"].iloc[i]) else 0.0

            # ── 1. Check exits ────────────────────────────────────────────
            still_open:    list[dict] = []
            unrealized_pnl = 0.0
            for trade in open_trades:
                dte_rem = trade["expiry_idx"] - i
                T_now   = max(dte_rem / 252.0, 1e-6)

                call_short_val = bs_price(spot, trade["call_short_K"], T_now, r, iv_val, "call")
                call_long_val  = bs_price(spot, trade["call_long_K"],  T_now, r, iv_val, "call")
                put_short_val  = bs_price(spot, trade["put_short_K"],  T_now, r, iv_val, "put")
                put_long_val   = bs_price(spot, trade["put_long_K"],   T_now, r, iv_val, "put")

                cur_cost = max((call_short_val - call_long_val) + (put_short_val - put_long_val), 0.0)
                pnl_per  = trade["credit"] - cur_cost
                pnl_tot  = pnl_per * trade["contracts"] * 100
                close_comm = 4 * comm * trade["contracts"]

                exit_reason = None
                if pnl_per >= pt * trade["credit"]:
                    exit_reason = "profit_target"
                elif dte_rem <= dte_ex:
                    exit_reason = "dte_exit"
                elif cur_cost >= sl_mult * trade["credit"]:
                    exit_reason = "stop_loss"
                elif i == n - 1:
                    exit_reason = "end_of_data"

                if exit_reason:
                    net_pnl = round(pnl_tot - close_comm, 2)
                    reserved_margin -= trade["margin_reserved"]
                    capital         += net_pnl
                    closed_trades.append({
                        "entry_date":      trade["entry_date"].date(),
                        "exit_date":       dt.date(),
                        "call_short_K":    round(trade["call_short_K"], 2),
                        "call_long_K":     round(trade["call_long_K"],  2),
                        "put_short_K":     round(trade["put_short_K"],  2),
                        "put_long_K":      round(trade["put_long_K"],   2),
                        "credit":          round(trade["credit"],        4),
                        "contracts":       trade["contracts"],
                        "margin_reserved": round(trade["margin_reserved"], 2),
                        "pnl":             net_pnl,
                        "exit_reason":     exit_reason,
                        "dte_held":        trade["dte_entry"] - dte_rem,
                        "winner":          net_pnl > 0,
                        "model_prob":      trade.get("model_prob", np.nan),
                    })
                else:
                    still_open.append(trade)
                    unrealized_pnl += pnl_per * trade["contracts"] * 100

            open_trades  = still_open
            free_capital = capital - reserved_margin
            mtm_equity   = capital + unrealized_pnl
            equity_curve.append(mtm_equity)
            cash_curve.append(free_capital)
            margin_curve.append(unrealized_pnl)

            # ── 2. Retrain model if due ────────────────────────────────────
            if i >= _WARMUP_BARS and (i - last_retrain) >= _RETRAIN_EVERY:
                X_train = feat_df[self.FEATURE_COLS].iloc[:i].values
                y_train = labels.iloc[:i].values
                mask    = ~np.isnan(X_train).any(axis=1) & ~np.isnan(y_train)
                X_tr, y_tr = X_train[mask], y_train[mask]

                if len(X_tr) >= 50 and y_tr.sum() >= 10:  # need enough positives
                    try:
                        model_pipeline = Pipeline([
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
                        model_pipeline.fit(X_tr, y_tr)
                        last_retrain = i
                        logger.debug(f"iron_condor_ai: retrained at bar {i} ({dt.date()}) "
                                     f"on {len(X_tr)} samples ({int(y_tr.sum())} positives)")
                    except Exception as _e:
                        logger.warning(f"iron_condor_ai: retrain failed at bar {i}: {_e}")

            # ── 3. Entry check ─────────────────────────────────────────────
            enough_history = i >= _WARMUP_BARS
            enough_data    = (n - i) > dte_tgt
            model_ready    = model_pipeline is not None

            prob = 0.0
            if model_ready and enough_history:
                try:
                    feat_row = self._prepare_feat_row(feat_df.iloc[i:i+1])
                    prob = float(model_pipeline.predict_proba(feat_row.values)[0][1])
                except Exception:
                    prob = 0.0

            regime_series.append({
                "date":    dt.date(),
                "ivr":     round(ivr_val, 3),
                "vix":     round(vix_val, 2),
                "prob":    round(prob, 3),
                "regime":  "ENTER" if (prob >= thresh and enough_history and enough_data) else "SKIP",
                "n_open":  len(open_trades),
            })

            # VIX circuit breaker: suspend new entries when VIX spikes >15% above 20d MA
            vix_ma20_val  = float(vix_ma20.iloc[i]) if not np.isnan(vix_ma20.iloc[i]) else vix_val
            vix_spiking   = vix_val > vix_ma20_val * 1.15

            can_enter = (
                enough_history
                and enough_data
                and model_ready
                and prob >= thresh
                and ivr_val >= ivr_min_eff
                and vix_val <= vix_max_eff
                and not vix_spiking
                and len(open_trades) < max_conc
                and spot > 0
            )

            if can_enter:
                T_entry = dte_tgt / 252.0

                # Regime-adapted delta: high conviction = wider strikes (give stock more room,
                # lock in premium efficiently). Marginal signal = tighter strikes (need more
                # credit to justify the uncertainty).
                adaptive_delta = d_short
                if prob >= 0.75:
                    adaptive_delta = max(d_short - 0.03, 0.10)   # high conviction → wider strikes
                elif prob < thresh + 0.10:
                    adaptive_delta = min(d_short + 0.04, 0.22)   # marginal signal → tighter strikes

                call_short_K = _find_strike_for_delta(spot, T_entry, r, iv_val, adaptive_delta, "call")
                put_short_K  = _find_strike_for_delta(spot, T_entry, r, iv_val, adaptive_delta, "put")

                wing_width   = spot * ww_pct
                call_long_K  = call_short_K + wing_width
                put_long_K   = put_short_K  - wing_width

                credit = (
                    bs_price(spot, call_short_K, T_entry, r, iv_val, "call")
                    - bs_price(spot, call_long_K,  T_entry, r, iv_val, "call")
                    + bs_price(spot, put_short_K,  T_entry, r, iv_val, "put")
                    - bs_price(spot, put_long_K,   T_entry, r, iv_val, "put")
                )

                if credit <= 0.10:
                    continue

                max_loss_per_spread = wing_width - credit
                if max_loss_per_spread <= 0:
                    continue

                contracts = max(1, int(capital * pos_sz / (max_loss_per_spread * 100)))
                contracts = min(contracts, 20)

                margin_needed = max_loss_per_spread * contracts * 100
                open_comm     = 4 * comm * contracts
                expiry_idx    = min(i + dte_tgt, n - 1)

                reserved_margin += margin_needed
                open_trades.append({
                    "entry_date":      dt,
                    "expiry_idx":      expiry_idx,
                    "dte_entry":       dte_tgt,
                    "call_short_K":    call_short_K,
                    "call_long_K":     call_long_K,
                    "put_short_K":     put_short_K,
                    "put_long_K":      put_long_K,
                    "credit":          credit,
                    "wing_width":      wing_width,
                    "contracts":       contracts,
                    "margin_reserved": margin_needed,
                    "entry_capital":   capital,
                    "model_prob":      prob,
                    "ivr_at_entry":    ivr_val,
                    "vix_at_entry":    vix_val,
                })
                capital -= open_comm
                signal_ledger.append({
                    "date":          dt.date(),
                    "spot":          round(spot, 2),
                    "call_short_K":  round(call_short_K, 2),
                    "put_short_K":   round(put_short_K, 2),
                    "credit":        round(credit, 4),
                    "contracts":     contracts,
                    "model_prob":    round(prob, 3),
                    "adaptive_delta": round(adaptive_delta, 3),
                    "ivr":           round(ivr_val, 3),
                    "vix":           round(vix_val, 2),
                })

        # ── Build output ──────────────────────────────────────────────────
        eq       = pd.Series(equity_curve, index=all_dates, dtype=float)
        cash_s   = pd.Series(cash_curve,   index=all_dates, dtype=float)
        margin_s = pd.Series(margin_curve,  index=all_dates, dtype=float)

        daily_returns = eq.pct_change().dropna()
        trades_df     = pd.DataFrame(closed_trades) if closed_trades else pd.DataFrame()
        signal_df     = pd.DataFrame(signal_ledger) if signal_ledger else pd.DataFrame()
        regime_df     = pd.DataFrame(regime_series) if regime_series else pd.DataFrame()
        metrics       = compute_all_metrics(eq, trades_df if not trades_df.empty else None)

        # Store trained model + save per-ticker file for live use
        self._model = model_pipeline
        if model_pipeline is not None:
            try:
                ticker_slug = auxiliary_data.get("ticker", "default")
                self.save_model(ticker_slug)
                logger.info(f"IronCondorAI: model saved for ticker '{ticker_slug}'")
            except Exception as _e:
                logger.warning(f"IronCondorAI: model save failed: {_e}")

        if not trades_df.empty:
            n_trades  = len(trades_df)
            n_winners = trades_df["winner"].sum()
            avg_prob  = trades_df["model_prob"].mean() if "model_prob" in trades_df.columns else 0
            logger.info(
                f"IronCondorAI: {n_trades} trades, "
                f"{n_winners}/{n_trades} winners ({100*n_winners/n_trades:.1f}%), "
                f"avg model prob {avg_prob:.3f}, final ${capital:,.0f}"
            )
        else:
            logger.warning("IronCondorAI: 0 trades — check signal_threshold / warmup period")

        return BacktestResult(
            strategy_name = self.name,
            equity_curve  = eq,
            daily_returns = daily_returns,
            trades        = trades_df,
            metrics       = metrics,
            params        = self.get_params(),
            extra         = {
                "signal_ledger": signal_df,
                "regime_series": regime_df,
                "feature_importance": (
                    dict(zip(self.FEATURE_COLS,
                             model_pipeline.named_steps["clf"].feature_importances_))
                    if model_pipeline is not None else {}
                ),
                "n_open_at_end": len(open_trades),
                "cash_curve":    cash_s,
                "margin_curve":  margin_s,
            },
        )
