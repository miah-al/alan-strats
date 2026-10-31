"""
scripts/rank_strategies.py — headless quant ranking over the production backtest path.

Replicates `app/pages/strategies/backtest_view.py::_run_backtest` exactly (same
loaders, same strategy classes, same default UI params, same auxiliary_data
shape) so the numbers this prints are the numbers the app produces. Nothing is
simulated or fabricated: a strategy that cannot get its data is reported as
BLOCKED with the loader's own reason, never as a zero.

Usage
-----
    python -m scripts.rank_strategies                  # rank everything
    python -m scripts.rank_strategies --slugs hmm_regime,vrp_premium
    python -m scripts.rank_strategies --json out.json --markdown out.md

Ranking is on CAGR by default; `--sort sharpe` is meaningful now that the
risk-free hurdle is only charged on deployed days (see risk/metrics.py).
"""
from __future__ import annotations

import argparse
import importlib
import json
import logging
import os
import sys
import traceback

# The codebase mixes two import roots: `app.*` / `strategies.*` (repo-relative)
# and `alan_trader.*` (parent-relative). Both must be importable.
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)
# alan_trader is this checkout by file path, whatever its folder is called; the parent stays off sys.path
# (beside the live checkout it would expose that copy) — api/bootstrap.py.
from api.bootstrap import register_platform_package  # noqa: E402

register_platform_package()
from dataclasses import dataclass, field, asdict
from datetime import date, timedelta
from typing import Any, Optional

import pandas as pd

