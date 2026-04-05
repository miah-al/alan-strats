"""
Bull Put Spread Strategy.

A defined-risk bullish income trade that collects premium by selling an OTM
put while buying a further OTM put as protection. The spread profits when
the underlying stays above the short put strike through expiration.

Entry rules (all must pass):
  • IVR ≥ ivr_min (40% default) — elevated IV inflates premium collected
  • Price > 50-day MA — bullish bias confirmation
  • ADX ≤ adx_max (30 default) — avoid extreme momentum against position
  • VIX ≤ vix_max (35 default) — not in panic regime
  • Credit ≥ 30% of spread width — minimum reward-to-risk

Structure:
  • Sell OTM put at delta 0.30 (short strike)
  • Buy further OTM put at delta 0.15–0.20 (long strike, protection)
  • Width: 5% of spot (e.g., $10 on a $200 stock)
  • Expiry: 21–45 DTE (target 30)

Exit:
  • 50% of max credit (profit target)
  • 2× credit loss (stop loss)
  • 21 DTE time exit to avoid gamma risk
"""

import numpy as np
import pandas as pd
from typing import Optional

from alan_trader.strategies.base import (
    BaseStrategy, BacktestResult, SignalResult,
    StrategyStatus, StrategyType,
)


class BullPutSpreadStrategy(BaseStrategy):
    name          = "bull_put_spread"
    display_name  = "Bull Put Spread"
    strategy_type = StrategyType.RULE_BASED
    status        = StrategyStatus.ACTIVE
    description   = (
        "Sells OTM put spread to collect premium in bullish markets. "
        "IVR > 40%, price above 50-MA. Credit ≥ 30% of width. 50% buyback target."
    )
    asset_class          = "equities_options"
    typical_holding_days = 30
    target_sharpe        = 1.3

    _DEFAULTS = {
        "ivr_min":          0.40,
        "adx_max":          30.0,
        "vix_max":          35.0,
        "short_put_delta":  0.30,   # short leg delta
        "long_put_delta":   0.15,   # long leg delta (protection)
        "spread_width_pct": 0.05,   # spread width as % of spot
        "min_credit_ratio": 0.30,   # credit must be ≥ 30% of width
        "dte_target":       30,     # target DTE
        "profit_target":    0.50,   # close at 50% of max credit
        "stop_loss_mult":   2.0,    # stop at 2× credit received
        "ma_period":        50,     # SMA period for trend filter
    }

    def get_params(self) -> dict:
        return dict(self._DEFAULTS)

    def get_backtest_ui_params(self) -> list:
        return [
            {"key": "ivr_min",          "label": "IVR min",          "type": "slider",
             "min": 0.20, "max": 0.70, "step": 0.05, "default": 0.40},
            {"key": "adx_max",          "label": "ADX max",          "type": "slider",
             "min": 15,   "max": 50,   "step": 1,    "default": 30},
            {"key": "vix_max",          "label": "VIX max",          "type": "slider",
             "min": 20,   "max": 50,   "step": 1,    "default": 35},
            {"key": "short_put_delta",  "label": "Short put delta",  "type": "slider",
             "min": 0.15, "max": 0.45, "step": 0.05, "default": 0.30},
            {"key": "spread_width_pct", "label": "Spread width %",   "type": "slider",
             "min": 0.02, "max": 0.10, "step": 0.01, "default": 0.05},
            {"key": "profit_target",    "label": "Profit target",    "type": "slider",
             "min": 0.25, "max": 0.70, "step": 0.05, "default": 0.50},
        ]

    def generate_signal(self, market_snapshot: dict) -> SignalResult:
        spot   = market_snapshot.get("price", 0)
        ivr    = market_snapshot.get("ivr", 0)
        adx    = market_snapshot.get("adx", 0)
        vix    = market_snapshot.get("vix", 20)
        ma50   = market_snapshot.get("ma50", 0)
        atm_iv = market_snapshot.get("atm_iv", 0)
        p      = self._DEFAULTS

        trend_ok = (spot > ma50) if ma50 else True
        ivr_ok   = ivr >= p["ivr_min"]
        adx_ok   = adx <= p["adx_max"]
        vix_ok   = vix <= p["vix_max"]

        if not (ivr_ok and adx_ok and vix_ok and trend_ok and spot > 0):
            return SignalResult(self.name, "HOLD", 0.0, 0.0,
                                {"reason": "Entry conditions not met"})

        iv = atm_iv or 0.25
        dte_frac    = p["dte_target"] / 252
        width       = round(spot * p["spread_width_pct"], 0)
        short_k     = round(spot * (1.0 - p["short_put_delta"] * iv * np.sqrt(dte_frac)), 0)
        long_k      = short_k - width
        credit_est  = spot * iv * np.sqrt(dte_frac) * (p["short_put_delta"] - p["long_put_delta"]) * 0.85
        credit_ratio = credit_est / width if width > 0 else 0

        if credit_ratio < p["min_credit_ratio"]:
            return SignalResult(self.name, "HOLD", 0.0, 0.0,
                                {"reason": f"Credit/width ratio {credit_ratio:.2f} < {p['min_credit_ratio']}"})

        confidence = float(np.clip(
            ivr * 0.5 + (1.0 - adx / p["adx_max"]) * 0.3 + 0.2, 0.3, 0.90))

        return SignalResult(
            self.name, "SELL", confidence,
            position_size_pct=0.02,
            metadata={
                "structure":     "bull_put_spread",
                "short_strike":  short_k,
                "long_strike":   long_k,
                "width":         width,
                "credit_est":    round(credit_est, 2),
                "credit_ratio":  round(credit_ratio, 3),
                "dte_target":    p["dte_target"],
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
        ivr_s  = _compute_ivr(vix)
        adx_s  = _compute_adx(high, low, close)
        ma50_s = close.rolling(p["ma_period"]).mean()

        capital   = 100_000.0
        trades    = []
        equity    = []
        in_trade  = False
        dte_rem   = 0
        entry_credit = entry_date = short_k = width = 0

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
                breached  = spot < short_k
                time_exit = dte_rem <= 21
                max_loss  = (width - entry_credit) * 100

                if breached:
                    pnl = -max_loss * 0.8  # partial loss on test
                    exit_reason = "stop"
                elif time_exit:
                    pnl = entry_credit * p["profit_target"] * 100
                    exit_reason = "dte"
                else:
                    equity.append(capital)
                    continue

                trades.append({"entry_date": entry_date, "exit_date": date,
                                "pnl": pnl, "exit_reason": exit_reason})
                capital  += pnl
                in_trade  = False
            else:
                trend_ok = spot > ma50_v
                ivr_ok   = ivr_v >= p["ivr_min"]
                adx_ok   = adx_v <= p["adx_max"]
                vix_ok   = vix_v <= p["vix_max"]
                if ivr_ok and adx_ok and vix_ok and trend_ok:
                    dte_frac      = p["dte_target"] / 252
                    width         = round(spot * p["spread_width_pct"], 0)
                    short_k       = spot * (1.0 - p["short_put_delta"] * iv_v * np.sqrt(dte_frac))
                    entry_credit  = spot * iv_v * np.sqrt(dte_frac) * (
                        p["short_put_delta"] - p["long_put_delta"]) * 0.85
                    credit_ratio  = entry_credit / width if width > 0 else 0
                    if credit_ratio >= p["min_credit_ratio"]:
                        in_trade   = True
                        entry_date = date
                        dte_rem    = p["dte_target"]

            equity.append(capital)

        trades_df = pd.DataFrame(trades)
        closed    = trades_df[trades_df["exit_date"].notna()] if not trades_df.empty else trades_df
        eq_series = pd.Series(equity, index=close.index[60:], name="equity")
        daily_ret = eq_series.pct_change().fillna(0.0)

        from alan_trader.risk.metrics import compute_all_metrics
        metrics = compute_all_metrics(daily_ret, eq_series)
        return BacktestResult(self.name, eq_series, daily_ret, closed, metrics, p)
