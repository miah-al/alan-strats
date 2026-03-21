## Zero-Cost Collar

**In plain English:** You own SPY and want to protect against a big drop — but you don't want to pay for insurance out of pocket. The collar solution: buy a put below the market (protection) and sell a call above the market (cap your gains). The call sale funds the put purchase, making the hedge nearly free. You trade unlimited upside for a band of defined outcomes.

---

### Real Trade Walkthrough

> **Date:** June 2, 2025 · **SPY:** $544.00 · **Portfolio:** 200 shares of SPY ($108,800)

**Goal:** Protect against a drop > 5% heading into a volatile summer.

**The trade (Jul 18 expiry, 46 DTE):**
- Buy Jul 18 $517 put (5% OTM protection) → pay $3.20
- Sell Jul 18 $561 put call (3.1% OTM cap) → collect $3.10
- **Net cost: $0.10/share = $10 per 100 shares — nearly free**

**Your outcome band:**
- Below $517: Protected — put kicks in, losses capped at 5%
- $517–$561: Full P&L follows SPY
- Above $561: Gains capped — shares called away at $561

| SPY at Jul 18 | Without Collar | With Collar |
|---|---|---|
| $585 (+7.5%) | **+$8,200** | **+$3,400** (capped at $561) |
| $561 (+3.1%) | +$3,400 | **+$3,400** (identical) |
| $544 (flat) | $0 | **$0** |
| $517 (−5%) | **−$5,400** | **−$540** (protected!) |
| $490 (−9.9%) | **−$10,800** | **−$540** (still protected) |
| $450 (−17.3%) | **−$18,800** | **−$540** (protection held) |

The collar converted a potential −$18,800 loss into just −$540. The cost: capped at +$3,400 instead of unlimited upside.

---

### When to Use a Collar

- Portfolio heavily weighted to equities entering uncertain period
- Approaching major binary event (election, FOMC, earnings season)
- Recent strong rally — locking in gains while maintaining exposure
- Running high P&L that you want to protect without selling

---

### Entry Checklist

- [ ] Long equity position you want to protect
- [ ] High IV Rank (> 50%) — expensive calls fund cheap puts better
- [ ] Put strike: 3–7% OTM depending on risk tolerance
- [ ] Call strike: far enough OTM to sacrifice acceptable upside
- [ ] Net cost ≤ $0.20/share (near-zero)
- [ ] 30–60 DTE

---

### Common Mistakes

1. **Selling the call too close.** If you sell a 1% OTM call when SPY is rallying, you'll be called away almost immediately. Give yourself 3–5% upside room.

2. **Using it as a permanent hedge.** Rolling the collar every month is essentially a zero-cost hedge fund fee. Over 10 years, the capped upside significantly reduces long-term wealth. Use only during high-risk periods, not permanently.

3. **Not understanding the psychological cost.** If SPY rallies 15% after you collared at +3%, you'll feel terrible even though you protected the downside. Be mentally prepared for this outcome before entering.
