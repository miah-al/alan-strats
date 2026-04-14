"""
dash_app/pages/paper_trading.py
Full Paper Trading page: Open Positions, Closed Positions, Transactions, Performance.
Includes a full-featured position detail modal matching the Streamlit version.
"""
from __future__ import annotations

import math
import datetime
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import dash_ag_grid as dag
import dash_bootstrap_components as dbc
from dash import html, dcc, callback, Input, Output, State, no_update, ctx, ALL

from dash_app import theme as T

_ACCOUNT_ID = 1


def _get_engine():
    from db.client import get_engine
    return get_engine()


def _load_data():
    """Returns (open_groups, closed_rows, txns_df) or empty on failure."""
    from engine.positions import load_transactions, get_open_trade_groups, get_closed_trade_groups
    try:
        engine = _get_engine()
        txns   = load_transactions(engine, _ACCOUNT_ID)
        if txns.empty:
            return {}, [], pd.DataFrame()
        return get_open_trade_groups(txns), get_closed_trade_groups(txns), txns
    except Exception:
        return {}, [], pd.DataFrame()


def _net_entry(grp: pd.DataFrame) -> float:
    total = 0.0
    for _, r in grp.iterrows():
        sign = -1.0 if str(r.get("Direction", "")).upper() == "BUY" else 1.0
        mult = float(r.get("Multiplier", 1) or 1)
        total += sign * float(r.get("Quantity", 0) or 0) \
                      * float(r.get("TransactionPrice", 0) or 0) * mult
    return total


# ── Column definitions ────────────────────────────────────────────────────────

_OPEN_COLS = [
    {"field": "Trade Group", "pinned": "left", "minWidth": 160, "flex": 2},
    {"field": "Underlying",  "minWidth": 90,  "flex": 1},
    {"field": "Strategy",    "minWidth": 150, "flex": 2},
    {"field": "Open Date",   "minWidth": 100, "flex": 1, "sort": "asc"},
    {"field": "Legs",        "minWidth": 60,  "width": 65,  "type": "numericColumn"},
    {"field": "DTE",         "minWidth": 55,  "width": 60,  "type": "numericColumn"},
    {"field": "_net",        "hide": True},
    {"field": "Net Entry",   "minWidth": 100, "flex": 1,
     "cellClassRules": {
         "cell-positive": {"function": "params.data._net > 0"},
         "cell-negative": {"function": "params.data._net < 0"},
         "cell-neutral":  {"function": "params.data._net === 0"},
     }},
    {"field": "Alerts",      "minWidth": 80,  "width": 90},
    {"field": "View", "width": 90, "sortable": False, "filter": False,
     "pinned": "right", "suppressSizeToFit": True,
     "cellStyle": {"textAlign": "center", "cursor": "pointer"},
     "valueGetter": {"function": "'📊 View'"},
     "cellClass": "ic-chart-btn"},
    {"field": "_tgid",       "hide": True},
]

_CLOSED_COLS = [
    {"field": "Underlying",  "minWidth": 90,  "flex": 1},
    {"field": "Strategy",    "minWidth": 150, "flex": 2},
    {"field": "Open Date",   "minWidth": 100, "flex": 1, "sort": "desc"},
    {"field": "Close Date",  "minWidth": 100, "flex": 1},
    {"field": "P&L",         "minWidth": 100, "flex": 1,
     "cellClassRules": {
         "cell-positive": {"function": "params.value && params.value.startsWith('+')"},
         "cell-negative": {"function": "params.value && params.value.startsWith('-')"},
     }},
    {"field": "Result",      "minWidth": 75,  "width": 85,
     "cellClassRules": {
         "cell-positive": {"function": "params.value === 'WIN'"},
         "cell-negative": {"function": "params.value === 'LOSS'"},
     }},
]

_TXNS_COLS = [
    {"field": "Date",        "minWidth": 95,  "flex": 1, "sort": "desc"},
    {"field": "Underlying",  "minWidth": 85,  "flex": 1},
    {"field": "Strategy",    "minWidth": 130, "flex": 2},
    {"field": "Symbol",      "minWidth": 130, "flex": 2},
    {"field": "LegType",     "minWidth": 90,  "flex": 1},
    {"field": "Direction",   "minWidth": 80,  "width": 90},
    {"field": "Qty",         "minWidth": 60,  "width": 65,  "type": "numericColumn"},
    {"field": "Price",       "minWidth": 80,  "flex": 1},
    {"field": "Cash Flow",   "minWidth": 95,  "flex": 1},
    {"field": "Type",        "minWidth": 75,  "width": 85},
    {"field": "Notes",       "minWidth": 100, "flex": 2},
]


def _grid(id: str, cols: list, height: int = 400) -> dag.AgGrid:
    return dag.AgGrid(
        id=id,
        columnDefs=cols,
        rowData=[],
        defaultColDef={"resizable": True, "sortable": True, "filter": True},
        dashGridOptions={
            "animateRows": True,
            "domLayout": "autoHeight",
            "rowSelection": {"mode": "singleRow", "checkboxes": False,
                             "enableClickSelection": True},
        },
        columnSize="sizeToFit",
        className=T.AGGRID_THEME,
        style={"width": "100%"},
    )


# ── Black-Scholes helper ──────────────────────────────────────────────────────

def bs_val(S: float, K: float, T: float, iv: float, otype: str) -> float:
    """Black-Scholes option price. otype: 'call' or 'put'."""
    from scipy.stats import norm as _norm
    r = 0.045
    if T <= 0 or iv <= 0:
        return max(0.0, (S - K) if otype == "call" else (K - S))
    d1 = (math.log(S / K) + (r + 0.5 * iv ** 2) * T) / (iv * math.sqrt(T))
    d2 = d1 - iv * math.sqrt(T)
    if otype == "call":
        return S * _norm.cdf(d1) - K * math.exp(-r * T) * _norm.cdf(d2)
    else:
        return K * math.exp(-r * T) * _norm.cdf(-d2) - S * _norm.cdf(-d1)


# ── Payoff chart (matches Streamlit _plot_payoff) ─────────────────────────────

def _plot_payoff(grp: pd.DataFrame, spot: float | None) -> go.Figure | None:
    """At-expiration payoff diagram for a multi-leg options position."""
    if "SecurityType" not in grp.columns:
        return None
    opt = grp[grp["SecurityType"].str.lower() == "option"].copy()
    if opt.empty:
        return None

    strikes = opt["Strike"].dropna().astype(float)
    # Filter out placeholder 0-strikes (stored when real strike wasn't available)
    strikes = strikes[strikes > 0]
    if strikes.empty and spot is None:
        return None

    if strikes.empty:
        # No real strikes — use spot-centered range
        lo, hi = spot * 0.80, spot * 1.20
    else:
        s_min  = float(strikes.min())
        s_max  = float(strikes.max())
        spread = max(s_max - s_min, s_min * 0.05, 5.0)
        refs   = [s_min - spread * 0.5, s_max + spread * 0.5]
        if spot:
            refs += [spot * 0.85, spot * 1.15]
        lo, hi = min(refs), max(refs)
    N      = 400
    prices = [lo + (hi - lo) * i / N for i in range(N + 1)]

    # Net entry credit (positive = credit received)
    net_entry_credit = 0.0
    for _, r in opt.iterrows():
        direction = str(r.get("Direction", "")).upper()
        qty  = float(r.get("Quantity") or 1)
        mult = float(r.get("Multiplier") or 100)
        px   = float(r.get("TransactionPrice") or 0)
        sign = -1.0 if direction == "BUY" else 1.0
        net_entry_credit += sign * px * qty * mult

    pnl_curve = []
    for S in prices:
        total = net_entry_credit
        for _, r in opt.iterrows():
            K         = float(r.get("Strike") or 0)
            otype     = str(r.get("OptionType") or "").lower()
            direction = str(r.get("Direction", "")).upper()
            qty       = float(r.get("Quantity") or 1)
            mult      = float(r.get("Multiplier") or 100)
            intrinsic = max(S - K, 0) if otype == "call" else max(K - S, 0)
            sign      = 1.0 if direction == "BUY" else -1.0
            total    += sign * intrinsic * qty * mult
        pnl_curve.append(total)

    fig = go.Figure()

    # Profit fill (green)
    fig.add_trace(go.Scatter(
        x=prices, y=[v if v >= 0 else 0 for v in pnl_curve],
        mode="none", fill="tozeroy",
        fillcolor="rgba(38,166,154,0.25)", showlegend=False,
    ))
    # Loss fill (red)
    fig.add_trace(go.Scatter(
        x=prices, y=[v if v <= 0 else 0 for v in pnl_curve],
        mode="none", fill="tozeroy",
        fillcolor="rgba(239,83,80,0.25)", showlegend=False,
    ))
    # Main payoff line
    fig.add_trace(go.Scatter(
        x=prices, y=pnl_curve,
        mode="lines",
        line=dict(color="#e0e0e0", width=2),
        showlegend=False,
        hovertemplate="S=$%{x:.2f}  P&L=$%{y:+,.2f}<extra></extra>",
    ))

    fig.add_hline(y=0, line_color="rgba(255,255,255,0.3)", line_width=1)

    leg_colors = {
        "ShortPut":  "#ef5350", "LongPut":  "#ffb300",
        "ShortCall": "#ef5350", "LongCall": "#ffb300",
    }
    for _, r in opt.iterrows():
        k = r.get("Strike")
        if k is None:
            continue
        lt    = str(r.get("LegType") or "")
        color = leg_colors.get(lt, "#888888")
        fig.add_vline(x=float(k), line_dash="dot", line_color=color, line_width=1)

    if spot:
        fig.add_vline(
            x=spot, line_dash="solid",
            line_color="rgba(255,255,255,0.6)", line_width=1.5,
            annotation_text=f"  ${spot:.2f}",
            annotation_position="top right",
            annotation_font=dict(size=10, color="#ffffff"),
        )

    fig.update_layout(
        title=dict(text="Payoff at Expiration", font=dict(size=13, color=T.TEXT_SEC)),
        height=300, template="plotly_dark",
        paper_bgcolor=T.BG_CARD, plot_bgcolor=T.BG_CARD,
        font=dict(color=T.TEXT_SEC, size=11),
        xaxis=dict(
            gridcolor=T.BORDER, tickprefix="$", range=[lo, hi], zeroline=False,
            title="Underlying Price at Expiry",
        ),
        yaxis=dict(gridcolor=T.BORDER, tickprefix="$", zeroline=False, title="P&L ($)"),
        margin=dict(l=50, r=20, t=40, b=40),
    )
    return fig


# ── Iron Condor enhanced payoff chart ─────────────────────────────────────────

def _plot_ic_payoff(
    opt: pd.DataFrame,
    net_credit: float,
    short_call_k: float | None,
    short_put_k: float | None,
    long_call_k: float | None,
    long_put_k: float | None,
    profit_target: float,
    stop_loss: float,
    be_upper: float | None,
    be_lower: float | None,
    dte_remaining: int | None,
    expiry_str: str | None,
    spot: float | None,
) -> go.Figure | None:
    """IC-specific payoff chart with BS today-line, exit rule lines, breakevens."""
    if not (short_call_k and short_put_k and long_call_k and long_put_k):
        return _plot_payoff(opt, spot)

    ref_price = spot if spot else (short_call_k + short_put_k) / 2
    prices_arr = np.linspace(ref_price * 0.75, ref_price * 1.25, 400)

    def pnl_expiry(S_arr):
        cs = np.minimum(0, short_call_k - S_arr) + np.maximum(0, S_arr - long_call_k)
        ps = np.minimum(0, S_arr - short_put_k)  + np.maximum(0, long_put_k - S_arr)
        return (net_credit + cs + ps) * 100

    pnl_exp = pnl_expiry(prices_arr)

    # BS today-line (25% IV fallback when no live IV)
    atm_iv  = 0.25
    T_now   = max((dte_remaining or 30) / 252, 0.001)

    pnl_today = np.array([
        (net_credit
         - bs_val(S, short_call_k, T_now, atm_iv, "call")
         + bs_val(S, long_call_k,  T_now, atm_iv, "call")
         - bs_val(S, short_put_k,  T_now, atm_iv, "put")
         + bs_val(S, long_put_k,   T_now, atm_iv, "put")) * 100
        for S in prices_arr
    ])

    fig = go.Figure()

    # Fills
    fig.add_trace(go.Scatter(
        x=prices_arr, y=np.where(pnl_exp >= 0, pnl_exp, 0),
        fill="tozeroy", fillcolor="rgba(16,185,129,0.10)",
        line=dict(width=0), showlegend=False, hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=prices_arr, y=np.where(pnl_exp < 0, pnl_exp, 0),
        fill="tozeroy", fillcolor="rgba(239,68,68,0.10)",
        line=dict(width=0), showlegend=False, hoverinfo="skip",
    ))

    # P&L lines
    fig.add_trace(go.Scatter(
        x=prices_arr, y=pnl_exp, name="At expiry",
        line=dict(color=T.ACCENT, width=2),
        hovertemplate="$%{x:.2f} → $%{y:.0f}<extra>Expiry</extra>",
    ))
    # BS today-line (always shown with 25% IV fallback)
    fig.add_trace(go.Scatter(
        x=prices_arr, y=pnl_today, name="Today (BS, 25% IV)",
        line=dict(color=T.SUCCESS, width=1.5, dash="dot"),
        hovertemplate="$%{x:.2f} → $%{y:.0f}<extra>Today</extra>",
    ))

    # Strategy exit rule horizontal lines
    fig.add_hline(
        y=profit_target * 100,
        line=dict(color=T.SUCCESS, width=1.5, dash="dash"),
        annotation_text=f"50% close +${profit_target * 100:.0f}",
        annotation_font_color=T.SUCCESS,
        annotation_position="top left",
    )
    fig.add_hline(
        y=stop_loss * 100,
        line=dict(color=T.DANGER, width=1.5, dash="dash"),
        annotation_text=f"2x stop -${abs(stop_loss) * 100:.0f}",
        annotation_font_color=T.DANGER,
        annotation_position="bottom left",
    )
    fig.add_hline(y=0, line=dict(color=T.BORDER_BRT, width=1))

    # Vertical: spot, breakevens
    if spot:
        fig.add_vline(
            x=spot, line=dict(color=T.WARNING, width=1.5, dash="dash"),
            annotation_text=f"Spot ${spot:.0f}",
            annotation_font_color=T.WARNING,
            annotation_position="top right",
        )
    if be_upper:
        fig.add_vline(
            x=be_upper, line=dict(color=T.TEXT_SEC, width=1, dash="dot"),
            annotation_text=f"BE ${be_upper:.0f}",
            annotation_font_color=T.TEXT_SEC,
        )
    if be_lower:
        fig.add_vline(
            x=be_lower, line=dict(color=T.TEXT_SEC, width=1, dash="dot"),
            annotation_text=f"BE ${be_lower:.0f}",
            annotation_font_color=T.TEXT_SEC,
        )

    dte_label = f"  ({dte_remaining} DTE)" if dte_remaining is not None else ""
    exp_label  = f"  Exp {expiry_str}" if expiry_str else ""
    fig.update_layout(
        title=dict(
            text=f"Iron Condor P&L{exp_label}{dte_label}  |  50% target · 2× stop · 21 DTE exit",
            font=dict(size=12, color=T.TEXT_SEC),
        ),
        xaxis_title="Underlying Price",
        yaxis_title="P&L per Contract ($)",
        height=380,
        margin=dict(l=0, r=0, t=50, b=0),
        template="plotly_dark",
        paper_bgcolor=T.BG_BASE,
        plot_bgcolor=T.BG_CARD,
        font=dict(color=T.TEXT_SEC, size=11),
        xaxis=dict(gridcolor=T.BORDER, tickformat="$,.0f"),
        yaxis=dict(gridcolor=T.BORDER, tickformat="$,.0f", zeroline=False),
        legend=dict(bgcolor="rgba(0,0,0,0)", orientation="h", y=-0.15),
    )
    return fig


