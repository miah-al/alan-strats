## ATM Butterfly (Expiry Pin)

**In plain English:** On expiry Friday, SPY often "pins" to a nearby strike with large open interest — market maker delta hedging creates a mechanical gravitational pull toward that level. This strategy buys a cheap ATM butterfly in the morning expecting SPY to close right at the middle strike by 4pm.

---

### The Pinning Mechanism

When large open interest exists at a strike (say $570 on a busy expiry Friday), market makers who are short those options must delta-hedge:
- As SPY approaches $570, dealers' options go toward delta 0.5 — they hold lots of short stock/calls
- This hedging activity itself creates buying pressure UNDER $570 and selling pressure ABOVE
- Result: SPY gets "pinned" at $570 like a magnet

This is most powerful when:
- OI at the strike is 5× higher than surrounding strikes
- It's an expiry Friday (max gamma)
- SPY is already within 0.5% of the strike by noon

---

### Real Trade Walkthrough

> **Date:** Friday Mar 21, 2025 (quarterly expiry) · **SPY:** $569.40 at 11am

**Check OI at nearby strikes:**
- $565 strike: 28,000 contracts
- $570 strike: **112,000 contracts** ← Heavy OI
- $575 strike: 31,000 contracts

SPY at $569.40 — 0.1% below the heavy $570 strike. Classic pin setup.

**The trade (entered 11:15am):**
- Buy 1× $565 call (March 21) → pay $4.50
- Sell 2× $570 call → collect $1.90 × 2 = $3.80
- Buy 1× $575 call → pay $0.60
- **Net debit: $4.50 + $0.60 − $3.80 = $1.30 = $130 per contract**
- Max profit at $570: $5 − $1.30 = $3.70 = **$370**

**At 3:55pm:** SPY closes at $570.20 — pinned!
- Butterfly at maximum value
- **Profit: $370 − $130 = $240** (leaving some time value)
- Or hold to 4pm expiry: **+$370** if SPY exactly at $570

| SPY at 3:55pm | P&L |
|---|---|
| $570 (pin!) | **+$370** |
| $571 | **+$270** |
| $572 | **+$170** |
| $574 | **−$30** |
| $576 | **−$130** |
| $565 | **−$130** |

---

### Entry Checklist

- [ ] Quarterly or monthly expiry Friday (strongest pinning)
- [ ] One strike with 3× or more OI vs adjacent strikes
- [ ] SPY within 0.5% of the high-OI strike by 11am
- [ ] Buy butterfly centered on the high-OI strike
- [ ] Only 1–3 contracts (precision trade, small size)

---

### Common Mistakes

1. **Entering too early.** Pinning only manifests in the last 2–3 hours. Enter after 10:30am when the day's trend is established.

2. **Wrong target strike.** Don't pick the strike you *think* SPY will pin to — pick the one with the highest open interest. The pin is mechanical, not directional.

3. **Over-sizing.** This trade wins ~40–50% of the time. Even when it wins, SPY might pin to $569.50 instead of $570 exactly, giving you only partial profit. Keep it to 1–3 contracts.
