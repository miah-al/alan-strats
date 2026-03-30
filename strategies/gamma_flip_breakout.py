"""
Gamma Flip Breakout Strategy.

THESIS
------
Dealer gamma exposure (GEX) creates price gravity.  When price is above the
GEX flip point, dealers are long gamma and dampen moves (sell rallies, buy
dips).  When price crosses BELOW the flip point, dealers become short gamma
and AMPLIFY moves (buy rallies, sell dips).

An XGBoost model trained on net GEX, distance to flip, and momentum detects
imminent breakouts caused by dealer hedging cascades.

GEX CALCULATION
---------------
  gex_contribution = gamma × open_interest × 100 × spot
  Call GEX:   positive (dealers long gamma on calls they sold)
  Put  GEX:   negative (dealers short gamma on puts they sold)
  Net  GEX:   sum(call_gex) + sum(put_gex)
  Flip level: strike where net GEX changes sign

TRADE STRUCTURE
---------------
Below flip (dist_to_flip < -flip_sensitivity%):
  Buy STRANGLE — long OTM call (0.30 delta) + long OTM put (0.30 delta), DTE=dte_entry
  Close: either leg doubles OR 7 DTE

Above flip (dist_to_flip > +flip_sensitivity%):
  Buy IRON CONDOR — sell straddle body + buy OTM wings
  Close: 50% credit collected OR 2× credit loss OR 7 DTE

Walk-forward: 150-bar warm-up, retrain every 45 bars.
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
NO_BREAKOUT  = 0
BREAKOUT     = 1

# ── Persistence ───────────────────────────────────────────────────────────────
_MODEL_DIR   = Path(__file__).parent.parent / "saved_models"
_MODEL_DIR.mkdir(exist_ok=True)

_WARMUP_BARS   = 150
_RETRAIN_EVERY = 45
_RISK_FREE     = 0.045
_HOLD_STOP_DTE = 7


class GammaFlipBreakoutStrategy(BaseStrategy):
    """
    XGBoost binary classifier trained on dealer GEX, distance to flip, and
    momentum.  Detects imminent volatility expansion caused by dealer hedging
    cascades, then trades a strangle (below flip) or iron condor (above flip).
    """

    name                 = "gamma_flip_breakout"
    display_name         = "Gamma Flip Breakout"
    strategy_type        = StrategyType.AI_DRIVEN
    status               = StrategyStatus.ACTIVE
    description          = (
        "XGBoost binary classifier trained on dealer GEX, distance to gamma-flip level, "
        "and price/vol momentum. Below flip: buys strangle (dealers amplify moves). "
        "Above flip: sells iron condor (dealers dampen moves). "
        "11 features across GEX structure, momentum, and macro context."
    )
    asset_class          = "equities_options"
    typical_holding_days = 14
    target_sharpe        = 1.4

    # ── Feature column order (must match training) ────────────────────────────
    FEATURE_COLS = [
        "stock_net_gex",
        "stock_net_gex_5d_change",
        "stock_dist_to_flip_pct",
        "stock_call_gex",
        "stock_put_gex",
        "stock_gex_ratio",
        "stock_5d_return",
        "stock_atr_14",
        "stock_volume_ratio",
        "vix",
        "spy_5d_return",
    ]

    def __init__(
        self,
        signal_threshold:  float = 55.0,   # % probability
        dte_entry:         int   = 21,
        position_size_pct: float = 2.0,    # % of capital
        flip_sensitivity:  float = 0.5,    # % distance threshold
        # XGBoost hyper-params
        max_depth:         int   = 3,
        n_estimators:      int   = 100,
        learning_rate:     float = 0.05,
        subsample:         float = 0.8,
        min_child_weight:  int   = 10,
        slippage_per_leg:  float = 0.05,
        commission_per_leg: float = 0.65,
    ):
        self.signal_threshold  = signal_threshold / 100.0
        self.dte_entry         = dte_entry
        self.position_size_pct = position_size_pct / 100.0
        self.flip_sensitivity  = flip_sensitivity / 100.0
        self.max_depth         = max_depth
        self.n_estimators      = n_estimators
        self.learning_rate     = learning_rate
        self.subsample         = subsample
        self.min_child_weight  = min_child_weight
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
            "dte_entry":         self.dte_entry,
            "position_size_pct": self.position_size_pct * 100,
            "flip_sensitivity":  self.flip_sensitivity * 100,
            "n_estimators":      self.n_estimators,
            "max_depth":         self.max_depth,
            "learning_rate":     self.learning_rate,
        }

    def get_backtest_ui_params(self) -> list[dict]:
        return [
            {"key": "signal_threshold",  "label": "Signal threshold (%)",     "type": "int",   "default": 55,  "min": 45,  "max": 70},
            {"key": "dte_entry",         "label": "DTE at entry",              "type": "int",   "default": 21,  "min": 14,  "max": 30},
            {"key": "position_size_pct", "label": "Position size (%)",         "type": "int",   "default": 2,   "min": 1,   "max": 5},
            {"key": "flip_sensitivity",  "label": "Flip sensitivity (% dist)", "type": "float", "default": 0.5, "min": 0.1, "max": 2.0, "step": 0.1},
            {"key": "n_estimators",      "label": "XGB trees",                 "type": "int",   "default": 100, "min": 50,  "max": 500},
            {"key": "max_depth",         "label": "XGB max depth",             "type": "int",   "default": 3,   "min": 2,   "max": 6},
        ]

    def is_trainable(self) -> bool:
        return True

    # ═════════════════════════════════════════════════════════════════════════
    # GEX helpers
    # ═════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _compute_gex(snap: pd.DataFrame, spot: float) -> dict:
        """
        Compute GEX metrics from an option snapshot DataFrame.

        Required columns: gamma (or Gamma), open_interest (or OpenInterest),
                          option_type / OptionType / type / contract_type,
                          strike / StrikePrice.

        Returns dict with keys:
          net_gex, call_gex, put_gex, gex_ratio, flip_level, dist_to_flip_pct
        Or raises ValueError if required columns are absent.
        """
        if snap is None or snap.empty:
            raise ValueError("option_snapshots is empty — cannot compute GEX")

        snap = snap.copy()

        # -- Normalise column names -----------------------------------------
        gamma_col = None
        for c in ("Gamma", "gamma"):
            if c in snap.columns:
                gamma_col = c
                break

        oi_col = None
        for c in ("OpenInterest", "open_interest", "oi"):
            if c in snap.columns:
                oi_col = c
                break

        strike_col = None
        for c in ("StrikePrice", "strike_price", "strike", "Strike"):
            if c in snap.columns:
                strike_col = c
                break

        type_col = None
        for c in ("OptionType", "option_type", "type", "contract_type"):
            if c in snap.columns:
                type_col = c
                break

        if gamma_col is None or oi_col is None or strike_col is None or type_col is None:
            raise ValueError(
                f"option_snapshots is missing required columns for GEX. "
                f"Need: gamma, open_interest, strike, option_type. "
                f"Found: {list(snap.columns)}"
            )

        snap[gamma_col]  = pd.to_numeric(snap[gamma_col],  errors="coerce").fillna(0.0)
        snap[oi_col]     = pd.to_numeric(snap[oi_col],     errors="coerce").fillna(0.0)
        snap[strike_col] = pd.to_numeric(snap[strike_col], errors="coerce").fillna(0.0)

        # -- Per-option GEX contribution ------------------------------------
        gex_contrib = snap[gamma_col] * snap[oi_col] * 100 * spot

        is_call = snap[type_col].str.lower().str.startswith("c")

        call_gex_vals = gex_contrib[is_call]
        put_gex_vals  = -gex_contrib[~is_call]   # put GEX is negative by convention

        call_gex = float(call_gex_vals.sum())
        put_gex  = float(put_gex_vals.sum())     # stored as absolute value (positive number)
        net_gex  = call_gex - put_gex

        gex_ratio = float(call_gex / (call_gex + put_gex + 1e-12))

        # Normalise net GEX by spot²
        net_gex_norm = net_gex / (spot ** 2 + 1e-12)

        # -- GEX flip level (strike where cumulative GEX changes sign) -------
        strikes = snap[strike_col].unique()
        strikes = np.sort(strikes[strikes > 0])
        flip_level = spot  # default: no flip detected

        if len(strikes) >= 2:
            # Accumulate net GEX strike by strike (sorted ascending)
            strike_gex = {}
            for _, row in snap.iterrows():
                k     = float(row[strike_col])
                g     = float(row[gamma_col]) * float(row[oi_col]) * 100 * spot
                if str(row[type_col]).lower().startswith("p"):
                    g = -g
                strike_gex[k] = strike_gex.get(k, 0.0) + g

            cum_gex = 0.0
            prev_k, prev_cum = None, 0.0
            for k in sorted(strike_gex.keys()):
                cum_gex += strike_gex[k]
                if prev_k is not None and prev_cum * cum_gex < 0:
                    # sign change — linear interpolation
                    frac = abs(prev_cum) / (abs(prev_cum) + abs(cum_gex) + 1e-12)
                    flip_level = prev_k + frac * (k - prev_k)
                    break
                prev_k, prev_cum = k, cum_gex

        dist_to_flip_pct = float((spot - flip_level) / (spot + 1e-12))

        return {
            "net_gex":          net_gex_norm,
            "call_gex":         call_gex,
            "put_gex":          put_gex,
            "gex_ratio":        gex_ratio,
            "flip_level":       flip_level,
            "dist_to_flip_pct": dist_to_flip_pct,
        }

    def _build_feature_row(
        self,
        snap_today:      pd.DataFrame,
        price_df:        pd.DataFrame,
        net_gex_history: list,          # historical net_gex values for 5d change
        vix_series:      pd.Series,
        spy_price_df:    Optional[pd.DataFrame] = None,
    ) -> Optional[dict]:
        """Compute one feature row. Returns None if data insufficient."""
        if price_df is None or len(price_df) < 20:
            return None
        if vix_series is None or vix_series.empty:
            return None

        spot = float(price_df["close"].iloc[-1])
        if spot <= 0:
            return None

        # GEX
        try:
            gex = self._compute_gex(snap_today, spot)
        except ValueError as e:
            logger.debug(f"GEX computation failed: {e}")
            return None

        net_gex_5d = 0.0
        if len(net_gex_history) >= 5:
            net_gex_5d = gex["net_gex"] - net_gex_history[-5]

        # Price momentum
        closes = price_df["close"].astype(float)
        if len(closes) < 6:
            return None
        ret_5d = float((closes.iloc[-1] - closes.iloc[-6]) / closes.iloc[-6])

        # ATR-14 normalised by spot
        highs  = price_df["high"].astype(float)
        lows   = price_df["low"].astype(float)
        tr_vals = []
        for j in range(1, min(15, len(closes))):
            tr = max(
                float(highs.iloc[-j]) - float(lows.iloc[-j]),
                abs(float(highs.iloc[-j]) - float(closes.iloc[-j-1])),
                abs(float(lows.iloc[-j])  - float(closes.iloc[-j-1])),
            )
            tr_vals.append(tr)
        atr14 = float(np.mean(tr_vals)) / spot if tr_vals else 0.01

        # Volume ratio
        vol_ratio = 1.0
        if "volume" in price_df.columns:
            vols = pd.to_numeric(price_df["volume"], errors="coerce").dropna()
            if len(vols) >= 2:
                avg20 = float(vols.iloc[-min(20, len(vols)):-1].mean())
                today = float(vols.iloc[-1])
                if avg20 > 0:
                    vol_ratio = today / avg20

        # VIX
        vix_val = float(vix_series.iloc[-1])

        # SPY 5d return
        spy_ret = 0.0
        if spy_price_df is not None and len(spy_price_df) >= 6:
            sc = spy_price_df["close"].astype(float)
            spy_ret = float((sc.iloc[-1] - sc.iloc[-6]) / sc.iloc[-6])

        return {
            "stock_net_gex":          gex["net_gex"],
            "stock_net_gex_5d_change": net_gex_5d,
            "stock_dist_to_flip_pct": gex["dist_to_flip_pct"],
            "stock_call_gex":         gex["call_gex"],
            "stock_put_gex":          gex["put_gex"],
            "stock_gex_ratio":        gex["gex_ratio"],
            "stock_5d_return":        ret_5d,
            "stock_atr_14":           atr14,
            "stock_volume_ratio":     vol_ratio,
            "vix":                    vix_val,
            "spy_5d_return":          spy_ret,
            # extras for trade simulation
            "_spot":                  spot,
            "_atr14":                 atr14,
            "_dist_to_flip_pct":      gex["dist_to_flip_pct"],
        }

    # ═════════════════════════════════════════════════════════════════════════
    # Label construction
    # ═════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _build_labels(price_df: pd.DataFrame, atr_series: pd.Series,
                      horizon: int = 5) -> pd.Series:
        """
        BREAKOUT label = 1 if |5d return| > 1.5 × ATR_14 (as % of spot).
        """
        closes = price_df["close"].astype(float)
        n      = len(closes)
        labels = np.full(n, NO_BREAKOUT, dtype=int)
        for i in range(n - horizon):
            ret  = abs(float(closes.iloc[i + horizon]) - float(closes.iloc[i])) / float(closes.iloc[i])
            atr  = float(atr_series.iloc[i]) if i < len(atr_series) else 0.01
            if ret > 1.5 * atr:
                labels[i] = BREAKOUT
        labels[-horizon:] = -1
        return pd.Series(labels, index=price_df.index, name="label")

    # ═════════════════════════════════════════════════════════════════════════
    # XGBoost classifier
    # ═════════════════════════════════════════════════════════════════════════

    def _get_classifier(self):
        try:
            import xgboost as xgb
            return xgb.XGBClassifier(
                n_estimators     = self.n_estimators,
                max_depth        = self.max_depth,
                learning_rate    = self.learning_rate,
                subsample        = self.subsample,
                min_child_weight = self.min_child_weight,
                use_label_encoder= False,
                eval_metric      = "logloss",
                verbosity        = 0,
                n_jobs           = -1,
            )
        except ImportError:
            logger.warning("xgboost not installed — falling back to sklearn GradientBoostingClassifier")
            from sklearn.ensemble import GradientBoostingClassifier
            return GradientBoostingClassifier(
                n_estimators  = self.n_estimators,
                max_depth     = self.max_depth,
                learning_rate = self.learning_rate,
                subsample     = self.subsample,
            )

    def _train_classifier(self, X: np.ndarray, y: np.ndarray):
        from sklearn.utils.class_weight import compute_class_weight
        classes = np.unique(y)
        weights = compute_class_weight("balanced", classes=classes, y=y)
        sw      = np.array([weights[np.searchsorted(classes, yi)] for yi in y])
        clf = self._get_classifier()
        try:
            clf.fit(X, y, sample_weight=sw)
        except (TypeError, ValueError):
            try:
                clf.fit(X, y)
            except Exception as e:
                logger.warning(f"Classifier fit error: {e}")
                from sklearn.ensemble import GradientBoostingClassifier
                clf = GradientBoostingClassifier(n_estimators=self.n_estimators,
                                                 max_depth=self.max_depth)
                clf.fit(X, y)
        return clf

    # ═════════════════════════════════════════════════════════════════════════
    # Save / load
    # ═════════════════════════════════════════════════════════════════════════

    def save_model(self, ticker: str = "default") -> str:
        path = _MODEL_DIR / f"gamma_flip_breakout_{ticker}.pkl"
        with open(path, "wb") as f:
            pickle.dump({"model": self._model, "meta": self._model_meta}, f)
        return str(path)

    def load_model(self, ticker: str = "default") -> bool:
        path = _MODEL_DIR / f"gamma_flip_breakout_{ticker}.pkl"
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

    def predict_breakout(self, feature_row: dict) -> dict:
        """
        Returns {signal, confidence, trade_type}.
        trade_type: 'strangle' | 'iron_condor' | None
        """
        if self._model is None:
            return {"signal": "NO_BREAKOUT", "confidence": 0.0, "trade_type": None}

        X = np.array([[feature_row.get(c, 0.0) for c in self.FEATURE_COLS]], dtype=float)
        pred = int(self._model.predict(X)[0])
        try:
            proba = self._model.predict_proba(X)[0]
            conf  = float(proba[pred])
        except Exception:
            conf  = 1.0

        trade_type = None
        if pred == BREAKOUT and conf >= self.signal_threshold:
            dist = feature_row.get("stock_dist_to_flip_pct",
                                   feature_row.get("_dist_to_flip_pct", 0.0))
            if dist < -self.flip_sensitivity:
                trade_type = "strangle"
            elif dist > self.flip_sensitivity:
                trade_type = "iron_condor"

        return {
            "signal":     "BREAKOUT" if pred == BREAKOUT else "NO_BREAKOUT",
            "label":      pred,
            "confidence": conf,
            "trade_type": trade_type,
        }

    def generate_signal(self, market_snapshot: dict) -> SignalResult:
        result = self.predict_breakout(market_snapshot)
        conf   = result["confidence"]
        tt     = result["trade_type"]
        if tt == "strangle":
            signal = "BUY"
        elif tt == "iron_condor":
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
          option_snapshots : DataFrame — with gamma, open_interest, option_type, strike columns
          vix              : DataFrame — date-indexed, "close" column
          rate10y          : DataFrame — date-indexed, "close" column (accepted but unused)
        """
        opts = auxiliary_data.get("option_snapshots")
        if opts is None or (isinstance(opts, pd.DataFrame) and opts.empty):
            raise ValueError(
                "gamma_flip_breakout: option_snapshots is required but was empty or missing. "
                "Please sync options data for this ticker before running the backtest."
            )

        vix_df  = auxiliary_data.get("vix")
        spy_aux = auxiliary_data.get("spy_price")

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

        if vix_df is not None and not isinstance(vix_df.index, pd.DatetimeIndex):
            try:
                vix_df = vix_df.set_index(pd.to_datetime(vix_df.index))
            except Exception:
                vix_df = None

        snap_dates  = sorted(opts[date_col].dt.normalize().unique())
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

        # ── Step 1: Build feature matrix ───────────────────────────────────
        if progress_callback:
            progress_callback(0.05, "Building GEX feature matrix…")

        net_gex_history: list[float] = []
        atr14_history:   list[float] = []
        feature_rows:    list[dict]  = []

        for i, snap_dt in enumerate(snap_dates):
            ts = pd.Timestamp(snap_dt)
            if ts not in price_data.index:
                continue

            snap_today = opts[opts[date_col].dt.normalize() == ts].copy()
            spot = float(price_data.loc[ts, "close"])
            # Inject spot for any moneyness-based fallbacks
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

            try:
                row = self._build_feature_row(
                    snap_today      = snap_today,
                    price_df        = px_to,
                    net_gex_history = net_gex_history,
                    vix_series      = vix_s,
                    spy_price_df    = spy_px,
                )
            except Exception as e:
                logger.debug(f"Feature build failed on {ts}: {e}")
                row = None

            if row is None:
                continue

            row["date"] = ts
            feature_rows.append(row)
            net_gex_history.append(row["stock_net_gex"])
            atr14_history.append(row["stock_atr_14"])

            if progress_callback and i % 20 == 0:
                progress_callback(0.05 + 0.35 * (i / len(snap_dates)),
                                  f"Building features {i}/{len(snap_dates)}…")

        if len(feature_rows) < _WARMUP_BARS + 5:
            return BacktestResult(
                strategy_name = self.name,
                equity_curve  = pd.Series(dtype=float),
                daily_returns = pd.Series(dtype=float),
                trades        = pd.DataFrame(),
                metrics       = {"error": f"Only {len(feature_rows)} valid GEX feature rows after filtering"},
            )

        feat_df   = pd.DataFrame(feature_rows).set_index("date")
        atr_series = pd.Series(atr14_history, index=feat_df.index)

        feat_price = price_data.loc[feat_df.index] if all(d in price_data.index for d in feat_df.index) \
                     else price_data.reindex(feat_df.index, method="ffill")
        all_labels = self._build_labels(feat_price, atr_series, horizon=5)

        if progress_callback:
            progress_callback(0.42, "Starting walk-forward simulation…")

        # ── Step 2: Walk-forward with retraining ───────────────────────────
        from alan_trader.backtest.engine import bs_price as _bs_price
        from scipy.stats import norm as _norm

        capital    = float(starting_capital)
        equity_pts = [{"date": feat_df.index[_WARMUP_BARS - 1], "equity": capital}]
        trade_rows: list[dict] = []
        open_trade: Optional[dict] = None
        _slip = self.slippage_per_leg
        _comm = self.commission_per_leg

        def _find_delta_strike(spot: float, T: float, iv: float, target_delta: float,
                               opt_type: str) -> float:
            """Approximate strike for a target delta using BS inversion."""
            if T <= 0 or iv <= 0:
                return spot
            from scipy.optimize import brentq
            def obj(K):
                if K <= 0:
                    return 1.0
                d1 = (math.log(spot / K) + (_RISK_FREE + 0.5 * iv**2) * T) / (iv * math.sqrt(T))
                delta = float(_norm.cdf(d1)) if opt_type == "call" else float(_norm.cdf(d1) - 1.0)
                return abs(delta) - target_delta
            try:
                return float(brentq(obj, spot * 0.50, spot * 1.50, xtol=0.01, maxiter=50))
            except Exception:
                move = iv * math.sqrt(T) * spot
                return spot + move if opt_type == "call" else spot - move

        for i in range(_WARMUP_BARS, len(feat_df)):
            dt       = feat_df.index[i]
            feat_row = feat_df.iloc[i]
            spot     = float(feat_row.get("_spot", price_data.loc[dt, "close"]
                             if dt in price_data.index else feat_row.get("_spot", 0)))
            if spot <= 0:
                continue

            since_warmup = i - _WARMUP_BARS

            # ── Retrain model ──────────────────────────────────────────────
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
                iv        = feat_row.get("stock_atm_iv", open_trade.get("entry_iv", 0.20))
                # Fallback: use ATR as IV proxy if atm_iv not in features
                if iv <= 0:
                    iv = feat_row.get("stock_atr_14", 0.01) * math.sqrt(252)
                T = max(dte_rem, 1) / 252.0

                closed     = False
                exit_reason = "time"
                net_pnl    = 0.0

                if open_trade["trade_type"] == "strangle":
                    call_k = open_trade["call_k"]
                    put_k  = open_trade["put_k"]
                    call_v = _bs_price(spot, call_k, T, _RISK_FREE, iv, "call")
                    put_v  = _bs_price(spot, put_k,  T, _RISK_FREE, iv, "put")
                    curr_val = (call_v + put_v) * 100 * open_trade["contracts"]
                    cost     = open_trade["cost"]
                    pnl      = curr_val - cost
                    doubled  = curr_val >= cost * 2.0   # either leg doubles
                    if doubled or dte_rem <= _HOLD_STOP_DTE:
                        exit_reason = "doubled" if doubled else "time"
                        net_pnl = pnl - _comm * open_trade["contracts"] * 2
                        capital += net_pnl
                        closed = True

                elif open_trade["trade_type"] == "iron_condor":
                    # Iron condor: sell body (short call + short put near ATM),
                    # buy wings. P&L = credit_received - current_cost_to_close
                    body_call_k = open_trade["body_call_k"]
                    body_put_k  = open_trade["body_put_k"]
                    wing_call_k = open_trade["wing_call_k"]
                    wing_put_k  = open_trade["wing_put_k"]

                    bc_v = _bs_price(spot, body_call_k, T, _RISK_FREE, iv, "call")
                    bp_v = _bs_price(spot, body_put_k,  T, _RISK_FREE, iv, "put")
                    wc_v = _bs_price(spot, wing_call_k, T, _RISK_FREE, iv, "call")
                    wp_v = _bs_price(spot, wing_put_k,  T, _RISK_FREE, iv, "put")

                    # Current cost to close condor (buy back body legs, sell wings)
                    close_cost = ((bc_v + _slip) + (bp_v + _slip)
                                  - (wc_v - _slip) - (wp_v - _slip)) * 100
                    credit    = open_trade["credit"]   # per-share total (×100 already stored)
                    pnl       = credit - close_cost * open_trade["contracts"]
                    profit_hit = pnl >= 0.50 * credit
                    loss_hit   = pnl <= -2.0 * credit
                    if profit_hit or loss_hit or dte_rem <= _HOLD_STOP_DTE:
                        exit_reason = "profit" if profit_hit else ("loss" if loss_hit else "time")
                        net_pnl = pnl - _comm * open_trade["contracts"] * 4
                        capital += net_pnl
                        closed = True

                if closed:
                    trade_rows.append({
                        "ticker":      ticker,
                        "entry_date":  open_trade["entry_date"],
                        "exit_date":   dt,
                        "trade_type":  open_trade["trade_type"],
                        "entry_dte":   open_trade["entry_dte"],
                        "confidence":  open_trade["confidence"],
                        "contracts":   open_trade["contracts"],
                        "cost":        round(open_trade["cost"], 2),
                        "pnl":         round(net_pnl, 2),
                        "exit_reason": exit_reason,
                    })
                    open_trade = None

            # ── Predict and maybe enter ────────────────────────────────────
            if self._model is None or open_trade is not None:
                pass
            else:
                row_d = feat_row.to_dict()
                pred  = self.predict_breakout(row_d)

                if pred["trade_type"] is not None:
                    iv = feat_row.get("stock_atr_14", 0.01) * math.sqrt(252)
                    T  = self.dte_entry / 252.0

                    if pred["trade_type"] == "strangle":
                        call_k = _find_delta_strike(spot, T, iv, 0.30, "call")
                        put_k  = _find_delta_strike(spot, T, iv, 0.30, "put")
                        call_v = _bs_price(spot, call_k, T, _RISK_FREE, iv, "call") + _slip
                        put_v  = _bs_price(spot, put_k,  T, _RISK_FREE, iv, "put")  + _slip
                        cost_per = (call_v + put_v) * 100
                        alloc    = capital * self.position_size_pct
                        contracts = max(1, int(alloc / max(cost_per, 1)))
                        total_cost = cost_per * contracts + _comm * contracts * 2
                        if total_cost <= capital:
                            capital -= total_cost
                            open_trade = {
                                "entry_date": dt,
                                "trade_type": "strangle",
                                "call_k":     call_k,
                                "put_k":      put_k,
                                "entry_dte":  self.dte_entry,
                                "entry_iv":   iv,
                                "confidence": pred["confidence"],
                                "contracts":  contracts,
                                "cost":       total_cost,
                            }

                    elif pred["trade_type"] == "iron_condor":
                        # Short body ≈ 0.35 delta; wings ≈ 0.10 delta
                        sc_k = _find_delta_strike(spot, T, iv, 0.35, "call")
                        sp_k = _find_delta_strike(spot, T, iv, 0.35, "put")
                        wc_k = _find_delta_strike(spot, T, iv, 0.10, "call")
                        wp_k = _find_delta_strike(spot, T, iv, 0.10, "put")

                        sc_v = _bs_price(spot, sc_k, T, _RISK_FREE, iv, "call") - _slip
                        sp_v = _bs_price(spot, sp_k, T, _RISK_FREE, iv, "put")  - _slip
                        wc_v = _bs_price(spot, wc_k, T, _RISK_FREE, iv, "call") + _slip
                        wp_v = _bs_price(spot, wp_k, T, _RISK_FREE, iv, "put")  + _slip
                        credit_per = max(0.01, (sc_v + sp_v - wc_v - wp_v) * 100)

                        alloc    = capital * self.position_size_pct
                        # Max loss = wing width − credit; use wing width as sizing basis
                        wing_w   = (sc_k - wc_k + wp_k - sp_k) / 2 * 100
                        contracts = max(1, int(alloc / max(wing_w, 1)))
                        max_loss  = (wing_w - credit_per) * contracts
                        if max_loss <= capital:
                            capital -= max_loss   # post margin for max loss
                            open_trade = {
                                "entry_date":  dt,
                                "trade_type":  "iron_condor",
                                "body_call_k": sc_k,
                                "body_put_k":  sp_k,
                                "wing_call_k": wc_k,
                                "wing_put_k":  wp_k,
                                "entry_dte":   self.dte_entry,
                                "entry_iv":    iv,
                                "confidence":  pred["confidence"],
                                "contracts":   contracts,
                                "cost":        max_loss,
                                "credit":      credit_per * contracts,
                            }

            # MTM equity
            mtm_val = 0.0
            if open_trade is not None:
                entry_ts  = pd.Timestamp(open_trade["entry_date"])
                days_held = max(0, (pd.Timestamp(dt) - entry_ts).days)
                dte_rem   = max(1, open_trade["entry_dte"] - days_held)
                iv_mtm    = feat_row.get("stock_atr_14", 0.01) * math.sqrt(252)
                T_mtm     = dte_rem / 252.0

                if open_trade["trade_type"] == "strangle":
                    cv = _bs_price(spot, open_trade["call_k"], T_mtm, _RISK_FREE, iv_mtm, "call")
                    pv = _bs_price(spot, open_trade["put_k"],  T_mtm, _RISK_FREE, iv_mtm, "put")
                    mtm_val = max(0.0, (cv + pv) * 100 * open_trade["contracts"])
                elif open_trade["trade_type"] == "iron_condor":
                    bc = _bs_price(spot, open_trade["body_call_k"], T_mtm, _RISK_FREE, iv_mtm, "call")
                    bp = _bs_price(spot, open_trade["body_put_k"],  T_mtm, _RISK_FREE, iv_mtm, "put")
                    wc = _bs_price(spot, open_trade["wing_call_k"], T_mtm, _RISK_FREE, iv_mtm, "call")
                    wp = _bs_price(spot, open_trade["wing_put_k"],  T_mtm, _RISK_FREE, iv_mtm, "put")
                    close_cost = (bc + bp - wc - wp) * 100 * open_trade["contracts"]
                    mtm_val = max(0.0, open_trade["credit"] - close_cost)

            equity_pts.append({"date": dt, "equity": capital + mtm_val})

            if progress_callback and since_warmup % 20 == 0:
                progress_callback(
                    0.42 + 0.50 * (since_warmup / max(1, len(feat_df) - _WARMUP_BARS)),
                    f"Simulating bar {since_warmup}…"
                )

        # ── Close any still-open trade at end ─────────────────────────────
        if open_trade is not None:
            trade_rows.append({
                "ticker":      ticker,
                "entry_date":  open_trade["entry_date"],
                "exit_date":   feat_df.index[-1],
                "trade_type":  open_trade["trade_type"],
                "entry_dte":   open_trade["entry_dte"],
                "confidence":  open_trade["confidence"],
                "contracts":   open_trade["contracts"],
                "cost":        round(open_trade["cost"], 2),
                "pnl":         0.0,
                "exit_reason": "end_of_data",
            })

        if progress_callback:
            progress_callback(0.95, "Computing metrics…")

        eq_df   = pd.DataFrame(equity_pts).set_index("date")["equity"].sort_index()
        eq_df   = eq_df[~eq_df.index.duplicated(keep="last")]
        returns = eq_df.pct_change().dropna()

        bench = None
        if len(price_data) >= 2:
            bench = price_data["close"].pct_change().reindex(returns.index).dropna()

        trades_df = pd.DataFrame(trade_rows) if trade_rows else pd.DataFrame(
            columns=["ticker","entry_date","exit_date","trade_type",
                     "pnl","contracts","cost","confidence","exit_reason"])

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
