"""
app/pages/strategies/modals.py — signal / IC payoff modals + paper-trade callbacks.

Holds every modal-and-trade callback for the strategies page: the IC chart modal
(_make_ic_chart_callback, _build_modal_body), paper-trade actions (_paper_trade_ic,
_paper_trade_sig), the signal modal (_make_signal_callback, _build_signal_body and
its helpers _sig_chart / _make_legs_table / _build_trend_signal_body), the modal
dismiss handler, and the HMM live-signal compute callback. Importing this module
registers all of those callbacks. Depends on the data_fetch / registry leaves;
db.client and engine.positions are imported lazily inside the trade handlers.
"""
from __future__ import annotations

import logging

import numpy as np
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash import html, dcc, callback, Input, Output, State, no_update

from app import theme as T
from app.ui import components as C
from app.grid_helpers import mrt_grid as _mrt_grid_shared
from app.pages.strategies.registry import _SLUG_TO_LABEL
from app.pages.strategies.data_fetch import (
    _build_ic_payoff_fig, _get_vix_series, _hmm_trade_preview,
)

logger = logging.getLogger(__name__)

# Map the legacy raw-colour tile API onto the design-system metric_card tones.
_TONE = {T.SUCCESS: "success", T.DANGER: "danger", T.WARNING: "warning",
         T.ACCENT: "accent", T.TEXT_PRIMARY: "default", T.TEXT_MUTED: "muted"}


# ── IC chart modal: two-step (open instantly → populate via store) ────────────

def _make_ic_chart_callback(slug: str):
    grid_id = f"str-{slug}-grid"

    # Step 1: row clicked → open modal immediately + store row data
    # MRT bridge: row clicks come via the hidden input written by
    # assets/mrt_row_click.js. The payload is a JSON string with `rowIndex`.
    @callback(
        Output("str-ic-modal",       "is_open",  allow_duplicate=True),
        Output("str-ic-modal-title", "children", allow_duplicate=True),
        Output("str-ic-row-store",   "data",     allow_duplicate=True),
        Output("str-ic-paper-btn",   "disabled", allow_duplicate=True),
        Input(f"{grid_id}-clicked",  "value"),
        State(grid_id,  "data"),
        prevent_initial_call=True,
    )
    def _open_modal(click_payload, all_rows):
        import json as _json
        if not click_payload or not all_rows:
            return no_update, no_update, no_update, no_update
        try:
            payload = _json.loads(click_payload)
        except Exception:
            return no_update, no_update, no_update, no_update
        row_index = int(payload.get("rowIndex", -1))
        if row_index < 0 or row_index >= len(all_rows):
            return no_update, no_update, no_update, no_update
        row = all_rows[row_index]
        if not row:
            return no_update, no_update, no_update, no_update
        row = {**row, "_slug": slug}   # tag the strategy slug for paper trade
        ticker = row.get("Ticker", "")
        chain  = row.get("_chain")
        title  = (f"{ticker} Iron Condor  ·  {chain['best_exp']} ({chain['dte_used']} DTE)  ·  "
                  f"~{chain['target_delta']:.0%}-delta  ·  Net credit ${chain['net_credit']*100:.2f}"
                  if chain else ticker)
        # Disable Paper Trade immediately; Step 2 re-enables only when chain is valid
        return True, title, row, True

    _open_modal.__name__ = f"_open_modal_{slug}"
    return _open_modal


# Step 2: store change → build and populate modal body (runs after modal is open)
@callback(
    Output("str-ic-modal-body",  "children"),
    Output("str-ic-paper-btn",   "disabled"),
    Input("str-ic-row-store", "data"),
    prevent_initial_call=True,
)
def _build_modal_body(row):
    if not row:
        return no_update, no_update
    ticker = row.get("Ticker", "")
    chain  = row.get("_chain")

    if not chain:
        err_detail = row.get("_chain_err") or "Polygon returned no data for the 30–60 DTE window"
        return dbc.Alert(
            [html.Strong(f"{ticker}: "), err_detail],
            color="warning",
        ), True

    spot          = row.get("Price", 0)
    atm_iv        = row.get("_atm_iv_raw") or 0.25
    net_credit    = chain["net_credit"]
    max_loss      = chain["max_loss"]
    be_upper      = chain["short_call_k"] + net_credit
    be_lower      = chain["short_put_k"]  - net_credit
    profit_target = net_credit * 0.50

    def _mc(label, val, color=T.TEXT_PRIMARY):
        return C.metric_card(label, str(val), _TONE.get(color, "default"))

    nc100 = net_credit * 100
    ml100 = max_loss   * 100
    pt100 = profit_target * 100
    _has_prices = any(chain.get(k, 0) > 0
                      for k in ["short_call_mid", "short_put_mid",
                                "long_call_mid",  "long_put_mid"])
    metrics = html.Div([
        _mc("Net Credit",   f"${nc100:.2f}" if _has_prices else "— (no quotes)",
            T.SUCCESS if net_credit > 0 else (T.WARNING if not _has_prices else T.DANGER)),
        _mc("Max Loss",     f"-${ml100:.2f}" if _has_prices else "—", T.DANGER),
        _mc("50% Target",   f"${pt100:.2f}" if _has_prices else "—", T.SUCCESS),
        _mc("Upper BE",     f"${be_upper:.2f}"),
        _mc("Lower BE",     f"${be_lower:.2f}"),
        _mc("Expiry",       f"{chain['best_exp']} ({chain['dte_used']} DTE)"),
        _mc("Delta target", f"~{chain['target_delta']:.0%}"),
    ], style={"display": "flex", "gap": "10px", "flexWrap": "wrap", "marginBottom": "16px"})

    def _fmt_mid(v):
        return f"${v:.2f}" if v and v > 0 else "—"

    def _cash(mid, action):
        if not mid or mid == 0:
            return "—"
        val = mid * 100 * (1 if action == "SELL" else -1)
        return f"+${val:.2f}" if val >= 0 else f"-${abs(val):.2f}"

    net_cash = net_credit * 100
    leg_rows = [
        {"Leg": "Long call (wing)", "Strike": f"${chain['long_call_k']:.0f}",
         "Mid": _fmt_mid(chain['long_call_mid']), "Action": "BUY",
         "$/Contract": _cash(chain['long_call_mid'], "BUY")},
        {"Leg": "Short call",       "Strike": f"${chain['short_call_k']:.0f}",
         "Mid": _fmt_mid(chain['short_call_mid']), "Action": "SELL",
         "$/Contract": _cash(chain['short_call_mid'], "SELL")},
        {"Leg": "Short put",        "Strike": f"${chain['short_put_k']:.0f}",
         "Mid": _fmt_mid(chain['short_put_mid']), "Action": "SELL",
         "$/Contract": _cash(chain['short_put_mid'], "SELL")},
        {"Leg": "Long put (wing)",  "Strike": f"${chain['long_put_k']:.0f}",
         "Mid": _fmt_mid(chain['long_put_mid']), "Action": "BUY",
         "$/Contract": _cash(chain['long_put_mid'], "BUY")},
        {"Leg": "NET CREDIT", "Strike": "", "Mid": "", "Action": "",
         "$/Contract": (f"+${net_cash:.2f}" if net_cash >= 0 else f"-${abs(net_cash):.2f}")
                       if _has_prices else "—"},
    ]
    leg_table = _mrt_grid_shared(
        data=leg_rows,
        col_defs=[
            {"field": "Leg"},
            {"field": "Strike"},
            {"field": "Mid"},
            {"field": "Action"},
            {"field": "$/Contract"},
        ],
        height=260,
        enable_pagination=False,
    )

    fig = _build_ic_payoff_fig(
        spot=spot,
        short_call_k=chain["short_call_k"], long_call_k=chain["long_call_k"],
        short_put_k=chain["short_put_k"],   long_put_k=chain["long_put_k"],
        net_credit=net_credit, dte_used=chain["dte_used"],
        atm_iv=atm_iv, ticker=ticker, best_exp=chain["best_exp"],
    )

    return html.Div([
        metrics,
        leg_table,
        dcc.Graph(figure=fig, config={"displayModeBar": False}),
        html.P(
            "Solid purple = P&L at expiry · Dotted green = P&L today (BS) · "
            "Green dashed = 50% profit target · Red dashed = 2× stop",
            style={"color": T.TEXT_MUTED, "fontSize": "11px", "marginTop": "8px"},
        ),
    ]), False


for _slug in ("iron_condor_rules", "iron_condor_ai"):
    _make_ic_chart_callback(_slug)


# ── Paper Trade callback ──────────────────────────────────────────────────────

@callback(
    Output("str-ic-paper-feedback", "children"),
    Input("str-ic-paper-btn", "n_clicks"),
    State("str-ic-row-store", "data"),
    State("str-ic-contracts", "value"),
    prevent_initial_call=True,
)
def _paper_trade_ic(n_clicks, row, contracts):
    if not n_clicks or not row:
        return no_update
    chain = row.get("_chain")
    if not chain:
        return html.Span("No chain data.", style={"color": T.DANGER})
    ticker = row.get("Ticker", "")
    slug   = row.get("_slug", "iron_condor_rules")
    label  = _SLUG_TO_LABEL.get(slug, slug)

    # Block trade if net credit is negative or below minimum threshold
    net_credit = chain.get("net_credit")
    if net_credit is not None and float(net_credit) < 0.05:
        return html.Span(
            f"⚠ Net credit ${float(net_credit):.2f} is too low — trade blocked. "
            "Credits below $0.05/share are not worth the risk.",
            style={"color": T.WARNING},
        )

    try:
        from engine.positions import insert_open_ic_trade
        from db.client import get_engine
        engine = get_engine()
        n = int(contracts or 1)
        err = insert_open_ic_trade(
            engine=engine,
            account_id=1,
            ticker=ticker,
            chain=chain,
            strategy_name=label,
            contracts=n,
        )
        if err:
            return html.Span(f"Error: {err}", style={"color": T.DANGER})
        return html.Span(
            f"✓ {ticker} IC saved ({n} contract(s))",
            style={"color": T.SUCCESS},
        )
    except Exception as e:
        return html.Span(f"Error: {e}", style={"color": T.DANGER})


# ── Paper Trade callback for signal-modal strategies ──────────────────────────

