"""
Market Data tab — Price Chart, Vol Surface, IV Smile, Top Movers,
Dealer Gamma Exposure, and Momentum Indicators.
Works for any optionable ticker.
"""

import streamlit as st
import pandas as pd


def _fetch_live_bars(ticker: str, api_key: str, n_days: int = 252) -> "pd.DataFrame":
    """Return OHLCV bars from Polygon.io, or empty DataFrame on failure."""
    import pandas as pd
    from datetime import datetime, timedelta
    try:
        from alan_trader.data.polygon_client import PolygonClient
        from alan_trader.data.loader import _fetch_polygon_aggs
        client    = PolygonClient(api_key=api_key)
        to_date   = datetime.now().date()
        from_date = to_date - timedelta(days=int(n_days * 1.5))
        return _fetch_polygon_aggs(client, ticker,
                                   from_date.strftime("%Y-%m-%d"),
                                   to_date.strftime("%Y-%m-%d"))
    except Exception:
        return pd.DataFrame()


def _fetch_live_vol_surface(ticker: str, api_key: str, spot_price: float,
                            min_dte: int = 7, max_dte: int = 180) -> "tuple[pd.DataFrame | None, str]":
    """Returns (df_or_None, error_message)."""
    try:
        from alan_trader.data.polygon_client import PolygonClient
        from alan_trader.data.loader import fetch_live_vol_surface
        client = PolygonClient(api_key=api_key)
        df = fetch_live_vol_surface(client, ticker, spot_price,
                                    min_dte=min_dte, max_dte=max_dte, step_pct=0.05)
        return df, ""
    except Exception as e:
        return None, str(e)


def _fetch_live_movers(api_key: str) -> "pd.DataFrame":
    """Fetch real top gainers + losers from Polygon. Returns movers_df or empty DataFrame."""
    try:
        from alan_trader.data.polygon_client import PolygonClient
        c = PolygonClient(api_key=api_key)
        gainers = c._get("/v2/snapshot/locale/us/markets/stocks/gainers").get("tickers", [])
        losers  = c._get("/v2/snapshot/locale/us/markets/stocks/losers").get("tickers", [])
        rows = []
        for snap in gainers + losers:
            rows.append({
                "ticker":     snap.get("ticker", ""),
                "price":      snap.get("day", {}).get("c") or snap.get("lastTrade", {}).get("p") or 0,
                "change_pct": snap.get("todaysChangePerc", 0),
                "volume":     snap.get("day", {}).get("v") or 0,
            })
        return pd.DataFrame(rows) if rows else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


def _fetch_live_gex(ticker: str, api_key: str, spot: float,
                    max_dte: int = 60) -> "pd.DataFrame":
    """
    Compute real Dealer GEX from Polygon options chain.
    GEX per strike = gamma × OI × 100 × spot²
    Calls add positive GEX, puts subtract.
    """
    from datetime import date, timedelta
    try:
        from alan_trader.data.polygon_client import PolygonClient
        c = PolygonClient(api_key=api_key)
        exp_to = (date.today() + timedelta(days=max_dte)).strftime("%Y-%m-%d")
        results, url = [], f"/v3/snapshot/options/{ticker}"
        params = {
            "expiration_date.gte": date.today().strftime("%Y-%m-%d"),
            "expiration_date.lte": exp_to,
            "strike_price.gte":    round(spot * 0.80, 2),
            "strike_price.lte":    round(spot * 1.20, 2),
            "limit": 250,
        }
        while url:
            data = c._get(url, params)
            results.extend(data.get("results", []))
            next_url = (data.get("next_url") or "").replace(c.BASE, "")
            url = next_url or None
            params = {}

        if not results:
            return pd.DataFrame()

        from collections import defaultdict
        gex_by_strike: dict = defaultdict(lambda: {"call_gex": 0.0, "put_gex": 0.0})
        for r in results:
            d = r.get("details", {})
            g = r.get("greeks", {})
            gamma = g.get("gamma")
            oi    = r.get("open_interest")
            if not gamma or not oi:
                continue
            strike = d.get("strike_price")
            ctype  = d.get("contract_type", "").lower()
            gex_val = float(gamma) * float(oi) * 100 * (spot ** 2) / 1e9  # scale to $B
            if ctype == "call":
                gex_by_strike[strike]["call_gex"] += gex_val
            elif ctype == "put":
                gex_by_strike[strike]["put_gex"] -= gex_val  # put dealers are short gamma

        rows = [
            {"strike": k, "call_gex": v["call_gex"], "put_gex": v["put_gex"],
             "net_gex": v["call_gex"] + v["put_gex"]}
            for k, v in sorted(gex_by_strike.items())
        ]
        return pd.DataFrame(rows) if rows else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


