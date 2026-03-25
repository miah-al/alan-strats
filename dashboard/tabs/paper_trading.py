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
    """
    if txns_df.empty:
        return {}

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
    """
    if txns_df.empty:
        return []

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

    # ── Account header + Refresh ──────────────────────────────────────────────
    hdr_col, btn_col = st.columns([6, 1])
    hdr_col.markdown(
        f"**Account:** {account_info['AccountName']} ({account_info['AccountType']})"
    )
    if btn_col.button("Refresh", key="pt_global_refresh"):
        for k in list(st.session_state.keys()):
            if k.startswith("pt_"):
                del st.session_state[k]
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

    # Realized P&L from closed groups
    total_realized = sum(r["P&L $"] for r in closed_rows) if closed_rows else 0.0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Open Trades", str(n_open))
    m2.metric("Unrealized P&L", "N/A*", help="Option quotes not available — see legs for stock Δ")
    m3.metric("Avg Days Open", f"{avg_days_open:.1f}" if avg_days_open is not None else "—")
    m4.metric("Total Realized P&L", f"${total_realized:+,.2f}")
    st.caption("* Option mid-price quotes are not available (IV-only data). Unrealized P&L cannot be computed.")

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
                st.session_state.pop("pt_live_prices", None)

            # Collect all underlyings for bulk fetch
            underlyings: set[str] = set()
            for tgid, grp in open_groups.items():
                if "Underlying" in grp.columns:
                    u = grp["Underlying"].dropna().iloc[0] if not grp["Underlying"].dropna().empty else None
                else:
                    u = None
                if u:
                    underlyings.add(str(u))

            # Fetch prices (cached in session state)
            if "pt_live_prices" not in st.session_state and api_key and underlyings:
                with st.spinner("Fetching live prices..."):
                    st.session_state["pt_live_prices"] = _fetch_stock_prices_bulk(api_key, list(underlyings))
            live_prices: dict[str, float | None] = st.session_state.get("pt_live_prices", {})

            today = datetime.date.today()

            for tgid, grp in open_groups.items():
                # Resolve underlying
                if "Underlying" in grp.columns and not grp["Underlying"].dropna().empty:
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

                tgid_short = str(tgid)[:8] + "…"

                expander_label = (
                    f"{underlying}  |  {strategy}  |  Signal: {signal_str}  |  "
                    f"Opened: {open_date}  |  {n_legs} legs  |  "
                    f"Net Entry: ${net_entry:+.2f}  |  Stock: {stock_delta_str}"
                )

                with st.expander(expander_label, expanded=False):
                    # Legs table
                    leg_rows = []
                    for _, r in grp.iterrows():
                        leg_rows.append({
                            "LegType":      r.get("LegType", "—"),
                            "Symbol":       r.get("Symbol", "—"),
                            "Strike":       r.get("Strike"),
                            "Expiry":       r.get("Expiration"),
                            "Direction":    r.get("Direction", "—"),
                            "Qty":          r.get("Quantity"),
                            "Entry Price":  r.get("TransactionPrice"),
                            "Current Price": stock_price if str(r.get("SecurityType", "")).lower() in ("equity", "etf") else None,
                            "P&L*":         "N/A",
                        })
                    legs_df = pd.DataFrame(leg_rows)
                    st.dataframe(
                        legs_df,
                        hide_index=True,
                        use_container_width=True,
                        column_config={
                            "Entry Price":   cc.NumberColumn(format="$%.4f"),
                            "Current Price": cc.NumberColumn(format="$%.2f"),
                            "Strike":        cc.NumberColumn(format="$%.1f"),
                        },
                    )
                    st.caption(f"TradeGroupId: {tgid}")

                    # Close Trade button
                    close_key = f"pt_close_{tgid}"
                    confirm_key = f"pt_close_confirm_{tgid}"

                    if st.session_state.get(confirm_key):
                        st.warning("Confirm close? This will insert closing transactions.")
                        exit_price_input = st.number_input(
                            "Exit price (stock/proxy)", min_value=0.0,
                            value=float(stock_price) if stock_price else 0.0,
                            key=f"pt_exit_price_{tgid}",
                        )
                        cc1, cc2 = st.columns([1, 4])
                        if cc1.button("Confirm Close", key=f"pt_close_yes_{tgid}", type="primary"):
                            _insert_closing_transactions(engine, account_id, grp, exit_price_input)
                            st.session_state.pop(confirm_key, None)
                            st.session_state.pop("pt_live_prices", None)
                            st.success("Closing transactions inserted.")
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
            closed_df = pd.DataFrame(closed_rows)
            closed_df["Return%"] = closed_df.apply(
                lambda r: (r["P&L $"] / abs(r["Net Entry"]) * 100)
                if r["Net Entry"] != 0 else None,
                axis=1,
            )
            display_cols = ["Underlying", "Strategy", "Open Date", "Close Date",
                            "Net Entry", "Net Exit", "P&L $", "Return%"]
            st.dataframe(
                closed_df[display_cols],
                hide_index=True,
                use_container_width=True,
                column_config={
                    "Net Entry": cc.NumberColumn(format="$%.2f"),
                    "Net Exit":  cc.NumberColumn(format="$%.2f"),
                    "P&L $":     cc.NumberColumn(format="$%.2f"),
                    "Return%":   cc.NumberColumn(format="%.2f%%"),
                },
            )

    # ── TAB: All Transactions ─────────────────────────────────────────────────
    with tab_txns:
        st.subheader("All Transactions")

        if txns_df.empty:
            st.info("No transactions found.")
        else:
            display_df = txns_df.copy()
            if "TradeGroupId" in display_df.columns:
                display_df["TradeGroup"] = display_df["TradeGroupId"].astype(str).str[:12] + "…"

            show_cols = [c for c in [
                "BusinessDate", "Underlying", "Symbol", "LegType",
                "Direction", "Quantity", "TransactionPrice", "Commission",
                "StrategyName", "TradeGroup", "Notes",
            ] if c in display_df.columns]

            st.dataframe(
                display_df[show_cols],
                hide_index=True,
                use_container_width=True,
                column_config={
                    "TransactionPrice": cc.NumberColumn(format="$%.4f"),
                    "Commission":       cc.NumberColumn(format="$%.2f"),
                },
            )
            st.caption(f"{len(display_df)} transaction(s) total")

    # ── TAB: Performance ──────────────────────────────────────────────────────
    with tab_perf:
        st.subheader("Performance")

        if not closed_rows:
            st.info("No closed trades available for performance analysis.")
        else:
            closed_df = pd.DataFrame(closed_rows)

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
                height=350,
                margin=dict(t=40, b=20, l=0, r=0),
                xaxis_title=None,
                yaxis_title="Total P&L ($)",
            )
            st.plotly_chart(fig_bar, use_container_width=True)

            # Cumulative P&L over time
            closed_sorted = closed_df.dropna(subset=["Close Date"]).sort_values("Close Date")
            if not closed_sorted.empty:
                closed_sorted = closed_sorted.copy()
                closed_sorted["Cumulative P&L"] = closed_sorted["P&L $"].cumsum()
                fig_line = go.Figure(go.Scatter(
                    x=closed_sorted["Close Date"],
                    y=closed_sorted["Cumulative P&L"],
                    mode="lines+markers",
                    line=dict(color="#5c6bc0", width=2),
                    fill="tozeroy",
                    fillcolor="rgba(92,107,192,0.08)",
                ))
                fig_line.update_layout(
                    template="plotly_dark",
                    title="Cumulative Realized P&L",
                    height=300,
                    margin=dict(t=40, b=20, l=0, r=0),
                    xaxis_title=None,
                    yaxis_title="Cumulative P&L ($)",
                )
                st.plotly_chart(fig_line, use_container_width=True)

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
                use_container_width=True,
                column_config={
                    "Win Rate":  cc.NumberColumn(format="%.1f%%"),
                    "Avg P&L":   cc.NumberColumn(format="$%.2f"),
                    "Total P&L": cc.NumberColumn(format="$%.2f"),
                },
            )

    st.markdown("---")

    # ─────────────────────────────────────────────────────────────────────────
    # ETF Rotation Strategies (Legacy) — collapsed expander
    # ─────────────────────────────────────────────────────────────────────────
    with st.expander("ETF Rotation Strategies (Legacy)", expanded=False):
        _render_etf_rotation(engine)


