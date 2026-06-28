"""
app/pages/strategies/ — Strategies page (package).

Split from the original ~5,000-line module into focused modules, matching the
market/ and tools/ page convention:
  registry.py      — strategy lists, universes, slug-sets, screener param specs
  columns.py       — grid column defs
  format.py        — numeric formatters, VIX banner, status pills, guide loader
  display_rows.py  — per-strategy grid row formatters
  data_fetch.py    — shared fetch / option-chain / payoff / trade-preview helpers
  scan.py          — screener scan engine + scan callbacks
  backtest_view.py — backtest run callbacks + result rendering
  modals.py        — signal / IC payoff modals + paper-trade callbacks
  layout.py        — page layout + per-strategy tab builders (pure view)
  callbacks.py     — layout-driving callbacks (outer tabs, selection merge, etc.)

Public surface is unchanged: `from app.pages.strategies import layout`.
Importing this package registers every callback via the side-effect imports below.
"""
from app.pages.strategies.layout import layout        # noqa: F401  (public API)
from app.pages.strategies import (                     # noqa: F401  (register callbacks)
    scan, backtest_view, modals, callbacks,
)

# ── Backward-compatible public surface ───────────────────────────────────────
# External code/tests import these names from the package root (see
# tests/test_strategies_page_smoke.py and test_ic_rules_integration.py). The
# implementations now live in submodules; keep the root names stable.
from app.pages.strategies.registry import _STRATEGIES               # noqa: F401
from app.pages.strategies.backtest_view import _STRATEGY_CLASSES_BT  # noqa: F401
from app.pages.strategies.data_fetch import _fetch_ic_strikes        # noqa: F401

__all__ = ["layout"]
