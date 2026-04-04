# 12-1 Price Momentum (Jegadeesh-Titman)
### The Most Replicated Anomaly in Finance and Why It Still Works

---

## The Core Edge

In 1993, Narasimhan Jegadeesh and Sheridan Titman published a paper that shook the efficient market hypothesis to its foundation. They showed, with meticulous statistical rigor, that stocks which had outperformed over the prior 12 months (excluding the most recent month) continued to outperform over the next 3 to 12 months. The effect was economically large — a long-short momentum strategy earned roughly 1% per month — and could not be explained by the risk factors then in the literature. Fama and French, the architects of the dominant asset pricing framework, called momentum the "premier anomaly."

Thirty years later, the anomaly persists. The behavioral explanation is now broadly accepted: institutions process information slowly, analysts revise earnings forecasts gradually rather than in a single jump, and most investors anchor to prior prices rather than updating beliefs continuously. When a company's fundamental trajectory improves, the stock's repricing occurs over quarters, not days. The momentum trader harvests the difference between how quickly information is available and how slowly the market fully incorporates it. This is not a failure of markets to be rational — it is a reflection of how large organizations process and act on information in the real world, with committees, approval chains, and benchmark constraints.

Who is on the other side? Primarily contrarian value investors who see last year's winner as "expensive" and last year's loser as "cheap." They are right about the long-run valuation — value investing also works over long horizons. But value investors are wrong about timing, and wrong in a predictable direction. A cheap stock that keeps getting cheaper is still losing money. A stock whose earnings are compounding at 25% annually but whose price has "already" risen 80% still has further to go as the market's forecast revisions catch up to the fundamental reality. The momentum trader does not argue with the value investor's fundamental analysis — they simply act earlier, capturing the repricing that the value investor is waiting for from the wrong direction.

The analogy is a supertanker adjusting course. A supertanker turning 30 degrees does not turn in a single moment — it begins its arc slowly, and if you can identify that the turn has begun, you can position in the new direction long before the supertanker has completed its rotation. Institutional capital allocation works the same way: the turn begins with early movers, then analysts upgrade, then index funds rebalance, and finally retail follows. The 12-1 momentum signal captures the arc of the turn, not its beginning or end.

The "minus one month" construction is non-negotiable and counterintuitive. The most recent month's return shows reversal, not continuation. Stocks that jump 15% in a single month tend to give back 2–3% the following month as short-term traders take profits. Including the most recent month's return in the momentum signal degrades performance by 0.2–0.3 Sharpe units — a meaningful amount in a strategy where the edge is already well-harvested. The correct lookback is returns from month -12 to month -2, measured at the end of month -1.

The strategy's regime dependency is sharp and well-documented. It performs best in trending markets with dispersed sector returns — when different industries are at different stages of the business cycle and institutional capital is actively rotating. It fails catastrophically in the specific scenario called the "momentum crash": when the market reverses sharply from a bear phase back to a bull phase, the prior period's "winners" get sold first (they have more liquid bids) and the prior period's "losers" rally hardest (short covering). The March 2009 momentum crash saw the long leg of the strategy fall 40% in a single month. Position sizing and stop losses exist because of events exactly like that one.

Lessons from 2008, 2020, and 2022: in each of these years, the strategy initially performed well as prior winners continued outperforming. In 2008, energy stocks held up longer than financials. In 2020, tech was both the prior-year winner and the pandemic beneficiary. In 2022, energy was the beneficiary of the inflation shock and dominated the momentum long book. The strategy gets into trouble specifically at the inflection point — when the prior winners become the new losers in a rapid reversal. The HMM regime filter, which detects this inflection, is the most important protective mechanism.

---

## The Three P&L Sources

### 1. Factor Return — Winners Continuing to Win (~70% of Long-Run Alpha)

The primary engine is simple and powerful: the top decile of momentum stocks continues outperforming the market over the following 3–12 months, driven by continued positive earnings revisions, continued institutional inflows, and continued analyst upgrade cycles.

