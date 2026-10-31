"""/api/watchlists and /api/alerts."""
from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, Request

from api.services import alerts as A
from api.services import watchlists as W

router = APIRouter(tags=["watchlists", "alerts"])


# ── watchlists ────────────────────────────────────────────────────────────────

@router.get("/watchlists")
def watchlists():
    return W.list_all()


@router.get("/watchlists/{name}")
def watchlist(name: str):
    try:
        got = W.get(name)
    except W.WatchlistError as exc:
        raise HTTPException(422, str(exc))
    if got is None:
        raise HTTPException(404, f"unknown watchlist {name!r}")
    return got


@router.put("/watchlists/{name}")
def watchlist_put(name: str, body: dict = Body(...)):
    try:
        return W.put(name, body.get("symbols") if isinstance(body, dict) else None)
    except W.WatchlistError as exc:
        raise HTTPException(422, str(exc))


@router.delete("/watchlists/{name}")
def watchlist_delete(name: str):
    try:
        W.delete(name)
    except W.WatchlistError as exc:
        raise HTTPException(422, str(exc))
    except W.UnknownWatchlist:
        raise HTTPException(404, f"unknown watchlist {name!r}")
    return {"deleted": name}


# ── alerts ────────────────────────────────────────────────────────────────────

@router.get("/alerts")
def alerts(request: Request):
    return request.app.state.alerts.list()


@router.post("/alerts")
def alert_create(request: Request, body: dict = Body(...)):
    try:
        return request.app.state.alerts.create(body)
    except A.AlertError as exc:
        raise HTTPException(422, str(exc))


@router.delete("/alerts/{alert_id}")
def alert_delete(alert_id: int, request: Request):
    try:
        request.app.state.alerts.delete(alert_id)
    except A.UnknownAlert:
        raise HTTPException(404, f"unknown alert {alert_id}")
    return {"deleted": alert_id}
