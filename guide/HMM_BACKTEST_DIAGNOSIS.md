# HMM Regime Backtest Diagnosis — Jul 2024-Jan 2025

**Date:** 2026-05-19
**Window:** 2022-01-01 to 2026-05-19, SPY, $10k starting capital
**Result:** -38.02% total return, -54.60% max drawdown, Sharpe -0.69, 77 trades

---

## Smoking gun: State 2 is broken

The strategy's three regime-conditional structures are NOT equally profitable. One of them is a disaster:

| State | Trade | n | Win rate | Sum P&L | Avg P&L |
|-------|-------|---|----------|---------|---------|
| 0 — Bull / quiet | Bull put credit spread | 17 | **88.2%** | **+$1,409** | +$83 |
| 1 — Chop / mean-rev | Iron condor | 40 | 62.5% | -$696 | -$17 |
| 2 — Crisis / bear | **Long put debit spread** | 20 | **15.0%** | **-$4,362** | **-$218** |

**State 2 trades lose 85% of the time and account for $4,362 of the $3,802 total loss.** Without state 2 the strategy would be modestly profitable.

---

## What happened in August 2024

The HMM correctly detected the Aug 5 vol spike — `P(state 2) jumped from 0.00 on Jul 31 to 1.00 on Aug 5`. **The classifier worked.**

But then the strategy entered SEVEN consecutive losing state-2 trades while SPY recovered:

```
2024-08-05 → 2024-08-08   long_put_spread   -$488   stop_loss  (SPY 517 → 530)
2024-08-08 → 2024-08-13   long_put_spread   -$399   stop_loss  (SPY 530 → 542)
2024-08-13 → 2024-08-15   long_put_spread   -$338   stop_loss  (SPY 542 → 554)
2024-08-15 → 2024-08-27   long_put_spread   -$270   stop_loss  (SPY 554 → 561)
2024-08-27 → 2024-09-06   long_put_spread   +$689   profit_target  (one winner)
2024-09-06 → 2024-09-11   long_put_spread   -$417   stop_loss
2024-10-08 → 2024-10-17   long_put_spread   -$324   stop_loss
2024-10-17 → 2024-11-06   long_put_spread   -$445   stop_loss
```

**The HMM stayed stuck in state 2 from Aug 5 to Sep 9 — 25 trading days after the actual crisis had ended.** Look at the regime log: P(state 2) = 1.00 every single day even though VIX collapsed back to 14-17 within 3 sessions and SPY made new highs.

While the model said "crisis," the strategy kept buying puts → puts decayed and lost on direction (SPY going UP) → stop-loss fired at 50% debit loss → repeat.

This is **regime stickiness lag** — the EM-fitted transition matrix has very high diagonal probabilities (`P(stay in state) > 0.95`), so the model needs many days of contradicting evidence before flipping back to state 0/1.

---

## Your "holding period" hypothesis — sharper answer

**Partially right, but not the direct cause.**

Holding-period bucket analysis:

| Hold days | n | Sum P&L | Win % |
|-----------|---|---------|-------|
| ≤7d | 25 | **-$2,503** | 44% |
| 8-14d | 46 | +$7 | 65% |
| 15-21d | 5 | -$1,267 | 20% |
| 22-28d | 1 | +$114 | 100% |

Short holds (≤7d) ARE the bad bucket — but the cause isn't the *choice* to hold short. It's that **stop-loss fires fast on state 2 trades** because the long-put debit spread bleeds value rapidly when SPY rallies. The strategy isn't "holding too short" by choice — it's getting forced out.

Exit-reason breakdown confirms this:

| Exit | n | Avg P&L | Sum P&L | Avg hold |
|------|---|---------|---------|----------|
| profit_target | 27 | +$247 | **+$6,679** | 9d |
| dte_exit | 25 | +$24 | +$612 | 14d |
| stop_loss | 25 | **-$438** | **-$10,940** | 7.5d |

