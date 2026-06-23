"""
app/pages/paper_trading/data.py — pure data + pricing logic.

No Dash @callback decorators here: just transaction loading, Black-Scholes
pricing/greeks, net-entry math, the risk-matrix computation and the simple
open-trade-group grouping used by the Risk tab. Reorganised verbatim from the
original monolithic paper_trading.py.
"""
from __future__ import annotations

import math
import datetime
import pandas as pd
import numpy as np

from dash import html
from app import theme as T

_ACCOUNT_ID = 1


def _pretty_strategy(name: str) -> str:
    """Map a strategy slug (e.g. 'hmm_regime') to its display label
    (e.g. 'HMM Regime Classifier'). Falls back to the input unchanged
    if no mapping is registered."""
    if not name:
        return name
    try:
        from app.pages.strategies.registry import _SLUG_TO_LABEL
        return _SLUG_TO_LABEL.get(str(name), str(name))
    except Exception:
        return str(name)


def _get_engine():
    from db.client import get_engine
    return get_engine()


def _load_data():
    """Returns (open_groups, closed_rows, txns_df) or empty on failure."""
    from engine.positions import load_transactions, get_open_trade_groups, get_closed_trade_groups
    try:
        engine = _get_engine()
        txns   = load_transactions(engine, _ACCOUNT_ID)
        if txns.empty:
            return {}, [], pd.DataFrame()
        return get_open_trade_groups(txns), get_closed_trade_groups(txns), txns
    except Exception:
        return {}, [], pd.DataFrame()


def _net_entry(grp: pd.DataFrame) -> float:
    total = 0.0
    for _, r in grp.iterrows():
        sign = -1.0 if str(r.get("Direction", "")).upper() == "BUY" else 1.0
        mult = float(r.get("Multiplier", 1) or 1)
        total += sign * float(r.get("Quantity", 0) or 0) \
                      * float(r.get("TransactionPrice", 0) or 0) * mult
    return total


# ── Black-Scholes helper ──────────────────────────────────────────────────────

def bs_val(S: float, K: float, T: float, iv: float, otype: str) -> float:
    """Black-Scholes option price. otype: 'call' or 'put'."""
    from scipy.stats import norm as _norm
    r = 0.045
    if T <= 0 or iv <= 0:
        return max(0.0, (S - K) if otype == "call" else (K - S))
    d1 = (math.log(S / K) + (r + 0.5 * iv ** 2) * T) / (iv * math.sqrt(T))
    d2 = d1 - iv * math.sqrt(T)
    if otype == "call":
        return S * _norm.cdf(d1) - K * math.exp(-r * T) * _norm.cdf(d2)
    else:
        return K * math.exp(-r * T) * _norm.cdf(-d2) - S * _norm.cdf(-d1)


# ── Risk tab: Black-Scholes engine ────────────────────────────────────────────

def _bs_full(S: float, K: float, T: float, r: float, sigma: float, otype: str):
    """
    Returns (price, delta, gamma, vega_per1pct, theta_per_day, vanna_per1pct).
    All Greeks are per-share (multiply by qty × mult for dollar Greeks).
    vega / vanna are per 1 percentage-point move in IV.
    """
    from scipy.stats import norm
    if T <= 1e-6:
        intrinsic = max(S - K, 0.0) if otype == "call" else max(K - S, 0.0)
        delta = (1.0 if S > K else 0.0) if otype == "call" else (-1.0 if S < K else 0.0)
        return intrinsic, delta, 0.0, 0.0, 0.0, 0.0
    if sigma <= 1e-6 or S <= 0 or K <= 0:
        intrinsic = max(S - K, 0.0) if otype == "call" else max(K - S, 0.0)
        return intrinsic, 0.0, 0.0, 0.0, 0.0, 0.0
    sqT  = np.sqrt(T)
    d1   = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqT)
    d2   = d1 - sigma * sqT
    φd1  = norm.pdf(d1)
    disc = np.exp(-r * T)
    if otype == "call":
        price = S * norm.cdf(d1) - K * disc * norm.cdf(d2)
        delta = norm.cdf(d1)
        theta = (-S * φd1 * sigma / (2 * sqT) - r * K * disc * norm.cdf(d2)) / 365
    else:
        price = K * disc * norm.cdf(-d2) - S * norm.cdf(-d1)
        delta = norm.cdf(d1) - 1.0
        theta = (-S * φd1 * sigma / (2 * sqT) + r * K * disc * norm.cdf(-d2)) / 365
    gamma = φd1 / (S * sigma * sqT)
    vega  = S * φd1 * sqT / 100.0          # per 1 pp IV change
    vanna = φd1 * d2 / sigma / 100.0       # per 1 pp IV change
    return price, delta, gamma, vega, theta, vanna


