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


# ── Term structures (api/services/structure.py) ───────────────────────────────

@router.get("/market/yield-curve/history")
def market_yield_curve_history(days: int = Query(default=400, ge=30, le=3650)):
    from api.services import structure as S
    return S.curve_history(days)


@router.get("/market/yield-curve/surface")
def market_yield_curve_surface(days: int = Query(default=730, ge=30, le=3650),
                               step: Literal["1d", "1w", "1m"] = "1w"):
    from api.services import structure as S
    return S.curve_surface(days, step)


@router.get("/market/vix-term")
def market_vix_term():
    from api.services import structure as S
    return S.vix_term()


@router.get("/market/iv-term/{ticker}")
def market_iv_term(ticker: str, source: Literal["auto", "db", "polygon"] = "auto",
                   max_dte: int = Query(default=180, ge=7, le=730)):
    from api.services import structure as S
    return S.iv_term(ticker, source, max_dte)
