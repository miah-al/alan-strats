"""NDX call-wall fade: a 0DTE backtest priced on the real NDXP prints. Behind docs/research/gex_wall_fade_2026-09.md.

    python docs/research/gex_wall_fade.py [--out fade.json]

The walls are docs/research/gex_walls.py's no-look-ahead maps (A: top-5 by cumulative same-day NDXP volume;
B: top-5 by |(calls - puts) x BS gamma x S^2|). A WALL here is a top-5 strike that is call-heavy (cumulative call
volume > put volume at that strike, at that minute).

Entry: NDX rallies to within 0.10% below a call-heavy wall after having been >= 0.20% away (gex_walls' approach,
from below). Window 11:00-15:00 ET (10:00-11:00 reported apart). At most one open trade, at most 2 a day.

Trades (0DTE NDXP, 1 lot = x100):
  A  call credit spread, short at the wall, long 25 / 50 points above
  B  call credit spread, short one grid step (25) above the wall, long 25 / 50 above that
  C  put debit spread, long the ATM strike (nearest to NDX), short 25 / 50 below — the directional fade
Fills: each leg's first print (VWAP, else close) in the 3 minutes after the trigger bar; no print, no trade.
Slippage per leg per transaction: $0.25 / $0.75 / $1.50 (option points); commission $1.00 per leg per
transaction; cash settlement at the 16:00 NDX close costs nothing.
Exits: hold   to cash settlement
       tp60   take profit at 50% of the credit (A/B: spread mark <= 0.5 x credit; C: mark >= 1.5 x debit),
              else out at +60 minutes (settled if that is past the close)
       stop   out when NDX trades >= 0.20% through the wall, else settled
       tp60s  tp60 and stop, whichever first
Marks and exits use the legs' prints (the last print carried forward for a mark; the first print in the next 3
minutes for an exit fill, else the last).
Controls, same rules: call-heavy strikes that are NOT walls, and every strike approached from below.
Walk-forward: in-sample 2024-10-01 .. 2025-09-30 (the variant is chosen there), out-of-sample 2025-10-01 .. 2026-09-23.

Read only; no network request.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
for p in (str(ROOT.parent), str(ROOT), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import gex_edge as GE  # noqa: E402
import gex_walls as GW  # noqa: E402

N = GW.N_MIN
STEP = 25.0
SLIPS = (0.25, 0.75, 1.50)
COMM = 1.00
MULT = 100.0
STOP_THROUGH = 0.002
IS_END = _dt.date(2025, 9, 30)
WINDOWS = {"11-15": (90, 330), "10-11": (30, 90)}
TYPES = ("A", "B", "C")
WIDTHS = (25.0, 50.0)
EXITS = ("hold", "tp60", "stop", "tp60s")
GROUPS = ("wall", "ctl_callheavy", "ctl_all")


# ── data ──────────────────────────────────────────────────────────────────────

def option_prints(since: _dt.date) -> pd.DataFrame:
    from sqlalchemy import text
    from api.services.db import require_db
    with require_db().connect() as c:
        r = c.execute(text("""
            SELECT o.BarTs, o.Strike, o.ContractType, o.[Close], o.Vwap, o.Volume FROM mkt.OptionMinuteBar o
            JOIN mkt.Ticker t ON t.TickerId = o.TickerId
            WHERE t.Symbol = 'NDX' AND o.Root = 'NDXP' AND o.ExpirationDate = CAST(o.BarTs AS date)
              AND o.BarTs >= :d"""), {"d": since}).fetchall()
    df = pd.DataFrame(r, columns=["ts", "strike", "type", "close", "vwap", "volume"])
    df["ts"] = pd.to_datetime(df["ts"])
    df["day"] = df["ts"].dt.date
    df["i"] = (df["ts"].dt.hour * 60 + df["ts"].dt.minute) - 570
    df["strike"] = df["strike"].astype(float)
    df["call"] = df["type"].astype(str).str.upper().str.startswith("C")
    for c in ("close", "vwap", "volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["px"] = df["vwap"].where(df["vwap"] > 0, df["close"])
    return df[(df["i"] >= 0) & (df["i"] < N)]


class Session:
    """One day's NDX bars, wall maps and option print grids."""

    def __init__(self, day, bars, opt, sigma):
        self.day = day
        self.o, self.h, self.l, self.c = bars
        self.maps = GW.wall_maps(opt, self.c, sigma)
        self.ks = self.maps[0]
        self.kix = {float(k): j for j, k in enumerate(self.ks)}
        self.pr, self.last = {}, {}
        for is_call in (True, False):
            px = np.full((N, len(self.ks)), np.nan)
            cl = np.full((N, len(self.ks)), np.nan)
            x = opt[opt["call"] == is_call]
            for r in x.itertuples(index=False):
                j = self.kix[float(r.strike)]
                px[int(r.i), j] = r.px
                cl[int(r.i), j] = r.close
            self.pr[is_call] = px
            self.last[is_call] = pd.DataFrame(cl).ffill().to_numpy()
        self.events = GW.session_events(day, bars, self.maps)

    def fill(self, is_call: bool, k: float, i0: int, span: int = 3):
        """(price, minute) of the first print of the contract in minutes i0 .. i0+span-1, else None."""
        j = self.kix.get(float(k))
        if j is None or i0 >= N:
            return None
        col = self.pr[is_call][i0:min(i0 + span, N), j]
        ok = np.where(np.isfinite(col))[0]
        return (float(col[ok[0]]), i0 + int(ok[0])) if len(ok) else None

    def exit_px(self, is_call: bool, k: float, i0: int):
        f = self.fill(is_call, k, i0)
        if f is not None:
            return f[0]
        j = self.kix.get(float(k))
        v = self.last[is_call][min(i0, N - 1), j] if j is not None else np.nan
        return float(v) if np.isfinite(v) else None


