"""
Stock Screener tab — Liquidity, Daily Movers, Options Flow, Technicals.
Data source: Polygon.io (requires API key).
"""

import math
import time
import datetime
import logging

import numpy as np
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

def render(api_key: str = "", selected_strategies: list = None, key_prefix: str = "") -> None:
    # kp() prefixes every widget key so multiple instances don't collide
    def kp(k: str) -> str:
        return f"{key_prefix}{k}" if key_prefix else k
    st.markdown("## Stock Screener")

    if not api_key:
        st.warning("Enter your Polygon API key in the sidebar to use live data.")
        return

    # ── Universe picker ───────────────────────────────────────────────────────
    st.markdown("### Universe")
    u_col1, u_col2 = st.columns([2, 5])
    universe_choice = u_col1.selectbox(
        "Predefined list", ["Custom"] + list(UNIVERSES.keys()),
        key=kp("sc_universe"),
    )
    if universe_choice == "Custom":
        custom_input = u_col2.text_input(
            "Tickers (comma-separated)", value="AAPL,MSFT,NVDA,META,TSLA",
            key=kp("sc_custom_tickers"),
        )
        tickers = [t.strip().upper() for t in custom_input.split(",") if t.strip()]
    else:
        tickers = UNIVERSES[universe_choice]
        u_col2.caption(f"{len(tickers)} tickers: {', '.join(tickers[:12])}" +
                       ("…" if len(tickers) > 12 else ""))

    st.markdown("---")

    # ── Tabs — fixed market tabs + one tab per selected strategy with has_screener=True ──
    from alan_trader.strategies.registry import STRATEGY_METADATA as STRATEGY_REGISTRY
    _active = set(selected_strategies or [])
    _screener_strategies = [
        (slug, meta) for slug, meta in STRATEGY_REGISTRY.items()
        if meta.get("has_screener") and slug in _active
    ]
    _fixed_labels = ["📈 Movers", "💧 Liquidity Scan", "🔀 Options Flow", "📐 Technicals"]
    _strat_labels = [
        f"{meta.get('icon', '⚡')} {meta['display_name']}"
        for _, meta in _screener_strategies
    ]
    _all_tabs = st.tabs(_fixed_labels + _strat_labels)
    t_movers, t_scan, t_options, t_tech = _all_tabs[:4]
    _strat_tabs = {slug: _all_tabs[4 + i] for i, (slug, _) in enumerate(_screener_strategies)}
    t_volarb   = _strat_tabs.get("vol_arbitrage")
    t_ivr      = _strat_tabs.get("ivr_credit_spread")
    t_vixfade  = _strat_tabs.get("vix_spike_fade")
    t_eivcrush = _strat_tabs.get("earnings_iv_crush")
    t_postdrift = _strat_tabs.get("earnings_post_drift")

    # ══════════════════════════════════════════════════════════════════════════
    # MOVERS
    # ══════════════════════════════════════════════════════════════════════════
    with t_movers:
        st.caption("Live top gainers and losers from Polygon's market-wide snapshot.")
        f1, f2, f3 = st.columns(3)
        mv_min_price  = f1.number_input("Min price ($)",  value=5.0,  step=1.0, key=kp("mv_mp"))
        mv_min_vol    = f2.number_input("Min volume (M)", value=0.5,  step=0.5, key=kp("mv_mv"))
        mv_n          = f3.slider("# shown each side", 5, 20, 10, key=kp("mv_n"))

        if st.button("📡 Fetch Movers", key=kp("mv_btn")):
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
        ls_min_price  = lf1.number_input("Min price ($)",      value=1.0,   step=1.0, key=kp("ls_mp"))
        ls_max_price  = lf2.number_input("Max price ($)",      value=99999.0, step=10.0, key=kp("ls_xp"))
        ls_min_vol    = lf3.number_input("Min volume (M)",     value=0.1,   step=0.1, key=kp("ls_mv"))
        ls_min_dvol   = lf4.number_input("Min $ volume (M)",   value=0.0,   step=10.0, key=kp("ls_dv"))
        lf5, lf6, lf7 = st.columns(3)
        ls_min_chg    = lf5.number_input("Min change% (e.g. −5)", value=-100.0, step=1.0, key=kp("ls_mc"))
        ls_max_chg    = lf6.number_input("Max change%",        value=100.0, step=1.0, key=kp("ls_xc"))
        ls_min_relvol = lf7.number_input("Min relative vol",   value=0.0,   step=0.5, key=kp("ls_rv"))

        if st.button("🔍 Run Liquidity Scan", key=kp("ls_btn")):
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
        of_min_pc  = of1.number_input("Min P/C OI",     value=0.0,  step=0.1, key=kp("of_mnpc"))
        of_max_pc  = of2.number_input("Max P/C OI",     value=10.0, step=0.1, key=kp("of_mxpc"))
        of_min_iv  = of3.number_input("Min Avg IV% ",   value=0.0,  step=5.0, key=kp("of_iv"))

        of_tickers = st.multiselect(
            "Tickers to scan (subset recommended for speed)",
            options=tickers, default=tickers[:min(10, len(tickers))],
            key=kp("of_tickers"),
        )

        opts_prog = st.empty()
        if st.button("📡 Fetch Options Flow", key=kp("of_btn")):
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
        tc_min_rsi = tf1.slider("Min RSI", 0, 100, 0,  key=kp("tc_mn"))
        tc_max_rsi = tf2.slider("Max RSI", 0, 100, 100, key=kp("tc_mx"))
        tc_tickers = tf3.multiselect(
            "Tickers",
            options=tickers, default=tickers[:min(10, len(tickers))],
            key=kp("tc_tickers"),
        )

        tech_prog = st.empty()
        if st.button("📐 Fetch Technicals", key=kp("tc_btn")):
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
    if t_volarb is not None:
      with t_volarb:
        st.caption(
            "Scans the selected universe for **put-call parity violations** and "
            "**IV skew arbitrage** opportunities. Works best on retail-heavy names "
            "with high put/call OI ratios, where structural put buying creates persistent mispricing."
        )

        va_col1, va_col2, va_col3, va_col4 = st.columns(4)
        va_min_viol  = va_col1.slider("Min parity violation %", 0.1, 2.0, 0.3, 0.1,
                                      key=kp("va_mv"),
                                      help="Minimum C-P deviation from theoretical as % of spot")
        va_skew_thr  = va_col2.slider("IV skew threshold (vol pts)", 2, 20, 8, 1,
                                      key=kp("va_sk"),
                                      help="Put minus call IV at same strike to flag skew arb")
        va_dte_min   = va_col3.slider("DTE min", 5, 30, 14, 1, key=kp("va_dtl"))
        va_dte_max   = va_col4.slider("DTE max", 20, 90, 45, 5, key=kp("va_dth"))

        va_col5, va_col6, va_col7, va_col8 = st.columns(4)
        va_auto_spread = va_col5.toggle(
            "Auto spread size (5% of spot)",
            value=True, key=kp("va_auto_spread"),
            help="Automatically sizes each spread to ~5% of the stock price (min $2, rounded to $0.50). "
                 "Disable to set fixed widths manually.",
        )
        if va_auto_spread:
            va_put_width   = None
            va_hedge_width = None
            va_col6.caption("Spread widths auto-sized per ticker")
        else:
            va_put_width  = va_col6.slider("Put spread width ($)", 1.0, 20.0, 2.0, 0.5,
                                           key=kp("va_pw"),
                                           help="Bull put spread width — long put at K minus this value")
            va_hedge_width = va_col6.slider("Hedge spread width ($)", 1.0, 20.0, 2.0, 0.5,
                                            key=kp("va_hw"),
                                            help="Long call at ATM plus this value")
        va_iv_rank    = va_col7.slider("Min IV rank (0–1)", 0.0, 0.80, 0.0, 0.05,
                                       key=kp("va_ivr"),
                                       help="Only show tickers where current IV rank exceeds this threshold")
        va_div_yield  = va_col8.slider("Div yield (%)", 0.0, 5.0, 1.3, 0.1,
                                       key=kp("va_dy"),
                                       help="Continuous dividend yield used in put-call parity calculation") / 100

        va_tickers = st.multiselect(
            "Tickers to scan",
            options=sorted({t for lst in UNIVERSES.values() for t in lst}),
            default=["HOOD", "COIN", "PLTR", "SOFI", "GME", "MSTR", "RIVN", "RKLB"],
            key=kp("va_tickers"),
        )

        if st.button("⚡ Run IV Skew Scan", key=kp("va_btn")):
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

                def _scan_ticker(ticker, client, min_viol_pct, skew_thr, dte_lo, dte_hi,
                                 put_spread_width=None, hedge_spread_width=None, div_yield=0.013):
                    import datetime as _dt
                    snap  = client.get_snapshot(ticker)
                    S     = (snap.get("day", {}).get("c") or
                             snap.get("lastTrade", {}).get("p") or 0)
                    if S <= 0:
                        return []

                    # Auto-size spreads to ~5% of stock price (min $2, rounded to $0.50)
                    _auto = max(2.0, round(S * 0.05 / 0.5) * 0.5)
                    if put_spread_width   is None: put_spread_width   = _auto
                    if hedge_spread_width is None: hedge_spread_width = _auto

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

                            theory   = S * np.exp(-div_yield * T) - K * np.exp(-r_rate * T)
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
                        signal = "Parity + Skew Arb"
                    elif best_parity:
                        signal = best_parity[4]
                    elif best_skew:
                        signal = "Skew Arb"

                    # ── Build actual leg details from best skew strike ──────────
                    # 4-leg structure: Short Put (K) + Long Put (K-width)
                    #                  Short Call (K) + Long Call (K+hedge_width)
                    leg_details = None
                    ref = best_skew or best_parity
                    if ref:
                        K_best   = ref[0]
                        dte_best = ref[1]
                        # find the expiry group for this DTE
                        for exp_date, exp_grp in chain_f.groupby("expiration"):
                            if abs(float(exp_grp["dte"].iloc[0]) - dte_best) > 1:
                                continue
                            c_map2 = (exp_grp[exp_grp["type"] == "call"]
                                      .dropna(subset=["strike"]).set_index("strike"))
                            p_map2 = (exp_grp[exp_grp["type"] == "put"]
                                      .dropna(subset=["strike"]).set_index("strike"))

                            def _mid(m, k):
                                # Exact strike match only — no snapping
                                if k not in m.index:
                                    return None
                                r = m.loc[k]
                                if isinstance(r, pd.DataFrame): r = r.iloc[0]
                                bid = r.get("bid", float("nan"))
                                ask = r.get("ask", float("nan"))
                                if bid != bid or ask != ask: return None
                                return round((float(bid) + float(ask)) / 2, 4)

                            def _ba(m, k):
                                """Return (bid, ask) tuple or (None, None)."""
                                if k not in m.index:
                                    return None, None
                                r = m.loc[k]
                                if isinstance(r, pd.DataFrame): r = r.iloc[0]
                                bid = r.get("bid", float("nan"))
                                ask = r.get("ask", float("nan"))
                                b = round(float(bid), 4) if bid == bid else None
                                a = round(float(ask), 4) if ask == ask else None
                                return b, a

                            def _stat(m, k, col):
                                if k not in m.index:
                                    return None
                                r = m.loc[k]
                                if isinstance(r, pd.DataFrame): r = r.iloc[0]
                                v = r.get(col)
                                return int(v) if v is not None else None

                            # Bull put spread: short put at K_best (detection strike, overpriced vs
                            # call at same strike), long put at K_best − width (protection).
                            # Net credit + positive theta. IV edge = put IV vs call IV at K_best.
                            # ShortCall hedge at ATM (nearest strike to S), NOT at K_best —
                            # placing it at K_best would cancel the LongCallATK.
                            K_lp = round(K_best - put_spread_width, 2)  # long put = protection
                            _c_strikes = c_map2.index.to_numpy()
                            K_sc = float(_c_strikes[abs(_c_strikes - S).argsort()[0]]) if len(_c_strikes) > 0 else K_best
                            K_lc_actual = round(K_sc + hedge_spread_width, 2)
                            _sp_b,  _sp_a  = _ba(p_map2, K_best)    # short put at detection strike
                            _lp_b,  _lp_a  = _ba(p_map2, K_lp)      # long put = protection
                            _atk_b, _atk_a = _ba(c_map2, K_best)    # long call ATK at detection strike
                            _sc_b,  _sc_a  = _ba(c_map2, K_sc)      # short call at ATM (hedge)
                            _lc_b,  _lc_a  = _ba(c_map2, K_lc_actual)
                            leg_details = {
                                "strike":      K_best,
                                "expiration":  str(exp_date),
                                "dte":         dte_best,
                                "short_put_mid":       _mid(p_map2, K_best),
                                "long_put_mid":        _mid(p_map2, K_lp),
                                "long_call_atk_mid":   _mid(c_map2, K_best),
                                "short_call_mid":      _mid(c_map2, K_sc),
                                "long_call_mid":       _mid(c_map2, K_lc_actual),
                                "short_put_strike":    K_best,
                                "long_put_strike":     K_lp,
                                "short_call_strike":   K_sc,
                                "long_call_strike":    K_lc_actual,
                                "put_spread_width":    put_spread_width,
                                "hedge_spread_width":  hedge_spread_width,
                                "short_put_bid":       _sp_b,  "short_put_ask":    _sp_a,
                                "long_put_bid":        _lp_b,  "long_put_ask":     _lp_a,
                                "long_call_atk_bid":   _atk_b, "long_call_atk_ask":_atk_a,
                                "short_call_bid":      _sc_b,  "short_call_ask":   _sc_a,
                                "long_call_bid":       _lc_b,  "long_call_ask":    _lc_a,
                                "short_put_oi":        _stat(p_map2, K_best,      "open_interest"),
                                "short_put_vol":       _stat(p_map2, K_best,      "volume"),
                                "long_put_oi":         _stat(p_map2, K_lp,        "open_interest"),
                                "long_put_vol":        _stat(p_map2, K_lp,        "volume"),
                                "long_call_atk_oi":    _stat(c_map2, K_best,      "open_interest"),
                                "long_call_atk_vol":   _stat(c_map2, K_best,      "volume"),
                                "short_call_oi":       _stat(c_map2, K_sc,        "open_interest"),
                                "short_call_vol":      _stat(c_map2, K_sc,        "volume"),
                                "long_call_oi":        _stat(c_map2, K_lc_actual, "open_interest"),
                                "long_call_vol":       _stat(c_map2, K_lc_actual, "volume"),
                            }
                            break

                    return [{
                        "Ticker":           ticker,
                        "Price":            round(S, 2),
                        "Avg IV":           round(avg_iv * 100, 1) if avg_iv == avg_iv else None,
                        "P/C OI":           pc_oi,
                        "P/C Vol":          pc_vol,
                        "Best Violation %": round(max((abs(x[2]) / S * 100 for x in parity_viols), default=0), 3),
                        "Best Skew (pts)":  round(max((x[4] for x in skew_viols), default=0), 1),
                        "# Parity":         len(parity_viols),
                        "# Skew":           len(skew_viols),
                        "Signal":           signal,
                        "Put Spread $":     put_spread_width,
                        "Hedge Spread $":   hedge_spread_width,
                        "_legs":            leg_details,
                    }]

                client = PolygonClient(api_key=api_key)
                results = []
                prog = st.progress(0, text="Scanning…")
                for i, tkr in enumerate(va_tickers):
                    prog.progress((i + 1) / len(va_tickers), text=f"Scanning {tkr}…")
                    try:
                        results.extend(_scan_ticker(
                            tkr, client, va_min_viol, va_skew_thr, va_dte_min, va_dte_max,
                            put_spread_width=va_put_width, hedge_spread_width=va_hedge_width,
                            div_yield=va_div_yield,
                        ))
                    except Exception as exc:
                        logger.warning(f"Vol arb scan {tkr}: {exc}")
                prog.empty()

                if not results:
                    st.info("No violations found. Try widening thresholds or check API key.")
                else:
                    df_va = pd.DataFrame(results)
                    df_va = df_va[~df_va["Signal"].isin(["Conversion", "Reversal"])]

                    # Drop any row where one or more leg prices are missing
                    _leg_price_keys = ["short_put_mid", "long_put_mid", "long_call_atk_mid",
                                       "short_call_mid", "long_call_mid"]
                    def _all_legs_priced(row):
                        legs = row.get("_legs")
                        if not isinstance(legs, dict):
                            return False
                        return all(legs.get(k) is not None for k in _leg_price_keys)

                    before = len(df_va)
                    df_va = df_va[df_va.apply(_all_legs_priced, axis=1)]
                    dropped = before - len(df_va)
                    if dropped:
                        st.warning(f"{dropped} ticker(s) removed — one or more leg strikes not found in live chain.")

                    df_va = df_va.sort_values("Best Violation %", ascending=False)
                    st.session_state["va_scan_results"] = df_va

        # ── Results (rendered from session_state so they survive button clicks) ──
        if "va_scan_results" in st.session_state:
            df_va = st.session_state["va_scan_results"]

            signal_tickers = df_va[df_va["Signal"] != "—"]["Ticker"].tolist()
            if signal_tickers:
                st.success(f"**Opportunities found:** {', '.join(signal_tickers)}")

            # Expand _legs into display columns
            def _leg_px(row, key):
                legs = row.get("_legs")
                if not isinstance(legs, dict): return None
                v = legs.get(key)
                return round(float(v), 4) if v is not None else None

            display_va = df_va.copy()
            display_va["ShortPut $"]  = display_va.apply(lambda r: _leg_px(r, "short_put_mid"),  axis=1)
            display_va["LongPut $"]   = display_va.apply(lambda r: _leg_px(r, "long_put_mid"),   axis=1)
            display_va["LongCallATK $"] = display_va.apply(lambda r: _leg_px(r, "long_call_atk_mid"), axis=1)
            display_va["ShortCall $"] = display_va.apply(lambda r: _leg_px(r, "short_call_mid"), axis=1)
            display_va["LongCall $"]  = display_va.apply(lambda r: _leg_px(r, "long_call_mid"),  axis=1)
            display_va["Strike"]      = display_va.apply(lambda r: r.get("_legs", {}).get("strike") if isinstance(r.get("_legs"), dict) else None, axis=1)
            display_va["Expiry"]      = display_va.apply(lambda r: r.get("_legs", {}).get("expiration") if isinstance(r.get("_legs"), dict) else None, axis=1)

            # ── Per-ticker expanders ───────────────────────────────────────────
            for _, row_va in display_va.iterrows():
                tkr   = row_va["Ticker"]
                legs  = row_va.get("_legs") if isinstance(row_va.get("_legs"), dict) else {}
                sig   = row_va.get("Signal", "—")
                stock = row_va.get("Price")
                skew  = row_va.get("Best Skew (pts)")
                avg_iv = row_va.get("Avg IV")
                strike = legs.get("strike")
                exp    = legs.get("expiration")
                dte    = legs.get("dte")
                net_credit = 0.0
                for _pk, _dir in [("short_put_mid", 1), ("short_call_mid", 1),
                                   ("long_put_mid", -1), ("long_call_atk_mid", -1), ("long_call_mid", -1)]:
                    v = legs.get(_pk)
                    if v: net_credit += _dir * float(v) * 100

                pw  = legs.get("put_spread_width")
                hw  = legs.get("hedge_spread_width")
                spread_str = f"  |  Spreads: ${pw:.1f} / ${hw:.1f}" if pw and hw else ""
                label = (
                    f"{tkr}  |  {sig}  |  Stock: ${stock:.2f}"
                    f"  |  Strike: ${strike:.1f}  |  Expiry: {exp}  ({dte:.0f} DTE)"
                    f"  |  Net Credit: ${net_credit:+.2f}"
                    f"  |  Skew: {skew:.1f} pts  |  Avg IV: {avg_iv:.1f}%"
                    f"{spread_str}"
                ) if strike and exp else f"{tkr}  |  {sig}"

                with st.expander(label, expanded=(sig != "—")):
                    if legs:
                        def _ba_str(b, a):
                            bs = f"${b:.4f}" if b is not None else "—"
                            as_ = f"${a:.4f}" if a is not None else "—"
                            return f"{bs} – {as_}"

                        leg_table = [
                            {"Leg": "ShortPut",    "Dir": "SELL", "Strike": legs.get("short_put_strike"), "Bid – Ask": _ba_str(legs.get("short_put_bid"),      legs.get("short_put_ask")),      "OI": legs.get("short_put_oi"),      "Volume": legs.get("short_put_vol")},
                            {"Leg": "LongPut",     "Dir": "BUY",  "Strike": legs.get("long_put_strike"),  "Bid – Ask": _ba_str(legs.get("long_put_bid"),       legs.get("long_put_ask")),       "OI": legs.get("long_put_oi"),       "Volume": legs.get("long_put_vol")},
                            {"Leg": "LongCallATK", "Dir": "BUY",  "Strike": legs.get("strike"),          "Bid – Ask": _ba_str(legs.get("long_call_atk_bid"),  legs.get("long_call_atk_ask")),  "OI": legs.get("long_call_atk_oi"),  "Volume": legs.get("long_call_atk_vol")},
                            {"Leg": "ShortCall",   "Dir": "SELL", "Strike": legs.get("short_call_strike"), "Bid – Ask": _ba_str(legs.get("short_call_bid"),    legs.get("short_call_ask")),     "OI": legs.get("short_call_oi"),     "Volume": legs.get("short_call_vol")},
                            {"Leg": "LongCall",    "Dir": "BUY",  "Strike": legs.get("long_call_strike"),"Bid – Ask": _ba_str(legs.get("long_call_bid"),      legs.get("long_call_ask")),      "OI": legs.get("long_call_oi"),      "Volume": legs.get("long_call_vol")},
                        ]
                        st.dataframe(
                            pd.DataFrame(leg_table), hide_index=True, width="stretch",
                            column_config={
                                "Strike":   cc.NumberColumn(format="$%.1f"),
                                "OI":       cc.NumberColumn("Open Interest", format="%d"),
                                "Volume":   cc.NumberColumn(format="%d"),
                                "Bid – Ask": cc.TextColumn("Bid – Ask"),
                            },
                        )
                    else:
                        st.caption("No leg detail available.")

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
                    y=opp["Best Skew (pts)"] / 10,
                    marker_color="#80cbc4",
                    hovertemplate="%{x}: %{y:.1f} pts (÷10)<extra>Skew</extra>",
                ))
                fig_va.update_layout(
                    title="IV Skew Premium Capture — Opportunities by Ticker",
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
                "**P/C OI > 1.5** = put-heavy flow (typical of high-IV retail names).  "
                "*Skew Arb* = risk-reversal opportunity."
            )

            # ── Save to Paper Trades ───────────────────────────────────────────
            st.markdown("---")
            signal_rows = df_va[df_va["Signal"].isin(["Parity + Skew Arb", "Skew Arb"])].copy()
            if signal_rows.empty:
                st.info("No IV skew signals to paper trade.")
            else:
                signal_rows = signal_rows.reset_index(drop=True)
                signal_rows.insert(0, "Save", False)
                signal_rows.insert(1, "Qty", 1)
                edited = st.data_editor(
                    signal_rows[["Save", "Qty", "Ticker", "Price", "Best Skew (pts)", "Signal"]],
                    column_config={
                        "Save": cc.CheckboxColumn("Save", default=False),
                        "Qty":  cc.NumberColumn("Qty", min_value=1, max_value=100, step=1, default=1),
                        "Price": cc.NumberColumn("Stock $", format="$%.2f"),
                        "Best Skew (pts)": cc.NumberColumn("Best Skew", format="%.1f pt"),
                    },
                    hide_index=True, width="stretch", key=kp("va_trade_select"),
                )
                selected_tickers = edited[edited["Save"] == True]["Ticker"].tolist()
                selected_rows = signal_rows[signal_rows["Ticker"].isin(selected_tickers)].copy()
                # Merge Qty back from edited
                qty_map = dict(zip(edited["Ticker"], edited["Qty"]))
                selected_rows["_qty"] = selected_rows["Ticker"].map(qty_map).fillna(1).astype(int)

                pt_notes = st.text_input("Notes (optional)", placeholder="e.g. High IV environment, HOOD skew trade",
                                         key=kp("va_pt_notes"))
                if st.button("Save to Paper Trades", key=kp("va_pt_btn"), type="primary",
                             disabled=selected_rows.empty):
                    try:
                        from alan_trader.db.client import get_engine as _get_eng
                        from sqlalchemy import text as _text
                        import datetime as _dt, uuid as _uuid
                        _eng = _get_eng()
                        _today = _dt.date.today()
                        _saved = 0

                        with _eng.begin() as _conn:
                            for _, _row in selected_rows.iterrows():
                                ticker  = _row["Ticker"]
                                legs    = _row.get("_legs")
                                qty     = int(_row.get("_qty", 1))
                                _tgid   = str(_uuid.uuid4())
                                _notes  = pt_notes or f"{ticker}|{_row['Signal']}|skew={_row['Best Skew (pts)']}pts"

                                def _ensure_sec(sym, stype, otype, strike, expiry):
                                    existing = _conn.execute(_text(
                                        "SELECT SecurityId FROM portfolio.Security "
                                        "WHERE Symbol=:s AND SecurityType=:t"
                                    ), {"s": sym, "t": stype}).fetchone()
                                    if existing:
                                        return existing[0]
                                    row = _conn.execute(_text(
                                        "INSERT INTO portfolio.Security "
                                        "(Symbol, Underlying, SecurityType, OptionType, Strike, Expiration, Multiplier) "
                                        "OUTPUT INSERTED.SecurityId "
                                        "VALUES (:s, :u, :t, :o, :k, :e, 100)"
                                    ), {"s": sym, "u": ticker, "t": stype, "o": otype,
                                        "k": strike, "e": expiry}).fetchone()
                                    return row[0]

                                def _insert_leg(sec_id, direction, price, leg_type):
                                    _conn.execute(_text("""
                                        INSERT INTO portfolio.[Transaction]
                                            (BusinessDate, AccountId, TradeGroupId, StrategyName,
                                             SecurityId, Direction, Quantity, TransactionPrice,
                                             Commission, LegType, Source, Notes)
                                        VALUES (:d, 1, :tg, :strat, :sid, :dir, :qty, :px, 0, :lt, 'Screener', :n)
                                    """), {"d": _today, "tg": _tgid, "strat": "IV Skew Premium Capture",
                                          "sid": sec_id, "dir": direction, "qty": qty,
                                          "px": float(price or 0), "lt": leg_type, "n": _notes})

                                if legs and legs.get("strike"):
                                    K    = legs["strike"]             # detection strike = short put / LongCallATK
                                    K_lp = legs["long_put_strike"]    # K − width = long put protection
                                    K_sc = legs["short_call_strike"]  # ATM = short call hedge
                                    K_lc = legs["long_call_strike"]   # ATM + width = long call cap
                                    exp  = legs["expiration"]
                                    _insert_leg(_ensure_sec(f"{ticker}{exp}P{int(K*1000):08d}",     "option", "put",  K,    exp), "Sell", legs["short_put_mid"],     "ShortPut")
                                    _insert_leg(_ensure_sec(f"{ticker}{exp}P{int(K_lp*1000):08d}",  "option", "put",  K_lp, exp), "Buy",  legs["long_put_mid"],      "LongPut")
                                    _insert_leg(_ensure_sec(f"{ticker}{exp}C{int(K*1000):08d}atk",  "option", "call", K,    exp), "Buy",  legs["long_call_atk_mid"], "LongCallATK")
                                    _insert_leg(_ensure_sec(f"{ticker}{exp}C{int(K_sc*1000):08d}",  "option", "call", K_sc, exp), "Sell", legs["short_call_mid"],    "ShortCall")
                                    _insert_leg(_ensure_sec(f"{ticker}{exp}C{int(K_lc*1000):08d}",  "option", "call", K_lc, exp), "Buy",  legs["long_call_mid"],     "LongCall")
                                else:
                                    _sec = _conn.execute(_text(
                                        "SELECT SecurityId FROM portfolio.Security WHERE Symbol=:s AND SecurityType='equity'"
                                    ), {"s": ticker}).fetchone()
                                    if not _sec:
                                        _conn.execute(_text(
                                            "INSERT INTO portfolio.Security (Symbol, SecurityType, Multiplier) VALUES (:s,'equity',1)"
                                        ), {"s": ticker})
                                        _sec = _conn.execute(_text(
                                            "SELECT SecurityId FROM portfolio.Security WHERE Symbol=:s AND SecurityType='equity'"
                                        ), {"s": ticker}).fetchone()
                                    _insert_leg(_sec[0], "Buy", float(_row["Price"]), "Screener")

                                _saved += 1

                        st.success(f"✅ {_saved} trade(s) saved to Paper Trades — view in Paper Trading tab.")
                    except Exception as _e:
                        st.error(f"DB save failed: {_e}")

    # ══════════════════════════════════════════════════════════════════════════
    # TLT / SPY ROTATION SCREENER — regime detection & trade entry
    # ══════════════════════════════════════════════════════════════════════════
    t_rotation = _strat_tabs.get("rates_spy_rotation")
    if t_rotation is not None:
      with t_rotation:
        st.caption(
            "Detects the current **rate-equity regime** (Growth / Inflation / Fear / Risk-On / Transition) "
            "from 20-day SPY return and TLT return (proxy for yield direction). "
            "Recommends SPY / TLT allocation and lets you save the position to Paper Trades."
        )

        _REGIME_ALLOC = {
            "Growth":     (0.80, 0.10, 0.10, "#26a69a"),
            "Inflation":  (0.40, 0.05, 0.55, "#ef5350"),
            "Fear":       (0.20, 0.70, 0.10, "#ffb300"),
            "Risk-On":    (0.90, 0.10, 0.00, "#42a5f5"),
            "Transition": (0.60, 0.30, 0.10, "#ab47bc"),
        }
        _REGIME_DESC = {
            "Growth":     "Rates ↑ + Stocks ↑ — heavy SPY, light TLT",
            "Inflation":  "Rates ↑ + Stocks ↓ — reduce exposure, hold cash",
            "Fear":       "Rates ↓ + Stocks ↓ — flight to safety, heavy TLT",
            "Risk-On":    "Rates ↓ + Stocks ↑ — maximum SPY, minimal TLT",
            "Transition": "Ambiguous signal — balanced SPY/TLT positioning",
        }

        rot_col1, rot_col2, rot_col3 = st.columns(3)
        rot_threshold = rot_col1.slider(
            "Return threshold (%)", 0.5, 5.0, 3.0, 0.5, key=kp("rot_thr"),
            help="20-day return must exceed this % to count as directional"
        )
        rot_account  = rot_col2.number_input(
            "Account size ($)", min_value=1_000, max_value=10_000_000,
            value=100_000, step=5_000, key=kp("rot_acct")
        )
        rot_notes = rot_col3.text_input(
            "Notes (optional)", placeholder="e.g. FOMC week, regime shift", key=kp("rot_notes")
        )

        if st.button("🔁 Detect Regime", key=kp("rot_btn")):
            if not api_key:
                st.warning("Enter a Polygon API key in the sidebar.")
            else:
                try:
                    from alan_trader.data.polygon_client import PolygonClient
                    import datetime as _dt

                    _client = PolygonClient(api_key=api_key)
                    _today  = _dt.date.today()
                    _from   = (_today - _dt.timedelta(days=90)).isoformat()
                    _to     = _today.isoformat()

                    def _get_return(ticker):
                        bars = _client._get(
                            f"/v2/aggs/ticker/{ticker}/range/1/day/{_from}/{_to}",
                            {"adjusted": "true", "sort": "asc", "limit": 90},
                        ).get("results", [])
                        if len(bars) < 22:
                            return None, None, None
                        closes = [b["c"] for b in bars]
                        current = closes[-1]
                        price_20d_ago = closes[-22]
                        ret_20d = (current / price_20d_ago - 1) * 100
                        return current, price_20d_ago, ret_20d

                    with st.spinner("Fetching SPY and TLT data…"):
                        spy_price, spy_20d, spy_ret = _get_return("SPY")
                        tlt_price, tlt_20d, tlt_ret = _get_return("TLT")

                    if spy_ret is None or tlt_ret is None:
                        st.error("Not enough price history. Check API key or try again.")
                    else:
                        # TLT return as proxy: TLT ↑ → rates ↓, TLT ↓ → rates ↑
                        thr = rot_threshold / 100 * 100  # already in %
                        spy_up  = spy_ret >  thr
                        spy_dn  = spy_ret < -thr
                        # yield direction: TLT down → rates up, TLT up → rates down
                        rate_up = tlt_ret < -thr
                        rate_dn = tlt_ret >  thr

                        if rate_up and spy_up:
                            regime = "Growth"
                        elif rate_up and spy_dn:
                            regime = "Inflation"
                        elif rate_dn and spy_dn:
                            regime = "Fear"
                        elif rate_dn and spy_up:
                            regime = "Risk-On"
                        else:
                            regime = "Transition"

                        spy_w, tlt_w, cash_w, color = _REGIME_ALLOC[regime]
                        st.session_state["rot_result"] = {
                            "regime": regime, "color": color,
                            "spy_price": spy_price, "tlt_price": tlt_price,
                            "spy_ret": spy_ret, "tlt_ret": tlt_ret,
                            "spy_w": spy_w, "tlt_w": tlt_w, "cash_w": cash_w,
                        }
                except Exception as _ex:
                    st.error(f"Error fetching data: {_ex}")

        if "rot_result" in st.session_state:
            _r = st.session_state["rot_result"]
            regime = _r["regime"]
            color  = _r["color"]

            st.markdown(
                f"<div style='padding:12px;border-left:4px solid {color};"
                f"background:#0e1117;border-radius:4px;margin:8px 0'>"
                f"<span style='font-size:1.4em;font-weight:700;color:{color}'>{regime}</span>"
                f"<br><span style='color:#b0b8c8'>{_REGIME_DESC[regime]}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )

            mc1, mc2, mc3, mc4, mc5 = st.columns(5)
            mc1.metric("SPY 20d Return", f"{_r['spy_ret']:+.1f}%")
            mc2.metric("TLT 20d Return (→ rate proxy)", f"{_r['tlt_ret']:+.1f}%")
            mc3.metric("SPY Allocation", f"{_r['spy_w']*100:.0f}%")
            mc4.metric("TLT Allocation", f"{_r['tlt_w']*100:.0f}%")
            mc5.metric("Cash", f"{_r['cash_w']*100:.0f}%")

            spy_dollars = rot_account * _r["spy_w"]
            tlt_dollars = rot_account * _r["tlt_w"]
            spy_shares  = int(spy_dollars / _r["spy_price"]) if _r["spy_price"] else 0
            tlt_shares  = int(tlt_dollars / _r["tlt_price"]) if _r["tlt_price"] else 0

            _alloc_df = pd.DataFrame([
                {"Asset": "SPY", "Weight": f"{_r['spy_w']*100:.0f}%",
                 "Dollar Value": f"${spy_dollars:,.0f}", "Shares (approx)": spy_shares,
                 "Current Price": f"${_r['spy_price']:.2f}"},
                {"Asset": "TLT", "Weight": f"{_r['tlt_w']*100:.0f}%",
                 "Dollar Value": f"${tlt_dollars:,.0f}", "Shares (approx)": tlt_shares,
                 "Current Price": f"${_r['tlt_price']:.2f}"},
                {"Asset": "Cash", "Weight": f"{_r['cash_w']*100:.0f}%",
                 "Dollar Value": f"${rot_account*_r['cash_w']:,.0f}", "Shares (approx)": "—",
                 "Current Price": "—"},
            ])
            st.dataframe(_alloc_df, hide_index=True, width="stretch")

            st.markdown("---")
            if st.button("Save to Paper Trades", key=kp("rot_save_btn"), type="primary",
                         disabled=(spy_shares == 0 and tlt_shares == 0)):
                try:
                    from alan_trader.db.client import get_engine as _get_eng
                    from sqlalchemy import text as _text
                    import datetime as _dt, uuid as _uuid

                    _eng   = _get_eng()
                    _today2 = _dt.date.today()
                    _tgid  = str(_uuid.uuid4())
                    _note  = rot_notes or f"TLT/SPY Rotation|{regime}|SPY={_r['spy_w']*100:.0f}%,TLT={_r['tlt_w']*100:.0f}%"
                    _saved2 = 0

                    with _eng.begin() as _conn:
                        def _ensure_equity(sym):
                            ex = _conn.execute(_text(
                                "SELECT SecurityId FROM portfolio.Security "
                                "WHERE Symbol=:s AND SecurityType='equity'"
                            ), {"s": sym}).fetchone()
                            if ex:
                                return ex[0]
                            row = _conn.execute(_text(
                                "INSERT INTO portfolio.Security (Symbol, SecurityType, Multiplier) "
                                "OUTPUT INSERTED.SecurityId VALUES (:s,'equity',1)"
                            ), {"s": sym}).fetchone()
                            return row[0]

                        def _insert_eq(sec_id, sym, qty, price):
                            _conn.execute(_text("""
                                INSERT INTO portfolio.[Transaction]
                                    (BusinessDate, AccountId, TradeGroupId, StrategyName,
                                     SecurityId, Direction, Quantity, TransactionPrice,
                                     Commission, LegType, Source, Notes)
                                VALUES (:d, 1, :tg, :strat, :sid, 'Buy', :qty, :px,
                                        0, :lt, 'Screener', :n)
                            """), {"d": _today2, "tg": _tgid, "strat": "TLT / SPY Rotation",
                                   "sid": sec_id, "qty": qty, "px": float(price or 0),
                                   "lt": sym, "n": _note})

                        if spy_shares > 0:
                            _insert_eq(_ensure_equity("SPY"), "SPY", spy_shares, _r["spy_price"])
                            _saved2 += 1
                        if tlt_shares > 0:
                            _insert_eq(_ensure_equity("TLT"), "TLT", tlt_shares, _r["tlt_price"])
                            _saved2 += 1

                    st.success(f"✅ {_saved2} position(s) saved to Paper Trades — view in Paper Trading tab.")
                except Exception as _ex2:
                    st.error(f"DB save failed: {_ex2}")

    # ══════════════════════════════════════════════════════════════════════════
    # VOL REGIME CALENDAR SPREAD SCREENER — AI-predicted IV compression/expansion
    # ══════════════════════════════════════════════════════════════════════════
    t_volcal = _strat_tabs.get("vol_calendar_spread")
    if t_volcal is not None:
      with t_volcal:
        st.caption(
            "Scores any optionable ticker using a trained **XGBoost vol-regime classifier**. "
            "Signal: **COMPRESS** → short calendar (credit) | **EXPAND** → long calendar (debit) | "
            "**NEUTRAL** → no trade.  "
            "16 features: IV term structure, VRP, VIX context, news sentiment."
        )

        _vc_col1, _vc_col2, _vc_col3 = st.columns(3)
        _vc_univ  = _vc_col1.selectbox(
            "Universe", list(UNIVERSES.keys()), index=0, key=kp("vc_univ")
        )
        _vc_custom = _vc_col2.text_input(
            "Custom tickers (comma-separated)", placeholder="AAPL, TSLA, NVDA", key=kp("vc_custom")
        )
        _vc_min_conf = _vc_col3.slider(
            "Min confidence", 0.40, 0.90, 0.55, 0.05, key=kp("vc_conf"),
            help="Only show signals above this XGBoost probability threshold"
        )

        _vc_scan_btn = st.button("📅 Run Vol-Regime Scan", key=kp("vc_scan_btn"))

        if _vc_scan_btn:
            if not api_key:
                st.warning("Enter a Polygon API key in the sidebar.")
            else:
                _vc_tickers = (
                    [t.strip().upper() for t in _vc_custom.split(",") if t.strip()]
                    if _vc_custom.strip()
                    else UNIVERSES[_vc_univ]
                )
                try:
                    from alan_trader.strategies.vol_calendar_spread import VolCalendarSpreadStrategy
                    from alan_trader.data.polygon_client import PolygonClient
                    import datetime as _dt

                    _vc_strat  = VolCalendarSpreadStrategy()
                    _vc_client = PolygonClient(api_key=api_key)
                    _vc_today  = _dt.date.today()
                    _vc_from   = (_vc_today - _dt.timedelta(days=365)).isoformat()
                    _vc_to     = _vc_today.isoformat()

                    def _vc_fetch_prices(ticker):
                        bars = _vc_client._get(
                            f"/v2/aggs/ticker/{ticker}/range/1/day/{_vc_from}/{_vc_to}",
                            {"adjusted": "true", "sort": "asc", "limit": 365},
                        ).get("results", [])
                        if not bars:
                            return None, None
                        import pandas as _pd2
                        df = _pd2.DataFrame(bars)
                        df["date"] = _pd2.to_datetime(df["t"], unit="ms").dt.date
                        df = df.rename(columns={"o": "open", "h": "high", "l": "low",
                                                 "c": "close", "v": "volume"})
                        df = df.set_index("date")
                        spot = float(df["close"].iloc[-1])
                        return df, spot

                    def _vc_fetch_vix():
                        try:
                            from alan_trader.db.client import get_engine as _vge, get_vix_bars as _gvb
                            import datetime as _dt2
                            _veng = _vge()
                            _vdf  = _gvb(_veng, _vc_today - _dt2.timedelta(days=10), _vc_today)
                            if _vdf is not None and not _vdf.empty:
                                _vcol = "close" if "close" in _vdf.columns else _vdf.columns[0]
                                return float(_vdf[_vcol].iloc[-1])
                        except Exception:
                            pass
                        return None

                    _vc_results = []
                    _vc_debug: list[str] = []
                    _prog = st.progress(0, text="Scanning…")
                    _vc_vix = _vc_fetch_vix() or 20.0
                    _vc_debug.append(f"VIX: {_vc_vix:.1f}")

                    for _idx, _vc_ticker in enumerate(_vc_tickers):
                        _prog.progress((_idx + 1) / len(_vc_tickers), text=f"Scanning {_vc_ticker}…")
                        try:
                            _price_df, _spot = _vc_fetch_prices(_vc_ticker)
                            if _price_df is None or len(_price_df) < 25:
                                _vc_debug.append(f"{_vc_ticker}: SKIP — price too short ({len(_price_df) if _price_df is not None else 0} rows)")
                                continue

                            _chain = _vc_client.get_options_chain(_vc_ticker)
                            if _chain is None or _chain.empty:
                                _vc_debug.append(f"{_vc_ticker}: SKIP — empty chain from Polygon")
                                continue

                            import datetime as _dt2
                            _feat = _vc_strat._build_feature_row(
                                date            = _dt2.date.today(),
                                spot            = _spot,
                                chain_df        = _chain,
                                price_df        = _price_df,
                                vix_series      = pd.Series([_vc_vix]),
                                front_iv_history= pd.Series(dtype=float),
                                back_iv_history = pd.Series(dtype=float),
                                news_df         = None,
                                spy_price_df    = None,
                            )
                            if _feat is None:
                                _vc_debug.append(f"{_vc_ticker}: SKIP — feature row returned None (chain cols: {list(_chain.columns)})")
                                continue

                            # Load saved model if available
                            _loaded = _vc_strat.load_model(_vc_ticker)
                            if not _loaded or _vc_strat._model is None:
                                _vc_debug.append(f"{_vc_ticker}: SKIP — no saved model (looked for vol_calendar_{_vc_ticker}.pkl)")
                                continue

                            _sig = _vc_strat.predict_regime(_feat)
                            _vc_debug.append(
                                f"{_vc_ticker}: signal={_sig['signal']} conf={_sig['confidence']:.0%} "
                                f"front_iv={_feat.get('front_iv',0):.1f} vrp={_feat.get('vrp',0):.2f}"
                            )
                            if _sig["signal"] == "NEUTRAL":
                                continue
                            if _sig["confidence"] < _vc_min_conf:
                                continue

                            _vc_results.append({
                                "Ticker":      _vc_ticker,
                                "Signal":      _sig["signal"],
                                "Confidence":  round(_sig["confidence"], 3),
                                "Trade":       _sig.get("trade_type", ""),
                                "p(COMPRESS)": round(_sig["probabilities"].get("COMPRESS", 0), 3),
                                "p(NEUTRAL)":  round(_sig["probabilities"].get("NEUTRAL", 0), 3),
                                "p(EXPAND)":   round(_sig["probabilities"].get("EXPAND", 0), 3),
                                "front_iv":    round(_feat.get("front_iv", 0), 1),
                                "back_iv":     round(_feat.get("back_iv", 0), 1),
                                "vrp":         round(_feat.get("vrp", 0), 2),
                                "front_ivr":   round(_feat.get("front_ivr", 0), 3),
                                "Spot":        _spot,
                            })
                        except Exception as _vc_e:
                            _vc_debug.append(f"{_vc_ticker}: ERROR — {type(_vc_e).__name__}: {_vc_e}")

                    _prog.empty()

                    with st.expander("🔍 Scan debug", expanded=not _vc_results):
                        for _dl in _vc_debug:
                            st.write(_dl)

                    if not _vc_results:
                        st.info(
                            "No signals above the confidence threshold. "
                            "Check the debug log above for details."
                        )
                    else:
                        import pandas as _pd3
                        _vc_df = _pd3.DataFrame(_vc_results).sort_values("Confidence", ascending=False)
                        st.session_state["vc_scan_results"] = _vc_df

                except Exception as _vc_err:
                    st.error(f"Scan error: {_vc_err}")

        if "vc_scan_results" in st.session_state:
            _vc_df = st.session_state["vc_scan_results"]

            def _vc_badge(row):
                color = "#ef5350" if row["Signal"] == "COMPRESS" else "#26a69a"
                return (
                    f"<span style='background:{color};color:#fff;padding:2px 8px;"
                    f"border-radius:4px;font-weight:600'>{row['Signal']}</span> "
                    f"<span style='color:#b0b8c8'>{row['Trade']}</span>"
                )

            st.markdown(f"**{len(_vc_df)} signal(s) found**")
            for _, _row in _vc_df.iterrows():
                with st.expander(
                    f"{_row['Ticker']}  —  {_row['Signal']}  ({_row['Confidence']:.0%} conf)  "
                    f"| Front IV {_row['front_iv']:.1f}%  Back IV {_row['back_iv']:.1f}%  "
                    f"VRP {_row['vrp']:+.2f}",
                    expanded=False,
                ):
                    _ec1, _ec2, _ec3, _ec4, _ec5 = st.columns(5)
                    _ec1.metric("Signal", _row["Signal"])
                    _ec2.metric("Confidence", f"{_row['Confidence']:.0%}")
                    _ec3.metric("Front IV", f"{_row['front_iv']:.1f}%")
                    _ec4.metric("VRP", f"{_row['vrp']:+.2f}")
                    _ec5.metric("Front IVR", f"{_row['front_ivr']:.2f}")

                    st.markdown(
                        f"Probabilities — "
                        f"COMPRESS: **{_row['p(COMPRESS)']:.0%}**  "
                        f"NEUTRAL: **{_row['p(NEUTRAL)']:.0%}**  "
                        f"EXPAND: **{_row['p(EXPAND)']:.0%}**"
                    )

                    if st.button(f"Save {_row['Ticker']} calendar to Paper Trades",
                                 key=kp(f"vc_save_{_row['Ticker']}")):
                        try:
                            from alan_trader.db.client import get_engine as _vc_get_eng
                            from sqlalchemy import text as _vc_text
                            import datetime as _dt3, uuid as _vc_uuid

                            _vc_eng    = _vc_get_eng()
                            _vc_date   = _dt3.date.today()
                            _vc_tgid   = str(_vc_uuid.uuid4())
                            _is_short  = _row["Signal"] == "COMPRESS"
                            _trade_lbl = "Short Calendar" if _is_short else "Long Calendar"
                            _note_str  = (
                                f"Vol Calendar|{_row['Ticker']}|{_row['Signal']}|"
                                f"conf={_row['Confidence']:.0%}|frontIV={_row['front_iv']:.1f}"
                            )

                            with _vc_eng.begin() as _vc_conn:
                                def _ensure_opt(sym, leg):
                                    ex = _vc_conn.execute(_vc_text(
                                        "SELECT SecurityId FROM portfolio.Security "
                                        "WHERE Symbol=:s AND SecurityType='option'"
                                    ), {"s": sym}).fetchone()
                                    if ex:
                                        return ex[0]
                                    row2 = _vc_conn.execute(_vc_text(
                                        "INSERT INTO portfolio.Security (Symbol, SecurityType, Multiplier) "
                                        "OUTPUT INSERTED.SecurityId VALUES (:s,'option',100)"
                                    ), {"s": sym}).fetchone()
                                    return row2[0]

                                def _ins_leg(sid, direction, qty, price, leg_type):
                                    _vc_conn.execute(_vc_text("""
                                        INSERT INTO portfolio.[Transaction]
                                            (BusinessDate, AccountId, TradeGroupId, StrategyName,
                                             SecurityId, Direction, Quantity, TransactionPrice,
                                             Commission, LegType, Source, Notes)
                                        VALUES (:d, 1, :tg, :strat, :sid, :dir, :qty, :px,
                                                0, :lt, 'Screener', :n)
                                    """), {
                                        "d": _vc_date, "tg": _vc_tgid,
                                        "strat": "Vol Regime Calendar Spread",
                                        "sid": sid, "dir": direction,
                                        "qty": qty, "px": 0.0,
                                        "lt": leg_type, "n": _note_str,
                                    })

                                _sym_front = f"{_row['Ticker']}_FRONT_CAL"
                                _sym_back  = f"{_row['Ticker']}_BACK_CAL"
                                _sid_front = _ensure_opt(_sym_front, "front")
                                _sid_back  = _ensure_opt(_sym_back, "back")

                                if _is_short:
                                    # Short calendar: sell back, buy front
                                    _ins_leg(_sid_back,  "Sell", 1, 0.0, "BackLeg")
                                    _ins_leg(_sid_front, "Buy",  1, 0.0, "FrontLeg")
                                else:
                                    # Long calendar: buy back, sell front
                                    _ins_leg(_sid_back,  "Buy",  1, 0.0, "BackLeg")
                                    _ins_leg(_sid_front, "Sell", 1, 0.0, "FrontLeg")

                            st.success(f"✅ {_trade_lbl} on {_row['Ticker']} saved to Paper Trades.")
                        except Exception as _vc_save_err:
                            st.error(f"DB save failed: {_vc_save_err}")

    # ══════════════════════════════════════════════════════════════════════════
    # DIVIDEND ARBITRAGE SCREENER — buy before ex-div, hedge with put
    # ══════════════════════════════════════════════════════════════════════════
    t_divarb = _strat_tabs.get("dividend_arb")
    if t_divarb is not None:
      with t_divarb:
        import datetime as _dt2
        st.caption(
            "Scans dividend-paying tickers approaching their ex-dividend date. "
            "Signal fires when net yield (dividend − put hedge cost) is positive "
            "within the entry window."
        )

        _da_col1, _da_col2, _da_col3 = st.columns(3)
        _da_entry_days = _da_col1.number_input("Entry days before ex-div", 1, 10, 3, key=kp("da_entry"))
        _da_min_yield  = _da_col2.number_input("Min annual div yield (%)", 0.1, 5.0, 0.5, 0.1, key=kp("da_yield")) / 100
        _da_custom     = _da_col3.text_input("Custom tickers (comma-separated)",
                                              placeholder="AAPL, MSFT, JNJ", key=kp("da_custom"))

        _DA_DEFAULT = ["AAPL", "MSFT", "JNJ", "KO", "PG", "VZ", "T", "XOM",
                       "CVX", "IBM", "MCD", "MMM", "PFE", "INTC", "WMT"]
        _da_tickers = (
            [t.strip().upper() for t in _da_custom.split(",") if t.strip()]
            if _da_custom.strip() else _DA_DEFAULT
        )

        if st.button("💰 Run Dividend Arb Scan", key=kp("da_scan_btn")):
            if not api_key:
                st.warning("Enter a Polygon API key in the sidebar.")
            else:
                from alan_trader.data.polygon_client import PolygonClient as _PC2
                from alan_trader.backtest.engine import bs_price as _bs2
                import requests as _req2

                _da_client = _PC2(api_key)
                _da_today  = _dt2.date.today()
                _da_rows   = []

                with st.spinner(f"Scanning {len(_da_tickers)} tickers for dividend events…"):
                    for _da_tkr in _da_tickers:
                        try:
                            _div_url = (
                                f"https://api.polygon.io/v3/reference/dividends"
                                f"?ticker={_da_tkr}&limit=3&apiKey={api_key}"
                            )
                            _div_resp = _req2.get(_div_url, timeout=10).json()
                            _divs = _div_resp.get("results", [])
                            _next_div = None
                            for _d in _divs:
                                _ex = _d.get("ex_dividend_date", "")
                                if _ex and _dt2.date.fromisoformat(_ex) >= _da_today:
                                    _next_div = _d
                                    break

                            if _next_div is None:
                                _da_rows.append({"Ticker": _da_tkr, "Signal": "—",
                                                 "Reason": "No upcoming ex-div"})
                                continue

                            _ex_date    = _dt2.date.fromisoformat(_next_div["ex_dividend_date"])
                            _div_amt    = float(_next_div.get("cash_amount", 0) or 0)
                            _days_to_ex = (_ex_date - _da_today).days

                            _snap2 = _da_client.get_snapshot(_da_tkr)
                            _S2    = (_snap2.get("day", {}).get("c") or
                                      _snap2.get("lastTrade", {}).get("p") or 0)
                            if _S2 <= 0:
                                _da_rows.append({"Ticker": _da_tkr, "Signal": "—",
                                                 "Reason": "No price"})
                                continue

                            _div_yield2      = _div_amt / _S2
                            _put_dte2        = max(7, _days_to_ex + 3)
                            _T2              = _put_dte2 / 252
                            _put_cost_share  = _bs2(_S2, _S2, _T2, 0.045, 0.30, "put") / 100
                            _net_yield       = _div_yield2 - _put_cost_share / _S2

                            _signal = "—"
                            if _days_to_ex <= _da_entry_days and _net_yield > 0:
                                _conf = min(1.0, _net_yield / 0.003)
                                _signal = f"BUY ({_conf:.0%} conf)"

                            _da_rows.append({
                                "Ticker":      _da_tkr,
                                "Price":       round(_S2, 2),
                                "Ex-Date":     str(_ex_date),
                                "Days to Ex":  _days_to_ex,
                                "Div $":       _div_amt,
                                "Div Yield %": round(_div_yield2 * 100, 3),
                                "Put Cost %":  round(_put_cost_share / _S2 * 100, 3),
                                "Net Yield %": round(_net_yield * 100, 3),
                                "Signal":      _signal,
                                "Reason":      "OK",
                            })
                        except Exception as _da_err:
                            _da_rows.append({"Ticker": _da_tkr, "Signal": "—",
                                             "Reason": str(_da_err)[:60]})

                st.session_state["da_scan_results"] = _da_rows

        if "da_scan_results" in st.session_state:
            _da_df = pd.DataFrame(st.session_state["da_scan_results"])
            _da_signals = _da_df[_da_df["Signal"] != "—"]
            if not _da_signals.empty:
                st.success(f"**Opportunities:** {', '.join(_da_signals['Ticker'].tolist())}")
            else:
                st.info("No dividend arb signals. Check back closer to ex-div dates.")

            _da_display = _da_df[[c for c in [
                "Ticker", "Price", "Ex-Date", "Days to Ex",
                "Div $", "Div Yield %", "Put Cost %", "Net Yield %", "Signal"
            ] if c in _da_df.columns]].copy()

            st.dataframe(
                _da_display.sort_values("Days to Ex", na_position="last")
                if "Days to Ex" in _da_display.columns else _da_display,
                hide_index=True, width="stretch",
                column_config={
                    "Price":       cc.NumberColumn("Price",     format="$%.2f"),
                    "Div $":       cc.NumberColumn("Div $",     format="$%.4f"),
                    "Div Yield %": cc.NumberColumn("Div Yield", format="%.3f%%"),
                    "Put Cost %":  cc.NumberColumn("Put Cost",  format="%.3f%%"),
                    "Net Yield %": cc.NumberColumn("Net Yield", format="%.3f%%"),
                    "Days to Ex":  cc.NumberColumn("Days to Ex-Div"),
                },
            )
            st.caption(
                "**Net Yield** = Dividend − estimated ATM put cost. "
                "Signal fires when Net Yield > 0 within entry window. "
                "Put cost uses 30% IV estimate — verify against live chain before trading."
            )

    # ══════════════════════════════════════════════════════════════════════════
    # CONVERSION ARB SCREENER — put-call parity implied dividend edge
    # ══════════════════════════════════════════════════════════════════════════
    t_convarb = _strat_tabs.get("conversion_arb")
    if t_convarb is not None:
      with t_convarb:
        import datetime as _dt3, math as _math3
        st.caption(
            "Scans for **put-call parity mispricing** of upcoming dividends. "
            "Computes implied dividend from live ATM call/put pair and compares to actual. "
            "Signal when edge (actual − implied) > threshold. "
            "Trade: long stock + long put + short call (delta-neutral conversion)."
        )

        _ca_col1, _ca_col2, _ca_col3 = st.columns(3)
        _ca_min_edge = _ca_col1.number_input("Min edge ($)", 0.01, 1.0, 0.05, 0.01, key=kp("ca_edge"))
        _ca_dte_max  = _ca_col2.number_input("Max DTE for options", 7, 60, 30, key=kp("ca_dte"))
        _ca_custom   = _ca_col3.text_input("Custom tickers (comma-separated)",
                                            placeholder="AAPL, MSFT, JNJ", key=kp("ca_custom"))

        _CA_DEFAULT = ["AAPL", "MSFT", "JNJ", "KO", "PG", "VZ", "T",
                       "XOM", "CVX", "IBM", "MCD", "PFE", "WMT"]
        _ca_tickers = (
            [t.strip().upper() for t in _ca_custom.split(",") if t.strip()]
            if _ca_custom.strip() else _CA_DEFAULT
        )

        if st.button("⚖️ Run Conversion Arb Scan", key=kp("ca_scan_btn")):
            if not api_key:
                st.warning("Enter a Polygon API key in the sidebar.")
            else:
                from alan_trader.data.polygon_client import PolygonClient as _PC3
                import requests as _req3
                import numpy as _np3

                _ca_client = _PC3(api_key)
                _ca_today  = _dt3.date.today()
                _ca_rows   = []
                _r_rate    = 0.045

                with st.spinner(f"Scanning {len(_ca_tickers)} tickers for conversion arb…"):
                    for _ca_tkr in _ca_tickers:
                        try:
                            _div_url2  = (
                                f"https://api.polygon.io/v3/reference/dividends"
                                f"?ticker={_ca_tkr}&limit=3&apiKey={api_key}"
                            )
                            _div_resp2 = _req3.get(_div_url2, timeout=10).json()
                            _divs2     = _div_resp2.get("results", [])
                            _next_div2 = None
                            for _d2 in _divs2:
                                _ex2 = _d2.get("ex_dividend_date", "")
                                if _ex2 and _dt3.date.fromisoformat(_ex2) >= _ca_today:
                                    _next_div2 = _d2
                                    break

                            if _next_div2 is None:
                                _ca_rows.append({"Ticker": _ca_tkr, "Signal": "—",
                                                 "Reason": "No upcoming ex-div"})
                                continue

                            _ca_ex_date = _dt3.date.fromisoformat(_next_div2["ex_dividend_date"])
                            _ca_div_amt = float(_next_div2.get("cash_amount", 0) or 0)

                            _ca_snap = _ca_client.get_snapshot(_ca_tkr)
                            _ca_S    = (_ca_snap.get("day", {}).get("c") or
                                        _ca_snap.get("lastTrade", {}).get("p") or 0)
                            if _ca_S <= 0:
                                _ca_rows.append({"Ticker": _ca_tkr, "Signal": "—",
                                                 "Reason": "No price"})
                                continue

                            _exp_gte2 = _ca_ex_date.isoformat()
                            _exp_lte2 = (_ca_today + _dt3.timedelta(days=_ca_dte_max)).isoformat()

                            _ca_chain = _ca_client.get_options_chain(
                                _ca_tkr,
                                expiration_date_gte=_exp_gte2,
                                expiration_date_lte=_exp_lte2,
                                strike_price_gte=round(_ca_S * 0.90, 2),
                                strike_price_lte=round(_ca_S * 1.10, 2),
                            )
                            if _ca_chain is None or _ca_chain.empty:
                                _ca_rows.append({"Ticker": _ca_tkr, "Signal": "—",
                                                 "Reason": "No chain data"})
                                continue

                            _ca_chain["strike"] = pd.to_numeric(_ca_chain["strike"], errors="coerce")
                            _ca_chain["bid"]    = pd.to_numeric(_ca_chain.get("bid", pd.Series(dtype=float)), errors="coerce")
                            _ca_chain["ask"]    = pd.to_numeric(_ca_chain.get("ask", pd.Series(dtype=float)), errors="coerce")
                            _ca_chain["mid"]    = (_ca_chain["bid"] + _ca_chain["ask"]) / 2

                            _ca_exps = sorted(_ca_chain["expiration"].dropna().unique())
                            if not _ca_exps:
                                _ca_rows.append({"Ticker": _ca_tkr, "Signal": "—",
                                                 "Reason": "No valid expiry"})
                                continue

                            _ca_exp_use = _ca_exps[0]
                            _ca_leg     = _ca_chain[_ca_chain["expiration"] == _ca_exp_use]
                            _ca_T       = max(1, (_dt3.date.fromisoformat(str(_ca_exp_use)[:10]) - _ca_today).days) / 252

                            _ca_strikes = _ca_leg["strike"].dropna().unique()
                            _ca_K       = float(_ca_strikes[_np3.argmin(_np3.abs(_ca_strikes - _ca_S))])

                            _type_col3 = "type" if "type" in _ca_leg.columns else "contract_type"
                            _call_row3 = _ca_leg[(_ca_leg["strike"] == _ca_K) &
                                                  (_ca_leg[_type_col3].str.lower().str.startswith("c"))]
                            _put_row3  = _ca_leg[(_ca_leg["strike"] == _ca_K) &
                                                  (_ca_leg[_type_col3].str.lower().str.startswith("p"))]

                            if _call_row3.empty or _put_row3.empty:
                                _ca_rows.append({"Ticker": _ca_tkr, "Signal": "—",
                                                 "Reason": "No ATM call+put pair"})
                                continue

                            _ca_C_mid = _call_row3.iloc[0]["mid"]
                            _ca_P_mid = _put_row3.iloc[0]["mid"]

                            if pd.isna(_ca_C_mid) or pd.isna(_ca_P_mid) or _ca_C_mid <= 0 or _ca_P_mid <= 0:
                                _ca_rows.append({"Ticker": _ca_tkr, "Signal": "—",
                                                 "Reason": "Missing call/put mid price"})
                                continue

                            # D_implied = S - K*e^(-rT) + P - C
                            _ca_D_implied = _ca_S - _ca_K * _math3.exp(-_r_rate * _ca_T) + float(_ca_P_mid) - float(_ca_C_mid)
                            _ca_edge      = _ca_div_amt - _ca_D_implied

                            _ca_signal = "—"
                            if _ca_edge >= _ca_min_edge:
                                _ca_signal = f"CONVERSION (+${_ca_edge:.3f} edge)"

                            _ca_rows.append({
                                "Ticker":       _ca_tkr,
                                "Price":        round(_ca_S, 2),
                                "Ex-Date":      str(_ca_ex_date),
                                "Expiry Used":  str(_ca_exp_use)[:10],
                                "Strike":       _ca_K,
                                "Call Mid":     round(float(_ca_C_mid), 4),
                                "Put Mid":      round(float(_ca_P_mid), 4),
                                "Actual Div":   _ca_div_amt,
                                "Implied Div":  round(_ca_D_implied, 4),
                                "Edge $":       round(_ca_edge, 4),
                                "Signal":       _ca_signal,
                            })

                        except Exception as _ca_err:
                            _ca_rows.append({"Ticker": _ca_tkr, "Signal": "—",
                                             "Reason": str(_ca_err)[:60]})

                st.session_state["ca_scan_results"] = _ca_rows

        if "ca_scan_results" in st.session_state:
            _ca_df = pd.DataFrame(st.session_state["ca_scan_results"])
            _ca_signals = _ca_df[_ca_df["Signal"] != "—"]
            if not _ca_signals.empty:
                st.success(f"**Opportunities:** {', '.join(_ca_signals['Ticker'].tolist())}")
            else:
                st.info("No conversion arb edges found. Market is pricing dividends fairly.")

            _ca_display = _ca_df[[c for c in [
                "Ticker", "Price", "Ex-Date", "Expiry Used", "Strike",
                "Call Mid", "Put Mid", "Actual Div", "Implied Div", "Edge $", "Signal"
            ] if c in _ca_df.columns]].copy()

            st.dataframe(
                _ca_display.sort_values("Edge $", ascending=False)
                if "Edge $" in _ca_display.columns else _ca_display,
                hide_index=True, width="stretch",
                column_config={
                    "Price":       cc.NumberColumn("Price",       format="$%.2f"),
                    "Strike":      cc.NumberColumn("Strike",      format="$%.1f"),
                    "Call Mid":    cc.NumberColumn("Call Mid",    format="$%.4f"),
                    "Put Mid":     cc.NumberColumn("Put Mid",     format="$%.4f"),
                    "Actual Div":  cc.NumberColumn("Actual Div",  format="$%.4f"),
                    "Implied Div": cc.NumberColumn("Implied Div", format="$%.4f"),
                    "Edge $":      cc.NumberColumn("Edge $",      format="$%.4f"),
                },
            )
            st.caption(
                "**Edge** = Actual dividend − Implied dividend from put-call parity. "
                "Positive edge means options are underpricing the dividend — enter CONVERSION: "
                "long stock + long put + short call (same strike, same expiry, delta-neutral)."
            )

    # ══════════════════════════════════════════════════════════════════════════
    # IVR CREDIT SPREAD SCREENER — scan for elevated IV Rank
    # ══════════════════════════════════════════════════════════════════════════
    if t_ivr is not None:
      with t_ivr:
        st.caption(
            "Scans the selected universe for elevated **IV Rank** (VIX percentile over 52 weeks). "
            "IVR ≥ 50% → sell premium. Trend filter (50-day MA) picks Bull Put vs Bear Call spread."
        )

        _ivr_col1, _ivr_col2, _ivr_col3 = st.columns(3)
        _ivr_min      = _ivr_col1.slider("Min IVR threshold", 0.30, 0.80, 0.50, 0.05,
                                          key=kp("ivr_min"),
                                          help="Minimum IV Rank (0–1) to flag as a sell candidate")
        _ivr_dte      = _ivr_col2.slider("DTE target", 21, 60, 45, 1, key=kp("ivr_dte"),
                                          help="Target days-to-expiry for spread entry")
        _ivr_tickers  = _ivr_col3.multiselect(
            "Tickers to scan",
            options=sorted({t for lst in UNIVERSES.values() for t in lst}),
            default=["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "META"],
            key=kp("ivr_tickers"),
        )

        if st.button("📡 Run IVR Scan", key=kp("ivr_btn")):
            if not api_key:
                st.warning("Enter a Polygon API key in the sidebar.")
            elif not _ivr_tickers:
                st.warning("Select at least one ticker.")
            else:
                from alan_trader.data.polygon_client import PolygonClient as _PCI
                _ivr_client = _PCI(api_key=api_key)
                _ivr_rows = []
                _ivr_prog = st.progress(0, text="Scanning tickers…")

                for _ii, _ivr_tkr in enumerate(_ivr_tickers):
                    _ivr_prog.progress((_ii + 1) / len(_ivr_tickers), text=f"IVR: {_ivr_tkr}")
                    try:
                        # Fetch 1-year daily price bars for IVR calculation
                        import datetime as _dt_ivr
                        _ivr_to   = _dt_ivr.date.today()
                        _ivr_from = _ivr_to - _dt_ivr.timedelta(days=380)
                        _ivr_bars = _ivr_client.get_daily_bars(_ivr_tkr, str(_ivr_from), str(_ivr_to))
                        if _ivr_bars is None or _ivr_bars.empty:
                            _ivr_rows.append({"Ticker": _ivr_tkr, "Signal": "—", "Reason": "No price data"})
                            continue

                        # Use close price as IV proxy (VIX for SPY, else skip)
                        # Fetch options chain for IV
                        _ivr_chain = _ivr_client.get_options_chain(_ivr_tkr)
                        if _ivr_chain is None or _ivr_chain.empty:
                            _ivr_rows.append({"Ticker": _ivr_tkr, "Signal": "—", "Reason": "No options chain"})
                            continue

                        _atm_iv = _ivr_chain["iv"].dropna()
                        if _atm_iv.empty:
                            _ivr_rows.append({"Ticker": _ivr_tkr, "Signal": "—", "Reason": "No IV data"})
                            continue
                        _iv_now = float(_atm_iv.median())

                        # Estimate IVR from 52-week high/low of close-to-close realized vol
                        _close_col = "close" if "close" in _ivr_bars.columns else _ivr_bars.columns[-1]
                        _closes = _ivr_bars[_close_col].dropna()
                        if len(_closes) < 30:
                            _ivr_rows.append({"Ticker": _ivr_tkr, "Signal": "—", "Reason": "Insufficient history"})
                            continue

                        _spot = float(_closes.iloc[-1])
                        _ma50 = float(_closes.tail(50).mean()) if len(_closes) >= 50 else _spot

                        # Use chain IV rolling proxy for IVR
                        _iv_52w_high = _iv_now * 1.5   # approximation — real IVR needs historical IV
                        _iv_52w_low  = _iv_now * 0.6
                        _ivr_val = (_iv_now - _iv_52w_low) / max(_iv_52w_high - _iv_52w_low, 0.001)
                        _ivr_val = max(0.0, min(1.0, _ivr_val))

                        _direction = "Bull Put Spread" if _spot > _ma50 else "Bear Call Spread"
                        _signal = "—"
                        if _ivr_val >= _ivr_min:
                            _signal = f"SELL {_direction}"

                        _ivr_rows.append({
                            "Ticker":    _ivr_tkr,
                            "Price":     round(_spot, 2),
                            "IV (ATM)":  round(_iv_now * 100, 1),
                            "IVR (est)": round(_ivr_val, 2),
                            "50d MA":    round(_ma50, 2),
                            "Trend":     "↑ Bullish" if _spot > _ma50 else "↓ Bearish",
                            "Signal":    _signal,
                        })
                    except Exception as _ivr_e:
                        _ivr_rows.append({"Ticker": _ivr_tkr, "Signal": "—", "Reason": str(_ivr_e)[:60]})

                _ivr_prog.empty()
                st.session_state["ivr_scan_results"] = _ivr_rows

        if "ivr_scan_results" in st.session_state:
            _ivr_df = pd.DataFrame(st.session_state["ivr_scan_results"])
            _ivr_hits = _ivr_df[_ivr_df["Signal"] != "—"]
            if not _ivr_hits.empty:
                st.success(f"**Sell candidates:** {', '.join(_ivr_hits['Ticker'].tolist())}")
            else:
                st.info("No tickers met the IVR threshold — market-wide IV may be depressed.")
            _ivr_display_cols = [c for c in ["Ticker", "Price", "IV (ATM)", "IVR (est)", "50d MA", "Trend", "Signal"] if c in _ivr_df.columns]
            st.dataframe(
                _ivr_df[_ivr_display_cols].sort_values("IVR (est)", ascending=False)
                if "IVR (est)" in _ivr_df.columns else _ivr_df[_ivr_display_cols],
                hide_index=True, width="stretch",
                column_config={
                    "Price":     cc.NumberColumn("Price",     format="$%.2f"),
                    "IV (ATM)":  cc.NumberColumn("IV ATM %",  format="%.1f%%"),
                    "IVR (est)": cc.NumberColumn("IVR",       format="%.2f"),
                    "50d MA":    cc.NumberColumn("50d MA",    format="$%.2f"),
                },
            )
            st.caption(
                "**IVR** = IV Rank estimate. Live IVR requires 52-week IV history; "
                "this uses a proxy from the current chain IV vs an estimated high/low range. "
                "For precise IVR, run the backtest with VIX data from the database."
            )

    # ══════════════════════════════════════════════════════════════════════════
    # VIX SPIKE FADE SCREENER — monitor VIX panic conditions
    # ══════════════════════════════════════════════════════════════════════════
    if t_vixfade is not None:
      with t_vixfade:
        st.caption(
            "Monitors VIX for **panic spike conditions** that signal a mean-reversion entry. "
            "Entry triggers when VIX > spike threshold AND > 130% of its 20-day average, "
            "while SPY remains within 5% of its 200-day MA (not a regime break)."
        )

        _vf_col1, _vf_col2, _vf_col3 = st.columns(3)
        _vf_spike_thr  = _vf_col1.slider("Spike threshold (VIX)", 20, 40, 25, 1, key=kp("vf_sthr"),
                                          help="Absolute VIX level to classify as a spike")
        _vf_spike_ratio = _vf_col2.slider("Spike ratio vs 20d avg", 1.10, 2.00, 1.30, 0.05, key=kp("vf_sratio"),
                                           help="VIX must be at least this multiple of its 20-day average")
        _vf_revert_thr  = _vf_col3.slider("Revert threshold (VIX)", 15, 30, 22, 1, key=kp("vf_rthr"),
                                           help="Exit signal when VIX drops below this level")

        if st.button("📡 Check VIX Conditions", key=kp("vf_btn")):
            if not api_key:
                st.warning("Enter a Polygon API key in the sidebar.")
            else:
                from alan_trader.data.polygon_client import PolygonClient as _PCF
                _vf_client = _PCF(api_key=api_key)
                try:
                    import datetime as _dt_vf
                    _vf_to   = _dt_vf.date.today()
                    _vf_from = _vf_to - _dt_vf.timedelta(days=300)

                    _vf_vix  = _vf_client.get_daily_bars("VIX", str(_vf_from), str(_vf_to))
                    _vf_spy  = _vf_client.get_daily_bars("SPY", str(_vf_from), str(_vf_to))

                    _vix_close = _vf_vix["close"].dropna() if _vf_vix is not None and not _vf_vix.empty else None
                    _spy_close = _vf_spy["close"].dropna() if _vf_spy is not None and not _vf_spy.empty else None

                    if _vix_close is not None and len(_vix_close) >= 20:
                        _vix_now     = float(_vix_close.iloc[-1])
                        _vix_20d_avg = float(_vix_close.tail(20).mean())
                        _vix_ratio   = _vix_now / _vix_20d_avg if _vix_20d_avg > 0 else 0.0
                        _spy_now     = float(_spy_close.iloc[-1]) if _spy_close is not None else 0.0
                        _spy_200d    = float(_spy_close.tail(200).mean()) if _spy_close is not None and len(_spy_close) >= 200 else _spy_now
                        _spy_pct_above_200d = (_spy_now / _spy_200d - 1) if _spy_200d > 0 else 0.0

                        _cond_spike     = _vix_now > _vf_spike_thr
                        _cond_ratio     = _vix_ratio >= _vf_spike_ratio
                        _cond_not_crash = _spy_pct_above_200d >= -0.05

                        _entry_signal = _cond_spike and _cond_ratio and _cond_not_crash
                        _exit_signal  = _vix_now < _vf_revert_thr

                        st.session_state["vf_scan_results"] = {
                            "vix_now": _vix_now, "vix_20d_avg": _vix_20d_avg,
                            "vix_ratio": _vix_ratio, "spy_now": _spy_now,
                            "spy_200d_ma": _spy_200d, "spy_pct_above_200d": _spy_pct_above_200d,
                            "entry_signal": _entry_signal, "exit_signal": _exit_signal,
                            "cond_spike": _cond_spike, "cond_ratio": _cond_ratio,
                            "cond_not_crash": _cond_not_crash,
                        }
                    else:
                        st.warning("Insufficient VIX history retrieved — check Polygon API key.")
                except Exception as _vf_e:
                    st.error(f"VIX scan error: {_vf_e}")

        if "vf_scan_results" in st.session_state:
            _vfr = st.session_state["vf_scan_results"]
            if _vfr.get("entry_signal"):
                st.success("🔥 **ENTRY SIGNAL ACTIVE** — Buy SPY bull call spread now.")
            elif _vfr.get("exit_signal"):
                st.info("✅ **VIX REVERTED** — Consider closing open position if held.")
            else:
                st.info("No signal — VIX conditions not yet at panic threshold.")

            _vf_m1, _vf_m2, _vf_m3 = st.columns(3)
            _vf_m1.metric("VIX (Current)", f"{_vfr.get('vix_now', 0):.2f}",
                          delta=f"vs 20d avg {_vfr.get('vix_20d_avg', 0):.1f}")
            _vf_m2.metric("VIX / 20d avg ratio", f"{_vfr.get('vix_ratio', 0):.2f}x",
                          delta=f"threshold {_vf_spike_ratio:.2f}x",
                          delta_color="inverse")
            _vf_m3.metric("SPY vs 200d MA", f"{_vfr.get('spy_pct_above_200d', 0)*100:+.1f}%",
                          delta="regime OK" if _vfr.get("cond_not_crash") else "⚠ CRASH REGIME",
                          delta_color="normal" if _vfr.get("cond_not_crash") else "inverse")

            st.markdown("#### Entry Conditions")
            _vf_c1, _vf_c2, _vf_c3 = st.columns(3)
            _vf_c1.metric(f"VIX > {_vf_spike_thr}", "✅ Yes" if _vfr.get("cond_spike") else "❌ No")
            _vf_c2.metric(f"VIX > {_vf_spike_ratio:.1f}× avg", "✅ Yes" if _vfr.get("cond_ratio") else "❌ No")
            _vf_c3.metric("SPY above 200d (−5% buffer)", "✅ Yes" if _vfr.get("cond_not_crash") else "❌ No")

    # ══════════════════════════════════════════════════════════════════════════
    # EARNINGS IV CRUSH SCREENER — upcoming earnings with high implied move
    # ══════════════════════════════════════════════════════════════════════════
    if t_eivcrush is not None:
      with t_eivcrush:
        st.caption(
            "Scans for upcoming earnings events where the **implied move exceeds historical average** by ≥ 1.2×. "
            "Sell an iron condor 1 day before earnings to harvest the systematic IV overpricing."
        )

        _eic_col1, _eic_col2, _eic_col3 = st.columns(3)
        _eic_min_imp  = _eic_col1.slider("Min implied move (%)", 2, 10, 4, 1, key=kp("eic_mimp"),
                                          help="Minimum ATM straddle implied move as % of spot")
        _eic_min_ivr  = _eic_col2.select_slider("Min implied/historical ratio",
                                                  options=[1.0, 1.1, 1.2, 1.3, 1.5, 2.0], value=1.2,
                                                  key=kp("eic_ivr"))
        _eic_tickers  = _eic_col3.multiselect(
            "Tickers to scan",
            options=sorted({t for lst in UNIVERSES.values() for t in lst}),
            default=["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "NFLX"],
            key=kp("eic_tickers"),
        )

        if st.button("📡 Scan Earnings IV", key=kp("eic_btn")):
            if not api_key:
                st.warning("Enter a Polygon API key in the sidebar.")
            elif not _eic_tickers:
                st.warning("Select at least one ticker.")
            else:
                from alan_trader.data.polygon_client import PolygonClient as _PCE
                from alan_trader.backtest.engine import bs_price as _eic_bs
                _eic_client = _PCE(api_key=api_key)
                _eic_rows = []
                _eic_prog = st.progress(0, text="Scanning earnings…")

                for _ei, _eic_tkr in enumerate(_eic_tickers):
                    _eic_prog.progress((_ei + 1) / len(_eic_tickers), text=f"Earnings IV: {_eic_tkr}")
                    try:
                        # Get current snapshot
                        _eic_snap = _eic_client.get_snapshot(_eic_tkr)
                        if _eic_snap is None:
                            _eic_rows.append({"Ticker": _eic_tkr, "Signal": "—", "Reason": "No snapshot"})
                            continue
                        _eic_S = float(_eic_snap.get("day", {}).get("c") or _eic_snap.get("lastTrade", {}).get("p") or 0)
                        if _eic_S <= 0:
                            _eic_rows.append({"Ticker": _eic_tkr, "Signal": "—", "Reason": "No price"})
                            continue

                        # Get ATM straddle IV
                        _eic_chain = _eic_client.get_options_chain(_eic_tkr)
                        if _eic_chain is None or _eic_chain.empty:
                            _eic_rows.append({"Ticker": _eic_tkr, "Signal": "—", "Reason": "No chain"})
                            continue

                        _eic_chain["strike"] = pd.to_numeric(_eic_chain.get("strike", pd.Series(dtype=float)), errors="coerce")
                        _eic_chain["iv"]     = pd.to_numeric(_eic_chain.get("iv",     pd.Series(dtype=float)), errors="coerce")
                        _eic_chain["atm_d"]  = (_eic_chain["strike"] - _eic_S).abs()
                        _eic_atm_row = _eic_chain.nsmallest(4, "atm_d")
                        _eic_iv = _eic_atm_row["iv"].dropna().mean()
                        if pd.isna(_eic_iv) or _eic_iv <= 0:
                            _eic_rows.append({"Ticker": _eic_tkr, "Signal": "—", "Reason": "No ATM IV"})
                            continue

                        # Implied 1-day move ≈ ATM straddle / spot = 0.8 * IV * sqrt(1/252)
                        import math as _eic_math
                        _eic_T1d = 1.0 / 252
                        _eic_c   = _eic_bs(_eic_S, _eic_S, _eic_T1d, 0.045, _eic_iv, "call")
                        _eic_p   = _eic_bs(_eic_S, _eic_S, _eic_T1d, 0.045, _eic_iv, "put")
                        _eic_imp_move = (_eic_c + _eic_p) / _eic_S

                        # Historical move — 30d realized vol proxy
                        import datetime as _dt_eic
                        _eic_bars = _eic_client.get_daily_bars(_eic_tkr,
                                                                str(_dt_eic.date.today() - _dt_eic.timedelta(days=90)),
                                                                str(_dt_eic.date.today()))
                        if _eic_bars is not None and not _eic_bars.empty and len(_eic_bars) >= 5:
                            _cl = "close" if "close" in _eic_bars.columns else _eic_bars.columns[-1]
                            _eic_hist_move = float(_eic_bars[_cl].pct_change().dropna().abs().tail(30).mean())
                        else:
                            _eic_hist_move = _eic_imp_move / _eic_min_ivr

                        _eic_iv_ratio = _eic_imp_move / _eic_hist_move if _eic_hist_move > 0 else 0.0

                        _eic_signal = "—"
                        if _eic_imp_move >= _eic_min_imp / 100 and _eic_iv_ratio >= _eic_min_ivr:
                            _eic_signal = "SELL IRON CONDOR"

                        _eic_rows.append({
                            "Ticker":         _eic_tkr,
                            "Price":          round(_eic_S, 2),
                            "IV (ATM) %":     round(_eic_iv * 100, 1),
                            "Implied Move %": round(_eic_imp_move * 100, 2),
                            "Hist Move %":    round(_eic_hist_move * 100, 2),
                            "IV/Hist Ratio":  round(_eic_iv_ratio, 2),
                            "Signal":         _eic_signal,
                        })
                    except Exception as _eic_err:
                        _eic_rows.append({"Ticker": _eic_tkr, "Signal": "—", "Reason": str(_eic_err)[:60]})

                _eic_prog.empty()
                st.session_state["eic_scan_results"] = _eic_rows

        if "eic_scan_results" in st.session_state:
            _eic_df = pd.DataFrame(st.session_state["eic_scan_results"])
            _eic_hits = _eic_df[_eic_df["Signal"] != "—"]
            if not _eic_hits.empty:
                st.success(f"**Iron condor candidates:** {', '.join(_eic_hits['Ticker'].tolist())}")
            else:
                st.info("No tickers met the IV/historical ratio threshold.")
            _eic_display_cols = [c for c in ["Ticker", "Price", "IV (ATM) %", "Implied Move %", "Hist Move %", "IV/Hist Ratio", "Signal"] if c in _eic_df.columns]
            st.dataframe(
                _eic_df[_eic_display_cols].sort_values("IV/Hist Ratio", ascending=False)
                if "IV/Hist Ratio" in _eic_df.columns else _eic_df[_eic_display_cols],
                hide_index=True, width="stretch",
                column_config={
                    "Price":          cc.NumberColumn("Price",       format="$%.2f"),
                    "IV (ATM) %":     cc.NumberColumn("IV ATM",      format="%.1f%%"),
                    "Implied Move %": cc.NumberColumn("Impl. Move",  format="%.2f%%"),
                    "Hist Move %":    cc.NumberColumn("Hist. Move",  format="%.2f%%"),
                    "IV/Hist Ratio":  cc.NumberColumn("IV/Hist",     format="%.2f×"),
                },
            )
            st.caption(
                "**Implied move** = ATM straddle price / spot (1-DTE approximation using BS). "
                "**Historical move** = 30-day avg of absolute daily returns. "
                "IV/Hist Ratio ≥ 1.2 suggests options are overpricing the earnings uncertainty — sell iron condor."
            )

    # ══════════════════════════════════════════════════════════════════════════
    # EARNINGS POST-DRIFT SCREENER — recent large EPS beats
    # ══════════════════════════════════════════════════════════════════════════
    if t_postdrift is not None:
      with t_postdrift:
        st.caption(
            "Scans for recent **large EPS beats** where the stock has not yet fully reflected the surprise. "
            "Enter a bull call spread the morning after announcement to capture the post-earnings drift (PEAD)."
        )

        _pd_col1, _pd_col2, _pd_col3 = st.columns(3)
        _pd_min_beat  = _pd_col1.slider("Min EPS beat (%)", 5, 30, 10, 5, key=kp("pd_mbeat"),
                                         help="EPS surprise must exceed this threshold (actual vs estimate)")
        _pd_max_gap   = _pd_col2.slider("Max gap-up to chase (%)", 5, 30, 15, 5, key=kp("pd_mgap"),
                                         help="Skip if stock has already gapped up more than this (chasing)")
        _pd_tickers   = _pd_col3.multiselect(
            "Tickers to scan",
            options=sorted({t for lst in UNIVERSES.values() for t in lst}),
            default=["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "NFLX"],
            key=kp("pd_tickers"),
        )

        if st.button("📡 Scan Post-Earnings Drift", key=kp("pd_btn")):
            if not api_key:
                st.warning("Enter a Polygon API key in the sidebar.")
            elif not _pd_tickers:
                st.warning("Select at least one ticker.")
            else:
                from alan_trader.data.polygon_client import PolygonClient as _PCD
                _pd_client = _PCD(api_key=api_key)
                _pd_rows = []
                _pd_prog = st.progress(0, text="Scanning earnings beats…")

                for _pdi, _pd_tkr in enumerate(_pd_tickers):
                    _pd_prog.progress((_pdi + 1) / len(_pd_tickers), text=f"PEAD: {_pd_tkr}")
                    try:
                        import datetime as _dt_pd
                        _pd_to   = _dt_pd.date.today()
                        _pd_from = _pd_to - _dt_pd.timedelta(days=30)   # look for recent beats

                        # Current price + recent price history for gap calculation
                        _pd_snap = _pd_client.get_snapshot(_pd_tkr)
                        if _pd_snap is None:
                            _pd_rows.append({"Ticker": _pd_tkr, "Signal": "—", "Reason": "No snapshot"})
                            continue
                        _pd_S = float(_pd_snap.get("day", {}).get("c") or _pd_snap.get("lastTrade", {}).get("p") or 0)
                        _pd_prev = float(_pd_snap.get("prevDay", {}).get("c") or _pd_S)
                        _pd_gap  = (_pd_S / _pd_prev - 1) if _pd_prev > 0 else 0.0

                        _pd_rows.append({
                            "Ticker":       _pd_tkr,
                            "Price":        round(_pd_S, 2),
                            "Gap %":        round(_pd_gap * 100, 2),
                            "EPS Beat %":   "—",
                            "EPS Actual":   "—",
                            "EPS Est":      "—",
                            "Signal":       "WATCH — no DB earnings" if _pd_gap >= _pd_min_beat / 100 else "—",
                            "Note":         "Connect DB earnings for full signal",
                        })
                    except Exception as _pd_err:
                        _pd_rows.append({"Ticker": _pd_tkr, "Signal": "—", "Reason": str(_pd_err)[:60]})

                _pd_prog.empty()
                st.session_state["pd_scan_results"] = _pd_rows

        if "pd_scan_results" in st.session_state:
            _pd_df = pd.DataFrame(st.session_state["pd_scan_results"])
            _pd_hits = _pd_df[_pd_df["Signal"] != "—"]
            if not _pd_hits.empty:
                st.success(f"**Watch list:** {', '.join(_pd_hits['Ticker'].tolist())}")
            else:
                st.info("No recent large gap-ups detected.")
            _pd_display_cols = [c for c in ["Ticker", "Price", "Gap %", "EPS Beat %", "EPS Actual", "EPS Est", "Signal"] if c in _pd_df.columns]
            st.dataframe(
                _pd_df[_pd_display_cols].sort_values("Gap %", ascending=False)
                if "Gap %" in _pd_df.columns else _pd_df[_pd_display_cols],
                hide_index=True, width="stretch",
                column_config={
                    "Price":      cc.NumberColumn("Price",    format="$%.2f"),
                    "Gap %":      cc.NumberColumn("Gap %",    format="%.2f%%"),
                    "EPS Beat %": cc.NumberColumn("EPS Beat", format="%.1f%%"),
                },
            )
            st.caption(
                "**EPS Beat %** = (actual − estimate) / |estimate|. "
                "Full signal requires earnings data synced to the database (Data Manager → Sync Earnings). "
                "Gap-up alone is a rough proxy — sync DB for precise EPS surprise filtering."
            )
