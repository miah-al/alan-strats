"""Do NDX "gamma walls" stall or reject price? The historical study behind docs/research/gex_walls_2026-09.md.

    python docs/research/gex_walls.py [--out walls.json] [--since 2024-10-01]

No strike-level open-interest history exists, so the wall map is a no-look-ahead PROXY built from the same-day
NDXP (0DTE) prints stored in mkt.OptionMinuteBar (the NDX task's post-close routine: 1-minute bars of the ~32
strikes around the day's open, 25 points apart). At each minute t of a session, per strike K:

    cumulative 0DTE volume  C(t, K) + P(t, K)         (calls, puts: bars that closed by t+1)
    gamma-weighted proxy    (C - P) x BS gamma(S_t, K, T_t, sigma) x S_t^2      (calls +, puts -: the service's
                            dealer sign convention; sigma = the prior VXN close; T = the session's minutes left)

"Walls" = the top-5 strikes at t by cumulative volume (map A) and by |gamma proxy| (map B). The event study runs on
the NDX 1-minute bars (mkt.MinuteBar): a strike is ARMED once price is >= 2 bands away from it (band = 0.10%);
an APPROACH is the first bar whose high (from below) / low (from above) comes within one band of it, from 10:00.
Outcome at +15 / +30 / +60 minutes: CROSSED = traded >= one band beyond the strike (bar high / low, the approach
bar included); the return and the excursions in the approach direction; after a cross, where price stands
relative to the strike (continuation). Every grid strike is tracked, so the non-wall strikes are the control.
Then ndx_0dte_tasty's trigger (15 points in 30 minutes, 11:00-14:00) is split by a wall ahead vs one just crossed.

Read only (a guard refuses every write statement). No network request is made.
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
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
for p in (str(ROOT.parent), str(ROOT), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import gex_edge as GE  # noqa: E402  (the research helpers: read-only guard, minute bars, trigger, regime)

BAND = 0.001
TOP = 5
HORIZONS = (15, 30, 60)
START_MIN = 30                       # 10:00 (minutes after 09:30)
N_MIN = 390
TOD = [("10:00-11:00", 30, 90), ("11:00-14:00", 90, 270), ("14:00-15:00", 270, 330), ("15:00-16:00", 330, 390)]


# ── data ──────────────────────────────────────────────────────────────────────

def option_minutes(since: _dt.date) -> pd.DataFrame:
    from sqlalchemy import text
    from api.services.db import require_db
    with require_db().connect() as c:
        r = c.execute(text("""
            SELECT o.BarTs, o.Strike, o.ContractType, o.Volume FROM mkt.OptionMinuteBar o
            JOIN mkt.Ticker t ON t.TickerId = o.TickerId
            WHERE t.Symbol = 'NDX' AND o.Root = 'NDXP' AND o.ExpirationDate = CAST(o.BarTs AS date)
              AND o.BarTs >= :d"""), {"d": since}).fetchall()
    df = pd.DataFrame(r, columns=["ts", "strike", "type", "volume"])
    df["ts"] = pd.to_datetime(df["ts"])
    df["day"] = df["ts"].dt.date
    df["i"] = (df["ts"].dt.hour * 60 + df["ts"].dt.minute) - 570
    df["strike"] = df["strike"].astype(float)
    df["call"] = df["type"].astype(str).str.upper().str.startswith("C")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0.0)
    return df[(df["i"] >= 0) & (df["i"] < N_MIN)]


def vxn_prev(since: _dt.date) -> pd.Series:
    """date -> the prior session's VXN close (known at the open)."""
    from db.client import get_engine, get_price_bars
    d = get_price_bars(get_engine(), "VXN", since - _dt.timedelta(days=30), _dt.date.today())
    s = pd.Series(d["close"].astype(float).values, index=pd.to_datetime(d["date"]).dt.date)
    return s.shift(1)


