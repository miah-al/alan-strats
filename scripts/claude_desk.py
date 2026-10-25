"""
python -m scripts.claude_desk <command> -- the desk Claude trades NDX 0DTE from, discretionary, on PAPER only.

No algorithm: Claude reads the snapshot, decides, and says why. The rails below are code, not judgment, and every
order goes through the service's paper order book (POST /api/orders, account "paper"; ``account: live`` is refused
there and nothing in the service talks to a broker's order API). Strategy name in the ledger: claude_discretionary.

Rails (agreed 2026-09-28; since 2026-09-29 the trader's, in the service's database: the app's Limits page or
GET/PUT /api/limits/claude_discretionary, read before every command and every feed poll; the values below are the
defaults):
  - NDXP same-day options, defined risk only (preview's max loss must be finite), at most 4 legs;
  - at most 2 lots, at most $2,500 at risk per position, at most ``max_positions`` positions at once (2 from
    2026-10-26, the owner on 10/23: "2 positions, $2,500 each"; a ratio pair is one position);
  - new entries 09:45-15:30 ET only;
  - day stop: at -$2,500 (realised + marked) everything is closed and the desk is done for the day (``guard``);
  - anything still open at 15:55 is closed (``guard``): nothing is left to settle unattended.
Every open and close is journaled BEFORE the order goes: the thesis, the exit plan and what would prove it wrong.

Commands:
  snapshot [--news]                 market, the level map (opening range, VWAP, yesterday's H/L/C, gamma walls /
                                    flip / max pain), my book, candidate spreads, the rails; new posts and official releases
                                    every 10 minutes (or now, with --news); headlines are the news desk's (claude_news)
  open --leg buy:C:30250 --leg sell:C:30275 [--lots 1] --thesis ... --exit ... --wrong ...
  pair --ndx sell:P:30650,buy:P:30625 [--ndx-lots 1] --spx sell:C:7835,buy:C:7840 [--spx-lots 2] --thesis ... --exit ...
       --wrong ...                  the NDX/SPX ratio trade (2026-10-12, the owner: "take over ratio into your desk, get
                                    in get out"): an NDXP spread and an SPXW spread opened together as ONE position.
                                    Under premium_only both are credit spreads: the ratio up (NDX to catch up) is an
                                    NDX put credit spread with an SPX call credit spread, the ratio down the mirror. Their
                                    max losses together must fit the per-position rail; close / guard treat them as one
  open|pair ... --style clone|ratio the AI agent's own strategies (2026-10-20, the owner: "i want the AI Agent to trade
                                    the clone strategy", "and also the ratio strategy", "all decisions on the fly by
                                    AI", "the AI Agents are super experts"): the agent decides on the fly from the
                                    news, the levels, the tape and the clone / ratio robots' calls (signals that book
                                    nothing), and the stop-table gate, built for premium held to expiry, does not
                                    second-guess it. Every hard rail still holds (lots, risk, positions, trades a day,
                                    hours, the day stop, premium only, no in-the-money short, live two-sided quotes)
  condor                            read-only: the SPX 13:00 iron condor menu (2026-10-25, the owner: "Need a AI
                                    assisted iron condor strategy", "Its goes to the desk", "An agent runs it"): the
                                    live 13:00 straddle, the call side by the SPX 13:00 v2 rule and the far put side,
                                    both scaled to the straddle, their mid and natural credits, max loss, month-end
  open ... --under SPX --style condor   the agent's SPX iron condor (or one side), 12:58-13:30, every rail holds
  trim --lots N --reason ... [--tg TG]   take N lots off (an offsetting order: the paper book closes groups whole);
                                    with two positions open, --tg names which
  close --reason ... [--tg TG]      close one position (--tg: its trade group, with its pair leg and trims) or, without
                                    --tg, every open claude_discretionary position, at market (paper mid)
  note --text ...                   journal a decision (standing aside is a decision)
  guard                             enforce the day stop and the 15:55 flat; prints what it did
  feed                              for the Monitor tool: guard every 30 s, a snapshot every 2 minutes 09:45-15:45,
                                    the day's summary after 15:55
  summary                           the day's trades and P&L (paper, and after the measured crossing cost)
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

BASE = "http://127.0.0.1:8765/api"
SLUG = "claude_discretionary"
UNDER, ROOT = "NDX", "NDXP"
ROOTS = {"NDX": "NDXP", "SPX": "SPXW"}          # the PM-settled same-day roots; SPX only as a ratio pair's second leg
# The rails. These are the fallbacks: the values in force are the trader's, in the service's database (app.TradeLimit,
# set on the app's Limits page or PUT /api/limits/claude_discretionary/<name>), read before every command and on every
# feed poll (apply_limits). The desk never changes them itself.
MAX_LOTS, MAX_RISK, DAY_STOP, MAX_POSITIONS = 2, 2500.0, -2500.0, 2
MAX_TRADES = 3                                  # new positions per day (a trim or a close is not one)
PREMIUM_ONLY = True                             # sell premium only: a debit structure is refused (agreed 2026-10-01)
ENTRY_START, ENTRY_END, FLAT_AT, FEED_END = "09:45", "15:30", "15:55", "16:00"
NY = "America/New_York"
STATE_DIR = Path(__file__).resolve().parents[1] / "paper_state" / "claude_desk"
NEWS_EVERY_S = 600


# ── plumbing ──────────────────────────────────────────────────────────────────

def apply_limits() -> None:
    """Take the limits in force from the service (GET /api/limits/<SLUG>). If it cannot answer, the last values stay:
    the desk cannot trade without the service anyway."""
    global MAX_LOTS, MAX_RISK, DAY_STOP, MAX_POSITIONS, MAX_TRADES, PREMIUM_ONLY, ENTRY_START, ENTRY_END, FLAT_AT
    try:
        v = api("GET", f"/limits/{SLUG}", timeout=10.0).get("values") or {}
    except Exception:  # noqa: BLE001
        return
    MAX_LOTS = int(v.get("max_lots", MAX_LOTS))
    MAX_RISK = float(v.get("max_risk", MAX_RISK))
    DAY_STOP = -abs(float(v.get("day_stop", DAY_STOP)))
    MAX_POSITIONS = int(v.get("max_positions", MAX_POSITIONS))
    MAX_TRADES = int(v.get("max_trades", MAX_TRADES))
    PREMIUM_ONLY = bool(int(float(v.get("premium_only", 1 if PREMIUM_ONLY else 0))))
    ENTRY_START = str(v.get("entry_start", ENTRY_START))
    ENTRY_END = str(v.get("entry_end", ENTRY_END))
    FLAT_AT = str(v.get("flat_at", FLAT_AT))


def now_et() -> pd.Timestamp:
    return pd.Timestamp.now(tz=NY)


def hm(t: pd.Timestamp) -> str:
    return t.strftime("%H:%M")


def api(method: str, path: str, body: dict | None = None, timeout: float = 20.0):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"{method} {path}: HTTP {e.code} {detail}") from None


def state_path(day: date) -> Path:
    return STATE_DIR / f"state_{day.isoformat()}.json"


def load_state(day: date) -> dict:
    p = state_path(day)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"done": False, "positions": {}, "last_news": None, "closed": []}


def save_state(day: date, st: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state_path(day).write_text(json.dumps(st, indent=1, default=str), encoding="utf-8")


def journal(day: date, text: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    p = STATE_DIR / f"journal_{day.isoformat()}.md"
    if not p.exists():
        p.write_text(f"# Claude's desk, {day.isoformat()} (paper, NDXP 0DTE, discretionary)\n\n", encoding="utf-8")
    with p.open("a", encoding="utf-8") as f:
        f.write(text.rstrip() + "\n\n")


def occ(cp: str, strike: float, day: date, root: str = ROOT) -> str:
    return f"{root}{day:%y%m%d}{cp}{int(round(strike * 1000)):08d}"


def rows(payload) -> list[dict]:
    if isinstance(payload, dict):
        for k in ("rows", "data", "items"):
            if isinstance(payload.get(k), list):
                return payload[k]
    return payload if isinstance(payload, list) else []


# ── the book ──────────────────────────────────────────────────────────────────

def my_positions(status: str = "open") -> list[dict]:
    return [r for r in rows(api("GET", f"/paper/positions?status={status}")) if r.get("strategy") == SLUG]


def day_pnl(day: date) -> tuple[float, float, list[dict]]:
    """(realised today, marked on the open positions, the open positions)."""
    opened = my_positions("open")
    closed = [r for r in my_positions("closed") if str(r.get("closed") or "")[:10] == day.isoformat()]
    realised = sum(float(r.get("pnl") or 0) for r in closed)
    marked = sum(float(r.get("pnl") or 0) for r in opened)
    return realised, marked, opened


def crossing_cost(legs: list[dict], spot: float, under: str = UNDER) -> float:
    """Points per unit the live runners would pay to cross, on one side (the measured model: 1.2 when a vertical's
    long leg is 25+ in the money, 0.1 nearer). Legs pair into verticals by right; an unpaired leg counts as near.
    SPXW verticals: 0.1 a vertical (live 5- and 10-wide quotes run about 0.15 wide)."""
    if under == "SPX":
        return 0.1 * max(1, len(legs) // 2)
    cost = 0.0
    for cp in ("C", "P"):
        longs = [l for l in legs if l["cp"] == cp and l["side"] == "buy"]
        shorts = [l for l in legs if l["cp"] == cp and l["side"] == "sell"]
        for lg in longs[:max(len(shorts), 1)] if shorts else longs:
            itm = (spot - lg["strike"]) if cp == "C" else (lg["strike"] - spot)
            cost += 1.2 if itm >= 25 else 0.1
        cost += 0.1 * max(0, len(shorts) - len(longs))
    return cost


def order_body(legs: list[dict], lots: int, day: date, label: str, under: str = UNDER) -> dict:
    root = ROOTS[under]
    return {"account": "paper", "underlying": under, "order_type": "market", "tif": "day", "strategy": SLUG,
            "label": label[:200], "client_order_id": f"claude-{uuid.uuid4().hex[:12]}",
            "legs": [{"type": "call" if l["cp"] == "C" else "put", "strike": l["strike"], "expiry": day.isoformat(),
                      "side": l["side"], "quantity": lots, "symbol": occ(l["cp"], l["strike"], day, root)} for l in legs]}


def preview(legs: list[dict], lots: int, day: date, under: str = UNDER) -> dict:
    return api("POST", "/orders/preview", order_body(legs, lots, day, "preview", under))


def parse_leg(s: str) -> dict:
    side, cp, k = s.split(":")
    side, cp = side.lower(), cp.upper()[0]
    if side not in ("buy", "sell") or cp not in ("C", "P"):
        raise SystemExit(f"bad leg {s!r}: use buy|sell:C|P:strike")
    return {"side": side, "cp": cp, "strike": float(k)}


def parse_legs(s: str) -> list[dict]:
    """``sell:P:30650,buy:P:30625`` -> two legs (the pair command's per-index spreads)."""
    return [parse_leg(x.strip()) for x in s.split(",") if x.strip()]


# ── market ────────────────────────────────────────────────────────────────────

def quote(t: str) -> dict:
    try:
        return api("GET", f"/market/quote/{t}")
    except Exception:
        return {}


def market() -> dict:
    ndx, vix, vxn = quote("NDX"), quote("VIX"), quote("VXN")
    out = {"spot": ndx.get("last") or ndx.get("close"), "prev": ndx.get("prev_close"), "open": ndx.get("open"),
           "high": ndx.get("high"), "low": ndx.get("low"), "vix": vix.get("last"), "vix_chg": vix.get("change"),
           "vxn": vxn.get("last"), "vxn_chg": vxn.get("change")}
    try:
        intr = api("GET", "/market/intraday/NDX?minutes=60&interval=1")
        c = [float(x) for x in (intr.get("c") or []) if x is not None]
        if c:
            out["m10"] = c[-1] - c[-11] if len(c) > 10 else None
            out["m30"] = c[-1] - c[-31] if len(c) > 30 else None
            out["m60"] = c[-1] - c[0]
            out["src"] = intr.get("vendor") or intr.get("source")
        h = [float(x) for x in (intr.get("h") or []) if x is not None]
        lo = [float(x) for x in (intr.get("l") or []) if x is not None]
        for k, n in (("range10", 10), ("range30", 30)):           # the realised noise a stop must clear
            if len(h) >= n and len(lo) >= n:
                out[k] = max(h[-n:]) - min(lo[-n:])
    except Exception:
        pass
    return out


def levels(spot: float | None) -> list[str]:
    """The level map a day trader keeps: the opening range (09:30-10:00), VWAP (QQQ's, volume-weighted, scaled to
    NDX: the index has no volume), yesterday's high / low / close, and the dealer gamma levels (call and put walls,
    the flip, max pain). Each source is optional: a missing one is left out, never guessed."""
    L = []
    today = now_et().date()
    try:
        nd = api("GET", "/market/intraday/NDX?minutes=390&interval=1")
        t = pd.to_datetime(nd["t"])
        orng = [(h, l) for ts, h, l in zip(t, nd["h"], nd["l"])
                if ts.date() == today and ts.hour == 9 and h is not None and l is not None]
        if orng:
            L.append(f"OR {max(h for h, _ in orng):,.0f}/{min(l for _, l in orng):,.0f}")
    except Exception:
        pass
    try:
        q = api("GET", "/market/intraday/QQQ?minutes=390&interval=1")
        tq = pd.to_datetime(q["t"])
        pv = v = 0.0
        for ts, h, l, c, vol in zip(tq, q["h"], q["l"], q["c"], q.get("v") or []):
            if ts.date() == today and None not in (h, l, c, vol) and vol > 0:
                pv += (h + l + c) / 3.0 * vol; v += vol
        last_q = next((c for c in reversed(q["c"]) if c is not None), None)
        if v > 0 and spot and last_q:
            L.append(f"VWAP~{pv / v * spot / last_q:,.0f}")
    except Exception:
        pass
    try:
        b = api("GET", f"/market/bars/NDX?from={(today - timedelta(days=7)).isoformat()}")
        prior = [i for i, d in enumerate(b["t"]) if str(d)[:10] < today.isoformat()]
        if prior:
            i = prior[-1]
            L.append(f"yday H {b['h'][i]:,.0f} L {b['l'][i]:,.0f} C {b['c'][i]:,.0f}")
    except Exception:
        pass
    try:
        g = api("GET", "/market/gex/NDX", timeout=30)
        parts = [f"{k.replace('_', ' ')} {g[k]:,.0f}" for k in ("call_wall", "put_wall", "flip", "max_pain")
                 if isinstance(g.get(k), (int, float))]
        if parts:
            L.append("gamma: " + ", ".join(parts) + (f" ({g.get('regime')})" if g.get("regime") else ""))
    except Exception:
        pass
    try:
        line = spx_walls_in_ndx(api("GET", "/market/gex/SPX", timeout=30), spot)
        if line:
            L.append(line)
    except Exception:
        pass
    return L


def spx_walls_in_ndx(g: dict, ndx_spot: float | None) -> str:
    """The S&P's dealer gamma levels (SPX's call and put walls, flip and max pain) in NDX points, at the live NDX/SPX
    ratio: most of the market's dealer gamma sits in SPX, so its walls can cap or pin NDX too (the owner, 2026-09-30:
    "ndx based on spx wall"). "" when either spot is missing."""
    spx = g.get("spot") if isinstance(g, dict) else None
    if not ndx_spot or not isinstance(spx, (int, float)) or spx <= 0:
        return ""
    r = float(ndx_spot) / float(spx)
    parts = [f"{k.replace('_', ' ')} {g[k] * r:,.0f} ({g[k]:,.0f})" for k in ("call_wall", "put_wall", "flip", "max_pain")
             if isinstance(g.get(k), (int, float))]
    if not parts:
        return ""
    return "SPX gamma in NDX pts: " + ", ".join(parts) + (f" (SPX {g.get('regime')})" if g.get("regime") else "")


def trades_today(st: dict) -> int:
    """New positions opened today (a trim's offsetting group is not a trade; a ratio pair's SPX leg is part of its
    NDX leg's trade)."""
    return sum(1 for m in (st.get("positions") or {}).values() if not m.get("trim_of") and not m.get("pair_of"))


def n_positions(opened: list[dict], st: dict) -> int:
    """Open positions, not trade groups: a ratio pair's SPX leg and a trim's offsetting group belong to their parent."""
    meta = st.get("positions") or {}
    return sum(1 for r in opened
               if not (meta.get(str(r.get("trade_group_id"))) or {}).get("pair_of")
               and not (meta.get(str(r.get("trade_group_id"))) or {}).get("trim_of"))


def linked_groups(tg: str, st: dict) -> set[str]:
    """``tg``'s whole position: its parent, the parent's ratio-pair leg and every trim of either."""
    meta = st.get("positions") or {}
    m = meta.get(str(tg)) or {}
    base = str(m.get("pair_of") or m.get("trim_of") or tg)
    out = {base}
    if (meta.get(base) or {}).get("pair"):
        out.add(str(meta[base]["pair"]))
    out |= {g for g, x in meta.items() if str(x.get("pair_of") or "") == base}
    out |= {g for g, x in meta.items() if str(x.get("trim_of") or "") in out}
    return out


def ratio_stats(ndx: float, spx: float, prev: float | None, opened: float | None, hist: pd.Series) -> dict:
    """The NDX/SPX ratio now against the prior closes, the open and its recent history (``hist``: the ratio on the
    intraday bars both indexes share, oldest first). Changes are in basis points of the ratio; z is the current ratio
    against that history's mean and spread (log terms)."""
    r = ndx / spx
    out = {"ndx": ndx, "spx": spx, "ratio": r}
    if prev:
        out["day_bp"] = (r / prev - 1.0) * 1e4
    if opened:
        out["open_bp"] = (r / opened - 1.0) * 1e4
    h = pd.to_numeric(hist, errors="coerce").dropna() if hist is not None else pd.Series(dtype=float)
    if len(h) >= 20:
        lg = h.map(math.log)
        sd = float(lg.std(ddof=1))
        out["z"] = (math.log(r) - float(lg.mean())) / sd if sd > 0 else None
        out["hist_lo_bp"] = (float(h.min()) / r - 1.0) * 1e4
        out["hist_hi_bp"] = (float(h.max()) / r - 1.0) * 1e4
        out["hist_n"] = len(h)
        out["hist_last"] = str(h.index[-1])[11:16] if hasattr(h.index[-1], "hour") else ""
    return out


def ratio_now(minutes: int = 120) -> dict:
    """``ratio_stats`` from the live quotes and the service's intraday bars (the bars can lag: yfinance's SPX runs
    about 15 minutes behind, so the history ends at the last minute both indexes have)."""
    n, s = quote("NDX"), quote("SPX")
    try:
        nl, sl = float(n.get("last") or n.get("close")), float(s.get("last") or s.get("close"))
    except (TypeError, ValueError):
        return {}
    prev = (float(n["prev_close"]) / float(s["prev_close"])) if n.get("prev_close") and s.get("prev_close") else None
    opened = (float(n["open"]) / float(s["open"])) if n.get("open") and s.get("open") else None
    hist = pd.Series(dtype=float)
    try:
        bars = {}
        for t in ("NDX", "SPX"):
            b = api("GET", f"/market/intraday/{t}?minutes={minutes}&interval=1")
            bars[t] = pd.Series([float(x) if x is not None else float("nan") for x in (b.get("c") or [])],
                                index=pd.to_datetime(b.get("t") or []))
        both = pd.concat(bars, axis=1).dropna()
        hist = both["NDX"] / both["SPX"]
    except Exception:  # noqa: BLE001 - the live ratio stands without its history
        pass
    return ratio_stats(nl, sl, prev, opened, hist)


def ratio_line(rs: dict) -> str:
    if not rs:
        return "ratio: no NDX/SPX quote"
    parts = [f"ratio NDX/SPX {rs['ratio']:.4f} (NDX {rs['ndx']:,.0f} / SPX {rs['spx']:,.2f})"]
    if rs.get("day_bp") is not None:
        parts.append(f"day {rs['day_bp']:+.0f} bp")
    if rs.get("open_bp") is not None:
        parts.append(f"since open {rs['open_bp']:+.0f} bp")
    if rs.get("z") is not None:
        parts.append(f"z {rs['z']:+.1f} vs the last {rs['hist_n']} common bars (to {rs.get('hist_last')}; range "
                     f"{rs['hist_lo_bp']:+.0f}..{rs['hist_hi_bp']:+.0f} bp from now)")
    return " | ".join(parts)


def ratio_menu(ndx: float, spx: float) -> list[tuple[str, list[tuple[str, str, float]], list[tuple[str, str, float]]]]:
    """The two credit-spread pairs the premium-only desk can express the ratio with: (name, NDX legs, SPX legs).
    'ratio up' bets NDX catches up with SPX: an NDX put credit spread (short at the first 25-pt strike below NDX, 25
    wide) with an SPX call credit spread (short at the first 5-pt strike above SPX, 5 wide). 'ratio down' is the
    mirror. The desk sizes them 1 NDX lot and 2 SPX lots, so the SPX side carries about 0.6 of the NDX side's
    dollar move near the money: a ratio bet with a tilt to NDX's direction."""
    kp = math.floor(ndx / 25.0) * 25.0
    kc = math.ceil(ndx / 25.0) * 25.0
    sc = math.ceil(spx / 5.0) * 5.0
    sp = math.floor(spx / 5.0) * 5.0
    return [("ratio up", [("sell", "P", kp), ("buy", "P", kp - 25.0)], [("sell", "C", sc), ("buy", "C", sc + 5.0)]),
            ("ratio down", [("sell", "C", kc), ("buy", "C", kc + 25.0)], [("sell", "P", sp), ("buy", "P", sp - 5.0)])]


#: the Friend Clone (ndx_0dte_friend_real) belongs to this desk from 2026-10-13 (the owner: "take over friend clone
#: as well ... it belongs to your desk now"). It stays a SHADOW runner (books nothing; its own decisions lost even at
#: the mid in three years of tests) and its calls are an input here: a "bull" call (a dip fade) is expressed, when my
#: own read agrees, as an out-of-the-money put credit spread below support; a "bear" call as a call credit spread
#: above resistance.
CLONE_LOGS = Path(__file__).resolve().parents[1] / "paper_state" / "runner_logs" / "arm"
CLONE_EVENT = re.compile(r"ALERT (\d\d:\d\d) (open|add|close) (bull|bear) ([\d.]+)/([\d.]+) @ ([\d.]+)(?: \(([^)]*)\))?")


def clone_events(lines) -> list[dict]:
    """The clone runner's trade events from its log lines (``ALERT hh:mm open|add|close bull|bear lo/hi @ px``)."""
    out = []
    for ln in lines:
        m = CLONE_EVENT.search(ln)
        if m:
            out.append({"at": m.group(1), "action": m.group(2), "side": m.group(3), "k_lo": float(m.group(4)),
                        "k_hi": float(m.group(5)), "px": float(m.group(6)), "why": (m.group(7) or "")[:60]})
    return out


def clone_line(day: date, now_hm: str, logs: Path | None = None) -> str:
    """The clone's latest call today, for the snapshot: what it did, how fresh, and how the desk would express it."""
    folder = logs or CLONE_LOGS
    files = sorted(folder.glob(f"ndx_0dte_friend_real_{day.isoformat()}_*.log")) if folder.exists() else []
    if not files:
        return "clone (shadow): not running today"
    try:
        ev = clone_events(files[-1].read_text(encoding="utf-8", errors="replace").splitlines())
    except OSError:
        return "clone (shadow): log unreadable"
    if not ev:
        return "clone (shadow): no call yet today"
    e = ev[-1]
    opens = sum(1 for x in ev if x["action"] == "open")
    h, m = map(int, e["at"].split(":")); nh, nm = map(int, now_hm.split(":"))
    age = (nh * 60 + nm) - (h * 60 + m)
    fresh = "FRESH" if 0 <= age <= 10 else f"{age} min ago"
    hint = ""
    if e["action"] in ("open", "add"):
        hint = (" -> desk: if my read agrees, sell an OTM put credit spread below support" if e["side"] == "bull"
                else " -> desk: if my read agrees, sell an OTM call credit spread above resistance")
    return (f"clone (shadow): {e['at']} {e['action']} {e['side']} {e['k_lo']:.0f}/{e['k_hi']:.0f} @ {e['px']:.2f} "
            f"[{fresh}; {opens} calls today]{hint}")


#: how far a pair's short strike may sit in the money (index points) before ``pair`` refuses it
ITM_TOLERANCE = {"NDX": 5.0, "SPX": 2.0}


def itm_short(legs: list[dict], spot: float | None, under: str) -> str | None:
    """Why a pair leg is refused: its short strike is in the money by more than ``ITM_TOLERANCE``. A short put spread
    sold above the index (or a call spread below it) is worth more every minute the index sits between its strikes:
    on 2026-10-12 the 30650/30625 put spread, sold 22 points in the money to fit the risk rail, lost $334 while NDX
    sat at 30,625, where the out-of-the-money 30625/30600 would have made about $317 by 15:24. Fit the rail by
    shrinking the SPX leg, never by moving the short strike into the money."""
    if spot is None:
        return None
    tol = ITM_TOLERANCE.get(under, 0.0)
    for l in legs:
        if l["side"] != "sell":
            continue
        depth = (float(spot) - l["strike"]) if l["cp"] == "C" else (l["strike"] - float(spot))
        if depth > tol:
            return (f"{under} short {l['cp']}{l['strike']:.0f} is {depth:.0f} points in the money (index {float(spot):,.2f}); "
                    f"the desk sells out-of-the-money spreads (fit the rail with fewer lots instead)")
    return None


#: A leg whose symbol was dropped and is wanted again can serve its last, minutes-old quote first, still marked
#: tastytrade. On 2026-10-13 the SPXW 7770 call previewed 29.0/29.3, then 20.4/20.5 three seconds later, and the menu
#: showed a 5-wide call spread at a 7.05 credit. An entry therefore previews twice, SETTLE_S apart, and is refused while
#: any leg's mid moves more than LEG_JUMP points between the two (more than the index can move a leg in that time).
SETTLE_S = 3.0
LEG_JUMP = {"NDX": 5.0, "SPX": 1.0}


def vertical_width(legs: list[dict]) -> float | None:
    """The strike width of a plain two-leg vertical (one type, one leg bought and one sold), else None."""
    if len(legs) != 2 or legs[0]["cp"] != legs[1]["cp"] or legs[0]["side"] == legs[1]["side"]:
        return None
    return abs(float(legs[0]["strike"]) - float(legs[1]["strike"]))


def quote_problems(first: dict, second: dict, legs: list[dict], under: str) -> list[str]:
    """Why the quotes behind an entry can't be trusted yet (empty when they can): a leg without a sane two-sided quote,
    a leg whose mid jumped between the two previews (a stale quote just replaced by a live one), a vertical whose net
    is not between 0 and its width, or a "max loss" that is no loss. Any of these makes a paper fill a fake one."""
    why = []
    jump = LEG_JUMP.get(under, 1.0)
    before = {l.get("symbol"): l for l in first.get("legs") or []}
    for l in second.get("legs") or []:
        sym, bid, ask, mid = l.get("symbol"), l.get("bid"), l.get("ask"), l.get("mid")
        if bid is None or ask is None or float(ask) <= 0 or float(bid) < 0 or float(ask) < float(bid):
            why.append(f"{sym}: no sane two-sided quote ({bid}/{ask})")
            continue
        was = (before.get(sym) or {}).get("mid")
        if was is not None and mid is not None and abs(float(mid) - float(was)) > jump:
            why.append(f"{sym} quote still settling ({float(was):.2f} -> {float(mid):.2f} in {SETTLE_S:.0f} s): retry")
    net, width = second.get("net_mid"), vertical_width(legs)
    if net is not None and width is not None and not 0 < abs(float(net)) < width:
        why.append(f"net {float(net):.2f} is not between 0 and {width:g} for a {width:g}-wide vertical "
                   f"(a stale or missing leg quote)")
    ml, mp = second.get("max_loss"), second.get("max_profit")
    if ml is not None and float(ml) >= 0:
        why.append(f"max loss {float(ml):,.0f} is no loss: the quotes are wrong")
    if mp is not None and float(mp) <= 0:
        why.append(f"max profit {float(mp):,.0f} is no profit: the quotes are wrong")
    return why


def shown_net(pv: dict, legs: list[dict]) -> str:
    """A menu's net, flagged when it can't be right for a vertical (see ``quote_problems``)."""
    net, width = pv.get("net_mid"), vertical_width(legs)
    if net is not None and width is not None and not 0 < abs(float(net)) < width:
        return f"{net} (quotes settling)"
    return str(net)


# ── the judgment gate (2026-10-13, the owner: "Improve judgement process") ─────────────────────────────────────────
#: P(NDX touches a level S points away before 15:40), by entry time, by how wild the day already is (its range so far,
#: cut at that time's terciles) and by S: 743 sessions of NDX minute bars, 2023-10 to 2026-09. On 2026-10-13 two
#: short call spreads were stopped by ordinary squeezes: their stops sat where this table says half the days reach.
STOP_TABLE_PATH = Path(__file__).resolve().parent / "data" / "ndx_stop_table.json"
MAX_STOP_HIT = 0.25            # a stop touched more often than this sits inside the day's noise
MIN_EDGE = 10.0                # $ a lot the stop-adjusted expectation must clear
WILD_MIN_STOP = 150.0          # on a wild day a short-premium stop must be at least this far from the index
KEEP = 0.8                     # the share of the credit kept when the stop is not touched (flat at 15:40, not expiry)
_TABLE: dict | None = None


def stop_table() -> dict:
    global _TABLE
    if _TABLE is None:
        _TABLE = json.loads(STOP_TABLE_PATH.read_text(encoding="utf-8"))
    return _TABLE


def _minutes(hmn: str) -> int:
    return int(hmn[:2]) * 60 + int(hmn[3:5])


def table_cell(hmn: str, table: dict | None = None) -> dict:
    times = (table or stop_table())["times"]
    return times[min(times, key=lambda x: abs(_minutes(x) - _minutes(hmn)))]


def wildness(hmn: str, range_day: float | None, table: dict | None = None) -> str:
    """calm / mid / wild: the day's range so far against that entry time's terciles in the table's history (NDX
    points for the NDX table, ratio bp for the ratio table)."""
    if range_day is None:
        return "mid"
    q1, q2 = table_cell(hmn, table)["wild_cuts"]
    return "calm" if range_day <= q1 else ("mid" if range_day <= q2 else "wild")


def stop_hit_prob(hmn: str, side: str, dist: float, range_day: float | None, table: dict | None = None) -> float:
    """P(a level ``dist`` away is touched before 15:40: ``side`` "up" for a call spread's stop, "down" for a put
    spread's; NDX points by default, ratio bp with the ratio table), interpolated in the table; nearer than its
    first row counts as that row, and past its last row the tail carries on geometrically (a flat tail priced a
    329-point stop like a 200-point one, 2026-10-19)."""
    tab = table or stop_table()
    ps, s = table_cell(hmn, tab)[side][wildness(hmn, range_day, tab)], tab["S"]
    if dist <= s[0]:
        return float(ps[0])
    for (s0, p0), (s1, p1) in zip(zip(s, ps), zip(s[1:], ps[1:])):
        if dist <= s1:
            return float(p0 + (p1 - p0) * (dist - s0) / (s1 - s0))
    decay = min(0.9, ps[-1] / ps[-2]) if ps[-2] > 0 else 0.9
    return float(ps[-1]) * decay ** ((dist - s[-1]) / (s[-1] - s[-2]))


def finish_beyond_prob(hmn: str, side: str, dist: float, range_day: float | None) -> float:
    """P(NDX settles ``dist`` points or more beyond where it is now): half the chance that level is touched (the
    reflection principle)."""
    return 0.5 * stop_hit_prob(hmn, side, dist, range_day)


def zone_outcomes(hmn: str, side: str, short_dist: float, width: float, stop_dist: float,
                  range_day: float | None, step: float = 5.0) -> list[tuple[float, float]]:
    """[(probability, intrinsic)] of settling between a vertical's short strike and a stop beyond it without ever
    touching the stop: a path that touched the stop and came back is the stop's (its mass is the reflection, the
    settlements as far beyond the stop). Nothing when the stop sits inside the short strike."""
    out, x = [], short_dist
    while x < stop_dist - 1e-9:
        hi = min(x + step, stop_dist)
        mass = (finish_beyond_prob(hmn, side, x, range_day) - finish_beyond_prob(hmn, side, hi, range_day)
                - (finish_beyond_prob(hmn, side, 2 * stop_dist - hi, range_day)
                   - finish_beyond_prob(hmn, side, 2 * stop_dist - x, range_day)))
        if mass > 0:
            out.append((mass, min(max((x + hi) / 2 - short_dist, 0.0), width)))
        x = hi
    return out


def safe_stop(hmn: str, side: str, range_day: float | None, table: dict | None = None) -> float | None:
    """The nearest stop distance the table puts at or under MAX_STOP_HIT."""
    tab = table or stop_table()
    ps, s = table_cell(hmn, tab)[side][wildness(hmn, range_day, tab)], tab["S"]
    return next((float(d) for d, p in zip(s, ps) if p <= MAX_STOP_HIT), None)


#: P(the NDX/SPX ratio, ln NDX - ln SPX, moves S bp before 15:40), by entry time, by how wild the ratio's day already
#: is and by S: 499 sessions of NDX and SPX minute bars, 2024-10 to 2026-10 (scripts/data/ratio_stop_table.json). A
#: pair's stop is a ratio move against it (2026-10-15, the owner: the expert trades the ratio by judgment).
RATIO_TABLE_PATH = Path(__file__).resolve().parent / "data" / "ratio_stop_table.json"
_RATIO_TABLE: dict | None = None


def ratio_table() -> dict:
    global _RATIO_TABLE
    if _RATIO_TABLE is None:
        _RATIO_TABLE = json.loads(RATIO_TABLE_PATH.read_text(encoding="utf-8"))
    return _RATIO_TABLE


def ratio_range_today() -> float | None:
    """The ratio's range so far today in bp of ln NDX - ln SPX, from the service's intraday bars (SPX can lag)."""
    try:
        bars = {}
        for t in ("NDX", "SPX"):
            b = api("GET", f"/market/intraday/{t}?minutes=400&interval=1")
            bars[t] = pd.Series([float(x) if x is not None else float("nan") for x in (b.get("c") or [])],
                                index=pd.to_datetime(b.get("t") or []))
        both = pd.concat(bars, axis=1).dropna()
        both = both[both.index.date == both.index[-1].date()]
        if len(both) < 10:
            return None
        r = (both["NDX"].map(math.log) - both["SPX"].map(math.log)) * 1e4
        return float(r.max() - r.min())
    except Exception:  # noqa: BLE001 - no range: the table's middle tercile
        return None


def pair_bet(ndx_legs: list[dict]) -> str | None:
    """"up" when the pair bets the ratio rises (its NDX vertical sells puts), "down" when it sells NDX calls."""
    shorts = [l for l in ndx_legs if l["side"] == "sell"]
    return None if not shorts else ("up" if shorts[0]["cp"] == "P" else "down")


def judge_pair(ndx_legs: list[dict], stop_bp: float | None, t: pd.Timestamp, range_bp: float | None,
               credit_usd: float | None, min_credit_usd: float | None) -> tuple[dict, list[str]]:
    """The judgment gate for a ratio pair: its stop is a ratio move against the bet (``stop_bp``), refused when the
    ratio table says it is touched more than MAX_STOP_HIT of the time; and the pair's credit must reach the one judged.
    A ratio stop does not pin either index's level, so there is no repricing at the stop (the NDX gate's expectation)."""
    if stop_bp is None:
        return {}, ["a pair needs --stop-bp: the ratio move against it (bp) that proves it wrong (the gate prices it)"]
    bet = pair_bet(ndx_legs)
    adverse = "down" if bet == "up" else "up"
    hmn, tab = hm(t), ratio_table()
    p = stop_hit_prob(hmn, adverse, float(stop_bp), range_bp, tab)
    wild = wildness(hmn, range_bp, tab)
    why = []
    if p > MAX_STOP_HIT:
        why.append(f"a ratio stop {stop_bp:.0f} bp {adverse} is touched {p:.0%} of the time at {hmn} on a {wild} ratio "
                   f"day (max {MAX_STOP_HIT:.0%}): it sits inside the noise; the table's nearest safe stop is "
                   f"{safe_stop(hmn, adverse, range_bp, tab) or 'none'} bp")
    if min_credit_usd is not None and (credit_usd is None or credit_usd < min_credit_usd):
        why.append(f"the pair's credit ${credit_usd or 0:,.0f} is under the planned ${min_credit_usd:,.0f}: "
                   f"the trade is not the one judged")
    return {"bet": bet, "stop_bp": float(stop_bp), "p_hit": p, "wild": wild, "range_bp": range_bp,
            "credit_usd": credit_usd}, why


def _ncdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_price(cp: str, s: float, k: float, t_years: float, iv: float) -> float:
    if t_years <= 0 or iv <= 0:
        return max(0.0, s - k) if cp == "C" else max(0.0, k - s)
    sd = iv * math.sqrt(t_years)
    d1 = (math.log(s / k) + 0.5 * sd * sd) / sd
    d2 = d1 - sd
    return s * _ncdf(d1) - k * _ncdf(d2) if cp == "C" else k * _ncdf(-d2) - s * _ncdf(-d1)


def implied_vol(cp: str, price: float | None, s: float, k: float, t_years: float) -> float | None:
    intrinsic = max(0.0, s - k) if cp == "C" else max(0.0, k - s)
    if price is None or t_years <= 0 or float(price) <= intrinsic + 1e-6:
        return None
    lo, hi = 1e-4, 5.0
    for _ in range(80):
        mid = (lo + hi) / 2
        lo, hi = (lo, mid) if bs_price(cp, s, k, t_years, mid) > float(price) else (mid, hi)
    return (lo + hi) / 2


def years_left(t: pd.Timestamp) -> float:
    """Trading time to the 16:00 settlement, in 252-day years of 390-minute sessions."""
    mins = max(1.0, ((t.normalize() + pd.Timedelta(hours=16)) - t).total_seconds() / 60.0)
    return mins / (390.0 * 252.0)


def leg_key(symbol: str) -> tuple[str, float]:
    """("C", 30550.0) from an OCC symbol such as NDXP261013C30550000."""
    return symbol[-9], int(symbol[-8:]) / 1000.0


def close_cost_at(legs: list[dict], quotes: list[dict], spot: float, spot_then: float, t_years: float) -> float | None:
    """What closing the structure would cost per unit (points) if the index stood at ``spot_then`` now: each leg
    repriced at its own implied vol (sticky strike). Positive = paying to close, as a credit trade does."""
    total = 0.0
    for l, q in zip(legs, quotes):
        iv = implied_vol(l["cp"], (q or {}).get("mid"), spot, float(l["strike"]), t_years)
        if iv is None:
            return None
        px = bs_price(l["cp"], spot_then, float(l["strike"]), t_years, iv)
        total += px if l["side"] == "sell" else -px
    return total


def judge_entry(legs: list[dict], pv: dict, stops: list[float], spot: float, t: pd.Timestamp,
                range_day: float | None, lots: int) -> tuple[dict, list[str]]:
    """The judgment gate for selling premium: each stop's chance of being touched (the table), what the structure would
    cost to close there (repriced at its implied vols), and the stop-adjusted expectation
    (1 - P - Z) x the credit kept + sum(Z x (credit kept - intrinsic)) - sum(P x loss at that stop), where Z is a
    settlement between a short strike and a stop beyond it that never touched the stop (zone_outcomes; without it a
    stop past the short strike printed +$190 to +$760 on 2026-10-16 for spreads worth about nothing at the mid).
    Refused when a stop sits inside the noise, when a wild day needs a wider stop, or when the expectation does not
    clear MIN_EDGE a lot. Debits pass through (premium_only rules them). Returns the numbers and the reasons to
    refuse."""
    net = pv.get("net_mid")
    if net is None or float(net) >= 0:
        return {}, []
    credit = -float(net)
    if not stops:
        return {}, ["a credit trade needs --stop: the NDX level that proves it wrong (the gate prices it)"]
    t_years, hmn = years_left(t), hm(t)
    by_key = {leg_key(q["symbol"]): q for q in pv.get("legs") or [] if q.get("symbol")}
    quotes = [by_key.get((l["cp"], float(l["strike"]))) for l in legs]
    mult = 100.0 * lots
    keep = KEEP * credit * mult
    wild = wildness(hmn, range_day)
    why: list[str] = []
    rows, p_any, lost, p_zone, zone_value = [], 0.0, 0.0, 0.0, 0.0
    for stop in stops:
        side, dist = ("up" if stop > spot else "down"), abs(stop - spot)
        p = stop_hit_prob(hmn, side, dist, range_day)
        cost = close_cost_at(legs, quotes, spot, stop, t_years)
        loss = None if cost is None else (cost - credit) * mult
        cp = "C" if side == "up" else "P"
        shorts = [float(l["strike"]) for l in legs if l["cp"] == cp and l["side"] == "sell"]
        longs = [float(l["strike"]) for l in legs if l["cp"] == cp and l["side"] == "buy"]
        z = 0.0
        if shorts and longs:
            short_dist = abs(min(shorts, key=lambda k: abs(k - spot)) - spot)
            width = abs(min(longs, key=lambda k: abs(k - spot)) - min(shorts, key=lambda k: abs(k - spot)))
            for mass, intrinsic in zone_outcomes(hmn, side, short_dist, width, dist, range_day):
                z += mass
                zone_value += mass * (KEEP * credit - intrinsic) * mult
        p_zone += z
        rows.append({"stop": stop, "side": side, "dist": dist, "p_hit": p, "loss": loss, "p_zone": z})
        p_any += p
        if p > MAX_STOP_HIT:
            why.append(f"the stop at {stop:,.0f} ({dist:.0f} pts {side}) is touched {p:.0%} of the time at {hmn} on a "
                       f"{wild} day (max {MAX_STOP_HIT:.0%}): it sits inside the noise")
        if wild == "wild" and dist < WILD_MIN_STOP:
            why.append(f"a wild day (range {range_day:.0f}): a short-premium stop needs >= {WILD_MIN_STOP:.0f} pts, "
                       f"the one at {stop:,.0f} is {dist:.0f}")
        if loss is None:
            why.append(f"could not price the structure at {stop:,.0f} (a leg has no implied vol)")
        else:
            lost += p * loss
    p_any = min(1.0, p_any)
    p_zone = min(p_zone, 1.0 - p_any)
    ev = None if any(r["loss"] is None for r in rows) else (1.0 - p_any - p_zone) * keep + zone_value - lost
    if ev is not None and ev < MIN_EDGE * lots:
        why.append(f"expected {ev:+.0f} after the stops: keep {keep:.0f} x {1 - p_any - p_zone:.0%} vs "
                   + ", ".join(f"lose {r['loss']:.0f} x {r['p_hit']:.0%}" for r in rows)
                   + (f", settle between the short strike and the stop {p_zone:.0%} ({zone_value:+.0f})"
                      if p_zone > 0 else "")
                   + f" (needs >= +{MIN_EDGE * lots:.0f})")
    return {"credit": credit, "wild": wild, "keep": keep, "p_any": p_any, "p_zone": p_zone, "zone_value": zone_value,
            "ev": ev, "stops": rows}, why


def judge_line(t: pd.Timestamp, m: dict) -> str:
    """The snapshot's numbers for judgment: the realised ranges, how wild the day is, and how far a stop must sit."""
    rd = (m["high"] - m["low"]) if m.get("high") and m.get("low") else None
    hmn = hm(t)
    parts = [f"judge: {wildness(hmn, rd)} day" + (f" (range {rd:.0f})" if rd else "")]
    rng = " ".join(f"{k} {m[k]:.0f}" for k in ("range10", "range30") if m.get(k) is not None)
    if rng:
        parts.append(rng)
    up, dn = safe_stop(hmn, "up", rd), safe_stop(hmn, "down", rd)
    parts.append(f"stops touched <= {MAX_STOP_HIT:.0%}: calls >= +{up:.0f}" if up else "no call stop under the cap")
    parts.append(f"puts >= -{dn:.0f}" if dn else "no put stop under the cap")
    rr = m.get("ratio_range")
    if rr is not None or "ratio_range" in m:
        rt = ratio_table()
        ru, rd2 = safe_stop(hmn, "up", rr, rt), safe_stop(hmn, "down", rr, rt)
        parts.append(f"ratio {wildness(hmn, rr, rt)} (range {rr:.0f} bp): pair stops >= {ru or '?'} bp up / "
                     f"{rd2 or '?'} bp down" if rr is not None else
                     f"ratio: pair stops >= {ru or '?'} bp up / {rd2 or '?'} bp down")
    return " | ".join(parts)


def premium_refusal(pv: dict, premium_only: bool) -> str | None:
    """Why an open is refused under the premium_only limit: the desk sells premium (condors, credit spreads) and buys
    no debit. Agreed with the owner on 2026-10-01, after three sessions of 0DTE debit direction calls lost (-$1.6k,
    37% won): the coin flip pays theta and the crossing cost on every trade."""
    if premium_only and pv.get("debit_credit") == "debit":
        return ("premium only (the premium_only limit): this structure is a debit; sell premium outside the range "
                "(a condor or a credit spread) or stand aside")
    return None


def premium_menu(spot: float, high: float | None, low: float | None) -> list[tuple[str, list[tuple[str, str, float]]]]:
    """The structures the premium-only desk quotes: an iron condor and its two credit spreads, short strikes one 25-pt
    step outside the day's range so far (and the spot), 25 wide (a 25-wide condor's max loss fits the $2,500 rail),
    plus a tighter condor with its shorts at the range edges themselves."""
    hi = math.ceil(max(high or spot, spot) / 25.0) * 25.0
    lo = math.floor(min(low or spot, spot) / 25.0) * 25.0
    return [
        ("condor", [("sell", "C", hi + 25), ("buy", "C", hi + 50), ("sell", "P", lo - 25), ("buy", "P", lo - 50)]),
        ("condor@edges", [("sell", "C", hi), ("buy", "C", hi + 25), ("sell", "P", lo), ("buy", "P", lo - 25)]),
        ("call credit", [("sell", "C", hi + 25), ("buy", "C", hi + 50)]),
        ("put credit", [("sell", "P", lo - 25), ("buy", "P", lo - 50)]),
    ]


def playbook(levels_text: str, t: pd.Timestamp) -> str:
    """The veteran's playbook for the regime and the clock (project memory, 2026-09-30): what to trade now, in one
    line. The regime is the dealer gamma one the level map carries ("(positive)", "(negative)", "(near_flip)")."""
    hmn = hm(t)
    if hmn < "10:00":
        return "the first 30 minutes are noise: no trades; name the day type by 10:30 (trend, range or reversal)"
    if hmn >= "15:40":
        return "no new short gamma: the closing-auction imbalances publish at 15:50 and can flush the close"
    reg = re.search(r"\((positive|negative|near_flip)\)", levels_text or "")
    if reg is None:
        return "no gamma regime: small size, trade only at levels"
    return {
        "positive": "positive gamma = a range: mean reversion at the range edges and VWAP, breaks fail (no break "
                    "trades); sell premium outside the range once it is set; let Friend's rules run, adds included",
        "negative": "negative gamma = moves extend: trade with the trend on pullbacks, never fade; as supervisor, block "
                    "Friend's adds (and consider its entries) when the trend runs against it",
        "near_flip": "near the gamma flip: the regime can turn; smaller size, wait for price to leave the flip zone",
    }[reg.group(1)]


def news(since: datetime) -> list[str]:
    """New headlines, official releases and presidential posts since ``since`` (the morning brief's sources)."""
    lines = []
    if since.tzinfo is None:                                   # the brief's sources compare tz-aware times
        since = pd.Timestamp(since).tz_localize(NY).to_pydatetime()
    try:
        from api.bootstrap import bootstrap
        bootstrap()
        from api.services import brief_sources as B
        # no GDELT headlines here: the news desk's watch fetches them (scripts/claude_news.py). Two processes asking
        # GDELT for the same thing broke its one-request-per-5-seconds rule all day on 2026-09-30 (a 429 every cycle).
        for label, fn in (("post", B.posts_block), ("official", B.official_block)):
            try:
                items = (fn(since) or {}).get("items") or []
            except Exception as exc:  # noqa: BLE001 - a source down is a line, not a failure
                lines.append(f"  ({label} unavailable: {str(exc)[:80]})")
                continue
            for i in items[:5]:
                text = i.get("title") or i.get("text") or i.get("summary") or ""
                lines.append(f"  [{label} {i.get('time_et', '')}] {str(text)[:160]}")
    except Exception as exc:  # noqa: BLE001
        lines.append(f"  (news unavailable: {str(exc)[:100]})")
    return lines


# ── commands ──────────────────────────────────────────────────────────────────

def cmd_snapshot(force_news: bool = False) -> str:
    t = now_et(); day = t.date(); st = load_state(day)
    m = market(); spot = m.get("spot")
    L = [f"DESK {hm(t)} ET"]
    if spot:
        chg = (spot - m["prev"]) if m.get("prev") else None
        L.append(f"  NDX {spot:,.2f}" + (f" ({chg:+,.0f} on the day)" if chg is not None else "")
                 + (f" | O {m['open']:,.0f} H {m['high']:,.0f} L {m['low']:,.0f}" if m.get("high") else "")
                 + " | moves " + " ".join(f"{k} {m[k]:+.0f}" for k in ("m10", "m30", "m60") if m.get(k) is not None))
    L.append(f"  VIX {m.get('vix')} ({(m.get('vix_chg') or 0):+.2f})  VXN {m.get('vxn')} ({(m.get('vxn_chg') or 0):+.2f})")
    rs = ratio_now()
    L.append("  " + ratio_line(rs))
    L.append("  " + clone_line(day, hm(t)))
    lv = levels(spot)
    if lv:
        L.append("  levels: " + " | ".join(lv))
    L.append("  playbook: " + playbook(" | ".join(lv), t))
    try:
        m["ratio_range"] = ratio_range_today()
        L.append("  " + judge_line(t, m))
    except Exception as exc:  # noqa: BLE001 - the snapshot must render without the table
        L.append(f"  judge: unavailable ({str(exc)[:80]})")
    realised, marked, opened = day_pnl(day)
    L.append(f"  book: day {realised + marked:+,.0f} (realised {realised:+,.0f}, open {marked:+,.0f})"
             + (" | DONE for the day" if st.get("done") else ""))
    for r in opened:
        L.append(f"    open {r.get('structure')} x{r.get('contracts')} entry {r.get('entry_net')} mark {r.get('mark')} "
                 f"pnl {r.get('pnl')} max loss {r.get('max_loss')} ({r.get('trade_group_id')})")
    used = trades_today(st)
    ok = (not st.get("done")) and n_positions(opened, st) < MAX_POSITIONS and used < MAX_TRADES \
        and ENTRY_START <= hm(t) <= ENTRY_END
    L.append(f"  entries {'OPEN' if ok else 'closed'} (rails: <= {MAX_LOTS} lots, <= ${MAX_RISK:,.0f} at risk, "
             f"<= {MAX_POSITIONS} position(s), <= {MAX_TRADES} trades a day ({used} used), {ENTRY_START}-{ENTRY_END}, "
             f"stop {DAY_STOP:+,.0f}, flat {FLAT_AT}" + (", PREMIUM ONLY: no debits" if PREMIUM_ONLY else "") + ")")
    if PREMIUM_ONLY:
        L.append("  mode: premium only - on a range day sell a condor or credit spread outside the range once it is set; "
                 "on a trend day stand aside")
    if "12:45" <= hm(t) <= CONDOR_END:
        L.append(f"  condor: the SPX 13:00 iron condor is due ({CONDOR_START}-{CONDOR_END}): run `condor` for the menu")
    if spot and ok:
        atm = round(spot / 25.0) * 25.0
        if PREMIUM_ONLY:
            cands = premium_menu(float(spot), m.get("high"), m.get("low"))
        else:
            cands = [("bull call", [("buy", "C", k), ("sell", "C", k + 25)]) for k in (atm - 25, atm, atm + 25)] + \
                    [("bear put", [("buy", "P", k), ("sell", "P", k - 25)]) for k in (atm + 25, atm, atm - 25)] + \
                    [("iron fly", [("sell", "C", atm), ("buy", "C", atm + 50), ("sell", "P", atm), ("buy", "P", atm - 50)])]
        for name, spec in cands:
            legs = [{"side": s, "cp": c, "strike": k} for s, c, k in spec]
            try:
                pv = preview(legs, 1, day)
                strikes = "/".join(f"{k:.0f}" for _, _, k in spec)
                L.append(f"    {name:<9} {strikes:<23} net {shown_net(pv, legs)} max loss {pv.get('max_loss')} "
                         f"max profit {pv.get('max_profit')}")
            except Exception as exc:  # noqa: BLE001
                L.append(f"    {name}: no quote ({str(exc)[:80]})")
        if rs.get("ndx") and rs.get("spx"):
            for name, nspec, sspec in ratio_menu(float(rs["ndx"]), float(rs["spx"])):
                try:
                    nlegs = [{"side": s, "cp": c, "strike": k} for s, c, k in nspec]
                    slegs = [{"side": s, "cp": c, "strike": k} for s, c, k in sspec]
                    pn = preview(nlegs, 1, day, "NDX")
                    spx_lots = 2
                    ps = preview(slegs, spx_lots, day, "SPX")
                    tot = sum(abs(float(p.get("max_loss") or 0)) for p in (pn, ps))
                    if tot > MAX_RISK:                   # over the rail: one SPX lot, never an in-the-money NDX strike
                        spx_lots = 1
                        ps = preview(slegs, spx_lots, day, "SPX")
                        tot = sum(abs(float(p.get("max_loss") or 0)) for p in (pn, ps))
                    L.append(f"    {name:<10} NDX {'/'.join(f'{c}{k:.0f}' for _, c, k in nspec)} x1 net {shown_net(pn, nlegs)} "
                             f"+ SPX {'/'.join(f'{c}{k:.0f}' for _, c, k in sspec)} x{spx_lots} net {shown_net(ps, slegs)}: "
                             f"max loss together {tot:,.0f}" + (" (over the rail)" if tot > MAX_RISK else ""))
                except Exception as exc:  # noqa: BLE001
                    L.append(f"    {name}: no quote ({str(exc)[:80]})")
    last = st.get("last_news")
    if force_news or last is None or (datetime.now() - datetime.fromisoformat(last)).total_seconds() >= NEWS_EVERY_S:
        since = datetime.fromisoformat(last) if last else datetime.combine(day, datetime.min.time()) + timedelta(hours=6)
        got = news(since)
        L += (["  news since " + since.strftime("%H:%M") + ":"] + got) if got else ["  news: nothing new"]
        st["last_news"] = datetime.now().isoformat(timespec="seconds")
        save_state(day, st)
    return "\n".join(L)


STYLES = ("clone", "ratio", "condor")

# The SPX 13:00 iron condor (the owner, 2026-10-25: a full condor the agent runs on top of the SPX 13:00 robot). The
# study (real SPXW prints, 2024-10 -> 2026-10, settings chosen walk-forward): the call side by the SPX 13:00 v2 rule
# and puts far out, both scaled to the 13:00 at-the-money straddle (the market's own afternoon move), held to the close:
# +$8.5k / +$9.2k a lot out of sample; the put side alone is weak (+$0.7k in its last year), so the agent judges it.
CONDOR_START, CONDOR_END = "12:58", "13:30"
CONDOR_CALL = (10.0, 0.8, 10.0)          # room max(10, 0.8 x straddle) above SPX, 10 wide
CONDOR_PUT = (20.0, 1.2, 20.0)           # room max(20, 1.2 x straddle) below SPX, 20 wide


def condor_strikes(spot: float, straddle: float) -> dict:
    """The condor's strikes: the short call at the first 5-pt strike at least max(10, 0.8 x straddle) above SPX, 10
    wide; the short put at the first 5-pt strike at least max(20, 1.2 x straddle) below, 20 wide."""
    (cm, ck, cw), (pm, pk, pw) = CONDOR_CALL, CONDOR_PUT
    croom, proom = max(cm, ck * straddle), max(pm, pk * straddle)
    cs, ps = math.ceil((spot + croom) / 5.0) * 5.0, math.floor((spot - proom) / 5.0) * 5.0
    return {"call_room": croom, "put_room": proom, "call": (cs, cs + cw), "put": (ps, ps - pw)}


def month_end(day: date) -> bool:
    """The month's last trading day (holidays aside): SPX rallied into the close on 59% of them (26% on other days),
    so the condor sells no calls then."""
    return (pd.Timestamp(day) + pd.offsets.BDay(1)).month != day.month


def natural_credit(legs: list[dict], pv: dict, day: date, under: str) -> float | None:
    """What selling ``legs`` at the touch takes in (each short at its bid, each long at its ask); None without quotes."""
    q = {l.get("symbol"): l for l in pv.get("legs") or []}
    total = 0.0
    for l in legs:
        x = q.get(occ(l["cp"], l["strike"], day, ROOTS[under])) or {}
        if x.get("bid") is None or x.get("ask") is None:
            return None
        total += float(x["bid"]) if l["side"] == "sell" else -float(x["ask"])
    return total


def cmd_condor() -> int:
    """Read-only: the SPX 13:00 iron condor menu. No order goes anywhere."""
    t = now_et(); day = t.date()
    q = quote("SPX")
    spot = q.get("last") or q.get("close")
    if not spot:
        print("CONDOR: no SPX quote"); return 2
    spot = float(spot)
    katm = round(spot / 5.0) * 5.0
    sv = preview([{"side": "buy", "cp": "C", "strike": katm}, {"side": "buy", "cp": "P", "strike": katm}], 1, day, "SPX")
    mids = [l.get("mid") for l in sv.get("legs") or []]
    if len(mids) != 2 or any(m is None for m in mids):
        print(f"CONDOR: no live straddle quote at {katm:.0f}"); return 2
    straddle = float(mids[0]) + float(mids[1])
    k = condor_strikes(spot, straddle)
    (cs, cl), (ps, pl) = k["call"], k["put"]
    sides = {"calls": [{"side": "sell", "cp": "C", "strike": cs}, {"side": "buy", "cp": "C", "strike": cl}],
             "puts": [{"side": "sell", "cp": "P", "strike": ps}, {"side": "buy", "cp": "P", "strike": pl}]}
    me = month_end(day)
    L = [f"CONDOR {hm(t)}: SPX {spot:,.2f} | 13:00 straddle {straddle:.2f} at {katm:.0f} (the market's afternoon move) | "
         f"entries {CONDOR_START}-{CONDOR_END}" + (" | MONTH-END: no calls (SPX rallies into the close)" if me else "")]
    for name, legs in sides.items():
        pv = preview(legs, 1, day, "SPX")
        nat = natural_credit(legs, pv, day, "SPX")
        room = k["call_room"] if name == "calls" else k["put_room"]
        L.append(f"  {name}: sell {legs[0]['cp']}{legs[0]['strike']:.0f} / buy {legs[1]['cp']}{legs[1]['strike']:.0f} "
                 f"(room {room:.1f}): credit mid {-float(pv.get('net_mid') or 0):.2f}"
                 + (f", natural {nat:.2f}" if nat is not None else "") + f", max loss {pv.get('max_loss')}")
    full = preview(sides["calls"] + sides["puts"], 1, day, "SPX")
    ml = abs(float(full.get("max_loss") or 0)) or None
    L.append(f"  condor x1: credit mid {-float(full.get('net_mid') or 0):.2f}, max loss {ml}"
             + (f", the ${MAX_RISK:,.0f} rail fits {int(MAX_RISK // ml)} lot(s)" if ml else ""))
    try:
        intr = api("GET", "/market/intraday/SPX?minutes=240&interval=1")
        c = [float(x) for x in (intr.get("c") or []) if x is not None]
        if len(c) > 60:
            L.append(f"  SPX today: {c[-1] - c[0]:+.1f} over the last {len(c)} min, {c[-1] - c[-61]:+.1f} over the last 60, "
                     f"range {max(c) - min(c):.1f}")
    except Exception:  # noqa: BLE001 - the menu stands without the tape
        pass
    legs_arg = " ".join(f"--leg {l['side']}:{l['cp']}:{l['strike']:.0f}"
                        for l in (sides["puts"] if me else sides["calls"] + sides["puts"]))
    L.append(f"  rule: {'the put side only (month-end)' if me else 'the full condor'}, held to the 15:55 flat: "
             f"open --under SPX --style condor {legs_arg} --lots 1 --min-credit <the credit you judged> ...")
    print("\n".join(L))
    return 0


def cmd_open(legs: list[dict], lots: int, thesis: str, exit_plan: str, wrong: str, stops: list[float] | None = None,
             min_credit: float | None = None, style: str | None = None, under: str = UNDER) -> int:
    """``style`` "clone": the AI agent's own clone-strategy trade, decided on the fly: the rails hold, the stop-table
    gate (built for premium held to expiry) does not apply. ``style`` "condor" with ``under`` "SPX": the agent's SPX
    13:00 iron condor (or one of its sides), inside CONDOR_START-CONDOR_END."""
    t = now_et(); day = t.date(); st = load_state(day)
    why = []
    if style is not None and style not in STYLES:
        why.append(f"style must be one of {', '.join(STYLES)}")
    if under not in ROOTS:
        why.append(f"under must be one of {', '.join(sorted(ROOTS))}")
    if under == "SPX" and style != "condor":
        why.append("SPX on the desk is the 13:00 iron condor only (--style condor); the ratio pair has its own command")
    if style == "condor":
        if under != "SPX":
            why.append("the condor style is the SPX 13:00 iron condor: --under SPX")
        if not CONDOR_START <= hm(t) <= CONDOR_END:
            why.append(f"the condor enters {CONDOR_START}-{CONDOR_END} only (the study's 13:00 entry)")
        if len(legs) not in (2, 4):
            why.append("a condor is 4 legs (or one side: 2)")
    if st.get("done"):
        why.append("done for the day (the stop was hit)")
    if not ENTRY_START <= hm(t) <= ENTRY_END:
        why.append(f"entries only {ENTRY_START}-{ENTRY_END}")
    if not 1 <= lots <= MAX_LOTS:
        why.append(f"lots must be 1-{MAX_LOTS}")
    if not 1 <= len(legs) <= 4:
        why.append("1-4 legs")
    if not (thesis.strip() and exit_plan.strip() and wrong.strip()):
        why.append("thesis, exit and what-proves-me-wrong are all required")
    if trades_today(st) >= MAX_TRADES:
        why.append(f"{trades_today(st)} trades opened today, the limit is {MAX_TRADES} (standing aside is a position)")
    realised, marked, opened = day_pnl(day)
    if (n := n_positions(opened, st)) >= MAX_POSITIONS:
        why.append(f"{n} position(s) open, the limit is {MAX_POSITIONS}")
    if realised + marked <= DAY_STOP:
        why.append("the day stop is hit")
    under = under if under in ROOTS else UNDER
    q = quote(under)
    if (reason := itm_short(legs, q.get("last") or q.get("close"), under)) is not None:
        why.append(reason)
    first = preview(legs, lots, day, under)
    time.sleep(SETTLE_S)
    pv = preview(legs, lots, day, under)
    ml = pv.get("max_loss")
    if not pv.get("ok") or pv.get("net_mid") is None:
        why.append("no two-sided quote for every leg")
    stale = sorted({str(l.get("source")) for l in pv.get("legs", []) if l.get("source") != "tastytrade"})
    if stale:                                  # a fallback feed (yfinance, polygon) can be minutes old: a fill there is fake
        why.append(f"legs priced from {', '.join(stale)}, not the live tastytrade stream")
    why += quote_problems(first, pv, legs, under)
    if (reason := premium_refusal(pv, PREMIUM_ONLY)) is not None:
        why.append(reason)
    if ml is None:
        why.append("risk is not defined (no finite max loss)")
    elif abs(float(ml)) > MAX_RISK + 1e-6:
        why.append(f"max loss {abs(float(ml)):,.0f} is over ${MAX_RISK:,.0f}")
    net = pv.get("net_mid")
    if min_credit is not None and (net is None or -float(net) < min_credit):
        why.append(f"credit {-(float(net)) if net is not None else 'none'} is under the planned {min_credit:.2f}: "
                   f"the trade is not the one judged")
    mk = market()
    gate_spot = pv.get("spot") or mk.get("spot") or q.get("last")
    rd = (mk["high"] - mk["low"]) if mk.get("high") and mk.get("low") else None
    gate: dict = {}
    if gate_spot and style is None:
        gate, gwhy = judge_entry(legs, pv, list(stops or []), float(gate_spot), t, rd, lots)
        why += gwhy
    if why:
        print("REFUSED: " + "; ".join(why)); return 2
    if style is not None:
        print(f"STYLE {style}: the agent's own decision; the rails passed, the stop-table gate does not apply")
    if gate:
        print(f"GATE ok: {gate['wild']} day; credit {gate['credit']:.2f}; " + ", ".join(
            f"stop {r['stop']:,.0f} ({r['dist']:.0f} {r['side']}) touched {r['p_hit']:.0%}, loss there {r['loss']:+.0f}"
            for r in gate["stops"])
            + (f"; settles past the short without the stop {gate['p_zone']:.0%}" if gate.get("p_zone") else "")
            + f"; expected {gate['ev']:+.0f}")
    spot = pv.get("spot") or (mk.get("spot") if under == UNDER else (q.get("last") or q.get("close")))
    desc = " ".join(f"{l['side']} {l['cp']}{l['strike']:.0f}" for l in legs)
    journal(day, f"## {hm(t)} OPEN {desc} x{lots}" + (f" [{style}]" if style else "")
            + f"\n- {under} {spot}; net mid {pv['net_mid']} ({pv['debit_credit']}), "
              f"max loss {ml}, max profit {pv.get('max_profit')}\n- thesis: {thesis}\n- exit: {exit_plan}\n"
              f"- wrong if: {wrong}" + (f"\n- gate: {json.dumps(gate, default=str)}" if gate else ""))
    res = api("POST", "/orders", order_body(legs, lots, day, thesis, under))
    tg = res.get("trade_group_id")
    st["positions"][str(tg)] = {"legs": legs, "lots": lots, "opened": hm(t), "spot": spot, "fill": res.get("fill_price"),
                                "cost": crossing_cost(legs, float(spot or 0), under), "thesis": thesis, "style": style,
                                "under": under}
    save_state(day, st)
    journal(day, f"- filled: status {res.get('status')}, net {res.get('fill_price')}, trade group {tg}")
    print(f"OPENED {desc} x{lots}: {res.get('status')} at {res.get('fill_price')} (trade group {tg}); max loss {ml}")
    return 0


def cmd_pair(ndx_legs: list[dict], ndx_lots: int, spx_legs: list[dict], spx_lots: int, thesis: str, exit_plan: str,
             wrong: str, stop_bp: float | None = None, min_credit_usd: float | None = None,
             style: str | None = None) -> int:
    """The NDX/SPX ratio trade as ONE position: an NDXP spread and an SPXW spread, checked together against the rails
    (their max losses summed against the per-position rail, one trade, the book must be flat) and opened together. If
    the second order does not fill, the first is closed at once: the desk never holds half a pair. ``style`` "ratio":
    the AI agent's own ratio-strategy trade, decided on the fly: the rails hold, the ratio stop table does not refuse
    it and ``stop_bp`` is the agent's own (optional) mark."""
    t = now_et(); day = t.date(); st = load_state(day)
    why = []
    if style is not None and style not in STYLES:
        why.append(f"style must be one of {', '.join(STYLES)}")
    if st.get("done"):
        why.append("done for the day (the stop was hit)")
    if not ENTRY_START <= hm(t) <= ENTRY_END:
        why.append(f"entries only {ENTRY_START}-{ENTRY_END}")
    for name, lots, legs in (("NDX", ndx_lots, ndx_legs), ("SPX", spx_lots, spx_legs)):
        if not 1 <= lots <= MAX_LOTS:
            why.append(f"{name} lots must be 1-{MAX_LOTS}")
        if len(legs) != 2:
            why.append(f"{name}: a pair leg is one vertical (2 legs)")
    if not (thesis.strip() and exit_plan.strip() and wrong.strip()):
        why.append("thesis, exit and what-proves-me-wrong are all required")
    if trades_today(st) >= MAX_TRADES:
        why.append(f"{trades_today(st)} trades opened today, the limit is {MAX_TRADES}")
    realised, marked, opened = day_pnl(day)
    if (n := n_positions(opened, st)) >= MAX_POSITIONS:
        why.append(f"{n} position(s) open, the limit is {MAX_POSITIONS} (a pair is one position)")
    if realised + marked <= DAY_STOP:
        why.append("the day stop is hit")
    for under, legs in (("NDX", ndx_legs), ("SPX", spx_legs)):
        q = quote(under)
        if (reason := itm_short(legs, q.get("last") or q.get("close"), under)) is not None:
            why.append(reason)
    first = {"NDX": preview(ndx_legs, ndx_lots, day, "NDX"), "SPX": preview(spx_legs, spx_lots, day, "SPX")}
    time.sleep(SETTLE_S)
    pvs = {"NDX": preview(ndx_legs, ndx_lots, day, "NDX"), "SPX": preview(spx_legs, spx_lots, day, "SPX")}
    total = 0.0
    for name, pv in pvs.items():
        ml = pv.get("max_loss")
        if not pv.get("ok") or pv.get("net_mid") is None:
            why.append(f"{name}: no two-sided quote for every leg")
        why += [f"{name}: {w}" for w in quote_problems(first[name], pv, ndx_legs if name == "NDX" else spx_legs, name)]
        stale = sorted({str(l.get("source")) for l in pv.get("legs", []) if l.get("source") != "tastytrade"})
        if stale:
            why.append(f"{name} legs priced from {', '.join(stale)}, not the live tastytrade stream")
        if (reason := premium_refusal(pv, PREMIUM_ONLY)) is not None:
            why.append(f"{name}: {reason}")
        if ml is None:
            why.append(f"{name}: risk is not defined (no finite max loss)")
        else:
            total += abs(float(ml))
    if total > MAX_RISK + 1e-6:
        why.append(f"the pair's max loss {total:,.0f} (NDX {pvs['NDX'].get('max_loss')}, SPX {pvs['SPX'].get('max_loss')}) "
                   f"is over ${MAX_RISK:,.0f}")
    nets = [(pvs[n].get("net_mid"), lots) for n, lots in (("NDX", ndx_lots), ("SPX", spx_lots))]
    credit_usd = None if any(v is None for v, _ in nets) else sum(-float(v) * lots * 100.0 for v, lots in nets)
    if style is None:
        gate, gwhy = judge_pair(ndx_legs, stop_bp, t, ratio_range_today(), credit_usd, min_credit_usd)
        why += gwhy
    else:
        gate = {"bet": pair_bet(ndx_legs), "stop_bp": stop_bp, "credit_usd": credit_usd, "style": style}
        if min_credit_usd is not None and (credit_usd is None or credit_usd < min_credit_usd):
            why.append(f"the pair's credit ${credit_usd or 0:,.0f} is under the planned ${min_credit_usd:,.0f}: "
                       f"the trade is not the one judged")
    if why:
        print("REFUSED: " + "; ".join(why)); return 2
    if style is not None:
        print(f"STYLE {style}: the agent's own decision, ratio {gate['bet']}; the rails passed, the ratio stop table "
              f"does not apply; credit ${credit_usd or 0:,.0f}")
    else:
        print(f"GATE ok: ratio {gate['bet']}, {gate['wild']} ratio day; stop {gate['stop_bp']:.0f} bp touched "
              f"{gate['p_hit']:.0%}; credit ${gate['credit_usd'] or 0:,.0f}")
    rs = ratio_now()
    dn = " ".join(f"{l['side']} {l['cp']}{l['strike']:.0f}" for l in ndx_legs)
    ds = " ".join(f"{l['side']} {l['cp']}{l['strike']:.0f}" for l in spx_legs)
    journal(day, f"## {hm(t)} OPEN PAIR NDX {dn} x{ndx_lots} + SPX {ds} x{spx_lots}\n- {ratio_line(rs)}\n"
                 f"- NDX net mid {pvs['NDX']['net_mid']} ({pvs['NDX']['debit_credit']}), max loss {pvs['NDX'].get('max_loss')}; "
                 f"SPX net mid {pvs['SPX']['net_mid']} ({pvs['SPX']['debit_credit']}), max loss {pvs['SPX'].get('max_loss')}; "
                 f"together {total:,.0f}\n- thesis: {thesis}\n- exit: {exit_plan}\n- wrong if: {wrong}\n"
                 f"- gate: {json.dumps(gate, default=str)}")
    res_n = api("POST", "/orders", order_body(ndx_legs, ndx_lots, day, thesis, "NDX"))
    tg_n = res_n.get("trade_group_id")
    if res_n.get("status") != "filled" or not tg_n:
        journal(day, f"- NDX leg not filled ({res_n.get('status')}); nothing opened")
        print(f"NOT OPENED: the NDX leg came back {res_n.get('status')}"); return 3
    st["positions"][str(tg_n)] = {"legs": ndx_legs, "lots": ndx_lots, "opened": hm(t), "spot": rs.get("ndx"),
                                  "fill": res_n.get("fill_price"), "under": "NDX", "thesis": thesis,
                                  "cost": crossing_cost(ndx_legs, float(rs.get("ndx") or 0), "NDX"),
                                  "max_loss": pvs["NDX"].get("max_loss"), "ratio": rs.get("ratio"),
                                  "bet": gate.get("bet"), "stop_bp": gate.get("stop_bp")}
    save_state(day, st)
    res_s = api("POST", "/orders", order_body(spx_legs, spx_lots, day, f"pair with {tg_n}: {thesis}", "SPX"))
    tg_s = res_s.get("trade_group_id")
    if res_s.get("status") != "filled" or not tg_s:
        out = _close_all(day, f"the pair's SPX leg came back {res_s.get('status')}: never hold half a pair")
        print(f"NOT OPENED: the SPX leg came back {res_s.get('status')}; the NDX leg was closed again\n" + "\n".join(out))
        return 3
    st = load_state(day)
    st["positions"][str(tg_n)]["pair"] = str(tg_s)
    st["positions"][str(tg_s)] = {"legs": spx_legs, "lots": spx_lots, "opened": hm(t), "spot": rs.get("spx"),
                                  "fill": res_s.get("fill_price"), "under": "SPX", "pair_of": str(tg_n), "thesis": thesis,
                                  "cost": crossing_cost(spx_legs, float(rs.get("spx") or 0), "SPX"),
                                  "max_loss": pvs["SPX"].get("max_loss")}
    save_state(day, st)
    journal(day, f"- filled: NDX net {res_n.get('fill_price')} ({tg_n}); SPX net {res_s.get('fill_price')} ({tg_s})")
    print(f"OPENED PAIR: NDX {dn} x{ndx_lots} at {res_n.get('fill_price')} ({tg_n}) + SPX {ds} x{spx_lots} at "
          f"{res_s.get('fill_price')} ({tg_s}); max loss together {total:,.0f}")
    return 0


def _close_all(day: date, reason: str, only: str | None = None) -> list[str]:
    """Close every open position, or only ``only``'s whole position (its pair leg and trims with it)."""
    st = load_state(day); out = []
    keep = linked_groups(only, st) if only else None
    for r in my_positions("open"):
        tg = r["trade_group_id"]
        if keep is not None and str(tg) not in keep:
            continue
        res = api("POST", f"/paper/positions/{tg}/close", {"order_type": "market"})
        meta = st["positions"].get(str(tg), {})
        out.append(f"CLOSED {r.get('structure')} x{r.get('contracts')} ({tg}): {res.get('status')} at {res.get('fill_price')}"
                   f"; was marked {r.get('pnl')}; reason: {reason}")
        st["closed"].append({"tg": tg, "at": hm(now_et()), "reason": reason, "cost": meta.get("cost", 0.1),
                             "lots": meta.get("lots", r.get("contracts"))})
        journal(day, f"## {hm(now_et())} CLOSE {r.get('structure')} ({tg})\n- reason: {reason}\n"
                     f"- close fill {res.get('fill_price')}; P&L as marked before the close {r.get('pnl')}")
    save_state(day, st)
    return out


def cmd_trim(lots: int, reason: str, tg: str | None = None) -> int:
    """Take part of an open position off: the paper book closes a trade group whole, so a trim is an offsetting
    order for ``lots`` units (the open legs with their sides reversed). The ledger then holds two groups that net to
    the smaller position; ``close`` later closes both, and the day's P&L sums them. With two positions open, ``tg``
    names which one."""
    t = now_et(); day = t.date(); st = load_state(day)
    opened = my_positions("open")
    longs = [r for r in opened if str(r.get("trade_group_id")) in st["positions"]
             and not st["positions"][str(r.get("trade_group_id"))].get("trim_of")
             and not st["positions"][str(r.get("trade_group_id"))].get("pair_of")]
    if tg is not None:
        longs = [r for r in longs if str(r.get("trade_group_id")) == str(tg)]
    if not longs or not reason.strip():
        print("REFUSED: nothing of mine open to trim" + (f" as {tg}" if tg else "") + ", or no reason given"); return 2
    if len(longs) > 1:
        print("REFUSED: " + ", ".join(str(r.get("trade_group_id")) for r in longs) + " are open: name one with --tg")
        return 2
    tg = str(longs[0]["trade_group_id"]); meta = st["positions"][tg]
    if meta.get("pair") or meta.get("pair_of"):
        print("REFUSED: a ratio pair is closed whole (close), never trimmed"); return 2
    held = int(meta.get("lots", 1)) - int(meta.get("trimmed", 0))
    if not 1 <= lots < held:
        print(f"REFUSED: can trim 1..{held - 1} of the {held} lots still on (close takes the rest)"); return 2
    rev = [{"side": "sell" if l["side"] == "buy" else "buy", "cp": l["cp"], "strike": l["strike"]} for l in meta["legs"]]
    journal(day, f"## {hm(t)} TRIM {lots} of {held} lots of {tg}\n- reason: {reason}")
    res = api("POST", "/orders", order_body(rev, lots, day, f"trim {tg}: {reason}"))
    meta["trimmed"] = int(meta.get("trimmed", 0)) + lots
    st["positions"][str(res.get("trade_group_id"))] = {"legs": rev, "lots": lots, "opened": hm(t), "trim_of": tg,
                                                       "cost": meta.get("cost", 0.1), "fill": res.get("fill_price")}
    save_state(day, st)
    journal(day, f"- trim filled: status {res.get('status')}, net {res.get('fill_price')}, offsetting group {res.get('trade_group_id')}")
    print(f"TRIMMED {lots} lot(s) of {tg}: {res.get('status')} at {res.get('fill_price')} (offset group {res.get('trade_group_id')})")
    return 0


def cmd_close(reason: str, tg: str | None = None) -> int:
    if not reason.strip():
        print("REFUSED: a reason is required"); return 2
    lines = _close_all(now_et().date(), reason, only=tg)
    print("\n".join(lines) if lines else ("nothing open" + (f" as {tg}" if tg else "")))
    return 0


def live_open_pnl(day: date, st: dict, opened: list[dict]) -> float | None:
    """The open positions' P&L from LIVE quotes, or None when any of them cannot be trusted. The ledger's mark is not
    used: when one leg is served by a fallback feed (yfinance, minutes old) and the other by the stream, the spread
    prices below zero and the ledger clamps it to 0 (2026-09-29 11:04: a fresh 12.05 debit marked at 0.0, -$2,412),
    and a stop acting on that would sell a good position on garbage."""
    total = 0.0
    for r in opened:
        meta = st["positions"].get(str(r.get("trade_group_id")))
        if not meta:
            return None
        pv = preview(meta["legs"], int(meta["lots"]), day, meta.get("under", UNDER))
        net = pv.get("net_mid")
        strikes = [l["strike"] for l in meta["legs"]]
        width = (max(strikes) - min(strikes)) if len(set(strikes)) > 1 else None
        if net is None or any(l.get("source") != "tastytrade" for l in pv.get("legs", [])) \
                or (width is not None and len(meta["legs"]) == 2 and not -width - 0.5 <= net <= width + 0.5):
            return None
        total += (float(net) - float(meta.get("fill") or 0)) * 100.0 * int(meta["lots"])
    return total


def cmd_guard() -> list[str]:
    t = now_et(); day = t.date(); st = load_state(day); out = []
    realised, marked, opened = day_pnl(day)
    live = live_open_pnl(day, st, opened) if opened else 0.0
    if live is None:
        # an untrustworthy mark never triggers the stop; the next poll (30 s) tries again
        return out if not opened or hm(t) < FLAT_AT else _close_all(day, f"flat at {FLAT_AT}")
    marked = live
    if realised + marked <= DAY_STOP and not st.get("done"):
        out += _close_all(day, f"day stop: {realised + marked:+,.0f} <= {DAY_STOP:+,.0f}")
        st = load_state(day); st["done"] = True; save_state(day, st)
        out.append(f"STOP: the desk is done for {day} at {realised + marked:+,.0f}")
    elif opened and hm(t) >= FLAT_AT:
        out += _close_all(day, f"flat at {FLAT_AT}: nothing is left to settle unattended")
    return out


def cmd_summary(day: date | None = None) -> str:
    day = day or now_et().date(); st = load_state(day)
    closed = [r for r in my_positions("closed") if str(r.get("closed") or "")[:10] == day.isoformat()]
    realised = sum(float(r.get("pnl") or 0) for r in closed)
    costed = realised
    for r in closed:
        meta = st["positions"].get(str(r.get("trade_group_id")), {})
        costed -= 2 * float(meta.get("cost", 0.1)) * 100 * float(meta.get("lots", r.get("contracts") or 1))
    L = [f"SUMMARY {day}: {len(closed)} trades, paper P&L {realised:+,.0f}, after the measured crossing cost {costed:+,.0f}"]
    for r in closed:
        L.append(f"  {r.get('structure')} x{r.get('contracts')} {r.get('opened')}->{r.get('closed')} pnl {r.get('pnl')}")
    return "\n".join(L)


JUDGMENTS = "judgments.csv"
JUDGMENT_COLS = ["ts", "setup", "action", "why", "ndx", "range10", "range30", "range_day", "wild", "safe_up", "safe_down"]


def cmd_judge(setup: str, action: str, why: str) -> int:
    """Log a judgment, a pass as much as a trade, with the numbers it was made on, for the weekly review of which
    calls were right (the owner, 2026-10-13: "Improve judgement process")."""
    import csv
    t, m = now_et(), market()
    rd = (m["high"] - m["low"]) if m.get("high") and m.get("low") else None
    row = {"ts": t.isoformat(timespec="seconds"), "setup": setup, "action": action, "why": why, "ndx": m.get("spot"),
           "range10": m.get("range10"), "range30": m.get("range30"), "range_day": rd, "wild": wildness(hm(t), rd),
           "safe_up": safe_stop(hm(t), "up", rd), "safe_down": safe_stop(hm(t), "down", rd)}
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = STATE_DIR / JUDGMENTS
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=JUDGMENT_COLS)
        if new:
            w.writeheader()
        w.writerow(row)
    journal(t.date(), f"## {hm(t)} JUDGE {action.upper()} {setup}\n{why}")
    print(f"judged: {action} {setup} at NDX {m.get('spot')} ({row['wild']} day)")
    return 0


