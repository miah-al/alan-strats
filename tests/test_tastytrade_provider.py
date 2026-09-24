"""TastytradeProvider against a mocked SDK: chain filtering by root, quote row mapping (UTC to ET,
bid/ask/last/last_trade_time), one re-login on an auth error, minute bars from samples. No network."""
from __future__ import annotations

import sys
import types
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest


class _Opt:
    def __init__(self, symbol, root, strike, right, exp):
        self.symbol, self.root_symbol, self.strike_price, self.option_type, self.expiration_date = symbol, root, Decimal(strike), right, exp
        self.streamer_symbol = "." + symbol


class _Row:
    def __init__(self, symbol, bid, ask, last, last_trade_time, updated_at):
        self.symbol, self.bid, self.ask, self.last = symbol, bid, ask, last
        self.last_trade_time, self.updated_at = last_trade_time, updated_at


@pytest.fixture
def fake_sdk(monkeypatch):
    """A tastytrade package with Session, instruments.get_option_chain and market_data.get_market_data_by_type."""
    calls = {"sessions": 0, "fetches": 0, "fail_next": False}

    class Session:
        def __init__(self, secret, refresh, is_test=False):
            calls["sessions"] += 1
            self.args = (secret, refresh, is_test)

    tt = types.ModuleType("tastytrade"); tt.Session = Session
    inst = types.ModuleType("tastytrade.instruments")
    day = date(2026, 9, 17)

    def get_option_chain(session, symbol):
        return {day: [_Opt("NDXP260917C29100000", "NDXP", "29100", "C", day), _Opt("NDXP260917C29200000", "NDXP", "29200", "C", day),
                      _Opt("NDXP260917P29100000", "NDXP", "29100", "P", day), _Opt("NDX260917C29100000", "NDX", "29100", "C", day)]}
    inst.get_option_chain = get_option_chain
    md = types.ModuleType("tastytrade.market_data")

    def get_market_data_by_type(session, indices=None, options=None, **kw):
        calls["fetches"] += 1
        if calls["fail_next"]:
            calls["fail_next"] = False
            raise RuntimeError("401 Unauthorized: token expired")
        utc = datetime(2026, 9, 17, 17, 30, 0)                    # 13:30 ET
        rows = [_Row("NDX", None, None, Decimal("29150.25"), None, utc)]
        for s in options or []:
            rows.append(_Row(s, Decimal("170.0"), Decimal("172.0"), Decimal("171.0"), utc - timedelta(minutes=2), utc))
        return rows
    md.get_market_data_by_type = get_market_data_by_type
    monkeypatch.setitem(sys.modules, "tastytrade", tt)
    monkeypatch.setitem(sys.modules, "tastytrade.instruments", inst)
    monkeypatch.setitem(sys.modules, "tastytrade.market_data", md)
    monkeypatch.setenv("TT_SECRET", "s"); monkeypatch.setenv("TT_REFRESH", "r")
    return calls


def test_chain_quotes_and_bars(fake_sdk):
    from paper.providers import TastytradeProvider
    p = TastytradeProvider("NDX", "NDXP", poll_seconds=15)
    assert fake_sdk["sessions"] == 1
    day = date(2026, 9, 17)
    assert p.load_chain(day) == 3                                   # the AM root NDX is excluded
    assert p.leg_symbols("call", 29100.0, 29200.0) == ("NDXP260917C29100000", "NDXP260917C29200000")
    assert p.leg_symbols("call", 29300.0, 29400.0) == (None, None)  # not in the chain
    q = p.fetch(["NDXP260917C29100000", "NDXP260917C29200000"])
    assert set(q) == {"NDX", "NDXP260917C29100000", "NDXP260917C29200000"}
    leg = q["NDXP260917C29100000"]
    assert (leg.bid, leg.ask, leg.last) == (170.0, 172.0, 171.0)
    assert leg.updated == datetime(2026, 9, 17, 13, 30) and leg.last_time == datetime(2026, 9, 17, 13, 28)   # UTC -> ET, naive
    now = datetime(2026, 9, 17, 13, 30, 10)
    vq = p.quote_vertical("call", 29100.0, 29200.0, q, now)
    assert vq is not None and vq.bid == -2.0 and vq.ask == 2.0 and vq.last == 0.0 and vq.age == 2
    # minute bars from samples
    assert p.sample_underlying(q, datetime(2026, 9, 17, 13, 30, 5)) == 29150.25
    p._samples.append((datetime(2026, 9, 17, 13, 30, 40), 29152.0))
    bar = p.close_minute(datetime(2026, 9, 17, 13, 30))
    assert (bar.open, bar.high, bar.low, bar.close) == (29150.25, 29152.0, 29150.25, 29152.0)
    assert p.close_minute(datetime(2026, 9, 17, 13, 31)) is None


