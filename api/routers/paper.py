"""/api/paper — the paper account (read-only)."""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query

from api.services import paper as P

router = APIRouter(tags=["paper"])


@router.get("/paper/summary")
def paper_summary():
    return P.summary()


@router.get("/paper/positions")
def paper_positions(status: Literal["open", "closed", "all"] = "open"):
    return P.positions(status)


@router.get("/paper/positions/{trade_group_id}/legs")
def paper_legs(trade_group_id: str):
    try:
        return P.legs(trade_group_id)
    except P.UnknownTradeGroup:
        raise HTTPException(404, f"unknown trade group {trade_group_id!r}")


@router.get("/paper/transactions")
def paper_transactions(limit: Optional[int] = Query(default=None, ge=1)):
    return P.transactions(limit)


@router.get("/paper/equity")
def paper_equity(from_: Optional[str] = Query(default=None, alias="from"), to: Optional[str] = None):
    for v in (from_, to):
        if v:
            try:
                date.fromisoformat(v[:10])
            except ValueError:
                raise HTTPException(422, f"{v!r} is not an ISO date (YYYY-MM-DD)")
    return P.equity(from_, to)


@router.get("/paper/runner")
def paper_runner():
    return P.runner()
