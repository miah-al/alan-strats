"""
alan-strats — Multi-Strategy Dashboard.
Run: streamlit run alan_trader/dashboard/app.py (from d:/Work/ClaudeCodeTest)
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import datetime
import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="alan-strats",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
  [data-testid="stAppViewContainer"] { background-color: #0e1117; }
  [data-testid="stSidebar"]          { background-color: #161b27; }
  .stTabs [data-baseweb="tab-list"]  { gap: 4px; flex-wrap: wrap; }
  .stTabs [data-baseweb="tab"] {
      background: #1e2130; border-radius: 6px;
      padding: 6px 14px; color: #e0e0e0; font-size: 13px;
  }
  .stTabs [aria-selected="true"] {
      background: #5c6bc0 !important; color: white !important;
  }
  h1, h2, h3 { color: #e0e0e0 !important; }
  p, li       { color: #b0b8c8; }
  [data-testid="stMetricValue"]  { color: #e0e0e0 !important; }
  [data-testid="stMetricLabel"]  { color: #78909c !important; }
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
# SESSION STATE
# ══════════════════════════════════════════════════════════════════════════════

_SS_DEFAULTS: dict = {
    "selected_strategies": ACTIVE_SLUGS[:1],
    "train_results":   {},          # {slug: train_result_dict}
    "bt_results":      {},          # {slug: BacktestResult}
    "bt_report":       {},          # last portfolio report (aggregate)
    "bt_rolling_w":    pd.DataFrame(),
    "portfolio_store": None,
}
for _k, _v in _SS_DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR — strategy picker + global settings
# ══════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.title("📈 alan-strats")
    st.markdown("---")

    st.subheader("Strategies")
    selected = st.multiselect(
        "Active strategies",
        options=ACTIVE_SLUGS,
        default=st.session_state["selected_strategies"],
        format_func=lambda s: f"{_meta(s).get('icon','📌')} {_meta(s)['display_name']}",
        key="selected_strategies",
        label_visibility="collapsed",
    )

    st.markdown("---")
    st.subheader("Data")
    use_sim = st.toggle("Simulated data (no API key)", value=True)
    st.caption("Disable to use real Polygon.io data")
    if not use_sim:
        st.text_input(
            "Polygon API key",
            type="password",
            placeholder="sk_...",
            key="polygon_api_key",
        )
        api_key_val = st.session_state.get("polygon_api_key", "")
        if not api_key_val:
            st.warning("⚠️ Enter your Polygon API key to fetch live data.")
        if st.button("🔌 Test API key", use_container_width=True, disabled=not api_key_val):
            try:
                from alan_trader.data.polygon_client import PolygonClient
                c = PolygonClient(api_key=api_key_val)
                snap = c._get("/v2/snapshot/locale/us/markets/stocks/tickers/SPY")
                if snap.get("ticker"):
                    price = snap["ticker"].get("day", {}).get("c") or snap["ticker"].get("lastTrade", {}).get("p")
                    st.success(f"✅ Connected — SPY ${price:.2f}" if price else "✅ Connected")
                else:
                    st.error("❌ Key accepted but no data returned.")
            except Exception as e:
                st.error(f"❌ {e}")

    st.markdown("---")
    if st.button("🔄 Clear all results", use_container_width=True):
        st.cache_data.clear()
        for _k in _SS_DEFAULTS:
            st.session_state[_k] = _SS_DEFAULTS[_k]
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
    from alan_trader.data.simulator import POPULAR_TICKERS, TICKER_PROFILES, DEFAULT_PROFILE
    c1, c2 = st.columns([2, 7])
    ticker = c1.selectbox("Ticker", POPULAR_TICKERS, index=0, key=f"{key_prefix}_ticker")
    prof = TICKER_PROFILES.get(ticker, DEFAULT_PROFILE)
    c2.caption(
        f"Est. vol: {prof['annual_vol']*100:.0f}% ann · {prof.get('category', 'equity')}"
    )
    return ticker


# ══════════════════════════════════════════════════════════════════════════════
# BACKEND HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _build_cm(trainer, features, labels):
    import torch
    from alan_trader.model.architecture import SequenceDataset
    from torch.utils.data import DataLoader
    scaled = trainer.scaler.transform(features)
    ds     = SequenceDataset(scaled, labels, trainer.seq_len)
    loader = DataLoader(ds, batch_size=256, shuffle=False)
    trainer.model.eval()
    preds, trues = [], []
    with torch.no_grad():
        for x, y, _ in loader:
            out = trainer.model(x.to(trainer.device)).argmax(1).cpu().numpy()
            preds.extend(out); trues.extend(y.numpy())
    cm = np.zeros((3, 3), dtype=float)
    for t, p in zip(trues, preds):
        cm[int(t), int(p)] += 1
    return cm


def _build_feat_imp(trainer, features, labels, feat_names):
    import torch
    from alan_trader.model.architecture import SequenceDataset
    from torch.utils.data import DataLoader
    scaled = trainer.scaler.transform(features.copy())

    def _acc():
        ds = SequenceDataset(scaled, labels, trainer.seq_len)
        loader = DataLoader(ds, batch_size=256)
        trainer.model.eval()
        correct = total = 0
        with torch.no_grad():
            for x, y, _ in loader:
                correct += (trainer.model(x.to(trainer.device)).argmax(1)
                            == y.to(trainer.device)).sum().item()
                total += len(y)
        return correct / total if total else 0.0

    baseline = _acc()
    rng = np.random.default_rng(0)
    imp = {}
    for i, name in enumerate(feat_names):
        if i >= scaled.shape[1]: continue
        saved = scaled[:, i].copy()
        rng.shuffle(scaled[:, i])
        imp[name] = max(0.0, baseline - _acc())
        scaled[:, i] = saved
    return pd.Series(imp).sort_values(ascending=False)


def _do_train(slug, seq_len, hidden_size, num_layers, dropout, lr, num_epochs,
              ticker="SPY", forward_days=5, otm_pct=0.0, spread_type="bull_call",
              use_sim=True, api_key=""):
    import warnings; warnings.filterwarnings("ignore")
    from alan_trader.data.features import build_feature_matrix, FEATURE_COLS
    from alan_trader.model.trainer import ModelTrainer

    if use_sim or not api_key:
        from alan_trader.data.simulator import (
            simulate_price, simulate_vix, simulate_rates, simulate_news, simulate_macro,
        )
        spy     = simulate_price(ticker=ticker, n_days=756, keep_regime=True)
        vix     = simulate_vix(756, price_df=spy)
        spy     = spy.drop(columns=["_regime"], errors="ignore")
        r2, r10 = simulate_rates(756)
        news    = simulate_news(756)
        macro   = simulate_macro(756)
    else:
        from alan_trader.data.loader import load_real_data
        data    = load_real_data(ticker=ticker, n_days=756, api_key=api_key)
        spy     = data["spy"]
        vix     = data["vix"]
        r2      = data["rate2y"]
        r10     = data["rate10y"]
        macro   = data["macro"]
        news    = data["news"]

    df      = build_feature_matrix(spy, vix, r2, r10, news, forward_days=forward_days,
                                    spread_type=spread_type, macro_df=macro)

    features = df[FEATURE_COLS].values
    labels   = df["label"].values
    n_train  = int(len(features) * 0.80)

    trainer = ModelTrainer(
        num_features=len(FEATURE_COLS),
        hidden_size=hidden_size, num_layers=num_layers, dropout=dropout,
        lr=lr, batch_size=32, num_epochs=num_epochs, patience=15, seq_len=seq_len,
    )
    history = trainer.fit(features[:n_train], labels[:n_train])

    test_features = features[n_train:]
    test_labels   = labels[n_train:]
    cm            = _build_cm(trainer, test_features, test_labels)
    feat_imp      = _build_feat_imp(trainer, test_features, test_labels, FEATURE_COLS)

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

    rows = []
    for i in range(len(w_df)):
        row    = w_df.iloc[i]
        actual = int(w_actual[i])
        S   = float(row.get("close", 0))
        iv  = float(row.get("vix", 18.0)) / 100
        r   = float(row.get("rate_10y", 0.045))
        T   = 30 / 252
        structure_str, cost = _structure(spread_type, S, iv, r, T, otm_pct / 100)
        rows.append({
            "date":             row.get(date_col, ""),
            "outcome":          "✅ Confirmed" if actual == 2 else ("⚠️ Skip" if actual == 1 else "❌ Avoid"),
            "structure":        structure_str,
            "spot":             round(S, 2),
            "total_1ct":        round(cost * 100, 2),
            "hold_days":        forward_days,
            "confidence":       round(float(w_probas[i].max()), 3),
            "fwd_%":            round(float(row.get("fwd_ret", 0)) * 100, 2),
        })
    samples = pd.DataFrame(rows)

    return {
        "history":        history,
        "cm":             cm,
        "feat_imp":       feat_imp,
        "trainer":        trainer,
        "feat_df":        df,
        "FEATURE_COLS":   FEATURE_COLS,
        "winner_samples": samples,
        "n_confirmed":    n_confirmed,
        "spread_type":    spread_type,
    }


def _do_backtest(slug, params, ticker, n_days, use_sim=True, api_key=""):
    import warnings; warnings.filterwarnings("ignore")

    if use_sim or not api_key:
        from alan_trader.data.simulator import (
            simulate_price, simulate_vix, simulate_rates, simulate_news,
            simulate_dividend_events, simulate_macro,
        )
        spy     = simulate_price(ticker=ticker, n_days=n_days, keep_regime=True)
        vix     = simulate_vix(n_days, price_df=spy)
        spy     = spy.drop(columns=["_regime"], errors="ignore")
        r2, r10 = simulate_rates(n_days)
        news    = simulate_news(n_days)
        macro   = simulate_macro(n_days)
        divs    = simulate_dividend_events(spy)
    else:
        from alan_trader.data.loader import load_real_data
        data    = load_real_data(ticker=ticker, n_days=n_days, api_key=api_key)
        spy     = data["spy"]
        vix     = data["vix"]
        r2      = data["rate2y"]
        r10     = data["rate10y"]
        macro   = data["macro"]
        news    = data["news"]
        from alan_trader.data.simulator import simulate_dividend_events
        divs    = simulate_dividend_events(spy)

    aux = {"vix": vix, "rate2y": r2, "rate10y": r10, "macro": macro,
           "news": news, "dividends": divs}

    strat = get_strategy(slug)
    if not strat.is_ready():
        raise ValueError(f"Strategy {slug} is not ready.")
    return strat.backtest(spy, aux, starting_capital=100_000, **params)


def _rebuild_portfolio_report():
    """Recompute portfolio report from all available bt_results."""
    results = list(st.session_state["bt_results"].values())
    if not results:
        return {}, pd.DataFrame()
    try:
        from alan_trader.data.simulator import simulate_price
        from alan_trader.portfolio.manager import PortfolioManager
        spy      = simulate_price(ticker="SPY", n_days=504)
        spy_rets = spy["close"].pct_change().dropna()
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
        hp7, hp8, _ = st.columns(3)
        forward_days = hp7.slider("Hold / forward days", 2, 20, 5, key=f"tr_{slug}_fwd")
        otm_pct_tr   = hp8.slider("OTM %", 0, 40, 0, 5,
                                   help="Strike offset for winners table leg price estimates.",
                                   key=f"tr_{slug}_otm")

    if st.button("▶ Train Model", type="primary", key=f"btn_train_{slug}"):
        with st.spinner("Training… this may take a minute."):
            try:
                result = _do_train(slug, seq_len, hidden, layers, dropout, lr, epochs,
                                   ticker=ticker if needs_ticker else "SPY",
                                   forward_days=forward_days, otm_pct=otm_pct_tr,
                                   spread_type=spread_type_tr,
                                   use_sim=use_sim,
                                   api_key=st.session_state.get("polygon_api_key", ""))
                st.session_state["train_results"][slug] = result
                st.success("Training complete!")
            except Exception as ex:
                st.error(f"Training failed: {ex}")
        st.rerun()

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

    # ── Model ENTER signals — shown first ──────────────────────────────────
    winner_samples = train_res.get("winner_samples")
    n_confirmed    = train_res.get("n_confirmed", 0)
    st.markdown("---")
    col_cfg = {
        "outcome":    st.column_config.TextColumn("Outcome",          width="small"),
        "structure":  st.column_config.TextColumn("Options Structure", width="large"),
        "spot":       st.column_config.NumberColumn("Spot",            format="$%.2f"),
        "total_1ct":  st.column_config.NumberColumn("1 Contract Total", format="$%.2f",
                          help="Per share × 100 — actual dollar amount for 1 contract"),
        "hold_days":  st.column_config.NumberColumn("Hold Days",       format="%d"),
        "confidence": st.column_config.ProgressColumn("Confidence",    min_value=0, max_value=1, format="%.2f"),
        "fwd_%":      st.column_config.NumberColumn("Fwd Ret %",       format="%.2f%%"),
    }
    if winner_samples is not None and not winner_samples.empty:
        n_total = len(winner_samples)
        st.subheader(f"Model ENTER Signals — {n_total} signals ({n_confirmed} confirmed correct)")
        st.caption(
            f"Spread: **{spread_label}**  ·  Strikes are 30-day expiry Black-Scholes at signal date  "
            "·  ✅ Confirmed = actual label also ENTER  ·  ⚠️ Skip / ❌ Avoid = model fired but conditions weren't ideal."
        )
        st.dataframe(winner_samples, use_container_width=True,
                     column_config=col_cfg, hide_index=True)
    else:
        st.info(f"Model generated no ENTER signals for **{spread_label}** in the test period. "
                "Try more epochs or a different spread type.")

    with st.expander("Training Curves", expanded=False):
        c1, c2 = st.columns(2)
        with c1: st.plotly_chart(C.loss_curves(history),     use_container_width=True)
        with c2: st.plotly_chart(C.accuracy_curves(history), use_container_width=True)

    with st.expander("Confusion Matrix & Label Distribution", expanded=False):
        c3, c4 = st.columns(2)
        with c3: st.plotly_chart(C.confusion_matrix_heatmap(cm), use_container_width=True)
        with c4: st.plotly_chart(C.label_distribution_pie(feat_df["label"].values), use_container_width=True)

    with st.expander("Feature Importance", expanded=False):
        st.plotly_chart(C.feature_importance_bar(feat_imp, top_n=20), use_container_width=True)

    with st.expander("Feature Correlation", expanded=False):
        st.plotly_chart(C.feature_correlation_heatmap(feat_df, FEATURE_COLS), use_container_width=True)

    with st.expander("Feature Scatter Analysis", expanded=False):
        s1, s2 = st.columns(2)
        with s1:
            st.plotly_chart(C.rsi_vix_scatter(feat_df), use_container_width=True)
        with s2:
            import plotly.graph_objects as go
            fx = st.selectbox("X feature", FEATURE_COLS, index=0, key=f"tr_{slug}_sc_x")
            fy = st.selectbox("Y feature", FEATURE_COLS, index=1, key=f"tr_{slug}_sc_y")
            cm_map = {0: "#ef5350", 1: "#78909c", 2: "#26a69a"}
            fig_sc = go.Figure()
            for cls, lbl in {0: "Avoid", 1: "Skip", 2: "Enter"}.items():
                mask = feat_df["label"] == cls
                fig_sc.add_trace(go.Scatter(
                    x=feat_df.loc[mask, fx], y=feat_df.loc[mask, fy],
                    mode="markers", name=lbl,
                    marker=dict(size=4, color=cm_map[cls], opacity=0.6),
                ))
            fig_sc.update_layout(
                paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
                font=dict(color="#e0e0e0"), height=380, margin=dict(l=40, r=20, t=40, b=40),
                title=f"{fx} vs {fy}",
                xaxis=dict(title=fx, gridcolor="#1e2130"),
                yaxis=dict(title=fy, gridcolor="#1e2130"),
            )
            st.plotly_chart(fig_sc, use_container_width=True, key=f"tr_{slug}_scatter")

    with st.expander("3-D Feature Space", expanded=False):
        c3a, c3b, c3c = st.columns(3)
        f3x = c3a.selectbox("X", FEATURE_COLS,
                            index=FEATURE_COLS.index("rsi_14") if "rsi_14" in FEATURE_COLS else 0,
                            key=f"tr_{slug}_3dx")
        f3y = c3b.selectbox("Y", FEATURE_COLS,
                            index=FEATURE_COLS.index("vix") if "vix" in FEATURE_COLS else 1,
                            key=f"tr_{slug}_3dy")
        f3z = c3c.selectbox("Z", FEATURE_COLS,
                            index=FEATURE_COLS.index("macd") if "macd" in FEATURE_COLS else 2,
                            key=f"tr_{slug}_3dz")
        st.plotly_chart(C.feature_scatter_3d(feat_df, f3x, f3y, f3z),
                        use_container_width=True, key=f"tr_{slug}_3d")


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
    bt_start = dr1.date_input("Start", value=today - datetime.timedelta(days=365),
                               max_value=today - datetime.timedelta(days=60),
                               key=f"bt_{slug}_start")
    bt_end   = dr2.date_input("End",   value=today - datetime.timedelta(days=1),
                               max_value=today, key=f"bt_{slug}_end")
    n_days   = max(60, int((bt_end - bt_start).days * 252 / 365))
    st.caption(f"≈ {n_days} trading days")

    # Strategy-specific parameters
    params = {}
    with st.expander("Strategy Parameters", expanded=True):
        p1, p2, p3 = st.columns(3)
        if slug == "options_spread":
            from alan_trader.data.features import SPREAD_TYPE_OPTIONS as _STO2
            params["spread_type"] = st.selectbox(
                "Spread type",
                options=list(_STO2.keys()),
                format_func=lambda k: _STO2[k],
                key=f"bt_{slug}_spread_type",
            )
            params["seq_len"]         = p1.slider("Seq length",      10, 60,  30, key=f"bt_{slug}_seq")
            params["hold_days"]       = p2.slider("Hold days",        2, 15,   5, key=f"bt_{slug}_hold")
            params["min_confidence"]  = p3.slider("Min confidence", 0.33, 0.70, 0.38, 0.01,
                                                   key=f"bt_{slug}_minc")
            p4, p5, p6 = st.columns(3)
            params["otm_pct"] = p4.slider("OTM %", 0, 40, 0, 5,
                                           help="How far out-of-the-money the long strike is. "
                                                "0 = ATM, 20 = 20% OTM, 30 = 30% OTM.",
                                           key=f"bt_{slug}_otm")
            params["num_epochs"] = p5.slider("Train epochs", 20, 200, 60, 10,
                                              key=f"bt_{slug}_epochs")
            p6.caption(f"Strike = spot × (1 ± {params['otm_pct']}%)")
        elif slug == "dividend_arb":
            params["hold_days"]       = p1.slider("Days before ex-div", 1, 10, 3, key=f"bt_{slug}_hold")
        elif slug == "vol_arbitrage":
            params["hold_days"]       = p1.slider("Max hold days",  1, 10, 3, key=f"bt_{slug}_hold")
            params["min_violation_pct"] = p2.slider("Min violation % of S", 0.1, 1.0, 0.3, 0.1,
                                                     key=f"bt_{slug}_minv")

    if st.button("▶ Run Backtest", type="primary", key=f"btn_bt_{slug}"):
        with st.spinner(f"Running {meta['display_name']} backtest…"):
            try:
                res = _do_backtest(slug, params, ticker or "SPY", n_days,
                                  use_sim=use_sim,
                                  api_key=st.session_state.get("polygon_api_key", ""))
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
            except Exception as ex:
                st.error(f"Backtest failed: {ex}")
        st.rerun()

    res = st.session_state["bt_results"].get(slug)
    if res is None:
        st.info("Configure settings above and press **▶ Run Backtest**.")
        return

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
        n_winners = int((trades["pnl"] > 0).sum()) if "pnl" in trades.columns else 0
        n_losers  = n_total - n_winners
        st.subheader(f"Trades — {n_winners} winners / {n_losers} losers / {n_total} total")
        st.caption("Long/short leg prices are per-share option prices at entry. "
                   "Spread cost = long leg − short leg + slippage.")

        disp = trades.copy()
        if "entry_cost" in disp.columns and "predicted_spread_price" in disp.columns:
            disp["price_error"] = (disp["predicted_spread_price"] - disp["entry_cost"]).round(4)

        show_cols = [c for c in ["entry_date", "exit_date", "spread_type",
                                  "long_strike", "long_leg_price",
                                  "short_strike", "short_leg_price",
                                  "entry_cost", "predicted_spread_price",
                                  "price_error", "pnl", "exit_reason"]
                     if c in disp.columns]
        col_cfg = {
            "pnl":                    st.column_config.NumberColumn("P&L ($)",         format="$%.2f"),
            "entry_cost":             st.column_config.NumberColumn("Spread Cost ($)",  format="$%.4f"),
            "predicted_spread_price": st.column_config.NumberColumn("Predicted ($)",   format="$%.4f"),
            "price_error":            st.column_config.NumberColumn("Price Error ($)",  format="$%.4f"),
            "long_strike":            st.column_config.NumberColumn("Long Strike",      format="$%.0f"),
            "short_strike":           st.column_config.NumberColumn("Short Strike",     format="$%.0f"),
            "long_leg_price":         st.column_config.NumberColumn("Long Leg ($)",     format="$%.4f"),
            "short_leg_price":        st.column_config.NumberColumn("Short Leg ($)",    format="$%.4f"),
        }
        if "pnl" in disp.columns:
            styled = disp[show_cols].style.map(
                lambda v: ("color:#26a69a;font-weight:600" if isinstance(v, (int, float)) and v > 0
                           else "color:#ef5350" if isinstance(v, (int, float)) and v < 0
                           else ""),
                subset=["pnl"],
            )
        else:
            styled = disp[show_cols]
        st.dataframe(styled, use_container_width=True, column_config=col_cfg, hide_index=True)

    st.markdown("---")

    eq = res.equity_curve.copy()
    eq.index = pd.to_datetime(eq.index)
    eq_df = pd.DataFrame({"equity": eq, "price": eq * 0 + 100_000})

    with st.expander("Equity Curve & Drawdown", expanded=True):
        st.plotly_chart(C.equity_curve(eq_df),   use_container_width=True, key=f"bt_{slug}_eq")
        st.plotly_chart(C.drawdown_chart(eq_df), use_container_width=True, key=f"bt_{slug}_dd")
        if len(eq_df) > 65:
            st.plotly_chart(C.rolling_sharpe(eq_df), use_container_width=True, key=f"bt_{slug}_rs")

    if not trades.empty:
        with st.expander("Trade Analysis", expanded=False):
            tr1, tr2 = st.columns(2)
            with tr1: st.plotly_chart(C.win_loss_pie(trades),    use_container_width=True, key=f"bt_{slug}_wl")
            with tr2: st.plotly_chart(C.exit_reason_pie(trades), use_container_width=True, key=f"bt_{slug}_er")
            st.plotly_chart(C.trade_pnl_scatter(trades),  use_container_width=True, key=f"bt_{slug}_pnl_sc")
            st.plotly_chart(C.pnl_histogram(trades),      use_container_width=True, key=f"bt_{slug}_pnl_hist")
            if len(eq_df) > 30:
                st.plotly_chart(C.monthly_returns_heatmap(eq_df), use_container_width=True, key=f"bt_{slug}_mr")



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
        with g1: st.plotly_chart(C.signal_gauge(proba),  use_container_width=True, key=f"live_{slug}_gauge")
        with g2: st.plotly_chart(C.proba_bar(proba),     use_container_width=True, key=f"live_{slug}_proba")
        st.markdown("---")
        st.plotly_chart(C.live_portfolio_line(signals_df),  use_container_width=True, key=f"live_{slug}_port")
        p1, p2 = st.columns(2)
        with p1: st.plotly_chart(C.cumulative_pnl_line(signals_df), use_container_width=True, key=f"live_{slug}_cpnl")
        with p2: st.plotly_chart(C.live_pnl_bars(signals_df),       use_container_width=True, key=f"live_{slug}_pnlb")
        st.markdown("---")
        st.plotly_chart(C.signal_timeline(signals_df),              use_container_width=True, key=f"live_{slug}_tl")
        sa1, sa2 = st.columns(2)
        with sa1: st.plotly_chart(C.vix_vs_confidence_scatter(signals_df), use_container_width=True, key=f"live_{slug}_vix")
        with sa2: st.plotly_chart(C.spread_type_pie(signals_df),           use_container_width=True, key=f"live_{slug}_pie")

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
                use_container_width=True, column_config=col_cfg, hide_index=True,
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
            use_container_width=True,
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
                use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN LAYOUT — dynamic strategy tabs + generic tabs
# ══════════════════════════════════════════════════════════════════════════════

if not selected:
    st.markdown(
        """<div style="text-align:center;padding:80px 0;color:#78909c">
          <div style="font-size:3rem">📈</div>
          <div style="font-size:1.3rem;margin-top:12px">Select strategies from the sidebar to get started.</div>
        </div>""", unsafe_allow_html=True,
    )
else:
    # Build tab list
    strat_tab_names   = [f"{_meta(s).get('icon','📌')} {_meta(s)['display_name']}" for s in selected]
    generic_tab_names = ["📦 Portfolio", "🛡 Risk", "📡 Market Data", "🗂 Registry"]
    all_tabs          = st.tabs(strat_tab_names + generic_tab_names)

    strategy_tabs = all_tabs[:len(selected)]
    tab_portfolio, tab_risk, tab_market, tab_registry = all_tabs[len(selected):]

    # ── Per-strategy tabs ─────────────────────────────────────────────────────
    for slug, stab in zip(selected, strategy_tabs):
        meta = _meta(slug)
        with stab:
            # Build inner sub-tab list based on capabilities
            inner_names = []
            if _cap(slug, "requires_training"):
                inner_names.append("🧠 Train")
            inner_names += ["📊 Backtest", "🔴 Live"]

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

    # ── Portfolio ─────────────────────────────────────────────────────────────
    with tab_portfolio:
        from alan_trader.dashboard.tabs.portfolio_overview import render as render_portfolio
        from alan_trader.visualization import charts as C

        _results = list(st.session_state["bt_results"].values())
        _report  = st.session_state["bt_report"]
        _roll_w  = st.session_state["bt_rolling_w"]

        _store = st.session_state.get("portfolio_store")
        if _store is None:
            try:
                from alan_trader.portfolio.store import PortfolioStore
                _store = PortfolioStore()
                if _store.load():
                    st.session_state["portfolio_store"] = _store
                else:
                    _store = None
            except Exception:
                _store = None

        if not _results:
            st.info("Run at least one **Backtest** to populate the Portfolio tab.")
        else:
            if not _roll_w.empty and _report:
                _report["rolling_weights"] = _roll_w
            render_portfolio(_report, _results, store=_store)
            if not _roll_w.empty:
                st.markdown("---")
                st.subheader("Portfolio Allocation Over Time")
                st.plotly_chart(C.portfolio_allocation_area(_roll_w), use_container_width=True)

    # ── Risk ──────────────────────────────────────────────────────────────────
    with tab_risk:
        from alan_trader.dashboard.tabs.risk_management import render as render_risk
        _results = list(st.session_state["bt_results"].values())
        _report  = st.session_state["bt_report"]
        if not _results:
            st.info("Run at least one **Backtest** to populate the Risk tab.")
        else:
            render_risk(_report, _results)

    # ── Market Data ───────────────────────────────────────────────────────────
    with tab_market:
        from alan_trader.dashboard.tabs.market_data import render as render_market
        mkt_ticker = _ticker_row("mkt")
        render_market(ticker=mkt_ticker, use_sim=use_sim,
                      api_key=st.session_state.get("polygon_api_key", ""))

    # ── Strategy Registry ─────────────────────────────────────────────────────
    with tab_registry:
        from alan_trader.dashboard.tabs.strategy_selector import render as render_selector
        bt_results_dict = st.session_state["bt_results"]
        render_selector(bt_results_dict, list(bt_results_dict.keys()))
