"""Does dealer GEX carry edge? The tests behind docs/research/gex_edge_2026-09.md.

    python docs/research/gex_edge.py crypto [--out crypto.json]   # IBIT / ETHA: intraday behaviour, weekend gaps
    python docs/research/gex_edge.py spy    [--out spy.json]      # SPY daily, on the stored-snapshot proxy GEX

Read only: a guard refuses every write statement for the whole run; backtests run in memory. Every network
request (yfinance BTC / ETH hourly bars) passes the service's request gate.
Data: the daily proxy GEX history (api/services/gex_history.py: stored SPY snapshots — monthly expiries only,
7-88 days out, OI proxied by 20-day contract volume), the recorded live GEX (app.GexHistory), SPY / QQQ / IWM /
IBIT / ETHA daily bars, IBIT / ETHA 1-minute bars (Polygon, synced into mkt.MinuteBar), VIX closes, and two
strategies' backtests over the SPY window (their slugs are passed as ``--trades slug:ticker:capital``).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import math
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
for p in (str(ROOT.parent), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

START, END = _dt.date(2024, 8, 1), _dt.date(2026, 7, 10)


# ── read only, for the whole run ──────────────────────────────────────────────

def strict_read_only() -> None:
    from sqlalchemy import event
    from sqlalchemy.engine import Engine
    bad = re.compile(r"\b(INSERT|UPDATE|DELETE|MERGE|CREATE|ALTER|DROP|TRUNCATE|EXEC|INTO)\b", re.I)

    def guard(conn, cursor, statement, parameters, context, executemany):
        body = re.sub(r"'(?:[^']|'')*'", "''", str(statement))
        if bad.search(body):
            raise RuntimeError(f"research is read only: {statement[:80]}")
    event.listen(Engine, "before_cursor_execute", guard)


# ── statistics ────────────────────────────────────────────────────────────────

def ols(y, X, names, lags=5):
    """OLS with Newey-West (Bartlett, ``lags``) standard errors. Returns a dict of coefficient rows and R²."""
    y = np.asarray(y, float)
    X = np.column_stack([np.ones(len(y)), np.asarray(X, float)])
    XtX_inv = np.linalg.inv(X.T @ X)
    b = XtX_inv @ X.T @ y
    u = y - X @ b
    xu = X * u[:, None]
    S = xu.T @ xu
    for l in range(1, lags + 1):
        w = 1 - l / (lags + 1)
        g = xu[l:].T @ xu[:-l]
        S += w * (g + g.T)
    V = XtX_inv @ S @ XtX_inv
    se = np.sqrt(np.diag(V))
    t = b / se
    p = 2 * (1 - stats.norm.cdf(np.abs(t)))
    r2 = 1 - (u @ u) / ((y - y.mean()) @ (y - y.mean()))
    return {"n": int(len(y)), "r2": float(r2),
            "coef": {n: {"b": float(bb), "se": float(s), "t": float(tt), "p": float(pp)}
                     for n, bb, s, tt, pp in zip(["const"] + names, b, se, t, p)}}


def logit(y, X, names, iters=50):
    y = np.asarray(y, float)
    X = np.column_stack([np.ones(len(y)), np.asarray(X, float)])
    b = np.zeros(X.shape[1])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-X @ b))
        W = p * (1 - p)
        H = X.T @ (X * W[:, None])
        g = X.T @ (y - p)
        step = np.linalg.solve(H, g)
        b += step
        if np.abs(step).max() < 1e-10:
            break
    p = 1 / (1 + np.exp(-X @ b))
    V = np.linalg.inv(X.T @ (X * (p * (1 - p))[:, None]))
    se = np.sqrt(np.diag(V))
    z = b / se
    return {"n": int(len(y)), "coef": {n: {"b": float(bb), "se": float(s), "z": float(zz),
                                           "p": float(2 * (1 - stats.norm.cdf(abs(zz)))), "odds_ratio": float(np.exp(bb))}
                                       for n, bb, s, zz in zip(["const"] + names, b, se, z)}}


def two_prop(k1, n1, k2, n2):
    p1, p2 = k1 / n1, k2 / n2
    p = (k1 + k2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    z = (p1 - p2) / se if se else float("nan")
    return {"p1": p1, "n1": n1, "p2": p2, "n2": n2, "diff": p1 - p2, "z": z, "p": float(2 * (1 - stats.norm.cdf(abs(z))))}


def welch(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    t, p = stats.ttest_ind(a, b, equal_var=False)
    return {"mean1": float(a.mean()), "n1": int(len(a)), "mean2": float(b.mean()), "n2": int(len(b)),
            "diff": float(a.mean() - b.mean()), "t": float(t), "p": float(p)}


# ── data ──────────────────────────────────────────────────────────────────────

def daily(sym: str) -> pd.DataFrame:
    from db.client import get_engine, get_price_bars
    df = get_price_bars(get_engine(), sym, START - _dt.timedelta(days=30), END + _dt.timedelta(days=10))
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df.set_index("date")[["open", "high", "low", "close"]].astype(float)


def vix() -> pd.Series:
    from db.client import get_engine, get_vix_bars
    v = get_vix_bars(get_engine(), START - _dt.timedelta(days=30), END + _dt.timedelta(days=10))
    col = "close" if "close" in v.columns else v.columns[-1]
    s = pd.to_numeric(v[col], errors="coerce")
    s.index = pd.to_datetime(v.index).date
    return s.dropna()


def outcomes(bars: pd.DataFrame) -> pd.DataFrame:
    """Next-day outcomes keyed by the signal day t: range_{t+1} = (H-L)/C_t, absret_{t+1} = |C_{t+1}/C_t - 1|."""
    c = bars["close"]
    nxt = bars.shift(-1)
    return pd.DataFrame({"range_next": (nxt["high"] - nxt["low"]) / c, "absret_next": (nxt["close"] / c - 1).abs(),
                         "ret_next": nxt["close"] / c - 1, "next_day": pd.Series(bars.index, index=bars.index).shift(-1)})


# ── the SPY study ─────────────────────────────────────────────────────────────

def spy_study() -> dict:
    from api.services import gex_history as GH
    res: dict = {}
    g = GH.build("SPY")
    g.index = pd.Index(g.index)
    res["coverage"] = coverage(g)
    spy, qqq, iwm = daily("SPY"), daily("QQQ"), daily("IWM")
    v = vix()
    d = g.join(outcomes(spy)).join(v.rename("vix"))
    d = d.dropna(subset=["range_next", "absret_next", "vix"])
    d["log_vix"] = np.log(d["vix"])
    d["neg"] = (d["regime"] == "negative").astype(float)
    d["near"] = (d["regime"] == "near_flip").astype(float)
    d["gex_pos"] = (d["net_gex"] > 0).astype(float)
    d["gex_z"] = (d["net_gex"] - d["net_gex"].mean()) / d["net_gex"].std()
    d["dist"] = d["dist_to_flip_pct"].astype(float) * 100
    d["log_range"] = np.log(d["range_next"])
    res["n"] = int(len(d))
    res["regime_counts"] = d["regime"].value_counts().to_dict()
    res["net_gex_positive_share"] = float(d["gex_pos"].mean())
    # T1: next-day range / |return| on VIX alone vs VIX + GEX
    t1 = {}
    for yname, y in (("log_range", d["log_range"]), ("absret_pct", d["absret_next"] * 100)):
        base = ols(y, d[["log_vix"]], ["log_vix"])
        reg = ols(y, d[["log_vix", "neg", "near"]], ["log_vix", "neg", "near"])
        lvl = ols(y, d[["log_vix", "gex_z"]], ["log_vix", "gex_z"])
        sgn = ols(y, d[["log_vix", "gex_pos"]], ["log_vix", "gex_pos"])
        f = d["dist"].notna()                                # days with a flip level (no zero crossing: none)
        dist = ols(y[f], d.loc[f, ["log_vix", "dist"]], ["log_vix", "dist"])
        base_f = ols(y[f], d.loc[f, ["log_vix"]], ["log_vix"])
        allx = ols(y, d[["log_vix", "neg", "near", "gex_z", "gex_pos"]], ["log_vix", "neg", "near", "gex_z", "gex_pos"])
        t1[yname] = {"vix_only": base, "regime": reg, "level": lvl, "sign": sgn, "dist_to_flip": dist,
                     "vix_only_on_flip_days": base_f, "all": allx, "delta_r2_all": allx["r2"] - base["r2"],
                     "delta_r2_dist": dist["r2"] - base_f["r2"]}
    # halves: is the regime coefficient's sign stable?
    half = len(d) // 2
    t1["halves_regime_neg_on_log_range"] = [
        ols(part["log_range"], part[["log_vix", "neg", "near"]], ["log_vix", "neg", "near"])["coef"]["neg"]
        for part in (d.iloc[:half], d.iloc[half:])]
    res["t1"] = t1
    res["raw_by_regime"] = {r: {"n": int(len(x)), "range_next_pct": float(x["range_next"].mean() * 100),
                                "absret_next_pct": float(x["absret_next"].mean() * 100), "vix": float(x["vix"].mean()),
                                "ret_next_pct": float(x["ret_next"].mean() * 100)}
                            for r, x in d.groupby("regime")}
    # VIX-matched: within VIX terciles, positive vs negative
    d["vix_q"] = pd.qcut(d["vix"], 3, labels=["low", "mid", "high"])
    res["range_by_vix_tercile"] = {str(q): {r: {"n": int(len(y)), "range_next_pct": float(y["range_next"].mean() * 100)}
                                            for r, y in x.groupby("regime")}
                                   for q, x in d.groupby("vix_q", observed=True)}
    # T2: premium selling — realised |move| vs the straddle-implied 1-day move
    e = d.dropna(subset=["implied_move_1d"]).copy()
    e["win"] = (e["absret_next"] < e["implied_move_1d"]).astype(float)
    e["edge_pct"] = (e["implied_move_1d"] - e["absret_next"]) * 100
    by = {r: {"n": int(len(x)), "p_realised_below_implied": float(x["win"].mean()),
              "mean_implied_pct": float(x["implied_move_1d"].mean() * 100),
              "mean_realised_pct": float(x["absret_next"].mean() * 100),
              "mean_edge_pct": float(x["edge_pct"].mean())} for r, x in e.groupby("regime")}
    pos, neg = e[e["regime"] == "positive"], e[e["regime"] == "negative"]
    res["t2"] = {"n": int(len(e)), "by_regime": by, "all": float(e["win"].mean()),
                 "pos_vs_neg_rate": two_prop(pos["win"].sum(), len(pos), neg["win"].sum(), len(neg)),
                 "pos_vs_neg_edge": welch(pos["edge_pct"], neg["edge_pct"]),
                 "logit": logit(e["win"], e[["log_vix", "neg", "near"]], ["log_vix", "neg", "near"]),
                 "edge_ols": ols(e["edge_pct"], e[["log_vix", "neg", "near"]], ["log_vix", "neg", "near"])}
    # T3 (direction, the allocator premise): next-day return by regime, and a regime-timed long
    res["t3_direction"] = {"pos_vs_neg_ret": welch(pos["ret_next"] * 100, neg["ret_next"] * 100)}
    r = d["ret_next"]
    timed = r.where(d["regime"] != "negative", 0.0)
    res["t3_direction"]["always_long"] = sharpe(r)
    res["t3_direction"]["long_unless_negative"] = sharpe(timed)
    res["t3_direction"]["exposure_unless_negative"] = float((d["regime"] != "negative").mean())
    # T4: pinning on expiration days (every expiry, K* from its last snapshot ≥ 7 days out)
    res["t4_pinning"] = pinning(g)
    # QQQ / IWM next-day range on the SPY regime (secondary)
    sec = {}
    for name, bars in (("QQQ", qqq), ("IWM", iwm)):
        x = g.join(outcomes(bars)).join(v.rename("vix")).dropna(subset=["range_next", "vix"])
        x["log_vix"], x["neg"], x["near"] = np.log(x["vix"]), (x["regime"] == "negative") * 1.0, (x["regime"] == "near_flip") * 1.0
        base = ols(np.log(x["range_next"]), x[["log_vix"]], ["log_vix"])
        reg = ols(np.log(x["range_next"]), x[["log_vix", "neg", "near"]], ["log_vix", "neg", "near"])
        sec[name] = {"n": int(len(x)), "r2_vix": base["r2"], "r2_with_regime": reg["r2"], "neg": reg["coef"]["neg"],
                     "near": reg["coef"]["near"]}
    res["secondary"] = sec
    # T5: strategy trades split by the prior close's regime
    res["t5_trades"] = trades_by_regime(g)
    return res


def sharpe(r: pd.Series) -> dict:
    r = r.dropna()
    return {"ann_return_pct": float(r.mean() * 252 * 100), "ann_vol_pct": float(r.std() * math.sqrt(252) * 100),
            "sharpe": float(r.mean() / r.std() * math.sqrt(252)) if r.std() else None}


def coverage(g: pd.DataFrame) -> dict:
    import pandas.tseries.offsets as off
    days = pd.bdate_range(g.index.min(), g.index.max())
    have = set(pd.to_datetime(g.index))
    missing = [d.date().isoformat() for d in days if d not in have]
    return {"first": str(g.index.min()), "last": str(g.index.max()), "days": int(len(g)),
            "weekdays_without_a_row": len(missing), "missing_sample": missing[:12]}


def pinning(g: pd.DataFrame) -> dict:
    """For each expiry E seen in the snapshots: K* = the strike with the most proxy OI (calls + puts) on its last
    snapshot day (≥ 7 days before E). Pinning ⇒ on E the close is nearer K* than the mirror strike K' = 2·S0 − K*
    (S0 = spot that snapshot day) more than half the time. Control: the same test one trading day before E."""
    from api.services import gex_history as GH
    raw = GH.add_oi_proxy(GH.load_snapshots("SPY"))
    spot = pd.Series(g["spot"].values, index=pd.to_datetime(pd.Index(g.index)))
    trading = list(spot.index)
    out = {"expiry": [], "day_before": []}
    for e, x in raw.groupby("expiry"):
        last = x["day"].max()
        s0 = spot.get(last)
        if s0 is None or e not in spot.index:
            continue
        snap = x[x["day"] == last]
        by_k = snap.groupby("strike")["oi_proxy"].sum()
        by_k = by_k[(by_k.index > s0 * 0.9) & (by_k.index < s0 * 1.1)]
        if by_k.empty or by_k.max() <= 0:
            continue
        k = float(by_k.idxmax())
        if abs(k - s0) < 1e-9:
            continue
        mirror = 2 * s0 - k
        i = trading.index(e)
        for key, day in (("expiry", e), ("day_before", trading[i - 1] if i > 0 else None)):
            if day is None or day <= last:
                continue
            c = spot[day]
            out[key].append({"closer_to_k": abs(c - k) < abs(c - mirror), "dist_pct": abs(c - k) / c * 100,
                             "monthly": 15 <= e.day <= 21 and e.weekday() in (3, 4)})
    res = {}
    for key, rows in out.items():
        df = pd.DataFrame(rows)
        n, k = len(df), int(df["closer_to_k"].sum())
        res[key] = {"n": n, "share_closer_to_max_oi_strike": k / n if n else None,
                    "binom_p_vs_half": float(stats.binomtest(k, n, 0.5).pvalue) if n else None,
                    "median_dist_pct": float(df["dist_pct"].median()) if n else None}
        m = df[df["monthly"]] if n else df
        if len(m):
            km = int(m["closer_to_k"].sum())
            res[key]["monthly"] = {"n": int(len(m)), "share": km / len(m),
                                   "binom_p": float(stats.binomtest(km, len(m), 0.5).pvalue)}
    return res


TRADES: list[tuple[str, str, float]] = []


def trades_by_regime(g: pd.DataFrame) -> dict:
    from engine.strategy_backtest import run_backtest
    reg = pd.Series(g["regime"].values, index=pd.to_datetime(pd.Index(g.index)))
    out = {}
    for slug, ticker, cap in TRADES:
        try:
            perf = run_backtest(slug, ticker, START.isoformat(), END.isoformat(), cap, report_window=True)
        except Exception as exc:  # noqa: BLE001
            out[slug] = {"error": f"{type(exc).__name__}: {exc}"}
            continue
        tr = perf["trades"].copy()
        if tr.empty:
            out[slug] = {"trades": 0}
            continue
        tr["entry"] = pd.to_datetime(tr["entry_date"])
        # the regime known before the entry: the last snapshot day strictly before the entry day
        prior = reg.reindex(pd.date_range(reg.index.min(), END + _dt.timedelta(days=5))).ffill().shift(1)
        tr["regime"] = tr["entry"].map(prior)
        tr = tr.dropna(subset=["regime"])
        pnl = pd.to_numeric(tr["pnl"], errors="coerce")
        by = {}
        for r, x in tr.groupby("regime"):
            p = pd.to_numeric(x["pnl"], errors="coerce")
            by[r] = {"trades": int(len(x)), "days": int(x["entry"].dt.date.nunique()), "win_rate": float((p > 0).mean()),
                     "avg_pnl": float(p.mean()), "total_pnl": float(p.sum())}
        # per day, so trades within a day are not counted as independent
        day = tr.assign(p=pnl).groupby([tr["entry"].dt.date, "regime"])["p"].sum().reset_index()
        pos, neg = day[day["regime"] == "positive"]["p"], day[day["regime"] == "negative"]["p"]
        out[slug] = {"trades": int(len(tr)), "by_regime": by,
                     "daily_pnl_pos_vs_neg": welch(pos, neg) if len(pos) > 1 and len(neg) > 1 else None}
    return out


# ── the crypto ETF study (IBIT, ETHA) ─────────────────────────────────────────

def gated() -> None:
    """Route this process's requests through the service's request gate."""
    from api.marketdata.limits import Gate
    from data import request_gate
    request_gate.install(Gate())
    request_gate.install_hooks()


def minutes(sym: str) -> pd.DataFrame:
    from db.client import get_engine, get_minute_bars
    df = get_minute_bars(get_engine(), sym, _dt.date(2024, 1, 1), _dt.date.today())
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()
    df["ts"] = pd.to_datetime(df["ts"])
    df["day"] = df["ts"].dt.date
    df["m"] = df["ts"].dt.hour * 60 + df["ts"].dt.minute
    return df.sort_values("ts")


def at(day_bars: pd.DataFrame, minute: int) -> float | None:
    """The close of the last bar that started before ``minute`` (minutes after midnight): the price at that time."""
    x = day_bars[day_bars["m"] < minute]
    return float(x["close"].iloc[-1]) if len(x) else None


def per_day(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for day, b in df.groupby("day"):
        if len(b) < 300:                                          # a half day or a gap
            continue
        o, c = float(b["open"].iloc[0]), float(b["close"].iloc[-1])
        p10, p1100, p1200, p1300, p1400, p1500 = (at(b, m) for m in (600, 660, 720, 780, 840, 900))
        five = b.set_index("ts")["close"].resample("5min").last().dropna()
        r5 = np.log(five / five.shift(1)).dropna()
        rows.append({"day": day, "open": o, "close": c, "high": float(b["high"].max()), "low": float(b["low"].min()),
                     "range_pct": (float(b["high"].max()) - float(b["low"].min())) / o * 100,
                     "rv_ann_pct": float(np.sqrt((r5 ** 2).sum()) * math.sqrt(252) * 100),
                     "r_open30": (p10 / o - 1) * 100 if p10 else None, "r_rest": (c / p10 - 1) * 100 if p10 else None,
                     "p1100": p1100, "p1200": p1200, "p1300": p1300, "p1400": p1400, "p1500": p1500,
                     "weekday": pd.Timestamp(day).weekday()})
    return pd.DataFrame(rows).set_index("day")


def corr_test(x, y) -> dict:
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    r, p = stats.pearsonr(x, y)
    b = np.polyfit(x, y, 1)[0]
    return {"n": int(len(x)), "corr": float(r), "p": float(p), "slope": float(b)}


def continuation(df: pd.DataFrame, k_sigma: float = 1.0) -> dict:
    """30-minute moves in 11:00–14:00 larger than ``k_sigma`` × the trailing 20-day σ of 30-minute returns:
    does the next hour continue (same sign) or revert? One event per day (the first), so days are independent."""
    closes = df.set_index("ts")["close"]
    r30 = closes.resample("30min").last().dropna()
    r30 = (r30 / r30.shift(1) - 1).dropna()
    sig = r30.groupby(r30.index.date).std().rolling(20).mean().shift(1)
    events = []
    for day, b in df.groupby("day"):
        s = sig.get(day)
        if s is None or not np.isfinite(s) or len(b) < 300:
            continue
        px = b.set_index("m")["close"]
        for m in range(660, 841, 5):
            p0, p30, p90 = at(b, m - 30), at(b, m), at(b, m + 60)
            if not (p0 and p30 and p90):
                continue
            move = p30 / p0 - 1
            if abs(move) >= k_sigma * s:
                fwd = (p90 / p30 - 1) * np.sign(move)
                events.append({"day": day, "minute": m, "move_pct": move * 100, "fwd_pct": fwd * 100,
                               "continued": fwd > 0})
                break
    e = pd.DataFrame(events)
    if e.empty:
        return {"n": 0}
    k = int(e["continued"].sum())
    return {"n": int(len(e)), "k_sigma": k_sigma, "continued_share": k / len(e),
            "binom_p_vs_half": float(stats.binomtest(k, len(e), 0.5).pvalue),
            "mean_fwd_in_move_direction_pct": float(e["fwd_pct"].mean()),
            "t_fwd": float(stats.ttest_1samp(e["fwd_pct"], 0.0).statistic),
            "p_fwd": float(stats.ttest_1samp(e["fwd_pct"], 0.0).pvalue)}


def crypto_hourly(sym: str) -> pd.Series:
    """BTC-USD / ETH-USD hourly closes (yfinance, 730 days), US/Eastern naive."""
    import yfinance as yf
    raw = yf.download(sym, period="730d", interval="1h", auto_adjust=False, progress=False, threads=False)
    if raw is None or raw.empty:
        return pd.Series(dtype=float)
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    s = pd.to_numeric(raw["Close"], errors="coerce").dropna()
    idx = pd.to_datetime(s.index)
    idx = idx.tz_convert("US/Eastern") if idx.tz is not None else idx.tz_localize("UTC").tz_convert("US/Eastern")
    s.index = idx.tz_localize(None)
    return s


def weekend_gap(etf_days: pd.DataFrame, coin: pd.Series) -> dict:
    """Monday's opening gap vs the coin's move from Friday 16:00 to Monday 09:30 ET, and whether the gap fades
    during Monday (the ETF only trades 09:30–16:00 on weekdays; the coin trades all weekend)."""
    rows = []
    days = list(etf_days.index)
    for i, d in enumerate(days):
        if i == 0 or pd.Timestamp(d).weekday() != 0:
            continue
        prev = days[i - 1]
        if (pd.Timestamp(d) - pd.Timestamp(prev)).days != 3:        # a plain weekend only
            continue
        fri_close, mon_open, mon_close = etf_days.loc[prev, "close"], etf_days.loc[d, "open"], etf_days.loc[d, "close"]
        c0 = coin[:pd.Timestamp(prev) + pd.Timedelta(hours=16)]
        c1 = coin[:pd.Timestamp(d) + pd.Timedelta(hours=9, minutes=30)]
        if c0.empty or c1.empty:
            continue
        rows.append({"gap_pct": (mon_open / fri_close - 1) * 100, "coin_weekend_pct": (c1.iloc[-1] / c0.iloc[-1] - 1) * 100,
                     "monday_open_to_close_pct": (mon_close / mon_open - 1) * 100})
    x = pd.DataFrame(rows)
    if len(x) < 10:
        return {"n": int(len(x))}
    fit = ols(x["gap_pct"], x[["coin_weekend_pct"]], ["coin_weekend_pct"], lags=0)
    fade = corr_test(x["gap_pct"], x["monday_open_to_close_pct"])
    return {"n": int(len(x)), "gap_on_coin_move": fit, "gap_vs_monday_session": fade,
            "mean_abs_gap_pct": float(x["gap_pct"].abs().mean())}


def strike_pinning(etf_days: pd.DataFrame, expiry_weekdays: tuple, grid: float = 1.0, band: float = 0.10) -> dict:
    """Without open interest there is no max-OI strike to test; the crude version: is the close within ``band`` of a
    strike on the ``grid`` more often on expiration days than on other days (uniform expectation 2·band/grid)?"""
    x = etf_days.copy()
    x["near"] = ((x["close"] / grid).round() * grid - x["close"]).abs() <= band
    exp = x[x["weekday"].isin(expiry_weekdays)]
    other = x[~x["weekday"].isin(expiry_weekdays)]
    return {"expiry_days": {"n": int(len(exp)), "share_near_strike": float(exp["near"].mean())},
            "other_days": {"n": int(len(other)), "share_near_strike": float(other["near"].mean())},
            "uniform_expectation": 2 * band / grid,
            "test": two_prop(int(exp["near"].sum()), len(exp), int(other["near"].sum()), len(other))}


def crypto_study() -> dict:
    from api.services import gex_recorder as REC
    gated()
    out: dict = {}
    coins = {"IBIT": "BTC-USD", "ETHA": "ETH-USD"}
    for sym, coin_sym in coins.items():
        res: dict = {}
        rec = REC.history_rows(sym, "eod", _dt.date(2020, 1, 1))
        res["gex_history_days"] = int(len(rec))
        res["gex_recorded"] = [{"date": str(pd.Timestamp(r.SlotTs).date()), "net_gex": r.NetGex, "flip": r.Flip,
                                "regime": r.Regime, "spot": r.Spot} for r in rec.itertuples(index=False)]
        m = minutes(sym)
        if m.empty:
            res["minute_bars"] = 0
            out[sym] = res
            continue
        d = per_day(m)
        res["minute_bars"] = {"days": int(len(d)), "first": str(d.index.min()), "last": str(d.index.max())}
        res["range_pct"] = {"mean": float(d["range_pct"].mean()), "median": float(d["range_pct"].median())}
        res["rv_ann_pct"] = {"mean": float(d["rv_ann_pct"].mean()), "median": float(d["rv_ann_pct"].median())}
        res["rv_by_weekday"] = {int(k): float(v) for k, v in d.groupby("weekday")["rv_ann_pct"].mean().items()}
        res["open30_vs_rest"] = corr_test(d["r_open30"], d["r_rest"])
        blocks = []
        for a, b, c in (("p1100", "p1200", "p1300"), ("p1200", "p1300", "p1400"), ("p1300", "p1400", "p1500")):
            blocks.append(pd.DataFrame({"x": (d[b] / d[a] - 1) * 100, "y": (d[c] / d[b] - 1) * 100}))
        bl = pd.concat(blocks).dropna()
        res["hour_vs_next_hour_11_to_15"] = corr_test(bl["x"], bl["y"])
        res["continuation_1sigma"] = continuation(m, 1.0)
        res["continuation_2sigma"] = continuation(m, 2.0)
        daily_rows = d[["open", "close", "weekday"]]
        try:
            coin = crypto_hourly(coin_sym)
            res["weekend_gap"] = weekend_gap(daily_rows, coin) if not coin.empty else {"n": 0, "note": "no coin data"}
        except Exception as exc:  # noqa: BLE001
            res["weekend_gap"] = {"error": f"{type(exc).__name__}: {exc}"}
        res["strike_pinning_fridays"] = strike_pinning(daily_rows, (4,), grid=1.0 if sym == "IBIT" else 0.5,
                                                       band=0.10 if sym == "IBIT" else 0.05)
        out[sym] = res
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("part", choices=["spy", "crypto"])
    ap.add_argument("--out")
    ap.add_argument("--trades", nargs="*", default=[], help="slug:ticker:capital, split by regime (spy part)")
    a = ap.parse_args(argv)
    for t in a.trades:
        slug, ticker, cap = t.split(":")
        TRADES.append((slug, ticker, float(cap)))
    from api.bootstrap import bootstrap
    bootstrap()
    strict_read_only()
    res = spy_study() if a.part == "spy" else crypto_study()
    text = json.dumps(res, indent=1, default=str)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