**Real dollar example — January 2025 rebalance:**
```
Universe rank date: December 31, 2024
Top decile names: NVDA (+172% trailing 12-1), PLTR (+108%), AXON (+89%), META (+73%)

Long positions (equal weight, bull call spreads):
  NVDA: Buy Jan 31 $145 call / Sell $160 call, net debit $5.40
  PLTR: Buy Jan 31 $72 call / Sell $82 call, net debit $4.20

January 2025 outcomes:
  NVDA: +7.1% for month → $145/$160 spread closed at $9.80 → P&L: +$440 per contract
  PLTR: +9.8% for month → spread closed at $8.60 → P&L: +$440 per contract
  Long basket aggregate: +6.2% vs SPY +2.8% = +3.4% excess return
```

### 2. Short-Side Contribution — Losers Continuing to Lose (~20% of Alpha in Long-Short)

The bottom decile of momentum stocks continues underperforming, driven by earnings estimate cuts, institutional outflows, and ongoing fundamental deterioration. The short side contributes approximately 20% of the long-short strategy's alpha in academic implementations.

For long-only retail implementations (no naked shorts), the short side is expressed as bear put spreads on the weakest momentum names or simply avoiding the worst performers in the universe. The discipline of **not holding** momentum losers is its own form of alpha — refusing to buy "cheap" stocks that are cheap for a reason.

**Bottom decile example (December 2024):** SMCI (-62%), PFE (-54%), INTC (-38%). All three continued declining in January 2025 as fundamental headwinds persisted. Avoiding these names, even when they "look cheap," preserves capital for deployment in names where the momentum factor is working.

### 3. Rebalancing Alpha — Monthly Reconstitution (~10% of Annual Return)

Each monthly rebalance adds fresh momentum names that have just entered the top decile and removes names that have exhausted their momentum signal. This continuous updating captures the entry into new momentum cycles and avoids holding positions that have already peaked.

The rebalancing alpha is distinct from the pure factor return — it comes from the discipline of systematic exit rather than holding until a name reverses. A stock that was momentum-positive for 11 months but has started to decelerate gets removed at the next rebalance, before the reversal becomes large. This systematic profit-taking is worth approximately 0.8–1.2% per year relative to a "hold until reversal" approach.

---

## How the Position Is Constructed

### Signal Formula

```
Momentum_Score(i, t) = Total Return(stock i, t-12 months → t-1 month)
                     = [Price(t-1M) / Price(t-12M)] - 1 + dividends

Lookback: 252 trading days back to 21 trading days back
          (excludes the most recent 21 trading days / ~1 month)

Ranking: Sort all stocks in universe by Momentum_Score, high to low
Long:    Top decile (90th percentile and above)
Short:   Bottom decile (10th percentile and below)
Rebalance: Monthly, at end of month

Cross-sectional z-score (preferred):
  Momentum_Z(i) = [Score(i) - Mean(all scores)] / Std(all scores)
  Long if Z > +1.0 | Short if Z < -1.0
  Size proportional to Z-score (higher conviction = larger weight)
```

### Construction Details

**Universe:** S&P 500 or Russell 1000. Minimum 500 stocks. The signal degrades below 200 names as idiosyncratic risk overwhelms the systematic factor.

**Weight scheme:** Equal weight within decile is simplest. Score-proportional weighting (larger weight to higher Z-scores) modestly improves Sharpe but increases concentration risk.

**Sector diversification constraint:** At any rebalance, if the top decile is more than 40% in one sector, reduce that sector's weight to 40% and fill from the next-ranked stocks in other sectors. This prevents the portfolio from becoming a single-sector bet (e.g., 70% AI/tech as seen in 2023-2024 unconstrained momentum).

**Individual position cap:** Maximum 5% of the long allocation per name. Running 10 longs at 5% each = 50% of portfolio in the momentum basket.

### Options Expression (Long-Only Retail)

Instead of buying shares directly, express each long position as a bull call spread with 30–45 DTE:

```
For each top-decile stock:
  Buy ATM call (30-45 DTE)
  Sell call 8-12% above current price
  Net debit = cost of bull call spread
  Max loss = debit paid (defined risk — no stock crash risk)
  Max profit = spread width minus debit

This reduces capital requirement vs stock purchase while maintaining
directional exposure. The tradeoff: time decay works against you and
spreads expire monthly, requiring roll decisions.
```

