## Statistical Arb — Index Reconstitution

**In plain English:** When a stock is added to the S&P 500 (or removed), index funds must buy (or sell) that stock to match the index. The announcement is public 5–7 days before the effective date. This creates a predictable price pressure event: announced additions typically rise 3–8% from announcement to effective date, then partially give back. This strategy buys additions immediately after announcement and shorts removals, then exits near the effective date.

---

### The Mechanics of Index Reconstitution

S&P 500 reconstitution follows a predictable schedule:

1. **Announcement:** S&P announces additions/deletions after market close (typically a Thursday)
2. **Effective date:** The change takes effect 5 trading days later (following Thursday after close)
3. **Index fund buying:** Funds tracking SPX must buy the addition on the effective date close (market-on-close orders)

**Why prices move up BEFORE the effective date:**
- Speculators buy the addition immediately after announcement
- Active funds buy early to avoid paying the MOC price spike
- ETF arbitrageurs pre-position

**The "fast money exit":** Near the effective date, institutional buyers (index funds) finally buy at the close — providing liquidity to all the speculators who bought earlier. Smart money sells into this buying.

---

### Historical Statistics

Average announcement-to-effective return for S&P 500 additions:

| Year | Avg Pre-Effective Return | Avg Post-Effective Return (next month) |
|---|---|---|
| 2020 | +8.2% | −3.1% |
| 2021 | +5.7% | −2.8% |
| 2022 | +3.4% | −1.9% |
| 2023 | +4.1% | −2.3% |
| 2024 | +3.8% | −1.7% |

The pre-effective return has been decreasing over time as more capital chases the same trade. Still, 3–5% in 5 days with known timing is compelling.

---

### Real Trade Walkthrough

> **Announcement:** November 28, 2023 (after close). CrowdStrike (CRWD) added to S&P 500, effective December 4, 2023.

**November 29, pre-market:** CRWD opens at $245 (up from $237 close — already +3.4% gap up)

**Trade consideration:** Buy at open or wait for pullback?

Strategy: Buy at market open in the first 30 minutes if the gap is < 5%. A >5% gap-open often means the easy money is gone.

**Entry:** Buy 100 shares CRWD at $244.80 (first 10 minutes of trading)

**Position management:**
- Day 1 (Nov 29): +2.1% → hold
- Day 2 (Nov 30): +1.8% → hold (total +3.9%)
- Day 3 (Dec 1): −0.8% → hold
- Day 4 (Dec 4 pre-market): +1.2% → ALERT: effective date today
- **Exit target:** Sell before 3:50pm (before the 4pm MOC rush)

**Exit:** Sell 100 shares at $253.40 (2:30pm on Dec 4)

**P&L:** $253.40 − $244.80 = $8.60 × 100 = **+$860 in 5 days**

**What happened after effective date:** CRWD fell from $254 (MOC close) to $241 over the next 3 weeks as index-buying pressure completely reversed.

---

### The Removal Play (Short Side)

S&P 500 removals are less clean but still tradeable:

- Announced removal → index funds MUST sell on effective date
- Speculators short immediately after announcement
- Average announcement-to-effective return: −4 to −6%

**Risk:** Removed stocks are often in distress (falling prices, restructuring). Short interest is already elevated. Risk of short squeeze. Harder to borrow. Generally skip the short side unless the fundamental case is clear.

---

### Russell Reconstitution (Better Opportunity)

Russell 2000 rebalances once per year in late June (rank day is last Friday of May, effective last Friday of June). This creates MASSIVE predictable flows:

- **Stocks graduating to Russell 1000** (large enough to exit Russell 2000): Russell 2000 funds SELL them, Russell 1000 funds BUY
- **Stocks entering Russell 2000** (new additions): Russell 2000 funds buy, small but predictable

**Key dates:**
- Rank day (~May 30): preliminary additions/deletions known
- Effective day (~June 28): final changes

Additions to Russell 2000 average **+8–12% from rank day to effective day** in historical data, with a strong reversal after. The reverse-direction trade (short after effective date) often works better for Russell than S&P 500.

---

### Entry Checklist

- [ ] Identify announcement (S&P typically announces after Thursday close, effective following Thursday)
- [ ] Calculate initial gap-open move — if already >5% at open, consider skipping
- [ ] Buy within first 30 minutes of Day 1 (Friday after announcement)
- [ ] Exit by 2:00–3:00pm on the effective date (before MOC buying drives the final spike)
- [ ] For Russell additions: same structure but expect larger absolute moves and larger reversal

---

### Common Mistakes

1. **Holding through the effective date close.** The MOC price is the TOP of the trade. Index funds must buy at the close — they pay the highest price. If you hold through 4pm, you sold your shares to the index fund at the exact right price. But don't try to squeeze out the last penny by holding — liquidity gets thin after 3:30pm.

2. **Ignoring market cap size.** A $50 billion addition to S&P 500 has a much smaller percentage impact than a $5 billion addition (because index funds need to buy proportionally less). Smaller additions move more on the same announcement.

3. **Being too greedy on pullback entry.** If CRWD gaps up 3% at open, placing a limit order 1% below to buy the pullback often results in missing the trade entirely. The announcement trade has known positive momentum — execute at market or use a tight limit (0.2–0.3% below current price).

4. **Trading both the addition and removal simultaneously.** The addition trade is much cleaner. Removals require short borrowing, have squeeze risk, and the negative momentum often begins before announcement. Focus on additions unless you have strong fundamental conviction on the removal.
