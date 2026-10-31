"""
paper/views.py — the paper account's read side, headless: pure data + pricing logic.

Transaction loading, net entry, liquidation value, capital at risk, structure labels, runner
ownership, the runner-published marks, Black-Scholes pricing/greeks, the risk matrix and the
mark-to-market equity curve. The service's /api/paper endpoints are built on it, and so is the
Paper Trading page while the Dash app exists (``app/pages/paper_trading/data.py`` is this
module under its old name). Moved verbatim from that page module.

The paper runners publish their state under ``STATE_DIR`` (``<checkout>/paper_state``, the
directory ``paper.runner`` writes) and, for runners started from another checkout, in
``EXTRA_STATE_DIRS`` (read only); every reader below looks in all of them.
"""
from __future__ import annotations

import math
import datetime
import pandas as pd
import numpy as np

from pathlib import Path

_ACCOUNT_ID = 1
#: Where the paper runners publish sessions and heartbeats (paper.runner.STATE_DIR).
STATE_DIR = Path(__file__).resolve().parent.parent / "paper_state"
#: Other checkouts' state directories to read as well (never written): a runner started from another
#: checkout publishes its sessions there, and its positions must still be priced and owned by it here.
EXTRA_STATE_DIRS: list = []


def state_dirs() -> list:
    """STATE_DIR first, then EXTRA_STATE_DIRS (duplicates dropped)."""
    out, seen = [], set()
    for d in [STATE_DIR, *EXTRA_STATE_DIRS]:
        try:
            key = Path(d).resolve()
        except OSError:
            continue
        if key not in seen:
            seen.add(key)
            out.append(Path(d))
    return out


def _glob_state(pattern: str) -> list:
    out = []
    for d in state_dirs():
        try:
            out.extend(sorted(d.glob(pattern)))
        except OSError:
            continue
    return out


def _pretty_strategy(name: str) -> str:
    """Map a strategy slug to the display label its plugin registered.
    Falls back to the input unchanged if no mapping is registered."""
    if not name:
        return name
    try:
        from alan_trader.strategy_api import registry as R
        labels = {e["value"]: e["label"] for e in R.ui_entries()}
        return labels.get(str(name), str(name))
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
    """The cash a position has moved so far: credits +, debits -.

    Taken from the booked Amount of every leg when all of them carry one -- that is what left or
    reached the account, commission and fees included. Recomputing it from prices alone leaves the
    costs out, so a position's P&L (net entry + value) read a few dollars better than the account
    did and the popup's figures did not add up to the page's. Rows without an Amount (a manually
    entered trade) fall back to price x quantity x multiplier, as before.
    """
    if "Amount" in grp.columns and not grp.empty:
        rows = grp[grp["SecurityType"].astype(str).str.lower() != "cash"] if "SecurityType" in grp.columns else grp
        amt = pd.to_numeric(rows["Amount"], errors="coerce")
        if len(amt) and amt.notna().all():
            return float(amt.sum())
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
    # The underlying level comes from the paper session that holds these positions -- the feed it
    # trades on, published every poll. The greeks are only as good as the spot behind them, and a
    # spot from a different vendor (or a stale one) makes every number in the risk table wrong while
    # looking perfectly plausible.
    spots: dict[str, float] = {}
    for _u in underlyings:
        _s = session_spot(str(_u))
        if _s:
            spots[str(_u)] = _s

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
            if exp_date == today:
                # 0DTE: hours, not days. Flooring at a whole day on a position with three hours left
                # prices in time value that cannot exist and flattens the gamma that dominates it.
                now = datetime.datetime.now()
                close = datetime.datetime.combine(today, datetime.time(16, 0))
                mins = max((close - now).total_seconds() / 60.0, 1.0)
                T_years = mins / (365.0 * 24.0 * 60.0)
            else:
                T_years = max((exp_date - today).days / 365.0, 1 / 365)
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


def _is_expired(row) -> bool:
    """True when an option leg's expiration date is strictly before today."""
    try:
        exp = str(row.get("Expiration") or "")[:10]
        return bool(exp) and datetime.date.fromisoformat(exp) < datetime.date.today()
    except Exception:
        return False


