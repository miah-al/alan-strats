"""/api/limits — the limits the trader sets (api/services/limits.py): every desk's, armed strategy's and the system's,
with today's usage; one scope's values in force (what the desk reads before each order); set one, with its change
logged."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Request

router = APIRouter()


def _limits(request: Request):
    from api.services.limits import Limits, paper_usage
    st = request.app.state
    arms = getattr(st, "arms", None)

    def armed() -> list[str]:
        try:
            return sorted({a["strategy"] for a in (arms.arms() if arms else []) if (a.get("kind") or "runner") != "allocator"})
        except Exception:
            return []
    return Limits(getattr(st, "limits_store", None), strategies=armed,
                  usage=lambda: paper_usage(hub=getattr(st, "market", None)))


@router.get("/limits")
def limits_table(request: Request):
    return _limits(request).table()


@router.get("/limits/{scope}")
def limits_scope(scope: str, request: Request):
    lim = _limits(request)
    if not lim.catalogue(scope):
        raise HTTPException(404, f"no limits for {scope}")
    return {"scope": scope, "values": lim.values(scope)}


@router.put("/limits/{scope}/{name}")
def limits_set(scope: str, name: str, request: Request, body: Optional[dict] = Body(default=None)):
    from api.services.limits import LimitError
    b = body or {}
    if "value" not in b:
        raise HTTPException(422, "value: required")
    try:
        return _limits(request).set(scope, name, b["value"], by=b.get("by"), reason=b.get("reason"))
    except LimitError as exc:
        raise HTTPException(422, str(exc))
