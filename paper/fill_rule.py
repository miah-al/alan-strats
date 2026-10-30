"""Where an NDXP or SPXW option order fills, and what it pays in fees: the rule for every paper booking a strategy's own
engine does not price (the order service: the desk and manual orders).

The fills research of 2026-10-30 (the owner: "We need to put fills to bed") read the recorder's tape -- 19,224 NDXP and
367,180 SPXW two-leg call spreads, each with its legs' quotes at the instant it printed -- beside the friend's 1,296
real NDX orders and the exchanges' rules. Index spread orders trade at the MID of the quote built from their legs, not
at that quote's bid: NDXP prints at exactly the mid in the median, 95% at the mid less 0.5 or better, 0.4% at the bid;
SPXW prints within a nickel of the mid, 98-99% at the mid less 0.05 or better. So a paper order gives up a little,
vertical by vertical:

  NDXP  the mid less max(0.5, a quarter of the vertical's half-width)  (when the legs are quoted 10+ points wide, 88% of
        the prints still beat the mid less 0.5)
  SPXW  the mid less 0.05
  and never through the vertical's own bid / ask (the bought legs' asks less the sold legs' bids).

A multi-leg order is priced vertical by vertical: its contracts pair by right and expiry, each sold one with the bought
one nearest in strike (a condor is two verticals, a butterfly two). A contract left unpaired gives up the same on its
own -- an assumption: no single-leg study was made. A vertical's mid is first kept inside what the vertical can be
worth, 0 to its strike width: the legs' mids of a far out-of-the-money spread near the close can say otherwise (on
2026-10-22 at 15:55 the 29150/29175 calls' mids made buying the spread back a 0.53 CREDIT).

Fees, tastytrade's schedule of 2026-10-28, per contract: a $1 commission to open (none to close), $0.10 clearing,
$0.02 options regulatory fee and the index fee (SPX $0.60, NDX $0.25), with the SEC fee on sales rounded in -- $3.45
and $2.77 a spread opened. A cash settlement costs nothing here: the listed $5 exercise / assignment fee is unverified
for cash-settled options, and FINRA's trading fee is waived to 2026-12-31.

Any other underlying (a stock, an ETF, their options) still fills at each leg's mid, at the platform's flat commission.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

#: the measured index an order's underlying or option root belongs to
INDEX = {"NDX": "NDX", "NDXP": "NDX", "SPX": "SPX", "SPXW": "SPX"}
#: points a vertical gives up against its mid: (the floor, the share of the vertical's half-width when that is more)
CONCESSION = {"NDX": (0.5, 0.25), "SPX": (0.05, 0.0)}
#: dollars per contract: (to open, to close)
FEES = {"NDX": (1.385, 0.385), "SPX": (1.725, 0.725)}
#: how each index's rule reads in a fill message
RULE_TEXT = {"NDX": "the mid less max(0.5, a quarter of the half-width) a vertical",
             "SPX": "the mid less 0.05 a vertical"}


def index_of(underlying: Optional[str]) -> Optional[str]:
    """``NDX`` or ``SPX`` for an order on those indices (or their option roots), else None."""
    return INDEX.get(str(underlying or "").strip().upper())


def concession(index: str, half_width: float) -> float:
    """Points a vertical (or an unpaired contract) gives up against its mid, before the bid / ask cap."""
    floor, share = CONCESSION[index]
    return max(floor, share * max(0.0, float(half_width)))


def fee_per_contract(index: Optional[str], opening: bool) -> Optional[float]:
    """The fee in dollars a contract pays to open (or close); None for an underlying without a measured schedule."""
    if index not in FEES:
        return None
    return FEES[index][0 if opening else 1]


@dataclass
class RuleLeg:
    type: str                 # call | put
    side: str                 # buy | sell
    ratio: int                # contracts per unit of the order
    strike: float
    expiry: object
    bid: float
    ask: float

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    @property
    def half_width(self) -> float:
        return max(0.0, (self.ask - self.bid) / 2.0)


def _bounds(cp: str, k_buy: float, k_sell: float) -> tuple[float, float]:
    """What one bought contract less one sold contract of the same right and expiry can be worth (debit positive)."""
    w = (k_sell - k_buy) if cp == "call" else (k_buy - k_sell)
    return min(0.0, w), max(0.0, w)


def leg_prices(index: str, legs: list[RuleLeg]) -> tuple[list[float], float, float]:
    """Each leg's fill price under the rule, and the order's net per unit at those prices and at the legs' mids
    (debit positive). Every leg needs a two-sided quote; the caller checks that first."""
    units = [i for i, l in enumerate(legs) for _ in range(int(l.ratio))]
    adj: dict[int, list[float]] = {i: [] for i in range(len(legs))}      # per unit: points against us (+ = worse)
    groups: dict[tuple, dict[str, list[int]]] = {}
    for i in units:
        g = groups.setdefault((legs[i].type, legs[i].expiry), {"buy": [], "sell": []})
        g[legs[i].side].append(i)
    for g in groups.values():
        buys, sells = g["buy"], g["sell"]
        while buys and sells:                                 # the closest pair of strikes first
            b, s = min(((b, s) for b in buys for s in sells), key=lambda p: abs(legs[p[0]].strike - legs[p[1]].strike))
            buys.remove(b); sells.remove(s)
            lb, ls = legs[b], legs[s]
            mid = lb.mid - ls.mid
            lo, hi = _bounds(lb.type, lb.strike, ls.strike)
            hw = lb.half_width + ls.half_width
            net = min(lb.ask - ls.bid, min(max(mid, lo), hi) + concession(index, hw))
            a = net - mid                                     # what the pair pays over its legs' mids
            wb = lb.half_width / hw if hw > 0 else 0.5
            adj[b].append(a * wb)
            adj[s].append(a * (1.0 - wb))
        for i in buys + sells:                                # a contract with no partner
            adj[i].append(min(legs[i].half_width, concession(index, legs[i].half_width)))
    prices, net_fill, net_mid = [], 0.0, 0.0
    for i, l in enumerate(legs):
        a = sum(adj[i]) / len(adj[i]) if adj[i] else 0.0
        px = max(0.0, l.mid + a) if l.side == "buy" else max(0.0, l.mid - a)
        prices.append(round(px, 4))
        sign = 1.0 if l.side == "buy" else -1.0
        net_fill += sign * l.ratio * px
        net_mid += sign * l.ratio * l.mid
    return prices, round(net_fill, 4), round(net_mid, 4)
