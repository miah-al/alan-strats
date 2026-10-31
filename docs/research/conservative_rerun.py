"""The two live paper strategies re-run under CONSERVATIVE execution (2026-09-25), next to the optimistic upper bound.

    set ALAN_TRADER_STRATEGIES_DIR=<the strategies checkout with the conservative ndx_0dte_tasty>
    set ALAN_TRADER_STRATEGY_OVERLAYS=<...>\strategies\ndx_gamma_walls   (the gamma-walls/conservative worktree)
    python docs/research/conservative_rerun.py [--since 2024-10-01] [--out docs/research/conservative_rerun_2026-09-25]
                                               [--skip-tasty] [--skip-walls] [--no-baselines]

Why. The replay of ndx_0dte_tasty for 2026-09-24 showed +$16,384 on 24 trades; live paper made -$1,117 on 2. The replay
had priced each vertical from one leg's print and the other leg's print up to 30 minutes older, at a flat half point of
spread (paper/providers.py, "the 16k trap"). Every backtest and replay on the platform now defaults to: both legs printed
in the same minute (stale_min = carry_min = 0), the calibrated live spread (paper/spread_model.py), taker or maker fills.
This script re-runs the evidence behind the two strategies under those defaults.

What runs:
  ndx_0dte_tasty v2.2 -- the parameters the live runner logged on 2026-09-24 (its runner.log) -- over every stored
    session (mkt.OptionMinuteSession), four ways: conservative taker (the headline), conservative maker, a reference at
    carry 0 with a flat 1.2-point bracket (the crossing cost measured on multi-leg prints), and the optimistic upper
    bound (legs carried 30 minutes, flat 0.5, taker: the promoted headline until today).
  ndx_gamma_walls -- its params.py defaults (map B, B50, hold to settlement, 11:00-15:00) -- over the same sessions,
    split like docs/research/gex_wall_fade_2026-09.md (in-sample to 2025-09-30, out-of-sample after): conservative
    taker (the call spread sold at its bid), conservative maker (rested at the mid, filled only through it), and the
    optimistic upper bound (mid + 1.5, legs carried).
Per run and per split: total, trades, P&L per trade, per-trade win rate, WIN-DAY rate, worst day, max drawdown.

Writes <out>.json, <out>.md (the tables; the prose is written by hand around them) and, unless --no-baselines,
data/backtest_baselines.json -- the conservative taker run per strategy, which strategy_stats serves as the Performance
page's expectation until a conservative app.BacktestRun row exists (scripts/store_conservative_baseline.py).

Read only: every query is a SELECT and the research guard refuses anything else. Chunked by month.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
for p in (str(ROOT), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

IS_END = _dt.date(2025, 9, 30)                 # the wall study's split; the tasty research used 2025-10-01 as the first OOS day
LEAD_WINDOW = (_dt.date(2026, 7, 27), _dt.date(2026, 9, 23))   # the 38 days the trap was measured over
TRAP_DAY = _dt.date(2026, 9, 24)
CAPITAL = 30_000.0                              # the owner's account; drawdown is read against it
EARLY_CLOSE_2024_26 = {_dt.date(2024, 11, 29), _dt.date(2024, 12, 24), _dt.date(2025, 7, 3), _dt.date(2025, 11, 28),
                       _dt.date(2025, 12, 24), _dt.date(2026, 7, 2)}

#: ndx_0dte_tasty v2.2 as the live runner logged it on 2026-09-24 (runner.log), without the execution settings
V22_LIVE = {"add_trigger_pts": 10.0, "ai_gate": "shadow", "bad_day_loss": 5000.0, "commission_per_leg": 1.0,
            "counter_trend": False, "daily_loss_cap": 15000.0, "daily_stop_cap": 2, "default_vol": 0.22, "entry_end": "14:00",
            "entry_start": "11:00", "entry_ttl_min": 2, "fees_per_round_trip": 1.5, "flatten": "15:50", "hold_to_settlement": True,
            "itm_offset": 24.0, "lookback_min": 30, "lots": 1, "max_adds": 2, "max_hold_min": 60, "max_reentries": 3, "max_units": 1,
            "maxhold_ends_day": True, "min_prior_move": 15.0, "min_vxn_prev": 20.0, "pricing": "market", "reentry_discount": 5.0,
            "reentry_window_min": 15, "risk_free": 0.04, "scratch_after_min": 0, "scratch_target_pts": 0.0, "skew_slope": 0.15,
            "skip_kinds": "", "slippage_pts": 0.0, "stop_pts": 60.0, "strike_step": 25.0, "taker_entry": False, "target_pts": 5.0,
            "use_bar_extremes": False, "weekly_stop_days": 3, "width": 50.0}

TASTY_RUNS = [
    ("conservative taker", "CONSERVATIVE: legs same minute, live spread, taker (cross to the far side)",
     {"stale_min": 0, "carry_min": 0, "spread_model": "live", "fill_model": "taker"}),
    ("conservative maker", "CONSERVATIVE: legs same minute, live spread, maker (rest; fill only through the limit)",
     {"stale_min": 0, "carry_min": 0, "spread_model": "live", "fill_model": "maker"}),
    ("reference: carry 0, crossing cost 1.2", "REFERENCE: legs same minute, a flat 1.2-pt bracket (the measured multi-leg crossing cost), taker",
     {"stale_min": 0, "carry_min": 0, "spread_model": "flat", "half_spread_pts": 1.2, "fill_model": "taker"}),
    ("optimistic (upper bound)", "OPTIMISTIC: legs carried 30 min, flat 0.5, taker -- the pre-2026-09-25 headline",
     {"stale_min": 5, "carry_min": 30, "spread_model": "flat", "half_spread_pts": 0.5, "fill_model": "taker"}),
]
WALLS_RUNS = [
    ("conservative taker", "CONSERVATIVE: legs same minute, live spread, the call spread sold at its bid",
     {"stale_min": 0, "carry_min": 0, "fill_model": "taker"}, {"half_spread": None, "carry_min": 0}),
    ("conservative maker", "CONSERVATIVE: legs same minute, live spread, rested at the mid and filled only through it",
     {"stale_min": 0, "carry_min": 0, "fill_model": "maker"}, {"half_spread": None, "carry_min": 0}),
    ("optimistic (upper bound)", "OPTIMISTIC: legs carried 30 min, flat 0.5, filled at the mid + 1.5 -- the study's middle case",
     {"stale_min": 5, "carry_min": 30, "fill_model": "mid", "entry_slippage_pts": 1.5}, {"half_spread": 0.5, "carry_min": 30}),
]


# ── data (chunked, read only) ─────────────────────────────────────────────────

def month_chunks(since: _dt.date, until: _dt.date):
    d = since.replace(day=1)
    while d <= until:
        nxt = (d.replace(day=28) + _dt.timedelta(days=4)).replace(day=1)
        yield max(d, since), min(nxt - _dt.timedelta(days=1), until)
        d = nxt


def load(since: _dt.date, until: _dt.date, log):
    from db.client import get_engine, get_minute_bars, get_option_minute_bars, get_option_minute_sessions
    eng = get_engine()
    sessions = get_option_minute_sessions(eng, "NDX")
    days = sorted(d for d in set(sessions["session"]) if since <= d <= until)
    bars, prints = [], []
    for a, b in month_chunks(since, until):
        t0 = time.time()
        mb = get_minute_bars(eng, "NDX", a, b)
        ob = get_option_minute_bars(eng, "NDX", a, b)
        bars.append(mb); prints.append(ob)
        log(f"  {a:%Y-%m}: {len(mb):,} NDX bars, {len(ob):,} prints ({time.time() - t0:.1f}s)")
    bars = pd.concat(bars, ignore_index=True); prints = pd.concat(prints, ignore_index=True)
    bars["ts"] = pd.to_datetime(bars["ts"]); prints["ts"] = pd.to_datetime(prints["ts"])
    prints = prints[pd.to_datetime(prints["expiry"]).dt.date == prints["ts"].dt.date]      # same-day expiries only
    return eng, days, bars.sort_values("ts").reset_index(drop=True), prints.sort_values("ts").reset_index(drop=True)


# ── metrics ───────────────────────────────────────────────────────────────────

def metrics(day_pnl: pd.Series, n_trades: int, trade_pnl: pd.Series) -> dict:
    """``day_pnl``: P&L per session (0 for sessions without a fill), indexed by date."""
    traded = day_pnl[day_pnl != 0]
    cum = day_pnl.cumsum()
    peak = pd.concat([pd.Series([0.0]), cum]).cummax().iloc[1:]
    dd = float((cum.values - peak.values).min()) if len(cum) else 0.0
    wins = trade_pnl[trade_pnl > 0]; losses = trade_pnl[trade_pnl < 0]
    daily_ret = day_pnl / CAPITAL
    sharpe = float(daily_ret.mean() / daily_ret.std() * math.sqrt(252)) if len(day_pnl) > 2 and daily_ret.std() > 0 else None
    return {"sessions": int(len(day_pnl)), "days_traded": int(len(traded)), "trades": int(n_trades),
            "total": round(float(day_pnl.sum()), 0),
            "per_trade": round(float(trade_pnl.mean()), 0) if n_trades else None,
            "win_rate": round(float((trade_pnl > 0).mean()), 3) if n_trades else None,
            "win_day_rate": round(float((traded > 0).mean()), 3) if len(traded) else None,
            "per_day_traded": round(float(traded.mean()), 0) if len(traded) else None,
            "worst_day": round(float(day_pnl.min()), 0) if len(day_pnl) else None,
            "best_day": round(float(day_pnl.max()), 0) if len(day_pnl) else None,
            "max_drawdown": round(min(dd, 0.0), 0),
            "avg_win": round(float(wins.mean()), 0) if len(wins) else None,
            "avg_loss": round(float(losses.mean()), 0) if len(losses) else None,
            "profit_factor": round(float(wins.sum() / -losses.sum()), 2) if len(losses) and losses.sum() else None,
            "sharpe": round(sharpe, 2) if sharpe is not None else None}


SPLITS = {"all": lambda d: True, "in_sample": lambda d: d <= IS_END, "out_of_sample": lambda d: d > IS_END,
          "last_38_days": lambda d: LEAD_WINDOW[0] <= d <= LEAD_WINDOW[1], "trap_day_2026_09_24": lambda d: d == TRAP_DAY}


def by_split(day_pnl: pd.Series, trades: pd.DataFrame) -> dict:
    out = {}
    tdays = pd.to_datetime(trades["entry_date"]).dt.date if len(trades) else pd.Series(dtype=object)
    for name, keep in SPLITS.items():
        idx = [d for d in day_pnl.index if keep(d)]
        if not idx:
            continue
        mask = tdays.map(keep) if len(trades) else pd.Series(dtype=bool)
        tp = trades.loc[mask.values, "pnl"] if len(trades) else pd.Series(dtype=float)
        out[name] = {"from": str(idx[0]), "to": str(idx[-1]), **metrics(day_pnl.loc[idx], int(len(tp)), pd.to_numeric(tp))}
    return out


# ── ndx_0dte_tasty ────────────────────────────────────────────────────────────

def price_index(bars: pd.DataFrame, days: list) -> pd.DataFrame:
    sub = bars[bars.ts.dt.date.isin(set(days))]
    g = sub.groupby(sub.ts.dt.date)
    df = pd.DataFrame({"open": g.open.first(), "high": g.high.max(), "low": g.low.min(), "close": g.close.last(), "volume": 1.0})
    df.index = pd.to_datetime(df.index)
    return df


def run_tasty(days, bars, prints, log) -> dict:
    from alan_trader_strategies.strategies.ndx_0dte_tasty import calendar as cal
    from alan_trader_strategies.strategies.ndx_0dte_tasty.strategy import Ndx0dteTastyStrategy, load_vxn, execution_mode
    from alan_trader_strategies.strategies.ndx_0dte_tasty.params import TastyParams
    vxn = load_vxn(); events = cal.load_events()
    b = bars.copy(); b["bar_min"] = 1
    px = price_index(b, days)
    out = {"strategy": "ndx_0dte_tasty", "params": V22_LIVE, "runs": {}}
    for name, label, kw in TASTY_RUNS:
        t0 = time.time()
        p = TastyParams.from_kwargs(**V22_LIVE, **kw)
        r = Ndx0dteTastyStrategy().backtest(px, {"ticker": "NDX"}, CAPITAL, bars_override=b, vxn_override=vxn,
                                            events_override=events, option_bars_override=prints, **V22_LIVE, **kw)
        eq = r.equity_curve                                    # anchored at the starting capital one day before the first session
        day_pnl = pd.Series(eq.diff().iloc[1:].values, index=[pd.Timestamp(t).date() for t in eq.index[1:]]).sort_index()
        trades = r.trades if r.trades is not None else pd.DataFrame(columns=["entry_date", "pnl"])
        out["runs"][name] = {"label": label, "params": kw, "execution": execution_mode(p), "note": r.extra.get("note"),
                             "splits": by_split(day_pnl, trades), "trades": len(trades),
                             "trap_day_trades": trades[pd.to_datetime(trades["entry_date"]).dt.date == TRAP_DAY][
                                 ["entry_time", "exit_time", "direction", "k_low", "k_high", "units", "entry_px", "exit_px", "exit_reason", "pnl"]
                             ].to_dict("records") if len(trades) else []}
        a = out["runs"][name]["splits"]["all"]
        log(f"  ndx_0dte_tasty {name}: {a['total']:+,.0f} on {a['trades']} trades, {a['days_traded']} days, "
            f"per trade {a['per_trade'] or 0:+,.0f}, win-day {a['win_day_rate']}, worst {a['worst_day']:+,.0f}, "
            f"max DD {a['max_drawdown']:,.0f} ({time.time() - t0:.0f}s)")
    return out


# ── ndx_gamma_walls ───────────────────────────────────────────────────────────

class FrameVolume:
    """wallmap.DbVolume from a frame of one day's prints (right, strike, ts, volume): cumulative same-day volume."""

    def __init__(self, day: _dt.date, prints: pd.DataFrame):
        from alan_trader_strategies.strategies.ndx_gamma_walls.wallmap import N_MIN, SESSION_OPEN_MIN
        self.day = day
        ks = sorted(set(prints["strike"].astype(float)))
        self.kix = {k: j for j, k in enumerate(ks)}
        self.ks = ks
        self.cum = {True: np.zeros((N_MIN, len(ks))), False: np.zeros((N_MIN, len(ks)))}
        ts = pd.to_datetime(prints["ts"])
        i = (ts.dt.hour * 60 + ts.dt.minute - SESSION_OPEN_MIN).to_numpy()
        is_call = prints["right"].astype(str).str.upper().str.startswith("C").to_numpy()
        vol = pd.to_numeric(prints["volume"], errors="coerce").fillna(0.0).to_numpy(float)
        kj = prints["strike"].astype(float).map(self.kix).to_numpy()
        ok = (i >= 0) & (i < N_MIN)
        for c in (True, False):
            m = ok & (is_call == c)
            np.add.at(self.cum[c], (i[m], kj[m]), vol[m])
        for c in (True, False):
            self.cum[c] = np.cumsum(self.cum[c], axis=0)
        self._n = N_MIN

    def volumes(self, i: int, strikes: list) -> dict:
        if i < 0 or not self.ks:
            return {}
        i = min(i, self._n - 1)
        return {k: (float(self.cum[True][i, self.kix[k]]), float(self.cum[False][i, self.kix[k]])) for k in strikes if k in self.kix}


