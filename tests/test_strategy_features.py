"""
Every user-visible feature of a wired strategy must actually be implemented.

The Performance tab shipped for months as an enabled, clickable tab rendering
only "Performance analytics coming soon." — indistinguishable, to a user, from a
feature that was working but had nothing to show. These tests assert that each
tab a strategy exposes builds real content, and that the analytics agree with
the ranking harness rather than being a second, divergent implementation.

The page is generic, so every strategy-parametrised test runs over whatever
the installed plugins expose (and skips when nothing is installed).
"""

import pandas as pd
import pytest
from dash import dcc
from dash.development.base_component import Component

import importlib

from alan_trader.app.pages.strategies import performance as P
from alan_trader.app.pages.strategies.registry import slugs as _slugs

# `app.pages.strategies.__init__` re-exports the `layout` FUNCTION, which
# shadows the `layout` MODULE on the package. Import the module explicitly.
L = importlib.import_module("alan_trader.app.pages.strategies.layout")

ALL_SLUGS = _slugs()
_PARAM_SLUGS = ALL_SLUGS or [pytest.param("__none__", marks=pytest.mark.skip(
    reason="no strategy plugin installed"))]


def _walk(node):
    if isinstance(node, (list, tuple)):
        for n in node:
            yield from _walk(n)
    elif isinstance(node, Component):
        yield node
        yield from _walk(getattr(node, "children", None))


def _text_of(node) -> str:
    out = []
    for n in _walk(node):
        ch = getattr(n, "children", None)
        if isinstance(ch, str):
            out.append(ch)
    return " ".join(out)


def _ids(node) -> set:
    return {i for i in (getattr(n, "id", None) for n in _walk(node)) if i}


def _graphs(node) -> int:
    return sum(1 for n in _walk(node) if isinstance(n, dcc.Graph))


# ── the placeholder must be gone ──────────────────────────────────────────────

@pytest.mark.parametrize("slug", _PARAM_SLUGS)
def test_performance_tab_is_not_a_placeholder(slug):
    text = _text_of(L._performance_tab(slug)).lower()
    for phrase in ("coming soon", "not implemented", "todo", "placeholder"):
        assert phrase not in text, f"{slug}: Performance tab still says {phrase!r}"


@pytest.mark.parametrize("slug", _PARAM_SLUGS)
def test_performance_tab_exposes_its_controls(slug):
    ids = _ids(L._performance_tab(slug))
    for suffix in ("perf-ticker", "perf-from", "perf-to", "perf-capital",
                   "perf-run", "perf-output"):
        assert f"str-{slug}-{suffix}" in ids, f"{slug}: missing {suffix}"


def test_every_strategy_has_a_performance_callback():
    if not ALL_SLUGS:
        pytest.skip("no strategy plugin installed")
    from dash._callback import GLOBAL_CALLBACK_MAP

    for slug in ALL_SLUGS:
        assert f"str-{slug}-perf-output.children" in GLOBAL_CALLBACK_MAP, (
            f"{slug}: Performance tab has controls but no callback — the button "
            f"would do nothing"
        )


# ── tab inventory ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("slug", _PARAM_SLUGS)
def test_core_tabs_build_for_every_strategy(slug):
    """Screener / Backtest / Performance / Guide exist for every strategy."""
    tabs = L._inner_tabs(slug)
    labels = {t.label for t in tabs.children}
    assert {"Screener", "Backtest", "Performance", "Guide"} <= labels, (
        f"{slug} is missing a core tab; has {sorted(labels)}"
    )


@pytest.mark.parametrize("slug", _PARAM_SLUGS)
def test_plugin_extra_tabs_are_wired(slug):
    """Whatever extra tabs the plugin declares must appear on the page."""
    from alan_trader.strategy_api.registry import get_ui
    labels = {t.label for t in L._inner_tabs(slug).children}
    for spec in get_ui(slug).extra_tabs():
        assert spec.label in labels, f"{slug}: declared tab {spec.label!r} not rendered"
    if get_ui(slug).has_signal_alert:
        assert "Signal & Alert" in labels


def test_unimplemented_tabs_are_disabled_not_silently_empty():
    """
    The Simulator is genuinely unbuilt. That is fine — but it must be visibly
    disabled rather than presenting as a working, empty tab.
    """
    if not ALL_SLUGS:
        pytest.skip("no strategy plugin installed")
    for tab in L._inner_tabs(ALL_SLUGS[0]).children:
        if tab.label == "Simulator":
            assert getattr(tab, "disabled", False) is True
            return
    pytest.fail("Simulator tab not found")


# ── analytics helpers ─────────────────────────────────────────────────────────

def _equity(values, start="2021-01-04"):
    idx = pd.bdate_range(start, periods=len(values))
    return pd.Series(values, index=idx, dtype=float)


def test_drawdown_is_zero_at_a_new_high_and_negative_below():
    eq = _equity([100.0, 110.0, 99.0, 120.0])
    dd = P._drawdown(eq)
    assert dd.iloc[0] == pytest.approx(0.0)
    assert dd.iloc[1] == pytest.approx(0.0)
    assert dd.iloc[2] == pytest.approx(-10.0, abs=0.01)
    assert dd.iloc[3] == pytest.approx(0.0)


def test_yearly_returns_split_by_calendar_year():
    idx = pd.bdate_range("2021-01-04", "2022-12-30")
    eq = pd.Series(100.0, index=idx)
    eq.loc[eq.index[eq.index.year == 2021]] = 110.0
    eq.iloc[0] = 100.0
    ys = P._yearly_returns(eq)
    assert len(ys) == 2
    assert list(ys.index.year) == [2021, 2022]


# ── the honesty panel ─────────────────────────────────────────────────────────

def _perf(metrics, coverage=1.0, span=1000, window=1000):
    return {"metrics": metrics, "coverage": coverage,
            "span_days": span, "window_days": window}


def test_small_sample_is_flagged():
    txt = _text_of(P._warnings_panel(_perf({"num_trades": 2}))).lower()
    assert "statistically meaningful" in txt or "too few" in txt


def test_partial_window_is_flagged():
    panel = P._warnings_panel(_perf({"num_trades": 100}, coverage=0.19,
                                    span=190, window=1000))
    assert "annualizes" in _text_of(panel).lower()


def test_infinite_profit_factor_is_flagged():
    txt = _text_of(P._warnings_panel(
        _perf({"num_trades": 47, "profit_factor": float("inf")}))).lower()
    assert "no losing trades" in txt


def test_zero_drawdown_is_flagged_as_missing_mark_to_market():
    txt = _text_of(P._warnings_panel(
        _perf({"num_trades": 47, "max_drawdown_pct": 0.0}))).lower()
    assert "marked to market" in txt


def test_healthy_result_raises_no_warnings():
    assert P._warnings_panel(_perf({
        "num_trades": 300, "profit_factor": 1.8, "max_drawdown_pct": -12.0,
    })) is None