def _expiry_settle_spot(und: str, exp_date: "datetime.date", api_key, cache: dict) -> float | None:
    """Underlying close on (or the nearest trading day on/before) the option's
    expiration date — the basis for cash settlement. Falls back to the latest
    live price when daily history is unavailable. Cached per (underlying, expiry)."""
    key = (und, exp_date.isoformat())
    if key in cache:
        return cache[key]
    spot = None
    # An option that expires TODAY settles on today's close, and the session that traded it watched
    # that close tick by tick. Its own last level is therefore the settlement basis -- the same feed
    # the fills came from -- and it is available immediately, where a daily history source has
    # nothing for today until well after the bell.
    if exp_date == datetime.date.today():
        spot = session_spot(und)
    if spot is not None:
        cache[key] = spot
        return spot
    try:
        from data.stock_data import yf_daily_bars
        df = yf_daily_bars(und, n_days=30)
        if df is not None and not df.empty:
            d = df.copy()
            d["date"] = pd.to_datetime(d["date"]).dt.date
            on_or_before = d[d["date"] <= exp_date]
            if not on_or_before.empty:
                spot = float(on_or_before["close"].iloc[-1])
    except Exception:
        spot = None
    cache[key] = spot          # no third-party fallback: a settlement basis from another vendor
    return spot                # would price the expiry differently from the fills that made it


def _expired_option_intrinsic(row, api_key, spot_cache: dict) -> float | None:
    """Per-share intrinsic settlement value of an EXPIRED option leg, or None
    when the leg isn't expired / can't be priced. Used in place of the entry-
    price fallback so expired legs mark at true settlement value (incl. $0 when
    they expire worthless), not at their original cost."""
    if str(row.get("SecurityType") or "").lower() != "option" or not _is_expired(row):
        return None
    try:
        exp_date = datetime.date.fromisoformat(str(row.get("Expiration"))[:10])
        K = float(row.get("Strike"))
    except Exception:
        return None
    und = str(row.get("Underlying") or row.get("Symbol") or "")
    if not und:
        return None
    S = _expiry_settle_spot(und, exp_date, api_key, spot_cache)
    if S is None or S <= 0:
        return None
    otype = str(row.get("OptionType") or "put").lower()
    return max(S - K, 0.0) if otype == "call" else max(K - S, 0.0)


def _expiry_payoff_pnl(grp: "pd.DataFrame", S: float) -> float:
    """Total P&L of the position if the underlying settles at price `S` at
    expiration: opening cashflow (credit +, debit −) plus the intrinsic
    liquidation value of every leg. Long legs are assets (+), shorts are
    liabilities (−) — the same convention as live_market_value()."""
    ne  = _net_entry(grp)            # opening cashflow: SELL +, BUY −
    liq = 0.0
    for _, r in grp.iterrows():
        st = str(r.get("SecurityType") or "").lower()
        if st == "cash":
            continue
        liq_sign = 1.0 if str(r.get("Direction", "")).upper() == "BUY" else -1.0
        qty  = abs(float(r.get("Quantity") or 0))
        mult = float(r.get("Multiplier") or (100 if st == "option" else 1))
        if st == "option":
            K     = float(r.get("Strike") or 0)
            otype = str(r.get("OptionType") or "put").lower()
            val   = max(S - K, 0.0) if otype == "call" else max(K - S, 0.0)
        else:
            val = S                  # stock/ETF is worth S per share
        liq += liq_sign * val * qty * mult
    return ne + liq


