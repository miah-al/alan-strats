"""
All Plotly chart functions.
Each function accepts data and returns a plotly Figure object.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

COLORS = {
    "bull":    "#26a69a",
    "bear":    "#ef5350",
    "neutral": "#78909c",
    "equity":  "#5c6bc0",
    "spy":     "#ffa726",
    "loss":    "#ef5350",
    "acc":     "#66bb6a",
    "vix":     "#ab47bc",
    "bg":      "#0e1117",
    "grid":    "#1e2130",
    "text":    "#e0e0e0",
}

_LAYOUT = dict(
    paper_bgcolor="#0e1117",
    plot_bgcolor="#0e1117",
    font=dict(color="#e0e0e0", family="monospace"),
    margin=dict(l=50, r=30, t=50, b=40),
)


def _apply(fig: go.Figure, title: str = "", height: int = 400) -> go.Figure:
    fig.update_layout(
        **_LAYOUT,
        title=dict(text=title, font=dict(size=14, color="#e0e0e0")),
        height=height,
        xaxis=dict(gridcolor=COLORS["grid"], showgrid=True),
        yaxis=dict(gridcolor=COLORS["grid"], showgrid=True),
    )
    return fig


# ============================================================
# TRAINING CHARTS
# ============================================================

def loss_curves(history: dict) -> go.Figure:
    """Line chart: train/val loss over epochs."""
    epochs = list(range(1, len(history["train_loss"]) + 1))
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=epochs, y=history["train_loss"],
                             name="Train Loss", line=dict(color=COLORS["loss"], width=2)))
    fig.add_trace(go.Scatter(x=epochs, y=history["val_loss"],
                             name="Val Loss",   line=dict(color="#ff8a65", width=2, dash="dash")))
    return _apply(fig, "Loss Curves", 350)


def accuracy_curves(history: dict) -> go.Figure:
    """Line chart: train/val accuracy over epochs."""
    epochs = list(range(1, len(history["train_acc"]) + 1))
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=epochs, y=history["train_acc"],
                             name="Train Acc", line=dict(color=COLORS["acc"], width=2)))
    fig.add_trace(go.Scatter(x=epochs, y=history["val_acc"],
                             name="Val Acc",   line=dict(color="#a5d6a7", width=2, dash="dash")))
    fig.update_layout(yaxis=dict(range=[0, 1], tickformat=".0%"))
    return _apply(fig, "Accuracy Curves", 350)


def confusion_matrix_heatmap(cm: np.ndarray) -> go.Figure:
    """Annotated heatmap of the 3×3 confusion matrix."""
    labels = ["Bear", "Neutral", "Bull"]
    cm_pct = cm / cm.sum(axis=1, keepdims=True) * 100
    text = [[f"{cm[i,j]:.0f}<br>({cm_pct[i,j]:.1f}%)" for j in range(3)] for i in range(3)]

    fig = go.Figure(go.Heatmap(
        z=cm_pct, x=labels, y=labels,
        text=text, texttemplate="%{text}",
        colorscale="Blues", showscale=False,
        hoverongaps=False,
    ))
    fig.update_layout(
        **_LAYOUT,
        title="Confusion Matrix (% of true class)",
        xaxis_title="Predicted", yaxis_title="Actual",
        height=380,
    )
    return fig


def label_distribution_pie(labels: np.ndarray | list) -> go.Figure:
    """Pie chart of Bear / Neutral / Bull label counts."""
    from collections import Counter
    counts = Counter(labels)
    names  = ["Bear", "Neutral", "Bull"]
    values = [counts.get(i, 0) for i in range(3)]
    fig = go.Figure(go.Pie(
        labels=names, values=values,
        marker=dict(colors=[COLORS["bear"], COLORS["neutral"], COLORS["bull"]]),
        hole=0.4, textinfo="label+percent",
    ))
    fig.update_layout(**_LAYOUT, title="Label Distribution", height=340,
                      showlegend=False)
    return fig


def feature_importance_bar(importance: pd.Series, top_n: int = 15) -> go.Figure:
    """Horizontal bar chart of top-N feature importances."""
    top = importance.head(top_n).sort_values()
    fig = go.Figure(go.Bar(
        x=top.values, y=top.index, orientation="h",
        marker=dict(
            color=top.values,
            colorscale="Teal",
            showscale=False,
        ),
    ))
    return _apply(fig, f"Top {top_n} Feature Importances", 420)


def feature_correlation_heatmap(df: pd.DataFrame, cols: list[str]) -> go.Figure:
    """Correlation matrix heatmap for selected features."""
    available = [c for c in cols if c in df.columns][:20]
    corr = df[available].corr()
    fig = go.Figure(go.Heatmap(
        z=corr.values, x=corr.columns, y=corr.index,
        colorscale="RdBu", zmid=0,
        colorbar=dict(thickness=10),
    ))
    fig.update_layout(
        **_LAYOUT,
        title="Feature Correlation Matrix",
        height=520,
        xaxis=dict(tickangle=-45),
    )
    return fig


def feature_scatter_3d(df: pd.DataFrame, fx: str, fy: str, fz: str,
                        label_col: str = "label") -> go.Figure:
    """3-D scatter of three features colored by signal class."""
    if not all(c in df.columns for c in [fx, fy, fz, label_col]):
        return go.Figure()

    label_map  = {0: "Bear", 1: "Neutral", 2: "Bull"}
    color_map  = {0: COLORS["bear"], 1: COLORS["neutral"], 2: COLORS["bull"]}
    fig = go.Figure()
    for cls, name in label_map.items():
        mask = df[label_col] == cls
        fig.add_trace(go.Scatter3d(
            x=df.loc[mask, fx], y=df.loc[mask, fy], z=df.loc[mask, fz],
            mode="markers",
            marker=dict(size=3, color=color_map[cls], opacity=0.7),
            name=name,
        ))
    fig.update_layout(
        **_LAYOUT,
        title=f"3-D Feature Space: {fx} / {fy} / {fz}",
        height=520,
        scene=dict(
            xaxis=dict(title=fx, backgroundcolor=COLORS["bg"],
                       gridcolor=COLORS["grid"], showbackground=True),
            yaxis=dict(title=fy, backgroundcolor=COLORS["bg"],
                       gridcolor=COLORS["grid"], showbackground=True),
            zaxis=dict(title=fz, backgroundcolor=COLORS["bg"],
                       gridcolor=COLORS["grid"], showbackground=True),
        ),
    )
    return fig


def rsi_vix_scatter(df: pd.DataFrame) -> go.Figure:
    """2-D scatter: RSI vs VIX, colored by label."""
    if not all(c in df.columns for c in ["rsi_14", "vix", "label"]):
        return go.Figure()

    label_map = {0: "Bear", 1: "Neutral", 2: "Bull"}
    color_map = {0: COLORS["bear"], 1: COLORS["neutral"], 2: COLORS["bull"]}
    fig = go.Figure()
    for cls, name in label_map.items():
        mask = df["label"] == cls
        fig.add_trace(go.Scatter(
            x=df.loc[mask, "rsi_14"], y=df.loc[mask, "vix"],
            mode="markers",
            marker=dict(size=5, color=color_map[cls], opacity=0.6),
            name=name,
        ))
    fig.update_layout(
        **_LAYOUT,
        xaxis_title="RSI-14", yaxis_title="VIX",
        title="RSI vs VIX by Signal Class",
        height=380,
    )
    return fig


# ============================================================
# BACKTEST CHARTS
# ============================================================

def equity_curve(equity_df: pd.DataFrame) -> go.Figure:
    """Equity curve vs buy-and-hold benchmark."""
    starting = equity_df["equity"].iloc[0]
    price_start = equity_df["price"].iloc[0]
    bah = starting * equity_df["price"] / price_start

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=equity_df.index, y=equity_df["equity"],
        name="Strategy", line=dict(color=COLORS["equity"], width=2),
        fill="tozeroy", fillcolor="rgba(92,107,192,0.08)",
    ))
    fig.add_trace(go.Scatter(
        x=equity_df.index, y=bah,
        name="Buy & Hold", line=dict(color=COLORS["spy"], width=1.5, dash="dot"),
    ))
    return _apply(fig, "Equity Curve vs Buy-and-Hold", 420)


def drawdown_chart(equity_df: pd.DataFrame) -> go.Figure:
    """Underwater (drawdown) chart."""
    eq = equity_df["equity"]
    dd = (eq / eq.cummax() - 1) * 100
    fig = go.Figure(go.Scatter(
        x=equity_df.index, y=dd,
        fill="tozeroy", fillcolor="rgba(239,83,80,0.25)",
        line=dict(color=COLORS["bear"], width=1),
        name="Drawdown",
    ))
    return _apply(fig, "Drawdown (%)", 280)


def trade_pnl_scatter(trades_df: pd.DataFrame) -> go.Figure:
    """Scatter: each trade's P&L vs entry date, sized by contracts."""
    if trades_df.empty:
        return go.Figure()

    colors = trades_df["pnl"].apply(lambda v: COLORS["bull"] if v > 0 else COLORS["bear"])
    fig = go.Figure(go.Scatter(
        x=trades_df["entry_date"],
        y=trades_df["pnl"],
        mode="markers",
        marker=dict(
            size=8,
            color=trades_df["pnl"],
            colorscale=[[0, COLORS["bear"]], [0.5, "#78909c"], [1, COLORS["bull"]]],
            showscale=True,
            colorbar=dict(title="P&L $", thickness=10),
        ),
        text=trades_df["spread_type"],
        hovertemplate="Date: %{x}<br>P&L: $%{y:.2f}<br>Type: %{text}<extra></extra>",
    ))
    fig.add_hline(y=0, line=dict(color="#aaa", dash="dash", width=1))
    return _apply(fig, "Trade P&L Scatter", 380)


