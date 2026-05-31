"""
app/ui/components.py — shared, polished UI primitives.

The mapping pass found the SAME helpers re-implemented independently in every page
(_section, _pill, _metric_card, _card_header, _status_badge, _hint, _DARK ...).
That duplication is the root cause of the inconsistent look. This module is the
single, polished implementation of each. Pages should import these instead of
rolling their own:

    from app.ui import components as C
    C.page_header("Strategies", "Backtest, screen, and read the playbooks")
    C.card([...], pad="lg")
    C.kpi_row([("Account", "$104,210", "success"), ...])

Everything here is presentation-only (no callbacks, no data access), so it is
safe to import anywhere and cannot break app behaviour.
"""
from __future__ import annotations

from typing import Iterable, Optional

from dash import html, dcc
import dash_bootstrap_components as dbc

from app.ui import tokens as D


# ── Page header ──────────────────────────────────────────────────────────────
def page_header(title: str, subtitle: str | None = None,
                actions: Optional[list] = None) -> html.Div:
    """Standard page title block. `actions` renders right-aligned (buttons etc.)."""
    left = [html.H1(title, style={
        "margin": "0", "fontSize": D.TEXT_2XL, "fontWeight": D.WEIGHT_HEAVY,
        "letterSpacing": "-0.02em", "color": D.COLOR.text,
    })]
    if subtitle:
        left.append(html.Div(subtitle, style={
            "marginTop": D.SPACE_1, "fontSize": D.TEXT_MD, "color": D.COLOR.text_sec,
        }))
    row = [html.Div(left)]
    if actions:
        row.append(html.Div(actions, style={"display": "flex", "gap": D.SPACE_2,
                                            "alignItems": "center"}))
    return html.Div(row, style={
        "display": "flex", "justifyContent": "space-between",
        "alignItems": "flex-start", "gap": D.SPACE_4,
        "marginBottom": D.SPACE_6,
        "paddingBottom": D.SPACE_4,
        "borderBottom": f"1px solid {D.COLOR.border}",
    })


# ── Card + section ───────────────────────────────────────────────────────────
_PAD = {"sm": D.SPACE_3, "md": D.SPACE_4, "lg": D.SPACE_6}


def card(children, pad: str = "md", style: dict | None = None) -> html.Div:
    """Standard surface card with hover-lift (lift comes from .card-less div via
    z_polish.css `.ui-card`)."""
    st = {**D.CARD, "padding": _PAD.get(pad, D.SPACE_4), "marginBottom": D.SPACE_4}
    if style:
        st.update(style)
    return html.Div(children, className="ui-card", style=st)


def section(title: str, children, subtitle: str | None = None,
            right=None) -> html.Div:
    """Card with an uppercase section header (and optional right-aligned control)."""
    head_left = [html.Div(title, style={
        "color": D.COLOR.text_sec, "fontSize": D.TEXT_XS, "fontWeight": D.WEIGHT_BOLD,
        "textTransform": "uppercase", "letterSpacing": "0.07em",
    })]
    if subtitle:
        head_left.append(html.Div(subtitle, style={
            "color": D.COLOR.text_muted, "fontSize": D.TEXT_SM, "marginTop": "2px",
            "textTransform": "none", "letterSpacing": "normal", "fontWeight": "500",
        }))
    header = html.Div(
        [html.Div(head_left)] + ([html.Div(right)] if right is not None else []),
        style={"display": "flex", "justifyContent": "space-between",
               "alignItems": "center",
               "borderBottom": f"1px solid {D.COLOR.border}",
               "paddingBottom": D.SPACE_2, "marginBottom": D.SPACE_3},
    )
    return html.Div([header, children], className="ui-card",
                    style={**D.CARD, "marginBottom": D.SPACE_4})


# ── Metrics / KPIs ───────────────────────────────────────────────────────────
_TONE = {
    "default": D.COLOR.text, "success": D.COLOR.success, "danger": D.COLOR.danger,
    "warning": D.COLOR.warning, "accent": D.COLOR.accent, "muted": D.COLOR.text_muted,
}


def metric_card(label: str, value: str, tone: str = "default",
                sub: str | None = None) -> html.Div:
    """A single KPI tile: small uppercase label over a large value."""
    body = [
        html.Div(label, style={
            "color": D.COLOR.text_muted, "fontSize": D.TEXT_XS,
            "fontWeight": D.WEIGHT_MED, "textTransform": "uppercase",
            "letterSpacing": "0.05em", "marginBottom": D.SPACE_1,
        }),
        html.Div(value, style={
            "color": _TONE.get(tone, D.COLOR.text), "fontSize": D.TEXT_XL,
            "fontWeight": D.WEIGHT_BOLD, "lineHeight": "1.1",
        }),
    ]
    if sub:
        body.append(html.Div(sub, style={
            "color": D.COLOR.text_muted, "fontSize": D.TEXT_SM, "marginTop": "2px"}))
    return html.Div(body, className="ui-card", style={
        **D.CARD, "flex": "1", "minWidth": "120px", "padding": f"{D.SPACE_3} {D.SPACE_4}",
    })


def kpi_row(items: Iterable[tuple]) -> html.Div:
    """Row of metric cards. Each item: (label, value) or (label, value, tone) or
    (label, value, tone, sub)."""
    cards = []
    for it in items:
        label, value = it[0], it[1]
        tone = it[2] if len(it) > 2 else "default"
        sub  = it[3] if len(it) > 3 else None
        cards.append(metric_card(label, value, tone, sub))
    return html.Div(cards, style={"display": "flex", "gap": D.SPACE_3,
                                  "flexWrap": "wrap", "marginBottom": D.SPACE_4})


# ── Pills / badges ───────────────────────────────────────────────────────────
def badge(text: str, tone: str = "accent", soft: bool = True) -> html.Span:
    """Small rounded status badge. soft=True uses a tinted bg; False is solid."""
    color = _TONE.get(tone, D.COLOR.accent)
    if soft:
        style = {"backgroundColor": _soft(color), "color": color,
                 "border": f"1px solid {_soft(color, 0.4)}"}
    else:
        style = {"backgroundColor": color, "color": "#fff"}
    return html.Span(text, style={
        **style, "padding": "2px 10px", "borderRadius": D.RADIUS_PILL,
        "fontSize": D.TEXT_XS, "fontWeight": D.WEIGHT_MED, "whiteSpace": "nowrap",
        "display": "inline-block",
    })


def hint(text: str) -> html.P:
    return html.P(text, style={"color": D.COLOR.text_muted, "fontSize": D.TEXT_SM,
                               "fontStyle": "italic", "margin": "4px 0"})


def _soft(hex_or_rgba: str, alpha: float = 0.12) -> str:
    """Make a soft translucent version of a colour for badge backgrounds."""
    c = hex_or_rgba.lstrip("#")
    if len(c) == 6:
        r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
        return f"rgba({r},{g},{b},{alpha})"
    return hex_or_rgba


# ── Empty state ──────────────────────────────────────────────────────────────
def empty_state(message: str, icon: str = "○") -> html.Div:
    return html.Div([
        html.Div(icon, style={"fontSize": "28px", "color": D.COLOR.text_muted,
                              "marginBottom": D.SPACE_2}),
        html.Div(message, style={"color": D.COLOR.text_sec, "fontSize": D.TEXT_MD}),
    ], style={"textAlign": "center", "padding": f"{D.SPACE_10} {D.SPACE_4}"})
