"""Multi-leg structures (a straddle, an iron fly) and the SYNTHETIC futures hedge in the paper runner
(strategy_api.live.STRUCTURE_KINDS, paper.providers.structure_quote, the runner's new fill paths, the Paper page's
marks, the arm). Offline: stub providers and engines, a temp state dir; no broker, no database, no plugin, nothing
armed. The vertical's paths are not exercised here: test_paper_poll_hook and friends keep those."""
from __future__ import annotations

import datetime as _dt
import json
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from paper.providers import Bar, LegQuote, ReplayProvider, structure_quote
from strategy_api.live import STRUCTURE_KINDS, SYNTHETIC_FUTURE_TYPE, Quote, is_structure, structure_legs

DAY = date(2026, 9, 24)
NOW = datetime(2026, 9, 24, 10, 30)
K = 30325.0


def _leg(sym, bid, ask, last=None, age_s=0.0):
    return LegQuote(sym, bid, ask, last, NOW - timedelta(seconds=age_s), NOW - timedelta(seconds=age_s))


# ── the contract ─────────────────────────────────────────────────────────────

def test_structure_legs_and_kinds():
    assert STRUCTURE_KINDS == ("straddle", "iron_fly") and is_structure("straddle") and not is_structure("call")
    assert structure_legs("straddle", K, K) == [("C", K, 1), ("P", K, 1)]
    assert structure_legs("iron_fly", K - 50, K + 50) == [("C", K, 1), ("P", K, 1), ("C", K + 50, -1), ("P", K - 50, -1)]
    with pytest.raises(ValueError):
        structure_legs("strangle", K, K + 50)
    assert Quote(1.0, 2.0, 1.5).age_s is None and Quote(1.0, 2.0, 1.5, age_s=12.0).age_s == 12.0
    assert SYNTHETIC_FUTURE_TYPE == "SynFuture" and len(SYNTHETIC_FUTURE_TYPE) <= 10     # portfolio.Security.SecurityType VARCHAR(10)


def test_structure_quote_from_the_legs_in_long_structure_terms():
    legs = structure_legs("straddle", K, K)
    q = structure_quote([_leg("C", 140.0, 143.0, 141.0, 5.0), _leg("P", 135.0, 138.0, 136.0, 65.0)], legs, NOW)
    assert q is not None and q.bid == 275.0 and q.ask == 281.0 and q.last == 278.0
    assert q.age == 1 and q.age_s == 65.0 and q.legs == ((140.0, 143.0, 0), (135.0, 138.0, 1))
    assert q.prints == ((141.0, NOW - timedelta(seconds=5)), (136.0, NOW - timedelta(seconds=65)))
    # an iron fly: the wings are sold, so their asks come off the bid and their bids off the ask; the mid is bounded
    fly = structure_legs("iron_fly", K - 100, K + 100)
    wings = [_leg("Cw", 90.0, 92.0), _leg("Pw", 88.0, 90.0)]
    qf = structure_quote([_leg("C", 140.0, 143.0), _leg("P", 135.0, 138.0), *wings], fly, NOW)
    assert qf is not None and qf.bid == pytest.approx(275.0 - 182.0) and qf.ask == pytest.approx(281.0 - 178.0) and qf.last == pytest.approx(98.0)
    qb = structure_quote([_leg("C", 140.0, 143.0), _leg("P", 135.0, 138.0), *wings], structure_legs("iron_fly", K - 50, K + 50), NOW)
    assert qb is not None and qb.last == 50.0 and qb.ask - qb.bid == pytest.approx(qf.ask - qf.bid)     # a 50-wide fly: shifted onto the bound, width kept
    # a missing, one-sided or crossed leg is no quote; a wildly wide one says nothing; too old is carried out
    assert structure_quote([_leg("C", 140.0, 143.0)], legs, NOW) is None
    assert structure_quote([_leg("C", 140.0, 143.0), LegQuote("P", None, 138.0, None, None, NOW)], legs, NOW) is None
    assert structure_quote([_leg("C", 140.0, 143.0), _leg("P", 139.0, 138.0)], legs, NOW) is None
    assert structure_quote([_leg("C", 100.0, 200.0), _leg("P", 100.0, 200.0)], legs, NOW) is None
    assert structure_quote([_leg("C", 140.0, 143.0), _leg("P", 135.0, 138.0, age_s=31 * 60)], legs, NOW, carry_min=30) is None


