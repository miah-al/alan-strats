"""
app/pages/market/data.py - pure data/logic for the Market Data page.

No @callback functions live here. Polygon.io helpers, the FRED Treasury yield
curve loader, the yfinance futures fetcher, screener batch/IV/HV/RSI helpers,
screener chart builders, futures-table data, and the render helpers
(_render_intraday, _render_yield_inner, _build_chain_table) the callbacks compose.
Split verbatim from the original market.py.
"""
from __future__ import annotations

import math
import datetime as _dt
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import html, dcc, no_update
import dash_bootstrap_components as dbc

from app import theme as T, get_polygon_api_key
from app.ui import tokens as D, components as C
from engine.screener import UNIVERSES

logger = logging.getLogger(__name__)


_TREASURY_FRED_SERIES = {
    "rate_3m":  "DGS3MO", "rate_6m":  "DGS6MO",
    "rate_1y":  "DGS1",   "rate_2y":  "DGS2",
    "rate_5y":  "DGS5",   "rate_10y": "DGS10",
    "rate_30y": "DGS30",
}
_MATURITIES = [
    ("3M",  0.25, "rate_3m"),  ("6M", 0.5,  "rate_6m"),
    ("1Y",  1.0,  "rate_1y"),  ("2Y", 2.0,  "rate_2y"),
    ("5Y",  5.0,  "rate_5y"),  ("10Y",10.0, "rate_10y"),
    ("30Y", 30.0, "rate_30y"),
]
_YIELD_CACHE: dict = {}


def _load_yield_curve() -> pd.DataFrame | None:
    if "df" in _YIELD_CACHE:
        return _YIELD_CACHE["df"]
    import requests
    from io import StringIO
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _fetch(item):
        col, sid = item
        try:
            r = requests.get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}", timeout=10)
            r.raise_for_status()
            df = pd.read_csv(StringIO(r.text))
            df.columns = ["date", col]
            df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
            df[col]    = pd.to_numeric(df[col], errors="coerce")
            return col, df.dropna(subset=["date"]).set_index("date")
        except Exception:
            return col, None

    series = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        for col, df in pool.map(_fetch, _TREASURY_FRED_SERIES.items()):
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
    _YIELD_CACHE["df"] = merged.reset_index(drop=True)
    return _YIELD_CACHE["df"]


# ── Polygon helpers ────────────────────────────────────────────────────────────

def _polygon_client(api_key: str):
    from data.polygon_client import PolygonClient
    return PolygonClient(api_key=api_key)


def _fetch_bars(ticker: str, api_key: str, n_days: int = 504) -> pd.DataFrame:
    # Stock OHLCV via yfinance (free, includes today's bar). api_key kept for
    # signature compatibility; not used for stock data anymore.
    from data.stock_data import yf_daily_bars
    return yf_daily_bars(ticker, n_days)


# Session-scoped record of which real-time endpoints this API key's plan allows.
# Probed lazily on first use; once a 403 is seen we stop hammering the endpoint
# and fall straight to the authorized daily-aggregate paths. None = not yet probed.
_PLAN_ALLOWS: dict[str, bool | None] = {
    "stock_snapshot": None,   # /v2/snapshot/locale/us/markets/stocks/...
    "intraday":       None,   # /v2/aggs/.../range/1/minute/...
}


def _is_not_authorized(exc: Exception) -> bool:
    """True if a Polygon request failed specifically because the plan forbids it."""
    resp = getattr(exc, "response", None)
    return resp is not None and resp.status_code == 403


def _fetch_intraday(ticker: str, api_key: str) -> pd.DataFrame:
    """Today's 1-minute bars via yfinance (df with 'datetime' column).
    api_key kept for signature compatibility; not used for stock data."""
    from data.stock_data import yf_intraday
    return yf_intraday(ticker)


def _fetch_quote(ticker: str, api_key: str) -> dict | None:
    """Normalized stock quote via yfinance (free, intraday-aware, ≈15-min delay).
    api_key kept for signature compatibility; not used for stock data."""
    from data.stock_data import yf_quote
    return yf_quote(ticker)


def _fetch_grouped_movers(api_key: str, top_n: int = 12,
                          min_price: float = 5.0,
                          min_dollar_vol: float = 2e7) -> dict | None:
    """Top gainers/losers for the most recent completed session, computed from
    grouped daily aggregates. The dedicated gainers/losers snapshot endpoint is
    not authorized on EOD/options plans, but grouped daily is — this gives a
    genuine market-wide movers board (filtered to liquid names).

    Change is measured vs the prior session's close when available, else the
    session's own open. Returns {"asof", "gainers", "losers", "all"} or None.
    """
    import datetime as _dt
    c = _polygon_client(api_key)

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


# ── UI helpers ─────────────────────────────────────────────────────────────────

def _hint(text: str) -> html.P:
    # Delegates to the shared design-system hint (same italic-muted treatment).
    return C.hint(text)


def _section(title: str, content) -> html.Div:
    # Thin wrapper over the shared C.section so every Market card gets the same
    # uppercase header, radius and spacing as the rest of the app. Signature is
    # unchanged so callbacks.py keeps working.
    return C.section(title, content)


def _pill(label: str, value: str, color: str = T.TEXT_PRIMARY) -> html.Div:
    # KPI tile matching C.metric_card. `color` is preserved as a free-form value
    # colour so existing callers can pass any hex (success/danger/etc.).
    return html.Div([
        html.Div(label, style={
            "color": D.COLOR.text_muted, "fontSize": D.TEXT_XS,
            "fontWeight": D.WEIGHT_MED, "textTransform": "uppercase",
            "letterSpacing": "0.05em", "marginBottom": D.SPACE_1,
        }),
        html.Div(value, style={
            "color": color, "fontSize": D.TEXT_XL, "fontWeight": D.WEIGHT_BOLD,
            "lineHeight": "1.1",
        }),
    ], className="ui-card", style={
        **D.CARD, "flex": "1", "minWidth": "90px",
        "padding": f"{D.SPACE_2} {D.SPACE_3}",
    })


