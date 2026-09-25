"""Sample the live quoted spread on the vertical the strategy would trade, through the session, so the
paper assumption (half_spread_pts) can be replaced by a measured number instead of a guess.

Read-only: the underlying plus a handful of option legs per sample, through the provider's own request
budget. Never places an order.

    python -m scripts.sample_quoted_spread --strategy ndx_0dte_tasty --until 14:05 --every 60

Two questions, one sample.

1. How wide is the quote on the vertical the strategy would pick right now? That is the worst case: the
   cost of paying the ask and selling the bid. Straightforward, since the quote is always two-sided.

2. Where do trades actually print inside that quote? This is the one that matters, because the strategy
   rests orders rather than crossing. It cannot be read off a single sample: the broker's snapshot carries
   a `last` price but no trade time, so a leg that has not traded for an hour still reports a `last` --
   often from when the contract was far from the money, which is why a leg quoted 80/86 can show a last
   of 201. Subtracting two such stale prints, one per leg, produces nonsense.

   So freshness is established by volume instead. Every symbol seen is remembered with its volume; when
   the same symbol comes back with MORE volume, the trades in between happened during that interval, and
   the newer `last` is one of them. Its position in that same sample's bid/ask is then a real observation:
   0 = someone sold the bid, 1 = someone paid the ask, 0.5 = the mid. The previous sample's legs are
   re-requested alongside the current ones (same request, no extra cost) so the chain is unbroken even
   as the underlying drifts through strikes.

Writes a row per sample to alan-trader-logs/quoted_spread_<symbol>_<date>.csv, every fill observation to
fills_<symbol>_<date>.csv, and prints both as they land.
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from datetime import date, datetime, time as dtime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
# alan_trader is this checkout by file path, whatever its folder is called; the parent stays off sys.path
# (beside the live checkout it would expose that copy) — api/bootstrap.py.
from api.bootstrap import register_platform_package  # noqa: E402

register_platform_package()

SPREAD_COLS = ["ts", "ndx", "k_low", "k_high",
               "long_sym", "long_bid", "long_ask", "long_last", "long_volume", "long_bid_size", "long_ask_size",
               "short_sym", "short_bid", "short_ask", "short_last", "short_volume", "short_bid_size", "short_ask_size",
               "v_bid", "v_ask", "spread", "mid", "leg_age_max"]
FILL_COLS = ["ts", "symbol", "leg", "bid", "ask", "last", "pos", "pos_prev", "drift", "clean",
             "contracts", "interval_s"]


def _pos(bid, ask, last):
    """Where a print sits in its own quote: 0 = the bid, 1 = the ask. None when the quote is unusable."""
    if bid is None or ask is None or last is None or ask <= bid:
        return None
    return (float(last) - float(bid)) / (float(ask) - float(bid))


def _describe(pos: float) -> str:
    if pos <= 0.05:
        return "sold the bid"
    if pos >= 0.95:
        return "paid the ask"
    if 0.4 <= pos <= 0.6:
        return "at the mid"
    return "inside the quote"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", required=True, help="the strategy whose live instrument to watch")
    ap.add_argument("--until", default="14:05", help="stop after this ET time (HH:MM)")
    ap.add_argument("--every", type=int, default=60, help="seconds between samples")
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args(argv)

    from paper.providers import TastytradeProvider, vertical_quote, now_et
    from strategy_api import registry as R

    strategy = R.get_strategy(args.strategy)
    inst = strategy.live_instrument() or {}
    underlying = str(inst.get("underlying") or "NDX"); root = str(inst.get("root") or "NDXP")
    width = float(inst.get("width") or 50.0)
    params = getattr(strategy, "params", None)
    itm = float(getattr(params, "itm_offset", 24.0))
    half_assumed = float(getattr(params, "half_spread_pts", 0.5))

    prov = TastytradeProvider(underlying, root)
    day = date.today()
    n = prov.load_chain(day)
    print(f"{underlying} {day}: {n} {root} contracts; sampling the {width:.0f}-wide vertical struck {itm:.0f} pts in the money "
          f"every {args.every}s until {args.until} ET (backtest assumes a {2 * half_assumed:.1f} pt quoted spread)")

    out_dir = Path(args.out_dir) if args.out_dir else ROOT.parent / "alan-trader-logs"
    out_dir.mkdir(parents=True, exist_ok=True)
    spread_path = out_dir / f"quoted_spread_{underlying}_{day.isoformat()}.csv"
    fill_path = out_dir / f"fills_{underlying}_{day.isoformat()}.csv"
    stop_h, stop_m = (int(x) for x in args.until.split(":"))

    spreads: list[float] = []
    fills: list[tuple[float, int]] = []          # (position in the quote, contracts that traded)
    seen: dict[str, tuple[float, float, float, float, datetime]] = {}   # symbol -> volume, bid, ask, last, when
    carry: list[str] = []                        # last sample's legs, re-requested so the volume chain holds

    sf = spread_path.open("a", newline="", encoding="utf-8")
    ff = fill_path.open("a", newline="", encoding="utf-8")
    try:
        sw = csv.DictWriter(sf, fieldnames=SPREAD_COLS)
        fw = csv.DictWriter(ff, fieldnames=FILL_COLS)
        if sf.tell() == 0:
            sw.writeheader()
        if ff.tell() == 0:
            fw.writeheader()

        while True:
            now = now_et()
            if now.time() >= dtime(stop_h, stop_m):
                break
            try:
                idx = prov.fetch([])
                spot_q = idx.get(underlying)
                spot = float(spot_q.last) if spot_q is not None and spot_q.last is not None else None
                if spot is None:
                    print(f"{now:%H:%M:%S}  no underlying price"); time.sleep(args.every); continue
                ls, ss, kl, kh = prov.near_the_money_vertical(spot, width, itm)
                want = [s for s in (ls, ss) if s]
                ask_for = want + [s for s in carry if s not in want]      # one request, carries the chain
                q = prov.fetch(ask_for)
                carry = want

                # --- every symbol in the request is a chance to catch a print we can date by volume ---
                for sym in ask_for:
                    lq = q.get(sym)
                    if lq is None:
                        continue
                    raw = prov.last_row(sym)
                    vol = getattr(raw, "volume", None)
                    prev = seen.get(sym)
                    if prev is not None and vol is not None and prev[0] is not None and float(vol) > float(prev[0]):
                        # The print happened somewhere between the two samples, so score it against BOTH
                        # quotes. Where they agree the conclusion survives the quote drifting under it;
                        # where they disagree the observation says nothing and is dropped from the number.
                        pos = _pos(lq.bid, lq.ask, lq.last)
                        pos_prev = _pos(prev[1], prev[2], lq.last)
                        if pos is not None:
                            traded = int(float(vol) - float(prev[0]))
                            gap = (now - prev[4]).total_seconds()
                            leg = "long" if sym == ls else ("short" if sym == ss else "carried")
                            drift = None
                            if None not in (prev[1], prev[2]):
                                drift = (float(lq.bid) + float(lq.ask)) / 2 - (float(prev[1]) + float(prev[2])) / 2
                            width_now = float(lq.ask) - float(lq.bid)
                            clean = bool(pos_prev is not None and drift is not None
                                         and abs(drift) <= 0.25 * width_now
                                         and (pos_prev < 0.5) == (pos < 0.5))
                            fw.writerow(dict(ts=now.isoformat(timespec="seconds"), symbol=sym, leg=leg,
                                             bid=lq.bid, ask=lq.ask, last=lq.last, pos=round(pos, 3),
                                             pos_prev=(None if pos_prev is None else round(pos_prev, 3)),
                                             drift=(None if drift is None else round(drift, 2)), clean=int(clean),
                                             contracts=traded, interval_s=int(gap)))
                            if clean:
                                fills.append((pos, traded))
                            mark = "" if clean else "  [drift, not counted]"
                            print(f"{now:%H:%M:%S}  FILL {sym}  {traded:3d} lot  bid {lq.bid:6.2f} ask {lq.ask:6.2f} "
                                  f"last {lq.last:6.2f}  -> {pos:+.0%} of the way bid->ask, {_describe(pos)}{mark}")
                    if vol is not None:
                        seen[sym] = (float(vol), lq.bid, lq.ask, lq.last, now)

                v = vertical_quote(q[ls], q[ss], now) if ls in q and ss in q else None
                if v is None:
                    print(f"{now:%H:%M:%S}  NDX {spot:,.0f}  {kl:.0f}/{kh:.0f}: no two-sided quote")
                    ff.flush(); time.sleep(args.every); continue
                lq, sq = q[ls], q[ss]
                raw_l, raw_s = prov.last_row(ls), prov.last_row(ss)
                sw.writerow(dict(ts=now.isoformat(timespec="seconds"), ndx=round(spot, 2), k_low=kl, k_high=kh,
                                 long_sym=ls, long_bid=lq.bid, long_ask=lq.ask, long_last=lq.last,
                                 long_volume=getattr(raw_l, "volume", None),
                                 long_bid_size=getattr(raw_l, "bid_size", None), long_ask_size=getattr(raw_l, "ask_size", None),
                                 short_sym=ss, short_bid=sq.bid, short_ask=sq.ask, short_last=sq.last,
                                 short_volume=getattr(raw_s, "volume", None),
                                 short_bid_size=getattr(raw_s, "bid_size", None), short_ask_size=getattr(raw_s, "ask_size", None),
                                 v_bid=round(v.bid, 2), v_ask=round(v.ask, 2), spread=round(v.ask - v.bid, 2),
                                 mid=round((v.bid + v.ask) / 2, 2), leg_age_max=v.age))
                sf.flush(); ff.flush()
                spreads.append(v.ask - v.bid)
                print(f"{now:%H:%M:%S}  NDX {spot:,.0f}  {kl:.0f}/{kh:.0f}  bid {v.bid:6.2f}  ask {v.ask:6.2f}  "
                      f"spread {v.ask - v.bid:5.2f}  mid {(v.bid + v.ask) / 2:6.2f}  "
                      f"vol {getattr(raw_l, 'volume', '?')}/{getattr(raw_s, 'volume', '?')}  fills so far {len(fills)}")
            except Exception as exc:
                print(f"{now:%H:%M:%S}  fetch failed: {str(exc)[:120]}")
            time.sleep(args.every)
    finally:
        sf.close(); ff.close()

    if spreads:
        s = sorted(spreads); k = len(s)
        med = s[k // 2]
        print(f"\n{k} samples: quoted spread median {med:.2f}, range {s[0]:.2f} to {s[-1]:.2f} pts; the backtest assumes {2 * half_assumed:.1f}")
        print(f"a half spread of {med / 2:.2f} pts per side is the taker assumption these quotes imply (half_spread_pts)")
        print(f"rows: {spread_path}")
    else:
        print("no samples taken")
    if fills:
        ps = sorted(p for p, _ in fills)
        pm = ps[len(ps) // 2]
        lots = sum(c for _, c in fills)
        at_mid = sum(1 for p in ps if 0.4 <= p <= 0.6) / len(ps)
        paid = sum(1 for p in ps if p >= 0.95) / len(ps)
        hit = sum(1 for p in ps if p <= 0.05) / len(ps)
        print(f"\n{len(fills)} clean dated prints ({lots} contracts): a leg whose volume rose between two samples, "
              f"where the quote barely moved in between and both quotes agree which side of the mid the print sat on")
        print(f"  median sat {pm:.0%} of the way from bid to ask (50% = the mid, 100% = paying the ask); range {ps[0]:.0%} to {ps[-1]:.0%}")
        print(f"  at the mid {at_mid:.0%} of the time, paid the ask {paid:.0%}, sold the bid {hit:.0%}")
        print(f"  rows: {fill_path}")
    else:
        print("\nno dated prints: no leg's volume rose between two samples, so where fills land is still unmeasured")
    print(f"broker requests used: {prov.budget.calls_today}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
