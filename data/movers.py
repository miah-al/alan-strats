"""
data/movers.py — the market-wide movers board from Polygon grouped daily aggregates.

The dedicated gainers/losers snapshot endpoint is not authorized on EOD/options plans, but
grouped daily is: this gives a genuine movers board (filtered to liquid names) for the most
recent completed session. Used by the service and, while it exists, the Dash Market page.
"""
from __future__ import annotations

import datetime as _dt


def fetch_grouped_movers(api_key: str, top_n: int = 12,
                         min_price: float = 5.0,
                         min_dollar_vol: float = 2e7) -> dict | None:
    """Top gainers/losers for the most recent completed session, computed from
    grouped daily aggregates.

    Change is measured vs the prior session's close when available, else the
    session's own open. Returns {"asof", "gainers", "losers", "all"} or None.
    """
    from data.polygon_client import PolygonClient
    c = PolygonClient(api_key=api_key)

    def _grouped(day: _dt.date) -> list[dict]:
        try:
            d = c._get(f"/v2/aggs/grouped/locale/us/market/stocks/{day}",
                       {"adjusted": "true"})
            return d.get("results", []) or []
        except Exception:
            return []

    # Walk back to the two most recent sessions that actually have data
    # (skips weekends, holidays, and today — usually not yet available intraday).
    sessions: list[tuple[_dt.date, list[dict]]] = []
    day = _dt.date.today()
    for _ in range(8):
        day -= _dt.timedelta(days=1)
        if day.weekday() >= 5:
            continue
        res = _grouped(day)
        if res:
            sessions.append((day, res))
        if len(sessions) == 2:
            break
    if not sessions:
        return None

    cur_day, cur = sessions[0]
    prev_close = {b.get("T"): b.get("c") for b in sessions[1][1]} if len(sessions) > 1 else {}

    rows = []
    for b in cur:
        t, cl, o, v = b.get("T"), b.get("c"), b.get("o"), b.get("v")
        if not t or not cl or cl < min_price:
            continue
        if cl * (v or 0) < min_dollar_vol:
            continue
        base = prev_close.get(t) or o
        if not base:
            continue
        rows.append({
            "ticker": t, "price": float(cl),
            "change_pct": round((cl - base) / base * 100, 2),
            "volume": int(v or 0),
        })
    if not rows:
        return None

    rows.sort(key=lambda r: r["change_pct"])
    return {
        "asof":    cur_day.isoformat(),
        "gainers": rows[-top_n:][::-1],
        "losers":  rows[:top_n],
        "all":     rows,
    }
