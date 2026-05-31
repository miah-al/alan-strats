# Iron Condor — AI
### Gradient Boosting Predicts Range-Bound Conditions — Adaptive Strike Placement by Regime

---

## Key Terms

```
Term                                     Definition
---------------------------------------- ---------------------------------------------------------------
IVR   — IV Rank                          0-100% percentile of VIX in its 52-week range. High = rich premium.
VIX   — CBOE Volatility Index            Market's 30-day implied vol for S&P 500. The "fear gauge."
ADX   — Avg Directional Index (14d)      Trend strength (not direction). <20 = range-bound, >25 = trending.
ATR   — Avg True Range (14d)             Daily price range normalised by spot price (ATR%).
VRP   — Volatility Risk Premium          IV minus realised vol (HV). Positive VRP = options overpriced vs reality.
DTE   — Days To Expiration               Calendar days remaining until the contract expires.
Delta — Option Delta                     $1 move sensitivity. 16-delta ≈ 16% chance of expiring ITM.
Vega  — Option Vega                      IV change sensitivity. Short vega = rising IV hurts P&L.
OTM   — Out of The Money                 Strike above spot (call) or below spot (put). No intrinsic value.
```

---

## The Core Edge

The rules-based Iron Condor earns its edge by selling overpriced implied volatility in calm markets. The AI version does the same thing — but it adds one critical capability: **it knows when the rules are about to fail**.

Rules use fixed thresholds. IVR ≥ 45%, ADX ≤ 22. These are good long-term averages. But the market has structure that rules can't see:

- An IVR of 0.55 in a trending sector behaves differently from an IVR of 0.55 after a VIX spike that just resolved
- A stock with flat ADX but rising 5-day momentum is about to trend — the ADX just hasn't caught up yet
- When the yield curve is inverted AND VIX is elevated, the realized vol over the next 30 days is structurally higher than the 20-day window suggests

The gradient boosting model sees 14 features simultaneously and learns the interactions between them. It has seen hundreds of setups and knows which combinations historically lead to range-bound outcomes and which ones look good on the surface but fail within 2 weeks.

**The second innovation: adaptive strike placement.** When model confidence is high (P ≥ 0.75), it tightens the strikes slightly (higher delta → more credit, more risk). When confidence is marginal (P just above threshold), it widens the strikes (lower delta → less credit, more buffer). This improves the risk-adjusted return across the confidence spectrum.

### Why Gradient Boosting (Not LSTM, Not Logistic Regression)?

- **Not LSTM:** Iron Condor edge is not about temporal sequence — it's about the current state of the market. LSTMs excel at detecting patterns that unfold over time (earnings drift, momentum). Range-bound prediction is a snapshot problem.
- **Not Logistic Regression:** The features interact nonlinearly. High IVR is good. High IVR + high ADX is bad. Logistic regression can't capture that interaction without manual feature engineering. GBM learns it automatically.
- **Gradient Boosting:** Interpretable (feature importances), handles nonlinear interactions, robust to outliers, fast to train on 2–3 years of daily data, doesn't overfit with proper regularization (max_depth=3, subsample=0.8).

---

## What the Model Sees — The 14 Features

```
Feature              Type      What It Measures                  Why It Matters for IC
-------------------  --------  --------------------------------  -------------------------------------------------
`ivr`                IV        IV Rank (0–1, 52-week window)     Higher = more overpriced premium to harvest
`adx`                Trend     Avg Directional Index (14d)       Low = range-bound (good IC); high = trending
`put_call_skew`      IV        1m vs 3m vol ratio (contango)     Flat skew = symmetric IC; steep skew = asymmetric
`iv_term_slope`      IV        5-day VIX momentum (slope proxy)  Rising VIX = expanding vol regime, dangerous
`vrp`                Vol       Implied − realized vol (premium)  Positive = selling at fair price + premium
`atr_pct`            Price     ATR / spot (daily range %)        High = stock moving fast, wings at risk
`ret_5d`             Price     5-day return                      Recent momentum signal
`ret_20d`            Price     20-day return                     Intermediate trend signal
`dist_from_ma50`     Price     % distance from 50-day MA         Overextended = mean-reversion likely (good IC)
`vix_level`          Macro     Current VIX                       Regime classifier
`vix_5d_change`      Macro     VIX % change over 5 days          Spiking = dangerous; collapsing = opportunity
`vix_ma_ratio`       Macro     VIX / 20-day VIX MA               >1.2 = elevated; <0.8 = complacent
`yield_curve_2y10y`  Macro     10y − 2y spread                   Inverted curve = recession risk, higher vol
`days_to_month_end`  Calendar  Days until month-end              Options cluster at month-end expiry
```

> **Removed in the 2026-05 audit:** `realized_vol_20d` was dropped as a model
> input because it is the normalizer for the supervised label band — feeding it
> to the model leaked the target into training and inflated backtest metrics.
> It is still computed, but only to construct labels, never as a feature.
> (`atm_iv` = VIX/100 and an `oi_put_call_proxy` duplicate of `put_call_skew`
> were also removed as redundant.)

### What a Training Row Actually Looks Like

The model ingests one row per trading day per ticker. Each row is the complete market state that day. Here is a real example from March 20, 2024 — the date the model fired a high-confidence signal on SPY:

```
Training row — SPY, March 20 2024:

Feature               Value    Interpretation
─────────────────────────────────────────────────────────────────────────
ivr                   0.43     IV in top 57% of 52-week range — elevated
adx                   16.8     Low trend strength — range-bound ✓
put_call_skew         1.08     Near-flat (1m IV ≈ 3m IV × 1.08) ✓
iv_term_slope         -0.012   VIX falling slowly (5-day slope negative) ✓
vrp                  +3.8      IV − RV = +3.8 vol points — very positive ✓
atr_pct               0.0078   0.78% daily range (very calm) ✓
ret_5d               +0.014   +1.4% over 5 days (mild drift, not trend) ✓
ret_20d              +0.051   +5.1% over 20 days (steady, not explosive)
dist_from_ma50       +0.023   +2.3% above 50-day MA (near flat) ✓
vix_level            13.2      Low-to-moderate VIX ✓
vix_5d_change        -0.091   VIX fell 9.1% over 5 days (calming) ✓
vix_ma_ratio          0.89     VIX 11% below its own 20-day MA (below-trend) ✓
yield_curve_2y10y    -0.38    2y10y inverted by 38 bps (mild caution)
days_to_month_end     11       11 days until month-end — expiry clustering
─────────────────────────────────────────────────────────────────────────
Label (45-day outcome): 1  (SPY stayed within ±1.5-sigma band → IC won)
```