def _fetch_live_quote(ticker: str, api_key: str) -> dict:
    """Return live price snapshot or empty dict on failure."""
    try:
        from alan_trader.data.loader import get_live_quote
        from alan_trader.data.polygon_client import PolygonClient
        client = PolygonClient(api_key=api_key)
        return get_live_quote(client, ticker)
    except Exception:
        return {}


_MATURITIES = [
    ("3M",  "rate_3m"),
    ("6M",  "rate_6m"),
    ("1Y",  "rate_1y"),
    ("2Y",  "rate_2y"),
    ("5Y",  "rate_5y"),
    ("10Y", "rate_10y"),
    ("30Y", "rate_30y"),
]


# yfinance tickers for intraday snapshot (15-min delayed, free)
_TREASURY_YF = {
    "rate_3m":  "^IRX",
    "rate_5y":  "^FVX",
    "rate_10y": "^TNX",
    "rate_30y": "^TYX",
}

_TREASURY_FRED_SERIES = {
    "rate_3m":  "DGS3MO",
    "rate_6m":  "DGS6MO",
    "rate_1y":  "DGS1",
    "rate_2y":  "DGS2",
    "rate_5y":  "DGS5",
    "rate_10y": "DGS10",
    "rate_30y": "DGS30",
    "sofr":     "SOFR",
}


@st.cache_data(ttl=300)
def _fetch_yield_snapshot() -> "dict":
    """Fetch intraday Treasury yields via yfinance (15-min delayed, cached 5 min)."""
    try:
        import yfinance as yf
        tickers = list(_TREASURY_YF.values())
        data = yf.download(tickers, period="1d", interval="1m", progress=False, auto_adjust=True)
        snapshot = {}
        for col, ticker in _TREASURY_YF.items():
            try:
                series = data["Close"][ticker].dropna()
                if not series.empty:
                    snapshot[col] = round(float(series.iloc[-1]), 3)
            except Exception:
                pass
        return snapshot
    except Exception:
        return {}


@st.cache_data(ttl=3600)
def _load_yield_curve_live() -> "pd.DataFrame | None":
    """Fetch Treasury yield curve directly from FRED free CSVs (no API key, cached 1h)."""
    import requests
    from io import StringIO
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _fetch_one(col_series):
        col, series_id = col_series
        try:
            resp = requests.get(
                f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}",
                timeout=15,
            )
            resp.raise_for_status()
            df = pd.read_csv(StringIO(resp.text))
            df.columns = ["date", col]
            df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
            df[col]    = pd.to_numeric(df[col], errors="coerce")
            return col, df.dropna(subset=["date"]).set_index("date")
        except Exception:
            return col, None

    series_dfs = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_fetch_one, item): item for item in _TREASURY_FRED_SERIES.items()}
        for fut in as_completed(futures):
            col, df = fut.result()
            if df is not None:
                series_dfs[col] = df

    if not series_dfs:
        return None

    merged = None
    for col, df in series_dfs.items():
        merged = df if merged is None else merged.join(df, how="outer")

    merged = merged.reset_index().sort_values("date")
    merged["spread_2s10s"] = pd.to_numeric(merged.get("rate_10y"), errors="coerce") - \
                             pd.to_numeric(merged.get("rate_2y"),  errors="coerce")
    merged["spread_3m10y"] = pd.to_numeric(merged.get("rate_10y"), errors="coerce") - \
                             pd.to_numeric(merged.get("rate_3m"),  errors="coerce")
    return merged.reset_index(drop=True)


