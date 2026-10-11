"""The equity-trend paper allocator (api/services/trend_alloc.py): the first run catches up to the last month-end's
decision, in-between days hold, the month-end decides at the 15:50 price and trades the difference beyond the band, a
fall below the trend sells everything (lots held at least a night), a stale close or a missing price trades nothing,
and a day is decided once. Offline: stub inputs, a stub order book, the event desk's memory store, and a stub rule
(this module's decide / target_shares with the plugin's semantics) so the plugin isn't needed."""
from __future__ import annotations

import datetime as _dt
import math

import numpy as np
import pandas as pd
import pytest

from api.services import trend_alloc as TA
from api.services.event_desk import MemoryEventStore


# ── the stub rule: the plugin's semantics ──
def decide(closes, price=None, sma_months=10, vol_days=21, target_vol=0.10, day=None):
    c = pd.to_numeric(closes, errors="coerce").dropna().sort_index()
    c.index = pd.to_datetime(c.index)
    if price is not None:
        d = pd.Timestamp(day)
        c = pd.concat([c[c.index < d], pd.Series([float(price)], index=[d])])
    me = c.groupby(c.index.to_period("M")).last()
    if len(me) < sma_months or len(c) < vol_days + 1:
        return {"in": False, "w": None, "price": float(c.iloc[-1]), "sma": None, "sigma": None}
    px, sma = float(c.iloc[-1]), float(me.iloc[-sma_months:].mean())
    r = np.diff(np.log(c.to_numpy(float)[-(vol_days + 1):]))
    sigma = float(np.std(r, ddof=1) * math.sqrt(252))
    is_in = px > sma
    return {"in": is_in, "w": (min(1.0, target_vol / sigma) if is_in else 0.0), "price": px, "sma": sma, "sigma": sigma}


def target_shares(weight, sleeve, price):
    return int(math.floor(weight * sleeve / price)) if price and weight > 0 else 0


class Rule:
    signal, holding, sma_months, vol_days, target_vol, sleeve, band = "SPY", "SPYM", 10, 21, 0.10, 8000.0, 0.05


class Inputs:
    def __init__(self, closes: pd.Series):
        self.s, self.px, self.held = closes, {"SPY": None, "SPYM": None}, []

    def closes(self, symbols, until):
        return pd.DataFrame({"SPY": self.s[self.s.index <= pd.Timestamp(until)]})

    def prices_now(self, symbols):
        return {k: self.px.get(k) for k in symbols}

    def lots(self):
        return list(self.held)


class Orders:
    def __init__(self, inputs, day_fn):
        self.inputs, self.day_fn, self.placed, self.closed, self.n = inputs, day_fn, [], [], 0

    def place(self, body):
        self.n += 1
        q = body["legs"][0]["quantity"]
        self.placed.append((body["underlying"], q, body["strategy"], body["client_order_id"]))
        tg = f"TG{self.n}"
        self.inputs.held.append({"trade_group_id": tg, "symbol": body["underlying"], "shares": q, "opened": self.day_fn()})
        return {"status": "filled", "trade_group_id": tg, "fill_price": self.inputs.px["SPYM"]}

    def close_position(self, tgid, body):
        self.closed.append(tgid)
        self.inputs.held = [l for l in self.inputs.held if l["trade_group_id"] != tgid]
        return {"status": "filled"}


@pytest.fixture(autouse=True)
def _calendar(monkeypatch):
    monkeypatch.setattr(TA.RA, "trading_day", lambda d: d.weekday() < 5)
    monkeypatch.setattr(TA.RA, "previous_trading_day", lambda d: next(d - _dt.timedelta(days=k) for k in range(1, 8)
                                                                       if (d - _dt.timedelta(days=k)).weekday() < 5))


def _setup(drift=0.0012, end="2026-10-09"):
    rng = np.random.default_rng(7)
    idx = pd.bdate_range(end=end, periods=320)
    s = pd.Series(600.0 * np.exp(np.cumsum(rng.normal(drift, 0.006, size=len(idx)))), index=idx)
    inp = Inputs(s)
    day = {"d": None}
    orders = Orders(inp, lambda: day["d"])
    alloc = TA.TrendAllocator(MemoryEventStore(), orders, inputs=inp, strategy_factory=Rule)
    return alloc, inp, orders, day


