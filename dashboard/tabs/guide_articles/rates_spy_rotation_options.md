## TLT / SPY Rotation — Options Variant

**In plain English:** The same four-regime framework as the base TLT/SPY Rotation strategy — but instead of holding ETF shares, every regime trade is executed with long calls or long puts. No short selling. No margin account required. Your maximum loss on any trade is the premium you paid, known from the moment you enter.

This is the retail-friendly version: defined risk, no broker restrictions, no assignment risk.

---

### Why Options Instead of Shares?

**The core problem with the share-based version for retail accounts:**

- **Inflation regime** requires reducing or shorting SPY — needs a margin account, exposes you to unlimited loss, and brokers may restrict short selling on volatile days.
- **Risk-On regime** wants heavy SPY + TLT simultaneously — requires capital for both, plus rebalancing friction.

**With long options:**
- Max loss = premium paid (e.g., 2% of portfolio per regime trade)
- No margin account needed for any position
- Leverage means a $2,000 options premium can capture the move of $100,000+ in notional value
- Clean entry/exit: you simply let options expire or close them when the regime changes

---

### Regime → Instrument Map

| Regime | Directional View | Instruments | Rationale |
|---|---|---|---|
| **Growth** (rates↑ + stocks↑) | Equities up, bonds flat | Buy SPY call, 1–3% OTM, 60 DTE | Ride the equity rally with leverage |
| **Risk-On** (rates↓ + stocks↑) | Equities up + bonds up | Buy SPY call + Buy TLT call | Both assets rise; own both with split budget |
| **Fear** (rates↓ + stocks↓) | Bonds up, equities down | Buy TLT call + Buy SPY put | Rates falling → TLT rises; equity sells off → SPY put profits |
| **Inflation** (rates↑ + stocks↓) | Both assets fall | Buy SPY put + Buy TLT put | Stocks drop AND bonds fall as rates rise — two legs, both win |
| **Transition** | Ambiguous | No new positions; existing positions stay open | Wait for regime clarity; closing prematurely locks in unnecessary losses |

---

### Trade Sizing: The Premium Budget Approach

Allocate a **fixed percentage of portfolio as premium per regime trade.** This is the total you can lose.

**Example — $100,000 portfolio, Inflation regime confirmed:**

```
SPY at $550. Inflation regime confirmed (3 consecutive days).
Premium budget: 2% × $100,000 = $2,000

Buy SPY $525 Put (5% OTM), 45 DTE
  → Option price: ~$6.50 per share × 100 = $650 per contract
  → Contracts: floor($2,000 / $650) = 3 contracts
  → Total cost: $1,950

Scenario A — SPY falls to $480 by expiry (−12.7% from entry):
  → Put value at expiry: $525 − $480 = $45 intrinsic
  → Proceeds: 3 × 100 × $45 = $13,500
  → Net profit: $13,500 − $1,950 = +$11,550 (+592% on premium)

Scenario B — SPY flat or up: options expire worthless → lose $1,950 (1.95% of portfolio)
```

The asymmetry is the point: you risk 2% to potentially make 10–20%+ if the regime call is right.

---

### DTE Strategy: How Far Out to Buy

Regimes are slow-moving (weeks to months), so you need enough time to be right.

| Regime | Typical Duration | Recommended DTE | Roll At |
|---|---|---|---|
| Inflation | 3–12 months | 60–90 DTE | 21 DTE |
| Fear | 1–3 months | 60 DTE | 21 DTE |
| Risk-On | 6–18 months | 60 DTE (monthly roll) | 21 DTE |
| Growth | 3–9 months | 60 DTE | 21 DTE |
| Transition | Days to weeks | No entry | — |

