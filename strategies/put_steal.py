"""
Put Steal (Short Stock Interest Arbitrage) AI Strategy.

THESIS
------
Barraclough & Whaley (2011) document that retail put option holders
systematically fail to exercise deep in-the-money American puts early —
even when early exercise is clearly optimal. The criterion for immediate
exercise is:

    NII = X(1 - e^{-rT}) - c(S, X, T, r, σ) > 0         [Eq. 3, paper]

where:
  X  = put strike
  r  = risk-free rate
  T  = time to expiry (years)
  c  = Black-Scholes call price with same S, X, T (the "caput")

When NII > 0 the interest income earned by exercising immediately exceeds
the call-option value of waiting. Retail longs don't exercise, forfeiting
NII to the short put holder. Over Jan 1996–Sep 2008 this mis-exercise
cost put holders $1.9 billion.

TRADING EDGE
------------
We sell bull put spreads on stocks where NII > threshold:
  - Short put: slightly ITM (itm_pct below spot) — captures forfeited premium
  - Long put:  wing_pct further below short         — defines max loss
The AI layer predicts whether the stock will stay above the short strike
over the spread's life, filtering out high-crash-risk entries.

WALK-FORWARD TRAINING
---------------------
  - Expanding window (no future data in labels or features)
  - Warmup: 90 bars
  - Retrain every 20 bars

FEATURE SET (12 features)
--------------------------
  Interest arb: nii_level, nii_to_credit_ratio, call_to_put_ratio
  Rate:         risk_free_rate (proxy: 3m T-bill)
  Stock:        ret_5d, ret_20d, dist_from_ma50, atr_pct
  Vol:          iv_level, ivr_20d, iv_5d_change
  Market:       vix_level

LABEL CONSTRUCTION
------------------
  1 if spot > short_strike (= spot × (1 - itm_pct)) over n_forward days
  i.e., the bull put spread expires fully profitable.
  Positive rate: ~65-70% (bull put survives when stock stays stable / recovers).
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
_RETRAIN_EVERY    = 20
_SAVED_MODELS_DIR = Path(__file__).parent.parent / "saved_models"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _bs_price(S: float, K: float, T: float, r: float, sigma: float,
              option_type: str) -> float:
    """Black-Scholes European option price."""
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        intrinsic = max(0.0, S - K) if option_type == "call" else max(0.0, K - S)
        return intrinsic
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    if option_type == "call":
        return float(S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2))
    return float(K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1))


def _compute_nii(S: float, X: float, T: float, r: float, sigma: float) -> float:
    """
    Net Interest Income for early exercise of a deep ITM put.

    NII = X(1 - e^{-rT}) - c(S, X, T, r, σ)

    Positive NII means early exercise is optimal: the interest earned on
    the strike exceeds the time value embedded in the corresponding call.
    When NII > 0, retail longs who don't exercise forfeit this to shorts.
    """
    if T <= 0:
        return 0.0
    interest_income = X * (1.0 - np.exp(-r * T))
    call_value      = _bs_price(S, X, T, r, sigma, "call")
    return float(interest_income - call_value)


def _build_features(
    close: pd.Series,
    high:  pd.Series,
    low:   pd.Series,
    vix:   pd.Series,
    rfr:   pd.Series,     # risk-free rate series (annualised, e.g. 0.045)
    itm_pct: float = 0.05,
    dte:     int   = 21,
) -> pd.DataFrame:
    """Build the 12-feature matrix for the put-steal GBM classifier."""
    T       = dte / 365.0
    iv_rv   = close.pct_change().rolling(20, min_periods=10).std() * np.sqrt(252)

    # ── Core NII signal ────────────────────────────────────────────────────────
    nii_series = pd.Series(np.nan, index=close.index)
    call_vals  = pd.Series(np.nan, index=close.index)
    put_vals   = pd.Series(np.nan, index=close.index)
    for i in range(len(close)):
        S     = float(close.iloc[i])
        r     = float(rfr.iloc[i]) if not np.isnan(float(rfr.iloc[i])) else _RISK_FREE_RATE
        sigma = float(iv_rv.iloc[i]) if not np.isnan(float(iv_rv.iloc[i])) else 0.20
        if S <= 0 or sigma <= 0:
            continue
        X = S * (1.0 + itm_pct)       # strike is itm_pct above current spot
                                        # (a put at this strike is itm_pct ITM)
        nii_series.iloc[i] = _compute_nii(S, X, T, r, sigma)
        call_vals.iloc[i]  = _bs_price(S, X, T, r, sigma, "call")
        put_vals.iloc[i]   = _bs_price(S, X, T, r, sigma, "put")

    nii_ma5    = nii_series.rolling(5,  min_periods=2).mean()
    put_filled = put_vals.replace(0, np.nan)
    # ratio: how much of the put value is the call (early exercise "leakage")
    call_to_put = (call_vals / put_filled).clip(0.0, 1.0)
    # NII relative to the theoretical credit we'd collect on a 5% ITM short put
    nii_to_cred = (nii_series / put_filled).clip(-1.0, 2.0)

    # ── IV features ───────────────────────────────────────────────────────────
    iv_level   = iv_rv
    iv_ma20    = iv_rv.rolling(20, min_periods=10).mean()
    ivr_20d    = ((iv_rv - iv_rv.rolling(20, min_periods=10).min()) /
                  (iv_rv.rolling(20, min_periods=10).max() -
                   iv_rv.rolling(20, min_periods=10).min() + 1e-8)).clip(0, 1)
    iv_5d_ch   = iv_rv.pct_change(5).clip(-1.0, 1.0)

    # ── Stock features ─────────────────────────────────────────────────────────
    ret_5d    = close.pct_change(5).clip(-0.5, 0.5)
    ret_20d   = close.pct_change(20).clip(-0.5, 0.5)
    ma50      = close.rolling(50, min_periods=20).mean()
    dist_ma50 = ((close - ma50) / ma50.replace(0, np.nan)).clip(-0.4, 0.4)

    prev_close = close.shift(1)
    tr    = pd.concat([high - low,
                        (high - prev_close).abs(),
                        (low  - prev_close).abs()], axis=1).max(axis=1)
    atr_pct = tr.rolling(14, min_periods=7).mean() / close.replace(0, np.nan)

    df = pd.DataFrame({
        "nii_level":        nii_series,
        "nii_ma5":          nii_ma5,
        "nii_to_cred":      nii_to_cred,
        "call_to_put":      call_to_put,
        "risk_free_rate":   rfr,
        "iv_level":         iv_level,
        "ivr_20d":          ivr_20d,
        "iv_5d_change":     iv_5d_ch,
        "ret_5d":           ret_5d,
        "ret_20d":          ret_20d,
        "dist_from_ma50":   dist_ma50,
        "atr_pct":          atr_pct,
        "vix_level":        vix,
    }, index=close.index)

    return df.ffill().bfill()


def _build_labels(
    close:    pd.Series,
    itm_pct:  float = 0.05,
    n_forward: int   = 21,
) -> pd.Series:
    """
    Label = 1 if spot > short_strike for ALL of the n_forward days.
    short_strike = spot_today × (1 - itm_pct).

    This is the condition under which a bull put spread with short strike
    at (1 - itm_pct)×S expires fully profitable (stock never breaches short).
    """
    labels = pd.Series(np.nan, index=close.index, dtype=float)
    for i in range(len(close) - n_forward):
        S_today      = float(close.iloc[i])
        short_strike = S_today * (1.0 - itm_pct)
        future_prices = close.iloc[i + 1: i + 1 + n_forward]
        if len(future_prices) < n_forward // 2:
            continue
        # Spread survives if stock stays above short strike the whole period
        labels.iloc[i] = 1.0 if float(future_prices.min()) > short_strike else 0.0
    return labels


# ── Strategy class ─────────────────────────────────────────────────────────────

class PutStealStrategy(BaseStrategy):
    """
    Put Steal AI Strategy — Short Stock Interest Arbitrage.

    Sells bull put spreads on stocks where NII > 0, exploiting retail put
    holders who fail to exercise early. The GBM classifier predicts whether
    the spread will survive (stock stays above short strike) over the holding
    period. Trade only entered when confidence is high AND NII > threshold.
    """

    name                 = "put_steal"
    display_name         = "Put Steal (Interest Arb)"
    strategy_type        = StrategyType.AI_DRIVEN
    status               = StrategyStatus.ACTIVE
    description          = (
        "Exploits retail put holders who fail to exercise deep ITM puts early, "
        "forfeiting interest income. Sells bull put spreads when NII > 0 "
        "(Barraclough-Whaley early exercise criterion). "
        "GBM classifier filters high-crash-risk entries. Walk-forward, 90-bar warmup."
    )
    asset_class          = "equities_options"
    typical_holding_days = 21
    target_sharpe        = 1.5

    FEATURE_COLS = [
        "nii_level", "nii_ma5", "nii_to_cred", "call_to_put",
        "risk_free_rate", "iv_level", "ivr_20d", "iv_5d_change",
        "ret_5d", "ret_20d", "dist_from_ma50", "atr_pct", "vix_level",
    ]

    _FEATURE_DEFAULTS = {
        "nii_level":       0.10,
        "nii_ma5":         0.10,
        "nii_to_cred":     0.30,
        "call_to_put":     0.20,
        "risk_free_rate":  0.045,
        "iv_level":        0.25,
        "ivr_20d":         0.50,
        "iv_5d_change":    0.00,
        "ret_5d":          0.00,
        "ret_20d":         0.00,
        "dist_from_ma50":  0.00,
        "atr_pct":         0.01,
        "vix_level":       18.0,
    }

    def __init__(
        self,
        nii_threshold:      float = 0.05,   # min NII ($/share) to consider a trade
        itm_pct:            float = 0.05,   # short put is this far ITM (5% above S)
        wing_pct:           float = 0.04,   # long put is wing_pct below short put
        dte_target:         int   = 21,
        dte_exit:           int   = 5,
        iv_max:             float = 0.60,   # skip entries if IV > 60% (panic)
        vix_max:            float = 40.0,
        confidence_thresh:  float = 0.55,
        profit_target_pct:  float = 0.50,
        stop_loss_mult:     float = 2.0,
        position_size_pct:  float = 0.02,
        n_estimators:       int   = 60,
        max_depth:          int   = 3,
        learning_rate:      float = 0.05,
    ):
        self.nii_threshold     = nii_threshold
        self.itm_pct           = itm_pct
        self.wing_pct          = wing_pct
        self.dte_target        = dte_target
        self.dte_exit          = dte_exit
        self.iv_max            = iv_max
        self.vix_max           = vix_max
        self.confidence_thresh = confidence_thresh
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
        path = _SAVED_MODELS_DIR / f"put_steal_{ticker}.pkl"
        with open(path, "wb") as f:
            pickle.dump(self._model, f)

    def load_model(self, ticker: str = "SPY") -> bool:
        path = _SAVED_MODELS_DIR / f"put_steal_{ticker}.pkl"
        if not path.exists():
            return False
        with open(path, "rb") as f:
            self._model = pickle.load(f)
        return True

    def is_trainable(self) -> bool:
        return True

    # ── Live signal ────────────────────────────────────────────────────────────

    def generate_signal(self, market_snapshot: dict) -> SignalResult:
        """
        Compute NII from live snapshot. SELL = sell bull put spread when NII > threshold.
        """
        S     = float(market_snapshot.get("spot", 100.0))
        r     = float(market_snapshot.get("risk_free_rate", _RISK_FREE_RATE))
        sigma = float(market_snapshot.get("iv_level", 0.25))
        vix   = float(market_snapshot.get("vix", 18.0))
        T     = self.dte_target / 365.0

        if vix > self.vix_max or sigma > self.iv_max:
            return SignalResult(
                strategy_name=self.name, signal="HOLD", confidence=0.3,
                position_size_pct=0.0,
                metadata={"reason": "high vol / panic", "vix": vix, "iv": sigma},
            )

        X   = S * (1.0 + self.itm_pct)
        nii = _compute_nii(S, X, T, r, sigma)

        if nii > self.nii_threshold:
            confidence = min(0.90, 0.55 + nii * 3.0)
            return SignalResult(
                strategy_name=self.name, signal="SELL", confidence=confidence,
                position_size_pct=self.position_size_pct,
                metadata={"nii": nii, "strike_X": X, "vix": vix, "iv": sigma, "r": r},
            )
        elif nii < -self.nii_threshold:
            # High caput — waiting has real value; no edge in selling
            return SignalResult(
                strategy_name=self.name, signal="HOLD", confidence=0.35,
                position_size_pct=0.0,
                metadata={"nii": nii, "reason": "caput > interest income"},
            )
        return SignalResult(
            strategy_name=self.name, signal="HOLD", confidence=0.4,
            position_size_pct=0.0,
            metadata={"nii": nii, "reason": "NII below threshold"},
        )

    # ── Params ─────────────────────────────────────────────────────────────────

    def get_params(self) -> dict:
        return {
            "nii_threshold":     self.nii_threshold,
            "itm_pct":           self.itm_pct,
            "wing_pct":          self.wing_pct,
            "dte_target":        self.dte_target,
            "dte_exit":          self.dte_exit,
            "iv_max":            self.iv_max,
            "vix_max":           self.vix_max,
            "confidence_thresh": self.confidence_thresh,
            "profit_target_pct": self.profit_target_pct,
            "stop_loss_mult":    self.stop_loss_mult,
            "position_size_pct": self.position_size_pct,
            "n_estimators":      self.n_estimators,
            "max_depth":         self.max_depth,
            "learning_rate":     self.learning_rate,
        }

    def get_backtest_ui_params(self) -> list[dict]:
        return [
            {"key": "nii_threshold",     "label": "Min NII ($/share)",  "type": "float",
             "min": 0.01, "max": 0.50, "step": 0.01, "default": self.nii_threshold},
            {"key": "itm_pct",           "label": "ITM % (short put)",  "type": "float",
             "min": 0.02, "max": 0.15, "step": 0.01, "default": self.itm_pct},
            {"key": "wing_pct",          "label": "Wing Width %",        "type": "float",
             "min": 0.02, "max": 0.10, "step": 0.01, "default": self.wing_pct},
            {"key": "dte_target",        "label": "DTE Target",          "type": "int",
             "min": 10,   "max": 45,   "step": 1,    "default": self.dte_target},
            {"key": "iv_max",            "label": "Max IV (skip entry)", "type": "float",
             "min": 0.30, "max": 1.00, "step": 0.05, "default": self.iv_max},
            {"key": "vix_max",           "label": "Max VIX",             "type": "float",
             "min": 25.0, "max": 60.0, "step": 1.0,  "default": self.vix_max},
            {"key": "confidence_thresh", "label": "AI Confidence Min",  "type": "float",
             "min": 0.40, "max": 0.80, "step": 0.05, "default": self.confidence_thresh},
            {"key": "profit_target_pct", "label": "Profit Target %",    "type": "float",
             "min": 0.30, "max": 0.80, "step": 0.05, "default": self.profit_target_pct},
            {"key": "stop_loss_mult",    "label": "Stop Loss Mult",      "type": "float",
             "min": 1.0,  "max": 4.0,  "step": 0.5,  "default": self.stop_loss_mult},
            {"key": "position_size_pct", "label": "Position Size %",     "type": "float",
             "min": 0.01, "max": 0.10, "step": 0.01, "default": self.position_size_pct},
            {"key": "n_estimators",      "label": "GBM Trees",           "type": "int",
             "min": 20,   "max": 200,  "step": 10,   "default": self.n_estimators},
        ]

    # ── Backtest ───────────────────────────────────────────────────────────────

    def backtest(
        self,
        price_data:         pd.DataFrame,
        auxiliary_data:     dict,
        starting_capital:   float = 100_000,
        nii_threshold:      float | None = None,
        itm_pct:            float | None = None,
        wing_pct:           float | None = None,
        dte_target:         int   | None = None,
        dte_exit:           int   | None = None,
        iv_max:             float | None = None,
        vix_max:            float | None = None,
        confidence_thresh:  float | None = None,
        profit_target_pct:  float | None = None,
        stop_loss_mult:     float | None = None,
        position_size_pct:  float | None = None,
        n_estimators:       int   | None = None,
        max_depth:          int   | None = None,
        learning_rate:      float | None = None,
    ) -> BacktestResult:

        # ── Apply overrides ────────────────────────────────────────────────────
        nii_thr  = nii_threshold     if nii_threshold     is not None else self.nii_threshold
        itm_p    = itm_pct           if itm_pct           is not None else self.itm_pct
        wing_p   = wing_pct          if wing_pct          is not None else self.wing_pct
        dte_tgt  = dte_target        if dte_target        is not None else self.dte_target
        dte_ex   = dte_exit          if dte_exit          is not None else self.dte_exit
        iv_mx    = iv_max            if iv_max            is not None else self.iv_max
        vix_mx   = vix_max           if vix_max           is not None else self.vix_max
        conf_min = confidence_thresh if confidence_thresh is not None else self.confidence_thresh
        pt_pct   = profit_target_pct if profit_target_pct is not None else self.profit_target_pct
        sl_mult  = stop_loss_mult    if stop_loss_mult    is not None else self.stop_loss_mult
        pos_pct  = position_size_pct if position_size_pct is not None else self.position_size_pct
        n_est    = n_estimators      if n_estimators      is not None else self.n_estimators
        m_dep    = max_depth         if max_depth         is not None else self.max_depth
        lr       = learning_rate     if learning_rate     is not None else self.learning_rate

        # ── Validate data ──────────────────────────────────────────────────────
        required = {"close", "high", "low"}
        if not required.issubset(price_data.columns):
            return BacktestResult(
                strategy_name=self.name,
                error=f"Missing columns: {required - set(price_data.columns)}",
            )

        close = price_data["close"].astype(float)
        high  = price_data["high"].astype(float)
        low   = price_data["low"].astype(float)

        if len(close) < _WARMUP_BARS + dte_tgt + 10:
            return BacktestResult(
                strategy_name=self.name,
                error=f"Need ≥ {_WARMUP_BARS + dte_tgt + 10} bars, got {len(close)}",
            )

        # ── VIX series ─────────────────────────────────────────────────────────
        vix_data = auxiliary_data.get("vix", {})
        if isinstance(vix_data, pd.DataFrame) and "close" in vix_data.columns:
            vix_raw = vix_data["close"].reindex(close.index).ffill().bfill()
        elif isinstance(vix_data, pd.Series):
            vix_raw = vix_data.reindex(close.index).ffill().bfill()
        else:
            vix_raw = pd.Series(18.0, index=close.index)

        # ── Risk-free rate series ──────────────────────────────────────────────
        rates_data = auxiliary_data.get("rates") or auxiliary_data.get("rate10y", {})
        if isinstance(rates_data, pd.DataFrame) and "close" in rates_data.columns:
            rfr = (rates_data["close"] / 100.0).reindex(close.index).ffill().bfill()
        elif isinstance(rates_data, pd.Series):
            rfr = (rates_data / 100.0).reindex(close.index).ffill().bfill()
        else:
            rfr = pd.Series(_RISK_FREE_RATE, index=close.index)

        # ── Build features & labels ────────────────────────────────────────────
        feats  = _build_features(close, high, low, vix_raw, rfr,
                                  itm_pct=itm_p, dte=dte_tgt)
        labels = _build_labels(close, itm_pct=itm_p, n_forward=dte_tgt)

        feat_cols = [c for c in self.FEATURE_COLS if c in feats.columns]

        # ── Walk-forward simulation ────────────────────────────────────────────
        from sklearn.ensemble import GradientBoostingClassifier

        capital       = starting_capital
        equity_list   = []
        trade_log     = []
        open_trade    = None
        last_rebal    = _WARMUP_BARS
        model         = None
        n_wins = n_losses = 0

        for i in range(_WARMUP_BARS, len(close)):
            spot = float(close.iloc[i])
            vix  = float(vix_raw.iloc[i])
            r    = float(rfr.iloc[i])
            iv   = float(feats["iv_level"].iloc[i]) if "iv_level" in feats.columns else 0.25

            # ── Retrain ────────────────────────────────────────────────────────
            if model is None or (i - last_rebal) >= _RETRAIN_EVERY:
                cutoff = max(0, i - dte_tgt)
                X_tr   = feats[feat_cols].iloc[:cutoff].dropna()
                y_tr   = labels.iloc[:cutoff].reindex(X_tr.index).dropna()
                X_tr   = X_tr.loc[y_tr.index]
                if len(X_tr) >= 40 and y_tr.nunique() == 2:
                    try:
                        model = GradientBoostingClassifier(
                            n_estimators=n_est, max_depth=m_dep,
                            learning_rate=lr, random_state=42,
                        )
                        model.fit(X_tr, y_tr)
                        last_rebal = i
                    except Exception:
                        model = None

            # ── Manage open trade ──────────────────────────────────────────────
            if open_trade is not None:
                bars_held = i - open_trade["entry_bar"]
                current_spread_val = _bs_price(
                    spot, open_trade["short_K"], (dte_tgt - bars_held) / 365.0,
                    r, max(iv, 0.01), "put"
                ) - _bs_price(
                    spot, open_trade["long_K"], (dte_tgt - bars_held) / 365.0,
                    r, max(iv, 0.01), "put"
                )
                pnl_now = (open_trade["credit"] - current_spread_val) * 100

                # Profit target
                if pnl_now >= open_trade["max_profit"] * pt_pct:
                    capital += pnl_now
                    n_wins  += 1
                    trade_log.append({
                        "entry": str(close.index[open_trade["entry_bar"]].date()),
                        "exit":  str(close.index[i].date()),
                        "pnl":   round(pnl_now, 2),
                        "result": "profit_target",
                    })
                    open_trade = None

                # Stop loss
                elif pnl_now <= -open_trade["max_loss"] * sl_mult:
                    capital += pnl_now
                    n_losses += 1
                    trade_log.append({
                        "entry": str(close.index[open_trade["entry_bar"]].date()),
                        "exit":  str(close.index[i].date()),
                        "pnl":   round(pnl_now, 2),
                        "result": "stop_loss",
                    })
                    open_trade = None

                # DTE exit
                elif bars_held >= dte_tgt - dte_ex:
                    pnl_exit = (open_trade["credit"] - max(0.0, current_spread_val)) * 100
                    capital += pnl_exit
                    if pnl_exit >= 0:
                        n_wins  += 1
                    else:
                        n_losses += 1
                    trade_log.append({
                        "entry": str(close.index[open_trade["entry_bar"]].date()),
                        "exit":  str(close.index[i].date()),
                        "pnl":   round(pnl_exit, 2),
                        "result": "dte_exit",
                    })
                    open_trade = None

            equity_list.append(capital)

            # ── Entry logic ────────────────────────────────────────────────────
            if open_trade is not None:
                continue
            if vix > vix_mx or iv > iv_mx:
                continue

            # NII gate
            T   = dte_tgt / 365.0
            X   = spot * (1.0 + itm_p)
            nii = _compute_nii(spot, X, T, r, max(iv, 0.01))
            if nii < nii_thr:
                continue

            # AI gate
            if model is not None:
                row = feats[feat_cols].iloc[i:i+1]
                if row.isna().any().any():
                    continue
                prob_survive = float(model.predict_proba(row)[0][1])
                if prob_survive < conf_min:
                    continue
            else:
                continue  # no model yet

            # Size & strikes
            short_K  = spot * (1.0 - itm_p)          # short put = itm_p below spot
            long_K   = short_K * (1.0 - wing_p)       # long put  = wing_p below short
            credit   = (
                _bs_price(spot, short_K, T, r, iv, "put") -
                _bs_price(spot, long_K,  T, r, iv, "put")
            )
            wing_w   = short_K - long_K
            max_loss  = max(0.01, (wing_w - credit) * 100)
            max_prof  = credit * 100
            n_spread  = max(1, int((capital * pos_pct) / max_loss))

            if credit < 0.05 or max_loss <= 0:
                continue

            open_trade = {
                "entry_bar": i,
                "short_K":   short_K,
                "long_K":    long_K,
                "credit":    credit,
                "max_profit": max_prof,
                "max_loss":   max_loss,
                "n_spread":   n_spread,
                "nii":        nii,
            }

        # ── Close any open position at end ─────────────────────────────────────
        if open_trade is not None:
            last_spot = float(close.iloc[-1])
            last_r    = float(rfr.iloc[-1])
            last_iv   = float(feats["iv_level"].iloc[-1]) if "iv_level" in feats.columns else 0.20
            bars_held = len(close) - 1 - open_trade["entry_bar"]
            rem_T     = max(0, dte_tgt - bars_held) / 365.0
            final_val = (
                _bs_price(last_spot, open_trade["short_K"], rem_T, last_r, max(last_iv, 0.01), "put") -
                _bs_price(last_spot, open_trade["long_K"],  rem_T, last_r, max(last_iv, 0.01), "put")
            )
            pnl_final = (open_trade["credit"] - max(0.0, final_val)) * 100
            capital += pnl_final
            equity_list[-1] = capital
            trade_log.append({
                "entry": str(close.index[open_trade["entry_bar"]].date()),
                "exit":  str(close.index[-1].date()),
                "pnl":   round(pnl_final, 2),
                "result": "end_of_data",
            })
            if pnl_final >= 0:
                n_wins += 1
            else:
                n_losses += 1

        # ── Metrics ───────────────────────────────────────────────────────────
        equity_series = pd.Series(equity_list, index=close.index[_WARMUP_BARS:])
        trades_df     = pd.DataFrame(trade_log) if trade_log else pd.DataFrame()
        metrics       = compute_all_metrics(equity_curve=equity_series, trades_df=trades_df)
        total_trades  = n_wins + n_losses
        win_rate      = n_wins / total_trades if total_trades else 0.0

        daily_returns = equity_series.pct_change().fillna(0.0)
        return BacktestResult(
            strategy_name = self.name,
            equity_curve  = equity_series,
            daily_returns = daily_returns,
            trades        = trades_df,
            metrics       = metrics,
            params        = {
                "nii_threshold":      self.nii_threshold,
                "itm_pct":            self.itm_pct,
                "dte":                self.dte,
                "ai_confidence_min":  self.ai_confidence_min,
                "vix_max":            self.vix_max,
                "iv_max":             self.iv_max,
            },
            extra         = {
                "n_wins":        n_wins,
                "n_losses":      n_losses,
                "win_rate":      win_rate,
                "total_trades":  total_trades,
                "final_capital": round(capital, 2),
            },
        )
