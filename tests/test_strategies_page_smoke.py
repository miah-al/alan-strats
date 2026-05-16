"""
tests/test_strategies_page_smoke.py

Smoke tests for dash_app/pages/strategies.py — the giant Dash callback module
(~4,800 lines). The page has no functional test coverage today; these tests
gate any future refactor of the file.

Goals:
  1. The module imports cleanly (catches syntax errors and broken `from ... import`).
  2. `layout()` returns a Dash html.Div without crashing.
  3. Every slug in the user-facing _STRATEGIES list has a backtest-class entry.
  4. Every backtest-class entry resolves to an importable class.
  5. Every active strategy in the registry that has a class_path resolves.

Run:  python -m pytest tests/test_strategies_page_smoke.py -v
"""
from __future__ import annotations

import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── Module import ────────────────────────────────────────────────────────────

def test_module_imports():
    """The strategies page imports without raising — catches syntax errors and
    broken imports introduced by refactors."""
    mod = importlib.import_module("dash_app.pages.strategies")
    assert mod is not None


# ── Layout ───────────────────────────────────────────────────────────────────

def test_layout_returns_div():
    """layout() returns a Dash html.Div (or function-callable that returns one)
    without crashing on call."""
    from dash_app.pages import strategies as page
    from dash import html

    layout = getattr(page, "layout", None)
    assert layout is not None, "strategies module must expose `layout`"

    rendered = layout() if callable(layout) else layout
    assert isinstance(rendered, html.Div), \
        f"layout must render to html.Div; got {type(rendered).__name__}"


# ── Slug registry consistency ────────────────────────────────────────────────

def test_every_user_visible_slug_has_backtest_class():
    """Every entry in the user-facing _STRATEGIES dropdown must have a backtest
    class wired in `_STRATEGY_CLASSES_BT`. Missing entries silently break the
    Backtest tab for that strategy."""
    from dash_app.pages import strategies as page

    slugs    = [s["value"] for s in page._STRATEGIES]
    bt_map   = page._STRATEGY_CLASSES_BT
    missing  = [s for s in slugs if s not in bt_map]
    assert not missing, (
        "These user-visible slugs lack a backtest-class entry "
        "(silently break the Backtest tab):\n  " + "\n  ".join(missing)
    )


def test_every_backtest_class_resolves():
    """Every (module, class) pair in _STRATEGY_CLASSES_BT must import and
    resolve to an instantiable class. Catches stale class paths after renames."""
    from dash_app.pages import strategies as page

    failures: list[str] = []
    for slug, (mod_path, cls_name) in page._STRATEGY_CLASSES_BT.items():
        try:
            mod = importlib.import_module(mod_path)
            cls = getattr(mod, cls_name, None)
            if cls is None:
                failures.append(f"{slug}: {mod_path}.{cls_name} not found")
            elif not isinstance(cls, type):
                failures.append(f"{slug}: {mod_path}.{cls_name} is not a class")
        except Exception as e:
            failures.append(f"{slug}: import failed — {type(e).__name__}: {e}")

    assert not failures, (
        "These backtest classes failed to resolve:\n  " + "\n  ".join(failures)
    )


def test_every_active_registry_strategy_has_class_path():
    """Every status='active' strategy in strategies/registry.py must have a
    populated class_path. Active strategies without class_path silently fall
    back to the StubStrategy stub at runtime."""
    from strategies.registry import STRATEGY_METADATA

    missing = [
        slug for slug, meta in STRATEGY_METADATA.items()
        if meta.get("status") == "active" and not meta.get("class_path")
    ]
    assert not missing, (
        "These active strategies have no class_path (silently stub):\n  "
        + "\n  ".join(missing)
    )


# ── Hidden re-export contract ────────────────────────────────────────────────

def test_fetch_ic_strikes_is_exported():
    """tests/test_ic_rules_integration.py imports _fetch_ic_strikes from this
    module. Refactors must keep that re-export alive."""
    from dash_app.pages.strategies import _fetch_ic_strikes
    assert callable(_fetch_ic_strikes)
