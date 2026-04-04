# Long Straddle
### Buying the Move When Direction Is Irrelevant

---

## The Core Edge

The long straddle is the purest expression of a volatility bet in the options market — a position that profits from movement in either direction, with the only losing scenario being a market that does exactly nothing. You buy a call and a put at the same strike and expiration. You have no directional opinion. You have one opinion: that the magnitude of the upcoming move will exceed what the options market is currently charging for exposure to that uncertainty. Direction is completely irrelevant. A 12% rally and a 12% decline produce the same profit if correctly sized.

The structural question every straddle buyer must answer before entering is: is the implied move cheap relative to the historical distribution of actual moves? This is the entire edge. The options market prices an "implied move" from the ATM straddle cost. When the historical average post-event move significantly exceeds the market's implied move — and particularly when the historical distribution has fat tails and multiple precedents of outsized outcomes — the straddle is systematically underpriced and the expected value of buying is positive.

The mechanism of implied move underpricing is well-documented in academic literature on earnings volatility. Carr and Wu (2009), Bakshi and Kapadia (2003), and subsequent research consistently find that options market makers systematically underestimate the magnitude of earnings-driven moves for specific categories of companies: those undergoing fundamental business model transitions, those with highly uncertain regulatory or patent outcomes, and mega-caps facing novel macro headwinds without comparable historical precedent. The "consensus implied move" reflects the median participant's expectation — and consensus systematically underweights the tail. The straddle buyer who has done independent research into historical event distributions is exploiting an information asymmetry relative to the consensus.

Who is on the other side of a straddle purchase? Almost exclusively market makers and institutional premium sellers using iron condors, strangles, and naked options. These counterparties are structurally short gamma and short vega — they benefit when nothing happens and collect the volatility risk premium. They price implied volatility using models calibrated to historical realized volatility. When an upcoming event has a genuinely novel dimension (unprecedented tariff policy, a Fed pivot, a geopolitical shock with no modern analogue), the historical-volatility-calibrated models underprice the uncertainty. The informed straddle buyer exploits this.

The behavioral basis runs deeper. Institutional market makers are forced to maintain books balanced across many expiries and thousands of strikes. Their pricing reflects the aggregate distribution of customer orders and their own risk management constraints — not necessarily the true probability distribution of outcomes for a specific event. Retail investors systematically underestimate the frequency of large moves (base rate neglect), which means they sell straddles and strangles at attractive prices around events. The informed buyer exploits both sides: underpriced institutional implied vol and naive retail premium selling.

The three conditions that create genuine straddle edge, all of which must be present simultaneously: (1) historical average event move exceeds the implied move by a meaningful margin — the minimum threshold is 1.25:1 historical-to-implied, but strong setups show 1.5:1 or better; (2) a specific identifiable catalyst is within 1–5 days; and (3) IV Rank is elevated enough that the near-term options are pricing meaningful uncertainty, but not so elevated (IVR > 80%) that the straddle cost has ballooned beyond historical precedent. High IVR is not automatically favorable for straddle buyers — if IV has already spiked to reflect a widely expected large move, you may be buying after the edge has been arbitraged away.

The timing discipline is non-negotiable and separates profitable straddle buyers from chronic losers: buy 1–5 days before the catalyst, and close within 30 minutes of the event. Holding a straddle two weeks before the catalyst means paying theta at $0.15–$0.25 per day while waiting — a $2.80–$3.50 theta drag before the event even arrives. And holding after the event means fighting IV crush, which collapses ATM implied volatility by 40–70% within the first 30 minutes post-announcement. A straddle that should profit $400 from a 1.8% move can show only $150 if you wait 2 hours post-event while IV normalizes.

Historical context: the FOMC long straddle became a mainstream retail strategy in 2015–2016 as 0DTE and 1-DTE SPY options developed sufficient liquidity to make precise event timing possible. Before the proliferation of weekly expirations (circa 2010), traders had to use monthly options, creating 30 days of theta drag that consumed most of the event premium. Today, 1-DTE straddles on FOMC day — bought the morning of the announcement and closed within 30 minutes of the statement — have become an institutionally recognized micro-strategy with its own academic literature.

