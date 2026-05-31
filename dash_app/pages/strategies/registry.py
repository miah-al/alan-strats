"""
dash_app/pages/strategies/registry.py

User-visible strategy lists (rules + AI), universe definitions, slug-set
constants, and the guide-articles path. No callbacks, no Dash components,
no formatters — pure data only.
"""
from __future__ import annotations

from pathlib import Path

# ── Strategy registry ─────────────────────────────────────────────────────────

_STRATEGIES_RULES = [
    {"label": "Iron Condor (Rules)",   "value": "iron_condor_rules"},
    {"label": "VIX Spike Fade",        "value": "vix_spike_fade"},
    {"label": "IVR Credit Spread",     "value": "ivr_credit_spread"},
    {"label": "Vol Arbitrage",         "value": "vol_arbitrage"},
    {"label": "GEX Positioning",       "value": "gex_positioning"},
    {"label": "Dealer Gamma Regime",   "value": "dealer_gamma_regime"},
    {"label": "Broken Wing Butterfly", "value": "broken_wing_butterfly"},
    {"label": "Calendar Spread",       "value": "calendar_spread"},
    {"label": "Earnings Straddle",     "value": "earnings_straddle"},
    {"label": "Wheel Strategy",        "value": "wheel_strategy"},
    {"label": "Bull Put Spread",       "value": "bull_put_spread"},
    {"label": "OpEx Max Pain Pin",     "value": "expiry_max_pain"},
    {"label": "Tail Risk Put Spread",  "value": "tail_risk_put_spread"},
    {"label": "Tail Risk Long Put",    "value": "tail_risk_long_put"},
    {"label": "FOMC Event Straddle",   "value": "fomc_event_straddle"},
    {"label": "Calendar Spread (VIX)", "value": "calendar_spread_vix"},
]

_STRATEGIES_AI = [
    {"label": "Iron Condor (AI)",            "value": "iron_condor_ai"},
    {"label": "VIX Term Structure AI",        "value": "vix_term_structure"},
    {"label": "Earnings Vol Crush AI",        "value": "earnings_vol_crush"},
    {"label": "Momentum Regime Spread AI",    "value": "momentum_regime_spread"},
    {"label": "Covered Call Optimizer AI",    "value": "covered_call_ai"},
    {"label": "Vol Regime Calendar Spread AI","value": "vol_calendar_spread"},
    {"label": "RS Credit Spread AI",          "value": "rs_credit_spread"},
    {"label": "Put Steal — Interest Arb AI",  "value": "put_steal"},
    {"label": "HMM Regime Classifier",        "value": "hmm_regime"},
    {"label": "Short Squeeze Detector",       "value": "short_squeeze_detector"},
    {"label": "News Sentiment NLP",           "value": "news_sentiment_nlp"},
    {"label": "Earnings Pin Risk",            "value": "earnings_pin_risk"},
    {"label": "Yield Curve Regime",           "value": "yield_curve_regime"},
]

# flat list kept for label lookup and scan-callback registration
_STRATEGIES = _STRATEGIES_RULES + _STRATEGIES_AI

_SLUG_TO_LABEL: dict[str, str] = {s["value"]: s["label"] for s in _STRATEGIES}


# ── Review status per strategy ────────────────────────────────────────────────
# Drives the colour-coded selector chips in the UI.
#   ready     : audited + signed off; safe to deploy / paper-trade
#   reviewed  : audited, has known issues but credible — paper only
#   reviewing : not yet audited / under review
#   avoid     : known broken — do not deploy until rewritten
# Defaults to "reviewing" for any slug not in this map.
_STRATEGY_STATUS: dict[str, str] = {
    # Ready
    "hmm_regime":            "ready",
    "iron_condor_rules":     "ready",
    # Reviewed (B-grade)
    "vix_spike_fade":        "reviewed",
    "fomc_event_straddle":   "reviewed",
    "tail_risk_put_spread":  "reviewed",
    "dealer_gamma_regime":   "reviewed",
    "ivr_credit_spread":     "reviewed",
    "bull_put_spread":       "reviewed",
    "put_steal":             "reviewed",
    "vix_term_structure":    "reviewed",
    "earnings_pin_risk":     "reviewed",
    "tail_risk_long_put":    "reviewed",
    # Avoid (D-grade or structurally broken)
    "covered_call_ai":       "avoid",
    "vol_arbitrage":         "avoid",
    "broken_wing_butterfly": "avoid",
    "calendar_spread":       "avoid",
    # everything else defaults to "reviewing"
}

# Palette mapped to status; consumed by the strategy selector.
#   ready     : green
#   reviewed  : yellow
#   reviewing : light orange (peach)
#   avoid     : red
_STATUS_COLORS: dict[str, dict] = {
    "ready":     {"label": "Ready",     "border": "#10b981", "dot": "#10b981", "tint": "rgba(16,185,129,0.10)"},
    "reviewed":  {"label": "Reviewed",  "border": "#facc15", "dot": "#facc15", "tint": "rgba(250,204,21,0.10)"},
    "reviewing": {"label": "Reviewing", "border": "#fdba74", "dot": "#fdba74", "tint": "rgba(253,186,116,0.10)"},
    "avoid":     {"label": "Avoid",     "border": "#ef4444", "dot": "#ef4444", "tint": "rgba(239,68,68,0.10)"},
}


def get_strategy_status(slug: str) -> str:
    """Return the review status for a slug. Defaults to 'reviewing'."""
    return _STRATEGY_STATUS.get(slug, "reviewing")


def get_status_color(slug: str, key: str = "border") -> str:
    """Return the colour value for a slug's status. `key` is one of border / dot / tint."""
    return _STATUS_COLORS[get_strategy_status(slug)][key]

# ── Universe options ──────────────────────────────────────────────────────────

_UNIVERSE_TICKERS: dict[str, list[str]] = {
    "ETF Core":  ["SPY", "QQQ", "IWM", "GLD", "TLT", "EEM", "XLF", "XLE", "XLV", "XLK"],
    "Mega Cap":  ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "BRK-B", "JPM", "JNJ"],
    "High IV":   ["TSLA", "NVDA", "AMD", "META", "NFLX", "COIN", "MSTR", "PLTR", "SMCI", "ARM"],
}

# Strategies that always operate on SPY only — lock the screener ticker selector
_SPY_ONLY_SLUGS = {"vix_term_structure", "momentum_regime_spread", "tail_risk_put_spread"}

# RS Credit Spread always scans the 11 SPDR sector ETFs — lock the ticker selector
_SECTOR_ETFS_LIST = ["XLK", "XLE", "XLF", "XLV", "XLI", "XLY", "XLP", "XLU", "XLRE", "XLB", "XLC"]
_SECTOR_ONLY_SLUGS = {"rs_credit_spread"}

_UNIVERSE_OPTIONS = [{"label": k, "value": k} for k in _UNIVERSE_TICKERS] + [
    {"label": "Custom", "value": "Custom"},
]

# ── Guide articles directory ──────────────────────────────────────────────────
# This file lives at dash_app/pages/strategies/registry.py; guides at dash_app/guide_articles/
_GUIDE_DIR = Path(__file__).parent.parent.parent / "guide_articles"
