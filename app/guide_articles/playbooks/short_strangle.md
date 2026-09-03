## Short Strangle (OTM Theta Harvesting)

### What It Is
A short strangle means selling an out-of-the-money call and an out-of-the-money put on the same underlying. You collect premium from both sides, betting the stock stays between your two strikes. Unlike an iron condor, you have no protective wings — your risk is theoretically unlimited on the call side and substantial on the put side (stock can go to zero). This is a high-probability trade that requires active management, margin, and discipline. It is best suited for experienced traders on low-volatility, range-bound underlyings.

### Real Trade Walkthrough
**Date:** February 3, 2025. SPY is at $600.00. VIX is 15.2, IV rank is 45%. You expect range-bound action.

You sell a 45 DTE strangle:
- **Sell** 1x SPY Mar 21 $620 call at $2.80 (delta 0.18)
- **Sell** 1x SPY Mar 21 $575 put at $3.10 (delta −0.18)
- **Total credit:** $5.90 per share = **$590 per strangle**
- **Upper breakeven:** $620 + $5.90 = **$625.90**
- **Lower breakeven:** $575 − $5.90 = **$569.10**
- **Margin requirement:** ~$10,000 per strangle (varies by broker)

You enter **2 strangles** = $1,180 credit, ~$20,000 margin.

### P&L Scenarios

| Scenario | SPY at Expiry | Call Value | Put Value | P&L per Strangle | Total P&L |
|----------|--------------|-----------|-----------|--------------------|-----------|
| **Win** — SPY at $605 | $605 | $0 | $0 | +$590 | **+$1,180** |
| **Partial loss** — SPY at $625 | $625 | $5.00 | $0 | −$410 | **−$820** |
| **Large loss** — SPY at $640 | $640 | $20.00 | $0 | −$1,410 | **−$2,820** |

### Entry Checklist
- [ ] IV rank > 40% (selling premium should be in rich-vol environments)
- [ ] Underlying is range-bound (no strong trend on daily chart)
- [ ] Short strikes at 15–20 delta each side
- [ ] DTE 30–50 days
- [ ] Sufficient margin for naked options
- [ ] No earnings or major events within the trade window
- [ ] Portfolio-level check: not over-concentrated in short vol

### Exit Rules
1. **Close at 50% of max credit** ($295 per strangle) — typically 15–20 days in
2. **Close at 21 DTE** regardless of profit (gamma ramp begins)
3. **Roll the tested side** if SPY approaches a short strike — roll out in time and further OTM
4. **Close entire position if SPY breaches a short strike by $3+** (momentum is against you)
5. **Close if VIX jumps above 25** — the vol regime has changed

### Key Parameters
| Parameter | Recommended Value | Why |
|-----------|------------------|-----|
| Short strike delta | 0.15–0.20 each | 70%+ probability of profit per side |
| DTE | 35–50 days | Maximizes theta/gamma ratio |
| Profit target | 50% of credit | Frees margin and avoids late-cycle risk |
| Portfolio allocation | Max 2–3 strangles per $100K | Naked options tie up margin and have tail risk |
| Rolling threshold | When short strike is breached | Do not wait — roll immediately for credit |

### Common Mistakes
1. **Not having enough margin.** Brokers can increase margin requirements during volatility spikes. Keep a 50% margin buffer.
2. **Selling strangles on individual stocks.** Single stocks can gap 20%+ on earnings. SPY and SPX are far more predictable.
3. **Ignoring the undefined risk.** "It probably won't happen" is not risk management. A 2020-style crash can turn a $590 credit into a $10,000+ loss.
4. **Not rolling early.** When SPY is $5 from your short strike with 30 DTE, the probability has shifted. Roll before it is tested, not after.
5. **Stacking too many short strangles.** Five strangles = $50K+ margin and catastrophic tail risk in a crash. Keep it small.