def pnl_histogram(trades_df: pd.DataFrame) -> go.Figure:
    """Histogram of trade P&L distribution."""
    if trades_df.empty:
        return go.Figure()

    wins   = trades_df[trades_df["pnl"] > 0]["pnl"]
    losses = trades_df[trades_df["pnl"] <= 0]["pnl"]
    fig = go.Figure()
    fig.add_trace(go.Histogram(x=losses, name="Losses",
                               marker_color=COLORS["bear"], opacity=0.75,
                               xbins=dict(size=50)))
    fig.add_trace(go.Histogram(x=wins, name="Wins",
                               marker_color=COLORS["bull"], opacity=0.75,
                               xbins=dict(size=50)))
    fig.add_vline(x=0, line=dict(color="#aaa", dash="dash"))
    fig.update_layout(barmode="overlay")
    return _apply(fig, "P&L Distribution", 340)


def win_loss_pie(trades_df: pd.DataFrame) -> go.Figure:
    """Donut chart: win / loss / skip breakdown."""
    if trades_df.empty:
        return go.Figure()

    n_win  = (trades_df["pnl"] > 0).sum()
    n_loss = (trades_df["pnl"] < 0).sum()
    n_be   = (trades_df["pnl"] == 0).sum()
    fig = go.Figure(go.Pie(
        labels=["Win", "Loss", "Breakeven"],
        values=[n_win, n_loss, n_be],
        marker=dict(colors=[COLORS["bull"], COLORS["bear"], COLORS["neutral"]]),
        hole=0.45, textinfo="label+percent",
    ))
    fig.update_layout(**_LAYOUT, title="Win / Loss Breakdown",
                      height=340, showlegend=False)
    return fig


