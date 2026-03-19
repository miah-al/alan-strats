"""
Trade Log tab — Real position tracking, P&L, and model signal accountability.
"""
from __future__ import annotations

import datetime
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
from streamlit import column_config as cc


SPREAD_TYPES = [
    "iron_condor", "bull_put", "bear_call",
    "bull_call", "bear_put", "long_straddle", "short_strangle", "call_butterfly",
]
CREDIT_SPREADS = {"iron_condor", "bull_put", "bear_call", "short_strangle"}
SPREAD_LEGS: dict[str, list[dict]] = {
    "iron_condor":    [
        {"label": "Sell Put",  "action": "STO", "type": "P"},
        {"label": "Buy Put",   "action": "BTO", "type": "P"},
        {"label": "Sell Call", "action": "STO", "type": "C"},
        {"label": "Buy Call",  "action": "BTO", "type": "C"},
    ],
    "bull_put":  [
        {"label": "Sell Put", "action": "STO", "type": "P"},
        {"label": "Buy Put",  "action": "BTO", "type": "P"},
    ],
    "bear_call": [
        {"label": "Sell Call", "action": "STO", "type": "C"},
        {"label": "Buy Call",  "action": "BTO", "type": "C"},
    ],
    "bull_call": [
        {"label": "Buy Call",  "action": "BTO", "type": "C"},
        {"label": "Sell Call", "action": "STO", "type": "C"},
    ],
    "bear_put": [
        {"label": "Buy Put",  "action": "BTO", "type": "P"},
        {"label": "Sell Put", "action": "STO", "type": "P"},
    ],
    "long_straddle": [
        {"label": "Buy Call", "action": "BTO", "type": "C"},
        {"label": "Buy Put",  "action": "BTO", "type": "P"},
    ],
    "short_strangle": [
        {"label": "Sell Call", "action": "STO", "type": "C"},
        {"label": "Sell Put",  "action": "STO", "type": "P"},
    ],
    "call_butterfly": [
        {"label": "Buy Low Call",  "action": "BTO", "type": "C"},
        {"label": "Sell Mid Call", "action": "STO", "type": "C"},
        {"label": "Sell Mid Call", "action": "STO", "type": "C"},
        {"label": "Buy High Call", "action": "BTO", "type": "C"},
    ],
}

SYMBOLS = ["HOOD", "SPY", "QQQ", "AAPL", "TSLA", "MARA"]

# ── colour helpers ────────────────────────────────────────────────────────────

def _pnl_color(val):
    if val is None:
        return ""
    return "color: #4caf50" if val >= 0 else "color: #ef5350"


# ── chart builders ────────────────────────────────────────────────────────────

def _chart_equity_curve(history_df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=history_df["BalanceDate"], y=history_df["TotalEquity"],
        mode="lines", name="Total Equity",
        line=dict(color="#5c6bc0", width=2),
        fill="tozeroy", fillcolor="rgba(92,107,192,0.1)",
    ))
    fig.update_layout(
        title="Account Equity", height=300,
        paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
        font=dict(color="#b0b8c8"),
        xaxis=dict(gridcolor="#1e2130"), yaxis=dict(gridcolor="#1e2130"),
        margin=dict(l=0, r=0, t=36, b=0),
    )
    return fig


def _chart_monthly_pnl(monthly_df: pd.DataFrame) -> go.Figure:
    colors = ["#4caf50" if v >= 0 else "#ef5350" for v in monthly_df["MonthlyPnL"]]
    fig = go.Figure()
    fig.add_bar(
        x=monthly_df["YearMonth"], y=monthly_df["MonthlyPnL"],
        marker_color=colors, name="Monthly P&L",
    )
    fig.add_trace(go.Scatter(
        x=monthly_df["YearMonth"], y=monthly_df["CumPnL"],
        mode="lines+markers", name="Cumulative",
        line=dict(color="#ffb300", width=2), yaxis="y2",
    ))
    fig.update_layout(
        title="Monthly P&L", height=320,
        paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
        font=dict(color="#b0b8c8"),
        xaxis=dict(gridcolor="#1e2130"),
        yaxis=dict(gridcolor="#1e2130", title="Month P&L ($)"),
        yaxis2=dict(title="Cumulative ($)", overlaying="y", side="right",
                    gridcolor="rgba(0,0,0,0)"),
        legend=dict(orientation="h", y=1.1),
        margin=dict(l=0, r=0, t=40, b=0),
    )
    return fig


