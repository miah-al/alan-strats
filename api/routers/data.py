"""/api/data — what the database holds, and syncing more of it."""
from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, Request

from api.services.coverage import coverage

router = APIRouter(tags=["data"])


@router.get("/data/coverage")
def data_coverage():
    return coverage()


@router.get("/data/sync/types")
def data_sync_types():
    from db.sync_jobs import sync_types
    return sync_types()


@router.post("/data/sync", status_code=202)
def data_sync(request: Request, body: dict = Body(...)):
    from api.services import sync as SY
    try:
        req = SY.validate(body)
    except SY.SyncRequestError as exc:
        raise HTTPException(422, str(exc))
    where = ", ".join(req["tickers"]) if req["tickers"] else "all"
    title = f"Sync {req['data_type']} {where}" + (f" from {req['from']}" if req["from"] else "")
    job = request.app.state.jobs.submit(
        "sync", title[:200], lambda ctx: SY.sync_job(ctx, req), slug=None,
        params={"data_type": req["data_type"], "tickers": req["tickers"],
                "from": req["from"].isoformat() if req["from"] else None,
                "to": req["to"].isoformat() if req["to"] else None})
    return request.app.state.json_response(status_code=202, content={"job_id": job.id, "job": job.to_dict()})
