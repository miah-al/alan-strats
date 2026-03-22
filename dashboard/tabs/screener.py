"""
Stock Screener tab — Liquidity, Daily Movers, Options Flow, Technicals.
Data source: Polygon.io (requires API key).
"""

import math
import time
import datetime
import logging

import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import streamlit.column_config as cc

logger = logging.getLogger(__name__)


# ── Predefined universes ──────────────────────────────────────────────────────

UNIVERSES: dict[str, list[str]] = {
    "Mag 7":        ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"],
    "Big Tech":     ["AAPL", "MSFT", "NVDA", "META", "GOOGL", "AMZN", "TSLA",
                     "AMD", "INTC", "ORCL", "CRM", "ADBE", "NFLX", "QCOM", "AVGO"],
    "Financials":   ["JPM", "BAC", "GS", "MS", "WFC", "C", "BLK", "V", "MA",
                     "AXP", "SCHW", "USB", "PNC", "COF"],
    "Energy":       ["XOM", "CVX", "COP", "EOG", "SLB", "MPC", "PSX", "OXY", "HAL"],
    "ETFs":         ["SPY", "QQQ", "IWM", "GLD", "TLT", "VXX", "UVXY",
                     "XLF", "XLK", "XLE", "XLV", "XLI", "ARKK", "SQQQ", "TQQQ"],
    "Retail / Meme":["HOOD", "PLTR", "SOFI", "COIN", "RIVN", "LCID", "GME", "AMC",
                     "MSTR", "RKLB", "IONQ", "SOUN"],
    "Large Cap 50": ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA",
                     "BRK.B", "JPM", "V", "UNH", "XOM", "MA", "JNJ", "PG",
                     "HD", "COST", "MRK", "ABBV", "WMT", "CVX", "LLY", "KO",
                     "PEP", "AVGO", "ORCL", "ACN", "BAC", "TMO", "CSCO",
                     "ABT", "CRM", "MCD", "DHR", "WFC", "ADBE", "NKE", "TXN",
                     "NFLX", "QCOM", "PM", "INTC", "AMD", "AMGN", "CAT", "RTX",
                     "LOW", "GS", "IBM", "SPGI"],
}


# ── Polygon helpers ───────────────────────────────────────────────────────────

def _batch_snapshot(tickers: list[str], api_key: str) -> pd.DataFrame:
    """Fetch snapshots for up to 250 tickers in a single Polygon call."""
    from alan_trader.data.polygon_client import PolygonClient
    c = PolygonClient(api_key=api_key)
    chunk_size = 200
    rows = []
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i: i + chunk_size]
        try:
            data = c._get(
                "/v2/snapshot/locale/us/markets/stocks/tickers",
                {"tickers": ",".join(chunk)},
            )
            for snap in data.get("tickers", []):
                day   = snap.get("day",     {})
                prev  = snap.get("prevDay", {})
                rows.append({
                    "Ticker":      snap.get("ticker", ""),
                    "Price":       day.get("c") or snap.get("lastTrade", {}).get("p") or 0,
                    "Change%":     snap.get("todaysChangePerc", 0),
                    "Change$":     snap.get("todaysChange", 0),
                    "Volume":      day.get("v") or 0,
                    "DollarVol":   (day.get("v") or 0) * (day.get("c") or 0),
                    "Open":        day.get("o") or 0,
                    "High":        day.get("h") or 0,
                    "Low":         day.get("l") or 0,
                    "VWAP":        day.get("vw") or 0,
                    "PrevClose":   prev.get("c") or 0,
                    "PrevVolume":  prev.get("v") or 1,
                    "Gap%":        (((day.get("o") or 0) / (prev.get("c") or 1)) - 1) * 100
                                   if prev.get("c") else 0,
                })
        except Exception as e:
            logger.warning(f"Batch snapshot error: {e}")
        if i + chunk_size < len(tickers):
            time.sleep(0.25)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["RelVol"] = (df["Volume"] / df["PrevVolume"].replace(0, 1)).round(2)
    return df


def _fetch_movers(api_key: str, direction: str = "gainers") -> pd.DataFrame:
    from alan_trader.data.polygon_client import PolygonClient
    c = PolygonClient(api_key=api_key)
    try:
        data = c._get(f"/v2/snapshot/locale/us/markets/stocks/{direction}")
        rows = []
        for snap in data.get("tickers", []):
            day  = snap.get("day", {})
            prev = snap.get("prevDay", {})
            rows.append({
                "Ticker":    snap.get("ticker", ""),
                "Price":     day.get("c") or 0,
                "Change%":   snap.get("todaysChangePerc", 0),
                "Change$":   snap.get("todaysChange", 0),
                "Volume":    day.get("v") or 0,
                "DollarVol": (day.get("v") or 0) * (day.get("c") or 0),
                "PrevVolume":prev.get("v") or 1,
            })
        df = pd.DataFrame(rows)
        if not df.empty:
            df["RelVol"] = (df["Volume"] / df["PrevVolume"].replace(0, 1)).round(2)
        return df
    except Exception as e:
        logger.warning(f"Movers fetch error: {e}")
        return pd.DataFrame()