def _compute_risk_matrix(
    txns_df: "pd.DataFrame",
    step_pct:    int   = 2,
    vol_up_pct:  float = 25.0,
    vol_down_pct: float = 25.0,
    default_iv_pct: float = 20.0,
    rate_pct:    float = 4.3,
) -> dict | None:
    """
    Compute the risk matrix for all open option positions.
    Returns a dict with keys: shocks, pnl_none, pnl_vol_up, pnl_vol_down,
    underlying_px, delta, gamma, vega, vanna, theta, spots (per underlying).
    """
    import json

    opt = txns_df[
        txns_df["SecurityType"].str.lower().eq("option") &
        txns_df["Strike"].notna() &
        (pd.to_numeric(txns_df["Strike"], errors="coerce") > 0)
    ].copy() if "SecurityType" in txns_df.columns else pd.DataFrame()

    eq = txns_df[
        txns_df["SecurityType"].str.lower().ne("option") &
        txns_df["SecurityType"].str.lower().ne("cash")
    ].copy() if "SecurityType" in txns_df.columns else pd.DataFrame()

    if opt.empty and eq.empty:
        return None

    # Numeric coercions
    for col in ["Strike", "Quantity", "TransactionPrice", "Multiplier"]:
        if col in opt.columns:
            opt[col] = pd.to_numeric(opt[col], errors="coerce")
    opt["Multiplier"] = opt["Multiplier"].fillna(100)
    opt["Quantity"]   = opt["Quantity"].fillna(1)

    # Always 11 columns centered on 0; range scales with step size
    shocks = [s * step_pct / 100.0 for s in range(-5, 6)]

    r   = rate_pct / 100.0
    today = datetime.date.today()

    # Get unique underlyings and fetch spot prices
    underlyings = list(txns_df["Underlying"].dropna().unique()) if "Underlying" in txns_df.columns else []
    spots: dict[str, float] = {}
    try:
        from app import get_polygon_api_key
        from engine.positions import fetch_stock_price
        api_key = get_polygon_api_key()
        if api_key:
            for und in underlyings:
                px = fetch_stock_price(api_key, und)
                if px:
                    spots[und] = px
    except Exception:
        pass

    # Aggregate across all underlyings + legs
    pnl_none    = [0.0] * len(shocks)
    pnl_vol_up  = [0.0] * len(shocks)
    pnl_vol_dn  = [0.0] * len(shocks)
    agg_delta   = [0.0] * len(shocks)
    agg_gamma   = [0.0] * len(shocks)
    agg_vega    = [0.0] * len(shocks)
    agg_vanna   = [0.0] * len(shocks)
    agg_theta   = [0.0] * len(shocks)
    ref_spots   = {}   # underlying → spot (for display)

    for _, row in opt.iterrows():
        und  = str(row.get("Underlying") or "")
        S    = spots.get(und)
        if not S or S <= 0:
            continue

        K    = float(row["Strike"])
        qty  = float(row["Quantity"])
        mult = float(row["Multiplier"])
        sign = 1.0 if str(row.get("Direction", "")).upper() == "BUY" else -1.0
        pos  = sign * qty * mult       # +ve = long, -ve = short
        entry_px = float(row.get("TransactionPrice") or 0)
        otype = str(row.get("OptionType") or "put").lower()

        # T in years
        exp_str = str(row.get("Expiration") or "")
        try:
            exp_date = datetime.date.fromisoformat(exp_str[:10])
            T_years  = max((exp_date - today).days / 365.0, 1 / 365)
        except Exception:
            T_years = 21 / 365.0

        # IV: try Notes JSON, else default
        sigma = default_iv_pct / 100.0
        try:
            notes = json.loads(str(row.get("Notes") or "{}") or "{}")
            iv_raw = notes.get("ATM IV") or notes.get("atm_iv")
            if iv_raw is not None:
                iv_f = float(str(iv_raw).strip("%")) / 100.0 if "%" in str(iv_raw) else float(iv_raw)
                if 0.01 < iv_f < 5.0:
                    sigma = iv_f
        except Exception:
            pass

        sigma_up = sigma * (1 + vol_up_pct / 100.0)
        sigma_dn = max(sigma * (1 - vol_down_pct / 100.0), 0.01)

        ref_spots.setdefault(und, S)

        # Baseline = BS price at current spot + current vol (no shock).
        # All P&L cells show INCREMENTAL change from current mark, so 0%/None = $0.
        price_base, _, _, _, _, _ = _bs_full(S, K, T_years, r, sigma, otype)

        for i, shock in enumerate(shocks):
            S_shock = S * (1 + shock)
            price_none, d, g, v, th, va = _bs_full(S_shock, K, T_years, r, sigma, otype)
            price_up,   _, _, _, _,  _  = _bs_full(S_shock, K, T_years, r, sigma_up, otype)
            price_dn,   _, _, _, _,  _  = _bs_full(S_shock, K, T_years, r, sigma_dn, otype)

            pnl_none[i]   += (price_none - price_base) * pos
            pnl_vol_up[i] += (price_up   - price_base) * pos
            pnl_vol_dn[i] += (price_dn   - price_base) * pos
            # Dollarized Greeks (all expressed as $ P&L, not notional exposure):
            # $ Delta  = delta × pos × S × 1%     ($ P&L per +1% underlying move)
            # $ Gamma  = 0.5 × gamma × (S×1%)² × pos  ($ extra P&L per additional 1% move)
            # $ Vega   = vega × pos               (already $/pp from _bs_full dividing by 100)
            # $ Vanna  = vanna × pos × S × 1%     ($ vega change per +1% move)
            # $ Theta  = theta × pos              (already $/day from _bs_full dividing by 365)
            agg_delta[i]  += d  * pos * S_shock * 0.01
            agg_gamma[i]  += 0.5 * g * pos * (S_shock * 0.01) ** 2
            agg_vega[i]   += v  * pos
            agg_vanna[i]  += va * pos * S_shock * 0.01
            agg_theta[i]  += th * pos

    # Equity legs: delta = qty × mult × sign per shock
    for _, row in eq.iterrows():
        und  = str(row.get("Underlying") or row.get("Symbol") or "")
        S    = spots.get(und)
        if not S or S <= 0:
            continue
        qty  = float(row.get("Quantity") or 0)
        mult = float(row.get("Multiplier") or 1)
        sign = 1.0 if str(row.get("Direction", "")).upper() == "BUY" else -1.0
        entry_px = float(row.get("TransactionPrice") or 0)
        pos  = sign * qty * mult
        ref_spots.setdefault(und, S)
        for i, shock in enumerate(shocks):
            S_shock = S * (1 + shock)
            gain    = (S_shock - S) * pos   # baseline = current spot, so 0%=0
            pnl_none[i]   += gain
            pnl_vol_up[i] += gain
            pnl_vol_dn[i] += gain
            agg_delta[i]  += pos * S_shock * 0.01   # $ P&L per +1% move (shares × price × 1%)

    # Primary underlying for display (pick most common)
    primary_und = max(ref_spots, key=lambda u: 1) if ref_spots else None
    S0 = ref_spots.get(primary_und, 0) if primary_und else 0

    pnl_stress = [min(pnl_none[i], pnl_vol_up[i], pnl_vol_dn[i]) for i in range(len(shocks))]

    return {
        "shocks":       shocks,
        "pnl_stress":   pnl_stress,
        "pnl_vol_up":   pnl_vol_up,
        "pnl_none":     pnl_none,
        "pnl_vol_dn":   pnl_vol_dn,
        "delta":        agg_delta,
        "gamma":        agg_gamma,
        "vega":         agg_vega,
        "vanna":        agg_vanna,
        "theta":        agg_theta,
        "spot0":        S0,
        "ref_spots":    ref_spots,
        "primary_und":  primary_und or "",
        "multi_und":    len(ref_spots) > 1,
    }


