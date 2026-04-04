# Minimum Variance Hedge
### Computing the Exact Hedge Size That Maximizes Protection Per Dollar Spent

---

## Detailed Introduction

Most retail investors hedge their portfolios by buying put options — an intuitive and reasonable first instinct. The problem is that "buying puts" without a principled framework for sizing almost always results in either severe over-hedging (spending 3-4% of portfolio annually on protection that reduces performance more than it protects) or dangerous under-hedging (owning puts that are too small, too far out-of-the-money, or on the wrong instrument to meaningfully offset the actual portfolio losses when a real drawdown occurs). The minimum variance hedge addresses both failures by computing the mathematically optimal hedge size based on the actual statistical relationship between the portfolio and the hedging instrument.

The core insight is that the effectiveness of a hedge depends entirely on the correlation between what you own and what you are using to hedge it. A portfolio that is 90% correlated with SPY can be effectively hedged with SPY puts. A portfolio concentrated in small-cap value stocks that has a 65% correlation with SPY can only partially be hedged with SPY puts — you need more protection per dollar to achieve the same variance reduction, and you should consider whether QQQ puts, sector-specific puts, or a combination might provide a tighter correlation. Buying the wrong instrument's puts is expensive protection that fails when you most need it.

The FRM-standard optimal hedge ratio formula — h* = ρ × (σ_P / σ_H) — captures this calculation precisely. Rho is the correlation between the portfolio and the hedge; sigma_P and sigma_H are their respective volatilities. A tech-heavy portfolio with beta 1.4 to SPY and high correlation needs 1.4× the SPY notional coverage to achieve the same dollar protection as a beta-1.0 portfolio. Ignoring this calculation and buying "one SPY put for every $100k of portfolio" systematically underhedges tech-heavy books while wasting premium in the process.

The practice of minimum variance hedging in equity portfolios emerged from the futures market, where farmers and commodity producers have been computing optimal hedge ratios since the 1970s. Financial academics formalized it for equity portfolios in the 1980s, and it became standard curriculum in CFA and FRM programs. The sophistication available to retail practitioners has caught up considerably since the creation of liquid SPY and QQQ options markets — any practitioner with a brokerage account can now implement a portfolio hedge that would have required institutional infrastructure a decade ago.

The one thing that kills this hedge is the assumption of constant beta. In normal markets, a portfolio might have beta 1.1 to SPY. In a severe crash — the scenario the hedge is most intended to protect against — correlations compress toward 1.0 and the effective beta of most portfolios spikes to 1.3-1.5. This "crisis beta" phenomenon means that a hedge sized for normal-market beta will underperform during the exact crisis it was intended for. The practical response is to size the hedge for a stress scenario (use beta 1.4 in the calculation even if observed beta is 1.1) and accept the small cost of modest over-hedging in normal times.

---

## How It Works

Estimate the portfolio's beta to the hedging instrument using a 60-day rolling regression. Calculate the optimal hedge ratio. Size the hedge instrument (typically SPY puts or a debit put spread) to cover the calculated notional. Review and rebalance monthly.

**Optimal hedge ratio formula:**

```
h* = ρ_{P,H} × (σ_P / σ_H)

where:
  ρ_{P,H} = rolling 60-day correlation between portfolio daily returns and hedge daily returns
  σ_P     = annualized portfolio volatility (rolling 60-day)
  σ_H     = annualized hedge instrument volatility (rolling 60-day)

Regression approach (equivalent, often easier):
  Run OLS regression: P_daily_return = α + β × H_daily_return + ε
  β is the hedge ratio
  Hedge notional = β × portfolio_value

Example:
  Portfolio value: $400,000
  Portfolio β to SPY: 1.12 (from 60-day regression)
  Correlation ρ: 0.92
  SPY σ: 16.8% annualized
  Portfolio σ: 19.4% annualized

  h* = 0.92 × (19.4% / 16.8%) = 0.92 × 1.155 = 1.063
  Hedge notional = 1.063 × $400,000 = $425,200

  At SPY $475: $425,200 / $475 = 895 shares equivalent
  → Buy 9 SPY put contracts (covers 900 shares ≈ $427,500 notional)
```

**Stress scenario adjustment:**

