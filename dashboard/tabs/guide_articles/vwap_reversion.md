## VWAP Mean Reversion

**In plain English:** VWAP (Volume-Weighted Average Price) is the average price weighted by volume since the market opened. It's the benchmark large institutions use — they try to buy below VWAP and sell above it. When SPY strays too far from VWAP and the move looks exhausted (declining volume, overbought RSI), the institutional reversion force tends to pull it back. This strategy trades that snap-back.

---

### Why VWAP Has Gravitational Pull

Large mutual funds, pension funds, and algo desks measure their execution quality against VWAP. A fund manager buying $500M of SPY wants to prove their fill was below VWAP. This creates natural buying pressure below VWAP and selling pressure above it throughout every single trading session.

**On low-volatility days** (VIX < 18), this force dominates and SPY often oscillates around VWAP like a pendulum. The strategy profits from this oscillation.

---

### Real Trade Walkthrough

> **Date:** April 8, 2025 · **SPY:** $529.80 · **Session VWAP at 11:30am:** $527.40

**Situation:** SPY has been creeping up all morning, now 0.45% above VWAP. RSI(5-min) = 78. Volume on the last 3 bars: declining (3.2M → 2.4M → 1.8M shares). Classic exhaustion above VWAP.

**Signal: Short (sell) the deviation**

**The trade:**
- Buy Apr 8 (0DTE) $529 put → pay $1.10
- Sell Apr 8 $525 put → collect $0.25
- **Net debit: $0.85 = $85 per contract**
- Target: SPY returns to VWAP ($527.40)
- Profit at $527.40: ($529 − $527.40) = $1.60 in-the-money on $529 put, less wing = spread worth ~$1.60

**At 1:15pm:** SPY is at $527.20 (slightly below VWAP — mean-reverted)
- Put spread worth $1.65
- **Close: profit = $1.65 − $0.85 = $0.80 = $80 per contract in 1hr 45min**

| SPY at 2:30pm | P&L | Notes |
|---|---|---|
| $525 (below VWAP) | **+$315** | Full spread value |
| $527.40 (VWAP) | **+$75** | Target hit, decent return |
| $528 (half-revert) | **+$10** | Barely moved |
| $529.80 (no move) | **−$85** | No reversion today |
| $532 (trend up) | **−$85** | Trending day, not a reversion day |

---

### Entry Checklist

- [ ] SPY > 0.40% above OR below session VWAP
- [ ] Volume declining on the recent bars reaching the extreme (exhaustion)
- [ ] RSI(5-min chart) above 70 (for short) or below 30 (for long)
- [ ] VIX below 22 (high-vol days trend far from VWAP and stay there)
- [ ] Time: between 10:15am and 2:30pm (avoid first 45 min and last 90 min)

---

### When NOT to Trade VWAP Reversion

| Condition | Action |
|---|---|
| VIX > 22 | Skip — trending markets stay far from VWAP |
| SPY opened with gap > 1% | First hour is high-vol price discovery — wait |
| FOMC day | Impossible to predict intraday; skip |
| Trend day (up >1% from open) | VWAP will reset higher all day — don't short |
| First 45 minutes of session | VWAP hasn't stabilized yet |

---

### Common Mistakes

1. **Treating it as a guaranteed mean-reversion.** On trend days, SPY can stay 0.5–1.0% above VWAP all day. The filter (declining volume + RSI > 70) is what separates trend from exhaustion — don't skip it.

2. **Entering too far from the VWAP deviation.** If you wait until SPY is 0.8% above VWAP to enter short, you've missed most of the move. Enter on first signs of exhaustion at 0.40–0.50% deviation.

3. **Not having a stop.** If SPY is 0.4% above VWAP and you enter short, and then the FOMC chair gives a surprise speech at 12pm, SPY might go to +1.5% above VWAP. Have a hard stop: if SPY extends another 0.25% in the same direction after entry, exit. The thesis (exhaustion) is invalidated.

4. **Using end-of-day VWAP instead of anchored session VWAP.** Always anchor to today's session open at 9:30am. Yesterday's VWAP is irrelevant for intraday reversion.
