"""The paper runner with an engine whose whole trade is the SYNTHETIC futures book (nq_vol_breakout): it gets every
bar's open, a late start hands it whole bars, and the forced settlement closes a book left open. Offline: synthetic
bars, no database, no network."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd
import pytest

from paper.providers import Bar, LegQuote, ReplayProvider

DAY = date(2026, 10, 26)
PRIOR = {"date": "2026-10-23", "high": 29161.03, "low": 28825.72, "range": 335.31}
SLUG = "nq_vol_breakout"


def _strategy():
    from strategy_api import registry as R
    try:
        return R.get_strategy(SLUG)
    except Exception as exc:                                  # the strategies checkout without the plugin
        pytest.skip(str(exc))


def _session(s):
    from alan_trader_strategies.strategies.nq_vol_breakout.live import SessionEngine
    return SessionEngine(s.params, DAY, prior=PRIOR)


def _tape():
    """09:30-15:59: opens 29,000, climbs through the upper level (29,167.66) at 10:30, drifts to 29,300."""
    rows = []
    for i in range(390):
        t = datetime(2026, 10, 26, 9, 30) + timedelta(minutes=i)
        c = 29000.0 + (0.0 if i < 60 else min(300.0, (i - 59) * 3.0))
        o = rows[-1]["close"] if rows else 29000.0
        rows.append({"ts": t, "open": o, "high": max(o, c) + 1.0, "low": min(o, c) - 1.0, "close": c})
    return pd.DataFrame(rows)


def test_replay_hands_the_open_and_books_one_synthetic_round_trip(tmp_path, monkeypatch):
    s = _strategy()
    from paper.runner import PaperSession
    prov = ReplayProvider.from_frames("NDX", DAY, _tape(), pd.DataFrame(columns=["right", "strike", "ts", "close"]))
    ps = PaperSession(SLUG, prov, None, write_ledger=False, log_dir=tmp_path, state_dir=tmp_path / "s")
    session = _session(s)
    monkeypatch.setattr(ps.strategy, "live_session", lambda *a, **k: session)
    monkeypatch.setattr(ps, "_gate", lambda d: (False, ""))
    res = ps.run_replay(DAY)
    assert session.level["open"] == 29000.0                  # the 09:30 bar's open, not its close
    rows = [f for f in res.fills if f["kind"] == "hedge"]
    assert [(f["direction"], f["final"]) for f in rows] == [("buy", False), ("sell", True)]
    assert rows[0]["units"] == 0.1 and session.hedge.units == 0.0
    assert session.trades[0]["exit_reason"] == "flat 15:49" and res.day_pnl == pytest.approx(session.trades[0]["pnl"])
    log = (tmp_path / f"paper_{DAY}.csv").read_text(encoding="utf-8") if (tmp_path / f"paper_{DAY}.csv").exists() else \
        "".join(p.read_text(encoding="utf-8") for p in tmp_path.glob("*.csv"))
    assert "SYNTHETIC" in log


class _Prov:
    name = "fake-live"
    underlying = "NDX"
    root = "NDXP"
    poll_seconds = 20
    expiry = DAY

    def __init__(self, bars):
        self._bars = bars

    def load_chain(self, day):
        return 64

    def leg_symbols(self, kind, k_low, k_high):
        return None, None

    def fetch(self, syms):
        now = datetime(2026, 10, 26, 11, 0)
        return {"NDX": LegQuote("NDX", None, None, 29010.0, now, now)}

    def sample_underlying(self, quotes, when):
        return 29010.0

    def close_minute(self, minute_start):
        return Bar(minute_start, 29010.0, 29012.0, 29008.0, 29010.0)

    def quote_vertical(self, *a, **k):
        return None

    def backfill_bars(self, day, until):
        return self._bars


def test_a_late_start_hands_whole_bars_to_on_backfill(tmp_path, monkeypatch):
    s = _strategy()
    from paper.runner import PaperSession
    hist = [Bar(datetime(2026, 10, 26, 9, 30) + timedelta(minutes=i), 29000.0 + (5 if i else 0), 29020.0, 28990.0, 29005.0)
            for i in range(90)]
    ps = PaperSession(SLUG, _Prov(hist), None, write_ledger=False, log_dir=tmp_path, state_dir=tmp_path / "s",
                      controls_fn=lambda slug: {})
    session = _session(s)
    monkeypatch.setattr(ps.strategy, "live_session", lambda *a, **k: session)
    monkeypatch.setattr(ps, "_gate", lambda d: (False, ""))
    monkeypatch.setattr(ps, "_preflight", lambda d: [])
    t = [datetime(2026, 10, 26, 11, 0, 0)]
    ps.run_live(day=DAY, now_fn=lambda: t[0], sleep_fn=lambda sec: t.__setitem__(0, t[0] + timedelta(seconds=40)),
                until=datetime(2026, 10, 26, 11, 3).time())
    assert session.level["open"] == 29000.0 and not session.done   # the first candle's open; no level traded yet
    assert len(session.closes) >= 90 and not session.fills


def test_the_forced_settlement_closes_a_synthetic_book(tmp_path):
    s = _strategy()
    from paper.runner import PaperSession
    ps = PaperSession(SLUG, _Prov([]), None, write_ledger=False, log_dir=tmp_path, state_dir=tmp_path / "s")
    session = _session(s)
    session.on_bar(571, 29000.0, None, high=29001.0, low=28999.0, open=29000.0)
    session.on_bar(631, 29200.0, None, high=29210.0, low=29150.0, open=29160.0)
    assert ps._book_open(session) and session.side == 1
    ps._force_settlement(session, DAY, None, DAY, lambda *a: (None, None), "test: runner ended with units on")
    assert not ps._book_open(session) and session.fills[-1]["final"]
    assert not ps._book_open(object())                        # an engine without a book