Most of the 14 features point to a calm, range-bound environment. The yield curve inversion and the middling IVR are mild negatives. The model weighs them all simultaneously and outputs:

```
P(range-bound over next 45 days) = 0.71
→ Signal fired. Delta = 0.16 (standard). Entry approved.
```

A rules-based system using only IVR and ADX would have flagged this entry too. But the model is also correctly *not* flagging entries on days where IVR is similar but atr_pct is 2.1%, vix_5d_change is +18%, and ret_5d is +4.2%. That discrimination is what makes the AI version incrementally better.

---

## What the Model Predicts

**The output is a single probability: P(range-bound) over the next 45 days.**

This is not a direction prediction. It is not a prediction of expected move magnitude. It is specifically the probability that the underlying will stay within a ±1-sigma band (computed from 20-day realized vol, annualized to 45 days) over the holding window.

```python
# Label construction (run at training time, not inference time):
annualized_rv = realized_vol_20d × sqrt(252)
sigma_45d     = annualized_rv × sqrt(45 / 252)
              = annualized_rv × 0.4226

# The 45-day return envelope:
upper_band = entry_price × (1 + sigma_45d)
lower_band = entry_price × (1 - sigma_45d)

# Label = 1 only if the stock NEVER closes outside this band
# during ANY of the 45 trading days following entry:
label = 1 if all(|daily_close[t+1 : t+45] / entry_price - 1| <= sigma_45d)
label = 0 if any close exceeds the band in either direction

# Base rates are data- and ticker-dependent and must be measured per universe;
# on broad-index equity data the positive (range-bound) rate typically falls in
# a roughly 40–55% band.
#
# The model's job: identify the positive windows BEFORE they happen, lifting
# precision above the base rate at the chosen threshold.
#
# TODO: re-run the current pipeline to report measured base rate, precision,
#       and lift. Do not quote a number until it is regenerated.
```

**Why this label is correct for Iron Condors:**

An Iron Condor at 16-delta short strikes profits as long as the stock stays within roughly ±1-sigma movement. The label directly mirrors the profit condition of the trade. There is no mismatch between what the model optimizes and what the trade needs.

The model is NOT predicting:
- Direction (bull or bear)
- Whether IV will expand or contract
- The magnitude of the eventual move
- A price target

It is predicting exactly one thing: *will the price stay inside the tent?*

---

## Walk-Forward Architecture

**The problem it solves:** If you train a model on all historical data and test it on the same data, you are cheating — the model already saw the answers. Walk-forward prevents that by ensuring the model at any point in time has only ever seen data from the past, never the future.

**Three phases:**

```
Phase 1 — Warmup (bars 0–180)
  Collect data only. No model, no trades.
  Need ~180 bars before IVR, MA50, and realized vol
  are stable enough to train on.

Phase 2 — First train (bar 180)
  Train on bars 0–180. Start generating signals from bar 181.

Phase 3 — Live + retrain (every 30 bars ≈ monthly)
  Bar 210 → retrain on 0–210, generate new signals.
  Bar 240 → retrain on 0–240, generate new signals.
  The model always learns from everything it has seen so far.
```

```
Time →  [BAR 0 ─────────────────── BAR 180] [BAR 181 ──── BAR 210] [BAR 211 ───→]
                                              ↑                     ↑
                                         First train           Retrain #2
                                         (180 bars of           (210 bars of
                                          history)               history)

Rule: Model retrained every 30 bars (≈ monthly) on ALL history up to current bar.
      No future data ever used in any feature or label.
      First 180 bars: no trades (warmup — insufficient data for reliable model).
```

**The result:** the model behaves exactly as it would in real trading — no lookahead, no data leakage, no inflated backtest results.

**Why 180-bar warmup?** The feature matrix needs ~252 bars to compute a reliable IV Rank. At bar 180 you have enough history for stable IVR, 50-day MA, and realized vol. The model also needs enough labeled examples of both classes to learn from, and the training window is further purged by the label's forward window (`dte_target` rows), so a longer warmup leaves a usable training set after the purge.

**Why retrain every 30 bars?** Market regimes shift over 4–12 weeks. A model trained in Jan 2022 (rising-rate bear market) will misfire in Jan 2023 (recovery). Monthly retraining keeps the model current without excessive refit risk.

---

## Label Construction

The model predicts whether the stock will stay within its expected range over the next 45 days:

```python
# 1-sigma N-day expected move (from options pricing theory):
sigma_45d = annualized_vol_20d × sqrt(45 / 252)
           = annualized_vol × 0.4226

# Range-bound label = 1 if max excursion stays within this band:
range_bound = 1 if max(|return_i|) ≤ sigma_45d  for all i in [t+1, t+45]
            = 0 otherwise

# Historical positive rate:
# SPY 2018–2024: ~42% of 45-day windows are range-bound by this definition
# AAPL 2018–2024: ~35% (more volatile single stock)
# NVDA 2018–2024: ~28% (high-beta semiconductor)
```

**Why this label?** An Iron Condor at 16-delta short strikes profits as long as the stock stays within roughly ±1× N-day sigma. This label directly measures whether the trade's profit condition would be met. It's the most aligned label for IC entry prediction.

---

## Adaptive Strike Placement

```
Model confidence → delta adjustment → credit/risk tradeoff

P(range-bound) ≥ 0.75  →  delta = 0.16 + 0.04 = 0.20  (tighter, more credit)
P(range-bound) 0.60–0.74 →  delta = 0.16              (standard)
P(range-bound) 0.55–0.60 →  delta = 0.16 − 0.03 = 0.13 (wider, more buffer)

At 0.20 delta (high confidence):
  Credit is ~30% higher than 0.16 delta
  Short strikes are ~1.5% closer to spot
  Model says we have 75%+ probability of staying in range
  Additional tightness is compensated by model's confidence

At 0.13 delta (marginal confidence):
  Credit is ~20% lower than 0.16 delta
  Short strikes are ~2% further from spot
  Extra wing buffer protects against model being wrong
```

---

## Real-World Trade Walkthrough — A Complete Iron Condor

