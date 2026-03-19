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
        st.caption("Full options chain for a specific expiration — strike, bid/ask, IV, Greeks.")
        c1, c2, c3 = st.columns(3)
        exp_input   = c1.text_input("Expiration (YYYY-MM-DD)", value=str(date.today() + timedelta(days=30)),
                                     key="px_chain_exp")
        chain_type  = c2.selectbox("Contract type", ["all", "call", "put"], key="px_chain_type")
        strike_pct  = c3.slider("Strike range (% of spot)", 50, 150, (80, 120), key="px_chain_strike_pct")

        if st.button("Fetch Chain", key="px_chain_btn"):
            c = _client(api_key)
            if c:
                try:
                    # First get spot price
                    snap = c._get(f"/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}")
                    spot = snap.get("ticker", {}).get("lastTrade", {}).get("p", 0) or \
                           snap.get("ticker", {}).get("day", {}).get("c", 0)

                    params = {"expiration_date": exp_input, "limit": 250}
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
                        st.warning("No contracts returned.")
                    else:
                        rows = []
                        for r in results:
                            d = r.get("details", {})
                            g = r.get("greeks", {})
                            rows.append({
                                "Strike":  d.get("strike_price"),
                                "Type":    d.get("contract_type", "").upper()[:1],
                                "Exp":     d.get("expiration_date"),
                                "Bid":     r.get("last_quote", {}).get("bid"),
                                "Ask":     r.get("last_quote", {}).get("ask"),
                                "Mid":     round(((r.get("last_quote", {}).get("bid") or 0) +
                                                  (r.get("last_quote", {}).get("ask") or 0)) / 2, 3),
                                "IV":      round((r.get("implied_volatility") or 0) * 100, 2),
                                "Delta":   round(g.get("delta") or 0, 4),
                                "Gamma":   round(g.get("gamma") or 0, 6),
                                "Theta":   round(g.get("theta") or 0, 4),
                                "Vega":    round(g.get("vega") or 0, 4),
                                "OI":      r.get("open_interest"),
                                "Volume":  r.get("day", {}).get("volume"),
                            })
                        df_chain = pd.DataFrame(rows).sort_values(["Strike", "Type"])
                        if spot:
                            st.caption(f"Spot: **${spot:.2f}** — {len(df_chain)} contracts")
                        st.dataframe(df_chain, width="stretch", height=400)
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

    # ── 8. Raw API Call ───────────────────────────────────────────────────────
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
