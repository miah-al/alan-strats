"""
app/pages/strategies/performance.py — the Performance tab.

Replaces the previous "Performance analytics coming soon." placeholder, which
was an enabled, clickable, permanently empty tab on all 33 strategies.

Runs the strategy through the SAME production path as the Backtest tab
(`backtest_view._STRATEGY_CLASSES_BT` + `backtest_loaders.run_loaders_for`) and
renders the analytics the ranking work showed actually matter:

  * headline KPIs, each compared against SPY buy-and-hold on the same window
  * equity curve vs the benchmark
  * drawdown curve
  * calendar-year returns — the single best test of regime dependence
  * exit-reason and trade-P&L distribution

Deliberate reporting choices, learned the hard way this session:
  * CAGR is annualized over ELAPSED TIME (`risk.metrics.elapsed_years`), never
    row count — a sparse equity curve otherwise reports 101%/yr on a 14% gain.
  * Coverage is shown whenever the curve spans materially less than the
    requested window, so a partial-window CAGR is never read as comparable.
  * Exposure sits next to Sharpe, because a 2.1 Sharpe at 3% exposure and a 0.8
    at 100% are not the same proposition.
"""
from __future__ import annotations

import importlib
import logging
from datetime import date, timedelta

import dash_bootstrap_components as dbc
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import html, dcc, callback, Input, Output, State, no_update

from app import theme as T
from app.ui import components as C

logger = logging.getLogger(__name__)

# Matches scripts/rank_strategies.py so the tab and the ranking agree.
WARMUP_DAYS = 420
_DEF_FROM = "2021-01-01"
_DEF_TO = date.today().isoformat()      # the latest stored session is the natural end of the window


# ── layout ────────────────────────────────────────────────────────────────────

def _default_ticker(slug: str) -> str:
    try:
        from strategy_api.registry import get_ui
        return str(get_ui(slug).meta.get("default_ticker") or "SPY").upper()
    except Exception:
        return "SPY"


def _meta_default(slug: str, key: str, fallback):
    try:
        from strategy_api.registry import get_ui
        return get_ui(slug).meta.get(key) or fallback
    except Exception:
        return fallback


def performance_tab(slug: str) -> html.Div:
    """Controls + output area. Analytics render on demand (a backtest is slow)."""
    inp = {"backgroundColor": T.BG_ELEVATED, "border": f"1px solid {T.BORDER}",
           "color": T.TEXT_PRIMARY, "fontSize": "13px", "height": "34px"}

    def lbl(text):
        return html.Label(text, style={
            "color": T.TEXT_MUTED, "fontSize": "11px", "fontWeight": "600",
            "textTransform": "uppercase", "marginBottom": "4px",
            "display": "block"})

    controls = C.card([
        html.Div([
            html.Div([lbl("Ticker"),
                      dbc.Input(id=f"str-{slug}-perf-ticker", value=_default_ticker(slug),
                                style={**inp, "width": "100px"})]),
            html.Div([lbl("From"),
                      dbc.Input(id=f"str-{slug}-perf-from", value=_meta_default(slug, "default_from", _DEF_FROM),
                                type="text", style={**inp, "width": "130px"})]),
            html.Div([lbl("To"),
                      dbc.Input(id=f"str-{slug}-perf-to", value=_DEF_TO,
                                type="text", style={**inp, "width": "130px"})]),
            html.Div([lbl("Capital"),
                      dbc.Input(id=f"str-{slug}-perf-capital", value=_meta_default(slug, "default_capital", 100000),
                                type="number", style={**inp, "width": "120px"})]),
            html.Div([lbl(" "),
                      dbc.Button("Run analytics",
                                 id=f"str-{slug}-perf-run", n_clicks=0,
                                 color="primary", size="sm",
                                 style={"height": "34px"})]),
        ], style={"display": "flex", "gap": "12px", "alignItems": "flex-end",
                  "flexWrap": "wrap"}),
    ], pad="sm")

    return html.Div([
        controls,
        dcc.Loading(html.Div(id=f"str-{slug}-perf-output"),
                    type="default", color=T.ACCENT),
    ])


# ── analytics ─────────────────────────────────────────────────────────────────

def _plot_layout(title: str, height: int = 300) -> dict:
    return {
        "title": {"text": title, "font": {"size": 13, "color": T.TEXT_PRIMARY},
                  "x": 0.01},
        "paper_bgcolor": T.BG_CARD, "plot_bgcolor": T.BG_CARD,
        "font": {"color": T.TEXT_SEC, "size": 11},
        "margin": {"l": 56, "r": 18, "t": 38, "b": 36},
        "height": height,
        "xaxis": {"gridcolor": T.BORDER, "zeroline": False},
        "yaxis": {"gridcolor": T.BORDER, "zeroline": False},
        "legend": {"orientation": "h", "y": 1.12, "x": 0},
        "hovermode": "x unified",
    }