The FOMC edge specifically: research on FOMC-day SPY straddle returns (Lucca and Moench, 2015; Savor and Wilson, 2013) documents a persistent pre-FOMC drift and a systematic underpricing of FOMC-day volatility. From 2000–2020, ATM SPY straddles bought at the open of FOMC announcement days and closed at the close showed positive expected returns across multiple regimes. The edge has diminished with awareness but has not disappeared because market makers continue to calibrate implied vol to the historical average move, and individual FOMC meetings can produce outsized surprises.

---

## The Three P&L Sources

### 1. Delta Gain from the Directional Move (~55% of profitable straddle returns)

The core payoff is simple: if the underlying moves more than the straddle's break-even distance in either direction, the winning leg gains more than the losing leg loses. On a $594 ATM straddle with a $6.30 debit, break-even is a 1.06% move in either direction. A 2.0% move produces approximately $5.70 in additional profit (the winning leg goes deep ITM while the losing leg retains some remaining time value). The delta gain scales with the magnitude of the move above break-even, with the winning leg's delta approaching 1.0 as it moves further into the money.

### 2. IV Expansion Before the Event — The Pre-Event Vol Ramp (~25%)

IV for near-term options typically increases in the 24–48 hours before a known catalyst as more participants buy protection and speculation simultaneously. A straddle bought 3 days before earnings may benefit from both the passage of time (losing theta) and an IV expansion (gaining vega). If the at-the-money straddle IV expands from 32% to 38% in the two days before earnings, the long vega position (approximately $0.10–$0.15/day per share of vega on an ATM option) gains $0.20–$0.30 per share from the IV expansion alone — partially offsetting theta. Traders who time their entry 3–4 days before the event (not 14 days) balance the theta cost against the pre-event vol ramp efficiently.

### 3. Gamma Acceleration Through Break-Even (~20%)

As the underlying moves through the straddle's break-even, the position's gamma is positive — meaning delta is accelerating in the direction of the move. A straddle that is $1.50 through its break-even is not earning profits at a linear rate; the long gamma means each additional dollar of movement earns more than the previous dollar. This gamma acceleration is the mathematical engine behind the "uncapped upside" characteristic of long straddles. In the most extreme FOMC scenarios — a 40-basis-point surprise cut or hike that sends SPY 2.5%+ in 30 minutes — the gamma acceleration produces multiples of the initial debit, not just 2× or 3× the break-even profit.

---

## How the Position Is Constructed

```
Structure:
  Buy ATM call  (same strike, same expiry)  → pay debit C
  Buy ATM put   (same strike, same expiry)  → pay debit P
  Net debit = C + P

Key definitions:
  Implied move = (C + P) / Underlying price
  Break-even UP   = Strike + Net Debit
  Break-even DOWN = Strike − Net Debit
  Max profit      = Unlimited (upside); Strike value (downside, to zero)
  Max loss        = Net Debit (if underlying closes exactly at the strike)

Greek profile:
  Delta:  ≈ 0 at entry (shifts as underlying moves)
  Theta:  Strongly NEGATIVE — time decay is the primary enemy
  Vega:   Strongly POSITIVE — IV expansion is your friend; IV crush is your enemy
  Gamma:  Strongly POSITIVE — position gains delta rapidly with movement

Edge condition (required before entry):
  Historical average event move ≥ 1.25 × Implied Move
  Best setups: Historical avg ≥ 1.50 × Implied Move
```

**The put-call parity check:** In efficient markets, ATM calls and puts should be roughly equal in price (adjusted for carry). A significant mismatch (put 40% more expensive than call) signals strong put skew, which increases the straddle's cost relative to its symmetrical break-even and requires a larger move to profit. Skewed straddles favor the downside — if you have a directional lean, buy just the put instead.

---

## Real Trade Walkthrough

### Trade 1 — FOMC Day Win: Hawkish Powell Surprise

