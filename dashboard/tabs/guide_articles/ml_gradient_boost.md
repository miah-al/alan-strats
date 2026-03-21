## Gradient Boost Direction Signal (XGBoost)

**In plain English:** XGBoost is a machine learning algorithm that builds hundreds of small decision trees, each correcting the errors of the previous one. Fed 60+ market features, it learns the most predictive combinations for SPY's 5-day direction — things that no human analyst would spot manually in the noise. It's the tabular-data complement to the LSTM model.

---

### Why XGBoost Instead of Another Neural Network

The LSTM model excels at sequence patterns — it remembers what the market looked like 30 bars ago. XGBoost excels at **feature interactions** — it discovers that "VIX above 25 AND credit spreads widening AND RSI below 40" is a specific combination that historically precedes -2%+ moves, even if each feature alone has no predictive value.

| Comparison | LSTM | XGBoost |
|---|---|---|
| Data structure | Sequences (time series) | Tabular (single-row snapshots) |
| Interpretability | Low (black box) | High (SHAP values per feature) |
| Training speed | Minutes to hours | Seconds |
| Overfitting risk | High (needs sequence data) | Moderate |
| Best at | Pattern recognition over time | Feature interaction discovery |

---

### Feature Set (60 features)

**Price:** 5/10/20/60-day returns, RSI(2), RSI(14), MACD, MACD histogram, Bollinger %B, ATR
**Volume:** OBV, volume ratio (today/30d avg), unusual volume flag
**Macro:** VIX level, VIX 20d change, 2Y yield, 10Y yield, 2s10s spread, HYG spread
**Sentiment:** Put/call ratio, AAII bull-bear spread, news sentiment score (NLP)
**Options:** IV rank, 25-delta put/call skew, 30-day IV vs 1-year IV
**Regime:** Above/below 50-day MA, above/below 200-day MA, golden/death cross flag, HMM regime

---

### Real Trade Walkthrough

> **Date:** Sep 4, 2025 · **XGBoost signal:** P(BULL 5-day) = 0.72

**Top 5 features driving this prediction (SHAP):**
1. RSI(14) = 38 (near oversold) → **+0.18 contribution to bull**
2. VIX down 12% from prior week → **+0.14 contribution**
3. HMM regime = Neutral (not Bear) → **+0.11 contribution**
4. SPY 60-day return = −5.1% (oversold medium-term) → **+0.09**
5. Put/call ratio = 1.3 (elevated fear → contrarian buy) → **+0.08**

With P(BULL) = 0.72 and the LSTM model also showing P(BULL) = 0.65 — ensemble agreement:

**Enter bull call spread:** Buy Oct 3 $548 call, sell $558 call, net debit $3.20

**Sep 19 (15 days):** SPY at $561 (+2.4%)
- Spread at max: **+$680 per contract**

---

### Training Protocol

- Walk-forward validation: train on 3 years, test on next quarter
- Repeat rolling forward 1 quarter at a time
- Report average out-of-sample Sharpe across all test windows
- Never peek at test data during hyperparameter tuning (use cross-validation on train set only)

**Hyperparameters:**
- max_depth: 4–6 (deep enough to capture interactions, not so deep it memorizes)
- learning_rate: 0.01–0.03 (slow learning = better generalization)
- n_estimators: 300–800 (more trees with slower learning rate)
- subsample: 0.8 (only use 80% of data per tree — regularization)

---

### Common Mistakes

1. **Not using walk-forward validation.** A single train/test split on time-series data will dramatically overestimate performance. Use at least 8 rolling test windows.

2. **Ignoring feature leakage.** If any feature uses future information (e.g., "stock went up this week" as a feature when predicting this week), the model will show amazing in-sample performance and fail completely out-of-sample.

3. **Too many features without regularization.** 60 features on a small dataset (3 years = ~750 trading days) can lead to overfitting. Use feature importance to prune to the top 20–30 features, or increase regularization (alpha, lambda in XGBoost).
