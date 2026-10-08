"""The pair runner (paper/pair_runner.py): a strategy that trades two indexes at once, driven by a scripted clock against
fake per-index providers (no broker, no database). It must build both indexes' minute bars, quote the verticals the
engine picks on the fly, book every structure fill as one ledger position per vertical whose cash adds up to the
fill's, and leave the state, heartbeat and logs in the shapes the service reads."""
from __future__ import annotations

import json
import math
from datetime import date, datetime, time as dtime, timedelta

import numpy as np
import pytest

from api.bootstrap import bootstrap

bootstrap()                         # the strategy plugin, loaded by path as the service and the runner load it

from paper import ledger as L  # noqa: E402
from paper import pair_runner as PR  # noqa: E402
from paper.providers import Bar, LegQuote, vertical_quote  # noqa: E402

SLUG = "ndx_spx_ratio"
DAY = date(2026, 10, 8)


def _ncdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _bs(S, K, T, sig, call):
    if T <= 0:
        return max(S - K, 0.0) if call else max(K - S, 0.0)
    sq = sig * math.sqrt(T)
    d1 = (math.log(S / K) + 0.5 * sq * sq) / sq
    d2 = d1 - sq
    return S * _ncdf(d1) - K * _ncdf(d2) if call else K * _ncdf(-d2) - S * _ncdf(-d1)


def paths(seed=7):
    """NDX and SPX together, NDX's own noise stationary around SPX, and two stretches the fade must take: NDX 60 points
    ahead at 11:00, 60 behind at 13:30, each given back over half an hour."""
    rng = np.random.default_rng(seed)
    n = 390
    m = rng.normal(0, 0.0004, n)
    rel = rng.normal(0, 0.00005, n)
    spx = 7800 * np.exp(np.cumsum(m))
    ndx = 31000 * np.exp(np.cumsum(m) + rel)
    for at, size in ((88, 60.0), (238, -60.0)):
        ndx[at:at + 30] += np.linspace(size, 0.0, 30)
    return ndx, spx


class FakeIndexProvider:
    """Looks like TastytradeProvider to the pair runner: the index level from a scripted path, every option leg a model
    price +/- half a point, stamped now."""
    name = "fake-live"

    def __init__(self, index, root, path, clock, sig):
        self.underlying, self.root, self.path, self.clock, self.sig = index, root, path, clock, sig
        self.expiry = DAY
        self._samples = []
        self.fetch_calls = 0
        self.symbols_seen = set()

    def load_chain(self, day):
        return 120

    def leg_symbols(self, kind, k_low, k_high):
        cp = "C" if kind == "call" else "P"
        lk, sk = (k_low, k_high) if kind == "call" else (k_high, k_low)
        return f"{self.root}{cp}{lk:.0f}", f"{self.root}{cp}{sk:.0f}"

    def _level(self, now):
        t = (now.hour * 60 + now.minute) - 570
        return float(self.path[min(max(t, 0), 389)])

    def fetch(self, syms):
        self.fetch_calls += 1
        self.symbols_seen.update(syms)
        now = self.clock()
        S = self._level(now)
        out = {self.underlying: LegQuote(self.underlying, None, None, S, now, now)}
        T = max(0.0, 960 - (now.hour * 60 + now.minute + 1)) / (252 * 390)
        for s in syms:
            cp, K = s[len(self.root)], float(s[len(self.root) + 1:])
            v = _bs(S, K, T, self.sig, cp == "C")
            out[s] = LegQuote(s, max(0.0, v - 0.5), v + 0.5, None, None, now)
        return out

    def sample_underlying(self, quotes, when):
        q = quotes.get(self.underlying)
        if q is not None and q.last is not None:
            self._samples.append((when, q.last))
            return q.last
        return None

    def close_minute(self, minute_start):
        end = minute_start + timedelta(minutes=1)
        s = [px for t, px in self._samples if minute_start <= t < end]
        self._samples = [(t, px) for t, px in self._samples if t >= end]
        return Bar(minute_start, s[0], max(s), min(s), s[-1]) if s else None

    def quote_vertical(self, kind, k_low, k_high, quotes, now, carry_min=30):
        ls, ss = self.leg_symbols(kind, k_low, k_high)
        if ls not in quotes or ss not in quotes:
            return None
        return vertical_quote(quotes[ls], quotes[ss], now, carry_min, max_width=abs(k_high - k_low))

    def backfill_bars(self, day, until):
        out = []
        t = datetime.combine(day, dtime(9, 30))
        while t < until:
            px = self._level(t)
            out.append(Bar(t, px, px, px, px))
            t += timedelta(minutes=1)
        return out


