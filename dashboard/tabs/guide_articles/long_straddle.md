## Long Straddle

**In plain English:** You buy both a call and a put at the same strike on the same expiry. You don't know (or don't care) which direction the market will move — you just believe it's going to move BIG. You make money if SPY moves far enough in either direction to cover the cost of both options. If the market stays flat, you lose the entire premium paid.

---

### When You'd Use This

The long straddle is the classic pre-earnings play. The market is pricing in uncertainty — options are expensive — but you believe the actual move will be even larger than what's priced in. It's also used before major macro events: FOMC decisions, CPI releases, geopolitical announcements.

**Key insight:** You don't need to know the direction. NVDA can beat earnings massively (+12%) or miss catastrophically (−15%) — either way, your straddle profits. You just need the magnitude to exceed what you paid.

---

### Real Trade Walkthrough

> **Date:** Jan 27, 2025 · **SPY:** $594.00 · **VIX:** 17.2 · **IV Rank:** 55%

**Market context:** FOMC meeting in 3 days (Jan 29). The Fed is expected to hold rates but the language could signal future cuts or hikes. SPY has been rangebound for 2 weeks. IV rank elevated at 55% — options are pricing in a move.

**The trade (Jan 31 expiry — 4 DTE):**
- Buy Jan 31 $594 call (ATM) → pay **$3.20**
- Buy Jan 31 $594 put (ATM) → pay **$3.10**
- **Total debit: $6.30 per share = $630 per contract**
- Break-even UP: $594 + $6.30 = **$600.30**
- Break-even DOWN: $594 − $6.30 = **$587.70**
- Max loss: $630 (if SPY pins at $594 at expiry)

**You need SPY to move at least $6.30 (1.06%) in either direction by Jan 31 to break even.** The options market is implying this move is possible — you're betting it will be even larger.

**FOMC result:** Fed holds, but Powell's language is more hawkish than expected. SPY drops to $584 by Jan 29.

| Time | SPY | P&L | Notes |
|---|---|---|---|
| Jan 27 entry | $594.00 | $0 | Straddle cost $630 |
| Jan 29 (FOMC day, 4pm) | $584.00 | **+$360** | Put worth $10.10, call worth $0.20, total $1,030 |
| Jan 31 expiry | $582.50 | **+$520** | Put worth $11.50, call $0 |

**Alternative: FOMC was dovish, SPY rallied to $605:**
- Jan 29: Call worth $10.80, put worth $0.15 = $1,095 total → profit **+$465**

**Worst case: SPY stays at $594.00 through FOMC (no reaction):**
- Jan 31: Call worth $0, put worth $0 → **−$630 max loss**

---

### Entry Checklist

- [ ] Major known catalyst within 1–5 days (earnings, FOMC, CPI, jobs report)
- [ ] The stock/index has historically moved MORE than the implied move (check historical data)
- [ ] IV rank is high BUT the implied move feels conservative vs past moves
- [ ] Buy 3–7 DTE for event plays (tight window, cheap theta exposure time)
- [ ] Premium is affordable: straddle cost < 3% of underlying price is reasonable
- [ ] You have a directional opinion? Consider a spread instead — it's cheaper

---

### P&L Scenarios (1 contract, $630 debit)

| SPY at Expiry | Call Value | Put Value | Total | P&L |
|---|---|---|---|---|
| $610 (+2.7%) | $16 | $0 | $1,600 | **+$970** |
| $605 (+1.9%) | $11 | $0 | $1,100 | **+$470** |
| $600.30 (+1.1%) | $6.30 | $0 | $630 | **$0 break-even** |
| $595 (+0.2%) | $1 | $0 | $100 | **−$530** |
| $594 (flat) | $0 | $0 | $0 | **−$630 max loss** |
| $588 (−1%) | $0 | $6 | $600 | **−$30** |
| $587.70 (−1.1%) | $0 | $6.30 | $630 | **$0 break-even** |
| $580 (−2.4%) | $0 | $14 | $1,400 | **+$770** |

---

### The Break-Even Math

The implied move from the options market is simply: **ATM straddle price ÷ stock price**

If SPY is at $594 and the straddle costs $6.30:
- Implied move = $6.30 / $594 = **1.06%**

If SPY historically moves 1.8% on FOMC days, the straddle at 1.06% implied looks cheap. If it only moves 0.5% on average, the straddle is expensive. This comparison — implied move vs historical actual move — is the entire edge of this strategy.

---

### Common Mistakes

1. **Buying the straddle too early.** If you buy 2 weeks before earnings, you're paying for 2 weeks of theta decay while waiting. IV will continue to rise closer to the event (further increasing the straddle cost), then crush afterward. Buy 1–5 days before the event.

2. **Ignoring the IV crush.** After the event, whether or not the move was big, IV collapses 40–70%. Even if SPY moves 1.5% (which usually would be profitable), if you don't sell quickly enough, IV crush can turn a 1.5% move into a loss. Close within 30 minutes of the event.

3. **Buying straddles on small-cap or illiquid stocks.** Wide bid-ask spreads make straddles extremely expensive in both legs. Stick to SPY, QQQ, or mega-cap tech with liquid options.

4. **Confusing "volatile stock" with "good straddle candidate."** TSLA is volatile — everyone knows it. That's already priced into the expensive IV. The edge isn't buying straddles on volatile stocks; it's buying straddles where the implied move is too cheap relative to actual historical moves for that specific event.

5. **Not closing before the second event.** If you hold an AAPL straddle through two earnings cycles, the second cycle's IV crush will destroy you. Always have a hard exit plan tied to the catalyst.

---

### Straddle vs Strangle

| Feature | Straddle | Strangle |
|---|---|---|
| Strikes | Both at-the-money | OTM call + OTM put |
| Cost | Higher (ATM = most time value) | Lower (OTM = cheaper) |
| Break-even range | Tighter | Wider |
| Max loss | Full premium | Full premium |
| Best for | Big event plays | Expecting "large" move but not "massive" |

For most FOMC/earnings plays, the **strangle** is more cost-effective — lower debit but still profits from big moves.
