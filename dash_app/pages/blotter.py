"""
dash_app/pages/blotter.py
Landing page — Morning blotter with summary metrics, active positions,
equity curve, today's activity, alerts, and full trade history.
"""
from __future__ import annotations

import datetime
import pandas as pd
import plotly.graph_objects as go
import dash_ag_grid as dag
import dash_bootstrap_components as dbc
from dash import html, dcc, callback, Input, Output, no_update, State

from dash_app import theme as T

_ACCOUNT_ID = 1


# ── DB helpers ────────────────────────────────────────────────────────────────

def _get_engine():
    from db.client import get_engine
    return get_engine()


def _load_transactions() -> pd.DataFrame:
    """Load all transactions via engine.positions."""
    try:
        from engine.positions import load_transactions
        engine = _get_engine()
        return load_transactions(engine, _ACCOUNT_ID)
    except Exception:
        return pd.DataFrame()


def _load_open_groups() -> dict:
    try:
        from engine.positions import load_transactions, get_open_trade_groups
        engine = _get_engine()
        txns = load_transactions(engine, _ACCOUNT_ID)
        if txns.empty:
            return {}
        return get_open_trade_groups(txns)
    except Exception:
        return {}


def _load_closed_rows() -> list[dict]:
    try:
        from engine.positions import load_transactions, get_closed_trade_groups
        engine = _get_engine()
        txns = load_transactions(engine, _ACCOUNT_ID)
        if txns.empty:
            return []
        return get_closed_trade_groups(txns)
    except Exception:
        return []


# ── Metric computation ────────────────────────────────────────────────────────

def _compute_metrics(txns: pd.DataFrame, open_groups: dict, closed_rows: list[dict]) -> dict:
    today = datetime.date.today()
    cutoff_30d = today - datetime.timedelta(days=30)

    # Open position count
    open_count = len(open_groups)

    # Closed trades in last 30 days for win rate
    wins_30d = 0
    total_30d = 0
    total_realised = 0.0
    today_realised = 0.0

    for row in closed_rows:
        pnl = row.get("P&L") or row.get("pnl") or 0
        try:
            pnl = float(str(pnl).replace("$", "").replace(",", "").replace("+", ""))
        except Exception:
            pnl = 0.0

        close_date = row.get("Close Date") or row.get("close_date") or row.get("ClosedAt")
        if isinstance(close_date, str):
            try:
                close_date = datetime.date.fromisoformat(close_date[:10])
            except Exception:
                close_date = None
        elif hasattr(close_date, "date"):
            close_date = close_date.date()

        total_realised += pnl

        if close_date and close_date == today:
            today_realised += pnl

        if close_date and close_date >= cutoff_30d:
            total_30d += 1
            if pnl > 0:
                wins_30d += 1

    win_rate = (wins_30d / total_30d * 100) if total_30d > 0 else 0.0

    # Unrealised P&L estimate (net entry cash flow from open positions)
    unrealised = 0.0
    for tgid, grp in open_groups.items():
        for _, r in grp.iterrows():
            direction = str(r.get("Direction", "")).upper()
            mult = float(r.get("Multiplier", 1) or 1)
            qty = float(r.get("Quantity", 0) or 0)
            price = float(r.get("TransactionPrice", 0) or 0)
            sign = -1.0 if direction == "BUY" else 1.0
            unrealised += sign * qty * price * mult

    total_pnl = total_realised + unrealised

    return {
        "today_pnl": today_realised,
        "total_pnl": total_pnl,
        "open_count": open_count,
        "win_rate": win_rate,
        "total_30d": total_30d,
    }


# ── Summary card builder ──────────────────────────────────────────────────────

def _metric_card(label: str, value: str, subtitle: str, color: str) -> dbc.Col:
    return dbc.Col(
        dbc.Card(
            dbc.CardBody([
                html.Div(label, style={
                    "color": T.TEXT_MUTED, "fontSize": "10px", "fontWeight": "700",
                    "textTransform": "uppercase", "letterSpacing": "0.08em",
                }),
                html.Div(value, style={
                    "color": color, "fontSize": "1.8rem", "fontWeight": "700",
                    "fontFamily": "JetBrains Mono, monospace", "lineHeight": "1.2",
                    "marginTop": "4px",
                }),
                html.Div(subtitle, style={
                    "color": T.TEXT_MUTED, "fontSize": "11px", "marginTop": "4px",
                }),
            ]),
            style={**T.STYLE_CARD, "borderLeft": f"3px solid {color}", "padding": "0"},
        ),
        xs=12, sm=6, lg=3,
    )


