"""
api/services/strategies.py — strategy metadata, screener scans, backtests, live signal.

Everything comes through the plugin registry (``alan_trader.strategy_api.registry``)
and the headless pipelines the Strategies page also uses
(``engine.strategy_scan``, ``engine.strategy_backtest``). Names no strategy.
"""
from __future__ import annotations

import logging
import threading
from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd

from api.jobs import JobContext, JobError
from api.serialize import DROP, column_from_aggrid, series, table_from_df, table_from_rows, to_jsonable

logger = logging.getLogger("alan_trader.api.strategies")

REVIEW_STATUSES = ("ready", "reviewed", "reviewing", "avoid")
#: The Backtest tab's fallbacks when a strategy declares no default window / capital.
DEFAULT_FROM = "2022-01-01"
DEFAULT_CAPITAL = 10_000

_INFO_CACHE: dict[str, dict] = {}
_INFO_LOCK = threading.Lock()


def clear_cache() -> None:
    """Forget cached StrategyInfo (after the registry is reloaded)."""
    with _INFO_LOCK:
        _INFO_CACHE.clear()


def R():
    from alan_trader.strategy_api import registry
    return registry


class UnknownStrategy(KeyError):
    pass


def require(slug: str) -> dict:
    meta = R().STRATEGY_METADATA.get(slug)
    if meta is None:
        raise UnknownStrategy(slug)
    return meta


def _strategy(slug: str):
    try:
        return R().get_strategy(slug)
    except Exception:
        logger.exception("%s: could not instantiate the strategy", slug)
        return None


def _is_stub(strat) -> bool:
    from alan_trader.strategy_api.base import StubStrategy
    return strat is None or isinstance(strat, StubStrategy)


def _overrides(obj, name: str, base) -> bool:
    return obj is not None and getattr(type(obj), name, None) is not getattr(base, name, None)


def _score(meta: dict) -> Optional[dict]:
    sc = meta.get("score")
    if not sc:
        return None
    try:
        value, grade = sc
        return {"value": int(value), "grade": str(grade)}
    except (TypeError, ValueError):
        return None


def labels() -> dict[str, str]:
    """slug → the label the Strategies page shows (the paper page uses the same map)."""
    return {e["value"]: e["label"] for e in R().ui_entries()}


def strategy_info(slug: str) -> dict:
    """StrategyInfo (contract). Cached: plugin metadata does not change at runtime."""
    with _INFO_LOCK:
        if slug in _INFO_CACHE:
            return dict(_INFO_CACHE[slug])
    from alan_trader.strategy_api.base import BaseStrategy
    from alan_trader.strategy_api.ui import StrategyUI
    from app.guides import find_guide

    meta = require(slug)
    reg = R()
    ui = reg.get_ui(slug)
    strat = _strategy(slug)
    plugin = reg.plugin_for(slug)

    has_screener = _overrides(ui, "scan", StrategyUI) and meta.get("has_screener", True) is not False
    live_inst = {}
    if not _is_stub(strat):
        try:
            live_inst = strat.live_instrument() or {}
        except Exception:
            live_inst = {}
    has_live = (not _is_stub(strat)) and (_overrides(strat, "live_session", BaseStrategy) or bool(live_inst))
    try:
        trainable = bool(strat.is_trainable()) if not _is_stub(strat) else bool(meta.get("requires_training"))
    except Exception:
        trainable = bool(meta.get("requires_training"))
    locked = list(ui.locked_tickers or [])
    review = meta.get("review_status")
    try:
        has_guide = find_guide(slug) is not None
    except Exception:
        has_guide = False
    info = {
        "slug": slug,
        "display_name": meta.get("display_name") or slug,
        "label": ui.label,
        "description": meta.get("description", ""),
        "type": meta.get("type", "rule"),
        "status": meta.get("status", "stub"),
        "review_status": review if review in REVIEW_STATUSES else None,
        "score": _score(meta),
        "asset_class": meta.get("asset_class", "equities"),
        "typical_holding_days": meta.get("typical_holding_days"),
        "target_sharpe": meta.get("target_sharpe"),
        "ui_visible": bool(meta.get("ui_visible")),
        "plugin": plugin.name if plugin else None,
        "default_ticker": str(meta.get("default_ticker") or "SPY").upper(),
        "default_from": str(meta.get("default_from") or DEFAULT_FROM),
        "default_capital": meta.get("default_capital") or DEFAULT_CAPITAL,
        "has_guide": has_guide,
        "has_screener": bool(has_screener),
        "has_signal_alert": bool(ui.has_signal_alert),
        "has_live_session": bool(has_live),
        "is_trainable": trainable,
        "trade_kind": ui.trade_kind,
        "is_credit": bool(ui.is_credit),
        "modal": ui.modal,
        "locked_tickers": locked or None,
        "locked_label": ui.locked_label or (f"{len(locked)} fixed tickers" if locked else ""),
        # additions beyond contract v1
        "icon": meta.get("icon"),
        "ui_order": meta.get("ui_order"),
        "has_backtest": not _is_stub(strat),
        "has_current_signal": _overrides(strat, "current_signal", BaseStrategy),
        "live_instrument": to_jsonable(live_inst, strict=True) or None,
        "disabled_by": meta.get("disabled_by"),
    }
    info = to_jsonable(info)
    with _INFO_LOCK:
        _INFO_CACHE[slug] = info
    return dict(info)