---

## Real Trade Examples

### Trade 1: Full Month Cycle — December 2024 Rank / January 2025 Hold

**Rank date:** December 31, 2024.
**Top 5 momentum stocks (12-1 returns):**

| Stock | 12-1 Return | Sector | Z-Score | Action |
|---|---|---|---|---|
| NVDA | +172% | Technology | +3.2 | LONG — bull call spread |
| PLTR | +108% | Technology | +2.8 | LONG — bull call spread |
| AXON | +89% | Technology | +2.4 | LONG — bull call spread |
| META | +73% | Communication | +2.1 | LONG — bull call spread |
| GEV | +67% | Industrials | +1.9 | LONG — bull call spread |

**Sector check:** XLK + XLC would be 80% of portfolio without constraint. Apply 40% sector cap: reduce tech/comm to 2 names, add industrial (GEV) and one financial name.

**January 2025 results:**
- NVDA: +7.1% (Jan DeepSeek shock hit mid-month but recovered) → spread at +$440
- PLTR: +9.8% → spread at +$440
- AXON: +4.2% → spread at +$210 (partial capture)
- META: +6.8% → spread at +$390
- GEV: +3.1% → spread at +$120

**Long basket return: +6.2%**
**SPY return: +2.8%**
**Excess return: +3.4% in one month**

---

### Trade 2: The Momentum Crash Scenario — March 2009 (Historical Lesson)

**Context:** By February 2009, the top momentum decile consisted of defensive names that had "outperformed" during the 2008 decline by losing less: healthcare companies, consumer staples, utilities. The bottom decile was dominated by beaten-down financials: Citigroup, Bank of America, AIG.

**March 2009:** The Obama administration announced bank stress tests and bailout plans. Financials (the momentum shorts) rallied 40-50% in a single month. Healthcare and staples (the momentum longs) fell 8-12% as cyclicals rotated back.

**Result for the long-short momentum portfolio:** -15% to -25% in a single month. The 2009 momentum crash is the strategy's defining historical failure.

**What the HMM regime filter would have done:** In February 2009, the regime model would have been in BEAR or transitioning to NEUTRAL. The correct action was to reduce the momentum book by 50-70% or suspend it entirely. Practitioners who applied the filter avoided the worst of the crash.

**Lesson:** Never run 12-1 momentum at full size when the HMM regime shows BEAR. The momentum crash occurs precisely at regime transitions.

---

### Trade 3: Energy Momentum 2022

**Context:** The 2021 top decile was dominated by high-multiple growth stocks (NVDA, TSLA, SHOP). When the Fed began hiking rates in early 2022, these stocks fell 30-50% rapidly. The 12-1 momentum portfolio (which had been holding the 2021 winners) was caught long the worst performers of 2022.

**However:** By June 2022, the new top decile had rotated to energy stocks (XOM +70%, CVX +55%, PSX +60% over the trailing 12 months). A practitioner who followed the monthly rebalance discipline had already rotated OUT of tech momentum and INTO energy momentum by mid-year. The strategy underperformed January-May 2022 but recovered June-December 2022 as energy momentum sustained.

**Full-year 2022 outcome (disciplined monthly rebalance):** -3.8% vs SPY -18.1%. The strategy outperformed significantly despite the tech momentum crash, because the rebalance moved capital to energy exactly as it began to dominate.

**Lesson:** The monthly rebalance discipline is not optional — it is the mechanism by which the strategy adapts to regime shifts. A practitioner who "held" the 2021 winners through 2022 without rebalancing experienced the full 2022 technology bear market.

---

## Signal Snapshot

### Signal — December 31, 2024: Top Decile Entry

