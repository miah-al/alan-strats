## Tail Risk — Put Spread Hedge

**In plain English:** Instead of buying a naked OTM put, buy a put spread — buy a put at one strike and sell a put at a lower strike. The sold put reduces your premium cost dramatically. You give up protection below the lower strike (total wipeout protection gone) but capture the 15–30% decline range at much lower cost. For most real-world scenarios, the put spread is more capital-efficient than a naked put.

---

### Put Spread vs Naked Put: The Math

Both protecting against a $500,000 equity portfolio at SPY $477 (December 2021):

**Naked Put:**
- Buy Mar 2022 $405 put (15% OTM) → pay $4.20 = $420/contract

**Put Spread:**
- Buy Mar 2022 $405 put → pay $4.20
- Sell Mar 2022 $370 put → collect $1.80
- **Net cost: $2.40 = $240/contract (43% cheaper)**

| Scenario | Naked Put Payout | Put Spread Payout |
|---|---|---|
| SPY at $477 (no move) | −$420 (loss) | −$240 (loss) |
| SPY at $430 (−10%) | $0 (still OTM) | $0 (still OTM) |
| SPY at $405 (−15%) | +$0 (just ATM) | +$0 (at max profit start) |
| SPY at $390 (−18%) | +$1,500 | +$1,500 |
| SPY at $370 (−22%) | +$3,500 | **+$3,500 (max: capped here)** |
| SPY at $350 (−27%) | +$5,500 | **+$3,500 (still max, capped)** |
| SPY at $320 (−33%) | +$8,500 | **+$3,500 (still max, capped)** |

The put spread caps your profit at $3,500 per contract (the $35 width × 100). You lose the protection below $370. But you halved the cost. For a 20–25% market decline (most historical bear markets), the put spread captures essentially all the protection value at half the price.

---

### Sizing the Spread

**For a $500,000 portfolio (approximately 1,050 SPY shares at $477):**

To fully offset a 20% SPY decline ($95 × 1,050 = $99,750 expected loss):
- Each $405/$370 put spread pays max $3,500
- Need 28 contracts to offset $99,750 = $98,000 protection
- Cost: 28 × $240 = **$6,720** (vs $11,760 for naked puts)

That's 1.3% of portfolio annually ($6,720 for 3-month protection × 4 rolls = $26,880/year — too expensive)

**More practical sizing:**
- Hedge 50% of the loss: 14 contracts → $3,360 cost for 3 months
- Annual cost: ~$13,440 = 2.7% of portfolio (still high in low-vol periods)
- **Better: reduce during low-VIX periods, increase during elevated-VIX periods**

---

### VIX-Adaptive Hedge Sizing

Buy MORE protection when it's cheap (VIX low), LESS when expensive (VIX high):

| VIX Level | Hedge Size | Rationale |
|---|---|---|
| < 15 | 60–80% hedge | Puts are cheapest; buy aggressively |
| 15–20 | 40–60% hedge | Normal vol; standard allocation |
| 20–25 | 20–40% hedge | Getting expensive; trim |
| > 25 | 10–20% hedge | Expensive; crisis may already be priced in |

Counterintuitively, you hedge MORE when VIX is low (cheap insurance) and LESS when VIX is high (expensive and crisis already happening).

---

### Real Trade Walkthrough

> **Date:** December 15, 2021 · SPY: $465 · VIX: 17.8 (low)

**Portfolio:** $500,000. Concern: Fed policy uncertainty in 2022.

**Put spread (entered 60 DTE):**
- Buy 15× Feb 2022 SPY $400 put → pay $3.20 each = $4,800
- Sell 15× Feb 2022 SPY $370 put → collect $1.30 each = $1,950
- **Net cost: $2,850** (60 DTE, 15 contracts)

**January 2022:** SPY falls from $465 to $440. $400 put at $5.80, $370 put at $2.10. Spread worth $3.70.

**February 15, 2022 (expiry week):** SPY at $443. $400 put still OTM, spread worth $4.20.

Decision: SPY hasn't reached strike — roll or exit?

- Roll into March spread: sell the Feb spread for $4.20, buy Mar $400/$370 spread for $3.40
- **Net received on roll: $0.80/contract × 15 = +$1,200**

March 2022: SPY collapses to $415 mid-March. $400 put reaches ATM.

- March expiry: SPY at $435. $400 put worth $2.80 (SPY above strike — time value only)
- Exit: sell March spread for $2.00 total

**P&L:**
- Initial cost: $2,850
- Roll credit received: +$1,200
- Final sale: 15 × $2.00 × 100 = +$3,000
- **Net: $2,850 − $1,200 − $3,000 = −$1,050 total cost for 4 months of protection on a declining market**

The hedge was cheap given that SPY declined 12% during the holding period. The put spread didn't fully pay out because SPY didn't reach the $400 strike, but the rolls reduced net cost significantly.

---

### Entry Checklist

- [ ] Select strikes: long put 13–17% OTM, short put 20–25% OTM (7–10% spread width)
- [ ] Buy 60–90 DTE for good time value, roll when 30 DTE remains
- [ ] Size: 25–50% portfolio coverage for cost efficiency
- [ ] Check VIX: if VIX < 16, add extra contracts (cheap insurance window)
- [ ] Roll when spread has appreciated > 80% of max value (lock in most profit, reset hedge)

---

### Common Mistakes

1. **Using a too-narrow spread.** A $405/$395 put spread only pays $1,000 max but still costs $180/contract. The 50% width reduction destroys efficiency. Keep spread width at least $25–$35.

2. **Not rolling down in a bear market.** If SPY falls from $465 to $420 but your strikes are $400/$370 (still OTM), roll the spread down to $380/$350 to capture the next leg of decline at a lower cost basis. You need to actively manage the hedge, not just buy and forget.

3. **Over-hedging with too many contracts.** Buying 30 contracts creates $90,000 of notional protection but costs $7,200 in premium. If the market rallies, you've wasted $7,200 — that's 1.4% drag annually. Be disciplined about sizing.

4. **Forgetting to close before expiry.** In the final 2 days before expiry, out-of-the-money spread legs have almost zero bid price — you'll get $0.05 for a spread that should theoretically be worth $0.50. Close all spread positions by 5 days before expiry to avoid liquidity trap.
