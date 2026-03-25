"""
Trade Log tab — Real position tracking, P&L, and model signal accountability.

Log Trade UX follows real trader workflow:
  1. Quick Entry  — symbol + type + strikes + net credit/debit → everything else is math
  2. CSV Import   — paste or upload broker export (Tastytrade / IBKR / Schwab)
  3. Manual Close — express or full close from open positions list
"""
from __future__ import annotations

import datetime
import io
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit import column_config as cc


SPREAD_TYPES = [
    "bull_put", "bear_call", "iron_condor",
    "bull_call", "bear_put", "long_straddle", "short_strangle", "call_butterfly",
]
CREDIT_SPREADS = {"iron_condor", "bull_put", "bear_call", "short_strangle"}
SPREAD_LABELS  = {
    "bull_put":       "Bull Put Spread",
    "bear_call":      "Bear Call Spread",
    "iron_condor":    "Iron Condor",
    "bull_call":      "Bull Call Spread",
    "bear_put":       "Bear Put Spread",
    "long_straddle":  "Long Straddle",
    "short_strangle": "Short Strangle",
    "call_butterfly": "Call Butterfly",
}
SYMBOLS = ["HOOD", "SPY", "QQQ", "AAPL", "TSLA", "MARA", "NVDA", "AMZN"]


# ─────────────────────────────────────────────────────────────────────────────
# Risk math — derive max profit / max loss / breakeven from strikes + net fill
# ─────────────────────────────────────────────────────────────────────────────

def _compute_risk(spread_type: str, strikes: dict, net: float) -> dict:
    """
    net  > 0  = credit received per share
    net  < 0  = debit paid per share  (stored as negative)
    Returns dict: max_profit, max_loss, breakevens (list), wing
    All values are per-share (multiply × 100 for per-contract dollar value).
    """
    r: dict = {"max_profit": 0.0, "max_loss": 0.0, "breakevens": [], "wing": 0.0}
    try:
        if spread_type in ("bull_put", "bear_call"):
            short = strikes.get("short", 0.0)
            long  = strikes.get("long",  0.0)
            wing  = abs(short - long)
            r["wing"]       = wing
            r["max_profit"] = net                   # credit received
            r["max_loss"]   = -(wing - net)         # negative = loss
            if spread_type == "bull_put":
                r["breakevens"] = [round(short - net, 2)]
            else:
                r["breakevens"] = [round(short + net, 2)]

        elif spread_type in ("bull_call", "bear_put"):
            long  = strikes.get("long",  0.0)
            short = strikes.get("short", 0.0)
            wing  = abs(short - long)
            debit = abs(net)
            r["wing"]       = wing
            r["max_profit"] = wing - debit
            r["max_loss"]   = -debit
            if spread_type == "bull_call":
                r["breakevens"] = [round(long + debit, 2)]
            else:
                r["breakevens"] = [round(long - debit, 2)]

        elif spread_type == "iron_condor":
            ps = strikes.get("put_short",  0.0)
            pl = strikes.get("put_long",   0.0)
            cs = strikes.get("call_short", 0.0)
            cl = strikes.get("call_long",  0.0)
            put_wing  = abs(ps - pl)
            call_wing = abs(cl - cs)
            wing      = min(put_wing, call_wing)   # max risk = wider wing
            r["wing"]       = wing
            r["max_profit"] = net
            r["max_loss"]   = -(wing - net)
            r["breakevens"] = [round(ps - net, 2), round(cs + net, 2)]

        elif spread_type == "long_straddle":
            strike = strikes.get("strike", 0.0)
            debit  = abs(net)
            r["max_profit"] = None                  # theoretically unlimited
            r["max_loss"]   = -debit
            r["breakevens"] = [round(strike - debit, 2), round(strike + debit, 2)]

        elif spread_type == "short_strangle":
            ps = strikes.get("put_strike",  0.0)
            cs = strikes.get("call_strike", 0.0)
            r["max_profit"] = net
            r["max_loss"]   = None                  # theoretically unlimited
            r["breakevens"] = [round(ps - net, 2), round(cs + net, 2)]

        elif spread_type == "call_butterfly":
            low = strikes.get("low",  0.0)
            mid = strikes.get("mid",  0.0)
            high = strikes.get("high", 0.0)
            wing  = abs(mid - low)
            debit = abs(net)
            r["wing"]       = wing
            r["max_profit"] = wing - debit
            r["max_loss"]   = -debit
            r["breakevens"] = [round(low + debit, 2), round(high - debit, 2)]

    except Exception:
        pass
    return r


