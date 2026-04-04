# How to Use This Iron Condor Screener
### Reading Signals, Avoiding Traps, and Building Conviction

---

## Introduction

The iron condor screener is not a signal generator that tells you what to trade. It is a regime assessment tool that tells you whether the current environment supports the iron condor's edge — and how much of that edge is present for each underlying. Every column represents a different dimension of the volatility and trend environment. The skill is reading them together, not reacting to any single number in isolation.

The most common screener mistake is treating a single high reading as a buy signal. A ticker with IVR of 0.72 looks immediately attractive — but if ADX is 44, the underlying has been in a clean uptrend for six weeks, and ATR% is 2.1%, selling a condor is handing away premium to a market that is directionally motivated and willing to breach your short strikes repeatedly. Conversely, a ticker with ADX of 12 and ATR% of 0.6% in a true consolidation is an iron condor setup even if IVR is only 0.38 — because the lack of movement means theta will do its work unmolested.

Building a real edge from the screener requires understanding what each column actually measures, what combination of signals is genuinely favorable, and what conditions should cause you to pass regardless of how one signal looks. Every section below is oriented toward practitioner judgment, not algorithmic rule-following.

---

## 1. Reading Each Column

| Column | What It Measures | Favorable Range for ICs |
|---|---|---|
| **IVR** | Where today's IV sits in its 52-week range (0 = 52-week low, 1 = 52-week high) | > 0.40 |
| **VRP** | IV minus 30-day realized volatility (vol points). Positive = options priced above actual recent movement | > 2.0 vol pts |
| **ATM IV** | Current annualized implied volatility at-the-money | Context-dependent (see VIX regime below) |
| **ADX** | Average Directional Index — strength of any directional trend, regardless of direction | < 22 (range-bound) |
| **ATR%** | Average True Range as % of price — current daily velocity | < 1.5% preferred |
| **VIX** | CBOE VIX — proxy for broad market volatility regime | 18–30 sweet spot |
| **Credit** | Approximate premium collected per share for a balanced condor at standard strikes | Higher is better, but only if ADX is also favorable |

**IVR > 0.40:** You are selling volatility that is historically elevated — the foundational condition for positive expected value in premium selling. Below 0.30, you are selling cheap vol into a quiet market; the credit doesn't compensate for the risk. At IVR 0.60+, you have the structural equivalent of entering a casino with the odds clearly in your favor.

**VRP > 2.0 vol pts:** Variance risk premium is the spread between what the market implies will happen (IV) and what recently happened (realized vol). When VRP is positive, option sellers are structurally overcompensated — like an insurance company charging more than actuarial fair value. VRP is positive roughly 70% of the time on SPY. When it's negative, realized vol is exceeding implied vol — a losing structural environment for condor sellers.

**ADX < 22:** The most important filter for condor entry timing. ADX below 18 is ideal — the underlying has been directionless. ADX above 28 is a serious caution, above 35 is a disqualifier. The underlying does not need to stop moving to be a good condor candidate — it needs to stop trending. A stock that oscillates ±2% within a range scores low on ADX even with significant daily moves.

---

## 2. What Makes a Good IC Entry

The ideal setup requires four of five signals to be favorable simultaneously. A single strong signal does not create an edge — it creates an appearance of edge that can be overridden by the one missing filter.

**Near-perfect SPY setup — typical late-summer consolidation:**
```
IVR = 0.55     (IV in top 45% of annual range — elevated ✓)
VRP = +4.5     (IV running well above 30-day realized — structural overpricing ✓)
ADX = 18       (no dominant trend — range-bound ✓)
ATR% = 0.85%   (calm daily movement — wings won't be tested routinely ✓)
VIX = 22       (moderate fear, decent credits without chaos ✓)
Credit = $1.40/share on 30-DTE balanced condor
```

This is a green-light setup. Place short strikes one standard deviation out, collect the credit, manage at 50%.

**Borderline setup (3 signals pass, one borderline):**
```
IVR = 0.38     (below preferred 0.40 — borderline ⚠)
VRP = +3.8     (positive but moderate)
ADX = 16       (range-bound ✓)
ATR% = 0.95%   (calm ✓)
VIX = 19       (acceptable ✓)
```

Three signals passing with one borderline: reduce position size by 40% and set a tighter stop. The screener is a queue, not a forced entry. Waiting one week for IVR to improve is always an option.

---

## 3. Reading VRP — The Overlooked Edge

Variance Risk Premium deserves more attention than most retail traders give it. IVR tells you whether IV is high relative to its own history. VRP tells you whether IV is high relative to what the market is actually doing right now.

A high IVR with low VRP means: IV is elevated on a historical basis, but recent realized vol has caught up with or exceeded implied vol. This is common in trending markets that have also seen elevated actual movement — the options are expensive, but they may be correctly priced given the current velocity. Selling condors here is riskier than the IVR alone suggests.

A moderate IVR with high VRP is the better setup: the market has been implying more movement than is actually occurring, structural overcompensation is in play, and theta decay will almost certainly outpace realized movement.

**VRP threshold practical guidance:**
- VRP > +5 vol pts: strong structural edge; size normally
- VRP +2 to +5 vol pts: positive edge; standard entry
- VRP 0 to +2 vol pts: marginal; reduce size or wait
- VRP negative: structural edge is absent; do not enter new condors