def _fmt_pnl(v: float) -> tuple[str, str]:
    """Return (formatted_string, color)."""
    color = T.SUCCESS if v >= 0 else T.DANGER
    sign = "+" if v >= 0 else ""
    return f"{sign}${v:,.2f}", color


# ── Active positions grid ─────────────────────────────────────────────────────

_ACTIVE_COLS = [
    {"field": "Strategy",    "width": 140},
    {"field": "Ticker",      "width": 80},
    {"field": "Side",        "width": 70,
     "cellStyle": {"function": "params.value === 'LONG' ? {color: '#10b981'} : {color: '#ef4444'}"}},
    {"field": "Entry Date",  "width": 110},
    {"field": "Entry Price", "width": 100},
    {"field": "P&L $",       "width": 110,
     "cellStyle": {"function": "params.value > 0 ? {color: '#10b981', fontWeight: '600'} : params.value < 0 ? {color: '#ef4444', fontWeight: '600'} : {}"}},
    {"field": "P&L %",       "width": 100,
     "cellStyle": {"function": "params.value > 0 ? {color: '#10b981'} : params.value < 0 ? {color: '#ef4444'} : {}"}},
    {"field": "DTE",         "width": 65, "type": "numericColumn",
     "cellStyle": {"function": "params.value != null && params.value <= 7 ? {color: '#ef4444', fontWeight: '700'} : {}"}},
    {"field": "Max Loss",    "width": 100},
    {"field": "Status",      "width": 110},
    {"field": "View", "width": 70, "sortable": False, "filter": False,
     "cellStyle": {"function": "({color: '#6366f1', fontWeight: '600', cursor: 'pointer', textDecoration: 'underline'})"}},
    {"field": "_tgid", "hide": True},
]


def _build_active_rows(open_groups: dict) -> list[dict]:
    rows = []
    today = datetime.date.today()
    for tgid, grp in open_groups.items():
        if grp.empty:
            continue

        first = grp.iloc[0]
        strategy = str(first.get("StrategyName", "—"))
        ticker = str(first.get("Underlying", first.get("Symbol", "—")))

        # Net entry — negative = credit received, positive = debit paid
        net_entry = 0.0
        for _, r in grp.iterrows():
            direction = str(r.get("Direction", "")).upper()
            mult = float(r.get("Multiplier", 1) or 1)
            qty = float(r.get("Quantity", 0) or 0)
            price = float(r.get("TransactionPrice", 0) or 0)
            sign = -1.0 if direction == "BUY" else 1.0
            net_entry += sign * qty * price * mult

        # DTE — look at option legs
        dte = None
        opt_legs = grp[grp.get("SecurityType", pd.Series(dtype=str)).str.lower() == "option"] \
            if "SecurityType" in grp.columns else pd.DataFrame()
        if not opt_legs.empty and "Expiration" in opt_legs.columns:
            exps = opt_legs["Expiration"].dropna()
            if not exps.empty:
                earliest = exps.min()
                if hasattr(earliest, "date"):
                    earliest = earliest.date()
                elif isinstance(earliest, str):
                    try:
                        earliest = datetime.date.fromisoformat(str(earliest)[:10])
                    except Exception:
                        earliest = None
                if earliest:
                    dte = (earliest - today).days

        # Side
        buy_qty = sum(float(r.get("Quantity", 0) or 0)
                      for _, r in grp.iterrows()
                      if str(r.get("Direction", "")).upper() == "BUY")
        sell_qty = sum(float(r.get("Quantity", 0) or 0)
                       for _, r in grp.iterrows()
                       if str(r.get("Direction", "")).upper() == "SELL")
        side = "LONG" if buy_qty >= sell_qty else "SHORT"

        # Entry date
        entry_date = ""
        if "BusinessDate" in grp.columns:
            bd = grp["BusinessDate"].dropna()
            if not bd.empty:
                d = bd.min()
                entry_date = str(d)[:10] if d else ""

        # Entry price (net per share/contract)
        qty_sum = sum(float(r.get("Quantity", 0) or 0) for _, r in grp.iterrows())
        entry_price_disp = f"${abs(net_entry):,.2f}" if net_entry != 0 else "—"

        # Max loss estimate (for credit trades: credit received; for debits: cost)
        max_loss = net_entry  # positive = credit (max profit), negative = debit (max loss)

        # Unrealised P&L: credit trades profit when position expires worthless
        # Use net entry as unrealised proxy (credit = current best case)
        pnl_dollar = net_entry
        pnl_pct = 0.0
        if abs(net_entry) > 0:
            pnl_pct = 0.0  # Can't compute without mark-to-market prices

        # Status
        if dte is not None and dte <= 7:
            status = "EXPIRING SOON"
        elif net_entry > 0 and net_entry >= abs(max_loss) * 0.5:
            status = "AT TARGET"
        else:
            status = "OPEN"

        rows.append({
            "Strategy":    strategy,
            "Ticker":      ticker,
            "Side":        side,
            "Entry Date":  entry_date,
            "Entry Price": entry_price_disp,
            "P&L $":       round(pnl_dollar, 2),
            "P&L %":       round(pnl_pct, 2),
            "DTE":         dte,
            "Max Loss":    f"${abs(max_loss):,.2f}" if max_loss != 0 else "—",
            "Status":      status,
            "View":        "View →",
            "_tgid":       str(tgid),
        })

    return rows