def test_the_replay_provider_quotes_a_straddle_from_both_legs_prints_and_names_its_legs():
    prov = ReplayProvider.__new__(ReplayProvider)
    prov.day, prov.root, prov.h, prov.carry, prov.underlying = DAY, "NDXP", 0.5, 30, "NDX"
    prov._prints = {("C", K): ([629, 631], [140.0, 150.0]), ("P", K): ([630], [135.0]), ("C", K + 100): ([630], [60.0])}
    q = prov.quote_structure("straddle", K, K, 630)
    assert q is not None and q.last == 275.0 and q.bid == 274.0 and q.ask == 276.0        # half a spread PER LEG
    assert q.age == 1 and q.age_s == 60.0                                                 # the call's print is a minute old
    assert prov.quote_structure("straddle", K, K, 631).age == 1                          # now the put's is
    assert prov.quote_structure("straddle", K + 100, K + 100, 630) is None               # no put print at that strike
    assert prov.structure_symbols("straddle", K, K) == ["NDXP260924C30325000", "NDXP260924P30325000"]
    assert prov.structure_symbols("iron_fly", K - 100, K + 100)[2:] == ["NDXP260924C30425000", "NDXP260924P30225000"]
    assert prov.quote_vertical("call", K, K + 100, 630).last == 80.0                     # the vertical's path, unchanged


# ── the runner's new fill paths ───────────────────────────────────────────────

class _Prov:
    name = "fake-live"
    underlying = "NDX"
    root = "NDXP"
    poll_seconds = 20
    expiry = DAY

    def __init__(self, clock):
        self.clock = clock
        self._samples = []
        self.fetches: list[list[str]] = []

    def load_chain(self, day):
        return 64

    def leg_symbols(self, kind, k_low, k_high):
        cp = "C" if kind == "call" else "P"
        return f"NDXP260924{cp}{int(k_low):08d}", f"NDXP260924{cp}{int(k_high):08d}"

    def structure_symbols(self, kind, k_low, k_high):
        return [f"NDXP260924{cp}{int(Kk):08d}" for cp, Kk, _ in structure_legs(kind, k_low, k_high)]

    def fetch(self, syms):
        self.fetches.append(list(syms))
        now = self.clock()
        out = {"NDX": LegQuote("NDX", None, None, 30330.0, now, now)}
        for s in syms:
            out[s] = LegQuote(s, 140.0, 143.0, 141.0, now, now)
        return out

    def sample_underlying(self, quotes, when):
        self._samples.append((when, 30330.0)); return 30330.0

    def close_minute(self, minute_start):
        return Bar(minute_start, 30330.0, 30330.0, 30330.0, 30330.0)

    def quote_vertical(self, kind, k_low, k_high, quotes, now, carry_min=30):
        return Quote(bid=1.0, ask=3.0, last=2.0, age=0)

    def quote_structure(self, kind, k_low, k_high, quotes, now, carry_min=30):
        syms = self.structure_symbols(kind, k_low, k_high)
        if any(s not in quotes for s in syms):
            return None
        return structure_quote([quotes[s] for s in syms], structure_legs(kind, k_low, k_high), now, carry_min)


class _Params:
    lookback_min = 0
    target_pts = 5.0
    entry_start_min = 24 * 60

    def as_dict(self):
        return {}


class _Hedge:
    units, avg_px, n_trades = -0.8, 30330.125, 1

    def pnl(self, S):
        return (S - self.avg_px) * self.units * 20.0


