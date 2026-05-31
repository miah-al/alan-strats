# Yield Curve Regime
### Trading Equity Options on the Macro Curve's Forward Signal

---

## Detailed Introduction

The slope of the U.S. Treasury yield curve is the single best-documented leading indicator of equity-regime change in modern macro-finance. Estrella and Mishkin (1998), in their landmark Federal Reserve Bank of New York paper "Predicting U.S. Recessions: Financial Variables as Leading Indicators," showed that the 2-year / 10-year Treasury spread predicted every U.S. recession from 1960 through their sample with a 6-to-12-month lead time. Ang, Piazzesi and Wei (2006) generalised this within a no-arbitrage VAR, demonstrating quantitatively that the term-structure carries information about future GDP growth that is not subsumed by past output. Stock and Watson (1989) embedded the slope into the canonical Coincident and Leading Economic Indicator factor model. Adrian, Crump and Moench (2013) decomposed the curve into expectations and term-premium components, showing that the term-premium itself loads on equity risk premia.

The macroeconomic mechanism is straightforward and durable. The short end of the curve is anchored by the Federal Reserve's policy rate. The long end is determined by market expectations of average future short rates plus a term premium. When the curve inverts — short rates above long rates — the market is implicitly forecasting future Fed rate cuts, which in turn signal expected economic weakness. Banks, whose business model is to borrow short and lend long, see net interest margins compress; credit creation slows; capex is delayed; the labour market eventually softens. Equity earnings growth turns negative six to twelve months after the inversion clears, and the equity market typically prices in this earnings deterioration with a 6-12 month lag from the original inversion signal.

The inversion itself does not cause the recession; it is a market-priced expectation of the recession. But it is a remarkably reliable one. Of the eight U.S. recessions since 1960, all were preceded by at least one daily 2y10y inversion, with an average lead time of 14 months. False positives exist (1966, 1998) but are uncommon. The curve's information content is greatest at the inflection points — the moments when the spread transitions from positive to negative or vice versa.

This strategy does not trade rates directly. The dedicated TLT/SPY rotation strategies in this codebase (rates_spy_rotation, rates_spy_rotation_options) already harvest the rates-equity correlation through asset rotation and long option premium. The Yield Curve Regime strategy is structurally different. It uses yield-curve features as INPUTS to a machine-learning classifier whose OUTPUT is a forward-60-day equity-regime forecast. That forecast is then expressed through DEFINED-RISK SPY options structures: bull put credit spreads when the model predicts bullish equity returns, iron condors when chop is forecast, bear put debit spreads when the model predicts bearish returns. Maximum loss is bounded on every trade by the wing width minus credit (for credit spreads) or by the debit paid (for the bear put). No naked options. No outright long premium decay risk. No correlated TLT exposure.

The edge is the lead time. The yield curve discounts future macro shifts that the equity market re-prices with a lag. By front-running the equity reaction with options structures sized to a small fraction of capital, the strategy captures the spread between the macro signal date and the equity confirmation date — typically 6-12 weeks of move in the predicted direction.

---

## How It Works

**The core hypothesis:** the 2y10y spread, contextualised against its historical distribution, the 3m10y spread, the 5y-10y curvature, short-end momentum, and the equity-vol regime, contains forward-looking information about SPY returns over the next 60 trading days.

**Feature derivation (8 features, all from FRED daily yields):**
```
yield_2y10y_spread        : level of 10y - 2y today
yield_2y10y_z_score_252d  : where today's spread sits in trailing 1-yr distribution
yield_2y10y_change_30d    : 30-day slope momentum (steepening or flattening)
yield_3m10y_spread        : 10y - 3m (NY Fed's preferred recession indicator)
yield_5y_minus_10y        : curvature; negative = humped curve
ted_spread_proxy          : negative 30-day change in 2y yield (funding-stress proxy)
vix_level                 : current equity vol regime
vix_ma_ratio              : VIX / VIX 20-day MA — dislocation flag
```

**Forward-regime label (3 classes):**
```
+1 (BULL) : forward 60-day SPY return >= +5%  AND realised 60-day vol <  20%
 0 (CHOP) : forward 60-day SPY return in [-3%, +5%] OR realised 60-day vol >= 20%
-1 (BEAR) : forward 60-day SPY return <  -3%
```
The vol gate on the bull label is critical: a +6% return achieved through a spike-then-revert path is not a true bull regime — it is chop with positive carry. The label disqualifies it.