# ── Equity P&L chart ──────────────────────────────────────────────────────────

def _plot_equity_pnl(
    underlying: str,
    entry_px: float,
    qty: float,
    days_held: int | None,
    spot: float | None,
) -> go.Figure | None:
    """Simple linear P&L chart for equity positions."""
    if entry_px <= 0:
        return None

    ref    = spot if spot else entry_px
    prices = np.linspace(ref * 0.80, ref * 1.20, 300)
    pnl    = (prices - entry_px) * qty
    days_str = f" · {days_held}d held" if days_held is not None else ""

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=prices, y=pnl,
        mode="lines",
        line=dict(color="#5c6bc0", width=2),
        name="Unrealized P&L",
        fill="tozeroy",
        fillcolor="rgba(92,107,192,0.08)",
        hovertemplate="Price: $%{x:.2f}<br>P&L: $%{y:+,.2f}<extra></extra>",
    ))
    fig.add_hline(y=0, line=dict(color=T.BORDER_BRT, width=1))
    fig.add_vline(
        x=entry_px,
        line=dict(color=T.WARNING, width=1.5, dash="dash"),
        annotation_text=f"Entry ${entry_px:.2f}",
        annotation_position="top left",
        annotation_font_color=T.WARNING,
        annotation_font_size=11,
    )
    if spot:
        cur_pnl = (spot - entry_px) * qty
        fig.add_vline(
            x=spot,
            line=dict(color=T.SUCCESS if cur_pnl >= 0 else T.DANGER, width=2),
            annotation_text=f"Now ${spot:.2f}  P&L ${cur_pnl:+,.2f}",
            annotation_position="top right",
            annotation_font_color=T.SUCCESS if cur_pnl >= 0 else T.DANGER,
            annotation_font_size=11,
        )

    fig.update_layout(
        title=dict(
            text=f"{underlying} Equity P&L — {qty:.0f} share(s) @ ${entry_px:.2f}{days_str}",
            font=dict(size=12, color=T.TEXT_SEC),
        ),
        height=300,
        template="plotly_dark",
        paper_bgcolor=T.BG_CARD,
        plot_bgcolor=T.BG_CARD,
        margin=dict(t=45, b=20, l=0, r=0),
        xaxis=dict(title="Stock Price ($)", tickformat="$,.2f", gridcolor=T.BORDER),
        yaxis=dict(title="Unrealized P&L ($)", tickformat="$,.0f", gridcolor=T.BORDER),
        showlegend=False,
        font=dict(color=T.TEXT_SEC, size=11),
    )
    return fig


# ── Alert badges ──────────────────────────────────────────────────────────────

_ALERT_COLORS = {
    "error":   (T.DANGER,  "#450a0a"),
    "warning": (T.WARNING, "#451a00"),
    "success": (T.SUCCESS, "#052e16"),
}

_ALERT_PREFIX = {
    "error":   "ERROR",
    "warning": "WARN",
    "success": "OK",
}


def _render_alert_badges(alerts: list[dict]) -> html.Div:
    if not alerts:
        return html.Div()
    badges = []
    for a in alerts:
        level   = a.get("level", "warning")
        fg, bg  = _ALERT_COLORS.get(level, (T.TEXT_MUTED, T.BG_CARD))
        prefix  = _ALERT_PREFIX.get(level, "INFO")
        badges.append(
            html.Div([
                html.Span(prefix, style={
                    "fontWeight": "700", "fontSize": "10px",
                    "marginRight": "6px", "opacity": "0.8",
                }),
                html.Span(a.get("msg", ""), style={"fontSize": "12px"}),
            ], style={
                "padding": "7px 12px",
                "background": bg,
                "border": f"1px solid {fg}",
                "borderLeft": f"3px solid {fg}",
                "borderRadius": "6px",
                "color": fg,
                "marginBottom": "6px",
            })
        )
    return html.Div(badges)


# ── Metric card helper ────────────────────────────────────────────────────────

def _metric_card(label: str, value: str, color: str = T.TEXT_PRIMARY) -> html.Div:
    return html.Div([
        html.Div(label, style={
            "color": T.TEXT_MUTED, "fontSize": "10px", "fontWeight": "600",
            "textTransform": "uppercase", "letterSpacing": "0.07em",
            "marginBottom": "4px",
        }),
        html.Div(value, style={
            "color": color, "fontSize": "1.1rem", "fontWeight": "700",
        }),
    ], style={
        **T.STYLE_CARD,
        "flex": "1", "minWidth": "110px",
        "padding": "10px 14px",
    })


# ── Legs table (AgGrid) ───────────────────────────────────────────────────────

def _build_legs_table(grp: pd.DataFrame, live_prices: dict | None = None) -> dag.AgGrid:
    legs = []
    for _, r in grp.iterrows():
        stype = str(r.get("SecurityType", "")).lower()
        if stype == "cash":
            continue
        px   = r.get("TransactionPrice")
        qty  = float(r.get("Quantity")   or 0)
        mult = float(r.get("Multiplier") or 100)
        dirn = str(r.get("Direction", "")).upper()
        sign = 1.0 if dirn == "SELL" else -1.0
        sym  = str(r.get("Symbol", ""))

        # Current mark price → live MKT VALUE; fall back to entry price
        live    = (live_prices or {}).get(sym, {})
        cur_px  = live.get("price") if isinstance(live, dict) else None
        mkt_val = sign * cur_px * abs(qty) * mult if cur_px is not None else None

        legs.append({
            "Symbol":    sym,
            "Type":      str(r.get("OptionType") or stype).upper(),
            "Strike":    str(r.get("Strike") or "—"),
            "Expiry":    str(r.get("Expiration") or "—")[:10],
            "Dir":       dirn,
            "Qty":       qty,
            "Entry Px":  f"${float(px):,.2f}" if px is not None else "—",
            "Mkt Value": f"${mkt_val:,.2f}" if mkt_val is not None else "—",
        })

    return dag.AgGrid(
        columnDefs=[
            {"field": "Symbol",    "flex": 1},
            {"field": "Type",      "width": 80},
            {"field": "Strike",    "width": 90},
            {"field": "Expiry",    "width": 110},
            {"field": "Dir",       "width": 70},
            {"field": "Qty",       "width": 60, "type": "numericColumn"},
            {"field": "Entry Px",  "width": 95},
            {"field": "Mkt Value", "width": 105},
        ],
        rowData=legs,
        defaultColDef={"resizable": True},
        dashGridOptions={"domLayout": "autoHeight"},
        className=T.AGGRID_THEME,
        style={"width": "100%"},
    )


# ── Modal body builders ───────────────────────────────────────────────────────

def _build_ic_modal_body(
    grp: pd.DataFrame,
    underlying: str,
    strategy: str,
    open_date,
    tgid: str,
) -> list:
    """Full Iron Condor position detail modal body."""
    # Live prices for current-price marker + position value
    spot: float | None = None
    live_prices: dict = {}
    try:
        from dash_app import get_polygon_api_key
        from engine.positions import fetch_stock_price, fetch_option_prices
        api_key = get_polygon_api_key()
        if api_key:
            spot = fetch_stock_price(api_key, underlying)
            live_prices = fetch_option_prices(api_key, grp)
    except Exception:
        pass

    opt = grp[grp["SecurityType"].str.lower() == "option"].copy()

    opt["Strike"]           = pd.to_numeric(opt["Strike"],           errors="coerce")
    opt["TransactionPrice"] = pd.to_numeric(opt["TransactionPrice"], errors="coerce")
    opt["Quantity"]         = pd.to_numeric(opt["Quantity"],         errors="coerce").fillna(1)
    opt["Multiplier"]       = pd.to_numeric(opt["Multiplier"],       errors="coerce").fillna(100)

    # Compute key IC parameters
    net_credit = 0.0
    for _, r in opt.iterrows():
        sign = -1.0 if str(r.get("Direction", "")).upper() == "BUY" else 1.0
        net_credit += sign * float(r.get("TransactionPrice") or 0)

    short_calls = opt[(opt["OptionType"].str.lower() == "call") & (opt["Direction"].str.upper() == "SELL")]
    short_puts  = opt[(opt["OptionType"].str.lower() == "put")  & (opt["Direction"].str.upper() == "SELL")]
    long_calls  = opt[(opt["OptionType"].str.lower() == "call") & (opt["Direction"].str.upper() == "BUY")]
    long_puts   = opt[(opt["OptionType"].str.lower() == "put")  & (opt["Direction"].str.upper() == "BUY")]

    short_call_k = float(short_calls["Strike"].iloc[0]) if not short_calls.empty else None
    short_put_k  = float(short_puts["Strike"].iloc[0])  if not short_puts.empty  else None
    long_call_k  = float(long_calls["Strike"].iloc[0])  if not long_calls.empty  else None
    long_put_k   = float(long_puts["Strike"].iloc[0])   if not long_puts.empty   else None

    profit_target = net_credit * 0.50
    stop_loss     = -net_credit * 2.0
    be_upper      = (short_call_k + net_credit) if short_call_k else None
    be_lower      = (short_put_k  - net_credit) if short_put_k  else None

    # Max loss = (wider spread width − net credit) × multiplier × contracts
    call_width = (float(long_calls["Strike"].iloc[0]) - float(short_calls["Strike"].iloc[0])
                  if not long_calls.empty and not short_calls.empty else 0.0)
    put_width  = (float(short_puts["Strike"].iloc[0]) - float(long_puts["Strike"].iloc[0])
                  if not long_puts.empty and not short_puts.empty else 0.0)
    spread_width = max(call_width, put_width) if (call_width > 0 or put_width > 0) else 0.0
    multiplier   = float(opt["Multiplier"].iloc[0]) if not opt.empty else 100.0
    contracts    = abs(float(opt["Quantity"].iloc[0])) if not opt.empty else 1.0
    max_loss     = -(spread_width - net_credit) * multiplier * contracts

    # DTE remaining
    exp_dates     = opt["Expiration"].dropna()
    dte_remaining = None
    expiry_str    = None
    if not exp_dates.empty:
        try:
            expiry        = pd.to_datetime(exp_dates.iloc[0]).date()
            expiry_str    = str(expiry)
            dte_remaining = (expiry - datetime.date.today()).days
        except Exception:
            pass

    # Days held
    try:
        days_held = (datetime.date.today() - pd.to_datetime(open_date).date()).days
    except Exception:
        days_held = None

    # Alerts (no live P&L — pass None for upnl)
    from engine.positions import compute_position_alerts
    ne_full = _net_entry(grp)
    alerts  = compute_position_alerts(grp, strategy, None, ne_full)

    # Exit recommendation
    exit_banner = None
    if dte_remaining is not None and dte_remaining <= 21:
        msg = (f"21 DTE rule — {dte_remaining} days to expiry. "
               "Strategy rules say CLOSE NOW to avoid gamma risk.")
        exit_banner = html.Div(msg, style={
            "padding": "8px 14px",
            "background": "#451a00",
            "border": f"1px solid {T.WARNING}",
            "borderLeft": f"3px solid {T.WARNING}",
            "borderRadius": "6px",
            "color": T.WARNING,
            "fontSize": "13px",
            "marginBottom": "10px",
        })
    # (50% target and 2× stop would need live P&L; shown only from alerts)

    # 5-column metric row — all dollar values use per-contract (×multiplier×contracts)
    net_credit_dollar   = net_credit * multiplier * contracts
    profit_target_dollar = net_credit_dollar * 0.50
    stop_loss_dollar    = -net_credit_dollar * 2.0
    dte_str  = str(dte_remaining) if dte_remaining is not None else "—"
    days_str = str(days_held)     if days_held     is not None else "—"
    max_loss_str = f"${max_loss:,.2f}" if spread_width > 0 else "—"

    # Current position value from live marks
    pos_val: float | None = None
    if live_prices:
        running, all_ok = 0.0, True
        for _, r in grp.iterrows():
            sym  = str(r.get("Symbol", ""))
            dirn = str(r.get("Direction", "")).upper()
            qty  = float(r.get("Quantity") or 0)
            mult = float(r.get("Multiplier") or 100)
            live = live_prices.get(sym, {})
            cur  = live.get("price") if isinstance(live, dict) else None
            if cur is None:
                all_ok = False; break
            sign = 1.0 if dirn == "SELL" else -1.0
            running += sign * cur * abs(qty) * mult
        if all_ok:
            pos_val = round(running, 2)

    pos_val_str   = f"${pos_val:,.2f}"  if pos_val is not None else "—"
    pos_val_color = (T.SUCCESS if pos_val is not None and pos_val >= 0
                     else T.DANGER if pos_val is not None else T.TEXT_MUTED)

    metrics  = html.Div([
        _metric_card("Net Credit",      f"${net_credit_dollar:,.2f}",    T.SUCCESS if net_credit >= 0 else T.DANGER),
        _metric_card("Max Loss",        max_loss_str,                    T.DANGER),
        _metric_card("50% Target",      f"${profit_target_dollar:,.2f}", T.SUCCESS),
        _metric_card("2× Stop",         f"${stop_loss_dollar:,.2f}",     T.DANGER),
        _metric_card("Position Value",  pos_val_str,                     pos_val_color),
        _metric_card("DTE Remaining",   dte_str,
                     T.DANGER if (dte_remaining or 999) <= 7 else
                     (T.WARNING if (dte_remaining or 999) <= 21 else T.TEXT_PRIMARY)),
        _metric_card("Days Held",       days_str),
    ], style={"display": "flex", "gap": "10px", "flexWrap": "wrap", "marginBottom": "14px"})

    # Payoff chart
    ic_fig = _plot_ic_payoff(
        opt=opt,
        net_credit=net_credit,
        short_call_k=short_call_k, short_put_k=short_put_k,
        long_call_k=long_call_k,  long_put_k=long_put_k,
        profit_target=profit_target, stop_loss=stop_loss,
        be_upper=be_upper, be_lower=be_lower,
        dte_remaining=dte_remaining, expiry_str=expiry_str,
        spot=spot,
    )
    chart = dcc.Graph(figure=ic_fig, config={"displayModeBar": False}) if ic_fig else html.P(
        "No payoff chart available.", style={"color": T.TEXT_MUTED}
    )
    chart_caption = html.P(
        "Solid purple = P&L at expiry · Dotted green = P&L today (BS, 25% IV) · "
        "Green/red dashed = strategy exit rules · Grey dotted = breakevens",
        style={"color": T.TEXT_MUTED, "fontSize": "11px", "marginTop": "4px"},
    )

    def _ic_leg_order(row):
        otype = str(row.get("OptionType", "")).lower()
        dirn  = str(row.get("Direction",  "")).upper()
        if otype == "put"  and dirn == "SELL": return 0
        if otype == "put"  and dirn == "BUY":  return 1
        if otype == "call" and dirn == "SELL": return 2
        if otype == "call" and dirn == "BUY":  return 3
        return 4
    grp_sorted = grp.loc[sorted(grp.index, key=lambda i: _ic_leg_order(grp.loc[i]))]
    legs_table = _build_legs_table(grp_sorted, live_prices)

    children = [
        _render_alert_badges(alerts),
        metrics,
    ]
    if exit_banner:
        children.append(exit_banner)
    children += [
        html.Div(style={"marginBottom": "6px"}),
        chart,
        chart_caption,
        html.Hr(style={"borderColor": T.BORDER, "margin": "14px 0"}),
        html.Div("Legs", style={
            "color": T.TEXT_MUTED, "fontSize": "11px", "fontWeight": "600",
            "textTransform": "uppercase", "marginBottom": "6px",
        }),
        legs_table,
    ]
    return children


