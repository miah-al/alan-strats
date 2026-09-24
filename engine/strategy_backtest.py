"""
engine/strategy_backtest.py — run a strategy through the production backtest path, headless.

The Performance tab (``app/pages/strategies/performance.py``) and the service API
both come through ``run_backtest``: price bars with a warm-up, VIX / rates, the
strategy's declared auxiliary-data loaders (``engine.backtest_loaders``), the
strategy's own ``backtest()``, then metrics on the reporting window only, against
buy & hold on the identical window.

Reporting choices (see performance.py): CAGR is annualised over elapsed time, the
warm-up never enters a metric, and coverage says how much of the requested window
the equity curve actually spans.

Names no strategy.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Callable, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Matches scripts/rank_strategies.py and the Backtest / Performance tabs.
WARMUP_DAYS = 420

Progress = Optional[Callable[[Optional[float], Optional[str]], None]]


class LoaderBlocked(ValueError):
    """A loader the strategy declares found no data for the window.

    ``str(exc)`` is the page's historical one-liner; ``reason`` is the loader's own
    message (which data is missing and how to fill it)."""

    def __init__(self, message: str, reason: str = ""):
        super().__init__(message)
        self.reason = reason or message


def component_text(node: Any) -> str:
    """Plain text of a rendered component tree (a loader's LoaderAlert, a Dash alert): the
    strings in ``children``, depth first. Works on anything shaped like a Dash
    component without importing Dash."""
    out: list[str] = []

    def walk(n):
        if n is None:
            return
        if isinstance(n, str):
            out.append(n)
        elif isinstance(n, (int, float)):
            out.append(str(n))
        elif isinstance(n, (list, tuple)):
            for c in n:
                walk(c)
        else:
            walk(getattr(n, "children", None))

    walk(node)
    return " ".join(" ".join(out).split())


def _report(progress: Progress, fraction: Optional[float], message: Optional[str]) -> None:
    if progress is not None:
        progress(fraction, message)


def backtest_param_specs(slug: str) -> list:
    """Instantiate the strategy and return its get_backtest_ui_params()."""
    from alan_trader.strategy_api.base import StubStrategy
    from alan_trader.strategy_api.registry import get_strategy
    try:
        strategy = get_strategy(slug)
        if isinstance(strategy, StubStrategy):
            return []
        return list(strategy.get_backtest_ui_params() or [])
    except Exception:
        logger.exception(f"{slug}: get_backtest_ui_params failed")
        return []


def default_backtest_params(slug: str) -> dict:
    """``{key: default}`` for every backtest UI param that declares a default."""
    return {p["key"]: p["default"] for p in backtest_param_specs(slug) if "default" in p}


def run_backtest(slug: str, ticker: str, from_date: str, to_date: str, capital: float,
                 params: Optional[dict] = None, *, report_window: bool = False,
                 progress: Progress = None) -> dict:
    """
    Run the strategy through the production path and return everything the
    Performance tab renders, plus the raw ``BacktestResult`` (``result``) and the
    parameters actually used (``params``). Raises on failure so the caller can
    surface the real reason.

    ``params`` override the defaults from ``get_backtest_ui_params()``.
    ``report_window`` also hands the strategy the reporting window
    (``report_from`` / ``report_to`` in auxiliary_data), as the Backtest tab does, so a
    strategy that does not need the warm-up bars can skip them.
    """
    from db.client import get_engine, get_price_bars, get_vix_bars, get_macro_bars
    from engine.backtest_loaders import run_loaders_for
    from alan_trader.strategy_api.base import StubStrategy
    from alan_trader.strategy_api.registry import get_strategy
    from risk.metrics import compute_all_metrics

    strategy = get_strategy(slug)
    if isinstance(strategy, StubStrategy):
        raise ValueError(f"No implementation registered for {slug!r}.")

    fd, td = date.fromisoformat(from_date), date.fromisoformat(to_date)
    load_fd = fd - timedelta(days=WARMUP_DAYS)   # indicators warm up before fd

    _report(progress, 0.02, f"loading {ticker} price bars")
    engine = get_engine()
    bars = get_price_bars(engine, ticker, load_fd, td)
    if bars is None or bars.empty:
        raise ValueError(f"No price bars for {ticker} in {from_date} → {to_date}.")
    if "date" in bars.columns:
        bars = bars.set_index("date")
    bars.index = pd.to_datetime(bars.index)

    _report(progress, 0.08, "loading VIX and rates")
    try:
        vix_df = get_vix_bars(engine, load_fd, td)
        rate_df = get_macro_bars(engine, load_fd, td)
    except Exception:
        vix_df, rate_df = pd.DataFrame(), pd.DataFrame()
    if not vix_df.empty:
        vix_df.index = pd.to_datetime(vix_df.index)
    if not rate_df.empty:
        rate_df.index = pd.to_datetime(rate_df.index)

    aux = {"vix": vix_df, "rate10y": rate_df, "ticker": ticker}
    if report_window:
        aux.update(report_from=from_date, report_to=to_date)
    _report(progress, 0.12, "loading the strategy's auxiliary data")
    extra, block = run_loaders_for(slug, engine, ticker, fd, td, price_data=bars)
    aux.update(extra)
    if block is not None:
        raise LoaderBlocked(
            f"{slug} is missing required data for this window — see the "
            f"Backtest tab for the loader's message.", component_text(block))

    used = {**default_backtest_params(slug), **(params or {})}
    _report(progress, 0.30, "running the backtest")
    result = strategy.backtest(bars, aux, starting_capital=float(capital), **used)

    _report(progress, 0.90, "computing metrics")
    equity = pd.Series(result.equity_curve).copy()
    equity.index = pd.to_datetime(equity.index)
    equity = equity[equity.index >= pd.Timestamp(fd)]
    if len(equity) < 3:
        raise ValueError("Backtest produced too few equity points to analyse.")

    trades = result.trades if result.trades is not None else pd.DataFrame()
    if not trades.empty:
        for col in ("exit_date", "entry_date"):
            if col in trades.columns:
                when = pd.to_datetime(trades[col], errors="coerce")
                trades = trades[when >= pd.Timestamp(fd)]
                break

    metrics = compute_all_metrics(equity, trades if not trades.empty else None)

    # Benchmark on the identical window.
    close = bars["close"] if "close" in bars.columns else bars.iloc[:, -1]
    close = close[close.index >= pd.Timestamp(fd)]
    bench_equity = float(capital) * (close / close.iloc[0])
    bench_metrics = compute_all_metrics(bench_equity)

    span_days = int((equity.index.max() - equity.index.min()).days)
    window_days = int((td - fd).days)

    return {
        "slug": slug, "ticker": ticker,
        "equity": equity, "bench_equity": bench_equity,
        "metrics": metrics, "bench_metrics": bench_metrics,
        "trades": trades,
        "coverage": (span_days / window_days) if window_days else 0.0,
        "span_days": span_days, "window_days": window_days,
        "from_date": from_date, "to_date": to_date,
        "params": used, "result": result,
    }


def performance_warnings(perf: dict) -> list[str]:
    """The things that make a headline number untrustworthy, as plain sentences
    (the Performance tab's "Read with care" panel). ``perf`` is ``run_backtest``'s dict."""
    notes = []
    m = perf["metrics"]
    n = int(m.get("num_trades") or 0)
    if 0 < n < 30:
        notes.append(f"Only {n} trades — too few to be statistically meaningful. "
                     f"Treat CAGR, Sharpe and profit factor as anecdotes.")
    if n == 0:
        notes.append("No trades in this window; every metric below is the "
                     "equity curve sitting flat.")
    if perf["coverage"] < 0.6 and perf["window_days"]:
        notes.append(
            f"The equity curve covers only {perf['span_days']}d of a "
            f"{perf['window_days']}d window ({perf['coverage']:.0%}). CAGR "
            f"annualizes that partial period — read total return instead.")
    pf = m.get("profit_factor")
    if pf in (float("inf"), None) and n > 5:
        notes.append("Profit factor is infinite — there are no losing trades at "
                     "all. Over this many trades that usually means losses are "
                     "not being realised, not that the strategy cannot lose.")
    if float(m.get("max_drawdown_pct") or 0) == 0.0 and n > 5:
        notes.append("Max drawdown is exactly zero, which normally means open "
                     "positions are never marked to market — the curve only "
                     "moves on close.")
    return notes
