"""
dash_app/pages/market.py
Market Data — pure Polygon.io (no DB dependency).
All sections load when user clicks "Load".
Mirrors dashboard/tabs/market_data.py feature set.
"""
from __future__ import annotations

import math
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import html, dcc, callback, Input, Output, State, no_update
import dash_bootstrap_components as dbc

from dash_app import theme as T, get_polygon_api_key

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
                dbc.Input(id="mkt-ticker", type="text", value="SPY",
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
                                 children=_hint("Click Load to render")),
                        type="circle", color=T.ACCENT),
        ], style={**T.STYLE_CARD, "marginBottom": "16px"}),
        _section("Treasury Term Structure — Yield Curve & 3D Surface (FRED, free)",
                 dcc.Loading(html.Div(id="mkt-yield-content",
                                      children=_hint("Click Load to fetch from FRED")),
                             type="circle", color=T.ACCENT)),
        _section("Volatility Surface 3D",
                 dcc.Loading(html.Div(id="mkt-vol-content",
                                      children=_hint("Click Load to render")),
                             type="circle", color=T.ACCENT)),
        _section("Market Activity — Top Movers & Dealer GEX",
                 dcc.Loading(html.Div(id="mkt-activity-content",
                                      children=_hint("Click Load to render")),
                             type="circle", color=T.ACCENT)),
        _section("Momentum Indicators — RSI & MACD",
                 dcc.Loading(html.Div(id="mkt-momentum-content",
                                      children=_hint("Click Load to render")),
                             type="circle", color=T.ACCENT)),
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

        dcc.Store(id="mkt-ticker-store", data=None),
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
    prevent_initial_call=True,
)
def render_candle(ticker, eod_mode, api_key):
    if not ticker:
        return _hint("Click Load to render")
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
    prevent_initial_call=True,
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
    prevent_initial_call=True,
)
def render_vol_surface(ticker, api_key):
    if not ticker:
        return _hint("Click Load to render")
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
    prevent_initial_call=True,
)
def render_activity(ticker, api_key):
    if not ticker:
        return _hint("Click Load to render")
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


# ── Momentum (RSI + MACD) ─────────────────────────────────────────────────────

@callback(
    Output("mkt-momentum-content", "children"),
    Input("mkt-ticker-store",      "data"),
    State("mkt-apikey-store",      "data"),
    prevent_initial_call=True,
)
def render_momentum(ticker, api_key):
    if not ticker:
        return _hint("Click Load to render")
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
