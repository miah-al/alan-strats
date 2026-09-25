"""
The service must not need the Dash app: ``app/`` (as ``app`` or ``alan_trader.app``) and Dash
itself are about to be deleted. A fresh interpreter blocks both with a meta-path finder, builds
the FastAPI app and exercises the endpoints that used to reach into ``app.*`` (health, the
strategy list / detail / guide, the backtest loader specs, the paper views, the market helpers
that do not need the network).

Strategy plugins whose own ``ui.py`` imports Dash (or ``alan_trader.app``) cannot load their UI
hooks with Dash gone; the registry then falls back to the generic ``StrategyUI`` for them. That is
the plugin's dependency, not the service's: the test reports those slugs rather than failing.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

_PROBE = r'''
import importlib.abc, json, logging, os, sys
BLOCKED = ("app", "alan_trader.app", "dash", "dash_bootstrap_components", "dash_ag_grid",
           "dash_mantine_react_table")

class Blocker(importlib.abc.MetaPathFinder):
    hits = []
    def find_spec(self, name, path=None, target=None):
        if any(name == b or name.startswith(b + ".") for b in BLOCKED):
            Blocker.hits.append(name)
            raise ImportError(f"blocked by the no-Dash test: {name}")
        return None

sys.meta_path.insert(0, Blocker())
sys.path[:0] = [REPO, os.path.dirname(REPO)]

ui_failures = []
class Grab(logging.Handler):
    def emit(self, record):
        msg = record.getMessage()
        if "UI module for" in msg and "failed" in msg:
            ui_failures.append(msg.split("UI module for ", 1)[1].split(" ", 1)[0])
logging.getLogger().addHandler(Grab())

from fastapi.testclient import TestClient
from api.app import create_app
app = create_app()
out = {"status": {}, "ui_fallbacks": ui_failures}
with TestClient(app, raise_server_exceptions=False) as c:
    def get(path):
        r = c.get(path)
        out["status"][path] = r.status_code
        return r
    get("/api/health")
    slugs = [s["slug"] for s in get("/api/strategies?include_hidden=true").json()]
    for s in slugs:
        get(f"/api/strategies/{s}")
        get(f"/api/strategies/{s}/guide")
    db_ok = c.get("/api/health").json()["db"]["ok"]
    out["db_ok"] = db_ok
    if db_ok:
        for p in ("/api/paper/summary", "/api/paper/positions?status=all", "/api/paper/transactions?limit=5",
                  "/api/paper/runner", "/api/market/tickers", "/api/data/coverage"):
            get(p)
    # modules that used to import the page code, imported in full
    import engine.strategy_backtest, engine.strategy_scan, engine.backtest_loaders, engine.guides
    import paper.views, data.movers, data.treasury_curve
    import api.services.market, api.services.paper, api.services.strategies, api.services.structure
out["blocked_attempts"] = sorted(set(Blocker.hits))
out["loaded"] = sorted(m for m in sys.modules
                       if any(m == b or m.startswith(b + ".") for b in BLOCKED))
print("RESULT " + json.dumps(out))
'''


def test_service_runs_without_the_dash_app():
    code = f"REPO = {str(REPO)!r}\n" + _PROBE
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    proc = subprocess.run([sys.executable, "-c", code], cwd=str(REPO), capture_output=True, text=True,
                          timeout=600, env=env)
    line = next((l for l in proc.stdout.splitlines() if l.startswith("RESULT ")), None)
    assert line is not None, f"probe failed (exit {proc.returncode}):\n{proc.stdout[-3000:]}\n{proc.stderr[-6000:]}"
    res = json.loads(line[len("RESULT "):])
    assert res["loaded"] == [], f"app/Dash modules were imported: {res['loaded']}"
    bad = {p: s for p, s in res["status"].items() if s >= 500 and not (s == 503 and not res["db_ok"])}
    assert not bad, f"endpoints failed without the Dash app: {bad}"
    assert res["status"]["/api/health"] == 200
    # every blocked import attempt must come from a strategy plugin's own UI module
    # (reported, not failed: the plugin's dependency on Dash, not the service's)
    if res["ui_fallbacks"]:
        print("plugin UI modules that need Dash / alan_trader.app:", ", ".join(sorted(set(res["ui_fallbacks"]))))
