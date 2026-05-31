"""
app/pages/strategies/columns.py

AG-Grid column definitions per strategy + the slug → columns map. No state,
no callbacks — pure dict literals built once at import time.
"""
from __future__ import annotations


def _col(field: str, width: int | None = None, flex: int | None = None,
         min_width: int = 70, numeric: bool = False, pinned: str | None = None,
         sort: str | None = None) -> dict:
    d: dict = {"field": field, "resizable": True, "sortable": True, "filter": True,
                "minWidth": min_width}
    if width:
        d["width"] = width
    if flex:
        d["flex"] = flex
    if numeric:
        d["type"] = "numericColumn"
    if pinned:
        d["pinned"] = pinned
    if sort:
        d["sort"] = sort
    return d


# _VIEW_BTN removed 2026-05-28: the entire row is now clickable via the JS
# bridge (see assets/mrt_row_click.js). A dedicated View column is redundant.

_IC_COLS = [
    _col("Ticker",  width=150, pinned="left"),
    _col("Price",   width=150, numeric=True),
    _col("ATM IV",  width=150, numeric=True),
    _col("IVR",     width=150, numeric=True),
    _col("HV20",    width=150, numeric=True),
    _col("VRP",     width=150, numeric=True),
    _col("IV/HV",   width=150, numeric=True),
    _col("VIX",     width=150, numeric=True),
    _col("ADX",     width=150, numeric=True),
    _col("ATR%",    width=150, numeric=True),
    _col("Score",   width=150, numeric=True, sort="desc"),
    _col("Status",  width=150),
    {"field": "Chart", "flex": 1, "minWidth": 150, "sortable": False, "filter": False,
     "cellStyle": {"textAlign": "center", "cursor": "pointer"},
     "valueGetter": {"function": "'📊 View'"},
     "cellClass": "ic-chart-btn"},
    {"field": "_chain",      "hide": True},
    {"field": "_chain_err",  "hide": True},
    {"field": "_atm_iv_raw", "hide": True},
]

_VSF_COLS = [
    _col("Ticker",      width=150, pinned="left"),
    _col("Price",       width=150, numeric=True),
    _col("VIX",         width=150, numeric=True),
    _col("VIX 20d avg", width=150, numeric=True),
    _col("VIX / 20d",   width=150, numeric=True),
    _col("ATM IV",      width=150, numeric=True),
    _col("HV20",        width=150, numeric=True),
    _col("IVR",         width=150, numeric=True),
    _col("ATR%",        width=150, numeric=True),
    _col("MA200",       width=150, numeric=True),
    _col("Score",       width=150, numeric=True, sort="desc"),
    _col("Status",      width=150),
]

_IVR_COLS = [
    _col("Ticker",      width=100, pinned="left"),
    _col("Price",       width=90,  numeric=True),
    _col("ATM IV",      width=90,  numeric=True),
    _col("IVR",         width=90,  numeric=True),
    _col("VRP",         width=85,  numeric=True),
    _col("HV20",        width=85,  numeric=True),
    _col("IV/HV",       width=85,  numeric=True),
    _col("VIX",         width=85,  numeric=True),
    _col("Trend",       width=100),
    _col("Spread Type", width=140),
    _col("Score",       width=85,  numeric=True, sort="desc"),
    _col("Status",      width=110),
]

_VA_COLS = [
    _col("Ticker",  width=150, pinned="left"),
    _col("Price",   width=150, numeric=True),
    _col("ATM IV",  width=150, numeric=True),
    _col("HV20",    width=150, numeric=True),
    _col("IV/HV",   width=150, numeric=True),
    _col("VRP",     width=150, numeric=True),
    _col("IVR",     width=150, numeric=True),
    _col("VIX",     width=150, numeric=True),
    _col("ATR%",    width=150, numeric=True),
    _col("Score",   width=150, numeric=True, sort="desc"),
    _col("Status",  width=150),
]

