## Tail Risk — Long Put Hedge

**In plain English:** Buy out-of-the-money SPY puts as insurance against a market crash. Pay a small premium each month. Lose money slowly in normal markets. Win explosively in crashes. The goal isn't to profit from the hedge — it's to stay solvent through a 30–40% drawdown so you can buy aggressively at the bottom when everyone else is forced to sell.

---

### The Insurance Framing

A long put hedge is exactly like car insurance:
- You pay premiums every month (cost)
- Most months, nothing bad happens (you "lose" the premium)
- When the crash hits, the insurance pays enormously

The question isn't "will the put make money?" — it probably won't on average. The question is: **"can I afford to be unhedged during a 40% crash?"**

For a $500,000 portfolio, a 40% crash = −$200,000. A hedge costing $1,000/month ($12,000/year) that returns $80,000 in the crash scenario has an expected value of roughly:
- P(crash) × $80,000 − P(no crash) × $12,000 ≈ negative expected value
- But the UTILITY value is enormous (avoids forced selling, avoids psychological panic)

---

### Strike Selection

The key variable: how far OTM you buy.

| Strike | Premium Cost | Payout in 20% Crash | Payout in 40% Crash |
|---|---|---|---|
| 5% OTM (near ATM) | $400/month | +$1,500 | +$3,500 |
| 15% OTM | $80/month | $0 (OTM) | +$2,500 |
| 25% OTM | $25/month | $0 (OTM) | +$1,500 |
| 30% OTM | $10/month | $0 (OTM) | +$1,000 |

For a $500,000 portfolio (holding ~1,500 SPY shares equivalent):

**Optimal zone: 15–20% OTM puts.** The premium is low enough to sustain monthly purchases, but the payout in a real crash is substantial.

---

### Real Trade Walkthrough

> **Date:** January 3, 2022 · SPY: $477 · Strategy: monthly far-OTM puts

**Purchase (January 2022):**
- Buy March 2022 SPY $390 put (18% OTM) → pay $2.10 = $210 per contract
- 5 contracts for $500,000 portfolio = $1,050 total

**January:** SPY falls from $477 to $450 → $390 put now worth $2.80 (+33%)

**Still far OTM — hold.** February: SPY at $435, put at $3.90.

**March FOMC (March 16, 2022):** Fed hikes 25 bps. SPY bounces to $450. Put falls back to $2.20. Let expire. **Loss: $210 × 5 = −$50**

**April 2022:** Buy June 2022 $380 put (15% OTM from $445) → pay $3.50 × 5 = $1,750

**May–June 2022:** Inflation prints high; tech crashes. SPY falls to $380 by mid-June.

**June 16, 2022 (2 weeks before expiry):** $380 put worth $14.50 (SPY AT $380 — nearly ATM)

**Sell:** $14.50 × 5 contracts × 100 = **$7,250**
**Paid:** $1,750
**Net P&L from this hedge:** **+$5,500**

**Portfolio protection:** Portfolio was down $60,000 in underlying equity, but hedge returned $5,500 — partial but meaningful offset.

---

### Sizing the Hedge

**Rule of thumb:** Hedge cost should be 0.5–1.5% of portfolio value per year.

For a $500,000 portfolio:
- $2,500–$7,500 annual hedge budget
- Monthly put budget: $200–$600/month

**How many contracts:**
Each SPY put contract covers 100 shares = ~$45,000 notional at $450 SPY.

For $500,000 portfolio → need ~11 contracts to fully hedge. At $80/month per contract (15% OTM), that's $880/month ($10,560/year) — above the 1.5% budget.

**Practical approach:** Hedge 50% of portfolio (5–6 contracts) and accept that you'll still take significant losses in crashes, just less severe.

---

### The Rolling Protocol

Puts expire. You must roll them continuously:

**Monthly rolling:**
- 30–45 days before expiry: assess current put's value
- If put has appreciated > 50% → sell, re-buy further OTM (lock in gains, reduce cost of new hedge)
- If put is near worthless → let expire, buy new put at same strike/expiry structure
- Never let puts expire in the final week (bid-ask spread widens dramatically)

**What expiry to buy:**
- 60–90 DTE (days to expiry) at purchase: captures enough time value decay at a reasonable rate
- Avoid < 30 DTE: theta decay accelerates, put loses value quickly even in moderate declines
- Avoid > 180 DTE: too expensive; pay for time value you don't need

---

### Entry Checklist

- [ ] Annual hedge budget set at 0.5–1.5% of portfolio value
- [ ] Strike: 15–20% below current SPY price
- [ ] Expiry: 60–90 DTE at purchase
- [ ] Monthly rolling protocol documented and automated
- [ ] Never hedge 100% — hedge cost would exceed portfolio's expected excess return
- [ ] Rebalance hedge contracts when portfolio grows > 20% (add contracts proportionally)

---

### Common Mistakes

1. **Buying puts right after a crash.** VIX spikes after crashes — puts become extremely expensive. The worst time to buy crash insurance is when everyone is panicking. The best time is when VIX is 12–15 and nobody is worried. Systematic monthly purchase solves this — you buy cheaply in low-vol periods.

2. **Selling the hedge when it's working.** During a crash, puts with 30+ days left have enormous time value. Many traders sell too early (after a 3% SPY decline) capturing minimal profit. Hold through the fear — the put earns most of its value during the worst 2–3 days of the crash.

3. **Using inverse ETFs (SQQQ, SH) instead of puts.** Inverse ETFs decay due to daily rebalancing — they're terrible long-term hedges. A $390 SPY put in January 2022 at $2.10 costs nothing if markets don't crash. SQQQ loses 1–2% monthly even in flat markets.

4. **Wrong portfolio coverage.** If your portfolio is 80% tech and you buy SPY puts, your tech holdings may fall 40% while SPY falls only 20% — your hedge provides half the protection you expected. Consider QQQ puts for tech-heavy portfolios.
