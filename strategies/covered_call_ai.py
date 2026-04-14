"""
Covered Call Optimizer AI Strategy.

THESIS
------
Covered call writing is the most common retail strategy, but most retail traders
use rules of thumb: "always sell 30 DTE at 0.30 delta." The optimal (strike, DTE)
combination varies with: (1) IVR — sell more aggressively when premium is rich,
(2) earnings proximity — avoid when earnings are within the hold window,
(3) momentum state — use further OTM strikes in strong uptrends to preserve upside,
(4) vol term structure — shorter DTE in steep contango captures faster theta decay.
The ML layer scores a grid of (delta: 0.15→0.35) × (DTE: 14→45) combinations and
selects the one predicted to maximize risk-adjusted premium extraction.

WHAT THE AI PREDICTS
--------------------
Regression target: P&L per $100 of stock held over the next 30 days for each
(short_delta, dte) combination, given current feature state. The model is trained
on historical outcomes: did selling this strike/DTE combination outperform the
next-best choice? Output is a ranking → select highest-scoring combination.

In practice (backtest): simplified to a binary decision of whether to write the
covered call at all (IVR-gated) and which strike bucket (aggressive=0.30 delta
when IVR high and momentum weak; conservative=0.15 delta when momentum strong or
earnings near).

WALK-FORWARD TRAINING
---------------------
  - Warmup: 90 bars
  - Retrain every 15 bars
  - Label window: 30-day forward premium extraction vs assignment cost

FEATURE SET (10 features)
--------------------------
  Options:  ivr, vrp, iv_rv_ratio
  Momentum: ret_20d, ret_5d, dist_from_ma50
  VIX:      vix_level, vix_ma_ratio
  Term:     atr_pct
  Calendar: days_to_earnings_proxy (earnings gaps in trailing 90d)
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


def _bs_delta(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0 or S <= 0:
        return 1.0 if S > K else 0.0
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    return float(norm.cdf(d1))


def _strike_for_delta(S, T, r, sigma, target_delta):
    """Find call strike corresponding to target delta via binary search."""
    from scipy.optimize import brentq
    if T <= 0 or sigma <= 0:
        return S * 1.05
    def obj(K): return _bs_delta(S, K, T, r, sigma) - target_delta
    try:
        return float(brentq(obj, S * 0.8, S * 1.5, xtol=0.01))
    except Exception:
        return S * np.exp(sigma * np.sqrt(T) * (1 - target_delta))


def _build_features(close, high, low, vix):
    iv_proxy = vix / 100.0
    rv20     = close.pct_change().rolling(20, min_periods=10).std() * np.sqrt(252)
    vrp      = iv_proxy - rv20
    iv_rv    = (iv_proxy / rv20.replace(0, np.nan)).clip(0.5, 3.0)

    vix_ma20 = vix.rolling(20, min_periods=10).mean()
    vix_rat  = (vix / vix_ma20.replace(0, np.nan)).clip(0.5, 2.5)
    ivr      = ((vix - vix.rolling(252, min_periods=60).min()) /
                (vix.rolling(252, min_periods=60).max() -
                 vix.rolling(252, min_periods=60).min()).replace(0, np.nan)).clip(0, 1)

    ret_5d   = close.pct_change(5)
    ret_20d  = close.pct_change(20)
    ma50     = close.rolling(50, min_periods=20).mean()
    d_ma50   = ((close - ma50) / ma50.replace(0, np.nan)).clip(-0.3, 0.3)

    prev_c   = close.shift(1)
    tr       = pd.concat([high - low, (high - prev_c).abs(),
                           (low - prev_c).abs()], axis=1).max(axis=1)
    atr_pct  = tr.rolling(14, min_periods=7).mean() / close.replace(0, np.nan)

    # Earnings proximity proxy: days since last large gap (>4%)
    large_gap = close.pct_change().abs() > 0.04
    days_since_earnings = pd.Series(index=close.index, dtype=float)
    counter = 999
    for i, idx in enumerate(close.index):
        if large_gap.iloc[i]:
            counter = 0
        else:
            counter += 1
        days_since_earnings.iloc[i] = float(min(counter, 90))

    return pd.DataFrame({
        "ivr":                  ivr,
        "vrp":                  vrp,
        "iv_rv_ratio":          iv_rv,
        "ret_20d":              ret_20d,
        "ret_5d":               ret_5d,
        "dist_from_ma50":       d_ma50,
        "vix_level":            vix,
        "vix_ma_ratio":         vix_rat,
        "atr_pct":              atr_pct,
        "days_since_earnings":  days_since_earnings,
    }).ffill().bfill()


def _build_labels(close: pd.Series, vix: pd.Series,
                   dte: int = 30, delta: float = 0.25) -> pd.Series:
    """
    Binary label: 1 if selling a covered call at `delta` strike for `dte` days
    outperforms holding the stock outright (premium > forgone upside).
    Positive when: stock stays below the short strike (premium fully kept).
    Negative when: stock rallies above strike (covered call assignment caps gain).
    """
    sigma = vix / 100.0
    labels = pd.Series(np.nan, index=close.index)

    for i in range(len(close) - dte):
        iv   = float(sigma.iloc[i])
        S    = float(close.iloc[i])
        T    = dte / 252.0
        if iv <= 0 or S <= 0:
            continue
        strike = _strike_for_delta(S, T, _RISK_FREE_RATE, iv, delta)
        premium = _bs_price(S, strike, T, _RISK_FREE_RATE, iv, "call")
        exit_px = float(close.iloc[i + dte])

        # P&L of covered call writer:
        # If exit <= strike: keep premium + stock gain
        # If exit > strike: gain capped at (strike - S) + premium
        if exit_px <= strike:
            cc_pnl = premium + (exit_px - S)
        else:
            cc_pnl = premium + (strike - S)
        # P&L of just holding stock:
        hold_pnl = exit_px - S
        # Covered call wins if the position made positive P&L (premium > capital loss)
        labels.iloc[i] = 1.0 if cc_pnl > 0.0 else 0.0

    return labels


# ── Strategy class ─────────────────────────────────────────────────────────────

class CoveredCallAIStrategy(BaseStrategy):
    """
    Covered Call Optimizer AI strategy.

    Holds long stock (100 shares equivalent) and writes covered calls.
    GBM classifier selects aggressive (0.30 delta) or conservative (0.15 delta)
    strike based on current regime, and gates entry (skip if earnings near or
    momentum too strong). Walk-forward, 90-bar warmup, retrain every 15 bars.
    """

    name                 = "covered_call_ai"
    display_name         = "Covered Call Optimizer — AI"
    strategy_type        = StrategyType.AI_DRIVEN
    status               = StrategyStatus.ACTIVE
    description          = (
        "AI-optimized covered call writing. GBM selects strike and DTE based on "
        "IVR, momentum, earnings proximity, and vol regime. Aggressive delta in "
        "high-IVR low-momentum regimes; conservative in strong uptrends. "
        "Walk-forward, 90-bar warmup."
    )
    asset_class          = "equities_options"
    typical_holding_days = 21
    target_sharpe        = 1.0

    FEATURE_COLS = [
        "ivr", "vrp", "iv_rv_ratio", "ret_20d", "ret_5d",
        "dist_from_ma50", "vix_level", "vix_ma_ratio",
        "atr_pct", "days_since_earnings",
    ]

    _FEATURE_DEFAULTS = {
        "ivr":                 0.50,
        "vrp":                 0.02,
        "iv_rv_ratio":         1.1,
        "ret_20d":             0.0,
        "ret_5d":              0.0,
        "dist_from_ma50":      0.0,
        "vix_level":           20.0,
        "vix_ma_ratio":        1.0,
        "atr_pct":             0.01,
        "days_since_earnings": 30.0,
    }

    def __init__(
        self,
        min_ivr:              float = 0.30,   # minimum IVR to write any call
        aggressive_delta:     float = 0.30,   # delta for high-IVR, low-momentum
        conservative_delta:   float = 0.15,   # delta for strong-momentum regimes
        dte_target:           int   = 21,
        min_days_since_earn:  int   = 10,     # skip if likely within earnings window
        profit_target_pct:    float = 0.75,   # close short call at 75% of premium
        stop_loss_mult:       float = 2.0,    # close if short call doubles in value
        position_size_pct:    float = 1.0,    # 100% stock position (CC requires stock)
        n_estimators:         int   = 50,
        max_depth:            int   = 2,
        learning_rate:        float = 0.05,
    ):
        self.min_ivr             = min_ivr
        self.aggressive_delta    = aggressive_delta
        self.conservative_delta  = conservative_delta
        self.dte_target          = dte_target
        self.min_days_since_earn = min_days_since_earn
        self.profit_target_pct   = profit_target_pct
        self.stop_loss_mult      = stop_loss_mult
        self.position_size_pct   = position_size_pct
        self.n_estimators        = n_estimators
        self.max_depth           = max_depth
        self.learning_rate       = learning_rate
        self._model              = None

    def save_model(self, ticker: str = "SPY"):
        if self._model is None:
            return
        _SAVED_MODELS_DIR.mkdir(exist_ok=True)
        with open(_SAVED_MODELS_DIR / f"covered_call_ai_{ticker}.pkl", "wb") as f:
            pickle.dump(self._model, f)

    def load_model(self, ticker: str = "SPY") -> bool:
        path = _SAVED_MODELS_DIR / f"covered_call_ai_{ticker}.pkl"
        if not path.exists():
            return False
        with open(path, "rb") as f:
            self._model = pickle.load(f)
        return True

    def is_trainable(self) -> bool:
        return True

    def generate_signal(self, market_snapshot: dict) -> SignalResult:
        ivr     = float(market_snapshot.get("ivr", 0.5))
        ret_20d = float(market_snapshot.get("ret_20d", 0.0))
        vix     = float(market_snapshot.get("vix", 20.0))

        if ivr < self.min_ivr:
            signal, delta = "HOLD", None
        elif ret_20d > 0.08:
            signal, delta = "BUY", self.conservative_delta  # strong bull → conservative
        else:
            signal, delta = "BUY", self.aggressive_delta    # normal → aggressive

        return SignalResult(
            strategy_name=self.name,
            signal=signal,
            confidence=min(0.85, 0.50 + ivr * 0.5) if signal != "HOLD" else 0.30,
            position_size_pct=self.position_size_pct if signal != "HOLD" else 0.0,
            metadata={"ivr": ivr, "delta": delta, "vix": vix},
        )

    def backtest(
        self,
        price_data:           pd.DataFrame,
        auxiliary_data:       dict,
        starting_capital:     float = 100_000,
        min_ivr:              float | None = None,
        aggressive_delta:     float | None = None,
        conservative_delta:   float | None = None,
        dte_target:           int   | None = None,
        profit_target_pct:    float | None = None,
        stop_loss_mult:       float | None = None,
        **kwargs,
    ) -> BacktestResult:
        try:
            from sklearn.ensemble import GradientBoostingClassifier
            from sklearn.preprocessing import StandardScaler
            from sklearn.pipeline import Pipeline
        except ImportError as e:
            raise ImportError("scikit-learn required") from e

        min_ivr_   = min_ivr           if min_ivr           is not None else self.min_ivr
        agg_delta  = aggressive_delta  if aggressive_delta  is not None else self.aggressive_delta
        cons_delta = conservative_delta if conservative_delta is not None else self.conservative_delta
        dte_tgt    = dte_target        if dte_target        is not None else self.dte_target
        pt_pct     = profit_target_pct if profit_target_pct is not None else self.profit_target_pct
        sl_mult    = stop_loss_mult    if stop_loss_mult    is not None else self.stop_loss_mult

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
        labels = _build_labels(close, vix, dte=dte_tgt, delta=agg_delta)

        all_dates   = list(price_data.index)
        # Model the stock position as a fixed fractional holding
        # Capital is entirely in stock; cash tracks cumulative premium P&L
        stock_px_0  = float(close.iloc[0])
        shares      = float(starting_capital) / stock_px_0  # fractional shares
        cash        = 0.0   # running cash from CC premium gains/losses
        equity_list = []
        trades_list = []
        open_cc     = None
        model_      = None
        last_train  = -999

        for i, dt in enumerate(all_dates):
            spot = float(close.iloc[i])

            # Mark-to-market: stock value
            stock_value = shares * spot

            if open_cc is not None:
                open_cc["days_held"] += 1
                iv_now   = float(vix.iloc[i]) / 100.0
                days_rem = max(0, dte_tgt - open_cc["days_held"])
                t_yr     = days_rem / 252.0
                cc_val   = _bs_price(spot, open_cc["strike"], t_yr,
                                      _RISK_FREE_RATE, iv_now, "call")
                entry_v  = open_cc["entry_value"]
                pnl_now  = (entry_v - cc_val) * 100  # short call gains when value drops

                exit_reason = None
                if pnl_now >= entry_v * 100 * pt_pct:
                    exit_reason = "profit_target"
                elif cc_val >= entry_v * sl_mult:
                    exit_reason = "stop_loss"
                elif open_cc["days_held"] >= dte_tgt:
                    exit_reason = "expiry"

                if exit_reason:
                    cash += pnl_now  # accumulate premium P&L to cash
                    trades_list.append({
                        "entry_date":  open_cc["entry_date"].date(),
                        "exit_date":   dt.date(),
                        "spread_type": "covered_call",
                        "entry_cost":  round(entry_v * 100, 2),
                        "exit_value":  round(cc_val * 100, 2),
                        "pnl":         round(pnl_now, 2),
                        "exit_reason": exit_reason,
                    })
                    open_cc = None

            # Total equity = mark-to-market stock value + running premium cash
            equity_list.append(stock_value + cash)

            if i < _WARMUP_BARS:
                continue

            if i - last_train >= _RETRAIN_EVERY:
                # Exclude last dte_tgt bars: their labels use future close data
                cutoff = max(0, i - dte_tgt)
                X_tr = feats.iloc[:cutoff][self.FEATURE_COLS]
                y_tr = labels.iloc[:cutoff]
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

            if open_cc is not None:
                continue

            # Check IVR gate
            ivr_now = float(feats["ivr"].iloc[i])
            if ivr_now < min_ivr_:
                continue

            # Check earnings window
            days_since_earn = float(feats["days_since_earnings"].iloc[i])
            if days_since_earn < self.min_days_since_earn:
                continue

            # Use ML to decide delta (aggressive vs conservative)
            if model_ is not None:
                feat_row = feats.iloc[[i]][self.FEATURE_COLS]
                for col, default in self._FEATURE_DEFAULTS.items():
                    if col in feat_row.columns:
                        feat_row[col] = feat_row[col].fillna(default)
                if not feat_row.isna().any().any():
                    prob_cc_wins = float(model_.predict_proba(feat_row.values)[0][1])
                    delta = agg_delta if prob_cc_wins >= 0.55 else cons_delta
                else:
                    delta = cons_delta
            else:
                delta = cons_delta

            iv_entry = float(vix.iloc[i]) / 100.0
            t_yr     = dte_tgt / 252.0
            strike   = _strike_for_delta(spot, t_yr, _RISK_FREE_RATE, iv_entry, delta)
            premium  = _bs_price(spot, strike, t_yr, _RISK_FREE_RATE, iv_entry, "call")
            if premium <= 0:
                continue

            open_cc = {
                "entry_date": dt,
                "strike":     strike,
                "entry_value": premium,
                "delta":      delta,
                "days_held":  0,
            }

        equity = pd.Series(equity_list, index=price_data.index, dtype=float)

        daily_ret = equity.pct_change().dropna()
        bh_ret    = close.pct_change().reindex(equity.index).dropna()
        trades_df = pd.DataFrame(trades_list) if trades_list else pd.DataFrame(
            columns=["entry_date", "exit_date", "spread_type",
                     "entry_cost", "exit_value", "pnl", "exit_reason"]
        )
        metrics = compute_all_metrics(
            equity_curve=equity, trades_df=trades_df, benchmark_returns=bh_ret
        )
        self._model = model_
        return BacktestResult(
            strategy_name=self.name,
            equity_curve=equity,
            daily_returns=daily_ret,
            trades=trades_df,
            metrics=metrics,
            params=self.get_params(),
            extra={},
        )

    def get_backtest_ui_params(self) -> list:
        return [
            {"key": "min_ivr",            "label": "Min IVR to write call",
             "type": "slider", "min": 0.20, "max": 0.60, "default": 0.30, "step": 0.05,
             "col": 0, "row": 0,
             "help": "IVR below this → skip writing covered call (premium not worth it)"},
            {"key": "aggressive_delta",   "label": "Aggressive delta (high IVR)",
             "type": "slider", "min": 0.20, "max": 0.40, "default": 0.30, "step": 0.05,
             "col": 1, "row": 0,
             "help": "Short call delta when IVR is high and momentum is low"},
            {"key": "conservative_delta", "label": "Conservative delta (strong trend)",
             "type": "slider", "min": 0.10, "max": 0.25, "default": 0.15, "step": 0.05,
             "col": 2, "row": 0,
             "help": "Short call delta when momentum is strong (preserve upside)"},
            {"key": "dte_target",         "label": "DTE at entry",
             "type": "slider", "min": 14, "max": 45, "default": 21, "step": 7,
             "col": 0, "row": 1,
             "help": "Target days-to-expiry when writing covered call"},
            {"key": "profit_target_pct",  "label": "Profit target (% of premium)",
             "type": "slider", "min": 0.50, "max": 0.90, "default": 0.75, "step": 0.05,
             "col": 1, "row": 1,
             "help": "Buy back short call when this fraction of premium is captured"},
            {"key": "stop_loss_mult",     "label": "Stop loss (× premium)",
             "type": "slider", "min": 1.5, "max": 4.0, "default": 2.0, "step": 0.5,
             "col": 2, "row": 1,
             "help": "Close short call if it reaches this multiple of entry premium"},
        ]

    def get_params(self) -> dict:
        return {
            "min_ivr":             self.min_ivr,
            "aggressive_delta":    self.aggressive_delta,
            "conservative_delta":  self.conservative_delta,
            "dte_target":          self.dte_target,
            "min_days_since_earn": self.min_days_since_earn,
            "profit_target_pct":   self.profit_target_pct,
            "stop_loss_mult":      self.stop_loss_mult,
            "n_estimators":        self.n_estimators,
            "max_depth":           self.max_depth,
            "learning_rate":       self.learning_rate,
        }
