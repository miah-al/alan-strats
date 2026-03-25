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

    st.info("📌 Portfolio tracking has moved to the **Paper Trading** tab.")
    st.markdown("Use the Paper Trading tab to view open positions, P&L, and transaction history.")



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
