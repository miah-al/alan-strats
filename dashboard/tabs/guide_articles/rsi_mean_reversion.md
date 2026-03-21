## RSI Mean Reversion

**In plain English:** RSI (Relative Strength Index) measures how overbought or oversold a stock is on a scale of 0–100. When RSI gets extreme — above 80 (overbought) or below 20 (oversold) — and starts turning back toward neutral, it signals that the short-term price extreme is reversing. This strategy trades those reversals with defined-risk spreads.

---

### RSI Explained

RSI(14) = 100 − 100/(1 + Average Gain/Average Loss) over 14 days

- RSI > 70: Overbought — stock has risen sharply, may be overextended
- RSI 40–60: Neutral zone
- RSI < 30: Oversold — stock has fallen sharply, may be oversold
- RSI > 80 or < 20: Extreme readings — highest probability of mean-reversion

The key is **RSI divergence**: price makes a new high but RSI makes a lower high. This tells you momentum is fading even as price extends.

---

### Real Trade Walkthrough

> **Date:** July 21, 2025 · **SPY:** $571.30 · **RSI(14):** 81.3

**Setup:** SPY has rallied 4.2% in 8 days. RSI(14) = 81.3 — overbought territory. More importantly, RSI made a lower high (was 84 on July 14 when SPY was at $568) despite SPY making a higher high at $571.30. **RSI bearish divergence.**

MACD: histogram declining ✅. Volume decreasing on up days ✅.

**Signal: Overbought + RSI divergence → enter bearish**

**The trade:**
- Buy Aug 1 $570 put → pay $3.40
- Sell Aug 1 $560 put → collect $1.00
- **Net debit: $2.40 = $240 per contract**
- Break-even: $567.60
- Max profit: $10 − $2.40 = $7.60 = **$760**

**8 days later (July 29):** SPY at $558.20 (RSI now 41 — mean-reverted)
- Bear put spread worth $8.40
- **Profit: $8.40 − $2.40 = $6.00 = $600**

| SPY Outcome | P&L |
|---|---|
| $558 (−2.3%) | **+$600** |
| $562 (−1.6%) | **+$360** |
| $567.60 | **$0** |
| $571 (flat) | **−$240** |
| $575 (+0.7%) | **−$240** |

---

### RSI Thresholds by Timeframe

| Timeframe | Enter Short | Enter Long | Context |
|---|---|---|---|
| 5-min chart | RSI > 75 | RSI < 25 | Scalping — very short-lived |
| Daily chart | RSI > 70 | RSI < 30 | Swing trading — 5–15 day hold |
| Weekly chart | RSI > 80 | RSI < 20 | Position trading — weeks to months |

**Best signals:** RSI(2) on daily charts. The 2-period RSI is extremely sensitive — RSI(2) > 90 on a daily chart is a very strong overbought signal with documented mean-reversion effect (Larry Connors' research).

---

### Entry Checklist

- [ ] RSI(14) above 75 (short) or below 25 (long) on daily chart
- [ ] RSI divergence: price making new extreme but RSI not confirming (strongest setup)
- [ ] Volume declining as price extends (exhaustion)
- [ ] Not a strong trend day — RSI reversion works best in rangebound environments

---

### Common Mistakes

1. **Shorting an uptrend just because RSI = 70.** In a strong uptrend, RSI can stay above 70 for weeks. An RSI of 72 in a bull market is just "normal overbought." Look for RSI > 80 with divergence.

2. **Using RSI alone.** RSI without a price pattern (divergence, failed swing) generates false signals frequently. Combine with volume, MACD, or a broader trend filter.

3. **No time stop.** RSI can stay extreme for longer than expected. Set a time stop: if RSI hasn't mean-reverted within 10 trading days, close the position regardless.
