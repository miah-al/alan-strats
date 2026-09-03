"""
StrategyUI — the optional presentation hooks a strategy plugin can implement.

The Strategies page is generic: it renders a screener grid, a backtest tab, a
performance tab and a guide for every visible strategy, and opens a detail
modal when a screener row is clicked. Everything that used to be a
``if slug == "..."`` branch in the platform is now a method on this class,
with a default that produces sensible generic behaviour.

A plugin points a strategy at its UI class via metadata::

    "ui": "my_plugin.ui.my_strategy"     # module exposing ``class UI(StrategyUI)``

Metadata keys the platform reads (all optional):

    ui_visible     bool         list the strategy on the Strategies page
    ui_label       str          selector label (falls back to display_name)
    review_status  str          ready | reviewed | reviewing | avoid
    score          (int, str)   credibility score + letter grade
    loaders        list         auxiliary-data loaders for backtests; each item
                                is a loader name or ``(name, options)``; the
                                platform's ``app.pages.backtest_loaders`` lists
                                the names it understands
    guide_path     str/Path     the strategy's own guide article (markdown)
    guide_chart    str          module exposing ``render_charts()`` for the guide
    tests_dir      str/Path     directory holding the strategy's pytest files
                                (``test_suites`` modules are resolved there)

This module is headless: it imports no Dash. Hooks that return components
return whatever the caller renders (Dash components in the app).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd


@dataclass
class ScanContext:
    """Everything a screener scan gets from the platform."""
    slug: str
    tickers: list[str]
    price_dfs: dict[str, pd.DataFrame]     # ticker -> OHLCV (date-indexed)
    vix_series: pd.Series                  # VIX closes
    iv_all: dict[str, dict]                # ticker -> IV metrics dict
    api_key: str
    params: dict = field(default_factory=dict)

    def iv(self, ticker: str) -> dict:
        return self.iv_all.get(ticker, {}) or {}


@dataclass
class TabSpec:
    """An extra per-strategy tab (e.g. a model-inspection tab)."""
    label: str
    content: Any
    tab_id: str
    accent: Optional[str] = None


@dataclass
class PaperTradeResult:
    ok: bool
    message: str


class StrategyUI:
    """
    Base UI hooks. Subclass in a plugin and override what the strategy needs;
    every default is safe and generic.
    """

    # ── Screener configuration ────────────────────────────────────────────────
    #: Fixed ticker list when the screener must not scan an arbitrary universe.
    locked_tickers: Optional[list[str]] = None
    #: Badge text shown instead of the universe selector when locked.
    locked_label: str = ""
    #: Filter-panel spec: [{"id","label","min","max","step","default","fmt"}, ...]
    screener_params: list[dict] = []
    #: Default scoring params merged under the user's filter overrides.
    default_params: dict = {}
    #: Grid column definitions (see ``app.ui.strategy_widgets.col``); None → generic.
    columns: Optional[list[dict]] = None
    #: Which modal a row click opens: "signal" (default) or None (rows inert).
    modal: Optional[str] = "signal"
    #: "options" → generic multi-leg paper trade; "equity" → buy shares.
    trade_kind: str = "options"
    #: Credit strategies are blocked when the net credit is below the floor.
    is_credit: bool = False
    #: Show the Signal & Alert tab (requires BaseStrategy.current_signal()).
    has_signal_alert: bool = False
    #: Test tab suites: [{"id","label","module"}] — module is a test file stem
    #: under the plugin's ``tests_dir``.
    test_suites: list[dict] = []

    def __init__(self, slug: str, meta: dict):
        self.slug = slug
        self.meta = meta or {}
        self.label = self.meta.get("ui_label") or self.meta.get("display_name") or slug
        # Test suites may be declared in metadata instead of on the class.
        if not type(self).test_suites and self.meta.get("test_suites"):
            self.test_suites = list(self.meta["test_suites"])

    # ── Screener ──────────────────────────────────────────────────────────────
    def info_banner(self) -> Any:
        """Optional component rendered above the screener controls."""
        return None

    def scan(self, ctx: ScanContext) -> list[dict]:
        """Return raw rows for the universe. Each row should carry at least
        ``Ticker``, ``Price``, ``score`` (sort key), ``all_pass`` and ``n_pass``."""
        return []

    def display_row(self, raw: dict) -> dict:
        """Map a raw scan row to grid columns. The default passes the scorer's
        fields through, adds the sort key and status-pill keys, and never errors
        on a missing column."""
        out = dict(raw)
        score = raw.get("Score", raw.get("score", 0))
        try:
            score_f = float(score)
        except (TypeError, ValueError):
            score_f = 0.0
        out["Score"] = score if "Score" in raw else round(score_f, 1)
        out["score"] = score_f
        if isinstance(out.get("Price"), (int, float)):
            out["Price"] = round(float(out["Price"]), 2)
        if "all_pass" not in out:
            status = str(raw.get("Status", "")).lower()
            ok = score_f >= 60 and not any(
                w in status for w in ("skip", "no data", "too low", "too high", "flat", "—"))
            out["all_pass"] = ok
            out["n_pass"] = raw.get("n_pass", 1 if ok else 0)
        out.setdefault("Status", "Trade-Ready" if out.get("all_pass") else
                       ("Partial" if out.get("n_pass", 0) > 0 else "Blocked"))
        return out

    def vix_banner_status(self, vix: float, vix_20d_avg: float) -> Optional[tuple[str, str]]:
        """(text, tone) for the VIX banner; tone is success|warning|danger|muted."""
        return None

    # ── Detail modal ──────────────────────────────────────────────────────────
    def modal_title(self, row: dict) -> str:
        ticker = row.get("Ticker", "")
        score = row.get("Score", "")
        return f"{ticker}  ·  {self.label}  ·  Score {score}"

    def signal_body(self, row: dict) -> Any:
        """Component for the modal body; None → the platform's generic body."""
        return None

    def can_paper_trade(self, row: dict) -> bool:
        return True

    def trade_details(self, row: dict) -> dict:
        """Extra fields merged into the generic paper-trade record."""
        return {}

    def paper_trade(self, row: dict, contracts: int, label: str) -> Optional[PaperTradeResult]:
        """Fully custom paper-trade path. Return None to use the generic path."""
        return None

    # ── Tabs / callbacks ──────────────────────────────────────────────────────
    def extra_tabs(self) -> list[TabSpec]:
        return []

    def register_callbacks(self) -> None:
        """Called once at page import so the plugin can register Dash callbacks
        for its extra tabs."""
        return None

    # ── Backtest ──────────────────────────────────────────────────────────────
    def backtest_panels(self, result: Any) -> list:
        """Extra components rendered under the equity curve."""
        return []

    def loaders(self) -> list:
        """Auxiliary-data loader specs for the Backtest / Performance tabs."""
        return list(self.meta.get("loaders", []) or [])

    def prepare_aux(self, aux: dict, ticker: str, price_data: Any) -> dict:
        """Last-chance reshaping of auxiliary_data before backtest()."""
        return aux