def live_market_value(open_groups: dict) -> tuple[float, bool, int, int]:
    """Live mark-to-market *liquidation* value of all open positions.

    Returns (market_value, is_live, n_legs_priced, n_legs_total).

    Convention: a position's market value is what you'd realise on liquidation.
    LONG legs are assets (+mark); SHORT legs are liabilities (-mark — you must
    buy them back to close). So a short-premium position has a NEGATIVE market
    value, and Account Value = cash + market_value correctly nets the premium
    already collected (sitting in cash) against the cost to close.

    Live option/stock marks are used where available; any leg without a live
    quote falls back to its entry price so the figure is always complete.
    `is_live` is True only when every leg got a live quote.
    """
    api_key = None
    try:
        from app import get_polygon_api_key
        api_key = get_polygon_api_key()
    except Exception:
        pass

    from engine.positions import fetch_option_prices, fetch_stock_price

    mv = 0.0
    n_priced = 0
    n_total  = 0
    for _tgid, grp in open_groups.items():
        live_opt: dict = {}
        if api_key:
            try:
                live_opt = fetch_option_prices(api_key, grp)
            except Exception:
                live_opt = {}
        spots: dict[str, float | None] = {}
        for _, r in grp.iterrows():
            stype = str(r.get("SecurityType", "")).lower()
            if stype == "cash":
                continue
            dirn     = str(r.get("Direction", "")).upper()
            qty      = abs(float(r.get("Quantity") or 0))
            mult     = float(r.get("Multiplier") or (100 if stype == "option" else 1))
            liq_sign = 1.0 if dirn == "BUY" else -1.0   # long = +asset, short = -liability
            entry_px = float(r.get("TransactionPrice") or 0)
            sym      = str(r.get("Symbol", ""))

            cur = None
            if stype == "option":
                live = live_opt.get(sym, {})
                cur  = live.get("price") if isinstance(live, dict) else None
            elif api_key:
                und = str(r.get("Underlying") or sym)
                if und not in spots:
                    try:
                        spots[und] = fetch_stock_price(api_key, und)
                    except Exception:
                        spots[und] = None
                cur = spots.get(und)

            n_total += 1
            if cur is not None:
                n_priced += 1
                px = float(cur)
            else:
                px = entry_px
            mv += liq_sign * px * qty * mult

    is_live = n_total > 0 and n_priced == n_total
    return round(mv, 2), is_live, n_priced, n_total