def _yearly_returns(equity: pd.Series) -> pd.Series:
    """Calendar-year return from an equity curve."""
    if equity.empty:
        return pd.Series(dtype=float)
    yearly = equity.resample("YE").last()
    first = equity.iloc[0]
    prev = pd.Series([first], index=[equity.index[0] - pd.Timedelta(days=1)])
    joined = pd.concat([prev, yearly])
    return (joined.pct_change().dropna() * 100).rename("ret")


def _drawdown(equity: pd.Series) -> pd.Series:
    return (equity / equity.cummax() - 1.0) * 100


def _tone(value: float, good_above: float) -> str:
    return "success" if value >= good_above else "danger"


def compute_performance(slug: str, ticker: str, from_date: str, to_date: str,
                        capital: float) -> dict:
    """
    Run the strategy through the production path and return everything the tab
    renders. Raises on failure so the caller can surface the real reason.
    """
    from db.client import get_engine, get_price_bars, get_vix_bars, get_macro_bars
    from app.pages.backtest_loaders import run_loaders_for
    from app.pages.strategies.backtest_view import _get_ui_params_for_slug
    from alan_trader.strategy_api.base import StubStrategy
    from alan_trader.strategy_api.registry import get_strategy
    from risk.metrics import compute_all_metrics

    strategy = get_strategy(slug)
    if isinstance(strategy, StubStrategy):
        raise ValueError(f"No implementation registered for {slug!r}.")

    fd, td = date.fromisoformat(from_date), date.fromisoformat(to_date)
    load_fd = fd - timedelta(days=WARMUP_DAYS)   # indicators warm up before fd

    engine = get_engine()
    bars = get_price_bars(engine, ticker, load_fd, td)
    if bars is None or bars.empty:
        raise ValueError(f"No price bars for {ticker} in {from_date} → {to_date}.")
    if "date" in bars.columns:
        bars = bars.set_index("date")
    bars.index = pd.to_datetime(bars.index)

    try:
        vix_df = get_vix_bars(engine, load_fd, td)
        rate_df = get_macro_bars(engine, load_fd, td)
    except Exception:
        vix_df, rate_df = pd.DataFrame(), pd.DataFrame()
    if not vix_df.empty:
        vix_df.index = pd.to_datetime(vix_df.index)
    if not rate_df.empty:
        rate_df.index = pd.to_datetime(rate_df.index)

    aux = {"vix": vix_df, "rate10y": rate_df, "ticker": ticker}
    extra, block = run_loaders_for(slug, engine, ticker, fd, td, price_data=bars)
    aux.update(extra)
    if block is not None:
        raise ValueError(
            f"{slug} is missing required data for this window — see the "
            f"Backtest tab for the loader's message.")

    params = {p["key"]: p["default"]
              for p in _get_ui_params_for_slug(slug) if "default" in p}
    result = strategy.backtest(bars, aux, starting_capital=float(capital), **params)

    equity = pd.Series(result.equity_curve).copy()
    equity.index = pd.to_datetime(equity.index)
    equity = equity[equity.index >= pd.Timestamp(fd)]
    if len(equity) < 3:
        raise ValueError("Backtest produced too few equity points to analyse.")

    trades = result.trades if result.trades is not None else pd.DataFrame()
    if not trades.empty:
        for col in ("exit_date", "entry_date"):
            if col in trades.columns:
                when = pd.to_datetime(trades[col], errors="coerce")
                trades = trades[when >= pd.Timestamp(fd)]
                break

    metrics = compute_all_metrics(equity, trades if not trades.empty else None)

    # Benchmark on the identical window.
    close = bars["close"] if "close" in bars.columns else bars.iloc[:, -1]
    close = close[close.index >= pd.Timestamp(fd)]
    bench_equity = float(capital) * (close / close.iloc[0])
    bench_metrics = compute_all_metrics(bench_equity)

    span_days = int((equity.index.max() - equity.index.min()).days)
    window_days = int((td - fd).days)

    return {
        "slug": slug, "ticker": ticker,
        "equity": equity, "bench_equity": bench_equity,
        "metrics": metrics, "bench_metrics": bench_metrics,
        "trades": trades,
        "coverage": (span_days / window_days) if window_days else 0.0,
        "span_days": span_days, "window_days": window_days,
        "from_date": from_date, "to_date": to_date,
    }


# ── rendering ─────────────────────────────────────────────────────────────────

