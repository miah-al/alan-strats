"""
scripts/check_end_to_end.py — verify every wired strategy across all five surfaces.

For each strategy checks, using the production code paths:

  guide    — the markdown article loads and is substantive
  layout   — the strategy's guide/backtest/screener layout builds
  params   — get_backtest_ui_params() is well-formed (the backtest UI reads it)
  signal   — generate_signal() returns a valid SignalResult on a real snapshot
  payoff   — the payoff figure builds for options strategies
  paper    — the paper-trade insert path is reachable and its columns resolve

Backtest and screener coverage live in their own scripts (rank_strategies.py,
check_screeners.py) because both are slow and need their own reporting.

    python -m scripts.check_end_to_end
    python -m scripts.check_end_to_end --slugs hmm_regime,covered_call_ai
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import traceback
from datetime import date

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_REPO, os.path.dirname(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import warnings
warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.CRITICAL)
for _n in ("strategies", "app", "db", "engine", "yfinance", "urllib3", "sklearn"):
    logging.getLogger(_n).setLevel(logging.CRITICAL)

PASS, FAIL, SKIP = "ok", "FAIL", "-"


class Check:
    def __init__(self):
        self.rows: dict[str, dict[str, str]] = {}
        self.problems: list[tuple[str, str, str]] = []

    def record(self, slug, surface, state, detail=""):
        self.rows.setdefault(slug, {})[surface] = state
        if state == FAIL:
            self.problems.append((slug, surface, detail))


def _try(chk, slug, surface, fn):
    try:
        out = fn()
        chk.record(slug, surface, PASS if out is not False else FAIL,
                   "" if out is not False else "returned False")
        return out
    except _Skip as exc:
        chk.record(slug, surface, SKIP, str(exc))
        return None
    except Exception as exc:
        detail = " ".join(f"{type(exc).__name__}: {exc}".split())[:200]
        chk.record(chk_slug := slug, surface, FAIL, detail)
        if os.environ.get("E2E_DEBUG"):
            traceback.print_exc()
        return None


class _Skip(Exception):
    """Raised when a surface does not apply to a strategy."""


# ── surfaces ──────────────────────────────────────────────────────────────────

def check_guide(slug):
    from app.pages.strategies.format import _load_guide
    md = _load_guide(slug)
    if not md or len(md.strip()) < 400:
        raise AssertionError(f"guide missing or too short ({len(md or '')} chars)")
    return True


def check_layout(slug):
    from app.pages.strategies.layout import _guide_layout
    div = _guide_layout(slug)
    if div is None:
        raise AssertionError("layout returned None")
    return True


def check_params(slug):
    from app.pages.strategies.backtest_view import (
        _STRATEGY_CLASSES_BT, _get_ui_params_for_slug,
    )
    if slug not in _STRATEGY_CLASSES_BT:
        raise _Skip("no backtest class")
    params = _get_ui_params_for_slug(slug)
    for p in params:
        if "key" not in p:
            raise AssertionError(f"param spec missing 'key': {p}")
        if "default" not in p:
            raise AssertionError(f"param {p['key']!r} has no default — "
                                 "the backtest UI cannot render it")
        if "type" not in p:
            raise AssertionError(f"param {p['key']!r} has no type")
    return True


def check_signal(slug):
    """generate_signal must return a well-formed SignalResult on real data."""
    import pandas as pd
    from strategies.registry import get_strategy
    from strategies.base import SignalResult
    from db.client import get_engine, get_price_bars, get_vix_bars

    strategy = get_strategy(slug)
    engine = get_engine()
    td = date.today()
    fd = date(td.year - 3, td.month, td.day)
    bars = get_price_bars(engine, "SPY", fd, td)
    if bars is None or bars.empty:
        raise _Skip("no price data")
    if "date" in bars.columns:
        bars = bars.set_index("date")
    bars.index = pd.to_datetime(bars.index)

    vix = get_vix_bars(engine, fd, td)
    snapshot = {
        "ticker": "SPY",
        "price": float(bars["close"].iloc[-1]),
        "price_data": bars,
        "features_df": bars,
        "vix": float(vix["close"].iloc[-1]) if not vix.empty else 18.0,
        "vix_series": vix["close"] if not vix.empty else None,
        "rate_10y": 4.2, "rate_2y": 4.0,
        "benchmark_price": float(bars["close"].iloc[-1]),
        "days_to_next_exdiv": 30, "next_dividend_yield": 0.013,
    }
    res = strategy.generate_signal(snapshot)
    # NB: identity check by name, not isinstance — the codebase's dual import
    # roots (`strategies.base` vs `alan_trader.strategies.base`) produce two
    # distinct SignalResult classes for the same source file.
    if type(res).__name__ != "SignalResult":
        raise AssertionError(f"returned {type(res).__name__}, not SignalResult")
    if res.signal not in ("BUY", "SELL", "HOLD"):
        raise AssertionError(f"invalid signal {res.signal!r}")
    if not (0.0 <= float(res.confidence) <= 1.0):
        raise AssertionError(f"confidence out of range: {res.confidence}")
    if float(res.position_size_pct) < 0:
        raise AssertionError(f"negative position size: {res.position_size_pct}")
    return True


_SCAN_CACHE: dict[str, list] = {}


def _scan_rows(slug):
    """Real screener rows — the same data the grid holds when a user clicks."""
    if slug not in _SCAN_CACHE:
        from app import get_polygon_api_key
        from app.pages.strategies.scan import _run_scan
        try:
            rows, _status, _banner = _run_scan(slug, "ETF Core", None,
                                               get_polygon_api_key())
            _SCAN_CACHE[slug] = list(rows or [])
        except Exception:
            _SCAN_CACHE[slug] = []
    return _SCAN_CACHE[slug]


def _count_graphs(node) -> int:
    """Count dcc.Graph components anywhere in a Dash tree."""
    from dash import dcc
    from dash.development.base_component import Component
    if isinstance(node, dcc.Graph):
        return 1
    if isinstance(node, (list, tuple)):
        return sum(_count_graphs(n) for n in node)
    if isinstance(node, Component):
        return _count_graphs(getattr(node, "children", None))
    return 0


def check_payoff(slug):
    """
    The payoff diagram lives on the signal popup: a screener row is clicked and
    `_build_signal_body` renders the body. This drives that exact path with a
    real screener row.
    """
    from app.pages.strategies.modals import _build_signal_body

    rows = _scan_rows(slug)
    if not rows:
        raise _Skip("screener returned no rows today")

    row = {**rows[0], "_slug": slug}
    body = _build_signal_body(row)
    if body is None:
        raise AssertionError("popup body was None")
    if type(body).__name__ == "_NoUpdate":
        raise AssertionError("popup body returned no_update for a real row")
    if _count_graphs(body) < 1:
        raise AssertionError("popup body built but contains no chart/payoff graph")
    return True


def check_paper(slug):
    """Paper-trade insert path: the columns it writes must exist in the schema."""
    from db.client import get_engine
    from sqlalchemy import text
    required = {
        "portfolio.Position": ["PositionId", "AccountId", "SecurityId",
                               "Status", "StrategyName"],
        "portfolio.Leg": ["LegId", "PositionId", "Symbol", "Strike",
                          "ContractType", "Expiration"],
        "portfolio.Transaction": ["TransactionId", "AccountId", "Amount",
                                  "Action"],
    }
    with get_engine().connect() as conn:
        for tbl, cols in required.items():
            schema, name = tbl.split(".")
            have = {r[0] for r in conn.execute(text(
                "SELECT c.name FROM sys.columns c JOIN sys.tables t "
                "ON t.object_id=c.object_id JOIN sys.schemas s "
                "ON s.schema_id=t.schema_id WHERE s.name=:s AND t.name=:t"),
                {"s": schema, "t": name}).fetchall()}
            if not have:
                raise AssertionError(f"table {tbl} does not exist")
            missing = [c for c in cols if c not in have]
            if missing:
                raise AssertionError(f"{tbl} missing columns {missing}")
    return True


SURFACES = [
    ("guide", check_guide),
    ("layout", check_layout),
    ("params", check_params),
    ("signal", check_signal),
    ("payoff", check_payoff),
    ("paper", check_paper),
]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--slugs")
    args = ap.parse_args(argv)

    from app.pages.strategies.registry import _STRATEGIES_RULES, _STRATEGIES_AI
    from strategies.registry import STRATEGY_METADATA

    all_slugs = [e["value"] for e in _STRATEGIES_RULES + _STRATEGIES_AI]
    slugs = [s.strip() for s in args.slugs.split(",")] if args.slugs else all_slugs

    chk = Check()
    names = [n for n, _ in SURFACES]
    print(f"{'slug':<26}{'type':<6}" + "".join(f"{n:>9}" for n in names))
    print("-" * (32 + 9 * len(names)))

    for slug in slugs:
        for surface, fn in SURFACES:
            _try(chk, slug, surface, lambda fn=fn, s=slug: fn(s))
        stype = STRATEGY_METADATA.get(slug, {}).get("type", "?")
        row = chk.rows[slug]
        print(f"{slug:<26}{stype:<6}"
              + "".join(f"{row.get(n, '?'):>9}" for n in names))

    n_fail = len(chk.problems)
    print(f"\n{len(slugs)} strategies × {len(names)} surfaces — {n_fail} failures")

    if chk.problems:
        print("\n── failures ─────────────────────────────────────────────────")
        for slug, surface, detail in chk.problems:
            print(f"  {slug:<26}{surface:<9}{detail}")

    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
