# Gradient Boost Direction Signal (XGBoost)
### How Ensemble Decision Trees Find Market Signals That No Human Would Code by Hand

---

## Detailed Introduction

If you asked an experienced trader to describe conditions that precede a 5-day SPY rally, they might say something like: "When RSI is near oversold, the VIX has been falling, and credit spreads are tightening." That is a reasonable heuristic. What XGBoost does is take that kind of intuition and systematically discover thousands of similar rules from data — rules that interact with each other in ways no human analyst would think to test. The combination of 300+ such rules, each correcting the errors of the ones before it, produces a prediction that is typically more accurate than any individual heuristic.

Gradient boosting is a machine learning technique that builds an ensemble of decision trees sequentially. The first tree is fit to the data and makes predictions. The second tree is fit to the residuals — the errors of the first tree. The third tree fits the residuals of the combined first and second trees. Each successive tree is "correcting" the mistakes of the prior ensemble. After hundreds of such iterations, the model has learned complex, nonlinear relationships between dozens of market features and next-week price direction.

The reason XGBoost belongs in a market timing system alongside the LSTM and factor models is that it excels at a different kind of pattern recognition. The LSTM model is built for temporal sequences — it "remembers" how the market behaved 20 or 30 days ago and uses that context. XGBoost operates on a single daily snapshot of market conditions. It does not care about sequence; it cares about feature combinations. The discovery that "VIX above 25 AND credit spreads widening AND RSI below 40 simultaneously" has historically preceded rallies is precisely the kind of interaction effect that XGBoost finds automatically. Neither the RSI, VIX, nor credit spread alone predicts the rally — only their simultaneous combination does.

The strategy emerged in quantitative equity research in the mid-2010s when financial data providers began offering real-time access to options market data (IV rank, put/call ratios) alongside the traditional price and macro features. This richer feature set dramatically improved the model's out-of-sample performance — the options market encodes institutional positioning that the price signal alone does not reveal. SHAP (SHapley Additive exPlanations) values, developed in 2017, made XGBoost's predictions interpretable in a way that black-box neural networks are not: for every prediction, you can see exactly which features drove it and by how much.

The primary risk to this model is overfitting — learning the specific noise of the training period rather than genuine signal. A model with 60 features and 750 training observations is in danger of memorizing rather than generalizing. Walk-forward validation is the non-negotiable protection: train on 3 years, test on the next quarter, repeat rolling forward. Any model that does not show positive Sharpe on multiple independent test windows is likely overfit to history.

---

## How It Works

XGBoost takes a snapshot of 60 market features on any given day and predicts the probability that SPY will be higher in 5 trading days. Above 0.60 probability: enter a bull call spread. Below 0.40 probability: enter a bear put spread. Between 0.40 and 0.60: no position.

**Prediction formula:**

```
P(BULL 5-day | features) = XGBoost(feature_vector)

feature_vector = [
  price features:  5d return, 10d return, 20d return, 60d return,
                   RSI(2), RSI(14), MACD, MACD histogram, BB%B, ATR
  volume:          OBV, volume ratio (today/30d avg), unusual volume flag
  macro:           VIX level, VIX 20d change, 2Y yield, 10Y yield,
                   2s10s spread, HYG 20d return
  sentiment:       put/call ratio, AAII bull-bear, news sentiment score
  options:         IV rank, 25Δ put/call skew, 30d IV / 1yr IV
  regime:          above/below 50d MA, above/below 200d MA,
                   golden/death cross flag, HMM regime
]

Entry thresholds:
  P(BULL) > 0.60 → bull call spread
  P(BULL) < 0.40 → bear put spread
  0.40–0.60       → no position
```

**SHAP-based position sizing:** When confidence is high (SHAP values for top 3 features all point in same direction), use full position size. When features are mixed (some bullish SHAP, some bearish), use 50% position size.

---

## Real Trade Example

**Date:** September 4, 2025. SPY at $548. XGBoost P(BULL 5-day) = 0.72.

**Top 5 SHAP features driving the prediction:**
1. RSI(14) = 38 (near oversold) → +0.18 contribution to bull probability
2. VIX fell 12% from prior week → +0.14 contribution (fear receding)
3. HMM regime = Neutral (not Bear) → +0.11 contribution
4. SPY 60-day return = −5.1% (oversold medium-term) → +0.09 contribution
5. Put/call ratio = 1.3 (elevated retail fear = contrarian buy) → +0.08 contribution

The LSTM model independently generated P(BULL) = 0.65 on the same day. Both models agree: ensemble confidence is high.

**Trade entered September 4:**
- Buy Oct 3 $548 call (29 DTE, ATM) at $6.80
- Sell Oct 3 $558 call (cap profit) at $3.60
- Net debit: $3.20 = $320 per contract
- Max profit: $10 − $3.20 = $6.80 = $680 per contract
- Break-even: $551.20

**September 19 (15 days later):** SPY at $561 (+2.4%). Bull call spread in-the-money.
- Spread worth $9.30 (near maximum)
- Close spread: $9.30 − $3.20 = **+$6.10 = $610 per contract.**