def list_strategies(include_hidden: bool = False) -> list[dict]:
    reg = R()
    ordered = [e["value"] for e in reg.ui_entries()]
    if include_hidden:
        ordered += [s for s in reg.STRATEGY_METADATA if s not in ordered]
    return [strategy_info(s) for s in ordered]


def _loader_names(ui) -> tuple[list[str], list[dict]]:
    from app.pages.backtest_loaders import parse_loader_spec
    names, specs = [], []
    for spec in ui.loaders() or []:
        try:
            name, opts = parse_loader_spec(spec)
        except Exception:
            continue
        names.append(name)
        specs.append({"name": name, "options": to_jsonable(opts, strict=True)})
    return names, specs


def strategy_detail(slug: str) -> dict:
    from engine.strategy_backtest import backtest_param_specs, component_text
    from engine.strategy_scan import UNIVERSE_TICKERS

    info = strategy_info(slug)
    reg = R()
    ui = reg.get_ui(slug)
    strat = _strategy(slug)

    try:
        banner = ui.info_banner()
        banner_text = (banner if isinstance(banner, str) else component_text(banner)) if banner is not None else None
    except Exception:
        logger.exception("%s: info_banner failed", slug)
        banner_text = None
    cols = None
    if ui.columns:
        cols = [c for c in (column_from_aggrid(cd) for cd in ui.columns) if c is not None]

    names, specs = _loader_names(ui)
    try:
        params = strat.get_params() if not _is_stub(strat) else {}
    except Exception:
        logger.exception("%s: get_params failed", slug)
        params = {}
    tabs = []
    try:
        for t in ui.extra_tabs() or []:
            tabs.append({"tab_id": getattr(t, "tab_id", None), "label": getattr(t, "label", None)})
    except Exception:
        logger.exception("%s: extra_tabs failed", slug)

    info.update({
        "screener": {
            "params": to_jsonable(list(ui.screener_params or [])),
            "default_params": to_jsonable(dict(ui.default_params or {})),
            "columns": cols,
            "universes": {k: list(v) for k, v in UNIVERSE_TICKERS.items()},
            "info_banner": banner_text or None,
        },
        "backtest": {
            "params": to_jsonable(backtest_param_specs(slug)),
            "loaders": names,
            "loader_specs": specs,
        },
        "params": to_jsonable(params),
        "extra_tabs": tabs,
    })
    return info


def guide(slug: str) -> dict:
    from app.guides import find_guide
    meta = require(slug)
    path = find_guide(slug)
    md = path.read_text(encoding="utf-8") if path is not None else f"*No guide article found for `{slug}`.*"
    title = None
    for line in md.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            break
    playbook = None
    root = meta.get("root")
    if root:
        pb = Path(root) / "playbook.md"
        if pb.is_file():
            playbook = pb.read_text(encoding="utf-8")
    return {"slug": slug, "title": title or meta.get("display_name") or slug, "markdown": md,
            "playbook_markdown": playbook, "path": str(path) if path else None}


