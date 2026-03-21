## 0-DTE Iron Condor (Same-Day Expiry)

**In plain English:** You sell a call spread and a put spread on SPY that both expire TODAY. You're collecting premium in the morning and hoping SPY stays in a tight range until the 4pm close. You never hold overnight. This is the highest-frequency, fastest-burning version of the iron condor — SPY now has daily options that expire every single trading day.

---

### Why 0-DTE Has Exploded in Popularity

Zero-days-to-expiry options (0DTE) on SPY now account for **over 50% of total SPX/SPY options volume** — more than all other expiries combined. Why? Three reasons:

1. **Theta decay is at maximum.** In the last day of an option's life, time decay accelerates sharply. Premium sellers get the fastest theta possible.
2. **Known holding period.** You enter at 9:45am, close by 3:45pm. No overnight gaps. No weekend risk.
3. **Defined risk.** As an iron condor (not naked), your max loss is fixed no matter what SPY does.

---

### Real Trade Walkthrough

> **Date:** Wednesday March 19, 2025 · **SPY Open:** $567.80 · **VIX:** 16.8

**Pre-trade check (9:30–9:45am):**
- VIX: 16.8 ✅ (below 25 cutoff)
- Pre-market futures: S&P500 down 0.1% — flat open ✅
- Economic calendar: No events today ✅ (no FOMC, no CPI)
- Recent SPY move: Rangebound ±0.5% past 3 days ✅
- Signal: ENTER

**The trade (placed at 9:45am):**

*Call spread (above market):*
- Sell Mar 19 $572 call (16-delta, 0.8% above open) → collect $1.15
- Buy Mar 19 $577 call (wing) → pay $0.30
- Call spread credit: **$0.85**

*Put spread (below market):*
- Sell Mar 19 $563 put (16-delta, 0.9% below open) → collect $1.05
- Buy Mar 19 $558 put (wing) → pay $0.25
- Put spread credit: **$0.80**

**Total net credit: $1.65 per share = $165 per contract**
**Max profit: $165 (SPY stays between $563 and $572)**
**Max loss: $5.00 − $1.65 = $3.35 = $335 per contract**
**Upper break-even: $572 + $1.65 = $573.65**
**Lower break-even: $563 − $1.65 = $561.35**

**SPY needs to stay between $561.35 and $573.65 — a $12.30 range (±1.1%) — for you to profit.**

**At 12:30pm — Mid-Day Check:**
- SPY: $568.90 (up 0.2% — still safely inside the tent)
- Condor is worth $0.72 (down from $1.65 collected)
- You've captured: ($1.65 − $0.72) / $1.65 = 56% of max profit
- **ACTION: Close it.** Buy the condor back for $0.72. Profit = **$93 per contract in 2 hours 45 minutes.**

**If you held to 3:45pm and SPY is at $570:**
- Both spreads expire worthless
- **Full profit: $165**

| SPY at 3:45pm | Your P&L | Notes |
|---|---|---|
| $567 (flat) | **+$165** | Full profit. Both spreads expire worthless. |
| $570 (up 0.4%) | **+$165** | Still inside tent. Full profit. |
| $573.65 | **$0** | Break-even — call spread barely in-the-money |
| $577 | **−$170** | Call spread partially breached |
| $577+ | **−$335** | Max loss — call wing hit |
| $561.35 | **$0** | Lower break-even |
| $556 | **−$335** | Max loss — put wing hit |

---

### Daily Ritual: The 0-DTE Decision Tree

```
9:30am: Market opens
  │
  ├── VIX > 25? ─────────────────► SKIP TODAY. Too volatile.
  │
  ├── Major event today (FOMC/CPI)? ► SKIP TODAY. Event = undefined risk.
  │
  ├── Pre-market gap > 1%? ──────► SKIP or wait for gap to resolve
  │
  └── All clear? ─────────────────► Wait 15 min for price discovery
                                        │
                                        ▼
                                   9:45am: Place condor
                                   Short strikes at 16-delta
                                   Wings $5 wide
                                   Target $0.80–$1.20 net credit
                                        │
                                   Mid-day check:
                                   50% profit? → Close
                                   One side < 5-delta? → Sell another 0DTE spread
                                   One side > 30-delta? → Close or adjust
                                        │
                                   3:30pm: Close if still open
                                   (never hold to expiry — pin risk)
```

---

### Entry Checklist

- [ ] VIX below 25 at 9:30am
- [ ] No scheduled economic events (FOMC, CPI, NFP, major FOMC speakers)
- [ ] No major SPY component reporting earnings today (check NVDA, AAPL, MSFT, AMZN)
- [ ] Pre-market S&P futures within ±0.4% of prior close
- [ ] Day is not a monthly options expiration Friday (third Friday — unusual behavior)

**Skip the day if any condition fails.** The premium you'd collect is not worth the tail risk of trading through a surprise event.

---

### Why "Close Early" Is the Right Move

The single best practice for 0-DTE condors is closing at **50% of max profit** rather than holding to expiry:

| Hold strategy | Expected Value (per trade) | Risk |
|---|---|---|
| Hold to expiry | +$165 × 70% win − $335 × 30% loss = **+$15.50** | High (pin risk, market-close spiking) |
| Close at 50% profit | +$82.50 × 80% capture rate = **+$66** average | Much lower (out before end-of-day chaos) |

By closing at 50% profit:
- You capture the bulk of premium in less time
- You avoid the final 90 minutes when market can be volatile
- You free up margin for the next day's trade sooner
- You eliminate assignment/pin risk entirely

---

### Common Mistakes

1. **Trading on FOMC days.** The Fed announcement at 2pm causes SPY to move 1–2% in seconds. Your 0-DTE condor's wings are only $5 wide. You will lose max loss almost guaranteed. No exceptions — skip FOMC days.

2. **Choosing $2.50-wide wings.** On a $2.50 spread with a $1.00 credit, your max loss is $1.50 per share. That's barely 1.5:1 risk/reward. A $5-wide spread for $1.65 credit gives you 2:1 risk/reward. The wing width determines your cushion.

3. **Selling the condor at market open.** The first 15 minutes are chaotic. Large orders, market maker positioning, news digestion — spreads are wide. Wait until 9:45am when things calm down. Discipline saves you $0.20–$0.40 in fill quality.

4. **Holding to 3:59pm.** The last minute of trading sees enormous volume as options market makers hedge positions and speculators make last-second bets. SPY can move $1–$2 in that final minute. Close by 3:30–3:45pm.

5. **Sizing too large too fast.** 0-DTE condors have a 25–30% loss rate. If you put on 20 contracts and have a max-loss day, that's $6,700 in losses — potentially more than a week of winning trades. Start with 1–3 contracts while learning.

---

### The Math Over 20 Trading Days

Assume: 15 win days at +$110 average (closed at 50%+), 5 loss days at −$275 average (max loss hit)

- Winning trades: 15 × $110 = +$1,650
- Losing trades: 5 × $275 = −$1,375
- **Net: +$275 per month per contract**
- On $5,000 capital (10 contracts), that's **5.5% per month** before commissions.
- Commissions matter: at $0.65/contract/side, a 4-leg condor costs ~$5.20 in commissions. Over 20 trading days × 10 contracts: $1,040/month in commissions alone. Use a low-cost broker (Tastytrade, IBKR).
