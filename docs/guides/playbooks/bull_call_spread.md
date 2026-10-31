## Bull Call Spread (Debit Call Vertical)

### What It Is
A bull call spread is the simplest bullish options trade with defined risk. You buy a call at a lower strike and sell a call at a higher strike, both with the same expiration. You pay a net debit (the cost) and your maximum profit is capped at the width of the strikes minus the debit. If the stock rises above your upper strike, you keep the max profit. If it drops below your lower strike, you lose only the debit. It is a cost-effective way to be bullish without the full price of a naked call.

### Real Trade Walkthrough
**Date:** March 5, 2025. SPY is at $598.00. You expect a move to $610+ over the next 3 weeks based on strong breadth and a dovish Fed outlook.

You enter a bull call spread:
- **Buy** 3x SPY Mar 28 $600 call at $5.80
- **Sell** 3x SPY Mar 28 $610 call at $2.20
- **Net debit:** $3.60 per share = **$360 per contract × 3 = $1,080**
- **Max profit:** ($610 − $600 − $3.60) × 100 × 3 = $6.40 × 100 × 3 = **$1,920**
- **Max loss:** $1,080 (the debit paid)
- **Breakeven:** $600 + $3.60 = **$603.60**

### P&L Scenarios

| Scenario | SPY at Expiry | Spread Value | P&L per Contract | Total P&L (3) |
|----------|--------------|-------------|-------------------|--------------|
| **Win** — SPY at $615 | $615 | $10.00 | +$640 | **+$1,920** |
| **Partial** — SPY at $605 | $605 | $5.00 | +$140 | **+$420** |
| **Loss** — SPY at $595 | $595 | $0 | −$360 | **−$1,080** |

### Entry Checklist
- [ ] Bullish thesis with a specific price target above the short strike
- [ ] DTE 14–30 days (enough time for the move, not so much that you pay excess theta)
- [ ] Long strike at or slightly ITM (higher delta = more directional exposure)
- [ ] Short strike at or near your price target
- [ ] Debit ≤ 50% of spread width (risk/reward at least 1:1)
- [ ] IV rank < 50% (debit spreads are cheaper in low-vol environments)

### Exit Rules
1. **Close at 75% of max profit** — do not wait for expiry
2. **Close if thesis is invalidated** (breakdown below support, macro change)
3. **Time stop:** Close by 5 DTE to avoid expiry gamma risk
4. **Rolling:** If still bullish at 5 DTE, close and reopen further out in time

### Key Parameters
| Parameter | Recommended Value | Why |
|-----------|------------------|-----|
| Spread width | $5–$10 | Balances cost vs. profit potential |
| Long strike delta | 0.45–0.55 (ATM to slightly ITM) | Maximum directional sensitivity |
| DTE | 14–30 days | Sweet spot for directional moves |
| Debit as % of width | 30–45% | Risk/reward of 1.2:1 to 2:1 |
| Position size | 2–3% of account | Defined risk allows consistent sizing |

### Common Mistakes
1. **Setting the short strike too close.** A $600/$602 spread costs $1.40 to make $0.60 max. The risk/reward is inverted.
2. **Buying too far OTM.** A $610/$620 spread when SPY is at $598 is cheap but requires a 2%+ move just to break even.
3. **Not having a price target.** The short strike should represent your realistic upside target. If you think SPY goes to $610, that is your short strike.
4. **Holding through expiry.** Pin risk near the short strike can result in partial assignment. Close by noon on expiry day.
