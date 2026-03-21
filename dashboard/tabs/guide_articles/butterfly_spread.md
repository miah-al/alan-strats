## Butterfly Spread

**In plain English:** You bet the market stays near a specific price at expiry. You buy one call at a lower strike, sell two calls at your target (middle) strike, and buy one call at an equal distance above. The result is a tent-shaped payoff that peaks at the middle strike. Maximum profit if SPY pins exactly to your target. Cheap to enter, high max profit, but you need pinpoint accuracy.

---

### Real Trade Walkthrough

> **Date:** Wed Apr 9, 2025 · **SPY:** $520.00 · **Expiry:** Friday Apr 11 (2 DTE)

**Setup:** SPY is trading at $520 with large open interest at the $520 strike (50,000+ contracts). It's Wednesday afternoon — the market has been rangebound all week. Classic pinning setup heading into Friday expiry.

**The trade (Apr 11 expiry butterfly):**
- Buy 1× $515 call → pay $5.80
- Sell 2× $520 call → collect $3.20 × 2 = $6.40
- Buy 1× $525 call → pay $1.20
- **Net debit: $5.80 + $1.20 − $6.40 = $0.60 per share = $60 per contract**

**Payoff at expiry:**

| SPY at Expiry | Your P&L | Notes |
|---|---|---|
| $515 or below | **−$60** | All calls worthless. Full debit lost. |
| $516 | **+$40** | $1 intrinsic on long $515 call − $60 debit = $40 |
| $520.60 | **$0** | Lower break-even |
| $520 (pin!) | **+$440** | Max profit: $5 wing − $0.60 debit = $4.40 × 100 = $440 |
| $519.40 | **$0** | Lower break-even (symmetric) |
| $524 | **−$60** | Max loss (above upper wing) |

**Maximum profit: $440 on $60 risk — a 7:1 reward/risk ratio.** But this requires SPY to close within about $0.50 of $520 at Friday's close.

---

### When Butterflies Work Best

1. **High open interest at a round strike** — more pinning force from dealer hedging
2. **Low volatility environment** (VIX < 18) — market more likely to stay range-bound
3. **End of week or expiry** — pinning tendency strongest in final 24–48 hours
4. **Market already near the target strike** — don't try to predict a pin from 3% away

---

### Entry Checklist

- [ ] Large OI (50,000+) at a nearby round-number strike (e.g., $500, $520, $550)
- [ ] SPY currently within 0.5% of the target strike
- [ ] 1–3 DTE (the pinning effect only appears near expiry)
- [ ] VIX below 20
- [ ] No news events before expiry

---

### Common Mistakes

1. **Setting the middle strike too far from current price.** A butterfly centered on $530 when SPY is at $520 requires a 2% rally just to reach your peak profit zone. The edge disappears.

2. **Using too wide wings.** A $515/$520/$525 butterfly costs $60 and pays $440 max. A $510/$520/$530 butterfly costs $150 and pays $850 max — but your break-evens are wider, and SPY needs to stay within ±$4 of $520 for profit. Wider wings aren't automatically better.

3. **Holding through the weekend on a 5-DTE butterfly.** Time decay works FOR you (you sold 2 calls), but theta accelerates near expiry. A butterfly entered Monday for Friday expiry sees most of its value in the final 24 hours. Don't exit too early.

4. **Treating this as a primary strategy.** Butterfly win rates are 40–50% — you need near-exact pinning. This is a supplementary trade you size small (1–2 contracts) as a speculation on pinning, not a core income strategy.
