## VIX Calendar Spread

**In plain English:** Buy a far-dated VIX call and sell a near-dated VIX call at the same strike. The near-term VIX call decays faster. If VIX stays stable, you profit from the faster decay of the short leg. If VIX spikes, the long back-month call provides significant upside (you're long volatility of volatility). It's a "have it both ways" structure — profits in calm AND crisis environments (but not in slow decay).

---

### Why VIX Options Have Unique Behavior

VIX futures have "mean-reversion on steroids":
- Front-month VIX futures are extremely sensitive to spot VIX moves
- Back-month futures are much less sensitive (spot vol spikes get "averaged out" over time)
- This creates a convexity: front-month options gain/lose value much faster

A VIX calendar exploits this by:
- Being short the sensitive (fast-decay, volatile) near-term option
- Being long the less sensitive (stable-value) back-month option

---

### Real Trade Walkthrough

> **Date:** Sep 12, 2025 · **Spot VIX:** 19.5 · **Oct VIX M1:** 20.8 · **Dec VIX M3:** 22.1

**The trade:**
- Sell Oct 21 VIX $22 call → collect $1.45
- Buy Dec 16 VIX $22 call → pay $2.80
- **Net debit: $1.35 = $135 per spread (each VIX option controls 100 shares at $100 multiplier)**

**Scenario 1 — VIX stays at 19.5 (calm market):**
- Oct 21: Short $22 call expires worthless (+$1.45)
- Dec $22 call: now worth $2.20 (still 55 days left, losing value slowly)
- **Net: $1.45 − $2.80 + $2.20 = +$0.85 = +$85**

**Scenario 2 — VIX spikes to 35 (fear event):**
- Oct 21 short call: now worth $13.50 (deep in the money) → loss of $12.05
- Dec $22 call: now worth $14.80 (back-month rises too, but less)
- **Net: $14.80 − $2.80 − $13.50 = −$1.50 = −$150** (small loss)

**Scenario 3 — VIX falls to 14 (very calm):**
- Both calls worth near zero
- **Net: −$135** (full debit lost — worst case in ultra-calm markets)

| VIX Scenario | P&L | Notes |
|---|---|---|
| Stable (18–21) | **+$85** | Theta advantage realized |
| Moderate spike (25–30) | **+$150–$250** | Back-month call gains from vol spike |
| Large spike (35+) | **−$50 to +$500** | Back-month outperforms front in big move |
| Collapse to 13 | **−$135** | Both calls worthless |

---

### Entry Conditions

- M1–M3 spread ≥ 1.5 vol points (calendar has value)
- VIX between 17–28 (below 17: not enough premium; above 28: calendar structure breaks)
- Not during sustained backwardation (M1 > spot VIX significantly)

---

### Common Mistakes

1. **Using calls when expecting a VIX spike.** If you think VIX is about to spike, buy VIX calls outright (or a bull call spread) — not a calendar. The calendar's short front-month leg will be very painful in a VIX spike.

2. **Ignoring early exercise on VIX options.** VIX options are European (no early exercise), but the settlement is based on a special calculation. Understand your broker's VIX settlement process before trading.

3. **Wrong multiplier math.** Each VIX option contract represents 100 shares, but the "share" price is 1 VIX point = $100. A VIX call at $2.00 costs $200, not $200 — confirm with your broker.
