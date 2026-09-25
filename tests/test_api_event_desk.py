"""
The event desk (api/services/event_signals.py, event_desk.py, event_alloc.py, crypto_flush.py): the signal math,
the playbook verdicts on crafted cases, the allocators' decisions and the hold-night rule, the post-close signal
log with its outcome back-fill, the crypto-flush trigger on a fake OKX, the event log round trip and the endpoints.
Nothing here touches the real paper account, a market-data provider or an exchange; the DB round trip (skipped
without the database) uses throwaway keys it deletes.
"""
from __future__ import annotations

import datetime as _dt
import sys
import uuid
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:      # only the checkout: its parent holds the live alan_trader (conftest binds ours by path)
    sys.path.insert(0, str(REPO))

from api.bootstrap import bootstrap  # noqa: E402

bootstrap()

from api.services import crypto_flush as CF  # noqa: E402
from api.services import event_alloc as EA  # noqa: E402
from api.services import event_desk as ED  # noqa: E402
from api.services import event_signals as ES  # noqa: E402

NY = "America/New_York"
D = _dt.date
TODAY = D(2026, 9, 25)                                   # a Friday


# ── fixtures: crafted closes, fake sources ─────────────────────────────────────

def series(values, end: D = TODAY) -> pd.Series:
    """Closes on business days ending at ``end``."""
    days = pd.bdate_range(end=end, periods=len(values))
    return pd.Series([float(v) for v in values], index=[d.date() for d in days])


def wobble(n: int, level: float, amp: float = 0.004, seed: int = 3) -> list[float]:
    """A level with small deterministic daily noise (so the sd is not zero)."""
    rng = np.random.default_rng(seed)
    out, x = [], level
    for _ in range(n):
        x *= 1 + rng.normal(0, amp)
        out.append(round(x, 3))
    return out


def crude_path(spike_pct=3.0, after=(), n=70):
    """70 quiet sessions, a spike, then ``after`` (a list of % changes) — ending at TODAY."""
    base = wobble(n, 90.0)
    vals = list(base)
    vals.append(round(vals[-1] * (1 + spike_pct / 100), 3))
    for a in after:
        vals.append(round(vals[-1] * (1 + a / 100), 3))
    return series(vals)


class FakeDaily:
    def __init__(self, closes: dict, partial: dict | None = None):
        self.closes = dict(closes)
        self.partial = dict(partial or {})
        self.calls = 0

    def get(self, key, force=False):
        return self.get_many([key], force)[key]

    def get_many(self, keys, force=False):
        self.calls += 1
        return {k: {"closes": self.closes.get(k, pd.Series(dtype=float)), "source": "test",
                    "partial": self.partial.get(k), "partial_asof": "partial" if k in self.partial else None,
                    "error": None} for k in keys}


class FakeLive:
    def __init__(self, marks=None):
        self.marks = dict(marks or {})

    def get(self, keys):
        return {k: (v, "2026-09-25T14:35:00-04:00", "hub:fake") for k, v in self.marks.items() if k in keys}


def flat_world(**overrides) -> dict:
    """Quiet closes for every key (70 sessions), with per-key overrides."""
    levels = {"CL": 90.0, "USO": 148.0, "OVX": 40.0, "VIX": 15.0, "VIX3M": 17.0, "BTC": 60000.0, "IBIT": 34.0}
    out = {k: series(wobble(70, lv, seed=i)) for i, (k, lv) in enumerate(levels.items())}
    out.update(overrides)
    return out


def ev(day: D, kind: str, barrels="N", text="Iran threatens Hormuz", eid=1, hour=13) -> dict:
    return {"id": eid, "ts": _dt.datetime(day.year, day.month, day.day, hour, 0), "kind": kind, "barrels_lost": barrels,
            "text": text, "region": "Iran", "source": None}


# ── signal math ────────────────────────────────────────────────────────────────

def test_compute_scores_the_last_close_against_the_closes_before_it():
    vals = [100.0] * 30
    vals[-1] = 103.0
    s = series([v * (1 + 0.001 * (i % 3)) for i, v in enumerate(vals)])     # a little noise, so sd > 0
    row = ES.compute("CL", s)
    assert row["symbol"] == "CL" and row["source"] == "daily" and row["as_of"] == TODAY.isoformat()
    assert row["last"] == row["close"] == s.iloc[-1] and row["prev_close"] == s.iloc[-2]
    assert row["change_pct"] == pytest.approx((s.iloc[-1] / s.iloc[-2] - 1) * 100, abs=1e-3)
    assert row["move_z20"] > 2 and row["z20"] > 2 and row["z60"] is None           # 29 closes before it: no 60-day z
    assert row["mean20"] == pytest.approx(float(np.mean(s.values[-21:-1])), abs=1e-3)
    assert row["dist_mean20_pct"] == pytest.approx((row["last"] / row["mean20"] - 1) * 100, abs=1e-3)
    assert len(row["history"]) == 30 and row["history"][-1] == [TODAY.isoformat(), round(float(s.iloc[-1]), 4)]


def test_compute_with_a_live_mark_scores_the_mark_against_the_last_close():
    s = series(wobble(70, 100.0))
    row = ES.compute("USO", s, last=float(s.iloc[-1]) * 1.02, last_asof="t", mark_source="hub:fake", source="live")
    assert row["source"] == "live" and row["mark_source"] == "hub:fake" and row["as_of"] == "t"
    assert row["change_pct"] == pytest.approx(2.0, abs=1e-6) and row["prev_close"] == row["close"]
    assert row["z60"] is not None and row["higher_streak"] == ES.higher_streak(s)   # the mark never extends the streak


def test_streaks_and_spikes():
    assert ES.higher_streak(series([1, 2, 3, 4])) == 3
    assert ES.higher_streak(series([1, 2, 3, 2])) == 0
    assert ES.higher_streak(series([5, 4, 3, 4, 5])) == 2
    assert ES.compute("X", series([1, 2, 3, 4]))["higher_streak"] == 3
    # a 3% spike two sessions ago, then a down close, then an up close
    s = crude_path(3.0, after=(-1.0, 0.5))
    sp = ES.recent_spike(s)
    assert sp["sessions_ago"] == 2 and sp["change_pct"] == pytest.approx(3.0, abs=0.01) and sp["move_z20"] > 2
    assert sp["down_close_since"] is True and sp["first_down_close"] == s.index[-2].isoformat() and len(sp["closes_since"]) == 2
    assert ES.recent_spike(crude_path(3.0)) is not None and ES.recent_spike(crude_path(3.0))["down_close_since"] is False
    assert ES.recent_spike(series(wobble(70, 90.0))) is None
    assert ES.recent_spike(crude_path(3.0, after=(0.1,) * 6)) is None            # older than the 5-session lookback
    assert ES.recent_spike(crude_path(1.0, after=(0.1,)), z=99) is None          # under both thresholds


