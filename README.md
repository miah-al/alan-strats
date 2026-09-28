# alan_trader

A strategy-free trading research platform: market data, database, backtest
engine, risk metrics, portfolio management and a Dash UI. Strategies are
plugins. This repository names none of them.

## Strategy plugins

Everything the platform knows about strategies comes through
`alan_trader.strategy_api`:

| Module | Purpose |
|---|---|
| `strategy_api.base` | `BaseStrategy`, `SignalResult`, `BacktestResult`, `StubStrategy` — what a strategy implements |
| `strategy_api.ui` | `StrategyUI` — optional screener / modal / tab hooks, with generic defaults |
| `strategy_api.plugin` | `StrategyPlugin` — what a plugin package publishes (metadata, model dir, guides, docs, tests) |
| `strategy_api.registry` | discovery, the merged `STRATEGY_METADATA`, `get_strategy()`, `get_ui()` |
| `strategy_api.indicators`, `strategy_api.timing_base` | shared quant helpers strategies may import |

Discovery, in order and merged: entry points in the `alan_trader.strategies`
group; packages named in `ALAN_TRADER_STRATEGY_PACKAGES` (comma-separated);
the default package `alan_trader_strategies` if importable. Set
`ALAN_TRADER_STRATEGY_PACKAGES=none` to run with no strategies at all — the UI
renders a notice, the registry is empty, nothing crashes.

The reference plugin is the sibling repository
[alan_trader_strategies](../alan_trader_strategies). A sibling checkout needs
no installation.

The invariant "no platform module names a strategy" is enforced by
`tests/test_strategy_api.py`.

## Import roots

The codebase uses two import roots: `app.*`, `db.*`, `engine.*` … relative
to this directory, and the package `alan_trader.*`. Plugins import the
platform as `alan_trader.*`.

The service and its test suite bind `alan_trader` to this checkout by file
path (`api/bootstrap.py`, `register_platform_package`), so a service checkout
can sit in a folder of any name — e.g. `alan_trader_service/` directly beside
the live `alan_trader/` — and never resolves `alan_trader.*` to the copy next
door. `app/app.py`, `main.py` and `scripts/` still use the older convention
(the parent directory on `sys.path`, which needs the folder to be called
`alan_trader`): run those from the live checkout.

## Running

```
python -m app.app                       # Dash UI
python -m pytest -q                     # platform tests
python -m scripts.rank_strategies       # rank every installed strategy on real data
python -m scripts.check_screeners       # run every installed screener
python -m scripts.check_end_to_end      # guide / layout / signal / popup / paper surfaces
```

Runtime state (signal-alert state, live-trader state, the LSTM trainer's
checkpoints) lives under `runtime_state/`.
