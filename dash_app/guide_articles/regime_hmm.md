# Regime Classification — Hidden Markov Model (HMM)
### The Market's Master Filter: Knowing Which Game You Are Playing Before You Bet

---

## Detailed Introduction

Every experienced trader, whether they know it or not, runs a mental regime model. They feel the market and make different decisions depending on whether it "feels like" a bull market, a choppy sideways grind, or a bear market decline. The problem with informal regime assessment is that it is slow, inconsistent, and subject to all the cognitive biases that make human judgment unreliable in high-stakes financial decisions. We anchor to the most recent experience. We interpret ambiguous signals in the direction of our open positions. We recognize bear markets most clearly in hindsight, after the damage is done.

The Hidden Markov Model is the systematic, algorithmic answer to the same question practitioners have always been asking: what regime is the market in right now, and how confident can I be? The HMM formalizes the intuition that market behavior clusters into distinct states — a bull state characterized by smooth upward drift and low volatility, a neutral state with choppy bidirectional movement, and a bear state with sustained downward trend and elevated volatility. These states are "hidden" — you cannot directly observe which state you are in; you can only observe the market's daily behavior and infer the most likely state from that behavior.

The mathematical elegance of the HMM lies in its recognition that regime transitions are probabilistic, not deterministic. A bull market does not flip to bear at a known moment; it transitions with a certain probability on each day. Markets spend roughly 55% of days in the bull regime, 25% in neutral, and 20% in bear, but any individual week is uncertain. The model quantifies that uncertainty and propagates it forward: P(Bull today | all observed data through today). This probability, updated daily, drives the position-sizing multipliers for all other strategies in the system.

The strategy's practical importance is illustrated by one number: a bull put spread strategy that earns Sharpe 1.4 in bull markets earns Sharpe −2.1 in bear markets. If you run that strategy for a full market cycle (including one bear market) without the HMM filter, your realized Sharpe will be approximately 0.6 — the weighted average of good and catastrophic performance. If the HMM correctly filters out 80% of bear-market days, the same strategy earns Sharpe ~1.1 over the full cycle. The regime model is not a strategy — it is the meta-filter that separates strategies from their regime-specific risk.

The HMM was introduced to financial applications in the 1990s by academics studying business cycle dating. Its adoption in systematic trading accelerated in the 2000s as computational costs fell and practitioners sought alternatives to purely technical regime measures. The model is now standard infrastructure at most systematic trading shops, typically complemented by more complex models (neural regime transformers, regime forests) that use more features. For a retail practitioner, the HMM provides 80% of the regime classification benefit with 10% of the complexity of a neural approach — an excellent starting point.

The thing that kills the HMM is unprecedented regime behavior. The COVID crash in March 2020 moved faster than any prior market decline in the model's training data. The HMM lagged by 3-5 days before reclassifying to bear. A manual override rule — any single-session SPY decline greater than 5% immediately triggers defensive positioning regardless of model state — is the essential circuit breaker for extraordinary events.

---

## How It Works

The HMM observes daily market returns and volatility and maintains a probability estimate of the current hidden state. The Baum-Welch algorithm learns state distributions and transition probabilities from historical data. The Viterbi algorithm decodes the most likely current state given all observed data.

**State distributions:**

```
Three hidden states:

Bull  regime: return mean ≈ +0.08%/day, vol ≈ 0.65%/day
Neutral regime: return mean ≈ +0.01%/day, vol ≈ 0.90%/day
Bear  regime: return mean ≈ −0.15%/day, vol ≈ 1.40%/day

Transition probability matrix (estimated, approximate):
        → Bull   → Neutral  → Bear
Bull    [0.92    0.06       0.02  ]
Neutral [0.10    0.82       0.08  ]
Bear    [0.05    0.10       0.85  ]

Interpretation:
  Once in Bear, 85% chance of staying Bear tomorrow
  Bear-to-Bull direct transition very rare (5%)
  Most transitions go: Bear → Neutral → Bull (the staircase)
```

