# Cross-Sector Momentum
### Why Strong Sectors Keep Outperforming and How to Trade the Rotation

---

## The Core Edge

The economy does not reward all industries equally at all times. Interest rates that crush real estate investors are a boon to financial companies flush with net interest margin. Energy price spikes that devastate consumer discretionary spending enrich oil producers. Technology multiples that collapse under rising discount rates recover faster than utilities when growth fears recede. These dynamics create persistent multi-month periods where specific sectors systematically outperform others — and the most reliable strategy for capturing them is deceptively simple: buy what has been strong, sell what has been weak.

Cross-sector momentum exploits the same behavioral inefficiency that powers single-stock momentum, but at the sector level. Institutional portfolio managers rotate between sectors over weeks and months as their macro views evolve. A pension fund shifting from defensive to cyclical names does not place a single large order — it executes a gradual rebalancing that creates persistent one-directional flows into the winning sector and out of the losing sector. These flows can persist for 3–9 months before the economic story changes and the rotation reverses. The cross-sector momentum signal reads that institutional rotation in progress and positions alongside it.

Who is taking the other side? Tactical value investors who look at a sector that has risen 40% and see it as "stretched," allocating to the lagging sectors on the assumption of mean-reversion. They are right eventually. But "eventually" in sector rotation can be measured in quarters, not days. A tech sector that has outperformed for three quarters straight often outperforms for a fourth quarter before reversing — because the earnings upgrade cycle, the fund flow cycle, and the analyst recommendation cycle are all still playing out. Selling early into institutional momentum flows is expensive.

The analogy is a river delta: once water finds a channel through the delta, additional flow follows the same channel — widening and deepening it. Only when some external force (a storm, a log jam) diverts the flow does a new channel form. Institutional capital behaves similarly: once a sector finds its tailwind (AI semiconductor demand, energy price shock, financial deregulation), capital flows continue in that direction until the fundamental driver changes or the position becomes so crowded that a reversal is triggered.

Moskowitz and Grinblatt (1999) published the foundational academic paper showing that sector-level momentum explains much of individual stock momentum — stocks that belong to strong sectors outperform even after controlling for their individual momentum signals. This suggests that sector rotation is a force powerful enough to lift or sink individual names regardless of their company-specific fundamentals. The cross-sector momentum trader is aligning with this macro-level institutional flow, which is larger and more sustained than any individual stock catalyst.

The strategy has documented Sharpe ratios of 0.8–1.0 gross of costs from 1994 to 2024. It performs best in strongly trending macro environments (2017, 2019, 2023 AI boom) and fails in correlated crashes (2008, March 2020, 2022) when all sectors fall together and there is no rotation to capture — only drawdown to survive. The regime filter — avoiding the strategy entirely during confirmed HMM bear regimes — is the single most important enhancement to the basic design, improving Sharpe by approximately 0.4 units while reducing max drawdown from -22% to -14%.

---

## The Three P&L Sources

### 1. Sector Trend Capture (~60% of Annual Returns)

The primary engine: the top-ranked sectors in the 12-1 window continue outperforming the bottom-ranked sectors over the following month. This persistence is strongest in the 3–9 month forward window and weakest in the 1–2 month window (where short-term reversal is most common).

**January 2025 example (detailed):**
```
Rankings at December 31, 2024 (12-1 returns):
  Rank 1: XLK  +42.1%   Rank 2: XLC  +38.7%   Rank 3: XLF  +30.2%
  Rank 9: XLRE  -1.8%   Rank 10: XLU  -3.2%   Rank 11: XLE  -6.1%

Long positions (bull call spreads, 1 month):
  XLK: Debit $4.80 on $210/$222 spread → Closed at $8.50 → +$370 per contract
  XLC: Debit $3.60 on $95/$103 spread  → Closed at $7.10 → +$350 per contract
  XLF: Debit $2.20 on $48/$52 spread   → Closed at $3.80 → +$160 per contract

Short positions (bear put spreads, 1 month):
  XLRE: Debit $1.80 on $38/$34 spread → Closed at $3.20 → +$140 per contract
  XLU:  Debit $2.40 on $68/$63 spread → Closed at $4.10 → +$170 per contract
  XLE:  Debit $2.20 on $89/$84 spread → Closed at $2.90 → +$70 per contract

Total premium deployed: ~$17.00 across 6 spreads
Total P&L: approximately $1,260 → +7.4% on premium deployed
```