def session_arrays(b: pd.DataFrame):
    """NDX 1-minute bars of a session on the 390-minute grid (gaps carried forward). None for a short session."""
    if len(b) < 300:
        return None
    i = (b["m"] - 570).to_numpy()
    ok = (i >= 0) & (i < N_MIN)
    grid = pd.DataFrame(index=range(N_MIN), columns=["open", "high", "low", "close"], dtype=float)
    grid.loc[i[ok], ["open", "high", "low", "close"]] = b.loc[ok, ["open", "high", "low", "close"]].to_numpy(float)
    c = grid["close"].ffill().bfill()
    for col in ("open", "high", "low"):
        grid[col] = grid[col].fillna(c)
    return grid["open"].to_numpy(), grid["high"].to_numpy(), grid["low"].to_numpy(), c.to_numpy()


def wall_maps(opt: pd.DataFrame, close: np.ndarray, sigma: float):
    """Per minute x strike: cumulative call / put volume, the gamma-weighted proxy, and the two top-5 masks."""
    ks = np.array(sorted(opt["strike"].unique()), float)
    kix = {k: j for j, k in enumerate(ks)}
    cv = np.zeros((N_MIN, len(ks)))
    pv = np.zeros((N_MIN, len(ks)))
    for is_call, arr in ((True, cv), (False, pv)):
        g = opt[opt["call"] == is_call].groupby(["i", "strike"])["volume"].sum()
        for (i, k), v in g.items():
            arr[int(i), kix[k]] += v
    C, P = np.cumsum(cv, axis=0), np.cumsum(pv, axis=0)
    S = close[:, None]
    T = np.maximum(N_MIN - np.arange(N_MIN) - 1, 5)[:, None] / (252.0 * N_MIN)
    sig = max(float(sigma), 0.05)
    d1 = (np.log(S / ks[None, :]) + 0.5 * sig * sig * T) / (sig * np.sqrt(T))
    gamma = np.exp(-0.5 * d1 * d1) / math.sqrt(2 * math.pi) / (S * sig * np.sqrt(T))
    gp = (C - P) * gamma * S * S
    tot = C + P

    def top_mask(score):
        order = np.argsort(-score, axis=1, kind="stable")
        rank = np.empty_like(order)
        rank[np.arange(N_MIN)[:, None], order] = np.arange(score.shape[1])[None, :]
        return (rank < TOP) & (score > 0), rank
    topA, rankA = top_mask(tot)
    topB, rankB = top_mask(np.abs(gp))
    share = tot / np.maximum(tot.sum(axis=1, keepdims=True), 1e-9)
    return ks, C, P, gp, topA, rankA, topB, rankB, share


# ── the events ────────────────────────────────────────────────────────────────

def session_events(day, bars, maps, band: float = BAND) -> list[dict]:
    o, h, l, c = bars
    ks, C, P, gp, topA, rankA, topB, rankB, share = maps
    out = []
    for j, K in enumerate(ks):
        armed, side = False, 0
        lo_b, hi_b = K * (1 - band), K * (1 + band)
        for i in range(N_MIN):
            dist = abs(c[i] - K) / K
            if not armed:
                if dist >= 2 * band:
                    armed, side = True, (1 if c[i] < K else -1)
                continue
            touched = (h[i] >= lo_b) if side > 0 else (l[i] <= hi_b)
            if not touched:
                if dist > band:
                    side = 1 if c[i] < K else -1
                continue
            armed = False
            if i < START_MIN:
                continue
            ev = {"day": day, "i": i, "strike": K, "side": side, "round100": bool(abs(K / 100 - round(K / 100)) < 1e-9),
                  "dist_open_bps": abs(K / o[0] - 1) * 1e4, "topA": bool(topA[i, j]), "topB": bool(topB[i, j]),
                  "rankA": int(rankA[i, j]), "rankB": int(rankB[i, j]), "vol": float(C[i, j] + P[i, j]),
                  "share": float(share[i, j]), "call_share": float(C[i, j] / (C[i, j] + P[i, j]))
                  if (C[i, j] + P[i, j]) > 0 else np.nan, "gp_sign": int(np.sign(gp[i, j])),
                  "cross_min": None}
            beyond = (h >= hi_b) if side > 0 else (l <= lo_b)
            first = np.argmax(beyond[i:]) if beyond[i:].any() else None
            ev["cross_min"] = int(first) if first is not None else None
            for hz in HORIZONS:
                e = i + hz
                if e >= N_MIN:
                    continue
                seg_h, seg_l = h[i:e + 1], l[i:e + 1]
                ev[f"crossed{hz}"] = bool(first is not None and first <= hz)
                ev[f"ret{hz}"] = side * (c[e] / c[i] - 1) * 1e4                         # bps, approach direction
                ev[f"toward{hz}"] = (seg_h.max() / c[i] - 1) * 1e4 if side > 0 else (1 - seg_l.min() / c[i]) * 1e4
                ev[f"away{hz}"] = (1 - seg_l.min() / c[i]) * 1e4 if side > 0 else (seg_h.max() / c[i] - 1) * 1e4
                ev[f"beyond{hz}"] = side * (c[e] / K - 1) * 1e4                         # bps past the strike
            out.append(ev)
    return out


