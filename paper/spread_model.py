"""The bid/ask a replayed vertical is quoted at, calibrated from the paper runners' live quotes.

Stored option data is one-minute PRINTS (mkt.OptionMinuteBar), one price per leg per minute, no bid or
ask. A replay or a market-priced backtest has to invent the spread around the print, and the number it
invents is the execution cost every conclusion rests on. Until 2026-09-25 that number was a flat
half-spread of 0.5 point. The live runners measured the real thing, and it is nowhere near flat.

Calibration data
----------------
1. The leg quotes the ndx_0dte_tasty runner logged at each of its 16 fills (paper_log/archive/2026-09-23
   and 2026-09-24, events.csv: long_bid/ask, short_bid/ask) and the two legs of each side of the
   ndx_gamma_walls entry of 2026-09-25 (call 30625/30675: 33.7/37.2 and 19.5/21.9; puts 115.5/126.4 and
   81.7/92.1; NDX about 30,573). 36 leg quotes. Half-spread of ONE LEG by how far it is in the money
   (points; negative = out of the money), both days VXN near 20:

       in the money   <= -25   -25..0   0..10   10..25   25..40   40..60   60..80   80+
       half-spread     1.2-1.75  1.3-1.9  1.3-2.5  2.05-2.1  4.15-5.4  4.15-6.6  5.6-6.8  5.45-5.8
       n                 6         4        5        2         6         8         4       3

   An out-of-the-money 0DTE NDXP leg is quoted about 1.5 points either side; at the money about 2;
   25-60 points in the money 4-6.6; deeper 5.5-7. That is the whole shape: the market makes a market in
   the out-of-the-money contract and quotes the in-the-money one wide.
2. The derived spread quotes of the verticals the runner held, one row per poll (marks.csv, 800 rows):
   they are what the sum of two leg quotes looks like minute by minute -- 2.2 points wide when both
   legs were out of the money late in the day, 12-14 when the long leg sat 50+ in the money in the
   morning, 21 at the widest.

The model
---------
``LiveSpread`` prices a vertical's half-spread as the SUM of its two legs' half-spreads, each read off
a piecewise-linear curve through the p75 of the leg buckets (erring wide where the data is thin: two
quotes between 10 and 25 in the money, none beyond 105):

       in the money   -25    0     10    25    40    60    80
       leg half-spread 1.75  2.00  2.50  4.25  5.75  6.75  7.25   (flat outside)

That is exactly how the live runner builds a vertical's quote (paper/providers.py vertical_quote: bid =
bid(long) - ask(short), ask = ask(long) - bid(short)), so a replay's spread and a live session's spread
come from the same construction. Width dependence follows from the strikes: a wider structure puts its
long leg deeper in the money and its short leg further out. Against the 17 logged fills the model is
between 1.0x and 1.5x the width the runner saw, never narrower. One cap: the bid is never negative
(half-spread <= the value), which only binds on spreads worth a point or two.

When the caller has no spot (a study that only knows the spread's value) the fallback is a curve on
the spread's moneyness f = value / width, the p75 of the marks bucketed by f, scaled by sqrt(width / 50):

       f      0.0   0.1   0.2   0.3   0.4   0.5   0.6   0.7   0.8   1.0
       half   1.4   2.0   2.75  3.25  4.25  6.0   7.5   9.5   10.5  11.0

It is coarser (it cannot see a 12-point spread whose long leg is 32 in the money, quoted 12.6 wide on
2026-09-24 12:15) and the leg model is preferred wherever spot is known.

Two things this is NOT. It is not where multi-leg orders fill: 1,458 NDXP verticals rebuilt from
multi-leg prints (2026-09-23) transacted at the derived mid on the median, and whoever crossed paid
about 1.2 points -- the derived NBBO is the price of crossing leg by leg, the floor a taker model
should assume. And it is not a time-of-day or vol model: the 2026-09-24 morning quotes were wider than
the 2026-09-23 afternoon ones at the same moneyness; that difference sits inside the p75 margin.

``FlatSpread(h)`` is the old assumption, kept so an OPTIMISTIC run can still be produced and labelled.
"""
from __future__ import annotations

import bisect
import math
from typing import Callable, Optional, Union

#: (points in the money, half-spread of ONE leg in points): the p75 of the logged leg quotes, flat outside
LEG_CURVE: tuple[tuple[float, float], ...] = (
    (-25.0, 1.75), (0.0, 2.00), (10.0, 2.50), (25.0, 4.25), (40.0, 5.75), (60.0, 6.75), (80.0, 7.25),
)
#: (f = value / width, half-spread in points) for a 50-point-wide vertical: the fallback when spot is unknown
LIVE_CURVE_50: tuple[tuple[float, float], ...] = (
    (0.0, 1.40), (0.1, 2.00), (0.2, 2.75), (0.3, 3.25), (0.4, 4.25), (0.5, 6.00), (0.6, 7.50), (0.7, 9.50),
    (0.8, 10.50), (1.0, 11.00),
)
REFERENCE_WIDTH = 50.0
#: the crossing cost measured on multi-leg prints (2026-09-23): what a vertical order pays past the mid
MEASURED_CROSSING_PTS = 1.2
#: the assumption every backtest and replay used until 2026-09-25
LEGACY_FLAT_HALF_SPREAD = 0.5