def monthly_returns_heatmap(equity_df: pd.DataFrame) -> go.Figure:
    """Calendar heatmap of monthly returns."""
    eq = equity_df["equity"]
    eq.index = pd.to_datetime(eq.index)
    monthly = eq.resample("ME").last().pct_change().dropna() * 100

    df = pd.DataFrame({
        "year":  monthly.index.year,
        "month": monthly.index.strftime("%b"),
        "ret":   monthly.values,
    })
    pivot = df.pivot(index="year", columns="month", values="ret")
    month_order = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    pivot = pivot.reindex(columns=[m for m in month_order if m in pivot.columns])

    fig = go.Figure(go.Heatmap(
        z=pivot.values, x=pivot.columns, y=pivot.index.astype(str),
        colorscale=[[0, COLORS["bear"]], [0.5, "#1e2130"], [1, COLORS["bull"]]],
        zmid=0,
        text=[[f"{v:.1f}%" if not np.isnan(v) else "" for v in row] for row in pivot.values],
        texttemplate="%{text}",
        colorbar=dict(title="%", thickness=10),
    ))
    fig.update_layout(**_LAYOUT, title="Monthly Returns (%)", height=320)
    return fig


def price_with_signals(equity_df: pd.DataFrame, trades_df: pd.DataFrame) -> go.Figure:
    """Price line with entry/exit markers."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=equity_df.index, y=equity_df["price"],
        name="Price", line=dict(color=COLORS["spy"], width=1.5),
    ))

    def _trade_y(subset: pd.DataFrame) -> pd.Series:
        """Look up price at each trade entry date from the equity_df."""
        if "price" in subset.columns:
            return subset["price"]
        price = equity_df["price"].copy()
        price.index = pd.to_datetime(price.index)
        dates = pd.to_datetime(subset["entry_date"])
        return dates.map(lambda d: price.asof(d) if d >= price.index[0] else price.iloc[0])

    if not trades_df.empty:
        bull_trades = trades_df[trades_df["spread_type"].isin(["bull_call", "bull_put"])]
        bear_trades = trades_df[trades_df["spread_type"].isin(["bear_put", "bear_call"])]

        if not bull_trades.empty:
            fig.add_trace(go.Scatter(
                x=bull_trades["entry_date"], y=_trade_y(bull_trades),
                mode="markers", name="Bull Entry",
                marker=dict(symbol="triangle-up", size=10, color=COLORS["bull"]),
            ))
        if not bear_trades.empty:
            fig.add_trace(go.Scatter(
                x=bear_trades["entry_date"], y=_trade_y(bear_trades),
                mode="markers", name="Bear Entry",
                marker=dict(symbol="triangle-down", size=10, color=COLORS["bear"]),
            ))

    return _apply(fig, "Price with Trade Entries", 380)


def exit_reason_pie(trades_df: pd.DataFrame) -> go.Figure:
    """Pie chart of exit reasons."""
    if trades_df.empty or "exit_reason" not in trades_df.columns:
        return go.Figure()
    counts = trades_df["exit_reason"].value_counts()
    fig = go.Figure(go.Pie(
        labels=counts.index, values=counts.values,
        hole=0.4, textinfo="label+percent",
        marker=dict(colors=px.colors.qualitative.Set2),
    ))
    fig.update_layout(**_LAYOUT, title="Exit Reasons", height=320, showlegend=False)
    return fig


def rolling_sharpe(equity_df: pd.DataFrame, window: int = 60) -> go.Figure:
    """Rolling Sharpe ratio over time."""
    rets = equity_df["equity"].pct_change().dropna()
    rs = (rets.rolling(window).mean() / rets.rolling(window).std()) * np.sqrt(252)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=rs.index, y=rs, name=f"Sharpe ({window}d)",
                             line=dict(color="#ce93d8", width=2)))
    fig.add_hline(y=0, line=dict(color="#888", dash="dash"))
    fig.add_hline(y=1, line=dict(color=COLORS["bull"], dash="dot", width=1))
    return _apply(fig, f"Rolling {window}-Day Sharpe Ratio", 320)


# ============================================================
# LIVE DASHBOARD CHARTS
# ============================================================

def signal_gauge(proba: list[float]) -> go.Figure:
    """Gauge showing current directional bias (-1 = full bear, +1 = full bull)."""
    bear_p, neutral_p, bull_p = proba
    score = bull_p - bear_p   # range roughly -1 to 1

    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=round(score * 100, 1),
        title={"text": "Signal Bias (Bull − Bear) %"},
        delta={"reference": 0},
        gauge={
            "axis": {"range": [-100, 100], "tickwidth": 1},
            "bar": {"color": COLORS["bull"] if score > 0 else COLORS["bear"]},
            "bgcolor": COLORS["bg"],
            "borderwidth": 1,
            "steps": [
                {"range": [-100, -20], "color": "rgba(239,83,80,0.15)"},
                {"range": [-20, 20],   "color": "rgba(120,144,156,0.10)"},
                {"range": [20, 100],   "color": "rgba(38,166,154,0.15)"},
            ],
            "threshold": {
                "line": {"color": "#fff", "width": 2},
                "thickness": 0.75,
                "value": score * 100,
            },
        },
    ))
    fig.update_layout(**_LAYOUT, height=280)
    return fig


def proba_bar(proba: list[float]) -> go.Figure:
    """Horizontal bar chart of Bear/Neutral/Bull probabilities."""
    fig = go.Figure(go.Bar(
        x=proba,
        y=["Bear", "Neutral", "Bull"],
        orientation="h",
        marker=dict(color=[COLORS["bear"], COLORS["neutral"], COLORS["bull"]]),
        text=[f"{p:.1%}" for p in proba],
        textposition="inside",
    ))
    fig.update_layout(
        **_LAYOUT,
        xaxis=dict(range=[0, 1], tickformat=".0%", gridcolor=COLORS["grid"]),
        yaxis=dict(gridcolor=COLORS["grid"]),
        title="Model Signal Probabilities",
        showlegend=False,
        height=220,
    )
    return fig


def live_portfolio_line(signals_df: pd.DataFrame) -> go.Figure:
    """Portfolio value over recent signal history."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=signals_df["date"], y=signals_df["portfolio_value"],
        line=dict(color=COLORS["equity"], width=2.5),
        fill="tozeroy", fillcolor="rgba(92,107,192,0.10)",
        name="Portfolio",
    ))
    fig.add_trace(go.Scatter(
        x=signals_df["date"], y=signals_df["price"] * (signals_df["portfolio_value"].iloc[0] / signals_df["price"].iloc[0]),
        line=dict(color=COLORS["spy"], width=1.5, dash="dot"),
        name="Buy & Hold",
    ))
    return _apply(fig, "Live Portfolio Value", 340)