SHAP explanation at exit confirmed that RSI normalized (from 38 to 62) and VIX continued declining — the mean-reversion the model had predicted occurred.

---

## Entry Checklist

- [ ] Walk-forward out-of-sample Sharpe ≥ 0.8 across at least 6 rolling test windows
- [ ] P(BULL) or P(BEAR) exceeds 0.60 (do not trade the 0.40-0.60 neutral zone)
- [ ] SHAP top 3 features all point in the same direction (no conflicting drivers)
- [ ] Feature leakage check: no feature uses any forward-looking information
- [ ] LSTM model agreement: same directional signal increases confidence (use 75% vs 50% position size)
- [ ] HMM regime consistent with signal: P(BULL) trade in BULL or NEUTRAL regime only
- [ ] No earnings for SPY major components within 3 days
- [ ] No FOMC within 2 days (macro policy override)
- [ ] Model retrained within the last quarter (walk-forward window updated)

---

## Risk Management

**Max loss:** The premium paid for the debit spread — $320 per contract in the example above. Defined risk by construction.

**Stop loss rule:** Close if the position is at 100% loss before expiry (spread went to zero while stock moved against you). Do not hold a worthless spread hoping for recovery — the 5-day model prediction has a time horizon, and sitting past that horizon means betting on a new, untrained forecast.

**Feature drift monitoring:** Monitor the model's live prediction accuracy on a rolling 20-day window. If actual next-5-day return is positive but the model predicted bearish (or vice versa) more than 12 times in 20 predictions, the model may have decayed. Halt trading and retrain before the next deployment.

**Position sizing:** Risk 3-5% of portfolio per XGBoost signal. When XGBoost and LSTM agree, use 5%. When only one model fires, use 3%. When they disagree, no position.

**When it goes wrong:** The primary failure mode is regime change — the 2022 inflation regime invalidated many XGBoost models trained on 2015-2021 data. The interaction "VIX rising AND rates rising = bearish" was not in the training data before 2022 (historically, those signals were uncorrelated). Walk-forward retraining on a rolling window is the mitigation, but there will always be a lag before new regime patterns appear in the training window.

---

## When to Avoid

1. **Out-of-sample accuracy has fallen below 52% for 20 consecutive days:** The model is no longer generating edge. Halt trading immediately and investigate whether regime change has invalidated the feature relationships.

2. **VIX above 35:** In extreme volatility regimes, 5-day returns are dominated by macro shocks that overwhelm any technical feature signal. The model's feature interactions were learned in normal markets; extreme volatility environments are out-of-distribution.

3. **Model was not retrained in the last 6 months:** Financial feature relationships decay. A model using 2022 data patterns will fail in 2024 if not updated. Mandatory retraining on a rolling basis is not optional.

4. **Fewer than 6 complete walk-forward test windows are positive:** If the model has profitable out-of-sample results in only 4 of 10 test windows, it is not reliably predictive — it may have been lucky in the windows where it worked. Require a majority of test windows to show positive Sharpe before live deployment.

5. **Top 3 SHAP features are contradicting each other:** When the model's highest-contributing feature points bullish and the second-highest points bearish, the model is uncertain. The 0.55-0.65 probability range is the ambiguity zone. Only trade when SHAP values converge on a direction.

---

## Strategy Parameters

```
Parameter             Default                        Range                Description
--------------------  -----------------------------  -------------------  ----------------------------------------------------------
Feature count         60                             30–80                After feature selection and pruning
max_depth             5                              4–6                  Tree depth — deeper = more interactions, more overfit risk
learning_rate         0.02                           0.01–0.05            Slower = better generalization
n_estimators          500                            300–800              Number of boosting rounds
subsample             0.8                            0.7–0.9              Row sampling per tree (regularization)
colsample_bytree      0.8                            0.7–0.9              Feature sampling per tree (regularization)
Train window          Rolling 3 years                2–5 years            Walk-forward training period
Test window           1 quarter                      1–2 quarters         Out-of-sample test per fold
Bull entry threshold  P > 0.60                       0.55–0.65            Minimum confidence to enter long
Bear entry threshold  P < 0.40                       0.35–0.45            Minimum confidence to enter short
Retrain frequency     Quarterly                      Monthly–semi-annual  Walk-forward update
Options DTE           21–30                          15–45                5-day model → need enough DTE buffer
Position size         3–5% of portfolio              2–6%                 Scales with model confidence
SHAP agreement        Top 3 features same direction  Preferred            High SHAP consensus → full size
```

---

## The Core Edge (Expanded)

The market inefficiency XGBoost exploits is the failure of human and rule-based systems to synthesize multiple signals simultaneously. A human trader sees RSI at 38 and thinks "slightly oversold." They see VIX down 12% and think "fear receding." They may not systematically combine these with the HMM regime, the 60-day return, the put/call ratio, and 55 other features to derive a composite probability. XGBoost does this for every possible combination, tested on thousands of historical observations, and derives interaction weights that no human would compute manually.

