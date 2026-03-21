## Broken Wing Butterfly (BWB)

**In plain English:** A standard butterfly has symmetrical wings. The broken wing butterfly intentionally has one wider wing, making it asymmetric. This lets you structure the trade for ZERO cost (or even a credit) while still having a substantial profit zone — at the cost of more downside risk on one side. It's one of the most capital-efficient structures available.

---

### Standard Butterfly vs Broken Wing

| Feature | Standard Butterfly | Broken Wing Butterfly |
|---|---|---|
| Wings | Equal width (e.g., $5/$5) | Unequal (e.g., $5/$10) |
| Cost | Debit ($0.60–$1.50) | Zero or small credit |
| Risk | Debit on both sides | More risk on one side |
| Best use | Pinning to exact strike | Directional + income |

---

### Real Trade Walkthrough

> **Date:** Jun 16, 2025 · **SPY:** $554.00 · **Bias:** Mildly bullish

**Broken Wing Butterfly (skipped put wing wider):**
- Buy 1× $555 call → pay $4.20
- Sell 2× $560 call → collect $2.30 × 2 = $4.60
- Buy 1× $570 call (wide wing, 2× normal distance) → pay $0.80
- **Net: $4.20 + $0.80 − $4.60 = $0.40 credit received** ← You receive premium!

Maximum profit if SPY pins at $560: ($560 − $555) − $0 = **$5 × 100 = $500 + $40 credit = $540**

**The asymmetric risk:**
- If SPY falls below $555 (all calls expire): **keep the $40 credit** (small win)
- If SPY pins at $560: **+$540** (max profit)
- If SPY rallies past $570: loss on the wide wing = ($570 − $560) − ($560 − $555) − credit = **−$460**

| SPY at Expiry | P&L |
|---|---|
| < $555 | **+$40** (credit kept) |
| $555 | **+$40** |
| $558 | **+$340** |
| $560 (pin) | **+$540** |
| $565 | **+$40** |
| $570 | **+$40** |
| $575 | **−$460** |
| $580 | **−$460** (max loss capped) |

The BWB is structured for the case where you have a mild bullish bias (don't expect a big rally above $570) and want to collect a credit while keeping significant profit potential if SPY is near $560.

---

### When to Use Broken Wing Butterflies

1. **Mild directional bias** — you think SPY will go up slightly (or stay flat) but NOT rally aggressively
2. **Low IV environment** — standard credit spreads pay poorly; BWB generates income with better profit potential
3. **Near an expected pin level** — if you see heavy open interest at a nearby strike

---

### Common Mistakes

1. **Forgetting about the skewed risk.** The $570 wide wing means unlimited (well, up to the wing) loss if SPY rallies hard. The BWB trades the "big rally" scenario for better structure everywhere else. Make sure you're comfortable with that trade-off.

2. **Not setting a stop on the wide wing.** If SPY approaches your wide wing strike, close the entire trade. Don't let the "I collected a credit" psychology keep you in a losing trade.

3. **Using too wide a strike gap.** On a $554 SPY, a $555/$560/$580 BWB has the wide wing 26 points out — it would collect very little credit and have extreme asymmetry. Keep the wide wing at most 2× the narrow wing width.
