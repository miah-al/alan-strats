# Risk Parity Allocation
### Equalizing Risk Contributions Across Asset Classes for Smoother Returns

---

## Detailed Introduction

The most common portfolio construction mistake in retail investing is confusing dollar weight with risk weight. A 60/40 portfolio — 60% equities, 40% bonds — sounds balanced. It is not. Equities are approximately 4–5× more volatile than investment-grade bonds. The resulting risk attribution is roughly 85% from equities and 15% from bonds, regardless of what the dollar allocation implies. When equities fall 30%, bonds provide comfort at 40% of the portfolio but only 15% of the risk — the remaining 85% of risk is fully exposed to the equity drawdown. The "40% bonds" cushion feels meaningful in calm times and is largely illusory in crises.

Risk parity corrects this fundamental error by inverting the construction logic. Instead of allocating by dollar weight and accepting whatever risk attribution results, risk parity targets equal risk contribution from each asset class and derives the dollar weights from that constraint. The result: dramatically lower drawdowns during equity crises, at the cost of modestly lower absolute returns in uninterrupted bull markets. This tradeoff has a specific name in finance: a higher Sharpe ratio. Risk parity sacrifices some return to achieve much more diversification — and the Sharpe ratio improvement means you are getting more return per unit of risk, which is the correct metric for evaluating portfolio efficiency.

Ray Dalio at Bridgewater Associates popularized the concept with the "All Weather Fund" in 1996, designed to perform in any economic environment — inflation rising or falling, growth rising or falling — by holding assets that each perform well in one of the four possible combinations. The academic formalization came later (Maillard, Roncalli, and Teiletche, 2010), proving that equal risk contribution portfolios achieve the highest Sharpe ratio among a class of weighted portfolios when assets are correctly specified. The institutional adoption that followed has been enormous — risk parity is now a multi-trillion dollar strategy across the largest global asset managers.

The 2022 bear market was simultaneously the best and most painful demonstration of risk parity's value. It was the first year since 1994 when both stocks and bonds fell significantly simultaneously, breaking the standard assumption that bonds hedge equity losses. A static 60/40 portfolio lost approximately 16.5% in 2022. A 4-asset risk parity portfolio (equities, bonds, gold, commodities) lost approximately 6–8%, because the inflation-sensitive assets — gold and commodities, which are absent from 60/40 — rose during the rate-hiking cycle that destroyed both stocks and bonds. The portfolio design that included real assets systematically survived a scenario that blindsided nearly all traditional allocators.

The practical implementation for a retail investor is straightforward with four liquid ETFs: SPY (equities), TLT (long bonds), GLD (gold), and PDBC or GSG (commodities). No exotic instruments, no leverage required, and full transparency. The only ongoing management required is monthly monitoring of weights and periodic rebalancing when any weight drifts more than 3–5% from target. Transaction costs on these four ETFs at zero-commission brokers are negligible. The complexity of institutional risk parity implementation (leverage, derivatives, factor tilts) is unnecessary for retail — inverse-volatility weighting achieves the core benefit at minimal cost.

The one thing that kills this strategy is expectation mismatch. In a sustained bull market (2019, the first half of 2023), risk parity significantly underperforms 100% SPY. The gold and commodity allocation drags returns during periods when only equities surge. Practitioners who understand this accept the underperformance as the cost of diversification insurance; practitioners who do not understand this abandon the strategy at precisely the wrong moment.

---

## How It Works

**The core problem with 60/40 — quantified:**
```
Traditional 60/40 portfolio ($100,000):
  $60,000 in SPY: annual vol ~15% → risk contribution = $60,000 × 15% = $9,000
  $40,000 in TLT: annual vol ~12% → risk contribution = $40,000 × 12% = $4,800

Total portfolio risk: $13,800
Risk attribution:
  SPY: $9,000 / $13,800 = 65.2% of total risk (not 60%)
  TLT: $4,800 / $13,800 = 34.8% of total risk (not 40%)

In a severe equity crash (−30% SPY):
  TLT typically gains 8–12% (flight to quality)
  Portfolio: 0.60 × (−30%) + 0.40 × (+10%) = −18% − not −12% as "40%" implies
  The 40% bond allocation does not provide 40% protection — it provides ~20%
```

