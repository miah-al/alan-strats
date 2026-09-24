"""/api/options — expirations and the option chain (greeks / IV) from the market-data hub."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from api.marketdata import options as O

router = APIRouter(tags=["options"])


@router.get("/options/{underlying}/expirations")
def option_expirations(underlying: str, request: Request):
    try:
        return O.expirations(request.app.state.market, underlying)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.get("/options/{underlying}/chain")
def option_chain(underlying: str, request: Request, expiry: str = Query(...),
                 strikes: int = Query(default=30, ge=1, le=200)):
    try:
        return O.chain(request.app.state.market, underlying, expiry, strikes)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
