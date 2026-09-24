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
for _p in (str(REPO), str(REPO.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

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
    assert p.supports(occ)                                          # not seen yet: it may
    snap = [{"details": {"ticker": "O:" + occ, "strike_price": 700, "contract_type": "call"},
             "day": {"close": 5.0}, "greeks": {"delta": 0.5}, "implied_volatility": 0.2}]
    monkeypatch.setattr(p, "_snapshot", lambda *a, **k: snap)
    got = p.poll([occ])
    assert got[occ]["fields"]["iv"] == 0.2 and got[occ]["fields"]["bid"] is None
    assert p.option_quotes is False and not p.supports(occ) and "no bid/ask" in p.limits.detail
