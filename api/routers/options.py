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


@router.get("/options/{underlying}/surface")
def option_surface(underlying: str, request: Request, max_dte: int = Query(default=180, ge=1, le=1100),
                   lo: float = Query(default=0.80), hi: float = Query(default=1.20), step: float = Query(default=0.01)):
    from api.marketdata import surface as SF
    try:
        return SF.surface(request.app.state.market, underlying, max_dte, lo, hi, step)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except SF.NoSurface as exc:
        raise HTTPException(422, str(exc))