logging.basicConfig(level=logging.WARNING,
                    format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("rank")

# Silence the noisy per-strategy loggers; we report status ourselves.
for _n in ("strategies", "app", "db", "engine"):
    logging.getLogger(_n).setLevel(logging.ERROR)


# ── Windows ───────────────────────────────────────────────────────────────────
# Kept identical to the 2026-07-11 audit so results stay comparable. A window is
# a property of the *data that exists*, not of the strategy's quality — the
# report prints it on every row precisely because they are not interchangeable.

PRICE_WINDOW    = ("2021-01-01", "2026-06-30")   # includes the 2022 bear
OPTIONS_WINDOW  = ("2024-04-01", "2026-03-31")   # extent of the option surface
EARNINGS_TICKER = "F"                            # only ticker with earnings+options

# Indicator warm-up. Feeding a strategy only the reporting window silently
# cripples anything with a long lookback: a 12-month momentum has NaN for its
# first 12 month-ends, and `NaN > 0` evaluates to False, so the strategy is
# forced FLAT for a year and the missed return is scored against it as if it
# were a decision. (Measured on a 12-month momentum overlay: 272 of 1378 bars
# forced flat, missing +23.6%, understating CAGR by ~3pp.) We therefore load history from
# WARMUP_DAYS before the window, then truncate the equity curve back to the
# window before computing metrics — so the warm-up informs the indicators but
# never contributes to the score.
WARMUP_DAYS = 420

# Which window a strategy is ranked on is declared by its plugin
# (metadata key ``rank_window``: "price" (default) | "options" | "earnings").


def _one_line(text: str, limit: int = 220) -> str:
    """Collapse a driver traceback into something a table cell can hold."""
    flat = " ".join(str(text).split()).replace("|", "/")
    return flat[:limit] + ("…" if len(flat) > limit else "")


@dataclass
class RunResult:
    slug: str
    type: str = "?"
    ticker: str = "SPY"
    window: str = ""
    status: str = "OK"              # OK | BLOCKED | ERROR | NO_TRADES
    reason: str = ""
    cagr_pct: Optional[float] = None
    total_return_pct: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    sharpe: Optional[float] = None
    sortino: Optional[float] = None
    calmar: Optional[float] = None
    exposure_pct: Optional[float] = None
    profit_factor: Optional[float] = None
    win_rate_pct: Optional[float] = None
    num_trades: int = 0
    span_days: int = 0          # calendar days actually covered by the equity curve
    window_days: int = 0        # calendar days requested
    metrics: dict = field(default_factory=dict)

    @property
    def coverage(self) -> float:
        return (self.span_days / self.window_days) if self.window_days else 0.0


def _alert_text(alert: Any) -> str:
    """Flatten a dbc.Alert (or anything) into a one-line reason string."""
    try:
        from dash.development.base_component import Component
    except Exception:
        Component = ()  # type: ignore

    def walk(node) -> list[str]:
        if node is None:
            return []
        if isinstance(node, str):
            return [node]
        if isinstance(node, (list, tuple)):
            return [t for n in node for t in walk(n)]
        if Component and isinstance(node, Component):
            return walk(getattr(node, "children", None))
        return []

    text = " ".join(walk(alert)).split()
    return " ".join(text)[:300] or "blocked (no reason given)"


def _degenerate_reason(result: Any, slug: str) -> str:
    """
    Detect a run that produced no trades because it could not see its inputs.

    Strategies signal this in `extra` (news_sentiment_nlp sets
    `model_meta.sentiment_active = False` when it falls back to sentiment=0).
    Nothing in the app reads those flags, so a broken run renders as a clean
    zero — which reads as "no setups today" rather than "no data".
    """
    extra = getattr(result, "extra", None) or {}
    meta = extra.get("model_meta") or {}
    if meta.get("sentiment_active") is False:
        return ("ran with sentiment forced to 0 — no news-sentiment data; "
                "this is a degenerate fallback, NOT evidence of no signal")
    for key in ("degenerate", "fallback_mode", "data_missing"):
        if extra.get(key):
            return f"degenerate run: {key}={extra[key]}"
    return ""


def window_for(slug: str) -> tuple[str, str, str]:
    """Return (ticker, from_date, to_date) for a slug, per its declared window."""
    from alan_trader.strategy_api.registry import STRATEGY_METADATA
    kind = STRATEGY_METADATA.get(slug, {}).get("rank_window", "price")
    if kind == "earnings":
        return EARNINGS_TICKER, OPTIONS_WINDOW[0], OPTIONS_WINDOW[1]
    if kind == "options":
        return "SPY", OPTIONS_WINDOW[0], OPTIONS_WINDOW[1]
    return "SPY", PRICE_WINDOW[0], PRICE_WINDOW[1]


def run_one(slug: str, capital: float = 100_000.0) -> RunResult:
    """
    Run a single strategy through the production backtest path.

    Mirrors backtest_view._run_backtest step for step.
    """
    from db.client import get_engine, get_price_bars, get_vix_bars, get_macro_bars
    from app.pages.backtest_loaders import run_loaders_for
    from app.pages.strategies.backtest_view import _get_ui_params_for_slug
    from alan_trader.strategy_api.base import StubStrategy
    from alan_trader.strategy_api.registry import STRATEGY_METADATA, get_strategy

    ticker, from_date, to_date = window_for(slug)
    res = RunResult(
        slug=slug,
        type=STRATEGY_METADATA.get(slug, {}).get("type", "?"),
        ticker=ticker,
        window=f"{from_date[:7]}→{to_date[:7]}",
    )

    strategy = get_strategy(slug) if slug in STRATEGY_METADATA else None
    if strategy is None or isinstance(strategy, StubStrategy):
        res.status, res.reason = "ERROR", "no implementation registered"
        return res

    fd, td = date.fromisoformat(from_date), date.fromisoformat(to_date)
    load_fd = fd - timedelta(days=WARMUP_DAYS)   # indicators warm up before `fd`

    try:
        engine = get_engine()
    except Exception as exc:
        res.status, res.reason = "ERROR", _one_line(f"engine unavailable: {exc}")
        return res

    # ── price data ────────────────────────────────────────────────────────────
    try:
        price_data = get_price_bars(engine, ticker, load_fd, td)
    except Exception as exc:
        res.status, res.reason = "ERROR", _one_line(f"price load failed: {exc}")
        return res

    if price_data is None or price_data.empty:
        res.status, res.reason = "BLOCKED", f"no price bars for {ticker} in window"
        return res

    if "date" in price_data.columns:
        price_data = price_data.set_index("date")
    price_data.index = pd.to_datetime(price_data.index)

    # ── auxiliary data ────────────────────────────────────────────────────────
    try:
        vix_df = get_vix_bars(engine, load_fd, td)
        rate_df = get_macro_bars(engine, load_fd, td)
    except Exception:
        vix_df, rate_df = pd.DataFrame(), pd.DataFrame()

    if not vix_df.empty:
        vix_df.index = pd.to_datetime(vix_df.index)
    if not rate_df.empty:
        rate_df.index = pd.to_datetime(rate_df.index)

    auxiliary_data = {"vix": vix_df, "rate10y": rate_df, "ticker": ticker}

    try:
        aux_extra, block = run_loaders_for(
            slug, engine, ticker, fd, td, price_data=price_data,
        )
    except Exception as exc:
        res.status, res.reason = "ERROR", _one_line(f"loader raised: {exc}")
        return res

    auxiliary_data.update(aux_extra)
    if block is not None:
        res.status, res.reason = "BLOCKED", _alert_text(block)
        return res

    # ── run ───────────────────────────────────────────────────────────────────
    try:
        ui_params = _get_ui_params_for_slug(slug)
        params = {p["key"]: p["default"] for p in ui_params if "default" in p}
        result = strategy.backtest(
            price_data, auxiliary_data, starting_capital=capital, **params,
        )
    except NotImplementedError:
        res.status, res.reason = "BLOCKED", "backtest not implemented"
        return res
    except Exception as exc:
        res.status = "ERROR"
        res.reason = _one_line(f"{type(exc).__name__}: {exc}")
        logger.debug(traceback.format_exc())
        return res

    # ── score on the reporting window only ────────────────────────────────────
    # The strategy ran with WARMUP_DAYS of extra history so its indicators were
    # live from bar one of the window. Its own `metrics` cover that whole span,
    # so recompute from the equity curve truncated to [fd, td]; the warm-up
    # informs the signal but must not be scored.
    m = dict(getattr(result, "metrics", {}) or {})
    try:
        eq = getattr(result, "equity_curve", None)
        if eq is not None and len(eq) > 0:
            eq = pd.Series(eq).copy()
            eq.index = pd.to_datetime(eq.index)
            eq_win = eq[eq.index >= pd.Timestamp(fd)]
            if len(eq_win) > 2:
                from risk.metrics import compute_all_metrics

                trades = getattr(result, "trades", None)
                tw = trades
                if trades is not None and not trades.empty:
                    for col in ("exit_date", "entry_date"):
                        if col in trades.columns:
                            when = pd.to_datetime(trades[col], errors="coerce")
                            tw = trades[when >= pd.Timestamp(fd)]
                            break
                m = compute_all_metrics(eq_win,
                                        tw if tw is not None and not tw.empty else None)
                res.window = f"{fd:%Y-%m}→{td:%Y-%m}"
                res.span_days = int((eq_win.index.max() - eq_win.index.min()).days)
                res.window_days = int((td - fd).days)
    except Exception as exc:
        logger.warning(f"{slug}: window truncation failed, using strategy metrics: {exc}")

    res.metrics = m
    res.cagr_pct = m.get("annualized_return_pct")
    res.total_return_pct = m.get("total_return_pct")
    res.max_drawdown_pct = m.get("max_drawdown_pct")
    res.sharpe = m.get("sharpe")
    res.sortino = m.get("sortino")
    res.calmar = m.get("calmar")
    res.exposure_pct = m.get("exposure_pct")
    res.profit_factor = m.get("profit_factor")
    res.win_rate_pct = m.get("win_rate_pct")
    res.num_trades = int(m.get("num_trades", 0) or 0)

    if res.num_trades == 0:
        # Distinguish "found no opportunities" from "could not see the data".
        # Reporting a degenerate/no-data run as `ran clean` reads as *flat, no
        # setups* when the truth is *broken, no inputs* — that mislabelled
        # news_sentiment_nlp (running with sentiment forced to 0) and
        # vrp_premium (which had errored on missing IV) as clean zero rows.
        degenerate = _degenerate_reason(result, slug)
        if degenerate:
            res.status, res.reason = "DEGENERATE", degenerate
        else:
            res.status = "NO_TRADES"
            res.reason = "ran clean but produced no trades in this window"
    elif res.window_days and res.coverage < 0.60:
        # A curve covering a fraction of the window still gets annualized, so a
        # modest total return becomes a spectacular CAGR (vrp_premium: 14.3%
        # over ~4.5 months of available option data read as 42%/yr). Those rows
        # are not comparable to full-window ones and must not head the ranking.
        res.status = "SHORT_SPAN"
        res.reason = (f"equity curve covers {res.span_days}d of a "
                      f"{res.window_days}d window ({res.coverage:.0%}) — "
                      f"CAGR annualizes a partial period, not comparable")

    return res


def benchmark_buy_and_hold(ticker: str, from_date: str, to_date: str) -> dict:
    """Buy-and-hold on real bars — the bar every strategy has to clear."""
    from db.client import get_engine, get_price_bars
    from risk.metrics import compute_all_metrics

    engine = get_engine()
    bars = get_price_bars(engine, ticker, date.fromisoformat(from_date),
                          date.fromisoformat(to_date))
    if bars is None or bars.empty:
        return {}
    if "date" in bars.columns:
        bars = bars.set_index("date")
    bars.index = pd.to_datetime(bars.index)
    close = bars["close"] if "close" in bars.columns else bars.iloc[:, -1]
    equity = 100_000.0 * (close / close.iloc[0])
    return compute_all_metrics(equity)


def fmt(v, nd=2, dash="—"):
    return dash if v is None else f"{v:.{nd}f}"


def to_markdown(results: list[RunResult], benches: dict) -> str:
    ok = [r for r in results if r.status in ("OK", "NO_TRADES")]
    short = [r for r in results if r.status == "SHORT_SPAN"]
    bad = [r for r in results if r.status not in ("OK", "NO_TRADES", "SHORT_SPAN")]
    ok.sort(key=lambda r: (r.cagr_pct is None, -(r.cagr_pct or 0)))

    lines = []
    lines.append("| # | Strategy | Type | CAGR% | TotRet% | MaxDD% | Sharpe | Sortino "
                 "| Expo% | PF | Win% | Trades | Window | Ticker |")
    lines.append("|--:|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|---|---|")
    for i, r in enumerate(ok, 1):
        lines.append(
            f"| {i} | {r.slug} | {r.type} | {fmt(r.cagr_pct)} | {fmt(r.total_return_pct)} "
            f"| {fmt(r.max_drawdown_pct)} | {fmt(r.sharpe)} | {fmt(r.sortino)} "
            f"| {fmt(r.exposure_pct,1)} | {fmt(r.profit_factor)} | {fmt(r.win_rate_pct,1)} "
            f"| {r.num_trades} | {r.window} | {r.ticker} |"
        )

    if benches:
        lines.append("")
        lines.append("**Buy-and-hold benchmarks (real bars, same windows):**")
        lines.append("")
        lines.append("| Benchmark | CAGR% | TotRet% | MaxDD% | Sharpe |")
        lines.append("|---|--:|--:|--:|--:|")
        for name, b in benches.items():
            if b:
                lines.append(
                    f"| {name} | {fmt(b.get('annualized_return_pct'))} "
                    f"| {fmt(b.get('total_return_pct'))} "
                    f"| {fmt(b.get('max_drawdown_pct'))} | {fmt(b.get('sharpe'))} |"
                )

    if short:
        lines.append("")
        lines.append("**Measured on a partial window — CAGR annualizes an "
                     "incomplete period and is NOT comparable to the table above:**")
        lines.append("")
        lines.append("| Strategy | Type | CAGR%* | TotRet% | MaxDD% | Sharpe "
                     "| Trades | Covered | Window |")
        lines.append("|---|---|--:|--:|--:|--:|--:|--:|---|")
        for r in sorted(short, key=lambda r: -(r.total_return_pct or 0)):
            lines.append(
                f"| {r.slug} | {r.type} | {fmt(r.cagr_pct)} | {fmt(r.total_return_pct)} "
                f"| {fmt(r.max_drawdown_pct)} | {fmt(r.sharpe)} | {r.num_trades} "
                f"| {r.coverage:.0%} | {r.window} |"
            )
        lines.append("")
        lines.append("\\* Read TotRet%, not CAGR%, for these rows.")

    if bad:
        lines.append("")
        lines.append("**Not ranked — could not produce real numbers:**")
        lines.append("")
        lines.append("| Strategy | Type | Status | Reason |")
        lines.append("|---|---|---|---|")
        for r in sorted(bad, key=lambda r: (r.status, r.slug)):
            lines.append(f"| {r.slug} | {r.type} | {r.status} | {r.reason} |")

    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--slugs", help="comma-separated subset to run")
    ap.add_argument("--capital", type=float, default=100_000.0)
    ap.add_argument("--json", dest="json_out")
    ap.add_argument("--markdown", dest="md_out")
    ap.add_argument("--sort", default="cagr", choices=["cagr", "sharpe", "calmar"])
    args = ap.parse_args(argv)

    from app.pages.strategies.registry import _STRATEGIES_RULES, _STRATEGIES_AI

    all_slugs = [e["value"] for e in _STRATEGIES_RULES + _STRATEGIES_AI]
    slugs = ([s.strip() for s in args.slugs.split(",")] if args.slugs else all_slugs)

    results: list[RunResult] = []
    for i, slug in enumerate(slugs, 1):
        print(f"[{i:>2}/{len(slugs)}] {slug:<26} ", end="", flush=True)
        r = run_one(slug, capital=args.capital)
        results.append(r)
        if r.status in ("OK", "NO_TRADES"):
            print(f"{r.status:<9} CAGR={fmt(r.cagr_pct):>7}  Sharpe={fmt(r.sharpe):>7}  "
                  f"trades={r.num_trades}")
        else:
            print(f"{r.status:<9} {r.reason[:80]}")

    benches = {}
    try:
        benches[f"SPY buy&hold {PRICE_WINDOW[0][:7]}→{PRICE_WINDOW[1][:7]}"] = \
            benchmark_buy_and_hold("SPY", *PRICE_WINDOW)
        benches[f"SPY buy&hold {OPTIONS_WINDOW[0][:7]}→{OPTIONS_WINDOW[1][:7]}"] = \
            benchmark_buy_and_hold("SPY", *OPTIONS_WINDOW)
    except Exception as exc:
        logger.warning(f"benchmark failed: {exc}")

    md = to_markdown(results, benches)
    print()
    print(md)

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump({"results": [asdict(r) for r in results],
                       "benchmarks": benches}, fh, indent=2, default=str)
        print(f"\nwrote {args.json_out}")

    if args.md_out:
        with open(args.md_out, "w", encoding="utf-8") as fh:
            fh.write(md + "\n")
        print(f"wrote {args.md_out}")

    n_ok = sum(1 for r in results if r.status == "OK")
    print(f"\n{n_ok}/{len(results)} produced real ranked metrics.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