def position_risk(grp: "pd.DataFrame") -> float | None:
    """Capital at risk = magnitude of the worst-case loss at expiration.

    The expiry payoff is piecewise-linear with kinks only at the strikes, so the
    worst case is found by scanning S at {0, each strike, a far point}. Returns
    None when the loss is unbounded (e.g. a naked short call / short stock) so
    callers can fall back to a cost basis.

    This single scan is correct for BOTH credit positions (risk = wing width −
    credit) and debit positions (risk = premium paid), so no credit/debit branch
    is needed.
    """
    strikes: list[float] = []
    if "Strike" in grp.columns:
        strikes = sorted({float(k) for k in
                          pd.to_numeric(grp["Strike"], errors="coerce").dropna() if k > 0})
    far = max(strikes) * 3.0 if strikes else 0.0
    pts = [0.0] + strikes + ([far] if far else [])
    if not pts:
        return None
    min_pnl = min(_expiry_payoff_pnl(grp, S) for S in pts)
    # Unbounded-upside check: if the payoff is still falling beyond `far`, the
    # loss is open-ended (short call / short stock) → no defined risk basis.
    if far and _expiry_payoff_pnl(grp, far * 2.0) < min(_expiry_payoff_pnl(grp, far), min_pnl) - 1e-6:
        return None
    risk = -min_pnl
    return risk if risk > 1e-9 else None


def _vertical_bound(grp) -> "tuple[float, float] | None":
    """For a two-leg same-type, same-expiry, equal-size option vertical: the no-arbitrage range of its
    liquidation value, (0, width*mult*qty) for a debit spread and (-width*mult*qty, 0) for a credit."""
    try:
        legs = grp[grp["SecurityType"].astype(str).str.lower() == "option"] if "SecurityType" in grp.columns else grp.iloc[0:0]
        if len(legs) != 2:
            return None
        a, b = legs.iloc[0], legs.iloc[1]
        same = (str(a.get("OptionType", "")).upper()[:1] == str(b.get("OptionType", "")).upper()[:1]
                and str(a.get("Expiration"))[:10] == str(b.get("Expiration"))[:10]
                and abs(float(a.get("Quantity") or 0)) == abs(float(b.get("Quantity") or 0))
                and str(a.get("Direction", "")).upper() != str(b.get("Direction", "")).upper())
        if not same:
            return None
        width = abs(float(a.get("Strike") or 0) - float(b.get("Strike") or 0))
        qty = abs(float(a.get("Quantity") or 0)); mult = float(a.get("Multiplier") or 100)
        if width <= 0:
            return None
        # debit spread = the bought leg is the one worth more: long the lower call / higher put
        cp = str(a.get("OptionType", "")).upper()[:1]
        buy_leg = a if str(a.get("Direction", "")).upper() == "BUY" else b
        sell_leg = b if buy_leg is a else a
        kb, ks = float(buy_leg.get("Strike") or 0), float(sell_leg.get("Strike") or 0)
        debit = (kb < ks) if cp == "C" else (kb > ks)
        cap = width * mult * qty
        return (0.0, cap) if debit else (-cap, 0.0)
    except Exception:
        return None