def get_open_trade_groups_simple(txns_df: "pd.DataFrame") -> dict:
    """Return {tgid: {underlying, strategy, open_date, grp}} for open positions only."""
    from engine.positions import get_open_trade_groups
    groups = get_open_trade_groups(txns_df)
    result = {}
    for tgid, grp in groups.items():
        und = (grp["Underlying"].dropna().iloc[0]
               if "Underlying" in grp.columns and not grp["Underlying"].dropna().empty
               else grp["Symbol"].iloc[0] if not grp.empty else "?")
        strat = _pretty_strategy(str(grp["StrategyName"].iloc[0])) if not grp.empty else "?"
        # Earliest transaction date for this group
        open_date = ""
        for date_col in ("BusinessDate", "Date", "CreatedAt"):
            if date_col in grp.columns and not grp[date_col].dropna().empty:
                try:
                    open_date = pd.to_datetime(grp[date_col].dropna().iloc[0]).strftime("%m/%d")
                except Exception:
                    open_date = str(grp[date_col].dropna().iloc[0])[:5]
                if open_date:
                    break
        result[tgid] = {"underlying": und, "strategy": strat, "open_date": open_date, "grp": grp}
    return result


# ── Mark-to-market equity curve (reconstructed from the ledger + history) ───────

def _occ_ticker(row) -> str | None:
    """Build a Polygon options ticker (O:SPY260731P00667000) from leg details."""
    try:
        und = str(row.get("Underlying") or "").upper()
        exp = pd.to_datetime(row.get("Expiration")).strftime("%y%m%d")
        cp  = "C" if str(row.get("OptionType") or "").lower() == "call" else "P"
        k   = int(round(float(row.get("Strike")) * 1000))
        return f"O:{und}{exp}{cp}{k:08d}" if und else None
    except Exception:
        return None


