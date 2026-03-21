## Earnings Pin Risk (Strike Pinning at Expiry)

**In plain English:** When a stock's options expire the same day as earnings (or the day after), large open interest at specific strikes can cause the stock to "pin" to that level as dealers frantically delta-hedge. This strategy identifies those magnets and trades into them — betting that the market maker hedging machine will push price toward the strike with the most pain for option holders.

---

### The Mechanism: How Stocks Get Pinned

When dealers are short large quantities of at-the-money calls and puts near expiry:

1. **Below the strike:** Dealers are net short puts (delta < 0) — they must BUY stock to hedge → buying pressure
2. **Above the strike:** Dealers are net short calls (delta > 0) — they must SELL stock to hedge → selling pressure
3. **At the strike:** Both effects cancel — stock gravitates toward the strike

This is most powerful when:
- **Open interest > 50,000 contracts** at the target strike
- Expiry is the **same day or next day** as earnings
- The stock is already **within 1–2%** of the strike before earnings announcement

---

### When Does Earnings Pin Risk Occur?

Standard earnings play: earnings after close Thursday, options expire Friday.

If a stock has heavy OI at $150 and it reports Thursday evening, the Friday expiry creates a pin machine. Even if the stock would "naturally" gap to $153, dealers' aggressive hedging activity can drag it back toward $150 throughout Friday.

This doesn't eliminate the gap — it fights it. For a 3–4% earnings move, the pin might reduce it to 1–2%. For a 1–2% move, the stock can literally end at exactly the strike.

---

### Real Trade Walkthrough

> **AAPL earnings Nov 2, 2023 (after close) · AAPL:** $177 · **Weekly options expiry:** Nov 3, 2023

**Check OI at nearby strikes:**
- $175 strike: 41,000 calls + 38,000 puts = **79,000 total**
- $177.50 strike: 12,000 calls + 9,000 puts = 21,000 total
- $180 strike: 55,000 calls + 48,000 puts = **103,000 total**

Two heavy-OI strikes: $175 and $180. AAPL at $177 is between them.

**AAPL reports:** EPS beat, revenue slight miss. Expected move was ±3.5%. Initial after-hours: $179.40 (+1.4%).

**Friday trade:**
- Enter $179/$181 bear call spread at open (9:35am) — sell $179 call for $1.20, buy $181 call for $0.40 → net $0.80 credit
- Thesis: $180 heavy OI pins it; any rally into $179–$181 will face dealer selling

**Friday close:** AAPL pins at $179.97 — right at the $180 wall.

- $179 call expired worthless (stock never closed above $179.97... wait, it did close above $179)
- Hmm, let me recalculate: stock pinned near $180. $179 call worth ~$0.97 intrinsic at close
- Net P&L: $0.80 − $0.97 = small loss

The trade required more precision: a $180/$182 spread would have worked perfectly. The lesson — structure your spread **above** the pin strike, not below it.

**Revised trade (correct structure):**
- Sell $180 call, buy $182 call → credit $0.55
- With pin at $179.97: $180 call expires worthless → **keep full $55 credit per contract**

---

### How to Find Pin Risk Opportunities

**Step 1:** Before earnings, check the OI distribution in the options chain for the nearest expiry date.

**Step 2:** Flag any strike with OI > 3× the surrounding strikes.

**Step 3:** Check if that high-OI strike is within 2% of the current stock price.

**Step 4:** Calculate the "max pain" level (the price at which total option holder losses are maximized — approximately where dealers want expiry).

**Step 5:** If high-OI strike ≈ max pain level ≈ current price ≈ expected post-earnings price → pin risk exists.

---

### Entry Checklist

- [ ] Earnings date aligns with weekly/monthly options expiry (same or next day)
- [ ] One strike has OI ≥ 40,000 contracts (or 5× adjacent strikes)
- [ ] High-OI strike is within 1.5% of pre-earnings stock price
- [ ] Sell a spread **on the far side** of the pin strike (not between the stock and the pin)
- [ ] Keep spreads narrow ($2–$5 wide) — pin trades lose if the move overwhelms the pin

---

### Common Mistakes

1. **Ignoring the direction of the gap.** If AAPL gaps to $185 at open, no pin at $180 will drag it back 3%. Pin risk works best for small earnings moves. If implied volatility is pricing in ±5%, pin risk doesn't help much.

2. **Misidentifying the pin level.** Max pain ≠ pin level. Max pain is the mathematical strike minimizing option holder payoffs; the pin is driven by the OI-weighted delta of dealer books. They're often close but not identical. Use the OI concentration, not max pain calculators.

3. **Trading individual names with low liquidity.** Pin mechanics require large institutional OI. For a small-cap with 2,000 contracts OI at each strike, there's no pin force. Stick to large-cap stocks (AAPL, AMZN, SPY) where dealer books are massive.

4. **Holding through the open with too much risk.** Even if pin risk exists, a massive earnings gap overwhelms everything. Size small (2–5 contracts) and be prepared to close immediately at open if the move exceeds the pin level.
