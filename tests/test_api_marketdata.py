"""
The market-data hub (api/marketdata): limits and backoff, the request gate hooks, symbol spelling,
one upstream subscription per symbol, fallback between providers, throttled fan-out, snapshots,
the option chain, WS /api/stream and the market endpoints — all with fake providers. Nothing here
opens a broker connection or sends a request to a data vendor.
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import json
import sys
import threading
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:      # only the checkout: its parent holds the live alan_trader (conftest binds ours by path)
    sys.path.insert(0, str(REPO))

from api.bootstrap import bootstrap  # noqa: E402

bootstrap()

from api.marketdata import symbols as SYM  # noqa: E402
from api.marketdata.cache import TTLCache  # noqa: E402
from api.marketdata.hub import MarketDataHub  # noqa: E402
from api.marketdata.limits import CONNECTED, DEGRADED, DOWN, Gate, ProviderLimits, ProviderPolicy, TokenBucket  # noqa: E402
from api.marketdata.providers.base import Provider  # noqa: E402
from data import request_gate  # noqa: E402
from data.request_gate import ProviderUnavailable  # noqa: E402


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


# ── limits ────────────────────────────────────────────────────────────────────

def test_token_bucket_waits_for_a_token_and_refuses_a_long_wait():
    clk = Clock()
    b = TokenBucket(60, 2, clock=clk, sleep=clk.sleep)          # one a second, two banked
    assert b.take() == 0 and b.take() == 0
    assert b.take() == pytest.approx(1.0)                         # slept for the next one
    with pytest.raises(TimeoutError):
        b.take(max_wait=0.1)


def test_backoff_after_429_then_recovery_and_4xx_does_not_back_off():
    clk = Clock()
    lim = ProviderLimits(ProviderPolicy("polygon", per_min=600, per_day=100, burst=50), clock=clk, sleep=clk.sleep)
    g = Gate([])
    g.providers["polygon"] = lim
    g.acquire("polygon")
    g.record("polygon", 404)                                      # an unknown ticker: the request's fault
    assert lim.state() == CONNECTED and lim.last_error.startswith("404")
    g.record("polygon", 429)
    assert lim.state() == DEGRADED
    with pytest.raises(ProviderUnavailable) as e:
        g.acquire("polygon")
    assert e.value.retry_after == pytest.approx(15.0)
    clk.t += 16
    g.acquire("polygon")
    g.record("polygon", 503)                                      # second failure with no success between: 30 s
    with pytest.raises(ProviderUnavailable) as e:
        g.acquire("polygon")
    assert e.value.retry_after == pytest.approx(30.0)
    clk.t += 31
    g.acquire("polygon")
    g.record("polygon", 200)
    assert lim.state() == CONNECTED and lim.failures == 0


def test_daily_budget_marks_the_provider_down():
    clk = Clock()
    lim = ProviderLimits(ProviderPolicy("fred", per_min=6000, per_day=3, burst=10), clock=clk, sleep=clk.sleep)
    for _ in range(3):
        lim.acquire()
    assert lim.budget_remaining() == 0 and lim.state() == DOWN
    with pytest.raises(ProviderUnavailable, match="budget"):
        lim.acquire()
    snap = lim.snapshot()
    assert {"name", "state", "requests_last_min", "budget_remaining", "last_error", "detail"} <= set(snap)
    assert snap["requests_last_min"] == 3


def test_request_gate_hooks_count_every_requests_call(monkeypatch):
    import requests
    from requests.adapters import HTTPAdapter
    from requests.models import Response

    request_gate.uninstall_hooks()
    seen = []

    def fake_send(self, request, *a, **k):                        # never on the network
        seen.append(request.url)
        r = Response()
        r.status_code = 429 if "throttle" in request.url else 200
        r._content = b"{}"
        r.url = request.url
        return r

    monkeypatch.setattr(HTTPAdapter, "send", fake_send)
    gate = Gate()
    request_gate.install(gate)
    request_gate.install_hooks()
    try:
        requests.get("https://api.polygon.io/v3/snapshot/options/SPY?apiKey=x")
        requests.get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10")
        requests.get("https://example.com/not-a-vendor")
        assert gate["polygon"].calls_today == 1 and gate["fred"].calls_today == 1
        requests.get("https://api.polygon.io/v2/throttle")
        assert gate["polygon"].state() == DEGRADED
        with pytest.raises(ProviderUnavailable):
            requests.get("https://api.polygon.io/v2/anything")
        assert len(seen) == 4                                     # the refused call never left
    finally:
        request_gate.install(None)
        request_gate.uninstall_hooks()
    assert request_gate.provider_for_url("https://query2.finance.yahoo.com/v8/finance/chart/SPY") == "yfinance"
    assert request_gate.polygon_kind("https://api.polygon.io/v2/aggs/ticker/O:SPY261030C00770000/range") == "options"
    assert request_gate.polygon_kind("https://api.polygon.io/v2/aggs/grouped/locale/us/market/stocks/x") == "stocks"


# ── symbols / cache ───────────────────────────────────────────────────────────

def test_symbol_spellings():
    assert SYM.normalize(" spy ") == "SPY" and SYM.normalize("^VIX") == "VIX" and SYM.normalize("I:SPX") == "SPX"
    assert SYM.normalize("O:SPY261030C00770000") == "SPY261030C00770000"
    assert SYM.normalize("SPY   261030C00770000") == "SPY261030C00770000"
    o = SYM.parse_option("SPXW261030P05812500")
    assert (o.underlying, o.expiry, o.right, o.strike) == ("SPX", _dt.date(2026, 10, 30), "P", 5812.5)
    assert o.streamer == ".SPXW261030P5812.5" and o.polygon == "O:SPXW261030P05812500"
    assert SYM.from_streamer(".SPY261030C770") == "SPY261030C00770000"
    assert SYM.to_yfinance("VIX") == "^VIX" and SYM.to_yfinance("BRK.B") == "BRK-B"
    with pytest.raises(ValueError):
        SYM.normalize("not a symbol!")


def test_ttl_cache_loads_once_for_concurrent_callers_and_remembers_no_data():
    c = TTLCache()
    calls = []
    gate = threading.Event()

    def slow():
        calls.append(1)
        gate.wait(2)
        return 42

    out = []
    ts = [threading.Thread(target=lambda: out.append(c.get_or_load("k", 10, slow))) for _ in range(5)]
    for t in ts:
        t.start()
    time.sleep(0.2)
    gate.set()
    for t in ts:
        t.join()
    assert out == [42] * 5 and len(calls) == 1

    class NoData(LookupError):
        pass

    n = []

    def empty():
        n.append(1)
        raise NoData("nothing")

    for _ in range(3):
        with pytest.raises(NoData):
            c.get_or_load("e", 10, empty, cache_errors=(NoData,), error_ttl=30)
    assert len(n) == 1


# ── fakes ─────────────────────────────────────────────────────────────────────

def _limits(name):
    return ProviderLimits(ProviderPolicy(name, per_min=6000, per_day=100000, burst=1000))


class FakeStream(Provider):
    name = "faketasty"
    streaming = True
    capabilities = frozenset({"quotes", "options", "greeks", "chain"})

    def __init__(self):
        super().__init__(_limits(self.name))
        self.connected = True
        self.subs: list[tuple[str, tuple]] = []
        self.want: set[str] = set()
        self.contracts = []

    def supports(self, s):
        return self.connected

    def subscribe(self, syms):
        self.subs.append(("+", tuple(syms)))
        self.want.update(syms)
        for s in syms:                                   # the streamer answers with a quote at once
            if SYM.is_option(s):
                o = SYM.parse_option(s)
                self.emit(s, self.name, time.time(), bid=1.0 + o.strike / 1000, ask=1.2 + o.strike / 1000,
                          iv=0.2, delta=0.5 if o.right == "C" else -0.5, oi=100)

    def unsubscribe(self, syms):
        self.subs.append(("-", tuple(syms)))
        self.want.difference_update(syms)

    def chain_contracts(self, u, expiry):
        return self.contracts if expiry == getattr(self, "expiry", None) else []


class FakePoll(Provider):
    name = "fakeyf"
    streaming = False
    poll_interval = 15.0
    capabilities = frozenset({"quotes", "chain"})

    def __init__(self):
        super().__init__(_limits(self.name))
        self.polls: list[list[str]] = []

    def supports(self, s):
        return True

    def poll(self, syms):
        self.polls.append(list(syms))
        return {s: {"fields": {"last": 100.0, "prev_close": 98.0, "volume": 1000}, "time": None} for s in syms}

    def expirations(self, u, spot=None):
        return [_dt.date.today() + _dt.timedelta(days=d) for d in (3, 10, 31)]

    def chain(self, u, expiry, spot, n):
        from api.marketdata.providers.polygon import pick_strikes
        by_k = {float(k): {"call": {"bid": 1.0, "ask": 1.1, "last": 1.05, "iv": 0.2, "delta": 0.5, "gamma": 0.01,
                                    "theta": -0.02, "vega": 0.1, "oi": 10, "volume": 5, "symbol": f"C{k}"},
                           "put": {"bid": 2.0, "ask": 2.2, "symbol": f"P{k}"}} for k in range(80, 121)}
        return {"rows": pick_strikes(by_k, spot, n), "source": self.name}


def _run(coro):
    return asyncio.run(coro)


# ── the hub ───────────────────────────────────────────────────────────────────

def test_one_upstream_subscription_per_symbol_and_release_on_last_watcher():
    async def go():
        st = FakeStream()
        hub = MarketDataHub(Gate([]), [st])
        hub.start()
        hub.watch("a", ["spy"])
        hub.watch("b", ["SPY"])
        hub.unwatch("a", ["SPY"])
        assert st.subs == [("+", ("SPY",))]
        hub.unwatch("b", ["SPY"])
        assert st.subs[-1] == ("-", ("SPY",)) and not st.want
        await hub.stop()
    _run(go())


def test_wait_for_checks_on_its_own_clock_not_on_every_quote_update():
    # a big chain's updates notify the hub's condition thousands of times a second; a scan per update under the
    # lock starved the API at every GEX half hour (2026-10-16)
    hub = MarketDataHub(Gate([]), [])
    calls, stop = [], threading.Event()

    def flood():
        i = 0
        while not stop.is_set():
            hub.emit(f"SPXW{i % 500}", "fake", None, bid=1.0, ask=1.1)
            i += 1

    t = threading.Thread(target=flood, daemon=True)
    t.start()
    try:
        assert hub.wait_for(lambda: bool(calls.append(1)), 0.6, poll=0.2) is False
    finally:
        stop.set()
        t.join()
    assert 2 <= len(calls) <= 5                       # one check per poll, not one per update
    assert hub.wait_for(lambda: True, 5.0) is True


def test_a_chain_still_filling_is_waited_for_and_a_stalled_one_is_not():
    # the streamer subscribes ~100 option symbols a second, so a big chain fills over many seconds (2026-10-20)
    from api.marketdata.options import wait_filling
    hub = MarketDataHub(Gate([]), [])
    n, stop = {"v": 0}, threading.Event()

    def fill(upto, every):
        for _ in range(upto):
            if stop.wait(every):
                return
            with hub._lock:
                n["v"] += 1

    def run(upto, every, target, stall, cap):
        n["v"] = 0
        stop.clear()
        t = threading.Thread(target=fill, args=(upto, every), daemon=True)
        t.start()
        t0 = time.monotonic()
        try:
            return wait_filling(hub, lambda: n["v"] >= target, lambda: n["v"], stall=stall, cap=cap), \
                time.monotonic() - t0
        finally:
            stop.set()
            t.join()

    ok, took = run(10, 0.1, 10, stall=0.3, cap=5.0)    # fills over ~1 s, past one 0.3 s stall window
    assert ok and took < 3.0
    ok, took = run(5, 0.05, 10, stall=0.3, cap=5.0)    # stops at half: given up a stall after the last fill
    assert not ok and took < 2.0
    ok, took = run(1000, 0.05, 1000, stall=0.3, cap=0.6)   # still filling at the cap: given up at the cap
    assert not ok and took < 2.0


def test_streamer_sends_one_capped_chunk_at_a_time_oldest_first_and_drops_last(monkeypatch):
    # a GEX pass wants up to ~1,800 contracts a ticker; sent at 250 symbols a second it cut the stream at most half
    # hours (10:00 on 10/12, 10/13, 10/19, 10/20)
    from api.marketdata.providers import tastytrade as T
    monkeypatch.setattr(T, "SUB_PACE_S", 0.0)
    monkeypatch.setattr(T, "SUB_CHUNK", 100)
    monkeypatch.setattr(T, "SUB_BURST", 10 ** 6)                # the order only: the bucket has its own test
    p = T.TastytradeProvider(ProviderLimits(ProviderPolicy("tastytrade", per_min=600, per_day=100, burst=50)))
    sent: list[tuple[str, str, list]] = []

    class St:
        async def subscribe(self, cls, syms):
            sent.append(("+", cls.__name__, list(syms)))

        async def unsubscribe(self, cls, syms):
            sent.append(("-", cls.__name__, list(syms)))

    gex = [f"SPY261120C{770000 + 1000 * i:08d}" for i in range(250)]
    p.subscribe(gex)                                         # the big pass first ...
    p.subscribe(["NDXP261020P29500000", "NDX"])              # ... then the desk's contract and its index
    have: set[str] = set()
    since: dict[str, float] = {}

    async def step():
        before = len(sent)
        more = await p._step(St(), have, since)
        return more, sent[before:]

    async def go():
        chunks = []
        while True:
            more, msgs = await step()
            if not more:
                assert msgs == []
                return chunks
            chunks.append(msgs)

    chunks = asyncio.run(go())
    assert len(chunks) == 3                                  # 252 symbols: 100 + 100 + 52, one chunk per step
    for msgs in chunks:
        assert {m[1] for m in msgs} == {"Quote", "Trade", "Summary", "Greeks"}
        assert all(len(m[2]) <= T.SUB_CHUNK for m in msgs)
    quotes = [s for msgs in chunks for m in msgs if m[1] == "Quote" for s in m[2]]
    assert quotes[0] == "NDX"                                # the index before any option
    assert quotes[-1] == SYM.to_streamer("NDXP261020P29500000")   # the newer request after the older pass
    assert quotes[1:251] == [SYM.to_streamer(s) for s in gex]
    assert have == set(gex) | {"NDX", "NDXP261020P29500000"}

    p.unsubscribe(gex)                                       # dropped: nothing goes out inside the grace
    more, msgs = asyncio.run(step())
    assert not more and msgs == []
    monkeypatch.setattr(T, "UNSUB_GRACE_S", 0.0)
    more, msgs = asyncio.run(step())                         # past the grace: one chunk of drops
    assert more and {m[0] for m in msgs} == {"-"} and all(len(m[2]) <= T.SUB_CHUNK for m in msgs)
    p.subscribe(["QQQ"])                                     # a new request goes ahead of the drops left
    more, msgs = asyncio.run(step())
    assert more and [m[:2] for m in msgs] == [("+", "Quote"), ("+", "Trade"), ("+", "Summary")]
    assert msgs[0][2] == ["QQQ"]
    drops = 0
    while True:                                              # then the drops left, a chunk a step
        more, msgs = asyncio.run(step())
        if not more:
            break
        drops += 1
        assert {m[0] for m in msgs} == {"-"}
    assert drops == 2 and have == {"NDX", "NDXP261020P29500000", "QQQ"}


def test_streamer_spends_a_token_bucket_and_halves_it_after_a_rate_cut(monkeypatch, caplog):
    # the rule is unpublished and a per-second cap still tripped (10/20 16:11, ~5,000 symbols in 97 s): no minute may
    # carry more than SUB_BURST + sub_budget, a cut halves the refill, a clean hour earns a quarter back
    from api.marketdata.providers import tastytrade as T
    monkeypatch.setattr(T, "SUB_PACE_S", 0.0)
    monkeypatch.setattr(T, "SUB_CHUNK", 100)
    monkeypatch.setattr(T, "SUB_BURST", 300)
    monkeypatch.setattr(T, "SUB_MIN_SEND", 50)
    monkeypatch.setattr(T, "SUB_BUDGET", 600)                   # 10 symbols a second
    monkeypatch.setattr(T, "SUB_BUDGET_MIN", 200)
    clock = {"t": 1000.0}
    p = T.TastytradeProvider(ProviderLimits(ProviderPolicy("tastytrade", per_min=600, per_day=100, burst=50)))
    p._clock = lambda: clock["t"]
    p._tok_at = p._budget_at = clock["t"]
    sizes: list[int] = []

    class St:
        async def subscribe(self, cls, syms):
            if cls.__name__ == "Quote":
                sizes.append(len(syms))

        async def unsubscribe(self, cls, syms):
            pass

    p.subscribe([f"SPY261120C{700000 + 1000 * i:08d}" for i in range(1000)])
    have: set[str] = set()

    def step():
        return asyncio.run(p._step(St(), have, {}))

    assert [step(), step(), step(), step()] == [True, True, True, None]   # the 300 burst, then wait
    assert sizes == [100, 100, 100] and p.sent_within(60) == 300
    clock["t"] += 3.0                                                     # 30 tokens: under the 50 minimum
    assert step() is None
    clock["t"] += 3.0                                                     # 60: send what the bucket affords
    assert step() is True and sizes[-1] == 60
    clock["t"] += 60.0                                                    # a minute: 600 back, capped at the 300 burst
    assert step() is True and step() is True and step() is True and step() is None
    assert sizes[-3:] == [100, 100, 100] and p.sent_within(60) == 300 and p.sent_within(300) == 660

    with caplog.at_level("WARNING", logger="alan_trader.api.marketdata.tastytrade"):
        p._rate_cut()                                                     # DXLink cut us: halve, empty, log
    assert p.sub_budget == 300 and p.rate_cuts == 1 and step() is None
    assert "sent 300 symbols in 10 s, 300 in 60 s, 660 in 300 s" in caplog.text
    p._rate_cut()
    p._rate_cut()
    assert p.sub_budget == 200                                            # not below SUB_BUDGET_MIN
    assert p.status_detail()["sub_budget"] == 200 and p.status_detail()["rate_cuts"] == 3
    clock["t"] += T.SUB_RECOVER_S                                         # a clean hour: a quarter back
    step()
    assert p.sub_budget == 250
    for _ in range(10):
        clock["t"] += T.SUB_RECOVER_S
        step()
    assert p.sub_budget == 600                                            # never above SUB_BUDGET


def test_fallback_to_polling_and_back_when_the_streamer_reconnects():
    async def go():
        st, pl = FakeStream(), FakePoll()
        st.connected = False
        hub = MarketDataHub(Gate([]), [st, pl])
        hub.start()
        hub.watch("a", ["QQQ"])
        assert hub.route["QQQ"] == "fakeyf"
        for _ in range(30):
            await asyncio.sleep(0.05)
            if pl.polls:
                break
        assert pl.polls and pl.polls[0] == ["QQQ"]
        assert hub.quotes["QQQ"].values["last"] == 100.0
        st.connected = True                              # the streamer comes back
        await asyncio.sleep(1.3)                         # next tick re-routes
        assert hub.route["QQQ"] == "faketasty" and ("+", ("QQQ",)) in st.subs
        await hub.stop()
    _run(go())


def test_live_quotes_can_be_limited_to_the_broker_feed():
    """With live_quotes set, a feed outside it never prices a live symbol, even while the streamer is down: the
    symbol waits for the stream instead of taking a delayed quote (2026-09-29: mixed feeds inside one spread)."""
    async def go():
        st, pl = FakeStream(), FakePoll()
        st.connected = False
        hub = MarketDataHub(Gate([]), [st, pl], live_quotes=["faketasty"])
        hub.start()
        hub.watch("a", ["QQQ"])
        assert "QQQ" not in hub.route                    # nothing may serve it: the poller is not a live source
        await asyncio.sleep(0.3)
        assert not pl.polls
        st.connected = True
        await asyncio.sleep(1.3)
        assert hub.route["QQQ"] == "faketasty"
        await hub.stop()
    _run(go())


def test_the_service_defaults_live_quotes_to_tastytrade(monkeypatch):
    from api.marketdata import service as S
    monkeypatch.delenv("ALAN_TRADER_LIVE_QUOTES", raising=False)
    assert S.live_quote_providers() == ["tastytrade"]
    monkeypatch.setenv("ALAN_TRADER_LIVE_QUOTES", "all")
    assert S.live_quote_providers() is None


def test_fan_out_is_throttled_to_four_messages_a_second_per_symbol():
    async def go():
        st = FakeStream()
        hub = MarketDataHub(Gate([]), [st])
        hub.start()
        c = hub.connect()
        while not c.queue.empty():                       # provider statuses on connect
            c.queue.get_nowait()
        hub.client_subscribe(c, ["IWM"])
        t0 = time.monotonic()
        for i in range(200):                              # 200 updates over ~1 s
            hub.emit("IWM", "faketasty", None, bid=100 + i * 0.01, ask=100.1 + i * 0.01)
            await asyncio.sleep(0.005)
        await asyncio.sleep(0.3)
        msgs = []
        while not c.queue.empty():
            msgs.append(c.queue.get_nowait())
        quotes = [m for m in msgs if m.get("type") == "quote"]
        elapsed = time.monotonic() - t0
        assert 2 <= len(quotes) <= 4 * elapsed + 2
        assert quotes[-1]["bid"] == pytest.approx(101.99)     # the latest state wins
        hub.disconnect(c)
        await hub.stop()
    _run(go())


def test_snapshot_polls_a_new_symbol_once_and_serves_the_cache_after():
    async def go():
        pl = FakePoll()
        hub = MarketDataHub(Gate([]), [pl])
        hub.start()
        got = await asyncio.to_thread(hub.snapshot, ["DIA", "bad sym!"], 3.0)
        assert got[0]["symbol"] == "DIA" and got[0]["last"] == 100.0 and got[0]["change"] == pytest.approx(2.0)
        assert got[1]["last"] is None and "error" in got[1]
        n = len(pl.polls)
        again = await asyncio.to_thread(hub.snapshot, ["DIA"], 3.0)
        assert again[0]["last"] == 100.0 and len(pl.polls) == n
        await hub.stop()
    _run(go())


def test_chains_from_a_polling_provider_and_from_the_streamer():
    from api.marketdata import options as O

    async def go():
        pl = FakePoll()
        hub = MarketDataHub(Gate([]), [pl])
        hub.start()
        hub.emit("XYZ", "fakeyf", None, last=100.0)
        exp = (_dt.date.today() + _dt.timedelta(days=10)).isoformat()
        e = await asyncio.to_thread(O.expirations, hub, "XYZ")
        assert e["underlying"] == "XYZ" and [x["dte"] for x in e["expirations"]] == [3, 10, 31]
        ch = await asyncio.to_thread(O.chain, hub, "XYZ", exp, 5)
        fields = [c["field"] for c in ch["table"]["columns"]]
        assert fields[0] == "strike" and "call_mid" in fields and "put_symbol" in fields and "put_iv" in fields
        ks = [r["strike"] for r in ch["table"]["rows"]]       # 5 at or below spot, 5 above
        assert ks == [96.0, 97.0, 98.0, 99.0, 100.0, 101.0, 102.0, 103.0, 104.0, 105.0]
        assert ch["table"]["rows"][0]["call_mid"] == pytest.approx(1.05) and ch["source"] == "fakeyf"
        await hub.stop()

        st = FakeStream()
        exp_d = st.expiry = _dt.date.today() + _dt.timedelta(days=10)
        st.contracts = [(float(k), SYM.make_option("XYZ", exp_d, "C", k).occ, SYM.make_option("XYZ", exp_d, "P", k).occ)
                        for k in range(90, 111)]
        hub2 = MarketDataHub(Gate([]), [st])
        hub2.start()
        hub2.emit("XYZ", "faketasty", None, bid=99.9, ask=100.1)
        ch2 = await asyncio.to_thread(O.chain, hub2, "XYZ", exp_d.isoformat(), 2)
        rows = ch2["table"]["rows"]
        assert [r["strike"] for r in rows] == [99.0, 100.0, 101.0, 102.0] and ch2["source"] == "faketasty"
        assert rows[0]["call_delta"] == 0.5 and rows[0]["put_delta"] == -0.5 and rows[0]["call_oi"] == 100
        assert rows[0]["call_symbol"] == "XYZ" + exp_d.strftime("%y%m%d") + "C00099000"
        with pytest.raises(O.NoChain):
            await asyncio.to_thread(O.chain, hub2, "XYZ", (exp_d + _dt.timedelta(days=1)).isoformat(), 2)
        await hub2.stop()
    _run(go())


def test_broker_budget_counts_runners_elsewhere_and_never_writes_there(tmp_path):
    from api.marketdata.providers.tastytrade import ServiceBrokerBudget
    ext = tmp_path / "other_checkout" / "paper_state"
    ext.mkdir(parents=True)
    f = ext / f"broker_calls_{_dt.date.today().isoformat()}.json"
    f.write_text(json.dumps({"date": _dt.date.today().isoformat(), "calls": 2999}), encoding="utf-8")
    before = f.stat().st_mtime_ns
    b = ServiceBrokerBudget(tmp_path / "mine", [ext], per_day=3000, min_interval_s=0)
    assert b.remaining() == 1
    b.take()
    assert b.remaining() == 0
    with pytest.raises(ProviderUnavailable, match="budget"):
        b.take()
    assert f.stat().st_mtime_ns == before and json.loads(f.read_text())["calls"] == 2999
    assert json.loads((tmp_path / "mine" / f.name).read_text())["calls"] == 1


# ── the endpoints ─────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from api.app import create_app
    from api.bootstrap import uninstall_db_read_only_guard
    app = create_app()
    try:
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c
    finally:
        uninstall_db_read_only_guard()


def test_stream_subscribe_quote_unsubscribe(client):
    hub = client.app.state.market
    st = FakeStream()
    hub.add_provider(st, first=True)
    try:
        with client.websocket_connect("/api/stream") as ws:
            statuses = [ws.receive_json()]
            assert statuses[0]["type"] == "status" and statuses[0]["provider"] == "faketasty"
            ws.send_text(json.dumps({"op": "subscribe", "symbols": ["SPY", "O:SPY261030C00770000", "??"]}))
            ack = ws.receive_json()
            while ack["type"] != "subscribed":                    # the option's first quote may come first
                ack = ws.receive_json()
            assert ack == {"type": "subscribed", "symbols": ["SPY", "SPY261030C00770000"], "rejected": ["??"]}
            assert ("+", ("SPY",)) in st.subs
            hub.emit("SPY", "faketasty", time.time(), bid=500.0, ask=500.2, last=500.1, prev_close=495.0, volume=10)
            while True:
                m = ws.receive_json()
                if m["type"] == "quote" and m["symbol"] == "SPY":
                    break
            assert set(m) >= {"type", "symbol", "bid", "ask", "last", "mid", "prev_close", "change", "change_pct",
                              "volume", "time", "source"}
            assert m["mid"] == pytest.approx(500.1) and m["change"] == pytest.approx(5.1) and m["source"] == "faketasty"
            ws.send_text(json.dumps({"op": "unsubscribe", "symbols": ["SPY"]}))
            while ws.receive_json()["type"] != "unsubscribed":
                pass
            assert st.subs[-1] == ("-", ("SPY",))
        quotes = client.get("/api/market/quotes?symbols=SPY,QQQ").json()["quotes"]
        assert [q["symbol"] for q in quotes] == ["SPY", "QQQ"] and quotes[0]["bid"] == 500.0
        prov = client.get("/api/market/providers").json()
        names = [p["name"] for p in prov]
        assert "faketasty" in names and {"polygon", "yfinance", "fred", "tastytrade"} <= set(names)
        for p in prov:
            assert {"name", "state", "requests_last_min", "budget_remaining", "last_error", "detail"} <= set(p)
        assert client.get("/api/market/quotes?symbols=").status_code == 422
    finally:
        hub.providers.remove(st)
        hub.by_name.pop(st.name, None)


def test_quote_v1_shape_comes_from_the_hub_when_it_can(client):
    hub = client.app.state.market
    st = FakeStream()
    hub.add_provider(st, first=True)
    try:
        hub.emit("TLT", "faketasty", time.time(), bid=90.0, ask=90.1, last=90.05, prev_close=89.0)
        q = client.get("/api/market/quote/TLT").json()
        assert q["ticker"] == "TLT" and q["close"] == 90.05 and q["source"] == "faketasty" and q["live"] is True
        assert q["bid"] == 90.0 and q["change"] == pytest.approx(1.05)
    finally:
        hub.providers.remove(st)
        hub.by_name.pop(st.name, None)


def test_option_endpoints_validate_and_report_no_chain(client):
    r = client.get("/api/options/SPY/chain?expiry=2020-01-17")
    assert r.status_code == 422 and "expired" in r.json()["detail"]
    r = client.get("/api/options/SPY/chain?expiry=soon")
    assert r.status_code == 422
    r = client.get("/api/options/SPY/expirations")           # no provider under test: a clean 422
    assert r.status_code == 422 and "SPY" in r.json()["detail"]


def test_one_streamer_per_checkout_across_processes(tmp_path):
    from api.marketdata.providers.tastytrade import StreamerLock
    a, b = StreamerLock(tmp_path / "tt.lock"), StreamerLock(tmp_path / "tt.lock")
    b.pid = a.pid + 1_000_000                           # "another process"
    assert a.acquire() and a.acquire()                  # re-entrant for its holder
    assert not b.acquire()                              # the holder (this test process) is alive
    a.release()
    assert b.acquire() and b.holder()["pid"] == b.pid
    (tmp_path / "tt.lock").write_text(json.dumps({"pid": 2_000_000_000}), encoding="utf-8")   # a dead holder
    assert a.acquire() and a.holder()["pid"] == a.pid   # stale lock taken over
    b.release()                                         # not b's: left alone
    assert (tmp_path / "tt.lock").exists()


def test_polygon_leaves_option_quotes_to_the_next_provider_when_its_plan_has_none(monkeypatch):
    from api.marketdata.providers.polygon import PolygonProvider
    p = PolygonProvider(_limits("polygon"), api_key="k")
    occ = SYM.make_option("SPY", _dt.date.today() + _dt.timedelta(days=30), "C", 700).occ
    assert not p.supports(occ)                                      # not seen yet: quotes go elsewhere
    snap = [{"details": {"ticker": "O:" + occ, "strike_price": 700, "contract_type": "call"},
             "day": {"close": 5.0}, "greeks": {"delta": 0.5}, "implied_volatility": 0.2}]
    monkeypatch.setattr(p, "_snapshot", lambda *a, **k: snap)
    got = p.poll([occ])
    assert got[occ]["fields"]["iv"] == 0.2 and got[occ]["fields"]["bid"] is None
    assert p.option_quotes is False and not p.supports(occ) and "no bid/ask" in p.limits.detail
    p2 = PolygonProvider(_limits("polygon"), api_key="k")
    p2._note_quotes([{"last_quote": {"bid": 1.0, "ask": 1.1}}])    # a plan with quotes
    assert p2.option_quotes is True and p2.supports(occ)


# ── the IV surface ────────────────────────────────────────────────────────────

def _synthetic_chain(today, spot=100.0):
    """Puts 10% vol + 0.1 per strike below spot, calls 20% flat: the OTM choice is visible in the numbers."""
    out = []
    for d in (7, 30, 400):                                   # 400 days: beyond max_dte
        e = today + _dt.timedelta(days=d)
        for k in range(90, 111, 5):                          # listed 90..110 only
            out.append({"expiry": e, "strike": float(k), "type": "put", "iv": 0.10 + (100 - k) * 0.01})
            out.append({"expiry": e, "strike": float(k), "type": "call", "iv": 0.20})
    e = today + _dt.timedelta(days=14)                       # an expiry with too few contracts
    out.append({"expiry": e, "strike": 95.0, "type": "put", "iv": 0.3})
    out.append({"expiry": e, "strike": 105.0, "type": "call", "iv": None})
    return out


def test_iv_surface_grid_otm_choice_and_no_extrapolation():
    from api.marketdata.surface import build_surface, moneyness_grid, pick_expiries
    today = _dt.date(2026, 9, 24)
    grid = moneyness_grid(0.80, 1.20, 0.05)
    assert grid == [0.8, 0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.15, 1.2]
    s = build_surface(_synthetic_chain(today), 100.0, grid, 180, today=today, include_today=True)
    assert [x["dte"] for x in s["expiries"]] == [7, 30]      # 400-day expiry out; 14-day one too thin
    assert len(s["iv"]) == 2 and all(len(r) == len(grid) for r in s["iv"])
    row = s["iv"][0]
    assert row[0] is None and row[1] is None and row[-1] is None and row[-2] is None     # 80-85%, 115-120%: unlisted
    assert row[2] == pytest.approx(20.0)                     # K=90: put, 10% + 10 x 1%
    assert row[3] == pytest.approx(15.0)                     # K=95: put
    assert row[4] == pytest.approx((10.0 + 20.0) / 2)        # K=100: both sides averaged
    assert row[5] == pytest.approx(20.0) and row[6] == pytest.approx(20.0)    # calls above spot
    assert s["atm_iv"] == [pytest.approx(15.0), pytest.approx(15.0)]
    fine = build_surface(_synthetic_chain(today), 100.0, moneyness_grid(0.9, 1.1, 0.025), 180, today=today)
    zero = [dict(c, expiry=today) for c in _synthetic_chain(today) if c["expiry"] == today + _dt.timedelta(days=7)]
    assert [x["dte"] for x in build_surface(zero, 100.0, grid, 180, today=today, include_today=False)["expiries"]] == []
    assert [x["dte"] for x in build_surface(zero, 100.0, grid, 180, today=today, include_today=True)["expiries"]] == [0]
    assert fine["iv"][0][1] == pytest.approx(17.5)           # K=92.5 interpolated between the 90 and 95 puts
    many = [today + _dt.timedelta(days=d) for d in range(1, 60)]
    picked = pick_expiries(many)
    assert len(picked) == 24 and picked[:12] == many[:12] and picked[-1] == many[-1] and picked == sorted(picked)
    with pytest.raises(ValueError):
        moneyness_grid(1.1, 1.2, 0.01)


def test_iv_surface_endpoint_from_a_snapshot_provider(client):
    hub = client.app.state.market

    class FakePolygon(Provider):
        name = "polygon"
        streaming = False
        capabilities = frozenset({"quotes", "chain"})

        def __init__(self):
            super().__init__(_limits("polygon"))
            self.calls = 0

        def supports(self, s):
            return not SYM.is_option(s)

        def poll(self, syms):
            return {s: {"fields": {"last": 100.0}, "time": None} for s in syms}

        def surface_contracts(self, u, spot, max_dte, lo, hi):
            self.calls += 1
            return _synthetic_chain(_dt.date.today(), spot)

    fp = FakePolygon()
    hub.add_provider(fp, first=True)
    try:
        hub.emit("ZZSURF", "polygon", None, last=100.0)
        r = client.get("/api/options/ZZSURF/surface?max_dte=180&lo=0.8&hi=1.2&step=0.05")
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["source"] == "polygon" and j["spot"] == 100.0 and len(j["moneyness"]) == 9
        assert [e["dte"] for e in j["expiries"]] == [7, 30] and j["iv"][0][4] == pytest.approx(15.0)
        again = client.get("/api/options/ZZSURF/surface?max_dte=180&lo=0.8&hi=1.2&step=0.01").json()
        assert len(again["moneyness"]) == 41 and fp.calls == 1                  # one snapshot, cached
        assert client.get("/api/options/ZZSURF/surface?lo=1.1").status_code == 422
    finally:
        hub.providers.remove(fp)
        hub.by_name.pop(fp.name, None)


# ── the merged chain: quotes and greeks from different providers ─────────────

class _ChainFake(Provider):
    streaming = False
    capabilities = frozenset({"quotes", "chain"})

    def __init__(self, name, ranks, rows_fn, option_quotes=None):
        self.name = name
        super().__init__(_limits(name))
        self.chain_ranks = ranks
        self.rows_fn = rows_fn
        self.option_quotes = option_quotes
        self.calls = 0

    def supports(self, s):
        return not SYM.is_option(s)

    def poll(self, syms):
        return {s: {"fields": {"last": 100.0}, "time": None} for s in syms}

    def chain(self, u, expiry, spot, n):
        self.calls += 1
        from api.marketdata.providers.polygon import pick_strikes
        return {"rows": pick_strikes(self.rows_fn(expiry), spot, n), "source": self.name}


def test_chain_quotes_and_greeks_are_merged_across_providers(monkeypatch):
    from api.marketdata import options as O
    exp = _dt.date.today() + _dt.timedelta(days=20)

    def poly_rows(e):          # greeks, IV, OI; no bid/ask (the plan here)
        return {float(k): {"call": {"bid": None, "ask": None, "last": 1.0, "iv": 0.2, "delta": 0.5, "gamma": 0.01,
                                    "theta": -0.1, "vega": 0.2, "oi": 500, "volume": 10,
                                    "symbol": SYM.make_option("XYZ", e, "C", k).occ},
                           "put": {"bid": None, "ask": None, "iv": 0.25, "delta": -0.5, "oi": 700,
                                   "symbol": SYM.make_option("XYZ", e, "P", k).occ}} for k in range(90, 111)}

    def yf_rows(e):            # bid/ask, its own IV and BS greeks; strikes 95..105 only
        return {float(k): {"call": {"bid": 1.1, "ask": 1.3, "last": 1.2, "iv": 0.3, "delta": 0.45, "oi": 5},
                           "put": {"bid": 0.0, "ask": 0.0, "iv": 0.3}} for k in range(95, 106)}

    async def go():
        poly = _ChainFake("polygon", {"skeleton": 2, "quotes": 2, "greeks": 1, "sizes": 1}, poly_rows, option_quotes=False)
        yf = _ChainFake("yfinance", {"skeleton": 1, "quotes": 1, "greeks": 2, "sizes": 2}, yf_rows)
        hub = MarketDataHub(Gate([]), [poly, yf])
        hub.start()
        hub.emit("XYZ", "yfinance", None, last=100.0)
        monkeypatch.setattr(O, "_market_open", lambda now=None: True)
        ch = await asyncio.to_thread(O.chain, hub, "XYZ", exp.isoformat(), 3)
        rows = {r["strike"]: r for r in ch["table"]["rows"]}
        assert sorted(rows) == [98.0, 99.0, 100.0, 101.0, 102.0, 103.0]
        r = rows[100.0]
        assert (r["call_bid"], r["call_ask"], r["call_mid"]) == (1.1, 1.3, pytest.approx(1.2))
        assert r["call_quote_source"] == "yfinance" and r["call_greeks_source"] == "polygon"
        assert r["call_iv"] == 0.2 and r["call_delta"] == 0.5 and r["call_oi"] == 500     # Polygon's, not yfinance's
        assert r["put_bid"] is None and r["put_mid"] is None and r["put_quote_source"] is None   # 0/0: no quote
        assert r["call_symbol"] == SYM.make_option("XYZ", exp, "C", 100).occ
        assert ch["quote_source"] == "yfinance" and ch["greeks_source"] == "polygon"
        assert ch["source"] == "yfinance" and set(ch["sources"]) == {"yfinance", "polygon"}
        assert ch["quoted"] == 6 and ch["contracts"] == 12 and not ch["stale"]
        assert any("6 of 12" in w for w in ch["warnings"]) and any("delayed" in w for w in ch["warnings"])
        monkeypatch.setattr(O, "_market_open", lambda now=None: False)
        ch2 = await asyncio.to_thread(O.chain, hub, "XYZ", exp.isoformat(), 3)
        assert ch2["stale"] and any("market closed" in w for w in ch2["warnings"])
        assert poly.calls == 1 and yf.calls == 1                                 # cached, and asked once each
        await hub.stop()
    _run(go())


def test_a_patient_job_waits_out_a_backoff_a_request_does_not():
    from api.marketdata.limits import patience
    clk = Clock()
    lim = ProviderLimits(ProviderPolicy("polygon", per_min=600, per_day=100, burst=50), clock=clk, sleep=clk.sleep)
    lim.fail("429 Too Many Requests")                                  # 15 s backoff
    with pytest.raises(ProviderUnavailable):
        lim.acquire()                                                  # a request thread: fails at once
    with patience(60.0):
        lim.acquire()                                                  # a job: sleeps through it
    assert clk.t >= 1015.0 and lim.calls_today == 1
    lim.fail("429"); lim.fail("429"); lim.fail("429")                 # 60 s, then 120 s: beyond the patience
    with patience(60.0):
        with pytest.raises(ProviderUnavailable):
            lim.acquire()
