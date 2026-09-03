"""
app/pages/strategies/ — Strategies page (package).

A generic page: every strategy it shows comes from an installed strategy
plugin (see alan_trader.strategy_api). Modules:
  registry.py      — selector lists, review palette, universes (from the registry)
  format.py        — VIX banner, status pills, guide loader
  data_fetch.py    — shared price / VIX / IV fetch
  scan.py          — screener scan engine + scan callbacks
  backtest_view.py — backtest run callbacks + result rendering
  modals.py        — row-click detail modal + paper-trade callbacks
  performance.py   — performance tab
  layout.py        — page layout + per-strategy tab builders (pure view)
  callbacks.py     — layout-driving callbacks (outer tabs, tests, alerts)

Public surface: `from app.pages.strategies import layout`.
Importing this package registers every callback via the side-effect imports
below, then gives each strategy's UI hook a chance to register its own.
"""
import logging as _logging

from app.pages.strategies.layout import layout        # noqa: F401  (public API)
from app.pages.strategies import (                     # noqa: F401  (register callbacks)
    scan, backtest_view, modals, callbacks, performance,
)
from app.pages.strategies.registry import _STRATEGIES, slugs as _slugs  # noqa: F401

# Performance-tab callbacks are per-slug, so they are registered explicitly
# rather than by import side effect alone.
performance.register_performance_callbacks(_slugs())

# Plugin-provided callbacks (extra tabs, model panels, ...).
from alan_trader.strategy_api.registry import get_ui as _get_ui

for _slug in _slugs():
    try:
        _get_ui(_slug).register_callbacks()
    except Exception as _exc:  # a broken plugin must not take the page down
        _logging.getLogger(__name__).warning(
            "register_callbacks failed for %s: %s", _slug, _exc)

__all__ = ["layout"]
