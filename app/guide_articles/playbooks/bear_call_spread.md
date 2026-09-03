## Bear Call Spread (Credit Call Vertical)

### What It Is
A bear call spread is the bearish version of the bull put spread. You sell a call at a lower strike and buy a call at a higher strike, collecting a net credit. You profit when the underlying stays below your short call strike. This is the trade to use when you think a stock or index has rallied too far and is unlikely to go higher — or at least not much higher — before expiry. Your profit is the credit collected and your loss is capped at the spread width minus the credit.

### Real Trade Walkthrough
**Date:** February 24, 2025. SPY has rallied to $605.00 and you believe it is near resistance. VIX is 14.5, IV rank 35%.

You sell a bear call spread:
- **Sell** 4x SPY Mar 21 $612 call at $2.40 (delta 0.22)
- **Buy** 4x SPY Mar 21 $617 call at $1.30
- **Net credit:** $1.10 per share = **$110 per contract × 4 = $440**
- **Max loss:** ($617 − $612 − $1.10) × 100 × 4 = $3.90 × 100 × 4 = **$1,560**
- **Breakeven:** $612 + $1.10 = **$613.10**

### P&L Scenarios

| Scenario | SPY at Expiry | Spread Value | P&L per Contract | Total P&L (4) |
|----------|--------------|-------------|-------------------|--------------|
| **Win** — SPY at $608 | $608 | $0 | +$110 | **+$440** |
| **Partial** — SPY at $615 | $615 | $3.00 | −$190 | **−$760** |
| **Max loss** — SPY at $620 | $620 | $5.00 | −$390 | **−$1,560** |

### Entry Checklist
- [ ] Bearish or neutral thesis (resistance level, overbought RSI > 70, etc.)
- [ ] Short call strike above a resistance level
- [ ] IV rank > 30% (adequate premium)
- [ ] DTE 25–45 days
- [ ] Credit ≥ 20% of spread width
- [ ] Not fighting a strong uptrend (check 20-day MA slope)

### Exit Rules
1. **Close at 50% of credit** ($55 per contract)
2. **Close at 21 DTE** if not profitable
3. **Roll up and out** if SPY breaks through the short call strike
4. **Close if SPY is > $2 above short strike** with 15+ DTE remaining

### Key Parameters
| Parameter | Recommended Value | Why |
|-----------|------------------|-----|
| Short call delta | 0.20–0.30 | Balances probability and premium |
| Spread width | $5 | Standard risk unit |
| DTE | 30–45 days | Optimal theta |
| Credit target | ≥ 20% of width | Minimum acceptable risk/reward |
| Position size | 2–3% of account at max risk | Conservative sizing |

### Common Mistakes
1. **Selling bear calls in a raging bull market.** Trends persist longer than expected. Wait for signs of exhaustion.
2. **Short strike too close to current price.** Selling a $607 call when SPY is at $605 gives high premium but 50%+ chance of loss.
3. **Not having a plan for a breakout.** If SPY gaps above your short strike on news, you need to close immediately, not hope.
4. **Over-concentrating in bear call spreads.** If the market rallies, all your positions lose simultaneously. Diversify with bull put spreads too.
