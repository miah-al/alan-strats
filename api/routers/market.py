"""/api/market — bars, quotes, movers, yield curve, IV metrics, GEX, term structures, providers.

Every upstream call these make passes the market-data hub's request gate (limits, budgets,
backoff); the answers are cached per the contract's minimums (quotes >= 1 s, snapshots and chains
>= 15 s, daily data >= 5 min) so a busy client does not turn into upstream traffic.
"""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query, Request

from api.marketdata.cache import DAILY_TTL, cached
from api.services import market as M

router = APIRouter(tags=["market"])

_NO_DATA = (M.MissingData,)
GEX_TTL = 60.0
IV_TERM_TTL = 60.0
BARS_TTL = 30.0


@router.get("/market/tickers")
def market_tickers():
    return M.tickers()


@router.get("/market/bars/{ticker}")
def market_bars(ticker: str, from_: Optional[str] = Query(default=None, alias="from"),
                to: Optional[str] = None, interval: Literal["1d", "1m"] = "1d"):
    try:
        return cached(("bars", ticker.upper(), from_, to, interval), BARS_TTL,
                      lambda: M.bars(ticker, from_, to, interval), cache_errors=_NO_DATA)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.get("/market/quote/{ticker}")
def market_quote(ticker: str, request: Request):
    return M.quote(ticker, hub=getattr(request.app.state, "market", None))


@router.get("/market/quotes")
def market_quotes(request: Request, symbols: str = Query(..., description="comma-separated, e.g. SPY,QQQ,^VIX")):
    syms = [s.strip() for s in symbols.split(",") if s.strip()]
    if not syms:
        raise HTTPException(422, "symbols: give at least one symbol")
    if len(syms) > 200:
        raise HTTPException(422, "symbols: at most 200 per request")
    return {"quotes": request.app.state.market.snapshot(syms)}


@router.get("/market/providers")
def market_providers(request: Request):
    return request.app.state.market.providers_status()


@router.get("/market/movers")
def market_movers(top: int = Query(default=12, ge=1, le=50)):
    return cached(("movers", top), DAILY_TTL, lambda: M.movers(top), cache_errors=_NO_DATA)


@router.get("/market/yield-curve")
def market_yield_curve():
    return cached(("yield-curve",), DAILY_TTL, M.yield_curve, cache_errors=_NO_DATA)


@router.get("/market/iv/{ticker}")
def market_iv(ticker: str):
    return cached(("iv", ticker.upper()), DAILY_TTL, lambda: M.iv(ticker), cache_errors=_NO_DATA)


@router.get("/market/gex/{ticker}")
def market_gex(ticker: str, source: Literal["auto", "db", "polygon"] = "auto"):
    return cached(("gex", ticker.upper(), source), GEX_TTL, lambda: M.gex(ticker, source), cache_errors=_NO_DATA)


# ── Term structures (api/services/structure.py) ───────────────────────────────

@router.get("/market/yield-curve/history")
def market_yield_curve_history(days: int = Query(default=400, ge=30, le=3650)):
    from api.services import structure as S
    return cached(("yc-history", days), DAILY_TTL, lambda: S.curve_history(days), cache_errors=_NO_DATA)


@router.get("/market/yield-curve/surface")
def market_yield_curve_surface(days: int = Query(default=730, ge=30, le=3650),
                               step: Literal["1d", "1w", "1m"] = "1w"):
    from api.services import structure as S
    return cached(("yc-surface", days, step), DAILY_TTL, lambda: S.curve_surface(days, step), cache_errors=_NO_DATA)


@router.get("/market/vix-term")
def market_vix_term():
    from api.services import structure as S
    return cached(("vix-term",), DAILY_TTL, S.vix_term, cache_errors=_NO_DATA)


@router.get("/market/iv-term/{ticker}")
def market_iv_term(ticker: str, source: Literal["auto", "db", "polygon"] = "auto",
                   max_dte: int = Query(default=180, ge=7, le=730)):
    from api.services import structure as S
    return cached(("iv-term", ticker.upper(), source, max_dte), IV_TERM_TTL,
                  lambda: S.iv_term(ticker, source, max_dte), cache_errors=_NO_DATA)
