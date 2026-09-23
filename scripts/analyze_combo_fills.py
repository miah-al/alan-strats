"""Reconstruct whole verticals from the streamed leg prints, and price each one against the quote that
stood behind it -- the number the backtest's ``half_spread_pts`` is supposed to represent.

    python -m scripts.analyze_combo_fills --day 2026-09-23 --width 50

A multi-leg execution reaches the tape as its individual legs, each flagged ``spread_leg`` and each
stamped with the same timestamp. Two such legs at one instant, same size, different strikes, are one
vertical. Its net price is the difference of the two leg prices, and the derived quote it traded inside
is the usual client-side construction:

    derived bid = bid(low strike) - ask(high strike)      the worst the package could be sold at
    derived ask = ask(low strike) - bid(high strike)      the worst it could be bought at

So the whole question -- where does a spread actually fill inside a quote that is only ever derived --
becomes a single measurable quantity per execution: the net price's position between those two bounds,
and its distance from their midpoint in points.

That distance IS the per-trade cost the backtest models. If real verticals transact at the derived mid,
the cost is zero against mid and the backtest's assumption is conservative rather than optimistic.
"""
from __future__ import annotations

import argparse
import csv
import statistics as st
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(paths: list[Path]) -> list[dict]:
    """Multi-leg prints, deduplicated. About 1% of trades arrive twice -- the same execution reported
    under two exchange codes -- which would otherwise make a two-leg group look like a four-leg one and
    get it thrown away by the pairing below."""
    rows, seen = [], set()
    for path in paths:
        for r in csv.DictReader(path.open(encoding="utf-8")):
            if r.get("spread_leg") != "True" or not r.get("strike"):
                continue
            key = (r["ts"], r["symbol"], r["price"], r["size"])
            if key in seen:
                continue
            seen.add(key)
            try:
                rows.append({"ts": r["ts"], "strike": float(r["strike"]), "price": float(r["price"]),
                             "size": int(float(r["size"] or 0)), "bid": float(r["bid"]), "ask": float(r["ask"]),
                             "ndx": float(r["ndx"]) if r.get("ndx") else None})
            except (TypeError, ValueError):
                continue
    return rows