def _render_term_structure():
    import plotly.graph_objects as go
    import numpy as np

    with st.spinner("Loading yield curve from FRED…"):
        df = _load_yield_curve_live()

    if df is None or df.empty:
        st.warning("Could not load yield curve data from FRED.")
        return

    latest_date = df["date"].iloc[-1]
    cols_avail   = [col for _, col in _MATURITIES if col in df.columns]
    labels_avail = [lbl for lbl, col in _MATURITIES if col in df.columns]

    # ── Live snapshot from yfinance (overrides FRED for available tenors) ─────
    live = _fetch_yield_snapshot()
    eod  = df.iloc[-1]

    def _y(col):
        """Live value if available, else latest FRED end-of-day."""
        v = live.get(col) or eod.get(col)
        return float(v) if v and str(v) != "nan" else None

    y2  = _y("rate_2y")
    y10 = _y("rate_10y")
    y30 = _y("rate_30y")
    y3m = _y("rate_3m")
    spread_2s10s = (y10 - y2)  if y10 and y2  else None
    spread_3m10y = (y10 - y3m) if y10 and y3m else None

    live_label = "📡 live (15-min delayed)" if live else f"end-of-day {latest_date}"

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("2Y Yield",     f"{y2:.2f}%"  if y2  else "—")
    m2.metric("10Y Yield",    f"{y10:.2f}%" if y10 else "—")
    m3.metric("30Y Yield",    f"{y30:.2f}%" if y30 else "—")
    if spread_2s10s is not None:
        m4.metric("2s10s Spread", f"{spread_2s10s:+.2f}%",
                  delta="Inverted" if spread_2s10s < 0 else "Normal",
                  delta_color="inverse" if spread_2s10s < 0 else "normal")
    else:
        m4.metric("2s10s Spread", "—")
    if spread_3m10y is not None:
        m5.metric("3m10y Spread", f"{spread_3m10y:+.2f}%",
                  delta="Inverted" if spread_3m10y < 0 else "Normal",
                  delta_color="inverse" if spread_3m10y < 0 else "normal")
    else:
        m5.metric("3m10y Spread", "—")
    st.caption(f"Yields: {live_label}  •  History: FRED (end-of-day, cached 1h)")

    # ── Controls ─────────────────────────────────────────────────────────────
    tc1, tc2 = st.columns([3, 1])
    compare_dates_labels = ["Today only", "vs 1M ago", "vs 3M ago", "vs 1Y ago", "All 4"]
    compare_mode = tc1.selectbox("Compare", compare_dates_labels, index=4, key="ts_compare")
    chart_type   = tc2.radio("View", ["Curve", "History"], key="ts_chart_type", horizontal=True)

    # ── Term Structure Snapshot Chart ─────────────────────────────────────────
    if chart_type == "Curve":
        offsets = {"Today only": [0], "vs 1M ago": [0, 21], "vs 3M ago": [0, 63],
                   "vs 1Y ago": [0, 252], "All 4": [0, 21, 63, 252]}
        target_offsets = offsets.get(compare_mode, [0])
        fig = go.Figure()
        colors = ["#00d4ff", "#ff9933", "#66ff66", "#ff4488"]
        for idx, offset in enumerate(target_offsets):
            row_idx = max(0, len(df) - 1 - offset)
            row = df.iloc[row_idx]
            yields = [float(row[col]) if row[col] is not None and not np.isnan(float(row[col])) else None
                      for col in cols_avail]
            label = str(row["date"])
            if offset == 0:
                label = f"Today ({row['date']})"
            elif offset == 21:
                label = f"~1M ago ({row['date']})"
            elif offset == 63:
                label = f"~3M ago ({row['date']})"
            elif offset == 252:
                label = f"~1Y ago ({row['date']})"
            fig.add_trace(go.Scatter(
                x=labels_avail, y=yields, mode="lines+markers",
                name=label, line=dict(color=colors[idx % len(colors)], width=2),
                marker=dict(size=7),
            ))
        fig.update_layout(
            title="Treasury Yield Curve",
            xaxis_title="Maturity", yaxis_title="Yield (%)",
            yaxis_tickformat=".2f",
            template="plotly_dark",
            height=350,
            legend=dict(orientation="h", y=-0.2),
            margin=dict(t=40, b=80, l=50, r=20),
        )
        # Overlay live yfinance dots where available
        if live:
            live_x = [lbl for lbl, col in _MATURITIES if live.get(col) is not None]
            live_y = [live[col] for _, col in _MATURITIES if live.get(col) is not None]
            if live_x:
                fig.add_trace(go.Scatter(
                    x=live_x, y=live_y, mode="markers",
                    name="Live (yfinance)",
                    marker=dict(color="#ffffff", size=10, symbol="circle",
                                line=dict(color="#00d4ff", width=2)),
                ))

        # Zero line to highlight inversion
        fig.add_hline(y=0, line_dash="dot", line_color="gray", opacity=0.5)
        st.plotly_chart(fig, width="stretch", key="ts_curve_chart")

    # ── Historical Yield Chart ────────────────────────────────────────────────
    else:
        plot_tenors = st.multiselect(
            "Tenors to plot", labels_avail,
            default=["2Y", "10Y", "30Y"],
            key="ts_hist_tenors",
        )
        fig = go.Figure()
        colors = ["#00d4ff", "#ff9933", "#66ff66", "#ff4488", "#cc88ff", "#ffff44", "#ff6666"]
        for i, lbl in enumerate(plot_tenors):
            col = dict(_MATURITIES)[lbl]
            if col in df.columns:
                fig.add_trace(go.Scatter(
                    x=df["date"], y=df[col], mode="lines",
                    name=f"{lbl} Yield",
                    line=dict(color=colors[i % len(colors)], width=1.5),
                ))

        # 2s10s spread as secondary
        if "rate_2y" in df.columns and "rate_10y" in df.columns:
            spread = df["rate_10y"] - df["rate_2y"]
            fig.add_trace(go.Scatter(
                x=df["date"], y=spread, mode="lines",
                name="2s10s Spread",
                line=dict(color="#888888", width=1, dash="dot"),
                yaxis="y2",
            ))

        fig.update_layout(
            title="Treasury Yields — History",
            xaxis_title="Date", yaxis_title="Yield (%)",
            yaxis2=dict(title="Spread (%)", overlaying="y", side="right",
                        showgrid=False, zeroline=True, zerolinecolor="#555"),
            template="plotly_dark",
            height=380,
            legend=dict(orientation="h", y=-0.2),
            margin=dict(t=40, b=80, l=50, r=60),
        )
        fig.add_hline(y=0, line_dash="dot", line_color="gray", opacity=0.4)
        st.plotly_chart(fig, width="stretch", key="ts_hist_chart")


