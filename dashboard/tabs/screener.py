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
    t_movers, t_scan, t_options, t_tech = st.tabs([
        "📈 Movers", "💧 Liquidity Scan", "🔀 Options Flow", "📐 Technicals"
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
