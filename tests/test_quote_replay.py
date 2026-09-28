"""QuoteReplayProvider on a synthetic recording: minute bars from the recorded index, a vertical priced from its
legs' bid/ask exactly as the live runner prices it, the first snapshot after a minute's end, the last trade inferred
from the day volume, and the live freshness rule (a leg that has not traded for carry_min minutes is no quote)."""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from paper.providers import QuoteReplayProvider

DAY = date(2026, 9, 28)


def _rows():
    rows = []
    # snapshots every 15 s from 09:30:10 to 10:10:55; the index rises 1 point a minute from 30,000
    for m in range(0, 41):
        for s in (10, 25, 40, 55):
            ts = pd.Timestamp(f"2026-09-28 09:30:00") + pd.Timedelta(minutes=m, seconds=s)
            spot = 30000.0 + m + s / 60.0
            for K, bid, ask in ((30000.0, 40.0 + m, 42.0 + m), (30050.0, 15.0 + m / 2, 16.0 + m / 2)):
                # the short leg stops trading at 09:35 (its volume freezes); the long leg trades every minute
                vol = (100 + m) if K == 30000.0 else (50 + min(m, 5))
                rows.append({"ts": ts.tz_localize("US/Eastern").isoformat(), "underlying": spot,
                             "symbol": f"NDXP260928C{int(K * 1000):08d}", "right": "C", "strike": K, "bid": bid, "ask": ask,
                             "bid_size": 1, "ask_size": 1, "last": (bid + ask) / 2, "volume": vol,
                             "quote_time": ts.tz_localize("US/Eastern").isoformat()})
    return pd.DataFrame(rows)


def test_bars_and_the_vertical_quote():
    p = QuoteReplayProvider(DAY, frame=_rows(), carry_min=30)
    assert p.has_option_data() and len(p.bars) == 41 and str(p.bars.ts.iloc[0]) == "2026-09-28 09:30:00"
    b = p.next_bar()
    assert b.open == pytest.approx(30000.0 + 10 / 60) and b.close == pytest.approx(30000.0 + 55 / 60)
    # at the end of the 09:35 bar (minute 576 = 09:36) the first snapshot at or after 09:36:00 is 09:36:10 (m = 6)
    q = p.quote_vertical("call", 30000.0, 30050.0, 576)
    assert q.bid == pytest.approx((40.0 + 6) - (16.0 + 3)) and q.ask == pytest.approx((42.0 + 6) - (15.0 + 3))
    assert q.mid == pytest.approx(((40 + 6 - 16 - 3) + (42 + 6 - 15 - 3)) / 2)
    assert p.leg_symbols("put", 30000.0, 30050.0) == ("NDXP260928P30050000", "NDXP260928P30000000")


def test_a_leg_that_stopped_trading_goes_stale_like_live():
    p = QuoteReplayProvider(DAY, frame=_rows(), carry_min=3)
    # the short leg's volume last grew at 09:35:10; on the 09:38:10 snapshot it is 3 minutes old (the limit), on the
    # 09:40:10 one 5 minutes: no quote
    assert p.quote_vertical("call", 30000.0, 30050.0, 9 * 60 + 38) is not None
    assert p.quote_vertical("call", 30000.0, 30050.0, 9 * 60 + 40) is None


def test_no_snapshot_near_the_minute_is_no_quote():
    p = QuoteReplayProvider(DAY, frame=_rows())
    assert p.quote_vertical("call", 30000.0, 30050.0, 11 * 60) is None          # 11:00: the recording ended at 10:10
    assert p.quote_vertical("call", 30100.0, 30150.0, 9 * 60 + 40) is None      # strikes that were not recorded


def test_a_missing_recording_says_so(tmp_path):
    with pytest.raises(RuntimeError, match="no recorded NDXP quotes"):
        QuoteReplayProvider(DAY, quotes_dir=str(tmp_path))
