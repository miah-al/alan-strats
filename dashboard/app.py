"""
alan-strats — Multi-Strategy Dashboard.
Run: streamlit run alan_trader/dashboard/app.py (from d:/Work/ClaudeCodeTest)
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import datetime
import logging
import numpy as np
import pandas as pd
import streamlit as st

logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="alan-strats",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
  /* ── App chrome ────────────────────────────────────────────────────── */
  [data-testid="stAppViewContainer"] { background-color: #0e1117; }
  [data-testid="stSidebar"]          { background-color: #0c1020; }

  /* ── Tabs — clean underline style ──────────────────────────────────── */
  .stTabs [data-baseweb="tab-list"] {
      gap: 0;
      border-bottom: 1px solid #1e2538;
      background: transparent;
      flex-wrap: wrap;
  }
  .stTabs [data-baseweb="tab"] {
      background: transparent;
      border: none;
      border-bottom: 2px solid transparent;
      border-radius: 0;
      padding: 8px 16px;
      color: #546e7a;
      font-size: 13px;
      font-weight: 500;
      letter-spacing: 0.02em;
      transition: color 0.15s, border-color 0.15s;
      margin-bottom: -1px;
  }
  .stTabs [data-baseweb="tab"]:hover {
      color: #b0c8e0 !important;
      background: rgba(92,107,192,0.06) !important;
  }
  .stTabs [aria-selected="true"] {
      color: #e0e0e0 !important;
      border-bottom: 2px solid #5c6bc0 !important;
      background: transparent !important;
      font-weight: 600 !important;
  }
  /* inner strategy sub-tabs — slightly different accent */
  .stTabs .stTabs [aria-selected="true"] {
      border-bottom: 2px solid #26a69a !important;
  }

  /* ── Typography ─────────────────────────────────────────────────────── */
  h1, h2, h3 { color: #e0e0e0 !important; }
  p, li       { color: #b0b8c8; }

  /* ── Metrics ────────────────────────────────────────────────────────── */
  [data-testid="stMetricValue"] { color: #e0e0e0 !important; font-size: 1.15rem !important; }
  [data-testid="stMetricLabel"] { color: #546e7a  !important; font-size: 0.78rem !important; }

  /* ── Buttons ────────────────────────────────────────────────────────── */
  .stButton > button {
      background: #1e2538; border: 1px solid #2a3550;
      color: #b0b8c8; border-radius: 7px;
      font-size: 12px; padding: 5px 12px;
      transition: background 0.15s, border-color 0.15s;
  }
  .stButton > button:hover {
      background: #252d45; border-color: #5c6bc0; color: #e0e0e0;
  }

  /* ── Inputs ─────────────────────────────────────────────────────────── */
  div[data-testid="stTextInput"] input,
  div[data-testid="stNumberInput"] input {
      background: #161b27 !important;
      border: 1px solid #2a2f3f !important;
      color: #e0e0e0 !important;
      border-radius: 7px !important;
  }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# REGISTRY
# ══════════════════════════════════════════════════════════════════════════════
from alan_trader.strategies.registry import STRATEGY_METADATA, get_strategy

ACTIVE_SLUGS = [s for s, m in STRATEGY_METADATA.items() if m.get("status") == "active"]


def _meta(slug):   return STRATEGY_METADATA[slug]
def _cap(slug, key, default=False): return _meta(slug).get(key, default)


# ══════════════════════════════════════════════════════════════════════════════
# CONFIG  (.env)
# ══════════════════════════════════════════════════════════════════════════════

def _load_env():
    """Load .env from project root into os.environ (simple key=value parser)."""
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    env_path = os.path.abspath(env_path)
    if not os.path.exists(env_path):
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

_load_env()

# ══════════════════════════════════════════════════════════════════════════════
# SESSION STATE
# ══════════════════════════════════════════════════════════════════════════════

_SS_DEFAULTS: dict = {
    "selected_strategies": [],
    "train_results":   {},          # {slug: train_result_dict}
    "bt_results":      {},          # {slug: BacktestResult}
    "bt_report":       {},          # last portfolio report (aggregate)
    "bt_rolling_w":    pd.DataFrame(),
    "portfolio_store": None,
}
for _k, _v in _SS_DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

if "polygon_api_key" not in st.session_state:
    st.session_state["polygon_api_key"] = os.environ.get("POLYGON_API_KEY", "")


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR — strategy picker + global settings
# ══════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    _logo_path = os.path.join(os.path.dirname(__file__), "static", "logo.svg")
    if os.path.exists(_logo_path):
        import base64 as _b64
        _logo_b64 = _b64.b64encode(open(_logo_path, "rb").read()).decode()
        st.markdown(
            f'<img src="data:image/svg+xml;base64,{_logo_b64}" width="260" style="margin-bottom:4px"/>',
            unsafe_allow_html=True,
        )
    else:
        st.title("Project Dream")
    st.markdown("---")

    st.subheader("Strategies")

    # Group strategies by type for a cleaner selector
    _groups: dict[str, list[str]] = {}
    for _s in ACTIVE_SLUGS:
        _group = _meta(_s).get("type", "other").replace("_", " ").title()
        _groups.setdefault(_group, []).append(_s)

    _current = set(st.session_state.get("selected_strategies", []))
    _new_selected: list[str] = []
    for _group_name, _slugs in _groups.items():
        st.caption(_group_name)
        for _s in _slugs:
            _checked = st.checkbox(
                f"{_meta(_s).get('icon','📌')} {_meta(_s)['display_name']}",
                value=_s in _current,
                key=f"strat_cb_{_s}",
            )
            if _checked:
                _new_selected.append(_s)
    selected = _new_selected
    st.session_state["selected_strategies"] = selected

    st.markdown("---")
    st.caption("Training & backtest data — local SQL Server")
    st.text_input("Polygon API key", type="password", placeholder="sk_...", key="polygon_api_key")

    st.markdown("---")
    if st.button("🔄 Clear all results", width="stretch"):
        st.cache_data.clear()
        for _k in list(_SS_DEFAULTS.keys()):
            if _k in st.session_state:
                del st.session_state[_k]
        st.rerun()

    st.markdown("---")
    # Quick-summary of selected strategies
    for s in selected:
        m = _meta(s)
        badges = []
        if m.get("uses_ml"):         badges.append("ML")
        if m.get("requires_training"): badges.append("Train")
        badge_str = " · ".join(badges) if badges else "Rule-Based"
        st.caption(f"{m.get('icon','📌')} **{m['display_name']}** — {badge_str}")


# ══════════════════════════════════════════════════════════════════════════════
# HELPER: ticker selector row
# ══════════════════════════════════════════════════════════════════════════════

def _ticker_row(key_prefix: str) -> str:
    from alan_trader.data.simulator import TICKER_PROFILES, DEFAULT_PROFILE
    c1, c2 = st.columns([2, 7])
    ticker = c1.text_input("Ticker", value="HOOD", key=f"{key_prefix}_ticker").upper().strip() or "HOOD"
    prof = TICKER_PROFILES.get(ticker, DEFAULT_PROFILE)
    c2.caption(
        f"Est. vol: {prof['annual_vol']*100:.0f}% ann · {prof.get('category', 'equity')}"
    )
    return ticker


# ══════════════════════════════════════════════════════════════════════════════
# BACKEND HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _render_single_param(p: dict, key_prefix: str, container=None):
    """Render one param-spec dict as a Streamlit widget. Returns the widget value."""
    ctx   = container or st
    key   = f"{key_prefix}_{p['key']}"
    label = p["label"]
    ptype = p["type"]
    if ptype == "slider":
        return ctx.slider(label, p["min"], p["max"], p.get("default"), p.get("step", 1),
                          key=key, help=p.get("help"))
    elif ptype == "select_slider":
        return ctx.select_slider(label, options=p["options"], value=p.get("default"), key=key)
    elif ptype == "selectbox":
        kwargs = {"options": p["options"], "key": key}
        if "format_func" in p:
            kwargs["format_func"] = p["format_func"]
        return ctx.selectbox(label, **kwargs)
    elif ptype == "checkbox":
        return ctx.checkbox(label, value=p.get("default", False), key=key)
    elif ptype == "number_input":
        return ctx.number_input(label, value=p.get("default", 0), step=p.get("step", 1), key=key)
    return p.get("default")


def _render_ui_params(params_spec: list, key_prefix: str) -> dict:
    """Render a list of param-spec dicts and return {key: value} dict."""
    result = {}
    full_width = [p for p in params_spec if "col" not in p]
    for p in full_width:
        result[p["key"]] = _render_single_param(p, key_prefix)

    grid_params = [p for p in params_spec if "col" in p]
    rows: dict = {}
    for p in grid_params:
        rows.setdefault(p.get("row", 0), []).append(p)
    for row_idx in sorted(rows):
        row_ps = sorted(rows[row_idx], key=lambda p: p["col"])
        n_cols = max(p["col"] for p in row_ps) + 1
        cols   = st.columns(n_cols)
        for p in row_ps:
            result[p["key"]] = _render_single_param(p, key_prefix, container=cols[p["col"]])
    return result


def _do_train(slug, seq_len, hidden_size, num_layers, dropout, lr, num_epochs,
              ticker="SPY", forward_days=5, otm_pct=0.0, spread_type="bull_call",
              enter_boost=2.0):
    import warnings; warnings.filterwarnings("ignore")
    from alan_trader.data.features import build_feature_matrix, FEATURE_COLS
    from alan_trader.model.trainer import ModelTrainer
    from alan_trader.db.loader import load_training_data

    data = load_training_data(ticker=ticker)

    spy   = data["spy"]
    vix   = data["vix"]
    r2    = data["rate2y"]
    r10   = data["rate10y"]
    macro = data["macro"]
    news  = data["news"]

    spread_pnl_df = None
    spread_diagnostics = {}
    try:
        from alan_trader.db.options_loader import build_spread_history
        from alan_trader.db.client import get_engine as _ge
        spread_pnl_df = build_spread_history(
            _ge(), ticker, spread_type=spread_type,
            target_dte=30, hold_days=forward_days,
            otm_pct=max(otm_pct, 5) / 100, wing_pct=0.05,
            diagnostics=spread_diagnostics,
        )
        if spread_pnl_df.empty:
            spread_pnl_df = None
    except Exception as _e:
        logger.warning(f"Spread history unavailable, falling back to fwd_ret labels: {_e}")
        spread_diagnostics["error"] = str(_e)
        spread_pnl_df = None

    df      = build_feature_matrix(spy, vix, r2, r10, news, forward_days=forward_days,
                                    spread_type=spread_type, macro_df=macro,
                                    spread_pnl_df=spread_pnl_df)

    avail    = [c for c in FEATURE_COLS if c in df.columns]
    features = df[avail].values
    labels   = df["label"].values
    n_train  = int(len(features) * 0.80)

    counts   = np.bincount(labels, minlength=3)
    label_dist = {"avoid": int(counts[0]), "skip": int(counts[1]), "enter": int(counts[2])}

    trainer = ModelTrainer(
        feature_cols=avail,
        hidden_size=hidden_size, num_layers=num_layers, dropout=dropout,
        lr=lr, batch_size=32, num_epochs=num_epochs, patience=15, seq_len=seq_len,
        enter_boost=enter_boost,
    )
    history = trainer.fit(features[:n_train], labels[:n_train])

    # Persist model to disk so live trader and backtest can reload it
    strat = get_strategy(slug)
    trainer.save(strat.get_model_name(ticker))

    test_features = features[n_train:]
    test_labels   = labels[n_train:]
    cm            = trainer.compute_confusion_matrix(test_features, test_labels)
    feat_imp      = trainer.compute_feature_importance(test_features, test_labels)

    # All model ENTER signals (pred_class == 2) — show them all, flag correct vs incorrect
    probas, _ = trainer.predict_batch(test_features)
    test_df   = df.iloc[n_train:].reset_index()
    date_col  = "date" if "date" in test_df.columns else "index"
    seq       = trainer.seq_len
    aligned_df     = test_df.iloc[seq:].reset_index(drop=True)
    aligned_labels = test_labels[seq:]
    pred_classes = probas.argmax(axis=1)

    # All signals where model predicts ENTER (class=2)
    enter_mask  = pred_classes == 2
    n_confirmed = int(((pred_classes == aligned_labels) & enter_mask).sum())  # for applicability banner
    w_df     = aligned_df[enter_mask].copy()
    w_probas = probas[enter_mask]
    w_actual = aligned_labels[enter_mask]

    from alan_trader.backtest.engine import bs_price as _bs

    def _structure(stype, S, iv, r, T, otm):
        """Return a BBG-style structure description string + net cost/credit."""
        p = lambda k, flag: round(_bs(S, k, T, r, iv, flag), 2)
        leg = lambda action, k, flag: f"{action} {int(k)}{flag[0].upper()} ${p(k, flag):.2f}"

        if stype == "bull_call":
            lk = round(S * (1 + otm) / 5) * 5; sk = lk + 5
            cost = round(p(lk, "call") - p(sk, "call"), 2)
            return f"{leg('BUY', lk, 'call')} / {leg('SELL', sk, 'call')} | Debit ${cost:.2f}", cost

        elif stype == "bear_put":
            lk = round(S * (1 - otm) / 5) * 5; sk = lk - 5
            cost = round(p(lk, "put") - p(sk, "put"), 2)
            return f"{leg('BUY', lk, 'put')} / {leg('SELL', sk, 'put')} | Debit ${cost:.2f}", cost

        elif stype == "bull_put":
            sk = round(S * (1 - otm) / 5) * 5; lk = sk - 5
            credit = round(p(sk, "put") - p(lk, "put"), 2)
            return f"{leg('SELL', sk, 'put')} / {leg('BUY', lk, 'put')} | Credit ${credit:.2f}", credit

        elif stype == "bear_call":
            sk = round(S * (1 + otm) / 5) * 5; lk = sk + 5
            credit = round(p(sk, "call") - p(lk, "call"), 2)
            return f"{leg('SELL', sk, 'call')} / {leg('BUY', lk, 'call')} | Credit ${credit:.2f}", credit

        elif stype == "iron_condor":
            ps = round(S * (1 - max(otm, 0.03)) / 5) * 5; pl = ps - 5
            cs = round(S * (1 + max(otm, 0.03)) / 5) * 5; cl = cs + 5
            credit = round((p(ps, "put") - p(pl, "put")) + (p(cs, "call") - p(cl, "call")), 2)
            return (f"{leg('SELL', ps, 'put')} / {leg('BUY', pl, 'put')} / "
                    f"{leg('SELL', cs, 'call')} / {leg('BUY', cl, 'call')} | Credit ${credit:.2f}"), credit

        elif stype == "long_straddle":
            K = round(S / 5) * 5
            cost = round(p(K, "call") + p(K, "put"), 2)
            return (f"{leg('BUY', K, 'call')} / {leg('BUY', K, 'put')} | Debit ${cost:.2f}"), cost

        elif stype == "short_strangle":
            pk = round(S * (1 - max(otm, 0.05)) / 5) * 5
            ck = round(S * (1 + max(otm, 0.05)) / 5) * 5
            credit = round(p(pk, "put") + p(ck, "call"), 2)
            return (f"{leg('SELL', pk, 'put')} / {leg('SELL', ck, 'call')} | Credit ${credit:.2f}"), credit

        elif stype == "call_butterfly":
            mid = round(S / 5) * 5; lk = mid - 5; uk = mid + 5
            cost = round(p(lk, "call") - 2 * p(mid, "call") + p(uk, "call"), 2)
            lp2 = round(p(mid, "call"), 2)
            return (f"{leg('BUY', lk, 'call')} / SELL 2× {int(mid)}C ${lp2:.2f} / "
                    f"{leg('BUY', uk, 'call')} | Debit ${cost:.2f}"), cost

        else:
            lk = round(S / 5) * 5; sk = lk + 5
            cost = round(p(lk, "call") - p(sk, "call"), 2)
            return f"{leg('BUY', lk, 'call')} / {leg('SELL', sk, 'call')} | Debit ${cost:.2f}", cost

    has_real_pnl = "entry_value" in aligned_df.columns

    rows = []
    for i in range(len(w_df)):
        row    = w_df.iloc[i]
        actual = int(w_actual[i])
        outcome = "✅ Won" if actual == 2 else ("⚠️ Marginal" if actual == 1 else "❌ Lost")

        if has_real_pnl:
            entry_v   = float(row.get("entry_value", 0))
            exit_v    = float(row.get("exit_value",  0))
            pnl_v     = float(row.get("pnl",         0))
            max_p     = float(row.get("max_profit",  0))
            max_l     = float(row.get("max_loss",    0))
            pnl_pct   = float(row.get("fwd_ret",     0))
            exit_date = row.get("exit_date", "")
            is_credit = spread_type in ("iron_condor", "bull_put", "bear_call", "short_strangle")
            rows.append({
                "Result":           outcome,
                "Trade Date":       row.get(date_col, ""),
                "Closed Date":      exit_date,
                "Collected" if is_credit else "Paid":
                                    round(abs(entry_v) * 100, 2),
                "Cost to Close" if is_credit else "Sold For":
                                    round(abs(exit_v)  * 100, 2),
                "Profit / Loss":    round(pnl_v   * 100, 2),
                "% of Max Profit":  round(pnl_pct  * 100, 1),
                "Max Profit":       round(max_p    * 100, 2),
                "Max Loss":         round(max_l    * 100, 2),
                "Model Confidence": round(float(w_probas[i].max()) * 100, 1),
            })
        else:
            S   = float(row.get("close", 0))
            iv  = float(row.get("vix", 18.0)) / 100
            r   = float(row.get("rate_10y", 0.045))
            T   = 30 / 252
            structure_str, cost = _structure(spread_type, S, iv, r, T, otm_pct / 100)
            rows.append({
                "entry date":   row.get(date_col, ""),
                "outcome":      outcome,
                "structure":    structure_str,
                "spot":         round(S, 2),
                "cost $/ct":    round(cost * 100, 2),
                "hold days":    forward_days,
                "fwd ret %":    round(float(row.get("fwd_ret", 0)) * 100, 2),
                "confidence":   round(float(w_probas[i].max()) * 100, 1),
            })
    samples = pd.DataFrame(rows)

    return {
        "history":           history,
        "cm":                cm,
        "feat_imp":          feat_imp,
        "trainer":           trainer,
        "feat_df":           df,
        "FEATURE_COLS":      avail,
        "winner_samples":    samples,
        "n_confirmed":       n_confirmed,
        "spread_type":       spread_type,
        "ticker":            ticker,
        "label_dist":        label_dist,
        "spread_diagnostics": spread_diagnostics,
    }


def _do_backtest(slug, params, ticker, n_days):
    import warnings; warnings.filterwarnings("ignore")

    from alan_trader.db.loader import load_training_data
    data = load_training_data(ticker=ticker)

    spy   = data["spy"]
    vix   = data["vix"]
    r2    = data["rate2y"]
    r10   = data["rate10y"]
    macro = data["macro"]
    news  = data["news"]

    aux = {"vix": vix, "rate2y": r2, "rate10y": r10, "macro": macro,
           "news": news}

    # Load dividends for strategies that need them
    if slug in ("dividend_arb", "conversion_arb"):
        try:
            from alan_trader.db.client import get_engine as _ge_div, get_dividends
            _div_from = datetime.date.today() - datetime.timedelta(days=n_days * 2)
            aux["dividends"] = get_dividends(_ge_div(), ticker, _div_from, datetime.date.today())
            aux["ticker"] = ticker   # needed by conversion_arb for option chain lookups
            logger.info(f"{slug}: loaded {len(aux['dividends'])} dividend rows for {ticker}")
        except Exception as _e_div:
            logger.warning(f"Could not load dividends for {ticker}: {_e_div}")
            aux["dividends"] = pd.DataFrame()

    # Load TLT price bars for strategies that need them
    meta_for_slug = STRATEGY_METADATA.get(slug, {})
    if "tlt" in meta_for_slug.get("required_data", []):
        try:
            from alan_trader.db.client import get_engine, get_price_bars
            _engine = get_engine()
            _tlt_from = (datetime.date.today() - datetime.timedelta(days=n_days * 2))
            _tlt_df   = get_price_bars(_engine, "TLT", _tlt_from, datetime.date.today())
            if not _tlt_df.empty:
                _tlt_df["date"] = pd.to_datetime(_tlt_df["date"]).dt.date
                _tlt_df = _tlt_df.set_index("date")
            aux["tlt"] = _tlt_df
        except Exception as _e:
            logger.warning(f"Could not load TLT data: {_e}")
            aux["tlt"] = pd.DataFrame()

    # Load real saved option chains for vol_arbitrage from mkt.OptionSnapshot
    if slug == "vol_arbitrage":
        try:
            from alan_trader.db.options_loader import _load_chain
            from alan_trader.db.client import get_engine as _ge_va, get_ticker_id as _gtid_va
            _eng_va   = _ge_va()
            # Always load full 2-year history — don't limit by n_days so we get all available chains
            _opt_from = (datetime.date.today() - datetime.timedelta(days=730))
            _opt_to   = datetime.date.today()
            _tid_va   = _gtid_va(_eng_va, ticker or "SPY")
            if _tid_va:
                _raw = _load_chain(_eng_va, _tid_va, _opt_from, _opt_to, min_dte=7, max_dte=60)
                if not _raw.empty:
                    _raw["dte"] = (_raw["expiration_date"] - _raw["snapshot_date"]).apply(
                        lambda td: td.days if hasattr(td, "days") else int(td)
                    )
                    _raw = _raw.rename(columns={"contract_type": "type"})
                    _raw["type"] = _raw["type"].str.lower().map(
                        {"c": "call", "call": "call", "p": "put", "put": "put"}
                    )
                    # Load historical spot prices for BS repricing
                    from alan_trader.db.client import get_price_bars as _gpb_va
                    from alan_trader.db.sync import bs_price_chain as _bspc
                    _spots_df = _gpb_va(_eng_va, ticker, _opt_from, _opt_to)
                    _spot_map = {}
                    if not _spots_df.empty:
                        for _, _sr in _spots_df.iterrows():
                            _sd = _sr["date"].date() if hasattr(_sr["date"], "date") else _sr["date"]
                            _spot_map[_sd] = float(_sr["close"])

                    _chains_va = {}
                    for snap_date, grp in _raw.groupby("snapshot_date"):
                        import datetime as _dt
                        _key = snap_date if isinstance(snap_date, _dt.date) else pd.Timestamp(snap_date).date()
                        _chain = grp[["strike", "type", "bid", "ask", "iv", "delta", "dte"]].reset_index(drop=True)
                        # Reprice with historical spot so prices reflect each date's market level
                        _S = _spot_map.get(_key)
                        if _S:
                            _chain = _bspc(_chain, _S)
                        _chains_va[_key] = _chain
                    aux["options_chains"] = _chains_va
                    # Candidate suitability assessment
                    try:
                        from alan_trader.strategies.vol_arbitrage import VolArbitrageStrategy as _VAS
                        _va_tmp = _VAS(iv_skew_threshold=0.05)
                        aux["candidate_assessment"] = _va_tmp.assess_candidate(
                            _chains_va, df,
                            dte_min=7, dte_max=60,
                        )
                    except Exception as _e_ca:
                        logger.debug(f"Candidate assessment failed: {_e_ca}")
                    # Check bid/ask quality — detect BS-reconstructed prices.
                    # Real market data varies day-to-day; BS-reconstructed data
                    # from a single Polygon snapshot has near-constant bid values.
                    _bid_filled = _raw["bid"].notna() & (_raw["bid"] > 0)
                    if _bid_filled.any():
                        # Check bid price variance across dates for the same contract
                        _bid_std = _raw.groupby(["strike", "type"])["bid"].std().dropna()
                        _pct_static = (_bid_std < 0.001).sum() / max(len(_bid_std), 1)
                        _is_bs = _pct_static > 0.80   # >80% contracts show no day-to-day price change
                    else:
                        _is_bs = True
                    aux["option_data_quality"] = "bs_reconstructed" if _is_bs else "real_quotes"
                    logger.info(
                        f"vol_arbitrage: loaded {len(_chains_va)} chain snapshots for {ticker} "
                        f"[{'BS-reconstructed' if _is_bs else 'real bid/ask'}]"
                    )
                else:
                    logger.info(f"vol_arbitrage: no saved option chain for {ticker} — backtest will raise ValueError")
        except Exception as _e_va:
            logger.warning(f"vol_arbitrage: could not load option chain from DB: {_e_va}")

    # Load real option chains for the options rotation strategy
    if slug == "rates_spy_rotation_options":
        try:
            from alan_trader.db.options_loader import _load_chain
            from alan_trader.db.client import get_engine as _ge_o, get_ticker_id as _gtid_o
            _eng_o   = _ge_o()
            _opt_from = (datetime.date.today() - datetime.timedelta(days=n_days * 2))
            _opt_to   = datetime.date.today()
            _spy_tid  = _gtid_o(_eng_o, "SPY")
            _tlt_tid  = _gtid_o(_eng_o, "TLT")
            aux["spy_options"] = (
                _load_chain(_eng_o, _spy_tid, _opt_from, _opt_to, min_dte=15, max_dte=120)
                if _spy_tid else pd.DataFrame()
            )
            aux["tlt_options"] = (
                _load_chain(_eng_o, _tlt_tid, _opt_from, _opt_to, min_dte=15, max_dte=120)
                if _tlt_tid else pd.DataFrame()
            )
        except Exception as _e_o:
            logger.warning(f"Could not load options chain data: {_e_o}")
            aux["spy_options"] = pd.DataFrame()
            aux["tlt_options"] = pd.DataFrame()

    strat = get_strategy(slug)
    if not strat.is_ready():
        raise ValueError(f"Strategy {slug} is not ready.")

    # For vol arb: always skip parity arb when using DB data — all bid/ask are
    # BS-reconstructed from IV, so parity violations are circular artifacts, not
    # real market mispricings. Only skew arb is valid on this data.
    extra_params = {}
    if slug == "vol_arbitrage":
        extra_params["skip_parity_arb"] = True

    return strat.backtest(spy, aux, starting_capital=100_000, **params, **extra_params)


def _rebuild_portfolio_report():
    """Recompute portfolio report from all available bt_results."""
    results = list(st.session_state["bt_results"].values())
    if not results:
        return {}, pd.DataFrame()
    try:
        from alan_trader.portfolio.manager import PortfolioManager
        from alan_trader.db.client import get_engine as _pm_eng, get_price_bars as _pm_bars
        import datetime as _pm_dt
        _spy_raw  = _pm_bars(_pm_eng(), "SPY",
                             _pm_dt.date.today() - _pm_dt.timedelta(days=730),
                             _pm_dt.date.today())
        if _spy_raw.empty:
            return {}, pd.DataFrame()
        spy_rets = _spy_raw.set_index("date")["close"].pct_change().dropna()
        spy_rets.index = pd.to_datetime(spy_rets.index)
        pm       = PortfolioManager(total_capital=100_000, kelly_fraction=0.25,
                                    max_strategy_weight=0.40, min_strategy_weight=0.02)
        report   = pm.build_portfolio_report(results, spy_returns=spy_rets)
        window   = min(40, max(10, len(results[0].daily_returns) // 4))
        roll_w   = pm.rolling_weights(results, window=window)
        return report, roll_w
    except Exception as e:
        import logging; logging.getLogger(__name__).warning(f"Portfolio report failed: {e}")
        return {}, pd.DataFrame()


# ══════════════════════════════════════════════════════════════════════════════
# PER-STRATEGY TAB RENDERERS
# ══════════════════════════════════════════════════════════════════════════════

def _render_train(slug: str):
    """Training sub-tab — only called for strategies with requires_training=True."""
    from alan_trader.visualization import charts as C
    meta    = _meta(slug)
    uses_ml = meta.get("uses_ml", False)
    needs_ticker = meta.get("requires_ticker", True)

    st.subheader(f"Model Training — {meta['display_name']}")

    if not uses_ml:
        st.info(f"**{meta['display_name']}** is a rule-based strategy and does not require training.")
        return

    ticker = _ticker_row(f"train_{slug}") if needs_ticker else "N/A"

    with st.expander("Hyperparameters", expanded=True):
        from alan_trader.data.features import SPREAD_TYPE_OPTIONS
        spread_type_tr = st.selectbox(
            "Spread type to train for",
            options=list(SPREAD_TYPE_OPTIONS.keys()),
            format_func=lambda k: SPREAD_TYPE_OPTIONS[k],
            key=f"tr_{slug}_spread_type",
        )
        hp1, hp2, hp3 = st.columns(3)
        seq_len    = hp1.slider("Sequence length", 10, 60,  30, key=f"tr_{slug}_seq")
        hidden     = hp2.slider("Hidden size",     32, 256, 64, step=32, key=f"tr_{slug}_hidden")
        layers     = hp3.slider("LSTM layers",      1,   4,  1, key=f"tr_{slug}_layers")
        hp4, hp5, hp6 = st.columns(3)
        dropout    = hp4.slider("Dropout",  0.0, 0.5, 0.2, 0.05, key=f"tr_{slug}_dropout")
        lr         = hp5.select_slider("Learning rate",
                        options=[1e-4, 5e-4, 1e-3, 2e-3, 5e-3], value=1e-3,
                        key=f"tr_{slug}_lr")
        epochs     = hp6.slider("Max epochs", 20, 200, 60, step=10, key=f"tr_{slug}_epochs")
        hp7, hp8, hp9 = st.columns(3)
        forward_days = hp7.slider("Hold / forward days", 2, 20, 5, key=f"tr_{slug}_fwd")
        otm_pct_tr   = hp8.slider("OTM %", 0, 40, 0, 5,
                                   help="Strike offset for winners table leg price estimates.",
                                   key=f"tr_{slug}_otm")
        enter_boost_tr = hp9.slider("ENTER weight boost", 1.0, 5.0, 2.0, 0.5,
                                    help="Multiplies the ENTER class loss weight. "
                                         "Increase if the model produces no ENTER signals.",
                                    key=f"tr_{slug}_enter_boost")

    if needs_ticker:
        if st.button("🔍 Check options data for this ticker", key=f"btn_chk_opts_{slug}"):
            try:
                from alan_trader.db.client import get_engine as _ge2, get_ticker_id as _gtid
                from sqlalchemy import text as _text2
                _eng = _ge2()
                _tid = _gtid(_eng, ticker)
                if _tid is None:
                    st.warning(f"Ticker '{ticker}' not found in database. Make sure it's synced in the Data tab.")
                else:
                    with _eng.connect() as _c:
                        _r = _c.execute(_text2("""
                            SELECT COUNT(*) as cnt,
                                   MIN(SnapshotDate) as earliest,
                                   MAX(SnapshotDate) as latest,
                                   COUNT(DISTINCT SnapshotDate) as unique_dates
                            FROM mkt.OptionSnapshot WHERE TickerId = :tid
                        """), {"tid": _tid}).fetchone()
                    if _r and _r[0] > 0:
                        st.success(
                            f"**{ticker}** has **{int(_r[0]):,}** option snapshot rows "
                            f"({_r[2]} unique dates, {_r[1]} → {_r[2]}). "
                            "Real spread P&L should be available for training."
                        )
                    else:
                        st.warning(
                            f"No option snapshot data found for **{ticker}**. "
                            "Go to the **🗄 Data** tab → **Sync from Polygon** → **Options Chain** to download it."
                        )
            except Exception as _ex:
                st.error(f"DB check failed: {_ex}")

    if st.button("▶ Train Model", type="primary", key=f"btn_train_{slug}"):
        with st.spinner("Training… this may take a minute."):
            try:
                result = _do_train(slug, seq_len, hidden, layers, dropout, lr, epochs,
                                   ticker=ticker if needs_ticker else "SPY",
                                   forward_days=forward_days, otm_pct=otm_pct_tr,
                                   spread_type=spread_type_tr,
                                   enter_boost=enter_boost_tr)
                st.session_state["train_results"][slug] = result
                st.rerun()
            except Exception as ex:
                import traceback
                st.session_state[f"train_error_{slug}"] = traceback.format_exc()

    err = st.session_state.get(f"train_error_{slug}")
    if err:
        st.error("Training failed — see details below:")
        st.code(err, language="python")

    train_res = st.session_state["train_results"].get(slug)
    if train_res is None:
        st.info("Configure hyperparameters above and press **▶ Train Model** to start.")
        return

    history      = train_res["history"]
    cm           = train_res["cm"]
    feat_imp     = train_res["feat_imp"]
    feat_df      = train_res["feat_df"]
    FEATURE_COLS = train_res["FEATURE_COLS"]

    trained_spread = train_res.get("spread_type", "bull_call")
    from alan_trader.data.features import SPREAD_TYPE_OPTIONS as _STO
    spread_label = _STO.get(trained_spread, trained_spread)

    n_ep = len(history["val_acc"])
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Best Val Accuracy", f"{max(history['val_acc']):.1%}")
    m2.metric("Final Val Loss",    f"{history['val_loss'][-1]:.4f}")
    m3.metric("Epochs Run",        n_ep)
    m4.metric("Spread Type",       spread_label.split("(")[0].strip())

    ld = train_res.get("label_dist", {})
    if ld:
        total_ld = sum(ld.values()) or 1
        l1, l2, l3 = st.columns(3)
        l1.metric("AVOID labels", f"{ld.get('avoid', 0):,}",
                  delta=f"{ld.get('avoid', 0)/total_ld:.0%}", delta_color="off")
        l2.metric("SKIP labels",  f"{ld.get('skip',  0):,}",
                  delta=f"{ld.get('skip',  0)/total_ld:.0%}", delta_color="off")
        l3.metric("ENTER labels", f"{ld.get('enter', 0):,}",
                  delta=f"{ld.get('enter', 0)/total_ld:.0%}", delta_color="off")
        if ld.get("enter", 0) / total_ld < 0.15:
            st.warning("ENTER labels are <15% of training data — increase ENTER weight boost "
                       "or switch to a credit spread (bull_put / iron_condor) which has more ENTER signals.")

    # ── Model ENTER signals — shown first ──────────────────────────────────
    winner_samples = train_res.get("winner_samples")
    n_confirmed    = train_res.get("n_confirmed", 0)
    st.markdown("---")

    # Column config adapts to whether real options P&L is available
    has_real = winner_samples is not None and "Profit / Loss" in (winner_samples.columns if winner_samples is not None else [])
    if has_real:
        col_cfg = {
            "Result":           st.column_config.TextColumn("Result",          width="small"),
            "Trade Date":       st.column_config.DateColumn("Trade Date"),
            "Closed Date":      st.column_config.DateColumn("Closed Date"),
            "Collected":        st.column_config.NumberColumn("Collected",      format="$%.2f",
                                    help="Premium received when opening the position (1 contract = 100 shares)"),
            "Paid":             st.column_config.NumberColumn("Paid",           format="$%.2f",
                                    help="Premium paid when opening the position (1 contract = 100 shares)"),
            "Cost to Close":    st.column_config.NumberColumn("Cost to Close",  format="$%.2f",
                                    help="What it cost to buy back / close the spread"),
            "Sold For":         st.column_config.NumberColumn("Sold For",       format="$%.2f",
                                    help="What the spread was worth when closed"),
            "Profit / Loss":    st.column_config.NumberColumn("Profit / Loss",  format="$%.2f",
                                    help="Net profit or loss per contract at close"),
            "% of Max Profit":  st.column_config.NumberColumn("% of Max",       format="%.1f%%",
                                    help="How much of the best-case profit was captured (or how deep into a loss)"),
            "Max Profit":       st.column_config.NumberColumn("Max Profit",     format="$%.2f",
                                    help="Best possible outcome if held to expiry and all legs expire worthless"),
            "Max Loss":         st.column_config.NumberColumn("Max Loss",       format="$%.2f",
                                    help="Worst possible outcome (spread fully against you at expiry)"),
            "Model Confidence": st.column_config.ProgressColumn("Confidence",  min_value=0, max_value=100, format="%.0f%%"),
        }
        caption = ""
    else:
        col_cfg = {
            "entry date":  st.column_config.TextColumn("Trade Date"),
            "outcome":     st.column_config.TextColumn("Result",        width="small"),
            "structure":   st.column_config.TextColumn("Structure",     width="large"),
            "spot":        st.column_config.NumberColumn("Spot",        format="$%.2f"),
            "cost $/ct":   st.column_config.NumberColumn("Cost/ct",     format="$%.2f"),
            "hold days":   st.column_config.NumberColumn("Hold Days",   format="%d"),
            "fwd ret %":   st.column_config.NumberColumn("Stock Move",  format="%.2f%%"),
            "confidence":  st.column_config.ProgressColumn("Confidence", min_value=0, max_value=100, format="%.0f%%"),
        }
        caption = (
            f"Black-Scholes approximation — no options chain data available for this ticker. "
            f"'Stock Move' = underlying % change over the hold period."
        )

    # ── Options data diagnostics (shown when real P&L is unavailable) ───────
    trained_ticker = train_res.get("ticker", "?")
    diag = train_res.get("spread_diagnostics", {})
    if not has_real and diag:
        with st.expander("Options data diagnostics — why is Black-Scholes being used?", expanded=True):
            if "error" in diag:
                st.error(f"**Error:** {diag['error']}")
            else:
                d1, d2, d3 = st.columns(3)
                d1.metric("Chain rows loaded", f"{diag.get('chain_rows', 0):,}")
                d2.metric("Price bars",         f"{diag.get('n_price_bars', 0):,}")
                d3.metric("Entry dates tried",  f"{diag.get('n_entry_dates', 0):,}")
                if diag.get("n_entry_dates", 0) > 0:
                    f1, f2, f3, f4, f5 = st.columns(5)
                    f1.metric("No expiry found", diag.get("n_no_expiry", 0),
                              help="No option expiration within ±21 days of target DTE")
                    f2.metric("Legs failed",     diag.get("n_no_legs", 0),
                              help="Nearest strike selection failed (check OTM% / wing%)")
                    f3.metric("Entry price N/A", diag.get("n_no_entry_val", 0),
                              help="Could not get mid price for one or more legs")
                    f4.metric("Sign mismatch",   diag.get("n_sign_fail", 0),
                              help="Spread priced as wrong direction (credit/debit)")
                    f5.metric("No exit data",    diag.get("n_no_exit", 0),
                              help="No chain snapshot found for exit date within +7 days")
                st.caption(
                    f"DTE filter: {diag.get('dte_filter', 'N/A')} | "
                    f"Date range: {diag.get('date_range', 'N/A')} | "
                    f"Rows produced: {diag.get('n_rows', 0)}"
                )
                if diag.get("chain_rows", 0) == 0:
                    st.warning(
                        f"No option chain rows found for **{trained_ticker}** ({trained_spread}). "
                        "Go to the **🗄 Data** tab and check Options Chain Coverage — options data must be synced for this ticker first."
                    )
                elif diag.get("n_no_expiry", 0) == diag.get("n_entry_dates", 0):
                    st.warning(
                        "Options data exists but no expiration matched target DTE. "
                        "Try adjusting the Hold/Forward Days slider or use a longer target DTE."
                    )
                elif diag.get("n_no_legs", 0) > diag.get("n_entry_dates", 0) * 0.5:
                    st.warning(
                        "Strike selection failed for most dates. "
                        "The OTM% or wing% may be too large — try reducing them, "
                        "or the option chain may have wide strike spacing."
                    )
                elif diag.get("n_no_exit", 0) > diag.get("n_entry_dates", 0) * 0.5:
                    st.warning(
                        "Exit chain data missing for most dates. "
                        "Options snapshots may not cover a contiguous enough date range "
                        "for the selected hold period."
                    )
                elif diag.get("n_rows", 0) > 0:
                    st.warning(
                        f"Only {diag['n_rows']} spread rows produced — below the minimum of 50 needed. "
                        "Widen the date range or use a different spread type."
                    )

    if winner_samples is not None and not winner_samples.empty:
        n_total   = len(winner_samples)
        n_wins    = (winner_samples.get("Result", pd.Series()).str.startswith("✅")).sum()
        win_rate  = n_wins / n_total if n_total else 0

        if has_real:
            avg_win  = winner_samples.loc[winner_samples["Result"].str.startswith("✅"), "Profit / Loss"].mean()
            avg_loss = winner_samples.loc[winner_samples["Result"].str.startswith("❌"), "Profit / Loss"].mean()
            st.subheader(f"Trades the model selected — {n_total} total, {n_wins} profitable ({win_rate:.0%} win rate)")
            st.caption(
                f"Each row is a **{spread_label}** trade the model said to take, with the real historical outcome. "
                f"Avg profit on winners: **${avg_win:.0f}/contract** · "
                f"Avg loss on losers: **${avg_loss:.0f}/contract**"
                if not np.isnan(avg_win) and not np.isnan(avg_loss) else
                f"Each row is a **{spread_label}** trade the model said to take, with the real historical outcome."
            )
        else:
            st.subheader(f"Trades the model selected — {n_total} total, {n_wins} confirmed profitable ({win_rate:.0%})")
            st.caption(caption)

        st.dataframe(winner_samples, width="stretch",
                     column_config=col_cfg, hide_index=True)

        if has_real:
            st.markdown("---")
            pa1, pa2 = st.columns(2)
            with pa1:
                st.plotly_chart(
                    C.signal_cumulative_pnl(winner_samples, spread_label),
                    width="stretch", key=f"tr_{slug}_cpnl",
                )
            with pa2:
                st.plotly_chart(
                    C.signal_winrate_by_confidence(winner_samples),
                    width="stretch", key=f"tr_{slug}_wr",
                )
            st.plotly_chart(
                C.signal_pnl_distribution(winner_samples),
                width="stretch", key=f"tr_{slug}_dist",
            )
    else:
        st.info(f"Model generated no ENTER signals for **{spread_label}** in the test period. "
                "Try more epochs or a different spread type.")

    st.markdown("---")
    with st.expander("Training Curves", expanded=False):
        c1, c2 = st.columns(2)
        with c1: st.plotly_chart(C.loss_curves(history),     width="stretch")
        with c2: st.plotly_chart(C.accuracy_curves(history), width="stretch")

    with st.expander("Confusion Matrix", expanded=False):
        st.caption("How often the model was right for each class. "
                   "High ENTER precision = fewer false trade signals.")
        st.plotly_chart(C.confusion_matrix_heatmap(cm), width="stretch")

    with st.expander("Top Features Driving Signals", expanded=False):
        st.caption("Which market conditions the model weighted most heavily.")
        st.plotly_chart(C.feature_importance_bar(feat_imp, top_n=15), width="stretch")


def _render_regime_chart(slug: str, res):
    """Render regime-annotated SPY + 10Y yield + VIX chart for rotation strategies."""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    extra = res.extra
    regime_series = extra.get("regime_series")
    spy_weights   = extra.get("spy_weights")
    tlt_weights   = extra.get("tlt_weights")
    spy_prices    = extra.get("spy_prices")
    tlt_prices    = extra.get("tlt_prices")
    rate10y       = extra.get("rate10y")
    vix           = extra.get("vix")
    equity        = res.equity_curve

    if regime_series is None:
        return

    _REGIME_COLORS = {
        "Growth":     "rgba(38,166,154,0.25)",
        "Inflation":  "rgba(239,83,80,0.25)",
        "Fear":       "rgba(92,107,192,0.25)",
        "Risk-On":    "rgba(255,167,38,0.25)",
        "Transition": "rgba(120,144,156,0.15)",
    }
    _REGIME_LINE = {
        "Growth":     "#26a69a",
        "Inflation":  "#ef5350",
        "Fear":       "#5c6bc0",
        "Risk-On":    "#ffa726",
        "Transition": "#78909c",
    }

    with st.expander("Regime Map — Portfolio / SPY & TLT / VIX & Yield", expanded=True):
        fig = make_subplots(
            rows=3, cols=1,
            shared_xaxes=True,
            row_heights=[0.38, 0.38, 0.24],
            subplot_titles=(
                "Portfolio Equity",
                "SPY & TLT (indexed)  ·  VIX →",
                "Regime",
            ),
            vertical_spacing=0.05,
            specs=[[{"secondary_y": True}],
                   [{"secondary_y": True}],
                   [{"secondary_y": False}]],
        )

        # ── Row 1: Portfolio equity (left) + 10Y Yield (right) ────────────────
        idx = pd.to_datetime(equity.index)
        fig.add_trace(go.Scatter(
            x=idx, y=equity.values,
            name="Portfolio", line=dict(color="#26a69a", width=2),
        ), row=1, col=1, secondary_y=False)

        if rate10y is not None and not rate10y.empty:
            r10_idx = pd.to_datetime(rate10y.index)
            fig.add_trace(go.Scatter(
                x=r10_idx, y=(rate10y * 100).values,
                name="10Y Yield (%)", line=dict(color="#ffa726", width=1.2, dash="dot"),
            ), row=1, col=1, secondary_y=True)

        fig.update_yaxes(title_text="Equity ($)", row=1, col=1, secondary_y=False,
                         title_font=dict(color="#26a69a"), tickfont=dict(color="#26a69a"))
        fig.update_yaxes(title_text="10Y Yield (%)", row=1, col=1, secondary_y=True,
                         title_font=dict(color="#ffa726"), tickfont=dict(color="#ffa726"))

        # ── Row 2: SPY + TLT indexed prices (left) | VIX shaded (right) ──────
        # Base strategy: use actual price data if available; fall back to weights
        _spy_line = spy_prices if spy_prices is not None and not spy_prices.empty else (
            spy_weights * 500 if spy_weights is not None else None   # weights scaled for visibility
        )
        _tlt_line = tlt_prices if tlt_prices is not None and not tlt_prices.empty else (
            tlt_weights * 150 if tlt_weights is not None else None
        )

        if _spy_line is not None:
            sp_idx = pd.to_datetime(_spy_line.index)
            base = _spy_line.dropna().iloc[0] if not _spy_line.dropna().empty else 1
            fig.add_trace(go.Scatter(
                x=sp_idx, y=(_spy_line / base * 100).values,
                name="SPY (indexed)", line=dict(color="#5c6bc0", width=2),
            ), row=2, col=1, secondary_y=False)

        if _tlt_line is not None:
            tp_idx = pd.to_datetime(_tlt_line.index)
            base = _tlt_line.dropna().iloc[0] if not _tlt_line.dropna().empty else 1
            fig.add_trace(go.Scatter(
                x=tp_idx, y=(_tlt_line / base * 100).values,
                name="TLT (indexed)", line=dict(color="#ab47bc", width=2),
            ), row=2, col=1, secondary_y=False)

        if vix is not None and not (isinstance(vix, pd.Series) and vix.empty):
            vix_idx = pd.to_datetime(vix.index)
            fig.add_trace(go.Scatter(
                x=vix_idx, y=vix.values,
                name="VIX", line=dict(color="#ef5350", width=1),
                fill="tozeroy", fillcolor="rgba(239,83,80,0.08)",
            ), row=2, col=1, secondary_y=True)
            for level, label in [(20, "20"), (30, "30")]:
                fig.add_hline(y=level, line=dict(color="#ef5350", dash="dash", width=0.7),
                              row=2, col=1, secondary_y=True,
                              annotation_text=f"VIX {label}",
                              annotation_font=dict(color="#ef5350", size=9),
                              annotation_position="right")

        fig.update_yaxes(title_text="Indexed (100 = start)", row=2, col=1, secondary_y=False,
                         title_font=dict(color="#b0b8c8"), tickfont=dict(color="#b0b8c8"))
        fig.update_yaxes(title_text="VIX", row=2, col=1, secondary_y=True,
                         title_font=dict(color="#ef5350"), tickfont=dict(color="#ef5350"))

        # ── Row 3: Regime strip ────────────────────────────────────────────────
        regime_idx = pd.to_datetime(regime_series.index)
        for rname, rcolor in _REGIME_LINE.items():
            mask = regime_series == rname
            if mask.any():
                xs, ys = [], []
                prev_in = False
                for dt, val in zip(regime_idx, regime_series):
                    if val == rname:
                        xs.append(dt); ys.append(rname); prev_in = True
                    else:
                        if prev_in:
                            xs.append(None); ys.append(None)
                        prev_in = False
                fig.add_trace(go.Scatter(
                    x=xs, y=ys, name=rname, mode="markers",
                    marker=dict(color=rcolor, size=6, symbol="square"),
                    showlegend=True,
                ), row=3, col=1)

        fig.update_layout(
            height=680,
            paper_bgcolor="#0c1020",
            plot_bgcolor="#0c1020",
            font=dict(color="#e0e0e0"),
            legend=dict(orientation="h", y=-0.05, x=0, yanchor="top"),
            margin=dict(t=50, b=80),
        )
        fig.update_yaxes(gridcolor="#1e2130", zeroline=False)
        fig.update_xaxes(gridcolor="#1e2130")
        st.plotly_chart(fig, width="stretch", key=f"bt_{slug}_regime_map")


def _render_backtest(slug: str):
    """Backtest sub-tab — universal for all strategies."""
    from alan_trader.visualization import charts as C
    meta         = _meta(slug)
    needs_ticker = meta.get("requires_ticker", True)

    st.subheader(f"Backtesting — {meta['display_name']}")

    ticker = _ticker_row(f"bt_{slug}") if needs_ticker else None

    # Date range
    today = datetime.date.today()
    dr1, dr2 = st.columns(2)
    bt_start = dr1.date_input("Start", value=today - datetime.timedelta(days=730),
                               max_value=today - datetime.timedelta(days=60),
                               key=f"bt_{slug}_start")
    bt_end   = dr2.date_input("End",   value=today - datetime.timedelta(days=1),
                               max_value=today, key=f"bt_{slug}_end")
    n_days   = max(60, int((bt_end - bt_start).days * 252 / 365))
    st.caption(f"≈ {n_days} trading days")

    # Strategy-specific parameters — driven by strategy.get_backtest_ui_params()
    params = {}
    _strat_for_ui = get_strategy(slug)
    _param_specs  = _strat_for_ui.get_backtest_ui_params()
    with st.expander("Strategy Parameters", expanded=True):
        if _param_specs:
            params = _render_ui_params(_param_specs, f"bt_{slug}")
        else:
            st.caption("No configurable parameters for this strategy.")

    if st.button("▶ Run Backtest", type="primary", key=f"btn_bt_{slug}"):
        with st.spinner(f"Running {meta['display_name']} backtest…"):
            try:
                res = _do_backtest(slug, params, ticker or "SPY", n_days)
                st.session_state["bt_results"][slug] = res

                # Rebuild aggregate portfolio report
                report, roll_w = _rebuild_portfolio_report()
                st.session_state["bt_report"]    = report
                st.session_state["bt_rolling_w"] = roll_w

                # Persist to portfolio store
                try:
                    from alan_trader.portfolio.store import PortfolioStore
                    _store = PortfolioStore()
                    _store.ingest_backtest([res], report)
                    st.session_state["portfolio_store"] = _store
                except Exception: pass

                st.success("Backtest complete!")
                st.rerun()
            except Exception as ex:
                import traceback
                st.error(f"Backtest failed: {ex}")
                st.code(traceback.format_exc())

    res = st.session_state["bt_results"].get(slug)
    if res is None:
        st.info("Configure settings above and press **▶ Run Backtest**.")
        return

    # Data quality warning for vol arb (IV-only data means no real bid/ask)
    if slug == "vol_arbitrage":
        _dq = (res.extra or {}).get("data_quality", "unknown")
        if _dq in ("iv_only", "bs_reconstructed"):
            st.warning(
                "⚠️ **BS-reconstructed prices** — Polygon does not provide historical bid/ask quotes on this plan. "
                "Option prices are calculated from IV using Black-Scholes. "
                "**Parity arb is disabled** (circular artifact when prices are reconstructed from IV). "
                "Only **IV Skew Arb** trades run. "
                "P&L is computed from delta + theta effects (BS price change as spot moves and time passes). "
                "To enable parity arb, connect to a provider with real historical quotes (IBKR, Tradier).",
            )
        elif _dq == "real_quotes":
            st.success("✅ Real bid/ask quotes — full parity violation + skew arb detection active.")

        # Show chain coverage diagnostics
        _ex = res.extra or {}
        _nc = _ex.get("n_chain_dates", "?")
        _np = _ex.get("n_price_dates", "?")
        _nm = _ex.get("n_chain_matches", "?")
        if _nc != "?":
            st.caption(
                f"Chain coverage: **{_nc}** snapshot dates in DB  ·  "
                f"**{_np}** price bars  ·  "
                f"**{_nm}** dates with both price + chain data (potential trade days)"
            )

        # Candidate suitability panel
        _ca = _ex.get("candidate_assessment")
        if _ca:
            _score   = _ca["score"]
            _verdict = _ca["verdict"]
            _color   = _ca["color"]
            _mets    = _ca.get("metrics", {})
            _color_map = {"green": "🟢", "orange": "🟡", "red": "🔴", "gray": "⚫"}
            _icon = _color_map.get(_color, "⚪")
            with st.expander(f"{_icon} **Ticker suitability: {_verdict}** — Score {_score}/100", expanded=(_score >= 45)):
                _ca1, _ca2, _ca3, _ca4, _ca5 = st.columns(5)
                _ca1.metric("Score",         f"{_score}/100")
                _ca2.metric("Avg IV Skew",   f"{_mets.get('avg_iv_skew_pts', '?')} vp")
                _ca3.metric("Avg ATM IV",    f"{_mets.get('avg_atm_iv_pct', '?')}%")
                _ca4.metric("$/lot premium", f"${_mets.get('avg_dollar_prem', '?'):.0f}" if _mets.get('avg_dollar_prem') else "?")
                _trend = _mets.get("price_trend_pct")
                _ca5.metric("Price trend",   f"{_trend:+.1f}%" if _trend is not None else "?")
                for _r in _ca.get("reasons", []):
                    st.markdown(_r)

    m = res.metrics
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Return",  f"{m.get('total_return_pct', 0):+.1f}%")
    c2.metric("Sharpe",        f"{m.get('sharpe', 0):.2f}")
    c3.metric("Max Drawdown",  f"{m.get('max_drawdown_pct', 0):.1f}%")
    c4.metric("Win Rate",      f"{m.get('win_rate_pct', 0):.1f}%")
    c5.metric("Profit Factor", f"{m.get('profit_factor', 0):.2f}")

    # ── All trades table — always shown ───────────────────────────────────
    trades = res.trades
    if isinstance(trades, list):
        trades = pd.DataFrame([vars(t) for t in trades]) if trades else pd.DataFrame()

    st.markdown("---")
    if trades.empty:
        st.info("No trades were executed. Try lowering Min Confidence or widening the date range.")
    else:
        n_total   = len(trades)
        n_winners = int((trades["pnl"] > 0).sum())  if "pnl" in trades.columns else 0
        n_losers  = int((trades["pnl"] < 0).sum())  if "pnl" in trades.columns else 0
        n_flat    = n_total - n_winners - n_losers
        _flat_str = f" / {n_flat} no-data" if n_flat > 0 else ""
        st.subheader(f"Trades — {n_winners} winners / {n_losers} losers / {n_total} total{_flat_str}")
        if "long_strike" in trades.columns:
            st.caption("Long/short leg prices are per-share option prices at entry. "
                       "Spread cost = long leg − short leg + slippage.")

        disp = trades.copy()
        if "entry_cost" in disp.columns and "predicted_spread_price" in disp.columns:
            disp["price_error"] = (disp["predicted_spread_price"] - disp["entry_cost"]).round(4)
        if "pnl" in disp.columns:
            disp["cum_pnl"] = disp["pnl"].cumsum().round(2)
        # Convert IV columns to % for display (stored as decimals 0–1)
        for _iv_col in ["iv_call", "iv_put", "iv_skew"]:
            if _iv_col in disp.columns:
                disp[_iv_col] = (disp[_iv_col] * 100).round(2)

        # Strategy-aware column selection
        if "description" in disp.columns:
            # Vol Arb: actual net premium cash flows (not margin)
            if "call_price_entry" in disp.columns and "put_price_entry" in disp.columns:
                # Net debit to enter: call_bought − put_sold (positive = net debit)
                disp["total_in"]  = ((disp["call_price_entry"] - disp["put_price_entry"])
                                     * disp["contracts"] * 100).round(2)
                if "pnl" in disp.columns:
                    disp["total_out"] = (disp["total_in"] + disp["pnl"]).round(2)
            elif "entry_cost" in disp.columns and "contracts" in disp.columns:
                disp["total_in"]  = (disp["entry_cost"] * disp["contracts"] * 100).round(2)
                if "exit_value" in disp.columns:
                    disp["total_out"] = (disp["exit_value"] * disp["contracts"] * 100).round(2)
            # Vol Arb — lead with description so user can follow the trade
            # (drop violation/signal_strength — always 0/1 for skew_arb, adds no info)
            show_cols = [c for c in [
                "W/L", "entry_date", "exit_date",
                "contracts", "trade_type",
                "iv_call", "iv_put", "iv_skew",
                "total_in", "total_out",
                "put_pnl", "call_pnl", "hedge_pnl", "commission",
                "pnl", "cum_pnl", "exit_reason",
            ] if c in disp.columns]
        elif slug == "conversion_arb":
            show_cols = [c for c in [
                "W/L", "entry_date", "exit_date",
                "strike", "contracts", "dte",
                "actual_div", "implied_div", "edge",
                "total_in", "pnl", "return_pct", "cum_pnl",
            ] if c in disp.columns]
        else:
            show_cols = [c for c in [
                "entry_date", "exit_date", "spread_type",
                "long_strike", "long_leg_price",
                "short_strike", "short_leg_price",
                "entry_cost", "exit_value",
                "predicted_spread_price", "price_error",
                "pnl", "cum_pnl", "exit_reason",
            ] if c in disp.columns]

        col_cfg = {
            "pnl":                    st.column_config.NumberColumn("P&L ($)",           format="$%.2f"),
            "cum_pnl":                st.column_config.NumberColumn("Cum. P&L ($)",      format="$%.2f"),
            "expected_pnl":           st.column_config.NumberColumn("Expected P&L ($)",  format="$%.2f"),
            "entry_cost":             st.column_config.NumberColumn("Entry Cost ($)",     format="$%.4f"),
            "exit_value":             st.column_config.NumberColumn("Exit Value ($)",     format="$%.4f"),
            "predicted_spread_price": st.column_config.NumberColumn("Predicted ($)",     format="$%.4f"),
            "price_error":            st.column_config.NumberColumn("Price Error ($)",    format="$%.4f"),
            "long_strike":            st.column_config.NumberColumn("Long Strike",        format="$%.0f"),
            "short_strike":           st.column_config.NumberColumn("Short Strike",       format="$%.0f"),
            "long_leg_price":         st.column_config.NumberColumn("Long Leg ($)",       format="$%.4f"),
            "short_leg_price":        st.column_config.NumberColumn("Short Leg ($)",      format="$%.4f"),
            "spot":                   st.column_config.NumberColumn("Spot",               format="$%.2f"),
            "strike":                 st.column_config.NumberColumn("Strike",             format="$%.1f"),
            "total_in":               st.column_config.NumberColumn("Capital In ($)",     format="$%.2f"),
            "return_pct":             st.column_config.NumberColumn("Return on Capital",  format="%.2f%%"),
            "total_out":              st.column_config.NumberColumn("Total Out ($)",      format="$%.2f"),
            "put_pnl":                st.column_config.NumberColumn("Put P&L ($)",        format="$%.2f"),
            "call_pnl":               st.column_config.NumberColumn("Call P&L ($)",       format="$%.2f"),
            "hedge_pnl":              st.column_config.NumberColumn("Hedge P&L ($)",      format="$%.2f"),
            "commission":             st.column_config.NumberColumn("Commiss. ($)",        format="$%.2f"),
            "iv_call":                st.column_config.NumberColumn("Call IV (%)",        format="%.2f%%"),
            "iv_put":                 st.column_config.NumberColumn("Put IV (%)",         format="%.2f%%"),
            "iv_skew":                st.column_config.NumberColumn("IV Skew (%)",        format="%.2f%%"),
            "violation":              st.column_config.NumberColumn("Parity Viol.",       format="%.4f"),
            "signal_strength":        st.column_config.NumberColumn("Signal",             format="%.3f"),
            "W/L":                    st.column_config.TextColumn("", width="small"),
        }

        # Add visual columns
        disp = disp.copy()
        if "pnl" in disp.columns:
            disp.insert(0, "W/L", disp["pnl"].apply(
                lambda v: "🟢" if isinstance(v, (int, float)) and v > 0
                else ("🔴" if isinstance(v, (int, float)) and v < 0 else "⚪")
            ))

        def _render_trade_detail(row):
            pnl       = row.get("pnl", None)
            cum_pnl   = row.get("cum_pnl", None)
            pnl_color = "#26a69a" if isinstance(pnl, (int, float)) and pnl > 0 else "#ef5350"

            # Header
            st.markdown(
                f"### {row.get('entry_date', '')} → {row.get('exit_date', '')}"
                f"&nbsp;&nbsp;&nbsp;<span style='color:{pnl_color};font-size:1.3em;font-weight:700'>"
                f"{f'${pnl:+,.2f}' if isinstance(pnl,(int,float)) else ''}</span>",
                unsafe_allow_html=True,
            )
            st.divider()

            def _fmt(v): return f"${v:+,.2f}" if isinstance(v, (int, float)) and v == v else "—"

            if row.get("spread_type") == "conversion":
                # ── Conversion Arb metrics ─────────────────────────────────────
                m1, m2, m3, m4, m5 = st.columns(5)
                m1.metric("Contracts",    row.get("contracts", "—"))
                m2.metric("Strike",       f"${row.get('strike', 0):.2f}" if row.get('strike') else "—")
                m3.metric("Actual Div",   f"${row.get('actual_div', 0):.4f}" if row.get('actual_div') else "—")
                m4.metric("Implied Div",  f"${row.get('implied_div', 0):.4f}" if row.get('implied_div') is not None else "—")
                m5.metric("Edge/sh",      f"${row.get('edge', 0):.4f}" if row.get('edge') is not None else "—")

                st.markdown("#### P&L Breakdown")
                p1, p2, p3, p4, p5, p6 = st.columns(6)
                p1.metric("Stock P&L",      _fmt(row.get("stock_pnl")))
                p2.metric("Put P&L",        _fmt(row.get("put_pnl")))
                p3.metric("Call P&L",       _fmt(row.get("call_pnl")))
                p4.metric("Div Received",   _fmt(row.get("div_received")))
                p5.metric("Commissions",    _fmt(row.get("commissions")))
                p6.metric("Net P&L",        _fmt(pnl))
            else:
                # ── Vol Arb / Spread metrics ───────────────────────────────────
                m1, m2, m3, m4, m5 = st.columns(5)
                m1.metric("Contracts",  row.get("contracts", "—"))
                m2.metric("Call IV",    f"{row.get('iv_call', 0):.1f}%" if row.get('iv_call') else "—")
                m3.metric("Put IV",     f"{row.get('iv_put',  0):.1f}%" if row.get('iv_put')  else "—")
                m4.metric("IV Skew",    f"{row.get('iv_skew', 0):.1f}vp" if row.get('iv_skew') else "—")
                m5.metric("Exit",       str(row.get("exit_reason", "—")))

                st.markdown("#### P&L Breakdown")
                p1, p2, p3, p4, p5 = st.columns(5)
                p1.metric("Put P&L",    _fmt(row.get("put_pnl")))
                p2.metric("Call P&L",   _fmt(row.get("call_pnl")))
                p3.metric("Hedge P&L",  _fmt(row.get("hedge_pnl")))
                p4.metric("Commission", _fmt(row.get("commission")))
                p5.metric("Net P&L",    _fmt(pnl))

                _exp_pnl = row.get("expected_pnl")
                _iv_sk   = row.get("iv_skew")
                if isinstance(_exp_pnl, (int, float)) and _exp_pnl == _exp_pnl and isinstance(_iv_sk, (int, float)):
                    st.divider()
                    st.markdown("#### IV Skew Scenario")
                    sc1, sc2, sc3 = st.columns(3)
                    sc1.metric("Skew at Entry",        f"{_iv_sk:.1f} vp")
                    sc2.metric("Expected P&L (full compression)", f"${_exp_pnl:+,.0f}")
                    _per_vp = _exp_pnl / _iv_sk if _iv_sk else 0
                    sc3.metric("$ per vol pt compressed", f"${_per_vp:+,.0f}")

            st.divider()

            # Position — structured from trade fields
            st.markdown("#### Position")
            _K        = row.get("strike") or row.get("long_strike")
            _dte      = row.get("dte", "?")
            _spot     = row.get("spot", "?")
            _n        = row.get("contracts", "?")
            _put_p    = row.get("put_price_entry")
            _call_p   = row.get("call_price_entry")
            _cost     = row.get("total_in") or row.get("cost")
            _iv_c     = row.get("iv_call")
            _iv_p     = row.get("iv_put")
            _iv_sk    = row.get("iv_skew")
            _pos_lines = []
            if _K:      _pos_lines.append(f"**Strike:** ${_K}  |  **DTE:** {_dte}d  |  **Spot at entry:** ${_spot}  |  **Size:** {_n} contracts")
            if _put_p:  _pos_lines.append(f"**Sell put** @ ${_put_p:.3f}  ·  **Buy call** @ ${_call_p:.3f}" if _call_p else f"**Sell put** @ ${_put_p:.3f}")
            if _cost:   _pos_lines.append(f"**Net {'credit' if _cost < 0 else 'debit'}:** ${abs(_cost):,.2f}")
            if _iv_c:   _pos_lines.append(f"**Call IV:** {_iv_c:.2f}%  ·  **Put IV:** {_iv_p:.2f}%" if _iv_p else f"**Call IV:** {_iv_c:.2f}%")
            st.info("\n\n".join(_pos_lines) if _pos_lines else str(row.get("description", "—")))

            # 3-leg breakdown for conversion arb
            if row.get("spread_type") == "conversion":
                st.markdown("#### Trade Legs")
                _n   = row.get("contracts", 1)
                _sh  = _n * 100
                _leg_df = pd.DataFrame([
                    {"Leg": f"① Long Stock ({_sh:,} sh)", "Side": "Buy",
                     "Entry": f"${row.get('entry_price',0):,.2f}",
                     "Exit":  f"${row.get('exit_price',0):,.2f}",
                     "P&L":   f"${row.get('stock_pnl',0):+,.2f}"},
                    {"Leg": f"② Long Put ({_n} cts)", "Side": "Buy",
                     "Entry": f"${row.get('put_entry_px',0):.3f}",
                     "Exit":  f"${row.get('put_exit_px',0):.3f}",
                     "P&L":   f"${row.get('put_pnl',0):+,.2f}"},
                    {"Leg": f"③ Short Call ({_n} cts)", "Side": "Sell",
                     "Entry": f"${row.get('call_entry_px',0):.3f}",
                     "Exit":  f"${row.get('call_exit_px',0):.3f}",
                     "P&L":   f"${row.get('call_pnl',0):+,.2f}"},
                ])
                st.dataframe(_leg_df, hide_index=True, width="stretch")
                st.markdown(
                    f"**Dividend received:** ${row.get('div_received',0):+,.2f} &nbsp;·&nbsp; "
                    f"**Carry:** −${row.get('carry_cost',0):,.2f} &nbsp;·&nbsp; "
                    f"**Commission:** −${row.get('commissions',0):,.2f} &nbsp;·&nbsp; "
                    f"**Net P&L: ${row.get('pnl',0):+,.2f}**"
                )
                st.caption(f"Actual div: ${row.get('actual_div',0):.4f}  ·  "
                           f"Implied div: ${row.get('implied_div',0):.4f}  ·  "
                           f"Edge: ${row.get('edge',0):.4f}/sh  ·  "
                           f"Risk-free: {row.get('risk_free_rate',0):.2f}%")
                st.divider()

            if row.get("spread_type") != "conversion":
                st.markdown("#### Rationale")
                _comment = str(row.get("comment") or "—")
                _comment_lines = "\n\n".join(s.strip() for s in _comment.split(". ") if s.strip())
                st.success(_comment_lines)

            if isinstance(cum_pnl, (int, float)):
                st.caption(f"Cumulative P&L at exit: ${cum_pnl:+,.2f}")

        # Center dialog vertically via CSS
        st.markdown("""
