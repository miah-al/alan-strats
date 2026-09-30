"""
python -m scripts.claude_news <command> -- the news desk Claude trades from: Truth posts, headlines and official
releases, traded on PAPER by judgment (the user, 2026-09-29: "Claude decides"). Strategy name in the ledger:
claude_events.

Not an algorithm. The desk shows each new item once, with its theme, how late it reached us (published -> seen) and
what the market has already done since it was published; Claude decides whether there is a trade left, and says why.
Every order goes through the service's paper order book (POST /api/orders, account "paper"), priced by the tastytrade
stream only (a leg from any other feed is refused, as on the NDX desk).

Instruments: liquid ETFs by theme -- IBIT (crypto), USO (oil), TLT (rates), SPY / QQQ (the market), GLD (war, havens) --
as shares with a stop, or a defined-risk option spread. Positions may be held overnight when the thesis says so.

Rails: the trader's, in the service's database (the app's Limits page, GET /api/limits/claude_events), read before every
command: risk per trade (shares: quantity x distance to the stop; a spread: its max loss), money per position, open
positions, the day stop (no new entry past it), the entry window. Claude never changes them.

Latency, measured: Truth posts come from a mirror refreshed about every 5 minutes; GDELT headlines are cached 10
minutes. What is tradable is the follow-through or the reversal, rarely the first move; every item logs its lag.

Commands:
  watch                     for the Monitor tool: posts every 60 s (a HEAD; the archive only when it changed),
                            headlines and official releases every 10 min, each new item once with its theme and the
                            market since it; the guard every 30 s; the book every 30 min; ends after 16:05 ET
  snapshot                  the watchlist (last, day move, 30-min move), the book, the rails
  open --symbol IBIT --side buy --qty 50 --stop 45.80 [--target 49] [--until 2026-10-02T15:45]
       --thesis ... --exit ... --wrong ... [--event "the item"]            shares
  open --symbol USO --leg buy:C:80:2026-10-17 --leg sell:C:84:2026-10-17 --lots 1 --stop-under 77.5 ...  a spread
  close --tg ID --reason ... | close --all --reason ...
  note --text ...           journal a decision (letting an item pass is a decision)
  guard                     stops / targets on the underlying's last price, time exits; prints what it did
  summary                   the day's trades and P&L
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from scripts.claude_desk import api, hm, now_et

SLUG = "claude_events"
NY = "America/New_York"
STATE_DIR = Path(__file__).resolve().parents[1] / "paper_state" / "claude_events"
WATCH = ["IBIT", "USO", "SPY", "QQQ", "TLT", "GLD"]

# Fallback rails; the values in force are the trader's (apply_limits).
MAX_RISK, MAX_NOTIONAL, MAX_POSITIONS, DAY_STOP = 1000.0, 10000.0, 2, -1500.0
ENTRY_START, ENTRY_END = "09:35", "15:50"

THEMES: dict[str, tuple[re.Pattern, list[str]]] = {
    "crypto": (re.compile(r"\b(bitcoin|btc|crypto\w*|ethereum|stablecoins?|coinbase|digital assets?|strategic (bitcoin )?reserve)\b", re.I), ["IBIT"]),
    "oil": (re.compile(r"\b(oil|crude|opec\+?|hormuz|iran\w*|saudi\w*|refiner\w*|pipelines?|brent|wti|drill\w*|barrels?)\b", re.I), ["USO"]),
    "rates": (re.compile(r"\b(fed|federal reserve|powell|rate cuts?|rate hikes?|interest rates?|inflation|cpi|pce|treasur\w*|yields?|bonds?)\b", re.I), ["TLT", "SPY"]),
    "trade": (re.compile(r"\b(tariffs?|trade (deal|war)|china|chinese|exports?|imports?|sanctions?)\b", re.I), ["SPY", "QQQ"]),
    "war": (re.compile(r"\b(war|air ?strikes?|missiles?|invasion|attack\w*|bomb\w*|nuclear|cease[- ]?fire|israel\w*|iran\w*|russia\w*|ukrain\w*)\b", re.I), ["SPY", "GLD", "USO"]),
    "tech": (re.compile(r"\b(nvidia|chips?|semiconductors?|apple|tesla|microsoft|artificial intelligence)\b", re.I), ["QQQ"]),
    "market": (re.compile(r"\b(stock market|nasdaq|dow|s&p|stocks|wall street)\b", re.I), ["SPY", "QQQ"]),
}
# A second headline query for the desk (the brief's own stays as it is): under GDELT's ~120 characters.
DESK_QUERY = '(bitcoin OR crypto OR crude OR OPEC OR Hormuz OR Powell OR "rate cut" OR tariff) sourcelang:english'


# ── plumbing ──────────────────────────────────────────────────────────────────

def apply_limits() -> None:
    """The rails in force (GET /api/limits/claude_events); the last values stay if the service cannot answer."""
    global MAX_RISK, MAX_NOTIONAL, MAX_POSITIONS, DAY_STOP, ENTRY_START, ENTRY_END
    try:
        v = api("GET", f"/limits/{SLUG}", timeout=10.0).get("values") or {}
    except Exception:  # noqa: BLE001
        return
    MAX_RISK = float(v.get("max_risk", MAX_RISK))
    MAX_NOTIONAL = float(v.get("max_notional", MAX_NOTIONAL))
    MAX_POSITIONS = int(v.get("max_positions", MAX_POSITIONS))
    DAY_STOP = -abs(float(v.get("day_stop", DAY_STOP)))
    ENTRY_START = str(v.get("entry_start", ENTRY_START))
    ENTRY_END = str(v.get("entry_end", ENTRY_END))


def load_state() -> dict:
    f = STATE_DIR / "state.json"
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"positions": {}, "seen": [], "last": {}}


def save_state(st: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    st["seen"] = st.get("seen", [])[-2000:]
    (STATE_DIR / "state.json").write_text(json.dumps(st, indent=1, default=str), encoding="utf-8")


def journal(day: date, text: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATE_DIR / f"journal_{day.isoformat()}.md", "a", encoding="utf-8") as f:
        f.write(text.rstrip() + "\n\n")


def themes_of(text: str) -> list[str]:
    return [name for name, (rx, _i) in THEMES.items() if rx.search(text or "")]


def instruments_for(themes: list[str]) -> list[str]:
    out: list[str] = []
    for t in themes:
        out += [s for s in THEMES[t][1] if s not in out]
    return out or ["SPY"]


def quote(sym: str) -> dict:
    try:
        return api("GET", f"/market/quote/{sym}", timeout=10.0)
    except Exception:  # noqa: BLE001
        return {}


def price_at(sym: str, when: pd.Timestamp) -> tuple[Optional[float], Optional[float]]:
    """(price at ``when`` from today's 1-minute bars, the latest bar's close); (None, None) when there are no bars."""
    try:
        d = api("GET", f"/market/intraday/{sym}?minutes=390", timeout=20.0)
    except Exception:  # noqa: BLE001
        return None, None
    ts = [pd.Timestamp(t) for t in d.get("t") or []]
    cs = d.get("c") or []
    pairs = [(t, float(c)) for t, c in zip(ts, cs) if c is not None]
    if not pairs:
        return None, None
    at = next((c for t, c in pairs if t >= when), None)
    return (at if at is not None else pairs[0][1]), pairs[-1][1]


def move_since(sym: str, when: pd.Timestamp) -> str:
    q = quote(sym)
    last = q.get("last") or q.get("mid")
    p0, _ = price_at(sym, when)
    day = f"{q.get('change_pct', 0):+.2f}% today" if q.get("change_pct") is not None else ""
    if last and p0:
        return f"{sym} {last:,.2f} ({(last / p0 - 1) * 100:+.2f}% since it, {day})"
    return f"{sym} {last:,.2f} ({day})" if last else f"{sym}: no quote"


# ── the news ──────────────────────────────────────────────────────────────────

_HEADLINE_CACHE: dict = {}


def fetch_items(since: datetime, want: set[str], notes: Optional[list] = None) -> list[dict]:
    """New items from the brief's sources: posts (``want`` has "post"), headlines and official releases ("news"). Each:
    {id, kind, time (ET), text, source}. A source that fails adds a line to ``notes`` (the watch prints it) instead of
    failing the rest."""
    notes = notes if notes is not None else []
    from api.bootstrap import bootstrap
    bootstrap()
    from api.services import brief_sources as B
    out: list[dict] = []
    if "post" in want:
        blk = B.posts_block(since) or {}
        notes += [f"posts: {n}" for n in blk.get("notes") or []]
        for p in blk.get("items") or []:
            out.append({"id": "post:" + str(p.get("id") or p.get("time_et")), "kind": "post", "time": p.get("time_et"),
                        "text": p.get("text") or "", "source": "Truth Social"})
    if "news" in want:
        for q in (B.GDELT_QUERY, DESK_QUERY):
            try:
                saved = B.GDELT_QUERY
                B.GDELT_QUERY = q
                B._GDELT_CACHE.clear()          # one slot, keyed on the day: each query fetched fresh (every 10 min)
                blk = B.headlines_block(since) or {}
                items = blk.get("items") or []
                notes += [f"headlines: {n}" for n in blk.get("notes") or []]
            finally:
                B.GDELT_QUERY = saved
            for h in items:
                out.append({"id": "news:" + re.sub(r"\W+", "", str(h.get("title") or ""))[:80].lower(), "kind": "news",
                            "time": h.get("time_et"), "text": h.get("title") or "",
                            "source": f"{h.get('domain') or 'GDELT'}" + (f" +{h['sources'] - 1} more" if (h.get("sources") or 1) > 1 else "")})
            time.sleep(12)                       # GDELT: one request at a time, 5 s apart (in practice a burst needs more)
        blk = B.official_block(since) or {}
        notes += [f"official: {n}" for n in blk.get("notes") or []]
        for o in blk.get("items") or []:
            out.append({"id": "official:" + str(o.get("title"))[:80], "kind": "official", "time": o.get("time_et") or o.get("time"),
                        "text": o.get("title") or o.get("summary") or "", "source": o.get("source") or "official"})
    return out


def _item_time(item: dict, now: pd.Timestamp) -> pd.Timestamp:
    """The item's time in ET: the sources write "HH:MM" (today) or a full timestamp."""
    t = str(item.get("time") or "").strip()
    if not t:
        return now
    try:
        if re.fullmatch(r"\d{1,2}:\d{2}", t):
            return pd.Timestamp(f"{now.date()} {t}", tz=NY)
        ts = pd.Timestamp(t)
        if pd.isna(ts):
            return now
        return ts.tz_localize(NY) if ts.tzinfo is None else ts.tz_convert(NY)
    except (ValueError, TypeError):
        return now


