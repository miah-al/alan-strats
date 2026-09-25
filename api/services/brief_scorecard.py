"""
api/services/brief_scorecard.py — the shadow A/B of the morning brief, as pure arithmetic.

Ledger A is the paper condor as traded (every eligible day, untouched). The other lines are computed, never
booked: each closed ndx_0dte_condor trade's P&L times that day's multiplier —

  B  the brief's size_multiplier (GO 1, REDUCE 0.5, STAND_ASIDE 0)
  C  "skip scheduled macro days" (the calendar gate the model was told not to use): 0 on F1 days, else 1
  D  "skip when VIX > VIX3M": 0 when the brief's sheet had the curve inverted, else 1

Only trades on days with a brief count (the brief's decision is frozen before the entry, so the comparison is fair
on exactly those days). The random-skip percentile (ai_risk/report.md, section 6.5): B - A against the same statistic
under ``n_random`` random assignments of the brief's skip weights (1 - multiplier) to the same days; the percentile is
the share of random assignments that did no better than the brief, so 50 is chance and a high number means the brief
skipped worse days than chance would. Reported once there are at least ``MIN_TRADES`` trades.
"""
from __future__ import annotations

import datetime as _dt
from typing import Optional

import numpy as np

MIN_TRADES = 10
N_RANDOM = 5000
WORST_N = 5


def _mean(xs: list[float]) -> Optional[float]:
    return round(float(sum(xs) / len(xs)), 2) if xs else None


def scorecard(trades: list[dict], briefs: dict, n_random: int = N_RANDOM, seed: int = 20260925) -> dict:
    """``trades``: [{"date": date, "pnl": float}]; ``briefs``: {date: {"size_multiplier", "macro_today",
    "vix_inverted"}}. The endpoint's shape, plus the per-line differences and how many of A's worst days were skipped."""
    rows = []
    for t in trades:
        b = briefs.get(t["date"])
        if b is None:
            continue
        rows.append((float(t["pnl"]), float(b.get("size_multiplier") if b.get("size_multiplier") is not None else 1.0),
                     0.0 if b.get("macro_today") else 1.0, 0.0 if b.get("vix_inverted") else 1.0))
    n = len(rows)
    without = len(trades) - n
    if n == 0:
        return {"trades": 0, "a_pnl": 0.0, "b_pnl": 0.0, "c_pnl": 0.0, "d_pnl": 0.0, "skipped": 0, "skipped_mean": None,
                "kept_mean": None, "random_percentile": None, "trades_without_brief": without, "b_minus_a": 0.0,
                "c_minus_a": 0.0, "d_minus_a": 0.0, "worst_days_skipped": 0,
                "note": "No closed condor trade on a day with a brief yet." +
                        (f" {without} closed trade(s) predate the brief." if without else "")}
    pnl = np.array([r[0] for r in rows])
    mb, mc, md = (np.array([r[i] for r in rows]) for i in (1, 2, 3))
    a, b, c, d = (float(x) for x in (pnl.sum(), (pnl * mb).sum(), (pnl * mc).sum(), (pnl * md).sum()))
    w = 1.0 - mb
    skipped_idx = [i for i in range(n) if mb[i] < 1.0]
    kept_idx = [i for i in range(n) if mb[i] >= 1.0]
    skipped_mean = _mean([float(pnl[i]) for i in skipped_idx])
    kept_mean = _mean([float(pnl[i]) for i in kept_idx])
    worst = np.argsort(pnl)[:min(WORST_N, n)]
    worst_skipped = int(sum(1 for i in worst if mb[i] < 1.0))
    percentile = None
    if n >= MIN_TRADES and w.sum() > 0:
        rng = np.random.RandomState(seed)
        actual = -float((w * pnl).sum())                      # B - A
        sims = np.empty(n_random)
        for k in range(n_random):
            sims[k] = -float((rng.permutation(w) * pnl).sum())
        percentile = round(float((sims <= actual).mean() * 100.0), 1)
    if n < MIN_TRADES:
        note = f"{n} trade(s) with a brief; the random-skip test starts at {MIN_TRADES}."
    elif w.sum() == 0:
        note = "The brief has not reduced or skipped a day yet: B equals A."
    else:
        note = (f"B - A = {b - a:+,.0f} over {n} trades; {len(skipped_idx)} day(s) reduced or skipped; "
                f"random-skip percentile {percentile} (50 = chance, higher = the brief picked worse days than chance).")
    if without:
        note += f" {without} closed trade(s) predate the brief and are not counted."
    return {"trades": n, "a_pnl": round(a, 2), "b_pnl": round(b, 2), "c_pnl": round(c, 2), "d_pnl": round(d, 2),
            "skipped": len(skipped_idx), "skipped_mean": skipped_mean, "kept_mean": kept_mean,
            "random_percentile": percentile, "trades_without_brief": without,
            "b_minus_a": round(b - a, 2), "c_minus_a": round(c - a, 2), "d_minus_a": round(d - a, 2),
            "worst_days_skipped": worst_skipped, "note": note}


def condor_trades(strategy: str = "ndx_0dte_condor") -> list[dict]:
    """The paper ledger's closed trades for ``strategy`` as [{"date", "pnl", "trade_group_id"}] (read only)."""
    from api.services.paper import load
    _, closed, _ = load()
    out = []
    for r in closed or []:
        if str(r.get("Strategy") or "") != strategy:
            continue
        cd = r.get("Close Date") or r.get("Open Date")
        if cd is None:
            continue
        try:
            day = cd.date() if isinstance(cd, _dt.datetime) else (cd if isinstance(cd, _dt.date) else _dt.date.fromisoformat(str(cd)[:10]))
        except ValueError:
            continue
        out.append({"date": day, "pnl": float(r.get("P&L $") or 0.0), "trade_group_id": str(r.get("TradeGroupId"))})
    out.sort(key=lambda t: (t["date"], t["trade_group_id"]))
    return out