def live_pnl_bars(signals_df: pd.DataFrame) -> go.Figure:
    """Daily P&L bars for recent trades."""
    colors = [COLORS["bull"] if p > 0 else COLORS["bear"] for p in signals_df["pnl"]]
    fig = go.Figure(go.Bar(
        x=signals_df["date"], y=signals_df["pnl"],
        marker_color=colors, name="Daily P&L",
    ))
    fig.add_hline(y=0, line=dict(color="#aaa", width=1))
    return _apply(fig, "Trade P&L History ($)", 300)


def signal_timeline(signals_df: pd.DataFrame) -> go.Figure:
    """Scatter plot of signal type over time with price."""
    color_map = {"BULL": COLORS["bull"], "NEUTRAL": COLORS["neutral"], "BEAR": COLORS["bear"]}
    colors = signals_df["signal"].map(color_map)

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.65, 0.35],
                        vertical_spacing=0.04)
    fig.add_trace(go.Scatter(
        x=signals_df["date"], y=signals_df["price"],
        name="Price", line=dict(color=COLORS["spy"], width=1.5),
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=signals_df["date"], y=signals_df["price"],
        mode="markers",
        marker=dict(size=10, color=colors, symbol="circle"),
        name="Signal",
        text=signals_df["signal"],
        hovertemplate="Date: %{x}<br>Signal: %{text}<br>Price: $%{y:.2f}<extra></extra>",
    ), row=1, col=1)
    fig.add_trace(go.Bar(
        x=signals_df["date"], y=signals_df["pnl"],
        marker_color=[COLORS["bull"] if p >= 0 else COLORS["bear"] for p in signals_df["pnl"]],
        name="P&L",
    ), row=2, col=1)
    fig.update_layout(**_LAYOUT, title="Signal Timeline with P&L", height=500,
                      xaxis2=dict(gridcolor=COLORS["grid"]),
                      yaxis=dict(gridcolor=COLORS["grid"]),
                      yaxis2=dict(gridcolor=COLORS["grid"], title="P&L ($)"))
    return fig


def vix_vs_confidence_scatter(signals_df: pd.DataFrame) -> go.Figure:
    """VIX level vs model confidence, colored by signal class."""
    if "price" not in signals_df.columns:
        return go.Figure()

    color_map = {"BULL": COLORS["bull"], "NEUTRAL": COLORS["neutral"], "BEAR": COLORS["bear"]}
    fig = go.Figure()
    for sig, grp in signals_df.groupby("signal"):
        fig.add_trace(go.Scatter(
            x=grp["confidence"], y=grp["pnl"],
            mode="markers",
            marker=dict(size=8, color=color_map.get(sig, "#aaa"), opacity=0.8),
            name=sig,
            hovertemplate=f"Signal: {sig}<br>Confidence: %{{x:.1%}}<br>P&L: $%{{y:.2f}}<extra></extra>",
        ))
    fig.add_hline(y=0, line=dict(color="#aaa", dash="dash"))
    return _apply(fig, "Model Confidence vs Realized P&L", 340)


def cumulative_pnl_line(signals_df: pd.DataFrame) -> go.Figure:
    """Cumulative P&L line chart."""
    cum = signals_df["pnl"].cumsum()
    colors = [COLORS["bull"] if v >= 0 else COLORS["bear"] for v in cum]
    fig = go.Figure(go.Scatter(
        x=signals_df["date"], y=cum,
        line=dict(color=COLORS["equity"], width=2),
        fill="tozeroy",
        fillcolor="rgba(92,107,192,0.12)",
        name="Cumulative P&L",
    ))
    fig.add_hline(y=0, line=dict(color="#aaa", dash="dash"))
    return _apply(fig, "Cumulative P&L ($)", 300)


def spread_type_pie(signals_df: pd.DataFrame) -> go.Figure:
    """Pie of how often each spread type was used."""
    counts = signals_df["spread_type"].value_counts()
    fig = go.Figure(go.Pie(
        labels=counts.index, values=counts.values,
        hole=0.4, textinfo="label+percent",
        marker=dict(colors=[COLORS["bull"], COLORS["bear"],
                             COLORS["neutral"], "#ffa726", "#ce93d8"]),
    ))
    fig.update_layout(**_LAYOUT, title="Spread Types Used",
                      height=300, showlegend=False)
    return fig


# ============================================================
# MULTI-STRATEGY / PORTFOLIO CHARTS
# ============================================================

_STRATEGY_COLORS = [
    "#5c6bc0", "#26a69a", "#ffa726", "#ef5350", "#ab47bc",
    "#42a5f5", "#66bb6a", "#ff7043", "#26c6da", "#d4e157",
]


def strategy_returns_comparison(
    equity_curves: dict,
    spy_equity=None,
) -> go.Figure:
    """Multi-line cumulative returns (%) for each strategy."""
    fig = go.Figure()
    for i, (name, eq) in enumerate(equity_curves.items()):
        eq = pd.to_numeric(eq, errors="coerce").dropna()
        if eq.empty or eq.iloc[0] == 0:
            continue
        pct = (eq / eq.iloc[0] - 1) * 100
        color = _STRATEGY_COLORS[i % len(_STRATEGY_COLORS)]
        fig.add_trace(go.Scatter(
            x=pct.index, y=pct,
            name=name.replace("_", " ").title(),
            line=dict(color=color, width=2),
        ))
    if spy_equity is not None and not spy_equity.empty:
        spy_pct = (spy_equity / spy_equity.iloc[0] - 1) * 100
        fig.add_trace(go.Scatter(
            x=spy_pct.index, y=spy_pct,
            name="Buy & Hold", line=dict(color=COLORS["spy"], width=1.5, dash="dot"),
        ))
    fig.add_hline(y=0, line=dict(color="#aaa", dash="dash", width=1))
    return _apply(fig, "Strategy Returns Comparison (%)", 450)