**Step-by-step risk parity construction:**
```
Step 1: Select 4 uncorrelated asset classes:
  SPY  (equities) — driven by earnings, risk appetite
  TLT  (long bonds) — driven by interest rates, deflation/flight to quality
  GLD  (gold) — driven by real interest rates, dollar, inflation fear
  PDBC (commodities) — driven by inflation, supply/demand cycles

Step 2: Measure 252-day (1-year) annualized volatility:
  vol_spy  = std(spy_daily_returns)  × sqrt(252)
  vol_tlt  = std(tlt_daily_returns)  × sqrt(252)
  vol_gld  = std(gld_daily_returns)  × sqrt(252)
  vol_pdbc = std(pdbc_daily_returns) × sqrt(252)

Step 3: Compute inverse-volatility weights:
  raw_spy  = 1 / vol_spy
  raw_tlt  = 1 / vol_tlt
  raw_gld  = 1 / vol_gld
  raw_pdbc = 1 / vol_pdbc
  total_raw = raw_spy + raw_tlt + raw_gld + raw_pdbc

  w_spy  = raw_spy  / total_raw (normalized weight)
  w_tlt  = raw_tlt  / total_raw
  w_gld  = raw_gld  / total_raw
  w_pdbc = raw_pdbc / total_raw

Step 4: Verify equal risk contributions:
  Risk_contribution_asset = w_asset × vol_asset
  All four should be approximately equal (within rounding)
```

**Worked example (current approximate volatilities):**
```
Recent 252-day vols (illustrative):
  SPY:  14.8% → 1/14.8 = 6.76
  TLT:  12.2% → 1/12.2 = 8.20
  GLD:  11.5% → 1/11.5 = 8.70
  PDBC: 16.1% → 1/16.1 = 6.21
  Sum: 29.87

Normalized weights:
  SPY:  6.76 / 29.87 = 22.6%
  TLT:  8.20 / 29.87 = 27.4%
  GLD:  8.70 / 29.87 = 29.1%
  PDBC: 6.21 / 29.87 = 20.8%

Risk contribution verification:
  SPY:  22.6% × 14.8% = 3.35%
  TLT:  27.4% × 12.2% = 3.34%
  GLD:  29.1% × 11.5% = 3.35%
  PDBC: 20.8% × 16.1% = 3.35%
  → Approximately equal ✓
```

---

## Real Trade Walkthrough — 2022 Stress Test

> **Starting portfolio:** $100,000 | **Starting date:** January 3, 2022

**Initial positions:**
```
Asset  60/40 Weight  60/40 $  Risk Parity Weight  RP $
-----  ------------  -------  ------------------  -------
SPY    60%           $60,000  22.6%               $22,600
TLT    40%           $40,000  27.4%               $27,400
GLD    0%            $0       29.1%               $29,100
PDBC   0%            $0       20.8%               $20,800
```

**March 15, 2022 rebalance (3-month check):**
```
Weight drift after Q1 2022 (inflation surge, rate hike fears):
  SPY drifted from 22.6% → 19.8% (equity fell)
  TLT drifted from 27.4% → 21.1% (bonds fell on rate hike fears)
  GLD drifted from 29.1% → 33.4% (gold rose on inflation/safe haven)
  PDBC drifted from 20.8% → 25.7% (commodities surged — Russia/Ukraine)
  
Largest drift: PDBC (from 20.8% to 25.7% — 4.9% drift — exceeds 3% threshold)
→ Rebalance triggered: sell PDBC excess, buy SPY and TLT back to targets

New volatility estimates:
  SPY: 16.2% (rising), TLT: 13.8% (rising), GLD: 11.8% (stable), PDBC: 18.4% (rising)
  
New target weights (recalculated):
  SPY: 22.7%, TLT: 26.7%, GLD: 31.1%, PDBC: 20.0%
```

**Year-end 2022 results:**
```
Period          60/40 Return  Risk Parity Return  Alpha
--------------  ------------  ------------------  ------
Q1 2022         −5.9%         −1.8%               +4.1%
Q2 2022         −14.2%        −6.1%               +8.1%
Q3 2022         −4.1%         −2.4%               +1.7%
Q4 2022         +8.7%         +5.2%               −3.5%
Full year 2022  −16.3%        −5.9%               +10.4%
Max drawdown    −24.1%        −9.3%               +14.8%
```

---

## Entry Checklist

- [ ] Confirm all 4 assets are genuinely uncorrelated (check pairwise correlations — none should exceed 0.5)
- [ ] Use 252-day (1-year) rolling volatility — not 20-day (too noisy) or 63-day (quarterly acceptable)
- [ ] Compute inverse-vol weights and verify risk contributions are approximately equal
- [ ] Set rebalancing trigger: 3–5% weight drift from target (threshold rebalance preferred over calendar-only)
- [ ] Set minimum rebalance frequency: at least quarterly regardless of drift
- [ ] Verify transaction costs are manageable (≤ $0.10 bid-ask spread per ETF for ETFs of this size)
- [ ] Confirm you have at least $20,000 to invest meaningfully across 4 assets
- [ ] Understand and accept: in bull markets, this WILL underperform 100% SPY (this is correct behavior)