class _Pos:
    def __init__(self):
        self.direction, self.kind, self.k_low, self.k_high, self.units, self.avg_px, self.last_mark = "long", "straddle", K, K, 1, 279.0, 281.0


class _StructEngine:
    """A straddle engine: rests, fills and hedges on the first three polls, settles on the last bar."""
    max_fills_per_session = 50

    def __init__(self, blocked_reason=""):
        self.fills, self.trades, self.positions, self.closes = [], [], [], []
        self.pending = None
        self.blocked_reason = blocked_reason
        self.last_minute = 0
        self.polls: list = []
        self.hedge = _Hedge()

    def _row(self, m, kind, **kw):
        base = dict(m=m, t=f"{m // 60:02d}:{m % 60:02d}:00", kind=kind, direction="long", kl=K, kh=K, px=279.0, lots=1, cash=0.0,
                    reason=f"{kind} row", oid=1, struct="straddle")
        base.update(kw); return base

    def on_bar(self, minute, S, quote_fn, is_last=False, high=None, low=None):
        self.closes.append(S); self.last_minute = minute
        if is_last and self.positions:
            self.positions.clear()
            self.fills.append(dict(m=minute, t="16:00:00", kind="hedge", direction="buy", kl=0.0, kh=0.0, px=S + 0.125, lots=0.8, units=0.8,
                                   cash=-(0.8 * (S + 0.125) * 20) - 1.0, reason="settle: buy 0.800 NQ-eq [SYNTHETIC]", oid=9, struct="hedge",
                                   symbol="NQ=NDX", synthetic=True, final=True, ndx=S, hedge_units=0.0, hedge_avg=0.0, hedge_pnl=12.0, fee=1.0))
            self.fills.append(self._row(minute, "close", cash=27500.0 - 1.0, legs=[["C", K, 1, 275.0], ["P", K, 1, 0.0]], delta=0.0, iv=0.1,
                                        ndx=S, hedge_pnl=12.0, opt_pnl=-403.0, reason="settle spot"))
            self.trades.append({"pnl": -391.0})

    def on_poll(self, now, spot, quote_fn):
        m = now.hour * 60 + now.minute
        q = quote_fn(spot, K, K, "straddle", m)
        self.polls.append((now, spot, q))
        n = len(self.polls)
        if n == 1:
            self.fills.append(self._row(m, "rest", iv=0.09))
        elif n == 2:
            self.fills.append(self._row(m, "open", cash=-27902.0, legs=[["C", K, 1, 139.5], ["P", K, 1, 139.5]], delta=-0.16, iv=0.09, ndx=spot))
            self.positions.append(_Pos())
        elif n == 3:
            self.fills.append(dict(m=m, t=f"{now:%H:%M:%S}", kind="hedge", direction="sell", kl=0.0, kh=0.0, px=spot - 0.125, lots=0.8, units=0.8,
                                   cash=0.8 * (spot - 0.125) * 20 - 1.0, reason="entry: sell 0.800 NQ-eq [SYNTHETIC]", oid=3, struct="hedge",
                                   symbol="NQ=NDX", synthetic=True, final=False, ndx=spot, hedge_units=-0.8, hedge_avg=spot - 0.125, hedge_pnl=-1.0,
                                   fee=1.0, delta=-0.16, iv=0.09))

    def watch_structures(self):
        return [("straddle", K, K)]

    @property
    def day_pnl(self):
        return float(sum(t["pnl"] for t in self.trades))

    def marked(self):
        return 0.0

    def to_dict(self):
        return {"positions": [{"direction": "long", "kind": "straddle", "k_low": K, "k_high": K, "units": 1, "last_mark": 281.0, "mark_sign": 1}
                              for _ in self.positions],
                "hedge": {"units": self.hedge.units, "avg_px": self.hedge.avg_px, "multiplier": 20.0, "synthetic": True, "symbol": "NQ=NDX"}}