**Daily update cycle:**

```
Inputs (updated daily at close):
  SPY: 5d, 10d, 20d, 60d returns
  SPY: distance from 50d and 200d MA (normalized)
  VIX: level, VIX/VIX_20d_MA ratio, realized vol (20d)
  Macro: 2Y/10Y yield spread, HYG/LQD ratio
  Breadth: % SPX stocks above 50d MA, highs/lows ratio
  Momentum: RSI(14), MACD histogram direction

Output:
  P(Bull | all data through today)
  P(Neutral | all data through today)
  P(Bear | all data through today)

Regime assignment:
  Dominant state = argmax(P)
  Minimum confidence to act: 0.50 (avoid action on near-uniform distributions)
  Smoothing: require same dominant state for 3 consecutive days before switching
```

**Strategy response to regime:**

```python
regime = hmm.current_regime()
multiplier = hmm.position_size_multiplier(regime)

if regime == "BULL":
    multiplier = 1.0
    allowed = ["bull_put_spread", "iron_condor", "covered_call", "momentum"]

elif regime == "NEUTRAL":
    multiplier = 0.6
    allowed = ["iron_condor", "calendar_spread", "vwap_reversion"]

elif regime == "BEAR":
    multiplier = 0.25
    allowed = ["tail_risk_hedge", "bear_put_spread"]
    # All bull-biased strategies halted
```

---

## Real Trade Example

**Date: January 19, 2022. SPY: $459.60.**

Over the prior week, multiple HMM inputs deteriorated simultaneously:
- SPY 20-day return: −3.2% (first sustained decline since November 2021)
- VIX: 26 (rose from 18 to 26 in 5 trading days)
- 2s10s yield spread: flattening rapidly toward inversion (−0.15%)
- HYG 20-day return: −2.1% (early credit stress signal)
- % SPX stocks above 50d MA: dropped from 72% to 54%

**HMM probability shift on January 19:**
- P(Bull): 0.72 → 0.38 (sudden drop)
- P(Neutral): 0.20 → 0.18
- P(Bear): 0.08 → 0.44

P(Bear) exceeded 0.40 on January 19, January 20, and January 21 (three consecutive days). **Bear regime confirmed January 21.**

**Immediate strategy actions:**
- All new bull put spreads: suspended
- Two open iron condors (Feb expiry): closed immediately at small losses
- Open covered calls on equity positions: allowed to expire (directional exposure reduced)
- Tail risk hedge activated: buy SPY Mar $430 put spread for $1.20 debit
- Position size multiplier: 0.25 for all remaining strategies

**What happened next:** SPY fell from $459.60 on January 19 to $348 by October 13, 2022 — a decline of 24.3% over 9 months. The HMM was in Bear regime for most of this period, correctly suppressing bull-biased strategies during the most destructive year for equities since 2008.

The tail risk hedge (SPY $430 put spread) paid $3.80 at peak on March 8 ($380 SPY), representing a +217% return on the $1.20 debit — partially offsetting portfolio losses during the most severe phase of the decline.

---

## Entry Checklist

- [ ] HMM trained on at least 10 years of data including 2008, 2020, and 2022 bear markets
- [ ] Three-day persistence rule: regime must hold for 3 consecutive days before switching
- [ ] Uncertainty handling: when P(dominant state) < 0.50, default to more conservative regime
- [ ] Hard override rule coded: SPY single-session fall > 5% → immediately switch to Bear, override model
- [ ] Retrain schedule: quarterly at minimum; immediately after any regime the model misclassified by > 5 days
- [ ] Position size multipliers defined for each regime (not just on/off — graduated scaling)
- [ ] Macro feature set verified: must include yield curve, credit spreads, breadth indicators (not just price/vol)
- [ ] Test on COVID 2020: model should detect Bear regime by March 16, 2020 at latest (5 days after initial crash)
- [ ] Test on 2022: model should detect Bear regime by February 28, 2022 at latest

---

## Risk Management