def strategy_correlation_heatmap(corr_df: pd.DataFrame) -> go.Figure:
    """N×N correlation heatmap of strategy daily returns."""
    if corr_df.empty:
        return go.Figure()
    labels = [n.replace("_", " ").title() for n in corr_df.columns]
    text = [[f"{corr_df.iloc[i,j]:.2f}" for j in range(len(corr_df.columns))]
            for i in range(len(corr_df))]
    fig = go.Figure(go.Heatmap(
        z=corr_df.values, x=labels, y=labels,
        text=text, texttemplate="%{text}",
        colorscale="RdBu", zmid=0, zmin=-1, zmax=1,
        colorbar=dict(title="r", thickness=12),
    ))
    n = len(corr_df)
    fig.update_layout(
        **_LAYOUT, title="Strategy Return Correlations",
        height=max(350, 80 * n), xaxis=dict(tickangle=-35),
    )
    return fig


def rolling_metric_per_strategy(
    returns_dict: dict,
    metric: str = "sharpe",
    window: int = 60,
) -> go.Figure:
    """Rolling Sharpe or Sortino per strategy on one chart."""
    from alan_trader.risk.metrics import rolling_sharpe as _rs, rolling_sortino as _rso
    fig = go.Figure()
    for i, (name, rets) in enumerate(returns_dict.items()):
        rets = rets.dropna()
        rets.index = pd.to_datetime(rets.index)
        series = _rs(rets, window) if metric == "sharpe" else _rso(rets, window)
        color = _STRATEGY_COLORS[i % len(_STRATEGY_COLORS)]
        fig.add_trace(go.Scatter(
            x=series.index, y=series,
            name=name.replace("_", " ").title(),
            line=dict(color=color, width=1.8),
        ))
    fig.add_hline(y=0, line=dict(color="#888", dash="dash", width=1))
    fig.add_hline(y=1, line=dict(color=COLORS["bull"], dash="dot", width=1))
    label = "Sharpe" if metric == "sharpe" else "Sortino"
    return _apply(fig, f"Rolling {window}-Day {label} by Strategy", 380)


def kelly_weights_bar(weights: dict, max_weight: float = 0.40) -> go.Figure:
    """Horizontal bar showing Kelly weight per strategy."""
    names  = [n.replace("_", " ").title() for n in weights.keys()]
    vals   = [v * 100 for v in weights.values()]
    colors = [COLORS["bull"] if v / 100 < max_weight else "#ffa726" for v in vals]
    fig = go.Figure(go.Bar(
        x=vals, y=names, orientation="h",
        marker_color=colors,
        text=[f"{v:.1f}%" for v in vals], textposition="inside",
    ))
    fig.add_vline(x=max_weight * 100, line=dict(color="#ef5350", dash="dash"),
                  annotation_text="Max weight", annotation_position="top right")
    return _apply(fig, "Kelly Position Weights", max(280, 60 + 45 * len(weights)))


def var_cvar_bar(metrics_by_strategy: dict) -> go.Figure:
    """Grouped VaR 95% / CVaR 95% bars per strategy."""
    names   = [n.replace("_", " ").title() for n in metrics_by_strategy.keys()]
    var_95  = [abs(m.get("var_95_pct", 0)) for m in metrics_by_strategy.values()]
    cvar_95 = [abs(m.get("cvar_95_pct", 0)) for m in metrics_by_strategy.values()]
    fig = go.Figure()
    fig.add_trace(go.Bar(name="VaR 95%",  x=names, y=var_95,
                         marker_color=COLORS["equity"], opacity=0.85))
    fig.add_trace(go.Bar(name="CVaR 95%", x=names, y=cvar_95,
                         marker_color=COLORS["bear"],   opacity=0.85))
    fig.update_layout(barmode="group")
    return _apply(fig, "Value-at-Risk & CVaR by Strategy (%)", 360)


def strategy_metrics_table(metrics_by_strategy: dict) -> go.Figure:
    """Table of key metrics across all strategies."""
    if not metrics_by_strategy:
        return go.Figure()
    key_metrics = ["total_return_pct", "sharpe", "sortino", "calmar",
                   "max_drawdown_pct", "var_95_pct", "win_rate_pct", "profit_factor"]
    names = list(metrics_by_strategy.keys())
    rows  = []
    for m_name in key_metrics:
        row = [m_name.replace("_", " ").title()]
        for s in names:
            v = metrics_by_strategy[s].get(m_name)
            row.append(f"{v:.2f}" if v is not None else "—")
        rows.append(row)
    header_vals = ["Metric"] + [n.replace("_", " ").title() for n in names]
    fig = go.Figure(go.Table(
        header=dict(values=header_vals, fill_color="#1e2130",
                    font=dict(color="#e0e0e0", size=12), align="center",
                    line=dict(color="#2e3450")),
        cells=dict(values=list(zip(*rows)),
                   fill_color=[["#161b27"] * len(rows)] + [["#0e1117"] * len(rows)] * len(names),
                   font=dict(color="#e0e0e0", size=11), align="center",
                   line=dict(color="#1e2130")),
    ))
    fig.update_layout(**_LAYOUT, title="Strategy Metrics Comparison", height=380)
    return fig


def portfolio_allocation_area(rolling_weights_df: pd.DataFrame) -> go.Figure:
    """Stacked area chart of strategy weights over time."""
    if rolling_weights_df.empty:
        return go.Figure()
    fig = go.Figure()
    for i, col in enumerate(rolling_weights_df.columns):
        color = _STRATEGY_COLORS[i % len(_STRATEGY_COLORS)]
        fig.add_trace(go.Scatter(
            x=rolling_weights_df.index, y=rolling_weights_df[col] * 100,
            name=col.replace("_", " ").title(),
            stackgroup="one",
            line=dict(color=color, width=0.5),
        ))
    return _apply(fig, "Portfolio Allocation Over Time (%)", 360)