def _build_screener_modal_body(
    grp: pd.DataFrame,
    underlying: str,
    strategy: str,
    open_date,
) -> list:
    """Options spread / screener position detail modal body."""
    # Live prices: spot for chart marker, option marks for position value + legs table
    spot: float | None = None
    live_prices: dict  = {}
    try:
        from dash_app import get_polygon_api_key
        from engine.positions import fetch_stock_price, fetch_option_prices
        api_key = get_polygon_api_key()
        if api_key and underlying:
            spot        = fetch_stock_price(api_key, underlying)
            live_prices = fetch_option_prices(api_key, grp)
    except Exception:
        pass

    opt = grp[grp["SecurityType"].str.lower() == "option"].copy() \
        if "SecurityType" in grp.columns else pd.DataFrame()

    if opt.empty:
        # No options — fall through to generic payoff
        fig = _plot_payoff(grp, spot)
        return [
            html.P("No option legs found.", style={"color": T.TEXT_MUTED}),
            dcc.Graph(figure=fig, config={"displayModeBar": False}) if fig else html.Div(),
            _build_legs_table(grp, live_prices),
        ]

    opt["Strike"]           = pd.to_numeric(opt["Strike"],           errors="coerce")
    opt["TransactionPrice"] = pd.to_numeric(opt["TransactionPrice"], errors="coerce")
    opt["Quantity"]         = pd.to_numeric(opt["Quantity"],         errors="coerce").fillna(1)
    opt["Multiplier"]       = pd.to_numeric(opt["Multiplier"],       errors="coerce").fillna(100)

    net_credit = 0.0
    for _, r in opt.iterrows():
        sign = -1.0 if str(r.get("Direction", "")).upper() == "BUY" else 1.0
        net_credit += sign * float(r.get("TransactionPrice") or 0)

    is_credit    = net_credit >= 0
    label_type   = "Net Credit" if is_credit else "Net Debit"
    profit_target = abs(net_credit) * 0.50

    # DTE remaining
    exp_dates     = opt["Expiration"].dropna()
    dte_remaining = None
    if not exp_dates.empty:
        try:
            expiry        = pd.to_datetime(exp_dates.iloc[0]).date()
            dte_remaining = (expiry - datetime.date.today()).days
        except Exception:
            pass

    # Days held
    try:
        days_held = (datetime.date.today() - pd.to_datetime(open_date).date()).days
    except Exception:
        days_held = None

    # Alerts
    from engine.positions import compute_position_alerts
    ne_full = _net_entry(grp)
    alerts  = compute_position_alerts(grp, strategy, None, ne_full)

    multiplier_gen = float(opt["Multiplier"].iloc[0]) if not opt.empty else 100.0
    contracts_gen  = abs(float(opt["Quantity"].iloc[0])) if not opt.empty else 1.0
    net_credit_dollar_gen   = net_credit * multiplier_gen * contracts_gen
    profit_target_dollar_gen = abs(net_credit_dollar_gen) * 0.50
    dte_str  = str(dte_remaining) if dte_remaining is not None else "—"
    days_str = str(days_held)     if days_held     is not None else "—"

    # Current position value from live marks
    pos_val: float | None = None
    if live_prices:
        running, all_ok = 0.0, True
        for _, r in grp.iterrows():
            sym  = str(r.get("Symbol", ""))
            dirn = str(r.get("Direction", "")).upper()
            qty  = float(r.get("Quantity") or 0)
            mult = float(r.get("Multiplier") or 100)
            live = live_prices.get(sym, {})
            cur  = live.get("price") if isinstance(live, dict) else None
            if cur is None:
                all_ok = False; break
            sign = 1.0 if dirn == "SELL" else -1.0
            running += sign * cur * abs(qty) * mult
        if all_ok:
            pos_val = round(running, 2)

    pos_val_str   = f"${pos_val:,.2f}"  if pos_val is not None else "—"
    pos_val_color = (T.SUCCESS if pos_val is not None and pos_val >= 0
                     else T.DANGER if pos_val is not None else T.TEXT_MUTED)

    metrics  = html.Div([
        _metric_card(label_type,       f"${net_credit_dollar_gen:,.2f}",    T.SUCCESS if is_credit else T.DANGER),
        _metric_card("50% Target",     f"${profit_target_dollar_gen:,.2f}", T.SUCCESS),
        _metric_card("Position Value", pos_val_str,                         pos_val_color),
        _metric_card("DTE Remaining",  dte_str,
                     T.DANGER if (dte_remaining or 999) <= 7 else
                     (T.WARNING if (dte_remaining or 999) <= 21 else T.TEXT_PRIMARY)),
        _metric_card("Days Held",      days_str),
    ], style={"display": "flex", "gap": "10px", "flexWrap": "wrap", "marginBottom": "14px"})

    # Exit hints
    hints = []
    if dte_remaining is not None and dte_remaining <= 14:
        hints.append(html.Div(
            f"{dte_remaining} DTE — consider closing to avoid gamma/pin risk at expiry.",
            style={
                "padding": "8px 14px",
                "background": "#451a00",
                "border": f"1px solid {T.WARNING}",
                "borderLeft": f"3px solid {T.WARNING}",
                "borderRadius": "6px",
                "color": T.WARNING,
                "fontSize": "13px",
                "marginBottom": "10px",
            }
        ))

    payoff_fig = _plot_payoff(grp, spot)
    chart      = dcc.Graph(figure=payoff_fig, config={"displayModeBar": False}) if payoff_fig else html.Div()
    caption    = html.P(
        "Payoff at expiration · Coloured dotted lines = strike levels · "
        "Green fill = profit zone · Red fill = loss zone",
        style={"color": T.TEXT_MUTED, "fontSize": "11px", "marginTop": "4px"},
    )

    legs_table = _build_legs_table(grp, live_prices)

    return [
        _render_alert_badges(alerts),
        metrics,
        *hints,
        chart,
        caption,
        html.Hr(style={"borderColor": T.BORDER, "margin": "14px 0"}),
        html.Div("Legs", style={
            "color": T.TEXT_MUTED, "fontSize": "11px", "fontWeight": "600",
            "textTransform": "uppercase", "marginBottom": "6px",
        }),
        legs_table,
    ]


def _build_equity_modal_body(
    grp: pd.DataFrame,
    underlying: str,
    strategy: str,
    open_date,
) -> list:
    """Equity position detail modal body."""
    buy_rows = grp[grp["Direction"].str.upper() == "BUY"] \
        if "Direction" in grp.columns else grp

    entry_px = 0.0
    qty      = 0.0
    if not buy_rows.empty:
        entry_px = float(buy_rows["TransactionPrice"].iloc[0] or 0)
        qty      = float(buy_rows["Quantity"].iloc[0] or 1)

    try:
        days_held = (datetime.date.today() - pd.to_datetime(open_date).date()).days
    except Exception:
        days_held = None

    ne_full = _net_entry(grp)

    from engine.positions import compute_position_alerts
    alerts  = compute_position_alerts(grp, strategy, None, ne_full)

    days_str = str(days_held) if days_held is not None else "—"
    cur_val  = entry_px * qty if entry_px > 0 else 0.0
    metrics  = html.Div([
        _metric_card("Entry Price",  f"${entry_px:,.2f}" if entry_px > 0 else "—"),
        _metric_card("Quantity",     f"{qty:.0f} shares"),
        _metric_card("Entry Value",  f"${cur_val:,.2f}" if cur_val > 0 else "—"),
        _metric_card("Days Held",    days_str),
    ], style={"display": "flex", "gap": "10px", "flexWrap": "wrap", "marginBottom": "14px"})

    fig   = _plot_equity_pnl(underlying, entry_px, qty, days_held, spot=None)
    chart = dcc.Graph(figure=fig, config={"displayModeBar": False}) if fig else html.Div()

    if entry_px > 0 and qty > 0:
        caption = html.P(
            f"Breakeven: ${entry_px:.2f} · "
            f"+10% target: ${entry_px * 1.10:.2f} (+${entry_px * 0.10 * qty:,.0f}) · "
            f"-10% stop: ${entry_px * 0.90:.2f} (-${entry_px * 0.10 * qty:,.0f})  "
            "(no live price — entry price used as reference)",
            style={"color": T.TEXT_MUTED, "fontSize": "11px", "marginTop": "4px"},
        )
    else:
        caption = html.Div()

    legs_table = _build_legs_table(grp)

    return [
        _render_alert_badges(alerts),
        metrics,
        chart,
        caption,
        html.Hr(style={"borderColor": T.BORDER, "margin": "14px 0"}),
        html.Div("Legs", style={
            "color": T.TEXT_MUTED, "fontSize": "11px", "fontWeight": "600",
            "textTransform": "uppercase", "marginBottom": "6px",
        }),
        legs_table,
    ]


# ── Equity curve from Balance table ──────────────────────────────────────────

def _build_equity_curve():
    """Build equity curve + drawdown from portfolio.Balance table."""
    from sqlalchemy import text as _text
    try:
        engine = _get_engine()
        with engine.connect() as conn:
            df = pd.read_sql(_text("""
                SELECT BusinessDate, Amount
                FROM portfolio.Balance
                WHERE AccountId = :aid AND BalanceType = 'Cash'
                ORDER BY BusinessDate ASC
            """), conn, params={"aid": _ACCOUNT_ID})
    except Exception:
        df = pd.DataFrame()

    if df.empty:
        return html.P(
            "No balance history. Run a Close of Business in Paper Trading first.",
            style={"color": T.TEXT_MUTED, "fontSize": "13px", "padding": "10px 0"},
        )

    df["BusinessDate"] = pd.to_datetime(df["BusinessDate"])
    df["Amount"]       = pd.to_numeric(df["Amount"], errors="coerce")
    df = df.dropna()

    if df.empty:
        return html.Div()

    # Equity curve
    fig_eq = go.Figure()
    fig_eq.add_trace(go.Scatter(
        x=df["BusinessDate"], y=df["Amount"],
        mode="lines",
        line=dict(color=T.ACCENT, width=2),
        fill="tozeroy", fillcolor=f"rgba(99,102,241,0.06)",
        hovertemplate="%{x|%Y-%m-%d}<br>$%{y:,.0f}<extra></extra>",
    ))
    fig_eq.add_hline(y=100_000, line=dict(color=T.BORDER_BRT, width=1, dash="dash"),
                     annotation_text="Starting $100k",
                     annotation_font_color=T.TEXT_MUTED)
    fig_eq.update_layout(
        title=dict(text="Portfolio — Net Liquidation (Cash Balance)", font=dict(size=12, color=T.TEXT_SEC)),
        template="plotly_dark",
        paper_bgcolor=T.BG_CARD, plot_bgcolor=T.BG_CARD,
        font=dict(color=T.TEXT_SEC, size=11),
        height=260, margin=dict(l=0, r=0, t=40, b=0),
        yaxis=dict(tickformat="$,.0f", gridcolor=T.BORDER, zeroline=False),
        xaxis=dict(gridcolor=T.BORDER),
        showlegend=False,
    )

    # Drawdown
    amounts = df["Amount"].values
    running_max = np.maximum.accumulate(amounts)
    drawdown = (amounts - running_max) / running_max * 100

    fig_dd = go.Figure()
    fig_dd.add_trace(go.Scatter(
        x=df["BusinessDate"], y=drawdown,
        mode="lines",
        line=dict(color=T.DANGER, width=1),
        fill="tozeroy", fillcolor="rgba(239,68,68,0.15)",
        hovertemplate="%{x|%Y-%m-%d}<br>DD: %{y:.1f}%<extra></extra>",
    ))
    fig_dd.update_layout(
        title=dict(text="Drawdown %", font=dict(size=12, color=T.TEXT_SEC)),
        template="plotly_dark",
        paper_bgcolor=T.BG_CARD, plot_bgcolor=T.BG_CARD,
        font=dict(color=T.TEXT_SEC, size=11),
        height=160, margin=dict(l=0, r=0, t=40, b=0),
        yaxis=dict(tickformat=".1f", ticksuffix="%", gridcolor=T.BORDER, zeroline=False),
        xaxis=dict(gridcolor=T.BORDER),
        showlegend=False,
    )

    return html.Div([
        dbc.Card(dbc.CardBody(dcc.Graph(figure=fig_eq, config={"displayModeBar": False})),
                 style={**T.STYLE_CARD, "marginBottom": "12px"}),
        dbc.Card(dbc.CardBody(dcc.Graph(figure=fig_dd, config={"displayModeBar": False})),
                 style=T.STYLE_CARD),
    ])


# ── Layout ────────────────────────────────────────────────────────────────────

