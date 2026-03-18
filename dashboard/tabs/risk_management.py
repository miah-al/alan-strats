"""
Risk Management tab — VaR/CVaR, rolling risk metrics, drawdown analysis.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

from alan_trader.visualization import charts as C
from alan_trader.risk import metrics as rm


def render(portfolio_report: dict, results: list):
    """
    portfolio_report: output of PortfolioManager.build_portfolio_report()
    results: list of BacktestResult
    """
    st.header("Risk Management")

    if not portfolio_report:
        st.warning("No portfolio data. Run backtest with at least one active strategy.")
        return

    pm        = portfolio_report.get("portfolio_metrics", {})
    blended   = portfolio_report.get("blended_equity", pd.Series(dtype=float))
    per_strat = portfolio_report.get("per_strategy", {})

    # Build per-strategy returns dict
    returns_dict = {}
    for res in results:
        rets = res.daily_returns.dropna()
        rets.index = pd.to_datetime(rets.index)
        returns_dict[res.strategy_name] = rets

    if not blended.empty:
        blended_rets = blended.pct_change().dropna()
        returns_dict["portfolio"] = blended_rets

    # ── top risk cards ─────────────────────────────────────────────────────
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("VaR 95% (daily)",   f"{pm.get('var_95_pct', 0):.2f}%")
    m2.metric("CVaR 95% (daily)",  f"{pm.get('cvar_95_pct', 0):.2f}%")
    m3.metric("Max Drawdown",      f"{pm.get('max_drawdown_pct', 0):.1f}%")
    m4.metric("Sharpe",            f"{pm.get('sharpe', 0):.2f}")
    m5.metric("Sortino",           f"{pm.get('sortino', 0):.2f}")
    m6.metric("Beta",              f"{pm.get('beta', 1):.2f}")

    st.markdown("---")

    # ── VaR / CVaR bar chart + return distribution ─────────────────────────
    v1, v2 = st.columns(2)
    with v1:
        if per_strat:
            merged = dict(per_strat)
            if pm:
                merged["portfolio"] = pm
            st.plotly_chart(C.var_cvar_bar(merged), use_container_width=True, key="rm_var_cvar")
    with v2:
        if not blended.empty and len(blended) > 5:
            rets = blended.pct_change().dropna()
            var  = rm.value_at_risk(rets, 0.95)
            cvar = rm.conditional_var(rets, 0.95)
            st.plotly_chart(
                C.return_distribution_with_var(rets, var, cvar, "Portfolio"),
                use_container_width=True,
                key="rm_ret_dist",
            )

    st.markdown("---")

    # ── rolling Sharpe ─────────────────────────────────────────────────────
    st.subheader("Rolling Risk Metrics")
    rc1, rc2, rc3 = st.columns([1, 1, 1])
    metric_choice  = rc1.selectbox("Metric",  ["sharpe", "sortino"], key="rm_metric")
    window_choice  = rc2.selectbox("Window",  [20, 60, 90], index=1, key="rm_window")

    active_returns = {k: v for k, v in returns_dict.items() if len(v) >= window_choice}

    if active_returns:
        st.plotly_chart(
            C.rolling_metric_per_strategy(active_returns, metric_choice, window_choice),
            use_container_width=True,
            key="rm_rolling_metric",
        )
    else:
        st.info("Not enough data for rolling metrics. Reduce window or run with more history.")

    # ── rolling drawdown per strategy ─────────────────────────────────────
    st.subheader("Rolling Max Drawdown")
    def _hex_to_rgba(hex_color: str, alpha: float) -> str:
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"rgba({r},{g},{b},{alpha})"

    fig_dd = go.Figure()
    colors = ["#5c6bc0", "#26a69a", "#ffa726", "#ef5350", "#ab47bc"]
    for i, res in enumerate(results):
        eq = res.equity_curve
        eq.index = pd.to_datetime(eq.index)
        if len(eq) < window_choice:
            continue
        dd_series = rm.rolling_max_drawdown(eq, window_choice) * 100
        fig_dd.add_trace(go.Scatter(
            x=dd_series.index, y=dd_series,
            name=res.strategy_name.replace("_", " ").title(),
            line=dict(color=colors[i % len(colors)], width=1.8),
            fill="tozeroy",
            fillcolor=_hex_to_rgba(colors[i % len(colors)], 0.08),
        ))
    if not blended.empty and len(blended) >= window_choice:
        blended_dd = rm.rolling_max_drawdown(blended.rename("portfolio").pipe(
            lambda s: s.set_axis(pd.to_datetime(s.index))), window_choice) * 100
        fig_dd.add_trace(go.Scatter(
            x=blended_dd.index, y=blended_dd, name="Portfolio (blended)",
            line=dict(color="#ffffff", width=2.5, dash="dash"),
        ))
    fig_dd.update_layout(
        paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
        font=dict(color="#e0e0e0"), height=340, margin=dict(l=50,r=20,t=40,b=40),
        title=f"Rolling {window_choice}-Day Max Drawdown (%)",
        xaxis=dict(gridcolor="#1e2130"),
        yaxis=dict(gridcolor="#1e2130"),
    )
    st.plotly_chart(fig_dd, use_container_width=True, key="rm_rolling_dd")

    st.markdown("---")

    # ── max DD + Calmar comparison ─────────────────────────────────────────
    dd1, dd2 = st.columns(2)
    with dd1:
        if per_strat:
            st.plotly_chart(C.max_drawdown_comparison(per_strat), use_container_width=True, key="rm_max_dd")
    with dd2:
        if per_strat:
            calmar_data = {k: m.get("calmar", 0) for k, m in per_strat.items()}
            names  = [n.replace("_", " ").title() for n in calmar_data.keys()]
            vals   = list(calmar_data.values())
            fig_c = go.Figure(go.Bar(
                x=names, y=vals,
                marker_color=["#26a69a" if v >= 1 else "#ef5350" for v in vals],
                text=[f"{v:.2f}" for v in vals], textposition="outside",
            ))
            fig_c.add_hline(y=1, line=dict(color="#aaa", dash="dash"))
            fig_c.update_layout(
                paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
                font=dict(color="#e0e0e0"), height=320, margin=dict(l=40,r=20,t=40,b=60),
                title="Calmar Ratio by Strategy",
                xaxis=dict(gridcolor="#1e2130"),
                yaxis=dict(gridcolor="#1e2130"),
            )
            st.plotly_chart(fig_c, use_container_width=True, key="rm_calmar")

    st.markdown("---")

    # ── PnL distribution per strategy ─────────────────────────────────────
    st.subheader("P&L Distribution by Strategy")

    if results:
        strat_names = [r.strategy_name for r in results]
        sel = st.selectbox(
            "Filter strategy",
            options=["All"] + strat_names,
            key="rm_pnl_strategy",
        )
        for res in results:
            if sel != "All" and res.strategy_name != sel:
                continue
            trades = res.trades
            if isinstance(trades, list):
                trades = pd.DataFrame([vars(t) for t in trades]) if trades else pd.DataFrame()
            if trades.empty or "pnl" not in trades.columns:
                continue

            st.caption(res.strategy_name.replace("_", " ").title())
            st.plotly_chart(
                C.pnl_histogram(trades),
                use_container_width=True,
                key=f"rm_pnl_hist_{res.strategy_name}",
            )
    else:
        st.info("Run a backtest first to see P&L distributions.")

    st.markdown("---")

    # ── strategy correlation (rolling window) ─────────────────────────────
    st.subheader("Strategy Correlation")
    corr_window = st.selectbox("Correlation window", [30, 60, 90, "Full period"],
                               index=1, key="corr_window")

    strat_returns_only = {k: v for k, v in returns_dict.items() if k != "portfolio"}
    if len(strat_returns_only) >= 2:
        df_r = pd.DataFrame(strat_returns_only).fillna(0)
        if corr_window != "Full period":
            df_r = df_r.tail(int(corr_window))
        corr = df_r.corr()
        st.plotly_chart(C.strategy_correlation_heatmap(corr), use_container_width=True, key="rm_corr_heatmap")
        st.caption("Lower correlation between strategies = better diversification benefit.")
    else:
        st.info("Enable 2+ strategies to see correlation analysis.")

    # ── risk reference guide ──────────────────────────────────────────────
    st.markdown("---")
    with st.expander("Risk Parameter Reference Guide"):
        st.markdown("""
| Metric | Definition | Good range |
|---|---|---|
| **Sharpe Ratio** | (Return - RF) / StdDev × √252 | > 1.0 |
| **Sortino Ratio** | (Return - RF) / Downside StdDev × √252 | > 1.5 |
| **Calmar Ratio** | Annual Return / |Max Drawdown| | > 1.0 |
| **VaR 95%** | Worst daily loss 95% of the time | < −2% concerning |
| **CVaR 95%** | Mean loss in worst 5% of days | < −3% concerning |
| **Beta** | Sensitivity to SPY moves | 0 = market-neutral; 1 = full market |
| **Max Drawdown** | Peak-to-trough equity decline | < −20% concerning |

**Kelly Fraction** recommendation: use 0.10–0.25 of "full Kelly" to avoid over-leveraging.
A 25% Kelly fraction limits position to 25% of what pure Kelly math suggests.

**VaR caveat:** Historical VaR assumes tomorrow looks like history.
Tail events (Black Swans) are systematically underestimated.
        """)
