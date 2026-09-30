"""The trader's limits (api/services/limits.py): the catalogue, validation, the change log, usage, and the launch
parameters a runner gets; the API on a stand-in app."""
from __future__ import annotations

import pytest

from api.services import limits as L

SPECS = [
    {"key": "daily_loss_cap", "label": "Daily loss cap ($, 0 = none)", "type": "slider", "min": 0, "max": 20000, "default": 5000},
    {"key": "max_adds", "label": "Adds into a loser", "type": "slider", "min": 0, "max": 4, "default": 2},
    {"key": "target_pts", "label": "Take-profit (pts)", "type": "slider", "min": 1, "max": 20, "default": 5},
    {"key": "entry_start", "label": "First entry", "type": "text", "default": "13:00"},
]


def make(usage=None):
    return L.Limits(L.MemoryLimitStore(), strategies=lambda: ["demo_strategy"], specs_for=lambda slug: SPECS,
                    usage=(lambda: usage) if usage is not None else None)


def test_a_strategys_limits_are_found_by_name_among_its_params():
    cat = make().catalogue("demo_strategy")
    names = [l["name"] for l in cat]
    assert names[:3] == ["daily_loss_cap", "max_adds", "entry_start"]       # target_pts is not a limit
    assert names[3:] == ["sup_entries", "sup_adds", "sup_close"]            # the supervisor's controls (test_supervisor)
    assert all(l["applies"] == "next_session" for l in cat[:3])


def test_values_are_the_defaults_until_set_and_every_change_is_logged():
    lim = make()
    assert lim.values("claude_discretionary")["max_lots"] == 2
    row = lim.set("claude_discretionary", "max_lots", "1", by="user", reason="tighter after two losses")
    assert row["value"] == 1 and row["is_default"] is False and row["updated_by"] == "user"
    lim.set("claude_discretionary", "max_lots", 3, by="user")
    assert lim.values("claude_discretionary")["max_lots"] == 3
    ch = lim.table()["changes"]
    assert [(c["old"], c["new"]) for c in ch] == [(1, 3), (None, 1)]          # newest first
    assert ch[1]["reason"] == "tighter after two losses"


@pytest.mark.parametrize("scope,name,value", [
    ("claude_discretionary", "max_lots", 50),        # over the range
    ("claude_discretionary", "day_stop", 100),       # a day stop must be a loss
    ("claude_discretionary", "entry_end", "3pm"),    # a time is HH:MM
    ("claude_discretionary", "entry_end", "16:30"),  # outside the session
    ("claude_discretionary", "nope", 1),             # no such limit
    ("demo_strategy", "max_adds", "x"),              # not a number
])
def test_bad_values_are_refused(scope, name, value):
    with pytest.raises(L.LimitError):
        make().set(scope, name, value)


def test_times_are_normalised():
    assert make().set("claude_discretionary", "entry_start", "9:50")["value"] == "09:50"


def test_usage_grades_each_limit():
    usage = {"claude_discretionary": {"day_pnl": -2100.0, "open_positions": 1, "max_open_risk": 1060.0},
             "demo_strategy": {"day_pnl": -5200.0, "open_positions": 0, "max_open_risk": 0.0},
             "system": {"broker_calls": 6989}}
    t = {s["scope"]: {r["name"]: r for r in s["limits"]} for s in make(usage).table()["scopes"]}
    assert t["claude_discretionary"]["day_stop"]["status"] == "near"         # -2,100 of -2,500
    assert t["claude_discretionary"]["max_positions"]["status"] == "hit"     # 1 of 1: no new position
    assert t["claude_discretionary"]["max_risk"]["status"] == "ok"
    assert t["demo_strategy"]["daily_loss_cap"]["status"] == "hit"           # -5,200 against 5,000
    assert t["system"]["broker_day_cap"]["used"] == 6989 and t["system"]["broker_day_cap"]["status"] == "near"   # 87%


def test_the_launcher_gets_only_what_the_trader_set(monkeypatch):
    store = L.MemoryLimitStore()
    monkeypatch.setattr(L, "STORE", store)
    monkeypatch.setattr(L, "_strategy_catalogue", lambda slug, *_a: [
        L._lim(s["key"], s["label"], "", s["default"], s.get("min"), s.get("max"), "next_session", "",
               "time" if isinstance(s["default"], str) else "number") for s in SPECS if s["key"] != "target_pts"])
    assert L.launch_params("demo_strategy") == {}
    L.Limits(store).set("demo_strategy", "max_adds", 0, by="user")
    L.Limits(store).set("system", "broker_day_cap", 9000, by="user")
    assert L.launch_params("demo_strategy") == {"max_adds": 0}
    assert L.launch_broker_cap() == 9000

    from api.services import arms
    cmd = arms.runner_command("demo_strategy", __import__("pathlib").Path("x.log"), __import__("pathlib").Path("csv"), py="py")
    assert "--param max_adds=0" in cmd and 'set "ALAN_TRADER_BROKER_DAY_CAP=9000" & ' in cmd
    assert '-Params "max_adds=0"' in arms.task_command("demo_strategy", __import__("pathlib").Path("C:/co"))


def test_the_api_reads_and_sets(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from types import SimpleNamespace

    from api.routers import limits as R

    app = FastAPI()
    app.include_router(R.router, prefix="/api")
    app.state.limits_store = L.MemoryLimitStore()
    app.state.arms = SimpleNamespace(arms=lambda: [])
    monkeypatch.setattr(L, "paper_usage", lambda hub=None, broker_calls=None: {})
    c = TestClient(app)
    assert c.get("/api/limits/claude_discretionary").json()["values"]["day_stop"] == -2500
    r = c.put("/api/limits/claude_discretionary/day_stop", json={"value": -1500, "by": "user", "reason": "test"})
    assert r.status_code == 200 and r.json()["value"] == -1500
    assert c.get("/api/limits/claude_discretionary").json()["values"]["day_stop"] == -1500
    assert c.put("/api/limits/claude_discretionary/day_stop", json={"value": 5}).status_code == 422
    assert c.get("/api/limits/nowhere").status_code == 404
    scopes = [s["scope"] for s in c.get("/api/limits").json()["scopes"]]
    assert scopes[0] == "claude_discretionary" and scopes[-1] == "system"


def test_a_strategys_limit_shows_the_value_its_runner_starts_with():
    # the UI spec lagged the params (Friend, 2026-09-29: spec 15,000, params 5,000): the params win
    lim = L.Limits(L.MemoryLimitStore(), specs_for=lambda slug: SPECS, values_for=lambda slug: {"daily_loss_cap": 5000.0})
    assert lim.values("demo_strategy")["daily_loss_cap"] == 5000.0
