"""GET/DELETE /api/jobs — scan and backtest jobs."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(tags=["jobs"])


@router.get("/jobs")
def list_jobs(request: Request):
    return [j.to_dict(include_result=False) for j in request.app.state.jobs.list()]


@router.get("/jobs/{job_id}")
def get_job(job_id: str, request: Request):
    job = request.app.state.jobs.get(job_id)
    if job is None:
        raise HTTPException(404, f"unknown job {job_id!r}")
    return job.to_dict(include_result=True)


@router.delete("/jobs/{job_id}")
def cancel_job(job_id: str, request: Request):
    job = request.app.state.jobs.cancel(job_id)
    if job is None:
        raise HTTPException(404, f"unknown job {job_id!r}")
    return job.to_dict(include_result=False)
