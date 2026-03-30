"""
OI Imbalance Put Fade Strategy.

THESIS
------
Retail investors systematically over-buy short-dated puts on high-IV stocks.
When put/call OI imbalance spikes, IV is elevated beyond fair value → sell a
bull put spread to harvest the excess put premium.

A logistic regression classifies when the imbalance is at an extreme that
historically mean-reverts.

TRADE STRUCTURE
---------------
Bull Put Spread (7–14 DTE):
  Sell put at 0.25 delta
  Buy  put spread_width strikes below short put

Entry conditions:
  P(iv_compress_5d) ≥ signal_threshold/100  AND  ATM put IV ≥ min_iv_floor

Exit conditions (first trigger wins):
  1. 50% of credit received (profit target)
  2. 2× credit as loss (stop loss)
  3. 5 DTE remaining (time stop)
  4. End of data
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

_MODEL_DIR = Path(__file__).parent.parent / "saved_models"
_MODEL_DIR.mkdir(exist_ok=True)

_RISK_FREE_RATE = 0.045
_WARMUP_BARS    = 150
_RETRAIN_EVERY  = 30


# ── Helpers ───────────────────────────────────────────────────────────────────

def _bs_delta(S: float, K: float, T: float, r: float, sigma: float,
              option_type: str) -> float:
    """Black-Scholes delta."""
    if T <= 0 or sigma <= 0 or S <= 0:
        return (1.0 if S > K else 0.0) if option_type == "call" else (-1.0 if S < K else 0.0)
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    return float(norm.cdf(d1)) if option_type == "call" else float(norm.cdf(d1) - 1.0)


def _find_strike_for_delta(S: float, T: float, r: float, sigma: float,
                           target_delta: float, option_type: str) -> float:
    """Find strike K such that |delta(K)| ≈ target_delta."""
    if T <= 0 or sigma <= 0:
        return S
    sign = 1.0 if option_type == "call" else -1.0

    def objective(K):
        return abs(_bs_delta(S, K, T, r, sigma, option_type)) - target_delta

    lo, hi = S * 0.50, S * 1.50
    try:
        K = brentq(objective, lo, hi, xtol=0.01, maxiter=50)
    except (ValueError, RuntimeError):
        K = S * np.exp(sign * sigma * np.sqrt(T))
    return max(float(K), 0.01)


def _round_to_increment(strike: float, spot: float) -> float:
    """Round strike to nearest $1 if spot < $100, else $5."""
    inc = 1.0 if spot < 100.0 else 5.0
    return round(round(strike / inc) * inc, 2)


# ─────────────────────────────────────────────────────────────────────────────
# Strategy class
# ─────────────────────────────────────────────────────────────────────────────

class OIImbalancePutFadeStrategy(BaseStrategy):
    """
    AI-driven OI Imbalance Put Fade.

    Logistic regression classifier identifies put/call OI extremes where
    ATM put IV is likely to compress within 5 days. Trades a bull put
    spread to harvest the excess put premium.
    """

    name                 = "oi_imbalance_put_fade"
    display_name         = "OI Imbalance Put Fade"
    strategy_type        = StrategyType.AI_DRIVEN
    status               = StrategyStatus.ACTIVE
    description          = (
        "Logistic regression detects retail put-buying extremes on high-IV stocks. "
        "Sells a bull put spread (7–14 DTE) when put/call OI imbalance spikes and "
        "IV is elevated. Exits at 50% profit, 2× loss, or 5 DTE stop."
    )
    asset_class          = "equities_options"
    typical_holding_days = 10
    target_sharpe        = 1.3

    FEATURE_COLS = [
        "stock_put_call_oi_ratio",
        "stock_atm_put_iv",
        "stock_iv_5d_zscore",
        "stock_20d_realized_vol",
        "stock_5d_return",
        "stock_oi_spike",
        "vix",
        "days_to_fomc",
    ]

    def __init__(
        self,
        min_iv_floor:       float = 40.0,   # minimum ATM put IV % to enter
        signal_threshold:   float = 62.0,   # P(compress) % required
        spread_width:       int   = 2,      # number of $1/$5 increments below short put
        dte_entry:          int   = 14,     # target DTE at entry
        position_size_pct:  float = 0.03,   # capital fraction per trade
        profit_target_pct:  float = 0.50,   # close at 50% of max credit
        stop_loss_mult:     float = 2.0,    # stop at 2× credit
        dte_time_stop:      int   = 5,      # exit at ≤ this DTE
        commission_per_leg: float = 0.65,
    ):
        self.min_iv_floor       = min_iv_floor
        self.signal_threshold   = signal_threshold
        self.spread_width       = spread_width
        self.dte_entry          = dte_entry
        self.position_size_pct  = position_size_pct
        self.profit_target_pct  = profit_target_pct
        self.stop_loss_mult     = stop_loss_mult
        self.dte_time_stop      = dte_time_stop
        self.commission_per_leg = commission_per_leg
        self._model             = None
        self._model_meta: dict  = {}

    # ── Params / UI ───────────────────────────────────────────────────────────

    def get_params(self) -> dict:
        return {
            "min_iv_floor":       self.min_iv_floor,
            "signal_threshold":   self.signal_threshold,
            "spread_width":       self.spread_width,
            "dte_entry":          self.dte_entry,
            "position_size_pct":  self.position_size_pct,
            "profit_target_pct":  self.profit_target_pct,
            "stop_loss_mult":     self.stop_loss_mult,
            "dte_time_stop":      self.dte_time_stop,
            "commission_per_leg": self.commission_per_leg,
        }

    def get_backtest_ui_params(self) -> list:
        return [
            {
                "key": "min_iv_floor", "label": "Min ATM Put IV (%)",
                "type": "slider", "min": 30, "max": 70, "default": 40, "step": 5,
                "col": 0, "row": 0,
                "help": "Minimum ATM put IV (%) required to enter a new spread",
            },
            {
                "key": "signal_threshold", "label": "Signal threshold (%)",
                "type": "slider", "min": 50, "max": 80, "default": 62, "step": 1,
                "col": 1, "row": 0,
                "help": "Minimum model probability (%) to trade",
            },
            {
                "key": "spread_width", "label": "Spread width (strikes)",
                "type": "slider", "min": 1, "max": 5, "default": 2, "step": 1,
                "col": 2, "row": 0,
                "help": "Number of $1 (or $5) increments between short and long put",
            },
            {
                "key": "dte_entry", "label": "Target DTE at entry",
                "type": "slider", "min": 7, "max": 21, "default": 14, "step": 1,
                "col": 0, "row": 1,
                "help": "Target days-to-expiry when opening a new spread",
            },
            {
                "key": "position_size_pct", "label": "Position size %",
                "type": "slider", "min": 0.01, "max": 0.05, "default": 0.03, "step": 0.01,
                "col": 1, "row": 1,
                "help": "Capital fraction allocated per trade",
            },
        ]

    def is_trainable(self) -> bool:
        return True

    # ── Feature engineering ───────────────────────────────────────────────────

    @staticmethod
    def _compute_atm_put_iv(snap_df: pd.DataFrame, spot: float) -> Optional[float]:
        """Median IV of puts within 5% of spot."""
        if snap_df is None or snap_df.empty:
            return None
        df = snap_df.copy()
        for col in ["StrikePrice", "ImpliedVol", "OpenInterest", "Delta", "DTE"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        if "OptionType" not in df.columns or "ImpliedVol" not in df.columns:
            return None

        puts = df[df["OptionType"].str.lower().str.startswith("p")].dropna(subset=["StrikePrice", "ImpliedVol"])
        if puts.empty:
            return None
        atm_puts = puts[(puts["StrikePrice"] >= spot * 0.95) & (puts["StrikePrice"] <= spot * 1.05)]
        if atm_puts.empty:
            # widen to 10%
            atm_puts = puts[(puts["StrikePrice"] >= spot * 0.90) & (puts["StrikePrice"] <= spot * 1.10)]
        if atm_puts.empty:
            return None
        iv_vals = atm_puts["ImpliedVol"].dropna()
        iv_vals = iv_vals[iv_vals > 0]
        if iv_vals.empty:
            return None
        iv = float(iv_vals.median())
        # Normalise: if stored as decimals (e.g. 0.45), convert to percent
        return iv * 100.0 if iv < 5.0 else iv

    def _build_feature_row(
        self,
        snap_df:     pd.DataFrame,
        price_slice: pd.DataFrame,
        vix_series:  pd.Series,
        fomc_dates:  Optional[pd.Series],
        current_date: pd.Timestamp,
    ) -> Optional[dict]:
        """Compute one feature row. Returns None if data is insufficient."""
        if snap_df is None or snap_df.empty:
            return None
        if price_slice is None or len(price_slice) < 22:
            return None

        spot = float(price_slice["close"].iloc[-1])
        if spot <= 0:
            return None

        # Normalise numeric columns
        df = snap_df.copy()
        for col in ["StrikePrice", "ImpliedVol", "OpenInterest", "Delta", "DTE"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # Normalise OptionType
        if "OptionType" not in df.columns:
            return None

        puts  = df[df["OptionType"].str.lower().str.startswith("p")].dropna(subset=["OpenInterest"])
        calls = df[df["OptionType"].str.lower().str.startswith("c")].dropna(subset=["OpenInterest"])

        # 1. Put/call OI ratio
        total_put_oi  = float(puts["OpenInterest"].sum())
        total_call_oi = float(calls["OpenInterest"].sum())
        if total_call_oi <= 0:
            return None
        put_call_oi_ratio = total_put_oi / total_call_oi

        # 2. ATM put IV
        atm_put_iv = self._compute_atm_put_iv(df, spot)
        if atm_put_iv is None:
            return None

        # 3. IV 5d z-score (needs history built externally — passed as vix_series proxy here)
        # We use the atm_put_iv series stored from prior rows via rolling window
        # During feature building we compute from accumulated history
        iv_5d_zscore = 0.0  # will be filled in _build_feature_matrix

        # 4. 20d realized vol
        log_rets = np.log(price_slice["close"] / price_slice["close"].shift(1)).dropna()
        if len(log_rets) < 20:
            return None
        rvol_20d = float(log_rets.iloc[-20:].std() * np.sqrt(252) * 100)

        # 5. 5d return
        close_arr = price_slice["close"].values
        stock_5d_return = float((close_arr[-1] - close_arr[-6]) / close_arr[-6]) if len(close_arr) >= 6 else 0.0

        # 6. OI spike: total OI today > 1.5× 10d average
        # This is computed at higher level; default 0
        total_oi_today = float(df["OpenInterest"].sum()) if "OpenInterest" in df.columns else 0.0

        # 7. VIX
        vix_val = float(vix_series.iloc[-1]) if vix_series is not None and not vix_series.empty else 20.0

        # 8. Days to FOMC
        days_to_fomc = 90.0  # default if calendar not available
        if fomc_dates is not None and len(fomc_dates) > 0:
            future = fomc_dates[fomc_dates >= current_date]
            if len(future) > 0:
                days_to_fomc = float((future.iloc[0] - current_date).days)

        return {
            "stock_put_call_oi_ratio": put_call_oi_ratio,
            "stock_atm_put_iv":        atm_put_iv,
            "stock_iv_5d_zscore":      iv_5d_zscore,  # filled in caller
            "stock_20d_realized_vol":  rvol_20d,
            "stock_5d_return":         stock_5d_return,
            "stock_oi_spike":          0.0,            # filled in caller
            "vix":                     vix_val,
            "days_to_fomc":            days_to_fomc,
            "_total_oi_today":         total_oi_today,  # helper for spike calc
        }

    def _build_feature_matrix(
        self,
        snap_by_date: dict,    # date → option_snapshots DataFrame
        price_data:   pd.DataFrame,
        vix_series:   pd.Series,
        fomc_dates:   Optional[pd.Series],
    ) -> pd.DataFrame:
        """Build the full feature matrix, filling z-score and OI spike columns."""
        rows         = []
        iv_history:  list[float] = []
        oi_history:  list[float] = []
        dates_sorted = sorted(snap_by_date.keys())

        for d in dates_sorted:
            ts = pd.Timestamp(d)
            if ts not in price_data.index:
                continue
            px_slice = price_data.loc[:ts].tail(120)
            vix_s    = vix_series.loc[:ts].tail(30) if ts <= vix_series.index.max() else vix_series.tail(30)

            row = self._build_feature_row(
                snap_df      = snap_by_date[d],
                price_slice  = px_slice,
                vix_series   = vix_s,
                fomc_dates   = fomc_dates,
                current_date = ts,
            )
            if row is None:
                continue

            # IV z-score from accumulated history
            iv_history.append(row["stock_atm_put_iv"])
            if len(iv_history) >= 20:
                iv_ser = pd.Series(iv_history)
                mean20 = float(iv_ser.iloc[-20:].mean())
                std20  = float(iv_ser.iloc[-20:].std())
                row["stock_iv_5d_zscore"] = (row["stock_atm_put_iv"] - mean20) / std20 if std20 > 0 else 0.0
            else:
                row["stock_iv_5d_zscore"] = 0.0

            # OI spike
            oi_today = row.pop("_total_oi_today")
            oi_history.append(oi_today)
            if len(oi_history) >= 10:
                oi_10d_avg = float(pd.Series(oi_history[-11:-1]).mean())
                row["stock_oi_spike"] = 1.0 if (oi_10d_avg > 0 and oi_today > 1.5 * oi_10d_avg) else 0.0
            else:
                row["stock_oi_spike"] = 0.0

            row["date"] = ts
            rows.append(row)

        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows).set_index("date")

    # ── Labels ────────────────────────────────────────────────────────────────

    @staticmethod
    def _build_labels(feature_df: pd.DataFrame, horizon: int = 5) -> pd.Series:
        """
        iv_compressed_5d = 1 if ATM put IV drops ≥ 5 vol points in next `horizon` bars.
        """
        iv = feature_df["stock_atm_put_iv"].values.astype(float)
        n  = len(iv)
        labels = np.full(n, 0, dtype=int)
        for i in range(n - horizon):
            if iv[i] > 0 and (iv[i] - iv[i + horizon]) >= 5.0:
                labels[i] = 1
        # Mask last horizon rows (no forward data)
        labels[-(horizon):] = -1
        return pd.Series(labels, index=feature_df.index, name="label")

    # ── Logistic Regression ───────────────────────────────────────────────────

    def _train_model(self, X: np.ndarray, y: np.ndarray):
        """Fit logistic regression with L2 regularisation."""
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler
        from sklearn.pipeline import Pipeline

        clf = Pipeline([
            ("scaler", StandardScaler()),
            ("lr", LogisticRegression(C=0.5, max_iter=500, class_weight="balanced",
                                      solver="lbfgs")),
        ])
        clf.fit(X, y)
        return clf

    def _walk_forward_train(
        self,
        feature_df: pd.DataFrame,
        horizon:    int = 5,
        progress_callback=None,
    ) -> dict:
        """
        Walk-forward training: 150-bar warm-up, retrain every 30 bars.
        Returns final model (trained on all labelled data) and meta.
        """
        labels = self._build_labels(feature_df, horizon)
        valid  = labels[labels >= 0].index
        X_all  = feature_df.loc[valid, self.FEATURE_COLS].values.astype(float)
        y_all  = labels.loc[valid].values.astype(int)
        n      = len(X_all)

        if n < _WARMUP_BARS:
            raise ValueError(
                f"Insufficient labelled samples for training: need ≥ {_WARMUP_BARS}, got {n}"
            )

        # Walk-forward evaluation
        preds_oos: list[int] = []
        trues_oos: list[int] = []

        step = 0
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

        # Final model on all labelled data
        if progress_callback:
            progress_callback(0.72, "Fitting final model…")
        self._model = self._train_model(X_all, y_all)

        # OOS accuracy
        cv_acc = None
        if preds_oos:
            from sklearn.metrics import accuracy_score
            cv_acc = float(accuracy_score(trues_oos, preds_oos))

        # Feature importances from LR coefficients
        feat_imp = {}
        try:
            lr_step = self._model.named_steps["lr"]
            coefs   = lr_step.coef_[0]
            feat_imp = {c: round(float(v), 6) for c, v in zip(self.FEATURE_COLS, coefs)}
        except Exception:
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
        path = _MODEL_DIR / f"oi_put_fade_{ticker}.pkl"
        with open(path, "wb") as f:
            pickle.dump({"model": self._model, "meta": self._model_meta}, f)
        return str(path)

    def load_model(self, ticker: str = "default") -> bool:
        path = _MODEL_DIR / f"oi_put_fade_{ticker}.pkl"
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
        Returns BUY (bull put spread) when probability ≥ threshold and IV ≥ floor.
        """
        if self._model is None:
            return SignalResult(
                strategy_name=self.name, signal="HOLD",
                confidence=0.0, position_size_pct=0.0,
                metadata={"reason": "model not trained"},
            )

        atm_put_iv = market_snapshot.get("stock_atm_put_iv", 0.0)
        if atm_put_iv < self.min_iv_floor:
            return SignalResult(
                strategy_name=self.name, signal="HOLD",
                confidence=0.0, position_size_pct=0.0,
                metadata={"reason": f"ATM put IV {atm_put_iv:.1f} below floor {self.min_iv_floor}"},
            )

        X = np.array([[market_snapshot.get(c, 0.0) for c in self.FEATURE_COLS]], dtype=float)
        try:
            proba     = self._model.predict_proba(X)[0]
            prob_compress = float(proba[1]) if len(proba) > 1 else 0.0
        except Exception:
            prob_compress = 0.0

        threshold = self.signal_threshold / 100.0
        if prob_compress >= threshold:
            return SignalResult(
                strategy_name=self.name, signal="BUY",
                confidence=round(prob_compress, 4),
                position_size_pct=self.position_size_pct,
                metadata={
                    "prob_compress":  round(prob_compress, 4),
                    "atm_put_iv":     atm_put_iv,
                    "spread_type":    "bull_put",
                    "put_call_oi_ratio": market_snapshot.get("stock_put_call_oi_ratio", 0.0),
                },
            )
        return SignalResult(
            strategy_name=self.name, signal="HOLD",
            confidence=round(prob_compress, 4), position_size_pct=0.0,
            metadata={"prob_compress": round(prob_compress, 4), "reason": "below threshold"},
        )

    # ── Backtest ──────────────────────────────────────────────────────────────

    def backtest(
        self,
        price_data:       pd.DataFrame,
        auxiliary_data:   dict,
        starting_capital: float = 100_000,
        ticker:           str   = "UNKNOWN",
        min_iv_floor:     Optional[float] = None,
        signal_threshold: Optional[float] = None,
        spread_width:     Optional[int]   = None,
        dte_entry:        Optional[int]   = None,
        position_size_pct: Optional[float] = None,
        **kwargs,
    ) -> BacktestResult:
        """
        Walk-forward simulation with in-line model retraining.

        auxiliary_data must contain:
          "option_snapshots" : DataFrame with SnapshotDate, StrikePrice, OptionType,
                               ImpliedVol, OpenInterest, Delta, DTE columns
          "vix"              : DataFrame date-indexed with "close" column
          "fomc_calendar"    : DataFrame with "MeetingDate" column (optional)
        """
        # ── Resolve effective params ──────────────────────────────────────
        iv_floor_eff  = min_iv_floor      if min_iv_floor      is not None else self.min_iv_floor
        thresh_eff    = signal_threshold  if signal_threshold  is not None else self.signal_threshold
        width_eff     = spread_width      if spread_width      is not None else self.spread_width
        dte_eff       = dte_entry         if dte_entry         is not None else self.dte_entry
        pos_sz_eff    = position_size_pct if position_size_pct is not None else self.position_size_pct

        pt_eff        = self.profit_target_pct
        sl_mult       = self.stop_loss_mult
        dte_stop_eff  = self.dte_time_stop
        comm          = self.commission_per_leg
        r             = _RISK_FREE_RATE

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

        # FOMC calendar
        fomc_df    = auxiliary_data.get("fomc_calendar")
        fomc_dates = None
        if fomc_df is not None and not fomc_df.empty and "MeetingDate" in fomc_df.columns:
            fomc_dates = pd.to_datetime(fomc_df["MeetingDate"]).sort_values().reset_index(drop=True)

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
            fomc_dates   = fomc_dates,
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
        iv_history:    list[float] = []

        for fi, dt in enumerate(all_feat_dates):
            feat_row = feature_df.iloc[fi]
            spot_ser = close.reindex([dt]).dropna()
            if spot_ser.empty:
                equity_list.append(capital)
                continue
            spot    = float(spot_ser.iloc[0])
            iv_hist = feature_df["stock_atm_put_iv"].iloc[:fi + 1]
            atm_iv  = float(feat_row["stock_atm_put_iv"])
            vix_val = float(feat_row["vix"])

            # ── Train / retrain model ─────────────────────────────────────
            if fi >= _WARMUP_BARS and (
                current_model is None or (fi - _WARMUP_BARS) % _RETRAIN_EVERY == 0
            ):
                labels_so_far = self._build_labels(feature_df.iloc[:fi + 1])
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
                iv_now  = max(atm_iv / 100.0, 0.01)

                cur_val = (
                    bs_price(spot, trade["short_K"], T_now, r, iv_now, "put")
                    - bs_price(spot, trade["long_K"],  T_now, r, iv_now, "put")
                )
                pnl_per_spread = trade["credit"] - cur_val
                pnl_total      = pnl_per_spread * trade["contracts"] * 100

                exit_reason: Optional[str] = None
                if pnl_per_spread >= pt_eff * trade["credit"]:
                    exit_reason = "profit_target"
                elif dte_rem <= dte_stop_eff:
                    exit_reason = "dte_stop"
                elif cur_val >= sl_mult * trade["credit"]:
                    exit_reason = "stop_loss"
                elif fi == n_feat - 1:
                    exit_reason = "end_of_data"

                if exit_reason:
                    close_comm = 2 * comm * trade["contracts"]
                    net_pnl    = round(pnl_total - close_comm, 2)
                    capital   += net_pnl
                    closed_trades.append({
                        "entry_date":  trade["entry_date"].date() if hasattr(trade["entry_date"], "date") else trade["entry_date"],
                        "exit_date":   dt.date() if hasattr(dt, "date") else dt,
                        "spread_type": "bull_put",
                        "short_K":     round(trade["short_K"],  2),
                        "long_K":      round(trade["long_K"],   2),
                        "credit":      round(trade["credit"],   4),
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
                and atm_iv >= iv_floor_eff
                and spot > 0
                and (n_feat - fi) > dte_eff
            )

            if can_enter:
                X_live = np.array([[feat_row.get(c, 0.0) for c in self.FEATURE_COLS]], dtype=float)
                try:
                    proba_compress = float(current_model.predict_proba(X_live)[0][1])
                except Exception:
                    proba_compress = 0.0

                if proba_compress >= (thresh_eff / 100.0):
                    T_entry = dte_eff / 252.0
                    iv_dec  = max(atm_iv / 100.0, 0.01)

                    # Short put at 0.25 delta
                    short_K_raw = _find_strike_for_delta(spot, T_entry, r, iv_dec, 0.25, "put")
                    short_K     = _round_to_increment(short_K_raw, spot)
                    inc         = 1.0 if spot < 100.0 else 5.0
                    long_K      = max(short_K - width_eff * inc, 0.01)

                    short_prem  = bs_price(spot, short_K, T_entry, r, iv_dec, "put")
                    long_prem   = bs_price(spot, long_K,  T_entry, r, iv_dec, "put")
                    credit      = short_prem - long_prem

                    if credit <= 0.01:
                        equity_list.append(capital)
                        continue

                    spread_width_dollars = short_K - long_K
                    max_loss_per_cont    = spread_width_dollars * 100
                    if max_loss_per_cont <= 0:
                        equity_list.append(capital)
                        continue

                    contracts    = max(1, math.floor(capital * pos_sz_eff / max_loss_per_cont))
                    entry_comm   = 2 * comm * contracts
                    capital     -= entry_comm

                    expiry_idx   = min(fi + dte_eff, n_feat - 1)
                    open_trades.append({
                        "entry_date": dt,
                        "expiry_idx": expiry_idx,
                        "dte_entry":  dte_eff,
                        "short_K":    short_K,
                        "long_K":     long_K,
                        "credit":     credit,
                        "contracts":  contracts,
                    })

            # ── Mark-to-market equity ─────────────────────────────────────
            mtm = 0.0
            iv_dec_mtm = max(atm_iv / 100.0, 0.01)
            for ot in open_trades:
                dte_rem   = ot["expiry_idx"] - fi
                T_mtm     = max(dte_rem / 252.0, 1e-6)
                ot_val    = (
                    bs_price(spot, ot["short_K"], T_mtm, r, iv_dec_mtm, "put")
                    - bs_price(spot, ot["long_K"],  T_mtm, r, iv_dec_mtm, "put")
                )
                mtm      += (ot["credit"] - ot_val) * ot["contracts"] * 100
            equity_list.append(capital + mtm)

        # ── Build results ─────────────────────────────────────────────────
        equity    = pd.Series(equity_list, index=all_feat_dates, dtype=float)
        daily_ret = equity.pct_change().dropna()
        bh_ret    = close.pct_change().reindex(equity.index).dropna()

        trades_df = (
            pd.DataFrame(closed_trades)
            if closed_trades
            else pd.DataFrame(columns=[
                "entry_date", "exit_date", "spread_type", "short_K", "long_K",
                "credit", "contracts", "pnl", "exit_reason", "dte_held",
            ])
        )

        metrics = compute_all_metrics(
            equity_curve       = equity,
            trades_df          = trades_df,
            benchmark_returns  = bh_ret,
        )

        # Store trained model for live use
        self._model = current_model

        return BacktestResult(
            strategy_name = self.name,
            equity_curve  = equity,
            daily_returns = daily_ret,
            trades        = trades_df,
            metrics       = metrics,
            params        = {
                **self.get_params(),
                "min_iv_floor":     iv_floor_eff,
                "signal_threshold": thresh_eff,
                "dte_entry":        dte_eff,
                "ticker":           ticker,
            },
            extra = {
                "model_meta":           self._model_meta,
                "feature_df":           feature_df,
                "open_trades_at_end":   len(open_trades),
            },
        )
