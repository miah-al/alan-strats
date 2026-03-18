"""
Market Data tab — Vol Surface, IV Smile, Top Movers,
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


def _fetch_live_quote(ticker: str, api_key: str) -> dict:
    """Return live price snapshot or empty dict on failure."""
    try:
        from alan_trader.data.loader import get_live_quote
        from alan_trader.data.polygon_client import PolygonClient
        client = PolygonClient(api_key=api_key)
        return get_live_quote(client, ticker)
    except Exception:
        return {}


def render(ticker: str = "SPY", use_sim: bool = True, api_key: str = ""):
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

    # ── Live spot price ──────────────────────────────────────────────────────
    if not use_sim and api_key:
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

    # ── Controls ────────────────────────────────────────────────────────────
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

    import numpy as np
    st.markdown("---")

    # ── Candlestick price chart ───────────────────────────────────────────────
    with st.expander(f"Price Chart — {ticker}", expanded=True):
        candle_days = st.slider("Candle history (trading days)", 20, 504, 120, 10,
                                key="md_candle_days")
        bars_df = None
        if not use_sim and api_key:
            with st.spinner(f"Fetching {ticker} bars…"):
                bars_df = _fetch_live_bars(ticker, api_key, n_days=candle_days)
            if not bars_df.empty:
                bars_df = bars_df.tail(candle_days)
                st.caption(f"📡 Live data from Polygon.io — {len(bars_df)} bars")
        if bars_df is None or bars_df.empty:
            bars_df = simulate_price(ticker=ticker, n_days=candle_days)
            bars_df = bars_df.tail(candle_days)
            if not use_sim and api_key:
                st.caption("⚠️ Showing simulated data — live bars unavailable.")
        st.plotly_chart(C.candlestick_chart(bars_df, ticker=ticker),
                        use_container_width=True, key="md_candle")

    # ── Volatility Surface ───────────────────────────────────────────────────
    with st.expander("Volatility Surface", expanded=False):
        strikes_all, dtes_all, iv_all = simulate_vol_surface(S=spot_price, iv_base=iv_base)

        zc1, zc2, zc3, zc4 = st.columns(4)
        strike_lo = zc1.slider("Strike low (% spot)",  70,  98,  80, 1,  key="vs_strike_lo")
        strike_hi = zc2.slider("Strike high (% spot)", 102, 130, 120, 1, key="vs_strike_hi")
        dte_lo    = zc3.slider("Min DTE",               1,   60,   7, 1,  key="vs_dte_lo")
        dte_hi    = zc4.slider("Max DTE",              30,  365, 180, 10, key="vs_dte_hi")

        mask_s = (strikes_all >= spot_price * strike_lo / 100) & \
                 (strikes_all <= spot_price * strike_hi / 100)
        mask_d = (dtes_all >= dte_lo) & (dtes_all <= dte_hi)
        strikes_z = strikes_all[mask_s]
        dtes_z    = dtes_all[mask_d]
        iv_z      = iv_all[np.ix_(mask_d, mask_s)]

        if strikes_z.size >= 2 and dtes_z.size >= 2:
            st.plotly_chart(C.vol_surface_3d(strikes_z, dtes_z, iv_z),
                            use_container_width=True, key="md_vol_surface")
        else:
            st.warning("Zoom range too narrow — broaden the strike or DTE range.")

        sm1, sm2 = st.columns([3, 1])
        with sm1:
            smile_df = simulate_iv_smile(S=spot_price, iv_base=iv_base)
            st.plotly_chart(C.iv_smile(smile_df), use_container_width=True, key="md_iv_smile")
        with sm2:
            st.markdown("**ATM Implied Vol**")
            for dte_val in [7, 21, 45, 90]:
                grp = smile_df[smile_df["dte"] == dte_val]
                if not grp.empty:
                    atm_row = grp.iloc[(grp["moneyness"] - 1).abs().argsort()[:1]]
                    st.metric(f"{dte_val} DTE", f"{float(atm_row['iv'].iloc[0]) * 100:.1f}%")

    # ── Top Movers + Dealer GEX ──────────────────────────────────────────────
    with st.expander("Market Activity", expanded=True):
        ma1, ma2 = st.columns(2)

        with ma1:
            movers_df = simulate_top_movers(ticker=ticker, n=30)
            st.plotly_chart(C.top_movers_bar(movers_df, ticker=ticker),
                            use_container_width=True, key="md_movers")
            gainers = (movers_df["change_pct"] > 0).sum()
            losers  = (movers_df["change_pct"] < 0).sum()
            m1, m2  = st.columns(2)
            m1.metric("Advancers", int(gainers))
            m2.metric("Decliners", int(losers))

        with ma2:
            gex_df = simulate_gex(S=spot_price, n_strikes=gex_n_strikes)
            st.plotly_chart(C.dealer_gex_bar(gex_df, S=spot_price, ticker=ticker),
                            use_container_width=True, key="md_gex")
            net_total = float(gex_df["net_gex"].sum())
        # Gamma flip: first sign change in net_gex when sorted by strike
        sorted_gex = gex_df.sort_values("strike")
        flip_level = spot_price
        for i in range(len(sorted_gex) - 1):
            a = sorted_gex.iloc[i]["net_gex"]
            b = sorted_gex.iloc[i + 1]["net_gex"]
            if a * b < 0:
                flip_level = float(sorted_gex.iloc[i]["strike"])
                break

        g1, g2, g3 = st.columns(3)
        g1.metric("Net GEX ($M)", f"{net_total / 1e6:+.1f}",
                  help="Positive = price-stabilising regime.")
        g2.metric("Gamma Flip", f"${flip_level:.0f}",
                  help="Strike where dealer hedging flips character.")
        g3.metric("Spot vs Flip", f"{spot_price - flip_level:+.0f} pts",
                  help="Distance of spot above/below the gamma flip.")

    # ── Momentum Indicators ──────────────────────────────────────────────────
    with st.expander(f"Momentum Indicators — {ticker}", expanded=True):
        mom_days = st.slider(
            "History (trading days)", min_value=60, max_value=504, value=252, step=20,
            key="md_mom_days",
        )

        momentum_df = None
        if not use_sim and api_key:
            with st.spinner(f"Fetching {ticker} bars…"):
                bars = _fetch_live_bars(ticker, api_key, n_days=mom_days)
            if not bars.empty:
                from alan_trader.data.features import add_price_features
                feat = add_price_features(bars.reset_index())
                feat["macd_line"]   = feat["macd"]
                feat["signal_line"] = feat["macd_signal"]
                momentum_df = feat[["date", "close", "rsi_14", "macd_line", "signal_line"]].rename(
                    columns={"rsi_14": "rsi"}
                ).dropna()
                st.caption(f"📡 Live data — {len(momentum_df)} trading days from Polygon.io")
        if momentum_df is None or momentum_df.empty:
            momentum_df = simulate_momentum_indicators(ticker=ticker, n_days=mom_days)

        st.plotly_chart(
            C.rsi_macd_chart(momentum_df, ticker=ticker),
            use_container_width=True, key="md_momentum",
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