class _Strategy:
    def __init__(self, engine_cls=_StructEngine):
        self.params = _Params()
        self.engine_cls = engine_cls
        self.session = None

    def live_instrument(self):
        return {"underlying": "NDX", "root": "NDXP", "kind": "straddle"}

    def session_gate(self, day, events=None):
        return False, ""

    def live_session(self, day, blocked_reason="", bar_min=1):
        self.session = self.engine_cls(blocked_reason=blocked_reason)
        return self.session


def _run(tmp_path, monkeypatch, strategy, minutes=3, until_settle=False):
    from paper import runner as RU
    monkeypatch.setattr(RU.R, "get_strategy", lambda slug: strategy)
    monkeypatch.setattr(RU.R, "find_guide", lambda slug: None)
    monkeypatch.setattr(RU.R, "tests_dir_for", lambda slug: None)
    t = [datetime.combine(DAY, dtime(15, 58, 5) if until_settle else dtime(9, 30, 5))]

    def now_fn():
        return t[0]

    def sleep_fn(sec):
        t[0] = t[0] + timedelta(seconds=20)

    prov = _Prov(now_fn)
    ps = RU.PaperSession("stub", prov, None, write_ledger=False, log_dir=tmp_path / "log", state_dir=tmp_path / "state")
    until = dtime(16, 1) if until_settle else dtime(9, 30 + minutes)
    res = ps.run_live(day=DAY, poll_seconds=20, until=until, now_fn=now_fn, sleep_fn=sleep_fn)
    return ps, prov, res


def test_a_structure_engine_is_quoted_on_every_leg_and_its_rows_reach_the_log_with_the_hedge_labelled_synthetic(tmp_path, monkeypatch):
    strat = _Strategy()
    ps, prov, res = _run(tmp_path, monkeypatch, strat)
    eng = strat.session
    assert ps.halted is None and len(eng.polls) >= 3
    # the straddle's two legs were fetched (watch_structures, then the open position), and quoted in long-structure terms
    assert any("NDXP260924C00030325" in f and "NDXP260924P00030325" in f for f in prov.fetches)
    q = eng.polls[0][2]
    assert q is not None and q.bid == 280.0 and q.ask == 286.0 and q.age_s == 0.0
    log = pd.read_csv(tmp_path / "log" / f"{DAY.isoformat()}.csv")
    assert list(log.event) == ["rest", "open", "hedge"]
    opn = log[log.event == "open"].iloc[0]
    assert opn.struct == "straddle" and opn.symbols == "NDXP260924C00030325|NDXP260924P00030325" and opn.k_low == K and opn.fill == 279.0
    assert opn.bid == 280.0 and opn.ask == 286.0 and opn.delta == -0.16 and json.loads(opn.note)[0][:3] == ["C", K, 1]
    h = log[log.event == "hedge"].iloc[0]
    assert h.kind == "hedge" and h.symbols == "NQ=NDX" and bool(h.synthetic) is True and h.hedge_units == -0.8 and h.direction == "sell"
    assert "SYNTHETIC" in h.note and "SYNTHETIC" in h.reason and h.units == 0.8 and h.fill == pytest.approx(30330.0 - 0.125)
    # without a ledger the unit and the hedge book are still tracked, and the state carries the hedge's ledger id slot
    assert ps._tgids == {("straddle", "long", K, K): [-1]} and ps._hedge_pid == -1
    state = json.loads((tmp_path / "state" / f"stub_{DAY.isoformat()}.json").read_text(encoding="utf-8"))
    assert state["hedge_pid"] == -1 and "straddle|long|30325.0|30325.0" in state["tgids"]
    hb = json.loads((tmp_path / "state" / "heartbeat_stub.json").read_text(encoding="utf-8"))
    assert hb["hedge"]["synthetic"] is True and hb["hedge"]["units"] == -0.8 and hb["hedge"]["symbol"] == "NQ=NDX" and hb["hedge"]["pnl"] is not None
    # the open straddle was marked off its structure quote at every poll (the marks file; the final heartbeat carries none)
    marks = pd.read_csv(tmp_path / "log" / f"marks_{DAY.isoformat()}.csv")
    assert len(marks) >= 1 and (marks.mid == 283.0).all() and (marks.k_low == K).all()