@pytest.fixture
def strategy():
    from strategy_api import registry as R
    try:
        return R.get_strategy(SLUG)
    except Exception as exc:                                     # the plugin checkout without the strategy
        pytest.skip(f"{SLUG} not installed: {exc}")


@pytest.fixture
def ledger(monkeypatch):
    """The ledger writes, captured (no database)."""
    calls = []
    ids = iter(range(5001, 9000))
    monkeypatch.setattr(L, "ensure_paper_account", lambda *a, **k: 77)
    monkeypatch.setattr(L, "record_session", lambda *a, **k: None)
    monkeypatch.setattr(L, "record_day_balance", lambda *a, **k: calls.append(("balance", a, k)))
    monkeypatch.setattr(L, "account_day_pnl", lambda *a, **k: 0.0)

    def rec(engine, account_id, slug, underlying, expiry, day, fill, symbols, position_id=None, extra=None):
        pid = next(ids) if fill["kind"] == "open" else position_id
        calls.append(("structure", dict(underlying=underlying, fill=dict(fill), symbols=list(symbols), position_id=position_id,
                                        returned=pid, extra=dict(extra or {}))))
        return pid
    monkeypatch.setattr(L, "record_structure_fill", rec)
    monkeypatch.setattr(PR.PairSession, "_other_runners_active", lambda self, day: [])
    return calls


def _run(tmp_path, start=dtime(9, 29, 50), until=PR.PAIR_UNTIL, write_ledger=True, controls=None):
    """``controls(now)`` -> the supervisor's rows at that moment (paper/supervisor.py's shape); none by default."""
    ndx, spx = paths()
    t = [datetime.combine(DAY, start)]
    now_fn = lambda: t[0]                                         # noqa: E731

    def sleep_fn(sec):
        t[0] = t[0] + timedelta(seconds=max(1.0, float(sec)))
    provs = {"NDX": FakeIndexProvider("NDX", "NDXP", ndx, now_fn, 0.07),
             "SPX": FakeIndexProvider("SPX", "SPXW", spx, now_fn, 0.05)}
    ps = PR.PairSession(SLUG, provs, (object() if write_ledger else None), write_ledger=write_ledger,
                        log_dir=tmp_path / "log", state_dir=tmp_path / "state",
                        controls_fn=(lambda slug: (controls(now_fn()) if controls else {})))
    res = ps.run_live(day=DAY, poll_seconds=10, until=until, now_fn=now_fn, sleep_fn=sleep_fn)
    return ps, res, provs


def test_a_day_books_each_structure_as_two_positions(tmp_path, strategy, ledger):
    ps, res, provs = _run(tmp_path)
    assert not ps.halted and not res.blocked
    assert res.bars >= 370
    assert len(res.trades) >= 2
    sells = [t for t in res.trades if t["direction"] == "short"]
    buys = [t for t in res.trades if t["direction"] == "long"]
    assert sells and buys                                        # NDX ran ahead at 11:00, fell behind at 13:30
    rows = [c[1] for c in ledger if c[0] == "structure"]
    assert len(rows) == 4 * len(res.trades)                      # open + close, NDX + SPX, per trade
    opens = [f for f in res.fills if f["kind"] == "open"]
    for f in opens:
        mine = [r for r in rows if r["fill"]["kind"] == "open" and r["fill"]["m"] == f["m"]]
        assert sorted(r["underlying"] for r in mine) == ["NDX", "SPX"]
        by = {r["underlying"]: r for r in mine}
        assert by["NDX"]["fill"]["lots"] == 1 and by["SPX"]["fill"]["lots"] == 4
        assert by["NDX"]["fill"]["struct"] == "ndx_call_vertical" and by["SPX"]["fill"]["struct"] == "spx_put_vertical"
        assert by["NDX"]["symbols"][0].startswith("NDXPC") and by["SPX"]["symbols"][0].startswith("SPXWP")
        # the two positions' cash is the structure's cash (commission included)
        assert by["NDX"]["fill"]["cash"] + by["SPX"]["fill"]["cash"] == pytest.approx(f["cash"], abs=0.05)
        # legs in long-structure terms, one symbol each, the leg prices differencing to the vertical's price
        for r in mine:
            (cp1, k1, s1, p1), (cp2, k2, s2, p2) = r["fill"]["legs"]
            assert (s1, s2) == (1, -1) and p1 - p2 == pytest.approx(r["fill"]["px"], abs=0.01)
    closes = [r for r in rows if r["fill"]["kind"] == "close"]
    assert all(r["position_id"] is not None for r in closes)     # every close finds the position its open made
    assert sorted(r["position_id"] for r in closes) == sorted(r["returned"] for r in rows if r["fill"]["kind"] == "open")
    assert any(c[0] == "balance" for c in ledger)


