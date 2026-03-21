## Online Adaptive Model

**In plain English:** Traditional ML models are trained once, then deployed frozen. Markets change — what worked in 2018 doesn't work in 2022. An online adaptive model updates its parameters continuously with each new day of data, without needing a full re-training cycle. Think of it as a model that never stops learning. The benefit: it adapts quickly to new regimes (rate hikes, AI boom, crypto cycle) rather than slowly drifting into obsolescence.

---

### The Problem with Batch-Trained Models

**Typical ML pipeline (batch):**
1. Collect data (2010–2020)
2. Train model
3. Deploy (2021)
4. Model slowly degrades as market structure changes
5. Re-train every 6 months (but the 6-month-old model has been underperforming)

**The issue:** Financial models decay faster than almost any other domain. A model trained before 2022's inflation regime will have never seen the relationship between rising rates and falling growth stocks — a historically unusual pattern.

**Online learning solves this** by updating the model daily:
- Each new day's data immediately updates model weights
- Model never drifts far from current market structure
- Adapts to new regimes within days, not months

---

### Online Learning Algorithms for Finance

**Option 1: Online Gradient Descent (simplest)**
After each new day, compute the prediction error and update weights:
```python
prediction = model.predict(features_today)
error = actual_return - prediction
model.weights -= learning_rate × error × features_today
```
Simple but can overfit to recent noise if learning rate is too high.

**Option 2: FTRL (Follow The Regularized Leader)**
Like online gradient descent but with L1/L2 regularization applied online:
```python
# Weights decay toward zero if not supported by recent data
regularized_gradient = gradient + lambda1 * sign(weights) + lambda2 * weights
model.weights -= learning_rate × regularized_gradient
```
Better than simple online GD; preferred for sparse financial features.

**Option 3: Online Boosting (EXP4 algorithm)**
Maintain a pool of "expert" predictors, weight them based on recent performance:
```python
expert_weights = softmax(cumulative_returns_per_expert)
prediction = sum(expert_weights × expert_predictions)
```
Excellent for multi-strategy systems — the best-performing strategy in recent history gets more weight automatically.

---

### Real-World System Architecture

```
Daily close data arrives (4:30pm EST)
    ↓
Feature engineering (52 features)
    ↓
Record today's prediction error (from yesterday's prediction)
    ↓
Online update step (update model with today's label)
    ↓
Generate tomorrow's prediction
    ↓
Position sizing based on prediction confidence
```

The entire update-predict cycle runs in < 10 seconds. No GPU needed (online updates are single samples, not batches).

---

### Real Trade Example: Adapting to 2022 Rate Shock

> **Batch model (trained 2010–2021, not updated):**

The batch model learned: "When 10-year yield rises 20 bps in a month, SPY typically falls 1–2% for rate-sensitive sectors but rises 2–3% for financials."

**In 2022:** This relationship broke. Rising rates AND SPY fell together (Inflation regime — all correlations shifted).

**January 2022:** Batch model signals LONG (falling SPY + rising rates = buy the dip, as per historical pattern). **Wrong.** SPY continues falling.

**Batch model February prediction:** Still signals long (pattern hasn't changed in its training data). **Wrong again.**

By March 2022, batch model has generated 3 consecutive wrong signals.

---

> **Online model (updating daily):**

**January 2022:** Online model starts with the same trained weights (rate up → mildly bullish signal).

**January 10, 2022 (after 10 days of rising rates + falling SPY):**
- Model has observed: rate rise → SPY fell (not rose) × 10 days
- Online update: weight on "rates → bullish" feature is being reduced each day
- New prediction: neutral (model uncertainty increasing)

**January 25, 2022:**
- Model has observed 25 days of rates up / SPY down
- Feature weight for rate-rising as bullish is now near zero
- Emerging pattern: rates up → bearish → model adapts
- Prediction: mild short signal on SPY

**March 2022:** Online model has fully adapted to the new rate-equity regime. Accuracy back to 57% (comparable to training period).

**Net difference vs batch model:** Online model avoided 6 weeks of false long signals; batch model continued giving long signals for 2+ months before manual re-training was triggered.

---

### Catastrophic Forgetting Prevention

The main risk of online learning: **catastrophic forgetting** — the model overwrites old patterns and becomes overly specialized to recent data.

**Solutions:**

1. **Elastic weight consolidation (EWC):** Penalize large changes to weights that were important for past accuracy.

2. **Memory replay:** Keep a buffer of 500 historical samples; when updating on today's data, also replay 20 random historical samples. The model can't completely forget the past.

3. **Learning rate schedule:** Use high learning rate for new regime detection (first 30 days of new regime), then decay to prevent overfitting to regime-specific noise.

4. **Dual-model ensemble:** Run online model + frozen batch model in parallel. Use the online model's recent performance to determine how much weight to give each.

---

### Entry Checklist

- [ ] Online update step implemented and tested (verify model weights change daily)
- [ ] Memory replay buffer: 500+ historical samples, randomly sampled
- [ ] Learning rate: 0.001–0.01 (too high → unstable; too low → doesn't adapt)
- [ ] Compare online model vs frozen model weekly — online should outperform in changing regimes
- [ ] Emergency fallback: if online model accuracy drops below 48% for 10 consecutive days, freeze model and await manual review
- [ ] Logging: record model weights daily for audit trail and debugging

---

### Common Mistakes

1. **Learning rate too high.** A learning rate of 0.1 means the model completely rewrites itself based on the last 10 days. If those days were anomalous (FOMC week), the model will generate garbage signals for weeks. Keep learning rate low (0.001–0.005) for stability.

2. **No memory replay (pure online = pure recency).** A model that only learns from the last 30 days of data will have forgotten all patterns from different regimes. Memory replay is essential to maintain long-run pattern recognition.

3. **Not testing for catastrophic forgetting.** Test your online model by simulating a regime return: after training on 2022 (bear market), does the model still perform well when 2019 (bull market) patterns return? If accuracy collapses on historical holdout data, you have catastrophic forgetting.

4. **Updating during anomalous events.** COVID crash (March 2020) or GameStop squeeze (January 2021) are outliers that would massively distort an online model if used as training data. Implement outlier detection: if today's return is > 5 standard deviations from the 60-day mean, don't update the model today (observe only).
