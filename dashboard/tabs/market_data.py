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


def render(ticker: str = "SPY", api_key: str = ""):
    st.header(f"Market Data — {ticker}")

    from alan_trader.data.simulator import (
        TICKER_PROFILES, DEFAULT_PROFILE,
        simulate_price,
        simulate_vol_surface,
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

        candle_days = st.slider("Candle history (trading days)", 20, 504, 120, 10,
                                key="md_candle_days")

        bars_df = None
        if api_key:
            with st.spinner(f"Fetching {ticker} bars from Polygon.io…"):
                bars_df = _fetch_live_bars(ticker, api_key, n_days=candle_days)
            if bars_df is not None and not bars_df.empty:
                bars_df = bars_df.tail(candle_days)
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
            bars_df = simulate_price(ticker=ticker, n_days=candle_days).tail(candle_days)
            if api_key:
                st.caption("⚠️ Showing simulated data — live bars unavailable.")
            else:
                st.caption("Simulated data — enter API key in sidebar for real bars.")

        st.plotly_chart(C.candlestick_chart(bars_df, ticker=ticker),
                        width="stretch", key="md_candle")

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
            if surf_err:
                st.error(f"Vol surface error: {surf_err}")

        if live_surf is not None and not live_surf.empty:
            strikes_z = np.array(sorted(live_surf["strike"].unique()))
            dtes_z    = np.array(sorted(live_surf["dte"].unique()))
            iv_z  = np.full((len(dtes_z), len(strikes_z)), np.nan)
            s_idx = {s: i for i, s in enumerate(strikes_z)}
            d_idx = {d: i for i, d in enumerate(dtes_z)}
            for _, row in live_surf.iterrows():
                iv = row["iv"]
                if iv and float(iv) > 0:
                    iv_z[d_idx[row["dte"]], s_idx[row["strike"]]] = float(iv)

            # 2-D interpolation: linear for interior, nearest for edges
            from scipy.interpolate import griddata
            di, si = np.meshgrid(np.arange(len(dtes_z)), np.arange(len(strikes_z)), indexing="ij")
            valid  = ~np.isnan(iv_z)
            if valid.sum() >= 4:
                pts = np.column_stack([di[valid], si[valid]])
                all_pts = np.column_stack([di.ravel(), si.ravel()])
                iv_linear  = griddata(pts, iv_z[valid], all_pts, method="linear").reshape(iv_z.shape)
                iv_nearest = griddata(pts, iv_z[valid], all_pts, method="nearest").reshape(iv_z.shape)
                iv_z = np.where(np.isnan(iv_linear), iv_nearest, iv_linear)
            n_strikes = len(strikes_z)
            n_exp     = len(dtes_z)
            st.caption(f"📡 Live IV surface — {n_strikes} strikes × {n_exp} expirations (Polygon calls, 5 % steps, cached 2 h)")
        else:
            # Simulated fallback — apply DTE filter
            strikes_all, dtes_all, iv_all = simulate_vol_surface(S=spot_price, iv_base=iv_base)
            mask_s = (strikes_all >= spot_price * 0.80) & (strikes_all <= spot_price * 1.20)
            mask_d = (dtes_all >= dte_lo) & (dtes_all <= dte_hi)
            strikes_z = strikes_all[mask_s]
            dtes_z    = dtes_all[mask_d]
            iv_z      = iv_all[np.ix_(mask_d, mask_s)]
            if api_key:
                st.caption("⚠️ Showing simulated surface — live options unavailable.")
            else:
                st.caption("Simulated surface — enter API key in sidebar for real IV data.")

        if strikes_z.size >= 2 and dtes_z.size >= 2:
            st.plotly_chart(C.vol_surface_3d(strikes_z, dtes_z, iv_z),
                            width="stretch", key="md_vol_surface")
        else:
            st.warning("Not enough data — broaden the DTE range.")

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
