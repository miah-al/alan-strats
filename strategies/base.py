"""
Abstract base class for all trading strategies.
Both AI-driven and rule-based strategies inherit from BaseStrategy.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import pandas as pd
import numpy as np


class StrategyType(Enum):
    AI_DRIVEN  = "ai"
    RULE_BASED = "rule"
    HYBRID     = "hybrid"


class StrategyStatus(Enum):
    ACTIVE   = "active"    # Fully implemented and enabled
    STUB     = "stub"      # Registered but not yet implemented
    DISABLED = "disabled"  # Implemented but switched off


@dataclass
class SignalResult:
    """Standardized signal output returned by every strategy."""
    strategy_name:    str
    signal:           str          # "BUY", "SELL", "HOLD"
    confidence:       float        # 0.0 – 1.0
    position_size_pct: float       # Recommended fraction of portfolio (pre-Kelly)
    metadata:         dict = field(default_factory=dict)


@dataclass
class BacktestResult:
    """Standardized backtest output consumed by PortfolioManager and risk metrics."""
    strategy_name:  str
    equity_curve:   pd.Series      # DatetimeIndex or date index → dollar value
    daily_returns:  pd.Series      # DatetimeIndex → daily pct change
    trades:         pd.DataFrame   # columns: entry_date, exit_date, pnl, ...
    metrics:        dict           # output of risk.metrics.compute_all_metrics()
    params:         dict = field(default_factory=dict)   # hyperparams used
    extra:          dict = field(default_factory=dict)   # strategy-specific extras (predictions, model summary, etc.)


class BaseStrategy(ABC):
    """
    Abstract base for all 30 strategies.

    Subclasses must set:
      name          : str  (unique slug, e.g. 'options_spread')
      display_name  : str  (human label)
      strategy_type : StrategyType
      status        : StrategyStatus
      description   : str

    Subclasses must implement:
      generate_signal(market_snapshot) -> SignalResult
      backtest(price_data, auxiliary_data, ...) -> BacktestResult
      get_params() -> dict
    """

    name:          str = "base"
    display_name:  str = "Base Strategy"
    strategy_type: StrategyType  = StrategyType.RULE_BASED
    status:        StrategyStatus = StrategyStatus.STUB
    description:   str = ""
    asset_class:   str = "equities"
    typical_holding_days: int = 5
    target_sharpe: float = 1.0

    @abstractmethod
    def generate_signal(self, market_snapshot: dict) -> SignalResult:
        """
        Called live. Must be fast — no training inside.
        market_snapshot keys (all optional, strategies extract what they need):
          spy_price, vix, rate_10y, rate_2y, days_to_next_exdiv,
          next_dividend_yield, features_df (last N rows of feature matrix)
        """
        ...

    @abstractmethod
    def backtest(
        self,
        price_data: pd.DataFrame,    # SPY OHLCV, date-indexed
        auxiliary_data: dict,        # {"vix": df, "rate2y": df, "rate10y": df,
                                     #  "news": df, "dividends": df, ...}
        starting_capital: float = 100_000,
        **kwargs,
    ) -> BacktestResult:
        """Walk-forward simulation. No look-ahead bias."""
        ...

    def fit(self, features: np.ndarray, labels: np.ndarray) -> dict:
        """
        Optional training step. Only AI strategies override.
        Returns training history dict (may be empty for rule-based).
        """
        return {}

    @abstractmethod
    def get_params(self) -> dict:
        """Return all hyperparameters as a flat dict for display."""
        ...

    def is_trainable(self) -> bool:
        """Return True if this strategy requires/supports ML training."""
        return False

    def get_model_name(self, ticker: str = "SPY") -> str:
        """Return unique checkpoint name for this strategy + ticker combo."""
        return f"{self.name}_{ticker.lower()}"

    def get_backtest_ui_params(self) -> list:
        """
        Return a list of param-spec dicts used by the generic backtest UI renderer.
        Each dict: {"key", "label", "type", "default", ...widget-specific kwargs...}
        "col" (0/1/2) groups params into a 3-column row; omit for full-width.
        "row" groups multiple column rows (default 0).
        Supported types: slider, select_slider, selectbox, checkbox, number_input.
        """
        return []

    def is_ready(self) -> bool:
        return self.status == StrategyStatus.ACTIVE

    def __repr__(self) -> str:
        return (f"<{self.__class__.__name__} name={self.name!r} "
                f"type={self.strategy_type.value} status={self.status.value}>")


# ─────────────────────────────────────────────────────────────────────────────
# Sentinel for unimplemented strategies
# ─────────────────────────────────────────────────────────────────────────────

class StubStrategy(BaseStrategy):
    """
    Placeholder returned by the registry for not-yet-implemented strategies.
    generate_signal() always returns HOLD.
    backtest() raises NotImplementedError.
    """

    def __init__(self, slug: str, meta: dict):
        self.name         = slug
        self.display_name = meta.get("display_name", slug)
        self.strategy_type = StrategyType(meta.get("type", "rule"))
        self.status       = StrategyStatus.STUB
        self.description  = meta.get("description", "Not yet implemented.")
        self.asset_class  = meta.get("asset_class", "equities")
        self.typical_holding_days = meta.get("typical_holding_days", 5)
        self.target_sharpe = meta.get("target_sharpe", 1.0)

    def generate_signal(self, market_snapshot: dict) -> SignalResult:
        return SignalResult(self.name, "HOLD", 0.0, 0.0,
                            metadata={"reason": "stub — not implemented"})

    def backtest(self, price_data, auxiliary_data, starting_capital=100_000, **kwargs) -> BacktestResult:
        raise NotImplementedError(f"Strategy '{self.name}' is a stub and has not been implemented yet.")

    def get_params(self) -> dict:
        return {}