def describe(item: dict, now: pd.Timestamp) -> str:
    when = _item_time(item, now)
    lag = max(0.0, (now - when).total_seconds() / 60.0)
    th = themes_of(item["text"])
    head = f"{hm(now)} NEW {item['kind'].upper()} {when:%H:%M} (seen {lag:.0f} min later) [{', '.join(th) or 'no theme'}]"
    lines = [head, f"  {item['source']}: {item['text'][:300]}"]
    if th:
        lines.append("  market: " + " | ".join(move_since(s, when) for s in instruments_for(th)))
    return "\n".join(lines)


# ── the book ──────────────────────────────────────────────────────────────────

def my_positions(status: str = "open") -> list[dict]:
    rows = api("GET", f"/paper/positions?status={status}").get("rows", [])
    return [r for r in rows if r.get("strategy") == SLUG]


def day_pnl(day: date) -> tuple[float, float, list[dict]]:
    opened = my_positions("open")
    closed = [r for r in my_positions("closed") if str(r.get("closed") or "")[:10] == day.isoformat()]
    return sum(float(r.get("pnl") or 0) for r in closed), sum(float(r.get("pnl") or 0) for r in opened), opened


def share_rails(qty: int, price: float, stop: float, side: str) -> list[str]:
    """Why a share order breaks the rails ([] = it doesn't): risk to the stop and money in the position."""
    why = []
    if qty < 1:
        why.append("quantity must be at least 1")
    risk = qty * ((price - stop) if side == "buy" else (stop - price))
    if risk <= 0:
        why.append(f"the stop {stop} is on the wrong side of {price} for a {side}")
    elif risk > MAX_RISK + 1e-6:
        why.append(f"risk to the stop {risk:,.0f} is over ${MAX_RISK:,.0f} (at most {int(MAX_RISK // abs(price - stop))} shares)")
    if qty * price > MAX_NOTIONAL + 1e-6:
        why.append(f"{qty * price:,.0f} in the position is over ${MAX_NOTIONAL:,.0f}")
    return why