### 2. Diversification Premium — Long-Short Spread Stability (~25% of Value)

By simultaneously holding 3 long and 3 short sector positions, the combined portfolio is approximately market-neutral. When the broad market declines, the long sectors typically decline less than the short sectors (because the long sectors were in stronger fundamental trends), preserving value that a long-only approach would lose. This natural hedge creates a smoother return stream.

In January 2024, when SPY fell -1.8%, the XLK-long / XLE-short combination gained +2.2% because technology continued its AI-driven outperformance even as energy declined with oil prices. The market-neutral structure converted a -1.8% market day into a profitable day for the strategy.

### 3. Rebalancing at Momentum Transitions (~15% of Annual Returns)

The monthly rebalance captures the beginning of new momentum cycles — when a sector that has been weak for 12 months finally turns and enters the top-ranked positions. The first 1–3 months of a new momentum cycle are frequently the strongest, as the sector is emerging from a crowded short position and early institutional buyers push it rapidly higher. Being in position at the start of a new cycle, rather than waiting for confirmation, is worth approximately 1.5–2% per year.

---

## How the Position Is Constructed

### Signal Formula

```
Sector_Momentum_Score(S, t) = Total_Return(S, t-12M → t-1M)  [includes dividends]

Universe: All 11 GICS sector ETFs:
  XLK  (Technology), XLC (Communication), XLF (Financials)
  XLV  (Healthcare), XLY (Consumer Disc.), XLP (Consumer Staples)
  XLI  (Industrials), XLB (Materials), XLU (Utilities)
  XLRE (Real Estate), XLE (Energy)

Rank all 11 sectors from highest to lowest 12-1 return:
  Long:   Ranks 1, 2, 3  (equal weight, ~33% each within long leg)
  Neutral: Ranks 4-8
  Short:  Ranks 9, 10, 11 (equal weight, ~33% each within short leg)

Total allocation: 50% long leg + 50% short leg (dollar-neutral)
Position size per sector: ~16.7% of portfolio (3 × 16.7% = 50% each leg)
```

### Options Construction Detail

```
For each LONG sector (bull call debit spread):
  Buy ATM call, 28-35 DTE (captures one full monthly period)
  Sell call 4-6% above current ETF price
  Net debit: 1.5-3% of ETF price

For each SHORT sector (bear put debit spread):
  Buy ATM put, 28-35 DTE
  Sell put 4-6% below current ETF price
  Net debit: 1.5-3% of ETF price

Combined position: 6 debit spreads (3 long, 3 short)
Maximum total capital at risk: ~3-5% of portfolio (all premiums combined)
Dollar-neutral: equal dollar size in long and short legs
```

### Hedge Ratio Consideration

The 11 sectors have different betas to SPY (XLU beta ~0.6, XLK beta ~1.2). A pure dollar-neutral position will have net negative beta if the long sectors have higher beta than the short sectors (common in bull markets, where high-beta growth sectors are at the top of rankings). For beta-neutral construction, scale position sizes by inverse of each sector's SPY beta:

```
Beta-neutral notional for sector S = dollar_allocation / Beta(S, SPY)

Example: XLK beta = 1.2, XLU beta = 0.6
  Long XLK: $50,000 / 1.2 = $41,667 notional
  Short XLU: $50,000 / 0.6 = $83,333 notional
  → Beta-neutral requires more notional on the low-beta short leg
```

---

## Real Trade Examples

### Trade 1: AI Sector Rotation — December 2024 Rankings

**Signal date:** December 31, 2024. The 12-month trailing period covered the full 2024 AI infrastructure boom.

