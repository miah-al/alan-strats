"""A put vertical booked by call parity (ndx_gamma_walls) is marked off the calls, wherever the service marks it.

The walls strategy sells a call credit spread and books it as the equivalent bear put spread ("priced via call
parity" in its entry note). The calls are the quoted side; on 2026-09-25 the same 32.1 mark, taken from the deep
in-the-money puts' own quotes, showed as -$732 and -$257 five minutes apart. So: the runner's quote_fn (the
heartbeat's ``marked`` and the state's last_mark), its live_marks and live_legs, and the API's hub fallback all
price such a position as width - the call spread, from the calls' quotes. Any other position is marked as before.
"""
from __future__ import annotations

import json
from datetime import date, datetime, time as dtime, timedelta

import pandas as pd
import pytest

from paper.providers import Bar, LegQuote, PARITY_TAG, parity_leg_mid, parity_put_quote, vertical_quote
from strategy_api.live import Quote

DAY = date(2026, 9, 25)
NOW = datetime(2026, 9, 25, 10, 0, 0)
SPOT = 30573.0
KL, KH = 30625.0, 30675.0          # the walls trade: calls 30625/30675 sold, booked as the 30625/30675 put spread
PL, PH = 30500.0, 30550.0          # an ordinary put spread, marked on its own legs
# the quotes of 2026-09-25 (paper/spread_model.py): out-of-the-money calls a point or two wide, the puts 10+ wide
BOOK = {"C30625": (33.7, 37.2), "C30675": (19.5, 21.9), "P30675": (115.5, 126.4), "P30625": (81.7, 92.1),
        "P30550": (100.0, 104.0), "P30500": (70.0, 73.0), "C30550": (50.0, 52.0), "C30500": (80.0, 83.0)}


def _sym(cp, k):
    return f"NDXP260925{cp}{int(k * 1000):08d}"


def _leg(cp, k, when=NOW):
    b, a = BOOK[f"{cp}{int(k)}"]
    return LegQuote(_sym(cp, k), b, a, (b + a) / 2, when, when)


def test_the_put_spread_quote_from_the_call_spread_is_as_wide_as_the_calls():
    qc = vertical_quote(_leg("C", KL), _leg("C", KH), NOW)                   # long 30625 / short 30675 call: 11.8 / 17.7
    assert qc.bid == pytest.approx(11.8) and qc.ask == pytest.approx(17.7) and qc.last == pytest.approx(14.75)
    qp = parity_put_quote(qc, KH - KL)
    assert qp.bid == pytest.approx(50 - 17.7) and qp.ask == pytest.approx(50 - 11.8) and qp.last == pytest.approx(35.25)
    assert qp.age == qc.age and qp.ask - qp.bid == pytest.approx(qc.ask - qc.bid)
    own = vertical_quote(_leg("P", KH), _leg("P", KL), NOW, max_width=50.0)   # the puts' own quote: 23.4 / 44.7
    assert own.ask - own.bid == pytest.approx(21.3) and own.last == pytest.approx(34.05)
    assert parity_put_quote(None, 50.0) is None and parity_put_quote(qc, 0.0) is None
    # a call quote that says the vertical is worth more than its width prices the put at nothing, never below
    assert parity_put_quote(Quote(bid=49.0, ask=53.0, last=51.0, age=0), 50.0).last == 0.0
    # leg by leg: put = call - (spot - strike); the two legs difference to the spread's parity value
    p_hi, p_lo = parity_leg_mid(20.7, SPOT, KH), parity_leg_mid(35.45, SPOT, KL)
    assert p_hi == pytest.approx(122.7) and p_lo == pytest.approx(87.45) and p_hi - p_lo == pytest.approx(35.25)
    assert parity_leg_mid(1.0, 31000.0, 30500.0) == 0.0


# ── the runner ────────────────────────────────────────────────────────────────

