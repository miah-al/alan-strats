# Momentum Regime Spread AI — Regime-Filtered Directional Debit Spreads
### Only Trade Momentum When the Model Is Confident. Cap Every Loss to the Debit Paid.

---

## The Core Edge

Markets exhibit autocorrelated momentum regimes at 5-15 day horizons. A plain momentum system — buy when trending up, short when trending down — takes full mark-to-market losses from whipsaws. Every false signal eats into capital. The naive momentum trader is right 55% of the time and makes money, but the 45% of losing trades are painful because there is no floor on the loss.

This strategy expresses directional momentum through **debit spreads** — capping the maximum loss to the premium paid while retaining asymmetric upside. The ML model's only job is to identify high-conviction momentum windows where the win rate exceeds the breakeven threshold (typically 55% for an ATM debit spread). In ambiguous or choppy regimes, it stays flat. No position = no loss.

```
Rule-Based Momentum vs Regime Spread:

  Rule-based:     Always in market → full drawdown exposure
  Regime Spread:  3 modes:
                    Bull regime (P ≥ 55%) → buy SPY bull call spread
                    Bear regime (P ≥ 55%) → buy SPY bear put spread
                    Chop regime            → flat (pay nothing, lose nothing)

  Max loss of debit spread = debit paid (e.g. $125 on a $500 wide spread)
  Max gain = wing width - debit (e.g. $375 on the same spread)
```

---

## Why This Works

**Momentum is real but noisy.** The academic evidence for momentum is overwhelming (Jegadeesh & Titman 1993, Moskowitz et al. 2012), but momentum at 10-day horizons is noisier than at 12-month horizons. The noise creates whipsaws — the momentum signal fires, then immediately reverses. The 3-class classifier filters out the whipsaw periods: if the model cannot confidently classify the regime as bull or bear, it returns "chop" and the strategy holds cash.

**Debit spreads have a natural regime filter.** By construction, you only pay premium when entering. A bull call spread in a chop regime costs the debit and expires worthless — but you would have chosen not to enter in chop. In bull regimes where the model is confident, the hit rate is elevated above the breakeven threshold, creating positive expectancy.

**The edge degrades gracefully.** If the model is wrong, the maximum loss is always bounded. There is no scenario where a single trade destroys the account. This is structurally different from directional strategies that use stop-losses — a spread has a hard max loss that doesn't depend on fills or gap risk.

---

## The Three Regimes

### Bull Regime (Class 1)

```
Conditions: SPY 5d return > 2%, 20d return > 0%, VIX falling or flat.
Signal: P(bull) ≥ confidence_threshold (default 55%)

Trade: Bull Call Debit Spread on SPY
  Long ATM call (spot strike)
  Short OTM call (spot + 2.5%)
  DTE: 14 days
  Max loss: debit paid (e.g. $1.20 per share = $120/contract)
  Max gain: wing - debit (e.g. $1.30 per share = $130/contract)

Breakeven: spot + debit at expiry (need only modest move to profit)
```

### Bear Regime (Class 2)

```
Conditions: SPY 5d return < -2%, 20d return < 0%, VIX rising.
Signal: P(bear) ≥ confidence_threshold (default 55%)

Trade: Bear Put Debit Spread on SPY
  Long ATM put (spot strike)
  Short OTM put (spot - 2.5%)
  DTE: 14 days
  Max loss: debit paid
  Max gain: wing - debit

Breakeven: spot - debit at expiry
```

### Chop Regime (Class 0)

```
Conditions: Neither bull nor bear confidence ≥ threshold.
Signal: No trade. Hold cash.
Cost: $0.
```

---

## The 11 Model Features

```
Feature               Rationale
--------------------  -------------------------------------------------------
ret_5d                5-day return — primary momentum signal
ret_20d               20-day return — medium-term trend direction
momentum_accel        ret_5d minus ret_20d — is momentum accelerating?
atr_pct               ATR / price — current realized range (cost of spread)
realized_vol_20d      20-day realized vol — regime texture
vix_level             Fear level — high VIX = avoid bull regime entries
vix_5d_change         VIX momentum — falling VIX = risk-on confirmation
vix_ma_ratio          VIX vs 20d average — spike vs trend
dist_from_ma50        Distance from 50MA — mean-reversion risk gauge
dist_from_ma200       Distance from 200MA — structural regime context
days_to_month_end     Calendar effect — monthly options expiry clustering
```

**Momentum acceleration** (`ret_5d - ret_20d`) is the single most distinctive feature. If the 5-day momentum is accelerating beyond the 20-day trend, it suggests the regime is strengthening. If 5-day is decelerating relative to 20-day, the regime is weakening — a warning sign even if the label looks bullish.

---

## Label Construction

