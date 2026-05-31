# Backtest-Integrity Fixes — Quant Sign-Off Sheet

**Date:** 2026-05-29
**Branch:** `guide-v5-reorg`
**Scope:** Look-ahead / metadata-honesty fixes flagged by a strategy code scan.
**Status:** Implemented + passed an adversarial automated quant review. **Awaiting human quant sign-off.**

The scan flagged four items. After reading the actual code, **one was a false positive** and is documented here so it is not "fixed" by mistake. Two were real and are fixed. One is a metadata-honesty change.

---

## 1. `earnings_vol_crush.py` — look-ahead leak — **FIXED**

**File:** `strategies/earnings_vol_crush.py`, retrain block (~line 380)

**The bug.** Labels are `contained over close[j+1 : j+1+h_days]`, so `label(j)` depends on bars up to `j+h_days`. The retrain trained on `labels.iloc[:i]`, whose most-recent row `j=i-1` referenced `close[i .. i+h_days-1]` — the decision bar `i` and up to `h_days-1` bars **after** it. With default `h_days=10`, the model saw up to 10 future bars (including the present). Classic missing-purge look-ahead → optimistic backtest.

**The fix.** Purge the last `h_days` bars from each training window:
```python
cutoff = max(0, i - h_days)
X_tr = feat_df.iloc[:cutoff][self.FEATURE_COLS]
y_tr = labels.iloc[:cutoff]
ev_mask = earnings_gaps.iloc[:cutoff]
```
**Purge length is tight (verified, not off-by-one).** Requirement for `label(j)` to be known strictly before bar `i`: `j + h_days < i ⟺ j ≤ i - h_days - 1`. `iloc[:cutoff]` with `cutoff = i - h_days` includes max `j = i - h_days - 1`, whose label closes at bar `i-1 < i`. ✓ (`i - h_days + 1` would reintroduce a one-bar leak; `i - h_days - 1` would needlessly drop a valid row.)

**Expected impact.** Reported Sharpe / win-rate for this strategy will **drop** post-fix (the leak was inflating them). Re-run the backtest and treat new numbers as the real baseline.

---

## 2. `iron_condor_ai.py` + `registry.py` — `target_sharpe` 1.8 → 0.8 — **FIXED**

**Files:** `strategies/iron_condor_ai.py` (~line 270), `strategies/registry.py` (iron_condor_ai entry)

**The issue.** The 2026-05 audit already removed the `realized_vol_20d` feature/label leak and documented (iron_condor_ai.py lines 277-280) that the honest post-fix Sharpe is **~0.5–0.9**, but the advertised `target_sharpe` still read the discredited pre-audit **1.8** in both the class attribute and the registry.

**The fix.** Both set to **0.8** (upper-middle of the honest band), with a comment pointing to the audit and marking it subject to quant confirmation.

**Safe to change (verified).** `target_sharpe` is **display-only** — surfaced in `registry_dataframe()` and dash cards. No risk-sizing, Kelly, ranking, gating, or allocation code reads it. No other hardcoded `1.8` for this strategy exists (registry, class, dash status map, strategy articles, guides all checked).

---

## 3. `rs_credit_spread.py` — alleged "ffill leak" — **FALSE POSITIVE, NO CHANGE**

**File:** `strategies/rs_credit_spread.py`, line ~375

**Claim (rejected).** A scanner claimed `s.reindex(spy_close.index).ffill()` leaks future sector returns backward into early dates.

**Why it's wrong.** `ffill` propagates the **most recent prior** value forward (past → present); it is structurally impossible for it to move a future value to an earlier index. The leak description actually matches `bfill`, which is **not** used. The code already carries a defensive comment (lines 372-374) explaining exactly this, and its training cutoff (line 471, `cutoff = max(0, i - h_days)`) correctly purges the label window. Leading all-NaN dates are excluded by `notna().all(axis=1)` and the inference NaN guard — no silent fill-from-future. Independent quant re-derivation agreed: **no leak; correctly left unmodified.**

**Out-of-scope future note (not a bug):** rs_credit_spread trains labels on `main_ticker` only (lines 390-398) then applies the model across all sectors at inference — a model-generalization question worth a later look, *not* a look-ahead issue.

---

## Automated review result

An adversarial automated quant review independently re-derived all four conclusions:

| Change | Verdict |
|--------|---------|
| earnings_vol_crush purge | CONFIRMED-CORRECT (real material leak; purge exactly tight; no other leak paths) |
| iron_condor_ai Sharpe 1.8→0.8 | CONFIRMED-CORRECT (display-only field; value within honest band) |
| rs_credit_spread (no-fix) | CONFIRMED-CORRECT (ffill is past→present; claim was inverted) |

No blocking issues found. All edits syntax-checked (`ast.parse` OK, UTF-8).

## Follow-ups surfaced by the review (out of scope — not changed)

1. **`dash_app/guide_articles/iron_condor_ai.md` (lines ~596-602) still advertises an annualized Sharpe of 2.38** ("excellent for options strategy"). This is the same pre-audit, leak-inflated number we just corrected in code — now even more optimistic and *user-facing*. Fixing it properly means re-deriving the worked example from a clean (post-purge) backtest, so it needs the quant's re-run output. (A near-identical `_iron_condor_ai.md` draft duplicates the claim.)
2. **`strategies/earnings_vol_crush.py` docstring (line ~17)** says "Warmup: 90 events / Retrain every 15," but the actual constants are `_WARMUP_EVENTS=30` / `_RETRAIN_EVERY=10`. Harmless but stale — quick truthful fix whenever convenient.

## Sign-off

- [ ] Quant: confirm earnings_vol_crush purge logic & re-run backtest for the new (lower) baseline
- [ ] Quant: confirm iron_condor_ai target_sharpe value (0.8 vs 0.7 midpoint)
- [ ] Quant: acknowledge rs_credit_spread false-positive (no change)
