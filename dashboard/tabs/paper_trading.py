from __future__ import annotations

import datetime
import math
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.column_config as cc

_INITIAL_CASH = 100_000.0
_COMMISSION   = 1.0   # per trade

# Strategies eligible for ETF paper trading (signal returns spy_weight / tlt_weight)
_ELIGIBLE_STRATEGIES: dict[str, str] = {
    "rates_spy_rotation":         "TLT / SPY Rotation",
    "rates_spy_rotation_options": "TLT / SPY Rotation (Options)",
    "gex_positioning":            "Dealer Gamma Exposure",
}


# ─────────────────────────────────────────────────────────────────────────────
# DB helpers — new portfolio schema
# ─────────────────────────────────────────────────────────────────────────────

def _get_engine():
    from alan_trader.db.client import get_engine
    return get_engine()


def _get_account_info(engine, account_id: int = 1) -> dict:
    from sqlalchemy import text
    try:
        with engine.connect() as conn:
            row = conn.execute(text("""
                SELECT AccountId, AccountName, AccountType, Currency, Status
                FROM portfolio.Account
                WHERE AccountId = :aid
            """), {"aid": account_id}).fetchone()
        if row:
            return {
                "AccountId":   row[0],
                "AccountName": row[1],
                "AccountType": row[2],
                "Currency":    row[3],
                "Status":      row[4],
            }
    except Exception:
        pass
    return {"AccountId": account_id, "AccountName": "Default Trading",
            "AccountType": "Paper", "Currency": "USD", "Status": "Active"}


def _load_transactions(engine, account_id: int = 1) -> pd.DataFrame:
    """
    Load all transactions for the account, joining Security for symbol details.
    Returns a DataFrame with columns:
      TransactionId, BusinessDate, TradeGroupId, StrategyName, SecurityId,
      Symbol, Underlying, SecurityType, OptionType, Strike, Expiration, Multiplier,
      Direction, Quantity, TransactionPrice, Commission, LegType, Source, Notes
    """
    from sqlalchemy import text
    try:
        with engine.connect() as conn:
            df = pd.read_sql(text("""
                SELECT
                    t.TransactionId,
                    t.BusinessDate,
                    t.TradeGroupId,
                    t.StrategyName,
                    t.SecurityId,
                    s.Symbol,
                    s.Underlying,
                    s.SecurityType,
                    s.OptionType,
                    s.Strike,
                    s.Expiration,
                    s.Multiplier,
                    t.Direction,
                    t.Quantity,
                    t.TransactionPrice,
                    t.Commission,
                    t.LegType,
                    t.Source,
                    t.Notes,
                    t.CreatedAt
                FROM portfolio.[Transaction] t
                JOIN portfolio.Security s ON s.SecurityId = t.SecurityId
                WHERE t.AccountId = :aid
                ORDER BY t.BusinessDate DESC, t.CreatedAt DESC
            """), conn, params={"aid": account_id})
        return df
    except Exception:
        return pd.DataFrame()


def _get_open_trade_groups(txns_df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """
    Identify open trade groups. A TradeGroupId is open if there is no closing
    transaction. Closing transactions are identified by Notes containing 'CLOSE'
    (case-insensitive) or Source = 'Close'.
    Returns a dict mapping TradeGroupId -> subset DataFrame of that group's rows.
    Cash entries (SecurityType='cash') are excluded.
    """
    if txns_df.empty:
        return {}

    # Exclude cash/deposit entries
    sec_type = txns_df.get("SecurityType", pd.Series(dtype=str)).fillna("").str.lower()
    leg_type  = txns_df.get("LegType",      pd.Series(dtype=str)).fillna("").str.lower()
    is_cash   = sec_type.isin(["cash"]) | leg_type.isin(["cashin", "cashout"])
    txns_df   = txns_df[~is_cash].copy()

    notes_col = txns_df.get("Notes", pd.Series(dtype=str)).fillna("").str.upper()
    source_col = txns_df.get("Source", pd.Series(dtype=str)).fillna("").str.upper()
    is_closing = notes_col.str.contains("CLOSE") | (source_col == "CLOSE")

    closed_groups: set = set(
        txns_df.loc[is_closing, "TradeGroupId"].dropna().unique()
    )

    open_groups: dict[str, pd.DataFrame] = {}
    for tgid, group in txns_df.groupby("TradeGroupId"):
        if tgid not in closed_groups:
            open_groups[str(tgid)] = group

    return open_groups


def _get_closed_trade_groups(txns_df: pd.DataFrame) -> list[dict]:
    """
    Returns summary rows for closed trade groups.
    A group is closed if it has at least one closing transaction (Notes contains CLOSE).
    Cash entries (SecurityType='cash') are excluded.
    """
    if txns_df.empty:
        return []

    # Exclude cash/deposit entries
    sec_type  = txns_df.get("SecurityType", pd.Series(dtype=str)).fillna("").str.lower()
    leg_type  = txns_df.get("LegType",      pd.Series(dtype=str)).fillna("").str.lower()
    is_cash   = sec_type.isin(["cash"]) | leg_type.isin(["cashin", "cashout"])
    txns_df   = txns_df[~is_cash].copy()

    notes_col = txns_df.get("Notes", pd.Series(dtype=str)).fillna("").str.upper()
    source_col = txns_df.get("Source", pd.Series(dtype=str)).fillna("").str.upper()
    is_closing = notes_col.str.contains("CLOSE") | (source_col == "CLOSE")

    closed_group_ids: set = set(
        txns_df.loc[is_closing, "TradeGroupId"].dropna().unique()
    )

    rows = []
    for tgid in closed_group_ids:
        group = txns_df[txns_df["TradeGroupId"] == tgid]
        opening = group[~(
            group.get("Notes", pd.Series(dtype=str)).fillna("").str.upper().str.contains("CLOSE") |
            (group.get("Source", pd.Series(dtype=str)).fillna("").str.upper() == "CLOSE")
        )]
        closing = group[
            group.get("Notes", pd.Series(dtype=str)).fillna("").str.upper().str.contains("CLOSE") |
            (group.get("Source", pd.Series(dtype=str)).fillna("").str.upper() == "CLOSE")
        ]

        underlying = (
            group["Underlying"].dropna().iloc[0]
            if "Underlying" in group.columns and not group["Underlying"].dropna().empty
            else group["Symbol"].iloc[0] if not group.empty else "?"
        )
        strategy = group["StrategyName"].iloc[0] if not group.empty else "?"
        open_date = opening["BusinessDate"].min() if not opening.empty else None
        close_date = closing["BusinessDate"].max() if not closing.empty else None

        # Net entry cost: sum of (Direction sign * Qty * Price * Multiplier) for opening legs
        def _signed_cost(sub: pd.DataFrame) -> float:
            total = 0.0
            for _, r in sub.iterrows():
                sign = -1.0 if str(r.get("Direction", "")).upper() == "BUY" else 1.0
                mult = float(r.get("Multiplier", 1) or 1)
                total += sign * float(r.get("Quantity", 0) or 0) * float(r.get("TransactionPrice", 0) or 0) * mult
            return total

        net_entry = _signed_cost(opening)
        net_exit  = _signed_cost(closing)
        pnl       = net_entry + net_exit  # entry is cost (negative if debit), exit is proceeds

        rows.append({
            "TradeGroupId": tgid,
            "Underlying":   underlying,
            "Strategy":     strategy,
            "Open Date":    open_date,
            "Close Date":   close_date,
            "Net Entry":    net_entry,
            "Net Exit":     net_exit,
            "P&L $":        pnl,
        })

    return rows


def _load_balance_history(engine, account_id: int = 1) -> pd.DataFrame:
    """Load NetLiquidation balance history."""
    from sqlalchemy import text
    try:
        with engine.connect() as conn:
            df = pd.read_sql(text("""
                SELECT BusinessDate, Amount
                FROM portfolio.Balance
                WHERE AccountId = :aid AND BalanceType = 'NetLiquidation'
                ORDER BY BusinessDate ASC
            """), conn, params={"aid": account_id})
        return df
    except Exception:
        return pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
# Polygon helpers
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_stock_price(api_key: str, symbol: str) -> float | None:
    try:
        from alan_trader.data.polygon_client import PolygonClient
        c = PolygonClient(api_key=api_key)
        snap = c.get_snapshot(symbol)
        return snap.get("day", {}).get("c") or snap.get("lastTrade", {}).get("p")
    except Exception:
        return None


def _fetch_stock_prices_bulk(api_key: str, symbols: list[str]) -> dict[str, float | None]:
    """Fetch prices for multiple symbols, returning {symbol: price}."""
    prices: dict[str, float | None] = {}
    for sym in symbols:
        prices[sym] = _fetch_stock_price(api_key, sym)
    return prices


def _fetch_option_prices(api_key: str, legs_df: pd.DataFrame) -> dict[str, dict]:
    """
    Fetch current mid prices and IV for option legs using exact strike/expiry/type match.
    Returns {Symbol: {"price": float|None, "iv": float|None}}.
    """
    if not api_key:
        return {}
    from alan_trader.data.polygon_client import PolygonClient
    result: dict[str, dict] = {}
    if "SecurityType" not in legs_df.columns:
        return result
    opt_legs = legs_df[legs_df["SecurityType"] == "option"].dropna(subset=["Strike", "Expiration"])
    if opt_legs.empty:
        return result
    client = PolygonClient(api_key=api_key)
    for underlying, grp in opt_legs.groupby("Underlying"):
        try:
            exp_dates = grp["Expiration"].astype(str).unique()
            strikes   = grp["Strike"].unique()
            chain = client.get_options_chain(
                underlying,
                expiration_date_gte=str(min(exp_dates)),
                expiration_date_lte=str(max(exp_dates)),
                strike_price_gte=float(min(strikes)) - 0.5,
                strike_price_lte=float(max(strikes)) + 0.5,
            )
            if chain is None or chain.empty:
                continue
            for _, row in grp.iterrows():
                sym    = row["Symbol"]
                strike = float(row["Strike"])
                exp    = str(row["Expiration"])
                otype  = str(row.get("OptionType") or "").lower()
                match  = chain[
                    (chain["strike"] == strike) &
                    (chain["expiration"].astype(str) == exp) &
                    (chain["type"] == otype)
                ]
                if match.empty:
                    result[sym] = {"price": None, "iv": None}
                    continue
                r   = match.iloc[0]
                bid = r.get("bid")
                ask = r.get("ask")
                mid = round((float(bid) + float(ask)) / 2, 4) \
                    if (bid is not None and ask is not None and bid == bid and ask == ask) \
                    else None
                iv_raw = r.get("iv")
                iv  = round(float(iv_raw) * 100, 2) if iv_raw is not None and iv_raw == iv_raw else None
                bid_val = round(float(bid), 4) if (bid is not None and bid == bid) else None
                ask_val = round(float(ask), 4) if (ask is not None and ask == ask) else None
                result[sym] = {"price": mid, "iv": iv, "bid": bid_val, "ask": ask_val}
        except Exception:
            pass
    return result


def _compute_position_alerts(
    grp: pd.DataFrame,
    strategy: str,
    total_upnl: float | None,
    net_entry: float,
) -> list[dict]:
    """
    Returns list of {"level": "error"|"warning"|"success", "msg": str}.
    Checks: DTE (all options), P&L vs strategy-specific thresholds.

    Strategy types detected from strategy name:
      credit  — Iron Condor, Bull Put Spread, Bear Call Spread
      debit   — Bear Put Spread, Bull Call Spread, Long Put, Long Call
      equity  — long stock / ETF
    """
    alerts: list[dict] = []
    today  = datetime.date.today()
    sl     = strategy.lower()

    # ── DTE check (options only) ─────────────────────────────────────────────
    min_dte: int | None = None
    for _, r in grp.iterrows():
        exp = r.get("Expiration")
        if exp:
            try:
                exp_date = pd.to_datetime(exp).date()
                dte = (exp_date - today).days
                if min_dte is None or dte < min_dte:
                    min_dte = dte
            except Exception:
                pass

    if min_dte is not None:
        if min_dte <= 0:
            alerts.append({"level": "error",
                           "msg": f"EXPIRED ({min_dte} DTE) — close immediately to avoid assignment."})
        elif min_dte <= 7:
            alerts.append({"level": "error",
                           "msg": f"{min_dte} DTE — critical, close immediately (assignment risk)."})
        elif min_dte <= 21:
            alerts.append({"level": "warning",
                           "msg": f"{min_dte} DTE — theta decay accelerating, consider closing."})

    # ── P&L check ────────────────────────────────────────────────────────────
    if total_upnl is not None and net_entry != 0:
        # Detect from actual position data — works for any strategy name
        has_options = any(
            str(r.get("SecurityType", "")).lower() == "option"
            for _, r in grp.iterrows()
        )
        if has_options:
            is_credit = net_entry > 0   # collected premium
            is_debit  = net_entry <= 0  # paid premium
            is_equity = False
        else:
            is_credit   = False
            is_debit    = False
            is_rotation = any(x in sl for x in ("rotation", "tlt / spy", "spy rotation"))
            is_equity   = not is_rotation

        if is_credit:
            # net_entry > 0 = premium collected
            credit = abs(net_entry)
            if total_upnl >= 0.50 * credit:
                alerts.append({"level": "success",
                               "msg": f"Take profit — P&L ${total_upnl:+.2f} ≥ 50% of credit (${credit:.2f}). Standard exit for credit spreads."})
            elif total_upnl <= -0.75 * credit:
                alerts.append({"level": "error",
                               "msg": f"Stop loss — P&L ${total_upnl:+.2f}, 75%+ of credit lost. Consider closing."})
            elif total_upnl <= -0.50 * credit:
                alerts.append({"level": "warning",
                               "msg": f"P&L ${total_upnl:+.2f} — 50% of credit lost. Monitor closely."})

        elif is_debit:
            # net_entry < 0 = premium paid
            cost = abs(net_entry)
            if total_upnl >= cost:
                alerts.append({"level": "success",
                               "msg": f"100%+ gain — P&L ${total_upnl:+.2f} vs ${cost:.2f} paid. Consider taking profits."})
            elif total_upnl >= 0.50 * cost:
                alerts.append({"level": "success",
                               "msg": f"Take profit — P&L ${total_upnl:+.2f} ≥ 50% of premium (${cost:.2f})."})
            elif total_upnl <= -0.50 * cost:
                alerts.append({"level": "error",
                               "msg": f"Stop loss — P&L ${total_upnl:+.2f}, 50% of premium lost (${cost:.2f}). Thesis may be broken."})

        elif is_rotation:
            # Regime-driven hold — wider thresholds, trend following
            cost = abs(net_entry)
            pct  = total_upnl / cost if cost > 0 else 0.0
            if pct >= 0.30:
                alerts.append({"level": "success",
                               "msg": f"+{pct:.1%} — consider trimming (≥30% gain on rotation position)."})
            elif pct <= -0.15:
                alerts.append({"level": "error",
                               "msg": f"{pct:.1%} — stop loss (≥15% loss). Regime signal may have reversed."})
            elif pct <= -0.08:
                alerts.append({"level": "warning",
                               "msg": f"{pct:.1%} — drawdown building. Check if regime has changed."})

        else:  # equity
            cost = abs(net_entry)
            pct  = total_upnl / cost if cost > 0 else 0.0
            if pct >= 0.20:
                alerts.append({"level": "success",
                               "msg": f"+{pct:.1%} — consider taking partial profits (≥20% gain)."})
            elif pct <= -0.08:
                alerts.append({"level": "error",
                               "msg": f"{pct:.1%} — stop loss territory (≥8% loss). Consider closing."})

    return alerts


def _alert_icon(alerts: list[dict]) -> str:
    levels = {a["level"] for a in alerts}
    if "error"   in levels: return "🔴 "
    if "warning" in levels: return "🟡 "
    if "success" in levels: return "✅ "
    return ""


def _render_equity_position(
    grp: pd.DataFrame,
    spot: float | None,
    open_date,
    net_entry: float,
    underlying: str,
    chart_key: str = "eq_pos_chart",
    live_prices: dict | None = None,
) -> None:
    """
    P&L chart for equity long positions.
    Single ticker: linear P&L curve.
    Multi-ticker (e.g. SPY+TLT rotation): per-leg P&L bar chart.
    """
    import datetime as _dt

    buy_rows = grp[grp["Direction"].str.upper() == "BUY"] if "Direction" in grp.columns else grp
    if buy_rows.empty:
        return

    # Days held
    try:
        days_held = (_dt.date.today() - pd.to_datetime(open_date).date()).days
    except Exception:
        days_held = None
    days_str = f" · {days_held}d held" if days_held is not None else ""

    unique_symbols = buy_rows["Symbol"].dropna().unique() if "Symbol" in buy_rows.columns else [underlying]

    if len(unique_symbols) > 1:
        # ── Multi-ticker: per-leg P&L bar chart ──────────────────────────────────
        leg_data = []
        for _, r in buy_rows.iterrows():
            sym      = str(r.get("Symbol", underlying))
            entry_px = float(r.get("TransactionPrice") or 0)
            qty      = float(r.get("Quantity") or 1)
            cur_px   = (live_prices or {}).get(sym)
            pnl      = (cur_px - entry_px) * qty if cur_px else None
            leg_data.append({"sym": sym, "entry": entry_px, "qty": qty, "cur": cur_px, "pnl": pnl})

        # Metrics row
        _mcols = st.columns(len(leg_data))
        for i, ld in enumerate(leg_data):
            _mcols[i].metric(
                f"{ld['sym']}  ({ld['qty']:.0f} sh @ ${ld['entry']:.2f})",
                f"${ld['cur']:.2f}" if ld["cur"] else "—",
                delta=round(ld["pnl"], 2) if ld["pnl"] is not None else None,
            )

        # Bar chart — always show all legs, use 0 for missing prices
        bar_data = [
            {"sym": ld["sym"], "pnl": ld["pnl"] if ld["pnl"] is not None else 0.0,
             "has_price": ld["pnl"] is not None}
            for ld in leg_data
        ]
        fig = go.Figure(go.Bar(
            x=[ld["sym"] for ld in bar_data],
            y=[ld["pnl"] for ld in bar_data],
            marker_color=["#26a69a" if ld["pnl"] >= 0 else "#ef5350" for ld in bar_data],
            marker_opacity=[1.0 if ld["has_price"] else 0.3 for ld in bar_data],
            text=[f"${ld['pnl']:+,.2f}" if ld["has_price"] else "no price" for ld in bar_data],
            textposition="outside",
            hovertemplate="%{x}<br>P&L: %{y:$,.2f}<extra></extra>",
            width=0.4,
        ))
        fig.add_hline(y=0, line=dict(color="#374151", width=1))
        fig.update_layout(
            template="plotly_dark",
            title=f"Position P&L per Leg{days_str}",
            height=260,
            margin=dict(t=40, b=20, l=0, r=0),
            yaxis=dict(tickformat="$,.0f"),
            xaxis=dict(type="category"),
        )
        st.plotly_chart(fig, width="stretch", key=chart_key)
        return

    # ── Single ticker: linear P&L curve ──────────────────────────────────────────
    entry_px = float(buy_rows["TransactionPrice"].iloc[0] or 0)
    qty      = float(buy_rows["Quantity"].iloc[0] or 1)

    if entry_px <= 0:
        return

    ref    = spot if spot else entry_px
    prices = np.linspace(ref * 0.80, ref * 1.20, 300)
    pnl    = (prices - entry_px) * qty

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=prices, y=pnl,
        mode="lines",
        line=dict(color="#5c6bc0", width=2),
        name="Unrealized P&L",
        fill="tozeroy",
        fillcolor="rgba(92,107,192,0.08)",
        hovertemplate="Price: $%{x:.2f}<br>P&L: $%{y:+,.2f}<extra></extra>",
    ))
    fig.add_hline(y=0, line=dict(color="#374151", width=1))
    fig.add_vline(
        x=entry_px,
        line=dict(color="#f59e0b", width=1.5, dash="dash"),
        annotation_text=f"Entry ${entry_px:.2f}",
        annotation_position="top left",
        annotation_font_color="#f59e0b",
        annotation_font_size=11,
    )
    if spot:
        cur_pnl = (spot - entry_px) * qty
        fig.add_vline(
            x=spot,
            line=dict(color="#26a69a" if cur_pnl >= 0 else "#ef5350", width=2),
            annotation_text=f"Now ${spot:.2f}  P&L ${cur_pnl:+,.2f}",
            annotation_position="top right",
            annotation_font_color="#26a69a" if cur_pnl >= 0 else "#ef5350",
            annotation_font_size=11,
        )
    fig.update_layout(
        template="plotly_dark",
        title=f"{underlying} Equity P&L — {qty:.0f} share(s) @ ${entry_px:.2f}{days_str}",
        height=300,
        margin=dict(t=45, b=20, l=0, r=0),
        xaxis_title="Stock Price ($)",
        yaxis_title="Unrealized P&L ($)",
        xaxis=dict(tickformat="$,.2f"),
        yaxis=dict(tickformat="$,.0f"),
        showlegend=False,
    )
    st.plotly_chart(fig, width="stretch", key=chart_key)
    st.caption(
        f"Breakeven: **${entry_px:.2f}** · "
        f"+10% target: **${entry_px*1.10:.2f}** (+${entry_px*0.10*qty:,.0f}) · "
        f"-10% stop: **${entry_px*0.90:.2f}** (-${entry_px*0.10*qty:,.0f})"
    )


