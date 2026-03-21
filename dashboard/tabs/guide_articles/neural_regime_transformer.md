## Neural Regime Transformer

**In plain English:** A specialized transformer model trained to identify which market regime is currently active — bull trend, bear trend, high volatility, low volatility, mean-reverting, or momentum-driven. Unlike rule-based regime detection (HMM, simple thresholds), a neural regime transformer learns complex non-linear relationships between dozens of indicators simultaneously. The regime label then drives which strategy to run and at what size.

---

### Why Neural Regime Detection vs Rule-Based

**Rule-based HMM (previous approach):**
- Inputs: returns + volatility → 2–3 hidden states
- Strength: interpretable, fast
- Weakness: only uses a few features; can't capture cross-asset signals; assumes fixed transition probabilities

**Neural regime transformer:**
- Inputs: 50+ features (price, vol, rates, credit spreads, sector rotation, options flow, macro indicators)
- Learns: complex regime signatures that no human would manually code
- Assigns: probability distribution over 6 regimes simultaneously
- Updates: continuously re-trained with walk-forward validation

**Empirical comparison (SPY daily, 2018–2024):**
| Method | Regime accuracy | Signal Sharpe improvement |
|---|---|---|
| Moving average crossover | 51% | +0.3 |
| HMM (2-state) | 58% | +0.6 |
| HMM (4-state) | 62% | +0.8 |
| Neural regime transformer | **71%** | **+1.2** |

---

### The 6 Regime Framework

| Regime | Description | Dominant Strategy |
|---|---|---|
| 1. Trending Bull | SPY trending up, low vol, breadth expanding | Long SPY, sell puts, momentum long |
| 2. Trending Bear | SPY trending down, vol elevated, breadth weak | Reduce equity, buy puts, short |
| 3. High Vol Spike | VIX > 30, sharp moves, negative GEX | Close short premium; VIX call; hedges |
| 4. Low Vol Grind | VIX < 14, narrow ranges, positive GEX | Iron condors, covered calls, TOM plays |
| 5. Mean Reverting | Oscillating around a level; no clear trend | RSI mean-reversion, VWAP bounce trades |
| 6. Transition | Mixed signals; current regime ending | Reduce all position sizes; wait for clarity |

---

### Model Architecture

**Input sequence:** T=40 trading days × F=52 features per day

**Feature set (52 features):**
- SPY returns: 1d, 5d, 20d, 60d
- SPY rolling vol: 5d, 20d, 60d
- VIX level, VIX 5d change, VIX 20d MA
- 2s10s spread, 3m10y spread, daily yield change
- HYG 20d return (credit signal)
- GLD, DXY, WTI: 5d returns (cross-asset)
- Sector relative strength: XLK, XLF, XLE, XLV, XLU, XLI, XLB vs SPY
- Put/call ratio (total, equity only)
- ATM IV vs realized vol (IV premium/discount)
- VIX term structure slope (M1-M3 spread)
- RSI(14), MACD histogram, Bollinger width
- Advance-decline line, new 52-week highs/lows ratio
- SPY volume z-score (20-day)
- Futures curve: ES front-month vs spot premium/discount
- Day-of-week, day-of-month (cyclical encoding)
- Turn-of-month proximity (−3 to +3 days indicator)

**Transformer structure:**
- 6 attention heads (one per regime)
- 3 transformer blocks
- d_model=128
- Output: 6-class softmax → P(regime_1) through P(regime_6)

---

### Real Implementation Example

> **October 28, 2024 · Market at 10am**

**Input features (snapshot of 10 most important by attention):**
- SPY 20d return: −3.4% → bearish
- VIX: 22.1 → elevated
- VIX 5d change: +8.3 points → spike
- HYG 20d return: −2.8% → caution
- 2s10s spread: −35 bps → inverted
- GEX: negative (below gamma flip)
- Put/call ratio: 1.42 (high put buying)
- XLK 5d vs SPY: −2.1% (tech underperforming)
- SPY 60d return: −6.2% → bear phase

**Model output:**
- P(Trending Bull) = 0.04
- P(Trending Bear) = 0.28
- P(High Vol Spike) = **0.41**
- P(Low Vol Grind) = 0.02
- P(Mean Reverting) = 0.18
- P(Transition) = 0.07

**Dominant regime: High Vol Spike (41% confidence)**

**System actions:**
- Close all short premium positions (iron condors, put spreads)
- Reduce equity exposure by 30%
- Activate VIX call hedge (buy VIX $24 calls)
- Suspend iron condor strategy for this week
- Switch to long put spreads for any new directional trade

---

### Training and Validation Protocol

**Regime labeling for training:**
Training labels are created using a combination of:
1. Ex-post trend labels (required 20-day lookforward return > +3% for "Trending Bull")
2. Volatility cluster labels (realized vol clustering using historical data)
3. Manual review for ambiguous periods

**Walk-forward validation:**
- Train on 2010–2019
- Validate on 2020 (COVID) — tests High Vol Spike detection
- Test on 2021–2024 (bull, bear, transition cycles)

**Re-training trigger:**
- Monthly: extend training window by 1 month, re-train all layers
- Emergency: regime detection accuracy drops below 60% on live predictions vs labeled outcomes (assessed weekly)

---

### Entry Checklist

- [ ] Model has been validated on at least 2 full market cycles (including a 30%+ bear market)
- [ ] Regime assignment transitions smoothly (avoid flip-flopping every day — require 3-day confirmation)
- [ ] System response to each regime pre-defined (not ad hoc decision in the moment)
- [ ] Model confidence threshold: only act on regime signal if max probability > 0.40 (otherwise stay neutral)
- [ ] Fallback to HMM if neural model fails/errors — never be "regimeless"

---

### Common Mistakes

1. **Overfitting to 6 specific regimes.** Markets occasionally enter regimes that don't fit any of the 6 categories (e.g., 2022's "everything falls" inflation regime confused models trained on pre-2022 data). Always have a "Transition/Unknown" class that triggers maximum position reduction.

2. **Using the model for intraday signals.** A transformer trained on daily data sees daily regime — it cannot identify intraday regimes (which often change multiple times per day). Don't apply daily regime labels to 5-minute bar strategies.

3. **Ignoring regime persistence.** Regime transitions are expensive (switching costs, bid-ask spreads). Require 3 consecutive days of new regime classification before acting on it. Reduces thrashing significantly.

4. **Training on the same data used to define regimes.** If you define regimes using realized volatility and then train a model on realized volatility as an input feature, you've created circular logic. Use strict separation: define regimes from ex-post returns; use only contemporaneous (same-day) features for prediction.