def test_the_settlement_closes_the_hedge_book_and_the_structure_and_the_state_restores_the_hedge_id(tmp_path, monkeypatch):
    strat = _Strategy()
    ps, prov, res = _run(tmp_path, monkeypatch, strat, until_settle=True)
    log = pd.read_csv(tmp_path / "log" / f"{DAY.isoformat()}.csv")
    assert list(log.event) == ["rest", "open", "hedge", "hedge", "close"]
    final = log[log.event == "hedge"].iloc[-1]
    assert final.hedge_units == 0.0 and final.direction == "buy" and final.minute == 960
    assert ps._hedge_pid is None and ps._tgids[("straddle", "long", K, K)] == []
    assert log[log.event == "close"].iloc[0].hedge_pnl == 12.0 and res.day_pnl == -391.0
    # a restore reads the hedge id and the structure's tgids back (the strikes as floats)
    from paper import runner as RU
    ps2 = RU.PaperSession("stub", prov, None, write_ledger=False, log_dir=tmp_path / "log", state_dir=tmp_path / "state")
    p = ps2._state_path(DAY)
    d = json.loads(p.read_text(encoding="utf-8")); d["finished"] = False; d["hedge_pid"] = 77; d["tgids"] = {"straddle|long|30325.0|30325.0": [78]}
    p.write_text(json.dumps(d), encoding="utf-8")
    monkeypatch.setattr(ps2.strategy, "live_session", lambda day, blocked_reason="": _StructEngine(), raising=False)
    monkeypatch.setattr(type(ps2.strategy.live_session(DAY)), "from_dict", classmethod(lambda cls, p, d: _StructEngine()), raising=False)
    ps2._restore(DAY, "")
    assert ps2._hedge_pid == 77 and ps2._tgids == {("straddle", "long", K, K): [78]}


def test_the_ledger_writers_are_called_for_structure_and_hedge_rows_with_the_ids_threaded_through(tmp_path, monkeypatch):
    from paper import runner as RU
    calls = []

    def fake_struct(db, aid, slug, und, expiry, day, f, syms, position_id=None, extra=None):
        calls.append(("struct", f["kind"], syms, position_id)); return 501

    def fake_hedge(db, aid, slug, und, day, f, position_id=None, extra=None):
        calls.append(("hedge", f["direction"], position_id, f.get("final"))); return 601

    monkeypatch.setattr(RU.L, "record_structure_fill", fake_struct)
    monkeypatch.setattr(RU.L, "record_synthetic_hedge", fake_hedge)
    monkeypatch.setattr(RU.L, "ensure_paper_account", lambda db, name, starting_cash=None: 99)
    monkeypatch.setattr(RU.R, "get_strategy", lambda slug: _Strategy())
    monkeypatch.setattr(RU.R, "find_guide", lambda slug: None)
    monkeypatch.setattr(RU.R, "tests_dir_for", lambda slug: None)
    prov = _Prov(lambda: datetime.combine(DAY, dtime(10, 30)))
    ps = RU.PaperSession("stub", prov, object(), write_ledger=True, log_dir=tmp_path / "log", state_dir=tmp_path / "state")
    eng = _StructEngine()
    for n in range(3):
        eng.on_poll(datetime.combine(DAY, dtime(10, 30 + n)), 30330.0, lambda *a: None)
    ps._write_new_fills(eng, DAY, DAY, 30330.0, prov.leg_symbols)
    eng.on_bar(960, 30400.0, lambda *a: None, is_last=True)
    ps._write_new_fills(eng, DAY, DAY, 30400.0, prov.leg_symbols)
    assert calls == [("struct", "open", ["NDXP260924C00030325", "NDXP260924P00030325"], None),
                     ("hedge", "sell", None, False),
                     ("hedge", "buy", 601, True),
                     ("struct", "close", ["NDXP260924C00030325", "NDXP260924P00030325"], 501)]
    assert ps._hedge_pid is None and ps._tgids[("straddle", "long", K, K)] == []


