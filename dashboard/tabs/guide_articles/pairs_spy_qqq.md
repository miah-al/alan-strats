## SPY / QQQ Pairs Trade

**In plain English:** SPY and QQQ move together most of the time because they overlap heavily (the Nasdaq 100 stocks make up ~35% of the S&P 500). But sometimes one diverges significantly from the other — tech gets expensive relative to the broad market, or vice versa. This strategy measures that divergence, waits for an extreme, and bets on reversion. You go long one and short the other simultaneously, so overall market direction doesn't matter — only the gap between them does.

---

### Why SPY and QQQ Diverge

QQQ is dominated by mega-cap tech: AAPL, NVDA, MSFT, AMZN, META, GOOGL (~60% of QQQ). SPY is more diversified across financials, healthcare, industrials. Their ratio drifts based on:

- **Tech earnings cycles:** Strong NVDA earnings lift QQQ more than SPY
- **Rate sensitivity:** Tech stocks (long duration) suffer more when rates rise → QQQ underperforms
- **Risk-on/risk-off:** QQQ leads on risk-on rallies (growth loves low rates, animal spirits)
- **Sector rotation:** Investors rotating from tech to value → QQQ underperforms

The key insight: **this ratio is stationary (mean-reverting)** over months. It doesn't trend forever. When it gets extreme, it comes back.

---

### Real Trade Walkthrough

> **Date:** December 3, 2024 · **SPY:** $604.50 · **QQQ:** $513.80

**Z-score calculation (60-day rolling):**
- Hedge ratio β (252-day regression): 0.85 (QQQ moves 0.85× as much as SPY in log space)
- Spread today: log(513.80) − 0.85 × log(604.50) = 6.242 − 0.85 × 6.405 = 6.242 − 5.444 = 0.798
- 60-day mean of spread: 0.782
- 60-day std of spread: 0.008
- **Z-score = (0.798 − 0.782) / 0.008 = +2.0**

Z-score of +2.0 means QQQ is expensive relative to SPY by 2 standard deviations. **Signal: Sell QQQ / Buy SPY (bet on QQQ underperforming).**

**The trade:**
- **Short 100 shares QQQ at $513.80** → proceeds $51,380
- **Long 85 shares SPY at $604.50** → cost $51,382 (roughly dollar-neutral)
- Net cash outlay: ~$0 (approximately market-neutral)

**Why 100 QQQ vs 85 SPY?** The hedge ratio β = 0.85 means 100 QQQ shares should be hedged with 85 × ($513.80 / $604.50) = ~72 SPY shares for perfect dollar-neutrality. Approximated here for illustration.

**Two weeks later (Dec 17, 2024):**
- Z-score reverted to +0.3 (QQQ came back in line)
- QQQ: $502.40 (fell $11.40 per share) → short profit: **+$1,140**
- SPY: $608.20 (rose $3.70 per share) → long profit: **+$315**
- **Net profit: $1,455 on ~$51k capital = 2.8% in 2 weeks**

| Scenario | Z-Score Outcome | QQQ | SPY | Net P&L |
|---|---|---|---|---|
| ✅ Full reversion | +2.0 → 0 | −$11 | +$4 | **+$1,450** |
| ✅ Partial reversion | +2.0 → +1.0 | −$5 | +$2 | **+$670** |
| ⚠️ No change | +2.0 stays | $0 | $0 | **$0** |
| ❌ Spread widens | +2.0 → +3.0 | +$5 | −$2 | **−$670** |
| ❌ Extended divergence | Tech re-rates | +$20 | flat | **−$2,000+** |

---

### Entry Checklist

- [ ] Z-score of SPY/QQQ spread reaches ±2.0 or beyond (at least ±1.8)
- [ ] Cointegration test confirms the pair is still stationary (Engle-Granger p-value < 0.05)
- [ ] No structural reason for permanent divergence (e.g., AI mega-cap rally might be different)
- [ ] Hedge ratio updated within the last 30 days (use rolling 252-day regression)
- [ ] Dollar-neutral positioning (long and short sides equal in dollar value)

---

### Exit Rules

- **Primary target:** Z-score reverts to ±0.5
- **Time stop:** Exit after 15 trading days regardless of P&L (prevents capital lockup)
- **Stop loss:** Z-score reaches ±3.5 — spread has moved against you significantly, reassess whether structure is breaking down

---

### The Risk of Structural Breakdown

The biggest risk: the pair's relationship permanently shifts. This happened in 2023–2024 when AI-driven tech outperformance drove QQQ to persistently expensive levels relative to SPY for months. The Z-score kept reading +2.0 to +3.0 for extended periods — the "short QQQ" trade was a loser.

**How to protect against this:**
1. Always recalculate the hedge ratio with recent data (rolling 252-day window)
2. Have a hard time stop (15 days) — don't "hope" for reversion indefinitely
3. Check whether there's a **fundamental reason** for the divergence (AI revolution, sector rotation, rate sensitivity shift) — if yes, skip the trade

---

### Common Mistakes

1. **Trading dollar-neutral but ignoring the hedge ratio.** Buying $50k of SPY and shorting $50k of QQQ is not pairs trading — it's two separate bets. The hedge ratio β matters because QQQ has higher beta than SPY. A 1% SPY move corresponds to ~1.15% QQQ move on average.

2. **Using a fixed hedge ratio from years ago.** The SPY/QQQ relationship evolves. Recalculate the beta monthly. If you're using β = 0.80 but the true current β is 0.92, your hedge is wrong and you have net directional exposure.

3. **Not verifying cointegration is still valid.** The Engle-Granger cointegration test should give p-value < 0.05 on your most recent rolling 252-day window. If it's > 0.10, the pair may have temporarily broken down — skip the trade.

4. **Over-leveraging.** Pairs trades can feel "safe" because they're market-neutral. But the spread can widen significantly before reverting. With 2× leverage, a Z-score move from +2.0 to +3.0 can cause a 5%+ loss before reverting.
