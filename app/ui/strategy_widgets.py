"""
app/ui/strategy_widgets.py — presentation primitives shared by the Strategies
page and by strategy plugins' UI hooks.

Strategy plugins import this module (as ``alan_trader.app.ui.strategy_widgets``)
to build screener columns, modal bodies and payoff charts that look like the
platform's own. Nothing here knows about any particular strategy.
"""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
from dash import html, dcc

from app import theme as T
from app.ui import components as C
from app.grid_helpers import mrt_grid  # noqa: F401  (re-exported for plugins)

# Map the legacy raw-colour tile API onto the design-system metric_card tones.
TONE = {T.SUCCESS: "success", T.DANGER: "danger", T.WARNING: "warning",
        T.ACCENT: "accent", T.TEXT_PRIMARY: "default", T.TEXT_MUTED: "muted"}


# ── Numeric parsing / formatting ──────────────────────────────────────────────

def num(v, default: float = 0.0) -> float:
    """
    Parse a screener-grid cell into a float, tolerating display formatting.

    Grid cells are display strings, not numbers: a missing value is the em-dash
    ``"—"``, and present values may carry ``$``, ``%``, ``+`` or thousands
    separators. Always route grid values through here before comparing them
    against a threshold.
    """
    if v is None:
        return default
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    text = str(v).strip()
    if not text or text in {"—", "-", "–", "N/A", "n/a", "None", "nan"}:
        return default
    cleaned = text.replace("$", "").replace("%", "").replace(",", "").replace("+", "")
    cleaned = cleaned.replace("×", "").replace("x", "").strip()
    try:
        return float(cleaned)
    except (TypeError, ValueError):
        return default


def fmt_pct(v) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v)*100:.1f}%"
    except Exception:
        return "—"


def fmt2(v) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):.2f}"
    except Exception:
        return "—"


def fmt_price(v) -> str:
    if v is None:
        return "—"
    try:
        return f"${float(v):.2f}"
    except Exception:
        return "—"


def status_label(raw: dict) -> str:
    """Trade-Ready / Partial / Blocked from the scorer's gate counters."""
    if raw.get("all_pass"):
        return "Trade-Ready"
    return "Partial" if raw.get("n_pass", 0) > 0 else "Blocked"


# ── Grid columns ──────────────────────────────────────────────────────────────

def col(field: str, width: int | None = None, flex: int | None = None,
        min_width: int = 70, numeric: bool = False, pinned: str | None = None,
        sort: str | None = None) -> dict:
    d: dict = {"field": field, "resizable": True, "sortable": True, "filter": True,
               "minWidth": min_width}
    if width:
        d["width"] = width
    if flex:
        d["flex"] = flex
    if numeric:
        d["type"] = "numericColumn"
    if pinned:
        d["pinned"] = pinned
    if sort:
        d["sort"] = sort
    return d


#: Generic column set used when a strategy declares none.
GENERIC_COLS = [
    col("Ticker", width=130, pinned="left"),
    col("Price",  width=110, numeric=True),
    col("Signal", width=110),
    col("Score",  width=110, numeric=True, sort="desc"),
    col("Status", width=160),
]


# ── Screener scan loops ───────────────────────────────────────────────────────

def scan_each(ctx, scorer, *, with_params: bool = True, **extra) -> list[dict]:
    """Run a per-ticker scorer `(ticker, price_df, vix_series, iv_metrics[, params])`
    over the fetched universe (`ScanContext`), keeping the rows it returns."""
    rows: list[dict] = []
    for ticker, df in ctx.price_dfs.items():
        args = [ticker, df, ctx.vix_series, ctx.iv(ticker)]
        if with_params:
            args.append(ctx.params)
        r = scorer(*args, **extra)
        if r:
            rows.append(r)
    return rows


def scan_score_status(ctx, scorer) -> list[dict]:
    """Run a `(ticker, price_df, vix_series, params) -> {Score, Status, ...}`
    scorer and inject Ticker / Price, which those scorers omit."""
    rows: list[dict] = []
    for ticker, df in ctx.price_dfs.items():
        r = scorer(ticker, df, ctx.vix_series, ctx.params)
        if r:
            r["Ticker"] = ticker
            r["Price"] = round(float(df["close"].iloc[-1]), 2)
            rows.append(r)
    return rows


# ── Modal building blocks ─────────────────────────────────────────────────────

def status_color(status: str) -> str:
    return (T.SUCCESS if status == "Trade-Ready" else
            T.WARNING if status == "Partial" else T.DANGER)


def metric(label: str, value, color: str = T.TEXT_PRIMARY):
    """Metric card in the design-system tone for a legacy colour value."""
    return C.metric_card(label, str(value), TONE.get(color, "default"))


