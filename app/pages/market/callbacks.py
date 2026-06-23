"""
app/pages/market/callbacks.py - all Market Data interactivity.

Importing this module registers every @callback with Dash (the decorator runs at
import). The package __init__ imports it for that side effect - keep it. Every
callback id, Input/Output/State, and the pattern-matched
{"type": "scr-univ-btn", "index": ...} are identical to the original market.py.
Split verbatim.
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
from dash import html, dcc, callback, Input, Output, State, no_update, ALL, ctx
import dash_bootstrap_components as dbc
import dash_ag_grid as dag

from app import theme as T, get_polygon_api_key
from engine.screener import UNIVERSES

from app.pages.market.data import (
    _load_yield_curve, _polygon_client, _fetch_bars, _fetch_intraday,
    _fetch_quote, _fetch_grouped_movers,
    _hint, _section, _pill, _DARK, _GRAPH_CFG,
    _SCR_UNIVERSE_OPTIONS, _SCR_DEFAULT_UNIVERSE, _SECTOR,
    _SCR_PLOT_BG, _SCR_PAPER_BG, _SCR_GRID, _SCR_FONT, _SCR_CFG,
    _fmt_vol, _scr_empty_fig, _scr_fetch_bars,
    _scr_fetch_iv, _scr_hv, _scr_rsi,
    _build_movers_fig, _build_momentum_fig, _build_vol_fig, _build_volalert_fig,
    _FUTURES_CATEGORIES, _FUT_CAPS, _fetch_futures_data, _fut_cell_style, _fmt_pct,
    _render_intraday, _render_yield_inner, _build_chain_table,
)
from app.pages.market.guides import (
    _gex_guide, _vol_surface_guide, _momentum_guide, _yield_guide,
)
from app.pages.market.layout import _build_futures_table

logger = logging.getLogger(__name__)


@callback(
    Output("mkt-ticker-store", "data"),
    Output("mkt-apikey-store", "data"),
    Input("mkt-load-btn",      "n_clicks"),
    State("mkt-ticker",        "value"),
    State("mkt-apikey",        "value"),
    prevent_initial_call=True,
)
def set_ticker(n_clicks, ticker, user_key):
    """Load button: just publish the ticker + key to the stores. The quote and
    each section then load from those (the quote auto-refreshes; sections wait
    for their own Load button) — so one click never fans out into a 30-call
    burst against the 5-req/min plan."""
    ticker  = (ticker or "SPY").upper().strip()
    api_key = get_polygon_api_key(user_key or "")
    return ticker, api_key


@callback(
    Output("mkt-quote-strip", "children"),
    Input("mkt-ticker-store", "data"),
    State("mkt-apikey-store", "data"),
)
def render_quote(ticker, api_key):
    """Auto-loads on page open (default ticker) and whenever the ticker changes.
    One cheap call, so it's safe to run without a button."""
    if not ticker:
        return no_update
    if not api_key:
        return html.P("No Polygon API key found. Set POLYGON_API_KEY in .env or enter above.",
                      style={"color": T.DANGER, "fontSize": "13px"})
    try:
        q = _fetch_quote(ticker, api_key)
        if not q:
            return html.P(f"No price data for {ticker} from Polygon.",
                          style={"color": T.WARNING, "fontSize": "12px"})

        price, prev_c = q["close"], q["prev_close"]
        chg, chg_pct  = q["change"], q["change_pct"]
        up = chg >= 0

        pills = [
            _pill("Price",      f"${price:,.2f}" if price else "—",
                  T.SUCCESS if up else T.DANGER),
            _pill("Change",     f"{chg:+.2f} ({chg_pct:+.2f}%)" if prev_c else "—",
                  T.SUCCESS if up else T.DANGER),
            _pill("Volume",     f"{q['volume']:,}" if q["volume"] else "—"),
            _pill("VWAP",       f"${q['vwap']:,.2f}" if q["vwap"] else "—"),
            _pill("Day High",   f"${q['high']:,.2f}" if q["high"] else "—"),
            _pill("Day Low",    f"${q['low']:,.2f}" if q["low"] else "—"),
            _pill("Prev Close", f"${prev_c:,.2f}" if prev_c else "—"),
        ]
        # Honest provenance: "Live" vs "last close (date)" so a flat/closed market
        # never looks like a data failure.
        tag = "Live" if q.get("live") else f"Last close · {q.get('asof','')}"
        return html.Div([
            html.Div(pills, style={"display": "flex", "gap": "10px",
                                   "flexWrap": "wrap", "marginBottom": "4px"}),
            html.Small(tag, style={"color": T.TEXT_MUTED, "fontSize": "10px"}),
        ])
    except Exception as e:
        return html.P(f"Quote error: {e}", style={"color": T.WARNING, "fontSize": "12px"})