def test_signals_snapshot_uses_marks_partials_and_daily():
    closes = flat_world()
    sig = ES.Signals(daily=FakeDaily(closes, partial={"BTC": 61000.0}), live=FakeLive({"USO": 150.0}),
                     clock=lambda: pd.Timestamp("2026-09-25 14:35", tz=NY))
    snap = sig.snapshot()
    assert list(snap) == list(ES.KEYS)
    assert snap["USO"]["source"] == "live" and snap["USO"]["last"] == 150.0 and snap["USO"]["mark_source"] == "hub:fake"
    assert snap["BTC"]["source"] == "daily" and snap["BTC"]["last"] == 61000.0 and "partial" in snap["BTC"]["mark_source"]
    assert snap["CL"]["source"] == "daily" and snap["CL"]["last"] == snap["CL"]["close"]
    assert snap["CL"]["warnings"] == [] and snap["CL"]["sessions"] == 70


# ── the crude playbook ─────────────────────────────────────────────────────────

def crude_case(closes, ovx=40.0, events=(), war=False, trades=(), params=None, trade=None):
    cl = ES.compute("CL", closes)
    return ED.evaluate_crude(cl, closes, ovx, list(events), war, list(trades), TODAY, params, trade)


def _ok(pb, label_start):
    return next(c for c in pb["checklist"] if c["label"].startswith(label_start))


def test_crude_no_spike_is_none():
    pb = crude_case(series(wobble(70, 90.0)))
    assert pb["id"] == "oil_fade" and pb["verdict"] == "none" and pb["experimental"] is True and pb["trade"] is None
    assert _ok(pb, "Spike")["ok"] is False and "No crude spike" in pb["headline"]


def test_crude_threat_only_spike_waits_for_the_first_down_close_then_fades():
    spike_day = crude_path(3.0).index[-1]
    esc = ev(spike_day, "escalation", "N")
    on_the_day = crude_case(crude_path(3.0), events=[esc])
    assert on_the_day["verdict"] == "wait" and "first down close" in on_the_day["reasons"][0]
    assert _ok(on_the_day, "First down close")["ok"] is False and _ok(on_the_day, "No barrels lost")["ok"] is True
    after = crude_path(3.0, after=(-1.2,))
    esc = ev(after.index[-2], "escalation", "N")
    trade = {"structure": "USO put vertical", "legs": "+P148 −P139 2026-10-30"}
    pb = crude_case(after, events=[esc], trade=trade)
    assert pb["verdict"] == "fade" and pb["trade"] == trade and "Fade the +3.0% crude spike" in pb["headline"]
    assert [c["ok"] for c in pb["checklist"]] == [True, True, True, True, True, False, True]
    assert any("OVX 40 < 45" in r for r in pb["reasons"]) and any("experimental" in r for r in pb["reasons"])
    assert _ok(pb, "OVX")["value"] == "40.0" and _ok(pb, "War regime")["value"] == "off"


def test_crude_leave_alone_cases():
    after = crude_path(3.0, after=(-1.2,))
    day = after.index[-2]
    # barrels lost
    pb = crude_case(after, events=[ev(day, "supply_loss", "Y", "Abqaiq hit; 5.7 mb/d offline")])
    assert pb["verdict"] == "leave" and "barrels" in pb["reasons"][0] and _ok(pb, "No barrels lost")["ok"] is False
    # OVX 65
    pb = crude_case(after, ovx=65.0, events=[ev(day, "escalation", "N")])
    assert pb["verdict"] == "leave" and "OVX 65" in pb["reasons"][0] and _ok(pb, "OVX")["ok"] is False
    # three higher closes running (spike + two more up closes)
    three = crude_path(3.0, after=(0.8, 0.6))
    pb = crude_case(three, events=[ev(three.index[-3], "escalation", "N")])
    assert pb["verdict"] == "leave" and "3 sessions running" in pb["reasons"][0]
    assert _ok(pb, "Not closed higher")["ok"] is False and _ok(pb, "Not closed higher")["value"] == "3 higher close(s) running"
    # partial loss is not a leave (R1b: barrels_lost != Y)
    pb = crude_case(after, events=[ev(day, "escalation", "P")])
    assert pb["verdict"] == "fade" and _ok(pb, "No barrels lost")["value"].startswith("partial")


def test_crude_needs_a_logged_event_and_respects_the_war_regime():
    after = crude_path(3.0, after=(-1.2,))
    day = after.index[-2]
    pb = crude_case(after)
    assert pb["verdict"] == "wait" and "no escalation logged" in pb["reasons"][0]
    assert _ok(pb, "No barrels lost")["ok"] is None
    pb = crude_case(after, events=[ev(day, "escalation", "N")], war=True)
    assert pb["verdict"] == "wait" and "war regime" in pb["reasons"][0] and _ok(pb, "War regime")["ok"] is False
    deesc = ev(TODAY, "de-escalation", "N", "Trump: talks resume, strikes paused", eid=2)
    pb = crude_case(after, events=[ev(day, "escalation", "N"), deesc], war=True)
    assert pb["verdict"] == "fade" and any("de-escalation logged" in r for r in pb["reasons"])
    assert _ok(pb, "De-escalation")["ok"] is True and "talks resume" in _ok(pb, "De-escalation")["value"]


def test_crude_add_on_the_first_deescalation_after_the_entry():
    after = crude_path(3.0, after=(-1.2, 0.3))
    spike_day = after.index[-3]
    opened = after.index[-2]
    trade = {"playbook": "oil_fade", "trade_group_id": "TG1", "opened": opened.isoformat()}
    events = [ev(spike_day, "escalation", "N")]
    pb = crude_case(after, events=events, trades=[trade])
    assert pb["verdict"] == "wait" and "one position at a time" in pb["reasons"][0]
    events.append(ev(TODAY, "de-escalation", "N", "ceasefire announced", eid=2))
    pb = crude_case(after, events=events, trades=[trade], trade={"legs": "x"})
    assert pb["verdict"] == "add" and "ceasefire" in pb["reasons"][0] and pb["trade"] == {"legs": "x"}
    # the add is once: with two groups open there is no further add
    pb = crude_case(after, events=events, trades=[trade, dict(trade, trade_group_id="TG2", opened=TODAY.isoformat())])
    assert pb["verdict"] == "wait"
    # a de-escalation logged BEFORE the entry is not an add
    early = [ev(spike_day, "escalation", "N"), ev(spike_day, "de-escalation", "N", "talks", eid=3, hour=18)]
    pb = crude_case(after, events=early, trades=[trade])
    assert pb["verdict"] == "wait"


