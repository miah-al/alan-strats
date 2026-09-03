"""
app/ui/timing_ui.py — a reusable StrategyUI base for equity-timing overlays.

An equity-timing overlay owns one liquid index when "in" and cash when "out"
(the shared machinery lives in `strategy_api.timing_base`). This base class
gives such a strategy a universe scan (who is currently in vs out), a
price-vs-signal chart in the detail modal, and a long-equity paper trade
(Contracts = shares). A plugin subclasses it with its own signal function.
"""
from __future__ import annotations

import logging
from typing import Callable

import plotly.graph_objects as go
from dash import html, dcc

from app import theme as T
from app.ui.strategy_widgets import col, metric as mc
from alan_trader.strategy_api.timing_base import load_close
from alan_trader.strategy_api.ui import StrategyUI, ScanContext

logger = logging.getLogger(__name__)

TIMING_COLS = [
    col("Ticker",    width=130, pinned="left"),
    col("Price",     width=120, numeric=True),
    col("Signal",    width=110),
    col("Reference", width=150),
    col("Strength %", width=130, numeric=True, sort="desc"),
    col("Status",    width=130),
]


class TimingUI(StrategyUI):
    columns = TIMING_COLS
    trade_kind = "equity"
    has_signal_alert = True

    #: (close) -> signal dict with at least signal / price / rule; subclasses set it.
    signal_fn: Callable = staticmethod(lambda close: {"signal": "UNKNOWN"})
    #: Bars of history to fetch per ticker for the scan / chart.
    history_days: int = 600
    #: Overlay a moving average of this window on the chart (0 = none).
    ma_window: int = 0

    def reference(self, sig: dict) -> tuple[str, float]:
        """(reference text, strength %) for a signal dict. Subclasses override
        when their signal carries different keys."""
        if "ma" in sig:
            return f"{sig['rule']} = {sig['ma']}", sig.get("pct_vs_ma", 0.0)
        return sig.get("rule", ""), sig.get("ret_lookback_pct", 0.0)

    def strength_label(self, sig: dict) -> str:
        if "pct_vs_ma" in sig:
            return f"{sig['pct_vs_ma']:+}% vs {self.ma_window}d MA"
        return f"{sig.get('ret_lookback_pct', 0):+}% trailing return"

    def scan(self, ctx: ScanContext) -> list[dict]:
        rows = []
        for ticker in ctx.tickers:
            try:
                close = load_close(ticker, n_days=self.history_days)
                sig = self.signal_fn(close)
                if sig.get("signal") in (None, "UNKNOWN"):
                    continue
                is_buy = sig.get("signal") == "BUY"
                ref, strength = self.reference(sig)
                rows.append({
                    "Ticker": ticker, "Price": sig.get("price", 0),
                    "Signal": sig.get("signal"), "Reference": ref,
                    "Strength %": strength, "score": strength,
                    "all_pass": is_buy, "n_pass": 4 if is_buy else 0,
                })
            except Exception as _e:
                logger.warning(f"{self.slug} scan {ticker} failed: {_e}")
        return rows

    def display_row(self, r: dict) -> dict:
        status = "BUY (uptrend)" if r.get("all_pass") else "HOLD (cash)"
        return {
            "Ticker":     r.get("Ticker", ""),
            "Price":      round(r.get("Price", 0), 2),
            "Signal":     r.get("Signal", ""),
            "Reference":  r.get("Reference", ""),
            "Strength %": round(r.get("Strength %", 0), 2),
            "Score":      round(r.get("score", r.get("Strength %", 0)) or 0, 2),  # sort key
            "Status":     status,
            "all_pass":   r.get("all_pass", False),
            "n_pass":     r.get("n_pass", 0),
        }

    def signal_body(self, row: dict):
        ticker = row.get("Ticker", "SPY")
        try:
            close = load_close(ticker, n_days=self.history_days)
            if close.empty:
                return html.Div(f"No price data for {ticker}.",
                                style={"color": T.DANGER, "fontSize": "13px"})
            sig = self.signal_fn(close)
            buy = sig.get("signal") == "BUY"
            colr = T.SUCCESS if buy else T.WARNING

            px = close.tail(260)
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=list(px.index), y=list(px.values), mode="lines",
                                     name=ticker, line={"color": "#818cf8", "width": 2}))
            if self.ma_window:
                ma = close.rolling(self.ma_window).mean().tail(260)
                fig.add_trace(go.Scatter(x=list(ma.index), y=list(ma.values), mode="lines",
                                         name=f"{self.ma_window}-day MA",
                                         line={"color": "#f59e0b", "width": 1.5, "dash": "dash"}))
            fig.update_layout(
                title={"text": f"{ticker} — {'above' if buy else 'below'} signal line",
                       "font": {"size": 13, "color": "#e2e8f0"}, "x": 0.01},
                paper_bgcolor="#1e293b", plot_bgcolor="#1e293b", font={"color": "#94a3b8"},
                margin={"l": 50, "r": 20, "t": 40, "b": 30}, height=300,
                xaxis={"gridcolor": "#334155"}, yaxis={"gridcolor": "#334155", "tickprefix": "$"},
                showlegend=True, legend={"font": {"size": 10}, "x": 0.01, "y": 0.99,
                                         "bgcolor": "rgba(0,0,0,0)"},
            )

            cards = html.Div([
                mc("Signal", sig.get("signal", "?"), colr),
                mc("Price", f"${sig.get('price', 0):,.2f}"),
                mc("Strength", self.strength_label(sig), colr),
                mc("As of", sig.get("asof", "—")),
            ], style={"display": "flex", "gap": "10px", "marginBottom": "14px", "flexWrap": "wrap"})

            note = html.Div(
                ("✓ Signal is BUY — 'Paper Trade' buys the shares set below at the current price."
                 if buy else
                 "Signal is HOLD (cash). You can still paper-trade, but the strategy is flat here."),
                style={"color": colr, "fontSize": "12px", "marginTop": "4px"})

            return html.Div([
                cards,
                dcc.Graph(figure=fig, config={"displayModeBar": False}),
                note,
                html.Div("Note: 'Contracts' below = number of shares to buy.",
                         style={"color": T.TEXT_MUTED, "fontSize": "11px", "marginTop": "8px"}),
            ])
        except Exception as e:
            return html.Div(f"Error building signal view: {e}",
                            style={"color": T.DANGER, "fontSize": "13px"})
