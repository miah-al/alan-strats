"""The DXLink quote stream (paper.providers.StreamQuotes) and the provider's --stream mode (2026-10-06, the owner:
"Fix the execution"): the legs' quotes come from a market-data subscription, so a runner can look every couple of
seconds without spending the broker's REST budget; REST is only the fallback. No network: a fake SDK and a fake
streamer."""
from __future__ import annotations

import sys
import time
import types
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from paper.providers import LegQuote, StreamQuotes, TastytradeProvider


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


NOW = datetime(2026, 10, 6, 11, 0, 5)


def test_events_update_the_book_and_health_follows_the_feed():
    clk = Clock()
    s = StreamQuotes(lambda: None, "NDX", clock=clk, now_fn=lambda: NOW, start=False)
    assert not s.healthy() and s.get(".NDXP1") is None
    s.on_quote(SimpleNamespace(event_symbol=".NDXP1", bid_price=Decimal("70.1"), ask_price=Decimal("76.3")))
    s.on_trade(SimpleNamespace(event_symbol="NDX", price=30010.5, time=1791298805000))     # 2026-10-06 11:00:05 ET
    s.on_quote(SimpleNamespace(event_symbol=".NDXP2", bid_price=float("nan"), ask_price=3.0))
    s.connected = True
    q = s.get(".NDXP1")
    assert (q.bid, q.ask, q.updated) == (70.1, 76.3, NOW)
    idx = s.get("NDX")
    assert idx.last == 30010.5 and idx.last_time == datetime(2026, 10, 6, 11, 0, 5) and idx.bid is None
    assert s.get(".NDXP2").bid is None                              # NaN is "no value"
    assert s.healthy()
    clk.t += StreamQuotes.STALE_S + 1                               # the feed went quiet
    assert not s.healthy()


class FakeStreamer:
    """An async context manager like DXLinkStreamer: records subscriptions, serves queued events."""
    instances: list = []

    def __init__(self, session):
        self.session, self.subs, self.queues = session, [], {}
        FakeStreamer.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def subscribe(self, cls, symbols):
        self.subs.append((cls.__name__, list(symbols)))
        for s in symbols:
            if cls.__name__ == "Q":
                self.queues.setdefault(cls, []).append(SimpleNamespace(event_symbol=s, bid_price=10.0, ask_price=12.0))
            else:
                self.queues.setdefault(cls, []).append(SimpleNamespace(event_symbol=s, price=30000.0, time=0))

    def get_event_nowait(self, cls):
        q = self.queues.get(cls) or []
        return q.pop(0) if q else None


class Q:
    pass


class T:
    pass


def test_the_thread_subscribes_the_index_and_each_wanted_leg_once():
    FakeStreamer.instances.clear()
    s = StreamQuotes(lambda: "session", "NDX", streamer_factory=FakeStreamer, quote_cls=Q, trade_cls=T,
                     now_fn=lambda: NOW)
    try:
        s.want([".NDXP1", ".NDXP2", None])
        deadline = time.time() + 5
        while time.time() < deadline and (s.get(".NDXP2") is None or s.get("NDX") is None):
            time.sleep(0.05)
        s.want([".NDXP1"])                                          # already subscribed: no second request
        time.sleep(0.3)
        st = FakeStreamer.instances[0]
        assert st.session == "session"
        assert st.subs[0] == ("T", ["NDX"])
        assert ("Q", [".NDXP1", ".NDXP2"]) in st.subs and sum(1 for c, _ in st.subs if c == "Q") == 1
        assert s.get(".NDXP1").bid == 10.0 and s.get("NDX").last == 30000.0 and s.healthy()
    finally:
        s.stop()


# ── the provider ─────────────────────────────────────────────────────────────────

class _Opt:
    def __init__(self, symbol, strike, right):
        self.symbol, self.root_symbol, self.strike_price, self.option_type = symbol, "NDXP", Decimal(strike), right
        self.streamer_symbol = "." + symbol


@pytest.fixture
def sdk(monkeypatch):
    calls = {"fetches": 0}

    class Session:
        def __init__(self, *a, **k):
            pass

    tt = types.ModuleType("tastytrade"); tt.Session = Session
    inst = types.ModuleType("tastytrade.instruments")
    day = date(2026, 10, 6)
    inst.get_option_chain = lambda session, symbol: {day: [_Opt("NDXP1", "29900", "C"), _Opt("NDXP2", "30000", "C")]}
    md = types.ModuleType("tastytrade.market_data")

    def get_market_data_by_type(session, indices=None, options=None, **kw):
        calls["fetches"] += 1
        utc = datetime(2026, 10, 6, 15, 0, 0)
        rows = [SimpleNamespace(symbol="NDX", bid=None, ask=None, last=Decimal("30001"), last_trade_time=None, updated_at=utc)]
        rows += [SimpleNamespace(symbol=s, bid=Decimal("1"), ask=Decimal("2"), last=None, last_trade_time=None, updated_at=utc)
                 for s in options or []]
        return rows
    md.get_market_data_by_type = get_market_data_by_type
    monkeypatch.setitem(sys.modules, "tastytrade", tt)
    monkeypatch.setitem(sys.modules, "tastytrade.instruments", inst)
    monkeypatch.setitem(sys.modules, "tastytrade.market_data", md)
    monkeypatch.setenv("TT_SECRET", "s"); monkeypatch.setenv("TT_REFRESH", "r")
    return calls


