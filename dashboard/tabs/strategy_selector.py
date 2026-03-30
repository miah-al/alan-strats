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
    cfg = {
        "Active":   ("#10b981", "rgba(16,185,129,0.15)"),
        "Stub":     ("#6b7280", "rgba(107,114,128,0.15)"),
        "Disabled": ("#ef4444", "rgba(239,68,68,0.15)"),
    }
    fg, bg = cfg.get(status, ("#6b7280", "rgba(107,114,128,0.15)"))
    return (f'<span style="background:{bg};color:{fg};padding:2px 9px;border-radius:10px;'
            f'font-size:11px;font-weight:600;font-family:Inter,sans-serif;border:1px solid {fg}40">'
            f'{status}</span>')


def _type_badge(t: str) -> str:
    cfg = {
        "AI":     ("#a78bfa", "rgba(167,139,250,0.15)"),
        "RULE":   ("#6366f1", "rgba(99,102,241,0.15)"),
        "HYBRID": ("#f59e0b", "rgba(245,158,11,0.15)"),
    }
    fg, bg = cfg.get(t.upper(), ("#6b7280", "rgba(107,114,128,0.15)"))
    return (f'<span style="background:{bg};color:{fg};padding:2px 9px;border-radius:10px;'
            f'font-size:11px;font-weight:600;font-family:Inter,sans-serif;border:1px solid {fg}40">'
            f'{t.upper()}</span>')


def _metric_card(label: str, value: str, delta: str = "", delta_positive: bool = True,
                 accent: str = "#6366f1") -> str:
    """Render a professional metric card as HTML."""
    delta_color = "#10b981" if delta_positive else "#ef4444"
    delta_html = ""
    if delta:
        delta_html = (
            f'<div style="margin-top:6px;font-size:11px;font-weight:500;'
            f'color:{delta_color};font-family:\'JetBrains Mono\',monospace;">'
            f'{delta}</div>'
        )
    return (
        f'<div style="'
        f'background:#111827;'
        f'border:1px solid #1f2937;'
        f'border-top:2px solid {accent};'
        f'border-radius:10px;'
        f'padding:14px 18px;'
        f'transition:border-color 0.2s,box-shadow 0.2s;'
        f'">'
        f'<div style="color:#6b7280;font-size:10px;font-weight:700;'
        f'text-transform:uppercase;letter-spacing:0.09em;'
        f'font-family:Inter,sans-serif;margin-bottom:6px">{label}</div>'
        f'<div style="color:#f9fafb;font-size:1.5rem;font-weight:700;'
        f'font-family:\'JetBrains Mono\',monospace;letter-spacing:-0.02em;line-height:1">'
        f'{value}</div>'
        f'{delta_html}'
        f'</div>'
    )