def parse_vertical(s: str) -> list[dict]:
    """``C:29425:29450`` -> sell the 29425 call, buy the 29450 (a credit vertical: the first strike is the short)."""
    cp, short, long_ = s.split(":")
    cp = cp.upper()[0]
    if cp not in ("C", "P"):
        raise SystemExit(f"bad vertical {s!r}: use C|P:short:long")
    return [{"side": "sell", "cp": cp, "strike": float(short)}, {"side": "buy", "cp": cp, "strike": float(long_)}]


def cmd_quote(verticals: list[str], stops: list[float], lots: int = 1) -> int:
    """Read-only: price candidate credit verticals (one preview each, no order) and run each through the gate at
    every --stop on its side, for the expert's hand-off (2026-10-16: a scratch script did this by hand)."""
    t = now_et(); day = t.date(); hmn = hm(t)
    mk = market()
    spot = mk.get("spot")
    if not spot:
        print("no NDX level"); return 2
    rd = (mk["high"] - mk["low"]) if mk.get("high") and mk.get("low") else None
    print(f"QUOTE {hmn} NDX {spot:,.2f} | {wildness(hmn, rd)} day" + (f" (range {rd:.0f})" if rd else "")
          + f" | safe stops: calls +{safe_stop(hmn, 'up', rd) or 0:.0f}, puts -{safe_stop(hmn, 'down', rd) or 0:.0f}")
    for v in verticals:
        legs = parse_vertical(v)
        cp, ks, kl = legs[0]["cp"], legs[0]["strike"], legs[1]["strike"]
        pv = preview(legs, lots, day)
        q = {leg_key(x["symbol"]): x for x in pv.get("legs") or [] if x.get("symbol")}
        s, b = q.get((cp, ks)), q.get((cp, kl))
        net = pv.get("net_mid")
        mid = -float(net) if net is not None else None
        nat = (float(s["bid"]) - float(b["ask"])) if s and b and s.get("bid") is not None and b.get("ask") is not None \
            else None
        out = f"{cp} {ks:.0f}/{kl:.0f} (short {ks - spot:+.0f}): credit mid " + (f"{mid:.2f}" if mid is not None else "n/a")
        out += ", natural " + (f"{nat:.2f}" if nat is not None else "n/a")
        if s and b:
            out += f" | short {s.get('bid')}/{s.get('ask')}, long {b.get('bid')}/{b.get('ask')}"
        print(out)
        for stop in [x for x in stops if (x > spot) == (cp == "C")]:
            g, why = judge_entry(legs, pv, [stop], float(spot), t, rd, lots)
            if not g:
                print(f"    stop {stop:,.0f}: no credit to judge"); continue
            r = g["stops"][0]
            print(f"    stop {stop:,.0f} ({r['dist']:.0f} {r['side']}): touched {r['p_hit']:.0%}, loss there "
                  + (f"{r['loss']:+.0f}" if r["loss"] is not None else "n/a")
                  + f"; settles past the short without it {g['p_zone']:.0%}; expected "
                  + (f"{g['ev']:+.0f}" if g["ev"] is not None else "n/a")
                  + (" | REFUSED: " + "; ".join(why) if why else " | passes"))
    return 0


