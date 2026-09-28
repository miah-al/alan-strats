"""Stale daily bars are topped up (db.sync_jobs, stubbed here), at most once an hour per ticker; the nightly job
covers the crypto ETPs and the watchlists. Nothing is fetched or written."""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:      # only the checkout: its parent holds the live alan_trader (conftest binds ours by path)
    sys.path.insert(0, str(REPO))

from api.bootstrap import bootstrap  # noqa: E402

bootstrap()

from api.services import bars_topup as BT  # noqa: E402

NY = "America/New_York"


def test_last_completed_session():
    f = BT.last_completed_session
    assert f(pd.Timestamp("2026-09-24 12:00", tz=NY)) == _dt.date(2026, 9, 23)      # Thursday midday: Wednesday
    assert f(pd.Timestamp("2026-09-24 16:20", tz=NY)) == _dt.date(2026, 9, 24)      # after 16:15: today
    assert f(pd.Timestamp("2026-09-27 10:00", tz=NY)) == _dt.date(2026, 9, 25)      # Sunday: Friday
    assert f(pd.Timestamp("2026-11-27 09:00", tz=NY)) == _dt.date(2026, 11, 25)     # after Thanksgiving


@pytest.fixture
def stubs(monkeypatch):
    import db.client as C
    import db.sync_jobs as J
    import api.services.db as D
    cov = {"IBIT": (_dt.date(2024, 1, 11), _dt.date(2026, 7, 31)), "SPY": (_dt.date(2020, 1, 2), _dt.date(2099, 1, 1))}
    calls = []
    monkeypatch.setattr(D, "require_db", lambda: None)
    monkeypatch.setattr(C, "get_price_coverage", lambda eng, s: cov.get(s))
    monkeypatch.setattr(J, "run_sync", lambda dt, t, fd, td, **k: calls.append((dt, t, fd, td)) or
                        {"status": "ok", "rows": 38, "detail": ""})
    monkeypatch.setattr(BT, "_TRIED", {})
    monkeypatch.setenv("ALAN_TRADER_BARS_TOPUP", "1")
    return calls


def test_top_up_pulls_only_what_is_missing_once_an_hour(stubs):
    r = BT.top_up("ibit")
    assert r["status"] == "topped_up" and r["rows"] == 38
    assert stubs[0][:3] == ("price", "IBIT", _dt.date(2026, 7, 31))
    assert BT.top_up("IBIT")["status"] == "skipped" and len(stubs) == 1          # tried within the hour
    assert BT.top_up("SPY")["status"] == "current" and len(stubs) == 1            # nothing to do, no request
    new = BT.top_up("FBTC")                                                       # never stored: ~400 days
    assert new["status"] == "topped_up" and stubs[-1][2] < _dt.date.today() - _dt.timedelta(days=390)
    assert BT.top_up("SPY261030C00770000")["status"] == "skipped"


def test_nightly_symbols_include_the_crypto_etps_and_the_watchlists(monkeypatch):
    import api.services.watchlists as W
    monkeypatch.setattr(W, "list_all", lambda: [{"name": "x", "symbols": ["NVDA", "IBIT", "SPY261030C00770000"]}])
    monkeypatch.delenv("ALAN_TRADER_DAILY_SYNC", raising=False)
    assert BT.nightly_symbols() == ["IBIT", "ETHA", "FBTC", "GBTC", "ETHE", "BITO", "NVDA"]
    n = BT.NightlyBars(jobs=None)
    assert n.due(pd.Timestamp("2026-09-24 16:45", tz=NY)) and not n.due(pd.Timestamp("2026-09-24 15:00", tz=NY))
    assert not n.due(pd.Timestamp("2026-09-26 17:00", tz=NY))                     # Saturday