def _strike_inputs(spread_type: str, prefix: str) -> dict:
    """Render minimal strike inputs for a given spread type. Returns dict of strike values."""
    st.markdown("**Strikes**")
    strikes: dict = {}

    if spread_type in ("bull_put", "bear_call"):
        label_s = "Sell Put" if spread_type == "bull_put" else "Sell Call"
        label_l = "Buy Put"  if spread_type == "bull_put" else "Buy Call"
        c1, c2 = st.columns(2)
        strikes["short"] = c1.number_input(f"{label_s} (short strike)", value=0.0, step=0.5, key=f"{prefix}_short")
        strikes["long"]  = c2.number_input(f"{label_l} (long strike)",  value=0.0, step=0.5, key=f"{prefix}_long")

    elif spread_type in ("bull_call", "bear_put"):
        label_l = "Buy Call"  if spread_type == "bull_call" else "Buy Put"
        label_s = "Sell Call" if spread_type == "bull_call" else "Sell Put"
        c1, c2 = st.columns(2)
        strikes["long"]  = c1.number_input(f"{label_l} (long strike)",  value=0.0, step=0.5, key=f"{prefix}_long")
        strikes["short"] = c2.number_input(f"{label_s} (short strike)", value=0.0, step=0.5, key=f"{prefix}_short")

    elif spread_type == "iron_condor":
        c1, c2, c3, c4 = st.columns(4)
        strikes["put_short"]  = c1.number_input("Sell Put",  value=0.0, step=0.5, key=f"{prefix}_ps")
        strikes["put_long"]   = c2.number_input("Buy Put",   value=0.0, step=0.5, key=f"{prefix}_pl")
        strikes["call_short"] = c3.number_input("Sell Call", value=0.0, step=0.5, key=f"{prefix}_cs")
        strikes["call_long"]  = c4.number_input("Buy Call",  value=0.0, step=0.5, key=f"{prefix}_cl")

    elif spread_type == "long_straddle":
        c1, = st.columns([1])
        strikes["strike"] = c1.number_input("ATM Strike (call + put)", value=0.0, step=0.5, key=f"{prefix}_atm")

    elif spread_type == "short_strangle":
        c1, c2 = st.columns(2)
        strikes["put_strike"]  = c1.number_input("Sell Put Strike",  value=0.0, step=0.5, key=f"{prefix}_psk")
        strikes["call_strike"] = c2.number_input("Sell Call Strike", value=0.0, step=0.5, key=f"{prefix}_csk")

    elif spread_type == "call_butterfly":
        c1, c2, c3 = st.columns(3)
        strikes["low"]  = c1.number_input("Buy Low Call",  value=0.0, step=0.5, key=f"{prefix}_low")
        strikes["mid"]  = c2.number_input("Sell 2× Mid",   value=0.0, step=0.5, key=f"{prefix}_mid")
        strikes["high"] = c3.number_input("Buy High Call", value=0.0, step=0.5, key=f"{prefix}_high")

    return strikes