# ── statistics ────────────────────────────────────────────────────────────────

def boot_diff(a: pd.DataFrame, b: pd.DataFrame, col: str, n: int = 1000, seed: int = 11) -> dict:
    """Mean(a) - mean(b) with a bootstrap over days (events within a day are not independent)."""
    rng = np.random.default_rng(seed)
    da = {d: x[col].to_numpy(float) for d, x in a.groupby("day")}
    db = {d: x[col].to_numpy(float) for d, x in b.groupby("day")}
    days = sorted(set(da) | set(db))
    diffs = []
    for _ in range(n):
        pick = rng.choice(len(days), len(days), replace=True)
        xa = [da[days[p]] for p in pick if days[p] in da]
        xb = [db[days[p]] for p in pick if days[p] in db]
        if not xa or not xb:
            continue
        diffs.append(np.concatenate(xa).mean() - np.concatenate(xb).mean())
    diffs = np.array(diffs)
    est = float(a[col].mean() - b[col].mean())
    return {"diff": est, "ci95": [float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))],
            "p_boot": float(2 * min((diffs <= 0).mean(), (diffs >= 0).mean()))}


def rates(e: pd.DataFrame) -> dict:
    out = {"n": int(len(e)), "days": int(e["day"].nunique()) if len(e) else 0}
    for hz in HORIZONS:
        x = e.dropna(subset=[f"ret{hz}"])
        if not len(x):
            continue
        x = x.assign(**{f"crossed{hz}": x[f"crossed{hz}"].astype(bool)})
        cr = x[f"crossed{hz}"].astype(float)
        crossed = x[x[f"crossed{hz}"]]
        out[f"h{hz}"] = {"n": int(len(x)), "cross_rate": float(cr.mean()), "reject_rate": float(1 - cr.mean()),
                         "mean_ret_bps": float(x[f"ret{hz}"].mean()),
                         "mean_toward_bps": float(x[f"toward{hz}"].mean()), "mean_away_bps": float(x[f"away{hz}"].mean()),
                         "crossed_beyond_bps": float(crossed[f"beyond{hz}"].mean()) if len(crossed) else None,
                         "crossed_held_share": float((crossed[f"beyond{hz}"] > 0).mean()) if len(crossed) else None,
                         "rejected_ret_bps": float(x[~x[f"crossed{hz}"]][f"ret{hz}"].mean())
                         if (~x[f"crossed{hz}"]).any() else None}
    return out


