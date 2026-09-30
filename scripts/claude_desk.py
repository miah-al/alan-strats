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
# The rails. These are the fallbacks: the values in force are the trader's, in the service's database (app.TradeLimit,
# set on the app's Limits page or PUT /api/limits/claude_discretionary/<name>), read before every command and on every
# feed poll (apply_limits). The desk never changes them itself.
MAX_LOTS, MAX_RISK, DAY_STOP, MAX_POSITIONS = 2, 2500.0, -2500.0, 1
MAX_TRADES = 3                                  # new positions per day (a trim or a close is not one)
ENTRY_START, ENTRY_END, FLAT_AT, FEED_END = "09:45", "15:30", "15:55", "16:00"
NY = "America/New_York"
STATE_DIR = Path(__file__).resolve().parents[1] / "paper_state" / "claude_desk"
NEWS_EVERY_S = 600


# ── plumbing ──────────────────────────────────────────────────────────────────

def apply_limits() -> None:
    """Take the limits in force from the service (GET /api/limits/<SLUG>). If it cannot answer, the last values stay:
    the desk cannot trade without the service anyway."""
    global MAX_LOTS, MAX_RISK, DAY_STOP, MAX_POSITIONS, MAX_TRADES, ENTRY_START, ENTRY_END, FLAT_AT
    try:
        v = api("GET", f"/limits/{SLUG}", timeout=10.0).get("values") or {}
    except Exception:  # noqa: BLE001
        return
    MAX_LOTS = int(v.get("max_lots", MAX_LOTS))
    MAX_RISK = float(v.get("max_risk", MAX_RISK))
    DAY_STOP = -abs(float(v.get("day_stop", DAY_STOP)))
    MAX_POSITIONS = int(v.get("max_positions", MAX_POSITIONS))
    MAX_TRADES = int(v.get("max_trades", MAX_TRADES))
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


def occ(cp: str, strike: float, day: date) -> str:
    return f"{ROOT}{day:%y%m%d}{cp}{int(round(strike * 1000)):08d}"


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


def crossing_cost(legs: list[dict], spot: float) -> float:
    """Points per unit the live runners would pay to cross, on one side (the measured model: 1.2 when a vertical's
    long leg is 25+ in the money, 0.1 nearer). Legs pair into verticals by right; an unpaired leg counts as near."""
    cost = 0.0
    for cp in ("C", "P"):
        longs = [l for l in legs if l["cp"] == cp and l["side"] == "buy"]
        shorts = [l for l in legs if l["cp"] == cp and l["side"] == "sell"]
        for lg in longs[:max(len(shorts), 1)] if shorts else longs:
            itm = (spot - lg["strike"]) if cp == "C" else (lg["strike"] - spot)
            cost += 1.2 if itm >= 25 else 0.1
        cost += 0.1 * max(0, len(shorts) - len(longs))
    return cost


def order_body(legs: list[dict], lots: int, day: date, label: str) -> dict:
    return {"account": "paper", "underlying": UNDER, "order_type": "market", "tif": "day", "strategy": SLUG,
            "label": label[:200], "client_order_id": f"claude-{uuid.uuid4().hex[:12]}",
            "legs": [{"type": "call" if l["cp"] == "C" else "put", "strike": l["strike"], "expiry": day.isoformat(),
                      "side": l["side"], "quantity": lots, "symbol": occ(l["cp"], l["strike"], day)} for l in legs]}


def preview(legs: list[dict], lots: int, day: date) -> dict:
    return api("POST", "/orders/preview", order_body(legs, lots, day, "preview"))


def parse_leg(s: str) -> dict:
    side, cp, k = s.split(":")
    side, cp = side.lower(), cp.upper()[0]
    if side not in ("buy", "sell") or cp not in ("C", "P"):
        raise SystemExit(f"bad leg {s!r}: use buy|sell:C|P:strike")
    return {"side": side, "cp": cp, "strike": float(k)}


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
    """New positions opened today (a trim's offsetting group is not a trade)."""
    return sum(1 for m in (st.get("positions") or {}).values() if not m.get("trim_of"))


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
             f"stop {DAY_STOP:+,.0f}, flat {FLAT_AT})")
    if spot and ok:
        atm = round(spot / 25.0) * 25.0
        cands = [("bull call", [("buy", "C", k), ("sell", "C", k + 25)]) for k in (atm - 25, atm, atm + 25)] + \
                [("bear put", [("buy", "P", k), ("sell", "P", k - 25)]) for k in (atm + 25, atm, atm - 25)] + \
                [("iron fly", [("sell", "C", atm), ("buy", "C", atm + 50), ("sell", "P", atm), ("buy", "P", atm - 50)])]
        for name, spec in cands:
            legs = [{"side": s, "cp": c, "strike": k} for s, c, k in spec]
            try:
                pv = preview(legs, 1, day)
                strikes = "/".join(f"{k:.0f}" for _, _, k in spec)
                L.append(f"    {name:<9} {strikes:<23} net {pv.get('net_mid')} max loss {pv.get('max_loss')} "
                         f"max profit {pv.get('max_profit')}")
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
    pv = preview(legs, lots, day)
    ml = pv.get("max_loss")
    if not pv.get("ok") or pv.get("net_mid") is None:
        why.append("no two-sided quote for every leg")
    stale = sorted({str(l.get("source")) for l in pv.get("legs", []) if l.get("source") != "tastytrade"})
    if stale:                                  # a fallback feed (yfinance, polygon) can be minutes old: a fill there is fake
        why.append(f"legs priced from {', '.join(stale)}, not the live tastytrade stream")
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
        pv = preview(meta["legs"], int(meta["lots"]), day)
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