def parse_leg(s: str) -> dict:
    side, cp, k, exp = s.split(":")
    if side not in ("buy", "sell") or cp.upper()[0] not in "CP":
        raise SystemExit(f"bad leg {s!r}: use buy|sell:C|P:strike:YYYY-MM-DD")
    return {"type": "call" if cp.upper()[0] == "C" else "put", "side": side, "strike": float(k), "expiry": exp[:10]}


def cmd_open(a) -> int:
    t = now_et(); day = t.date(); st = load_state()
    sym = a.symbol.upper()
    why = []
    if not ENTRY_START <= hm(t) <= ENTRY_END or t.weekday() >= 5:
        why.append(f"entries only {ENTRY_START}-{ENTRY_END} on weekdays")
    if not (a.thesis.strip() and a.exit_plan.strip() and a.wrong.strip()):
        why.append("thesis, exit and what-proves-me-wrong are all required")
    realised, marked, opened = day_pnl(day)
    if len(opened) >= MAX_POSITIONS:
        why.append(f"{len(opened)} position(s) open, the limit is {MAX_POSITIONS}")
    if realised + marked <= DAY_STOP:
        why.append(f"the day stop is hit ({realised + marked:+,.0f})")
    if a.leg:
        legs = [dict(parse_leg(x), quantity=a.lots) for x in a.leg]
        body = {"account": "paper", "underlying": sym, "order_type": "market", "tif": "day", "strategy": SLUG, "legs": legs}
    else:
        if a.qty is None or a.stop is None:
            why.append("shares need --qty and --stop")
        if a.side == "sell":                        # the owner's account cannot short (2026-09-30: "I cannot short")
            why.append("the account cannot short shares: get the exposure with a long put (--leg buy:P:<strike>:<expiry>)")
        legs = [{"type": "stock", "side": a.side, "quantity": int(a.qty or 0)}]
        body = {"account": "paper", "underlying": sym, "order_type": "market", "tif": "day", "strategy": SLUG, "legs": legs}
    pv = api("POST", "/orders/preview", body)
    if not pv.get("ok") or pv.get("net_mid") is None:
        why.append("no two-sided quote for every leg")
    stale = sorted({str(l.get("source")) for l in pv.get("legs", []) if l.get("source") != "tastytrade"})
    if stale:
        why.append(f"priced from {', '.join(stale)}, not the live tastytrade stream")
    if a.leg:
        ml = pv.get("max_loss")
        if ml is None:
            why.append("risk is not defined (no finite max loss)")
        elif abs(float(ml)) > MAX_RISK + 1e-6:
            why.append(f"max loss {abs(float(ml)):,.0f} is over ${MAX_RISK:,.0f}")
    elif pv.get("net_mid") is not None and a.stop is not None:
        # the preview's net is signed (a sale is a credit, -145.85): the rails want the share price
        why += share_rails(int(a.qty), abs(float(pv["net_mid"])), float(a.stop), a.side)
    if why:
        print("REFUSED: " + "; ".join(why)); return 2
    label = f"claude_events: {a.thesis[:150]}"
    journal(day, f"## {hm(t)} OPEN {sym} {'spread' if a.leg else a.side + ' ' + str(a.qty)}\n"
                 f"- event: {a.event or '-'}\n- thesis: {a.thesis}\n- exit: {a.exit_plan}\n- wrong if: {a.wrong}\n"
                 f"- stop: {a.stop if a.stop is not None else a.stop_under} target: {a.target} until: {a.until}\n- preview: {pv.get('net_mid')}")
    res = api("POST", "/orders", dict(body, label=label, client_order_id=f"claude-ev-{int(time.time())}"))
    tg = res.get("trade_group_id")
    if res.get("status") != "filled" or not tg:
        print(f"NOT FILLED: {res.get('status')} {res.get('message')}"); return 3
    st.setdefault("positions", {})[tg] = {"symbol": sym, "kind": "spread" if a.leg else "shares", "side": a.side,
                                          "stop": a.stop, "stop_under": a.stop_under, "stop_over": a.stop_over,
                                          "target": a.target, "until": a.until, "opened_at": t.isoformat(),
                                          "thesis": a.thesis, "event": a.event}
    save_state(st)
    print(f"OPENED {sym} ({tg}) at {res.get('fill_price')}")
    return 0


