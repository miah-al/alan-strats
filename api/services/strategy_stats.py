"""
api/services/strategy_stats.py — how each strategy has done on paper, next to what its backtest expects.

``stats(from, to)``: per strategy (the ledger's StrategyName; the service's own orders are "manual"
unless the order names a strategy) over the trades closed in the window: trades, wins, win rate, P&L,
average win / loss, profit factor, the maximum drawdown of its cumulative closed P&L, average days
held, and the positions still open. ``backtest_expectation`` is the CONSERVATIVE backtest of that
strategy: the latest ``app.BacktestRun`` row whose execution assumptions are conservative (legs priced
in the same minute, the calibrated spread, taker or maker fills -- ``execution_mode``), else the
checked-in baseline ``data/backtest_baselines.json`` (docs/research/conservative_rerun_2026-09-25.md),
else the latest stored run flagged ``"mode": "optimistic"`` so the page can say so. Before 2026-09-25
the expectation was whatever ran last, and for ndx_0dte_tasty that was an optimistic run (92% wins,
+$488 a trade) that paper could never match (the 16k trap, paper/providers.py).
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import os
from typing import Optional

import pandas as pd

from api.serialize import table_from_rows, to_jsonable
from api.services.db import require_db

logger = logging.getLogger("alan_trader.api.strategy_stats")

FIELDS = ["strategy", "strategy_label", "trades", "wins", "win_rate", "pnl", "avg_win", "avg_loss", "profit_factor",
          "max_drawdown", "avg_days_held", "open_positions", "bt_win_rate", "bt_avg_pnl", "bt_trades", "bt_ran", "bt_mode", "bt_execution"]
_HEADERS = {"strategy": "Strategy (slug)", "strategy_label": "Strategy", "trades": "Trades", "wins": "Wins",
            "win_rate": "Win Rate", "pnl": "P&L", "avg_win": "Avg Win", "avg_loss": "Avg Loss",
            "profit_factor": "Profit Factor", "max_drawdown": "Max Drawdown", "avg_days_held": "Avg Days Held",
            "open_positions": "Open", "bt_win_rate": "Backtest Win Rate", "bt_avg_pnl": "Backtest Avg P&L",
            "bt_trades": "Backtest Trades", "bt_ran": "Backtest Run", "bt_mode": "Backtest Mode", "bt_execution": "Backtest Execution"}
_FORMATS = {"win_rate": "ratio", "pnl": "money", "avg_win": "money", "avg_loss": "money", "max_drawdown": "money",
            "bt_win_rate": "ratio", "bt_avg_pnl": "money", "trades": "int", "wins": "int", "open_positions": "int",
            "bt_trades": "int"}
_TYPES = {"strategy": "string", "strategy_label": "string", "trades": "integer", "wins": "integer",
          "open_positions": "integer", "bt_trades": "integer", "bt_ran": "datetime", "bt_mode": "string", "bt_execution": "string"}

#: the checked-in conservative baselines (written by docs/research/conservative_rerun.py)
BASELINES_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                              "data", "backtest_baselines.json")
#: the key under which a stored run's ParamsJson carries its execution mode (first, so a truncated JSON keeps it)
MODE_KEY = "_execution_mode"
CONSERVATIVE, OPTIMISTIC = "conservative", "optimistic"


# ── which side of the trap a run sits on ──────────────────────────────────────

def execution_mode(params: Optional[dict]) -> str:
    """'conservative' or 'optimistic', read from a backtest's parameters. Conservative means: no print older than
    this minute prices a fill or a mark (stale_min = carry_min = 0), the spread around the print is the calibrated
    live one (or a flat bracket no narrower than the measured 1.2-point crossing cost), fills are taker or maker,
    and no favourable bar extreme fills a resting order. A strategy without any of those knobs has nothing to be
    optimistic about here and counts as conservative."""
    p = params or {}
    if p.get(MODE_KEY) in (CONSERVATIVE, OPTIMISTIC):
        return str(p[MODE_KEY])
    try:
        from paper.spread_model import MEASURED_CROSSING_PTS
    except Exception:  # pragma: no cover - the platform package always has it
        MEASURED_CROSSING_PTS = 1.2
    def num(k, default=0.0):
        try:
            return float(p.get(k, default) or 0.0)
        except (TypeError, ValueError):
            return default
    if num("stale_min") > 0 or num("carry_min") > 0:
        return OPTIMISTIC
    if str(p.get("spread_model", "live")).lower() == "flat" and num("half_spread_pts") < MEASURED_CROSSING_PTS:
        return OPTIMISTIC
    if str(p.get("fill_model", "taker")).lower() == "mid":
        return OPTIMISTIC
    if p.get("use_bar_extremes") in (True, 1, 1.0, "1", "true", "True"):
        return OPTIMISTIC
    return CONSERVATIVE


# ── the numbers (pure) ────────────────────────────────────────────────────────

def summarize(trades: pd.DataFrame) -> dict:
    """``trades``: columns pnl, opened, closed (dates). Win rate is a fraction; max_drawdown is the deepest
    fall of cumulative closed P&L from its running peak (dollars, <= 0, the first peak being zero)."""
    n = int(len(trades))
    if n == 0:
        return {"trades": 0, "wins": 0, "win_rate": None, "pnl": 0.0, "avg_win": None, "avg_loss": None,
                "profit_factor": None, "max_drawdown": 0.0, "avg_days_held": None}
    pnl = pd.to_numeric(trades["pnl"], errors="coerce").fillna(0.0)
    wins, losses = pnl[pnl > 0], pnl[pnl < 0]
    order = trades.assign(pnl=pnl).sort_values(["closed", "opened"], kind="stable")
    cum = order["pnl"].cumsum()
    peak = pd.concat([pd.Series([0.0]), cum]).cummax().iloc[1:]
    dd = float((cum.values - peak.values).min()) if len(cum) else 0.0
    held = (pd.to_datetime(trades["closed"]) - pd.to_datetime(trades["opened"])).dt.days
    return {"trades": n, "wins": int(len(wins)), "win_rate": round(len(wins) / n, 4), "pnl": round(float(pnl.sum()), 2),
            "avg_win": round(float(wins.mean()), 2) if len(wins) else None,
            "avg_loss": round(float(losses.mean()), 2) if len(losses) else None,
            "profit_factor": round(float(wins.sum() / -losses.sum()), 3) if len(losses) and losses.sum() else None,
            "max_drawdown": round(min(dd, 0.0), 2),
            "avg_days_held": round(float(held.mean()), 2) if held.notna().any() else None}


# ── stored backtests ──────────────────────────────────────────────────────────

def store_backtests() -> bool:
    return os.environ.get("ALAN_TRADER_STORE_BACKTESTS", "1").strip().lower() not in ("0", "false", "no", "off")


def record_backtest(slug: str, ticker: str, from_date: str, to_date: str, capital: float, params: dict,
                    metrics: dict, trades: Optional[pd.DataFrame], mode: Optional[str] = None) -> None:
    """One app.BacktestRun row for a finished backtest job (never raises). The run's execution mode
    (``execution_mode(params)`` unless given) is stored first in ParamsJson so the expectation can prefer
    conservative runs."""
    if not store_backtests():
        return
    from sqlalchemy import text
    from api.services import appdb
    try:
        pnl = pd.to_numeric(trades["pnl"], errors="coerce").dropna() if trades is not None and "pnl" in trades.columns \
            else pd.Series(dtype=float)
        wr = metrics.get("win_rate_pct")
        mode = mode or execution_mode(params)
        pj = {MODE_KEY: mode, **{k: v for k, v in to_jsonable(params or {}).items() if k != MODE_KEY}}
        appdb.ensure("BacktestRun")
        with require_db().begin() as c:
            c.execute(text("""
                INSERT INTO app.BacktestRun (Slug, Ticker, FromDate, ToDate, Capital, ParamsJson, Trades, WinRate,
                    AvgPnl, AvgWin, AvgLoss, ProfitFactor, TotalReturnPct, Sharpe, MaxDrawdownPct)
                VALUES (:slug, :t, :f, :to, :cap, :p, :n, :wr, :avg, :aw, :al, :pf, :tr, :sh, :dd)"""),
                {"slug": slug, "t": ticker, "f": from_date, "to": to_date, "cap": float(capital),
                 "p": json.dumps(pj)[:4000], "n": int(len(pnl)),
                 "wr": (float(wr) / 100.0) if wr is not None else None,
                 "avg": float(pnl.mean()) if len(pnl) else None, "aw": _f(metrics.get("avg_win")),
                 "al": _f(metrics.get("avg_loss")), "pf": _f(metrics.get("profit_factor")),
                 "tr": _f(metrics.get("total_return_pct")), "sh": _f(metrics.get("sharpe")),
                 "dd": _f(metrics.get("max_drawdown_pct"))})
    except Exception as exc:  # noqa: BLE001 — a backtest result is never lost for want of a row
        logger.warning("backtest of %s not stored: %s", slug, exc)


def _f(v) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and f not in (float("inf"), float("-inf")) else None


def stored_backtests(limit: int = 400) -> list[dict]:
    """The most recent stored runs, newest first, each with its execution mode (from ParamsJson; a row written
    before modes were recorded is judged by its parameters, so an old optimistic run is not mistaken for a baseline)."""
    from sqlalchemy import text
    from api.services import appdb
    from api.services.orders import _iso_utc
    if not appdb.exists("BacktestRun"):
        return []
    with require_db().connect() as c:
        rows = c.execute(text(f"""
            SELECT TOP {int(limit)} b.Slug, b.Ticker, b.FromDate, b.ToDate, b.Capital, b.Trades, b.WinRate, b.AvgPnl,
                   b.AvgWin, b.AvgLoss, b.ProfitFactor, b.TotalReturnPct, b.Sharpe, b.MaxDrawdownPct, b.RunAt, b.ParamsJson
            FROM app.BacktestRun b ORDER BY b.RunId DESC""")).fetchall()
    out = []
    for r in rows:
        try:
            params = json.loads(r[15]) if r[15] else {}
        except (TypeError, ValueError):
            params = {}
        out.append({"slug": r[0], "ticker": r[1], "from": r[2], "to": r[3], "capital": r[4], "trades": r[5], "win_rate": r[6],
                    "avg_pnl": r[7], "avg_win": r[8], "avg_loss": r[9], "profit_factor": r[10],
                    "total_return_pct": r[11], "sharpe": r[12], "max_drawdown_pct": r[13], "ran": _iso_utc(r[14]),
                    "mode": (execution_mode(params) if isinstance(params, dict) and MODE_KEY in params else OPTIMISTIC),
                    "source": "db"})
    return out


def file_baselines(path: Optional[str] = None) -> dict[str, dict]:
    """``data/backtest_baselines.json``: {slug: expectation}, the conservative re-run checked in with the code."""
    p = path or BASELINES_FILE
    try:
        with open(p, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return {}
    out = {}
    for slug, b in (raw.get("strategies") if isinstance(raw, dict) and "strategies" in raw else raw or {}).items():
        if isinstance(b, dict):
            out[str(slug)] = {**b, "mode": b.get("mode", CONSERVATIVE), "source": "file"}
    return out


def latest_backtests() -> dict[str, dict]:
    """Per strategy, the expectation paper is read against: the newest CONSERVATIVE stored run; else the checked-in
    baseline; else the newest stored run of any kind, flagged optimistic."""
    rows = stored_backtests()
    files = file_baselines()
    out: dict[str, dict] = {}
    fallback: dict[str, dict] = {}
    for r in rows:                                          # newest first
        slug = r["slug"]
        if r["mode"] == CONSERVATIVE and slug not in out:
            out[slug] = {k: v for k, v in r.items() if k != "slug"}
        elif slug not in fallback:
            fallback[slug] = {k: v for k, v in r.items() if k != "slug"}
    for slug, b in files.items():
        out.setdefault(slug, b)
    for slug, b in fallback.items():
        out.setdefault(slug, b)
    return out


# ── the endpoint ──────────────────────────────────────────────────────────────

def stats(from_date: Optional[str] = None, to_date: Optional[str] = None) -> dict:
    from api.services import paper as P
    fd = _dt.date.fromisoformat(from_date[:10]) if from_date else None
    td = _dt.date.fromisoformat(to_date[:10]) if to_date else None
    if fd and td and fd > td:
        raise ValueError("from must not be after to")
    open_groups, closed_rows, _txns = P.load()
    labels = P._labels()
    closed = pd.DataFrame([{"strategy": str(r.get("Strategy") or "manual") or "manual", "pnl": r.get("P&L $"),
                            "opened": pd.to_datetime(r.get("Open Date")), "closed": pd.to_datetime(r.get("Close Date"))}
                           for r in closed_rows or []], columns=["strategy", "pnl", "opened", "closed"])
    if not closed.empty:
        cd = closed["closed"].dt.date
        if fd:
            closed = closed[cd >= fd]
            cd = closed["closed"].dt.date
        if td:
            closed = closed[cd <= td]
    opens: dict[str, int] = {}
    for grp in open_groups.values():
        s = str(grp["StrategyName"].iloc[0]) if not grp.empty else "manual"
        opens[s or "manual"] = opens.get(s or "manual", 0) + 1
    try:
        bt = latest_backtests()
    except Exception as exc:
        logger.warning("stored backtests unavailable: %s", exc)
        bt = {}
    # A strategy with a checked-in baseline is listed before its first paper trade, so its card shows what to expect.
    names = sorted(set(closed["strategy"]) | set(opens) | set(file_baselines()), key=lambda s: (s == "manual", s))
    out = []
    for s in names:
        row = {"strategy": s, "strategy_label": labels.get(s, "Manual" if s == "manual" else s),
               **summarize(closed[closed["strategy"] == s]), "open_positions": opens.get(s, 0)}
        b = bt.get(s)
        row["backtest_expectation"] = b
        row.update(bt_win_rate=(b or {}).get("win_rate"), bt_avg_pnl=(b or {}).get("avg_pnl"),
                   bt_trades=(b or {}).get("trades"), bt_ran=(b or {}).get("ran"), bt_mode=(b or {}).get("mode"),
                   bt_execution=(b or {}).get("execution"))
        out.append(row)
    total = {"strategy": "all", **summarize(closed), "open_positions": sum(opens.values())}
    table = table_from_rows([{f: r.get(f) for f in FIELDS} for r in out], field_order=FIELDS, headers=_HEADERS,
                            formats=_FORMATS, types=_TYPES)
    return to_jsonable({"from": fd, "to": td, "strategies": out, "total": total, "table": table,
                        "account_id": P.account_id()})