@callback(
    Output("mkt-candle-content",   "children"),
    Input("mkt-candle-load",       "n_clicks"),
    Input("mkt-candle-view-store", "data"),
    State("mkt-ticker-store",      "data"),
    State("mkt-apikey-store",      "data"),
    prevent_initial_call=True,
)
def render_candle(_n, eod_mode, ticker, api_key):
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


@callback(
    Output("mkt-yield-content", "children"),
    Input("mkt-yield-load",     "n_clicks"),
    prevent_initial_call=True,
)
def render_yield(_n):
    try:
        return _render_yield_inner()
    except Exception as e:
        return html.P(f"Yield curve error: {e}", style={"color": T.DANGER, "fontSize": "12px"})


@callback(
    Output("mkt-vol-view-store",  "data"),
    Output("mkt-vol-3d-btn",      "color"),
    Output("mkt-vol-3d-btn",      "outline"),
    Output("mkt-vol-chain-btn",   "color"),
    Output("mkt-vol-chain-btn",   "outline"),
    Input("mkt-vol-3d-btn",       "n_clicks"),
    Input("mkt-vol-chain-btn",    "n_clicks"),
    prevent_initial_call=True,
)
def toggle_vol_view(_n3d, _nchain):
    if ctx.triggered_id == "mkt-vol-chain-btn":
        return "chain", "secondary", True, "primary", False
    return "surface", "primary", False, "secondary", True


@callback(
    Output("mkt-candle-view-store",   "data"),
    Output("mkt-candle-eod-btn",      "color"),
    Output("mkt-candle-eod-btn",      "outline"),
    Output("mkt-candle-intraday-btn", "color"),
    Output("mkt-candle-intraday-btn", "outline"),
    Input("mkt-candle-eod-btn",       "n_clicks"),
    Input("mkt-candle-intraday-btn",  "n_clicks"),
    prevent_initial_call=True,
)
def toggle_candle_view(_neod, _nintra):
    # store data is the eod flag: True = EOD daily, False = intraday
    if ctx.triggered_id == "mkt-candle-intraday-btn":
        return False, "secondary", True, "primary", False
    return True, "primary", False, "secondary", True


@callback(
    Output("mkt-chain-expiry",     "options"),
    Output("mkt-chain-expiry",     "value"),
    Output("mkt-chain-expiry-row", "style"),
    Output("mkt-chain-data-store", "data"),
    Input("mkt-vol-load",          "n_clicks"),
    Input("mkt-vol-view-store",    "data"),
    State("mkt-ticker-store",      "data"),
    State("mkt-apikey-store",      "data"),
    prevent_initial_call=True,
)
def update_chain_expiry(_n, view, ticker, api_key):
    _hidden  = {"display": "none"}
    _visible = {"display": "flex", "alignItems": "center", "marginBottom": "10px"}
    if view != "chain" or not ticker or not api_key:
        return [], None, _hidden, None
    try:
        from data.loader import fetch_options_snapshot
        c  = _polygon_client(api_key)
        df = fetch_options_snapshot(c, ticker, min_dte=7, max_dte=180)
        if df.empty:
            return [], None, _visible, None
        exps = (df[["expiration", "dte"]].drop_duplicates()
                  .sort_values("expiration"))
        options = [{"label": f"{r['expiration']}  ({int(r['dte'])}d)", "value": r["expiration"]}
                   for _, r in exps.iterrows()]
        best = exps.iloc[(exps["dte"] - 45).abs().argsort().iloc[0]]["expiration"]
        return options, best, _visible, df.to_json(orient="records")
    except Exception as e:
        return [], None, _visible, None


