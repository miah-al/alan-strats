"""
python -m scripts.claude_desk <command> -- the desk Claude trades NDX 0DTE from, discretionary, on PAPER only.

No algorithm: Claude reads the snapshot, decides, and says why. The rails below are code, not judgment, and every
order goes through the service's paper order book (POST /api/orders, account "paper"; ``account: live`` is refused
there and nothing in the service talks to a broker's order API). Strategy name in the ledger: claude_discretionary.

Rails (agreed 2026-09-28; since 2026-09-29 the trader's, in the service's database: the app's Limits page or
GET/PUT /api/limits/claude_discretionary, read before every command and every feed poll; the values below are the
defaults):
  - NDXP same-day options, defined risk only (preview's max loss must be finite), at most 4 legs;
  - at most 2 lots, at most $2,500 at risk per position, one position at a time;
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
  trim --lots N --reason ...        take N lots off (an offsetting order: the paper book closes groups whole)
  close --reason ...                close every open claude_discretionary position at market (paper mid)
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
MAX_LOTS, MAX_RISK, DAY_STOP, MAX_POSITIONS = 2, 2500.0, -2500.0, 1
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
    realised, marked, opened = day_pnl(day)
    L.append(f"  book: day {realised + marked:+,.0f} (realised {realised:+,.0f}, open {marked:+,.0f})"
             + (" | DONE for the day" if st.get("done") else ""))
    for r in opened:
        L.append(f"    open {r.get('structure')} x{r.get('contracts')} entry {r.get('entry_net')} mark {r.get('mark')} "
                 f"pnl {r.get('pnl')} max loss {r.get('max_loss')} ({r.get('trade_group_id')})")
    used = trades_today(st)
    ok = (not st.get("done")) and len(opened) < MAX_POSITIONS and used < MAX_TRADES and ENTRY_START <= hm(t) <= ENTRY_END
    L.append(f"  entries {'OPEN' if ok else 'closed'} (rails: <= {MAX_LOTS} lots, <= ${MAX_RISK:,.0f} at risk, "
             f"<= {MAX_POSITIONS} position(s), <= {MAX_TRADES} trades a day ({used} used), {ENTRY_START}-{ENTRY_END}, "
             f"stop {DAY_STOP:+,.0f}, flat {FLAT_AT}" + (", PREMIUM ONLY: no debits" if PREMIUM_ONLY else "") + ")")
    if PREMIUM_ONLY:
        L.append("  mode: premium only - on a range day sell a condor or credit spread outside the range once it is set; "
                 "on a trend day stand aside")
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


def cmd_open(legs: list[dict], lots: int, thesis: str, exit_plan: str, wrong: str) -> int:
    t = now_et(); day = t.date(); st = load_state(day)
    why = []
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
    if len(opened) >= MAX_POSITIONS:
        why.append(f"{len(opened)} position(s) open, the limit is {MAX_POSITIONS}")
    if realised + marked <= DAY_STOP:
        why.append("the day stop is hit")
    q = quote(UNDER)
    if (reason := itm_short(legs, q.get("last") or q.get("close"), UNDER)) is not None:
        why.append(reason)
    first = preview(legs, lots, day)
    time.sleep(SETTLE_S)
    pv = preview(legs, lots, day)
    ml = pv.get("max_loss")
    if not pv.get("ok") or pv.get("net_mid") is None:
        why.append("no two-sided quote for every leg")
    stale = sorted({str(l.get("source")) for l in pv.get("legs", []) if l.get("source") != "tastytrade"})
    if stale:                                  # a fallback feed (yfinance, polygon) can be minutes old: a fill there is fake
        why.append(f"legs priced from {', '.join(stale)}, not the live tastytrade stream")
    why += quote_problems(first, pv, legs, UNDER)
    if (reason := premium_refusal(pv, PREMIUM_ONLY)) is not None:
        why.append(reason)
    if ml is None:
        why.append("risk is not defined (no finite max loss)")
    elif abs(float(ml)) > MAX_RISK + 1e-6:
        why.append(f"max loss {abs(float(ml)):,.0f} is over ${MAX_RISK:,.0f}")
    if why:
        print("REFUSED: " + "; ".join(why)); return 2
    spot = pv.get("spot") or market().get("spot")
    desc = " ".join(f"{l['side']} {l['cp']}{l['strike']:.0f}" for l in legs)
    journal(day, f"## {hm(t)} OPEN {desc} x{lots}\n- NDX {spot}; net mid {pv['net_mid']} ({pv['debit_credit']}), "
                 f"max loss {ml}, max profit {pv.get('max_profit')}\n- thesis: {thesis}\n- exit: {exit_plan}\n"
                 f"- wrong if: {wrong}")
    res = api("POST", "/orders", order_body(legs, lots, day, thesis))
    tg = res.get("trade_group_id")
    st["positions"][str(tg)] = {"legs": legs, "lots": lots, "opened": hm(t), "spot": spot, "fill": res.get("fill_price"),
                                "cost": crossing_cost(legs, float(spot or 0)), "thesis": thesis}
    save_state(day, st)
    journal(day, f"- filled: status {res.get('status')}, net {res.get('fill_price')}, trade group {tg}")
    print(f"OPENED {desc} x{lots}: {res.get('status')} at {res.get('fill_price')} (trade group {tg}); max loss {ml}")
    return 0


def cmd_pair(ndx_legs: list[dict], ndx_lots: int, spx_legs: list[dict], spx_lots: int, thesis: str, exit_plan: str,
             wrong: str) -> int:
    """The NDX/SPX ratio trade as ONE position: an NDXP spread and an SPXW spread, checked together against the rails
    (their max losses summed against the per-position rail, one trade, the book must be flat) and opened together. If
    the second order does not fill, the first is closed at once: the desk never holds half a pair."""
    t = now_et(); day = t.date(); st = load_state(day)
    why = []
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
    if opened:
        why.append(f"{len(opened)} position(s) open: a pair needs a flat book")
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
    if why:
        print("REFUSED: " + "; ".join(why)); return 2
    rs = ratio_now()
    dn = " ".join(f"{l['side']} {l['cp']}{l['strike']:.0f}" for l in ndx_legs)
    ds = " ".join(f"{l['side']} {l['cp']}{l['strike']:.0f}" for l in spx_legs)
    journal(day, f"## {hm(t)} OPEN PAIR NDX {dn} x{ndx_lots} + SPX {ds} x{spx_lots}\n- {ratio_line(rs)}\n"
                 f"- NDX net mid {pvs['NDX']['net_mid']} ({pvs['NDX']['debit_credit']}), max loss {pvs['NDX'].get('max_loss')}; "
                 f"SPX net mid {pvs['SPX']['net_mid']} ({pvs['SPX']['debit_credit']}), max loss {pvs['SPX'].get('max_loss')}; "
                 f"together {total:,.0f}\n- thesis: {thesis}\n- exit: {exit_plan}\n- wrong if: {wrong}")
    res_n = api("POST", "/orders", order_body(ndx_legs, ndx_lots, day, thesis, "NDX"))
    tg_n = res_n.get("trade_group_id")
    if res_n.get("status") != "filled" or not tg_n:
        journal(day, f"- NDX leg not filled ({res_n.get('status')}); nothing opened")
        print(f"NOT OPENED: the NDX leg came back {res_n.get('status')}"); return 3
    st["positions"][str(tg_n)] = {"legs": ndx_legs, "lots": ndx_lots, "opened": hm(t), "spot": rs.get("ndx"),
                                  "fill": res_n.get("fill_price"), "under": "NDX", "thesis": thesis,
                                  "cost": crossing_cost(ndx_legs, float(rs.get("ndx") or 0), "NDX"),
                                  "max_loss": pvs["NDX"].get("max_loss")}
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


def _close_all(day: date, reason: str) -> list[str]:
    st = load_state(day); out = []
    for r in my_positions("open"):
        tg = r["trade_group_id"]
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


def cmd_trim(lots: int, reason: str) -> int:
    """Take part of the open position off: the paper book closes a trade group whole, so a trim is an offsetting
    order for ``lots`` units (the open legs with their sides reversed). The ledger then holds two groups that net to
    the smaller position; ``close`` later closes both, and the day's P&L sums them."""
    t = now_et(); day = t.date(); st = load_state(day)
    opened = my_positions("open")
    longs = [r for r in opened if str(r.get("trade_group_id")) in st["positions"]]
    if not longs or not reason.strip():
        print("REFUSED: nothing of mine open to trim, or no reason given"); return 2
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


