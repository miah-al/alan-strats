"""Watch actual option trades stream in, and record where each one printed inside the quote that stood
at the moment it happened.

    python -m scripts.stream_spread_fills --strategy ndx_0dte_tasty --until 14:05

Read-only: a market data subscription. No account, no orders, nothing placed.

Why this exists. There is no quoted market for a spread: OPRA disseminates quotes for single contracts,
and the exchanges' complex order books are not in the retail feed. Any "spread bid/ask" -- the platform's
and our own -- is therefore DERIVED, bid(long) - ask(short) against ask(long) - bid(short), which simply
adds the two legs' widths together and prices crossing both legs separately as a taker. It is a real
upper bound and nothing more. A market maker quoting the package does not have to be paid both leg
spreads, so the derived width says very little about what a resting combo order would fill at.

What can be observed is the other side of the same question: the trades themselves. Each TimeAndSale
event carries

    time            the exact timestamp, so nothing here depends on a print being fresh
    bid_price       the bid AT THE INSTANT OF THE TRADE
    ask_price       the ask at that same instant, so nothing depends on the quote holding still
    spread_leg      whether this print was one leg of a MULTI-LEG order
    aggressor_side  who initiated it -- someone paying up, or someone filled passively

so a fill's position in its own quote is exact rather than inferred, and `spread_leg` isolates the
prints that came from combo executions: the population a resting spread order belongs to.

Writes every print to alan-trader-logs/prints_<symbol>_<date>.csv and reports the two distributions --
combo prints against outright prints -- as they build.
"""
from __future__ import annotations

import argparse
import csv
import statistics as st
import sys
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT.parent), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

COLS = ["ts", "symbol", "strike", "price", "size", "bid", "ask", "width", "pos",
        "spread_leg", "aggressor", "exchange", "conditions", "ndx", "moneyness"]


def _pos(bid, ask, price):
    """Where the print sat in the quote standing at that instant: 0 = the bid, 1 = the ask."""
    try:
        b, a, p = float(bid), float(ask), float(price)
    except (TypeError, ValueError):
        return None
    return None if a <= b else (p - b) / (a - b)


def _describe(p: float) -> str:
    if p <= 0.02:
        return "sold the bid"
    if p >= 0.98:
        return "paid the ask"
    if 0.45 <= p <= 0.55:
        return "AT THE MID"
    return "inside"


def _report(rows: list[dict]) -> list[str]:
    """The two distributions, combo prints against outright prints."""
    out = []
    for flag, name in ((True, "combo (multi-leg)"), (False, "outright")):
        g = [r for r in rows if r["spread_leg"] is flag and r["pos"] is not None]
        if not g:
            out.append(f"  {name:<18} no prints yet")
            continue
        ps = sorted(r["pos"] for r in g)
        lots = sum(int(r["size"] or 0) for r in g)
        mid = sum(1 for x in ps if 0.45 <= x <= 0.55) / len(ps)
        ask = sum(1 for x in ps if x >= 0.98) / len(ps)
        bid = sum(1 for x in ps if x <= 0.02) / len(ps)
        out.append(f"  {name:<18} {len(ps):4d} prints / {lots:5d} lots   median {st.median(ps):5.0%} bid->ask"
                   f"   at mid {mid:4.0%}   paid ask {ask:4.0%}   sold bid {bid:4.0%}")
    return out