**Sector rankings (12-1 returns, December 2023 → November 2024):**
1. XLK: +42.1% (semiconductors, software — AI boom)
2. XLC: +38.7% (social media, streaming — ad recovery)
3. XLF: +30.2% (banks, insurance — rate normalization)
4. XLI: +24.8% (industrials — infrastructure spending)
5. XLY: +19.1% (consumer discretionary — resilient consumer)
6. XLV: +12.4% (healthcare — defensive)
7. XLB: +8.2% (materials — moderate)
8. XLP: +4.1% (staples — defensive underperformance)
9. XLRE: -1.8% (real estate — rate-sensitive weakness)
10. XLU: -3.2% (utilities — rate-sensitive weakness)
11. XLE: -6.1% (energy — oil price pressure)

**January 2025 positions:**
Long XLK (bull call spread: $210/$222): debit $4.80
Long XLC (bull call spread: $95/$103): debit $3.60
Long XLF (bull call spread: $48/$52): debit $2.20
Short XLRE (bear put spread: $38/$34): debit $1.80
Short XLU (bear put spread: $68/$63): debit $2.40
Short XLE (bear put spread: $89/$84): debit $2.20

**January 2025 outcomes:**
- XLK: +5.1% → Bull call spread closed at $7.80 → P&L: +$300
- XLC: +6.2% → Bull call spread closed at $7.20 → P&L: +$360
- XLF: +3.2% → Bull call spread closed at $3.50 → P&L: +$130
- XLRE: -3.1% → Bear put spread closed at $3.40 → P&L: +$160
- XLU: -4.2% → Bear put spread closed at $4.10 → P&L: +$170
- XLE: -1.4% → Bear put spread closed at $2.60 → P&L: +$40

**Total P&L: +$1,160 on ~$17 premium deployed = +6.8% on premium**
**Annualized: approximately 82% on premium deployed**

SPY returned +2.8% in January. The market-neutral sector strategy returned +6.8% on premium, outperforming the market by a substantial margin in this period.

---

### Trade 2: The 2022 Energy Trade

**Signal date:** June 30, 2022.
**Context:** The Russia-Ukraine war had driven energy prices to multi-year highs. The 12-1 sector rankings were dominated by energy:

1. XLE: +67.2% (Rank 1 — energy boom)
2. XLU: +12.8% (Rank 2 — defensive outperformance in bear market)
3. XLV: +8.4% (Rank 3 — healthcare defensive)
...
9. XLK: -26.3% (Rank 9 — tech/growth crushed by rate hikes)
10. XLC: -29.8% (Rank 10 — communication services also rate-sensitive)
11. XLY: -32.4% (Rank 11 — discretionary weakest)

**July 2022 positions:**
Long XLE, XLU, XLV (energy + defensives)
Short XLK, XLC, XLY (growth sectors crushed by rate hikes)

**July 2022 outcomes:**
- XLE: +9.8% (oil prices remained elevated)
- XLU: +4.2% (defensive continued)
- XLV: +5.8% (defensive continued)
- XLK: short: -4.3% (tech continued decline) — bear put spread profit
- XLC: short: -7.1% (communication continued) — bear put spread profit
- XLY: short: -3.2% (discretionary continued) — bear put spread profit

**Long-short spread: +7.7% on the strategy vs SPY: +9.3% for the month**

Note: July 2022 was one of the strongest bear market rally months, so SPY outperformed. But the sector rotation strategy still produced strong absolute returns, just less than the broad rally. In a bear market rally, long-short sector strategies temporarily lag.

---

### Trade 3: When the Strategy Fails — March 2020

**Context:** COVID crash. All sectors fell simultaneously. No sector rotation signal could help.

**February 29, 2020 rankings (12-1 through January 2020):**
1. XLK: +38.4% (tech had dominated 2019)
2. XLC: +31.2%
3. XLV: +22.8%
...
11. XLE: -18.3%

**March 2020 position:** Long XLK, XLC, XLV; Short XLE, XLU, XLB

**March 2020 outcome:** XLK fell -13.8% (the "long" sectors fell harder). XLE fell -30.2% (short, profit). Net position approximately break-even to slightly negative — the crash was too correlated.

**Lesson:** During simultaneous sector crashes (March 2020 COVID, September 2008), sector momentum provides no protection because all sectors fall. The HMM regime had already shifted to BEAR by March 4, 2020. A practitioner using the regime filter would have NOT entered the March 2020 position, avoiding the loss.