def compare(a: pd.DataFrame, b: pd.DataFrame, hz: int = 30) -> dict:
    """a vs b at one horizon: cross rate (two proportions, and the day bootstrap), post-cross continuation."""
    xa, xb = a.dropna(subset=[f"ret{hz}"]), b.dropna(subset=[f"ret{hz}"])
    xa = xa.assign(**{f"crossed{hz}": xa[f"crossed{hz}"].astype(bool)})
    xb = xb.assign(**{f"crossed{hz}": xb[f"crossed{hz}"].astype(bool)})
    if len(xa) < 10 or len(xb) < 10:
        return {"n_a": int(len(xa)), "n_b": int(len(xb))}
    ka, kb = int(xa[f"crossed{hz}"].sum()), int(xb[f"crossed{hz}"].sum())
    out = {"n_a": int(len(xa)), "n_b": int(len(xb)), "cross_a": ka / len(xa), "cross_b": kb / len(xb),
           "two_prop": GE.two_prop(ka, len(xa), kb, len(xb))}
    xa = xa.assign(cr=xa[f"crossed{hz}"].astype(float))
    xb = xb.assign(cr=xb[f"crossed{hz}"].astype(float))
    out["cross_diff_day_bootstrap"] = boot_diff(xa, xb, "cr")
    ca, cb = xa[xa[f"crossed{hz}"]], xb[xb[f"crossed{hz}"]]
    if len(ca) >= 10 and len(cb) >= 10:
        out["post_cross_beyond_bps"] = {"a": float(ca[f"beyond{hz}"].mean()), "b": float(cb[f"beyond{hz}"].mean()),
                                        "welch": GE.welch(ca[f"beyond{hz}"], cb[f"beyond{hz}"])}
    out["ret_bps"] = {"a": float(xa[f"ret{hz}"].mean()), "b": float(xb[f"ret{hz}"].mean()),
                      "welch": GE.welch(xa[f"ret{hz}"], xb[f"ret{hz}"])}
    return out


def lpm(e: pd.DataFrame, flag: str, hz: int = 30) -> dict:
    """crossed_hz on the wall flag and the confounders (a linear probability model; standard errors clustered by
    day): call-heavy, the approach side, time of day, distance of the strike from the open, a round-100 strike,
    the prior-close regime (SPY proxy) and the prior VXN."""
    x = e.dropna(subset=[f"ret{hz}", "vxn_prev"]).copy()
    x = x[x["regime"] != "unknown"]
    y = x[f"crossed{hz}"].astype(float).to_numpy()
    cols = {
        "wall": x[flag].astype(float),
        "call_heavy": (x["call_share"].fillna(0.5) >= 0.5).astype(float),
        "wall_x_call_heavy": x[flag].astype(float) * (x["call_share"].fillna(0.5) >= 0.5).astype(float),
        "from_below": (x["side"] > 0).astype(float),
        "tod_11_14": ((x["i"] >= 90) & (x["i"] < 270)).astype(float),
        "tod_14_15": ((x["i"] >= 270) & (x["i"] < 330)).astype(float),
        "tod_15_16": (x["i"] >= 330).astype(float),
        "dist_open_100bps": x["dist_open_bps"] / 100.0,
        "round100": x["round100"].astype(float),
        "regime_positive": (x["regime"] == "positive").astype(float),
        "regime_near_flip": (x["regime"] == "near_flip").astype(float),
        "vxn_prev": x["vxn_prev"].astype(float),
    }
    names = list(cols)
    X = np.column_stack([np.ones(len(y))] + [cols[n].to_numpy(float) for n in names])
    XtX_inv = np.linalg.pinv(X.T @ X)
    b = XtX_inv @ X.T @ y
    u = y - X @ b
    meat = np.zeros((X.shape[1], X.shape[1]))
    for _d, idx in x.reset_index(drop=True).groupby("day").indices.items():
        s_ = X[idx].T @ u[idx]
        meat += np.outer(s_, s_)
    g = x["day"].nunique()
    V = XtX_inv @ meat @ XtX_inv * (g / max(g - 1, 1))
    se = np.sqrt(np.diag(V))
    out = {"n": int(len(y)), "days": int(g), "mean": float(y.mean()), "coef": {}}
    for k, n in enumerate(["const"] + names):
        t = b[k] / se[k] if se[k] > 0 else float("nan")
        out["coef"][n] = {"b": float(b[k]), "se": float(se[k]), "t": float(t),
                          "p": float(2 * (1 - stats.norm.cdf(abs(t))))}
    return out