#: fn(value, width, S=None, k_low=None, k_high=None, kind=None) -> half-spread in points
SpreadFn = Callable[..., float]


def _interp(curve: tuple[tuple[float, float], ...], xs: list[float], x: float) -> float:
    i = bisect.bisect_right(xs, x) - 1
    if i < 0:
        return curve[0][1]
    if i >= len(curve) - 1:
        return curve[-1][1]
    (x0, y0), (x1, y1) = curve[i], curve[i + 1]
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)


def leg_moneyness(kind: str, k_low: float, k_high: float, S: float) -> tuple[float, float]:
    """(long leg, short leg) points in the money for a LONG vertical: calls are long k_low / short k_high,
    puts long k_high / short k_low."""
    if str(kind).lower().startswith("c"):
        return float(S) - float(k_low), float(S) - float(k_high)
    return float(k_high) - float(S), float(k_low) - float(S)


class LiveSpread:
    """Half-spread (points) of a vertical: the sum of its legs' half-spreads by moneyness when spot and strikes
    are given, else the value-curve fallback. ``scale`` multiplies the whole thing (1.0 = as calibrated)."""

    name = "live"

    def __init__(self, scale: float = 1.0, leg_curve: tuple[tuple[float, float], ...] = LEG_CURVE,
                 curve: tuple[tuple[float, float], ...] = LIVE_CURVE_50):
        self.scale = float(scale)
        self.leg_curve = tuple(sorted((float(m), float(h)) for m, h in leg_curve))
        self._ms = [m for m, _ in self.leg_curve]
        self.curve = tuple(sorted((float(f), float(h)) for f, h in curve))
        self._fs = [f for f, _ in self.curve]

    def leg(self, itm_pts: float) -> float:
        """Half-spread of one leg that is ``itm_pts`` points in the money (negative: out of the money)."""
        return _interp(self.leg_curve, self._ms, float(itm_pts)) * self.scale

    def by_value(self, value: float, width: float) -> float:
        """The fallback: by the spread's own moneyness (value / width), scaled by sqrt(width / 50)."""
        w = float(width) if width and width > 0 else REFERENCE_WIDTH
        f = min(1.0, max(0.0, float(value) / w))
        return _interp(self.curve, self._fs, f) * math.sqrt(w / REFERENCE_WIDTH) * self.scale

    def __call__(self, value: float, width: float, S: Optional[float] = None, k_low: Optional[float] = None,
                 k_high: Optional[float] = None, kind: Optional[str] = None) -> float:
        if S is not None and k_low is not None and k_high is not None and kind:
            m_long, m_short = leg_moneyness(kind, k_low, k_high, S)
            h = self.leg(m_long) + self.leg(m_short)
        else:
            h = self.by_value(value, width)
        v = float(value)
        if v > 0:
            h = min(h, v)                       # the bid never goes negative; binds only on spreads worth a point or two
        return h

    @property
    def label(self) -> str:
        s = "" if self.scale == 1.0 else f" x{self.scale:g}"
        return f"live spread model (the legs' half-spreads by moneyness, p75 of the 2026-09-23/24/25 quotes){s}"

    def __repr__(self) -> str:
        return f"LiveSpread(scale={self.scale:g})"


class FlatSpread:
    """The old bracket: the same half-spread whatever the structure. Optimistic below ~1.2 points."""

    name = "flat"

    def __init__(self, half_spread: float = LEGACY_FLAT_HALF_SPREAD):
        self.h = float(half_spread)

    def __call__(self, value: float, width: float, S=None, k_low=None, k_high=None, kind=None) -> float:
        return self.h

    @property
    def label(self) -> str:
        return f"flat half-spread {self.h:g} pt"

    def __repr__(self) -> str:
        return f"FlatSpread({self.h:g})"


def make_spread(spec: Union[None, str, float, int, SpreadFn] = None) -> SpreadFn:
    """``None`` / ``"live"`` -> the calibrated model; a number -> that flat half-spread; a callable as is."""
    if spec is None:
        return LiveSpread()
    if callable(spec):
        return spec
    if isinstance(spec, str):
        s = spec.strip().lower()
        if s in ("", "live", "model", "conservative"):
            return LiveSpread()
        if s in ("flat", "legacy", "optimistic"):
            return FlatSpread()
        return FlatSpread(float(s))
    return FlatSpread(float(spec))


def label_of(fn: Optional[SpreadFn]) -> str:
    if fn is None:
        return "no spread"
    return getattr(fn, "label", None) or getattr(fn, "__name__", repr(fn))


def is_conservative(fn: SpreadFn) -> bool:
    """A spread model counts as conservative when it is at least the calibrated curve, or a flat bracket no
    narrower than the measured crossing cost."""
    if isinstance(fn, LiveSpread):
        return fn.scale >= 1.0
    if isinstance(fn, FlatSpread):
        return fn.h >= MEASURED_CROSSING_PTS
    return False
