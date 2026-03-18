"""
Multi-strategy portfolio manager.
Handles Kelly position sizing, weight allocation, correlation, and blended equity.
"""

import logging
import numpy as np
import pandas as pd
from typing import Optional

from alan_trader.strategies.base import BacktestResult
from alan_trader.risk import metrics as rm

logger = logging.getLogger(__name__)

TRADING_DAYS = 252


class PortfolioManager:
    def __init__(
        self,
        total_capital: float = 100_000,
        kelly_fraction: float = 0.25,
        max_strategy_weight: float = 0.40,
        min_strategy_weight: float = 0.02,
        rebalance_days: int = 21,
    ):
        self.capital     = total_capital
        self.kelly_frac  = kelly_fraction
        self.max_weight  = max_strategy_weight
        self.min_weight  = min_strategy_weight
        self.rebal_days  = rebalance_days

    # ─────────────────────────────────────────────────────────────────────
    # Kelly sizing
    # ─────────────────────────────────────────────────────────────────────

    def compute_kelly_weights(
        self,
        results: list[BacktestResult],
    ) -> dict[str, float]:
        """
        Fractional Kelly weight for each strategy.
        f* = kelly_fraction * (mu / sigma^2)
        Clipped to [min_weight, max_weight] then normalized to sum to 1.
        """
        raw = {}
        for res in results:
            rets = res.daily_returns.dropna()
            if len(rets) < 5 or rets.std() == 0:
                raw[res.strategy_name] = self.min_weight
                continue
            mu      = float(rets.mean())
            sigma_sq = float(rets.var())
            kelly   = self.kelly_frac * (mu / sigma_sq) if sigma_sq > 0 else 0
            raw[res.strategy_name] = max(self.min_weight, min(self.max_weight, kelly))

        total = sum(raw.values())
        if total == 0:
            equal_w = 1.0 / len(results)
            return {k: equal_w for k in raw}

        normalized = {k: v / total for k, v in raw.items()}
        # Re-clip after normalization
        clipped = {k: max(self.min_weight, min(self.max_weight, v))
                   for k, v in normalized.items()}
        total2 = sum(clipped.values())
        return {k: v / total2 for k, v in clipped.items()}

    # ─────────────────────────────────────────────────────────────────────
    # Correlation
    # ─────────────────────────────────────────────────────────────────────

    def compute_correlation_matrix(
        self,
        results: list[BacktestResult],
    ) -> pd.DataFrame:
        """Correlation of daily returns across strategies."""
        series = {}
        for res in results:
            rets = res.daily_returns.dropna()
            rets.index = pd.to_datetime(rets.index)
            series[res.strategy_name] = rets

        if not series:
            return pd.DataFrame()

        df = pd.DataFrame(series).fillna(0)
        return df.corr()

    # ─────────────────────────────────────────────────────────────────────
    # Blending
    # ─────────────────────────────────────────────────────────────────────

    def blend_equity_curves(
        self,
        results: list[BacktestResult],
        weights: dict[str, float],
    ) -> pd.Series:
        """
        Weighted blend of strategy equity curves.
        Normalizes each curve to start at 1, blends by weight, scales to total capital.
        """
        normalized = {}
        for res in results:
            eq = res.equity_curve
            if eq.empty or eq.iloc[0] == 0:
                continue
            eq.index = pd.to_datetime(eq.index)
            normalized[res.strategy_name] = eq / eq.iloc[0]

        if not normalized:
            return pd.Series(dtype=float)

        # Align on common date range
        all_eq = pd.DataFrame(normalized).fillna(method="ffill").fillna(1.0)

        blended = pd.Series(0.0, index=all_eq.index)
        total_w = 0.0
        for name, norm_eq in all_eq.items():
            w = weights.get(name, 0.0)
            blended += norm_eq * w
            total_w += w

        if total_w > 0:
            blended /= total_w

        return (blended * self.capital).rename("portfolio")

    # ─────────────────────────────────────────────────────────────────────
    # Full portfolio report
    # ─────────────────────────────────────────────────────────────────────

    def build_portfolio_report(
        self,
        results: list[BacktestResult],
        spy_returns: Optional[pd.Series] = None,
    ) -> dict:
        """
        Returns a dict with:
          weights, correlation, blended_equity, portfolio_metrics,
          per_strategy_metrics
        """
        if not results:
            return {}

        weights     = self.compute_kelly_weights(results)
        corr        = self.compute_correlation_matrix(results)
        blended_eq  = self.blend_equity_curves(results, weights)

        portfolio_metrics = {}
        if not blended_eq.empty:
            portfolio_metrics = rm.compute_all_metrics(
                equity_curve=blended_eq,
                benchmark_returns=spy_returns,
            )

        per_strategy = {}
        for res in results:
            per_strategy[res.strategy_name] = res.metrics

        return {
            "weights":            weights,
            "correlation":        corr,
            "blended_equity":     blended_eq,
            "portfolio_metrics":  portfolio_metrics,
            "per_strategy":       per_strategy,
        }

    # ─────────────────────────────────────────────────────────────────────
    # Rolling weights (for allocation-over-time chart)
    # ─────────────────────────────────────────────────────────────────────

    def rolling_weights(
        self,
        results: list[BacktestResult],
        window: int = 60,
    ) -> pd.DataFrame:
        """
        Compute Kelly weights on a rolling window across the backtest period.
        Returns DataFrame: date × strategy_name → weight.
        """
        series = {}
        for res in results:
            rets = res.daily_returns.dropna()
            rets.index = pd.to_datetime(rets.index)
            series[res.strategy_name] = rets

        if not series:
            return pd.DataFrame()

        df     = pd.DataFrame(series).fillna(0)
        dates  = df.index[window:]
        rows   = []

        for i in range(window, len(df)):
            window_df = df.iloc[i - window: i]
            raw = {}
            for col in window_df.columns:
                rets = window_df[col]
                mu   = float(rets.mean())
                var  = float(rets.var())
                raw[col] = max(self.min_weight,
                               min(self.max_weight, self.kelly_frac * mu / var if var > 0 else self.min_weight))
            total = sum(raw.values())
            rows.append({k: v / total for k, v in raw.items()})

        return pd.DataFrame(rows, index=dates)
