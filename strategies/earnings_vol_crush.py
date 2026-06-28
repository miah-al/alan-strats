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
  - Warmup: 30 earnings events before first prediction (cycles, not calendar bars)
  - Retrain every 10 new events
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
  Positive (contained) rate is data-dependent and must be measured per universe.

COSTS & PRICING
---------------
  - Per-leg slippage + commission applied on BOTH entry and exit (2 legs ×
    contracts) via DEFAULT_SLIPPAGE_PER_LEG / DEFAULT_COMMISSION_PER_LEG.
  - Legs priced with the engine's skew-aware pricer (bs_price_skew) when
    available so OTM strikes reflect the vol smile; flat-IV BS fallback.
  - Position sized so worst-case (defined-risk) loss ≈ position_size_pct of
    equity; all P&L scaled by contract count. Open positions are marked to
    market in the equity curve (no step-function-only equity).
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

# Transaction-cost constants and skew-aware pricing live in the backtest engine.
# Import them defensively so the module stays importable even if the engine API
# drifts; fall back to conservative defaults / flat IV in that case.
try:  # pragma: no cover - import shim
    from alan_trader.backtest.engine import (
        DEFAULT_SLIPPAGE_PER_LEG,
        DEFAULT_COMMISSION_PER_LEG,
    )
except Exception:  # pragma: no cover
    try:
        from backtest.engine import (
            DEFAULT_SLIPPAGE_PER_LEG,
            DEFAULT_COMMISSION_PER_LEG,
        )
    except Exception:
        DEFAULT_SLIPPAGE_PER_LEG   = 0.05   # per-share adverse fill per leg
        DEFAULT_COMMISSION_PER_LEG = 0.65   # $ per contract per leg

try:  # pragma: no cover - import shim
    from alan_trader.backtest.engine import bs_price_skew
    _HAS_SKEW = True
except Exception:  # pragma: no cover
    try:
        from backtest.engine import bs_price_skew
        _HAS_SKEW = True
    except Exception:
        bs_price_skew = None
        _HAS_SKEW = False

logger = logging.getLogger(__name__)

_RISK_FREE_RATE   = 0.045
_WARMUP_EVENTS    = 30      # earnings events before first ML prediction
_RETRAIN_EVERY    = 10      # events between retrains
_SAVED_MODELS_DIR = Path(__file__).parent.parent / "saved_models"

# Per-leg round-trip cost in *contract* dollars (slippage×100 + commission),
# applied on BOTH entry and exit, scaled by number of legs × contracts.
_LEG_COST = DEFAULT_SLIPPAGE_PER_LEG * 100.0 + DEFAULT_COMMISSION_PER_LEG


# ── Helpers ────────────────────────────────────────────────────────────────────

from strategies.indicators import bs_price as _bs_price, compute_adx as _compute_adx


def _leg_price(S, K, T, r, iv, option_type):
    """
    Price a single option leg. Uses the engine's skew-aware pricer when
    available so OTM short/long strikes reflect the volatility smile rather than
    a single flat IV; otherwise falls back to flat-IV Black-Scholes. The engine's
    bs_price_skew(S, K, T, r, atm_iv, option_type) applies the moneyness skew
    internally, so we pass the ATM (VIX-derived) IV directly.
    """
    if _HAS_SKEW:
        try:
            return float(bs_price_skew(S, K, T, r, iv, option_type))
        except Exception:
            pass
    return _bs_price(S, K, T, r, iv, option_type)


def _spread_credit(S, short_K, long_K, T, r, iv, spread_type):
    if spread_type == "bull_put":
        return (_leg_price(S, short_K, T, r, iv, "put")
                - _leg_price(S, long_K, T, r, iv, "put"))
    return (_leg_price(S, short_K, T, r, iv, "call")
            - _leg_price(S, long_K, T, r, iv, "call"))


