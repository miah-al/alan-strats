"""Verify the platform holds a complete day of the data the paper phase depends on, and say what is
missing. Run after the post-close pull (the start script does) or by hand.

    python -m scripts.check_data_day                 # yesterday's session (or today after the close)
    python -m scripts.check_data_day --day 2026-09-16 --symbol NDX --notify

Checks: NDX 1-minute bars (390 on a full day, 211 on an early close), NDXP prints for the same-day
expiry (contracts with prints, bars), the VXN daily close, the event calendar reaching a month ahead.
Exit code 1 when something is missing, so a scheduler can see it.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
# alan_trader is this checkout by file path, whatever its folder is called; the parent stays off sys.path
# (beside the live checkout it would expose that copy) — api/bootstrap.py.
from api.bootstrap import register_platform_package  # noqa: E402

register_platform_package()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default=None)
    ap.add_argument("--symbol", default="NDX")
    ap.add_argument("--notify", action="store_true", help="WhatsApp the problems (engine.notify)")
    args = ap.parse_args(argv)
    from db.client import get_engine, get_minute_bars, get_option_minute_bars, get_price_bars, get_event_calendar
    from sqlalchemy import text
    eng = get_engine()
    day = date.fromisoformat(args.day) if args.day else date.today()
    problems, notes = [], []
    with eng.connect() as c:
        early = c.execute(text("SELECT 1 FROM mkt.EventCalendar WHERE EventDate = :d AND Kind = 'early_close'"), {"d": day}).fetchone() is not None
        holiday = c.execute(text("SELECT 1 FROM mkt.EventCalendar WHERE EventDate = :d AND Kind = 'holiday'"), {"d": day}).fetchone() is not None
    if day.weekday() >= 5 or holiday:
        print(f"{day}: not a session (weekend/holiday); nothing to check")
        return 0
    expect = 211 if early else 390
    mb = get_minute_bars(eng, args.symbol, day, day)
    if len(mb) < expect * 0.98:
        problems.append(f"{args.symbol} minute bars: {len(mb)} of {expect} expected")
    else:
        notes.append(f"{args.symbol} minute bars {len(mb)}")
    ob = get_option_minute_bars(eng, args.symbol, day, day, expiry=day)
    n_contracts = int(ob.groupby(["right", "strike"]).ngroups) if len(ob) else 0
    if n_contracts < 30:
        problems.append(f"option prints for {day}: {n_contracts} contracts, {len(ob)} bars (expected 50+ contracts)")
    else:
        notes.append(f"option prints {n_contracts} contracts / {len(ob):,} bars")
    vx = get_price_bars(eng, "VXN", day - timedelta(days=6), day)
    if vx is None or len(vx) == 0 or str(vx["date"].iloc[-1])[:10] < str(day):
        problems.append(f"VXN daily close for {day} missing (last: {str(vx['date'].iloc[-1])[:10] if vx is not None and len(vx) else 'none'})")
    else:
        notes.append(f"VXN {float(vx['close'].iloc[-1]):.2f}")
    ev = get_event_calendar(eng, day, day + timedelta(days=35))
    if ev is None or len(ev) == 0:
        problems.append("event calendar has nothing in the next 35 days: run bootstrap --events")
    else:
        notes.append(f"events ahead {len(ev)}")
    status = "OK" if not problems else "MISSING"
    print(f"{day} data check: {status}; " + "; ".join(notes))
    for p in problems:
        print("  !", p)
    if problems and args.notify:
        try:
            from engine.notify import whatsapp_configured
            from engine.signal_alerts import send_trade_alert
            if whatsapp_configured():
                send_trade_alert(f"📄 data check {day}: " + "; ".join(problems))
        except Exception as exc:
            print("  alert failed:", exc)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
