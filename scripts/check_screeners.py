"""
scripts/check_screeners.py — run every wired screener through the production scan path.

Calls `app.pages.strategies.scan._run_scan` directly, the same function the Scan
button invokes, on live market data. Reports per-strategy row counts and the
first error, so a screener that silently returns nothing is distinguishable from
one that raises.

    python -m scripts.check_screeners
    python -m scripts.check_screeners --universe etf_core --slugs hmm_regime
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
import traceback

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)
# alan_trader is this checkout by file path, whatever its folder is called; the parent stays off sys.path
# (beside the live checkout it would expose that copy) — api/bootstrap.py.
from api.bootstrap import register_platform_package  # noqa: E402

register_platform_package()

_env = os.path.join(_REPO, ".env")
if os.path.exists(_env):
    with open(_env, encoding="utf-8") as fh:
        for line in fh:
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.strip().split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

logging.basicConfig(level=logging.ERROR)
for _n in ("strategies", "app", "db", "engine", "yfinance", "urllib3"):
    logging.getLogger(_n).setLevel(logging.CRITICAL)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    # Universe values are the display labels themselves — see
    # app/pages/strategies/registry.py::_UNIVERSE_TICKERS.
    ap.add_argument("--universe", default="ETF Core",
                    choices=["ETF Core", "Mega Cap", "High IV"])
    ap.add_argument("--slugs", help="comma-separated subset")
    args = ap.parse_args(argv)

    from app import get_polygon_api_key
    from app.pages.strategies.scan import _run_scan
    from app.pages.strategies.registry import _STRATEGIES_RULES, _STRATEGIES_AI
    from alan_trader.strategy_api.registry import STRATEGY_METADATA

    all_slugs = [e["value"] for e in _STRATEGIES_RULES + _STRATEGIES_AI]
    slugs = [s.strip() for s in args.slugs.split(",")] if args.slugs else all_slugs

    api_key = get_polygon_api_key()
    print(f"universe={args.universe}  api_key={'yes' if api_key else 'NO'}  "
          f"strategies={len(slugs)}\n")
    print(f"{'slug':<26}{'type':<6}{'status':<10}{'rows':>6}  detail")
    print("-" * 84)

    ok = err = empty = 0
    failures = []
    for slug in slugs:
        stype = STRATEGY_METADATA.get(slug, {}).get("type", "?")
        t0 = time.time()
        try:
            rows, status, _banner = _run_scan(slug, args.universe, None, api_key)
            n = len(rows or [])
            if n:
                ok += 1
                state = "OK"
            else:
                empty += 1
                state = "EMPTY"
            print(f"{slug:<26}{stype:<6}{state:<10}{n:>6}  ({time.time()-t0:.1f}s)")
        except Exception as exc:
            err += 1
            failures.append((slug, f"{type(exc).__name__}: {exc}",
                             traceback.format_exc()))
            detail = " ".join(f"{type(exc).__name__}: {exc}".split())[:70]
            print(f"{slug:<26}{stype:<6}{'ERROR':<10}{'-':>6}  {detail}")

    print(f"\n{ok} returned rows · {empty} returned none · {err} raised")

    if failures:
        print("\n── failures ─────────────────────────────────────────────────")
        for slug, msg, tb in failures:
            print(f"\n{slug}: {msg}")
            print("   " + "\n   ".join(tb.strip().splitlines()[-6:]))

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