```
Crisis beta multiplier: 1.3× to 1.5× of normal beta
  Normal beta: 1.12
  Stress beta: 1.12 × 1.3 = 1.46
  Stress hedge notional: 1.46 × $400,000 = $584,000

Conservative hedge: size for (normal + stress) / 2 = (1.063 + 1.46) / 2 = 1.26
  → Hedge notional: 1.26 × $400,000 = $504,000 (12 SPY put contracts at $475)

This costs ~20% more in premium but provides meaningful additional protection
in the crash scenario where beta spikes beyond normal levels.
```

**Strike selection:**

```
At-the-money (ATM) puts:
  Most expensive per unit of protection
  Best hedge efficiency (highest delta coverage)
  Best for portfolios actively trading and needing current-level protection

10% out-of-the-money (OTM) puts:
  Lower premium per contract (typically 30-50% cheaper than ATM)
  Only protects against declines beyond 10%
  Best for long-term portfolios tolerating small corrections but hedging tail risk

15-20% OTM puts:
  Cheapest per contract
  Only activates in severe corrections (2022-level or worse)
  Best for very long-horizon investors who accept 15-20% drawdowns but not 40-50%
```

---

## Real Trade Example

**Portfolio: $400,000. Composition: 40% SPY, 20% QQQ, 20% IWM, 20% individual stocks (AAPL, NVDA, JPM, AMZN).**

**Step 1: Measure portfolio beta (60-day regression vs SPY):**
- Result: β = 1.12 (portfolio moves 1.12× SPY on average)
- Correlation: 0.92 (high — good hedge instrument)
- Portfolio annualized vol: 19.4%
- SPY annualized vol: 16.8%

**Step 2: Optimal hedge ratio:**
h* = 0.92 × (19.4% / 16.8%) = **1.06**
Hedge notional = 1.06 × $400,000 = $424,000

**Step 3: Select instrument and size (using stress scenario):**
- Stress beta = 1.12 × 1.3 = 1.46 (crisis scenario)
- Average h* = (1.06 + 1.46) / 2 = 1.26 (compromise sizing)
- Hedge notional: 1.26 × $400,000 = $504,000
- SPY at $475: $504,000 / $475 = 1,061 shares equivalent
- **Buy 10 SPY Mar 2024 $450 put contracts** (10% OTM) at $4.20 each
  - Cost: 10 × 100 × $4.20 = $4,200 (1.05% of portfolio — annual budget: 1-2%)
  - Notional covered: 10 × 100 × $475 = $475,000

**Step 4: Evaluate hedge performance (March 2024 hypothetical):**
SPY falls to $430 (−9.5% drawdown):
- Portfolio loss at β=1.12: −$400,000 × 1.12 × 9.5% = −$42,600
- Put value: $450 put with SPY at $430 → $20 intrinsic × 10 × 100 = $20,000
- Hedge effectiveness: $20,000 / $42,600 = **47% of loss recovered**

Note: Using 10% OTM puts recovered 47%. ATM puts would have recovered approximately 65-75% at 2-3× the premium cost. The choice of OTM strike is the core cost-effectiveness tradeoff.

**Annual hedge cost budget:**
$4,200 per quarter × 4 = $16,800 per year = **4.2% of portfolio** (expensive — roll to ATM to reduce cost, or accept lower coverage with 15% OTM at ~2% annual cost)

---

## Entry Checklist

- [ ] Calculate portfolio beta using 60-day rolling OLS regression against SPY (or chosen hedge)
- [ ] Calculate h* = ρ × (σ_P / σ_H) or use β directly from regression
- [ ] Apply stress beta multiplier: use (normal β + 1.3 × normal β) / 2 for sizing
- [ ] Hedge notional = h* × portfolio value
- [ ] Strike selection: 10-15% OTM for cost-efficiency (ATM if protecting against near-term correction)
- [ ] DTE: 60-90 days to allow time for hedge to activate without immediate theta drain
- [ ] Annual premium budget set: 1-2% of portfolio maximum (roll quarterly if using 3-month puts)
- [ ] Rebalance trigger: if calculated optimal notional differs more than 15% from current hedge
- [ ] Track hedge efficiency: after any 5%+ drawdown, calculate how much the hedge paid vs portfolio loss
- [ ] Include bonds (TLT) in portfolio beta calculation: TLT negative correlation may reduce hedge need

---

## Risk Management