def _render_screener_position(
    grp: pd.DataFrame,
    spot: float | None,
    open_date,
    net_entry: float,
    strategy: str,
    live_opt_prices: dict,
    chart_key_prefix: str = "scr_pos",
) -> None:
    """
    Generic payoff chart + P&L metrics for screener-saved positions
    (VIX Spike Fade, Vol Arbitrage, IVR Credit Spread, etc.).
    """
    from datetime import date as _date
    import math as _math

    opt = grp[grp["SecurityType"].str.lower() == "option"].copy() if "SecurityType" in grp.columns else pd.DataFrame()
    if opt.empty:
        payoff_fig = _plot_payoff(grp, spot)
        if payoff_fig is not None:
            st.plotly_chart(payoff_fig, width="stretch", key=f"{chart_key_prefix}_payoff_eq")
        return

    opt["Strike"]           = pd.to_numeric(opt["Strike"],           errors="coerce")
    opt["TransactionPrice"] = pd.to_numeric(opt["TransactionPrice"], errors="coerce")
    opt["Quantity"]         = pd.to_numeric(opt["Quantity"],         errors="coerce").fillna(1)
    opt["Multiplier"]       = pd.to_numeric(opt["Multiplier"],       errors="coerce").fillna(100)

    # Net credit/debit at entry
    net_credit = 0.0
    for _, r in opt.iterrows():
        sign = -1.0 if str(r.get("Direction", "")).upper() == "BUY" else 1.0
        net_credit += sign * float(r.get("TransactionPrice") or 0)

    is_credit = net_credit >= 0
    label_type = "Net Credit" if is_credit else "Net Debit"

    # DTE remaining
    exp_dates     = opt["Expiration"].dropna()
    dte_remaining = None
    expiry_str    = None
    if not exp_dates.empty:
        try:
            expiry        = pd.to_datetime(exp_dates.iloc[0]).date()
            expiry_str    = str(expiry)
            dte_remaining = (expiry - _date.today()).days
        except Exception:
            pass

    # Days held
    try:
        days_held = (_date.today() - pd.to_datetime(open_date).date()).days
    except Exception:
        days_held = None

    # Current mark P&L from live option prices
    current_pnl: float | None = 0.0
    for _, r in opt.iterrows():
        sym = r.get("Symbol", "")
        mid = (live_opt_prices.get(sym) or {}).get("price")
        if mid is None:
            current_pnl = None
            break
        sign = 1.0 if str(r.get("Direction", "")).upper() == "BUY" else -1.0
        current_pnl = (current_pnl or 0.0) + sign * float(mid)
    if current_pnl is not None:
        current_pnl += net_credit  # entry credit already received

    # Profit target = 50% of credit (or 50% of debit for debit spreads)
    profit_target = abs(net_credit) * 0.50

    # Metrics row
    s1, s2, s3, s4 = st.columns(4)
    s1.metric(label_type,     f"${net_credit:.2f}")
    s2.metric("50% Target",   f"${profit_target:.2f}" if is_credit else f"${profit_target:.2f} debit recoup")
    s3.metric("DTE Remaining", str(dte_remaining) if dte_remaining is not None else "—")
    s4.metric("Days Held",    str(days_held) if days_held is not None else "—")

    if current_pnl is not None:
        pnl_color = "#10b981" if current_pnl >= 0 else "#ef4444"
        ref = abs(net_credit) if net_credit != 0 else 1
        pnl_pct = current_pnl / ref * 100
        st.markdown(
            f"<div style='padding:8px 12px;background:#111827;border-radius:6px;"
            f"border-left:3px solid {pnl_color};margin-bottom:8px'>"
            f"<span style='color:#6b7280;font-size:11px'>Current P&L (mark-to-market)</span><br>"
            f"<span style='color:{pnl_color};font-size:1.2rem;font-weight:700'>"
            f"${current_pnl:+.2f}  ({pnl_pct:+.1f}%)</span></div>",
            unsafe_allow_html=True,
        )

    # Exit signal hints
    if dte_remaining is not None and dte_remaining <= 14:
        st.warning(f"⚠️ {dte_remaining} DTE — consider closing to avoid gamma/pin risk at expiry.")
    elif current_pnl is not None and is_credit and current_pnl >= profit_target:
        st.success(f"✅ 50% profit target reached (${current_pnl:+.2f}). Consider closing.")

    # Payoff chart
    payoff_fig = _plot_payoff(grp, spot)
    if payoff_fig is not None:
        st.plotly_chart(payoff_fig, width="stretch", key=f"{chart_key_prefix}_payoff")
        st.caption(
            "Payoff at expiration · Coloured dotted lines = strike levels · "
            "White line = current spot · Green fill = profit zone · Red fill = loss zone"
        )
    else:
        if spot is not None:
            st.caption(f"Current spot: ${spot:.2f}")


