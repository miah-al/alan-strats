"""
api/services/sync.py — data sync as service jobs (``db/sync_jobs.py`` behind ``/api/data/sync``).

One job per request: each ticker (or the one global dataset) in turn, progress on ``/api/events``,
cancellable between (and, through the progress callback, within) syncs. Every upstream call the
syncs make passes the market-data hub's request gate — Polygon, FRED, CBOE, Alpha Vantage and
yfinance budgets and backoff — and the job thread may wait up to five minutes for a request slot
instead of the request path's 30 s. Writes go through the DB guard's allow-list (the market-data
tables db/sync.py fills).
"""
from __future__ import annotations

import datetime as _dt
from typing import Optional

from api.jobs import JobContext, JobError
from api.marketdata import symbols as SYM

MAX_TICKERS = 50
JOB_PATIENCE_S = 300.0


class SyncRequestError(ValueError):
    pass


def validate(body: dict) -> dict:
    from db.sync_jobs import SYNC_TYPES
    if not isinstance(body, dict):
        raise SyncRequestError("a sync request is a JSON object")
    dt = str(body.get("data_type") or "").strip()
    if dt not in SYNC_TYPES:
        raise SyncRequestError(f"data_type must be one of {sorted(SYNC_TYPES)}")
    label, needs_ticker, source = SYNC_TYPES[dt]
    tickers = body.get("tickers") or []
    if isinstance(tickers, str):
        tickers = [t for t in tickers.split(",") if t.strip()]
    if not isinstance(tickers, list):
        raise SyncRequestError("tickers: a list")
    clean = []
    for t in tickers:
        try:
            c = SYM.normalize(str(t))
        except ValueError:
            raise SyncRequestError(f"tickers: {t!r} is not a symbol")
        if SYM.is_option(c):
            raise SyncRequestError(f"tickers: {t!r} is an option; sync its underlying")
        if c not in clean:
            clean.append(c)
    if needs_ticker and not clean:
        raise SyncRequestError(f"{dt} needs at least one ticker")
    if not needs_ticker:
        clean = []
    if len(clean) > MAX_TICKERS:
        raise SyncRequestError(f"at most {MAX_TICKERS} tickers per job")
    fd = td = None
    try:
        if body.get("from"):
            fd = _dt.date.fromisoformat(str(body["from"])[:10])
        if body.get("to"):
            td = _dt.date.fromisoformat(str(body["to"])[:10])
    except ValueError:
        raise SyncRequestError("from / to must be ISO dates (YYYY-MM-DD)")
    if fd and td and fd > td:
        raise SyncRequestError("from must not be after to")
    if td and td > _dt.date.today() + _dt.timedelta(days=366):
        raise SyncRequestError("to is more than a year ahead")
    return {"data_type": dt, "label": label, "source": source, "tickers": clean, "from": fd, "to": td}


def sync_job(ctx: JobContext, req: dict) -> dict:
    from api.marketdata.limits import patience
    from db.sync_jobs import describe, run_sync
    targets = req["tickers"] or [None]
    results = []
    n = len(targets)
    for i, t in enumerate(targets):
        ctx.progress(i / n, f"{req['data_type']} {t or ''}".strip() + f" ({i + 1}/{n})")
        base, span = i / n, 1.0 / n

        def progress(msg: str, frac: Optional[float], _t=t, _base=base, _span=span):
            f = _base + _span * max(0.0, min(1.0, frac)) if frac is not None else None
            ctx.progress(f, f"{_t + ': ' if _t else ''}{msg}"[:200])

        with patience(JOB_PATIENCE_S):
            r = run_sync(req["data_type"], t, req["from"], req["to"], progress=progress)
        results.append({"ticker": t, "status": r["status"], "rows": r["rows"], "detail": r["detail"],
                        "message": describe(r)})
    ok = [r for r in results if r["status"] in ("ok", "up_to_date")]
    if not ok and all(r["status"] == "error" for r in results):
        raise JobError("; ".join(f"{r['ticker'] or req['data_type']}: {r['detail']}" for r in results)[:1000])
    return {"data_type": req["data_type"], "label": req["label"], "from": req["from"], "to": req["to"],
            "results": results, "rows": sum(r["rows"] for r in results),
            "ok": len(ok), "failed": sum(1 for r in results if r["status"] == "error")}
