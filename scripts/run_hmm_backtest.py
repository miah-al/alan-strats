"""
Standalone driver for the HMM Regime Classifier backtest on real SPY+VIX data.

Usage (from repo root):
    python -m scripts.run_hmm_backtest                # 5-year SPY backtest
    python -m scripts.run_hmm_backtest --days 1260    # custom length
    python -m scripts.run_hmm_backtest --ticker QQQ   # different underlying

Pulls daily bars from yfinance (free, no key needed; indices included via ^VIX).
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# Force UTF-8 for stdout/stderr on Windows so arrow / em-dash glyphs in the
# report don't trip cp1252 encoding errors.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import numpy as np
import pandas as pd

# Strategy code uses `alan_trader.*` absolute imports, but the repo is laid out
# such that "alan_trader" *is* the project root directory. Putting both the
# repo root (`alan_trader/`) and its parent on sys.path lets both
# `strategies.foo` and `alan_trader.strategies.foo` resolve, matching how
# dash_app/app.py bootstraps itself.
_ROOT   = Path(__file__).resolve().parent.parent
_PARENT = _ROOT.parent
for p in (_ROOT, _PARENT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

try:
    from dotenv import load_dotenv
    load_dotenv(_ROOT / ".env")
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s %(name)s: %(message)s",
)
log = logging.getLogger("hmm_backtest")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", default="SPY")
    ap.add_argument("--days",   type=int, default=1260,
                    help="Trading days of history to fetch (~5 yrs default)")
    ap.add_argument("--capital", type=float, default=100_000.0)
    args = ap.parse_args()

    try:
        import yfinance as yf
    except ImportError:
        log.error("yfinance is required. `pip install yfinance`.")
        return 2

    from strategies.hmm_regime import HMMRegimeStrategy

    # yfinance: free, no API key, indices included (^VIX). Pull a calendar-day
    # window that comfortably exceeds `args.days` trading days (~1.5× factor).
    cal_days = int(args.days * 1.5) + 60
    end = pd.Timestamp.today().normalize()
    start = end - pd.Timedelta(days=cal_days)
    log.info(f"Fetching {args.ticker} + ^VIX from yfinance ({start.date()} → {end.date()})...")
    spy_raw = yf.download(args.ticker, start=start, end=end, progress=False, auto_adjust=False)
    vix_raw = yf.download("^VIX",       start=start, end=end, progress=False, auto_adjust=False)
    if spy_raw.empty or vix_raw.empty:
        log.error("yfinance returned empty data — check network / ticker.")
        return 2

    # yfinance returns a MultiIndex on columns when multiple tickers are
    # requested; for single-ticker calls it's flat. Normalise to (close)-only
    # DataFrames indexed by date.
    def _flatten(df: pd.DataFrame) -> pd.DataFrame:
        if isinstance(df.columns, pd.MultiIndex):
            df = df.droplevel(1, axis=1)
        df = df.rename(columns=str.lower)
        return df[[c for c in ("open", "high", "low", "close", "volume") if c in df.columns]]

    spy = _flatten(spy_raw)
    vix = _flatten(vix_raw)
    spy = spy.tail(args.days)
    vix = vix.reindex(spy.index).ffill()

    log.info(f"SPY: {len(spy)} bars, {spy.index.min().date()} → {spy.index.max().date()}")
    log.info(f"VIX: {len(vix)} bars, {vix.index.min().date()} → {vix.index.max().date()}")

    strat = HMMRegimeStrategy()
    log.info("Running HMM backtest (this fits EM every 30 bars; takes ~30-90s)...")
    result = strat.backtest(
        price_data=spy,
        auxiliary_data={"vix": vix},
        starting_capital=args.capital,
        ticker=args.ticker,
    )

    _print_report(result, args.ticker)
    return 0


def _print_report(result, ticker: str) -> None:
    eq = result.equity_curve
    rets = result.daily_returns
    trades = result.trades
    metrics = result.metrics or {}
    regime_log = result.extra.get("regime_log", pd.DataFrame())

    print()
    print("=" * 72)
    print(f"HMM REGIME BACKTEST  —  {ticker}  ({eq.index.min().date()} → {eq.index.max().date()})")
    print("=" * 72)

    final = float(eq.iloc[-1])
    start = float(eq.iloc[0])
    total_ret = final / start - 1.0
    print(f"  Final equity     ${final:>12,.0f}   (start ${start:,.0f})")
    print(f"  Total return     {total_ret:>+12.2%}")
    print(f"  HMM backend      {result.extra.get('hmm_backend', '?')}")

    # Core risk metrics
    for k in ("annual_return", "annual_vol", "sharpe_ratio", "sortino_ratio",
              "max_drawdown", "calmar_ratio", "cvar_95", "var_95"):
        v = metrics.get(k)
        if v is None:
            continue
        print(f"  {k:<16} {v:>+12.4f}")

    print()
    print("─ Trades ─" * 7)
    if trades is None or trades.empty:
        print("  NO TRADES — check confidence floor / data length.")
        return
    n_t = len(trades)
    n_w = int(trades["winner"].sum())
    avg_pnl = float(trades["pnl"].mean())
    print(f"  N trades         {n_t}")
    print(f"  Winners          {n_w}  ({100 * n_w / n_t:.1f}%)")
    print(f"  Avg P&L / trade  ${avg_pnl:>+10.2f}")
    print(f"  Total P&L        ${float(trades['pnl'].sum()):>+10.2f}")

    print("\n  By trade type:")
    by_t = trades.groupby("trade_type")["pnl"].agg(["count", "sum", "mean"])
    by_t["win_rate"] = trades.groupby("trade_type")["winner"].mean() * 100
    for tt, row in by_t.iterrows():
        print(f"    {tt:<22} n={int(row['count']):>3}  "
              f"sum=${row['sum']:>+9.0f}  mean=${row['mean']:>+7.0f}  "
              f"win%={row['win_rate']:>5.1f}")

    print("\n  Exit reasons:")
    for reason, cnt in trades["exit_reason"].value_counts().items():
        print(f"    {reason:<22} {cnt}")

    # Regime durations
    if not regime_log.empty and "state" in regime_log.columns:
        rl = regime_log.dropna(subset=["state"]).copy()
        rl["state"] = rl["state"].astype(int)
        total = len(rl)
        print(f"\n─ Regime distribution (n={total} bars post-warmup)")
        for s, label in [(0, "low_vol_bull"), (1, "chop"), (2, "high_vol_bear")]:
            cnt = int((rl["state"] == s).sum())
            print(f"    state {s} ({label:<14}) {cnt:>4} bars  ({100*cnt/total:5.1f}%)")

        # Average regime confidence when each state is the argmax
        print(f"\n─ Mean P(dominant state) when state = argmax")
        for s in (0, 1, 2):
            subset = rl[rl["state"] == s]
            if not subset.empty:
                print(f"    state {s}: mean P = {subset['p_state'].mean():.3f}  "
                      f"(median {subset['p_state'].median():.3f})")

        # Last 5 regime transitions for sanity
        rl["prev"] = rl["state"].shift(1)
        transitions = rl[rl["state"] != rl["prev"]].dropna(subset=["prev"])
        print(f"\n─ Regime transitions: {len(transitions)} total. Last 8:")
        for _, row in transitions.tail(8).iterrows():
            print(f"    {row['date'].date()}  state {int(row['prev'])} → {int(row['state'])}  "
                  f"VIX={row['vix']:.1f}  P={row['p_state']:.2f}")


if __name__ == "__main__":
    sys.exit(main())
