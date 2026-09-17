"""Live-path guards of the paper runner: quote sanity, empty chain, stale VXN preflight, engine
errors halting the session, late-start backfill. Offline except where the database is needed."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from paper.providers import LegQuote, vertical_quote, Bar

NOW = datetime(2026, 9, 17, 13, 30)


def _leg(sym, bid, ask, last=None, age=0):
    return LegQuote(sym, bid, ask, last, NOW - timedelta(minutes=age), NOW)


def test_quote_sanity_rejects_crossed_empty_and_too_wide():
    good = vertical_quote(_leg("L", 170, 172, 171), _leg("S", 108, 110, 109), NOW)
    assert good is not None and good.bid == 60 and good.ask == 64
    assert vertical_quote(_leg("L", 172, 170), _leg("S", 108, 110), NOW) is None          # crossed leg
    assert vertical_quote(_leg("L", 0, 0), _leg("S", 108, 110), NOW) is None              # empty leg
    assert vertical_quote(_leg("L", 150, 200), _leg("S", 100, 110), NOW) is None          # 60-pt wide vertical
    assert vertical_quote(_leg("L", 170, 172, age=45), _leg("S", 108, 110), NOW, carry_min=30) is None   # too old


class _Prov:
    name = "fake-live"
    underlying = "NDX"
    root = "NDXP"
    poll_seconds = 20
    expiry = date(2026, 9, 17)

    def __init__(self, n_chain=64, bars=None):
        self.n_chain = n_chain
        self._bars = bars or []
        self._samples = []

    def load_chain(self, day):
        return self.n_chain

    def leg_symbols(self, kind, k_low, k_high):
        return "NDXP260917C29100000", "NDXP260917C29200000"

    def fetch(self, syms):
        return {"NDX": LegQuote("NDX", None, None, 29100.0, NOW, NOW)}

    def sample_underlying(self, quotes, when):
        self._samples.append((when, 29100.0)); return 29100.0

    def close_minute(self, minute_start):
        return Bar(minute_start, 29100.0, 29100.0, 29100.0, 29100.0)

    def quote_vertical(self, *a, **k):
        return None

    def backfill_bars(self, day, until):
        return self._bars


def _session_factory(db_ok=True):
    from strategy_api import registry as R
    try:
        s = R.get_strategy("ndx_0dte_tasty")
    except Exception as exc:
        pytest.skip(str(exc))
    return s


def _db():
    try:
        from db.client import get_engine
        eng = get_engine()
        with eng.connect() as c:
            c.exec_driver_sql("SELECT 1")
        return eng
    except Exception as exc:
        pytest.skip(f"database unavailable: {exc}")


def test_empty_chain_blocks_the_session(tmp_path):
    _session_factory(); eng = _db()
    from paper.runner import PaperSession
    ps = PaperSession("ndx_0dte_tasty", _Prov(n_chain=0), eng, write_ledger=False, log_dir=tmp_path, state_dir=tmp_path / "s")
    ps._preflight = lambda d: []                              # isolate the chain check from the data freshness check
    ps._gate = lambda d: (False, "")
    t = [datetime(2026, 9, 17, 15, 59, 30)]
    res = ps.run_live(day=date(2026, 9, 17), now_fn=lambda: t[0], sleep_fn=lambda s: t.__setitem__(0, t[0] + timedelta(seconds=40)))
    assert res.blocked and "no NDXP contracts" in res.reason


def test_preflight_flags_stale_vxn(tmp_path):
    _session_factory(); eng = _db()
    from paper.runner import PaperSession
    ps = PaperSession("ndx_0dte_tasty", _Prov(), eng, write_ledger=False, log_dir=tmp_path, state_dir=tmp_path / "s")
    far = date(2030, 1, 15)                                   # no VXN close within 4 days of this
    problems = ps._preflight(far)
    assert any("VXN" in p for p in problems)
    assert ps._preflight(date(2026, 9, 12)) == []              # a date right after stored closes passes


def test_engine_error_halts_and_saves_state(tmp_path, monkeypatch):
    s = _session_factory(); eng = _db()
    from paper.runner import PaperSession
    ps = PaperSession("ndx_0dte_tasty", _Prov(), eng, write_ledger=False, log_dir=tmp_path, state_dir=tmp_path / "s")
    day = date(2026, 9, 17)
    session = s.live_session(day)
    def boom(*a, **k):
        raise RuntimeError("synthetic engine failure")
    monkeypatch.setattr(session, "on_bar", boom)
    monkeypatch.setattr(ps.strategy, "live_session", lambda *a, **k: session)
    monkeypatch.setattr(ps, "_gate", lambda d: (False, ""))
    monkeypatch.setattr(ps, "_preflight", lambda d: [])
    t = [datetime(2026, 9, 17, 11, 0, 0)]
    res = ps.run_live(day=day, now_fn=lambda: t[0], sleep_fn=lambda sec: t.__setitem__(0, t[0] + timedelta(seconds=40)),
                      until=datetime(2026, 9, 17, 11, 5).time())
    assert ps.halted and "synthetic engine failure" in ps.halted
    assert "HALTED" in res.reason or "synthetic" in res.reason
    assert (tmp_path / "s" / f"ndx_0dte_tasty_{day}.json").exists()


def test_late_start_backfills_history_without_trading_it(tmp_path, monkeypatch):
    s = _session_factory(); eng = _db()
    from paper.runner import PaperSession
    day = date(2026, 9, 17)
    hist = [Bar(datetime(2026, 9, 17, 9, 30) + timedelta(minutes=i), 29000 + i, 29000 + i, 29000 + i, 29000 + i) for i in range(90)]
    ps = PaperSession("ndx_0dte_tasty", _Prov(bars=hist), eng, write_ledger=False, log_dir=tmp_path, state_dir=tmp_path / "s")
    monkeypatch.setattr(ps, "_gate", lambda d: (False, ""))
    monkeypatch.setattr(ps, "_preflight", lambda d: [])
    t = [datetime(2026, 9, 17, 11, 0, 0)]
    res = ps.run_live(day=day, now_fn=lambda: t[0], sleep_fn=lambda sec: t.__setitem__(0, t[0] + timedelta(seconds=40)),
                      until=datetime(2026, 9, 17, 11, 3).time())
    assert res.bars >= 2 and not res.fills                    # history fed, no fills from it (no quotes in this fake)
    assert len(ps._day_bars) >= 90 + 2


def test_replay_of_a_non_session_is_a_clean_error(capsys):
    """Asking for a replay of a weekend (no minute bars stored) prints one line and exits 1."""
    try:
        from db.client import get_engine
        get_engine().connect().close()
    except Exception as exc:
        import pytest; pytest.skip(f"database unavailable: {exc}")
    from scripts.paper_runner import main
    rc = main(["--strategy", "ndx_0dte_tasty", "--replay", "2026-09-12", "--no-ledger"])
    out = capsys.readouterr().out
    assert rc == 1 and "cannot replay 2026-09-12" in out and "Traceback" not in out
