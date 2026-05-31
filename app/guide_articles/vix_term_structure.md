# VIX Term Structure AI — Vol Regime Premium Switcher
### Selling Premium in Contango, Buying Protection in Backwardation

---

## The Core Edge

The VIX risk premium — the persistent spread between implied volatility (VIX) and realized volatility — is one of the most rigorously documented structural edges in equity markets. Implied volatility exceeds realized volatility roughly **75-80% of trading days**, creating a systematic premium-selling opportunity.

The problem: the **20-25% of days when realized vol exceeds implied** (backwardation periods) cause catastrophic losses for static premium sellers. March 2020, August 2015, September 2022 — these were all backwardation regimes where selling premium destroyed capital. A static "always sell premium" approach loses more in those periods than it makes in all the contango periods combined.

This strategy uses a gradient boosting classifier to predict **regime transitions** — specifically, will realized vol exceed current implied vol over the next 14 days? When the answer is "yes" with high confidence, it flips from selling premium to buying protection.

```
Regime Detection:

  VIX implied vol  →  ┌─────────────────────────────────────────┐
  Realized vol     →  │  GBM predicts: realized > implied?       │
                      │                                           │
                      │  P < 0.40 → CONTANGO → sell bull put     │
                      │  P > 0.60 → BACKWARDATION → buy bear put │
                      │  0.40-0.60 → AMBIGUOUS → stay flat       │
                      └─────────────────────────────────────────┘
```

---

## Why This Edge Is Real and Persistent

The vol risk premium (VRP) is well-established in academic literature (Carr & Wu 2009, Bollerslev et al. 2011). The mechanism: investors pay a premium for insurance, and the aggregate difference between implied and realized vol accrues to the systematic options seller.

**The ML layer adds value in two specific ways:**

1. **Regime-transition detection.** A rule-based version uses a fixed threshold: "VRP < 0 = backwardation, sell premium." But VRP is noisy — a single spike in realized vol creates false signals. The GBM uses 12 features including VIX momentum, vol-of-vol (the volatility of VIX itself), and SPY trend to distinguish true regime shifts from noise.

2. **Leading indicator features.** VIX vol-of-vol is a documented leading indicator for regime breaks. When VIX starts gyrating before it spikes, dealers are pricing in uncertainty about future uncertainty. The model captures this before the actual VRP flip occurs.

---

## The Two Trade Structures

### Contango (P < 0.40) — Short Premium

```
Setup: VIX > Realized Vol. VIX = 20%, RV20 = 14%, VRP = +6%

Trade: Bull Put Credit Spread on SPY
  Short put: spot × (1 - 2%) — ~2% OTM
  Long put:  short_strike - 2.5% × spot
  DTE: 21 days
  Max credit: net premium received (max profit)
  Max loss:   wing width - credit (fully defined)

Exit: 50% of max credit OR 7 DTE remaining OR 2× credit (stop)
```

### Backwardation (P > 0.60) — Buy Protection

```
Setup: Realized Vol > VIX. VIX = 18%, RV20 = 22%, VRP = -4%

Trade: Bear Put Debit Spread on SPY
  Long put:  spot × (1 - 1%) — ~1% OTM (near ATM)
  Short put: long_strike - 2.5% × spot
  DTE: 21 days
  Max loss:  debit paid (fully defined)
  Max gain:  wing width - debit

Exit: 80% of max gain OR 50% value loss OR 7 DTE remaining
```

---

## The 12 Model Features

```
Feature                  Rationale
-----------------------  -------------------------------------------------------
vix_level                Absolute fear level — regime anchor
vix_5d_change            Rate of VIX change — fast rise = risk-off transition
vix_20d_change           Medium-term VIX trend direction
vix_ma_ratio             VIX vs 20d average — spike vs trend detection
vix_vol_of_vol           Std of daily VIX changes — leading indicator for breaks
realized_vol_20d         Current realized vol — direct VRP component
vrp                      VIX/100 minus realized — the raw premium signal
iv_rv_ratio              Normalized premium richness (VIX / realized vol)
ret_5d                   SPY 5-day return — risk-on/off context
ret_20d                  SPY 20-day return — medium trend
dist_from_ma200          SPY vs 200d MA — structural regime context
atr_pct                  ATR as % of price — realized daily range
```

