"""/api/risk — the paper book's greeks in dollars and its stress grid (api/services/risk_stress.py). Read only."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from api.services import risk_stress as RS

router = APIRouter(tags=["risk"])


@router.get("/risk")
def risk(request: Request,
         moves: Optional[str] = Query(default=None, description="underlying moves in %, comma-separated (default -3,-2,-1,-0.5,0,0.5,1,2,3)"),
         vols: Optional[str] = Query(default=None, description="IV shocks in vol points, comma-separated (default -5,0,5,10)"),
         horizon: str = Query(default="now", description="now | +1h (or 1h) | settlement"),
         strategy: Optional[str] = Query(default=None, description="only this strategy's positions (slug)"),
         trade_group_id: Optional[str] = Query(default=None, description="only this position")):
    """Every open paper position, each strategy and the portfolio: greeks now in dollars, and per move × vol-shock
    cell the P&L change (full Black-Scholes revaluation) with the greeks re-computed there; the worst cell of each.
    Inputs (positions, marks, IVs) are re-read at most every 20 s and cost no broker call beyond the positions table's."""
    try:
        return RS.report(getattr(request.app.state, "market", None), moves=moves, vols=vols, horizon=horizon,
                         strategy=strategy, trade_group_id=trade_group_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
