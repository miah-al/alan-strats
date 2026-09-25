"""/api/paper/regime-split over a synthetic ledger and a synthetic app.GexHistory (both stubbed: nothing is
read from or written to the real paper account or the recorded history)."""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
for _p in (str(REPO), str(REPO.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from api.bootstrap import bootstrap  # noqa: E402

bootstrap()

from api.services import gex_recorder as REC  # noqa: E402
from api.services import regime_split as RS  # noqa: E402

E = _dt.datetime


def _trade(strategy, opened, pnl, closed=None):
    return {"Strategy": strategy, "Open Date": opened, "Close Date": closed or opened, "P&L $": pnl,
            "TradeGroupId": f"T-{opened}-{pnl}", "Underlying": "NDX"}


LEDGER = [
    _trade("ndx_0dte_tasty", "2026-09-18", 900.0),         # before the window
    _trade("ndx_0dte_tasty", "2026-09-21", 500.0), _trade("ndx_0dte_tasty", "2026-09-21", -100.0),
    _trade("ndx_0dte_tasty", "2026-09-22", 300.0),
    _trade("ndx_0dte_tasty", "2026-09-23", -200.0),
    _trade("ndx_0dte_tasty", "2026-09-24", 50.0),
    _trade("iron_condor_rules", "2026-09-22", 1000.0),     # another strategy
]


def _gex_rows(kind, spec):
    """spec: {trade date: (regime, net, spot, flip, recorded at ET)}."""
    rows = []
    for d, (reg, net, spot, flip, at) in spec.items():
        slot = E.combine(d, _dt.time(16, 0) if kind == "eod" else _dt.time(10, 55))
        rows.append({"Ticker": "NDX", "Kind": kind, "SlotTs": slot, "TradeDate": d, "Spot": spot, "NetGex": net,
                     "CallGex": None, "PutGex": None, "Flip": flip, "CallWall": None, "PutWall": None,
                     "DistToFlipPct": (spot - flip) / spot if flip else None, "Regime": reg, "MaxPain": None,
                     "Contracts": 100, "Source": "hub:test", "RecordedAt": None,
                     "Late": REC.is_late(kind, slot, at)})
    return pd.DataFrame(rows, columns=REC.ROW_COLS + ["Late"])


D = _dt.date
EOD = {D(2026, 9, 18): ("negative", -2e9, 24000.0, 24500.0, E(2026, 9, 18, 16, 11)),
       D(2026, 9, 21): ("negative", -1e9, 24100.0, 24300.0, E(2026, 9, 21, 16, 12)),
       D(2026, 9, 22): ("positive", 3e9, 24600.0, 24200.0, E(2026, 9, 22, 16, 11)),
       # 09-23: the service was not running — no row
       D(2026, 9, 24): ("negative", -5e8, 24400.0, 24450.0, E(2026, 9, 25, 8, 30))}      # recorded late, pre-open
SESSION = {D(2026, 9, 21): ("positive", 1e9, 24350.0, 24300.0, E(2026, 9, 21, 10, 56))}


@pytest.fixture()
def stubs(monkeypatch):
    from api.services import paper as P
    monkeypatch.setattr(P, "load", lambda: ({}, list(LEDGER), pd.DataFrame()))
    monkeypatch.setattr(P, "account_id", lambda: 99)
    monkeypatch.setattr(RS, "_today", lambda: D(2026, 9, 30))
    asked = []

    def rows(ticker, kind, f, t=None):
        asked.append((ticker, kind, f, t))
        df = _gex_rows(kind, EOD if kind == "eod" else SESSION) if ticker == "NDX" else pd.DataFrame(
            columns=REC.ROW_COLS + ["Late"])
        return df[(df["TradeDate"] >= f) & ((df["TradeDate"] <= t) if t else True)]

    monkeypatch.setattr(REC, "rows", rows)
    return asked


def test_split_by_the_prior_close_regime(stubs):
    out = RS.split("ndx_0dte_tasty", "2026-09-21", "2026-09-25", "NDX", "prior_close")
    days = {d["date"]: d for d in out["days"]}
    assert list(days) == ["2026-09-21", "2026-09-22", "2026-09-23", "2026-09-24", "2026-09-25"]
    # each day's regime is the previous session's close
    assert [days[d]["regime"] for d in days] == ["negative", "negative", "positive", "unrecorded", "negative"]
    assert days["2026-09-21"]["trades"] == 2 and days["2026-09-21"]["pnl"] == 400.0 and days["2026-09-21"]["wins"] == 1
    assert days["2026-09-21"]["spot_vs_flip"] == "below" and days["2026-09-23"]["spot_vs_flip"] == "above"
    assert days["2026-09-24"]["net_gex"] is None and days["2026-09-24"]["pnl"] == 50.0      # kept, not guessed
    assert days["2026-09-25"]["late"] is True and days["2026-09-25"]["trades"] == 0
    assert days["2026-09-22"]["regime_slot"].startswith("2026-09-21T16:00")
    by = {s["regime"]: s for s in out["summary"]}
    assert [s["regime"] for s in out["summary"]] == list(RS.REGIMES)
    n = by["negative"]
    assert (n["sessions"], n["days"], n["trades"], n["pnl"], n["pnl_per_day"]) == (3, 2, 3, 700.0, 350.0)
    assert n["win_rate"] == pytest.approx(2 / 3, abs=1e-4) and n["win_days"] == 1.0 and n["late_sessions"] == 1
    assert n["bt_pnl_per_day"] == pytest.approx(4566.73) and n["in_sample"]["days"] == 253
    p = by["positive"]
    assert (p["sessions"], p["days"], p["pnl"], p["win_days"]) == (1, 1, -200.0, 0.0)
    assert by["unrecorded"]["sessions"] == 1 and by["unrecorded"]["pnl"] == 50.0
    assert by["near_flip"]["sessions"] == 0 and by["near_flip"]["pnl_per_day"] is None
    t = out["test"]["negative_minus_positive_per_day"]
    assert t["diff"] == 550.0 and t["enough"] is False and t["t"] is None
    assert out["test"]["in_sample"]["diff"] == pytest.approx(2210.56)
    # totals are the ledger's for the strategy in the window (the other strategy and 09-18 are out)
    assert (out["trades"], out["pnl"], out["traded_days"], out["recorded_sessions"]) == (5, 550.0, 4, 4)
    assert out["account_id"] == 99 and out["in_sample"]["capital"] == 30000.0
    assert [c["field"] for c in out["table"]["columns"]][:3] == ["date", "regime", "net_gex"]
    assert len(out["summary_table"]["rows"]) == len(RS.REGIMES)
    assert stubs[-1][:2] == ("NDX", "eod")


def test_split_at_the_decision_time_and_the_endpoint(stubs):
    out = RS.split("ndx_0dte_tasty", "2026-09-21", "2026-09-22", "NDX", "session")
    assert [(d["date"], d["regime"]) for d in out["days"]] == [("2026-09-21", "positive"), ("2026-09-22", "unrecorded")]
    assert out["days"][0]["late"] is False
    assert {s["regime"]: s["bt_pnl_per_day"] for s in out["summary"]}["positive"] == pytest.approx(3349.37)
    other = RS.split("ndx_0dte_tasty", "2026-09-21", "2026-09-25", "SPY", "prior_close")
    assert other["recorded_sessions"] == 0 and other["notes"] and all(d["regime"] == "unrecorded" for d in other["days"])
    none = RS.split("zz_unknown", "2026-09-21", "2026-09-22")
    assert none["trades"] == 0 and none["in_sample"] is None and none["summary"][0]["in_sample"] is None
    # with no from, the window starts at the strategy's first trade; it never runs past today
    assert RS.split("ndx_0dte_tasty", to_date="2026-09-22")["from"] == "2026-09-18"
    assert RS.split("ndx_0dte_tasty", "2026-09-28", "2026-10-09")["days"][-1]["date"] == "2026-09-30"
    with pytest.raises(ValueError):
        RS.split("ndx_0dte_tasty", "2026-09-25", "2026-09-21")

    from fastapi.testclient import TestClient
    from api.app import create_app
    from api.bootstrap import db_guard_installed, uninstall_db_read_only_guard
    had = db_guard_installed()
    try:
        with TestClient(create_app()) as c:
            r = c.get("/api/paper/regime-split?strategy=ndx_0dte_tasty&from=2026-09-21&to=2026-09-25"
                      "&regime_source=NDX&at=prior_close")
            assert r.status_code == 200 and r.json()["summary"][0]["pnl"] == 700.0
            assert c.get("/api/paper/regime-split?regime_source=QQQ").status_code == 422
            assert c.get("/api/paper/regime-split?at=close").status_code == 422
            assert c.get("/api/paper/regime-split?from=2026-13-01").status_code == 422
            assert c.get("/api/paper/regime-split?from=2026-09-25&to=2026-09-21").status_code == 422
            st = c.get("/api/market/gex-recorder").json()
            assert st["enabled"] is False and st["running"] is False and "table" in st
    finally:
        if not had:
            uninstall_db_read_only_guard()