_GEX_COLS = [
    _col("Ticker",       width=120, pinned="left"),
    _col("Price",        width=110, numeric=True),
    _col("VIX",          width=100, numeric=True),
    _col("Regime",       width=130),
    _col("SPY Weight",   width=130, numeric=True),
    _col("Signal",       width=100),
    _col("ATR%",         width=100, numeric=True),
    _col("5d Return",    width=115, numeric=True),
    _col("Regime Label", width=220),
    _col("Score",        width=110, numeric=True, sort="desc"),
    _col("Status",       width=120),
]

_BWB_COLS = [
    _col("Ticker",      width=150, pinned="left"),
    _col("Price",       width=120, numeric=True),
    _col("ATM IV",      width=120, numeric=True),
    _col("IVR",         width=120, numeric=True),
    _col("VIX",         width=120, numeric=True),
    _col("ADX",         width=120, numeric=True),
    _col("Narrow Wing", width=130, numeric=True),
    _col("Wide Wing",   width=120, numeric=True),
    _col("Score",       width=120, numeric=True, sort="desc"),
    _col("Status",      width=130),
]

_CAL_COLS = [
    _col("Ticker",  width=150, pinned="left"),
    _col("Price",   width=120, numeric=True),
    _col("ATM IV",  width=120, numeric=True),
    _col("HV20",    width=120, numeric=True),
    _col("VRP",     width=120, numeric=True),
    _col("IVR",     width=120, numeric=True),
    _col("VIX",     width=120, numeric=True),
    _col("ADX",     width=120, numeric=True),
    _col("Score",   width=120, numeric=True, sort="desc"),
    _col("Status",  width=130),
]

_EARN_COLS = [
    _col("Ticker",           width=150, pinned="left"),
    _col("Price",            width=120, numeric=True),
    _col("ATM IV",           width=120, numeric=True),
    _col("IVR",              width=120, numeric=True),
    _col("Days to Earnings", width=150, numeric=True),
    _col("Impl. Move",       width=130, numeric=True),
    _col("Straddle Credit",  width=150, numeric=True),
    _col("VIX",              width=120, numeric=True),
    _col("Score",            width=120, numeric=True, sort="desc"),
    _col("Status",           width=130),
]

_WHEEL_COLS = [
    _col("Ticker",    width=150, pinned="left"),
    _col("Price",     width=120, numeric=True),
    _col("MA50",      width=120, numeric=True),
    _col("ATM IV",    width=120, numeric=True),
    _col("IVR",       width=120, numeric=True),
    _col("VIX",       width=120, numeric=True),
    _col("ADX",       width=120, numeric=True),
    _col("Put Strike",width=130, numeric=True),
    _col("~Premium",  width=120, numeric=True),
    _col("Score",     width=120, numeric=True, sort="desc"),
    _col("Status",    width=130),
]

_BPS_COLS = [
    _col("Ticker",       width=150, pinned="left"),
    _col("Price",        width=120, numeric=True),
    _col("MA50",         width=120, numeric=True),
    _col("ATM IV",       width=120, numeric=True),
    _col("IVR",          width=120, numeric=True),
    _col("Short Strike", width=130, numeric=True),
    _col("Long Strike",  width=130, numeric=True),
    _col("Width",        width=100, numeric=True),
    _col("~Credit",      width=110, numeric=True),
    _col("Credit/Width", width=130, numeric=True),
    _col("Score",        width=120, numeric=True, sort="desc"),
    _col("Status",       width=130),
]

_VTS_COLS = [
    _col("Ticker",   width=120, pinned="left"),
    _col("Price",    width=110, numeric=True),
    _col("VIX",      width=100, numeric=True),
    _col("Regime",   width=130),
    _col("VRP",      width=110, numeric=True),
    _col("RV20",     width=110, numeric=True),
    _col("VoV",      width=100, numeric=True),
    _col("5d Chg",   width=110, numeric=True),
    _col("Score",    width=110, numeric=True, sort="desc"),
    _col("Status",   width=120),
]