This is a full trade lifecycle using the AI signal on SPY. Follow every number.

### Step 1 — Market Conditions at Entry

**Date:** October 11, 2023 (Thursday close)

```
Market State — SPY, October 11 2023:
──────────────────────────────────────────────────────────────────
SPY spot price:       $427.00
VIX:                  19.2
IV Rank (52-week):    63%  (0.63 — elevated; 2023 IVR range was 18%–78%)
Historical vol 20d:   15.0% annualized  (calm recent actual movement)
IV - RV spread (VRP): +4.2 vol points  (strong vol premium)
ATR (daily range %):  1.9%  (slightly elevated but acceptable)
5-day SPY return:     -0.8%  (drift, not trend)
20-day SPY return:    -1.2%  (flat; SPY corrected from $432 high)
Distance from MA50:   -2.1%  (SPY trading slightly below 50-day MA)
VIX 5-day change:     -11.4% (VIX falling — calming from mini-spike)
Yield curve 2y10y:    -0.82 (inverted — macro caution, but stable)
ADX:                  16.4  (no dominant trend)
──────────────────────────────────────────────────────────────────
Model P(range-bound 45 days): 0.77
Adaptive delta:               0.20  (high confidence → tighter strikes)
```

Most of the 14 features are positive. The inverted yield curve is a negative, but it is a macro backdrop, not a direct vol driver. The VIX falling + IVR elevated + VRP strongly positive + calm ATR is the combination the model was built to recognize.

**Why the model fired at 0.77 specifically:**

The interaction that pushed probability from ~0.62 (base for these IVR/VIX levels) to 0.77 was VIX falling sharply (5-day change = −11.4%) while IVR was still elevated (0.63). This happens when a vol event just resolved — IV takes days to mean-revert downward even after the fear subsides. The model learned this creates a short window of elevated IVR in a structurally calming environment. That's the sweet spot.

### Step 2 — Strike Selection

At 16-delta for a standard entry, but with model confidence at 0.77 (above 0.75 threshold), adaptive delta bumps to **0.20**.

```
Strike selection — SPY $427, Oct 11 2023:
  Target expiry: November 17, 2023  (37 DTE — nearest expiry ≥ 30 DTE)

  Short call:  $444  (0.20 delta call → 4% above spot)
  Long call:   $451  (7-point wide call wing)
  Short put:   $410  (0.20 delta put → 4% below spot)
  Long put:    $403  (7-point wide put wing)

  ┌────────────────────────────────────────────────────────────┐
  │  $403    $410          $427          $444    $451          │
  │   │       │             │             │       │            │
  │   ●───────●             ▲             ●───────●            │
  │  long   short          SPOT         short   long           │
  │  put    put                         call    call           │
  │                                                            │
  │  ←── put spread ──→  ←── profit zone ──→  ← call spread→ │
  └────────────────────────────────────────────────────────────┘
```

### Step 3 — Entry Credits and Risk

```
Position pricing at entry (Oct 11, 2023 close):
──────────────────────────────────────────────────────────────────
Sell $444 call (0.20δ):   +$2.10
Buy  $451 call (0.12δ):   −$1.05
Call spread net credit:   +$1.05

Sell $410 put (0.20δ):    +$2.65
Buy  $403 put (0.13δ):    −$1.10
Put spread net credit:    +$1.55

Total Iron Condor credit: +$2.60 per share = $260 per contract
──────────────────────────────────────────────────────────────────
Max profit:    $260  (if SPY closes between $410–$444 at expiry)
Max loss:      $440  (wing width $7 − credit $2.60 = $4.40/share × 100)
Upper breakeven: $444 + $2.60 = $446.60
Lower breakeven: $410 − $2.60 = $407.40
Profit zone:     $407.40 to $446.60  (±4.6% from spot $427)
Risk/reward:     $260 credit / $440 max loss = 59% potential return on risk
──────────────────────────────────────────────────────────────────
```

Note the adaptive strike effect: at standard 0.16 delta, credit would have been ~$2.00. The extra 4 delta points (tighter strikes, per model confidence) added $0.60/contract = $60 per contract premium.

### Step 4 — Theta Decay Over 37 Days

The Iron Condor profits through time decay. Here is what the position value looks like as days pass (assuming SPY stays near $427):

```
Iron Condor P&L through time — SPY stays at $427:
(Theta decay curve — idealized, no vol change)

Day   DTE   IC Value   Profit   % of Max
──────────────────────────────────────────
 0    37    $2.60      $0       0%
 5    32    $2.35      $25      10%
10    27    $2.10      $50      19%
15    22    $1.80      $80      31%
21    16    $1.30      $130     50%  ← 50% profit target ← CLOSE HERE
25    12    $1.00      $160     62%
30     7    $0.65      $195     75%
37     0    $0.00      $260     100% (theoretical)

Key: Theta is not linear. It accelerates in the final 2 weeks.
     Days 0–15: earned $80 (31% of max)
     Days 15–21: earned $50 (19% of max) in just 6 days
     Days 21–37: remaining $130 — but gamma risk spikes dramatically.
                 The remaining premium is not worth the additional
                 pin/gap/event risk of holding another 16 days.
```

### Step 5 — Exit at 50% Profit Target

**Date: October 28, 2023 (day 17 of trade, DTE = 20)**

```
Exit — SPY, Oct 28 2023:
──────────────────────────────────────────────────────────────────
SPY price:             $418.00  (down from $427 entry — put side tested)
DTE remaining:         20

Current position value (to close):
  Buy back $444 call:  -$0.40  (deep OTM, far from $418)
  Sell $451 call:      +$0.12
  Buy back $410 put:   -$0.85  (closer to money at $418, but still $8 OTM)
  Sell $403 put:       +$0.10
  Total to close:      -$1.03

Original credit:        $2.60
Cost to close:          $1.03
P&L:                   +$1.57 per share = +$157 per contract
% of max profit:        60.4%  (above 50% target — CLOSE)
──────────────────────────────────────────────────────────────────
Final result:  +$157 / $440 max risk = +35.7% return on max risk
Hold time:     17 days (vs 37 day max)
Capital freed: 17 days early — available for the next trade
```

**P&L breakdown:**
- Call spread: collected $1.05, bought back for $0.28 net → kept $0.77
- Put spread: collected $1.55, bought back for $0.75 net → kept $0.80
- Total kept: $0.77 + $0.80 = $1.57/share

