"""Automated paper trading for one strategy.

    python -m scripts.paper_runner --strategy ndx_0dte_tasty                      # live: tastytrade quotes, today, ledger on
    python -m scripts.paper_runner --strategy ndx_0dte_tasty --replay 2026-08-26  # a stored session, fast, ledger off
    python -m scripts.paper_runner --strategy ndx_0dte_tasty --replay 2026-08-26 --ledger   # ... and write it to the ledger
    python -m scripts.paper_runner --strategy ndx_0dte_tasty --check              # credentials, chain, one quote; no trading

Live needs TT_SECRET and TT_REFRESH (tastytrade OAuth) in .env. Fills, quotes and cancels go to
<strategy folder>/paper_log/YYYY-MM-DD.csv (replays: paper_log/replay/); the ledger to the portfolio
schema (Paper Trading page); state to paper_state/ so a restart resumes the session. A first live
day with credentials can be kept out of the record with --log-dir <somewhere> --no-ledger.
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
# alan_trader is this checkout by file path, whatever its folder is called; the parent stays off sys.path
# (beside the live checkout it would expose that copy) — api/bootstrap.py.
from api.bootstrap import register_platform_package  # noqa: E402

register_platform_package()


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
    ap.add_argument("--notify", action="store_true", help="live: WhatsApp the gate verdict, every fill and the day's end (engine.notify)")
    ap.add_argument("--log-dir", default=None, help="where the CSV paper log goes (default: the strategy's paper_log/; replays use paper_log/replay/)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    log_dir = ROOT / "logs" / "paper"; log_dir.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(log_dir / f"{args.strategy}_{date.today().isoformat()}.log", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")); logging.getLogger().addHandler(fh)

    from db.client import get_engine
    from paper.runner import PaperSession, now_et
    from paper.providers import ReplayProvider, TastytradeProvider
    from strategy_api import registry as R

    params = {}
    try:
        starting_cash = float(R.get_ui(args.strategy).meta.get("default_capital") or 0) or None   # seeds the paper account once
    except Exception:
        starting_cash = None
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
    # A strategy may declare how it wants to be run LIVE (live_instrument()["live_params"]) -- for
    # instance a fill model priced off the live mid, where a backtest brackets minute prints. They
    # apply to live sessions and the --check preflight only, so a replay still reproduces the backtest;
    # --param still wins. Declared by the strategy so that every way of starting a session gets them:
    # a runner started by hand without the right flags would otherwise quietly price fills another way.
    live_params = dict(inst.get("live_params") or {})
    engine = get_engine()

    log_dir = Path(args.log_dir) if args.log_dir else None
    if args.replay:
        day = date.fromisoformat(args.replay)
        try:
            prov = ReplayProvider(engine, underlying, day, half_spread=args.half_spread, root=root)
        except RuntimeError as exc:                          # a weekend, a holiday, or a day not yet pulled
            print(f"cannot replay {day}: {exc}"); return 1
        if log_dir is None:                                   # replays are dry runs: keep them out of the real paper log
            folder = PaperSession._strategy_folder(args.strategy)
            log_dir = (folder / "paper_log" / "replay") if folder else None
        ps = PaperSession(args.strategy, prov, engine, write_ledger=args.ledger, params=params, log_dir=log_dir, starting_cash=starting_cash)
        res = ps.run_replay(day, resume=args.resume)
    else:
        try:
            prov = TastytradeProvider(underlying, root, is_test=args.test_env, poll_seconds=args.poll)
        except RuntimeError as exc:
            print(f"cannot start: {exc}"); return 1
        if args.check:
            day = date.today()
            n = prov.load_chain(day)
            print(f"tastytrade session ok; {n} {root} contracts expiring {day}")
            # one quote request, on the structure the strategy trades: the underlying, then the two legs of a
            # near-the-money vertical (read-only; the runner never places an order)
            spot_q = prov.fetch([]).get(underlying)
            spot = float(spot_q.last) if spot_q is not None and spot_q.last is not None else None
            inst = strategy.live_instrument() if hasattr(strategy, "live_instrument") else {}
            width = float(inst.get("width") or 50.0); itm = float(getattr(getattr(strategy, "params", None), "itm_offset", 24.0))
            if spot is None:
                print("  no underlying price (market closed?); skipping the leg quotes")
            else:
                ls, ss, kl, kh = prov.near_the_money_vertical(spot, width, itm)
                q = prov.fetch([s for s in (ls, ss) if s])
                for s in (ls, ss):
                    lq = q.get(s) if s else None
                    print(f"  {s}: bid {lq.bid} ask {lq.ask} last {lq.last} last_time {lq.last_time} updated {lq.updated}" if lq else f"  {s}: no quote")
                from paper.providers import vertical_quote
                v = vertical_quote(q[ls], q[ss], now_et()) if ls in q and ss in q else None
                # the width printed here is DERIVED (both legs' widths added), not a market anyone quotes; spreads
                # were measured to trade at the mid, crossing in costing ~1.2 pts deep in the money (2026-09-23)
                print(f"  NDX {spot:,.2f}; bull call vertical {kl:.0f}/{kh:.0f}: " + (f"mid {v.last:.2f} (derived bid {v.bid:.2f} / ask {v.ask:.2f}: "
                      f"the legs' widths added, {v.ask - v.bid:.2f} pts, not a market), leg ages {v.legs[0][2]} / {v.legs[1][2]} min" if v else "no two-sided quote"))
            if spot is not None and hasattr(strategy, "check_structures"):
                try:
                    from paper.providers import vertical_quote
                    from strategy_api.live import is_structure
                    for kind, k_lo, k_hi, label in strategy.check_structures(spot):
                        if is_structure(kind):                               # a straddle / iron fly: every leg, one quote (read-only)
                            syms = prov.structure_symbols(kind, k_lo, k_hi)
                            q2 = prov.fetch([s for s in syms if s])
                            v2 = prov.quote_structure(kind, k_lo, k_hi, q2, now_et())
                            print(f"  {label}: {kind} {k_lo:.0f}/{k_hi:.0f} " + (f"bid {v2.bid:.2f} ask {v2.ask:.2f} mid {v2.last:.2f} "
                                  f"(long-structure terms), leg ages {'/'.join(str(l[2]) for l in v2.legs)} min" if v2 else "no two-sided quote"))
                            continue
                        ls2, ss2 = prov.leg_symbols(kind, k_lo, k_hi)
                        q2 = prov.fetch([s for s in (ls2, ss2) if s])
                        v2 = vertical_quote(q2[ls2], q2[ss2], now_et()) if ls2 in q2 and ss2 in q2 else None
                        print(f"  {label}: {kind} {k_lo:.0f}/{k_hi:.0f} " + (f"bid {v2.bid:.2f} ask {v2.ask:.2f} mid {v2.last:.2f} "
                              f"(long-vertical terms), leg ages {v2.legs[0][2]} / {v2.legs[1][2]} min" if v2 else "no two-sided quote"))
                except Exception as exc:
                    print(f"  the strategy's structures: {exc}")
            ps = PaperSession(args.strategy, prov, engine, write_ledger=False, params=params)
            problems = ps._preflight(day)
            blocked, why = ps._gate(day)
            print("preflight:", "ok" if not problems else "; ".join(problems))
            print(f"gate for {day}: {'BLOCKED ' + why if blocked else 'open'}")
            try:
                from engine.notify import whatsapp_configured
                print("WhatsApp alerts:", "configured" if whatsapp_configured() else "not configured (optional)")
            except Exception:
                pass
            if hasattr(strategy, "ai_features") and hasattr(strategy, "ai_verdict"):
                try:
                    feats = strategy.ai_features(day, [], engine)
                    ai = strategy.ai_verdict(feats)
                    print(f"AI gate: mode {ai.get('mode')}, model {ai.get('model')}, verdict {ai.get('verdict')} (p={ai.get('p')}); "
                          f"features ok: {'error' not in feats}")
                except Exception as exc:
                    print(f"AI gate hooks raised: {exc}"); problems.append("ai hooks")
            if live_params:
                print("live parameters declared by the strategy:", ", ".join(f"{k}={v}" for k, v in sorted({**live_params, **params}.items())))
            return 0 if (n and not problems) else 1
        if live_params:
            print("live parameters declared by the strategy:", ", ".join(f"{k}={v}" for k, v in sorted(live_params.items())),
                  "" if not params else f"(overridden by --param: {', '.join(sorted(set(params) & set(live_params))) or 'none'})")
        live_run_params = {**live_params, **params}
        ps = PaperSession(args.strategy, prov, engine, write_ledger=not args.no_ledger, params=live_run_params, notify=args.notify, log_dir=log_dir, starting_cash=starting_cash)
        res = ps.run_live(poll_seconds=args.poll)

    print(f"\n{res.slug} {res.day} [{res.provider}] {'BLOCKED: ' + res.reason if res.blocked else 'traded'}")
    # n_fills_written counts rows written to the CSV paper log, which happens either way; whether the
    # portfolio ledger was touched is a different question, and saying "ledger rows written" when it
    # was not sends someone looking for records to delete from a live account.
    wrote_ledger = bool(getattr(ps, "write_ledger", False))
    print(f"bars {res.bars}; fills {len(res.fills)} logged {res.n_fills_written}"
          f"{'; ledger updated' if wrote_ledger else '; ledger untouched (dry run)'}"
          f"; trades {len(res.trades)}; day P&L {res.day_pnl:+,.0f}")
    for t in res.trades:
        print(f"  {t['entry_time']}-{t['exit_time']} {t['direction']:4s} {t['k_low']:.0f}/{t['k_high']:.0f} x{t['units']} "
              f"{t['entry_px']:.2f} -> {t['exit_px']:.2f} {t['exit_reason']:7s} {t['pnl']:+,.0f}")
    print(f"log: {res.log_path}\nstate: {res.state_path}")
    halted = getattr(ps, "halted", None)
    if halted:
        print(f"HALTED: {halted}")
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