# ── Equity curve ─────────────────────────────────────────────────────────────

def _build_equity_curve(closed_rows: list[dict]) -> go.Figure:
    today = datetime.date.today()
    cutoff = today - datetime.timedelta(days=90)

    records = []
    for row in closed_rows:
        pnl = row.get("P&L") or row.get("pnl") or 0
        try:
            pnl = float(str(pnl).replace("$", "").replace(",", "").replace("+", ""))
        except Exception:
            pnl = 0.0

        close_date = row.get("Close Date") or row.get("close_date") or row.get("ClosedAt")
        if isinstance(close_date, str):
            try:
                close_date = datetime.date.fromisoformat(close_date[:10])
            except Exception:
                close_date = None
        elif hasattr(close_date, "date"):
            close_date = close_date.date()

        if close_date and close_date >= cutoff:
            records.append({"date": close_date, "pnl": pnl})

    fig = go.Figure()
    fig.update_layout(
        paper_bgcolor=T.BG_CARD,
        plot_bgcolor=T.BG_CARD,
        height=280,
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis=dict(showgrid=False, color=T.TEXT_MUTED, tickfont=dict(size=10)),
        yaxis=dict(showgrid=True, gridcolor=T.BORDER, color=T.TEXT_MUTED,
                   tickfont=dict(size=10), tickprefix="$"),
        showlegend=False,
        font=dict(family="Inter, sans-serif", color=T.TEXT_SEC),
    )

    if not records:
        fig.add_annotation(
            text="No closed trade data yet",
            xref="paper", yref="paper", x=0.5, y=0.5,
            showarrow=False, font=dict(color=T.TEXT_MUTED, size=13),
        )
        return fig

    df = pd.DataFrame(records).sort_values("date")
    df["cumulative"] = df["pnl"].cumsum()

    color = T.SUCCESS if df["cumulative"].iloc[-1] >= 0 else T.DANGER
    fill_color = "rgba(16,185,129,0.15)" if df["cumulative"].iloc[-1] >= 0 else "rgba(239,68,68,0.15)"

    fig.add_trace(go.Scatter(
        x=df["date"], y=df["cumulative"],
        mode="lines",
        line=dict(color=color, width=2),
        fill="tozeroy",
        fillcolor=fill_color,
        hovertemplate="%{x|%b %d}<br>Cumulative P&L: $%{y:,.2f}<extra></extra>",
    ))

    return fig


# ── Today's activity grid ─────────────────────────────────────────────────────