def _hist_price_series(row, start, end, api_key, idx) -> "pd.Series":
    """Daily close series for one security, reindexed onto `idx`. Options via
    Polygon options aggregates (unthrottled on this plan); stocks via yfinance.
    Falls back to the entry price (flat) when no history is available."""
    st    = str(row.get("SecurityType") or "").lower()
    entry = float(row.get("TransactionPrice") or 0)
    s = None
    try:
        if st == "option":
            occ = _occ_ticker(row)
            if occ and api_key:
                from data.polygon_client import PolygonClient
                c = PolygonClient(api_key=api_key)
                d = c._get(f"/v2/aggs/ticker/{occ}/range/1/day/{start}/{end}",
                           {"adjusted": "true", "sort": "asc", "limit": 5000})
                res = d.get("results", []) or []
                if res:
                    s = pd.Series({pd.Timestamp(b["t"], unit="ms").normalize(): float(b["c"])
                                   for b in res if b.get("c") is not None})
        else:
            from data.stock_data import yf_daily_bars
            sym = str(row.get("Underlying") or row.get("Symbol") or "")
            n   = (pd.Timestamp(end) - pd.Timestamp(start)).days + 5
            df  = yf_daily_bars(sym, n_days=max(n, 30))
            if df is not None and not df.empty:
                s = pd.Series(df["close"].values, index=pd.to_datetime(df["date"]))
    except Exception:
        s = None
    if s is None or s.empty:
        return pd.Series(entry, index=idx)
    s = s[~s.index.duplicated(keep="last")].sort_index()
    return s.reindex(idx).ffill().bfill().fillna(entry)


def mtm_equity_series(txns_df: "pd.DataFrame", start_date, end_date=None) -> "pd.DataFrame":
    """Daily mark-to-market equity reconstructed on the fly:

        equity(t) = net deposits(t) + cumulative trade cashflow(t)
                    + Σ  net_qty_i(t) × price_i(t) × multiplier_i

    Net holdings come from the ledger (BUY +, SELL −) so opens and closes are
    handled automatically; prices are historical daily closes. History is built
    from the first trade (so holdings are correct) then trimmed to >= start_date.
    Returns DataFrame[BusinessDate, Amount].
    """
    import datetime as _dt
    if txns_df is None or txns_df.empty:
        return pd.DataFrame()
    from app import get_polygon_api_key
    api_key = get_polygon_api_key()

    t = txns_df.copy()
    t["BusinessDate"] = pd.to_datetime(t["BusinessDate"])
    first = t["BusinessDate"].min().normalize()
    end   = pd.Timestamp(end_date or _dt.date.today()).normalize()
    if end < first:
        end = first
    idx = pd.date_range(first, end, freq="D")

    sec_type = t.get("SecurityType", pd.Series(dtype=str)).fillna("").str.lower()
    noncash  = t[sec_type != "cash"]

    cf      = pd.Series(0.0, index=idx)
    pos_val = pd.Series(0.0, index=idx)

    for _secid, g in noncash.groupby("SecurityId"):
        row0 = g.iloc[0]
        st   = str(row0.get("SecurityType") or "").lower()
        mult = float(row0.get("Multiplier") or (100 if st == "option" else 1))

        def _sq(r):  # signed quantity: BUY +, SELL −
            return (1 if str(r["Direction"]).upper() == "BUY" else -1) * float(r["Quantity"] or 0)

        def _cf(r):  # cash flow: SELL +, BUY −
            return ((1 if str(r["Direction"]).upper() == "SELL" else -1)
                    * float(r["Quantity"] or 0) * float(r["TransactionPrice"] or 0) * mult)

        net_qty = (pd.Series(g.apply(_sq, axis=1).values, index=g["BusinessDate"].values)
                     .groupby(level=0).sum().reindex(idx, fill_value=0).cumsum())
        cf = cf.add((pd.Series(g.apply(_cf, axis=1).values, index=g["BusinessDate"].values)
                       .groupby(level=0).sum().reindex(idx, fill_value=0).cumsum()), fill_value=0)
        prices  = _hist_price_series(row0, first.date(), end.date(), api_key, idx)
        pos_val = pos_val.add(net_qty * prices * mult, fill_value=0)

    # Net deposits running baseline.
    dep_s = pd.Series(0.0, index=idx)
    try:
        from sqlalchemy import text as _text
        eng = _get_engine()
        with eng.connect() as conn:
            dep = pd.read_sql(_text("""
                SELECT BusinessDate, Amount FROM portfolio.Balance
                WHERE AccountId = :aid AND BalanceType = 'Cash'
                ORDER BY BusinessDate ASC
            """), conn, params={"aid": _ACCOUNT_ID})
        if not dep.empty:
            dep["BusinessDate"] = pd.to_datetime(dep["BusinessDate"])
            dep["Amount"]       = pd.to_numeric(dep["Amount"], errors="coerce")
            dep_s = (dep.dropna().groupby("BusinessDate")["Amount"].last()
                        .reindex(idx, method="ffill").bfill().fillna(0.0))
    except Exception:
        pass

    equity = dep_s + cf + pos_val
    df = pd.DataFrame({"BusinessDate": idx, "Amount": equity.values})
    return df[df["BusinessDate"] >= pd.Timestamp(start_date)].reset_index(drop=True)