def run_walls(days, bars, prints, log) -> dict:
    from paper.providers import ReplayProvider
    from alan_trader_strategies.strategies.ndx_gamma_walls.live import SessionEngine
    from alan_trader_strategies.strategies.ndx_gamma_walls.params import WallsParams
    from alan_trader_strategies.strategies.ndx_0dte_tasty.strategy import load_vxn
    vxn = load_vxn()                                          # decimal, by date: the prior session's close is the map's vol
    vdates = np.array(sorted(vxn.index))
    by_day_b = {d: g for d, g in bars.groupby(bars.ts.dt.date)}
    by_day_p = {d: g for d, g in prints.groupby(prints.ts.dt.date)}
    out = {"strategy": "ndx_gamma_walls", "params": WallsParams().as_dict(), "runs": {}}
    for name, label, kw, pkw in WALLS_RUNS:
        t0 = time.time()
        p = WallsParams.from_kwargs(**kw)
        day_pnl, trades, signals = {}, [], 0
        for d in days:
            b = by_day_b.get(d); o = by_day_p.get(d)
            if b is None or len(b) < 300 or o is None or len(o) == 0 or d in EARLY_CLOSE_2024_26 or d.weekday() >= 5:
                continue
            k = int(np.searchsorted(vdates, d))
            sigma = float(vxn.loc[vdates[k - 1]]) if k > 0 else None
            if sigma is None:
                continue
            prov = ReplayProvider.from_frames("NDX", d, b, o, **pkw)
            src = FrameVolume(d, o)
            e = SessionEngine(p, d, source=src, sigma=sigma)
            qfn = lambda S, kl, kh, kind, minute, _prov=prov: _prov.quote_vertical(kind, kl, kh, minute, S)
            n = len(b)
            for i, row in enumerate(b.itertuples(index=False)):
                minute = row.ts.hour * 60 + row.ts.minute + 1
                e.on_bar(minute, float(row.close), qfn, is_last=(i == n - 1), high=float(row.high), low=float(row.low))
            day_pnl[d] = float(e.day_pnl)
            signals += sum(1 for s in e.signals if s.get("taken"))
            for t in e.trades:
                trades.append({**t, "entry_date": pd.Timestamp(d)})
        dp = pd.Series(day_pnl).sort_index()
        tr = pd.DataFrame(trades) if trades else pd.DataFrame(columns=["entry_date", "pnl"])
        out["runs"][name] = {"label": label, "params": kw, "provider": pkw, "execution": ("conservative" if pkw["carry_min"] == 0 and pkw["half_spread"] is None else "optimistic"),
                             "signals_taken": signals, "splits": by_split(dp, tr), "trades": len(tr)}
        a = out["runs"][name]["splits"]["all"]
        log(f"  ndx_gamma_walls {name}: {a['total']:+,.0f} on {a['trades']} trades ({signals} signals), per trade {a['per_trade'] or 0:+,.0f}, "
            f"win-day {a['win_day_rate']}, worst {a['worst_day']:+,.0f}, max DD {a['max_drawdown']:,.0f} ({time.time() - t0:.0f}s)")
    return out


