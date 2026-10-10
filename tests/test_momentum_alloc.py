"""The BTC shock-momentum paper allocator (api/services/momentum_alloc.py): a quiet day buys nothing, a 2-sigma up day
buys $4,000 of IBIT once, the lot is held and sold after 10 sessions, the exit day opens nothing, a stale close or a
missing price buys nothing, down shocks are never bought, and a weekend is no session. Offline: stub inputs, a stub
order book, the event desk's memory store and a stub rule (this module's shock_z / entry_signal / target_shares /
exit_due, the plugin's semantics) so the plugin isn't needed."""
from __future__ import annotations

import datetime as _dt
import math

import numpy as np
import pandas as pd
import pytest

from api.services import momentum_alloc as MA
from api.services.event_desk import MemoryEventStore


# ── the stub rule (the plugin's semantics) ──
def shock_z(closes, last, window=20):
    c = np.asarray(closes, dtype=float)
    if last is None or len(c) < window + 1:
        return float("nan"), float("nan"), float("nan")
    r = np.diff(np.log(c[-(window + 1):]))
    sigma = float(np.std(r, ddof=1))
    move = float(np.log(float(last) / c[-1]))
    return move / sigma, move, sigma


def entry_signal(z, k=2.0):
    return bool(np.isfinite(z) and z >= k)


def target_shares(price, notional):
    return int(math.floor(notional / price)) if price else 0


def exit_due(sessions_held, hold=10):
    return sessions_held >= hold


class Rule:
    symbol, k, hold, window, notional = "IBIT", 2.0, 10, 20, 4000.0


class Inputs:
    def __init__(self, closes: pd.Series):
        self.s, self.px, self.held = closes, None, []

    def closes(self, symbols, until):
        return pd.DataFrame({"IBIT": self.s[self.s.index <= pd.Timestamp(until)]})

    def prices_now(self, symbols):
        return {"IBIT": self.px}

    def lots(self):
        return list(self.held)


class Orders:
    def __init__(self, inputs: Inputs, day_fn):
        self.inputs, self.day_fn, self.placed, self.closed, self.n = inputs, day_fn, [], [], 0

    def place(self, body):
        self.n += 1
        q = body["legs"][0]["quantity"]
        self.placed.append((body["underlying"], q, body["client_order_id"], body["strategy"]))
        tg = f"TG{self.n}"
        self.inputs.held.append({"trade_group_id": tg, "symbol": body["underlying"], "shares": q, "opened": self.day_fn()})
        return {"status": "filled", "order_id": self.n, "fill_price": self.inputs.px, "trade_group_id": tg}

    def close_position(self, tgid, body):
        self.closed.append((tgid, body["client_order_id"]))
        self.inputs.held = [l for l in self.inputs.held if l["trade_group_id"] != tgid]
        return {"status": "filled", "order_id": f"c{tgid}", "fill_price": self.inputs.px}


@pytest.fixture(autouse=True)
def _weekdays(monkeypatch):
    monkeypatch.setattr(MA.RA, "trading_day", lambda d: d.weekday() < 5)
    monkeypatch.setattr(MA.RA, "previous_trading_day", lambda d: next(d - _dt.timedelta(days=k) for k in range(1, 8)
                                                                       if (d - _dt.timedelta(days=k)).weekday() < 5))


def _setup(last_close_day: str = "2026-10-08"):
    """30 quiet sessions of IBIT closes ending ``last_close_day`` (1% daily sigma)."""
    rng = np.random.default_rng(11)
    idx = pd.bdate_range(end=last_close_day, periods=30)
    s = pd.Series(50.0 * np.exp(np.cumsum(rng.normal(0.0, 0.01, size=30))), index=idx)
    inp = Inputs(s)
    day = {"d": None}
    orders = Orders(inp, lambda: day["d"])
    alloc = MA.MomentumAllocator(MemoryEventStore(), orders, inputs=inp, strategy_factory=Rule)
    return alloc, inp, orders, day


def _at(d: str, hm: str = "15:50") -> pd.Timestamp:
    return pd.Timestamp(f"{d} {hm}", tz=MA.NY)


