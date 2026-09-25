"""/api/strategies — the plugin registry, screener scans, backtests and live signals."""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from api.services import strategies as S

router = APIRouter(tags=["strategies"])


def _known(slug: str) -> dict:
    try:
        return S.require(slug)
    except S.UnknownStrategy:
        raise HTTPException(404, f"unknown strategy {slug!r}")


def _accepted(request: Request, job) -> object:
    return request.app.state.json_response(status_code=202, content={"job_id": job.id, "job": job.to_dict()})


@router.get("/strategies")
def list_strategies(include_hidden: bool = False):
    return S.list_strategies(include_hidden=include_hidden)


@router.get("/strategies/{slug}")
def strategy_detail(slug: str):
    _known(slug)
    return S.strategy_detail(slug)


@router.get("/strategies/{slug}/guide")
def strategy_guide(slug: str):
    _known(slug)
    return S.guide(slug)


# ── Scan ──────────────────────────────────────────────────────────────────────

class ScanRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    universe: Optional[str] = "ETF Core"
    tickers: Optional[list[str]] = None
    params: dict = Field(default_factory=dict)


@router.post("/strategies/{slug}/scan", status_code=202)
def start_scan(slug: str, body: ScanRequest, request: Request):
    from engine.env import get_polygon_api_key
    from engine.strategy_scan import UNIVERSE_TICKERS, scan_tickers

    _known(slug)
    info = S.strategy_info(slug)
    if not info["has_screener"]:
        raise HTTPException(422, f"{slug} has no screener")
    api_key = get_polygon_api_key()
    if not api_key:
        raise HTTPException(422, "No Polygon API key found. Set POLYGON_API_KEY in .env.")
    universe = body.universe or "ETF Core"
    custom = ",".join(t for t in (body.tickers or []) if t and t.strip())
    if not info["locked_tickers"] and not custom and universe not in UNIVERSE_TICKERS:
        raise HTTPException(422, f"unknown universe {universe!r}; one of {sorted(UNIVERSE_TICKERS)} "
                                 f"or 'Custom' with tickers")
    tickers = scan_tickers(slug, universe, custom or None)
    if not tickers:
        raise HTTPException(422, "No tickers in universe.")
    spec_ids = {p.get("id") for p in S.R().get_ui(slug).screener_params or []}
    unknown = [k for k in body.params if k not in spec_ids and k not in (S.R().get_ui(slug).default_params or {})]
    if unknown:
        raise HTTPException(422, f"unknown screener parameter(s) {unknown}; valid: {sorted(p for p in spec_ids if p)}")
    params = {k: v for k, v in body.params.items() if v is not None}
    where = info["locked_label"] or ("Custom" if custom else universe)
    job = request.app.state.jobs.submit(
        "scan", f"Scan {slug} {where} ({len(tickers)} tickers)",
        lambda ctx: S.scan_job(ctx, slug, tickers, params, api_key, "Custom" if custom else universe),
        slug=slug, params={"universe": universe, "tickers": tickers, "params": params})
    return _accepted(request, job)


# ── Backtest ──────────────────────────────────────────────────────────────────

class BacktestRequest(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)
    ticker: Optional[str] = None
    from_: Optional[str] = Field(default=None, alias="from")
    to: Optional[str] = None
    capital: Optional[float] = None
    params: dict = Field(default_factory=dict)


@router.post("/strategies/{slug}/backtest", status_code=202)
def start_backtest(slug: str, body: BacktestRequest, request: Request):
    _known(slug)
    info = S.strategy_info(slug)
    if not info["has_backtest"]:
        raise HTTPException(422, f"Strategy {slug!r} has no implementation registered.")
    ticker = (body.ticker or info["default_ticker"] or "SPY").upper().strip()
    from_date = body.from_ or info["default_from"]
    to_date = body.to or date.today().isoformat()
    try:
        fd, td = date.fromisoformat(from_date[:10]), date.fromisoformat(to_date[:10])
    except ValueError:
        raise HTTPException(422, "from / to must be ISO dates (YYYY-MM-DD)")
    if fd >= td:
        raise HTTPException(422, "from must be before to")
    capital = float(body.capital if body.capital is not None else info["default_capital"])
    if capital <= 0:
        raise HTTPException(422, "capital must be positive")
    try:
        params = S.validate_backtest_params(slug, body.params)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    # The commonest missing-data case answers now rather than as a failed job; a
    # strategy loader that finds nothing still fails the job with the loader's message.
    from api.services.db import require_db
    from db.client import get_price_coverage
    cov = get_price_coverage(require_db(), ticker)
    if cov is None:
        raise HTTPException(422, f"No price bars stored for {ticker} (mkt.PriceBar). Sync it first.")
    if td < cov[0] or fd > cov[1]:
        raise HTTPException(422, f"No price bars for {ticker} between {fd} and {td}; "
                                 f"stored {cov[0]} → {cov[1]}.")
    job = request.app.state.jobs.submit(
        "backtest", f"Backtest {slug} {ticker} {fd}→{td}",
        lambda ctx: S.backtest_job(ctx, slug, ticker, fd.isoformat(), td.isoformat(), capital, params),
        slug=slug, params={"ticker": ticker, "from": fd.isoformat(), "to": td.isoformat(),
                           "capital": capital, "params": params})
    return _accepted(request, job)


# ── Signal ────────────────────────────────────────────────────────────────────

@router.get("/strategies/{slug}/signal")
def strategy_signal(slug: str, ticker: Optional[str] = Query(default=None)):
    _known(slug)
    try:
        return S.signal(slug, ticker)
    except LookupError as exc:
        raise HTTPException(422, str(exc.args[0]) if exc.args else "no data")
