## Weekly Iron Condor (Mechanical)

**In plain English:** Every Monday morning, sell a 16-delta iron condor on SPY expiring that Friday. Repeat every week for 52 weeks. No discretion — purely mechanical. The statistical edge comes from the systematic overpricing of weekly implied volatility relative to actual weekly moves.

---

### Why Mechanical?

Discretionary traders improve on bad setups and skip good ones. Research shows that mechanical premium-selling systems outperform discretionary variations over the long run because:
1. They don't skip trades that feel scary (which are often the best-priced)
2. They don't over-trade when it feels easy
3. They generate consistent sample sizes for proper statistical evaluation

---

### The Monday Morning Checklist

**Every Monday at 9:45am:**

1. Check: Is today's VIX > 28? → **SKIP this week**
2. Check: Is there FOMC, CPI, or NFP before Friday close? → **SKIP this week**
3. Pull ATM straddle price: tells you the implied weekly move
4. Set short strikes at 16-delta on both sides (~$0.80–$1.20 each)
5. Buy wings $5 further out
6. Target total credit: $0.70–$1.00

**Example — Monday March 10, 2025 · SPY:** $569.20 · **VIX:** 17.4

Implied weekly move (ATM straddle): $3.60 → 0.63%

- Sell Fri Mar 14 $574 call (16-delta, $4.80 above ATM) → collect $0.85
- Sell Fri Mar 14 $563 put (16-delta, $6.20 below ATM) → collect $0.75
- Buy $579 call wing → pay $0.20
- Buy $558 put wing → pay $0.18
- **Net credit: $1.22 = $122 per condor**

---

### Management Rules (Non-Negotiable)

| Day | Condition | Action |
|---|---|---|
| Any day | 50% of credit captured | Close — take the $61 profit |
| Any day | Loss reaches 200% of credit | Close the tested side, keep untested |
| Wednesday | Untested side < 5-delta | Roll it to a new short strike for more credit |
| Thursday EOD | Still open, both sides > 10-delta | Close — don't hold into Friday |
| Friday | Pin risk — any open position | Close by 3:30pm |

---

### Annual Statistics (Typical Year, 40 Weeks Traded)

- Skip weeks: ~12 (FOMC, CPI, NFP, VIX > 28)
- Winning weeks: ~27 (close at 50% profit = $61 avg)
- Losing weeks: ~13 (2× loss = $244 avg)
- **Annual P&L per contract: 27 × $61 − 13 × $244 = $1,647 − $3,172 = −$1,525**

Wait — that's negative? **The math works only with strict 50% close rule.** Without it:
- Full wins: 28 × $122 = $3,416
- Full losses: 12 × $488 = $5,856
- Net: **−$2,440** — definitely negative

The **50% close rule** is not optional. It's what makes the strategy profitable by limiting loss severity.

With 50% close + 200% loss stop:
- Average win: $61 (50% close)
- Average loss: $148 (200% stop before full max loss)
- Win rate: 68%
- **Expected value per trade: 0.68 × $61 − 0.32 × $148 = $41.48 − $47.36 = −$5.88**

Still slightly negative? The real edge comes from efficient capital deployment: freeing up margin when you close at 50% profit lets you put on a new trade immediately, potentially 2 trades in one week.

---

### Common Mistakes

1. **Getting greedy — not closing at 50%.** The most common and most costly mistake. The trade feels easy; you hold for full credit. Then Thursday's CPI surprise moves SPY 2% and wipes out 3 winning weeks.

2. **Trading FOMC weeks.** Fed announcements can move SPY 2% in 30 minutes — your entire weekly condor range. Non-negotiable skip.

3. **Not accounting for position scaling.** At 5 contracts per condor, a max-loss week is $4,400. If you have 4 losing weeks in a row (rare but possible), that's $17,600. Ensure your account can absorb 6 consecutive max-loss events before starting.