# ── one trade ─────────────────────────────────────────────────────────────────

def legs(ttype: str, wall: float, width: float, spot: float, ks) -> tuple:
    """(is_call, short strike, long strike). A / B are call credit spreads, C a put debit spread (long, short)."""
    if ttype == "A":
        return True, wall, wall + width
    if ttype == "B":
        return True, wall + STEP, wall + STEP + width
    atm = float(ks[int(np.argmin(np.abs(np.asarray(ks) - spot)))])
    return False, atm - width, atm                      # C: short the lower put, long the ATM put


def simulate(s: Session, ev: dict, ttype: str, width: float, exit_rule: str) -> dict | None:
    """P&L before slippage and commission, the number of leg transactions, and the exit minute. None: no fill."""
    i, wall = int(ev["i"]), float(ev["strike"])
    is_call, k_short, k_long = legs(ttype, wall, width, float(s.c[i]), s.ks)
    if k_short not in s.kix or k_long not in s.kix:
        return None
    fs, fl = s.fill(is_call, k_short, i + 1), s.fill(is_call, k_long, i + 1)
    if fs is None or fl is None:
        return None
    entry = max(fs[1], fl[1])
    credit = fs[0] - fl[0]                                # A/B: credit received; C: minus the debit paid
    if ttype in ("A", "B") and credit <= 0:
        return None
    if ttype == "C" and -credit <= 0:
        return None
    js, jl = s.kix[k_short], s.kix[k_long]
    mark = s.last[is_call][:, js] - s.last[is_call][:, jl]   # short - long (C: negative of the spread's value)
    end = N - 1
    ex_at = None
    horizon = entry + 60
    if exit_rule in ("tp60", "tp60s"):
        seg = mark[entry + 1:min(horizon, end) + 1]
        hit = (seg <= 0.5 * credit) if ttype != "C" else (-seg >= 1.5 * -credit)
        hit = hit & np.isfinite(seg)
        if hit.any():
            ex_at = entry + 1 + int(np.argmax(hit))
    if exit_rule in ("stop", "tp60s"):
        lim = N if exit_rule == "stop" else min(horizon, end) + 1
        through = s.h[entry + 1:lim] >= wall * (1 + STOP_THROUGH)
        if through.any():
            st = entry + 1 + int(np.argmax(through))
            ex_at = st if ex_at is None else min(ex_at, st)
    if ex_at is None and exit_rule in ("tp60", "tp60s") and horizon < end:
        ex_at = horizon
    settle = float(s.c[-1])
    if ex_at is None or ex_at >= end:
        if is_call:
            value = min(max(settle - k_short, 0.0), width)          # the call spread's payout
            pnl = (credit - value) * MULT
        else:
            value = min(max(k_long - settle, 0.0), width)           # the put spread's payout
            pnl = (value + credit) * MULT
        return {"pnl0": pnl, "tx": 2, "exit_i": N, "entry_i": entry, "credit": credit, "how": "settled"}
    ps, pl = s.exit_px(is_call, k_short, ex_at + 1), s.exit_px(is_call, k_long, ex_at + 1)
    if ps is None or pl is None:
        return None
    pnl = (credit - (ps - pl)) * MULT
    return {"pnl0": pnl, "tx": 4, "exit_i": ex_at + 1, "entry_i": entry, "credit": credit, "how": "exited"}


