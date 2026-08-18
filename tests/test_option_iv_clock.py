"""
Option IV reconstruction must use a calendar-day year.

`db/sync.py` derives implied vol by inverting Black-Scholes against an option's
observed close. `dte` there is CALENDAR days, but the year fraction was computed
as `dte / 252.0` — a trading-day denominator. That made T 365/252 = 1.45x too
large, and because sigma is solved to reproduce a fixed observed price, an
over-large T forces a correspondingly smaller sigma: every stored ImpliedVol
came out ~15% too low, and _bs_greeks inherited the same T so Delta and Gamma
carried it as well.
"""

import math

import pytest

from alan_trader.db.sync import _bs_mid, _bs_greeks


def _invert_iv(price, S, K, T, r, opt):
    """Recover sigma from a price by bisection — what sync.py does with brentq."""
    lo, hi = 1e-4, 5.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if _bs_mid(S, K, T, r, mid, opt) < price:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def test_sync_uses_a_calendar_year_for_calendar_dte():
    import inspect
    from alan_trader.db import sync

    src = inspect.getsource(sync.sync_option_snapshots)
    assert "T = dte / 365.0" in src
    assert "T = dte / 252.0" not in src, (
        "calendar dte divided by a trading-day year understates every IV ~15%"
    )


def test_wrong_year_fraction_understates_implied_vol():
    """Quantifies the bug: same price, wrong clock, ~15% lower sigma."""
    S, K, r, true_iv = 500.0, 490.0, 0.045, 0.20
    dte_calendar = 30
    price = _bs_mid(S, K, dte_calendar / 365.0, r, true_iv, "put")

    correct = _invert_iv(price, S, K, dte_calendar / 365.0, r, "put")
    buggy = _invert_iv(price, S, K, dte_calendar / 252.0, r, "put")

    assert correct == pytest.approx(true_iv, rel=1e-3)
    ratio = buggy / correct
    # Predicted sqrt(252/365) = 0.831; measured on real data 0.851.
    assert 0.80 < ratio < 0.90, f"expected ~0.83 understatement, got {ratio:.3f}"


def test_greeks_share_the_same_clock():
    """Delta/Gamma are derived from the same T, so they inherit the error."""
    S, K, r, iv = 500.0, 490.0, 0.045, 0.20
    d_ok, g_ok = _bs_greeks(S, K, 30 / 365.0, r, iv, "put")
    d_bad, g_bad = _bs_greeks(S, K, 30 / 252.0, r, iv, "put")
    assert d_ok is not None and d_bad is not None
    assert abs(d_ok - d_bad) > 0.01, "the clock must materially move delta"
