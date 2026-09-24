"""
api/app.py — the FastAPI application factory.

``create_app()`` bootstraps the platform (sys.path, .env, the strategy plugin by
path, the DB write guard), mounts every router under ``/api``, and owns the
process-wide services: the WebSocket event hub, the job manager and the market-data
hub (whose request gate every upstream call of the process passes).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
import subprocess
from contextlib import asynccontextmanager

from api.bootstrap import WORKING_COPY, BootstrapError, ReadOnlyViolation, bootstrap, install_db_read_only_guard

logger = logging.getLogger("alan_trader.api")

CONTRACT_VERSION = "2"


def _git(*args: str) -> str:
    try:
        out = subprocess.run(["git", *args], cwd=str(WORKING_COPY), capture_output=True, text=True, timeout=5)
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:
        return ""


def build_info() -> dict:
    return {"version": _git("rev-parse", "--short", "HEAD") or "unknown",
            "branch": _git("rev-parse", "--abbrev-ref", "HEAD") or "unknown",
            "python": platform.python_version()}


def create_app():
    info = bootstrap()
    install_db_read_only_guard()

    from fastapi import FastAPI, Request
    from fastapi.exceptions import RequestValidationError
    from fastapi.responses import JSONResponse
    from starlette.exceptions import HTTPException as StarletteHTTPException

    from api.events import EventHub, LogForwarder
    from api.jobs import JobManager
    from api.serialize import to_jsonable
    from api.services.db import DatabaseUnavailable
    from api.services.market import MissingData, NeedsApiKey

    class SafeJSONResponse(JSONResponse):
        """JSON with NaN/±inf → null and numpy/pandas/date values converted."""

        def render(self, content) -> bytes:
            return json.dumps(to_jsonable(content), ensure_ascii=False, allow_nan=False,
                              separators=(",", ":")).encode("utf-8")

    build = build_info()
    # The service's own records (job started / finished / failed) always reach the event
    # stream, whatever the host process configured for the root logger.
    svc_log = logging.getLogger("alan_trader.api")
    if svc_log.getEffectiveLevel() > logging.INFO:
        svc_log.setLevel(logging.INFO)
    hub = EventHub()
    hub.version = build["version"]
    jobs = JobManager(max_workers=int(os.environ.get("ALAN_TRADER_API_JOB_WORKERS", "2") or 2),
                      publish=hub.publish)
    forwarder = LogForwarder(hub)

    from api.marketdata.service import build_hub
    from data import request_gate
    market_hub = build_hub()

    # other checkouts' runner state (read only): their positions stay priced and owned by them here
    from api.config import external_state_dirs, paper_account_id
    from paper import views as paper_views
    paper_views.EXTRA_STATE_DIRS = external_state_dirs()

    from api.services.orders import OrderBook
    order_book = OrderBook(market_hub, paper_account_id, publish=hub.publish)
    from api.services.alerts import AlertEngine
    alert_engine = AlertEngine(market_hub, publish=hub.publish)
    from api.services.runner import RunnerManager
    runners = RunnerManager(publish=hub.publish)
    from api.services.volstats import VolStats
    vol_stats = VolStats(market_hub)

    from api.redact import RedactingFilter, install_redaction, redact
    forwarder.addFilter(RedactingFilter())

    @asynccontextmanager
    async def lifespan(app):
        hub.bind(asyncio.get_running_loop())
        root = logging.getLogger()
        root.addHandler(forwarder)
        install_redaction()
        request_gate.install(market_hub.gate)          # every requests / yfinance call now passes the gate
        request_gate.install_hooks()
        market_hub.start(asyncio.get_running_loop())
        order_book.start()
        alert_engine.start()
        runners.start_monitor()
        beat = asyncio.create_task(hub.heartbeat_forever())
        logger.info("alan_trader service %s (%s) up; strategies from %s",
                    build["version"], build["branch"], info.get("strategies_dir"))
        try:
            yield
        finally:
            beat.cancel()
            order_book.stop()
            alert_engine.stop()
            runners.shutdown()
            vol_stats.shutdown()
            await market_hub.stop()
            if request_gate.installed() is market_hub.gate:
                request_gate.install(None)
            root.removeHandler(forwarder)
            jobs.shutdown()
            hub.unbind()

    app = FastAPI(title="alan_trader service", version=f"contract v{CONTRACT_VERSION} · {build['version']}",
                  default_response_class=SafeJSONResponse, lifespan=lifespan,
                  docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
    app.state.hub = hub
    app.state.jobs = jobs
    app.state.market = market_hub
    app.state.orders = order_book
    app.state.alerts = alert_engine
    app.state.runner = runners
    app.state.volstats = vol_stats
    app.state.build = build
    app.state.bootstrap = info
    app.state.json_response = SafeJSONResponse

    def _err(status: int, detail: str):
        return SafeJSONResponse(status_code=status, content={"detail": detail})

    @app.exception_handler(StarletteHTTPException)
    async def _http_exc(request: Request, exc: StarletteHTTPException):
        return _err(exc.status_code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        parts = []
        for e in exc.errors():
            loc = ".".join(str(x) for x in e.get("loc", []) if x not in ("body", "query", "path"))
            parts.append(f"{loc}: {e.get('msg')}" if loc else str(e.get("msg")))
        return _err(422, "; ".join(parts) or "invalid request")

    @app.exception_handler(DatabaseUnavailable)
    async def _db_down(request: Request, exc: DatabaseUnavailable):
        return _err(503, str(exc))

    @app.exception_handler(MissingData)
    async def _missing(request: Request, exc: MissingData):
        return _err(422, str(exc.args[0]) if exc.args else "no data")

    @app.exception_handler(NeedsApiKey)
    async def _no_key(request: Request, exc: NeedsApiKey):
        return _err(422, str(exc))

    from api.marketdata.options import NoChain
    from data.request_gate import ProviderUnavailable

    @app.exception_handler(ProviderUnavailable)
    async def _provider_unavailable(request: Request, exc: ProviderUnavailable):
        # the gate refused an upstream call (over budget / backing off): nothing was sent upstream
        resp = _err(503, redact(str(exc)))
        if exc.retry_after:
            resp.headers["Retry-After"] = str(int(exc.retry_after) + 1)
        return resp

    @app.exception_handler(NoChain)
    async def _no_chain(request: Request, exc: NoChain):
        return _err(422, redact(str(exc.args[0]) if exc.args else "no option chain"))

    @app.exception_handler(ReadOnlyViolation)
    async def _ro(request: Request, exc: ReadOnlyViolation):
        logger.error("blocked a database write: %s", exc)
        return _err(500, str(exc))

    import requests

    @app.exception_handler(requests.exceptions.RequestException)
    async def _upstream(request: Request, exc: requests.exceptions.RequestException):
        # A data provider refused or failed (e.g. Polygon 403 for data outside the plan): not our bug, so a 502
        # with the provider's status and no traceback. The URL would carry the API key, hence redact().
        resp = getattr(exc, "response", None)
        status = f"{resp.status_code} {resp.reason}" if resp is not None else type(exc).__name__
        host = getattr(getattr(exc, "request", None), "url", "") or ""
        host = host.split("/")[2] if host.count("/") >= 2 else "the data provider"
        logger.warning("upstream %s on %s %s: %s", host, request.method, request.url.path, redact(status))
        return _err(502, f"{host} answered {status} for this request")

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        logger.exception("unhandled error on %s %s", request.method, request.url.path)
        return _err(500, redact(f"{type(exc).__name__}: {exc}"))

    from api.routers import (data, guides, health, jobs as jobs_router, lists, market, options, orders, paper, runner,
                             strategies)
    for r in (health.router, strategies.router, jobs_router.router, paper.router, orders.router, market.router,
              options.router, lists.router, data.router, runner.router, guides.router):
        app.include_router(r, prefix="/api")
    from api.routers import events as events_router, stream as stream_router
    app.include_router(events_router.router, prefix="/api")
    app.include_router(stream_router.router, prefix="/api")
    return app


__all__ = ["create_app", "BootstrapError", "CONTRACT_VERSION"]
