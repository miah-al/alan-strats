"""Store the conservative re-run as the Performance page's backtest expectation (one app.BacktestRun row per strategy).

    python -m scripts.store_conservative_baseline                       # from data/backtest_baselines.json
    python -m scripts.store_conservative_baseline --slug ndx_0dte_tasty # one strategy
    python -m scripts.store_conservative_baseline --dry-run             # print what would be stored

The rows carry ``_execution_mode: conservative`` in ParamsJson, which api/services/strategy_stats.py prefers over any
optimistic run when it builds ``backtest_expectation``. Until this has been run the service serves the same numbers from
the checked-in file, so running it is optional; it makes the expectation survive a checkout that lacks the file, and
records when the baseline was set. Refuses to run while ALAN_TRADER_STORE_BACKTESTS=0 (the test setting).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from api.bootstrap import register_platform_package  # noqa: E402

register_platform_package()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", default=str(ROOT / "data" / "backtest_baselines.json"))
    ap.add_argument("--slug", default=None)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    from api.services import strategy_stats as SS
    if not SS.store_backtests():
        print("ALAN_TRADER_STORE_BACKTESTS is off; nothing stored"); return 2
    raw = json.loads(Path(a.file).read_text(encoding="utf-8"))
    strategies = raw.get("strategies", raw)
    n = 0
    for slug, b in strategies.items():
        if a.slug and slug != a.slug:
            continue
        if b.get("mode", "conservative") != "conservative":
            print(f"{slug}: not a conservative baseline; skipped"); continue
        metrics = {"win_rate_pct": (b["win_rate"] * 100.0) if b.get("win_rate") is not None else None, "avg_win": b.get("avg_win"),
                   "avg_loss": b.get("avg_loss"), "profit_factor": b.get("profit_factor"), "total_return_pct": b.get("total_return_pct"),
                   "sharpe": b.get("sharpe"), "max_drawdown_pct": b.get("max_drawdown_pct")}
        import pandas as pd
        # record_backtest takes the trade list for the count and the mean; the baseline carries both already
        trades = pd.DataFrame({"pnl": [b["avg_pnl"]] * int(b.get("trades") or 0)}) if b.get("avg_pnl") is not None else None
        params = {"execution": b.get("execution"), **(b.get("params") or {})}
        print(f"{slug}: {b['from']} .. {b['to']}, {b.get('trades')} trades, avg {b.get('avg_pnl')}, win rate {b.get('win_rate')} "
              f"-> app.BacktestRun (conservative){' [dry run]' if a.dry_run else ''}")
        if not a.dry_run:
            SS.record_backtest(slug, b.get("ticker", "NDX"), b["from"], b["to"], float(b.get("capital") or 0.0), params, metrics, trades,
                               mode=SS.CONSERVATIVE)
        n += 1
    print(f"{n} baseline(s) {'would be ' if a.dry_run else ''}stored")
    return 0


if __name__ == "__main__":
    sys.exit(main())
