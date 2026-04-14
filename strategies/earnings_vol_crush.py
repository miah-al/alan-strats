"""
Earnings Volatility Crush AI Strategy.

THESIS
------
After earnings announcements, implied volatility collapses 30-60% within 1-3 trading
days as the binary uncertainty event resolves. This IV crush is mechanical and
calendar-driven — it happens regardless of whether the earnings were good or bad.
The trade enters a credit spread immediately AFTER the announcement (T+0 or T+1),
when IV is still artificially elevated from pre-announcement fear, but the directional
risk is now known (the gap has already happened). The AI layer predicts:
  (1) How large the IV crush will be (favoring larger-crush names)
  (2) Whether the stock will stay contained (not extend its gap) over the next 10 days

WALK-FORWARD TRAINING
---------------------
  - Warmup: 90 earnings events before first prediction (cycles, not calendar bars)
  - Retrain every 15 new events
  - Label: binary — did the stock stay within ±8% of the gap close over 10 days?

FEATURE SET (10 features)
--------------------------
  ivr:              IVR at time of earnings announcement
  earnings_gap_pct: Actual price gap on announcement day (signed)
  abs_gap_pct:      Absolute magnitude of gap
  vix_level:        Market vol at time of announcement
  realized_vol_20d: Stock's recent realized vol (normalized move magnitude)
  gap_vs_rv:        Gap as multiple of 20d realized vol
  adx:              Trend strength (high ADX = directional; risky for credit)
  ret_20d:          20-day return before earnings (momentum context)
  dist_from_ma50:   Distance from 50-day MA (mean-reversion potential)
  days_to_month_end: Calendar effect — options pinning near expiry

LABEL CONSTRUCTION
------------------
  contained_10d = 1 if max(|close - gap_close|) / gap_close ≤ 0.08 over next 10 days
  This is the credit spread survival condition: stock must not extend 8% beyond gap.
  Positive rate: ~65% (most earnings gaps are "one and done").
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
_WARMUP_EVENTS    = 30      # earnings events before first ML prediction
_RETRAIN_EVERY    = 10      # events between retrains
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


def _spread_credit(S, short_K, long_K, T, r, iv, spread_type):
    if spread_type == "bull_put":
        return _bs_price(S, short_K, T, r, iv, "put") - _bs_price(S, long_K, T, r, iv, "put")
    return _bs_price(S, short_K, T, r, iv, "call") - _bs_price(S, long_K, T, r, iv, "call")


def _spread_value_at_expiry(spot, short_K, long_K, spread_type):
    """Intrinsic value of spread at expiry."""
    if spread_type == "bull_put":
        return max(0, short_K - spot) - max(0, long_K - spot)
    return max(0, spot - short_K) - max(0, spot - long_K)


def _compute_adx(high, low, close, period=14):
    ph, pl, pc = high.shift(1), low.shift(1), close.shift(1)
    tr  = pd.concat([high - low, (high - pc).abs(), (low - pc).abs()], axis=1).max(axis=1)
    dmp = (high - ph).clip(lower=0.0).where((high - ph) > (pl - low), 0.0)
    dmm = (pl - low).clip(lower=0.0).where((pl - low) > (high - ph), 0.0)
    atr_s = tr.rolling(period, min_periods=period // 2).mean()
    dip   = 100 * dmp.rolling(period, min_periods=period // 2).mean() / atr_s.replace(0, np.nan)
    dim   = 100 * dmm.rolling(period, min_periods=period // 2).mean() / atr_s.replace(0, np.nan)
    dx    = 100 * (dip - dim).abs() / (dip + dim).replace(0, np.nan)
    return dx.rolling(period, min_periods=period // 2).mean().fillna(20.0)


def _detect_earnings_gaps(close: pd.Series, threshold: float = 0.03) -> pd.Series:
    """
    Proxy for earnings dates: days with gap > threshold and no adjacent gap.
    In live use, real earnings dates come from Polygon API.
    Returns a boolean Series (True on earnings gap days).
    """
    daily_ret = close.pct_change().abs()
    # Rolling max to avoid adjacent gaps on multi-day moves
    gap_days = (daily_ret > threshold) & (daily_ret.shift(1).fillna(0) < threshold * 0.5)
    return gap_days


# ── Strategy class ─────────────────────────────────────────────────────────────

class EarningsVolCrushStrategy(BaseStrategy):
    """
    Earnings Volatility Crush AI strategy.

    After a large earnings gap, sells a credit spread (bear call if gapped up,
    bull put if gapped down) targeting residual IV premium compression.
    GBM classifier predicts whether the stock stays contained over hold period.
    Only enters when P(contained) ≥ min_confidence.
    """

    name                 = "earnings_vol_crush"
    display_name         = "Earnings Vol Crush — AI"
    strategy_type        = StrategyType.AI_DRIVEN
    status               = StrategyStatus.ACTIVE
    description          = (
        "AI-powered earnings IV crush. Enters credit spread after earnings gap "
        "when IV is still elevated but directional risk is resolved. "
        "GBM predicts P(stock contained) using gap magnitude, IVR, and vol context."
    )
    asset_class          = "equities_options"
    typical_holding_days = 10
    target_sharpe        = 1.2

    FEATURE_COLS = [
        "ivr", "earnings_gap_pct", "abs_gap_pct", "vix_level",
        "realized_vol_20d", "gap_vs_rv", "adx", "ret_20d",
        "dist_from_ma50", "days_to_month_end",
    ]

    _FEATURE_DEFAULTS = {
        "ivr":              0.50,
        "earnings_gap_pct": 0.0,
        "abs_gap_pct":      0.05,
        "vix_level":        20.0,
        "realized_vol_20d": 0.25,
        "gap_vs_rv":        2.0,
        "adx":              20.0,
        "ret_20d":          0.0,
        "dist_from_ma50":   0.0,
        "days_to_month_end": 10,
    }

    def __init__(
        self,
        min_gap_pct:        float = 0.03,  # minimum gap to consider an earnings event
        min_confidence:     float = 0.60,  # P(contained) ≥ this to enter
        containment_pct:    float = 0.08,  # label: gap must not extend > 8%
        hold_days:          int   = 10,
        dte_target:         int   = 14,
        buffer_pct:         float = 0.03,  # short strike set 3% beyond gap
        wing_width_pct:     float = 0.05,  # wing width 5% of spot
        profit_target_pct:  float = 0.50,
        stop_loss_mult:     float = 2.0,
        position_size_pct:  float = 0.02,
        vix_max:            float = 45.0,
        n_estimators:       int   = 50,
        max_depth:          int   = 2,
        learning_rate:      float = 0.05,
    ):
        self.min_gap_pct       = min_gap_pct
        self.min_confidence    = min_confidence
        self.containment_pct   = containment_pct
        self.hold_days         = hold_days
        self.dte_target        = dte_target
        self.buffer_pct        = buffer_pct
        self.wing_width_pct    = wing_width_pct
        self.profit_target_pct = profit_target_pct
        self.stop_loss_mult    = stop_loss_mult
        self.position_size_pct = position_size_pct
        self.vix_max           = vix_max
        self.n_estimators      = n_estimators
        self.max_depth         = max_depth
        self.learning_rate     = learning_rate
        self._model            = None

    def save_model(self, ticker: str = "SPY"):
        if self._model is None:
            return
        _SAVED_MODELS_DIR.mkdir(exist_ok=True)
        path = _SAVED_MODELS_DIR / f"earnings_vol_crush_{ticker}.pkl"
        with open(path, "wb") as f:
            pickle.dump(self._model, f)

    def load_model(self, ticker: str = "SPY") -> bool:
        path = _SAVED_MODELS_DIR / f"earnings_vol_crush_{ticker}.pkl"
        if not path.exists():
            return False
        with open(path, "rb") as f:
            self._model = pickle.load(f)
        return True

    def is_trainable(self) -> bool:
        return True

    def generate_signal(self, market_snapshot: dict) -> SignalResult:
        gap_pct = float(market_snapshot.get("earnings_gap_pct", 0.0))
        ivr     = float(market_snapshot.get("ivr", 0.5))
        vix     = float(market_snapshot.get("vix", 20.0))

        if abs(gap_pct) >= self.min_gap_pct and ivr >= 0.40:
            signal = "SELL" if gap_pct > 0 else "BUY"
            confidence = min(0.80, 0.50 + abs(gap_pct) * 3)
        else:
            signal, confidence = "HOLD", 0.3

        return SignalResult(
            strategy_name=self.name,
            signal=signal,
            confidence=confidence,
            position_size_pct=self.position_size_pct if signal != "HOLD" else 0.0,
            metadata={"earnings_gap_pct": gap_pct, "ivr": ivr, "vix": vix},
        )

    def backtest(
        self,
        price_data:         pd.DataFrame,
        auxiliary_data:     dict,
        starting_capital:   float = 100_000,
        min_gap_pct:        float | None = None,
        min_confidence:     float | None = None,
        hold_days:          int   | None = None,
        buffer_pct:         float | None = None,
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
            raise ImportError("scikit-learn required") from e

        gap_min  = min_gap_pct       if min_gap_pct       is not None else self.min_gap_pct
        conf_min = min_confidence    if min_confidence    is not None else self.min_confidence
        h_days   = hold_days         if hold_days         is not None else self.hold_days
        buf      = buffer_pct        if buffer_pct        is not None else self.buffer_pct
        wing     = wing_width_pct    if wing_width_pct    is not None else self.wing_width_pct
        pt_pct   = profit_target_pct if profit_target_pct is not None else self.profit_target_pct
        sl_mult  = stop_loss_mult    if stop_loss_mult    is not None else self.stop_loss_mult

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

        # Build features
        rv20   = close.pct_change().rolling(20, min_periods=10).std() * np.sqrt(252)
        adx_s  = _compute_adx(high, low, close)
        ivr    = ((vix - vix.rolling(252, min_periods=60).min()) /
                  (vix.rolling(252, min_periods=60).max() -
                   vix.rolling(252, min_periods=60).min()).replace(0, np.nan)).clip(0, 1)
        ma50   = close.rolling(50, min_periods=20).mean()
        d_ma50 = ((close - ma50) / ma50.replace(0, np.nan)).clip(-0.3, 0.3)
        ret20  = close.pct_change(20)
        gap    = close.pct_change()  # daily return as gap proxy
        month_end_days = pd.Series(
            [(_d + pd.offsets.MonthEnd(0) - _d).days for _d in close.index],
            index=close.index, dtype=float
        )

        earnings_gaps = _detect_earnings_gaps(close, threshold=gap_min)

        # Build feature matrix for ML
        feat_df = pd.DataFrame({
            "ivr":              ivr,
            "earnings_gap_pct": gap,
            "abs_gap_pct":      gap.abs(),
            "vix_level":        vix,
            "realized_vol_20d": rv20,
            "gap_vs_rv":        (gap.abs() / rv20.replace(0, np.nan)).clip(0, 10),
            "adx":              adx_s,
            "ret_20d":          ret20,
            "dist_from_ma50":   d_ma50,
            "days_to_month_end": month_end_days,
        }).ffill().bfill()

        # Build labels: did the stock stay contained over h_days after gap?
        labels = pd.Series(np.nan, index=close.index)
        for i in range(len(close) - h_days):
            if not earnings_gaps.iloc[i]:
                continue
            entry_px = float(close.iloc[i])
            if entry_px <= 0:
                continue
            fwd = close.iloc[i + 1: i + 1 + h_days]
            max_ext = (fwd - entry_px).abs().max() / entry_px
            labels.iloc[i] = 1.0 if max_ext <= self.containment_pct else 0.0

        all_dates   = list(price_data.index)
        capital     = float(starting_capital)
        equity_list = []
        trades_list = []
        open_trade  = None
        model_      = None
        events_seen = 0
        last_train  = -999

        for i, dt in enumerate(all_dates):
            if open_trade is not None:
                open_trade["days_held"] += 1
                spot    = float(close.iloc[i])
                iv_now  = float(vix.iloc[i]) / 100.0
                days_rem = max(0, h_days - open_trade["days_held"])
                t_yr    = days_rem / 252.0
                st      = open_trade["spread_type"]

                pnl_now = (_spread_value_at_expiry(spot, open_trade["short_strike"],
                             open_trade["long_strike"], st)
                           if days_rem == 0
                           else (_spread_credit(spot, open_trade["short_strike"],
                                  open_trade["long_strike"], t_yr, _RISK_FREE_RATE, iv_now, st)))

                entry_v    = open_trade["entry_value"]
                pnl_dollar = (entry_v - pnl_now) * 100 if True else 0.0  # credit trade
                max_profit = open_trade["max_profit"]

                exit_reason = None
                if pnl_dollar >= max_profit * pt_pct:
                    exit_reason = "profit_target"
                elif pnl_dollar <= -open_trade["max_loss"] * sl_mult:
                    exit_reason = "stop_loss"
                elif open_trade["days_held"] >= h_days:
                    exit_reason = "hold_days"

                if exit_reason:
                    capital += pnl_dollar
                    trades_list.append({
                        "entry_date":  open_trade["entry_date"].date(),
                        "exit_date":   dt.date(),
                        "spread_type": open_trade["spread_type"],
                        "entry_cost":  round(open_trade["entry_value"] * 100, 2),
                        "exit_value":  round(pnl_now * 100, 2),
                        "pnl":         round(pnl_dollar, 2),
                        "exit_reason": exit_reason,
                    })
                    open_trade = None

            equity_list.append(capital)

            if not earnings_gaps.iloc[i]:
                continue

            events_seen += 1

            if events_seen < _WARMUP_EVENTS:
                continue

            # Retrain
            if events_seen - last_train >= _RETRAIN_EVERY:
                X_tr = feat_df.iloc[:i][self.FEATURE_COLS]
                y_tr = labels.iloc[:i]
                # only use earnings event rows
                ev_mask = earnings_gaps.iloc[:i]
                X_tr = X_tr[ev_mask]
                y_tr = y_tr[ev_mask]
                valid = y_tr.notna() & X_tr.notna().all(axis=1)
                X_tr, y_tr = X_tr[valid], y_tr[valid]
                if len(y_tr) >= 15 and y_tr.nunique() >= 2:
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
                    last_train = events_seen

            if model_ is None or open_trade is not None:
                continue

            vix_now = float(vix.iloc[i])
            if vix_now > self.vix_max:
                continue

            feat_row = feat_df.iloc[[i]][self.FEATURE_COLS]
            for col, default in self._FEATURE_DEFAULTS.items():
                if col in feat_row.columns:
                    feat_row[col] = feat_row[col].fillna(default)
            if feat_row.isna().any().any():
                continue

            prob_contained = float(model_.predict_proba(feat_row.values)[0][1])
            if prob_contained < conf_min:
                continue

            spot     = float(close.iloc[i])
            gap_pct  = float(gap.iloc[i])
            iv_entry = float(vix.iloc[i]) / 100.0
            t_yr     = self.dte_target / 252.0
            wing_w   = spot * wing

            if gap_pct > 0:
                # Gap up → bear call credit spread above gap high
                short_K = round(spot * (1 + buf), 2)
                long_K  = round(short_K + wing_w, 2)
                stype   = "bear_call"
            else:
                # Gap down → bull put credit spread below gap low
                short_K = round(spot * (1 - buf), 2)
                long_K  = round(short_K - wing_w, 2)
                stype   = "bull_put"

            entry_v = _spread_credit(spot, short_K, long_K, t_yr, _RISK_FREE_RATE, iv_entry, stype)
            if entry_v <= 0:
                continue

            max_loss_  = (wing_w - entry_v) * 100
            max_profit = entry_v * 100

            open_trade = {
                "entry_date":   dt, "spread_type": stype,
                "short_strike": short_K, "long_strike": long_K,
                "entry_value":  entry_v, "max_profit": max_profit, "max_loss": max_loss_,
                "days_held": 0, "prob": prob_contained,
            }

        if open_trade is not None:
            trades_list.append({
                "entry_date":  open_trade["entry_date"].date(),
                "exit_date":   all_dates[-1].date(),
                "spread_type": open_trade["spread_type"],
                "entry_cost":  round(open_trade["entry_value"] * 100, 2),
                "exit_value":  0.0,
                "pnl":         0.0,
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
            {"key": "min_gap_pct",       "label": "Min earnings gap (%)",
             "type": "slider", "min": 0.02, "max": 0.08, "default": 0.03, "step": 0.01,
             "col": 0, "row": 0,
             "help": "Minimum one-day gap to classify as an earnings event"},
            {"key": "min_confidence",    "label": "Min confidence (P contained)",
             "type": "slider", "min": 0.50, "max": 0.80, "default": 0.60, "step": 0.05,
             "col": 1, "row": 0,
             "help": "ML must predict containment above this probability to enter"},
            {"key": "hold_days",         "label": "Hold days",
             "type": "slider", "min": 5, "max": 20, "default": 10, "step": 1,
             "col": 2, "row": 0,
             "help": "Maximum days to hold after earnings announcement"},
            {"key": "buffer_pct",        "label": "Strike buffer (% spot)",
             "type": "slider", "min": 0.01, "max": 0.06, "default": 0.03, "step": 0.01,
             "col": 0, "row": 1,
             "help": "Short strike placed this far beyond the earnings gap"},
            {"key": "wing_width_pct",    "label": "Wing width (% spot)",
             "type": "slider", "min": 0.03, "max": 0.08, "default": 0.05, "step": 0.01,
             "col": 1, "row": 1,
             "help": "Width of spread as percentage of spot price"},
            {"key": "profit_target_pct", "label": "Profit target (% max credit)",
             "type": "slider", "min": 0.30, "max": 0.75, "default": 0.50, "step": 0.05,
             "col": 2, "row": 1,
             "help": "Close at this fraction of maximum credit received"},
        ]

    def get_params(self) -> dict:
        return {
            "min_gap_pct":       self.min_gap_pct,
            "min_confidence":    self.min_confidence,
            "containment_pct":   self.containment_pct,
            "hold_days":         self.hold_days,
            "dte_target":        self.dte_target,
            "buffer_pct":        self.buffer_pct,
            "wing_width_pct":    self.wing_width_pct,
            "profit_target_pct": self.profit_target_pct,
            "stop_loss_mult":    self.stop_loss_mult,
            "position_size_pct": self.position_size_pct,
            "vix_max":           self.vix_max,
            "n_estimators":      self.n_estimators,
            "max_depth":         self.max_depth,
            "learning_rate":     self.learning_rate,
        }