# Canonical dark Plotly base for this page. Kept to the same keys the original
# `_DARK` exposed (template / bg / font) so call sites that also pass height,
# margin, legend, xaxis, yaxis as kwargs don't collide with **_DARK. Sourced
# from the design-system layout so colours/fonts stay app-consistent.
_PLOTLY_BASE = D.plotly_layout()
_DARK = dict(
    template=_PLOTLY_BASE["template"],
    paper_bgcolor=_PLOTLY_BASE["paper_bgcolor"],
    plot_bgcolor=_PLOTLY_BASE["plot_bgcolor"],
    font=_PLOTLY_BASE["font"],
)

# Graph config WITH the Plotly toolbar (zoom / pan / autoscale / PNG export),
# minus the rarely-used select/lasso buttons and the Plotly logo. Used for the
# analytical Market charts so they have interactive controls.
_GRAPH_CFG = {
    "displayModeBar": True,
    "displaylogo": False,
    "responsive": True,
    "modeBarButtonsToRemove": ["select2d", "lasso2d"],
    "toImageButtonOptions": {"format": "png", "scale": 2},
}


# ── Screener: universe + sector map ───────────────────────────────────────────

_SCR_UNIVERSE_OPTIONS = [{"label": k, "value": k} for k in UNIVERSES]
_SCR_DEFAULT_UNIVERSE = "ETF Core"  # default if key exists in UNIVERSES else first
if _SCR_DEFAULT_UNIVERSE not in UNIVERSES:
    _SCR_DEFAULT_UNIVERSE = list(UNIVERSES.keys())[0]

_SECTOR = {
    "SPY": "Broad Market", "QQQ": "Technology", "IWM": "Small Cap",
    "GLD": "Commodities", "TLT": "Fixed Income", "EEM": "Emerging Markets",
    "XLF": "Financials", "XLE": "Energy", "XLK": "Technology", "XLV": "Healthcare",
    "DIA": "Broad Market", "MDY": "Mid Cap", "VTI": "Broad Market",
    "VEA": "International Dev", "VWO": "Emerging Markets",
    "AAPL": "Technology", "MSFT": "Technology", "NVDA": "Technology",
    "AMZN": "Consumer Discretionary", "GOOGL": "Communication Services",
    "META": "Communication Services", "TSLA": "Consumer Discretionary",
    "AVGO": "Technology", "JPM": "Financials",
    "MSTR": "Technology", "COIN": "Financials", "PLTR": "Technology",
    "ARKK": "Innovation", "SOXL": "Semiconductors (3x)", "TQQQ": "Technology (3x)",
}

_SCR_PLOT_BG  = D.COLOR.card
_SCR_PAPER_BG = D.COLOR.card
_SCR_GRID     = D.COLOR.border
_SCR_FONT     = dict(family=D.FONT_SANS, color=D.COLOR.text_sec, size=11)
_SCR_CFG      = D.PLOTLY_CONFIG


def _fmt_vol(n: float) -> str:
    if n >= 1_000_000_000: return f"{n/1_000_000_000:.1f}B"
    if n >= 1_000_000:     return f"{n/1_000_000:.1f}M"
    if n >= 1_000:         return f"{n/1_000:.0f}K"
    return str(int(n))


def _scr_empty_fig(msg: str = "") -> dict:
    fig = go.Figure()
    if msg:
        fig.add_annotation(text=msg, xref="paper", yref="paper",
                           x=0.5, y=0.5, showarrow=False,
                           font=dict(color=D.COLOR.text_muted, size=13))
    fig.update_layout(paper_bgcolor=_SCR_PAPER_BG, plot_bgcolor=_SCR_PLOT_BG,
                      font=_SCR_FONT, height=300, margin=dict(l=10, r=10, t=10, b=10),
                      xaxis=dict(visible=False), yaxis=dict(visible=False))
    return fig


def _scr_batch_snapshot(tickers: list[str], client) -> dict[str, dict]:
    joined = ",".join(tickers)
    try:
        data = client._get("/v2/snapshot/locale/us/markets/stocks/tickers", {"tickers": joined})
    except Exception as e:
        logger.warning("Batch snapshot failed: %s", e)
        return {}
    out: dict[str, dict] = {}
    for item in data.get("tickers", []):
        tkr  = item.get("ticker", "")
        day  = item.get("day", {})
        prev = item.get("prevDay", {})
        close  = float(day.get("c") or 0) or float(prev.get("c") or 0)
        volume = float(day.get("v") or 0) or float(prev.get("v") or 0)
        chg    = float(item.get("todaysChangePerc") or 0)
        if chg == 0:
            prev_c = float(prev.get("c") or 0)
            day_c  = float(day.get("c") or 0)
            if prev_c > 0 and day_c > 0:
                chg = round((day_c - prev_c) / prev_c * 100, 2)
        out[tkr] = {
            "close":  close,
            "volume": volume,
            "change_pct": chg,
        }
    return out


