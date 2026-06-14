"""
app/pages/paper_trading/callbacks.py — all Dash callbacks (registered on import).

Importing this module runs every @callback decorator, wiring the page. The
package __init__ imports it for that side effect — do not remove that import.
All callback ids, Inputs/Outputs/States and pattern-matched ids are preserved
byte-identically from the original monolithic paper_trading.py.
"""
from __future__ import annotations

import datetime
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import dash_bootstrap_components as dbc
from dash import html, dcc, callback, Input, Output, State, no_update, ctx, ALL

from app import theme as T
from app.grid_helpers import mrt_grid

from app.pages.paper_trading.data import (
    _ACCOUNT_ID, _pretty_strategy, _get_engine, _load_data, _net_entry,
    bs_val, _bs_full, _compute_risk_matrix, get_open_trade_groups_simple,
    live_market_value,
)
from app.pages.paper_trading.builders import (
    _grid, _OPEN_COLS, _CLOSED_COLS, _TXNS_COLS,
    _metric_card, _render_alert_badges, _build_legs_table,
    _plot_payoff, _plot_ic_payoff, _plot_equity_pnl,
    _build_ic_modal_body, _build_screener_modal_body, _build_equity_modal_body,
    _build_perf_chart, _build_equity_curve, _render_risk_table,
)


# ── Callbacks ─────────────────────────────────────────────────────────────────

