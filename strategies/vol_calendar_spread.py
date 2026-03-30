"""
Vol Regime Calendar Spread Strategy.

THESIS
------
For any optionable ticker, the market systematically misprices the *level* of
future implied volatility relative to what realized volatility will be.

  Overpriced IV  → IV will compress → Short Calendar (credit spread)
  Underpriced IV → IV will expand   → Long Calendar  (debit spread)

A 3-class XGBoost classifier is trained on four feature groups:
  1. IV term structure   (front IV, back IV, slope, IVR, IVR spread)
  2. Variance risk premium (realized vol, VRP, VRP z-score)
  3. Market context       (VIX, put/call ratio, options volume spike)
  4. News sentiment       (FinBERT ticker + macro sentiment, velocity)

Labels are 5-day forward IV changes bucketed into COMPRESS / NEUTRAL / EXPAND.
Walk-forward expanding-window CV with 20% holdout for OOS evaluation.

TRADE STRUCTURE
---------------
Long Calendar  (EXPAND signal):
  Buy  back-month ATM option  (~45 DTE)
  Sell front-month ATM option (~21 DTE)
  Net: debit — profits if IV expands

Short Calendar (COMPRESS signal):
  Sell back-month ATM option (~45 DTE)
  Buy  front-month ATM option (~21 DTE)
  Net: credit — profits if IV compresses

Strike: ATM (maximises theta window for front leg)
Exit  : 50% max profit, or front-month ≤ 5 DTE, or regime flip

REFERENCES
----------
  PMC 2024 walk-forward study    — XGBoost beats LSTM on limited vol history
  ORATS calendar backtest        — regime filter lifts return from −0.09% → +0.58%
  arXiv 2510.16503               — BERT sentiment coefficient −0.2275 p=0.0016
  ScienceDirect 2024 IV review   — VRP most consistently predictive single feature
"""

from __future__ import annotations

import datetime
import logging
import math
import os
import pickle
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from alan_trader.strategies.base import (
    BaseStrategy,
    BacktestResult,
    SignalResult,
    StrategyStatus,
    StrategyType,
)
from alan_trader.risk.metrics import compute_all_metrics

logger = logging.getLogger(__name__)

# ── Labels ────────────────────────────────────────────────────────────────────
COMPRESS = 0
NEUTRAL  = 1
EXPAND   = 2
LABEL_NAMES = {COMPRESS: "COMPRESS", NEUTRAL: "NEUTRAL", EXPAND: "EXPAND"}

# ── Model persistence ─────────────────────────────────────────────────────────
_MODEL_DIR = Path(__file__).parent.parent / "saved_models"
_MODEL_DIR.mkdir(exist_ok=True)


