## Post-Earnings Drift (SUE Effect)

**In plain English:** When a company reports earnings that significantly beat analyst expectations, the stock tends to continue drifting higher for days or weeks after the announcement — not just gap up on the day. This is the "Standardized Unexpected Earnings" (SUE) effect, documented in academic research since the 1960s. The market underreacts to earnings surprises, and the drift is a slow catch-up.

---

### Why the Market Underreacts

Behavioral finance explains the post-earnings drift in two ways:
1. **Anchoring:** Analysts update their models slowly. Institutional investors wait for confirmation across multiple data points before committing capital.
2. **Limited attention:** Not all market participants see or process the earnings immediately. Capital flows in gradually over days and weeks.

The effect is strongest when:
- The earnings beat is large (top decile of surprise)
- Analyst consensus was especially wrong (crowded expectations)
- Guidance raised (signals the beat is sustainable)

---

### Real Trade Walkthrough

> **Date:** Jan 30, 2025 · **META earnings beat (after close Jan 29)**

**META reported:**
- EPS: $8.02 actual vs $6.75 estimate → **+18.8% beat**
- Revenue: $48.4B vs $46.98B → +3% beat
- Guidance raised for Q1 2025
- Stock gapped from $617 → $694 at open (+12.5%)

**The question:** Is there still drift upside after the gap?

**Historical SUE pattern for META (earnings beats > 15%):**
- Day 0 (earnings): +12.5% average gap
- Days 1–5 post-earnings: +2.1% additional drift
- Days 5–20: +1.3% additional drift
- Total 20-day post-earnings drift: **+3.4% on average**

**The trade (entered Jan 30 open at $694):**
- Buy Feb 21 $695 call (3 weeks out, ATM) → pay $12.80
- Sell Feb 21 $720 call (upside cap) → collect $4.20
- **Net debit: $8.60 = $860 per contract**
- Break-even: $695 + $8.60 = **$703.60**
- Max profit at $720: $25 − $8.60 = $16.40 = **$1,640**

**Feb 21 outcome (META at $748 — strong continued drift):**
- Spread worth $25 (max profit hit, META blew through cap)
- **Profit: $25 − $8.60 = $16.40 = $1,640 per contract (+191% in 3 weeks)**

| META at Feb 21 | P&L | Notes |
|---|---|---|
| $720+ | **+$1,640** | Max profit — strong drift |
| $710 | **+$690** | Good return |
| $703.60 | **$0** | Break-even |
| $695 | **−$860** | No drift from gap level |
| $680 | **−$860** | Gap partially faded |

---

### How to Quantify "Significant Beat"

**Standardized Unexpected Earnings (SUE) score:**
> SUE = (Actual EPS − Estimated EPS) / Standard Deviation of Analyst Estimates

- SUE > 2.0: Strong beat → high probability of drift
- SUE 1.0–2.0: Moderate beat → modest drift
- SUE < 1.0: Small beat → minimal drift (often "sell the news")
- SUE < 0: Miss → downward drift signal (bearish)

---

### Entry Checklist

- [ ] EPS beat > 10% of estimate OR SUE score > 1.5
- [ ] Revenue beat (not just EPS beat through cost-cutting)
- [ ] Guidance raised or maintained (not lowered)
- [ ] Stock in uptrend pre-earnings (momentum amplifies SUE drift)
- [ ] Large-cap, liquid options available (AAPL, META, NVDA, AMZN, MSFT, GOOGL)
- [ ] Enter at or near the open after earnings, not pre-market

---

### Common Mistakes

1. **Chasing the gap with a naked call.** If META gaps 12.5%, buying a call at the open means you've already missed the big move. The drift is typically 2–4% additional — buying a naked call risking $1,280 for a 2% drift is poor risk/reward. Use a call spread.

2. **Holding through the next earnings.** The SUE drift effect lasts 1–3 months — not forever. Once the next quarter approaches, IV spikes again and the dynamics change. Exit before the next earnings cycle.

3. **Ignoring guidance.** A company can beat EPS by 15% through cost cuts but lower guidance. In this case, the initial gap may be real but the drift reverses quickly as investors digest the weak forward outlook. Check guidance first.

4. **Applying to small-cap stocks.** Small-cap earnings drifts are often interrupted by low liquidity, wide bid-ask spreads, and analyst coverage gaps. The SUE effect is most reliable on S&P 500 and Nasdaq 100 members.