**Negative VRP is a serious warning.** It means the market moved more than options priced in during the recent period — a regime where condor sellers lose money structurally. Do not open new positions when VRP turns negative; tighten stops on existing ones immediately.

---

## 4. Red Flags — When NOT to Trade

These conditions override favorable screener readings. If any is present, do not enter.

- **ADX > 40:** The underlying is in a strong directional move. One leg of your condor will be tested almost immediately. A credit of $2.50 is not worth the near-certain test.

- **VIX > 45:** This is a fear regime. August 2024 touched VIX 65 intraday; April 2025 briefly cleared VIX 50 on tariff headlines. Wings priced at "one standard deviation" become meaningless when realized vol is running at 3–4 standard deviations daily. Sit on hands and wait for ADX to begin declining.

- **VRP negative:** Realized vol is exceeding implied. You are selling underpriced insurance. Historical loss rates for iron condor sellers spike sharply in negative-VRP environments regardless of IVR.

- **Earnings within the hold window:** A 30-DTE condor opened with earnings 15 days out will reprice violently on the event. The screener's ATM IV will look elevated — it is, because of the earnings premium — but that premium vaporizes post-event, often with a large directional gap. The high IV is a trap, not an opportunity.

- **ATR% > 2.0% and rising:** Even without a trend, expanding daily ranges will test your short strikes repeatedly through a 30-day hold. An underlying moving 2%+ daily needs strikes far enough out that the credit drops below the 1/3 width rule.

---

## 5. VIX Regime Context

| VIX Level | Regime | IC Strategy |
|---|---|---|
| 14–20 | Low vol | Credits thin; IVR and VRP filters become critical — only trade best setups |
| 20–30 | Sweet spot | Best risk/reward for balanced condors; standard sizing |
| 30–45 | Elevated | Widen short strikes by 15–20%; reduce size by 30–40%; shorten to 21 DTE |
| > 45 | Danger zone | No new iron condors; manage or close existing positions aggressively |

In low-vol regimes (VIX 14–17), the IVR filter becomes your most important tool. A $0.60 credit on a well-positioned condor in a genuinely range-bound SPY beats a $1.40 credit on a name with ADX 38. The absolute credit level is less important than whether the structural edge is present.

---

## 6. Practical Usage Tips

**Run the screener weekly, not daily.** Most new IC entries are opened with 25–35 DTE. Forcing daily entries creates overtrading in marginal setups. Sunday evening or Monday pre-market is the optimal review cadence.

**Limit concurrent ICs to 3–5 maximum** until you have a full year of personal trade history. Correlation spikes in selloffs — five "uncorrelated" condors can breach simultaneously in a broad market move. What looks like diversification on the screener is often correlation that only manifests under stress.

**Size each IC at 2–3% of account at max loss.** This lets you absorb three simultaneous breaches without a portfolio-level wound that impairs your judgment on future entries.

**When 3 of 5 filters pass:** Reduce position size by 40% and set a tighter stop — close if the underlying moves more than 60% of the distance to the short strike within the first 10 days.

**Roll, don't panic.** If one side is tested but you have 10+ DTE and the untested side still has meaningful premium (below 10-delta), rolling the tested side out one expiration and further OTM (at a net credit if possible) is often superior to taking a full loss. Rolling is appropriate when: (1) you have 10+ DTE remaining, (2) the untested side is still worth keeping, and (3) you can roll the tested side at a net credit of $0.30+.

**Theta accelerates fastest in the final 21 days.** Entries at 28–35 DTE maximize the benefit of this acceleration while maintaining a reasonable buffer against early adverse moves. Beyond 45 DTE, gamma risk is low but theta harvest is slow; under 21 DTE, theta is fastest but gamma risk makes management more difficult.

**After a VIX spike above 35**, the screener will populate with high-IVR tickers. Resist the temptation to enter immediately. Wait for ADX to begin declining (typically 3–5 days after the VIX peak) before entering — catching a falling vol knife on day 1 of a VIX spike is a classic trap.

---

## 7. Common Mistakes

1. **Chasing high credit without checking ADX.** A name paying $2.50/share looks attractive until ADX is 48 and the stock has been trending cleanly for six weeks. The credit reflects the trend risk — it is correct pricing, not an opportunity.

2. **Ignoring earnings dates.** The screener cannot know your intended hold period. Always cross-reference the next earnings date before entering any single-stock IC. The tool shows current conditions; the calendar is your responsibility.

3. **Over-diversifying into correlated underlyings.** Running ICs on SPY, QQQ, and IWM simultaneously provides almost no true diversification. In any broad market selloff, all three breach simultaneously. True IC diversification requires selecting names from different macro sectors with low recent correlation.

4. **Treating IVR = 0.40 as a rigid floor.** In persistently low-vol environments (2017, 2024 Q1), IVR 0.40 may still represent historically cheap premium because the entire IV history is compressed. Pair IVR with VRP to confirm the structural opportunity is real, not just a historical artifact.

5. **Holding through expiration week.** The final 5 days carry outsized gamma risk relative to remaining premium. Unless you are actively watching intraday prices and delta, closing at 5–7 DTE for 65–70% of max profit is a sound mechanical rule that significantly improves long-run Sharpe. The final $50–$80 of premium per contract is not worth the gamma exposure.