_CREDIT_SLUGS = {
    "ivr_credit_spread", "bull_put_spread", "put_steal",
    "broken_wing_butterfly", "rs_credit_spread",
}
_MIN_CREDIT_PER_SHARE = 0.05   # block if net credit < $0.05/share


@callback(
    Output("str-sig-paper-feedback", "children"),
    Input("str-sig-paper-btn", "n_clicks"),
    State("str-sig-row-store", "data"),
    State("str-sig-contracts", "value"),
    prevent_initial_call=True,
)
def _paper_trade_sig(n_clicks, row, contracts):
    if not n_clicks or not row:
        return no_update
    ticker  = row.get("Ticker", "")
    slug    = row.get("_slug", "")
    label   = _SLUG_TO_LABEL.get(slug, slug)
    status  = row.get("Status", "")
    n       = int(contracts or 1)

    # Timing strategies → buy `n` shares of the index at the current price.
    if slug in ("trend_following", "ts_momentum"):
        try:
            from engine.positions import insert_equity_paper_trade
            from db.client import get_engine
            price = float(row.get("Price") or 0)
            if price <= 0:
                return html.Span("⚠ No current price — cannot record trade.",
                                 style={"color": T.WARNING, "fontSize": "12px"})
            err = insert_equity_paper_trade(
                engine=get_engine(), account_id=1, ticker=ticker,
                strategy_name=slug, shares=n, price=price,
                details={k: row.get(k) for k in ("Signal", "Reference", "Strength %")})
            if err:
                return html.Span(f"❌ {err}", style={"color": T.DANGER, "fontSize": "12px"})
            return html.Span(f"✓ Bought {n} {ticker} @ ${price:,.2f} ({label}).",
                             style={"color": T.SUCCESS, "fontSize": "12px"})
        except Exception as e:
            return html.Span(f"❌ {e}", style={"color": T.DANGER, "fontSize": "12px"})

    # Block credit strategies where net credit is too low / negative
    if slug in _CREDIT_SLUGS:
        chain = row.get("_chain") or {}
        raw = (chain.get("net_credit") or row.get("net_credit") or
               row.get("~Credit") or row.get("Credit"))
        if raw is not None:
            try:
                cred_f = float(str(raw).lstrip("$+") or 0)
                if cred_f < _MIN_CREDIT_PER_SHARE:
                    return html.Span(
                        f"⚠ Net credit ${cred_f:.2f}/share is too low — trade blocked "
                        f"(min ${_MIN_CREDIT_PER_SHARE:.2f}/share).",
                        style={"color": T.WARNING, "fontSize": "12px"},
                    )
            except Exception:
                pass

    try:
        from engine.positions import insert_generic_paper_trade
        from db.client import get_engine
        engine = get_engine()
        # Build a summary of the key trade parameters
        details = {k: v for k, v in row.items()
                   if k not in ("_slug", "all_pass", "n_pass", "_chain")
                   and v not in (None, "—", "")}

        # VSF: inject chain leg data so insert_generic_paper_trade gets real strikes/premiums
        if slug == "vix_spike_fade":
            vsf = row.get("_chain") or {}
            if vsf:
                details["Short Strike"]   = vsf.get("short_put_k")   # OTM put we SELL
                details["Long Strike"]    = vsf.get("long_put_k")    # ATM put we BUY
                details["~Credit"]        = vsf.get("short_put_mid") # premium collected
                details["~Long Premium"]  = vsf.get("long_put_mid")  # premium paid
                details["Expiry"]         = vsf.get("best_exp")
                details["DTE"]            = vsf.get("dte_used")
                details["Long Delta"]     = vsf.get("long_delta")
                details["Net Debit"]      = vsf.get("net_debit")

        # IVR Credit Spread: inject chain leg data (put or call spread)
        elif slug == "ivr_credit_spread":
            ivr_c = row.get("_chain") or {}
            if ivr_c:
                details["Short Strike"]  = ivr_c.get("short_k")     # leg we SELL
                details["Long Strike"]   = ivr_c.get("long_k")      # wing we BUY
                details["~Credit"]       = ivr_c.get("short_mid")   # premium collected
                details["~Long Premium"] = ivr_c.get("long_mid")    # premium paid
                details["Expiry"]        = ivr_c.get("best_exp")
                details["DTE"]           = ivr_c.get("dte_used")

        # HMM Regime: compute strikes from the state-specific structure.
        # State 0 (bull put) and State 2 (long put spread) → 2-leg PUT inserter.
        # State 1 (iron condor) → routes through the 4-leg IC inserter directly,
        # returning early to bypass insert_generic_paper_trade.
        elif slug == "hmm_regime":
            try:
                state_val = int(row.get("State", -1))
            except Exception:
                state_val = -1
            try:
                spot = float(row.get("Price") or 0.0)
                vix  = float(row.get("VIX") or 0.0)
                preview = _hmm_trade_preview(state_val, spot, vix, ticker)
            except Exception:
                preview = None
            if state_val not in (0, 1, 2) or preview is None:
                return html.Span(
                    "⚠ HMM paper trade unavailable — current state has no entry "
                    "(VIX too high, or no dominant regime).",
                    style={"color": T.WARNING, "fontSize": "12px"},
                )
            try:
                from datetime import date, timedelta
                dte_map = {0: 30, 1: 35, 2: 45}
                dte_used = dte_map[state_val]
                expiry   = (date.today() + timedelta(days=dte_used)).isoformat()
                leg_rows = preview["legs_table"].rowData

                def _strike(r):
                    return float(str(r["Strike"]).lstrip("$"))

                def _mid(r):
                    return float(str(r["Mid"]).lstrip("$"))

                if state_val == 1:
                    # ── Iron Condor (4 legs) — route through insert_open_ic_trade ──
                    # leg_rows order from _hmm_trade_preview:
                    #   Long call (wing) BUY  | Short call SELL
                    #   Short put SELL        | Long put (wing) BUY
                    rows_by_label = {r["Leg"]: r for r in leg_rows
                                     if not str(r.get("Leg", "")).startswith("NET")}
                    chain = {
                        "best_exp":         expiry,
                        "long_call_k":      _strike(rows_by_label["Long call (wing)"]),
                        "short_call_k":     _strike(rows_by_label["Short call"]),
                        "short_put_k":      _strike(rows_by_label["Short put"]),
                        "long_put_k":       _strike(rows_by_label["Long put (wing)"]),
                        "long_call_mid":    _mid(rows_by_label["Long call (wing)"]),
                        "short_call_mid":   _mid(rows_by_label["Short call"]),
                        "short_put_mid":    _mid(rows_by_label["Short put"]),
                        "long_put_mid":     _mid(rows_by_label["Long put (wing)"]),
                    }
                    from engine.positions import insert_open_ic_trade
                    from db.client import get_engine
                    err = insert_open_ic_trade(
                        engine=get_engine(),
                        account_id=1,
                        ticker=ticker,
                        chain=chain,
                        strategy_name=label,
                        contracts=n,
                    )
                    if err:
                        return html.Span(f"Error: {err}", style={"color": T.DANGER, "fontSize": "12px"})
                    return html.Span(
                        f"✓ {ticker} {label} (Iron Condor, state 1) saved ({n} contract(s))",
                        style={"color": T.SUCCESS, "fontSize": "12px"},
                    )

                # ── State 0 / State 2 → 2-leg PUT spreads via generic inserter ──
                short_row = next(r for r in leg_rows if r["Action"] == "SELL")
                long_row  = next(r for r in leg_rows if r["Action"] == "BUY")
                short_k, long_k = _strike(short_row), _strike(long_row)
                short_mid, long_mid = _mid(short_row), _mid(long_row)
                details["Short Strike"]   = short_k
                details["Long Strike"]    = long_k
                details["~Credit"]        = short_mid - long_mid   # +ve for state 0, -ve for state 2
                details["~Long Premium"]  = long_mid
                details["Expiry"]         = expiry
                details["DTE"]            = dte_used
            except Exception as _e:
                return html.Span(
                    f"⚠ HMM paper-trade injection failed: {_e}",
                    style={"color": T.DANGER, "fontSize": "12px"},
                )

        err = insert_generic_paper_trade(
            engine=engine,
            account_id=1,
            ticker=ticker,
            strategy_name=label,
            contracts=n,
            details=details,
        )
        if err:
            return html.Span(f"Error: {err}", style={"color": T.DANGER, "fontSize": "12px"})
        return html.Span(
            f"✓ {ticker} {label} saved ({n} contract(s))",
            style={"color": T.SUCCESS, "fontSize": "12px"},
        )
    except Exception as e:
        return html.Span(f"Error: {e}", style={"color": T.DANGER, "fontSize": "12px"})


# ── Signal detail modal for VSF / IVR / VA / GEX ─────────────────────────────

def _make_signal_callback(slug: str):
    grid_id = f"str-{slug}-grid"

    @callback(
        Output("str-sig-modal",       "is_open",  allow_duplicate=True),
        Output("str-sig-modal-title", "children", allow_duplicate=True),
        Output("str-sig-row-store",   "data",     allow_duplicate=True),
        Input(f"{grid_id}-clicked", "value"),
        State(grid_id,  "data"),
        prevent_initial_call=True,
    )
    def _open_sig_modal(click_payload, all_rows):
        import json as _json
        if not click_payload or not all_rows:
            return no_update, no_update, no_update
        try:
            payload = _json.loads(click_payload)
        except Exception:
            return no_update, no_update, no_update
        row_index = int(payload.get("rowIndex", -1))
        if row_index < 0 or row_index >= len(all_rows):
            return no_update, no_update, no_update
        row = all_rows[row_index]
        if not row:
            return no_update, no_update, no_update
        row    = {**row, "_slug": slug}
        ticker = row.get("Ticker", "")
        label  = _SLUG_TO_LABEL.get(slug, slug)
        score  = row.get("Score", "")
        title  = f"{ticker}  ·  {label}  ·  Score {score}"
        return True, title, row

    _open_sig_modal.__name__ = f"_open_sig_modal_{slug}"
    return _open_sig_modal