# ── Scan ──────────────────────────────────────────────────────────────────────

def scan_job(ctx: JobContext, slug: str, tickers: list[str], params: dict, api_key: str,
             universe: str) -> dict:
    from app.ui.strategy_widgets import GENERIC_COLS
    from engine.strategy_scan import run_strategy_scan, vix_summary

    try:
        outcome = run_strategy_scan(slug, tickers, api_key, param_overrides=params, progress=ctx.progress)
    except RuntimeError as exc:          # the pipeline's own "no VIX" / "no prices" errors
        raise JobError(str(exc)) from exc
    ui = R().get_ui(slug)
    rows = []
    for r in outcome.display_rows:
        r = dict(r)
        if "score" not in r:
            sc = r.get("Score")
            r["score"] = float(sc) if isinstance(sc, (int, float)) and not isinstance(sc, bool) else 0.0
        rows.append(r)
    col_defs = list(ui.columns or GENERIC_COLS)
    table = table_from_rows(rows, col_defs=col_defs)
    declared = {c["field"] for c in table["columns"]}
    # every other key the rows carry (score, all_pass, n_pass, strategy internals) as hidden
    # columns, so the table describes all of its data
    extra_keys: list[str] = []
    for r in rows:
        for k in r:
            if k not in declared and k not in extra_keys and not any(k == cd.get("field") for cd in col_defs):
                extra_keys.append(k)
    if extra_keys:
        tail = table_from_rows([{k: r.get(k) for k in extra_keys} for r in rows], field_order=extra_keys)
        for c in tail["columns"]:
            c["hidden"] = True
        table["columns"].extend(tail["columns"])

    errors = list(outcome.errors)
    if outcome.ivr_fallback_count:
        errors.append(f"IVR data quality warning: {outcome.ivr_fallback_count}/{len(outcome.raw_rows)} "
                      "ticker(s) are using VIX proxy IVR — real options bid/ask unavailable.")
    vix = vix_summary(outcome.vix_series, slug)
    ready = sum(1 for r in rows if r.get("all_pass"))
    partial = sum(1 for r in rows if not r.get("all_pass") and (r.get("n_pass") or 0) > 0)
    blocked = sum(1 for r in rows if (r.get("n_pass") or 0) == 0)
    return {
        "table": table, "vix": vix, "tickers": outcome.tickers, "errors": errors,
        "slug": slug, "universe": universe, "params": outcome.params,
        "counts": {"trade_ready": ready, "partial": partial, "blocked": blocked, "scanned": len(rows)},
    }


# ── Backtest ──────────────────────────────────────────────────────────────────

#: The Backtest tab's trade-grid headers / order (app/pages/strategies/backtest_view.py).
_TRADE_HEADERS = {
    "entry_date": "Entry", "exit_date": "Exit", "pnl": "P&L", "pnl_pct": "P&L %",
    "dte_held": "DTE Held", "hold_days": "Days Held", "exit_reason": "Exit Reason",
    "contracts": "Contracts", "credit": "Credit", "call_short_k": "Call Short",
    "call_long_k": "Call Long", "put_short_k": "Put Short", "put_long_k": "Put Long",
    "margin_reserved": "Margin Rsv", "ticker": "Ticker", "status": "Status",
}
_TRADE_SKIP = {"winner", "free_capital"}
_TRADE_FORMATS = {"pnl": "money", "credit": "price", "margin_reserved": "money"}
_EXTRA_MAX_ROWS = 5000
_EXTRA_MAX_POINTS = 20000