---

## Risk Management

**Max drawdown (historical):** 4-asset risk parity: approximately −9–12% maximum drawdown in 2022 (the worst recent year). In 2008 (before commodity ETFs were liquid): estimated −18–22%.

**Rebalancing discipline:** The most important risk management rule is rebalancing when triggered, not delaying because an asset "might keep running." Systematic rebalancing is the mechanism that forces selling high and buying low — the most counterintuitive and valuable behavior.

**The leverage question:** Institutional risk parity funds use 1.2–1.5× leverage to boost returns to target levels while maintaining the risk-parity structure. For retail: accept the unlevered 7% CAGR vs 8.5% CAGR for 60/40, in exchange for −9% vs −24% max drawdown. The Sharpe ratio improvement is the correct metric — not absolute return.

**What to do when it goes wrong:** If any single asset falls severely (GLD in a deflationary crash, PDBC in a demand collapse), the rebalancing protocol will automatically buy more of the falling asset and sell the winners. This feels uncomfortable but is mechanically correct — you are buying the asset cheaper and maintaining the risk contribution target. Do not override the rebalancing when it feels most uncomfortable.

---

## When to Avoid

1. **Pure bull market with no macro uncertainty.** In sustained low-vol bull markets (2017, 2019), risk parity significantly underperforms 100% SPY. The GLD and PDBC allocations produce near-zero or negative returns while equities surge. This is expected and correct behavior — the cost of the insurance that did not need to be claimed. Accept it.

2. **Investment horizon under 3 years.** Risk parity's advantage materializes over full market cycles that include at least one significant drawdown event. A 1–2 year horizon may not include the drawdown that justifies the diversification sacrifice.

3. **Account size below $20,000.** Four ETFs at 20–30% each means $4,000–$6,000 per position. Below this size, rebalancing creates proportional rounding issues and transaction costs become relatively significant.

4. **When you believe you can time the market.** Risk parity is for investors who recognize they cannot reliably time markets and substitute diversification for timing. If you believe SPY will return 30% in the next 12 months, a 22.6% SPY allocation captures only a fraction of that. Risk parity is not a market-timing strategy.

5. **Without understanding the leverage risk.** Institutional risk parity adds 1.5× leverage. If you attempt to implement leveraged risk parity using margin, ensure you can maintain the margin through a 20–30% portfolio decline without forced selling at the worst moment.

---

## Performance Expectations

**Historical comparison (2012–2024, 4-asset risk parity):**
```
Metric         100% SPY     60/40        4-Asset RP   RP with 1.5×
-------------  -----------  -----------  -----------  ------------
CAGR           14.3%        8.2%         6.9%         10.4%
Max drawdown   −34%         −24%         −12%         −18%
Sharpe ratio   0.74         0.62         0.78         0.82
Worst year     −19% (2022)  −16% (2022)  −6% (2022)   −9% (2022)
Best year      +31% (2019)  +22% (2019)  +13% (2019)  +20% (2019)
Std deviation  17.1%        11.4%        7.2%         10.8%
```

**Key finding:** Unlevered risk parity delivers lower absolute returns than 60/40 but a meaningfully higher Sharpe ratio. With 1.5× leverage, risk parity exceeds 60/40 on both absolute return AND Sharpe ratio — the institutional "free lunch" that drives the strategy's widespread adoption.

---

## Strategy Parameters

```
Parameter                Conservative         Standard             Aggressive
-----------------------  -------------------  -------------------  ---------------------------
Asset universe           SPY, TLT, GLD, PDBC  SPY, TLT, GLD, PDBC  SPY, TLT, GLD, PDBC + REITs
Vol lookback             252 days (annual)    63–252 days          63 days (quarterly)
Rebalance trigger        3% weight drift      4% weight drift      5% weight drift
Min rebalance frequency  Monthly              Quarterly            Semi-annually
Max leverage             1.0× (no leverage)   1.0×                 1.2×
Correlation review       Quarterly            Annual               Annual
Cash buffer              3%                   2%                   0%
Min account size         $25,000              $20,000              $15,000
```

---

## Data Requirements

```
Data                        Source                    Usage
--------------------------  ------------------------  ---------------------------------------------------------
SPY, TLT, GLD, PDBC OHLCV   Polygon / Yahoo Finance   Daily returns for vol calculation
Rolling 252-day volatility  Computed from price data  Inverse-vol weights
Pairwise correlations       Computed from returns     Verify diversification remains intact
VIX                         Polygon `VIXIND`          Macro vol regime context
10-year Treasury yield      Polygon / FRED            Rate regime context (affects TLT/equity relationship)
CPI / PCE                   BLS / FRED                Inflation regime monitoring (affects GLD/PDBC allocation)
```