def paper_runner_marks() -> dict:
    """Live marks published by the paper runners themselves, as {trade group id: (mark, units, source)}.

    ``source`` is the feed the session actually traded on, carried through so a position is always
    marked by the venue that filled it -- a tastytrade paper trade is priced with tastytrade prices,
    and a position from some other provider with that provider's -- and so the page can say which.

    A paper position is priced by the session that owns it, off the same broker feed it trades on.
    Nothing else can be correct: a second vendor's quote for the same legs disagrees with the fills,
    and a stale one disagrees badly -- prior-day closes on a 0DTE spread value a deep in-the-money
    leg at almost nothing and then present it as a live mark.

    ``mark`` is the vertical's liquidation value in points per unit. Missing or unreadable state
    simply yields no marks, and the caller falls back to net entry value.
    """
    import json
    from pathlib import Path
    out: dict = {}
    try:
        today = datetime.date.today().isoformat()
        for f in _glob_state(f"*_{today}.json"):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
            tgids = d.get("tgids") or {}
            source = str(d.get("provider") or "paper runner")
            # The heartbeat is rewritten every poll and carries a mark from that poll's quote; the
            # session state is only saved when a minute bar closes. Prefer the fresher one.
            live: dict = {}
            hb = f.parent / f"heartbeat_{f.name.rsplit('_', 1)[0]}.json"
            try:
                if hb.exists():
                    h = json.loads(hb.read_text(encoding="utf-8"))
                    live = h.get("live_marks") or {}
                    # A runner that has stopped leaves its last mark behind, and a page that keeps
                    # showing it says nothing is wrong. Say how old the price is instead: the number
                    # is still the best available, but the reader gets to know it has stopped moving.
                    at = h.get("at")
                    if at:
                        age = (datetime.datetime.now() - datetime.datetime.fromisoformat(at)).total_seconds()
                        if age > 120:
                            source = f"{source} · STALE {int(age // 60)}m"
                            live = {}          # do not present a stale mark as a live one
                    if h.get("halted"):
                        source = f"{source} · HALTED"
            except (ValueError, OSError):
                live = {}
            state = d.get("state") or {}
            for pos in state.get("positions") or []:
                key = f"{pos.get('direction')}|{pos.get('k_low')}|{pos.get('k_high')}"
                mark, units = live.get(key, pos.get("last_mark")), pos.get("units")
                if mark is None or not units:
                    continue
                # a multi-leg structure (a straddle, an iron fly) is keyed by its kind too, and a SHORT one's
                # liquidation value is a liability: the engine says which way with mark_sign (+1 long, -1 short)
                sign = float(pos.get("mark_sign") or 1)
                for k in (key, f"{pos.get('kind')}|{key}"):
                    for tgid in tgids.get(k) or []:
                        out[str(tgid)] = (float(mark) * sign, float(units), source)
            # the SYNTHETIC futures hedge book (ndx_gamma_scalp): marked at the runner's spot, units scaled so the
            # page's option arithmetic (mark x units x 100) gives units x spot x its $20 multiplier, signed long / short
            h = state.get("hedge") or {}
            hpid = d.get("hedge_pid")
            try:
                hu = float(h.get("units") or 0.0)
                spot = None
                if hb.exists() and not (source.endswith("m") and "STALE" in source):
                    spot = (json.loads(hb.read_text(encoding="utf-8")).get("spot"))
                if hpid and hu and spot:
                    out[str(hpid)] = (float(spot), hu * float(h.get("multiplier") or 20.0) / 100.0, f"{source} · synthetic hedge")
            except (ValueError, OSError, TypeError):
                pass
    except Exception:
        return {}
    return out