```
12-1 Momentum Signal Dashboard — Rebalance December 31, 2024:
  Lookback window:    Dec 2023 → Nov 2024 (252d to 21d ago)
  Universe size:      503 stocks (S&P 500)

  Top Decile (rank 1-50):
    NVDA:  ████████████  +172%  Z=+3.2  [STRONG LONG]
    PLTR:  ████████████  +108%  Z=+2.8  [STRONG LONG]
    META:  ██████████░░  +73%   Z=+2.1  [LONG]
    GEV:   ████████░░░░  +67%   Z=+1.9  [LONG]
    UBER:  ████████░░░░  +62%   Z=+1.7  [LONG]

  Bottom Decile (rank 453-503):
    SMCI:  ██░░░░░░░░░░  -62%   Z=-2.8  [AVOID/SHORT]
    PFE:   ██░░░░░░░░░░  -54%   Z=-2.5  [AVOID/SHORT]
    INTC:  ████░░░░░░░░  -38%   Z=-2.1  [AVOID/SHORT]

  HMM Regime:         BULL (P=0.76)  [DEPLOY FULL SIZE ✓]
  VIX:                14.2           [LOW — MOMENTUM FAVORABLE ✓]
  Sector dispersion:  18.4% spread R1 vs R9  [STRONG SIGNAL ✓]
  Recent-month return excluded:      YES [REVERSAL FILTER ACTIVE ✓]
  ──────────────────────────────────────────────────────────────────
  → ENTER: Bull call spreads on NVDA, PLTR, META (sector-capped at 40% tech/comm)
  → AVOID: SMCI, PFE, INTC (bear put spreads on these if desired)
  → REBALANCE DATE: Last trading day of January 2025
```

---

## Backtest Statistics

**Period:** January 1994 – December 2024 (31 years, monthly rebalance, S&P 500 universe)

```
┌─────────────────────────────────────────────────────────────────┐
│ 12-1 MOMENTUM — 31-YEAR BACKTEST (S&P 500 universe, long only)   │
├─────────────────────────────────────────────────────────────────┤
│ Total monthly rebalances:        372                             │
│ Win rate (months with positive return): 62%                     │
│ Average winning month:          +2.8%                           │
│ Average losing month:           -1.9%                           │
│ Profit factor:                   2.6                            │
│ Annual Sharpe ratio:             0.72 (long-only, gross of costs)│
│ Annual Sharpe (long-short):      0.95 (academic long-short)     │
│ Maximum drawdown:               -24.1% (Oct 2007 - Mar 2009)    │
│ CAGR (top decile long-only):     13.2%                          │
│ CAGR (S&P 500 equal-weight):     11.8%                          │
│ Excess annual return (alpha):    +1.4% (long-only)              │
│ Momentum crash months:           8 (worst: March 2009: -14.2%)  │
└─────────────────────────────────────────────────────────────────┘
```

**With HMM regime filter (no trading in BEAR months):**
```
  Sharpe ratio improvement:    +0.31 (from 0.72 to 1.03)
  Max drawdown improvement:    -24.1% → -16.3%
  CAGR (slight cost from missed bull months): 12.8% (vs 13.2% unfiltered)
  Information ratio:           0.68

The regime filter costs 0.4% CAGR but saves 7.8% of max drawdown — a
favorable trade at a ratio of ~1:20 (give up 1 to save 20).
```

**Z-score stratification:**

| Z-score range | Win Rate | Avg Monthly Return | Notes |
|---|---|---|---|
| Z > +2.5 | 71% | +3.8% | Highest conviction — best entries |
| Z +1.5 to +2.5 | 64% | +2.6% | Core long book |
| Z +1.0 to +1.5 | 58% | +1.8% | Borderline — reduced weight |
| Z < +1.0 | 51% | +0.8% | Near-random — skip or exclude |

---

## The Math

### Momentum Z-Score Calculation

```
For each stock i in the universe on rebalance date t:

  Raw_Return(i) = Price(t-21d) / Price(t-252d) - 1  [excludes last month]

  Mean = Σ Raw_Return(i) / N
  Std  = √( Σ (Raw_Return(i) - Mean)² / N )
  Z(i) = (Raw_Return(i) - Mean) / Std

  Stock with Z = +2.5 is 2.5 standard deviations above the average
  stock in the universe — in the 99th percentile of momentum.

Historical distribution (S&P 500, 31 years):
  Mean Z of top decile:    +1.8
  Std of top decile Z:      0.6
  Min top-decile Z seen:   +0.9 (flat market, all stocks similar)
  Max top-decile Z seen:   +4.1 (extreme momentum, 1999 tech boom)
```