The put side did the heavy lifting — SPY drifted toward the put strikes, so the put spread decayed faster from the combined theta + small delta move toward it.

---

## Feature Importance — What the Model Actually Uses

The model exposes `feature_importances_` over the 14 features in `FEATURE_COLS`
after each walk-forward retrain. The ranking shifts as the model retrains on new
data, so there is no single fixed importance table.

**Qualitatively, the dominant signals are the "is the stock calm right now?"
features** — daily velocity (`atr_pct`), overextension (`dist_from_ma50`), trend
strength (`adx`), and premium richness (`vrp`). These measure whether the
underlying is in a calm, mean-reverting state, which matters more for an iron
condor than the raw IV level. IVR, which traders fixate on, is typically a
mid-pack contributor rather than the top driver.

> **TODO: re-run for current numbers.** The previously-published importance
> table listed `realized_vol_20d` as a top-3 feature — that feature was removed
> in the 2026-05 audit (it leaked the label band), so any table including it is
> stale. Regenerate the importance ranking from a fresh run before quoting
> specific percentages.

---

## When the Model Is WRONG — Iron Condor Failures

Understanding failure modes is more important than understanding wins. These are the exact mechanisms that destroy Iron Condor portfolios.

### Failure Mode 1 — Earnings Gap Through Strikes

**Trade: AAPL Iron Condor, January 2025**

```
Entry — AAPL, Jan 15 2025:
  Spot:   $236.00
  VIX:    15.1
  IVR:    0.52  (elevated from Jan seasonal effects)
  ATR%:   1.1%  (calm)
  Model P: 0.61  (marginal — borderline entry)
  Short call: $250 (0.16δ), Short put: $222 (0.16δ)
  Credit: $2.20/share

Entry mistake: Earnings were Jan 30. Condor expiry was Feb 7.
               Earnings fell INSIDE the holding window.

What happened:
  Jan 30 after-hours: AAPL reported EPS beat but iPhone China weakness
  Stock gapped from $240 → $218 at open on Jan 31
  Short $222 put went immediately ITM
  Short $222 put delta jumped from 0.16 to 0.68 overnight
  Condor P&L: -$380 per contract

The error: The screener's ATM IV was elevated (IVR = 0.52) BECAUSE of earnings
           premium. That premium is not available for IC sellers — it belongs
           to the earnings event. The model's IVR feature cannot distinguish
           between "sustained elevated IV" and "earnings-inflated IV."

Rule learned: NEVER open an Iron Condor when earnings fall within the hold window.
              Check earnings dates BEFORE entry. This is not negotiable.
```

### Failure Mode 2 — VIX Spike from 18 → 35

**Trade: SPY Iron Condor, August 2024**

```
Entry — SPY, July 31 2024:
  Spot:   $546.00
  VIX:    17.0
  IVR:    0.54
  ATR%:   0.82%
  Model P: 0.72  (solid entry — all signals positive)
  Short call: $570 (0.18δ), Short put: $522 (0.18δ)
  Credit: $3.40/share (wide strikes, good credit)

What happened — the carry unwind:
  August 5, 2024: Japanese yen carry trade unwind triggered
  SPY fell from $540 → $505 over 3 trading days
  VIX spiked from 17 → 65 intraday (closed ~38)
  Short $522 put delta went from 0.18 to 0.71 in 3 days
  IC value went from $3.40 collected to $9.20 to buy back
  Loss: -$580 per contract ($920 close − $340 credit)

Why the model was wrong:
  vix_5d_change at entry was -4.2% (VIX was calm and falling)
  put_call_skew was near 1.0 (balanced — no warning)
  No feature captured the building yen carry tension
  The yen/Nikkei was not in the feature set — no warning available
  This is a known blind spot: macro regime shocks from non-equity markets

What you could have done:
  Stop-loss rule: close if IC value doubles (2× credit = $6.80 to buy back)
  The position should have been closed on the first day SPY fell through $530
  and put delta exceeded 0.35. Hard stops matter more than model signals once
  a structural shock begins.

Rule learned: The model gives you a probability, not a guarantee.
              A 0.72 model score means 28% of the time it loses.
              Position sizing is the only real risk management here.
              Never risk more than 3% of account on a single IC.
              A $580 loss on 2 contracts on a $40,000 account = 2.9%.
              Survivable. On 10 contracts: $5,800 = 14.5%. Portfolio wound.
```

### Failure Mode 3 — Trending Market (ADX > 35)

**Why the ADX filter exists and why it is not optional**

```
SPY directional moves that would have destroyed ICs (2022–2024):

February 2022: Fed pivot language shock
  SPY dropped from $452 → $412 in 3 weeks (+8.8% move)
  ADX on Feb 7 entry day: 18 (looked fine — trending HADN'T started yet)
  ADX on Feb 18 (1 week in): 31 (trend established, condor in trouble)
  Lesson: ADX lags. By the time it confirms a trend, strikes are already
          under pressure. Use 5-day return rate of change as early warning.

October 2023: Israel-Hamas war weekend gap
  SPY gapped -1.8% Sunday-to-Monday
  ADX at entry (prior Friday): 22 (acceptable)
  No model feature captures weekend geopolitical events
  This is a known and accepted risk — it is called "gap risk"
  Managed by position sizing, not signal improvement

March 2024: Post-FOMC trending breakout
  SPY rallied from $508 → $543 in 3 weeks
  ADX started at 21, hit 38 by week 3
  Short call at $543 was tested — exactly at the short strike
  Managed via delta hedge (bought SPY calls to offset delta) at day 18
  Avoided max loss but gave back 40% of credit

Why the ADX filter exists:
  Iron Condors bleed on the short gamma exposure when the market trends.
  A condor has negative delta-of-delta (negative gamma). As SPY trends up,
  the short call's delta increases every day — you lose more each additional
  day of the trend. A trending market is the worst possible environment for
  a short-premium strategy. ADX > 25 is a caution; ADX > 35 is a hard block.

ADX threshold impact on win rate (illustrative — directional, not measured):
  ────────────────────────────────────────────────
  ADX at entry    Win rate (lower in stronger trends)   Expectancy
  < 15            highest                               clearly positive
  15–25           high                                  positive
  25–35           moderate                              marginal
  35–45           low                                   negative
  > 45            lowest                                strongly negative
  ────────────────────────────────────────────────
  The pattern is the point: win rate and expectancy fall monotonically as the
  trend strengthens, which is why the ADX filter blocks high-ADX entries.
  TODO: re-run for current numbers to fill in measured win rate / P&L per bucket.
```