_ACTIVITY_COLS = [
    {"field": "Time",     "width": 90},
    {"field": "Strategy", "width": 150, "flex": 2},
    {"field": "Ticker",   "width": 80},
    {"field": "Action",   "width": 90,
     "cellStyle": {"function": "params.value === 'OPEN' ? {color: '#10b981'} : params.value === 'CLOSE' ? {color: '#ef4444'} : {color: '#f59e0b'}"}},
    {"field": "Price",    "width": 90},
    {"field": "P&L",      "width": 100,
     "cellStyle": {"function": "typeof params.value === 'number' && params.value > 0 ? {color: '#10b981'} : typeof params.value === 'number' && params.value < 0 ? {color: '#ef4444'} : {}"}},
]


def _build_activity_rows(txns: pd.DataFrame) -> list[dict]:
    if txns.empty:
        return []

    today = datetime.date.today()
    rows = []

    if "BusinessDate" not in txns.columns:
        return []

    txns_copy = txns.copy()
    txns_copy["_date"] = pd.to_datetime(txns_copy["BusinessDate"], errors="coerce").dt.date
    today_txns = txns_copy[txns_copy["_date"] == today]

    for _, r in today_txns.iterrows():
        direction = str(r.get("Direction", "")).upper()
        action = "OPEN" if direction == "BUY" else "CLOSE"
        price = r.get("TransactionPrice", 0)
        try:
            price_str = f"${float(price):,.2f}"
        except Exception:
            price_str = "—"

        time_str = ""
        bd = r.get("BusinessDate")
        if hasattr(bd, "strftime"):
            try:
                time_str = bd.strftime("%H:%M")
            except Exception:
                time_str = str(bd)[:10]
        else:
            time_str = str(bd)[:10] if bd else "—"

        rows.append({
            "Time":     time_str,
            "Strategy": str(r.get("StrategyName", "—")),
            "Ticker":   str(r.get("Underlying", r.get("Symbol", "—"))),
            "Action":   action,
            "Price":    price_str,
            "P&L":      None,
        })

    return rows


# ── Alerts ────────────────────────────────────────────────────────────────────

def _build_alerts(open_groups: dict) -> list[dbc.Alert]:
    alerts = []
    today = datetime.date.today()

    for tgid, grp in open_groups.items():
        if grp.empty:
            continue
        first = grp.iloc[0]
        ticker = str(first.get("Underlying", first.get("Symbol", "?")))

        # DTE check
        if "SecurityType" in grp.columns and "Expiration" in grp.columns:
            opt_legs = grp[grp["SecurityType"].str.lower() == "option"]
            if not opt_legs.empty:
                exps = opt_legs["Expiration"].dropna()
                if not exps.empty:
                    earliest = exps.min()
                    if hasattr(earliest, "date"):
                        earliest = earliest.date()
                    elif isinstance(earliest, str):
                        try:
                            earliest = datetime.date.fromisoformat(str(earliest)[:10])
                        except Exception:
                            earliest = None
                    if earliest:
                        dte = (earliest - today).days
                        if dte <= 7:
                            alerts.append(dbc.Alert(
                                f"⚠️ {ticker} options expire in {dte} day{'s' if dte != 1 else ''} — consider closing",
                                color="warning",
                                style={"padding": "8px 14px", "marginBottom": "6px",
                                       "fontSize": "13px", "borderRadius": "6px"},
                                dismissable=True,
                            ))

        # P&L check: net entry credit >= 50% of max credit = at target
        net_entry = 0.0
        for _, r in grp.iterrows():
            direction = str(r.get("Direction", "")).upper()
            mult = float(r.get("Multiplier", 1) or 1)
            qty = float(r.get("Quantity", 0) or 0)
            price = float(r.get("TransactionPrice", 0) or 0)
            sign = -1.0 if direction == "BUY" else 1.0
            net_entry += sign * qty * price * mult

        if net_entry > 0:
            # Credit trade — current unrealised profit proxy
            # 50% profit target alert (simplified: if net credit > 0 at all, remind)
            pass  # Would need mark-to-market for real check

        # Stop loss: P&L <= -2x credit
        # Without mark-to-market data this is a placeholder

    return alerts


# ── Full blotter grid ─────────────────────────────────────────────────────────

