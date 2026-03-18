"""
Portfolio Overview tab.

Section order:
  1. Summary  — date slider, equity/cash metrics, open positions
  2. Transactions — full OPEN/CLOSE audit trail
  3. Portfolio KPIs & charts
  4. Combined trade log
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from alan_trader.visualization import charts as C


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _positions_table(positions: list[dict], is_demo: bool = False):
    if not positions:
        st.info("No open positions on this date — portfolio was in cash.")
        return

    label = "Open Positions"
    if is_demo:
        label += " *(simulated demo data — run a backtest to see real positions)*"
    st.markdown(f"**{label}** &nbsp; `{len(positions)} spread{'s' if len(positions) != 1 else ''}`")

    pos_df = pd.DataFrame(positions)
    show = [c for c in [
        "strategy", "spread_type", "long_strike", "short_strike",
        "expiration", "entry_date", "entry_cost", "contracts",
    ] if c in pos_df.columns]
    pos_df = pos_df[show].rename(columns={
        "strategy":    "Strategy",
        "spread_type": "Spread",
        "long_strike": "Long K",
        "short_strike":"Short K",
        "expiration":  "Expiry",
        "entry_date":  "Opened",
        "entry_cost":  "Entry Cost",
        "contracts":   "Contracts",
    })
    st.dataframe(pos_df, use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────────────────────────────────────
# Main render
# ─────────────────────────────────────────────────────────────────────────────

def render(portfolio_report: dict, results: list, store=None):
    """
    portfolio_report : output of PortfolioManager.build_portfolio_report()
    results          : list of BacktestResult
    store            : optional PortfolioStore (enables time-travel & transactions)
    """
    from alan_trader.portfolio.store import PortfolioStore

    st.header("Portfolio Overview")

    pm        = portfolio_report.get("portfolio_metrics", {}) if portfolio_report else {}
    weights   = portfolio_report.get("weights", {})           if portfolio_report else {}
    corr      = portfolio_report.get("correlation", pd.DataFrame()) if portfolio_report else pd.DataFrame()
    blended   = portfolio_report.get("blended_equity", pd.Series(dtype=float)) if portfolio_report else pd.Series(dtype=float)
    per_strat = portfolio_report.get("per_strategy", {})      if portfolio_report else {}

    # ══════════════════════════════════════════════════════════════════════
    # 1. SUMMARY
    # ══════════════════════════════════════════════════════════════════════
    st.subheader("Summary")

    has_store = store and not store.is_empty()

    if has_store:
        all_dates     = store.get_all_dates()
        selected_date = st.select_slider(
            "Select date",
            options=all_dates,
            value=all_dates[-1],
            key="portfolio_time_travel_slider",
        )
        snap      = store.get_snapshot(selected_date)
        positions = store.get_positions_at(selected_date)
        is_demo   = False
    else:
        selected_date = None
        snap          = None
        positions     = PortfolioStore.get_demo_positions()
        is_demo       = True

    # Metric row
    if snap:
        tc1, tc2, tc3, tc4, tc5 = st.columns(5)
        tc1.metric("Equity",          f"${snap['equity']:,.2f}")
        tc2.metric("Cash",            f"${snap.get('cash', 0):,.2f}")
        tc3.metric("Positions Value", f"${snap.get('positions_value', 0):,.2f}")
        tc4.metric("Daily P&L",       f"${snap['daily_pnl']:+,.2f}",
                   delta=f"${snap['daily_pnl']:+,.2f}")
        tc5.metric("Open Positions",  len(snap["open_position_ids"]))
    elif pm:
        tc1, tc2, tc3, tc4 = st.columns(4)
        tc1.metric("Total Return",   f"{pm.get('total_return_pct', 0):+.1f}%")
        tc2.metric("Sharpe",         f"{pm.get('sharpe', 0):.2f}")
        tc3.metric("Max Drawdown",   f"{pm.get('max_drawdown_pct', 0):.1f}%")
        tc4.metric("Beta vs Market", f"{pm.get('beta', 1):.2f}")

    # Strategy weights badge row
    if snap and snap.get("strategy_weights"):
        wt_html = " &nbsp;|&nbsp; ".join(
            f'<span style="color:#26a69a">{k.replace("_", " ").title()}</span>'
            f' <b>{v:.1%}</b>'
            for k, v in snap["strategy_weights"].items()
        )
        st.markdown(
            f'<div style="background:#161b27;padding:8px 16px;border-radius:8px;'
            f'font-size:13px;color:#b0b8c8;margin:6px 0">'
            f'<b>Strategy weights on {selected_date}:</b> &nbsp; {wt_html}</div>',
            unsafe_allow_html=True,
        )
    elif weights:
        wt_html = " &nbsp;|&nbsp; ".join(
            f'<span style="color:#26a69a">{k.replace("_", " ").title()}</span>'
            f' <b>{v:.1%}</b>'
            for k, v in weights.items()
        )
        st.markdown(
            f'<div style="background:#161b27;padding:8px 16px;border-radius:8px;'
            f'font-size:13px;color:#b0b8c8;margin:6px 0">'
            f'<b>Strategy weights:</b> &nbsp; {wt_html}</div>',
            unsafe_allow_html=True,
        )

    st.markdown("")
    _positions_table(positions, is_demo=is_demo)

    # ══════════════════════════════════════════════════════════════════════
    # 2. TRANSACTIONS
    # ══════════════════════════════════════════════════════════════════════
    if has_store:
        st.markdown("---")
        st.subheader("Transactions")

        all_strategies = store.all_strategies()
        tf1, tf2 = st.columns(2)
        with tf1:
            tx_type_filter = st.multiselect(
                "Type", ["OPEN", "CLOSE"],
                default=["OPEN", "CLOSE"],
                key="portfolio_tx_type_filter",
            )
        with tf2:
            strat_filter = st.multiselect(
                "Strategy", all_strategies,
                default=all_strategies,
                key="portfolio_tx_strat_filter",
            )

        txns = store.get_transactions(
            strategies=strat_filter or None,
            tx_types=tx_type_filter or None,
        )
        if txns:
            txns_df = pd.DataFrame(txns)
            show_cols = [c for c in [
                "date", "tx_type", "strategy", "spread_type",
                "long_strike", "short_strike", "expiration",
                "contracts", "price", "realized_pnl", "exit_reason",
            ] if c in txns_df.columns]
            txns_df = txns_df[show_cols].rename(columns={
                "date":         "Date",
                "tx_type":      "Type",
                "strategy":     "Strategy",
                "spread_type":  "Spread",
                "long_strike":  "Long K",
                "short_strike": "Short K",
                "expiration":   "Expiry",
                "contracts":    "Contracts",
                "price":        "Price",
                "realized_pnl": "Realized P&L",
                "exit_reason":  "Exit Reason",
            })

            def _tx_row_style(row):
                if row.get("Type") == "OPEN":
                    return ["background-color:#0e1825"] * len(row)
                pnl = row.get("Realized P&L", 0)
                if isinstance(pnl, (int, float)) and pnl > 0:
                    return ["background-color:#0d1f18"] * len(row)
                if isinstance(pnl, (int, float)) and pnl < 0:
                    return ["background-color:#1f0d0d"] * len(row)
                return [""] * len(row)

            st.dataframe(
                txns_df.style
                    .apply(_tx_row_style, axis=1)
                    .map(
                        lambda v: (
                            "color:#26a69a;font-weight:600"
                            if isinstance(v, (int, float)) and v > 0
                            else "color:#ef5350;font-weight:600"
                            if isinstance(v, (int, float)) and v < 0
                            else ""
                        ),
                        subset=["Realized P&L"] if "Realized P&L" in txns_df.columns else [],
                    ),
                use_container_width=True,
                height=380,
                hide_index=True,
            )
            st.caption(
                f"{len(txns_df)} transaction{'s' if len(txns_df) != 1 else ''} shown"
            )
        else:
            st.info("No transactions match the current filters.")

    if not portfolio_report:
        return

    # ══════════════════════════════════════════════════════════════════════
    # 3. PORTFOLIO KPIs
    # ══════════════════════════════════════════════════════════════════════
    st.markdown("---")
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Total Return",  f"{pm.get('total_return_pct', 0):+.1f}%",
              delta=f"{pm.get('total_return_pct', 0):+.1f}%")
    m2.metric("Sharpe",        f"{pm.get('sharpe', 0):.2f}")
    m3.metric("Sortino",       f"{pm.get('sortino', 0):.2f}")
    m4.metric("Max Drawdown",  f"{pm.get('max_drawdown_pct', 0):.1f}%")
    m5.metric("Calmar",        f"{pm.get('calmar', 0):.2f}")
    m6.metric("Beta vs Market",f"{pm.get('beta', 1):.2f}")

    st.markdown("---")

    # ── blended equity curve ───────────────────────────────────────────────
    if not blended.empty:
        st.subheader("Blended Portfolio Equity")
        curves = {r.strategy_name: r.equity_curve for r in results}
        curves["PORTFOLIO (blended)"] = blended
        st.plotly_chart(
            C.strategy_returns_comparison(curves),
            use_container_width=True,
            key="portfolio_blended_equity",
        )

    # ── drawdown ───────────────────────────────────────────────────────────
    if not blended.empty and len(blended) > 5:
        st.subheader("Portfolio Drawdown")
        st.plotly_chart(
            C.drawdown_chart(pd.DataFrame({"equity": blended, "price": blended})),
            use_container_width=True,
            key="portfolio_drawdown",
        )

    st.markdown("---")

    # ── weights + correlation ──────────────────────────────────────────────
    col_w, col_c = st.columns(2)
    with col_w:
        if weights:
            st.plotly_chart(C.kelly_weights_bar(weights), use_container_width=True,
                            key="portfolio_kelly_weights")
    with col_c:
        if not corr.empty:
            st.plotly_chart(C.strategy_correlation_heatmap(corr),
                            use_container_width=True,
                            key="portfolio_correlation_heatmap")

    st.markdown("---")

    # ── per-strategy metrics ───────────────────────────────────────────────
    if per_strat:
        st.subheader("Strategy Metrics Comparison")
        st.plotly_chart(C.strategy_metrics_table(per_strat),
                        use_container_width=True,
                        key="portfolio_metrics_table")

    # ── win rate + max drawdown ────────────────────────────────────────────
    if per_strat:
        rc1, rc2 = st.columns(2)
        with rc1:
            wr_data = {k: m.get("win_rate_pct", 0) for k, m in per_strat.items()}
            names   = [n.replace("_", " ").title() for n in wr_data.keys()]
            values  = list(wr_data.values())
            fig_wr  = go.Figure(go.Bar(
                x=names, y=values,
                marker_color=["#26a69a" if v >= 50 else "#ef5350" for v in values],
                text=[f"{v:.1f}%" for v in values], textposition="outside",
            ))
            fig_wr.add_hline(y=50, line=dict(color="#aaa", dash="dash"))
            fig_wr.update_layout(
                paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
                font=dict(color="#e0e0e0"), height=320,
                margin=dict(l=40, r=20, t=40, b=60),
                title="Win Rate by Strategy (%)",
                xaxis=dict(gridcolor="#1e2130"),
                yaxis=dict(gridcolor="#1e2130", range=[0, 110]),
            )
            st.plotly_chart(fig_wr, use_container_width=True, key="portfolio_win_rate")
        with rc2:
            st.plotly_chart(C.max_drawdown_comparison(per_strat),
                            use_container_width=True,
                            key="portfolio_max_drawdown")

    # ── monthly returns ────────────────────────────────────────────────────
    if not blended.empty and len(blended) > 30:
        st.markdown("---")
        st.subheader("Monthly Returns — Blended Portfolio")
        blended_df2 = pd.DataFrame(
            {"equity": blended.values},
            index=pd.to_datetime(blended.index),
        )
        try:
            st.plotly_chart(C.monthly_returns_heatmap(blended_df2),
                            use_container_width=True,
                            key="portfolio_monthly_returns")
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════════════════
    # 4. COMBINED TRADE LOG
    # ══════════════════════════════════════════════════════════════════════
    all_trades = []
    for res in results:
        if not res.trades.empty:
            df = res.trades.copy()
            df["strategy"] = res.strategy_name
            all_trades.append(df)

    if all_trades:
        st.markdown("---")
        st.subheader("Combined Trade Log")
        combined = pd.concat(all_trades, ignore_index=True)
        show = [c for c in ["entry_date", "exit_date", "strategy", "spread_type",
                             "pnl", "exit_reason", "contracts"] if c in combined.columns]
        combined_sorted = (
            combined[show].sort_values("entry_date", ascending=False)
            if "entry_date" in show else combined[show]
        )
        st.dataframe(
            combined_sorted.style.applymap(
                lambda v: "color: #26a69a" if isinstance(v, (int, float)) and v > 0
                          else ("color: #ef5350" if isinstance(v, (int, float)) and v < 0 else ""),
                subset=["pnl"] if "pnl" in show else [],
            ),
            use_container_width=True,
            height=340,
        )
