## Short Squeeze Detector

**In plain English:** A short squeeze happens when heavily shorted stocks start rising rapidly, forcing short sellers to buy shares to cover their positions — which drives the price up further, forcing more covering, creating a feedback loop. GameStop (GME) in January 2021 is the most famous example (stock rose 1,500% in 2 weeks). This strategy identifies high short-interest stocks where conditions are ripe for a squeeze and positions ahead of it.

---

### What Triggers a Short Squeeze

**Pre-conditions (all must be present):**
1. **High short interest:** > 20% of float sold short (some squeezes require > 40%)
2. **Low days-to-cover (DTC):** Short interest / avg daily volume < 5 days (shorts can't cover quickly)
3. **Low float:** < 50 million shares (less supply = faster price move)
4. **Catalyst event:** Earnings beat, buyout rumor, Reddit/social attention, analyst upgrade

**The mechanism:**
- Stock gaps up on catalyst (+10–20% in one day)
- Short sellers' stop-losses trigger → they buy to close
- Buying drives price higher
- More stop-losses trigger
- Feedback loop accelerates
- Price can reach 5–10× previous price in extreme cases

---

### Key Metrics to Monitor

| Metric | Squeeze Risk Threshold | Data Source |
|---|---|---|
| Short Interest % of Float | > 20% | FINRA (twice monthly) |
| Days to Cover | < 5 days | Short interest / avg volume |
| Utilization Rate | > 85% (hard to borrow) | Broker stock loan data |
| Cost to Borrow | > 50% annualized | S3 Partners, Ortex |
| Put/Call Ratio | High puts relative to calls (lopsided bear sentiment) | Options chain |
| Insider Buying | Recent insider purchases | SEC Form 4 |
| Earnings Surprise Potential | Low consensus accuracy, wide estimate range | Bloomberg |

**Highest squeeze probability:** All 6 criteria simultaneously met = rare but extremely high squeeze potential.

---

### Real Trade Walkthrough

> **January 22, 2021 — GameStop (GME) approaching peak squeeze conditions**

**January 22 pre-market data:**
- Short Interest: 138% of float (yes, over 100% — due to multiple short chains)
- Days to Cover: 2.1 (extremely low)
- Cost to Borrow: 29% annualized (elevated but not yet extreme)
- GME price: $65 (already up from $20 two weeks earlier)
- WallStreetBets post count: 12,400 GME mentions overnight (explosive growth)

**Catalyst identified:** Roaring Kitty's YouTube stream gaining massive attention; Ryan Cohen's board appointment driving fundamental bullish narrative.

**Trade (January 22, market open):**
- Buy 100 shares GME at $68.20
- Buy Feb 5 $80 calls at $8.50 × 5 contracts = $4,250

**January 25:** GME at $76.79 (+12.6%)
**January 26:** GME at $147.98 (+92.7%) — mainstream media picks up; Elon Musk tweets "Gamestonk"
**January 27:** GME at $347.51 (+134.8%) — peak squeeze day; Robinhood restricts buying

**January 26 exit (before Robinhood restriction was known):**
- Sell shares at $140 → +$71.80 × 100 = **+$7,180**
- Sell $80 calls at $65.00 → +$56.50 × 500 = **+$28,250**
- **Total: +$35,430** on initial $11,070 investment = **+320% in 4 days**

---

### Modern Short Squeeze Screening

**Step 1: Weekly scan (FINRA data updates twice monthly)**
```
Filter: Short_Interest_Float > 0.20 AND Days_to_Cover < 5 AND Market_Cap < $3B
```
This typically returns 15–40 stocks.

**Step 2: Catalyst watch (daily)**
For each flagged stock:
- Check earnings date (next earnings = potential catalyst)
- Monitor Reddit mention velocity (API: Pushshift, Reddit API)
- Check insider filings (SEC Form 4 daily)
- Watch options unusual activity (large call buying = potential squeeze setup)

**Step 3: Enter on catalyst + confirmation**
Never enter based on short interest alone — stocks can stay heavily shorted for months. Wait for:
- Volume spike > 5× average daily volume
- Stock breaking above 52-week high OR strong resistance level
- Social sentiment spike (Reddit/Twitter)

---

### Position Sizing and Risk Management

**This is a high-risk, high-reward strategy.** Position sizing rules:

- Maximum position: 2% of portfolio per squeeze candidate
- Maximum total exposure to all squeeze plays: 5% of portfolio
- Stop loss: −25% from entry (squeezes fail fast — if the squeeze doesn't materialize within 3–5 days, exit)
- Take partial profits aggressively: take 50% off at +50%, let remainder run

**Using options for squeeze exposure:**
- Advantage: limited downside (only premium at risk)
- Disadvantage: options IV becomes extremely expensive once squeeze is in progress (you pay for the squeeze)
- Best practice: buy calls BEFORE the squeeze begins (when IV is still moderate)

---

### Entry Checklist

- [ ] Short interest > 20% of float (confirmed via FINRA)
- [ ] Days-to-cover < 5
- [ ] Identifiable catalyst: earnings, announcement, or social momentum surge
- [ ] Volume > 3× average daily volume on entry day
- [ ] Position size ≤ 2% of portfolio (treat as lottery ticket)
- [ ] Pre-set stop loss at −25% and take-profit ladders at +50%, +100%

---

### Common Mistakes

1. **Chasing after the squeeze is already 200%+ up.** The squeeze candidates to buy are those with all the setup metrics in place BEFORE the catalyst. Once GME is at $150 and you read about it on Twitter, you're not early — you're the exit liquidity.

2. **Over-sizing squeeze positions.** GME rose 1,500% — but 9 out of 10 "squeeze" plays fail and fall 40–70% instead. The portfolio math only works if you size each position as a small option-like position. A 2% position that goes to 0 costs 2% of portfolio; a 2% position that goes up 15× returns 30%.

3. **Ignoring naked short selling vs synthetic short interest.** Short interest > 100% of float isn't mathematically impossible — it occurs when shares are lent and re-lent multiple times (daisy chain). But very high short interest (> 100%) creates legal and regulatory attention that often triggers early squeeze (brokers recall shares, forcing covering).

4. **Shorting a highly shorted stock to "bet against the squeeze."** Going short a stock with 40% short interest because you "know" the squeeze can't last is extremely dangerous. Shorts in a squeeze environment face unlimited losses. Never short into a short squeeze.
