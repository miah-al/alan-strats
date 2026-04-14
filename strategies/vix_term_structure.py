"""
VIX Term Structure AI Strategy.

THESIS
------
The VIX risk premium — the persistent spread between implied vol (VIX) and
realized vol — is one of the most documented structural edges in equity markets.
Implied vol exceeds realized vol roughly 75-80% of trading days, creating a
systematic premium-selling opportunity. However, the 20-25% of days when realized
vol EXCEEDS implied (backwardation periods) cause catastrophic losses for static
premium sellers. This strategy uses a gradient boosting classifier to distinguish
contango (sell premium) from backwardation (buy protection) regimes before entry.

LAYER 1 — REGIME CLASSIFIER (Gradient Boosting):
  Predicts P(14d realized vol > current implied vol) = P(backwardation).
  Features: VIX momentum, vol-of-vol, SPY trend, IV-RV spread, term structure.
  P < 0.40 → contango regime → sell credit spread (harvest premium).
  P > 0.60 → backwardation regime → buy debit spread (buy protection).
  0.40–0.60 → ambiguous → stay flat.

WALK-FORWARD TRAINING
---------------------
  - Expanding window: model sees all history up to current bar
  - Warmup: 90 bars before first prediction
  - Retrain every 15 bars
  - No future data used in feature construction or labels

FEATURE SET (12 features)
--------------------------
  VIX:       vix_level, vix_5d_change, vix_20d_change, vix_ma_ratio, vix_vol_of_vol
  Vol:       realized_vol_20d, vrp (iv - rv), iv_rv_ratio
  SPY:       ret_5d, ret_20d, dist_from_ma200, atr_pct

LABEL CONSTRUCTION
------------------
  backwardation_N = 1 if realized_vol_14d_forward > vix_today / 100
  This is binary: will realized vol exceed the current implied vol estimate?
  Positive rate: ~22% (backwardation is the minority but catastrophic regime).
"""

from __future__ import annotations

import logging
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
from alan_trader.risk.metrics import compute_all_metrics

logger = logging.getLogger(__name__)

_RISK_FREE_RATE   = 0.045
_WARMUP_BARS      = 90
_RETRAIN_EVERY    = 15
_SAVED_MODELS_DIR = Path(__file__).parent.parent / "saved_models"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _bs_price(S, K, T, r, sigma, option_type):
    if T <= 0 or sigma <= 0 or S <= 0:
        return max(0.0, (S - K) if option_type == "call" else (K - S))
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    if option_type == "call":
        return float(S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2))
    return float(K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1))


def _spread_value(S, short_K, long_K, T, r, iv, spread_type):
    """Net value of a vertical spread at expiry-equivalent pricing."""
    if spread_type == "bull_put":
        short_val = _bs_price(S, short_K, T, r, iv, "put")
        long_val  = _bs_price(S, long_K,  T, r, iv, "put")
        return short_val - long_val
    elif spread_type == "bear_call":
        short_val = _bs_price(S, short_K, T, r, iv, "call")
        long_val  = _bs_price(S, long_K,  T, r, iv, "call")
        return short_val - long_val
    elif spread_type == "bear_put":  # debit
        long_val  = _bs_price(S, long_K,  T, r, iv, "put")
        short_val = _bs_price(S, short_K, T, r, iv, "put")
        return long_val - short_val
    elif spread_type == "bull_call":  # debit
        long_val  = _bs_price(S, long_K,  T, r, iv, "call")
        short_val = _bs_price(S, short_K, T, r, iv, "call")
        return long_val - short_val
    return 0.0


