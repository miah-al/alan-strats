"""The at-the-money straddle (api/marketdata/options.py pick_straddle, straddle_expiry): the market's expected move to
the close, read off the nearest strike's call and put at their mids, stale quotes named."""
import datetime as dt

import pandas as pd

from api.marketdata.options import pick_straddle, straddle_expiry

NOW = dt.datetime(2026, 11, 5, 12, 43, 30, tzinfo=dt.timezone(dt.timedelta(hours=-5)))


def side(bid, ask, age_s=5.0, symbol=None):
    return {"bid": bid, "ask": ask, "symbol": symbol, "quote_time": (NOW - dt.timedelta(seconds=age_s)).isoformat()}


def row(k, call, put):
    return {"strike": k, "call": call, "put": put}


def test_the_nearest_strike_at_the_mids():
    # SPXW 0DTE at 12:43 on 2026-11-05, SPX 7,402.12: the 7400 call 29.4/29.6 and put 25.5/25.7
    rows = [row(7395.0, side(39.4, 39.7), side(23.2, 23.5)),
            row(7400.0, side(29.4, 29.6), side(25.5, 25.7)),
            row(7405.0, side(27.2, 27.4), side(27.6, 27.9))]
    s = pick_straddle(rows, 7402.12, NOW)
    assert s["strike"] == 7400.0
    assert s["straddle"] == 55.1
    assert abs(s["pct"] - 55.1 / 7402.12 * 100) < 1e-3
    assert s["half_spread"] == 0.2
    assert s["stale"] is False and s["quote_age_s"] == 5.0


def test_a_stale_nearest_strike_gives_way_to_a_fresh_one_as_near():
    # SPX exactly between two strikes: the one whose quotes are minutes old loses to the fresh one
    rows = [row(7400.0, side(29.4, 29.6, age_s=240), side(25.5, 25.7)),
            row(7405.0, side(27.2, 27.4), side(27.6, 27.9))]
    assert pick_straddle(rows, 7402.5, NOW)["strike"] == 7405.0


def test_only_stale_quotes_are_shown_but_named():
    rows = [row(7400.0, side(29.4, 29.6, age_s=240), side(25.5, 25.7, age_s=10))]
    s = pick_straddle(rows, 7402.12, NOW)
    assert s["stale"] is True and s["quote_age_s"] == 240.0


def test_a_one_sided_strike_is_skipped():
    rows = [row(7400.0, side(None, 29.6), side(25.5, 25.7)),
            row(7405.0, side(27.2, 27.4), side(27.6, 27.9))]
    assert pick_straddle(rows, 7401.0, NOW)["strike"] == 7405.0
    assert pick_straddle([row(7400.0, side(0.0, 0.0), side(25.5, 25.7))], 7401.0, NOW) is None


def test_the_expiry_is_today_until_the_close_then_the_next_weekday():
    ny = "America/New_York"
    assert straddle_expiry(pd.Timestamp("2026-11-05 12:43", tz=ny)) == dt.date(2026, 11, 5)
    assert straddle_expiry(pd.Timestamp("2026-11-05 16:05", tz=ny)) == dt.date(2026, 11, 6)
    assert straddle_expiry(pd.Timestamp("2026-11-06 16:30", tz=ny)) == dt.date(2026, 11, 9)    # Friday night: Monday
    assert straddle_expiry(pd.Timestamp("2026-11-07 10:00", tz=ny)) == dt.date(2026, 11, 9)    # Saturday
