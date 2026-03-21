## Minimum Variance Hedge

**In plain English:** Instead of arbitrarily deciding to hedge 50% of your portfolio, minimum variance hedging calculates the EXACT hedge ratio that minimizes your total portfolio variance. It uses the covariance between your portfolio and the hedging instrument (usually SPY puts or VIX) to find the point where adding more hedge stops reducing risk and starts increasing it. The result is an optimally sized hedge that doesn't over- or under-protect.

---

### The Math: Optimal Hedge Ratio

**Setup:**
- Portfolio P with value $V_P and returns σ_P (volatility)
- Hedging instrument H (e.g., SPY put, VIX call) with returns σ_H
- Correlation between P and H: ρ_{P,H}

**Optimal hedge ratio (h*):**
```
h* = ρ_{P,H} × (σ_P / σ_H)
```

**Interpretation:** If your portfolio is perfectly correlated with SPY (ρ=1.0) and has the same volatility (σ_P = σ_H), then h* = 1.0 — hedge 100%. If your portfolio is only 70% correlated with SPY and has 1.5× the volatility of SPY, then h* = 0.7 × 1.5 = 1.05 — hedge 105% notional.

**Practical formula (using regression):**
Run a regression of portfolio daily returns on hedging instrument returns:
```
P_return = α + β × H_return + ε
```
The β is your hedge ratio. Hedge with notional = β × V_P.

---

### Why Optimal Hedge Ratio Matters

**Example: Tech-heavy portfolio**

You hold $300,000 in QQQ, NVDA, TSLA, MSFT. Your portfolio β to SPY is 1.4 (moves 1.4× as much as SPY).

**Naive hedge:** Buy SPY puts with $300,000 notional coverage. This underhedges — when SPY falls 5%, your portfolio falls 7%, but your SPY puts only pay for a 5% move.

**Optimal hedge:**
- β = 1.4
- Hedge notional = 1.4 × $300,000 = $420,000 SPY equivalent
- At $450 SPY, that's $420,000 / $450 = 933 shares equivalent
- Buy 10 SPY put contracts (covers 1,000 shares = $450,000 notional)

Now when SPY falls 5%, your portfolio falls ~7%, and your puts pay on a 5% SPY move with 10 contracts × 100 × $22.50 (value at expiry if 5% OTM put lands ITM) = $22,500 payout. This offsets more of the loss.

---

### Real Trade Walkthrough

> **Portfolio:** $400,000, diversified: 40% SPY, 20% QQQ, 20% IWM, 20% individual stocks (AAPL, NVDA, JPM, AMZN)

**Step 1: Measure portfolio beta to SPY**

Run 60-day regression of portfolio daily returns vs SPY daily returns:
- Result: β = 1.12 (portfolio moves 1.12× SPY)
- Correlation: 0.92 (high)
- Portfolio volatility (annualized): 19.4%
- SPY volatility (annualized): 16.8%

**Step 2: Optimal hedge ratio**
```
h* = ρ × (σ_P / σ_H) = 0.92 × (19.4% / 16.8%) = 1.06
```
Hedge notional = 1.06 × $400,000 = $424,000

**Step 3: Select instrument and size**
- SPY at $475: $424,000 / $475 = 893 shares equivalent
- Buy 9 contracts of SPY Mar 2024 $450 put (15% OTM) at $4.20 each
  - Cost: 9 × 100 × $4.20 = $3,780
  - Notional covered: 9 × 100 × $475 = $427,500

**Step 4: Evaluate hedge efficiency**

March 2024: SPY falls to $430 (−9.5% drawdown):
- Portfolio loss (at β=1.12): approximately −$47,800
- Put value: $450 put with SPY at $430 → $20 intrinsic × 9 contracts × 100 = $18,000
- Hedge ratio: $18,000 / $47,800 = 38% of loss recovered

Note: The hedge recovered only 38% because puts were 15% OTM (needed a bigger move to be fully effective). Adjusting to 10% OTM puts would have recovered 65% at higher cost.

---

### Dynamic Rebalancing of Hedge

The optimal hedge ratio changes over time as:
1. Portfolio composition changes (buy/sell individual stocks)
2. Correlations change (after market structure shifts)
3. Volatilities change (VIX expanding in stress periods)

**Rebalancing protocol:**
- Monthly: recalculate β using 60-day rolling regression
- Rebalance hedge if calculated notional differs > 15% from current hedge
- After major portfolio changes (add new positions): recalculate immediately

---

### Alternative Hedging Instruments

| Instrument | Correlation to Portfolio | Cost | Best Use |
|---|---|---|---|
| SPY puts | 0.90–0.95 | Low–moderate | Standard hedge |
| QQQ puts | 0.92 (for tech-heavy) | Moderate | Tech portfolios |
| VIX calls | 0.65–0.75 | Low in calm markets | Tail risk only |
| Inverse ETF (SH) | −0.93 | High (decay) | Never — use puts |
| ProShares 2× inverse (SDS) | −1.85 | Very high (decay) | Never — use puts |

**For optimal variance reduction:** Choose the instrument with the highest correlation to your portfolio losses.

---

### Entry Checklist

- [ ] Calculate portfolio β using 60-day rolling regression vs SPY
- [ ] Calculate optimal hedge ratio: h* = ρ × (σ_P / σ_H)
- [ ] Select strikes: 10–15% OTM for cost-efficiency
- [ ] Monthly recalculation and rebalancing if drift > 15%
- [ ] Track hedge efficiency: after any 5%+ portfolio drawdown, verify hedge paid as expected
- [ ] Annual hedge budget: 1–2% of portfolio value (keep cost bounded)

---

### Common Mistakes

1. **Using a round number for hedge size.** "I'll buy 10 puts" is not a hedge strategy — it's a guess. Compute the optimal hedge ratio and size accordingly, even if the result is an odd number like 7 or 13 contracts.

2. **Not adjusting for dividends and carry.** SPY puts on a 9-month horizon miss the dividends your SPY position earns (approximately 1.2% annually). The "fair" hedge cost is slightly lower than the put price, accounting for dividends that offset some of the downside.

3. **Assuming constant β.** Your portfolio's β to SPY increases significantly during crashes (crisis correlation = all assets move together). A β of 1.1 in normal times becomes 1.4 in a crisis. Consider stress-testing your hedge with β=1.5 to understand real crisis exposure.

4. **Hedging only the equity part.** If you also hold bonds (TLT) and your TLT has negative correlation to your equity portfolio, you may be naturally hedged already. Run the min-variance calculation on your TOTAL portfolio (equities + bonds + other) to avoid over-hedging.
