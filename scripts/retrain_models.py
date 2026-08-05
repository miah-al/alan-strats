"""
scripts/retrain_models.py — rebuild persisted ML artifacts under the current sklearn.

Why this exists
---------------
`saved_models/*.pkl` were pickled under scikit-learn 1.8. Under 1.9 the
gradient-boosting loss class moved, so 12 of them raise
`ModuleNotFoundError: No module named '_loss'` on load. That mattered more than
it looks: `load_model()` used to let the exception escape, the screener wrapped
scoring in a broad `except`, and a broken model surfaced to the user as
`score = 0.0, all_pass = False` — indistinguishable from "no setup today".

`load_model()` now returns False instead of raising, so a stale artifact
degrades to the documented heuristic rather than a fake zero. This script fixes
the underlying cause by regenerating the artifacts.

It deliberately retrains by running each strategy's own `backtest()` — the same
walk-forward fit the app uses — rather than reimplementing the training. The
strategy persists the model itself at the end of the run.

Usage
-----
    python -m scripts.retrain_models                 # audit only, no writes
    python -m scripts.retrain_models --apply         # retrain everything broken
    python -m scripts.retrain_models --apply --slug iron_condor_ai
"""
from __future__ import annotations

import argparse
import glob
import logging
import os
import pickle
import sys
from datetime import date, timedelta

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_REPO, os.path.dirname(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import warnings
warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.ERROR)
for _n in ("strategies", "app", "db", "engine", "sklearn"):
    logging.getLogger(_n).setLevel(logging.CRITICAL)

import pandas as pd  # noqa: E402

SAVED = os.path.join(_REPO, "saved_models")

# Warm-up before the training window so indicators are live from bar one.
WARMUP_DAYS = 420
TRAIN_FROM = date(2021, 1, 1)
TRAIN_TO = date(2026, 6, 30)

# (slug, module, class, tickers) — tickers become the per-model filename suffix.
RETRAINABLE = [
    # "default" is the screener's fallback when a ticker has no own model, so
    # it must exist and load like any other.
    ("iron_condor_ai", "strategies.iron_condor_ai", "IronCondorAIStrategy",
     ["SPY", "QQQ", "IWM", "TLT", "GLD", "EEM", "XLK", "XLF", "XLE", "XLV",
      "default"]),
    ("covered_call_ai", "strategies.covered_call_ai", "CoveredCallAIStrategy",
     ["SPY"]),
    # Writes rs_credit_spread_{lag,lead}.pkl; needs the sector-ETF loader, so
    # it is driven on SPY with the loader supplying the sector frames.
    ("rs_credit_spread", "strategies.rs_credit_spread", "RSCreditSpreadStrategy",
     ["SPY"]),
]

# Artifacts this script cannot regenerate, with the reason. Reported rather
# than silently left looking broken.
UNRETRAINABLE = {
    "vol_calendar_HOOD.pkl":
        "requires xgboost, which is not installed in this environment",
    "vol_calendar_spread_hood.pt":
        "PyTorch checkpoint; torch is not installed in this environment",
}


def audit() -> list[tuple[str, str]]:
    """Return [(filename, status)] for every pickle in saved_models/."""
    rows = []
    for path in sorted(glob.glob(os.path.join(SAVED, "*.pkl"))):
        name = os.path.basename(path)
        try:
            with open(path, "rb") as fh:
                pickle.load(fh)
            rows.append((name, "OK"))
        except Exception as exc:
            rows.append((name, f"FAIL {type(exc).__name__}: {str(exc)[:52]}"))
    return rows


def _load_inputs(ticker: str, slug: str):
    """
    Price + auxiliary data for a retrain, via the production loaders.

    `ticker` may be the sentinel "default" (iron_condor_ai's fallback model),
    which is not a real symbol — train it on SPY but keep the save tag.
    """
    from db.client import get_engine, get_price_bars, get_vix_bars, get_macro_bars
    from app.pages.backtest_loaders import run_loaders_for

    data_ticker = "SPY" if ticker.lower() == "default" else ticker
    engine = get_engine()
    bars = get_price_bars(engine, data_ticker,
                          TRAIN_FROM - timedelta(days=WARMUP_DAYS), TRAIN_TO)
    if bars is None or bars.empty:
        raise ValueError(f"no price bars for {data_ticker}")
    if "date" in bars.columns:
        bars = bars.set_index("date")
    bars.index = pd.to_datetime(bars.index)

    warm_from = TRAIN_FROM - timedelta(days=WARMUP_DAYS)
    try:
        vix = get_vix_bars(engine, warm_from, TRAIN_TO)
        rates = get_macro_bars(engine, warm_from, TRAIN_TO)
    except Exception:
        vix, rates = pd.DataFrame(), pd.DataFrame()
    if not vix.empty:
        vix.index = pd.to_datetime(vix.index)
    if not rates.empty:
        rates.index = pd.to_datetime(rates.index)

    aux = {"vix": vix, "rate10y": rates, "ticker": ticker}

    # Per-strategy loaders (sector ETFs, option chains, …) — the same ones the
    # Backtest tab uses, so training sees exactly the app's inputs.
    try:
        extra, block = run_loaders_for(slug, engine, data_ticker,
                                       TRAIN_FROM, TRAIN_TO, price_data=bars)
        aux.update(extra)
        if block is not None:
            raise ValueError(f"{slug}: required data missing for {data_ticker}")
    except ValueError:
        raise
    except Exception:
        pass   # loaders are optional for most strategies

    return bars, aux