**Classifier:** sklearn GradientBoostingClassifier, 80 trees, max depth 4, learning rate 0.05, subsample 0.8, min_samples_leaf 10. Wrapped in StandardScaler.

**Walk-forward training (NO LOOK-AHEAD):**
```
Warmup:        252 bars (one full year — yield-curve seasonality + at least one
               full term-premium rebalance cycle)
Retrain:       every 60 bars (≈ each macro quarter)
Train cutoff:  at retrain bar i, training labels limited to indices < i - 60.
               This guarantees no label could have used prices at or after bar i.
Test:          single forward bar (i+1) to mark a regime
```

**Regime → structure map (defined risk only):**
```
Predicted regime  Structure                Construction
────────────────  ───────────────────────  ──────────────────────────────────────
BULL  (+1)        Bull put credit spread   Short put -0.20Δ; long put 5% lower
CHOP   (0)        Iron condor              16Δ short call + put; 5% wide wings
BEAR  (-1)        Bear put debit spread    Long put +0.30Δ; short put 5% lower
```
Black-Scholes pricing through the project's `bs_price_skew` helper, which applies a linear equity-index volatility skew (downside puts priced at higher IV than upside calls) rather than a single flat IV — so the OTM put wings carry a realistic premium. Strikes are solved by Brent's method on the flat-IV delta target. Zero-delta divergence not chased; if the strike search fails the trade is skipped.

**Trade management:**
- DTE 30 at entry
- Credit spreads: take profit at 50% of credit captured; stop loss when buyback cost reaches 2× credit, capped at the wing width (the cost to close a vertical/condor can never exceed the wing, so the stop threshold is clamped there to stay reachable)
- Debit spread: take profit when value reaches 2× debit (+100%); stop loss when value falls to 0.5× debit (-50%)
- Time-stop at 1 day to expiry

**Transaction costs (modeled in the backtest):** every leg is charged both a broker commission ($0.65/contract) AND bid/ask slippage (an adverse-fill haircut per leg) on BOTH entry and exit, scaled by leg count × contracts. A 4-leg iron condor therefore pays 8 legs of friction over its round-trip. These frictions are deducted from realized P&L, so the equity curve reflects net-of-cost performance.

**Entry gates:**
```
P(predicted regime) >= 0.55    (3-class confidence)
VIX                  <= 35      (skip dislocations / Fed-emergency days)
Open positions       <  2       (max concurrent enforced strictly)
Critical features (yield_2y10y_spread, vix_level) must not be NaN
```

---

## Real Trade Examples

> **Note:** The walkthroughs below are ILLUSTRATIVE scenarios constructed to show how the regime → structure mapping behaves around documented macro events. The strike, premium, and P&L figures are representative, not exact backtest fills. Net-of-cost P&L in a live backtest will be lower because both commission and slippage are charged on entry and exit (see Transaction costs above). Headline performance statistics (Sharpe, win rate, CAGR) are not quoted here pending a fresh end-to-end backtest run with the current cost and skew model. **TODO: populate verified headline stats after a cost-and-skew-inclusive backtest re-run.**

### Illustrative — Bear put debit spread, August 2019 (curve inversion regime)

> **Date:** August 14, 2019 | **SPY:** $283.48 | **2y10y spread:** -1 bp (first inversion since 2007) | **VIX:** 22.10 | **Predicted regime:** BEAR (P=0.62)

**Setup conditions:**
- 2y10y inverted for the first time in 12 years
- 3m10y already deeply inverted (-30 bp)
- Yield-curve z-score: -2.4σ (deepest in the year-long lookback)
- 30-day curve change: -18 bp (rapid flattening into inversion)
- VIX at 22 (elevated but not dislocated)
- Model probability mass: P(BULL) 0.18, P(CHOP) 0.20, P(BEAR) 0.62

**Trade entered August 15, 2019:**
- SPY at $284.65
- Long  Sep $280 put (delta ~ -0.30) at $4.15
- Short Sep $266 put (5% lower)        at $1.25
- Net debit $2.90, max profit $11.10, breakeven $277.10
- 4 contracts: $1,160 cost, $4,440 max profit, max loss $1,160

**Path:**
- Aug 23 (Powell at Jackson Hole + Trump tariff escalation): SPY drops to $284 then $279 in one session
- Sep 3-5: SPY at $292, drift back; spread valuation $3.20 (slight gain)
- Sep 30 expiry: SPY closes at $296.77 — both puts expire worthless