@callback(
    Output("mkt-vol-content",       "children"),
    Input("mkt-vol-load",           "n_clicks"),
    Input("mkt-vol-view-store",     "data"),
    Input("mkt-chain-data-store",   "data"),
    Input("mkt-chain-expiry",       "value"),
    Input("mkt-chain-moneyness",    "value"),
    State("mkt-ticker-store",       "data"),
    State("mkt-apikey-store",       "data"),
    prevent_initial_call=True,
)
def render_vol_surface(_n, view, chain_json, expiry, moneyness, ticker, api_key):
    if not ticker:
        return _hint("Loading…")
    if not api_key:
        return _hint("No API key — enter above and click Load")
    try:
        import datetime as _dt
        from data.stock_data import yf_stock_price
        c     = _polygon_client(api_key)
        spot  = yf_stock_price(ticker)
        if not spot:
            return html.P(f"Could not fetch spot price for {ticker}.", style={"color": T.WARNING})

        # ── Chain table view ──────────────────────────────────────────────
        if view == "chain":
            if not chain_json or not expiry:
                return _hint("Loading chain…")
            from io import StringIO
            df = pd.read_json(StringIO(chain_json), orient="records")
            if df.empty or expiry not in df["expiration"].values:
                return html.P("No chain data for selected expiry.", style={"color": T.WARNING})
            return _build_chain_table(df, expiry, spot, moneyness or "all")

        # ── 3D surface view (default) ─────────────────────────────────────
        from data.loader import fetch_live_vol_surface
        today   = _dt.date.today()
        surf_df = fetch_live_vol_surface(c, ticker, spot, min_dte=7, max_dte=180, step_pct=0.05)
        if surf_df is None or surf_df.empty:
            return html.P("No vol surface data.", style={"color": T.WARNING})

        from scipy.interpolate import griddata
        pts  = surf_df[["strike", "dte"]].to_numpy(dtype=float)
        vals = surf_df["iv"].to_numpy(dtype=float) * 100.0

        # Resample onto a regular, evenly-spaced grid so the wireframe is uniform.
        # Raw strikes ($1 near ATM, $5 in the wings) and clustered expiries make the
        # mesh look jagged otherwise.
        s_lo, s_hi = float(surf_df["strike"].min()), float(surf_df["strike"].max())
        d_lo, d_hi = float(surf_df["dte"].min()),    float(surf_df["dte"].max())
        strikes = np.linspace(s_lo, s_hi, 28)
        dtes    = np.linspace(d_lo, d_hi, 14)
        Sg, Dg  = np.meshgrid(strikes, dtes)          # (len(dtes), len(strikes))

        z_lin = griddata(pts, vals, (Sg, Dg), method="linear")
        z_nn  = griddata(pts, vals, (Sg, Dg), method="nearest")
        z_pct = np.where(np.isnan(z_lin), z_nn, z_lin)

        # ── Wireframe mesh ──────────────────────────────────────────────────
        WIRE  = "#3a5a8a"
        ATM_C = "#69f0ae"
        atm_j = int(np.argmin(np.abs(strikes - spot))) if spot else None

        fig = go.Figure()
        # Lines along the strike axis (one per DTE row)
        for i, dte in enumerate(dtes):
            fig.add_trace(go.Scatter3d(
                x=strikes.tolist(), y=[float(dte)]*len(strikes), z=z_pct[i].tolist(),
                mode="lines", line=dict(color=WIRE, width=2), showlegend=False,
                hovertemplate=f"DTE {dte:.0f}d — Strike $%{{x:.0f}} — IV %{{z:.1f}}%<extra></extra>",
            ))
        # Lines along the DTE axis (one per strike column)
        for j, strike in enumerate(strikes):
            is_atm = (atm_j is not None and j == atm_j)
            fig.add_trace(go.Scatter3d(
                x=[float(strike)]*len(dtes), y=dtes.tolist(), z=z_pct[:, j].tolist(),
                mode="lines",
                line=dict(color=ATM_C if is_atm else WIRE, width=5 if is_atm else 2),
                showlegend=False,
                hovertemplate=(("⚡ ATM — " if is_atm else "") +
                               f"Strike ${strike:.0f} — DTE %{{y:.0f}}d — IV %{{z:.1f}}%<extra></extra>"),
            ))
        # ATM column markers
        if atm_j is not None:
            fig.add_trace(go.Scatter3d(
                x=[float(strikes[atm_j])]*len(dtes), y=dtes.tolist(),
                z=z_pct[:, atm_j].tolist(), mode="markers",
                marker=dict(size=4, color=ATM_C, symbol="circle"), showlegend=False,
                hovertemplate="⚡ ATM $%{x:.0f} — DTE %{y:.0f}d — IV %{z:.1f}%<extra></extra>",
            ))

        _ax = dict(gridcolor="#2a3050", backgroundcolor="#0c1020",
                   color="#e0e0e0", showbackground=True,
                   tickfont=dict(color="#c0c8d8", size=13))
        # Cap the IV axis to the bulk of the data so a stray spike can't flatten
        # the real smile (belt-and-suspenders alongside the upstream outlier filter).
        _finite = z_pct[np.isfinite(z_pct)]
        z_max = float(np.nanpercentile(_finite, 98)) * 1.15 if _finite.size else 100.0
        z_max = max(10.0, min(z_max, 150.0))
        atm_label = f"  ATM ≈ ${spot:.2f}" if spot else ""
        fig.update_layout(
            paper_bgcolor="#0e1117", font=dict(color="#e0e0e0", family="monospace", size=13),
            title=dict(text=f"{ticker} Volatility Surface{atm_label}  ·  <span style='color:#69f0ae'>green = ATM</span>",
                       font=dict(size=15, color="#e0e0e0")),
            scene=dict(
                domain=dict(x=[0, 0.9], y=[0, 1]),
                xaxis=dict(**_ax, title=dict(text="Strike ($)", font=dict(color="#e0e0e0", size=13))),
                yaxis=dict(**_ax, title=dict(text="DTE (days)", font=dict(color="#e0e0e0", size=13))),
                zaxis=dict(**_ax, title=dict(text="IV (%)",     font=dict(color="#e0e0e0", size=13)),
                           range=[0, z_max]),
                bgcolor="#0c1020",
                camera=dict(eye=dict(x=1.6, y=-1.6, z=0.9)),
                aspectmode="manual", aspectratio=dict(x=2.0, y=1.0, z=0.6),
            ),
            height=650, margin=dict(l=0, r=0, t=50, b=0),
        )
        return dcc.Graph(figure=fig, config={"displayModeBar": True})
    except Exception as e:
        return html.P(f"Vol surface error: {e}", style={"color": T.DANGER, "fontSize": "12px"})


