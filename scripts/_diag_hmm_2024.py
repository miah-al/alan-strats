"""HMM Regime diagnostic: why did the strategy bleed in Jul 2024 - Jan 2025?

Tests:
1. Per-trade P&L distribution during the drawdown window
2. State classification: did the HMM detect the regime shift in Aug 2024?
3. Holding period hypothesis: are long holds (>21d) the bad trades?
4. Exit reason breakdown: profit_target / stop_loss / dte_exit / end_of_data
"""
from __future__ import annotations
import sys
from pathlib import Path
# Add BOTH the project dir (for `db`, `strategies`...) and the parent
# (so `alan_trader.*` package imports resolve).
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
import numpy as np
from datetime import date

from db.client import get_engine, get_price_bars, get_vix_bars
from alan_trader.strategies.hmm_regime import HMMRegimeStrategy


def main():
    print("=" * 78)
    print("HMM Regime Backtest Diagnostic — Jan 2022 to May 2026")
    print("=" * 78)

    eng = get_engine()
    print("\n[1/4] Loading SPY + VIX from DB...")
    spy_df = get_price_bars(eng, "SPY", date(2021, 1, 1), date(2026, 5, 31))
    vix_df = get_vix_bars(eng, date(2021, 1, 1), date(2026, 5, 31))

    if spy_df.empty or vix_df.empty:
        print(f"  SPY bars: {len(spy_df)}, VIX bars: {len(vix_df)} — aborting")
        return

    # get_price_bars returns a DataFrame with 'date' as a column; set as index
    if "date" in spy_df.columns:
        spy_df = spy_df.set_index(pd.to_datetime(spy_df["date"])).drop(columns="date")
    else:
        spy_df.index = pd.to_datetime(spy_df.index)
    if "date" in vix_df.columns:
        vix_df = vix_df.set_index(pd.to_datetime(vix_df["date"])).drop(columns="date")
    else:
        vix_df.index = pd.to_datetime(vix_df.index)
    print(f"  SPY: {len(spy_df):,} bars  ({spy_df.index.min().date()} -> {spy_df.index.max().date()})")
    print(f"  VIX: {len(vix_df):,} bars  ({vix_df.index.min().date()} -> {vix_df.index.max().date()})")

    # Filter to the same window the user ran (2022-01-01 to 2026-05-19)
    spy_df = spy_df.loc["2022-01-01":"2026-05-19"]
    vix_df = vix_df.reindex(spy_df.index).ffill()

    print(f"\n[2/4] Running HMMRegimeStrategy.backtest()...")
    strat = HMMRegimeStrategy(allow_gmm_fallback=True)  # allow fallback if hmmlearn missing
    result = strat.backtest(
        price_data       = spy_df,
        auxiliary_data   = {"vix": vix_df, "ticker": "SPY"},
        starting_capital = 10_000.0,
    )

    eq = result.equity_curve
    trades = result.trades
    regime_log = result.extra.get("regime_log", pd.DataFrame())
    m = result.metrics

    print(f"\n  Equity:   ${eq.iloc[0]:,.0f} -> ${eq.iloc[-1]:,.0f}  ({m.get('total_return_pct', 0):+.2f}%)")
    print(f"  Sharpe:   {m.get('sharpe', 0):.3f}")
    print(f"  Max DD:   {m.get('max_drawdown_pct', 0):.2f}%")
    print(f"  Trades:   {len(trades)}  (win rate {m.get('win_rate_pct', 0):.1f}%)")
    print(f"  HMM backend: {result.extra.get('hmm_backend', 'unknown')}")

    if trades.empty:
        print("\nNo trades to analyze — aborting")
        return

    # ── DRAWDOWN WINDOW: Jul 2024 - Jan 2025 ─────────────────────────────────
    print("\n[3/4] Per-trade analysis in DRAWDOWN window (Jul 2024 - Jan 2025)")
    print("-" * 78)
    trades = trades.copy()
    trades["entry_date"] = pd.to_datetime(trades["entry_date"])
    trades["exit_date"]  = pd.to_datetime(trades["exit_date"])
    trades["hold_days"]  = (trades["exit_date"] - trades["entry_date"]).dt.days

    dd_trades = trades[(trades["entry_date"] >= "2024-07-01") &
                       (trades["entry_date"] <= "2025-02-01")].copy()

    print(f"  {len(dd_trades)} trades opened in window")
    if not dd_trades.empty:
        cols = ["entry_date", "exit_date", "trade_type", "state", "p_state",
                "contracts", "max_loss", "pnl", "exit_reason", "hold_days"]
        avail = [c for c in cols if c in dd_trades.columns]
        with pd.option_context("display.max_columns", None, "display.width", 220,
                                "display.float_format", "{:.2f}".format):
            print(dd_trades[avail].to_string(index=False))

        print(f"\n  Drawdown-window totals:")
        print(f"    P&L sum:        ${dd_trades['pnl'].sum():+,.0f}")
        print(f"    Winners:        {(dd_trades['winner']).sum()} / {len(dd_trades)}")
        print(f"    Worst single:   ${dd_trades['pnl'].min():+,.0f}")
        print(f"    Worst 3 sum:    ${dd_trades['pnl'].nsmallest(3).sum():+,.0f}")

    # ── EXIT-REASON BREAKDOWN over the full backtest ─────────────────────────
    print("\n[4/4] Exit-reason breakdown (full backtest)")
    print("-" * 78)
    er = trades.groupby("exit_reason").agg(
        n=("pnl", "count"),
        avg_pnl=("pnl", "mean"),
        sum_pnl=("pnl", "sum"),
        avg_hold=("hold_days", "mean"),
    ).round(2)
    print(er.to_string())

    # ── HOLDING PERIOD HYPOTHESIS ─────────────────────────────────────────────
    print("\n[HOLDING PERIOD HYPOTHESIS] Bucket P&L by hold-days")
    print("-" * 78)
    buckets = pd.cut(trades["hold_days"],
                     bins=[-1, 7, 14, 21, 28, 35, 60],
                     labels=["<=7d", "8-14d", "15-21d", "22-28d", "29-35d", ">35d"])
    hold = trades.groupby(buckets, observed=True).agg(
        n=("pnl", "count"),
        avg_pnl=("pnl", "mean"),
        sum_pnl=("pnl", "sum"),
        win_pct=("winner", lambda s: 100*s.mean()),
    ).round(2)
    print(hold.to_string())

    # ── BY TRADE TYPE & STATE ─────────────────────────────────────────────────
    print("\n[BY TRADE TYPE & STATE] Full backtest")
    print("-" * 78)
    by_state = trades.groupby(["state", "trade_type"], observed=True).agg(
        n=("pnl", "count"),
        avg_pnl=("pnl", "mean"),
        sum_pnl=("pnl", "sum"),
        win_pct=("winner", lambda s: 100*s.mean()),
        avg_hold=("hold_days", "mean"),
    ).round(2)
    print(by_state.to_string())

    # ── REGIME LOG around Aug 2024 ─────────────────────────────────────────────
    if not regime_log.empty and "date" in regime_log.columns:
        print("\n[REGIME LOG] State classification 2024-07-15 to 2024-09-30")
        print("-" * 78)
        regime_log = regime_log.copy()
        regime_log["date"] = pd.to_datetime(regime_log["date"])
        crisis = regime_log[(regime_log["date"] >= "2024-07-15") &
                            (regime_log["date"] <= "2024-09-30")]
        if not crisis.empty:
            cols = ["date", "spot", "vix", "state", "p_state",
                    "p_state0", "p_state1", "p_state2", "n_open"]
            avail = [c for c in cols if c in crisis.columns]
            # Sample every 3 days for readability
            with pd.option_context("display.max_columns", None, "display.width", 220,
                                    "display.float_format", "{:.2f}".format):
                print(crisis[avail].iloc[::3].to_string(index=False))

    print("\n" + "=" * 78)
    print("End of diagnostic")
    print("=" * 78)


if __name__ == "__main__":
    main()