class _Prov:
    name = "fake-live"
    underlying = "NDX"
    root = "NDXP"
    poll_seconds = 20
    expiry = DAY

    def __init__(self, clock):
        self.clock = clock
        self.fetches: list[list[str]] = []

    def load_chain(self, day):
        return 64

    def leg_symbols(self, kind, k_low, k_high):
        cp = "C" if kind == "call" else "P"
        long_k, short_k = (k_low, k_high) if kind == "call" else (k_high, k_low)
        return _sym(cp, long_k), _sym(cp, short_k)

    def fetch(self, syms):
        self.fetches.append(list(syms))
        now = self.clock()
        out = {"NDX": LegQuote("NDX", None, None, SPOT, now, now)}
        for s in syms:
            cp, k = s[10], int(s[11:]) / 1000              # NDXP + yymmdd, then the right and the strike x 1000
            out[s] = _leg(cp, k, now)
        return out

    def sample_underlying(self, quotes, when):
        return SPOT

    def close_minute(self, minute_start):
        return Bar(minute_start, SPOT, SPOT, SPOT, SPOT)

    def quote_vertical(self, kind, k_low, k_high, quotes, now, carry_min=30):
        ls, ss = self.leg_symbols(kind, k_low, k_high)
        if ls not in quotes or ss not in quotes:
            return None
        return vertical_quote(quotes[ls], quotes[ss], now, carry_min, max_width=abs(k_high - k_low))


class _Pos:
    def __init__(self, k_low, k_high, note):
        self.direction, self.kind, self.k_low, self.k_high, self.units, self.avg_px, self.last_mark, self.note = \
            "bear", "put", k_low, k_high, 1, 33.0, None, note


class _Engine:
    """Holds the walls trade (booked by parity) and an ordinary put spread; marks both through quote_fn on every bar."""
    max_fills_per_session = 50

    def __init__(self, blocked_reason=""):
        self.fills, self.trades, self.closes = [], [], []
        self.positions = [_Pos(KL, KH, f"wall 30650 mapB | {PARITY_TAG} | call 30625/30675 ... (the credit) | rank 5"),
                          _Pos(PL, PH, "wall 30500 mapB | priced via put quote | ...")]
        self.pending = None
        self.blocked_reason = blocked_reason
        self.last_minute = 0
        self.quotes_seen: list = []

    def on_bar(self, minute, S, quote_fn, is_last=False, high=None, low=None):
        self.closes.append(S); self.last_minute = minute
        for pos in self.positions:
            q = quote_fn(S, pos.k_low, pos.k_high, pos.kind, minute)
            self.quotes_seen.append((pos.k_low, q))
            if q is not None:
                pos.last_mark = (q.bid + q.ask) / 2.0

    @property
    def day_pnl(self):
        return 0.0

    def marked(self):
        return sum(((p.last_mark if p.last_mark is not None else p.avg_px) - p.avg_px) * 100.0 * p.units for p in self.positions)

    def to_dict(self):
        return {"positions": [{"direction": p.direction, "kind": p.kind, "k_low": p.k_low, "k_high": p.k_high, "units": p.units,
                               "last_mark": p.last_mark, "note": p.note} for p in self.positions]}


class _Params:
    lookback_min = 0
    target_pts = 5.0
    entry_start_min = 24 * 60

    def as_dict(self):
        return {}


class _Strategy:
    def __init__(self):
        self.params = _Params()
        self.session = None

    def live_instrument(self):
        return {"underlying": "NDX", "root": "NDXP", "width": 50.0}

    def session_gate(self, day, events=None):
        return False, ""

    def live_session(self, day, blocked_reason="", bar_min=1):
        self.session = _Engine(blocked_reason=blocked_reason)
        return self.session


def _spy_heartbeats(monkeypatch, RU) -> list:
    """Every heartbeat's (live_marks, live_legs): the final 'finished' heartbeat carries none, so the file alone
    cannot show what the polls published."""
    seen: list = []
    orig = RU.PaperSession._heartbeat

    def spy(self, day, now, session, note="", live_marks=None, live_legs=None, spot=None):
        if live_marks:
            seen.append((dict(live_marks), dict(live_legs or {})))
        return orig(self, day, now, session, note, live_marks, live_legs, spot)

    monkeypatch.setattr(RU.PaperSession, "_heartbeat", spy)
    return seen