def validate_backtest_params(slug: str, overrides: dict) -> dict:
    """Coerce user overrides to the declared param types; raise ValueError on an
    unknown key or an out-of-range value."""
    from engine.strategy_backtest import backtest_param_specs
    specs = {p["key"]: p for p in backtest_param_specs(slug) if "key" in p}
    out = {}
    for k, v in (overrides or {}).items():
        spec = specs.get(k)
        if spec is None:
            raise ValueError(f"unknown backtest parameter {k!r}; valid: {sorted(specs)}")
        default = spec.get("default")
        if isinstance(default, bool) or spec.get("type") == "checkbox":
            if not isinstance(v, bool):
                raise ValueError(f"{k} must be true/false")
        elif isinstance(default, int) and isinstance(v, (int, float)) and not isinstance(v, bool):
            if float(v) != int(v):
                raise ValueError(f"{k} must be an integer")
            v = int(v)
        elif isinstance(default, float) and isinstance(v, (int, float)) and not isinstance(v, bool):
            v = float(v)
        opts = spec.get("options")
        if opts and v not in opts:
            raise ValueError(f"{k} must be one of {opts}")
        lo, hi = spec.get("min"), spec.get("max")
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            if isinstance(lo, (int, float)) and v < lo - 1e-12:
                raise ValueError(f"{k}={v} is below its minimum {lo}")
            if isinstance(hi, (int, float)) and v > hi + 1e-12:
                raise ValueError(f"{k}={v} is above its maximum {hi}")
        out[k] = v
    return out


def _yearly(equity: pd.Series) -> pd.Series:
    """Calendar-year return (fraction) from an equity curve, keyed by year."""
    if equity is None or equity.empty:
        return pd.Series(dtype=float)
    yearly = equity.resample("YE").last()
    prev = pd.Series([equity.iloc[0]], index=[equity.index[0] - pd.Timedelta(days=1)])
    r = pd.concat([prev, yearly]).pct_change().dropna()
    r.index = [int(i.year) for i in r.index]
    return r


def _trades_table(trades: Optional[pd.DataFrame], extra: dict) -> dict:
    if trades is None or trades.empty:
        return {"columns": [], "rows": []}
    trades = trades.reset_index(drop=True)
    cols_lower = {str(c).lower(): c for c in trades.columns}
    order, headers = [], {}
    for item in (extra or {}).get("trade_columns") or []:
        try:
            f, h = item
        except (TypeError, ValueError):
            continue
        if f in trades.columns and f not in order:
            order.append(f)
            headers[str(f)] = str(h)
    for key in _TRADE_HEADERS:
        orig = cols_lower.get(key)
        if orig is not None and orig not in order and orig not in _TRADE_SKIP:
            order.append(orig)
    for orig in trades.columns:
        if orig not in order and orig not in _TRADE_SKIP:
            order.append(orig)
    for orig in order:
        headers.setdefault(str(orig), _TRADE_HEADERS.get(str(orig).lower(), str(orig).replace("_", " ").title()))
    formats = {str(c): _TRADE_FORMATS[str(c).lower()] for c in order if str(c).lower() in _TRADE_FORMATS}
    return table_from_df(trades[order], headers=headers, formats=formats)


def _safe_extra(extra: dict) -> tuple[dict, list[str]]:
    """The JSON-representable part of ``BacktestResult.extra``: Series → Series,
    DataFrames → Table (size-capped), plain data as is; anything else is dropped."""
    out, dropped = {}, []
    for k, v in (extra or {}).items():
        key = str(k)
        try:
            if isinstance(v, pd.DataFrame):
                if len(v) > _EXTRA_MAX_ROWS:
                    dropped.append(key)
                    continue
                out[key] = table_from_df(v, index=not isinstance(v.index, pd.RangeIndex))
            elif isinstance(v, pd.Series):
                if len(v) > _EXTRA_MAX_POINTS:
                    dropped.append(key)
                    continue
                out[key] = series(v, name=key)
            else:
                jv = to_jsonable(v, strict=True)
                if jv is DROP:
                    dropped.append(key)
                    continue
                out[key] = jv
        except Exception:
            dropped.append(key)
    return out, dropped


