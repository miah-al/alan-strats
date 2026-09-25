"""The live-session contract between the platform's paper runner and a strategy plugin.

The platform owns the clock, the quotes, the ledger and the logs; the strategy owns the rules.
A strategy that can be paper traded exposes:

  ``session_gate(day, events=None) -> (blocked: bool, reason: str)``
      whether the session is tradeable at all (calendar, volatility gate, weekly caps)
  ``live_session(day, blocked_reason="", bar_min=1) -> LiveSession``
      a fresh engine for the day

and the engine is driven one bar at a time with ``on_bar``. The runner reads ``fills`` after
every bar and writes the new ones to the ledger; ``to_dict`` / ``from_dict`` let it resume after
a restart. Quotes are for the strategy's instrument as one number set: a vertical spread by default
(``kind`` = call | put), or one of the multi-leg STRUCTURE_KINDS below (a straddle, an iron fly), always in
long-structure terms (bid = what a seller of the whole structure gets, ask = what a buyer pays).

Optional hooks (the live runner looks for them with ``getattr``; an engine without them behaves as before):

  ``on_poll(now, spot, quote_fn)``
      called at every quote poll between bar closes with the quotes just fetched, for engines that work
      resting orders and must see every quote, not one a minute; ``spot`` may be None
  ``watch_structures() -> [(kind, k_low, k_high)]``
      structures to keep quoted every poll beyond the open and pending ones (e.g. the other right of a
      vertical, read by parity); their legs are fetched in the same request as everything else
  ``max_fills_per_session: int``
      the engine's own ceiling for the runner's runaway guard, for engines that log every order placed
      and cancelled in ``fills``

Fill rows beyond the vertical's (``kind`` rest | open | add | close | cancel with direction bull | bear):
  a STRUCTURE fill carries ``struct`` (straddle | iron_fly), ``direction`` long | short and ``legs``
      = [[cp, strike, sign, price], ...] (sign +1 bought, -1 sold, in long-structure terms) so the ledger can
      book every leg;
  a SYNTHETIC HEDGE row has ``kind`` "hedge", ``struct`` "hedge", ``synthetic`` True, ``symbol`` (NQ=NDX),
      ``direction`` buy | sell | flat, ``units`` (NQ-equivalents, fractional), ``px`` (the index level paid),
      ``cash``, ``hedge_units`` (the book after the trade) and ``final`` (the row that closes the book).
      Nothing about it is a real future: it is priced off the index and booked as SecurityType SynFuture.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Protocol, runtime_checkable

#: multi-leg structures the runner can quote and book beside the vertical: (k_low, k_high) are the wings of an iron
#: fly (its body is their midpoint) and both equal the body of a straddle
STRUCTURE_KINDS = ("straddle", "iron_fly")
#: the synthetic futures hedge's security type in the paper ledger (portfolio.Security.SecurityType is VARCHAR(10))
SYNTHETIC_FUTURE_TYPE = "SynFuture"


@dataclass(frozen=True)
class Quote:
    """A two-sided quote for the strategy's instrument, in its own price units (index points
    per spread for an NDX vertical). ``age`` is minutes since the quote or last print updated."""
    bid: float
    ask: float
    last: float
    age: int = 0
    legs: Optional[tuple] = None   # ((bid, ask, age), (bid, ask, age)) of the long and short leg when the quote came from leg quotes
    prints: Optional[tuple] = None  # ((last, last_time), (last, last_time)) of the long and short leg's most recent trade, when
                                    # the feed reports one (None entries otherwise); a resting-order engine tells a NEW print
                                    # from the previous poll's by comparing both
    age_s: Optional[float] = None   # the same age in seconds when the provider knows it (an engine that counts polls needs
                                    # finer than a minute); None means "only ``age`` is known"

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0


def structure_legs(kind: str, k_low: float, k_high: float) -> list[tuple[str, float, int]]:
    """(cp, strike, sign) of the LONG structure ``kind``: sign +1 bought, -1 sold. A straddle has k_low == k_high
    == its body; an iron fly's body is the midpoint of its wings (long the body, short the wings)."""
    K = (float(k_low) + float(k_high)) / 2.0
    legs = [("C", K, 1), ("P", K, 1)]
    if kind == "iron_fly":
        legs += [("C", float(k_high), -1), ("P", float(k_low), -1)]
    elif kind != "straddle":
        raise ValueError(f"unknown structure kind {kind!r}")
    return legs


def is_structure(kind: str) -> bool:
    return str(kind) in STRUCTURE_KINDS


#: (spot, k_low, k_high, kind, minute_end) -> Quote | None
QuoteFn = Callable[[float, float, float, str, int], Optional[Quote]]


@runtime_checkable
class LiveSession(Protocol):
    fills: list          # dicts: m (minute), kind (rest|open|add|close|cancel|hedge), direction, kl, kh, px, lots, cash, reason
    trades: list
    positions: list
    blocked_reason: str

    def on_bar(self, minute: int, S: float, quote_fn: QuoteFn, is_last: bool = False,
               high: Optional[float] = None, low: Optional[float] = None) -> None: ...
    def marked(self) -> float: ...
    def to_dict(self) -> dict: ...