def _render_ic_position(
    grp: pd.DataFrame,
    spot: float | None,
    open_date,
    net_entry: float,
    api_key: str,
    tgid,
) -> None:
    """Strategy-aware position detail for Iron Condor trades."""
    import math as _math
    from datetime import date as _date
    from scipy.stats import norm as _norm

    opt = grp[grp["SecurityType"].str.lower() == "option"].copy()
    if opt.empty:
        payoff_fig = _plot_payoff(grp, spot)
        if payoff_fig is not None:
            st.plotly_chart(payoff_fig, width="stretch", key=f"ic_payoff_eq_{tgid}")
        return
    # spot may be None if live price not fetched — chart still works, BS today-line skipped

    opt["Strike"]           = pd.to_numeric(opt["Strike"],           errors="coerce")
    opt["TransactionPrice"] = pd.to_numeric(opt["TransactionPrice"], errors="coerce")
    opt["Quantity"]         = pd.to_numeric(opt["Quantity"],         errors="coerce").fillna(1)
    opt["Multiplier"]       = pd.to_numeric(opt["Multiplier"],       errors="coerce").fillna(100)

    # ── Compute key IC parameters from legs ──────────────────────────────────
    net_credit = 0.0
    for _, r in opt.iterrows():
        sign = -1.0 if str(r.get("Direction", "")).upper() == "BUY" else 1.0
        net_credit += sign * float(r.get("TransactionPrice") or 0)

    short_calls = opt[(opt["OptionType"].str.lower() == "call") &
                      (opt["Direction"].str.upper() == "SELL")]
    short_puts  = opt[(opt["OptionType"].str.lower() == "put") &
                      (opt["Direction"].str.upper() == "SELL")]
    long_calls  = opt[(opt["OptionType"].str.lower() == "call") &
                      (opt["Direction"].str.upper() == "BUY")]
    long_puts   = opt[(opt["OptionType"].str.lower() == "put") &
                      (opt["Direction"].str.upper() == "BUY")]

    short_call_k  = float(short_calls["Strike"].iloc[0]) if not short_calls.empty else None
    short_put_k   = float(short_puts["Strike"].iloc[0])  if not short_puts.empty  else None
    long_call_k   = float(long_calls["Strike"].iloc[0])  if not long_calls.empty  else None
    long_put_k    = float(long_puts["Strike"].iloc[0])   if not long_puts.empty   else None

    # Strategy exit rules
    profit_target = net_credit * 0.50   # 50% of max credit
    stop_loss     = -net_credit * 2.0   # 2× credit as loss

    # Breakevens
    be_upper = (short_call_k + net_credit) if short_call_k else None
    be_lower = (short_put_k  - net_credit) if short_put_k  else None

    # DTE remaining
    exp_dates = opt["Expiration"].dropna()
    dte_remaining = None
    expiry_str    = None
    if not exp_dates.empty:
        try:
            expiry = pd.to_datetime(exp_dates.iloc[0]).date()
            expiry_str = str(expiry)
            dte_remaining = (expiry - _date.today()).days
        except Exception:
            pass

    # Days held
    try:
        days_held = (_date.today() - pd.to_datetime(open_date).date()).days
    except Exception:
        days_held = None

    # ── Current P&L estimate (mark-to-market via live_opt_prices in session) ─
    current_pnl = None
    # Try both session key names (pt_live_option_prices set by paper trading tab)
    live_opts   = (
        st.session_state.get("pt_live_option_prices") or
        st.session_state.get("_live_opt_prices_cache") or
        {}
    )
    if live_opts:
        total_close_cost = 0.0
        all_priced = True
        for _, r in opt.iterrows():
            sym = r.get("Symbol", "")
            mid = (live_opts.get(sym) or {}).get("price")
            if mid is None:
                all_priced = False
                break
            sign = 1.0 if str(r.get("Direction", "")).upper() == "BUY" else -1.0
            total_close_cost += sign * float(mid)
        if all_priced:
            current_pnl = net_credit + total_close_cost

    # ── Status panel ─────────────────────────────────────────────────────────
    s1, s2, s3, s4, s5 = st.columns(5)
    s1.metric("Net Credit",       f"${net_credit:.2f}")
    s2.metric("50% Target",       f"${profit_target:.2f}")
    s3.metric("2× Stop",          f"${stop_loss:.2f}")
    s4.metric("DTE Remaining",    str(dte_remaining) if dte_remaining is not None else "—")
    s5.metric("Days Held",        str(days_held) if days_held is not None else "—")

    if current_pnl is not None:
        pnl_pct = current_pnl / net_credit * 100 if net_credit else 0
        pnl_color = "#10b981" if current_pnl >= 0 else "#ef4444"
        st.markdown(
            f"<div style='padding:8px 12px;background:#111827;border-radius:6px;"
            f"border-left:3px solid {pnl_color};margin-bottom:8px'>"
            f"<span style='color:#6b7280;font-size:11px'>Current P&L (mark)</span><br>"
            f"<span style='color:{pnl_color};font-size:1.2rem;font-weight:700'>"
            f"${current_pnl:+.2f}  ({pnl_pct:+.1f}% of max credit)</span></div>",
            unsafe_allow_html=True,
        )

    # ── Exit recommendation based on strategy rules ───────────────────────────
    exit_reason = None
    if dte_remaining is not None and dte_remaining <= 21:
        exit_reason = (f"🕐 **21 DTE rule** — {dte_remaining} days to expiry. "
                       "Strategy rules say CLOSE NOW to avoid gamma risk.")
    elif current_pnl is not None and current_pnl >= profit_target:
        exit_reason = (f"✅ **50% profit target hit** — P&L ${current_pnl:+.2f} ≥ target ${profit_target:.2f}. "
                       "Close the position.")
    elif current_pnl is not None and current_pnl <= stop_loss:
        exit_reason = (f"🛑 **2× stop loss hit** — P&L ${current_pnl:+.2f} ≤ stop ${stop_loss:.2f}. "
                       "Close immediately.")

    if exit_reason:
        st.warning(exit_reason)

    # ── Enhanced payoff chart ─────────────────────────────────────────────────
    if short_call_k and short_put_k and long_call_k and long_put_k:
        # Use spot if available, else centre on the short strikes mid-point
        ref_price = spot if spot else (short_call_k + short_put_k) / 2
        prices = np.linspace(ref_price * 0.75, ref_price * 1.25, 400)

        def pnl_expiry(S):
            cs = np.minimum(0, short_call_k - S) + np.maximum(0, S - long_call_k)
            ps = np.minimum(0, S - short_put_k)  + np.maximum(0, long_put_k - S)
            return (net_credit + cs + ps) * 100

        pnl_exp = pnl_expiry(prices)

        # Today's P&L via BS — use IV from live option prices if available, else 25%
        _underlying_name = grp["Underlying"].iloc[0] if "Underlying" in grp.columns and not grp["Underlying"].dropna().empty else "?"
        _live_opt_for_iv = (
            st.session_state.get("pt_live_option_prices") or
            st.session_state.get("_live_opt_prices_cache") or
            {}
        )
        # Try to find IV from short call leg
        _sc_sym = short_calls["Symbol"].iloc[0] if not short_calls.empty and "Symbol" in short_calls.columns else None
        _raw_iv = (_live_opt_for_iv.get(_sc_sym) or {}).get("iv") if _sc_sym else None
        atm_iv = (_raw_iv / 100.0) if (_raw_iv is not None and _raw_iv > 0) else (
            st.session_state.get(f"_atm_iv_{_underlying_name}", 0.25)
        )
        T_now  = max((dte_remaining or 30) / 252, 0.001)
        r      = 0.045

        def bs_val(S, K, T, iv, otype):
            if T <= 0 or iv <= 0: return max(0, (S-K) if otype=="call" else (K-S))
            d1 = (_math.log(S/K) + (r + 0.5*iv**2)*T) / (iv*_math.sqrt(T))
            d2 = d1 - iv*_math.sqrt(T)
            return (S*_norm.cdf(d1) - K*_math.exp(-r*T)*_norm.cdf(d2) if otype=="call"
                    else K*_math.exp(-r*T)*_norm.cdf(-d2) - S*_norm.cdf(-d1))

        pnl_today = np.array([
            (net_credit
             - bs_val(S, short_call_k, T_now, atm_iv, "call")
             + bs_val(S, long_call_k,  T_now, atm_iv, "call")
             - bs_val(S, short_put_k,  T_now, atm_iv, "put")
             + bs_val(S, long_put_k,   T_now, atm_iv, "put")) * 100
            for S in prices
        ])

        fig = go.Figure()

        # Fills
        fig.add_trace(go.Scatter(x=prices, y=np.where(pnl_exp >= 0, pnl_exp, 0),
            fill="tozeroy", fillcolor="rgba(16,185,129,0.10)",
            line=dict(width=0), showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=prices, y=np.where(pnl_exp < 0, pnl_exp, 0),
            fill="tozeroy", fillcolor="rgba(239,68,68,0.10)",
            line=dict(width=0), showlegend=False, hoverinfo="skip"))

        # P&L lines
        fig.add_trace(go.Scatter(x=prices, y=pnl_exp, name="At expiry",
            line=dict(color="#6366f1", width=2),
            hovertemplate="$%{x:.2f} → $%{y:.0f}<extra>Expiry</extra>"))
        if spot:  # BS today-line only when live price available
            fig.add_trace(go.Scatter(x=prices, y=pnl_today, name="Today (BS)",
                line=dict(color="#10b981", width=1.5, dash="dot"),
                hovertemplate="$%{x:.2f} → $%{y:.0f}<extra>Today</extra>"))

        # Strategy exit rule lines
        fig.add_hline(y=profit_target * 100, line=dict(color="#10b981", width=1.5, dash="dash"),
                      annotation_text=f"✅ 50% close +${profit_target*100:.0f}",
                      annotation_font_color="#10b981", annotation_position="top left")
        fig.add_hline(y=stop_loss * 100, line=dict(color="#ef4444", width=1.5, dash="dash"),
                      annotation_text=f"🛑 2× stop −${abs(stop_loss)*100:.0f}",
                      annotation_font_color="#ef4444", annotation_position="bottom left")
        fig.add_hline(y=0, line=dict(color="#374151", width=1))

        # Verticals
        if spot:
            fig.add_vline(x=spot, line=dict(color="#f59e0b", width=1.5, dash="dash"),
                          annotation_text=f"Spot ${spot:.0f}", annotation_font_color="#f59e0b",
                          annotation_position="top right")
        if be_upper:
            fig.add_vline(x=be_upper, line=dict(color="#9ca3af", width=1, dash="dot"),
                          annotation_text=f"BE ${be_upper:.0f}", annotation_font_color="#9ca3af")
        if be_lower:
            fig.add_vline(x=be_lower, line=dict(color="#9ca3af", width=1, dash="dot"),
                          annotation_text=f"BE ${be_lower:.0f}", annotation_font_color="#9ca3af")

        title = f"Iron Condor P&L  |  Exp {expiry_str}  ({dte_remaining} DTE)  |  50% target · 2× stop · 21 DTE exit"
        fig.update_layout(
            title=dict(text=title, font=dict(size=12)),
            xaxis_title="Underlying Price", yaxis_title="P&L per Contract ($)",
            height=360, margin=dict(l=0, r=0, t=45, b=0),
            paper_bgcolor="#0a0e1a", plot_bgcolor="#111827",
            font=dict(color="#9ca3af", size=11),
            xaxis=dict(gridcolor="#1f2937", tickformat="$,.0f"),
            yaxis=dict(gridcolor="#1f2937", tickformat="$,.0f", zeroline=False),
            legend=dict(bgcolor="rgba(0,0,0,0)", orientation="h", y=-0.15),
        )
        st.plotly_chart(fig, width="stretch", key=f"ic_pnl_{tgid}")
        st.caption(
            "Solid purple = P&L at expiry · Dotted green = P&L today (BS, uses cached ATM IV) · "
            "Green/red dashed = strategy exit rules · Yellow = spot · Grey = breakevens"
        )
    else:
        # Fallback for non-IC structures
        payoff_fig = _plot_payoff(grp, spot)
        if payoff_fig is not None:
            st.plotly_chart(payoff_fig, width="stretch", key=f"ic_payoff_fallback_{tgid}")


