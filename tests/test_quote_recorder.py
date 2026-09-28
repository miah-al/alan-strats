"""The quote recorder: what it watches, when it writes, and that it never asks for quotes without the stream."""
import datetime as _dt
from zoneinfo import ZoneInfo

import pandas as pd

from api.services.quote_recorder import QuoteRecorder, read_day, strikes_around

NY = ZoneInfo("America/New_York")


class FakeStreamer:
    connected = True


class FakeHub:
    """Enough of MarketDataHub: watch / unwatch / snapshot over a fixed book of quotes."""

    def __init__(self, spot=30500.0, streaming=True):
        self.by_name = {"tastytrade": FakeStreamer()} if streaming else {}
        self.spot = spot
        self.watched: set[str] = set()
        self.snap_calls = 0

    def watch(self, owner, symbols):
        self.watched |= set(symbols)
        return list(symbols)

    def unwatch(self, owner, symbols):
        self.watched -= set(symbols)

    def unwatch_all(self, owner):
        self.watched.clear()

    def snapshot(self, symbols, wait=3.0):
        self.snap_calls += 1
        out = []
        for s in symbols:
            if s == "NDX":
                out.append({"symbol": "NDX", "last": self.spot})
            else:
                out.append({"symbol": s, "bid": 10.0, "ask": 11.5, "bid_size": 3, "ask_size": 5, "last": 10.8, "volume": 42,
                            "time": "2026-09-25T11:03:00-04:00"})
        return out


def clock(h, m):
    return lambda: _dt.datetime(2026, 9, 25, h, m, 0, tzinfo=NY)


def test_strikes_are_the_25_point_grid_around_spot():
    ks = strikes_around(30510.0)
    assert ks[0] == 30125.0 and ks[-1] == 30900.0
    assert all(k % 25 == 0 for k in ks)


def test_records_calls_and_puts_while_streaming_and_writes_a_day_file(tmp_path):
    hub = FakeHub()
    rec = QuoteRecorder(hub, out_dir=tmp_path, now=clock(11, 3))
    for _ in range(4):                       # a minute of 15-second snapshots is one append
        assert rec.tick() > 0
    path = tmp_path / "2026-09-25.csv.gz"
    df = read_day(path)
    assert set(df["right"]) == {"C", "P"}
    assert len(df) == 4 * len(rec.symbols)
    assert df["underlying"].iloc[0] == 30500.0
    assert list(df.columns[:5]) == ["ts", "underlying", "symbol", "right", "strike"]
    n = len(rec.symbols)
    rec.tick(); rec.stop()                   # stop flushes the partial minute: still one readable file, one header
    assert len(read_day(path)) == 5 * n
    assert not rec.symbols                   # and releases the contracts


def test_nothing_is_asked_without_the_stream_or_outside_the_session(tmp_path):
    hub = FakeHub(streaming=False)
    assert QuoteRecorder(hub, out_dir=tmp_path, now=clock(11, 3)).tick() == 0
    assert hub.snap_calls == 0 and not hub.watched
    hub = FakeHub()
    assert QuoteRecorder(hub, out_dir=tmp_path, now=clock(8, 0)).tick() == 0
    assert QuoteRecorder(hub, out_dir=tmp_path, now=lambda: _dt.datetime(2026, 9, 26, 11, 0, tzinfo=NY)).tick() == 0   # Saturday
    assert hub.snap_calls == 0


def test_recentres_when_ndx_moves_a_quarter_band(tmp_path):
    hub = FakeHub(spot=30500.0)
    rec = QuoteRecorder(hub, out_dir=tmp_path, now=clock(11, 3))
    rec.tick()
    first = set(rec.symbols)
    hub.spot = 30650.0                       # +150 > 100
    rec.tick()
    assert rec.center == 30650.0 and set(rec.symbols) != first
    assert hub.watched == set(rec.symbols)   # the strikes that fell out of the band were released