def side_by_heavy(e: pd.DataFrame, flag: str, hz: int = 30) -> dict:
    """The cross rate by approach side x call- / put-heavy, walls and the other strikes."""
    x = e.dropna(subset=[f"ret{hz}"])
    x = x.assign(cr=x[f"crossed{hz}"].astype(bool), heavy=np.where(x["call_share"] >= 0.5, "call_heavy", "put_heavy"),
                 approach=np.where(x["side"] > 0, "from_below", "from_above"),
                 group=np.where(x[flag], "wall", np.where(~x["topA"] & ~x["topB"], "control", "other_top")))
    return {f"{g}|{a}|{h}": {"n": int(len(y)), "cross_rate": float(y["cr"].mean())}
            for (g, a, h), y in x.groupby(["group", "approach", "heavy"]) if len(y) >= 20}


def splits(e: pd.DataFrame, flag: str) -> dict:
    w = e[e[flag]]
    out = {}
    w = w.assign(heavy=np.where(w["call_share"] >= 0.5, "call_heavy", "put_heavy"),
                 tod=pd.cut(w["i"], [t[1] for t in TOD] + [N_MIN], labels=[t[0] for t in TOD], right=False),
                 approach=np.where(w["side"] > 0, "from_below", "from_above"))
    for col in ("heavy", "tod", "regime", "approach"):
        out[col] = {str(k): rates(x) for k, x in w.groupby(col, observed=True) if len(x) >= 20}
    hv = w[w["heavy"] == "call_heavy"], w[w["heavy"] == "put_heavy"]
    out["call_vs_put_heavy_h30"] = compare(hv[0], hv[1], 30)
    # dose-response: the strike's share of the day's cumulative 0DTE volume, all tracked strikes
    q = e.assign(q=pd.qcut(e["share"].rank(method="first"), 5, labels=["q1 (least)", "q2", "q3", "q4", "q5 (most)"]))
    out["by_volume_share_quintile_all_strikes"] = {str(k): rates(x).get("h30") for k, x in q.groupby("q", observed=True)}
    return out


# ── the trigger, by a wall ahead vs one just crossed ──────────────────────────

def trigger_split(m: pd.DataFrame, maps_by_day: dict, reg: pd.DataFrame) -> dict:
    trig = GE.trigger_events(m)
    rows = []
    for r in trig.itertuples(index=False):
        mm = maps_by_day.get(r.day)
        if mm is None:
            continue
        (o, h, l, c), maps = mm
        ks, topA, topB = maps[0], maps[4], maps[6]
        i = int(r.minute) - 570
        if not (30 <= i < N_MIN):
            continue
        sgn = 1 if r.move > 0 else -1
        px, px30 = c[i], c[i - 30]
        for name, top in (("A", topA), ("B", topB)):
            walls = ks[top[i]]
            ahead = walls[(sgn * (walls - px) > 0) & (np.abs(walls - px) <= 0.0025 * px)]
            lo, hi = sorted((px30, px))
            crossed = walls[(walls > lo) & (walls < hi)]
            state = ("both" if len(ahead) and len(crossed) else "wall_ahead" if len(ahead) else
                     "just_crossed" if len(crossed) else "neither")
            rows.append({"map": name, "day": r.day, "state": state, "fwd15": r.fwd15, "fwd30": r.fwd30,
                         "fwd60": r.fwd60, "fwd_close": r.fwd_close,
                         "regime": reg.loc[r.day, "regime"] if r.day in reg.index and isinstance(
                             reg.loc[r.day, "regime"], str) else "unknown"})
    df = pd.DataFrame(rows)
    out = {}
    for name, x in df.groupby("map"):
        res = {}
        for st, y in x.groupby("state"):
            f = y["fwd60"].dropna()
            res[st] = {"n": int(len(y)), "continued_60m_share": float((f > 0).mean()) if len(f) else None,
                       "mean_fwd60_pts": float(f.mean()) if len(f) else None,
                       "mean_fwd30_pts": float(y["fwd30"].mean()), "mean_fwd_close_pts": float(y["fwd_close"].mean())}
        a, b = x[x["state"] == "wall_ahead"]["fwd60"].dropna(), x[x["state"] == "just_crossed"]["fwd60"].dropna()
        if len(a) >= 5 and len(b) >= 5:
            res["wall_ahead_vs_just_crossed_fwd60"] = GE.welch(a, b)
        n = x[x["state"] == "neither"]["fwd60"].dropna()
        if len(a) >= 5 and len(n) >= 5:
            res["wall_ahead_vs_neither_fwd60"] = GE.welch(a, n)
        out[f"map_{name}"] = res
    return out


