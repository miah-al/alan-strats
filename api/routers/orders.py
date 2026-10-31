"""/api/orders — paper orders (preview, place, list, cancel) and closing a paper position."""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Body, HTTPException, Query, Request

from api.services import orders as O

router = APIRouter(tags=["orders"])


def _book(request: Request) -> O.OrderBook:
    return request.app.state.orders


def _errors(fn):
    try:
        return fn()
    except O.LiveNotArmed as exc:
        raise HTTPException(403, str(exc) or "live trading is not armed")
    except O.OrderError as exc:
        raise HTTPException(422, str(exc))
    except O.OrderConflict as exc:
        raise HTTPException(409, str(exc))


@router.post("/orders/preview")
def order_preview(request: Request, body: dict = Body(...)):
    return _errors(lambda: O.preview(request.app.state.market, body))


@router.post("/orders")
def order_place(request: Request, body: dict = Body(...)):
    return _errors(lambda: _book(request).place(body))


@router.get("/orders")
def order_list(request: Request, status: Literal["working", "filled", "cancelled", "rejected", "all"] = "all",
               limit: int = Query(default=500, ge=1, le=5000)):
    return _book(request).list(status, limit)


@router.delete("/orders/{order_id}")
def order_cancel(order_id: int, request: Request):
    try:
        return _errors(lambda: _book(request).cancel(order_id))
    except O.UnknownOrder:
        raise HTTPException(404, f"unknown order {order_id}")


@router.post("/paper/positions/{trade_group_id}/close")
def paper_close(trade_group_id: str, request: Request, body: Optional[dict] = Body(default=None)):
    try:
        return _errors(lambda: _book(request).close_position(trade_group_id, body or {}))
    except O.UnknownOrder:
        raise HTTPException(404, f"unknown or empty trade group {trade_group_id!r}")
