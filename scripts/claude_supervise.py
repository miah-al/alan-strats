"""
python -m scripts.claude_supervise <command> -- Claude supervises the armed rule strategies (from 2026-09-30, the
owner's call: "You have to be the one for all the strategies and improvise. The rule-based ones can lose too much money
otherwise").

The one rule: supervision only takes risk off. The rules keep opening their trades; Claude can stop a strategy's new
entries or its adds for the day, close its positions now (a profit or a loss), or do both and end its day. Claude never
opens or adds for a strategy: risk Claude wants on goes through its own desk (scripts/claude_desk.py), scored as its own.

The controls are stored with the trader's limits (PUT /api/limits/<strategy>/sup_entries|sup_adds|sup_close, by
"claude", with the reason in the change log; paper/supervisor.py) and count only on the day they are set. The runner reads
them every poll (about 20 s) and hands them to the engine; an engine without the hooks is not supervised, and its runner
says so. The strategies' own caps (the owner's) stay as they are.

Commands:
  status [--strategy S]            every armed strategy: runner, today's P&L, open positions, the controls in force
  hold S --reason ...              no new entries today (a resting entry is cancelled)
  no-adds S --reason ...           no adds today
  allow S [--entries] [--adds] --reason ...   hand entries and/or adds back to the rules (both when neither is named)
  close S --reason ...             close S's open positions at the next poll; the rules carry on
  done S --reason ...              no entries, no adds, and close: S is finished for the day
Each change is journaled in the desk's journal (paper_state/claude_desk/journal_<day>.md) before it is sent.
"""
from __future__ import annotations

import argparse
import sys
import time

from scripts.claude_desk import api, hm, journal, now_et, rows

CONTROLS = ("sup_entries", "sup_adds", "sup_close")


def runner_strategies() -> list[str]:
    """The armed runner strategies: the Limits page's strategy scopes (the allocators have none and are not supervised)."""
    tbl = api("GET", "/limits")
    return [s["scope"] for s in tbl.get("scopes", []) if s.get("kind") == "strategy"]


def open_positions(strategy: str) -> list[dict]:
    return [r for r in rows(api("GET", "/paper/positions?status=open")) if r.get("strategy") == strategy]


def put(strategy: str, name: str, value, reason: str) -> dict:
    return api("PUT", f"/limits/{strategy}/{name}", {"value": value, "by": "claude", "reason": reason})


def check(strategy: str) -> None:
    known = runner_strategies()
    if strategy not in known:
        raise SystemExit(f"{strategy} is not an armed strategy ({', '.join(known) or 'none armed'})")


def cmd_status(only: str | None = None) -> str:
    tbl = api("GET", "/limits")
    procs = {r.get("strategy"): r for r in api("GET", "/processes").get("rows", []) if r.get("strategy")}
    out = [f"SUPERVISOR {hm(now_et())} ET"]
    for s in tbl.get("scopes", []):
        if s.get("kind") != "strategy" or (only and s["scope"] != only):
            continue
        name = s["scope"]
        lim = {l["name"]: l for l in s.get("limits", [])}
        ent, add, cl = (lim.get(n, {}) for n in CONTROLS)
        ctl = (f"entries {'on' if float(ent.get('value', 1)) >= 0.5 else 'OFF'}, adds {'on' if float(add.get('value', 1)) >= 0.5 else 'OFF'}"
               + ("" if cl.get("is_default", True) else f", close requested {str(cl.get('updated_at'))[11:16]} UTC"))
        p = procs.get(name, {})
        pos = open_positions(name)
        pos_s = "; ".join(f"{r.get('description') or r.get('symbol') or r.get('structure') or '?'} x{r.get('contracts') or r.get('qty') or '?'} "
                          f"{float(r.get('pnl') or 0):+,.0f}" for r in pos) or "flat"
        day = s.get("day_pnl")
        out.append(f"  {name:<20} runner {p.get('status', '?')} ({p.get('reason', '')}) | day {f'{day:+,.0f}' if day is not None else 'n/a'}"
                   f" | {pos_s} | {ctl}")
    return "\n".join(out)


def act(strategy: str, what: str, reason: str) -> int:
    check(strategy)
    t = now_et()
    sets = {"hold": [("sup_entries", 0)], "no-adds": [("sup_adds", 0)], "close": [("sup_close", int(time.time()))],
            "done": [("sup_entries", 0), ("sup_adds", 0), ("sup_close", int(time.time()))]}[what]
    pos = open_positions(strategy)
    held = "; ".join(f"{r.get('description') or r.get('symbol') or '?'} {float(r.get('pnl') or 0):+,.0f}" for r in pos) or "flat"
    journal(t.date(), f"## {hm(t)} SUPERVISOR {strategy}: {what.upper()}\nHolding: {held}\nWhy: {reason}")
    for name, value in sets:
        put(strategy, name, value, reason)
    print(f"{strategy}: {what} sent at {hm(t)} ({reason})")
    if any(n == "sup_close" for n, _ in sets) and pos:
        for _ in range(24):                                   # the runner polls about every 20 s
            time.sleep(5)
            left = open_positions(strategy)
            if not left:
                print(f"{strategy}: flat")
                return 0
        print(f"{strategy}: still {len(left)} open after 2 minutes: check its runner (status)")
        return 1
    return 0


def allow(strategy: str, entries: bool, adds: bool, reason: str) -> int:
    check(strategy)
    if not entries and not adds:
        entries = adds = True
    t = now_et()
    what = " and ".join(x for x, on in (("entries", entries), ("adds", adds)) if on)
    journal(t.date(), f"## {hm(t)} SUPERVISOR {strategy}: ALLOW {what}\nWhy: {reason}")
    if entries:
        put(strategy, "sup_entries", 1, reason)
    if adds:
        put(strategy, "sup_adds", 1, reason)
    print(f"{strategy}: {what} back with the rules at {hm(t)} ({reason})")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Claude supervises the armed rule strategies (paper; risk off only)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    st = sub.add_parser("status"); st.add_argument("--strategy")
    for c in ("hold", "no-adds", "close", "done"):
        x = sub.add_parser(c); x.add_argument("strategy"); x.add_argument("--reason", required=True)
    al = sub.add_parser("allow"); al.add_argument("strategy"); al.add_argument("--entries", action="store_true")
    al.add_argument("--adds", action="store_true"); al.add_argument("--reason", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "status":
        print(cmd_status(a.strategy)); return 0
    if a.cmd == "allow":
        return allow(a.strategy, a.entries, a.adds, a.reason)
    return act(a.strategy, a.cmd, a.reason)


if __name__ == "__main__":
    sys.exit(main())
