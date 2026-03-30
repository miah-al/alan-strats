"""
GEX Positioning Strategy — Dealer Gamma Exposure Regime Filter.

Uses Dealer Gamma Exposure (GEX) to classify the volatility regime and
size SPY / cash exposure accordingly:

  High positive GEX  (VIX < 15  / net_gex > +2B)  → Vol-suppressed; dealers dampen swings.
                                                       Full equity exposure: 90% SPY.
  Mild positive GEX  (VIX 15-18 / net_gex 0..+2B)  → Calm-to-neutral; modest dampening.
                                                       Heavy equity:        80% SPY.
  Neutral / flip zone(VIX 18-22 / net_gex ±0)      → Regime ambiguous; light de-risk.
                                                       Moderate exposure:   60% SPY.
  Negative GEX       (VIX 22-30 / net_gex −2B..0)  → Dealers amplify moves; risk elevated.
                                                       Defensive:           35% SPY.
  Deep negative GEX  (VIX > 30  / net_gex < −2B)   → Crash dynamics; max de-risk.
                                                       Capital preservation: 15% SPY.

Live mode:  net_gex is computed from Polygon options chain and passed via market_snapshot.
Backtest:   VIX is used as a GEX proxy (historically correlated, always available in DB).

Key edge: In positive-GEX regimes, intraday ranges compress and short-volatility trades
thrive. In negative-GEX regimes, drawdowns are amplified — cutting exposure dramatically
outperforms a buy-and-hold baseline.

Parameters:
  vix_low       — VIX ceiling for "high positive GEX" regime  (default 15)
  vix_mid_low   — VIX ceiling for "mild positive GEX" regime  (default 18)
  vix_mid_high  — VIX ceiling for "neutral/flip" regime       (default 22)
  vix_high      — VIX ceiling for "negative GEX" regime       (default 30; above → deep neg)
  gex_pos_thr   — Net GEX ($B) above which live mode calls positive regime  (default +1.5)
  gex_neg_thr   — Net GEX ($B) below which live mode calls negative regime  (default −1.5)
  confirm_days  — Consecutive days in same regime before switching           (default 3)
  cooldown_days — Minimum days between regime changes                         (default 5)
"""

import numpy as np
import pandas as pd

from alan_trader.strategies.base import (
    BaseStrategy, BacktestResult, SignalResult,
    StrategyStatus, StrategyType,
)
from alan_trader.risk.metrics import compute_all_metrics


# ── Regime → SPY weight ──────────────────────────────────────────────────────

_ALLOC: dict[str, float] = {
    "HighPositive":  0.90,   # VIX < 15  — dampened vol, dealers long gamma
    "MildPositive":  0.80,   # VIX 15-18 — calm, moderate dampening
    "Neutral":       0.60,   # VIX 18-22 — near gamma flip, ambiguous
    "Negative":      0.35,   # VIX 22-30 — volatile, dealers short gamma
    "DeepNegative":  0.15,   # VIX > 30  — crash dynamics
}

_REGIME_LABEL: dict[str, str] = {
    "HighPositive":  "High Positive GEX (vol-suppressed)",
    "MildPositive":  "Mild Positive GEX (calm)",
    "Neutral":       "Neutral / Gamma Flip Zone",
    "Negative":      "Negative GEX (volatile)",
    "DeepNegative":  "Deep Negative GEX (crash dynamics)",
}


def _classify_vix(vix: float, vix_low: float, vix_mid_low: float,
                  vix_mid_high: float, vix_high: float) -> str:
    if vix < vix_low:
        return "HighPositive"
    elif vix < vix_mid_low:
        return "MildPositive"
    elif vix < vix_mid_high:
        return "Neutral"
    elif vix < vix_high:
        return "Negative"
    else:
        return "DeepNegative"


def _classify_gex(net_gex: float, pos_thr: float, neg_thr: float) -> str:
    """Classify regime from live net GEX ($B)."""
    if net_gex > pos_thr * 2:
        return "HighPositive"
    elif net_gex > pos_thr:
        return "MildPositive"
    elif net_gex > neg_thr:
        return "Neutral"
    elif net_gex > neg_thr * 2:
        return "Negative"
    else:
        return "DeepNegative"