def _scr_fetch_bars(ticker: str, client, days: int = 60) -> pd.DataFrame:
    to_date  = _dt.date.today()
    frm_date = to_date - _dt.timedelta(days=int(days * 1.6))
    path = f"/v2/aggs/ticker/{ticker}/range/1/day/{frm_date}/{to_date}"
    params = {"adjusted": "true", "sort": "asc", "limit": 200}
    results, url = [], path
    while url:
        try:
            data = client._get(url, params)
        except Exception:
            break
        results.extend(data.get("results", []))
        next_url = data.get("next_url", "")
        from data.polygon_client import PolygonClient
        url = next_url.replace(PolygonClient.BASE, "") if next_url else None
        params = {}
    if not results:
        return pd.DataFrame()
    df = pd.DataFrame(results).rename(columns={"o":"open","h":"high","l":"low","c":"close","v":"volume"})
    df["date"] = pd.to_datetime(df["t"], unit="ms", utc=True).dt.date
    return df[["date","open","high","low","close","volume"]].sort_values("date").reset_index(drop=True)


def _scr_fetch_iv(ticker: str, client) -> Optional[float]:
    try:
        data = client._get(f"/v3/snapshot/options/{ticker}",
                           {"limit": 250, "contract_type": "call"})
        ivs = [float(s["implied_volatility"])
               for s in data.get("results", [])
               if s.get("implied_volatility") and float(s["implied_volatility"]) > 0]
        return float(np.median(ivs[:20])) if ivs else None
    except Exception:
        return None


def _scr_hv(closes: pd.Series, window: int) -> Optional[float]:
    if len(closes) < window + 1:
        return None
    log_ret = np.log(closes / closes.shift(1)).dropna()
    if len(log_ret) < window:
        return None
    return float(log_ret.iloc[-window:].std() * math.sqrt(252) * 100)


def _scr_rsi(closes: pd.Series, period: int = 14) -> Optional[float]:
    if len(closes) < period + 1:
        return None
    delta = closes.diff().dropna()
    ag = delta.clip(lower=0).rolling(period, min_periods=period).mean()
    al = (-delta).clip(lower=0).rolling(period, min_periods=period).mean()
    if ag.empty or al.empty:
        return None
    a, b = float(ag.iloc[-1]), float(al.iloc[-1])
    return 100.0 if b == 0 else float(100 - (100 / (1 + a / b)))


# ── Screener chart builders ─────────────────────────────────────────────────────

def _build_movers_fig(rows: list[dict]):
    if not rows:
        return _scr_empty_fig("No data")
    tickers = [r["Ticker"] for r in rows]
    changes = [r["Change%"] for r in rows]
    colors  = [T.SUCCESS if c >= 0 else T.DANGER for c in changes]
    fig = go.Figure(go.Bar(
        x=changes, y=tickers, orientation="h",
        marker_color=colors,
        text=[f"{c:+.2f}%" for c in changes],
        textposition="outside", textfont=dict(size=11, color=D.COLOR.text),
        hovertemplate="%{y}: %{x:+.2f}%<extra></extra>",
    ))
    fig.update_layout(
        paper_bgcolor=_SCR_PAPER_BG, plot_bgcolor=_SCR_PLOT_BG, font=_SCR_FONT,
        height=max(260, len(tickers) * 28),
        margin=dict(l=10, r=60, t=10, b=10),
        xaxis=dict(showgrid=True, gridcolor=_SCR_GRID, zeroline=True,
                   zerolinecolor=D.COLOR.border_brt, ticksuffix="%", color=D.COLOR.text_sec),
        yaxis=dict(showgrid=False, color=D.COLOR.text, autorange="reversed"),
        bargap=0.3,
    )
    return fig


def _build_momentum_fig(rows: list[dict]):
    if not rows:
        return _scr_empty_fig("No data")
    top = sorted(
        [r for r in rows if isinstance(r["20d%"], (int, float))],
        key=lambda r: abs(r["20d%"]), reverse=True
    )[:15] or rows[:15]
    tickers = [r["Ticker"] for r in top]
    r1  = [r["1d%"]  if isinstance(r["1d%"],  (int, float)) else 0 for r in top]
    r5  = [r["5d%"]  if isinstance(r["5d%"],  (int, float)) else 0 for r in top]
    r20 = [r["20d%"] if isinstance(r["20d%"], (int, float)) else 0 for r in top]
    fig = go.Figure()
    fig.add_trace(go.Bar(name="1d%",  x=tickers, y=r1,  marker_color="#6366f1",
                         hovertemplate="%{x} 1d: %{y:+.1f}%<extra></extra>"))
    fig.add_trace(go.Bar(name="5d%",  x=tickers, y=r5,  marker_color="#8b5cf6",
                         hovertemplate="%{x} 5d: %{y:+.1f}%<extra></extra>"))
    fig.add_trace(go.Bar(name="20d%", x=tickers, y=r20, marker_color="#a78bfa",
                         hovertemplate="%{x} 20d: %{y:+.1f}%<extra></extra>"))
    fig.update_layout(
        paper_bgcolor=_SCR_PAPER_BG, plot_bgcolor=_SCR_PLOT_BG, font=_SCR_FONT,
        height=420, barmode="group", bargap=0.2, bargroupgap=0.05,
        margin=dict(l=10, r=10, t=10, b=60),
        xaxis=dict(showgrid=False, color=D.COLOR.text_sec, tickangle=-30),
        yaxis=dict(showgrid=True, gridcolor=_SCR_GRID, zeroline=True,
                   zerolinecolor=D.COLOR.border_brt, ticksuffix="%", color=D.COLOR.text_sec),
        legend=dict(orientation="h", x=0, y=1.06, font=dict(size=11)),
    )
    return fig


