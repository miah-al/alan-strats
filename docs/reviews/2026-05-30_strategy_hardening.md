# 20-Strategy Hardening — Synthesis & Quant Sign-Off Sheet

**Date:** 2026-05-30
**Branch:** `guide-v5-reorg`
**Status:** Implemented + per-strategy adversarial review. **Awaiting human quant sign-off + backtest re-run.**
**Commits:** NONE — all changes uncommitted, in working tree.

## What was done

A shared **engine realism fix** + per-strategy hardening across 20 strategies, their guide
articles, the registry, and the Dash UI. Every strategy was fixed then adversarially
verified by an independent agent; two that reverted mid-run (iron_condor_ai,
short_squeeze_detector) were re-fixed and re-checked.

### 1. Shared engine (`backtest/engine.py`) — backward-compatible
- `effective_iv(S, K, atm_iv, skew_slope=0.15)` — linear equity-index put skew (OTM puts richer).
- `bs_price_skew(...)` — skew-aware pricer; `skew_slope=0` reproduces flat `bs_price` exactly.
- `DEFAULT_SLIPPAGE_PER_LEG = 0.05`, `DEFAULT_COMMISSION_PER_LEG = 0.65`.
- `bs_price` signature/behavior unchanged → no existing caller broke. Smoke-tested.

### 2. Per-strategy fixes (all 20)
- **Skew pricing** wired into every strategy that prices option legs (19/20; `gex_positioning`
  is SPY/cash allocation — skew N/A, costs applied on rebalance turnover).
- **Transaction costs** (slippage + commission) on BOTH entry and exit, per leg × contracts.
- **Look-ahead**: ffill-only features (no bfill leaks); training windows purged by the
  forward-label window (`cutoff = i - hold/dte`).
- **Correctness**: `X if X is not None else self.X` param resolution (fixes silent drop of
  zero-valued inputs); P&L scaled by contracts; mark-to-market equity; no unreachable stops.
- **Honest metadata/guides**: inflated headline stats removed (esp. iron_condor_ai's 2.38
  Sharpe / 74% win rate), references to the removed `realized_vol_20d` leaked feature purged,
  fabricated numbers replaced with qualitative statements + "TODO: re-run" markers.

### 3. Registry — honest `target_sharpe` where the old number was leak-inflated (e.g. iron_condor_ai → 0.8).

### 4. UI (`dash_app/pages/strategies/`)
- **Found+fixed a real gap:** `vol_calendar_spread` was entirely missing from the selector,
  column map, and backtest-class registry. Now wired (3 files).
- Verified all 20 render with correct labels + review chips; every `get_backtest_ui_params()`
  key maps to a real `backtest()` kwarg (no dead controls); screener columns/formatters safe.

## Verification (final sweep)
- **30 modified Python files parse OK** (ast).
- **20/20 strategies import cleanly** (`alan_trader.strategies.*`).
- **Zero residual `X or self.X` param bugs** across all strategies.
- **No bfill leaks** (the one `bfill` in earnings_pin_risk is `get_indexer(method="bfill")` —
  date→next-bar alignment, not a data fill; correct).

## Change set
~1,400 insertions: 20 strategies + registry, 14 guide articles, 6 UI files, 1 engine file.

---

## Known limitations — needs human quant + re-run (NOT fully fixable in code)

1. **Skew model is a linear approximation**, not a real per-contract chain surface. It makes
   backtests far less optimistic but is not ground truth. *Pending: user-approved cleanup pass
   to bake skew into `bs_price` as the default so coverage doesn't depend on per-strategy wiring.*
2. **All guide headline numbers replaced with TODO markers must be regenerated** from clean,
   cost+skew-inclusive backtests before publishing. No numbers were invented.
3. **VIX-as-single-name-IV** persists in earnings/single-name strategies (earnings_vol_crush,
   earnings_pin_risk) — the backtest still can't fully see single-name IV crush. Flagged in
   each docstring; real fix needs option-chain IV data.
4. **`vol_calendar_spread.backtest()` has a non-standard signature** (`ticker/chains/vix_data`
   positional) vs the `(price_data, auxiliary_data)` convention — the dash runner mis-binds
   `auxiliary_data` to `ticker`. Backend quirk, flagged by UI audit, not fixed (out of UI scope).
5. **Expect reported Sharpe/returns to DROP** across the board once re-run — costs + skew +
   look-ahead purges all remove prior optimism. The new numbers are the honest baseline.

## Sign-off
- [ ] Quant: re-run all 20 backtests with the new engine; record honest baseline metrics
- [ ] Quant: regenerate guide-article stats from those runs (replace TODO markers)
- [ ] Quant: confirm skew_slope=0.15 is a reasonable index default; tune per-asset if needed
- [ ] Decide: bake skew into bs_price as default (cleanup pass) vs keep opt-in helpers
- [ ] Fix vol_calendar_spread backtest signature to the standard convention