# ── the Paper page's marks and the arm ───────────────────────────────────────

def test_runner_marks_carry_a_short_structures_sign_and_the_synthetic_hedge_at_the_spot(tmp_path, monkeypatch):
    from paper import views as V
    state = {"state": {"positions": [{"direction": "short", "kind": "straddle", "k_low": K, "k_high": K, "units": 1, "last_mark": 250.0, "mark_sign": -1}],
                       "hedge": {"units": 2.5, "avg_px": 30300.0, "multiplier": 20.0, "synthetic": True}},
             "tgids": {"straddle|short|30325.0|30325.0": [4001]}, "hedge_pid": 4002, "provider": "tastytrade"}
    f = tmp_path / f"ndx_gamma_scalp_{_dt.date.today().isoformat()}.json"
    f.write_text(json.dumps(state), encoding="utf-8")
    (tmp_path / "heartbeat_ndx_gamma_scalp.json").write_text(json.dumps({"at": datetime.now().isoformat(timespec="seconds"), "spot": 30400.0,
                                                                           "live_marks": {f"short|{K}|{K}": 260.0}}), encoding="utf-8")
    monkeypatch.setattr(V, "_glob_state", lambda pattern: [f])
    marks = V.paper_runner_marks()
    assert marks["4001"] == (-260.0, 1.0, "tastytrade")                    # a short straddle: a liability, at the live mark
    assert marks["4002"][0] == 30400.0 and marks["4002"][1] == pytest.approx(0.5) and "synthetic hedge" in marks["4002"][2]
    # so the page's option arithmetic (mark x units x 100) gives the hedge's value: 2.5 NQ-eq x 30400 x $20
    assert marks["4002"][0] * marks["4002"][1] * 100.0 == pytest.approx(2.5 * 30400.0 * 20.0)
    # a vertical's state is read exactly as before
    state2 = {"state": {"positions": [{"direction": "bull", "k_low": 30100.0, "k_high": 30200.0, "units": 1, "last_mark": 60.0}]},
              "tgids": {"bull|30100.0|30200.0": [5001]}, "provider": "tastytrade"}
    f.write_text(json.dumps(state2), encoding="utf-8")
    assert V.paper_runner_marks() == {"5001": (60.0, 1.0, "tastytrade")}


def test_risk_treats_the_synthetic_future_as_a_linear_leg():
    from api.services import risk as RK
    grp = pd.DataFrame([{"Symbol": "NQ=NDX", "Underlying": "NDX", "SecurityType": SYNTHETIC_FUTURE_TYPE, "OptionType": None, "Strike": None,
                         "Expiration": None, "Multiplier": 20, "Direction": "Sell", "Quantity": 2.5, "TransactionPrice": 30300.0}])
    legs = RK.net_legs(grp)
    assert len(legs) == 1 and legs[0].type == "stock" and not legs[0].is_option and legs[0].qty == -2.5 and legs[0].mult == 20.0
    assert RK.describe_structure(legs) == "short stock 2.5"


def test_the_gamma_scalp_arm_spec():
    from api.services import arms as A
    spec = A.SPECS["ndx_gamma_scalp"]
    assert spec.kind == "runner" and spec.at == _dt.time(9, 45) and spec.until == _dt.time(10, 30) and spec.variants == ("",)
    assert "synthetic" in spec.label and "never armed by default" in spec.label
    cmd = A.runner_command("ndx_gamma_scalp", Path(r"C:\l\g.log"), Path(r"C:\csv"), py=r"D:\venv\python.exe")
    assert "-m api.runner_launch --strategy ndx_gamma_scalp --poll 15" in cmd and "--ledger" not in cmd and "--replay" not in cmd
