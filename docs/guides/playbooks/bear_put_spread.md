## Bear Put Spread (Debit Put Vertical)

### What It Is
The bear put spread is the mirror image of the bull call spread — a defined-risk bearish trade. You buy a put at a higher strike and sell a put at a lower strike. You pay a net debit and profit when the underlying drops below your long strike. Max profit is the spread width minus the debit if the underlying closes below the short strike at expiry. It is the cleanest way to bet on a decline with known, limited risk.

### Real Trade Walkthrough
**Date:** April 2, 2025. SPY is at $580.00. Tariff concerns and weakening breadth make you bearish. You expect SPY could drop to $560 within 3 weeks.

You enter a bear put spread:
- **Buy** 4x SPY Apr 25 $580 put at $7.50
- **Sell** 4x SPY Apr 25 $570 put at $4.20
- **Net debit:** $3.30 per share = **$330 per contract × 4 = $1,320**
- **Max profit:** ($580 − $570 − $3.30) × 100 × 4 = $6.70 × 100 × 4 = **$2,680**
- **Breakeven:** $580 − $3.30 = **$576.70**

### P&L Scenarios

| Scenario | SPY at Expiry | Spread Value | P&L per Contract | Total P&L (4) |
|----------|--------------|-------------|-------------------|--------------|
| **Win** — SPY at $565 | $565 | $10.00 | +$670 | **+$2,680** |
| **Partial** — SPY at $575 | $575 | $5.00 | +$170 | **+$680** |
| **Loss** — SPY rallies to $590 | $590 | $0 | −$330 | **−$1,320** |

### Entry Checklist
- [ ] Bearish thesis: technical breakdown, deteriorating breadth, or macro headwind
- [ ] DTE 14–30 days
- [ ] Long strike at or near ATM
- [ ] Short strike at or near your downside target
- [ ] Debit ≤ 40% of spread width
- [ ] VIX not already > 30 (puts are expensive in high-vol; consider credit spreads instead)

### Exit Rules
1. **Close at 75% of max profit**
2. **Stop-loss:** Close if SPY rallies 2% above entry price (thesis broken)
3. **Time stop:** Close by 5 DTE
4. **If VIX spikes > 30** and you are profitable, close — vol expansion has helped but won't continue

### Key Parameters
| Parameter | Recommended Value | Why |
|-----------|------------------|-----|
| Spread width | $10 | Provides substantial profit potential |
| Long strike | ATM or slightly ITM | Higher delta for directional participation |
| DTE | 14–30 days | Enough time for the move |
| Debit as % of width | 25–40% | 1.5:1 to 3:1 reward/risk |
| Position size | 2–3% of account | Standard risk budgeting |

### Common Mistakes
1. **Buying bear puts in a strong uptrend.** Fighting the trend is expensive. Wait for the first lower high before entering.
2. **Using puts that are too far OTM.** A $560/$550 spread when SPY is at $580 needs a 3.5% drop just to break even.
3. **Not considering a credit spread instead.** In high-IV environments, selling a bull call spread (bearish credit spread) is often better than buying a bear put spread.
4. **Panicking on a bounce.** SPY rarely drops in a straight line. Small bounces within a downtrend are normal. Trust your thesis and timeline.