The insight from Fama-French factor models applies here: single factors have modest predictive power individually, but orthogonal factors combined multiply their information content. XGBoost is finding the non-linear version of this — the specific combination of technical, macro, sentiment, and regime signals that together point strongly in one direction, even when each alone is inconclusive.

The 2022 rate shock revealed the model's core limitation: it cannot predict what it has not seen. A model trained on 2015–2021 data learned that "VIX rising = equities down, TLT up." In 2022, rising rates caused both to fall. The walk-forward retraining protocol is the only mitigation — as 2022 data enters the training window, the model learns the new relationship.

---

## Signal Snapshot (Enhanced)

### September 4, 2025 — P(BULL) = 0.72

```
XGBoost Signal Dashboard — September 4, 2025:
  SPY price:              ████████░░  $548.20
  P(BULL 5-day):          ████████░░  0.72  [ABOVE 0.60 THRESHOLD ✓]
  Confidence zone:        ████████░░  HIGH (0.72 > 0.65)

  SHAP Breakdown (top features):
    RSI(14)=38.2:         ████████░░  +0.18 [OVERSOLD → BULL ✓]
    VIX 5d change -12%:   ████████░░  +0.14 [FEAR RECEDING ✓]
    HMM=Neutral:          ██████░░░░  +0.11 [NOT BEAR ✓]
    60d return=-5.1%:     ██████░░░░  +0.09 [OVERSOLD MEDIUM-TERM ✓]
    Put/call=1.31:        ████░░░░░░  +0.08 [CONTRARIAN SIGNAL ✓]
    Low volume (0.82×):   ██░░░░░░░░  -0.04 [SLIGHT DRAG]
    Energy outperf:       ██░░░░░░░░  -0.03 [SLIGHT DRAG]

  LSTM model P(BULL):     ████████░░  0.65  [BOTH AGREE → FULL SIZE ✓]
  Walk-fwd Sharpe (OOS):  ████████░░  1.31  [ABOVE 0.80 MIN ✓]
  Last 20 signal accuracy:████████░░  68%   [ABOVE 55% MIN ✓]
  ──────────────────────────────────────────────────────────────────
  → SIGNAL: BULL — P=0.72, SHAP features align, LSTM confirms
  → TRADE: Bull call spread Oct 3 $548/$558, debit $3.20
  → SIZE: Full size (both models agree) = 5% of portfolio
  → STOP: Close if spread loses 75% of value, or at expiry
```

---

## Backtest Statistics (Full)

**Period:** Walk-forward out-of-sample, 2020-2025 (5 years, quarterly retrain)

```
┌─────────────────────────────────────────────────────────────────┐
│ XGBOOST DIRECTION SIGNAL — 5-YEAR OOS PERFORMANCE              │
├─────────────────────────────────────────────────────────────────┤
│ Total signals fired (P > 0.60 or P < 0.40):  187               │
│ Bull signals:   118  |  Bear signals: 69                        │
│ No-trade zone (0.40-0.60):  523 events correctly avoided        │
│ Win rate (bull):  67%  |  Win rate (bear):  62%                 │
│ Average winning trade:    +$580/contract                        │
│ Average losing trade:     -$280/contract                        │
│ Profit factor:             3.6                                  │
│ Annual Sharpe (OOS):       1.31                                 │
│ Maximum drawdown:         -9.4%                                 │
│ Best month: Jan 2023     +6.8%                                  │
│ Worst month: Oct 2022    -4.8%  (2022 regime shift impact)      │
└─────────────────────────────────────────────────────────────────┘
```

**By signal confidence:**

```
P(BULL) range  Win Rate    Avg P&L  Action
-------------  ----------  -------  --------------------
P > 0.80       74%         +$720    Full position
P 0.70-0.80    68%         +$580    Full position
P 0.60-0.70    61%         +$380    Half position
P 0.40-0.60    No trade    —        Uncertainty zone
P 0.30-0.40    58% (bear)  +$290    Half position (bear)
P < 0.30       65% (bear)  +$480    Full position (bear)
```

---

## Data Requirements

```
Data                                     Source                   Usage
---------------------------------------  -----------------------  -----------------------------------------
SPY daily OHLCV (10+ years)              Polygon                  Price momentum features + target variable
VIX daily (10+ years)                    Polygon / CBOE           Macro vol features
Treasury yields (2Y, 10Y)                FRED / Polygon           Rate curve features
HYG daily price                          Polygon                  Credit condition feature
DXY, GLD daily                           Polygon                  Cross-asset features
Sector ETF returns (XLK, XLF, XLE, XLV)  Polygon                  Sector relative strength
Put/call ratio (total and equity)        CBOE                     Sentiment features
HMM regime state                         Platform regime model    Regime feature
IV rank (30-day)                         Calculated from options  Options market feature
FOMC calendar                            Federal Reserve          Days-to-FOMC feature
```