def pair_up(rows: list[dict]) -> list[dict]:
    """Legs that printed at the same instant, same size, two strikes: one vertical."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        groups[r["ts"]].append(r)
    out = []
    for ts, legs in groups.items():
        by_size: dict[int, list[dict]] = defaultdict(list)
        for lg in legs:
            by_size[lg["size"]].append(lg)
        for size, same in by_size.items():
            strikes = {lg["strike"] for lg in same}
            if len(same) != 2 or len(strikes) != 2:
                continue                       # butterflies, condors, ratios: not a two-leg vertical
            lo, hi = sorted(same, key=lambda x: x["strike"])
            dbid = lo["bid"] - hi["ask"]
            dask = lo["ask"] - hi["bid"]
            if dask <= dbid:
                continue
            net = lo["price"] - hi["price"]
            mid = (dbid + dask) / 2
            spot = lo.get("ndx") or hi.get("ndx")
            out.append({
                "ts": ts, "k_low": lo["strike"], "k_high": hi["strike"],
                "strike_width": hi["strike"] - lo["strike"], "size": size,
                "ndx": spot,
                # how far the LONG leg sat in the money: the strategy's own leg is ~50 pts ITM
                "itm": None if spot is None else spot - lo["strike"],
                "net": net, "derived_bid": dbid, "derived_ask": dask, "derived_mid": mid,
                "quote_width": dask - dbid,
                "pos": (net - dbid) / (dask - dbid),
                "vs_mid": net - mid,
            })
    return sorted(out, key=lambda x: x["ts"])


def summarize(pairs: list[dict], label: str) -> None:
    if not pairs:
        print(f"  {label}: none")
        return
    pos = sorted(p["pos"] for p in pairs)
    vs = sorted(abs(p["vs_mid"]) for p in pairs)
    qw = sorted(p["quote_width"] for p in pairs)
    lots = sum(p["size"] for p in pairs)
    at_mid = sum(1 for p in pairs if 0.45 <= p["pos"] <= 0.55) / len(pairs)
    at_edge = sum(1 for p in pairs if p["pos"] <= 0.02 or p["pos"] >= 0.98) / len(pairs)
    print(f"  {label}: {len(pairs)} verticals / {lots} contracts")
    print(f"    derived quote width   median {st.median(qw):6.2f} pts   (the number a platform would show you)")
    print(f"    filled at             median {st.median(pos):6.0%} of the way bid->ask; at mid {at_mid:.0%}, at an edge {at_edge:.0%}")
    print(f"    distance from mid     median {st.median(vs):6.2f} pts   (this is what half_spread_pts should be)")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default=None)
    ap.add_argument("--symbol", default="NDX")
    ap.add_argument("--width", type=float, default=50.0, help="the strategy's own strike width, reported separately")
    ap.add_argument("--logs", default=None)
    ap.add_argument("--show", type=int, default=12, help="how many reconstructed verticals to print")
    args = ap.parse_args(argv)

    day = args.day or date.today().isoformat()
    logs = Path(args.logs) if args.logs else ROOT.parent / "alan-trader-logs"
    paths = sorted(logs.glob(f"prints_{args.symbol}_{day}*.csv"))     # the day's parts, in order
    if not paths:
        print(f"no streamed prints for {day} in {logs}"); return 1

    rows = load(paths)
    pairs = pair_up(rows)
    print(f"{day}: {len(rows)} multi-leg leg-prints -> {len(pairs)} two-leg verticals reconstructed\n")
    if not pairs:
        print("no clean two-leg verticals yet; multi-leg prints so far are wider structures")
        return 0

    if args.show:
        print(f"{'time':<13}{'structure':>16}{'wide':>7}{'size':>6}{'net':>9}{'derived bid/ask':>20}{'mid':>9}{'pos':>7}{'vs mid':>9}")
        for p in pairs[-args.show:]:
            print(f"{p['ts'][11:23]:<13}{int(p['k_low']):>8}/{int(p['k_high']):<7}{p['strike_width']:>6.0f}{p['size']:>6}"
                  f"{p['net']:>9.2f}{p['derived_bid']:>10.2f}/{p['derived_ask']:<9.2f}{p['derived_mid']:>8.2f}"
                  f"{p['pos']:>7.0%}{p['vs_mid']:>+9.2f}")
        print()

    print("all reconstructed verticals")
    summarize(pairs, "every strike width")
    wide = [p for p in pairs if abs(p["strike_width"] - args.width) < 1e-6]
    print(f"\nthe strategy's own structure ({args.width:.0f} wide)")
    summarize(wide, f"{args.width:.0f}-wide")
    if not wide:
        print(f"    nothing {args.width:.0f} wide traded as a two-leg vertical in this sample; the widths above stand in for it")

    # The distinction that actually matters here: the strategy buys a leg deep in the money, where the
    # quote is widest and the trade is thinnest. An out-of-the-money vertical is an easier problem.
    known = [p for p in pairs if p["itm"] is not None]
    if known:
        print("\nby how far the long leg sat in the money")
        for lo_b, hi_b, name in ((-1e9, 0, "out of the money"), (0, 25, "0-25 pts ITM"),
                                 (25, 75, "25-75 pts ITM (the strategy's own range)"), (75, 1e9, "75+ pts ITM")):
            summarize([p for p in known if lo_b <= p["itm"] < hi_b], name)

    vs = sorted(abs(p["vs_mid"]) for p in (wide or pairs))
    print(f"\nimplied cost per side against the derived mid: {st.median(vs):.2f} pts "
          f"(the backtest assumes 0.50, i.e. it charges itself more than this sample paid)"
          if st.median(vs) < 0.5 else
          f"\nimplied cost per side against the derived mid: {st.median(vs):.2f} pts "
          f"(the backtest assumes 0.50, i.e. it charges itself less than this sample paid)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