def retrain_one(slug: str, module: str, cls_name: str, ticker: str) -> tuple[bool, str]:
    """Run the strategy's own walk-forward backtest, which fits and saves."""
    import importlib

    try:
        bars, aux = _load_inputs(ticker, slug)
    except Exception as exc:
        return False, f"data: {exc}"

    try:
        strategy = getattr(importlib.import_module(module), cls_name)()
        result = strategy.backtest(bars, aux, starting_capital=100_000.0)
    except Exception as exc:
        return False, f"backtest: {type(exc).__name__}: {str(exc)[:60]}"

    fitted = [getattr(strategy, a, None)
              for a in ("_model", "_model_lag", "_model_lead")]
    if not any(f is not None for f in fitted):
        return False, "backtest produced no model (too little data to fit?)"

    # ALWAYS save, never conditionally. Only iron_condor_ai persists itself
    # inside backtest(); for the others a stale, unreadable artifact would
    # otherwise survive untouched and the retrain would silently "pass" while
    # re-reading the old broken file.
    try:
        strategy.save_model(ticker)
    except Exception as exc:
        return False, f"save: {type(exc).__name__}: {exc}"

    written = _artifacts_for(slug, ticker)
    missing = [f for f in written if not os.path.exists(os.path.join(SAVED, f))]
    if missing:
        return False, f"expected artifact(s) not written: {missing}"
    for fname in written:
        try:
            with open(os.path.join(SAVED, fname), "rb") as fh:
                pickle.load(fh)
        except Exception as exc:
            return False, f"{fname} still unreadable: {type(exc).__name__}: {exc}"

    n = int((result.metrics or {}).get("num_trades", 0) or 0)
    return True, f"{', '.join(written)} ({n} trades)"


def _artifacts_for(slug: str, ticker: str) -> list[str]:
    """Filenames a given (slug, ticker) retrain is expected to produce."""
    if slug == "iron_condor_ai":
        return [f"iron_condor_ai_{ticker.lower()}.pkl"]
    if slug == "rs_credit_spread":
        return ["rs_credit_spread_lag.pkl", "rs_credit_spread_lead.pkl"]
    return [f"{slug}_{ticker}.pkl"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="actually retrain (default is audit only)")
    ap.add_argument("--slug", help="restrict to one strategy slug")
    args = ap.parse_args(argv)

    import sklearn
    print(f"scikit-learn {sklearn.__version__}\n")

    print("── current artifacts ─────────────────────────────────────────")
    rows = audit()
    broken = [n for n, s in rows if s != "OK"]
    for name, status in rows:
        print(f"  {name:<40}{status}")
    print(f"\n  {len(rows) - len(broken)} load, {len(broken)} FAIL\n")

    if not args.apply:
        print("Audit only. Re-run with --apply to retrain.")
        return 1 if broken else 0

    print("── retraining ────────────────────────────────────────────────")
    ok = fail = 0
    for slug, module, cls_name, tickers in RETRAINABLE:
        if args.slug and slug != args.slug:
            continue
        for ticker in tickers:
            print(f"  {slug:<18}{ticker:<6}", end="", flush=True)
            good, msg = retrain_one(slug, module, cls_name, ticker)
            print(("OK   " if good else "FAIL ") + msg)
            ok, fail = (ok + 1, fail) if good else (ok, fail + 1)

    print(f"\n  {ok} retrained, {fail} failed\n")

    print("── artifacts after retrain ───────────────────────────────────")
    rows = audit()
    still = [n for n, s in rows if s != "OK"]
    for name, status in rows:
        print(f"  {name:<40}{status}")
    print(f"\n  {len(rows) - len(still)} load, {len(still)} FAIL")
    if still:
        print("\n  Still unreadable (not covered by this script):")
        for n in still:
            print(f"    - {n}")
    return 0 if not still else 1


if __name__ == "__main__":
    sys.exit(main())