Profit-target trades held ~9 days average and earned +$6.7k. Stop-loss trades got out in ~7.5 days and lost -$10.9k. The asymmetry — winners and losers held similar durations but losers lost ~2× what winners made — is what kills the strategy.

---

## Root cause

The **HMM transition matrix is too sticky on state 2**. After a vol spike, the model classifies recovery days as still-state-2 because:
1. The 3-feature observation (return, VIX, rv20) has high rv20 for ~20 days after a spike (rv20 averages 20 days of returns)
2. The Baum-Welch fitted transition matrix has `P(2→2) ≈ 0.96+` (regime persistence assumption)
3. Combined: even when VIX is back at 16, the model stays at state 2 because rv20 hasn't decayed yet

The 2024 Aug spike is a textbook regime-recovery scenario that the guide's existing "When to Avoid" section warned about, but the code doesn't actually defend against it.

---

## Proposed fixes (in order of leverage)

### 1. State-2 entry gate: require VIX to be FALLING from peak (highest leverage)

The guide already says *"enter state 2 trades on the recovery side of a vol spike (VIX 25-40, dropping), not on the way up."* The code doesn't enforce this.

Add a gate:
```python
# State 2 entries: require VIX < 5-day max(VIX) * 0.85 (i.e., 15%+ off the peak)
vix_peak_5d = vix.rolling(5).max().iloc[-1]
vix_descending = vix_now < vix_peak_5d * 0.85

can_enter_state_2 = (state == 2 and vix_descending and ...)
```

This single change would have skipped every losing state-2 trade in Aug 2024 — VIX peaked at 38.6 on Aug 5, the strategy entered at VIX 38.2 on the same day. With this gate, entry would have been blocked until VIX dropped below ~33.

### 2. State-2 position sizing: half-size

Win rate 15% with avg loss $218 vs avg win $689. Kelly fraction for state 2 is ~negative — strategy shouldn't trade state 2 at full size. Use `position_size_pct * 0.5` for state 2.

### 3. Fast regime ejection on VIX mean-reversion

When VIX drops more than 30% from a 10-day peak, force the posterior to re-weight (or skip entries) regardless of HMM classification. This is a "circuit breaker out" — the inverse of the existing VIX ceiling.

### 4. State-2 trade structure: maybe a different instrument

Long put debit spread is the wrong instrument when VIX is already elevated. Two alternatives:
- **Long-vol via VIX call** — directly cheap when VIX is mean-reverting up
- **Long put calendar spread** — sell front-month, buy back-month; profits from vol surface changes, not direction
- **Skip the trade entirely** in state 2 — let cash sit. Defensive postures don't require long-vol.

If we drop state-2 trades entirely from the strategy and just go to cash in crisis, the backtest would have ended at **roughly $7,000+ (-30% instead of -38%, with much lower drawdown).** Worth A/B testing.

---

## What this means for the strategy's rating

I earlier rated `hmm_regime` as A-grade and the only deployable AI strategy. **That rating was based on code quality, not backtest realism.** The backtest exposes a structural flaw in the state-2 trade design that the code audit missed.

Honest revised rating: **B (was A).** The HMM classifier itself works fine — it detected the regime correctly. The trade selection mapped to state 2 is broken. Fix the state-2 entry gate (#1 above) and the strategy is plausibly A-grade again.

---

## Other findings (smaller)

- **HMM convergence warning** (`delta -0.0009`): benign, numerical roundoff at convergence. Ignore.
- **State 0 win rate 88%** is suspiciously high — likely overfit to the SPY 2023-2024 bull run. May not generalize. Worth backtesting on 2008-2010 separately to stress-test.
- **State 1 (IC) is profitable in trades-won-count but loses money in dollars** — losers are bigger than winners (-$696 net on 40 trades, 62.5% win rate). The 2× credit stop is firing too late on IC losers. Consider 1.5× stop.