**Result:** -$1,160 loss (-100% of debit). The signal was correct directionally over 18 months — SPY did fall 35% in March 2020 — but the 30-day expiry was too short to capture the move. The trade was a classic timing failure on a correct macro thesis.

**Lesson built into the strategy:** The 30-day DTE is intentional — longer dates would dilute the macro signal with noise. The strategy compensates by opening multiple spreads over the inversion window (max_concurrent=2), so the cumulative position eventually catches the move when it materialises.

### Illustrative — Bull put credit spread, March 2021 (steepening curve regime)

> **Date:** March 22, 2021 | **SPY:** $392.59 | **2y10y spread:** +159 bp (steepest in 5 years) | **VIX:** 18.88 | **Predicted regime:** BULL (P=0.71)

**Setup conditions:**
- Curve steepened 60 bp over 90 days as long-end yields rose on reflation
- Yield-curve z-score: +1.9σ (top of trailing year distribution)
- 30-day change: +25 bp (steepening confirmed)
- VIX falling from 30 to 19 over six weeks
- Model probability mass: P(BULL) 0.71, P(CHOP) 0.21, P(BEAR) 0.08

**Trade entered March 23, 2021:**
- SPY at $390.84
- Short Apr $370 put (delta -0.20) at $1.85
- Long  Apr $352 put (5% wider)    at $0.45
- Net credit $1.40, max loss $16.60 per spread
- 6 contracts: max profit $840, max loss $9,960
- Breakeven SPY $368.60 (-5.7% from entry)

**Path:**
- April 9: SPY rallies to $411; spread cost $0.25; +$0.70 profit per spread captured
- Profit target $0.70 = 50% of credit hit; closed all 6 contracts

**Result (illustrative):** roughly +$420 gross; net P&L is lower after commission and slippage on both the 2-leg entry and exit. Held ~17 calendar days. The exact net figure depends on fill quality and is not a verified backtest result.

The steepening curve correctly forecast continued reflation upside; the credit spread captured premium decay efficiently as SPY drifted higher with no near-strike test.

---

## Entry Checklist

- [ ] Macro data current (FRED yields synced to today): rate_2y, rate_10y, rate_3m, rate_5y all present
- [ ] Walk-forward warmup of 252 bars completed (model is trained)
- [ ] Predicted regime probability >= 0.55 (3-class confidence)
- [ ] VIX <= 35 (no Fed-emergency / liquidity-crisis day)
- [ ] Open positions < 2 (max_concurrent enforced)
- [ ] SPY option chain has ~30-DTE strikes available at the target deltas
- [ ] Wing width achievable without violating min increment ($1 SPY strikes typically)
- [ ] Position size (~2.5% of capital at risk) within allocation limits
- [ ] No conflicting open trade in the same regime structure on SPY

---

## Risk Management

**Defined-risk by construction.** Every trade is a 2-leg or 4-leg spread. Maximum loss = wing width minus credit (for credit spreads) or debit paid (for bear put). No naked options, no margin-blow risk.

**Position sizing.** 2.5% of capital at risk per trade. With max_concurrent=2, total at-risk capital is capped at 5%. A perfectly correlated 100% loss across both spreads would draw down 5% of equity — survivable, recoverable, and small enough to allow signal noise without portfolio-killing risk.

**Profit targets.** Credit spreads close at 50% of max credit. The remaining 50% of theoretical premium has the worst risk-reward of the trade lifecycle (collecting marginal premium while gamma risk increases into expiry). Debit spreads close at +100% of debit (value doubled) — this is the natural take-profit for a defined-risk directional trade and matches the standard bear put management.

**Stop losses.** Credit spreads stop when buyback cost reaches 2× credit (i.e. equivalent to losing 1× the credit capital, with the other 1× absorbed by remaining intrinsic). Because the cost to close a vertical or condor can never exceed the wing width, this 2× threshold is clamped at the wing — otherwise, on trades where the collected credit is large relative to the wing, the stop level would sit above the maximum possible spread value and could never trigger. Debit spreads stop at -50% of debit value — preserves half the debit when the directional thesis breaks.

**Time stops.** All trades close at 1 DTE if no other exit triggered. Avoids assignment risk and gamma-blowup at the open of expiry day.