# ── Per-position P&L (since open + day-over-day) ───────────────────────────────

def _leg_prior_close(row, api_key) -> float | None:
    """Prior completed session's close for one leg — option via Polygon options
    aggregates, stock/ETF via yfinance. None if unavailable."""
    import datetime as _dt
    st    = str(row.get("SecurityType") or "").lower()
    today = _dt.date.today()
    start = today - _dt.timedelta(days=14)
    closes: list = []
    try:
        if st == "option":
            occ = _occ_ticker(row)
            if occ and api_key:
                from data.polygon_client import PolygonClient
                c = PolygonClient(api_key=api_key)
                d = c._get(f"/v2/aggs/ticker/{occ}/range/1/day/{start}/{today}",
                           {"adjusted": "true", "sort": "asc", "limit": 5000})
                closes = [(pd.Timestamp(b["t"], unit="ms").date(), float(b["c"]))
                          for b in (d.get("results", []) or []) if b.get("c") is not None]
        else:
            from data.stock_data import yf_daily_bars
            sym = str(row.get("Underlying") or row.get("Symbol") or "")
            df  = yf_daily_bars(sym, 16)
            if df is not None and not df.empty:
                closes = list(zip(list(df["date"]), [float(x) for x in df["close"]]))
    except Exception:
        closes = []
    if not closes:
        return None
    prior = [c for (d, c) in closes if d < today]   # last close strictly before today
    return prior[-1] if prior else closes[-1][1]


def position_pnl(grp, api_key=None) -> dict:
    """Per-position P&L: live liquidation value, P&L since open, and day-over-day.

    Returns {value, since_open, dod, is_live}.  since_open = net_entry + value
    (unrealized since the trade was opened); dod = value − prior-session value.
    """
    if api_key is None:
        from app import get_polygon_api_key
        api_key = get_polygon_api_key()
    from engine.positions import fetch_option_prices, fetch_stock_price

    live_opt = {}
    try:
        live_opt = fetch_option_prices(api_key, grp) if api_key else {}
    except Exception:
        live_opt = {}

    cur = prior = 0.0
    n = priced = 0
    stock_now: dict = {}
    for _, r in grp.iterrows():
        st = str(r.get("SecurityType") or "").lower()
        if st == "cash":
            continue
        sign  = 1.0 if str(r.get("Direction", "")).upper() == "BUY" else -1.0
        qty   = abs(float(r.get("Quantity") or 0))
        mult  = float(r.get("Multiplier") or (100 if st == "option" else 1))
        entry = float(r.get("TransactionPrice") or 0)
        sym   = str(r.get("Symbol", ""))

        if st == "option":
            cur_px = (live_opt.get(sym) or {}).get("price")
        else:
            und = str(r.get("Underlying") or sym)
            if und not in stock_now:
                try:
                    stock_now[und] = fetch_stock_price(api_key, und)
                except Exception:
                    stock_now[und] = None
            cur_px = stock_now[und]

        n += 1
        if cur_px is not None and float(cur_px) > 0:
            priced += 1
        else:
            cur_px = entry
        prior_px = _leg_prior_close(r, api_key)
        if prior_px is None or prior_px <= 0:
            prior_px = entry

        cur   += sign * float(cur_px) * qty * mult
        prior += sign * float(prior_px) * qty * mult

    ne = _net_entry(grp)
    return {"value": cur, "since_open": ne + cur, "dod": cur - prior,
            "is_live": n > 0 and priced == n}
