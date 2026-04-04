# Neural Regime Transformer
### Reading the Market's Hidden State with 52 Features and Six Output Classes

---

## Detailed Introduction

Every experienced trader maintains an informal regime model in their head. Bull market — size up, sell premium, momentum works. Bear market — reduce exposure, buy protection, mean-reversion fails. High volatility — close everything short-duration, wait for clarity. The problem is that human regime recognition is slow, inconsistent, and anchored to recent experience. We all believe we saw the 2022 bear market coming — in hindsight. In real time, in January 2022, most practitioners were still in bull-market mode, and the February-October descent extracted capital from strategies that had worked perfectly well for the prior decade.

The neural regime transformer is a systematic answer to the human lag in regime recognition. By processing 52 simultaneous market features over a 40-day sequence — equity trends, volatility structure, interest rate dynamics, credit signals, cross-asset flows, options market positioning, and breadth indicators — it assigns a probability distribution over six market regimes. The key advantage over simpler rule-based regime detection (HMM with 2-3 states, moving average crossovers) is that the neural model can detect subtle combinations of signals that no human would think to combine. A shift in the VIX term structure slope combined with specific sector rotation patterns and a compression in new 52-week highs/lows ratio might together signal a "Transition" regime that rule-based systems miss until it becomes obvious.

The six-regime framework was designed from a practitioner's perspective, not a statistician's perspective. The question was: what are the distinct market environments that require materially different strategy responses? Bull trending and bear trending require opposite positioning. High-vol spike regimes require defensive posturing regardless of direction. Low-vol grind regimes favor premium selling and range-bound strategies. Mean-reverting regimes favor short-duration oscillation strategies. And transition regimes — characterized by mixed signals and uncertainty — require reduced position sizes while clarity emerges.

Who benefits from correct regime classification? Every strategy in the system. The HMM regime model provides a binary on/off signal for most strategies. The neural regime transformer provides a probability distribution over six states, enabling graded position sizing across all active strategies simultaneously. When P(Trending Bull) = 0.85, momentum strategies run at full size and premium selling is aggressive. When P(High Vol Spike) = 0.60, all short-premium positions close, equity exposure reduces, and hedges activate. The probabilistic output is the critical improvement over the binary regime labels of simpler models.

The failure mode that most concerns practitioners with this class of model is the "trained on past regimes" problem. A model trained through 2019 has never seen a global pandemic shutdown. Trained through 2021, it has never seen simultaneous equity-bond correlation breakdown from inflation. The training data for this model must be carefully constructed to include every major regime from the past 15+ years, and the walk-forward validation protocol must test on genuinely different regimes from the training period. No amount of regularization substitutes for testing on genuinely out-of-sample market conditions.

---

## How It Works

The transformer processes a sequence of 40 daily feature vectors (52 features each) and outputs a 6-class softmax probability distribution over the current market regime. The system acts on the regime with the highest probability, provided it exceeds a 0.40 confidence threshold.

**Feature set (52 features per day):**

```
Price & trend (10 features):
  SPY returns: 1d, 5d, 20d, 60d
  SPY rolling vol: 5d, 20d, 60d
  RSI(14), MACD histogram, Bollinger bandwidth

Volatility (6 features):
  VIX level, VIX 5d change, VIX 20d MA
  VIX term structure slope (M1-M3)
  Realized vol (20d), IV premium over realized

Macro & rates (8 features):
  2s10s spread, 3m10y spread, daily yield change
  HYG 20d return, DXY 5d return
  GLD 5d return, WTI 5d return
  Credit spread change (IG OAS 20d change)

Sector rotation (7 features):
  XLK, XLF, XLE, XLV, XLU, XLI vs SPY (5d relative performance)

Options & positioning (6 features):
  Put/call ratio (total), put/call ratio (equity)
  ATM IV vs realized vol ratio
  ES futures front-month premium/discount vs spot
  GEX estimate (positive/negative)

Breadth (5 features):
  Advance-decline line (20d change)
  % SPX stocks above 50d MA
  New 52-week highs/lows ratio
  SPY volume z-score (20d)

Seasonal (4 features):
  Day-of-week (cyclical sin/cos encoding)
  Day-of-month (cyclical sin/cos)
  Turn-of-month proximity (−3 to +3 days indicator)
  Month-of-year (cyclical sin/cos)
```

**The six regimes and their system responses:**

| Regime | P(regime) trigger | Strategy response |
|---|---|---|
| 1. Trending Bull | > 0.50 | Full risk-on: size up all long strategies |
| 2. Trending Bear | > 0.50 | Close longs; activate tail hedges; bear spreads |
| 3. High Vol Spike | > 0.40 | Close all short premium; buy VIX calls; max defensive |
| 4. Low Vol Grind | > 0.55 | Iron condors, covered calls, premium selling |
| 5. Mean Reverting | > 0.50 | RSI bounce trades, VWAP reversion, range strategies |
| 6. Transition | > 0.35 | Reduce all sizes 50%; hold cash; wait for clarity |

---

## Real Trade Example

**October 28, 2024. Market at 10:00am.**

40-day input sequence fed to model. Top attentive features at this snapshot:
- SPY 20d return: −3.4% → bearish context
- VIX: 22.1 and rising 5d (+8.3 points) → vol spike developing
- HYG 20d return: −2.8% → credit caution
- 2s10s: −35 bps → inverted, recession pricing increasing
- GEX: negative (below gamma flip → dealer flows amplifying moves)
- Put/call ratio: 1.42 (elevated institutional hedging)
- XLK 5d vs SPY: −2.1% (tech underperforming — risk-off rotation)