_EVC_COLS = [
    _col("Ticker",    width=120, pinned="left"),
    _col("Price",     width=110, numeric=True),
    _col("Gap%",      width=110, numeric=True),
    _col("Gap Type",  width=170),
    _col("IVR",       width=100, numeric=True),
    _col("VIX",       width=100, numeric=True),
    _col("RV20",      width=110, numeric=True),
    _col("Score",     width=110, numeric=True, sort="desc"),
    _col("Status",    width=130),
]

_MRS_COLS = [
    _col("Ticker",   width=120, pinned="left"),
    _col("Price",    width=110, numeric=True),
    _col("Regime",   width=110),
    _col("5d Ret",   width=110, numeric=True),
    _col("20d Ret",  width=115, numeric=True),
    _col("Accel",    width=110, numeric=True),
    _col("VIX",      width=100, numeric=True),
    _col("VIX/MA",   width=110, numeric=True),
    _col("Score",    width=110, numeric=True, sort="desc"),
    _col("Status",   width=140),
]

_CCA_COLS = [
    _col("Ticker",     width=120, pinned="left"),
    _col("Price",      width=110, numeric=True),
    _col("IVR",        width=100, numeric=True),
    _col("VRP",        width=100, numeric=True),
    _col("Delta Mode", width=170),
    _col("20d Ret",    width=115, numeric=True),
    _col("VIX",        width=100, numeric=True),
    _col("Score",      width=110, numeric=True, sort="desc"),
    _col("Status",     width=140),
]

_RCS_COLS = [
    _col("Ticker",   width=120, pinned="left"),
    _col("Price",    width=110, numeric=True),
    _col("10d Ret",  width=115, numeric=True),
    _col("Role",     width=170),
    _col("IVR",      width=100, numeric=True),
    _col("VIX",      width=100, numeric=True),
    _col("ADX",      width=100, numeric=True),
    _col("Score",    width=110, numeric=True, sort="desc"),
    _col("Status",   width=130),
]

_PS_COLS = [
    _col("Ticker",    width=120, pinned="left"),
    _col("Price",     width=100, numeric=True),
    _col("NII",       width=100, numeric=True),
    _col("Strike X",  width=110, numeric=True),
    _col("Short Put", width=110, numeric=True),
    _col("Long Put",  width=110, numeric=True),
    _col("~Credit",   width=100, numeric=True),
    _col("Max Loss",  width=110, numeric=True),
    _col("Expiry",    width=110),
    _col("IV Src",    width=100),
    _col("ATM IV",    width=100, numeric=True),
    _col("IVR",       width=90,  numeric=True),
    _col("VIX",       width=90,  numeric=True),
    _col("Score",     width=100, numeric=True, sort="desc"),
    _col("Status",    width=120),
]

_HMM_COLS = [
    _col("Ticker",   width=120, pinned="left"),
    _col("Price",    width=110, numeric=True),
    _col("VIX",      width=100, numeric=True),
    _col("IVR",      width=100, numeric=True),
    _col("Regime",   width=160),
    _col("State",    width=90,  numeric=True),
    _col("P(state)", width=110, numeric=True),
    _col("Trade",    width=200),
    _col("Signal",   width=100),
    _col("5d Ret",   width=110, numeric=True),
    _col("20d Ret",  width=115, numeric=True),
    _col("Mode",     width=120),
    _col("Score",    width=110, numeric=True, sort="desc"),
    _col("Status",   width=240),
]

_EMP_COLS = [
    _col("Ticker",      width=120, pinned="left"),
    _col("Price",       width=110, numeric=True),
    _col("VIX",         width=100, numeric=True),
    _col("ATM IV",      width=100, numeric=True),
    _col("IVR",         width=100, numeric=True),
    _col("OpEx Week",   width=110),
    _col("DTE to OpEx", width=130, numeric=True),
    _col("Structure",   width=180),
    _col("Score",       width=110, numeric=True, sort="desc"),
    _col("Status",      width=280),
]