# ── the study ─────────────────────────────────────────────────────────────────

def study(since: _dt.date) -> dict:
    from api.services import gex_history as GH
    opt = option_minutes(since)
    m = GE.minutes("NDX", since)
    vx = vxn_prev(since)
    reg = GE.prior_regime(GH.history("SPY"), sorted(m["day"].unique()))
    events, maps_by_day, used = [], {}, 0
    by_day = {d: x for d, x in opt.groupby("day")}
    for day, b in m.groupby("day"):
        o = by_day.get(day)
        bars = session_arrays(b)
        if o is None or bars is None or o["volume"].sum() <= 0:
            continue
        sigma = (vx.get(day) or 20.0) / 100.0
        maps = wall_maps(o, bars[3], sigma)
        maps_by_day[day] = (bars, maps)
        evs = session_events(day, bars, maps)
        r = reg.loc[day, "regime"] if day in reg.index else None
        for ev in evs:
            ev["regime"] = r if isinstance(r, str) else "unknown"
            ev["vxn_prev"] = float(vx.get(day)) if vx.get(day) is not None else np.nan
        events += evs
        used += 1
    e = pd.DataFrame(events)
    res = {"sessions": used, "first": str(min(maps_by_day)), "last": str(max(maps_by_day)), "band": BAND,
           "events_all_strikes": int(len(e)), "events_per_session": float(len(e) / max(used, 1))}
    for name, flag in (("A_top5_by_volume", "topA"), ("B_top5_by_gamma_proxy", "topB")):
        w, ctl = e[e[flag]], e[~e["topA"] & ~e["topB"]]
        res[name] = {"walls": rates(w), "control_non_top_strikes": rates(ctl),
                     "walls_vs_control": {f"h{hz}": compare(w, ctl, hz) for hz in HORIZONS},
                     "splits": splits(e, flag)}
        res[name]["lpm_crossed30"] = lpm(e, flag, 30)
        res[name]["lpm_crossed60"] = lpm(e, flag, 60)
        res[name]["side_by_heavy_h30"] = side_by_heavy(e, flag, 30)
        ctl = e[~e["topA"] & ~e["topB"]]
        ctl = ctl.assign(tod=pd.cut(ctl["i"], [t[1] for t in TOD] + [N_MIN], labels=[t[0] for t in TOD], right=False))
        res[name]["control_by_tod_h30"] = {str(k): rates(x).get("h30") for k, x in ctl.groupby("tod", observed=True)}
        res[name]["control_by_regime_h30"] = {str(k): rates(x).get("h30") for k, x in ctl.groupby("regime")}
    res["trigger_by_wall"] = trigger_split(m, maps_by_day, reg)
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2024-10-01")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    from api.bootstrap import bootstrap
    bootstrap()
    GE.strict_read_only()
    res = study(_dt.date.fromisoformat(a.since))
    txt = json.dumps(res, indent=1, default=lambda x: None if isinstance(x, float) and not math.isfinite(x) else str(x))
    if a.out:
        Path(a.out).write_text(txt, encoding="utf-8")
    print(txt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
