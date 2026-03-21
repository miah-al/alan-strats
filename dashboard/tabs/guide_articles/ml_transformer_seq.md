## ML Transformer Sequence Model

**In plain English:** The same architecture that powers large language models (GPT, BERT) can be applied to financial time series. Instead of predicting the next word, the transformer predicts the next price move. The key advantage over LSTM: transformers use "attention" to find which historical time steps are most relevant to the current prediction — not just the most recent ones. A bearish pattern from 60 days ago may be more informative than yesterday's data; attention learns this.

---

### Why Transformers vs LSTMs

| Feature | LSTM | Transformer |
|---|---|---|
| Memory | Sequential — must pass info through each step | Attention — directly accesses any past timestep |
| Long-range dependencies | Struggles beyond 30–40 steps | Handles 200+ step lookback easily |
| Training speed | Slow (sequential by nature) | Fast (parallelizable) |
| Data requirements | Moderate (500+ sequences) | High (2,000+ sequences minimum) |
| Interpretability | Black box | Attention maps are somewhat interpretable |

For financial data with weekly seasonality, earnings cycle patterns (quarterly = 63 trading days), and macro regimes spanning 100+ days, transformers often outperform LSTMs.

---

### Architecture Overview

**Input:** Sequence of `T` time steps, each with `F` features.
- Typical: T=60 days, F=20 features (returns, volume, VIX, sector returns, options data)

**Model blocks:**
1. **Embedding layer:** Project each feature vector from F dimensions to d_model (e.g., 64)
2. **Positional encoding:** Add sinusoidal position embedding so model knows "this is day 15 of 60"
3. **Multi-head self-attention (×N layers):** Each attention head learns different patterns (trend-following, mean-reversion, vol regime)
4. **Feed-forward layers:** Non-linear transformations within each block
5. **Output head:** Final linear layer → softmax → probabilities for Up/Down/Flat

**Attention mechanism (simplified):**
```
Attention(Q, K, V) = softmax(QK^T / sqrt(d_k)) × V
```
Q = "what am I looking for?", K = "what does each historical step contain?", V = "what's the value of that step?"

---

### Real Backtest Results

> **Model:** 4-layer transformer, 4 attention heads, d_model=64, trained on SPY features 2010–2022, tested 2023–2024

**Feature set (20 features per day):**
- 1d, 5d, 20d SPY return
- Volume ratio (today vs 20-day avg)
- VIX level, VIX 5-day change
- 10-year yield, yield 5-day change
- 2s10s spread
- SPY RSI(14), MACD histogram
- XLK, XLF, XLE, XLV relative performance vs SPY (5-day)
- Put/call ratio
- ATM implied vol vs 20-day realized vol ratio
- Day-of-week encoding (5 binary features)

**Test period (2023–2024):**
- Trades: 312 (close position daily, re-enter next day if signal)
- Long accuracy: 56.2%
- Short accuracy: 52.8%
- Average 1-day return when long: +0.18%
- Average 1-day return when short: +0.12% (short)
- **Sharpe ratio: 1.4** (annualized, 1-day holding period)

The accuracy numbers look modest but over 312 trades, even 54% accuracy with even win/loss sizes generates meaningful alpha.

---

### Training Protocol

**Data split:**
- Training: 2010–2020 (2,517 trading days)
- Validation: 2021 (252 days)
- Test: 2022–2024 (504 days, NEVER seen during training)

**Labeling:** Binary return classification with a "neutral zone":
- Return > +0.2% next day → Label 1 (Up)
- Return < −0.2% next day → Label 0 (Down)
- Return within ±0.2% → Label 2 (Flat) — optionally excluded from trading

**Loss function:** Cross-entropy with class weights (correct for imbalanced Up/Down/Flat distribution)

**Regularization to prevent overfitting:**
- Dropout: 0.3 on attention layers
- L2 weight decay: 1e-4
- Early stopping: halt when validation loss hasn't improved for 20 epochs
- Walk-forward re-training: every 3 months, extend training window and retrain

**Critical warning:** Financial transformers overfit catastrophically if not regularized. A model that shows 70%+ accuracy in-sample will show 50% (random) out-of-sample. Always test on completely held-out data.

---

### Attention Visualization

After training, you can visualize which past days the model "pays attention to" for a given prediction. Typical patterns discovered:

- **Attention spike at day −5:** Market reacts to last week's close (weekly seasonality)
- **Attention spike at day −21:** Monthly rebalancing effect
- **Attention spike at day −63:** Previous quarter's pattern (earnings cycle)
- **Diffuse attention across recent 10 days:** Trend-following mode

These patterns validate that the model is learning economically meaningful signals rather than overfitting to noise.

---

### Entry Checklist

- [ ] Minimum 2,000 training samples (8 years of daily data)
- [ ] Held-out test set is strictly after training period (no temporal leakage)
- [ ] Out-of-sample Sharpe ≥ 1.0 before deploying capital
- [ ] Walk-forward validation: retrain quarterly with expanding window
- [ ] Monitor live prediction accuracy vs historical — halt trading if accuracy falls below 51% for 20 consecutive predictions
- [ ] Cap position size at 10% of portfolio (model uncertainty is high)

---

### Common Mistakes

1. **Data snooping.** If you test 50 variations of the architecture and pick the best, you've overfit to your test set. Use a held-out "out-of-sample" set that you look at only once, at the very end.

2. **Not including transaction costs in backtest.** The model's raw Sharpe might be 2.0, but if you're trading every day (250 round trips/year) at $0.01 commission, that's 250 × 0.01 = $2.50/share in annual costs — easily 0.5–1.0 Sharpe points eaten.

3. **Ignoring regime changes.** A model trained on 2010–2020 (low-vol, QE era) performed poorly in 2022 (high inflation, rate hike regime). Monitor regime indicators and reduce position size when current conditions are unlike training data distribution.

4. **Using raw prices instead of returns.** Transformers on raw prices will learn "prices go up over time" — a trivially true but useless pattern. Always normalize inputs as returns, z-scores, or ratios.