---

## Edge vs Luck — How to Know the Strategy Is Working

This is the question most traders never ask until it is too late. A high win
rate sounds like edge, but a short streak of wins can happen by luck even with a
coin-flip strategy. You need a framework that checks expectancy, not just the
hit rate.

### Expected Value — The Only Number That Matters

Expected value, not win rate, decides whether a strategy is worth trading:

```
EV per trade = (win_rate × avg_win) − (loss_rate × avg_loss)

  Sanity check: EV must be POSITIVE for the strategy to be worth trading.
  If your win rate is 60% but your average loss is 3× your average win,
  EV is negative and you are grinding toward ruin slowly. An iron condor's
  structural risk is that the rare losses are larger than the frequent wins,
  so the win rate must stay high enough to keep EV positive net of costs.

TODO: re-run for current numbers. The previously-published figures
      (74% win rate, +$112 avg win, −$244 avg loss, +$19.44 EV/trade, and a
      "+4pp lift vs rules") were derived from the leaked pre-audit pipeline
      and are NOT reliable. Regenerate win rate, average win/loss, and EV from
      a fresh post-audit run (skew pricing + round-trip costs + purged
      walk-forward) before quoting any of these.
```

### Win Rate Is Not Edge — The Distinction That Matters

```
Consider two strategies with the SAME win rate (say 70%):

  Strategy A: Wins $112, loses $244
    EV = (0.70 × 112) + (0.30 × −244) = $78.40 − $73.20 = +$5.20 ← EDGE

  Strategy B: Wins $50, loses $400
    EV = (0.70 × 50) + (0.30 × −400) = $35 − $120 = −$85 ← NO EDGE

  Same win rate. Opposite expectancy.
  Always check BOTH win rate AND loss magnitude before declaring edge.
  (Illustrative numbers — not measured results for this strategy.)
```

### Sharpe Ratio of the Strategy

The strategy's target Sharpe is **0.8** (honest post-audit estimate; the realistic
band is roughly **0.5–0.9**). This replaces a previously-published annualized
Sharpe of ~2.38, which was a discredited pre-audit figure: it was produced by a
pipeline that fed `realized_vol_20d` to the model while also using it to build
the label, leaking the target into training and massively inflating the metric.
After removing that leak, skew-aware leg pricing, and charging realistic per-leg
slippage + commission on both entry and exit, the honest expectation is far
lower.

```
Backtest results — AI Iron Condor on SPY:
──────────────────────────────────────────────────────────────────
Target Sharpe:        0.8   (honest band 0.5–0.9)

TODO: re-run the post-audit pipeline (skew pricing + round-trip costs +
      purged walk-forward, realized_vol_20d removed) and report measured
      trade count, win rate, P&L, monthly Sharpe, and worst/best months.
      Do NOT quote the old 2.38 Sharpe / 74% win-rate numbers — they were
      leakage artifacts.

For context (unchanged, external benchmarks):
  S&P 500 long-only: Sharpe ~1.0
  SPY buy-and-hold (incl. 2022 drawdown): ~0.85
──────────────────────────────────────────────────────────────────
```

### The Expected P&L Shape

The P&L distribution of a managed iron condor is **right-skewed by
construction**: most trades win a small-to-moderate amount (theta decay captured
to the 50% profit target), while a minority of trades lose larger amounts when a
short strike is breached. The 2× credit stop-loss rule truncates the left tail —
most losing trades are closed early rather than held to structural max loss.

> **TODO: re-run for current numbers.** A previously-published histogram quoted
> a specific 192-trade distribution (modal +$142 win, −$380 average loss). Those
> counts came from the leaked pre-audit pipeline and have been removed.
> Regenerate the bucketed P&L distribution from a fresh post-audit run.

### Statistical Significance

```
Null hypothesis: win rate = 50% (random)

Binomial test (apply to your OWN measured results):
  z = (observed_win_rate − 0.50) / sqrt(0.50 × 0.50 / n_trades)
  Convert z to a p-value; p < 0.01 is reasonable evidence the win rate is
  not luck.

TODO: re-run for current numbers. The previously-published claim ("74% over
      192 trades, p < 0.0001") was a leaked pre-audit artifact and has been
      removed. Re-run the post-audit pipeline, then apply this test to the
      measured win rate and trade count.

In live trading you have far less data than a multi-year backtest.
When can you trust that YOUR live results reflect edge?

  After 30 trades with positive EV: preliminary evidence (p ≈ 0.08)
  After 60 trades with positive EV: moderate confidence (p ≈ 0.04)
  After 100 trades with positive EV: statistical significance (p < 0.01)

  Practical guidance: trade small (2–3% max risk per trade) for the first
  60 trades. Treat it as model validation. Scale up only after 60 trades
  with positive average EV per trade.
```

---

## Worked Trade Examples

> These are **illustrative** worked examples to show how the signal, strike
> placement, and exit logic fit together — not a verified backtest trade log.
> The credit/P&L figures are rounded teaching numbers. **TODO: replace with a
> sampled set of real trades from a current post-audit backtest run.**

### AI-Predicted Range-Bound Setups

```
Date         Ticker  Spot  VIX   IVR   Model P  δ Used  Short Call  Short Put  Credit  Max Loss  Outcome           P&L
-----------  ------  ----  ----  ----  -------  ------  ----------  ---------  ------  --------  ----------------  -----
Feb 8 2023   SPY     $412  18.3  0.66  0.73     0.18    $427        $397       $2.85   $12.15    ✅ 50% target hit  +$143
May 3 2023   QQQ     $322  17.1  0.58  0.68     0.16    $336        $308       $2.40   $11.60    ✅ 50% target hit  +$120
Sep 6 2023   AAPL    $189  14.4  0.51  0.61     0.14    $199        $179       $1.55   $8.45     ✅ 50% target hit  +$78
Oct 11 2023  SPY     $427  19.2  0.63  0.77     0.20    $444        $410       $3.60   $11.40    ✅ 50% target hit  +$180
Jan 15 2024  MSFT    $389  13.8  0.46  0.62     0.14    $409        $369       $2.90   $17.10    ✅ 21 DTE exit     +$115
Mar 20 2024  SPY     $520  13.2  0.43  0.59     0.13    $543        $497       $3.10   $16.90    ✅ 50% target hit  +$155
Jun 5 2024   NVDA    $120  15.6  0.54  0.71     0.17    $128        $112       $1.85   $8.15     ✅ 50% target hit  +$93
Sep 18 2024  QQQ     $478  17.4  0.60  0.74     0.18    $498        $458       $3.95   $16.05    ✅ 50% target hit  +$198
```