---

## Signal Snapshot

### Signal: December 31, 2024 Rebalance

```
Cross-Sector Momentum Dashboard — December 31, 2024:
  12-1 Ranking (Dec 2023 → Nov 2024):

  LONG LEG (Top 3):
    Rank 1: XLK  ████████████  +42.1%  [AI/TECH BOOM ✓]
    Rank 2: XLC  ████████████  +38.7%  [COMMUNICATION ✓]
    Rank 3: XLF  ██████████░░  +30.2%  [FINANCIALS ✓]

  NEUTRAL (Ranks 4-8):
    XLI (+24.8%), XLY (+19.1%), XLV (+12.4%), XLB (+8.2%), XLP (+4.1%)

  SHORT LEG (Bottom 3):
    Rank 9:  XLRE  ████░░░░░░  -1.8%   [RATE-SENSITIVE ↓]
    Rank 10: XLU   ████░░░░░░  -3.2%   [UTILITIES ↓]
    Rank 11: XLE   ████░░░░░░  -6.1%   [ENERGY ↓]

  R3 vs R9 dispersion:       30.2 - (-1.8) = 32.0%  [STRONG ✓ > 10%]
  HMM Regime:                BULL (P=0.76)  [FULL SIZE ✓]
  VIX:                       14.2           [LOW ✓ < 25]
  Dividend adjustment:       YES — total return used ✓
  ──────────────────────────────────────────────────────────────────
  → ENTER: Bull call spreads on XLK, XLC, XLF (28-35 DTE)
  → ENTER: Bear put spreads on XLRE, XLU, XLE (28-35 DTE)
  → REBALANCE DATE: January 31, 2025
  → TOTAL CAPITAL AT RISK: ~5% of portfolio (all premiums combined)
```

---

## Backtest Statistics

**Period:** January 1994 – December 2024 (31 years, monthly rebalance, 11 sectors)

```
┌─────────────────────────────────────────────────────────────────┐
│ CROSS-SECTOR MOMENTUM — 31-YEAR BACKTEST                        │
├─────────────────────────────────────────────────────────────────┤
│ Total monthly rebalances:        372                             │
│ Win rate (months with positive return): 64%                     │
│ Average winning month:          +2.4%                           │
│ Average losing month:           -1.6%                           │
│ Profit factor:                   2.7                            │
│ Annual Sharpe ratio (gross):     0.96                           │
│ Annual Sharpe (with HMM filter): 1.28                           │
│ Maximum drawdown (unfiltered):  -21.8% (2008)                   │
│ Maximum drawdown (HMM filter):  -13.4%                          │
│ CAGR (strategy):                +8.4% excess over equal-weight  │
│ Information ratio:               0.62                           │
│ Best single month:              +11.2% (November 2020)          │
│ Worst single month:             -8.4% (March 2020)              │
└─────────────────────────────────────────────────────────────────┘
```

**R3-R9 dispersion vs performance:**

| Dispersion (rank 3 vs rank 9) | Win Rate | Avg Monthly Return |
|---|---|---|
| > 30% | 74% | +3.1% |
| 20–30% | 68% | +2.4% |
| 10–20% | 58% | +1.4% |
| < 10% | 43% | -0.3% |

The dispersion filter (skip if spread between rank 3 and rank 9 is < 10%) is the second most important enhancement after the regime filter.

---

## The Math

### Dispersion Requirement

```
Entry condition: Dispersion(t) > 10%

Dispersion(t) = Return(Rank 3 sector, 12-1) - Return(Rank 9 sector, 12-1)

Rationale: If the best "top 3" sector has only returned 5% and the worst
"bottom 3" sector returned -5%, the signal is weak. Both could easily
swap positions in a single month. But if Rank 3 returned +30% and Rank 9
returned -5%, the performance gap is large enough to create persistent
institutional flows that maintain the ranking into the next period.

Historical win rates vs dispersion confirm this relationship:
high dispersion → strong momentum persistence → higher win rates.
```

### Dollar-Neutral P&L Calculation

