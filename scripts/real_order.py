"""
scripts/real_order.py — the owner's REAL order, on the owner's yes. The only caller of api/services/real_orders.py.

    python scripts/real_order.py check-key [--key trade|platform]   # the login, the account, ONE test order (never sent)
    python scripts/real_order.py place --ticket T.json               # a tastytrade test order of the ticket (never sent)
    python scripts/real_order.py place --ticket T.json --live        # ONLY after the owner's yes: the test order, then the
                                                                     #   real one, watched; cancelled at the cut-off if unfilled
    python scripts/real_order.py status [--day D] [--broker]         # the day's ledger (+ tastytrade's live orders)
    python scripts/real_order.py cancel [--day D]                    # cancel the day's live order (only the one sent here)
    python scripts/real_order.py settle --close 7549.83 [--day D]    # book the day's result at the cash settlement

What may go is decided by <paper_state>/real_orders/permission.json (see api/services/real_orders.py). Nothing here
prints a secret or the full account number. Exit codes: 0 done, 3 refused (nothing sent), 1 error.
"""
from __future__ import annotations

import argparse
import asyncio
import dataclasses
import datetime as dt
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.bootstrap import bootstrap  # noqa: E402


def _now() -> dt.datetime:
    from paper.providers import now_et
    return now_et()


def _state_dir() -> Path:
    from api.config import service_state_dir
    return service_state_dir()


def _budget():
    from api.config import external_state_dirs, service_state_dir
    from api.marketdata.providers.tastytrade import ServiceBrokerBudget
    return ServiceBrokerBudget(service_state_dir(), external_state_dirs(), min_interval_s=0.5, per_minute=60)


def _next_session(now: dt.datetime) -> dt.date:
    d = now.date()
    if now.weekday() < 5 and now.time() < dt.time(16, 0):
        return d
    d += dt.timedelta(days=1)
    while d.weekday() >= 5:
        d += dt.timedelta(days=1)
    return d


def _money(x) -> str:
    if x is None:
        return "?"
    x = float(x)
    return f"-${abs(x):,.2f}" if x < 0 else f"${x:,.2f}"


def _order_line(t) -> str:
    return (f"SELL TO OPEN {t.lots} {t.root} {t.day:%m/%d} {t.short:g} CALL + BUY TO OPEN {t.lots} {t.long:g} CALL, "
            f"LIMIT {t.limit:.2f} CREDIT, DAY")


def _verdict(s: dict) -> str:
    bits = [f"buying power change {_money(s.get('bp_change'))}", f"fees {_money(s.get('fees'))}"]
    if s.get("warnings"):
        bits.append("warnings: " + "; ".join(s["warnings"]))
    if s.get("errors"):
        bits.append("ERRORS: " + "; ".join(s["errors"]))
    return ", ".join(bits)


async def cmd_check_key(a) -> int:
    from api.services import real_orders as R
    sd = _state_dir()
    present = R.keys_present()
    print("logins set up: " + ", ".join(f"{k} {'yes' if v else 'no'}" for k, v in present.items()))
    perm = None
    try:
        perm = R.load_permission(sd)
        print(f"permission: mode {perm.mode}, login '{perm.key}', account ****{perm.account[-4:]}, "
              f"allowed: {', '.join(r.strategy for r in perm.rules)}")
    except R.Refused as exc:
        print(f"permission: {exc}")
    key = a.key or (perm.key if perm else "trade")
    last4 = (a.account or (perm.account if perm else "")).lstrip("*")
    if not last4:
        raise R.Refused("no account: pass --account or write the permission file")
    creds = R.credentials(key)
    day = _next_session(_now())
    sample = R.Ticket(strategy="check-key", day=day, underlying="SPX", root="SPXW", right="C", short=float(a.short),
                      long=float(a.short) + 10, lots=1, limit=0.20, spot=0.0)
    async with R.Broker(creds, budget=_budget()) as b:
        acct = await b.account(last4)
        print(f"login '{key}': signed in; account {R.mask(b.account_number)} found")
        try:
            resp = await b.dry_run(acct, R.build_order(sample))
        except Exception as exc:  # noqa: BLE001
            print(f"TEST ORDER refused by tastytrade: {b.scrub(f'{type(exc).__name__}: {exc}')}")
            return 3
    s = R.summarize(resp)
    print(f"TEST ORDER (checked by tastytrade, never sent): {_order_line(sample)}")
    print(f"  tastytrade: {'ACCEPTED' if not s['errors'] else 'REJECTED'}; {_verdict(s)}")
    return 0 if not s["errors"] else 3


