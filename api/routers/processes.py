"""/api/processes — the process monitor (api/services/processes.py): every process a trading day depends on, with a
status and the reason. Read only; stopping a runner is POST /api/runner/{strategy}/stop."""
from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/processes")
def processes(request: Request):
    from api.services import processes as P
    return P.snapshot(request.app.state)