def return_distribution_with_var(
    returns: pd.Series,
    var_95: float,
    cvar_95: float,
    label: str = "Portfolio",
) -> go.Figure:
    """Histogram of daily returns with normal curve, VaR and CVaR lines."""
    from scipy.stats import norm
    r = returns.dropna()
    mu, sigma = float(r.mean()), float(r.std())
    x = np.linspace(r.min(), r.max(), 300)
    normal_y = norm.pdf(x, mu, sigma) * len(r) * (r.max() - r.min()) / 50
    fig = go.Figure()
    fig.add_trace(go.Histogram(x=r * 100, nbinsx=60, name=label,
                               marker_color=COLORS["equity"], opacity=0.7))
    fig.add_trace(go.Scatter(x=x * 100, y=normal_y, name="Normal",
                             line=dict(color="#ffa726", width=2, dash="dot")))
    fig.add_vline(x=var_95 * 100,  line=dict(color=COLORS["bear"],  dash="dash"),
                  annotation_text=f"VaR {var_95*100:.2f}%")
    fig.add_vline(x=cvar_95 * 100, line=dict(color="#ff8f00", dash="dot"),
                  annotation_text=f"CVaR {cvar_95*100:.2f}%")
    return _apply(fig, f"Return Distribution — {label}", 360)


def max_drawdown_comparison(metrics_by_strategy: dict) -> go.Figure:
    """Horizontal bar: max drawdown per strategy."""
    data = {k: abs(m.get("max_drawdown_pct", 0)) for k, m in metrics_by_strategy.items()}
    data = dict(sorted(data.items(), key=lambda x: -x[1]))
    names  = [n.replace("_", " ").title() for n in data.keys()]
    values = list(data.values())
    fig = go.Figure(go.Bar(
        x=values, y=names, orientation="h",
        marker=dict(color=values,
                    colorscale=[[0, COLORS["bull"]], [1, COLORS["bear"]]],
                    showscale=False),
        text=[f"{v:.1f}%" for v in values], textposition="inside",
    ))
    return _apply(fig, "Max Drawdown by Strategy (%)", max(280, 60 + 45 * len(data)))


# ============================================================
# MARKET DATA CHARTS
# ============================================================

def candlestick_chart(bars_df: pd.DataFrame, ticker: str = "") -> go.Figure:
    """
    OHLCV candlestick with volume bars below.
    bars_df must have columns: date (or DatetimeIndex), open, high, low, close, volume.
    """
    df = bars_df.copy()
    if "date" not in df.columns:
        df = df.reset_index().rename(columns={"index": "date"})
    df["date"] = pd.to_datetime(df["date"])

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.75, 0.25],
        vertical_spacing=0.02,
    )

    fig.add_trace(go.Candlestick(
        x=df["date"],
        open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        name=ticker or "Price",
        increasing_line_color=COLORS["bull"],
        decreasing_line_color=COLORS["bear"],
        increasing_fillcolor=COLORS["bull"],
        decreasing_fillcolor=COLORS["bear"],
    ), row=1, col=1)

    colors = [COLORS["bull"] if c >= o else COLORS["bear"]
              for c, o in zip(df["close"], df["open"])]
    if "volume" in df.columns:
        fig.add_trace(go.Bar(
            x=df["date"], y=df["volume"], name="Volume",
            marker_color=colors, opacity=0.6,
        ), row=2, col=1)

    fig.update_layout(
        **_LAYOUT,
        title=f"{ticker} — Price History" if ticker else "Price History",
        height=480,
        xaxis_rangeslider_visible=False,
        showlegend=False,
    )
    fig.update_yaxes(gridcolor=COLORS["grid"])
    fig.update_xaxes(gridcolor=COLORS["grid"])
    return fig


def vol_surface_3d(
    strikes: np.ndarray,
    dtes: np.ndarray,
    iv_matrix: np.ndarray,
) -> go.Figure:
    """
    Pure wireframe mesh vol surface.
    No filled surface — only grid lines and vertex markers, both coloured by IV.
    """
    import plotly.colors as pc

    z      = iv_matrix * 100          # convert to %
    z_min  = float(z.min())
    z_max  = float(z.max())

    def _line_color(val: float) -> str:
        """Map a scalar IV value to a Plasma hex colour."""
        t = (val - z_min) / (z_max - z_min) if z_max > z_min else 0.5
        return pc.sample_colorscale("Plasma", [float(np.clip(t, 0, 1))])[0]

    fig = go.Figure()

    # ── grid lines along strike axis (one line per DTE row) ─────────────────
    for i, dte in enumerate(dtes):
        fig.add_trace(go.Scatter3d(
            x=strikes.tolist(),
            y=[float(dte)] * len(strikes),
            z=z[i].tolist(),
            mode="lines",
            line=dict(color=_line_color(float(z[i].mean())), width=3),
            showlegend=False,
            hovertemplate=(
                f"DTE {int(dte)}d — "
                "Strike $%{x:.0f} — IV %{z:.1f}%<extra></extra>"
            ),
        ))

    # ── grid lines along DTE axis (one line per strike column) ──────────────
    for j, strike in enumerate(strikes):
        fig.add_trace(go.Scatter3d(
            x=[float(strike)] * len(dtes),
            y=dtes.tolist(),
            z=z[:, j].tolist(),
            mode="lines",
            line=dict(color=_line_color(float(z[:, j].mean())), width=3),
            showlegend=False,
            hovertemplate=(
                f"Strike ${strike:.0f} — "
                "DTE %{y}d — IV %{z:.1f}%<extra></extra>"
            ),
        ))

    # ── vertex markers (grid nodes, tiny dots coloured by IV) ───────────────
    xv, yv, zv, cv = [], [], [], []
    for i in range(len(dtes)):
        for j in range(len(strikes)):
            xv.append(float(strikes[j]))
            yv.append(float(dtes[i]))
            zv.append(float(z[i, j]))
            cv.append(float(z[i, j]))

    fig.add_trace(go.Scatter3d(
        x=xv, y=yv, z=zv,
        mode="markers",
        marker=dict(
            size=4,
            color=cv,
            colorscale="Plasma",
            cmin=z_min, cmax=z_max,
            showscale=True,
            colorbar=dict(
                title=dict(text="IV %", font=dict(color="#e0e0e0", size=12)),
                thickness=14, len=0.7,
                tickfont=dict(color="#e0e0e0", size=11),
            ),
        ),
        showlegend=False,
        hovertemplate="Strike $%{x:.0f} — DTE %{y}d — IV %{z:.1f}%<extra></extra>",
    ))

    # ── layout ───────────────────────────────────────────────────────────────
    _ax = dict(
        gridcolor="#2a3050", backgroundcolor="#0c1020",
        color="#e0e0e0", showbackground=True,
        tickfont=dict(color="#c0c8d8", size=10),
    )
    fig.update_layout(
        paper_bgcolor="#0e1117",
        font=dict(color="#e0e0e0", family="monospace"),
        title=dict(text="Volatility Surface — Wireframe", font=dict(size=15, color="#e0e0e0")),
        scene=dict(
            xaxis=dict(**_ax, title=dict(text="Strike ($)", font=dict(color="#e0e0e0"))),
            yaxis=dict(**_ax, title=dict(text="DTE",        font=dict(color="#e0e0e0"))),
            zaxis=dict(**_ax, title=dict(text="IV (%)",     font=dict(color="#e0e0e0"))),
            bgcolor="#0c1020",
            camera=dict(eye=dict(x=1.55, y=-1.55, z=0.85)),
            aspectmode="manual",
            aspectratio=dict(x=1.6, y=1.0, z=0.7),
        ),
        height=880,
        margin=dict(l=0, r=0, t=50, b=0),
    )
    return fig


