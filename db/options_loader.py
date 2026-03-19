"""
alan-strats | Historical spread P&L from mkt.OptionSnapshot.

Strike selection is purely moneyness-based (% of spot price at entry).
On exit, looks up those same absolute strikes in the exit-date chain for
the same expiration. No contract-ID tracking needed.

Supported spread types:
  iron_condor   — sell OTM put + call, buy wings
  bull_call     — buy ATM call, sell OTM call
  bear_put      — buy ATM put,  sell OTM put
  bull_put      — sell OTM put, buy further put (credit)
  bear_call     — sell OTM call, buy further call (credit)
  long_straddle — buy ATM call + put
  short_strangle— sell OTM call + put
  call_butterfly— buy low, sell 2x mid, buy high call
"""

import logging
from datetime import date, timedelta
from typing import Optional

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

CREDIT_SPREADS = {"iron_condor", "bull_put", "bear_call", "short_strangle"}
DEBIT_SPREADS  = {"bull_call", "bear_put", "long_straddle", "call_butterfly"}


# ── Chain loader ──────────────────────────────────────────────────────────────

def _load_chain(engine: Engine, ticker_id: int,
                from_date: date, to_date: date,
                min_dte: int = 7, max_dte: int = 75) -> pd.DataFrame:
    """Bulk-load option snapshots for the date range."""
    query = text("""
        SELECT SnapshotDate, ExpirationDate, Strike, ContractType,
               Mid, Bid, Ask, Delta, ImpliedVol
        FROM   mkt.OptionSnapshot
        WHERE  TickerId = :tid
          AND  SnapshotDate BETWEEN :from_d AND :to_d
          AND  DATEDIFF(day, SnapshotDate, ExpirationDate) BETWEEN :min_dte AND :max_dte
        ORDER  BY SnapshotDate, ExpirationDate, Strike, ContractType
    """)
    with engine.connect() as conn:
        result = conn.execute(query, {
            "tid": ticker_id, "from_d": from_date, "to_d": to_date,
            "min_dte": min_dte, "max_dte": max_dte,
        })
        df = pd.DataFrame(result.fetchall(), columns=result.keys())

    if df.empty:
        return df

    df.columns = [c.lower() for c in df.columns]
    df = df.rename(columns={
        "snapshotdate":   "snapshot_date",
        "expirationdate": "expiration_date",
        "contracttype":   "contract_type",
        "impliedvol":     "iv",
    })
    df["snapshot_date"]   = pd.to_datetime(df["snapshot_date"]).dt.date
    df["expiration_date"] = pd.to_datetime(df["expiration_date"]).dt.date
    for col in ["strike", "mid", "bid", "ask", "delta", "iv"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Fill missing mid from bid-ask midpoint
    mask = df["mid"].isna() | (df["mid"] == 0)
    df.loc[mask, "mid"] = (df.loc[mask, "bid"].fillna(0) + df.loc[mask, "ask"].fillna(0)) / 2

    return df


# ── Helpers ───────────────────────────────────────────────────────────────────

def _find_expiry(available_exps: list, snap_date: date, target_dte: int,
                 tolerance: int = 15) -> Optional[date]:
    if not available_exps:
        return None
    best = min(available_exps, key=lambda e: abs((e - snap_date).days - target_dte))
    if abs((best - snap_date).days - target_dte) > tolerance:
        return None
    return best


def _nearest_strike(strikes: np.ndarray, target: float) -> Optional[float]:
    if len(strikes) == 0:
        return None
    return float(strikes[np.argmin(np.abs(strikes - target))])


def _leg_mid(chain_slice: pd.DataFrame, strike: float, ctype: str) -> Optional[float]:
    row = chain_slice[
        (np.isclose(chain_slice["strike"], strike)) &
        (chain_slice["contract_type"] == ctype)
    ]
    if row.empty or pd.isna(row.iloc[0]["mid"]):
        return None
    v = float(row.iloc[0]["mid"])
    return v if v > 0 else None


# ── Leg definitions (moneyness-based) ─────────────────────────────────────────

def _define_legs(spread_type: str, spot: float,
                 otm_pct: float, wing_pct: float,
                 chain_exp: pd.DataFrame) -> Optional[list[dict]]:
    """
    Return leg list [{contract_type, strike, action}] using moneyness targeting.
    Actual strikes are the nearest available in the chain.
    """
    put_strikes  = np.sort(chain_exp.loc[chain_exp["contract_type"] == "P", "strike"].dropna().unique())
    call_strikes = np.sort(chain_exp.loc[chain_exp["contract_type"] == "C", "strike"].dropna().unique())

    np_ = lambda t: _nearest_strike(put_strikes,  t)
    nc  = lambda t: _nearest_strike(call_strikes, t)

    if spread_type == "iron_condor":
        sp = np_(spot * (1 - otm_pct));         lp = np_(spot * (1 - otm_pct - wing_pct))
        sc = nc(spot  * (1 + otm_pct));         lc = nc(spot  * (1 + otm_pct + wing_pct))
        if any(x is None for x in [sp, lp, sc, lc]):     return None
        if lp >= sp or sc >= lc:                           return None
        return [{"contract_type": "P", "strike": sp, "action": "sell"},
                {"contract_type": "P", "strike": lp, "action": "buy"},
                {"contract_type": "C", "strike": sc, "action": "sell"},
                {"contract_type": "C", "strike": lc, "action": "buy"}]

    elif spread_type == "bull_call":
        lk = nc(spot); sk = nc(spot * (1 + wing_pct))
        if lk is None or sk is None or lk >= sk: return None
        return [{"contract_type": "C", "strike": lk, "action": "buy"},
                {"contract_type": "C", "strike": sk, "action": "sell"}]

    elif spread_type == "bear_put":
        lk = np_(spot); sk = np_(spot * (1 - wing_pct))
        if lk is None or sk is None or sk >= lk: return None
        return [{"contract_type": "P", "strike": lk, "action": "buy"},
                {"contract_type": "P", "strike": sk, "action": "sell"}]

    elif spread_type == "bull_put":
        sk = np_(spot * (1 - otm_pct)); lk = np_(spot * (1 - otm_pct - wing_pct))
        if sk is None or lk is None or lk >= sk: return None
        return [{"contract_type": "P", "strike": sk, "action": "sell"},
                {"contract_type": "P", "strike": lk, "action": "buy"}]

    elif spread_type == "bear_call":
        sk = nc(spot * (1 + otm_pct)); lk = nc(spot * (1 + otm_pct + wing_pct))
        if sk is None or lk is None or sk >= lk: return None
        return [{"contract_type": "C", "strike": sk, "action": "sell"},
                {"contract_type": "C", "strike": lk, "action": "buy"}]

    elif spread_type == "long_straddle":
        ck = nc(spot); pk = np_(spot)
        if ck is None or pk is None: return None
        return [{"contract_type": "C", "strike": ck, "action": "buy"},
                {"contract_type": "P", "strike": pk, "action": "buy"}]

    elif spread_type == "short_strangle":
        sk_c = nc(spot * (1 + otm_pct)); sk_p = np_(spot * (1 - otm_pct))
        if sk_c is None or sk_p is None: return None
        return [{"contract_type": "C", "strike": sk_c, "action": "sell"},
                {"contract_type": "P", "strike": sk_p, "action": "sell"}]

    elif spread_type == "call_butterfly":
        mid = nc(spot); lo = nc(spot * (1 - wing_pct)); hi = nc(spot * (1 + wing_pct))
        if any(x is None for x in [lo, mid, hi]): return None
        if not (lo < mid < hi):                    return None
        # Two sells at mid
        return [{"contract_type": "C", "strike": lo,  "action": "buy"},
                {"contract_type": "C", "strike": mid, "action": "sell"},
                {"contract_type": "C", "strike": mid, "action": "sell"},
                {"contract_type": "C", "strike": hi,  "action": "buy"}]

    return None


def _spread_value(legs: list[dict], chain_exp: pd.DataFrame) -> Optional[float]:
    """Net credit (+) or debit (-) given current chain prices."""
    total = 0.0
    for leg in legs:
        mid = _leg_mid(chain_exp, leg["strike"], leg["contract_type"])
        if mid is None:
            return None
        total += mid if leg["action"] == "sell" else -mid
    return round(total, 4)


def _max_profit_loss(spread_type: str, legs: list[dict],
                     entry_value: float) -> tuple[float, float]:
    strikes = sorted(set(l["strike"] for l in legs))
    if spread_type == "iron_condor":
        p_strikes = sorted(l["strike"] for l in legs if l["contract_type"] == "P")
        c_strikes = sorted(l["strike"] for l in legs if l["contract_type"] == "C")
        wing = max(
            p_strikes[-1] - p_strikes[0] if len(p_strikes) >= 2 else 0,
            c_strikes[-1] - c_strikes[0] if len(c_strikes) >= 2 else 0,
        )
    else:
        wing = strikes[-1] - strikes[0] if len(strikes) >= 2 else 0

    if spread_type in CREDIT_SPREADS:
        return max(entry_value, 0), max(wing - entry_value, 0)
    elif spread_type == "long_straddle":
        # Unlimited upside; use 2x premium as a practical max_profit reference
        return abs(entry_value) * 2, abs(entry_value)
    elif spread_type == "short_strangle":
        # Unlimited downside; max_profit = premium received
        return max(entry_value, 0), abs(entry_value) * 3
    else:  # debit spreads with defined wings
        return max(wing + entry_value, 0), abs(entry_value)


# ── Main builder ──────────────────────────────────────────────────────────────

def build_spread_history(
    engine: Engine,
    ticker: str,
    spread_type: str = "iron_condor",
    target_dte:  int   = 30,
    hold_days:   int   = 21,
    otm_pct:     float = 0.05,   # short leg distance from spot (fraction)
    wing_pct:    float = 0.05,   # wing width (fraction of spot)
    from_date:   Optional[date] = None,
    to_date:     Optional[date] = None,
    enter_threshold: float = 0.25,   # pnl >= 25% of max_profit → ENTER
    avoid_threshold: float = -0.10,  # pnl < -10% of max_profit → AVOID
    diagnostics: Optional[dict] = None,  # populated in-place if provided
) -> pd.DataFrame:
    """
    Build historical spread P&L for a ticker and spread type.

    Returns DataFrame indexed by entry date with columns:
      date, exit_date, expiration, dte_at_entry, spread_type,
      spot, entry_value, exit_value, pnl, pnl_pct, max_profit, max_loss, label
    """
    def _diag(key, val):
        if diagnostics is not None:
            diagnostics[key] = val

    from alan_trader.db.client import get_ticker_id, get_price_bars

    tid = get_ticker_id(engine, ticker)
    if tid is None:
        logger.warning(f"build_spread_history: ticker {ticker} not found")
        _diag("error", f"Ticker '{ticker}' not found in database")
        return pd.DataFrame()

    to_date   = to_date   or date.today() - timedelta(days=1)
    from_date = from_date or (to_date - timedelta(days=730))

    # Price bars give us spot prices
    price_df = get_price_bars(engine, ticker, from_date,
                              to_date + timedelta(days=hold_days + 10))
    if price_df.empty:
        logger.warning(f"build_spread_history: no price bars for {ticker}")
        _diag("error", f"No price bars found for '{ticker}' in date range {from_date} → {to_date}")
        return pd.DataFrame()
    price_df["date"] = pd.to_datetime(price_df["date"]).dt.date
    spot_by_date = dict(zip(price_df["date"], price_df["close"].astype(float)))
    _diag("n_price_bars", len(spot_by_date))
    _diag("date_range", f"{from_date} → {to_date}")

    # Bulk-load options chain (include exit window) — use wide DTE window
    min_dte = max(hold_days - 10, 0)
    max_dte = target_dte + 30
    chain = _load_chain(
        engine, tid,
        from_date,
        to_date + timedelta(days=hold_days + 10),
        min_dte=min_dte,
        max_dte=max_dte,
    )
    _diag("chain_rows", len(chain))
    _diag("dte_filter", f"min_dte={min_dte}, max_dte={max_dte}")
    if chain.empty:
        logger.warning(f"build_spread_history: no options data for {ticker}")
        _diag("error", f"No option chain rows found for '{ticker}' (DTE {min_dte}–{max_dte})")
        return pd.DataFrame()

    # Index: (snapshot_date, expiration_date) → sub-DataFrame
    chain_idx: dict[tuple, pd.DataFrame] = {}
    for (snap, exp), grp in chain.groupby(["snapshot_date", "expiration_date"]):
        chain_idx[(snap, exp)] = grp.reset_index(drop=True)

    rows = []
    entry_dates = sorted(d for d in spot_by_date if from_date <= d <= to_date)
    n_no_expiry = n_no_legs = n_no_entry_val = n_no_exit = n_sign_fail = 0

    for entry_date in entry_dates:
        spot = spot_by_date.get(entry_date)
        if not spot or spot <= 0:
            continue

        # Pick expiration
        entry_exps = [exp for (snap, exp) in chain_idx if snap == entry_date]
        expiry = _find_expiry(entry_exps, entry_date, target_dte, tolerance=21)
        if expiry is None:
            n_no_expiry += 1
            continue

        entry_chain = chain_idx.get((entry_date, expiry))
        if entry_chain is None or entry_chain.empty:
            n_no_expiry += 1
            continue

        legs = _define_legs(spread_type, spot, otm_pct, wing_pct, entry_chain)
        if legs is None:
            n_no_legs += 1
            continue

        entry_value = _spread_value(legs, entry_chain)
        if entry_value is None:
            n_no_entry_val += 1
            continue

        # Sanity check sign
        if spread_type in CREDIT_SPREADS and entry_value <= 0:
            n_sign_fail += 1
            continue
        if spread_type in DEBIT_SPREADS and entry_value >= 0:
            n_sign_fail += 1
            continue

        # Find exit snapshot — first available on or after target exit date
        target_exit = entry_date + timedelta(days=hold_days)
        exit_candidates = sorted(
            snap for (snap, exp) in chain_idx
            if exp == expiry and snap >= target_exit
        )
        if not exit_candidates:
            n_no_exit += 1
            continue
        exit_date = exit_candidates[0]
        if (exit_date - target_exit).days > 7:   # tolerate up to 7-day gap
            n_no_exit += 1
            continue

        exit_chain = chain_idx.get((exit_date, expiry))
        if exit_chain is None or exit_chain.empty:
            n_no_exit += 1
            continue

        exit_value = _spread_value(legs, exit_chain)
        if exit_value is None:
            n_no_exit += 1
            continue

        # entry_value - exit_value works for both credit and debit:
        # credit: received credit_entry, paid credit_exit to close → profit = entry - exit
        # debit:  entry_value is negative; exit_value is also negative (same leg actions);
        #         closing receives -exit_value; P&L = -exit_value - (-entry_value) = entry - exit
        pnl = entry_value - exit_value

        max_profit, max_loss = _max_profit_loss(spread_type, legs, entry_value)
        pnl_pct = pnl / max(max_profit, 0.01)

        label = 1
        if pnl_pct >= enter_threshold:
            label = 2
        elif pnl_pct < avoid_threshold:
            label = 0

        rows.append({
            "date":         entry_date,
            "exit_date":    exit_date,
            "expiration":   expiry,
            "dte_at_entry": (expiry - entry_date).days,
            "spread_type":  spread_type,
            "spot":         round(float(spot), 4),
            "entry_value":  round(entry_value, 4),
            "exit_value":   round(exit_value, 4),
            "pnl":          round(pnl, 4),
            "pnl_pct":      round(pnl_pct, 4),
            "max_profit":   round(max_profit, 4),
            "max_loss":     round(max_loss, 4),
            "label":        int(label),
        })

    _diag("n_entry_dates", len(entry_dates))
    _diag("n_no_expiry",   n_no_expiry)
    _diag("n_no_legs",     n_no_legs)
    _diag("n_no_entry_val",n_no_entry_val)
    _diag("n_sign_fail",   n_sign_fail)
    _diag("n_no_exit",     n_no_exit)
    _diag("n_rows",        len(rows))

    logger.info(
        f"build_spread_history [{ticker} {spread_type}]: "
        f"entry_dates={len(entry_dates)} chain_rows={len(chain)} "
        f"no_expiry={n_no_expiry} no_legs={n_no_legs} "
        f"no_entry_val={n_no_entry_val} sign_fail={n_sign_fail} "
        f"no_exit={n_no_exit} → {len(rows)} rows"
    )

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("date").reset_index(drop=True)
        n_enter = (df["label"] == 2).sum()
        n_skip  = (df["label"] == 1).sum()
        n_avoid = (df["label"] == 0).sum()
        _diag("n_enter", int(n_enter))
        _diag("n_skip",  int(n_skip))
        _diag("n_avoid", int(n_avoid))
        logger.info(
            f"build_spread_history [{ticker} {spread_type}]: "
            f"{len(df)} rows | ENTER={n_enter} SKIP={n_skip} AVOID={n_avoid}"
        )
    return df
