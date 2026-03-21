"""
Rates / SPY Rotation Strategy  (v2 — improved signal quality).

Classifies the daily market regime from the 20-day change in the 10-year
Treasury yield and the 20-day SPY return, then allocates between SPY and TLT
according to the active regime.

Five regimes:
  Growth    : rates ↑  + stocks ↑  → 80% SPY / 10% TLT / 10% cash
  Inflation : rates ↑  + stocks ↓  → 40% SPY /  5% TLT / 55% cash
  Fear      : rates ↓  + stocks ↓  → 20% SPY / 70% TLT / 10% cash
                                       (20% SPY / 10% TLT / 70% cash when 10Y > 3.5%)
  Risk-On   : rates ↓  + stocks ↑  → 90% SPY / 10% TLT /  0% cash
  Transition: ambiguous             → 60% SPY / 30% TLT / 10% cash

v2 improvements over v1:
  1. Wider thresholds (20 bps / 3%) — fewer false signals in high-vol markets
  2. 7-day confirmation (was 3) — eliminates most whipsaw regime flips
  3. 10-day cooldown after each regime change — no re-trigger within cooldown window
  4. Rate-adaptive Fear allocation — when 10Y > 3.5%, bonds are NOT a safe haven;
     Fear regime shifts to 70% cash instead of 70% TLT
  5. Trend filter — bearish regimes (Inflation / Fear) only activate when SPY is
     below its 50-day SMA, blocking false bearish signals during temporary dips
"""

import numpy as np
import pandas as pd

from alan_trader.strategies.base import (
    BaseStrategy, BacktestResult, SignalResult,
    StrategyStatus, StrategyType,
)
from alan_trader.risk.metrics import compute_all_metrics


# ── Regime allocations ──────────────────────────────────────────────────────
# {regime: (spy_weight, tlt_weight)}  — remainder sits in cash

_ALLOC: dict[str, tuple[float, float]] = {
    "Growth":          (0.80, 0.10),
    "Inflation":       (0.40, 0.05),
    "Fear":            (0.20, 0.70),   # standard (low-rate) Fear
    "Fear-HighRate":   (0.20, 0.10),   # rate-adaptive Fear: cash instead of TLT
    "Risk-On":         (0.90, 0.10),
    "Transition":      (0.60, 0.30),
}

# Rate level above which TLT is NOT treated as a safe haven in Fear
_FEAR_RATE_THRESHOLD = 0.035   # 3.5%