def iv_smile(smile_df: pd.DataFrame) -> go.Figure:
    """IV smile across strikes for multiple expirations."""
    colors = ["#5c6bc0", "#26a69a", "#ffa726", "#ef5350"]
    fig = go.Figure()
    for i, (dte, grp) in enumerate(smile_df.groupby("dte")):
        fig.add_trace(go.Scatter(
            x=grp["strike"], y=grp["iv"] * 100,
            name=f"{dte} DTE",
            line=dict(color=colors[i % len(colors)], width=2),
            mode="lines+markers",
            marker=dict(size=5),
        ))
    return _apply(fig, "Implied Volatility Smile (%)", 380)


def top_movers_bar(movers_df: pd.DataFrame, ticker: str = "") -> go.Figure:
    """Horizontal bar chart of top gainers/losers for the selected ticker's universe."""
    df = pd.concat([movers_df.head(5), movers_df.tail(5)]).sort_values("change_pct")
    colors = [COLORS["bull"] if v >= 0 else COLORS["bear"] for v in df["change_pct"]]
    # Highlight the primary ticker
    colors_final = [
        "#ffa726" if row["ticker"] == ticker.upper() else c
        for (_, row), c in zip(df.iterrows(), colors)
    ]
    fig = go.Figure(go.Bar(
        x=df["change_pct"],
        y=df["ticker"],
        orientation="h",
        marker_color=colors_final,
        text=[f"{v:+.2f}%" for v in df["change_pct"]],
        textposition="outside",
    ))
    fig.add_vline(x=0, line=dict(color="#aaa", width=1))
    title = f"Top Movers — {ticker} Universe (%)" if ticker else "Top Movers (%)"
    return _apply(fig, title, 380)


def dealer_gex_bar(gex_df: pd.DataFrame, S: float = 500.0, ticker: str = "") -> go.Figure:
    """Dealer GEX bar chart (by strike) with spot price marker."""
    pos = gex_df["net_gex"] >= 0
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=gex_df.loc[pos,  "strike"], y=gex_df.loc[pos,  "net_gex"] / 1e6,
        name="Long Gamma (stabilising)", marker_color=COLORS["bull"],
    ))
    fig.add_trace(go.Bar(
        x=gex_df.loc[~pos, "strike"], y=gex_df.loc[~pos, "net_gex"] / 1e6,
        name="Short Gamma (destabilising)", marker_color=COLORS["bear"],
    ))
    label = ticker if ticker else "Spot"
    fig.add_vline(x=S, line=dict(color="#ffa726", dash="dash", width=2),
                  annotation_text=f"{label} ${S:.0f}",
                  annotation_font=dict(color="#ffa726"))
    fig.add_hline(y=0, line=dict(color="#aaa", width=1))
    fig.update_layout(barmode="relative")
    title = f"Dealer GEX — {ticker} by Strike ($M)" if ticker else "Dealer GEX by Strike ($M)"
    return _apply(fig, title, 400)


