"""/api/market — bars, quotes, movers, yield curve, IV metrics, GEX."""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query

from api.services import market as M

router = APIRouter(tags=["market"])


@router.get("/market/tickers")
def market_tickers():
    return M.tickers()


@router.get("/market/bars/{ticker}")
def market_bars(ticker: str, from_: Optional[str] = Query(default=None, alias="from"),
                to: Optional[str] = None, interval: Literal["1d", "1m"] = "1d"):
    try:
        return M.bars(ticker, from_, to, interval)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.get("/market/quote/{ticker}")
def market_quote(ticker: str):
    return M.quote(ticker)


@router.get("/market/movers")
def market_movers(top: int = Query(default=12, ge=1, le=50)):
    return M.movers(top)


@router.get("/market/yield-curve")
def market_yield_curve():
    return M.yield_curve()


@router.get("/market/iv/{ticker}")
def market_iv(ticker: str):
    return M.iv(ticker)


@router.get("/market/gex/{ticker}")
def market_gex(ticker: str, source: Literal["auto", "db", "polygon"] = "auto"):
    return M.gex(ticker, source)
