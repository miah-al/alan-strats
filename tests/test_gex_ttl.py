"""The dealer-GEX answer is reused for an hour outside the session: each load for a stock is Polygon's whole chain
snapshot (~40 calls for SPY), and the market strip asks every 5 minutes all night (2026-10-05: the 5,000-call day spent
by 08:47)."""
from __future__ import annotations

import datetime as _dt
from zoneinfo import ZoneInfo

from api.routers.market import GEX_TTL, GEX_TTL_CLOSED, gex_ttl

NY = ZoneInfo("America/New_York")


def at(y, m, d, hh, mm):
    return _dt.datetime(y, m, d, hh, mm, tzinfo=NY)


def test_a_minute_in_the_session_an_hour_outside():
    assert gex_ttl(at(2026, 10, 5, 9, 30)) == GEX_TTL == 60.0        # Monday, the open
    assert gex_ttl(at(2026, 10, 5, 15, 59)) == GEX_TTL
    assert gex_ttl(at(2026, 10, 5, 16, 10)) == GEX_TTL               # the recorder's end-of-day rows run then
    assert gex_ttl(at(2026, 10, 5, 16, 15)) == GEX_TTL_CLOSED == 3600.0
    assert gex_ttl(at(2026, 10, 6, 2, 0)) == GEX_TTL_CLOSED           # overnight
    assert gex_ttl(at(2026, 10, 6, 9, 29)) == GEX_TTL_CLOSED
    assert gex_ttl(at(2026, 10, 3, 11, 0)) == GEX_TTL_CLOSED          # Saturday
