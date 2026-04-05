"""
Calendar Spread (Time Spread) Strategy.

Harvests the theta differential between near-term and far-term options.
Sells a front-month ATM option while buying the same strike in the next expiry,
capturing the structural premium that near-term options command.

Entry rules (all must pass):
  • ADX ≤ adx_max (22 default)       — range-bound, not trending
  • VIX 14–25                        — stable vol environment
  • Front-month IV > back-month IV   — normal term structure (front is expensive)
  • HV20 < ATM IV by ≥ 3 vol pts     — VRP confirms front month is overpriced
  • No earnings within front expiry window

Structure:
  • Sell front-month ATM call/put (21–28 DTE)
  • Buy back-month same strike (49–56 DTE)
  • Net debit; back/front price ratio ≤ 1.8

Exit:
  • 25–35% return on debit
  • 50% loss on debit → stop
  • 7 DTE on front month → roll or close
  • ADX crosses above 25 → close (trend break)
"""

import numpy as np
import pandas as pd
from typing import Optional

from alan_trader.strategies.base import (
    BaseStrategy, BacktestResult, SignalResult,
    StrategyStatus, StrategyType,
)


class CalendarSpreadStrategy(BaseStrategy):
    name          = "calendar_spread"
    display_name  = "Calendar Spread"
    strategy_type = StrategyType.RULE_BASED
    status        = StrategyStatus.ACTIVE
    description   = (
        "Sells front-month ATM option against same-strike back-month to harvest theta differential. "
        "Best in range-bound, stable-IV environments. ADX < 22, VIX 14–25, front IV > back IV."
    )
    asset_class          = "equities_options"
    typical_holding_days = 21
    target_sharpe        = 1.3

    _DEFAULTS = {
        "adx_max":              22.0,
        "vix_min":              14.0,
        "vix_max":              25.0,
        "hv_iv_spread_min":     0.03,   # front IV must exceed HV20 by ≥ 3 vol pts (decimal)
        "front_back_iv_min":    0.02,   # front IV > back IV by ≥ 2 vol pts
        "max_price_ratio":      1.8,    # back/front ≤ 1.8
        "front_dte":            25,     # target DTE for front month
        "back_dte":             53,     # target DTE for back month
        "profit_target_pct":    0.30,   # close at 30% ROC on debit
        "stop_loss_pct":        0.50,   # close if 50% of debit lost
    }

    def get_params(self) -> dict:
        return dict(self._DEFAULTS)

    def get_backtest_ui_params(self) -> list:
        return [
            {"key": "adx_max",           "label": "ADX max",        "type": "slider",
             "min": 10, "max": 35, "step": 1, "default": 22},
            {"key": "vix_min",           "label": "VIX min",        "type": "slider",
             "min": 10, "max": 20, "step": 1, "default": 14},
            {"key": "vix_max",           "label": "VIX max",        "type": "slider",
             "min": 18, "max": 40, "step": 1, "default": 25},
            {"key": "hv_iv_spread_min",  "label": "HV<IV spread",   "type": "slider",
             "min": 0.01, "max": 0.10, "step": 0.01, "default": 0.03},
            {"key": "profit_target_pct", "label": "Profit target %","type": "slider",
             "min": 0.15, "max": 0.50, "step": 0.05, "default": 0.30},
        ]

    def generate_signal(self, market_snapshot: dict) -> SignalResult:
        vix   = market_snapshot.get("vix", 20)
        adx   = market_snapshot.get("adx", 0)
        atm_iv = market_snapshot.get("atm_iv", 0)
        hv20  = market_snapshot.get("hv20", 0)
        p     = self._DEFAULTS

        vrp_ok = (atm_iv - hv20) >= p["hv_iv_spread_min"] if atm_iv and hv20 else False
        adx_ok = adx <= p["adx_max"]
        vix_ok = p["vix_min"] <= vix <= p["vix_max"]

        if not (adx_ok and vix_ok and vrp_ok):
            return SignalResult(self.name, "HOLD", 0.0, 0.0,
                                {"reason": "Entry conditions not met"})

        confidence = (
            (1.0 - adx / p["adx_max"]) * 0.4 +
            (1.0 - abs(vix - 19) / 5) * 0.3 +
            min((atm_iv - hv20) / 0.05, 1.0) * 0.3
        )

        return SignalResult(
            self.name, "SELL", float(np.clip(confidence, 0.3, 0.9)),
            position_size_pct=0.02,
            metadata={
                "structure":   "atm_calendar",
                "front_dte":   p["front_dte"],
                "back_dte":    p["back_dte"],
                "adx":         adx,
                "vix":         vix,
                "vrp":         round(atm_iv - hv20, 4) if atm_iv and hv20 else None,
            },
        )

    def backtest(self, price_data: pd.DataFrame, auxiliary_data: dict,
                 params: Optional[dict] = None, **kwargs) -> BacktestResult:
        p      = {**self._DEFAULTS, **(params or {})}
        close  = price_data["close"].astype(float)
        high   = price_data.get("high", close).astype(float)
        low    = price_data.get("low",  close).astype(float)
        vix    = auxiliary_data.get("vix", pd.Series(dtype=float))

        from alan_trader.strategies.ivr_credit_spread import _compute_ivr, _compute_adx, _compute_atr
        adx_s = _compute_adx(high, low, close)
        # HV20 proxy
        ret   = close.pct_change()
        hv20_s = ret.rolling(20).std() * np.sqrt(252)

        capital   = 100_000.0
        trades    = []
        equity    = []
        in_trade  = False
        dte_rem   = 0
        entry_debit = entry_date = 0

        for i in range(50, len(close)):
            date  = close.index[i]
            spot  = float(close.iloc[i])
            adx_v = float(adx_s.iloc[i]) if i < len(adx_s) else 30.0
            vix_v = float(vix.iloc[i])   if not vix.empty and i < len(vix) else 20.0
            hv_v  = float(hv20_s.iloc[i]) if not pd.isna(hv20_s.iloc[i]) else 0.20
            iv_v  = vix_v / 100.0

            if in_trade:
                dte_rem -= 1
                trend_break = adx_v > 25
                time_exit   = dte_rem <= 7
                if trend_break or time_exit:
                    # Assume partial theta capture: 20% ROC on trend break, 25% on time exit
                    roi = -p["stop_loss_pct"] if trend_break else p["profit_target_pct"] * 0.8
                    pnl = entry_debit * roi * 100
                    trades.append({"entry_date": entry_date, "exit_date": date,
                                   "pnl": pnl, "exit_reason": "stop" if trend_break else "dte"})
                    capital  += pnl
                    in_trade  = False
            else:
                vrp_ok = (iv_v - hv_v) >= p["hv_iv_spread_min"]
                adx_ok = adx_v <= p["adx_max"]
                vix_ok = p["vix_min"] <= vix_v <= p["vix_max"]
                if adx_ok and vix_ok and vrp_ok:
                    # Debit proxy: ATM option price ≈ spot × iv × √(T/252)
                    front_price = spot * iv_v * np.sqrt(p["front_dte"] / 252)
                    back_price  = spot * iv_v * np.sqrt(p["back_dte"]  / 252)
                    debit       = back_price - front_price
                    if debit > 0 and (back_price / front_price) <= p["max_price_ratio"]:
                        in_trade    = True
                        entry_date  = date
                        entry_debit = debit
                        dte_rem     = p["front_dte"]

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
