## Iron Condor (Standard 4-Leg SPY/SPX Strategy)

### What It Is
An iron condor is a combination of two credit spreads: a bull put spread below the market and a bear call spread above it. You are betting the underlying stays within a range by expiry. You collect premium from both sides and keep it all if the price stays between your two short strikes. It is the options equivalent of saying "I think SPY will trade in a $20 range for the next month" and getting paid for that prediction. Your risk is capped on both sides by the long options.

### Real Trade Walkthrough
**Date:** December 2, 2024. SPY is at $602.00. VIX is 13.8. IV rank is 32%. You expect low volatility to persist through the holidays.

You sell a 30 DTE iron condor (Jan 3, 2025 expiry):
- **Sell** 1x SPY Jan 3 $615 call at $1.85 (delta 0.16)
- **Buy** 1x SPY Jan 3 $620 call at $1.10
- **Sell** 1x SPY Jan 3 $588 put at $1.95 (delta −0.16)
- **Buy** 1x SPY Jan 3 $583 put at $1.25
- **Call spread credit:** $0.75
- **Put spread credit:** $0.70
- **Total credit:** $1.45 per share = **$145 per iron condor**
- **Max loss per side:** $5.00 − $1.45 = $3.55 × 100 = **$355**
- **Breakeven range:** $586.55 to $616.45

You enter **5 contracts** → credit = $725, max loss = $1,775.

### P&L Scenarios

| Scenario | SPY at Expiry | P&L per Contract | Total P&L (5 contracts) |
|----------|--------------|-------------------|------------------------|
| **Win** — SPY at $600 (inside range) | $600.00 | +$145 | **+$725** |
| **Partial loss** — SPY at $617 (call side tested) | $617.00 | −$55 | **−$275** |
| **Max loss** — SPY at $625 (call side blown) | $625.00 | −$355 | **−$1,775** |

### Entry Checklist
- [ ] IV rank > 25% (some premium richness needed)
- [ ] VIX < 25 (avoid selling condors in a high-vol crash environment)
- [ ] DTE 30–45 days
- [ ] Short strikes at 15–20 delta each side (~70% POP)
- [ ] No major event (earnings, FOMC) within the condor's life
- [ ] Credit collected ≥ 25% of wing width ($1.25+ on $5-wide)

### Exit Rules
1. **Close at 50% of max credit** ($72.50 per contract) — typically within 10–15 days
2. **Close if one side is breached** (SPY touches a short strike) — defend or close the tested side
3. **Roll the untested side** closer to collect additional credit if one side is threatened
4. **Close by 10 DTE** regardless — gamma risk increases sharply
5. **Max loss exit:** If the spread reaches $3.00 (out of $5 max), close for a $1.55 loss

### Key Parameters
| Parameter | Recommended Value | Why |
|-----------|------------------|-----|
| Wing width | $5 on SPY | Standard risk per side, good liquidity |
| Short strike delta | 0.15–0.20 each side | 65–75% probability of profit |
| DTE | 30–45 days | Optimal theta decay zone |
| Credit target | ≥ 25% of wing width | Ensures adequate risk/reward |
| Max concurrent condors | 3–5 across different expirations | Diversify timing risk |
| Profit target | 50% of credit | Increases win rate from ~70% to ~85% |

### Common Mistakes
1. **Selling condors in trending markets.** If SPY is trending strongly in one direction, the directional side will be tested. Condors work best in range-bound conditions.
2. **Not managing the tested side.** "Hoping" SPY bounces back is not a plan. If SPY is at your short put with 20 DTE, close the put spread and keep the call spread.
3. **Making the wings too narrow.** A $2-wide iron condor collects $0.50 but risks $1.50. One loss wipes 3 winners. Use $5 minimum.
4. **Holding through a VIX spike.** If VIX jumps from 14 to 25, your condor's value has exploded against you. Close and reassess.