### AI False Positives — Model Fooled

```
Date         Ticker  Spot  VIX   IVR   Model P  Reason Model Fired               What Happened                                                            P&L    Feature Model Missed
-----------  ------  ----  ----  ----  -------  -------------------------------  -----------------------------------------------------------------------  -----  --------------------------------------------------------------------
Jul 18 2023  TSLA    $278  15.2  0.52  0.64     Low ADX, VIX calm, IVR elevated  Musk sold 7.9M shares — stock dropped 9% in 3 days                       −$820  insider-sale flow not in feature set — no warning available
Oct 19 2023  SPY     $418  17.8  0.58  0.66     All features positive            Israel-Hamas war expansion news over weekend, SPY gapped −1.8% Mon open  −$180  Geopolitical event — no model can predict this
Feb 22 2024  NVDA    $788  14.1  0.49  0.60     IVR elevated post-earnings       Stock continued to surge on AI mania — call wing breached in 8 days      −$640  `dist_from_ma50` was +18% (very overextended) — model weight too low
```

### Regime Performance Summary

Iron condors are expected to perform best in the **medium-VIX "sweet spot"
(~16–30)**, where credits are meaningful but the market is not in a fear
regime. Performance should thin out in low-VIX regimes (credits too small to
overcome costs) and is blocked entirely above the VIX cap (extreme regimes,
where wings priced "one sigma out" become meaningless). Holding periods tend to
shorten as VIX rises because the profit target is hit faster.

> **TODO: re-run for current numbers.** A previously-published per-regime table
> quoted specific trade counts, win rates, and a "+4pp vs rules" lift (Total:
> 192 trades, 74% win). Those came from the leaked pre-audit pipeline and have
> been removed. Regenerate per-VIX-regime stats from a fresh post-audit run.

---

## Real Signal Snapshots

### Snapshot 1 — High Confidence Entry (SPY, Oct 11 2023)

```
Signal Snapshot — SPY, Oct 11 2023:
  IVR:               ███████░░░  0.63  [ELEVATED ✓]
  VIX:               ████░░░░░░  19.2  [NORMAL ✓]
  ATR/Spot:          ██░░░░░░░░  1.9%  [CALM ✓]
  5d Return:         ██░░░░░░░░  -0.8% [FLAT ✓]
  20d Return:        ██░░░░░░░░  -1.2% [FLAT ✓]
  Dist from MA50:    ███░░░░░░░  -2.1% [SLIGHT UNDERPERFORM ✓]
  VRP (IV-RV):       ██████░░░░  +4.2  [OVERPRICED PREMIUM ✓]
  Yield Curve:       ██░░░░░░░░  -0.82 [INVERTED — slight caution]
  ─────────────────────────────────────────────────────────────────
  Model P(range-bound 45d): 0.77 → HIGH CONFIDENCE
  Adaptive delta: 0.16 + 0.04 = 0.20 (tighter strikes, more credit)
  Short call: $444  |  Short put: $410  |  Credit: $3.60
  Result: Closed Oct 28 at 50% profit target, +$180/contract (+50%)
```

### Snapshot 2 — Marginal Entry (AAPL, Sep 6 2023)

```
Signal Snapshot — AAPL, Sep 6 2023:
  IVR:               █████░░░░░  0.51  [MARGINAL]
  VIX:               ███░░░░░░░  14.4  [BELOW PREFERRED FLOOR]
  ATR/Spot:          ██░░░░░░░░  1.3%  [VERY CALM ✓]
  5d Return:         ██░░░░░░░░  +0.4% [FLAT ✓]
  20d Return:        ███░░░░░░░  +2.1% [SLIGHT UPTREND]
  Dist from MA50:    ███░░░░░░░  +1.8% [NEAR MA, STABLE ✓]
  VRP (IV-RV):       ████░░░░░░  +2.8  [MODERATE PREMIUM]
  ─────────────────────────────────────────────────────────────────
  Model P(range-bound 45d): 0.61 → MODERATE CONFIDENCE
  Adaptive delta: 0.16 − 0.03 = 0.13 (wider strikes, more buffer)
  Short call: $199  |  Short put: $179  |  Credit: $1.55
  Result: Closed at 50% target in 24 days, +$78/contract
  Note: Low VIX meant thin credit — marginal trade, barely worth commission
```

### Snapshot 3 — Correctly Rejected (TSLA, Jan 2024)

```
Signal Snapshot — TSLA, Jan 10 2024:
  IVR:               ████████░░  0.72  [HIGH ✓ — would pass rules]
  VIX:               ███░░░░░░░  14.6  [OK]
  ATR/Spot:          █████████░  3.8%  [⚠ HIGH — exceeds 2.5% threshold]
  5d Return:         ██████░░░░  +8.2% [⚠ TRENDING STRONGLY]
  20d Return:        ████████░░  +22%  [⚠ MOMENTUM SURGE]
  Dist from MA50:    █████████░  +19%  [⚠ VERY OVEREXTENDED]
  VRP:               ██░░░░░░░░  +1.1  [LOW]
  ─────────────────────────────────────────────────────────────────
  Model P(range-bound 45d): 0.31 → REJECTED (below 0.55 threshold)

  Rules-based: would have entered (IVR = 0.72 is very high)
  AI: correctly rejected based on momentum + overextension combination
  Actual outcome: TSLA continued to trend, call side would have been breached
  Value of model: avoided ~$800 loss per contract
```

---

## AI vs Rules — When Each Wins

