## Bull Call Spread (Debit Call Spread)

**In plain English:** You think SPY is going up. Instead of buying a call outright (expensive, fast time decay), you buy a call AND sell a higher-strike call to partially fund it. The sold call cuts your cost in half but caps your profit at that higher strike. It's a defined-risk, defined-reward bullish bet — you know exactly what you can make and lose before you enter.

---

### The Core Trade-off

| Approach | Cost | Break-even | Max Profit | Max Loss |
|---|---|---|---|---|
| Buy $580 call outright | $5.50/share | $585.50 | Unlimited | −$550/contract |
| Bull call spread $580/$590 | $3.00/share | $583.00 | $700/contract | −$300/contract |

By selling the $590 call you give up profits above $590, but you get the trade on for nearly half the cost and a closer break-even. For directional trades without huge conviction, this is almost always better than buying a naked call.

---

### Real Trade Walkthrough

> **Date:** May 5, 2025 · **SPY:** $568.20 · **VIX:** 18.5 · **IV Rank:** 43%

**Market context:** SPY just bounced off its 100-day MA with volume above average. MACD crossed bullish. Target: rally to $580–$585 over the next 2–3 weeks. Want to express a bullish view with limited risk.

**The trade (May 23 expiry — 18 DTE):**
- Buy May 23 $570 call (ATM) → pay **$4.20**
- Sell May 23 $580 call (cap) → collect **$1.65**
- **Net debit: $2.55 per share = $255 per contract**
- Max profit: ($580 − $570) − $2.55 = $7.45 = **$745 per contract**
- Max loss: debit paid = **−$255 per contract**
- Break-even: $570 + $2.55 = **$572.55**

SPY is at $568.20. You need just a $4.35 move (0.77%) to break even. If SPY hits $580 — only a 2.1% rally — you make **$745 on $255 risk, nearly 3:1 reward/risk**.

**Eighteen days later:**

| SPY at May 23 | Spread Value | Your P&L | Notes |
|---|---|---|---|
| $582 (+2.4%) | $10 | **+$745** | SPY cleared $580 — max profit |
| $578 (+1.7%) | $8 | **+$545** | Strong move, excellent trade |
| $575 (+1.2%) | $5 | **+$245** | Good result |
| $572.55 (+0.8%) | $2.55 | **$0** | Break-even |
| $570 (flat) | $1.20 | **−$135** | ATM at expiry, time decay hurt |
| $562 (−1.1%) | $0.10 | **−$245** | Near max loss |
| $558 (−1.8%) | $0 | **−$255** | Max loss |

**Day 10 update:** SPY reached $576. The spread is worth $5.50 (up from $2.55). You've more than doubled. You can:
- **Hold to max profit** if you believe $580 is coming
- **Close for $5.50 — profit of $295** — lock it in, not greedy

---

### Entry Checklist

- [ ] Clear bullish technical signal (MA crossover, bounce off support, breakout)
- [ ] VIX below 25 (high VIX makes debit spreads expensive)
- [ ] Buy the ATM or 1-strike OTM call; sell 2–4 strikes above
- [ ] 14–30 DTE (longer gives more time but costs more debit)
- [ ] Long strike delta: 0.45–0.55 (ATM or just OTM)
- [ ] Cap strike delta: 0.25–0.35 (sets your profit ceiling realistically)

---

### Strike Selection Guide

The width between strikes determines your max profit and risk:

| Width | Example | Max Profit | Max Risk | Notes |
|---|---|---|---|---|
| $5 wide | $570/$575 | $245 | $255 | Small reward, affordable |
| $10 wide | $570/$580 | $745 | $255 | Good balance — standard choice |
| $20 wide | $570/$590 | $1,545 | $455 | Higher cost, much more upside |

**Rule of thumb:** Width should be at least 3× your net debit. A $10-wide spread costing $3.00 gives 3.3:1 max reward/risk. Don't pay $4.00 for a $5-wide spread — that's 1.25:1 and barely worth trading.

---

### P&L Scenarios (1 contract, $255 debit)

| SPY at Expiry | Spread Value | P&L | Notes |
|---|---|---|---|
| $580+ | $10 | **+$745** | Max profit — SPY above cap |
| $576 | $6 | **+$345** | Strong profit |
| $572.55 | $2.55 | **$0** | Break-even |
| $570 | $0 | **−$255** | Max loss (ATM at expiry) |
| < $570 | $0 | **−$255** | Max loss |

---

### Common Mistakes

1. **Buying the spread with too wide a bid-ask.** If the spread has a $0.50 bid/ask on each leg, you're paying $1.00 in slippage before the trade even starts. Use limit orders; never market orders on spreads. Aim for mid-price fills.

2. **Choosing a cap strike too close to entry.** Selling the $572 call when SPY is at $568 caps your profit at $4 and costs you more in credit. Your max profit is only $1.45 — why bother? Set the cap at a realistic target, 2–4% above entry.

3. **Holding through earnings when the long call will lose to IV crush.** After earnings, IV collapses 40–60%. Even if SPY doesn't move, your long call loses significant value. Close before earnings or specifically target the earnings move.

4. **Buying a spread with 5 DTE or less.** The debit spread needs time for SPY to move. With 5 DTE, theta decay on the long call accelerates dramatically. You need to be right almost immediately. Use 14+ DTE minimum.

5. **Using the wrong spread for the thesis.** If you expect a massive move (+5%), a bull call spread caps your profit. Consider buying the call outright or using a wider spread. Bull call spreads are best for "moderate move" expectations.

---

### Bull Call vs Bull Put: Which to Use?

| Bull Call Spread | Bull Put Spread |
|---|---|
| Pay debit upfront | Collect credit upfront |
| Need price to GO UP to profit | Profit if price stays flat OR goes up |
| Higher max profit potential | Lower max profit (capped at credit) |
| Better when strongly bullish | Better when neutral-to-bullish |
| Higher win threshold needed | Lower win threshold |
| Best when IV is LOW (cheap options) | Best when IV is HIGH (expensive premium) |

**Simple rule:** If IV Rank is above 50%, sell the bull put spread. If IV Rank is below 30% and you're directionally confident, buy the bull call spread.