def _fetch_options_flow(tickers: list[str], api_key: str,
                        prog_bar=None) -> pd.DataFrame:
    """For each ticker fetch P/C OI ratio, P/C volume ratio, avg IV."""
    from alan_trader.data.polygon_client import PolygonClient
    c = PolygonClient(api_key=api_key)
    rows = []
    for i, ticker in enumerate(tickers):
        if prog_bar:
            prog_bar.progress((i + 1) / len(tickers), text=f"Options: {ticker}")
        try:
            chain = c.get_options_chain(ticker)
            if chain.empty:
                continue
            calls = chain[chain["type"] == "call"]
            puts  = chain[chain["type"] == "put"]

            call_oi  = calls["open_interest"].fillna(0).sum()
            put_oi   = puts["open_interest"].fillna(0).sum()
            call_vol = calls["volume"].fillna(0).sum()
            put_vol  = puts["volume"].fillna(0).sum()
            avg_iv   = chain["iv"].dropna().mean()

            # ATM IV: contracts with lowest |delta - 0.5|
            atm = chain[chain["delta"].notna()].copy()
            if not atm.empty:
                atm["atm_dist"] = (atm["delta"].abs() - 0.5).abs()
                atm_iv = atm.nsmallest(4, "atm_dist")["iv"].mean()
            else:
                atm_iv = avg_iv

            rows.append({
                "Ticker":       ticker,
                "PC_OI":        round(put_oi  / call_oi,  2) if call_oi  > 0 else None,
                "PC_Vol":       round(put_vol / call_vol, 2) if call_vol > 0 else None,
                "AvgIV%":       round((avg_iv or 0) * 100, 1),
                "ATM_IV%":      round((atm_iv or 0) * 100, 1),
                "CallOI":       int(call_oi),
                "PutOI":        int(put_oi),
                "CallVol":      int(call_vol),
                "PutVol":       int(put_vol),
            })
        except Exception as e:
            logger.debug(f"Options flow {ticker}: {e}")
        time.sleep(0.15)  # rate limit

    return pd.DataFrame(rows) if rows else pd.DataFrame()


def _fetch_rsi(tickers: list[str], api_key: str, prog_bar=None) -> pd.DataFrame:
    from alan_trader.data.polygon_client import PolygonClient
    c = PolygonClient(api_key=api_key)
    today = datetime.date.today().isoformat()
    month_ago = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
    rows = []
    for i, ticker in enumerate(tickers):
        if prog_bar:
            prog_bar.progress((i + 1) / len(tickers), text=f"RSI: {ticker}")
        try:
            rsi = c.get_technical_indicator(ticker, "rsi", month_ago, today, window=14)
            sma50 = c.get_technical_indicator(ticker, "sma", month_ago, today, window=50)
            sma200 = c.get_technical_indicator(ticker, "sma", month_ago, today, window=200)
            rows.append({
                "Ticker":    ticker,
                "RSI":       round(float(rsi.iloc[-1]), 1) if not rsi.empty else None,
                "SMA50":     round(float(sma50.iloc[-1]), 2) if not sma50.empty else None,
                "SMA200":    round(float(sma200.iloc[-1]), 2) if not sma200.empty else None,
            })
        except Exception as e:
            logger.debug(f"RSI {ticker}: {e}")
        time.sleep(0.15)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


# ── Chart helpers ─────────────────────────────────────────────────────────────

