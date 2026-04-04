# Online Adaptive Model
### The Model That Never Stops Learning: Surviving Regime Shifts by Updating Daily

---

## Detailed Introduction

The history of quantitative finance is littered with models that worked brilliantly in backtests, performed acceptably in the first year of live trading, and then slowly degraded into irrelevance. The cause is almost always the same: the market's statistical relationships changed, and the model did not. A model trained on 2010-2020 data learned that rising 10-year yields coincided with mild equity strength (financial sector leading). In 2022, rising yields caused equity market destruction. The trained model could not know this relationship had inverted; it was frozen in time, applying patterns that no longer existed.

This is not a failure of model design or implementation — it is a fundamental property of financial markets. Unlike natural science, where physical laws are constant, financial "laws" are social conventions that change as participants, regulations, technology, and macro regimes evolve. The zero-interest-rate era of 2009-2021 created a specific set of correlations and patterns that cannot be expected to persist indefinitely. When that era ended, the statistical models trained on it became obsolete — some quickly, some gradually, but all eventually.

Online learning is the framework for building models that adapt in real time rather than batch-retrain periodically. Instead of training once and freezing, an online model updates its parameters every day when new labeled data arrives (yesterday's features are now matched with yesterday's actual outcome). The update step is small — controlled by a learning rate parameter — so a single anomalous day does not destroy the model's accumulated knowledge. But over weeks and months, the model continuously drifts toward current market reality, maintaining relevance in ways that batch-trained models cannot.

The behavioral intuition is a practitioner who updates their mental model daily. After every trade closes, they revisit: did my thesis work? What did I miss? What new pattern emerged? The online model does this systematically and without the cognitive biases (anchoring, confirmation bias, loss aversion) that distort human updating. The model updates its understanding of which features currently predict future returns, without being influenced by whether the last trade made money or whether the hypothesis was intellectually satisfying.

The one thing that kills online learning is catastrophic forgetting: the model is updated so aggressively on recent data that it overwrites its accumulated historical knowledge. A model that forgets what bear markets look like because it was trained during a three-year bull run will be completely unprepared when bear-market conditions return. Memory replay — periodically retraining on a randomly sampled buffer of historical data alongside current data — is the primary defense. The goal is a model that is responsive to current conditions without amnesiac disregard for historical patterns.

---

## How It Works

The online model starts with weights trained on historical data. Each day, after market close, it observes the labeled outcome (what actually happened) for the prediction made on the previous day. It updates its weights by a small gradient step in the direction that would have reduced the prediction error. Tomorrow's prediction uses the updated weights.

**Online gradient descent (simplified):**

```python
# Daily update cycle (runs at 4:30pm after close):
prediction_yesterday = model.predict(features_yesterday)
actual_outcome_today = today_close_return  # observed label
error = actual_outcome_today - prediction_yesterday

# Online weight update (FTRL with regularization):
gradient = error × features_yesterday
regularized_gradient = gradient + λ1 × sign(weights) + λ2 × weights
weights -= learning_rate × regularized_gradient

# Memory replay: also update on 20 random historical samples
for _ in range(20):
    hist_features, hist_outcome = random.sample(history_buffer)
    hist_error = hist_outcome - model.predict(hist_features)
    weights -= 0.3 × learning_rate × hist_error × hist_features

# Generate tomorrow's prediction with updated weights
tomorrow_prediction = model.predict(features_today)
```

**Key hyperparameters:**

```
learning_rate:   0.001 – 0.005
  Too high (> 0.01):  model overwrites itself on each day's noise
  Too low (< 0.0005): model adapts too slowly, behaves like a batch model

λ1 (L1 regularization): 0.0001  [sparsity — prune irrelevant features]
λ2 (L2 regularization): 0.001   [shrinkage — prevent extreme weights]

memory_replay_ratio: 20 historical samples per 1 new observation
memory_buffer_size:  500 historical samples (rolling, replace oldest)

outlier_detection:  if |today_return| > 5 × std(60d), skip the update
                    (don't let black-swan events distort the model)
```

---

## Real Trade Example

**The 2022 rate shock — batch model versus online model.**

**January 2022 baseline:**
Both models start the year with weights trained through December 2021. Both have learned: "Fed tightening cycle approaching, but market pricing is benign; rate sensitivity is mild at current levels."

**January 10 - January 25, 2022 (10 trading days of rising yields + falling SPY):**

*Batch model behavior:*
Week 1: Signal = mild long (historical pattern: rate rise → mild bullish for financials → slight SPY positive). Wrong. SPY falls 3%.
Week 2: Signal = mild long again. Still wrong. SPY falls another 2%.
Model shows 2 consecutive wrong signals but makes no update. It will be manually retrained in 6 months.

*Online model behavior:*
Day 1-5: Same initial signal as batch model. Wrong. Error registered. Weight on "rate-rise → bullish" feature reduced slightly each day.
Day 6-10: Weight has been reduced 5 times. Model moves from mild long to neutral. Accuracy recovering.
Day 11-15: Model has fully inverted the rate-equity relationship for the current feature set. Generates short signal when yields spike. Accuracy: 58% (back to normal range).