def _build_vol_fig(rows: list[dict]):
    if not rows:
        return _scr_empty_fig("No data")
    def _num(v): return float(str(v).replace("%","")) if v != "—" else None
    def _ratio(r):
        ih = r.get("IV/HV")
        return float(ih) if isinstance(ih, (int, float)) else 0.0
    top = sorted(rows, key=_ratio, reverse=True)[:15]
    tickers = [r["Ticker"] for r in top]
    hv20 = [_num(r["HV20"]) for r in top]
    iv   = [_num(r["IV"])   for r in top]
    iv_colors = [T.WARNING if (h and i and i > 1.5 * h) else T.ACCENT
                 for h, i in zip(hv20, iv)]
    fig = go.Figure()
    fig.add_trace(go.Bar(name="HV20", x=tickers, y=hv20, marker_color="#3b82f6",
                         hovertemplate="%{x} HV20: %{y:.1f}%<extra></extra>"))
    fig.add_trace(go.Bar(name="IV",   x=tickers, y=iv,   marker_color=iv_colors,
                         hovertemplate="%{x} IV: %{y:.1f}%<extra></extra>"))
    fig.update_layout(
        paper_bgcolor=_SCR_PAPER_BG, plot_bgcolor=_SCR_PLOT_BG, font=_SCR_FONT,
        height=420, barmode="group", bargap=0.2, bargroupgap=0.05,
        margin=dict(l=10, r=10, t=10, b=60),
        xaxis=dict(showgrid=False, color=D.COLOR.text_sec, tickangle=-30),
        yaxis=dict(showgrid=True, gridcolor=_SCR_GRID, ticksuffix="%", color=D.COLOR.text_sec),
        legend=dict(orientation="h", x=0, y=1.06, font=dict(size=11)),
    )
    return fig


def _build_volalert_fig(rows: list[dict]):
    if not rows:
        fig = go.Figure()
        fig.add_annotation(text="No tickers with volume > 2× average",
                           xref="paper", yref="paper", x=0.5, y=0.5,
                           showarrow=False, font=dict(color=D.COLOR.text_muted, size=13))
        fig.update_layout(paper_bgcolor=_SCR_PAPER_BG, plot_bgcolor=_SCR_PLOT_BG,
                          font=_SCR_FONT, height=160, margin=dict(l=10,r=10,t=10,b=10),
                          xaxis=dict(visible=False), yaxis=dict(visible=False))
        return fig
    tickers = [r["Ticker"] for r in rows]
    ratios  = [r["Vol Ratio"] for r in rows]
    fig = go.Figure(go.Bar(
        x=tickers, y=ratios,
        marker_color=[T.DANGER if r >= 3 else T.WARNING for r in ratios],
        text=[f"{r:.1f}×" for r in ratios],
        textposition="outside", textfont=dict(size=11, color=D.COLOR.text),
        hovertemplate="%{x}: %{y:.1f}× avg volume<extra></extra>",
    ))
    fig.add_hline(y=2, line_dash="dot", line_color=D.COLOR.border_brt,
                  annotation_text="2× threshold", annotation_font_size=10)
    fig.update_layout(
        paper_bgcolor=_SCR_PAPER_BG, plot_bgcolor=_SCR_PLOT_BG, font=_SCR_FONT,
        height=220, margin=dict(l=10, r=10, t=10, b=30),
        xaxis=dict(showgrid=False, color=D.COLOR.text_sec),
        yaxis=dict(showgrid=True, gridcolor=_SCR_GRID, ticksuffix="×", color=D.COLOR.text_sec),
    )
    return fig


_FUTURES_CATEGORIES: list[dict] = [
    {
        "label": "Energy",
        "color": "#f97316",
        "tickers": [
            ("CL=F",  "WTI Crude Oil"),
            ("BZ=F",  "Brent Crude"),
            ("NG=F",  "Natural Gas"),
            ("HO=F",  "Heating Oil"),
            ("RB=F",  "RBOB Gasoline"),
        ],
    },
    {
        "label": "Metals",
        "color": "#a78bfa",
        "tickers": [
            ("GC=F",  "Gold"),
            ("SI=F",  "Silver"),
            ("HG=F",  "Copper"),
            ("PL=F",  "Platinum"),
            ("PA=F",  "Palladium"),
        ],
    },
    {
        "label": "Agriculture",
        "color": "#4ade80",
        "tickers": [
            ("ZW=F",  "Wheat"),
            ("ZC=F",  "Corn"),
            ("ZS=F",  "Soybeans"),
            ("KC=F",  "Coffee"),
            ("CC=F",  "Cocoa"),
            ("SB=F",  "Sugar #11"),
            ("CT=F",  "Cotton"),
        ],
    },
    {
        "label": "Rates",
        "color": "#fbbf24",
        "tickers": [
            ("ZB=F",   "30Y T-Bond"),
            ("ZN=F",   "10Y T-Note"),
            ("ZF=F",   "5Y T-Note"),
            ("ZT=F",   "2Y T-Note"),
            ("SR3=F",  "SOFR 3M"),
        ],
    },
    {
        "label": "Crypto",
        "color": "#38bdf8",
        "tickers": [
            ("BTC=F",  "Bitcoin Futures"),
            ("ETH=F",  "Ethereum Futures"),
            ("MBT=F",  "Micro BTC Futures"),
        ],
    },
]

# caps used to normalize cell color intensity (per column)
_FUT_CAPS = {"1D": 3.0, "5D": 7.0, "1M": 15.0, "YTD": 30.0}