def layout() -> html.Div:
    modal = dbc.Modal([
        dbc.ModalHeader(
            dbc.ModalTitle(id="pt-modal-title", children="Position Detail"),
            style={"backgroundColor": T.BG_ELEVATED, "borderBottom": f"1px solid {T.BORDER}"},
            close_button=True,
        ),
        dbc.ModalBody(
            dcc.Loading(
                html.Div(id="pt-modal-body"),
                type="circle", color=T.ACCENT,
            ),
            style={"backgroundColor": T.BG_BASE, "padding": "20px"},
        ),
        dbc.ModalFooter([
            dbc.Button(
                "Close Position", id="pt-close-btn", color="danger", size="sm",
                style={"marginRight": "8px"},
            ),
            dbc.Button(
                "Dismiss", id="pt-modal-dismiss", color="secondary", size="sm",
            ),
        ], style={"backgroundColor": T.BG_ELEVATED, "borderTop": f"1px solid {T.BORDER}"}),
    ], id="pt-modal", size="xl", is_open=False, scrollable=True)

    return html.Div([
        html.Div([
            html.Div([
                html.H2("Paper Trading", style={
                    "color": T.TEXT_PRIMARY, "fontSize": "1.35rem",
                    "fontWeight": "700", "marginBottom": "0",
                }),
            ]),
            dbc.Button(
                "Refresh", id="pt-refresh-btn", size="sm", outline=True,
                style={"borderColor": T.BORDER, "color": T.TEXT_SEC, "fontSize": "12px"},
            ),
        ], style={"display": "flex", "justifyContent": "space-between",
                  "alignItems": "center", "marginBottom": "16px"}),

        html.Div(id="pt-metric-row", style={"marginBottom": "16px"}),

        dbc.Tabs([
            dbc.Tab(label="Open Positions", tab_id="open", children=[
                html.Div(style={"height": "12px"}),
                html.P(
                    "Click a row to view position detail and payoff chart.",
                    style={"color": T.TEXT_MUTED, "fontSize": "12px", "marginBottom": "4px"},
                ),
                dcc.Loading(_grid("pt-open-grid", _OPEN_COLS),
                            type="circle", color=T.ACCENT),
            ]),
            dbc.Tab(label="Closed Positions", tab_id="closed", children=[
                html.Div(style={"height": "12px"}),
                html.Div(id="pt-closed-chart", style={"marginBottom": "16px"}),
                dcc.Loading(_grid("pt-closed-grid", _CLOSED_COLS),
                            type="circle", color=T.ACCENT),
            ]),
            dbc.Tab(label="Transactions", tab_id="txns", children=[
                html.Div(style={"height": "12px"}),
                # Delete controls
                dbc.Row([
                    dbc.Col(dbc.Card(dbc.CardBody([
                        html.Div("Delete by date", style={"color": T.TEXT_SEC, "fontSize": "11px",
                                                           "fontWeight": "600", "marginBottom": "8px"}),
                        dcc.Dropdown(id="pt-del-date-picker", placeholder="Select date…",
                                     clearable=True, className="dash-dropdown",
                                     style={"fontSize": "12px", "marginBottom": "8px",
                                            "backgroundColor": T.BG_ELEVATED}),
                        dbc.Button("Delete this date", id="pt-del-date-btn", color="danger",
                                   size="sm", outline=True, style={"width": "100%", "fontSize": "12px"}),
                    ]), style={**T.STYLE_CARD, "padding": "12px"}), width=4),
                    dbc.Col(dbc.Card(dbc.CardBody([
                        html.Div("Delete today only", style={"color": T.TEXT_SEC, "fontSize": "11px",
                                                              "fontWeight": "600", "marginBottom": "8px"}),
                        html.Div(id="pt-del-today-count",
                                 style={"color": T.TEXT_MUTED, "fontSize": "12px", "marginBottom": "8px"}),
                        dbc.Button("Delete today's trades", id="pt-del-today-btn", color="danger",
                                   size="sm", outline=True, style={"width": "100%", "fontSize": "12px"}),
                    ]), style={**T.STYLE_CARD, "padding": "12px"}), width=4),
                    dbc.Col(dbc.Card(dbc.CardBody([
                        html.Div("Delete everything", style={"color": T.TEXT_SEC, "fontSize": "11px",
                                                              "fontWeight": "600", "marginBottom": "8px"}),
                        html.Div(id="pt-del-all-count",
                                 style={"color": T.TEXT_MUTED, "fontSize": "12px", "marginBottom": "8px"}),
                        dbc.Button("Delete ALL transactions", id="pt-del-all-btn", color="danger",
                                   size="sm", style={"width": "100%", "fontSize": "12px"}),
                    ]), style={**T.STYLE_CARD, "padding": "12px"}), width=4),
                ], className="g-2", style={"marginBottom": "12px"}),
                html.Div(id="pt-delete-status-msg", style={"marginBottom": "8px"}),
                # Cash record form
                dbc.Card(dbc.CardBody([
                    html.Div("Record Cash Movement", style={
                        "color": T.TEXT_SEC, "fontSize": "11px", "fontWeight": "600",
                        "textTransform": "uppercase", "marginBottom": "10px",
                    }),
                    dbc.Row([
                        dbc.Col(dbc.Select(
                            id="pt-cash-dir",
                            options=[{"label": "Deposit", "value": "DEPOSIT"},
                                     {"label": "Withdrawal", "value": "WITHDRAWAL"}],
                            value="DEPOSIT",
                            style={"fontSize": "13px", "backgroundColor": T.BG_ELEVATED,
                                   "border": f"1px solid {T.BORDER}", "color": T.TEXT_PRIMARY},
                        ), width=3),
                        dbc.Col(dbc.Input(
                            id="pt-cash-amount", type="number", placeholder="Amount",
                            min=0, step=100,
                            style={"fontSize": "13px", "backgroundColor": T.BG_ELEVATED,
                                   "border": f"1px solid {T.BORDER}", "color": T.TEXT_PRIMARY},
                        ), width=3),
                        dbc.Col(dbc.Input(
                            id="pt-cash-notes", type="text", placeholder="Notes (optional)",
                            style={"fontSize": "13px", "backgroundColor": T.BG_ELEVATED,
                                   "border": f"1px solid {T.BORDER}", "color": T.TEXT_PRIMARY},
                        ), width=4),
                        dbc.Col(dbc.Button(
                            "Record", id="pt-cash-save", color="primary", size="sm",
                            style={"backgroundColor": T.ACCENT, "border": "none",
                                   "fontSize": "13px", "width": "100%"},
                        ), width=2),
                    ], align="center"),
                    html.Div(id="pt-cash-status", style={"marginTop": "6px"}),
                ]), style={**T.STYLE_CARD, "marginBottom": "12px"}),
                # Filters
                dbc.Card(dbc.CardBody([
                    dbc.Row([
                        dbc.Col(dbc.Input(
                            id="pt-txn-search", type="text",
                            placeholder="Search symbol / strategy / notes…",
                            style={"fontSize": "13px", "backgroundColor": T.BG_ELEVATED,
                                   "border": f"1px solid {T.BORDER}", "color": T.TEXT_PRIMARY},
                        ), width=4),
                        dbc.Col(dcc.Dropdown(
                            id="pt-txn-filter-type", placeholder="Security Type",
                            clearable=True, className="dash-dropdown",
                            style={"fontSize": "13px", "backgroundColor": T.BG_ELEVATED},
                        ), width=2),
                        dbc.Col(dcc.Dropdown(
                            id="pt-txn-filter-dir", placeholder="Direction",
                            clearable=True, className="dash-dropdown",
                            style={"fontSize": "13px", "backgroundColor": T.BG_ELEVATED},
                        ), width=2),
                        dbc.Col(dcc.Dropdown(
                            id="pt-txn-filter-strat", placeholder="Strategy",
                            clearable=True, className="dash-dropdown",
                            style={"fontSize": "13px", "backgroundColor": T.BG_ELEVATED},
                        ), width=4),
                    ], align="center"),
                ]), style={**T.STYLE_CARD, "marginBottom": "8px", "padding": "8px"}),
                html.Div(id="pt-txn-count", style={
                    "color": T.TEXT_MUTED, "fontSize": "12px", "marginBottom": "4px",
                }),
                dcc.Loading(_grid("pt-txns-grid", _TXNS_COLS),
                            type="circle", color=T.ACCENT),
            ]),
            dbc.Tab(label="Performance", tab_id="perf", children=[
                html.Div(style={"height": "12px"}),
                dcc.Loading(
                    html.Div(id="pt-perf-chart"),
                    type="circle", color=T.ACCENT,
                ),
                html.Div(style={"height": "16px"}),
                dcc.Loading(
                    html.Div(id="pt-equity-curve"),
                    type="circle", color=T.ACCENT,
                ),
            ]),
            dbc.Tab(label="Risk", tab_id="risk", children=[
                html.Div(style={"height": "12px"}),
                # ── Config row ───────────────────────────────────────────────
                dbc.Card(dbc.CardBody([
                    html.Div([
                        html.Div([
                            html.Label("Step size", style={"color": T.TEXT_SEC, "fontSize": "11px",
                                "fontWeight": "600", "marginBottom": "4px"}),
                            dbc.Input(id="pt-risk-step", type="number", value=2, min=1, max=10, step=1,
                                      style={"width": "80px", "fontSize": "12px",
                                             "backgroundColor": T.BG_ELEVATED, "color": "#e5e7eb",
                                             "border": f"1px solid {T.BORDER}"}),
                        ]),
                        html.Div([
                            html.Label("Vol Up %", style={"color": T.TEXT_SEC, "fontSize": "11px",
                                "fontWeight": "600", "marginBottom": "4px"}),
                            dbc.Input(id="pt-risk-vol-up", type="number", value=25, min=1, max=200,
                                      style={"width": "80px", "fontSize": "12px",
                                             "backgroundColor": T.BG_ELEVATED, "color": "#e5e7eb",
                                             "border": f"1px solid {T.BORDER}"}),
                        ]),
                        html.Div([
                            html.Label("Vol Down %", style={"color": T.TEXT_SEC, "fontSize": "11px",
                                "fontWeight": "600", "marginBottom": "4px"}),
                            dbc.Input(id="pt-risk-vol-down", type="number", value=25, min=1, max=200,
                                      style={"width": "80px", "fontSize": "12px",
                                             "backgroundColor": T.BG_ELEVATED, "color": "#e5e7eb",
                                             "border": f"1px solid {T.BORDER}"}),
                        ]),
                        html.Div([
                            html.Label("Default IV %", style={"color": T.TEXT_SEC, "fontSize": "11px",
                                "fontWeight": "600", "marginBottom": "4px"}),
                            dbc.Input(id="pt-risk-iv-default", type="number", value=20, min=1, max=300,
                                      style={"width": "80px", "fontSize": "12px",
                                             "backgroundColor": T.BG_ELEVATED, "color": "#e5e7eb",
                                             "border": f"1px solid {T.BORDER}"}),
                        ]),
                        html.Div([
                            html.Label("Rate %", style={"color": T.TEXT_SEC, "fontSize": "11px",
                                "fontWeight": "600", "marginBottom": "4px"}),
                            dbc.Input(id="pt-risk-rate", type="number", value=4.3, min=0, max=20, step=0.1,
                                      style={"width": "80px", "fontSize": "12px",
                                             "backgroundColor": T.BG_ELEVATED, "color": "#e5e7eb",
                                             "border": f"1px solid {T.BORDER}"}),
                        ]),
                        html.Div([
                            html.Label("\u00a0", style={"fontSize": "11px", "marginBottom": "4px",
                                                         "display": "block"}),
                            dbc.Button("Calculate", id="pt-risk-calc-btn", size="sm",
                                       color="primary", style={"fontSize": "12px"}),
                        ]),
                    ], style={"display": "flex", "gap": "16px", "alignItems": "flex-end",
                               "flexWrap": "wrap"}),
                ]), style={**T.STYLE_CARD, "marginBottom": "12px"}),

                dcc.Store(id="pt-risk-position", data="__all__"),
                dcc.Store(id="pt-risk-leg",      data="__all__"),

                # Row 1: position pills
                html.Div(id="pt-risk-pos-pills", style={"marginBottom": "6px"}),
                # Row 2: leg pills (shown only when a position is selected)
                html.Div(id="pt-risk-leg-pills", style={"marginBottom": "10px"}),

                dcc.Loading(
                    html.Div(id="pt-risk-matrix"),
                    type="circle", color=T.ACCENT,
                ),
            ]),
        ], id="pt-tabs", active_tab="open",
           style={"borderBottom": f"1px solid {T.BORDER}"}),

        # Modal for position detail
        modal,

        # ── Close-trade confirmation modal ────────────────────────────────────
        dbc.Modal([
            dbc.ModalHeader(
                dbc.ModalTitle("Confirm Close Position"),
                style={"backgroundColor": T.BG_ELEVATED, "borderBottom": f"1px solid {T.BORDER}"},
            ),
            dbc.ModalBody([
                dbc.Alert(
                    "Each leg will close at its entry price (no live prices loaded). "
                    "Refresh live prices first for accurate fills.",
                    color="warning",
                    style={"fontSize": "12px", "marginBottom": "12px"},
                ),
                html.Div(id="pt-close-confirm-body"),
            ], style={"backgroundColor": T.BG_BASE}),
            dbc.ModalFooter([
                dbc.Button("Confirm Close", id="pt-close-confirm-btn", color="danger", size="sm",
                           style={"marginRight": "8px"}),
                dbc.Button("Cancel", id="pt-close-cancel-btn", color="secondary", size="sm"),
            ], style={"backgroundColor": T.BG_ELEVATED, "borderTop": f"1px solid {T.BORDER}"}),
        ], id="pt-close-confirm-modal", size="lg", is_open=False),

        # ── Delete confirmation modal ─────────────────────────────────────────
        dbc.Modal([
            dbc.ModalHeader(
                dbc.ModalTitle("Confirm Delete"),
                style={"backgroundColor": T.BG_ELEVATED, "borderBottom": f"1px solid {T.BORDER}"},
            ),
            dbc.ModalBody(
                html.Div(id="pt-delete-confirm-body"),
                style={"backgroundColor": T.BG_BASE},
            ),
            dbc.ModalFooter([
                dbc.Button("Confirm Delete", id="pt-delete-confirm-btn", color="danger", size="sm",
                           style={"marginRight": "8px"}),
                dbc.Button("Cancel", id="pt-delete-cancel-btn", color="secondary", size="sm"),
            ], style={"backgroundColor": T.BG_ELEVATED, "borderTop": f"1px solid {T.BORDER}"}),
        ], id="pt-delete-modal", size="md", is_open=False),

        # Stores
        dcc.Store(id="pt-selected-tgid",    data=""),
        dcc.Store(id="pt-delete-action",    data=""),   # "date:{d}", "today", "all"
        dcc.Store(id="pt-delete-status",    data=""),

        dcc.Interval(id="pt-refresh", interval=60_000, n_intervals=0),
        dcc.Location(id="pt-url", refresh=False),
    ], style=T.STYLE_PAGE)


# ── Callbacks ─────────────────────────────────────────────────────────────────

