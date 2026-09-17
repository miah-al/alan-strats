"""
app/pages/strategies/backtest_view.py — backtest run callbacks + result rendering.

Holds the result renderer (_render_backtest_results), the UI-param resolver
(_get_ui_params_for_slug, also used by the layout's backtest tab) and
_make_backtest_callback. Importing this module registers a backtest callback set
per visible strategy. Strategies are instantiated through the plugin registry;
strategy-specific result panels come from `StrategyUI.backtest_panels`.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta as _timedelta

import pandas as _pd
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from dash_mantine_react_table import DashMantineReactTable as _MRT
from dash import html, dcc, callback, Input, Output, State, no_update

from app import theme as T
from app.ui import components as C
from alan_trader.strategy_api.base import StubStrategy
from alan_trader.strategy_api.registry import get_strategy, get_ui
from app.pages.strategies.registry import slugs as _slugs

logger = logging.getLogger(__name__)

# Map the legacy raw-colour tile API onto the design-system metric_card tones.
_TONE = {T.SUCCESS: "success", T.DANGER: "danger", T.WARNING: "warning",
         T.ACCENT: "accent", T.TEXT_PRIMARY: "default", T.TEXT_MUTED: "muted"}


# Matches scripts/rank_strategies.py and performance.py so all three agree.
_WARMUP_DAYS = 420


def _get_ui_params_for_slug(slug: str) -> list:
    """Instantiate the strategy and return its get_backtest_ui_params()."""
    try:
        strategy = get_strategy(slug)
        if isinstance(strategy, StubStrategy):
            return []
        return list(strategy.get_backtest_ui_params() or [])
    except Exception:
        logger.exception(f"{slug}: get_backtest_ui_params failed")
        return []


#: The last backtest's trades per strategy, served by the "Download CSV" button.
_LAST_TRADES: dict[str, "pd.DataFrame"] = {}


def _render_backtest_results(result, slug: str) -> html.Div:
    """Build the full results display: metric cards, equity curve, monthly heatmap, trades table."""
    m = result.metrics

    # ── 6 metric cards ────────────────────────────────────────────────────────
    def _card(label: str, value: str, color: str = T.TEXT_PRIMARY) -> html.Div:
        return C.metric_card(label, value, _TONE.get(color, "default"))

    total_ret  = m.get("total_return_pct", 0.0)
    sharpe     = m.get("sharpe", 0.0)
    max_dd     = m.get("max_drawdown_pct", 0.0)
    win_rate   = m.get("win_rate_pct", 0.0)
    pf         = m.get("profit_factor", 0.0)
    n_trades   = m.get("num_trades", 0)

    metric_row = html.Div([
        _card("Total Return",  f"{total_ret:+.2f}%",
              T.SUCCESS if total_ret >= 0 else T.DANGER),
        _card("Sharpe Ratio",  f"{sharpe:.3f}",
              T.SUCCESS if sharpe >= 1.0 else T.WARNING if sharpe >= 0 else T.DANGER),
        _card("Max Drawdown",  f"{max_dd:.2f}%",
              T.DANGER if max_dd < -15 else T.WARNING if max_dd < -5 else T.SUCCESS),
        _card("Win Rate",      f"{win_rate:.1f}%",
              T.SUCCESS if win_rate >= 55 else T.WARNING if win_rate >= 40 else T.DANGER),
        _card("Profit Factor", f"{pf:.3f}" if pf != float("inf") else "∞",
              T.SUCCESS if pf >= 1.5 else T.WARNING if pf >= 1.0 else T.DANGER),
        _card("Total Trades",  str(n_trades)),
        # a strategy can add cards in its own units (dollars per lot, sessions, worst day) via result.extra["cards"]
        *[_card(str(c.get("label", "")), str(c.get("value", "")), {"good": T.SUCCESS, "bad": T.DANGER, "warn": T.WARNING}.get(c.get("tone"), T.TEXT_PRIMARY))
          for c in ((getattr(result, "extra", None) or {}).get("cards") or []) if isinstance(c, dict)],
    ], style={"display": "flex", "gap": "10px", "flexWrap": "wrap", "marginBottom": "16px"})

    # ── Equity curve + Capital Deployment ─────────────────────────────────────
    eq        = result.equity_curve
    cash_s    = result.extra.get("cash_curve",   _pd.Series(dtype=float))
    start_cap = float(result.extra.get("starting_capital") or (eq.iloc[0] if not eq.empty else 100_000))

    has_breakdown = not cash_s.empty and not eq.empty

    if has_breakdown:
        # % of capital deployed = (equity - cash) / equity × 100
        deploy_pct = ((eq - cash_s) / eq * 100).clip(lower=0)
        fig_eq = make_subplots(
            rows=2, cols=1,
            row_heights=[0.72, 0.28],
            shared_xaxes=True,
            vertical_spacing=0.04,
            subplot_titles=("Equity (MTM)", "% Capital Deployed"),
        )
    else:
        fig_eq = make_subplots(rows=1, cols=1)

    # ── Row 1: equity + drawdown shading ──────────────────────────────────────
    roll_max = eq.cummax()
    fig_eq.add_trace(go.Scatter(
        x=list(eq.index), y=list(roll_max),
        line=dict(width=0), showlegend=False, hoverinfo="skip", name="peak",
    ), row=1, col=1)
    fig_eq.add_trace(go.Scatter(
        x=list(eq.index), y=list(eq),
        fill="tonexty", fillcolor="rgba(239,68,68,0.12)",
        line=dict(width=0), showlegend=False, hoverinfo="skip", name="dd_fill",
    ), row=1, col=1)
    fig_eq.add_trace(go.Scatter(
        x=list(eq.index), y=list(eq),
        line=dict(color=T.ACCENT, width=2),
        name="Equity",
        hovertemplate="%{x|%Y-%m-%d}  $%{y:,.0f}<extra>Equity (MTM)</extra>",
    ), row=1, col=1)
    fig_eq.add_hline(
        y=start_cap, row=1,
        line=dict(color=T.BORDER_BRT, width=1, dash="dot"),
        annotation_text=f"Start ${start_cap:,.0f}",
        annotation_position="bottom right",
        annotation_font_color=T.TEXT_MUTED,
        annotation_font_size=10,
    )

    # ── Row 2: % capital deployed (filled area) ────────────────────────────────
    if has_breakdown:
        fig_eq.add_trace(go.Scatter(
            x=list(deploy_pct.index), y=list(deploy_pct),
            fill="tozeroy",
            fillcolor="rgba(245,158,11,0.25)",
            line=dict(color="#f59e0b", width=1.5),
            name="Deployed %",
            hovertemplate="%{x|%Y-%m-%d}  %{y:.1f}%<extra>Deployed</extra>",
        ), row=2, col=1)
        fig_eq.add_hline(y=50, row=2,
            line=dict(color=T.BORDER_BRT, width=1, dash="dot"),
            annotation_text="50%", annotation_position="bottom right",
            annotation_font_color=T.TEXT_MUTED, annotation_font_size=10,
        )

    fig_eq.update_layout(
        paper_bgcolor=T.BG_CARD, plot_bgcolor=T.BG_CARD,
        font=dict(color=T.TEXT_PRIMARY, family="Inter, sans-serif", size=12),
        height=430, margin=dict(l=10, r=10, t=30, b=10),
        showlegend=False,
        template="plotly_dark",
    )
    fig_eq.update_xaxes(gridcolor=T.BORDER, showgrid=True)
    fig_eq.update_yaxes(gridcolor=T.BORDER, showgrid=True)
    fig_eq.update_yaxes(tickformat="$,.0f", row=1, col=1)
    fig_eq.update_yaxes(tickformat=".0f", ticksuffix="%", range=[0, 105], row=2, col=1)
    # Style subplot titles
    for ann in fig_eq.layout.annotations:
        ann.font.color = T.TEXT_MUTED
        ann.font.size  = 11

    equity_chart = C.card([
        dcc.Graph(figure=fig_eq, config={"displayModeBar": False}),
    ])

    # ── Monthly returns heatmap ───────────────────────────────────────────────
    dr = result.daily_returns
    heatmap_card = html.Div()
    if not dr.empty:
        try:
            dr_idx = _pd.to_datetime(dr.index)
            dr_df  = _pd.DataFrame({
                "year":  dr_idx.year,
                "month": dr_idx.month,
                "ret":   dr.values,
            })
            # Aggregate to monthly
            monthly = (dr_df.groupby(["year", "month"])["ret"]
                       .apply(lambda x: (1 + x).prod() - 1)
                       .reset_index())
            pivot = monthly.pivot(index="year", columns="month", values="ret").fillna(0)
            pivot = pivot.loc[(pivot != 0).any(axis=1)] if (pivot != 0).any(axis=1).any() else pivot   # years with no sessions add nothing
            _zmax = float(max(abs(pivot.values.min()), abs(pivot.values.max()), 1e-9) * 100)                # symmetric scale on the data, not a fixed +-50%
            month_labels = ["Jan","Feb","Mar","Apr","May","Jun",
                            "Jul","Aug","Sep","Oct","Nov","Dec"]
            col_labels = [month_labels[c - 1] for c in pivot.columns]

            fig_heat = go.Figure(go.Heatmap(
                z=(pivot.values * 100).tolist(),
                x=col_labels,
                y=[str(y) for y in pivot.index],
                colorscale="RdYlGn",
                zmid=0, zmin=-_zmax, zmax=_zmax,
                hovertemplate="%{y} %{x}: %{z:.2f}%<extra></extra>",
                colorbar=dict(
                    tickformat=".1f",
                    ticksuffix="%",
                    thickness=12,
                    len=0.8,
                    title=dict(text="%", side="right"),
                ),
            ))
            fig_heat.update_layout(
                paper_bgcolor=T.BG_CARD, plot_bgcolor=T.BG_CARD,
                font=dict(color=T.TEXT_PRIMARY, family="Inter, sans-serif", size=11),
                height=max(180, 40 + 35 * len(pivot)),
                margin=dict(l=10, r=60, t=30, b=10),
                title=dict(text="Monthly return, % of capital (colour scale fits the data)", font=dict(size=12, color=T.TEXT_MUTED)),
                xaxis=dict(side="top"),
                template="plotly_dark",
            )
            heatmap_card = C.card([
                dcc.Graph(figure=fig_heat, config={"displayModeBar": False}),
            ])
        except Exception:
            pass

    # ── Trades table ──────────────────────────────────────────────────────────
    trades_card = html.Div()
    trades_df = result.trades
    if trades_df is not None and not trades_df.empty:
        # Column config: field → (headerName, width, cellStyle)
        _COL_CONFIG = {
            "entry_date":      ("Entry",          105, None),
            "exit_date":       ("Exit",           105, None),
            "pnl":             ("P&L",            100, {"function": "params.value >= 0 ? {'color':'#10b981','fontWeight':'600'} : {'color':'#ef4444','fontWeight':'600'}"}),
            "pnl_pct":         ("P&L %",           90, {"function": "params.value >= 0 ? {'color':'#10b981'} : {'color':'#ef4444'}"}),
            "dte_held":        ("DTE Held",         90, None),
            "hold_days":       ("Days Held",        95, None),
            "exit_reason":     ("Exit Reason",     130, None),
            "contracts":       ("Contracts",       100, None),
            "credit":          ("Credit",           90, None),
            "call_short_k":    ("Call Short",      110, None),
            "call_long_k":     ("Call Long",       110, None),
            "put_short_k":     ("Put Short",       110, None),
            "put_long_k":      ("Put Long",        110, None),
            "margin_reserved": ("Margin Rsv",      115, None),
            "ticker":          ("Ticker",          100, None),
            "status":          ("Status",          100, None),
        }
        # Columns to skip (redundant or internal)
        _SKIP = {"winner", "free_capital"}

        # Build ordered display list: known preferred first, then any extras
        _preferred_order = ["entry_date", "exit_date", "pnl", "pnl_pct", "dte_held",
                            "hold_days", "exit_reason", "contracts", "credit",
                            "call_short_k", "call_long_k", "put_short_k", "put_long_k",
                            "margin_reserved", "ticker", "status"]
        cols_lower = {c.lower(): c for c in trades_df.columns}
        display_cols = []
        _declared = (getattr(result, "extra", None) or {}).get("trade_columns") or []       # [(field, header), ...] in display order
        for field, header in _declared:
            if field in trades_df.columns and field not in display_cols:
                display_cols.append(field); _COL_CONFIG[field.lower()] = (header, 100, None)
        for key in _preferred_order:
            orig = cols_lower.get(key)
            if orig and orig not in _SKIP:
                display_cols.append(orig)
        for orig in trades_df.columns:
            if orig not in display_cols and orig not in _SKIP:
                display_cols.append(orig)

        col_defs = []
        for orig in display_cols:
            key = orig.lower()
            header, width, style = _COL_CONFIG.get(key, (orig.replace("_", " ").title(), 100, None))
            cd = {
                "field":       orig,
                "headerName":  header,
                "width":       width,
                "resizable":   True,
                "sortable":    True,
                "filter":      True,
            }
            if style:
                cd["cellStyle"] = style
            col_defs.append(cd)

        tbl_height = min(500, 80 + len(trades_df) * 38)
        # Convert column defs to MRT format on the fly
        mrt_cols = [
            {"accessorKey": c["field"], "header": c.get("headerName", c["field"])}
            for c in col_defs
        ]
        trades_grid = _MRT(
            data=trades_df[display_cols].astype(str).to_dict("records"),
            columns=mrt_cols,
            mrtProps={
                "enableColumnFilters": True,
                "enableGlobalFilter":  True,
                "enableSorting":       True,
                "enableDensityToggle": True,
                "enableColumnOrdering":False,
                "enablePagination":    True,
                "layoutMode":          "grid",
                "initialState": {
                    "density": "xs",
                    "pagination": {"pageIndex": 0, "pageSize": 25},
                },
                "defaultColumn": {"minSize": 80, "maxSize": 400, "size": 130},
                "mantineTableProps": {
                    "highlightOnHover": True,
                    "withTableBorder":  False,
                    "withColumnBorders":False,
                    "horizontalSpacing":"md",
                    "verticalSpacing":  "xs",
                },
                "mantineTableContainerProps": {
                    "style": {"maxHeight": f"{tbl_height}px", "width": "100%"},
                },
                "mantinePaperProps": {
                    "shadow": "0", "withBorder": False,
                    "style": {"backgroundColor": "transparent", "width": "100%"},
                },
            },
            mantineProviderProps={
                "theme": {
                    "colorScheme": "dark",
                    "primaryColor": "indigo",
                    "fontFamily": "Inter, system-ui, sans-serif",
                },
            },
        )
        _LAST_TRADES[slug] = trades_df.copy()
        export_bar = html.Div([
            dbc.Button("⬇ Download CSV", id=f"str-{slug}-bt-trades-btn", size="sm", outline=True, color="secondary", n_clicks=0),
            html.Span(f"  {len(trades_df)} trades, every column the strategy records",
                      style={"color": T.TEXT_MUTED, "fontSize": "11px", "marginLeft": "10px"}),
            dcc.Download(id=f"str-{slug}-bt-trades-dl"),
        ], style={"marginBottom": "6px"})
        trades_card = C.section("Trades", [export_bar, trades_grid])

    # ── Strategy-specific panels ─────────────────────────────────────────────
    try:
        extra_panels = [p for p in (get_ui(slug).backtest_panels(result) or []) if p is not None]
    except Exception:
        logger.exception(f"{slug}: backtest_panels failed")
        extra_panels = []

    return html.Div([
        metric_row,
        equity_chart,
        *extra_panels,
        heatmap_card,
        trades_card,
    ])


def _make_backtest_callback(slug: str):
    """Register a backtest run callback for the given strategy slug."""
    ui_params = _get_ui_params_for_slug(slug)
    results_id = f"str-{slug}-bt-results"
    run_id     = f"str-{slug}-bt-run"
    ticker_id  = f"str-{slug}-bt-ticker"
    from_id    = f"str-{slug}-bt-from"
    to_id      = f"str-{slug}-bt-to"
    capital_id = f"str-{slug}-bt-capital"
    param_ids  = [f"str-{slug}-bt-param-{p['key']}" for p in ui_params]

    # Build slider value display callbacks (one per param)
    for p in ui_params:
        key      = p["key"]
        val_id   = f"str-{slug}-bt-param-{key}-val"
        slider_id = f"str-{slug}-bt-param-{key}"

        @callback(
            Output(val_id, "children"),
            Input(slider_id, "value"),
        )
        def _update_val(v):
            if v is None:
                return ""
            # Only strip trailing zeros from true decimals, not integers like 30 → "3"
            if v == int(v):
                return str(int(v))
            return str(round(float(v), 4)).rstrip("0").rstrip(".")

        _update_val.__name__ = f"_bt_val_{slug}_{key}"

    @callback(
        Output(f"str-{slug}-bt-trades-dl", "data"),
        Input(f"str-{slug}-bt-trades-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def _download_trades(n):
        df = _LAST_TRADES.get(slug)
        if not n or df is None or df.empty:
            return no_update
        return dcc.send_data_frame(df.to_csv, f"{slug}_backtest_trades.csv", index=False)

    @callback(
        Output(results_id, "children"),
        Input(run_id, "n_clicks"),
        State(ticker_id, "value"),
        State(from_id, "value"),
        State(to_id, "value"),
        State(capital_id, "value"),
        *[State(pid, "value") for pid in param_ids],
        prevent_initial_call=True,
    )
    def _run_backtest(n, ticker, from_date, to_date, capital, *param_values):
        if not n:
            return no_update

        ticker     = (ticker or "SPY").upper().strip()
        from_date  = from_date  or "2022-01-01"
        to_date    = to_date    or date.today().isoformat()
        capital    = float(capital or 10_000)

        # ── Load price data ───────────────────────────────────────────────────
        try:
            from db.client import get_engine, get_vix_bars, get_macro_bars, get_price_bars
            engine = get_engine()
        except Exception as e:
            return dbc.Alert(
                f"Database not available — ensure DB connection is configured. ({e})",
                color="warning",
            )

        try:
            fd = date.fromisoformat(from_date)
            td = date.fromisoformat(to_date)
            # Load WARMUP_DAYS of history before the window so indicators are
            # live from bar one. Feeding a strategy only the reporting window
            # cripples long-lookback signals; without this the Backtest tab
            # disagreed with the Performance tab on identical inputs.
            price_data = get_price_bars(engine, ticker, fd - _timedelta(days=_WARMUP_DAYS), td)
        except Exception as e:
            return dbc.Alert(
                f"Error loading price data for {ticker}: {e}",
                color="danger",
            )

        if price_data is None or price_data.empty:
            return dbc.Alert(
                f"No price data found for {ticker} in {from_date} → {to_date}. "
                "Sync data first via Tools → Data Manager.",
                color="warning",
            )

        # Set date index
        if "date" in price_data.columns:
            price_data = price_data.set_index("date")
        price_data.index = _pd.to_datetime(price_data.index)

        # ── Load auxiliary data ───────────────────────────────────────────────
        try:
            vix_df  = get_vix_bars(engine, fd, td)
            rate_df = get_macro_bars(engine, fd, td)
        except Exception:
            vix_df  = _pd.DataFrame()
            rate_df = _pd.DataFrame()

        if not vix_df.empty:
            vix_df.index = _pd.to_datetime(vix_df.index)
        if not rate_df.empty:
            rate_df.index = _pd.to_datetime(rate_df.index)

        auxiliary_data = {"vix": vix_df, "rate10y": rate_df, "ticker": ticker,
                          "report_from": from_date, "report_to": to_date}   # the window the user asked for; bars before it are warm-up

        # ── Strategy-declared auxiliary-data loaders ──────────────────────────
        # Loader logic lives in app/pages/backtest_loaders.py — one pure
        # function per data type; the strategy declares which ones it needs.
        from app.pages.backtest_loaders import run_loaders_for
        _aux_extra, _block = run_loaders_for(
            slug, engine, ticker, fd, td, price_data=price_data,
        )
        auxiliary_data.update(_aux_extra)
        if _block is not None:
            return _block

        # ── Instantiate strategy + run backtest ───────────────────────────────
        try:
            strategy = get_strategy(slug)
            if isinstance(strategy, StubStrategy):
                return dbc.Alert(f"Strategy '{slug}' has no implementation registered.",
                                 color="danger")

            params = dict(zip([p["key"] for p in ui_params], param_values))
            result = strategy.backtest(
                price_data, auxiliary_data,
                starting_capital=capital,
                **params,
            )
        except NotImplementedError:
            return dbc.Alert(
                f"Strategy '{slug}' backtest is not yet implemented.",
                color="warning",
            )
        except Exception as e:
            logger.exception(f"Backtest error for {slug}: {e}")
            return dbc.Alert(f"Backtest error: {str(e)}", color="danger")

        # Score on the reporting window only — the warm-up informs the signal
        # but must not contribute to the metrics.
        try:
            _eq = _pd.Series(result.equity_curve).copy()
            _eq.index = _pd.to_datetime(_eq.index)
            _eq_win = _eq[_eq.index >= _pd.Timestamp(fd)]
            if len(_eq_win) > 2:
                from risk.metrics import compute_all_metrics as _cam
                _tr = result.trades
                if _tr is not None and not _tr.empty:
                    for _c in ("exit_date", "entry_date"):
                        if _c in _tr.columns:
                            _w = _pd.to_datetime(_tr[_c], errors="coerce")
                            _tr = _tr[_w >= _pd.Timestamp(fd)]
                            break
                result.equity_curve = _eq_win
                result.metrics = _cam(_eq_win, _tr if _tr is not None and not _tr.empty else None)
        except Exception:
            logger.exception(f"{slug}: window truncation failed; showing full-span metrics")

        # ── Render results ────────────────────────────────────────────────────
        try:
            return _render_backtest_results(result, slug)
        except Exception as e:
            logger.exception(f"Result render error for {slug}: {e}")
            return dbc.Alert(f"Error rendering results: {str(e)}", color="danger")

    _run_backtest.__name__ = f"_run_backtest_{slug}"
    return _run_backtest


# Register backtest callbacks for every visible strategy
for _slug in _slugs():
    _make_backtest_callback(_slug)
