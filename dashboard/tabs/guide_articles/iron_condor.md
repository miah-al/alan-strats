## Iron Condor

**In plain English:** You're betting the market stays inside a range. You collect premium upfront by selling both a call spread above the market and a put spread below it. As long as SPY doesn't move too far in either direction before expiry, you keep the premium. You don't need to be right about direction — you just need the market to stay calm.

---

### Why It Works

Options are consistently overpriced relative to what the market actually does. The implied move priced into options (as measured by VIX) has historically been about 15–20% larger than the actual realized move. As a condor seller, you're collecting this "volatility risk premium" — the excess the market pays for protection.

The iron condor limits your risk on both sides. Unlike a naked short strangle, you can never lose more than the width of the spreads minus the credit you collected.

---

### Real Trade Walkthrough

> **Date:** January 8, 2025 · **SPY:** $585.00 · **VIX:** 16.4 · **IV Rank:** 47%

**Market context:** SPY has been rangebound between $575–$595 for two weeks. No FOMC, no CPI for 18 days. VIX below 18. Classic iron condor setup.

**The trade you place (monthly expiry, 30 DTE — Feb 7 expiry):**

*Put spread (lower tent):*
- Sell Feb 7 $570 put (16-delta) → collect $2.10
- Buy Feb 7 $560 put (wing) → pay $0.90
- Put spread net credit: **$1.20**

*Call spread (upper tent):*
- Sell Feb 7 $600 call (16-delta) → collect $1.85
- Buy Feb 7 $610 call (wing) → pay $0.70
- Call spread net credit: **$1.15**

**Total net credit: $2.35 per share = $235 per contract**
**Max profit: $235 (both spreads expire worthless)**
**Max loss: $10 wing − $2.35 = $7.65 = $765 per contract**
**Upper break-even: $600 + $2.35 = $602.35**
**Lower break-even: $570 − $2.35 = $567.65**

SPY has to stay between **$567.65 and $602.35** for you to profit. That's a ±$17.35 buffer around the current price — about ±3%.

**What happens at Feb 7 expiry:**

| SPY at Expiry | Your P&L | Explanation |
|---|---|---|
| $595 (inside tent) | **+$235** | Both spreads expire worthless. Full premium kept. |
| $602.35 (upper BE) | **$0** | Call spread partially in-the-money, exactly offset by credit |
| $608 (above upper BE) | **−$330** | $8 spread loss − $2.35 credit = −$5.65 × 100 = −$565... wait, let's be exact: spread = $608−$600 = $8 loss on call spread, net = $8−$2.35 = −$5.65 = **−$330** after putting both spreads together |
| $557 (below lower BE) | **−$450** | Put spread breached, similar math |
| $615 (above call wing) | **−$765** | Max loss. Both spreads, call side fully breached. |

**Management (critical — don't skip):**
- Day 15 (halfway): SPY is at $591. Condor is worth $1.10 (down from $2.35). **Close it for $1.10 — profit of $125.** You've captured 53% of max profit in 15 days. Free the capital for the next trade.

---

### Entry Checklist

- [ ] IV Rank > 40% (you want implied vol elevated — you're selling it)
- [ ] VIX between 14–26 (below 14: premium too thin; above 26: moves too large for condor)
- [ ] No FOMC, CPI, NFP, major earnings within the expiry window
- [ ] SPY in a range — check if it's been trading between two levels for 2+ weeks
- [ ] 21–45 DTE at entry (30 DTE is the sweet spot)
- [ ] Wings at least 15 points wide ($10 wings are dangerously narrow)

---

### Exit Rules

| Condition | Action |
|---|---|
| 50% of max profit captured | Close entire condor. Always. Don't get greedy. |
| 21 DTE reached without 50% profit | Close or roll out to next month |
| One side tested (delta > 30) | Roll the tested spread further OTM or close |
| 200% of credit received as loss | Emergency close. Accept the loss. |
| FOMC / major event announced in window | Close before the event |

---

### Common Mistakes

1. **Holding for full credit.** The last 50% of profit takes 3× as long as the first 50% and exposes you to far more risk. A +$235 trade becomes a −$400 loss if you hold through a surprise event. **Always close at 50%.**

2. **Wings too narrow.** A $5-wide condor on SPY gives you $5 of protection. SPY regularly moves $5 in a single session. Use $10–$15 wide wings minimum. Yes, you collect less credit — that's the cost of not blowing up.

3. **Selling into low IV.** If VIX is 12 and IV rank is 20%, the premium is terrible. You collect $1.00 on a $10 spread — a 9:1 risk/reward in the wrong direction. Wait for elevated IV.

4. **No earnings check.** NVDA earnings can move SPY 1–2% in a session. If NVDA, AAPL, or MSFT report within your expiry window, that premium spike will blow through your wings.

5. **Over-sizing.** One bad condor (max loss) wipes 4–5 winning condors. Keep each condor at 3–5% of capital. If you have $20k, that's 2–4 contracts maximum.

6. **Not adjusting the tested side.** When SPY runs toward one of your short strikes, the textbook response is to roll the tested side further out or close the untested side for additional buying power. Many beginners freeze and hope — hope is not a strategy.

---

### Greeks & What They Mean for You

| Greek | Sign | What it means in plain English |
|---|---|---|
| Delta | Small (±0.05) | You don't care much about direction — you want the market to stay still |
| Theta | Positive (+$8–15/day) | Time passing makes you money. Every day that passes with no move = profit |
| Vega | Negative | If volatility rises, your position loses value (the sold options get more expensive) |
| Gamma | Negative | Near expiry, sudden large moves hurt you the most |

---

### Key Parameters

| Parameter | Conservative | Standard | Income-Focused |
|---|---|---|---|
| Short delta | 10-delta | 16-delta | 20-delta |
| Wing width | $15 | $10 | $5 |
| DTE at entry | 45 | 30 | 21 |
| Profit target | 25% | 50% | 75% |
| IVR minimum | 50% | 40% | 30% |
| Max position size | 2% capital | 4% capital | 6% capital |

**The 16-delta rule of thumb:** A 16-delta option has approximately a 16% chance of expiring in-the-money (by options pricing theory). Both your short put and short call are ~84% likely to expire worthless. Combined, the condor has roughly a 68% probability of max profit — matching the 1-standard-deviation expected range.