_BLOTTER_COLS = [
    {"field": "Date",           "width": 110, "sort": "desc"},
    {"field": "Strategy",       "minWidth": 130, "flex": 2},
    {"field": "Ticker",         "width": 80},
    {"field": "Action",         "width": 80},
    {"field": "Qty",            "width": 65, "type": "numericColumn"},
    {"field": "Price",          "width": 90},
    {"field": "Cash Flow",      "width": 110,
     "cellStyle": {"function": "typeof params.value === 'number' && params.value > 0 ? {color: '#10b981'} : typeof params.value === 'number' && params.value < 0 ? {color: '#ef4444'} : {}"}},
    {"field": "Cumulative P&L", "width": 120,
     "cellStyle": {"function": "typeof params.value === 'number' && params.value > 0 ? {color: '#10b981'} : typeof params.value === 'number' && params.value < 0 ? {color: '#ef4444'} : {}"}},
    {"field": "Source",         "width": 85},
    {"field": "Notes",          "minWidth": 100, "flex": 2},
]


def _build_blotter_rows(txns: pd.DataFrame) -> list[dict]:
    if txns.empty:
        return []

    rows = []
    cumulative = 0.0

    txns_sorted = txns.copy()
    if "BusinessDate" in txns_sorted.columns:
        txns_sorted = txns_sorted.sort_values("BusinessDate", ascending=True)

    for _, r in txns_sorted.iterrows():
        direction = str(r.get("Direction", "")).upper()
        qty = float(r.get("Quantity", 0) or 0)
        price = float(r.get("TransactionPrice", 0) or 0)
        mult = float(r.get("Multiplier", 1) or 1)
        commission = float(r.get("Commission", 0) or 0)
        sign = 1.0 if direction == "SELL" else -1.0
        cash_flow = sign * qty * price * mult - commission
        cumulative += cash_flow

        bd = r.get("BusinessDate")
        date_str = str(bd)[:10] if bd else "—"

        rows.append({
            "Date":           date_str,
            "Strategy":       str(r.get("StrategyName", "—")),
            "Ticker":         str(r.get("Underlying", r.get("Symbol", "—"))),
            "Action":         direction,
            "Qty":            int(qty) if qty == int(qty) else qty,
            "Price":          f"${price:,.2f}" if price else "—",
            "Cash Flow":      round(cash_flow, 2),
            "Cumulative P&L": round(cumulative, 2),
            "Source":         str(r.get("Source", "Paper")),
            "Notes":          str(r.get("Notes", "") or ""),
        })

    rows.reverse()  # newest first
    return rows


# ── Empty state ───────────────────────────────────────────────────────────────

def _db_empty_state() -> html.Div:
    return html.Div([
        html.Div("🗄️", style={"fontSize": "48px", "marginBottom": "12px"}),
        html.Div("Connect your database to see live blotter",
                 style={"color": T.TEXT_MUTED, "fontSize": "16px", "fontWeight": "500"}),
        html.Div("Check your SQL Server connection and ensure the AlanStrats database is reachable.",
                 style={"color": T.TEXT_MUTED, "fontSize": "12px", "marginTop": "6px"}),
    ], style={"textAlign": "center", "padding": "60px 20px"})


def _section_header(title: str, badge: str | None = None) -> html.Div:
    children = [
        html.Span(title, style={
            "color": T.TEXT_PRIMARY, "fontSize": "14px",
            "fontWeight": "600", "letterSpacing": "0.02em",
        }),
    ]
    if badge is not None:
        children.append(html.Span(badge, style={
            "backgroundColor": T.ACCENT_DIM, "color": T.ACCENT,
            "fontSize": "11px", "fontWeight": "600",
            "padding": "2px 8px", "borderRadius": "10px",
            "marginLeft": "10px",
        }))
    return html.Div(children, style={"marginBottom": "10px", "display": "flex", "alignItems": "center"})


# ── Layout ────────────────────────────────────────────────────────────────────