# ── the BTC and VIX playbooks ──────────────────────────────────────────────────

def btc_case(closes, events=(), trades=(), now="2026-09-25 08:00", partial=None):
    now = pd.Timestamp(now, tz=NY)
    btc = ES.compute("BTC", closes, partial, "partial", "yfinance partial day", "daily") if partial else ES.compute("BTC", closes)
    return ED.evaluate_btc(btc, closes, list(events), list(trades), now)


def test_btc_dip_after_a_logged_shock():
    base = wobble(70, 60000.0)
    closes = series(base)
    shock = ev(D(2026, 9, 24), "escalation", "N", "strikes on Iran overnight")
    pre = float(closes[closes.index < D(2026, 9, 24)].iloc[-1])
    dipped = series(base[:-1] + [round(pre * 0.97, 2)])
    pb = btc_case(dipped, events=[shock])
    assert pb["verdict"] == "fade" and pb["action"] == "buy_dip" and pb["experimental"] is True
    assert pb["detail"]["pre_shock"] == pre and pb["detail"]["dip_pct"] == pytest.approx(-3.0, abs=0.01)
    assert _ok(pb, "Risk-off event")["ok"] is True and _ok(pb, "BTC ≥")["ok"] is True
    assert _ok(pb, "Next NYSE open")["value"] == "2026-09-25" and "2026-09-25 open" in pb["headline"]
    # only 1% under: wait
    pb = btc_case(series(base[:-1] + [round(pre * 0.99, 2)]), events=[shock])
    assert pb["verdict"] == "wait" and "not dipped enough" in pb["headline"]
    # nothing logged, but a 24-h drop of 3.5% (the partial day against the last close): a candidate too
    pb = btc_case(closes, partial=float(closes.iloc[-1]) * 0.965, now="2026-09-25 18:00")
    assert pb["verdict"] == "fade" and _ok(pb, "or a 24-h drop")["ok"] is True and _ok(pb, "Next NYSE open")["value"] == "2026-09-28"
    # nothing at all
    pb = btc_case(closes)
    assert pb["verdict"] == "none" and pb["trade"] is None
    # a position open: managed by the exits
    pb = btc_case(dipped, events=[shock], trades=[{"playbook": "btc_dip", "trade_group_id": "T"}])
    assert pb["verdict"] == "wait" and _ok(pb, "No btc_dip position")["ok"] is False


def test_vix_note_never_trades():
    quiet = series(wobble(70, 15.0))
    pb = ED.evaluate_vix(ES.compute("VIX", quiet), ES.compute("VIX3M", series(wobble(70, 17.0))))
    assert pb["verdict"] == "none" and pb["trade"] is None and pb["reasons"] == [] and pb["experimental"] is False
    spiked = series(wobble(69, 15.0) + [24.0])
    pb = ED.evaluate_vix(ES.compute("VIX", spiked), ES.compute("VIX3M", series(wobble(70, 17.0))))
    assert pb["verdict"] == "none" and "priced into the futures" in pb["headline"] and pb["reasons"]
    assert _ok(pb, "VIX level")["ok"] is True and _ok(pb, "VIX above VIX3M")["ok"] is True


# ── structures ─────────────────────────────────────────────────────────────────

def test_the_put_vertical_suggestion():
    exps = [TODAY + _dt.timedelta(days=d) for d in (7, 14, 28, 35, 63)]
    t = ED.suggest_vertical("put", "USO", 147.9, TODAY, exps, 0.06, 21, 42, 30, 1.0)
    assert t["expiry"] == (TODAY + _dt.timedelta(days=28)).isoformat() and t["dte"] == 28
    assert (t["long_strike"], t["short_strike"], t["width"]) == (148.0, 139.0, 9.0)
    assert t["legs"].startswith("+P148 −P139 ") and t["est_debit"] is None and t["max_loss"] is None
    syms = [l["symbol"] for l in t["order_legs"]]
    t2 = ED.suggest_vertical("put", "USO", 147.9, TODAY, exps, 0.06, 21, 42, 30, 1.0, mids={syms[0]: 4.1, syms[1]: 1.6})
    assert t2["est_debit"] == 2.5 and t2["max_loss"] == 250.0 and t2["max_profit"] == 650.0
    # no listed expirations: the next monthly at least 21 days out (October's third Friday)
    t3 = ED.suggest_vertical("put", "USO", 147.9, TODAY, None, 0.06, 21, 42, 30, 1.0)
    assert t3["expiry"] == "2026-10-16"
    assert ED.suggest_vertical("call", "IBIT", 34.2, TODAY, exps, 0.06, 21, 42, 30, 1.0)["short_strike"] == 36.0


# ── the allocators on a fake desk ──────────────────────────────────────────────

class FakeChain:
    def __init__(self, spot=147.9):
        self.spot_px = spot
        self.exps = [TODAY + _dt.timedelta(days=30)]

    def spot(self, s):
        return self.spot_px

    def expirations(self, u):
        return self.exps

    def mids(self, symbols):
        from api.marketdata import symbols as SYM
        out = {}
        for s in symbols:
            o = SYM.parse_option(s)
            out[s] = 4.0 if o.strike >= self.spot_px * 0.97 else 1.5
        return out


class Book:
    """Fake order book + the desk's open trades."""

    def __init__(self, clock):
        self.clock = clock
        self.calls, self.trades, self.n = [], [], 0

    def today(self):
        return self.clock().date()

    def place(self, body):
        self.calls.append(("place", body))
        self.n += 1
        tg = f"TG{self.n}"
        assert body["account"] == "paper"
        legs = body["legs"]
        px = body.get("limit_price") or 34.0
        self.trades.append({"playbook": body["strategy"].split(":")[1], "trade_group_id": tg,
                            "opened": self.today().isoformat(), "entry": px, "mark": px,
                            "expiry": legs[0].get("expiry"), "quantity": legs[0]["quantity"],
                            "description": body.get("label")})
        return {"order_id": self.n, "status": "filled", "fill_price": px, "trade_group_id": tg, "message": "filled"}

    def close_position(self, tgid, body):
        self.calls.append(("close", tgid, body))
        self.trades = [t for t in self.trades if t["trade_group_id"] != tgid]
        self.n += 1
        return {"order_id": self.n, "status": "filled", "fill_price": 1.0, "closes_trade_group_id": tgid}

    def open_trades(self):
        today = self.today()
        return [dict(t, days_held=ED.sessions_between(D.fromisoformat(t["opened"]), today),
                     nights_held=(today - D.fromisoformat(t["opened"])).days) for t in self.trades]