def rsi_macd_chart(momentum_df: pd.DataFrame, ticker: str = "") -> go.Figure:
    """3-panel chart: price, RSI-14, MACD (12/26/9)."""
    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        row_heights=[0.50, 0.25, 0.25],
        vertical_spacing=0.04,
        subplot_titles=(f"{ticker} Price" if ticker else "Price", "RSI (14)", "MACD (12/26/9)"),
    )

    # Price
    fig.add_trace(go.Scatter(
        x=momentum_df.index, y=momentum_df["close"],
        line=dict(color=COLORS["spy"], width=1.5), name=ticker or "Price",
    ), row=1, col=1)

    # RSI
    fig.add_trace(go.Scatter(
        x=momentum_df.index, y=momentum_df["rsi"],
        line=dict(color="#ab47bc", width=1.5), name="RSI",
    ), row=2, col=1)
    for level, color in [(70, COLORS["bear"]), (30, COLORS["bull"]), (50, "#888")]:
        fig.add_hline(y=level, line=dict(color=color, dash="dash", width=0.8), row=2, col=1)

    # MACD
    fig.add_trace(go.Scatter(
        x=momentum_df.index, y=momentum_df["macd_line"],
        line=dict(color="#42a5f5", width=1.5), name="MACD",
    ), row=3, col=1)
    fig.add_trace(go.Scatter(
        x=momentum_df.index, y=momentum_df["signal_line"],
        line=dict(color="#ffa726", width=1.2, dash="dash"), name="Signal",
    ), row=3, col=1)
    hist_colors = [
        COLORS["bull"] if v >= 0 else COLORS["bear"]
        for v in momentum_df["macd_histogram"].fillna(0)
    ]
    fig.add_trace(go.Bar(
        x=momentum_df.index, y=momentum_df["macd_histogram"],
        marker_color=hist_colors, name="Histogram", opacity=0.55,
    ), row=3, col=1)

    fig.update_layout(**_LAYOUT, height=580, showlegend=False)
    for row in [1, 2, 3]:
        fig.update_xaxes(gridcolor=COLORS["grid"], row=row, col=1)
        fig.update_yaxes(gridcolor=COLORS["grid"], row=row, col=1)
    return fig


# ── Training signal analysis charts ───────────────────────────────────────────

def signal_cumulative_pnl(samples_df: pd.DataFrame, spread_label: str = "") -> go.Figure:
    """
    Cumulative P&L over time from all model ENTER signals (test period).
    Each point = another trade taken; slope = edge per trade.
    """
    df = samples_df.copy()
    df["Trade Date"] = pd.to_datetime(df["Trade Date"])
    df = df.sort_values("Trade Date")
    df["cumulative"] = df["Profit / Loss"].cumsum()

    colors = [COLORS["bull"] if v >= 0 else COLORS["bear"] for v in df["Profit / Loss"]]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df["Trade Date"], y=df["Profit / Loss"],
        marker_color=colors, opacity=0.5, name="Trade P&L",
    ))
    fig.add_trace(go.Scatter(
        x=df["Trade Date"], y=df["cumulative"],
        mode="lines", line=dict(color=COLORS["equity"], width=2),
        name="Cumulative P&L",
    ))
    fig.add_hline(y=0, line_color=COLORS["neutral"], line_dash="dot", line_width=1)

    title = f"Cumulative P&L — {spread_label} signals" if spread_label else "Cumulative P&L"
    fig.update_layout(
        **_LAYOUT, height=360,
        xaxis=dict(title="", gridcolor=COLORS["grid"]),
        yaxis=dict(title="$ per contract", gridcolor=COLORS["grid"], tickprefix="$"),
        legend=dict(orientation="h", y=1.05),
        title=dict(text=title, font=dict(size=13)),
    )
    return fig


def signal_winrate_by_confidence(samples_df: pd.DataFrame) -> go.Figure:
    """
    Win rate vs minimum confidence threshold.
    Shows: if you only took signals above X% confidence, what % were profitable?
    Also overlays number of trades remaining at each threshold.
    """
    thresholds = list(range(30, 96, 5))
    win_rates, trade_counts = [], []
    for t in thresholds:
        subset = samples_df[samples_df["Model Confidence"] >= t]
        if len(subset) == 0:
            win_rates.append(None)
            trade_counts.append(0)
        else:
            wins = subset["Result"].str.startswith("✅").sum()
            win_rates.append(round(wins / len(subset) * 100, 1))
            trade_counts.append(len(subset))

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(
        x=thresholds, y=win_rates,
        mode="lines+markers", name="Win Rate %",
        line=dict(color=COLORS["bull"], width=2),
        marker=dict(size=6),
    ), secondary_y=False)
    fig.add_trace(go.Bar(
        x=thresholds, y=trade_counts,
        name="# Trades", opacity=0.3,
        marker_color=COLORS["equity"],
    ), secondary_y=True)
    fig.add_hline(y=50, line_color=COLORS["neutral"], line_dash="dot",
                  line_width=1, secondary_y=False)

    fig.update_layout(
        **_LAYOUT, height=360,
        title=dict(text="Win Rate vs Confidence Threshold", font=dict(size=13)),
        xaxis=dict(title="Min Confidence %", gridcolor=COLORS["grid"], ticksuffix="%"),
        legend=dict(orientation="h", y=1.05),
    )
    fig.update_yaxes(title_text="Win Rate %", gridcolor=COLORS["grid"],
                     ticksuffix="%", secondary_y=False)
    fig.update_yaxes(title_text="# Trades", gridcolor=COLORS["grid"],
                     secondary_y=True)
    return fig


def signal_pnl_distribution(samples_df: pd.DataFrame) -> go.Figure:
    """
    Histogram of individual trade P&L outcomes.
    Quickly shows the shape: are wins bigger than losses? Is there fat-tail risk?
    """
    pnls = samples_df["Profit / Loss"].dropna()
    wins  = pnls[pnls >= 0]
    loses = pnls[pnls < 0]

    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=wins, name="Profitable",
        marker_color=COLORS["bull"], opacity=0.7,
        xbins=dict(size=10),
    ))
    fig.add_trace(go.Histogram(
        x=loses, name="Loss",
        marker_color=COLORS["bear"], opacity=0.7,
        xbins=dict(size=10),
    ))
    avg = pnls.mean()
    fig.add_vline(x=avg, line_color=COLORS["equity"], line_dash="dash", line_width=1.5,
                  annotation_text=f"Avg ${avg:.0f}", annotation_position="top right",
                  annotation_font_color=COLORS["text"])

    fig.update_layout(
        **_LAYOUT, height=360, barmode="overlay",
        title=dict(text="P&L Distribution per Trade ($/contract)", font=dict(size=13)),
        xaxis=dict(title="Profit / Loss ($/contract)", gridcolor=COLORS["grid"], tickprefix="$"),
        yaxis=dict(title="# Trades", gridcolor=COLORS["grid"]),
        legend=dict(orientation="h", y=1.05),
    )
    return fig
