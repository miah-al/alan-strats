"""
The platform is strategy-free: everything about a strategy arrives through
`alan_trader.strategy_api`. These tests pin the plugin contract and the
"no strategy named anywhere in the platform" invariant.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:      # only the checkout: its parent holds the live alan_trader (conftest binds ours by path)
    sys.path.insert(0, str(REPO))

from alan_trader.strategy_api import registry as R
from alan_trader.strategy_api.base import BaseStrategy, StubStrategy, SignalResult, BacktestResult
from alan_trader.strategy_api.plugin import StrategyPlugin
from alan_trader.strategy_api.ui import StrategyUI, ScanContext


# ── a throwaway plugin ────────────────────────────────────────────────────────

class _Toy(BaseStrategy):
    name = "toy_probe"
    display_name = "Toy Probe"
    status = BaseStrategy.status.__class__("active")

    def generate_signal(self, market_snapshot):
        return SignalResult(self.name, "HOLD", 0.0, 0.0)

    def backtest(self, price_data, auxiliary_data, starting_capital=100_000, **kw):
        eq = pd.Series([starting_capital] * 3, index=pd.bdate_range("2024-01-01", periods=3))
        return BacktestResult(self.name, eq, eq.pct_change().fillna(0), pd.DataFrame(), {})

    def get_params(self):
        return {}

    def current_signal(self, close):
        return {"signal": "HOLD", "state": "cash", "price": 1.0, "asof": "2024-01-01",
                "detail": "probe"}


def _toy_plugin(name="toy", slug="toy_probe", **extra_meta):
    meta = {
        slug: {
            "display_name": "Toy Probe", "type": "rule", "status": "active",
            "class_path": f"{__name__}._Toy", "ui_visible": True, "ui_order": -1,
            "loaders": ["macro", ("sector_etfs", {"tickers": ["XLK"]})],
            "guide_path": str(REPO / "README.md"),
            **extra_meta,
        }
    }
    return StrategyPlugin(name=name, metadata=meta, guide_dir=REPO / "tests",
                          docs_dir=REPO / "docs")


@pytest.fixture
def toy_registry():
    before = list(R.plugins())
    R.register_plugin(_toy_plugin())
    try:
        yield
    finally:
        R._install(before)


# ── discovery / factories ─────────────────────────────────────────────────────

def test_registered_plugin_shows_up_in_the_merged_table(toy_registry):
    assert "toy_probe" in R.STRATEGY_METADATA
    assert R.plugin_for("toy_probe").name == "toy"
    strat = R.get_strategy("toy_probe")
    assert isinstance(strat, _Toy)
    assert not isinstance(strat, StubStrategy)
    assert "toy_probe" in R.ui_slugs()
    assert R.ui_entries()[0]["value"] == "toy_probe"     # ui_order -1 sorts first


def test_unknown_slug_raises_and_missing_class_degrades_to_stub(toy_registry):
    with pytest.raises(KeyError):
        R.get_strategy("definitely_not_registered")
    R.register_plugin(_toy_plugin(name="toy2", slug="toy_broken",
                                  class_path="no.such.module.Klass"))
    assert isinstance(R.get_strategy("toy_broken"), StubStrategy)


def test_two_plugins_may_not_claim_the_same_slug(toy_registry):
    with pytest.raises(ValueError):
        R.register_plugin(_toy_plugin(name="imposter"))


def test_get_ui_falls_back_to_the_generic_hooks(toy_registry):
    ui = R.get_ui("toy_probe")
    assert isinstance(ui, StrategyUI)
    assert ui.label == "Toy Probe"
    assert ui.scan(ScanContext("toy_probe", [], {}, pd.Series(dtype=float), {}, "")) == []
    assert ui.loaders() == ["macro", ("sector_etfs", {"tickers": ["XLK"]})]
    assert ui.signal_body({"Ticker": "SPY"}) is None
    assert ui.paper_trade({}, 1, "x") is None


def test_guide_lookup_honours_a_strategys_own_guide_path(toy_registry):
    """A strategy folder may carry its own article; the page must find it
    through the registry, not only through plugin-level guide directories."""
    from app.guides import find_guide, load_guide, all_guide_slugs
    assert find_guide("toy_probe") == REPO / "README.md"
    assert "toy_probe" in all_guide_slugs()
    assert len(load_guide("toy_probe")) > 100


def test_get_ui_survives_a_broken_ui_module(toy_registry):
    R.register_plugin(_toy_plugin(name="toy3", slug="toy_bad_ui",
                                  ui="no.such.ui.module"))
    assert isinstance(R.get_ui("toy_bad_ui"), StrategyUI)


def test_generic_display_row_never_errors_on_sparse_rows():
    ui = StrategyUI("x", {})
    row = ui.display_row({"Ticker": "SPY", "Score": 72, "Status": "ENTER"})
    assert row["score"] == 72.0 and row["all_pass"] is True
    row = ui.display_row({"Ticker": "SPY"})
    assert row["Status"] == "Blocked" and row["score"] == 0.0


def test_loader_specs_parse_both_shapes():
    from app.pages.backtest_loaders import parse_loader_spec, LOADERS
    assert parse_loader_spec("macro") == ("macro", {})
    assert parse_loader_spec(("sector_etfs", {"tickers": ["XLK"]})) == ("sector_etfs", {"tickers": ["XLK"]})
    assert {"option_snapshots", "sector_etfs", "earnings_calendar", "macro"} <= set(LOADERS)


def test_signal_monitor_picks_up_strategies_that_publish_a_signal(toy_registry, monkeypatch):
    from engine import signal_alerts as SA
    monitored = SA._monitored()
    assert "toy_probe" in monitored
    monkeypatch.setattr("alan_trader.strategy_api.timing_base.load_close",
                        lambda t, n_days=7500: pd.Series([1.0, 2.0]))
    out = SA.compute_signals(["SPY"])
    assert out["toy_probe|SPY"]["signal"] == "HOLD"
    assert "probe" in SA.format_signal_line(out["toy_probe|SPY"])


# ── the strategy-free invariant ───────────────────────────────────────────────

_PLATFORM_DIRS = ["app", "engine", "portfolio", "live", "scripts", "strategy_api",
                  "db", "data", "risk", "backtest", "model", "trading", "analytics"]


def test_platform_source_never_names_an_installed_strategy():
    """With plugins installed, no platform module may mention a strategy slug
    as a string literal — that is the whole point of the carve-out."""
    slugs = [s for s in R.STRATEGY_METADATA if not s.startswith("toy_")]
    if not slugs:
        pytest.skip("no strategy plugin installed")
    pat = re.compile(r"""["'](%s)["']""" % "|".join(map(re.escape, slugs)))
    hits = []
    for d in _PLATFORM_DIRS:
        for p in (REPO / d).rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if pat.search(line):
                    hits.append(f"{p.relative_to(REPO)}:{i}: {line.strip()[:90]}")
    assert not hits, "platform code names a strategy:\n  " + "\n  ".join(hits)


def test_platform_never_imports_the_strategy_package():
    hits = []
    for d in _PLATFORM_DIRS:
        for p in (REPO / d).rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            src = p.read_text(encoding="utf-8", errors="replace")
            if re.search(r"^\s*(from|import)\s+alan_trader_strategies", src, re.M):
                hits.append(str(p.relative_to(REPO)))
    assert not hits, f"platform imports the strategy package: {hits}"


def test_page_builds_with_zero_plugins():
    """The strategy-free configuration must still start: the page renders a
    notice instead of crashing when no plugin is discoverable."""
    code = (
        "import os, sys\n"
        "sys.path.insert(0, %r)\n"
        # this checkout is alan_trader by path: with the parent on sys.path the live checkout next door would be tested
        "from api.bootstrap import register_platform_package; register_platform_package()\n"
        "os.environ['ALAN_TRADER_STRATEGY_PACKAGES'] = 'none'\n"
        "from alan_trader.strategy_api import registry as R\n"
        "assert R.STRATEGY_METADATA == {}, R.STRATEGY_METADATA\n"
        "from app.pages import strategies as page\n"
        "from dash import html\n"
        "assert isinstance(page.layout(), html.Div)\n"
        "from app.pages.tools.tabs import _registry_tab\n"
        "_registry_tab()\n"
        "print('OK')\n"
    ) % str(REPO)
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                          cwd=str(REPO), timeout=300)
    assert proc.returncode == 0 and "OK" in proc.stdout, proc.stderr[-2000:]