def _sig_chart(spots, pnl, spot_price, ticker, title, max_loss, max_profit, target,
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
    # Colour the loss zone red
    fig.add_trace(go.Scatter(
        x=list(spots), y=[min(p, 0) for p in pnl],
        mode="lines", name="Loss zone",
        line={"width": 0},
        fill="tozeroy",
        fillcolor="rgba(239,68,68,0.12)",
        showlegend=False,
    ))
    # Reference lines
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


def _make_legs_table(rows: list[dict]):
    """Build a compact legs summary table for strategy modals."""
    return _mrt_grid_shared(
        data=rows,
        col_defs=[
            {"field": "Leg"},
            {"field": "Strike"},
            {"field": "Action"},
            {"field": "~/Contract"},
        ],
        height=240,
        enable_pagination=False,
    )


def _build_trend_signal_body(row: dict) -> html.Div:
    """Modal body for the trend / momentum timing strategies: a price chart with
    the signal overlay (200-day MA, or 12-month reference) + key stats. The
    'trade' is a long-equity position, sized via the Contracts→shares input."""
    slug   = row.get("_slug", "")
    ticker = row.get("Ticker", "SPY")
    try:
        from strategies.timing_base import load_close
        from strategies.trend_following import current_trend_signal
        from strategies.ts_momentum import current_tsmom_signal
        import plotly.graph_objects as go

        close = load_close(ticker, n_days=600)
        if close.empty:
            return html.Div(f"No price data for {ticker}.",
                            style={"color": T.DANGER, "fontSize": "13px"})
        is_trend = slug == "trend_following"
        sig = current_trend_signal(close) if is_trend else current_tsmom_signal(close)
        buy = sig.get("signal") == "BUY"
        col = T.SUCCESS if buy else T.WARNING

        # Chart: last ~1y of price + (trend) the 200-day MA line
        px = close.tail(260)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=list(px.index), y=list(px.values), mode="lines",
                                 name=ticker, line={"color": "#818cf8", "width": 2}))
        if is_trend:
            ma = close.rolling(200).mean().tail(260)
            fig.add_trace(go.Scatter(x=list(ma.index), y=list(ma.values), mode="lines",
                                     name="200-day MA", line={"color": "#f59e0b", "width": 1.5, "dash": "dash"}))
        fig.update_layout(
            title={"text": f"{ticker} — {'above' if buy else 'below'} signal line",
                   "font": {"size": 13, "color": "#e2e8f0"}, "x": 0.01},
            paper_bgcolor="#1e293b", plot_bgcolor="#1e293b", font={"color": "#94a3b8"},
            margin={"l": 50, "r": 20, "t": 40, "b": 30}, height=300,
            xaxis={"gridcolor": "#334155"}, yaxis={"gridcolor": "#334155", "tickprefix": "$"},
            showlegend=True, legend={"font": {"size": 10}, "x": 0.01, "y": 0.99,
                                     "bgcolor": "rgba(0,0,0,0)"},
        )

        def _mc(label, val, c=T.TEXT_PRIMARY):
            return C.metric_card(label, str(val), _TONE.get(c, "default"))

        detail = (f"{sig['pct_vs_ma']:+}% vs 200d MA" if is_trend
                  else f"{sig['ret_lookback_pct']:+}% trailing 12m")
        cards = html.Div([
            _mc("Signal", sig.get("signal", "?"), col),
            _mc("Price", f"${sig.get('price', 0):,.2f}"),
            _mc("Strength", detail, col),
            _mc("As of", sig.get("asof", "—")),
        ], style={"display": "flex", "gap": "10px", "marginBottom": "14px", "flexWrap": "wrap"})

        note = html.Div(
            ("✓ Signal is BUY — 'Paper Trade' buys the shares set below at the current price."
             if buy else
             "Signal is HOLD (cash). You can still paper-trade, but the strategy is flat here."),
            style={"color": col, "fontSize": "12px", "marginTop": "4px"})

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


