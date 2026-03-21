## IV Rank Credit Spread

**In plain English:** Before selling any options premium, ask: are options cheap or expensive right now? IV Rank answers that question by comparing today's implied volatility to its range over the past year. If IV is in the top 50% of its yearly range, options are expensive — great time to sell. This strategy only sells credit spreads when that condition is met, making every trade statistically better than random.

---

### The IV Rank Concept

**IV Rank formula:**
> IVR = (Today's IV − 52-week Low IV) / (52-week High IV − 52-week Low IV) × 100

**Example for SPY:**
- 52-week IV low: 12% (July 2024 — very quiet market)
- 52-week IV high: 65% (August 2024 — yen carry unwind)
- Today's IV: 22%
- IVR = (22 − 12) / (65 − 12) × 100 = **18.9% → LOW**

With IVR at 18.9%, options are cheap relative to the past year. Selling premium now means collecting less for the same risk. The strategy would **pass** on this environment.

**Compare to October 2024:**
- 52-week IV low: 12% (still July)
- Today's IV: 34% (some uncertainty crept back in)
- IVR = (34 − 12) / (65 − 12) × 100 = **41.5% → MODERATE** → Eligible to sell

---

### Real Trade Walkthrough

> **Date:** Oct 15, 2024 · **SPY:** $576.80 · **VIX:** 21.3 · **IVR:** 62%

**IVR Context:** SPY pulled back 3% over the prior week. VIX rose from 15 to 21. IVR jumped from 28% to 62% — options are now pricing in elevated uncertainty. This is exactly the window where selling premium is statistically advantageous.

**Step 1 — Direction filter:**
- SPY still above 50-day MA ($565)? ✅ → Bullish bias → sell **bull put spread**
- If below 50-day MA → neutral → sell **iron condor**

**Step 2 — Strike selection (30 DTE, Nov 15 expiry):**
- Sell Nov 15 $560 put (20-delta, 3% below current) → collect $2.55
- Buy Nov 15 $550 put (wing) → pay $1.10
- **Net credit: $1.45 per share = $145 per contract**
- Max loss: $10 − $1.45 = $8.55 = **$855 per contract**
- Break-even: $560 − $1.45 = **$558.55**

**Nov 15 outcome (SPY at $587.20):**
- SPY rallied 1.8% over 30 days
- Both puts expire far out of the money
- **Full profit: $145**

| Oct 15 IVR | Result | SPY at Nov 15 | P&L |
|---|---|---|---|
| 62% (entered) | ✅ Win | $587 | **+$145** |

**Comparison — if you ignored IVR and entered when IVR = 15%:**
- With IVR = 15%, the same $560 put only collects $0.85 (credit is 40% lower)
- Max loss is still $8.55
- Risk/reward is now 10:1 — the math doesn't work
- **Same trade, same result, but only $85 profit vs $145. Over a year, this compounds significantly.**

---

### IVR Decision Table

| IVR Level | Action | Premium Quality | Strategy |
|---|---|---|---|
| 0–25% | Skip — don't sell premium | Very cheap | Consider buying spreads instead |
| 25–40% | Maybe — marginal | Below average | Small size only, or iron condor |
| 40–55% | Yes — good window | Average to good | Bull put spread or condor |
| 55–70% | Strong signal — sell | Rich | Full size, shorter DTE |
| 70–90% | Prime window | Very rich | Full size, multiple positions |
| 90%+ | Extreme — be careful | Extremely rich | VIX spike likely — use wider wings |

---

### Entry Checklist

- [ ] IVR ≥ 50% (the core requirement — never skip this)
- [ ] Trend filter: determine if bullish, bearish, or neutral for strike selection
- [ ] 30–45 DTE at entry
- [ ] No events in window
- [ ] Wing width: at least 2× the net credit you're collecting

---

### P&L Scenarios (1 contract, $145 credit, $855 max risk)

| SPY at Expiry | P&L | Notes |
|---|---|---|
| > $560 | **+$145** | Both strikes worthless |
| $558.55 | **$0** | Break-even |
| $555 | **−$210** | Partial loss |
| $550 | **−$855** | Max loss |

---

### IV Rank vs IV Percentile — Don't Confuse Them

**IV Rank (IVR):** Where is today's IV relative to the min/max of the past year?
- Single outlier event (VIX = 65 in Aug 2024) permanently pulls the 52-week high up, making all future IVR look artificially low for the rest of the year.

**IV Percentile:** What percentage of days in the past year had lower IV than today?
- More robust to outliers — even if Aug 2024 VIX = 65, if 70% of all other days were below today's 22 VIX, IV percentile = 70%.

**Recommendation:** Use IV percentile for more robust signal. Many platforms show both. Target IV percentile > 50% for entries.

---

### Common Mistakes

1. **Selling premium when IVR = 20% because the stock "looks bullish."** Options are cheap. You're selling underpriced insurance. Even if you're right about direction, you collect $0.65 instead of $1.50. The edge is in the premium, not the direction.

2. **Forgetting that IVR resets after outlier events.** After August 2024's VIX = 65 spike, the 52-week high was anchored at 65% IV. For the rest of 2024, even a 22% VIX showed IVR of only 19% because 65% was the year high. Check that your IVR calculation makes sense given the context.

3. **Confusing IVR with certainty.** High IVR tells you options are expensive — it doesn't tell you the market won't move. In March 2020, IVR was 99% but SPY fell 34%. High IV means high expected move — not that the move won't happen.

4. **Only trading one underlying.** If SPY's IVR is 30%, check QQQ, IWM, and individual stocks. Some will have higher IVR — trade those instead. IVR-based trading improves dramatically when you can select across underlyings.