**Net difference through March 2022:**
Batch model: 8 consecutive incorrect long signals, accumulating -11% loss before manual retrain.
Online model: 10-day adaptation period, then correct alignment with new regime. -2.4% loss during adaptation, then profitable.

**Cumulative P&L difference:** Online model saved approximately 8.6 percentage points by adapting in 10 days rather than waiting 5+ months for a batch retrain.

---

## Entry Checklist

- [ ] Initial model trained on at least 10 years of historical data (not starting from zero)
- [ ] Online update step implemented and verified daily (check that weights change each day)
- [ ] Learning rate set in range 0.001-0.005 (tested for stability on historical data)
- [ ] Memory replay buffer: 500 samples, randomly drawn, updated with FIFO
- [ ] Outlier detection: skip update if today's return is > 5 standard deviations from 60-day mean
- [ ] Frozen batch model running in parallel for comparison (benchmark for online model improvement)
- [ ] Weekly comparison: online model accuracy vs frozen batch model over rolling 20 days
- [ ] Emergency freeze: if online model accuracy falls below 48% for 10 consecutive predictions, halt updates and await manual review
- [ ] Weight logging: record model weights daily for audit trail and debugging catastrophic forgetting

---

## Risk Management

**Max loss per trade:** Defined by the debit spread structure. The online model's changing weights affect which trades are entered, not the maximum loss per trade.

**Stop loss rule on model performance:** If the online model's rolling 20-day accuracy falls below 50% AND the batch model's accuracy is above 52% over the same period, switch immediately to the batch model and halt online updates. The online model has overfit to recent noise or is in catastrophic forgetting mode.

**Outlier event protection:** Black-swan events (COVID crash, flash crash, war outbreak) generate extreme outcomes that should not be allowed to dominate the online model's update. Implement hard outlier detection: if the day's SPY return is more than 5 standard deviations from the 60-day rolling mean, skip the online update entirely for that day. Observe but do not update.

**Position sizing:** Scale position size with the online model's rolling accuracy: when rolling 20-day accuracy exceeds 58%, use 100% of target position. At 54-58%, use 75%. At 50-54%, use 50%. Below 50%, halt trading.

**When it goes wrong:** Catastrophic forgetting during a prolonged one-directional period. If the market trends in one direction for 60+ days (2017's steady bull, 2022's steady bear), the online model may fully adapt to that regime and forget historical patterns that should still be active. The memory replay buffer is the primary defense, but review the weight history quarterly for signs of extreme drift from initial trained weights.

---

## When to Avoid

1. **Learning rate above 0.01:** A learning rate this high means the model can completely rewrite itself within 10 days. During a volatile period like FOMC week, one anomalous week can destroy months of learned patterns. The instability threshold begins at 0.01; anything above 0.02 is undeployable.

2. **No memory replay (pure recency bias):** An online model with no memory replay will eventually forget all historical patterns and become a short-term noise follower. Without periodic exposure to historical samples, the model's long-run accuracy will degrade to random over 6-12 months.

3. **Updating during index reconstitution days:** Major index rebalances (Russell reconstitution in late June, quarterly index reconstitutions) create one-day flow distortions that are not predictive of forward returns. Updating the model based on these distorted outcomes teaches the model a false pattern.

4. **Deploying without the frozen batch model benchmark:** Without a parallel batch model running simultaneously, there is no reference point for evaluating whether the online model is genuinely adapting to new information or overfitting to noise. The comparison is essential for confident live deployment.

5. **More than 30 days since manual validation:** Even though the model updates automatically, a human practitioner should review model accuracy, weight distributions, and prediction quality at minimum every 30 days. Automated monitoring catches obvious failure modes; manual review catches subtle drift that automation misses.

---

## Strategy Parameters

| Parameter | Default | Range | Description |
|---|---|---|---|
| Base training window | 10 years | 8–15 years | Historical training before online phase begins |
| Learning rate | 0.002 | 0.001–0.005 | Daily parameter update step size |
| λ1 (L1 regularization) | 0.0001 | 0.00005–0.001 | Sparsity regularization |
| λ2 (L2 regularization) | 0.001 | 0.0005–0.005 | Shrinkage regularization |
| Memory replay ratio | 20:1 | 10:1–50:1 | Historical samples per new observation in each update |
| Memory buffer size | 500 samples | 200–2000 | Rolling historical sample pool |
| Outlier detection | 5 × 60d std | 3–7 std | Returns beyond this skip the update |
| Emergency freeze | 48% accuracy, 10 days | Firm | Halt online updates, switch to batch |
| Position size by accuracy | 50/75/100% | Scales | At 50-54% / 54-58% / >58% rolling accuracy |
| Weight logging | Daily | Required | Audit trail for drift detection |
| Manual review frequency | Every 30 days | 14–60 days | Human validation cadence |
| Algorithm | FTRL | FTRL / online GD | FTRL preferred for financial features |
| Feature count | Same as base model | Match base | Online updates all features from base model |
