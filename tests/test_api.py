"""
The service API (api/): contract shapes, jobs, events, serialisation, the read-only
database guard. FastAPI TestClient, no server process.

Nothing here writes to the database, calls the broker or spends Polygon requests:
the scan runs a toy strategy on synthetic data, and every test that reads the
shared AlanStrats database is marked ``db`` and skips when it cannot be reached.

Importing this module runs ``api.bootstrap``, which loads the alan_trader_strategies
plugin by path (never through its parent directory) — so, as in a checkout that sits
next to the plugin, the rest of the session sees the installed strategies too.
"""
from __future__ import annotations

import logging
import math
import os
import sys
import threading
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
for _p in (str(REPO), str(REPO.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from api.bootstrap import WORKING_COPY, bootstrap  # noqa: E402

BOOT = bootstrap()

from alan_trader.strategy_api import registry as R  # noqa: E402
from alan_trader.strategy_api.base import BacktestResult, BaseStrategy, SignalResult  # noqa: E402
from alan_trader.strategy_api.plugin import StrategyPlugin  # noqa: E402
from alan_trader.strategy_api.ui import ScanContext, StrategyUI  # noqa: E402

from api import serialize as SER  # noqa: E402

TOY = "toy_api_probe"


# ── a throwaway plugin (no network, no DB) ────────────────────────────────────

class _ToyStrategy(BaseStrategy):
    name = TOY
    display_name = "Toy API Probe"
    status = BaseStrategy.status.__class__("active")

    def generate_signal(self, market_snapshot):
        return SignalResult(self.name, "HOLD", 0.0, 0.0)

    def backtest(self, price_data, auxiliary_data, starting_capital=100_000, **kw):
        eq = pd.Series([starting_capital] * 3, index=pd.bdate_range("2024-01-01", periods=3))
        return BacktestResult(self.name, eq, eq.pct_change().fillna(0), pd.DataFrame(), {})

    def get_params(self):
        return {"alpha": 1.5, "when": date(2024, 1, 2)}

    def get_backtest_ui_params(self):
        return [{"key": "alpha", "label": "Alpha", "type": "slider", "min": 0.0, "max": 3.0,
                 "default": 1.5, "step": 0.5},
                {"key": "n", "label": "N", "type": "slider", "min": 1, "max": 10, "default": 3, "step": 1}]


class UI(StrategyUI):
    screener_params = [{"id": "min_score", "label": "Min score", "min": 0, "max": 100, "step": 1,
                        "default": 10, "fmt": ".0f"}]
    default_params = {"min_score": 10}
    columns = [
        {"field": "Ticker", "width": 120, "pinned": "left"},
        {"field": "Price", "width": 90, "type": "numericColumn"},
        {"field": "IVR", "width": 90, "type": "numericColumn"},          # carries "25.0%" strings
        {"field": "Score", "width": 90, "type": "numericColumn", "sort": "desc"},
        {"field": "Status", "width": 120},
        {"field": "Chart", "valueGetter": {"function": "'View'"}},        # a client-side button
        {"field": "_raw", "hide": True},
    ]

    def scan(self, ctx: ScanContext) -> list[dict]:
        rows = []
        for i, (t, df) in enumerate(ctx.price_dfs.items()):
            rows.append({"Ticker": t, "Price": float(df["close"].iloc[-1]), "IVR": f"{25 + i:.1f}%",
                         "score": 50.0 + 10 * i, "all_pass": i == 1, "n_pass": i + 1,
                         "_raw": {"nan": float("nan"), "i": np.int64(i)}})
        return rows

    def vix_banner_status(self, vix, vix_20d_avg):
        return ("toy banner", "muted")


def _toy_plugin() -> StrategyPlugin:
    meta = {TOY: {"display_name": "Toy API Probe", "type": "rule", "status": "active",
                  "class_path": f"{__name__}._ToyStrategy", "ui": __name__, "ui_visible": True,
                  "ui_order": -5, "score": (77, "B"), "review_status": "reviewing",
                  "guide_path": str(REPO / "README.md"), "default_ticker": "qqq"}}
    return StrategyPlugin(name="toy_api", metadata=meta)


@pytest.fixture
def toy():
    from api.services import strategies as S
    before = list(R.plugins())
    R.register_plugin(_toy_plugin())
    S.clear_cache()
    try:
        yield TOY
    finally:
        R._install(before)
        S.clear_cache()


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from api.app import create_app
    from api.bootstrap import uninstall_db_read_only_guard
    app = create_app()
    try:
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c
    finally:
        # other test modules in this session may legitimately write (e.g. the ledger round trip)
        uninstall_db_read_only_guard()


def _db_ok() -> bool:
    try:
        from api.services.db import ping
        return ping()[0]
    except Exception:
        return False


DB = _db_ok()
needs_db = pytest.mark.skipif(not DB, reason="AlanStrats database unreachable")


def _wait(client, job_id: str, timeout: float = 120.0) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(f"/api/jobs/{job_id}").json()
        if j["status"] in ("succeeded", "failed", "cancelled"):
            return j
        time.sleep(0.1)
    raise AssertionError(f"job {job_id} did not finish in {timeout}s")


# ── bootstrap ─────────────────────────────────────────────────────────────────

def test_bootstrap_imports_this_checkout_only():
    import alan_trader
    import app
    for mod in (alan_trader, app):
        Path(mod.__file__).resolve().relative_to(WORKING_COPY)      # raises if outside
    for p in sys.path:
        cand = Path(p or os.getcwd()) / "alan_trader"
        assert not (cand.is_dir() and cand.resolve() != WORKING_COPY), f"foreign alan_trader on sys.path: {p}"
    if BOOT.get("strategies_dir"):
        import alan_trader_strategies
        Path(alan_trader_strategies.__file__).resolve().relative_to(Path(BOOT["strategies_dir"]))


# ── serialisation ─────────────────────────────────────────────────────────────

def test_to_jsonable_handles_numpy_pandas_dates_and_non_finite():
    v = SER.to_jsonable({"a": np.float64("nan"), "b": float("inf"), "c": np.int64(3), "d": np.bool_(True),
                         "e": pd.Timestamp("2024-01-02"), "f": pd.Timestamp("2024-01-02 09:30", tz="America/New_York"),
                         "g": date(2024, 1, 3), "h": pd.NaT, 5: [np.float32(1.5)], "i": (1, 2)})
    assert v == {"a": None, "b": None, "c": 3, "d": True, "e": "2024-01-02", "f": "2024-01-02T09:30:00-05:00",
                 "g": "2024-01-03", "h": None, "5": [1.5], "i": [1, 2]}
    assert SER.to_jsonable(object(), strict=True) is SER.DROP
    assert SER.to_jsonable({"x": object(), "y": 1}, strict=True) == {"y": 1}


def test_series_and_table_shapes():
    s = pd.Series([1.0, float("nan")], index=pd.to_datetime(["2024-01-02", "2024-01-03"]))
    assert SER.series(s, "eq") == {"name": "eq", "t": ["2024-01-02", "2024-01-03"], "v": [1.0, None]}
    df = pd.DataFrame({"Ticker": ["SPY"], "n": [3], "px": [1.5], "ok": [True], "d": pd.to_datetime(["2024-01-02"])})
    t = SER.table_from_df(df, headers={"px": "Price"}, formats={"px": "price"})
    types = {c["field"]: c["type"] for c in t["columns"]}
    assert types == {"Ticker": "string", "n": "integer", "px": "number", "ok": "bool", "d": "date"}
    px = next(c for c in t["columns"] if c["field"] == "px")
    assert px["header"] == "Price" and px["format"] == "price"
    assert set(px) >= {"field", "header", "type", "format", "width", "pinned", "sort"}
    assert t["rows"] == [{"Ticker": "SPY", "n": 3, "px": 1.5, "ok": True, "d": "2024-01-02"}]


def test_aggrid_columns_follow_the_data():
    rows = [{"Ticker": "SPY", "IVR": "25.0%", "Score": 50.0}]
    t = SER.table_from_rows(rows, col_defs=UI.columns)
    cols = {c["field"]: c for c in t["columns"]}
    assert "Chart" not in cols                                      # a pure client-side cell
    assert cols["Ticker"]["pinned"] == "left" and cols["Ticker"]["width"] == 120
    assert cols["IVR"]["type"] == "string" and cols["IVR"]["numeric"] is True   # formatted strings stay strings
    assert cols["Score"]["type"] == "number" and cols["Score"]["sort"] == "desc"
    assert cols["_raw"]["hidden"] is True


# ── health / errors ───────────────────────────────────────────────────────────

def test_health_shape(client):
    h = client.get("/api/health").json()
    assert h["service"] == "alan_trader" and h["status"] in ("ok", "degraded")
    assert set(h["db"]) >= {"ok", "server", "database", "error"}
    assert set(h["strategies"]) == {"plugins", "count", "visible"}
    assert isinstance(h["polygon_key"], bool) and isinstance(h["tastytrade_creds"], bool)
    assert h["db"]["read_only_guard"] is True


def test_errors_are_detail_json(client):
    r = client.get("/api/strategies/no_such_strategy")
    assert r.status_code == 404 and "no_such_strategy" in r.json()["detail"]
    r = client.get("/api/jobs/nope")
    assert r.status_code == 404 and "detail" in r.json()
    r = client.get("/api/paper/positions?status=bogus")
    assert r.status_code == 422 and isinstance(r.json()["detail"], str)


def test_read_only_guard_refuses_writes_before_they_reach_a_server(client):
    from sqlalchemy import create_engine, text
    from api.bootstrap import ReadOnlyViolation
    eng = create_engine("sqlite://")                     # in-memory; the shared DB is never touched
    with eng.connect() as c:
        assert c.execute(text("SELECT 1")).scalar() == 1
        with pytest.raises(ReadOnlyViolation):
            c.execute(text("CREATE TABLE t (x int)"))
        with pytest.raises(ReadOnlyViolation):
            c.execute(text("SELECT 1 AS x; DELETE FROM t"))
        # the words inside string literals / identifiers do not trip it
        assert c.execute(text("SELECT 'insert or update' AS UpdatedAt")).scalar() == "insert or update"


# ── strategies ────────────────────────────────────────────────────────────────

_INFO_KEYS = {"slug", "display_name", "label", "description", "type", "status", "review_status", "score",
              "asset_class", "typical_holding_days", "target_sharpe", "ui_visible", "plugin", "default_ticker",
              "default_from", "default_capital", "has_guide", "has_screener", "has_signal_alert",
              "has_live_session", "is_trainable", "trade_kind", "is_credit", "modal", "locked_tickers",
              "locked_label"}


def test_strategy_list_and_detail(client, toy):
    items = client.get("/api/strategies").json()
    assert items[0]["slug"] == TOY                        # ui_order -5 sorts first
    info = items[0]
    assert _INFO_KEYS <= set(info)
    assert info["score"] == {"value": 77, "grade": "B"} and info["has_screener"] is True
    assert info["default_ticker"] == "QQQ" and info["plugin"] == "toy_api" and info["has_guide"] is True
    d = client.get(f"/api/strategies/{TOY}").json()
    assert _INFO_KEYS <= set(d)
    assert d["screener"]["params"][0]["id"] == "min_score"
    assert d["screener"]["default_params"] == {"min_score": 10}
    assert "ETF Core" in d["screener"]["universes"]
    assert [c["field"] for c in d["screener"]["columns"]][:2] == ["Ticker", "Price"]
    assert [p["key"] for p in d["backtest"]["params"]] == ["alpha", "n"]
    assert d["params"] == {"alpha": 1.5, "when": "2024-01-02"}
    g = client.get(f"/api/strategies/{TOY}/guide").json()
    assert g["slug"] == TOY and g["markdown"].startswith("# alan_trader")


def test_plugin_strategies_are_listed_when_installed(client):
    if not BOOT.get("strategies_dir"):
        pytest.skip("no strategy plugin directory")
    items = client.get("/api/strategies").json()
    assert items and all(i["ui_visible"] for i in items)
    hidden = client.get("/api/strategies?include_hidden=true").json()
    assert len(hidden) >= len(items)


def test_scan_job_end_to_end_with_events(client, toy, monkeypatch):
    import engine.strategy_scan as SS
    idx = pd.bdate_range("2024-01-01", periods=30)

    def fake_fetch(tickers, api_key, progress=None):
        for i, t in enumerate(tickers):
            if progress:
                progress(0.1 + 0.3 * i / len(tickers), f"prices {t}")
        prices = {t: pd.DataFrame({"close": np.linspace(100, 110, len(idx)) + i}, index=idx)
                  for i, t in enumerate(tickers)}
        return pd.Series(np.linspace(15, 17, len(idx)), index=idx), prices, {t: {} for t in tickers}

    monkeypatch.setattr(SS, "fetch_scan_data", fake_fetch)
    monkeypatch.setenv("POLYGON_API_KEY", os.environ.get("POLYGON_API_KEY") or "test-key")
    with client.websocket_connect("/api/events") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello" and hello["version"]
        r = client.post(f"/api/strategies/{TOY}/scan", json={"universe": "Custom", "tickers": ["aaa", "BBB"],
                                                              "params": {"min_score": 5}})
        assert r.status_code == 202
        job_id = r.json()["job_id"]
        statuses, logs = [], []
        while True:
            m = ws.receive_json()
            if m["type"] == "job" and m["job"]["id"] == job_id:
                assert "result" not in m["job"]
                statuses.append(m["job"]["status"])
                if m["job"]["status"] in ("succeeded", "failed", "cancelled"):
                    break
            elif m["type"] == "log":
                logs.append(m)
    assert statuses[0] == "queued" and "running" in statuses and statuses[-1] == "succeeded"
    assert any(job_id in m["message"] for m in logs)
    job = client.get(f"/api/jobs/{job_id}").json()
    res = job["result"]
    assert set(res) >= {"table", "vix", "tickers", "errors"}
    assert res["tickers"] == ["AAA", "BBB"] and res["params"] == {"min_score": 5}
    rows = res["table"]["rows"]
    assert [r["Ticker"] for r in rows] == ["BBB", "AAA"]                        # score descending
    for r in rows:
        assert {"score", "all_pass", "n_pass", "Status"} <= set(r)
    assert rows[0]["_raw"] == {"nan": None, "i": 1}
    fields = {c["field"]: c for c in res["table"]["columns"]}
    assert fields["IVR"]["type"] == "string" and fields["score"]["hidden"] is True
    assert res["vix"]["banner"] == {"text": "toy banner", "tone": "muted"}
    assert math.isclose(res["vix"]["last"], 17.0)
    listed = client.get("/api/jobs").json()
    assert listed[0]["id"] == job_id and "result" not in listed[0]


def test_scan_rejects_bad_requests(client, toy):
    assert client.post(f"/api/strategies/{TOY}/scan", json={"universe": "Nope"}).status_code == 422
    r = client.post(f"/api/strategies/{TOY}/scan", json={"universe": "ETF Core", "params": {"bogus": 1}})
    assert r.status_code == 422 and "bogus" in r.json()["detail"]
    assert client.post("/api/strategies/unknown_x/scan", json={}).status_code == 404


def test_backtest_request_validation(client, toy):
    assert client.post(f"/api/strategies/{TOY}/backtest", json={"params": {"zzz": 1}}).status_code == 422
    r = client.post(f"/api/strategies/{TOY}/backtest", json={"params": {"n": 99}})
    assert r.status_code == 422 and "maximum" in r.json()["detail"]
    r = client.post(f"/api/strategies/{TOY}/backtest", json={"params": {"n": 2.5}})
    assert r.status_code == 422
    r = client.post(f"/api/strategies/{TOY}/backtest", json={"from": "2024-05-01", "to": "2024-01-01"})
    assert r.status_code == 422


def test_signal_for_a_strategy_without_one(client, toy):
    s = client.get(f"/api/strategies/{TOY}/signal").json()
    assert s["signal"] is None and s["session"] is None and "no live signal" in s["detail"]


# ── jobs ──────────────────────────────────────────────────────────────────────

def test_job_cancellation_is_cooperative():
    from api.jobs import JobManager
    events: list[dict] = []
    jm = JobManager(max_workers=1, publish=events.append)
    started, release = threading.Event(), threading.Event()
    seen = {}

    def slow(ctx):
        started.set()
        release.wait(5)
        try:
            ctx.progress(0.5, "halfway")
        except BaseException as exc:                    # JobCancelled
            seen["exc"] = type(exc).__name__
            raise
        return {"never": "returned"}

    def fast(ctx):
        return {"ok": 1}

    job = jm.submit("scan", "slow", slow)
    queued = jm.submit("scan", "queued behind", fast)
    assert started.wait(5)
    assert jm.cancel(queued.id).status == "cancelled"               # still queued: cancelled outright
    j = jm.cancel(job.id)
    assert j.status == "cancelled" and j.cancel_requested
    release.set()
    for _ in range(50):
        if seen:
            break
        time.sleep(0.05)
    assert seen.get("exc") == "JobCancelled"
    assert jm.get(job.id).result is None and jm.get(job.id).status == "cancelled"
    ok = jm.submit("scan", "after", fast)
    for _ in range(100):
        if jm.get(ok.id).status == "succeeded":
            break
        time.sleep(0.02)
    assert jm.get(ok.id).result == {"ok": 1}
    assert [e["job"]["status"] for e in events if e["job"]["id"] == ok.id][-1] == "succeeded"
    jm.shutdown()


def test_log_records_are_forwarded(client):
    with client.websocket_connect("/api/events") as ws:
        assert ws.receive_json()["type"] == "hello"
        logging.getLogger("alan_trader.test_api").warning("probe %s", 42)
        while True:
            m = ws.receive_json()
            if m["type"] == "log" and m["logger"] == "alan_trader.test_api":
                break
    assert m["level"] == "WARNING" and m["message"] == "probe 42" and m["time"]


# ── against the real database (read-only) ─────────────────────────────────────

@needs_db
def test_real_backtest_job(client):
    if "iron_condor_rules" not in R.STRATEGY_METADATA:
        pytest.skip("reference strategy not installed")
    slug = "iron_condor_rules"
    r = client.post(f"/api/strategies/{slug}/backtest",
                    json={"ticker": "SPY", "from": "2025-01-01", "to": "2025-12-31", "capital": 100000,
                          "params": {"dte_target": 40}})
    assert r.status_code == 202
    j = _wait(client, r.json()["job_id"])
    if j["status"] == "failed" and "No price bars" in (j["error"] or ""):
        pytest.skip(j["error"])
    assert j["status"] == "succeeded", j["error"]
    res = j["result"]
    assert set(res) >= {"slug", "ticker", "from", "to", "capital", "params", "metrics", "bench_metrics", "equity",
                        "bench_equity", "drawdown", "yearly", "trades", "coverage", "warnings", "extra"}
    assert res["params"]["dte_target"] == 40
    assert set(res["equity"]) == {"name", "t", "v"} and len(res["equity"]["t"]) == len(res["equity"]["v"]) > 100
    assert max(v for v in res["drawdown"]["v"] if v is not None) <= 0
    assert res["yearly"] and set(res["yearly"][0]) == {"year", "strategy", "benchmark"}
    assert "sharpe" in res["metrics"] and "total_return_pct" in res["bench_metrics"]


@needs_db
def test_paper_endpoints_shapes(client):
    s = client.get("/api/paper/summary").json()
    assert set(s) >= {"starting_capital", "cash", "market_value", "equity", "realized_pnl", "unrealized_pnl",
                      "total_pnl", "total_return", "open_positions", "closed_positions", "asof", "live_marks"}
    assert math.isclose(s["equity"], s["cash"] + s["market_value"], abs_tol=0.01)
    pos = client.get("/api/paper/positions?status=all").json()
    fields = [c["field"] for c in pos["columns"]]
    for f in ("trade_group_id", "strategy", "strategy_label", "underlying", "structure", "expiry", "dte",
              "contracts", "opened", "closed", "entry_net", "mark", "market_value", "pnl", "pnl_pct",
              "max_risk", "managed_by", "status"):
        assert f in fields
    if pos["rows"]:
        tg = pos["rows"][0]["trade_group_id"]
        legs = client.get(f"/api/paper/positions/{tg}/legs").json()
        assert legs["rows"] and {"symbol", "side", "quantity", "entry_price", "mark", "pnl"} <= set(legs["rows"][0])
    assert client.get("/api/paper/positions/NO-SUCH-GROUP/legs").status_code == 404
    tx = client.get("/api/paper/transactions?limit=3").json()
    assert "columns" in tx and len(tx["rows"]) <= 3
    run = client.get("/api/paper/runner").json()
    assert set(run) >= {"sessions", "marks"}


@needs_db
def test_market_and_data_endpoints_from_the_database(client):
    tick = client.get("/api/market/tickers").json()
    assert tick and set(tick[0]) == {"ticker", "first", "last", "bars"}
    spy = next((t for t in tick if t["ticker"] == "SPY"), None)
    if spy is None:
        pytest.skip("SPY bars not stored")
    b = client.get(f"/api/market/bars/SPY?from={spy['last'][:8]}01&to={spy['last']}").json()
    assert b["source"] == "db" and b["interval"] == "1d"
    assert len(b["t"]) == len(b["o"]) == len(b["h"]) == len(b["l"]) == len(b["c"]) == len(b["v"]) > 0
    assert client.get("/api/market/bars/SPY?interval=5m").status_code == 422
    cov = client.get("/api/data/coverage").json()
    names = [t["name"] for t in cov["tables"]]
    assert "price_bars" in names and "global" in names
    yc = client.get("/api/market/yield-curve").json()
    assert len(yc["tenors"]) == len(yc["yields"]) > 0
