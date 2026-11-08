"""/api/real — the owner's REAL tastytrade account, read-only, in /api/paper's shapes (the app's Paper | Real switch).

Only GET routes: this router cannot send anything to the broker (tests/test_real_account.py checks it). ``account``
picks one of the login's accounts by its last four digits; by default ``REAL_ACCOUNT`` or the login's only account.
"""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query

from api.services import real_account as R

router = APIRouter(tags=["real"])


def _guard(fn, *a, **k):
    try:
        return fn(*a, **k)
    except R.RealAccountUnavailable as exc:
        raise HTTPException(503, f"real account unavailable: {exc}")


def _iso(*vals) -> None:
    for v in vals:
        if v:
            try:
                date.fromisoformat(v[:10])
            except ValueError:
                raise HTTPException(422, f"{v!r} is not an ISO date (YYYY-MM-DD)")


@router.get("/real/status")
def real_status():
    return R.status()


@router.get("/real/accounts")
def real_accounts():
    return _guard(R.accounts)


@router.get("/real/summary")
def real_summary(account: Optional[str] = None):
    return _guard(R.summary, account)


@router.get("/real/positions")
def real_positions(status: Literal["open", "closed", "all"] = "open", account: Optional[str] = None):
    return _guard(R.positions, status, account)


@router.get("/real/positions/{trade_group_id}/legs")
def real_legs(trade_group_id: str, account: Optional[str] = None):
    try:
        return _guard(R.legs, trade_group_id, account)
    except R.UnknownTradeGroup:
        raise HTTPException(404, f"unknown real trade group {trade_group_id!r}")


@router.get("/real/transactions")
def real_transactions(limit: Optional[int] = Query(default=None, ge=1), account: Optional[str] = None):
    return _guard(R.transactions, limit, account)


@router.get("/real/equity")
def real_equity(from_: Optional[str] = Query(default=None, alias="from"), to: Optional[str] = None,
                account: Optional[str] = None):
    _iso(from_, to)
    return _guard(R.equity, from_, to, account)
