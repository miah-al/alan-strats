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
import re
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


def live_values(strategy) -> dict:
    """What the strategy's live runner starts with: its own parameters (``get_params()``), then the ``LIVE_PARAMS`` it
    declares for live sessions (the fill model and crossing cost measured on real fills)."""
    out: dict = {}
    try:
        p = strategy.get_params()
        if isinstance(p, dict):
            out.update(p)
    except Exception:
        pass
    out.update(dict(getattr(strategy, "LIVE_PARAMS", None) or {}))
    return out


_CODE = re.compile(r"(\d+)\s*=?\s*([A-Za-z][\w-]*)")


def slider_codes(label: str) -> dict[str, int]:
    """A slider that stands for names, read from its label: "Fill model (0 maker, 1 mid, 2 taker)" gives
    {"maker": 0, "mid": 1, "taker": 2}; "Price source (0 model, 1 market prints)" gives {"model": 0, "market": 1}."""
    if "(" not in label:
        return {}
    inner = label[label.find("(") + 1: label.rfind(")") if ")" in label else len(label)]
    return {m.group(2).lower(): int(m.group(1)) for m in _CODE.finditer(inner)}


def synced_spec(spec: dict, live: dict) -> dict:
    """``spec`` with its default replaced by the live runner's value, in the spec's own terms (a number, a bool as 0/1,
    a name as its slider code); unchanged when the two cannot be matched. The range widens to hold the value."""
    key = spec.get("key")
    if key not in live or "default" not in spec:
        return spec
    v, d = live[key], spec["default"]
    new = None
    if isinstance(v, bool):
        new = v if isinstance(d, bool) else (int(v) if isinstance(d, (int, float)) else None)
    elif isinstance(v, (int, float)) and isinstance(d, (int, float)) and not isinstance(d, bool):
        new = int(v) if isinstance(d, int) and float(v).is_integer() else v
    elif isinstance(v, str) and isinstance(d, str):
        new = v
    elif isinstance(v, str) and isinstance(d, (int, float)) and not isinstance(d, bool):
        codes = slider_codes(str(spec.get("label") or ""))
        name = v.lower()
        if name in codes:
            new = codes[name]
        else:
            new = next((c for w, c in codes.items() if w.startswith(name) or name.startswith(w)), None)
    if new is None or new == d:
        return spec
    out = dict(spec, default=new)
    if isinstance(new, (int, float)) and not isinstance(new, bool):
        if out.get("min") is not None and new < out["min"]:
            out["min"] = new
        if out.get("max") is not None and new > out["max"]:
            out["max"] = new
    out["help"] = (str(spec.get("help") or "") + f" Default: the live runner's {v!r}.").strip()
    return out


def backtest_param_specs(slug: str) -> list:
    """The strategy's get_backtest_ui_params(), with every default the live runner overrides synced to what it runs
    (``live_values``). The tab's defaults drifted from the runners (2026-09-29: Friend's tab was a 50-wide trend follower
    with a 60-point stop and a $15k cap; its runner trades 100-wide against the move with no stop and a $5k cap, and
    v2.3's tab still said +5 for its +10), so a default backtest now tests what is running."""
    from alan_trader.strategy_api.base import StubStrategy
    from alan_trader.strategy_api.registry import get_strategy
    try:
        strategy = get_strategy(slug)
        if isinstance(strategy, StubStrategy):
            return []
        live = live_values(strategy)
        return [synced_spec(p, live) for p in (strategy.get_backtest_ui_params() or [])]
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

    defaults = default_backtest_params(slug)
    # The live pricing a strategy declares (LIVE_PARAMS) applies here too, as the runner applies it: keys the tab shows
    # are in its synced defaults; the rest (the crossing-cost model) are added when the strategy has such a parameter.
    live_params = dict(getattr(strategy, "LIVE_PARAMS", None) or {})
    try:
        own = strategy.get_params() or {}
    except Exception:
        own = {}
    hidden = {k: v for k, v in live_params.items() if k not in defaults and k in own}
    used = {**defaults, **hidden, **(params or {})}
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
        "live_params": {k: defaults.get(k, v) for k, v in live_params.items() if k in defaults or k in hidden},
        "live_defaults": defaults if live_params else {},
        "live_params_named": live_params,
    }


def performance_warnings(perf: dict) -> list[str]:
    """The things that make a headline number untrustworthy, as plain sentences
    (the Performance tab's "Read with care" panel). ``perf`` is ``run_backtest``'s dict."""
    notes = []
    # How the fills were priced, against how the live runner fills (its LIVE_PARAMS).
    live, named, used = perf.get("live_params") or {}, perf.get("live_params_named") or {}, perf.get("params") or {}
    live_defaults = perf.get("live_defaults") or {}

    def _same(a, b) -> bool:
        try:
            return float(a) == float(b)
        except (TypeError, ValueError):
            return str(a).lower() == str(b).lower()
    rules = [k for k, v in live_defaults.items() if k not in live and k in used and not _same(used[k], v)]
    if rules:
        notes.append("Not the strategy the live runner trades: " + ", ".join(f"{k} {used[k]!r} (live {live_defaults[k]!r})" for k in rules)
                     + ". Read it as a variant; Reset the parameters for the live settings.")
    if live:
        off = [k for k, v in live.items() if not _same(used.get(k), v)]
        what = ", ".join(f"{k} {named.get(k, v)}" for k, v in live.items())
        if off:
            notes.append("Not priced like the live runner: " + "; ".join(f"{k} is {used.get(k)!r} here, {named.get(k)!r} live" for k in off)
                         + ". Read the result as a model comparison, not a forecast of paper fills.")
        elif not rules:
            # The strategy says what its prices are (a calibrated model, last-trade prints...); the platform only knows
            # the fill rules it shares with the live runner.
            extra = getattr(perf.get("result"), "extra", None) or {}
            basis = extra.get("pricing_basis") or ("The fills are still modelled on last-trade prints, not the recorded "
                                                   "bid/ask; the quote replay is the real-quote check.")
            notes.append(f"Priced like the live runner ({what}). {basis}")
    # The same days on the recorded bid/ask (api/services/quote_replay.calibrate): how far the print-priced fills are
    # from real quotes (2026-09-29: Friend on 9/28 made +8,227 on prints, +2,462 on the recorded quotes).
    cal = perf.get("calibration")
    if cal is not None:
        ds = [d for d in cal.get("days") or [] if d.get("backtest_trades")]
        empty = [d["day"] for d in cal.get("days") or [] if not d.get("backtest_trades")]
        if ds:
            b = sum(d["backtest"] for d in ds)
            r = sum(d["replay"] for d in ds)
            bt = sum(d["backtest_trades"] for d in ds)
            rt = sum(d["replay_trades"] for d in ds)
            ratio = f", {b / r:.1f}x" if r > 0 and b > 0 else ""
            notes.append(f"Checked on real quotes: on {len(ds)} recorded day(s) ({', '.join(d['day'] for d in ds)}) this "
                         f"backtest made {b:+,.0f} over {bt} trades, and the live engine on the recorded bid/ask made "
                         f"{r:+,.0f} over {rt}{ratio}. The more days recorded, the better this check.")
        if empty:
            notes.append(f"No backtest trades on {', '.join(empty)}, a recorded day: its prints or index minutes are not "
                         "stored yet, so it is left out of the real-quote check.")
        if not cal.get("days") and cal.get("recorded"):
            notes.append(f"No day in this window has recorded quotes to check the fills against (recorded "
                         f"{cal['recorded'][0]} to {cal['recorded'][-1]}); include them to see how far prints are from real quotes.")
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