def _fetch_futures_data() -> dict[str, dict]:
    """
    Fetch 1D/5D/1M/YTD moves for all futures tickers using yfinance.
    Returns {ticker: {last, 1D, 5D, 1M, YTD}} — pct values as floats (e.g. -1.23).
    Missing values are None.
    """
    import yfinance as yf
    import datetime as _dt

    all_tickers = [t for cat in _FUTURES_CATEGORIES for t, _ in cat["tickers"]]
    today = _dt.date.today()
    start = (today - _dt.timedelta(days=400)).strftime("%Y-%m-%d")

    result: dict[str, dict] = {}
    try:
        raw = yf.download(
            all_tickers,
            start=start,
            end=today.strftime("%Y-%m-%d"),
            auto_adjust=True,
            progress=False,
        )
    except Exception as exc:
        logger.warning(f"yfinance futures download failed: {exc}")
        return result

    def _get_close(ticker: str) -> pd.Series | None:
        try:
            if isinstance(raw.columns, pd.MultiIndex):
                closes = raw["Close"][ticker].dropna()
            else:
                # single-ticker download — columns are flat ("Close", "Open", ...)
                closes = raw["Close"].dropna()
            return closes if not closes.empty else None
        except Exception:
            return None

    ytd_start = _dt.date(today.year, 1, 1)

    for ticker in all_tickers:
        closes = _get_close(ticker)
        if closes is None or len(closes) < 2:
            result[ticker] = {"last": None, "1D": None, "5D": None, "1M": None, "YTD": None}
            continue

        last = float(closes.iloc[-1])

        def _pct(n_days: int | None = None, from_date: _dt.date | None = None) -> float | None:
            try:
                if from_date is not None:
                    idx = closes.index.searchsorted(pd.Timestamp(from_date))
                    if idx >= len(closes):
                        return None
                    ref = float(closes.iloc[idx])
                else:
                    if len(closes) < (n_days + 1):
                        return None
                    ref = float(closes.iloc[-(n_days + 1)])
                return (last / ref - 1) * 100 if ref else None
            except Exception:
                return None

        result[ticker] = {
            "last": last,
            "1D":   _pct(1),
            "5D":   _pct(5),
            "1M":   _pct(21),
            "YTD":  _pct(from_date=ytd_start),
        }

    return result


def _fut_cell_style(value: float | None, col: str) -> dict:
    """Background color for a pct move cell. Intensity scales with magnitude."""
    if value is None:
        return {}
    cap = _FUT_CAPS.get(col, 10.0)
    alpha = min(abs(value) / cap, 1.0) * 0.45
    if value >= 0:
        return {"backgroundColor": f"rgba(16,185,129,{alpha:.2f})", "color": "#d1fae5" if alpha > 0.25 else T.TEXT_PRIMARY}
    else:
        return {"backgroundColor": f"rgba(239,68,68,{alpha:.2f})", "color": "#fee2e2" if alpha > 0.25 else T.TEXT_PRIMARY}


def _fmt_pct(v: float | None) -> str:
    if v is None:
        return "—"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.2f}%"


def _render_intraday(ticker: str, api_key: str):
    from plotly.subplots import make_subplots
    import datetime as _dt
    df = _fetch_intraday(ticker, api_key)
    if df.empty:
        return html.P(
            "No intraday data — market may be closed, or try EOD History.",
            style={"color": T.WARNING, "fontSize": "12px"})

    close   = pd.to_numeric(df["close"], errors="coerce")
    open_px = pd.to_numeric(df["open"],  errors="coerce")
    vwap    = pd.to_numeric(df.get("vwap", pd.Series(dtype=float)), errors="coerce")
    volume  = pd.to_numeric(df.get("volume", pd.Series(dtype=float)), errors="coerce")

    start_px  = float(open_px.iloc[0])
    last_px   = float(close.iloc[-1])
    chg       = last_px - start_px
    chg_pct   = chg / start_px * 100 if start_px else 0
    line_color = T.SUCCESS if chg >= 0 else T.DANGER
    fill_color = "rgba(16,185,129,0.08)" if chg >= 0 else "rgba(239,68,68,0.08)"

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.75, 0.25], vertical_spacing=0.02,
    )

    # Candlestick chart
    high_px = pd.to_numeric(df.get("high", close), errors="coerce")
    low_px  = pd.to_numeric(df.get("low",  close), errors="coerce")
    fig.add_trace(go.Candlestick(
        x=df["datetime"],
        open=open_px, high=high_px, low=low_px, close=close,
        name="Price",
        increasing_line_color=T.SUCCESS, decreasing_line_color=T.DANGER,
        increasing_fillcolor=T.SUCCESS,  decreasing_fillcolor=T.DANGER,
        hovertext=[f"{t.strftime('%H:%M')}  O:{o:.2f} H:{h:.2f} L:{l:.2f} C:{c:.2f}"
                   for t, o, h, l, c in zip(df["datetime"], open_px, high_px, low_px, close)],
        hoverinfo="text",
    ), row=1, col=1)

    # VWAP
    if not vwap.empty and vwap.notna().any():
        fig.add_trace(go.Scatter(
            x=df["datetime"], y=vwap,
            name="VWAP",
            line=dict(color="#ffa726", width=1.5, dash="dot"),
            hovertemplate="%{x|%H:%M}  VWAP $%{y:.2f}<extra></extra>",
        ), row=1, col=1)

    # Volume bars
    if not volume.empty and volume.notna().any():
        bar_colors = [T.SUCCESS if c >= o else T.DANGER
                      for c, o in zip(close, open_px)]
        fig.add_trace(go.Bar(
            x=df["datetime"], y=volume,
            name="Volume",
            marker_color=bar_colors, opacity=0.6, showlegend=False,
            hovertemplate="%{x|%H:%M}  %{y:,.0f}<extra>Vol</extra>",
        ), row=2, col=1)

    # Open price reference line
    fig.add_hline(y=start_px, row=1, col=1,
                  line=dict(color=T.BORDER_BRT, width=1, dash="dot"))

    last_time = df["datetime"].iloc[-1].strftime("%H:%M")
    fig.update_layout(
        **_DARK,
        title=dict(
            text=f"{ticker} Today  ·  {len(df)} bars  ·  last {last_time} ET",
            font=dict(size=13, color=T.TEXT_SEC),
        ),
        height=420, hovermode="x unified",
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", x=0, y=1.02,
                    font=dict(size=11, color=T.TEXT_SEC), bgcolor="rgba(0,0,0,0)"),
        margin=dict(l=0, r=0, t=50, b=0),
    )
    fig.update_yaxes(gridcolor=T.BORDER, autorange=True)
    fig.update_xaxes(gridcolor=T.BORDER, rangeslider_visible=False)
    fig.update_yaxes(title_text="Vol", row=2, col=1)
    # Price axis: auto-scale to candle range, not from zero
    price_min = float(low_px.min()) * 0.999
    price_max = float(high_px.max()) * 1.001
    fig.update_yaxes(range=[price_min, price_max], row=1, col=1)

    chg_str = f"{chg:+.2f} ({chg_pct:+.1f}%)"
    return html.Div([
        html.Div(
            f"${last_px:.2f}  {chg_str}  (from open ${start_px:.2f})",
            style={"color": line_color, "fontSize": "13px",
                   "fontWeight": "600", "marginBottom": "8px"},
        ),
        dcc.Graph(figure=fig, config=_GRAPH_CFG),
    ])


