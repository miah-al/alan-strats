"""
Vol Term Structure Regime Strategy.

THESIS
------
The shape of a stock's IV term structure (near-term vs longer-dated implied vol)
is a leading indicator of upcoming volatility events and premium harvest windows.

  Contango  (back IV > front IV, slope < 0): IV tends to compress.
      → Premium sellers win → Bull Put Spread (credit)

  Backwardation (front IV > back IV, slope > 0): vol event expected.
      → Premium buyers win → Long Straddle (debit)

An LSTM trained on a 20-bar sequence of term-structure shape, VRP, and macro
context classifies the current regime (COMPRESS / FLAT / EXPAND) and sizes
positions accordingly.

TRADE STRUCTURES
----------------
Regime 0 (COMPRESS):  Bull Put Spread — sell 0.20-delta put, buy further OTM put
                       21-30 DTE. Credit trade; profits as IV compresses.
Regime 1 (FLAT):      No trade.
Regime 2 (EXPAND):    Long Straddle — ATM call + ATM put, 21-30 DTE.
                       Debit trade; profits as IV/spot moves expand.

FEATURES (10)
-------------
1  stock_front_iv         — median ATM IV, DTE 7–21
2  stock_back_iv          — median ATM IV, DTE 22–60
3  stock_term_slope       — front_iv − back_iv (+ = backwardation)
4  stock_term_slope_5d_change — change in slope over last 5 bars
5  stock_vrp              — front_iv/100 − 20d realized vol
6  stock_ivr              — IV rank of front_iv over 52-week rolling window
7  vix                    — VIX close
8  vix_term_slope         — VIX term-structure proxy
9  yield_curve_2y10y      — 10y − 2y spread (or just 10y if 2y unavailable)
10 spy_20d_realized_vol   — 20d realized vol of price_data (benchmark)

LABELS
------
Forward 10-day relative IV change → 3 classes:
  0 COMPRESS: < -5%
  1 FLAT:     -5% to +5%
  2 EXPAND:   > +5%
"""

from __future__ import annotations

import logging
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

# ── Labels ─────────────────────────────────────────────────────────────────────
COMPRESS = 0
FLAT     = 1
EXPAND   = 2
LABEL_NAMES = {COMPRESS: "COMPRESS", FLAT: "FLAT", EXPAND: "EXPAND"}

# ── Model persistence dir ──────────────────────────────────────────────────────
_MODEL_DIR = Path(__file__).parent.parent / "saved_models"
_MODEL_DIR.mkdir(exist_ok=True)


