"""
Wheel Strategy (Cash-Secured Put → Covered Call).

A systematic income strategy that cycles between selling cash-secured puts
and covered calls. The premium harvested from repeatedly selling time decay
generates steady income in sideways-to-bullish markets.

Entry rules (all must pass):
  • IVR ≥ ivr_min (40% default) — elevated IV ensures fat premiums
  • ADX 15–30 — slight trend OK, but avoid runaway trends
  • Price above 50-day MA — underlying in uptrend bias
  • VIX ≤ vix_max (35 default) — not in crash mode

Phase 1 — Cash-Secured Put:
  • Sell OTM put at delta 0.25–0.35 (≈ 1 standard deviation below spot)
  • Expiry 21–35 DTE (target 28)
  • Collect premium; max risk = strike − premium

Phase 2 — Covered Call (if assigned):
  • Own 100 shares at put strike
  • Sell ATM-to-slightly-OTM call, delta 0.30–0.40, 21–35 DTE
  • Repeat until called away

Exit:
  • 50% of max profit (buyback)
  • Roll down/out if tested (21 DTE, still profitable)
  • If assigned at Phase 1 → move to Phase 2 (covered call)
"""

import numpy as np
import pandas as pd
from typing import Optional

from alan_trader.strategies.base import (
    BaseStrategy, BacktestResult, SignalResult,
    StrategyStatus, StrategyType,
)


