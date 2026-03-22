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


def _fetch_api_vol_surface_historical(
    ticker: str, api_key: str, as_of: "datetime.date",
    min_dte: int = 7, max_dte: int = 180,
    spot_range_pct: float = 0.25,
) -> "tuple[pd.DataFrame | None, str]":
    """
    Build a vol surface for a specific historical date using the same approach
    as the DB backfill — per-contract OHLC + BS IV inversion.
    No DB dependency. No volume filter.
    """
    import math
    import datetime as _dt
    from datetime import timedelta
    try:
        from alan_trader.data.polygon_client import PolygonClient
        from scipy.optimize import brentq as _brentq
        from scipy.stats import norm as _norm
    except ImportError as e:
        return None, f"Missing dependency: {e}"

    def _bs_mid(S, K, T, r, iv, opt):
        if T <= 0 or iv <= 0 or S <= 0 or K <= 0:
            return float("nan")
        try:
            d1 = (math.log(S / K) + (r + 0.5 * iv * iv) * T) / (iv * math.sqrt(T))
            d2 = d1 - iv * math.sqrt(T)
            if opt == "call":
                return S * _norm.cdf(d1) - K * math.exp(-r * T) * _norm.cdf(d2)
            else:
                return K * math.exp(-r * T) * _norm.cdf(-d2) - S * _norm.cdf(-d1)
        except Exception:
            return float("nan")

    try:
        client = PolygonClient(api_key=api_key)

        # Get spot price for the as_of date from Polygon aggregates
        agg = client._get(
            f"/v2/aggs/ticker/{ticker}/range/1/day/{as_of}/{as_of}",
            {"adjusted": "true", "limit": 1},
        )
        results = agg.get("results", [])
        if not results:
            return None, f"No price bar for {ticker} on {as_of}. Market may have been closed."
        S = float(results[0]["c"])  # close price

        strike_lo = round(S * (1 - spot_range_pct), 2)
        strike_hi = round(S * (1 + spot_range_pct), 2)
        exp_min   = str(as_of + timedelta(days=min_dte))
        exp_max   = str(as_of + timedelta(days=max_dte))

        # Enumerate contracts (including expired) active on as_of date
        all_contracts = []
        for ctype in ("call", "put"):
            url    = "/v3/reference/options/contracts"
            params = {
                "underlying_ticker":   ticker,
                "contract_type":       ctype,
                "expiration_date.gte": exp_min,
                "expiration_date.lte": exp_max,
                "strike_price.gte":    strike_lo,
                "strike_price.lte":    strike_hi,
                "expired":             "true",
                "limit":               1000,
            }
            while url:
                data = client._get(url, params)
                all_contracts.extend(data.get("results", []))
                url  = (data.get("next_url") or "").replace(client.BASE, "") or None
                params = {}

        if not all_contracts:
            return None, f"No option contracts found for {ticker} around {as_of} (strike {strike_lo}–{strike_hi}, DTE {min_dte}–{max_dte})."

        rows = []
        r    = 0.045  # fixed risk-free rate
        date_str = str(as_of)

        for contract in all_contracts:
            cticker  = contract["ticker"]
            K        = float(contract["strike_price"])
            exp_str  = contract["expiration_date"]
            opt_type = contract["contract_type"]  # "call" or "put"
            exp_date = _dt.date.fromisoformat(exp_str)
            dte      = (exp_date - as_of).days

            if not (min_dte <= dte <= max_dte):
                continue

            try:
                bar = client._get(
                    f"/v2/aggs/ticker/{cticker}/range/1/day/{date_str}/{date_str}",
                    {"adjusted": "true", "limit": 1},
                )
                bar_results = bar.get("results", [])
            except Exception:
                continue

            if not bar_results:
                continue

            close_price = float(bar_results[0].get("c", 0) or 0)
            if close_price <= 0:
                continue

            T = dte / 252.0
            intrinsic = max(0.0, S - K) if opt_type == "call" else max(0.0, K - S)
            if close_price <= intrinsic * 1.001:
                continue

            try:
                iv = _brentq(
                    lambda v: _bs_mid(S, K, T, r, v, opt_type) - close_price,
                    1e-4, 10.0, xtol=1e-5, maxiter=50,
                )
                if not (0.01 <= iv <= 5.0):
                    continue
            except (ValueError, RuntimeError):
                continue

            spread = max(0.01, close_price * (0.04 if close_price < 1 else 0.02))
            rows.append({
                "strike": K,
                "dte":    dte,
                "type":   opt_type,
                "iv":     round(iv, 6),
                "bid":    round(close_price - spread / 2, 4),
                "ask":    round(close_price + spread / 2, 4),
                "delta":  None,
            })

        if not rows:
            return None, f"No tradeable options with valid IV found for {ticker} on {as_of}."

        df = pd.DataFrame(rows)
        # Use calls for the surface (same convention as live API)
        calls = df[df["type"] == "call"]
        return (calls if not calls.empty else df), ""

    except Exception as e:
        return None, str(e)


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
    chart_type   = tc2.radio("View", ["Curve", "History", "3D Surface"], key="ts_chart_type", horizontal=True)

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
    elif chart_type == "History":
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

    # ── 3D Yield Surface ──────────────────────────────────────────────────────
    elif chart_type == "3D Surface":
        # Maturity in years for each tenor
        _TENOR_YEARS = [
            ("3M",  0.25,  "rate_3m"),
            ("6M",  0.5,   "rate_6m"),
            ("1Y",  1.0,   "rate_1y"),
            ("2Y",  2.0,   "rate_2y"),
            ("5Y",  5.0,   "rate_5y"),
            ("10Y", 10.0,  "rate_10y"),
            ("30Y", 30.0,  "rate_30y"),
        ]
        avail_tenors = [(lbl, yrs, col) for lbl, yrs, col in _TENOR_YEARS if col in df.columns]

        # Weekly sample — 2 years of daily data → ~104 rows
        surf_df = df.set_index("date").sort_index()
        surf_df = surf_df[[col for _, _, col in avail_tenors]].dropna(how="all")
        surf_df = surf_df.iloc[::5]  # every 5 trading days ≈ weekly

        dates_z    = surf_df.index.tolist()
        maturities = [yrs for _, yrs, _ in avail_tenors]
        tenor_cols = [col for _, _, col in avail_tenors]
        tenor_lbls = [lbl for lbl, _, _ in avail_tenors]

        # Z matrix: rows = dates, cols = tenors
        z_matrix = surf_df[tenor_cols].values.tolist()

        # Date labels for hover (convert to string)
        date_strs = [str(d) for d in dates_z]

        fig3d = go.Figure(data=[go.Surface(
            x=maturities,
            y=list(range(len(dates_z))),
            z=z_matrix,
            colorscale=[
                [0.0,  "#1a237e"],
                [0.25, "#1565c0"],
                [0.5,  "#00acc1"],
                [0.75, "#ffb300"],
                [1.0,  "#e53935"],
            ],
            colorbar=dict(title="Yield (%)", thickness=15, len=0.7),
            hovertemplate=(
                "Maturity: %{x}Y<br>"
                "Yield: %{z:.2f}%<extra></extra>"
            ),
            showscale=True,
        )])

        # Annotate y-axis with date labels (sample every 10 weeks)
        tick_step = max(1, len(dates_z) // 10)
        tick_vals = list(range(0, len(dates_z), tick_step))
        tick_text = [date_strs[i] for i in tick_vals]

        fig3d.update_layout(
            title="Treasury Yield Surface — Maturity × Time",
            scene=dict(
                xaxis=dict(
                    title="Maturity (years)",
                    tickvals=maturities,
                    ticktext=tenor_lbls,
                    gridcolor="#2a2f3f",
                    backgroundcolor="#0e1117",
                ),
                yaxis=dict(
                    title="Date",
                    tickvals=tick_vals,
                    ticktext=tick_text,
                    gridcolor="#2a2f3f",
                    backgroundcolor="#0e1117",
                ),
                zaxis=dict(
                    title="Yield (%)",
                    tickformat=".2f",
                    gridcolor="#2a2f3f",
                    backgroundcolor="#0e1117",
                ),
                camera=dict(eye=dict(x=1.8, y=-1.6, z=0.8)),
                bgcolor="#0e1117",
            ),
            paper_bgcolor="#0e1117",
            font=dict(color="#e0e0e0"),
            height=600,
            margin=dict(t=50, b=20, l=20, r=20),
        )
        st.plotly_chart(fig3d, width="stretch", key="ts_3d_surface")


def render(ticker: str = "SPY", api_key: str = ""):
    st.header(f"Market Data — {ticker}")

    from alan_trader.data.simulator import (
        TICKER_PROFILES, DEFAULT_PROFILE,
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
    with st.expander(f"📈 Price Chart — {ticker}", expanded=True):

        # Live quote strip at the top of the chart section
        if api_key:
            with st.spinner(f"Fetching live quote for {ticker}…"):
                q = _fetch_live_quote(ticker, api_key)
            if q.get("price"):
                default_S = q["price"]
                # Force the spot price widget to refresh when ticker changes
                st.session_state[f"md_spot_price_{ticker}"] = default_S
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
            st.warning(
                f"No price bars found for **{ticker}**. "
                "Go to **Tools → Data Manager → Sync Price Bars** to download data."
            )
            return

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
    with st.expander("📐 Treasury Term Structure", expanded=False):
        _render_term_structure()

    # ── Shared controls (used by Vol Surface + GEX below) ────────────────────
    st.markdown("---")
    ctrl1, ctrl2, ctrl3 = st.columns(3)
    spot_price = ctrl1.number_input(
        f"{ticker} Price ($)", value=float(default_S),
        min_value=1.0, max_value=10_000.0, step=max(1.0, default_S * 0.01),
        key=f"md_spot_price_{ticker}",
    )
    iv_base = ctrl2.slider(
        "Base IV (%)", min_value=5, max_value=120, value=int(profile["annual_vol"] * 100),
        key=f"md_iv_base_{ticker}",
    ) / 100.0
    gex_n_strikes = ctrl3.slider(
        "GEX strikes shown", min_value=10, max_value=30, value=20,
        key="md_gex_n_strikes",
    )
    st.markdown("---")

    # ── Volatility Surface ───────────────────────────────────────────────────
    with st.expander("🌊 Volatility Surface", expanded=False):
        import datetime as _vs_dt

        # ── Controls row ──────────────────────────────────────────────────
        vc1, vc2, vc3 = st.columns([2, 2, 2])
        dte_lo = vc1.slider("Min DTE",  1,  60,   7, 1,  key="vs_dte_lo")
        dte_hi = vc2.slider("Max DTE", 30, 365, 180, 10, key="vs_dte_hi")
        as_of  = vc3.date_input("As Of", value=_vs_dt.date.today(),
                                min_value=_vs_dt.date(2020, 1, 1),
                                max_value=_vs_dt.date.today(), key="vs_as_of")

        surf_df  = None
        surf_src = ""
        surf_err = ""

        if api_key:
            _is_today = (as_of == _vs_dt.date.today())
            if _is_today:
                with st.spinner("Fetching live options chain…"):
                    surf_df, surf_err = _fetch_live_vol_surface(
                        ticker, api_key, spot_price, min_dte=dte_lo, max_dte=dte_hi
                    )
                surf_src = f"📡 Live IV surface — {ticker}"
            else:
                with st.spinner(f"Building IV surface for {ticker} on {as_of} (per-contract OHLC + BS inversion)…"):
                    surf_df, surf_err = _fetch_api_vol_surface_historical(
                        ticker, api_key, as_of, min_dte=dte_lo, max_dte=dte_hi
                    )
                surf_src = f"📡 IV surface — {ticker} as of {as_of} (per-contract OHLC)"
        else:
            surf_err = ""

        if not api_key:
            st.info("Enter your Polygon API key in the sidebar to load the surface.")
        elif surf_df is None or surf_df.empty:
            msg = surf_err or f"IV surface unavailable for {ticker} on {as_of}."
            st.warning(msg)
        else:
            live_surf = surf_df
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
                    iv_z = iv_nearest

            n_strikes = strikes_z.size
            n_dtes    = dtes_z.size
            if n_strikes >= 2 and n_dtes >= 2:
                st.caption(f"{surf_src} — {n_strikes} strikes × {n_dtes} expirations")
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
                    title=f"IV Smile — {ticker} ({dte_val} DTE)",
                    xaxis_title="Strike", yaxis_title="IV",
                    template="plotly_dark", height=320,
                    margin=dict(t=40, b=40, l=50, r=20),
                )
                st.caption(surf_src + " — single expiry, showing IV smile.")
                st.plotly_chart(fig_smile, width="stretch", key="md_vol_surface")
            else:
                st.warning(
                    f"Not enough data for {ticker}: {n_strikes} strike(s) × {n_dtes} expiry(s). "
                    "Try widening the DTE range."
                )

            with st.expander("📋 Raw chain data", expanded=False):
                show_cols = [c for c in ["strike", "dte", "iv", "bid", "ask", "delta"] if c in surf_df.columns]
                st.dataframe(
                    surf_df[show_cols].sort_values(["dte", "strike"]),
                    hide_index=True, width="stretch",
                    column_config={
                        "strike": st.column_config.NumberColumn("Strike",  format="$%.1f"),
                        "dte":    st.column_config.NumberColumn("DTE",     format="%d"),
                        "iv":     st.column_config.NumberColumn("IV",      format="%.1f%%"),
                        "bid":    st.column_config.NumberColumn("Bid",     format="$%.3f"),
                        "ask":    st.column_config.NumberColumn("Ask",     format="$%.3f"),
                        "delta":  st.column_config.NumberColumn("Delta",   format="%.3f"),
                    },
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
    with st.expander("🔥 Market Activity", expanded=False):
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
    with st.expander(f"⚡ Momentum Indicators — {ticker}", expanded=False):
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

    # ── Correlation Analysis ──────────────────────────────────────────────────
    with st.expander("📊 Correlation Analysis", expanded=False):
        st.caption("Compare price and returns between two tickers — scatter, rolling correlation, return distribution, and cumulative performance.")
        cor1, cor2, cor3 = st.columns(3)
        comp_ticker = cor1.text_input("Compare with ticker", value="SPY", key=f"corr_comp_{ticker}").upper().strip() or "SPY"
        corr_days   = cor2.slider("Lookback (trading days)", 30, 504, 252, step=21, key=f"corr_days_{ticker}")
        corr_window = cor3.slider("Rolling corr window (days)", 10, 60, 21, step=5, key=f"corr_window_{ticker}")

        if st.button("Run Correlation", key=f"corr_run_{ticker}"):
            import numpy as np
            import plotly.graph_objects as go
            from plotly.subplots import make_subplots

            with st.spinner(f"Fetching {ticker} and {comp_ticker} price history…"):
                df_a = _fetch_live_bars(ticker,      api_key, n_days=corr_days) if api_key else pd.DataFrame()
                df_b = _fetch_live_bars(comp_ticker, api_key, n_days=corr_days) if api_key else pd.DataFrame()

            if df_a.empty or df_b.empty:
                st.warning(f"Could not fetch price data for one or both tickers. Check API key and ticker symbols.")
            else:
                # Align on common dates
                df_a = df_a.set_index("date")["close"].rename(ticker)      if "date" in df_a.columns else df_a["close"].rename(ticker)
                df_b = df_b.set_index("date")["close"].rename(comp_ticker) if "date" in df_b.columns else df_b["close"].rename(comp_ticker)
                prices = pd.concat([df_a, df_b], axis=1).dropna()
                if len(prices) < 10:
                    st.warning("Not enough overlapping trading days to compute correlation.")
                else:
                    rets = prices.pct_change().dropna()
                    overall_corr = float(rets[ticker].corr(rets[comp_ticker]))
                    beta         = float(np.cov(rets[ticker], rets[comp_ticker])[0, 1] / np.var(rets[comp_ticker]))
                    roll_corr    = rets[ticker].rolling(corr_window).corr(rets[comp_ticker]).dropna()

                    # Normalised cumulative return
                    cum_a = (1 + rets[ticker]).cumprod()
                    cum_b = (1 + rets[comp_ticker]).cumprod()

                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("Pearson Corr",   f"{overall_corr:.3f}")
                    m2.metric("Beta",           f"{beta:.3f}",           help=f"{ticker} β vs {comp_ticker}")
                    m3.metric(f"{ticker} Vol",  f"{rets[ticker].std()*16:.1f}%",      help="Annualised daily vol × √252 / √16≈252/16 daily approx")
                    m4.metric(f"{comp_ticker} Vol", f"{rets[comp_ticker].std()*16:.1f}%")

                    _L = dict(template="plotly_dark", margin=dict(l=40, r=20, t=45, b=35), height=320)

                    row1_l, row1_r = st.columns(2)
                    row2_l, row2_r = st.columns(2)

                    # ── Top-left: Cumulative return ───────────────────────────
                    with row1_l:
                        fig = go.Figure()
                        fig.add_trace(go.Scatter(x=cum_a.index.astype(str), y=cum_a.values,
                                                 name=ticker, line=dict(color="#00cc96", width=2)))
                        fig.add_trace(go.Scatter(x=cum_b.index.astype(str), y=cum_b.values,
                                                 name=comp_ticker, line=dict(color="#ab63fa", width=2)))
                        fig.update_layout(title=f"Cumulative Return",
                                          xaxis_title="Date", yaxis_title="Growth of $1", **_L)
                        st.plotly_chart(fig, width="stretch", key=f"corr_cum_{ticker}")

                    # ── Top-right: Scatter + regression ──────────────────────
                    with row1_r:
                        m_coef = np.polyfit(rets[comp_ticker].values, rets[ticker].values, 1)
                        x_line = np.linspace(rets[comp_ticker].min(), rets[comp_ticker].max(), 100)
                        fig2 = go.Figure()
                        fig2.add_trace(go.Scatter(
                            x=rets[comp_ticker].values, y=rets[ticker].values,
                            mode="markers", name="Daily returns",
                            marker=dict(size=4, color="#00b4d8", opacity=0.55),
                        ))
                        fig2.add_trace(go.Scatter(
                            x=x_line, y=np.polyval(m_coef, x_line),
                            mode="lines", name=f"β={beta:.2f}",
                            line=dict(color="#ff6b6b", width=2, dash="dash"),
                        ))
                        fig2.update_layout(
                            title=f"Return Scatter  ρ={overall_corr:.2f}  β={beta:.2f}",
                            xaxis_title=f"{comp_ticker} return",
                            yaxis_title=f"{ticker} return",
                            xaxis_tickformat=".1%", yaxis_tickformat=".1%", **_L,
                        )
                        st.plotly_chart(fig2, width="stretch", key=f"corr_sc_{ticker}")

                    # ── Bottom-left: Rolling correlation ─────────────────────
                    with row2_l:
                        fig3 = go.Figure()
                        fig3.add_trace(go.Scatter(
                            x=roll_corr.index.astype(str), y=roll_corr.values,
                            mode="lines", name=f"{corr_window}d ρ",
                            line=dict(color="#ffd166", width=2),
                            fill="tozeroy", fillcolor="rgba(255,209,102,0.12)",
                        ))
                        fig3.add_hline(y=overall_corr, line_dash="dash", line_color="#888",
                                       annotation_text=f"  avg {overall_corr:.2f}")
                        fig3.add_hline(y=0, line_color="#444")
                        fig3.update_layout(
                            title=f"{corr_window}-day Rolling Correlation",
                            xaxis_title="Date", yaxis_title="ρ",
                            yaxis=dict(range=[-1.1, 1.1]), **_L,
                        )
                        st.plotly_chart(fig3, width="stretch", key=f"corr_roll_{ticker}")

                    # ── Bottom-right: Return distribution ────────────────────
                    with row2_r:
                        fig4 = go.Figure()
                        fig4.add_trace(go.Histogram(
                            x=rets[ticker].values, name=ticker,
                            nbinsx=50, opacity=0.7,
                            marker_color="#00cc96", histnorm="probability",
                        ))
                        fig4.add_trace(go.Histogram(
                            x=rets[comp_ticker].values, name=comp_ticker,
                            nbinsx=50, opacity=0.7,
                            marker_color="#ab63fa", histnorm="probability",
                        ))
                        fig4.update_layout(
                            title="Return Distribution",
                            xaxis_title="Daily Return", yaxis_title="Probability",
                            xaxis_tickformat=".1%", barmode="overlay", **_L,
                        )
                        st.plotly_chart(fig4, width="stretch", key=f"corr_dist_{ticker}")