# ── output ────────────────────────────────────────────────────────────────────

def fmt(v, money=True):
    if v is None:
        return "-"
    if isinstance(v, float) and not money:
        return f"{v:.0%}"
    return f"{v:+,.0f}" if money else str(v)


def table(res: dict, split: str) -> str:
    rows = ["| run | total | trades | per trade | win rate | win-day rate | days traded | worst day | max DD | PF |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    for name, r in res["runs"].items():
        s = r["splits"].get(split)
        if not s:
            continue
        head = f"**{name}**" if name.startswith("conservative taker") else name
        rows.append(f"| {head} | {fmt(s['total'])} | {s['trades']} | {fmt(s['per_trade'])} | {fmt(s['win_rate'], False)} | "
                    f"{fmt(s['win_day_rate'], False)} | {s['days_traded']} / {s['sessions']} | {fmt(s['worst_day'])} | "
                    f"{fmt(s['max_drawdown'])} | {s['profit_factor'] if s['profit_factor'] is not None else '-'} |")
    return "\n".join(rows)


def markdown(res: dict) -> str:
    out = ["# The two live paper strategies under conservative execution (2026-09-25)", "",
           "<!-- tables generated by docs/research/conservative_rerun.py; the prose around them is written by hand -->", ""]
    for key in ("ndx_0dte_tasty", "ndx_gamma_walls"):
        r = res.get(key)
        if not r:
            continue
        out += [f"## {key}", ""]
        for name, run in r["runs"].items():
            out.append(f"- **{name}**: {run['label']}")
        out.append("")
        for split, title in (("all", "Every stored session"), ("in_sample", "In-sample (to 2025-09-30)"),
                             ("out_of_sample", "Out-of-sample (from 2025-10-01)"), ("last_38_days", "The 38 days the trap was measured over (2026-07-27 .. 09-23)"),
                             ("trap_day_2026_09_24", "2026-09-24, the trap day (live paper: -$1,117 on 2 trades)")):
            any_split = any(split in run["splits"] for run in r["runs"].values())
            if not any_split:
                continue
            first = next(run["splits"][split] for run in r["runs"].values() if split in run["splits"])
            out += [f"### {title}: {first['from']} .. {first['to']}, {first['sessions']} sessions", "", table(r, split), ""]
    return "\n".join(out)


def baselines(res: dict) -> dict:
    ran = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = {"note": "Conservative re-run of 2026-09-25 (docs/research/conservative_rerun_2026-09-25.md): the expectation the "
                   "Performance page reads paper against until a conservative app.BacktestRun row exists.", "strategies": {}}
    for key, r in res.items():
        if not isinstance(r, dict) or "runs" not in r:
            continue
        run = r["runs"].get("conservative taker")
        if not run:
            continue
        s = run["splits"]["all"]
        alt = {}
        for nm, rr in r["runs"].items():
            a = rr["splits"]["all"]
            alt[nm] = {"label": rr["label"], "trades": a["trades"], "avg_pnl": a["per_trade"], "win_rate": a["win_rate"],
                       "win_day_rate": a["win_day_rate"], "total": a["total"], "worst_day": a["worst_day"], "max_drawdown": a["max_drawdown"]}
        out["strategies"][key] = {"ticker": "NDX", "from": s["from"], "to": s["to"], "capital": CAPITAL, "trades": s["trades"],
                                  "win_rate": s["win_rate"], "avg_pnl": s["per_trade"], "avg_win": s["avg_win"], "avg_loss": s["avg_loss"],
                                  "profit_factor": s["profit_factor"], "total_return_pct": round(100.0 * s["total"] / CAPITAL, 2),
                                  "sharpe": s["sharpe"], "max_drawdown_pct": round(100.0 * s["max_drawdown"] / CAPITAL, 2),
                                  "ran": ran, "mode": "conservative", "execution": run["label"],
                                  "win_day_rate": s["win_day_rate"], "worst_day": s["worst_day"], "max_drawdown": s["max_drawdown"],
                                  "params": {**({"v2.2 live": True} if key == "ndx_0dte_tasty" else {}), **run["params"]},
                                  "runs": alt}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2024-10-01")
    ap.add_argument("--until", default=_dt.date.today().isoformat())
    ap.add_argument("--out", default=str(HERE / "conservative_rerun_2026-09-25"))
    ap.add_argument("--skip-tasty", action="store_true")
    ap.add_argument("--skip-walls", action="store_true")
    ap.add_argument("--no-baselines", action="store_true")
    a = ap.parse_args(argv)
    from api.bootstrap import bootstrap
    info = bootstrap()
    import gex_edge as GE
    GE.strict_read_only()
    log = lambda s: print(s, flush=True)
    log(f"platform {info['working_copy']}; strategies {info['strategies_dir']}; overlays {info['strategy_overlays']}")
    since, until = _dt.date.fromisoformat(a.since), _dt.date.fromisoformat(a.until)
    log("loading (read only, by month) ...")
    eng, days, bars, prints = load(since, until, log)
    log(f"{len(days)} stored sessions {days[0]} .. {days[-1]}; {len(bars):,} bars, {len(prints):,} same-day prints")
    res = {"generated": _dt.datetime.now().isoformat(timespec="seconds"), "since": str(since), "until": str(until),
           "sessions": len(days), "first": str(days[0]), "last": str(days[-1]), "capital": CAPITAL, "in_sample_end": str(IS_END)}
    if not a.skip_tasty:
        res["ndx_0dte_tasty"] = run_tasty(days, bars, prints, log)
    if not a.skip_walls:
        res["ndx_gamma_walls"] = run_walls(days, bars, prints, log)
    out = Path(a.out)
    out.with_suffix(".json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    out.with_suffix(".tables.md").write_text(markdown(res), encoding="utf-8")
    log(f"wrote {out.with_suffix('.json')} and {out.with_suffix('.tables.md')}")
    if not a.no_baselines:
        bp = ROOT / "data" / "backtest_baselines.json"
        existing = {}
        if bp.exists():
            try:
                existing = json.loads(bp.read_text(encoding="utf-8")).get("strategies", {})
            except ValueError:
                existing = {}
        b = baselines(res)
        b["strategies"] = {**existing, **b["strategies"]}
        bp.write_text(json.dumps(b, indent=1), encoding="utf-8")
        log(f"wrote {bp} ({', '.join(b['strategies'])})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
