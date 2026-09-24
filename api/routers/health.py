"""GET /api/health — is the service, its database and its plugin set usable."""
from __future__ import annotations

import os

from fastapi import APIRouter, Request

from api.events import now_iso

from api.app import CONTRACT_VERSION  # noqa: E402

router = APIRouter(tags=["health"])


@router.get("/health")
def health(request: Request):
    from alan_trader.strategy_api import registry as R
    from engine.env import get_polygon_api_key
    from api.bootstrap import db_guard_installed, write_allow_list
    from api.services.db import ping, server_and_database

    ok, err = ping()
    server, database = server_and_database()
    build = request.app.state.build
    return {
        "status": "ok" if ok else "degraded",
        "service": "alan_trader",
        "version": build["version"],
        "branch": build["branch"],
        "python": build["python"],
        "time": now_iso(),
        "db": {"ok": ok, "server": server, "database": database, "error": err, "read_only_guard": db_guard_installed(),
               "write_allow_list": write_allow_list()},
        "polygon_key": bool(get_polygon_api_key()),
        "tastytrade_creds": bool(os.environ.get("TT_SECRET") and os.environ.get("TT_REFRESH")),
        "strategies": {"plugins": [p.name for p in R.plugins()], "count": len(R.STRATEGY_METADATA),
                       "visible": len(R.ui_slugs())},
        "contract": CONTRACT_VERSION,
        "working_copy": request.app.state.bootstrap.get("working_copy"),
        "strategies_dir": request.app.state.bootstrap.get("strategies_dir"),
        "jobs": {"workers": request.app.state.jobs._pool._max_workers,
                 "active": sum(1 for j in request.app.state.jobs.list() if j.status in ("queued", "running"))},
        "event_clients": request.app.state.hub.client_count,
        "paper_account_id": request.app.state.orders.account_id(),
        "working_orders": request.app.state.orders.working_count(),
        "market_data": [{"name": p["name"], "state": p["state"], "detail": p["detail"]}
                        for p in request.app.state.market.providers_status()],
    }
