"""
Momentum Regime Debit Spread AI Strategy.

THESIS
------
Markets exhibit persistent momentum regimes predictable at 5-15 day horizons.
A plain momentum system takes full losses from whipsaws. This strategy expresses
directional momentum as a debit spread — capping maximum loss to the premium paid
while retaining asymmetric upside. The ML model's only job is to identify high-
conviction regime windows where the hit rate exceeds the breakeven threshold
(typically ~55% for an ATM debit spread). In ambiguous/choppy regimes, it stays flat.

LAYER 1 — REGIME CLASSIFIER (3-class GBM):
  Class 0: Chop / mean-reverting (stay flat)
  Class 1: Bullish momentum → bull call debit spread
  Class 2: Bearish momentum → bear put debit spread
  Label construction: 10-day forward return tercile (rolling regime-aware)
  Only trade when P(max_class) ≥ confidence_threshold

WALK-FORWARD TRAINING
---------------------
  - Warmup: 90 bars
  - Retrain every 15 bars
  - No look-ahead in features or labels

FEATURE SET (11 features)
--------------------------
  Momentum:   ret_5d, ret_20d, momentum_accel (5d minus 20d return)
  Vol:        atr_pct, realized_vol_20d
  VIX:        vix_level, vix_5d_change, vix_ma_ratio
  Trend:      dist_from_ma50, dist_from_ma200
  Calendar:   days_to_month_end

LABEL CONSTRUCTION
------------------
  10d forward return → rolling tercile classification (top = bull, bottom = bear, mid = chop)
  Tercile boundaries re-computed at each retrain point using trailing 252-bar window.
  This makes the label regime-adaptive rather than fixed-threshold.
"""

from __future__ import annotations

import logging
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
from alan_trader.backtest.engine import (
    bs_price_skew,
    DEFAULT_SLIPPAGE_PER_LEG,
    DEFAULT_COMMISSION_PER_LEG,
)
from alan_trader.risk.metrics import compute_all_metrics

logger = logging.getLogger(__name__)

_RISK_FREE_RATE   = 0.045
_WARMUP_BARS      = 90
_RETRAIN_EVERY    = 15
_SAVED_MODELS_DIR = Path(__file__).parent.parent / "saved_models"

_LABEL_CHOP  = 0
_LABEL_BULL  = 1
_LABEL_BEAR  = 2

# Two legs per debit spread (long + short). Frictions are applied per leg, on
# both entry and exit, scaled by the number of contracts.
_LEGS_PER_SPREAD = 2


# ── Helpers ────────────────────────────────────────────────────────────────────

def _debit_spread_value(S, long_K, short_K, T, r, atm_iv, spread_type):
    """Per-share value of a debit spread, priced with a realistic equity-index
    vol skew (downside strikes carry higher IV than upside strikes).

    Each leg is priced via :func:`bs_price_skew` so the OTM short wing reflects
    skew rather than a single flat ATM IV.
    """
    opt = "call" if spread_type == "bull_call" else "put"
    long_v  = bs_price_skew(S, long_K,  T, r, atm_iv, opt)
    short_v = bs_price_skew(S, short_K, T, r, atm_iv, opt)
    return float(long_v - short_v)


def _build_features(close, high, low, vix):
    prev_c  = close.shift(1)
    tr      = pd.concat([high - low, (high - prev_c).abs(),
                          (low - prev_c).abs()], axis=1).max(axis=1)
    atr_pct = tr.rolling(14, min_periods=7).mean() / close.replace(0, np.nan)
    rv20    = close.pct_change().rolling(20, min_periods=10).std() * np.sqrt(252)

    ret_5d  = close.pct_change(5)
    ret_20d = close.pct_change(20)
    mom_acc = ret_5d - ret_20d   # 5d momentum minus 20d = acceleration

    ma50    = close.rolling(50,  min_periods=20).mean()
    ma200   = close.rolling(200, min_periods=50).mean()
    d_ma50  = ((close - ma50)  / ma50.replace(0, np.nan)).clip(-0.3, 0.3)
    d_ma200 = ((close - ma200) / ma200.replace(0, np.nan)).clip(-0.3, 0.3)

    vix_5d  = vix.pct_change(5)
    vix_ma20 = vix.rolling(20, min_periods=10).mean()
    vix_rat  = (vix / vix_ma20.replace(0, np.nan)).clip(0.5, 2.5)

    month_end = pd.Series(
        [(_d + pd.offsets.MonthEnd(0) - _d).days for _d in close.index],
        index=close.index, dtype=float
    )

    return pd.DataFrame({
        "ret_5d":           ret_5d,
        "ret_20d":          ret_20d,
        "momentum_accel":   mom_acc,
        "atr_pct":          atr_pct,
        "realized_vol_20d": rv20,
        "vix_level":        vix,
        "vix_5d_change":    vix_5d,
        "vix_ma_ratio":     vix_rat,
        "dist_from_ma50":   d_ma50,
        "dist_from_ma200":  d_ma200,
        "days_to_month_end": month_end,
    }).ffill()  # ffill only — bfill leaks future values into early NaNs (walk-forward look-ahead)