class RatesSpyRotationStrategy(BaseStrategy):
    name                 = "rates_spy_rotation"
    display_name         = "TLT / SPY Rotation"
    strategy_type        = StrategyType.RULE_BASED
    status               = StrategyStatus.ACTIVE
    description          = (
        "Rotate between SPY and TLT based on rate-equity regime. "
        "Five regimes (Growth / Inflation / Fear / Risk-On / Transition) detected from "
        "20-day yield change and SPY return. Wider thresholds, 7-day confirmation, "
        "10-day cooldown, rate-adaptive Fear allocation, and 50-day trend filter."
    )
    asset_class          = "equities"
    typical_holding_days = 21
    target_sharpe        = 0.9

    def __init__(
        self,
        yield_threshold:  float = 0.002,   # 20 bps in decimal  (was 10 bps)
        return_threshold: float = 0.03,    # 3% SPY 20-day return (was 2%)
        confirm_days:     int   = 7,       # consecutive days before regime switch (was 3)
        cooldown_days:    int   = 10,      # days before next regime change is allowed
        use_trend_filter: bool  = True,    # require SPY < 50-day SMA for bearish regimes
        slippage_pct:     float = 0.0005,  # 5 bps round-trip slippage
    ):
        self.yield_threshold  = yield_threshold
        self.return_threshold = return_threshold
        self.confirm_days     = confirm_days
        self.cooldown_days    = cooldown_days
        self.use_trend_filter = use_trend_filter
        self.slippage         = slippage_pct

    # ── Signal (live) ──────────────────────────────────────────────────────

    def generate_signal(self, market_snapshot: dict) -> SignalResult:
        regime = market_snapshot.get("regime", "Transition")
        spy_w, tlt_w = _ALLOC.get(regime, _ALLOC["Transition"])
        signal = "BUY" if spy_w >= 0.70 else ("SELL" if spy_w <= 0.40 else "HOLD")
        return SignalResult(
            strategy_name=self.name,
            signal=signal,
            confidence=0.7,
            position_size_pct=spy_w,
            metadata={"regime": regime, "spy_weight": spy_w, "tlt_weight": tlt_w},
        )

    # ── Backtest ───────────────────────────────────────────────────────────

    def backtest(
        self,
        price_data: pd.DataFrame,
        auxiliary_data: dict,
        starting_capital:  float = 100_000,
        yield_threshold:   float | None = None,
        return_threshold:  float | None = None,
        confirm_days:      int   | None = None,
        cooldown_days:     int   | None = None,
        use_trend_filter:  bool  | None = None,
        **kwargs,
    ) -> BacktestResult:

        # UI sliders send bps/% integers — convert to decimals
        yield_thr = yield_threshold
        if yield_thr is not None:
            if yield_thr >= 1:
                yield_thr = yield_thr / 10_000
        else:
            yield_thr = self.yield_threshold

        return_thr = return_threshold
        if return_thr is not None:
            if return_thr >= 1:
                return_thr = return_thr / 100
        else:
            return_thr = self.return_threshold

        conf_days    = confirm_days    if confirm_days    is not None else self.confirm_days
        cool_days    = cooldown_days   if cooldown_days   is not None else self.cooldown_days
        trend_filter = use_trend_filter if use_trend_filter is not None else self.use_trend_filter

        # ── Align data ────────────────────────────────────────────────────
        price_data = price_data.copy()
        price_data.index = pd.to_datetime(price_data.index)

        rate10y_df = auxiliary_data.get("rate10y", pd.DataFrame())
        tlt_df     = auxiliary_data.get("tlt",     pd.DataFrame())
        vix_df     = auxiliary_data.get("vix",     pd.DataFrame())

        if rate10y_df.empty:
            raise ValueError(
                "No 10Y rate data found. Go to Data Manager → Macro Bars and sync first."
            )
        if tlt_df is None or (isinstance(tlt_df, pd.DataFrame) and tlt_df.empty):
            raise ValueError(
                "No TLT price data found.\n\n"
                "Go to Data Manager → Sync from Polygon, select TLT, "
                "and click 'Sync Price Bars'."
            )

        rate10y_df = rate10y_df.copy()
        rate10y_df.index = pd.to_datetime(rate10y_df.index)
        rate10y = rate10y_df["close"].reindex(price_data.index).ffill().infer_objects(copy=False)

        tlt_df = tlt_df.copy()
        tlt_df.index = pd.to_datetime(tlt_df.index)
        tlt_ret = tlt_df["close"].reindex(price_data.index).ffill().infer_objects(copy=False).pct_change()

        spy_close = price_data["close"]
        spy_ret   = spy_close.pct_change()

        if not vix_df.empty:
            vix_df = vix_df.copy()
            vix_df.index = pd.to_datetime(vix_df.index)
            vix = vix_df["close"].reindex(price_data.index).ffill().infer_objects(copy=False).fillna(20.0)
        else:
            vix = pd.Series(20.0, index=price_data.index)

        # ── Fix 5: 50-day trend filter ────────────────────────────────────
        spy_ma50 = spy_close.rolling(50, min_periods=20).mean()

        # ── Regime classification ─────────────────────────────────────────
        rate_change_20d = rate10y - rate10y.shift(20)
        spy_return_20d  = spy_close.pct_change(20)

        def _classify(rc, sr, price, ma50, r10y) -> str:
            if np.isnan(rc) or np.isnan(sr):
                return "Transition"
            above_ma = (not np.isnan(ma50)) and (price > ma50)
            # Fix 5: block bearish regimes when price is above 50-day MA
            if rc > yield_thr and sr > return_thr:
                return "Growth"
            elif rc > yield_thr and sr < -return_thr:
                # Inflation only if below trend
                return "Inflation" if (not trend_filter or not above_ma) else "Transition"
            elif rc < -yield_thr and sr < -return_thr:
                # Fear only if below trend; Fix 4: use cash-heavy allocation when rates elevated
                if trend_filter and above_ma:
                    return "Transition"
                return "Fear-HighRate" if (not np.isnan(r10y) and r10y > _FEAR_RATE_THRESHOLD) else "Fear"
            elif rc < -yield_thr and sr > return_thr:
                return "Risk-On"
            else:
                return "Transition"

        raw_regime = pd.Series(
            [_classify(rc, sr, px, ma, r10)
             for rc, sr, px, ma, r10 in zip(
                 rate_change_20d.values,
                 spy_return_20d.values,
                 spy_close.values,
                 spy_ma50.values,
                 rate10y.values,
             )],
            index=price_data.index,
        )

        # ── Fix 2: N-day confirmation ─────────────────────────────────────
        confirmed = raw_regime.copy()
        streak = 1
        for i in range(1, len(raw_regime)):
            if raw_regime.iloc[i] == raw_regime.iloc[i - 1]:
                streak += 1
            else:
                streak = 1
            if streak < conf_days:
                confirmed.iloc[i] = confirmed.iloc[i - 1]
        regime_series = confirmed

        # ── Portfolio simulation ──────────────────────────────────────────
        capital        = float(starting_capital)
        equity_list    = []
        trades_list    = []
        all_dates      = list(price_data.index)
        current_spy_w  = 0.60
        current_tlt_w  = 0.30
        current_regime = "Transition"
        entry_date     = all_dates[0]
        entry_capital  = capital
        spy_weights_l  = []
        tlt_weights_l  = []
        days_since_change = cool_days   # start ready to trade

        for i, dt in enumerate(all_dates):
            regime       = regime_series.iloc[i]
            spy_w, tlt_w = _ALLOC.get(regime, _ALLOC["Transition"])

            # Daily P&L
            if i > 0:
                s_ret = float(spy_ret.iloc[i])   if not np.isnan(spy_ret.iloc[i])  else 0.0
                t_ret = float(tlt_ret.iloc[i])   if not np.isnan(tlt_ret.iloc[i]) else 0.0
                capital += capital * (current_spy_w * s_ret + current_tlt_w * t_ret)
                days_since_change += 1

            # Fix 3: only rebalance if outside cooldown window
            if regime != current_regime and i > 0 and days_since_change >= cool_days:
                slippage_cost = (
                    capital * abs(spy_w - current_spy_w) * self.slippage
                    + capital * abs(tlt_w - current_tlt_w) * self.slippage
                )
                capital -= slippage_cost
                period_pnl = round(capital - entry_capital, 2)
                trades_list.append({
                    "entry_date":  entry_date.date(),
                    "exit_date":   dt.date(),
                    "spread_type": f"{current_regime} ({round(current_spy_w*100)}% SPY / {round(current_tlt_w*100)}% TLT)",
                    "entry_cost":  round(entry_capital, 2),
                    "exit_value":  round(capital, 2),
                    "pnl":         period_pnl,
                    "exit_reason": f"regime→{regime}",
                })
                current_spy_w     = spy_w
                current_tlt_w     = tlt_w
                current_regime    = regime
                entry_date        = dt
                entry_capital     = capital
                days_since_change = 0

            equity_list.append(capital)
            spy_weights_l.append(current_spy_w)
            tlt_weights_l.append(current_tlt_w)

        # Close final open period
        if entry_capital != capital:
            period_pnl = round(capital - entry_capital, 2)
            trades_list.append({
                "entry_date":  entry_date.date(),
                "exit_date":   all_dates[-1].date(),
                "spread_type": f"{current_regime} ({round(current_spy_w*100)}% SPY / {round(current_tlt_w*100)}% TLT)",
                "entry_cost":  round(entry_capital, 2),
                "exit_value":  round(capital, 2),
                "pnl":         period_pnl,
                "exit_reason": "end_of_period",
            })

        equity    = pd.Series(equity_list, index=price_data.index, dtype=float)
        daily_ret = equity.pct_change().dropna()
        spy_bh    = price_data["close"].pct_change().reindex(equity.index).dropna()

        trades_df = pd.DataFrame(trades_list) if trades_list else pd.DataFrame(
            columns=["entry_date", "exit_date", "spread_type",
                     "entry_cost", "exit_value", "pnl", "exit_reason"]
        )

        metrics = compute_all_metrics(
            equity_curve=equity,
            trades_df=trades_df,
            benchmark_returns=spy_bh,
        )

        return BacktestResult(
            strategy_name=self.name,
            equity_curve=equity,
            daily_returns=daily_ret,
            trades=trades_df,
            metrics=metrics,
            params=self.get_params(),
            extra={
                "regime_series":  regime_series,
                "spy_weights":    pd.Series(spy_weights_l, index=price_data.index),
                "tlt_weights":    pd.Series(tlt_weights_l, index=price_data.index),
                "spy_returns":    spy_ret,
                "tlt_returns":    tlt_ret,
                "rate10y":        rate10y,
                "vix":            vix,
            },
        )

    # ── UI params ──────────────────────────────────────────────────────────

    def get_backtest_ui_params(self) -> list:
        return [
            {
                "key": "yield_threshold",
                "label": "Yield threshold (bps)",
                "type": "slider", "min": 5, "max": 30, "default": 20, "step": 5,
                "col": 0, "row": 0,
                "help": "20-day yield change in bps to classify as rising/falling regime",
            },
            {
                "key": "return_threshold",
                "label": "Return threshold (%)",
                "type": "slider", "min": 1, "max": 5, "default": 3, "step": 1,
                "col": 1, "row": 0,
                "help": "20-day SPY return % to classify as bullish/bearish",
            },
            {
                "key": "confirm_days",
                "label": "Confirmation days",
                "type": "slider", "min": 1, "max": 14, "default": 7, "step": 1,
                "col": 2, "row": 0,
                "help": "Consecutive days in same regime before switching positions",
            },
            {
                "key": "cooldown_days",
                "label": "Cooldown days",
                "type": "slider", "min": 0, "max": 20, "default": 10, "step": 1,
                "col": 0, "row": 1,
                "help": "Minimum days between regime changes — prevents rapid whipsawing",
            },
            {
                "key": "use_trend_filter",
                "label": "50-day trend filter",
                "type": "checkbox", "default": True,
                "col": 1, "row": 1,
                "help": "Block Inflation/Fear regimes when SPY is above its 50-day MA",
            },
        ]

    def get_params(self) -> dict:
        return {
            "yield_threshold":  self.yield_threshold,
            "return_threshold": self.return_threshold,
            "confirm_days":     self.confirm_days,
            "cooldown_days":    self.cooldown_days,
            "use_trend_filter": self.use_trend_filter,
            "slippage_pct":     self.slippage,
        }

    def _empty_result(self, capital: float) -> BacktestResult:
        eq = pd.Series([capital], dtype=float)
        return BacktestResult(
            strategy_name=self.name,
            equity_curve=eq,
            daily_returns=pd.Series(dtype=float),
            trades=pd.DataFrame(),
            metrics={},
            params=self.get_params(),
        )