def test_the_runner_marks_a_parity_booked_put_spread_off_the_calls_and_the_others_off_their_own_legs(tmp_path, monkeypatch):
    from paper import runner as RU
    strat = _Strategy()
    beats = _spy_heartbeats(monkeypatch, RU)
    monkeypatch.setattr(RU.R, "get_strategy", lambda slug: strat)
    monkeypatch.setattr(RU.R, "find_guide", lambda slug: None)
    monkeypatch.setattr(RU.R, "tests_dir_for", lambda slug: None)
    t = [datetime.combine(DAY, dtime(9, 30, 5))]

    def now_fn():
        return t[0]

    def sleep_fn(sec):
        t[0] = t[0] + timedelta(seconds=20)

    prov = _Prov(now_fn)
    ps = RU.PaperSession("stub", prov, None, write_ledger=False, log_dir=tmp_path / "log", state_dir=tmp_path / "state")
    ps.run_live(day=DAY, poll_seconds=20, until=dtime(9, 33), now_fn=now_fn, sleep_fn=sleep_fn)
    eng = strat.session
    assert ps.halted is None and eng.closes
    # the calls of the parity trade are watched on every poll, beside its own puts; the ordinary spread's calls are not
    assert all({_sym("C", KL), _sym("C", KH), _sym("P", KL), _sym("P", KH)} <= set(f) for f in prov.fetches)
    assert not any(_sym("C", PL) in f or _sym("C", PH) in f for f in prov.fetches)
    # the engine's own mark (quote_fn): the parity trade at width - the call spread, the other at its puts' mid
    seen = {k: q for k, q in eng.quotes_seen}
    assert seen[KL].last == pytest.approx(35.25) and seen[KL].bid == pytest.approx(32.3) and seen[KL].ask == pytest.approx(38.2)
    assert seen[PL].last == pytest.approx(30.5) and seen[PL].bid == pytest.approx(27.0)
    parity_pos, plain_pos = eng.positions
    assert parity_pos.last_mark == pytest.approx(35.25) and plain_pos.last_mark == pytest.approx(30.5)
    # the heartbeat: ``marked`` from those, live_marks per position, and the parity trade's legs priced off the calls
    hb = json.loads((tmp_path / "state" / "heartbeat_stub.json").read_text(encoding="utf-8"))
    assert hb["marked"] == round((35.25 - 33.0) * 100 + (30.5 - 33.0) * 100, 0)
    assert beats and all(lm == {f"bear|{KL}|{KH}": 35.25, f"bear|{PL}|{PH}": 30.5} for lm, _ in beats)
    legs = beats[-1][1]
    assert legs[_sym("P", KH)] == pytest.approx(122.7) and legs[_sym("P", KL)] == pytest.approx(87.45)
    assert legs[_sym("P", PH)] == pytest.approx(102.0) and legs[_sym("P", PL)] == pytest.approx(71.5)
    # the saved state carries the parity mark, which is what the API reads when the heartbeat is stale
    state = json.loads((tmp_path / "state" / f"stub_{DAY.isoformat()}.json").read_text(encoding="utf-8"))
    assert [p["last_mark"] for p in state["state"]["positions"]] == [pytest.approx(35.25), pytest.approx(30.5)]
    # and the intra-bar marks log rows carry the parity quote for the parity trade
    marks = pd.read_csv(tmp_path / "log" / f"marks_{DAY.isoformat()}.csv")
    assert set(marks[marks.k_low == KL].mid.round(2)) == {35.25} and set(marks[marks.k_low == PL].mid.round(2)) == {30.5}


def test_a_restored_session_without_a_note_falls_back_to_the_puts_own_quote(tmp_path, monkeypatch):
    """The parity tag lives on the position; an engine that does not carry one is marked as it always was."""
    from paper import runner as RU
    strat = _Strategy()
    beats = _spy_heartbeats(monkeypatch, RU)
    monkeypatch.setattr(RU.R, "get_strategy", lambda slug: strat)
    monkeypatch.setattr(RU.R, "find_guide", lambda slug: None)
    monkeypatch.setattr(RU.R, "tests_dir_for", lambda slug: None)
    t = [datetime.combine(DAY, dtime(9, 30, 5))]
    prov = _Prov(lambda: t[0])

    class _Bare(_Engine):
        def __init__(self, blocked_reason=""):
            super().__init__(blocked_reason)
            self.positions = [_Pos(KL, KH, "")]

    strat.live_session = lambda day, blocked_reason="", bar_min=1: setattr(strat, "session", _Bare(blocked_reason)) or strat.session
    ps = RU.PaperSession("stub", prov, None, write_ledger=False, log_dir=tmp_path / "log", state_dir=tmp_path / "state")
    ps.run_live(day=DAY, poll_seconds=20, until=dtime(9, 32), now_fn=lambda: t[0], sleep_fn=lambda s: t.__setitem__(0, t[0] + timedelta(seconds=20)))
    assert beats and all(lm == {f"bear|{KL}|{KH}": 34.05} for lm, _ in beats) and not any(_sym("C", KL) in f for f in prov.fetches)
    assert beats[-1][1][_sym("P", KH)] == pytest.approx(120.95)                     # its own leg's mid, as before