@callback(
    Output("pt-metric-row",        "children"),
    Output("pt-open-grid",         "data"),
    Output("pt-closed-grid",       "data"),
    Output("pt-closed-chart",      "children"),
    Output("pt-txns-grid",         "data"),
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
        strategy = _pretty_strategy(str(grp["StrategyName"].iloc[0])) if not grp.empty else "?"

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

    # Deposited / baseline cash (deposits & withdrawals only — Balance table).
    deposit_cash = 0.0
    try:
        from sqlalchemy import text as _text
        with engine.connect() as conn:
            row = conn.execute(_text("""
                SELECT TOP 1 Amount FROM portfolio.Balance
                WHERE AccountId = :aid AND BalanceType = 'Cash'
                ORDER BY BusinessDate DESC
            """), {"aid": _ACCOUNT_ID}).fetchone()
            if row:
                deposit_cash = float(row[0])
    except Exception:
        pass

    # Cash moves on every trade: opening a short-premium position credits cash,
    # closing debits it. The transaction ledger is the source of truth, so live
    # cash = deposited cash + net cash flow of every (non-cash) trade.
    trade_cf = 0.0
    if not txns_df.empty:
        for _, r in txns_df.iterrows():
            if str(r.get("SecurityType", "")).lower() == "cash":
                continue
            dirn = str(r.get("Direction", "")).upper()
            qty  = float(r.get("Quantity") or 0)
            px   = float(r.get("TransactionPrice") or 0)
            mult = float(r.get("Multiplier") or 1)
            trade_cf += (1.0 if dirn == "SELL" else -1.0) * qty * px * mult
    cash_bal = deposit_cash + trade_cf

    # Live market value of open positions (negative for short premium) and the
    # resulting true account value.
    market_value, _mv_live, _mv_priced, _mv_total = live_market_value(open_groups)
    account_value = cash_bal + market_value

    # ── Metrics ───────────────────────────────────────────────────────────────
    n_open       = len(open_data)
    total_entry  = sum(r["_net"] for r in open_data)
    total_closed = sum(r["P&L $"] for r in closed_rows) if closed_rows else 0.0
    n_wins       = sum(1 for r in closed_rows if r.get("P&L $", 0) > 0) if closed_rows else 0
    # Total return vs starting capital (net deposits) — includes BOTH realized
    # P&L (already folded into cash) and unrealized P&L (via market value), so it
    # is non-zero whenever open positions have moved, not just on closed trades.
    starting_capital = deposit_cash if deposit_cash else (account_value or 0.0)
    ytd_return   = ((account_value - starting_capital) / starting_capital * 100) \
                   if starting_capital else 0.0

    today_str  = datetime.date.today().isoformat()
    today_pnl  = sum(
        r.get("P&L $", 0) for r in closed_rows
        if str(r.get("Close Date", ""))[:10] == today_str
    ) if closed_rows else 0.0

    n_closed     = len(closed_rows) if closed_rows else 0
    win_rate     = (n_wins / n_closed * 100) if n_closed > 0 else None
    gross_wins   = sum(r.get("P&L $", 0) for r in closed_rows if r.get("P&L $", 0) > 0) if closed_rows else 0.0
    gross_losses = abs(sum(r.get("P&L $", 0) for r in closed_rows if r.get("P&L $", 0) < 0)) if closed_rows else 0.0
    # Unrealized P&L on OPEN positions = entry premium (received/paid) + live market value.
    # e.g. short credit collected minus current cost to close.
    unrealized_pnl = total_entry + market_value

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
    mkt_val_str = f"{'-' if market_value < 0 else ''}${abs(market_value):,.2f}"

    row1 = html.Div([
        _metric("Account",       str(acct.get("AccountName", "—"))),
        _metric("Type",          str(acct.get("AccountType", "—"))),
        _metric("Status",        str(acct.get("Status", "—")), status_color),
        _metric("Cash Balance",  f"${cash_bal:,.2f}",
                T.SUCCESS if cash_bal >= 0 else T.DANGER),
        _metric("Account Value", f"${account_value:,.2f}",
                T.SUCCESS if account_value >= 0 else T.DANGER),
    ], style={"display": "flex", "gap": "10px", "flexWrap": "wrap"})

    row2 = html.Div([
        _metric("Open Trades",   str(n_open)),
        _metric("Market Value",  mkt_val_str,
                T.SUCCESS if market_value > 0 else T.DANGER if market_value < 0 else T.TEXT_MUTED),
        _metric("Today's P&L",  f"{'+'if today_pnl>=0 else ''}${today_pnl:,.2f}",
                T.SUCCESS if today_pnl > 0 else T.DANGER if today_pnl < 0 else T.TEXT_MUTED),
        _metric("Unrealized P&L", f"{'+'if unrealized_pnl>=0 else ''}${unrealized_pnl:,.2f}",
                T.SUCCESS if unrealized_pnl > 0 else T.DANGER if unrealized_pnl < 0 else T.TEXT_MUTED),
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
            "Strategy":   _pretty_strategy(str(r.get("Strategy", "?"))),
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
                "Strategy":   _pretty_strategy(str(r.get("StrategyName", ""))),
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
    Input("pt-open-grid-clicked", "value"),
    Input("pt-url",            "search"),
    State("pt-open-grid",      "data"),
    prevent_initial_call=True,
)
def open_position_modal(clicked_json, url_search, all_rows):
    from dash import ctx
    _loading = html.Div("Loading…", style={"color": T.TEXT_MUTED, "padding": "20px"})
    # Deep-link from blotter: /paper-trading?tgid=xxx
    if ctx.triggered_id == "pt-url" and url_search:
        from urllib.parse import parse_qs
        qs = parse_qs(url_search.lstrip("?"))
        tgid = (qs.get("tgid") or [""])[0].strip()
        if tgid:
            return True, "Position Detail", _loading, tgid
        return no_update, no_update, no_update, no_update

    if not clicked_json or not all_rows:
        return no_update, no_update, no_update, no_update

    import json
    try:
        payload = json.loads(clicked_json)
    except Exception:
        return no_update, no_update, no_update, no_update
    row_index = payload.get("rowIndex", -1)
    if not (0 <= row_index < len(all_rows)):
        return no_update, no_update, no_update, no_update

    row  = all_rows[row_index]
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
    strategy  = _pretty_strategy(str(grp["StrategyName"].iloc[0])) if not grp.empty else "?"
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
    Input("pt-modal-dismiss", "n_clicks"),
    prevent_initial_call=True,
)
def dismiss_modal(n_clicks):
    if n_clicks:
        return False
    return no_update


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
    Output("pt-txns-grid",  "data",      allow_duplicate=True),
    Output("pt-txn-count",  "children"),
    Input("pt-txn-search",       "value"),
    Input("pt-txn-filter-type",  "value"),
    Input("pt-txn-filter-dir",   "value"),
    Input("pt-txn-filter-strat", "value"),
    State("pt-txns-grid",        "data"),
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

    table = mrt_grid(
        aggrid_cols=[
            {"field": "Leg"},
            {"field": "Symbol"},
            {"field": "Dir"},
            {"field": "Qty",         "type": "numericColumn"},
            {"field": "Entry"},
            {"field": "Close (est)"},
        ],
        data=rows,
        enable_pagination=False,
        height=240,
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
        # rgb() (not the #6366f1 hex) so z_polish.css's broad
        # `button[style*="6366f1"]` gradient rule doesn't hijack the pill;
        # color="link" keeps it off `.btn-primary`. Inline styles then win,
        # so selected (filled) vs unselected (outline) stays readable.
        accent_rgb = "rgb(99,102,241)"
        return dbc.Button(
            label,
            id={"type": "pt-risk-pill", "tgid": tgid},
            n_clicks=0,
            size="sm",
            color="link",
            style={
                "display": "inline-block",
                "padding": "4px 12px", "borderRadius": "16px",
                "fontSize": "12px", "fontWeight": "600",
                "marginRight": "6px", "marginBottom": "6px",
                "textDecoration": "none",
                "border": f"1px solid {accent_rgb}",
                "backgroundColor": accent_rgb if selected else "transparent",
                "color": "#fff" if selected else accent_rgb,
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
            color="link",
            style={
                "padding": "3px 10px", "borderRadius": "12px",
                "fontSize": "11px", "fontWeight": "600",
                "marginRight": "5px", "marginBottom": "5px",
                "textDecoration": "none",
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

    # If no live underlying price was obtained, every leg was skipped and the
    # whole matrix is $0.00 — say so instead of showing silent zeros.
    if not mx.get("ref_spots"):
        return dbc.Alert(
            "Couldn't fetch a live underlying price (Polygon returned nothing). "
            "The risk matrix needs a live spot price to value the options — "
            "check that POLYGON_API_KEY is set and that the market is open.",
            color="warning", style={"fontSize": "13px"},
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