def layout() -> html.Div:
    # Load all data once
    txns = pd.DataFrame()
    open_groups: dict = {}
    closed_rows: list = []
    db_ok = True

    try:
        txns = _load_transactions()
        if not txns.empty:
            from engine.positions import get_open_trade_groups, get_closed_trade_groups
            open_groups = get_open_trade_groups(txns)
            closed_rows = get_closed_trade_groups(txns)
    except Exception:
        db_ok = False

    metrics = _compute_metrics(txns, open_groups, closed_rows) if db_ok else {
        "today_pnl": 0.0, "total_pnl": 0.0, "open_count": 0, "win_rate": 0.0, "total_30d": 0,
    }

    # ── Summary cards ──────────────────────────────────────────────────────────
    today_pnl_str, today_color = _fmt_pnl(metrics["today_pnl"])
    total_pnl_str, total_color = _fmt_pnl(metrics["total_pnl"])
    open_count = metrics["open_count"]
    win_rate = metrics["win_rate"]
    total_30d = metrics["total_30d"]

    summary_bar = dbc.Row([
        _metric_card(
            "TODAY P&L", today_pnl_str,
            "Realised today",
            today_color,
        ),
        _metric_card(
            "TOTAL P&L", total_pnl_str,
            "Realised + unrealised all-time",
            total_color,
        ),
        _metric_card(
            "OPEN POSITIONS", str(open_count),
            "Active paper trades",
            T.ACCENT,
        ),
        _metric_card(
            "WIN RATE (30D)",
            f"{win_rate:.0f}%",
            f"{total_30d} closed trades in last 30 days",
            T.SUCCESS if win_rate >= 50 else T.WARNING,
        ),
    ], className="g-3", style={"marginBottom": "20px"})

    # ── Active positions + equity curve ───────────────────────────────────────
    active_rows = _build_active_rows(open_groups)
    active_grid = dag.AgGrid(
        id="blotter-active-grid",
        columnDefs=_ACTIVE_COLS,
        rowData=active_rows,
        defaultColDef={"resizable": True, "sortable": True, "filter": True},
        dashGridOptions={
            "animateRows": True,
            "domLayout": "autoHeight",
            "rowSelection": "single",
        },
        className=T.AGGRID_THEME,
        style={"width": "100%"},
    )

    equity_fig = _build_equity_curve(closed_rows)

    mid_row = dbc.Row([
        dbc.Col([
            _section_header("Active Positions", str(len(active_rows))),
            active_grid if active_rows else html.Div(
                "No open positions",
                style={"color": T.TEXT_MUTED, "fontSize": "13px",
                       "padding": "24px 0", "textAlign": "center"},
            ),
        ], xs=12, lg=7, style={
            "backgroundColor": T.BG_CARD, "border": f"1px solid {T.BORDER}",
            "borderRadius": "10px", "padding": "16px",
        }),
        dbc.Col([
            _section_header("Equity Curve", "90d"),
            dcc.Graph(
                figure=equity_fig,
                config={"displayModeBar": False},
                style={"height": "280px"},
            ),
        ], xs=12, lg=5, style={
            "backgroundColor": T.BG_CARD, "border": f"1px solid {T.BORDER}",
            "borderRadius": "10px", "padding": "16px",
        }),
    ], className="g-3", style={"marginBottom": "20px"})

    # ── Today's activity ──────────────────────────────────────────────────────
    activity_rows = _build_activity_rows(txns)
    activity_section = html.Div([
        _section_header("Today's Activity", str(len(activity_rows)) if activity_rows else None),
        dag.AgGrid(
            id="blotter-activity-grid",
            columnDefs=_ACTIVITY_COLS,
            rowData=activity_rows,
            defaultColDef={"resizable": True, "sortable": True, "filter": False},
            dashGridOptions={"animateRows": True, "domLayout": "autoHeight"},
            className=T.AGGRID_THEME,
            style={"width": "100%"},
        ) if activity_rows else html.Div(
            "No activity today",
            style={"color": T.TEXT_MUTED, "fontSize": "13px",
                   "padding": "20px 0", "textAlign": "center"},
        ),
    ], style={
        **T.STYLE_CARD, "padding": "16px", "marginBottom": "20px",
    })

    # ── Alerts ────────────────────────────────────────────────────────────────
    alerts_list = _build_alerts(open_groups)
    alerts_section = html.Div([
        _section_header("Alerts", str(len(alerts_list)) if alerts_list else None),
        html.Div(
            alerts_list if alerts_list else html.Div(
                "No alerts — all positions look healthy",
                style={"color": T.TEXT_MUTED, "fontSize": "13px",
                       "padding": "12px 0"},
            ),
        ),
    ], style={**T.STYLE_CARD, "padding": "16px", "marginBottom": "20px"})

    # ── Full blotter ──────────────────────────────────────────────────────────
    blotter_rows = _build_blotter_rows(txns)
    blotter_section = html.Div([
        html.Div([
            _section_header("Full Trade Blotter", str(len(blotter_rows))),
            html.Button(
                "Export CSV",
                id="blotter-export-btn",
                n_clicks=0,
                style={
                    "backgroundColor": T.BG_ELEVATED,
                    "border": f"1px solid {T.BORDER_BRT}",
                    "color": T.TEXT_SEC,
                    "fontSize": "12px",
                    "padding": "4px 12px",
                    "borderRadius": "5px",
                    "cursor": "pointer",
                },
            ),
        ], style={"display": "flex", "justifyContent": "space-between", "alignItems": "center"}),
        dag.AgGrid(
            id="blotter-full-grid",
            columnDefs=_BLOTTER_COLS,
            rowData=blotter_rows,
            defaultColDef={"resizable": True, "sortable": True, "filter": True},
            dashGridOptions={
                "animateRows": True,
                "pagination": True,
                "paginationPageSize": 50,
                "paginationPageSizeSelector": [25, 50, 100],
            },
            className=T.AGGRID_THEME,
            style={"width": "100%", "height": "400px"},
            csvExportParams={"fileName": "trade_blotter.csv"},
        ) if blotter_rows else html.Div(
            "No trades recorded yet",
            style={"color": T.TEXT_MUTED, "fontSize": "13px",
                   "padding": "40px 0", "textAlign": "center"},
        ),
    ], style={**T.STYLE_CARD, "padding": "16px"})

    # ── Auto-refresh interval + nav ───────────────────────────────────────────
    refresh = dcc.Interval(id="blotter-refresh", interval=60_000, n_intervals=0)
    nav = dcc.Location(id="blotter-nav", refresh=True)

    # ── No-DB fallback ────────────────────────────────────────────────────────
    if not db_ok:
        return html.Div([
            refresh,
            html.Div([
                html.H4("Morning Blotter", style={
                    "color": T.TEXT_PRIMARY, "fontWeight": "700",
                    "marginBottom": "4px",
                }),
                html.Div(
                    datetime.date.today().strftime("%A, %B %#d, %Y"),
                    style={"color": T.TEXT_MUTED, "fontSize": "13px"},
                ),
            ], style={"marginBottom": "24px"}),
            dbc.Card(dbc.CardBody(_db_empty_state()),
                     style={**T.STYLE_CARD, "borderLeft": f"3px solid {T.WARNING}"}),
        ], style=T.STYLE_PAGE)

    # ── Page heading ──────────────────────────────────────────────────────────
    today_str = datetime.date.today().strftime("%A, %B %#d, %Y")

    heading = html.Div([
        html.Div([
            html.H4("Morning Blotter", style={
                "color": T.TEXT_PRIMARY, "fontWeight": "700",
                "marginBottom": "2px", "fontSize": "20px",
            }),
            html.Div(today_str, style={"color": T.TEXT_MUTED, "fontSize": "13px"}),
        ]),
        html.Div(
            f"Last refreshed: {datetime.datetime.now().strftime('%H:%M:%S')}",
            style={"color": T.TEXT_MUTED, "fontSize": "11px", "alignSelf": "flex-end"},
        ),
    ], style={
        "display": "flex", "justifyContent": "space-between",
        "alignItems": "flex-start", "marginBottom": "20px",
    })

    return html.Div([
        refresh,
        nav,
        heading,
        summary_bar,
        mid_row,
        activity_section,
        alerts_section,
        blotter_section,
    ], style=T.STYLE_PAGE)


# ── Callbacks ────────────────────────────────────────────────────────────────

@callback(
    Output("blotter-full-grid", "exportDataAsCsv"),
    Input("blotter-export-btn", "n_clicks"),
    prevent_initial_call=True,
)
def export_csv(n_clicks):
    if n_clicks:
        return True
    return no_update


@callback(
    Output("blotter-nav", "href"),
    Input("blotter-active-grid", "selectedRows"),
    prevent_initial_call=True,
)
def view_position(selected_rows):
    if not selected_rows:
        return no_update
    tgid = (selected_rows[0] or {}).get("_tgid", "")
    if not tgid:
        return no_update
    return f"/paper-trading?tgid={tgid}"
