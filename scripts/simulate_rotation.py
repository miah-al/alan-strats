"""
TLT/SPY Rotation Strategy — standalone simulation script.

Connects to SQL Server via alan_trader.db.client.get_engine(), loads all
available history for SPY + TLT price bars and MacroBar yields, then
replicates RatesSpyRotationStrategy logic exactly.

Usage:
    python -m alan_trader.scripts.simulate_rotation
  or
    python scripts/simulate_rotation.py   (from repo root)
"""

import sys
import math
import warnings
from datetime import date, timedelta

# Force UTF-8 output on Windows so Unicode chars don't raise cp1252 errors.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd
from sqlalchemy import text

warnings.filterwarnings("ignore")

# ── Constants matching RatesSpyRotationStrategy defaults ─────────────────────
STARTING_CAPITAL   = 100_000.0
YIELD_THRESHOLD    = 0.001       # 10 bps in decimal
RETURN_THRESHOLD   = 0.02        # 2 %
CONFIRM_DAYS       = 3
SLIPPAGE_PCT       = 0.0005      # 5 bps per asset on rebalance
SOFR_DEFAULT       = 0.0362      # 3.62 % annualised constant fallback

ALLOC = {
    "Growth":     (0.80, 0.10),
    "Inflation":  (0.40, 0.05),
    "Fear":       (0.20, 0.70),
    "Risk-On":    (0.90, 0.10),
    "Transition": (0.60, 0.30),
}

SEP  = "-" * 220
SEP2 = "=" * 220


# ── Helpers ──────────────────────────────────────────────────────────────────

def _classify(rc: float, sr: float) -> str:
    if math.isnan(rc) or math.isnan(sr):
        return "Transition"
    if rc >  YIELD_THRESHOLD and sr >  RETURN_THRESHOLD:
        return "Growth"
    if rc >  YIELD_THRESHOLD and sr < -RETURN_THRESHOLD:
        return "Inflation"
    if rc < -YIELD_THRESHOLD and sr < -RETURN_THRESHOLD:
        return "Fear"
    if rc < -YIELD_THRESHOLD and sr >  RETURN_THRESHOLD:
        return "Risk-On"
    return "Transition"


def _confirm_regimes(raw: pd.Series, conf_days: int) -> pd.Series:
    confirmed = raw.copy()
    streak = 1
    for i in range(1, len(raw)):
        if raw.iloc[i] == raw.iloc[i - 1]:
            streak += 1
        else:
            streak = 1
        if streak < conf_days:
            confirmed.iloc[i] = confirmed.iloc[i - 1]
    return confirmed


def _sharpe(returns: pd.Series, risk_free_annual: float = 0.0) -> float:
    rf_daily = (1 + risk_free_annual) ** (1 / 252) - 1
    excess   = returns - rf_daily
    if excess.std() == 0:
        return 0.0
    return float(excess.mean() / excess.std() * math.sqrt(252))


def _max_drawdown(equity: pd.Series) -> float:
    roll_max = equity.cummax()
    dd = (equity - roll_max) / roll_max
    return float(dd.min())


def _ann_return(equity: pd.Series) -> float:
    n_days = len(equity)
    if n_days < 2:
        return 0.0
    total_ret = equity.iloc[-1] / equity.iloc[0] - 1
    years     = n_days / 252
    return float((1 + total_ret) ** (1 / years) - 1)


# ── Database helpers ─────────────────────────────────────────────────────────

def load_price_bars_all(engine, symbol: str) -> pd.DataFrame:
    """Load ALL available price bars for symbol, date-indexed."""
    from alan_trader.db.client import get_ticker_id
    tid = get_ticker_id(engine, symbol)
    if tid is None:
        return pd.DataFrame()
    with engine.connect() as conn:
        result = conn.execute(
            text("""
                SELECT BarDate, [Close]
                FROM   mkt.PriceBar
                WHERE  TickerId = :tid
                ORDER  BY BarDate
            """),
            {"tid": tid},
        )
        rows = result.fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["date", "close"])
    df["date"]  = pd.to_datetime(df["date"])
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.set_index("date").sort_index()
    return df