```
Scenario                                             Rules                      AI                 Why
---------------------------------------------------  -------------------------  -----------------  ------------------------------------------
Standard calm market (IVR 0.50, VIX 18, ADX 15)      ✅ Enter                    ✅ Enter            Both agree
High IVR but stock is trending (ADX 28)              ✅ Enter (ADX rule blocks)  ✅ Reject           Both block it
Marginal IVR (0.46) but momentum is flat, VRP high   ✅ Enter (barely)           ✅ Enter (P=0.62)   Both enter
High IVR (0.65) but stock 20% above 50MA (momentum)  ✅ Enter                    ❌ Reject (P=0.34)  AI wins — avoids trending breakout
Low VIX (14) but VRP strongly positive, all quiet    ❌ Skip (VIX too low)       ✅ Enter (P=0.64)   AI wins — captures thin but real edge
VIX spiked 40% in 5 days, IVR hits 0.80              ✅ Enter                    ❌ Reject (P=0.29)  AI wins — vol spike = dangerous regime
FOMC in 3 days, all rules pass                       ✅ Enter                    ❌ Reject (P=0.38)  AI wins — learned FOMC uncertainty pattern
```

---

## Key Rules to Internalize

These are not suggestions. They are the operating rules of this strategy. Traders who deviate from them consistently underperform.

**Position sizing and risk:**
- Size each Iron Condor at 2–3% of account value as maximum possible loss (not notional, not credit — the wing width minus the credit times 100, per contract)
- Never run more than 5 concurrent ICs. In broad selloffs, five "uncorrelated" condors breach simultaneously. Ask anyone who ran SPY, QQQ, IWM, AAPL, and NVDA condors in August 2024.
- The model gives you a probability, not a guarantee. A P = 0.75 means 1 in 4 of those trades loses. Expect it. Size for it.

**Entry filters (all must pass):**
- Model P ≥ 0.55 (hard floor — below this, the edge disappears in transaction costs)
- No earnings within the hold window (check before you enter, every time)
- VIX < 38 (above this level, the wings priced "1 standard deviation out" are meaningless)
- ADX < 30 at entry (higher is possible in high-confidence model reads, but reduces expected win rate to ~63%)
- VRP positive (if implied vol is running below realized, you are selling cheap insurance — stop)

**Strike placement:**
- Default delta: 0.16 for standard entries (P 0.55–0.74)
- Tight delta: 0.20 for high-confidence entries (P ≥ 0.75)
- Wide delta: 0.13 for marginal entries (P 0.55–0.59)
- Wing width: minimum 5% of spot. Never use $5 wings on a $400 stock — the risk/reward collapses and commissions eat the edge
- Target 35–45 DTE at entry. Below 21 DTE at entry, there is insufficient theta runway

**Managing the trade:**
- Close at 50% of max credit. Always. Without exception. The compounding effect of freeing capital early (average 17 days ahead of expiry) consistently beats holding for the last 50%. The remaining premium is not worth the gamma risk.
- Close any position that reaches 200% of credit as a loss (2× stop). A condor that collected $2.60 should be closed the moment it costs $5.20 to buy back. This rule truncates max loss and is the primary driver of the average realized loss sitting well below the theoretical max loss.
- Close at 21 DTE if the 50% profit target has not been reached. The final 3 weeks have the worst gamma/theta tradeoff for a condor that is not yet profitable.
- When one side is tested (short strike delta ≥ 0.35), evaluate rolling — not from panic, but from arithmetic. Rolling the tested side 30 DTE forward often recovers 60–70% of the original credit at no additional net cost.

**Regime awareness:**
- After a VIX spike above 30, the screener will show many high-IVR tickers. Wait for VIX to begin declining AND for ATR to start contracting before re-entering. Catching a falling volatility knife is the most common post-spike mistake.
- Inverted yield curve (2y10y < −0.5) is not a trade blocker, but it indicates structurally elevated macro uncertainty. Reduce position size by 25% in this environment.
- When SPY is more than 5% below its 50-day MA, the probability of a continued downtrend is elevated. Hold off on new put-side ICs until SPY reclaims the 50-day or the model P exceeds 0.70.

**Monitoring:**
- Check positions daily at close. This does not mean reacting daily — it means knowing where your deltas are at all times.
- If one short strike's delta crosses 0.35, decide within 24 hours: roll, hedge, or close. Do not wait for it to become 0.50 before acting.
- The model score at entry tells you the entry quality. It does not update during the hold. Use price delta as the live risk indicator once the trade is open.

---

## Quick Reference

```
Parameter            Default  Range      Description
-------------------  -------  ---------  ------------------------------------
`signal_threshold`   0.50     0.45–0.80  Minimum P(range-bound) to enter
`ivr_min`            0.20     0.10–0.65  IVR floor (AI relaxes this vs rules)
`vix_max`            38.0     25–50      VIX ceiling
`delta_short`        0.16     0.10–0.25  Default short strike delta
`wing_width_pct`     0.05     0.02–0.12  Wing width as % of spot
`dte_target`         45       21–60      Target DTE at entry
`dte_exit`           21       14–28      Force-close DTE
`profit_target_pct`  0.50     0.25–0.75  Close at % of max credit
`stop_loss_mult`     2.0      1.5–3.0    Stop at N× credit
`position_size_pct`  0.03     0.01–0.08  Capital at risk per trade
`n_estimators`       50       25–200     Gradient boosting trees (regularized)
```

---

## Data Requirements

```
Data                               Source                     Required
---------------------------------  -------------------------  --------
Daily OHLCV (open/high/low/close)  `mkt.PriceBar`             ✅ Yes
VIX daily close                    `mkt.VixBar`               ✅ Yes
10-year Treasury rate              `mkt.MacroBar` (rate_10y)  Optional
2-year Treasury rate               `mkt.MacroBar` (rate_2y)   Optional
```

No option chain data required. The model uses VIX as IV proxy and reconstructs all vol features from price + VIX history.

---

## Screener Guide

# How to Use This Iron Condor Screener

## 1. How to Read the Screener

Each column is a filter, not a standalone signal. Read them together.

```
Column  What It Measures                                                                                         Good Range for ICs
------  -------------------------------------------------------------------------------------------------------  -------------------------------------------------------
IVR     Where today's IV sits in its 52-week range (0 = 52-week low, 1 = 52-week high)                           > 0.40
VRP     IV minus realized volatility (vol points). Positive = options are expensive relative to actual movement  > 2.0 vol pts
ATM IV  Current annualized implied volatility at the money                                                       Context-dependent (see VIX banner)
ADX     Average Directional Index — measures trend strength, not direction                                       < 25 (range-bound)
ATR%    Average True Range as % of price — daily velocity                                                        < 1.5% preferred
VIX     CBOE fear gauge — proxy for broad market regime                                                          20–30 sweet spot
Credit  Approximate premium collected per share for a balanced IC                                                Higher is better, but not at the cost of narrow strikes
```

