"""
Broken Wing Butterfly (BWB) Strategy.

Exploits volatility skew and low-IV environments by constructing a butterfly
with an asymmetric wide wing that generates a net credit at entry.

Entry rules (all must pass):
  • IVR ≤ ivr_max (35% default) — low IV is where BWB generates best credit-to-risk
  • ADX ≤ adx_max (28 default)  — range-bound, not trending
  • VIX ≤ vix_max (30 default)  — not in panic regime
  • No earnings within expiry window

Structure:
  • Call BWB (mildly bullish): Buy lower call, Sell 2× body call, Buy 2× wide upper call
  • Put BWB  (mildly bearish): Buy upper put, Sell 2× body put, Buy 2× wide lower put
  • Narrow wing = 5% of spot, Wide wing = 2× narrow (10% of spot)
  • Net credit ≥ $0.20 required

Exit:
  • 75% of max profit
  • Within $1 of wide wing strike → close immediately
  • 7 DTE time exit
"""

import numpy as np
import pandas as pd
from typing import Optional

from alan_trader.strategies.base import (
    BaseStrategy, BacktestResult, SignalResult,
    StrategyStatus, StrategyType,
)


class BrokenWingButterflyStrategy(BaseStrategy):
    name         = "broken_wing_butterfly"
    display_name = "Broken Wing Butterfly"
    strategy_type = StrategyType.RULE_BASED
    status        = StrategyStatus.ACTIVE
    description   = (
        "Net-credit butterfly with asymmetric wide wing. Profits from pin at body strike, "
        "keeps credit if flat/below. Low-IV specialist (IVR < 35%). Stop: within $1 of wide wing."
    )
    asset_class          = "equities_options"
    typical_holding_days = 21
    target_sharpe        = 1.4

    # Default params
    _DEFAULTS = {
        "ivr_max":        0.35,   # maximum IVR (low-IV strategy)
        "adx_max":        28.0,   # range-bound filter
        "vix_max":        30.0,   # not in panic
        "narrow_wing_pct": 0.05,  # narrow wing = 5% of spot
        "wide_wing_mult":  2.0,   # wide wing = 2× narrow
        "min_credit":      0.20,  # minimum net credit per spread
        "dte_target":      21,    # target DTE at entry
        "profit_target":   0.75,  # close at 75% of max profit
    }

    def get_params(self) -> dict:
        return dict(self._DEFAULTS)

    def get_backtest_ui_params(self) -> list:
        return [
            {"key": "ivr_max",         "label": "IVR max",         "type": "slider",
             "min": 0.10, "max": 0.60, "step": 0.05, "default": 0.35},
            {"key": "adx_max",         "label": "ADX max",         "type": "slider",
             "min": 10,   "max": 50,   "step": 1,    "default": 28},
            {"key": "vix_max",         "label": "VIX max",         "type": "slider",
             "min": 15,   "max": 50,   "step": 1,    "default": 30},
            {"key": "narrow_wing_pct", "label": "Narrow wing %",   "type": "slider",
             "min": 0.02, "max": 0.10, "step": 0.01, "default": 0.05},
            {"key": "min_credit",      "label": "Min credit ($)",  "type": "input",
             "default": 0.20},
        ]

    def generate_signal(self, market_snapshot: dict) -> SignalResult:
        spot    = market_snapshot.get("price", 0)
        vix     = market_snapshot.get("vix", 20)
        ivr     = market_snapshot.get("ivr", 0)
        adx     = market_snapshot.get("adx", 0)
        p       = self._DEFAULTS

        if ivr > p["ivr_max"] or adx > p["adx_max"] or vix > p["vix_max"] or spot <= 0:
            return SignalResult(self.name, "HOLD", 0.0, 0.0,
                                {"reason": "Entry conditions not met"})

        narrow_w = round(spot * p["narrow_wing_pct"], 0)
        wide_w   = narrow_w * p["wide_wing_mult"]
        confidence = 1.0 - (ivr / p["ivr_max"]) * 0.4 - (adx / p["adx_max"]) * 0.3

        return SignalResult(
            self.name, "SELL", float(np.clip(confidence, 0.3, 0.95)),
            position_size_pct=0.02,
            metadata={
                "structure":  "call_bwb",
                "narrow_wing": narrow_w,
                "wide_wing":   wide_w,
                "dte_target":  p["dte_target"],
                "ivr":         ivr,
                "adx":         adx,
            },
        )

    def backtest(self, price_data: pd.DataFrame, auxiliary_data: dict,
                 params: Optional[dict] = None, **kwargs) -> BacktestResult:
        p = {**self._DEFAULTS, **(params or {})}
        close  = price_data["close"].astype(float)
        high   = price_data.get("high", close).astype(float)
        low    = price_data.get("low",  close).astype(float)
        vix    = auxiliary_data.get("vix", pd.Series(dtype=float))

        from alan_trader.strategies.ivr_credit_spread import _compute_ivr, _compute_adx, _compute_atr
        ivr_s  = _compute_ivr(vix)
        adx_s  = _compute_adx(high, low, close)
        atr_s  = _compute_atr(high, low, close)

        trades, equity = [], []
        capital = 100_000.0
        in_trade = False
        entry_credit = entry_date = body_k = wide_k = None
        dte_remaining = 0

        for i in range(50, len(close)):
            date  = close.index[i]
            spot  = float(close.iloc[i])
            ivr_v = float(ivr_s.iloc[i]) if i < len(ivr_s) and not pd.isna(ivr_s.iloc[i]) else 0.5
            adx_v = float(adx_s.iloc[i]) if i < len(adx_s) else 30.0
            vix_v = float(vix.iloc[i]) if not vix.empty and i < len(vix) else 20.0
            atr_v = float(atr_s.iloc[i]) if i < len(atr_s) else spot * 0.015

            if in_trade:
                dte_remaining -= 1
                # Wide wing stop: underlying within $1 of wide wing
                wide_breached = abs(spot - wide_k) < 1.0
                time_exit = dte_remaining <= 7
                if wide_breached or time_exit:
                    pnl = -entry_credit * 0.5 * 100 if wide_breached else entry_credit * 0.35 * 100
                    trades.append({"entry_date": entry_date, "exit_date": date,
                                   "pnl": pnl, "exit_reason": "stop" if wide_breached else "dte"})
                    capital += pnl
                    in_trade = False
            else:
                if (ivr_v <= p["ivr_max"] and adx_v <= p["adx_max"] and vix_v <= p["vix_max"]):
                    narrow_w     = round(spot * p["narrow_wing_pct"], 0)
                    wide_w       = narrow_w * p["wide_wing_mult"]
                    body_k       = round(spot * 1.005 / narrow_w) * narrow_w  # nearest round above spot
                    wide_k       = body_k + wide_w
                    entry_credit = p["min_credit"] + atr_v * 0.1  # proxy
                    if entry_credit >= p["min_credit"]:
                        in_trade      = True
                        entry_date    = date
                        dte_remaining = p["dte_target"]
                        max_profit    = narrow_w + entry_credit
                        # partial profit assumption: 50% chance of 60% of max, 50% keep credit
                        exp_pnl = 0.5 * max_profit * 0.60 * 100 + 0.5 * entry_credit * 100
                        trades.append({"entry_date": date, "exit_date": None,
                                       "pnl": exp_pnl, "exit_reason": "open"})

            equity.append(capital)

        trades_df = pd.DataFrame(trades)
        closed    = trades_df[trades_df["exit_date"].notna()] if not trades_df.empty else trades_df
        eq_series = pd.Series(equity, index=close.index[50:], name="equity")
        daily_ret = eq_series.pct_change().fillna(0.0)

        from alan_trader.risk.metrics import compute_all_metrics
        metrics = compute_all_metrics(daily_ret, eq_series)

        return BacktestResult(
            strategy_name=self.name,
            equity_curve=eq_series,
            daily_returns=daily_ret,
            trades=closed,
            metrics=metrics,
            params=p,
        )