def _risk_card(spread_type: str, symbol: str, strikes: dict, net: float,
               contracts: int, expiration: datetime.date, open_date: datetime.date) -> None:
    """Render a compact confirmation card showing computed risk stats."""
    r = _compute_risk(spread_type, strikes, net)
    dte = (expiration - open_date).days
    is_credit = spread_type in CREDIT_SPREADS

    # Build strike summary string
    sk_parts = []
    for k, v in strikes.items():
        if v:
            sk_parts.append(f"{v:.0f}")
    strike_str = "/".join(sk_parts) if sk_parts else "—"

    mp_dollars = (r["max_profit"]  * contracts * 100) if r["max_profit"]  is not None else None
    ml_dollars = (abs(r["max_loss"]) * contracts * 100) if r["max_loss"]   is not None else None
    net_dollars = abs(net) * contracts * 100

    mp_str = f"${mp_dollars:,.2f}" if mp_dollars is not None else "Unlimited"
    ml_str = f"${ml_dollars:,.2f}" if ml_dollars is not None else "Unlimited"
    be_str = " / ".join(f"${b:.2f}" for b in r["breakevens"]) if r["breakevens"] else "—"

    border = "#26a69a" if is_credit else "#5c6bc0"
    label  = SPREAD_LABELS.get(spread_type, spread_type)
    net_label = "Net credit" if is_credit else "Net debit"

    st.markdown(f"""
<div style="
  background:#161b27; border-left:4px solid {border};
  border-radius:8px; padding:14px 18px; margin:12px 0;
  display:grid; grid-template-columns:1fr 1fr 1fr 1fr;
  gap:10px 20px;
">
  <div style="grid-column:1/-1; color:#e0e0e0; font-size:1.05rem; font-weight:600; margin-bottom:6px">
    {contracts}× {symbol} {strike_str} {label}
  </div>
  <div>
    <div style="color:#78909c; font-size:11px">{net_label}</div>
    <div style="color:{border}; font-weight:700; font-size:1.1rem">${abs(net):.2f}/share</div>
    <div style="color:#b0b8c8; font-size:12px">${net_dollars:,.2f} total</div>
  </div>
  <div>
    <div style="color:#78909c; font-size:11px">Max profit</div>
    <div style="color:#26a69a; font-weight:600">{mp_str}</div>
  </div>
  <div>
    <div style="color:#78909c; font-size:11px">Max loss / margin</div>
    <div style="color:#ef5350; font-weight:600">{ml_str}</div>
  </div>
  <div>
    <div style="color:#78909c; font-size:11px">Breakeven{"s" if len(r["breakevens"]) > 1 else ""}</div>
    <div style="color:#e0e0e0">{be_str}</div>
  </div>
  <div>
    <div style="color:#78909c; font-size:11px">DTE</div>
    <div style="color:#e0e0e0">{dte}d</div>
  </div>
</div>""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# CSV import — parse broker exports
# ─────────────────────────────────────────────────────────────────────────────

def _parse_tastytrade_csv(content: str) -> pd.DataFrame:
    """
    Parse a Tastytrade transaction history CSV.
    Columns: Date,Type,Action,Symbol,Instrument Type,Description,Value,Quantity,
             Average Price,Commissions,Fees,Multiplier,Underlying Symbol,Expiration Date,
             Strike Price,Call or Put
    Returns a DataFrame with one row per POSITION (matched legs grouped).
    """
    try:
        df = pd.read_csv(io.StringIO(content))
        df.columns = [c.strip() for c in df.columns]
        # Keep only options trades
        opts = df[df.get("Instrument Type", df.get("Type", pd.Series(dtype=str))) == "Equity Option"].copy()
        if opts.empty:
            return pd.DataFrame()
        return opts
    except Exception:
        return pd.DataFrame()


def _parse_ibkr_csv(content: str) -> pd.DataFrame:
    """Parse IBKR Flex Query CSV — Trades section."""
    try:
        df = pd.read_csv(io.StringIO(content))
        df.columns = [c.strip() for c in df.columns]
        opts = df[df.get("AssetClass", pd.Series(dtype=str)).str.upper() == "OPT"].copy() if "AssetClass" in df.columns else df
        return opts
    except Exception:
        return pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
# Chart helpers
# ─────────────────────────────────────────────────────────────────────────────

def _chart_equity_curve(history_df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=history_df["BalanceDate"], y=history_df["TotalEquity"],
        mode="lines", name="Total Equity",
        line=dict(color="#5c6bc0", width=2),
        fill="tozeroy", fillcolor="rgba(92,107,192,0.1)",
    ))
    fig.update_layout(
        title="Account Equity", height=300,
        paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
        font=dict(color="#b0b8c8"),
        xaxis=dict(gridcolor="#1e2130"), yaxis=dict(gridcolor="#1e2130"),
        margin=dict(l=0, r=0, t=36, b=0),
    )
    return fig


def _chart_monthly_pnl(monthly_df: pd.DataFrame) -> go.Figure:
    colors = ["#4caf50" if v >= 0 else "#ef5350" for v in monthly_df["MonthlyPnL"]]
    fig = go.Figure()
    fig.add_bar(x=monthly_df["YearMonth"], y=monthly_df["MonthlyPnL"],
                marker_color=colors, name="Monthly P&L")
    fig.add_trace(go.Scatter(
        x=monthly_df["YearMonth"], y=monthly_df["CumPnL"],
        mode="lines+markers", name="Cumulative",
        line=dict(color="#ffb300", width=2), yaxis="y2",
    ))
    fig.update_layout(
        title="Monthly P&L", height=320,
        paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
        font=dict(color="#b0b8c8"),
        xaxis=dict(gridcolor="#1e2130"),
        yaxis=dict(gridcolor="#1e2130", title="Month P&L ($)"),
        yaxis2=dict(title="Cumulative ($)", overlaying="y", side="right",
                    gridcolor="rgba(0,0,0,0)"),
        legend=dict(orientation="h", y=1.1),
        margin=dict(l=0, r=0, t=40, b=0),
    )
    return fig


def _chart_strategy_bars(perf_df: pd.DataFrame) -> go.Figure:
    df = perf_df.sort_values("TotalPnL", ascending=True)
    label_col = df.get("StrategyName", df.get("Symbol", pd.Series(["?"] * len(df), dtype=str)))
    if "StrategyName" in df.columns and "Symbol" in df.columns:
        labels = df["Symbol"].fillna("") + " / " + df["StrategyName"].fillna("")
    elif "StrategyName" in df.columns:
        labels = df["StrategyName"].fillna("—")
    else:
        labels = df["Symbol"].fillna("—")
    colors = ["#4caf50" if v >= 0 else "#ef5350" for v in df["TotalPnL"]]
    fig = go.Figure(go.Bar(
        x=df["TotalPnL"],
        y=labels,
        orientation="h", marker_color=colors,
        text=[f"W:{int(r['Wins'])}  L:{int(r['Losses'])}  ({r['WinRate']}%)" for _, r in df.iterrows()],
        textposition="auto",
    ))
    fig.update_layout(
        title="P&L by Strategy", height=max(250, len(df) * 50),
        paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
        font=dict(color="#b0b8c8"),
        xaxis=dict(gridcolor="#1e2130", title="Total P&L ($)"),
        margin=dict(l=0, r=0, t=36, b=0),
    )
    return fig


def _chart_cumulative_pnl(closed_df: pd.DataFrame, strategy_filter: list | None = None) -> go.Figure:
    """Cumulative P&L over time, one line per strategy (or filtered subset)."""
    df = closed_df.copy()
    df["CloseDate"] = pd.to_datetime(df["CloseDate"])
    df = df.sort_values("CloseDate")

    strat_col = "StrategyName" if "StrategyName" in df.columns else None
    if strat_col and strategy_filter:
        df = df[df[strat_col].isin(strategy_filter)]

    fig = go.Figure()
    palette = ["#5c6bc0", "#26a69a", "#ffb300", "#ef5350", "#ab47bc",
               "#42a5f5", "#66bb6a", "#ff7043", "#ec407a", "#78909c"]

    if strat_col:
        strategies = df[strat_col].fillna("(none)").unique()
        for i, strat in enumerate(sorted(strategies)):
            sd = df[df[strat_col].fillna("(none)") == strat].copy()
            sd = sd.sort_values("CloseDate")
            sd["CumPnL"] = sd["RealizedPnL"].cumsum()
            color = palette[i % len(palette)]
            fig.add_trace(go.Scatter(
                x=sd["CloseDate"], y=sd["CumPnL"],
                mode="lines+markers", name=strat or "(none)",
                line=dict(color=color, width=2),
                marker=dict(size=5),
            ))
    else:
        df["CumPnL"] = df["RealizedPnL"].cumsum()
        fig.add_trace(go.Scatter(
            x=df["CloseDate"], y=df["CumPnL"],
            mode="lines", name="All trades",
            line=dict(color="#5c6bc0", width=2),
            fill="tozeroy", fillcolor="rgba(92,107,192,0.1)",
        ))

    # zero line
    fig.add_hline(y=0, line=dict(color="#546e7a", width=1, dash="dot"))

    fig.update_layout(
        title="Cumulative P&L by Strategy", height=360,
        paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
        font=dict(color="#b0b8c8"),
        xaxis=dict(gridcolor="#1e2130"),
        yaxis=dict(gridcolor="#1e2130", title="Cumulative P&L ($)"),
        legend=dict(orientation="h", y=1.08),
        margin=dict(l=0, r=0, t=50, b=0),
    )
    return fig


def _chart_pnl_histogram(closed_df: pd.DataFrame) -> go.Figure:
    wins   = closed_df[closed_df["RealizedPnL"] > 0]["RealizedPnL"]
    losses = closed_df[closed_df["RealizedPnL"] <= 0]["RealizedPnL"]
    fig = go.Figure()
    fig.add_trace(go.Histogram(x=wins,   name="Wins",   marker_color="#4caf50", opacity=0.8))
    fig.add_trace(go.Histogram(x=losses, name="Losses", marker_color="#ef5350", opacity=0.8))
    fig.update_layout(
        title="P&L Distribution", barmode="overlay", height=280,
        paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
        font=dict(color="#b0b8c8"),
        xaxis=dict(gridcolor="#1e2130", title="Realized P&L ($)"),
        yaxis=dict(gridcolor="#1e2130"),
        legend=dict(orientation="h", y=1.1),
        margin=dict(l=0, r=0, t=36, b=0),
    )
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# Main render
# ─────────────────────────────────────────────────────────────────────────────

def render(api_key: str = ""):
    st.markdown("## Portfolio")

    try:
        from alan_trader.db.client import get_engine
        from sqlalchemy import text as _text
        engine = get_engine()
    except Exception as e:
        st.error(f"Database not available: {e}")
        return

    try:
        with engine.connect() as _c:
            accounts = pd.read_sql(_text(
                "SELECT AccountId, AccountName AS Name FROM portfolio.Account WHERE Status = 'Active' ORDER BY AccountId"
            ), _c)
    except Exception:
        st.error("Portfolio schema not found. Run the migration in `db/migrations/rebuild_portfolio.sql` first.")
        return

    if accounts.empty:
        st.error("No accounts found. Check the portfolio schema.")
        return

    acct_options = {row["Name"]: row["AccountId"] for _, row in accounts.iterrows()}
    selected_acct_name = st.selectbox("Account", list(acct_options.keys()), key="tl_account")
    account_id = acct_options[selected_acct_name]

    st.info("📌 Portfolio tracking has moved to the **Paper Trading** tab with the new schema. "
            "The legacy Portfolio section below is being migrated.")

    try:
        from alan_trader.db import portfolio_client as pc
    except Exception:
        st.warning("portfolio_client not available — legacy Portfolio section disabled.")
        return

    # KPI header
    kpis = pc.get_kpis(engine, account_id)
    k1, k2, k3, k4, k5 = st.columns(5)
    def _d(v): return f"${v:+,.2f}" if v is not None else None   # delta string → drives green/red

    k1.metric("Total Equity",     f"${kpis['total_equity']:,.2f}"  if kpis["total_equity"] else "—")
    k2.metric("Day P&L",          f"${kpis['day_pnl']:,.2f}"       if kpis["day_pnl"]      else "—",
              delta=_d(kpis["day_pnl"]))
    k3.metric("YTD Realized P&L", f"${kpis['ytd_pnl']:,.2f}"       if kpis["ytd_pnl"]      else "—",
              delta=_d(kpis["ytd_pnl"]))
    k4.metric("Open Positions",   str(kpis["open_positions"]))
    k5.metric("Win Rate",         f"{kpis['win_rate']:.1f}%"        if kpis["win_rate"]     else "—",
              help=f"{kpis['wins']} wins of {kpis['total_trades']} closed trades")

    st.markdown("---")

    t_open, t_log, t_close, t_history, t_perf, t_model = st.tabs([
        "📂 Open Positions", "➕ Log Trade", "✅ Close Position",
        "📋 History", "📈 Performance", "🤖 Model Accuracy"
    ])

    # ══════════════════════════════════════════════════════════════════════════
    # OPEN POSITIONS
    # ══════════════════════════════════════════════════════════════════════════
    with t_open:
        open_df = pc.get_open_positions(engine, account_id)
        if open_df.empty:
            st.info("No open positions. Use **Log Trade** to record a new position.")
        else:
            avail = [c for c in [
                "Symbol","PositionType","Quantity","Direction","OpenDate",
                "AvgEntryPrice","EntryDollars","UnrealizedPnL",
                "Regime","StrategyName","Source","Notes"
            ] if c in open_df.columns]
            disp = open_df[avail].copy()
            st.dataframe(disp, width="stretch", hide_index=True, column_config={
                "UnrealizedPnL": cc.NumberColumn("Unreal P&L", format="$%.2f"),
                "EntryDollars":  cc.NumberColumn("Entry $",    format="$%.2f"),
                "AvgEntryPrice": cc.NumberColumn("Avg Entry",  format="$%.4f"),
                "Quantity":      cc.NumberColumn("Qty"),
            })

    # ══════════════════════════════════════════════════════════════════════════
    # LOG TRADE  — quick-entry
    # ══════════════════════════════════════════════════════════════════════════
    with t_log:
        log_tab_q, log_tab_csv = st.tabs(["⚡ Quick Entry", "📥 Import from Broker"])

        # ── Quick Entry ───────────────────────────────────────────────────────
        with log_tab_q:
            # Row 1: identity
            c1, c2, c3, c4, c5 = st.columns([2, 3, 1, 2, 2])
            lg_symbol    = c1.selectbox("Underlying", SYMBOLS, key="lg_sym")
            lg_spread    = c2.selectbox("Spread type", SPREAD_TYPES,
                                         format_func=lambda k: SPREAD_LABELS[k], key="lg_spread")
            lg_contracts = c3.number_input("Qty", min_value=1, value=1, step=1, key="lg_ct",
                                            label_visibility="visible")
            lg_open_date = c4.date_input("Open date", value=datetime.date.today(), key="lg_od")
            lg_expiry    = c5.date_input("Expiration", key="lg_exp",
                                          value=datetime.date.today() + datetime.timedelta(days=30))

            st.markdown("")
            # Row 2: strikes (dynamic)
            strikes = _strike_inputs(lg_spread, "lg")

            st.markdown("")
            # Row 3: net fill
            is_credit = lg_spread in CREDIT_SPREADS
            net_label = "Net credit received ($/share)" if is_credit else "Net debit paid ($/share)"
            net_help  = ("The total premium you received when opening. E.g. for SPY 550/545 bull put @ $2.15 credit → enter 2.15"
                         if is_credit else
                         "The total premium you paid. E.g. for a $1.50 debit spread → enter 1.50")
            n1, n2 = st.columns([2, 5])
            lg_net = n1.number_input(net_label, value=0.0, min_value=0.0, step=0.01,
                                      key="lg_net", help=net_help)
            if lg_net > 0 and any(v > 0 for v in strikes.values()):
                with n2:
                    st.markdown("")
                    _risk_card(lg_spread, lg_symbol, strikes, lg_net if is_credit else -lg_net,
                               lg_contracts, lg_expiry, lg_open_date)

            # Optional fields (collapsed)
            with st.expander("Optional fields", expanded=False):
                oc1, oc2, oc3 = st.columns(3)
                lg_spot  = oc1.number_input("Spot price", value=0.0, step=0.01, key="lg_spot")
                lg_vix   = oc2.number_input("VIX",        value=0.0, step=0.1,  key="lg_vix")
                lg_source = oc3.selectbox("Source", ["manual", "model", "import"], key="lg_src")
                lg_notes = st.text_input("Notes (optional)", key="lg_notes",
                                          placeholder="e.g. High IV rank, earnings play, managed at 50%")

            if st.button("Save Position", key="lg_save", type="primary"):
                if lg_net <= 0:
                    st.error("Enter the net credit or debit received.")
                elif not any(v > 0 for v in strikes.values()):
                    st.error("Enter at least one strike price.")
                else:
                    net_signed = lg_net if is_credit else -lg_net
                    r = _compute_risk(lg_spread, strikes, net_signed)
                    dte = (lg_expiry - lg_open_date).days
                    total_comm = 0.65 * lg_contracts * len([v for v in strikes.values() if v > 0])

                    # Store representative legs from strikes
                    leg_defs = _strikes_to_legs(lg_spread, strikes, lg_net, is_credit)

                    from alan_trader.db import portfolio_client as pc2
                    sec_id = pc2.get_security_id(engine, lg_symbol)
                    if sec_id is None:
                        st.error(f"{lg_symbol} not found in security master (mkt.Ticker). Sync price bars first.")
                        st.stop()
                    dte_note = f"exp {lg_expiry} DTE={dte}"
                    risk_note = (f"max_profit=${r['max_profit']*lg_contracts*100:,.2f} "
                                 f"max_loss=${abs(r['max_loss'])*lg_contracts*100:,.2f}" if r["max_profit"] else "")
                    full_notes = " | ".join(filter(None, [dte_note, risk_note, lg_notes or ""]))
                    pos_id = pc2.insert_position(
                        engine=engine, account_id=account_id,
                        security_id=sec_id,
                        position_type="option_spread",
                        quantity=float(lg_contracts),
                        open_date=lg_open_date,
                        avg_entry_price=net_signed,
                        commission=total_comm,
                        strategy_name=lg_spread,
                        source=lg_source,
                        tags=lg_spread,
                        notes=full_notes or None,
                    )
                    for leg in leg_defs:
                        pc2.insert_leg(
                            engine=engine, position_id=pos_id,
                            symbol=lg_symbol, action=leg["action"],
                            contracts=lg_contracts, fill_price=leg["fill_price"],
                            fill_date=lg_open_date, strike=leg["strike"],
                            expiration=lg_expiry,
                            contract_type=leg["contract_type"],
                            commission=0.65 * lg_contracts,
                            leg_order=leg["leg_order"],
                        )
                    label = SPREAD_LABELS.get(lg_spread, lg_spread)
                    st.success(f"Saved #{pos_id} — {lg_contracts}× {lg_symbol} {label} "
                               f"@ ${lg_net:.2f} {'cr' if is_credit else 'db'}")
                    st.rerun()

        # ── CSV Import ────────────────────────────────────────────────────────
        with log_tab_csv:
            st.markdown("### Import from broker")
            st.caption(
                "Export your transaction history from your broker and paste or upload it here. "
                "Supported: **Tastytrade** (History → Export CSV) · **IBKR** (Flex Query, Trades)"
            )
            broker = st.radio("Broker format", ["Tastytrade", "IBKR"], horizontal=True, key="csv_broker")
            uploaded = st.file_uploader("Upload CSV", type=["csv"], key="csv_upload")
            pasted   = st.text_area("...or paste CSV text here", height=120, key="csv_paste")

            raw = None
            if uploaded:
                raw = uploaded.read().decode("utf-8", errors="ignore")
            elif pasted.strip():
                raw = pasted.strip()

            if raw:
                parsed = _parse_tastytrade_csv(raw) if broker == "Tastytrade" else _parse_ibkr_csv(raw)
                if parsed.empty:
                    st.warning("Could not parse any option trades from the uploaded file. "
                               "Check the format or broker selection.")
                else:
                    st.success(f"Parsed {len(parsed)} rows. Review below before importing.")
                    st.dataframe(parsed.head(50), width="stretch", hide_index=True)
                    st.info("Full auto-import coming soon. For now, use Quick Entry above to log each position.")

    # ══════════════════════════════════════════════════════════════════════════
    # CLOSE POSITION
    # ══════════════════════════════════════════════════════════════════════════
    with t_close:
        open_df = pc.get_open_positions(engine, account_id)
        if open_df.empty:
            st.info("No open positions to close.")
        else:
            st.markdown("### Close a position")

            # Build readable labels
            def _pos_label(row):
                ptype = row.get("PositionType", "position")
                qty   = row.get("Quantity", "?")
                tags  = row.get("Tags", "") or ""
                label = tags if tags else ptype
                return f"{row['Symbol']} {label}  {qty}qty  |  opened {row['OpenDate']}"

            pid_map = {_pos_label(row): row["PositionId"] for _, row in open_df.iterrows()}
            selected_label = st.selectbox("Select position", list(pid_map.keys()), key="cl_pos")
            close_pid = pid_map[selected_label]
            pos_row   = open_df[open_df["PositionId"] == close_pid].iloc[0]

            entry_value = float(pos_row.get("AvgEntryPrice", 0) or 0)
            contracts   = float(pos_row.get("Quantity", 1) or 1)
            tags        = (pos_row.get("Tags") or "")
            is_credit   = any(t in CREDIT_SPREADS for t in tags.split(","))

            st.markdown("")
            mode = st.radio(
                "How did it close?",
                ["Closed for value", "Expired worthless", "Assigned / exercised", "Rolled"],
                horizontal=True, key="cl_mode",
            )

            cl1, cl2 = st.columns(2)
            close_date = cl1.date_input("Close date", value=datetime.date.today(), key="cl_date")

            realized_pnl = 0.0
            exit_val     = 0.0

            if mode == "Expired worthless":
                # Full credit captured (credit spread) or full debit lost (debit spread)
                if is_credit:
                    realized_pnl = abs(entry_value) * contracts * 100
                    exit_val     = 0.0
                    st.success(f"Full credit captured: **${realized_pnl:,.2f}**")
                else:
                    realized_pnl = -(abs(entry_value) * contracts * 100)
                    exit_val     = 0.0
                    st.error(f"Full debit lost: **${realized_pnl:,.2f}**")

            elif mode == "Closed for value":
                net_help_c = ("Cost to close — what you paid to BUY back the spread (e.g. $0.25)."
                              if is_credit else
                              "What you sold the spread for (e.g. $2.50).")
                exit_val = cl2.number_input(
                    "Close price ($/share)", value=0.0, min_value=0.0, step=0.01,
                    key="cl_exit", help=net_help_c,
                )
                if is_credit:
                    # Collected entry, paid exit to close
                    realized_pnl = (abs(entry_value) - exit_val) * contracts * 100
                else:
                    # Paid entry, received exit on close
                    realized_pnl = (exit_val - abs(entry_value)) * contracts * 100

                color = "#26a69a" if realized_pnl >= 0 else "#ef5350"
                st.markdown(
                    f"<div style='color:{color}; font-size:1.1rem; font-weight:600'>"
                    f"Realized P&L: ${realized_pnl:+,.2f}</div>",
                    unsafe_allow_html=True,
                )

            elif mode in ("Assigned / exercised", "Rolled"):
                exit_val     = cl2.number_input("Exit value ($/share)", value=0.0, step=0.01, key="cl_exit_r")
                realized_pnl = cl1.number_input("Realized P&L ($)", value=0.0, step=1.0, key="cl_pnl_r")

            status_map = {
                "Closed for value": "closed",
                "Expired worthless": "expired",
                "Assigned / exercised": "assigned",
                "Rolled": "rolled",
            }

            if st.button("Confirm Close", type="primary", key="cl_confirm"):
                pc.close_position(
                    engine, int(close_pid), close_date,
                    exit_val, realized_pnl, status_map[mode],
                )
                st.success(f"Position closed — P&L: ${realized_pnl:+,.2f}")
                st.rerun()

    # ══════════════════════════════════════════════════════════════════════════
    # HISTORY
    # ══════════════════════════════════════════════════════════════════════════
    with t_history:
        hf1, hf2, hf3, hf4, hf5 = st.columns(5)
        h_sym  = hf1.selectbox("Symbol",   ["All"] + SYMBOLS,      key="h_sym")
        _pos_types = ["equity", "etf_rotation", "option_spread", "cash"]
        h_st   = hf2.selectbox("Type", ["All"] + _pos_types, key="h_st")
        h_from = hf3.date_input("From", value=datetime.date(2020, 1, 1), key="h_from")
        h_to   = hf4.date_input("To",   value=datetime.date.today(),     key="h_to")
        h_out  = hf5.selectbox("Outcome", ["All", "Win", "Loss", "Breakeven"], key="h_out")

        closed_df = pc.get_closed_positions(
            engine, account_id=account_id,
            symbol=None if h_sym == "All" else h_sym,
            position_type=None if h_st == "All" else h_st,
            from_date=h_from, to_date=h_to,
        )
        if h_out != "All" and not closed_df.empty:
            closed_df = closed_df[closed_df["Outcome"] == h_out]

        if closed_df.empty:
            st.info("No closed positions match these filters.")
        else:
            n_trades  = len(closed_df)
            n_wins    = (closed_df["RealizedPnL"] > 0).sum()
            total_pnl = closed_df["RealizedPnL"].sum()
            avg_pnl   = closed_df["RealizedPnL"].mean()
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Trades",    str(n_trades))
            m2.metric("Win Rate",  f"{n_wins / n_trades * 100:.1f}%")
            m3.metric("Total P&L", f"${total_pnl:,.2f}")
            m4.metric("Avg P&L",   f"${avg_pnl:,.2f}")

            avail_c = [c for c in [
                "Symbol","PositionType","StrategyName","Quantity","OpenDate","CloseDate",
                "HoldDays","EntryDollars","RealizedPnL","Outcome","Regime","Notes"
            ] if c in closed_df.columns]
            disp = closed_df[avail_c].copy()
            st.dataframe(disp, width="stretch", hide_index=True, column_config={
                "RealizedPnL": cc.NumberColumn("P&L",     format="$%.2f"),
                "EntryDollars":cc.NumberColumn("Entry $", format="$%.2f"),
                "Quantity":    cc.NumberColumn("Qty"),
                "HoldDays":    cc.NumberColumn("Hold Days"),
            })

    # ══════════════════════════════════════════════════════════════════════════
    # PERFORMANCE
    # ══════════════════════════════════════════════════════════════════════════
    with t_perf:
        monthly_df = pc.get_monthly_pnl(engine)
        perf_df    = pc.get_strategy_performance(engine)
        bal_hist   = pc.get_balance_history(engine, account_id, days=365)
        closed_all = pc.get_closed_positions(engine, account_id=account_id)

        if monthly_df.empty and perf_df.empty and closed_all.empty:
            st.info("No closed trades yet.")
        else:
            # Strategy filter
            all_strats = []
            if not closed_all.empty and "StrategyName" in closed_all.columns:
                all_strats = sorted(closed_all["StrategyName"].dropna().unique().tolist())
            if all_strats:
                pf_strats = st.multiselect(
                    "Filter by strategy", options=all_strats,
                    default=all_strats, key="perf_strat_filter",
                )
            else:
                pf_strats = all_strats

            filtered_closed = closed_all.copy()
            if pf_strats and "StrategyName" in filtered_closed.columns:
                filtered_closed = filtered_closed[filtered_closed["StrategyName"].isin(pf_strats)]

            # Cumulative PnL chart (primary)
            if not filtered_closed.empty:
                st.plotly_chart(_chart_cumulative_pnl(filtered_closed, pf_strats or None), width="stretch")

            if not bal_hist.empty:
                st.plotly_chart(_chart_equity_curve(bal_hist), width="stretch")

            ch1, ch2 = st.columns(2)
            if not monthly_df.empty:
                ch1.plotly_chart(_chart_monthly_pnl(monthly_df), width="stretch")
            if not perf_df.empty:
                ch2.plotly_chart(_chart_strategy_bars(perf_df), width="stretch")
            if not filtered_closed.empty:
                st.plotly_chart(_chart_pnl_histogram(filtered_closed), width="stretch")
            if not perf_df.empty:
                st.markdown("#### Strategy breakdown")
                st.dataframe(perf_df, width="stretch", hide_index=True, column_config={
                    "WinRate":     cc.NumberColumn("Win %",    format="%.1f%%"),
                    "TotalPnL":    cc.NumberColumn("Total P&L",format="$%.2f"),
                    "AvgPnL":      cc.NumberColumn("Avg P&L",  format="$%.2f"),
                    "BestTrade":   cc.NumberColumn("Best",     format="$%.2f"),
                    "WorstTrade":  cc.NumberColumn("Worst",    format="$%.2f"),
                    "AvgHoldDays": cc.NumberColumn("Avg Hold", format="%.1f d"),
                })

        with st.expander("Update account balance"):
            ub1, ub2, ub3 = st.columns(3)
            bal_date     = ub1.date_input("Date", value=datetime.date.today(), key="bal_date")
            bal_cash     = ub2.number_input("Cash balance ($)", value=0.0, step=100.0, key="bal_cash")
            bal_port_val = ub3.number_input("Portfolio value ($)", value=0.0, step=100.0, key="bal_pv")
            ub4, ub5 = st.columns(2)
            bal_day_pnl = ub4.number_input("Day P&L ($)", value=0.0, step=1.0, key="bal_dpnl")
            bal_ytd     = ub5.number_input("Realized YTD ($)", value=0.0, step=1.0, key="bal_ytd")
            if st.button("Save balance snapshot", key="bal_save"):
                pc.upsert_balance(engine, account_id, bal_date, bal_cash, bal_port_val,
                                  day_pnl=bal_day_pnl, realized_ytd=bal_ytd)
                st.success("Balance saved.")
                st.rerun()

    # ══════════════════════════════════════════════════════════════════════════
    # MODEL ACCURACY
    # ══════════════════════════════════════════════════════════════════════════
    with t_model:
        st.markdown("### Model signal accountability")
        acc_df = pc.get_model_accuracy(engine)
        if acc_df.empty:
            st.info("No model signals logged yet.")
        else:
            taken = acc_df[acc_df["SignalsTaken"] > 0]
            if not taken.empty:
                overall_win = (taken["WinsWhenTaken"].sum() / taken["SignalsTaken"].sum() * 100
                               if taken["SignalsTaken"].sum() > 0 else 0)
                a1, a2, a3 = st.columns(3)
                a1.metric("Win rate (when taken)", f"{overall_win:.1f}%")
                a2.metric("Total P&L (when taken)", f"${taken['TotalPnLWhenTaken'].sum():,.2f}")
                a3.metric("Signals taken", str(int(taken["SignalsTaken"].sum())))
            st.dataframe(acc_df, width="stretch", hide_index=True, column_config={
                "WinRateWhenTaken":  cc.NumberColumn("Win % (taken)", format="%.1f%%"),
                "AvgConfidencePct":  cc.NumberColumn("Avg Confidence", format="%.1f%%"),
                "TotalPnLWhenTaken": cc.NumberColumn("Total P&L",     format="$%.2f"),
                "AvgPnLWhenTaken":   cc.NumberColumn("Avg P&L",       format="$%.2f"),
            })


# ─────────────────────────────────────────────────────────────────────────────
# Helper: convert strike dict → Leg rows for DB
# ─────────────────────────────────────────────────────────────────────────────

def _strikes_to_legs(spread_type: str, strikes: dict, net: float, is_credit: bool) -> list[dict]:
    """Reconstruct approximate per-leg fill rows from strikes + net credit/debit."""
    legs = []
    idx  = 1

    def _leg(action, ctype, strike, fill):
        nonlocal idx
        l = {"action": action, "contract_type": ctype,
             "strike": strike, "fill_price": fill, "leg_order": idx}
        idx += 1
        return l

    if spread_type in ("bull_put", "bear_call"):
        short = strikes.get("short", 0.0)
        long  = strikes.get("long",  0.0)
        ctype = "P" if spread_type == "bull_put" else "C"
        # Approximate: net split evenly; exact fills not known from net alone
        legs.append(_leg("STO", ctype, short, net))
        legs.append(_leg("BTO", ctype, long,  0.0))

    elif spread_type in ("bull_call", "bear_put"):
        long  = strikes.get("long",  0.0)
        short = strikes.get("short", 0.0)
        ctype = "C" if spread_type == "bull_call" else "P"
        legs.append(_leg("BTO", ctype, long,  net))
        legs.append(_leg("STO", ctype, short, 0.0))

    elif spread_type == "iron_condor":
        legs.append(_leg("STO", "P", strikes.get("put_short",  0.0), net / 2))
        legs.append(_leg("BTO", "P", strikes.get("put_long",   0.0), 0.0))
        legs.append(_leg("STO", "C", strikes.get("call_short", 0.0), net / 2))
        legs.append(_leg("BTO", "C", strikes.get("call_long",  0.0), 0.0))

    elif spread_type == "long_straddle":
        strike = strikes.get("strike", 0.0)
        legs.append(_leg("BTO", "C", strike, net / 2))
        legs.append(_leg("BTO", "P", strike, net / 2))

    elif spread_type == "short_strangle":
        legs.append(_leg("STO", "P", strikes.get("put_strike",  0.0), net / 2))
        legs.append(_leg("STO", "C", strikes.get("call_strike", 0.0), net / 2))

    elif spread_type == "call_butterfly":
        legs.append(_leg("BTO", "C", strikes.get("low",  0.0), net))
        legs.append(_leg("STO", "C", strikes.get("mid",  0.0), 0.0))
        legs.append(_leg("STO", "C", strikes.get("mid",  0.0), 0.0))
        legs.append(_leg("BTO", "C", strikes.get("high", 0.0), 0.0))

    return legs
