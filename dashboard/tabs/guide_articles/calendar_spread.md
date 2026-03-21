## Calendar Spread (Time Spread)

**In plain English:** You sell a near-term option and buy the same strike in a further-out expiry. The near-term option decays faster than the far-term option — that difference in decay rate is your profit. You're exploiting the fact that time decay (theta) accelerates in the final weeks of an option's life, while longer-dated options still retain most of their value.

---

### The Theta Advantage

An option with 7 days left loses value much faster per day than an option with 60 days left. If SPY is at $570 and stays there:
- $570 call with 7 DTE: loses ~$0.30/day in time value
- $570 call with 60 DTE: loses ~$0.05/day in time value

The calendar spread captures this difference: you're short the fast-decaying near-term option and long the slow-decaying far-term option.

---

### Real Trade Walkthrough

> **Date:** May 12, 2025 · **SPY:** $572.00 · **VIX:** 17.5

**Market context:** SPY has been rangebound for 2 weeks between $565–$580. You expect it to continue sideways for 2–3 more weeks. VIX is moderate at 17.5 — not too cheap for the far-term option.

**The trade:**
- Sell May 23 $572 call (11 DTE) → collect **$2.40**
- Buy Jun 20 $572 call (39 DTE) → pay **$5.80**
- **Net debit: $3.40 per share = $340 per contract**

This is a debit trade — you pay upfront and profit from time passage. The sold call decays faster and eventually expires, leaving you with a longer-dated call you can roll or sell.

**At May 23 expiry (SPY still at $572):**
- Short May 23 $572 call expires worth $0 (collected $2.40, kept it all)
- Long Jun 20 $572 call still worth ~$4.10 (39 days ago it was $5.80, lost only $1.70)
- **Net position value: $4.10 (vs $3.40 paid)**
- **Profit: $0.70 = $70 per contract** — just from the theta differential

**What happens next:** You've "refreshed" your position. Now sell another near-term call against your June long, collecting more premium. This creates a rolling income stream.

| SPY at May 23 Expiry | Near-term call value | Far-term call value | Calendar P&L |
|---|---|---|---|
| $572 (flat) | $0 | $4.10 | **+$70** |
| $575 (up slightly) | $3 (ITM) | $6.20 | **+$2.20 − $3.40 = −$120** (short call tested) |
| $565 (down slightly) | $0 | $3.50 | **+$10** (small profit, far call lost more) |
| $550 (down 3.8%) | $0 | $2.20 | **−$120** (far call value declined) |

---

### Calendar Spread Sweet Spot

The calendar is most profitable when SPY closes **exactly at the short strike** at expiry. Moving in either direction hurts because:
- Moving UP: the short call goes in the money (loss), even though the long call gains too, the short usually gains faster near expiry
- Moving DOWN: the long call loses value faster than expected; both calls move toward worthlessness

---

### Entry Checklist

- [ ] Market in consolidation phase (rangebound past 10+ days)
- [ ] VIX between 14–25 (moderate vol — enough premium in short, affordable long)
- [ ] Short strike = ATM or very close (maximize theta differential)
- [ ] Near-term expiry 10–21 days out; far-term expiry 30–60 days out
- [ ] No events (earnings, FOMC) in the near-term window

---

### Common Mistakes

1. **Trading the calendar through the near-term expiry.** If SPY moves 2% toward expiry, the short call gains value fast (gamma spikes). Close before expiry, don't let it pin at an uncomfortable level.

2. **Ignoring the vega risk.** The long option has more vega than the short. If implied volatility drops (VIX falls), the long option loses more value than the short saves. Calendar spreads prefer stable or rising IV environments.

3. **Wrong expiry spacing.** If near-term is 3 DTE and far-term is 7 DTE, there's not enough theta differential to make the trade worthwhile. Use at least a 3-week gap between expiries.

4. **Not rolling.** The calendar isn't a "set it and forget it" trade. After the near-term expires, you have a naked long call that needs to be paired again with a new short. Active management is required.
