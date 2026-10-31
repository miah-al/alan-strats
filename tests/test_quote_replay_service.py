"""The real-quote check (api/services/quote_replay.py): a backtest's P&L per recorded day next to the live engine's on
the recorded bid/ask, and how the "Read with care" panel says it. No network, no database: the replay is stubbed."""
from __future__ import annotations

import datetime as _dt

import pandas as pd

from api.services import quote_replay as QR
from engine import strategy_backtest as B


def _stub(monkeypatch, recorded, replay_pnl):
    monkeypatch.setattr(QR, "live_instrument", lambda slug: {"root": "NDXP", "underlying": "NDX", "live_params": {}})
    monkeypatch.setattr(QR, "recorded_days", lambda root="NDXP", qdir=None: [_dt.date.fromisoformat(d) for d in recorded])

    def replay(slug, days=None, overrides=None, progress=None):
        return {"days": [{"day": d.isoformat(), "blocked": False, "pnl": replay_pnl[d.isoformat()][0],
                          "trades": replay_pnl[d.isoformat()][1]} for d in days]}
    monkeypatch.setattr(QR, "replay", replay)


def test_backtest_days_line_up_with_the_replay(monkeypatch):
    _stub(monkeypatch, ["2026-09-28", "2026-09-29"], {"2026-09-28": (2462.5, 6), "2026-09-29": (2482.5, 5)})
    trades = pd.DataFrame({"entry_date": ["2026-09-25", "2026-09-28", "2026-09-28"], "pnl": [4965.0, 5000.0, 3227.19]})
    cal = QR.calibrate("demo", trades, "2026-09-22", "2026-09-29")
    assert cal["recorded"] == ["2026-09-28", "2026-09-29"]
    assert cal["days"] == [
        {"day": "2026-09-28", "backtest": 8227.19, "backtest_trades": 2, "replay": 2462.5, "replay_trades": 6},
        {"day": "2026-09-29", "backtest": 0.0, "backtest_trades": 0, "replay": 2482.5, "replay_trades": 5}]


def test_no_recorded_day_in_the_window(monkeypatch):
    _stub(monkeypatch, ["2026-09-28"], {})
    cal = QR.calibrate("demo", pd.DataFrame({"entry_date": ["2026-06-01"], "pnl": [1.0]}), "2026-06-01", "2026-06-30")
    assert cal == {"recorded": ["2026-09-28"], "days": []}


def test_a_strategy_without_a_live_session_is_not_checked(monkeypatch):
    monkeypatch.setattr(QR, "live_instrument", lambda slug: {})
    assert QR.calibrate("demo", pd.DataFrame(), "2026-09-01", "2026-09-30") is None


def _perf(cal):
    return {"metrics": {"num_trades": 40}, "coverage": 1.0, "window_days": 30, "span_days": 30, "params": {},
            "calibration": cal}


def test_the_panel_states_the_check():
    notes = B.performance_warnings(_perf({"recorded": ["2026-09-28", "2026-09-29"], "days": [
        {"day": "2026-09-28", "backtest": 8227.0, "backtest_trades": 11, "replay": 2462.0, "replay_trades": 6},
        {"day": "2026-09-29", "backtest": 0.0, "backtest_trades": 0, "replay": 2482.0, "replay_trades": 5}]}))
    check = next(n for n in notes if n.startswith("Checked on real quotes"))
    assert "+8,227 over 11 trades" in check and "+2,462 over 6" in check and "3.3x" in check
    assert any("No backtest trades on 2026-09-29" in n for n in notes)
    none = B.performance_warnings(_perf({"recorded": ["2026-09-28"], "days": []}))
    assert any(n.startswith("No day in this window has recorded quotes") for n in none)
    assert not any("real quotes" in n for n in B.performance_warnings(_perf(None)))