@callback(
    Output("pt-metric-row",        "children"),
    Output("pt-open-grid",         "rowData"),
    Output("pt-closed-grid",       "rowData"),
    Output("pt-closed-chart",      "children"),
    Output("pt-txns-grid",         "rowData"),
    Output("pt-perf-chart",        "children"),
    Output("pt-equity-curve",      "children"),
    Output("pt-txn-filter-type",   "options"),
    Output("pt-txn-filter-dir",    "options"),
    Output("pt-txn-filter-strat",  "options"),
    Output("pt-del-date-picker",   "options"),
    Output("pt-del-today-count",   "children"),
    Output("pt-del-all-count",     "children"),
    Input("pt-refresh",            "n_intervals"),
    Input("pt-refresh-btn",        "n_clicks"),
)
def refresh_all(_n, _btn):
    open_groups, closed_rows, txns_df = _load_data()

    # ── Open positions ────────────────────────────────────────────────────────
    open_data = []
    for tgid, grp in open_groups.items():
        underlying = (
            grp["Underlying"].dropna().iloc[0]
            if "Underlying" in grp.columns and not grp["Underlying"].dropna().empty
            else grp["Symbol"].iloc[0] if not grp.empty else "?"
        )
        ne = _net_entry(grp)
        strategy = str(grp["StrategyName"].iloc[0]) if not grp.empty else "?"

        # DTE — earliest option expiration
        dte = None
        if "Expiration" in grp.columns:
            exps = grp["Expiration"].dropna()
            if not exps.empty:
                try:
                    earliest = pd.to_datetime(exps).min().date()
                    dte = (earliest - datetime.date.today()).days
                except Exception:
                    pass

        # Alerts
        try:
            from engine.positions import compute_position_alerts
            alerts_list = compute_position_alerts(grp, strategy, None, ne)
        except Exception:
            alerts_list = []
        alert_icons = ""
        for a in alerts_list:
            lvl = a.get("level", "")
            if lvl == "error":   alert_icons += "🔴 "
            elif lvl == "warning": alert_icons += "🟡 "
            elif lvl == "success": alert_icons += "🟢 "
        alert_str = alert_icons.strip() if alert_icons else "—"

        open_data.append({
            "Trade Group": str(tgid),
            "Underlying":  str(underlying),
            "Strategy":    strategy,
            "Open Date":   str(grp["BusinessDate"].min())[:10],
            "Legs":        len(grp),
            "DTE":         dte,
            "Net Entry":   f"+${ne:,.2f}" if ne >= 0 else f"-${abs(ne):,.2f}",
            "Alerts":      alert_str,
            "_net":        ne,
            "_tgid":       str(tgid),
        })

    # ── Account info + Cash balance ───────────────────────────────────────────
    try:
        from engine.positions import get_account_info
        engine = _get_engine()
        acct = get_account_info(engine, _ACCOUNT_ID)
    except Exception:
        acct = {"AccountName": "Default", "AccountType": "Paper",
                "Currency": "USD", "Status": "Active"}

    cash_bal = 0.0
    try:
        from sqlalchemy import text as _text
        with engine.connect() as conn:
            row = conn.execute(_text("""
                SELECT TOP 1 Amount FROM portfolio.Balance
                WHERE AccountId = :aid AND BalanceType = 'Cash'
                ORDER BY BusinessDate DESC
            """), {"aid": _ACCOUNT_ID}).fetchone()
            if row:
                cash_bal = float(row[0])
    except Exception:
        pass

    # ── Metrics ───────────────────────────────────────────────────────────────
    n_open       = len(open_data)
    total_entry  = sum(r["_net"] for r in open_data)
    total_closed = sum(r["P&L $"] for r in closed_rows) if closed_rows else 0.0
    n_wins       = sum(1 for r in closed_rows if r.get("P&L $", 0) > 0) if closed_rows else 0
    ytd_return   = total_closed / 100_000 * 100

    today_str  = datetime.date.today().isoformat()
    today_pnl  = sum(
        r.get("P&L $", 0) for r in closed_rows
        if str(r.get("Close Date", ""))[:10] == today_str
    ) if closed_rows else 0.0

    n_closed     = len(closed_rows) if closed_rows else 0
    win_rate     = (n_wins / n_closed * 100) if n_closed > 0 else None
    gross_wins   = sum(r.get("P&L $", 0) for r in closed_rows if r.get("P&L $", 0) > 0) if closed_rows else 0.0
    gross_losses = abs(sum(r.get("P&L $", 0) for r in closed_rows if r.get("P&L $", 0) < 0)) if closed_rows else 0.0
    net_premium  = sum(r["_net"] for r in open_data)

    def _metric(label, value, color=T.TEXT_PRIMARY):
        return html.Div([
            html.Div(label, style={
                "color": T.TEXT_MUTED, "fontSize": "10px", "fontWeight": "600",
                "textTransform": "uppercase", "letterSpacing": "0.07em",
                "marginBottom": "5px",
            }),
            html.Div(value, style={"color": color, "fontSize": "1.1rem", "fontWeight": "700"}),
        ], style={**T.STYLE_CARD, "minWidth": "110px", "flex": "1", "padding": "10px 12px"})

    status_color = T.SUCCESS if acct.get("Status") == "Active" else T.WARNING
    win_rate_str = f"{win_rate:.0f}%" if win_rate is not None else "—"
    win_rate_color = (T.SUCCESS if win_rate and win_rate >= 50 else T.DANGER) if win_rate is not None else T.TEXT_MUTED
    net_prem_str = f"{'+'if net_premium>=0 else ''}${net_premium:,.2f}"

    row1 = html.Div([
        _metric("Account",      str(acct.get("AccountName", "—"))),
        _metric("Type",         str(acct.get("AccountType", "—"))),
        _metric("Status",       str(acct.get("Status", "—")), status_color),
        _metric("Cash Balance", f"${cash_bal:,.0f}",
                T.SUCCESS if cash_bal >= 0 else T.DANGER),
    ], style={"display": "flex", "gap": "10px", "flexWrap": "wrap"})

    row2 = html.Div([
        _metric("Open Trades",   str(n_open)),
        _metric("Net Premium",   net_prem_str,
                T.SUCCESS if net_premium > 0 else T.DANGER if net_premium < 0 else T.TEXT_MUTED),
        _metric("Today's P&L",  f"{'+'if today_pnl>=0 else ''}${today_pnl:,.2f}",
                T.SUCCESS if today_pnl > 0 else T.DANGER if today_pnl < 0 else T.TEXT_MUTED),
        _metric("Realized P&L", f"{'+'if total_closed>=0 else ''}${total_closed:,.2f}",
                T.SUCCESS if total_closed >= 0 else T.DANGER),
        _metric("Win Rate",     win_rate_str, win_rate_color),
        _metric("YTD Return",   f"{'+'if ytd_return>=0 else ''}{ytd_return:.1f}%",
                T.SUCCESS if ytd_return >= 0 else T.DANGER),
    ], style={"display": "flex", "gap": "10px", "flexWrap": "wrap"})

    metrics = html.Div([row1, row2], style={"display": "flex", "flexDirection": "column", "gap": "10px"})

    # ── Closed positions ──────────────────────────────────────────────────────
    closed_data = []
    for r in closed_rows:
        pnl = r.get("P&L $", 0) or 0
        closed_data.append({
            "Underlying": str(r.get("Underlying", "?")),
            "Strategy":   str(r.get("Strategy", "?")),
            "Open Date":  str(r.get("Open Date", ""))[:10],
            "Close Date": str(r.get("Close Date", ""))[:10],
            "P&L":        f"{'+'if pnl>=0 else ''}${pnl:,.2f}",
            "Result":     "WIN" if pnl > 0 else ("LOSS" if pnl < 0 else "BE"),
        })

    # Closed P&L bar chart
    closed_chart = html.Div()
    if closed_rows:
        sorted_closed = sorted(
            [r for r in closed_rows if r.get("Close Date")],
            key=lambda r: str(r["Close Date"]),
        )
        bar_labels = [f"{r.get('Underlying','?')} {str(r.get('Close Date',''))[:10]}"
                      for r in sorted_closed]
        bar_pnls   = [r.get("P&L $", 0) or 0 for r in sorted_closed]
        fig_bar = go.Figure(go.Bar(
            x=bar_labels, y=bar_pnls,
            marker_color=[T.SUCCESS if p >= 0 else T.DANGER for p in bar_pnls],
            hovertemplate="%{x}<br>P&L: $%{y:+,.2f}<extra></extra>",
        ))
        fig_bar.add_hline(y=0, line=dict(color=T.BORDER_BRT, width=1))
        fig_bar.update_layout(
            template="plotly_dark",
            paper_bgcolor=T.BG_CARD, plot_bgcolor=T.BG_CARD,
            font=dict(color=T.TEXT_SEC, size=11),
            height=200, margin=dict(l=0, r=0, t=10, b=60),
            xaxis=dict(gridcolor=T.BORDER, tickangle=-30, tickfont=dict(size=10)),
            yaxis=dict(gridcolor=T.BORDER, tickformat="$,.0f", zeroline=False),
            showlegend=False,
        )
        closed_chart = dbc.Card(dbc.CardBody([
            html.Div("Closed Trade P&L", style={
                "color": T.TEXT_SEC, "fontSize": "11px", "fontWeight": "600",
                "textTransform": "uppercase", "letterSpacing": "0.07em",
                "marginBottom": "8px",
            }),
            dcc.Graph(figure=fig_bar, config={"displayModeBar": False}),
        ]), style={**T.STYLE_CARD})

    # ── All transactions ──────────────────────────────────────────────────────
    txns_data = []
    if not txns_df.empty:
        for _, r in txns_df.iterrows():
            stype = str(r.get("SecurityType", "")).lower()
            px    = r.get("TransactionPrice")
            qty   = float(r.get("Quantity") or 0)
            mult  = float(r.get("Multiplier") or 1)
            dirn  = str(r.get("Direction", "")).upper()
            # Cash flow: deposits positive, withdrawals negative; buys negative, sells positive
            if stype == "cash":
                cf = float(r.get("TransactionPrice") or 0)
            else:
                sign = -1.0 if dirn == "BUY" else 1.0
                cf   = sign * qty * float(px or 0) * mult
            txns_data.append({
                "Date":       str(r.get("BusinessDate", ""))[:10],
                "Underlying": str(r.get("Underlying", "")),
                "Strategy":   str(r.get("StrategyName", "")),
                "Symbol":     str(r.get("Symbol", "")),
                "LegType":    str(r.get("LegType", "")),
                "Direction":  dirn,
                "Qty":        qty,
                "Price":      f"${float(px):,.4f}" if px is not None else "—",
                "Cash Flow":  f"{'+'if cf>=0 else ''}${cf:,.2f}",
                "Type":       str(r.get("SecurityType", "")),
                "Notes":      str(r.get("Notes") or ""),
            })

    # ── Performance chart (closed P&L) ───────────────────────────────────────
    perf_chart = _build_perf_chart(closed_rows)

    # ── Equity curve from Balance table ──────────────────────────────────────
    equity_curve = _build_equity_curve()

    # ── Filter dropdown options from txns_data ────────────────────────────────
    def _opts(vals):
        return [{"label": v, "value": v} for v in sorted(set(v for v in vals if v))]

    type_opts  = _opts(r["Type"]      for r in txns_data)
    dir_opts   = _opts(r["Direction"] for r in txns_data)
    strat_opts = _opts(r["Strategy"]  for r in txns_data)

    # Delete control data
    all_dates     = sorted(set(r["Date"] for r in txns_data if r["Date"]), reverse=True)
    date_opts     = [{"label": d, "value": d} for d in all_dates]
    today_str     = datetime.date.today().isoformat()
    today_count   = sum(1 for r in txns_data if r["Date"] == today_str)
    total_count   = len(txns_data)
    today_caption = f"{today_count} transaction(s) on {today_str}"
    total_caption = f"{total_count} total transaction(s)"

    return (metrics, open_data, closed_data, closed_chart, txns_data, perf_chart, equity_curve,
            type_opts, dir_opts, strat_opts, date_opts, today_caption, total_caption)


# ── Modal open: step 1 — open instantly + store tgid ─────────────────────────

@callback(
    Output("pt-modal",         "is_open",  allow_duplicate=True),
    Output("pt-modal-title",   "children", allow_duplicate=True),
    Output("pt-modal-body",    "children", allow_duplicate=True),
    Output("pt-selected-tgid", "data"),
    Input("pt-open-grid",      "selectedRows"),
    Input("pt-url",            "search"),
    prevent_initial_call=True,
)
def open_position_modal(selected_rows, url_search):
    from dash import ctx
    _loading = html.Div("Loading…", style={"color": T.TEXT_MUTED, "padding": "20px"})
    # Deep-link from blotter: /paper-trading?tgid=xxx
    if ctx.triggered_id == "pt-url" and url_search:
        from urllib.parse import parse_qs, urlparse
        qs = parse_qs(url_search.lstrip("?"))
        tgid = (qs.get("tgid") or [""])[0].strip()
        if tgid:
            return True, "Position Detail", _loading, tgid
        return no_update, no_update, no_update, no_update

    if not selected_rows:
        return no_update, no_update, no_update, no_update

    row = selected_rows[0]
    tgid = str(row.get("_tgid", "") or "").strip()
    if not tgid:
        return no_update, no_update, no_update, no_update

    underlying = str(row.get("Underlying", row.get("Trade Group", "?")))
    strategy   = str(row.get("Strategy", ""))
    title      = f"{underlying}  ·  {strategy}"
    return True, title, _loading, tgid


# ── Modal open: step 2 — build body from tgid ────────────────────────────────

@callback(
    Output("pt-modal-body",    "children"),
    Output("pt-modal-title",   "children", allow_duplicate=True),
    Input("pt-selected-tgid",  "data"),
    prevent_initial_call=True,
)
def build_modal_body(tgid):
    if not tgid:
        return no_update, no_update

    _, _, txns_df = _load_data()
    if txns_df.empty:
        return no_update, no_update

    grp = txns_df[txns_df["TradeGroupId"] == tgid].copy()
    if grp.empty:
        return no_update, no_update

    underlying = (
        grp["Underlying"].dropna().iloc[0]
        if "Underlying" in grp.columns and not grp["Underlying"].dropna().empty
        else grp["Symbol"].iloc[0] if not grp.empty else "?"
    )
    strategy  = str(grp["StrategyName"].iloc[0]) if not grp.empty else "?"
    open_date = str(grp["BusinessDate"].min())[:10] if not grp.empty else ""
    ne        = _net_entry(grp)
    ne_str    = f"{'+' if ne >= 0 else ''}${ne:,.2f}"

    title = f"{underlying}  ·  {strategy}  ·  {ne_str}  ·  opened {open_date}"
    sl    = strategy.lower()

    has_options = (
        "SecurityType" in grp.columns and
        grp["SecurityType"].str.lower().eq("option").any()
    )

    if "condor" in sl and has_options:
        body = _build_ic_modal_body(grp, underlying, strategy, open_date, tgid)
    elif has_options:
        body = _build_screener_modal_body(grp, underlying, strategy, open_date)
    else:
        body = _build_equity_modal_body(grp, underlying, strategy, open_date)

    return body, title


# ── Modal dismiss button ──────────────────────────────────────────────────────

@callback(
    Output("pt-modal",      "is_open",      allow_duplicate=True),
    Output("pt-open-grid",  "selectedRows", allow_duplicate=True),
    Input("pt-modal-dismiss", "n_clicks"),
    prevent_initial_call=True,
)
def dismiss_modal(n_clicks):
    if n_clicks:
        return False, []
    return no_update, no_update


# (Close Position is now handled by open_close_confirm + execute_close below)


# ── Performance chart ─────────────────────────────────────────────────────────