@callback(
    Output("str-sig-modal-body", "children"),
    Input("str-sig-row-store",   "data"),
    prevent_initial_call=True,
)
def _build_signal_body(row):
    if not row:
        return no_update

    slug   = row.get("_slug", "")
    ticker = row.get("Ticker", "")
    status = row.get("Status", "—")

    # Timing strategies (trend / momentum) have no options payoff — show a
    # price-vs-MA chart + stats instead, and a long-equity paper trade.
    if slug in ("trend_following", "ts_momentum"):
        return _build_trend_signal_body(row)

    status_color = (T.SUCCESS if status == "Trade-Ready" else
                    T.WARNING if status == "Partial" else T.DANGER)

    def _mc(label, val, color=T.TEXT_PRIMARY):
        return C.metric_card(label, str(val), _TONE.get(color, "default"))

    def _row(*cards):
        return html.Div(list(cards),
                        style={"display": "flex", "gap": "10px",
                               "flexWrap": "wrap", "marginBottom": "14px"})

    # ── Strategy-specific content ─────────────────────────────────────────────
    chart      = html.Div()   # default: no chart; overridden by strategies that have P&L graphs
    legs_table = html.Div()   # default: no legs table

    if slug == "vix_spike_fade":
        vix     = row.get("VIX", "—")
        vix20   = row.get("VIX 20d avg", "—")
        ratio   = row.get("VIX / 20d", "—")
        atm_iv  = row.get("ATM IV", "—")
        hv20    = row.get("HV20", "—")
        ivr     = row.get("IVR", "—")
        ma200   = row.get("MA200", "—")
        spot    = float(row.get("Price") or 0)

        # Fetch real ATM put from Polygon (~30 DTE, delta ≈ -0.50)
        vsf_chain = None
        vsf_err   = None
        try:
            from app import get_polygon_api_key
            from data.polygon_client import PolygonClient
            import datetime as _dt
            api_key = get_polygon_api_key()
            if api_key and spot > 0:
                client = PolygonClient(api_key=api_key)
                today  = _dt.date.today()
                exp_lo = (today + _dt.timedelta(days=21)).isoformat()
                exp_hi = (today + _dt.timedelta(days=45)).isoformat()
                chain  = client.get_options_chain(
                    ticker,
                    expiration_date_gte=exp_lo,
                    expiration_date_lte=exp_hi,
                    strike_price_gte=spot * 0.85,
                    strike_price_lte=spot * 1.02,
                )
                if chain is not None and not chain.empty:
                    puts = chain[chain["type"] == "put"].copy()
                    puts["delta_abs"] = puts["delta"].abs()
                    # ATM put: delta closest to -0.50
                    atm_put = puts.loc[(puts["delta_abs"] - 0.50).abs().idxmin()] if not puts.empty else None
                    # OTM wing: delta closest to -0.25, strike below ATM
                    if atm_put is not None:
                        atm_k   = float(atm_put["strike"])
                        otm_row = puts[puts["strike"] < atm_k].copy()
                        otm_put = otm_row.loc[(otm_row["delta_abs"] - 0.25).abs().idxmin()] if not otm_row.empty else None
                        atm_mid = round((float(atm_put["bid"]) + float(atm_put["ask"])) / 2, 2) \
                                  if (atm_put.get("bid") == atm_put.get("bid")) else None
                        otm_mid = round((float(otm_put["bid"]) + float(otm_put["ask"])) / 2, 2) \
                                  if (otm_put is not None and otm_put.get("bid") == otm_put.get("bid")) else None
                        net_debit = round((atm_mid or 0) - (otm_mid or 0), 2)
                        vsf_chain = {
                            "long_put_k":  atm_k,
                            "long_put_mid": atm_mid,
                            "short_put_k": float(otm_put["strike"]) if otm_put is not None else None,
                            "short_put_mid": otm_mid,
                            "net_debit":   net_debit,
                            "best_exp":    str(atm_put["expiration"]),
                            "dte_used":    int(atm_put["dte"]) if atm_put.get("dte") else 30,
                            "long_delta":  round(float(atm_put["delta"]), 2) if atm_put.get("delta") == atm_put.get("delta") else None,
                        }
        except Exception as _e:
            vsf_err = str(_e)

        is_ready = float(str(ratio).rstrip("%") or 0) > 1.2
        signal = ("Buy put spread — VIX elevated, fade the spike back toward mean"
                  if is_ready else "Monitor — VIX spike not sufficient")

        chain_info = html.Div()
        if vsf_chain:
            c = vsf_chain
            _lpm = f"${c['long_put_mid']:.2f}" if c.get("long_put_mid") else "—"
            _spm = f"${c['short_put_mid']:.2f}" if c.get("short_put_mid") else "—"
            _nd  = f"${c['net_debit']:.2f}" if c.get("net_debit") is not None else "—"
            _sk  = f"${c['short_put_k']:.0f}" if c.get("short_put_k") else "—"
            chain_info = html.Div([
                html.Div("PUT SPREAD", style={"color": T.TEXT_MUTED, "fontSize": "10px",
                                              "fontWeight": "700", "letterSpacing": "0.07em",
                                              "marginBottom": "6px"}),
                _mrt_grid_shared(
                    data=[
                        {"Leg": "Long put (ATM)",  "Strike": f"${c['long_put_k']:.0f}",
                         "Mid": _lpm, "Action": "BUY",
                         "$/Contract": f"-${c['long_put_mid']*100:.2f}" if c.get("long_put_mid") else "—"},
                        {"Leg": "Short put (wing)", "Strike": _sk,
                         "Mid": _spm, "Action": "SELL",
                         "$/Contract": f"+${c['short_put_mid']*100:.2f}" if c.get("short_put_mid") else "—"},
                        {"Leg": "NET DEBIT", "Strike": "", "Mid": "", "Action": "",
                         "$/Contract": f"-${c['net_debit']*100:.2f}" if c.get("net_debit") else "—"},
                    ],
                    col_defs=[
                        {"field": "Leg"},
                        {"field": "Strike"},
                        {"field": "Mid"},
                        {"field": "Action"},
                        {"field": "$/Contract"},
                    ],
                    height=200,
                    enable_pagination=False,
                ),
                html.Div(f"Expiry: {c['best_exp']}  ({c['dte_used']} DTE)  ·  "
                         f"Long delta: {c['long_delta']}",
                         style={"color": T.TEXT_MUTED, "fontSize": "11px"}),
            ], style={"marginTop": "12px"})
        elif vsf_err:
            chain_info = html.P(f"Chain error: {vsf_err}",
                                style={"color": T.WARNING, "fontSize": "12px"})
        else:
            chain_info = html.P("No Polygon data — set POLYGON_API_KEY to see real strikes.",
                                style={"color": T.TEXT_MUTED, "fontSize": "12px"})

        # Attach chain to row store so paper trade can use it
        row["_chain"] = vsf_chain
        legs_table = chain_info   # wire into final layout

        # Payoff chart — bear put spread (long ATM put, short OTM put)
        if vsf_chain and spot > 0:
            c   = vsf_chain
            lk  = c.get("long_put_k")  or spot
            sk  = c.get("short_put_k") or spot * 0.97
            nd  = c.get("net_debit")   or 0
            sw  = lk - sk
            max_prof  =  (sw - nd) * 100   # profit if spot falls below OTM put
            max_loss  = -nd * 100          # lose debit if spot stays above ATM put
            spots_vsf = np.linspace(spot * 0.80, spot * 1.10, 300)
            def _vsf_pnl(s):
                long_p  =  max(0, lk - s)
                short_p = -max(0, sk - s)
                return (-nd + long_p + short_p) * 100
            pnl_vsf = [_vsf_pnl(s) for s in spots_vsf]
            chart = _sig_chart(spots_vsf, pnl_vsf, spot, ticker,
                               "VIX Spike Fade — Bear Put Spread",
                               max_loss, max_prof, max_prof * 0.5,
                               stop_level=max_loss * 0.5)

        metrics = _row(
            _mc("VIX",        str(vix),   T.DANGER if float(str(vix) or 0) > 25 else T.TEXT_PRIMARY),
            _mc("VIX 20d Avg",str(vix20)),
            _mc("VIX / 20d",  str(ratio)),
            _mc("ATM IV",     str(atm_iv)),
            _mc("HV20",       str(hv20)),
            _mc("IVR",        str(ivr)),
            _mc("MA200",      str(ma200)),
            _mc("Status",     status, status_color),
        )

    elif slug == "ivr_credit_spread":
        atm_iv   = row.get("ATM IV", "—")
        ivr      = row.get("IVR", "—")
        vrp      = row.get("VRP", "—")
        hv20     = row.get("HV20", "—")
        iv_hv    = row.get("IV/HV", "—")
        trend    = row.get("Trend", "—")
        sp_type  = row.get("Spread Type", "—")
        spot     = float(row.get("Price") or 0)
        is_bull  = "Bull" in str(sp_type)
        signal   = f"{sp_type} — sell premium into elevated IV (IVR {ivr})"

        # Fetch real options chain from Polygon
        ivr_chain = None
        ivr_err   = None
        try:
            from app import get_polygon_api_key
            from data.polygon_client import PolygonClient
            import datetime as _dt
            api_key = get_polygon_api_key()
            if api_key and spot > 0:
                client  = PolygonClient(api_key=api_key)
                today_d = _dt.date.today()
                exp_lo  = (today_d + _dt.timedelta(days=21)).isoformat()
                exp_hi  = (today_d + _dt.timedelta(days=45)).isoformat()
                opt_type = "put" if is_bull else "call"
                chain = client.get_options_chain(
                    ticker,
                    expiration_date_gte=exp_lo,
                    expiration_date_lte=exp_hi,
                    strike_price_gte=spot * 0.85,
                    strike_price_lte=spot * 1.15,
                )
                if chain is not None and not chain.empty:
                    legs_df = chain[chain["type"] == opt_type].copy()
                    legs_df["delta_abs"] = legs_df["delta"].abs()
                    if not legs_df.empty:
                        # Short leg: delta ≈ 0.35 (ATM-ish)
                        short_leg = legs_df.loc[(legs_df["delta_abs"] - 0.35).abs().idxmin()]
                        short_k   = float(short_leg["strike"])
                        # Long leg (wing): OTM beyond short leg, delta ≈ 0.15
                        if is_bull:
                            wing_df = legs_df[legs_df["strike"] < short_k].copy()
                        else:
                            wing_df = legs_df[legs_df["strike"] > short_k].copy()
                        long_leg = wing_df.loc[(wing_df["delta_abs"] - 0.15).abs().idxmin()] if not wing_df.empty else None

                        def _mid(r):
                            try:
                                b, a = float(r["bid"]), float(r["ask"])
                                return round((b + a) / 2, 2)
                            except Exception:
                                return None

                        short_mid = _mid(short_leg)
                        long_mid  = _mid(long_leg) if long_leg is not None else None
                        long_k    = float(long_leg["strike"]) if long_leg is not None else None
                        net_credit = round((short_mid or 0) - (long_mid or 0), 2)
                        ivr_chain = {
                            "short_k":     short_k,
                            "short_mid":   short_mid,
                            "long_k":      long_k,
                            "long_mid":    long_mid,
                            "net_credit":  net_credit,
                            "opt_type":    opt_type,
                            "best_exp":    str(short_leg["expiration"]),
                            "dte_used":    int(short_leg["dte"]) if short_leg.get("dte") else 30,
                            "short_delta": round(float(short_leg["delta"]), 2) if short_leg.get("delta") == short_leg.get("delta") else None,
                        }
        except Exception as _e:
            ivr_err = str(_e)

        # Build legs table
        chain_info = html.Div()
        if ivr_chain:
            c = ivr_chain
            stype_label = "PUT" if is_bull else "CALL"
            _sm  = f"${c['short_mid']:.2f}"  if c.get("short_mid")  else "—"
            _lm  = f"${c['long_mid']:.2f}"   if c.get("long_mid")   else "—"
            _nc  = f"${c['net_credit']:.2f}"  if c.get("net_credit") is not None else "—"
            _sk  = f"${c['short_k']:.0f}"    if c.get("short_k")   else "—"
            _lk  = f"${c['long_k']:.0f}"     if c.get("long_k")    else "—"
            spread_w = abs((c.get("long_k") or 0) - (c.get("short_k") or 0))
            max_loss = round((spread_w - (c.get("net_credit") or 0)) * 100, 2)

            # Payoff chart
            xs = [round(spot * (1 + p / 100), 2) for p in range(-20, 21)]
            nc100 = (c.get("net_credit") or 0) * 100
            sk, lk = c.get("short_k") or spot, c.get("long_k") or spot
            ys = []
            for x in xs:
                if is_bull:  # bull put spread profits when price > short put strike
                    if x >= sk:
                        pnl = nc100
                    elif x <= lk:
                        pnl = -max_loss
                    else:
                        pnl = nc100 - (sk - x) * 100
                else:  # bear call spread profits when price < short call strike
                    if x <= sk:
                        pnl = nc100
                    elif x >= lk:
                        pnl = -max_loss
                    else:
                        pnl = nc100 - (x - sk) * 100
                ys.append(round(pnl, 2))

            chart = dcc.Graph(
                figure={
                    "data": [{"type": "scatter", "x": xs, "y": ys,
                               "mode": "lines", "name": "P&L",
                               "line": {"color": "#6366f1", "width": 2},
                               "fill": "tozeroy",
                               "fillcolor": "rgba(99,102,241,0.08)"}],
                    "layout": {
                        "paper_bgcolor": "transparent", "plot_bgcolor": "transparent",
                        "font": {"color": "#e5e7eb", "size": 11},
                        "height": 200, "margin": {"l": 50, "r": 20, "t": 20, "b": 40},
                        "xaxis": {"gridcolor": "#374151", "title": "Spot Price ($)"},
                        "yaxis": {"gridcolor": "#374151", "title": "P&L ($)",
                                  "zeroline": True, "zerolinecolor": "#6b7280"},
                        "shapes": [{"type": "line", "x0": spot, "x1": spot,
                                    "y0": min(ys)*1.15, "y1": max(ys)*1.15,
                                    "line": {"color": "#9ca3af", "dash": "dot", "width": 1}}],
                    },
                },
                config={"displayModeBar": False},
                style={"marginTop": "10px"},
            )

            chain_info = html.Div([
                html.Div(f"{stype_label} SPREAD", style={"color": T.TEXT_MUTED, "fontSize": "10px",
                                                         "fontWeight": "700", "letterSpacing": "0.07em",
                                                         "marginBottom": "6px"}),
                _mrt_grid_shared(
                    data=[
                        {"Leg": f"Short {opt_type} (ATM)",  "Strike": _sk, "Mid": _sm, "Action": "SELL",
                         "$/Contract": f"+${(c['short_mid'] or 0)*100:.2f}" if c.get("short_mid") else "—"},
                        {"Leg": f"Long {opt_type} (wing)",  "Strike": _lk, "Mid": _lm, "Action": "BUY",
                         "$/Contract": f"-${(c['long_mid'] or 0)*100:.2f}" if c.get("long_mid") else "—"},
                        {"Leg": "NET CREDIT", "Strike": "", "Mid": "", "Action": "",
                         "$/Contract": f"+${(c['net_credit'] or 0)*100:.2f}" if c.get("net_credit") else "—"},
                    ],
                    col_defs=[
                        {"field": "Leg"},
                        {"field": "Strike"},
                        {"field": "Mid"},
                        {"field": "Action"},
                        {"field": "$/Contract"},
                    ],
                    height=200,
                    enable_pagination=False,
                ),
                html.Div(
                    f"Expiry: {c['best_exp']}  ({c['dte_used']} DTE)  ·  "
                    f"Short delta: {c['short_delta']}  ·  Max loss: ${max_loss:.0f}/contract",
                    style={"color": T.TEXT_MUTED, "fontSize": "11px"},
                ),
            ], style={"marginTop": "12px"})

            # Inject into details for paper trade
            row["_chain"] = {
                "short_k":    c["short_k"],    "short_mid":  c["short_mid"],
                "long_k":     c["long_k"],     "long_mid":   c["long_mid"],
                "net_credit": c["net_credit"], "best_exp":   c["best_exp"],
                "dte_used":   c["dte_used"],   "opt_type":   opt_type,
            }
        elif ivr_err:
            chain_info = html.P(f"Chain error: {ivr_err}",
                                style={"color": T.WARNING, "fontSize": "12px"})
        else:
            chain_info = html.P("No Polygon data — set POLYGON_API_KEY to see real strikes.",
                                style={"color": T.TEXT_MUTED, "fontSize": "12px"})

        legs_table = chain_info   # wire into final layout

        metrics  = _row(
            _mc("ATM IV",     str(atm_iv)),
            _mc("IVR",        str(ivr),  T.SUCCESS if status == "Trade-Ready" else T.TEXT_PRIMARY),
            _mc("VRP",        str(vrp)),
            _mc("HV20",       str(hv20)),
            _mc("IV/HV",      str(iv_hv)),
            _mc("Trend",      str(trend)),
            _mc("Spread Type",str(sp_type)),
            _mc("Status",     status, status_color),
        )

    elif slug == "vol_arbitrage":
        atm_iv = row.get("ATM IV", "—")
        hv20   = row.get("HV20", "—")
        iv_hv  = row.get("IV/HV", "—")
        vrp    = row.get("VRP", "—")
        ivr    = row.get("IVR", "—")
        try:
            ratio_f = float(str(iv_hv) or 0)
        except Exception:
            ratio_f = 0
        signal = (f"Sell straddle/strangle — IV {ratio_f:.1f}× HV, collect the vol premium"
                  if ratio_f >= 1.3 else "IV/HV spread insufficient for arb")
        metrics = _row(
            _mc("ATM IV", str(atm_iv)),
            _mc("HV20",   str(hv20)),
            _mc("IV/HV",  str(iv_hv),
                T.SUCCESS if ratio_f >= 1.3 else T.TEXT_PRIMARY),
            _mc("VRP",    str(vrp)),
            _mc("IVR",    str(ivr)),
            _mc("Status", status, status_color),
        )

    elif slug == "broken_wing_butterfly":
        atm_iv   = row.get("ATM IV", "—")
        ivr      = row.get("IVR", "—")
        vix      = row.get("VIX", "—")
        adx      = row.get("ADX", "—")
        narrow_w = row.get("Narrow Wing", "—")
        wide_w   = row.get("Wide Wing", "—")
        price    = float(str(row.get("Price", 0)) or 0)
        try:
            nw = float(str(narrow_w) or 0)
            ww = float(str(wide_w)   or 0)
        except Exception:
            nw = ww = 0
        # Risk metrics (rough — no live chain)
        credit_rough = (0.20 + price * 0.015 * 0.1) if (price > 0 and nw > 0) else 0.0
        max_profit_rough = (nw + credit_rough) * 100 if nw > 0 else None
        max_loss_rough   = max((ww - nw - credit_rough), 0) * 100 if (ww > nw) else None
        signal  = ("Net-credit BWB entry — IVR low, range-bound. Pin at body for max profit."
                   if status == "Trade-Ready" else "Conditions not fully met — monitor")
        metrics = html.Div([
            _row(
                _mc("ATM IV",     str(atm_iv)),
                _mc("IVR",        str(ivr)),
                _mc("VIX",        str(vix)),
                _mc("ADX",        str(adx)),
                _mc("Narrow Wing",str(narrow_w)),
                _mc("Wide Wing",  str(wide_w)),
                _mc("Status",     status, status_color),
            ),
            _row(
                _mc("~Net Credit", f"+${credit_rough * 100:.0f} / contract" if credit_rough > 0 else "—", T.SUCCESS),
                _mc("Max Profit",  f"+${max_profit_rough:.0f} / contract"   if max_profit_rough else "—", T.SUCCESS),
                _mc("Max Loss",    f"-${max_loss_rough:.0f} / contract"     if max_loss_rough else "—",   T.DANGER),
                _mc("Wide Wing Stop", f"within $1 of ${price * 1.10:.0f}" if price > 0 else "—",         T.WARNING),
            ),
        ])
        # Legs table + P&L chart
        chart = html.Div()
        if price > 0 and nw > 0 and ww > 0:
            body_k   = round(price * 1.005 / nw) * nw
            long1_k  = body_k - nw
            short_k  = body_k
            long2_k  = body_k + ww
            credit   = credit_rough
            legs_table = _make_legs_table([
                {"Leg": "Long call (lower wing)", "Strike": f"${long1_k:.0f}", "Action": "BUY",  "~/Contract": f"-${credit * 30:.2f}"},
                {"Leg": "Short call × 2 (body)",  "Strike": f"${short_k:.0f}", "Action": "SELL", "~/Contract": f"+${credit * 80:.2f}"},
                {"Leg": "Long call (wide wing)",  "Strike": f"${long2_k:.0f}", "Action": "BUY",  "~/Contract": f"-${credit * 30:.2f}"},
                {"Leg": "NET CREDIT",             "Strike": "",               "Action": "",     "~/Contract": f"+${credit * 100:.2f}"},
            ])
            spots    = np.linspace(price * 0.75, price * 1.30, 300)
            def _bwb_pnl(s):
                c1 = max(0, s - long1_k)     # long call lower wing  (×1)
                c2 = -2 * max(0, s - short_k) # short calls at body   (×2)
                c3 = max(0, s - long2_k)      # long call wide wing   (×1) — caps loss above
                return (c1 + c2 + c3 + credit) * 100
            pnl = [_bwb_pnl(s) for s in spots]
            max_profit = max(pnl)
            chart = _sig_chart(spots, pnl, price, ticker, "Broken Wing Butterfly",
                               -(ww - nw - credit) * 100, max_profit, 0.75 * max_profit)

    elif slug == "calendar_spread":
        atm_iv = row.get("ATM IV", "—")
        hv20   = row.get("HV20", "—")
        vrp    = row.get("VRP", "—")
        ivr    = row.get("IVR", "—")
        vix    = row.get("VIX", "—")
        adx    = row.get("ADX", "—")
        price  = float(str(row.get("Price", 0)) or 0)
        try:
            iv_f_cal = float(str(atm_iv).rstrip("%")) / 100 if "%" in str(atm_iv) else float(str(atm_iv) or 0.25)
        except Exception:
            iv_f_cal = 0.25
        debit_rough = price * iv_f_cal * (25 / 252) ** 0.5 * 0.3 if price > 0 else 0.0
        signal = ("Sell front-month, buy back-month — VRP positive, range-bound."
                  if status == "Trade-Ready" else "Conditions not fully met — monitor")
        metrics = html.Div([
            _row(
                _mc("ATM IV", str(atm_iv)),
                _mc("HV20",   str(hv20)),
                _mc("VRP",    str(vrp),  T.SUCCESS if vrp not in ("—", None) else T.TEXT_MUTED),
                _mc("IVR",    str(ivr)),
                _mc("VIX",    str(vix)),
                _mc("ADX",    str(adx)),
                _mc("Status", status, status_color),
            ),
            _row(
                _mc("~Net Debit",  f"-${debit_rough * 0.4 * 100:.0f} / contract" if debit_rough > 0 else "—", T.WARNING),
                _mc("Max Loss",    f"-${debit_rough * 0.4 * 100:.0f} / contract" if debit_rough > 0 else "—", T.DANGER),
                _mc("Max Profit",  f"+${debit_rough * 0.7 * 100:.0f} / contract" if debit_rough > 0 else "—", T.SUCCESS),
                _mc("Risk Note",   "Defined — lose debit only", T.TEXT_MUTED),
            ),
        ])
        # Calendar spread P&L is IV-dependent; show a tent-shaped approximation
        price = float(str(row.get("Price", 0)) or 0)
        chart = html.Div()
        if price > 0:
            try:
                iv_f = float(str(atm_iv).rstrip("%")) / 100 if "%" in str(atm_iv) else float(str(atm_iv) or 0.25)
            except Exception:
                iv_f = 0.25
            debit      = price * iv_f * (25 / 252) ** 0.5 * 0.3   # rough debit
            legs_table = _make_legs_table([
                {"Leg": "Sell front-month ATM",  "Strike": f"${price:.0f}", "Action": "SELL", "~/Contract": f"+${debit * 0.6 * 100:.2f}"},
                {"Leg": "Buy back-month ATM",    "Strike": f"${price:.0f}", "Action": "BUY",  "~/Contract": f"-${debit * 1.0 * 100:.2f}"},
                {"Leg": "NET DEBIT",             "Strike": "",              "Action": "",     "~/Contract": f"-${debit * 0.4 * 100:.2f}"},
            ])
            spots   = np.linspace(price * 0.85, price * 1.15, 300)
            def _cal_pnl(s):
                dist = abs(s - price) / price
                return (debit * max(0, 1 - dist / (iv_f * 0.5)) - debit * 0.3) * 100
            pnl = [_cal_pnl(s) for s in spots]
            chart = _sig_chart(spots, pnl, price, ticker, "Calendar Spread",
                               -debit * 100, debit * 0.7 * 100, debit * 0.3 * 100)

    elif slug == "earnings_straddle":
        atm_iv  = row.get("ATM IV", "—")
        ivr     = row.get("IVR", "—")
        dte_e   = row.get("Days to Earnings", "—")
        impl_mv = row.get("Impl. Move", "—")
        credit  = row.get("Straddle Credit", "—")
        price   = float(str(row.get("Price", 0)) or 0)
        try:
            cred_f = float(str(credit).lstrip("$") or 0)
        except Exception:
            cred_f = price * 0.05 if price > 0 else 0.0
        # Wing protection: buy OTM call + put at implied-move distance (~10% or impl_mv)
        try:
            impl_mv_f = float(str(impl_mv).rstrip("%")) / 100 if "%" in str(impl_mv) else float(str(impl_mv) or 0.08)
        except Exception:
            impl_mv_f = 0.08
        wing_dist    = max(impl_mv_f * 1.5, 0.10) * price if price > 0 else 0.0
        wing_cost_ps = cred_f * 0.20   # rough: OTM wing ≈ 20% of ATM value each
        net_cred_ps  = cred_f - 2 * wing_cost_ps
        max_loss_ps  = max(wing_dist / 100 - net_cred_ps, 0) * 100 if wing_dist > 0 else 0.0
        credit_display = f"${cred_f * 100:.0f} / contract" if cred_f > 0 else "—"
        net_cred_display = f"+${net_cred_ps * 100:.0f} / contract" if net_cred_ps > 0 else "—"
        max_loss_display = f"-${max_loss_ps:.0f} / contract" if max_loss_ps > 0 else "—"
        signal  = (f"Short iron condor — sell ATM straddle + buy OTM wings. Earnings in {dte_e} days, IV crush expected."
                   if status == "Trade-Ready" else "Outside earnings window or IV too low — monitor")
        metrics = html.Div([
            _row(
                _mc("ATM IV",           str(atm_iv)),
                _mc("IVR",              str(ivr),          T.SUCCESS if status == "Trade-Ready" else T.TEXT_MUTED),
                _mc("Days to Earnings", str(dte_e)),
                _mc("Impl. Move",       str(impl_mv)),
                _mc("Straddle Credit",  credit_display),
                _mc("Status",           status, status_color),
            ),
            _row(
                _mc("Net Credit (w/ wings)", net_cred_display,  T.SUCCESS),
                _mc("Max Loss",              max_loss_display,  T.DANGER),
                _mc("Wing Distance",         f"±{wing_dist:.0f}" if wing_dist > 0 else "—", T.WARNING),
                _mc("Structure",             "Short Iron Condor — defined risk", T.TEXT_MUTED),
            ),
        ])
        chart = html.Div()
        if price > 0 and cred_f > 0:
            call_wing_k = price + wing_dist
            put_wing_k  = price - wing_dist
            legs_table = _make_legs_table([
                {"Leg": "Long OTM call (wing)",  "Strike": f"${call_wing_k:.0f}", "Action": "BUY",  "~/Contract": f"-${wing_cost_ps * 100:.2f}"},
                {"Leg": "Short ATM call",        "Strike": f"${price:.0f}",       "Action": "SELL", "~/Contract": f"+${cred_f * 50:.2f}"},
                {"Leg": "Short ATM put",         "Strike": f"${price:.0f}",       "Action": "SELL", "~/Contract": f"+${cred_f * 50:.2f}"},
                {"Leg": "Long OTM put (wing)",   "Strike": f"${put_wing_k:.0f}",  "Action": "BUY",  "~/Contract": f"-${wing_cost_ps * 100:.2f}"},
                {"Leg": "NET CREDIT",            "Strike": "",                    "Action": "",     "~/Contract": f"+${net_cred_ps * 100:.2f}"},
            ])
            spots = np.linspace(price * 0.70, price * 1.30, 300)
            def _strad_pnl(s):
                short_call = -max(0, s - price)
                short_put  = -max(0, price - s)
                long_call  =  max(0, s - call_wing_k)
                long_put   =  max(0, put_wing_k - s)
                return (net_cred_ps + short_call + short_put + long_call + long_put) * 100
            pnl = [_strad_pnl(s) for s in spots]
            chart = _sig_chart(spots, pnl, price, ticker, "Earnings Short Condor (IV Crush)",
                               min(pnl), net_cred_ps * 100, net_cred_ps * 0.5 * 100,
                               stop_level=-net_cred_ps * 2 * 100)

    elif slug == "wheel_strategy":
        ma50    = row.get("MA50", "—")
        atm_iv  = row.get("ATM IV", "—")
        ivr     = row.get("IVR", "—")
        put_k   = row.get("Put Strike", "—")
        premium = row.get("~Premium", "—")
        adx     = row.get("ADX", "—")
        price   = float(str(row.get("Price", 0)) or 0)
        try:
            _prem_ps = float(str(premium).lstrip("$") or 0)
            premium_display = f"${_prem_ps * 100:.0f} / contract"
        except Exception:
            premium_display = str(premium)
        signal  = (f"Sell protected put spread at {put_k} — IVR elevated, above MA50."
                   if status == "Trade-Ready" else "Conditions not fully met — monitor")
        try:
            pk_pre    = float(str(put_k)  or 0)
            prem_pre  = float(str(premium).lstrip("$") or 0)
            # Add a long OTM put wing ~5% below short strike to cap downside
            long_k_pre  = round(pk_pre * 0.95, 1)
            wing_cost_pre = round(prem_pre * 0.25, 2)   # estimate long put ≈ 25% of credit
            net_cred_pre  = round(prem_pre - wing_cost_pre, 2)
            spread_width  = round(pk_pre - long_k_pre, 1)
            wheel_max_loss = round((spread_width - net_cred_pre) * 100, 0)
            wheel_be       = round(pk_pre - net_cred_pre, 2)
        except Exception:
            pk_pre = prem_pre = long_k_pre = wing_cost_pre = 0.0
            net_cred_pre = None; wheel_max_loss = None; wheel_be = None
        net_credit_display = f"${net_cred_pre * 100:.0f} / contract" if net_cred_pre else "—"
        be_display         = f"${wheel_be:,.2f}"     if wheel_be      else "—"
        metrics = html.Div([
            _row(
                _mc("ATM IV",    str(atm_iv)),
                _mc("IVR",       str(ivr),     T.SUCCESS if status == "Trade-Ready" else T.TEXT_MUTED),
                _mc("MA50",      str(ma50)),
                _mc("Put Strike",str(put_k)),
                _mc("~Premium",  premium_display, T.SUCCESS),
                _mc("ADX",       str(adx)),
                _mc("Status",    status, status_color),
            ),
            _row(
                _mc("Net Credit", net_credit_display, T.SUCCESS),
                _mc("Breakeven",  be_display,          T.WARNING),
                _mc("Max Loss",   f"-${wheel_max_loss:,.0f} / contract" if wheel_max_loss else "—", T.DANGER),
                _mc("Long Put",   f"${long_k_pre:.0f} wing — caps downside" if long_k_pre else "—", T.WARNING),
            ),
        ])
        chart = html.Div()
        if price > 0:
            try:
                pk      = float(str(put_k) or price * 0.90)
                prem    = float(str(premium).lstrip("$") or price * 0.02)
                long_k  = round(pk * 0.95, 1)
                wing_cost = round(prem * 0.25, 2)
                net_cred  = round(prem - wing_cost, 2)
            except Exception:
                pk = price * 0.90; prem = price * 0.02
                long_k = pk * 0.95; wing_cost = prem * 0.25; net_cred = prem - wing_cost
            legs_table = _make_legs_table([
                {"Leg": "Short put (CSP)",  "Strike": f"${pk:.0f}",     "Action": "SELL", "~/Contract": f"+${prem * 100:.2f}"},
                {"Leg": "Long put (wing)",  "Strike": f"${long_k:.0f}", "Action": "BUY",  "~/Contract": f"-${wing_cost * 100:.2f}"},
                {"Leg": "NET CREDIT",       "Strike": "",               "Action": "",     "~/Contract": f"+${net_cred * 100:.2f}"},
            ])
            spots = np.linspace(price * 0.70, price * 1.15, 300)
            def _wheel_pnl(s):
                short_put = -max(0, pk - s)
                long_put  =  max(0, long_k - s)
                return (net_cred + short_put + long_put) * 100
            pnl = [_wheel_pnl(s) for s in spots]
            true_max_loss = -(pk - long_k - net_cred) * 100
            chart = _sig_chart(spots, pnl, price, ticker, "Wheel — Protected Put Spread",
                               true_max_loss, net_cred * 100, net_cred * 0.5 * 100,
                               stop_level=-net_cred * 2 * 100)

    elif slug == "bull_put_spread":
        ma50    = row.get("MA50", "—")
        atm_iv  = row.get("ATM IV", "—")
        ivr     = row.get("IVR", "—")
        short_k = row.get("Short Strike", "—")
        long_k  = row.get("Long Strike", "—")
        width   = row.get("Width", "—")
        credit  = row.get("~Credit", "—")
        cw_r    = row.get("Credit/Width", "—")
        price   = float(str(row.get("Price", 0)) or 0)
        try:
            _cred_ps = float(str(credit).lstrip("$") or 0)
            credit_display = f"${_cred_ps * 100:.0f} / contract"
        except Exception:
            credit_display = str(credit)
        signal  = (f"Sell put spread {short_k}/{long_k} — bullish, IVR elevated, price above MA50."
                   if status == "Trade-Ready" else "Conditions not fully met — monitor")
        try:
            sk_pre   = float(str(short_k) or 0)
            lk_pre   = float(str(long_k)  or 0)
            cred_pre = float(str(credit).lstrip("$") or 0)
            w_pre    = sk_pre - lk_pre
            bps_max_loss   = (w_pre - cred_pre) * 100
            bps_net_credit = cred_pre * 100
        except Exception:
            bps_max_loss = bps_net_credit = None
        metrics = html.Div([
            _row(
                _mc("ATM IV",      str(atm_iv)),
                _mc("IVR",         str(ivr),    T.SUCCESS if status == "Trade-Ready" else T.TEXT_MUTED),
                _mc("MA50",        str(ma50)),
                _mc("Short Strike",str(short_k)),
                _mc("Long Strike", str(long_k)),
                _mc("~Credit",     credit_display, T.SUCCESS),
                _mc("Credit/Width",str(cw_r)),
                _mc("Status",      status, status_color),
            ),
            _row(
                _mc("Net Credit", f"+${bps_net_credit:.0f} / contract" if bps_net_credit else "—", T.SUCCESS),
                _mc("Max Loss",   f"-${bps_max_loss:.0f} / contract"   if bps_max_loss   else "—", T.DANGER),
                _mc("Structure",  "Bull Put Spread — defined risk",  T.TEXT_MUTED),
            ),
        ])
        chart = html.Div()
        if price > 0:
            try:
                sk   = float(str(short_k) or price * 0.92)
                lk   = float(str(long_k)  or price * 0.87)
                cred = float(str(credit).lstrip("$") or 1.0)
                w    = sk - lk
            except Exception:
                sk = price * 0.92; lk = price * 0.87; cred = 1.0; w = sk - lk
            legs_table = _make_legs_table([
                {"Leg": "Short put (income)",    "Strike": f"${sk:.0f}", "Action": "SELL", "~/Contract": f"+${cred * 100:.2f}"},
                {"Leg": "Long put (protection)", "Strike": f"${lk:.0f}", "Action": "BUY",  "~/Contract": f"-${(w - cred) * 100:.2f}"},
                {"Leg": "NET CREDIT",            "Strike": "",           "Action": "",     "~/Contract": f"+${cred * 100:.2f}"},
            ])
            spots = np.linspace(price * 0.75, price * 1.15, 300)
            def _bps_pnl(s):
                short_put = -max(0, sk - s)
                long_put  =  max(0, lk - s)
                return (cred + short_put + long_put) * 100
            pnl = [_bps_pnl(s) for s in spots]
            chart = _sig_chart(spots, pnl, price, ticker, "Bull Put Spread",
                               -(w - cred) * 100, cred * 100, cred * 0.5 * 100,
                               stop_level=-cred * 2 * 100)

    elif slug == "put_steal":
        price    = float(str(row.get("Price", 0)) or 0)
        nii      = row.get("NII", "—")
        strike_x = row.get("Strike X", "—")
        atm_iv   = row.get("ATM IV", "—")
        ivr      = row.get("IVR", "—")
        vix_val  = row.get("VIX", "—")
        # Prefer real Polygon chain data
        chain    = row.get("_chain") or {}
        iv_src   = row.get("IV Src", "~BS est.")
        short_k  = chain.get("short_put_k")  or row.get("Short Put", "—")
        long_k   = chain.get("long_put_k")   or row.get("Long Put",  "—")
        exp_date = chain.get("best_exp",      row.get("Expiry", ""))
        dte_used = chain.get("dte_used",      21)
        short_mid = chain.get("short_put_mid", None)
        long_mid  = chain.get("long_put_mid",  None)
        net_cred  = chain.get("net_credit",    None)
        ml_chain  = chain.get("max_loss",      None)  # already positive dollars/share
        chain_err = row.get("_chain_err", "")
        try:
            nii_f  = float(str(nii))
            nii_color = T.SUCCESS if nii_f > 0.05 else T.WARNING if nii_f > 0 else T.DANGER
        except Exception:
            nii_f = 0.0; nii_color = T.TEXT_MUTED
        # Numeric strikes/credit — prefer chain floats, else parse display strings
        try:
            sk = float(short_k) if isinstance(short_k, (int, float)) else float(str(short_k).lstrip("$") or 0)
            lk = float(long_k)  if isinstance(long_k,  (int, float)) else float(str(long_k).lstrip("$")  or 0)
        except Exception:
            sk = lk = 0.0
        if net_cred is not None:
            cred_f = float(net_cred)
        else:
            try:
                cred_f = float(str(row.get("~Credit", "0")).lstrip("$") or 0)
            except Exception:
                cred_f = 0.0
        wing     = sk - lk
        max_prof = cred_f * 100
        max_loss_v = ml_chain * 100 if ml_chain is not None else (wing - cred_f) * 100 if wing > 0 else None
        src_badge = html.Span(
            f" [{iv_src}]",
            style={"color": T.SUCCESS if iv_src == "Polygon" else T.WARNING, "fontSize": "11px"},
        )
        exp_label = f"{exp_date}  ({dte_used}d)" if exp_date else "—"
        signal = (f"Sell bull put ${sk:.0f}/${lk:.0f} exp {exp_date} — NII={nii} (early exercise edge open)"
                  if status == "Trade-Ready" else "NII edge not wide enough — monitor")
        if chain_err:
            signal += f"  ⚠ chain: {chain_err}"
        metrics = html.Div([
            _row(
                _mc("NII",       str(nii),    nii_color),
                _mc("Strike X",  str(strike_x)),
                _mc("Expiry",    exp_label),
                _mc("ATM IV",    str(atm_iv)),
                _mc("IVR",       str(ivr)),
                _mc("VIX",       str(vix_val)),
                _mc("Status",    status, status_color),
            ),
            _row(
                _mc("Net Credit", f"+${max_prof:.0f} / contract" if max_prof else "—", T.SUCCESS),
                _mc("Max Loss",   f"-${max_loss_v:.0f} / contract" if max_loss_v else "—", T.DANGER),
                _mc("Data Src",   iv_src, T.SUCCESS if iv_src == "Polygon" else T.WARNING),
                _mc("Structure",  "Bull Put Spread — defined risk", T.TEXT_MUTED),
            ),
        ])
        chart = html.Div()
        if price > 0 and sk > 0 and lk > 0 and cred_f > 0:
            def _fmt_leg(v):
                if v is None: return "—"
                v100 = v * 100
                if v100 < 0.01:
                    return "~$0  (far OTM)"
                return f"${v100:.2f}"
            sp_mid = short_mid if short_mid is not None else cred_f + (long_mid or 0)
            lp_mid = long_mid  if long_mid  is not None else max(0, sp_mid - cred_f)
            legs_table = _make_legs_table([
                {"Leg": "Short put (income)",    "Strike": f"${sk:.2f}", "Action": "SELL", "~/Contract": f"+{_fmt_leg(sp_mid)}"},
                {"Leg": "Long put (protection)", "Strike": f"${lk:.2f}", "Action": "BUY",  "~/Contract": f"-{_fmt_leg(lp_mid)}"},
                {"Leg": "NET CREDIT",            "Strike": "",           "Action": "",     "~/Contract": f"+${cred_f * 100:.2f}"},
            ])
            spots = np.linspace(price * 0.75, price * 1.15, 300)
            def _ps_pnl(s):
                return (cred_f - max(0, sk - s) + max(0, lk - s)) * 100
            pnl = [_ps_pnl(s) for s in spots]
            ml_for_chart = max_loss_v if max_loss_v else (wing - cred_f) * 100
            chart = _sig_chart(spots, pnl, price, ticker, "Put Steal — Bull Put Spread",
                               -ml_for_chart, max_prof, max_prof * 0.5,
                               stop_level=-cred_f * 2 * 100)

    elif slug == "hmm_regime":
        state    = row.get("State", "—")
        p_state  = row.get("P(state)", "—")
        regime   = row.get("Regime", "—")
        trade    = row.get("Trade", "—")
        sig_val  = row.get("Signal", "—")
        mode     = row.get("Mode", "—")
        vix_val  = row.get("VIX", "—")
        ivr      = row.get("IVR", "—")
        ret5d    = row.get("5d Ret", "—")
        ret20d   = row.get("20d Ret", "—")
        rv20     = row.get("RV20", "—")
        spot_val = row.get("Price", 0)

        state_color = (T.SUCCESS if str(state) == "0" else
                       T.WARNING if str(state) == "1" else
                       T.DANGER  if str(state) == "2" else T.TEXT_MUTED)
        sig_color = (T.SUCCESS if str(sig_val).upper() == "SELL" else
                     T.ACCENT  if str(sig_val).upper() == "BUY"  else T.TEXT_MUTED)
        try:
            p_float = float(p_state)
        except Exception:
            p_float = 0.0
        conv_color = (T.SUCCESS if p_float >= 0.60 else
                      T.WARNING if p_float >= 0.50 else T.DANGER)

        # ── Regime status row (state classification context) ──────────────
        regime_status = html.Div([
            _row(
                _mc("State",     str(state),    state_color),
                _mc("Regime",    str(regime)),
                _mc("P(state)",  str(p_state),  conv_color),
                _mc("Signal",    str(sig_val),  sig_color),
                _mc("Mode",      str(mode),     T.WARNING if str(mode) == "heuristic" else T.SUCCESS),
                _mc("VIX",       str(vix_val)),
                _mc("IVR",       str(ivr)),
            ),
        ], style={"marginBottom": "14px"})

        # ── Try to build state-specific trade preview (payoff diagram) ────
        try:
            spot_f = float(spot_val) if spot_val not in ("—", None, "") else 0.0
            vix_f  = float(vix_val) if vix_val not in ("—", None, "") else 0.0
            state_i = int(state) if str(state).isdigit() else -1
            preview = _hmm_trade_preview(state_i, spot_f, vix_f, ticker)
        except Exception:
            preview = None

        if preview is not None:
            # Trade preview metrics + leg table + payoff diagram
            preview_metrics = preview["metrics"]
            legs_table = preview["legs_table"]
            chart      = preview["chart"]

            # Disclaimer banner about IV proxy mode
            disclaimer = html.Div([
                html.Span("ℹ️ ", style={"fontSize": "13px"}),
                html.Span(
                    "Strikes computed via BS delta inversion at IV proxy = VIX / 100. "
                    "Real fills will differ — verify against your broker chain before paper-trading."
                    if str(mode) == "heuristic" else
                    "Model mode active. Strikes computed via BS at IV proxy.",
                    style={"color": T.TEXT_MUTED, "fontSize": "11px", "fontStyle": "italic"},
                ),
            ], style={"marginBottom": "12px", "padding": "8px 12px",
                       "backgroundColor": "rgba(99,102,241,0.08)",
                       "border": f"1px solid {T.BORDER}",
                       "borderLeft": f"3px solid {T.ACCENT}",
                       "borderRadius": "4px"})

            # Combine regime status + disclaimer + trade metrics into the metrics slot
            metrics = html.Div([regime_status, disclaimer, preview_metrics])
        else:
            # Fall back to status-only view if spot/vix are degenerate
            metrics = html.Div([
                regime_status,
                html.P(f"Unable to render trade preview: spot={spot_val}, vix={vix_val}",
                       style={"color": T.WARNING, "fontSize": "12px"}),
            ])

        signal = f"{sig_val} — {trade}"

    else:  # gex_positioning
        regime  = row.get("Regime", "—")
        sig     = row.get("Signal", "—")
        weight  = row.get("SPY Weight", "—")
        atr     = row.get("ATR%", "—")
        ret5d   = row.get("5d Return", "—")
        label_r = row.get("Regime Label", "—")
        vix_val = row.get("VIX", "—")
        price   = float(str(row.get("Price", 0)) or 0)
        sig_color = (T.SUCCESS if str(sig).upper() == "LONG" else
                     T.DANGER  if str(sig).upper() == "SHORT" else T.TEXT_MUTED)
        signal  = str(label_r)
        # Parse current weight for highlight
        try:
            cur_weight_pct = float(str(weight).rstrip("%") or 0)
        except Exception:
            cur_weight_pct = 0.0
        # Position Value — SPY allocation on $100k example portfolio
        pos_val_display = f"${cur_weight_pct * 1000:.0f} / $100k portfolio" if cur_weight_pct > 0 else "—"
        cash_display    = f"${(100 - cur_weight_pct) * 1000:.0f} / $100k in cash" if cur_weight_pct > 0 else "—"
        metrics = html.Div([
            _row(
                _mc("Signal",     str(sig),    sig_color),
                _mc("Regime",     str(regime)),
                _mc("SPY Weight", str(weight), T.SUCCESS if cur_weight_pct >= 60 else
                                               T.WARNING if cur_weight_pct >= 35 else T.DANGER),
                _mc("VIX",        str(vix_val),
                    T.DANGER if float(str(vix_val) or 0) > 25 else
                    T.WARNING if float(str(vix_val) or 0) > 18 else T.SUCCESS),
                _mc("ATR%",       str(atr)),
                _mc("5d Return",  str(ret5d)),
                _mc("Status",     status, status_color),
            ),
            _row(
                _mc("Position Value", pos_val_display, T.SUCCESS if cur_weight_pct >= 60 else T.WARNING),
                _mc("Cash Reserve",   cash_display,    T.TEXT_MUTED),
                _mc("Risk Note",      "Equity + cash allocation — no options, no leverage", T.TEXT_MUTED),
            ),
        ])
        # Regime allocation ladder chart
        _regimes   = ["Deep Negative\n(VIX>30)", "Negative\n(VIX 22-30)",
                      "Neutral\n(VIX 18-22)", "Mild Positive\n(VIX 15-18)", "High Positive\n(VIX<15)"]
        _allocs    = [15, 35, 60, 80, 90]
        _colors    = ["#ef4444", "#f97316", "#f59e0b", "#84cc16", "#10b981"]
        _cur_regime_map = {
            "DeepNegative": 0, "Negative": 1, "Neutral": 2,
            "MildPositive": 3, "HighPositive": 4,
        }
        cur_idx = _cur_regime_map.get(str(regime), -1)
        bar_colors = [
            "#818cf8" if i == cur_idx else c
            for i, c in enumerate(_colors)
        ]
        gex_fig = go.Figure(go.Bar(
            x=_regimes,
            y=_allocs,
            marker_color=bar_colors,
            text=[f"{a}%" for a in _allocs],
            textposition="outside",
            textfont={"color": "#e2e8f0", "size": 12},
        ))
        if cur_idx >= 0:
            gex_fig.add_shape(
                type="rect",
                x0=cur_idx - 0.4, x1=cur_idx + 0.4,
                y0=0, y1=_allocs[cur_idx],
                fillcolor="rgba(129,140,248,0.15)",
                line={"color": "#818cf8", "width": 2},
            )
        gex_fig.add_hline(y=cur_weight_pct, line_dash="dash",
                          line_color="#f59e0b", line_width=1.5,
                          annotation_text=f"Current: {weight}",
                          annotation_font_color="#f59e0b", annotation_font_size=11)
        gex_fig.update_layout(
            title={"text": f"{ticker}  GEX Regime → SPY Allocation",
                   "font": {"size": 13, "color": "#e2e8f0"}, "x": 0.01},
            paper_bgcolor="#1e293b", plot_bgcolor="#1e293b",
            font={"color": "#94a3b8"},
            margin={"l": 40, "r": 20, "t": 40, "b": 60},
            height=300,
            yaxis={"title": "SPY Allocation %", "range": [0, 105],
                   "gridcolor": "rgba(255,255,255,0.06)", "ticksuffix": "%"},
            xaxis={"gridcolor": "rgba(255,255,255,0.06)"},
            showlegend=False,
        )
        chart = dcc.Graph(figure=gex_fig, config={"displayModeBar": False},
                          style={"marginTop": "12px"})

    score_val = row.get("Score", 0)
    score_color = (T.SUCCESS if float(str(score_val) or 0) >= 70 else
                   T.WARNING if float(str(score_val) or 0) >= 40 else T.DANGER)

    return html.Div([
        metrics,
        C.card([
            html.Div("Signal", style={"color": T.TEXT_MUTED, "fontSize": "10px",
                                      "fontWeight": "600", "textTransform": "uppercase",
                                      "marginBottom": "6px"}),
            html.Div(signal, style={"color": T.TEXT_PRIMARY, "fontSize": "13px"}),
        ], pad="sm"),
        legs_table,
        chart,
        html.Div([
            html.Span("Score  ", style={"color": T.TEXT_MUTED, "fontSize": "12px"}),
            html.Span(str(score_val), style={"color": score_color,
                                              "fontSize": "1.4rem", "fontWeight": "700"}),
            html.Span(" / 100", style={"color": T.TEXT_MUTED, "fontSize": "12px"}),
        ]),
    ])