**Model output (6-class softmax):**
- P(Trending Bull) = 0.04
- P(Trending Bear) = 0.28
- P(High Vol Spike) = **0.41**
- P(Low Vol Grind) = 0.02
- P(Mean Reverting) = 0.18
- P(Transition) = 0.07

**Dominant regime: High Vol Spike (0.41 confidence, exceeds 0.40 threshold)**

**System actions triggered:**
1. Close all open iron condor positions immediately (short premium at risk in high vol)
2. Close all bear put spreads with > 2 weeks remaining (protect gains, avoid gamma)
3. Reduce equity exposure across all accounts by 30%
4. Activate VIX call hedge: buy VIX $24/$32 call spread at $1.40 debit
5. Suspend new iron condor entries until regime normalizes
6. Switch all new directional trades to long put spreads (defined risk bearish)

**Over the following 10 days:** VIX peaked at 27.8. SPY fell 4.1%. The VIX call spread paid $3.20 on the $1.40 investment (+128%). Iron condors that had been closed at the regime signal would have lost their entire premium on the subsequent volatility surge.

---

## Entry Checklist

- [ ] Model validated on at least two complete market cycles including a 30%+ bear market
- [ ] Walk-forward validation: train 2010-2019, validate 2020 (COVID test), test 2021-2024
- [ ] Regime transition confirmation: require same dominant regime for 3 consecutive days before acting
- [ ] Confidence threshold met: max P(regime) > 0.40 before taking action on regime signal
- [ ] Transition regime handled: if Transition class > 0.35, automatically reduce all sizes 50%
- [ ] Fallback to HMM defined: if transformer fails or errors, automatic fallback to 3-state HMM
- [ ] Regime label construction verified: no circular logic (ex-post labels must not use same-day input features)
- [ ] Monthly retraining: extend training window by 1 month, retrain all layers
- [ ] Emergency halt: if regime accuracy drops below 60% on labeled weekly validation, suspend and retrain

---

## Risk Management

**Max loss:** The regime classifier does not itself generate trades — it modifies the behavior of other strategies. Risk per trade is defined by the individual strategy risk rules. The regime classifier's primary risk management contribution is position-size reduction during dangerous regimes.

**Stop loss at regime level:** If the portfolio loses more than 8% from peak while a non-defensive regime (Bull or Low Vol) is active, override the regime signal and move to maximum defensive regardless of the model's output. The model may have been wrong — human circuit breaker overrides model.

**Transition state sizing:** When P(Transition) exceeds 0.35, all active positions are reduced by 50% regardless of which other regime the model nominates as dominant. Mixed signals mean uncertainty, and uncertainty means less capital at risk.

**Regime persistence requirement:** Do not act on a single day's regime classification. Require 3 consecutive days of the same dominant regime before triggering any system-wide strategy change. This eliminates most false transitions caused by single anomalous days.

**When it goes wrong:** The model assigns a regime with 0.45 confidence, the system acts, and the actual market behavior is characteristic of a completely different regime. This is expected some fraction of the time — the model has inherent uncertainty. The 3-day confirmation rule and the fallback to HMM provide redundant protection. When both the transformer and HMM agree on a regime, confidence should be higher and action size can scale up.

---

## When to Avoid

1. **Current market is outside the model's training distribution:** If all major features (VIX, yield curve, sector performance) are in regions the model never saw during training, it is operating without meaningful calibration. The Transition regime class provides a partial buffer (high entropy → higher Transition probability), but manual review is required for genuinely unprecedented conditions.

2. **Regime flip-flopping daily:** If the dominant regime changes every 1-2 days (Bull → Transition → Bear → Transition → Bull), the model is highly uncertain about current conditions. The 3-day persistence rule should contain this, but if flip-flopping persists for more than a week, reduce all positions to minimum until the model stabilizes.

3. **Intraday strategy application:** The model was trained on daily bar features. It classifies daily regimes. Applying its daily regime label to intraday decisions (5-minute or 15-minute strategies) is a category error. Intraday strategies should use intraday volatility and price action directly, not a daily regime label.

4. **Training labels derived from same-day features:** If the training labels for "Trending Bull" were defined based on same-day realized volatility and same-day returns, and the model is also using these as input features, the training has circular structure. Regime labels must be defined from ex-post forward-looking returns; features must be contemporaneous only.

5. **P(regime) is highest for multiple classes simultaneously (near-uniform distribution):** If P(Bull) = 0.22, P(Neutral) = 0.20, P(Bear) = 0.18, P(High Vol) = 0.19, etc., the model has maximum entropy and zero conviction. The 0.40 single-class threshold should prevent acting in this case, but verify that the threshold is being enforced.

---

## Strategy Parameters

| Parameter | Default | Range | Description |
|---|---|---|---|
| Input sequence | 40 days | 30–60 | Daily lookback for attention |
| Feature count | 52 per day | 40–70 | Comprehensive cross-asset feature set |
| d_model | 128 | 64–256 | Transformer embedding dimension |
| Attention heads | 6 (one per regime) | 4–8 | Multi-head — each can specialize |
| Transformer blocks | 3 | 2–4 | Model depth |
| Output classes | 6 | 4–8 | Regime taxonomy |
| Confidence threshold | 0.40 | 0.35–0.50 | Min P(regime) to act |
| Transition trigger | P(Transition) > 0.35 | 0.30–0.40 | Reduce size on uncertainty |
| Persistence requirement | 3 consecutive days | 2–5 | Days before regime change is enacted |
| Monthly retrain | Rolling +1 month | Required | Walk-forward extension |
| Emergency halt threshold | Accuracy < 60% | Firm | Weekly validation check |
| HMM fallback | 3-state HMM | Required | Never be regimeless |
| Max position in High Vol | 0 short premium | Non-negotiable | Iron condors never in High Vol Spike |
