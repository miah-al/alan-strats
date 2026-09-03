"""
app/pages/strategies/modals.py — the row-click detail modal + paper-trade callbacks.

One modal serves every strategy. Clicking a screener row opens it with a title
from the strategy's UI hook; the body comes from `StrategyUI.signal_body`
(falling back to a generic metrics view), and Paper Trade goes through
`StrategyUI.paper_trade` (falling back to the generic equity / options paths).
Importing this module registers all of those callbacks.
"""
from __future__ import annotations

import logging

from dash import html, callback, Input, Output, State, no_update

from app import theme as T
from app.ui import components as C
from app.ui.strategy_widgets import num as _num, metric as _mc, cards_row as _row
from alan_trader.strategy_api.registry import get_ui
from app.pages.strategies.registry import _SLUG_TO_LABEL, slugs as _slugs

logger = logging.getLogger(__name__)

_MIN_CREDIT_PER_SHARE = 0.05   # block credit trades below $0.05/share


# ── Row click → open modal ────────────────────────────────────────────────────

def _make_click_callback(slug: str):
    grid_id = f"str-{slug}-grid"

    # MRT bridge: row clicks come via the hidden input written by
    # assets/mrt_row_click.js. The payload is a JSON string with `rowIndex`.
    @callback(
        Output("str-sig-modal",       "is_open",  allow_duplicate=True),
        Output("str-sig-modal-title", "children", allow_duplicate=True),
        Output("str-sig-row-store",   "data",     allow_duplicate=True),
        Output("str-sig-paper-btn",   "disabled", allow_duplicate=True),
        Input(f"{grid_id}-clicked", "value"),
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
        ui = get_ui(slug)
        try:
            title = ui.modal_title(row)
        except Exception:
            title = row.get("Ticker", "")
        try:
            can_trade = bool(ui.can_paper_trade(row))
        except Exception:
            can_trade = False
        return True, title, row, not can_trade

    _open_modal.__name__ = f"_open_modal_{slug}"
    return _open_modal


for _slug in _slugs():
    if get_ui(_slug).modal:
        _make_click_callback(_slug)


# ── Modal body ────────────────────────────────────────────────────────────────

def _generic_signal_body(row: dict) -> html.Div:
    """Render whatever screener metrics the row carries so the popup always
    opens with useful detail rather than crashing."""
    status = row.get("Status", "—")
    status_color = (T.SUCCESS if status == "Trade-Ready" else
                    T.WARNING if status == "Partial" else T.DANGER)
    _skip = {"_slug", "all_pass", "n_pass", "Ticker", "Status", "Score", "score"}
    cards = []
    _px = row.get("Price")
    if isinstance(_px, (int, float)) and _px:
        cards.append(_mc("Price", f"${float(_px):,.2f}"))
    for _k, _v in row.items():
        if _k in _skip or str(_k).startswith("_") or _v in (None, "", "—"):
            continue
        cards.append(_mc(_k, _v))
    signal = str(row.get("Signal", row.get("Status", "—")))
    return _finish_body(row, html.Div([_mc("Status", status, status_color), _row(*cards[:8])]),
                        signal)


def _finish_body(row: dict, metrics, signal: str) -> html.Div:
    score_val = row.get("Score", 0)
    score_color = (T.SUCCESS if _num(score_val) >= 70 else
                   T.WARNING if _num(score_val) >= 40 else T.DANGER)
    return html.Div([
        metrics,
        C.card([
            html.Div("Signal", style={"color": T.TEXT_MUTED, "fontSize": "10px",
                                      "fontWeight": "600", "textTransform": "uppercase",
                                      "marginBottom": "6px"}),
            html.Div(signal, style={"color": T.TEXT_PRIMARY, "fontSize": "13px"}),
        ], pad="sm"),
        html.Div([
            html.Span("Score  ", style={"color": T.TEXT_MUTED, "fontSize": "12px"}),
            html.Span(str(score_val), style={"color": score_color,
                                              "fontSize": "1.4rem", "fontWeight": "700"}),
            html.Span(" / 100", style={"color": T.TEXT_MUTED, "fontSize": "12px"}),
        ]),
    ])


@callback(
    Output("str-sig-modal-body", "children"),
    Input("str-sig-row-store",   "data"),
    prevent_initial_call=True,
)
def _build_signal_body(row):
    if not row:
        return no_update
    slug = row.get("_slug", "")
    try:
        body = get_ui(slug).signal_body(row) if slug else None
    except Exception as exc:
        logger.exception(f"signal_body failed for {slug}")
        return html.Div(f"Error building signal view: {exc}",
                        style={"color": T.DANGER, "fontSize": "13px"})
    if body is None:
        body = _generic_signal_body(row)
    return body


# ── Paper trade ───────────────────────────────────────────────────────────────

def _credit_too_low(row: dict) -> float | None:
    """Net credit per share if it is below the floor, else None."""
    chain = row.get("_chain") or {}
    raw = (chain.get("net_credit") or row.get("net_credit") or
           row.get("~Credit") or row.get("Credit"))
    if raw is None:
        return None
    try:
        cred = float(str(raw).lstrip("$+") or 0)
    except Exception:
        return None
    return cred if cred < _MIN_CREDIT_PER_SHARE else None


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
    n       = int(contracts or 1)
    ui      = get_ui(slug)

    def _msg(text, color):
        return html.Span(text, style={"color": color, "fontSize": "12px"})

    # Strategy-owned path
    try:
        custom = ui.paper_trade(row, n, label)
    except Exception as e:
        return _msg(f"❌ {e}", T.DANGER)
    if custom is not None:
        return _msg(custom.message, T.SUCCESS if custom.ok else T.DANGER)

    # Equity strategies → buy `n` shares at the current price.
    if ui.trade_kind == "equity":
        try:
            from engine.positions import insert_equity_paper_trade
            from db.client import get_engine
            price = _num(row.get("Price"))
            if price <= 0:
                return _msg("⚠ No current price — cannot record trade.", T.WARNING)
            details = {k: v for k, v in row.items()
                       if not str(k).startswith("_") and k not in ("all_pass", "n_pass")}
            err = insert_equity_paper_trade(
                engine=get_engine(), account_id=1, ticker=ticker,
                strategy_name=slug, shares=n, price=price, details=details)
            if err:
                return _msg(f"❌ {err}", T.DANGER)
            return _msg(f"✓ Bought {n} {ticker} @ ${price:,.2f} ({label}).", T.SUCCESS)
        except Exception as e:
            return _msg(f"❌ {e}", T.DANGER)

    # Credit strategies: block when the net credit is too low / negative
    if ui.is_credit:
        low = _credit_too_low(row)
        if low is not None:
            return _msg(f"⚠ Net credit ${low:.2f}/share is too low — trade blocked "
                        f"(min ${_MIN_CREDIT_PER_SHARE:.2f}/share).", T.WARNING)

    try:
        from engine.positions import insert_generic_paper_trade
        from db.client import get_engine
        details = {k: v for k, v in row.items()
                   if k not in ("_slug", "all_pass", "n_pass", "_chain")
                   and v not in (None, "—", "")}
        try:
            details.update(ui.trade_details(row) or {})
        except Exception as e:
            return _msg(f"⚠ trade details failed: {e}", T.DANGER)
        err = insert_generic_paper_trade(
            engine=get_engine(), account_id=1, ticker=ticker,
            strategy_name=label, contracts=n, details=details)
        if err:
            return _msg(f"Error: {err}", T.DANGER)
        return _msg(f"✓ {ticker} {label} saved ({n} contract(s))", T.SUCCESS)
    except Exception as e:
        return _msg(f"Error: {e}", T.DANGER)


@callback(
    Output("str-sig-modal", "is_open", allow_duplicate=True),
    Input("str-sig-modal-dismiss", "n_clicks"),
    prevent_initial_call=True,
)
def _dismiss_sig_modal(n):
    return False