def _plot_payoff(legs_grp: pd.DataFrame, spot: float | None) -> "go.Figure | None":
    """
    Plot the at-expiration payoff diagram for a multi-leg options position.
    """
    if "SecurityType" not in legs_grp.columns:
        return None
    opt = legs_grp[legs_grp["SecurityType"].str.lower() == "option"].copy()
    if opt.empty:
        return None

    strikes = opt["Strike"].dropna().astype(float)
    if strikes.empty:
        return None

    s_min = float(strikes.min())
    s_max = float(strikes.max())
    spread = max(s_max - s_min, 5.0)

    # Range must include current spot price plus generous buffer around strikes
    ref_points = [s_min - spread * 0.5, s_max + spread * 0.5]
    if spot:
        ref_points += [spot * 0.85, spot * 1.15]
    lo = min(ref_points)
    hi = max(ref_points)
    N = 400
    prices = [lo + (hi - lo) * i / N for i in range(N + 1)]

    # Net entry credit (positive = credit received)
    net_entry_credit = 0.0
    for _, r in opt.iterrows():
        direction = str(r.get("Direction", "")).upper()
        qty  = float(r.get("Quantity") or 1)
        mult = float(r.get("Multiplier") or 100)
        px   = float(r.get("TransactionPrice") or 0)
        sign = -1.0 if direction == "BUY" else 1.0
        net_entry_credit += sign * px * qty * mult

    # Payoff at each price
    pnl_curve = []
    for S in prices:
        total = net_entry_credit
        for _, r in opt.iterrows():
            K         = float(r.get("Strike") or 0)
            otype     = str(r.get("OptionType") or "").lower()
            direction = str(r.get("Direction", "")).upper()
            qty       = float(r.get("Quantity") or 1)
            mult      = float(r.get("Multiplier") or 100)
            intrinsic = max(S - K, 0) if otype == "call" else max(K - S, 0)
            sign      = 1.0 if direction == "BUY" else -1.0
            total    += sign * intrinsic * qty * mult
        pnl_curve.append(total)

    # Split into profit (green) and loss (red) segments
    profit_y = [v if v >= 0 else 0 for v in pnl_curve]
    loss_y   = [v if v <= 0 else 0 for v in pnl_curve]

    fig = go.Figure()

    # Profit fill (green)
    fig.add_trace(go.Scatter(
        x=prices, y=profit_y,
        mode="none", fill="tozeroy",
        fillcolor="rgba(38,166,154,0.25)", showlegend=False,
    ))
    # Loss fill (red)
    fig.add_trace(go.Scatter(
        x=prices, y=loss_y,
        mode="none", fill="tozeroy",
        fillcolor="rgba(239,83,80,0.25)", showlegend=False,
    ))
    # Main payoff line
    fig.add_trace(go.Scatter(
        x=prices, y=pnl_curve,
        mode="lines",
        line=dict(color="#e0e0e0", width=2),
        showlegend=False,
        hovertemplate="S=$%{x:.2f}  P&L=$%{y:+,.2f}<extra></extra>",
    ))

    # Breakeven zero line
    fig.add_hline(y=0, line_color="rgba(255,255,255,0.3)", line_width=1)

    # Strike lines (no annotations — too cluttered)
    leg_colors = {
        "ShortPut": "#ef5350", "LongPut": "#ffb300",
        "LongCallATK": "#26a69a", "ShortCall": "#ef5350", "LongCall": "#ffb300",
    }
    seen_strikes: set = set()
    for _, r in opt.iterrows():
        k = r.get("Strike")
        if k is None:
            continue
        k_f = float(k)
        lt  = str(r.get("LegType") or "")
        color = leg_colors.get(lt, "#888888")
        seen_strikes.add(k_f)
        fig.add_vline(
            x=k_f, line_dash="dot", line_color=color, line_width=1,
        )

    # Current spot
    if spot:
        fig.add_vline(
            x=spot, line_dash="solid", line_color="rgba(255,255,255,0.6)", line_width=1.5,
            annotation_text=f"  ${spot:.2f}",
            annotation_position="top right",
            annotation_font=dict(size=10, color="#ffffff"),
        )

    fig.update_layout(
        title=dict(text="Payoff at Expiration", font=dict(size=13)),
        height=280,
        template="plotly_dark",
        paper_bgcolor="#0e1117",
        plot_bgcolor="#0e1117",
        font=dict(color="#b0b8c8", size=11),
        xaxis=dict(
            gridcolor="#1e2130", title="Underlying Price at Expiry",
            tickprefix="$", range=[lo, hi],
        ),
        yaxis=dict(
            gridcolor="#1e2130", title="P&L ($)",
            tickprefix="$", zeroline=False,
        ),
        margin=dict(l=50, r=20, t=40, b=40),
    )
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# Close of Business — EOD snapshot
# ─────────────────────────────────────────────────────────────────────────────

def _run_close_of_business(engine, account_id: int, api_key: str) -> None:
    """
    EOD snapshot: aggregate all open positions from Transaction table and write
    to portfolio.Position for today's BusinessDate. Also roll the cash balance
    forward into portfolio.Balance.

    Logic:
      - Open positions  = all transaction legs whose TradeGroupId has no CLOSE note
      - Cash balance    = latest prior EOD Balance row + today's cash transactions
      - Position rows   = one row per (SecurityId, TradeGroupId) still open,
                          with net Quantity and weighted-avg cost
      - Any existing Position / Balance rows for today are deleted first
        so the button is idempotent (safe to re-run).
    """
    from sqlalchemy import text as _text

    business_date = datetime.date.today()

    with st.spinner("Running Close of Business…"):
        try:
            txns_df = _load_transactions(engine, account_id)
            if txns_df.empty:
                st.warning("No transactions found — nothing to snapshot.")
                return

            # ── Separate cash vs trade transactions ────────────────────────
            _st  = txns_df["SecurityType"].fillna("").str.lower()
            _lt  = txns_df.get("LegType", pd.Series(dtype=str)).fillna("").str.lower()
            cash_mask  = _st.isin(["cash"]) | _lt.isin(["cashin", "cashout"])
            trade_df   = txns_df[~cash_mask].copy()
            cash_txns  = txns_df[cash_mask].copy()

            # ── Identify open trade groups (no CLOSE note) ─────────────────
            _notes  = trade_df["Notes"].fillna("").str.upper()
            _src    = trade_df.get("Source", pd.Series(dtype=str)).fillna("").str.upper()
            _closed_ids = set(
                trade_df.loc[
                    _notes.str.contains("CLOSE") | (_src == "CLOSE"),
                    "TradeGroupId"
                ].dropna().unique()
            )
            open_df = trade_df[~trade_df["TradeGroupId"].isin(_closed_ids)].copy()

            # ── Compute net position per (SecurityId, TradeGroupId) ────────
            # Quantity: Buy = +, Sell = -
            open_df["SignedQty"] = open_df.apply(
                lambda r: float(r["Quantity"]) if str(r.get("Direction","")).upper() == "BUY"
                          else -float(r["Quantity"]),
                axis=1,
            )
            # Weighted avg cost (abs-qty weighted, direction-agnostic for entry price)
            open_df["CostBasis"] = open_df["SignedQty"].abs() * open_df["TransactionPrice"].fillna(0)

            pos_grp = (
                open_df
                .groupby(["SecurityId", "TradeGroupId", "StrategyName"])
                .agg(
                    NetQty       = ("SignedQty",  "sum"),
                    TotalCost    = ("CostBasis",  "sum"),
                    TotalAbsQty  = ("SignedQty",  lambda x: x.abs().sum()),
                )
                .reset_index()
            )
            pos_grp["AvgCostPrice"] = pos_grp.apply(
                lambda r: r["TotalCost"] / r["TotalAbsQty"] if r["TotalAbsQty"] > 0 else 0,
                axis=1,
            )
            # Drop fully-closed legs (net qty ≈ 0)
            pos_grp = pos_grp[pos_grp["NetQty"].abs() > 0.0001].copy()

            # ── Fetch live prices for mark-to-market ──────────────────────
            live_prices: dict[str, float] = {}
            live_opt:    dict[str, float] = {}
            if api_key and not open_df.empty:
                _und_list = list(open_df["Underlying"].dropna().unique())
                if _und_list:
                    live_prices = _fetch_stock_prices_bulk(api_key, _und_list)
                live_opt_full = _fetch_option_prices(api_key, open_df)
                live_opt = {sym: (d.get("price") or 0) for sym, d in live_opt_full.items() if d.get("price")}

            # ── Compute unrealized P&L per position ───────────────────────
            def _unrealized(row):
                sid  = row["SecurityId"]
                tgid = row["TradeGroupId"]
                legs = open_df[
                    (open_df["SecurityId"] == sid) &
                    (open_df["TradeGroupId"] == tgid)
                ]
                total = 0.0
                for _, leg in legs.iterrows():
                    stype = str(leg.get("SecurityType","")).lower()
                    sym   = str(leg.get("Symbol",""))
                    und   = str(leg.get("Underlying",""))
                    qty   = float(leg.get("Quantity") or 0)
                    ep    = float(leg.get("TransactionPrice") or 0)
                    mult  = float(leg.get("Multiplier") or 1)
                    d     = str(leg.get("Direction","")).upper()
                    cur   = live_prices.get(und) if stype in ("equity","etf") else live_opt.get(sym)
                    if cur is not None:
                        sign = 1.0 if d == "BUY" else -1.0
                        total += sign * (cur - ep) * qty * mult
                return total

            pos_grp["UnrealizedPnL"] = pos_grp.apply(_unrealized, axis=1)

            # ── Cash balance ───────────────────────────────────────────────
            # Prior EOD cash balance
            with engine.connect() as _conn:
                _prior = _conn.execute(_text("""
                    SELECT TOP 1 Amount FROM portfolio.Balance
                    WHERE AccountId = :aid AND BalanceType = 'Cash'
                      AND BusinessDate < :bd
                    ORDER BY BusinessDate DESC
                """), {"aid": account_id, "bd": business_date}).fetchone()
            prior_cash = float(_prior[0]) if _prior else 0.0

            # Today's cash transactions
            today_cash_df = cash_txns[
                cash_txns["BusinessDate"].apply(
                    lambda d: (d.date() if hasattr(d, "date") else d) == business_date
                )
            ]
            today_cash_delta = 0.0
            for _, r in today_cash_df.iterrows():
                amt = float(r.get("TransactionPrice") or 0)
                if str(r.get("Direction","")).lower() == "deposit":
                    today_cash_delta += amt
                else:
                    today_cash_delta -= amt

            eod_cash = prior_cash + today_cash_delta

            # ── Write to DB (idempotent — delete today's rows first) ───────
            with engine.begin() as _conn:
                # Clear today's snapshot
                _conn.execute(_text(
                    "DELETE FROM portfolio.Position WHERE AccountId=:aid AND BusinessDate=:bd"
                ), {"aid": account_id, "bd": business_date})
                _conn.execute(_text(
                    "DELETE FROM portfolio.Balance  WHERE AccountId=:aid AND BusinessDate=:bd"
                ), {"aid": account_id, "bd": business_date})

                # Write Position rows
                for _, pos in pos_grp.iterrows():
                    _conn.execute(_text("""
                        INSERT INTO portfolio.Position
                            (BusinessDate, AccountId, SecurityId, StrategyName,
                             TradeGroupId, Quantity, AvgCostPrice,
                             UnrealizedPnL, RealizedPnL, Status)
                        VALUES (:bd, :aid, :sid, :strat, :tgid, :qty, :acp,
                                :upnl, 0, 'Open')
                    """), {
                        "bd":   business_date,
                        "aid":  account_id,
                        "sid":  int(pos["SecurityId"]),
                        "strat": pos["StrategyName"] or "",
                        "tgid": pos["TradeGroupId"],
                        "qty":  float(pos["NetQty"]),
                        "acp":  float(pos["AvgCostPrice"]),
                        "upnl": float(pos["UnrealizedPnL"]),
                    })

                # Write Cash Balance row
                _conn.execute(_text("""
                    INSERT INTO portfolio.Balance
                        (BusinessDate, AccountId, BalanceType, Amount, Notes)
                    VALUES (:bd, :aid, 'Cash', :amt, :n)
                """), {
                    "bd":  business_date,
                    "aid": account_id,
                    "amt": eod_cash,
                    "n":   f"EOD snapshot — prior ${prior_cash:,.2f} + today ${today_cash_delta:+,.2f}",
                })

            n_pos = len(pos_grp)
            st.success(
                f"✅ EOD snapshot complete for {business_date}:  "
                f"**{n_pos}** position(s) written  |  "
                f"Cash balance: **${eod_cash:,.2f}**"
            )
            # Clear live price cache so next load re-fetches
            for k in list(st.session_state.keys()):
                if k.startswith("pt_live") or k.startswith("pt_iv"):
                    del st.session_state[k]
            st.rerun()

        except Exception as _e:
            st.error(f"Close of Business failed: {_e}")


# ─────────────────────────────────────────────────────────────────────────────
# Main render
# ─────────────────────────────────────────────────────────────────────────────