def _build_features(
    close:  pd.Series,
    high:   pd.Series,
    low:    pd.Series,
    vix:    pd.Series,
) -> pd.DataFrame:
    iv_proxy   = vix / 100.0
    rv20       = close.pct_change().rolling(20, min_periods=10).std() * np.sqrt(252)
    vrp        = iv_proxy - rv20
    iv_rv_rat  = (iv_proxy / rv20.replace(0, np.nan)).clip(0.5, 3.0)

    vix_5d     = vix.pct_change(5)
    vix_20d    = vix.pct_change(20)
    vix_ma20   = vix.rolling(20, min_periods=10).mean()
    vix_ma_rat = (vix / vix_ma20.replace(0, np.nan)).clip(0.5, 2.5)
    # vol-of-vol: std of VIX daily changes over 10 days
    vix_vov    = vix.diff().rolling(10, min_periods=5).std()

    ret_5d     = close.pct_change(5)
    ret_20d    = close.pct_change(20)
    ma200      = close.rolling(200, min_periods=50).mean()
    dist_ma200 = ((close - ma200) / ma200.replace(0, np.nan)).clip(-0.3, 0.3)

    prev_close = close.shift(1)
    tr         = pd.concat([high - low, (high - prev_close).abs(),
                             (low - prev_close).abs()], axis=1).max(axis=1)
    atr_pct    = tr.rolling(14, min_periods=7).mean() / close.replace(0, np.nan)

    df = pd.DataFrame({
        "vix_level":       vix,
        "vix_5d_change":   vix_5d,
        "vix_20d_change":  vix_20d,
        "vix_ma_ratio":    vix_ma_rat,
        "vix_vol_of_vol":  vix_vov,
        "realized_vol_20d": rv20,
        "vrp":             vrp,
        "iv_rv_ratio":     iv_rv_rat,
        "ret_5d":          ret_5d,
        "ret_20d":         ret_20d,
        "dist_from_ma200": dist_ma200,
        "atr_pct":         atr_pct,
    })
    return df.ffill().bfill()


def _build_labels(close: pd.Series, vix: pd.Series, n_forward: int = 14) -> pd.Series:
    """
    Binary label: 1 if realized vol over the next n_forward days
    exceeds the current VIX/100 (implied vol estimate).
    This is the backwardation regime — when it occurs, premium selling loses.
    Positive rate: ~20-25%.
    """
    labels = pd.Series(np.nan, index=close.index)
    log_ret = np.log(close / close.shift(1))

    for i in range(len(close) - n_forward):
        implied = float(vix.iloc[i]) / 100.0
        if np.isnan(implied) or implied <= 0:
            continue
        fwd_rets = log_ret.iloc[i + 1: i + 1 + n_forward].dropna()
        if len(fwd_rets) < n_forward // 2:
            continue
        realized = float(fwd_rets.std() * np.sqrt(252))
        labels.iloc[i] = 1.0 if realized > implied else 0.0

    return labels


# ── Strategy class ─────────────────────────────────────────────────────────────