**Default is 60 DTE** — long enough to survive regime ambiguity without paying peak theta. Rolling at 21 DTE avoids the steepest theta decay window (the last 3 weeks of an option's life). The cost of the roll is the time value you pay on the new position minus the residual time value you sell on the old one.

**Transition pass-through:** When the regime enters Transition, existing positions are *not* closed. Transition is ambiguous noise, not a reversal. Positions only close when a new directional regime (Growth / Risk-On / Fear / Inflation) is confirmed.

---

### Real Trade Walkthrough

> **$100,000 portfolio · Inflation Regime (March 2022)**

**Signal confirmed March 1, 2022** (20-day yield change +51 bps, SPY 20d return −3.8%)

**Entry — March 3, 2022:**

| Trade | Strike | DTE | Price | Contracts | Cost |
|---|---|---|---|---|---|
| Buy SPY 430 Put | $430 (5% OTM) | 60 DTE | $7.20 | 4 | $2,880 |

SPY at entry: $448.20. Budget used: $2,880 (2.9% of capital).

**Roll — April 29, 2022** (SPY now at $415, 21 DTE remaining):

| Trade | Action | Strike | Price | Contracts | Proceeds/Cost |
|---|---|---|---|---|---|
| Close SPY 430 Put | Sell | $430 | $19.40 (ITM) | 4 | +$7,760 |
| Open SPY 395 Put | Buy | $395 (5% OTM, new) | $8.10 | 4 | −$3,240 |
| **Roll net** | | | | | **+$4,520** |

Running P&L after roll: +$4,520 − $2,880 initial = **+$1,640 realized**

**June 16, 2022** (SPY at $363.50, regime still Inflation):
- Open put (395 strike, 45 DTE remaining): $395 − $363.50 = $31.50 intrinsic + time value ≈ $34.00
- Unrealized: 4 × 100 × ($34.00 − $8.10) = **+$10,360**

**Total P&L through June 16:** +$1,640 (realized roll) + $10,360 (unrealized) = **+$12,000**

Capital committed: maximum $2,880 at any time (2.9% of portfolio).
**Return on premium: +416%**. Return on total portfolio: **+12.0%** in a period SPY fell 23%.

---

### Reading the VIX Overlay

The backtest regime chart shows VIX as a shaded red area (right axis) alongside 10Y yield and your allocations. Two reference lines are drawn at **VIX 20** and **VIX 30**.

| VIX Level | What It Means for This Strategy |
|---|---|
| < 20 | Calm market — options are cheap. Good time to open calls (Growth/Risk-On). |
| 20–30 | Elevated fear — puts cost 30–60% more than at VIX 15. Size down if entering Fear/Inflation. |
| > 30 | Crisis territory — puts have doubled or tripled in premium. Consider put spread instead of naked put. |

**The key insight:** When Fear or Inflation regime fires and VIX is already above 30, you're late to the put trade. The premium reflects the move that has already started. Your edge is better when you catch the regime early, before VIX spikes.

**Use the VIX chart to:**
- Spot regimes where you *would have* paid peak premium and adjust position size mentally
- Identify regime starts where VIX was still low — those are the highest-quality entries
- Understand why some Fear/Inflation trades underperformed even with the right direction: high IV at entry compressed returns

---

### The Inflation Regime Problem: Puts Are Expensive When You Need Them Most

VIX spikes precisely when you want to buy puts. In 2022, VIX went from 17 to 37 between January and March — put prices nearly doubled.

**Solution — put spread instead of naked put:**

```
Buy  SPY $430 Put  → pay $7.20
Sell SPY $400 Put  → receive $3.10
Net cost: $4.10 per spread (vs $7.20 for naked put)
Max profit: ($430 − $400) × 100 = $3,000 per contract
Breakeven: SPY below $425.90
```

Cost cut by 43%. You give up profit below $400, but in a normal Inflation regime (not a crash), SPY typically falls 15–25% — a $30-wide spread captures most of that move at lower cost.

---

### Risk-On Regime: The Two-Leg Trade

In Risk-On (rates falling + stocks rising), both SPY calls and TLT calls are profitable. Split the budget:

```
$100,000 portfolio. Risk-On confirmed December 14, 2022.
Budget: 2.5% = $2,500 total (split across two legs)

Leg 1: Buy SPY 405 Call (3% OTM), 45 DTE → $4.80 × 2 contracts = $960
Leg 2: Buy TLT 102 Call (2% OTM), 45 DTE → $1.90 × 8 contracts = $1,520
Total premium: $2,480

By January 31, 2023 (SPY +10%, TLT +8%):
  SPY 405 Call: SPY now at $403 → approaching ITM, value ~$8.50
  TLT 102 Call: TLT now at $107 → deeply ITM, value ~$5.80

  SPY leg P&L:  2 × 100 × ($8.50 − $4.80) = +$740
  TLT leg P&L:  8 × 100 × ($5.80 − $1.90) = +$3,120
  Total:        +$3,860 on $2,480 invested = +155% return on premium
```

---

### Entry Checklist

- [ ] Confirm regime (3 consecutive days) before opening any position
- [ ] Calculate premium budget: 1–3% of portfolio per trade
- [ ] Select DTE: minimum 60 days (regime needs time to play out)
- [ ] Select OTM%: 1–2% OTM — near-the-money means higher delta and faster profit when the move happens
- [ ] Check VIX level before opening — if VIX > 30, consider put spread instead of naked put to reduce premium cost
- [ ] Set calendar reminder at 21 DTE to evaluate roll
- [ ] Let take-profit (1.5×) and stop-loss (0.4×) rules manage exits — don't override them emotionally

---

### Common Mistakes

1. **Buying too short-dated options.** A 2-week option on a regime confirmation will lose to theta before the regime has time to pay off. Minimum 60 DTE for any regime trade.

2. **Over-allocating to premium.** Putting 10% of your portfolio into option premium per trade turns a diversified regime strategy into a high-risk bet. Keep each trade to 1–3% premium budget; the leverage does the rest.

3. **Panic-closing on Transition.** When the regime briefly flips to Transition, do *not* close your positions. Transition is ambiguous noise — the regime often resolves back to its prior direction within days. Only close when a confirmed *opposing* regime signal appears (e.g., Inflation → Risk-On). Early closure locks in theta losses for no reason.

4. **Ignoring VIX at entry.** Buying a naked put when VIX is 35 means you're paying for volatility that is already priced in. Check the VIX overlay in the regime chart — if VIX spiked before the regime confirmed, your edge is significantly reduced. Use a put spread to cut cost.

5. **Ignoring the bid-ask spread.** SPY options have tight bid-asks (~$0.01–0.05). TLT options are less liquid — expect $0.05–0.20 spreads. Factor this into your entry/exit pricing; always use limit orders at the mid-price or better.

6. **Treating Transition as an entry signal.** Transition = ambiguous rates and returns. Options bought in Transition will decay as the regime resolves. Wait for a clear Growth/Inflation/Fear/Risk-On classification before paying premium.