**Max loss on the hedge itself:** The premium paid on the puts — never more. Puts are long convexity; they cannot create additional portfolio losses beyond the premium cost.

**Hedge slippage:** SPY put spreads (long ATM put, short OTM put to reduce cost) reduce premium but cap the maximum hedge payoff. A 10% OTM long put combined with a 25% OTM short put costs approximately 40% less than a naked ATM put but stops paying at 25% decline. Match the spread structure to the specific tail you are protecting against.

**Rebalancing protocol:** The hedge notional becomes stale as the portfolio changes:
- Monthly: recalculate β using rolling 60-day data
- Immediately after large portfolio changes (adding/removing 10%+ of capital)
- Rebalance if calculated notional drifts more than 15% from current hedge
- After a 20%+ market decline: β typically spikes; recalculate immediately

**Dividend and carry considerations:** SPY puts on long horizons (6-12 months) need to account for the dividend your SPY long position earns (~1.3% annually) and the forward price effect. The "fair" cost of the hedge is slightly lower than the raw put price. This is a second-order effect but matters when comparing hedge costs across different instruments.

**When it goes wrong:** The crisis correlation failure — portfolio loses more than beta × market decline because individual holdings have idiosyncratic risk. A concentrated portfolio (four stocks plus ETFs) will have idiosyncratic events — earnings misses, regulatory hits — that are not captured by the market hedge. Minimum variance hedging addresses the systematic risk; it does not protect against individual stock blowups. For concentrated single-stock risk, individual put protection on the large holdings is required in addition to the portfolio hedge.

---

## When to Avoid

1. **Hedging a portfolio that is not correlated with SPY (below 0.70 correlation):** If the portfolio has low SPY correlation (emerging markets, commodities, merger arb), SPY puts are a poor hedge. Calculate the actual hedge instrument correlation and use QQQ puts (tech portfolio), EEM puts (emerging market portfolio), or sector-specific puts for more precise hedging.

2. **Using a round number for contract count without calculation:** "I'll buy 10 puts" is not minimum variance hedging — it's guessing. Compute h* and size to that number, even if the result is an odd number like 7 or 13 contracts.

3. **Annual hedge budget exceeding 3% of portfolio:** Spending more than 3% per year on portfolio insurance consistently destroys long-run returns. If the calculated optimal hedge costs more than this, either accept less protection (OTM strikes), use hedges only when the regime model signals elevated risk, or restructure the underlying portfolio to reduce its beta.

4. **Ignoring the existing hedge in bonds:** If the portfolio holds TLT or investment-grade bonds, the natural negative correlation with equities provides implicit hedging. Run the minimum variance calculation on the TOTAL portfolio (equities + bonds + other) to avoid double-hedging equity risk that the bonds already offset.

5. **Assuming the hedge is set-and-forget for more than 30 days:** Beta, correlation, and volatility all change over time. A hedge sized in January may be significantly over- or under-sized by March if the portfolio was rebalanced, if volatility changed, or if correlations shifted. Monthly recalculation is not optional.

---

## Strategy Parameters

| Parameter | Default | Range | Description |
|---|---|---|---|
| Beta estimation window | 60 days | 40–120 | Rolling OLS regression lookback |
| Hedge instrument | SPY puts | SPY / QQQ / Sector | Choose based on portfolio composition |
| Hedge ratio method | h* = ρ × (σ_P/σ_H) | h* or β | Both equivalent; regression β is simpler |
| Stress beta multiplier | 1.3× | 1.2–1.5× | Crisis beta spike adjustment |
| Sizing approach | Stress-adjusted (conservative) | Normal or stress-adjusted | Conservative covers crisis better |
| Strike selection | 10–15% OTM | ATM to 20% OTM | Balance cost and coverage depth |
| DTE | 60–90 days | 45–120 | Roll quarterly |
| Annual budget cap | 1–2% of portfolio | 0.5–3% | Maximum acceptable hedge cost |
| Rebalance threshold | 15% drift from target | 10–20% | When to resize the hedge |
| Rebalance frequency | Monthly | Monthly or event-driven | Or immediately after large portfolio change |
| Debit spread option | ATM long / OTM short | Optional | Reduces cost, caps maximum payoff |
| Dividend adjustment | Include in cost calculation | Preferred | Forward price effect on long-horizon hedges |
