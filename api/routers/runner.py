"""/api/runner — paper runner sessions: list all, start and stop the service's own; arm scheduled paper runs."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Request

from api.services import runner as RN

router = APIRouter(tags=["runner"])


@router.get("/runner/sessions")
def runner_sessions(request: Request):
    return request.app.state.runner.sessions()


@router.post("/runner/{strategy}/start")
def runner_start(strategy: str, request: Request, body: Optional[dict] = Body(default=None)):
    try:
        return request.app.state.runner.start(strategy, body or {})
    except KeyError:
        raise HTTPException(404, f"unknown strategy {strategy!r}")
    except RN.RunnerError as exc:
        raise HTTPException(422, str(exc))
    except RN.RunnerConflict as exc:
        raise HTTPException(409, str(exc))


@router.post("/runner/{strategy}/stop")
def runner_stop(strategy: str, request: Request):
    try:
        return request.app.state.runner.stop(strategy)
    except RN.RunnerConflict as exc:
        raise HTTPException(409, str(exc))
    except LookupError as exc:
        raise HTTPException(404, str(exc))


@router.post("/runner/stop-all")
def runner_stop_all(request: Request):
    """The kill switch: stop every session the service started (never one it did not)."""
    return {"stopped": request.app.state.runner.stop_all()}


@router.get("/runner/arms")
def runner_arms(request: Request):
    return request.app.state.arms.arms()


@router.post("/runner/{strategy}/arm")
def runner_arm(strategy: str, request: Request, body: Optional[dict] = Body(default=None)):
    from api.services.arms import ArmError
    b = body or {}
    try:
        return request.app.state.arms.arm(strategy, b.get("schedule") or "weekdays", b.get("date"), b.get("variant"))
    except ArmError as exc:
        raise HTTPException(422, str(exc))


@router.delete("/runner/{strategy}/arm")
def runner_disarm(strategy: str, request: Request, variant: Optional[str] = None):
    from api.services.arms import ArmError
    try:
        rows = request.app.state.arms.disarm(strategy, variant)
    except ArmError as exc:
        raise HTTPException(422, str(exc))
    if not rows:
        raise HTTPException(404, f"{strategy}{':' + variant if variant else ''} is not armed")
    return rows