def _build_perf_chart(closed_rows: list[dict]):
    if not closed_rows:
        return html.P("No closed trades yet.", style={"color": T.TEXT_MUTED, "padding": "20px"})

    rows = sorted(
        [r for r in closed_rows if r.get("Close Date")],
        key=lambda r: str(r["Close Date"]),
    )

    if len(rows) < 2:
        return html.P(
            "Not enough trade history — need at least 2 closed trades.",
            style={"color": T.TEXT_MUTED, "padding": "20px"},
        )

    dates   = [str(r["Close Date"])[:10] for r in rows]
    pnls    = [float(r.get("P&L $", 0) or 0) for r in rows]

    # ── Core metrics ─────────────────────────────────────────────────────────
    cum_pnl: list[float] = []
    running = 0.0
    for p in pnls:
        running += p
        cum_pnl.append(running)

    total    = cum_pnl[-1]
    wins_v   = [p for p in pnls if p > 0]
    losses_v = [p for p in pnls if p < 0]
    wins     = len(wins_v)
    losses   = len(losses_v)
    win_rate = wins / len(pnls) * 100
    avg_win  = sum(wins_v)  / wins   if wins   else 0.0
    avg_loss = sum(losses_v) / losses if losses else 0.0

    sum_wins   = sum(wins_v)
    sum_losses = abs(sum(losses_v))
    profit_factor = sum_wins / sum_losses if sum_losses > 0 else float("inf")

    # Sharpe — treat each trade P&L as a "return" relative to $100k capital
    cap = 100_000.0
    returns = np.array([p / cap for p in pnls])
    sharpe = float(np.mean(returns) / np.std(returns) * np.sqrt(252)) if np.std(returns) > 0 else 0.0

    # Max drawdown from cumulative P&L series
    cum_arr     = np.array(cum_pnl)
    running_max = np.maximum.accumulate(cum_arr)
    # avoid div-by-zero when running_max contains zeros (early trades all flat)
    safe_max    = np.where(running_max == 0, 1.0, running_max)
    dd_series   = (cum_arr - running_max) / np.abs(safe_max) * 100
    max_dd      = float(np.min(dd_series))  # most-negative value

    # ── Helper: metric card ──────────────────────────────────────────────────
    _CARD_STYLE = {
        "background": T.BG_CARD,
        "border": f"1px solid {T.BORDER}",
        "borderRadius": "8px",
        "padding": "12px 16px",
        "flex": "1 1 130px",
        "minWidth": "120px",
    }
    _LABEL_STYLE = {"color": T.TEXT_MUTED, "fontSize": "11px",
                    "textTransform": "uppercase", "letterSpacing": "0.06em",
                    "marginBottom": "4px"}
    _VAL_STYLE   = {"fontWeight": "700", "fontSize": "18px"}

    def _card(label: str, value_str: str, color: str = T.TEXT_PRIMARY) -> html.Div:
        return html.Div([
            html.Div(label, style=_LABEL_STYLE),
            html.Div(value_str, style={**_VAL_STYLE, "color": color}),
        ], style=_CARD_STYLE)

    pf_str  = f"{profit_factor:.2f}" if profit_factor != float("inf") else "∞"
    dd_str  = f"{max_dd:.1f}%"
    sr_color = T.SUCCESS if sharpe >= 1.0 else (T.WARNING if sharpe >= 0 else T.DANGER)
    dd_color = T.DANGER if max_dd < -10 else (T.WARNING if max_dd < -5 else T.SUCCESS)

    summary_row = html.Div([
        _card("Total P&L",
              f"{'+'if total>=0 else ''}${total:,.2f}",
              T.SUCCESS if total >= 0 else T.DANGER),
        _card("Win Rate",
              f"{win_rate:.0f}%  ({wins}W/{losses}L)"),
        _card("Avg Win",    f"+${avg_win:,.2f}",  T.SUCCESS),
        _card("Avg Loss",   f"${avg_loss:,.2f}",  T.DANGER),
        _card("Profit Factor", pf_str,
              T.SUCCESS if profit_factor >= 1.5 else (T.WARNING if profit_factor >= 1.0 else T.DANGER)),
        _card("Sharpe Ratio",  f"{sharpe:.2f}", sr_color),
        _card("Max Drawdown",  dd_str,          dd_color),
    ], style={
        "display": "flex", "flexWrap": "wrap", "gap": "10px",
        "marginBottom": "16px",
    })

    # ── Monthly returns heatmap ───────────────────────────────────────────────
    df_trades = pd.DataFrame({"close_date": pd.to_datetime(dates), "pnl": pnls})
    df_trades["year"]  = df_trades["close_date"].dt.year
    df_trades["month"] = df_trades["close_date"].dt.month

    monthly = df_trades.groupby(["year", "month"])["pnl"].sum().reset_index()
    years   = sorted(monthly["year"].unique())
    months  = list(range(1, 13))
    month_labels = ["Jan","Feb","Mar","Apr","May","Jun",
                    "Jul","Aug","Sep","Oct","Nov","Dec"]

    # Build z matrix: rows = years (top→bottom), cols = months
    z = []
    for yr in years:
        row_vals = []
        for mo in months:
            mask = (monthly["year"] == yr) & (monthly["month"] == mo)
            val  = float(monthly.loc[mask, "pnl"].sum()) if mask.any() else None
            row_vals.append(val)
        z.append(row_vals)

    # Build hover text matrix
    hover_text = []
    for yi, yr in enumerate(years):
        row_txt = []
        for mi, mo in enumerate(months):
            v = z[yi][mi]
            if v is None:
                row_txt.append(f"{month_labels[mi]} {yr}<br>No trades")
            else:
                sign = "+" if v >= 0 else ""
                row_txt.append(f"{month_labels[mi]} {yr}<br>{sign}${v:,.2f}")
        hover_text.append(row_txt)

    # Replace None with NaN for plotly
    z_plot = [[v if v is not None else float("nan") for v in row] for row in z]

    fig_hm = go.Figure(go.Heatmap(
        z=z_plot,
        x=month_labels,
        y=[str(yr) for yr in years],
        text=hover_text,
        hovertemplate="%{text}<extra></extra>",
        colorscale=[
            [0.0,  "#ef4444"],   # deep red  (large loss)
            [0.45, "#7f1d1d"],   # dark red
            [0.5,  "#1f2937"],   # neutral (near-zero)
            [0.55, "#064e3b"],   # dark green
            [1.0,  "#10b981"],   # deep green (large gain)
        ],
        zmid=0,
        showscale=True,
        colorbar=dict(
            thickness=10, len=0.8,
            tickformat="$,.0f",
            tickfont=dict(color=T.TEXT_SEC, size=10),
            bgcolor=T.BG_CARD,
            bordercolor=T.BORDER,
        ),
        xgap=3, ygap=3,
    ))

    # Annotate each cell with the P&L value
    annotations = []
    for yi, yr in enumerate(years):
        for mi in range(12):
            v = z[yi][mi]
            if v is not None:
                sign = "+" if v >= 0 else ""
                annotations.append(dict(
                    x=month_labels[mi], y=str(yr),
                    text=f"{sign}${v:,.0f}",
                    showarrow=False,
                    font=dict(size=9, color=T.TEXT_PRIMARY),
                    xref="x", yref="y",
                ))

    fig_hm.update_layout(
        template="plotly_dark",
        paper_bgcolor=T.BG_CARD,
        plot_bgcolor=T.BG_CARD,
        font=dict(color=T.TEXT_SEC, size=11),
        title=dict(text="Monthly Returns ($)", font=dict(size=12, color=T.TEXT_SEC)),
        height=max(120, 60 + len(years) * 52),
        margin=dict(l=0, r=0, t=40, b=10),
        xaxis=dict(side="top", gridcolor=T.BORDER),
        yaxis=dict(gridcolor=T.BORDER, autorange="reversed"),
        annotations=annotations,
    )

    # ── Per-trade P&L bar chart ───────────────────────────────────────────────
    colors = [T.SUCCESS if p >= 0 else T.DANGER for p in pnls]

    fig_bar = go.Figure()
    fig_bar.add_trace(go.Bar(
        x=dates, y=pnls,
        marker_color=colors,
        name="Trade P&L",
        hovertemplate="%{x}<br>P&L: $%{y:+,.2f}<extra></extra>",
    ))
    fig_bar.add_trace(go.Scatter(
        x=dates, y=cum_pnl,
        mode="lines+markers",
        line=dict(color=T.ACCENT, width=2),
        marker=dict(size=5),
        name="Cumulative",
        yaxis="y2",
        hovertemplate="%{x}<br>Cumulative: $%{y:+,.2f}<extra></extra>",
    ))
    fig_bar.add_hline(y=0, line=dict(color=T.BORDER_BRT, width=1))
    fig_bar.update_layout(
        template="plotly_dark",
        paper_bgcolor=T.BG_CARD,
        plot_bgcolor=T.BG_CARD,
        font=dict(color=T.TEXT_SEC, size=11),
        title=dict(text="Per-Trade P&L", font=dict(size=12, color=T.TEXT_SEC)),
        height=320,
        margin=dict(l=0, r=0, t=40, b=0),
        legend=dict(orientation="h", y=-0.18, bgcolor="rgba(0,0,0,0)"),
        yaxis=dict(title="Trade P&L ($)", tickformat="$,.0f",
                   gridcolor=T.BORDER, zeroline=False),
        yaxis2=dict(title="Cumulative ($)", tickformat="$,.0f",
                    overlaying="y", side="right", gridcolor="rgba(0,0,0,0)",
                    zeroline=False),
        xaxis=dict(gridcolor=T.BORDER),
        barmode="relative",
    )

    # ── P&L by Strategy ──────────────────────────────────────────────────────
    from collections import defaultdict
    strat_pnl: dict = defaultdict(list)
    for r in rows:
        strat_pnl[r.get("Strategy", "Unknown")].append(r.get("P&L $", 0) or 0)

    strat_names  = sorted(strat_pnl.keys())
    strat_totals = [sum(strat_pnl[s]) for s in strat_names]
    strat_wins   = [sum(1 for p in strat_pnl[s] if p > 0) for s in strat_names]
    strat_counts = [len(strat_pnl[s]) for s in strat_names]
    strat_avgs   = [sum(strat_pnl[s]) / len(strat_pnl[s]) if strat_pnl[s] else 0
                    for s in strat_names]

    fig_s = go.Figure(go.Bar(
        x=strat_names, y=strat_totals,
        marker_color=[T.SUCCESS if p >= 0 else T.DANGER for p in strat_totals],
        text=[f"{'+'if p>=0 else ''}${p:,.0f}" for p in strat_totals],
        textposition="outside",
        hovertemplate="%{x}<br>Total: $%{y:+,.2f}<extra></extra>",
    ))
    fig_s.add_hline(y=0, line=dict(color=T.BORDER_BRT, width=1))
    fig_s.update_layout(
        template="plotly_dark", paper_bgcolor=T.BG_CARD, plot_bgcolor=T.BG_CARD,
        font=dict(color=T.TEXT_SEC, size=11),
        title=dict(text="P&L by Strategy", font=dict(size=12, color=T.TEXT_SEC)),
        height=300, margin=dict(l=0, r=0, t=40, b=60),
        xaxis=dict(gridcolor=T.BORDER, tickangle=-20),
        yaxis=dict(gridcolor=T.BORDER, tickformat="$,.0f", zeroline=False),
        showlegend=False,
    )

    # Summary table
    summary_rows = [
        {
            "Strategy":  s,
            "# Trades":  strat_counts[i],
            "Win Rate":  f"{strat_wins[i]/strat_counts[i]*100:.0f}%" if strat_counts[i] else "—",
            "Avg P&L":   f"{'+'if strat_avgs[i]>=0 else ''}${strat_avgs[i]:,.2f}",
            "Total P&L": f"{'+'if strat_totals[i]>=0 else ''}${strat_totals[i]:,.2f}",
        }
        for i, s in enumerate(strat_names)
    ]
    summary_grid = dag.AgGrid(
        columnDefs=[
            {"field": "Strategy",  "flex": 1},
            {"field": "# Trades",  "width": 90,  "type": "numericColumn"},
            {"field": "Win Rate",  "width": 90},
            {"field": "Avg P&L",   "width": 110},
            {"field": "Total P&L", "width": 120},
        ],
        rowData=summary_rows,
        defaultColDef={"resizable": True, "sortable": True},
        dashGridOptions={"domLayout": "autoHeight"},
        className=T.AGGRID_THEME,
        style={"width": "100%"},
    )

    _section_label = lambda txt: html.Div(txt, style={
        "color": T.TEXT_SEC, "fontSize": "11px", "fontWeight": "600",
        "textTransform": "uppercase", "letterSpacing": "0.07em", "marginBottom": "10px",
    })

    return html.Div([
        # 1. Summary metrics cards
        summary_row,

        # 2. Monthly returns heatmap
        dbc.Card(dbc.CardBody([
            _section_label("Monthly Returns"),
            dcc.Graph(figure=fig_hm, config={"displayModeBar": False}),
        ]), style={**T.STYLE_CARD, "marginBottom": "12px"}),

        # 3. Per-trade P&L bars + cumulative
        dbc.Card(dbc.CardBody([
            _section_label("Per-Trade P&L"),
            dcc.Graph(figure=fig_bar, config={"displayModeBar": False}),
        ]), style={**T.STYLE_CARD, "marginBottom": "12px"}),

        # 4. P&L by strategy
        dbc.Card(dbc.CardBody([
            _section_label("P&L by Strategy"),
            dcc.Graph(figure=fig_s, config={"displayModeBar": False}),
            html.Div(style={"height": "12px"}),
            summary_grid,
        ]), style={**T.STYLE_CARD}),
    ])


# ── Cash Record callback ──────────────────────────────────────────────────────

@callback(
    Output("pt-cash-status",  "children"),
    Output("pt-refresh",      "n_intervals", allow_duplicate=True),
    Input("pt-cash-save",     "n_clicks"),
    State("pt-cash-dir",      "value"),
    State("pt-cash-amount",   "value"),
    State("pt-cash-notes",    "value"),
    State("pt-refresh",       "n_intervals"),
    prevent_initial_call=True,
)
def record_cash(n_clicks, direction, amount, notes, current_n):
    if not n_clicks or not amount or float(amount) <= 0:
        return html.P("Enter a positive amount.", style={"color": T.WARNING, "fontSize": "12px"}), no_update

    try:
        from sqlalchemy import text as _text
        import uuid
        engine = _get_engine()
        biz_date = datetime.date.today().isoformat()
        tgid     = str(uuid.uuid4())
        sign     = 1.0 if direction == "DEPOSIT" else -1.0
        amt      = float(amount) * sign
        note_txt = notes or direction

        with engine.begin() as conn:
            # Insert into Balance
            conn.execute(_text("""
                INSERT INTO portfolio.Balance (AccountId, BalanceType, Amount, BusinessDate)
                VALUES (:aid, 'Cash', (
                    ISNULL((SELECT TOP 1 Amount FROM portfolio.Balance
                            WHERE AccountId = :aid AND BalanceType='Cash'
                            ORDER BY BusinessDate DESC), 100000) + :delta
                ), :bdate)
            """), {"aid": _ACCOUNT_ID, "delta": amt, "bdate": biz_date})

        return (
            html.P(f"Recorded {direction} ${abs(float(amount)):,.2f}", style={"color": T.SUCCESS, "fontSize": "12px"}),
            (current_n or 0) + 1,
        )
    except Exception as e:
        return html.P(f"Error: {e}", style={"color": T.DANGER, "fontSize": "12px"}), no_update


# ── Transaction filter callback ───────────────────────────────────────────────

@callback(
    Output("pt-txns-grid",  "rowData",   allow_duplicate=True),
    Output("pt-txn-count",  "children"),
    Input("pt-txn-search",       "value"),
    Input("pt-txn-filter-type",  "value"),
    Input("pt-txn-filter-dir",   "value"),
    Input("pt-txn-filter-strat", "value"),
    State("pt-txns-grid",        "rowData"),
    prevent_initial_call=True,
)
def filter_transactions(search, ftype, fdir, fstrat, all_rows):
    if not all_rows:
        return no_update, ""
    rows = all_rows
    if ftype:
        rows = [r for r in rows if r.get("Type") == ftype]
    if fdir:
        rows = [r for r in rows if r.get("Direction") == fdir]
    if fstrat:
        rows = [r for r in rows if r.get("Strategy") == fstrat]
    if search and search.strip():
        q = search.strip().lower()
        rows = [r for r in rows if
                q in str(r.get("Symbol", "")).lower() or
                q in str(r.get("Strategy", "")).lower() or
                q in str(r.get("Notes", "")).lower() or
                q in str(r.get("Underlying", "")).lower()]
    net_cf = sum(
        float(str(r.get("Cash Flow", "0")).replace("$", "").replace(",", "").replace("+", "") or 0)
        for r in rows
        if r.get("Cash Flow") not in (None, "—", "")
    )
    count_str = (f"{len(rows)} of {len(all_rows)} transaction(s)"
                 + (f" | Net Cash Flow: {'+'if net_cf>=0 else ''}${net_cf:,.2f}" if rows else ""))
    return rows, count_str


# ── Delete: open confirmation modal ──────────────────────────────────────────

@callback(
    Output("pt-delete-modal",        "is_open",  allow_duplicate=True),
    Output("pt-delete-confirm-body", "children"),
    Output("pt-delete-action",       "data"),
    Input("pt-del-date-btn",   "n_clicks"),
    Input("pt-del-today-btn",  "n_clicks"),
    Input("pt-del-all-btn",    "n_clicks"),
    State("pt-del-date-picker", "value"),
    prevent_initial_call=True,
)
def open_delete_modal(n_date, n_today, n_all, sel_date):
    triggered = ctx.triggered_id
    if triggered == "pt-del-date-btn":
        if not sel_date:
            return no_update, no_update, no_update
        action = f"date:{sel_date}"
        msg    = f"Delete all transactions on {sel_date}? This cannot be undone."
    elif triggered == "pt-del-today-btn":
        action = "today"
        today  = datetime.date.today().isoformat()
        msg    = f"Delete all transactions from today ({today})? This cannot be undone."
    elif triggered == "pt-del-all-btn":
        action = "all"
        msg    = "Delete ALL transactions? This cannot be undone."
    else:
        return no_update, no_update, no_update

    body = dbc.Alert(msg, color="danger", style={"fontSize": "13px"})
    return True, body, action


@callback(
    Output("pt-delete-modal",      "is_open",      allow_duplicate=True),
    Output("pt-refresh",           "n_intervals",  allow_duplicate=True),
    Output("pt-delete-status-msg", "children"),
    Input("pt-delete-confirm-btn", "n_clicks"),
    Input("pt-delete-cancel-btn",  "n_clicks"),
    State("pt-delete-action",      "data"),
    State("pt-refresh",            "n_intervals"),
    prevent_initial_call=True,
)
def execute_delete(n_confirm, n_cancel, action, current_n):
    triggered = ctx.triggered_id
    if triggered == "pt-delete-cancel-btn" or not action:
        return False, no_update, no_update
    if not n_confirm:
        return no_update, no_update, no_update

    try:
        from sqlalchemy import text as _text
        engine = _get_engine()
        with engine.begin() as conn:
            if action.startswith("date:"):
                d = action[5:]
                conn.execute(_text(
                    "DELETE FROM portfolio.[Transaction] WHERE AccountId=:aid AND CAST(BusinessDate AS DATE)=:d"
                ), {"aid": _ACCOUNT_ID, "d": d})
                msg = f"Deleted all transactions on {d}."
            elif action == "today":
                d = datetime.date.today().isoformat()
                conn.execute(_text(
                    "DELETE FROM portfolio.[Transaction] WHERE AccountId=:aid AND CAST(BusinessDate AS DATE)=:d"
                ), {"aid": _ACCOUNT_ID, "d": d})
                msg = f"Deleted today's transactions ({d})."
            elif action == "all":
                conn.execute(_text(
                    "DELETE FROM portfolio.[Transaction] WHERE AccountId=:aid"
                ), {"aid": _ACCOUNT_ID})
                msg = "Deleted all transactions."
            else:
                return False, no_update, no_update

        status = html.P(msg, style={"color": T.SUCCESS, "fontSize": "12px"})
        return False, (current_n or 0) + 1, status
    except Exception as e:
        status = html.P(f"Delete error: {e}", style={"color": T.DANGER, "fontSize": "12px"})
        return False, no_update, status


# ── Close trade: show confirmation modal ─────────────────────────────────────