def _spread_value_at_expiry(spot, short_K, long_K, spread_type):
    """Intrinsic value of spread at expiry."""
    if spread_type == "bull_put":
        return max(0, short_K - spot) - max(0, long_K - spot)
    return max(0, spot - short_K) - max(0, spot - long_K)




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
        }).ffill()  # ffill only — bfill leaks future values into early NaNs (walk-forward look-ahead)

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
            mtm = 0.0  # unrealized P&L of any open position, marked to market today
            if open_trade is not None:
                open_trade["days_held"] += 1
                spot    = float(close.iloc[i])
                iv_now  = float(vix.iloc[i]) / 100.0
                days_rem = max(0, h_days - open_trade["days_held"])
                t_yr    = days_rem / 252.0
                st      = open_trade["spread_type"]
                contracts = open_trade["contracts"]

                # Current cost to buy the spread back.
                pnl_now = (_spread_value_at_expiry(spot, open_trade["short_strike"],
                             open_trade["long_strike"], st)
                           if days_rem == 0
                           else (_spread_credit(spot, open_trade["short_strike"],
                                  open_trade["long_strike"], t_yr, _RISK_FREE_RATE, iv_now, st)))

                # Credit trade: profit = credit collected − cost to close, scaled
                # by contracts × 100 shares/contract.
                entry_v    = open_trade["entry_value"]
                pnl_dollar = (entry_v - pnl_now) * 100.0 * contracts
                max_profit = open_trade["max_profit"]   # already contract-scaled
                max_loss   = open_trade["max_loss"]     # already contract-scaled

                # Stop is a multiple of the *credit received* (max_profit), which
                # is reachable; a multiple of max_loss could never trigger since a
                # defined-risk spread cannot lose more than max_loss (1×). Cap at
                # the structural max loss so the threshold stays valid.
                stop_level = min(max_profit * sl_mult, max_loss)

                exit_reason = None
                if pnl_dollar >= max_profit * pt_pct:
                    exit_reason = "profit_target"
                elif pnl_dollar <= -stop_level:
                    exit_reason = "stop_loss"
                elif open_trade["days_held"] >= h_days:
                    exit_reason = "hold_days"

                if exit_reason:
                    # Round-trip exit cost: 2 legs × contracts (entry cost was
                    # already deducted from capital at entry).
                    exit_cost = _LEG_COST * 2.0 * contracts
                    pnl_net   = pnl_dollar - exit_cost
                    capital  += pnl_net
                    trades_list.append({
                        "entry_date":  open_trade["entry_date"].date(),
                        "exit_date":   dt.date(),
                        "spread_type": open_trade["spread_type"],
                        "contracts":   contracts,
                        "entry_cost":  round(open_trade["entry_value"] * 100 * contracts, 2),
                        "exit_value":  round(pnl_now * 100 * contracts, 2),
                        "pnl":         round(pnl_net, 2),
                        "exit_reason": exit_reason,
                    })
                    open_trade = None
                else:
                    # Still open: mark to market so equity isn't a step function.
                    mtm = pnl_dollar

            equity_list.append(capital + mtm)

            if not earnings_gaps.iloc[i]:
                continue

            events_seen += 1

            if events_seen < _WARMUP_EVENTS:
                continue

            # Retrain — purge the last h_days bars. Each label looks forward
            # h_days (close[j+1 : j+1+h_days]), so a row at j carries information
            # up to bar j+h_days. Training on rows j > i-h_days would leak prices
            # at/after the decision bar i into the model (walk-forward look-ahead).
            # cutoff = i - h_days keeps only rows whose label window closed before i.
            # Mirrors the purge already used in rs_credit_spread.
            if events_seen - last_train >= _RETRAIN_EVERY:
                cutoff = max(0, i - h_days)
                X_tr = feat_df.iloc[:cutoff][self.FEATURE_COLS]
                y_tr = labels.iloc[:cutoff]
                # only use earnings event rows
                ev_mask = earnings_gaps.iloc[:cutoff]
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

            # Per-contract risk = wing − credit (defined-risk spread). Size so the
            # worst-case loss ≈ position_size_pct of current equity.
            risk_per_contract = max(1e-9, (wing_w - entry_v) * 100.0)
            risk_budget       = capital * self.position_size_pct
            contracts         = int(max(1, np.floor(risk_budget / risk_per_contract)))

            max_loss_  = risk_per_contract * contracts
            max_profit = entry_v * 100.0 * contracts

            # Entry transaction cost: 2 legs × contracts, deducted immediately.
            capital -= _LEG_COST * 2.0 * contracts

            open_trade = {
                "entry_date":   dt, "spread_type": stype,
                "short_strike": short_K, "long_strike": long_K,
                "entry_value":  entry_v, "max_profit": max_profit, "max_loss": max_loss_,
                "contracts":    contracts,
                "days_held": 0, "prob": prob_contained,
            }

        if open_trade is not None:
            # Close the dangling position at the final bar's mark, net of the
            # exit transaction cost, so the trade log and final equity agree.
            contracts = open_trade["contracts"]
            spot      = float(close.iloc[-1])
            iv_now    = float(vix.iloc[-1]) / 100.0
            days_rem  = max(0, h_days - open_trade["days_held"])
            t_yr      = days_rem / 252.0
            st        = open_trade["spread_type"]
            close_val = (_spread_value_at_expiry(spot, open_trade["short_strike"],
                            open_trade["long_strike"], st)
                         if days_rem == 0
                         else _spread_credit(spot, open_trade["short_strike"],
                                open_trade["long_strike"], t_yr, _RISK_FREE_RATE, iv_now, st))
            pnl_dollar = (open_trade["entry_value"] - close_val) * 100.0 * contracts
            pnl_net    = pnl_dollar - _LEG_COST * 2.0 * contracts
            capital   += pnl_net
            if equity_list:
                equity_list[-1] = capital  # replace MTM with realized close
            trades_list.append({
                "entry_date":  open_trade["entry_date"].date(),
                "exit_date":   all_dates[-1].date(),
                "spread_type": open_trade["spread_type"],
                "contracts":   contracts,
                "entry_cost":  round(open_trade["entry_value"] * 100 * contracts, 2),
                "exit_value":  round(close_val * 100 * contracts, 2),
                "pnl":         round(pnl_net, 2),
                "exit_reason": "end_of_data",
            })
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
            {"key": "stop_loss_mult",    "label": "Stop loss (× max credit)",
             "type": "slider", "min": 1.0, "max": 3.0, "default": 2.0, "step": 0.5,
             "col": 0, "row": 2,
             "help": "Close when loss reaches this multiple of credit received"},
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