class WheelStrategy(BaseStrategy):
    name          = "wheel_strategy"
    display_name  = "Wheel Strategy"
    strategy_type = StrategyType.RULE_BASED
    status        = StrategyStatus.ACTIVE
    description   = (
        "Sells cash-secured puts then covered calls in a cycle to harvest premium. "
        "IVR > 40%, price above 50-MA, ADX 15–30. 50% buyback target."
    )
    asset_class          = "equities_options"
    typical_holding_days = 28
    target_sharpe        = 1.2

    _DEFAULTS = {
        "ivr_min":          0.40,
        "adx_min":          15.0,
        "adx_max":          30.0,
        "vix_max":          35.0,
        "put_delta":        0.30,   # target delta for short put
        "call_delta":       0.35,   # target delta for covered call
        "dte_target":       28,     # target DTE at entry
        "profit_target":    0.50,   # close at 50% of max profit
        "ma_period":        50,     # SMA period for trend filter
    }

    def get_params(self) -> dict:
        return dict(self._DEFAULTS)

    def get_backtest_ui_params(self) -> list:
        return [
            {"key": "ivr_min",       "label": "IVR min",        "type": "slider",
             "min": 0.20, "max": 0.70, "step": 0.05, "default": 0.40},
            {"key": "adx_max",       "label": "ADX max",        "type": "slider",
             "min": 20,   "max": 50,   "step": 1,    "default": 30},
            {"key": "vix_max",       "label": "VIX max",        "type": "slider",
             "min": 20,   "max": 50,   "step": 1,    "default": 35},
            {"key": "put_delta",     "label": "Put delta",      "type": "slider",
             "min": 0.15, "max": 0.45, "step": 0.05, "default": 0.30},
            {"key": "profit_target", "label": "Profit target",  "type": "slider",
             "min": 0.25, "max": 0.70, "step": 0.05, "default": 0.50},
        ]

    def generate_signal(self, market_snapshot: dict) -> SignalResult:
        spot  = market_snapshot.get("price", 0)
        ivr   = market_snapshot.get("ivr", 0)
        adx   = market_snapshot.get("adx", 0)
        vix   = market_snapshot.get("vix", 20)
        ma50  = market_snapshot.get("ma50", 0)
        atm_iv = market_snapshot.get("atm_iv", 0)
        p     = self._DEFAULTS

        trend_ok = (spot > ma50) if ma50 else True
        ivr_ok   = ivr >= p["ivr_min"]
        adx_ok   = p["adx_min"] <= adx <= p["adx_max"]
        vix_ok   = vix <= p["vix_max"]

        if not (ivr_ok and adx_ok and vix_ok and trend_ok and spot > 0):
            return SignalResult(self.name, "HOLD", 0.0, 0.0,
                                {"reason": "Entry conditions not met"})

        # Put strike ≈ spot × (1 − delta × iv × √T)
        dte_frac    = p["dte_target"] / 252
        put_otm_pct = p["put_delta"] * (atm_iv or 0.25) * np.sqrt(dte_frac)
        put_strike  = round(spot * (1.0 - put_otm_pct), 0)
        premium_est = spot * (atm_iv or 0.25) * np.sqrt(dte_frac) * p["put_delta"] * 0.8

        confidence = float(np.clip(
            ivr * 0.5 + (1.0 - adx / p["adx_max"]) * 0.3 + 0.2, 0.3, 0.90))

        return SignalResult(
            self.name, "SELL", confidence,
            position_size_pct=0.025,
            metadata={
                "phase":         "cash_secured_put",
                "put_strike":    put_strike,
                "premium_est":   round(premium_est, 2),
                "dte_target":    p["dte_target"],
                "put_delta":     p["put_delta"],
                "ivr":           ivr,
                "adx":           adx,
            },
        )

    def backtest(self, price_data: pd.DataFrame, auxiliary_data: dict,
                 params: Optional[dict] = None, **kwargs) -> BacktestResult:
        p      = {**self._DEFAULTS, **(params or {})}
        close  = price_data["close"].astype(float)
        high   = price_data.get("high", close).astype(float)
        low    = price_data.get("low",  close).astype(float)
        vix    = auxiliary_data.get("vix", pd.Series(dtype=float))

        from alan_trader.strategies.ivr_credit_spread import _compute_ivr, _compute_adx
        ivr_s = _compute_ivr(vix)
        adx_s = _compute_adx(high, low, close)
        ma50_s = close.rolling(p["ma_period"]).mean()

        capital   = 100_000.0
        trades    = []
        equity    = []
        in_trade  = False
        dte_rem   = 0
        entry_credit = entry_date = put_k = 0

        for i in range(60, len(close)):
            date  = close.index[i]
            spot  = float(close.iloc[i])
            ivr_v = float(ivr_s.iloc[i]) if i < len(ivr_s) and not pd.isna(ivr_s.iloc[i]) else 0.5
            adx_v = float(adx_s.iloc[i]) if i < len(adx_s) else 20.0
            vix_v = float(vix.iloc[i]) if not vix.empty and i < len(vix) else 20.0
            ma50_v = float(ma50_s.iloc[i]) if not pd.isna(ma50_s.iloc[i]) else spot
            iv_v  = vix_v / 100.0

            if in_trade:
                dte_rem -= 1
                assigned = spot < put_k
                time_exit = dte_rem <= 0
                half_profit = entry_credit * p["profit_target"]

                if time_exit or assigned:
                    if assigned:
                        # assignment: keep premium but take stock loss
                        stock_loss = (put_k - spot) * 100
                        pnl = entry_credit * 100 - stock_loss
                        exit_reason = "assigned"
                    else:
                        pnl = half_profit * 100
                        exit_reason = "profit_target"
                    trades.append({"entry_date": entry_date, "exit_date": date,
                                   "pnl": pnl, "exit_reason": exit_reason})
                    capital  += pnl
                    in_trade  = False
            else:
                trend_ok = spot > ma50_v
                ivr_ok   = ivr_v >= p["ivr_min"]
                adx_ok   = p["adx_min"] <= adx_v <= p["adx_max"]
                vix_ok   = vix_v <= p["vix_max"]
                if ivr_ok and adx_ok and vix_ok and trend_ok:
                    dte_frac     = p["dte_target"] / 252
                    entry_credit = spot * iv_v * np.sqrt(dte_frac) * p["put_delta"] * 0.8
                    put_k        = spot * (1.0 - p["put_delta"] * iv_v * np.sqrt(dte_frac))
                    in_trade     = True
                    entry_date   = date
                    dte_rem      = p["dte_target"]

            equity.append(capital)

        trades_df = pd.DataFrame(trades)
        closed    = trades_df[trades_df["exit_date"].notna()] if not trades_df.empty else trades_df
        eq_series = pd.Series(equity, index=close.index[60:], name="equity")
        daily_ret = eq_series.pct_change().fillna(0.0)

        from alan_trader.risk.metrics import compute_all_metrics
        metrics = compute_all_metrics(daily_ret, eq_series)
        return BacktestResult(self.name, eq_series, daily_ret, closed, metrics, p)
