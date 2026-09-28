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
if str(REPO) not in sys.path:      # only the checkout: its parent holds the live alan_trader (conftest binds ours by path)
    sys.path.insert(0, str(REPO))

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
    import api.services.gex_recorder as REC
    monkeypatch.setattr(REC, "history_rows", lambda t, k, since: pd.DataFrame())
    had = db_guard_installed()
    try:
        with TestClient(create_app()) as c:
            j = c.get("/api/market/gex/SPY/history?days=3000").json()
            assert j["ticker"] == "SPY" and j["units"].startswith("$ per 1% move") and "volume" in j["method"]["snapshot_proxy"]
            assert [p["date"] for p in j["points"]][-2:] == ["2026-07-09", "2026-07-10"] and j["sources"][0] == "snapshot_proxy"
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


def test_recorder_schedule_and_one_tick(monkeypatch):
    import api.services.gex_recorder as REC
    NY = "America/New_York"
    E = _dt.datetime
    day = pd.Timestamp("2026-09-23 10:47", tz=NY)                           # a Wednesday
    assert REC.due_slots(day, streaming=True) == [("intraday", E(2026, 9, 23, 10, 30))]
    assert REC.due_slots(day, streaming=False) == []                         # auto: intraday only while streaming
    assert REC.due_slots(day, streaming=False, mode="on") == [("intraday", E(2026, 9, 23, 10, 30))]
    # the decision-time snapshot, streaming or not, 10:55 until 11:30
    assert REC.due_slots(pd.Timestamp("2026-09-23 10:56", tz=NY), streaming=False) == [("session", E(2026, 9, 23, 10, 55))]
    assert REC.due_slots(pd.Timestamp("2026-09-23 11:10", tz=NY), streaming=True) == [
        ("intraday", E(2026, 9, 23, 11, 0)), ("session", E(2026, 9, 23, 10, 55))]
    assert REC.due_slots(pd.Timestamp("2026-09-23 11:31", tz=NY), streaming=False) == []
    late = pd.Timestamp("2026-09-23 16:20", tz=NY)
    assert REC.due_slots(late, streaming=True) == [("eod", E(2026, 9, 23, 16, 0))]
    # a missed close can still be recorded until the next session opens — only the last one, never an older day
    assert REC.due_slots(pd.Timestamp("2026-09-26 12:00", tz=NY), streaming=True) == [("eod", E(2026, 9, 25, 16, 0))]
    assert REC.due_slots(pd.Timestamp("2026-09-28 09:00", tz=NY), streaming=True) == [("eod", E(2026, 9, 25, 16, 0))]
    assert REC.due_slots(pd.Timestamp("2026-09-28 09:45", tz=NY), streaming=False) == []
    assert REC.due_slots(pd.Timestamp("2026-11-26 16:30", tz=NY), streaming=True) == [("eod", E(2026, 11, 25, 16, 0))]
    assert REC.is_late("eod", E(2026, 9, 23, 16), E(2026, 9, 23, 16, 30)) is False
    assert REC.is_late("eod", E(2026, 9, 23, 16), E(2026, 9, 23, 19, 0)) is True
    assert REC.is_late("eod", E(2026, 9, 25, 16), E(2026, 9, 28, 8, 0)) is True
    assert REC.is_late("session", E(2026, 9, 23, 10, 55), E(2026, 9, 23, 11, 1)) is False
    assert REC.is_late("session", E(2026, 9, 23, 10, 55), E(2026, 9, 23, 11, 20)) is True
    monkeypatch.setenv("ALAN_TRADER_GEX_TICKERS", "IBIT,ETHA,SPY")
    assert REC.tickers() == ["IBIT", "ETHA", "SPY", "NDX", "SPX"] and REC.session_tickers() == ["NDX", "SPX", "SPY"]

    saved = []
    monkeypatch.setattr(REC, "tickers", lambda: ["IBIT", "ETHA"])
    monkeypatch.setattr(REC, "recorded", lambda t, k, s: t == "ETHA")        # ETHA's slot is already there
    monkeypatch.setattr(REC, "save", lambda t, k, s, g: saved.append((t, k, s, g["net_gex"], g.get("source"))) or True)
    import api.services.market as M
    calls = []
    monkeypatch.setattr(M, "gex", lambda t, source, hub=None, spot=None: calls.append((t, source, spot))
                        or {"net_gex": 1.0, "regime": "positive", "source": "hub:x"})
    rec = REC.GexRecorder(hub=None)
    assert rec.tick(late) == 1 and calls == [("IBIT", "hub", None)]
    assert saved == [("IBIT", "eod", E(2026, 9, 23, 16, 0), 1.0, "hub:x")]
    assert rec.tick(late) == 0 and len(calls) == 1                           # done slots cost nothing

    # a late end-of-day row (Saturday, for Friday) is valued at the stored close; without one it is not recorded,
    # and a failed slot waits before it is tried again
    saved.clear(), calls.clear()
    monkeypatch.setattr(REC, "recorded", lambda t, k, s: False)
    closes = {"IBIT": 47.5, "ETHA": None}
    monkeypatch.setattr(REC, "session_close", lambda t, d, hub=None: closes[t])
    sat = pd.Timestamp("2026-09-26 12:00", tz=NY)
    assert rec.tick(sat) == 1 and calls == [("IBIT", "hub", 47.5)]
    assert saved == [("IBIT", "eod", E(2026, 9, 25, 16, 0), 1.0, "hub:x spot=close")]
    assert rec.last["IBIT"]["late"] is True
    st = rec.status()
    assert [f["ticker"] for f in st["failed"]] == ["ETHA"] and st["failed"][0]["tries"] == 1
    closes["ETHA"] = 20.0
    assert rec.tick(sat) == 0 and len(calls) == 1                            # ETHA waits RETRY_S before a retry