async def cmd_place(a) -> int:
    from api.services import real_orders as R
    sd = _state_dir()
    perm = R.load_permission(sd)
    t = R.parse_ticket(json.loads(Path(a.ticket).read_text(encoding="utf-8")))
    if a.limit is not None:
        t = dataclasses.replace(t, limit=round(float(a.limit), 2))
    rule = R.check(t, perm, _now(), a.live, sd)
    creds = R.credentials(perm.key)
    print(("LIVE ORDER" if a.live else "TEST ORDER (checked by tastytrade, never sent)") + f": {_order_line(t)}")
    async with R.Broker(creds, budget=_budget()) as b:
        out = await R.place(t, perm, rule, b, sd, live=a.live, now=_now, say=print)
    print(f"  account {out['account']}; tastytrade test order: {_verdict(out['dry_run'])}")
    if a.live:
        lv = out["live"]
        line = f"  LIVE order {lv['order_id']}: {lv['status']}"
        if lv.get("fill_credit") is not None:
            line += f" at {lv['fill_credit']:.2f} credit"
        if lv.get("warning"):
            line += f" - {lv['warning']}"
        print(line)
    return 0


async def cmd_status(a) -> int:
    from api.services import real_orders as R
    sd = _state_dir()
    day = dt.date.fromisoformat(a.day) if a.day else _now().date()
    rows = R.read_ledger(sd, day)
    print(f"{day}: {len(rows)} ledger event(s); live slots used {R.live_slots_used(sd, day)}")
    for r in rows:
        extra = {k: v for k, v in r.items() if k not in ("at", "event", "ticket")}
        print(f"  {r['at'][11:]} {r['event']:<17} {json.dumps(extra, default=str)[:200]}")
    try:
        perm = R.load_permission(sd)
        print(f"permission: mode {perm.mode}; real result since {perm.since}: "
              f"{_money(R.realized_since(sd, perm.since))} (pause at {_money(perm.loss_pause)})")
    except R.Refused as exc:
        print(f"permission: {exc}")
        perm = None
    if a.broker and perm is not None:
        async with R.Broker(R.credentials(perm.key), budget=_budget()) as b:
            acct = await b.account(perm.account)
            live = await b.live_orders(acct)
            print(f"tastytrade, account {R.mask(b.account_number)}: {len(live)} order(s) today")
            for o in live:
                legs = " / ".join(f"{getattr(l.action, 'value', l.action)} {l.quantity} {l.symbol}" for l in o.legs)
                print(f"  {o.id} {getattr(o.status, 'value', o.status)} {legs} price {o.price}")
    return 0


async def cmd_cancel(a) -> int:
    from api.services import real_orders as R
    sd = _state_dir()
    day = dt.date.fromisoformat(a.day) if a.day else _now().date()
    oid = R.day_order(sd, day).get("order_id")
    if not oid:
        raise R.Refused(f"no live order was sent here on {day}")
    perm = R.load_permission(sd)
    async with R.Broker(R.credentials(perm.key), budget=_budget()) as b:
        acct = await b.account(perm.account)
        await b.cancel(acct, int(oid))
        R.record(sd, day, "manual_cancel_sent", _now(), order_id=oid)
        po = await b.get(acct, int(oid))
    print(f"order {oid}: cancel sent; status now {getattr(po.status, 'value', po.status)}")
    return 0


async def cmd_settle(a) -> int:
    from api.services import real_orders as R
    sd = _state_dir()
    day = dt.date.fromisoformat(a.day) if a.day else _now().date()
    row = R.settle(sd, day, float(a.close))
    print(f"{day}: {row['strategy']} {row['short']:g}/{row['long']:g} x{row['lots']} credit {row['credit']:.2f}, "
          f"settled {row['settle_value']:.2f} (close {row['spx_close']:,.2f}), fees {_money(row['fees'])}: "
          f"P&L {_money(row['pnl'])}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    k = sub.add_parser("check-key")
    k.add_argument("--key", choices=["trade", "platform"])
    k.add_argument("--account", help="last 4 characters (default: the permission file's)")
    k.add_argument("--short", type=float, default=8000.0, help="the test order's short call strike (far out of the money)")
    p = sub.add_parser("place")
    p.add_argument("--ticket", required=True)
    p.add_argument("--live", action="store_true", help="ONLY after the owner's yes")
    p.add_argument("--limit", type=float, help="a different limit credit (still checked)")
    s = sub.add_parser("status")
    s.add_argument("--day")
    s.add_argument("--broker", action="store_true", help="also list tastytrade's orders for today")
    c = sub.add_parser("cancel")
    c.add_argument("--day")
    t = sub.add_parser("settle")
    t.add_argument("--close", required=True, type=float)
    t.add_argument("--day")
    a = ap.parse_args(argv)

    sys.stdout.reconfigure(encoding="utf-8")
    bootstrap()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    for name in ("httpx", "httpx2", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
    from api.services.real_orders import Refused
    fn = {"check-key": cmd_check_key, "place": cmd_place, "status": cmd_status, "cancel": cmd_cancel,
          "settle": cmd_settle}[a.cmd]
    try:
        return asyncio.run(fn(a))
    except Refused as exc:
        print(f"REFUSED: {exc}")
        return 3
    except Exception as exc:  # noqa: BLE001 - one line, no traceback (it could carry request details)
        print(f"ERROR: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
