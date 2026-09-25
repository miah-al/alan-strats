"""Intraday 1-minute bars (api/services/intraday.py): minutes built from a synthetic quote stream, merged after
the vendor's last bar, resampled, and the endpoint — with the vendors stubbed (no request is made)."""
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

from api.services import intraday as I  # noqa: E402

NY = "America/New_York"
DAY = _dt.date(2026, 9, 25)


def ts(hm: str, s: int = 0) -> pd.Timestamp:
    return pd.Timestamp(f"2026-09-25 {hm}:{s:02d}", tz=NY)


def _vendor(last_hm: str) -> pd.DataFrame:
    t = pd.date_range(ts("09:30"), ts(last_hm), freq="1min")
    return pd.DataFrame({"ts": t, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 10.0})


def test_minutes_from_quotes():
    agg = I.MinuteAggregator(None, clock=lambda: ts("10:10"))
    agg._wanted["NDX"] = 0.0
    for sec, px, vol in ((1, 30000.0, 1000), (20, 30010.0, 1100), (59, 29995.0, 1250)):
        agg.add("NDX", ts("10:06", sec), px, vol)
    agg.add("NDX", ts("10:07", 5), 30020.0, 1300)
    agg.add("NDX", ts("16:00", 5), 1.0, 2000)                              # after the close: ignored
    f = agg.frame("NDX", DAY)
    assert list(f["ts"]) == [ts("10:06"), ts("10:07")]
    assert f.iloc[0][["open", "high", "low", "close"]].tolist() == [30000.0, 30010.0, 29995.0, 29995.0]
    assert f.iloc[0]["volume"] == 250.0 and f.iloc[1]["volume"] == 50.0
    assert I.MinuteAggregator.price_of("NDX", {"last": 5.0, "mid": 6.0}) == 5.0
    assert I.MinuteAggregator.price_of("SPY", {"last": 5.0, "mid": 6.0}) == 6.0


def test_vendor_then_hub_minutes(monkeypatch):
    monkeypatch.setattr(I, "vendor_minutes", lambda s, d: (_vendor("10:05"), "yfinance", []))
    monkeypatch.setattr(I, "prev_close", lambda s, d, hub=None: 29900.0)
    agg = I.MinuteAggregator(None, clock=lambda: ts("10:11"))
    for m in range(3, 11):                                                    # 10:03 .. 10:10 live
        agg.add("NDX", ts(f"10:{m:02d}", 10), 30000.0 + m)
    out = I.intraday("NDX", 390, 1, agg=agg, now=ts("10:11", 30))
    assert out["t"][0] == "2026-09-25T09:30:00-04:00" and out["t"][-1] == "2026-09-25T10:10:00-04:00"
    assert len(out["t"]) == 41 and out["source"] == "yfinance+hub" and out["hub_minutes"] == 5
    assert out["c"][35] == 100.5 and out["c"][36] == 30006.0                  # 10:05 vendor, 10:06 hub
    assert out["prev_close"] == 29900.0 and out["delayed_minutes"] == 0 and out["vendor_delayed_minutes"] == 5
    assert out["session"] == "2026-09-25" and set(out) >= {"t", "o", "h", "l", "c", "v"}
    five = I.intraday("NDX", 390, 5, agg=agg, now=ts("10:11", 30))
    assert five["interval"] == "5m" and five["t"][:2] == ["2026-09-25T09:30:00-04:00", "2026-09-25T09:35:00-04:00"]
    assert five["h"][-1] == 30010.0 and five["o"][0] == 100.0
    last30 = I.intraday("NDX", 30, 1, agg=agg, now=ts("10:11", 30))
    assert len(last30["t"]) == 30 and last30["t"][0] == "2026-09-25T09:41:00-04:00"
    # before the open the session is the last trading day's
    assert I.session_day(pd.Timestamp("2026-09-28 09:00", tz=NY)) == DAY
    with pytest.raises(ValueError):
        I.intraday("NDX", 390, 3, agg=agg, now=ts("10:11"))


def test_the_endpoint(monkeypatch):
    from fastapi.testclient import TestClient
    from api.app import create_app
    from api.bootstrap import db_guard_installed, uninstall_db_read_only_guard
    monkeypatch.setattr(I, "vendor_minutes", lambda s, d: (_vendor("15:59"), "polygon", []))
    monkeypatch.setattr(I, "prev_close", lambda s, d, hub=None: 760.0)
    had = db_guard_installed()
    try:
        with TestClient(create_app()) as c:
            j = c.get("/api/market/intraday/SPY?minutes=60").json()
            assert len(j["t"]) == 60 and j["source"] == "polygon" and j["prev_close"] == 760.0
            assert j["t"][-1].endswith("15:59:00-04:00") and "delayed_minutes" in j
            assert c.get("/api/market/intraday/SPY?interval=45").status_code == 422
    finally:
        if not had:
            uninstall_db_read_only_guard()
