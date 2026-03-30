"""
IV Skew Momentum Strategy.

THESIS
------
The shape and direction of a stock's IV skew (OTM puts vs OTM calls) is a
forward-looking indicator of expected price direction.  When put skew
accelerates — put IV rising faster than call IV — the options market is pricing
in downside risk before price reacts.  A LightGBM 3-class classifier detects
extreme skew readings and their momentum to time directional vertical spreads.

TRADE STRUCTURE
---------------
Bullish signal (P >= signal_threshold):
  Bull Call Spread — long ATM call, short call at ATM + spread_width_pct × spot
  DTE target: dte_entry (default 21)

Bearish signal (P >= signal_threshold):
  Bear Put Spread — long ATM put, short put at ATM − spread_width_pct × spot

LABELS (3-class)
  0 = NEUTRAL  (|5d return| <= 2%)
  1 = BULLISH  (5d return > +2%)
  2 = BEARISH  (5d return < −2%)

EXIT CONDITIONS
  Profit target : 60% of max spread value
  Loss stop     : lose 50% of debit paid
  Time stop     : close at 7 DTE remaining

Walk-forward: 150-bar warm-up, retrain every 30 bars.
"""

from __future__ import annotations

import logging
import math
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
NEUTRAL  = 0
BULLISH  = 1
BEARISH  = 2
LABEL_NAMES = {NEUTRAL: "NEUTRAL", BULLISH: "BULLISH", BEARISH: "BEARISH"}

# ── Model persistence ─────────────────────────────────────────────────────────
_MODEL_DIR = Path(__file__).parent.parent / "saved_models"
_MODEL_DIR.mkdir(exist_ok=True)

_WARMUP_BARS  = 150   # minimum bars before first model fit
_RETRAIN_EVERY = 30   # walk-forward retrain cadence (bars)
_RISK_FREE     = 0.045
_HOLD_STOP_DTE = 7    # close trade when remaining DTE <= this