def run(sessions: list[Session], group: str, mapname: str, window: str, ttype: str, width: float,
        exit_rule: str) -> list[dict]:
    lo, hi = WINDOWS[window]
    top = "topA" if mapname == "A" else "topB"
    out = []
    for s in sessions:
        evs = [e for e in s.events if e["side"] > 0 and lo <= e["i"] < hi]
        if group == "wall":
            evs = [e for e in evs if e[top] and (e["call_share"] or 0) > 0.5]
        elif group == "ctl_callheavy":
            evs = [e for e in evs if not e[top] and (e["call_share"] or 0) > 0.5]
        evs.sort(key=lambda e: (e["i"], e["strike"]))
        free_at, n = -1, 0
        for e in evs:
            if n >= 2 or e["i"] <= free_at:
                continue
            t = simulate(s, e, ttype, width, exit_rule)
            if t is None:
                continue
            t.update(day=s.day, i=e["i"], strike=e["strike"])
            out.append(t)
            free_at, n = t["exit_i"], n + 1
    return out


# ── metrics ───────────────────────────────────────────────────────────────────

def pnl(t: dict, slip: float) -> float:
    return t["pnl0"] - slip * MULT * t["tx"] - COMM * t["tx"]


def metrics(trades: list[dict], slip: float) -> dict:
    if not trades:
        return {"n": 0}
    p = np.array([pnl(t, slip) for t in trades])
    days = pd.Series(p, index=[t["day"] for t in trades]).groupby(level=0).sum()
    cum = np.cumsum(p)
    dd = float((cum - np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:]).min())
    k = max(1, int(math.ceil(0.05 * len(p))))
    return {"n": int(len(p)), "days": int(len(days)), "win_rate": float((p > 0).mean()), "mean": float(p.mean()),
            "median": float(np.median(p)), "per_day": float(days.mean()), "total": float(p.sum()),
            "worst_day": float(days.min()), "max_dd": min(dd, 0.0), "tail5_mean": float(np.sort(p)[:k].mean()),
            "settled_share": float(np.mean([t["how"] == "settled" for t in trades]))}


def boot_diff(a: list[dict], b: list[dict], slip: float, n: int = 2000, seed: int = 5) -> dict | None:
    if len(a) < 10 or len(b) < 10:
        return None
    rng = np.random.default_rng(seed)
    da, db = {}, {}
    for t in a:
        da.setdefault(t["day"], []).append(pnl(t, slip))
    for t in b:
        db.setdefault(t["day"], []).append(pnl(t, slip))
    days = sorted(set(da) | set(db))
    diffs = []
    for _ in range(n):
        pick = [days[i] for i in rng.integers(0, len(days), len(days))]
        xa = [v for d in pick for v in da.get(d, [])]
        xb = [v for d in pick for v in db.get(d, [])]
        if xa and xb:
            diffs.append(np.mean(xa) - np.mean(xb))
    diffs = np.array(diffs)
    return {"diff": float(np.mean([pnl(t, slip) for t in a]) - np.mean([pnl(t, slip) for t in b])),
            "ci95": [float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))],
            "p_boot": float(2 * min((diffs <= 0).mean(), (diffs >= 0).mean()))}