<style>
div[data-testid="stDialog"] > div[role="dialog"] {
    margin-top: auto !important;
    margin-bottom: auto !important;
    top: 50% !important;
    transform: translateY(-50%) !important;
    position: fixed !important;
}
</style>""", unsafe_allow_html=True)

        # ── Tabulator master-detail via CDN ──────────────────────────────────
        import json as _json

        def _detail_rows_for(row):
            if slug == "conversion_arb":
                n = int(row.get("contracts", 1)); sh = n * 100
                def _f(v): return round(float(v or 0), 4)
                return [
                    {"leg": f"① Stock ({sh:,} sh)", "side": "Buy",
                     "entry": _f(row.get("entry_price")), "exit": _f(row.get("exit_price")),
                     "pnl":  round(float(row.get("stock_pnl",   0) or 0), 2)},
                    {"leg": f"② Put ({n} cts)",     "side": "Buy",
                     "entry": _f(row.get("put_entry_px")), "exit": _f(row.get("put_exit_px")),
                     "pnl":  round(float(row.get("put_pnl",     0) or 0), 2)},
                    {"leg": f"③ Call ({n} cts)",    "side": "Sell",
                     "entry": _f(row.get("call_entry_px")), "exit": _f(row.get("call_exit_px")),
                     "pnl":  round(float(row.get("call_pnl",    0) or 0), 2)},
                    {"leg": "Dividend",    "side": "—", "entry": None, "exit": None,
                     "pnl":  round(float(row.get("div_received", 0) or 0), 2)},
                    {"leg": "Carry",       "side": "—", "entry": None, "exit": None,
                     "pnl": -round(float(row.get("carry_cost",   0) or 0), 2)},
                    {"leg": "Commissions", "side": "—", "entry": None, "exit": None,
                     "pnl": -round(float(row.get("commissions",  0) or 0), 2)},
                ]
            elif slug == "dividend_arb":
                n = int(row.get("contracts", 1)); sh = n * 100
                def _f(v): return round(float(v or 0), 4)
                _put_total = float(row.get("put_cost", 0) or 0)
                _put_prem  = _put_total / max(sh, 1)
                return [
                    {"leg": f"① Stock ({sh:,} sh)", "side": "Buy",
                     "entry": _f(row.get("entry_cost")), "exit": _f(row.get("exit_value")),
                     "pnl":  round(float(row.get("equity_pnl", 0) or 0), 2)},
                    {"leg": f"② Put hedge ({n} cts)", "side": "Buy",
                     "entry": round(_put_prem, 4), "exit": None,
                     "pnl": -round(_put_total, 2)},
                    {"leg": "Dividend", "side": "—", "entry": None, "exit": None,
                     "pnl":  round(float(row.get("div_income", 0) or 0), 2)},
                ]
            elif slug == "vol_arbitrage":
                n = int(row.get("contracts", 1))
                def _fv(v): return round(float(v), 4) if v is not None and v == v else None
                tt  = str(row.get("trade_type", ""))
                cpe = _fv(row.get("call_price_entry")); ppe = _fv(row.get("put_price_entry"))
                cex = _fv(row.get("call_price_exit"));  pex = _fv(row.get("put_price_exit"))
                cpnl = round(float(row.get("call_pnl", 0) or 0), 2)
                ppnl = round(float(row.get("put_pnl",  0) or 0), 2)
                if tt == "skew_arb":
                    rows = [
                        {"leg": f"① Short Put  ({n} cts)", "side": "Sell",
                         "entry": ppe, "exit": pex, "pnl": ppnl},
                        {"leg": f"② Long Call  ({n} cts)", "side": "Buy",
                         "entry": cpe, "exit": cex, "pnl": cpnl},
                    ]
                    if row.get("hedge_puts") and float(row.get("hedge_puts", 0)) > 0:
                        rows.append({"leg": "③ Delta Hedge", "side": "—", "entry": None, "exit": None,
                                     "pnl": round(float(row.get("hedge_pnl", 0) or 0), 2)})
                    if row.get("commission"):
                        rows.append({"leg": "Commission", "side": "—", "entry": None, "exit": None,
                                     "pnl": -round(float(row.get("commission", 0) or 0), 2)})
                    return rows
                elif tt == "conversion":
                    return [
                        {"leg": f"① Long Call  ({n} cts)", "side": "Buy",  "entry": cpe, "exit": cex, "pnl": cpnl},
                        {"leg": f"② Short Put  ({n} cts)", "side": "Sell", "entry": ppe, "exit": pex, "pnl": ppnl},
                    ]
                else:  # reversal
                    return [
                        {"leg": f"① Short Call ({n} cts)", "side": "Sell", "entry": cpe, "exit": cex, "pnl": cpnl},
                        {"leg": f"② Long Put   ({n} cts)", "side": "Buy",  "entry": ppe, "exit": pex, "pnl": ppnl},
                    ]
            else:
                # Generic: show any numeric P&L component fields present in the row
                _known_pnl_fields = [
                    ("Put P&L",    "put_pnl"),    ("Call P&L",   "call_pnl"),
                    ("Hedge P&L",  "hedge_pnl"),  ("Stock P&L",  "stock_pnl"),
                    ("Dividend",   "div_income"),  ("Carry",     "carry_cost"),
                    ("Commission", "commission"),  ("Commission", "commissions"),
                ]
                seen = set()
                out = []
                for k, v in _known_pnl_fields:
                    if v in seen or row.get(v) is None: continue
                    seen.add(v)
                    mult = -1 if v in ("carry_cost","commission","commissions") else 1
                    out.append({"leg": k, "side": "—", "entry": None, "exit": None,
                                "pnl": round(mult * float(row.get(v) or 0), 2)})
                return out

        # ── Pure HTML <details>/<summary> — no JS library, browser handles expand ──
        _col_labels = {
            "W/L":"W/L","entry_date":"Entry","exit_date":"Exit",
            "strike":"Strike","contracts":"Cts","dte":"DTE",
            "actual_div":"Actual Div","implied_div":"Impl Div","edge":"Edge $",
            "total_in":"Invested","pnl":"P&L","return_pct":"Ret%","cum_pnl":"Cum P&L",
            "spread_type":"Type","trade_type":"Type","entry_cost":"Cost",
            "exit_reason":"Exit","iv_call":"Call IV","iv_put":"Put IV",
        }
        _visible = [c for c in show_cols if c in disp.columns]

        def _fmt(col, val):
            if val is None or (isinstance(val, float) and np.isnan(val)):
                return "—"
            if col == "W/L":
                c = "#22c55e" if val == "W" else "#ef4444"
                return f'<span style="color:{c};font-weight:700">{val}</span>'
            if col in ("pnl", "cum_pnl"):
                v = float(val)
                c = "#22c55e" if v >= 0 else "#ef4444"
                return f'<span style="color:{c};font-weight:600">${v:+,.2f}</span>'
            if col == "return_pct":
                return f"{float(val):.2%}"
            if col in ("actual_div","implied_div","edge"):
                return f"${float(val):.4f}"
            if col == "total_in":
                return f"${float(val):,.0f}"
            if col == "strike":
                return f"${float(val):.2f}"
            return str(val)

        CB = "#2d3748"; CH = "#1a2035"; BG0 = "#0f1623"; BG1 = "#141c2e"; DET = "#0a1120"
        BORD = "1px solid #2d3748"

        def _pc(v):   # P&L colored
            c = "#22c55e" if float(v or 0) >= 0 else "#ef4444"
            return f'<span style="color:{c};font-weight:600;font-family:monospace">${float(v or 0):+,.2f}</span>'

        def _badge(label, val, color="#9ca3af"):
            return (f'<span style="display:inline-flex;flex-direction:column;margin-right:20px;margin-bottom:4px;">'
                    f'<span style="font-size:10px;color:#6b7280;text-transform:uppercase;letter-spacing:.06em;margin-bottom:2px">{label}</span>'
                    f'<span style="color:{color};font-size:13px;font-weight:600;font-family:monospace">{val}</span></span>')

        def _leg_row(d):
            muted = d.get("side") == "—"
            tc = "#6b7280" if muted else "#d1d5db"
            pv = float(d.get("pnl") or 0)
            pc = "#22c55e" if pv >= 0 else "#ef4444"
            ent = f'${float(d["entry"]):.4f}' if d.get("entry") is not None else "—"
            ext = f'${float(d["exit"]):.4f}'  if d.get("exit")  is not None else "—"
            return (f'<tr style="border-bottom:{BORD};">'
                    f'<td style="padding:6px 14px;color:{tc}">{d["leg"]}</td>'
                    f'<td style="padding:6px 14px;color:{tc}">{d.get("side","")}</td>'
                    f'<td style="padding:6px 14px;color:{tc};font-family:monospace">{ent}</td>'
                    f'<td style="padding:6px 14px;color:{tc};font-family:monospace">{ext}</td>'
                    f'<td style="padding:6px 14px;color:{pc};font-weight:600;font-family:monospace">${pv:+,.2f}</td></tr>')

        def _build_detail(tr):
            det  = _detail_rows_for(tr)
            legs = [d for d in det if d.get("side") not in ("—",)]
            attr = [d for d in det if d.get("side") == "—"]
            if slug == "vol_arbitrage":
                extras = []
                if tr.get("put_pnl")  is not None: extras.append({"leg": "Short Put", "side": "—", "pnl": round(float(tr.get("put_pnl")  or 0), 2)})
                if tr.get("call_pnl") is not None: extras.append({"leg": "Long Call",  "side": "—", "pnl": round(float(tr.get("call_pnl") or 0), 2)})
                attr = extras + attr

            html = f'<td colspan="99" style="padding:0;"><div style="background:{DET};padding:14px 20px 16px;border-top:{BORD};font-family:sans-serif;">'

            # Arb Setup
            if slug in ("conversion_arb", "dividend_arb", "vol_arbitrage"):
                _n_ct = int(tr.get("contracts", 1)); _n_sh = _n_ct * 100
                html += '<div style="display:flex;flex-wrap:wrap;gap:16px 0;margin-bottom:14px;padding-bottom:12px;border-bottom:1px solid #1e293b;">'
                html += '<div style="width:100%;font-size:10px;color:#4b5563;text-transform:uppercase;letter-spacing:.1em;margin-bottom:4px;font-weight:600">Arbitrage Setup</div>'
                if slug == "vol_arbitrage":
                    _tt   = str(tr.get("trade_type", "—"))
                    _tt_label = {"skew_arb": "Skew Arb (risk-reversal)", "conversion": "Conversion", "reversal": "Reversal"}.get(_tt, _tt)
                    _ivc  = tr.get("iv_call");  _ivp = tr.get("iv_put");  _ivsk = tr.get("iv_skew")
                    _viol = tr.get("violation"); _exp = tr.get("expected_pnl"); _sig = tr.get("signal_strength")
                    _spot = tr.get("spot");      _dte = tr.get("dte");         _cost = tr.get("cost")
                    _cpe  = tr.get("call_price_entry"); _ppe = tr.get("put_price_entry")
                    html += _badge("Type",         _tt_label, "#a5b4fc")
                    if _spot: html += _badge("Spot at entry", f"${float(_spot):.2f}", "#e2e8f0")
                    if _dte:  html += _badge("DTE",           f"{int(_dte)}d", "#e2e8f0")
                    if _ivc:  html += _badge("IV Call",       f"{float(_ivc):.1f}%", "#e2e8f0")
                    if _ivp:  html += _badge("IV Put",        f"{float(_ivp):.1f}%", "#e2e8f0")
                    if _ivsk:
                        _sc2 = "#f87171" if float(_ivsk) > 0 else "#4ade80"
                        html += _badge("IV Skew (put−call)", f"{float(_ivsk):+.1f} pts", _sc2)
                    if _viol:
                        _vc = "#4ade80" if float(_viol) > 0 else "#f87171"
                        html += _badge("Parity violation", f"${float(_viol):.4f}", _vc)
                    if _exp:  html += _badge("Expected P&L", f"${float(_exp):+,.2f}", "#4ade80")
                    if _sig:  html += _badge("Signal strength", f"{float(_sig):.3f}", "#e2e8f0")
                    if _cpe:  html += _badge("Call entry px", f"${float(_cpe):.4f}", "#e2e8f0")
                    if _ppe:  html += _badge("Put entry px",  f"${float(_ppe):.4f}", "#e2e8f0")
                    if _cost: html += _badge("Net cost",      f"${float(_cost):,.2f}", "#e2e8f0")
                elif slug == "conversion_arb":
                    adiv = tr.get("actual_div"); idiv = tr.get("implied_div"); edge = tr.get("edge")
                    rfr  = tr.get("risk_free_rate"); dte = tr.get("dte")
                    inv  = tr.get("total_in") or (float(tr.get("entry_cost", 0)) * _n_sh)
                    if adiv: html += _badge("Actual div",  f"${float(adiv):.4f}/sh", "#e2e8f0")
                    if idiv: html += _badge("Implied div", f"${float(idiv):.4f}/sh", "#e2e8f0")
                    if edge:
                        ec = "#4ade80" if float(edge) > 0 else "#f87171"
                        html += _badge("Edge", f"${float(edge):.4f}/sh", ec)
                    if rfr: html += _badge("Risk-free", f"{float(rfr):.2f}%", "#e2e8f0")
                    if dte: html += _badge("DTE", f"{int(dte)}d", "#e2e8f0")
                    if inv: html += _badge("Invested", f"${float(inv):,.0f}", "#e2e8f0")
                else:
                    _div_total  = float(tr.get("div_income", 0) or 0)
                    _div_per_sh = _div_total / max(_n_sh, 1)
                    _entry_px   = float(tr.get("entry_cost", 0) or 0)
                    _put_total  = float(tr.get("put_cost", 0) or 0)
                    html += _badge("Div/share",  f"${_div_per_sh:.4f}", "#e2e8f0")
                    html += _badge("Total div",  f"${_div_total:,.2f}", "#e2e8f0")
                    html += _badge("Put cost",   f"${_put_total:,.2f}", "#e2e8f0")
                    html += _badge("Invested",   f"${_entry_px * _n_sh:,.0f}", "#e2e8f0")
                    html += _badge("Size",       f"{_n_ct} cts · {_n_sh:,} sh", "#e2e8f0")
                html += '</div>'

            # Trade Legs
            if legs:
                html += '<div style="margin-bottom:14px;">'
                html += '<div style="font-size:10px;color:#4b5563;text-transform:uppercase;letter-spacing:.1em;font-weight:600;margin-bottom:6px">Trade Legs</div>'
                html += '<table style="width:100%;border-collapse:collapse;font-size:12.5px;">'
                html += (f'<tr style="background:#111827;border-bottom:2px solid #374151;">'
                         f'<th style="padding:5px 14px;text-align:left;color:#6b7280;font-weight:500;font-size:11px;text-transform:uppercase;letter-spacing:.05em">Leg</th>'
                         f'<th style="padding:5px 14px;text-align:left;color:#6b7280;font-weight:500;font-size:11px;text-transform:uppercase;letter-spacing:.05em">Side</th>'
                         f'<th style="padding:5px 14px;text-align:right;color:#6b7280;font-weight:500;font-size:11px;text-transform:uppercase;letter-spacing:.05em">Entry px</th>'
                         f'<th style="padding:5px 14px;text-align:right;color:#6b7280;font-weight:500;font-size:11px;text-transform:uppercase;letter-spacing:.05em">Exit px</th>'
                         f'<th style="padding:5px 14px;text-align:right;color:#6b7280;font-weight:500;font-size:11px;text-transform:uppercase;letter-spacing:.05em">P&L</th></tr>')
                for d in legs:
                    html += _leg_row(d)
                html += '</table></div>'

            # P&L Attribution
            if attr:
                pnl_total = float(tr.get("pnl") or 0)
                ptc = "#4ade80" if pnl_total >= 0 else "#f87171"
                html += (f'<div style="display:flex;flex-wrap:wrap;align-items:center;gap:6px 0;'
                         f'padding-top:10px;border-top:1px solid #1e293b;">'
                         f'<div style="width:100%;font-size:10px;color:#4b5563;text-transform:uppercase;'
                         f'letter-spacing:.1em;font-weight:600;margin-bottom:4px">P&L Attribution</div>')
                for d in attr:
                    pv = float(d.get("pnl") or 0)
                    pc = "#4ade80" if pv >= 0 else "#f87171"
                    html += (f'<span style="margin-right:24px;white-space:nowrap;">'
                             f'<span style="color:#6b7280;font-size:12px">{d["leg"]} </span>'
                             f'<span style="color:{pc};font-weight:600;font-family:monospace">${pv:+,.2f}</span></span>')
                html += (f'<span style="margin-left:auto;padding:4px 12px;background:#111827;'
                         f'border-radius:4px;border:1px solid #374151;white-space:nowrap;">'
                         f'<span style="color:#9ca3af;font-size:12px">Net P&L </span>'
                         f'<span style="color:{ptc};font-weight:700;font-size:14px;font-family:monospace">${pnl_total:+,.2f}</span></span>')
                html += '</div>'

            html += '</div>'
            return html

        # ── CSS Grid <details> — same grid-template-columns = perfect alignment ─
        _sum_cols = [c for c in ["entry_date","exit_date","strike","contracts","dte","edge","pnl","return_pct","cum_pnl"] if c in disp.columns]
        _sum_labels = {"entry_date":"Entry","exit_date":"Exit","strike":"Strike","contracts":"Cts","dte":"DTE","edge":"Edge $/sh","pnl":"P&L","return_pct":"Return %","cum_pnl":"Cum P&L"}
        _col_w = {"entry_date":"120px","exit_date":"120px","strike":"80px","contracts":"55px","dte":"55px","edge":"100px","pnl":"115px","return_pct":"95px","cum_pnl":"115px"}
        _grid = "36px " + " ".join(_col_w.get(c,"100px") for c in _sum_cols)

        def _sc(col, val):
            if val is None or (isinstance(val, float) and np.isnan(val)): return "—"
            if col in ("pnl","cum_pnl"): return _pc(val)
            if col == "return_pct":
                v = float(val); c = "#4ade80" if v >= 0 else "#f87171"
                return f'<span style="color:{c};font-weight:600">{v:+.2f}%</span>'
            if col == "edge":
                v = float(val); c = "#4ade80" if v > 0 else "#f87171"
                return f'<span style="color:{c};font-weight:600;font-family:monospace">${v:.4f}</span>'
            if col == "strike": return f"${float(val):.2f}"
            return str(val)

        _hdr_cells = (
            f'<div style="display:grid;grid-template-columns:{_grid};background:{CH};'
            f'border-bottom:2px solid #374151;font-family:sans-serif;">'
            f'<div style="padding:8px 10px;"></div>'
            + "".join(
                f'<div style="padding:8px 14px;font-size:11px;color:#6b7280;font-weight:600;'
                f'text-transform:uppercase;letter-spacing:.07em;border-left:{BORD};white-space:nowrap;">'
                f'{_sum_labels.get(c,c)}</div>'
                for c in _sum_cols
            ) + '</div>'
        )

        _row_groups = []
        for _i, (_, _tr) in enumerate(disp.iterrows()):
            _bg  = BG0 if _i % 2 == 0 else BG1
            _det = _build_detail(_tr)
            _cells = "".join(
                f'<div style="padding:9px 14px;font-size:13px;color:#e2e8f0;'
                f'border-left:{BORD};white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">'
                f'{_sc(c, _tr.get(c))}</div>'
                for c in _sum_cols
            )
            _row_groups.append(
                f'<details style="border-top:{BORD};">'
                f'<summary style="display:grid;grid-template-columns:{_grid};list-style:none;'
                f'cursor:pointer;background:{_bg};align-items:center;" '
                f'onmouseover="this.style.background=\'#1a2840\'" onmouseout="this.style.background=\'{_bg}\'">'
                f'<div style="padding:9px 10px;text-align:center;">'
                f'<span style="font-size:10px;color:#6b7280;display:inline-block;'
                f'transition:transform .2s;">&#9654;</span></div>'
                f'{_cells}</summary>'
                f'<div style="background:{DET};border-top:{BORD};">{_det}</div>'
                f'</details>'
            )

        _html = (
            f'<style>details[open]>summary>div>span{{transform:rotate(90deg);}}'
            f'details>summary::-webkit-details-marker{{display:none;}}</style>'
            f'<div style="border:{BORD};border-radius:6px;overflow:hidden;font-family:sans-serif;">'
            f'{_hdr_cells}{"".join(_row_groups)}</div>'
        )
        st.markdown(_html, unsafe_allow_html=True)

    st.markdown("---")

    eq = res.equity_curve.copy()
    eq.index = pd.to_datetime(eq.index)
    starting_cap = float(res.equity_curve.iloc[0]) if not res.equity_curve.empty else 10_000
    eq_df = pd.DataFrame({"equity": eq, "price": eq * 0 + starting_cap})

    with st.expander("Equity Curve & Drawdown", expanded=True):
        st.plotly_chart(C.equity_curve(eq_df),   width="stretch", key=f"bt_{slug}_eq")
        st.plotly_chart(C.drawdown_chart(eq_df), width="stretch", key=f"bt_{slug}_dd")
        if len(eq_df) > 65:
            st.plotly_chart(C.rolling_sharpe(eq_df), width="stretch", key=f"bt_{slug}_rs")

    if not trades.empty:
        with st.expander("Trade Analysis", expanded=False):
            if "pnl" in trades.columns and "exit_date" in trades.columns:
                _cum_df = trades[["exit_date", "pnl"]].rename(columns={"exit_date": "date"}).copy()
                _cum_df["date"] = pd.to_datetime(_cum_df["date"])
                st.plotly_chart(C.cumulative_pnl_line(_cum_df), width="stretch", key=f"bt_{slug}_cum_pnl")
            tr1, tr2 = st.columns(2)
            with tr1: st.plotly_chart(C.win_loss_pie(trades),    width="stretch", key=f"bt_{slug}_wl")
            with tr2: st.plotly_chart(C.exit_reason_pie(trades), width="stretch", key=f"bt_{slug}_er")
            st.plotly_chart(C.trade_pnl_scatter(trades),  width="stretch", key=f"bt_{slug}_pnl_sc")
            st.plotly_chart(C.pnl_histogram(trades),      width="stretch", key=f"bt_{slug}_pnl_hist")
            if len(eq_df) > 30:
                st.plotly_chart(C.monthly_returns_heatmap(eq_df), width="stretch", key=f"bt_{slug}_mr")

    # ── Walk-Forward Analysis (vol_arbitrage only) ────────────────────────
    if slug == "vol_arbitrage":
        st.markdown("---")
        with st.expander("Walk-Forward Analysis", expanded=False):
            st.caption(
                "Runs the same fixed parameters on non-overlapping 2-month windows. "
                "Tests whether the edge holds across different market regimes — not curve fitting."
            )
            _wf_key = f"wf_results_{slug}"
            _wf_months_key = f"wf_months_{slug}"
            _wf_cols = st.columns([1, 3])
            _wf_test_months = _wf_cols[0].selectbox(
                "Window size", [1, 2, 3], index=1,
                format_func=lambda x: f"{x} month{'s' if x > 1 else ''}",
                key=_wf_months_key,
            )
            if _wf_cols[1].button("▶ Run Walk-Forward", key=f"btn_wf_{slug}"):
                with st.spinner("Running walk-forward…"):
                    try:
                        from alan_trader.strategies.vol_arbitrage import VolArbitrageStrategy as _WFStrat
                        _wf_strat = _WFStrat()
                        _wf_price = res.extra.get("spy_returns")  # reuse loaded data

                        # Re-load price + chains from session (already loaded for main backtest)
                        # We need the raw price_data (not returns) — reload from DB
                        from alan_trader.db.loader import load_training_data as _wf_ltd
                        _wf_data   = _wf_ltd(ticker=ticker or "SPY")
                        _wf_spy_df = _wf_data["spy"]

                        # Reuse aux (vix, rate, chains) built during _do_backtest
                        # The chains are not in res.extra — need to rebuild aux from DB
                        from alan_trader.db.options_loader import _load_chain as _wf_lc
                        from alan_trader.db.client import get_engine as _wf_ge, get_ticker_id as _wf_gtid
                        from alan_trader.db.sync import bs_price_chain as _wf_bspc
                        from alan_trader.db.client import get_price_bars as _wf_gpb
                        _wf_eng  = _wf_ge()
                        _wf_tid  = _wf_gtid(_wf_eng, ticker or "SPY")
                        _wf_from = (datetime.date.today() - datetime.timedelta(days=730))
                        _wf_raw  = _wf_lc(_wf_eng, _wf_tid, _wf_from, datetime.date.today(), min_dte=7, max_dte=60) if _wf_tid else pd.DataFrame()

                        _wf_chains = {}
                        if not _wf_raw.empty:
                            _wf_raw["dte"] = (_wf_raw["expiration_date"] - _wf_raw["snapshot_date"]).apply(
                                lambda td: td.days if hasattr(td, "days") else int(td)
                            )
                            _wf_raw = _wf_raw.rename(columns={"contract_type": "type"})
                            _wf_raw["type"] = _wf_raw["type"].str.lower().map(
                                {"c": "call", "call": "call", "p": "put", "put": "put"}
                            )
                            _wf_spots_df = _wf_gpb(_wf_eng, ticker or "SPY", _wf_from, datetime.date.today())
                            _wf_spot_map = {}
                            if not _wf_spots_df.empty:
                                for _, _wf_sr in _wf_spots_df.iterrows():
                                    _sd = _wf_sr["date"].date() if hasattr(_wf_sr["date"], "date") else _wf_sr["date"]
                                    _wf_spot_map[_sd] = float(_wf_sr["close"])
                            for _snap_dt, _grp in _wf_raw.groupby("snapshot_date"):
                                import datetime as _dt2
                                _k = _snap_dt if isinstance(_snap_dt, _dt2.date) else pd.Timestamp(_snap_dt).date()
                                _ch = _grp[["strike", "type", "bid", "ask", "iv", "delta", "dte"]].reset_index(drop=True)
                                _S2 = _wf_spot_map.get(_k)
                                if _S2:
                                    _ch = _wf_bspc(_ch, _S2)
                                _wf_chains[_k] = _ch

                        _wf_aux = {
                            "vix":               _wf_data["vix"],
                            "rate10y":           _wf_data["rate10y"],
                            "options_chains":    _wf_chains,
                            "option_data_quality": (res.extra or {}).get("data_quality", "unknown"),
                        }

                        _wf_result = _wf_strat.walk_forward(
                            _wf_spy_df, _wf_aux,
                            test_months=_wf_test_months,
                            starting_capital=100_000,
                            skip_parity_arb=True,
                            **params,
                        )
                        st.session_state[_wf_key] = _wf_result
                        st.rerun()
                    except Exception as _wf_ex:
                        import traceback
                        st.error(f"Walk-forward failed: {_wf_ex}")
                        st.code(traceback.format_exc())

            _wf_res = st.session_state.get(_wf_key)
            if _wf_res and _wf_res.get("windows"):
                _wf_summary = _wf_res["summary"]
                _wf_windows = _wf_res["windows"]
                _wf_eq      = _wf_res["equity"]

                # Summary metrics
                _ws1, _ws2, _ws3, _ws4, _ws5 = st.columns(5)
                _ws1.metric("Windows",        f"{_wf_summary['n_windows']}")
                _ws2.metric("Profitable",     f"{_wf_summary['profitable_windows']}/{_wf_summary['n_windows']} ({_wf_summary['consistency_pct']:.0f}%)")
                _ws3.metric("Avg Return/Wdw", f"{_wf_summary['avg_return_pct']:+.1f}%")
                _ws4.metric("Avg Sharpe",     f"{_wf_summary['avg_sharpe']:.2f}")
                _ws5.metric("Worst Window",   f"{_wf_summary['worst_window_return']:+.1f}%")

                # Per-window table
                _wf_rows = []
                for _w in _wf_windows:
                    _pf = _w["profit_factor"]
                    _pf_str = f"{_pf:.2f}" if _pf != float("inf") else "∞"
                    _ret = _w["total_return"]
                    _wf_rows.append({
                        "":               "🟢" if _ret > 0 else ("🔴" if _ret < 0 else "⚪"),
                        "Period":         _w["period"],
                        "Trades":         _w["trades"],
                        "Win Rate":       f"{_w['win_rate']:.0f}%",
                        "Return":         f"{_ret:+.1f}%",
                        "Sharpe":         f"{_w['sharpe']:.2f}",
                        "Max DD":         f"{_w['max_dd']:.1f}%",
                        "Profit Factor":  _pf_str,
                    })
                _wf_df = pd.DataFrame(_wf_rows)
                st.dataframe(_wf_df, hide_index=True, width="stretch")

                # Combined equity curve
                if not _wf_eq.empty:
                    from alan_trader.visualization import charts as _C2
                    _wf_start = float(_wf_eq.iloc[0])
                    _wf_eq_df = pd.DataFrame({"equity": _wf_eq, "price": _wf_start})
                    st.plotly_chart(_C2.equity_curve(_wf_eq_df), width="stretch", key=f"wf_{slug}_eq")

                st.caption(
                    f"**Interpretation:** {_wf_summary['consistency_pct']:.0f}% of windows profitable. "
                    "If consistency ≥ 60% and avg Sharpe > 0, the edge is regime-independent. "
                    "Low consistency means the strategy only worked in specific market conditions."
                )

    # ── Rates/SPY Rotation — regime chart (both variants) ─────────────────
    if slug in ("rates_spy_rotation", "rates_spy_rotation_options") and res.extra:
        _render_regime_chart(slug, res)



def _render_live(slug: str):
    """Live Monitor sub-tab."""
    from alan_trader.visualization import charts as C
    meta    = _meta(slug)
    uses_ml = meta.get("uses_ml", False)

    st.subheader(f"Live Monitor — {meta['display_name']}")

    # ── Strategy applicability banner ─────────────────────────────────────
    if uses_ml:
        from alan_trader.data.features import SPREAD_TYPE_OPTIONS as _STO3
        train_res = st.session_state["train_results"].get(slug)
        bt_res    = st.session_state["bt_results"].get(slug)
        if train_res is not None:
            stype     = train_res.get("spread_type", "bull_call")
            n_winners = train_res.get("n_confirmed", 0)
            stype_label = _STO3.get(stype, stype).split("(")[0].strip()
            win_rate = bt_res.metrics.get("win_rate_pct", 0) if bt_res else None
            if n_winners >= 10:
                status_color, status_icon, status_text = "#26a69a", "✅", "APPLICABLE"
                status_detail = (f"Training found **{n_winners} confirmed ENTER signals** for "
                                 f"**{stype_label}**. "
                                 + (f"Backtest win rate: **{win_rate:.1f}%**." if win_rate else "Run a backtest to see P&L."))
            elif n_winners > 0:
                status_color, status_icon, status_text = "#ffa726", "⚠️", "MARGINAL"
                status_detail = (f"Only **{n_winners} confirmed ENTER signals** for **{stype_label}**. "
                                 "Consider more training epochs or a different spread type.")
            else:
                status_color, status_icon, status_text = "#ef5350", "❌", "NOT RECOMMENDED"
                status_detail = (f"No confirmed ENTER signals for **{stype_label}** in training. "
                                 "Model is not finding a mispricing edge. Try a different spread type.")
            st.markdown(
                f"""<div style="display:flex;gap:16px;align-items:center;padding:12px 16px;
                        background:#161b27;border-left:4px solid {status_color};
                        border-radius:6px;margin-bottom:16px">
                  <div style="font-size:1.8rem">{status_icon}</div>
                  <div>
                    <div style="color:{status_color};font-size:1.1rem;font-weight:700">
                      Strategy {status_text}</div>
                    <div style="color:#b0b8c8;margin-top:4px">{status_detail}</div>
                  </div>
                </div>""", unsafe_allow_html=True,
            )
        else:
            st.info("Train the model first (🧠 Train tab) to see whether this strategy is applicable.")

    if uses_ml:
        # Full live simulation for ML strategies
        n_signals = st.slider("Signals to show", 10, 120, 60, key=f"live_{slug}_n")
        from alan_trader.data.simulator import simulate_live_state
        signals_df = simulate_live_state(n_signals=n_signals)

        latest    = signals_df.iloc[-1]
        proba     = [latest["proba_bear"], latest["proba_neutral"], latest["proba_bull"]]
        signal    = latest["signal"]
        sig_color = {"BULL": "#26a69a", "BEAR": "#ef5350", "NEUTRAL": "#78909c"}[signal]
        sig_icon  = {"BULL": "📈", "BEAR": "📉", "NEUTRAL": "⚖️"}[signal]

        st.markdown(
            f"""<div style="display:flex;gap:24px;align-items:center;padding:16px;
                    background:#161b27;border-radius:10px;margin-bottom:16px">
              <div style="font-size:2.4rem">{sig_icon}</div>
              <div>
                <div style="color:{sig_color};font-size:1.6rem;font-weight:700">{signal}</div>
                <div style="color:#b0b8c8">Confidence: {latest['confidence']:.1%} &nbsp;|&nbsp;
                     Price: ${latest['price']:.2f} &nbsp;|&nbsp;
                     Spread: {latest['spread_type'].upper() if latest['spread_type'] != 'skip' else '—'}</div>
              </div>
              <div style="margin-left:auto;text-align:right">
                <div style="color:#e0e0e0">Portfolio</div>
                <div style="color:#5c6bc0;font-size:1.8rem;font-weight:700">
                     ${latest['portfolio_value']:,.0f}</div>
              </div>
            </div>""", unsafe_allow_html=True,
        )

        g1, g2 = st.columns([1, 1])
        with g1: st.plotly_chart(C.signal_gauge(proba),  width="stretch", key=f"live_{slug}_gauge")
        with g2: st.plotly_chart(C.proba_bar(proba),     width="stretch", key=f"live_{slug}_proba")
        st.markdown("---")
        st.plotly_chart(C.live_portfolio_line(signals_df),  width="stretch", key=f"live_{slug}_port")
        p1, p2 = st.columns(2)
        with p1: st.plotly_chart(C.cumulative_pnl_line(signals_df), width="stretch", key=f"live_{slug}_cpnl")
        with p2: st.plotly_chart(C.live_pnl_bars(signals_df),       width="stretch", key=f"live_{slug}_pnlb")
        st.markdown("---")
        st.plotly_chart(C.signal_timeline(signals_df),              width="stretch", key=f"live_{slug}_tl")
        sa1, sa2 = st.columns(2)
        with sa1: st.plotly_chart(C.vix_vs_confidence_scatter(signals_df), width="stretch", key=f"live_{slug}_vix")
        with sa2: st.plotly_chart(C.spread_type_pie(signals_df),           width="stretch", key=f"live_{slug}_pie")

        # ── Selected trades (non-neutral, actionable signals) ────────────
        st.markdown("---")
        selected_trades = signals_df[
            (signals_df["signal"] != "NEUTRAL") &
            (signals_df["spread_type"] != "skip")
        ].copy()

        st.subheader(f"Selected Trades — {len(selected_trades)} actionable signals")
        if not selected_trades.empty:
            trade_cols = [c for c in ["date", "signal", "spread_type", "confidence",
                                       "price", "pnl"]
                          if c in selected_trades.columns]
            col_cfg = {
                "confidence": st.column_config.ProgressColumn("Win Prob", min_value=0, max_value=1, format="%.3f"),
            }
            if "pnl" in trade_cols:
                col_cfg["pnl"] = st.column_config.NumberColumn("P&L ($)", format="$%.2f")
            st.dataframe(
                selected_trades[trade_cols].sort_values("date", ascending=False),
                width="stretch", column_config=col_cfg, hide_index=True,
            )
        else:
            st.info("No actionable signals in this window.")

        st.markdown("---")
        st.subheader("All Recent Signals")
        display = (signals_df[["date", "signal", "spread_type", "confidence",
                                "price", "pnl", "portfolio_value"]]
                   .tail(20).sort_values("date", ascending=False))
        st.dataframe(
            display.style.map(
                lambda v: ("color:#26a69a" if isinstance(v, (int, float)) and v > 0
                           else "color:#ef5350" if isinstance(v, (int, float)) and v < 0
                           else ""),
                subset=["pnl"],
            ),
            width="stretch",
        )

        with st.expander("Auto-refresh"):
            if st.toggle("Refresh every 60 s", value=False, key=f"live_{slug}_refresh"):
                import time; time.sleep(60); st.rerun()

    else:
        # Simplified view for rule-based strategies
        res = st.session_state["bt_results"].get(slug)
        if res is None:
            st.info("Run a **Backtest** for this strategy first to see live monitoring.")
            return

        eq  = res.equity_curve
        m   = res.metrics
        trades = res.trades if isinstance(res.trades, pd.DataFrame) else pd.DataFrame()

        # Latest signal from last trade
        last_signal = "—"
        last_conf   = "—"
        if not trades.empty and "exit_reason" in trades.columns:
            last_t = trades.iloc[-1]
            last_signal = last_t.get("spread_type", "—") if "spread_type" in last_t else "—"

        st.markdown(
            f"""<div style="background:#161b27;padding:16px;border-radius:10px;margin-bottom:16px">
              <div style="color:#e0e0e0;font-size:1.1rem;font-weight:600">
                {meta['display_name']} — Rule-Based Strategy
              </div>
              <div style="color:#b0b8c8;margin-top:8px">
                Signals are generated deterministically from market conditions — no model training required.
              </div>
            </div>""", unsafe_allow_html=True,
        )

        mc1, mc2, mc3, mc4 = st.columns(4)
        mc1.metric("Total Return",  f"{m.get('total_return_pct', 0):+.1f}%")
        mc2.metric("Sharpe",        f"{m.get('sharpe', 0):.2f}")
        mc3.metric("Win Rate",      f"{m.get('win_rate_pct', 0):.1f}%")
        mc4.metric("Total Trades",  str(m.get("num_trades", len(trades))))

        if not trades.empty:
            st.markdown("---")
            st.subheader("Recent Trades")
            show_cols = [c for c in ["entry_date", "exit_date", "spread_type",
                                      "entry_cost", "pnl", "exit_reason"]
                         if c in trades.columns]
            st.dataframe(trades[show_cols].tail(20).sort_values(
                "entry_date", ascending=False
            ) if "entry_date" in show_cols else trades[show_cols].tail(20),
                width="stretch")


# ══════════════════════════════════════════════════════════════════════════════
# STRATEGY PERFORMANCE — last backtest + live P&L from portfolio tables
# ══════════════════════════════════════════════════════════════════════════════

def _render_strategy_performance(slug: str):
    import plotly.graph_objects as go
    import plotly.express as px
    import pandas as pd
    import streamlit.column_config as cc

    meta         = _meta(slug)
    display_name = meta["display_name"]
    bt_res       = st.session_state.get("bt_results", {}).get(slug)

    _DARK = dict(
        paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
        font=dict(color="#b0b8c8"),
        xaxis=dict(gridcolor="#1e2130"),
        yaxis=dict(gridcolor="#1e2130"),
        margin=dict(l=0, r=0, t=40, b=0),
    )

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 1 — LAST BACKTEST RESULTS
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown("### 📊 Last Backtest")

    if bt_res is None:
        st.info("No backtest run yet for this strategy. Go to **Backtest** tab and run one first.")
    else:
        m = bt_res.metrics if bt_res.metrics else {}
        trades_df = bt_res.trades if bt_res.trades is not None else pd.DataFrame()
        equity    = bt_res.equity_curve
        extra     = bt_res.extra or {}

        # ── Metrics rows ─────────────────────────────────────────────────────
        total_ret  = (equity.iloc[-1] / equity.iloc[0] - 1) * 100 if len(equity) > 1 else 0
        sharpe     = m.get("sharpe_ratio", m.get("sharpe", float("nan")))
        sortino    = m.get("sortino_ratio", m.get("sortino", float("nan")))
        max_dd     = m.get("max_drawdown", m.get("max_drawdown_pct", float("nan")))
        ann_ret    = m.get("cagr", m.get("annualized_return", float("nan")))
        n_trades   = len(trades_df)
        wins       = int((trades_df["pnl"] > 0).sum()) if "pnl" in trades_df.columns else 0
        losses     = int((trades_df["pnl"] < 0).sum()) if "pnl" in trades_df.columns else 0
        win_rate   = 100 * wins / (wins + losses) if (wins + losses) > 0 else 0
        total_pnl  = trades_df["pnl"].sum()  if "pnl" in trades_df.columns else 0
        avg_win    = trades_df.loc[trades_df["pnl"] > 0,  "pnl"].mean() if wins    > 0 else 0
        avg_loss   = trades_df.loc[trades_df["pnl"] <= 0, "pnl"].mean() if losses  > 0 else 0
        best_trade = trades_df["pnl"].max() if n_trades else 0
        worst_trade= trades_df["pnl"].min() if n_trades else 0
        profit_fac = m.get("profit_factor", abs(avg_win * wins / (avg_loss * losses))
                           if avg_loss != 0 and losses > 0 else float("nan"))
        avg_hold   = (
            (pd.to_datetime(trades_df["exit_date"]) - pd.to_datetime(trades_df["entry_date"]))
            .dt.days.mean()
            if "entry_date" in trades_df.columns and "exit_date" in trades_df.columns and n_trades > 0
            else float("nan")
        )

        r1c1, r1c2, r1c3, r1c4, r1c5, r1c6, r1c7, r1c8 = st.columns(8)
        r1c1.metric("Total Return",    f"{total_ret:+.1f}%")
        r1c2.metric("Total P&L",       f"${total_pnl:,.0f}")
        r1c3.metric("Ann. Return",     f"{ann_ret*100:+.1f}%" if ann_ret == ann_ret else "—")
        r1c4.metric("Sharpe",          f"{sharpe:.2f}"         if sharpe  == sharpe  else "—")
        r1c5.metric("Sortino",         f"{sortino:.2f}"        if sortino == sortino else "—")
        r1c6.metric("Max Drawdown",    f"{max_dd:.1f}%"        if max_dd  == max_dd  else "—")
        r1c7.metric("Win Rate",        f"{win_rate:.1f}%")
        r1c8.metric("Profit Factor",   f"{profit_fac:.2f}"     if profit_fac == profit_fac else "—")

        r2c1, r2c2, r2c3, r2c4, r2c5, r2c6 = st.columns(6)
        r2c1.metric("# Trades",        str(n_trades))
        r2c2.metric("Winners",         f"{wins} ({win_rate:.0f}%)")
        r2c3.metric("Losers",          str(losses))
        r2c4.metric("Avg Win",         f"${avg_win:,.2f}"   if avg_win  else "—")
        r2c5.metric("Avg Loss",        f"${avg_loss:,.2f}"  if avg_loss else "—")
        r2c6.metric("Avg Hold (days)", f"{avg_hold:.1f}"    if avg_hold == avg_hold else "—")

        # ── Equity curve ─────────────────────────────────────────────────────
        fig_eq = go.Figure()
        # SPY buy-and-hold benchmark
        spy_rets = extra.get("spy_returns")
        if spy_rets is not None:
            spy_eq = (1 + spy_rets.fillna(0)).cumprod() * equity.iloc[0]
            fig_eq.add_trace(go.Scatter(
                x=spy_eq.index, y=spy_eq.values,
                mode="lines", name="SPY B&H",
                line=dict(color="#546e7a", width=1, dash="dot"),
                hovertemplate="%{x|%Y-%m-%d}: $%{y:,.0f}<extra>SPY</extra>",
            ))
        fig_eq.add_trace(go.Scatter(
            x=equity.index, y=equity.values,
            mode="lines", name=display_name,
            line=dict(color="#5c6bc0", width=2),
            fill="tozeroy", fillcolor="rgba(92,107,192,0.08)",
            hovertemplate="%{x|%Y-%m-%d}: $%{y:,.0f}<extra></extra>",
        ))
        fig_eq.update_layout(title="Equity Curve", height=320,
                             legend=dict(orientation="h", y=1.1), **_DARK)
        st.plotly_chart(fig_eq, width="stretch")

        # ── Styler helpers (used by both regime and trade-type tables) ────────
        def _pnl_color(v):
            if not isinstance(v, (int, float)) or v != v: return ""
            return "color: #4caf50; font-weight:600" if v > 0 else ("color: #ef5350; font-weight:600" if v < 0 else "")
        def _wr_color(v):
            if not isinstance(v, (int, float)) or v != v: return ""
            return "color: #4caf50" if v >= 50 else "color: #ef5350"

        # ── Strategy-specific extras ──────────────────────────────────────────
        regime_series = extra.get("regime_series")
        spy_weights   = extra.get("spy_weights")

        if regime_series is not None and spy_weights is not None:
            st.markdown("#### Regime Breakdown")

            # Allocation over time
            fig_alloc = go.Figure()
            fig_alloc.add_trace(go.Scatter(
                x=spy_weights.index, y=(spy_weights * 100).values,
                mode="lines", fill="tozeroy",
                fillcolor="rgba(92,107,192,0.15)",
                line=dict(color="#5c6bc0", width=1.5),
                hovertemplate="%{x|%Y-%m-%d}: %{y:.0f}% SPY<extra></extra>",
                name="SPY Allocation %",
            ))
            fig_alloc.update_layout(
                title="SPY Allocation Over Time", height=220,
                yaxis=dict(gridcolor="#1e2130", title="% SPY", range=[0, 105]),
                xaxis=dict(gridcolor="#1e2130"),
                paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
                font=dict(color="#b0b8c8"),
                margin=dict(l=0, r=0, t=36, b=0),
            )
            st.plotly_chart(fig_alloc, width="stretch")

            # P&L by regime from trades
            if not trades_df.empty and "spread_type" in trades_df.columns:
                regime_grp = (
                    trades_df.groupby("spread_type")["pnl"]
                    .agg(total_pnl="sum", trades="count",
                         win_rate=lambda x: 100 * (x > 0).sum() / len(x),
                         avg_pnl="mean")
                    .reset_index()
                    .rename(columns={"spread_type": "Regime"})
                    .sort_values("total_pnl", ascending=False)
                )

                col_tbl, col_bar = st.columns([2, 3])
                with col_tbl:
                    _rdisp = regime_grp.rename(columns={
                        "total_pnl": "Total P&L", "win_rate": "Win %",
                        "avg_pnl": "Avg P&L", "trades": "# Trades",
                    })
                    _rstyled = (
                        _rdisp.style
                        .map(_pnl_color, subset=["Total P&L", "Avg P&L"])
                        .map(_wr_color,  subset=["Win %"])
                        .format({"Total P&L": "${:,.0f}", "Avg P&L": "${:,.0f}",
                                 "Win %": "{:.1f}%", "# Trades": "{:d}"})
                    )
                    st.dataframe(_rstyled, hide_index=True, width="stretch")
                with col_bar:
                    colors = ["#4caf50" if v >= 0 else "#ef5350"
                              for v in regime_grp["total_pnl"]]
                    fig_rg = go.Figure(go.Bar(
                        x=regime_grp["Regime"], y=regime_grp["total_pnl"],
                        marker_color=colors,
                        hovertemplate="%{x}<br>P&L: $%{y:,.0f}<extra></extra>",
                    ))
                    fig_rg.add_hline(y=0, line=dict(color="#546e7a", width=1, dash="dot"))
                    fig_rg.update_layout(
                        title="P&L by Regime", height=260,
                        xaxis=dict(gridcolor="#1e2130", tickangle=-20),
                        yaxis=dict(gridcolor="#1e2130", title="P&L ($)"),
                        paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
                        font=dict(color="#b0b8c8"),
                        margin=dict(l=0, r=0, t=36, b=0),
                    )
                    st.plotly_chart(fig_rg, width="stretch")

            # Regime time distribution
            regime_days = regime_series.value_counts().reset_index()
            regime_days.columns = ["Regime", "Days"]
            fig_pie = px.pie(regime_days, names="Regime", values="Days",
                             title="Time in Each Regime",
                             color_discrete_sequence=px.colors.qualitative.Set2)
            fig_pie.update_layout(height=280, paper_bgcolor="#0e1117",
                                  font=dict(color="#b0b8c8"),
                                  margin=dict(l=0, r=0, t=40, b=0))
            st.plotly_chart(fig_pie, width="stretch")

        # ── Per-trade bars + distribution ────────────────────────────────────
        if not trades_df.empty and "pnl" in trades_df.columns:
            date_col = "exit_date" if "exit_date" in trades_df.columns else trades_df.columns[1]

            # Trade type breakdown (vol arb has trade_type; others have spread_type)
            type_col = next((c for c in ["trade_type", "spread_type"] if c in trades_df.columns), None)
            if type_col:
                st.markdown("#### Performance by Trade Type")
                type_grp = (
                    trades_df.groupby(type_col)["pnl"]
                    .agg(
                        total_pnl ="sum",
                        trades    ="count",
                        win_rate  =lambda x: 100 * (x > 0).sum() / len(x),
                        avg_pnl   ="mean",
                        best      ="max",
                        worst     ="min",
                    )
                    .reset_index()
                    .rename(columns={type_col: "Type"})
                    .sort_values("total_pnl", ascending=False)
                )
                tg_l, tg_r = st.columns([2, 3])
                with tg_l:
                    _disp = type_grp.rename(columns={
                        "total_pnl": "Total P&L", "win_rate": "Win %",
                        "avg_pnl": "Avg P&L", "best": "Best", "worst": "Worst",
                        "trades": "# Trades",
                    })
                    _styled = (
                        _disp.style
                        .map(_pnl_color, subset=["Total P&L", "Avg P&L"])
                        .map(lambda v: "color: #4caf50; font-weight:600", subset=["Best"])
                        .map(lambda v: "color: #ef5350; font-weight:600", subset=["Worst"])
                        .map(_wr_color, subset=["Win %"])
                        .format({"Total P&L": "${:,.0f}", "Avg P&L": "${:,.2f}",
                                 "Win %": "{:.1f}%", "Best": "${:,.2f}",
                                 "Worst": "${:,.2f}", "# Trades": "{:d}"})
                    )
                    st.dataframe(_styled, hide_index=True, width="stretch")
                with tg_r:
                    _colors = ["#4caf50" if v >= 0 else "#ef5350" for v in type_grp["total_pnl"]]
                    fig_tg = go.Figure(go.Bar(
                        x=type_grp["Type"], y=type_grp["total_pnl"],
                        marker_color=_colors,
                        hovertemplate="%{x}<br>P&L: $%{y:,.2f}<extra></extra>",
                    ))
                    fig_tg.add_hline(y=0, line=dict(color="#546e7a", width=1, dash="dot"))
                    fig_tg.update_layout(title="P&L by Type", height=240,
                                         xaxis=dict(gridcolor="#1e2130"),
                                         yaxis=dict(title="P&L ($)", gridcolor="#1e2130"),
                                         paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
                                         font=dict(color="#b0b8c8"),
                                         margin=dict(l=0, r=0, t=36, b=0))
                    st.plotly_chart(fig_tg, width="stretch")

            col_left, col_right = st.columns(2)
            with col_left:
                colors = ["#4caf50" if v >= 0 else "#ef5350" for v in trades_df["pnl"]]
                fig_bars = go.Figure(go.Bar(
                    x=trades_df[date_col], y=trades_df["pnl"],
                    marker_color=colors,
                    hovertemplate="<b>%{x}</b><br>P&L: $%{y:,.2f}<extra></extra>",
                ))
                fig_bars.add_hline(y=0, line=dict(color="#546e7a", width=1, dash="dot"))
                fig_bars.update_layout(title="Per-Trade P&L", height=280,
                                       yaxis=dict(title="P&L ($)", gridcolor="#1e2130"),
                                       xaxis=dict(gridcolor="#1e2130"),
                                       paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
                                       font=dict(color="#b0b8c8"),
                                       margin=dict(l=0, r=0, t=36, b=0))
                st.plotly_chart(fig_bars, width="stretch")

            with col_right:
                _all_pnl = trades_df["pnl"].dropna()
                _range   = _all_pnl.max() - _all_pnl.min() if len(_all_pnl) > 1 else 100
                _bin     = max(1.0, round(_range / 15, 1))
                wins_v   = trades_df[trades_df["pnl"] > 0]["pnl"]
                loss_v   = trades_df[trades_df["pnl"] <= 0]["pnl"]
                fig_hist = go.Figure()
                if not wins_v.empty:
                    fig_hist.add_trace(go.Histogram(x=wins_v, name="Wins",
                                                    marker_color="#4caf50", opacity=0.8,
                                                    xbins=dict(size=_bin)))
                if not loss_v.empty:
                    fig_hist.add_trace(go.Histogram(x=loss_v, name="Losses",
                                                    marker_color="#ef5350", opacity=0.8,
                                                    xbins=dict(size=_bin)))
                fig_hist.update_layout(
                    title="P&L Distribution", barmode="overlay", height=280,
                    xaxis=dict(title="P&L ($)", gridcolor="#1e2130"),
                    yaxis=dict(gridcolor="#1e2130"),
                    paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
                    font=dict(color="#b0b8c8"),
                    legend=dict(orientation="h", y=1.1),
                    margin=dict(l=0, r=0, t=36, b=0),
                )
                st.plotly_chart(fig_hist, width="stretch")

            # Cumulative P&L line
            _cum = trades_df[["exit_date", "pnl"]].copy()
            _cum["exit_date"] = pd.to_datetime(_cum["exit_date"])
            _cum = _cum.sort_values("exit_date")
            _cum["cum_pnl"] = _cum["pnl"].cumsum()
            fig_cum = go.Figure()
            fig_cum.add_trace(go.Scatter(
                x=_cum["exit_date"], y=_cum["cum_pnl"],
                mode="lines+markers", name="Cum. P&L",
                line=dict(color="#5c6bc0", width=2),
                fill="tozeroy", fillcolor="rgba(92,107,192,0.08)",
                hovertemplate="%{x|%Y-%m-%d}: $%{y:,.2f}<extra></extra>",
            ))
            fig_cum.add_hline(y=0, line=dict(color="#546e7a", width=1, dash="dot"))
            fig_cum.update_layout(title="Cumulative P&L by Trade", height=260,
                                  xaxis=dict(gridcolor="#1e2130"),
                                  yaxis=dict(title="P&L ($)", gridcolor="#1e2130"),
                                  paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
                                  font=dict(color="#b0b8c8"),
                                  margin=dict(l=0, r=0, t=36, b=0))
            st.plotly_chart(fig_cum, width="stretch")

            # Monthly returns heatmap (if enough data)
            if len(equity) > 30:
                eq_df_perf = pd.DataFrame({"equity": equity})
                try:
                    st.plotly_chart(C.monthly_returns_heatmap(eq_df_perf),
                                    width="stretch", key=f"perf_{slug}_mr")
                except Exception:
                    pass

            # Trade table — expandable rows with leg detail
            st.markdown("#### All Trades")
            _td = trades_df.copy()
            if "pnl" in _td.columns:
                _td["cum_pnl"] = _td["pnl"].cumsum().round(2)
            for _iv_col in ["iv_call", "iv_put", "iv_skew"]:
                if _iv_col in _td.columns:
                    _td[_iv_col] = (_td[_iv_col] * 100).round(2)
            if "call_price_entry" in _td.columns and "put_price_entry" in _td.columns:
                _td["total_in"]  = ((_td["call_price_entry"] - _td["put_price_entry"])
                                    * _td["contracts"] * 100).round(2)
                if "pnl" in _td.columns:
                    _td["total_out"] = (_td["total_in"] + _td["pnl"]).round(2)
            elif "entry_cost" in _td.columns and "contracts" in _td.columns:
                _td["total_in"]  = (_td["entry_cost"] * _td["contracts"] * 100).round(2)
                if "exit_value" in _td.columns:
                    _td["total_out"] = (_td["exit_value"] * _td["contracts"] * 100).round(2)

            # strategies with description column (but NOT vol_arb) → plain dataframe
            if "description" in _td.columns and slug != "vol_arbitrage":
                if "pnl" in _td.columns:
                    _td.insert(0, "W/L", _td["pnl"].apply(
                        lambda v: "🟢" if isinstance(v, (int, float)) and v > 0
                        else ("🔴" if isinstance(v, (int, float)) and v < 0 else "⚪")
                    ))
                perf_show = [c for c in [
                    "W/L", "entry_date", "exit_date", "description", "comment",
                    "contracts", "trade_type",
                    "iv_call", "iv_put", "iv_skew",
                    "total_in", "total_out",
                    "pnl", "cum_pnl", "exit_reason",
                ] if c in _td.columns]
                st.dataframe(
                    _td[perf_show].sort_values(date_col, ascending=False),
                    hide_index=True, width="stretch",
                    column_config={
                        "W/L":          cc.TextColumn("", width="small"),
                        "description":  cc.TextColumn("Position",  width="large"),
                        "comment":      cc.TextColumn("Rationale", width="large"),
                        "total_in":     cc.NumberColumn("Total In ($)",  format="$%.2f"),
                        "total_out":    cc.NumberColumn("Total Out ($)", format="$%.2f"),
                        "iv_call":      cc.NumberColumn("Call IV (%)",   format="%.2f%%"),
                        "iv_put":       cc.NumberColumn("Put IV (%)",    format="%.2f%%"),
                        "iv_skew":      cc.NumberColumn("IV Skew (%)",   format="%.2f%%"),
                        "pnl":          cc.NumberColumn("P&L ($)",       format="$%.2f"),
                        "cum_pnl":      cc.NumberColumn("Cum. P&L ($)",  format="$%.2f"),
                        "exit_reason":  cc.TextColumn("Exit Reason"),
                    },
                )
            else:
                # ── expandable HTML table for arb strategies ──────────────────
                _sorted_td = _td.sort_values(date_col, ascending=False).copy()

                def _perf_detail_rows(row):
                    if slug == "conversion_arb":
                        n = int(row.get("contracts", 1)); sh = n * 100
                        def _f(v): return round(float(v or 0), 4)
                        return [
                            {"leg": f"① Stock ({sh:,} sh)", "side": "Buy",
                             "entry": _f(row.get("entry_price")), "exit": _f(row.get("exit_price")),
                             "pnl":  round(float(row.get("stock_pnl",   0) or 0), 2)},
                            {"leg": f"② Put ({n} cts)",     "side": "Buy",
                             "entry": _f(row.get("put_entry_px")), "exit": _f(row.get("put_exit_px")),
                             "pnl":  round(float(row.get("put_pnl",     0) or 0), 2)},
                            {"leg": f"③ Call ({n} cts)",    "side": "Sell",
                             "entry": _f(row.get("call_entry_px")), "exit": _f(row.get("call_exit_px")),
                             "pnl":  round(float(row.get("call_pnl",    0) or 0), 2)},
                            {"leg": "Dividend",    "side": "—", "entry": None, "exit": None,
                             "pnl":  round(float(row.get("div_received", 0) or 0), 2)},
                            {"leg": "Carry",       "side": "—", "entry": None, "exit": None,
                             "pnl": -round(float(row.get("carry_cost",   0) or 0), 2)},
                            {"leg": "Commissions", "side": "—", "entry": None, "exit": None,
                             "pnl": -round(float(row.get("commissions",  0) or 0), 2)},
                        ]
                    elif slug == "dividend_arb":
                        n = int(row.get("contracts", 1)); sh = n * 100
                        def _f(v): return round(float(v or 0), 4)
                        _put_total = float(row.get("put_cost", 0) or 0)
                        _put_prem  = _put_total / max(sh, 1)
                        return [
                            {"leg": f"① Stock ({sh:,} sh)", "side": "Buy",
                             "entry": _f(row.get("entry_cost")), "exit": _f(row.get("exit_value")),
                             "pnl":  round(float(row.get("equity_pnl", 0) or 0), 2)},
                            {"leg": f"② Put hedge ({n} cts)", "side": "Buy",
                             "entry": round(_put_prem, 4), "exit": None,
                             "pnl": -round(_put_total, 2)},
                            {"leg": "Dividend", "side": "—", "entry": None, "exit": None,
                             "pnl":  round(float(row.get("div_income", 0) or 0), 2)},
                        ]
                    elif slug == "vol_arbitrage":
                        n = int(row.get("contracts", 1))
                        def _fv(v): return round(float(v), 4) if v is not None and str(v) not in ("", "nan", "None") else None
                        tt  = str(row.get("trade_type", ""))
                        cpe = _fv(row.get("call_price_entry")); ppe = _fv(row.get("put_price_entry"))
                        cex = _fv(row.get("call_price_exit"));  pex = _fv(row.get("put_price_exit"))
                        if tt == "skew_arb":
                            rows2 = [
                                {"leg": f"① Short Put  ({n} cts)", "side": "Sell", "entry": ppe, "exit": pex,
                                 "pnl": round(float(row.get("put_pnl",  0) or 0), 2)},
                                {"leg": f"② Long Call  ({n} cts)", "side": "Buy",  "entry": cpe, "exit": cex,
                                 "pnl": round(float(row.get("call_pnl", 0) or 0), 2)},
                            ]
                            if row.get("hedge_puts") and float(row.get("hedge_puts", 0)) > 0:
                                rows2.append({"leg": "③ Delta Hedge", "side": "—", "entry": None, "exit": None,
                                              "pnl": round(float(row.get("hedge_pnl", 0) or 0), 2)})
                            if row.get("commission"):
                                rows2.append({"leg": "Commission", "side": "—", "entry": None, "exit": None,
                                              "pnl": -round(float(row.get("commission", 0) or 0), 2)})
                            return rows2
                        elif tt == "conversion":
                            return [
                                {"leg": f"① Long Call  ({n} cts)", "side": "Buy",  "entry": cpe, "exit": cex,
                                 "pnl": round(float(row.get("call_pnl", 0) or 0), 2)},
                                {"leg": f"② Short Put  ({n} cts)", "side": "Sell", "entry": ppe, "exit": pex,
                                 "pnl": round(float(row.get("put_pnl",  0) or 0), 2)},
                            ]
                        else:  # reversal
                            return [
                                {"leg": f"① Short Call ({n} cts)", "side": "Sell", "entry": cpe, "exit": cex,
                                 "pnl": round(float(row.get("call_pnl", 0) or 0), 2)},
                                {"leg": f"② Long Put   ({n} cts)", "side": "Buy",  "entry": ppe, "exit": pex,
                                 "pnl": round(float(row.get("put_pnl",  0) or 0), 2)},
                            ]
                    else:
                        _known_pnl_fields2 = [
                            ("Put P&L",    "put_pnl"),    ("Call P&L",   "call_pnl"),
                            ("Hedge P&L",  "hedge_pnl"),  ("Stock P&L",  "stock_pnl"),
                            ("Dividend",   "div_income"),  ("Carry",     "carry_cost"),
                            ("Commission", "commission"),  ("Commission", "commissions"),
                        ]
                        seen2 = set(); out2 = []
                        for k, v in _known_pnl_fields2:
                            if v in seen2 or row.get(v) is None: continue
                            seen2.add(v)
                            mult = -1 if v in ("carry_cost","commission","commissions") else 1
                            out2.append({"leg": k, "side": "—", "entry": None, "exit": None,
                                         "pnl": round(mult * float(row.get(v) or 0), 2)})
                        return out2

                _PCB = "#2d3748"; _PCH = "#1a2035"; _PBG0 = "#0f1623"; _PBG1 = "#141c2e"; _PDET = "#0a1120"
                _PBORD = "1px solid #2d3748"

                def _ppc(v):
                    c = "#4ade80" if float(v or 0) >= 0 else "#f87171"
                    return f'<span style="color:{c};font-weight:600;font-family:monospace">${float(v or 0):+,.2f}</span>'

                def _pbadge(label, val, color="#e2e8f0"):
                    return (f'<span style="display:inline-flex;flex-direction:column;margin-right:20px;margin-bottom:4px;">'
                            f'<span style="font-size:10px;color:#6b7280;text-transform:uppercase;letter-spacing:.06em;margin-bottom:2px">{label}</span>'
                            f'<span style="color:{color};font-size:13px;font-weight:600;font-family:monospace">{val}</span></span>')

                def _pleg_row(d):
                    muted = d.get("side") == "—"
                    tc = "#6b7280" if muted else "#d1d5db"
                    pv = float(d.get("pnl") or 0)
                    pc = "#4ade80" if pv >= 0 else "#f87171"
                    ent = f'${float(d["entry"]):.4f}' if d.get("entry") is not None else "—"
                    ext = f'${float(d["exit"]):.4f}'  if d.get("exit")  is not None else "—"
                    return (f'<tr style="border-bottom:{_PBORD};">'
                            f'<td style="padding:6px 14px;color:{tc}">{d["leg"]}</td>'
                            f'<td style="padding:6px 14px;color:{tc}">{d.get("side","")}</td>'
                            f'<td style="padding:6px 14px;color:{tc};font-family:monospace">{ent}</td>'
                            f'<td style="padding:6px 14px;color:{tc};font-family:monospace">{ext}</td>'
                            f'<td style="padding:6px 14px;color:{pc};font-weight:600;font-family:monospace">${pv:+,.2f}</td></tr>')

                def _pbuild_detail(tr):
                    det  = _perf_detail_rows(tr)
                    legs = [d for d in det if d.get("side") not in ("—",)]
                    attr = [d for d in det if d.get("side") == "—"]

                    html = f'<td colspan="99" style="padding:0;"><div style="background:{_PDET};padding:14px 20px 16px;border-top:{_PBORD};font-family:sans-serif;">'

                    # Arb Setup
                    if slug in ("conversion_arb", "dividend_arb", "vol_arbitrage"):
                        _n_ct2 = int(tr.get("contracts", 1)); _n_sh2 = _n_ct2 * 100
                        html += '<div style="display:flex;flex-wrap:wrap;gap:16px 0;margin-bottom:14px;padding-bottom:12px;border-bottom:1px solid #1e293b;">'
                        html += '<div style="width:100%;font-size:10px;color:#4b5563;text-transform:uppercase;letter-spacing:.1em;margin-bottom:4px;font-weight:600">Arbitrage Setup</div>'
                        if slug == "vol_arbitrage":
                            _tt2  = str(tr.get("trade_type", "—"))
                            _tt2_label = {"skew_arb": "Skew Arb (risk-reversal)", "conversion": "Conversion", "reversal": "Reversal"}.get(_tt2, _tt2)
                            _ivc2  = tr.get("iv_call");  _ivp2 = tr.get("iv_put");  _ivsk2 = tr.get("iv_skew")
                            _viol2 = tr.get("violation"); _exp2 = tr.get("expected_pnl"); _sig2 = tr.get("signal_strength")
                            _spot2 = tr.get("spot");      _dte2 = tr.get("dte");          _cost2 = tr.get("cost")
                            _cpe2  = tr.get("call_price_entry"); _ppe2 = tr.get("put_price_entry")
                            _desc2 = tr.get("description")
                            html += _pbadge("Type",          _tt2_label, "#a5b4fc")
                            if _spot2: html += _pbadge("Spot at entry",  f"${float(_spot2):.2f}")
                            if _dte2:  html += _pbadge("DTE",            f"{int(_dte2)}d")
                            if _ivc2:  html += _pbadge("IV Call",        f"{float(_ivc2):.1f}%")
                            if _ivp2:  html += _pbadge("IV Put",         f"{float(_ivp2):.1f}%")
                            if _ivsk2:
                                _psc3 = "#f87171" if float(_ivsk2) > 0 else "#4ade80"
                                html += _pbadge("IV Skew (put−call)", f"{float(_ivsk2):+.1f} pts", _psc3)
                            if _viol2:
                                _pvc = "#4ade80" if float(_viol2) > 0 else "#f87171"
                                html += _pbadge("Parity violation", f"${float(_viol2):.4f}", _pvc)
                            if _exp2:  html += _pbadge("Expected P&L",   f"${float(_exp2):+,.2f}", "#4ade80")
                            if _sig2:  html += _pbadge("Signal strength", f"{float(_sig2):.3f}")
                            if _cpe2:  html += _pbadge("Call entry px",  f"${float(_cpe2):.4f}")
                            if _ppe2:  html += _pbadge("Put entry px",   f"${float(_ppe2):.4f}")
                            if _cost2: html += _pbadge("Net cost",       f"${float(_cost2):,.2f}")
                            if _desc2:
                                html += (f'<div style="width:100%;margin-top:8px;padding-top:8px;border-top:1px solid #1e293b;'
                                         f'font-size:12px;color:#94a3b8;line-height:1.5;">{str(_desc2)}</div>')
                        elif slug == "conversion_arb":
                            adiv = tr.get("actual_div"); idiv = tr.get("implied_div"); edge = tr.get("edge")
                            rfr  = tr.get("risk_free_rate"); dte = tr.get("dte")
                            inv  = tr.get("total_in") or (float(tr.get("entry_cost", 0)) * _n_sh2)
                            if adiv: html += _pbadge("Actual div",  f"${float(adiv):.4f}/sh")
                            if idiv: html += _pbadge("Implied div", f"${float(idiv):.4f}/sh")
                            if edge:
                                ec = "#4ade80" if float(edge) > 0 else "#f87171"
                                html += _pbadge("Edge", f"${float(edge):.4f}/sh", ec)
                            if rfr: html += _pbadge("Risk-free", f"{float(rfr):.2f}%")
                            if dte: html += _pbadge("DTE", f"{int(dte)}d")
                            if inv: html += _pbadge("Invested", f"${float(inv):,.0f}")
                        else:
                            _div_total  = float(tr.get("div_income", 0) or 0)
                            _div_per_sh = _div_total / max(_n_sh2, 1)
                            _entry_px   = float(tr.get("entry_cost", 0) or 0)
                            _put_total  = float(tr.get("put_cost", 0) or 0)
                            html += _pbadge("Div/share",  f"${_div_per_sh:.4f}")
                            html += _pbadge("Total div",  f"${_div_total:,.2f}")
                            html += _pbadge("Put cost",   f"${_put_total:,.2f}")
                            html += _pbadge("Invested",   f"${_entry_px * _n_sh2:,.0f}")
                            html += _pbadge("Size",       f"{_n_ct2} cts · {_n_sh2:,} sh")
                        html += '</div>'

                    # Trade Legs
                    if legs:
                        html += '<div style="margin-bottom:14px;">'
                        html += '<div style="font-size:10px;color:#4b5563;text-transform:uppercase;letter-spacing:.1em;font-weight:600;margin-bottom:6px">Trade Legs</div>'
                        html += '<table style="width:100%;border-collapse:collapse;font-size:12.5px;">'
                        html += (f'<tr style="background:#111827;border-bottom:2px solid #374151;">'
                                 f'<th style="padding:5px 14px;text-align:left;color:#6b7280;font-weight:500;font-size:11px;text-transform:uppercase;letter-spacing:.05em">Leg</th>'
                                 f'<th style="padding:5px 14px;text-align:left;color:#6b7280;font-weight:500;font-size:11px;text-transform:uppercase;letter-spacing:.05em">Side</th>'
                                 f'<th style="padding:5px 14px;text-align:right;color:#6b7280;font-weight:500;font-size:11px;text-transform:uppercase;letter-spacing:.05em">Entry px</th>'
                                 f'<th style="padding:5px 14px;text-align:right;color:#6b7280;font-weight:500;font-size:11px;text-transform:uppercase;letter-spacing:.05em">Exit px</th>'
                                 f'<th style="padding:5px 14px;text-align:right;color:#6b7280;font-weight:500;font-size:11px;text-transform:uppercase;letter-spacing:.05em">P&L</th></tr>')
                        for d in legs:
                            html += _pleg_row(d)
                        html += '</table></div>'

                    # P&L Attribution
                    if attr:
                        pnl_total = float(tr.get("pnl") or 0)
                        ptc = "#4ade80" if pnl_total >= 0 else "#f87171"
                        html += (f'<div style="display:flex;flex-wrap:wrap;align-items:center;gap:6px 0;'
                                 f'padding-top:10px;border-top:1px solid #1e293b;">'
                                 f'<div style="width:100%;font-size:10px;color:#4b5563;text-transform:uppercase;'
                                 f'letter-spacing:.1em;font-weight:600;margin-bottom:4px">P&L Attribution</div>')
                        for d in attr:
                            pv = float(d.get("pnl") or 0)
                            pc = "#4ade80" if pv >= 0 else "#f87171"
                            html += (f'<span style="margin-right:24px;white-space:nowrap;">'
                                     f'<span style="color:#6b7280;font-size:12px">{d["leg"]} </span>'
                                     f'<span style="color:{pc};font-weight:600;font-family:monospace">${pv:+,.2f}</span></span>')
                        html += (f'<span style="margin-left:auto;padding:4px 12px;background:#111827;'
                                 f'border-radius:4px;border:1px solid #374151;white-space:nowrap;">'
                                 f'<span style="color:#9ca3af;font-size:12px">Net P&L </span>'
                                 f'<span style="color:{ptc};font-weight:700;font-size:14px;font-family:monospace">${pnl_total:+,.2f}</span></span>')
                        html += '</div>'

                    html += '</div></td>'
                    return html

                # Summary columns
                _psum_cols = [c for c in ["entry_date","exit_date","strike","contracts","dte","edge","pnl","return_pct","cum_pnl"] if c in _sorted_td.columns]
                _psum_labels = {"entry_date":"Entry","exit_date":"Exit","strike":"Strike","contracts":"Cts","dte":"DTE","edge":"Edge $/sh","pnl":"P&L","return_pct":"Return %","cum_pnl":"Cum P&L"}
                # Fallback for strategies without standard arb columns
                if not _psum_cols:
                    _psum_cols = [c for c in ["entry_date","exit_date","spread_type","entry_cost","pnl","cum_pnl","exit_reason"] if c in _sorted_td.columns]
                    _psum_labels.update({"spread_type":"Type","entry_cost":"Cost/sh","exit_reason":"Exit"})

                def _psc(col, val):
                    if val is None or (isinstance(val, float) and np.isnan(val)): return "—"
                    if col in ("pnl","cum_pnl"): return _ppc(val)
                    if col == "return_pct":
                        v = float(val); c = "#4ade80" if v >= 0 else "#f87171"
                        return f'<span style="color:{c};font-weight:600">{v:+.2f}%</span>'
                    if col == "edge":
                        v = float(val); c = "#4ade80" if v > 0 else "#f87171"
                        return f'<span style="color:{c};font-weight:600;font-family:monospace">${v:.4f}</span>'
                    if col == "strike": return f"${float(val):.2f}"
                    return str(val)

                _pcol_w = {"entry_date":"120px","exit_date":"120px","strike":"80px","contracts":"55px","dte":"55px","edge":"100px","pnl":"115px","return_pct":"95px","cum_pnl":"115px","spread_type":"120px","entry_cost":"100px","exit_reason":"120px"}
                _pgrid = "36px " + " ".join(_pcol_w.get(c,"100px") for c in _psum_cols)

                _phdr_cells = (
                    f'<div style="display:grid;grid-template-columns:{_pgrid};background:{_PCH};'
                    f'border-bottom:2px solid #374151;font-family:sans-serif;">'
                    f'<div style="padding:8px 10px;"></div>'
                    + "".join(
                        f'<div style="padding:8px 14px;font-size:11px;color:#6b7280;font-weight:600;'
                        f'text-transform:uppercase;letter-spacing:.07em;border-left:{_PBORD};white-space:nowrap;">'
                        f'{_psum_labels.get(c,c)}</div>'
                        for c in _psum_cols
                    ) + '</div>'
                )

                _pdet_groups = []
                for _pi, (_, _ptr) in enumerate(_sorted_td.iterrows()):
                    _pbg  = _PBG0 if _pi % 2 == 0 else _PBG1
                    _pdet = _pbuild_detail(_ptr)
                    _pcells = "".join(
                        f'<div style="padding:9px 14px;font-size:13px;color:#e2e8f0;'
                        f'border-left:{_PBORD};white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">'
                        f'{_psc(c, _ptr.get(c))}</div>'
                        for c in _psum_cols
                    )
                    _pdet_groups.append(
                        f'<details style="border-top:{_PBORD};">'
                        f'<summary style="display:grid;grid-template-columns:{_pgrid};list-style:none;'
                        f'cursor:pointer;background:{_pbg};align-items:center;" '
                        f'onmouseover="this.style.background=\'#1a2840\'" onmouseout="this.style.background=\'{_pbg}\'">'
                        f'<div style="padding:9px 10px;text-align:center;">'
                        f'<span style="font-size:10px;color:#6b7280;display:inline-block;'
                        f'transition:transform .2s;">&#9654;</span></div>'
                        f'{_pcells}</summary>'
                        f'<div style="background:{_PDET};border-top:{_PBORD};">{_pdet}</div>'
                        f'</details>'
                    )

                _phtml = (
                    f'<style>details[open]>summary>div>span{{transform:rotate(90deg);}}'
                    f'details>summary::-webkit-details-marker{{display:none;}}</style>'
                    f'<div style="border:{_PBORD};border-radius:6px;overflow:hidden;font-family:sans-serif;">'
                    f'{_phdr_cells}{"".join(_pdet_groups)}</div>'
                )
                st.markdown(_phtml, unsafe_allow_html=True)

    st.divider()

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 2 — LIVE / PAPER TRADING P&L (from DB)
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown("### 💹 Live / Paper Trades")

    try:
        from alan_trader.db.client import get_engine
        from alan_trader.db import portfolio_client as pc
        engine = get_engine()
    except Exception as e:
        st.warning(f"DB not available: {e}")
        return

    closed = pc.get_closed_positions(engine, strategy_name=slug)
    if closed.empty:
        closed = pc.get_closed_positions(engine, strategy_name=display_name)

    if closed.empty:
        st.info("No executed trades recorded yet. Trades appear here after you execute from "
                "Paper Trading or log them in Portfolio → Log Trade.")
        return

    closed["CloseDate"] = pd.to_datetime(closed["CloseDate"])
    closed = closed.sort_values("CloseDate")

    total_pnl = closed["RealizedPnL"].sum()
    wins      = (closed["RealizedPnL"] > 0).sum()
    n_trades  = len(closed)
    win_rate  = 100 * wins / n_trades if n_trades else 0
    avg_pnl   = closed["RealizedPnL"].mean()
    best      = closed["RealizedPnL"].max()
    worst     = closed["RealizedPnL"].min()

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Total P&L",   f"${total_pnl:,.2f}")
    c2.metric("Trades",       str(n_trades))
    c3.metric("Win Rate",    f"{win_rate:.1f}%")
    c4.metric("Avg P&L",     f"${avg_pnl:,.2f}")
    c5.metric("Best Trade",  f"${best:,.2f}")
    c6.metric("Worst Trade", f"${worst:,.2f}")

    closed["CumPnL"] = closed["RealizedPnL"].cumsum()
    fig_live = go.Figure()
    fig_live.add_trace(go.Scatter(
        x=closed["CloseDate"], y=closed["CumPnL"],
        mode="lines+markers", name="Cumulative P&L",
        line=dict(color="#26a69a", width=2),
        fill="tozeroy", fillcolor="rgba(38,166,154,0.1)",
        hovertemplate="<b>%{x|%Y-%m-%d}</b><br>Cumulative: $%{y:,.2f}<extra></extra>",
    ))
    fig_live.add_hline(y=0, line=dict(color="#546e7a", width=1, dash="dot"))
    fig_live.update_layout(title="Cumulative Live P&L", height=300, **_DARK)
    st.plotly_chart(fig_live, width="stretch")

    show_cols = [c for c in ["CloseDate", "Symbol", "PositionType", "Direction",
                              "Quantity", "AvgEntryPrice", "AvgExitPrice",
                              "RealizedPnL", "HoldDays", "Regime", "Tags"]
                 if c in closed.columns]
    st.dataframe(
        closed[show_cols].sort_values("CloseDate", ascending=False),
        width="stretch", hide_index=True,
        column_config={
            "CloseDate":     cc.DateColumn("Close Date"),
            "RealizedPnL":   cc.NumberColumn("P&L",     format="$%.2f"),
            "AvgEntryPrice": cc.NumberColumn("Entry",   format="$%.4f"),
            "AvgExitPrice":  cc.NumberColumn("Exit",    format="$%.4f"),
            "Quantity":      cc.NumberColumn("Qty",     format="%.2f"),
            "HoldDays":      cc.NumberColumn("Hold Days", format="%d d"),
        },
    )


# ══════════════════════════════════════════════════════════════════════════════
# MAIN LAYOUT — dynamic strategy tabs + generic tabs
# ══════════════════════════════════════════════════════════════════════════════

# ── Top-level tabs ─────────────────────────────────────────────────────────────
tab_market, tab_screener, tab_paper, tab_portfolio, tab_strategies, tab_tools = st.tabs(
    ["📡 Market", "🔍 Screener", "💹 Paper Trading", "📦 Portfolio", "📈 Strategies", "🛠 Tools"]
)

# ── MARKET (homepage) ─────────────────────────────────────────────────────────
with tab_market:
    from alan_trader.dashboard.tabs.market_data import render as render_market
    mkt_ticker = _ticker_row("mkt")
    render_market(ticker=mkt_ticker, api_key=st.session_state.get("polygon_api_key", ""))

# ── SCREENER ──────────────────────────────────────────────────────────────────
with tab_screener:
    from alan_trader.dashboard.tabs.screener import render as render_screener
    render_screener(api_key=st.session_state.get("polygon_api_key", ""))

# ── PAPER TRADING ──────────────────────────────────────────────────────────────
with tab_paper:
    from alan_trader.dashboard.tabs.paper_trading import render as render_paper_trading
    render_paper_trading()

# ── PORTFOLIO / TRADE LOG ──────────────────────────────────────────────────────
with tab_portfolio:
    from alan_trader.dashboard.tabs.trade_log import render as render_tradelog
    render_tradelog(api_key=st.session_state.get("polygon_api_key", ""))

# ── STRATEGIES ────────────────────────────────────────────────────────────────
with tab_strategies:
    if not selected:
        st.markdown(
            """<div style="text-align:center;padding:80px 0;color:#78909c">
              <div style="font-size:3rem">📈</div>
              <div style="font-size:1.3rem;margin-top:12px">Select strategies from the sidebar to get started.</div>
            </div>""", unsafe_allow_html=True,
        )
    else:
        strat_tab_names = [f"{_meta(s).get('icon','📌')} {_meta(s)['display_name']}" for s in selected]
        strategy_tabs   = st.tabs(strat_tab_names)

        for slug, stab in zip(selected, strategy_tabs):
            with stab:
                inner_names = []
                if _cap(slug, "requires_training"):
                    inner_names.append("🧠 Train")
                inner_names += ["📊 Backtest", "🔴 Live", "📈 Performance"]

                inner_tabs = st.tabs(inner_names)
                idx = 0

                if _cap(slug, "requires_training"):
                    with inner_tabs[idx]:
                        _render_train(slug)
                    idx += 1

                with inner_tabs[idx]:
                    _render_backtest(slug)
                idx += 1

                with inner_tabs[idx]:
                    _render_live(slug)
                idx += 1

                with inner_tabs[idx]:
                    _render_strategy_performance(slug)

# ── TOOLS ─────────────────────────────────────────────────────────────────────
with tab_tools:
    tool_tab_names = ["🗄 Data", "🔭 Polygon", "🛡 Risk", "🗂 Registry", "📚 Guide"]
    (tab_data, tab_polygon, tab_risk, tab_registry, tab_guide) = st.tabs(tool_tab_names)

    with tab_data:
        from alan_trader.dashboard.tabs.data_manager import render as render_data
        render_data(api_key=st.session_state.get("polygon_api_key", ""))

    with tab_polygon:
        from alan_trader.dashboard.tabs.polygon_explorer import render as render_polygon
        render_polygon(api_key=st.session_state.get("polygon_api_key", ""))

    with tab_risk:
        from alan_trader.dashboard.tabs.risk_management import render as render_risk
        _results = list(st.session_state["bt_results"].values())
        _report  = st.session_state["bt_report"]
        if not _results:
            st.info("Run at least one **Backtest** to populate the Risk tab.")
        else:
            render_risk(_report, _results)

    with tab_registry:
        from alan_trader.dashboard.tabs.strategy_selector import render as render_selector
        bt_results_dict = st.session_state["bt_results"]
        render_selector(bt_results_dict, list(bt_results_dict.keys()))

    with tab_guide:
        from alan_trader.dashboard.tabs.strategy_guide import render as render_guide
        render_guide()