_SSD_COLS = [
    _col("Ticker",     width=120, pinned="left"),
    _col("Price",      width=110, numeric=True),
    _col("VIX",        width=100, numeric=True),
    _col("IVR",        width=100, numeric=True),
    _col("Vol Ratio",  width=110, numeric=True),
    _col("5d Ret",     width=110, numeric=True),
    _col("20d Ret",    width=115, numeric=True),
    _col("P(squeeze)", width=120, numeric=True),
    _col("Structure",  width=160),
    _col("Mode",       width=160),
    _col("Score",      width=110, numeric=True, sort="desc"),
    _col("Status",     width=260),
]

_TRP_COLS = [
    _col("Ticker",       width=120, pinned="left"),
    _col("Price",        width=110, numeric=True),
    _col("VIX",          width=100, numeric=True),
    _col("ATM IV",       width=100, numeric=True),
    _col("IVR",          width=100, numeric=True),
    _col("Long Strike",  width=130, numeric=True),
    _col("Short Strike", width=130, numeric=True),
    _col("Width",        width=100, numeric=True),
    _col("DTE",          width=80,  numeric=True),
    _col("~Debit",       width=110, numeric=True),
    _col("Max Payout",   width=120, numeric=True),
    _col("Structure",    width=180),
    _col("Score",        width=110, numeric=True, sort="desc"),
    _col("Status",       width=260),
]

_NSN_COLS = [
    _col("Ticker",     width=120, pinned="left"),
    _col("Price",      width=110, numeric=True),
    _col("VIX",        width=100, numeric=True),
    _col("IVR",        width=100, numeric=True),
    _col("1d Ret",     width=100, numeric=True),
    _col("5d Ret",     width=110, numeric=True),
    _col("z (proxy)",  width=120, numeric=True),
    _col("z thresh",   width=110, numeric=True),
    _col("Signal",     width=130),
    _col("Structure",  width=140),
    _col("Mode",       width=160),
    _col("Score",      width=110, numeric=True, sort="desc"),
    _col("Status",     width=260),
]

_COLS_BY_SLUG: dict[str, list[dict]] = {
    "iron_condor_rules":     _IC_COLS,
    "iron_condor_ai":        _IC_COLS,
    "vix_spike_fade":        _VSF_COLS,
    "ivr_credit_spread":     _IVR_COLS,
    "vol_arbitrage":         _VA_COLS,
    "gex_positioning":       _GEX_COLS,
    "broken_wing_butterfly": _BWB_COLS,
    "calendar_spread":       _CAL_COLS,
    "earnings_straddle":     _EARN_COLS,
    "wheel_strategy":        _WHEEL_COLS,
    "bull_put_spread":       _BPS_COLS,
    # New AI strategies
    "vix_term_structure":    _VTS_COLS,
    "earnings_vol_crush":    _EVC_COLS,
    "momentum_regime_spread": _MRS_COLS,
    "covered_call_ai":       _CCA_COLS,
    "rs_credit_spread":      _RCS_COLS,
    "put_steal":             _PS_COLS,
    # New strategies (2026-05-01)
    "hmm_regime":             _HMM_COLS,
    "expiry_max_pain":        _EMP_COLS,
    "short_squeeze_detector": _SSD_COLS,
    "tail_risk_put_spread":   _TRP_COLS,
    "news_sentiment_nlp":     _NSN_COLS,
    # VIX / vol calendar spreads — reuse the generic calendar column set.
    # The screener fills a subset; absent fields render blank, never error.
    "calendar_spread_vix":    _CAL_COLS,
    "vol_calendar_spread":    _CAL_COLS,
}
