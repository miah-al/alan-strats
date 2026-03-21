## SPY / IWM Pairs Trade (Large vs Small Cap)

**In plain English:** When the economy is booming, small-cap stocks (IWM, Russell 2000) tend to outperform large-caps (SPY). When fear rises, small-caps underperform badly — they have worse credit access, more domestic exposure, and less pricing power. This strategy trades the spread between them, going long the one that's statistically cheap and short the one that's expensive.

---

### The Economic Intuition

Small-cap companies (median market cap ~$700M in IWM) are:
- More sensitive to US domestic growth (less global revenue)
- More sensitive to credit conditions (rely more on bank loans, not capital markets)
- More volatile — they move 1.3–1.5× as much as SPY on average

When the IWM/SPY ratio is historically high (small-caps expensive relative to large-caps), it often means the "risk-on" cycle is overextended and due for a reversal.

---

### Real Trade Walkthrough

> **Date:** Feb 3, 2025 · **SPY:** $605.20 · **IWM:** $229.80 · **IWM/SPY ratio:** 0.3798

**Z-score of IWM/SPY spread (60-day rolling):** +2.1
Signal: IWM expensive relative to SPY → Sell IWM / Buy SPY

**The trade (dollar-neutral):**
- Short 265 shares IWM at $229.80 = $60,897
- Long 100 shares SPY at $605.20 = $60,520
- Net: approximately market-neutral

**Feb 20 (17 days later):** Z-score reverted to +0.4
- SPY: $611.80 (+$6.60 × 100 = +$660)
- IWM: $225.10 (−$4.70 × 265 = +$1,245 on short)
- **Net profit: $1,905 on ~$60k capital = +3.2%**

---

### Risk Factors

**2020–2021 small-cap rally:** IWM outperformed SPY by 45% — the "re-opening trade." The Z-score reached +3.5 and kept going. This is the key risk: regime shifts that make the divergence permanent (not temporary).

**Defense:** Time stop (close after 15 days regardless), and avoid entering when there's a macro catalyst specifically favoring small-caps (Fed cutting rates benefits small-cap borrowers disproportionately).

---

### Common Mistakes

1. **Not adjusting for the beta difference.** IWM is ~1.35× more volatile than SPY. A dollar-neutral position is actually short beta. For true factor-neutral positions, you need to weight by beta: short fewer dollars of IWM than you're long in SPY.

2. **Entering during rate-cut cycles.** Rate cuts disproportionately benefit small-caps (lower borrowing costs). If the Fed is cutting, IWM will outperform SPY for months — don't short IWM in that environment.

3. **Holding through earnings season.** Individual small-cap stocks in IWM have more volatile earnings surprises. Q4 earnings season (January–February) often causes dramatic IWM outperformance or underperformance that's not mean-reversion — it's fundamental repricing.
