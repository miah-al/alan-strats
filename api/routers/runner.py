"""/api/runner — paper runner sessions: list all, start and stop the service's own."""
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