def load_macro_bars_all(engine) -> pd.DataFrame:
    """Load ALL available MacroBar rows."""
    with engine.connect() as conn:
        result = conn.execute(
            text("""
                SELECT BarDate, Rate10Y, Rate2Y, Sofr
                FROM   mkt.MacroBar
                ORDER  BY BarDate
            """)
        )
        rows = result.fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["date", "rate_10y", "rate_2y", "sofr"])
    df["date"]     = pd.to_datetime(df["date"])
    df["rate_10y"] = pd.to_numeric(df["rate_10y"], errors="coerce")
    df["rate_2y"]  = pd.to_numeric(df["rate_2y"],  errors="coerce")
    df["sofr"]     = pd.to_numeric(df["sofr"],      errors="coerce")
    df = df.set_index("date").sort_index()
    return df


# ── Main simulation ──────────────────────────────────────────────────────────

def run():
    from alan_trader.db.client import get_engine
    engine = get_engine()

    print(SEP2)
    print(" TLT / SPY ROTATION STRATEGY  —  Standalone Back-Test Simulation")
    print(SEP2)

    # ── 1. Load data ─────────────────────────────────────────────────────────
    print("\n[1/5] Loading price bars …")
    spy_df   = load_price_bars_all(engine, "SPY")
    tlt_df   = load_price_bars_all(engine, "TLT")
    macro_df = load_macro_bars_all(engine)

    if spy_df.empty:
        sys.exit("ERROR: No SPY price bars found. Sync SPY price bars first.")
    if tlt_df.empty:
        sys.exit("ERROR: No TLT price bars found. Sync TLT price bars first.")
    if macro_df.empty:
        print("WARNING: No MacroBar data — using SOFR=3.62% constant; rate10y unavailable.")

    print(f"  SPY   : {len(spy_df):,} bars  {spy_df.index[0].date()} → {spy_df.index[-1].date()}")
    print(f"  TLT   : {len(tlt_df):,} bars  {tlt_df.index[0].date()} → {tlt_df.index[-1].date()}")
    if not macro_df.empty:
        print(f"  Macro : {len(macro_df):,} rows  {macro_df.index[0].date()} → {macro_df.index[-1].date()}")

    # ── 2. Align to common trading calendar (SPY dates) ──────────────────────
    print("\n[2/5] Aligning to SPY calendar …")
    idx = spy_df.index

    tlt_close  = tlt_df["close"].reindex(idx).ffill()
    rate10y    = (macro_df["rate_10y"].reindex(idx).ffill()
                  if not macro_df.empty else pd.Series(np.nan, index=idx))
    rate2y     = (macro_df["rate_2y"].reindex(idx).ffill()
                  if not macro_df.empty else pd.Series(np.nan, index=idx))
    sofr_daily = None
    if not macro_df.empty and "sofr" in macro_df.columns:
        sofr_series = macro_df["sofr"].reindex(idx).ffill()
        # convert annualised % to daily rate
        sofr_daily  = ((1 + sofr_series / 100) ** (1 / 252) - 1)
    else:
        sofr_daily = pd.Series((1 + SOFR_DEFAULT) ** (1 / 252) - 1, index=idx)

    spy_close = spy_df["close"]

    # ── 3. Regime classification ─────────────────────────────────────────────
    print("[3/5] Classifying regimes …")
    rate_change_20d = rate10y - rate10y.shift(20)    # absolute change in rate
    spy_return_20d  = spy_close.pct_change(20)

    raw_regime = pd.Series(
        [_classify(rc, sr)
         for rc, sr in zip(rate_change_20d.values, spy_return_20d.values)],
        index=idx,
    )
    regime_series = _confirm_regimes(raw_regime, CONFIRM_DAYS)

    # ── 4. Portfolio simulation ───────────────────────────────────────────────
    print("[4/5] Simulating portfolio …")
    spy_ret = spy_close.pct_change()
    tlt_ret = tlt_close.pct_change()

    capital        = STARTING_CAPITAL
    bm_capital     = STARTING_CAPITAL          # SPY buy-and-hold
    current_spy_w  = 0.60
    current_tlt_w  = 0.30
    current_cash_w = 1.0 - current_spy_w - current_tlt_w
    current_regime = "Transition"

    rows      = []           # daily detail
    trades    = []           # regime-change events
    prev_val  = capital
    entry_cap = capital
    entry_dt  = idx[0]

    for i, dt in enumerate(idx):
        regime       = regime_series.iloc[i]
        spy_w, tlt_w = ALLOC.get(regime, ALLOC["Transition"])
        cash_w       = 1.0 - spy_w - tlt_w

        # ── Daily P&L before any rebalance ───────────────────────────────────
        if i > 0:
            s_ret = float(spy_ret.iloc[i]) if not math.isnan(spy_ret.iloc[i]) else 0.0
            t_ret = float(tlt_ret.iloc[i]) if not math.isnan(tlt_ret.iloc[i]) else 0.0
            c_ret = float(sofr_daily.iloc[i]) if not math.isnan(sofr_daily.iloc[i]) else 0.0
            capital += capital * (current_spy_w * s_ret
                                  + current_tlt_w * t_ret
                                  + current_cash_w * c_ret)
            # Benchmark
            bm_capital += bm_capital * (s_ret if not math.isnan(s_ret) else 0.0)

        slip_cost = 0.0
        rebalanced = False

        # ── Rebalance on regime change ────────────────────────────────────────
        if regime != current_regime and i > 0:
            slip_cost = (
                capital * abs(spy_w  - current_spy_w)  * SLIPPAGE_PCT
                + capital * abs(tlt_w  - current_tlt_w)  * SLIPPAGE_PCT
            )
            capital   -= slip_cost
            rebalanced = True

            period_pnl = capital - entry_cap
            trades.append({
                "entry_date":   entry_dt.date(),
                "exit_date":    dt.date(),
                "from_regime":  current_regime,
                "to_regime":    regime,
                "spy_w_before": current_spy_w,
                "tlt_w_before": current_tlt_w,
                "spy_w_after":  spy_w,
                "tlt_w_after":  tlt_w,
                "spy_price":    float(spy_close.iloc[i]),
                "tlt_price":    float(tlt_close.iloc[i]),
                "slip_cost":    slip_cost,
                "period_pnl":   period_pnl,
                "capital_after": capital,
            })

            current_spy_w  = spy_w
            current_tlt_w  = tlt_w
            current_cash_w = cash_w
            current_regime = regime
            entry_cap      = capital
            entry_dt       = dt

        daily_pnl = capital - prev_val
        prev_val  = capital

        rows.append({
            "date":           dt.date(),
            "regime":         current_regime,
            "spy_price":      round(float(spy_close.iloc[i]), 2),
            "tlt_price":      round(float(tlt_close.iloc[i]) if not math.isnan(float(tlt_close.iloc[i])) else 0, 2),
            "rate10y":        round(float(rate10y.iloc[i]) if not math.isnan(float(rate10y.iloc[i])) else 0, 4),
            "spy_alloc_pct":  round(current_spy_w * 100, 1),
            "tlt_alloc_pct":  round(current_tlt_w * 100, 1),
            "cash_pct":       round(current_cash_w * 100, 1),
            "portfolio_val":  round(capital, 2),
            "daily_pnl":      round(daily_pnl, 2),
            "cum_pnl":        round(capital - STARTING_CAPITAL, 2),
            "cum_pnl_pct":    round((capital / STARTING_CAPITAL - 1) * 100, 3),
            "bm_value":       round(bm_capital, 2),
            "vs_bm":          round(capital - bm_capital, 2),
            "rebalanced":     rebalanced,
            "slip_cost":      round(slip_cost, 2),
        })

    # Close final period
    final_cap = capital
    if entry_dt.date() != idx[-1].date():
        trades.append({
            "entry_date":   entry_dt.date(),
            "exit_date":    idx[-1].date(),
            "from_regime":  current_regime,
            "to_regime":    "(end)",
            "spy_w_before": current_spy_w,
            "tlt_w_before": current_tlt_w,
            "spy_w_after":  current_spy_w,
            "tlt_w_after":  current_tlt_w,
            "spy_price":    float(spy_close.iloc[-1]),
            "tlt_price":    float(tlt_close.iloc[-1]),
            "slip_cost":    0.0,
            "period_pnl":   capital - entry_cap,
            "capital_after": capital,
        })

    daily_df  = pd.DataFrame(rows)
    trades_df = pd.DataFrame(trades)

    # ── 5. Summary statistics ─────────────────────────────────────────────────
    print("[5/5] Computing statistics …\n")

    equity         = pd.Series(daily_df["portfolio_val"].values,
                                index=pd.to_datetime(daily_df["date"]))
    daily_returns  = equity.pct_change().dropna()

    bm_equity      = pd.Series(daily_df["bm_value"].values,
                                index=pd.to_datetime(daily_df["date"]))
    bm_returns     = bm_equity.pct_change().dropna()

    total_ret_pct  = (equity.iloc[-1] / equity.iloc[0] - 1) * 100
    ann_ret_pct    = _ann_return(equity) * 100
    max_dd         = _max_drawdown(equity) * 100
    sharpe         = _sharpe(daily_returns)

    bm_total_pct   = (bm_equity.iloc[-1] / bm_equity.iloc[0] - 1) * 100
    bm_ann_pct     = _ann_return(bm_equity) * 100
    bm_sharpe      = _sharpe(bm_returns)
    bm_maxdd       = _max_drawdown(bm_equity) * 100

    best_day       = daily_df.loc[daily_df["daily_pnl"].idxmax()]
    worst_day      = daily_df.loc[daily_df["daily_pnl"].idxmin()]
    n_rebalances   = int(daily_df["rebalanced"].sum())
    n_regime_chg   = len(trades_df) - 1   # last row is "end" not a real trade

    years_traded   = len(daily_df) / 252
    total_slip     = daily_df["slip_cost"].sum()

    # ── Print regime-change trades ────────────────────────────────────────────
    print(SEP2)
    print(" REGIME-CHANGE TRADE LOG")
    print(SEP2)

    tc_hdr = (f"{'#':>4}  {'Entry Date':>12}  {'Exit Date':>12}  "
              f"{'From Regime':>11}  {'To Regime':>11}  "
              f"{'SPY%Before':>10}  {'TLT%Before':>10}  "
              f"{'SPY%After':>9}  {'TLT%After':>9}  "
              f"{'SPY Px':>8}  {'TLT Px':>7}  "
              f"{'Slip($)':>8}  {'Period P&L($)':>14}  {'Capital After($)':>17}")
    print(tc_hdr)
    print(SEP)
    for k, t in trades_df.iterrows():
        print(f"{k+1:>4}  {str(t['entry_date']):>12}  {str(t['exit_date']):>12}  "
              f"{t['from_regime']:>11}  {t['to_regime']:>11}  "
              f"{t['spy_w_before']*100:>9.1f}%  {t['tlt_w_before']*100:>9.1f}%  "
              f"{t['spy_w_after']*100:>8.1f}%  {t['tlt_w_after']*100:>8.1f}%  "
              f"{t['spy_price']:>8.2f}  {t['tlt_price']:>7.2f}  "
              f"{t['slip_cost']:>8.2f}  {t['period_pnl']:>+14.2f}  {t['capital_after']:>17,.2f}")
    print(SEP)

    # ── Print daily detail (all rows) ─────────────────────────────────────────
    print()
    print(SEP2)
    print(" DAILY PORTFOLIO DETAIL  (* = regime change / rebalance day)")
    print(SEP2)

    hdr = (f"{'Date':>12}  {'Regime':>11}  {'Rate10Y':>7}  "
           f"{'SPY Px':>8}  {'TLT Px':>7}  "
           f"{'SPY%':>5}  {'TLT%':>5}  {'Cash%':>6}  "
           f"{'Port Val':>12}  {'Daily P&L':>11}  "
           f"{'Cum P&L':>12}  {'Cum %':>8}  "
           f"{'BM Value':>12}  {'vs BM':>11}")
    print(hdr)
    print(SEP)

    prev_regime = None
    for _, r in daily_df.iterrows():
        star = "*" if r["rebalanced"] else " "
        regime_changed = r["regime"] != prev_regime and prev_regime is not None
        prev_regime    = r["regime"]

        line = (f"{star}{str(r['date']):>11}  {r['regime']:>11}  {r['rate10y']:>7.4f}  "
                f"{r['spy_price']:>8.2f}  {r['tlt_price']:>7.2f}  "
                f"{r['spy_alloc_pct']:>5.1f}  {r['tlt_alloc_pct']:>5.1f}  {r['cash_pct']:>6.1f}  "
                f"{r['portfolio_val']:>12,.2f}  {r['daily_pnl']:>+11.2f}  "
                f"{r['cum_pnl']:>+12.2f}  {r['cum_pnl_pct']:>+8.3f}%  "
                f"{r['bm_value']:>12,.2f}  {r['vs_bm']:>+11.2f}")
        print(line)
    print(SEP)

    # ── Summary statistics ────────────────────────────────────────────────────
    print()
    print(SEP2)
    print(" SUMMARY STATISTICS")
    print(SEP2)
    print()

    W = 38

    def stat(label, val):
        print(f"  {label:<{W}} {val}")

    print("  --- Strategy (TLT/SPY Rotation) ---")
    stat("Starting capital",            f"${STARTING_CAPITAL:>15,.2f}")
    stat("Final portfolio value",       f"${equity.iloc[-1]:>15,.2f}")
    stat("Total return",                f"{total_ret_pct:>+15.2f} %")
    stat("Annualised return",           f"{ann_ret_pct:>+15.2f} %")
    stat("Max drawdown",                f"{max_dd:>15.2f} %")
    stat("Sharpe ratio (rf=0)",         f"{sharpe:>15.3f}")
    stat("Number of regime changes",    f"{n_regime_chg:>15d}")
    stat("Number of rebalance days",    f"{n_rebalances:>15d}")
    stat("Total slippage cost",         f"${total_slip:>15.2f}")
    stat("Trading days",                f"{len(daily_df):>15,d}")
    stat("Years of history",            f"{years_traded:>15.2f}")
    stat(f"Best single day  ({str(best_day['date'])})",
                                        f"${best_day['daily_pnl']:>+14.2f}")
    stat(f"Worst single day ({str(worst_day['date'])})",
                                        f"${worst_day['daily_pnl']:>+14.2f}")
    print()
    print("  --- SPY Buy-and-Hold Benchmark ---")
    stat("Final benchmark value",       f"${bm_equity.iloc[-1]:>15,.2f}")
    stat("Total return (BM)",           f"{bm_total_pct:>+15.2f} %")
    stat("Annualised return (BM)",      f"{bm_ann_pct:>+15.2f} %")
    stat("Max drawdown (BM)",           f"{bm_maxdd:>15.2f} %")
    stat("Sharpe ratio (BM, rf=0)",     f"{bm_sharpe:>15.3f}")
    print()
    print("  --- Active vs Benchmark ---")
    stat("Alpha (total return)",        f"{total_ret_pct - bm_total_pct:>+15.2f} pp")
    stat("Alpha (annualised)",          f"{ann_ret_pct - bm_ann_pct:>+15.2f} pp")
    stat("Sharpe delta",                f"{sharpe - bm_sharpe:>+15.3f}")
    stat("Drawdown improvement",        f"{bm_maxdd - max_dd:>+15.2f} pp")
    stat("Final $ vs benchmark",        f"${equity.iloc[-1] - bm_equity.iloc[-1]:>+15.2f}")
    print()
    print(SEP2)
    print(" Regime allocation reference:")
    for name, (sw, tw) in ALLOC.items():
        cw = 1.0 - sw - tw
        print(f"   {name:>11}: SPY {sw*100:.0f}%  TLT {tw*100:.0f}%  Cash {cw*100:.0f}%")
    print(f"\n Parameters used: yield_threshold={YIELD_THRESHOLD*10000:.0f} bps  "
          f"return_threshold={RETURN_THRESHOLD*100:.0f}%  "
          f"confirm_days={CONFIRM_DAYS}  slippage={SLIPPAGE_PCT*10000:.0f} bps")
    print(SEP2)


if __name__ == "__main__":
    run()