async def run(prov, symbols: dict[str, float], stop_at: datetime, path: Path, every: int,
              index_symbol: str = "NDX") -> list[dict]:
    """Subscribe to trades and quotes for the strike band; record every print with its own quote.

    The index is subscribed alongside so each print carries the level that stood behind it: without it
    there is no way to tell afterwards whether a vertical was out of the money and cheap or deep in the
    money like the strategy's own structure, which is exactly the distinction that matters.
    """
    from tastytrade import DXLinkStreamer
    from tastytrade.dxfeed import Quote, TimeAndSale, Trade

    rows: list[dict] = []
    book: dict[str, tuple] = {}                 # streamer symbol -> (bid, ask), kept live off the feed
    spot: float | None = None
    fh = path.open("a", newline="", encoding="utf-8")
    w = csv.DictWriter(fh, fieldnames=COLS)
    if fh.tell() == 0:
        w.writeheader()
    last_report = datetime.now()

    import anyio

    async with DXLinkStreamer(prov.session) as streamer:
        await streamer.subscribe(Quote, list(symbols))
        await streamer.subscribe(TimeAndSale, list(symbols))
        # A cash index has no bid or ask -- it publishes a computed level, which arrives as Trade.
        await streamer.subscribe(Trade, [index_symbol])
        print(f"subscribed: {len(symbols)} strikes plus the {index_symbol} level, until {stop_at:%H:%M} ET\n")

        # Drained rather than awaited: a blocking listen() would stall on a quiet tape, so the clock
        # and the summaries would stop with it.
        while datetime.now() < stop_at:
            await anyio.sleep(0.25)
            q = streamer.get_event_nowait(Quote)
            while q is not None:
                book[str(q.event_symbol)] = (q.bid_price, q.ask_price)
                q = streamer.get_event_nowait(Quote)

            t = streamer.get_event_nowait(Trade)
            while t is not None:
                if str(t.event_symbol) == index_symbol and t.price is not None:
                    spot = float(t.price)
                t = streamer.get_event_nowait(Trade)

            ev = streamer.get_event_nowait(TimeAndSale)
            while ev is not None:
                cur, ev = ev, streamer.get_event_nowait(TimeAndSale)
                if str(cur.type).upper() not in ("NEW", "0", "NONE"):   # skip corrections and cancellations
                    continue
                sym = str(cur.event_symbol)
                pos = _pos(cur.bid_price, cur.ask_price, cur.price)
                width = None
                if cur.bid_price is not None and cur.ask_price is not None:
                    width = float(cur.ask_price) - float(cur.bid_price)
                when = datetime.fromtimestamp(cur.time / 1000) if cur.time else datetime.now()
                row = {
                    "ts": when.isoformat(timespec="milliseconds"),
                    "symbol": sym, "strike": symbols.get(sym),
                    "price": cur.price, "size": cur.size,
                    "bid": cur.bid_price, "ask": cur.ask_price,
                    "width": None if width is None else round(width, 2),
                    "pos": None if pos is None else round(pos, 3),
                    "spread_leg": bool(cur.spread_leg),
                    "aggressor": cur.aggressor_side, "exchange": cur.exchange_code,
                    "conditions": cur.exchange_sale_conditions,
                    "ndx": None if spot is None else round(spot, 2),
                    # how far in the money the call is, in points: positive = ITM, the strategy's long leg
                    "moneyness": (None if (spot is None or symbols.get(sym) is None)
                                  else round(spot - symbols[sym], 1)),
                }
                w.writerow(row)
                rows.append({**row, "pos": pos})
                if cur.spread_leg and pos is not None and float(cur.size or 0) >= 5:
                    print(f"{when:%H:%M:%S}  COMBO {sym:<20} {int(cur.size or 0):4d} @ {float(cur.price):7.2f}  "
                          f"quote {float(cur.bid_price):6.2f}/{float(cur.ask_price):6.2f}  "
                          f"-> {pos:+.0%} {_describe(pos)}  [{cur.aggressor_side}]")
            fh.flush()

            now = datetime.now()
            if (now - last_report).total_seconds() >= every:
                print(f"\n-- {now:%H:%M:%S} ET, {len(rows)} prints seen --")
                for line in _report(rows):
                    print(line)
                print()
                last_report = now
    fh.close()
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", required=True, help="the strategy whose live instrument to watch")
    ap.add_argument("--until", default="14:05", help="stop after this ET time (HH:MM)")
    # The strategy's own legs sit within ~50 points below spot, but nearly all the volume -- and so
    # nearly all the combo prints -- is at and above the money, which is where fill behaviour is visible.
    ap.add_argument("--band", type=float, default=300.0, help="strikes to watch below spot")
    ap.add_argument("--above", type=float, default=500.0, help="strikes to watch above spot")
    ap.add_argument("--every", type=int, default=120, help="seconds between summaries")
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args(argv)

    from paper.providers import TastytradeProvider, _sdk_loop, now_et
    from strategy_api import registry as R

    strategy = R.get_strategy(args.strategy)
    inst = strategy.live_instrument() or {}
    underlying = str(inst.get("underlying") or "NDX"); root = str(inst.get("root") or "NDXP")

    prov = TastytradeProvider(underlying, root)
    day = date.today()
    n = prov.load_chain(day)
    idx = prov.fetch([])
    spot_q = idx.get(underlying)
    spot = float(spot_q.last) if spot_q is not None and spot_q.last is not None else None
    if spot is None:
        print("no underlying price; cannot choose a strike band"); return 1

    # the band has to cover both legs as the index moves: the long leg sits deep in the money
    lo, hi = spot - args.band, spot + args.above
    symbols: dict[str, float] = {}
    for (cp, K), o in prov._chain.items():
        if cp != "C" or not (lo <= K <= hi):
            continue
        s = getattr(o, "streamer_symbol", None)
        if s:
            symbols[str(s)] = float(K)
    if not symbols:
        print("no streamer symbols on the chain"); return 1

    print(f"{underlying} {day}: {n} {root} contracts, spot {spot:,.2f}")
    print(f"watching {len(symbols)} call strikes from {lo:,.0f} to {hi:,.0f}")
    print("no spread quote exists in this feed; measuring the trades instead (spread_leg = a combo print)\n")

    out_dir = Path(args.out_dir) if args.out_dir else ROOT.parent / "alan-trader-logs"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"prints_{underlying}_{day.isoformat()}.csv"

    now = now_et()
    stop_at = datetime.now() + timedelta(
        seconds=max(0, (dtime(*(int(x) for x in args.until.split(":"))).hour * 3600
                        + dtime(*(int(x) for x in args.until.split(":"))).minute * 60)
                    - (now.hour * 3600 + now.minute * 60 + now.second)))

    loop = _sdk_loop()                    # the SDK's own long-lived loop; its session is bound to it
    rows = loop.run_until_complete(run(prov, symbols, stop_at, path, args.every, underlying))

    print(f"\n{len(rows)} prints recorded -> {path}")
    for line in _report(rows):
        print(line)
    combo = [r for r in rows if r["spread_leg"] and r["pos"] is not None]
    if not combo:
        print("\nno multi-leg prints were seen: where a resting spread order fills is still unmeasured")
    return 0


if __name__ == "__main__":
    sys.exit(main())
