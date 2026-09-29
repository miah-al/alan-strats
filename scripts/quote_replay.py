"""
python -m scripts.quote_replay --strategy <slug>[,<slug>...] --day YYYY-MM-DD|all [--param KEY=VALUE ...] [--quiet]

Replays strategies on the NDXP quotes the service recorded (paper.providers.QuoteReplayProvider), under the
parameters a LIVE session runs with (each strategy's declared live_params, then --param): the question it answers
is what the live runner would have done that day, priced off the same bid/ask it sees. A print-priced replay
(scripts.paper_runner --replay) answers a different one and fills targets the live quotes never reach.

``--day all`` replays every recorded day. With several strategies or days it ends with a table: day P&L per
strategy, and each strategy's total, trades and winning days so far.

A dry run: no ledger, no broker call. The event log and state go to paper_state/quote_replay/<slug>/, never the
live paper log.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path


def _parse(kvs: list[str]) -> dict:
    params: dict = {}
    for kv in kvs:
        k, v = kv.split("=", 1)
        try:
            v = float(v) if v.replace(".", "", 1).replace("-", "", 1).isdigit() else ({"true": True, "false": False}.get(v.lower(), v))
        except ValueError:
            pass
        params[k] = v
    return params


def recorded_days(quotes_dir: Path, root: str = "NDXP") -> list[date]:
    return sorted(date.fromisoformat(p.name[:10]) for p in (quotes_dir / root).glob("????-??-??.csv.gz"))


def main(argv=None) -> int:
    from api.bootstrap import BootstrapError, bootstrap
    try:
        bootstrap()
    except BootstrapError as exc:
        print(f"quote replay: {exc}", file=sys.stderr)
        return 2
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("--strategy", required=True, help="one slug or a comma-separated list")
    ap.add_argument("--day", required=True, help="YYYY-MM-DD or all")
    ap.add_argument("--param", action="append", default=[], metavar="KEY=VALUE")
    ap.add_argument("--quotes-dir", default=None, help="default: paper_state/quotes of this checkout")
    ap.add_argument("--quiet", action="store_true", help="only the summary table")
    a = ap.parse_args(argv)

    from db.client import get_engine
    from strategy_api import registry as R
    from paper.providers import QUOTES_DIR
    from api.services.quote_replay import replay_day
    qdir = Path(a.quotes_dir or QUOTES_DIR)
    slugs = [s.strip() for s in a.strategy.split(",") if s.strip()]
    days = recorded_days(qdir) if a.day == "all" else [date.fromisoformat(a.day)]
    if not days:
        print(f"no recorded quotes under {qdir}")
        return 1
    overrides = _parse(a.param)
    eng = get_engine()
    table: dict = {}
    for slug in slugs:
        inst = R.get_strategy(slug).live_instrument() or {}
        if not inst:
            print(f"{slug} does not expose a live session (live_instrument is empty)")
            continue
        run_params = {**dict(inst.get("live_params") or {}), **overrides}
        for day in days:
            res, prov = replay_day(slug, day, run_params, inst, qdir=qdir, eng=eng)       # api/services/quote_replay.py
            table[(slug, day)] = res
            if a.quiet:
                continue
            print(f"\n{slug} {day} on recorded quotes ({prov.describe()})")
            print("parameters:", ", ".join(f"{k}={v}" for k, v in sorted(run_params.items())) or "the strategy's defaults")
            print(f"{'BLOCKED: ' + res.reason if res.blocked else 'open'}; {res.bars} bars; {len(res.trades)} trades; day P&L {res.day_pnl:+,.0f}")
            for f in res.fills:
                print(f"    {f.get('m', 0) // 60:02d}:{f.get('m', 0) % 60:02d} {f.get('kind'):<6} {f.get('direction', '')} "
                      f"{f.get('kl', 0):.0f}/{f.get('kh', 0):.0f} x{f.get('units', f.get('lots', 1))} @ {f.get('px', 0):.2f} ({f.get('reason', '')})")
            print(f"log: {res.log_path}")
    if len(table) > 1 or a.quiet:
        print("\n| strategy | " + " | ".join(str(d) for d in days) + " | total | trades | winning days |")
        print("|---|" + "---|" * (len(days) + 3))
        for slug in slugs:
            rs = [table.get((slug, d)) for d in days]
            cells = [("blocked" if r.blocked else f"{r.day_pnl:+,.0f}") if r is not None else "n/a" for r in rs]
            done = [r for r in rs if r is not None and not r.blocked]
            total = sum(r.day_pnl for r in done)
            wins = sum(1 for r in done if r.day_pnl > 0)
            print(f"| {slug} | " + " | ".join(cells) + f" | {total:+,.0f} | {sum(len(r.trades) for r in done)} | {wins} of {len(done)} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