def _render_yield_inner():
    df = _load_yield_curve()
    if df is None or df.empty:
        return html.P("Could not load yield curve from FRED.", style={"color": T.WARNING})

    latest = df.iloc[-1]
    cols_avail  = [(lbl, col) for lbl, _, col in _MATURITIES if col in df.columns]
    labels_avail = [lbl for lbl, _ in cols_avail]
    col_names    = [col for _, col in cols_avail]

    def _v(col):
        v = latest.get(col)
        return float(v) if v is not None and not pd.isna(v) else None

    y2, y10, y30 = _v("rate_2y"), _v("rate_10y"), _v("rate_30y")
    y3m = _v("rate_3m")
    spr  = y10 - y2  if y10 and y2  else None
    spr3 = y10 - y3m if y10 and y3m else None

    metrics = html.Div([
        _pill("2Y",     f"{y2:.2f}%"  if y2  else "—"),
        _pill("10Y",    f"{y10:.2f}%" if y10 else "—"),
        _pill("30Y",    f"{y30:.2f}%" if y30 else "—"),
        _pill("2s10s",  f"{spr:+.2f}%" if spr  else "—",
              T.SUCCESS if spr and spr >= 0 else T.DANGER),
        _pill("3m10y",  f"{spr3:+.2f}%" if spr3 else "—",
              T.SUCCESS if spr3 and spr3 >= 0 else T.DANGER),
    ], style={"display": "flex", "gap": "10px", "flexWrap": "wrap", "marginBottom": "16px"})

    # Yield curve snapshot
    colors = [T.ACCENT, T.WARNING, T.SUCCESS, T.DANGER]
    offsets = [("Today", 0), ("~1M ago", 21), ("~3M ago", 63), ("~1Y ago", 252)]
    fig_c = go.Figure()
    for i, (lbl, off) in enumerate(offsets):
        row  = df.iloc[max(0, len(df) - 1 - off)]
        vals = [float(row[c]) if row.get(c) is not None and not pd.isna(row.get(c)) else None
                for c in col_names]
        fig_c.add_trace(go.Scatter(
            x=labels_avail, y=vals, mode="lines+markers",
            name=f"{lbl} ({row['date']})",
            line=dict(color=colors[i % len(colors)], width=2),
            marker=dict(size=7),
        ))
    fig_c.add_hline(y=0, line=dict(color=T.BORDER_BRT, width=1, dash="dot"))
    fig_c.update_layout(**_DARK, height=300,
                        title=dict(text="Treasury Yield Curve", font=dict(size=13, color=T.TEXT_SEC)),
                        xaxis_title="Maturity", yaxis_title="Yield (%)",
                        legend=dict(orientation="h", y=-0.25, bgcolor="rgba(0,0,0,0)"),
                        margin=dict(l=0, r=0, t=40, b=80))

    # Historical yields
    hist_colors = [T.ACCENT, T.WARNING, T.SUCCESS, T.DANGER, "#c084fc", "#fb923c"]
    fig_h = go.Figure()
    for i, (lbl, _, col) in enumerate(_MATURITIES):
        if col in df.columns:
            fig_h.add_trace(go.Scatter(
                x=df["date"], y=df[col], mode="lines", name=f"{lbl}",
                line=dict(color=hist_colors[i % len(hist_colors)], width=1.5),
            ))
    if "rate_2y" in df.columns and "rate_10y" in df.columns:
        fig_h.add_trace(go.Scatter(
            x=df["date"], y=df["rate_10y"] - df["rate_2y"],
            mode="lines", name="2s10s",
            line=dict(color="#666", width=1, dash="dot"), yaxis="y2",
        ))
    fig_h.add_hline(y=0, line=dict(color=T.BORDER_BRT, width=1, dash="dot"))
    fig_h.update_layout(**_DARK, height=320,
                        title=dict(text="Treasury Yields — History", font=dict(size=13, color=T.TEXT_SEC)),
                        yaxis2=dict(title="Spread", overlaying="y", side="right", showgrid=False),
                        legend=dict(orientation="h", y=-0.25, bgcolor="rgba(0,0,0,0)"),
                        margin=dict(l=0, r=0, t=40, b=80))

    # 3D Surface
    try:
        import datetime as _dt
        surf = df.set_index("date").sort_index()
        surf.index = pd.to_datetime(surf.index)
        t_cols  = [col for _, _, col in _MATURITIES if col in surf.columns]
        t_lbls  = [lbl for lbl, _, col in _MATURITIES if col in surf.columns]
        surf    = surf[t_cols].dropna(how="all")
        surf    = surf[surf.index >= pd.Timestamp(_dt.date.today()) - pd.Timedelta(days=730)]
        surf    = surf.iloc[::5]

        n_d = len(surf)
        d_str = [str(d.date() if hasattr(d, "date") else d) for d in surf.index]
        z_mat = surf[t_cols].values.astype(float)
        n_t   = len(t_cols)

        # Forward-fill NaNs
        for ci in range(n_t):
            mask = np.isnan(z_mat[:, ci])
            if mask.any() and not mask.all():
                idx = np.where(~mask)[0]
                z_mat[mask, ci] = np.interp(np.where(mask)[0], idx, z_mat[idx, ci])

        ti  = list(range(n_t))
        yi  = list(range(n_d))
        ts  = max(1, n_d // 8)
        tvl = list(range(0, n_d, ts))
        ttt = [d_str[i] for i in tvl]
        _lc = dict(color="#3a6a9a", width=2)

        traces = []
        for j in range(n_t):
            traces.append(go.Scatter3d(
                x=[j]*n_d, y=yi, z=z_mat[:, j].tolist(),
                mode="lines", line=_lc, showlegend=False,
                hovertemplate=f"{t_lbls[j]}: %{{z:.2f}}%<extra></extra>",
            ))
        ds = max(1, n_d // 10)
        for k in range(0, n_d, ds):
            traces.append(go.Scatter3d(
                x=ti, y=[k]*n_t, z=z_mat[k, :].tolist(),
                mode="lines", line=_lc, showlegend=False,
            ))
        _ax = dict(gridcolor="#2a3050", backgroundcolor="#0c1020",
                   color="#e0e0e0", showbackground=True)
        fig3d = go.Figure(data=traces)
        fig3d.update_layout(
            paper_bgcolor="#0e1117", font=dict(color="#e0e0e0", size=12),
            title=dict(text="Treasury Yield Surface — Maturity × Date × Yield",
                       font=dict(size=14, color="#e0e0e0")),
            scene=dict(
                xaxis=dict(**_ax, title="Maturity", tickvals=ti, ticktext=t_lbls),
                yaxis=dict(**_ax, title="Date", tickvals=tvl, ticktext=ttt),
                zaxis=dict(**_ax, title="Yield (%)", tickformat=".2f"),
                bgcolor="#0c1020",
                camera=dict(eye=dict(x=1.8, y=-1.6, z=0.8)),
                aspectmode="manual", aspectratio=dict(x=1.2, y=2.0, z=0.7),
            ),
            height=700, margin=dict(l=0, r=0, t=50, b=0),
        )
        g3d = dcc.Graph(figure=fig3d, config={"displayModeBar": True})
    except Exception as e:
        g3d = html.P(f"3D surface error: {e}", style={"color": T.DANGER})

    return html.Div([
        metrics,
        dbc.Row([
            dbc.Col(dcc.Graph(figure=fig_c, config=_GRAPH_CFG), width=6),
            dbc.Col(dcc.Graph(figure=fig_h, config=_GRAPH_CFG), width=6),
        ], className="g-3", style={"marginBottom": "16px"}),
        html.Div("3D Yield Surface (2y lookback, weekly)",
                 style={"color": T.TEXT_SEC, "fontSize": "11px", "fontWeight": "600",
                        "textTransform": "uppercase", "marginBottom": "8px"}),
        g3d,
        html.P("Source: FRED (St. Louis Fed) — free, cached per session.",
               style={"color": T.TEXT_MUTED, "fontSize": "11px", "marginTop": "6px"}),
    ])


from statistics import NormalDist as _NormalDist
_NORM_CDF  = _NormalDist().cdf
_RISK_FREE = 0.043   # ~3M T-bill; dividends ignored — indicative model price


def _bs_price(S: float, K: float, T: float, sigma: float, is_call: bool) -> float | None:
    """Black-Scholes theoretical option price (no dividends). Falls back to
    intrinsic value when inputs are degenerate. sigma is decimal (0.20 = 20%)."""
    if not S or not K or S <= 0 or K <= 0:
        return None
    if T <= 0 or not sigma or sigma <= 0:
        return max(0.0, (S - K) if is_call else (K - S))
    srt = sigma * math.sqrt(T)
    d1  = (math.log(S / K) + (_RISK_FREE + 0.5 * sigma * sigma) * T) / srt
    d2  = d1 - srt
    if is_call:
        return S * _NORM_CDF(d1) - K * math.exp(-_RISK_FREE * T) * _NORM_CDF(d2)
    return K * math.exp(-_RISK_FREE * T) * _NORM_CDF(-d2) - S * _NORM_CDF(-d1)


def _build_chain_table(df: "pd.DataFrame", expiry: str, spot: float,
                       moneyness: str = "all") -> "html.Div":
    """Returns an AG Grid in OMON style: calls left | strike centre | puts right.

    No live NBBO on this plan, so each side shows the delayed traded mark (Last)
    and a Black-Scholes Model price computed from the contract's IV, spot and DTE.
    """
    exp = df[df["expiration"] == expiry].copy()
    calls = exp[exp["type"] == "call"].set_index("strike")
    puts  = exp[exp["type"] == "put"].set_index("strike")
    all_strikes = sorted(set(calls.index) | set(puts.index))

    # Moneyness filter
    if moneyness == "itm":
        strikes = [k for k in all_strikes if k < spot]          # ITM calls = below spot
    elif moneyness == "otm":
        strikes = [k for k in all_strikes if k > spot]          # OTM calls = above spot
    elif moneyness == "near":
        strikes = [k for k in all_strikes if abs(k - spot) / spot <= 0.10]
    else:
        strikes = all_strikes

    def _pct(v):
        return f"{v*100:.1f}%" if v and float(v) > 0 else "—"
    def _px(v):
        return f"{v:.2f}" if v and float(v) > 0 else "—"
    def _vol(v):
        return f"{int(v):,}" if v and float(v) > 0 else "—"

    def _model_px(leg: dict, strike: float, is_call: bool):
        iv, dte = leg.get("iv"), leg.get("dte")
        if not iv or dte is None:
            return None
        try:
            return _bs_price(spot, float(strike), float(dte) / 365.0, float(iv), is_call)
        except Exception:
            return None

    atm_dist = min(abs(s - spot) for s in strikes) if strikes else 0
    rows = []
    for k in strikes:
        c = calls.loc[k].to_dict() if k in calls.index else {}
        p = puts.loc[k].to_dict()  if k in puts.index  else {}
        is_atm = abs(k - spot) == atm_dist
        rows.append({
            "c_iv":      _pct(c.get("iv")),
            "c_last":    _px( c.get("last")),
            "c_model":   _px(_model_px(c, k, True)),
            "c_vol":     _vol(c.get("volume")),
            "strike":    f"${k:.0f}",
            "p_model":   _px(_model_px(p, k, False)),
            "p_last":    _px( p.get("last")),
            "p_iv":      _pct(p.get("iv")),
            "p_vol":     _vol(p.get("volume")),
            "_atm":      is_atm,
            "_itm_call": k < spot,
            "_itm_put":  k > spot,
        })

    # ── Render as a styled HTML table (OMON mirror) — no grid library ─────────
    # Per-cell colouring is computed here in Python from the _atm/_itm flags:
    #   ATM row  → green-tinted background, bold
    #   ITM cell → bright; OTM cell → dimmed
    DIM, BRIGHT, ATM_BG = "#6b7280", T.TEXT_PRIMARY, "#0d2b1a"

    def _cell(value, row, itm_key):
        st = {"padding": "2px 10px", "fontSize": "12px", "textAlign": "right",
              "fontFamily": "JetBrains Mono, monospace", "whiteSpace": "nowrap"}
        if row["_atm"]:
            st.update({"backgroundColor": ATM_BG, "fontWeight": "700", "color": BRIGHT})
        elif row[itm_key]:
            st["color"] = BRIGHT
        else:
            st["color"] = DIM
        return html.Td(value, style=st)

    def _strike_cell(row):
        st = {"padding": "2px 10px", "fontSize": "12px", "textAlign": "center",
              "fontFamily": "JetBrains Mono, monospace", "fontWeight": "700"}
        if row["_atm"]:
            st.update({"backgroundColor": ATM_BG, "color": "#69f0ae"})
        else:
            st["color"] = "#e0e0e0"
        return html.Td(row["strike"], style=st)

    _grp = {"padding": "5px 8px", "fontSize": "11px", "fontWeight": "700",
            "textTransform": "uppercase", "letterSpacing": "0.08em",
            "textAlign": "center", "backgroundColor": T.BG_CARD,
            "position": "sticky", "top": "0", "zIndex": "3"}
    _sub = {"padding": "4px 10px", "fontSize": "10px", "fontWeight": "700",
            "textTransform": "uppercase", "letterSpacing": "0.04em",
            "color": T.TEXT_MUTED, "textAlign": "right",
            "borderBottom": f"1px solid {T.BORDER}",
            "backgroundColor": T.BG_CARD, "position": "sticky", "top": "26px", "zIndex": "3"}

    header = html.Thead([
        html.Tr([
            html.Th("Calls", colSpan=4, style={**_grp, "color": T.SUCCESS}),
            html.Th("",      style=_grp),
            html.Th("Puts",  colSpan=4, style={**_grp, "color": T.DANGER}),
        ]),
        html.Tr(
            [html.Th(h, style=_sub) for h in ("Vol", "IV", "Last", "Model")]
            + [html.Th("Strike", style={**_sub, "textAlign": "center"})]
            + [html.Th(h, style=_sub) for h in ("Model", "Last", "IV", "Vol")]
        ),
    ])
    body = html.Tbody([
        html.Tr([
            _cell(r["c_vol"],   r, "_itm_call"),
            _cell(r["c_iv"],    r, "_itm_call"),
            _cell(r["c_last"],  r, "_itm_call"),
            _cell(r["c_model"], r, "_itm_call"),
            _strike_cell(r),
            _cell(r["p_model"], r, "_itm_put"),
            _cell(r["p_last"],  r, "_itm_put"),
            _cell(r["p_iv"],    r, "_itm_put"),
            _cell(r["p_vol"],   r, "_itm_put"),
        ]) for r in rows
    ])
    return html.Div(
        html.Table([header, body],
                   style={"width": "100%", "borderCollapse": "collapse"}),
        style={"maxHeight": "520px", "overflowY": "auto", "width": "100%",
               "border": f"1px solid {T.BORDER}", "borderRadius": "8px"},
    )