@callback(
    Output("pt-close-confirm-modal", "is_open",       allow_duplicate=True),
    Output("pt-close-confirm-body",  "children"),
    Input("pt-close-btn",            "n_clicks"),
    State("pt-selected-tgid",        "data"),
    prevent_initial_call=True,
)
def open_close_confirm(n_clicks, tgid):
    if not n_clicks or not tgid:
        return no_update, no_update
    _, _, txns_df = _load_data()
    if txns_df.empty:
        return no_update, no_update
    grp = txns_df[txns_df["TradeGroupId"] == tgid].copy()
    if grp.empty:
        return no_update, no_update

    rows = []
    for _, r in grp.iterrows():
        stype = str(r.get("SecurityType", "")).lower()
        if stype == "cash":
            continue
        px = r.get("TransactionPrice")
        rows.append({
            "Leg":        str(r.get("LegType") or r.get("Symbol", "")),
            "Symbol":     str(r.get("Symbol", "")),
            "Dir":        str(r.get("Direction", "")),
            "Qty":        float(r.get("Quantity") or 0),
            "Entry":      f"${float(px):,.4f}" if px is not None else "—",
            "Close (est)": f"${float(px):,.4f}" if px is not None else "—",
        })

    table = dag.AgGrid(
        columnDefs=[
            {"field": "Leg",         "flex": 1},
            {"field": "Symbol",      "flex": 1},
            {"field": "Dir",         "width": 70},
            {"field": "Qty",         "width": 70, "type": "numericColumn"},
            {"field": "Entry",       "width": 110},
            {"field": "Close (est)", "width": 110},
        ],
        rowData=rows,
        defaultColDef={"resizable": True},
        dashGridOptions={"domLayout": "autoHeight"},
        className=T.AGGRID_THEME,
        style={"width": "100%"},
    )
    return True, table


@callback(
    Output("pt-close-confirm-modal", "is_open",      allow_duplicate=True),
    Output("pt-modal",               "is_open",      allow_duplicate=True),
    Output("pt-refresh",             "n_intervals",  allow_duplicate=True),
    Input("pt-close-confirm-btn",    "n_clicks"),
    Input("pt-close-cancel-btn",     "n_clicks"),
    State("pt-selected-tgid",        "data"),
    State("pt-refresh",              "n_intervals"),
    prevent_initial_call=True,
)
def execute_close(n_confirm, n_cancel, tgid, current_n):
    triggered = ctx.triggered_id
    if triggered == "pt-close-cancel-btn":
        return False, no_update, no_update
    if not n_confirm or not tgid:
        return no_update, no_update, no_update

    from engine.positions import insert_closing_transactions
    _, _, txns_df = _load_data()
    if not txns_df.empty:
        grp = txns_df[txns_df["TradeGroupId"] == tgid].copy()
        if not grp.empty:
            engine = _get_engine()
            insert_closing_transactions(
                engine=engine, account_id=_ACCOUNT_ID,
                open_grp=grp, live_opt={}, fallback_price=0.0,
            )
    return False, False, (current_n or 0) + 1


# ── Risk tab: Black-Scholes engine ────────────────────────────────────────────

def _bs_full(S: float, K: float, T: float, r: float, sigma: float, otype: str):
    """
    Returns (price, delta, gamma, vega_per1pct, theta_per_day, vanna_per1pct).
    All Greeks are per-share (multiply by qty × mult for dollar Greeks).
    vega / vanna are per 1 percentage-point move in IV.
    """
    from scipy.stats import norm
    if T <= 1e-6:
        intrinsic = max(S - K, 0.0) if otype == "call" else max(K - S, 0.0)
        delta = (1.0 if S > K else 0.0) if otype == "call" else (-1.0 if S < K else 0.0)
        return intrinsic, delta, 0.0, 0.0, 0.0, 0.0
    if sigma <= 1e-6 or S <= 0 or K <= 0:
        intrinsic = max(S - K, 0.0) if otype == "call" else max(K - S, 0.0)
        return intrinsic, 0.0, 0.0, 0.0, 0.0, 0.0
    sqT  = np.sqrt(T)
    d1   = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqT)
    d2   = d1 - sigma * sqT
    φd1  = norm.pdf(d1)
    disc = np.exp(-r * T)
    if otype == "call":
        price = S * norm.cdf(d1) - K * disc * norm.cdf(d2)
        delta = norm.cdf(d1)
        theta = (-S * φd1 * sigma / (2 * sqT) - r * K * disc * norm.cdf(d2)) / 365
    else:
        price = K * disc * norm.cdf(-d2) - S * norm.cdf(-d1)
        delta = norm.cdf(d1) - 1.0
        theta = (-S * φd1 * sigma / (2 * sqT) + r * K * disc * norm.cdf(-d2)) / 365
    gamma = φd1 / (S * sigma * sqT)
    vega  = S * φd1 * sqT / 100.0          # per 1 pp IV change
    vanna = φd1 * d2 / sigma / 100.0       # per 1 pp IV change
    return price, delta, gamma, vega, theta, vanna


def _compute_risk_matrix(
    txns_df: "pd.DataFrame",
    step_pct:    int   = 2,
    vol_up_pct:  float = 25.0,
    vol_down_pct: float = 25.0,
    default_iv_pct: float = 20.0,
    rate_pct:    float = 4.3,
) -> dict | None:
    """
    Compute the risk matrix for all open option positions.
    Returns a dict with keys: shocks, pnl_none, pnl_vol_up, pnl_vol_down,
    underlying_px, delta, gamma, vega, vanna, theta, spots (per underlying).
    """
    import json

    opt = txns_df[
        txns_df["SecurityType"].str.lower().eq("option") &
        txns_df["Strike"].notna() &
        (pd.to_numeric(txns_df["Strike"], errors="coerce") > 0)
    ].copy() if "SecurityType" in txns_df.columns else pd.DataFrame()

    eq = txns_df[
        txns_df["SecurityType"].str.lower().ne("option") &
        txns_df["SecurityType"].str.lower().ne("cash")
    ].copy() if "SecurityType" in txns_df.columns else pd.DataFrame()

    if opt.empty and eq.empty:
        return None

    # Numeric coercions
    for col in ["Strike", "Quantity", "TransactionPrice", "Multiplier"]:
        if col in opt.columns:
            opt[col] = pd.to_numeric(opt[col], errors="coerce")
    opt["Multiplier"] = opt["Multiplier"].fillna(100)
    opt["Quantity"]   = opt["Quantity"].fillna(1)

    # Always 11 columns centered on 0; range scales with step size
    shocks = [s * step_pct / 100.0 for s in range(-5, 6)]

    r   = rate_pct / 100.0
    today = datetime.date.today()

    # Get unique underlyings and fetch spot prices
    underlyings = list(txns_df["Underlying"].dropna().unique()) if "Underlying" in txns_df.columns else []
    spots: dict[str, float] = {}
    try:
        from dash_app import get_polygon_api_key
        from engine.positions import fetch_stock_price
        api_key = get_polygon_api_key()
        if api_key:
            for und in underlyings:
                px = fetch_stock_price(api_key, und)
                if px:
                    spots[und] = px
    except Exception:
        pass

    # Aggregate across all underlyings + legs
    pnl_none    = [0.0] * len(shocks)
    pnl_vol_up  = [0.0] * len(shocks)
    pnl_vol_dn  = [0.0] * len(shocks)
    agg_delta   = [0.0] * len(shocks)
    agg_gamma   = [0.0] * len(shocks)
    agg_vega    = [0.0] * len(shocks)
    agg_vanna   = [0.0] * len(shocks)
    agg_theta   = [0.0] * len(shocks)
    ref_spots   = {}   # underlying → spot (for display)

    for _, row in opt.iterrows():
        und  = str(row.get("Underlying") or "")
        S    = spots.get(und)
        if not S or S <= 0:
            continue

        K    = float(row["Strike"])
        qty  = float(row["Quantity"])
        mult = float(row["Multiplier"])
        sign = 1.0 if str(row.get("Direction", "")).upper() == "BUY" else -1.0
        pos  = sign * qty * mult       # +ve = long, -ve = short
        entry_px = float(row.get("TransactionPrice") or 0)
        otype = str(row.get("OptionType") or "put").lower()

        # T in years
        exp_str = str(row.get("Expiration") or "")
        try:
            exp_date = datetime.date.fromisoformat(exp_str[:10])
            T_years  = max((exp_date - today).days / 365.0, 1 / 365)
        except Exception:
            T_years = 21 / 365.0

        # IV: try Notes JSON, else default
        sigma = default_iv_pct / 100.0
        try:
            notes = json.loads(str(row.get("Notes") or "{}") or "{}")
            iv_raw = notes.get("ATM IV") or notes.get("atm_iv")
            if iv_raw is not None:
                iv_f = float(str(iv_raw).strip("%")) / 100.0 if "%" in str(iv_raw) else float(iv_raw)
                if 0.01 < iv_f < 5.0:
                    sigma = iv_f
        except Exception:
            pass

        sigma_up = sigma * (1 + vol_up_pct / 100.0)
        sigma_dn = max(sigma * (1 - vol_down_pct / 100.0), 0.01)

        ref_spots.setdefault(und, S)

        # Baseline = BS price at current spot + current vol (no shock).
        # All P&L cells show INCREMENTAL change from current mark, so 0%/None = $0.
        price_base, _, _, _, _, _ = _bs_full(S, K, T_years, r, sigma, otype)

        for i, shock in enumerate(shocks):
            S_shock = S * (1 + shock)
            price_none, d, g, v, th, va = _bs_full(S_shock, K, T_years, r, sigma, otype)
            price_up,   _, _, _, _,  _  = _bs_full(S_shock, K, T_years, r, sigma_up, otype)
            price_dn,   _, _, _, _,  _  = _bs_full(S_shock, K, T_years, r, sigma_dn, otype)

            pnl_none[i]   += (price_none - price_base) * pos
            pnl_vol_up[i] += (price_up   - price_base) * pos
            pnl_vol_dn[i] += (price_dn   - price_base) * pos
            # Dollarized Greeks:
            # $ Delta  = delta × S × pos          ($ equiv stock exposure)
            # $ Gamma  = 0.5 × gamma × (S×0.01)² × pos  ($ P&L per additional 1% move)
            # $ Vega   = vega × pos               (already $/pp from _bs_full dividing by 100)
            # $ Vanna  = vanna × S × pos          ($ vega change per 1% spot move)
            # $ Theta  = theta × pos              (already $/day from _bs_full dividing by 365)
            agg_delta[i]  += d  * pos * S_shock
            agg_gamma[i]  += 0.5 * g * pos * (S_shock * 0.01) ** 2
            agg_vega[i]   += v  * pos
            agg_vanna[i]  += va * pos * S_shock
            agg_theta[i]  += th * pos

    # Equity legs: delta = qty × mult × sign per shock
    for _, row in eq.iterrows():
        und  = str(row.get("Underlying") or row.get("Symbol") or "")
        S    = spots.get(und)
        if not S or S <= 0:
            continue
        qty  = float(row.get("Quantity") or 0)
        mult = float(row.get("Multiplier") or 1)
        sign = 1.0 if str(row.get("Direction", "")).upper() == "BUY" else -1.0
        entry_px = float(row.get("TransactionPrice") or 0)
        pos  = sign * qty * mult
        ref_spots.setdefault(und, S)
        for i, shock in enumerate(shocks):
            S_shock = S * (1 + shock)
            gain    = (S_shock - S) * pos   # baseline = current spot, so 0%=0
            pnl_none[i]   += gain
            pnl_vol_up[i] += gain
            pnl_vol_dn[i] += gain
            agg_delta[i]  += pos * S_shock    # $ delta: shares × price

    # Primary underlying for display (pick most common)
    primary_und = max(ref_spots, key=lambda u: 1) if ref_spots else None
    S0 = ref_spots.get(primary_und, 0) if primary_und else 0

    pnl_stress = [min(pnl_none[i], pnl_vol_up[i], pnl_vol_dn[i]) for i in range(len(shocks))]

    return {
        "shocks":       shocks,
        "pnl_stress":   pnl_stress,
        "pnl_vol_up":   pnl_vol_up,
        "pnl_none":     pnl_none,
        "pnl_vol_dn":   pnl_vol_dn,
        "delta":        agg_delta,
        "gamma":        agg_gamma,
        "vega":         agg_vega,
        "vanna":        agg_vanna,
        "theta":        agg_theta,
        "spot0":        S0,
        "ref_spots":    ref_spots,
        "primary_und":  primary_und or "",
        "multi_und":    len(ref_spots) > 1,
    }