# ── the API's hub fallback (no runner mark in hand) ───────────────────────────

def _group(note: str, cp: str = "P"):
    """A two-leg vertical as api.services.paper.load() hands it out: long the high strike, short the low."""
    notes = json.dumps({"spread_px": 33.0, "kind": "open", "reason": note, "k_low": KL, "k_high": KH, "direction": "bear"})
    rows = [dict(Symbol=_sym(cp, KH), SecurityType="Option", OptionType="PUT" if cp == "P" else "CALL", Strike=KH, Expiration=pd.Timestamp(DAY),
                 Direction="Buy", Quantity=1, Multiplier=100, TransactionPrice=120.0, Notes=notes, Underlying="NDX", StrategyName="ndx_gamma_walls"),
            dict(Symbol=_sym(cp, KL), SecurityType="Option", OptionType="PUT" if cp == "P" else "CALL", Strike=KL, Expiration=pd.Timestamp(DAY),
                 Direction="Sell", Quantity=1, Multiplier=100, TransactionPrice=87.0, Notes=notes, Underlying="NDX", StrategyName="ndx_gamma_walls")]
    return pd.DataFrame(rows)


def _hub_quote(sym, bid, ask):
    return {"symbol": sym, "bid": bid, "ask": ask, "mid": (bid + ask) / 2, "source": "tastytrade"}


class _Hub:
    providers = [object()]

    def __init__(self):
        self.asked: list = []

    def snapshot(self, syms, wait=0.0):
        self.asked.append(sorted(syms))
        out = []
        for s in syms:
            if s.startswith("NDXP"):
                b, a = BOOK[f"{s[10]}{int(int(s[11:]) / 1000)}"]
                out.append(_hub_quote(s, b, a))
        return out


def test_the_api_hub_fallback_values_a_parity_group_off_the_calls_and_says_so(monkeypatch):
    from api.services import paper as P
    monkeypatch.setattr(P, "_today", lambda: DAY)
    grp = _group(f"wall 30650 mapB | {PARITY_TAG} | call 30625/30675 bid 33.7 ask 37.2 mid 35.45 age 0 (the credit) | rank 5")
    assert P._parity_group(grp) and not P._parity_group(_group("wall 30650 mapB | priced via put quote | ..."))
    assert not P._parity_group(_group(f"x | {PARITY_TAG} | y", cp="C"))                     # only a put vertical
    assert P._parity_call_symbols(grp) == {_sym("P", KH): _sym("C", KH), _sym("P", KL): _sym("C", KL)}
    hub = _Hub()
    quotes = P._hub_quotes({"NDX-NDX_GAMM-77": grp}, {}, hub)
    assert {_sym("C", KL), _sym("C", KH)} <= set(quotes) and {_sym("P", KL), _sym("P", KH)} <= set(quotes)
    mv, src, n = P._hub_value("NDX-NDX_GAMM-77", grp, {}, quotes)
    assert mv == pytest.approx((50.0 - 14.75) * 100) and n == 2 and src == "market data (tastytrade) by call parity"
    # the same legs without the note: the puts' own mids, as before (bounded to the width)
    plain = _group("wall 30650 mapB | priced via put quote | ...")
    mv2, src2, _ = P._hub_value("NDX-NDX_GAMM-78", plain, {}, P._hub_quotes({"NDX-NDX_GAMM-78": plain}, {}, hub))
    assert mv2 == pytest.approx((120.95 - 86.9) * 100) and src2 == "market data (tastytrade)"
    # a call left unquoted: no parity value, and the legs' own quotes stand in
    partial = {k: v for k, v in quotes.items() if k != _sym("C", KH)}
    assert P._parity_value(grp, partial) is None and P._hub_value("NDX-NDX_GAMM-77", grp, {}, partial)[0] == pytest.approx(mv2)
    # the runner's own mark still wins over the hub
    assert P._hub_value("NDX-NDX_GAMM-77", grp, {"77": (35.25, 1.0, "tastytrade")}, quotes) is None
