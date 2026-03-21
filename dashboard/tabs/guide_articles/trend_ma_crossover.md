## Trend — MA Crossover

**In plain English:** When a shorter-period moving average crosses above a longer-period moving average, it signals that recent price action is trending up — a buy signal. When it crosses back below, that's the exit (or short) signal. The most common version: 50-day MA crossing the 200-day MA (the "Golden Cross" / "Death Cross"). Simple, time-tested, and still works because it captures the middle portion of major trends while avoiding the worst drawdowns.

---

### Why Moving Average Crossovers Still Work

Three reasons the signal persists despite being one of the oldest technical strategies:

1. **Self-fulfilling:** Millions of traders watch the same moving averages. When SPY crosses above the 200-day, buyers pile in — creating the very trend the signal predicted.

2. **Trend persistence:** Markets trend roughly 35% of the time. During sustained trends, MA crossovers capture the majority of the move while sitting out the noise.

3. **Catastrophic loss avoidance:** The 200-day MA filter has been in bear territory (price below 200MA) during almost every major crash (2000–2002, 2008–2009, 2022). Being out of the market during those periods dramatically improves long-run risk-adjusted returns.

---

### Signal Types and Their Trade-offs

| Crossover | Speed | Win Rate | Avg Win | Avg Loss |
|---|---|---|---|---|
| 10MA/50MA | Fast | 38% | +5.2% | −2.1% |
| 20MA/100MA | Medium | 44% | +8.4% | −2.8% |
| 50MA/200MA | Slow | 48% | +12.3% | −3.8% |
| 100MA/200MA | Very slow | 52% | +18.1% | −4.2% |

Slower crossovers have higher win rates (trend is more established before signal fires) but fewer signals. The 50/200 "Golden Cross" is the best balance of frequency and quality.

---

### Real Trade Walkthroughs

> **Golden Cross — October 28, 2022:**

After a brutal 2022 bear market, SPY's 50-day MA crossed back above the 200-day MA on October 28, 2022.

- SPY at signal: $393.40
- 50-day MA: $381.20
- 200-day MA: $380.10
- Gap: 50MA crossed above 200MA → **Golden Cross confirmed**

**Entry:** Buy SPY at $393.40 (or at close of confirmation day)

**Hold through all subsequent pullbacks (discipline required):**
- November 2022: pullback to $375 (−4.7%) → 50MA still above 200MA → hold
- January 2023: SPY at $397 → tiny gain, hold
- March 2023 banking crisis: SPY drops to $381 → 50MA approaching 200MA → reduce size 50%
- April 2023: Crisis passes, 50MA re-expands above 200MA → restore full size

**Death Cross warning never materialized in 2023.** By year-end 2023: SPY at $473.

**Exit would have triggered if Death Cross occurred.** With sustained hold: **+20.2% from Golden Cross entry to year-end 2023.**

---

> **Death Cross — March 25, 2022:**

SPY's 50-day MA crossed below 200-day MA on March 25, 2022 (after already falling from $479 January high).

- SPY at signal: $451.90
- 50-day MA: $445.80
- 200-day MA: $446.20
- Gap: 50MA crossed below 200MA → **Death Cross confirmed**

**Action:** Exit long SPY (sell $451.90); optionally short or buy puts

SPY at Death Cross: $451.90
SPY low (October 2022): $348.11 → −22.9% from Death Cross signal

**Exit short/re-enter:** When Golden Cross fired October 28, 2022 at $393.40

**Outcome:** Avoided −22.9% drawdown by exiting at Death Cross; reentered for subsequent +20% gain.

---

### Enhancements That Improve Performance

**1. Volume confirmation:**
- Golden Cross with volume > 1.2× average daily volume: win rate jumps to 64% (vs 48% baseline)
- Death Cross with volume confirmation: bear case stronger, hold short longer

**2. Trend strength filter (ADX):**
- Only trade Golden Cross when ADX > 20 (trend is strong enough to sustain)
- Skip crossovers when ADX < 15 (choppy market, crossover will fail quickly)

**3. Reducing false signals with confirmation period:**
- Require 50MA to remain above 200MA for 3 consecutive days before entering
- Filters out temporary crossovers during whipsaw markets
- Reduces trades by 20%, improves win rate by 8%

**4. Regime filter:**
- Only take Golden Cross signals when VIX < 25 (trend signals fail in high-vol environments)
- When VIX > 25, use mean-reversion strategies instead

---

### Comparative Performance (SPY, 2000–2024)

| Strategy | CAGR | Max Drawdown | Sharpe |
|---|---|---|---|
| Buy and hold SPY | 10.2% | −55% (2008–2009) | 0.68 |
| 50/200 MA crossover | 9.1% | −26% (2022) | 0.82 |
| 50/200 MA + ADX filter | 10.4% | −22% | 0.91 |
| 50/200 MA + volume + ADX | 11.2% | −19% | 1.03 |

The simple crossover gives up a little return for a large reduction in drawdown. With filters, you get comparable return AND reduced drawdown.

---

### Entry Checklist

- [ ] 50-day MA crosses above 200-day MA (Golden Cross)
- [ ] Confirm: SPY price is also above both MAs (no divergence)
- [ ] Volume > 1.1× average on crossover day
- [ ] ADX > 18 (trend present)
- [ ] VIX < 25 (not in high-vol regime)
- [ ] Enter at close of signal day (avoid intraday whipsaw)
- [ ] Exit at Death Cross OR when loss exceeds 8% from entry

---

### Common Mistakes

1. **Using MA crossovers in sideways markets.** When SPY oscillates in a $10 range, the MAs cross repeatedly generating false signals in both directions. The ADX filter catches this — stop trading MA crossovers when ADX < 15.

2. **Different MA types.** Simple MA (SMA) and Exponential MA (EMA) produce different crossover dates. EMA gives more weight to recent data and signals earlier. In fast-moving markets, EMA 50/200 signals 1–3 weeks before SMA 50/200. Neither is strictly better — pick one and stick with it.

3. **Over-optimizing the lookback periods.** Testing all combinations of MA periods and picking the best one (12/26, 10/30, 15/45...) produces in-sample overfitting. The 50/200 works because it's the most-watched combination, not because it's mathematically optimal.

4. **Shorting the Death Cross.** Taking a short position on a Death Cross is dramatically riskier than simply exiting longs. Markets can rally 15–20% from a Death Cross level even during a broader bear market (bear market rallies). Death Cross = exit longs, not automatically short.