class VolTermStructureRegimeStrategy(BaseStrategy):
    """
    LSTM classifies IV term structure regime (contango / backwardation) to
    time premium selling vs buying. Trades bull put spreads in contango,
    long straddles in backwardation.
    """

    name                 = "vol_term_structure_regime"
    display_name         = "Vol Term Structure Regime"
    strategy_type        = StrategyType.AI_DRIVEN
    status               = StrategyStatus.ACTIVE
    description          = (
        "LSTM classifies IV term structure regime (contango/backwardation) to time "
        "premium selling vs buying. Trades bull put spreads in contango, long straddles "
        "in backwardation."
    )
    asset_class          = "equities_options"
    typical_holding_days = 14
    target_sharpe        = 1.3

    # ── Feature column order (must match ModelTrainer) ─────────────────────────
    feature_cols = [
        "stock_front_iv",
        "stock_back_iv",
        "stock_term_slope",
        "stock_term_slope_5d_change",
        "stock_vrp",
        "stock_ivr",
        "vix",
        "vix_term_slope",
        "yield_curve_2y10y",
        "spy_20d_realized_vol",
    ]

    # ── LSTM / walk-forward hyperparams ───────────────────────────────────────
    SEQ_LEN      = 20    # lookback window for LSTM
    HIDDEN_SIZE  = 32
    NUM_LAYERS   = 1
    DROPOUT      = 0.2
    WARMUP_BARS  = 200   # minimum bars before first training
    RETRAIN_EVERY = 60   # retrain every N bars (walk-forward)

    def __init__(
        self,
        signal_threshold:    float = 0.55,  # min model confidence to trade
        dte_entry:           int   = 21,    # target DTE at entry
        position_size_pct:   float = 0.03,  # capital % per trade
        regime_reeval_bars:  int   = 10,    # re-evaluate regime every N bars
        slippage_per_leg:    float = 0.05,  # bid-ask half-spread per leg ($)
        commission_per_leg:  float = 0.65,  # commission per contract per leg
        starting_capital:    float = 100_000.0,
    ):
        self.signal_threshold   = signal_threshold
        self.dte_entry          = dte_entry
        self.position_size_pct  = position_size_pct
        self.regime_reeval_bars = regime_reeval_bars
        self.slippage_per_leg   = slippage_per_leg
        self.commission_per_leg = commission_per_leg
        self.starting_capital   = starting_capital

        self._trainer       = None   # ModelTrainer instance (fitted)
        self._train_history = {}

    # ═══════════════════════════════════════════════════════════════════════════
    # BaseStrategy interface
    # ═══════════════════════════════════════════════════════════════════════════

    def get_params(self) -> dict:
        return {
            "signal_threshold":   self.signal_threshold,
            "dte_entry":          self.dte_entry,
            "position_size_pct":  self.position_size_pct,
            "regime_reeval_bars": self.regime_reeval_bars,
            "seq_len":            self.SEQ_LEN,
            "hidden_size":        self.HIDDEN_SIZE,
            "num_layers":         self.NUM_LAYERS,
            "dropout":            self.DROPOUT,
            "warmup_bars":        self.WARMUP_BARS,
            "retrain_every":      self.RETRAIN_EVERY,
        }

    def get_backtest_ui_params(self) -> list[dict]:
        return [
            {
                "key": "signal_threshold",
                "label": "Signal threshold (%)",
                "type": "slider",
                "default": 55,
                "min": 45,
                "max": 75,
                "step": 1,
                "col": 0,
                "row": 0,
            },
            {
                "key": "dte_entry",
                "label": "DTE at entry",
                "type": "slider",
                "default": 21,
                "min": 14,
                "max": 30,
                "step": 1,
                "col": 1,
                "row": 0,
            },
            {
                "key": "position_size_pct",
                "label": "Position size %",
                "type": "slider",
                "default": 3,
                "min": 1,
                "max": 5,
                "step": 1,
                "col": 2,
                "row": 0,
            },
            {
                "key": "regime_reeval_bars",
                "label": "Regime re-eval bars",
                "type": "slider",
                "default": 10,
                "min": 5,
                "max": 20,
                "step": 1,
                "col": 0,
                "row": 1,
            },
        ]

    def is_trainable(self) -> bool:
        return True

    def fit(self, features: np.ndarray, labels: np.ndarray) -> dict:
        """Train the LSTM via ModelTrainer (BaseStrategy override)."""
        from alan_trader.model.trainer import ModelTrainer
        self._trainer = ModelTrainer(
            feature_cols=self.feature_cols,
            hidden_size=self.HIDDEN_SIZE,
            num_layers=self.NUM_LAYERS,
            dropout=self.DROPOUT,
            seq_len=self.SEQ_LEN,
        )
        self._train_history = self._trainer.fit(features, labels)
        return self._train_history

    def generate_signal(self, market_snapshot: dict) -> SignalResult:
        """Live inference — requires a pre-trained _trainer."""
        if self._trainer is None:
            return SignalResult(self.name, "HOLD", 0.0, 0.0,
                                metadata={"reason": "model not trained"})
        features_df = market_snapshot.get("features_df")
        if features_df is None or len(features_df) < self.SEQ_LEN:
            return SignalResult(self.name, "HOLD", 0.0, 0.0,
                                metadata={"reason": "insufficient features"})
        avail = [c for c in self.feature_cols if c in features_df.columns]
        try:
            proba = self._trainer.predict(features_df[avail].values)
        except Exception as e:
            return SignalResult(self.name, "HOLD", 0.0, 0.0,
                                metadata={"reason": str(e)})
        cls  = int(np.argmax(proba))
        conf = float(proba[cls])
        signal_map = {COMPRESS: "SELL", FLAT: "HOLD", EXPAND: "BUY"}
        signal = "HOLD" if conf < self.signal_threshold else signal_map[cls]
        return SignalResult(
            strategy_name     = self.name,
            signal            = signal,
            confidence        = conf,
            position_size_pct = self.position_size_pct * conf if signal != "HOLD" else 0.0,
            metadata          = {"proba": proba.tolist(), "class": cls,
                                 "regime": LABEL_NAMES[cls]},
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # Feature engineering
    # ═══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _compute_realized_vol(price_series: pd.Series, window: int = 20) -> Optional[float]:
        """Annualised realised vol from log returns over last `window` bars."""
        if len(price_series) < window + 1:
            return None
        log_ret = np.log(price_series / price_series.shift(1)).dropna()
        if len(log_ret) < window:
            return None
        return float(log_ret.iloc[-window:].std() * np.sqrt(252))

    @staticmethod
    def _ivr(current_iv: float, iv_series: pd.Series) -> float:
        """IV rank: position within the 52-week rolling range."""
        if len(iv_series) < 2:
            return 0.5
        lo = iv_series.min()
        hi = iv_series.max()
        if hi == lo:
            return 0.5
        return float(np.clip((current_iv - lo) / (hi - lo), 0.0, 1.0))

    def _build_feature_row(
        self,
        date,
        snap_today: pd.DataFrame,   # option_snapshots filtered to this date
        price_slice: pd.DataFrame,  # price_data up to and including this date
        vix_series: pd.Series,      # VIX closes up to this date
        front_iv_history: pd.Series,
        aux: dict,
    ) -> Optional[dict]:
        """
        Compute one feature-row dict for `date`.
        Returns None if insufficient options data.
        No fallbacks — if real IV is missing the bar is skipped.
        """
        if snap_today.empty:
            return None

        # Ensure ImpliedVol and DTE are numeric
        snap = snap_today.copy()
        for col in ["ImpliedVol", "DTE", "Delta", "StrikePrice"]:
            if col in snap.columns:
                snap[col] = pd.to_numeric(snap[col], errors="coerce")

        snap = snap.dropna(subset=["ImpliedVol", "DTE"])
        snap = snap[snap["DTE"] > 0]
        if snap.empty:
            return None

        # ── Feature 1 & 2: front / back ATM IV ───────────────────────────────
        front_df = snap[(snap["DTE"] >= 7)  & (snap["DTE"] <= 21)]
        back_df  = snap[(snap["DTE"] >= 22) & (snap["DTE"] <= 60)]

        if front_df.empty or back_df.empty:
            return None

        # ATM = options with |delta| closest to 0.50 (calls) or -0.50 (puts)
        # If Delta column absent, use median IV directly as a proxy for ATM
        def _median_atm_iv(df: pd.DataFrame) -> Optional[float]:
            if "Delta" in df.columns:
                d = df["Delta"].dropna().abs()
                if len(d) == 0:
                    return None
                # keep options within ±0.15 of ATM delta
                mask = (d >= 0.35) & (d <= 0.65)
                subset = df[mask]
                if subset.empty:
                    # relax — closest delta to 0.5
                    idx = (d - 0.5).abs().idxmin()
                    subset = df.loc[[idx]]
            else:
                subset = df
            ivs = subset["ImpliedVol"].dropna()
            if len(ivs) == 0:
                return None
            val = float(ivs.median())
            # ImpliedVol from Robinhood is in decimal (0.35 = 35%) — convert to %
            if val < 2.0:
                val = val * 100.0
            return val if val > 0 else None

        stock_front_iv = _median_atm_iv(front_df)
        stock_back_iv  = _median_atm_iv(back_df)

        if stock_front_iv is None or stock_back_iv is None:
            return None

        # ── Feature 3: term slope ─────────────────────────────────────────────
        stock_term_slope = stock_front_iv - stock_back_iv

        # ── Feature 4: 5-bar slope change ────────────────────────────────────
        # Computed externally from rolling front_iv_history (passed as Series)
        # We record slope now; 5d change computed during matrix building below.
        # Use 0.0 as placeholder here; filled in _build_feature_matrix.
        stock_term_slope_5d_change = 0.0  # will be back-filled in matrix pass

        # ── Feature 5: VRP ────────────────────────────────────────────────────
        rvol = self._compute_realized_vol(price_slice["close"], window=20)
        if rvol is None:
            stock_vrp = 0.0
        else:
            stock_vrp = (stock_front_iv / 100.0) - rvol

        # ── Feature 6: IVR ────────────────────────────────────────────────────
        stock_ivr = self._ivr(stock_front_iv, front_iv_history)

        # ── Feature 7: VIX ────────────────────────────────────────────────────
        vix_val = float(vix_series.iloc[-1]) if len(vix_series) > 0 else 20.0

        # ── Feature 8: VIX term slope proxy ──────────────────────────────────
        vix_futures = aux.get("vix_futures")
        if vix_futures is not None and not vix_futures.empty:
            ts = pd.Timestamp(date)
            vf = vix_futures.loc[:ts].tail(1) if ts >= vix_futures.index.min() else pd.DataFrame()
            if not vf.empty and "front" in vf.columns and "second" in vf.columns:
                vx1 = float(vf["front"].iloc[-1])
                vx2 = float(vf["second"].iloc[-1])
                if vx1 > 0:
                    vix_term_slope = (vx2 - vx1) / vx1
                else:
                    vix_term_slope = 0.0
            else:
                vix_term_slope = _vix_rolling_proxy(vix_series)
        else:
            vix_term_slope = _vix_rolling_proxy(vix_series)

        # ── Feature 9: Yield curve 2y10y ─────────────────────────────────────
        rate10y_df = aux.get("rate10y")
        rate2y_df  = aux.get("rate2y")
        ts = pd.Timestamp(date)
        r10 = _last_rate(rate10y_df, ts)
        r2  = _last_rate(rate2y_df,  ts)
        if r10 is not None and r2 is not None:
            yield_curve_2y10y = r10 - r2
        elif r10 is not None:
            yield_curve_2y10y = r10
        else:
            yield_curve_2y10y = 0.0

        # ── Feature 10: SPY 20d realised vol ─────────────────────────────────
        spy_rvol = self._compute_realized_vol(price_slice["close"], window=20)
        spy_20d_realized_vol = float(spy_rvol) if spy_rvol is not None else 0.0

        return {
            "date":                       date,
            "stock_front_iv":             stock_front_iv,
            "stock_back_iv":              stock_back_iv,
            "stock_term_slope":           stock_term_slope,
            "stock_term_slope_5d_change": stock_term_slope_5d_change,
            "stock_vrp":                  stock_vrp,
            "stock_ivr":                  stock_ivr,
            "vix":                        vix_val,
            "vix_term_slope":             vix_term_slope,
            "yield_curve_2y10y":          yield_curve_2y10y,
            "spy_20d_realized_vol":       spy_20d_realized_vol,
        }

    def _build_feature_matrix(
        self,
        price_data: pd.DataFrame,
        option_snapshots: pd.DataFrame,
        vix_df: pd.DataFrame,
        aux: dict,
        progress_callback=None,
    ) -> pd.DataFrame:
        """
        Build full feature matrix from raw data.
        Validates that at least 2 distinct DTE buckets (front 7-21 and back 22-60)
        exist in option_snapshots; raises ValueError otherwise.

        Returns a DataFrame indexed by date with all 10 feature columns.
        """
        # Validate option data coverage
        if option_snapshots is None or option_snapshots.empty:
            raise ValueError("option_snapshots is empty — cannot build features.")

        snap = option_snapshots.copy()
        if "DTE" in snap.columns:
            snap["DTE"] = pd.to_numeric(snap["DTE"], errors="coerce")
            has_front = ((snap["DTE"] >= 7)  & (snap["DTE"] <= 21)).any()
            has_back  = ((snap["DTE"] >= 22) & (snap["DTE"] <= 60)).any()
            if not (has_front and has_back):
                raise ValueError(
                    "option_snapshots does not have both front (DTE 7-21) and "
                    "back (DTE 22-60) buckets — strategy requires 2 distinct DTE buckets."
                )

        # Normalise SnapshotDate column
        date_col = None
        for c in ["SnapshotDate", "snapshot_date", "date", "Date"]:
            if c in snap.columns:
                date_col = c
                break
        if date_col is None:
            raise ValueError("option_snapshots must have a SnapshotDate column.")
        snap["_date"] = pd.to_datetime(snap[date_col]).dt.date

        # Build VIX series
        if vix_df is not None and not vix_df.empty and "close" in vix_df.columns:
            vix_series = pd.to_numeric(vix_df["close"], errors="coerce").dropna()
            vix_series.index = pd.to_datetime(vix_series.index)
        else:
            vix_series = pd.Series(20.0, index=price_data.index)

        price_data = price_data.sort_index()
        dates = sorted(snap["_date"].unique())

        rows: list[dict] = []
        front_iv_hist: list[float] = []
        n_dates = len(dates)

        for i, d in enumerate(dates):
            ts = pd.Timestamp(d)
            if ts not in price_data.index:
                # try nearest earlier date
                idx_pos = price_data.index.searchsorted(ts)
                if idx_pos == 0:
                    continue
                ts = price_data.index[idx_pos - 1]

            snap_today = snap[snap["_date"] == d]
            price_slice = price_data.loc[:ts].tail(120)
            if len(price_slice) < 21:
                continue

            vix_s = vix_series.loc[:ts].tail(30) if len(vix_series) > 0 else pd.Series([20.0])

            fih = pd.Series(front_iv_hist[-252:]) if front_iv_hist else pd.Series([30.0])

            try:
                row = self._build_feature_row(
                    date          = d,
                    snap_today    = snap_today,
                    price_slice   = price_slice,
                    vix_series    = vix_s,
                    front_iv_history = fih,
                    aux           = aux,
                )
            except Exception as e:
                logger.debug(f"Feature build failed on {d}: {e}")
                continue

            if row is not None:
                rows.append(row)
                front_iv_hist.append(row["stock_front_iv"])

            if progress_callback and i % 20 == 0:
                progress_callback(0.05 + 0.35 * (i / n_dates),
                                  f"Building features {i}/{n_dates}…")

        if len(rows) < 60:
            raise ValueError(
                f"Only {len(rows)} feature rows built — need ≥ 60 to train. "
                "Check option_snapshots coverage."
            )

        feature_df = pd.DataFrame(rows).set_index("date")
        feature_df.index = pd.to_datetime(feature_df.index)

        # Back-fill the 5-day slope change now that we have the full slope series
        slope = feature_df["stock_term_slope"]
        feature_df["stock_term_slope_5d_change"] = slope - slope.shift(5)
        feature_df["stock_term_slope_5d_change"] = (
            feature_df["stock_term_slope_5d_change"].fillna(0.0)
        )

        return feature_df

    # ═══════════════════════════════════════════════════════════════════════════
    # Label construction
    # ═══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _build_label_series(feature_df: pd.DataFrame, horizon: int = 10) -> pd.Series:
        """
        Forward `horizon`-day relative IV change → 3-class label.
          COMPRESS (<−5%): 0
          FLAT    (−5%–+5%): 1
          EXPAND  (>+5%): 2
        Last `horizon` rows are masked as -1 (no look-ahead data).
        """
        front_iv = feature_df["stock_front_iv"].values.astype(float)
        n        = len(front_iv)
        labels   = np.full(n, FLAT, dtype=int)

        for i in range(n - horizon):
            iv_now = front_iv[i]
            if iv_now <= 0:
                continue
            fwd_rel = (front_iv[i + horizon] - iv_now) / iv_now
            if fwd_rel < -0.05:
                labels[i] = COMPRESS
            elif fwd_rel > 0.05:
                labels[i] = EXPAND
            # else remains FLAT

        labels[-horizon:] = -1   # no forward data — mask
        return pd.Series(labels, index=feature_df.index, name="label")

    # ═══════════════════════════════════════════════════════════════════════════
    # Walk-forward LSTM training
    # ═══════════════════════════════════════════════════════════════════════════

    def _make_trainer(self) -> "ModelTrainer":  # noqa: F821
        from alan_trader.model.trainer import ModelTrainer
        return ModelTrainer(
            feature_cols = self.feature_cols,
            hidden_size  = self.HIDDEN_SIZE,
            num_layers   = self.NUM_LAYERS,
            dropout      = self.DROPOUT,
            seq_len      = self.SEQ_LEN,
            num_epochs   = 60,
            patience     = 12,
            batch_size   = 32,
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # Backtest
    # ═══════════════════════════════════════════════════════════════════════════

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
        Walk-forward LSTM backtest.

        Parameters
        ----------
        price_data       : OHLCV DataFrame, DatetimeIndex
        auxiliary_data   : dict with keys:
                             option_snapshots — DataFrame (SnapshotDate, DTE, ImpliedVol, Delta, …)
                             vix              — DataFrame (date-indexed, "close")
                             rate10y          — DataFrame (date-indexed, "close") [optional]
                             rate2y           — DataFrame (date-indexed, "close") [optional]
                             vix_futures      — DataFrame (date-indexed, "front", "second") [optional]
        starting_capital : float
        ticker           : str (for labelling trades only)
        """
        # Override params from kwargs (dashboard sliders)
        for k in ("signal_threshold", "dte_entry", "position_size_pct", "regime_reeval_bars"):
            if k in kwargs:
                setattr(self, k, float(kwargs[k]) if k not in ("dte_entry", "regime_reeval_bars")
                        else int(kwargs[k]))

        option_snapshots = auxiliary_data.get("option_snapshots")
        vix_df           = auxiliary_data.get("vix",    pd.DataFrame())

        # ── Step 1: Build feature matrix ─────────────────────────────────────
        if progress_callback:
            progress_callback(0.02, "Building feature matrix…")

        try:
            feature_df = self._build_feature_matrix(
                price_data       = price_data,
                option_snapshots = option_snapshots,
                vix_df           = vix_df,
                aux              = auxiliary_data,
                progress_callback = progress_callback,
            )
        except ValueError as e:
            return BacktestResult(
                strategy_name = self.name,
                equity_curve  = pd.Series(dtype=float),
                daily_returns = pd.Series(dtype=float),
                trades        = pd.DataFrame(),
                metrics       = {"error": str(e)},
            )

        n_total = len(feature_df)
        if n_total < self.WARMUP_BARS + self.SEQ_LEN + 10:
            return BacktestResult(
                strategy_name = self.name,
                equity_curve  = pd.Series(dtype=float),
                daily_returns = pd.Series(dtype=float),
                trades        = pd.DataFrame(),
                metrics       = {"error": f"Only {n_total} bars — need ≥ {self.WARMUP_BARS + self.SEQ_LEN + 10}"},
            )

        labels_all = self._build_label_series(feature_df, horizon=10)

        # ── Step 2: Walk-forward simulation ──────────────────────────────────
        if progress_callback:
            progress_callback(0.42, "Running walk-forward simulation…")

        capital     = float(starting_capital)
        equity_pts  = [{"date": feature_df.index[self.WARMUP_BARS - 1], "equity": capital}]
        trade_rows  = []
        open_trades: list[dict] = []

        # Separate open-position counters per regime type
        open_compress_count = 0
        open_expand_count   = 0

        current_trainer: Optional[object] = None
        last_retrain_bar = -1
        bars_since_signal = 0

        feature_arr = feature_df[self.feature_cols].values.astype(float)

        n_sim = n_total - self.WARMUP_BARS
        for step in range(n_sim):
            bar_idx = self.WARMUP_BARS + step
            dt      = feature_df.index[bar_idx]
            feat_row = feature_df.iloc[bar_idx]

            # ── Re-train if needed (walk-forward) ────────────────────────────
            need_retrain = (
                current_trainer is None
                or (bar_idx - last_retrain_bar) >= self.RETRAIN_EVERY
            )
            if need_retrain:
                X_train = feature_arr[:bar_idx]
                y_all   = labels_all.iloc[:bar_idx].values
                valid   = y_all >= 0
                X_v = X_train[valid]
                y_v = y_all[valid]
                if len(np.unique(y_v)) >= 2 and len(X_v) >= self.SEQ_LEN + 2:
                    try:
                        trainer = self._make_trainer()
                        trainer.fit(X_v, y_v)
                        current_trainer = trainer
                        last_retrain_bar = bar_idx
                    except Exception as e:
                        logger.debug(f"Retrain failed at bar {bar_idx}: {e}")

            # ── MTM: update open-trade value every bar ────────────────────────
            still_open = []
            for ot in open_trades:
                days_held = (dt - pd.Timestamp(ot["entry_date"])).days
                closed = False
                pnl    = 0.0

                spot_now = _get_spot(price_data, dt)
                if spot_now is None:
                    still_open.append(ot)
                    continue

                if ot["trade_type"] == "bull_put_spread":
                    # Credit spread: profit = credit received − current spread value
                    bs_short = _bs_val(spot_now, ot["short_strike"], ot["dte_short"] - days_held,
                                       ot["iv_entry"], "put")
                    bs_long  = _bs_val(spot_now, ot["long_strike"],  ot["dte_short"] - days_held,
                                       ot["iv_entry"], "put")
                    current_spread_val = (bs_short - bs_long) * 100.0 * ot["contracts"]
                    entry_credit       = ot["entry_credit"]
                    pnl_mtm            = entry_credit - current_spread_val

                    # Exits: 50% profit, 2× credit loss, 21 DTE time stop
                    profit_target = entry_credit * 0.50
                    loss_stop     = entry_credit * 2.0
                    time_stop     = days_held >= 21 or (ot["dte_short"] - days_held) <= 0

                    if pnl_mtm >= profit_target or pnl_mtm <= -loss_stop or time_stop:
                        pnl = pnl_mtm
                        closed = True
                        exit_reason = (
                            "profit_target" if pnl_mtm >= profit_target
                            else "time_stop" if time_stop
                            else "loss_stop"
                        )

                elif ot["trade_type"] == "long_straddle":
                    bs_call = _bs_val(spot_now, ot["strike"], ot["dte_entry"] - days_held,
                                      ot["iv_entry"], "call")
                    bs_put  = _bs_val(spot_now, ot["strike"], ot["dte_entry"] - days_held,
                                      ot["iv_entry"], "put")
                    current_val  = (bs_call + bs_put) * 100.0 * ot["contracts"]
                    entry_debit  = ot["entry_debit"]
                    pnl_mtm      = current_val - entry_debit

                    # Exits: either leg +100%, total position −50%, or 7 DTE
                    max_leg_gain = max(
                        (bs_call * 100 * ot["contracts"]) / max(ot["call_entry_val"], 1) - 1,
                        (bs_put  * 100 * ot["contracts"]) / max(ot["put_entry_val"],  1) - 1,
                    ) if ot.get("call_entry_val", 0) > 0 and ot.get("put_entry_val", 0) > 0 else 0.0

                    leg_double   = max_leg_gain >= 1.0
                    position_cut = pnl_mtm <= -entry_debit * 0.50
                    time_stop    = (ot["dte_entry"] - days_held) <= 7

                    if leg_double or position_cut or time_stop:
                        pnl = pnl_mtm
                        closed = True
                        exit_reason = (
                            "leg_double" if leg_double
                            else "time_stop" if time_stop
                            else "position_cut"
                        )

                if closed:
                    capital += pnl
                    trade_rows.append({
                        "ticker":       ticker,
                        "entry_date":   ot["entry_date"],
                        "exit_date":    dt.date() if hasattr(dt, "date") else dt,
                        "trade_type":   ot["trade_type"],
                        "regime":       ot["regime"],
                        "confidence":   ot["confidence"],
                        "contracts":    ot["contracts"],
                        "pnl":          round(pnl, 2),
                        "exit_reason":  exit_reason,
                        "days_held":    days_held,
                        "iv_entry":     ot["iv_entry"],
                    })
                    if ot["trade_type"] == "bull_put_spread":
                        open_compress_count = max(0, open_compress_count - 1)
                    else:
                        open_expand_count = max(0, open_expand_count - 1)
                else:
                    still_open.append(ot)

            open_trades = still_open

            # ── Regime signal (every regime_reeval_bars) ──────────────────────
            bars_since_signal += 1
            if bars_since_signal < self.regime_reeval_bars:
                equity_pts.append({"date": dt, "equity": capital})
                continue
            bars_since_signal = 0

            if current_trainer is None:
                equity_pts.append({"date": dt, "equity": capital})
                continue

            # Need at least SEQ_LEN rows of history for inference
            if bar_idx < self.SEQ_LEN:
                equity_pts.append({"date": dt, "equity": capital})
                continue

            try:
                X_inf = feature_arr[max(0, bar_idx - self.SEQ_LEN * 3): bar_idx + 1]
                proba = current_trainer.predict(X_inf)
                regime = int(np.argmax(proba))
                conf   = float(proba[regime])
            except Exception as e:
                logger.debug(f"Predict failed at {dt}: {e}")
                equity_pts.append({"date": dt, "equity": capital})
                continue

            # Skip if confidence below threshold
            if conf < self.signal_threshold:
                equity_pts.append({"date": dt, "equity": capital})
                continue

            spot = _get_spot(price_data, dt)
            if spot is None:
                equity_pts.append({"date": dt, "equity": capital})
                continue

            front_iv = float(feat_row.get("stock_front_iv", 30.0))
            dte      = max(1, self.dte_entry)

            # ── Enter trade ───────────────────────────────────────────────────
            if regime == COMPRESS and open_compress_count < 1:
                # Bull Put Spread: sell 0.20-delta put, buy ~5% further OTM put
                short_strike = _approx_delta_strike(spot, dte, front_iv / 100.0, 0.20, "put")
                long_strike  = short_strike * 0.95   # ~5% further OTM
                # BS credit: sell short put - buy long put
                bs_short = _bs_val(spot, short_strike, dte, front_iv / 100.0, "put")
                bs_long  = _bs_val(spot, long_strike,  dte, front_iv / 100.0, "put")
                net_credit_per_contract = max(0.01, bs_short - bs_long) * 100.0
                slip    = self.slippage_per_leg
                comm    = self.commission_per_leg * 2
                entry_credit_per = (max(0.0, (bs_short - slip) - (bs_long + slip))) * 100.0
                if entry_credit_per <= 0:
                    entry_credit_per = net_credit_per_contract * 0.8
                contracts = max(1, int(
                    capital * (self.position_size_pct / 100.0) / max(entry_credit_per + comm, 1)
                ))
                total_credit = entry_credit_per * contracts
                capital += total_credit - comm * contracts  # credit received

                open_trades.append({
                    "entry_date":   dt.date() if hasattr(dt, "date") else dt,
                    "trade_type":   "bull_put_spread",
                    "regime":       LABEL_NAMES[regime],
                    "confidence":   conf,
                    "contracts":    contracts,
                    "short_strike": short_strike,
                    "long_strike":  long_strike,
                    "dte_short":    dte,
                    "iv_entry":     front_iv / 100.0,
                    "entry_credit": total_credit,
                    "spot_entry":   spot,
                })
                open_compress_count += 1

            elif regime == EXPAND and open_expand_count < 1:
                # Long Straddle: buy ATM call + ATM put
                atm_strike = round(spot / 5.0) * 5.0  # round to nearest $5
                bs_call = _bs_val(spot, atm_strike, dte, front_iv / 100.0, "call")
                bs_put  = _bs_val(spot, atm_strike, dte, front_iv / 100.0, "put")
                slip    = self.slippage_per_leg
                comm    = self.commission_per_leg * 2
                entry_debit_per = ((bs_call + slip) + (bs_put + slip)) * 100.0
                if entry_debit_per <= 0:
                    entry_debit_per = (bs_call + bs_put) * 100.0 * 1.05
                contracts = max(1, int(
                    capital * (self.position_size_pct / 100.0) / max(entry_debit_per + comm, 1)
                ))
                total_debit = entry_debit_per * contracts
                capital -= total_debit + comm * contracts  # debit paid

                open_trades.append({
                    "entry_date":    dt.date() if hasattr(dt, "date") else dt,
                    "trade_type":    "long_straddle",
                    "regime":        LABEL_NAMES[regime],
                    "confidence":    conf,
                    "contracts":     contracts,
                    "strike":        atm_strike,
                    "dte_entry":     dte,
                    "iv_entry":      front_iv / 100.0,
                    "entry_debit":   total_debit,
                    "call_entry_val": bs_call * 100 * contracts,
                    "put_entry_val":  bs_put  * 100 * contracts,
                    "spot_entry":    spot,
                })
                open_expand_count += 1

            equity_pts.append({"date": dt, "equity": capital})

            if progress_callback and step % 20 == 0:
                progress_callback(
                    0.42 + 0.55 * (step / n_sim),
                    f"Simulating bar {step}/{n_sim}…",
                )

        # ── Force-close remaining open trades at last bar ─────────────────────
        last_dt   = feature_df.index[-1]
        last_spot = _get_spot(price_data, last_dt)
        for ot in open_trades:
            pnl = 0.0
            days_held = (last_dt - pd.Timestamp(ot["entry_date"])).days
            if last_spot is not None:
                if ot["trade_type"] == "bull_put_spread":
                    bs_s = _bs_val(last_spot, ot["short_strike"], max(1, ot["dte_short"] - days_held),
                                   ot["iv_entry"], "put")
                    bs_l = _bs_val(last_spot, ot["long_strike"],  max(1, ot["dte_short"] - days_held),
                                   ot["iv_entry"], "put")
                    current_val = (bs_s - bs_l) * 100.0 * ot["contracts"]
                    pnl = ot["entry_credit"] - current_val
                elif ot["trade_type"] == "long_straddle":
                    bs_c = _bs_val(last_spot, ot["strike"], max(1, ot["dte_entry"] - days_held),
                                   ot["iv_entry"], "call")
                    bs_p = _bs_val(last_spot, ot["strike"], max(1, ot["dte_entry"] - days_held),
                                   ot["iv_entry"], "put")
                    pnl = (bs_c + bs_p) * 100.0 * ot["contracts"] - ot["entry_debit"]
            capital += pnl
            trade_rows.append({
                "ticker":       ticker,
                "entry_date":   ot["entry_date"],
                "exit_date":    last_dt.date() if hasattr(last_dt, "date") else last_dt,
                "trade_type":   ot["trade_type"],
                "regime":       ot["regime"],
                "confidence":   ot["confidence"],
                "contracts":    ot["contracts"],
                "pnl":          round(pnl, 2),
                "exit_reason":  "expiry",
                "days_held":    days_held,
                "iv_entry":     ot["iv_entry"],
            })

        if open_trades and equity_pts:
            equity_pts[-1] = {"date": last_dt, "equity": capital}

        # ── Build results ─────────────────────────────────────────────────────
        if progress_callback:
            progress_callback(0.98, "Computing metrics…")

        eq_df = pd.DataFrame(equity_pts).set_index("date")["equity"]
        eq_df.index = pd.to_datetime(eq_df.index)
        eq_df = eq_df[~eq_df.index.duplicated(keep="last")]

        daily_ret = eq_df.pct_change().dropna()
        trades_df = pd.DataFrame(trade_rows) if trade_rows else pd.DataFrame()
        metrics   = compute_all_metrics(eq_df, trades_df)
        metrics.update({
            "n_signals":   len(trade_rows),
            "n_compress":  sum(1 for t in trade_rows if t.get("trade_type") == "bull_put_spread"),
            "n_expand":    sum(1 for t in trade_rows if t.get("trade_type") == "long_straddle"),
            "warmup_bars": self.WARMUP_BARS,
            "seq_len":     self.SEQ_LEN,
        })

        if progress_callback:
            progress_callback(1.0, "Backtest complete.")

        return BacktestResult(
            strategy_name = self.name,
            equity_curve  = eq_df,
            daily_returns = daily_ret,
            trades        = trades_df,
            metrics       = metrics,
            params        = self.get_params(),
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Module-level helper functions (pure, no class state)
# ═══════════════════════════════════════════════════════════════════════════════

def _vix_rolling_proxy(vix_series: pd.Series) -> float:
    """
    Proxy for VIX term slope using rolling mean deviation.
    Negative = spot VIX above 20d average = backwardation proxy.
    """
    if len(vix_series) < 20:
        return 0.0
    vix_now  = float(vix_series.iloc[-1])
    vix_mean = float(vix_series.iloc[-20:].mean())
    if vix_mean == 0:
        return 0.0
    return (vix_mean - vix_now) / vix_mean   # negative when spot > mean


def _last_rate(rate_df: Optional[pd.DataFrame], ts: pd.Timestamp) -> Optional[float]:
    """Return most recent rate close on or before ts."""
    if rate_df is None or rate_df.empty or "close" not in rate_df.columns:
        return None
    try:
        sub = rate_df.loc[:ts]
        if sub.empty:
            return None
        return float(pd.to_numeric(sub["close"], errors="coerce").dropna().iloc[-1])
    except Exception:
        return None


def _get_spot(price_data: pd.DataFrame, ts: pd.Timestamp) -> Optional[float]:
    """Return the close price for ts (or nearest earlier bar)."""
    if price_data is None or price_data.empty:
        return None
    try:
        if ts in price_data.index:
            return float(price_data.loc[ts, "close"])
        idx = price_data.index.searchsorted(ts)
        if idx == 0:
            return None
        return float(price_data.iloc[idx - 1]["close"])
    except Exception:
        return None


def _bs_val(
    S: float, K: float, T_days: float, iv: float, option_type: str
) -> float:
    """
    Black-Scholes option value.
    Uses alan_trader.backtest.engine.bs_price when available,
    falls back to an inline implementation.
    T_days is in calendar days; converted to years assuming 252 trading days/yr.
    """
    T = max(T_days, 0.5) / 252.0
    try:
        from alan_trader.backtest.engine import bs_price
        return float(bs_price(S, K, T, 0.045, max(iv, 0.01), option_type))
    except Exception:
        return _bs_inline(S, K, T, 0.045, max(iv, 0.01), option_type)


def _bs_inline(S: float, K: float, T: float, r: float, sigma: float, option_type: str) -> float:
    """Inline Black-Scholes pricing as fallback."""
    import math
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    try:
        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        from scipy.stats import norm
        if option_type.lower().startswith("c"):
            return float(S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2))
        else:
            return float(K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1))
    except Exception:
        # Last resort: intrinsic only
        if option_type.lower().startswith("c"):
            return max(0.0, S - K)
        return max(0.0, K - S)


def _approx_delta_strike(
    spot: float, dte: int, iv: float, target_delta: float, option_type: str
) -> float:
    """
    Approximate the strike that gives ~target_delta for a put or call.
    Uses the normal-approximation: K ≈ S * exp(−Φ^{-1}(delta) * σ√T) for puts.
    """
    import math
    try:
        from scipy.stats import norm
        T = max(dte, 1) / 252.0
        sig_t = max(iv, 0.01) * math.sqrt(T)
        if option_type.lower().startswith("p"):
            # For put delta (negative): P(d2 < x) = target => d2 = Φ^{-1}(target)
            z = norm.ppf(target_delta)   # e.g. 0.20 → z ≈ -0.84
        else:
            z = norm.ppf(1 - target_delta)
        K = spot * math.exp(-z * sig_t)
        return round(K / 0.50) * 0.50  # round to nearest $0.50
    except Exception:
        # Fallback: rough approximation
        if option_type.lower().startswith("p"):
            return spot * (1 - iv * math.sqrt(dte / 252.0) * 0.84)
        return spot * (1 + iv * math.sqrt(dte / 252.0) * 0.84)