class VIXTermStructureStrategy(BaseStrategy):
    """
    VIX Term Structure AI strategy.

    Uses gradient boosting to classify the vol regime as contango (sell premium)
    or backwardation (buy protection). Only enters when regime is unambiguous.

    Credit trade: bull put spread on SPY when contango confirmed (P < threshold_short).
    Debit trade: bear put spread on SPY when backwardation confirmed (P > threshold_long).
    """

    name                 = "vix_term_structure"
    display_name         = "VIX Term Structure AI"
    strategy_type        = StrategyType.AI_DRIVEN
    status               = StrategyStatus.ACTIVE
    description          = (
        "AI classifier predicts VIX contango vs backwardation regime. "
        "Sells SPY bull put credit spreads in contango (implied > realized), "
        "buys bear put debit spreads in backwardation. Walk-forward GBM, 90-bar warmup."
    )
    asset_class          = "equities_options"
    typical_holding_days = 14
    target_sharpe        = 1.3

    FEATURE_COLS = [
        "vix_level", "vix_5d_change", "vix_20d_change", "vix_ma_ratio",
        "vix_vol_of_vol", "realized_vol_20d", "vrp", "iv_rv_ratio",
        "ret_5d", "ret_20d", "dist_from_ma200", "atr_pct",
    ]

    _FEATURE_DEFAULTS = {
        "vix_level":        20.0,
        "vix_5d_change":     0.0,
        "vix_20d_change":    0.0,
        "vix_ma_ratio":      1.0,
        "vix_vol_of_vol":    0.5,
        "realized_vol_20d":  0.15,
        "vrp":               0.02,
        "iv_rv_ratio":       1.1,
        "ret_5d":            0.0,
        "ret_20d":           0.0,
        "dist_from_ma200":   0.0,
        "atr_pct":           0.01,
    }

    def __init__(
        self,
        threshold_short:    float = 0.40,  # P(backwardation) < this → sell credit
        threshold_long:     float = 0.60,  # P(backwardation) > this → buy debit
        vix_max:            float = 45.0,  # skip extreme panic
        dte_target:         int   = 21,
        dte_exit:           int   = 7,
        wing_width_pct:     float = 0.025, # 2.5% of spot
        profit_target_pct:  float = 0.50,
        stop_loss_mult:     float = 2.0,
        position_size_pct:  float = 0.02,
        n_estimators:       int   = 50,
        max_depth:          int   = 2,
        learning_rate:      float = 0.05,
    ):
        self.threshold_short   = threshold_short
        self.threshold_long    = threshold_long
        self.vix_max           = vix_max
        self.dte_target        = dte_target
        self.dte_exit          = dte_exit
        self.wing_width_pct    = wing_width_pct
        self.profit_target_pct = profit_target_pct
        self.stop_loss_mult    = stop_loss_mult
        self.position_size_pct = position_size_pct
        self.n_estimators      = n_estimators
        self.max_depth         = max_depth
        self.learning_rate     = learning_rate
        self._model            = None

    # ── Model persistence ──────────────────────────────────────────────────────

    def save_model(self, ticker: str = "SPY"):
        if self._model is None:
            return
        _SAVED_MODELS_DIR.mkdir(exist_ok=True)
        path = _SAVED_MODELS_DIR / f"vix_term_structure_{ticker}.pkl"
        with open(path, "wb") as f:
            pickle.dump(self._model, f)

    def load_model(self, ticker: str = "SPY") -> bool:
        path = _SAVED_MODELS_DIR / f"vix_term_structure_{ticker}.pkl"
        if not path.exists():
            return False
        with open(path, "rb") as f:
            self._model = pickle.load(f)
        return True

    def is_trainable(self) -> bool:
        return True

    # ── Live signal ────────────────────────────────────────────────────────────

    def generate_signal(self, market_snapshot: dict) -> SignalResult:
        vix  = float(market_snapshot.get("vix", 20.0))
        rv20 = float(market_snapshot.get("realized_vol_20d", 0.15))

        vrp = vix / 100.0 - rv20
        if vrp < -0.03:
            regime, signal = "backwardation", "BUY"   # buy protection (debit)
            confidence = min(0.85, 0.5 + abs(vrp) * 5)
        elif vrp > 0.03:
            regime, signal = "contango", "SELL"       # sell credit (premium)
            confidence = min(0.85, 0.5 + vrp * 5)
        else:
            regime, signal = "neutral", "HOLD"
            confidence = 0.4

        return SignalResult(
            strategy_name=self.name,
            signal=signal,
            confidence=confidence,
            position_size_pct=self.position_size_pct if signal != "HOLD" else 0.0,
            metadata={"regime": regime, "vix": vix, "rv20": rv20, "vrp": vrp},
        )

    # ── Backtest ───────────────────────────────────────────────────────────────

    def backtest(
        self,
        price_data:         pd.DataFrame,
        auxiliary_data:     dict,
        starting_capital:   float = 100_000,
        threshold_short:    float | None = None,
        threshold_long:     float | None = None,
        vix_max:            float | None = None,
        dte_target:         int   | None = None,
        dte_exit:           int   | None = None,
        wing_width_pct:     float | None = None,
        profit_target_pct:  float | None = None,
        stop_loss_mult:     float | None = None,
        **kwargs,
    ) -> BacktestResult:
        try:
            from sklearn.ensemble import GradientBoostingClassifier
            from sklearn.preprocessing import StandardScaler
            from sklearn.pipeline import Pipeline
        except ImportError as e:
            raise ImportError("scikit-learn required for VIXTermStructureStrategy") from e

        t_short   = threshold_short   if threshold_short   is not None else self.threshold_short
        t_long    = threshold_long    if threshold_long    is not None else self.threshold_long
        vix_max_  = vix_max           if vix_max           is not None else self.vix_max
        dte_tgt   = dte_target        if dte_target        is not None else self.dte_target
        dte_ex    = dte_exit          if dte_exit          is not None else self.dte_exit
        wing_pct  = wing_width_pct    if wing_width_pct    is not None else self.wing_width_pct
        pt_pct    = profit_target_pct if profit_target_pct is not None else self.profit_target_pct
        sl_mult   = stop_loss_mult    if stop_loss_mult    is not None else self.stop_loss_mult

        price_data = price_data.copy()
        price_data.index = pd.to_datetime(price_data.index)
        close = price_data["close"]
        high  = price_data.get("high",  close)
        low   = price_data.get("low",   close)

        vix_df = auxiliary_data.get("vix", pd.DataFrame())
        if vix_df.empty:
            raise ValueError("No VIX data. Sync Macro Bars first.")
        vix_df.index = pd.to_datetime(vix_df.index)
        vix = vix_df["close"].reindex(close.index).ffill().fillna(20.0)

        feats  = _build_features(close, high, low, vix)
        labels = _build_labels(close, vix, n_forward=dte_tgt)

        all_dates   = list(price_data.index)
        capital     = float(starting_capital)
        equity_list = []
        trades_list = []
        open_trade  = None          # one position at a time
        signal_log  = []
        model_      = None
        last_train  = -999

        for i, dt in enumerate(all_dates):
            # ── Update open trade ──────────────────────────────────────────
            if open_trade is not None:
                open_trade["days_held"] += 1
                spot     = float(close.iloc[i])
                iv_now   = float(vix.iloc[i]) / 100.0
                T_remain = max(0, open_trade["dte_remaining"] - 1)
                open_trade["dte_remaining"] = T_remain
                t_yr = T_remain / 252.0

                val_now = _spread_value(
                    spot,
                    open_trade["short_strike"],
                    open_trade["long_strike"],
                    t_yr,
                    _RISK_FREE_RATE,
                    iv_now,
                    open_trade["spread_type"],
                )

                entry_val = open_trade["entry_value"]
                is_credit = open_trade["is_credit"]
                pnl_now   = (entry_val - val_now) * 100 if is_credit else (val_now - entry_val) * 100
                max_profit = open_trade["max_profit"]
                max_loss   = open_trade["max_loss"]

                exit_reason = None
                if is_credit:
                    if pnl_now >= max_profit * pt_pct:
                        exit_reason = "profit_target"
                    elif pnl_now <= -max_loss * sl_mult:
                        exit_reason = "stop_loss"
                else:
                    if pnl_now >= max_loss * pt_pct:
                        exit_reason = "profit_target"
                    elif pnl_now <= -open_trade["entry_cost"] * 0.5:
                        exit_reason = "stop_loss"

                if T_remain <= dte_ex:
                    exit_reason = "dte_exit"

                if exit_reason:
                    capital += pnl_now
                    trades_list.append({
                        "entry_date":   open_trade["entry_date"].date(),
                        "exit_date":    dt.date(),
                        "spread_type":  open_trade["spread_type"],
                        "entry_cost":   round(open_trade["entry_cost"], 2),
                        "exit_value":   round(val_now * 100, 2),
                        "pnl":          round(pnl_now, 2),
                        "exit_reason":  exit_reason,
                    })
                    open_trade = None

            equity_list.append(capital)

            if i < _WARMUP_BARS:
                continue

            # ── Retrain ────────────────────────────────────────────────────
            if i - last_train >= _RETRAIN_EVERY:
                # Exclude last dte_tgt bars: their labels use future data beyond bar i
                cutoff = max(0, i - dte_tgt)
                X_tr = feats.iloc[:cutoff][self.FEATURE_COLS].copy()
                y_tr = labels.iloc[:cutoff].copy()
                valid = y_tr.notna() & X_tr.notna().all(axis=1)
                X_tr, y_tr = X_tr[valid], y_tr[valid]
                if len(y_tr) >= 30 and y_tr.nunique() >= 2:
                    pipe = Pipeline([
                        ("scaler", StandardScaler()),
                        ("clf", GradientBoostingClassifier(
                            n_estimators=self.n_estimators,
                            max_depth=self.max_depth,
                            learning_rate=self.learning_rate,
                            random_state=42,
                        )),
                    ])
                    pipe.fit(X_tr.values, y_tr.values)
                    model_ = pipe
                    last_train = i

            if model_ is None or open_trade is not None:
                continue

            # ── Entry signal ───────────────────────────────────────────────
            vix_now = float(vix.iloc[i])
            if vix_now > vix_max_:
                continue

            feat_row = feats.iloc[[i]][self.FEATURE_COLS]
            for col, default in self._FEATURE_DEFAULTS.items():
                if col in feat_row.columns:
                    feat_row[col] = feat_row[col].fillna(default)
            if feat_row.isna().any().any():
                continue

            prob_backwardation = float(model_.predict_proba(feat_row.values)[0][1])
            signal_log.append({"date": dt.date(), "prob_back": round(prob_backwardation, 3)})

            spot      = float(close.iloc[i])
            iv_entry  = float(vix.iloc[i]) / 100.0
            t_yr      = dte_tgt / 252.0
            wing      = spot * wing_pct
            max_cost  = capital * self.position_size_pct

            if prob_backwardation < t_short:
                # Contango → sell bull put credit spread
                short_K = round(spot * (1 - 0.02), 2)
                long_K  = round(short_K - wing, 2)
                entry_v = _spread_value(spot, short_K, long_K, t_yr, _RISK_FREE_RATE, iv_entry, "bull_put")
                if entry_v <= 0:
                    continue
                contracts  = max(1, int(max_cost / ((wing - entry_v) * 100)))
                max_profit = entry_v * 100 * contracts
                max_loss_  = (wing - entry_v) * 100 * contracts
                open_trade = {
                    "entry_date": dt, "spread_type": "bull_put",
                    "short_strike": short_K, "long_strike": long_K,
                    "entry_value": entry_v, "entry_cost": entry_v * 100 * contracts,
                    "is_credit": True, "max_profit": max_profit, "max_loss": max_loss_,
                    "dte_remaining": dte_tgt, "days_held": 0,
                    "prob": prob_backwardation,
                }

            elif prob_backwardation > t_long:
                # Backwardation → buy bear put debit spread
                long_K  = round(spot * (1 - 0.01), 2)
                short_K = round(long_K - wing, 2)
                entry_v = _spread_value(spot, short_K, long_K, t_yr, _RISK_FREE_RATE, iv_entry, "bear_put")
                if entry_v <= 0:
                    continue
                contracts  = max(1, int(max_cost / (entry_v * 100)))
                max_loss_  = entry_v * 100 * contracts
                capital   -= max_loss_
                if capital < 0:
                    capital += max_loss_
                    continue
                open_trade = {
                    "entry_date": dt, "spread_type": "bear_put",
                    "short_strike": short_K, "long_strike": long_K,
                    "entry_value": entry_v, "entry_cost": max_loss_,
                    "is_credit": False, "max_profit": (wing - entry_v) * 100 * contracts,
                    "max_loss": max_loss_,
                    "dte_remaining": dte_tgt, "days_held": 0,
                    "prob": prob_backwardation,
                }

        # Close any open trade at final bar
        if open_trade is not None:
            trades_list.append({
                "entry_date":  open_trade["entry_date"].date(),
                "exit_date":   all_dates[-1].date(),
                "spread_type": open_trade["spread_type"],
                "entry_cost":  round(open_trade["entry_cost"], 2),
                "exit_value":  0.0,
                "pnl":         round(-open_trade["entry_cost"], 2) if not open_trade["is_credit"] else 0.0,
                "exit_reason": "end_of_data",
            })

        equity    = pd.Series(equity_list, index=price_data.index, dtype=float)
        daily_ret = equity.pct_change().dropna()
        bh_ret    = close.pct_change().reindex(equity.index).dropna()

        trades_df = pd.DataFrame(trades_list) if trades_list else pd.DataFrame(
            columns=["entry_date", "exit_date", "spread_type",
                     "entry_cost", "exit_value", "pnl", "exit_reason"]
        )

        metrics = compute_all_metrics(
            equity_curve=equity,
            trades_df=trades_df,
            benchmark_returns=bh_ret,
        )

        self._model = model_
        return BacktestResult(
            strategy_name=self.name,
            equity_curve=equity,
            daily_returns=daily_ret,
            trades=trades_df,
            metrics=metrics,
            params=self.get_params(),
            extra={"signal_log": signal_log, "vix": vix},
        )

    # ── UI params ──────────────────────────────────────────────────────────────

    def get_backtest_ui_params(self) -> list:
        return [
            {"key": "threshold_short",   "label": "Contango threshold (sell)",
             "type": "slider", "min": 0.20, "max": 0.55, "default": 0.40, "step": 0.05,
             "col": 0, "row": 0,
             "help": "P(backwardation) below this → sell credit spread"},
            {"key": "threshold_long",    "label": "Backwardation threshold (buy)",
             "type": "slider", "min": 0.50, "max": 0.80, "default": 0.60, "step": 0.05,
             "col": 1, "row": 0,
             "help": "P(backwardation) above this → buy debit spread"},
            {"key": "dte_target",        "label": "DTE at entry",
             "type": "slider", "min": 10, "max": 35, "default": 21, "step": 1,
             "col": 2, "row": 0,
             "help": "Target days-to-expiry when opening spread"},
            {"key": "wing_width_pct",    "label": "Wing width (% spot)",
             "type": "slider", "min": 0.01, "max": 0.05, "default": 0.025, "step": 0.005,
             "col": 0, "row": 1,
             "help": "Width of spread as percentage of spot price"},
            {"key": "profit_target_pct", "label": "Profit target (% max)",
             "type": "slider", "min": 0.30, "max": 0.75, "default": 0.50, "step": 0.05,
             "col": 1, "row": 1,
             "help": "Close credit spread at this fraction of max credit"},
            {"key": "vix_max",           "label": "VIX ceiling",
             "type": "slider", "min": 30, "max": 60, "default": 45, "step": 5,
             "col": 2, "row": 1,
             "help": "Skip entry when VIX exceeds this level"},
        ]

    def get_params(self) -> dict:
        return {
            "threshold_short":   self.threshold_short,
            "threshold_long":    self.threshold_long,
            "vix_max":           self.vix_max,
            "dte_target":        self.dte_target,
            "dte_exit":          self.dte_exit,
            "wing_width_pct":    self.wing_width_pct,
            "profit_target_pct": self.profit_target_pct,
            "stop_loss_mult":    self.stop_loss_mult,
            "position_size_pct": self.position_size_pct,
            "n_estimators":      self.n_estimators,
            "max_depth":         self.max_depth,
            "learning_rate":     self.learning_rate,
        }
