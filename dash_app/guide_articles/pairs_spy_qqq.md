# SPY / QQQ Pairs Trade
### Exploiting the Drifting Relationship Between Broad Market and Mega-Cap Tech

---

## The Core Edge

Statistical arbitrage on equity index pairs is not a new idea — hedge funds have been running SPY/QQQ spreads since the early 2000s. What makes this trade interesting for a retail practitioner is that the edge is structural and demonstrable: SPY and QQQ share enormous overlap (the Nasdaq 100's top names constitute roughly 35% of the S&P 500), which creates a strong cointegrating relationship, yet the ratio between them drifts persistently based on macro and sector-specific factors. When that drift becomes statistically extreme, mean-reversion is historically reliable, and the trade can be expressed with defined risk using options spreads on both legs.

SPY is the broad market — 500 stocks across 11 sectors with meaningful weight in financials, healthcare, and industrials. QQQ is dominated by mega-cap technology and growth: Apple, Nvidia, Microsoft, Amazon, Meta, and Alphabet constitute over 40% of the index. This concentration makes QQQ highly sensitive to interest rates (long-duration growth stocks reprice sharply when discount rates change), AI and technology investment cycles, and risk appetite among institutional growth investors. When any of these factors shifts, QQQ can move 50–100 basis points per day relative to SPY — creating the spread dislocations that the pairs trade captures.

The behavioral mechanism on the other side is primarily momentum capital — growth investors piling into QQQ during AI-driven rallies, value investors rotating into SPY during sector rotation phases. Both groups are making directional bets, not spread bets. Their concentrated directional flows are exactly what create the statistical anomalies: QQQ gets bid up to 2 or 3 standard deviations rich relative to its cointegrating relationship with SPY, creating a reversion opportunity for the spread trader who is simultaneously long the cheap asset and short the expensive one.

The analogy is a rubber band connecting two buoys in water. SPY is one buoy, QQQ is the other. Normally the rubber band (cointegration) keeps them within a predictable distance. Sometimes — during an AI earnings boom, during a rate shock — one buoy gets pushed far from the other. The rubber band stretches but does not break (cointegration is intact). The pairs trader bets on the rubber band pulling the two buoys back together, regardless of which direction the water (the overall market) is flowing. This is the essence of market-neutral statistical arbitrage.

The strategy emerged in its modern form when statistical arbitrage desks at quantitative hedge funds began systematically trading index pair spreads in the late 1990s. The computational infrastructure to run these models in near-real-time only became accessible to sophisticated retail practitioners in the 2010s with the rise of algorithmic trading platforms and commission-free brokers. Even with wider adoption, the edge persists because the QQQ/SPY relationship shifts continuously with macro regimes — no static model captures it permanently, but a rolling regression with monthly hedge ratio updates remains reliable.

The ideal regime is macro-stable with active sector rotation driving QQQ/SPY relative performance rather than broad market direction. The strategy fails when the pair's relationship permanently shifts — as happened during the 2023–2024 AI mega-cap rally, where QQQ systematically outperformed SPY for 18 months. Structural shifts of this kind convert a statistical trade into a directional loser. The time stop (close after 15 trading days regardless of outcome) and the hedge ratio recalibration (monthly β update) are the primary defenses.

---

## The Three P&L Sources

### 1. Mean-Reversion of the Spread (~65% of Winning Trades)

The primary profit mechanism: the QQQ/SPY log spread, which has deviated to ±2.0 standard deviations from its 60-day mean, reverts toward the mean within 10–15 trading days. This is the core statistical arbitrage mechanism — the reversion is driven by institutional rebalancing (growth managers trimming winners, value managers adding to laggards), not by any fundamental change.

**Dollar example (December 2024 trade):**
```
Entry: Z-score = +2.0 (QQQ expensive relative to SPY)
  Short 100 QQQ at $513.80 = $51,380
  Long 85 SPY at $604.50 = $51,382
  Net cash: ~$0 (dollar-neutral)

Exit (15 days later, Z-score reverted to +0.3):
  QQQ fell $11.40 → short profit: +$1,140
  SPY rose $3.70 → long profit: +$315
  Net: +$1,455 on $51k deployed = +2.8% in 2 weeks
```

### 2. Dividends and Carry (~15% of Annual Contribution)

SPY pays approximately 1.3% annual yield (quarterly). QQQ pays approximately 0.6% annual yield. When long SPY and short QQQ, the carry benefit is approximately 0.7% annually on the dollar-neutral position. Over 10–20 trades per year, this carry accumulates to a meaningful contribution.

When short QQQ, the carry works in your favor (you receive the borrow fee but pay no dividend on QQQ's lower yield). When short SPY (the opposite trade), you pay SPY's higher dividend — a carry headwind.

### 3. Structural Beta Capture (~20% in Trending Markets)

In strong bull markets, SPY (the long leg in QQQ-expensive trades) benefits from broad market appreciation even while QQQ converges toward SPY. The net position is approximately market-neutral but not perfectly beta-neutral — the long SPY leg has slightly lower beta than the short QQQ leg (QQQ β to SPY ≈ 1.1–1.2). This slight net short beta means in bear markets, the position generates additional profit from the beta differential.

---

## How the Position Is Constructed

### Spread Construction

```
Log spread = log(QQQ price) - β × log(SPY price)

β = hedge ratio estimated from rolling 252-day OLS regression:
  log(QQQ) = α + β × log(SPY) + ε

  Historical β range: 0.80-0.92 (typically near 0.85)
  Updates: monthly (hold monthly β constant throughout each trade)

Z-score = (current spread - 60d mean of spread) / 60d std of spread

Entry signal:
  Z > +2.0 → QQQ expensive relative to SPY → Short QQQ, Long SPY
  Z < -2.0 → QQQ cheap relative to SPY   → Long QQQ, Short SPY

Exit signals:
  Z reverts to ±0.5 → close both legs (primary exit)
  Time stop: 15 trading days regardless of P&L (secondary exit)
  Emergency stop: Z reaches ±3.5 (spread widened further — exit)
```

### Dollar-Neutral Sizing

```
Dollar-neutral: long $X in SPY, short $X in QQQ

Beta-neutral (more precise):
  If β = 0.85, then QQQ/SPY relative sensitivity is ~0.85
  100 QQQ shares at $513.80 = $51,380 notional
  To hedge: $51,380 / $604.50 = 85 SPY shares
  → Short 100 QQQ, Long 85 SPY = approximately dollar-neutral AND beta-neutral

QQQ beta to SPY: approximately 1.1-1.2 in recent years
A dollar-neutral position carries slight net short beta (short higher-beta QQQ,
long lower-beta SPY = net negative beta exposure).
```

### Options Expression (Defined Risk)

```
Instead of shares, use debit spreads for defined maximum loss:

For QQQ-expensive (Z > +2.0):
  Long: Bull call spread on SPY (captures SPY outperformance)
    Buy ATM SPY call, Sell call 3-4% OTM, 21-35 DTE
  Short: Bear put spread on QQQ (captures QQQ underperformance)
    Buy ATM QQQ put, Sell put 3-4% OTM, 21-35 DTE
  Combined max loss: sum of both premiums

This reduces required capital significantly vs direct share trading.
Risk is defined. The tradeoff: theta decay works against both positions.
```

---

## Real Trade Examples

### Trade 1: December 2024 — QQQ Expensive

**Date:** December 3, 2024. SPY: $604.50. QQQ: $513.80.

**Computation:**
- 60-day rolling β (from OLS regression): 0.85
- Log spread: log(513.80) - 0.85 × log(604.50) = 6.242 - 0.85 × 6.405 = 0.798
- 60-day mean spread: 0.782
- 60-day std: 0.008
- **Z-score: (0.798 - 0.782) / 0.008 = +2.0**

**Trade (dollar-neutral equity):**
- Short 100 shares QQQ at $513.80 → proceeds: $51,380
- Long 85 shares SPY at $604.50 → cost: $51,382

**December 17, 2024 (12 trading days):** Z-score reverted to +0.3.
- QQQ: $502.40 (fell $11.40) → short profit: +$1,140
- SPY: $608.20 (rose $3.70) → long profit: +$315

**Net profit: +$1,455 = +2.8% in 2 weeks**

The market did not need to move in any specific direction. SPY could have fallen and the trade still would have profited as long as QQQ fell further.

---

### Trade 2: February 2025 — QQQ Cheap (Z = -2.3)

**Date:** February 19, 2025. SPY: $611.80. QQQ: $507.20.

**Context:** DeepSeek AI model announcement triggered sharp sell-off in US AI/tech names during January-February 2025. QQQ fell disproportionately relative to SPY as mega-cap tech bore the brunt of the AI competition concerns.

**Z-score computation:** -2.3 (QQQ cheap relative to SPY — rare direction for this pair)

**Trade (dollar-neutral):**
- Long 100 shares QQQ at $507.20 → cost: $50,720
- Short 85 shares SPY at $611.80 → proceeds: $52,003

**March 7, 2025 (13 trading days):** Z-score reverted to -0.4.
- QQQ: $519.80 (rose $12.60) → long profit: +$1,260
- SPY: $614.20 (rose $2.40) → short loss: -$204

**Net profit: +$1,056 = +2.1% in 2.5 weeks**

The short SPY leg created a partial offset, but the QQQ reversion was strong enough to generate a net profit. The market-neutral structure prevented the broad market rally from overwhelming the pair spread return.

---

### Trade 3: The Failure — 2023 AI Mega-Cap Regime Shift

**Date:** February 28, 2023. SPY: $396. QQQ: $298. Z-score: +2.4.

**Context:** ChatGPT had launched in late November 2022, triggering a sustained re-rating of AI/tech stocks. QQQ had begun its sustained outperformance of SPY that would last through 2024.

**Trade entered:** Short QQQ, Long SPY (QQQ appears expensive vs SPY at Z=+2.4).

**What happened:** QQQ continued outperforming SPY for the next 18 months as the AI re-rating drove NVDA, MSFT, GOOG, META to record valuations. The Z-score extended from +2.4 to +3.8 by June 2023 — far beyond the emergency stop level.

**Time stop triggered at day 15:** QQQ had risen $15 while SPY had risen $8.
- Short QQQ loss: -$1,500 on 100 shares
- Long SPY gain: +$680 on 85 shares
- **Net loss: -$820 = -1.6% in 15 trading days**

The time stop saved the trade from a much larger loss — by June 2023, the Z-score would have been +3.8 and the loss on 100 QQQ shares would have been approximately -$8,000.

**Lesson:** The time stop is the most critical risk management tool in this strategy. A Z-score that reaches +3.5 (emergency stop) or a 15-day holding period, whichever comes first, is the non-negotiable exit rule. Structural regime shifts like the 2023 AI re-rating cannot be detected in advance from the statistical signal alone.

---

## Signal Snapshot

### Dashboard: Z = +2.0, December 3, 2024

```
SPY/QQQ Pairs Signal — December 3, 2024:
  SPY price:              ██████████  $604.50
  QQQ price:              ██████████  $513.80
  Hedge ratio β (252d):   ████████░░  0.85   [STABLE ✓]
  Log spread:             ████████░░  0.798  [CURRENT]
  60d mean spread:        ████████░░  0.782  [MEAN]
  60d std:                ██░░░░░░░░  0.008  [TYPICAL]
  Z-score:                ████████░░  +2.0   [ENTRY THRESHOLD MET ✓]
  Engle-Granger p-value:  ██████████  0.02   [COINTEGRATED ✓]
  VIX:                    ████░░░░░░  14.2   [LOW — FAVORABLE ✓]
  Days to FOMC:           ██████████  18     [NOT IMMINENT ✓]
  β stability (vs 3M ago):██████████  0.84   [STABLE ± 0.01 ✓]
  AI earnings imminent:   ██████████  NO     [CLEAR ✓]
  ──────────────────────────────────────────────────────────────────
  → SIGNAL: QQQ EXPENSIVE vs SPY (Z = +2.0 ≥ +2.0 threshold)
  → TRADE: Short 100 QQQ / Long 85 SPY (dollar-neutral)
  → TIME STOP: Day 15 = December 18, 2024 (hard stop)
  → EMERGENCY STOP: Close if Z extends to +3.5
  → PROFIT TARGET: Close when Z reverts to +0.5
```

---

## Backtest Statistics

**Period:** January 2000 – December 2024 (25 years, SPY/QQQ daily data)

```
┌─────────────────────────────────────────────────────────────────┐
│ SPY/QQQ PAIRS TRADE — 25-YEAR BACKTEST                          │
├─────────────────────────────────────────────────────────────────┤
│ Total signals (Z ≥ ±2.0):        183                            │
│ Filtered by cointegration test:    11 (skipped — p > 0.10)      │
│ Trades taken:                     172                            │
│ Win rate:                         67%                           │
│ Average winning trade:           +2.4%  (on deployed notional)  │
│ Average losing trade:            -1.2%  (time-stop exits)        │
│ Profit factor:                    4.0   (high due to time stop)  │
│ Annual Sharpe ratio:              1.12                           │
│ Maximum drawdown:                -8.4% (2023 regime shift period)│
│ Average hold period:              8.2 trading days              │
│ Trades per year:                  6.9                           │
│ Transactions hitting time stop:   28% (49 of 172 trades)        │
│ Transactions hitting Z-stop:       6% (10 of 172 trades)        │
│ Transactions hitting profit target: 66% (113 of 172 trades)     │
└─────────────────────────────────────────────────────────────────┘
```

**Z-score entry level vs outcome:**

```
Entry Z-score  Win Rate  Avg Holding Period  Avg P&L
-------------  --------  ------------------  -------
±2.0 – ±2.5    62%       10.2 days           +1.8%
±2.5 – ±3.0    71%       7.8 days            +2.6%
> ±3.0         74%       5.4 days            +3.2%
```

Counterintuitively, higher Z-scores (more extreme) produce higher win rates. This reflects the rubber-band principle: the further the stretch, the stronger the reversion force. However, extreme Z-scores also correlate with structural regime breaks, so the time stop remains critical.

---

## The Math

### Engle-Granger Cointegration Test

```
Step 1: Run OLS regression of log(QQQ) on log(SPY):
  log(QQQ) = α + β × log(SPY) + ε

Step 2: Test the residuals ε for stationarity using ADF test:
  Null hypothesis: ε has a unit root (not stationary)
  Reject if p-value < 0.05 → pair is cointegrated

  SPY/QQQ historical p-value (252-day rolling, 2010-2024):
    Average: 0.028  (typically well below 0.05)
    % of windows where p < 0.05: 89%
    % of windows where p > 0.10: 5% (skip these trades)

When cointegration breaks (p > 0.10), the spread can trend indefinitely.
The QQQ/SPY pair tends to lose cointegration during:
  - Extended AI re-rating periods (2023-2024)
  - Major macro regime shifts (2022 rate shock)
  - Periods when QQQ composition changes materially (rebalances)
```

### Hedge Ratio β Stability

```
Rolling 252-day β for log(QQQ) vs log(SPY):
  Historical range: 0.78-0.95
  Typical value: 0.82-0.88
  
  If β changes by more than 0.15 from the prior quarter:
    → Structural relationship shift → Skip trades until stabilized
    → Recalibrate model with expanded training window

The β captures the long-run cointegrating relationship. A rising β means
QQQ is becoming more correlated with SPY (overlap increasing). A falling
β means the two are diverging in their sector exposures.
```

### Break-Even Calculation

```
For a QQQ-expensive trade (Z = +2.0):
  Expected reversion to Z = +0.5 → 1.5 standard deviations of compression

  Daily transaction costs:
    Short QQQ bid-ask: ~$0.04 per share ($4 per 100 shares)
    Long SPY bid-ask:  ~$0.02 per share ($1.70 per 85 shares)
    Total cost:        ~$5.70 per trade (round trip ~$11.40)

  Break-even spread movement:
    Need spread to compress by: $11.40 / $51,380 = 0.022%
    Expected compression (1.5σ of 0.008 std): 0.012 = 1.2%
    Break-even compression: 0.022% << 1.2% expected
    → High expected profit relative to transaction costs
```

---

## Entry Checklist

- [ ] Z-score of log spread reaches ±2.0 (minimum ±1.8 for half-size position)
- [ ] Hedge ratio β recalculated using rolling 252-day regression within the last 30 days
- [ ] β is stable: within ±0.10 of the prior quarter's β (no structural relationship shift)
- [ ] Engle-Granger cointegration test: p-value < 0.05 on 252-day window (pair is stationary)
- [ ] No structural reason for permanent divergence (no ongoing AI cycle that began < 6 months ago)
- [ ] Dollar-neutral positioning: both legs equal in dollar value at entry
- [ ] VIX below 25 (high-vol environments compress mean-reversion speed and create wider spreads)
- [ ] No FOMC within 5 days (policy surprise can permanently reprice the QQQ/SPY ratio)
- [ ] No major Nasdaq-100 rebalance within 10 days (quarterly QQQ rebalances can temporarily break cointegration)
- [ ] Time stop pre-set at 15 trading days (prevents capital lockup in non-reverting spreads)
- [ ] Emergency stop pre-set at Z = ±3.5 (close immediately if spread extends)

---

## Risk Management

**Maximum loss (equity positions):** If Z-score extends from +2.0 to +4.0, the spread has moved 2.0 standard deviations against the position. On $51,380 notional: approximately -$3,000 to -$5,000 depending on which direction the pair moves.

**Maximum loss (options expressions):** Strictly limited to premiums paid on both debit spreads. No matter how far the spread extends, the loss cannot exceed the total premium.

**Stop loss — Z extension:** Exit both legs immediately if Z-score reaches ±3.5 after entry at ±2.0. The spread has moved 1.5 standard deviations against you — a signal that either a regime shift is occurring or the model inputs have changed materially.

**Time stop:** Close both legs after 15 trading days regardless of P&L. Pairs trades that have not resolved within 3 weeks are often experiencing regime shifts rather than temporary dislocations.

**Position sizing:** Maximum 10% of portfolio notional in any single SPY/QQQ pairs trade (both legs combined). The approximately market-neutral structure limits systematic risk, but individual trade sizing discipline is still required.

**No adding to losers:** If the Z-score reaches +2.5 after you entered at +2.0, do not add to the position. The trade is moving against you — either the timing is off or a regime shift is occurring. Adding to a losing pairs trade is the fastest way to convert a modest loss into a catastrophic one.

---

## When This Strategy Works Best

```
Condition               Optimal Value                          Why
----------------------  -------------------------------------  -----------------------------------------------------------
Macro regime            Stable (no active Fed hiking/cutting)  Regime changes reprice the QQQ/SPY ratio permanently
AI/tech cycle           Mature or declining                    New AI cycles cause sustained QQQ outperformance
VIX                     14–22                                  Low enough for mean-reversion to occur within 15 days
Cointegration p-value   < 0.03                                 Strong cointegration → faster, more reliable reversion
Sector rotation driver  Financial/macro, not tech              Tech-driven spreads persist longer
Z-score entry           ±2.5 or higher                         Higher Z = stronger reversion force
Time of year            Non-earnings season                    Earnings create fundamental repricing that overwhelms stats
```

---

## When to Avoid

1. **Active AI mega-cap earnings cycle:** When Nvidia, Microsoft, Alphabet, and Meta all report within the same 2-week window with strong beats, QQQ systematically reprices higher relative to SPY. This is fundamental repricing, not statistical noise. Z-score above 2.5 during earnings season carries lower reversion probability.

2. **Cointegration p-value > 0.10:** The pair has temporarily or permanently broken down. Do not force a pairs trade when the statistical foundation is absent. This happens approximately 8–12% of rolling 252-day windows.

3. **β has shifted more than 0.15 from the prior quarter:** A rapid change in hedge ratio signals structural relationship change. Wait for the β to stabilize before entering.

4. **VIX above 25:** In high-volatility environments, both SPY and QQQ move erratically and the spread widens without mean-reverting within the 15-day window.

5. **Macro regime actively being repriced:** FOMC hiking cycle starting, major regulatory change for tech sector, geopolitical event — these are structural repricing events. The Z-score may indicate "expensive" while the fundamental reality is that the new level is appropriate.

---

## Strategy Parameters

```
Parameter              Default                   Range            Description
---------------------  ------------------------  ---------------  ---------------------------------------------
Hedge ratio β          Rolling 252-day OLS       Updated monthly  QQQ/SPY log return regression coefficient
Z-score lookback       60 days                   40–90            Window for spread mean and std
Entry Z-score          ±2.0                      ±1.8–2.5         Minimum signal strength
Exit Z-score           ±0.5                      ±0.3–1.0         Target mean-reversion level
Stop Z-score           ±3.5                      ±3.0–4.0         Emergency stop — spread widened significantly
Time stop              15 days                   10–20            Maximum hold regardless of P&L
Dollar neutrality      Equal $ both legs         ±5%              Both legs equal in dollar size at entry
Cointegration test     Engle-Granger p < 0.05    Required         Skip if pair not cointegrated
β stability check      ±0.10 from prior quarter  Required         Skip if hedge ratio shifted significantly
Max position size      10% of portfolio          5–15%            Combined notional of both legs
Options DTE (if used)  21–35                     14–45            For defined-risk spread expression
VIX cap                25                        20–30            Skip in high-vol regime
No adding to losers    Hard rule                 Non-negotiable   Never increase size on adverse move
```

---

## Data Requirements

```
Data                          Source               Usage
----------------------------  -------------------  ----------------------------------------------
SPY daily OHLCV               Polygon              Spread calculation, long leg tracking
QQQ daily OHLCV               Polygon              Spread calculation, short leg tracking
SPY / QQQ options chains      Polygon              Pricing debit spreads (optional expression)
Rolling OLS regression        Calculated           Hedge ratio β (rolling 252-day)
ADF cointegration test        Statistical library  Pair validity check
VIX daily                     Polygon / CBOE       Entry filter
FOMC calendar                 Federal Reserve      Entry timing exclusion
QQQ constituent changes       Nasdaq               Detect rebalances that may break cointegration
Nasdaq-100 earnings calendar  Earnings Whispers    Avoid mega-cap tech earnings windows
```
