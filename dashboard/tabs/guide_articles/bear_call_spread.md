## Bear Call Spread (Credit Call Spread)

**In plain English:** The mirror image of the bull put spread — you're bearish or neutral. You sell a call above the current price and buy a further-out-of-the-money call as protection. You collect premium upfront and profit if SPY stays below your short call strike. Three ways to win: market goes down, stays flat, or goes up only a little.

---

### Real Trade Walkthrough

> **Date:** July 23, 2025 · **SPY:** $563.80 · **VIX:** 19.3 · **IV Rank:** 58%

**Market context:** SPY has rallied hard off the June lows and is now overbought — RSI(14) = 72, trading 4% above the 50-day MA. VIX elevated at 19 with IV rank at 58%. Earnings season in full swing but SPY-level events are sparse for the next 30 days. Bearish setup for a credit call spread.

**The trade (Aug 15 expiry — 23 DTE):**
- Sell Aug 15 $575 call (20-delta) → collect **$2.10**
- Buy Aug 15 $585 call (protection wing) → pay **$0.90**
- **Net credit: $1.20 per share = $120 per contract**
- Max profit: $120 (if SPY stays below $575)
- Max loss: ($585 − $575) − $1.20 = $8.80 = **$880 per contract**
- Break-even: $575 + $1.20 = **$576.20**

SPY is at $563.80. Your short call is $11.20 above current price. SPY needs to rally 2% to even touch your short strike. You have a wide cushion.

**At August 15 (23 days later):**

| SPY at Expiry | Your P&L | What Happened |
|---|---|---|
| $552 (−2%) | **+$120** | SPY pulled back. Both calls expire worthless. Max profit. |
| $563 (flat) | **+$120** | No move. Both calls expire worthless. Max profit. |
| $576 (+2.1%) | **−$0** | SPY just above break-even. Tiny loss. |
| $581 (+3%) | **−$480** | $6 of the call spread in the money |
| $585+ (+3.7%) | **−$880** | Max loss. Full $10 spread breached. |

**Day 14 check-in:** SPY is at $568 (up slightly). Your spread is worth $0.55 — you've captured $0.65 of the original $1.20 (54%). **Close it.** Profit: $65 per contract in 14 days.

---

### Entry Checklist

- [ ] SPY in short-term overbought territory (RSI > 65, or 3%+ above 50-day MA)
- [ ] IV Rank > 40% — selling expensive premium
- [ ] Short call at 15–25 delta (above current price)
- [ ] 21–45 DTE
- [ ] No FOMC or major catalyst in window
- [ ] Trend check: is the broader trend still up? (Be cautious selling calls in strong bull markets)

---

### P&L Table (1 contract, $120 credit, $880 max risk)

| SPY at Expiry | Spread Value | P&L | Notes |
|---|---|---|---|
| < $575 | $0 | **+$120** | Full profit |
| $576.20 | $1.20 | **$0** | Break-even |
| $578 | $3 | **−$180** | Short call in the money |
| $580 | $5 | **−$380** | Deep in the money |
| $585+ | $10 | **−$880** | Max loss |

---

### Common Mistakes

1. **Selling calls in a raging bull market.** If SPY is making new all-time highs every week and momentum is strong, don't fight the trend with bear call spreads. The market can stay overbought far longer than you can stay solvent.

2. **Forgetting that calls have unlimited theoretical risk without the wing.** Always buy the wing. A naked short call means unlimited loss potential if SPY gaps up on a surprise catalyst (Fed pivot, deal announcement, surprise CPI).

3. **Placing the short call too close (high delta).** A 35-delta short call has a 35% chance of ending in the money. If you collect $2.50 on a $10 spread, you're taking on $7.50 risk for $2.50 reward — that's a 3:1 risk/reward in the wrong direction. Use 15–20 delta.

4. **Not accounting for the upward drift in equities.** Markets go up over time. Selling bear call spreads as a systematic income strategy will underperform selling bull put spreads over a long bull market. Use this strategy in corrections or when specific overbought signals align.

---

### When Bear Call vs Bear Put Spread?

| Strategy | Use When | Type |
|---|---|---|
| Bear Call Spread | Neutral-to-bearish, want to collect premium | Credit spread — collect cash now |
| Bear Put Spread | Strongly bearish, want defined-risk downside bet | Debit spread — pay for directional bet |

If you think SPY will fall significantly, buy the **bear put spread** (directional bet).
If you think SPY will just stay flat or fall modestly, sell the **bear call spread** (income trade).
