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
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)
# alan_trader is this checkout by file path, whatever its folder is called; the parent stays off sys.path
# (beside the live checkout it would expose that copy) — api/bootstrap.py.
from api.bootstrap import register_platform_package  # noqa: E402

register_platform_package()

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

# Index levels stored as daily price bars (yfinance caret symbols, mapped in db.sync).
INDEX_DAILY = ["NDX", "VXN"]
# Intraday 1-minute bars pulled from Polygon (index feed for NDX). Off by default: ~10 minutes
# for the full history, so it runs only with --intraday.
INTRADAY_DEFAULT = ["NDX"]


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
    ap.add_argument("--intraday", nargs="*", metavar="SYMBOL",
                    help="pull 1-minute bars from Polygon into mkt.MinuteBar for these symbols "
                         f"(default when given with no symbols: {' '.join(INTRADAY_DEFAULT)}); "
                         "months already stored are skipped, the current month is re-pulled")
    ap.add_argument("--intraday-from", default="2023-10-01",
                    help="first month of minute history to pull (Polygon I:NDX starts 2023-10)")
    ap.add_argument("--intraday-refresh", action="store_true",
                    help="re-pull months already stored")
    ap.add_argument("--events", action="store_true",
                    help="rebuild mkt.EventCalendar from mkt.FomcCalendar, db/seed/events/*.csv and third Fridays")
    ap.add_argument("--intraday-only", action="store_true",
                    help="skip the daily sources; run only --intraday / --events / --option-minutes")
    ap.add_argument("--option-minutes", nargs="*", metavar="SYMBOL",
                    help="pull per-contract 1-minute option trade bars (Polygon) for the same-day expiry into "
                         f"mkt.OptionMinuteBar (default with no symbols: {' '.join(INTRADAY_DEFAULT)}); needs the "
                         "index minute bars first; about 3 hours for two years of NDX")
    ap.add_argument("--option-minutes-from", default="2024-10-01",
                    help="first session for --option-minutes (Options Starter serves about two years)")
    ap.add_argument("--option-minutes-refresh", action="store_true",
                    help="re-pull sessions already in mkt.OptionMinuteSession")
    ap.add_argument("--option-minutes-band", type=float, default=400.0,
                    help="strikes within +-band points of the 13:00 underlying level")
    ap.add_argument("--option-minutes-step", type=int, default=25, help="strike grid step (25 = the traded grid)")
    ap.add_argument("--option-minutes-max", type=int, default=None,
                    help="stop after N new sessions (smoke tests)")
    args = ap.parse_args(argv)

    from db import sync

    key = _key()
    print(f"POLYGON_API_KEY: {'present' if key else 'MISSING'}")
    print(f"window: {START} → {END}")

    if not args.options_only and not args.intraday_only:
        print("\n── price bars (yfinance) ──────────────────────────────────────")
        for sym in ALL_SYMBOLS:
            _run(sym, sync.sync_price_bars, sym, key,
                 from_date=START, to_date=END)

        print("\n── index levels, daily (yfinance) ─────────────────────────────")
        for sym in INDEX_DAILY:
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

    if args.events or args.intraday_only:
        print("\n── event calendar (FOMC table + db/seed/events + third Fridays) ──")
        _run("events", sync.sync_event_calendar)

    if args.intraday is not None:
        if not key:
            print("\nPOLYGON_API_KEY missing — cannot pull minute bars.")
            return 1
        symbols = args.intraday or INTRADAY_DEFAULT
        print(f"\n── 1-minute bars (Polygon) from {args.intraday_from} ────────────────")

        def _p(msg):
            print(f"\r   {msg[:90]:<90}", end="", flush=True)

        for sym in symbols:
            out = _run(sym, sync.sync_minute_bars, sym, key,
                       from_date=date.fromisoformat(args.intraday_from), to_date=END,
                       refresh=args.intraday_refresh, progress_cb=_p)
            print()
            if out:
                print(f"     coverage: {out.get('coverage')}  empty months: {out.get('empty_months')}")
        show_counts("── row counts after intraday sources ──")

    if args.option_minutes is not None:
        if not key:
            print("\nPOLYGON_API_KEY missing — cannot pull option minute bars.")
            return 1
        symbols = args.option_minutes or INTRADAY_DEFAULT
        print(f"\n── option 1-minute bars, same-day expiry (Polygon) from {args.option_minutes_from} ──")

        def _p2(msg):
            print(f"\r   {msg[:90]:<90}", end="", flush=True)

        for sym in symbols:
            out = _run(sym, sync.sync_option_minute_bars, sym, key,
                       from_date=date.fromisoformat(args.option_minutes_from), to_date=END,
                       band=args.option_minutes_band, step=args.option_minutes_step,
                       refresh=args.option_minutes_refresh, max_sessions=args.option_minutes_max,
                       progress_cb=_p2)
            print()
            if out:
                print(f"     coverage: {out.get('coverage')}  new sessions: {out.get('sessions')}  "
                      f"skipped: {out.get('skipped')}  failed: {len(out.get('failed') or [])}")
                for d, err in (out.get("failed") or [])[:10]:
                    print(f"       {d}: {err}")
        show_counts("── row counts after option minute bars ──")

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