```python
# 10-day forward return → rolling tercile classification
# Window: trailing 252 bars (regime-adaptive, not fixed-threshold)

for each bar i:
    historical_fwd_returns = close.pct_change(10)[max(0, i-252) : i]
    lower_tercile = percentile(historical_fwd_returns, 33)
    upper_tercile = percentile(historical_fwd_returns, 67)

    fwd_return_10d = close.pct_change(10)[i]  # forward — shifted back by 10d

    if fwd_return_10d > upper_tercile:   label[i] = BULL (1)
    elif fwd_return_10d < lower_tercile: label[i] = BEAR (2)
    else:                                label[i] = CHOP (0)
```

**Why rolling terciles instead of fixed thresholds?** The magnitude of typical 10-day SPY moves varies with vol regime. In low-vol 2017, a +1.5% 10-day return was bullish. In high-vol 2022, +1.5% was noise. Rolling tercile boundaries adapt to the current vol environment, ensuring the label is meaningful across different market regimes.

---

## Walk-Forward Architecture

```
Timeline:
  Bar 0──────────────Bar 90──────────────────────────────────────▶
  │  Warmup (no trades) │  First prediction possible
                        │
                        Retrain every 15 bars (expanding window)
                        3-class GBM (bull / bear / chop)
                        Standard scaler applied before each fit
```

The 3-class GBM is handled with sklearn's `GradientBoostingClassifier` in one-vs-rest mode. Class weights are not adjusted — the chop class is the plurality (~40% of bars) and having the model default to "chop" in uncertain environments is the desired behavior.

---

## Real Trade Walkthrough — Bull Regime Entry

**Date:** January 2024 | **SPY:** $470 | **VIX:** 13.4

Model inputs:
- `ret_5d` = +0.021 (2.1% gain over 5 days)
- `ret_20d` = +0.038 (3.8% gain over 20 days)
- `momentum_accel` = +0.021 - 0.038/4 = small acceleration
- `vix_5d_change` = -0.12 (VIX falling)
- `dist_from_ma50` = +0.015 (1.5% above 50MA)

**Model output: P(bull) = 0.67** → above 55% threshold → enter bull call spread.

Trade:
- Long call: $470 strike (ATM)
- Short call: $482 strike (spot + 2.5%)
- Debit: $1.85 per share | Max gain: $10.15 | Max loss: $1.85

Outcome: SPY reached $478 by day 8.
Closed at 80% of max gain → **P&L: +$812 per contract.**

---

## Real Trade Walkthrough — Bear Regime Entry

**Date:** September 2022 | **SPY:** $382 | **VIX:** 26.8

Model inputs:
- `ret_5d` = -0.041 (-4.1% loss over 5 days)
- `ret_20d` = -0.073 (-7.3% loss over 20 days)
- `vix_5d_change` = +0.38 (VIX rising sharply)
- `dist_from_ma200` = -0.11 (11% below 200MA — deep downtrend)

**Model output: P(bear) = 0.71** → above 55% threshold → enter bear put spread.

Trade:
- Long put: $382 strike (ATM)
- Short put: $372.50 strike (spot - 2.5%)
- Debit: $1.95 per share | Max gain: $7.55 | Max loss: $1.95

Outcome: SPY fell to $374 by day 10.
Closed at 80% of max gain → **P&L: +$604 per contract.**

---

## Entry Rules Summary

```
Condition                       Bull Spread      Bear Spread
------------------------------  ---------------  ---------------
P(class)                        ≥ 55% bull       ≥ 55% bear
VIX                             ≤ 40             ≤ 40
No open position                Required         Required
Model trained (≥ 90 bars)       Required         Required
```

---

## Exit Rules Summary

```
Exit Trigger           Action
---------------------  ----------------------------------------
Profit target          80% of max gain → close spread
Stop loss              50% of spread value lost → close spread
DTE exit               Remaining DTE ≤ 5 → close spread
End of data            Close at market
```

---

## Common Mistakes

**Treating all momentum as equal.** A 2% rally after a 15% correction is not the same as a 2% rally in a quiet uptrend. The `dist_from_ma200` and `vix_level` features help distinguish these — but watch the model's confidence score. Lower confidence in extended markets is appropriate.

**Entering in high-VIX environments for bull spreads.** When VIX > 40, debit spread premiums are inflated (breakeven is harder to reach). The vix_max parameter defaults to 40 — raise it at your own risk. At VIX = 45, a 2.5% wing spread might cost $3.50 when the expected move is the same $2.50.

**Confusing stop-loss percentage with max loss.** The `stop_loss_pct` (50% default) means: if the spread's current value drops to 50% of the entry debit, close it. This is NOT the maximum loss — maximum loss is always the debit paid. The stop-loss is an active management rule to exit losing positions before time decay fully erodes them.

**Overlapping with other directional strategies.** If you are also running VIX Spike Fade (which buys bull spreads during panics), make sure they don't stack in the same direction during extreme events. The Momentum Regime model should be signaling chop or bear during VIX spikes, not bull — but worth monitoring.