def _chart_strategy_bars(perf_df: pd.DataFrame) -> go.Figure:
    df = perf_df.sort_values("TotalPnL", ascending=True)
    colors = ["#4caf50" if v >= 0 else "#ef5350" for v in df["TotalPnL"]]
    fig = go.Figure(go.Bar(
        x=df["TotalPnL"],
        y=df["Symbol"] + " / " + df["SpreadType"],
        orientation="h",
        marker_color=colors,
        text=[f"W:{int(r['Wins'])}  L:{int(r['Losses'])}  ({r['WinRate']}%)" for _, r in df.iterrows()],
        textposition="auto",
    ))
    fig.update_layout(
        title="P&L by Strategy", height=max(250, len(df) * 50),
        paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
        font=dict(color="#b0b8c8"),
        xaxis=dict(gridcolor="#1e2130", title="Total P&L ($)"),
        margin=dict(l=0, r=0, t=36, b=0),
    )
    return fig


def _chart_pnl_histogram(closed_df: pd.DataFrame) -> go.Figure:
    wins   = closed_df[closed_df["RealizedPnL"] > 0]["RealizedPnL"]
    losses = closed_df[closed_df["RealizedPnL"] <= 0]["RealizedPnL"]
    fig = go.Figure()
    fig.add_trace(go.Histogram(x=wins,   name="Wins",   marker_color="#4caf50", opacity=0.8))
    fig.add_trace(go.Histogram(x=losses, name="Losses", marker_color="#ef5350", opacity=0.8))
    fig.update_layout(
        title="P&L Distribution", barmode="overlay", height=280,
        paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
        font=dict(color="#b0b8c8"),
        xaxis=dict(gridcolor="#1e2130", title="Realized P&L ($)"),
        yaxis=dict(gridcolor="#1e2130"),
        legend=dict(orientation="h", y=1.1),
        margin=dict(l=0, r=0, t=36, b=0),
    )
    return fig


# ── main render ───────────────────────────────────────────────────────────────

