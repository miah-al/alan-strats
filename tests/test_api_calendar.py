"""/api/market/events: the checked-in macro calendar (kept in step with the platform's seed CSVs), opex
computed around exchange holidays, earnings from a stubbed calendar. No network."""
from __future__ import annotations

import csv
import datetime as _dt
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
for _p in (str(REPO), str(REPO.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from api.bootstrap import bootstrap  # noqa: E402

bootstrap()

from api.services import calendar_events as CE  # noqa: E402


def test_macro_calendar_matches_the_platform_seeds():
    doc = json.loads((REPO / "data" / "macro_calendar.json").read_text(encoding="utf-8"))
    mine = {(e["date"], e["kind"]) for e in doc["events"] if e["kind"] in ("cpi", "nfp", "pce", "fomc")}
    seeds = set()
    for f in ("bls.csv", "bea.csv", "fomc.csv"):
        with open(REPO / "db" / "seed" / "events" / f, encoding="utf-8") as fh:
            seeds |= {(r["date"], r["kind"]) for r in csv.DictReader(fh)
                      if r["date"].startswith("2026") and r["kind"] in ("cpi", "nfp", "pce", "fomc")}
    assert mine == seeds
    kinds = {e["kind"] for e in doc["events"]}
    assert kinds == {"cpi", "nfp", "pce", "fomc", "gdp"}
    assert all(e["time"] in ("08:30", "14:00") for e in doc["events"])


def test_opex_moves_to_thursday_on_a_holiday_and_quarterlies_are_marked():
    got = dict(CE.opex_dates(_dt.date(2026, 5, 1), _dt.date(2026, 9, 30)))
    assert got[_dt.date(2026, 5, 15)] is False
    assert _dt.date(2026, 6, 18) in got and got[_dt.date(2026, 6, 18)] is True       # 06-19 Juneteenth
    assert got[_dt.date(2026, 9, 18)] is True and len(got) == 5


def test_events_window_macro_opex_holidays_and_earnings(monkeypatch):
    import api.services.earnings as E
    monkeypatch.setattr(E, "earnings_dates", lambda s: [_dt.date(2026, 10, 29)] if s == "AAPL" else [])
    rows, warnings = CE.events(40, ["aapl", "SPY"], today=_dt.date(2026, 9, 24))
    kinds = [(r["date"].isoformat(), r["kind"]) for r in rows]
    assert ("2026-09-30", "pce") in kinds and ("2026-09-30", "gdp") in kinds and ("2026-10-02", "nfp") in kinds
    assert ("2026-10-14", "cpi") in kinds and ("2026-10-16", "opex") in kinds and ("2026-10-28", "fomc") in kinds
    assert ("2026-10-29", "earnings") in kinds
    e = next(r for r in rows if r["kind"] == "earnings")
    assert e["symbol"] == "AAPL" and e["title"] == "AAPL earnings"
    assert rows == sorted(rows, key=lambda r: (r["date"], r["time"] or "99:99", r["kind"], r["symbol"] or ""))
    assert not warnings
    hol, _ = CE.events(3, today=_dt.date(2026, 11, 25))
    assert [r["title"] for r in hol if r["kind"] == "other"] == ["Market holiday: Thanksgiving",
                                                                  "Early close: Day after Thanksgiving 13:00 close"]
    _, w = CE.events(30, today=_dt.date(2026, 12, 20))
    assert any("2027" in x for x in w)
    with pytest.raises(ValueError):
        CE.events(400)
    with pytest.raises(ValueError):
        CE.events(5, ["bad sym!"])


def test_events_endpoint(monkeypatch):
    from fastapi.testclient import TestClient
    from api.app import create_app
    from api.bootstrap import db_guard_installed, uninstall_db_read_only_guard
    import api.services.earnings as E
    monkeypatch.setattr(E, "earnings_dates", lambda s: [])
    had = db_guard_installed()
    try:
        with TestClient(create_app()) as c:
            r = c.get("/api/market/events?days=14&symbols=SPY")
            assert r.status_code == 200 and isinstance(r.json(), list)
            for ev in r.json():
                assert set(ev) >= {"date", "time", "kind", "symbol", "title"} and ev["kind"] in CE.KINDS
            assert c.get("/api/market/events?days=999").status_code == 422
    finally:
        if not had:
            uninstall_db_read_only_guard()
