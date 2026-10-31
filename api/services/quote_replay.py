"""
api/services/quote_replay.py — a strategy replayed on the NDXP bid/ask the service recorded (paper_state/quotes/), the
way its live runner would have traded it: the live session's own engine (paper.runner.PaperSession) on a
QuoteReplayProvider, with the strategy's declared live parameters. The most honest check there is, and it grows a day
at a time as the recorder runs.

  recorded_days()                    the days with recorded quotes
  replay(slug, days, overrides)      each day's P&L, trades and fills on the recorded quotes
  calibrate(slug, trades, fd, td, …) a backtest's P&L per recorded day in its window next to the replay's (the
                                     "Read with care" panel says how far the print-priced backtest is from real quotes)

A dry run: no ledger write, no broker call; logs and state go to paper_state/quote_replay/<slug>/. Used by the Backtest
tab's "Replay on real quotes", the backtest's calibration line, and scripts/quote_replay.py.
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Callable, Optional

import pandas as pd


def quotes_dir() -> Path:
    from paper.providers import QUOTES_DIR
    return Path(QUOTES_DIR)


def recorded_days(root: str = "NDXP", qdir: Optional[Path] = None) -> list[_dt.date]:
    d = (qdir or quotes_dir()) / root
    return sorted(_dt.date.fromisoformat(p.name[:10]) for p in d.glob("????-??-??.csv.gz"))


def live_instrument(slug: str) -> dict:
    from strategy_api import registry as R
    return R.get_strategy(slug).live_instrument() or {}


def replay_day(slug: str, day: _dt.date, run_params: dict, inst: dict, qdir: Optional[Path] = None, eng=None):
    """One day on the recorded quotes: the PaperSession's replay result (day_pnl, trades, fills, blocked, reason)."""
    from db.client import get_engine
    from paper.providers import QuoteReplayProvider
    from paper.runner import PaperSession
    out_dir = Path(__file__).resolve().parents[2] / "paper_state" / "quote_replay" / slug
    prov = QuoteReplayProvider(day, underlying=inst.get("underlying", "NDX"), root=inst.get("root", "NDXP"),
                               carry_min=int(run_params.get("carry_min", 30)), quotes_dir=str(qdir or quotes_dir()))
    res = PaperSession(slug, prov, eng or get_engine(), write_ledger=False, log_dir=out_dir, state_dir=out_dir,
                       params=run_params).run_replay(day)
    return res, prov


def replay(slug: str, days: Optional[list[_dt.date]] = None, overrides: Optional[dict] = None,
           progress: Optional[Callable[[Optional[float], Optional[str]], None]] = None) -> dict:
    """The strategy on every recorded day (or ``days``), with its live parameters then ``overrides``."""
    inst = live_instrument(slug)
    if not inst:
        raise ValueError(f"{slug} has no live session to replay (live_instrument is empty)")
    run_params = {**dict(inst.get("live_params") or {}), **(overrides or {})}
    days = days if days is not None else recorded_days(inst.get("root", "NDXP"))
    rows = []
    for i, day in enumerate(days):
        if progress:
            progress(i / max(1, len(days)), f"replaying {day} on the recorded quotes")
        res, prov = replay_day(slug, day, run_params, inst)
        rows.append({
            "day": day.isoformat(), "blocked": bool(res.blocked), "reason": res.reason if res.blocked else None,
            "pnl": None if res.blocked else float(res.day_pnl), "trades": len(res.trades),
            "quotes": prov.describe(),
            "fills": [{"at": f"{f.get('m', 0) // 60:02d}:{f.get('m', 0) % 60:02d}", "kind": f.get("kind"),
                       "direction": f.get("direction", ""), "strikes": f"{f.get('kl', 0):.0f}/{f.get('kh', 0):.0f}",
                       "units": f.get("units", f.get("lots", 1)), "price": f.get("px"), "reason": f.get("reason", "")}
                      for f in res.fills],
        })
    done = [r for r in rows if not r["blocked"]]
    return {"slug": slug, "params": run_params, "days": rows,
            "total": sum(r["pnl"] for r in done), "trades": sum(r["trades"] for r in done),
            "winning_days": sum(1 for r in done if r["pnl"] > 0), "replayed_days": len(done),
            "basis": "the live runner's engine on the recorded NDXP bid/ask (paper_state/quotes)"}


def _day_pnl(trades: pd.DataFrame) -> dict[str, tuple[float, int]]:
    """A backtest's trades as {day: (P&L, trades)} by entry date (or exit date); {} when it has no such columns."""
    if trades is None or trades.empty or "pnl" not in trades.columns:
        return {}
    col = next((c for c in ("entry_date", "exit_date", "date") if c in trades.columns), None)
    if col is None:
        return {}
    day = pd.to_datetime(trades[col], errors="coerce").dt.date.astype(str)
    g = trades.assign(_d=day).groupby("_d")["pnl"]
    return {d: (float(s), int(n)) for (d, s), (_d2, n) in zip(g.sum().items(), g.count().items())}


def calibrate(slug: str, trades: pd.DataFrame, fd: str, td: str, params: Optional[dict] = None) -> Optional[dict]:
    """The backtest's P&L on the recorded days inside [fd, td] next to the replay's on the same days, with the same
    parameters. None when the strategy has no live session; ``days`` empty when no recorded day is in the window."""
    try:
        inst = live_instrument(slug)
    except Exception:
        return None
    if not inst:
        return None
    lo, hi = _dt.date.fromisoformat(fd[:10]), _dt.date.fromisoformat(td[:10])
    recorded = recorded_days(inst.get("root", "NDXP"))
    days = [d for d in recorded if lo <= d <= hi]
    out = {"recorded": [d.isoformat() for d in recorded], "days": []}
    if not days:
        return out
    bt = _day_pnl(trades)
    rep = replay(slug, days, overrides=params)
    for r in rep["days"]:
        if r["blocked"]:
            continue
        b = bt.get(r["day"], (0.0, 0))
        out["days"].append({"day": r["day"], "backtest": b[0], "backtest_trades": b[1], "replay": r["pnl"],
                            "replay_trades": r["trades"]})
    return out
