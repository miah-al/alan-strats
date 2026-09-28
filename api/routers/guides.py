"""/api/guides — the guides library (platform articles, playbooks, the course, each strategy's guide)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from api.services import guides as G

router = APIRouter(tags=["guides"])


@router.get("/guides")
def guides():
    return G.list_guides()


@router.get("/guides/{slug}")
def guide(slug: str, request: Request):
    try:
        return G.get(slug, base=str(request.base_url).rstrip("/"))
    except G.UnknownGuide:
        raise HTTPException(404, f"unknown guide {slug!r}")


@router.get("/guides/{slug}/files/{path:path}")
def guide_file(slug: str, path: str):
    try:
        return FileResponse(G.file_path(slug, path))
    except G.UnknownGuide:
        raise HTTPException(404, f"no file {path!r} for guide {slug!r}")