def _build_labels(close: pd.Series, n_forward: int = 10,
                   lookback: int = 252) -> pd.Series:
    """
    3-class regime label using rolling tercile boundaries.
    Top tercile of n_forward return → BULL (1)
    Bottom tercile → BEAR (2)
    Middle tercile → CHOP (0)
    """
    fwd_ret = close.pct_change(n_forward).shift(-n_forward)
    labels  = pd.Series(np.nan, index=close.index, dtype=float)

    for i in range(lookback, len(close)):
        hist = fwd_ret.iloc[max(0, i - lookback): i].dropna()
        if len(hist) < 30:
            continue
        lo = float(np.percentile(hist, 33))
        hi = float(np.percentile(hist, 67))
        v  = fwd_ret.iloc[i]
        if np.isnan(v):
            labels.iloc[i] = np.nan
            continue
        if v > hi:
            labels.iloc[i] = float(_LABEL_BULL)
        elif v < lo:
            labels.iloc[i] = float(_LABEL_BEAR)
        else:
            labels.iloc[i] = float(_LABEL_CHOP)

    # mask last n_forward bars (label uses future data)
    labels.iloc[-n_forward:] = np.nan
    return labels


# ── Strategy class ─────────────────────────────────────────────────────────────

class MomentumRegimeSpreadStrategy(BaseStrategy):
    """
    Momentum Regime Debit Spread AI strategy.

    GBM classifies momentum regime into 3 classes (bull, bear, chop).
    In bull regime: bull call debit spread on SPY (defined-risk directional bet).
    In bear regime: bear put debit spread on SPY.
    In chop: stay flat.
    Max loss is always bounded to the debit paid.
    """

    name                 = "momentum_regime_spread"
    display_name         = "Momentum Regime Spread — AI"
    strategy_type        = StrategyType.AI_DRIVEN
    status               = StrategyStatus.ACTIVE
    description          = (
        "3-class GBM classifies SPY into bull / bear / chop momentum regimes. "
        "Bull regime → bull call debit spread. Bear → bear put debit spread. "
        "Chop → flat. Max loss bounded to debit paid. Walk-forward, 90-bar warmup."
    )
    asset_class          = "equities_options"
    typical_holding_days = 10
    target_sharpe        = 1.1

    FEATURE_COLS = [
        "ret_5d", "ret_20d", "momentum_accel", "atr_pct", "realized_vol_20d",
        "vix_level", "vix_5d_change", "vix_ma_ratio",
        "dist_from_ma50", "dist_from_ma200", "days_to_month_end",
    ]

    _FEATURE_DEFAULTS = {
        "ret_5d":            0.0,
        "ret_20d":           0.0,
        "momentum_accel":    0.0,
        "atr_pct":           0.01,
        "realized_vol_20d":  0.15,
        "vix_level":         20.0,
        "vix_5d_change":     0.0,
        "vix_ma_ratio":      1.0,
        "dist_from_ma50":    0.0,
        "dist_from_ma200":   0.0,
        "days_to_month_end": 10.0,
    }

    def __init__(
        self,
        confidence_threshold: float = 0.55,
        vix_max:              float = 40.0,
        dte_target:           int   = 14,
        dte_exit:             int   = 5,
        wing_width_pct:       float = 0.025,
        stop_loss_pct:        float = 0.50,  # close debit if loses 50% of value
        profit_target_pct:    float = 0.80,  # close at 80% of max profit
        position_size_pct:    float = 0.02,
        n_estimators:         int   = 50,
        max_depth:            int   = 2,
        learning_rate:        float = 0.05,
    ):
        self.confidence_threshold = confidence_threshold
        self.vix_max              = vix_max
        self.dte_target           = dte_target
        self.dte_exit             = dte_exit
        self.wing_width_pct       = wing_width_pct
        self.stop_loss_pct        = stop_loss_pct
        self.profit_target_pct    = profit_target_pct
        self.position_size_pct    = position_size_pct
        self.n_estimators         = n_estimators
        self.max_depth            = max_depth
        self.learning_rate        = learning_rate
        self._model               = None

    def save_model(self, ticker: str = "SPY"):
        if self._model is None:
            return
        _SAVED_MODELS_DIR.mkdir(exist_ok=True)
        with open(_SAVED_MODELS_DIR / f"momentum_regime_spread_{ticker}.pkl", "wb") as f:
            pickle.dump(self._model, f)

    def load_model(self, ticker: str = "SPY") -> bool:
        path = _SAVED_MODELS_DIR / f"momentum_regime_spread_{ticker}.pkl"
        if not path.exists():
            return False
        with open(path, "rb") as f:
            self._model = pickle.load(f)
        return True

    def is_trainable(self) -> bool:
        return True

    def generate_signal(self, market_snapshot: dict) -> SignalResult:
        ret_5d   = float(market_snapshot.get("ret_5d",  0.0))
        ret_20d  = float(market_snapshot.get("ret_20d", 0.0))
        vix      = float(market_snapshot.get("vix",     20.0))
        vix_ma   = float(market_snapshot.get("vix_20d_avg", 20.0))
        vix_rat  = vix / max(vix_ma, 0.01)

        if ret_5d > 0.03 and ret_20d > 0.01 and vix_rat < 1.1:
            signal, regime = "BUY", "bull"
        elif ret_5d < -0.03 and ret_20d < -0.01 and vix_rat > 0.9:
            signal, regime = "SELL", "bear"
        else:
            signal, regime = "HOLD", "chop"

        return SignalResult(
            strategy_name=self.name,
            signal=signal,
            confidence=0.60 if signal != "HOLD" else 0.35,
            position_size_pct=self.position_size_pct if signal != "HOLD" else 0.0,
            metadata={"regime": regime, "ret_5d": ret_5d, "vix": vix},
        )

    def backtest(
        self,
        price_data:           pd.DataFrame,
        auxiliary_data:       dict,
        starting_capital:     float = 100_000,
        confidence_threshold: float | None = None,
        vix_max:              float | None = None,
        dte_target:           int   | None = None,
        wing_width_pct:       float | None = None,
        stop_loss_pct:        float | None = None,
        profit_target_pct:    float | None = None,
        **kwargs,
    ) -> BacktestResult:
        try:
            from sklearn.ensemble import GradientBoostingClassifier
            from sklearn.preprocessing import StandardScaler
            from sklearn.pipeline import Pipeline
        except ImportError as e:
            raise ImportError("scikit-learn required") from e

        conf    = confidence_threshold if confidence_threshold is not None else self.confidence_threshold
        vmax    = vix_max              if vix_max              is not None else self.vix_max
        dte_tgt = dte_target           if dte_target           is not None else self.dte_target
        wing    = wing_width_pct       if wing_width_pct       is not None else self.wing_width_pct
        sl_pct  = stop_loss_pct        if stop_loss_pct        is not None else self.stop_loss_pct
        pt_pct  = profit_target_pct    if profit_target_pct    is not None else self.profit_target_pct

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
        labels = _build_labels(close, n_forward=10)

        all_dates   = list(price_data.index)
        capital     = float(starting_capital)
        equity_list = []
        trades_list = []
        open_trade  = None
        model_      = None
        last_train  = -999

        # Per-spread (per-contract) round-trip friction in per-share BS-mark
        # units: slippage applied on entry AND exit, on both legs.
        slip_per_spread = DEFAULT_SLIPPAGE_PER_LEG * _LEGS_PER_SPREAD
        comm_per_spread = DEFAULT_COMMISSION_PER_LEG * _LEGS_PER_SPREAD

        for i, dt in enumerate(all_dates):
            mtm_value = 0.0  # marked-to-market value of any open position (added to equity)

            if open_trade is not None:
                open_trade["days_held"] += 1
                spot    = float(close.iloc[i])
                iv_now  = float(vix.iloc[i]) / 100.0
                days_rem = max(0, dte_tgt - open_trade["days_held"])
                t_yr    = days_rem / 252.0
                stype   = open_trade["spread_type"]
                contracts = open_trade["contracts"]
                val_now = _debit_spread_value(
                    spot, open_trade["long_strike"], open_trade["short_strike"],
                    t_yr, _RISK_FREE_RATE, iv_now, stype
                )
                entry_v   = open_trade["entry_value"]
                # Unrealized P&L if we closed now (net of exit frictions), scaled
                # by contracts. Exit slippage drags the realizable value down.
                exit_val_ps = max(0.0, val_now - slip_per_spread)
                pnl_now   = ((exit_val_ps - entry_v) * 100 - comm_per_spread) * contracts
                max_gain  = open_trade["max_gain"]

                exit_reason = None
                if pnl_now >= max_gain * pt_pct:
                    exit_reason = "profit_target"
                elif val_now <= entry_v * (1 - sl_pct):
                    exit_reason = "stop_loss"
                elif open_trade["days_held"] >= dte_tgt - self.dte_exit:
                    exit_reason = "dte_exit"

                if exit_reason:
                    # Return the originally-paid debit basis plus realized P&L.
                    capital += open_trade["entry_cost"] + pnl_now
                    trades_list.append({
                        "entry_date":  open_trade["entry_date"].date(),
                        "exit_date":   dt.date(),
                        "spread_type": stype,
                        "contracts":   contracts,
                        "entry_cost":  round(open_trade["entry_cost"], 2),
                        "exit_value":  round(exit_val_ps * 100 * contracts, 2),
                        "pnl":         round(pnl_now, 2),
                        "exit_reason": exit_reason,
                    })
                    open_trade = None
                else:
                    # Still open: mark the position to market so the equity curve
                    # is not a step function frozen at the entry debit.
                    mtm_value = exit_val_ps * 100 * contracts

            # Equity = free cash + marked value of open position.
            equity_list.append(capital + mtm_value)

            if i < _WARMUP_BARS:
                continue

            if i - last_train >= _RETRAIN_EVERY:
                # Purge the most recent bars whose labels (10d forward return) or
                # trade hold window (dte_target) overlap the prediction point i.
                # cutoff = i - max(label_window, hold_window) prevents both label
                # look-ahead and hold-period leakage.
                purge = max(10, dte_tgt)
                cutoff = max(0, i - purge)
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
                    pipe.fit(X_tr.values, y_tr.values.astype(int))
                    model_ = pipe
                    last_train = i

            if model_ is None or open_trade is not None:
                continue

            vix_now = float(vix.iloc[i])
            if vix_now > vmax:
                continue

            feat_row = feats.iloc[[i]][self.FEATURE_COLS]
            for col, default in self._FEATURE_DEFAULTS.items():
                if col in feat_row.columns:
                    feat_row[col] = feat_row[col].fillna(default)
            if feat_row.isna().any().any():
                continue

            proba   = model_.predict_proba(feat_row.values)[0]
            classes = model_.classes_
            prob_map = {int(c): p for c, p in zip(classes, proba)}
            p_bull  = prob_map.get(_LABEL_BULL, 0.0)
            p_bear  = prob_map.get(_LABEL_BEAR, 0.0)

            spot     = float(close.iloc[i])
            iv_entry = float(vix.iloc[i]) / 100.0
            t_yr     = dte_tgt / 252.0
            wing_w   = spot * wing
            max_cost = capital * self.position_size_pct

            if p_bull >= conf:
                long_K  = round(spot, 0)
                short_K = round(spot + wing_w, 0)
                stype   = "bull_call"
                p_sel   = p_bull
            elif p_bear >= conf:
                long_K  = round(spot, 0)
                short_K = round(spot - wing_w, 0)
                stype   = "bear_put"
                p_sel   = p_bear
            else:
                continue

            entry_v = _debit_spread_value(spot, long_K, short_K, t_yr, _RISK_FREE_RATE, iv_entry, stype)
            if entry_v <= 0:
                continue

            # All-in per-contract entry cost = debit (incl. entry slippage) + commissions.
            entry_v_filled  = entry_v + slip_per_spread
            cost_per_spread = entry_v_filled * 100 + comm_per_spread
            if cost_per_spread <= 0:
                continue

            # Size by integer contracts within the position budget. Skip if we
            # cannot afford even one spread.
            contracts = int(max_cost // cost_per_spread)
            if contracts < 1:
                continue
            cost = cost_per_spread * contracts
            if cost > capital:
                continue
            capital -= cost

            open_trade = {
                "entry_date": dt, "spread_type": stype,
                "long_strike": long_K, "short_strike": short_K,
                "entry_value": entry_v_filled, "entry_cost": cost,
                "contracts": contracts,
                # Max gain = (wing - net debit paid) per contract, net of the
                # round-trip exit frictions, scaled by contracts.
                "max_gain": ((wing_w - entry_v_filled) * 100 - comm_per_spread) * contracts,
                "days_held": 0, "prob": p_sel,
            }

        if open_trade is not None:
            # Mark the open spread to market at the final bar instead of
            # assuming a total loss of the debit.
            spot     = float(close.iloc[-1])
            iv_last  = float(vix.iloc[-1]) / 100.0
            days_rem = max(0, dte_tgt - open_trade["days_held"])
            t_yr     = days_rem / 252.0
            contracts = open_trade["contracts"]
            val_last = _debit_spread_value(
                spot, open_trade["long_strike"], open_trade["short_strike"],
                t_yr, _RISK_FREE_RATE, iv_last, open_trade["spread_type"]
            )
            exit_val_ps = max(0.0, val_last - slip_per_spread)
            pnl_eod = ((exit_val_ps - open_trade["entry_value"]) * 100 - comm_per_spread) * contracts
            capital += open_trade["entry_cost"] + pnl_eod
            trades_list.append({
                "entry_date":  open_trade["entry_date"].date(),
                "exit_date":   all_dates[-1].date(),
                "spread_type": open_trade["spread_type"],
                "contracts":   contracts,
                "entry_cost":  round(open_trade["entry_cost"], 2),
                "exit_value":  round(exit_val_ps * 100 * contracts, 2),
                "pnl":         round(pnl_eod, 2),
                "exit_reason": "end_of_data",
            })
            equity_list[-1] = capital
            open_trade = None

        equity    = pd.Series(equity_list, index=price_data.index, dtype=float)
        daily_ret = equity.pct_change().dropna()
        bh_ret    = close.pct_change().reindex(equity.index).dropna()
        trades_df = pd.DataFrame(trades_list) if trades_list else pd.DataFrame(
            columns=["entry_date", "exit_date", "spread_type", "contracts",
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
            {"key": "confidence_threshold", "label": "Confidence threshold",
             "type": "slider", "min": 0.45, "max": 0.75, "default": 0.55, "step": 0.05,
             "col": 0, "row": 0,
             "help": "Minimum P(regime) to enter — higher = fewer but higher-conviction trades"},
            {"key": "vix_max",              "label": "VIX ceiling",
             "type": "slider", "min": 25, "max": 55, "default": 40, "step": 5,
             "col": 1, "row": 0,
             "help": "Skip entry when VIX is above this level"},
            {"key": "dte_target",           "label": "DTE at entry",
             "type": "slider", "min": 7, "max": 21, "default": 14, "step": 1,
             "col": 2, "row": 0,
             "help": "Target days-to-expiry for debit spread"},
            {"key": "wing_width_pct",       "label": "Wing width (% spot)",
             "type": "slider", "min": 0.01, "max": 0.05, "default": 0.025, "step": 0.005,
             "col": 0, "row": 1,
             "help": "Width of debit spread as % of spot"},
            {"key": "stop_loss_pct",        "label": "Stop loss (% value lost)",
             "type": "slider", "min": 0.30, "max": 0.80, "default": 0.50, "step": 0.05,
             "col": 1, "row": 1,
             "help": "Close if spread loses this fraction of its entry value"},
            {"key": "profit_target_pct",    "label": "Profit target (% max)",
             "type": "slider", "min": 0.50, "max": 0.95, "default": 0.80, "step": 0.05,
             "col": 2, "row": 1,
             "help": "Close at this fraction of maximum possible profit"},
        ]

    def get_params(self) -> dict:
        return {
            "confidence_threshold": self.confidence_threshold,
            "vix_max":              self.vix_max,
            "dte_target":           self.dte_target,
            "dte_exit":             self.dte_exit,
            "wing_width_pct":       self.wing_width_pct,
            "stop_loss_pct":        self.stop_loss_pct,
            "profit_target_pct":    self.profit_target_pct,
            "position_size_pct":    self.position_size_pct,
            "n_estimators":         self.n_estimators,
            "max_depth":            self.max_depth,
            "learning_rate":        self.learning_rate,
        }
