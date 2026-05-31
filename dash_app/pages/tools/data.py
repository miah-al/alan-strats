"""
dash_app/pages/tools/data.py -- pure data/logic helpers for the Tools hub.

No Dash @callback functions live here. Pure helpers used by the tab builders and
callbacks: AG-Grid column/metric/badge helpers, the sync runner, coverage and
validation table builders, the risk computation, the Polygon client helper and
the Robinhood helpers, plus the sync-button registry constants.

Split verbatim from the original dash_app/pages/tools.py -- behaviour unchanged.
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from pathlib import Path

import dash_ag_grid as dag
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash import html, dcc, callback, Input, Output, State, no_update

from dash_app import theme as T, get_polygon_api_key
from dash_app.ui import tokens as D, components as C

logger = logging.getLogger(__name__)

_GUIDE_DIR = Path(__file__).parent.parent.parent / "guide_articles"
_COVERAGE_SYMBOLS = ["HOOD", "SPY", "QQQ", "AAPL", "TSLA", "MARA", "TLT"]
_PORTFOLIO_HISTORY = Path(__file__).parent.parent.parent / "portfolio_history.json"


def _col(field: str, flex: int = 1, width: int | None = None,
         min_width: int = 60, numeric: bool = False) -> dict:
    d: dict = {"field": field, "resizable": True, "sortable": True,
                "filter": True, "minWidth": min_width}
    if width:
        d["width"] = width
    else:
        d["flex"] = flex
    if numeric:
        d["type"] = "numericColumn"
    return d


def _metric_card(label: str, value: str) -> html.Div:
    """KPI tile — delegates to the shared design-system metric card so every
    counter/metric tile in the app matches."""
    return C.metric_card(label, value)


def _status_badge(txt: str, color: str) -> html.Span:
    return html.Span(txt, style={
        "backgroundColor": color, "color": D.COLOR.text,
        "borderRadius": D.RADIUS_SM, "padding": "1px 7px",
        "fontSize": D.TEXT_XS, "fontWeight": D.WEIGHT_MED,
    })


def _run_sync(data_type: str, ticker: str, from_date_str: str,
              force: list, av_key: str = "") -> tuple[str, str]:
    """Execute one sync and return (status_html, caption_str)."""
    try:
        from db.sync import (
            sync_price_bars, sync_news, sync_dividends, sync_earnings,
            sync_option_snapshots, sync_treasury_bars, sync_vix_bars,
            sync_macro_bars, sync_cpi, sync_fomc_calendar, sync_eps_estimates,
        )
        from db.client import get_engine
        from datetime import date as _date

        api_key = get_polygon_api_key()
        try:
            from_date = _date.fromisoformat(from_date_str) if from_date_str else _date(2020, 1, 1)
        except Exception:
            from_date = _date(2020, 1, 1)

        do_force = bool(force)

        if do_force and data_type in ("price", "options") and ticker:
            from db.client import get_ticker_id
            from sqlalchemy import text as _t
            engine = get_engine()
            tid = get_ticker_id(engine, ticker)
            if tid:
                table_map = {
                    "price":   ("mkt.PriceBar",       "PriceBar"),
                    "options": ("mkt.OptionSnapshot",  "OptionSnapshot"),
                }
                tbl, dtype = table_map[data_type]
                with engine.begin() as c:
                    c.execute(_t(f"DELETE FROM {tbl} WHERE TickerId=:tid"), {"tid": tid})
                    c.execute(_t("DELETE FROM mkt.SyncLog WHERE DataType=:dt AND TickerId=:tid"),
                              {"dt": dtype, "tid": tid})

        ticker_types = {"price", "news", "options", "divs", "earnings", "eps_estimates"}
        fn_map = {
            "price":        (sync_price_bars,    (ticker, api_key), {"from_date": from_date}),
            "news":         (sync_news,           (ticker, api_key), {"from_date": from_date}),
            "options":      (sync_option_snapshots, (ticker, api_key), {"from_date": from_date}),
            "divs":         (sync_dividends,      (ticker, api_key), {"from_date": from_date}),
            "earnings":     (sync_earnings,        (ticker, api_key), {"from_date": from_date}),
            "treasury":     (sync_treasury_bars,   (), {"from_date": from_date}),
            "vix":          (sync_vix_bars,        (), {"from_date": from_date}),
            "macro":        (sync_macro_bars,      (), {"from_date": from_date}),
            "cpi":          (sync_cpi,             (), {"from_date": from_date}),
            "fomc":         (sync_fomc_calendar,   (), {}),
        }

        if data_type == "eps_estimates":
            if not av_key:
                return "AV key required", ""
            r = sync_eps_estimates(ticker, av_key)
            rows = r.get("updated", 0) + r.get("inserted", 0)
            return f"Done — {rows} rows", ""

        if data_type not in fn_map:
            return "Unknown type", ""

        if data_type in ticker_types and not ticker:
            return "Enter a ticker first", ""

        fn, args, kwargs = fn_map[data_type]
        r = fn(*args, **kwargs)
        s = r.get("status", "ok")
        rows = r.get("rows", 0)
        if s == "up_to_date":
            return "Already up to date", ""
        elif s in ("no_data", "no_calendar"):
            detail = r.get("detail", r.get("message", ""))
            return f"No data: {detail}", ""
        else:
            return f"Done — {rows:,} rows", ""

    except Exception as e:
        logger.exception("Sync error")
        return f"Error: {e}", ""


def _coverage_label(mn, mx, cnt) -> str:
    if not cnt:
        return "no data"
    return f"{int(cnt):,} rows · {mn} → {mx}"


def _build_coverage_tables() -> html.Div:
    try:
        from db.client import get_engine
        from sqlalchemy import text as _t
        engine = get_engine()
        syms_str = "','".join(_COVERAGE_SYMBOLS)

        with engine.connect() as conn:
            price_rows = conn.execute(_t(f"""
                SELECT t.Symbol, COUNT(*) AS Bars,
                       MIN(pb.BarDate) AS [From], MAX(pb.BarDate) AS [To]
                FROM   mkt.PriceBar pb
                JOIN   mkt.Ticker t ON t.TickerId = pb.TickerId
                WHERE  t.Symbol IN ('{syms_str}')
                GROUP BY t.Symbol
            """)).fetchall()

            opt_rows = conn.execute(_t(f"""
                SELECT t.Symbol,
                       COUNT(DISTINCT o.SnapshotDate) AS OptDays,
                       MIN(o.SnapshotDate) AS [From], MAX(o.SnapshotDate) AS [To]
                FROM   mkt.OptionSnapshot o
                JOIN   mkt.Ticker t ON t.TickerId = o.TickerId
                WHERE  t.Symbol IN ('{syms_str}')
                GROUP BY t.Symbol
            """)).fetchall()

            def _safe(sql):
                try:
                    return conn.execute(_t(sql)).fetchone()
                except Exception:
                    return None

            vix_row   = _safe("SELECT MIN(BarDate), MAX(BarDate), COUNT(*) FROM mkt.VixBar")
            macro_row = _safe("SELECT MIN(BarDate), MAX(BarDate), COUNT(*) FROM mkt.MacroBar")
            cpi_row   = _safe("SELECT MIN(BarDate), MAX(BarDate), COUNT(*) FROM mkt.CpiBar")
            fomc_row  = _safe("SELECT MIN(MeetingDate), MAX(MeetingDate), COUNT(*) FROM mkt.FomcCalendar")
            vxf_row   = _safe("SELECT MIN(TradeDate), MAX(TradeDate), COUNT(*) FROM mkt.VixFuture")
            tsy_row   = _safe("SELECT MIN(BarDate), MAX(BarDate), COUNT(*) FROM mkt.TreasuryBar")

        price_map = {r[0]: r for r in price_rows}
        opt_map   = {r[0]: r for r in opt_rows}
        ticker_data = []
        for sym in _COVERAGE_SYMBOLS:
            p = price_map.get(sym)
            o = opt_map.get(sym)
            ticker_data.append({
                "Ticker":     sym,
                "Price Bars": f"{int(p[1]):,}" if p else "—",
                "Price From": str(p[2]) if p else "—",
                "Price To":   str(p[3]) if p else "—",
                "Opt Days":   f"{int(o[1]):,}" if o else "—",
                "Opt From":   str(o[2]) if o else "—",
                "Opt To":     str(o[3]) if o else "—",
            })

        ticker_cols = [
            _col("Ticker",     width=80),
            _col("Price Bars", min_width=100, flex=1, numeric=True),
            _col("Price From", min_width=120, flex=1),
            _col("Price To",   min_width=120, flex=1),
            _col("Opt Days",   min_width=100, flex=1, numeric=True),
            _col("Opt From",   min_width=120, flex=1),
            _col("Opt To",     min_width=120, flex=1),
        ]

        def _cov(row, label):
            if row and row[2]:
                return {"Dataset": label, "From": str(row[0]),
                        "To": str(row[1]), "Rows": f"{int(row[2]):,}"}
            return {"Dataset": label, "From": "—", "To": "—", "Rows": "0"}

        global_data = [
            _cov(tsy_row,   "Treasury Yields"),
            _cov(vix_row,   "VIX Bars"),
            _cov(macro_row, "Macro (FRED)"),
            _cov(cpi_row,   "CPI (FRED)"),
            _cov(vxf_row,   "VIX Futures"),
            _cov(fomc_row,  "FOMC Calendar"),
        ]
        global_cols = [
            _col("Dataset", width=180),
            _col("From",    width=120),
            _col("To",      width=120),
            _col("Rows",    width=100, numeric=True),
        ]

        return html.Div([
            html.P("Per-ticker", style={"color": D.COLOR.text_muted,
                                        "fontSize": D.TEXT_SM,
                                        "marginBottom": D.SPACE_2}),
            dag.AgGrid(
                rowData=ticker_data,
                columnDefs=ticker_cols,
                defaultColDef={"resizable": True},
                className=T.AGGRID_THEME,
                style={"height": "260px", "width": "100%", "marginBottom": D.SPACE_4},
            ),
            html.P("Global datasets", style={"color": D.COLOR.text_muted,
                                             "fontSize": D.TEXT_SM,
                                             "marginBottom": D.SPACE_2}),
            dag.AgGrid(
                rowData=global_data,
                columnDefs=global_cols,
                defaultColDef={"resizable": True},
                className=T.AGGRID_THEME,
                style={"height": "230px", "width": "100%"},
            ),
        ])

    except Exception as e:
        return html.Div(f"Could not load coverage: {e}",
                        style={"color": T.DANGER, "fontSize": "13px"})


def _build_validation(val_ticker: str) -> html.Div:
    if not val_ticker:
        return html.Div()
    try:
        from db.loader import validate_training_data
        report = validate_training_data(val_ticker)
    except Exception as e:
        return html.Div(f"Validation error: {e}", style={"color": T.DANGER, "fontSize": "13px"})

    parts: list = []
    if report.get("issues"):
        for issue in report["issues"]:
            parts.append(dbc.Alert(f"BLOCKER: {issue}", color="danger",
                                   style={"fontSize": "13px", "padding": "8px 12px"}))
    if not report.get("issues") and report.get("warnings"):
        parts.append(dbc.Alert(
            f"{val_ticker} price data is ready for training, but some data is missing.",
            color="warning", style={"fontSize": "13px", "padding": "8px 12px"},
        ))
    if not report.get("issues") and not report.get("warnings"):
        parts.append(dbc.Alert(
            f"{val_ticker} data is ready for training.",
            color="success", style={"fontSize": "13px", "padding": "8px 12px"},
        ))

    for w in report.get("warnings", []):
        parts.append(html.Div(f"Warning: {w}",
                               style={"color": T.WARNING, "fontSize": "12px",
                                      "marginBottom": "4px"}))

    cov = report.get("coverage", {})
    if cov:
        cov_rows = []
        for label, vals in cov.items():
            mn, mx, cnt = vals
            rows_str = f"{cnt:,}" if isinstance(cnt, int) and cnt > 0 else str(cnt)
            cov_rows.append({"Data": label, "From": str(mn), "To": str(mx), "Rows": rows_str})
        cov_cols = [
            _col("Data", width=180),
            _col("From", width=120),
            _col("To",   width=120),
            _col("Rows", width=100, numeric=True),
        ]
        parts.append(dag.AgGrid(
            rowData=cov_rows,
            columnDefs=cov_cols,
            defaultColDef={"resizable": True},
            className=T.AGGRID_THEME,
            style={"height": str(40 + len(cov_rows) * 40) + "px", "width": "100%",
                   "marginTop": "12px"},
        ))

    return html.Div(parts)


_SYNC_BUTTONS = [
    ("tools-dm-btn-price",    "tools-dm-st-price",    "tools-dm-cap-price",    "price"),
    ("tools-dm-btn-news",     "tools-dm-st-news",     "tools-dm-cap-news",     "news"),
    ("tools-dm-btn-options",  "tools-dm-st-options",  "tools-dm-cap-options",  "options"),
    ("tools-dm-btn-divs",     "tools-dm-st-divs",     "tools-dm-cap-divs",     "divs"),
    ("tools-dm-btn-earnings", "tools-dm-st-earnings", "tools-dm-cap-earnings", "earnings"),
    ("tools-dm-btn-eps",      "tools-dm-st-eps",      "tools-dm-cap-eps",      "eps_estimates"),
    ("tools-dm-btn-treasury", "tools-dm-st-treasury", "tools-dm-cap-treasury", "treasury"),
    ("tools-dm-btn-vix",      "tools-dm-st-vix",      "tools-dm-cap-vix",      "vix"),
    ("tools-dm-btn-macro",    "tools-dm-st-macro",    "tools-dm-cap-macro",    "macro"),
    ("tools-dm-btn-cpi",      "tools-dm-st-cpi",      "tools-dm-cap-cpi",      "cpi"),
    ("tools-dm-btn-fomc",     "tools-dm-st-fomc",     "tools-dm-cap-fomc",     "fomc"),
]


_SYNC_ALL_STEPS = ("price", "news", "divs", "earnings",
                   "treasury", "vix", "macro", "cpi", "fomc")
# Map step name → index in the output tuple (order matches outputs below).
_SYNC_ALL_IDX = {name: i for i, name in enumerate(_SYNC_ALL_STEPS)}


def _running_badge() -> html.Span:
    return html.Span(
        [
            html.Span(className="app-busy-dot",
                      style={"display": "inline-block", "width": "8px", "height": "8px",
                             "borderRadius": D.RADIUS_PILL,
                             "backgroundColor": D.COLOR.purple,
                             "marginRight": D.SPACE_2, "verticalAlign": "middle"}),
            html.Span("Running…"),
        ],
        style={"color": D.COLOR.purple, "fontWeight": D.WEIGHT_MED},
    )


def _get_px_client(user_key: str | None):
    """Build a PolygonClient, preferring user-supplied key then .env."""
    from data.polygon_client import PolygonClient
    key = get_polygon_api_key(user_key or "")
    if not key:
        raise ValueError("No Polygon API key — set POLYGON_API_KEY in .env or enter above.")
    return PolygonClient(api_key=key)


def _px_error(msg: str) -> html.Div:
    return dbc.Alert(str(msg), color="danger",
                     style={"fontSize": "13px", "marginTop": "8px"})


def _px_df_grid(df, height: int = 300) -> dag.AgGrid:
    """Render a DataFrame as an AG Grid."""
    cols = [{"field": c, "resizable": True, "sortable": True, "filter": True,
              "minWidth": 80, "flex": 1} for c in df.columns]
    return dag.AgGrid(
        rowData=df.astype(str).to_dict("records"),
        columnDefs=cols,
        defaultColDef={"resizable": True},
        className=T.AGGRID_THEME,
        style={"height": f"{height}px", "width": "100%"},
    )


def _compute_risk_metrics():
    """Load portfolio_history.json and compute VaR/CVaR/Sharpe/Sortino/MaxDD."""
    import numpy as np
    try:
        with open(_PORTFOLIO_HISTORY) as f:
            hist = json.load(f)
        snaps = hist.get("snapshots", [])
        if len(snaps) < 5:
            return None, None
        import pandas as pd
        equity = pd.Series(
            {s["date"]: float(s["equity"]) for s in snaps if s.get("equity")},
            name="equity",
        ).sort_index()
        rets = equity.pct_change().dropna()
        if len(rets) < 5:
            return None, None
        var_95  = float(np.percentile(rets, 5))
        cvar_95 = float(rets[rets <= var_95].mean()) if any(rets <= var_95) else var_95
        rolling_max = equity.cummax()
        drawdowns   = (equity - rolling_max) / rolling_max
        max_dd = float(drawdowns.min())
        ann = np.sqrt(252)
        sharpe  = float(rets.mean() / rets.std() * ann) if rets.std() > 0 else 0.0
        neg     = rets[rets < 0]
        sortino = float(rets.mean() / neg.std() * ann) if len(neg) > 1 else 0.0
        metrics = {
            "var_95":  var_95 * 100,
            "cvar_95": cvar_95 * 100,
            "max_dd":  max_dd * 100,
            "sharpe":  sharpe,
            "sortino": sortino,
        }
        return metrics, (equity, rets, drawdowns)
    except Exception as e:
        logger.warning("Risk metrics error: %s", e)
        return None, None


def _rh_available() -> bool:
    """Return True if robin_stocks is installed and RH credentials are configured."""
    try:
        import robin_stocks  # noqa: F401
        import os
        return bool(os.environ.get("ROBINHOOD_USERNAME") and os.environ.get("ROBINHOOD_PASSWORD"))
    except ImportError:
        return False


def _rh_get_stock_price(ticker: str) -> float | None:
    """Fetch Robinhood last trade price for a stock."""
    try:
        import robin_stocks.robinhood as rh
        import os
        rh.login(
            os.environ["ROBINHOOD_USERNAME"],
            os.environ["ROBINHOOD_PASSWORD"],
            mfa_code=os.environ.get("ROBINHOOD_MFA_CODE"),
            store_session=False,
        )
        quote = rh.stocks.get_latest_price(ticker)
        rh.authentication.logout()
        return float(quote[0]) if quote else None
    except Exception:
        return None


def _rh_get_option_ask(ticker: str, expiry: str, strike: str, opt_type: str) -> float | None:
    """Fetch Robinhood ask price for a specific option contract."""
    try:
        import robin_stocks.robinhood as rh
        import os
        rh.login(
            os.environ["ROBINHOOD_USERNAME"],
            os.environ["ROBINHOOD_PASSWORD"],
            mfa_code=os.environ.get("ROBINHOOD_MFA_CODE"),
            store_session=False,
        )
        data = rh.options.find_options_by_expiration_and_strike(
            ticker, expiry, strike, opt_type
        )
        rh.authentication.logout()
        if data and len(data) > 0:
            ask = data[0].get("ask_price")
            return float(ask) if ask else None
        return None
    except Exception:
        return None