def finish_body(row: dict, metrics, signal: str, legs_table=None, chart=None) -> html.Div:
    """Assemble the standard detail-modal body: metrics, signal card, legs,
    chart, score."""
    score_val = row.get("Score", 0)
    score_color = (T.SUCCESS if num(score_val) >= 70 else
                   T.WARNING if num(score_val) >= 40 else T.DANGER)
    return html.Div([
        metrics,
        C.card([
            html.Div("Signal", style={"color": T.TEXT_MUTED, "fontSize": "10px",
                                      "fontWeight": "600", "textTransform": "uppercase",
                                      "marginBottom": "6px"}),
            html.Div(signal, style={"color": T.TEXT_PRIMARY, "fontSize": "13px"}),
        ], pad="sm"),
        legs_table if legs_table is not None else html.Div(),
        chart if chart is not None else html.Div(),
        html.Div([
            html.Span("Score  ", style={"color": T.TEXT_MUTED, "fontSize": "12px"}),
            html.Span(str(score_val), style={"color": score_color,
                                              "fontSize": "1.4rem", "fontWeight": "700"}),
            html.Span(" / 100", style={"color": T.TEXT_MUTED, "fontSize": "12px"}),
        ]),
    ])


def cards_row(*cards) -> html.Div:
    return html.Div(list(cards),
                    style={"display": "flex", "gap": "10px",
                           "flexWrap": "wrap", "marginBottom": "14px"})


def legs_table(rows: list[dict], columns: list[str] | None = None, height: int = 240):
    """Compact legs summary table for strategy modals."""
    fields = columns or ["Leg", "Strike", "Action", "~/Contract"]
    return mrt_grid(
        data=rows,
        col_defs=[{"field": f} for f in fields],
        height=height,
        enable_pagination=False,
    )


def sig_chart(spots, pnl, spot_price, ticker, title, max_loss, max_profit, target,
              stop_level=None):
    """Reusable P&L-at-expiry chart for signal modals.
    stop_level: explicit stop P&L line (e.g. -2×credit). Defaults to max_loss if None."""
    if stop_level is None:
        stop_level = max_loss
    be_prices = []
    for i in range(1, len(spots)):
        if pnl[i-1] * pnl[i] <= 0:
            be_prices.append(float(spots[i]))

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=list(spots), y=pnl,
        mode="lines", name="P&L at expiry",
        line={"color": "#818cf8", "width": 2},
        fill="tozeroy",
        fillcolor="rgba(129,140,248,0.08)",
    ))
    fig.add_trace(go.Scatter(
        x=list(spots), y=[min(p, 0) for p in pnl],
        mode="lines", name="Loss zone",
        line={"width": 0},
        fill="tozeroy",
        fillcolor="rgba(239,68,68,0.12)",
        showlegend=False,
    ))
    fig.add_hline(y=0,      line_dash="solid", line_color="rgba(255,255,255,0.15)", line_width=1)
    fig.add_hline(y=target, line_dash="dash",  line_color="#10b981", line_width=1.5,
                  annotation_text=f"50% target: {target:+.0f}",
                  annotation_font_color="#10b981", annotation_font_size=11)
    fig.add_hline(y=stop_level, line_dash="dash", line_color="#ef4444", line_width=1.5,
                  annotation_text=f"2× stop: {stop_level:+.0f}",
                  annotation_font_color="#ef4444", annotation_font_size=11)
    fig.add_vline(x=spot_price, line_dash="dash", line_color="#f59e0b", line_width=1.5,
                  annotation_text=f"Spot ${spot_price:.0f}",
                  annotation_font_color="#f59e0b", annotation_font_size=11)
    for be in be_prices:
        fig.add_vline(x=be, line_dash="dot", line_color="rgba(255,255,255,0.4)", line_width=1,
                      annotation_text=f"BE ${be:.0f}",
                      annotation_font_color="rgba(255,255,255,0.6)", annotation_font_size=10)
    fig.update_layout(
        title={"text": f"{ticker} {title}", "font": {"size": 13, "color": "#e2e8f0"}, "x": 0.01},
        paper_bgcolor="#1e293b", plot_bgcolor="#1e293b",
        font={"color": "#94a3b8"},
        margin={"l": 50, "r": 20, "t": 40, "b": 40},
        height=320,
        xaxis={"title": "Underlying Price", "gridcolor": "#334155", "tickprefix": "$"},
        yaxis={"title": "P&L per Contract ($)", "gridcolor": "#334155", "tickprefix": "$"},
        showlegend=False,
    )
    return dcc.Graph(figure=fig, config={"displayModeBar": False},
                     style={"marginTop": "14px"})


