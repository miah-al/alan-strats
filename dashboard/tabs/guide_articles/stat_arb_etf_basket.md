## Statistical Arb — ETF Basket

**In plain English:** An ETF is just a basket of stocks. If the ETF's market price drifts away from the fair value of its components (the "NAV"), that's an arbitrage opportunity. This strategy continuously monitors the difference between an ETF's live price and its calculated intraday NAV (iNAV), entering long/short pairs when the gap exceeds transaction costs. Large-scale ETF arbitrage is done by authorized participants; this strategy exploits the smaller residual dislocations available to retail traders.

---

### How ETF Arbitrage Works

Every ETF has a "creation/redemption" mechanism:
- **Authorized Participants (APs)** can create new shares by delivering the underlying basket to the ETF issuer
- They can also redeem shares by returning ETF shares in exchange for the basket
- This mechanism keeps ETF price close to NAV — but not perfectly

**Dislocation scenarios:**
1. **ETF > NAV (premium):** APs create new ETF shares (buy basket, deliver to issuer, sell ETF) → premium collapses
2. **ETF < NAV (discount):** APs redeem ETF shares (buy ETF, return to issuer, receive basket, sell basket) → discount collapses

APs handle dislocations > 0.5–1%. **Smaller dislocations (0.1–0.4%)** remain for 10–60 minutes before being corrected.

---

### Real Trade Walkthrough

> **Date:** Mar 14, 2024 · **XLK (Technology Select Sector ETF)** · Time: 10:22am

**Live XLK price:** $206.80
**Calculated iNAV** (weighted sum of AAPL, MSFT, NVDA, etc. weights × live prices): $206.45
**Premium:** $0.35 = **0.17% above fair value**

The premium appeared during a brief momentum surge as retail FOMO bought XLK without proportionate buying in underlying stocks.

**Trade:**
- Sell 300 shares XLK at $206.80 (short the expensive ETF)
- Buy hedge: AAPL × 0.23, MSFT × 0.21, NVDA × 0.06, etc. (per XLK weights) — or use SPY as a rough proxy
- Net position: short XLK, long component basket

**10:38am (16 minutes later):** XLK reprices to $206.52, iNAV moves to $206.48.

**Close:**
- Cover XLK short at $206.52 → gain $0.28/share × 300 = **+$84**
- Close component longs at various prices → net cost $0.03/share after commissions
- **Net profit: ~$75 on $62,040 notional = 0.12%**

Small dollar amounts — this strategy requires size or high frequency to be meaningful. But the risk/reward is excellent: the spread MUST close because of the creation/redemption mechanism.

---

### Finding Dislocations

**iNAV calculation:**

```
iNAV = Σ (weight_i × price_i) / (shares_outstanding × divisor)
```

Most brokers and financial data providers publish iNAV in real time for major ETFs.

**Useful data sources:**
- ETF issuer websites (iShares, SPDR, Vanguard publish iNAV)
- Bloomberg terminal: `XLK US EQUITY INAV`
- Polygon.io: real-time quotes for ETF + components

**Filters for good candidates:**
- High-volume ETFs only (SPY, QQQ, XLK, XLF, GLD) — tight bid-ask spreads
- Premium/discount > 0.15% (minimum after commissions)
- Premium/discount has been stable for ≥ 5 minutes (not already reversing)
- Not during opening 15 minutes or closing 5 minutes (iNAV unreliable)

---

### Sector ETF Specific Patterns

Different sectors show different dislocation patterns:

**XLF (Financial Select):** Dislocates heavily during bank earnings (large holdings = JPMC, BAC report → components move but ETF lags by 2–5 minutes)

**GLD (Gold ETF):** Dislocates when London gold market closes at 10:30am EST — gold futures continue trading but the London fixing is done. 30-minute window of iNAV divergence.

**EEM (Emerging Markets):** Largest and most frequent dislocations because underlying components trade in Asian time zones. During US morning, stale Asian prices create persistent discounts/premiums.

**TLT (20+ Year Treasury ETF):** Dislocates around 8:30am economic data releases — futures gap immediately but the ETF opening price lags.

---

### Entry Checklist

- [ ] Calculate current premium/discount using live iNAV
- [ ] Premium > 0.15% after estimated bid-ask spread on both legs (ETF + basket or proxy)
- [ ] Volume on ETF is normal (not a "stuck" price in illiquid conditions)
- [ ] No pending macro event in next 30 minutes (FOMC, CPI could widen dislocation unpredictably)
- [ ] Exit target: 50–75% of premium closure (don't wait for full convergence — it may not converge today)

---

### Common Mistakes

1. **Not accounting for both sides of the spread.** You pay bid-ask on both legs. If XLK bid-ask is $0.02 and each component averages $0.03, total round-trip cost is ~$0.05. A $0.10 premium barely covers costs.

2. **Trading illiquid ETFs.** A small-cap sector ETF (e.g., PSCT for small-cap tech) might have 50,000 shares/day volume. The bid-ask is wide and the iNAV is stale. Stick to ETFs with >5 million shares daily volume.

3. **Ignoring dividend dates.** ETF NAV adjusts on ex-dividend dates — what looks like a premium might just be the ETF going ex-dividend (NAV drops, price lags). Always check ex-dividend dates before trading.

4. **Confusing NAV premium with momentum.** Sometimes XLK is at a premium because large buyers are accumulating it — and they'll keep buying, widening the premium further. The arbitrage works on a statistical basis, not every single occurrence. Use size proportional to your confidence.