def render() -> None:
    st.header("Paper Trading")

    try:
        engine = _get_engine()
    except Exception as e:
        st.error(f"Cannot connect to database: {e}")
        return

    account_id = 1
    account_info = _get_account_info(engine, account_id)

    api_key: str = st.session_state.get("polygon_api_key", "")

    # ── Account header + Refresh + Close of Business ──────────────────────────
    hdr_col, cob_col, btn_col = st.columns([5, 2, 1])
    hdr_col.markdown(
        f"**Account:** {account_info['AccountName']} ({account_info['AccountType']})"
    )
    if btn_col.button("Refresh", key="pt_global_refresh"):
        for k in list(st.session_state.keys()):
            if k.startswith("pt_"):
                del st.session_state[k]
        st.rerun()

    if cob_col.button("📅 Close of Business", key="pt_cob_btn",
                      help="Snapshot today's positions and cash balance into Position and Balance tables"):
        st.session_state["pt_cob_confirm"] = True

    if st.session_state.get("pt_cob_confirm"):
        st.warning(
            "This will write today's EOD snapshot to **Position** and **Balance** tables "
            f"for {datetime.date.today()}. Run once at end of day."
        )
        _c1, _c2 = st.columns(2)
        if _c1.button("Confirm EOD Snapshot", key="pt_cob_yes", type="primary"):
            _run_close_of_business(engine, account_id, api_key)
            st.session_state.pop("pt_cob_confirm", None)
        if _c2.button("Cancel", key="pt_cob_no"):
            st.session_state.pop("pt_cob_confirm", None)
            st.rerun()

    # ── Load transactions ─────────────────────────────────────────────────────
    txns_df = _load_transactions(engine, account_id)

    # ── Metrics row ───────────────────────────────────────────────────────────
    open_groups  = _get_open_trade_groups(txns_df)
    closed_rows  = _get_closed_trade_groups(txns_df)

    n_open = len(open_groups)

    # Avg days open
    avg_days_open: float | None = None
    if open_groups:
        today = datetime.date.today()
        day_counts = []
        for tgid, grp in open_groups.items():
            open_date = grp["BusinessDate"].min()
            if open_date is not None:
                try:
                    if hasattr(open_date, "date"):
                        open_date = open_date.date()
                    day_counts.append((today - open_date).days)
                except Exception:
                    pass
        avg_days_open = float(np.mean(day_counts)) if day_counts else None

    STARTING_CAPITAL = 100_000.0  # fallback if no cash transactions in DB

    # Cash from DB: sum Deposit - Withdrawal transactions (SecurityType='cash')
    _cash_df = pd.DataFrame()
    if not txns_df.empty and "SecurityType" in txns_df.columns:
        _st = txns_df["SecurityType"].fillna("").str.lower()
        _lt = txns_df.get("LegType", pd.Series(dtype=str)).fillna("").str.lower()
        _cash_mask = _st.isin(["cash"]) | _lt.isin(["cashin", "cashout"])
        _cash_df = txns_df[_cash_mask]
    if not _cash_df.empty:
        _deposits    = _cash_df[_cash_df["Direction"].fillna("").str.lower() == "deposit"]["TransactionPrice"].fillna(0).sum()
        _withdrawals = _cash_df[_cash_df["Direction"].fillna("").str.lower() == "withdrawal"]["TransactionPrice"].fillna(0).sum()
        total_cash   = float(_deposits) - float(_withdrawals)
    else:
        total_cash   = STARTING_CAPITAL  # no cash transactions yet → use default

    # Realized P&L from closed groups
    total_realized = sum(r["P&L $"] for r in closed_rows) if closed_rows else 0.0

    # Fetch live prices early so metrics can show unrealized P&L
    if open_groups:
        _underlyings_early: set[str] = set()
        for _tgid, _grp in open_groups.items():
            if "Underlying" in _grp.columns:
                _u = _grp["Underlying"].dropna()
                if not _u.empty:
                    _underlyings_early.add(str(_u.iloc[0]))
        if "pt_live_prices" not in st.session_state and api_key and _underlyings_early:
            with st.spinner("Fetching live prices…"):
                st.session_state["pt_live_prices"] = _fetch_stock_prices_bulk(api_key, list(_underlyings_early))
                st.session_state["pt_live_option_prices"] = _fetch_option_prices(api_key, txns_df)

    _live_px  = st.session_state.get("pt_live_prices", {})
    _live_opt = st.session_state.get("pt_live_option_prices", {})

    # Compute total unrealized P&L across all open trades
    total_unrealized: float | None = 0.0
    for _, _grp in open_groups.items():
        _underlying = str(_grp["Underlying"].dropna().iloc[0]) if ("Underlying" in _grp.columns and not _grp["Underlying"].dropna().empty) else None
        for _, _r in _grp.iterrows():
            _stype = str(_r.get("SecurityType", "")).lower()
            _sym   = _r.get("Symbol", "")
            _ep    = float(_r.get("TransactionPrice") or 0)
            _dir   = str(_r.get("Direction", "")).upper()
            _qty   = float(_r.get("Quantity") or 1)
            _mult  = float(_r.get("Multiplier") or 1)
            _cur   = _live_px.get(str(_sym)) if _stype in ("equity", "etf") else (_live_opt.get(_sym) or {}).get("price")
            if _cur is not None and total_unrealized is not None:
                _sign = 1.0 if _dir == "BUY" else -1.0
                total_unrealized += _sign * (_cur - _ep) * _qty * _mult
            else:
                total_unrealized = None
                break
        if total_unrealized is None:
            break

    # Net cash flow from entering open positions (credits in = +, debits out = -)
    net_entry_cash = 0.0
    for _, _grp in open_groups.items():
        for _, _r in _grp.iterrows():
            _stype = str(_r.get("SecurityType", "")).lower()
            if _stype not in ("equity", "etf", "option"):
                continue
            _sign  = -1.0 if str(_r.get("Direction", "")).upper() == "BUY" else 1.0
            _qty   = float(_r.get("Quantity") or 1)
            _mult  = float(_r.get("Multiplier") or 1)
            _px    = float(_r.get("TransactionPrice") or 0)
            net_entry_cash += _sign * _qty * _mult * _px

    # Cash = deposits + realized + net premiums received (what's actually in the account)
    cash_balance  = total_cash + total_realized + net_entry_cash
    # Position value at current mark (what open positions are worth right now)
    position_mark = (total_unrealized or 0.0) - net_entry_cash   # unrealized vs entry, converted to current market value
    account_value = total_cash + total_realized + (total_unrealized or 0.0)

    m1, m2, m3, m4, m5, m6, m7 = st.columns(7)
    m1.metric("Account Value", f"${account_value:,.2f}",
              delta=f"{account_value - total_cash:+,.2f}",
              help="Cash + realized + unrealized P&L")
    m2.metric("Cash", f"${cash_balance:,.2f}",
              help="Deposits + realized P&L + net premiums received from open trades")
    m3.metric("Positions (Mark)", f"${position_mark:+,.2f}" if total_unrealized is not None else "—",
              help="Current market value of all open positions at mid-price")
    m4.metric("Open Trades", str(n_open))
    m5.metric("Unrealized P&L",
              f"${total_unrealized:+,.2f}" if total_unrealized is not None else "—",
              help="Mid-price mark vs entry across all open legs")
    m6.metric("Total Realized P&L", f"${total_realized:+,.2f}")
    m7.metric("Avg Days Open", f"{avg_days_open:.1f}" if avg_days_open is not None else "—")

    st.markdown("---")

    # ── Main tabs ─────────────────────────────────────────────────────────────
    tab_open, tab_closed, tab_txns, tab_perf = st.tabs(
        ["Open Positions", "Closed Positions", "All Transactions", "Performance"]
    )

    # ── TAB: Open Positions ───────────────────────────────────────────────────
    with tab_open:
        st.subheader("Open Positions")

        if not open_groups:
            st.info("No open trades. Run the screener and save signals to start tracking.")
        else:
            if st.button("Refresh Live Prices", key="pt_refresh_prices"):
                for k in list(st.session_state.keys()):
                    if k.startswith("pt_live") or k.startswith("pt_iv_skew"):
                        del st.session_state[k]
                st.rerun()

            # Collect all underlyings for bulk fetch
            underlyings: set[str] = set()
            all_txns_for_options = txns_df.copy()
            for tgid, grp in open_groups.items():
                if "Underlying" in grp.columns:
                    for u in grp["Underlying"].dropna().unique():
                        underlyings.add(str(u))
                # For multi-ticker equity groups (e.g. rotation), also add each equity symbol
                if "Symbol" in grp.columns and "SecurityType" in grp.columns:
                    eq = grp[grp["SecurityType"].str.lower().isin(["equity", "etf"])]
                    for sym in eq["Symbol"].dropna().unique():
                        underlyings.add(str(sym))

            # Fetch stock + option prices (cached in session state)
            if "pt_live_prices" not in st.session_state and api_key and underlyings:
                with st.spinner("Fetching live prices..."):
                    st.session_state["pt_live_prices"] = _fetch_stock_prices_bulk(api_key, list(underlyings))
                    st.session_state["pt_live_option_prices"] = _fetch_option_prices(api_key, all_txns_for_options)
            live_prices: dict[str, float | None] = dict(st.session_state.get("pt_live_prices", {}))
            # Fetch any symbols missing from the cache (positions added after last full refresh)
            if api_key:
                missing = [u for u in underlyings if u not in live_prices]
                if missing:
                    for _sym in missing:
                        live_prices[_sym] = _fetch_stock_price(api_key, _sym)
                    st.session_state["pt_live_prices"] = live_prices
            live_opt_prices: dict[str, float | None] = st.session_state.get("pt_live_option_prices", {})

            today = datetime.date.today()

            for tgid, grp in open_groups.items():
                # Resolve underlying — combined label only for multi-ticker equity groups
                _has_options = ("SecurityType" in grp.columns and
                                grp["SecurityType"].str.lower().eq("option").any())
                if not _has_options and "Symbol" in grp.columns:
                    _eq_syms = sorted(grp["Symbol"].dropna().unique())
                    if len(_eq_syms) > 1:
                        underlying = "+".join(_eq_syms)
                    elif _eq_syms:
                        underlying = _eq_syms[0]
                    else:
                        underlying = "?"
                elif "Underlying" in grp.columns and not grp["Underlying"].dropna().empty:
                    underlying = str(grp["Underlying"].dropna().iloc[0])
                elif "Symbol" in grp.columns and not grp.empty:
                    underlying = str(grp["Symbol"].iloc[0])
                else:
                    underlying = "?"

                strategy   = grp["StrategyName"].iloc[0] if not grp.empty else "?"
                open_date  = grp["BusinessDate"].min()
                n_legs     = len(grp)

                # Net entry cost (debit = negative, credit = positive)
                net_entry = 0.0
                for _, r in grp.iterrows():
                    sign = -1.0 if str(r.get("Direction", "")).upper() == "BUY" else 1.0
                    mult = float(r.get("Multiplier", 1) or 1)
                    net_entry += sign * float(r.get("Quantity", 0) or 0) * float(r.get("TransactionPrice", 0) or 0) * mult

                stock_price = live_prices.get(underlying)

                # Stock Δ% vs entry date — use SPY or underlying price; we just show current price
                stock_delta_str = f"${stock_price:.2f}" if stock_price else "—"

                # Signal from Notes of first row
                signal_str = "—"
                if not grp.empty and "Notes" in grp.columns:
                    notes_val = str(grp["Notes"].iloc[0] or "")
                    if notes_val and notes_val.upper() not in ("NAN", "NONE", ""):
                        signal_str = notes_val[:60]

                # Compute total unrealized P&L for header
                total_upnl: float | None = 0.0
                for _, r in grp.iterrows():
                    stype_h = str(r.get("SecurityType", "")).lower()
                    sym_h   = r.get("Symbol", "")
                    ep_h    = float(r.get("TransactionPrice") or 0)
                    dir_h   = str(r.get("Direction", "")).upper()
                    qty_h   = float(r.get("Quantity") or 1)
                    mult_h  = float(r.get("Multiplier") or 1)
                    cur_h   = live_prices.get(str(sym_h)) if stype_h in ("equity", "etf") else (live_opt_prices.get(sym_h) or {}).get("price")
                    if cur_h is not None and total_upnl is not None:
                        sign_h = 1.0 if dir_h == "BUY" else -1.0
                        total_upnl += sign_h * (cur_h - ep_h) * qty_h * mult_h
                    else:
                        total_upnl = None
                        break

                _ne_icon   = "🟢" if net_entry >= 0 else "🔴"
                _ne_str    = f"Net Entry: {_ne_icon} ${abs(net_entry):,.2f}"
                if total_upnl is not None:
                    _pnl_icon  = "🟢" if total_upnl >= 0 else "🔴"
                    upnl_str   = f" · P&L: {_pnl_icon} ${abs(total_upnl):,.2f}"
                else:
                    upnl_str   = ""
                pos_alerts    = _compute_position_alerts(grp, strategy, total_upnl, net_entry)
                alert_pfx     = _alert_icon(pos_alerts)
                # Use · instead of | to avoid Streamlit markdown table interpretation
                def _md_safe(s: str) -> str:
                    """Strip markdown-special chars that corrupt expander label rendering."""
                    for ch in ("_", "*", "`", "#", "~", "—", "|", "[", "]", "(", ")"):
                        s = s.replace(ch, " ")
                    return s.strip()

                expander_label = (
                    f"{alert_pfx}{underlying} · {_md_safe(strategy)} · "
                    f"Opened: {open_date} · {n_legs} {'leg' if n_legs == 1 else 'legs'} · "
                    f"{_ne_str} · Stock: {stock_delta_str}{upnl_str}"
                )

                with st.expander(expander_label, expanded=False):
                    # Alerts
                    for _alert in pos_alerts:
                        if _alert["level"] == "error":
                            st.error(_alert["msg"])
                        elif _alert["level"] == "warning":
                            st.warning(_alert["msg"])
                        else:
                            st.success(_alert["msg"])

                    # Legs table
                    leg_rows = []
                    for _, r in grp.iterrows():
                        stype    = str(r.get("SecurityType", "")).lower()
                        sym      = r.get("Symbol", "")
                        entry_px = float(r.get("TransactionPrice") or 0)
                        direction = str(r.get("Direction", "")).upper()
                        qty      = float(r.get("Quantity") or 1)
                        mult     = float(r.get("Multiplier") or 1)
                        opt_data = live_opt_prices.get(sym) or {}
                        is_long  = direction == "BUY"
                        if stype in ("equity", "etf"):
                            cur_px = live_prices.get(underlying)
                        else:
                            cur_px = opt_data.get("price")   # mid for P&L mark
                        cur_iv   = opt_data.get("iv") if stype == "option" else None
                        if cur_px is not None:
                            sign = 1.0 if is_long else -1.0
                            pnl  = sign * (cur_px - entry_px) * qty * mult
                        else:
                            pnl = None
                        signed_qty = qty if is_long else -qty
                        # Display: mid (bid–ask)
                        if stype in ("equity", "etf"):
                            px_label = cur_px
                        else:
                            b = opt_data.get("bid")
                            a = opt_data.get("ask")
                            m = opt_data.get("price")
                            if m is not None and b is not None and a is not None:
                                px_label = f"${m:.2f} ({b:.2f}–{a:.2f})"
                            elif m is not None:
                                px_label = f"${m:.2f}"
                            else:
                                px_label = None
                        leg_rows.append({
                            "LegType":     r.get("LegType", "—"),
                            "Symbol":      sym,
                            "Strike":      r.get("Strike"),
                            "Expiry":      r.get("Expiration"),
                            "Qty":         signed_qty,
                            "Entry Price": entry_px,
                            "Bid–Ask":     px_label,
                            "IV %":        cur_iv,
                            "P&L":         pnl,
                        })
                    legs_df = pd.DataFrame(leg_rows)

                    def _color_pnl(val):
                        if val is None or (isinstance(val, float) and math.isnan(val)):
                            return ""
                        return "color: #26a69a; font-weight: bold" if val >= 0 else "color: #ef5350; font-weight: bold"

                    def _fmt(x, fmt):
                        return fmt.format(x) if (x is not None and not (isinstance(x, float) and math.isnan(x))) else "—"

                    def _color_qty(val):
                        if val is None or (isinstance(val, float) and math.isnan(val)):
                            return ""
                        return "color: #26a69a" if val > 0 else "color: #ef5350"

                    def _fmt_ba(x):
                        if x is None or (isinstance(x, float) and math.isnan(x)):
                            return "—"
                        if isinstance(x, str):
                            return x   # already formatted as "bid – ask" for options
                        return f"${float(x):.2f}"  # equity: single price

                    styled_legs = (
                        legs_df.style
                        .map(_color_pnl, subset=["P&L"])
                        .map(_color_qty, subset=["Qty"])
                        .format({
                            "Entry Price": lambda x: _fmt(x, "${:.4f}"),
                            "Bid–Ask":     _fmt_ba,
                            "Strike":      lambda x: _fmt(x, "${:.1f}"),
                            "IV %":        lambda x: _fmt(x, "{:.1f}%"),
                            "P&L":         lambda x: _fmt(x, "${:+.2f}"),
                            "Qty":         lambda x: f"{x:+.0f}" if (x is not None and not (isinstance(x, float) and math.isnan(x))) else "—",
                        })
                    )
                    st.dataframe(styled_legs, hide_index=True, width="stretch")

                    # Strategy-specific position detail
                    _ic_strategies = ("Iron Condor — Rules", "Iron Condor — AI",
                                      "iron_condor_rules", "iron_condor_ai")

                    _has_options = any(
                        str(r.get("SecurityType", "")).lower() == "option"
                        for _, r in grp.iterrows()
                    )

                    if any(s in strategy for s in _ic_strategies):
                        try:
                            _render_ic_position(grp, stock_price, open_date, net_entry, api_key, tgid)
                        except Exception as _e:
                            st.warning(f"Payoff chart error: {_e}")
                            payoff_fig = _plot_payoff(grp, stock_price)
                            if payoff_fig is not None:
                                st.plotly_chart(payoff_fig, width="stretch", key=f"payoff_fallback_{tgid}")
                    elif _has_options:
                        # Any options position (GEX, screener, spreads) → generic options renderer
                        _render_screener_position(grp, stock_price, open_date, net_entry,
                                                  strategy, live_opt_prices,
                                                  chart_key_prefix=f"scr_{tgid}")
                    else:
                        # Pure equity / ETF position
                        _render_equity_position(grp, stock_price, open_date, net_entry, underlying,
                                                chart_key=f"eq_pos_{tgid}", live_prices=live_prices)

                    # Strategy-specific charts
                    if strategy == "IV Skew Premium Capture" and api_key:
                        from alan_trader.dashboard.tabs.chart_helpers import plot_iv_skew as _plot_iv_skew
                        _skew_key = f"pt_skew_{tgid}"
                        if _skew_key not in st.session_state:
                            with st.spinner(f"Fetching IV skew for {underlying}…"):
                                st.session_state[_skew_key] = _plot_iv_skew(api_key, underlying, grp)
                        _skew_fig = st.session_state.get(_skew_key)
                        if _skew_fig is not None:
                            st.plotly_chart(_skew_fig, width="stretch", key=f"skew_{tgid}")
                            st.caption(
                                "Dashed lines = position strikes.  "
                                "🔴 Short  🟡 Long  🟢 ATK"
                            )

                    st.caption(f"TradeGroupId: {tgid}")

                    # Close Trade button
                    close_key = f"pt_close_{tgid}"
                    confirm_key = f"pt_close_confirm_{tgid}"

                    if st.session_state.get(confirm_key):
                        # Show per-leg close prices from live data
                        _leg_rows = []
                        for _, _lr in grp.iterrows():
                            _sym  = str(_lr.get("Symbol", ""))
                            _ep   = float(_lr.get("TransactionPrice", 0) or 0)
                            _lp   = (_live_opt.get(_sym) or {}).get("price")
                            _leg_rows.append({
                                "Leg":         _lr.get("LegType", _sym),
                                "Symbol":      _sym,
                                "Entry Price": f"${_ep:.4f}",
                                "Close Price": f"${_lp:.4f}" if _lp is not None else "— (entry price used)",
                            })
                        st.warning("Confirm close? Each leg closes at live Polygon mid-price.")
                        st.dataframe(pd.DataFrame(_leg_rows), hide_index=True, width="stretch")
                        cc1, cc2 = st.columns([1, 4])
                        if cc1.button("Confirm Close", key=f"pt_close_yes_{tgid}", type="primary"):
                            _err = _insert_closing_transactions(engine, account_id, grp, _live_opt)
                            if _err:
                                st.error(f"Close failed: {_err}")
                            else:
                                st.session_state.pop(confirm_key, None)
                                st.session_state.pop("pt_live_prices", None)
                                st.session_state.pop("pt_live_option_prices", None)
                                st.toast("✅ Trade closed — positions updated.", icon="✅")
                                st.rerun()
                        if cc2.button("Cancel", key=f"pt_close_no_{tgid}"):
                            st.session_state.pop(confirm_key, None)
                            st.rerun()
                    else:
                        if st.button("Close Trade", key=close_key):
                            st.session_state[confirm_key] = True
                            st.rerun()

    # ── TAB: Closed Positions ─────────────────────────────────────────────────
    with tab_closed:
        st.subheader("Closed Positions")

        if not closed_rows:
            st.info("No closed trades yet.")
        else:
            for _cr in sorted(closed_rows, key=lambda r: str(r.get("Close Date") or ""), reverse=True):
                _tgid      = _cr["TradeGroupId"]
                _ul        = _cr["Underlying"]
                _strat     = _cr["Strategy"]
                _open_dt   = str(_cr.get("Open Date",  "—"))[:10]
                _close_dt  = str(_cr.get("Close Date", "—"))[:10]
                _pnl       = _cr["P&L $"]
                _pnl_str   = f"{'▲' if _pnl >= 0 else '▼'} ${_pnl:+,.2f}"
                _label     = f"{_ul} | {_strat} | {_open_dt} → {_close_dt} | {_pnl_str}"

                with st.expander(_label, expanded=False):
                    # Raw legs for this group
                    _grp_df = txns_df[txns_df["TradeGroupId"] == _tgid].copy()

                    # Opening legs
                    _open_legs = _grp_df[
                        ~(_grp_df.get("Notes", pd.Series(dtype=str)).fillna("").str.upper().str.contains("CLOSE") |
                          (_grp_df.get("Source", pd.Series(dtype=str)).fillna("").str.upper() == "CLOSE"))
                    ]
                    # Closing legs
                    _close_legs = _grp_df[
                        _grp_df.get("Notes", pd.Series(dtype=str)).fillna("").str.upper().str.contains("CLOSE") |
                        (_grp_df.get("Source", pd.Series(dtype=str)).fillna("").str.upper() == "CLOSE")
                    ]

                    # Merge open + close prices per leg by Symbol
                    _leg_rows = []
                    for _, _ol in _open_legs.iterrows():
                        _sym      = str(_ol.get("Symbol", ""))
                        _cl_match = _close_legs[_close_legs["Symbol"] == _sym]
                        _close_px = float(_cl_match["TransactionPrice"].iloc[0]) if not _cl_match.empty else None
                        _open_px  = float(_ol.get("TransactionPrice", 0) or 0)
                        _qty      = float(_ol.get("Quantity", 1) or 1)
                        _mult     = float(_ol.get("Multiplier", 100) or 100)
                        _dir      = str(_ol.get("Direction", "BUY")).upper()
                        # SELL-to-open profits when price falls; BUY-to-open profits when price rises
                        _sign     = 1.0 if _dir == "SELL" else -1.0
                        _leg_pnl  = _sign * (_open_px - _close_px) * _qty * _mult if _close_px is not None else None
                        _leg_rows.append({
                            "Leg":         _ol.get("LegType", ""),
                            "Symbol":      _sym,
                            "Strike":      _ol.get("Strike"),
                            "Type":        str(_ol.get("OptionType", "")).capitalize(),
                            "Expiry":      str(_ol.get("Expiration", ""))[:10],
                            "Qty":         _qty,
                            "Open Price":  _open_px,
                            "Close Price": _close_px,
                            "P&L":         _leg_pnl,
                        })

                    if _leg_rows:
                        st.dataframe(
                            pd.DataFrame(_leg_rows),
                            hide_index=True,
                            width="stretch",
                            column_config={
                                "Strike":      cc.NumberColumn(format="$%.2f"),
                                "Open Price":  cc.NumberColumn(format="$%.4f"),
                                "Close Price": cc.NumberColumn(format="$%.4f"),
                                "P&L":         cc.NumberColumn(format="$%.2f"),
                            },
                        )

                        # P&L bar chart per leg
                        _pnl_vals = [r["P&L"] for r in _leg_rows if r["P&L"] is not None]
                        if _pnl_vals:
                            _pnl_labels  = [
                                f"{r['Leg'] or r['Symbol'][:12]}" for r in _leg_rows if r["P&L"] is not None
                            ]
                            _pnl_colors  = ["#26a69a" if v >= 0 else "#ef5350" for v in _pnl_vals]
                            _total_pnl   = sum(_pnl_vals)

                            fig_closed = go.Figure(go.Bar(
                                x=_pnl_labels,
                                y=_pnl_vals,
                                marker_color=_pnl_colors,
                                text=[f"${v:+,.2f}" for v in _pnl_vals],
                                textposition="outside",
                                hovertemplate="%{x}<br>P&L: %{y:$,.2f}<extra></extra>",
                            ))
                            fig_closed.add_hline(y=0, line=dict(color="#374151", width=1))
                            fig_closed.update_layout(
                                template="plotly_dark",
                                title=f"P&L per Leg — Total: ${_total_pnl:+,.2f}",
                                height=260,
                                margin=dict(t=40, b=20, l=0, r=0),
                                xaxis_title=None,
                                yaxis=dict(tickformat="$,.0f"),
                            )
                            st.plotly_chart(fig_closed, width="stretch", key=f"closed_pnl_{_tgid}")
                    else:
                        st.caption("No legs found.")

    # ── TAB: All Transactions ─────────────────────────────────────────────────
    with tab_txns:
        st.subheader("All Transactions")

        # ── Delete controls ────────────────────────────────────────────────────
        with st.expander("Delete Transactions", expanded=False):
            from sqlalchemy import text as _text

            today_str = datetime.date.today().isoformat()

            # Available business dates for targeted delete
            available_dates = sorted(
                txns_df["BusinessDate"].dropna().astype(str).unique(), reverse=True
            ) if not txns_df.empty else []

            d1, d2, d3 = st.columns(3)

            # ── Delete by date ─────────────────────────────────────────────
            with d1:
                st.markdown("**Delete by date**")
                del_date = st.selectbox(
                    "Business date", options=available_dates or [today_str],
                    key="pt_del_date"
                )
                if st.button("Delete this date", key="pt_del_date_btn"):
                    st.session_state["pt_del_date_confirm"] = del_date

                if st.session_state.get("pt_del_date_confirm"):
                    target = st.session_state["pt_del_date_confirm"]
                    st.warning(f"Delete all transactions on {target}?")
                    ca, cb = st.columns(2)
                    if ca.button("Confirm", key="pt_del_date_yes", type="primary"):
                        try:
                            with engine.begin() as _conn:
                                _conn.execute(_text(
                                    "DELETE FROM portfolio.[Transaction] WHERE BusinessDate = :d"
                                ), {"d": target})
                            st.session_state.pop("pt_del_date_confirm", None)
                            for k in list(st.session_state.keys()):
                                if k.startswith("pt_live") or k.startswith("pt_iv"):
                                    del st.session_state[k]
                            st.success(f"Deleted transactions for {target}.")
                            st.rerun()
                        except Exception as _e:
                            st.error(f"Failed: {_e}")
                    if cb.button("Cancel", key="pt_del_date_no"):
                        st.session_state.pop("pt_del_date_confirm", None)
                        st.rerun()

            # ── Delete today ────────────────────────────────────────────────
            with d2:
                st.markdown("**Delete today only**")
                today_count = (
                    len(txns_df[txns_df["BusinessDate"].astype(str) == today_str])
                    if not txns_df.empty else 0
                )
                st.caption(f"{today_count} transaction(s) on {today_str}")
                if st.button("Delete today's trades", key="pt_del_today_btn"):
                    st.session_state["pt_del_today_confirm"] = True

                if st.session_state.get("pt_del_today_confirm"):
                    st.warning(f"Delete all {today_count} transaction(s) from today?")
                    ca, cb = st.columns(2)
                    if ca.button("Confirm", key="pt_del_today_yes", type="primary"):
                        try:
                            with engine.begin() as _conn:
                                _conn.execute(_text(
                                    "DELETE FROM portfolio.[Transaction] WHERE BusinessDate = :d"
                                ), {"d": today_str})
                            st.session_state.pop("pt_del_today_confirm", None)
                            for k in list(st.session_state.keys()):
                                if k.startswith("pt_live") or k.startswith("pt_iv"):
                                    del st.session_state[k]
                            st.success("Today's transactions deleted.")
                            st.rerun()
                        except Exception as _e:
                            st.error(f"Failed: {_e}")
                    if cb.button("Cancel", key="pt_del_today_no"):
                        st.session_state.pop("pt_del_today_confirm", None)
                        st.rerun()

            # ── Delete everything ───────────────────────────────────────────
            with d3:
                st.markdown("**Delete everything**")
                total_count = len(txns_df) if not txns_df.empty else 0
                st.caption(f"{total_count} total transaction(s)")
                if st.button("Delete ALL transactions", key="pt_reset_btn"):
                    st.session_state["pt_confirm_reset"] = True

                if st.session_state.get("pt_confirm_reset"):
                    st.error("This cannot be undone.")
                    ca, cb = st.columns(2)
                    if ca.button("Confirm", key="pt_reset_confirm_yes", type="primary"):
                        try:
                            with engine.begin() as _conn:
                                _conn.execute(_text("DELETE FROM portfolio.[Transaction]"))
                                _conn.execute(_text("DELETE FROM portfolio.Security"))
                            for k in list(st.session_state.keys()):
                                if k.startswith("pt_"):
                                    del st.session_state[k]
                            st.success("All transactions deleted.")
                            st.rerun()
                        except Exception as _e:
                            st.error(f"Failed: {_e}")
                    if cb.button("Cancel", key="pt_reset_confirm_no"):
                        st.session_state.pop("pt_confirm_reset", None)
                        st.rerun()

        # ── Cash movement entry ────────────────────────────────────────────────
        with st.expander("Record Cash Movement", expanded=False):
            from sqlalchemy import text as _text2
            _cm1, _cm2, _cm3 = st.columns(3)
            _cm_dir    = _cm1.selectbox("Type", ["Deposit", "Withdrawal"], key="pt_cash_dir")
            _cm_amount = _cm2.number_input("Amount ($)", min_value=0.01, value=100_000.0,
                                           step=1_000.0, key="pt_cash_amount")
            _cm_notes  = _cm3.text_input("Notes", placeholder="e.g. Starting capital",
                                         key="pt_cash_notes")
            if st.button("Record Cash", key="pt_cash_btn", type="primary"):
                try:
                    import uuid as _uuid2, datetime as _dt2
                    with engine.begin() as _conn2:
                        # Ensure USD cash security exists
                        _usd = _conn2.execute(_text2(
                            "SELECT SecurityId FROM portfolio.Security "
                            "WHERE Symbol='USD' AND SecurityType='cash'"
                        )).fetchone()
                        if not _usd:
                            _usd = _conn2.execute(_text2(
                                "INSERT INTO portfolio.Security (Symbol, SecurityType, Multiplier) "
                                "OUTPUT INSERTED.SecurityId VALUES ('USD','cash',1)"
                            )).fetchone()
                        _usd_id = _usd[0]
                        _lt2 = "CashIn" if _cm_dir == "Deposit" else "CashOut"
                        _conn2.execute(_text2("""
                            INSERT INTO portfolio.[Transaction]
                                (BusinessDate, AccountId, TradeGroupId, StrategyName,
                                 SecurityId, Direction, Quantity, TransactionPrice,
                                 Commission, LegType, Source, Notes)
                            VALUES (:d, :aid, :tg, 'Account', :sid, :dir, 1, :px,
                                    0, :lt, 'Manual', :n)
                        """), {"d": _dt2.date.today(), "aid": account_id,
                               "tg": f"CASH-{str(_uuid2.uuid4())[:8]}",
                               "sid": _usd_id, "dir": _cm_dir, "px": _cm_amount,
                               "lt": _lt2, "n": _cm_notes or f"{_cm_dir} ${_cm_amount:,.0f}"})
                    st.success(f"{_cm_dir} of ${_cm_amount:,.2f} recorded.")
                    st.rerun()
                except Exception as _ex3:
                    st.error(f"Failed: {_ex3}")

        if txns_df.empty:
            st.info("No transactions found.")
        else:
            display_df = txns_df.copy()
            if "TradeGroupId" in display_df.columns:
                display_df["TradeGroup"] = display_df["TradeGroupId"].astype(str).str[:12] + "…"

            # Compute Cash Flow column: Deposit/Sell = positive, Withdrawal/Buy = negative
            def _cash_flow(row):
                direction = str(row.get("Direction", "")).lower()
                qty   = float(row.get("Quantity") or 0)
                price = float(row.get("TransactionPrice") or 0)
                mult  = float(row.get("Multiplier") or 1)
                sec   = str(row.get("SecurityType", "")).lower()
                if sec == "cash":
                    return price if direction == "deposit" else -price
                if direction in ("sell", "buy"):
                    sign = 1.0 if direction == "sell" else -1.0
                    return sign * qty * price * mult
                return 0.0

            display_df["Cash Flow"] = display_df.apply(_cash_flow, axis=1)

            show_cols = [c for c in [
                "BusinessDate", "Underlying", "Symbol", "LegType",
                "Direction", "Quantity", "TransactionPrice", "Cash Flow", "Commission",
                "StrategyName", "TradeGroup", "Notes",
            ] if c in display_df.columns]

            st.dataframe(
                display_df[show_cols],
                hide_index=True,
                width="stretch",
                column_config={
                    "TransactionPrice": cc.NumberColumn("Price",    format="$%.4f"),
                    "Cash Flow":        cc.NumberColumn("Cash Flow", format="$%.2f"),
                    "Commission":       cc.NumberColumn(format="$%.2f"),
                },
            )
            total_flow = display_df["Cash Flow"].sum()
            st.caption(f"{len(display_df)} transaction(s)  |  Net Cash Flow: ${total_flow:+,.2f}")

    # ── TAB: Performance ──────────────────────────────────────────────────────
    with tab_perf:
        st.subheader("Performance")

        # ── Account Equity Curve ──────────────────────────────────────────────
        if closed_rows or open_groups:
            _today = datetime.date.today()

            # Build daily realized P&L series from closed trades
            _eq_dates:  list = []
            _eq_values: list = []
            _eq_daily:  list = []
            _eq_cumreal: list = []
            _eq_unreal: list = []

            _cum_real  = 0.0
            _cum_cash  = 0.0  # net deposits/withdrawals beyond initial cash

            # Cash movements from transactions (deposits + / withdrawals -)
            _cash_events: dict = {}  # date -> net cash flow
            if not txns_df.empty and "SecurityType" in txns_df.columns:
                _cash_txns = txns_df[txns_df["SecurityType"].str.lower() == "cash"].copy()
                for _, _ct in _cash_txns.iterrows():
                    _ct_date = pd.to_datetime(_ct.get("BusinessDate")).date()
                    _ct_dir  = str(_ct.get("Direction", "")).lower()
                    _ct_amt  = float(_ct.get("TransactionPrice") or 0)
                    _ct_flow = _ct_amt if _ct_dir == "deposit" else -_ct_amt
                    _cash_events[_ct_date] = _cash_events.get(_ct_date, 0.0) + _ct_flow

            # Merge closed trade P&L + cash events by date
            _all_dates: set = set()
            _daily_real: dict = {}
            if closed_rows:
                _closed_eq = (
                    pd.DataFrame(closed_rows)
                    .dropna(subset=["Close Date"])
                    .assign(**{"Close Date": lambda d: pd.to_datetime(d["Close Date"]).dt.date})
                    .groupby("Close Date")["P&L $"]
                    .sum()
                )
                for _d, _v in _closed_eq.items():
                    _daily_real[_d] = float(_v)
                    _all_dates.add(_d)
            _all_dates.update(_cash_events.keys())

            _sorted_dates = sorted(_all_dates)

            # Anchor point: $100k on the day before the first event
            if _sorted_dates:
                import datetime as _dt_mod
                _anchor_date = _sorted_dates[0] - _dt_mod.timedelta(days=1)
                _eq_dates.append(_anchor_date)
                _eq_daily.append(0.0)
                _eq_cumreal.append(0.0)
                _eq_values.append(_INITIAL_CASH)
                _eq_unreal.append(None)

            for _edate in _sorted_dates:
                _day_pnl  = _daily_real.get(_edate, 0.0)
                _day_cash = _cash_events.get(_edate, 0.0)
                _cum_real += _day_pnl
                _cum_cash += _day_cash
                _eq_dates.append(_edate)
                _eq_daily.append(_day_pnl)
                _eq_cumreal.append(_cum_real)
                _eq_values.append(_INITIAL_CASH + _cum_cash + _cum_real)
                _eq_unreal.append(None)

            # Add today's point with unrealized P&L
            _total_unreal: float | None = None
            if open_groups and _live_opt is not None:
                _total_unreal = 0.0
                for _, _og in open_groups.items():
                    for _, _or in _og.iterrows():
                        _stype_e = str(_or.get("SecurityType", "")).lower()
                        _sym_e   = _or.get("Symbol", "")
                        _ul_e    = str(_or.get("Underlying", ""))
                        _ep_e    = float(_or.get("TransactionPrice") or 0)
                        _dir_e   = str(_or.get("Direction", "")).upper()
                        _qty_e   = float(_or.get("Quantity") or 1)
                        _mult_e  = float(_or.get("Multiplier") or 1)
                        _cur_e   = _live_px.get(_ul_e) if _stype_e in ("equity", "etf") else (_live_opt.get(_sym_e) or {}).get("price")
                        if _cur_e is not None and _total_unreal is not None:
                            _sign_e = 1.0 if _dir_e == "BUY" else -1.0
                            _total_unreal += _sign_e * (_cur_e - _ep_e) * _qty_e * _mult_e
                        else:
                            _total_unreal = None
                            break
                    if _total_unreal is None:
                        break

            # Add today point (even if unrealized is None, show realized-only value)
            _today_value = _INITIAL_CASH + _cum_real + (_total_unreal or 0.0)
            if not _eq_dates or _eq_dates[-1] != _today:
                _eq_dates.append(_today)
                _eq_daily.append(0.0)
                _eq_cumreal.append(_cum_real)
                _eq_values.append(_today_value)
                _eq_unreal.append(_total_unreal)
            else:
                # Update last point with unrealized
                _eq_values[-1]  = _today_value
                _eq_unreal[-1]  = _total_unreal

            if len(_eq_dates) >= 1:
                # Build hover text
                def _clr(v: float) -> str:
                    return "#26a69a" if v >= 0 else "#ef5350"

                def _signed(v: float) -> str:
                    return f"{'▲' if v >= 0 else '▼'} ${abs(v):,.2f}"

                _hover = []
                for i, d in enumerate(_eq_dates):
                    _val  = _eq_values[i]
                    _real = _eq_cumreal[i]
                    _day  = _eq_daily[i]
                    _unr  = _eq_unreal[i]
                    _dc   = _cash_events.get(d, 0.0)
                    _net_chg = _val - _INITIAL_CASH

                    _unr_row  = (
                        f"<br><span style='color:#a78bfa'>Unrealized: {_signed(_unr)}</span>"
                        if _unr is not None else ""
                    )
                    _day_row  = (
                        f"<br><span style='color:{_clr(_day)}'>Daily P&L: {_signed(_day)}</span>"
                        if _day != 0 else ""
                    )
                    _cash_row = (
                        f"<br><span style='color:#60a5fa'>{'Deposit' if _dc > 0 else 'Withdrawal'}: ${abs(_dc):,.2f}</span>"
                        if _dc != 0 else ""
                    )

                    _hover.append(
                        f"<b style='font-size:13px'>{d}</b><br>"
                        f"<b style='color:#f5f5f5;font-size:15px'>${_val:,.2f}</b>"
                        f"<br><span style='color:{_clr(_net_chg)}'>Total: {_signed(_net_chg)}</span>"
                        f"<br><span style='color:{_clr(_real)}'>Realized: {_signed(_real)}</span>"
                        f"{_day_row}{_cash_row}{_unr_row}"
                        f"<extra></extra>"
                    )

                _line_color  = "#26a69a" if _eq_values[-1] >= _INITIAL_CASH else "#ef5350"
                _fill_color  = "rgba(38,166,154,0.12)" if _eq_values[-1] >= _INITIAL_CASH else "rgba(239,83,80,0.10)"

                fig_eq = go.Figure()
                # Baseline at initial cash
                fig_eq.add_hline(
                    y=_INITIAL_CASH, line_dash="dot",
                    line_color="rgba(255,255,255,0.25)", line_width=1,
                    annotation_text=f"Starting ${_INITIAL_CASH:,.0f}",
                    annotation_position="bottom right",
                    annotation_font=dict(size=9, color="rgba(255,255,255,0.4)"),
                )
                fig_eq.add_trace(go.Scatter(
                    x=_eq_dates,
                    y=_eq_values,
                    mode="lines+markers",
                    line=dict(color=_line_color, width=2.5),
                    marker=dict(size=6, color=_line_color),
                    fill="tozeroy",
                    fillcolor=_fill_color,
                    hovertemplate=_hover,
                    name="Account Value",
                ))

                _pnl_total = _eq_values[-1] - _INITIAL_CASH
                _pnl_pct   = _pnl_total / _INITIAL_CASH * 100
                fig_eq.update_layout(
                    template="plotly_dark",
                    title=dict(
                        text=f"Account Equity  |  ${_eq_values[-1]:,.2f}  "
                             f"({'▲' if _pnl_total >= 0 else '▼'} ${abs(_pnl_total):,.2f} / {_pnl_pct:+.2f}%)",
                        font=dict(size=13),
                    ),
                    height=320,
                    margin=dict(t=45, b=20, l=0, r=0),
                    showlegend=False,
                    xaxis=dict(title=None),
                    yaxis=dict(title="Account Value ($)", tickformat="$,.0f",
                               showgrid=True, gridcolor="rgba(255,255,255,0.07)"),
                    paper_bgcolor="#0e1117",
                    plot_bgcolor="#0e1117",
                    hoverlabel=dict(
                        bgcolor="#1e2130",
                        bordercolor="#444",
                        font=dict(size=12, color="#f5f5f5"),
                    ),
                    hovermode="x unified",
                )
                st.plotly_chart(fig_eq, width="stretch")
                if _total_unreal is None:
                    st.caption("Realized P&L only — refresh Live Prices in Open Positions to include unrealized.")
            st.markdown("---")

        # ── Open Positions — Unrealized P&L snapshot ──────────────────────────
        if open_groups:
            open_pnl_rows = []
            for _tgid, _grp in open_groups.items():
                _underlying = str(_grp["Underlying"].dropna().iloc[0]) if ("Underlying" in _grp.columns and not _grp["Underlying"].dropna().empty) else "?"
                _strategy   = _grp["StrategyName"].iloc[0] if not _grp.empty else "?"
                _open_date  = _grp["BusinessDate"].min()
                _dte = None
                # DTE from first option expiry
                _exps = _grp["Expiration"].dropna() if "Expiration" in _grp.columns else pd.Series()
                if not _exps.empty:
                    try:
                        _dte = (pd.to_datetime(_exps.iloc[0]).date() - datetime.date.today()).days
                    except Exception:
                        pass

                _upnl: float | None = 0.0
                for _, _r in _grp.iterrows():
                    _stype = str(_r.get("SecurityType", "")).lower()
                    _sym   = _r.get("Symbol", "")
                    _ep    = float(_r.get("TransactionPrice") or 0)
                    _dir   = str(_r.get("Direction", "")).upper()
                    _qty   = float(_r.get("Quantity") or 1)
                    _mult  = float(_r.get("Multiplier") or 1)
                    _cur   = _live_px.get(str(_sym)) if _stype in ("equity", "etf") else (_live_opt.get(_sym) or {}).get("price")
                    if _cur is not None and _upnl is not None:
                        _sign = 1.0 if _dir == "BUY" else -1.0
                        _upnl += _sign * (_cur - _ep) * _qty * _mult
                    else:
                        _upnl = None
                        break

                # Net entry credit/debit (full dollar value: price × qty × multiplier)
                _net_entry = sum(
                    (-1 if str(_r.get("Direction","")).upper()=="BUY" else 1)
                    * float(_r.get("TransactionPrice") or 0)
                    * float(_r.get("Quantity") or 1)
                    * float(_r.get("Multiplier") or 1)
                    for _, _r in _grp.iterrows()
                )

                open_pnl_rows.append({
                    "label":    f"{_underlying}\n{_strategy[:20]}",
                    "ticker":   _underlying,
                    "strategy": _strategy,
                    "upnl":     _upnl,
                    "net_entry": _net_entry,
                    "dte":      _dte,
                    "open_date": str(_open_date)[:10] if _open_date is not None else "—",
                    "tgid":     _tgid[:12],
                })

            if open_pnl_rows:
                st.markdown("#### 📊 Open Positions — Unrealized P&L")

                # Bar chart per open position
                _labels  = [f"{r['ticker']} ({r['tgid']})" for r in open_pnl_rows]
                _upnls   = [r["upnl"] for r in open_pnl_rows]
                _has_any = any(v is not None for v in _upnls)

                if _has_any:
                    _colors  = ["#26a69a" if (v or 0) >= 0 else "#ef5350" for v in _upnls]
                    _vals    = [v if v is not None else 0 for v in _upnls]
                    _texts   = [f"${v:+,.2f}" if v is not None else "No price" for v in _upnls]

                    fig_open = go.Figure(go.Bar(
                        x=_labels, y=_vals,
                        marker_color=_colors,
                        text=_texts, textposition="outside",
                        hovertemplate="%{x}<br>Unrealized P&L: %{y:$,.2f}<extra></extra>",
                    ))
                    fig_open.add_hline(y=0, line=dict(color="#374151", width=1))
                    fig_open.update_layout(
                        template="plotly_dark",
                        title="Unrealized P&L — Open Positions (live mark)",
                        height=320,
                        margin=dict(t=40, b=20, l=0, r=0),
                        xaxis_title=None, yaxis_title="Unrealized P&L ($)",
                        yaxis=dict(tickformat="$,.0f"),
                    )
                    st.plotly_chart(fig_open, width="stretch")
                else:
                    st.caption("Refresh Live Prices in Open Positions to see unrealized P&L here.")

                # Open positions summary table
                _open_tbl = pd.DataFrame([{
                    "Ticker":    r["ticker"],
                    "Strategy":  r["strategy"],
                    "Opened":    r["open_date"],
                    "DTE":       r["dte"],
                    "Net Entry": r["net_entry"],
                    "Unr. P&L":  r["upnl"],
                } for r in open_pnl_rows])
                st.dataframe(_open_tbl, hide_index=True, width="stretch", column_config={
                    "Net Entry": cc.NumberColumn(format="$%.2f",  help="Credit (+) or debit (-) at entry"),
                    "Unr. P&L":  cc.NumberColumn(format="$%.2f",  help="Live mark vs entry price"),
                })
                st.markdown("---")

        if not closed_rows:
            st.info("No closed trades available for performance analysis.")
        else:
            closed_df = pd.DataFrame(closed_rows)

            # ── Combo chart: daily P&L bars + cumulative P&L line ─────────────────
            closed_sorted = closed_df.dropna(subset=["Close Date"]).sort_values("Close Date").copy()
            closed_sorted["Close Date"] = pd.to_datetime(closed_sorted["Close Date"]).dt.date

            if not closed_sorted.empty:
                # Daily P&L: sum all trades closed on the same date
                daily_pnl = (
                    closed_sorted.groupby("Close Date")["P&L $"]
                    .sum()
                    .reset_index()
                    .sort_values("Close Date")
                )
                daily_pnl["Cumulative P&L"] = daily_pnl["P&L $"].cumsum()

                _bar_colors = ["#26a69a" if v >= 0 else "#ef5350" for v in daily_pnl["P&L $"]]

                fig_combo = go.Figure()

                # Bars — daily P&L (left y-axis)
                fig_combo.add_trace(go.Bar(
                    x=daily_pnl["Close Date"],
                    y=daily_pnl["P&L $"],
                    name="Daily P&L",
                    marker_color=_bar_colors,
                    text=[f"${v:+,.0f}" for v in daily_pnl["P&L $"]],
                    textposition="outside",
                    yaxis="y1",
                    hovertemplate="%{x}<br>Daily P&L: %{y:$,.2f}<extra></extra>",
                ))

                # Line — cumulative P&L (right y-axis)
                fig_combo.add_trace(go.Scatter(
                    x=daily_pnl["Close Date"],
                    y=daily_pnl["Cumulative P&L"],
                    name="Cumulative P&L",
                    mode="lines+markers",
                    line=dict(color="#5c6bc0", width=2),
                    marker=dict(size=6),
                    yaxis="y2",
                    hovertemplate="%{x}<br>Cumulative: %{y:$,.2f}<extra></extra>",
                ))

                fig_combo.update_layout(
                    template="plotly_dark",
                    title="Realized P&L — Daily vs Cumulative",
                    height=380,
                    margin=dict(t=45, b=20, l=0, r=60),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                    barmode="relative",
                    xaxis=dict(title=None),
                    yaxis=dict(
                        title="Daily P&L ($)",
                        tickformat="$,.0f",
                        showgrid=True,
                        gridcolor="rgba(255,255,255,0.07)",
                    ),
                    yaxis2=dict(
                        title="Cumulative P&L ($)",
                        tickformat="$,.0f",
                        overlaying="y",
                        side="right",
                        showgrid=False,
                    ),
                )
                st.plotly_chart(fig_combo, width="stretch")

            # P&L by strategy bar chart
            by_strategy = (
                closed_df.groupby("Strategy")["P&L $"]
                .agg(["sum", "count", "mean"])
                .reset_index()
                .rename(columns={"sum": "Total P&L", "count": "# Trades", "mean": "Avg P&L"})
            )

            fig_bar = go.Figure(go.Bar(
                x=by_strategy["Strategy"],
                y=by_strategy["Total P&L"],
                marker_color=[
                    "#26a69a" if v >= 0 else "#ef5350"
                    for v in by_strategy["Total P&L"]
                ],
                text=[f"${v:+,.2f}" for v in by_strategy["Total P&L"]],
                textposition="outside",
            ))
            fig_bar.update_layout(
                template="plotly_dark",
                title="P&L by Strategy",
                height=320,
                margin=dict(t=40, b=20, l=0, r=0),
                xaxis_title=None,
                yaxis_title="Total P&L ($)",
            )
            st.plotly_chart(fig_bar, width="stretch")

            # Summary table
            summary_rows = []
            for _, srow in by_strategy.iterrows():
                strat_closed = closed_df[closed_df["Strategy"] == srow["Strategy"]]
                wins = (strat_closed["P&L $"] > 0).sum()
                n    = len(strat_closed)
                win_rate = wins / n * 100 if n > 0 else 0.0
                summary_rows.append({
                    "Strategy":  srow["Strategy"],
                    "# Trades":  n,
                    "Win Rate":  win_rate,
                    "Avg P&L":   srow["Avg P&L"],
                    "Total P&L": srow["Total P&L"],
                })

            summary_df = pd.DataFrame(summary_rows)
            st.dataframe(
                summary_df,
                hide_index=True,
                width="stretch",
                column_config={
                    "Win Rate":  cc.NumberColumn(format="%.1f%%"),
                    "Avg P&L":   cc.NumberColumn(format="$%.2f"),
                    "Total P&L": cc.NumberColumn(format="$%.2f"),
                },
            )