def _close(tg: str, reason: str) -> str:
    try:
        res = api("POST", f"/paper/positions/{tg}/close", {"order_type": "market"})
    except Exception as exc:  # noqa: BLE001
        return f"close {tg} failed: {exc}"
    journal(now_et().date(), f"## {hm(now_et())} CLOSE {tg}\n- reason: {reason}\n- result: {res.get('status')} {res.get('fill_price')}")
    st = load_state()
    st.get("positions", {}).pop(tg, None)
    save_state(st)
    return f"CLOSED {tg}: {res.get('status')} at {res.get('fill_price')} ({reason})"


def exit_reason(meta: dict, last: float, now: pd.Timestamp) -> Optional[str]:
    """Why an event position should be closed now, or None: the stop, the target (on the underlying's last) or the time."""
    side = meta.get("side") or "buy"
    stop, target = meta.get("stop"), meta.get("target")
    if meta.get("kind") == "shares" and stop is not None:
        if (side == "buy" and last <= float(stop)) or (side == "sell" and last >= float(stop)):
            return f"stop {stop} hit (last {last})"
    if meta.get("stop_under") is not None and last <= float(meta["stop_under"]):
        return f"underlying under {meta['stop_under']} (last {last})"
    if meta.get("stop_over") is not None and last >= float(meta["stop_over"]):
        return f"underlying over {meta['stop_over']} (last {last})"
    if target is not None and ((side == "buy" and last >= float(target)) or (side == "sell" and last <= float(target))):
        return f"target {target} reached (last {last})"
    if meta.get("until"):
        until = pd.Timestamp(meta["until"])
        until = until.tz_localize(NY) if until.tzinfo is None else until
        if now >= until:
            return f"time exit ({meta['until']})"
    return None