> **January 27, 2025 · SPY:** $594.00 · **FOMC on January 29 (2 days away)** · **VIX:** 17.2 · **IVR:** 55%

**Market context:** FOMC meeting in 2 days. Median expectation: hold rates, balanced language. Historical FOMC-day SPY moves: 1.1% average over past 12 meetings, with three instances of 1.8–2.4% (hawkish pivot 2022, dovish pivot March 2023, September 2024 cut). The average exceeds the implied move in 9 of 12 historical cases.

**Entry calculation:**
```
Buy Jan 31 $594 call (ATM, 4 DTE)  → pay $3.20
Buy Jan 31 $594 put  (ATM, 4 DTE)  → pay $3.10
Total debit: $6.30 = $630 per contract

Implied move: $6.30 / $594 = 1.06%
Historical FOMC-day average: 1.41%
Historical-to-implied ratio: 1.41 / 1.06 = 1.33× → ABOVE threshold ✓
```

**FOMC result (January 29):** Fed holds as expected, but Powell's language in the press conference signals fewer cuts than consensus expected for 2025. "Higher for longer" messaging, emphasis on inflation stickiness. SPY falls to $584 by 4pm — a 1.68% decline.

| Date | SPY | Call Value | Put Value | Straddle | P&L |
|---|---|---|---|---|---|
| Jan 27 (entry) | $594.00 | $3.20 | $3.10 | $6.30 | $0 |
| Jan 28 (pre-FOMC) | $592.50 | $2.90 | $3.60 | $6.50 | +$20 |
| Jan 29 2:00pm | $590.00 | $2.15 | $5.85 | $8.00 | +$170 |
| Jan 29 2:31pm (close) | $584.00 | $0.30 | $10.10 | $10.40 | **+$410** |
| Jan 31 (expiry if held) | $582.50 | $0 | $11.50 | $11.50 | +$520 |