def iron_condor_payoff_fig(spot, short_call_k, long_call_k, short_put_k, long_put_k,
                           net_credit, dte_used, atm_iv, ticker, best_exp,
                           exit_rule: str = "Exit: 50% profit · 2× stop · 21 DTE"):
    """Four-leg iron-condor payoff: P&L at expiry plus P&L today (Black-Scholes),
    50% target and 2× stop lines, breakevens."""
    import math
    from scipy.stats import norm as _scipy_norm
    r = 0.045
    prices = np.linspace(spot * 0.75, spot * 1.25, 400)

    def pnl_expiry(S):
        call_spread = np.minimum(0, short_call_k - S) + np.maximum(0, S - long_call_k)
        put_spread  = np.minimum(0, S - short_put_k)  + np.maximum(0, long_put_k - S)
        return (net_credit + call_spread + put_spread) * 100

    def pnl_today(S_arr):
        T_     = max(dte_used / 252, 0.001)
        iv     = max(atm_iv or 0.25, 0.01)
        sqT    = math.sqrt(T_)
        exp_rT = math.exp(-r * T_)

        def _call(K):
            d1 = (np.log(S_arr / K) + (r + 0.5 * iv ** 2) * T_) / (iv * sqT)
            return S_arr * _scipy_norm.cdf(d1) - K * exp_rT * _scipy_norm.cdf(d1 - sqT * iv)

        def _put(K):
            d1 = (np.log(S_arr / K) + (r + 0.5 * iv ** 2) * T_) / (iv * sqT)
            return K * exp_rT * _scipy_norm.cdf(sqT * iv - d1) - S_arr * _scipy_norm.cdf(-d1)

        return (net_credit + (-_call(short_call_k) + _call(long_call_k)
                              - _put(short_put_k) + _put(long_put_k))) * 100

    pe = pnl_expiry(prices)
    pt = pnl_today(prices)
    return payoff_figure(
        prices, pe, spot,
        f"{ticker} Iron Condor  |  {best_exp} ({dte_used} DTE)  |  {exit_rule}",
        pnl_today=pt,
        profit_target=net_credit * 0.50 * 100,
        stop_loss=-net_credit * 2.0 * 100,
        breakevens=[("BE", short_call_k + net_credit), ("BE", short_put_k - net_credit)],
    )


def payoff_figure(prices, pnl_expiry, spot, title, *, pnl_today=None,
                  profit_target=None, stop_loss=None, breakevens=(),
                  target_label="50% target", stop_label="2× stop"):
    """Generic payoff diagram (P&L at expiry, optional P&L today, target/stop
    lines, breakeven markers) in the platform theme."""
    prices = np.asarray(prices, dtype=float)
    pe = np.asarray(pnl_expiry, dtype=float)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=prices, y=np.where(pe >= 0, pe, 0),
        fill="tozeroy", fillcolor="rgba(16,185,129,0.10)",
        line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=prices, y=np.where(pe < 0, pe, 0),
        fill="tozeroy", fillcolor="rgba(239,68,68,0.10)",
        line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=prices, y=pe,
        line=dict(color="#6366f1", width=2), name="P&L at expiry",
        hovertemplate="$%{x:.2f} → $%{y:.0f}<extra>At expiry</extra>"))
    if pnl_today is not None:
        fig.add_trace(go.Scatter(x=prices, y=np.asarray(pnl_today, dtype=float),
            line=dict(color="#10b981", width=1.5, dash="dot"), name="P&L today (BS)",
            hovertemplate="$%{x:.2f} → $%{y:.0f}<extra>Today</extra>"))
    if profit_target is not None:
        fig.add_hline(y=profit_target, line=dict(color="#10b981", width=1.5, dash="dash"),
            annotation_text=f"✅ {target_label}: +${profit_target:.0f}",
            annotation_position="top left", annotation_font_color="#10b981")
    if stop_loss is not None:
        fig.add_hline(y=stop_loss, line=dict(color="#ef4444", width=1.5, dash="dash"),
            annotation_text=f"🛑 {stop_label}: -${abs(stop_loss):.0f}",
            annotation_position="bottom left", annotation_font_color="#ef4444")
    fig.add_hline(y=0, line=dict(color="#374151", width=1))
    fig.add_vline(x=spot, line=dict(color="#f59e0b", width=1.5, dash="dash"),
        annotation_text=f"Spot ${spot:.0f}", annotation_font_color="#f59e0b")
    for label, x in breakevens:
        if x is not None:
            fig.add_vline(x=x, line=dict(color="#9ca3af", width=1, dash="dot"),
                annotation_text=f"{label} ${x:.0f}", annotation_font_color="#9ca3af")
    fig.update_layout(
        title=dict(text=title, font=dict(size=13)),
        xaxis_title="Underlying Price", yaxis_title="P&L per Contract ($)",
        height=380, margin=dict(l=0, r=0, t=50, b=0),
        paper_bgcolor=T.BG_BASE, plot_bgcolor=T.BG_CARD,
        font=dict(color=T.TEXT_SEC, size=12),
        xaxis=dict(gridcolor=T.BORDER, tickformat="$,.0f"),
        yaxis=dict(gridcolor=T.BORDER, tickformat="$,.0f", zeroline=False),
        legend=dict(bgcolor="rgba(0,0,0,0)", orientation="h", y=-0.15),
        template="plotly_dark",
    )
    return fig