class FakeStream:
    def __init__(self):
        self.book, self.wanted, self.ok = {}, set(), True

    def want(self, syms):
        self.wanted.update(s for s in syms if s)

    def get(self, sym):
        return self.book.get(sym)

    def healthy(self):
        return self.ok


def _provider(sdk, clk):
    fs = FakeStream()
    p = TastytradeProvider("NDX", "NDXP", stream=True, stream_factory=lambda: fs, clock=clk)
    p.budget.take = lambda *a, **k: None                           # the budget's own pacing is tested elsewhere
    p.load_chain(date(2026, 10, 6))
    return p, fs


def test_a_healthy_stream_answers_from_memory_and_spends_no_rest(sdk):
    clk = Clock()
    p, fs = _provider(sdk, clk)
    fs.book = {".NDXP1": LegQuote(".NDXP1", 70.0, 76.0, None, None, datetime(2026, 10, 6, 10, 50)),
               ".NDXP2": LegQuote(".NDXP2", 12.0, 14.0, None, None, datetime(2026, 10, 6, 10, 50)),
               "NDX": LegQuote("NDX", None, None, 30005.0, datetime(2026, 10, 6, 11, 0), datetime(2026, 10, 6, 11, 0))}
    q = p.fetch(["NDXP1", "NDXP2"])
    assert sdk["fetches"] == 0 and fs.wanted == {".NDXP1", ".NDXP2"}
    assert (q["NDXP1"].bid, q["NDXP1"].ask, q["NDX"].last) == (70.0, 76.0, 30005.0)
    from paper.providers import now_et
    assert abs((q["NDXP1"].updated - now_et()).total_seconds()) < 5   # a live stream's quote stands now, not at 10:50
    assert p.quote_vertical("call", 29900.0, 30000.0, q, datetime.now()) is not None


def test_a_leg_the_stream_has_not_sent_yet_costs_one_rest_call_at_most_every_5_s(sdk):
    clk = Clock()
    p, fs = _provider(sdk, clk)
    fs.book = {"NDX": LegQuote("NDX", None, None, 30005.0, None, None)}
    q = p.fetch(["NDXP1"])
    assert sdk["fetches"] == 1 and q["NDXP1"].bid == 1.0
    p.fetch(["NDXP1"]); assert sdk["fetches"] == 1                 # within 5 s: what the stream has, nothing more
    clk.t += 6
    p.fetch(["NDXP1"]); assert sdk["fetches"] == 2


def test_a_dead_stream_falls_back_to_rest_once_a_minute_and_the_settlement_always_reads_rest(sdk):
    clk = Clock()
    p, fs = _provider(sdk, clk)
    fs.ok = False
    p.fetch(["NDXP1"]); assert sdk["fetches"] == 1
    clk.t += 30
    q = p.fetch(["NDXP1"]); assert sdk["fetches"] == 1 and q["NDXP1"].bid == 1.0     # the last quotes in hand
    clk.t += 31
    p.fetch(["NDXP1"]); assert sdk["fetches"] == 2
    fs.ok = True
    fs.book = {"NDX": LegQuote("NDX", None, None, 1.0, None, None)}
    assert p.index_last() == 30001.0 and sdk["fetches"] == 3        # REST, not the stream's last trade


def test_without_stream_nothing_changes(sdk):
    p = TastytradeProvider("NDX", "NDXP")
    p.budget.take = lambda *a, **k: None
    p.load_chain(date(2026, 10, 6))
    assert p._stream is None
    p.fetch(["NDXP1"]); p.fetch(["NDXP1"])
    assert sdk["fetches"] == 2


def test_the_clone_arms_with_a_2_second_poll_on_the_stream_and_no_one_else_streams():
    from pathlib import Path
    from api.services import arms as A
    cmd = A.task_command("ndx_0dte_friend_real", Path("D:/checkout"))
    assert "-Strategy ndx_0dte_friend_real -Poll 2 -Stream" in cmd
    for slug, spec in A.SPECS.items():
        if slug != "ndx_0dte_friend_real":
            assert not spec.stream and "-Stream" not in (A.task_command(slug, Path("D:/c")) if spec.kind == "script" else "")