def render(api_key: str = ""):
    st.markdown("## Trade Log")

    try:
        from alan_trader.db.client import get_engine
        from alan_trader.db import portfolio_client as pc
        engine = get_engine()
    except Exception as e:
        st.error(f"Database not available: {e}")
        st.info("Run `db/portfolio_schema.sql` to create the portfolio schema.")
        return

    # Schema check
    try:
        accounts = pc.get_accounts(engine)
    except Exception:
        st.error("Portfolio schema not found. Run `db/portfolio_schema.sql` first.")
        with st.expander("Show SQL to run"):
            import pathlib
            schema_path = pathlib.Path(__file__).parents[2] / "db" / "portfolio_schema.sql"
            if schema_path.exists():
                st.code(schema_path.read_text(), language="sql")
        return

    if accounts.empty:
        st.warning("No accounts found. Seeding default paper account...")
        pc.ensure_default_account(engine)
        accounts = pc.get_accounts(engine)

    # ── Account selector ──────────────────────────────────────────────────────
    acct_options = {row["Name"]: row["AccountId"] for _, row in accounts.iterrows()}
    selected_acct_name = st.selectbox("Account", list(acct_options.keys()), key="tl_account")
    account_id = acct_options[selected_acct_name]

    # ── KPI header ────────────────────────────────────────────────────────────
    kpis = pc.get_kpis(engine, account_id)
    k1, k2, k3, k4, k5 = st.columns(5)

    def _fmt_dollar(v):
        return f"${v:,.2f}" if v is not None else "—"
    def _fmt_pct(v):
        return f"{v:.1f}%" if v is not None else "—"
    def _delta_str(v):
        if v is None: return None
        return f"${v:+,.2f}"

    k1.metric("Total Equity",      _fmt_dollar(kpis["total_equity"]))
    k2.metric("Day P&L",           _fmt_dollar(kpis["day_pnl"]),
              delta=_delta_str(kpis["day_pnl"]))
    k3.metric("YTD Realized P&L",  _fmt_dollar(kpis["ytd_pnl"]),
              delta=_delta_str(kpis["ytd_pnl"]))
    k4.metric("Open Positions",    str(kpis["open_positions"]))
    k5.metric("Win Rate (closed)", _fmt_pct(kpis["win_rate"]),
              help=f"{kpis['wins']} wins of {kpis['total_trades']} closed trades")

    st.markdown("---")

    # ── Inner tabs ────────────────────────────────────────────────────────────
    t_open, t_log, t_history, t_perf, t_model = st.tabs([
        "📂 Open Positions", "➕ Log Trade", "📋 History", "📈 Performance", "🤖 Model Accuracy"
    ])

    # ══════════════════════════════════════════════════════════════════════════
    # OPEN POSITIONS
    # ══════════════════════════════════════════════════════════════════════════
    with t_open:
        open_df = pc.get_open_positions(engine, account_id)

        if open_df.empty:
            st.info("No open positions. Use **Log Trade** to record a new position.")
        else:
            # Close position action
            with st.expander("Close a position"):
                close_pid = st.selectbox(
                    "Position to close",
                    open_df["PositionId"].tolist(),
                    format_func=lambda pid: (
                        open_df[open_df["PositionId"] == pid]
                        .iloc[0][["Symbol","SpreadType","OpenDate"]]
                        .to_dict().__repr__()
                    ),
                    key="tl_close_pid"
                )
                col_a, col_b, col_c = st.columns(3)
                close_date  = col_a.date_input("Close date",  value=datetime.date.today(), key="tl_close_date")
                exit_value  = col_b.number_input("Exit value ($/share)", value=0.0, step=0.01, key="tl_exit_val",
                                                  help="Credit remaining (credit spreads) or current spread value (debit)")
                close_pnl   = col_c.number_input("Realized P&L ($)", value=0.0, step=1.0, key="tl_close_pnl")
                close_status = st.selectbox("Status", ["closed","expired","assigned","rolled"], key="tl_close_status")
                if st.button("Close Position", key="tl_do_close", type="primary"):
                    pc.close_position(engine, int(close_pid), close_date, exit_value, close_pnl, close_status)
                    st.success("Position closed.")
                    st.rerun()

            # Format display
            disp = open_df[[
                "Symbol","SpreadType","Contracts","OpenDate","Expiration","DTE",
                "EntryDollars","CurrentValue","UnrealizedPnL","PctOfMaxProfit",
                "VixAtEntry","Source","ModelConfidence","Notes"
            ]].copy()
            disp.columns = [
                "Symbol","Strategy","Qty","Open","Exp","DTE",
                "Entry $","Current","Unrealized P&L","% of Max",
                "VIX@Entry","Source","Model Conf","Notes"
            ]

            st.dataframe(
                disp,
                width="stretch",
                hide_index=True,
                column_config={
                    "Unrealized P&L": cc.NumberColumn(format="$%.2f"),
                    "Entry $":        cc.NumberColumn(format="$%.2f"),
                    "% of Max":       cc.NumberColumn(format="%.1f%%"),
                    "Model Conf":     cc.NumberColumn(format="%.1f%%"),
                    "DTE":            cc.NumberColumn(help="Days to expiration"),
                }
            )

    # ══════════════════════════════════════════════════════════════════════════
    # LOG TRADE
    # ══════════════════════════════════════════════════════════════════════════
    with t_log:
        st.markdown("### Log a new position")
        st.caption("Enter the position details and each leg's fill price.")

        c1, c2, c3, c4 = st.columns(4)
        lg_symbol      = c1.selectbox("Underlying", SYMBOLS, key="lg_sym")
        lg_spread      = c2.selectbox("Spread type", SPREAD_TYPES, key="lg_spread")
        lg_contracts   = c3.number_input("Contracts", min_value=1, value=1, step=1, key="lg_ct")
        lg_open_date   = c4.date_input("Open date", value=datetime.date.today(), key="lg_od")

        c5, c6, c7 = st.columns(3)
        lg_expiration  = c5.date_input("Expiration", key="lg_exp",
                                        value=datetime.date.today() + datetime.timedelta(days=30))
        lg_spot        = c6.number_input("Spot price at entry", value=0.0, step=0.01, key="lg_spot")
        lg_vix         = c7.number_input("VIX at entry", value=0.0, step=0.1, key="lg_vix")

        c8, c9 = st.columns(2)
        lg_max_profit  = c8.number_input("Max profit ($/share)", value=0.0, step=0.01, key="lg_mp",
                                          help="Wing width for credit spreads; 2× premium for straddle")
        lg_max_loss    = c9.number_input("Max loss ($/share)", value=0.0, step=0.01, key="lg_ml")

        lg_source = st.selectbox("Source", ["manual","model","import"], key="lg_src")
        lg_notes  = st.text_area("Notes", key="lg_notes", height=60)

        st.markdown("#### Leg fills")
        leg_template = SPREAD_LEGS.get(lg_spread, [])
        leg_fills: list[dict] = []
        total_credit = 0.0
        for i, tmpl in enumerate(leg_template):
            lc1, lc2, lc3 = st.columns([3, 2, 2])
            action_display = f"{tmpl['action']} {tmpl['label']}"
            strike = lc1.number_input(f"{action_display} — Strike", value=0.0, step=0.50,
                                       key=f"lg_sk_{i}")
            fill   = lc2.number_input(f"Fill price", value=0.0, step=0.01, min_value=0.0,
                                       key=f"lg_fp_{i}")
            comm   = lc3.number_input(f"Commission", value=0.65, step=0.01, min_value=0.0,
                                       key=f"lg_comm_{i}")
            leg_fills.append({
                "action": tmpl["action"], "contract_type": tmpl["type"],
                "strike": strike, "fill_price": fill, "commission": comm,
                "leg_order": i + 1,
            })
            signed = fill if tmpl["action"] == "STO" else -fill
            total_credit += signed

        # Net value summary
        is_credit = lg_spread in CREDIT_SPREADS
        net_label = "Net credit" if is_credit else "Net debit"
        net_value = total_credit if is_credit else -total_credit
        st.markdown(f"**{net_label}: ${net_value:.2f}/share  →  ${net_value * lg_contracts * 100:.2f} total**")

        if st.button("Save Position", key="lg_save", type="primary"):
            if net_value == 0:
                st.error("All fill prices are 0 — enter the actual fills first.")
            else:
                dte = (lg_expiration - lg_open_date).days
                total_comm = sum(l["commission"] * lg_contracts for l in leg_fills)
                pos_id = pc.insert_position(
                    engine=engine, account_id=account_id,
                    symbol=lg_symbol, spread_type=lg_spread,
                    contracts=lg_contracts, open_date=lg_open_date,
                    expiration=lg_expiration, dte_at_entry=dte,
                    entry_value=net_value,
                    max_profit=lg_max_profit, max_loss=lg_max_loss,
                    commission=total_comm,
                    spot=lg_spot if lg_spot else None,
                    vix=lg_vix if lg_vix else None,
                    source=lg_source, notes=lg_notes or None,
                )
                for leg in leg_fills:
                    pc.insert_leg(
                        engine=engine, position_id=pos_id,
                        symbol=lg_symbol, action=leg["action"],
                        contracts=lg_contracts, fill_price=leg["fill_price"],
                        fill_date=lg_open_date, strike=leg["strike"] or None,
                        expiration=lg_expiration,
                        contract_type=leg["contract_type"],
                        commission=leg["commission"] * lg_contracts,
                        leg_order=leg["leg_order"],
                    )
                st.success(f"Position #{pos_id} saved — {lg_contracts}× {lg_spread} on {lg_symbol}.")
                st.rerun()

    # ══════════════════════════════════════════════════════════════════════════
    # HISTORY
    # ══════════════════════════════════════════════════════════════════════════
    with t_history:
        hf1, hf2, hf3, hf4, hf5 = st.columns(5)
        h_sym  = hf1.selectbox("Symbol", ["All"] + SYMBOLS, key="h_sym")
        h_st   = hf2.selectbox("Strategy", ["All"] + SPREAD_TYPES, key="h_st")
        h_from = hf3.date_input("From", value=datetime.date(2020, 1, 1), key="h_from")
        h_to   = hf4.date_input("To",   value=datetime.date.today(), key="h_to")
        h_out  = hf5.selectbox("Outcome", ["All", "Win", "Loss", "Breakeven"], key="h_out")

        closed_df = pc.get_closed_positions(
            engine, account_id=account_id,
            symbol=None if h_sym == "All" else h_sym,
            spread_type=None if h_st == "All" else h_st,
            from_date=h_from, to_date=h_to,
        )

        if h_out != "All" and not closed_df.empty:
            closed_df = closed_df[closed_df["Outcome"] == h_out]

        if closed_df.empty:
            st.info("No closed positions match these filters.")
        else:
            # Summary strip
            n_trades  = len(closed_df)
            n_wins    = (closed_df["RealizedPnL"] > 0).sum()
            win_rate  = n_wins / n_trades * 100
            total_pnl = closed_df["RealizedPnL"].sum()
            avg_pnl   = closed_df["RealizedPnL"].mean()

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Trades",    str(n_trades))
            m2.metric("Win Rate",  f"{win_rate:.1f}%")
            m3.metric("Total P&L", f"${total_pnl:,.2f}")
            m4.metric("Avg P&L",   f"${avg_pnl:,.2f}")

            disp = closed_df[[
                "Symbol","SpreadType","Contracts","OpenDate","CloseDate","HoldDays",
                "EntryDollars","RealizedPnL","PnLPct","MaxProfitDollars",
                "Outcome","VixAtEntry","ModelConfidence","Notes"
            ]].copy()
            disp.columns = [
                "Symbol","Strategy","Qty","Open","Close","Hold Days",
                "Entry $","P&L","% of Max","Max Profit",
                "Result","VIX","Model Conf","Notes"
            ]
            disp["% of Max"] = disp["% of Max"].apply(
                lambda x: round(float(x) * 100, 1) if pd.notna(x) else None
            )

            st.dataframe(
                disp,
                width="stretch",
                hide_index=True,
                column_config={
                    "P&L":         cc.NumberColumn(format="$%.2f"),
                    "Entry $":     cc.NumberColumn(format="$%.2f"),
                    "Max Profit":  cc.NumberColumn(format="$%.2f"),
                    "% of Max":    cc.NumberColumn(format="%.1f%%"),
                    "Model Conf":  cc.NumberColumn(format="%.1f%%"),
                    "Result":      cc.TextColumn(),
                }
            )

    # ══════════════════════════════════════════════════════════════════════════
    # PERFORMANCE
    # ══════════════════════════════════════════════════════════════════════════
    with t_perf:
        monthly_df = pc.get_monthly_pnl(engine)
        perf_df    = pc.get_strategy_performance(engine)
        bal_hist   = pc.get_balance_history(engine, account_id, days=365)
        closed_all = pc.get_closed_positions(engine, account_id=account_id)

        if monthly_df.empty and perf_df.empty:
            st.info("No closed trades yet — P&L charts will appear here once positions are closed.")
        else:
            if not bal_hist.empty:
                st.plotly_chart(_chart_equity_curve(bal_hist), width="stretch")

            ch1, ch2 = st.columns(2)
            if not monthly_df.empty:
                ch1.plotly_chart(_chart_monthly_pnl(monthly_df), width="stretch")
            if not perf_df.empty:
                ch2.plotly_chart(_chart_strategy_bars(perf_df), width="stretch")

            if not closed_all.empty:
                st.plotly_chart(_chart_pnl_histogram(closed_all), width="stretch")

            # Strategy table
            if not perf_df.empty:
                st.markdown("#### Strategy breakdown")
                st.dataframe(
                    perf_df,
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "WinRate":      cc.NumberColumn("Win %",    format="%.1f%%"),
                        "TotalPnL":     cc.NumberColumn("Total P&L",format="$%.2f"),
                        "AvgPnL":       cc.NumberColumn("Avg P&L",  format="$%.2f"),
                        "BestTrade":    cc.NumberColumn("Best",     format="$%.2f"),
                        "WorstTrade":   cc.NumberColumn("Worst",    format="$%.2f"),
                        "AvgHoldDays":  cc.NumberColumn("Avg Hold", format="%.1f d"),
                        "AvgPctOfMax":  cc.NumberColumn("Avg % of Max", format="%.1f%%"),
                    }
                )

        # Update account balance
        with st.expander("Update account balance"):
            ub1, ub2, ub3 = st.columns(3)
            bal_date     = ub1.date_input("Date", value=datetime.date.today(), key="bal_date")
            bal_cash     = ub2.number_input("Cash balance ($)", value=0.0, step=100.0, key="bal_cash")
            bal_port_val = ub3.number_input("Portfolio value ($)", value=0.0, step=100.0, key="bal_pv")
            ub4, ub5 = st.columns(2)
            bal_day_pnl  = ub4.number_input("Day P&L ($)",   value=0.0, step=1.0, key="bal_dpnl")
            bal_ytd      = ub5.number_input("Realized YTD ($)", value=0.0, step=1.0, key="bal_ytd")
            if st.button("Save balance snapshot", key="bal_save"):
                pc.upsert_balance(
                    engine, account_id, bal_date, bal_cash, bal_port_val,
                    day_pnl=bal_day_pnl, realized_ytd=bal_ytd
                )
                st.success("Balance saved.")
                st.rerun()

    # ══════════════════════════════════════════════════════════════════════════
    # MODEL ACCURACY
    # ══════════════════════════════════════════════════════════════════════════
    with t_model:
        st.markdown("### Model signal accountability")
        st.caption(
            "Every ENTER signal the model generated — and whether it would have won if taken. "
            "Use this to decide whether to trust the model's current signals."
        )

        acc_df = pc.get_model_accuracy(engine)

        if acc_df.empty:
            st.info(
                "No model signals logged yet. After training, signals can be linked to real "
                "positions via **Log Trade → Source: model** to track accuracy here."
            )
        else:
            # Headline win rate when model signals are followed
            taken  = acc_df[acc_df["SignalsTaken"] > 0]
            if not taken.empty:
                overall_win = (
                    taken["WinsWhenTaken"].sum() / taken["SignalsTaken"].sum() * 100
                    if taken["SignalsTaken"].sum() > 0 else 0
                )
                total_pnl = taken["TotalPnLWhenTaken"].sum()
                a1, a2, a3 = st.columns(3)
                a1.metric("Win rate (when taken)", f"{overall_win:.1f}%")
                a2.metric("Total P&L (when taken)", f"${total_pnl:,.2f}")
                a3.metric("Signals taken", str(int(taken["SignalsTaken"].sum())))

            st.dataframe(
                acc_df,
                width="stretch",
                hide_index=True,
                column_config={
                    "WinRateWhenTaken":  cc.NumberColumn("Win % (taken)", format="%.1f%%"),
                    "AvgConfidencePct":  cc.NumberColumn("Avg Confidence", format="%.1f%%"),
                    "TotalPnLWhenTaken": cc.NumberColumn("Total P&L",     format="$%.2f"),
                    "AvgPnLWhenTaken":   cc.NumberColumn("Avg P&L",       format="$%.2f"),
                }
            )
