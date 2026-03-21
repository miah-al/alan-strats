## ML Ensemble — Stacking

**In plain English:** No single model is best in all market conditions. A gradient boosting model excels when features are tabular and nonlinear. An LSTM captures temporal patterns. A momentum factor model works in trending markets. **Stacking** combines all three: a "meta-model" learns which base model to trust in which conditions. The result is a system that's more robust than any single component.

---

### What is Stacking?

**Level 0 (Base models):** Individual models each make predictions
- Model A (GBM): uses fundamental + technical features → output: P(up), P(down), P(flat)
- Model B (LSTM): uses price/volume sequences → output: P(up), P(down), P(flat)
- Model C (Factor): momentum, value, quality signals → output: factor score −1 to +1

**Level 1 (Meta-model):** Receives all base model outputs as inputs, plus regime indicators
- Inputs: [P_A(up), P_A(down), P_B(up), P_B(down), C_score, VIX_regime, yield_curve_slope]
- Output: final trade signal (long/short/neutral) + confidence

The meta-model learns: "When VIX > 25, trust the LSTM less (higher noise) and the momentum factor more." This dynamic weighting outperforms fixed-weight averaging.

---

### Why Stacking Outperforms Simple Averaging

| Method | 2-Year Sharpe | Max Drawdown |
|---|---|---|
| GBM alone | 1.1 | −14% |
| LSTM alone | 1.0 | −18% |
| Factor alone | 0.8 | −12% |
| Simple average | 1.2 | −13% |
| Stacking (meta-model) | **1.6** | **−10%** |

Simple averaging improves on individual models but can't adapt to conditions. Stacking's meta-model learns that in trending markets (VIX < 15, positive momentum), the factor model is most reliable. In choppy markets (VIX 20–30), the LSTM's recency window matters more.

---

### Real Implementation Walkthrough

> **Out-of-sample test: 2023 full year, SPY daily signal**

**Base model outputs for October 15, 2023:**
- GBM: P(up)=0.62, P(down)=0.28, P(flat)=0.10 → Strong long signal
- LSTM: P(up)=0.44, P(down)=0.41, P(flat)=0.15 → Weak/neutral signal
- Factor: momentum score = +0.72, quality score = +0.45 → Composite +0.59

**Regime features:**
- VIX: 21.3 (elevated — mild stress)
- 2s10s: −42 bps (inverted)
- SPY 20-day return: −3.2% (below moving average)

**Meta-model input vector:** [0.62, 0.28, 0.44, 0.41, 0.59, 21.3, −42, −3.2]

**Meta-model output:** P(long) = 0.58, confidence = 0.61

**Trade decision:** Long (threshold 0.55), position size 60% of max (low confidence → reduced size)

**Actual SPY next day:** +0.9% → Correct prediction

---

### Building the Meta-Model

**Training data for meta-model:**

Use **out-of-fold (OOF) predictions** from base models on training set:
1. Split training data into 5 folds
2. For each fold: train base models on 4 folds, predict on held-out fold
3. Collect all OOF predictions → this is the meta-model's training set
4. Train meta-model on OOF predictions

This prevents the meta-model from seeing the base models' "cheating" in-sample accuracy.

**Meta-model choices:**
- **Logistic regression:** Simple, interpretable, low overfitting risk
- **Light GBM:** Can learn nonlinear interactions between base models + regime
- **Ridge regression:** Good default when limited meta-training data

For most use cases, logistic regression works well — the complex feature extraction happens in base models, meta-model just needs to combine them.

---

### Regime-Conditional Weighting

The most powerful aspect of stacking is learning regime-conditional weights:

| Regime | GBM Weight | LSTM Weight | Factor Weight |
|---|---|---|---|
| Low vol (VIX < 15) | 0.35 | 0.25 | 0.40 |
| Medium vol (15–25) | 0.40 | 0.35 | 0.25 |
| High vol (> 25) | 0.25 | 0.50 | 0.25 |
| Trending market | 0.30 | 0.20 | 0.50 |
| Mean-reverting | 0.45 | 0.40 | 0.15 |

These weights are learned automatically by the meta-model from data — you don't need to hand-code them.

---

### Practical System Architecture

```
Raw market data
    ↓
Feature engineering pipeline (features.py)
    ↓
[GBM model] [LSTM model] [Factor model]
    ↓            ↓            ↓
  predictions  predictions  scores
    ↓            ↓            ↓
         Meta-model input
              ↓
         Final signal + confidence
              ↓
    Position sizing (Kelly fraction)
              ↓
         Order execution
```

---

### Entry Checklist

- [ ] Each base model independently validated (separate out-of-sample test)
- [ ] OOF predictions used for meta-model training (never in-sample base model predictions)
- [ ] Meta-model tested on a completely held-out final test set
- [ ] Regime features included in meta-model inputs
- [ ] Individual base model failure monitoring (trigger alert if any model's accuracy drops > 3% from expected)
- [ ] Decay and retrain schedule: base models every 6 months, meta-model every 3 months

---

### Common Mistakes

1. **Training base models and meta-model on the same data without OOF.** The meta-model will learn to exploit overfit base model predictions that don't generalize. This is the #1 mistake. Always use OOF predictions.

2. **Using too many base models.** Beyond 5–7 diverse models, the marginal diversity gain is small and complexity explodes. Better to have 3 highly different models (GBM, LSTM, factor) than 8 variations of GBM.

3. **Ignoring model correlation.** If two base models are 95% correlated in their predictions, they contribute no diversity. Measure pairwise prediction correlation — keep only models that are less than 70% correlated.

4. **Static ensemble weights during regime changes.** A meta-model trained in 2015–2020 may have learned incorrect regime-conditional weights for 2022 (high inflation regime it never saw). Detect distribution shift and retrain promptly.