@callback(
    Output("mkt-activity-content", "children"),
    Input("mkt-activity-load",     "n_clicks"),
    State("mkt-ticker-store",      "data"),
    State("mkt-apikey-store",      "data"),
    prevent_initial_call=True,
)
def render_activity(_n, ticker, api_key):
    if not ticker:
        return _hint("Loading…")
    if not api_key:
        return _hint("No API key — enter above and click Load")
    try:
        c = _polygon_client(api_key)
    except Exception as e:
        return html.P(f"Client error: {e}", style={"color": T.DANGER, "fontSize": "12px"})

    movers_asof = ""
    try:
        mv = _fetch_grouped_movers(api_key, top_n=12)
        if mv:
            movers_asof = mv["asof"]
            top = mv["gainers"] + mv["losers"]
            movers_df = pd.DataFrame(top)
            all_df    = pd.DataFrame(mv["all"])
        else:
            movers_df, all_df = pd.DataFrame(), pd.DataFrame()
    except Exception as e:
        return html.P(f"Movers error: {e}", style={"color": T.DANGER, "fontSize": "12px"})

    # GEX
    try:
        import datetime as _dt
        from data.stock_data import yf_stock_price
        spot = yf_stock_price(ticker) or 500.0

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
    fig_m.update_layout(**_DARK, height=480,
                        title=dict(text=f"Top Movers · liquid names · {movers_asof}",
                                   font=dict(size=13, color=T.TEXT_SEC)),
                        xaxis=dict(ticksuffix="%", gridcolor=T.BORDER),
                        yaxis=dict(gridcolor=T.BORDER), showlegend=False)

    adv = int((all_df["change_pct"] > 0).sum()) if not all_df.empty else 0
    dec = int((all_df["change_pct"] < 0).sum()) if not all_df.empty else 0
    children = [
        html.Div([
            _pill("Advancers", f"{adv:,}", T.SUCCESS),
            _pill("Decliners", f"{dec:,}", T.DANGER),
            _pill("Universe",  f"{len(all_df):,}"),
        ], style={"display": "flex", "gap": "10px", "marginBottom": "12px"}),
        dcc.Graph(figure=fig_m, config=_GRAPH_CFG),
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
        fig_g.update_layout(**_DARK, height=420, barmode="relative",
                            title=dict(text=f"Dealer GEX — {ticker} ($B)",
                                       font=dict(size=13, color=T.TEXT_SEC)),
                            xaxis=dict(tickprefix="$", gridcolor=T.BORDER),
                            yaxis=dict(title="GEX ($B)", gridcolor=T.BORDER, zeroline=False),
                            legend=dict(orientation="h", y=-0.2, bgcolor="rgba(0,0,0,0)"))
        children += [
            html.Div(style={"height": "12px"}),
            _pill("Net GEX ($B)", f"{net:+.3f}", T.SUCCESS if net >= 0 else T.DANGER),
            html.Div(style={"height": "8px"}),
            dcc.Graph(figure=fig_g, config=_GRAPH_CFG),
        ]

    return html.Div(children)


@callback(
    Output("mkt-gex-content",   "children"),
    Input("mkt-gex-load",       "n_clicks"),
    State("mkt-ticker-store",   "data"),
    State("mkt-apikey-store",   "data"),
    prevent_initial_call=True,
)
def render_gex(_n, ticker, api_key):
    if not ticker:
        return _hint("Loading…")
    if not api_key:
        return _hint("No API key — enter above and click Load")
    try:
        import datetime as _dt
        from collections import defaultdict
        from data.stock_data import yf_stock_price
        c    = _polygon_client(api_key)
        spot = yf_stock_price(ticker)
        if not spot:
            return html.P(f"Could not fetch spot price for {ticker}.", style={"color": T.WARNING})

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

        # Dealer cluster zones — VERTICAL x-bands between the gamma wall and the σ
        # edge (add_vrect, not add_hrect: hrect ignores x0/x1 and spans full width,
        # which dumped the label at the chart's right edge).
        if g1 is not None and sig_hi is not None and g1 != sig_hi:
            fig.add_vrect(x0=min(g1, sig_hi), x1=max(g1, sig_hi),
                          fillcolor="rgba(239,68,68,0.07)", line_width=0,
                          annotation_text="cluster", annotation_position="top left",
                          annotation_font_color="rgba(239,68,68,0.6)",
                          annotation_font_size=9)
        if g2 is not None and sig_lo is not None and g2 != sig_lo:
            fig.add_vrect(x0=min(g2, sig_lo), x1=max(g2, sig_lo),
                          fillcolor="rgba(16,185,129,0.07)", line_width=0,
                          annotation_text="cluster", annotation_position="bottom left",
                          annotation_font_color="rgba(16,185,129,0.6)",
                          annotation_font_size=9)

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

        # Vertical reference lines. These levels (spot/G1/G2/ZERO-G/σ) all cluster
        # within a few dollars, so on-chart text labels would overlap — they're
        # already named in the colour-matched pills above. Only Spot gets a label.
        def _vl(x, color, text=None, width=1.5, dash="dot"):
            fig.add_vline(x=x, line=dict(color=color, width=width, dash=dash),
                          annotation_text=(text or ""), annotation_font_color=color,
                          annotation_font_size=10, annotation_position="top")

        _vl(spot,  T.WARNING,  f"Spot ${spot:.0f}", dash="dash")
        if zero_g: _vl(zero_g, "#fb923c")
        if g1:     _vl(g1,     "#ef4444")
        if g2:     _vl(g2,     "#10b981")
        if sig_hi: _vl(sig_hi, "#8b5cf6")
        if sig_lo: _vl(sig_lo, "#8b5cf6")

        fig.add_hline(y=0, line=dict(color=T.BORDER_BRT, width=1))
        fig.update_layout(
            **_DARK, height=400, barmode="overlay",
            title=dict(text=f"{ticker} — GEX by Strike  ·  zoomed to ±8% spot  ·  next 60 DTE",
                       font=dict(size=13, color=T.TEXT_SEC)),
            # Fetch is ±15% but GEX concentrates at the money — zoom in so the bars
            # are legible instead of squished into the centre of a wide axis.
            xaxis=dict(tickprefix="$", gridcolor=T.BORDER,
                       range=[spot * 0.92, spot * 1.08]),
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
            yaxis=dict(tickprefix="$", gridcolor=T.BORDER, color="#9ca3af",
                       range=[spot * 0.92, spot * 1.08]),
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
                dbc.Col(dcc.Graph(figure=fig,    config=_GRAPH_CFG), width=8),
                dbc.Col(dcc.Graph(figure=fig_oi, config=_GRAPH_CFG), width=4),
            ], className="g-2"),
        ])
    except Exception as e:
        return html.P(f"GEX error: {e}", style={"color": T.DANGER, "fontSize": "12px"})


