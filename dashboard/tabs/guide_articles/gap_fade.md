## Gap Fade Strategy

**In plain English:** When SPY opens higher or lower than yesterday's close without a strong fundamental reason, the gap often "fills" — price returns to where it closed the previous day. This strategy fades (bets against) the gap using a bull or bear spread, targeting the gap fill within the same session.

---

### Real Trade Walkthrough

> **Date:** Feb 12, 2025 · **SPY prior close:** $604.20 · **SPY open:** $608.90 (+0.77% gap up)

**Gap analysis at 9:35am:**
- Gap size: +$4.70 / 0.77%
- Catalyst check: No major economic data, no FOMC — it's a routine Wednesday
- Pre-market news: Asian markets rose on low-significance trade talk optimism
- Pre-market volume: 8.2M shares (vs 14M average) — light, low conviction ✅
- ML P(gap fill): 0.72 ✅

**Signal: Fade the gap up** (bear put spread targeting $604.20 close level)

**The trade (placed at 9:35am):**
- Buy Feb 12 (0DTE) $608 put (just OTM of open) → pay $2.20
- Sell Feb 12 $603 put (below gap fill target) → collect $0.60
- **Net debit: $1.60 = $160 per contract**
- Profit target: SPY returns to $604.20 (gap fill) = $608 − $604.20 = $3.80 gap, spread pays $3.80 of its $5 width
- Max profit at $603: $5 − $1.60 = $3.40 = **$340 per contract**
- Break-even: $608 − $1.60 = **$606.40**

**At 11:45am:** SPY has drifted down to $604.80 — near gap fill
- Bear put spread worth $2.90
- **Close: profit = $2.90 − $1.60 = $1.30 = $130 per contract in ~2 hours**

| SPY at 3:30pm close | P&L | Notes |
|---|---|---|
| $603 or below | **+$340** | Full gap fill and then some |
| $604.20 (exact fill) | **+$230** | Gap filled — good result |
| $606.40 | **$0** | Break-even |
| $608.90 (no fill) | **−$160** | Gap-and-go day |
| $612 | **−$160** | Gap extension — max loss |

---

### Gap Types and Fill Probability

| Gap Type | Fill Same Day | Trade? |
|---|---|---|
| No-catalyst sentiment gap (<1%) | ~70% | ✅ Best candidate |
| Weak catalyst (overseas markets, minor news) | ~60% | ✅ Good |
| Economic data miss/beat | ~45% | ⚠️ Lower probability |
| Fed announcement | ~30% | ❌ Skip |
| Earnings-related (single stock in SPY) | ~55% | ⚠️ Check component |
| Technical breakout with volume | ~35% | ❌ Skip — gap-and-go |

---

### Entry Checklist

- [ ] Gap > 0.4% (smaller gaps aren't worth the spread cost)
- [ ] No scheduled macro event today (no FOMC, no CPI, no NFP)
- [ ] Pre-market volume BELOW average (conviction gap = don't fade; exhaustion gap = fade)
- [ ] Gap direction OPPOSITE to prior-day trend (counter-trend gaps fill more often)
- [ ] ML P(gap fill) > 0.60
- [ ] Enter within 15 minutes of open (after initial discovery, before gap starts filling)

---

### Common Mistakes

1. **Fading gaps caused by real catalysts.** When jobs data misses badly, SPY gaps down AND KEEPS GOING. The economic news is a legitimate repricing event. NLP classification of the pre-market catalyst is essential.

2. **Holding too late into the session.** If the gap hasn't filled by 2pm, it's probably not filling today. Sentiment-driven morning gaps fade in the first 2–3 hours or not at all. Exit by 2pm if not hit target.

3. **Using too wide a spread.** If you buy a $608/$598 put spread to fade a gap, your target ($604.20 fill) is near the middle of the spread. Your max profit requires SPY to fall $10 — much more than the gap size. Match the spread width to the gap size.

4. **Forgetting that gap-and-go days exist.** Some days, the gap is real and extends. Your hard stop must be: if SPY extends the gap by another 0.3%, your thesis is wrong. Exit immediately.