def session_spot(underlying: str) -> "float | None":
    """The index level the paper session trading ``underlying`` last published, or None.

    Matched on the underlying the heartbeat names, so a level is never handed to a position on a
    different underlying -- the NDX session's 30,400 is not a price for an SPY leg. A heartbeat from an
    older runner that does not name its underlying is only trusted when it is the only one there is.
    """
    import json
    from pathlib import Path
    und = str(underlying or "").upper()
    unnamed = []
    for hb in _glob_state("heartbeat_*.json"):
        try:
            d = json.loads(hb.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        s = d.get("spot")
        if not s:
            continue
        named = str(d.get("underlying") or "").upper()
        if named and named == und:
            return float(s)
        if not named:
            unnamed.append(float(s))
    return unnamed[0] if len(unnamed) == 1 else None


_BROKER_PROVIDER: dict = {}          # one provider per underlying, reused across popups


def live_leg_prices(grp) -> "tuple[dict, float | None]":
    """Per-leg mid prices and the underlying level, from the broker the paper session trades on.

    Returns ({symbol: {"price": mid}}, spot). Both empty/None when the broker cannot be reached --
    the caller then shows a dash, which is the honest answer. It must never fall back to a second
    vendor: a leg priced off somebody else's stale close is worse than no price, because it looks
    like a number and gets read as one.

    The prices come from the running paper session, which already quotes these legs every poll and
    publishes them in its heartbeat. The web process therefore opens no broker connection of its
    own: no second set of credentials, no extra requests, no second opinion about the price -- and
    no event loop belonging to another thread, which is what made the first attempt at this return
    nothing at all from inside a Dash callback.
    """
    import json
    from pathlib import Path
    try:
        syms = [str(s) for s in grp["Symbol"].dropna().unique()
                if str(grp.loc[grp["Symbol"] == s, "SecurityType"].iloc[0]).lower() == "option"]
        if not syms:
            return {}, None
        legs: dict = {}
        spot = None
        for hb in _glob_state("heartbeat_*.json"):
            try:
                d = json.loads(hb.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
            legs.update(d.get("live_legs") or {})         # option symbols are unique across underlyings
        und = str(grp["Underlying"].dropna().iloc[0]) if "Underlying" in grp.columns and not grp["Underlying"].dropna().empty else ""
        spot = session_spot(und)
        out = {s: {"price": float(legs[s])} for s in syms if s in legs}
        return out, spot
    except Exception:
        return {}, None


def structure_label(grp) -> str:
    """What the position actually is, in the words a trader would use: "Bear put 30475/30525".

    A strategy name alone does not say which way you are leaning, and this one trades both
    directions -- a bull call spread on an up day and a bear put spread on a down day look
    identical on the page until something tells them apart.

    Read off the legs rather than a note, so it is right whatever wrote the rows: for calls,
    buying the lower strike is bullish and buying the higher strike is bearish; for puts it is
    the other way round.
    """
    try:
        legs = grp[grp["SecurityType"].astype(str).str.lower() == "option"]
        if legs.empty:
            return ""
        buys = legs[legs["Direction"].astype(str).str.upper() == "BUY"]
        sells = legs[legs["Direction"].astype(str).str.upper() == "SELL"]
        if buys.empty or sells.empty:
            return ""
        kb = float(pd.to_numeric(buys["Strike"], errors="coerce").dropna().iloc[0])
        ks = float(pd.to_numeric(sells["Strike"], errors="coerce").dropna().iloc[0])
        otype = str(buys["OptionType"].dropna().iloc[0]).lower() if "OptionType" in buys.columns and not buys["OptionType"].dropna().empty else ""
        if otype.startswith("c"):
            side = "Bull call" if kb < ks else "Bear call"
        elif otype.startswith("p"):
            side = "Bear put" if kb > ks else "Bull put"
        else:
            return ""
        lo, hi = sorted((kb, ks))
        return f"{side} {lo:.0f}/{hi:.0f}"
    except Exception:
        return ""


def managed_by_runner(tgid) -> "str | None":
    """The feed of the live paper session that holds this position, or None if no session does.

    A position a runner holds must only be closed by that runner. Closing it from the page writes
    closing rows to the ledger while the engine still owns the position; the runner then closes it
    again at its target or at settlement, and the ledger records two exits for one position.
    """
    import json
    from pathlib import Path
    tail = str(tgid).rsplit("-", 1)[-1]
    try:
        today = datetime.date.today().isoformat()
        for f in _glob_state(f"*_{today}.json"):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
            for ids in (d.get("tgids") or {}).values():
                if tail in {str(i) for i in (ids or [])}:
                    return str(d.get("provider") or "paper runner")
    except Exception:
        return None
    return None


def runner_mark_for(marks: dict, tgid) -> "tuple | None":
    """Look a position up in the runner marks. The page keys a group as 'NDX-NDX_0DTE-10029' while the
    runner records the bare ledger id it was given, so the numeric tail is the reliable join."""
    if not marks:
        return None
    key = str(tgid)
    if key in marks:
        return marks[key]
    return marks.get(key.rsplit("-", 1)[-1])


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
    api_key = None                     # no third-party market data here: paper marks come from the
                                       # broker feed the session trades on (see paper_runner_marks)
    runner_marks = paper_runner_marks()

    mv = 0.0
    n_priced = 0
    n_total  = 0
    settle_cache: dict = {}   # (underlying, expiry) → settlement spot
    for _tgid, grp in open_groups.items():
        # the owning paper session's own mark, where there is one: authoritative, and free
        rm = runner_mark_for(runner_marks, _tgid)
        if rm is not None:
            mark, units, _src = rm
            n_legs = int((grp["SecurityType"].astype(str).str.lower() == "option").sum()) if "SecurityType" in grp.columns else 2
            mv += mark * units * 100.0
            n_priced += n_legs
            n_total += n_legs
            continue
        live_opt: dict = {}
        spots: dict[str, float | None] = {}
        grp_live, grp_entry, grp_all_live, grp_n = 0.0, 0.0, True, 0
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
                if cur is None:   # expired legs have no live quote → settle at intrinsic
                    cur = _expired_option_intrinsic(r, api_key, settle_cache)
            elif api_key:
                und = str(r.get("Underlying") or sym)
                if und not in spots:
                    try:
                        spots[und] = fetch_stock_price(api_key, und)
                    except Exception:
                        spots[und] = None
                cur = spots.get(und)

            n_total += 1; grp_n += 1
            grp_entry += liq_sign * entry_px * qty * mult
            if cur is not None:
                n_priced += 1
                grp_live += liq_sign * float(cur) * qty * mult
            else:
                grp_all_live = False
        # all legs live: the live value; otherwise the group's net entry value (never a mix)
        if grp_n:
            gv = grp_live if grp_all_live else grp_entry
            bound = _vertical_bound(grp)
            if bound is not None:                       # a vertical is worth between 0 and its width, whatever two stale quotes say
                lo, hi = bound
                gv = min(hi, max(lo, gv))
            mv += gv

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


def mtm_equity_series(txns_df: "pd.DataFrame", start_date, end_date=None, account_id=None) -> "pd.DataFrame":
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
    from engine.env import get_polygon_api_key
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

        def _cf(r):  # cash flow: the booked net cash when the runner wrote it, else SELL +, BUY −
            amt = r.get("Amount") if hasattr(r, "get") else None
            if amt is not None and amt == amt:
                return float(amt)
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
            """), conn, params={"aid": _ACCOUNT_ID if account_id is None else account_id})
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
    # Prices come from the paper session that holds the position (see live_leg_prices): the same
    # feed it trades on, published every poll. api_key is kept in the signature for callers that
    # still pass one, and ignored -- a paper position marked off a second vendor's stale close is
    # how this card came to report a -89.9% loss on a position that was up.
    api_key = None
    live_opt, _spot = live_leg_prices(grp)

    cur = prior = 0.0
    n = priced = 0
    stock_now: dict = {}
    settle_cache: dict = {}   # (underlying, expiry) → settlement spot
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
            # a stock or ETF leg has no price in the paper session's feed (it publishes the index level
            # and its own option legs); leave it unpriced so it falls back to entry, rather than
            # borrowing the index level as the price of a share
            cur_px = None

        # Expired option legs have no live quote — settle at intrinsic value
        # (incl. $0 when worthless) rather than reverting to entry price.
        expired_px = None
        if st == "option" and (cur_px is None or float(cur_px) <= 0):
            expired_px = _expired_option_intrinsic(r, api_key, settle_cache)

        n += 1
        if cur_px is not None and float(cur_px) > 0:
            priced += 1
        elif expired_px is not None:
            priced += 1
            cur_px = expired_px
        else:
            cur_px = entry
        prior_px = _leg_prior_close(r, api_key)
        if prior_px is None or prior_px <= 0:
            prior_px = entry

        cur   += sign * float(cur_px) * qty * mult
        prior += sign * float(prior_px) * qty * mult

    ne = _net_entry(grp)
    _b = _vertical_bound(grp)
    if _b is not None:                                  # two stale leg quotes cannot make a vertical worth more than its width
        cur = min(_b[1], max(_b[0], cur)); prior = min(_b[1], max(_b[0], prior))
    dod = cur - prior
    # A position opened today has no prior close: its day so far IS its life so far. The leg-by-leg
    # baseline falls back to each leg's price, which leaves out the commission paid on the way in, so
    # Day P&L read a few dollars better than P&L Since Open on the same 0DTE position.
    try:
        if "BusinessDate" in grp.columns and (pd.to_datetime(grp["BusinessDate"]).dt.date == datetime.date.today()).all():
            dod = ne + cur
    except Exception:
        pass
    return {"value": cur, "since_open": ne + cur, "dod": dod,
            "is_live": n > 0 and priced == n}