@callback(
    Output("mkt-momentum-content", "children"),
    Input("mkt-momentum-load",     "n_clicks"),
    State("mkt-ticker-store",      "data"),
    State("mkt-apikey-store",      "data"),
    prevent_initial_call=True,
)
def render_momentum(_n, ticker, api_key):
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
                          font=dict(color=T.TEXT_SEC, size=11), height=680,
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
            dcc.Graph(figure=fig, config=_GRAPH_CFG),
        ])
    except Exception as e:
        return html.P(f"Error: {e}", style={"color": T.DANGER, "fontSize": "12px"})


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
    fig_c.update_layout(**_DARK, height=380,
                        title=dict(text="Cumulative Return", font=dict(size=12, color=T.TEXT_SEC)),
                        legend=dict(orientation="h", y=-0.2, bgcolor="rgba(0,0,0,0)"))

    fig_s = go.Figure()
    fig_s.add_trace(go.Scatter(x=rets[ticker_b], y=rets[ticker_a], mode="markers",
                               marker=dict(color=T.ACCENT, size=4, opacity=0.5)))
    fig_s.add_trace(go.Scatter(x=xl, y=m[0]*xl+m[1], mode="lines",
                               line=dict(color=T.DANGER, width=2, dash="dash"),
                               name=f"β={beta:.2f}"))
    fig_s.update_layout(**_DARK, height=380,
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
            dbc.Col(dcc.Graph(figure=fig_c, config=_GRAPH_CFG), width=6),
            dbc.Col(dcc.Graph(figure=fig_s, config=_GRAPH_CFG), width=6),
        ], className="g-3"),
    ])


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