class GexPositioningStrategy(BaseStrategy):
    name                 = "gex_positioning"
    display_name         = "Dealer Gamma Exposure"
    strategy_type        = StrategyType.RULE_BASED
    status               = StrategyStatus.ACTIVE
    description          = (
        "Classifies the volatility regime from Dealer Gamma Exposure (GEX) and "
        "sizes SPY / cash exposure accordingly. Positive GEX → dealers long gamma "
        "→ vol-suppressed → heavy equity. Negative GEX → dealers short gamma "
        "→ moves amplified → cut exposure. Gamma flip level acts as the regime "
        "boundary. Backtested using VIX as a GEX proxy."
    )
    asset_class          = "equities"
    typical_holding_days = 5
    target_sharpe        = 1.1

    def __init__(
        self,
        vix_low:       float = 15.0,
        vix_mid_low:   float = 18.0,
        vix_mid_high:  float = 22.0,
        vix_high:      float = 30.0,
        gex_pos_thr:   float = 1.5,    # $B
        gex_neg_thr:   float = -1.5,   # $B
        confirm_days:  int   = 3,
        cooldown_days: int   = 5,
        slippage_pct:  float = 0.0005,
    ):
        self.vix_low       = vix_low
        self.vix_mid_low   = vix_mid_low
        self.vix_mid_high  = vix_mid_high
        self.vix_high      = vix_high
        self.gex_pos_thr   = gex_pos_thr
        self.gex_neg_thr   = gex_neg_thr
        self.confirm_days  = confirm_days
        self.cooldown_days = cooldown_days
        self.slippage      = slippage_pct

    # ── Live signal ──────────────────────────────────────────────────────────

    def generate_signal(self, market_snapshot: dict) -> SignalResult:
        net_gex = market_snapshot.get("net_gex")
        vix     = market_snapshot.get("vix", 20.0)

        if net_gex is not None:
            regime = _classify_gex(float(net_gex), self.gex_pos_thr, self.gex_neg_thr)
            source = "live_gex"
        else:
            regime = _classify_vix(float(vix), self.vix_low, self.vix_mid_low,
                                   self.vix_mid_high, self.vix_high)
            source = "vix_proxy"

        spy_weight = _ALLOC[regime]
        signal     = "BUY" if spy_weight >= 0.75 else ("SELL" if spy_weight <= 0.35 else "HOLD")

        return SignalResult(
            strategy_name=self.name,
            signal=signal,
            confidence=0.75,
            position_size_pct=spy_weight,
            metadata={
                "regime":      regime,
                "regime_label":_REGIME_LABEL[regime],
                "spy_weight":  spy_weight,
                "source":      source,
                "net_gex":     net_gex,
                "vix":         vix,
            },
        )

    # ── Backtest ─────────────────────────────────────────────────────────────

    def backtest(
        self,
        price_data:       pd.DataFrame,
        auxiliary_data:   dict,
        starting_capital: float = 100_000,
        vix_low:          float | None = None,
        vix_mid_low:      float | None = None,
        vix_mid_high:     float | None = None,
        vix_high:         float | None = None,
        confirm_days:     int   | None = None,
        cooldown_days:    int   | None = None,
        **kwargs,
    ) -> BacktestResult:

        v_low      = vix_low      if vix_low      is not None else self.vix_low
        v_mid_low  = vix_mid_low  if vix_mid_low  is not None else self.vix_mid_low
        v_mid_high = vix_mid_high if vix_mid_high is not None else self.vix_mid_high
        v_high     = vix_high     if vix_high     is not None else self.vix_high
        conf_days  = confirm_days  if confirm_days  is not None else self.confirm_days
        cool_days  = cooldown_days if cooldown_days is not None else self.cooldown_days

        # ── Align data ────────────────────────────────────────────────────
        price_data = price_data.copy()
        price_data.index = pd.to_datetime(price_data.index)

        vix_df = auxiliary_data.get("vix", pd.DataFrame())
        if vix_df.empty:
            raise ValueError(
                "No VIX data found. Go to Data Manager → Macro Bars and sync first."
            )
        vix_df = vix_df.copy()
        vix_df.index = pd.to_datetime(vix_df.index)
        vix = vix_df["close"].reindex(price_data.index).ffill().infer_objects(copy=False).fillna(20.0)

        close   = price_data["close"]
        bh_ret  = close.pct_change()

        # ── Raw regime from VIX proxy ─────────────────────────────────────
        raw_regime = pd.Series(
            [_classify_vix(float(v), v_low, v_mid_low, v_mid_high, v_high)
             for v in vix.values],
            index=price_data.index,
        )

        # ── N-day confirmation filter ─────────────────────────────────────
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
        capital       = float(starting_capital)
        equity_list   = []
        trades_list   = []
        all_dates     = list(price_data.index)
        cur_spy_w     = _ALLOC["Neutral"]
        cur_regime    = "Neutral"
        entry_date    = all_dates[0]
        entry_capital = capital
        spy_weights_l = []
        days_since    = cool_days   # start ready to trade

        for i, dt in enumerate(all_dates):
            regime  = regime_series.iloc[i]
            spy_w   = _ALLOC[regime]

            if i > 0:
                s_ret = float(bh_ret.iloc[i]) if not np.isnan(bh_ret.iloc[i]) else 0.0
                capital += capital * cur_spy_w * s_ret
                days_since += 1

            # Regime change with cooldown
            if regime != cur_regime and i > 0 and days_since >= cool_days:
                slip = capital * abs(spy_w - cur_spy_w) * self.slippage
                capital -= slip
                trades_list.append({
                    "entry_date":  entry_date.date(),
                    "exit_date":   dt.date(),
                    "spread_type": _REGIME_LABEL.get(cur_regime, cur_regime),
                    "entry_cost":  round(entry_capital, 2),
                    "exit_value":  round(capital, 2),
                    "pnl":         round(capital - entry_capital, 2),
                    "exit_reason": f"regime→{regime}",
                })
                cur_spy_w     = spy_w
                cur_regime    = regime
                entry_date    = dt
                entry_capital = capital
                days_since    = 0

            equity_list.append(capital)
            spy_weights_l.append(cur_spy_w)

        # Close final period
        if entry_capital != capital:
            trades_list.append({
                "entry_date":  entry_date.date(),
                "exit_date":   all_dates[-1].date(),
                "spread_type": _REGIME_LABEL.get(cur_regime, cur_regime),
                "entry_cost":  round(entry_capital, 2),
                "exit_value":  round(capital, 2),
                "pnl":         round(capital - entry_capital, 2),
                "exit_reason": "end_of_period",
            })

        equity    = pd.Series(equity_list, index=price_data.index, dtype=float)
        daily_ret = equity.pct_change().dropna()
        bh_benchmark = close.pct_change().reindex(equity.index).dropna()

        trades_df = pd.DataFrame(trades_list) if trades_list else pd.DataFrame(
            columns=["entry_date", "exit_date", "spread_type",
                     "entry_cost", "exit_value", "pnl", "exit_reason"]
        )

        metrics = compute_all_metrics(
            equity_curve=equity,
            trades_df=trades_df,
            benchmark_returns=bh_benchmark,
        )

        return BacktestResult(
            strategy_name=self.name,
            equity_curve=equity,
            daily_returns=daily_ret,
            trades=trades_df,
            metrics=metrics,
            params=self.get_params(),
            extra={
                "regime_series": regime_series,
                "spy_weights":   pd.Series(spy_weights_l, index=price_data.index),
                "vix":           vix,
                "spy_returns":   bh_ret,
            },
        )

    # ── UI params ─────────────────────────────────────────────────────────────

    def get_backtest_ui_params(self) -> list:
        return [
            {
                "key": "vix_low", "label": "VIX — High Positive GEX ceiling",
                "type": "slider", "min": 10, "max": 20, "default": 15, "step": 1,
                "col": 0, "row": 0,
                "help": "VIX below this → dealers long gamma, full 90% SPY allocation",
            },
            {
                "key": "vix_mid_low", "label": "VIX — Mild Positive GEX ceiling",
                "type": "slider", "min": 13, "max": 25, "default": 18, "step": 1,
                "col": 1, "row": 0,
                "help": "VIX in this band → calm-to-neutral, 80% SPY",
            },
            {
                "key": "vix_mid_high", "label": "VIX — Gamma Flip zone ceiling",
                "type": "slider", "min": 18, "max": 30, "default": 22, "step": 1,
                "col": 2, "row": 0,
                "help": "VIX in this band → near gamma flip, 60% SPY",
            },
            {
                "key": "vix_high", "label": "VIX — Negative GEX ceiling",
                "type": "slider", "min": 25, "max": 50, "default": 30, "step": 1,
                "col": 0, "row": 1,
                "help": "VIX in this band → negative GEX, 35% SPY. Above → deep negative (15%)",
            },
            {
                "key": "confirm_days", "label": "Confirmation days",
                "type": "slider", "min": 1, "max": 10, "default": 3, "step": 1,
                "col": 1, "row": 1,
                "help": "Consecutive days in same VIX regime before switching allocation",
            },
            {
                "key": "cooldown_days", "label": "Cooldown days",
                "type": "slider", "min": 0, "max": 15, "default": 5, "step": 1,
                "col": 2, "row": 1,
                "help": "Minimum days between allocation changes — reduces whipsawing",
            },
        ]

    def get_params(self) -> dict:
        return {
            "vix_low":       self.vix_low,
            "vix_mid_low":   self.vix_mid_low,
            "vix_mid_high":  self.vix_mid_high,
            "vix_high":      self.vix_high,
            "gex_pos_thr":   self.gex_pos_thr,
            "gex_neg_thr":   self.gex_neg_thr,
            "confirm_days":  self.confirm_days,
            "cooldown_days": self.cooldown_days,
            "slippage_pct":  self.slippage,
        }
