"""
dash_app/pages/paper_trading/builders.py — UI builders (no @callback).

Column definitions, plotly figure builders, the modal-body assemblers, metric
cards, the legs/risk tables and the equity/performance charts. Moved verbatim
from the original monolithic paper_trading.py.
"""
from __future__ import annotations

import datetime
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import dash_ag_grid as dag
import dash_bootstrap_components as dbc
from dash import html, dcc

from dash_app import theme as T

from dash_app.pages.paper_trading.data import (
    _ACCOUNT_ID, _get_engine, _net_entry, bs_val,
)


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