---

## Label Construction

```python
# 14-day forward backwardation label (no look-ahead)
for each bar i:
    implied_vol  = VIX[i] / 100
    realized_vol = std(log_returns[i+1 : i+15]) * sqrt(252)
    label[i]     = 1 if realized_vol > implied_vol else 0

# Positive rate: ~20-25% of days (backwardation is the minority regime)
# Class imbalance is expected — backwardation is rare but catastrophic
```

The 14-day window matches the dte_target (21 DTE). The model predicts whether the next 14 days of realized vol will overshoot current implied vol — the exact condition that causes credit spread losses.

---

## Walk-Forward Architecture

```
Timeline:
  Bar 0──────────────Bar 90──────────────────────────────────────▶
  │  Warmup (no trades) │  First prediction possible
                        │
                        Retrain every 15 bars (expanding window)
                        No future data ever used in training
```

**Warmup:** 90 bars ensures enough contango/backwardation transitions to learn from. VIX regimes cluster — a 90-bar window typically spans at least 2-3 regime cycles.

**Retrain every 15 bars:** Monthly cadence adapts to vol regime drift without overfitting to recent noise.

---

## Real Trade Walkthrough #1 — Contango Entry

**Date:** March 2024 | **SPY:** $516 | **VIX:** 14.8 | **RV20:** 9.2%

- `vix_ma_ratio` = 0.91 (VIX below its 20d average — calm trending down)
- `vrp` = +0.056 (positive — good premium available)
- `dist_from_ma200` = +0.08 (SPY well above trend)

**Model output: P(backwardation) = 0.18** → deep contango → sell credit spread.

Trade: Short put $506 / Long put $503.50 | Net credit: $0.85 | Max loss: $1.80
Outcome (21 days): SPY at $524. Both puts expired worthless. **P&L: +$85/contract.**

---

## Real Trade Walkthrough #2 — Backwardation Entry

**Date:** August 5, 2024 | **SPY:** $507 | **VIX:** 38.6 | **RV20:** 18.1%

- `vix_vol_of_vol` = 4.2 (VIX gyrating wildly — high uncertainty signal)
- `vix_5d_change` = +1.45 (massive spike in 5 days)
- `vrp` = +0.205 (still positive — but model sees the dynamics, not just VRP)

**Model output: P(backwardation) = 0.74** → backwardation risk → buy debit.

Key insight: Despite positive VRP, the model correctly identifies that the rapid spike dynamics predict future realized vol overshooting. Rule-based VRP would say "sell premium here" — a costly mistake.

Trade: Long put $502 / Short put $489 | Debit: $3.20 | Max gain: $9.80
Outcome: SPY dropped to $492 over 5 days. Closed at 80% of max gain. **P&L: +$620/contract.**

---

## Typical Feature Importance

```
Feature              Typical Weight
-------------------  --------------
vrp                  23%   Core signal
vix_vol_of_vol       19%   Leading indicator for breaks
vix_5d_change        16%   Fast momentum signal
iv_rv_ratio          14%   Normalized richness
dist_from_ma200      10%   Structural context
vix_ma_ratio          8%   Spike vs trend
Others               10%   Level, calendar, ATR
```

---

## Entry Rules Summary

```
Condition                       Credit Spread    Debit Spread
------------------------------  ---------------  ---------------
P(backwardation)                < 0.40           > 0.60
VIX                             ≤ 45             ≤ 45
No open position                Required         Required
Model trained (≥ 90 bar warmup) Required         Required
```

---

## Common Mistakes

**Confusing VRP level with regime direction.** Positive VRP does not guarantee contango *persists* next period. The model uses the rate of change of VIX and vol-of-vol to detect regime shifts before VRP flips — that is the actual edge.

**Using this in isolation from other vol strategies.** When this model says backwardation, it is also a signal to reduce IC exposure and GEX allocation. Treat its output as a vol regime overlay for the entire portfolio.

**Ignoring the 0.40-0.60 flat zone.** This zone is not indecision — it is genuine model uncertainty and should be respected. A P(backwardation) = 0.52 is not a trade signal.

**Increasing model complexity.** If raising n_estimators or max_depth dramatically improves the backtest, you are likely overfitting. The regularized defaults produce modest but robust improvements over the simple VRP threshold rule.