**Model retraining cadence.** Every 60 bars (~quarterly). Frequent enough to adapt to regime change in the macro features, infrequent enough to avoid overfitting to recent noise. The 252-bar warmup ensures the first prediction has a full year of yield-curve seasonality embedded.

**What to do when the model is wrong.** Honor the stop. Do NOT widen the wings or "average down" by adding contracts. The macro signal can be early by 6-12 months — this is documented behaviour from Estrella & Mishkin. The strategy expresses the view in 30-day windows; if a 30-day window goes the wrong way, the 30-day VIEW is wrong, even if the 12-month view eventually proves right.

---

## When to Avoid

1. **During Fed-engineered curve manipulation.** When the Fed runs Operation Twist (2011-2012), Yield Curve Control discussions, or unprecedented QE programs, the curve's information content is dampened. The 2010-2013 period had multiple flat-to-inverted readings that did NOT lead to recession because the long end was being directly suppressed. Do not trust the model output blindly during announced LSAP or YCC programs.

2. **At Fed meeting weeks.** FOMC days produce intraday yield swings of 20+ bp that are pure policy noise, not macro information. Suspend new entries during the 24 hours before and after each FOMC announcement.

3. **When VIX >= 35.** The vix_max gate handles this automatically. High-VIX dislocation periods (March 2020, October 2008) produce massive option spreads where bid-ask costs eat the entire model edge. Wait for VIX to subside before re-engaging.

4. **When macro data is stale or partially missing.** If the FRED sync has not run within the last 2 trading days, do not trade. The strategy raises ValueError if rate_2y or rate_10y is missing — respect it.

5. **In the first 252 bars after deployment.** The model is in warmup; predictions are constant or based on insufficient history. The strategy enforces this internally but the user should not override warmup_bars below 200 without re-validating on backtest.

6. **When the predicted regime conflicts with cross-asset signals.** If the model predicts BULL but credit spreads (HY OAS) are widening rapidly, treat the model output with reduced size. Cross-asset confirmation is not coded into the strategy but is useful as a manual gate.

---

## Strategy Parameters

```
Parameter                Conservative           Standard               Aggressive
─────────────────────    ───────────────────    ───────────────────    ───────────────────
Regime confidence        >= 0.65                >= 0.55                >= 0.45
VIX ceiling              <= 30                  <= 35                  <= 40
Target DTE               45                     30                     21
Wing width (% spot)      0.07                   0.05                   0.03
Profit target (credit)   60% of credit          50% of credit          40% of credit
Stop loss (credit)       1.5× credit            2.0× credit            2.5× credit
Position size            1.5%                   2.5%                   3.5%
Max concurrent           1                      2                      3
GBM trees                120                    80                     60
Retrain interval         90 bars                60 bars                45 bars
Warmup                   504 bars (2y)          252 bars (1y)          252 bars (1y)
```

---

## Data Requirements

**Required (auxiliary_data["macro"]):** A daily-indexed pandas DataFrame containing at minimum:
- `rate_2y`  : 2-year U.S. Treasury constant-maturity yield (FRED `DGS2`), expressed as decimal (0.045 = 4.5%)
- `rate_10y` : 10-year U.S. Treasury constant-maturity yield (FRED `DGS10`), decimal

**Strongly recommended (degradation if absent):**
- `rate_3m`  : 3-month T-bill secondary market rate (FRED `DGS3MO` or `DTB3`), decimal
- `rate_5y`  : 5-year U.S. Treasury constant-maturity yield (FRED `DGS5`), decimal

If `rate_3m` is missing, the strategy falls back to `rate_2y` for the 3m10y feature (degraded but functional). If `rate_5y` is missing, the curvature feature is computed as the average of `rate_2y` and `rate_10y` (constant zero — feature is effectively dropped).

**Recommended (for VIX features):** auxiliary_data["vix"] — a DataFrame with a `close` column containing daily VIX close levels. If missing, VIX is defaulted to 20.0 throughout (which disables the vix_ma_ratio feature signal).

**Price data (price_data argument):** Daily SPY OHLCV. Must contain a `close` column at minimum.

**Ingestion:** All FRED series can be synced via the project's Data Manager → Macro Bars ingestor. The strategy's backtest raises a clear ValueError with sync instructions if any required series is missing — there is no synthetic-yield fallback. This is intentional: a yield-curve strategy with fabricated yields would be a backtest fiction, not a research product.