@pytest.fixture
def world():
    clock = {"t": pd.Timestamp("2026-09-25 15:45", tz=NY)}
    daily = FakeDaily(flat_world())
    sig = ES.Signals(daily=daily, live=FakeLive(), clock=lambda: clock["t"])
    book = Book(lambda: clock["t"])
    store = ED.MemoryEventStore()
    desk = ED.EventDesk(None, store=store, signals=sig, clock=lambda: clock["t"], trades=book.open_trades, chain=FakeChain())
    events = []
    return desk, daily, book, store, clock, events


def test_oil_fade_allocator_opens_once_and_exits_only_after_a_night(world):
    desk, daily, book, store, clock, events = world
    a = EA.OilFadeAllocator(desk, book, publish=events.append)
    # quiet crude: no trade, logged
    r = a.run()
    assert r["status"] == "no_trade" and r["verdict"] == "none" and book.calls == []
    assert a.run()["status"] == "already_decided"
    # Monday 9/28: a spike happened Thursday 9/24, Friday closed down, the event is logged: fade
    clock["t"] = pd.Timestamp("2026-09-28 15:45", tz=NY)
    daily.closes["CL"] = crude_path(3.0, after=(-1.2, 0.2), )                    # spike 9/23, down 9/24, up 9/25
    daily.closes["CL"] = series(list(daily.closes["CL"].values), end=D(2026, 9, 28))  # shift: spike 9/24, down 9/25, up 9/28
    spike_day = daily.closes["CL"].index[-3]
    desk.log_event({"ts": f"{spike_day}T09:00", "kind": "escalation", "region": "Iran", "text": "IRGC seizes tanker",
                    "barrels_lost": "N"})
    r = a.run()
    assert r["status"] == "opened" and r["action"] == "open" and r["trade_group_id"] == "TG1"
    kind, body = book.calls[-1]
    assert kind == "place" and body["strategy"] == "event:oil_fade" and body["order_type"] == "limit"
    assert body["limit_price"] == pytest.approx(2.5 + 0.05) and body["client_order_id"] == "event-oil_fade-2026-09-28-open"
    assert [l["side"] for l in body["legs"]] == ["buy", "sell"] and body["legs"][0]["type"] == "put"
    uso = float(daily.closes["USO"].iloc[-1])                                  # sized off USO's own last, not the chain's spot
    assert body["legs"][0]["strike"] == round(uso) and body["legs"][1]["strike"] == round(uso * 0.94)
    assert events[-1]["type"] == "event_alloc" and events[-1]["status"] == "opened"
    # same day, crude already back at its mean: the hold-night rule blocks the exit
    clock["t"] = pd.Timestamp("2026-09-28 15:50", tz=NY)
    store.decisions.clear()                                                   # pretend a second decision were possible
    daily.closes["CL"] = series(list(daily.closes["CL"].values[:-1]) + [85.0], end=D(2026, 9, 28))
    r = a.run()
    assert r["status"] == "held" and len(book.trades) == 1
    assert EA.oil_exit_reason(book.open_trades()[0], 85.0, 90.0, D(2026, 9, 28), a.params) is None
    # next day: crude at the mean -> target exit
    clock["t"] = pd.Timestamp("2026-09-29 15:45", tz=NY)
    daily.closes["CL"] = series(list(daily.closes["CL"].values) + [85.0], end=D(2026, 9, 29))
    r = a.run()
    assert r["status"] == "closed" and r["action"] == "exit" and book.calls[-1][0] == "close"
    assert "target" in r["detail"]["orders"][0]["reason"] and book.trades == []
    log = a.log(10)
    assert [d["status"] for d in log["decisions"]] == ["closed", "held"]      # (the earlier rows were cleared above)
    st = a.status()
    assert st["experimental"] is True and st["last_decision"]["status"] == "closed" and st["open_trades"] == []


def test_oil_exit_rules():
    p = ED.OIL_PARAMS
    t = {"opened": "2026-09-21", "entry": 2.5, "mark": 2.4, "expiry": "2026-10-30", "days_held": 4}
    assert EA.oil_exit_reason(t, 92.0, 90.0, D(2026, 9, 25), p) is None
    assert EA.oil_exit_reason(dict(t, mark=1.2), 92.0, 90.0, D(2026, 9, 25), p).startswith("stop")
    assert EA.oil_exit_reason(dict(t, days_held=10), 92.0, 90.0, D(2026, 9, 25), p).startswith("time")
    assert EA.oil_exit_reason(dict(t, expiry="2026-09-28"), 92.0, 90.0, D(2026, 9, 25), p).startswith("expiry")
    assert EA.oil_exit_reason(t, 89.0, 90.0, D(2026, 9, 25), p).startswith("target")
    assert EA.oil_exit_reason(dict(t, opened="2026-09-25", mark=0.1), 80.0, 90.0, D(2026, 9, 25), p) is None   # never before a night