def cmd_close(reason: str) -> int:
    if not reason.strip():
        print("REFUSED: a reason is required"); return 2
    lines = _close_all(now_et().date(), reason)
    print("\n".join(lines) if lines else "nothing open")
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
    pr = sub.add_parser("pair")
    pr.add_argument("--ndx", required=True); pr.add_argument("--ndx-lots", type=int, default=1)
    pr.add_argument("--spx", required=True); pr.add_argument("--spx-lots", type=int, default=2)
    pr.add_argument("--thesis", required=True); pr.add_argument("--exit", required=True, dest="exit_plan")
    pr.add_argument("--wrong", required=True)
    c = sub.add_parser("close"); c.add_argument("--reason", required=True)
    n = sub.add_parser("note"); n.add_argument("--text", required=True)   # a decision not to trade is a decision too
    tr = sub.add_parser("trim"); tr.add_argument("--lots", type=int, default=1); tr.add_argument("--reason", required=True)
    sub.add_parser("guard"); sub.add_parser("feed"); sub.add_parser("summary")
    a = ap.parse_args(argv)
    apply_limits()
    if a.cmd == "snapshot":
        print(cmd_snapshot(a.news)); return 0
    if a.cmd == "open":
        return cmd_open([parse_leg(x) for x in a.leg], a.lots, a.thesis, a.exit_plan, a.wrong)
    if a.cmd == "pair":
        return cmd_pair(parse_legs(a.ndx), a.ndx_lots, parse_legs(a.spx), a.spx_lots, a.thesis, a.exit_plan, a.wrong)
    if a.cmd == "close":
        return cmd_close(a.reason)
    if a.cmd == "trim":
        return cmd_trim(a.lots, a.reason)
    if a.cmd == "note":
        t = now_et(); journal(t.date(), f"## {hm(t)} NOTE\n{a.text}"); print("noted"); return 0
    if a.cmd == "guard":
        print("\n".join(cmd_guard()) or "guard: nothing to do"); return 0
    if a.cmd == "summary":
        print(cmd_summary()); return 0
    return cmd_feed()


if __name__ == "__main__":
    sys.exit(main())