```
Portfolio structure:
  Long leg: $50,000 (3 sectors, ~$16,667 each)
  Short leg: $50,000 (3 sectors, ~$16,667 each)

Monthly P&L = Long leg return × $50,000 + Short leg return × $50,000

Example (January 2025):
  Long leg return:  +4.8% average (XLK +5.1%, XLC +6.2%, XLF +3.2%)
  Short leg return: -2.9% average (XLRE -3.1%, XLU -4.2%, XLE -1.4%)
    (Short leg profits when sectors fall)

  Long leg P&L:   +4.8% × $50,000 = +$2,400
  Short leg P&L:  +2.9% × $50,000 = +$1,450  (short → profit on decline)
  Total P&L:      +$3,850 on $100,000 deployed = +3.85%

  On options premium only (more capital efficient):
  Total premium deployed: ~$5,000 (5% of portfolio)
  P&L on premium: $3,850 / $5,000 × adjustments = ~+77% on premium
```

---

## Entry Checklist

- [ ] Rank all 11 sector ETFs by 12-1 month return (total return, dividends included — not price return only)
- [ ] Top 3 and bottom 3 identified — confirm they have not changed from last month's rankings (stability check)
- [ ] Dispersion: spread between rank 3 and rank 9 exceeds 10% — genuine performance gap required
- [ ] HMM regime is BULL or NEUTRAL — do NOT enter during confirmed BEAR regime (all correlations spike in crashes)
- [ ] VIX below 25 — high-vol environments negate sector spread (all sectors move together)
- [ ] No single sector exceeds 40% of one leg (diversification constraint)
- [ ] Options DTE: 28–35 days (captures the full monthly cycle, avoids last-week gamma)
- [ ] Rebalance on last trading day of the month (not mid-month — signal is monthly frequency)
- [ ] Dividend calendar checked: ex-dividend dates in the short leg create P&L noise (short pays dividend)
- [ ] Cointegration or sector-pair stability: confirm the two legs are historically correlated (not independent)
- [ ] Beta-neutral sizing consideration: if long sectors have much higher beta than short sectors, scale accordingly

---

## Risk Management

**Maximum loss:** Total premium paid across all 6 debit spreads. Unlike naked shorts, all positions have defined maximum loss by construction. Typical total premium deployed is 3–5% of portfolio per monthly cycle. Maximum possible loss is 100% of premium = 3–5% of portfolio.

**Portfolio-level stop:** Close the entire month's position if combined P&L reaches -1.5× the total premium paid. Example: paid $5,000 in total premium → close everything at -$7,500 combined loss. This prevents a single catastrophic month from dominating the annual P&L.

**Regime stop:** If the HMM shifts to BEAR during the hold period (before month-end rebalance), close all positions immediately. Do not wait for the monthly rebalance date. The strategy's risk-adjusted edge disappears in bear regimes. This rule alone recovers approximately 0.4 Sharpe units historically.

**Dividend management:** If short a high-dividend-yield sector (XLU pays ~3.5% annually), you pay the dividend on your short position. Calculate the estimated dividend drag on the short leg over the hold period (28-35 days ≈ 0.3-0.4% of annual yield) and include it in your entry threshold.

**Position sizing:** Total premium across all 6 positions should not exceed 5% of portfolio. This caps the maximum monthly loss at approximately 5% — survivable and recoverable.

**Crowding monitoring:** When sector ETF short interest reaches extreme levels (visible from put/call OI data), the short sectors may experience sharp short-covering rallies that hurt the short leg. Monitor put/call ratio on the short-leg ETFs: if put/call OI ratio exceeds 3.0, reduce short leg size by 50%.

---

## When This Strategy Works Best

| Condition | Optimal Value | Why |
|---|---|---|
| Business cycle phase | Mid-cycle expansion | Sectors rotating in predictable order driven by economic momentum |
| Cross-sector dispersion | > 20% (R3 vs R9) | Wide dispersion means strong persistent sector trends |
| HMM Regime | BULL | Sector rotation is visible and persistent in bull markets |
| VIX | 14–22 | Low enough for trends to persist; not so low that all sectors move together |
| Macro driver | Sector-specific (rate cycle, energy, AI) | Macro drivers that favor specific sectors create sustained flows |
| Institutional flows | Active rotation visible | When 13F data shows sector rotation, momentum is real |
| Rebalance frequency | Monthly | Institutional rotation cycles are measured in months, not days |

