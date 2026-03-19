"""
Strategy Selector tab — browse all 30 strategies, view params, compare active ones.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from alan_trader.strategies.registry import STRATEGY_METADATA, registry_dataframe


def _status_badge(status: str) -> str:
    colors = {"Active": "#26a69a", "Stub": "#78909c", "Disabled": "#ef5350"}
    c = colors.get(status, "#78909c")
    return f'<span style="background:{c};color:#fff;padding:2px 8px;border-radius:10px;font-size:11px">{status}</span>'


def _type_badge(t: str) -> str:
    colors = {"AI": "#ab47bc", "RULE": "#5c6bc0", "HYBRID": "#ffa726"}
    c = colors.get(t.upper(), "#78909c")
    return f'<span style="background:{c};color:#fff;padding:2px 8px;border-radius:10px;font-size:11px">{t.upper()}</span>'


def render(backtest_results: dict = None, selected_slugs: list = None):
    """
    backtest_results: {slug: BacktestResult} for active strategies
    selected_slugs:   list of slugs currently selected by sidebar
    """
    st.header("Strategy Registry")

    meta_df = registry_dataframe()

    # ── top-level counters ─────────────────────────────────────────────────
    total    = len(STRATEGY_METADATA)
    active   = sum(1 for m in STRATEGY_METADATA.values() if m["status"] == "active")
    stub     = sum(1 for m in STRATEGY_METADATA.values() if m["status"] == "stub")
    ai       = sum(1 for m in STRATEGY_METADATA.values() if m["type"] == "ai")
    rule     = sum(1 for m in STRATEGY_METADATA.values() if m["type"] == "rule")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Strategies",    total)
    c2.metric("Implemented",         active, delta=f"{active}/{total}")
    c3.metric("Stubs (Roadmap)",     stub)
    c4.metric("AI-Driven",           ai)
    c5.metric("Rule-Based",          rule)

    st.markdown("---")

    # ── strategy grid ──────────────────────────────────────────────────────
    st.subheader("All 30 Strategies")

    display_df = meta_df[["Name", "Type", "Status", "Asset Class",
                           "Typical Hold (days)", "Target Sharpe"]].copy()

    # Inject Sharpe from backtest results if available
    if backtest_results:
        display_df["Live Sharpe"] = display_df.index.map(
            lambda s: f"{backtest_results[s].metrics.get('sharpe', '—'):.2f}"
                      if s in backtest_results and backtest_results[s].metrics else "—"
        )

    # Style the dataframe
    def _row_style(row):
        if row["Status"] == "Active":
            return ["background-color: #0d1f18"] * len(row)
        return ["background-color: #0e1117"] * len(row)

    st.dataframe(
        display_df.style.apply(_row_style, axis=1),
        width="stretch",
        height=700,
    )

    st.markdown("---")

    # ── detail view for selected strategy ─────────────────────────────────
    st.subheader("Strategy Detail")
    slug_options = list(STRATEGY_METADATA.keys())
    selected = st.selectbox(
        "Select a strategy to inspect",
        options=slug_options,
        format_func=lambda s: STRATEGY_METADATA[s]["display_name"],
        key="strategy_detail_select",
    )

    meta = STRATEGY_METADATA[selected]
    d1, d2 = st.columns([1.5, 1])

    with d1:
        st.markdown(f"""
        <div style="background:#161b27;padding:20px;border-radius:10px">
          <h3 style="color:#e0e0e0;margin:0">{meta["display_name"]}</h3>
          <div style="margin:8px 0">
            {_type_badge(meta["type"])} &nbsp; {_status_badge(meta["status"].capitalize())}
          </div>
          <p style="color:#b0b8c8;margin:12px 0 6px">{meta["description"]}</p>
          <table style="width:100%;color:#b0b8c8;font-size:12px">
            <tr><td><b>Asset Class</b></td><td>{meta.get("asset_class","")}</td></tr>
            <tr><td><b>Typical Hold</b></td><td>{meta.get("typical_holding_days","")} days</td></tr>
            <tr><td><b>Target Sharpe</b></td><td>{meta.get("target_sharpe","")}</td></tr>
            <tr><td><b>Class path</b></td><td style="font-size:10px;font-family:monospace">{meta.get("class_path","(stub)")}</td></tr>
          </table>
        </div>
        """, unsafe_allow_html=True)

    with d2:
        if meta["status"] == "active" and backtest_results and selected in backtest_results:
            res = backtest_results[selected]
            m   = res.metrics
            st.markdown("**Backtest Metrics**")
            pairs = [
                ("Total Return",  f"{m.get('total_return_pct', 0):.1f}%"),
                ("Sharpe",        f"{m.get('sharpe', 0):.2f}"),
                ("Sortino",       f"{m.get('sortino', 0):.2f}"),
                ("Calmar",        f"{m.get('calmar', 0):.2f}"),
                ("Max Drawdown",  f"{m.get('max_drawdown_pct', 0):.1f}%"),
                ("Win Rate",      f"{m.get('win_rate_pct', 0):.1f}%"),
                ("Profit Factor", f"{m.get('profit_factor', 0):.2f}"),
                ("VaR 95%",       f"{m.get('var_95_pct', 0):.2f}%"),
            ]
            for label, val in pairs:
                st.markdown(
                    f'<div style="display:flex;justify-content:space-between;'
                    f'padding:4px 0;border-bottom:1px solid #1e2130">'
                    f'<span style="color:#b0b8c8">{label}</span>'
                    f'<span style="color:#e0e0e0;font-weight:600">{val}</span></div>',
                    unsafe_allow_html=True,
                )
        elif meta["status"] == "active":
            st.info("Run backtest to see live metrics.")
        else:
            st.markdown("""
            <div style="background:#1e2130;padding:20px;border-radius:10px;text-align:center">
              <div style="font-size:2rem">🚧</div>
              <div style="color:#78909c;margin-top:8px">Not yet implemented</div>
              <div style="color:#546e7a;font-size:12px;margin-top:6px">
                This strategy is on the roadmap.
              </div>
            </div>
            """, unsafe_allow_html=True)

    # ── params table for active strategy ──────────────────────────────────
    if meta["status"] == "active":
        st.markdown("---")
        st.subheader(f"Parameters — {meta['display_name']}")
        try:
            from alan_trader.strategies.registry import get_strategy
            strat = get_strategy(selected)
            params = strat.get_params()
            if params:
                param_df = pd.DataFrame(
                    [{"Parameter": k, "Value": str(v)} for k, v in params.items()]
                )
                st.dataframe(param_df, width="stretch", hide_index=True)
        except Exception as e:
            st.warning(f"Could not load params: {e}")

    # ── spread-strategy deep-dive (only when that strategy is selected) ───
    if (
        selected == "options_spread"
        and backtest_results
        and selected in backtest_results
    ):
        res   = backtest_results[selected]
        extra = res.extra if hasattr(res, "extra") else {}

        # ---- Feature Inputs Table ----------------------------------------
        st.markdown("---")
        st.subheader("Feature Inputs (last 60 bars)")
        feat_df_tail = extra.get("feature_df_tail")
        feat_cols    = extra.get("feature_cols", [])
        if feat_df_tail is not None and feat_cols:
            display_feats = [c for c in feat_cols if c in feat_df_tail.columns]
            tail = feat_df_tail[display_feats].tail(60)
            # Round for readability
            tail = tail.round(5)
            st.dataframe(tail, width="stretch", height=300)

            # Feature statistics summary
            with st.expander("Feature statistics", expanded=False):
                stats = tail.describe().T.round(4)
                st.dataframe(stats, width="stretch")
        else:
            st.info("Run a backtest to populate the feature table.")

        # ---- Neural Network Architecture ---------------------------------
        st.markdown("---")
        st.subheader("Neural Network Architecture")
        model_summary = extra.get("model_summary")
        if model_summary:
            layers_df = pd.DataFrame(model_summary["layers"])
            total_p   = model_summary.get("total_params", 0)
            trainable = model_summary.get("trainable_params", 0)

            c1, c2, c3 = st.columns(3)
            c1.metric("Total Parameters",     f"{total_p:,}")
            c2.metric("Trainable Parameters", f"{trainable:,}")
            c3.metric("Architecture",          "LSTM + Attention")

            st.dataframe(layers_df, width="stretch", hide_index=True)

            st.markdown("""
            <div style="background:#161b27;padding:14px;border-radius:8px;font-size:12px;color:#b0b8c8">
              <b>Data flow:</b>
              Input (batch × 30 × 32) →
              LSTM (2-layer, 128 hidden) →
              Attention → context (128) →
              LayerNorm + Dropout →
              <span style="color:#26a69a">Direction Head → 3 classes (Bear / Neutral / Bull)</span>
              &nbsp;|&nbsp;
              <span style="color:#ffa726">Price Head → 1 value (spread entry cost $)</span>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info("Run a backtest to see the network architecture.")

        # ---- Predicted vs Actual Spread Price ----------------------------
        st.markdown("---")
        st.subheader("Spread Price Prediction vs Actual")
        preds   = extra.get("spread_price_predictions")
        actuals = extra.get("spread_price_actuals")
        dates   = extra.get("test_dates")

        if preds is not None and actuals is not None and len(preds) > 0 and len(actuals) > 0:
            n = min(len(preds), len(actuals))
            preds   = np.array(preds[:n])
            actuals = np.array(actuals[:n])
            x_axis  = dates[:n] if dates is not None else np.arange(n)

            errors  = preds - actuals
            mae     = float(np.mean(np.abs(errors)))
            rmse    = float(np.sqrt(np.mean(errors ** 2)))
            ss_res  = float(np.sum((actuals - preds) ** 2))
            ss_tot  = float(np.sum((actuals - np.mean(actuals)) ** 2))
            r2      = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("MAE",  f"${mae:.4f}")
            m2.metric("RMSE", f"${rmse:.4f}")
            m3.metric("R²",   f"{r2:.4f}")
            m4.metric("Samples", str(n))

            # Time series: predicted vs actual
            fig_ts = go.Figure()
            fig_ts.add_trace(go.Scatter(
                x=x_axis, y=actuals,
                name="Actual spread price",
                line=dict(color="#26a69a", width=1.5),
            ))
            fig_ts.add_trace(go.Scatter(
                x=x_axis, y=preds,
                name="Predicted spread price",
                line=dict(color="#ffa726", width=1.5, dash="dot"),
            ))
            fig_ts.update_layout(
                title="ATM Bull-Call Spread Entry Cost: Predicted vs Actual",
                xaxis_title="Date",
                yaxis_title="Spread Price ($)",
                height=380,
                legend=dict(orientation="h", y=1.05),
                paper_bgcolor="#0c1020",
                plot_bgcolor="#0c1020",
                font=dict(color="#e0e0e0"),
            )
            st.plotly_chart(fig_ts, width="stretch", key="spread_pred_vs_actual_ts")

            # Error analysis: scatter + residual histogram side by side
            st.subheader("Prediction Error Analysis")
            fig_err = make_subplots(
                rows=1, cols=2,
                subplot_titles=("Predicted vs Actual (scatter)", "Residual Distribution"),
            )

            # Scatter: predicted vs actual with y=x diagonal
            mn, mx = float(min(actuals.min(), preds.min())), float(max(actuals.max(), preds.max()))
            fig_err.add_trace(
                go.Scatter(
                    x=actuals, y=preds,
                    mode="markers",
                    marker=dict(color="#ab47bc", opacity=0.6, size=5),
                    name="Pred vs Actual",
                ),
                row=1, col=1,
            )
            fig_err.add_trace(
                go.Scatter(
                    x=[mn, mx], y=[mn, mx],
                    mode="lines",
                    line=dict(color="#78909c", dash="dash", width=1),
                    name="Perfect fit",
                    showlegend=False,
                ),
                row=1, col=1,
            )
            fig_err.update_xaxes(title_text="Actual ($)", row=1, col=1)
            fig_err.update_yaxes(title_text="Predicted ($)", row=1, col=1)

            # Residual histogram
            fig_err.add_trace(
                go.Histogram(
                    x=errors,
                    nbinsx=40,
                    marker_color="#5c6bc0",
                    opacity=0.8,
                    name="Residuals",
                ),
                row=1, col=2,
            )
            fig_err.update_xaxes(title_text="Error (Predicted − Actual, $)", row=1, col=2)
            fig_err.update_yaxes(title_text="Count", row=1, col=2)

            fig_err.update_layout(
                height=380,
                showlegend=False,
                paper_bgcolor="#0c1020",
                plot_bgcolor="#0c1020",
                font=dict(color="#e0e0e0"),
            )
            st.plotly_chart(fig_err, width="stretch", key="spread_error_analysis")

            # Residuals over time
            fig_res = go.Figure()
            fig_res.add_trace(go.Scatter(
                x=x_axis, y=errors,
                mode="lines",
                line=dict(color="#ef5350", width=1),
                name="Residual",
            ))
            fig_res.add_hline(y=0, line_dash="dot", line_color="#78909c")
            fig_res.update_layout(
                title="Residuals Over Time (Predicted − Actual)",
                xaxis_title="Date",
                yaxis_title="Error ($)",
                height=280,
                paper_bgcolor="#0c1020",
                plot_bgcolor="#0c1020",
                font=dict(color="#e0e0e0"),
            )
            st.plotly_chart(fig_res, width="stretch", key="spread_residuals_ts")
        else:
            st.info("Run a backtest to see spread price predictions.")

    # ── mini equity comparison for active strategies ──────────────────────
    if backtest_results and len(backtest_results) >= 2:
        st.markdown("---")
        st.subheader("Active Strategy Comparison")
        from alan_trader.visualization.charts import strategy_returns_comparison
        curves = {k: v.equity_curve for k, v in backtest_results.items()}
        st.plotly_chart(strategy_returns_comparison(curves), width="stretch", key="strategy_returns_comparison")

    # ── roadmap / progress bar ─────────────────────────────────────────────
    st.markdown("---")
    st.subheader("Implementation Roadmap")
    pct = active / total * 100
    st.markdown(f"""
    <div style="background:#161b27;padding:16px;border-radius:10px">
      <div style="display:flex;justify-content:space-between;margin-bottom:8px">
        <span style="color:#e0e0e0">Implemented</span>
        <span style="color:#26a69a;font-weight:700">{active} / {total} ({pct:.0f}%)</span>
      </div>
      <div style="background:#1e2130;border-radius:4px;height:10px">
        <div style="background:linear-gradient(90deg,#26a69a,#5c6bc0);
             width:{pct}%;height:10px;border-radius:4px"></div>
      </div>
    </div>
    """, unsafe_allow_html=True)
