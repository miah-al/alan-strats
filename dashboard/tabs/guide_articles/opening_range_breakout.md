## Opening Range Breakout (ORB)

**In plain English:** Mark the highest and lowest prices SPY trades in the first 30 minutes of the session. If SPY decisively breaks above that high, buy. If it breaks below that low, sell. The first 30 minutes reflects all overnight information being absorbed — a break out of that range with volume signals institutional commitment to a direction for the rest of the day.

---

### Why the First 30 Minutes Matter

The 9:30–10:00am window is the most information-dense period of the trading day:
- Pre-market futures positioning unwinds
- Retail orders accumulated overnight execute
- Institutional desks respond to overnight news
- Market makers set their inventory positions

By 10:00am, this initial chaos settles into a "consensus" range. A decisive break beyond that consensus — with above-average volume confirming real conviction — signals the institutional view of where the market is going for the day.

**Historical fact:** On days when SPY breaks the opening range by 10:15am with volume 1.5×+ average, it continues in that direction for the rest of the session approximately **62% of the time**.

---

### Real Trade Walkthrough

> **Date:** March 20, 2025 · **SPY open:** $565.40

**Opening range (9:30–10:00am):**
- High: $567.80
- Low: $563.20
- Range width: $4.60

**10:05am:** SPY ticks to $568.10 — **breaking above the range high of $567.80**
- Volume on the breakout bar: 4.2M shares (vs 2.1M average for that time window) ✅ 2× volume
- Pre-market S&P futures were +0.3% ✅ (confirming trend)
- ML filter P(breakout sustains) = 0.68 ✅ (above 0.60 threshold)

**SIGNAL: Enter bull call spread**

**The trade:**
- Buy Mar 20 (0DTE) $568 call → pay $1.95
- Sell Mar 20 $573 call → collect $0.45
- **Net debit: $1.50 = $150 per contract**
- Max profit: $5 − $1.50 = $3.50 = **$350 per contract**
- Break-even: $568 + $1.50 = **$569.50**

**Profit target:** Range width = $4.60 → price target = $567.80 + $4.60 = **$572.40**
This approximately equals the max profit at the $573 cap.

**At 1:30pm:** SPY reaches $572.90
- Bull call spread worth $4.40 (near max profit)
- Close for $4.40: **profit = $4.40 − $1.50 = $2.90 = $290 per contract in ~3.5 hours**

| SPY at close | P&L | Notes |
|---|---|---|
| $573+ | **+$350** | Max profit — strong trend day |
| $572 | **+$320** | Near target |
| $570 | **+$150** | Broke even on target move |
| $569.50 | **$0** | Break-even |
| $568 | **−$150** | Breakout failed, flat |
| $565 | **−$150** | Breakout false — max loss |

---

### Entry Checklist

- [ ] Wait for 10:00am (full 30-min range established)
- [ ] Break above range high OR below range low by at least $0.20 (not a tick)
- [ ] Volume on breakout bar > 1.5× average for that time (see your platform's VWAP volume)
- [ ] ML filter P(sustained) > 0.60
- [ ] Pre-market futures trend matches the breakout direction
- [ ] No major event (FOMC, CPI) scheduled for today at 2pm

**Skip days:** FOMC decision days, CPI release days, NFP Friday, monthly/quarterly options expiry

---

### False Breakout Red Flags

| Signal | Interpretation |
|---|---|
| Breakout on low volume | Institutional conviction absent — high false breakout risk |
| Pre-market gap in opposite direction | Conflicting signals |
| VIX > 28 | High-vol days often have reversals after initial breakout |
| It's a Friday | Weekly options expiration creates erratic intraday patterns |
| SPY broke range but immediately pulled back inside | Classic trap — bear/bull trap |

---

### Common Mistakes

1. **Jumping in at 9:31am.** The first minute is noise. Even 9:32am is too early. The range needs the full 30 minutes to establish — any "breakout" before 10:00am is not an ORB signal.

2. **Not having a stop loss.** Define your stop before entry: if SPY re-enters the opening range after breaking out, the thesis is invalidated. Exit. Don't hope it breaks out again.

3. **Chasing the breakout 1% after it happens.** If SPY breaks the $567.80 range high and you're watching at $570, entering now means buying 2.2 points above the range. Your reward/risk has deteriorated. If you missed the entry window, skip the trade.

4. **Trading on choppy days without the ML filter.** On rangebound days, SPY can break the opening range in both directions multiple times. The ML filter (trained on pre-market futures, VIX, gap analysis) separates trend days from chop days — this is why the strategy is labeled "Hybrid."
