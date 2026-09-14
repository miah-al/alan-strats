"""
tests/test_strategies_page_smoke.py

Smoke tests for the Strategies page. The page is generic — every strategy it
shows comes from an installed plugin — so these tests are written against the
registry, never against a named strategy.

Goals:
  1. The page package imports cleanly (catches syntax errors and broken imports).
  2. `layout()` returns a Dash html.Div without crashing.
  3. Every visible strategy resolves to a real (non-stub) implementation.
  4. Every active registry entry has a class_path.

Run:  python -m pytest tests/test_strategies_page_smoke.py -v
"""
from __future__ import annotations

import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _visible_slugs() -> list[str]:
    from alan_trader.strategy_api.registry import ui_slugs
    return ui_slugs()


# ── Module import ────────────────────────────────────────────────────────────

def test_module_imports():
    """The strategies page imports without raising — catches syntax errors and
    broken imports introduced by refactors."""
    mod = importlib.import_module("app.pages.strategies")
    assert mod is not None


# ── Layout ───────────────────────────────────────────────────────────────────

def test_layout_returns_div():
    """layout() returns a Dash html.Div (or function-callable that returns one)
    without crashing on call."""
    from app.pages import strategies as page
    from dash import html

    layout = getattr(page, "layout", None)
    assert layout is not None, "strategies module must expose `layout`"

    rendered = layout() if callable(layout) else layout
    assert isinstance(rendered, html.Div), \
        f"layout must render to html.Div; got {type(rendered).__name__}"


def test_inner_tabs_build_for_every_visible_strategy():
    """Screener / Backtest / Performance / Guide build for every strategy a
    plugin exposes, plus whatever extra tabs the plugin declares."""
    slugs = _visible_slugs()
    if not slugs:
        pytest.skip("no strategy plugin installed")
    L = importlib.import_module("app.pages.strategies.layout")
    for slug in slugs:
        labels = {t.label for t in L._inner_tabs(slug).children}
        from alan_trader.strategy_api.registry import get_ui
        core = {"Backtest", "Performance", "Guide"} | ({"Screener"} if get_ui(slug).meta.get("has_screener", True) else set())
        assert core <= labels, (
            f"{slug} is missing a core tab; has {sorted(labels)}")


# ── Registry consistency ─────────────────────────────────────────────────────

def test_every_visible_slug_resolves_to_a_real_strategy():
    """A visible strategy that resolves to StubStrategy cannot backtest."""
    from alan_trader.strategy_api.base import StubStrategy
    from alan_trader.strategy_api.registry import get_strategy

    slugs = _visible_slugs()
    if not slugs:
        pytest.skip("no strategy plugin installed")
    stubs = [s for s in slugs if isinstance(get_strategy(s), StubStrategy)]
    assert not stubs, (
        "These visible strategies resolve to a stub (silently break the Backtest tab):\n  "
        + "\n  ".join(stubs))


def test_every_active_registry_strategy_has_class_path():
    """Every status='active' strategy must have a populated class_path. Active
    strategies without class_path silently fall back to StubStrategy."""
    from alan_trader.strategy_api.registry import STRATEGY_METADATA

    missing = [
        slug for slug, meta in STRATEGY_METADATA.items()
        if meta.get("status") == "active" and not meta.get("class_path")
    ]
    assert not missing, (
        "These active strategies have no class_path (silently stub):\n  "
        + "\n  ".join(missing)
    )