@callback(
    Output("str-sig-modal", "is_open", allow_duplicate=True),
    Input("str-sig-modal-dismiss", "n_clicks"),
    prevent_initial_call=True,
)
def _dismiss_sig_modal(n):
    return False


for _slug in (
    "vix_spike_fade", "ivr_credit_spread", "vol_arbitrage", "gex_positioning",
    "broken_wing_butterfly", "calendar_spread", "earnings_straddle",
    "wheel_strategy", "bull_put_spread", "put_steal", "hmm_regime",
    "trend_following", "ts_momentum",
):
    _make_signal_callback(_slug)


# ── HMM Live Signal compute callback ──────────────────────────────────────────

@callback(
    Output("str-hmm_regime-live-signal-output", "children"),
    Input("str-hmm_regime-live-compute-btn", "n_clicks"),
    prevent_initial_call=True,
)
def _compute_hmm_live_signal(n_clicks):
    """Fetch the latest SPY + VIX bars, score the HMM heuristic, and render
    today's posterior + recommended trade. If a trained model pickle exists,
    use it for a full posterior; otherwise fall back to the VIX-bucket heuristic
    (same path as the strategy's `_heuristic_signal`)."""
    if not n_clicks:
        return no_update

    try:
        from app import get_polygon_api_key
        from engine.screener import _fetch_ohlcv, _score_hmm_regime
        from engine.iv_metrics import get_iv_metrics_batch

        api_key = get_polygon_api_key()
        if not api_key:
            return dbc.Alert(
                "No Polygon API key configured — set POLYGON_API_KEY in your env.",
                color="danger", style={"fontSize": "12px"},
            )

        # Fetch SPY OHLCV (60 bars is enough for rv20 + recent context)
        spy_df = _fetch_ohlcv("SPY", api_key, bars=60)
        if spy_df.empty:
            return dbc.Alert("Failed to fetch SPY data from Polygon.",
                              color="danger", style={"fontSize": "12px"})

        # Fetch VIX (DB-first, Polygon-fallback)
        vix_series = _get_vix_series(api_key)
        if vix_series is None or vix_series.empty:
            return dbc.Alert("No VIX data available (DB and Polygon both failed).",
                              color="danger", style={"fontSize": "12px"})

        # IV metrics (atm_iv, ivr)
        try:
            iv_metrics = get_iv_metrics_batch(["SPY"], spy_df.iloc[-1].name).get("SPY", {})
        except Exception:
            iv_metrics = {}

        # Score via heuristic — same code path the screener uses
        row = _score_hmm_regime("SPY", spy_df, vix_series, iv_metrics or {})
        if row is None:
            return dbc.Alert("Heuristic scoring returned no data — check data freshness.",
                              color="warning", style={"fontSize": "12px"})

        # Headline cards
        state    = row.get("State", "—")
        regime   = row.get("Regime", "—")
        p_state  = row.get("P(state)", 0.0)
        trade    = row.get("Trade", "—")
        signal   = row.get("Signal", "—")
        vix_now  = row.get("VIX", 0.0)
        ivr_now  = row.get("IVR") or 0.0
        spot     = row.get("Price", 0.0)

        state_color = (T.SUCCESS if str(state) == "0" else
                       T.WARNING if str(state) == "1" else
                       T.DANGER  if str(state) == "2" else T.TEXT_MUTED)
        conf_color = (T.SUCCESS if p_state >= 0.60 else
                      T.WARNING if p_state >= 0.50 else T.DANGER)

        def _chip(label, val, color=T.TEXT_PRIMARY):
            return C.metric_card(label, str(val), _TONE.get(color, "default"))

        # Entry-gate evaluation
        vix_ok  = vix_now <= 40.0
        conf_ok = p_state >= 0.60
        gates = [
            ("p_state >= 0.60",  conf_ok, f"{p_state:.2f}"),
            ("VIX <= 40",        vix_ok, f"{vix_now:.2f}"),
        ]
        gate_rows = []
        for name, ok, val in gates:
            ind = "✓" if ok else "✗"
            color = T.SUCCESS if ok else T.DANGER
            gate_rows.append(html.Div([
                html.Span(ind, style={"color": color, "fontWeight": "700",
                                       "marginRight": "8px",
                                       "fontFamily": "JetBrains Mono, monospace"}),
                html.Span(name, style={"color": T.TEXT_PRIMARY, "fontSize": "12px"}),
                html.Span(f"  →  {val}",
                          style={"color": T.TEXT_MUTED, "fontSize": "11px",
                                  "fontFamily": "JetBrains Mono, monospace"}),
            ], style={"marginBottom": "4px"}))

        all_pass = vix_ok and conf_ok
        verdict_color = T.SUCCESS if all_pass else T.WARNING
        verdict_text  = ("✅ ENTRY READY — would open " + str(trade)) if all_pass \
            else "⏸ HOLD — at least one gate failed"

        mode_text = row.get("Mode", "heuristic")
        status = row.get("Status", "")

        return html.Div([
            # Headline cards
            html.Div([
                _chip("State",     str(state),                    state_color),
                _chip("Regime",    regime),
                _chip("P(state)",  f"{p_state:.2f}",              conf_color),
                _chip("Trade",     trade,                         T.ACCENT),
                _chip("Signal",    signal,                        T.SUCCESS if signal == "SELL"
                                                                  else T.ACCENT),
                _chip("Mode",      mode_text,                     T.WARNING if mode_text == "heuristic"
                                                                  else T.SUCCESS),
            ], style={"display": "flex", "gap": "8px", "flexWrap": "wrap", "marginBottom": "12px"}),
            html.Div([
                _chip("Spot",   f"${spot:.2f}"),
                _chip("VIX",    f"{vix_now:.2f}"),
                _chip("IVR",    f"{(ivr_now or 0)*100:.1f}%" if ivr_now < 1 else f"{ivr_now:.1f}"),
            ], style={"display": "flex", "gap": "8px", "flexWrap": "wrap", "marginBottom": "12px"}),

            # Entry gate evaluation
            C.section("Entry gate check", gate_rows),

            # Verdict
            html.Div([
                html.Span(verdict_text, style={
                    "color": verdict_color, "fontSize": "13px", "fontWeight": "700"}),
            ], style={"marginBottom": "8px"}),

            html.P(status, style={"color": T.TEXT_MUTED, "fontSize": "11px",
                                    "fontStyle": "italic", "margin": "0"}),
        ])

    except Exception as e:
        logger.exception("hmm_regime compute live signal failed")
        return dbc.Alert(
            f"Compute failed: {e}",
            color="danger", style={"fontSize": "12px"},
        )
