"""
dash_app/pages/market.py
Market Data — pure Polygon.io (no DB dependency).
All sections load when user clicks "Load".
Mirrors dashboard/tabs/market_data.py feature set.
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
from dash import html, dcc, callback, Input, Output, State, no_update, ALL
import dash_bootstrap_components as dbc

from dash_app import theme as T, get_polygon_api_key
from engine.screener import UNIVERSES

logger = logging.getLogger(__name__)

# ── FRED yield curve (free, no API key) ────────────────────────────────────────

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
    import datetime as _dt
    from data.loader import _fetch_polygon_aggs
    c    = _polygon_client(api_key)
    to   = _dt.date.today()
    frm  = to - _dt.timedelta(days=int(n_days * 1.4))
    return _fetch_polygon_aggs(c, ticker, frm.strftime("%Y-%m-%d"), to.strftime("%Y-%m-%d"))


def _fetch_intraday(ticker: str, api_key: str) -> pd.DataFrame:
    """Fetch 1-minute bars for today from Polygon. Returns df with 'datetime' column."""
    import datetime as _dt
    c = _polygon_client(api_key)
    today = _dt.date.today().strftime("%Y-%m-%d")
    results = []
    url = f"/v2/aggs/ticker/{ticker}/range/1/minute/{today}/{today}"
    params = {"adjusted": "true", "sort": "asc", "limit": 50000}
    while url:
        data = c._get(url, params)
        results.extend(data.get("results", []))
        url = data.get("next_url", "").replace(c.BASE, "") or None
        params = {}
    if not results:
        return pd.DataFrame()
    df = pd.DataFrame(results)
    df["datetime"] = pd.to_datetime(df["t"], unit="ms", utc=True).dt.tz_convert("America/New_York")
    df = df.rename(columns={"o": "open", "h": "high", "l": "low",
                             "c": "close", "v": "volume", "vw": "vwap"})
    cols = [c for c in ["datetime", "open", "high", "low", "close", "volume", "vwap"] if c in df.columns]
    return df[cols].reset_index(drop=True)


# ── UI helpers ─────────────────────────────────────────────────────────────────

def _hint(text: str) -> html.P:
    return html.P(text, style={"color": T.TEXT_MUTED, "fontSize": "12px",
                               "fontStyle": "italic", "margin": "4px 0"})


def _section(title: str, content) -> html.Div:
    return html.Div([
        html.Div(title, style={
            "color": T.TEXT_SEC, "fontSize": "11px", "fontWeight": "600",
            "textTransform": "uppercase", "letterSpacing": "0.07em",
            "borderBottom": f"1px solid {T.BORDER}",
            "paddingBottom": "8px", "marginBottom": "12px",
        }),
        content,
    ], style={**T.STYLE_CARD, "marginBottom": "16px"})


def _pill(label: str, value: str, color: str = T.TEXT_PRIMARY) -> html.Div:
    return html.Div([
        html.Div(label, style={"color": T.TEXT_MUTED, "fontSize": "10px", "fontWeight": "600",
                               "textTransform": "uppercase", "marginBottom": "3px"}),
        html.Div(value, style={"color": color, "fontSize": "1rem", "fontWeight": "700"}),
    ], style={**T.STYLE_CARD, "flex": "1", "minWidth": "90px", "padding": "8px 12px"})


_DARK = dict(template="plotly_dark", paper_bgcolor=T.BG_CARD, plot_bgcolor=T.BG_CARD,
             font=dict(color=T.TEXT_SEC, size=11))


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

_SCR_PLOT_BG  = "#111827"
_SCR_PAPER_BG = "#111827"
_SCR_GRID     = "#1f2937"
_SCR_FONT     = dict(family="Inter, sans-serif", color="#9ca3af", size=11)
_SCR_CFG      = {"displayModeBar": False, "responsive": True}


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
                           font=dict(color="#6b7280", size=13))
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
        textposition="outside", textfont=dict(size=11, color="#f9fafb"),
        hovertemplate="%{y}: %{x:+.2f}%<extra></extra>",
    ))
    fig.update_layout(
        paper_bgcolor=_SCR_PAPER_BG, plot_bgcolor=_SCR_PLOT_BG, font=_SCR_FONT,
        height=max(260, len(tickers) * 28),
        margin=dict(l=10, r=60, t=10, b=10),
        xaxis=dict(showgrid=True, gridcolor=_SCR_GRID, zeroline=True,
                   zerolinecolor="#374151", ticksuffix="%", color="#9ca3af"),
        yaxis=dict(showgrid=False, color="#f9fafb", autorange="reversed"),
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
        xaxis=dict(showgrid=False, color="#9ca3af", tickangle=-30),
        yaxis=dict(showgrid=True, gridcolor=_SCR_GRID, zeroline=True,
                   zerolinecolor="#374151", ticksuffix="%", color="#9ca3af"),
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
        xaxis=dict(showgrid=False, color="#9ca3af", tickangle=-30),
        yaxis=dict(showgrid=True, gridcolor=_SCR_GRID, ticksuffix="%", color="#9ca3af"),
        legend=dict(orientation="h", x=0, y=1.06, font=dict(size=11)),
    )
    return fig


def _build_volalert_fig(rows: list[dict]):
    if not rows:
        fig = go.Figure()
        fig.add_annotation(text="No tickers with volume > 2× average",
                           xref="paper", yref="paper", x=0.5, y=0.5,
                           showarrow=False, font=dict(color="#6b7280", size=13))
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
        textposition="outside", textfont=dict(size=11, color="#f9fafb"),
        hovertemplate="%{x}: %{y:.1f}× avg volume<extra></extra>",
    ))
    fig.add_hline(y=2, line_dash="dot", line_color="#374151",
                  annotation_text="2× threshold", annotation_font_size=10)
    fig.update_layout(
        paper_bgcolor=_SCR_PAPER_BG, plot_bgcolor=_SCR_PLOT_BG, font=_SCR_FONT,
        height=220, margin=dict(l=10, r=10, t=10, b=30),
        xaxis=dict(showgrid=False, color="#9ca3af"),
        yaxis=dict(showgrid=True, gridcolor=_SCR_GRID, ticksuffix="×", color="#9ca3af"),
    )
    return fig


# ── GEX guide: illustrative static charts ─────────────────────────────────────

def _gex_guide() -> html.Div:
    """Static illustrative section — no API calls, pure synthetic examples."""

    _bg  = "#111827"
    _grd = "#1f2937"
    _fnt = dict(family="Inter, sans-serif", color="#9ca3af", size=10)
    _cfg = {"displayModeBar": False, "responsive": True}

    def _base_layout(title, height=300):
        return dict(
            paper_bgcolor=_bg, plot_bgcolor=_bg, font=_fnt,
            height=height, barmode="overlay",
            title=dict(text=title, font=dict(size=12, color="#d1d5db"), x=0),
            xaxis=dict(tickprefix="$", gridcolor=_grd, color="#9ca3af"),
            yaxis=dict(title="GEX ($B)", gridcolor=_grd, zeroline=False, color="#9ca3af"),
            legend=dict(orientation="h", x=0, y=1.12, font=dict(size=10),
                        bgcolor="rgba(0,0,0,0)"),
            margin=dict(l=50, r=20, t=55, b=30),
        )

    def _bars_and_levels(strikes, calls, puts, spot, zero_g, g1, g2,
                         sig_hi=None, sig_lo=None):
        nets = [c + p for c, p in zip(calls, puts)]
        y_rng = max(max(calls), abs(min(puts))) * 1.4
        fig = go.Figure()
        # dealer cluster shading
        if g1 is not None and sig_hi is not None:
            fig.add_hrect(y0=-y_rng, y1=y_rng,
                          x0=min(g1, sig_hi), x1=max(g1, sig_hi),
                          fillcolor="rgba(239,68,68,0.08)", line_width=0)
        if g2 is not None and sig_lo is not None:
            fig.add_hrect(y0=-y_rng, y1=y_rng,
                          x0=min(g2, sig_lo), x1=max(g2, sig_lo),
                          fillcolor="rgba(16,185,129,0.08)", line_width=0)
        fig.add_trace(go.Bar(x=strikes, y=calls, name="Call GEX",
                             marker_color=T.SUCCESS, opacity=0.8,
                             hovertemplate="$%{x}  Call: %{y:.1f}B<extra></extra>"))
        fig.add_trace(go.Bar(x=strikes, y=puts, name="Put GEX",
                             marker_color=T.DANGER, opacity=0.8,
                             hovertemplate="$%{x}  Put: %{y:.1f}B<extra></extra>"))
        fig.add_trace(go.Bar(x=strikes, y=nets, name="Net GEX",
                             marker_color=[T.ACCENT if v >= 0 else "#7c3aed" for v in nets],
                             opacity=0.5,
                             hovertemplate="$%{x}  Net: %{y:.1f}B<extra></extra>"))
        fig.add_vline(x=spot,   line=dict(color="#fbbf24", width=1.5, dash="dash"),
                      annotation_text=f"Spot ${spot}", annotation_font_color="#fbbf24",
                      annotation_font_size=10, annotation_position="top right")
        if zero_g:
            fig.add_vline(x=zero_g, line=dict(color="#fb923c", width=1.2, dash="dot"),
                          annotation_text=f"ZERO G ${zero_g}",
                          annotation_font_color="#fb923c", annotation_font_size=10,
                          annotation_position="bottom left")
        if g1:
            fig.add_vline(x=g1, line=dict(color="#ef4444", width=1.2, dash="dot"),
                          annotation_text=f"G1 ${g1}",
                          annotation_font_color="#ef4444", annotation_font_size=10,
                          annotation_position="top left")
        if g2:
            fig.add_vline(x=g2, line=dict(color="#10b981", width=1.2, dash="dot"),
                          annotation_text=f"G2 ${g2}",
                          annotation_font_color="#10b981", annotation_font_size=10,
                          annotation_position="bottom left")
        if sig_hi:
            fig.add_vline(x=sig_hi, line=dict(color="#8b5cf6", width=1, dash="dot"),
                          annotation_text=f"σ ${sig_hi}",
                          annotation_font_color="#8b5cf6", annotation_font_size=10,
                          annotation_position="top right")
        if sig_lo:
            fig.add_vline(x=sig_lo, line=dict(color="#8b5cf6", width=1, dash="dot"),
                          annotation_text=f"σ ${sig_lo}",
                          annotation_font_color="#8b5cf6", annotation_font_size=10,
                          annotation_position="bottom right")
        fig.add_hline(y=0, line=dict(color="#374151", width=1))
        return fig

    # ── Scenario 1: Positive GEX, spot between G2 and G1 — pinning ────────────
    st1 = list(range(520, 591, 5))
    c1  = [max(0, 40 * np.exp(-((s - 565)**2) / 180)) for s in st1]
    p1  = [-max(0, 12 * np.exp(-((s - 535)**2) / 250)) for s in st1]
    fig1 = _bars_and_levels(st1, c1, p1, spot=554, zero_g=540, g1=565, g2=535,
                             sig_hi=578, sig_lo=522)
    fig1.update_layout(**_base_layout(
        "① Positive GEX — Spot between G2 ($535) and G1 ($565)  ·  ZERO G at $540"))

    # ── Scenario 2: Negative GEX, spot below ZERO G — amplification ────────────
    st2 = list(range(520, 591, 5))
    c2  = [max(0, 6  * np.exp(-((s - 575)**2) / 400)) for s in st2]
    p2  = [-max(0, 20 * np.exp(-((s - 548)**2) / 150)) for s in st2]
    fig2 = _bars_and_levels(st2, c2, p2, spot=552, zero_g=568, g1=575, g2=548,
                             sig_hi=585, sig_lo=530)
    fig2.update_layout(**_base_layout(
        "② Negative GEX — Spot BELOW ZERO G ($568)  ·  Amplification regime"))

    # ── Scenario 3: Spot just crossed ZERO G from below — regime flip ──────────
    st3 = list(range(520, 591, 5))
    c3  = [max(0, 15 * np.exp(-((s - 568)**2) / 280)) for s in st3]
    p3  = [-max(0, 10 * np.exp(-((s - 553)**2) / 280)) for s in st3]
    fig3 = _bars_and_levels(st3, c3, p3, spot=563, zero_g=560, g1=568, g2=553,
                             sig_hi=580, sig_lo=538)
    fig3.update_layout(**_base_layout(
        "③ Regime Flip — Spot ($563) just crossed above ZERO G ($560)  ·  Entry window"))

    def _rule(title, body, color=T.ACCENT):
        return html.Div([
            html.Span(title, style={"color": color, "fontWeight": "700",
                                    "fontSize": "12px"}),
            html.Span(f"  {body}", style={"color": "#9ca3af", "fontSize": "12px"}),
        ], style={"marginBottom": "6px"})

    pill_style = lambda c: {
        "display": "inline-block", "padding": "2px 10px", "borderRadius": "12px",
        "backgroundColor": c, "color": "#fff", "fontSize": "11px",
        "fontWeight": "600", "marginRight": "6px", "marginBottom": "4px",
    }

    return html.Div([
        # ── Level reference ───────────────────────────────────────────────────
        html.Div([
            html.Div("Key Levels", style={"color": T.TEXT_SEC, "fontSize": "11px",
                                          "fontWeight": "700", "textTransform": "uppercase",
                                          "marginBottom": "10px"}),
            html.Div([
                html.Span("Spot",   style=pill_style("#fbbf24")),
                html.Span("G1 — upper gamma wall", style=pill_style("#ef4444")),
                html.Span("ZERO G — flip point",   style=pill_style("#fb923c")),
                html.Span("G2 — lower gamma wall", style=pill_style("#10b981")),
                html.Span("σ — 1 std dev implied move", style=pill_style("#8b5cf6")),
            ], style={"marginBottom": "10px"}),
            html.Div([
                _rule("G1 (red):", "Strike above spot with highest absolute Net GEX. Mechanical ceiling — dealers sell every rally into it. Use for short call strikes."),
                _rule("ZERO G (orange):", "Where cumulative GEX crosses zero. Above = dampening (sell premium). Below = amplifying (protect positions). The single most important level.", "#fb923c"),
                _rule("G2 (green):", "Strike below spot with highest absolute Net GEX. Mechanical floor — dealers buy every dip into it. Use for short put strikes.", "#10b981"),
                _rule("σ (purple):", "One standard deviation implied move from nearest ATM IV. Beyond σ = dealer positioning thins out, moves can extend freely.", "#8b5cf6"),
                _rule("Dealer Clusters (shaded):", "Red band (G1→σ upper) and green band (G2→σ lower). Dense dealer positioning inside these zones — price moves slowly, tends to revert."),
            ]),
        ], style={**T.STYLE_CARD, "marginBottom": "12px", "padding": "12px 16px"}),

        # ── OI panel note ─────────────────────────────────────────────────────
        html.Div([
            html.Div("Open Interest Panel (right chart)", style={
                "color": T.TEXT_SEC, "fontSize": "11px", "fontWeight": "700",
                "textTransform": "uppercase", "marginBottom": "8px"}),
            _rule("Green bars (right):", "Call OI per strike. Large call OI wall above spot reinforces G1 as resistance."),
            _rule("Red bars (left):", "Put OI per strike, mirrored. Large put OI near G2 reinforces it as support.", T.DANGER),
            _rule("OI + GEX agreement:", "When G1 aligns with the tallest call OI bar, that level is double-confirmed — highest conviction for short call placement.", T.SUCCESS),
            _rule("Put OI >> Call OI:", "Indicates negative GEX regime. Dealers are short the overall book — amplification risk is elevated.", T.WARNING),
        ], style={**T.STYLE_CARD, "marginBottom": "12px", "padding": "12px 16px"}),

        # ── Example charts ────────────────────────────────────────────────────
        html.Div("Example Scenarios", style={
            "color": T.TEXT_SEC, "fontSize": "11px", "fontWeight": "700",
            "textTransform": "uppercase", "marginBottom": "10px",
        }),

        html.Div([
            dcc.Graph(figure=fig1, config=_cfg),
            html.Div([
                _rule("Regime:", "Dampening. Spot is above ZERO G, trapped between G2 ($535) and G1 ($565). Dealer clusters visible on both sides.", T.SUCCESS),
                _rule("Trade:", "Iron condor: short put at G2 ($535), short call at G1 ($565). Both short legs sit at mechanical walls with dealer backing.", T.SUCCESS),
                _rule("Caution:", "If spot breaks below ZERO G ($540), close the short put side immediately — regime will flip to amplifying.", T.WARNING),
            ], style={"padding": "8px 4px"}),
        ], style={**T.STYLE_CARD, "marginBottom": "12px", "padding": "14px"}),

        html.Div([
            dcc.Graph(figure=fig2, config=_cfg),
            html.Div([
                _rule("Regime:", "Amplifying. Spot ($552) is below ZERO G ($568). Put GEX dominates. Dealers must sell into any decline.", T.DANGER),
                _rule("Trade:", "Exit all premium-selling positions. Buy long puts or VIX calls. Size all trades at 50% of normal. Tighten stops to 1–1.5× ATR.", T.DANGER),
                _rule("Watch for:", "Net GEX transitioning from −$2B toward zero over 3–5 days. That transition + a spot close above ZERO G = the entry window.", "#fb923c"),
            ], style={"padding": "8px 4px"}),
        ], style={**T.STYLE_CARD, "marginBottom": "12px", "padding": "14px"}),

        html.Div([
            dcc.Graph(figure=fig3, config=_cfg),
            html.Div([
                _rule("Regime:", "Transitioning. Spot ($563) just crossed above ZERO G ($560). Call and put GEX now roughly balanced. Net GEX turning positive.", "#fb923c"),
                _rule("Trade:", "Wait one full daily close above ZERO G for confirmation. Then enter condors with short call at G1 ($568) and short put at G2 ($553).", T.SUCCESS),
                _rule("Don't jump early:", "An intraday touch above ZERO G without a close is not confirmation. The regime can flip back below on the same session.", T.WARNING),
            ], style={"padding": "8px 4px"}),
        ], style={**T.STYLE_CARD, "marginBottom": "0", "padding": "14px"}),
    ], style={"marginTop": "16px"})


# ── Vol Surface guide ─────────────────────────────────────────────────────────

def _vol_surface_guide() -> html.Div:
    """Static illustrative guide for the IV volatility surface."""
    _bg  = "#111827"
    _grd = "#1f2937"
    _fnt = dict(family="Inter, sans-serif", color="#9ca3af", size=10)
    _cfg = {"displayModeBar": False, "responsive": True}

    # IV smile: moneyness 0.80–1.20, three DTE slices
    mon = np.linspace(0.80, 1.20, 31)
    lbl = [f"{int(m*100)}%" for m in mon]
    def _smile(base, skew, wing):
        return [(base + (-skew*(m-1.0)) + wing*(m-1.0)**2*15) * 100 for m in mon]
    iv7d  = _smile(0.35, 0.10, 0.12)
    iv30d = _smile(0.28, 0.07, 0.10)
    iv90d = _smile(0.22, 0.04, 0.08)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=lbl, y=iv7d,  mode="lines", name="7 DTE",
                             line=dict(color="#ef4444", width=2)))
    fig.add_trace(go.Scatter(x=lbl, y=iv30d, mode="lines", name="30 DTE",
                             line=dict(color="#fbbf24", width=2)))
    fig.add_trace(go.Scatter(x=lbl, y=iv90d, mode="lines", name="90 DTE",
                             line=dict(color="#3b82f6", width=2)))
    fig.add_shape(type="line", xref="x", yref="paper",
                  x0="100%", x1="100%", y0=0, y1=1,
                  line=dict(color="#69f0ae", width=1.5, dash="dot"))
    fig.add_annotation(x="100%", y=1, xref="x", yref="paper",
                       text="ATM (green in 3D)", showarrow=False,
                       font=dict(color="#69f0ae", size=10),
                       xanchor="left", yanchor="bottom")
    fig.update_layout(
        paper_bgcolor=_bg, plot_bgcolor=_bg, font=_fnt, height=280,
        title=dict(text="IV Smile — put skew + term structure (synthetic)",
                   font=dict(size=12, color="#d1d5db"), x=0),
        xaxis=dict(title="Strike (% of spot)", gridcolor=_grd, color="#9ca3af"),
        yaxis=dict(title="IV (%)", gridcolor=_grd, color="#9ca3af"),
        legend=dict(orientation="h", x=0, y=1.12, font=dict(size=10), bgcolor="rgba(0,0,0,0)"),
        margin=dict(l=50, r=20, t=55, b=40),
    )

    def _rule(title, body, color=T.ACCENT):
        return html.Div([
            html.Span(title, style={"color": color, "fontWeight": "700", "fontSize": "12px"}),
            html.Span(f"  {body}", style={"color": "#9ca3af", "fontSize": "12px"}),
        ], style={"marginBottom": "6px"})

    return html.Div([
        html.Div([
            html.Div("Reading the Axes", style={
                "color": T.TEXT_SEC, "fontSize": "11px", "fontWeight": "700",
                "textTransform": "uppercase", "marginBottom": "10px"}),
            _rule("X (Strike $):", "Left = OTM puts (below spot). Right = OTM calls (above spot). Center = ATM."),
            _rule("Y (DTE):", "Days to expiration. Front = near-term. Back = longer-dated.", "#fbbf24"),
            _rule("Z (IV %):", "Implied volatility. Higher = options market pricing larger expected moves.", "#8b5cf6"),
            _rule("Green ATM column:", "The at-the-money strike. Skew and term structure are measured relative to ATM IV.", "#69f0ae"),
        ], style={**T.STYLE_CARD, "marginBottom": "12px", "padding": "12px 16px"}),

        html.Div([
            dcc.Graph(figure=fig, config=_cfg),
            html.Div([
                _rule("IV Smile:", "IV rises at both wings vs ATM — OTM options price tail risk. Universal pattern."),
                _rule("Put Skew (left wing higher):", "OTM puts more expensive than OTM calls — typical in equities. Reflects demand for downside hedges.", T.DANGER),
                _rule("Inverted term structure (near > far):", "Short-dated IV above long-dated IV. Common near earnings, macro events, or in elevated-vol regimes.", "#ef4444"),
                _rule("Normal term structure (far > near):", "Long-dated IV above short-dated IV. Default state in calm markets — time uncertainty priced at a premium.", "#3b82f6"),
            ], style={"padding": "8px 4px"}),
        ], style={**T.STYLE_CARD, "marginBottom": "12px", "padding": "14px"}),

        html.Div([
            html.Div("Trade Applications", style={
                "color": T.TEXT_SEC, "fontSize": "11px", "fontWeight": "700",
                "textTransform": "uppercase", "marginBottom": "8px"}),
            _rule("ATM IV = expected move:", "ATM IV × √(DTE/365) × Spot ≈ 1σ implied move. Read the green column.", "#69f0ae"),
            _rule("Elevated skew → put spreads:", "When OTM put IV is abnormally high vs HV, credit put spreads sell the expensive side. The skew shows you which side is overpriced.", T.SUCCESS),
            _rule("Steep term structure → calendars:", "Buy front-month/sell back-month (debit) when near-term IV is depressed. Reverse when inverted (near > far). Surface makes this visible at a glance.", "#fbbf24"),
            _rule("IV trough near ATM → butterflies:", "ATM IV cheapest relative to wings. Long butterfly buys wings, sells ATM — profits if surface flattens or price pins near current level.", T.ACCENT),
        ], style={**T.STYLE_CARD, "padding": "12px 16px"}),
    ], style={"marginTop": "16px"})


# ── Momentum guide ─────────────────────────────────────────────────────────────

def _momentum_guide() -> html.Div:
    """Static illustrative guide for RSI and MACD."""
    _bg  = "#111827"
    _grd = "#1f2937"
    _fnt = dict(family="Inter, sans-serif", color="#9ca3af", size=10)
    _cfg = {"displayModeBar": False, "responsive": True}

    # Synthetic price: uptrend → overbought → pullback → oversold → recovery
    np.random.seed(7)
    n = 90
    segs = np.concatenate([
        np.linspace(100, 128, 35),  # uptrend
        np.linspace(128, 108, 25),  # pullback
        np.linspace(108, 122, 30),  # recovery
    ])
    price = pd.Series(segs + np.random.randn(n) * 1.2)

    delta  = price.diff()
    gain   = delta.clip(lower=0).rolling(14).mean()
    loss   = (-delta.clip(upper=0)).rolling(14).mean()
    rsi    = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    ema12  = price.ewm(span=12).mean()
    ema26  = price.ewm(span=26).mean()
    macd   = ema12 - ema26
    sig    = macd.ewm(span=9).mean()
    hist   = macd - sig

    from plotly.subplots import make_subplots
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
                        row_heights=[0.45, 0.28, 0.27], vertical_spacing=0.04,
                        subplot_titles=["Price", "RSI (14)", "MACD"])
    t = list(range(n))
    fig.add_trace(go.Scatter(x=t, y=price, mode="lines",
                             line=dict(color="#6366f1", width=2), showlegend=False), row=1, col=1)
    fig.add_trace(go.Scatter(x=t, y=rsi, mode="lines",
                             line=dict(color="#fbbf24", width=1.5), showlegend=False), row=2, col=1)
    fig.add_hrect(y0=70, y1=100, row=2, col=1, fillcolor="rgba(239,68,68,0.12)", line_width=0)
    fig.add_hrect(y0=0,  y1=30,  row=2, col=1, fillcolor="rgba(16,185,129,0.12)", line_width=0)
    fig.add_hline(y=70, row=2, col=1, line=dict(color="#ef4444", width=1, dash="dot"))
    fig.add_hline(y=30, row=2, col=1, line=dict(color="#10b981", width=1, dash="dot"))
    fig.add_hline(y=50, row=2, col=1, line=dict(color="#374151", width=0.8, dash="dot"))
    fig.add_trace(go.Scatter(x=t, y=macd, mode="lines",
                             line=dict(color="#6366f1", width=1.5), showlegend=False), row=3, col=1)
    fig.add_trace(go.Scatter(x=t, y=sig, mode="lines",
                             line=dict(color="#fbbf24", width=1.5), showlegend=False), row=3, col=1)
    hist_colors = ["#10b981" if (v is not None and not np.isnan(v) and v >= 0) else "#ef4444"
                   for v in hist.fillna(0)]
    fig.add_trace(go.Bar(x=t, y=hist.fillna(0),
                         marker_color=hist_colors, opacity=0.6, showlegend=False), row=3, col=1)

    # Annotate first bullish MACD cross
    for i in range(1, len(t)):
        if (not pd.isna(macd.iloc[i-1]) and not pd.isna(sig.iloc[i-1])
                and macd.iloc[i-1] < sig.iloc[i-1] and macd.iloc[i] >= sig.iloc[i]):
            fig.add_annotation(x=i, y=float(macd.iloc[i]), xref="x3", yref="y3",
                               text="Bullish↑", showarrow=True, arrowhead=2,
                               arrowcolor="#10b981", font=dict(color="#10b981", size=9),
                               ax=0, ay=-28)
            break
    # Annotate first bearish MACD cross
    for i in range(1, len(t)):
        if (not pd.isna(macd.iloc[i-1]) and not pd.isna(sig.iloc[i-1])
                and macd.iloc[i-1] > sig.iloc[i-1] and macd.iloc[i] <= sig.iloc[i]):
            fig.add_annotation(x=i, y=float(macd.iloc[i]), xref="x3", yref="y3",
                               text="Bearish↓", showarrow=True, arrowhead=2,
                               arrowcolor="#ef4444", font=dict(color="#ef4444", size=9),
                               ax=0, ay=28)
            break

    for i in range(1, 4):
        fig.update_xaxes(gridcolor=_grd, showticklabels=(i == 3), row=i, col=1)
        fig.update_yaxes(gridcolor=_grd, row=i, col=1)
    fig.update_layout(paper_bgcolor=_bg, plot_bgcolor=_bg, font=_fnt,
                      height=400, margin=dict(l=50, r=20, t=35, b=20), showlegend=False)
    for ann in fig.layout.annotations:
        if ann.text in ("Price", "RSI (14)", "MACD"):
            ann.font = dict(size=11, color="#9ca3af")

    def _rule(title, body, color=T.ACCENT):
        return html.Div([
            html.Span(title, style={"color": color, "fontWeight": "700", "fontSize": "12px"}),
            html.Span(f"  {body}", style={"color": "#9ca3af", "fontSize": "12px"}),
        ], style={"marginBottom": "6px"})

    return html.Div([
        html.Div([dcc.Graph(figure=fig, config=_cfg)],
                 style={**T.STYLE_CARD, "marginBottom": "12px", "padding": "14px"}),
        html.Div([
            html.Div("RSI — Relative Strength Index", style={
                "color": T.TEXT_SEC, "fontSize": "11px", "fontWeight": "700",
                "textTransform": "uppercase", "marginBottom": "8px"}),
            _rule("RSI > 70 (red zone):", "Overbought. Momentum stretched upward — watch for RSI turning down as a warning, not an outright sell trigger.", T.DANGER),
            _rule("RSI < 30 (green zone):", "Oversold. Good time to tighten stops on shorts, watch for bounce setups. Not a standalone buy signal.", T.SUCCESS),
            _rule("RSI 50 centerline:", "Crossing 50 from below = bullish momentum shift. Below 50 = bearish regime. More reliable than overbought/oversold alone."),
            _rule("Divergence:", "Price new high + RSI lower high = bearish divergence (momentum fading). Price new low + RSI higher low = bullish divergence. Precedes reversals.", T.WARNING),
        ], style={**T.STYLE_CARD, "marginBottom": "12px", "padding": "12px 16px"}),
        html.Div([
            html.Div("MACD — Moving Average Convergence / Divergence", style={
                "color": T.TEXT_SEC, "fontSize": "11px", "fontWeight": "700",
                "textTransform": "uppercase", "marginBottom": "8px"}),
            _rule("MACD line (blue):", "EMA(12) − EMA(26). Captures short-term vs intermediate momentum."),
            _rule("Signal line (yellow):", "EMA(9) of MACD. Cross above = bullish. Cross below = bearish. Confirmed by histogram direction.", "#fbbf24"),
            _rule("Histogram (green/red):", "MACD − Signal. Expanding = momentum building. Shrinking = momentum fading. Watch for bar shrinkage before price turns.", T.SUCCESS),
            _rule("Zero line cross:", "MACD crossing above zero = uptrend confirmed. Below zero = downtrend confirmed. Slower but more reliable than signal-line crosses."),
            _rule("Caveat:", "MACD generates many false signals in choppy, range-bound markets. Combine with RSI and price structure for confirmation.", T.WARNING),
        ], style={**T.STYLE_CARD, "padding": "12px 16px"}),
    ], style={"marginTop": "16px"})


# ── Yield curve guide ──────────────────────────────────────────────────────────

def _yield_guide() -> html.Div:
    """Static illustrative guide for the Treasury yield curve."""
    _bg  = "#111827"
    _grd = "#1f2937"
    _fnt = dict(family="Inter, sans-serif", color="#9ca3af", size=10)
    _cfg = {"displayModeBar": False, "responsive": True}

    mat = ["3M", "6M", "1Y", "2Y", "5Y", "10Y", "30Y"]
    normal   = [4.8, 4.7, 4.5, 4.3, 4.2, 4.4, 4.6]
    inverted = [5.3, 5.4, 5.2, 5.0, 4.4, 4.1, 4.3]
    flat_h   = [4.9, 4.9, 4.8, 4.7, 4.6, 4.6, 4.7]

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=mat, y=normal, mode="lines+markers",
                             name="Normal (healthy)", line=dict(color="#10b981", width=2),
                             marker=dict(size=7)))
    fig.add_trace(go.Scatter(x=mat, y=inverted, mode="lines+markers",
                             name="Inverted (recession signal)", line=dict(color="#ef4444", width=2),
                             marker=dict(size=7)))
    fig.add_trace(go.Scatter(x=mat, y=flat_h, mode="lines+markers",
                             name="Flat/Humped (transition)", line=dict(color="#fbbf24", width=2),
                             marker=dict(size=7)))
    fig.update_layout(
        paper_bgcolor=_bg, plot_bgcolor=_bg, font=_fnt, height=240,
        title=dict(text="Yield Curve Shapes (synthetic example)",
                   font=dict(size=12, color="#d1d5db"), x=0),
        xaxis=dict(title="Maturity", gridcolor=_grd, color="#9ca3af"),
        yaxis=dict(title="Yield (%)", gridcolor=_grd, color="#9ca3af", tickformat=".1f"),
        legend=dict(orientation="h", x=0, y=1.15, font=dict(size=10), bgcolor="rgba(0,0,0,0)"),
        margin=dict(l=50, r=20, t=55, b=40),
    )

    def _rule(title, body, color=T.ACCENT):
        return html.Div([
            html.Span(title, style={"color": color, "fontWeight": "700", "fontSize": "12px"}),
            html.Span(f"  {body}", style={"color": "#9ca3af", "fontSize": "12px"}),
        ], style={"marginBottom": "6px"})

    return html.Div([
        html.Div([dcc.Graph(figure=fig, config=_cfg)],
                 style={**T.STYLE_CARD, "marginBottom": "12px", "padding": "14px"}),
        html.Div([
            html.Div("Curve Shapes", style={
                "color": T.TEXT_SEC, "fontSize": "11px", "fontWeight": "700",
                "textTransform": "uppercase", "marginBottom": "8px"}),
            _rule("Normal (green, upward):", "Long rates higher than short rates. Economy healthy, investors demand yield premium for time risk. Default state.", T.SUCCESS),
            _rule("Inverted (red):", "Short rates above long rates. Most reliable historical recession predictor. 2s10s negative = watch for credit stress 12–18 months out.", T.DANGER),
            _rule("Flat / Humped (yellow):", "Short and long rates converging. Transition state — watch the 2s10s trend to see which way it resolves.", "#fbbf24"),
        ], style={**T.STYLE_CARD, "marginBottom": "12px", "padding": "12px 16px"}),
        html.Div([
            html.Div("The Key Spreads", style={
                "color": T.TEXT_SEC, "fontSize": "11px", "fontWeight": "700",
                "textTransform": "uppercase", "marginBottom": "8px"}),
            _rule("2s10s (shown in pills):", "10Y minus 2Y. Positive = normal. Goes negative months before recessions. Inversions can last 1–2 years before economic impact."),
            _rule("3m10y:", "Fed's preferred recession indicator. More sensitive to policy rate. First to invert, often first to re-steepen.", "#fbbf24"),
            _rule("Re-steepening from inversion:", "When 2s10s climbs rapidly from deeply negative, it often signals recession is starting — not ending. Counter-intuitive but historically consistent.", T.DANGER),
            _rule("3D Surface:", "Shows how the full curve evolved over 2 years. A 'front-end rise' = Fed tightening. A 'bull steepener' (long end dropping) = market pricing future cuts.", "#3b82f6"),
            _rule("For options traders:", "Steep inverted curve → recession risk elevated → reduce short vol, widen spread widths, avoid iron condors on cyclical sectors.", T.WARNING),
        ], style={**T.STYLE_CARD, "padding": "12px 16px"}),
    ], style={"marginTop": "16px"})


# ── Layout ─────────────────────────────────────────────────────────────────────

def layout() -> html.Div:
    key_loaded = bool(get_polygon_api_key())
    return html.Div([
        html.Div([
            html.H2("Market Data", style={
                "color": T.TEXT_PRIMARY, "fontSize": "1.35rem",
                "fontWeight": "700", "marginBottom": "0",
            }),
            html.Div([
                dbc.Input(
                    id="mkt-apikey", type="password",
                    placeholder="API key loaded ✓" if key_loaded else "Polygon API key",
                    style={"fontSize": "12px", "width": "280px",
                           "backgroundColor": T.BG_ELEVATED,
                           "border": f"1px solid {'#10b981' if key_loaded else T.BORDER}",
                           "color": T.TEXT_PRIMARY},
                ),
                dbc.Input(id="mkt-ticker", type="text", value="F",
                          style={"fontSize": "12px", "width": "80px",
                                 "backgroundColor": T.BG_ELEVATED,
                                 "border": f"1px solid {T.BORDER}", "color": T.TEXT_PRIMARY}),
                dbc.Button("Load", id="mkt-load-btn", color="primary", size="sm",
                           style={"backgroundColor": T.ACCENT, "border": "none", "fontSize": "12px"}),
            ], style={"display": "flex", "gap": "8px", "alignItems": "center"}),
        ], style={"display": "flex", "justifyContent": "space-between",
                  "alignItems": "center", "marginBottom": "16px"}),

        # Quote strip
        dcc.Loading(html.Div(id="mkt-quote-strip"), type="circle", color=T.ACCENT),
        html.Div(style={"height": "12px"}),

        # Charts — all rendered on Load click
        html.Div([
            html.Div([
                html.Div("Price Chart", style={
                    "color": T.TEXT_SEC, "fontSize": "11px", "fontWeight": "600",
                    "textTransform": "uppercase", "letterSpacing": "0.07em",
                }),
                dbc.Switch(
                    id="mkt-eod-toggle",
                    label="EOD History",
                    value=False,
                    style={"color": T.TEXT_MUTED, "fontSize": "12px"},
                ),
            ], style={"display": "flex", "justifyContent": "space-between",
                      "alignItems": "center", "borderBottom": f"1px solid {T.BORDER}",
                      "paddingBottom": "8px", "marginBottom": "12px"}),
            dcc.Loading(html.Div(id="mkt-candle-content",
                                 children=_hint("Loading…")),
                        type="circle", color=T.ACCENT),
        ], style={**T.STYLE_CARD, "marginBottom": "16px"}),
        html.Div([
            html.Div([
                html.Div("Dealer GEX — Gamma Exposure by Strike", style={
                    "color": T.TEXT_SEC, "fontSize": "11px", "fontWeight": "600",
                    "textTransform": "uppercase", "letterSpacing": "0.07em",
                }),
                dbc.Button("How to read this chart",
                           id="mkt-gex-guide-toggle",
                           size="sm", color="link",
                           style={"color": T.ACCENT, "fontSize": "11px",
                                  "padding": "0", "fontWeight": "500"}),
            ], style={"display": "flex", "justifyContent": "space-between",
                      "alignItems": "center", "borderBottom": f"1px solid {T.BORDER}",
                      "paddingBottom": "8px", "marginBottom": "12px"}),
            dcc.Loading(html.Div(id="mkt-gex-content", children=_hint("Loading…")),
                        type="circle", color=T.ACCENT),
            dbc.Collapse(_gex_guide(), id="mkt-gex-guide-collapse", is_open=False),
        ], style={**T.STYLE_CARD, "marginBottom": "16px"}),
        html.Div([
            html.Div([
                html.Div("Volatility Surface 3D", style={
                    "color": T.TEXT_SEC, "fontSize": "11px", "fontWeight": "600",
                    "textTransform": "uppercase", "letterSpacing": "0.07em",
                }),
                dbc.Button("How to read this chart", id="mkt-vol-guide-toggle",
                           size="sm", color="link",
                           style={"color": T.ACCENT, "fontSize": "11px",
                                  "padding": "0", "fontWeight": "500"}),
            ], style={"display": "flex", "justifyContent": "space-between",
                      "alignItems": "center", "borderBottom": f"1px solid {T.BORDER}",
                      "paddingBottom": "8px", "marginBottom": "12px"}),
            dcc.Loading(html.Div(id="mkt-vol-content", children=_hint("Loading…")),
                        type="circle", color=T.ACCENT),
            dbc.Collapse(_vol_surface_guide(), id="mkt-vol-guide-collapse", is_open=False),
        ], style={**T.STYLE_CARD, "marginBottom": "16px"}),
        _section("Market Activity — Top Movers & Dealer GEX",
                 dcc.Loading(html.Div(id="mkt-activity-content",
                                      children=_hint("Loading…")),
                             type="circle", color=T.ACCENT)),
        html.Div([
            html.Div([
                html.Div("Momentum Indicators — RSI & MACD", style={
                    "color": T.TEXT_SEC, "fontSize": "11px", "fontWeight": "600",
                    "textTransform": "uppercase", "letterSpacing": "0.07em",
                }),
                dbc.Button("How to read this chart", id="mkt-momentum-guide-toggle",
                           size="sm", color="link",
                           style={"color": T.ACCENT, "fontSize": "11px",
                                  "padding": "0", "fontWeight": "500"}),
            ], style={"display": "flex", "justifyContent": "space-between",
                      "alignItems": "center", "borderBottom": f"1px solid {T.BORDER}",
                      "paddingBottom": "8px", "marginBottom": "12px"}),
            dcc.Loading(html.Div(id="mkt-momentum-content", children=_hint("Loading…")),
                        type="circle", color=T.ACCENT),
            dbc.Collapse(_momentum_guide(), id="mkt-momentum-guide-collapse", is_open=False),
        ], style={**T.STYLE_CARD, "marginBottom": "16px"}),
        _section("Correlation Analysis", html.Div([
            html.Div([
                html.Label("Compare with:", style={"color": T.TEXT_SEC, "fontSize": "12px",
                                                   "marginRight": "8px"}),
                dbc.Input(id="mkt-corr-ticker", type="text", value="QQQ",
                          style={"width": "80px", "fontSize": "12px",
                                 "backgroundColor": T.BG_ELEVATED,
                                 "border": f"1px solid {T.BORDER}", "color": T.TEXT_PRIMARY}),
                dbc.Button("Run Correlation", id="mkt-corr-run", color="secondary", size="sm",
                           style={"marginLeft": "8px", "fontSize": "12px",
                                  "border": f"1px solid {T.BORDER}"}),
            ], style={"display": "flex", "alignItems": "center", "marginBottom": "12px"}),
            dcc.Loading(html.Div(id="mkt-corr-content"), type="circle", color=T.ACCENT),
        ])),

        html.Div([
            html.Div([
                html.Div("Treasury Term Structure — Yield Curve & 3D Surface (FRED, free)", style={
                    "color": T.TEXT_SEC, "fontSize": "11px", "fontWeight": "600",
                    "textTransform": "uppercase", "letterSpacing": "0.07em",
                }),
                dbc.Button("How to read this chart", id="mkt-yield-guide-toggle",
                           size="sm", color="link",
                           style={"color": T.ACCENT, "fontSize": "11px",
                                  "padding": "0", "fontWeight": "500"}),
            ], style={"display": "flex", "justifyContent": "space-between",
                      "alignItems": "center", "borderBottom": f"1px solid {T.BORDER}",
                      "paddingBottom": "8px", "marginBottom": "12px"}),
            dcc.Loading(html.Div(id="mkt-yield-content", children=_hint("Loading…")),
                        type="circle", color=T.ACCENT),
            dbc.Collapse(_yield_guide(), id="mkt-yield-guide-collapse", is_open=False),
        ], style={**T.STYLE_CARD, "marginBottom": "16px"}),

        # ── Market Screener ──────────────────────────────────────────────────────
        html.Div([
            html.Div([
                html.Div("Market Screener", style={
                    "color": T.TEXT_SEC, "fontSize": "11px", "fontWeight": "600",
                    "textTransform": "uppercase", "letterSpacing": "0.07em",
                }),
                html.Div(
                    [dbc.Button(
                        opt["label"],
                        id={"type": "scr-univ-btn", "index": opt["value"]},
                        size="sm",
                        style={
                            "fontSize": "12px", "fontWeight": "500",
                            "padding": "4px 12px",
                            "backgroundColor": T.ACCENT if opt["value"] == _SCR_DEFAULT_UNIVERSE else T.BG_ELEVATED,
                            "border": f"1px solid {T.ACCENT if opt['value'] == _SCR_DEFAULT_UNIVERSE else T.BORDER}",
                            "color": T.TEXT_PRIMARY,
                            "borderRadius": "6px",
                        },
                    ) for opt in _SCR_UNIVERSE_OPTIONS],
                    style={"display": "flex", "gap": "6px"},
                ),
                dcc.Store(id="mkt-scr-universe", data=_SCR_DEFAULT_UNIVERSE),
            ], style={
                "display": "flex", "justifyContent": "space-between",
                "alignItems": "center",
                "borderBottom": f"1px solid {T.BORDER}",
                "paddingBottom": "8px", "marginBottom": "16px",
            }),

            dcc.Loading(type="circle", color=T.ACCENT, children=html.Div([
                # Row 1: Movers full width
                html.Div([
                    html.Div("Movers", style={"color": T.TEXT_MUTED, "fontSize": "11px",
                                              "fontWeight": "600", "marginBottom": "6px",
                                              "borderLeft": f"3px solid {T.ACCENT}",
                                              "paddingLeft": "8px"}),
                    dcc.Graph(id="mkt-scr-movers-fig", figure=_scr_empty_fig(),
                              config=_SCR_CFG),
                ], style={"marginBottom": "16px"}),
                # Row 2: Momentum | Volatility
                html.Div([
                    html.Div([
                        html.Div("Momentum — top 15 by absolute 20d return",
                                 style={"color": T.TEXT_MUTED, "fontSize": "11px",
                                        "fontWeight": "600", "marginBottom": "6px",
                                        "borderLeft": f"3px solid {T.ACCENT}",
                                        "paddingLeft": "8px"}),
                        dcc.Graph(id="mkt-scr-mom-fig", figure=_scr_empty_fig(),
                                  config=_SCR_CFG, style={"height": "420px"}),
                    ]),
                    html.Div([
                        html.Div("Volatility — HV20 vs IV (amber = IV > 1.5× HV)",
                                 style={"color": T.TEXT_MUTED, "fontSize": "11px",
                                        "fontWeight": "600", "marginBottom": "6px",
                                        "borderLeft": f"3px solid {T.ACCENT}",
                                        "paddingLeft": "8px"}),
                        dcc.Graph(id="mkt-scr-vol-fig", figure=_scr_empty_fig(),
                                  config=_SCR_CFG, style={"height": "420px"}),
                    ]),
                ], style={"display": "grid", "gridTemplateColumns": "1fr 1fr",
                          "gap": "16px", "marginBottom": "16px"}),
                # Row 3: Volume Alerts
                html.Div([
                    html.Div("Volume Alerts — today vs 20-day average",
                             style={"color": T.TEXT_MUTED, "fontSize": "11px",
                                    "fontWeight": "600", "marginBottom": "6px",
                                    "borderLeft": f"3px solid {T.ACCENT}",
                                    "paddingLeft": "8px"}),
                    dcc.Graph(id="mkt-scr-volalert-fig", figure=_scr_empty_fig(),
                              config=_SCR_CFG),
                ]),
            ])),
        ], style={**T.STYLE_CARD, "marginBottom": "16px"}),

        dcc.Store(id="mkt-ticker-store", data="F"),
        dcc.Store(id="mkt-apikey-store", data=get_polygon_api_key()),
    ], style=T.STYLE_PAGE)


# ── Load button: quote strip + store ─────────────────────────────────────────

@callback(
    Output("mkt-ticker-store", "data"),
    Output("mkt-apikey-store", "data"),
    Output("mkt-quote-strip",  "children"),
    Input("mkt-load-btn",      "n_clicks"),
    State("mkt-ticker",        "value"),
    State("mkt-apikey",        "value"),
    prevent_initial_call=True,
)
def store_and_quote(n_clicks, ticker, user_key):
    ticker  = (ticker or "SPY").upper().strip()
    api_key = get_polygon_api_key(user_key or "")

    if not api_key:
        return ticker, "", html.P("No Polygon API key found. Set POLYGON_API_KEY in .env or enter above.",
                                  style={"color": T.DANGER, "fontSize": "13px"})

    try:
        c = _polygon_client(api_key)
        snap = c._get(f"/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}", {})
        q    = snap.get("ticker", {})
        day  = q.get("day") or {}
        prev = q.get("prevDay") or {}
        price   = day.get("c") or 0
        open_p  = day.get("o") or 0
        chg     = price - open_p if price and open_p else 0
        chg_pct = chg / open_p * 100 if open_p else 0
        hi      = day.get("h") or 0
        lo      = day.get("l") or 0
        vol     = int(day.get("v") or 0)
        vwap    = day.get("vw") or 0
        prev_c  = prev.get("c") or 0
        chg_prev = (price - prev_c) if price and prev_c else 0

        strip = html.Div([
            _pill("Price",     f"${price:,.2f}" if price else "—",
                  T.SUCCESS if chg_prev >= 0 else T.DANGER),
            _pill("Change",    f"{chg_prev:+.2f} ({chg_prev/prev_c*100:+.1f}%)" if prev_c else "—",
                  T.SUCCESS if chg_prev >= 0 else T.DANGER),
            _pill("Volume",    f"{vol:,}" if vol else "—"),
            _pill("VWAP",      f"${vwap:,.2f}" if vwap else "—"),
            _pill("Day High",  f"${hi:,.2f}" if hi else "—"),
            _pill("Day Low",   f"${lo:,.2f}" if lo else "—"),
            _pill("Prev Close",f"${prev_c:,.2f}" if prev_c else "—"),
        ], style={"display": "flex", "gap": "10px", "flexWrap": "wrap", "marginBottom": "4px"})
    except Exception as e:
        strip = html.P(f"Quote error: {e}", style={"color": T.WARNING, "fontSize": "12px"})

    return ticker, api_key, strip


# ── Intraday chart ─────────────────────────────────────────────────────────────

def _render_intraday(ticker: str, api_key: str):
    from plotly.subplots import make_subplots
    import datetime as _dt
    df = _fetch_intraday(ticker, api_key)
    if df.empty:
        return html.P(
            "No intraday data yet — market may be closed or pre-market.",
            style={"color": T.WARNING, "fontSize": "12px"},
        )

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

    # Price area line
    fig.add_trace(go.Scatter(
        x=df["datetime"], y=close,
        name="Price",
        line=dict(color=line_color, width=2),
        fill="tozeroy", fillcolor=fill_color,
        hovertemplate="%{x|%H:%M}  $%{y:.2f}<extra></extra>",
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
        template="plotly_dark", paper_bgcolor=T.BG_CARD, plot_bgcolor=T.BG_CARD,
        font=dict(color=T.TEXT_SEC, size=11),
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
    fig.update_yaxes(gridcolor=T.BORDER)
    fig.update_xaxes(gridcolor=T.BORDER)
    fig.update_yaxes(title_text="Vol", row=2, col=1)

    chg_str = f"{chg:+.2f} ({chg_pct:+.1f}%)"
    return html.Div([
        html.Div(
            f"${last_px:.2f}  {chg_str}  (from open ${start_px:.2f})",
            style={"color": line_color, "fontSize": "13px",
                   "fontWeight": "600", "marginBottom": "8px"},
        ),
        dcc.Graph(figure=fig, config={"displayModeBar": False}),
    ])


# ── Candlestick / Price chart (intraday default, EOD toggle) ──────────────────

@callback(
    Output("mkt-candle-content", "children"),
    Input("mkt-ticker-store",    "data"),
    Input("mkt-eod-toggle",      "value"),
    State("mkt-apikey-store",    "data"),
)
def render_candle(ticker, eod_mode, api_key):
    if not ticker:
        return _hint("Loading…")
    if not api_key:
        return _hint("No API key — enter above and click Load")

    # ── Intraday (default) ───────────────────────────────────────────────────
    if not eod_mode:
        try:
            return _render_intraday(ticker, api_key)
        except Exception as e:
            return html.P(f"Intraday error: {e}", style={"color": T.DANGER, "fontSize": "12px"})

    # ── EOD history ──────────────────────────────────────────────────────────
    try:
        from plotly.subplots import make_subplots
        bars = _fetch_bars(ticker or "SPY", api_key)
        if bars.empty:
            return html.P("No price data from Polygon.", style={"color": T.WARNING})
        if "date" not in bars.columns and bars.index.name == "date":
            bars = bars.reset_index()
        bars["date"] = pd.to_datetime(bars["date"])

        # ── Indicators ─────────────────────────────────────────────────────
        c = pd.to_numeric(bars["close"], errors="coerce")
        bars["ema20"]  = c.ewm(span=20, adjust=False).mean()
        bars["ema50"]  = c.ewm(span=50, adjust=False).mean()
        bars["bb_mid"] = c.rolling(20).mean()
        bars["bb_std"] = c.rolling(20).std()
        bars["bb_hi"]  = bars["bb_mid"] + 2 * bars["bb_std"]
        bars["bb_lo"]  = bars["bb_mid"] - 2 * bars["bb_std"]
        delta = c.diff()
        gain  = delta.clip(lower=0).rolling(14).mean()
        loss  = (-delta.clip(upper=0)).rolling(14).mean()
        bars["rsi"] = 100 - 100 / (1 + gain / loss.replace(0, np.nan))

        fig = make_subplots(
            rows=3, cols=1, shared_xaxes=True,
            row_heights=[0.60, 0.20, 0.20],
            vertical_spacing=0.02,
        )

        # Row 1 — Candlestick + overlays
        fig.add_trace(go.Candlestick(
            x=bars["date"], open=bars["open"], high=bars["high"],
            low=bars["low"], close=bars["close"],
            name=ticker,
            increasing_line_color=T.SUCCESS, decreasing_line_color=T.DANGER,
            increasing_fillcolor=T.SUCCESS, decreasing_fillcolor=T.DANGER,
        ), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=bars["date"], y=bars["bb_hi"], name="BB Upper",
            line=dict(color="#546e7a", width=1, dash="dot"), showlegend=False,
        ), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=bars["date"], y=bars["bb_lo"], name="BB Lower",
            line=dict(color="#546e7a", width=1, dash="dot"),
            fill="tonexty", fillcolor="rgba(84,110,122,0.10)", showlegend=False,
        ), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=bars["date"], y=bars["ema20"], name="EMA 20",
            line=dict(color="#ffa726", width=1.5),
        ), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=bars["date"], y=bars["ema50"], name="EMA 50",
            line=dict(color="#ab47bc", width=1.5),
        ), row=1, col=1)

        # Row 2 — RSI
        fig.add_trace(go.Scatter(
            x=bars["date"], y=bars["rsi"], name="RSI 14",
            line=dict(color="#69f0ae", width=1.5), showlegend=False,
        ), row=2, col=1)
        fig.add_hrect(y0=70, y1=100, row=2, col=1,
                      fillcolor="rgba(239,83,80,0.08)", line_width=0)
        fig.add_hrect(y0=0,  y1=30,  row=2, col=1,
                      fillcolor="rgba(38,166,154,0.08)", line_width=0)
        fig.add_hline(y=70, row=2, col=1, line=dict(color="#ef5350", width=1, dash="dot"))
        fig.add_hline(y=30, row=2, col=1, line=dict(color="#26a69a", width=1, dash="dot"))

        # Row 3 — Volume
        vol_colors = [T.SUCCESS if float(cl) >= float(op) else T.DANGER
                      for cl, op in zip(bars["close"], bars["open"])]
        if "volume" in bars.columns:
            fig.add_trace(go.Bar(
                x=bars["date"], y=pd.to_numeric(bars["volume"], errors="coerce"),
                name="Volume", marker_color=vol_colors, opacity=0.6, showlegend=False,
            ), row=3, col=1)

        fig.update_layout(
            template="plotly_dark", paper_bgcolor=T.BG_CARD, plot_bgcolor=T.BG_CARD,
            font=dict(color=T.TEXT_SEC, size=11),
            title=dict(text=f"{ticker} — Price & Indicators ({len(bars)} bars)",
                       font=dict(size=13, color=T.TEXT_SEC)),
            height=600,
            hovermode="x unified",
            xaxis_rangeslider_visible=False,
            xaxis3=dict(
                gridcolor=T.BORDER,
                rangeselector=dict(
                    bgcolor=T.BG_ELEVATED, activecolor=T.ACCENT,
                    font=dict(color=T.TEXT_PRIMARY, size=11),
                    buttons=[
                        dict(count=1, label="1M", step="month", stepmode="backward"),
                        dict(count=3, label="3M", step="month", stepmode="backward"),
                        dict(count=6, label="6M", step="month", stepmode="backward"),
                        dict(count=1, label="1Y", step="year",  stepmode="backward"),
                        dict(step="all", label="All"),
                    ],
                ),
            ),
            legend=dict(orientation="h", x=0, y=1.02,
                        font=dict(size=11, color=T.TEXT_SEC),
                        bgcolor="rgba(0,0,0,0)"),
            margin=dict(l=0, r=0, t=50, b=0),
        )
        fig.update_yaxes(gridcolor=T.BORDER)
        fig.update_xaxes(gridcolor=T.BORDER)
        fig.update_yaxes(title_text="RSI", row=2, col=1, range=[0, 100],
                         tickvals=[30, 50, 70])
        fig.update_yaxes(title_text="Vol", row=3, col=1)

        return dcc.Graph(figure=fig, config={"displayModeBar": True,
                                             "modeBarButtonsToAdd": ["drawline", "drawopenpath"]})
    except Exception as e:
        return html.P(f"Error: {e}", style={"color": T.DANGER, "fontSize": "12px"})


# ── Treasury Term Structure ────────────────────────────────────────────────────

@callback(
    Output("mkt-yield-content", "children"),
    Input("mkt-ticker-store",   "data"),
)
def render_yield(_ticker):
    if _ticker is None:
        return _hint("Click Load to fetch from FRED")
    try:
        return _render_yield_inner()
    except Exception as e:
        return html.P(f"Yield curve error: {e}", style={"color": T.DANGER, "fontSize": "12px"})


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
            dbc.Col(dcc.Graph(figure=fig_c, config={"displayModeBar": False}), width=6),
            dbc.Col(dcc.Graph(figure=fig_h, config={"displayModeBar": False}), width=6),
        ], className="g-3", style={"marginBottom": "16px"}),
        html.Div("3D Yield Surface (2y lookback, weekly)",
                 style={"color": T.TEXT_SEC, "fontSize": "11px", "fontWeight": "600",
                        "textTransform": "uppercase", "marginBottom": "8px"}),
        g3d,
        html.P("Source: FRED (St. Louis Fed) — free, cached per session.",
               style={"color": T.TEXT_MUTED, "fontSize": "11px", "marginTop": "6px"}),
    ])


# ── Volatility Surface 3D ──────────────────────────────────────────────────────

@callback(
    Output("mkt-vol-content",  "children"),
    Input("mkt-ticker-store",  "data"),
    State("mkt-apikey-store",  "data"),
)
def render_vol_surface(ticker, api_key):
    if not ticker:
        return _hint("Loading…")
    if not api_key:
        return _hint("No API key — enter above and click Load")
    try:
        import datetime as _dt
        from data.loader import fetch_live_vol_surface
        c     = _polygon_client(api_key)
        today = _dt.date.today()
        agg   = c._get(f"/v2/aggs/ticker/{ticker}/prev", {"adjusted": "true"})
        res   = agg.get("results", [])
        if not res:
            return html.P(f"Could not fetch spot price for {ticker}.", style={"color": T.WARNING})
        spot  = float(res[0]["c"])

        surf_df = fetch_live_vol_surface(c, ticker, spot, min_dte=7, max_dte=180, step_pct=0.05)
        if surf_df is None or surf_df.empty:
            return html.P("No vol surface data.", style={"color": T.WARNING})

        strikes = np.array(sorted(surf_df["strike"].unique()))
        dtes    = np.array(sorted(surf_df["dte"].unique()))
        iv_z    = np.full((len(dtes), len(strikes)), np.nan)
        s_idx   = {s: i for i, s in enumerate(strikes)}
        d_idx   = {d: i for i, d in enumerate(dtes)}
        for _, row in surf_df.iterrows():
            iv = row.get("iv")
            if iv and float(iv) > 0:
                iv_z[d_idx[row["dte"]], s_idx[row["strike"]]] = float(iv)

        from scipy.interpolate import griddata
        di, si = np.meshgrid(np.arange(len(dtes)), np.arange(len(strikes)), indexing="ij")
        valid   = ~np.isnan(iv_z)
        if valid.sum() >= 4:
            pts    = np.column_stack([di[valid], si[valid]])
            all_pt = np.column_stack([di.ravel(), si.ravel()])
            iv_z   = griddata(pts, iv_z[valid], all_pt, method="nearest").reshape(iv_z.shape)

        # ── Wireframe mesh (matches Streamlit version) ──────────────────────
        WIRE  = "#3a5a8a"
        ATM_C = "#69f0ae"
        z_pct = iv_z * 100
        atm_j = int(np.argmin(np.abs(strikes - spot))) if spot else None

        fig = go.Figure()
        # Lines along strike axis (one per DTE row)
        for i, dte in enumerate(dtes):
            fig.add_trace(go.Scatter3d(
                x=strikes.tolist(), y=[float(dte)]*len(strikes), z=z_pct[i].tolist(),
                mode="lines", line=dict(color=WIRE, width=2), showlegend=False,
                hovertemplate=f"DTE {int(dte)}d — Strike $%{{x:.0f}} — IV %{{z:.1f}}%<extra></extra>",
            ))
        # Lines along DTE axis (one per strike column)
        for j, strike in enumerate(strikes):
            is_atm = (atm_j is not None and j == atm_j)
            fig.add_trace(go.Scatter3d(
                x=[float(strike)]*len(dtes), y=dtes.tolist(), z=z_pct[:, j].tolist(),
                mode="lines",
                line=dict(color=ATM_C if is_atm else WIRE, width=5 if is_atm else 2),
                showlegend=False,
                hovertemplate=(("⚡ ATM — " if is_atm else "") +
                               f"Strike ${strike:.0f} — DTE %{{y}}d — IV %{{z:.1f}}%<extra></extra>"),
            ))
        # ATM column markers only
        axv, ayv, azv = [], [], []
        for i in range(len(dtes)):
            if atm_j is not None:
                axv.append(float(strikes[atm_j])); ayv.append(float(dtes[i])); azv.append(float(z_pct[i, atm_j]))
        if axv:
            fig.add_trace(go.Scatter3d(
                x=axv, y=ayv, z=azv, mode="markers",
                marker=dict(size=5, color=ATM_C, symbol="circle"),
                showlegend=False,
                hovertemplate="⚡ ATM $%{x:.0f} — DTE %{y}d — IV %{z:.1f}%<extra></extra>",
            ))

        _ax = dict(gridcolor="#2a3050", backgroundcolor="#0c1020",
                   color="#e0e0e0", showbackground=True,
                   tickfont=dict(color="#c0c8d8", size=13))
        atm_label = f"  ATM ≈ ${spot:.2f}" if spot else ""
        fig.update_layout(
            paper_bgcolor="#0e1117", font=dict(color="#e0e0e0", family="monospace", size=13),
            title=dict(text=f"{ticker} Volatility Surface{atm_label}  ·  <span style='color:#69f0ae'>green = ATM</span>",
                       font=dict(size=15, color="#e0e0e0")),
            scene=dict(
                domain=dict(x=[0, 0.9], y=[0, 1]),
                xaxis=dict(**_ax, title=dict(text="Strike ($)", font=dict(color="#e0e0e0", size=13))),
                yaxis=dict(**_ax, title=dict(text="DTE (days)", font=dict(color="#e0e0e0", size=13))),
                zaxis=dict(**_ax, title=dict(text="IV (%)",     font=dict(color="#e0e0e0", size=13))),
                bgcolor="#0c1020",
                camera=dict(eye=dict(x=1.6, y=-1.6, z=0.9)),
                aspectmode="manual", aspectratio=dict(x=2.0, y=1.0, z=0.6),
            ),
            height=650, margin=dict(l=0, r=0, t=50, b=0),
        )
        return dcc.Graph(figure=fig, config={"displayModeBar": True})
    except Exception as e:
        return html.P(f"Vol surface error: {e}", style={"color": T.DANGER, "fontSize": "12px"})


# ── Market Activity ────────────────────────────────────────────────────────────

@callback(
    Output("mkt-activity-content", "children"),
    Input("mkt-ticker-store",      "data"),
    State("mkt-apikey-store",      "data"),
)
def render_activity(ticker, api_key):
    if not ticker:
        return _hint("Loading…")
    if not api_key:
        return _hint("No API key — enter above and click Load")
    try:
        c = _polygon_client(api_key)
        gainers = c._get("/v2/snapshot/locale/us/markets/stocks/gainers").get("tickers", [])
        losers  = c._get("/v2/snapshot/locale/us/markets/stocks/losers").get("tickers", [])
        rows = []
        for snap in gainers + losers:
            rows.append({
                "ticker":     snap.get("ticker", ""),
                "price":      snap.get("day", {}).get("c") or 0,
                "change_pct": snap.get("todaysChangePerc", 0),
                "volume":     snap.get("day", {}).get("v") or 0,
            })
        movers_df = pd.DataFrame(rows) if rows else pd.DataFrame()
    except Exception as e:
        return html.P(f"Movers error: {e}", style={"color": T.DANGER, "fontSize": "12px"})

    # GEX
    try:
        import datetime as _dt
        agg  = c._get(f"/v2/aggs/ticker/{ticker}/range/1/day",
                      {"from": str(_dt.date.today()), "to": str(_dt.date.today()), "limit": 1})
        res  = agg.get("results", [])
        spot = float(res[0]["c"]) if res else 500.0

        exp_to = (_dt.date.today() + _dt.timedelta(days=60)).strftime("%Y-%m-%d")
        results, url = [], f"/v3/snapshot/options/{ticker}"
        params = {
            "expiration_date.gte": str(_dt.date.today()),
            "expiration_date.lte": exp_to,
            "strike_price.gte": round(spot * 0.85, 0),
            "strike_price.lte": round(spot * 1.15, 0),
            "limit": 250,
        }
        while url:
            data = c._get(url, params)
            results.extend(data.get("results", []))
            nxt = (data.get("next_url") or "").replace(c.BASE, "")
            url, params = nxt or None, {}

        from collections import defaultdict
        gex: dict = defaultdict(lambda: {"call_gex": 0.0, "put_gex": 0.0})
        for r in results:
            gamma = (r.get("greeks") or {}).get("gamma")
            oi    = r.get("open_interest")
            if not gamma or not oi:
                continue
            strike = (r.get("details") or {}).get("strike_price")
            ctype  = (r.get("details") or {}).get("contract_type", "").lower()
            val    = float(gamma) * float(oi) * 100 * (spot**2) / 1e9
            if ctype == "call":
                gex[strike]["call_gex"] += val
            elif ctype == "put":
                gex[strike]["put_gex"]  -= val

        gex_df = pd.DataFrame([
            {"strike": k, "call_gex": v["call_gex"], "put_gex": v["put_gex"],
             "net_gex": v["call_gex"] + v["put_gex"]}
            for k, v in sorted(gex.items())
        ]) if gex else pd.DataFrame()
    except Exception:
        gex_df, spot = pd.DataFrame(), 500.0

    if movers_df.empty:
        return html.P("No movers data from Polygon.", style={"color": T.WARNING})

    ms = movers_df.sort_values("change_pct", ascending=True)
    fig_m = go.Figure(go.Bar(
        x=ms["change_pct"], y=ms["ticker"], orientation="h",
        marker_color=[T.SUCCESS if v >= 0 else T.DANGER for v in ms["change_pct"]],
        hovertemplate="%{y}: %{x:+.2f}%<extra></extra>",
    ))
    fig_m.add_vline(x=0, line=dict(color=T.BORDER_BRT, width=1))
    fig_m.update_layout(**_DARK, height=320,
                        title=dict(text="Top Movers (Polygon)", font=dict(size=13, color=T.TEXT_SEC)),
                        xaxis=dict(ticksuffix="%", gridcolor=T.BORDER),
                        yaxis=dict(gridcolor=T.BORDER), showlegend=False)

    children = [
        html.Div([
            _pill("Advancers", str(int((movers_df["change_pct"]>0).sum())), T.SUCCESS),
            _pill("Decliners", str(int((movers_df["change_pct"]<0).sum())), T.DANGER),
        ], style={"display": "flex", "gap": "10px", "marginBottom": "12px"}),
        dcc.Graph(figure=fig_m, config={"displayModeBar": False}),
    ]

    if not gex_df.empty:
        net = float(gex_df["net_gex"].sum())
        fig_g = go.Figure()
        fig_g.add_trace(go.Bar(x=gex_df["strike"], y=gex_df["call_gex"],
                               name="Call GEX", marker_color=T.SUCCESS, opacity=0.7))
        fig_g.add_trace(go.Bar(x=gex_df["strike"], y=gex_df["put_gex"],
                               name="Put GEX",  marker_color=T.DANGER, opacity=0.7))
        fig_g.add_trace(go.Scatter(x=gex_df["strike"], y=gex_df["net_gex"],
                                   mode="lines+markers", name="Net GEX",
                                   line=dict(color=T.ACCENT, width=2)))
        fig_g.add_vline(x=spot, line=dict(color=T.WARNING, width=1.5, dash="dash"),
                        annotation_text=f"Spot ${spot:.0f}", annotation_font_color=T.WARNING)
        fig_g.add_hline(y=0, line=dict(color=T.BORDER_BRT, width=1))
        fig_g.update_layout(**_DARK, height=300, barmode="relative",
                            title=dict(text=f"Dealer GEX — {ticker} ($B)",
                                       font=dict(size=13, color=T.TEXT_SEC)),
                            xaxis=dict(tickprefix="$", gridcolor=T.BORDER),
                            yaxis=dict(title="GEX ($B)", gridcolor=T.BORDER, zeroline=False),
                            legend=dict(orientation="h", y=-0.2, bgcolor="rgba(0,0,0,0)"))
        children += [
            html.Div(style={"height": "12px"}),
            _pill("Net GEX ($B)", f"{net:+.3f}", T.SUCCESS if net >= 0 else T.DANGER),
            html.Div(style={"height": "8px"}),
            dcc.Graph(figure=fig_g, config={"displayModeBar": False}),
        ]

    return html.Div(children)


# ── Dealer GEX ────────────────────────────────────────────────────────────────

@callback(
    Output("mkt-gex-content",   "children"),
    Input("mkt-ticker-store",   "data"),
    State("mkt-apikey-store",   "data"),
)
def render_gex(ticker, api_key):
    if not ticker:
        return _hint("Loading…")
    if not api_key:
        return _hint("No API key — enter above and click Load")
    try:
        import datetime as _dt
        from collections import defaultdict
        c    = _polygon_client(api_key)
        agg  = c._get(f"/v2/aggs/ticker/{ticker}/prev", {"adjusted": "true"})
        res  = agg.get("results", [])
        if not res:
            return html.P(f"Could not fetch spot price for {ticker}.", style={"color": T.WARNING})
        spot = float(res[0]["c"])

        exp_to = (_dt.date.today() + _dt.timedelta(days=60)).strftime("%Y-%m-%d")
        results, url = [], f"/v3/snapshot/options/{ticker}"
        params = {
            "expiration_date.gte": str(_dt.date.today()),
            "expiration_date.lte": exp_to,
            "strike_price.gte":    round(spot * 0.85, 0),
            "strike_price.lte":    round(spot * 1.15, 0),
            "limit": 250,
        }
        while url:
            data   = c._get(url, params)
            results.extend(data.get("results", []))
            nxt    = (data.get("next_url") or "").replace(c.BASE, "")
            url, params = (nxt or None), {}

        if not results:
            return html.P("No options data for GEX calculation.", style={"color": T.WARNING})

        # ── Aggregate GEX and OI per strike ───────────────────────────────────
        gex: dict = defaultdict(lambda: {"call_gex": 0.0, "put_gex": 0.0,
                                          "call_oi": 0,   "put_oi": 0})
        atm_opts = []   # (iv, dte) for σ computation
        for r in results:
            details = r.get("details") or {}
            strike  = details.get("strike_price")
            ctype   = details.get("contract_type", "").lower()
            exp     = details.get("expiration_date", "")
            if not strike:
                continue
            gamma = (r.get("greeks") or {}).get("gamma")
            oi    = r.get("open_interest") or 0
            iv    = r.get("implied_volatility")
            if gamma and oi:
                val = float(gamma) * float(oi) * 100 * (spot ** 2) / 1e9
                if ctype == "call":
                    gex[strike]["call_gex"] += val
                elif ctype == "put":
                    gex[strike]["put_gex"]  -= val
            if ctype == "call":
                gex[strike]["call_oi"] += int(oi)
            elif ctype == "put":
                gex[strike]["put_oi"]  += int(oi)
            # collect near-ATM options for σ
            if iv and abs(float(strike) - spot) / spot < 0.03 and exp:
                try:
                    dte_r = (_dt.date.fromisoformat(exp) - _dt.date.today()).days
                    if dte_r > 0:
                        atm_opts.append((float(iv), dte_r))
                except Exception:
                    pass

        if not gex:
            return html.P("Options data present but no gamma/OI available.",
                          style={"color": T.WARNING})

        gex_df = pd.DataFrame([
            {"strike": k, "call_gex": v["call_gex"], "put_gex": v["put_gex"],
             "net_gex": v["call_gex"] + v["put_gex"],
             "call_oi": v["call_oi"],  "put_oi": v["put_oi"]}
            for k, v in sorted(gex.items())
        ])
        net_total  = float(gex_df["net_gex"].sum())
        call_total = float(gex_df["call_gex"].sum())
        put_total  = float(gex_df["put_gex"].sum())

        # ── Key levels ────────────────────────────────────────────────────────
        # ZERO G — flip where cumulative GEX crosses zero
        gex_s    = gex_df.sort_values("strike")
        cum_gex  = gex_s["net_gex"].cumsum()
        flip_mask = (cum_gex.shift(1, fill_value=cum_gex.iloc[0]) * cum_gex) < 0
        zero_g   = float(gex_s.loc[flip_mask, "strike"].iloc[0]) if flip_mask.any() else None

        # G1 — highest absolute net GEX above spot
        above = gex_df[gex_df["strike"] > spot]
        g1 = float(above.loc[above["net_gex"].abs().idxmax(), "strike"]) if not above.empty else None
        g1_val = float(above.loc[above["net_gex"].abs().idxmax(), "net_gex"]) if not above.empty else None

        # G2 — highest absolute net GEX below spot
        below = gex_df[gex_df["strike"] < spot]
        g2 = float(below.loc[below["net_gex"].abs().idxmax(), "strike"]) if not below.empty else None
        g2_val = float(below.loc[below["net_gex"].abs().idxmax(), "net_gex"]) if not below.empty else None

        # σ — 1 std dev implied move from nearest-expiry ATM IV
        sigma = None
        if atm_opts:
            nearest_dte = min(d for _, d in atm_opts)
            near_ivs = [iv for iv, d in atm_opts if d == nearest_dte]
            if near_ivs:
                atm_iv = float(np.median(near_ivs))
                sigma  = spot * atm_iv * math.sqrt(nearest_dte / 365)

        sig_hi = spot + sigma if sigma else None
        sig_lo = spot - sigma if sigma else None

        # ── GEX by strike chart ───────────────────────────────────────────────
        fig = go.Figure()

        # Dealer cluster zones (shaded bands)
        y_rng = max(gex_df[["call_gex","put_gex","net_gex"]].abs().max()) * 1.3
        if g1 is not None and sig_hi is not None:
            fig.add_hrect(y0=-y_rng, y1=y_rng,
                          x0=min(g1, sig_hi), x1=max(g1, sig_hi),
                          fillcolor="rgba(239,68,68,0.07)", line_width=0,
                          annotation_text="DEALER CLUSTER",
                          annotation_font_color="rgba(239,68,68,0.5)",
                          annotation_font_size=9)
        if g2 is not None and sig_lo is not None:
            fig.add_hrect(y0=-y_rng, y1=y_rng,
                          x0=min(g2, sig_lo), x1=max(g2, sig_lo),
                          fillcolor="rgba(16,185,129,0.07)", line_width=0,
                          annotation_text="DEALER CLUSTER",
                          annotation_font_color="rgba(16,185,129,0.5)",
                          annotation_font_size=9,
                          annotation_position="bottom right")

        fig.add_trace(go.Bar(x=gex_df["strike"], y=gex_df["call_gex"],
                             name="Call GEX", marker_color=T.SUCCESS, opacity=0.8,
                             hovertemplate="$%{x:.0f}  Call: %{y:+.4f}B<extra></extra>"))
        fig.add_trace(go.Bar(x=gex_df["strike"], y=gex_df["put_gex"],
                             name="Put GEX", marker_color=T.DANGER, opacity=0.8,
                             hovertemplate="$%{x:.0f}  Put: %{y:+.4f}B<extra></extra>"))
        fig.add_trace(go.Bar(x=gex_df["strike"], y=gex_df["net_gex"],
                             name="Net GEX",
                             marker_color=[T.ACCENT if v >= 0 else "#7c3aed"
                                           for v in gex_df["net_gex"]],
                             opacity=0.55,
                             hovertemplate="$%{x:.0f}  Net: %{y:+.4f}B<extra></extra>"))

        # Vertical reference lines
        def _vl(x, color, text, pos="top left", width=1.5, dash="dot"):
            fig.add_vline(x=x, line=dict(color=color, width=width, dash=dash),
                          annotation_text=text, annotation_font_color=color,
                          annotation_font_size=10, annotation_position=pos)

        _vl(spot,  T.WARNING,  f"Spot ${spot:.0f}", "top right", dash="dash")
        if zero_g: _vl(zero_g, "#fb923c", f"ZERO G  ${zero_g:.0f}", "bottom left")
        if g1:     _vl(g1,     "#ef4444", f"G1  ${g1:.0f}", "top left")
        if g2:     _vl(g2,     "#10b981", f"G2  ${g2:.0f}", "bottom left")
        if sig_hi: _vl(sig_hi, "#8b5cf6", f"σ  ${sig_hi:.0f}", "top right")
        if sig_lo: _vl(sig_lo, "#8b5cf6", f"σ  ${sig_lo:.0f}", "bottom right")

        fig.add_hline(y=0, line=dict(color=T.BORDER_BRT, width=1))
        fig.update_layout(
            **_DARK, height=400, barmode="overlay",
            title=dict(text=f"{ticker} — GEX by Strike  ·  ±15% spot  ·  next 60 DTE",
                       font=dict(size=13, color=T.TEXT_SEC)),
            xaxis=dict(tickprefix="$", gridcolor=T.BORDER),
            yaxis=dict(title="GEX ($B)", gridcolor=T.BORDER, zeroline=False),
            legend=dict(orientation="h", x=0, y=1.08, bgcolor="rgba(0,0,0,0)"),
            margin=dict(l=0, r=0, t=50, b=0),
        )

        # ── Open Interest by Strike chart ─────────────────────────────────────
        oi_df = gex_df.sort_values("strike")
        fig_oi = go.Figure()
        fig_oi.add_trace(go.Bar(
            y=oi_df["strike"], x=oi_df["call_oi"], orientation="h",
            name="Call OI", marker_color=T.SUCCESS, opacity=0.8,
            hovertemplate="$%{y:.0f}  Call OI: %{x:,.0f}<extra></extra>",
        ))
        fig_oi.add_trace(go.Bar(
            y=oi_df["strike"], x=[-v for v in oi_df["put_oi"]], orientation="h",
            name="Put OI", marker_color=T.DANGER, opacity=0.8,
            hovertemplate="$%{y:.0f}  Put OI: %{customdata:,.0f}<extra></extra>",
            customdata=oi_df["put_oi"],
        ))
        fig_oi.add_hline(y=spot, line=dict(color=T.WARNING, width=1.5, dash="dash"),
                         annotation_text=f"${spot:.0f}",
                         annotation_font_color=T.WARNING, annotation_font_size=10)
        if zero_g:
            fig_oi.add_hline(y=zero_g, line=dict(color="#fb923c", width=1, dash="dot"),
                             annotation_text="ZERO G",
                             annotation_font_color="#fb923c", annotation_font_size=9)
        fig_oi.update_layout(
            **_DARK, height=400, barmode="overlay",
            title=dict(text="Open Interest by Strike",
                       font=dict(size=13, color=T.TEXT_SEC)),
            xaxis=dict(title="OI (contracts)", gridcolor=T.BORDER,
                       tickformat=",", color="#9ca3af"),
            yaxis=dict(tickprefix="$", gridcolor=T.BORDER, color="#9ca3af"),
            legend=dict(orientation="h", x=0, y=1.08, bgcolor="rgba(0,0,0,0)"),
            margin=dict(l=0, r=0, t=50, b=0),
        )

        # ── Pills ─────────────────────────────────────────────────────────────
        pills = [
            _pill("Net GEX", f"{net_total:+.3f}B",
                  T.SUCCESS if net_total >= 0 else T.DANGER),
            _pill("Dealers", "Long Gamma" if net_total >= 0 else "Short Gamma",
                  T.SUCCESS if net_total >= 0 else T.DANGER),
            _pill("Call GEX", f"{call_total:+.3f}B", T.SUCCESS),
            _pill("Put GEX",  f"{put_total:+.3f}B",  T.DANGER),
        ]
        if g1:     pills.append(_pill("G1",     f"${g1:.0f}", "#ef4444"))
        if zero_g: pills.append(_pill("ZERO G", f"${zero_g:.0f}", "#fb923c"))
        if g2:     pills.append(_pill("G2",     f"${g2:.0f}", "#10b981"))
        if sig_hi: pills.append(_pill("σ range", f"${sig_lo:.0f} – ${sig_hi:.0f}", "#8b5cf6"))
        pills.append(_pill("Spot", f"${spot:,.2f}"))

        return html.Div([
            html.Div(pills, style={"display": "flex", "gap": "8px",
                                   "flexWrap": "wrap", "marginBottom": "12px"}),
            dbc.Row([
                dbc.Col(dcc.Graph(figure=fig,    config={"displayModeBar": False}), width=8),
                dbc.Col(dcc.Graph(figure=fig_oi, config={"displayModeBar": False}), width=4),
            ], className="g-2"),
        ])
    except Exception as e:
        return html.P(f"GEX error: {e}", style={"color": T.DANGER, "fontSize": "12px"})


# ── Momentum (RSI + MACD) ─────────────────────────────────────────────────────

@callback(
    Output("mkt-momentum-content", "children"),
    Input("mkt-ticker-store",      "data"),
    State("mkt-apikey-store",      "data"),
)
def render_momentum(ticker, api_key):
    if not ticker:
        return _hint("Loading…")
    if not api_key:
        return _hint("No API key — enter above and click Load")
    try:
        bars = _fetch_bars(ticker or "SPY", api_key)
        if bars.empty:
            return html.P("No price data.", style={"color": T.WARNING})
        if "date" not in bars.columns and bars.index.name == "date":
            bars = bars.reset_index()

        close  = pd.to_numeric(bars["close"], errors="coerce").dropna()
        delta  = close.diff()
        gain   = delta.clip(lower=0).rolling(14).mean()
        loss   = (-delta.clip(upper=0)).rolling(14).mean()
        rsi    = 100 - (100 / (1 + gain / loss.replace(0, np.nan)))
        ema12  = close.ewm(span=12).mean()
        ema26  = close.ewm(span=26).mean()
        macd   = ema12 - ema26
        signal = macd.ewm(span=9).mean()
        hist   = macd - signal

        from plotly.subplots import make_subplots
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
                            row_heights=[0.5, 0.25, 0.25], vertical_spacing=0.04)
        dates = bars["date"].values
        fig.add_trace(go.Scatter(x=dates, y=close.values, mode="lines",
                                 line=dict(color=T.ACCENT, width=1.5), name="Close"), row=1, col=1)
        fig.add_trace(go.Scatter(x=dates, y=rsi.values, mode="lines",
                                 line=dict(color=T.WARNING, width=1.5), name="RSI(14)"), row=2, col=1)
        fig.add_hline(y=70, line=dict(color=T.DANGER, width=1, dash="dot"), row=2, col=1)
        fig.add_hline(y=30, line=dict(color=T.SUCCESS, width=1, dash="dot"), row=2, col=1)
        fig.add_trace(go.Scatter(x=dates, y=macd.values, mode="lines",
                                 line=dict(color=T.ACCENT, width=1.5), name="MACD"), row=3, col=1)
        fig.add_trace(go.Scatter(x=dates, y=signal.values, mode="lines",
                                 line=dict(color=T.WARNING, width=1.5), name="Signal"), row=3, col=1)
        fig.add_trace(go.Bar(x=dates, y=hist.values,
                             marker_color=[T.SUCCESS if v >= 0 else T.DANGER for v in hist.fillna(0)],
                             name="Histogram", opacity=0.6), row=3, col=1)
        for i in range(1, 4):
            fig.update_xaxes(gridcolor=T.BORDER, row=i, col=1)
            fig.update_yaxes(gridcolor=T.BORDER, row=i, col=1)
        fig.update_layout(template="plotly_dark", paper_bgcolor=T.BG_CARD, plot_bgcolor=T.BG_CARD,
                          font=dict(color=T.TEXT_SEC, size=11), height=500,
                          margin=dict(l=0, r=0, t=10, b=0),
                          legend=dict(orientation="h", y=-0.05, bgcolor="rgba(0,0,0,0)"))

        lr  = float(rsi.dropna().iloc[-1])  if not rsi.dropna().empty  else 0
        lm  = float(macd.dropna().iloc[-1]) if not macd.dropna().empty else 0
        ls  = float(signal.dropna().iloc[-1]) if not signal.dropna().empty else 0
        cross = "Bullish" if lm > ls else "Bearish"

        return html.Div([
            html.Div([
                _pill("RSI (14)", f"{lr:.1f}",
                      T.DANGER if lr > 70 else (T.SUCCESS if lr < 30 else T.TEXT_PRIMARY)),
                _pill("MACD",    f"{lm:.3f}"),
                _pill("Signal",  f"{ls:.3f}"),
                _pill("Cross",   cross, T.SUCCESS if cross == "Bullish" else T.DANGER),
            ], style={"display": "flex", "gap": "10px", "marginBottom": "12px"}),
            dcc.Graph(figure=fig, config={"displayModeBar": False}),
        ])
    except Exception as e:
        return html.P(f"Error: {e}", style={"color": T.DANGER, "fontSize": "12px"})


# ── Correlation Analysis ───────────────────────────────────────────────────────

@callback(
    Output("mkt-corr-content",  "children"),
    Input("mkt-corr-run",       "n_clicks"),
    State("mkt-ticker-store",   "data"),
    State("mkt-corr-ticker",    "value"),
    State("mkt-apikey-store",   "data"),
    prevent_initial_call=True,
)
def render_corr(n_clicks, ticker_a, ticker_b, api_key):
    if not api_key:
        return html.P("API key required.", style={"color": T.WARNING})
    ticker_a = (ticker_a or "SPY").upper()
    ticker_b = (ticker_b or "QQQ").upper()
    try:
        df_a = _fetch_bars(ticker_a, api_key)
        df_b = _fetch_bars(ticker_b, api_key)
    except Exception as e:
        return html.P(f"Error: {e}", style={"color": T.DANGER})

    if df_a.empty or df_b.empty:
        return html.P("No data for one or both tickers.", style={"color": T.WARNING})

    def _c(df):
        if "date" not in df.columns and df.index.name == "date":
            df = df.reset_index()
        return df.set_index("date")["close"] if "date" in df.columns else df["close"]

    prices = pd.concat([_c(df_a).rename(ticker_a), _c(df_b).rename(ticker_b)], axis=1).dropna()
    if len(prices) < 10:
        return html.P("Not enough overlapping dates.", style={"color": T.WARNING})

    rets  = prices.pct_change().dropna()
    corr  = float(rets[ticker_a].corr(rets[ticker_b]))
    beta  = float(np.cov(rets[ticker_a], rets[ticker_b])[0,1] / np.var(rets[ticker_b]))
    cum_a = (1 + rets[ticker_a]).cumprod()
    cum_b = (1 + rets[ticker_b]).cumprod()
    m     = np.polyfit(rets[ticker_b], rets[ticker_a], 1)
    xl    = np.linspace(rets[ticker_b].min(), rets[ticker_b].max(), 100)

    fig_c = go.Figure()
    fig_c.add_trace(go.Scatter(x=cum_a.index.astype(str), y=cum_a,
                               name=ticker_a, line=dict(color=T.SUCCESS, width=2)))
    fig_c.add_trace(go.Scatter(x=cum_b.index.astype(str), y=cum_b,
                               name=ticker_b, line=dict(color=T.ACCENT, width=2)))
    fig_c.update_layout(**_DARK, height=280,
                        title=dict(text="Cumulative Return", font=dict(size=12, color=T.TEXT_SEC)),
                        legend=dict(orientation="h", y=-0.2, bgcolor="rgba(0,0,0,0)"))

    fig_s = go.Figure()
    fig_s.add_trace(go.Scatter(x=rets[ticker_b], y=rets[ticker_a], mode="markers",
                               marker=dict(color=T.ACCENT, size=4, opacity=0.5)))
    fig_s.add_trace(go.Scatter(x=xl, y=m[0]*xl+m[1], mode="lines",
                               line=dict(color=T.DANGER, width=2, dash="dash"),
                               name=f"β={beta:.2f}"))
    fig_s.update_layout(**_DARK, height=280,
                        title=dict(text=f"{ticker_a} vs {ticker_b}", font=dict(size=12, color=T.TEXT_SEC)),
                        xaxis=dict(title=ticker_b, gridcolor=T.BORDER),
                        yaxis=dict(title=ticker_a, gridcolor=T.BORDER))

    return html.Div([
        html.Div([
            _pill("Pearson Corr", f"{corr:.3f}",
                  T.SUCCESS if corr >= 0.7 else (T.WARNING if corr >= 0.3 else T.DANGER)),
            _pill("Beta",  f"{beta:.3f}"),
            _pill(f"{ticker_a} Vol", f"{rets[ticker_a].std()*np.sqrt(252):.1%}"),
            _pill(f"{ticker_b} Vol", f"{rets[ticker_b].std()*np.sqrt(252):.1%}"),
        ], style={"display": "flex", "gap": "10px", "marginBottom": "12px"}),
        dbc.Row([
            dbc.Col(dcc.Graph(figure=fig_c, config={"displayModeBar": False}), width=6),
            dbc.Col(dcc.Graph(figure=fig_s, config={"displayModeBar": False}), width=6),
        ], className="g-3"),
    ])


# ── Guide toggles ─────────────────────────────────────────────────────────────

@callback(Output("mkt-gex-guide-collapse",      "is_open"),
          Input("mkt-gex-guide-toggle",          "n_clicks"),
          State("mkt-gex-guide-collapse",        "is_open"),
          prevent_initial_call=True)
def _toggle_gex_guide(n, is_open): return not is_open


@callback(Output("mkt-vol-guide-collapse",      "is_open"),
          Input("mkt-vol-guide-toggle",          "n_clicks"),
          State("mkt-vol-guide-collapse",        "is_open"),
          prevent_initial_call=True)
def _toggle_vol_guide(n, is_open): return not is_open


@callback(Output("mkt-momentum-guide-collapse", "is_open"),
          Input("mkt-momentum-guide-toggle",     "n_clicks"),
          State("mkt-momentum-guide-collapse",   "is_open"),
          prevent_initial_call=True)
def _toggle_momentum_guide(n, is_open): return not is_open


@callback(Output("mkt-yield-guide-collapse",    "is_open"),
          Input("mkt-yield-guide-toggle",        "n_clicks"),
          State("mkt-yield-guide-collapse",      "is_open"),
          prevent_initial_call=True)
def _toggle_yield_guide(n, is_open): return not is_open


# ── Universe pill buttons → store + active highlight ──────────────────────────

@callback(
    Output("mkt-scr-universe", "data"),
    Output({"type": "scr-univ-btn", "index": ALL}, "style"),
    Input({"type": "scr-univ-btn", "index": ALL}, "n_clicks"),
    State({"type": "scr-univ-btn", "index": ALL}, "id"),
    prevent_initial_call=True,
)
def _select_universe(n_clicks_list, ids):
    from dash import ctx
    triggered = ctx.triggered_id
    if not triggered:
        return no_update, [no_update] * len(ids)
    selected = triggered["index"]
    styles = []
    for btn_id in ids:
        active = btn_id["index"] == selected
        styles.append({
            "fontSize": "12px", "fontWeight": "500",
            "padding": "4px 12px",
            "backgroundColor": T.ACCENT if active else T.BG_ELEVATED,
            "border": f"1px solid {T.ACCENT if active else T.BORDER}",
            "color": T.TEXT_PRIMARY,
            "borderRadius": "6px",
        })
    return selected, styles


# ── Market Screener callback ───────────────────────────────────────────────────

@callback(
    Output("mkt-scr-movers-fig",   "figure"),
    Output("mkt-scr-mom-fig",      "figure"),
    Output("mkt-scr-vol-fig",      "figure"),
    Output("mkt-scr-volalert-fig", "figure"),
    Input("mkt-scr-universe",      "data"),
    State("mkt-apikey-store",      "data"),
)
def run_screener(universe, api_key):
    _ef = _scr_empty_fig()
    api_key = api_key or get_polygon_api_key()
    if not api_key:
        msg_fig = _scr_empty_fig("No Polygon API key — enter key above and click Load")
        return msg_fig, msg_fig, msg_fig, msg_fig

    tickers = UNIVERSES.get(universe or _SCR_DEFAULT_UNIVERSE, [])
    if not tickers:
        return _ef, _ef, _ef, _ef

    try:
        from data.polygon_client import PolygonClient
        client = PolygonClient(api_key=api_key)
    except Exception:
        return _ef, _ef, _ef, _ef

    # Batch snapshot
    snap = _scr_batch_snapshot(tickers, client)

    # Daily bars in parallel
    bars: dict[str, pd.DataFrame] = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        fut_map = {ex.submit(_scr_fetch_bars, t, client, 60): t for t in tickers}
        for fut in as_completed(fut_map):
            t = fut_map[fut]
            try:
                df = fut.result()
                if not df.empty:
                    bars[t] = df
            except Exception:
                pass

    # ── Movers ────────────────────────────────────────────────────────────────
    mover_rows = []
    for t in tickers:
        df = bars.get(t)
        if df is None or df.empty:
            continue
        s     = snap.get(t, {})
        price = float(df["close"].iloc[-1])
        vol   = int(s.get("volume", 0))
        if len(df) >= 2:
            prev_c = float(df["close"].iloc[-2])
            chg = round((price - prev_c) / prev_c * 100, 2) if prev_c > 0 else 0.0
        else:
            chg = round(s.get("change_pct", 0), 2)
        mover_rows.append({
            "Ticker": t, "Price": round(price, 2),
            "Change%": chg, "Volume": _fmt_vol(vol),
            "Dollar Vol": _fmt_vol(price * vol),
        })
    mover_sorted = sorted(mover_rows, key=lambda r: r["Change%"], reverse=True)

    # ── Momentum ──────────────────────────────────────────────────────────────
    mom_rows = []
    for t in tickers:
        s  = snap.get(t, {})
        df = bars.get(t)
        if df is None or df.empty:
            continue
        closes = df["close"]
        price  = s.get("close") or float(closes.iloc[-1])
        def _ret(n):
            if len(closes) < n + 1: return None
            return round((float(closes.iloc[-1]) / float(closes.iloc[-(n+1)]) - 1) * 100, 2)
        rsi  = _scr_rsi(closes)
        ma20 = float(closes.iloc[-20:].mean()) if len(closes) >= 20 else None
        ma50 = float(closes.iloc[-50:].mean()) if len(closes) >= 50 else None
        mom_rows.append({
            "Ticker": t, "Price": round(price, 2),
            "1d%":   _ret(1)  if _ret(1)  is not None else "—",
            "5d%":   _ret(5)  if _ret(5)  is not None else "—",
            "20d%":  _ret(20) if _ret(20) is not None else "—",
            "RSI14": round(rsi, 1) if rsi is not None else "—",
            ">20MA": "Yes" if (ma20 and price > ma20) else "No",
            ">50MA": "Yes" if (ma50 and price > ma50) else "No",
        })

    # ── Volatility (IV in parallel) ───────────────────────────────────────────
    with ThreadPoolExecutor(max_workers=8) as ex:
        iv_futs = {ex.submit(_scr_fetch_iv, t, client): t for t in tickers}
        iv_map  = {iv_futs[f]: f.result() for f in iv_futs}

    vol_rows = []
    for t in tickers:
        s  = snap.get(t, {})
        df = bars.get(t)
        if df is None or df.empty:
            continue
        closes = df["close"]
        price  = s.get("close") or float(closes.iloc[-1])
        hv20   = _scr_hv(closes, 20)
        iv_raw = iv_map.get(t)
        iv_val = iv_raw * 100 if iv_raw is not None else None
        iv_hv  = round(iv_val / hv20, 2) if (iv_val and hv20 and hv20 > 0) else None
        vol_rows.append({
            "Ticker": t, "Price": round(price, 2),
            "HV20":   f"{hv20:.1f}%" if hv20 is not None else "—",
            "IV":     f"{iv_val:.1f}%" if iv_val is not None else "—",
            "IV/HV":  iv_hv if iv_hv is not None else "—",
        })

    # ── Volume Alerts ─────────────────────────────────────────────────────────
    volalert_rows = []
    for t in tickers:
        s  = snap.get(t, {})
        df = bars.get(t)
        if df is None or df.empty or s.get("volume", 0) == 0:
            continue
        avg_vol = float(df["volume"].iloc[-20:].mean()) if len(df) >= 20 else None
        if not avg_vol:
            continue
        ratio = s["volume"] / avg_vol
        if ratio >= 2.0:
            price = s.get("close") or float(df["close"].iloc[-1])
            volalert_rows.append({
                "Ticker": t, "Vol Ratio": round(ratio, 2),
                "Price": round(price, 2), "Change%": round(s.get("change_pct", 0), 2),
            })
    volalert_rows.sort(key=lambda r: r["Vol Ratio"], reverse=True)

    return (
        _build_movers_fig(mover_sorted),
        _build_momentum_fig(mom_rows),
        _build_vol_fig(vol_rows),
        _build_volalert_fig(volalert_rows),
    )
