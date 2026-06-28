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
    live_market_value, mtm_equity_series, position_pnl, position_risk,
)
from app.pages.paper_trading.builders import (
    _grid, _OPEN_COLS, _CLOSED_COLS, _TXNS_COLS,
    _metric_card, _render_alert_badges, _build_legs_table,
    _plot_payoff, _plot_ic_payoff, _plot_equity_pnl,
    _build_ic_modal_body, _build_screener_modal_body, _build_equity_modal_body,
    _build_perf_chart, _build_equity_curve, _render_risk_table, _GRAPH_CFG,
)


# ── Callbacks ─────────────────────────────────────────────────────────────────

@callback(
    Output("pt-metric-row",        "children"),
    Output("pt-open-grid",         "data"),
    Output("pt-closed-grid",       "data"),
    Output("pt-closed-chart",      "children"),
    Output("pt-txns-grid",         "data"),
    Output("pt-perf-chart",        "children"),
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
    market_value = 0.0   # accumulated per-position below (live mark-to-market)
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

        # Live unrealized P&L for this position — required for the P&L-based
        # alerts (take-profit / stop-loss). Without it only DTE alerts fire.
        try:
            mv_grp, _, _, _ = live_market_value({tgid: grp})
        except Exception:
            mv_grp = 0.0
        market_value += mv_grp
        upnl = ne + mv_grp

        # Alerts — collapse to a single status dot (red > amber > green) so every
        # row shows a health indicator instead of a blank.
        try:
            from engine.positions import compute_position_alerts
            alerts_list = compute_position_alerts(grp, strategy, upnl, ne)
        except Exception:
            alerts_list = []
        levels = {a.get("level", "") for a in alerts_list}
        alert_str = "🔴" if "error" in levels else ("🟡" if "warning" in levels else "🟢")

        # P&L % is return on capital at risk (max loss), not on the premium
        # collected — otherwise every fully-won credit spread reads +100%.
        # Falls back to cost basis for unbounded-risk / non-defined positions.
        risk = position_risk(grp)
        pnl_basis = risk if (risk and risk > 0) else (abs(ne) if ne else None)
        pnl_pct = (upnl / pnl_basis * 100) if pnl_basis else None
        open_data.append({
            "Trade Group": str(tgid),
            "Underlying":  str(underlying),
            "Strategy":    strategy,
            "Open Date":   str(grp["BusinessDate"].min())[:10],
            "Legs":        len(grp),
            "DTE":         dte,
            "Net Entry":   f"+${ne:,.2f}" if ne >= 0 else f"-${abs(ne):,.2f}",
            "P&L":         f"{'+' if upnl >= 0 else '-'}${abs(upnl):,.2f}",
            "P&L %":       f"{pnl_pct:+.1f}%" if pnl_pct is not None else "—",
            "Alerts":      alert_str,
            "_net":        ne,
            "_pnl":        upnl,
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

    # market_value was accumulated per-position above (live mark-to-market;
    # negative for net short premium). Account value nets it against cash.
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

    def _metric(label, value, color=T.TEXT_PRIMARY, sub=None, big=False):
        children = [
            html.Div(label, style={
                "color": T.TEXT_MUTED, "fontSize": "10px", "fontWeight": "600",
                "textTransform": "uppercase", "letterSpacing": "0.07em",
                "marginBottom": "5px",
            }),
            html.Div(value, style={"color": color,
                                   "fontSize": "1.7rem" if big else "1.1rem",
                                   "fontWeight": "700", "lineHeight": "1.15"}),
        ]
        if sub:
            children.append(html.Div(sub, style={
                "color": T.TEXT_MUTED, "fontSize": "11px", "marginTop": "4px"}))
        return html.Div(children, style={
            **T.STYLE_CARD, "minWidth": "150px", "flex": "1", "padding": "12px 14px"})

    # Total P&L = realized (closed) + unrealized (open). Total return vs starting capital.
    total_pnl = unrealized_pnl + total_closed
    win_rate_str = f"{win_rate:.0f}%" if win_rate is not None else "—"
    win_rate_color = (T.SUCCESS if win_rate and win_rate >= 50 else T.DANGER) if win_rate is not None else T.TEXT_MUTED

    def _c(v):  # value-based colour
        return T.SUCCESS if v > 0 else (T.DANGER if v < 0 else T.TEXT_MUTED)
    def _sd(v):  # signed dollar
        return f"{'+' if v >= 0 else '-'}${abs(v):,.2f}"

    # Row 1 — portfolio: Account Value = Cash + Positions, plus headline P&L.
    row1 = html.Div([
        _metric("Account Value", f"${account_value:,.2f}", T.TEXT_PRIMARY,
                sub=f"Cash ${cash_bal:,.0f}  +  Positions {_sd(market_value)}", big=True),
        _metric("Cash", f"${cash_bal:,.2f}",
                T.SUCCESS if cash_bal >= 0 else T.DANGER,
                sub="available to deploy"),
        _metric("Positions", _sd(market_value), _c(market_value),
                sub=f"{n_open} open · live mark"),
        _metric("Total P&L", _sd(total_pnl), _c(total_pnl),
                sub=f"{'+' if ytd_return >= 0 else ''}{ytd_return:.1f}% vs start", big=True),
    ], style={"display": "flex", "gap": "10px", "flexWrap": "wrap"})

    # Row 2 — P&L breakdown + activity.
    row2 = html.Div([
        _metric("Unrealized P&L", _sd(unrealized_pnl), _c(unrealized_pnl), sub="open positions"),
        _metric("Realized P&L",   _sd(total_closed),   _c(total_closed),   sub="closed trades"),
        _metric("Today's P&L",    _sd(today_pnl),      _c(today_pnl),      sub="realized today"),
        _metric("Open Positions", str(n_open)),
        _metric("Win Rate",       win_rate_str, win_rate_color,
                sub=f"{n_wins}/{n_closed} closed" if n_closed else "no closed trades"),
    ], style={"display": "flex", "gap": "10px", "flexWrap": "wrap"})

    # Row 3 — portfolio dollar Greeks (open positions only), always visible.
    greeks_row = html.Div()
    try:
        if open_groups:
            open_txns = pd.concat(open_groups.values(), ignore_index=True)
            gmx = _compute_risk_matrix(open_txns)
            if gmx and gmx.get("ref_spots"):
                greeks_row = _greeks_summary_row(gmx)
    except Exception:
        greeks_row = html.Div()

    metrics = html.Div([row1, row2, greeks_row],
                       style={"display": "flex", "flexDirection": "column", "gap": "10px"})

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
            dcc.Graph(figure=fig_bar, config=_GRAPH_CFG),
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
    # NOTE: the equity curve has its own callback (render_equity_curve) so it can
    # be range-driven and only recompute on the Performance tab — it pulls daily
    # historical prices and shouldn't run on the 60s background refresh.

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

    return (metrics, open_data, closed_data, closed_chart, txns_data, perf_chart,
            type_opts, dir_opts, strat_opts, date_opts, today_caption, total_caption)


# ── Equity curve — range-driven, computed only on the Performance tab ─────────
# (pulls daily historical option/stock prices, so it must NOT run on the 60s
# background refresh; tab + range + manual Refresh are the only triggers.)
@callback(
    Output("pt-equity-curve",  "children"),
    Input("pt-perf-range",     "value"),
    Input("pt-tabs",           "active_tab"),
    Input("pt-refresh-btn",    "n_clicks"),
)
def render_equity_curve(range_key, active_tab, _btn):
    if active_tab != "perf":
        return no_update
    _, _, txns_df = _load_data()
    if txns_df.empty:
        return _build_equity_curve(None)
    days = {"1W": 7, "1M": 30, "3M": 90, "6M": 180, "1Y": 365}.get(range_key or "1M")
    if days is None:   # "ALL"
        start = pd.to_datetime(txns_df["BusinessDate"]).min().date()
    else:
        start = datetime.date.today() - datetime.timedelta(days=days)
    df = mtm_equity_series(txns_df, start)
    return _build_equity_curve(df)


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

    # P&L summary header — since open + day-over-day (live marks; DoD vs prior close)
    pnl_block = html.Div()
    try:
        pnl    = position_pnl(grp)
        so, dd = pnl["since_open"], pnl["dod"]
        _risk  = position_risk(grp)
        _basis = _risk if (_risk and _risk > 0) else (abs(ne) if ne else None)
        so_pct = (so / _basis * 100) if _basis else None

        def _pcard(lbl, val, pct=None, sub=None):
            col = T.SUCCESS if val > 0 else (T.DANGER if val < 0 else T.TEXT_MUTED)
            kids = [
                html.Div(lbl, style={"color": T.TEXT_MUTED, "fontSize": "10px",
                                     "fontWeight": "600", "textTransform": "uppercase",
                                     "letterSpacing": "0.06em", "marginBottom": "4px"}),
                html.Div(f"{'+' if val >= 0 else '-'}${abs(val):,.2f}",
                         style={"color": col, "fontSize": "1.3rem", "fontWeight": "700"}),
            ]
            tag = (f"{pct:+.1f}%" if pct is not None else sub) or ""
            if tag:
                kids.append(html.Div(tag, style={"color": col if pct is not None else T.TEXT_MUTED,
                                                 "fontSize": "11px", "marginTop": "2px"}))
            return html.Div(kids, style={**T.STYLE_CARD, "flex": "1", "minWidth": "130px",
                                         "padding": "10px 14px"})

        live_tag = "live marks" if pnl.get("is_live") else "some legs at entry (no live quote)"
        pnl_block = html.Div([
            html.Div([
                _pcard("P&L Since Open", so, so_pct),
                _pcard("Day P&L (DoD)", dd, sub="vs prior close"),
                _pcard("Market Value", pnl["value"], sub=live_tag),
            ], style={"display": "flex", "gap": "10px", "flexWrap": "wrap",
                      "marginBottom": "16px"}),
        ])
    except Exception:
        pnl_block = html.Div()

    # body may be a single component OR a list (e.g. the IC builder returns a
    # list) — wrap it so we never nest a bare list inside the outer children.
    return html.Div([pnl_block, html.Div(body)]), title


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
        col_defs=[
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

    from engine.positions import (insert_closing_transactions, fetch_option_prices,
                                   fetch_stock_price)
    from app import get_polygon_api_key
    _, _, txns_df = _load_data()
    if not txns_df.empty:
        grp = txns_df[txns_df["TradeGroupId"] == tgid].copy()
        if not grp.empty:
            engine  = _get_engine()
            api_key = get_polygon_api_key()
            # Realize the close at LIVE marks (not entry), so realized P&L is real.
            # Options via the chain snapshot; stock/ETF legs via yfinance. Any leg
            # without a live quote falls back to its entry price inside the inserter.
            live: dict = {}
            try:
                live = fetch_option_prices(api_key, grp) if api_key else {}
            except Exception:
                live = {}
            try:
                for _, r in grp.iterrows():
                    st  = str(r.get("SecurityType", "")).lower()
                    sym = str(r.get("Symbol", ""))
                    if st and st not in ("option", "cash") and sym not in live:
                        px = fetch_stock_price(api_key, str(r.get("Underlying") or sym))
                        if px:
                            live[sym] = {"price": float(px)}
            except Exception:
                pass
            insert_closing_transactions(
                engine=engine, account_id=_ACCOUNT_ID,
                open_grp=grp, live_opt=live, fallback_price=0.0,
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


def _greeks_summary_row(mx: dict, _greeks_title: str = "Portfolio Greeks ($)"):
    """Dollar Greeks at the current spot (the no-shock middle column of the
    scenario matrix), shown as headline cards. `_greeks_title` lets callers label
    it for a single position instead of the whole portfolio."""
    shocks = mx.get("shocks") or []
    if not shocks:
        return html.Div()
    atm = len(shocks) // 2

    def _g(k):
        arr = mx.get(k) or []
        return float(arr[atm]) if atm < len(arr) else 0.0

    items = [
        ("$ Delta", _g("delta"), "P&L per +1% move"),
        ("$ Gamma", _g("gamma"), "extra P&L per +1% move"),
        ("$ Vega",  _g("vega"),  "per +1 IV point"),
        ("$ Theta", _g("theta"), "per day"),
        ("$ Vanna", _g("vanna"), "Δvega per +1% move"),
    ]
    cards = []
    for label, val, sub in items:
        col = T.SUCCESS if val > 0 else (T.DANGER if val < 0 else T.TEXT_MUTED)
        cards.append(html.Div([
            html.Div(label, style={"color": T.TEXT_MUTED, "fontSize": "10px",
                                   "fontWeight": "600", "textTransform": "uppercase",
                                   "letterSpacing": "0.06em", "marginBottom": "4px"}),
            html.Div(f"{'+' if val >= 0 else '-'}${abs(val):,.0f}",
                     style={"color": col, "fontSize": "1.25rem", "fontWeight": "700"}),
            html.Div(sub, style={"color": T.TEXT_MUTED, "fontSize": "10px", "marginTop": "2px"}),
        ], style={**T.STYLE_CARD, "flex": "1", "minWidth": "120px", "padding": "10px 12px"}))

    return html.Div([
        html.Div(_greeks_title, style={
            "color": T.TEXT_SEC, "fontSize": "11px", "fontWeight": "600",
            "textTransform": "uppercase", "letterSpacing": "0.07em", "marginBottom": "8px"}),
        html.Div(cards, style={"display": "flex", "gap": "10px", "flexWrap": "wrap"}),
    ], style={"marginBottom": "16px"})


@callback(
    Output("pt-risk-matrix",    "children"),
    Input("pt-risk-calc-btn",   "n_clicks"),
    Input("pt-risk-position",   "data"),
    Input("pt-risk-leg",        "data"),
    State("pt-risk-step",       "value"),
    State("pt-risk-vol-up",     "value"),
    State("pt-risk-vol-down",   "value"),
    State("pt-risk-iv-default", "value"),
    State("pt-risk-rate",       "value"),
    prevent_initial_call=True,
)
def compute_risk(n_clicks, position_filter, leg_filter, step, vol_up, vol_dn, iv_default, rate):
    # Recomputes on Calculate AND whenever the selected position/leg changes, so
    # clicking a pill immediately re-scopes the matrix (not just on Calculate).
    _, _, txns_df = _load_data()
    if txns_df.empty:
        return html.P("No transactions found.", style={"color": T.TEXT_MUTED, "padding": "20px"})

    # Restrict to genuinely OPEN positions. Filtering out just the CLOSE legs would
    # leave a closed group's *opening* legs behind and leak them into the risk —
    # use the open-group set instead (excludes closed groups and cash entirely).
    from engine.positions import get_open_trade_groups
    open_groups = get_open_trade_groups(txns_df)
    if not open_groups:
        return html.P("No open positions.", style={"color": T.TEXT_MUTED, "padding": "20px"})
    txns_df = pd.concat(open_groups.values(), ignore_index=True)

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
    else:
        g = open_groups.get(position_filter)
        if g is not None and not g.empty:
            und = (g["Underlying"].dropna().iloc[0]
                   if "Underlying" in g.columns and not g["Underlying"].dropna().empty
                   else g["Symbol"].iloc[0])
            strat = _pretty_strategy(str(g["StrategyName"].iloc[0]))
            try:
                od = pd.to_datetime(g["BusinessDate"]).min().strftime("%Y-%m-%d")
            except Exception:
                od = ""
            scope = f"{und} · {strat}" + (f"  ·  opened {od}" if od else "")
        else:
            scope = str(position_filter)
        if leg_filter and leg_filter != "__all__":
            scope += f"  ›  {leg_filter}"

    header = html.Div(
        scope,
        style={"color": T.TEXT_SEC, "fontSize": "13px", "fontWeight": "600", "marginBottom": "10px"},
    )
    greeks_title = "Portfolio Greeks ($)" if position_filter == "__all__" else "Position Greeks ($)"
    return dbc.Card(dbc.CardBody([header, _greeks_summary_row(mx, greeks_title),
                                  _render_risk_table(mx)]),
                    style={**T.STYLE_CARD})