def test_sessions_held_counts_trading_days_after_the_entry():
    assert MA.sessions_held(_dt.date(2026, 10, 9), _dt.date(2026, 10, 9)) == 0
    assert MA.sessions_held(_dt.date(2026, 10, 9), _dt.date(2026, 10, 12)) == 1      # a Friday to the Monday
    assert MA.sessions_held(_dt.date(2026, 10, 9), _dt.date(2026, 10, 23)) == 10


def test_a_quiet_day_buys_nothing_and_a_2_sigma_up_day_buys_4000_once():
    alloc, inp, orders, day = _setup()
    day["d"] = _dt.date(2026, 10, 9)
    inp.px = float(inp.s.iloc[-1]) * 1.002
    r = alloc.run(now=_at("2026-10-09"))
    assert r["status"] == "no_signal" and not orders.placed
    alloc2, inp2, orders2, day2 = _setup()
    day2["d"] = _dt.date(2026, 10, 9)
    inp2.px = float(inp2.s.iloc[-1]) * 1.06                              # +6% on a ~1% sigma
    r = alloc2.run(now=_at("2026-10-09"))
    assert r["status"] == "opened" and r["verdict"] == "entry" and r["detail"]["z"] > 2.0
    sym, q, cid, strat = orders2.placed[0]
    assert (sym, q, strat) == ("IBIT", int(4000 // inp2.px), "btc_momentum")
    assert cid == "momentum-2026-10-09-buy-IBIT"
    again = alloc2.run(now=_at("2026-10-09", "15:55"))
    assert again["status"] == "already_decided" and len(orders2.placed) == 1


def test_the_lot_is_held_then_sold_after_10_sessions_and_the_exit_day_opens_nothing():
    alloc, inp, orders, day = _setup()
    day["d"] = _dt.date(2026, 10, 9)
    inp.px = float(inp.s.iloc[-1]) * 1.06
    alloc.run(now=_at("2026-10-09"))
    for d in pd.bdate_range("2026-10-12", "2026-10-22"):                 # sessions 1..9: held, even on another shock
        day["d"] = d.date()
        r = alloc.run(now=_at(d.date().isoformat()))
        assert r["status"] == "held" and not orders.closed
    day["d"] = _dt.date(2026, 10, 23)                                    # session 10: sold
    r = alloc.run(now=_at("2026-10-23"))
    assert r["status"] == "closed" and r["verdict"] == "exit" and orders.closed == [("TG1", "momentum-2026-10-23-close-TG1")]
    assert len(orders.placed) == 1                                       # nothing bought on the exit day


def test_a_stale_close_a_missing_price_and_a_down_shock_buy_nothing():
    alloc, inp, orders, day = _setup(last_close_day="2026-10-07")         # yesterday's (10-08) close is missing
    day["d"] = _dt.date(2026, 10, 9)
    inp.px = float(inp.s.iloc[-1]) * 1.10
    r = alloc.run(now=_at("2026-10-09"))
    assert r["status"] == "stale_closes" and not orders.placed
    alloc, inp, orders, day = _setup()
    day["d"] = _dt.date(2026, 10, 9)
    inp.px = None
    assert alloc.run(now=_at("2026-10-09"))["status"] == "no_quote" and not orders.placed
    alloc, inp, orders, day = _setup()
    day["d"] = _dt.date(2026, 10, 9)
    inp.px = float(inp.s.iloc[-1]) * 0.90                                # a -10% day: never bought
    r = alloc.run(now=_at("2026-10-09"))
    assert r["status"] == "no_signal" and r["detail"]["z"] < -2.0 and not orders.placed


def test_a_weekend_is_no_session_and_status_reports_holdings():
    alloc, inp, orders, day = _setup()
    r = alloc.run(now=_at("2026-10-10"))
    assert r["status"] == "no_session"
    inp.held = [{"trade_group_id": "TG9", "symbol": "IBIT", "shares": 80, "opened": _dt.date(2026, 10, 5)}]
    st = alloc.status()
    assert st["holdings"] == {"IBIT": 80} and st["ledger_strategy"] == "btc_momentum"
