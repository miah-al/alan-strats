# How to Use This Iron Condor Screener

## 1. How to Read the Screener

Each column is a filter, not a standalone signal. Read them together.

| Column | What It Measures | Good Range for ICs |
|--------|-----------------|-------------------|
| **IVR** | Where today's IV sits in its 52-week range (0 = 52-week low, 1 = 52-week high) | > 0.40 |
| **VRP** | IV minus realized volatility (vol points). Positive = options are expensive relative to actual movement | > 2.0 vol pts |
| **ATM IV** | Current annualized implied volatility at the money | Context-dependent (see VIX banner) |
| **ADX** | Average Directional Index — measures trend strength, not direction | < 25 (range-bound) |
| **ATR%** | Average True Range as % of price — daily velocity | < 1.5% preferred |
| **VIX** | CBOE fear gauge — proxy for broad market regime | 20–30 sweet spot |
| **Credit** | Approximate premium collected per share for a balanced IC | Higher is better, but not at the cost of narrow strikes |

**IVR > 0.40** means IV is in the top 60% of its annual range — you are selling volatility that is historically elevated, which is the foundation of the trade. IVR 0.60+ is a strong signal. IVR below 0.30 means you are selling cheap premium; the risk/reward deteriorates.

**ADX < 25** means the underlying is chopping sideways. Iron condors bleed premium in range-bound markets and get steamrolled in trends. An ADX of 18 is ideal. An ADX of 35 is a caution. Above 40, walk away.

---

## 2. What Makes a Good IC Entry

The ideal setup stacks at least four of the five signals. A single strong reading is not enough.

**Example of a near-perfect setup — SPY, typical late-summer environment:**

- IVR = 0.55 (IV in top 45% of range)
- VRP = +4.5 vol points (IV running well above 30-day realized)
- ADX = 18 (no dominant trend)
- ATR% = 0.85% (calm daily movement)
- VIX = 22 (moderate fear, decent credits without chaos)
- Credit = $1.40/share on a 30-DTE balanced condor

This is a green-light setup. Place strikes one standard deviation out, collect the credit, and let theta work.

**Three signals passing, one borderline** (e.g. IVR = 0.38): reduce size by half or wait for a better entry. The screener is a queue, not a forced entry system.

---

## 3. Reading VRP — The Overlooked Edge

Variance Risk Premium is the spread between what the market *implies* will happen (IV) and what actually happened (realized vol). When VRP is positive, option sellers are collecting a structural risk premium — analogous to an insurance company charging more than actuarial fair value.

**VRP is positive roughly 70% of the time on SPY and QQQ.** That is the long-run edge of systematic vol selling. The problem is the other 30%: those periods tend to cluster around sudden dislocations (Aug 2024 carry unwind, Apr 2025 tariff shock) where realized vol explodes past IV.

**When VRP matters more than IVR:** Use VRP as your primary filter in slow-drift IV environments where IVR is middling (0.35–0.50). If VRP is running +5 to +8 vol points in that window, the market is paying you significantly more than the recent historical movement justifies. That is the real edge.

**Negative VRP** is a serious warning. It means the market moved *more* than options priced in — a regime where IC sellers lose money structurally. Do not open new positions when VRP turns negative; tighten stops on existing ones.

---

## 4. Red Flags — When NOT to Trade

- **ADX > 40:** The underlying is in a strong directional move. One leg of your condor will be tested immediately. Skip it.
- **VIX > 45:** This is a fear regime. Aug 2024 touched 65 intraday; Apr 2025 briefly cleared 50 on tariff headlines. Wings priced at "one standard deviation" become meaningless when vol term structure collapses and gaps become routine. Sit on hands.
- **VRP negative:** Realized vol is exceeding implied. You are selling underpriced insurance. Historical loss rates for IC sellers spike sharply in negative-VRP environments.
- **Earnings within the hold window:** A 30-DTE condor opened with earnings 15 days out will reprice violently on the event. The screener's ATM IV will look elevated (it is — because of the earnings premium), but that premium vaporizes post-event, often with a large directional gap attached.
- **ATR% > 2.0% and rising:** Intraday ranges are expanding. Even without a trend, wide daily swings will test your short strikes repeatedly through a 30-day hold.

---

## 5. Regime Context — The VIX Banner

| VIX Level | Regime | IC Strategy |
|-----------|--------|-------------|
| 14–20 | Low vol | Credits thin; be highly selective; IVR filter becomes critical |
| 20–30 | Sweet spot | Best risk/reward for balanced condors; standard sizing |
| 30–45 | Elevated | Widen strikes by 15–20%; reduce size; shorter DTE (21 days) |
| > 45 | Danger zone | No new ICs; manage or close existing positions |

In low-vol regimes, prioritize IVR and VRP over credit size. A $0.60 credit on a well-positioned SPY condor beats a $1.20 credit on a name with ADX of 38.

---

## 6. Practical Tips

- **Run 3–5 concurrent ICs maximum** until you have a full year of personal trade history. Correlation spikes in selloffs — five "uncorrelated" condors can all breach simultaneously.
- **Size each IC at 2–3% of account risk** (max loss on the spread, not notional). This lets you absorb three simultaneous breaches without a portfolio-level wound.
- **Check the screener weekly**, ideally Sunday evening or Monday pre-market. Most new IC entries are opened with 25–35 DTE; forcing daily entries creates overtrading.
- **When 3 of 5 filters pass,** reduce position size by 40% and set a tighter stop — close if the underlying moves more than 60% of the distance to the short strike within the first 10 days.
- **Roll, don't panic.** If one side is tested but you have 10+ days to expiration and the untested side still has meaningful premium, rolling the tested side out one expiration and up/down toward the market is often superior to closing for a full loss.
- **Theta is fastest in the final 21 days.** The screener's credit column matters most for entries at 28–35 DTE. Beyond 45 DTE, gamma risk is low but theta harvest is slow.
- **After a VIX spike above 35, the screener will light up with high-IVR tickers.** Wait for ADX to begin falling before entering — catching a falling vol knife is a classic mistake.

---

## 7. Common Mistakes

1. **Chasing high credit without checking ADX.** A name paying $2.50/share looks attractive until you notice ADX is 48 and the stock has been in a clean uptrend for six weeks. The credit reflects the trend risk.

2. **Ignoring earnings dates.** The screener cannot know your intended hold period. Always cross-reference the next earnings date before entering any single-stock IC.

3. **Over-diversifying into correlated names.** Running ICs on SPY, QQQ, and IWM simultaneously provides almost no diversification. In a broad selloff all three breach together.

4. **Treating IVR = 0.40 as a hard floor.** In a persistently low-vol environment (e.g. most of 2017, much of 2024 Q1), IVR 0.40 may still represent historically cheap premium. Pair IVR with VRP to confirm the opportunity is real.

5. **Holding through expiration week.** The final 5 days of a condor carry outsized gamma risk relative to the remaining premium. Unless you are actively watching intraday, closing at 5–7 DTE for 60–70% of max profit is a sound mechanical rule that significantly improves long-run Sharpe.
