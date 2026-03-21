## Regime Classification — Hidden Markov Model (HMM)

**In plain English:** Markets don't behave the same way all the time. A bull market, a choppy sideways market, and a bear market all feel completely different — and strategies that work in one regime fail badly in another. The HMM is a machine learning model that reads market data every day and quietly assigns a label to the current regime: Bull, Neutral, or Bear. Every other strategy then uses this label to decide whether to be aggressive, cautious, or defensive.

---

### Why Regime Matters More Than Most Traders Realize

Consider these two facts:
- A bull put spread strategy backtested from 2012–2024 shows Sharpe 1.4 — impressive
- The same strategy backtested only during bear market periods (2022, 2008 second half) shows Sharpe −2.1 — catastrophic

The single biggest performance lever for any strategy is: **are you trading in the right regime?** The HMM's job is to answer that question every day.

**Historical SPY returns by regime (illustrative):**

| Regime | % of Days | Avg Daily Return | Avg Daily Vol | What it Feels Like |
|---|---|---|---|---|
| Bull | 55% | +0.08% | 0.65% | Steady grind higher, dips get bought |
| Neutral | 25% | +0.01% | 0.90% | Choppy, no clear trend, high dispersion |
| Bear | 20% | −0.15% | 1.40% | Trending down, bounces fail, high vol |

A strategy that earns +0.15%/day in Bull regime and −0.30%/day in Bear regime, if naively traded all the time, would average only +0.05%/day. But gated to Bull-only, it earns +0.15%/day consistently.

---

### What is a Hidden Markov Model?

The market "state" (bull/neutral/bear) is hidden — you can't directly observe it. You only observe the outputs (price moves, vol, spreads). The HMM assumes:

1. The market is always in one of 3 hidden states
2. Each state has a characteristic distribution of daily returns and volatility
3. The market transitions between states with certain probabilities (e.g., Bull → Neutral: 8% per day; Bear → Neutral: 15% per day)
4. Given the last 60 days of observed market data, we can estimate the current hidden state with a probability

The HMM uses the **Baum-Welch algorithm** to learn the state distributions and transition probabilities from historical data, then uses the **Viterbi algorithm** to decode the most likely current state.

---

### Real Example: 2022 Bear Market Detection

> **Date:** Jan 19, 2022 · **SPY:** $459.60

On Jan 19, 2022, the HMM regime probability shifted:
- P(Bull) dropped from 0.72 to 0.38
- P(Bear) increased from 0.08 to 0.44
- P(Neutral) = 0.18
- **Regime output: BEAR (threshold: P(Bear) > 0.40 → switch)**

What triggered the shift:
- SPY 20-day return: −3.2% (negative)
- VIX: 26 and rising
- 2Y/10Y spread: −0.15% (inverting)
- HYG (high yield bonds): −2.1% over 20 days
- SPY below its 50-day MA for 3 consecutive days

**Actions taken when regime = BEAR:**
- Stop entering new bull put spreads
- Close open credit spreads aggressively (don't let winners become losers)
- Reduce position sizes across all strategies by 50%
- Activate tail risk hedge (put spread rolling begins)
- Only enter bear put spreads or protective collars

By April 2022, SPY had fallen another 18%. The regime model correctly identified the transition and protected capital.

---

### HMM Features (What the Model Reads Daily)

| Feature Category | Specific Features |
|---|---|
| Price | SPY 5/10/20/60-day returns, distance from 50/200-day MA |
| Volatility | VIX level, VIX 20-day MA ratio, realized vol (20-day), vol of vol |
| Macro | 2Y/10Y yield spread, credit spreads (HYG/LQD ratio) |
| Breadth | % SPX stocks above 50-day MA, new highs/lows ratio |
| Momentum | SPY RSI(14), MACD histogram sign and trend |

---

### How It's Used in the Platform

The HMM regime is a **master filter**, not a trading signal by itself. Every other strategy checks:

```python
regime = hmm.current_regime()

if regime == "BULL":
    # Full risk-on: bull put spreads, iron condors, momentum trades
    position_size_multiplier = 1.0
    allowed_strategies = ["bull_put_spread", "iron_condor", "momentum"]

elif regime == "NEUTRAL":
    # Reduced risk: condors only, smaller size
    position_size_multiplier = 0.6
    allowed_strategies = ["iron_condor", "calendar_spread"]

elif regime == "BEAR":
    # Defensive: only protective strategies
    position_size_multiplier = 0.3
    allowed_strategies = ["tail_risk_hedge", "bear_put_spread", "cash"]
```

---

### Common Mistakes

1. **Over-trading the regime signal.** The HMM might flip between Neutral and Bear several times during a choppy period. Don't adjust your entire portfolio every time the regime shifts. Add a smoothing rule: regime must hold for 3 consecutive days before acting.

2. **Trusting the model in truly unprecedented events.** The COVID crash happened faster than any prior event in the HMM training data. The model lagged by 3–5 days. Have a manual override: if SPY falls more than 5% in a single session, immediately go defensive regardless of the model.

3. **Training on too little data.** An HMM trained on only 2 years of data won't have seen a real bear market. Train on at least 10 years including 2008, 2020, and 2022.

4. **Not updating the model.** Markets evolve. An HMM trained in 2018 might not properly characterize the post-COVID regime. Retrain quarterly.

5. **Ignoring regime uncertainty.** When P(Bull) = 0.45 and P(Neutral) = 0.40, the model is genuinely uncertain. In this case, act as if it's Neutral (the more conservative of the two). Never go full risk-on on uncertain signals.
