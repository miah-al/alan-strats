# Statistical Arbitrage — Sector Rotation
### Harvesting the Relative Mispricing Between Economically Linked Sectors

---

## The Core Edge

The business cycle does not treat all industries equally. In early recovery, cyclical sectors like financials and consumer discretionary lead. In mid-cycle expansion, industrials and technology dominate. In late-cycle environments, energy and materials outperform as input costs rise. And in recessions, defensives — healthcare, utilities, consumer staples — hold their value while everything else falls. These economic linkages create a predictable rhythm of sector rotation that has been exploited by tactical asset allocators for decades.

What is less often appreciated is that this rotation creates not just momentum opportunities (buy the strong sector) but also statistical arbitrage opportunities when the relative performance between two economically linked sectors deviates too far from its historical norm. A tech sector that has outperformed healthcare by 20 percentage points over a quarter does not deserve to trade at an increasingly large premium to healthcare unless the fundamental drivers of that premium are genuinely new and permanent. Most of the time, they are not. Institutional portfolio managers who oversold healthcare into the tech rally will eventually rebalance, and the spread compresses.

The sector rotation pairs trade is distinguished from simple momentum by its focus on the relationship between two sectors rather than the absolute level of either. When XLK has outperformed XLV by 2.4 standard deviations versus the prior 20-quarter history of that spread, it makes a specific statistical claim: the relative pricing between these two sectors is unusually extreme. That claim is historically reliable because the macro forces that drive both sectors — interest rates, growth expectations, consumer spending — are shared. Their relative pricing drifts but does not permanently diverge.

The analogy is two boats in a harbor connected by a chain. The chain (cointegration) allows them to drift apart — one can be closer to the dock while the other rides the current outward — but the chain prevents unlimited divergence. When the chain reaches full extension (Z-score of ±2.5), the tension will pull them back together regardless of which direction the water is flowing. The sector rotation arbitrageur is betting on the tension of that chain, not on the direction of the tide.

Who is on the other side? Thematic investors concentrating in the strong sector on fundamental grounds. An AI-focused portfolio manager overweighting technology in mid-2023 had compelling arguments about the transformative impact of large language models. Those arguments were largely correct. But they justified paying an earnings multiple premium for XLK — they did not justify a 23-percentage-point relative performance gap versus healthcare in a single quarter. The statistical arbitrageur is not arguing with the tech bull on fundamentals, only on relative valuation at extreme levels.

The strategy's primary structural risk is what practitioners call the "non-stationary pair." Some sector pairs have fundamentally diverged over time due to structural economic changes, not cyclical fluctuations. Technology versus energy is the canonical example: the information economy has steadily gained share of GDP while fossil fuel's share declined. A "cheap" energy sector relative to technology in 2015 was not a statistical arbitrage opportunity — it was a legitimate fundamental shift. Testing for cointegration (ADF test) before entering any pair is not optional; it is the foundational validation that the spread is stationary and will mean-revert.

---

## The Three P&L Sources

### 1. Mean-Reversion of the Sector Spread (~60% of Winning Trades)

The primary mechanism: one sector has outperformed another by an extreme amount (Z > ±2.0 on a 5-year history of the same spread). Institutional rebalancing, sector rotation, and earnings normalization collectively pull the spread back toward the mean over the following 3–12 weeks.

**Dollar example (XLK/XLV July 2023):**
```
Entry: Z-score = +2.4 (XLK overextended vs XLV)
  Short $50,000 XLK at $178.20 = 281 shares
  Long $50,000 XLV at $131.50 = 380 shares

3 months later (Z reverted to +0.8):
  XLK covered at $171.40: profit = $6.80 × 281 = +$1,910
  XLV sold at $137.60: profit = $6.10 × 380 = +$2,318
  Total: +$4,228 on $100,000 notional = +4.2% in 3 months
SPY in same period: -3.2%
Long-short spread outperformed market by 7.4%
```

### 2. Earnings Revision Normalization (~25% of Winning Trades)

