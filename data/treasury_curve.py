"""
data/treasury_curve.py — the US Treasury yield curve from FRED's public CSV series.

One CSV per constant-maturity series (DGS3MO … DGS30), merged on date, plus the 2s10s and
3m10y spreads. Cached for the life of the process (the Market page's behaviour): a daily
series does not change within a session. Used by the service as the fallback when
``mkt.MacroBar`` is empty, and by the Dash Market page while it exists.
"""
from __future__ import annotations

import pandas as pd

TREASURY_FRED_SERIES = {
    "rate_3m":  "DGS3MO", "rate_6m":  "DGS6MO",
    "rate_1y":  "DGS1",   "rate_2y":  "DGS2",
    "rate_5y":  "DGS5",   "rate_10y": "DGS10",
    "rate_30y": "DGS30",
}
MATURITIES = [
    ("3M",  0.25, "rate_3m"),  ("6M", 0.5,  "rate_6m"),
    ("1Y",  1.0,  "rate_1y"),  ("2Y", 2.0,  "rate_2y"),
    ("5Y",  5.0,  "rate_5y"),  ("10Y", 10.0, "rate_10y"),
    ("30Y", 30.0, "rate_30y"),
]
CACHE: dict = {}


def fred_csv(series_id: str, timeout: float = 10.0) -> str:
    """One FRED series as CSV text (raises on an HTTP error)."""
    import requests
    r = requests.get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}", timeout=timeout)
    r.raise_for_status()
    return r.text


def load_treasury_curve() -> pd.DataFrame | None:
    """DataFrame[date, rate_3m … rate_30y (percent), spread_2s10s, spread_3m10y] or None."""
    if "df" in CACHE:
        return CACHE["df"]
    from io import StringIO
    from concurrent.futures import ThreadPoolExecutor

    def _fetch(item):
        col, sid = item
        try:
            df = pd.read_csv(StringIO(fred_csv(sid)))
            df.columns = ["date", col]
            df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
            df[col] = pd.to_numeric(df[col], errors="coerce")
            return col, df.dropna(subset=["date"]).set_index("date")
        except Exception:
            return col, None

    series = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        for col, df in pool.map(_fetch, TREASURY_FRED_SERIES.items()):
            if df is not None:
                series[col] = df

    if not series:
        return None
    merged = None
    for col, df in series.items():
        merged = df if merged is None else merged.join(df, how="outer")
    merged = merged.reset_index().sort_values("date")
    merged["spread_2s10s"] = merged.get("rate_10y", 0) - merged.get("rate_2y", 0)
    merged["spread_3m10y"] = merged.get("rate_10y", 0) - merged.get("rate_3m", 0)
    CACHE["df"] = merged.reset_index(drop=True)
    return CACHE["df"]