def cmd_guard() -> list[str]:
    t = now_et()
    if t.weekday() >= 5 or not ("09:30" <= hm(t) <= "15:59"):
        return []
    st = load_state()
    out = []
    for tg, meta in list(st.get("positions", {}).items()):
        q = quote(meta["symbol"])
        last = q.get("last") or q.get("mid")
        if not last or q.get("source") != "tastytrade":
            continue                                    # no live price: never act on a stale one
        why = exit_reason(meta, float(last), t)
        if why:
            out.append(_close(tg, why))
    return out


def cmd_snapshot() -> str:
    t = now_et(); day = t.date()
    L = [f"NEWS DESK {hm(t)} ET"]
    row = []
    for s in WATCH:
        q = quote(s)
        last = q.get("last") or q.get("mid")
        if last:
            row.append(f"{s} {last:,.2f} ({(q.get('change_pct') or 0):+.2f}%)")
    L.append("  " + " | ".join(row))
    try:
        realised, marked, opened = day_pnl(day)
        L.append(f"  book: day {realised + marked:+,.0f} (realised {realised:+,.0f}, open {marked:+,.0f})")
        st = load_state()
        for r in opened:
            m = st.get("positions", {}).get(str(r.get("trade_group_id")), {})
            L.append(f"    {r.get('structure')} x{r.get('contracts')} pnl {r.get('pnl')} stop {m.get('stop') or m.get('stop_under') or m.get('stop_over')} "
                     f"target {m.get('target')} until {m.get('until')} ({r.get('trade_group_id')})")
        ok = len(opened) < MAX_POSITIONS and realised + marked > DAY_STOP and ENTRY_START <= hm(t) <= ENTRY_END
        L.append(f"  entries {'OPEN' if ok else 'closed'} (rails: <= ${MAX_RISK:,.0f} risk, <= ${MAX_NOTIONAL:,.0f} a position, "
                 f"<= {MAX_POSITIONS} positions, {ENTRY_START}-{ENTRY_END}, day stop {DAY_STOP:+,.0f})")
    except Exception as exc:  # noqa: BLE001
        L.append(f"  book unavailable: {exc}")
    return "\n".join(L)