@callback(
    Output("mkt-scr-movers-fig",   "figure"),
    Output("mkt-scr-mom-fig",      "figure"),
    Output("mkt-scr-vol-fig",      "figure"),
    Output("mkt-scr-volalert-fig", "figure"),
    Input("mkt-scr-universe",      "data"),
    State("mkt-apikey-store",      "data"),
    prevent_initial_call=True,
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

    # Daily bars for the whole universe in ONE yfinance download (free, includes
    # today's bar, no 5/min cap) instead of N throttled Polygon calls.
    from data.stock_data import yf_batch_daily
    bars = yf_batch_daily(tickers, 60)

    # Per-ticker last-session snapshot derived from daily bars:
    # close, volume, and day-over-day % change.
    snap: dict[str, dict] = {}
    for t, df in bars.items():
        last = df.iloc[-1]
        close = float(last["close"])
        vol   = float(last.get("volume", 0) or 0)
        chg   = 0.0
        if len(df) >= 2:
            prev_c = float(df["close"].iloc[-2])
            if prev_c > 0:
                chg = round((close - prev_c) / prev_c * 100, 2)
        snap[t] = {"close": close, "volume": vol, "change_pct": chg}

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


@callback(
    Output("mkt-futures-content", "children"),
    Input("mkt-futures-refresh-btn", "n_clicks"),
    prevent_initial_call=True,
)
def refresh_futures(n_clicks):
    try:
        data = _fetch_futures_data()
        if not data:
            return html.P("No data returned from Yahoo Finance. Try again.",
                          style={"color": T.WARNING, "fontSize": "12px"})
        return _build_futures_table(data)
    except Exception as exc:
        logger.exception(f"Futures refresh error: {exc}")
        return html.P(f"Error loading futures: {exc}",
                      style={"color": T.DANGER, "fontSize": "12px"})
