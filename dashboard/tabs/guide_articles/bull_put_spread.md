## Bull Put Spread (Credit Put Spread)

**In plain English:** You're bullish on SPY (or at least neutral — you think it won't fall much). You sell a put and buy a cheaper put further below it. The sold put collects premium; the bought put caps your loss if you're wrong. You profit as long as SPY stays above your short put strike by expiry. This is one of the most popular strategies for income traders because you win even if the market goes sideways or up slightly.

---

### Why Traders Love This Structure

Unlike buying calls (where you need to be right about direction AND timing AND magnitude), the bull put spread gives you **three ways to win**:
1. SPY goes up ✅
2. SPY stays flat ✅
3. SPY goes down a little (but not below your short strike) ✅

You only lose if SPY falls significantly — past your break-even level. That's a wide margin of error.

---

### Real Trade Walkthrough

> **Date:** March 12, 2025 · **SPY:** $572.30 · **VIX:** 17.1 · **IV Rank:** 52%

**Market context:** SPY pulled back 2% over the last week to its 50-day MA at $570. Bounce expected. VIX elevated slightly — good time to sell premium. No major events for 3 weeks.

**The trade (April 4 expiry — 23 DTE):**
- Sell Apr 4 $560 put (20-delta) → collect **$2.45**
- Buy Apr 4 $550 put (protection wing) → pay **$1.20**
- **Net credit: $1.25 per share = $125 per contract**
- Max profit: $125 (if SPY stays above $560)
- Max loss: ($560 − $550) − $1.25 = $8.75 = **$875 per contract**
- Break-even: $560 − $1.25 = **$558.75**

SPY is at $572. Your short put is $12 below the current price. SPY needs to fall 2.3% just to reach your short strike, and another 1.25% more before you start losing money.

**Three weeks later (March 26, 17 days in):**

| SPY Level | Your Position Value | P&L | Action |
|---|---|---|---|
| $580 (up 1.3%) | Spread worth $0.45 | **+$80 (64% of max)** | Close early — great result |
| $572 (flat) | Spread worth $0.62 | **+$63 (50% of max)** | Close at 50% target |
| $562 (down 1.8%) | Spread worth $0.95 | **+$30** | Still profitable, monitor closely |
| $558 (down 2.5%) | Spread worth $1.25 | **$0 (break-even)** | Decision point — close or hold |
| $548 (down 4.2%) | Spread worth $2.10 | **−$85 loss** | Below break-even |
| $545 (down 4.8%) | Spread worth $8.75 | **−$875 (max loss)** | Both puts in the money |

**What actually happened:** SPY bounced off the 50-day MA and reached $578 by March 26. You close the spread for $0.38 debit. Profit: $125 − $38 = **$87 on $875 max risk** in 17 days. That's a 10% return on risk in under 3 weeks.

---

### Entry Checklist

- [ ] SPY is in an uptrend (price above 50-day MA, or strong support level nearby)
- [ ] IV Rank > 40% (you're selling premium — want it elevated)
- [ ] Short put at least 2 standard deviations below current price (use 15–25 delta)
- [ ] 21–45 DTE (gives theta time to work, but not so long you're exposed to events)
- [ ] VIX below 28 (above this, market moves are too volatile for comfort)
- [ ] No earnings or macro events within the expiry window for SPY holdings

---

### Exit Rules

| Condition | What to Do |
|---|---|
| 50% of max credit captured | **Close the spread.** This is the golden rule. |
| 21 DTE reached (if not yet 50%) | Close or accept the risk of holding to expiry |
| Short put delta exceeds 30 | Position is getting tested. Roll down or close. |
| SPY closes below your short put strike | Serious threat. Close or aggressively roll. |
| 200% max loss hit ($250 loss on $125 credit trade) | Emergency close. |

---

### P&L Table (1 contract, $125 credit, $875 max risk)

| SPY at Expiry | Spread Value | Your P&L | Notes |
|---|---|---|---|
| > $560 | $0 | **+$125** | Full profit — both puts worthless |
| $559 | $1 | **+$25** | Just above break-even |
| $558.75 | $1.25 | **$0** | Break-even exactly |
| $555 | $5 | **−$375** | Short put $5 in-the-money |
| $550 | $10 | **−$875** | Max loss — both strikes breached |
| < $550 | $10 (capped) | **−$875** | Max loss (long put caps further losses) |

---

### Selecting Your Strikes

**Short put delta guide:**
- **10-delta ($548 put):** Very far OTM, collect only $0.65. High probability of winning but tiny income. Good for portfolio protection, not income.
- **20-delta ($558 put):** The sweet spot. Collect $1.25–$2.50. ~80% probability of expiring worthless. This is the standard recommendation.
- **30-delta ($565 put):** Higher income ($2.50–$4.00 credit) but only ~70% probability. Larger position in the "pain zone."

**Wing width:**
- $5-wide spread: Limits max loss to $5 per share. Lower premium (credit spread is tighter).
- $10-wide spread: Higher premium, but $10 max loss. Better for lower-vol stocks.
- **Always buy the wing.** A naked short put has unlimited downside and margin requirements. The wing costs ~40% of the credit but caps your loss.

---

### Common Mistakes

1. **Selling the put too close to the current price (30+ delta).** A 30-delta put has a 30% chance of being in the money at expiry. That's too high. Stick to 15–25 delta for systematic selling.

2. **Not knowing what the max loss looks like in dollar terms.** On a 10-wide spread collecting $1.50, your max loss is $850 per contract. If you have 5 contracts, that's $4,250 at risk. Know this number before you enter.

3. **Selling bull put spreads in bear markets.** In 2022, every bouncer was a trap. Check the 200-day MA — if SPY is below it, be much more conservative with this strategy or switch to iron condors.

4. **Ignoring assignment risk near expiry.** If your short put is in-the-money at expiry, you may be assigned 100 shares of SPY. Most brokers auto-exercise, but know your broker's rules. Roll or close before expiry to avoid.

5. **Chasing premium on small-cap or illiquid options.** Bid/ask spreads of $0.50+ make these trades uneconomical. Stick to SPY, QQQ, IWM, or large-cap liquid underlyings.

---

### How This Differs from Buying Calls

| Aspect | Long Call | Bull Put Spread |
|---|---|---|
| Direction needed | Must go UP | Up, flat, or slightly down |
| Time decay | Hurts you | Helps you |
| Premium | You pay it | You collect it |
| Break-even | Strike + premium paid above current | Below current price |
| Win probability | ~35–40% | ~75–80% |
| Max profit | Unlimited (theoretically) | Fixed (credit received) |
| Max loss | Premium paid | Wing − credit |