def _render_risk_table(mx: dict) -> html.Div:
    shocks = mx["shocks"]
    spot0  = mx["spot0"]

    _TH = {
        "padding": "6px 10px", "textAlign": "center", "fontSize": "11px",
        "fontWeight": "700", "color": T.TEXT_SEC, "whiteSpace": "nowrap",
        "borderBottom": f"1px solid {T.BORDER_BRT}",
        "backgroundColor": T.BG_ELEVATED,
    }
    _ROW_LABEL = {
        "padding": "5px 12px", "fontSize": "12px", "fontWeight": "600",
        "whiteSpace": "nowrap", "color": T.TEXT_SEC,
        "borderRight": f"1px solid {T.BORDER}",
    }
    _SEP_ROW = {
        "padding": "2px 12px", "fontSize": "10px", "fontWeight": "700",
        "letterSpacing": "0.08em", "textTransform": "uppercase",
        "color": T.TEXT_MUTED, "backgroundColor": T.BG_ELEVATED,
        "borderTop": f"2px solid {T.BORDER_BRT}",
    }

    def _pnl_cell(val: float) -> html.Td:
        if val is None:
            return html.Td("—", style={"textAlign": "center", "color": T.TEXT_MUTED, "padding": "5px 6px"})
        color = T.SUCCESS if val > 0 else T.DANGER if val < 0 else T.TEXT_MUTED
        intensity = min(abs(val) / max(abs(v) for row in [mx["pnl_none"], mx["pnl_vol_up"], mx["pnl_vol_dn"]]
                                       for v in row if v != 0) if any(
            v != 0 for row in [mx["pnl_none"], mx["pnl_vol_up"], mx["pnl_vol_dn"]] for v in row) else 1, 1.0)
        bg = (f"rgba(16,185,129,{intensity*0.35})" if val > 0
              else f"rgba(239,68,68,{intensity*0.35})" if val < 0 else "transparent")
        r = round(val)
        sign = "+" if r > 0 else "-" if r < 0 else ""
        return html.Td(
            f"{sign}${abs(r):,}",
            style={"textAlign": "right", "color": color, "backgroundColor": bg,
                   "padding": "5px 8px", "fontSize": "12px", "fontFamily": "monospace"},
        )

    def _greek_cell(val: float) -> html.Td:
        if val is None:
            return html.Td("—", style={"textAlign": "center", "color": T.TEXT_MUTED, "padding": "5px 6px"})
        color = T.SUCCESS if val > 0 else T.DANGER if val < 0 else T.TEXT_MUTED
        sign = "+" if val > 0 else "-" if val < 0 else ""
        return html.Td(
            f"{sign}${abs(val):,.2f}",
            style={"textAlign": "right", "color": color, "backgroundColor": "transparent",
                   "padding": "5px 8px", "fontSize": "12px", "fontFamily": "monospace"},
        )

    def _spot_cell(shock: float) -> html.Td:
        if spot0 <= 0:
            return html.Td("—", style={"textAlign": "right", "color": T.TEXT_MUTED,
                                        "padding": "5px 8px", "fontSize": "12px"})
        px = spot0 * (1 + shock)
        color = T.SUCCESS if shock > 0 else T.DANGER if shock < 0 else "#e5e7eb"
        return html.Td(f"${px:,.2f}", style={"textAlign": "right", "color": color,
                                              "padding": "5px 8px", "fontSize": "12px",
                                              "fontFamily": "monospace"})

    # Normalise P&L intensities across all scenario rows (including stress)
    all_pnl_vals = mx["pnl_none"] + mx["pnl_vol_up"] + mx["pnl_vol_dn"] + mx["pnl_stress"]
    max_abs_pnl  = max((abs(v) for v in all_pnl_vals if v), default=1.0)

    def _pnl_cell2(val: float) -> html.Td:
        intensity = min(abs(val) / max_abs_pnl, 1.0)
        if val > 0:
            bg    = f"rgba(59,130,246,{intensity*0.25})"
            color = "#93c5fd"
        elif val < 0:
            bg    = f"rgba(239,68,68,{intensity*0.25})"
            color = "#fca5a5"
        else:
            bg    = "transparent"
            color = T.TEXT_MUTED
        sign = "+" if val > 0 else "-" if val < 0 else ""
        return html.Td(
            f"{sign}${abs(val):,.2f}",
            style={"textAlign": "right", "color": color, "backgroundColor": bg,
                   "padding": "5px 8px", "fontSize": "12px", "fontFamily": "monospace"},
        )

    header = html.Tr(
        [html.Th("", style=_TH)] +
        [html.Th(f"{'+'if s>0 else ''}{s:.0%}", style={
            **_TH,
            "color": T.SUCCESS if s > 0 else T.DANGER if s < 0 else "#e5e7eb",
        }) for s in shocks]
    )

    def _row(label, cells, sep=False):
        lbl_style = _SEP_ROW if sep else _ROW_LABEL
        return html.Tr([html.Td(label, style=lbl_style)] + cells)

    multi_und = mx.get("multi_und", False)
    tbody_rows = [
        _row("Vol Up",     [_pnl_cell2(v) for v in mx["pnl_vol_up"]]),
        _row("None",       [_pnl_cell2(v) for v in mx["pnl_none"]]),
        _row("Vol Down",   [_pnl_cell2(v) for v in mx["pnl_vol_dn"]]),
        _row("Greeks",     [html.Td("", style={"padding": "2px"}) for _ in shocks], sep=True),
        # Underlying only shown for single-underlying view
        *([_row("Underlying", [_spot_cell(s) for s in shocks])] if not multi_und else []),
        _row("$ Delta",  [_greek_cell(v) for v in mx["delta"]]),
        _row("$ Gamma",  [_greek_cell(v) for v in mx["gamma"]]),
        _row("$ Vega",   [_greek_cell(v) for v in mx["vega"]]),
        _row("$ Vanna",  [_greek_cell(v) for v in mx["vanna"]]),
        _row("$ Theta",  [_greek_cell(v) for v in mx["theta"]]),
    ]

    label = mx.get("primary_und", "")
    if mx.get("ref_spots"):
        parts = [f"{u} @ ${s:,.2f}" for u, s in mx["ref_spots"].items()]
        label = "  ·  ".join(parts[:4])

    table = html.Table(
        [html.Thead(header), html.Tbody(tbody_rows)],
        style={
            "width": "100%", "borderCollapse": "collapse",
            "backgroundColor": T.BG_CARD,
        },
    )
    # Single stress number: worst P&L across entire matrix
    stress_val = min(mx["pnl_stress"])
    stress_str = f"-${abs(stress_val):,.2f}" if stress_val < 0 else f"+${stress_val:,.2f}"
    stress_card = html.Div([
        html.Div("STRESS (worst case)", style={
            "fontSize": "10px", "fontWeight": "700", "letterSpacing": "0.08em",
            "color": T.WARNING, "marginBottom": "4px",
        }),
        html.Div(stress_str, style={
            "fontSize": "22px", "fontWeight": "700",
            "color": T.DANGER if stress_val < 0 else T.SUCCESS,
            "fontFamily": "monospace",
        }),
        html.Div("max loss across all price × vol scenarios", style={
            "fontSize": "10px", "color": T.TEXT_MUTED, "marginTop": "2px",
        }),
    ], style={
        "display": "inline-block", "padding": "10px 18px",
        "border": f"1px solid {T.WARNING}",
        "borderRadius": "8px", "marginBottom": "14px",
        "backgroundColor": "rgba(245,158,11,0.07)",
    })

    # ── Payoff chart ──────────────────────────────────────────────────────────
    x_labels = [f"{'+' if s > 0 else ''}{s:.0%}" for s in shocks]

    fig = go.Figure()

    all_vals  = mx["pnl_vol_up"] + mx["pnl_none"] + mx["pnl_vol_dn"]
    y_max = max(max(all_vals) * 1.15, 1)
    y_min = min(min(all_vals) * 1.15, -1)

    # Positive region shading (above zero)
    fig.add_hrect(y0=0, y1=y_max, fillcolor="rgba(16,185,129,0.04)", line_width=0, layer="below")
    # Negative region shading (below zero)
    fig.add_hrect(y0=y_min, y1=0, fillcolor="rgba(239,68,68,0.04)", line_width=0, layer="below")

    # Vol band fill
    fig.add_trace(go.Scatter(
        x=x_labels + x_labels[::-1],
        y=mx["pnl_vol_up"] + mx["pnl_vol_dn"][::-1],
        fill="toself",
        fillcolor="rgba(99,102,241,0.07)",
        line={"width": 0},
        hoverinfo="skip",
        showlegend=False,
    ))

    fig.add_trace(go.Scatter(
        x=x_labels, y=mx["pnl_vol_up"],
        name="Vol Up ↑", mode="lines",
        line={"color": "#ef4444", "width": 1.5, "dash": "dot"},
    ))
    fig.add_trace(go.Scatter(
        x=x_labels, y=mx["pnl_none"],
        name="Base (no vol Δ)", mode="lines",
        line={"color": "#6366f1", "width": 2.5},
    ))
    fig.add_trace(go.Scatter(
        x=x_labels, y=mx["pnl_vol_dn"],
        name="Vol Down ↓", mode="lines",
        line={"color": "#10b981", "width": 1.5, "dash": "dot"},
    ))

    # Zero line with +/- annotations
    fig.add_hline(y=0, line={"color": "#4b5563", "width": 1, "dash": "dash"},
                  annotation_text="  $0", annotation_position="left",
                  annotation_font={"color": "#6b7280", "size": 10})

    fig.update_layout(
        template="none",
        height=220,
        margin={"t": 10, "b": 30, "l": 70, "r": 20},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"color": "#9ca3af", "size": 11},
        legend={"orientation": "h", "x": 0.5, "xanchor": "center",
                "y": 1.18, "font": {"size": 11, "color": "#9ca3af"},
                "traceorder": "normal", "itemwidth": 100,
                "bgcolor": "rgba(0,0,0,0)"},
        xaxis={"gridcolor": "#1f2937", "color": "#9ca3af",
               "tickfont": {"size": 10, "color": "#9ca3af"}},
        yaxis={"gridcolor": "#1f2937", "tickprefix": "$", "tickformat": ",.0f",
               "zeroline": False, "range": [y_min, y_max],
               "color": "#9ca3af",
               "tickfont": {"size": 10, "color": "#9ca3af"}},
        hovermode="x unified",
    )

    payoff_chart = dcc.Graph(
        figure=fig,
        config={"displayModeBar": False},
        style={"marginTop": "20px"},
    )

    return html.Div([
        html.Div(label, style={"color": T.TEXT_MUTED, "fontSize": "11px",
                                "marginBottom": "8px", "fontStyle": "italic"}),
        stress_card,
        html.Div(table, style={"overflowX": "auto"}),
        html.Div(
            "Delta ($) = portfolio $ delta at each shock  ·  "
            "Gamma ($) = $ P&L per additional 1% move  ·  "
            "Vega/Vanna ($) = per 1 pp IV change  ·  "
            "Theta ($) = per-day decay",
            style={"color": T.TEXT_MUTED, "fontSize": "10px", "marginTop": "8px",
                   "fontStyle": "italic"},
        ),
        payoff_chart,
    ])


@callback(
    Output("pt-risk-pos-pills", "children"),
    Output("pt-risk-position",  "data"),
    Input("pt-tabs",            "active_tab"),
    Input("pt-refresh",         "n_intervals"),
    Input({"type": "pt-risk-pill", "tgid": ALL}, "n_clicks"),
    State("pt-risk-position",   "data"),
)
def populate_risk_pills(active_tab, _n, _pill_clicks, current_sel):
    from dash import callback_context as _ctx

    if active_tab != "risk":
        return no_update, no_update

    _, _, txns_df = _load_data()
    if txns_df.empty:
        return html.P("No open positions.", style={"color": T.TEXT_MUTED, "fontSize": "12px"}), "__all__"
    if "Notes" in txns_df.columns:
        txns_df = txns_df[~txns_df["Notes"].str.upper().str.contains("CLOSE", na=False)]

    open_groups = get_open_trade_groups_simple(txns_df)

    # Detect pill click
    new_sel = current_sel or "__all__"
    triggered = _ctx.triggered_id
    if isinstance(triggered, dict) and triggered.get("type") == "pt-risk-pill":
        new_sel = triggered["tgid"]

    def _pill(label, tgid):
        selected = tgid == new_sel
        return dbc.Button(
            label,
            id={"type": "pt-risk-pill", "tgid": tgid},
            n_clicks=0,
            size="sm",
            style={
                "display": "inline-block",
                "padding": "4px 12px", "borderRadius": "16px",
                "fontSize": "12px", "fontWeight": "600",
                "marginRight": "6px", "marginBottom": "6px",
                "border": f"1px solid {T.ACCENT}",
                "backgroundColor": T.ACCENT if selected else "transparent",
                "color": "#fff" if selected else T.ACCENT,
                "cursor": "pointer",
            },
        )

    def _pos_label(tgid: str, g: dict) -> str:
        base = f"{g['underlying']}  ·  {g['strategy'][:22]}"
        suffix = g["open_date"] if g.get("open_date") else f"#{tgid[-4:]}"
        return f"{base}  ({suffix})"

    pills = [_pill("Portfolio", "__all__")] + [
        _pill(_pos_label(tgid, g), tgid)
        for tgid, g in open_groups.items()
    ]
    return html.Div(pills, style={"flexWrap": "wrap"}), new_sel


def get_open_trade_groups_simple(txns_df: "pd.DataFrame") -> dict:
    """Return {tgid: {underlying, strategy, open_date, grp}} for open positions only."""
    from engine.positions import get_open_trade_groups
    groups = get_open_trade_groups(txns_df)
    result = {}
    for tgid, grp in groups.items():
        und = (grp["Underlying"].dropna().iloc[0]
               if "Underlying" in grp.columns and not grp["Underlying"].dropna().empty
               else grp["Symbol"].iloc[0] if not grp.empty else "?")
        strat = str(grp["StrategyName"].iloc[0]) if not grp.empty else "?"
        # Earliest transaction date for this group
        open_date = ""
        for date_col in ("BusinessDate", "Date", "CreatedAt"):
            if date_col in grp.columns and not grp[date_col].dropna().empty:
                try:
                    open_date = pd.to_datetime(grp[date_col].dropna().iloc[0]).strftime("%m/%d")
                except Exception:
                    open_date = str(grp[date_col].dropna().iloc[0])[:5]
                if open_date:
                    break
        result[tgid] = {"underlying": und, "strategy": strat, "open_date": open_date, "grp": grp}
    return result


@callback(
    Output("pt-risk-leg-pills", "children"),
    Output("pt-risk-leg",       "data"),
    Input("pt-risk-position",   "data"),
    Input({"type": "pt-risk-leg-pill", "sid": ALL}, "n_clicks"),
    State("pt-risk-leg",        "data"),
)
def populate_leg_pills(position_tgid, _leg_clicks, current_leg):
    from dash import callback_context as _ctx

    # Reset leg selection when position changes
    triggered = _ctx.triggered_id
    new_leg = current_leg or "__all__"
    if isinstance(triggered, dict) and triggered.get("type") == "pt-risk-leg-pill":
        new_leg = triggered["sid"]
    elif triggered == "pt-risk-position":
        new_leg = "__all__"

    if not position_tgid or position_tgid == "__all__":
        return html.Div(), "__all__"

    _, _, txns_df = _load_data()
    if txns_df.empty:
        return html.Div(), "__all__"
    if "Notes" in txns_df.columns:
        txns_df = txns_df[~txns_df["Notes"].str.upper().str.contains("CLOSE", na=False)]

    grp = txns_df[txns_df["TradeGroupId"] == position_tgid]
    opt = grp[grp["SecurityType"].str.lower().eq("option")] if "SecurityType" in grp.columns else pd.DataFrame()
    if opt.empty:
        return html.Div(), "__all__"

    def _lpill(label, sid):
        selected = sid == new_leg
        return dbc.Button(
            label,
            id={"type": "pt-risk-leg-pill", "sid": sid},
            n_clicks=0, size="sm",
            style={
                "padding": "3px 10px", "borderRadius": "12px",
                "fontSize": "11px", "fontWeight": "600",
                "marginRight": "5px", "marginBottom": "5px",
                "border": f"1px solid {T.BORDER_BRT}",
                "backgroundColor": T.BG_ELEVATED if selected else "transparent",
                "color": "#e5e7eb" if selected else T.TEXT_MUTED,
                "cursor": "pointer",
            },
        )

    pills = [_lpill("All legs", "__all__")]
    for _, r in opt.iterrows():
        sid = str(r.get("Symbol") or r.get("SecurityId") or "")
        k   = r.get("Strike", "")
        ot  = str(r.get("OptionType") or "").upper()
        dr  = str(r.get("Direction") or "").capitalize()
        label = f"{dr}  {ot}  ${float(k):.0f}" if k else sid
        pills.append(_lpill(label, sid))

    return html.Div([
        html.Span("  Legs: ", style={"color": T.TEXT_MUTED, "fontSize": "11px",
                                      "marginRight": "6px", "lineHeight": "28px"}),
        *pills,
    ], style={"display": "flex", "alignItems": "center", "flexWrap": "wrap",
              "paddingLeft": "8px", "borderLeft": f"2px solid {T.BORDER_BRT}"}), new_leg


@callback(
    Output("pt-risk-matrix",    "children"),
    Input("pt-risk-calc-btn",   "n_clicks"),
    State("pt-risk-step",       "value"),
    State("pt-risk-vol-up",     "value"),
    State("pt-risk-vol-down",   "value"),
    State("pt-risk-iv-default", "value"),
    State("pt-risk-rate",       "value"),
    State("pt-risk-position",   "data"),
    State("pt-risk-leg",        "data"),
    prevent_initial_call=True,
)
def compute_risk(n_clicks, step, vol_up, vol_dn, iv_default, rate, position_filter, leg_filter):
    if not n_clicks:
        return no_update
    _, _, txns_df = _load_data()
    if txns_df.empty:
        return html.P("No transactions found.", style={"color": T.TEXT_MUTED, "padding": "20px"})

    # Only open positions (no CLOSE notes)
    if "Notes" in txns_df.columns:
        txns_df = txns_df[~txns_df["Notes"].str.upper().str.contains("CLOSE", na=False)]

    # Filter to single position if requested
    if position_filter and position_filter != "__all__":
        txns_df = txns_df[txns_df["TradeGroupId"] == position_filter]
        if txns_df.empty:
            return html.P("Position not found.", style={"color": T.TEXT_MUTED, "padding": "20px"})

    # Filter to single leg if requested
    if leg_filter and leg_filter != "__all__" and "Symbol" in txns_df.columns:
        leg_mask = txns_df["Symbol"] == leg_filter
        if leg_mask.any():
            txns_df = txns_df[leg_mask]

    mx = _compute_risk_matrix(
        txns_df,
        step_pct=int(step or 2),
        vol_up_pct=float(vol_up or 25),
        vol_down_pct=float(vol_dn or 25),
        default_iv_pct=float(iv_default or 20),
        rate_pct=float(rate or 4.3),
    )
    if mx is None:
        return html.P(
            "No priceable option legs found. Legs may have Strike=0 (incomplete entry data).",
            style={"color": T.TEXT_MUTED, "padding": "20px", "fontSize": "12px"},
        )

    if position_filter == "__all__":
        scope = "Portfolio"
    elif leg_filter and leg_filter != "__all__":
        scope = f"{position_filter}  ›  {leg_filter}"
    else:
        scope = position_filter
    header = html.Div(
        scope,
        style={"color": T.TEXT_SEC, "fontSize": "13px", "fontWeight": "600", "marginBottom": "10px"},
    )
    return dbc.Card(dbc.CardBody([header, _render_risk_table(mx)]),
                    style={**T.STYLE_CARD})