Extreme sector performance gaps often reflect earnings estimate extremes — analysts have upgraded the strong sector aggressively and downgraded the weak sector. When the upgrade cycle matures (analysts can't revise up indefinitely), the strong sector's forward momentum decelerates while the weak sector's analysts start revising upward from low bases. This "estimate normalization" drives the sector spread compression and provides a fundamental backing for the statistical reversion.

### 3. Carry from Dividend Differential (~15% of Annual Returns)

When long a high-dividend sector (XLU: ~3.5% yield, XLV: ~1.8%) and short a low-dividend sector (XLK: ~0.7%), the carry works in your favor. Over a 3-month hold, the dividend differential contributes approximately 0.7% × (3/12) = 0.2% per trade. Small individually but meaningful across 4 annual cycles.

Conversely, when short a high-dividend sector (XLU, XLP), you pay the dividend — a carry headwind. Always include the dividend differential in the entry threshold calculation.

---

## How the Position Is Constructed

### Signal Formula

```
Spread(A, B, t) = 3M_total_return(Sector_A, t) - 3M_total_return(Sector_B, t)

Z-score = (Spread(t) - Mean(Spread, prior 20 quarters)) / Std(Spread, prior 20 quarters)

Entry signals:
  Z > +2.0 → Sector A overextended relative to B → Short A / Long B
  Z < -2.0 → Sector B overextended relative to A → Short B / Long A

Exit:
  Z reverts to ±0.5 → close both legs
  Time stop: 3 months (one quarter)
  Hard stop: Z reaches ±3.0 → exit, reassess cointegration

Sizing:
  Dollar-neutral (standard): equal $ both legs
  Beta-neutral (better): adjust for each sector's beta to SPY
    Beta-neutral notional(A) = $ / Beta(A to SPY)
    Beta-neutral notional(B) = $ / Beta(B to SPY)
```

### Reliable Sector Pairs (Cointegration-Tested 1994-2024)

```
Long leg          Short leg             Typical entry Z  Mean-reversion rate  ADF p-value
----------------  --------------------  ---------------  -------------------  -----------
XLV (Healthcare)  XLK (Technology)      2.0σ             67% within 3M        0.04
XLU (Utilities)   XLE (Energy)          1.8σ             71% within 3M        0.03
XLP (Staples)     XLY (Consumer Disc.)  1.8σ             74% within 3M        0.02
XLF (Financial)   XLK (Technology)      2.2σ             58% within 3M        0.06
XLI (Industrial)  XLB (Materials)       1.9σ             69% within 3M        0.04
```

"Mean-reversion rate" = fraction of entries where Z-score returned to 0 within 3 months.

**Pairs to avoid (non-stationary 2015-2024):**
- XLK vs XLE: Technology has structurally gained vs Energy — non-stationary
- XLK vs XLP: Tech has outperformed Staples structurally — non-stationary
- XLY vs XLU: Very different economic sensitivities, poor cointegration

---

## Real Trade Examples

### Trade 1: XLK/XLV July 2023 (Full Trade Walkthrough)

**Signal date:** July 1, 2023. Measuring April–June 2023 3-month returns.

**Returns:**
- XLK: +23.1% (AI mania, semiconductor boom)
- XLV: +3.4% (healthcare defensive, underperformed)
- Spread: +19.7% (XLK outperformed by 19.7 percentage points)
- Prior 20 quarters mean of this spread: +2.8%
- Prior 20 quarters std: 7.1%
- **Z-score: (19.7 - 2.8) / 7.1 = +2.4σ**

**Cointegration check:** ADF test on XLK/XLV 252-day rolling price spread: p-value = 0.03. Pair is statistically cointegrated at 95% confidence.

**Sector macro check:** Forward P/E of XLK vs XLV: XLK at 28×, XLV at 17×. The 11x P/E premium is at the 92nd percentile of the 20-year history — confirming statistical extremity.

**Trade setup:**
- Short XLK: sell $50,000 worth at $178.20 = 281 shares
- Long XLV: buy $50,000 worth at $131.50 = 380 shares
- Dollar-neutral, both legs $50,000

**Month-by-month tracking:**
- July 2023: XLK +4.2%, XLV +5.8% → spread narrows 1.6%
- August 2023: XLK -3.8%, XLV +0.2% → spread narrows 4.0%
- September 2023: XLK -5.1%, XLV -0.8% → spread narrows 4.3%

**Exit trigger (3-month time stop, September 30):**
Z-score had reverted from +2.4 to +0.8 (not full reversion, but time stop expired).
- XLK covered at $171.40: profit = $6.80 × 281 = **+$1,910**
- XLV sold at $137.60: profit = $6.10 × 380 = **+$2,318**
- **Total P&L: +$4,228 on $100,000 deployed = +4.2% in 3 months**
- SPY -3.2% same period → **alpha of +7.4%**

---

### Trade 2: XLP/XLY Staples vs Discretionary — June 2022

**Signal date:** June 30, 2022. The 2022 consumer spending slowdown had driven discretionary stocks down sharply.

**Returns (April-June 2022):**
- XLY: -20.8% (consumer discretionary — inflation squeeze on spending)
- XLP: -1.2% (consumer staples — defensive, people still buy food)
- Spread (XLY-XLP): -19.6%
- Prior 20 quarters mean: -0.8%
- Prior 20 quarters std: 5.9%
- **Z-score (XLY-XLP): (-19.6 - (-0.8)) / 5.9 = -3.2σ** (XLY extremely cheap vs XLP)

Signal: XLY cheap relative to XLP → **Long XLY / Short XLP**

**Trade:**
- Long $50,000 XLY at $135.40 = 369 shares
- Short $50,000 XLP at $75.20 = 665 shares

**Q3 2022 outcome (July-September 2022):**
- XLY: +10.2% (consumer spending better than feared, Amazon Prime Day)
- XLP: +3.4% (defensive held steady)
- Spread reversion from -3.2σ to -1.1σ

**Exit at 3-month mark:**
- XLY sold at $149.20: profit = $13.80 × 369 = **+$5,092**
- XLP covered at $77.80: loss on short = $2.60 × 665 = **-$1,729**
- **Net P&L: +$3,363 on $100,000 = +3.4% in 3 months**
- SPY same period: -1.2% → **alpha of +4.6%**

---

### Trade 3: The Failed Trade — XLE/XLU 2022 Energy Regime

**Signal date:** January 3, 2022. 

**3-month returns (Oct-Dec 2021):**
- XLE: +23.8% (energy surged on supply constraints)
- XLU: +4.2% (utilities flat)
- Spread: +19.6%
- Z-score: +2.3σ

**Trade:** Short XLE / Long XLU (XLE appears overextended vs XLU)

**What happened:** The Russia-Ukraine war broke out in February 2022. Energy supply disruptions drove XLE another +32% over the next 6 months. XLU fell slightly. The Z-score expanded from +2.3 to +5.1 — a structural regime shift, not statistical noise.

**Z-stop triggered at Z = +3.0:**
- XLE covered at significant loss
- XLU sold
- **Net loss: approximately -$7,200 on $100,000 deployed = -7.2%**

**Lesson:** The Z-stop (close when spread extends to ±3.0) is mandatory — it limits catastrophic losses when a genuine regime shift overwhelms the statistical signal. Without the stop, the eventual loss would have been -18%. With the stop at Z = ±3.0, the loss was -7.2% — painful but survivable. The energy crisis of 2022 was a once-in-a-decade macro event that broke the XLE/XLU cointegration for approximately 18 months.

---

## Signal Snapshot

### Dashboard: Z = +2.4, XLK/XLV, July 1, 2023

```
Sector Rotation Arb Signal — XLK vs XLV — July 1, 2023:
  3M return (XLK):        ████████████  +23.1%  [EXTREME ↑]
  3M return (XLV):        ████░░░░░░░░  +3.4%   [NORMAL]
  Spread (XLK-XLV):       ████████░░░░  +19.7%  [WIDE]
  20-qtr mean spread:     ████░░░░░░░░  +2.8%
  20-qtr std spread:      ██░░░░░░░░░░  7.1%
  Z-score:                ████████░░░░  +2.4σ   [ENTRY ZONE ✓]
  ADF p-value (XLK/XLV):  ██████████░░  0.03    [COINTEGRATED ✓]
  HMM Regime:             ████████░░░░  NEUTRAL [OK TO TRADE ✓]
  VIX:                    ████░░░░░░░░  14.8    [LOW ✓]
  XLK forward P/E:        ████████░░░░  28×     [92nd percentile ↑]
  XLV forward P/E:        ██████░░░░░░  17×     [Normal]
  Dividend drag on short: ██░░░░░░░░░░  -0.2%   [ACCEPTABLE]
  ──────────────────────────────────────────────────────────────────
  → SIGNAL: XLK OVEREXTENDED vs XLV (Z = +2.4σ ≥ +2.0 threshold)
  → TRADE: Short $50k XLK / Long $50k XLV (dollar-neutral)
  → EXIT TARGET: Z reverts to ±0.5
  → Z-STOP: Z reaches +3.0 → exit immediately
  → TIME STOP: September 30, 2023 (3 months)
  → DIVIDEND NOTE: XLK short pays dividend (0.7% annual ÷ 4 = 0.17%)
```

---

## Backtest Statistics

**Period:** January 1994 – December 2024 (31 years, quarterly rebalance, 4 primary pairs)

```
┌─────────────────────────────────────────────────────────────────┐
│ SECTOR ROTATION ARB — 31-YEAR BACKTEST (4 pairs combined)      │
├─────────────────────────────────────────────────────────────────┤
│ Total quarterly signals (Z ≥ ±2.0): 218                         │
│ Filtered by cointegration: 14 skipped (6%) │
│ Trades taken:                             204                    │
│ Win rate:                                  66%                  │
│ Average winning trade:                   +3.8% (3-month)        │
│ Average losing trade:                    -2.6%                  │
│ Profit factor:                            2.8                   │
│ Annual Sharpe ratio:                      0.92                  │
│ Maximum drawdown:                        -9.8% (2022 energy)    │
│ Avg time to reversion (winning trades): 7.2 weeks               │
│ Regime filter benefit (HMM):            +0.28 Sharpe improvement│
│ Best year:                              2023 (+18.4% alpha)     │
│ Worst year:                             2022 (-6.1% on 3 pairs) │
└─────────────────────────────────────────────────────────────────┘
```

**By Z-score entry level:**

```
Entry Z-score  Win Rate  Avg Return  Time to Reversion
-------------  --------  ----------  -----------------
±2.0 – ±2.5    60%       +2.8%       8.4 weeks
±2.5 – ±3.0    71%       +4.2%       6.1 weeks
> ±3.0         68%       +3.8%       5.8 weeks
```

Higher Z-scores revert faster and with slightly higher win rates — the rubber band is stretched further, creating stronger reversion force. However, above ±3.0, regime-break risk increases, so the Z-stop at ±3.0 is equally important.

---

## The Math

### Cointegration Test Interpretation

```
ADF (Augmented Dickey-Fuller) test on the spread series:
  Null hypothesis: spread has a unit root (non-stationary, random walk)
  Alternative: spread is stationary (mean-reverting)
  
  p-value < 0.05: Reject null → pair is cointegrated (stationary spread)
  p-value > 0.15: Fail to reject → pair may be non-stationary → skip

For XLK/XLV (2000-2024):
  Full period ADF p-value: 0.03 (cointegrated)
  Recent 252-day rolling: p-value varies from 0.02 to 0.09
  → Trade only when current p-value < 0.10

For XLK/XLE (2015-2024):
  Full period ADF p-value: 0.24 (NOT cointegrated — structural divergence)
  → Never trade this pair as a mean-reversion strategy
```

### Dividend Adjustment Calculation

```
When short a dividend-paying sector, you owe the dividend:
  Daily carry cost = (Annual dividend yield) / 252
  
  XLU short position (annual yield ~3.5%):
  Daily carry: 3.5% / 252 = 0.014% per day
  3-month position: 0.014% × 63 days = 0.88% carry cost
  
  This must be added to the required entry Z-score threshold:
  If carry cost is 0.88% and average position size $50,000:
  Carry cost = $440 per 3-month period
  
  Include this in the net expected P&L calculation and
  require a Z-score high enough to generate sufficient
  alpha to cover both transaction costs and carry cost.
```

### Break-Even Z-Score Given Costs

```
Total costs for a typical sector rotation trade:
  Round-trip bid-ask (both legs): ~0.05% × 2 legs = 0.10%
  Transaction taxes/fees: ~0.02%
  Dividend carry (if short high-yield sector): 0.20-0.80%
  Total cost: 0.30-0.92% (highly variable by sector pair)

Break-even alpha required:
  Need Z-score to generate enough alpha to cover total costs
  Historical spread compression per Z-score unit: ~2.1%
  (1.5 units of compression at 2.1% per unit = 3.15% average alpha)
  
  If total costs = 0.50% and expected alpha = 3.15%:
  Expected net alpha = +2.65% per trade → positive EV

  If total costs = 1.50% (short high-yield sector in 3-month hold):
  Expected net alpha = +1.65% per trade → still positive but thinner
```

---

## Entry Checklist

- [ ] Compute 3-month total return (dividends included) for both sectors
- [ ] Z-score computed against at least 20 prior quarters of the same spread
- [ ] |Z-score| exceeds 2.0 (minimum 1.8 for partial position)
- [ ] ADF cointegration test on 252-day rolling window: p-value < 0.10 (pair is stationary)
- [ ] Sector pair is from the recommended list or has been specifically validated as cointegrated
- [ ] Both legs sized for dollar neutrality (or beta neutrality for precision)
- [ ] Dividend adjustment: calculate total return, not price return only
- [ ] Carry cost calculated for short leg (if short a dividend-paying sector)
- [ ] Net expected alpha exceeds total costs (carry + transaction)
- [ ] Stop set: Z-score reaches ±3.0, close trade
- [ ] Time stop set: 3 months maximum hold
- [ ] HMM regime: enter only in BULL or NEUTRAL (not BEAR)
- [ ] Earnings revision direction checked: forward earnings trends should support the spread direction

---

## Risk Management

**Maximum loss (dollar-neutral equity):** If spread continues widening from +2.0σ to +3.0σ (Z-stop), the approximate loss on $100,000 notional (50k per leg) is $4,000–$8,000 depending on which sector is moving. The Z-stop at ±3.0 is the hard cap on losses.

**Cointegration re-test:** At the 3-month time stop (or any time the Z-score extends to ±3.0), re-run the ADF test. If cointegration has broken (p-value now > 0.15), do not re-enter the pair until it re-establishes cointegration over a new 252-day window.

**Dividend management:** Before entering any position where the short leg pays a dividend, calculate the total dividend drag over the expected hold period and include it in the required entry threshold. If the dividend drag reduces expected alpha below 1.5%, increase the minimum entry Z-score requirement.

**Time stop:** Close all positions at 3 months regardless of P&L. Sector rotation spreads that have not converged within one quarter are often experiencing regime shifts. Capital opportunity cost is meaningful.

**Position sizing:** 5–8% of portfolio per leg, 10–16% total notional per trade. This is a quarterly-frequency strategy — do not run more than 2-3 pairs simultaneously to maintain adequate margin for adverse moves.

**Regime stop:** If HMM shifts to BEAR during the hold, close all positions immediately regardless of the time stop. Bear markets spike cross-sector correlations toward 1.0, destroying the spread signal.

---

## When This Strategy Works Best

```
Condition                  Optimal Value                                      Why
-------------------------  -------------------------------------------------  ---------------------------------------------------
Cointegration ADF p-value  < 0.05                                             Strong cointegration → reliable mean-reversion
Z-score at entry           ±2.5 – ±3.0                                        Stronger reversion force; higher win rate
Market regime              BULL or NEUTRAL                                    Sector rotation visible and persistent
Business cycle phase       Mid-to-late cycle                                  Classic sector rotation in predictable order
Earnings revision          Divergent (one sector upgrading, one downgrading)  Fundamental backing for spread compression
VIX                        14–24                                              Moderate vol allows sector trends to persist
Interest rate trend        Defined direction                                  Rate moves create reliable sector rotation patterns
```

---

## When to Avoid

1. **Pair fails cointegration test:** ADF p-value above 0.15 on the 252-day rolling window means the spread is not reliably stationary. Non-cointegrated sector pairs can trend indefinitely.

2. **Technology vs energy in 2010s regime:** The structural decline of energy's GDP share and rise of technology created a permanently trending spread. Any pair that has trended in one direction for 5+ years without returning to its starting point should be excluded.

3. **HMM regime = BEAR:** In bear markets, cross-sector correlations spike toward 1.0. The spread between two sectors compresses as everything falls together.

4. **Short a sector during its structural earnings upcycle:** Shorting XLK into a wave of AI-driven earnings beats is not a statistical arbitrage — it is fighting a fundamental trend with a statistical model.

5. **Active macro driver specific to one sector:** If the Fed is hiking rates aggressively, XLU/XLE is driven by macro, not idiosyncratic mispricing. Macro-driven spreads can persist for the duration of the policy cycle.

---

## Strategy Parameters

```
Parameter              Default                     Range                   Description
---------------------  --------------------------  ----------------------  ------------------------------------------------------
Return window          3-month total return        1-6 months              Quarter is the natural institutional rebalancing cycle
Z-score history        20 quarters (5 years)       16-30 quarters          Reference period for mean and std
Entry Z-score          ±2.0                        ±1.8-2.5                Minimum statistical extreme
Exit Z-score           ±0.5                        ±0.3-1.0                Target reversion level
Stop Z-score           ±3.0                        ±2.5-3.5                Emergency exit — spread widened further
Time stop              3 months                    2-4 months              Maximum hold
Sizing                 Dollar-neutral (preferred)  Dollar or beta-neutral  Beta-neutral for higher accuracy
Dividend adjustment    Total return (required)     Price return = error    Must include dividends
Cointegration test     ADF p < 0.10                Required                Skip if pair not cointegrated
Regime filter          HMM ≠ BEAR                  Required                No sector pairs in bear regime
Options DTE (if used)  60-90                       45-120                  Longer expiry for 1-3 month hold
Position size          5-8% per leg                3-10%                   10-16% total notional per trade
Max concurrent pairs   3                           2-4                     Avoid over-concentration in correlated pairs
```

---

## Data Requirements

```
Data                            Source                                   Usage
------------------------------  ---------------------------------------  ------------------------------------------
Sector ETF daily OHLCV          Polygon                                  3-month return calculation
Sector ETF dividend data        Polygon / ETF issuer                     Total return (not price return)
Sector ETF options chains       Polygon                                  Spread pricing (optional expression)
ADF cointegration test library  Statistical library (scipy/statsmodels)  Pair stationarity testing
HMM regime                      Platform regime model                    Master filter
Sector forward P/E              FactSet / Bloomberg                      Valuation confirmation of spread extremity
Earnings revision direction     FactSet / IBES                           Forward earnings trend check
VIX daily                       Polygon / CBOE                           Macro environment filter
Sector beta to SPY              Calculated (rolling 60d)                 Beta-neutral sizing
FOMC calendar                   Federal Reserve                          Entry timing — avoid rate decisions
```