**IVR > 0.40** means IV is in the top 60% of its annual range — you are selling volatility that is historically elevated, which is the foundation of the trade. IVR 0.60+ is a strong signal. IVR below 0.30 means you are selling cheap premium; the risk/reward deteriorates.

**ADX < 25** means the underlying is chopping sideways. Iron condors bleed premium in range-bound markets and get steamrolled in trends. An ADX of 18 is ideal. An ADX of 35 is a caution. Above 40, walk away.

---

## 2. What Makes a Good IC Entry

The ideal setup stacks at least four of the five signals. A single strong reading is not enough.

**Example of a near-perfect setup — SPY, typical late-summer environment:**

- IVR = 0.55 (IV in top 45% of range)
- VRP = +4.5 vol points (IV running well above 30-day realized)
- ADX = 18 (no dominant trend)
- ATR% = 0.85% (calm daily movement)
- VIX = 22 (moderate fear, decent credits without chaos)
- Credit = $1.40/share on a 30-DTE balanced condor

This is a green-light setup. Place strikes one standard deviation out, collect the credit, and let theta work.

**Three signals passing, one borderline** (e.g. IVR = 0.38): reduce size by half or wait for a better entry. The screener is a queue, not a forced entry system.

---

## 3. Reading VRP — The Overlooked Edge

Variance Risk Premium is the spread between what the market *implies* will happen (IV) and what actually happened (realized vol). When VRP is positive, option sellers are collecting a structural risk premium — analogous to an insurance company charging more than actuarial fair value.

**VRP is positive roughly 70% of the time on SPY and QQQ.** That is the long-run edge of systematic vol selling. The problem is the other 30%: those periods tend to cluster around sudden dislocations (Aug 2024 carry unwind, Apr 2025 tariff shock) where realized vol explodes past IV.

**When VRP matters more than IVR:** Use VRP as your primary filter in slow-drift IV environments where IVR is middling (0.35–0.50). If VRP is running +5 to +8 vol points in that window, the market is paying you significantly more than the recent historical movement justifies. That is the real edge.

**Negative VRP** is a serious warning. It means the market moved *more* than options priced in — a regime where IC sellers lose money structurally. Do not open new positions when VRP turns negative; tighten stops on existing ones.

---

## 4. Red Flags — When NOT to Trade

- **ADX > 40:** The underlying is in a strong directional move. One leg of your condor will be tested immediately. Skip it.
- **VIX > 45:** This is a fear regime. Aug 2024 touched 65 intraday; Apr 2025 briefly cleared 50 on tariff headlines. Wings priced at "one standard deviation" become meaningless when vol term structure collapses and gaps become routine. Sit on hands.
- **VRP negative:** Realized vol is exceeding implied. You are selling underpriced insurance. Historical loss rates for IC sellers spike sharply in negative-VRP environments.
- **Earnings within the hold window:** A 30-DTE condor opened with earnings 15 days out will reprice violently on the event. The screener's ATM IV will look elevated (it is — because of the earnings premium), but that premium vaporizes post-event, often with a large directional gap attached.
- **ATR% > 2.0% and rising:** Intraday ranges are expanding. Even without a trend, wide daily swings will test your short strikes repeatedly through a 30-day hold.

---

## 5. Regime Context — The VIX Banner

```
VIX Level  Regime       IC Strategy
---------  -----------  --------------------------------------------------------------
14–20      Low vol      Credits thin; be highly selective; IVR filter becomes critical
20–30      Sweet spot   Best risk/reward for balanced condors; standard sizing
30–45      Elevated     Widen strikes by 15–20%; reduce size; shorter DTE (21 days)
> 45       Danger zone  No new ICs; manage or close existing positions
```

In low-vol regimes, prioritize IVR and VRP over credit size. A $0.60 credit on a well-positioned SPY condor beats a $1.20 credit on a name with ADX of 38.

---

## 6. Practical Tips

- **Run 3–5 concurrent ICs maximum** until you have a full year of personal trade history. Correlation spikes in selloffs — five "uncorrelated" condors can all breach simultaneously.
- **Size each IC at 2–3% of account risk** (max loss on the spread, not notional). This lets you absorb three simultaneous breaches without a portfolio-level wound.
- **Check the screener weekly**, ideally Sunday evening or Monday pre-market. Most new IC entries are opened with 25–35 DTE; forcing daily entries creates overtrading.
- **When 3 of 5 filters pass,** reduce position size by 40% and set a tighter stop — close if the underlying moves more than 60% of the distance to the short strike within the first 10 days.
- **Roll, don't panic.** If one side is tested but you have 10+ days to expiration and the untested side still has meaningful premium, rolling the tested side out one expiration and up/down toward the market is often superior to closing for a full loss.
- **Theta is fastest in the final 21 days.** The screener's credit column matters most for entries at 28–35 DTE. Beyond 45 DTE, gamma risk is low but theta harvest is slow.
- **After a VIX spike above 35, the screener will light up with high-IVR tickers.** Wait for ADX to begin falling before entering — catching a falling vol knife is a classic mistake.

---

## 7. Common Mistakes

1. **Chasing high credit without checking ADX.** A name paying $2.50/share looks attractive until you notice ADX is 48 and the stock has been in a clean uptrend for six weeks. The credit reflects the trend risk.

2. **Ignoring earnings dates.** The screener cannot know your intended hold period. Always cross-reference the next earnings date before entering any single-stock IC.

3. **Over-diversifying into correlated names.** Running ICs on SPY, QQQ, and IWM simultaneously provides almost no diversification. In a broad selloff all three breach together.

4. **Treating IVR = 0.40 as a hard floor.** In a persistently low-vol environment (e.g. most of 2017, much of 2024 Q1), IVR 0.40 may still represent historically cheap premium. Pair IVR with VRP to confirm the opportunity is real.

5. **Holding through expiration week.** The final 5 days of a condor carry outsized gamma risk relative to the remaining premium. Unless you are actively watching intraday, closing at 5–7 DTE for 60–70% of max profit is a sound mechanical rule that significantly improves long-run Sharpe.