def _kpis(perf: dict) -> html.Div:
    m, b = perf["metrics"], perf["bench_metrics"]

    def d(key):
        return float(m.get(key) or 0.0), float(b.get(key) or 0.0)

    cagr, cagr_b = d("annualized_return_pct")
    dd, dd_b = d("max_drawdown_pct")
    sharpe, sharpe_b = d("sharpe")

    items = [
        ("CAGR", f"{cagr:.2f}%", _tone(cagr, cagr_b), f"buy & hold {cagr_b:.2f}%"),
        ("Total return", f"{float(m.get('total_return_pct') or 0):.2f}%", "default",
         f"buy & hold {float(b.get('total_return_pct') or 0):.2f}%"),
        ("Max drawdown", f"{dd:.2f}%", _tone(dd, dd_b), f"buy & hold {dd_b:.2f}%"),
        ("Sharpe", f"{sharpe:.2f}", _tone(sharpe, sharpe_b),
         f"buy & hold {sharpe_b:.2f}"),
        ("Exposure", f"{float(m.get('exposure_pct') or 0):.1f}%", "default",
         "share of days deployed"),
        ("Profit factor", f"{float(m.get('profit_factor') or 0):.2f}", "default",
         f"win rate {float(m.get('win_rate_pct') or 0):.1f}%"),
        ("Trades", f"{int(m.get('num_trades') or 0)}", "default",
         "sample size"),
    ]
    return C.kpi_row(items)


def _warnings_panel(perf: dict) -> html.Div | None:
    """Surface the things that make a headline number untrustworthy."""
    notes = []
    m = perf["metrics"]
    n = int(m.get("num_trades") or 0)
    if 0 < n < 30:
        notes.append(f"Only {n} trades — too few to be statistically meaningful. "
                     f"Treat CAGR, Sharpe and profit factor as anecdotes.")
    if n == 0:
        notes.append("No trades in this window; every metric below is the "
                     "equity curve sitting flat.")
    if perf["coverage"] < 0.6 and perf["window_days"]:
        notes.append(
            f"The equity curve covers only {perf['span_days']}d of a "
            f"{perf['window_days']}d window ({perf['coverage']:.0%}). CAGR "
            f"annualizes that partial period — read total return instead.")
    pf = m.get("profit_factor")
    if pf in (float("inf"), None) and n > 5:
        notes.append("Profit factor is infinite — there are no losing trades at "
                     "all. Over this many trades that usually means losses are "
                     "not being realised, not that the strategy cannot lose.")
    if float(m.get("max_drawdown_pct") or 0) == 0.0 and n > 5:
        notes.append("Max drawdown is exactly zero, which normally means open "
                     "positions are never marked to market — the curve only "
                     "moves on close.")
    if not notes:
        return None
    return dbc.Alert(
        [html.Div("⚠ Read with care", style={"fontWeight": "700",
                                             "marginBottom": "6px"}),
         html.Ul([html.Li(t, style={"marginBottom": "3px"}) for t in notes],
                 style={"marginBottom": 0, "paddingLeft": "18px"})],
        color="warning", style={"fontSize": "12px"})


def _equity_chart(perf: dict) -> dcc.Graph:
    eq, bench = perf["equity"], perf["bench_equity"]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=eq.index, y=eq.values, name=perf["slug"],
                             line={"color": T.ACCENT, "width": 2}))
    fig.add_trace(go.Scatter(x=bench.index, y=bench.values,
                             name=f"{perf['ticker']} buy & hold",
                             line={"color": T.TEXT_MUTED, "width": 1.5,
                                   "dash": "dot"}))
    fig.update_layout(**_plot_layout("Equity curve vs buy & hold", 330))
    fig.update_yaxes(tickprefix="$")
    return dcc.Graph(figure=fig, config={"displayModeBar": False})


def _drawdown_chart(perf: dict) -> dcc.Graph:
    dd = _drawdown(perf["equity"])
    dd_b = _drawdown(perf["bench_equity"])
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=dd.index, y=dd.values, name=perf["slug"],
                             fill="tozeroy", line={"color": T.DANGER, "width": 1.5},
                             fillcolor="rgba(239,68,68,0.16)"))
    fig.add_trace(go.Scatter(x=dd_b.index, y=dd_b.values, name="buy & hold",
                             line={"color": T.TEXT_MUTED, "width": 1, "dash": "dot"}))
    fig.update_layout(**_plot_layout("Drawdown", 240))
    fig.update_yaxes(ticksuffix="%")
    return dcc.Graph(figure=fig, config={"displayModeBar": False})