def _movers_chart(df: pd.DataFrame, n: int = 10) -> go.Figure:
    top = df.nlargest(n // 2, "Change%")
    bot = df.nsmallest(n // 2, "Change%")
    combined = pd.concat([bot, top]).sort_values("Change%")
    colors = ["#4caf50" if v >= 0 else "#ef5350" for v in combined["Change%"]]
    fig = go.Figure(go.Bar(
        x=combined["Change%"],
        y=combined["Ticker"],
        orientation="h",
        marker_color=colors,
        text=[f"{v:+.2f}%" for v in combined["Change%"]],
        textposition="outside",
    ))
    fig.update_layout(
        title=f"Top {n // 2} Gainers / Losers", height=max(300, n * 30),
        paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
        font=dict(color="#b0b8c8"),
        xaxis=dict(gridcolor="#1e2130", title="Change %"),
        margin=dict(l=0, r=60, t=36, b=0),
    )
    return fig


def _pc_chart(opts_df: pd.DataFrame) -> go.Figure:
    df = opts_df.dropna(subset=["PC_OI"]).sort_values("PC_OI", ascending=True)
    colors = ["#ef5350" if v > 1.2 else ("#4caf50" if v < 0.8 else "#ffb300")
              for v in df["PC_OI"]]
    fig = go.Figure(go.Bar(
        x=df["PC_OI"], y=df["Ticker"],
        orientation="h", marker_color=colors,
        text=[f"{v:.2f}" for v in df["PC_OI"]], textposition="outside",
    ))
    fig.add_vline(x=1.0, line=dict(color="#546e7a", dash="dot", width=1))
    fig.update_layout(
        title="Put/Call OI Ratio  (>1.0 = bearish skew)", height=max(280, len(df) * 28),
        paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
        font=dict(color="#b0b8c8"),
        xaxis=dict(gridcolor="#1e2130", title="P/C OI"),
        margin=dict(l=0, r=60, t=36, b=0),
    )
    return fig


# ── Main render ───────────────────────────────────────────────────────────────

def render(api_key: str = "") -> None:
    st.markdown("## Stock Screener")

    if not api_key:
        st.warning("Enter your Polygon API key in the sidebar to use live data.")
        return

    # ── Universe picker ───────────────────────────────────────────────────────
    st.markdown("### Universe")
    u_col1, u_col2 = st.columns([2, 5])
    universe_choice = u_col1.selectbox(
        "Predefined list", ["Custom"] + list(UNIVERSES.keys()),
        key="sc_universe",
    )
    if universe_choice == "Custom":
        custom_input = u_col2.text_input(
            "Tickers (comma-separated)", value="AAPL,MSFT,NVDA,META,TSLA",
            key="sc_custom_tickers",
        )
        tickers = [t.strip().upper() for t in custom_input.split(",") if t.strip()]
    else:
        tickers = UNIVERSES[universe_choice]
        u_col2.caption(f"{len(tickers)} tickers: {', '.join(tickers[:12])}" +
                       ("…" if len(tickers) > 12 else ""))

    st.markdown("---")

    # ── Tabs ──────────────────────────────────────────────────────────────────
    t_movers, t_scan, t_options, t_tech, t_volarb = st.tabs([
        "📈 Movers", "💧 Liquidity Scan", "🔀 Options Flow", "📐 Technicals", "⚡ Vol Arb Scan"
    ])

    # ══════════════════════════════════════════════════════════════════════════
    # MOVERS
    # ══════════════════════════════════════════════════════════════════════════
    with t_movers:
        st.caption("Live top gainers and losers from Polygon's market-wide snapshot.")
        f1, f2, f3 = st.columns(3)
        mv_min_price  = f1.number_input("Min price ($)",  value=5.0,  step=1.0, key="mv_mp")
        mv_min_vol    = f2.number_input("Min volume (M)", value=0.5,  step=0.5, key="mv_mv")
        mv_n          = f3.slider("# shown each side", 5, 20, 10, key="mv_n")

        if st.button("📡 Fetch Movers", width="stretch", key="mv_btn"):
            with st.spinner("Fetching gainers and losers…"):
                g = _fetch_movers(api_key, "gainers")
                l = _fetch_movers(api_key, "losers")
                combined = pd.concat([g, l]).drop_duplicates("Ticker")
            st.session_state["sc_movers"] = combined

        mv_df = st.session_state.get("sc_movers", pd.DataFrame())

        if not mv_df.empty:
            # Apply filters
            fdf = mv_df[
                (mv_df["Price"]  >= mv_min_price) &
                (mv_df["Volume"] >= mv_min_vol * 1_000_000)
            ]
            if not fdf.empty:
                st.plotly_chart(_movers_chart(fdf, n=mv_n * 2), width="stretch")
                st.dataframe(
                    fdf.sort_values("Change%", ascending=False),
                    width="stretch", hide_index=True,
                    column_config={
                        "Price":     cc.NumberColumn("Price",      format="$%.2f"),
                        "Change%":   cc.NumberColumn("Change %",   format="%.2f%%"),
                        "Change$":   cc.NumberColumn("Change $",   format="$%.2f"),
                        "Volume":    cc.NumberColumn("Volume",     format="%.0f"),
                        "DollarVol": cc.NumberColumn("$ Volume",   format="$%.0f"),
                        "RelVol":    cc.NumberColumn("Rel. Vol",   format="%.1fx"),
                    },
                )
            else:
                st.info("No movers passed the filters.")

    # ══════════════════════════════════════════════════════════════════════════
    # LIQUIDITY SCAN
    # ══════════════════════════════════════════════════════════════════════════
    with t_scan:
        st.caption("Batch snapshot for the selected universe. Filters by liquidity and price action.")

        lf1, lf2, lf3, lf4 = st.columns(4)
        ls_min_price  = lf1.number_input("Min price ($)",      value=1.0,   step=1.0, key="ls_mp")
        ls_max_price  = lf2.number_input("Max price ($)",      value=99999.0, step=10.0, key="ls_xp")
        ls_min_vol    = lf3.number_input("Min volume (M)",     value=0.1,   step=0.1, key="ls_mv")
        ls_min_dvol   = lf4.number_input("Min $ volume (M)",   value=0.0,   step=10.0, key="ls_dv")
        lf5, lf6, lf7 = st.columns(3)
        ls_min_chg    = lf5.number_input("Min change% (e.g. −5)", value=-100.0, step=1.0, key="ls_mc")
        ls_max_chg    = lf6.number_input("Max change%",        value=100.0, step=1.0, key="ls_xc")
        ls_min_relvol = lf7.number_input("Min relative vol",   value=0.0,   step=0.5, key="ls_rv")

        if st.button("🔍 Run Liquidity Scan", width="stretch", key="ls_btn"):
            with st.spinner(f"Fetching {len(tickers)} tickers…"):
                raw = _batch_snapshot(tickers, api_key)
            st.session_state["sc_scan"] = raw

        scan_df = st.session_state.get("sc_scan", pd.DataFrame())

        if not scan_df.empty:
            fdf = scan_df[
                (scan_df["Price"]     >= ls_min_price) &
                (scan_df["Price"]     <= ls_max_price) &
                (scan_df["Volume"]    >= ls_min_vol * 1_000_000) &
                (scan_df["DollarVol"] >= ls_min_dvol * 1_000_000) &
                (scan_df["Change%"]   >= ls_min_chg) &
                (scan_df["Change%"]   <= ls_max_chg) &
                (scan_df["RelVol"]    >= ls_min_relvol)
            ].copy()

            st.caption(f"**{len(fdf)}** tickers passed filters (out of {len(scan_df)} fetched)")

            if not fdf.empty:
                # Colour-code Change% as delta
                st.dataframe(
                    fdf.sort_values("Change%", ascending=False),
                    width="stretch", hide_index=True,
                    column_config={
                        "Price":     cc.NumberColumn("Price",       format="$%.2f"),
                        "Change%":   cc.NumberColumn("Change %",    format="%.2f%%"),
                        "Change$":   cc.NumberColumn("Change $",    format="$%.2f"),
                        "Volume":    cc.NumberColumn("Volume",      format="%.0f"),
                        "DollarVol": cc.NumberColumn("$ Volume",    format="$%.0f"),
                        "RelVol":    cc.NumberColumn("Rel. Vol",    format="%.1fx"),
                        "Gap%":      cc.NumberColumn("Gap %",       format="%.2f%%"),
                        "VWAP":      cc.NumberColumn("VWAP",        format="$%.2f"),
                        "High":      cc.NumberColumn("High",        format="$%.2f"),
                        "Low":       cc.NumberColumn("Low",         format="$%.2f"),
                    },
                )

                # Quick bar chart of biggest movers in the scan
                if len(fdf) >= 3:
                    st.plotly_chart(_movers_chart(fdf, n=min(len(fdf), 20)), width="stretch")
            else:
                st.info("No tickers passed the filters — try relaxing the criteria.")

    # ══════════════════════════════════════════════════════════════════════════
    # OPTIONS FLOW
    # ══════════════════════════════════════════════════════════════════════════
    with t_options:
        st.caption(
            "Put/Call OI ratio, P/C volume ratio, and IV for each ticker. "
            "Calls options chain per ticker — can be slow for large universes."
        )

        of1, of2, of3 = st.columns(3)
        of_min_pc  = of1.number_input("Min P/C OI",     value=0.0,  step=0.1, key="of_mnpc")
        of_max_pc  = of2.number_input("Max P/C OI",     value=10.0, step=0.1, key="of_mxpc")
        of_min_iv  = of3.number_input("Min Avg IV% ",   value=0.0,  step=5.0, key="of_iv")

        of_tickers = st.multiselect(
            "Tickers to scan (subset recommended for speed)",
            options=tickers, default=tickers[:min(10, len(tickers))],
            key="of_tickers",
        )

        opts_prog = st.empty()
        if st.button("📡 Fetch Options Flow", width="stretch", key="of_btn"):
            prog = opts_prog.progress(0, text="Starting…")
            with st.spinner("Fetching options chains…"):
                opts_raw = _fetch_options_flow(of_tickers, api_key, prog_bar=prog)
            opts_prog.empty()
            st.session_state["sc_opts"] = opts_raw

        opts_df = st.session_state.get("sc_opts", pd.DataFrame())

        if not opts_df.empty:
            fdf = opts_df[
                (opts_df["PC_OI"].fillna(0)   >= of_min_pc) &
                (opts_df["PC_OI"].fillna(999) <= of_max_pc) &
                (opts_df["AvgIV%"].fillna(0)  >= of_min_iv)
            ]

            if not fdf.empty:
                oc1, oc2 = st.columns(2)
                oc1.plotly_chart(_pc_chart(fdf), width="stretch")

                # IV bar chart
                iv_df = fdf.dropna(subset=["ATM_IV%"]).sort_values("ATM_IV%", ascending=True)
                if not iv_df.empty:
                    iv_colors = ["#ffb300"] * len(iv_df)
                    fig_iv = go.Figure(go.Bar(
                        x=iv_df["ATM_IV%"], y=iv_df["Ticker"],
                        orientation="h", marker_color=iv_colors,
                        text=[f"{v:.1f}%" for v in iv_df["ATM_IV%"]],
                        textposition="outside",
                    ))
                    fig_iv.update_layout(
                        title="ATM Implied Volatility (%)", height=max(280, len(iv_df) * 28),
                        paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
                        font=dict(color="#b0b8c8"),
                        xaxis=dict(gridcolor="#1e2130", title="ATM IV %"),
                        margin=dict(l=0, r=60, t=36, b=0),
                    )
                    oc2.plotly_chart(fig_iv, width="stretch")

                st.dataframe(
                    fdf.sort_values("PC_OI", ascending=False),
                    width="stretch", hide_index=True,
                    column_config={
                        "PC_OI":   cc.NumberColumn("P/C OI",       format="%.2f"),
                        "PC_Vol":  cc.NumberColumn("P/C Vol",       format="%.2f"),
                        "AvgIV%":  cc.NumberColumn("Avg IV %",      format="%.1f%%"),
                        "ATM_IV%": cc.NumberColumn("ATM IV %",      format="%.1f%%"),
                        "CallOI":  cc.NumberColumn("Call OI",       format="%d"),
                        "PutOI":   cc.NumberColumn("Put OI",        format="%d"),
                        "CallVol": cc.NumberColumn("Call Vol",      format="%d"),
                        "PutVol":  cc.NumberColumn("Put Vol",       format="%d"),
                    },
                )

                # Interpretation guide
                with st.expander("How to read P/C ratio"):
                    st.markdown("""
| P/C OI | Signal | Interpretation |
|---|---|---|
| > 1.5 | 🐻 Bearish skew | Heavy put buying / hedging — market expects downside |
| 1.0–1.5 | 🔶 Neutral/cautious | More puts than calls but within normal range |
| 0.7–1.0 | 🐂 Neutral/bullish | Balanced to call-heavy; no strong fear signal |
| < 0.7 | 🚀 Bullish/complacent | Heavy call buying; can signal euphoria |

**IV context:** High IV (> 40%) with P/C > 1.2 = fear. High IV with P/C < 0.8 = speculative call buying.
                    """)

    # ══════════════════════════════════════════════════════════════════════════
    # TECHNICALS
    # ══════════════════════════════════════════════════════════════════════════
    with t_tech:
        st.caption("RSI, SMA50, SMA200 for each ticker via Polygon's indicator endpoint.")

        tf1, tf2, tf3 = st.columns(3)
        tc_min_rsi = tf1.slider("Min RSI", 0, 100, 0,  key="tc_mn")
        tc_max_rsi = tf2.slider("Max RSI", 0, 100, 100, key="tc_mx")
        tc_tickers = tf3.multiselect(
            "Tickers",
            options=tickers, default=tickers[:min(10, len(tickers))],
            key="tc_tickers",
        )

        tech_prog = st.empty()
        if st.button("📐 Fetch Technicals", width="stretch", key="tc_btn"):
            prog = tech_prog.progress(0, text="Starting…")
            with st.spinner("Fetching RSI and moving averages…"):
                tech_raw = _fetch_rsi(tc_tickers, api_key, prog_bar=prog)
            tech_prog.empty()
            st.session_state["sc_tech"] = tech_raw

        # Merge with scan data if available
        tech_df = st.session_state.get("sc_tech", pd.DataFrame())
        if not tech_df.empty:
            scan_cache = st.session_state.get("sc_scan", pd.DataFrame())
            if not scan_cache.empty:
                tech_df = tech_df.merge(
                    scan_cache[["Ticker", "Price", "Change%"]],
                    on="Ticker", how="left",
                )

            fdf = tech_df[
                (tech_df["RSI"].fillna(50) >= tc_min_rsi) &
                (tech_df["RSI"].fillna(50) <= tc_max_rsi)
            ].copy()

            if not fdf.empty:
                # Add above/below MA flags
                if "Price" in fdf.columns:
                    fdf["vs SMA50"]  = fdf.apply(
                        lambda r: "▲" if (r["SMA50"]  and r["Price"] > r["SMA50"])  else "▼", axis=1
                    )
                    fdf["vs SMA200"] = fdf.apply(
                        lambda r: "▲" if (r["SMA200"] and r["Price"] > r["SMA200"]) else "▼", axis=1
                    )

                # RSI bar chart
                rsi_sorted = fdf.dropna(subset=["RSI"]).sort_values("RSI")
                if not rsi_sorted.empty:
                    rsi_colors = [
                        "#ef5350" if v >= 70 else ("#4caf50" if v <= 30 else "#5c6bc0")
                        for v in rsi_sorted["RSI"]
                    ]
                    fig_rsi = go.Figure(go.Bar(
                        x=rsi_sorted["RSI"], y=rsi_sorted["Ticker"],
                        orientation="h", marker_color=rsi_colors,
                        text=[f"{v:.1f}" for v in rsi_sorted["RSI"]],
                        textposition="outside",
                    ))
                    fig_rsi.add_vline(x=70, line=dict(color="#ef5350", dash="dot", width=1))
                    fig_rsi.add_vline(x=30, line=dict(color="#4caf50", dash="dot", width=1))
                    fig_rsi.update_layout(
                        title="RSI(14)  — red > 70 (overbought), green < 30 (oversold)",
                        height=max(280, len(rsi_sorted) * 28),
                        paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
                        font=dict(color="#b0b8c8"),
                        xaxis=dict(gridcolor="#1e2130", range=[0, 100]),
                        margin=dict(l=0, r=60, t=40, b=0),
                    )
                    st.plotly_chart(fig_rsi, width="stretch")

                st.dataframe(
                    fdf.sort_values("RSI"),
                    width="stretch", hide_index=True,
                    column_config={
                        "RSI":     cc.NumberColumn("RSI(14)",   format="%.1f"),
                        "Price":   cc.NumberColumn("Price",     format="$%.2f"),
                        "Change%": cc.NumberColumn("Change %",  format="%.2f%%"),
                        "SMA50":   cc.NumberColumn("SMA50",     format="$%.2f"),
                        "SMA200":  cc.NumberColumn("SMA200",    format="$%.2f"),
                    },
                )
            else:
                st.info("No tickers in RSI range — adjust the filter.")

    # ══════════════════════════════════════════════════════════════════════════
    # VOL ARB SCAN — detect parity violations & IV skew opportunities
    # ══════════════════════════════════════════════════════════════════════════
    with t_volarb:
        st.caption(
            "Scans the selected universe for **put-call parity violations** and "
            "**IV skew arbitrage** opportunities. Works best on retail-heavy names "
            "(HOOD, COIN, GME) where structural put buying creates persistent mispricing."
        )

        va_col1, va_col2, va_col3, va_col4 = st.columns(4)
        va_min_viol  = va_col1.slider("Min parity violation %", 0.1, 2.0, 0.3, 0.1,
                                      key="va_mv",
                                      help="Minimum C-P deviation from theoretical as % of spot")
        va_skew_thr  = va_col2.slider("IV skew threshold (vol pts)", 2, 20, 8, 1,
                                      key="va_sk",
                                      help="Put minus call IV at same strike to flag skew arb")
        va_dte_min   = va_col3.slider("DTE min", 5, 30, 14, 1, key="va_dtl")
        va_dte_max   = va_col4.slider("DTE max", 20, 90, 45, 5, key="va_dth")

        va_tickers = st.multiselect(
            "Tickers to scan",
            options=sorted({t for lst in UNIVERSES.values() for t in lst}),
            default=["HOOD", "COIN", "PLTR", "SOFI", "GME", "MSTR", "RIVN", "RKLB"],
            key="va_tickers",
        )

        if st.button("⚡ Run Vol Arb Scan", width="stretch", key="va_btn"):
            if not api_key:
                st.warning("Enter a Polygon API key in the sidebar.")
            elif not va_tickers:
                st.warning("Select at least one ticker.")
            else:
                from alan_trader.data.polygon_client import PolygonClient
                from alan_trader.backtest.engine import bs_price
                from scipy.optimize import brentq

                def _iv(price, S, K, T, r, kind):
                    if T <= 0 or price <= 0:
                        return None
                    intr = max(0, S - K) if kind == "call" else max(0, K - S)
                    if price < intr:
                        return None
                    try:
                        return brentq(lambda v: bs_price(S, K, T, r, v, kind) - price,
                                      1e-4, 10.0, xtol=1e-5, maxiter=80)
                    except Exception:
                        return None

                def _scan_ticker(ticker, client, min_viol_pct, skew_thr, dte_lo, dte_hi):
                    import datetime as _dt
                    snap  = client.get_snapshot(ticker)
                    S     = (snap.get("day", {}).get("c") or
                             snap.get("lastTrade", {}).get("p") or 0)
                    if S <= 0:
                        return []

                    # ── Targeted fetch: only 14-45 DTE + ±25% strike band ──
                    # This cuts API calls from 6+ pages to typically 1 page per ticker.
                    today    = _dt.date.today()
                    exp_gte  = (today + _dt.timedelta(days=dte_lo)).isoformat()
                    exp_lte  = (today + _dt.timedelta(days=dte_hi)).isoformat()
                    s_lo     = round(S * 0.75, 2)
                    s_hi     = round(S * 1.25, 2)

                    chain = client.get_options_chain(
                        ticker,
                        expiration_date_gte=exp_gte,
                        expiration_date_lte=exp_lte,
                        strike_price_gte=s_lo,
                        strike_price_lte=s_hi,
                    )
                    if chain is None or chain.empty:
                        return []

                    # Aggregate chain stats (whole chain)
                    calls = chain[chain["type"] == "call"]
                    puts  = chain[chain["type"] == "put"]
                    call_oi  = calls["open_interest"].fillna(0).sum()
                    put_oi   = puts["open_interest"].fillna(0).sum()
                    call_vol = calls["volume"].fillna(0).sum()
                    put_vol  = puts["volume"].fillna(0).sum()
                    pc_oi    = round(put_oi / call_oi, 2) if call_oi > 0 else None
                    pc_vol   = round(put_vol / call_vol, 2) if call_vol > 0 else None
                    avg_iv   = chain["iv"].dropna().mean()

                    # Filter by DTE window (dte column now always present from polygon_client)
                    chain_f = chain.dropna(subset=["dte"])
                    chain_f = chain_f[(chain_f["dte"] >= dte_lo) & (chain_f["dte"] <= dte_hi)]
                    if chain_f.empty:
                        chain_f = chain  # fallback: use whole chain

                    r_rate = 0.045
                    parity_viols, skew_viols = [], []

                    # ── Process per expiration to avoid duplicate-strike index issues ──
                    for exp_date, exp_grp in chain_f.groupby("expiration"):
                        dte_v = exp_grp["dte"].iloc[0]
                        if dte_v is None or dte_v != dte_v:
                            continue
                        dte_v = float(dte_v)
                        T = dte_v / 252
                        if T <= 0:
                            continue

                        c_map = (exp_grp[exp_grp["type"] == "call"]
                                 .dropna(subset=["strike"])
                                 .set_index("strike"))
                        p_map = (exp_grp[exp_grp["type"] == "put"]
                                 .dropna(subset=["strike"])
                                 .set_index("strike"))
                        common = c_map.index.intersection(p_map.index)

                        for K in common:
                            c_row = c_map.loc[K]
                            p_row = p_map.loc[K]

                            # Handle duplicate strikes within same expiration (take first)
                            if isinstance(c_row, pd.DataFrame):
                                c_row = c_row.iloc[0]
                            if isinstance(p_row, pd.DataFrame):
                                p_row = p_row.iloc[0]

                            c_bid = c_row.get("bid", float("nan"))
                            c_ask = c_row.get("ask", float("nan"))
                            p_bid = p_row.get("bid", float("nan"))
                            p_ask = p_row.get("ask", float("nan"))

                            # Skip if no valid quotes
                            if any(v != v for v in [c_bid, c_ask, p_bid, p_ask]):
                                continue

                            c_mid = (float(c_bid) + float(c_ask)) / 2
                            p_mid = (float(p_bid) + float(p_ask)) / 2
                            if c_mid <= 0 or p_mid <= 0:
                                continue

                            theory   = S * np.exp(-0.013 * T) - K * np.exp(-r_rate * T)
                            obs      = c_mid - p_mid
                            viol     = obs - theory
                            viol_pct = abs(viol) / S * 100

                            if viol_pct >= min_viol_pct:
                                trade = "Conversion" if viol > 0 else "Reversal"
                                parity_viols.append((K, int(dte_v), round(viol, 3),
                                                     round(viol_pct, 3), trade))

                            iv_c = _iv(c_mid, S, K, T, r_rate, "call")
                            iv_p = _iv(p_mid, S, K, T, r_rate, "put")
                            if iv_c and iv_p:
                                skew = iv_p - iv_c
                                if skew > skew_thr / 100:
                                    skew_viols.append((K, int(dte_v),
                                                       round(iv_c * 100, 1),
                                                       round(iv_p * 100, 1),
                                                       round(skew * 100, 1)))

                    best_parity = max(parity_viols, key=lambda x: abs(x[2])) if parity_viols else None
                    best_skew   = max(skew_viols,   key=lambda x: x[4])      if skew_viols   else None

                    signal = "—"
                    if best_parity and best_skew:
                        signal = f"Parity + Skew Arb"
                    elif best_parity:
                        signal = best_parity[4]  # Conversion / Reversal
                    elif best_skew:
                        signal = "Skew Arb"

                    return [{
                        "Ticker":        ticker,
                        "Price":         round(S, 2),
                        "Avg IV":        round(avg_iv * 100, 1) if avg_iv == avg_iv else None,
                        "P/C OI":        pc_oi,
                        "P/C Vol":       pc_vol,
                        "Best Violation %": round(max((abs(x[2]) / S * 100 for x in parity_viols), default=0), 3),
                        "Best Skew (pts)":  round(max((x[4] for x in skew_viols), default=0), 1),
                        "# Parity":      len(parity_viols),
                        "# Skew":        len(skew_viols),
                        "Signal":        signal,
                    }]

                client = PolygonClient(api_key=api_key)
                results = []
                prog = st.progress(0, text="Scanning…")
                for i, tkr in enumerate(va_tickers):
                    prog.progress((i + 1) / len(va_tickers), text=f"Scanning {tkr}…")
                    try:
                        results.extend(_scan_ticker(
                            tkr, client, va_min_viol, va_skew_thr, va_dte_min, va_dte_max
                        ))
                    except Exception as exc:
                        logger.warning(f"Vol arb scan {tkr}: {exc}")
                prog.empty()

                if not results:
                    st.info("No violations found. Try widening thresholds or check API key.")
                else:
                    df_va = pd.DataFrame(results)
                    df_va = df_va.sort_values("Best Violation %", ascending=False)

                    # Highlight rows with signals
                    signal_tickers = df_va[df_va["Signal"] != "—"]["Ticker"].tolist()
                    if signal_tickers:
                        st.success(f"**Opportunities found:** {', '.join(signal_tickers)}")

                    st.dataframe(
                        df_va, hide_index=True, width="stretch",
                        column_config={
                            "Price":               cc.NumberColumn("Price",       format="$%.2f"),
                            "Avg IV":              cc.NumberColumn("Avg IV",      format="%.1f%%"),
                            "P/C OI":              cc.NumberColumn("P/C OI",      format="%.2f"),
                            "P/C Vol":             cc.NumberColumn("P/C Vol",     format="%.2f"),
                            "Best Violation %":    cc.NumberColumn("Best Viol %", format="%.3f%%"),
                            "Best Skew (pts)":     cc.NumberColumn("Best Skew",   format="%.1f pt"),
                            "# Parity":            cc.NumberColumn("# Parity",    format="%d"),
                            "# Skew":              cc.NumberColumn("# Skew",      format="%d"),
                            "Signal":              cc.TextColumn("Signal"),
                        },
                    )

                    # Bar: violations by ticker
                    opp = df_va[(df_va["Best Violation %"] > 0) | (df_va["Best Skew (pts)"] > 0)]
                    if not opp.empty:
                        fig_va = go.Figure()
                        fig_va.add_trace(go.Bar(
                            name="Parity Violation %", x=opp["Ticker"],
                            y=opp["Best Violation %"],
                            marker_color="#ef9a9a",
                            hovertemplate="%{x}: %{y:.3f}%<extra>Parity</extra>",
                        ))
                        fig_va.add_trace(go.Bar(
                            name="IV Skew (pts)", x=opp["Ticker"],
                            y=opp["Best Skew (pts)"] / 10,  # scale to same axis
                            marker_color="#80cbc4",
                            hovertemplate="%{x}: %{y:.1f} pts (÷10)<extra>Skew</extra>",
                        ))
                        fig_va.update_layout(
                            title="Vol Arb Opportunities by Ticker",
                            barmode="group", height=300,
                            paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
                            font=dict(color="#b0b8c8"),
                            xaxis=dict(gridcolor="#1e2130"),
                            yaxis=dict(gridcolor="#1e2130", title="Violation % / Skew÷10"),
                            legend=dict(orientation="h", y=1.1),
                            margin=dict(l=0, r=0, t=40, b=0),
                        )
                        st.plotly_chart(fig_va, width="stretch")

                    st.caption(
                        "**Parity Violation %** = |C − P − theoretical| / S × 100.  "
                        "**IV Skew** = put IV − call IV at same strike (vol points).  "
                        "**P/C OI > 1.5** = put-heavy flow (typical for HOOD, COIN).  "
                        "Signal: *Conversion* = calls overpriced; *Reversal* = puts overpriced; "
                        "*Skew Arb* = risk-reversal opportunity."
                    )
