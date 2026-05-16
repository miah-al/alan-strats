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