def test_state_heartbeat_and_logs(tmp_path, strategy, ledger):
    ps, res, provs = _run(tmp_path)
    st = json.loads((tmp_path / "state" / f"{SLUG}_{DAY.isoformat()}.json").read_text(encoding="utf-8"))
    assert st["finished"] is True and st["provider"] == "fake-live" and st["pair"] == ["NDX", "SPX"]
    assert st["state"]["positions"] == [] and st["state"]["day_pnl"] == pytest.approx(res.day_pnl, abs=0.01)
    hb = json.loads((tmp_path / "state" / f"heartbeat_{SLUG}.json").read_text(encoding="utf-8"))
    assert hb["note"] == "finished" and hb["underlying"] == "NDX" and set(hb["spots"]) == {"NDX", "SPX"}
    import pandas as pd
    log = pd.read_csv(tmp_path / "log" / f"{DAY.isoformat()}.csv")
    o = log[log.event == "open"]
    assert len(o) == len(res.trades) and o.ndx_vertical.str.endswith("call").all() and (o.spx_qty == 4).all()
    assert (tmp_path / "log" / f"decisions_{DAY.isoformat()}.csv").exists()
    u = pd.read_csv(tmp_path / "log" / f"underlying_{DAY.isoformat()}.csv")
    assert list(u.columns) == ["ts", "NDX", "SPX", "source"] and len(u) >= 370


def test_a_late_start_backfills_both_indexes_and_trades_the_same(tmp_path, strategy, ledger):
    _, full, _ = _run(tmp_path / "full")
    ps, late, _ = _run(tmp_path / "late", start=dtime(10, 40, 5))
    assert late.trades and [t["pnl"] for t in late.trades] == [t["pnl"] for t in full.trades if t["entry_time"] > "10:40"]
    u = (tmp_path / "late" / "log" / f"underlying_{DAY.isoformat()}.csv").read_text(encoding="utf-8")
    assert "broker candles" in u and "polled" in u


def test_a_restart_mid_trade_resumes_the_open_structure(tmp_path, strategy, ledger):
    # stop at 11:05 with the 11:00 sell open, then start again: the close must find the positions the open made
    ps1, r1, _ = _run(tmp_path, until=dtime(11, 5))
    st_path = tmp_path / "state" / f"{SLUG}_{DAY.isoformat()}.json"
    # a halted run (not a finished one) is what a crash leaves; the end-of-run close must not have happened for this
    d = json.loads(st_path.read_text(encoding="utf-8"))
    assert d["finished"] is True                       # an orderly stop closes everything ...
    assert d["state"]["positions"] == []               # ... so nothing is carried


def _utc(hh, mm):
    """A New York wall time on DAY as the UTC-naive stamp the limits table stores (EDT: UTC-4)."""
    return datetime.combine(DAY, dtime(hh, mm)) + timedelta(hours=4)


def test_the_supervisor_keeps_the_pair_out_when_entries_are_off(tmp_path, strategy, ledger):
    rows = {"sup_entries": {"value": 0, "at": _utc(9, 0), "reason": "a trend day"}}
    ps, res, _ = _run(tmp_path, controls=lambda now: rows)
    assert not ps.halted and not res.trades and not [f for f in res.fills if f["kind"] == "open"]
    assert not [c for c in ledger if c[0] == "structure"]
    st = json.loads((tmp_path / "state" / f"{SLUG}_{DAY.isoformat()}.json").read_text(encoding="utf-8"))
    blocked = [d for d in st["state"]["decisions"] if str(d.get("done", "")).startswith("blocked: supervisor: entries off")]
    assert blocked and st["state"]["sup_entries_off"] is True
    # a control set on another day does not count: the rules are in charge again
    old = {"sup_entries": {"value": 0, "at": _utc(9, 0) - timedelta(days=1), "reason": "yesterday"}}
    _, res2, _ = _run(tmp_path / "next", controls=lambda now: old)
    assert res2.trades