def cmd_feed() -> int:
    last_snap = None
    while True:
        t = now_et()
        if t.weekday() >= 5:
            print("weekend: the desk is closed"); return 0
        apply_limits()
        try:
            for line in cmd_guard():
                print(f"{hm(t)} {line}", flush=True)
        except Exception as exc:  # noqa: BLE001 - the service restarting must not end the loop
            print(f"{hm(t)} guard failed (the service may be restarting): {str(exc)[:120]}", flush=True)
        slot = hm(t)
        if ENTRY_START <= slot <= "15:45" and t.minute % 2 == 0 and slot != last_snap:
            last_snap = slot
            try:
                print(cmd_snapshot(), flush=True)
            except Exception as exc:  # noqa: BLE001
                print(f"{slot} snapshot failed: {exc}", flush=True)
        if slot >= FEED_END:
            print(cmd_summary(t.date()), flush=True)
            return 0
        time.sleep(30)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Claude's paper desk (NDXP 0DTE, discretionary)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snapshot"); s.add_argument("--news", action="store_true")
    o = sub.add_parser("open")
    o.add_argument("--leg", action="append", required=True); o.add_argument("--lots", type=int, default=1)
    o.add_argument("--thesis", required=True); o.add_argument("--exit", required=True, dest="exit_plan")
    o.add_argument("--wrong", required=True)
    o.add_argument("--stop", type=float, action="append", default=[],
                   help="the NDX level that proves the trade wrong (twice for a condor); the gate prices it")
    o.add_argument("--min-credit", type=float, default=None, help="refuse a fill under the credit judged")
    o.add_argument("--style", choices=STYLES, default=None,
                   help="clone: the agent's own clone-strategy trade (the rails hold, the stop-table gate does not); "
                        "condor: the SPX 13:00 iron condor (with --under SPX)")
    o.add_argument("--under", choices=sorted(ROOTS), default=UNDER, help="SPX: the 13:00 iron condor only")
    sub.add_parser("condor")                     # read-only: the SPX 13:00 iron condor menu, no order
    qt = sub.add_parser("quote")                 # read-only: candidate verticals priced and gated, no order
    qt.add_argument("--vertical", action="append", required=True, help="C|P:short:long, e.g. C:29425:29450")
    qt.add_argument("--stop", type=float, action="append", default=[], help="an NDX stop level (repeat)")
    qt.add_argument("--lots", type=int, default=1)
    jd = sub.add_parser("judge")                 # every decision, a pass as much as a trade, goes in the log
    jd.add_argument("--setup", required=True)
    jd.add_argument("--action", choices=["pass", "trade"], required=True)
    jd.add_argument("--why", required=True)
    pr = sub.add_parser("pair")
    pr.add_argument("--ndx", required=True); pr.add_argument("--ndx-lots", type=int, default=1)
    pr.add_argument("--spx", required=True); pr.add_argument("--spx-lots", type=int, default=2)
    pr.add_argument("--thesis", required=True); pr.add_argument("--exit", required=True, dest="exit_plan")
    pr.add_argument("--wrong", required=True)
    pr.add_argument("--stop-bp", type=float, default=None,
                    help="the ratio move against the pair (bp) that proves it wrong; the gate prices it")
    pr.add_argument("--min-credit-usd", type=float, default=None, help="refuse the pair under the credit judged ($)")
    pr.add_argument("--style", choices=STYLES, default=None,
                    help="ratio: the agent's own ratio-strategy trade (the rails hold, the ratio stop table does not)")
    c = sub.add_parser("close"); c.add_argument("--reason", required=True)
    c.add_argument("--tg", default=None, help="close only this position (its trade group; pair leg and trims with it)")
    n = sub.add_parser("note"); n.add_argument("--text", required=True)   # a decision not to trade is a decision too
    tr = sub.add_parser("trim"); tr.add_argument("--lots", type=int, default=1); tr.add_argument("--reason", required=True)
    tr.add_argument("--tg", default=None, help="which position, when two are open")
    sub.add_parser("guard"); sub.add_parser("feed"); sub.add_parser("summary")
    a = ap.parse_args(argv)
    apply_limits()
    if a.cmd == "snapshot":
        print(cmd_snapshot(a.news)); return 0
    if a.cmd == "open":
        return cmd_open([parse_leg(x) for x in a.leg], a.lots, a.thesis, a.exit_plan, a.wrong, a.stop, a.min_credit,
                        a.style, a.under)
    if a.cmd == "condor":
        return cmd_condor()
    if a.cmd == "judge":
        return cmd_judge(a.setup, a.action, a.why)
    if a.cmd == "quote":
        return cmd_quote(a.vertical, a.stop, a.lots)
    if a.cmd == "pair":
        return cmd_pair(parse_legs(a.ndx), a.ndx_lots, parse_legs(a.spx), a.spx_lots, a.thesis, a.exit_plan, a.wrong,
                        a.stop_bp, a.min_credit_usd, a.style)
    if a.cmd == "close":
        return cmd_close(a.reason, a.tg)
    if a.cmd == "trim":
        return cmd_trim(a.lots, a.reason, a.tg)
    if a.cmd == "note":
        t = now_et(); journal(t.date(), f"## {hm(t)} NOTE\n{a.text}"); print("noted"); return 0
    if a.cmd == "guard":
        print("\n".join(cmd_guard()) or "guard: nothing to do"); return 0
    if a.cmd == "summary":
        print(cmd_summary()); return 0
    return cmd_feed()


if __name__ == "__main__":
    sys.exit(main())
