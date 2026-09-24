"""/api/data — what the database holds."""
from __future__ import annotations

from fastapi import APIRouter

from api.services.coverage import coverage

router = APIRouter(tags=["data"])


@router.get("/data/coverage")
def data_coverage():
    return coverage()
