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
from dash import html, dcc, callback, Input, Output, State, no_update, ctx

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
    {"field": "Net Entry",   "minWidth": 100, "flex": 1},
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
    {"field": "P&L",         "minWidth": 100, "flex": 1},
    {"field": "Result",      "minWidth": 75,  "width": 85},
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
    if strikes.empty:
        return None

    s_min  = float(strikes.min())
    s_max  = float(strikes.max())
    spread = max(s_max - s_min, 5.0)
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

def _build_legs_table(grp: pd.DataFrame) -> dag.AgGrid:
    legs = []
    for _, r in grp.iterrows():
        stype = str(r.get("SecurityType", "")).lower()
        if stype == "cash":
            continue
        px = r.get("TransactionPrice")
        legs.append({
            "Symbol":    str(r.get("Symbol", "")),
            "Type":      str(r.get("OptionType") or stype).upper(),
            "Strike":    str(r.get("Strike") or "—"),
            "Expiry":    str(r.get("Expiration") or "—")[:10],
            "Dir":       str(r.get("Direction", "")),
            "Qty":       float(r.get("Quantity") or 0),
            "Price":     f"${float(px):,.2f}" if px is not None else "—",
        })

    return dag.AgGrid(
        columnDefs=[
            {"field": "Symbol",  "flex": 1},
            {"field": "Type",    "width": 80},
            {"field": "Strike",  "width": 90},
            {"field": "Expiry",  "width": 110},
            {"field": "Dir",     "width": 80},
            {"field": "Qty",     "width": 70, "type": "numericColumn"},
            {"field": "Price",   "width": 100},
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

    # 5-column metric row
    dte_str  = str(dte_remaining) if dte_remaining is not None else "—"
    days_str = str(days_held)     if days_held     is not None else "—"
    metrics  = html.Div([
        _metric_card("Net Credit",    f"${net_credit:.2f}",   T.SUCCESS if net_credit >= 0 else T.DANGER),
        _metric_card("50% Target",    f"${profit_target:.2f}", T.SUCCESS),
        _metric_card("2× Stop",       f"${stop_loss:.2f}",    T.DANGER),
        _metric_card("DTE Remaining", dte_str,
                     T.DANGER if (dte_remaining or 999) <= 7 else
                     (T.WARNING if (dte_remaining or 999) <= 21 else T.TEXT_PRIMARY)),
        _metric_card("Days Held",     days_str),
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
        spot=None,
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
    legs_table = _build_legs_table(grp_sorted)

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
    opt = grp[grp["SecurityType"].str.lower() == "option"].copy() \
        if "SecurityType" in grp.columns else pd.DataFrame()

    if opt.empty:
        # No options — fall through to generic payoff
        fig = _plot_payoff(grp, None)
        return [
            html.P("No option legs found.", style={"color": T.TEXT_MUTED}),
            dcc.Graph(figure=fig, config={"displayModeBar": False}) if fig else html.Div(),
            _build_legs_table(grp),
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

    dte_str  = str(dte_remaining) if dte_remaining is not None else "—"
    days_str = str(days_held)     if days_held     is not None else "—"
    metrics  = html.Div([
        _metric_card(label_type,      f"${net_credit:.2f}",   T.SUCCESS if is_credit else T.DANGER),
        _metric_card("50% Target",    f"${profit_target:.2f}", T.SUCCESS),
        _metric_card("DTE Remaining", dte_str,
                     T.DANGER if (dte_remaining or 999) <= 7 else
                     (T.WARNING if (dte_remaining or 999) <= 21 else T.TEXT_PRIMARY)),
        _metric_card("Days Held",     days_str),
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

    payoff_fig = _plot_payoff(grp, None)
    chart      = dcc.Graph(figure=payoff_fig, config={"displayModeBar": False}) if payoff_fig else html.Div()
    caption    = html.P(
        "Payoff at expiration · Coloured dotted lines = strike levels · "
        "Green fill = profit zone · Red fill = loss zone",
        style={"color": T.TEXT_MUTED, "fontSize": "11px", "marginTop": "4px"},
    )

    legs_table = _build_legs_table(grp)

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
                                     clearable=True, style={"fontSize": "12px", "marginBottom": "8px"}),
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
                        dbc.Col(dcc.Dropdown(
                            id="pt-cash-dir",
                            options=[{"label": "Deposit", "value": "DEPOSIT"},
                                     {"label": "Withdrawal", "value": "WITHDRAWAL"}],
                            value="DEPOSIT", clearable=False,
                            style={"fontSize": "13px"},
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
                            clearable=True, style={"fontSize": "13px"},
                        ), width=2),
                        dbc.Col(dcc.Dropdown(
                            id="pt-txn-filter-dir", placeholder="Direction",
                            clearable=True, style={"fontSize": "13px"},
                        ), width=2),
                        dbc.Col(dcc.Dropdown(
                            id="pt-txn-filter-strat", placeholder="Strategy",
                            clearable=True, style={"fontSize": "13px"},
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
            "DTE":         dte if dte is not None else "—",
            "Net Entry":   f"{'+' if ne >= 0 else ''}${ne:,.2f}",
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
    metrics = html.Div([
        _metric("Account",       str(acct.get("AccountName", "—"))),
        _metric("Type",          str(acct.get("AccountType", "—"))),
        _metric("Status",        str(acct.get("Status", "—")), status_color),
        _metric("Cash Balance",  f"${cash_bal:,.0f}",
                T.SUCCESS if cash_bal >= 0 else T.DANGER),
        _metric("Open Trades",   str(n_open)),
        _metric("Realized P&L",  f"{'+'if total_closed>=0 else ''}${total_closed:,.2f}",
                T.SUCCESS if total_closed >= 0 else T.DANGER),
        _metric("YTD Return",    f"{'+'if ytd_return>=0 else ''}{ytd_return:.1f}%",
                T.SUCCESS if ytd_return >= 0 else T.DANGER),
    ], style={"display": "flex", "gap": "10px", "flexWrap": "wrap"})

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
    Output("pt-selected-tgid", "data"),
    Input("pt-open-grid",      "selectedRows"),
    prevent_initial_call=True,
)
def open_position_modal(selected_rows):
    if not selected_rows:
        return no_update, no_update, no_update

    row = selected_rows[0]
    tgid = str(row.get("_tgid", "") or "").strip()
    if not tgid:
        return no_update, no_update, no_update

    underlying = str(row.get("Underlying", row.get("Trade Group", "?")))
    strategy   = str(row.get("Strategy", ""))
    title      = f"{underlying}  ·  {strategy}"
    return True, title, tgid


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
    Output("pt-modal", "is_open", allow_duplicate=True),
    Input("pt-modal-dismiss", "n_clicks"),
    prevent_initial_call=True,
)
def dismiss_modal(n_clicks):
    if n_clicks:
        return False
    return no_update


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
