"""
Short Squeeze Vol Expansion Strategy.

THESIS
------
When call OI surges on a high-short-interest stock while IV is still low,
dealers go short gamma on the call side. Forced delta hedging creates
directional momentum. A LightGBM classifier trained on call OI acceleration
+ volume spike signals identifies early squeeze setups.

TRADE STRUCTURE
---------------
Bull Call Spread (14–21 DTE):
  Long  ATM call (nearest $1/$5 strike at or below spot)
  Short call at ATM + spread_width (capped upside)

Entry conditions:
  P(squeeze_5d) ≥ signal_threshold/100
  AND  stock_call_vol_oi_ratio > 0.10
  AND  vix < max_vix

Exit conditions (first trigger wins):
  1. 80% of max gain (debit × 0 → spread_width × 100 per contract)
  2. 50% loss of debit paid
  3. 5 DTE remaining
  4. +8% stock move (directional exit)
  5. End of data
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

logger = logging.getLogger(__name__)

_MODEL_DIR = Path(__file__).parent.parent / "saved_models"
_MODEL_DIR.mkdir(exist_ok=True)

_RISK_FREE_RATE = 0.045
_WARMUP_BARS    = 120
_RETRAIN_EVERY  = 45


# ── Helpers ───────────────────────────────────────────────────────────────────

def _round_to_increment(strike: float, spot: float) -> float:
    """Round strike to nearest $1 if spot < $100, else $5."""
    inc = 1.0 if spot < 100.0 else 5.0
    return round(round(strike / inc) * inc, 2)


def _bs_delta(S: float, K: float, T: float, r: float, sigma: float,
              option_type: str) -> float:
    """Black-Scholes delta."""
    if T <= 0 or sigma <= 0 or S <= 0:
        return (1.0 if S > K else 0.0) if option_type == "call" else (-1.0 if S < K else 0.0)
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    return float(norm.cdf(d1)) if option_type == "call" else float(norm.cdf(d1) - 1.0)


# ─────────────────────────────────────────────────────────────────────────────
# Strategy class
# ─────────────────────────────────────────────────────────────────────────────

class ShortSqueezeVolExpansionStrategy(BaseStrategy):
    """
    AI-driven Short Squeeze Vol Expansion.

    LightGBM classifier detects early squeeze setups via call OI acceleration
    and volume spikes. Trades a bull call spread (14–21 DTE) to capture
    the forced-gamma-hedging directional move.
    """

    name                 = "short_squeeze_vol_expansion"
    display_name         = "Short Squeeze Vol Expansion"
    strategy_type        = StrategyType.AI_DRIVEN
    status               = StrategyStatus.ACTIVE
    description          = (
        "LightGBM classifier detects early short-squeeze setups via call OI surge + low IV. "
        "Trades a bull call spread (14–21 DTE) to capture forced-dealer-hedge momentum. "
        "Features: call OI concentration, vol/OI ratio, OTM call OI change, ATM IV, VIX context."
    )
    asset_class          = "equities_options"
    typical_holding_days = 14
    target_sharpe        = 1.4

    FEATURE_COLS = [
        "stock_call_oi_concentration",
        "stock_call_vol_oi_ratio",
        "stock_otm_call_oi_5d_change",
        "stock_5d_return",
        "stock_volume_ratio",
        "stock_atm_iv",
        "stock_iv_call_put_spread",
        "vix",
        "spy_5d_return",
    ]

    def __init__(
        self,
        signal_threshold:   float = 55.0,   # P(squeeze) % required
        spread_width:       int   = 3,      # $ width of call spread (in $1/$5 increments)
        dte_entry:          int   = 21,     # target DTE at entry
        position_size_pct:  float = 0.02,   # capital fraction per trade
        max_vix:            float = 28.0,   # maximum VIX to enter
        profit_target_pct:  float = 0.80,   # close at 80% of max gain
        stop_loss_pct:      float = 0.50,   # close at 50% loss of debit
        dte_time_stop:      int   = 5,      # exit at ≤ this DTE
        stock_move_exit:    float = 0.08,   # exit on +8% move
        commission_per_leg: float = 0.65,
        n_estimators:       int   = 80,
        max_depth:          int   = 4,
        min_child_samples:  int   = 15,
    ):
        self.signal_threshold   = signal_threshold
        self.spread_width       = spread_width
        self.dte_entry          = dte_entry
        self.position_size_pct  = position_size_pct
        self.max_vix            = max_vix
        self.profit_target_pct  = profit_target_pct
        self.stop_loss_pct      = stop_loss_pct
        self.dte_time_stop      = dte_time_stop
        self.stock_move_exit    = stock_move_exit
        self.commission_per_leg = commission_per_leg
        self.n_estimators       = n_estimators
        self.max_depth          = max_depth
        self.min_child_samples  = min_child_samples
        self._model             = None
        self._model_meta: dict  = {}

    # ── Params / UI ───────────────────────────────────────────────────────────

    def get_params(self) -> dict:
        return {
            "signal_threshold":   self.signal_threshold,
            "spread_width":       self.spread_width,
            "dte_entry":          self.dte_entry,
            "position_size_pct":  self.position_size_pct,
            "max_vix":            self.max_vix,
            "profit_target_pct":  self.profit_target_pct,
            "stop_loss_pct":      self.stop_loss_pct,
            "dte_time_stop":      self.dte_time_stop,
            "n_estimators":       self.n_estimators,
            "max_depth":          self.max_depth,
            "min_child_samples":  self.min_child_samples,
        }

    def get_backtest_ui_params(self) -> list:
        return [
            {
                "key": "signal_threshold", "label": "Signal threshold (%)",
                "type": "slider", "min": 45, "max": 70, "default": 55, "step": 1,
                "col": 0, "row": 0,
                "help": "Minimum model probability (%) to enter a bull call spread",
            },
            {
                "key": "spread_width", "label": "Spread width (strikes)",
                "type": "slider", "min": 1, "max": 5, "default": 3, "step": 1,
                "col": 1, "row": 0,
                "help": "$ width of call spread in $1 (spot<$100) or $5 (spot>=$100) increments",
            },
            {
                "key": "dte_entry", "label": "Target DTE at entry",
                "type": "slider", "min": 14, "max": 30, "default": 21, "step": 1,
                "col": 2, "row": 0,
                "help": "Target days-to-expiry when opening a new spread",
            },
            {
                "key": "max_vix", "label": "Max VIX to enter",
                "type": "slider", "min": 20, "max": 35, "default": 28, "step": 1,
                "col": 0, "row": 1,
                "help": "Squeezes are more likely in calm/moderate VIX environments",
            },
            {
                "key": "position_size_pct", "label": "Position size %",
                "type": "slider", "min": 0.01, "max": 0.05, "default": 0.02, "step": 0.01,
                "col": 1, "row": 1,
                "help": "Capital fraction allocated per trade",
            },
            {
                "key": "n_estimators", "label": "LGBM trees",
                "type": "slider", "min": 20, "max": 300, "default": 80, "step": 10,
                "col": 2, "row": 1,
                "help": "Number of LightGBM boosting rounds",
            },
        ]

    def is_trainable(self) -> bool:
        return True

    # ── Feature engineering ───────────────────────────────────────────────────

    @staticmethod
    def _compute_atm_iv(snap_df: pd.DataFrame, spot: float) -> Optional[float]:
        """ATM IV — uses call or put, whichever is available, within 5% of spot."""
        if snap_df is None or snap_df.empty:
            return None
        df = snap_df.copy()
        for col in ["StrikePrice", "ImpliedVol", "OpenInterest", "Delta", "DTE", "Volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        if "ImpliedVol" not in df.columns or "StrikePrice" not in df.columns:
            return None

        atm = df[(df["StrikePrice"] >= spot * 0.95) & (df["StrikePrice"] <= spot * 1.05)]
        if atm.empty:
            atm = df[(df["StrikePrice"] >= spot * 0.90) & (df["StrikePrice"] <= spot * 1.10)]
        if atm.empty:
            return None

        iv_vals = atm["ImpliedVol"].dropna()
        iv_vals = iv_vals[iv_vals > 0]
        if iv_vals.empty:
            return None
        iv = float(iv_vals.median())
        return iv * 100.0 if iv < 5.0 else iv

    def _build_feature_row(
        self,
        snap_df:         pd.DataFrame,
        price_slice:     pd.DataFrame,
        vix_series:      pd.Series,
        spy_price_slice: Optional[pd.DataFrame],
        ticker:          str,
    ) -> Optional[dict]:
        """Compute one feature row. Returns None if data is insufficient."""
        if snap_df is None or snap_df.empty:
            return None
        if price_slice is None or len(price_slice) < 22:
            return None

        spot = float(price_slice["close"].iloc[-1])
        if spot <= 0:
            return None

        df = snap_df.copy()
        for col in ["StrikePrice", "ImpliedVol", "OpenInterest", "Delta", "DTE", "Volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        if "OptionType" not in df.columns:
            return None

        calls = df[df["OptionType"].str.lower().str.startswith("c")].dropna(subset=["StrikePrice"])
        puts  = df[df["OptionType"].str.lower().str.startswith("p")].dropna(subset=["StrikePrice"])

        # 1. Call OI concentration (Herfindahl of top-3 call strikes / total call OI)
        call_oi_conc = 0.0
        if not calls.empty and "OpenInterest" in calls.columns:
            calls_oi = calls.dropna(subset=["OpenInterest"])
            total_call_oi = float(calls_oi["OpenInterest"].sum())
            if total_call_oi > 0:
                top3_oi = float(
                    calls_oi.groupby("StrikePrice")["OpenInterest"]
                    .sum()
                    .nlargest(3)
                    .sum()
                )
                call_oi_conc = top3_oi / total_call_oi

        # 2. Call vol/OI ratio
        call_vol_oi_ratio = 0.0
        if not calls.empty and "Volume" in calls.columns and "OpenInterest" in calls.columns:
            total_call_vol = float(calls["Volume"].fillna(0).sum())
            total_call_oi  = float(calls["OpenInterest"].fillna(0).sum())
            if total_call_oi > 0:
                call_vol_oi_ratio = total_call_vol / total_call_oi

        # 3. OTM call OI 5d change — placeholder (filled during matrix build from history)
        otm_call_oi_today = 0.0
        if not calls.empty and "OpenInterest" in calls.columns and "Delta" in calls.columns:
            otm_calls = calls[calls["Delta"].fillna(0).abs() < 0.4].dropna(subset=["OpenInterest"])
            otm_call_oi_today = float(otm_calls["OpenInterest"].sum())

        # 4. 5d return
        close_arr       = price_slice["close"].values
        stock_5d_return = float((close_arr[-1] - close_arr[-6]) / close_arr[-6]) if len(close_arr) >= 6 else 0.0

        # 5. Volume ratio
        vol_ratio = 1.0
        if len(price_slice) >= 2 and "volume" in price_slice.columns:
            vol_ser = pd.to_numeric(price_slice["volume"], errors="coerce").dropna()
            if len(vol_ser) >= 2:
                avg_vol = float(vol_ser.iloc[-min(20, len(vol_ser)):-1].mean())
                today_vol = float(vol_ser.iloc[-1])
                if avg_vol > 0:
                    vol_ratio = today_vol / avg_vol

        # 6. ATM IV
        atm_iv = self._compute_atm_iv(df, spot)
        if atm_iv is None:
            return None

        # 7. IV call-put spread
        iv_call_put_spread = 0.0
        atm_calls = calls[(calls["StrikePrice"] >= spot * 0.97) & (calls["StrikePrice"] <= spot * 1.03)]
        atm_puts  = puts[ (puts["StrikePrice"]  >= spot * 0.97) & (puts["StrikePrice"]  <= spot * 1.03)]
        if not atm_calls.empty and "ImpliedVol" in atm_calls.columns:
            c_iv = atm_calls["ImpliedVol"].dropna()
            c_iv = c_iv[c_iv > 0]
            if not c_iv.empty and not atm_puts.empty and "ImpliedVol" in atm_puts.columns:
                p_iv = atm_puts["ImpliedVol"].dropna()
                p_iv = p_iv[p_iv > 0]
                if not p_iv.empty:
                    c_iv_val = float(c_iv.median())
                    p_iv_val = float(p_iv.median())
                    # Normalise to percent if needed
                    if c_iv_val < 5.0:
                        c_iv_val *= 100.0
                    if p_iv_val < 5.0:
                        p_iv_val *= 100.0
                    iv_call_put_spread = c_iv_val - p_iv_val

        # 8. VIX
        vix_val = float(vix_series.iloc[-1]) if vix_series is not None and not vix_series.empty else 20.0

        # 9. SPY 5d return (only if ticker is not SPY)
        spy_5d_return = 0.0
        if spy_price_slice is not None and len(spy_price_slice) >= 6 and ticker.upper() != "SPY":
            spy_close = spy_price_slice["close"].values
            spy_5d_return = float((spy_close[-1] - spy_close[-6]) / spy_close[-6])

        return {
            "stock_call_oi_concentration": call_oi_conc,
            "stock_call_vol_oi_ratio":     call_vol_oi_ratio,
            "stock_otm_call_oi_5d_change": 0.0,          # filled in caller
            "stock_5d_return":             stock_5d_return,
            "stock_volume_ratio":          vol_ratio,
            "stock_atm_iv":                atm_iv,
            "stock_iv_call_put_spread":    iv_call_put_spread,
            "vix":                         vix_val,
            "spy_5d_return":               spy_5d_return,
            "_otm_call_oi_today":          otm_call_oi_today,  # helper for 5d change
        }

    def _build_feature_matrix(
        self,
        snap_by_date:    dict,
        price_data:      pd.DataFrame,
        vix_series:      pd.Series,
        spy_data:        Optional[pd.DataFrame],
        ticker:          str,
    ) -> pd.DataFrame:
        """Build full feature matrix filling OTM call OI 5d change."""
        rows            = []
        otm_oi_history: list[tuple] = []   # (ts, oi_value)
        dates_sorted    = sorted(snap_by_date.keys())

        for d in dates_sorted:
            ts = pd.Timestamp(d)
            if ts not in price_data.index:
                continue
            px_slice  = price_data.loc[:ts].tail(120)
            vix_s     = vix_series.loc[:ts].tail(30) if ts <= vix_series.index.max() else vix_series.tail(30)
            spy_slice = spy_data.loc[:ts].tail(30) if spy_data is not None and len(spy_data) > 0 else None

            row = self._build_feature_row(
                snap_df         = snap_by_date[d],
                price_slice     = px_slice,
                vix_series      = vix_s,
                spy_price_slice = spy_slice,
                ticker          = ticker,
            )
            if row is None:
                continue

            # OTM call OI 5d change
            oi_today = row.pop("_otm_call_oi_today")
            otm_oi_history.append((ts, oi_today))
            oi_5d_change = 0.0
            if len(otm_oi_history) >= 6:
                oi_5d_ago = otm_oi_history[-6][1]
                if oi_5d_ago > 0:
                    oi_5d_change = (oi_today - oi_5d_ago) / oi_5d_ago
            row["stock_otm_call_oi_5d_change"] = oi_5d_change
            row["date"] = ts
            rows.append(row)

        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows).set_index("date")

    # ── Labels ────────────────────────────────────────────────────────────────

    @staticmethod
    def _build_labels(price_data: pd.DataFrame, feat_index: pd.Index,
                      horizon: int = 5) -> pd.Series:
        """
        squeeze_5d = 1 if stock price moves ≥ +7% in next `horizon` bars.
        """
        labels = np.full(len(feat_index), 0, dtype=int)
        close  = price_data["close"]

        for i, dt in enumerate(feat_index):
            if dt not in close.index:
                labels[i] = -1
                continue
            idx_in_close = close.index.get_loc(dt)
            if isinstance(idx_in_close, slice):
                idx_in_close = idx_in_close.start
            fwd_idx = idx_in_close + horizon
            if fwd_idx >= len(close):
                labels[i] = -1
                continue
            price_now = float(close.iloc[idx_in_close])
            price_fwd = float(close.iloc[fwd_idx])
            if price_now > 0 and (price_fwd - price_now) / price_now >= 0.07:
                labels[i] = 1

        # Mask last horizon rows
        labels[-(horizon):] = -1
        return pd.Series(labels, index=feat_index, name="label")

    # ── LightGBM model ────────────────────────────────────────────────────────

    def _get_classifier(self):
        """Return LightGBM classifier, fall back to sklearn GBM if not available."""
        try:
            import lightgbm as lgb
            return lgb.LGBMClassifier(
                n_estimators      = self.n_estimators,
                max_depth         = self.max_depth,
                min_child_samples = self.min_child_samples,
                class_weight      = "balanced",
                verbosity         = -1,
                n_jobs            = -1,
            )
        except ImportError:
            logger.warning("lightgbm not installed — falling back to sklearn GradientBoostingClassifier")
            from sklearn.ensemble import GradientBoostingClassifier
            return GradientBoostingClassifier(
                n_estimators = self.n_estimators,
                max_depth    = self.max_depth,
            )

    def _train_model(self, X: np.ndarray, y: np.ndarray):
        """Fit classifier."""
        clf = self._get_classifier()
        try:
            clf.fit(X, y)
        except Exception as e:
            logger.debug(f"Classifier fit failed: {e}")
            from sklearn.ensemble import GradientBoostingClassifier
            clf = GradientBoostingClassifier(n_estimators=50, max_depth=3)
            clf.fit(X, y)
        return clf

    def _walk_forward_train(
        self,
        feature_df: pd.DataFrame,
        price_data: pd.DataFrame,
        horizon:    int = 5,
        progress_callback=None,
    ) -> dict:
        """
        Walk-forward training: 120-bar warm-up, retrain every 45 bars.
        Returns model meta.
        """
        labels = self._build_labels(price_data, feature_df.index, horizon)
        valid  = labels[labels >= 0].index
        X_all  = feature_df.loc[valid, self.FEATURE_COLS].values.astype(float)
        y_all  = labels.loc[valid].values.astype(int)
        n      = len(X_all)

        if n < _WARMUP_BARS:
            raise ValueError(
                f"Insufficient labelled samples: need ≥ {_WARMUP_BARS}, got {n}"
            )

        preds_oos: list[int] = []
        trues_oos: list[int] = []

        step        = 0
        total_steps = max(1, (n - _WARMUP_BARS) // _RETRAIN_EVERY)
        for start in range(_WARMUP_BARS, n, _RETRAIN_EVERY):
            X_tr, y_tr = X_all[:start], y_all[:start]
            if len(np.unique(y_tr)) < 2:
                continue
            mdl = self._train_model(X_tr, y_tr)
            end = min(start + _RETRAIN_EVERY, n)
            preds_oos.extend(mdl.predict(X_all[start:end]).tolist())
            trues_oos.extend(y_all[start:end].tolist())
            step += 1
            if progress_callback:
                progress_callback(0.1 + 0.6 * (step / total_steps),
                                  f"Walk-forward step {step}/{total_steps}…")

        if progress_callback:
            progress_callback(0.72, "Fitting final model…")
        self._model = self._train_model(X_all, y_all)

        cv_acc = None
        if preds_oos:
            from sklearn.metrics import accuracy_score
            cv_acc = float(accuracy_score(trues_oos, preds_oos))

        feat_imp = {}
        try:
            fi = self._model.feature_importances_
            feat_imp = {c: round(float(v), 6) for c, v in zip(self.FEATURE_COLS, fi)}
        except AttributeError:
            pass

        self._model_meta = {
            "n_samples":           n,
            "cv_accuracy":         cv_acc,
            "feature_importances": feat_imp,
            "warmup_bars":         _WARMUP_BARS,
            "retrain_every":       _RETRAIN_EVERY,
        }
        if progress_callback:
            progress_callback(1.0, f"Done. Walk-forward accuracy: {cv_acc:.1%}" if cv_acc else "Done.")
        return self._model_meta

    # ── Persistence ───────────────────────────────────────────────────────────

    def save_model(self, ticker: str = "default") -> str:
        path = _MODEL_DIR / f"squeeze_vol_{ticker}.pkl"
        with open(path, "wb") as f:
            pickle.dump({"model": self._model, "meta": self._model_meta}, f)
        return str(path)

    def load_model(self, ticker: str = "default") -> bool:
        path = _MODEL_DIR / f"squeeze_vol_{ticker}.pkl"
        if not path.exists():
            return False
        with open(path, "rb") as f:
            data = pickle.load(f)
        self._model      = data["model"]
        self._model_meta = data.get("meta", {})
        return True

    # ── Live signal ───────────────────────────────────────────────────────────

    def generate_signal(self, market_snapshot: dict) -> SignalResult:
        """
        Live signal from a market_snapshot dict with keys matching FEATURE_COLS.
        Returns BUY (bull call spread) when probability ≥ threshold and filters pass.
        """
        if self._model is None:
            return SignalResult(
                strategy_name=self.name, signal="HOLD",
                confidence=0.0, position_size_pct=0.0,
                metadata={"reason": "model not trained"},
            )

        vix              = market_snapshot.get("vix", 20.0)
        call_vol_oi_ratio = market_snapshot.get("stock_call_vol_oi_ratio", 0.0)

        if vix >= self.max_vix:
            return SignalResult(
                strategy_name=self.name, signal="HOLD",
                confidence=0.0, position_size_pct=0.0,
                metadata={"reason": f"VIX {vix:.1f} ≥ max_vix {self.max_vix}"},
            )

        if call_vol_oi_ratio <= 0.10:
            return SignalResult(
                strategy_name=self.name, signal="HOLD",
                confidence=0.0, position_size_pct=0.0,
                metadata={"reason": f"call vol/OI ratio {call_vol_oi_ratio:.3f} ≤ 0.10"},
            )

        X = np.array([[market_snapshot.get(c, 0.0) for c in self.FEATURE_COLS]], dtype=float)
        try:
            proba        = self._model.predict_proba(X)[0]
            prob_squeeze = float(proba[1]) if len(proba) > 1 else 0.0
        except Exception:
            prob_squeeze = 0.0

        threshold = self.signal_threshold / 100.0
        if prob_squeeze >= threshold:
            return SignalResult(
                strategy_name=self.name, signal="BUY",
                confidence=round(prob_squeeze, 4),
                position_size_pct=self.position_size_pct,
                metadata={
                    "prob_squeeze":       round(prob_squeeze, 4),
                    "spread_type":        "bull_call",
                    "call_vol_oi_ratio":  round(call_vol_oi_ratio, 4),
                    "vix":                vix,
                    "atm_iv":             market_snapshot.get("stock_atm_iv", 0.0),
                },
            )
        return SignalResult(
            strategy_name=self.name, signal="HOLD",
            confidence=round(prob_squeeze, 4), position_size_pct=0.0,
            metadata={"prob_squeeze": round(prob_squeeze, 4), "reason": "below threshold"},
        )

    # ── Backtest ──────────────────────────────────────────────────────────────

    def backtest(
        self,
        price_data:        pd.DataFrame,
        auxiliary_data:    dict,
        starting_capital:  float = 100_000,
        ticker:            str   = "UNKNOWN",
        signal_threshold:  Optional[float] = None,
        spread_width:      Optional[int]   = None,
        dte_entry:         Optional[int]   = None,
        position_size_pct: Optional[float] = None,
        max_vix:           Optional[float] = None,
        **kwargs,
    ) -> BacktestResult:
        """
        Walk-forward simulation with in-line model retraining.

        auxiliary_data must contain:
          "option_snapshots" : DataFrame with SnapshotDate, StrikePrice, OptionType,
                               ImpliedVol, OpenInterest, Delta, DTE, Volume columns
          "vix"              : DataFrame date-indexed with "close" column
        Optional:
          "spy_price"        : DataFrame with OHLCV for SPY (used for spy_5d_return feature)
        """
        # ── Resolve effective params ──────────────────────────────────────
        thresh_eff    = signal_threshold  if signal_threshold  is not None else self.signal_threshold
        width_eff     = spread_width      if spread_width      is not None else self.spread_width
        dte_eff       = dte_entry         if dte_entry         is not None else self.dte_entry
        pos_sz_eff    = position_size_pct if position_size_pct is not None else self.position_size_pct
        max_vix_eff   = max_vix           if max_vix           is not None else self.max_vix

        pt_eff       = self.profit_target_pct
        sl_pct       = self.stop_loss_pct
        dte_stop_eff = self.dte_time_stop
        move_exit    = self.stock_move_exit
        comm         = self.commission_per_leg
        r            = _RISK_FREE_RATE

        # ── Validate and align data ───────────────────────────────────────
        price_data = price_data.copy()
        price_data.index = pd.to_datetime(price_data.index)
        price_data = price_data.sort_index()

        snap_raw = auxiliary_data.get("option_snapshots")
        if snap_raw is None or (isinstance(snap_raw, pd.DataFrame) and snap_raw.empty):
            raise ValueError(
                "option_snapshots is empty. Go to Data Manager → Options and sync data for this ticker."
            )

        vix_df = auxiliary_data.get("vix", pd.DataFrame())
        if vix_df is None or (isinstance(vix_df, pd.DataFrame) and vix_df.empty):
            raise ValueError("No VIX data found. Sync VIX in Data Manager → Macro Bars.")

        vix_df = vix_df.copy()
        vix_df.index = pd.to_datetime(vix_df.index)
        vix_series = vix_df["close"].reindex(price_data.index).ffill().fillna(20.0)

        # SPY data (optional)
        spy_data = auxiliary_data.get("spy_price")
        if spy_data is not None and not spy_data.empty:
            spy_data = spy_data.copy()
            spy_data.index = pd.to_datetime(spy_data.index)
        else:
            spy_data = None

        # Group option_snapshots by date
        snap_df = snap_raw.copy()
        if "SnapshotDate" not in snap_df.columns:
            raise ValueError("option_snapshots must have a 'SnapshotDate' column.")
        snap_df["SnapshotDate"] = pd.to_datetime(snap_df["SnapshotDate"])
        snap_by_date = {ts: grp for ts, grp in snap_df.groupby("SnapshotDate")}

        # ── Build feature matrix ──────────────────────────────────────────
        feature_df = self._build_feature_matrix(
            snap_by_date = snap_by_date,
            price_data   = price_data,
            vix_series   = vix_series,
            spy_data     = spy_data,
            ticker       = ticker,
        )

        if feature_df.empty or len(feature_df) < _WARMUP_BARS + 10:
            return BacktestResult(
                strategy_name = self.name,
                equity_curve  = pd.Series([starting_capital], dtype=float),
                daily_returns = pd.Series(dtype=float),
                trades        = pd.DataFrame(),
                metrics       = {"error": f"Insufficient feature rows: {len(feature_df)} (need ≥ {_WARMUP_BARS + 10})"},
                params        = self.get_params(),
            )

        # ── Walk-forward simulation with rolling model retraining ─────────
        close          = price_data["close"]
        all_feat_dates = list(feature_df.index)
        n_feat         = len(all_feat_dates)

        capital        = float(starting_capital)
        equity_list:   list[float] = []
        open_trades:   list[dict]  = []
        closed_trades: list[dict]  = []
        current_model  = None

        for fi, dt in enumerate(all_feat_dates):
            feat_row   = feature_df.iloc[fi]
            spot_ser   = close.reindex([dt]).dropna()
            if spot_ser.empty:
                equity_list.append(capital)
                continue
            spot    = float(spot_ser.iloc[0])
            atm_iv  = float(feat_row["stock_atm_iv"])
            vix_val = float(feat_row["vix"])

            # ── Train / retrain model ─────────────────────────────────────
            if fi >= _WARMUP_BARS and (
                current_model is None or (fi - _WARMUP_BARS) % _RETRAIN_EVERY == 0
            ):
                labels_so_far = self._build_labels(price_data, feature_df.iloc[:fi + 1].index)
                valid_idx     = labels_so_far[labels_so_far >= 0].index
                if len(valid_idx) >= _WARMUP_BARS:
                    X_tr = feature_df.loc[valid_idx, self.FEATURE_COLS].values.astype(float)
                    y_tr = labels_so_far.loc[valid_idx].values.astype(int)
                    if len(np.unique(y_tr)) >= 2:
                        try:
                            current_model = self._train_model(X_tr, y_tr)
                        except Exception as e:
                            logger.debug(f"Model training failed at bar {fi}: {e}")

            # ── Exit open trades ──────────────────────────────────────────
            still_open: list[dict] = []
            for trade in open_trades:
                dte_rem = trade["expiry_idx"] - fi
                T_now   = max(dte_rem / 252.0, 1e-6)
                iv_dec  = max(atm_iv / 100.0, 0.01)

                # Current value of bull call spread
                long_val  = bs_price(spot, trade["long_K"],  T_now, r, iv_dec, "call")
                short_val = bs_price(spot, trade["short_K"], T_now, r, iv_dec, "call")
                spread_val = long_val - short_val  # current value of the debit spread

                # P&L = current value − debit paid
                pnl_per_spread = spread_val - trade["debit"]
                pnl_total      = pnl_per_spread * trade["contracts"] * 100

                # Max gain = (spread_width_dollars − debit) per spread
                max_gain_per_spread = trade["max_gain"]

                stock_move = (spot - trade["entry_spot"]) / trade["entry_spot"] if trade["entry_spot"] > 0 else 0.0

                exit_reason: Optional[str] = None
                if max_gain_per_spread > 0 and pnl_per_spread >= pt_eff * max_gain_per_spread:
                    exit_reason = "profit_target"
                elif pnl_per_spread <= -sl_pct * trade["debit"]:
                    exit_reason = "stop_loss"
                elif dte_rem <= dte_stop_eff:
                    exit_reason = "dte_stop"
                elif stock_move >= move_exit:
                    exit_reason = "stock_move_exit"
                elif fi == n_feat - 1:
                    exit_reason = "end_of_data"

                if exit_reason:
                    close_comm = 2 * comm * trade["contracts"]
                    net_pnl    = round(pnl_total - close_comm, 2)
                    capital   += net_pnl
                    closed_trades.append({
                        "entry_date":  trade["entry_date"].date() if hasattr(trade["entry_date"], "date") else trade["entry_date"],
                        "exit_date":   dt.date() if hasattr(dt, "date") else dt,
                        "spread_type": "bull_call",
                        "long_K":      round(trade["long_K"],  2),
                        "short_K":     round(trade["short_K"], 2),
                        "debit":       round(trade["debit"],   4),
                        "contracts":   trade["contracts"],
                        "pnl":         net_pnl,
                        "exit_reason": exit_reason,
                        "dte_held":    trade["dte_entry"] - dte_rem,
                    })
                else:
                    still_open.append(trade)
            open_trades = still_open

            # ── Entry check ───────────────────────────────────────────────
            can_enter = (
                fi >= _WARMUP_BARS
                and current_model is not None
                and vix_val < max_vix_eff
                and feat_row["stock_call_vol_oi_ratio"] > 0.10
                and spot > 0
                and (n_feat - fi) > dte_eff
            )

            if can_enter:
                X_live = np.array([[feat_row.get(c, 0.0) for c in self.FEATURE_COLS]], dtype=float)
                try:
                    proba        = current_model.predict_proba(X_live)[0]
                    prob_squeeze = float(proba[1]) if len(proba) > 1 else 0.0
                except Exception:
                    prob_squeeze = 0.0

                if prob_squeeze >= (thresh_eff / 100.0):
                    T_entry = dte_eff / 252.0
                    iv_dec  = max(atm_iv / 100.0, 0.01)
                    inc     = 1.0 if spot < 100.0 else 5.0

                    # Long ATM call: nearest $1/$5 at or below spot
                    long_K  = _round_to_increment(math.floor(spot / inc) * inc, spot)
                    short_K = long_K + width_eff * inc

                    long_prem  = bs_price(spot, long_K,  T_entry, r, iv_dec, "call")
                    short_prem = bs_price(spot, short_K, T_entry, r, iv_dec, "call")
                    debit      = max(long_prem - short_prem, 0.01)

                    spread_width_dollars = short_K - long_K
                    max_gain_per_spread  = spread_width_dollars - debit  # per share

                    if debit <= 0.01 or max_gain_per_spread <= 0:
                        equity_list.append(capital)
                        continue

                    # Size by debit risk (max loss = debit × contracts × 100)
                    contracts   = max(1, math.floor(capital * pos_sz_eff / (debit * 100)))
                    entry_comm  = 2 * comm * contracts
                    capital    -= debit * contracts * 100 + entry_comm

                    expiry_idx  = min(fi + dte_eff, n_feat - 1)
                    open_trades.append({
                        "entry_date":  dt,
                        "expiry_idx":  expiry_idx,
                        "dte_entry":   dte_eff,
                        "long_K":      long_K,
                        "short_K":     short_K,
                        "debit":       debit,
                        "max_gain":    max_gain_per_spread,
                        "contracts":   contracts,
                        "entry_spot":  spot,
                    })

            # ── Mark-to-market equity ─────────────────────────────────────
            mtm = 0.0
            iv_dec_mtm = max(atm_iv / 100.0, 0.01)
            for ot in open_trades:
                dte_rem  = ot["expiry_idx"] - fi
                T_mtm    = max(dte_rem / 252.0, 1e-6)
                lv       = bs_price(spot, ot["long_K"],  T_mtm, r, iv_dec_mtm, "call")
                sv       = bs_price(spot, ot["short_K"], T_mtm, r, iv_dec_mtm, "call")
                cur_val  = lv - sv
                mtm     += (cur_val - ot["debit"]) * ot["contracts"] * 100
            equity_list.append(capital + mtm)

        # ── Build results ─────────────────────────────────────────────────
        equity    = pd.Series(equity_list, index=all_feat_dates, dtype=float)
        daily_ret = equity.pct_change().dropna()
        bh_ret    = close.pct_change().reindex(equity.index).dropna()

        trades_df = (
            pd.DataFrame(closed_trades)
            if closed_trades
            else pd.DataFrame(columns=[
                "entry_date", "exit_date", "spread_type", "long_K", "short_K",
                "debit", "contracts", "pnl", "exit_reason", "dte_held",
            ])
        )

        metrics = compute_all_metrics(
            equity_curve       = equity,
            trades_df          = trades_df,
            benchmark_returns  = bh_ret,
        )

        self._model = current_model

        return BacktestResult(
            strategy_name = self.name,
            equity_curve  = equity,
            daily_returns = daily_ret,
            trades        = trades_df,
            metrics       = metrics,
            params        = {
                **self.get_params(),
                "signal_threshold": thresh_eff,
                "dte_entry":        dte_eff,
                "max_vix":          max_vix_eff,
                "ticker":           ticker,
            },
            extra = {
                "model_meta":         self._model_meta,
                "feature_df":         feature_df,
                "open_trades_at_end": len(open_trades),
            },
        )
