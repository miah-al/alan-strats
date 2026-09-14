"""Automated paper trading for one strategy.

    python -m scripts.paper_runner --strategy ndx_0dte_tasty                      # live: tastytrade quotes, today, ledger on
    python -m scripts.paper_runner --strategy ndx_0dte_tasty --replay 2026-08-26  # a stored session, fast, ledger off
    python -m scripts.paper_runner --strategy ndx_0dte_tasty --replay 2026-08-26 --ledger   # ... and write it to the ledger
    python -m scripts.paper_runner --strategy ndx_0dte_tasty --check              # credentials, chain, one quote; no trading

Live needs TT_SECRET and TT_REFRESH (tastytrade OAuth) in .env. Fills, quotes and cancels go to
<strategy folder>/paper_log/YYYY-MM-DD.csv; the ledger to portfolio.Transaction (Paper Trading page);
state to paper_state/ so a restart resumes the session.
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT.parent), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--strategy", required=True)
    ap.add_argument("--replay", metavar="YYYY-MM-DD", help="run a stored session instead of live")
    ap.add_argument("--half-spread", type=float, default=0.5, help="replay: bid/ask = print -/+ this")
    ap.add_argument("--ledger", action="store_true", help="replay: also write the portfolio ledger (live always does)")
    ap.add_argument("--no-ledger", action="store_true", help="live: do not write the ledger")
    ap.add_argument("--poll", type=int, default=15, help="live: seconds between quote polls")
    ap.add_argument("--test-env", action="store_true", help="live: tastytrade certification environment")
    ap.add_argument("--check", action="store_true", help="live: verify credentials, today's chain and one quote, then exit")
    ap.add_argument("--resume", action="store_true", help="replay: resume from saved state if present")
    ap.add_argument("--param", action="append", default=[], metavar="KEY=VALUE", help="override a strategy parameter")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    log_dir = ROOT / "logs" / "paper"; log_dir.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(log_dir / f"{args.strategy}_{date.today().isoformat()}.log", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")); logging.getLogger().addHandler(fh)

    from db.client import get_engine
    from paper.runner import PaperSession
    from paper.providers import ReplayProvider, TastytradeProvider
    from strategy_api import registry as R

    params = {}
    for kv in args.param:
        k, v = kv.split("=", 1)
        try:
            v = float(v) if v.replace(".", "", 1).replace("-", "", 1).isdigit() else v
        except Exception:
            pass
        params[k] = v
    strategy = R.get_strategy(args.strategy)
    inst = strategy.live_instrument() or {}
    if not inst:
        print(f"{args.strategy} does not expose a live session (live_instrument is empty)"); return 2
    underlying, root = inst.get("underlying", "NDX"), inst.get("root", "NDXP")
    engine = get_engine()

    if args.replay:
        day = date.fromisoformat(args.replay)
        prov = ReplayProvider(engine, underlying, day, half_spread=args.half_spread, root=root)
        ps = PaperSession(args.strategy, prov, engine, write_ledger=args.ledger, params=params)
        res = ps.run_replay(day, resume=args.resume)
    else:
        prov = TastytradeProvider(underlying, root, is_test=args.test_env, poll_seconds=args.poll)
        if args.check:
            day = date.today()
            n = prov.load_chain(day)
            print(f"tastytrade session ok; {n} {root} contracts expiring {day}")
            syms = [o.symbol for o in list(prov._chain.values())[:2]]
            q = prov.fetch(syms)
            for s, lq in q.items():
                print(f"  {s}: bid {lq.bid} ask {lq.ask} last {lq.last} last_time {lq.last_time} updated {lq.updated}")
            return 0
        ps = PaperSession(args.strategy, prov, engine, write_ledger=not args.no_ledger, params=params)
        res = ps.run_live(poll_seconds=args.poll)

    print(f"\n{res.slug} {res.day} [{res.provider}] {'BLOCKED: ' + res.reason if res.blocked else 'traded'}")
    print(f"bars {res.bars}; fills {len(res.fills)} (ledger rows written for {res.n_fills_written}); trades {len(res.trades)}; day P&L {res.day_pnl:+,.0f}")
    for t in res.trades:
        print(f"  {t['entry_time']}-{t['exit_time']} {t['direction']:4s} {t['k_low']:.0f}/{t['k_high']:.0f} x{t['units']} "
              f"{t['entry_px']:.2f} -> {t['exit_px']:.2f} {t['exit_reason']:7s} {t['pnl']:+,.0f}")
    print(f"log: {res.log_path}\nstate: {res.state_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