def test_a_supervisor_close_flattens_the_open_structure_and_books_it(tmp_path, strategy, ledger):
    asked = datetime.combine(DAY, dtime(11, 5))

    def controls(now):                                            # the request is made at 11:05, with the 11:00 sell open
        return {"sup_close": {"value": 1, "at": _utc(11, 5), "reason": "risk off"}} if now >= asked else {}
    ps, res, _ = _run(tmp_path, controls=controls)
    first = res.trades[0]
    assert first["direction"] == "short" and first["entry_time"] < "11:05"
    assert first["exit_reason"] == "supervisor close" and "11:05" <= first["exit_time"] <= "11:07"
    rows = [c[1] for c in ledger if c[0] == "structure"]
    closes = [r for r in rows if r["fill"]["kind"] == "close" and r["fill"]["m"] == [f for f in res.fills if f["kind"] == "close"][0]["m"]]
    assert sorted(r["underlying"] for r in closes) == ["NDX", "SPX"] and all(r["position_id"] is not None for r in closes)
    assert len(res.trades) >= 2                                   # entries stayed on: the 13:30 stretch is still traded
    assert not ps.halted


def test_blocked_day_does_nothing(tmp_path, strategy, ledger, monkeypatch):
    monkeypatch.setattr(type(strategy), "session_gate", lambda self, day, events=None: (True, "early_close"))
    ps, res, provs = _run(tmp_path)
    assert res.blocked and res.reason == "early_close" and not res.trades
    assert all(p.fetch_calls == 0 for p in provs.values())


def test_vertical_subfill_cash_and_legs():
    f = dict(m=600, kind="open", direction="short", px=101.0, lots=1, cash=10090.0, reason="x", ndx=31000.0)
    v_ndx = dict(index="NDX", kind="call", kl=31000.0, kh=31100.0, qty=1, px=50.0,
                 legs=[(120.0, 124.0, 0), (70.0, 72.0, 0)])
    v_spx = dict(index="SPX", kind="put", kl=7790.0, kh=7815.0, qty=4, px=12.75, legs=None)
    a, b = PR.vertical_subfill(f, v_ndx), PR.vertical_subfill(f, v_spx)
    assert a["cash"] == pytest.approx(50.0 * 100 - 2.0) and b["cash"] == pytest.approx(12.75 * 100 * 4 - 8.0)
    assert a["cash"] + b["cash"] == pytest.approx(f["cash"])
    assert a["legs"][0][:3] == ["C", 31000.0, 1] and a["legs"][1][:3] == ["C", 31100.0, -1]
    assert a["legs"][0][3] - a["legs"][1][3] == pytest.approx(50.0)
    assert b["legs"][0][:3] == ["P", 7815.0, 1] and b["legs"][1][:3] == ["P", 7790.0, -1] and b["legs"][0][3] == 12.75
    c = PR.vertical_subfill(dict(f, kind="close", direction="long"), dict(v_ndx, px=55.0))
    assert c["cash"] == pytest.approx(55.0 * 100)


def test_the_service_marks_an_open_pair_from_its_state(tmp_path, monkeypatch):
    """paper.views.paper_runner_marks reads the pair's state and heartbeat like a single-index runner's."""
    from paper import views
    sd = tmp_path / "state"; sd.mkdir()
    monkeypatch.setattr(views, "STATE_DIR", sd)
    monkeypatch.setattr(views, "EXTRA_STATE_DIRS", [])
    today = date.today().isoformat()
    pos = [dict(direction="short", kind="ndx_call_vertical", index="NDX", root="NDXP", cp="call", k_low=31000.0,
                k_high=31100.0, units=1, avg_px=50.0, last_mark=48.0, mark_sign=-1),
           dict(direction="short", kind="spx_put_vertical", index="SPX", root="SPXW", cp="put", k_low=7790.0,
                k_high=7815.0, units=4, avg_px=12.75, last_mark=12.0, mark_sign=-1)]
    (sd / f"{SLUG}_{today}.json").write_text(json.dumps({
        "state": {"positions": pos}, "provider": "tastytrade",
        "tgids": {"ndx_call_vertical|short|31000.0|31100.0": [101], "spx_put_vertical|short|7790.0|7815.0": [102]}}),
        encoding="utf-8")
    (sd / f"heartbeat_{SLUG}.json").write_text(json.dumps({
        "slug": SLUG, "day": today, "at": datetime.now().isoformat(timespec="seconds"),
        "live_marks": {"short|31000.0|31100.0": 47.5}}), encoding="utf-8")
    marks = views.paper_runner_marks()
    assert marks["101"][:2] == (-47.5, 1.0)            # the heartbeat's fresher mark, a short liability
    assert marks["102"][:2] == (-12.0, 4.0)            # the state's mark where the heartbeat has none


def test_the_runner_script_refuses_a_pair_replay(capsys, strategy):
    from scripts import paper_runner
    rc = paper_runner.main(["--strategy", SLUG, "--replay", DAY.isoformat()])
    assert rc == 2 and "pair strategy" in capsys.readouterr().out