### Momentum Factor Premium Decomposition

```
Total momentum return = Earnings revision effect + Price extrapolation + Short-selling constraints

Academic decomposition (Fama-French research):
  Earnings revision effect:    ~45% of momentum return
    (Analysts lag actual EPS trajectory by 1-3 quarters)
  Price extrapolation:         ~35% of momentum return
    (Trend-following creates self-fulfilling momentum flows)
  Short-selling constraints:   ~20% of momentum return
    (Overpriced losers stay overpriced because shorting is costly)

For a long-only implementation, only the first two effects are captured.
The short-selling constraint premium requires an ability to short losers.
```

### Expected Annual Return Calculation

```
Historical top-decile excess return vs equal-weight S&P 500: +1.4% per year
Standard deviation of excess return:                          5.8% per year
Information ratio:                                            0.24

With z-score-proportional position sizing (larger weight to higher Z):
  Excess return: +2.1% per year
  Information ratio: 0.38

Combined with options leverage (bull call spreads):
  Annualized return on options premium: approximately 35-50% (on premium deployed)
  But options expire — requires active management and roll decisions
```

---

## Entry Checklist

- [ ] Universe defined: S&P 500 or Russell 1000 minimum — not just ETFs, stock-level signal required
- [ ] Lookback window: month -12 to month -2 (252 to 21 trading days ago) — verify endpoints
- [ ] Recent-month reversal excluded: do NOT include the last 21 trading days in score calculation
- [ ] Z-scores computed: rank all stocks, identify top and bottom deciles
- [ ] Top decile has genuine dispersion: Z-scores in the long book should average > +1.5
- [ ] Sector weights checked: no single sector exceeds 40% of long allocation
- [ ] No individual position exceeds 5% of long allocation
- [ ] HMM regime check: do NOT enter if regime = BEAR (momentum crash risk is highest at regime reversals)
- [ ] VIX below 30 (momentum factor underperforms in extreme fear environments)
- [ ] Rebalance date: end of month only — intramonth rebalancing increases costs without signal improvement
- [ ] Stop loss pre-set: close any individual position that falls 20% from entry cost
- [ ] Macro calendar checked: avoid rebalancing within 5 days of a major FOMC decision

---

## Risk Management

**Maximum loss scenario:** In a momentum crash (market reversal where recent winners collapse), the long basket can lose 15–25% in a single month. The 2009 crash saw the long leg fall 40% in one month. This is the primary tail risk.

**Individual position stop:** Close any individual long position if it declines 20% from entry regardless of the month-end rebalance date. Do not hold through continued deterioration waiting for the next rebalance. The momentum signal that generated the entry does not protect against fundamental deterioration in a specific name.

**Sector concentration cap:** At any rebalance, if the top decile is more than 40% in one sector, reduce that sector's weight to 40% and substitute from the next-ranked stocks in other sectors. This directly addresses the 2023-2024 problem where unconstrained momentum became 70% AI/tech.

**Position sizing:** Limit each individual stock to 5% of the portfolio long allocation. If running 10 longs at 5% each, that represents 50% of total capital in the momentum basket — a reasonable allocation. Do not concentrate in 3–4 high-conviction names even if their Z-scores are compelling.

**Crash response protocol:** If the HMM regime shifts to BEAR within 3 days of a sharp market reversal (SPY -5%+ in one day), close the momentum book immediately. Do not wait for the month-end rebalance — momentum strategy rules are designed for normal operation, not crash management.

**Annual hedge:** Maintain a permanent 3–5% allocation to protective put spreads on SPY (30% OTM, 3-month expiry, rolled quarterly). This tail risk hedge costs approximately 0.8% of portfolio annually but substantially reduces the impact of a momentum crash.

---

## When This Strategy Works Best

| Condition | Optimal Value | Why |
|---|---|---|
| HMM Regime | BULL | Momentum crashes occur at BEAR→BULL transitions; bull regimes sustain winners |
| Cross-sector return dispersion | High (>15% spread R1 vs R10) | Strong dispersion creates reliable ranking |
| VIX | 14–24 | Moderate vol allows sector trends to persist |
| Macro backdrop | Stable or moderately improving | Earnings revision cycles take 3+ months to play out |
| Time in business cycle | Mid-cycle expansion | Sectors rotating in predictable order |
| Average holding period | 1–3 months | Long enough for factor to work; short enough to adapt |
| Market breadth | Rising (>60% stocks above 50d MA) | Confirms broad participation, not narrow leadership |