def test_btc_dip_allocator(world):
    desk, daily, book, store, clock, events = world
    a = EA.BtcDipAllocator(desk, book, publish=events.append)
    clock["t"] = pd.Timestamp("2026-09-25 09:31", tz=NY)
    base = flat_world()["BTC"]
    pre = float(base.iloc[-2])
    daily.closes["BTC"] = series(list(base.values[:-1]) + [round(pre * 0.97, 2)])
    desk.log_event({"ts": "2026-09-24T22:00", "kind": "escalation", "text": "US strikes", "barrels_lost": "unknown"})
    desk.chain.spot_px = 34.0
    r = a.run()
    assert r["status"] == "opened" and r["detail"]["playbook_detail"]["pre_shock"] == pre
    kind, body = book.calls[-1]
    ibit = float(daily.closes["IBIT"].iloc[-1])                                 # sized off IBIT's own last close
    assert body["order_type"] == "market" and body["legs"] == [{"type": "stock", "side": "buy", "quantity": int(5000 // ibit)}]
    assert body["strategy"] == "event:btc_dip" and body["client_order_id"] == "event-btc_dip-2026-09-25-open"
    # the same day nothing closes (one night); Monday BTC back at the pre-shock price: target
    clock["t"] = pd.Timestamp("2026-09-28 09:31", tz=NY)
    daily.closes["BTC"] = series(list(daily.closes["BTC"].values) + [pre * 1.001], end=D(2026, 9, 28))
    r = a.run()
    assert r["status"] == "closed" and "target" in r["detail"]["orders"][0]["reason"] and book.trades == []
    p = ED.BTC_PARAMS
    t = {"opened": "2026-09-25", "entry": 34.0, "mark": 33.0, "days_held": 1}
    assert EA.btc_exit_reason(t, 59000.0, 60000.0, D(2026, 9, 28), p) is None
    assert EA.btc_exit_reason(dict(t, mark=32.5), 59000.0, 60000.0, D(2026, 9, 28), p).startswith("stop")
    assert EA.btc_exit_reason(dict(t, days_held=3), 59000.0, 60000.0, D(2026, 9, 30), p).startswith("time")
    assert EA.btc_exit_reason(dict(t, mark=30.0), 59000.0, 60000.0, D(2026, 9, 25), p) is None                    # same day


def test_a_failed_input_is_logged_not_traded(world):
    desk, daily, book, store, clock, events = world
    desk.signals = None                                                       # everything upstream broken
    a = EA.OilFadeAllocator(desk, book, publish=events.append)
    r = a.run()
    assert r["status"] == "failed" and book.calls == [] and events[-1]["status"] == "failed"


def test_armed_through_the_scheduler(world, tmp_path):
    from api.services import arms as A
    from api.services import runner as RN
    desk, daily, book, store, clock, events = world
    a = EA.OilFadeAllocator(desk, book, publish=events.append)
    sched = A.ArmScheduler(A.MemoryArmStore(), RN.RunnerManager(log_dir=tmp_path), publish=events.append,
                           clock=lambda: clock["t"], launcher=lambda s: (_ for _ in ()).throw(AssertionError("no script")),
                           allocators={"oil_fade": a})
    desk.armed = sched.is_armed
    assert desk.playbook("oil_fade")["armed"] is False
    clock["t"] = pd.Timestamp("2026-09-25 09:00", tz=NY)
    rows = sched.arm("oil_fade", "once", "2026-09-25")
    assert rows[0]["kind"] == "allocator" and rows[0]["next_run"] == "2026-09-25T15:45:00-04:00"
    assert desk.playbook("oil_fade")["armed"] is True and sched.is_armed("btc_dip") is False
    with pytest.raises(A.ArmError):
        sched.arm("btc_dip", "once", "2026-09-25")                            # no allocator wired for it here
    assert sched.tick(pd.Timestamp("2026-09-25 15:44", tz=NY)) == []
    evs = sched.tick(pd.Timestamp("2026-09-25 15:45:10", tz=NY))
    assert [e["event"] for e in evs] == ["ran"] and "no_trade" in evs[0]["decision"]["status"]
    assert store.decided("oil_fade", D(2026, 9, 25))["status"] == "no_trade"
    arms = sched.arms()
    assert arms[0]["status"]["playbook"] == "oil_fade" and arms[0]["last_result"].startswith("ran: oil_fade")


# ── the signal log ─────────────────────────────────────────────────────────────

def test_outcome_backfill():
    # a +3% up day at index 20, then a slow give-back
    vals = [100.0] * 20 + [103.0, 102.5, 101.4, 101.0, 100.8]
    s = series(vals, end=D(2026, 9, 25))
    day = s.index[20]
    o = ED.outcome(s, day)
    assert o["r3"] == pytest.approx((101.0 / 103.0 - 1) * 100, abs=1e-3) and o["r10"] is None and o["r20"] is None
    assert o["half_back_days"] == 2 and o["half_back"] is True and o["outcome_asof"] == s.index[-1]
    pending = ED.outcome(series([100.0] * 20 + [103.0, 103.5]), series([100.0] * 20 + [103.0, 103.5]).index[20])
    assert pending["half_back"] is None and pending["half_back_days"] is None
    never = ED.outcome(series([100.0] * 20 + [103.0] + [104.0] * 20), series([100.0] * 41).index[20])
    assert never["half_back"] is False and never["r20"] == pytest.approx((104.0 / 103.0 - 1) * 100, abs=1e-3)
    down = ED.outcome(series([100.0] * 20 + [96.0, 97.0, 98.5]), series([100.0] * 23).index[20])
    assert down["half_back_days"] == 2                                          # half of a −4 move is 98
    assert ED.outcome(s, D(2000, 1, 1)) == {}


def test_signal_log_job_records_tags_and_backfills():
    clock = {"t": pd.Timestamp("2026-09-25 16:15", tz=NY)}
    closes = flat_world()
    uso = list(closes["USO"].values)
    uso[-1] = round(uso[-2] * 1.03, 3)                                          # a 3% USO day (many σ)
    closes["USO"] = series(uso)
    closes["BTC"] = series(list(closes["BTC"].values[:-1]) + [round(closes["BTC"].iloc[-2] * 0.96, 2)])
    daily = FakeDaily(closes)
    sig = ES.Signals(daily=daily, live=FakeLive({"USO": 999.0}), clock=lambda: clock["t"])
    store = ED.MemoryEventStore()
    desk = ED.EventDesk(None, store=store, signals=sig, clock=lambda: clock["t"], trades=lambda: [])
    events = []
    job = ED.SignalLogJob(desk, publish=events.append)
    r = job.run()
    assert sorted(r["logged"]) == ["BTC", "USO"] and r["already"] == [] and r["backfilled"] == 0
    assert events[-1]["type"] == "event_signal_log"
    rows = desk.signal_log(30)
    assert {x["symbol"] for x in rows} == {"BTC", "USO"}
    u = next(x for x in rows if x["symbol"] == "USO")
    assert u["date"] == "2026-09-25" and u["change_pct"] == pytest.approx(3.0, abs=0.01) and u["move_z"] > 2
    assert u["close"] == uso[-1] and u["vix"] == closes["VIX"].iloc[-1] and u["ovx"] == closes["OVX"].iloc[-1]
    assert u["tag"] is None and u["complete"] is False and u["mean20"] is not None and u["sd20"] is not None
    # the job scores CLOSES only, never the live mark (USO's hub mark was 999)
    assert u["close"] != 999.0
    # once a day
    r = job.run()
    assert r["logged"] == [] and sorted(r["already"]) == ["BTC", "USO"]
    # the tag, that evening
    t = desk.tag_signal(u["id"], {"tag": "iran_headline", "note": "Hormuz threat"})
    assert t["tag"] == "iran_headline" and t["note"] == "Hormuz threat" and t["tagged_at"]
    with pytest.raises(ED.EventError):
        desk.tag_signal(u["id"], {"tag": "whatever"})
    assert desk.tag_signal(u["id"], {"tag": None})["tag"] is None
    assert desk.tag_signal(999, {"tag": "macro"}) is None
    # three sessions later the give-back is in: r3 and half_back filled, r10 still pending
    clock["t"] = pd.Timestamp("2026-09-30 16:15", tz=NY)
    daily.closes["USO"] = series(uso + [round(uso[-1] * 0.99, 3), round(uso[-1] * 0.98, 3), round(uso[-1] * 0.975, 3)],
                                 end=D(2026, 9, 30))
    r = job.run()
    assert r["logged"] == [] and r["backfilled"] >= 1
    u = next(x for x in desk.signal_log(30) if x["symbol"] == "USO")
    assert u["r3"] == pytest.approx(-2.5, abs=0.01) and u["half_back_days"] == 2 and u["half_back"] is True
    assert u["r10"] is None and u["complete"] is False and u["outcome_asof"] == "2026-09-30"
    assert job.status()["rows"] == 2 and job.status()["pending"] == 2 and job.status()["untagged"] == 2   # (the tag was cleared)
    desk.tag_signal(u["id"], {"tag": "macro"})
    assert job.status()["untagged"] == 1
    # BTC never closes: at 16:15 ET its UTC day is still open, so the day's partial is what gets scored
    clock["t"] = pd.Timestamp("2026-10-01 16:15", tz=NY)
    btc = daily.closes["BTC"]
    daily.closes["BTC"] = series(list(btc.values), end=D(2026, 9, 30))           # the UTC close of 9/30 is the last close
    daily.partial["BTC"] = round(float(btc.iloc[-1]) * 0.95, 2)                  # 10/1 so far: −5%
    r = job.run()
    assert r["logged"] == ["BTC"]
    b = next(x for x in desk.signal_log(30) if x["symbol"] == "BTC" and x["date"] == "2026-10-01")
    assert b["close"] == daily.partial["BTC"] and b["change_pct"] == pytest.approx(-5.0, abs=0.01)


# ── the crypto flush ───────────────────────────────────────────────────────────

def test_r0_rule():
    t0 = 1_700_000_000_000
    prices = [(t0 + i * 60_000, 100.0) for i in range(240)]
    ois = [(t0 + i * 60_000, 1000.0) for i in range(240)]
    now = t0 + 240 * 60_000
    quiet = CF.evaluate(prices, ois, now)
    assert quiet["triggered"] is False and quiet["drop_pct"] == 0.0 and quiet["oi_drop_pct"] == 0.0
    hit = CF.evaluate(prices + [(now, 94.0)], ois + [(now, 940.0)], now)
    assert hit["triggered"] is True and hit["drop_pct"] == -6.0 and hit["oi_drop_pct"] == -6.0 and hit["oi_age_min"] == 0.0
    assert CF.evaluate(prices + [(now, 96.0)], ois + [(now, 940.0)], now)["triggered"] is False        # price only −4%
    assert CF.evaluate(prices + [(now, 94.0)], ois + [(now, 970.0)], now)["triggered"] is False        # OI only −3%
    stale = CF.evaluate(prices + [(now, 94.0)], ois[:-20] + [(now - 15 * 60_000, 940.0)], now)
    assert stale["triggered"] is False and any("min old" in r for r in stale["reasons"])
    rising = ois[:-40] + [(now - 40 * 60_000, 900.0)] + [(now - k * 60_000, 900.0 + (40 - k)) for k in range(39, 0, -1)]
    r = CF.evaluate(prices + [(now, 94.0)], rising + [(now, 940.0)], now)
    assert r["oi_rising"] is True and r["triggered"] is False
    cool = CF.evaluate(prices + [(now, 94.0)], ois + [(now, 940.0)], now, last_signal_ms=now - 600 * 60_000)
    assert cool["triggered"] is False and cool["cooldown_min_left"] == 840.0
    warm = CF.evaluate(prices + [(now, 94.0)], ois[-5:] + [(now, 940.0)], now)
    assert warm["triggered"] is False and any("warming" in r for r in warm["reasons"])


class FakeOkx:
    def __init__(self, clock):
        self.clock = clock
        self.px = {"BTC": 60000.0, "ETH": 3000.0}
        self.oi = {"BTC": 50000.0, "ETH": 800000.0}
        self.calls = 0

    def _ms(self):
        return int(self.clock().tz_convert("UTC").timestamp() * 1000)

    def candles(self, inst, limit=240):
        self.calls += 1
        px = self.px[inst[:3]]
        return [(self._ms() - (limit - i) * 60_000, px) for i in range(limit)]

    def ticker(self, inst):
        self.calls += 1
        return self.px[inst[:3]], self._ms()

    def open_interest(self, inst):
        self.calls += 1
        return self.oi[inst[:3]], self._ms()


def test_crypto_flush_poller_logs_and_trades_when_armed():
    clock = {"t": pd.Timestamp("2026-09-25 03:00", tz=NY)}
    armed = {"on": False}
    okx = FakeOkx(lambda: clock["t"])
    store = CF.MemoryFlushStore()
    events = []
    p = CF.CryptoFlushPoller(store=store, client=okx, publish=events.append, clock=lambda: clock["t"],
                             armed=lambda s: armed["on"], on=True)
    assert p.running() is False
    for _ in range(12):                                                       # the OI window warms up
        assert p.tick() == []
        clock["t"] += pd.Timedelta(minutes=1)
    st = p.status()
    assert st["coins"]["BTC"]["oi_samples"] == 12 and st["coins"]["BTC"]["drop_pct"] == 0.0 and st["ticks"] == 12
    okx.px["BTC"], okx.oi["BTC"] = 56000.0, 46000.0                           # −6.7% price, −8% OI
    rows = p.tick()
    assert len(rows) == 1 and rows[0]["coin"] == "BTC" and rows[0]["trade"] is False and rows[0]["micro"] is None
    assert rows[0]["drop_pct"] == pytest.approx(-6.667, abs=0.01) and rows[0]["oi_drop_pct"] == -8.0
    assert events[-1]["type"] == "crypto_flush" and events[-1]["coin"] == "BTC"
    pb = p.playbook()
    assert pb["verdict"] == "buy" and pb["armed"] is False and pb["experimental"] is False and "not armed" in pb["reasons"][1]
    assert pb["trade"]["legs"] == "+1 MBT (0.1 BTC)"
    clock["t"] += pd.Timedelta(minutes=1)
    assert p.tick() == []                                                     # one per 24 h
    # the +1 h mark
    clock["t"] += pd.Timedelta(minutes=60)
    okx.px["BTC"] = 57120.0
    p.tick()
    r = p.signals(1)[0]
    assert r["r1h"] == pytest.approx(2.0, abs=0.01) and r["r24h"] is None and r["open"] is False
    # ETH, armed: the paper micro future is logged, entered a minute later, out at +24 h
    armed["on"] = True
    okx.px["ETH"], okx.oi["ETH"] = 2800.0, 700000.0
    rows = p.tick()
    assert rows[0]["coin"] == "ETH" and rows[0]["trade"] is True and rows[0]["micro"] == "MET" and rows[0]["entry_price"] is None
    assert p.playbook()["verdict"] == "buy" and p.playbook()["armed"] is True
    clock["t"] += pd.Timedelta(minutes=1)
    okx.px["ETH"] = 2810.0
    p.tick()
    r = next(x for x in p.signals(1) if x["coin"] == "ETH")
    assert r["entry_price"] == pytest.approx(2810.0 * 1.001, abs=0.01) and r["open"] is True and r["entry_ts"]
    assert p.playbook()["verdict"] in ("buy", "wait")
    clock["t"] += pd.Timedelta(hours=24)
    okx.px["ETH"] = 2900.0
    p.tick()
    r = next(x for x in p.signals(2) if x["coin"] == "ETH")
    assert r["exit_price"] == pytest.approx(2900.0 * 0.999, abs=0.01) and r["open"] is False
    assert r["pnl_usd"] == pytest.approx((r["exit_price"] - r["entry_price"]) * 0.1, abs=0.01) and r["r24h"] > 0
    assert p.run()["status"] == "ran"
    # a poll failure is recorded, not raised
    okx.ticker = lambda inst: (_ for _ in ()).throw(RuntimeError("451"))
    p.tick()
    assert "451" in p.status()["coins"]["BTC"]["error"]


# ── the event log, the regime and the endpoints ────────────────────────────────

def test_parse_event_and_memory_round_trip():
    now = pd.Timestamp("2026-09-25 14:00", tz=NY)
    row = ED.parse_event({"kind": "Escalation", "text": " Iran fires at tankers ", "barrels_lost": "n", "region": "Gulf"}, now)
    assert row["kind"] == "escalation" and row["barrels_lost"] == "N" and row["text"] == "Iran fires at tankers"
    assert row["ts"] == _dt.datetime(2026, 9, 25, 18, 0) and row["source"] is None
    assert ED.parse_event({"kind": "de_escalation", "text": "x"}, now)["kind"] == "de-escalation"
    assert ED.parse_event({"kind": "post", "text": "x", "ts": "2026-09-25T09:00"}, now)["ts"] == _dt.datetime(2026, 9, 25, 13, 0)
    assert ED.parse_event({"kind": "post", "text": "x", "ts": "2026-09-25T09:00:00+00:00"}, now)["ts"] == _dt.datetime(2026, 9, 25, 9, 0)
    for bad in ({"kind": "war", "text": "x"}, {"kind": "post"}, {"kind": "post", "text": "x", "barrels_lost": "maybe"},
                {"kind": "post", "text": "x", "ts": "yesterday"}, "nope"):
        with pytest.raises(ED.EventError):
            ED.parse_event(bad, now)
    store = ED.MemoryEventStore()
    desk = ED.EventDesk(None, store=store, clock=lambda: now, trades=lambda: [])
    a = desk.log_event({"kind": "escalation", "text": "one", "ts": "2026-09-20T10:00"})
    b = desk.log_event({"kind": "policy", "text": "two"})
    assert a["id"] == 1 and b["id"] == 2 and a["ts"] == "2026-09-20T10:00:00-04:00" and b["barrels_lost"] == "unknown"
    assert [e["id"] for e in desk.events(14)] == [2, 1] and desk.events(3) == [b]
    assert desk.delete_event(1) is True and desk.delete_event(1) is False and [e["id"] for e in desk.events(14)] == [2]
    assert desk.regime() == {"war": False, "note": None, "updated": None}
    r = desk.set_regime({"war": True, "note": "2026 Iran war"})
    assert r["war"] is True and r["note"] == "2026 Iran war" and r["updated"]
    with pytest.raises(ED.EventError):
        desk.set_regime({"note": "no flag"})


def test_the_endpoints():
    from fastapi.testclient import TestClient
    from api.app import create_app
    from api.bootstrap import db_guard_installed, uninstall_db_read_only_guard
    had = db_guard_installed()
    try:
        app = create_app()
        desk = app.state.event_desk
        assert isinstance(desk.store, ED.MemoryEventStore)
        clock = {"t": pd.Timestamp("2026-09-25 14:35", tz=NY)}
        desk.clock = lambda: clock["t"]
        desk.signals = ES.Signals(daily=FakeDaily(flat_world()), live=FakeLive(), clock=desk.clock)
        desk.trades = lambda: [{"playbook": "oil_fade", "trade_group_id": "TGX", "opened": "2026-09-23", "description": "USO put vertical",
                                "entry": 2.5, "mark": 2.1, "pnl": -42.0, "days_held": 2, "exit_rule": ED.EXIT_RULES["oil_fade"]}]
        assert app.state.crypto_flush.on is False                              # never polls under test
        with TestClient(app) as c:
            r = c.post("/api/events/log", json={"kind": "escalation", "region": "Iran", "text": "drone strike",
                                                "barrels_lost": "N", "source": "https://x.example"})
            assert r.status_code == 200 and r.json()["id"] == 1 and r.json()["ts"].endswith("-04:00")
            assert c.post("/api/events/log", json={"kind": "nope", "text": "x"}).status_code == 422
            assert c.post("/api/events/log", json={"kind": "post"}).status_code == 422
            assert [e["id"] for e in c.get("/api/events/log?days=14").json()] == [1]
            r = c.put("/api/events/regime", json={"war": True, "note": "2026 Iran war"})
            assert r.status_code == 200 and r.json()["war"] is True and c.get("/api/events/regime").json()["note"] == "2026 Iran war"
            assert c.put("/api/events/regime", json={"note": "x"}).status_code == 422
            j = c.get("/api/events/desk").json()
            assert j["as_of"] == "2026-09-25T14:35:00-04:00" and j["regime"]["war"] is True
            assert [s["symbol"] for s in j["signals"]] == list(ES.KEYS)
            cl = j["signals"][0]
            for k in ("last", "change_pct", "z20", "z60", "mean20", "higher_streak", "source", "as_of", "history", "name"):
                assert k in cl
            assert cl["source"] == "daily" and len(cl["history"]) == 60 and isinstance(cl["history"][0], list)
            pbs = {p["id"]: p for p in j["playbooks"]}
            assert list(pbs) == list(ED.PLAYBOOKS)
            for p in pbs.values():
                for k in ("title", "verdict", "headline", "reasons", "checklist", "trade", "armed", "experimental"):
                    assert k in p
                assert p["armed"] is False
            assert pbs["oil_fade"]["experimental"] is True and pbs["crypto_flush"]["experimental"] is False
            assert pbs["vix_note"]["verdict"] == "none" and pbs["crypto_flush"]["verdict"] == "none"
            assert j["open_trades"][0]["trade_group_id"] == "TGX" and j["open_trades"][0]["pnl"] == -42.0
            assert j["events"][0]["text"] == "drone strike" and j["signal_log"] == [] and j["crypto_flush"]["enabled"] is False
            assert c.delete("/api/events/log/1").status_code == 204 and c.delete("/api/events/log/1").status_code == 404
            assert c.get("/api/events/log").json() == []
            assert c.get("/api/events/signals?days=30").json() == []
            assert c.put("/api/events/signals/7/tag", json={"tag": "macro"}).status_code == 404
            assert c.put("/api/events/signals/7/tag", json={"tag": "bogus"}).status_code == 422
            assert c.get("/api/events/decisions").json()["decisions"] == []
            assert c.get("/api/events/decisions?playbook=nope").status_code == 422
            cf = c.get("/api/events/crypto-flush").json()
            assert cf["status"]["enabled"] is False and cf["signals"] == []
            # arming (memory store, scheduler off): the desk reflects it; nothing runs
            r = c.post("/api/runner/oil_fade/arm", json={"schedule": "once", "date": "2026-10-01"})
            assert r.status_code == 200 and r.json()[0]["kind"] == "allocator" and r.json()[0]["status"]["playbook"] == "oil_fade"
            assert {p["id"]: p["armed"] for p in c.get("/api/events/desk").json()["playbooks"]}["oil_fade"] is True
            r = c.post("/api/runner/crypto_flush/arm", json={"schedule": "weekdays"})
            assert r.status_code == 200 and r.json()[0]["status"]["armed"] is True
            assert c.delete("/api/runner/oil_fade/arm").status_code == 200
            assert c.delete("/api/runner/crypto_flush/arm").status_code == 200
            assert c.get("/api/runner/arms").json() == []
    finally:
        if not had:
            uninstall_db_read_only_guard()


# ── the database stores (throwaway keys, deleted afterwards) ───────────────────

def _db_ok() -> bool:
    try:
        from api.services.db import ping
        return ping()[0]
    except Exception:
        return False


@pytest.mark.skipif(not _db_ok(), reason="AlanStrats database unreachable")
def test_the_db_stores_round_trip():
    from sqlalchemy import text
    from api.bootstrap import db_guard_installed, install_db_read_only_guard, uninstall_db_read_only_guard
    from api.services.db import require_db
    had = db_guard_installed()
    install_db_read_only_guard()
    key = f"zz{uuid.uuid4().hex[:6]}"
    src = f"alan_trader service tests {key}"
    st, fs = ED.DbEventStore(), CF.DbFlushStore()
    ids: list[int] = []
    try:
        e = st.add_event({"ts": _dt.datetime(2026, 9, 25, 13, 0), "kind": "escalation", "region": "Iran", "text": "test",
                          "barrels_lost": "N", "source": src})
        ids.append(e["id"])
        assert e["kind"] == "escalation" and e["text"] == "test" and e["ts"] == _dt.datetime(2026, 9, 25, 13, 0)
        got = [r for r in st.events_since(_dt.datetime(2026, 9, 1)) if r["source"] == src]
        assert [r["id"] for r in got] == ids
        assert st.delete_event(e["id"]) is True and st.delete_event(e["id"]) is False
        assert st.get_setting(key) is None
        assert st.put_setting(key, {"war": True, "note": "t"})["war"] is True and st.get_setting(key)["note"] == "t"
        row = {"playbook": key, "date": D(2026, 9, 25), "status": "no_trade", "verdict": "none", "summary": "s", "detail": {"a": 1}}
        assert st.add_decision(row) is True and st.add_decision(row) is False
        d = st.decided(key, D(2026, 9, 25))
        assert d["status"] == "no_trade" and d["detail"] == {"a": 1} and st.decisions_since(D(2026, 9, 1), key)[0]["playbook"] == key
        sym = key.upper()[:8]
        s = st.add_signal({"date": D(2026, 9, 25), "symbol": sym, "close": 1.0, "change_pct": 3.0, "move_z": 2.5})
        assert s["id"] and st.add_signal({"date": D(2026, 9, 25), "symbol": sym}) is None
        assert st.update_signal(s["id"], tag="macro", note="n", tagged_at=_dt.datetime(2026, 9, 25, 22, 0))["tag"] == "macro"
        assert any(r["id"] == s["id"] for r in st.pending_signals())
        assert st.update_signal(s["id"], r3=1.0, r10=2.0, r20=3.0, half_back=True, half_back_days=2,
                                outcome_asof=D(2026, 10, 23))["half_back"] is True
        assert not any(r["id"] == s["id"] for r in st.pending_signals())
        assert st.signals_since(D(2026, 9, 1))[0]["symbol"] == sym or any(r["symbol"] == sym for r in st.signals_since(D(2026, 9, 1)))
        c = fs.add({"ts": _dt.datetime(2026, 9, 25, 7, 0), "coin": sym, "price": 1.0, "drop_pct": -6.0, "trade": True,
                    "micro": "MBT", "size": 0.1})
        assert c["trade"] is True and fs.last(sym)["id"] == c["id"] and any(r["id"] == c["id"] for r in fs.pending())
        assert fs.update(c["id"], entry_price=1.001, exit_price=1.02, r24h=2.0)["exit_price"] == 1.02
        assert not any(r["id"] == c["id"] for r in fs.pending())
    finally:
        with require_db().begin() as c:
            c.execute(text("DELETE FROM app.EventLog WHERE Source = :s"), {"s": src})
            c.execute(text("DELETE FROM app.EventDeskSetting WHERE Name = :n"), {"n": key})
            c.execute(text("DELETE FROM app.EventDeskLog WHERE Playbook = :p"), {"p": key})
            c.execute(text("DELETE FROM app.EventSignalLog WHERE Symbol = :s"), {"s": key.upper()[:8]})
            c.execute(text("DELETE FROM app.CryptoFlushSignal WHERE Coin = :s"), {"s": key.upper()[:8]})
        if not had:
            uninstall_db_read_only_guard()
