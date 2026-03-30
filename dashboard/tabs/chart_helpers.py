"""
Shared chart helper functions used across multiple dashboard tabs.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go


def plot_iv_skew(
    api_key: str,
    underlying: str,
    legs_grp: pd.DataFrame | None = None,
) -> "go.Figure | None":
    """
    Fetch live options chain and plot IV % vs Strike for the nearest expiry.
    If legs_grp is provided, position strikes are marked with dashed vertical lines.
    """
    if not api_key:
        return None
    try:
        from alan_trader.data.polygon_client import PolygonClient
        client = PolygonClient(api_key=api_key)

        exp_dates: list[str] = []
        if legs_grp is not None and "Expiration" in legs_grp.columns:
            exp_dates = sorted(legs_grp["Expiration"].dropna().astype(str).unique())
        if not exp_dates:
            exps = client.get_expirations(underlying)
            exp_dates = exps[:1] if exps else []
        if not exp_dates:
            return None
        exp = exp_dates[0]

        chain = client.get_options_chain(underlying, expiration_date_gte=exp, expiration_date_lte=exp)
        if chain is None or chain.empty or "iv" not in chain.columns:
            return None

        chain = chain.dropna(subset=["iv"])
        calls = chain[chain["type"] == "call"].sort_values("strike")
        puts  = chain[chain["type"] == "put"].sort_values("strike")

        fig = go.Figure()
        if not calls.empty:
            fig.add_trace(go.Scatter(
                x=calls["strike"], y=calls["iv"] * 100,
                mode="lines+markers", name="Call IV",
                line=dict(color="#5c6bc0", width=2), marker=dict(size=5),
            ))
        if not puts.empty:
            fig.add_trace(go.Scatter(
                x=puts["strike"], y=puts["iv"] * 100,
                mode="lines+markers", name="Put IV",
                line=dict(color="#ef5350", width=2), marker=dict(size=5),
            ))

        if legs_grp is not None and not legs_grp.empty:
            _leg_colors = {
                "ShortPut": "#ef5350", "LongPut": "#ffb300",
                "LongCallATK": "#26a69a", "ShortCall": "#ef5350", "LongCall": "#ffb300",
            }
            for _, r in legs_grp.iterrows():
                strike = r.get("Strike")
                if strike is None:
                    continue
                leg_type  = str(r.get("LegType") or "")
                direction = str(r.get("Direction") or "").upper()
                color = _leg_colors.get(leg_type, "#26a69a" if direction == "SELL" else "#ffa726")
                fig.add_vline(
                    x=float(strike), line_dash="dash", line_color=color, line_width=1.5,
                    annotation_text=leg_type or direction,
                    annotation_position="top",
                    annotation_font=dict(size=10, color=color),
                )

        fig.update_layout(
            title=f"IV Skew  —  {underlying}  ({exp})",
            height=350, template="plotly_dark",
            paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
            font=dict(color="#b0b8c8"),
            xaxis=dict(gridcolor="#1e2130", title="Strike"),
            yaxis=dict(gridcolor="#1e2130", title="IV %"),
            legend=dict(orientation="h", y=1.12),
            margin=dict(l=0, r=0, t=50, b=0),
        )
        return fig
    except Exception:
        return None
