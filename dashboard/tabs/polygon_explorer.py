"""
Polygon.io API Explorer — interactive playground for all major endpoints.
"""

import json
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from alan_trader.data.polygon_client import PolygonClient


def _client(api_key: str) -> PolygonClient | None:
    try:
        return PolygonClient(api_key=api_key)
    except Exception as e:
        st.error(str(e))
        return None


def _raw(data):
    with st.expander("Raw JSON", expanded=False):
        st.code(json.dumps(data, indent=2, default=str), language="json")


def render(api_key: str = ""):
    st.markdown("## 🔭 Polygon.io API Explorer")

    # ── API Key ───────────────────────────────────────────────────────────────
    api_key = st.session_state.get("polygon_api_key", "")
    if not api_key:
        st.info("Enter your Polygon.io API key in the sidebar.")
    test_clicked = st.button("🔌 Test API key", disabled=not api_key, key="px_test_btn")
    if test_clicked:
        try:
            c_test = PolygonClient(api_key=api_key)
            snap = c_test._get("/v2/snapshot/locale/us/markets/stocks/tickers/SPY")
            if snap.get("ticker"):
                price = snap["ticker"].get("day", {}).get("c") or snap["ticker"].get("lastTrade", {}).get("p")
                st.success(f"✅ Connected — SPY ${price:.2f}" if price else "✅ Connected")
            else:
                st.error("❌ Key accepted but no data returned.")
        except Exception as e:
            st.error(f"❌ {e}")

    if not api_key:
        return

    st.markdown("---")
    ticker = st.text_input("Ticker", value="SPY", key="px_ticker").upper().strip()
    st.markdown("---")

    # ── 1. Market Snapshot ────────────────────────────────────────────────────
    with st.expander("📸 Market Snapshot", expanded=True):
        st.caption("Current price, daily OHLCV, and market stats.")
        if st.button("Fetch Snapshot", key="px_snap_btn"):
            c = _client(api_key)
            if c:
                try:
                    raw = c._get(f"/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}")
                    snap = raw.get("ticker", {})
                    day  = snap.get("day", {})
                    prev = snap.get("prevDay", {})
                    lq   = snap.get("lastQuote", {})
                    lt   = snap.get("lastTrade", {})

                    col1, col2, col3, col4, col5 = st.columns(5)
                    price   = lt.get("p") or day.get("c", 0)
                    chg_pct = snap.get("todaysChangePerc", 0)
                    col1.metric("Price",   f"${price:.2f}")
                    col2.metric("Change",  f"{chg_pct:+.2f}%")
                    col3.metric("Volume",  f"{int(day.get('v', 0)):,}")
                    col4.metric("Day High", f"${day.get('h', 0):.2f}")
                    col5.metric("Day Low",  f"${day.get('l', 0):.2f}")

                    st.dataframe(pd.DataFrame([{
                        "Open":         day.get("o"),
                        "High":         day.get("h"),
                        "Low":          day.get("l"),
                        "Close":        day.get("c"),
                        "VWAP":         day.get("vw"),
                        "Volume":       day.get("v"),
                        "Prev Close":   prev.get("c"),
                        "Bid":          lq.get("P"),
                        "Ask":          lq.get("P"),
                        "Last Trade":   lt.get("p"),
                    }]), width="stretch")
                    _raw(raw)
                except Exception as e:
                    st.error(f"Error: {e}")

    # ── 2. OHLCV Bars ─────────────────────────────────────────────────────────
    with st.expander("📊 OHLCV Bars (Aggregates)", expanded=False):
        st.caption("Historical price bars. Supports minute, hour, day timespans.")
        c1, c2, c3, c4 = st.columns(4)
        mult      = c1.number_input("Multiplier", 1, 60, 1, key="px_mult")
        timespan  = c2.selectbox("Timespan", ["minute", "hour", "day", "week", "month"], index=2, key="px_ts")
        from_date = c3.date_input("From", value=date.today() - timedelta(days=90), key="px_from")
        to_date   = c4.date_input("To",   value=date.today(), key="px_to")

        if st.button("Fetch Bars", key="px_bars_btn"):
            c = _client(api_key)
            if c:
                try:
                    with st.spinner("Fetching bars…"):
                        df = c.get_aggregates(
                            ticker, str(from_date), str(to_date),
                            timespan=timespan, multiplier=int(mult),
                        )
                    if df.empty:
                        st.warning("No data returned.")
                    else:
                        st.success(f"{len(df):,} bars returned.")
                        st.dataframe(df.tail(200).style.format("{:.4f}", subset=["open","high","low","close","vwap"]),
                                     width="stretch")
                        raw_url = f"/v2/aggs/ticker/{ticker}/range/{int(mult)}/{timespan}/{from_date}/{to_date}"
                        _raw(c._get(raw_url, {"adjusted": "true", "sort": "asc", "limit": 5}))
                except Exception as e:
                    st.error(f"Error: {e}")

    # ── 3. Technical Indicators ───────────────────────────────────────────────
    with st.expander("📈 Technical Indicators", expanded=False):
        st.caption("Polygon's built-in RSI, MACD, SMA, EMA.")
        c1, c2, c3, c4, c5 = st.columns(5)
        indicator  = c1.selectbox("Indicator", ["rsi", "macd", "sma", "ema"], key="px_ind")
        window     = c2.number_input("Window", 2, 200, 14, key="px_win")
        ind_span   = c3.selectbox("Timespan", ["day", "hour", "minute"], key="px_ind_ts")
        ind_from   = c4.date_input("From", value=date.today() - timedelta(days=180), key="px_ind_from")
        ind_to     = c5.date_input("To",   value=date.today(), key="px_ind_to")

        if st.button("Fetch Indicator", key="px_ind_btn"):
            c = _client(api_key)
            if c:
                try:
                    with st.spinner(f"Fetching {indicator.upper()}…"):
                        result = c.get_technical_indicator(
                            ticker, indicator,
                            str(ind_from), str(ind_to),
                            window=int(window), timespan=ind_span,
                        )
                    if isinstance(result, pd.DataFrame):
                        st.success(f"{len(result)} rows returned.")
                        st.dataframe(result.tail(100), width="stretch")
                    elif isinstance(result, pd.Series):
                        st.success(f"{len(result)} values returned.")
                        df_out = result.tail(100).reset_index()
                        df_out.columns = ["date", indicator.upper()]
                        st.dataframe(df_out, width="stretch")
                    else:
                        st.warning("No data returned.")
                    url = f"/v1/indicators/{indicator}/{ticker}"
                    params = {"timespan": ind_span, "window": window, "limit": 3,
                              "from": str(ind_from), "to": str(ind_to)}
                    _raw(c._get(url, params))
                except Exception as e:
                    st.error(f"Error: {e}")

    # ── 4. Options Expirations ────────────────────────────────────────────────
    with st.expander("📅 Options Expirations", expanded=False):
        st.caption("List all available expiration dates for the ticker.")
        if st.button("Fetch Expirations", key="px_exp_btn"):
            c = _client(api_key)
            if c:
                try:
                    with st.spinner("Fetching expirations…"):
                        exps = c.get_expirations(ticker, as_of=str(date.today()))
                    if not exps:
                        st.warning("No expirations found.")
                    else:
                        st.success(f"{len(exps)} expirations found.")
                        df_exp = pd.DataFrame({"Expiration": exps})
                        df_exp["DTE"] = (pd.to_datetime(df_exp["Expiration"]).dt.date
                                         .apply(lambda d: (d - date.today()).days))
                        st.dataframe(df_exp, width="stretch")
                        _raw({"expirations": exps})
                except Exception as e:
                    st.error(f"Error: {e}")

    # ── 5. Options Chain ──────────────────────────────────────────────────────
    with st.expander("🔗 Options Chain", expanded=False):
        st.caption("Full options chain — pick a real expiration from Polygon, then fetch strikes.")

        # Step 1: load available expirations
        if st.button("📅 Load Expirations", key="px_load_exp_btn"):
            c = _client(api_key)
            if c:
                try:
                    with st.spinner("Loading expirations…"):
                        exps = c.get_expirations(ticker, as_of=str(date.today()))
                    if exps:
                        st.session_state["px_expirations"] = exps
                        st.success(f"{len(exps)} expirations available — select one below.")
                    else:
                        st.warning("No expirations found for this ticker.")
                        st.session_state["px_expirations"] = []
                except Exception as e:
                    st.error(f"Error loading expirations: {e}")

        exps_available = st.session_state.get("px_expirations", [])

        # Historical mode toggle
        use_hist = st.checkbox("📆 Historical snapshot (EOD data)", value=False, key="px_chain_hist_mode",
                               help="Fetch EOD snapshot for a past date. Prices come from day.vwap/close — bid/ask will be estimated.")
        if use_hist:
            snap_date_input = st.date_input("Snapshot date", value=date.today() - timedelta(days=5),
                                             max_value=date.today() - timedelta(days=1), key="px_chain_snap_date")
            st.caption("ℹ️ Historical snapshots return IV + greeks. Bid/Ask are estimated from day.vwap (Polygon doesn't backfill live quotes).")
        else:
            snap_date_input = None

        c1, c2, c3 = st.columns(3)
        if exps_available:
            exp_input = c1.selectbox("Expiration", exps_available, key="px_chain_exp_sel")
        else:
            exp_input = c1.text_input("Expiration (YYYY-MM-DD) — or click Load Expirations above",
                                       value=str(date.today() + timedelta(days=30)), key="px_chain_exp")
        chain_type  = c2.selectbox("Contract type", ["all", "call", "put"], key="px_chain_type")
        strike_pct  = c3.slider("Strike range (% of spot)", 50, 150, (80, 120), key="px_chain_strike_pct")

        if st.button("Fetch Chain", key="px_chain_btn"):
            c = _client(api_key)
            if c:
                try:
                    # Get spot price — try multiple sources with fallbacks
                    spot = 0.0
                    if snap_date_input:
                        # Historical: use daily bar close
                        agg = c.get_aggregates(ticker, str(snap_date_input), str(snap_date_input))
                        if not agg.empty:
                            spot = float(agg["close"].iloc[0])
                        if not spot:
                            # Try previous trading day
                            prev = (date.fromisoformat(str(snap_date_input)) - timedelta(days=5))
                            agg2 = c.get_aggregates(ticker, str(prev), str(snap_date_input))
                            if not agg2.empty:
                                spot = float(agg2["close"].iloc[-1])
                    else:
                        snap_data = c._get(f"/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}")
                        t = snap_data.get("ticker", {})
                        spot = (t.get("lastTrade", {}).get("p") or
                                t.get("day",        {}).get("c") or
                                t.get("day",        {}).get("vw") or
                                t.get("prevDay",    {}).get("c") or 0)
                        spot = float(spot)
                    if not spot:
                        st.warning(f"⚠️ Could not fetch spot price for **{ticker}** — ATM line and strike filter disabled. Check ticker or try a different date.")

                    params = {"expiration_date": str(exp_input), "limit": 250}
                    if snap_date_input:
                        params["date"] = str(snap_date_input)
                    if spot:
                        params["strike_price.gte"] = round(spot * strike_pct[0] / 100, 2)
                        params["strike_price.lte"] = round(spot * strike_pct[1] / 100, 2)
                    if chain_type != "all":
                        params["contract_type"] = chain_type

                    results, url = [], f"/v3/snapshot/options/{ticker}"
                    with st.spinner("Fetching options chain…"):
                        while url:
                            data = c._get(url, params)
                            results.extend(data.get("results", []))
                            next_url = (data.get("next_url") or "").replace(c.BASE, "")
                            url = next_url or None
                            params = {}

                    if not results:
                        if snap_date_input:
                            st.warning(
                                f"No contracts returned for snapshot **{snap_date_input}** / expiry **{exp_input}**. "
                                "The expiration must be in the future relative to the snapshot date. "
                                "Also check your Polygon plan — historical options require Starter or above."
                            )
                        else:
                            st.warning(
                                f"No contracts returned for expiration **{exp_input}**. "
                                "Options only exist on valid expiration dates (usually Fridays). "
                                "Click **Load Expirations** above to see available dates."
                            )
                    else:
                        import plotly.graph_objects as go
                        rows = []
                        for r in results:
                            d  = r.get("details", {})
                            g  = r.get("greeks", {}) or {}
                            lq = r.get("last_quote", {}) or {}
                            dy = r.get("day", {}) or {}
                            bid = lq.get("bid")
                            ask = lq.get("ask")
                            if bid is None and ask is None:
                                mid_proxy = dy.get("vwap") or dy.get("close")
                                if mid_proxy:
                                    spread = max(0.01, float(mid_proxy) * 0.02)
                                    bid = float(mid_proxy) - spread / 2
                                    ask = float(mid_proxy) + spread / 2
                            mid = round(((bid or 0) + (ask or 0)) / 2, 3)
                            rows.append({
                                "Strike":  d.get("strike_price"),
                                "Type":    d.get("contract_type", "").upper()[:1],
                                "Bid":     round(bid, 3) if bid else None,
                                "Ask":     round(ask, 3) if ask else None,
                                "Mid":     mid,
                                "Spread":  round((ask or 0) - (bid or 0), 3),
                                "IV %":    round((r.get("implied_volatility") or 0) * 100, 1),
                                "Delta":   round(g.get("delta") or 0, 4),
                                "Gamma":   round(g.get("gamma") or 0, 6),
                                "Theta":   round(g.get("theta") or 0, 4),
                                "Vega":    round(g.get("vega") or 0, 4),
                                "OI":      r.get("open_interest") or 0,
                                "Volume":  dy.get("volume") or 0,
                            })
                        df_chain = pd.DataFrame(rows).sort_values(["Strike", "Type"])

                        # ── Summary stats ──────────────────────────────────────────
                        calls = df_chain[df_chain["Type"] == "C"]
                        puts  = df_chain[df_chain["Type"] == "P"]
                        total_call_oi = int(calls["OI"].sum())
                        total_put_oi  = int(puts["OI"].sum())
                        pc_ratio      = round(total_put_oi / max(total_call_oi, 1), 2)
                        dte_days      = (date.fromisoformat(str(exp_input)) - date.today()).days

                        # ATM IV (nearest strike to spot for calls & puts)
                        atm_call_iv = atm_put_iv = None
                        if spot:
                            atm_c = calls.iloc[(calls["Strike"] - spot).abs().argsort()[:1]]
                            atm_p = puts.iloc[(puts["Strike"]  - spot).abs().argsort()[:1]]
                            atm_call_iv = atm_c["IV %"].values[0] if not atm_c.empty else None
                            atm_put_iv  = atm_p["IV %"].values[0] if not atm_p.empty else None

                        # Max pain: strike where total OI-weighted loss is minimized
                        all_strikes = sorted(df_chain["Strike"].dropna().unique())
                        max_pain_strike = None
                        if all_strikes and spot:
                            min_pain, best_k = float("inf"), all_strikes[0]
                            for k in all_strikes:
                                pain = (
                                    calls[calls["Strike"] < k]["OI"].sum() * (k - calls[calls["Strike"] < k]["Strike"]).mean()
                                    + puts[puts["Strike"] > k]["OI"].sum() * (puts[puts["Strike"] > k]["Strike"].mean() - k)
                                )
                                if pain < min_pain:
                                    min_pain, best_k = pain, k
                            max_pain_strike = best_k

                        spot_str = f"${spot:.2f}" if spot else "N/A"
                        mode_badge = f"📆 EOD {snap_date_input}" if snap_date_input else "🔴 Live"
                        st.caption(f"{mode_badge} — {len(rows)} contracts — expiry {exp_input} — spot used for ATM line: **{spot_str}**")
                        c1, c2, c3, c4, c5 = st.columns(5)
                        c1.metric("Spot", spot_str, help="Price used for ATM line and strike filter. If wrong, spot fetch failed — try Historical mode with a specific date.")
                        c2.metric("DTE", dte_days)
                        c3.metric("P/C OI Ratio", pc_ratio,
                                  help="Put OI ÷ Call OI — >1 means more put hedging")
                        c4.metric("ATM IV (Call/Put)",
                                  f"{atm_call_iv:.1f}% / {atm_put_iv:.1f}%" if atm_call_iv else "—")
                        c5.metric("Max Pain", f"${max_pain_strike}" if max_pain_strike else "—",
                                  help="Strike where total option-holder loss is minimized at expiry")

                        # ── Charts ─────────────────────────────────────────────────
                        tab_smile, tab_oi, tab_table = st.tabs(["📈 IV Smile", "📊 OI by Strike", "📋 Full Chain"])

                        with tab_smile:
                            if not calls.empty or not puts.empty:
                                fig = go.Figure()
                                if not calls.empty:
                                    fig.add_trace(go.Scatter(
                                        x=calls["Strike"], y=calls["IV %"],
                                        mode="lines+markers", name="Call IV",
                                        line=dict(color="#00cc96", width=2),
                                        marker=dict(size=5),
                                    ))
                                if not puts.empty:
                                    fig.add_trace(go.Scatter(
                                        x=puts["Strike"], y=puts["IV %"],
                                        mode="lines+markers", name="Put IV",
                                        line=dict(color="#ef553b", width=2),
                                        marker=dict(size=5),
                                    ))
                                if spot:
                                    fig.add_vline(x=spot, line_dash="dash",
                                                  line_color="white", opacity=0.6,
                                                  annotation_text=f"  spot ${spot:.2f}",
                                                  annotation_font_color="white")
                                fig.update_layout(
                                    title=f"IV Smile — {ticker} exp {exp_input}",
                                    xaxis_title="Strike", yaxis_title="IV %",
                                    height=350, template="plotly_dark",
                                    legend=dict(orientation="h", y=1.1),
                                    margin=dict(l=40, r=20, t=60, b=40),
                                )
                                st.plotly_chart(fig, width="stretch")

                        with tab_oi:
                            fig2 = go.Figure()
                            if not calls.empty:
                                fig2.add_trace(go.Bar(
                                    x=calls["Strike"], y=calls["OI"],
                                    name="Call OI", marker_color="#00cc96", opacity=0.75,
                                ))
                            if not puts.empty:
                                fig2.add_trace(go.Bar(
                                    x=puts["Strike"], y=puts["OI"],
                                    name="Put OI", marker_color="#ef553b", opacity=0.75,
                                ))
                            if spot:
                                fig2.add_vline(x=spot, line_dash="dash",
                                               line_color="white", opacity=0.6,
                                               annotation_text=f"  spot ${spot:.2f}",
                                               annotation_font_color="white")
                            if max_pain_strike:
                                fig2.add_vline(x=max_pain_strike, line_dash="dot",
                                               line_color="gold", opacity=0.8,
                                               annotation_text=f"  max pain ${max_pain_strike}",
                                               annotation_font_color="gold")
                            fig2.update_layout(
                                title=f"Open Interest by Strike — {ticker} exp {exp_input}",
                                xaxis_title="Strike", yaxis_title="Open Interest",
                                barmode="overlay", height=350, template="plotly_dark",
                                legend=dict(orientation="h", y=1.1),
                                margin=dict(l=40, r=20, t=60, b=40),
                            )
                            st.plotly_chart(fig2, width="stretch")

                        with tab_table:
                            # Highlight ATM rows
                            def _highlight_atm(row):
                                if spot and abs(row["Strike"] - spot) / spot < 0.01:
                                    return ["background-color: #1a3a5c"] * len(row)
                                return [""] * len(row)
                            st.caption(f"{len(df_chain)} contracts — ATM rows highlighted in blue")
                            st.dataframe(
                                df_chain.style.apply(_highlight_atm, axis=1)
                                        .format({"IV %": "{:.1f}", "Delta": "{:.4f}",
                                                 "Gamma": "{:.5f}", "Theta": "{:.4f}",
                                                 "Vega": "{:.4f}", "Mid": "{:.3f}",
                                                 "Spread": "{:.3f}"},
                                                na_rep="—"),
                                width="stretch", height=450,
                            )
                        _raw({"results_count": len(results), "first_result": results[0] if results else {}})
                except Exception as e:
                    st.error(f"Error: {e}")

    # ── 6. Ticker Details ─────────────────────────────────────────────────────
    with st.expander("🏢 Ticker Details", expanded=False):
        st.caption("Company info — description, market cap, shares outstanding, SIC code.")
        if st.button("Fetch Details", key="px_details_btn"):
            c = _client(api_key)
            if c:
                try:
                    raw = c._get(f"/v3/reference/tickers/{ticker}")
                    res = raw.get("results", {})
                    info = {
                        "Name":          res.get("name"),
                        "Ticker":        res.get("ticker"),
                        "Market":        res.get("market"),
                        "Exchange":      res.get("primary_exchange"),
                        "Currency":      res.get("currency_name"),
                        "Market Cap":    res.get("market_cap"),
                        "Shares Out.":   res.get("share_class_shares_outstanding"),
                        "Employees":     res.get("total_employees"),
                        "SIC":           res.get("sic_code"),
                        "SIC Desc":      res.get("sic_description"),
                        "Homepage":      res.get("homepage_url"),
                    }
                    df_info = pd.DataFrame([info]).T.rename(columns={0: "Value"})
                    df_info["Value"] = df_info["Value"].astype(str)
                    st.dataframe(df_info, width="stretch")
                    desc = res.get("description", "")
                    if desc:
                        st.markdown(f"> {desc[:600]}{'…' if len(desc) > 600 else ''}")
                    _raw(raw)
                except Exception as e:
                    st.error(f"Error: {e}")

    # ── 7. News ───────────────────────────────────────────────────────────────
    with st.expander("📰 News", expanded=False):
        st.caption("Recent news articles tagged to the ticker.")
        c1, c2, c3 = st.columns(3)
        news_from  = c1.date_input("From", value=date.today() - timedelta(days=14), key="px_news_from")
        news_to    = c2.date_input("To",   value=date.today(), key="px_news_to")
        news_limit = c3.number_input("Max articles", 5, 100, 20, key="px_news_lim")

        if st.button("Fetch News", key="px_news_btn"):
            c = _client(api_key)
            if c:
                try:
                    with st.spinner("Fetching news…"):
                        df_news = c.get_news(ticker, str(news_from), str(news_to), limit=int(news_limit))
                    if df_news.empty:
                        st.warning("No news found.")
                    else:
                        st.success(f"{len(df_news)} articles found.")
                        for _, row in df_news.head(int(news_limit)).iterrows():
                            st.markdown(f"**{row.get('date', '')}** — {row.get('title', '')}")
                            desc = row.get("description", "")
                            if desc:
                                st.caption(str(desc)[:200])
                            st.markdown("---")
                except Exception as e:
                    st.error(f"Error: {e}")

    # ── 8. EPS Financials (plan test) ─────────────────────────────────────────
    with st.expander("💰 EPS Financials (plan test)", expanded=False):
        st.caption(
            "Fetches filed EPS actuals via `/vX/reference/financials`. "
            "If your plan includes analyst **estimates**, they will appear under `eps_estimate` — "
            "otherwise only `eps_actual` (filed) will be populated."
        )
        c1, c2 = st.columns(2)
        fin_timeframe = c1.selectbox("Timeframe", ["quarterly", "annual"], key="px_fin_tf")
        fin_limit     = c2.number_input("Periods", 1, 20, 8, key="px_fin_limit")

        if st.button("Fetch Financials", key="px_fin_btn"):
            c = _client(api_key)
            if c:
                try:
                    with st.spinner("Fetching financials…"):
                        raw = c._get("/vX/reference/financials", {
                            "ticker":    ticker,
                            "timeframe": fin_timeframe,
                            "order":     "desc",
                            "limit":     int(fin_limit),
                        })
                    results = raw.get("results", [])
                    if not results:
                        st.warning("No financials returned — ticker may not have data or plan may not include this endpoint.")
                    else:
                        rows = []
                        for r in results:
                            fi     = r.get("financials", {})
                            inc    = fi.get("income_statement", {})
                            eps_a  = inc.get("basic_earnings_per_share", {}).get("value")
                            # Polygon does not expose consensus estimates in vX/reference/financials.
                            # Check if any estimate field exists in the raw response.
                            eps_e  = r.get("eps_estimate") or r.get("estimated_eps") or r.get("consensus_eps")
                            rev    = inc.get("revenues", {}).get("value")
                            net    = inc.get("net_income_loss", {}).get("value")
                            rows.append({
                                "Period":       r.get("fiscal_period"),
                                "Fiscal Year":  r.get("fiscal_year"),
                                "Filed Date":   r.get("filing_date"),
                                "Period End":   r.get("end_date"),
                                "EPS Actual":   round(eps_a, 4) if eps_a is not None else None,
                                "EPS Estimate": round(eps_e, 4) if eps_e is not None else "— (not in plan)",
                                "Revenue":      f"${rev/1e9:.2f}B" if rev else None,
                                "Net Income":   f"${net/1e9:.2f}B" if net else None,
                            })

                        df_fin = pd.DataFrame(rows)
                        has_estimates = any(r.get("eps_estimate") or r.get("estimated_eps") or r.get("consensus_eps")
                                            for r in results)
                        if has_estimates:
                            st.success("✅ Your plan includes EPS estimates — earnings_post_drift can be wired up.")
                        else:
                            st.warning(
                                "⚠️ No EPS estimates found in response. "
                                "Polygon's standard financials endpoint only returns filed actuals. "
                                "Consensus estimates require a higher-tier plan or separate data provider."
                            )

                        st.dataframe(df_fin, width="stretch")
                        _raw(raw)
                except Exception as e:
                    st.error(f"Error: {e}")

    # ── 9. Raw API Call ───────────────────────────────────────────────────────
    with st.expander("🛠 Raw API Call", expanded=False):
        st.caption("Call any Polygon endpoint directly. Params as JSON.")
        raw_path   = st.text_input("Endpoint path", value=f"/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}",
                                    key="px_raw_path")
        raw_params = st.text_area("Params (JSON)", value="{}", height=80, key="px_raw_params")

        if st.button("Call API", key="px_raw_btn"):
            c = _client(api_key)
            if c:
                try:
                    params = json.loads(raw_params)
                    with st.spinner("Calling…"):
                        result = c._get(raw_path, params)
                    st.success("Response received.")
                    st.code(json.dumps(result, indent=2, default=str), language="json")
                except json.JSONDecodeError:
                    st.error("Invalid JSON in params field.")
                except Exception as e:
                    st.error(f"Error: {e}")
