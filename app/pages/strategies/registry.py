"""
app/pages/strategies/registry.py

Page-side view of the strategy registry: selector lists, review-status
palette, universe definitions. Everything strategy-specific comes from the
installed plugins through ``alan_trader.strategy_api.registry``; this module
names no strategy.
"""
from __future__ import annotations

from alan_trader.strategy_api import registry as R

# ── Selector lists ────────────────────────────────────────────────────────────

def _split() -> tuple[list[dict], list[dict]]:
    rules, ai = [], []
    for e in R.ui_entries():
        entry = {"label": e["label"], "value": e["value"]}
        (ai if e.get("type") == "ai" else rules).append(entry)
    return rules, ai


_STRATEGIES_RULES, _STRATEGIES_AI = _split()

# flat list kept for label lookup and scan-callback registration
_STRATEGIES = _STRATEGIES_RULES + _STRATEGIES_AI

_SLUG_TO_LABEL: dict[str, str] = {s["value"]: s["label"] for s in _STRATEGIES}


def slugs() -> list[str]:
    return [s["value"] for s in _STRATEGIES]


# ── Review status ─────────────────────────────────────────────────────────────
# Drives the colour-coded selector chips in the UI.
#   ready     : audited + signed off; safe to deploy / paper-trade
#   reviewed  : audited, has known issues but credible — paper only
#   reviewing : not yet audited / under review
#   avoid     : known broken — do not deploy until rewritten
_STATUS_COLORS: dict[str, dict] = {
    "ready":     {"label": "Ready",     "border": "#10b981", "dot": "#10b981", "tint": "rgba(16,185,129,0.10)"},
    "reviewed":  {"label": "Reviewed",  "border": "#facc15", "dot": "#facc15", "tint": "rgba(250,204,21,0.10)"},
    "reviewing": {"label": "Reviewing", "border": "#fdba74", "dot": "#fdba74", "tint": "rgba(253,186,116,0.10)"},
    "avoid":     {"label": "Avoid",     "border": "#ef4444", "dot": "#ef4444", "tint": "rgba(239,68,68,0.10)"},
}


def get_strategy_status(slug: str) -> str:
    """Return the review status for a slug. Defaults to 'reviewing'."""
    status = R.review_status(slug)
    return status if status in _STATUS_COLORS else "reviewing"


def get_status_color(slug: str, key: str = "border") -> str:
    """Return the colour value for a slug's status. `key` is one of border / dot / tint."""
    return _STATUS_COLORS[get_strategy_status(slug)][key]


# ── Credibility score ─────────────────────────────────────────────────────────

def get_strategy_score(slug: str):
    """Return (score:int, grade:str) for a slug, or None if not scored."""
    sc = R.score(slug)
    if not sc:
        return None
    try:
        score, grade = sc
        return int(score), str(grade)
    except (TypeError, ValueError):
        return None


def get_score_color(score: int) -> str:
    """Map a 0-100 credibility score to a band colour (green/yellow/peach/red)."""
    if score >= 80:
        return _STATUS_COLORS["ready"]["dot"]       # green  — deploy candidate
    if score >= 70:
        return _STATUS_COLORS["reviewed"]["dot"]    # yellow — paper-trade
    if score >= 62:
        return _STATUS_COLORS["reviewing"]["dot"]   # peach  — needs work
    return _STATUS_COLORS["avoid"]["dot"]           # red    — thin/weak edge


# ── Universe options ──────────────────────────────────────────────────────────

_UNIVERSE_TICKERS: dict[str, list[str]] = {
    "ETF Core":  ["SPY", "QQQ", "IWM", "GLD", "TLT", "EEM", "XLF", "XLE", "XLV", "XLK"],
    "Mega Cap":  ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "BRK-B", "JPM", "JNJ"],
    "High IV":   ["TSLA", "NVDA", "AMD", "META", "NFLX", "COIN", "MSTR", "PLTR", "SMCI", "ARM"],
}

_UNIVERSE_OPTIONS = [{"label": k, "value": k} for k in _UNIVERSE_TICKERS] + [
    {"label": "Custom", "value": "Custom"},
]
