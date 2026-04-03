"""
engine/positions.py — UI-agnostic position and trade logic.

Extracted from dashboard/tabs/paper_trading.py so this logic
can be used independently of Streamlit.
"""
from __future__ import annotations

import datetime
import pandas as pd

# ── Constants ─────────────────────────────────────────────────────────────────

_INITIAL_CASH = 100_000.0
_COMMISSION   = 1.0   # per trade

# Strategies eligible for ETF paper trading (signal returns spy_weight / tlt_weight)
_ELIGIBLE_STRATEGIES: dict[str, str] = {
    "rates_spy_rotation":         "TLT / SPY Rotation",
    "rates_spy_rotation_options": "TLT / SPY Rotation (Options)",
    "gex_positioning":            "Dealer Gamma Exposure",
}


# ── DB helpers ────────────────────────────────────────────────────────────────

def get_account_info(engine, account_id: int = 1) -> dict:
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


def load_transactions(engine, account_id: int = 1) -> pd.DataFrame:
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


def get_open_trade_groups(txns_df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """
    Identify open trade groups. A TradeGroupId is open if there is no closing
    transaction. Closing transactions are identified by Notes containing 'CLOSE'
    (case-insensitive) or Source = 'Close'.
    Returns a dict mapping TradeGroupId -> subset DataFrame of that group's rows.
    Cash entries (SecurityType='cash') are excluded.
    """
    if txns_df.empty:
        return {}

    sec_type = txns_df.get("SecurityType", pd.Series(dtype=str)).fillna("").str.lower()
    leg_type  = txns_df.get("LegType",      pd.Series(dtype=str)).fillna("").str.lower()
    is_cash   = sec_type.isin(["cash"]) | leg_type.isin(["cashin", "cashout"])
    txns_df   = txns_df[~is_cash].copy()

    notes_col  = txns_df.get("Notes",  pd.Series(dtype=str)).fillna("").str.upper()
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


def get_closed_trade_groups(txns_df: pd.DataFrame) -> list[dict]:
    """
    Returns summary rows for closed trade groups.
    A group is closed if it has at least one closing transaction (Notes contains CLOSE).
    Cash entries (SecurityType='cash') are excluded.
    """
    if txns_df.empty:
        return []

    sec_type  = txns_df.get("SecurityType", pd.Series(dtype=str)).fillna("").str.lower()
    leg_type  = txns_df.get("LegType",      pd.Series(dtype=str)).fillna("").str.lower()
    is_cash   = sec_type.isin(["cash"]) | leg_type.isin(["cashin", "cashout"])
    txns_df   = txns_df[~is_cash].copy()

    notes_col  = txns_df.get("Notes",  pd.Series(dtype=str)).fillna("").str.upper()
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
        strategy   = group["StrategyName"].iloc[0] if not group.empty else "?"
        open_date  = opening["BusinessDate"].min() if not opening.empty else None
        close_date = closing["BusinessDate"].max() if not closing.empty else None

        def _signed_cost(sub: pd.DataFrame) -> float:
            total = 0.0
            for _, r in sub.iterrows():
                sign = -1.0 if str(r.get("Direction", "")).upper() == "BUY" else 1.0
                mult = float(r.get("Multiplier", 1) or 1)
                total += sign * float(r.get("Quantity", 0) or 0) * float(r.get("TransactionPrice", 0) or 0) * mult
            return total

        net_entry = _signed_cost(opening)
        net_exit  = _signed_cost(closing)
        pnl       = net_entry + net_exit

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


def load_balance_history(engine, account_id: int = 1) -> pd.DataFrame:
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


# ── Polygon price helpers ─────────────────────────────────────────────────────

def fetch_stock_price(api_key: str, symbol: str) -> float | None:
    try:
        from data.polygon_client import PolygonClient
        c = PolygonClient(api_key=api_key)
        snap = c.get_snapshot(symbol)
        return snap.get("day", {}).get("c") or snap.get("lastTrade", {}).get("p")
    except Exception:
        return None


def fetch_stock_prices_bulk(api_key: str, symbols: list[str]) -> dict[str, float | None]:
    """Fetch prices for multiple symbols, returning {symbol: price}."""
    prices: dict[str, float | None] = {}
    for sym in symbols:
        prices[sym] = fetch_stock_price(api_key, sym)
    return prices


def fetch_option_prices(api_key: str, legs_df: pd.DataFrame) -> dict[str, dict]:
    """
    Fetch current mid prices and IV for option legs using exact strike/expiry/type match.
    Returns {Symbol: {"price": float|None, "iv": float|None}}.
    """
    if not api_key:
        return {}
    from data.polygon_client import PolygonClient
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
                iv_raw  = r.get("iv")
                iv      = round(float(iv_raw) * 100, 2) if iv_raw is not None and iv_raw == iv_raw else None
                bid_val = round(float(bid), 4) if (bid is not None and bid == bid) else None
                ask_val = round(float(ask), 4) if (ask is not None and ask == ask) else None
                result[sym] = {"price": mid, "iv": iv, "bid": bid_val, "ask": ask_val}
        except Exception:
            pass
    return result


# ── Alert logic ───────────────────────────────────────────────────────────────

def compute_position_alerts(
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
        is_spread = any(x in sl for x in ("condor", "spread", "strangle", "butterfly"))
        if min_dte <= 0:
            if is_spread:
                alerts.append({"level": "error",
                               "msg": f"EXPIRED ({min_dte} DTE) — close now to avoid messy expiry fills. No assignment risk (defined-risk spread)."})
            else:
                alerts.append({"level": "error",
                               "msg": f"EXPIRED ({min_dte} DTE) — close immediately to avoid assignment."})
        elif min_dte <= 7:
            if is_spread:
                alerts.append({"level": "error",
                               "msg": f"{min_dte} DTE — close soon. Robinhood may auto-close near expiry; get ahead of it for a better fill."})
            else:
                alerts.append({"level": "error",
                               "msg": f"{min_dte} DTE — critical, close immediately (assignment risk)."})
        elif min_dte <= 21:
            alerts.append({"level": "warning",
                           "msg": f"{min_dte} DTE — theta decay accelerating, consider closing."})

    # ── P&L check ────────────────────────────────────────────────────────────
    if total_upnl is not None and net_entry != 0:
        has_options = any(
            str(r.get("SecurityType", "")).lower() == "option"
            for _, r in grp.iterrows()
        )
        if has_options:
            is_credit   = net_entry > 0
            is_debit    = net_entry <= 0
            is_equity   = False
            is_rotation = False
        else:
            is_credit   = False
            is_debit    = False
            is_rotation = any(x in sl for x in ("rotation", "tlt / spy", "spy rotation"))
            is_equity   = not is_rotation

        if is_credit:
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


# ── Trade execution ───────────────────────────────────────────────────────────

def insert_closing_transactions(
    engine,
    account_id: int,
    open_grp: pd.DataFrame,
    live_opt: dict,
    fallback_price: float = 0.0,
) -> str | None:
    """
    Insert closing (reverse) transactions for every leg in open_grp.
    Uses live option mid-price from live_opt per leg; falls back to fallback_price.
    Returns None on success, error string on failure.
    """
    from sqlalchemy import text

    today = datetime.date.today()

    try:
        with engine.begin() as conn:
            for _, row in open_grp.iterrows():
                orig_dir  = str(row.get("Direction", "BUY")).upper()
                close_dir = "SELL" if orig_dir == "BUY" else "BUY"
                symbol    = str(row.get("Symbol", ""))
                orig_tgid = str(row.get("TradeGroupId", ""))
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


def insert_open_ic_trade(
    engine,
    account_id: int,
    ticker: str,
    chain: dict,
    strategy_name: str = "iron_condor_rules",
    contracts: int = 1,
) -> str | None:
    """
    Insert a 4-leg Iron Condor opening trade into portfolio.[Transaction].
    Creates Security records if they don't exist.
    Returns None on success, error string on failure.
    """
    import uuid
    from sqlalchemy import text

    today  = datetime.date.today()
    tgid   = f"IRON-{ticker}-{uuid.uuid4().hex[:8].upper()}"
    exp    = str(chain["best_exp"])                  # "2026-05-15"
    exp_db = exp.replace("-", "")[2:]                # "260515"

    legs = [
        (chain["long_call_k"],  "call", "Buy",  chain["long_call_mid"],  "LongCall"),
        (chain["short_call_k"], "call", "Sell", chain["short_call_mid"], "ShortCall"),
        (chain["short_put_k"],  "put",  "Sell", chain["short_put_mid"],  "ShortPut"),
        (chain["long_put_k"],   "put",  "Buy",  chain["long_put_mid"],   "LongPut"),
    ]

    def _opt_symbol(strike: float, opt_type: str) -> str:
        cp = "C" if opt_type == "call" else "P"
        return f"{ticker}{exp_db}{cp}{int(strike * 1000):08d}"

    try:
        with engine.begin() as conn:
            for strike, opt_type, direction, mid, leg_type in legs:
                sym = _opt_symbol(strike, opt_type)

                # Find or insert Security
                row = conn.execute(text(
                    "SELECT SecurityId FROM portfolio.Security "
                    "WHERE Symbol = :s AND SecurityType = 'option'"
                ), {"s": sym}).fetchone()

                if row:
                    sec_id = row[0]
                else:
                    row = conn.execute(text(
                        "INSERT INTO portfolio.Security "
                        "(Symbol, Underlying, SecurityType, OptionType, Strike, Expiration, Multiplier) "
                        "OUTPUT INSERTED.SecurityId "
                        "VALUES (:s, :u, 'option', :ot, :k, :e, 100)"
                    ), {"s": sym, "u": ticker, "ot": opt_type, "k": strike, "e": exp}).fetchone()
                    sec_id = row[0]

                conn.execute(text("""
                    INSERT INTO portfolio.[Transaction]
                        (BusinessDate, AccountId, TradeGroupId, StrategyName,
                         SecurityId, Direction, Quantity, TransactionPrice,
                         Commission, LegType, Source, Notes)
                    VALUES (:d, :aid, :tg, :strat, :sid, :dir, :qty, :px,
                            :comm, :lt, 'Screener', :notes)
                """), {
                    "d":     today,
                    "aid":   account_id,
                    "tg":    tgid,
                    "strat": strategy_name,
                    "sid":   int(sec_id),
                    "dir":   direction,
                    "qty":   float(contracts),
                    "px":    float(mid or 0),
                    "comm":  _COMMISSION,
                    "lt":    leg_type,
                    "notes": f"IC {ticker} {exp} opened from Screener",
                })
        return None
    except Exception as e:
        return str(e)