**Max loss in regime misclassification:** When the HMM incorrectly classifies a bear market as neutral or bull, strategies that should have been suppressed are active at full size. The historical frequency of this error is approximately 8% of bear-market days. The hard override (SPY -5% single session) catches the worst cases.

**Regime uncertainty management:** When P(Bull) = 0.48 and P(Neutral) = 0.39, the model is genuinely uncertain. Do not go full risk-on on a near-coin-flip probability. The conservative default is: treat the situation as one regime below the most optimistic assignment (uncertain Bull/Neutral → act as Neutral; uncertain Neutral/Bear → act as Bear).

**Emergency override protocol:** For extreme events (>5% single-day SPY decline, geopolitical shock, flash crash):
1. Immediately close all short-premium positions
2. Reduce equity exposure by 50%
3. Buy tail risk hedge (SPY put spread)
4. Wait for HMM to formally reclassify (may take 1-3 days)
5. Only restore positions once HMM confirms stabilization (3 consecutive days of Neutral or Bull)

**When it goes wrong:** The HMM's most reliable failure mode is rapid reversals. The March 2020 COVID crash recovered 30% within 3 weeks — the HMM correctly identified Bear, protective positions were entered, but the rapid recovery meant re-entry at higher prices. The regime model cannot optimize for these "false bear" periods because they look identical to real bear regimes at the time. Accept the cost of being wrong occasionally — the long-run protection value far exceeds the occasional missed recovery.

---

## When to Avoid

1. **Ignoring the model during 3-5 day transitions:** The most dangerous instinct is overriding the Bear signal when the market looks like it's recovering after 1-2 days. Regime transitions are messy — a 2-day bounce in the middle of a 6-month bear market is not a new Bull regime. The 3-day persistence rule exists for exactly this reason.

2. **Using the HMM as a timing tool for exits:** The HMM identifies current regime — it does not predict when a regime will end. Do not trade around regime transitions. Regime transitions are detected after they have occurred; they cannot be predicted in advance.

3. **Running bull strategies at full size in Neutral regime:** "Neutral" does not mean "weakly bullish." It means genuinely uncertain direction. The 0.6× position size multiplier is there to capture opportunities while acknowledging that the environment is not favorable for maximum exposure.

4. **Not retraining after a regime the model missed:** If the model stayed Bull-classified during the first 3 weeks of the 2022 decline, that is a calibration failure requiring investigation and likely retraining. Do not skip the post-mortem.

5. **Three HMM states when more are needed:** The standard 3-state HMM may be insufficient for highly concentrated books. If you trade primarily short-premium strategies (iron condors, put spreads), a 4th state — "High Volatility Spike" — provides critical differentiation between a bear trend (where premium selling at reduced size may still work) and a volatility spike (where all short-premium positions should be closed immediately).

---

## Strategy Parameters

| Parameter | Default | Range | Description |
|---|---|---|---|
| Number of hidden states | 3 (Bull/Neutral/Bear) | 2–5 | 3 is standard; 4 adds High Vol state |
| Feature set | 15+ macro/price/vol | Comprehensive | Yield curve and credit required, not just price |
| Persistence smoothing | 3 days | 2–5 | Days of same state before regime switch enacted |
| Bull → full risk multiplier | 1.0 | Fixed | 100% of target position in bull |
| Neutral → reduced multiplier | 0.6 | 0.5–0.7 | 60% of target in neutral |
| Bear → defensive multiplier | 0.25 | 0.1–0.4 | 25% of target in bear (mostly hedges) |
| Minimum P(dominant) to act | 0.50 | 0.45–0.60 | Below this → use next conservative regime |
| Hard override threshold | SPY single session −5% | Non-negotiable | Immediate Bear switch regardless of model |
| Retrain frequency | Quarterly | Monthly–semi-annual | Walk-forward window expansion |
| Minimum training data | 10 years | 8–15 years | Must include genuine bear market |
| Post-mortem trigger | Any regime miss > 5 days | Required | Mandatory review after misclassification |