def render(ticker: str = "SPY", api_key: str = ""):
    st.header(f"Market Data — {ticker}")

    from alan_trader.data.simulator import (
        TICKER_PROFILES, DEFAULT_PROFILE,
        simulate_price,
        simulate_iv_smile,
        simulate_top_movers,
        simulate_gex,
        simulate_momentum_indicators,
    )
    from alan_trader.visualization import charts as C

    profile   = TICKER_PROFILES.get(ticker.upper(), DEFAULT_PROFILE)
    default_S = profile["start_price"]

    import numpy as np

    # ── Price Chart (FIRST, default open) ────────────────────────────────────
    with st.expander(f"Price Chart — {ticker}", expanded=True):

        # Live quote strip at the top of the chart section
        if api_key:
            with st.spinner(f"Fetching live quote for {ticker}…"):
                q = _fetch_live_quote(ticker, api_key)
            if q.get("price"):
                default_S = q["price"]
                lq1, lq2, lq3, lq4, lq5 = st.columns(5)
                lq1.metric("Price",  f"${q['price']:,.2f}")
                lq2.metric("Change", f"${q.get('change', 0):+.2f}",
                           delta=f"{q.get('change_pct', 0):+.2f}%")
                lq3.metric("Volume", f"{int(q.get('volume') or 0):,}")
                lq4.metric("High",   f"${q.get('high', 0):,.2f}")
                lq5.metric("Low",    f"${q.get('low', 0):,.2f}")
                st.markdown("---")

        bars_df = None
        if api_key:
            with st.spinner(f"Fetching {ticker} bars from Polygon.io…"):
                bars_df = _fetch_live_bars(ticker, api_key, n_days=504)
            if bars_df is not None and not bars_df.empty:
                # Append today's partial bar from snapshot if missing
                import datetime as _dt
                today = _dt.date.today()
                last_date = pd.to_datetime(bars_df.index[-1]).date() if hasattr(bars_df.index[-1], 'year') \
                            else pd.to_datetime(bars_df["date"].iloc[-1]).date() \
                            if "date" in bars_df.columns else None
                if last_date and last_date < today and q.get("price"):
                    today_bar = pd.DataFrame([{
                        "date":   today,
                        "open":   q.get("open") or q["price"],
                        "high":   q.get("high") or q["price"],
                        "low":    q.get("low")  or q["price"],
                        "close":  q["price"],
                        "volume": q.get("volume") or 0,
                        "vwap":   q.get("vwap")   or q["price"],
                    }]).set_index("date")
                    bars_df = pd.concat([bars_df, today_bar])
                st.caption(f"📡 Live data from Polygon.io — {len(bars_df)} bars (incl. today)")
            else:
                bars_df = None

        if bars_df is None or bars_df.empty:
            bars_df = simulate_price(ticker=ticker, n_days=504)
            if api_key:
                st.caption("⚠️ Showing simulated data — live bars unavailable.")
            else:
                st.caption("Simulated data — enter API key in sidebar for real bars.")

        # ── Date range slice ─────────────────────────────────────────────────
        import datetime as _dt
        bar_dates = pd.to_datetime(bars_df.index).date
        d_min, d_max = bar_dates.min(), bar_dates.max()
        rng = st.slider(
            "View range",
            min_value=d_min, max_value=d_max,
            value=(d_min, d_max),
            format="YYYY-MM-DD",
            key="md_candle_range",
        )
        slice_df = bars_df.loc[
            (pd.to_datetime(bars_df.index).date >= rng[0]) &
            (pd.to_datetime(bars_df.index).date <= rng[1])
        ]

        st.plotly_chart(C.candlestick_chart(slice_df, ticker=ticker),
                        width="stretch", key="md_candle")

    # ── Treasury Term Structure ───────────────────────────────────────────────
    with st.expander("Treasury Term Structure", expanded=False):
        _render_term_structure()

    # ── Shared controls (used by Vol Surface + GEX below) ────────────────────
    st.markdown("---")
    ctrl1, ctrl2, ctrl3 = st.columns(3)
    spot_price = ctrl1.number_input(
        f"{ticker} Price ($)", value=float(default_S),
        min_value=1.0, max_value=10_000.0, step=max(1.0, default_S * 0.01),
        key="md_spot_price",
    )
    iv_base = ctrl2.slider(
        "Base IV (%)", min_value=5, max_value=120, value=int(profile["annual_vol"] * 100),
        key="md_iv_base",
    ) / 100.0
    gex_n_strikes = ctrl3.slider(
        "GEX strikes shown", min_value=10, max_value=30, value=20,
        key="md_gex_n_strikes",
    )
    st.markdown("---")

    # ── Volatility Surface ───────────────────────────────────────────────────
    with st.expander("Volatility Surface", expanded=False):
        zc1, zc2 = st.columns(2)
        dte_lo = zc1.slider("Min DTE",  1,  60,   7, 1,  key="vs_dte_lo")
        dte_hi = zc2.slider("Max DTE", 30, 365, 180, 10, key="vs_dte_hi")

        live_surf = None
        if api_key:
            with st.spinner("Fetching live options chain (calls, 5 % strike steps)…"):
                live_surf, surf_err = _fetch_live_vol_surface(
                    ticker, api_key, spot_price, min_dte=dte_lo, max_dte=dte_hi
                )
        if not api_key:
            st.info("Enter your Polygon API key in the sidebar to load the real volatility surface.")
        elif live_surf is None or live_surf.empty:
            msg = surf_err or (
                f"Live IV surface unavailable for {ticker}. "
                "The `implied_volatility` field requires a Polygon Options add-on plan. "
                "The IV smile below uses simulated data."
            )
            st.warning(msg)
        else:
            strikes_z = np.array(sorted(live_surf["strike"].unique()))
            dtes_z    = np.array(sorted(live_surf["dte"].unique()))
            iv_z  = np.full((len(dtes_z), len(strikes_z)), np.nan)
            s_idx = {s: i for i, s in enumerate(strikes_z)}
            d_idx = {d: i for i, d in enumerate(dtes_z)}
            for _, row in live_surf.iterrows():
                iv = row["iv"]
                if iv and float(iv) > 0:
                    iv_z[d_idx[row["dte"]], s_idx[row["strike"]]] = float(iv)

            from scipy.interpolate import griddata
            di, si = np.meshgrid(np.arange(len(dtes_z)), np.arange(len(strikes_z)), indexing="ij")
            valid  = ~np.isnan(iv_z)
            if valid.sum() >= 4:
                pts     = np.column_stack([di[valid], si[valid]])
                all_pts = np.column_stack([di.ravel(), si.ravel()])
                iv_nearest = griddata(pts, iv_z[valid], all_pts, method="nearest").reshape(iv_z.shape)
                try:
                    iv_linear = griddata(pts, iv_z[valid], all_pts, method="linear").reshape(iv_z.shape)
                    iv_z = np.where(np.isnan(iv_linear), iv_nearest, iv_linear)
                except Exception:
                    # Degenerate geometry (e.g. all points share one DTE) — nearest is fine
                    iv_z = iv_nearest

            n_strikes = strikes_z.size
            n_dtes    = dtes_z.size
            if n_strikes >= 2 and n_dtes >= 2:
                st.caption(f"📡 Live IV surface — {n_strikes} strikes × {n_dtes} expirations")
                st.plotly_chart(C.vol_surface_3d(strikes_z, dtes_z, iv_z, spot_price=spot_price),
                                width="stretch", key="md_vol_surface")
            elif n_strikes >= 2 and n_dtes == 1:
                import plotly.graph_objects as _go
                dte_val   = int(dtes_z[0])
                fig_smile = _go.Figure(_go.Scatter(
                    x=strikes_z, y=iv_z[0], mode="lines+markers",
                    line=dict(color="#00d4ff", width=2), marker=dict(size=6),
                ))
                fig_smile.update_layout(
                    title=f"📡 IV Smile — {ticker} ({dte_val} DTE)",
                    xaxis_title="Strike", yaxis_title="IV",
                    template="plotly_dark", height=320,
                    margin=dict(t=40, b=40, l=50, r=20),
                )
                st.caption("Single expiry with live IV — showing IV smile. Outside market hours Polygon only populates IV for the nearest active expiry. Try again during trading hours for 3D view.")
                st.plotly_chart(fig_smile, width="stretch", key="md_vol_surface")
            else:
                st.warning(
                    f"Not enough data for {ticker}: {n_strikes} strike(s) × {n_dtes} expiry(s). "
                    "Try widening the DTE range or strike range."
                )

        sm1, sm2 = st.columns([3, 1])
        with sm1:
            smile_df = simulate_iv_smile(S=spot_price, iv_base=iv_base)
            st.plotly_chart(C.iv_smile(smile_df), width="stretch", key="md_iv_smile")
        with sm2:
            st.markdown("**ATM Implied Vol**")
            for dte_val in [7, 21, 45, 90]:
                grp = smile_df[smile_df["dte"] == dte_val]
                if not grp.empty:
                    atm_row = grp.iloc[(grp["moneyness"] - 1).abs().argsort()[:1]]
                    st.metric(f"{dte_val} DTE", f"{float(atm_row['iv'].iloc[0]) * 100:.1f}%")

    # ── Top Movers + Dealer GEX ──────────────────────────────────────────────
    with st.expander("Market Activity", expanded=False):
        ma1, ma2 = st.columns(2)

        # ── Top Movers ────────────────────────────────────────────────────────
        with ma1:
            movers_df = pd.DataFrame()
            if api_key:
                with st.spinner("Fetching market movers from Polygon…"):
                    movers_df = _fetch_live_movers(api_key)
                if not movers_df.empty:
                    st.caption("📡 Live gainers/losers — Polygon.io")
                else:
                    st.caption("⚠️ Live movers unavailable — showing simulated data.")
            if movers_df.empty:
                movers_df = simulate_top_movers(ticker=ticker, n=30)
                if not api_key:
                    st.caption("Simulated movers — enter API key in sidebar for real data.")

            st.plotly_chart(C.top_movers_bar(movers_df, ticker=ticker),
                            width="stretch", key="md_movers")
            gainers = (movers_df["change_pct"] > 0).sum()
            losers  = (movers_df["change_pct"] < 0).sum()
            m1, m2  = st.columns(2)
            m1.metric("Advancers", int(gainers))
            m2.metric("Decliners", int(losers))

        # ── Dealer GEX ────────────────────────────────────────────────────────
        with ma2:
            gex_df = pd.DataFrame()

            if api_key:
                gex_dte = st.slider("GEX max DTE", 7, 90, 45, 7, key="md_gex_dte")
                if st.button("📡 Fetch Live GEX", width="stretch", key="md_gex_btn"):
                    with st.spinner(f"Fetching {ticker} options chain (±20% strikes, {gex_dte}d DTE)…"):
                        gex_df = _fetch_live_gex(ticker, api_key, spot_price, max_dte=gex_dte)
                    st.session_state["md_live_gex"] = gex_df
                else:
                    gex_df = st.session_state.get("md_live_gex", pd.DataFrame())

                if not gex_df.empty:
                    st.caption(f"📡 Live GEX — {len(gex_df)} strikes from Polygon options chain")
                elif "md_live_gex" in st.session_state:
                    st.caption("⚠️ Live GEX unavailable — showing simulated data.")

            if gex_df.empty:
                gex_df = simulate_gex(S=spot_price, n_strikes=gex_n_strikes)
                if not api_key:
                    st.caption("Simulated GEX — click 'Fetch Live GEX' in live mode for real data.")

            st.plotly_chart(C.dealer_gex_bar(gex_df, S=spot_price, ticker=ticker),
                            width="stretch", key="md_gex")
            net_total = float(gex_df["net_gex"].sum())

        # Gamma flip
        sorted_gex = gex_df.sort_values("strike")
        flip_level = spot_price
        for i in range(len(sorted_gex) - 1):
            a = sorted_gex.iloc[i]["net_gex"]
            b = sorted_gex.iloc[i + 1]["net_gex"]
            if a * b < 0:
                flip_level = float(sorted_gex.iloc[i]["strike"])
                break

        g1, g2, g3 = st.columns(3)
        g1.metric("Net GEX ($B)", f"{net_total:+.3f}",
                  help="Positive = price-stabilising regime.")
        g2.metric("Gamma Flip", f"${flip_level:.0f}",
                  help="Strike where dealer hedging flips character.")
        g3.metric("Spot vs Flip", f"{spot_price - flip_level:+.0f} pts",
                  help="Distance of spot above/below the gamma flip.")

    # ── Momentum Indicators ──────────────────────────────────────────────────
    with st.expander(f"Momentum Indicators — {ticker}", expanded=False):
        mom_days = st.slider(
            "History (trading days)", min_value=60, max_value=504, value=252, step=20,
            key="md_mom_days",
        )

        momentum_df = None
        if api_key:
            with st.spinner(f"Fetching {ticker} bars…"):
                bars = _fetch_live_bars(ticker, api_key, n_days=mom_days)
            if not bars.empty:
                from alan_trader.data.features import add_price_features
                feat = add_price_features(bars.reset_index())
                feat["macd_line"]      = feat["macd"]
                feat["signal_line"]    = feat["macd_signal"]
                feat["macd_histogram"] = feat["macd_hist"]
                momentum_df = feat[["date", "close", "rsi_14", "macd_line", "signal_line", "macd_histogram"]].rename(
                    columns={"rsi_14": "rsi"}
                ).dropna()
                st.caption(f"📡 Live data — {len(momentum_df)} trading days from Polygon.io")
        if momentum_df is None or momentum_df.empty:
            momentum_df = simulate_momentum_indicators(ticker=ticker, n_days=mom_days)

        st.plotly_chart(
            C.rsi_macd_chart(momentum_df, ticker=ticker),
            width="stretch", key="md_momentum",
        )

        latest = momentum_df.dropna().iloc[-1]
        ri1, ri2, ri3, ri4 = st.columns(4)
        rsi_val = float(latest["rsi"])
        ri1.metric("RSI (14)", f"{rsi_val:.1f}",
                   delta="Overbought" if rsi_val > 70 else ("Oversold" if rsi_val < 30 else "Neutral"))
        ri2.metric("MACD Line",   f"{float(latest['macd_line']):.3f}")
        ri3.metric("Signal Line", f"{float(latest['signal_line']):.3f}")
        ri4.metric(
            "MACD Cross",
            "Bullish" if float(latest["macd_line"]) > float(latest["signal_line"]) else "Bearish",
        )
