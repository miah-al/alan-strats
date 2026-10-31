"""/api/events/* — the event desk (api/services/event_desk.py): the desk view, the manual event log, the war-regime
switch, the post-close signal log with the trader's tags, the allocators' decisions and the crypto-flush signals.
(``WS /api/events`` — the service's event stream — is api/routers/events.py.)"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Query, Request, Response

from api.services.event_desk import EventError

router = APIRouter(tags=["event desk"])


def _desk(request: Request):
    d = getattr(request.app.state, "event_desk", None)
    if d is None:
        raise HTTPException(503, "the event desk is not available in this service")
    return d


@router.get("/events/desk")
def events_desk(request: Request):
    return _desk(request).desk()


@router.get("/events/log")
def events_log(request: Request, days: int = Query(default=14, ge=1, le=3660)):
    return _desk(request).events(days)


@router.post("/events/log")
def events_log_add(request: Request, body: Optional[dict] = Body(default=None)):
    try:
        return _desk(request).log_event(body or {})
    except EventError as exc:
        raise HTTPException(422, str(exc))


@router.delete("/events/log/{event_id}", status_code=204)
def events_log_delete(event_id: int, request: Request):
    try:
        ok = _desk(request).delete_event(event_id)
    except EventError as exc:
        raise HTTPException(422, str(exc))
    if not ok:
        raise HTTPException(404, f"no event {event_id}")
    return Response(status_code=204)


@router.get("/events/regime")
def events_regime(request: Request):
    return _desk(request).regime()


@router.put("/events/regime")
def events_regime_set(request: Request, body: Optional[dict] = Body(default=None)):
    try:
        return _desk(request).set_regime(body or {})
    except EventError as exc:
        raise HTTPException(422, str(exc))


@router.get("/events/signals")
def events_signals(request: Request, days: int = Query(default=90, ge=1, le=3660)):
    return _desk(request).signal_log(days)


@router.put("/events/signals/{signal_id}/tag")
def events_signal_tag(signal_id: int, request: Request, body: Optional[dict] = Body(default=None)):
    try:
        row = _desk(request).tag_signal(signal_id, body or {})
    except EventError as exc:
        raise HTTPException(422, str(exc))
    if row is None:
        raise HTTPException(404, f"no signal {signal_id}")
    return row


@router.get("/events/decisions")
def events_decisions(request: Request, days: int = Query(default=30, ge=1, le=3660), playbook: Optional[str] = None):
    from api.services.event_desk import LEDGER
    if playbook is not None and playbook not in LEDGER:
        raise HTTPException(422, f"playbook must be one of {', '.join(LEDGER)}")
    d = _desk(request)
    return {"days": days, "playbook": playbook, "decisions": d.decisions(days, playbook)}


@router.get("/events/crypto-flush")
def events_crypto_flush(request: Request, days: int = Query(default=30, ge=1, le=3660)):
    p = getattr(request.app.state, "crypto_flush", None)
    if p is None:
        raise HTTPException(503, "the crypto_flush poller is not available in this service")
    return {"days": days, "status": p.status(), "signals": p.signals(days)}
