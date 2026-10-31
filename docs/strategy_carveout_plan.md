# Strategy carve-out — design record (done 2026-09-03)

`alan_trader` is now a strategy-free platform (data, DB, backtest engine, risk,
portfolio, UI). Every strategy lives in the sibling repository
`alan_trader_strategies` as an installable plugin the platform discovers at
start-up, **one self-contained folder per strategy** that shares no code with
any other strategy. Two invariants are enforced by tests:

- no platform module names a strategy slug (`tests/test_strategy_api.py`);
- no strategy folder imports another strategy's folder or a shared plugin
  module (independence scan; the plugin's own suite).

## What moved where

| From (platform) | To (plugin) |
|---|---|
| `strategies/<slug>.py` (44 modules, history kept via `git subtree split`) | `strategies/<slug>/strategy.py` |
| `strategies/registry.py` metadata table + page-side UI tables | `strategies/<slug>/meta.py` (one entry each; discovery merges them) |
| per-strategy scorers in `engine/screener.py` | `strategies/<slug>/screener.py` (+ its own `DEFAULT_PARAMS`) |
| per-slug branches in the Strategies page (`scan`, `columns`, `display_rows`, `modals`, `layout`, `backtest_view`, `callbacks`, `data_fetch`, `backtest_loaders`) | `strategies/<slug>/ui.py` (`class UI(StrategyUI)`) |
| `saved_models/*.pkl, *.pt` | `strategies/<slug>/models/` |
| strategy tests, including the multi-strategy files split by owner | `strategies/<slug>/tests/` |
| guide articles named after a registered slug, and the charts that serve them | `strategies/<slug>/guide.md`, `charts.py` |
| `strategy_articles.py` | `strategies/<slug>/playbook.md` (generic option-structure playbooks → `app/guide_articles/playbooks/`) |
| strategy-specific scripts and sample data | `strategies/<slug>/scripts/`, `data/` |
| `docs/strategy_scope.md`, strategy reviews, rankings | plugin `docs/` |

The platform kept: `strategy_api/` (the contract), the generic Strategies
page, loaders keyed by data type, generic screener + spread-builder helpers in
`engine/screener.py`, the design-system widgets strategies build on
(`app/ui/strategy_widgets.py`, `app/ui/timing_ui.py`), 14 general education
articles, and the harness scripts (`rank_strategies`, `check_screeners`,
`check_end_to_end`) driven by the registry. Runtime state moved from
`saved_models/` to `runtime_state/`.

## The contract (`alan_trader.strategy_api`)

- `StrategyPlugin(name, metadata, root, model_dir, docs_dir, guide_dir, guide_charts, tests_dir)` — what a plugin publishes.
- Discovery in `registry.load()`: entry points in group `alan_trader.strategies`, then packages in `ALAN_TRADER_STRATEGY_PACKAGES`, then the default `alan_trader_strategies`; `none` disables all. Duplicate slugs raise; a broken plugin is logged and skipped.
- `BaseStrategy` gained one headless hook, `current_signal(close)`, which the signal monitor uses instead of importing named strategies.
- `StrategyUI` replaces every per-slug branch the page had: `locked_tickers`, `screener_params`, `default_params`, `columns`, `scan()`, `display_row()`, `vix_banner_status()`, `modal_title()`, `signal_body()`, `can_paper_trade()`, `trade_details()`, `paper_trade()`, `extra_tabs()`, `register_callbacks()`, `backtest_panels()`, `loaders()`, `prepare_aux()`, `has_signal_alert`, `test_suites`.
- Metadata keys read by the platform: `ui`, `ui_visible`, `ui_order`, `ui_label`, `review_status`, `score`, `loaders`, `test_suites`, `rank_window`, `guide_path`, `guide_chart`, `tests_dir`, `model_dir`.

## Where shared code went

Strategies used to share column sets, row formatters, the iron-condor chain
lookup, the HMM trade preview, a timing-overlay UI base and a subclass
relationship (`iron_condor_ai` ← `iron_condor_rules` UI,
`stock_bond_vol_rotation` ← `vrp_premium`). Genuinely generic pieces were
hoisted into the platform (scan loops, modal assembly, payoff figures,
`fetch_iron_condor_strikes` / `fetch_put_spread_strikes`, `TimingUI`).
Strategy-flavoured pieces were duplicated into each folder that used them
(`iron_condor_ai` carries a private copy of the rules UI and scorer,
`stock_bond_vol_rotation` a private copy of the VRP base and scorer, the
calendar / VRP column sets, the HMM preview). Each copy is annotated as such.

## Behaviour changes worth knowing

- One detail modal serves every strategy (the separate iron-condor modal is gone; same content).
- Every visible strategy's screener rows are clickable; strategies without a bespoke body get a generic metrics view. Previously several strategies fell into the GEX branch by accident.
- `earnings_vol_crush` and `momentum_regime_spread` screeners are wired (their scorers existed but were never dispatched).
- `insert_open_ic_trade` no longer defaults `strategy_name`; callers pass it.
- `check_end_to_end` skips the payoff surface for strategies that declare no bespoke popup instead of failing it.

## Known follow-ups

- The three `earnings_pin_risk_*.pkl` artifacts embed the old module path `strategies.earnings_pin_risk`; they still unpickle today, but retrain them with the plugin's `scripts/retrain_models.py` before relying on them.
- The platform's own dual import root (`app.*` vs `alan_trader.*`) is unchanged; plugins use `alan_trader.*`.
- The LSTM options-spread pipeline (`main.py`, `model/`, `trading/`, `live/`) is platform ML infrastructure and was left in place.