def test_fetch_relogins_once_on_auth_error(fake_sdk):
    from paper.providers import TastytradeProvider
    p = TastytradeProvider("NDX", "NDXP")
    fake_sdk["fail_next"] = True
    q = p.fetch(["NDXP260917C29100000"])
    assert "NDX" in q and fake_sdk["sessions"] == 2 and fake_sdk["fetches"] == 2


def test_missing_credentials_is_a_clean_error(monkeypatch, fake_sdk):
    monkeypatch.delenv("TT_SECRET"); monkeypatch.delenv("TT_REFRESH")
    import engine.env
    monkeypatch.setattr(engine.env, "load_env", lambda *a, **k: False)   # the machine's real .env must not leak in
    from paper.providers import TastytradeProvider
    with pytest.raises(RuntimeError, match="TT_SECRET"):
        TastytradeProvider("NDX", "NDXP")


def test_vertical_quote_carries_its_legs():
    """The vertical's quote keeps the leg quotes and ages it was built from, so the paper log can show
    what the NBBO looked like on each leg at every fill (the print-synchrony question, settled live)."""
    from datetime import datetime, timedelta
    from paper.providers import LegQuote, vertical_quote
    now = datetime(2026, 9, 17, 11, 30)
    long_leg = LegQuote("NDXP260917C29100000", 170.0, 172.0, 171.0, now - timedelta(minutes=2), now)
    short_leg = LegQuote("NDXP260917C29150000", 140.0, 141.0, 140.5, now, now)
    q = vertical_quote(long_leg, short_leg, now)
    assert (q.bid, q.ask, q.last) == (29.0, 32.0, 30.5) and q.age == 2
    assert q.legs == ((170.0, 172.0, 2), (140.0, 141.0, 0))
    assert vertical_quote(LegQuote("x", None, 1.0, None, None, now), short_leg, now) is None


def test_async_sdk_calls_are_awaited(fake_sdk, monkeypatch):
    """tastytrade >= 13 made get_option_chain and get_market_data_by_type coroutines; the provider must
    give the same answers whether the SDK is sync (older SDKs, these fakes) or async."""
    import sys
    from datetime import date
    inst, md = sys.modules["tastytrade.instruments"], sys.modules["tastytrade.market_data"]
    sync_chain, sync_md = inst.get_option_chain, md.get_market_data_by_type

    async def a_chain(session, symbol):
        return sync_chain(session, symbol)

    async def a_md(session, indices=None, options=None, **kw):
        return sync_md(session, indices=indices, options=options, **kw)
    monkeypatch.setattr(inst, "get_option_chain", a_chain); monkeypatch.setattr(md, "get_market_data_by_type", a_md)
    from paper.providers import TastytradeProvider
    p = TastytradeProvider("NDX", "NDXP")
    assert p.load_chain(date(2026, 9, 17)) == 3
    q = p.fetch(["NDXP260917C29100000"])
    assert q["NDXP260917C29100000"].bid == 170.0 and fake_sdk["fetches"] == 1


def test_wrong_secret_is_one_plain_sentence(fake_sdk, monkeypatch):
    """A regenerated OAuth application with the Client ID pasted as the secret: no traceback, no re-login loop."""
    import sys
    from datetime import date
    inst = sys.modules["tastytrade.instruments"]

    def bad_chain(session, symbol):
        raise RuntimeError("Couldn't parse response: {'error_code': 'invalid_grant', 'error_description': 'Client secret mismatch'}")
    monkeypatch.setattr(inst, "get_option_chain", bad_chain)
    from paper.providers import TastytradeProvider
    p = TastytradeProvider("NDX", "NDXP")
    with pytest.raises(RuntimeError) as e:
        p.load_chain(date(2026, 9, 17))
    assert "Client Secret shown once" in str(e.value) and "Client secret mismatch" in str(e.value)
    assert fake_sdk["sessions"] == 1                                # no re-login attempted