def split(trades: list[dict]) -> tuple[list[dict], list[dict]]:
    return [t for t in trades if t["day"] <= IS_END], [t for t in trades if t["day"] > IS_END]


# ── the ndx_0dte_tasty filter ─────────────────────────────────────────────────

def tasty_filter(sessions: dict, since: _dt.date) -> dict:
    """ndx_0dte_tasty's backtest trades, split by whether a wall (map A / B top-5) was crossed by the NDX move of the
    30 minutes before the entry; the filter (skip those) chosen in-sample, reported out of sample."""
    from engine.strategy_backtest import run_backtest
    perf = run_backtest("ndx_0dte_tasty", "NDX", since.isoformat(), max(sessions).isoformat(), 30000,
                        report_window=True)
    tr = perf["trades"].copy()
    cols = list(tr.columns)
    tcol = next((c for c in ("entry_time", "entry_ts", "entry_datetime", "open_time", "entry_date") if c in cols), None)
    if tcol is None or tr.empty:
        return {"error": f"no entry time in the backtest's trades ({cols})"}
    if tcol == "entry_time" and "entry_date" in cols:
        tr["ts"] = pd.to_datetime(tr["entry_date"].astype(str) + " " + tr["entry_time"].astype(str))
    else:
        tr["ts"] = pd.to_datetime(tr[tcol])
    tr["day"] = tr["ts"].dt.date
    tr["i"] = tr["ts"].dt.hour * 60 + tr["ts"].dt.minute - 570
    tr["pnl"] = pd.to_numeric(tr["pnl"], errors="coerce")
    has_time = bool((tr["i"] > 0).any())
    if not has_time:
        return {"error": f"the trades carry no intraday entry time ({tcol}); the filter cannot be placed", "columns": cols}
    rows = []
    for r in tr.itertuples(index=False):
        s = sessions.get(r.day)
        if s is None or not (30 <= r.i < N):
            continue
        c_now, c_then = s.c[r.i], s.c[r.i - 30]
        lo, hi = sorted((c_then, c_now))
        flags = {}
        for name, idx in (("A", 4), ("B", 6)):
            walls = s.ks[s.maps[idx][r.i]]
            flags[name] = bool(((walls > lo) & (walls < hi)).any())
        rows.append({"day": r.day, "pnl": float(r.pnl), "crossedA": flags["A"], "crossedB": flags["B"]})
    df = pd.DataFrame(rows)
    ins, oos = df[df["day"] <= IS_END], df[df["day"] > IS_END]

    def stat(x):
        return {"trades": int(len(x)), "days": int(x["day"].nunique()), "total": float(x["pnl"].sum()),
                "mean": float(x["pnl"].mean()) if len(x) else None, "win_rate": float((x["pnl"] > 0).mean()) if len(x) else None}
    choice, best = None, None
    for name in ("A", "B"):
        gain = -ins[ins[f"crossed{name}"]]["pnl"].sum()                # what skipping them adds in-sample
        if best is None or gain > best:
            choice, best = name, gain
    out = {"entry_time_column": tcol, "in_sample": {"all": stat(ins), "skipped_A": stat(ins[ins["crossedA"]]),
                                                    "skipped_B": stat(ins[ins["crossedB"]])},
           "chosen_map_in_sample": choice, "in_sample_gain_from_skipping": float(best)}
    if choice is not None and len(oos):
        kept, skipped = oos[~oos[f"crossed{choice}"]], oos[oos[f"crossed{choice}"]]
        out["out_of_sample"] = {"all": stat(oos), "kept": stat(kept), "skipped": stat(skipped),
                                "filter_gain": float(-skipped["pnl"].sum()),
                                "skipped_vs_kept_mean": GE.welch(skipped["pnl"], kept["pnl"])
                                if len(skipped) > 1 and len(kept) > 1 else None}
    return out


