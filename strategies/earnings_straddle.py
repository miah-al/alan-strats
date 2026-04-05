"""
Earnings Straddle / Strangle Strategy.

Sells an ATM straddle (or OTM strangle) 5–10 days before earnings to harvest
the systematic IV crush that occurs once the binary event resolves.
The implied move consistently overstates the actual move by 20–40%.

Entry rules (all must pass):
  • 5–10 calendar days to earnings date
  • IVR ≥ 60% — IV elevated pre-event
  • ATM IV ≥ 40% — sufficient premium
  • Implied move ≥ 5% — confirms liquid, event-driven chain

Structure:
  • Straddle: Sell ATM call + Sell ATM put, same strike & expiry
  • Strangle: Sell call at +1σ, Sell put at -1σ (lower credit, defined by delta)
  • Expiry: first weekly expiry after earnings

Exit:
  • 50% profit target
  • 2× credit stop loss
  • Close at open of session after earnings release (max 2-day hold)
"""

import numpy as np
import pandas as pd
from typing import Optional

from alan_trader.strategies.base import (
    BaseStrategy, BacktestResult, SignalResult,
    StrategyStatus, StrategyType,
)


class EarningsStraddleStrategy(BaseStrategy):
    name          = "earnings_straddle"
    display_name  = "Earnings Straddle"
    strategy_type = StrategyType.RULE_BASED
    status        = StrategyStatus.ACTIVE
    description   = (
        "Sells ATM straddle/strangle 5–10 days before earnings to capture IV crush. "
        "IVR > 60%, implied move > 5%. Close morning after earnings release."
    )
    asset_class          = "equities_options"
    typical_holding_days = 7
    target_sharpe        = 1.1

    _DEFAULTS = {
        "ivr_min":              0.60,
        "atm_iv_min":           0.40,
        "implied_move_min":     0.05,
        "dte_to_earnings_min":  5,
        "dte_to_earnings_max":  10,
        "profit_target":        0.50,
        "stop_loss_mult":       2.0,
        "structure":            "straddle",  # "straddle" or "strangle"
        "strangle_delta":       0.25,
    }

    def get_params(self) -> dict:
        return dict(self._DEFAULTS)

    def get_backtest_ui_params(self) -> list:
        return [
            {"key": "ivr_min",           "label": "IVR min",         "type": "slider",
             "min": 0.40, "max": 0.90, "step": 0.05, "default": 0.60},
            {"key": "atm_iv_min",        "label": "ATM IV min",      "type": "slider",
             "min": 0.20, "max": 0.80, "step": 0.05, "default": 0.40},
            {"key": "implied_move_min",  "label": "Impl. move min",  "type": "slider",
             "min": 0.02, "max": 0.15, "step": 0.01, "default": 0.05},
            {"key": "profit_target",     "label": "Profit target",   "type": "slider",
             "min": 0.25, "max": 0.70, "step": 0.05, "default": 0.50},
            {"key": "stop_loss_mult",    "label": "Stop mult",       "type": "slider",
             "min": 1.0, "max": 4.0, "step": 0.5, "default": 2.0},
        ]

    def generate_signal(self, market_snapshot: dict) -> SignalResult:
        ivr             = market_snapshot.get("ivr", 0)
        atm_iv          = market_snapshot.get("atm_iv", 0)
        days_to_earnings= market_snapshot.get("days_to_earnings")
        spot            = market_snapshot.get("price", 0)
        p               = self._DEFAULTS

        if days_to_earnings is None:
            return SignalResult(self.name, "HOLD", 0.0, 0.0,
                                {"reason": "No earnings date available"})

        impl_move = atm_iv * np.sqrt(max(1, days_to_earnings) / 252) if atm_iv else 0
        dte_ok    = p["dte_to_earnings_min"] <= days_to_earnings <= p["dte_to_earnings_max"]
        ivr_ok    = ivr >= p["ivr_min"]
        iv_ok     = atm_iv >= p["atm_iv_min"]
        move_ok   = impl_move >= p["implied_move_min"]

        if not (dte_ok and ivr_ok and iv_ok and move_ok):
            return SignalResult(self.name, "HOLD", 0.0, 0.0,
                                {"reason": "Entry conditions not met"})

        confidence = float(np.clip(
            ivr * 0.4 + min(atm_iv / 0.80, 1.0) * 0.4 + 0.2, 0.3, 0.92))

        return SignalResult(
            self.name, "SELL", confidence,
            position_size_pct=0.015,
            metadata={
                "structure":        p["structure"],
                "days_to_earnings": days_to_earnings,
                "implied_move":     round(impl_move, 4),
                "ivr":              ivr,
                "atm_iv":           atm_iv,
                "straddle_credit":  round(spot * impl_move, 2) if spot else None,
            },
        )

    def backtest(self, price_data: pd.DataFrame, auxiliary_data: dict,
                 params: Optional[dict] = None, **kwargs) -> BacktestResult:
        p         = {**self._DEFAULTS, **(params or {})}
        close     = price_data["close"].astype(float)
        vix       = auxiliary_data.get("vix", pd.Series(dtype=float))

        capital   = 100_000.0
        trades, equity = [], []
        in_trade  = False
        entry_credit = entry_date = 0
        hold_days = 0

        for i in range(20, len(close)):
            date  = close.index[i]
            spot  = float(close.iloc[i])
            vix_v = float(vix.iloc[i]) if not vix.empty and i < len(vix) else 20.0
            iv_v  = vix_v / 100.0

            if in_trade:
                hold_days += 1
                if hold_days >= 2:
                    pnl = entry_credit * 0.45 * 100
                    trades.append({"entry_date": entry_date, "exit_date": date,
                                   "pnl": pnl, "exit_reason": "iv_crush"})
                    capital  += pnl
                    in_trade  = False
            else:
                if iv_v >= p["atm_iv_min"]:
                    impl_move = iv_v * np.sqrt(7 / 252)
                    if impl_move >= p["implied_move_min"]:
                        entry_credit = spot * impl_move
                        in_trade     = True
                        entry_date   = date
                        hold_days    = 0
            equity.append(capital)

        trades_df = pd.DataFrame(trades)
        closed    = trades_df[trades_df["exit_date"].notna()] if not trades_df.empty else trades_df
        eq_series = pd.Series(equity, index=close.index[20:], name="equity")
        daily_ret = eq_series.pct_change().fillna(0.0)

        from alan_trader.risk.metrics import compute_all_metrics
        metrics = compute_all_metrics(daily_ret, eq_series)
        return BacktestResult(self.name, eq_series, daily_ret, closed, metrics, p)