def test_near_the_money_vertical_uses_the_chain_grid(fake_sdk):
    from datetime import date
    from paper.providers import TastytradeProvider
    p = TastytradeProvider("NDX", "NDXP"); p.load_chain(date(2026, 9, 17))
    long_sym, short_sym, k_low, k_high = p.near_the_money_vertical(spot=29_174.0, width=100.0, itm_offset=24.0)
    assert (k_low, k_high) == (29_100.0, 29_200.0)
    assert long_sym == "NDXP260917C29100000" and short_sym == "NDXP260917C29200000"


def test_paper_path_never_imports_order_or_account_apis():
    """The paper runner is quotes-only by construction: the only tastytrade modules it touches are the
    session, the option chain and market data. No order, account or trading module, ever."""
    import pathlib, re
    root = pathlib.Path(__file__).resolve().parents[1]
    sources = [root / "paper" / "providers.py", root / "paper" / "runner.py", root / "scripts" / "paper_runner.py"]
    # tastytrade.dxfeed holds the streamed market-data event types (Candle, Quote, Trade, TimeAndSale,
    # Greeks, Profile, Summary, TheoPrice, Underlying) and nothing else -- audited 2026-09-23, when the
    # bar backfill moved from Polygon to the broker's own candle feed. It carries no order, account or
    # execution code; the forbidden-word check below still guards against any of that appearing.
    allowed = {"tastytrade", "tastytrade.instruments", "tastytrade.market_data", "tastytrade.utils", "tastytrade.dxfeed"}
    for src in sources:
        text = src.read_text(encoding="utf-8")
        for mod in re.findall(r"^\s*(?:from|import)\s+(tastytrade[\w.]*)", text, flags=re.M):
            assert mod in allowed, f"{src.name} imports {mod}"
        for word in ("place_order", "new_order", "NewOrder", "submit_order", "OrderAction", "/orders", "get_accounts", "Account.get"):
            assert word not in text, f"{src.name} mentions {word}"


def test_request_budget_floors_spaces_and_caps_calls():
    """No caller can exceed the broker budget: a floor between calls, a per-minute cap, a per-day cap."""
    from paper.providers import RequestBudget
    clock = [1000.0]; slept = []
    b = RequestBudget(min_interval_s=5.0, per_minute=3, per_day=5, clock=lambda: clock[0], sleep=lambda s: (slept.append(s), clock.__setitem__(0, clock[0] + s)))
    b.take(); b.take()                                   # the second call waits out the 5 s floor
    assert slept == [5.0] and b.calls_today == 2
    clock[0] += 5; b.take()                              # third call within the minute: allowed
    clock[0] += 5; b.take()                              # fourth: the per-minute cap makes it wait for the window to roll
    assert slept[-1] > 40 and b.calls_today == 4
    clock[0] += 5; b.take()
    with pytest.raises(RuntimeError, match="budget spent"):
        b.take()                                         # the day's cap: no sleeping, no call, a plain error


def test_provider_counts_every_broker_call_against_the_budget(fake_sdk):
    from datetime import date
    from paper.providers import TastytradeProvider, RequestBudget
    p = TastytradeProvider("NDX", "NDXP")
    p.budget = RequestBudget(min_interval_s=0.0, per_minute=100, per_day=100, clock=lambda: 0.0, sleep=lambda s: None)
    p.load_chain(date(2026, 9, 17)); p.fetch(["NDXP260917C29100000"])
    fake_sdk["fail_next"] = True; p.fetch(["NDXP260917C29100000"])          # one failure, one re-login, one retry
    assert p.budget.calls_today == 4                                          # chain + fetch + failed fetch + retry
    with pytest.raises(RuntimeError, match="101 option symbols"):
        p.fetch([f"S{i}" for i in range(101)])


def test_request_budget_day_cap_holds_across_processes(tmp_path):
    """Two budgets sharing one day file -- two processes -- cannot each spend the whole day's allowance."""
    from paper.providers import RequestBudget
    shared = tmp_path / "broker_calls.json"
    a = RequestBudget(min_interval_s=0, per_minute=1000, per_day=5, shared_path=shared, sleep=lambda s: None)
    b = RequestBudget(min_interval_s=0, per_minute=1000, per_day=5, shared_path=shared, sleep=lambda s: None)
    for _ in range(3):
        a.take()
    for _ in range(2):
        b.take()
    assert b.shared_calls == 5
    import pytest
    with pytest.raises(RuntimeError, match="across all processes"):
        b.take()