def render(backtest_results: dict = None, selected_slugs: list = None):
    """
    backtest_results: {slug: BacktestResult} for active strategies
    selected_slugs:   list of slugs currently selected by sidebar
    """
    st.markdown(
        '<h2 style="color:#f9fafb;font-size:1.25rem;font-weight:700;'
        'padding-left:12px;border-left:3px solid #6366f1;'
        'margin-bottom:20px;font-family:Inter,sans-serif">Strategy Registry</h2>',
        unsafe_allow_html=True,
    )

    meta_df = registry_dataframe()

    # ── top-level counters ─────────────────────────────────────────────────
    total    = len(STRATEGY_METADATA)
    active   = sum(1 for m in STRATEGY_METADATA.values() if m["status"] == "active")
    stub     = sum(1 for m in STRATEGY_METADATA.values() if m["status"] == "stub")
    ai       = sum(1 for m in STRATEGY_METADATA.values() if m["type"] == "ai")
    rule     = sum(1 for m in STRATEGY_METADATA.values() if m["type"] == "rule")

    _cards = [
        _metric_card("Total Strategies", str(total),  accent="#6366f1"),
        _metric_card("Implemented",       str(active), delta=f"{active}/{total} · {active*100//total}%",
                     delta_positive=True, accent="#10b981"),
        _metric_card("Stubs (Roadmap)",  str(stub),   accent="#f59e0b"),
        _metric_card("AI-Driven",         str(ai),     accent="#a78bfa"),
        _metric_card("Rule-Based",        str(rule),   accent="#38bdf8"),
    ]
    st.markdown(
        '<div style="display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:24px">'
        + "".join(_cards) + "</div>",
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # ── strategy grid ──────────────────────────────────────────────────────
    st.markdown(
        '<h2 style="color:#f9fafb;font-size:1.05rem;font-weight:700;'
        'padding-left:12px;border-left:3px solid #6366f1;'
        'margin-bottom:16px;font-family:Inter,sans-serif">All 30 Strategies</h2>',
        unsafe_allow_html=True,
    )

    display_df = meta_df[["Name", "Type", "Status", "Asset Class",
                           "Typical Hold (days)", "Target Sharpe"]].copy()

    # Inject Sharpe from backtest results if available
    if backtest_results:
        def _fmt_sharpe(s):
            if s not in backtest_results or not backtest_results[s].metrics:
                return "—"
            v = backtest_results[s].metrics.get("sharpe")
            try:
                return f"{float(v):.2f}" if v is not None else "—"
            except (TypeError, ValueError):
                return "—"
        display_df["Live Sharpe"] = display_df.index.map(_fmt_sharpe)

    # Style the dataframe
    def _row_style(row):
        if row["Status"] == "Active":
            return ["background-color: #0d1a14"] * len(row)
        return ["background-color: #0a0e1a"] * len(row)

    st.dataframe(
        display_df.style.apply(_row_style, axis=1),
        width="stretch",
        height=700,
    )

    st.markdown("---")

    # ── detail view for selected strategy ─────────────────────────────────
    st.markdown(
        '<h2 style="color:#f9fafb;font-size:1.05rem;font-weight:700;'
        'padding-left:12px;border-left:3px solid #6366f1;'
        'margin-bottom:16px;font-family:Inter,sans-serif">Strategy Detail</h2>',
        unsafe_allow_html=True,
    )
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
        <div style="
            background:#111827;
            border:1px solid #1f2937;
            border-top:2px solid #6366f1;
            border-radius:10px;
            padding:20px 22px;
        ">
          <div style="
              font-size:1.1rem;font-weight:700;
              color:#f9fafb;margin-bottom:10px;
              font-family:Inter,sans-serif;letter-spacing:-0.01em;
          ">{meta["display_name"]}</div>
          <div style="margin-bottom:12px;display:flex;gap:6px;flex-wrap:wrap">
            {_type_badge(meta["type"])} {_status_badge(meta["status"].capitalize())}
          </div>
          <p style="color:#9ca3af;margin:0 0 14px;font-size:13px;line-height:1.6;
                     font-family:Inter,sans-serif">{meta["description"]}</p>
          <table style="width:100%;border-collapse:collapse;">
            <tr style="border-bottom:1px solid #1f2937">
              <td style="color:#6b7280;font-size:11px;font-weight:600;text-transform:uppercase;
                         letter-spacing:.07em;padding:7px 0;font-family:Inter,sans-serif">Asset Class</td>
              <td style="color:#d1d5db;font-size:13px;font-weight:500;padding:7px 0 7px 16px;
                         font-family:Inter,sans-serif">{meta.get("asset_class","—")}</td>
            </tr>
            <tr style="border-bottom:1px solid #1f2937">
              <td style="color:#6b7280;font-size:11px;font-weight:600;text-transform:uppercase;
                         letter-spacing:.07em;padding:7px 0;font-family:Inter,sans-serif">Typical Hold</td>
              <td style="color:#d1d5db;font-size:13px;font-weight:500;padding:7px 0 7px 16px;
                         font-family:'JetBrains Mono',monospace">{meta.get("typical_holding_days","—")} days</td>
            </tr>
            <tr style="border-bottom:1px solid #1f2937">
              <td style="color:#6b7280;font-size:11px;font-weight:600;text-transform:uppercase;
                         letter-spacing:.07em;padding:7px 0;font-family:Inter,sans-serif">Target Sharpe</td>
              <td style="color:#10b981;font-size:13px;font-weight:700;padding:7px 0 7px 16px;
                         font-family:'JetBrains Mono',monospace">{meta.get("target_sharpe","—")}</td>
            </tr>
            <tr>
              <td style="color:#6b7280;font-size:11px;font-weight:600;text-transform:uppercase;
                         letter-spacing:.07em;padding:7px 0;font-family:Inter,sans-serif;vertical-align:top">Class</td>
              <td style="color:#6366f1;font-size:10px;padding:7px 0 7px 16px;
                         font-family:'JetBrains Mono',monospace;word-break:break-all">{meta.get("class_path","(stub)")}</td>
            </tr>
          </table>
        </div>
        """, unsafe_allow_html=True)

    with d2:
        if meta["status"] == "active" and backtest_results and selected in backtest_results:
            res = backtest_results[selected]
            m   = res.metrics
            st.markdown(
                '<div style="color:#6b7280;font-size:10px;font-weight:700;'
                'text-transform:uppercase;letter-spacing:0.09em;'
                'font-family:Inter,sans-serif;margin-bottom:12px">Backtest Metrics</div>',
                unsafe_allow_html=True,
            )

            def _val_color(label, val_str):
                """Return a color hint for certain metrics."""
                try:
                    num = float(val_str.replace("%", "").replace("$", "").replace(",", ""))
                except ValueError:
                    return "#f9fafb"
                if "Return" in label or "Win Rate" in label or "Profit Factor" in label:
                    return "#10b981" if num > 0 else "#ef4444"
                if "Drawdown" in label or "VaR" in label:
                    return "#f59e0b"
                if "Sharpe" in label or "Sortino" in label or "Calmar" in label:
                    return "#10b981" if num >= 1 else ("#f59e0b" if num >= 0 else "#ef4444")
                return "#f9fafb"

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
            rows_html = ""
            for i, (label, val) in enumerate(pairs):
                row_bg = "#111827" if i % 2 == 0 else "#0f1623"
                vc = _val_color(label, val)
                rows_html += (
                    f'<div style="display:flex;justify-content:space-between;align-items:center;'
                    f'padding:8px 12px;background:{row_bg};'
                    f'border-bottom:1px solid #1f2937;">'
                    f'<span style="color:#9ca3af;font-size:12px;font-family:Inter,sans-serif">{label}</span>'
                    f'<span style="color:{vc};font-weight:700;font-size:13px;'
                    f'font-family:\'JetBrains Mono\',monospace">{val}</span>'
                    f'</div>'
                )
            st.markdown(
                f'<div style="border:1px solid #1f2937;border-radius:10px;overflow:hidden">'
                f'{rows_html}</div>',
                unsafe_allow_html=True,
            )
        elif meta["status"] == "active":
            st.markdown(
                '<div style="background:#111827;border:1px solid #1f2937;border-radius:10px;'
                'padding:20px;text-align:center;">'
                '<div style="font-size:1.5rem;margin-bottom:8px">⚡</div>'
                '<div style="color:#9ca3af;font-size:13px;font-family:Inter,sans-serif">'
                'Run a backtest to see live metrics</div>'
                '</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div style="background:#111827;border:1px solid #1f2937;border-radius:10px;'
                'padding:24px;text-align:center;">'
                '<div style="font-size:2rem;margin-bottom:10px">🚧</div>'
                '<div style="color:#9ca3af;font-size:13px;font-weight:500;'
                'font-family:Inter,sans-serif">Not yet implemented</div>'
                '<div style="color:#6b7280;font-size:11px;margin-top:6px;font-family:Inter,sans-serif">'
                'This strategy is on the roadmap.</div>'
                '</div>',
                unsafe_allow_html=True,
            )

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
    st.markdown(
        '<h2 style="color:#f9fafb;font-size:1.05rem;font-weight:700;'
        'padding-left:12px;border-left:3px solid #6366f1;'
        'margin-bottom:16px;font-family:Inter,sans-serif">Implementation Roadmap</h2>',
        unsafe_allow_html=True,
    )
    pct = active / total * 100
    st.markdown(f"""
    <div style="
        background:#111827;border:1px solid #1f2937;
        border-radius:10px;padding:18px 20px;
    ">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
        <span style="color:#9ca3af;font-size:13px;font-family:Inter,sans-serif">
          Strategies implemented
        </span>
        <span style="
            color:#10b981;font-weight:700;font-size:14px;
            font-family:'JetBrains Mono',monospace;
        ">{active} / {total}
          <span style="color:#6b7280;font-size:12px;font-weight:500"> · {pct:.0f}%</span>
        </span>
      </div>
      <div style="background:#1f2937;border-radius:6px;height:8px;overflow:hidden">
        <div style="
            background:linear-gradient(90deg,#6366f1,#10b981);
            width:{pct}%;height:8px;border-radius:6px;
            box-shadow:0 0 8px rgba(99,102,241,0.4);
            transition:width 0.6s ease;
        "></div>
      </div>
      <div style="
          display:flex;gap:20px;margin-top:12px;flex-wrap:wrap;
      ">
        <span style="
            color:#6b7280;font-size:11px;font-family:Inter,sans-serif;
        ">
          <span style="
              display:inline-block;width:8px;height:8px;border-radius:50%;
              background:#10b981;margin-right:5px;vertical-align:middle;
          "></span>Active: {active}
        </span>
        <span style="
            color:#6b7280;font-size:11px;font-family:Inter,sans-serif;
        ">
          <span style="
              display:inline-block;width:8px;height:8px;border-radius:50%;
              background:#f59e0b;margin-right:5px;vertical-align:middle;
          "></span>Roadmap: {total - active}
        </span>
      </div>
    </div>
    """, unsafe_allow_html=True)