def _at(d: str) -> pd.Timestamp:
    return pd.Timestamp(f"{d} 15:50", tz=TA.NY)


def test_the_first_run_catches_up_to_the_last_month_ends_decision_and_a_day_is_decided_once():
    alloc, inp, orders, day = _setup()
    day["d"] = _dt.date(2026, 10, 12)
    inp.px = {"SPY": float(inp.s.iloc[-1]), "SPYM": 92.0}
    r = alloc.run(now=_at("2026-10-12"))
    d = r["detail"]["decision"]
    assert r["status"] == "rebalanced" and r["verdict"] == "catch_up" and d["in"]
    assert r["detail"]["basis"] == "the 2026-09-30 month-end decision"
    assert orders.placed == [("SPYM", target_shares(d["w"], 8000.0, 92.0), "equity_trend",
                              "equity_trend-2026-10-12-buy-SPYM")]
    assert alloc.run(now=_at("2026-10-12"))["status"] == "already_decided" and len(orders.placed) == 1


def test_in_between_days_hold_inside_the_band():
    alloc, inp, orders, day = _setup()
    day["d"] = _dt.date(2026, 10, 12)
    inp.px = {"SPY": float(inp.s.iloc[-1]), "SPYM": 92.0}
    alloc.run(now=_at("2026-10-12"))
    day["d"] = _dt.date(2026, 10, 13)
    inp.px["SPYM"] = 93.0                                                # a 1% move: well inside the 5% band
    r = alloc.run(now=_at("2026-10-13"))
    assert r["status"] == "held" and len(orders.placed) == 1


def test_a_month_end_below_the_trend_sells_everything():
    alloc, inp, orders, day = _setup()
    day["d"] = _dt.date(2026, 10, 12)
    inp.px = {"SPY": float(inp.s.iloc[-1]), "SPYM": 92.0}
    alloc.run(now=_at("2026-10-12"))
    # extend the closes to 10-29, then decide on the month-end 10-30 with a crash at 15:50
    more = pd.bdate_range("2026-10-12", "2026-10-29")
    inp.s = pd.concat([inp.s, pd.Series(float(inp.s.iloc[-1]), index=more)])
    day["d"] = _dt.date(2026, 10, 30)
    inp.px = {"SPY": float(inp.s.iloc[-1]) * 0.70, "SPYM": 64.0}
    r = alloc.run(now=_at("2026-10-30"))
    assert r["verdict"] == "month_end" and not r["detail"]["decision"]["in"] and r["detail"]["target_shares"] == 0
    assert orders.closed == ["TG1"] and inp.held == []


def test_a_stale_close_or_a_missing_price_trades_nothing_on_a_month_end():
    alloc, inp, orders, day = _setup(end="2026-10-28")                  # 10-29's close is missing
    day["d"] = _dt.date(2026, 10, 30)
    inp.px = {"SPY": float(inp.s.iloc[-1]), "SPYM": 92.0}
    assert alloc.run(now=_at("2026-10-30"))["status"] == "stale_closes" and not orders.placed
    alloc, inp, orders, day = _setup(end="2026-10-29")
    day["d"] = _dt.date(2026, 10, 30)
    inp.px = {"SPY": None, "SPYM": 92.0}
    assert alloc.run(now=_at("2026-10-30"))["status"] == "no_quote" and not orders.placed


def test_a_downtrend_never_buys_and_a_weekend_is_no_session():
    alloc, inp, orders, day = _setup(drift=-0.0015)
    day["d"] = _dt.date(2026, 10, 12)
    inp.px = {"SPY": float(inp.s.iloc[-1]), "SPYM": 92.0}
    r = alloc.run(now=_at("2026-10-12"))
    assert r["status"] == "held" and r["detail"]["target_shares"] == 0 and not orders.placed
    assert alloc.run(now=_at("2026-10-10"))["status"] == "no_session"