class IVSkewMomentumStrategy(BaseStrategy):
    """
    LightGBM 3-class classifier trained on IV skew shape and momentum.

    Predicts whether the ticker will rise > 2%, fall > 2%, or stay flat over
    the next 5 trading days, then enters a bull call spread or bear put spread.
    """

    name                 = "iv_skew_momentum"
    display_name         = "IV Skew Momentum"
    strategy_type        = StrategyType.AI_DRIVEN
    status               = StrategyStatus.ACTIVE
    description          = (
        "LightGBM 3-class classifier trained on IV skew shape and momentum. "
        "Bullish signal → bull call spread; bearish signal → bear put spread. "
        "11 features across skew, IVR, realized vol, and macro context."
    )
    asset_class          = "equities_options"
    typical_holding_days = 21
    target_sharpe        = 1.3

    # ── Feature column order (must match training) ────────────────────────────
    FEATURE_COLS = [
        "stock_25d_put_skew",
        "stock_10d_put_skew",
        "stock_skew_5d_change",
        "stock_skew_zscore",
        "stock_atm_iv",
        "stock_ivr",
        "stock_5d_return",
        "stock_20d_realized_vol",
        "vix",
        "vix_5d_change",
        "spy_5d_return",
    ]

    def __init__(
        self,
        signal_threshold:  float = 58.0,   # % probability required to trade
        spread_width_pct:  float = 4.0,    # % of spot for spread width
        dte_entry:         int   = 21,     # target DTE at entry
        position_size_pct: float = 3.0,    # % of capital per trade
        skew_lookback:     int   = 20,     # days for skew z-score
        # LightGBM hyper-params
        n_estimators:      int   = 100,
        max_depth:         int   = 4,
        learning_rate:     float = 0.05,
        min_child_samples: int   = 20,
        slippage_per_leg:  float = 0.05,
        commission_per_leg: float = 0.65,
    ):
        self.signal_threshold  = signal_threshold / 100.0  # store as fraction
        self.spread_width_pct  = spread_width_pct / 100.0
        self.dte_entry         = dte_entry
        self.position_size_pct = position_size_pct / 100.0
        self.skew_lookback     = skew_lookback
        self.n_estimators      = n_estimators
        self.max_depth         = max_depth
        self.learning_rate     = learning_rate
        self.min_child_samples = min_child_samples
        self.slippage_per_leg  = slippage_per_leg
        self.commission_per_leg = commission_per_leg
        self._model             = None
        self._model_meta: dict  = {}

    # ═════════════════════════════════════════════════════════════════════════
    # Public interface
    # ═════════════════════════════════════════════════════════════════════════

    def get_params(self) -> dict:
        return {
            "signal_threshold":  self.signal_threshold * 100,
            "spread_width_pct":  self.spread_width_pct * 100,
            "dte_entry":         self.dte_entry,
            "position_size_pct": self.position_size_pct * 100,
            "skew_lookback":     self.skew_lookback,
            "n_estimators":      self.n_estimators,
            "max_depth":         self.max_depth,
            "learning_rate":     self.learning_rate,
        }

    def get_backtest_ui_params(self) -> list[dict]:
        return [
            {"key": "signal_threshold",  "label": "Signal threshold (%)",  "type": "int",   "default": 58,   "min": 50,  "max": 75},
            {"key": "spread_width_pct",  "label": "Spread width (% spot)",  "type": "int",   "default": 4,    "min": 2,   "max": 8},
            {"key": "dte_entry",         "label": "DTE at entry",           "type": "int",   "default": 21,   "min": 14,  "max": 30},
            {"key": "position_size_pct", "label": "Position size (%)",      "type": "int",   "default": 3,    "min": 1,   "max": 5},
            {"key": "skew_lookback",     "label": "Skew lookback (days)",   "type": "int",   "default": 20,   "min": 10,  "max": 30},
            {"key": "n_estimators",      "label": "LGB trees",              "type": "int",   "default": 100,  "min": 50,  "max": 500},
            {"key": "max_depth",         "label": "LGB max depth",          "type": "int",   "default": 4,    "min": 2,   "max": 8},
        ]

    def is_trainable(self) -> bool:
        return True

    # ═════════════════════════════════════════════════════════════════════════
    # Feature engineering helpers
    # ═════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _median_iv_by_delta(snap_today: pd.DataFrame,
                            delta_lo: float, delta_hi: float,
                            option_type: str) -> Optional[float]:
        """
        Median IV of options whose |delta| is in [delta_lo, delta_hi].
        option_type: "call" or "put"
        Falls back to moneyness-based selection if delta column is absent/null.
        """
        if snap_today is None or snap_today.empty:
            return None

        otype = option_type.lower()
        col_type = None
        for c in ("OptionType", "option_type", "type", "contract_type"):
            if c in snap_today.columns:
                col_type = c
                break
        if col_type is None:
            return None

        sub = snap_today[snap_today[col_type].str.lower().str.startswith(otype[0])]
        if sub.empty:
            return None

        # Ensure IV column exists
        iv_col = None
        for c in ("ImpliedVol", "implied_vol", "iv", "IV"):
            if c in sub.columns:
                iv_col = c
                break
        if iv_col is None:
            return None

        sub = sub.copy()
        sub[iv_col] = pd.to_numeric(sub[iv_col], errors="coerce")

        # Try delta-based selection
        delta_col = None
        for c in ("Delta", "delta"):
            if c in sub.columns:
                delta_col = c
                break

        if delta_col is not None:
            sub[delta_col] = pd.to_numeric(sub[delta_col], errors="coerce")
            sub_d = sub[sub[delta_col].notna()]
            if not sub_d.empty:
                mask = sub_d[delta_col].abs().between(delta_lo, delta_hi)
                filtered = sub_d.loc[mask, iv_col].dropna()
                if len(filtered) >= 1:
                    return float(filtered.median())

        # Fallback: moneyness-based (no delta available)
        spot_col = None
        for c in ("spot", "Spot", "underlying_price", "UnderlyingPrice"):
            if c in sub.columns:
                spot_col = c
                break
        strike_col = None
        for c in ("StrikePrice", "strike_price", "strike", "Strike"):
            if c in sub.columns:
                strike_col = c
                break
        if spot_col is None or strike_col is None:
            # No way to compute moneyness — return median of all options of this type
            vals = sub[iv_col].dropna()
            return float(vals.median()) if len(vals) >= 1 else None

        sub[strike_col] = pd.to_numeric(sub[strike_col], errors="coerce")
        sub[spot_col]   = pd.to_numeric(sub[spot_col],   errors="coerce")
        sub = sub[sub[spot_col] > 0]
        if sub.empty:
            return None
        # Approximate delta from moneyness: for puts, OTM means strike < spot
        if otype == "put":
            # 25-delta ~ strike/spot in [0.92, 0.97]; 10-delta ~ [0.85, 0.92]
            if abs(delta_lo - 0.20) < 0.05:
                mono_lo, mono_hi = 0.88, 0.97
            else:
                mono_lo, mono_hi = 0.80, 0.88
            mask = (sub[strike_col] / sub[spot_col]).between(mono_lo, mono_hi)
        else:
            # call OTM: strike > spot
            if abs(delta_lo - 0.20) < 0.05:
                mono_lo, mono_hi = 1.03, 1.12
            else:
                mono_lo, mono_hi = 1.12, 1.20
            mask = (sub[strike_col] / sub[spot_col]).between(mono_lo, mono_hi)

        filtered = sub.loc[mask, iv_col].dropna()
        return float(filtered.median()) if len(filtered) >= 1 else None

    @staticmethod
    def _atm_iv(snap_today: pd.DataFrame, spot: float) -> Optional[float]:
        """Median IV of options with |delta| in [0.45, 0.55], or nearest-strike fallback."""
        if snap_today is None or snap_today.empty:
            return None
        iv_col = None
        for c in ("ImpliedVol", "implied_vol", "iv", "IV"):
            if c in snap_today.columns:
                iv_col = c
                break
        if iv_col is None:
            return None

        snap = snap_today.copy()
        snap[iv_col] = pd.to_numeric(snap[iv_col], errors="coerce")

        delta_col = None
        for c in ("Delta", "delta"):
            if c in snap.columns:
                delta_col = c
                break

        if delta_col is not None:
            snap[delta_col] = pd.to_numeric(snap[delta_col], errors="coerce")
            mask = snap[delta_col].abs().between(0.45, 0.55)
            vals = snap.loc[mask, iv_col].dropna()
            if len(vals) >= 1:
                return float(vals.median())

        # Fallback: nearest strike to spot
        strike_col = None
        for c in ("StrikePrice", "strike_price", "strike", "Strike"):
            if c in snap.columns:
                strike_col = c
                break
        if strike_col is None:
            vals = snap[iv_col].dropna()
            return float(vals.median()) if len(vals) >= 1 else None

        snap[strike_col] = pd.to_numeric(snap[strike_col], errors="coerce")
        snap = snap[snap[strike_col].notna()]
        if snap.empty:
            return None
        idx = (snap[strike_col] - spot).abs().idxmin()
        row = snap.loc[[idx]]
        val = pd.to_numeric(row[iv_col], errors="coerce").dropna()
        return float(val.iloc[0]) if len(val) >= 1 else None

    def _build_feature_row(
        self,
        snap_today:     pd.DataFrame,
        price_df:       pd.DataFrame,   # OHLCV up to and including today
        atm_iv_history: pd.Series,      # historical ATM IV values (same ticker)
        vix_series:     pd.Series,
        spy_price_df:   Optional[pd.DataFrame] = None,
    ) -> Optional[dict]:
        """
        Compute one feature row. Returns None if any required piece is missing.
        """
        if snap_today is None or snap_today.empty:
            return None
        if price_df is None or len(price_df) < 22:
            return None

        spot = float(price_df["close"].iloc[-1])
        if spot <= 0:
            return None

        # ── Skew features ──────────────────────────────────────────────────
        put25  = self._median_iv_by_delta(snap_today, 0.20, 0.30, "put")
        call25 = self._median_iv_by_delta(snap_today, 0.20, 0.30, "call")
        put10  = self._median_iv_by_delta(snap_today, 0.08, 0.14, "put")
        call10 = self._median_iv_by_delta(snap_today, 0.08, 0.14, "call")

        if put25 is None or call25 is None:
            return None  # required

        skew_25d = put25 - call25
        skew_10d = (put10 - call10) if (put10 is not None and call10 is not None) else skew_25d

        # ── ATM IV ─────────────────────────────────────────────────────────
        atm_iv = self._atm_iv(snap_today, spot)
        if atm_iv is None:
            return None

        # ── IVR: 52-week rank of ATM IV ────────────────────────────────────
        iv_hist = atm_iv_history.dropna()
        if len(iv_hist) >= 2:
            lo, hi = float(iv_hist.min()), float(iv_hist.max())
            ivr = float(np.clip((atm_iv - lo) / (hi - lo + 1e-9), 0, 1))
        else:
            ivr = 0.5

        # ── Skew 5-day change ──────────────────────────────────────────────
        # Requires at least 6 entries in atm_iv_history — use skew stored in history
        # We just compute it from spot data: if not enough history, set to 0
        skew_hist = atm_iv_history.get("skew_25d") if isinstance(atm_iv_history, pd.DataFrame) else None
        skew_5d_change = 0.0  # will be filled when series is built outside

        # ── Skew z-score ───────────────────────────────────────────────────
        if len(iv_hist) >= self.skew_lookback:
            recent = iv_hist.iloc[-self.skew_lookback:]
            mu, sigma = float(recent.mean()), float(recent.std())
            skew_zscore = float((atm_iv - mu) / (sigma + 1e-9))
        else:
            skew_zscore = 0.0

        # ── Price-based features ───────────────────────────────────────────
        closes = price_df["close"].astype(float)
        if len(closes) < 6:
            return None
        ret_5d = float((closes.iloc[-1] - closes.iloc[-6]) / closes.iloc[-6])

        log_rets = np.log(closes / closes.shift(1)).dropna()
        rvol_20d = float(log_rets.iloc[-20:].std() * np.sqrt(252)) if len(log_rets) >= 20 else float(log_rets.std() * np.sqrt(252))

        # ── VIX ────────────────────────────────────────────────────────────
        if vix_series is None or vix_series.empty:
            return None
        vix_val = float(vix_series.iloc[-1])
        vix_5d  = float(vix_series.iloc[-1] - vix_series.iloc[-6]) if len(vix_series) >= 6 else 0.0

        # ── SPY 5-day return ───────────────────────────────────────────────
        spy_ret = 0.0
        if spy_price_df is not None and len(spy_price_df) >= 6:
            sc = spy_price_df["close"].astype(float)
            spy_ret = float((sc.iloc[-1] - sc.iloc[-6]) / sc.iloc[-6])

        return {
            "stock_25d_put_skew":    skew_25d,
            "stock_10d_put_skew":    skew_10d,
            "stock_skew_5d_change":  skew_5d_change,   # patched by caller after row series built
            "stock_skew_zscore":     skew_zscore,
            "stock_atm_iv":          atm_iv,
            "stock_ivr":             ivr,
            "stock_5d_return":       ret_5d,
            "stock_20d_realized_vol": rvol_20d,
            "vix":                   vix_val,
            "vix_5d_change":         vix_5d,
            "spy_5d_return":         spy_ret,
            # extras for trade simulation (not features)
            "_spot":                 spot,
            "_atm_iv_raw":           atm_iv,
        }

    # ═════════════════════════════════════════════════════════════════════════
    # Label construction
    # ═════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _build_labels(price_df: pd.DataFrame, horizon: int = 5) -> pd.Series:
        """
        3-class label:  1 (BULLISH) if 5d fwd return > +2%
                        2 (BEARISH) if 5d fwd return < −2%
                        0 (NEUTRAL) otherwise
        """
        closes = price_df["close"].astype(float)
        n      = len(closes)
        labels = np.full(n, NEUTRAL, dtype=int)
        for i in range(n - horizon):
            fwd = (float(closes.iloc[i + horizon]) - float(closes.iloc[i])) / float(closes.iloc[i])
            if fwd > 0.02:
                labels[i] = BULLISH
            elif fwd < -0.02:
                labels[i] = BEARISH
        labels[-(horizon):] = -1   # no forward data
        return pd.Series(labels, index=price_df.index, name="label")

    # ═════════════════════════════════════════════════════════════════════════
    # LightGBM classifier
    # ═════════════════════════════════════════════════════════════════════════

    def _get_classifier(self):
        """Return a LightGBM classifier; fallback to sklearn GBM if lgb not installed."""
        try:
            import lightgbm as lgb
            return lgb.LGBMClassifier(
                n_estimators      = self.n_estimators,
                max_depth         = self.max_depth,
                learning_rate     = self.learning_rate,
                min_child_samples = self.min_child_samples,
                class_weight      = "balanced",
                num_class         = 3,
                objective         = "multiclass",
                n_jobs            = -1,
                verbose           = -1,
            )
        except ImportError:
            logger.warning("lightgbm not installed — falling back to sklearn GradientBoostingClassifier")
            from sklearn.ensemble import GradientBoostingClassifier
            from sklearn.multiclass import OneVsRestClassifier
            return OneVsRestClassifier(GradientBoostingClassifier(
                n_estimators  = self.n_estimators,
                max_depth     = self.max_depth,
                learning_rate = self.learning_rate,
            ))

    def _train_classifier(self, X: np.ndarray, y: np.ndarray):
        """Fit with class-weight balancing."""
        clf = self._get_classifier()
        try:
            clf.fit(X, y)
        except Exception as e:
            logger.warning(f"Classifier fit error: {e}; retrying without extra kwargs")
            from sklearn.ensemble import GradientBoostingClassifier
            from sklearn.multiclass import OneVsRestClassifier
            clf = OneVsRestClassifier(GradientBoostingClassifier(
                n_estimators=self.n_estimators, max_depth=self.max_depth,
                learning_rate=self.learning_rate,
            ))
            clf.fit(X, y)
        return clf

    # ═════════════════════════════════════════════════════════════════════════
    # Save / load
    # ═════════════════════════════════════════════════════════════════════════

    def save_model(self, ticker: str = "default") -> str:
        path = _MODEL_DIR / f"iv_skew_momentum_{ticker}.pkl"
        with open(path, "wb") as f:
            pickle.dump({"model": self._model, "meta": self._model_meta}, f)
        return str(path)

    def load_model(self, ticker: str = "default") -> bool:
        path = _MODEL_DIR / f"iv_skew_momentum_{ticker}.pkl"
        if not path.exists():
            return False
        with open(path, "rb") as f:
            data = pickle.load(f)
        self._model      = data["model"]
        self._model_meta = data.get("meta", {})
        return True

    # ═════════════════════════════════════════════════════════════════════════
    # Predict
    # ═════════════════════════════════════════════════════════════════════════

    def predict_direction(self, feature_row: dict) -> dict:
        """
        Returns {signal, label, confidence, probabilities, trade_type}.
        trade_type: 'bull_call_spread' | 'bear_put_spread' | None
        """
        if self._model is None:
            return {"signal": "NEUTRAL", "label": NEUTRAL, "confidence": 0.0,
                    "probabilities": {}, "trade_type": None}

        X = np.array([[feature_row.get(c, 0.0) for c in self.FEATURE_COLS]], dtype=float)
        pred = int(self._model.predict(X)[0])
        try:
            proba  = self._model.predict_proba(X)[0]
            conf   = float(proba[pred])
            prob_d = {LABEL_NAMES[i]: round(float(proba[i]), 4) for i in range(3)}
        except Exception:
            conf   = 1.0
            prob_d = {}

        trade_type = None
        if conf >= self.signal_threshold:
            if pred == BULLISH:
                trade_type = "bull_call_spread"
            elif pred == BEARISH:
                trade_type = "bear_put_spread"

        return {
            "signal":       LABEL_NAMES[pred],
            "label":        pred,
            "confidence":   conf,
            "probabilities": prob_d,
            "trade_type":   trade_type,
        }

    def generate_signal(self, market_snapshot: dict) -> SignalResult:
        result = self.predict_direction(market_snapshot)
        label  = result["label"]
        conf   = result["confidence"]
        if label == BULLISH and result["trade_type"]:
            signal = "BUY"
        elif label == BEARISH and result["trade_type"]:
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
        auxiliary_data:   dict,
        starting_capital: float = 100_000.0,
        ticker:           str   = "UNKNOWN",
        progress_callback = None,
        **kwargs,
    ) -> BacktestResult:
        """
        Walk-forward backtest with online model retraining every _RETRAIN_EVERY bars.

        auxiliary_data keys:
          option_snapshots : DataFrame — SnapshotDate, StrikePrice, OptionType,
                             ImpliedVol, Delta, DTE, OpenInterest
          vix              : DataFrame — date-indexed, "close" column
          rate10y          : DataFrame — date-indexed, "close" column (unused but accepted)
        """
        opts = auxiliary_data.get("option_snapshots")
        if opts is None or (isinstance(opts, pd.DataFrame) and opts.empty):
            raise ValueError(
                "iv_skew_momentum: option_snapshots is required but was empty or missing. "
                "Please sync options data for this ticker before running the backtest."
            )

        vix_df  = auxiliary_data.get("vix")
        spy_aux = auxiliary_data.get("spy_price")  # optional

        price_data = price_data.sort_index()

        # Normalise snapshot date column
        date_col = None
        for c in ("SnapshotDate", "snapshot_date", "date", "Date"):
            if c in opts.columns:
                date_col = c
                break
        if date_col is None:
            raise ValueError("option_snapshots must have a date column (SnapshotDate, date, etc.)")

        opts = opts.copy()
        opts[date_col] = pd.to_datetime(opts[date_col])

        # Index VIX by date
        if vix_df is not None and not isinstance(vix_df.index, pd.DatetimeIndex):
            try:
                vix_df = vix_df.set_index(pd.to_datetime(vix_df.index))
            except Exception:
                vix_df = None

        # Collect unique snapshot dates that also appear in price_data
        snap_dates = sorted(opts[date_col].dt.normalize().unique())
        price_dates = set(pd.to_datetime(price_data.index).normalize())
        snap_dates  = [d for d in snap_dates if d in price_dates]

        if len(snap_dates) < _WARMUP_BARS + 10:
            return BacktestResult(
                strategy_name = self.name,
                equity_curve  = pd.Series(dtype=float),
                daily_returns = pd.Series(dtype=float),
                trades        = pd.DataFrame(),
                metrics       = {"error": f"Insufficient snapshot history: {len(snap_dates)} dates (need ≥ {_WARMUP_BARS + 10})"},
            )

        # ── Step 1: Build full feature matrix ─────────────────────────────
        if progress_callback:
            progress_callback(0.05, "Building feature matrix…")

        atm_iv_series: list[float] = []   # historical ATM IVs for IVR / z-score
        skew_25d_series: list[float] = [] # for 5d change
        feature_rows: list[dict] = []

        for i, snap_dt in enumerate(snap_dates):
            ts = pd.Timestamp(snap_dt)
            if ts not in price_data.index:
                continue

            snap_today = opts[opts[date_col].dt.normalize() == ts].copy()
            # Add spot price so moneyness fallback can work
            spot = float(price_data.loc[ts, "close"])
            snap_today["spot"] = spot

            px_to = price_data.loc[:ts].tail(252)
            vix_s = pd.Series(dtype=float)
            if vix_df is not None:
                try:
                    vix_s = vix_df.loc[:ts, "close"].dropna().tail(20)
                except Exception:
                    pass

            spy_px = None
            if spy_aux is not None:
                try:
                    spy_px = spy_aux.loc[:ts].tail(20)
                except Exception:
                    pass

            atm_hist = pd.Series(atm_iv_series[-252:])

            try:
                row = self._build_feature_row(
                    snap_today     = snap_today,
                    price_df       = px_to,
                    atm_iv_history = atm_hist,
                    vix_series     = vix_s,
                    spy_price_df   = spy_px,
                )
            except Exception as e:
                logger.debug(f"Feature build failed on {ts}: {e}")
                row = None

            if row is None:
                continue

            # Patch skew_5d_change now that we have the series
            if len(skew_25d_series) >= 5:
                row["stock_skew_5d_change"] = row["stock_25d_put_skew"] - skew_25d_series[-5]
            else:
                row["stock_skew_5d_change"] = 0.0

            row["date"] = ts
            feature_rows.append(row)
            atm_iv_series.append(row["stock_atm_iv"])
            skew_25d_series.append(row["stock_25d_put_skew"])

            if progress_callback and i % 20 == 0:
                progress_callback(0.05 + 0.35 * (i / len(snap_dates)),
                                  f"Building features {i}/{len(snap_dates)}…")

        if len(feature_rows) < _WARMUP_BARS + 5:
            return BacktestResult(
                strategy_name = self.name,
                equity_curve  = pd.Series(dtype=float),
                daily_returns = pd.Series(dtype=float),
                trades        = pd.DataFrame(),
                metrics       = {"error": f"Only {len(feature_rows)} valid feature rows after filtering"},
            )

        feat_df = pd.DataFrame(feature_rows).set_index("date")

        # Build labels on the same price_data subset
        feat_price = price_data.loc[feat_df.index] if all(d in price_data.index for d in feat_df.index) \
                     else price_data.reindex(feat_df.index, method="ffill")
        all_labels = self._build_labels(feat_price, horizon=5)

        if progress_callback:
            progress_callback(0.42, "Starting walk-forward simulation…")

        # ── Step 2: Walk-forward with periodic retraining ─────────────────
        capital    = float(starting_capital)
        equity_pts = [{"date": feat_df.index[_WARMUP_BARS - 1], "equity": capital}]
        trade_rows: list[dict] = []
        open_trade: Optional[dict] = None   # max 1 open at a time

        from alan_trader.backtest.engine import bs_price as _bs_price
        _slip  = self.slippage_per_leg
        _comm  = self.commission_per_leg

        for i in range(_WARMUP_BARS, len(feat_df)):
            dt       = feat_df.index[i]
            feat_row = feat_df.iloc[i]
            spot     = float(feat_row.get("_spot", price_data.loc[dt, "close"]
                             if dt in price_data.index else feat_row.get("_spot", 0)))
            if spot <= 0:
                continue

            # ── Retrain model if needed ────────────────────────────────────
            since_warmup = i - _WARMUP_BARS
            if since_warmup % _RETRAIN_EVERY == 0:
                X_tr = feat_df.iloc[:i][self.FEATURE_COLS].values.astype(float)
                y_tr = all_labels.iloc[:i].values.astype(int)
                valid = y_tr >= 0
                if valid.sum() >= 30 and len(np.unique(y_tr[valid])) >= 2:
                    self._model = self._train_classifier(X_tr[valid], y_tr[valid])

            # ── Check open trade exit ──────────────────────────────────────
            if open_trade is not None:
                entry_ts  = pd.Timestamp(open_trade["entry_date"])
                days_held = (pd.Timestamp(dt) - entry_ts).days
                dte_rem   = max(0, open_trade["entry_dte"] - days_held)

                # Re-price with BS
                T_long  = max(dte_rem, 1) / 252.0
                T_short = max(dte_rem - 1, 1) / 252.0
                iv      = feat_row.get("stock_atm_iv", open_trade["entry_iv"]) / 100.0
                r       = _RISK_FREE

                if open_trade["trade_type"] == "bull_call_spread":
                    long_v  = _bs_price(spot, open_trade["long_k"],  T_long,  r, iv, "call")
                    short_v = _bs_price(spot, open_trade["short_k"], T_short, r, iv, "call")
                    current_val = (long_v - short_v) * 100 * open_trade["contracts"]
                else:
                    long_v  = _bs_price(spot, open_trade["long_k"],  T_long,  r, iv, "put")
                    short_v = _bs_price(spot, open_trade["short_k"], T_short, r, iv, "put")
                    current_val = (long_v - short_v) * 100 * open_trade["contracts"]

                debit = open_trade["debit"]
                max_profit = open_trade["max_profit"]
                pnl = current_val - debit

                profit_hit = current_val >= max_profit * 0.60
                loss_hit   = pnl <= -0.50 * abs(debit)
                time_hit   = dte_rem <= _HOLD_STOP_DTE

                if profit_hit or loss_hit or time_hit:
                    exit_reason = "profit" if profit_hit else ("loss" if loss_hit else "time")
                    net_pnl = pnl - _comm * open_trade["contracts"] * 2
                    capital += net_pnl
                    trade_rows.append({
                        "ticker":       ticker,
                        "entry_date":   open_trade["entry_date"],
                        "exit_date":    dt,
                        "trade_type":   open_trade["trade_type"],
                        "long_k":       open_trade["long_k"],
                        "short_k":      open_trade["short_k"],
                        "entry_dte":    open_trade["entry_dte"],
                        "confidence":   open_trade["confidence"],
                        "contracts":    open_trade["contracts"],
                        "debit":        round(debit, 2),
                        "pnl":          round(net_pnl, 2),
                        "exit_reason":  exit_reason,
                    })
                    open_trade = None

            # ── Predict and maybe enter ────────────────────────────────────
            if self._model is None or open_trade is not None:
                pass
            else:
                row_d = feat_row.to_dict()
                pred  = self.predict_direction(row_d)

                if pred["trade_type"] is not None:
                    iv     = feat_row.get("stock_atm_iv", 20.0) / 100.0
                    T      = self.dte_entry / 252.0
                    width  = spot * self.spread_width_pct
                    r      = _RISK_FREE

                    if pred["trade_type"] == "bull_call_spread":
                        long_k  = spot
                        short_k = spot + width
                        long_v  = _bs_price(spot, long_k,  T, r, iv, "call") + _slip
                        short_v = _bs_price(spot, short_k, T, r, iv, "call") - _slip
                        debit   = max(0.01, long_v - short_v) * 100
                        max_pft = (width - (long_v - short_v)) * 100
                    else:
                        long_k  = spot
                        short_k = spot - width
                        long_v  = _bs_price(spot, long_k,  T, r, iv, "put") + _slip
                        short_v = _bs_price(spot, short_k, T, r, iv, "put") - _slip
                        debit   = max(0.01, long_v - short_v) * 100
                        max_pft = (width - (long_v - short_v)) * 100

                    alloc     = capital * self.position_size_pct
                    contracts = max(1, int(alloc / max(debit, 1)))
                    cost      = debit * contracts + _comm * contracts * 2

                    if cost <= capital:
                        capital -= cost
                        open_trade = {
                            "entry_date":  dt,
                            "trade_type":  pred["trade_type"],
                            "long_k":      long_k,
                            "short_k":     short_k,
                            "entry_dte":   self.dte_entry,
                            "entry_iv":    feat_row.get("stock_atm_iv", 20.0),
                            "confidence":  pred["confidence"],
                            "contracts":   contracts,
                            "debit":       debit * contracts,
                            "max_profit":  max_pft * contracts,
                        }

            # MTM equity = cash + open trade current value
            mtm_val = 0.0
            if open_trade is not None:
                entry_ts  = pd.Timestamp(open_trade["entry_date"])
                days_held = max(0, (pd.Timestamp(dt) - entry_ts).days)
                dte_rem   = max(1, open_trade["entry_dte"] - days_held)
                iv        = feat_row.get("stock_atm_iv", 20.0) / 100.0
                T_l       = dte_rem / 252.0
                T_s       = max(dte_rem - 1, 1) / 252.0
                if open_trade["trade_type"] == "bull_call_spread":
                    lv = _bs_price(spot, open_trade["long_k"],  T_l, _RISK_FREE, iv, "call")
                    sv = _bs_price(spot, open_trade["short_k"], T_s, _RISK_FREE, iv, "call")
                else:
                    lv = _bs_price(spot, open_trade["long_k"],  T_l, _RISK_FREE, iv, "put")
                    sv = _bs_price(spot, open_trade["short_k"], T_s, _RISK_FREE, iv, "put")
                mtm_val = max(0.0, (lv - sv) * 100 * open_trade["contracts"])

            equity_pts.append({"date": dt, "equity": capital + mtm_val})

            if progress_callback and since_warmup % 20 == 0:
                progress_callback(0.42 + 0.50 * (since_warmup / max(1, len(feat_df) - _WARMUP_BARS)),
                                  f"Simulating bar {since_warmup}…")

        # ── Close any still-open trade at end ─────────────────────────────
        if open_trade is not None:
            trade_rows.append({
                "ticker":      ticker,
                "entry_date":  open_trade["entry_date"],
                "exit_date":   feat_df.index[-1],
                "trade_type":  open_trade["trade_type"],
                "long_k":      open_trade["long_k"],
                "short_k":     open_trade["short_k"],
                "entry_dte":   open_trade["entry_dte"],
                "confidence":  open_trade["confidence"],
                "contracts":   open_trade["contracts"],
                "debit":       round(open_trade["debit"], 2),
                "pnl":         0.0,
                "exit_reason": "end_of_data",
            })

        if progress_callback:
            progress_callback(0.95, "Computing metrics…")

        eq_df = pd.DataFrame(equity_pts).set_index("date")["equity"].sort_index()
        eq_df = eq_df[~eq_df.index.duplicated(keep="last")]
        returns = eq_df.pct_change().dropna()

        bench = None
        if len(price_data) >= 2:
            bench = price_data["close"].pct_change().reindex(returns.index).dropna()

        trades_df = pd.DataFrame(trade_rows) if trade_rows else pd.DataFrame(
            columns=["ticker","entry_date","exit_date","trade_type",
                     "pnl","contracts","debit","confidence","exit_reason"])

        metrics = compute_all_metrics(eq_df, trades_df if not trades_df.empty else None, bench)

        if progress_callback:
            progress_callback(1.0, "Done.")

        return BacktestResult(
            strategy_name = self.name,
            equity_curve  = eq_df,
            daily_returns = returns,
            trades        = trades_df,
            metrics       = metrics,
            params        = self.get_params(),
            extra         = {"model_meta": self._model_meta, "ticker": ticker},
        )