# ── the study ─────────────────────────────────────────────────────────────────

def study(since: _dt.date, with_tasty: bool = True) -> dict:
    opt = option_prints(since)
    m = GE.minutes("NDX", since)
    vx = GW.vxn_prev(since)
    by_day = {d: x for d, x in opt.groupby("day")}
    sessions = {}
    for day, b in m.groupby("day"):
        o = by_day.get(day)
        bars = GW.session_arrays(b)
        if o is None or bars is None or o["volume"].sum() <= 0:
            continue
        sessions[day] = Session(day, bars, o, (vx.get(day) or 20.0) / 100.0)
    ss = [sessions[d] for d in sorted(sessions)]
    res = {"sessions": len(ss), "first": str(ss[0].day), "last": str(ss[-1].day), "in_sample_end": str(IS_END),
           "slippage_per_leg": list(SLIPS), "commission_per_leg": COMM, "variants": {}}
    for mapname in ("A", "B"):
        for window in WINDOWS:
            for ttype in TYPES:
                for width in WIDTHS:
                    for ex in EXITS:
                        key = f"map{mapname}|{window}|{ttype}{int(width)}|{ex}"
                        g = {grp: run(ss, grp, mapname, window, ttype, width, ex) for grp in GROUPS}
                        v = {}
                        for part, idx in (("in_sample", 0), ("out_of_sample", 1)):
                            parts = {grp: split(g[grp])[idx] for grp in GROUPS}
                            v[part] = {grp: {f"slip{s}": metrics(parts[grp], s) for s in SLIPS} for grp in GROUPS}
                            v[part]["wall_vs_ctl_callheavy_slip0.75"] = boot_diff(parts["wall"], parts["ctl_callheavy"], 0.75)
                            v[part]["wall_vs_ctl_all_slip0.75"] = boot_diff(parts["wall"], parts["ctl_all"], 0.75)
                        res["variants"][key] = v
    # the in-sample choice: the fade (A / B), 11-15, n >= 40, the best edge over the call-heavy control at $0.75,
    # with a positive mean itself
    best, best_edge = None, None
    for key, v in res["variants"].items():
        mp, win, tw, ex = key.split("|")
        if win != "11-15" or tw[0] == "C":
            continue
        w = v["in_sample"]["wall"]["slip0.75"]
        c = v["in_sample"]["ctl_callheavy"]["slip0.75"]
        if w.get("n", 0) < 40 or c.get("n", 0) < 40 or w["mean"] <= 0:
            continue
        edge = w["mean"] - c["mean"]
        if best_edge is None or edge > best_edge:
            best, best_edge = key, edge
    res["chosen_in_sample"] = {"variant": best, "edge_vs_ctl_callheavy_slip0.75": best_edge}
    if with_tasty:
        try:
            res["tasty_filter"] = tasty_filter(sessions, since)
        except Exception as exc:  # noqa: BLE001
            res["tasty_filter"] = {"error": f"{type(exc).__name__}: {exc}"[:300]}
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2024-10-01")
    ap.add_argument("--out", default=None)
    ap.add_argument("--no-tasty", action="store_true")
    a = ap.parse_args(argv)
    from api.bootstrap import bootstrap
    bootstrap()
    GE.strict_read_only()
    res = study(_dt.date.fromisoformat(a.since), with_tasty=not a.no_tasty)
    txt = json.dumps(res, indent=1, default=lambda x: None if isinstance(x, float) and not math.isfinite(x) else str(x))
    if a.out:
        Path(a.out).write_text(txt, encoding="utf-8")
    print(json.dumps(res["chosen_in_sample"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