def backtest_job(ctx: JobContext, slug: str, ticker: str, from_date: str, to_date: str,
                 capital: float, params: dict) -> dict:
    from engine.strategy_backtest import LoaderBlocked, performance_warnings, run_backtest

    try:
        perf = run_backtest(slug, ticker, from_date, to_date, capital, params=params,
                            report_window=True, progress=ctx.progress)
    except LoaderBlocked as exc:
        raise JobError(exc.reason) from exc
    except (ValueError, NotImplementedError) as exc:
        raise JobError(str(exc) or type(exc).__name__) from exc
    ctx.progress(0.95, "building the result")
    result = perf["result"]
    equity, bench = perf["equity"], perf["bench_equity"]
    dd = equity / equity.cummax() - 1.0
    bench_dd = bench / bench.cummax() - 1.0
    ys, yb = _yearly(equity), _yearly(bench)
    years = sorted(set(ys.index) | set(yb.index))
    yearly = [{"year": y, "strategy": float(ys[y]) if y in ys.index else None,
               "benchmark": float(yb[y]) if y in yb.index else None} for y in years]
    extra = getattr(result, "extra", None) or {}
    safe_extra, dropped = _safe_extra(extra)
    warnings = performance_warnings(perf)
    return {
        "slug": slug, "ticker": ticker, "from": from_date, "to": to_date, "capital": float(capital),
        "params": perf["params"],
        "metrics": perf["metrics"], "bench_metrics": perf["bench_metrics"],
        "equity": series(equity, "equity"), "bench_equity": series(bench, "bench_equity"),
        "drawdown": series(dd, "drawdown"), "bench_drawdown": series(bench_dd, "bench_drawdown"),
        "yearly": yearly,
        "trades": _trades_table(perf["trades"], extra),
        "coverage": perf["coverage"], "span_days": perf["span_days"], "window_days": perf["window_days"],
        "warnings": warnings,
        "extra": safe_extra, "extra_dropped": dropped,
    }


# ── Live signal ───────────────────────────────────────────────────────────────

def _db_closes(ticker: str) -> pd.Series:
    from datetime import timedelta
    from db.client import get_engine, get_price_bars
    try:
        df = get_price_bars(get_engine(), ticker, date.today() - timedelta(days=3650), date.today())
    except Exception:
        return pd.Series(dtype=float)
    if df is None or df.empty:
        return pd.Series(dtype=float)
    s = pd.Series(pd.to_numeric(df["close"], errors="coerce").values, index=pd.to_datetime(df["date"])).dropna()
    return s[~s.index.duplicated(keep="last")].sort_index()


def signal(slug: str, ticker: Optional[str]) -> dict:
    from alan_trader.strategy_api.base import BaseStrategy
    meta = require(slug)
    strat = _strategy(slug)
    ticker = (ticker or meta.get("default_ticker") or "SPY").upper().strip()
    out = {"slug": slug, "ticker": ticker, "signal": None, "state": "", "price": None,
           "asof": None, "detail": "", "session": None}
    if _is_stub(strat):
        out["detail"] = "This strategy has no implementation registered."
        return out
    if _overrides(strat, "session_gate", BaseStrategy):
        try:
            blocked, reason = strat.session_gate(date.today())
            out["session"] = {"blocked": bool(blocked), "reason": str(reason or ""), "day": date.today().isoformat()}
        except Exception as exc:
            out["session"] = {"blocked": None, "reason": f"session gate failed: {exc}", "day": date.today().isoformat()}
    if not _overrides(strat, "current_signal", BaseStrategy):
        out["detail"] = "This strategy publishes no live signal."
        return out
    from alan_trader.strategy_api.timing_base import load_close
    close = load_close(ticker)              # the Signal & Alert tab's source
    out["price_source"] = "yfinance"
    if close is None or len(close) == 0:
        close = _db_closes(ticker)          # index symbols (NDX, VXN …) are stored, but not on yfinance by that name
        out["price_source"] = "db"
    if close is None or len(close) == 0:
        raise LookupError(f"No daily closes for {ticker} (yfinance returned nothing and none are stored).")
    sig = strat.current_signal(close)
    if not sig:
        out["detail"] = "The strategy returned no signal for this ticker."
        return out
    sig = dict(sig)
    out.update({k: sig.get(k, out.get(k)) for k in ("signal", "state", "price", "asof", "detail")})
    out["extra"] = to_jsonable({k: v for k, v in sig.items()
                                if k not in ("signal", "state", "price", "asof", "detail")}, strict=True)
    return to_jsonable(out)
