## Ratio Spread (1x2 — Buy 1, Sell 2 Further OTM)

### What It Is
A ratio spread involves buying one option and selling two options at a further OTM strike. The most common is the 1x2 call ratio spread: buy 1 ATM call, sell 2 OTM calls. The net cost is low (often zero or a small credit) because the two sold calls fund the one bought call. You profit if the stock moves moderately toward the short strikes but not beyond. If the stock moves too far up, you are effectively naked short one call — which has unlimited risk. This is an advanced strategy for traders expecting a specific target price.

### Real Trade Walkthrough
**Date:** January 22, 2025. SPY is at $607.00. You expect a modest rally to $615 but no further.

You enter a 1x2 call ratio spread:
- **Buy** 1x SPY Feb 14 $607 call at $6.20
- **Sell** 2x SPY Feb 14 $615 call at $2.80 each = $5.60
- **Net debit:** $6.20 − $5.60 = **$0.60 × 100 = $60**
- **Max profit:** ($615 − $607 − $0.60) × 100 = **$740** (if SPY at exactly $615)
- **Upside breakeven:** $615 + $7.40 = **$622.40** (beyond this, you lose)
- **Downside max loss:** $60 (the debit)

### P&L Scenarios

| Scenario | SPY at Expiry | Long Call Value | Short Calls Value (2x) | Net P&L |
|----------|--------------|----------------|------------------------|---------|
| **Sweet spot** — SPY at $615 | $615 | $8.00 | $0 | **+$740** |
| **Modest rally** — SPY at $612 | $612 | $5.00 | $0 | **+$440** |
| **Overshoot** — SPY at $625 | $625 | $18.00 | $20.00 | **−$260** |
| **Drop** — SPY at $600 | $600 | $0 | $0 | **−$60** |

### Entry Checklist
- [ ] Strong conviction on a specific price target (the short strike)
- [ ] Net debit ≤ $1.00 (ideally zero or credit)
- [ ] Short strikes at your price target
- [ ] Margin account with capacity for naked call risk above the upper breakeven
- [ ] DTE 20–35 days
- [ ] No earnings or events that could cause a gap beyond the upper breakeven

### Exit Rules
1. **Close at 50–70% of max profit** ($370–$520)
2. **Close if SPY breaks above $620** (approaching the danger zone)
3. **Close the extra short call** if SPY is at $615 with 5 DTE (convert to a vertical)
4. **Close entire position by 5 DTE** to manage gamma risk

### Key Parameters
| Parameter | Recommended Value | Why |
|-----------|------------------|-----|
| Ratio | 1:2 (never more) | Higher ratios = more naked risk |
| Spread width | $8–$10 | Gives a wide profit zone |
| Net cost | ≤ $1.00 debit or net credit | The low cost is the key advantage |
| DTE | 20–35 days | Time for the move but not excessive theta |
| Management point | SPY at short strike − $2 | Take profit before max profit or convert to vertical |

### Common Mistakes
1. **Forgetting about the naked risk.** The second short call is uncovered. If SPY rallies to $630, you lose $760+ and growing. Always have an upside stop.
2. **Using ratios greater than 1:2.** A 1:3 ratio has TWO naked calls. The risk is enormous. Stick to 1:2.
3. **Not converting when the stock approaches the short strike.** If SPY hits $615 with 10 DTE, buy back one short call to convert to a simple vertical. Lock in the profit.
4. **Placing the ratio spread directionally wrong.** If you are bullish, use a call ratio. If bearish, use a put ratio. Getting this backwards doubles your risk.
