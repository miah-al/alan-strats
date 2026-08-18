"""
scripts/bootstrap_market_data.py — populate a fresh AlanStrats DB with real data.

Every source here is genuine market data:
  * price bars   — yfinance (the canonical stock source per db.sync)
  * VIX bars     — CBOE's free daily CSV
  * macro bars   — FRED
  * earnings     — Polygon financials
  * option chain — Polygon per-contract daily aggregates (slow; run with --options)

Nothing is synthesised. If a source is unreachable the symbol is reported as
FAILED and left empty rather than filled with a placeholder.

Usage
-----
    python -m scripts.bootstrap_market_data                # fast sources only
    python -m scripts.bootstrap_market_data --options      # + Polygon option surface
    python -m scripts.bootstrap_market_data --options-only --symbol SPY
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import traceback
from datetime import date

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_REPO, os.path.dirname(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Load POLYGON_API_KEY from .env if present.
_env = os.path.join(_REPO, ".env")
if os.path.exists(_env):
    with open(_env, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


# Window: start well before the 2021-01 ranking window so indicators that need
# a 200-day warm-up have real history rather than a truncated ramp.
START = date(2020, 1, 1)
END = date.today()

CORE = ["SPY", "QQQ", "IWM", "TLT"]
SECTOR_ETFS = ["XLK", "XLE", "XLF", "XLV", "XLI",
               "XLY", "XLP", "XLU", "XLRE", "XLB", "XLC"]
EXTRA = ["GLD", "EEM", "AAPL", "F", "HOOD", "TSLA", "MARA", "BITO"]

ALL_SYMBOLS = CORE + SECTOR_ETFS + EXTRA
EARNINGS_SYMBOLS = ["F", "AAPL", "HOOD", "TSLA"]


def _key() -> str:
    return os.environ.get("POLYGON_API_KEY", "")


def _run(label: str, fn, *a, **kw):
    print(f"  {label:<34}", end="", flush=True)
    t0 = time.time()
    try:
        out = fn(*a, **kw)
        dt = time.time() - t0
        if isinstance(out, dict):
            bits = ", ".join(f"{k}={v}" for k, v in list(out.items())[:4]
                             if not isinstance(v, (list, dict)))
        else:
            bits = str(out)[:80]
        print(f"OK   ({dt:5.1f}s) {bits}")
        return out
    except Exception as exc:
        print(f"FAIL ({time.time()-t0:5.1f}s) {type(exc).__name__}: {str(exc)[:120]}")
        if os.environ.get("BOOTSTRAP_DEBUG"):
            traceback.print_exc()
        return None


def counts() -> dict:
    from db.client import get_engine
    from sqlalchemy import text
    q = """SELECT s.name+'.'+t.name AS tbl, SUM(p.rows) AS n
           FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id
           JOIN sys.partitions p ON p.object_id=t.object_id AND p.index_id IN (0,1)
           WHERE s.name='mkt'
           GROUP BY s.name,t.name ORDER BY s.name,t.name"""
    with get_engine().connect() as c:
        return {r[0]: r[1] for r in c.execute(text(q)).fetchall()}


def show_counts(title: str):
    print(f"\n{title}")
    for k, v in counts().items():
        print(f"    {k:<26}{v:>10,}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--options", action="store_true",
                    help="also sync the Polygon option surface (slow)")
    ap.add_argument("--options-only", action="store_true")
    ap.add_argument("--symbol", default="SPY", help="underlying for the option sync")
    ap.add_argument("--dte-min", type=int, default=7)
    ap.add_argument("--dte-max", type=int, default=90)
    ap.add_argument("--monthly-only", action="store_true", default=True)
    ap.add_argument("--options-start", default="2024-04-01",
                    help="option history start; the Starter plan only serves ~2y")
    ap.add_argument("--force", action="store_true",
                    help="re-fetch dates already synced. Needed after a pricing "
                         "correction: the resume logic skips (date, contract_type) "
                         "pairs already present, so without this a re-sync is a no-op "
                         "and stale values survive.")
    args = ap.parse_args(argv)

    from db import sync

    key = _key()
    print(f"POLYGON_API_KEY: {'present' if key else 'MISSING'}")
    print(f"window: {START} → {END}")

    if not args.options_only:
        print("\n── price bars (yfinance) ──────────────────────────────────────")
        for sym in ALL_SYMBOLS:
            _run(sym, sync.sync_price_bars, sym, key,
                 from_date=START, to_date=END)

        print("\n── VIX (CBOE) ─────────────────────────────────────────────────")
        _run("VIX", sync.sync_vix_bars, from_date=START, to_date=END)

        print("\n── macro (FRED) ───────────────────────────────────────────────")
        _run("macro", sync.sync_macro_bars, from_date=START, to_date=END)

        print("\n── FOMC calendar ──────────────────────────────────────────────")
        _run("fomc", sync.sync_fomc_calendar)

        if key:
            print("\n── earnings (Polygon) ─────────────────────────────────────────")
            for sym in EARNINGS_SYMBOLS:
                _run(sym, sync.sync_earnings, sym, key,
                     from_date=START, to_date=END)

            print("\n── dividends ──────────────────────────────────────────────────")
            for sym in ["SPY"]:
                _run(sym, sync.sync_dividends, sym, key,
                     from_date=START, to_date=END)

        show_counts("── row counts after fast sources ──")

    if args.options or args.options_only:
        if not key:
            print("\nPOLYGON_API_KEY missing — cannot sync options.")
            return 1
        print(f"\n── option surface for {args.symbol} (Polygon, slow) ───────────")
        print(f"   dte {args.dte_min}–{args.dte_max}, "
              f"monthly_only={args.monthly_only}")

        def progress(msg, done=0, total=0, rows=0):
            if total:
                print(f"\r   {msg[:60]:<60} {done}/{total} rows={rows}",
                      end="", flush=True)

        _run(args.symbol, sync.sync_option_snapshots, args.symbol, key,
             from_date=date.fromisoformat(args.options_start), to_date=END,
             dte_min=args.dte_min, dte_max=args.dte_max,
             monthly_only=args.monthly_only, force=args.force,
             progress_cb=progress)
        print()
        show_counts("── row counts after option sync ──")

    return 0


if __name__ == "__main__":
    sys.exit(main())
