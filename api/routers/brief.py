"""/api/brief — the AI morning brief for the paper condor: today's decision row, run it now, the history, the shadow A/B."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(tags=["brief"])


def _brief(request: Request):
    b = getattr(request.app.state, "brief", None)
    if b is None or b.store is None:
        raise HTTPException(503, "the morning brief is off in this service (ALAN_TRADER_BRIEF=off)")
    return b


@router.get("/brief/today")
def brief_today(request: Request):
    """Today's brief, or the not-yet-run shape (decision null)."""
    return _brief(request).today()


@router.post("/brief/run")
def brief_run(request: Request, force: bool = False):
    """Write today's brief now and return it. A day's brief is written once: a second call returns the row that
    stands; ``force=true`` replaces it (noted in the row) — for a re-run before the 10:00 entry, never after."""
    b = _brief(request)
    try:
        return b.run(force=force)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))


@router.get("/brief/history")
def brief_history(request: Request, days: int = 60):
    if not 1 <= days <= 3660:
        raise HTTPException(422, "days must be between 1 and 3660")
    return _brief(request).history(days)


@router.get("/brief/scorecard")
def brief_scorecard(request: Request):
    """Ledger A (the paper condor as traded) against the brief's shadow line B and the two rule controls C and D."""
    return _brief(request).scorecard()


@router.get("/brief/status")
def brief_status(request: Request):
    b = getattr(request.app.state, "brief", None)
    return b.status() if b is not None else {"enabled": False}