def cmd_watch() -> int:
    st = load_state()
    seen = set(st.get("seen", []))
    last_news = last_post = last_book = 0.0
    first = True
    while True:
        t = now_et()
        apply_limits()
        try:
            for line in cmd_guard():
                print(f"{hm(t)} {line}", flush=True)
        except Exception as exc:  # noqa: BLE001 - the service restarting must not end the loop
            print(f"{hm(t)} guard failed: {str(exc)[:120]}", flush=True)
        want = set()
        if time.monotonic() - last_post >= 60:
            want.add("post"); last_post = time.monotonic()
        if time.monotonic() - last_news >= 600:
            want.add("news"); last_news = time.monotonic()
        if want:
            since = (t - pd.Timedelta(hours=2)).to_pydatetime() if first else (t - pd.Timedelta(hours=1)).to_pydatetime()
            notes: list[str] = []
            try:
                items = fetch_items(since, want, notes)
            except Exception as exc:  # noqa: BLE001
                items = []
                notes.append(f"news unavailable: {str(exc)[:120]}")
            for n in dict.fromkeys(notes):             # a source down is said once per poll, never silently
                print(f"{hm(t)} SOURCE {n}", flush=True)
            fresh = [i for i in items if i["id"] not in seen]
            for i in fresh:
                seen.add(i["id"])
                if first and not themes_of(i["text"]):
                    continue                            # the backlog at start: only what could matter
                try:
                    print(describe(i, now_et()), flush=True)
                except Exception as exc:  # noqa: BLE001
                    print(f"{hm(t)} NEW {i['kind']}: {i['text'][:200]} (market unavailable: {exc})", flush=True)
            if fresh:
                st = load_state(); st["seen"] = sorted(seen)[-2000:]; save_state(st)
            first = False
        if time.monotonic() - last_book >= 1800 and "09:30" <= hm(t) <= "16:00":
            last_book = time.monotonic()
            try:
                print(cmd_snapshot(), flush=True)
            except Exception as exc:  # noqa: BLE001
                print(f"{hm(t)} snapshot failed: {exc}", flush=True)
        if hm(t) >= "16:05" or t.weekday() >= 5:
            print(cmd_summary(t.date()), flush=True)
            return 0
        time.sleep(30)


def cmd_summary(day: Optional[date] = None) -> str:
    day = day or now_et().date()
    closed = [r for r in my_positions("closed") if str(r.get("closed") or "")[:10] == day.isoformat()]
    opened = my_positions("open")
    L = [f"NEWS DESK SUMMARY {day}: {len(closed)} closed, P&L {sum(float(r.get('pnl') or 0) for r in closed):+,.0f}; "
         f"{len(opened)} open ({sum(float(r.get('pnl') or 0) for r in opened):+,.0f})"]
    for r in closed + opened:
        L.append(f"  {r.get('structure')} x{r.get('contracts')} {r.get('opened')}->{r.get('closed') or 'open'} pnl {r.get('pnl')}")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Claude's news desk (paper, discretionary)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("watch"); sub.add_parser("snapshot"); sub.add_parser("guard"); sub.add_parser("summary")
    o = sub.add_parser("open")
    o.add_argument("--symbol", required=True); o.add_argument("--side", choices=["buy", "sell"], default="buy")
    o.add_argument("--qty", type=int); o.add_argument("--stop", type=float); o.add_argument("--target", type=float)
    o.add_argument("--leg", action="append"); o.add_argument("--lots", type=int, default=1)
    o.add_argument("--stop-under", type=float, dest="stop_under"); o.add_argument("--stop-over", type=float, dest="stop_over")
    o.add_argument("--until"); o.add_argument("--event")
    o.add_argument("--thesis", required=True); o.add_argument("--exit", required=True, dest="exit_plan"); o.add_argument("--wrong", required=True)
    c = sub.add_parser("close"); c.add_argument("--tg"); c.add_argument("--all", action="store_true"); c.add_argument("--reason", required=True)
    n = sub.add_parser("note"); n.add_argument("--text", required=True)
    a = ap.parse_args(argv)
    apply_limits()
    if a.cmd == "watch":
        return cmd_watch()
    if a.cmd == "snapshot":
        print(cmd_snapshot()); return 0
    if a.cmd == "guard":
        print("\n".join(cmd_guard()) or "guard: nothing to do"); return 0
    if a.cmd == "summary":
        print(cmd_summary()); return 0
    if a.cmd == "open":
        return cmd_open(a)
    if a.cmd == "close":
        tgs = [str(r.get("trade_group_id")) for r in my_positions("open")] if a.all else [a.tg]
        for tg in [x for x in tgs if x]:
            print(_close(tg, a.reason))
        return 0
    if a.cmd == "note":
        t = now_et(); journal(t.date(), f"## {hm(t)} NOTE\n{a.text}"); print("noted"); return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
