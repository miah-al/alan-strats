"""The daily GEX history (api/services/gex_history.py): the open-interest proxy, the parity spot, and the
endpoint over a stubbed history; plus the real build on the stored SPY snapshots when the DB is there
(read only)."""
from __future__ import annotations

import datetime as _dt
import math
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

from api.services import gex_history as GH  # noqa: E402


def test_oi_proxy_is_a_rolling_volume_sum_over_snapshot_days():
    days = pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08"])
    e = pd.Timestamp("2026-02-20")
    df = pd.DataFrame({"day": list(days) + [days[0], days[2]], "expiry": e,
                       "strike": [100.0] * 4 + [105.0, 105.0], "type": "call",
                       "volume": [10, 20, 30, 40, 5, 7]})
    out = GH.add_oi_proxy(df, window=2).sort_values(["strike", "day"])
    assert out[out["strike"] == 100]["oi_proxy"].tolist() == [10, 30, 50, 70]
    assert out[out["strike"] == 105]["oi_proxy"].tolist() == [5, 7]          # 01-05 is out of 01-07's 2-day window


def test_parity_spot_and_implied_move():
    day = pd.Timestamp("2026-03-02")
    e = pd.Timestamp("2026-03-09")
    T = 7 / 365
    rows = []
    for k in (95.0, 100.0, 105.0):
        c = max(100 - k, 0) + 2.0
        p = c - 100 + k * math.exp(-GH.RISK_FREE * T)                         # parity at S = 100
        rows += [{"day": day, "expiry": e, "strike": k, "type": "call", "mid": c, "iv": 0.2},
                 {"day": day, "expiry": e, "strike": k, "type": "put", "mid": p, "iv": 0.2}]
    g = pd.DataFrame(rows)
    assert GH.parity_spot(g) == pytest.approx(100.0)
    im, iv = GH.implied_move_1d(g, 100.0)
    straddle = 2.0 + (2.0 - 100 + 100 * math.exp(-GH.RISK_FREE * T))
    assert im == pytest.approx(straddle / math.sqrt(7 * 252 / 365) / 100.0) and iv == pytest.approx(0.2)


def test_history_endpoint(monkeypatch):
    from fastapi.testclient import TestClient
    from api.app import create_app
    from api.bootstrap import db_guard_installed, uninstall_db_read_only_guard
    idx = [_dt.date(2026, 7, 1) + _dt.timedelta(days=i) for i in range(10)]
    h = pd.DataFrame({"spot": 700.0, "net_gex": [1e9 * (i - 5) for i in range(10)], "call_gex": 2e9, "put_gex": -1e9,
                      "flip": 690.0, "call_wall": 720.0, "put_wall": 680.0, "dist_to_flip_pct": 0.014,
                      "regime": "positive", "implied_move_1d": 0.006, "atm_iv_near": 0.12, "contracts": 150}, index=idx)
    monkeypatch.setattr(GH, "history", lambda t: h if t.upper() == "SPY" else (_ for _ in ()).throw(GH.NoHistory("none")))
    had = db_guard_installed()
    try:
        with TestClient(create_app()) as c:
            j = c.get("/api/market/gex/SPY/history?days=3").json()
            assert j["ticker"] == "SPY" and j["units"].startswith("$ per 1% move") and "volume" in j["method"]
            assert [p["date"] for p in j["points"]] == ["2026-07-07", "2026-07-08", "2026-07-09", "2026-07-10"]
            assert set(j["points"][0]) >= {"date", "net_gex", "flip", "call_wall", "put_wall", "spot", "regime"}
            assert c.get("/api/market/gex/QQQ/history").status_code == 422
    finally:
        if not had:
            uninstall_db_read_only_guard()


def _db_ok() -> bool:
    try:
        from api.services.db import ping
        return ping()[0]
    except Exception:
        return False


@pytest.mark.skipif(not _db_ok(), reason="AlanStrats database unreachable")
def test_real_history_on_a_month_of_stored_snapshots():
    raw = GH.load_snapshots("SPY", _dt.date(2026, 6, 1))
    if raw.empty:
        pytest.skip("no stored SPY snapshots since 2026-06-01")
    h = GH.build("SPY", since=_dt.date(2026, 6, 1))
    assert len(h) >= 15 and h["spot"].between(300, 3000).all()
    assert set(h["regime"]) <= {"positive", "negative", "near_flip", "unknown"}
    assert (h["implied_move_1d"].dropna().between(0.001, 0.05)).all()
