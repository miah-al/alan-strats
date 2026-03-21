from __future__ import annotations

import datetime
import math
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

_INITIAL_CASH = 100_000.0
_COMMISSION   = 1.0   # per trade

# Strategies eligible for ETF paper trading (signal returns spy_weight / tlt_weight)
_ELIGIBLE_STRATEGIES: dict[str, str] = {
    "rates_spy_rotation":         "TLT / SPY Rotation",
    "rates_spy_rotation_options": "TLT / SPY Rotation (Options)",
    "gex_positioning":            "Dealer Gamma Exposure",
}


def _get_engine():
    from alan_trader.db.client import get_engine
    return get_engine()


def _classify_regime(engine) -> dict:
    from sqlalchemy import text

    today = datetime.date.today()
    from_d = today - datetime.timedelta(days=120)

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
    """
    Build a market snapshot from DB, call strategy.generate_signal(), and return
    a normalised dict:
      spy_weight  (float 0-1)
      tlt_weight  (float 0-1)
      label       (str — regime / signal label)
      metadata    (dict — strategy-specific extras for display)
      error       (str | None)
    """
    try:
        from alan_trader.strategies.registry import get_strategy
        strategy = get_strategy(slug)
    except Exception as e:
        return {"spy_weight": 0.6, "tlt_weight": 0.3, "label": "Transition",
                "metadata": {}, "error": str(e)}

    try:
        # Build snapshot appropriate for the strategy
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
            "Security":      symbol,
            "Target %":      f"{weight*100:.0f}%",
            "Target $":      f"${target_dollar:,.0f}",
            "Shares Held":   f"{held:.2f}" if symbol != "CASH" else "—",
            "Current Value": f"${current_val:,.2f}",
            "Difference":    f"${diff:+,.2f}",
            "Action":        action,
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
            # Need to BUY
            shares_to_buy = abs(math.floor(diff_sh))
            cost = shares_to_buy * price + _COMMISSION
            if cost > current_cash:
                shares_to_buy = max(0, math.floor((current_cash - _COMMISSION) / price))
                if shares_to_buy == 0:
                    summary.append(f"Skipped BUY {symbol}: insufficient cash")
                    continue
                cost = shares_to_buy * price + _COMMISSION

            new_held   = held + shares_to_buy
            # weighted average cost
            if held > 0:
                old_cost_total = held * price  # approximate; we don't store avg cost per symbol here
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
            # Need to SELL
            shares_to_sell = min(math.floor(diff_sh), math.floor(held))
            if shares_to_sell <= 0:
                continue
            proceeds = shares_to_sell * price - _COMMISSION

            # Close any open positions for this security (approximate FIFO)
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

    # Update cash holding
    if cash_id is not None:
        upsert_holding(engine, account_id, cash_id, current_cash, 1.0, 1.0)
        record_transaction(
            engine, account_id, cash_id, today, "FEE" if current_cash < _INITIAL_CASH else "DEPOSIT",
            amount=current_cash, notes="Cash balance after rebalance"
        ) if not summary else None

    # Refresh invested value for balance update
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


def render() -> None:
    st.header("Paper Trading")

    try:
        engine = _get_engine()
    except Exception as e:
        st.error(f"Cannot connect to database: {e}")
        return

    from alan_trader.db.portfolio_client import (
        ensure_default_account, get_holdings, get_balance_history,
        get_transactions, get_security_id, upsert_holding, upsert_balance
    )

    account_id = ensure_default_account(engine)
    _seed_initial_deposit(engine, account_id)

    # ── Strategy selector ─────────────────────────────────────────────────────
    active_eligible = {
        slug: label for slug, label in _ELIGIBLE_STRATEGIES.items()
        if slug in __import__("alan_trader.strategies.registry",
                              fromlist=["STRATEGY_METADATA"]).STRATEGY_METADATA
        and __import__("alan_trader.strategies.registry",
                       fromlist=["STRATEGY_METADATA"]).STRATEGY_METADATA[slug].get("status") == "active"
    }
    slug_options = list(active_eligible.keys())
    slug_labels  = list(active_eligible.values())

    sel_idx = st.selectbox(
        "Strategy",
        options=range(len(slug_options)),
        format_func=lambda i: slug_labels[i],
        key="pt_strategy_slug_idx",
    )
    selected_slug = slug_options[sel_idx]
    st.caption(f"Running paper trades for **{slug_labels[sel_idx]}** (`{selected_slug}`)")
    st.markdown("---")

    # ── NAV header ────────────────────────────────────────────────────────────
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

    # ── Strategy signal ────────────────────────────────────────────────────────
    st.subheader("Current Signal")

    sig_cache_key = f"pt_signal_{selected_slug}"
    if st.button("Refresh Signal", key="pt_refresh_sig"):
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

    # Strategy-specific detail metrics
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

    # ── Allocation table ──────────────────────────────────────────────────────
    st.subheader("Allocation")

    spy_price = _get_latest_price(engine, "SPY")
    tlt_price = _get_latest_price(engine, "TLT")

    holdings = get_holdings(engine, account_id)

    # Update current prices in holdings
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
    st.dataframe(alloc_df[display_cols], width="stretch", hide_index=True)

    # ── Rebalance button ──────────────────────────────────────────────────────
    needs_rebalance = any(
        row["Action"] not in ("—", "No price")
        for _, row in alloc_df.iterrows()
        if row["Security"] != "CASH"
    )

    if not needs_rebalance:
        st.info("Portfolio is at target allocation — no rebalance needed.")
    else:
        if "pt_confirm_rebalance" not in st.session_state:
            st.session_state["pt_confirm_rebalance"] = False

        if not st.session_state["pt_confirm_rebalance"]:
            if st.button("Execute Rebalance", type="primary"):
                st.session_state["pt_confirm_rebalance"] = True
                st.rerun()
        else:
            st.warning("Confirm rebalance? This will execute trades against the paper account.")
            col_yes, col_no = st.columns([1, 4])
            if col_yes.button("Yes, rebalance", type="primary"):
                st.session_state["pt_confirm_rebalance"] = False
                st.session_state.pop(f"pt_signal_{selected_slug}", None)
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
            if col_no.button("Cancel"):
                st.session_state["pt_confirm_rebalance"] = False
                st.rerun()

    st.markdown("---")

    # ── Transactions ──────────────────────────────────────────────────────────
    st.subheader("Transactions")
    txns = get_transactions(engine, account_id, limit=100)
    if txns.empty:
        st.info("No transactions yet.")
    else:
        show_cols = ["TransactionDate", "Symbol", "Action", "Quantity",
                     "Price", "Amount", "Commission", "Regime", "Notes"]
        show_cols = [c for c in show_cols if c in txns.columns]
        st.dataframe(txns[show_cols], width="stretch", hide_index=True)

    st.markdown("---")

    # ── NAV History ──────────────────────────────────────────────────────────
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
        st.plotly_chart(fig, width="stretch")