class VolCalendarSpreadStrategy(BaseStrategy):
    """
    AI-driven Vol Regime Calendar Spread.

    Predicts whether IV will compress or expand over the next 5 trading days
    for any optionable ticker, then trades a credit or debit calendar spread.
    """

    name                 = "vol_calendar_spread"
    display_name         = "Vol Regime Calendar Spread"
    strategy_type        = StrategyType.AI_DRIVEN
    status               = StrategyStatus.ACTIVE
    description          = (
        "XGBoost classifier predicts IV compression or expansion for any ticker. "
        "Credit calendar (short back / buy front) on COMPRESS signal. "
        "Debit calendar (buy back / sell front) on EXPAND signal. "
        "Features: IV term structure, variance risk premium, VIX context, FinBERT news sentiment."
    )
    asset_class          = "equities_options"
    typical_holding_days = 21
    target_sharpe        = 1.2

    # ── Feature column order (must match training) ────────────────────────────
    FEATURE_COLS = [
        # Group 1 — IV term structure
        "front_iv", "back_iv", "term_slope",
        "front_ivr", "back_ivr", "ivr_spread",
        # Group 2 — Variance risk premium
        "realized_vol_20d", "vrp", "vrp_zscore",
        # Group 3 — Market context
        "vix", "pc_ratio", "iv_vol_spike", "ticker_mkt_corr_20d",
        # Group 4 — News sentiment
        "news_sentiment", "macro_sentiment", "sentiment_velocity",
    ]

    def __init__(
        self,
        front_dte_min:      int   = 21,    # min DTE for front-month leg
        front_dte_max:      int   = 35,    # max DTE for front-month leg
        back_dte_target:    int   = 45,    # target DTE for back-month leg
        label_sigma_mult:   float = 0.5,   # σ multiplier for COMPRESS/EXPAND label threshold
        label_horizon:      int   = 5,     # days forward for label construction
        confidence_min:     float = 0.55,  # minimum model confidence to trade
        position_size_pct:  float = 0.05,  # capital % per trade
        min_ivr_compress:   float = 0.50,  # minimum front IVR to consider COMPRESS trade
        max_ivr_expand:     float = 0.60,  # maximum front IVR to consider EXPAND trade
        # ── Quality filters derived from feature distribution analysis ──────
        min_term_slope:     float = -200.0, # steepest backwardation allowed (no floor by default)
        max_term_slope:     float = -5.0,   # flat term structure → skip (wrong signals cluster near 0)
        min_ivr_quality:    float = 0.0,    # minimum IVR for any trade (set >0.6 to target high-IVR wins)
        max_vrp_noisy:      float = 999.0,  # max VRP; set e.g. 15 to avoid the noisy 20-VRP zone
        # ── XGBoost hyperparams ─────────────────────────────────────────────
        n_estimators:       int   = 300,
        max_depth:          int   = 4,
        learning_rate:      float = 0.05,
        subsample:          float = 0.8,
        colsample_bytree:   float = 0.8,
        oos_fraction:       float = 0.20,  # holdout fraction for OOS evaluation
        starting_capital:   float = 100_000.0,
        slippage_per_leg:   float = 0.05,  # dollars per option per share (bid-ask half-spread)
        commission_per_leg: float = 0.65,  # dollars per contract per leg (standard retail)
    ):
        self.starting_capital  = starting_capital
        self.slippage_per_leg  = slippage_per_leg
        self.commission_per_leg = commission_per_leg
        self.front_dte_min     = front_dte_min
        self.front_dte_max     = front_dte_max
        self.back_dte_target   = back_dte_target
        self.label_sigma_mult  = label_sigma_mult
        self.label_horizon     = label_horizon
        self.confidence_min    = confidence_min
        self.position_size_pct = position_size_pct
        self.min_ivr_compress  = min_ivr_compress
        self.max_ivr_expand    = max_ivr_expand
        self.min_term_slope    = min_term_slope
        self.max_term_slope    = max_term_slope
        self.min_ivr_quality   = min_ivr_quality
        self.max_vrp_noisy     = max_vrp_noisy
        self.n_estimators      = n_estimators
        self.max_depth         = max_depth
        self.learning_rate     = learning_rate
        self.subsample         = subsample
        self.colsample_bytree  = colsample_bytree
        self.oos_fraction      = oos_fraction
        self._model            = None   # fitted XGBoost / GBM classifier
        self._model_meta: dict = {}

    # ═════════════════════════════════════════════════════════════════════════
    # Public interface
    # ═════════════════════════════════════════════════════════════════════════

    def get_params(self) -> dict:
        return {
            "front_dte_min":     self.front_dte_min,
            "front_dte_max":     self.front_dte_max,
            "back_dte_target":   self.back_dte_target,
            "label_horizon":     self.label_horizon,
            "confidence_min":    self.confidence_min,
            "position_size_pct": self.position_size_pct,
            "max_term_slope":    self.max_term_slope,
            "min_ivr_quality":   self.min_ivr_quality,
            "max_vrp_noisy":     self.max_vrp_noisy,
            "n_estimators":      self.n_estimators,
            "max_depth":         self.max_depth,
            "learning_rate":     self.learning_rate,
            "oos_fraction":      self.oos_fraction,
        }

    def get_backtest_ui_params(self) -> list[dict]:
        return [
            {"key": "front_dte_min",     "label": "Front DTE min",      "type": "int",   "default": 21,    "min": 7,    "max": 45},
            {"key": "front_dte_max",     "label": "Front DTE max",      "type": "int",   "default": 35,    "min": 14,   "max": 60},
            {"key": "back_dte_target",   "label": "Back DTE target",    "type": "int",   "default": 45,    "min": 30,   "max": 90},
            {"key": "label_horizon",     "label": "Label horizon (days)","type": "int",  "default": 5,     "min": 2,    "max": 10},
            {"key": "label_sigma_mult",  "label": "Label σ threshold",  "type": "float", "default": 0.50,  "min": 0.2,  "max": 1.0,  "step": 0.05},
            {"key": "confidence_min",    "label": "Min confidence",     "type": "float", "default": 0.55,  "min": 0.4,  "max": 0.9,  "step": 0.05},
            {"key": "position_size_pct", "label": "Position size %",    "type": "float", "default": 0.05,  "min": 0.01, "max": 0.20, "step": 0.01},
            # ── Quality filters (from feature distribution analysis) ─────────
            {"key": "max_term_slope",    "label": "Max term slope (skip flat)", "type": "float", "default": -5.0, "min": -30.0, "max": 0.0, "step": 1.0},
            {"key": "min_ivr_quality",   "label": "Min IVR (quality gate)",    "type": "float", "default": 0.0,  "min": 0.0,   "max": 0.9, "step": 0.05},
            {"key": "max_vrp_noisy",     "label": "Max |VRP| (skip noisy zone)","type": "float", "default": 999.0,"min": 5.0,  "max": 999.0,"step": 5.0},
            # ── XGBoost ──────────────────────────────────────────────────────
            {"key": "n_estimators",      "label": "XGB trees",          "type": "int",   "default": 300,   "min": 50,   "max": 1000},
            {"key": "max_depth",         "label": "XGB max depth",      "type": "int",   "default": 4,     "min": 2,    "max": 8},
            {"key": "oos_fraction",      "label": "OOS holdout",        "type": "float", "default": 0.20,  "min": 0.10, "max": 0.40, "step": 0.05},
        ]

    # ═════════════════════════════════════════════════════════════════════════
    # Feature engineering
    # ═════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _atm_price(chain_df: pd.DataFrame, expiry: str, spot: float) -> Optional[float]:
        """ATM mid/close price for a given expiry. Uses mid if available, else last price."""
        exp = chain_df[chain_df["expiration"] == str(expiry)]
        if exp.empty:
            return None
        strikes = exp["strike"].dropna().unique()
        if len(strikes) == 0:
            return None
        atm_k = strikes[np.abs(strikes - spot).argmin()]
        rows  = exp[exp["strike"] == atm_k]
        # Prefer call side for consistency; fall back to put
        calls = rows[rows["type"].str.lower().str.startswith("c")] if "type" in rows.columns else rows
        src   = calls if not calls.empty else rows
        # mid > last > (bid+ask)/2
        for col in ["mid", "last"]:
            if col in src.columns:
                v = pd.to_numeric(src[col], errors="coerce").dropna()
                if len(v) > 0 and float(v.iloc[0]) > 0:
                    return float(v.iloc[0])
        if "bid" in src.columns and "ask" in src.columns:
            b = pd.to_numeric(src["bid"], errors="coerce").iloc[0]
            a = pd.to_numeric(src["ask"], errors="coerce").iloc[0]
            if pd.notna(b) and pd.notna(a) and (b + a) > 0:
                return float((b + a) / 2)
        return None

    @staticmethod
    def _atm_iv(chain_df: pd.DataFrame, expiry: str, spot: float) -> Optional[float]:
        """ATM IV for a given expiry: average of nearest call and put IV at the ATM strike."""
        exp = chain_df[chain_df["expiration"] == str(expiry)]
        if exp.empty or "iv" not in exp.columns:
            return None
        strikes = exp["strike"].dropna().unique()
        if len(strikes) == 0:
            return None
        atm_k = strikes[np.abs(strikes - spot).argmin()]
        rows = exp[exp["strike"] == atm_k]
        ivs = rows["iv"].dropna().values
        if len(ivs) == 0:
            return None
        return float(np.nanmean(ivs)) * 100  # return as %

    @staticmethod
    def _ivr(current_iv: float, iv_series: pd.Series) -> float:
        """IV Rank: position of current_iv within the 52-week (rolling 252-day) range."""
        if iv_series.empty or len(iv_series) < 2:
            return 0.5
        lo = iv_series.min()
        hi = iv_series.max()
        if hi == lo:
            return 0.5
        return float(np.clip((current_iv - lo) / (hi - lo), 0, 1))

    def _build_feature_row(
        self,
        date: datetime.date,
        spot: float,
        chain_df: pd.DataFrame,
        price_df: pd.DataFrame,
        vix_series: pd.Series,
        front_iv_history: pd.Series,
        back_iv_history: pd.Series,
        news_df: Optional[pd.DataFrame] = None,
        spy_price_df: Optional[pd.DataFrame] = None,
    ) -> Optional[dict]:
        """
        Compute one feature row for a given date. Returns None if data is insufficient.
        chain_df must be filtered to date already (or contain date column).
        """
        # ── Identify front and back expiries from chain ────────────────────
        today = pd.Timestamp(date)
        if "expiration" not in chain_df.columns:
            return None

        chain_today = chain_df.copy()
        # Cast numeric columns — SQL Server returns DECIMAL as decimal.Decimal
        for _col in ["strike", "iv", "delta", "gamma", "theta", "vega",
                     "bid", "ask", "mid", "open_interest", "volume"]:
            if _col in chain_today.columns:
                chain_today[_col] = pd.to_numeric(chain_today[_col], errors="coerce")
        # Normalise expiration to YYYY-MM-DD string so all comparisons are consistent
        chain_today["expiration"] = pd.to_datetime(chain_today["expiration"]).dt.strftime("%Y-%m-%d")
        # Compute DTE from normalised expiration
        chain_today["dte"] = (pd.to_datetime(chain_today["expiration"]) - today).dt.days
        # Normalise contract type column (DB returns contract_type, live returns type)
        if "contract_type" in chain_today.columns and "type" not in chain_today.columns:
            chain_today = chain_today.rename(columns={"contract_type": "type"})
        chain_today = chain_today[chain_today["dte"] > 0]
        if chain_today.empty:
            return None

        # Build a DTE lookup: expiry_str → dte (take first row per expiry)
        _dte_map = chain_today.groupby("expiration")["dte"].first().to_dict()

        # Front: nearest expiry with DTE in [front_dte_min, front_dte_max]
        front_candidates = [
            e for e, d in _dte_map.items()
            if self.front_dte_min <= d <= self.front_dte_max
        ]
        if not front_candidates:
            # relax — take nearest expiry with DTE >= front_dte_min
            front_candidates = [e for e, d in _dte_map.items() if d >= self.front_dte_min]
        if not front_candidates:
            return None
        front_exp = sorted(front_candidates, key=lambda e: _dte_map[e])[0]

        # Back: next expiry after front, closest to back_dte_target
        front_dte_val = _dte_map[front_exp]
        back_candidates = [e for e, d in _dte_map.items() if d > front_dte_val + 5]
        if not back_candidates:
            return None
        back_exp = sorted(back_candidates, key=lambda e: abs(_dte_map[e] - self.back_dte_target))[0]

        front_iv = self._atm_iv(chain_today, front_exp, spot)
        back_iv  = self._atm_iv(chain_today, back_exp,  spot)
        if front_iv is None or back_iv is None:
            return None

        # ── Group 1 — IV term structure ────────────────────────────────────
        term_slope = back_iv - front_iv
        front_ivr  = self._ivr(front_iv, front_iv_history)
        back_ivr   = self._ivr(back_iv,  back_iv_history)
        ivr_spread = front_ivr - back_ivr

        # ── Group 2 — Variance risk premium ───────────────────────────────
        if len(price_df) < 22:
            return None
        log_rets   = np.log(price_df["close"] / price_df["close"].shift(1)).dropna()
        rvol_20d   = float(log_rets.iloc[-20:].std() * np.sqrt(252) * 100)
        vrp        = front_iv - rvol_20d

        # VRP z-score over rolling 90 days
        if len(price_df) >= 90:
            rvol_series = log_rets.rolling(20).std() * np.sqrt(252) * 100
            vrp_series  = front_iv_history.iloc[-90:] - rvol_series.iloc[-90:]
            vrp_z = float((vrp - vrp_series.mean()) / vrp_series.std()) if vrp_series.std() > 0 else 0.0
        else:
            vrp_z = 0.0

        # ── Group 3 — Market context ───────────────────────────────────────
        vix_val = float(vix_series.iloc[-1]) if not vix_series.empty else 20.0

        # Put/Call ratio
        if "type" in chain_today.columns and "open_interest" in chain_today.columns:
            calls_oi = chain_today[chain_today["type"] == "call"]["open_interest"].fillna(0).sum()
            puts_oi  = chain_today[chain_today["type"] == "put"]["open_interest"].fillna(0).sum()
            pc_ratio = float(puts_oi / calls_oi) if calls_oi > 0 else 1.0
        else:
            pc_ratio = 1.0

        # IV volume spike: today's stock volume vs 20-day average (proxy for options activity)
        iv_vol_spike = 1.0
        if len(price_df) >= 5 and "volume" in price_df.columns:
            try:
                _vol_series = pd.to_numeric(price_df["volume"], errors="coerce").dropna()
                if len(_vol_series) >= 2:
                    _avg_vol = float(_vol_series.iloc[-min(20, len(_vol_series)):-1].mean())
                    _today_vol = float(_vol_series.iloc[-1])
                    if _avg_vol > 0:
                        iv_vol_spike = _today_vol / _avg_vol
            except Exception:
                iv_vol_spike = 1.0

        # Ticker / broad-market-benchmark correlation (benchmark supplied via spy_price_df)
        if spy_price_df is not None and len(price_df) >= 20:
            try:
                ticker_ret = price_df["close"].pct_change().iloc[-20:].reset_index(drop=True)
                mkt_ret    = spy_price_df["close"].pct_change().iloc[-20:].reset_index(drop=True)
                if len(ticker_ret) == len(mkt_ret) and len(ticker_ret) > 2:
                    corr = float(ticker_ret.corr(mkt_ret))
                else:
                    corr = 0.5
            except Exception:
                corr = 0.5
        else:
            corr = 0.5

        # ── Group 4 — News sentiment ───────────────────────────────────────
        news_sent  = 0.0
        macro_sent = 0.0
        sent_vel   = 0.0
        if news_df is not None and not news_df.empty:
            if "sentiment" in news_df.columns:
                recent = news_df[news_df.index <= pd.Timestamp(date)].tail(10)
                if not recent.empty:
                    news_sent  = float(recent["sentiment"].mean())
                    s3  = float(recent.tail(3)["sentiment"].mean())
                    s10 = float(recent.tail(10)["sentiment"].mean())
                    sent_vel = s3 - s10
            if "macro_sentiment" in news_df.columns:
                macro_recent = news_df[news_df.index <= pd.Timestamp(date)].tail(10)
                if not macro_recent.empty:
                    macro_sent = float(macro_recent["macro_sentiment"].mean())

        return {
            "date":               date,
            "spot":               spot,
            "front_exp":          front_exp,
            "back_exp":           back_exp,
            "front_iv":           front_iv,
            "back_iv":            back_iv,
            "term_slope":         term_slope,
            "front_ivr":          front_ivr,
            "back_ivr":           back_ivr,
            "ivr_spread":         ivr_spread,
            "realized_vol_20d":   rvol_20d,
            "vrp":                vrp,
            "vrp_zscore":         vrp_z,
            "vix":                vix_val,
            "pc_ratio":           pc_ratio,
            "iv_vol_spike":        round(iv_vol_spike, 4),
            "ticker_mkt_corr_20d": corr,
            "news_sentiment":     news_sent,
            "macro_sentiment":    macro_sent,
            "sentiment_velocity": sent_vel,
        }

    # ═════════════════════════════════════════════════════════════════════════
    # Label construction
    # ═════════════════════════════════════════════════════════════════════════

    def _build_labels(self, feature_df: pd.DataFrame) -> pd.Series:
        """
        5-day forward front_iv *relative* change bucketed into COMPRESS / NEUTRAL / EXPAND.
        Uses relative (%) change to normalise across tickers with different IV regimes —
        a 3-vol-point swing at IV=25 (AAPL, 12% relative) is very different from
        the same swing at IV=80 (HOOD, 3.7% relative).
        """
        front_iv  = feature_df["front_iv"].values.astype(float)
        n         = len(front_iv)
        labels    = np.full(n, NEUTRAL, dtype=int)

        # Rolling σ of 5-day *relative* IV changes (pct_change over horizon)
        iv_series    = pd.Series(front_iv)
        rel_changes  = iv_series.pct_change(self.label_horizon)   # (IV[t] - IV[t-h]) / IV[t-h]
        sigma_roll   = rel_changes.rolling(90, min_periods=20).std()

        for i in range(n - self.label_horizon):
            iv_now = front_iv[i]
            if iv_now <= 0:
                continue
            fwd_rel = (front_iv[i + self.label_horizon] - iv_now) / iv_now
            sigma   = float(sigma_roll.iloc[i]) if not np.isnan(sigma_roll.iloc[i]) else 0.05
            thr     = self.label_sigma_mult * sigma
            if fwd_rel < -thr:
                labels[i] = COMPRESS
            elif fwd_rel > thr:
                labels[i] = EXPAND

        # Last label_horizon rows have no forward data — mask them
        labels[-self.label_horizon:] = -1
        return pd.Series(labels, index=feature_df.index, name="label")

    # ═════════════════════════════════════════════════════════════════════════
    # XGBoost classifier
    # ═════════════════════════════════════════════════════════════════════════

    def _get_classifier(self):
        """Return an XGBoost classifier, fall back to GradientBoosting if not installed."""
        try:
            import xgboost as xgb
            return xgb.XGBClassifier(
                n_estimators     = self.n_estimators,
                max_depth        = self.max_depth,
                learning_rate    = self.learning_rate,
                subsample        = self.subsample,
                colsample_bytree = self.colsample_bytree,
                use_label_encoder= False,
                eval_metric      = "mlogloss",
                verbosity        = 0,
                n_jobs           = -1,
            )
        except ImportError:
            logger.warning("xgboost not installed — falling back to sklearn GradientBoostingClassifier")
            from sklearn.ensemble import GradientBoostingClassifier
            # One-vs-rest for 3 classes
            from sklearn.multiclass import OneVsRestClassifier
            return OneVsRestClassifier(GradientBoostingClassifier(
                n_estimators = self.n_estimators,
                max_depth    = self.max_depth,
                learning_rate= self.learning_rate,
                subsample    = self.subsample,
            ))

    def _train_classifier(self, X: np.ndarray, y: np.ndarray):
        """Fit classifier with class-weight balancing, early stopping, and probability calibration."""
        from sklearn.utils.class_weight import compute_class_weight
        from sklearn.model_selection import train_test_split

        classes = np.array([COMPRESS, NEUTRAL, EXPAND])
        weights = compute_class_weight("balanced", classes=classes, y=y)
        weight_map    = {c: w for c, w in zip(classes, weights)}
        sample_weights = np.array([weight_map.get(yi, 1.0) for yi in y])

        clf = self._get_classifier()

        # Hold 15% as internal validation for early stopping (time-ordered, no shuffle)
        if len(X) > 80:
            split = max(1, int(len(X) * 0.85))
            X_tr, X_val   = X[:split], X[split:]
            y_tr, y_val   = y[:split], y[split:]
            sw_tr         = sample_weights[:split]

            try:
                # XGBoost native early stopping
                clf.set_params(early_stopping_rounds=30, eval_metric="mlogloss")
                clf.fit(X_tr, y_tr, sample_weight=sw_tr,
                        eval_set=[(X_val, y_val)], verbose=False)
            except (TypeError, ValueError, AttributeError):
                try:
                    clf.fit(X_tr, y_tr, sample_weight=sw_tr)
                except (TypeError, ValueError):
                    clf.fit(X_tr, y_tr)

            # Isotonic calibration on the held-out validation set
            try:
                from sklearn.calibration import CalibratedClassifierCV
                calibrated = CalibratedClassifierCV(clf, method="isotonic", cv="prefit")
                calibrated.fit(X_val, y_val)
                return calibrated
            except Exception:
                return clf
        else:
            try:
                clf.fit(X, y, sample_weight=sample_weights)
            except (TypeError, ValueError):
                clf.fit(X, y)
            return clf

    # ═════════════════════════════════════════════════════════════════════════
    # Train
    # ═════════════════════════════════════════════════════════════════════════

    def train(
        self,
        feature_df: pd.DataFrame,
        progress_callback=None,
    ) -> dict:
        """
        Train the XGBoost classifier using walk-forward expanding-window CV.
        The last oos_fraction of data is held out as the OOS test set.

        Parameters
        ----------
        feature_df : DataFrame
            Must contain all FEATURE_COLS columns plus be time-sorted.
            Typically built by _build_feature_row() for each historical date.
        progress_callback : callable(float, str), optional
            Called with (fraction_done, message) for UI progress bars.

        Returns
        -------
        dict with keys: n_train, n_oos, oos_accuracy, oos_report, feature_importances
        """
        labels = self._build_labels(feature_df)
        valid  = labels[labels >= 0].index
        X_all  = feature_df.loc[valid, self.FEATURE_COLS].values.astype(float)
        y_all  = labels.loc[valid].values.astype(int)

        n        = len(X_all)
        n_oos    = max(1, int(n * self.oos_fraction))
        n_train  = n - n_oos

        X_train, y_train = X_all[:n_train], y_all[:n_train]
        X_oos,   y_oos   = X_all[n_train:], y_all[n_train:]

        if progress_callback:
            progress_callback(0.1, f"Training on {n_train} samples…")

        # ── Walk-forward expanding CV (diagnostics only, final model uses full train) ──
        fold_size   = max(20, n_train // 10)
        oos_preds_cv = []
        oos_true_cv  = []
        init_train   = max(60, fold_size * 2)

        fold_idx = 0
        total_folds = max(1, (n_train - init_train) // fold_size)
        for start in range(init_train, n_train - fold_size, fold_size):
            X_f, y_f = X_all[:start], y_all[:start]
            X_v, y_v = X_all[start:start + fold_size], y_all[start:start + fold_size]
            if len(np.unique(y_f)) < 2:
                continue
            clf_f = self._train_classifier(X_f, y_f)
            oos_preds_cv.extend(clf_f.predict(X_v).tolist())
            oos_true_cv.extend(y_v.tolist())
            fold_idx += 1
            if progress_callback:
                progress_callback(0.1 + 0.5 * (fold_idx / total_folds),
                                  f"Walk-forward fold {fold_idx}/{total_folds}…")

        # ── Final model: fit on all training data ──────────────────────────
        if progress_callback:
            progress_callback(0.65, "Fitting final model on full training set…")

        self._model = self._train_classifier(X_train, y_train)

        # ── OOS evaluation ─────────────────────────────────────────────────
        from sklearn.metrics import accuracy_score, classification_report
        if progress_callback:
            progress_callback(0.80, "Evaluating on holdout…")

        oos_pred = self._model.predict(X_oos)
        oos_acc  = float(accuracy_score(y_oos, oos_pred))
        oos_rep  = classification_report(
            y_oos, oos_pred,
            target_names=["COMPRESS", "NEUTRAL", "EXPAND"],
            output_dict=True, zero_division=0,
        )

        # ── Feature importances ────────────────────────────────────────────
        feat_imp = {}
        try:
            fi = self._model.feature_importances_
            feat_imp = dict(zip(self.FEATURE_COLS, fi.tolist()))
        except AttributeError:
            pass  # OvR wrapper doesn't expose importances directly

        # ── CV accuracy ────────────────────────────────────────────────────
        cv_acc = None
        if oos_preds_cv:
            cv_acc = float(accuracy_score(oos_true_cv, oos_preds_cv))

        self._model_meta = {
            "n_train":             n_train,
            "n_oos":               n_oos,
            "oos_accuracy":        oos_acc,
            "cv_accuracy":         cv_acc,
            "oos_report":          oos_rep,
            "feature_importances": feat_imp,
            "trained_at":          datetime.datetime.now().isoformat(),
            "label_horizon":       self.label_horizon,
            "label_sigma_mult":    self.label_sigma_mult,
        }

        if progress_callback:
            progress_callback(1.0, f"Done. OOS accuracy: {oos_acc:.1%}")

        return self._model_meta

    def save_model(self, ticker: str = "default") -> str:
        path = _MODEL_DIR / f"vol_calendar_{ticker}.pkl"
        with open(path, "wb") as f:
            pickle.dump({"model": self._model, "meta": self._model_meta}, f)
        return str(path)

    def load_model(self, ticker: str = "default") -> bool:
        path = _MODEL_DIR / f"vol_calendar_{ticker}.pkl"
        if not path.exists():
            return False
        with open(path, "rb") as f:
            data = pickle.load(f)
        self._model      = data["model"]
        self._model_meta = data.get("meta", {})
        return True

    # ═════════════════════════════════════════════════════════════════════════
    # Predict (live signal)
    # ═════════════════════════════════════════════════════════════════════════

    def predict_regime(self, feature_row: dict) -> dict:
        """
        Given a feature dict (from _build_feature_row), return:
          { signal: 'COMPRESS'|'NEUTRAL'|'EXPAND',
            label:  int,
            confidence: float,
            probabilities: {COMPRESS: float, NEUTRAL: float, EXPAND: float},
            trade_type: 'credit_calendar'|'debit_calendar'|None,
            shap_values: dict (if shap installed),
          }
        """
        if self._model is None:
            return {"signal": "NEUTRAL", "label": NEUTRAL, "confidence": 0.0,
                    "probabilities": {}, "trade_type": None}

        X = np.array([[feature_row.get(c, 0.0) for c in self.FEATURE_COLS]], dtype=float)
        pred   = int(self._model.predict(X)[0])
        try:
            proba  = self._model.predict_proba(X)[0]
            conf   = float(proba[pred])
            prob_d = {LABEL_NAMES[i]: round(float(proba[i]), 4) for i in range(3)}
        except Exception:
            conf   = 1.0
            prob_d = {}

        signal     = LABEL_NAMES[pred]
        trade_type = None
        term_slope = feature_row.get("term_slope", -999)
        front_ivr  = feature_row.get("front_ivr", 0)
        vrp        = feature_row.get("vrp", 0)
        # Quality gate: flat term structure and noisy VRP zones produce wrong signals
        quality_ok = (
            self.min_term_slope <= term_slope <= self.max_term_slope
            and front_ivr >= self.min_ivr_quality
            and abs(vrp) <= self.max_vrp_noisy
        )
        if conf >= self.confidence_min and quality_ok:
            if pred == COMPRESS and front_ivr >= self.min_ivr_compress:
                trade_type = "credit_calendar"
            elif pred == EXPAND and front_ivr <= self.max_ivr_expand:
                trade_type = "debit_calendar"

        # SHAP values (optional, best-effort)
        shap_vals = {}
        try:
            import shap
            explainer  = shap.TreeExplainer(self._model)
            sv         = explainer.shap_values(X)
            # sv shape: (n_classes, n_samples, n_features) for multiclass
            if isinstance(sv, list):
                sv_pred = sv[pred][0]
            else:
                sv_pred = sv[0]
            shap_vals = {c: round(float(v), 6) for c, v in zip(self.FEATURE_COLS, sv_pred)}
        except Exception:
            pass

        return {
            "signal":        signal,
            "label":         pred,
            "confidence":    conf,
            "probabilities": prob_d,
            "trade_type":    trade_type,
            "shap_values":   shap_vals,
            "front_exp":     feature_row.get("front_exp"),
            "back_exp":      feature_row.get("back_exp"),
            "front_iv":      feature_row.get("front_iv"),
            "back_iv":       feature_row.get("back_iv"),
            "term_slope":    feature_row.get("term_slope"),
            "vrp":           feature_row.get("vrp"),
            "front_ivr":     feature_row.get("front_ivr"),
        }

    def generate_signal(self, market_snapshot: dict) -> SignalResult:
        """BaseStrategy interface — wraps predict_regime for compatibility."""
        result = self.predict_regime(market_snapshot)
        label  = result["label"]
        conf   = result["confidence"]
        if label == EXPAND and result["trade_type"] == "debit_calendar":
            signal = "BUY"
        elif label == COMPRESS and result["trade_type"] == "credit_calendar":
            signal = "SELL"
        else:
            signal = "HOLD"
        return SignalResult(
            strategy_name     = self.name,
            signal            = signal,
            confidence        = conf,
            position_size_pct = self.position_size_pct * conf if signal != "HOLD" else 0.0,
        )

    # ═════════════════════════════════════════════════════════════════════════
    # Backtest
    # ═════════════════════════════════════════════════════════════════════════

    def backtest(
        self,
        price_data:       pd.DataFrame,
        ticker:           str = "UNKNOWN",
        chains:           Optional[dict] = None,    # date → options chain DataFrame
        vix_data:         Optional[pd.Series] = None,
        news_data:        Optional[pd.DataFrame] = None,
        spy_data:         Optional[pd.DataFrame] = None,
        starting_capital: float = 100_000.0,
        progress_callback = None,
        **kwargs,
    ) -> BacktestResult:
        """
        Full walk-forward backtest.

        1. Build feature matrix from historical options chains + price data.
        2. Train model on first (1 − oos_fraction) of data.
        3. Simulate trades on OOS period only — no lookahead.
        4. Each trade: ATM calendar at signal date, marked-to-market at
           min(hold_days, front expiry − 5 DTE).

        Parameters
        ----------
        price_data : DataFrame with columns [open, high, low, close, volume], DatetimeIndex
        chains     : dict mapping date → options chain DataFrame (from Polygon)
        vix_data   : Series of VIX closes, DatetimeIndex
        news_data  : DataFrame with sentiment columns, DatetimeIndex
        spy_data   : DataFrame with SPY OHLCV for correlation feature
        """
        if chains is None or len(chains) == 0:
            return BacktestResult(
                strategy_name = self.name,
                equity_curve  = pd.Series(dtype=float),
                daily_returns = pd.Series(dtype=float),
                trades        = pd.DataFrame(),
                metrics       = {"error": "No options chain data provided"},
            )

        price_data = price_data.sort_index()
        dates      = sorted(chains.keys())
        if len(dates) < 60:
            return BacktestResult(
                strategy_name = self.name,
                equity_curve  = pd.Series(dtype=float),
                daily_returns = pd.Series(dtype=float),
                trades        = pd.DataFrame(),
                metrics       = {"error": "Insufficient chain history (need ≥ 60 dates)"},
            )

        if vix_data is None:
            vix_data = pd.Series(20.0, index=price_data.index)

        # ── Step 1: Build full feature matrix ─────────────────────────────
        rows = []
        front_iv_hist: list[float] = []
        back_iv_hist:  list[float] = []

        for i, d in enumerate(dates):
            chain_d = chains[d]
            if d not in price_data.index and pd.Timestamp(d) not in price_data.index:
                continue
            try:
                ts    = pd.Timestamp(d)
                spot  = float(price_data.loc[ts, "close"] if ts in price_data.index
                              else price_data.iloc[price_data.index.searchsorted(ts) - 1]["close"])
                px_to = price_data.loc[:ts].tail(120)
                vix_s = vix_data.loc[:ts].tail(10) if ts in vix_data.index or ts > vix_data.index.min() else pd.Series([20.0])
                spy_p = spy_data.loc[:ts].tail(25) if spy_data is not None else None

                fih = pd.Series(front_iv_hist[-252:]) if front_iv_hist else pd.Series([30.0])
                bih = pd.Series(back_iv_hist[-252:])  if back_iv_hist  else pd.Series([30.0])

                row = self._build_feature_row(
                    date             = d if isinstance(d, datetime.date) else d.date(),
                    spot             = spot,
                    chain_df         = chain_d,
                    price_df         = px_to,
                    vix_series       = vix_s,
                    front_iv_history = fih,
                    back_iv_history  = bih,
                    news_df          = news_data,
                    spy_price_df     = spy_p,
                )
                if row:
                    rows.append(row)
                    front_iv_hist.append(row["front_iv"])
                    back_iv_hist.append(row["back_iv"])
            except Exception as e:
                logger.debug(f"Feature build failed on {d}: {e}")
                continue

            if progress_callback and i % 20 == 0:
                progress_callback(0.1 + 0.4 * (i / len(dates)), f"Building features {i}/{len(dates)}…")

        if len(rows) < 60:
            return BacktestResult(
                strategy_name = self.name,
                equity_curve  = pd.Series(dtype=float),
                daily_returns = pd.Series(dtype=float),
                trades        = pd.DataFrame(),
                metrics       = {"error": f"Only {len(rows)} feature rows — need ≥ 60"},
            )

        feature_df = pd.DataFrame(rows).set_index("date")

        # ── Step 2: Train on first (1 − oos_fraction) ─────────────────────
        if progress_callback:
            progress_callback(0.52, "Training model…")

        train_result = self.train(feature_df, progress_callback=lambda f, m: (
            progress_callback(0.52 + 0.25 * f, m) if progress_callback else None
        ))

        # ── Step 3: Simulate OOS trades ────────────────────────────────────
        if progress_callback:
            progress_callback(0.78, "Simulating OOS trades…")

        n_total  = len(feature_df)
        n_train  = n_total - train_result["n_oos"]
        oos_df   = feature_df.iloc[n_train:].copy()

        capital     = float(starting_capital)
        equity_pts  = [{"date": feature_df.index[n_train - 1], "equity": capital}]
        trade_rows  = []
        open_trades = []
        hold_days   = 5  # default hold period

        # Build actual labels for OOS window for signal ledger
        _all_labels = self._build_labels(feature_df)
        signal_ledger = []  # every OOS prediction vs actual

        for i, (dt, feat_row) in enumerate(oos_df.iterrows()):
            # Close expired / hit-target trades
            still_open = []
            for ot in open_trades:
                days_held = (pd.Timestamp(dt) - pd.Timestamp(ot["entry_date"])).days
                _cd = chains.get(dt)
                chain_d = _cd if _cd is not None else chains.get(pd.Timestamp(dt))
                closed    = False

                time_exit = days_held >= hold_days
                if days_held >= 1:
                    spot_exit = float(
                        price_data.loc[pd.Timestamp(dt), "close"]
                        if pd.Timestamp(dt) in price_data.index else ot["spot"]
                    )
                    # Try real exit prices first
                    f_price_exit = self._atm_price(chain_d, ot["front_exp"], spot_exit) if chain_d is not None else None
                    b_price_exit = self._atm_price(chain_d, ot["back_exp"],  spot_exit) if chain_d is not None else None
                    f_iv_exit    = self._atm_iv(chain_d, ot["front_exp"], spot_exit)    if chain_d is not None else None
                    b_iv_exit    = self._atm_iv(chain_d, ot["back_exp"],  spot_exit)    if chain_d is not None else None

                    _slip = self.slippage_per_leg
                    _comm_exit = self.commission_per_leg * 2  # exit 2 legs

                    if f_price_exit is not None and b_price_exit is not None:
                        # Real P&L from actual option prices with exit slippage
                        if ot["trade_type"] == "debit_calendar":
                            # Unwind: sell back leg at bid, buy front leg at ask
                            exit_spread  = ((b_price_exit - _slip) - (f_price_exit + _slip)) * 100
                        else:
                            # Unwind: buy back leg at ask, sell front leg at bid
                            exit_spread  = ((b_price_exit + _slip) - (f_price_exit - _slip)) * 100
                        entry_spread = ot["cost"] / max(ot["contracts"], 1)
                        if ot["trade_type"] == "debit_calendar":
                            pnl = (exit_spread - entry_spread) * ot["contracts"] - _comm_exit * ot["contracts"]
                        else:
                            pnl = (entry_spread - exit_spread) * ot["contracts"] - _comm_exit * ot["contracts"]
                    elif f_iv_exit is not None and b_iv_exit is not None:
                        # BS fallback using stored IVs
                        from alan_trader.backtest.engine import bs_price as _bs_exit
                        _dte_f = max(1, ot.get("front_dte", 21) - days_held)
                        _dte_b = max(1, self.back_dte_target - days_held)
                        _f_bs = _bs_exit(spot_exit, ot["spot"], _dte_f / 252, 0.045, f_iv_exit / 100, "call")
                        _b_bs = _bs_exit(spot_exit, ot["spot"], _dte_b / 252, 0.045, b_iv_exit / 100, "call")
                        if ot["trade_type"] == "debit_calendar":
                            exit_spread = ((_b_bs - _slip) - (_f_bs + _slip)) * 100
                        else:
                            exit_spread = ((_b_bs + _slip) - (_f_bs - _slip)) * 100
                        entry_spread = ot["cost"] / max(ot["contracts"], 1)
                        if ot["trade_type"] == "debit_calendar":
                            pnl = (exit_spread - entry_spread) * ot["contracts"] - _comm_exit * ot["contracts"]
                        else:
                            pnl = (entry_spread - exit_spread) * ot["contracts"] - _comm_exit * ot["contracts"]
                    else:
                        # Theta decay estimate when no price data available
                        theta_decay = -ot["cost"] * (days_held / max(ot.get("front_dte", 21), 1))
                        pnl = theta_decay * 0.3

                    target_hit = pnl >= abs(ot["cost"]) * 0.5
                    if target_hit or time_exit:
                        capital += ot["cost"] + pnl
                        trade_rows.append({
                            "ticker":         ticker,
                            "entry_date":     ot["entry_date"],
                            "exit_date":      dt,
                            "trade_type":     ot["trade_type"],
                            "front_exp":      ot["front_exp"],
                            "back_exp":       ot["back_exp"],
                            "front_iv_entry": ot["front_iv"],
                            "back_iv_entry":  ot["back_iv"],
                            "front_iv_exit":  f_iv_exit,
                            "back_iv_exit":   b_iv_exit,
                            "vrp_entry":      ot["vrp"],
                            "confidence":     ot["confidence"],
                            "contracts":      ot["contracts"],
                            "cost":           ot["cost"],
                            "pnl":            round(pnl, 2),
                            "exit_reason":    "target" if target_hit else "time",
                        })
                        closed = True

                if not closed:
                    still_open.append(ot)
            open_trades = still_open

            # ── New trade signal ──────────────────────────────────────────
            row_d = feat_row.to_dict()
            row_d["date"]     = dt
            row_d["front_exp"] = feat_row.get("front_exp") or ""
            row_d["back_exp"]  = feat_row.get("back_exp")  or ""
            result = self.predict_regime(row_d)

            # ── Signal ledger: record every prediction with actual outcome ──
            actual_lbl = int(_all_labels.get(dt, -1))
            signal_ledger.append({
                "date":          dt,
                "predicted":     result["signal"],
                "confidence":    round(result["confidence"], 4),
                "actual":        LABEL_NAMES.get(actual_lbl, "UNKNOWN"),
                "correct":       actual_lbl == result["label"],
                "trade_taken":   bool(result["trade_type"] and len(open_trades) < 3),
                "trade_type":    result["trade_type"] or "—",
                "front_ivr":     round(float(feat_row.get("front_ivr", 0)), 3),
                "back_ivr":      round(float(feat_row.get("back_ivr", 0)), 3),
                "term_slope":    round(float(feat_row.get("term_slope", 0)), 4),
                "vrp":           round(float(feat_row.get("vrp", 0)), 3),
                "vrp_zscore":    round(float(feat_row.get("vrp_zscore", 0)), 3),
                "vix":           round(float(feat_row.get("vix", 0)), 2),
                "front_iv":        round(float(feat_row.get("front_iv", 0)), 2),
                "realized_vol_20d":round(float(feat_row.get("realized_vol_20d", 0)), 2),
                "news_sentiment":  round(float(feat_row.get("news_sentiment", 0)), 3),
            })

            if result["trade_type"] and len(open_trades) < 3:
                spot = float(
                    price_data.loc[pd.Timestamp(dt), "close"]
                    if pd.Timestamp(dt) in price_data.index else feat_row["spot"]
                )
                front_exp = result["front_exp"] or ""
                back_exp  = result["back_exp"]  or ""
                dte_f     = self.front_dte_min

                # Use real ATM option price from chain; fall back to vega proxy
                _cd_entry = chains.get(dt)
                if _cd_entry is None:
                    _cd_entry = chains.get(pd.Timestamp(dt))
                front_price = self._atm_price(_cd_entry, front_exp, spot) if _cd_entry is not None else None
                back_price  = self._atm_price(_cd_entry, back_exp,  spot) if _cd_entry is not None else None

                slip = self.slippage_per_leg
                if front_price is not None and back_price is not None:
                    # Apply bid-ask half-spread per leg directionally
                    if result["trade_type"] == "debit_calendar":
                        back_adj  = back_price  + slip   # buy back leg at ask
                        front_adj = front_price - slip   # sell front leg at bid
                    else:
                        back_adj  = back_price  - slip   # sell back leg at bid
                        front_adj = front_price + slip   # buy front leg at ask
                    cost = max(0.01, (back_adj - front_adj)) * 100
                    price_source = "market"
                else:
                    # BS fallback: price both legs using stored IV
                    from alan_trader.backtest.engine import bs_price as _bs_price
                    _iv_f = feat_row["front_iv"] / 100.0
                    _iv_b = feat_row["back_iv"]  / 100.0
                    _T_f  = max(dte_f, 1) / 252.0
                    _T_b  = max(self.back_dte_target, 1) / 252.0
                    front_price = _bs_price(spot, spot, _T_f, 0.045, _iv_f, "call")
                    back_price  = _bs_price(spot, spot, _T_b, 0.045, _iv_b, "call")
                    if result["trade_type"] == "debit_calendar":
                        cost = max(0.01, (back_price + slip) - (front_price - slip)) * 100
                    else:
                        cost = max(0.01, (front_price + slip) - (back_price - slip)) * 100
                    price_source = "bs_fallback"

                commission = self.commission_per_leg * 2  # 2 legs per calendar
                contracts = max(1, int(capital * self.position_size_pct / max(cost + commission, 1)))
                capital  -= (cost + commission) * contracts

                open_trades.append({
                    "entry_date":   dt,
                    "trade_type":   result["trade_type"],
                    "front_exp":    front_exp,
                    "back_exp":     back_exp,
                    "front_iv":     result["front_iv"]  or feat_row["front_iv"],
                    "back_iv":      result["back_iv"]   or feat_row["back_iv"],
                    "front_price":  front_price,
                    "back_price":   back_price,
                    "price_source": price_source,
                    "vrp":          feat_row["vrp"],
                    "spot":         spot,
                    "front_dte":    dte_f,
                    "cost":         cost * contracts,
                    "contracts":    contracts,
                    "confidence":   result["confidence"],
                })

            equity_pts.append({"date": dt, "equity": capital})

        # ── Force-close any still-open trades at end of OOS ───────────────
        last_dt = oos_df.index[-1] if len(oos_df) > 0 else feature_df.index[-1]
        _last_cd = chains.get(last_dt)
        last_chain = _last_cd if _last_cd is not None else chains.get(pd.Timestamp(last_dt))
        last_spot  = float(
            price_data.loc[pd.Timestamp(last_dt), "close"]
            if pd.Timestamp(last_dt) in price_data.index else 0
        )
        for ot in open_trades:
            days_held = (pd.Timestamp(last_dt) - pd.Timestamp(ot["entry_date"])).days
            pnl = 0.0
            if last_chain is not None and last_spot > 0:
                f_iv_exit = self._atm_iv(last_chain, ot["front_exp"], last_spot)
                b_iv_exit = self._atm_iv(last_chain, ot["back_exp"],  last_spot)
                if f_iv_exit is not None and b_iv_exit is not None:
                    entry_spread = ot["back_iv"] - ot["front_iv"]
                    exit_spread  = b_iv_exit - f_iv_exit
                    d_spread     = exit_spread - entry_spread
                    dte_approx   = max(1, ot.get("front_dte", 21) - days_held)
                    vega_proxy   = ot["spot"] * 0.01 * math.sqrt(dte_approx / 252) * 100
                    if ot["trade_type"] == "debit_calendar":
                        pnl = d_spread * vega_proxy * ot["contracts"]
                    else:
                        pnl = -d_spread * vega_proxy * ot["contracts"]
            capital += ot["cost"] + pnl
            trade_rows.append({
                "ticker":         ticker,
                "entry_date":     ot["entry_date"],
                "exit_date":      last_dt,
                "trade_type":     ot["trade_type"],
                "front_exp":      ot["front_exp"],
                "back_exp":       ot["back_exp"],
                "front_iv_entry": ot["front_iv"],
                "back_iv_entry":  ot["back_iv"],
                "front_iv_exit":  None,
                "back_iv_exit":   None,
                "vrp_entry":      ot["vrp"],
                "confidence":     ot["confidence"],
                "contracts":      ot["contracts"],
                "cost":           ot["cost"],
                "pnl":            round(pnl, 2),
                "exit_reason":    "expiry",
            })
        # Update final equity point after force-close
        if open_trades:
            equity_pts[-1] = {"date": last_dt, "equity": capital}

        # ── Step 4: Build results ──────────────────────────────────────────
        eq_df     = pd.DataFrame(equity_pts).set_index("date")["equity"]
        eq_df.index = pd.to_datetime(eq_df.index)
        daily_ret = eq_df.pct_change().dropna()
        trades_df = pd.DataFrame(trade_rows) if trade_rows else pd.DataFrame()
        metrics   = compute_all_metrics(eq_df, trades_df)
        metrics.update({
            "model_oos_accuracy": round(train_result.get("oos_accuracy", 0), 4),
            "model_cv_accuracy":  round(train_result.get("cv_accuracy") or 0, 4),
            "n_signals":          len(trade_rows),
            "n_compress":         sum(1 for t in trade_rows if t.get("trade_type") == "credit_calendar"),
            "n_expand":           sum(1 for t in trade_rows if t.get("trade_type") == "debit_calendar"),
            "feature_importances": train_result.get("feature_importances", {}),
            "label_distribution": {
                "COMPRESS": int(sum(1 for t in trade_rows if t.get("trade_type") == "credit_calendar")),
                "EXPAND":   int(sum(1 for t in trade_rows if t.get("trade_type") == "debit_calendar")),
            },
        })

        if progress_callback:
            progress_callback(1.0, "Backtest complete.")

        signal_ledger_df = pd.DataFrame(signal_ledger) if signal_ledger else pd.DataFrame()

        return BacktestResult(
            strategy_name = self.name,
            equity_curve  = eq_df,
            daily_returns = daily_ret,
            trades        = trades_df,
            metrics       = metrics,
            extra         = {"signal_ledger": signal_ledger_df},
        )