def _yearly_chart(perf: dict) -> dcc.Graph:
    ys = _yearly_returns(perf["equity"])
    yb = _yearly_returns(perf["bench_equity"])
    years = [str(i.year) for i in ys.index]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=years, y=ys.values, name=perf["slug"],
                         marker_color=[T.SUCCESS if v >= 0 else T.DANGER
                                       for v in ys.values]))
    fig.add_trace(go.Bar(x=[str(i.year) for i in yb.index], y=yb.values,
                         name="buy & hold",
                         marker_color="rgba(156,163,175,0.45)"))
    fig.update_layout(**_plot_layout("Calendar-year returns", 260))
    fig.update_layout(barmode="group")
    fig.update_yaxes(ticksuffix="%")
    return dcc.Graph(figure=fig, config={"displayModeBar": False})


def _trade_breakdown(perf: dict) -> html.Div:
    trades = perf["trades"]
    if trades is None or trades.empty or "pnl" not in trades.columns:
        return C.card(C.empty_state("No closed trades in this window.", icon="○"))

    pnl = pd.to_numeric(trades["pnl"], errors="coerce").dropna()
    fig = go.Figure(go.Histogram(x=pnl.values, nbinsx=30,
                                 marker_color=T.ACCENT, opacity=0.85))
    fig.update_layout(**_plot_layout("Trade P&L distribution", 240))
    fig.update_xaxes(tickprefix="$")

    rows = []
    if "exit_reason" in trades.columns:
        grp = trades.groupby("exit_reason")["pnl"].agg(["count", "sum", "mean"])
        grp = grp.sort_values("count", ascending=False)
        rows = [html.Tr([
            html.Td(str(idx)),
            html.Td(f"{int(r['count'])}", style={"textAlign": "right"}),
            html.Td(f"${r['sum']:,.0f}", style={
                "textAlign": "right",
                "color": T.SUCCESS if r["sum"] >= 0 else T.DANGER}),
            html.Td(f"${r['mean']:,.0f}", style={
                "textAlign": "right",
                "color": T.SUCCESS if r["mean"] >= 0 else T.DANGER}),
        ]) for idx, r in grp.iterrows()]

    table = html.Table([
        html.Thead(html.Tr([html.Th("Exit reason"), html.Th("Count"),
                            html.Th("Total P&L"), html.Th("Avg P&L")])),
        html.Tbody(rows),
    ], style={"width": "100%", "fontSize": "12px"}) if rows else html.Div()

    return html.Div([
        C.section("Trade distribution",
                  dcc.Graph(figure=fig, config={"displayModeBar": False})),
        C.section("Exits", table) if rows else html.Div(),
    ])


def render_performance(perf: dict) -> html.Div:
    blocks = [_kpis(perf)]
    warn = _warnings_panel(perf)
    if warn is not None:
        blocks.append(warn)
    blocks += [
        C.card(_equity_chart(perf)),
        C.card(_drawdown_chart(perf)),
        C.card(_yearly_chart(perf)),
        _trade_breakdown(perf),
        html.Div(
            f"Measured on real {perf['ticker']} data via the production backtest "
            f"path, {perf['from_date']} → {perf['to_date']}. Indicators warm up "
            f"on {WARMUP_DAYS} days of prior history, which is excluded from "
            f"every figure above.",
            style={"color": T.TEXT_MUTED, "fontSize": "11px",
                   "marginTop": "4px"}),
    ]
    return html.Div(blocks)


# ── callback registration ─────────────────────────────────────────────────────

def _make_performance_callback(slug: str):
    @callback(
        Output(f"str-{slug}-perf-output", "children"),
        Input(f"str-{slug}-perf-run", "n_clicks"),
        State(f"str-{slug}-perf-ticker", "value"),
        State(f"str-{slug}-perf-from", "value"),
        State(f"str-{slug}-perf-to", "value"),
        State(f"str-{slug}-perf-capital", "value"),
        prevent_initial_call=True,
    )
    def _run_performance(n, ticker, from_date, to_date, capital):
        if not n:
            return no_update
        try:
            perf = compute_performance(
                slug,
                (ticker or "SPY").upper().strip(),
                from_date or _DEF_FROM,
                to_date or _DEF_TO,
                float(capital or 100_000),
            )
        except Exception as exc:
            logger.exception(f"performance failed for {slug}")
            return dbc.Alert(f"Could not compute performance: {exc}",
                             color="danger", style={"fontSize": "12px"})
        try:
            return render_performance(perf)
        except Exception as exc:
            logger.exception(f"performance render failed for {slug}")
            return dbc.Alert(f"Error rendering analytics: {exc}", color="danger")

    _run_performance.__name__ = f"_run_performance_{slug}"
    return _run_performance


def register_performance_callbacks(slugs) -> None:
    for slug in slugs:
        _make_performance_callback(slug)
