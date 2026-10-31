"""
alan_trader.strategy_api — the contract between the platform and strategy plugins.

The platform (this repository) contains no strategy. Strategies live in
separately installed packages that expose a `StrategyPlugin` and are found by
`strategy_api.registry` at start-up. This package is everything a plugin needs
to import from the platform:

  base        BaseStrategy, SignalResult, BacktestResult, StrategyType,
              StrategyStatus, StubStrategy
  ui          StrategyUI, ScanContext, TabSpec, PaperTradeResult — the optional
              screener / modal / tab hooks a strategy can implement
  plugin      StrategyPlugin — what a plugin package publishes
  registry    discovery + the merged STRATEGY_METADATA, get_strategy(), get_ui()
  indicators  shared technical indicators + Black-Scholes re-export
  timing_base helpers for equity-timing overlays

Nothing in here may reference a specific strategy.
"""
from alan_trader.strategy_api.base import (  # noqa: F401
    BaseStrategy, StubStrategy, SignalResult, BacktestResult,
    StrategyType, StrategyStatus,
)
from alan_trader.strategy_api.plugin import StrategyPlugin  # noqa: F401
from alan_trader.strategy_api.ui import (  # noqa: F401
    StrategyUI, ScanContext, TabSpec, PaperTradeResult,
)