# ─────────────────────────────────────────────────────────────────────────────
# Close-trade helper
# ─────────────────────────────────────────────────────────────────────────────

def _insert_closing_transactions(
    engine,
    account_id: int,
    open_grp: pd.DataFrame,
    live_opt: dict,
    fallback_price: float = 0.0,
) -> None:
    """
    Insert closing (reverse) transactions for every leg in open_grp.
    Uses live option mid-price from live_opt per leg; falls back to fallback_price.
    """
    from sqlalchemy import text
    import uuid

    today = datetime.date.today()

    try:
        with engine.begin() as conn:
            for _, row in open_grp.iterrows():
                orig_dir  = str(row.get("Direction", "BUY")).upper()
                close_dir = "SELL" if orig_dir == "BUY" else "BUY"
                symbol    = str(row.get("Symbol", ""))
                orig_tgid = str(row.get("TradeGroupId", ""))
                # Use live mid-price for this leg; fall back to entry price if unavailable
                leg_price = (live_opt.get(symbol) or {}).get("price") or fallback_price or float(row.get("TransactionPrice", 0) or 0)
                conn.execute(text("""
                    INSERT INTO portfolio.[Transaction]
                        (BusinessDate, AccountId, TradeGroupId, StrategyName, SecurityId,
                         Direction, Quantity, TransactionPrice, Commission,
                         LegType, Source, Notes)
                    VALUES
                        (:bdate, :aid, :tgid, :strat, :secid,
                         :dir, :qty, :price, :comm,
                         :legtype, :src, :notes)
                """), {
                    "bdate":   today,
                    "aid":     account_id,
                    "tgid":    orig_tgid,
                    "strat":   row.get("StrategyName", ""),
                    "secid":   int(row["SecurityId"]),
                    "dir":     close_dir,
                    "qty":     float(row.get("Quantity", 0) or 0),
                    "price":   leg_price,
                    "comm":    _COMMISSION,
                    "legtype": row.get("LegType", ""),
                    "src":     "Close",
                    "notes":   f"CLOSE of {orig_tgid[:36]}",
                })
        return None
    except Exception as e:
        return str(e)