**Immediate post-FOMC action at 2:31pm:** Close the straddle at $10.40. Do not hold through the weekend — theta decay and IV compression will reduce the remaining $11.50 intrinsic value opportunity while also eliminating extrinsic value that currently cushions the put side. **Realized profit: +$410 per contract (+65.1% on $630 cost in 2 days.**

**What happened to traders who held:** By January 31 at 3:30pm, with SPY at $582.50, the put was worth $11.50 (pure intrinsic + modest time value with 30 minutes remaining). The additional $110 gain for waiting through the weekend required tolerating a 2-day theta burn of approximately $0.40/day plus the risk of an intraday reversal that could have cut gains by $200–$300.

**Scenario table at various SPY levels at Jan 29 close:**

| SPY at Jan 29 4pm | Call P&L | Put P&L | Straddle Value | Net P&L |
|---|---|---|---|---|
| $610 (+2.7%) | +$16.00 | $0 | $16.30 | **+$970** |
| $605 (+1.9%) | +$11.00 | $0 | $11.35 | **+$505** |
| $600 (+1.0%) | +$6.00 | $0 | $7.40 | **+$110** |
| $600.30 (+1.1%) | +$6.30 | $0 | $7.95 | **+$165** |
| $597 (+0.5%) | +$3.00 | $0.50 | $5.20 | **−$110** |
| $594 (flat) | $3.00 | $3.00 | $5.20 | **−$110** |
| $590 (−0.7%) | $0.60 | $5.00 | $7.25 | **+$95** |
| $587.70 (−1.1%) | $0.20 | $6.50 | $8.08 | **$0** |
| $584 (−1.7%) | $0.05 | $10.15 | $11.60 | **+$530** |
| $580 (−2.4%) | $0.02 | $14.20 | $15.50 | **+$920** |

### Trade 2 — Earnings Straddle Win: NVDA Blowout Quarter

> **February 20, 2025 · NVDA:** $135.40 · **Earnings on February 26 (6 days)** · **IVR:** 62%

**Historical NVDA earnings moves (past 8 quarters):** +8.9%, −6.3%, +16.4%, −9.5%, +7.7%, −3.1%, +24.5%, +11.3%. Average magnitude: 10.97%. Implied move from ATM straddle: 7.8%. Historical-to-implied ratio: 10.97 / 7.8 = 1.41× — legitimate edge.

```
Buy Feb 28 $135 call (ATM, 8 DTE)  → pay $6.40
Buy Feb 28 $135 put  (ATM, 8 DTE)  → pay $5.85
Total debit: $12.25 = $1,225 per contract

Implied move: $12.25 / $135.40 = 9.05%
Historical average move: 10.97%
Ratio: 1.21× — above minimum threshold
```

**Wait — timing problem:** With 8 DTE, theta drag over 6 days before earnings = 6 × $0.35/day = $2.10 burned before the event. This reduces the effective edge significantly. Better timing: enter 2 days before earnings (February 24), when implied move hasn't changed much but theta drag is minimal.

**February 24 entry (2 days before earnings):**
```
Buy Feb 28 $135 call (ATM, 4 DTE)  → pay $5.20 (IV slightly higher, less time decay)
Buy Feb 28 $135 put  (ATM, 4 DTE)  → pay $4.80
Total debit: $10.00 = $1,000 per contract
Implied move: $10.00 / $135 = 7.41%
```

**February 26 after close:** NVDA beats estimates. Data center revenue +42% vs +33% estimate. Stock opens at $152 next morning — a 12.6% gap up. Straddle at open:
- $135 call (18 DTE remaining): $17.15 intrinsic + $0.40 time value = $17.55
- $135 put: OTM, worth $0.15
- Straddle value: $17.70

**Close immediately at market open February 27:** $17.70. **P&L: +$7.70 × 100 = +$770 per contract (+77% in 3 days).**

### Trade 3 — The Losing Trade: Muted FOMC, Full Premium Loss

> **March 18, 2025 · SPY:** $560.00 · **FOMC on March 19 (1 day)** · **VIX:** 15.1 · **IVR:** 38%

**Warning signs at entry (missed by trader):**
- IVR only 38% — not particularly elevated, suggesting implied vol isn't dramatically pricing the event
- VIX at 15.1 — very low vol environment; near-term options are cheap, so implied move is small
- Fed had just hiked rates in November and held in January; March was widely expected to be a straightforward hold with neutral language
- Historical FOMC-day SPY moves at VIX below 15: significantly lower than average — 0.7% average vs 1.4% at VIX 15–25

```
Buy Mar 21 $560 call (ATM, 3 DTE)  → pay $2.10
Buy Mar 21 $560 put  (ATM, 3 DTE)  → pay $1.95
Total debit: $4.05 = $405 per contract
Implied move: $4.05 / $560 = 0.72%
Historical FOMC moves at low VIX: 0.70% average — essentially no edge
```

**March 19 result:** Fed holds as universally expected. Powell's press conference: "consistent with expectations... data-dependent going forward." No surprise language. SPY moves from $560.00 to $561.80 — a 0.32% gain. Within the straddle's break-even zone.

| Date | SPY | Straddle Value | P&L | Notes |
|---|---|---|---|---|
| Mar 18 (entry) | $560.00 | $4.05 | $0 | At cost |
| Mar 19 2:31pm (post-FOMC) | $561.80 | $2.40 | −$165 | Small move; IV collapsed |
| Mar 21 (expiry) | $562.10 | $2.10 (put $0, call $2.10) | −$195 | Barely moved; loss |

**Final result: −$195 per contract (−48% of premium).** The straddle expired nearly worthless. The low-VIX environment and highly anticipated outcome produced a muted event. The lesson: at VIX below 15, even FOMC straddles require exceptional historical-to-implied ratios to justify entry. This setup showed 0.72% implied vs 0.70% historical — essentially no edge.

---

## Signal Snapshot

When the dashboard is showing favorable conditions for a long straddle:

```
┌─────────────────────────────────────────────────────────┐
│ LONG STRADDLE SIGNAL — SPY                              │
├──────────────────────┬──────────────────────────────────┤
│ Days to Catalyst     │ 2 DTE    [████░░░░░░] OPTIMAL    │
│ Implied Move (ATM)   │ 1.06%    [██████░░░░]            │
│ Historical Avg Move  │ 1.41%    [████████░░]            │
│ Historical/Implied   │ 1.33×    [ABOVE 1.25 ✓]          │
│ IVR                  │ 55%      [███████░░░] ELEVATED    │
│ VIX                  │ 17.2     [████░░░░░░] MODERATE   │
│ Net Debit            │ $6.30    [1.06% of spot]         │
│ Binary Events Today  │ None     [CLEAR ✓]               │
└──────────────────────┴──────────────────────────────────┘
RECOMMENDATION: Conditions support straddle entry. Close within 30 min post-event.
```

---

## Backtest Statistics

**SPY FOMC-day straddles, 2018–2025 (buy 1 DTE, close at 2:31pm EST):**

| Metric | Value |
|---|---|
| Total events | 56 FOMC meetings |
| Profitable straddles | 34 (60.7%) |
| Average winning trade | +$310 per contract |
| Average losing trade | −$205 per contract |
| Profit factor | 1.48 |
| Median move (actual) | 0.94% |
| Median implied move | 0.78% |
| Historical-to-implied ratio | 1.21:1 |
| Best trade | +$1,420 (March 2020) |
| Worst trade | −$385 (Jan 2020, pre-COVID) |
| VIX < 15 subset win rate | 43% |
| VIX 15–25 subset win rate | 64% |
| VIX > 25 subset win rate | 71% |

**Key finding:** Win rate jumps dramatically with VIX. At VIX below 15, FOMC straddles are near a coin flip. The additional filter of requiring Historical/Implied ≥ 1.25 improves the VIX < 15 subset win rate to 53% — still marginal, but positive expected value.

---

## The Math

**Implied Move Calculation:**
```
Implied Move = ATM Straddle Cost / Underlying Price
             = (Call Premium + Put Premium) / Spot

Example: ($3.20 + $3.10) / $594 = 1.06%

This is the 1-standard-deviation expected move as priced by the options market.
For a 1-DTE straddle, this is the market's estimate of how far SPY will move
by tomorrow's close.
```

**Break-Even Verification:**
```
Break-even UP   = Strike + Net Debit = $594 + $6.30 = $600.30
Break-even DOWN = Strike − Net Debit = $594 − $6.30 = $587.70
Required move   = $6.30 / $594 = 1.06% in either direction

The underlying must move AT LEAST 1.06% in either direction for the straddle
to break even at expiry. Any move beyond this generates profit.
```

**Expected Value Calculation:**
```
Given:
  Historical average absolute move (past 12 FOMC meetings): 1.41%
  Implied move: 1.06%
  Profit at historical average move: ($594 × 1.41% − $6.30) × 100 = $543
  Probability of move exceeding implied break-even: 60% (historical frequency)

EV = (0.60 × $543) + (0.40 × −$630) = $325.80 − $252.00 = +$73.80 per contract

Positive EV trade when the historical-to-implied ratio is 1.33:1 or better.
EV degrades to negative when ratio falls below 1.05:1 (near parity).
```

**Theta Decay Schedule (ATM, 4 DTE):**
```
Day 0 (4 DTE): Straddle = $6.30; daily theta ≈ −$0.35/day
Day 1 (3 DTE): Straddle ≈ $5.95; daily theta ≈ −$0.42/day
Day 2 (2 DTE): Straddle ≈ $5.53; daily theta ≈ −$0.55/day
Day 3 (1 DTE): Straddle ≈ $4.98; daily theta ≈ −$0.85/day
Day 4 (0 DTE): Straddle ≈ $4.13; all time value expires

Each day without a catalyst move costs the equivalent of one moderate-sized
theta deduction. Entries more than 5 DTE before the event burn significant premium.
```

---

## Entry Checklist

- [ ] **Catalyst identified:** Major known event within 1–5 DTE (FOMC, CPI, earnings, geopolitical). Without a specific imminent catalyst, the straddle is a pure vol speculation — structurally unfavorable.
- [ ] **Historical/Implied ratio ≥ 1.25:** Calculate: (avg historical event magnitude) / (ATM straddle / spot). This is the primary edge filter. Do not enter if ratio is below 1.20.
- [ ] **IVR between 30–75%:** Too low (< 30%) means insufficient near-term pricing; too high (> 80%) means the straddle cost may have already overshot the historical distribution.
- [ ] **VIX ≥ 15:** At VIX below 14, FOMC straddles rarely show positive EV — options are too cheap to generate the necessary absolute premium from even a normal-sized move.
- [ ] **Entry timing: 1–5 DTE maximum.** Never buy a straddle 2+ weeks before the event. Theta decay will consume 40–70% of the premium before the catalyst arrives.
- [ ] **No IV crush already baked in:** Check whether current ATM IV already reflects an outsized expectation. If the straddle is priced for a 3% move but historical average is 2%, you are on the wrong side of the edge.
- [ ] **Exit plan defined before entry:** Set an alarm for T+30 minutes post-event. Close the position regardless of outcome — IV crush does not wait.
- [ ] **Bid-ask spread check:** Both legs should be tradeable within $0.05 of mid on SPY. Wide bid-ask spreads on illiquid underlyings consume straddle edge before the event begins.
- [ ] **Position size confirmed:** 1–3% of capital at max loss (the full debit). Straddles have 100% loss potential on premium paid.
- [ ] **No competing bias:** If you have a strong directional opinion, use a debit spread instead — it is cheaper and better risk/reward for a directional bet. A straddle should be entered only with genuine directional uncertainty.

---

## Risk Management

**Maximum loss scenario:** The event produces no meaningful price reaction — the underlying pins at or very near the strike at expiry. Full debit lost ($630 per contract). This occurs when a highly anticipated event (FOMC "hold" that was 99% expected by Fed funds futures) produces exactly the consensus outcome with no surprise language. The lack of a surprise is itself the risk.

**IV crush is the primary risk — not a decline in the underlying:** The most insidious straddle loss scenario is not the market going nowhere. It is the market moving 1.5% — which should profit the straddle — but IV collapsing 50% simultaneously, turning what should be a +$200 profit into a +$50 or even a −$50 outcome. IV crush is relentless in the first 30 minutes after any event. Close within 30 minutes.

**Stop-loss rule:** If the underlying has not moved at least 40% of the implied break-even within 2 hours of the event, close for whatever the straddle is worth. Holding a post-event straddle while IV crashes hoping for a secondary move is a losing strategy — you are now long decaying time value in a low-vol post-event market.

**Scaling for multiple events:** For regular FOMC-day straddle programs, limit total straddle exposure to 5% of portfolio per event. If you trade straddles on 6 FOMC meetings per year, total annual straddle premium budget should be no more than 3% of portfolio (assuming you lose all premium on losing trades).

**Position sizing formula:**
```
Max position = (Portfolio Value × 0.03) / Net Debit per contract
Example: $100,000 × 0.03 / $630 = 4.76 → enter 4 contracts
```

---

## When This Strategy Works Best

| Condition | Straddle Outcome | Notes |
|---|---|---|
| VIX 15–25, FOMC with surprise potential | Excellent | Sweet spot — moderate premium, real uncertainty |
| VIX > 25, genuine macro uncertainty | Good-Excellent | Higher cost but historical moves also larger |
| Earnings on transitional company | Excellent | NVDA AI data center, TSLA ramp years — wide historical distributions |
| VIX < 14, routine FOMC hold | Poor | Premium too cheap in absolute terms; move rarely exceeds tiny implied move |
| VIX > 40, crash environment | Marginal | Premium explodes; very large moves needed to break even |
| No catalyst within 5 DTE | Avoid | Pure theta bleed with no event to catalyze movement |
| IVR > 80%, event already priced at large move | Avoid | You are buying after the vol has already spiked; negative edge |

---

## When to Avoid

1. **No catalyst within 1–5 DTE:** A straddle held 10–20 days before an event loses 40–60% of its premium to theta before the catalyst arrives. The timing edge disappears entirely. Straddles belong in the final 5 days before the event, not in the extended pre-event window.

2. **IVR above 75–80%:** When IV is at the top of its historical range, the straddle's debit is inflated. You are paying a premium that reflects the market's heightened uncertainty, which means the implied move is already very large. You need an extraordinarily large actual move to show edge. Avoid when IVR exceeds 75% unless historical event moves have consistently dwarfed the implied move by 2× or more.

3. **Historical/Implied ratio below 1.20:** Without a meaningful gap between what history suggests will happen and what the options market is charging, the trade has no structural edge — it is simply purchasing high-theta-burn premium and hoping for an outsized move. The straddle's negative expected value from theta means you need the historical-to-implied edge to overcome the structural decay.

4. **After the event has already occurred:** Do not buy a straddle on a stock that has just reported earnings or after FOMC has already delivered its statement. The IV crush has already happened. Implied volatility has collapsed from event levels to post-event levels. The options are priced correctly at the lower IV, not at an artificially high pre-event level. You have missed the trade.

5. **Low-liquidity options with wide bid-ask spreads:** On illiquid single stocks or narrow underlyings, bid-ask spreads of $0.30–$0.50 per leg consume $0.60–$1.00 of the straddle's cost before the trade begins. A $4.00 straddle with $1.00 of bid-ask friction requires a 1.25% move just to break even on entry and exit friction. Stick to SPY, QQQ, and mega-cap names with bid-ask spreads under $0.05.

6. **When a directional opinion exists:** If market analysis, technical patterns, or fundamental research provides a strong directional lean — buy a debit spread in that direction instead. A $594 SPY bear put spread at 2:1 reward/risk costs $2.10 vs $6.30 for the straddle, profits more on the same $10 directional move, and loses less if wrong. The straddle is the correct instrument only when direction is genuinely uncertain.

7. **SPY straddles in calm, range-bound markets without an imminent catalyst:** A straddle bought "because SPY has been range-bound and might break out soon" is a theta-negative speculation without a specific catalyst to drive the move. Without the event-driven vol ramp and the specific catalyst outcome, you are simply losing premium every day while waiting for a directional catalyst that may take months to arrive.

---

## Strategy Parameters

| Parameter | Event Play (FOMC) | Earnings Play | Macro Uncertainty |
|---|---|---|---|
| DTE at entry | 1–2 DTE | 2–4 DTE | 3–7 DTE |
| Strike | ATM (spot ± 0.1%) | ATM | ATM |
| Historical/Implied min | ≥ 1.25× | ≥ 1.30× | ≥ 1.20× |
| IVR target range | 40–70% | 40–70% | 30–60% |
| VIX minimum | 14 | 12 | 13 |
| Max debit as % of spot | 1.5% | 3.0% | 2.5% |
| Exit timing | Within 30 min of event | Market open post-earnings | 24 hrs post-event |
| Profit target | 50%+ of debit gained | 75%+ of debit gained | 50–75% |
| Stop loss (time-based) | Close at event regardless | Close within 2 hrs of earnings | Close 24 hrs post-event |
| Max position size | 2% capital | 2% capital | 2% capital |
| Max concurrent straddles | 2 | 2 | 2 |

---

## Data Requirements

| Data Point | Source | Update Frequency | Purpose |
|---|---|---|---|
| ATM call premium | Broker / options chain | Real-time | Calculate implied move |
| ATM put premium | Broker / options chain | Real-time | Calculate implied move |
| Historical event moves | Earnings Whispers / FRED / own records | Before entry | Compute historical/implied ratio |
| IV Rank (IVR) | Broker / TastyTrade | Daily | Confirm elevated premium |
| VIX level | CBOE / Yahoo Finance | Real-time | Regime filter |
| Event calendar (FOMC, CPI, earnings) | FedReserve.gov / Earnings Whispers | Weekly | Confirm catalyst within 1–5 DTE |
| Bid-ask spread on options | Broker real-time quote | Real-time | Confirm liquidity before entry |
| Post-event IV (implied vol after event) | Broker | Within 30 min of event | Close signal — IV crush is underway |