# ─────────────────────────────────────────────────────────────────────────────
# Close-trade helper
# ─────────────────────────────────────────────────────────────────────────────

def _insert_closing_transactions(engine, account_id: int, open_grp: pd.DataFrame, exit_price: float) -> None:
    """
    Insert closing (reverse) transactions for every leg in open_grp.
    Closing direction is the reverse of the opening direction.
    Uses exit_price as TransactionPrice for all legs (proxy).
    Notes column is set to 'CLOSE'.
    """
    from sqlalchemy import text
    import uuid

    today = datetime.date.today()
    close_group_id = str(uuid.uuid4())

    try:
        with engine.begin() as conn:
            for _, row in open_grp.iterrows():
                orig_dir = str(row.get("Direction", "BUY")).upper()
                close_dir = "SELL" if orig_dir == "BUY" else "BUY"
                conn.execute(text("""
                    INSERT INTO portfolio.Transaction
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
                    "tgid":    close_group_id,
                    "strat":   row.get("StrategyName", ""),
                    "secid":   int(row["SecurityId"]),
                    "dir":     close_dir,
                    "qty":     float(row.get("Quantity", 0) or 0),
                    "price":   exit_price,
                    "comm":    _COMMISSION,
                    "legtype": row.get("LegType", ""),
                    "src":     "Close",
                    "notes":   f"CLOSE of {str(row.get('TradeGroupId', ''))[:36]}",
                })
    except Exception as e:
        st.error(f"Failed to insert closing transactions: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# ETF rotation legacy section (preserved from original)
# ─────────────────────────────────────────────────────────────────────────────

def _classify_regime(engine) -> dict:
    from sqlalchemy import text

    today = datetime.date.today()

    with engine.connect() as c:
        spy_rows = c.execute(text("""
            SELECT TOP 60 pb.BarDate, pb.[Close]
            FROM mkt.PriceBar pb
            JOIN mkt.Ticker tk ON tk.TickerId = pb.TickerId
            WHERE tk.Symbol = 'SPY' AND pb.BarDate <= :today
            ORDER BY pb.BarDate DESC
        """), {"today": today}).fetchall()

        macro_rows = c.execute(text("""
            SELECT TOP 60 BarDate, Rate10Y
            FROM mkt.MacroBar
            WHERE BarDate <= :today AND Rate10Y IS NOT NULL
            ORDER BY BarDate DESC
        """), {"today": today}).fetchall()

    if not spy_rows or not macro_rows:
        return {"regime": "Transition", "spy_close": None, "rate10y": None,
                "rate_change_20d": None, "spy_return_20d": None, "spy_above_ma50": None,
                "error": "Insufficient market data"}

    spy_df = pd.DataFrame(spy_rows, columns=["date", "close"]).sort_values("date")
    spy_df["close"] = pd.to_numeric(spy_df["close"])

    macro_df = pd.DataFrame(macro_rows, columns=["date", "rate10y"]).sort_values("date")
    macro_df["rate10y"] = pd.to_numeric(macro_df["rate10y"])

    spy_close = spy_df["close"].values
    spy_latest = float(spy_close[-1])

    n_spy = len(spy_close)
    spy_return_20d = None
    if n_spy >= 21:
        spy_return_20d = (spy_close[-1] / spy_close[-21] - 1)

    spy_ma50 = float(np.mean(spy_close)) if n_spy >= 20 else None
    spy_above_ma50 = (spy_latest > spy_ma50) if spy_ma50 is not None else None

    rates = macro_df["rate10y"].values
    rate_latest = float(rates[-1])
    rate_change_20d = None
    n_rates = len(rates)
    if n_rates >= 21:
        rate_change_20d = float(rates[-1] - rates[-21])

    yield_thr  = 0.002
    return_thr = 0.03
    fear_rate_threshold = 0.035

    regime = "Transition"
    if rate_change_20d is not None and spy_return_20d is not None:
        above_ma = bool(spy_above_ma50) if spy_above_ma50 is not None else False
        rc = rate_change_20d
        sr = spy_return_20d
        r10y = rate_latest

        if rc > yield_thr and sr > return_thr:
            regime = "Growth"
        elif rc > yield_thr and sr < -return_thr:
            regime = "Inflation" if not above_ma else "Transition"
        elif rc < -yield_thr and sr < -return_thr:
            if above_ma:
                regime = "Transition"
            elif r10y > fear_rate_threshold:
                regime = "Fear-HighRate"
            else:
                regime = "Fear"
        elif rc < -yield_thr and sr > return_thr:
            regime = "Risk-On"

    return {
        "regime":           regime,
        "spy_close":        spy_latest,
        "rate10y":          rate_latest,
        "rate_change_20d":  rate_change_20d,
        "spy_return_20d":   spy_return_20d,
        "spy_above_ma50":   spy_above_ma50,
        "error":            None,
    }


def _get_vix_from_db(engine) -> float | None:
    from sqlalchemy import text
    with engine.connect() as c:
        row = c.execute(text("""
            SELECT TOP 1 pb.[Close]
            FROM mkt.PriceBar pb
            JOIN mkt.Ticker tk ON tk.TickerId = pb.TickerId
            WHERE tk.Symbol = 'VIX'
            ORDER BY pb.BarDate DESC
        """)).fetchone()
    return float(row[0]) if row else None


def _get_signal_for_strategy(slug: str, engine) -> dict:
    try:
        from alan_trader.strategies.registry import get_strategy
        strategy = get_strategy(slug)
    except Exception as e:
        return {"spy_weight": 0.6, "tlt_weight": 0.3, "label": "Transition",
                "metadata": {}, "error": str(e)}

    try:
        snapshot: dict = {}

        if slug in ("rates_spy_rotation", "rates_spy_rotation_options"):
            rdata = _classify_regime(engine)
            snapshot["regime"] = rdata.get("regime", "Transition")
            snapshot["spy_price"] = rdata.get("spy_close")
            snapshot["rate_10y"] = rdata.get("rate10y")
            extra_display = rdata
        else:
            vix = _get_vix_from_db(engine)
            snapshot["vix"] = vix or 20.0
            extra_display = {"vix": vix}

        signal = strategy.generate_signal(snapshot)
        meta   = signal.metadata or {}

        spy_w = float(meta.get("spy_weight", signal.position_size_pct or 0.6))
        tlt_w = float(meta.get("tlt_weight", 0.0))
        label = meta.get("regime_label") or meta.get("regime") or signal.signal

        return {
            "spy_weight": spy_w,
            "tlt_weight": tlt_w,
            "label":      label,
            "metadata":   {**extra_display, **meta},
            "error":      None,
        }
    except Exception as e:
        return {"spy_weight": 0.6, "tlt_weight": 0.3, "label": "Transition",
                "metadata": {}, "error": str(e)}


def _get_latest_price(engine, symbol: str) -> float | None:
    from sqlalchemy import text
    with engine.connect() as c:
        row = c.execute(text("""
            SELECT TOP 1 pb.[Close]
            FROM mkt.PriceBar pb
            JOIN mkt.Ticker tk ON tk.TickerId = pb.TickerId
            WHERE tk.Symbol = :sym
            ORDER BY pb.BarDate DESC
        """), {"sym": symbol}).fetchone()
    return float(row[0]) if row else None


def _build_alloc_table(engine, account_id: int, spy_w: float, tlt_w: float,
                       nav: float, holdings_df: pd.DataFrame,
                       spy_price: float | None, tlt_price: float | None) -> pd.DataFrame:
    cash_w = max(0.0, 1.0 - spy_w - tlt_w)

    from alan_trader.db.portfolio_client import get_security_id
    spy_id  = get_security_id(engine, "SPY")
    tlt_id  = get_security_id(engine, "TLT")
    cash_id = get_security_id(engine, "CASH")

    def _held_shares(sec_id):
        if sec_id is None or holdings_df.empty:
            return 0.0
        row = holdings_df[holdings_df["SecurityId"] == sec_id]
        return float(row.iloc[0]["Shares"]) if not row.empty else 0.0

    rows = []
    for symbol, weight, price, sec_id in [
        ("SPY",  spy_w,  spy_price,  spy_id),
        ("TLT",  tlt_w,  tlt_price,  tlt_id),
        ("CASH", cash_w, 1.0,        cash_id),
    ]:
        target_dollar   = nav * weight
        held            = _held_shares(sec_id)
        current_val     = held * (price or 0.0)
        diff            = current_val - target_dollar

        if symbol == "CASH":
            action = "—"
        elif price and price > 0:
            shares_diff = diff / price
            if abs(shares_diff) < 0.5:
                action = "—"
            elif shares_diff < 0:
                action = f"BUY {abs(math.floor(shares_diff))} sh"
            else:
                action = f"SELL {math.floor(shares_diff)} sh"
        else:
            action = "No price"

        rows.append({
            "Security":       symbol,
            "Target %":       f"{weight*100:.0f}%",
            "Target $":       f"${target_dollar:,.0f}",
            "Shares Held":    f"{held:.2f}" if symbol != "CASH" else "—",
            "Current Value":  f"${current_val:,.2f}",
            "Difference":     f"${diff:+,.2f}",
            "Action":         action,
            "_target_dollar": target_dollar,
            "_held":          held,
            "_price":         price or 0.0,
            "_sec_id":        sec_id,
            "_diff_shares":   (diff / price) if (price and price > 0 and symbol != "CASH") else 0.0,
        })
    return pd.DataFrame(rows)


def _execute_rebalance(engine, account_id: int, alloc_df: pd.DataFrame,
                       regime: str, strategy_name: str = "rates_spy_rotation") -> list[str]:
    from alan_trader.db.portfolio_client import (
        get_security_id, record_transaction, upsert_holding,
        insert_position, close_position, upsert_balance, get_open_positions
    )

    today    = datetime.date.today()
    cash_id  = get_security_id(engine, "CASH")
    summary  = []

    cash_row = alloc_df[alloc_df["Security"] == "CASH"].iloc[0]
    current_cash = float(cash_row["_held"])

    for _, row in alloc_df.iterrows():
        symbol    = row["Security"]
        sec_id    = row["_sec_id"]
        price     = float(row["_price"])
        held      = float(row["_held"])
        diff_sh   = float(row["_diff_shares"])
        target_d  = float(row["_target_dollar"])

        if symbol == "CASH" or sec_id is None or abs(diff_sh) < 0.5:
            continue

        if diff_sh < 0:
            shares_to_buy = abs(math.floor(diff_sh))
            cost = shares_to_buy * price + _COMMISSION
            if cost > current_cash:
                shares_to_buy = max(0, math.floor((current_cash - _COMMISSION) / price))
                if shares_to_buy == 0:
                    summary.append(f"Skipped BUY {symbol}: insufficient cash")
                    continue
                cost = shares_to_buy * price + _COMMISSION

            new_held = held + shares_to_buy
            if held > 0:
                old_cost_total = held * price
                new_avg_cost = (old_cost_total + shares_to_buy * price) / new_held
            else:
                new_avg_cost = price

            pos_id = insert_position(
                engine, account_id, sec_id, "etf_rotation",
                quantity=float(shares_to_buy),
                open_date=today, avg_entry_price=price,
                commission=_COMMISSION, regime=regime,
                strategy_name=strategy_name, source="paper"
            )
            record_transaction(
                engine, account_id, sec_id, today, "BUY",
                amount=-(cost), quantity=float(shares_to_buy),
                price=price, commission=_COMMISSION,
                position_id=pos_id, regime=regime,
                strategy_name=strategy_name
            )
            upsert_holding(engine, account_id, sec_id, new_held, new_avg_cost, price)
            current_cash -= cost
            summary.append(f"BUY {shares_to_buy} {symbol} @ ${price:.2f} = ${shares_to_buy*price:,.2f}")

        else:
            shares_to_sell = min(math.floor(diff_sh), math.floor(held))
            if shares_to_sell <= 0:
                continue
            proceeds = shares_to_sell * price - _COMMISSION

            open_pos = get_open_positions(engine, account_id)
            if not open_pos.empty:
                sec_pos = open_pos[
                    (open_pos["SecurityId"].astype(str) == str(sec_id)) &
                    (open_pos["Status"] == "open") if "Status" in open_pos.columns
                    else open_pos["SecurityId"].astype(str) == str(sec_id)
                ] if "SecurityId" in open_pos.columns else pd.DataFrame()

                remaining = shares_to_sell
                for _, prow in sec_pos.iterrows():
                    if remaining <= 0:
                        break
                    pos_qty = float(prow.get("Quantity", 0))
                    entry_p = float(prow.get("AvgEntryPrice", price))
                    close_qty = min(pos_qty, remaining)
                    pnl = (price - entry_p) * close_qty - _COMMISSION
                    close_position(
                        engine, int(prow["PositionId"]), today,
                        avg_exit_price=price, realized_pnl=round(pnl, 2)
                    )
                    remaining -= close_qty

            record_transaction(
                engine, account_id, sec_id, today, "SELL",
                amount=proceeds, quantity=float(shares_to_sell),
                price=price, commission=_COMMISSION,
                regime=regime, strategy_name=strategy_name
            )
            new_held = max(0.0, held - shares_to_sell)
            if new_held == 0:
                upsert_holding(engine, account_id, sec_id, 0.0, 0.0)
            else:
                upsert_holding(engine, account_id, sec_id, new_held, price, price)
            current_cash += proceeds
            summary.append(f"SELL {shares_to_sell} {symbol} @ ${price:.2f} = ${proceeds:,.2f}")

    if cash_id is not None:
        upsert_holding(engine, account_id, cash_id, current_cash, 1.0, 1.0)
        record_transaction(
            engine, account_id, cash_id, today, "FEE" if current_cash < _INITIAL_CASH else "DEPOSIT",
            amount=current_cash, notes="Cash balance after rebalance"
        ) if not summary else None

    from alan_trader.db.portfolio_client import get_holdings
    holdings_after = get_holdings(engine, account_id)
    invested_val = 0.0
    if not holdings_after.empty:
        for _, hr in holdings_after.iterrows():
            if cash_id is not None and int(hr["SecurityId"]) == cash_id:
                continue
            mv = hr["MarketValue"]
            if mv is not None and not (isinstance(mv, float) and math.isnan(mv)):
                invested_val += float(mv)

    upsert_balance(engine, account_id, today, cash=current_cash, portfolio_val=invested_val)
    return summary


def _get_cash_balance(engine, account_id: int) -> float:
    from alan_trader.db.portfolio_client import get_security_id, get_holdings
    cash_id = get_security_id(engine, "CASH")
    if cash_id is None:
        return 0.0
    holdings = get_holdings(engine, account_id)
    if holdings.empty:
        return 0.0
    row = holdings[holdings["SecurityId"] == cash_id]
    if row.empty:
        return 0.0
    return float(row.iloc[0]["Shares"])


def _seed_initial_deposit(engine, account_id: int) -> None:
    from alan_trader.db.portfolio_client import (
        get_transactions, get_security_id, record_transaction, upsert_holding, upsert_balance
    )
    txns = get_transactions(engine, account_id, limit=1)
    if not txns.empty:
        return

    today = datetime.date.today()
    cash_id = get_security_id(engine, "CASH")
    if cash_id is None:
        st.error("CASH ticker not found. Run the paper trading migration first.")
        return

    record_transaction(
        engine, account_id, cash_id, today, "DEPOSIT",
        amount=_INITIAL_CASH, notes="Initial paper trading seed"
    )
    upsert_holding(engine, account_id, cash_id, _INITIAL_CASH, 1.0, current_price=1.0)
    upsert_balance(engine, account_id, today, cash=_INITIAL_CASH, portfolio_val=0.0)


def _compute_nav(engine, account_id: int) -> dict:
    from alan_trader.db.portfolio_client import get_holdings, get_security_id

    holdings = get_holdings(engine, account_id)
    cash_id  = get_security_id(engine, "CASH")

    cash_val = 0.0
    invested = 0.0

    if not holdings.empty:
        for _, row in holdings.iterrows():
            sid = int(row["SecurityId"])
            if cash_id is not None and sid == cash_id:
                cash_val += float(row["Shares"])
            else:
                mv = row["MarketValue"]
                if mv is not None and not (isinstance(mv, float) and math.isnan(mv)):
                    invested += float(mv)

    total_nav = cash_val + invested
    return {"nav": total_nav, "cash": cash_val, "invested": invested}


def _render_etf_rotation(engine) -> None:
    """Render the legacy ETF rotation paper trading section."""
    try:
        from alan_trader.db.portfolio_client import (
            get_holdings, get_balance_history,
            get_transactions, get_security_id, upsert_holding, upsert_balance
        )
    except Exception as e:
        st.warning(f"Legacy portfolio client unavailable: {e}")
        return

    try:
        from sqlalchemy import text as _t
        with engine.connect() as _c:
            row = _c.execute(_t(
                "SELECT TOP 1 AccountId FROM portfolio.Account WHERE Status='Active' ORDER BY AccountId"
            )).fetchone()
        account_id = row[0] if row else 1
        _seed_initial_deposit(engine, account_id)
    except Exception as e:
        st.warning(f"Could not initialise legacy account: {e}")
        return

    # Strategy selector
    active_eligible = {
        slug: label for slug, label in _ELIGIBLE_STRATEGIES.items()
        if slug in __import__("alan_trader.strategies.registry",
                              fromlist=["STRATEGY_METADATA"]).STRATEGY_METADATA
        and __import__("alan_trader.strategies.registry",
                       fromlist=["STRATEGY_METADATA"]).STRATEGY_METADATA[slug].get("status") == "active"
    }
    slug_options = list(active_eligible.keys())
    slug_labels  = list(active_eligible.values())

    if not slug_options:
        st.info("No eligible ETF rotation strategies are active.")
        return

    sel_idx = st.selectbox(
        "Strategy",
        options=range(len(slug_options)),
        format_func=lambda i: slug_labels[i],
        key="pt_etf_strategy_slug_idx",
    )
    selected_slug = slug_options[sel_idx]
    st.caption(f"Running paper trades for **{slug_labels[sel_idx]}** (`{selected_slug}`)")
    st.markdown("---")

    # NAV header
    nav_data   = _compute_nav(engine, account_id)
    nav        = nav_data["nav"]
    cash       = nav_data["cash"]
    invested   = nav_data["invested"]

    bal_hist = get_balance_history(engine, account_id, days=365)
    initial  = _INITIAL_CASH
    total_return_pct = (nav / initial - 1) * 100 if initial > 0 else 0.0

    day_pnl = None
    if not bal_hist.empty and len(bal_hist) >= 2:
        prev_eq = float(bal_hist.iloc[-2]["TotalEquity"])
        cur_eq  = float(bal_hist.iloc[-1]["TotalEquity"])
        day_pnl = cur_eq - prev_eq

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("NAV",          f"${nav:,.2f}")
    c2.metric("Cash",         f"${cash:,.2f}")
    c3.metric("Invested",     f"${invested:,.2f}")
    c4.metric("Total Return", f"{total_return_pct:+.2f}%")
    c5.metric("Day P&L",      f"${day_pnl:+,.2f}" if day_pnl is not None else "—")

    st.markdown("---")

    # Strategy signal
    st.subheader("Current Signal")

    sig_cache_key = f"pt_etf_signal_{selected_slug}"
    if st.button("Refresh Signal", key="pt_etf_refresh_sig"):
        with st.spinner("Computing signal..."):
            st.session_state[sig_cache_key] = _get_signal_for_strategy(selected_slug, engine)

    sig = st.session_state.get(sig_cache_key)
    if sig is None:
        with st.spinner("Loading signal..."):
            sig = _get_signal_for_strategy(selected_slug, engine)
            st.session_state[sig_cache_key] = sig

    if sig.get("error"):
        st.warning(f"Signal unavailable: {sig['error']}")

    spy_w_target = sig["spy_weight"]
    tlt_w_target = sig["tlt_weight"]
    regime       = sig.get("label", "—")
    meta         = sig.get("metadata", {})

    sc1, sc2, sc3, sc4 = st.columns(4)
    sc1.metric("Signal / Regime", regime)
    sc2.metric("SPY Target", f"{spy_w_target*100:.0f}%")
    sc3.metric("TLT Target", f"{tlt_w_target*100:.0f}%")
    sc4.metric("Cash Target", f"{(1 - spy_w_target - tlt_w_target)*100:.0f}%")

    detail_items = []
    if "rate10y" in meta and meta["rate10y"]:
        detail_items.append(("10Y Yield", f"{meta['rate10y']*100:.2f}%"))
    if "rate_change_20d" in meta and meta["rate_change_20d"] is not None:
        detail_items.append(("Yield Δ 20d", f"{meta['rate_change_20d']*10000:+.1f} bps"))
    if "spy_return_20d" in meta and meta["spy_return_20d"] is not None:
        detail_items.append(("SPY Ret 20d", f"{meta['spy_return_20d']*100:+.2f}%"))
    if "vix" in meta and meta["vix"]:
        detail_items.append(("VIX", f"{meta['vix']:.1f}"))
    if detail_items:
        dc = st.columns(len(detail_items))
        for col, (lbl, val) in zip(dc, detail_items):
            col.metric(lbl, val)

    st.markdown("---")

    # Allocation table
    st.subheader("Allocation")

    spy_price = _get_latest_price(engine, "SPY")
    tlt_price = _get_latest_price(engine, "TLT")

    holdings = get_holdings(engine, account_id)

    for symbol, price in [("SPY", spy_price), ("TLT", tlt_price)]:
        sid = get_security_id(engine, symbol)
        if sid is not None and price is not None and not holdings.empty:
            row = holdings[holdings["SecurityId"] == sid]
            if not row.empty:
                shares = float(row.iloc[0]["Shares"])
                cost   = float(row.iloc[0]["AvgCostBasis"])
                upsert_holding(engine, account_id, sid, shares, cost, price)

    holdings = get_holdings(engine, account_id)

    alloc_df = _build_alloc_table(engine, account_id, spy_w_target, tlt_w_target,
                                  nav, holdings, spy_price, tlt_price)

    display_cols = ["Security", "Target %", "Target $", "Shares Held", "Current Value", "Difference", "Action"]
    st.dataframe(alloc_df[display_cols], use_container_width=True, hide_index=True)

    # Rebalance button
    needs_rebalance = any(
        row["Action"] not in ("—", "No price")
        for _, row in alloc_df.iterrows()
        if row["Security"] != "CASH"
    )

    if not needs_rebalance:
        st.info("Portfolio is at target allocation — no rebalance needed.")
    else:
        if "pt_etf_confirm_rebalance" not in st.session_state:
            st.session_state["pt_etf_confirm_rebalance"] = False

        if not st.session_state["pt_etf_confirm_rebalance"]:
            if st.button("Execute Rebalance", type="primary", key="pt_etf_rebalance_btn"):
                st.session_state["pt_etf_confirm_rebalance"] = True
                st.rerun()
        else:
            st.warning("Confirm rebalance? This will execute trades against the paper account.")
            col_yes, col_no = st.columns([1, 4])
            if col_yes.button("Yes, rebalance", type="primary", key="pt_etf_rebalance_yes"):
                st.session_state["pt_etf_confirm_rebalance"] = False
                st.session_state.pop(f"pt_etf_signal_{selected_slug}", None)
                with st.spinner("Executing rebalance..."):
                    summary = _execute_rebalance(engine, account_id, alloc_df,
                                                 regime, strategy_name=selected_slug)
                if summary:
                    st.success("Rebalance complete:")
                    for line in summary:
                        st.write(f"- {line}")
                else:
                    st.info("No trades executed.")
                st.rerun()
            if col_no.button("Cancel", key="pt_etf_rebalance_cancel"):
                st.session_state["pt_etf_confirm_rebalance"] = False
                st.rerun()

    st.markdown("---")

    # Transactions
    st.subheader("Transactions")
    txns = get_transactions(engine, account_id, limit=100)
    if txns.empty:
        st.info("No transactions yet.")
    else:
        show_cols = ["TransactionDate", "Symbol", "Action", "Quantity",
                     "Price", "Amount", "Commission", "Regime", "Notes"]
        show_cols = [c for c in show_cols if c in txns.columns]
        st.dataframe(txns[show_cols], use_container_width=True, hide_index=True)

    st.markdown("---")

    # NAV History
    st.subheader("NAV History")
    bal_hist = get_balance_history(engine, account_id, days=365)
    if bal_hist.empty:
        st.info("No balance history yet. Execute a rebalance to start tracking NAV.")
    else:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=bal_hist["BalanceDate"],
            y=bal_hist["TotalEquity"],
            mode="lines",
            name="NAV",
            line=dict(color="#5c6bc0", width=2),
            fill="tozeroy",
            fillcolor="rgba(92,107,192,0.08)",
        ))
        fig.add_hline(y=_INITIAL_CASH, line_dash="dash",
                      line_color="#546e7a", annotation_text="Initial $100K")
        fig.update_layout(
            template="plotly_dark",
            height=300,
            margin=dict(t=20, b=20, l=0, r=0),
            xaxis_title=None,
            yaxis_title="Total Equity ($)",
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)