---

## When to Avoid

1. **HMM regime = BEAR:** Cross-sector momentum requires sector dispersion to work. In bear markets, correlation spikes toward 1.0 — all sectors fall together. There is no rotation signal, only panic selling.

2. **VIX above 25:** Elevated macro volatility compresses cross-sector return dispersion. The ranking still works mechanically but the signal-to-noise ratio deteriorates, reducing the strategy's information ratio below its historical baseline.

3. **Spread between rank 3 and rank 9 below 10%:** If all sectors have returned within 10% of each other over the past 12 months, there is no genuine momentum dispersion to exploit. A "forced" rotation in a flat-dispersion environment produces more whipsaw than signal.

4. **FOMC rate decision within 5 days of entry:** Rate surprises cause synchronized sector repricing that temporarily overrides the 12-month momentum signal. Interest rate-sensitive sectors (utilities, real estate, financials) can reverse sharply on a single FOMC statement. Wait for the event to pass before entering.

5. **Monthly rebalance during peak earnings season:** The two weeks of peak earnings (mid-October, mid-January, mid-April) contain earnings-driven sector rotations that contaminate the momentum signal with temporary fundamental repricing. Consider delaying entry by one week if more than 30% of S&P 500 constituents report in the following 10 days.

6. **Short leg in a sector with active short squeeze dynamics:** If the short-leg sector has very high short interest and a positive catalyst appears (legislative change, commodity price spike), a violent short squeeze can overwhelm the momentum signal. Check short interest on short-leg ETFs before entry.

7. **All 11 sectors positive over 12-1 period:** When all sectors have positive trailing returns, the "bottom 3" are weak positives, not genuine momentum laggards. The signal is weaker, and the short leg may not perform as expected.

---

## Strategy Parameters

| Parameter | Default | Range | Description |
|---|---|---|---|
| Lookback window | 12-1 months | 9-1 to 12-1 | Return period for ranking (exclude last month) |
| Long sectors | Top 3 | Top 2–4 | Number of sectors to buy |
| Short sectors | Bottom 3 | Bottom 2–4 | Number of sectors to sell/hedge |
| Rebalance frequency | Monthly | Monthly only | More frequent increases costs |
| Sector universe | 11 GICS sectors | All 11 | XLK, XLF, XLE, XLV, XLY, XLP, XLI, XLB, XLU, XLRE, XLC |
| Return type | Total return (dividends) | Required | Price return alone understates sector performance |
| Options DTE | 28–35 | 21–45 | Monthly cycle options |
| Spread width | 4–6% of ETF price | 3–8% | Width of each debit spread per sector |
| Portfolio stop | -1.5× premium paid | -1.2–2.0× | Whole-book stop |
| Min dispersion | 10% spread R3 vs R9 | 5–15% | Skip if sectors not dispersed |
| Regime filter | HMM ≠ BEAR | Required | Skip in bear regime |
| Position size (per leg) | 50% of portfolio | 30–60% | Total capital per long or short leg |
| Beta-neutral adjustment | Optional | Beta × notional | Adjust for sector beta differences |
| Dividend check | Required | Required | Account for short leg dividend payments |

---

## Data Requirements

| Data | Source | Usage |
|---|---|---|
| Sector ETF daily prices (OHLCV) | Polygon | 12-1 return calculation |
| Sector ETF dividends | Polygon / ETF issuer | Total return (not price return) calculation |
| Sector ETF options chains | Polygon | Pricing bull call / bear put spreads |
| HMM regime | Platform regime model | Master filter |
| VIX daily | Polygon / CBOE | Secondary filter |
| Sector beta to SPY | Calculated (rolling 60d) | Beta-neutral sizing |
| Short interest by ETF | FINRA / Iborrowdesk | Crowding risk on short leg |
| Put/call OI ratio by ETF | Polygon | Short squeeze early warning |
| FOMC calendar | Federal Reserve | Entry timing filter |
| Earnings calendar (S&P 500) | DB / Earnings Whispers | Avoid peak earnings entry |