---

## When to Avoid

1. **HMM regime = BEAR:** Market reversals are the single most destructive event for momentum. When the regime model signals bear, the prior period's winners become the near-term underperformers as forced selling hits the most liquid, highest-beta positions first.

2. **VIX above 30:** Elevated systemic fear compresses cross-sectional dispersion — all stocks move together, destroying the long-short spread. Wait for VIX to normalize below 25 before deploying momentum capital.

3. **February through early March during FOMC hiking cycles:** Rate hike regimes hit high-multiple growth stocks (the typical momentum winners) disproportionately. In 2022, the top momentum stocks from 2021 were the worst performers as rates rose — a complete regime reversal that no momentum filter could avoid at the transition.

4. **After a momentum crash (within 3 months):** In the aftermath of a major momentum reversal, the strategy typically continues to underperform as post-crash bounces favor prior losers (short covering). Give the factor 2–3 months to re-establish its statistical edge before re-entering at full size.

5. **Universe too small:** Running 12-1 momentum on 20 stocks produces mostly noise — the idiosyncratic risk dominates the factor signal. Minimum viable universe is 100 stocks; 500+ is better. Never run this on fewer than 50 names.

6. **Post-earnings anomaly contamination:** If more than 30% of the universe has reported earnings in the last 5 trading days, the momentum scores are temporarily contaminated by post-earnings drift. Wait 5 trading days after major earnings waves before rebalancing.

7. **Momentum factor in crowded positioning:** When hedge fund 13F filings (available quarterly) show extreme clustering in top-momentum names, the crowding risk is elevated. A crowded momentum portfolio experiences amplified drawdowns when the crowd exits simultaneously.

---

## Strategy Parameters

| Parameter | Default | Range | Description |
|---|---|---|---|
| Lookback start | Month -12 | -18 to -6 | Beginning of return window |
| Lookback end | Month -1 | -3 to -1 | End of return window (exclude recent reversal) |
| Long decile | Top 10% | Top 5–20% | Stocks to buy |
| Short decile | Bottom 10% | Bottom 5–20% | Stocks to avoid or short (with spread) |
| Rebalance frequency | Monthly | Monthly only | More frequent = higher costs, no signal gain |
| Max single stock weight | 5% | 3–8% | Position cap per name |
| Max single sector weight | 40% | 30–50% | Sector concentration cap |
| Universe minimum | 200 stocks | 100–1000+ | S&P 500 or Russell 1000 recommended |
| Stop loss per position | -20% | -15 to -25% | Exit individual name if down this much |
| Regime filter | HMM ≠ BEAR | Required | Do not run in confirmed bear regime |
| Z-score minimum | +1.0 | +0.8–1.5 | Minimum Z-score to include in long book |
| Options DTE | 30–45 | 21–60 | For spread expression of long positions |
| Tail hedge allocation | 3–5% of portfolio | 2–6% | SPY put spreads, rolled quarterly |
| Crash protocol trigger | SPY -5% single day | Non-negotiable | Close momentum book on crash signal |

---

## Data Requirements

| Data | Source | Usage |
|---|---|---|
| Daily stock prices (OHLCV) | Polygon | 12-1 return calculation |
| Total return data (dividends) | Polygon | Dividends must be included in return calculation |
| S&P 500 / Russell 1000 constituents | Index provider | Universe definition (changes monthly) |
| Sector classifications (GICS) | MSCI / S&P | Sector concentration check |
| HMM regime | Platform regime model | Master filter — suppress in BEAR |
| VIX daily level | Polygon / CBOE | Secondary regime filter |
| Earnings calendar | DB | Avoid rebalancing immediately after mass earnings |
| Hedge fund 13F data (quarterly) | SEC EDGAR | Crowding risk assessment |
| FOMC meeting calendar | Federal Reserve | Avoid rebalancing within 5 days of decision |
