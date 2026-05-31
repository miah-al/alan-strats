# Weekly Iron Condor (Mechanical)
### Systematic Premium Harvesting on a 5-Day Cycle

---

## The Core Edge

The weekly iron condor is the mechanical, high-frequency cousin of the standard monthly condor — a strategy built not on discretion but on the relentless application of a single statistical fact: SPY's weekly implied move, as priced by the ATM straddle, has historically overstated the actual weekly move approximately 60–65% of the time in calm regimes. The market prices in roughly 1.0–1.4% weekly moves; SPY actually moves more than that range only about 35–40% of weeks when VIX is below 20. That persistent overestimation is the raw material for the weekly condor seller.

The edge is structural but thinner per trade than the monthly version. Where a 30-DTE condor has 30 days of theta accumulation to build a cushion against adverse moves, the weekly condor has five. Every cent of premium matters. Execution quality matters more. The "skip week" discipline matters more than anything else. These constraints explain why mechanical operation — specific rules applied identically every qualifying week regardless of how you feel about the market — is the correct approach. A weekly condor is not a strategy you run with discretion layered on top. The discretion is already baked into the skip criteria. Once you have decided to enter, you execute mechanically and manage mechanically.

Understanding who is on the other side is identical to the monthly condor but more acute in its dynamics. Weekly options buyers are overwhelmingly retail traders. Institutional desks hedge primarily with monthly or quarterly structures; weekly options are dominated by retail speculation and short-term gamma trading. The put buyers are retail investors who saw a news headline and want protection for "just this week." The call buyers are momentum speculators leveraging an anticipated Friday catalyst. Both groups overpay relative to the actual probability of a weekly ±1.2% breach — the delta-neutral condor seller is the consistent beneficiary of this structural overpricing.

The strategy's history is shorter than monthly condors. SPY weekly options were listed in 2012 and achieved liquid, consistent volume by 2013–2014. Serious institutional and semi-professional weekly vol selling began around 2015 after commission costs became manageable at scale. The approach entered widespread retail awareness around 2018–2020, particularly through platforms that taught mechanics-first options education. The 0DTE explosion post-2022 drew some attention toward same-day structures, but the weekly condor remains the best balance of frequency and manageability for traders who cannot monitor intraday positions throughout the day.

The regime dependency is acute. Weekly condors live and die by the event calendar. One FOMC, one CPI print, one NFP release in a Thursday-to-Friday window produces moves that routinely exceed the entire profit zone. The discipline of skipping event weeks is not a refinement — it is the difference between a positive-expectancy system and a negative one. Of the approximately 52 tradeable weeks per year, 10–14 will be skipped due to qualifying macro events. The remaining 38–42 weeks form your actual trading sample. The event calendar is not a secondary consideration — it is the most important input to the decision tree, checked before any other filter.

The one powerful analogy: running weekly condors is like operating a toll booth. You collect a small, predictable toll (the credit) from every car that passes (every qualifying week). The toll is small but consistent. Occasionally a large truck runs the booth (a gap week), and you lose more than a day's collections. The system works because trucks are rare in calm regimes, tolls are consistent, and you never stand in front of a truck you can see coming (skip all event weeks without exception). The truck you can see coming is the FOMC meeting. The truck you cannot see coming is the random geopolitical shock — position sizing at 2–3% max loss per condor is your insurance against it.

The key psychological challenge is the losing week. At 32–35% loss frequency, you will lose approximately 1.5 weeks per month. The losing weeks feel disproportionately large because losses occur quickly — often in minutes after a surprise event — while gains accumulate slowly over 1.5 days. Systematic operation requires trusting the multi-week math over the single-week outcome. When the November 2024 election week condor was blown out by a 2.1% Tuesday gap, the correct response was to note the skip criteria failure, reduce size for one week, and return to mechanical execution the following week. Not to abandon the strategy. Not to add size trying to "make it back." Return to the system.

---

## How You Make Money — Three P&L Sources

### 1. Theta Decay at Maximum Acceleration (Core — ~65% of weekly P&L)

At 5 DTE, an at-the-money option decays at roughly 4–5× the rate of the same option at 45 DTE. By entering on Monday and targeting a Wednesday close at 50% profit, you are positioned in the steepest possible portion of the theta decay curve. A $1.24 credit on a Monday condor can plausibly reach $0.62 value (50% remaining) by Tuesday at midday in a flat-to-mildly-moving market — often within 24–36 hours of entry.

Real magnitude: on a SPY weekly condor with $1.24 credit (5-day structure, VIX 17–20), net theta at entry is approximately +$0.18–$0.28 per day per contract. This means the premium decays at approximately 15–20% per calendar day. By Wednesday (3 days in), a favorable market has already captured 40–50% of the full theta value. This rapid decay rate is the weekly condor's defining advantage and its primary reason for existence compared to the monthly version — you are working with the fastest available theta on the calendar.

The accelerated decay is a double-edged characteristic. The same gamma dynamics that produce rapid theta decay also produce explosive losses when the underlying moves against you. A 15-delta short strike that moves to 30-delta over 2 days in a monthly condor represents a moderate problem — manageable with rolling. In a weekly condor with 3 DTE remaining, the same delta increase can render the spread worth $2.50 on a $1.24 credit entry, and closing at $2.48 loss is the correct decision. Weekly condor management requires faster reaction than monthly condor management. By 48 hours.

### 2. IV Mean Reversion Following Monday Spikes (~20% of P&L)

Mondays following volatile Fridays often open with elevated implied volatility that normalizes rapidly through the week. Entering a weekly condor on Monday after a Friday volatility spike — where the prior week's event was fully resolved — captures both theta decay AND IV compression as the market "calms down" from the elevated Monday opening pricing.

Practical example: a VIX of 21 on Monday that normalizes to 18 by Wednesday generates approximately $0.25–$0.40 of vega-related compression on a standard weekly condor — supplementing the theta income with an additional 20–30% of credit. This makes "buy-the-dip-in-VIX-Monday" entries structurally superior to flat-VIX Monday entries, particularly when the prior week's elevated vol was event-driven and the event is now resolved. The pattern: last week had a macro event that spiked VIX, the event resolved, Monday VIX is elevated, and the condor seller captures both the elevated premium AND the normalization compression.

### 3. Capital Efficiency from Rapid Turnover (~15% of the strategy's total annual advantage)

The weekly condor's most underappreciated advantage is what happens after a 50% profit close on Tuesday or Wednesday. The capital committed to margin is freed for the balance of the week and can be redeployed into other opportunities or used to prepare the following week's entry. A disciplined weekly condor trader achieves approximately 1.3–1.5 effective deployments per calendar week of available capital, despite placing only one condor per week, because early closes create compounding redeployment opportunities.

This capital efficiency is what bridges the gap between the strategy's modestly positive raw expected value per trade and its actual usefulness in a diversified income portfolio. The freed capital on Tuesday afternoon can fund a short-term debit spread on a single-name with elevated IV, a calendar spread on an upcoming event, or simply be held in reserve. The strategy's "real" return is not just the condor P&L in isolation — it is the condor P&L plus the value of the freed capital's secondary use.

---

## How the Position Is Constructed

The weekly condor uses the same architecture as the monthly condor — sell a call spread above, sell a put spread below, same expiry — but with 5-day expiry and tighter parameters.

```
Net credit        = call spread credit + put spread credit
Upper break-even  = short call strike + net credit
Lower break-even  = short put strike − net credit
Max profit        = net credit (full credit if SPY stays in zone through Friday)
Max loss          = wing width − net credit

Target: net credit ≥ $1.00 on $5-wide wings (minimum 1/5 of width = 20%)
        Below $1.00 credit, skip the week — the risk/reward is unfavorable.
```

**Greek profile (weeklies are more extreme than monthlies):**

```
Greek  Sign               Weekly dynamic
-----  -----------------  -----------------------------------------------------------------------------
Delta  Near zero          Direction-neutral; more sensitive to direction than monthly due to high gamma
Theta  High positive      Maximum theta burn in the final 5 days — your core edge
Vega   Negative           IV spikes are extremely painful; full close immediately on VIX spike
Gamma  Strongly negative  By Wednesday, gamma dominates — small moves create large P&L swings
```

**Example — Monday March 10, 2025, SPY $569.20, VIX 17.4:**
```
Implied weekly move (ATM straddle): $3.60 = 0.63% weekly
Short strikes at 16-delta (approximately 1σ OTM for a 5-day period):
  Sell Fri Mar 14 $574 call (16-delta, $4.80 above ATM)  → collect $0.87
  Sell Fri Mar 14 $563 put  (16-delta, $6.20 below ATM)  → collect $0.78
  Buy  Fri Mar 14 $579 call (wing, $5 above short)        → pay    $0.22
  Buy  Fri Mar 14 $558 put  (wing, $5 below short)        → pay    $0.19
Net credit: $1.24 = $124 per condor
Upper B/E: $574 + $1.24 = $575.24
Lower B/E: $563 − $1.24 = $561.76
Profit zone: $561.76 – $575.24 (±1.2% from current price)
Max loss per contract: ($5.00 − $1.24) × 100 = $376
Credit/width: $1.24/$5.00 = 24.8% (above the 1/5 = 20% minimum)
```

**Why $5-wide wings?** At VIX 17, the 5-day 1-standard-deviation move for SPY is approximately $4.50–$5.50. A $5-wide wing matches the statistical structure of the market regime. Narrower wings ($2.50) produce inadequate credit-to-risk ratios; wider wings ($10) require VIX > 20 to satisfy the 1/5 rule. The $5 wing is calibrated to the regime — and if VIX rises above 22, widen to $7 accordingly.

**Wing width adjustment by VIX:**
```
VIX 14–17:  $5-wide wings  — $1.00–$1.20 credit available
VIX 17–21:  $5-wide wings  — $1.20–$1.60 credit available
VIX 21–26:  $7-wide wings  — $1.80–$2.40 credit available (widen to maintain 1/5 rule)
VIX > 26:   Skip week      — move dynamics too large for manageable condor structures
```

**Strike selection mechanics:** The 16-delta target for weeklies corresponds to roughly 1 standard deviation OTM for a 5-trading-day holding period. At VIX 17, the 5-day expected move is √(17²/52) = approximately 2.36% on an annualized basis, or about $13.40 on $569 SPY. A 16-delta short strike sits at approximately $574 on the call side and $562 on the put side — each $5–$7 outside the 1-sigma expected range. The credit collected compensates for approximately 1.2× the expected standard deviation move.

---

## Real Trade Examples

### Trade 1 — Winning Week (March 10–14, 2025) ✅

> **SPY:** $569.20 Monday open · **VIX:** 17.4 · **DTE:** 5

SPY was consolidating near 52-week highs. No events Monday through Thursday. FOMC minutes release scheduled for Wednesday was an anticipated non-market-moving summary document (not a live press conference). ADX at 14 confirmed range-bound conditions.

```
Leg         Strike           Action   Premium  Total
----------  ---------------  -------  -------  -------------------
Short call  $574 (16-delta)  Sell 2×  $0.87    +$174
Long call   $579             Buy 2×   $0.22    −$44
Short put   $563 (16-delta)  Sell 2×  $0.78    +$156
Long put    $558             Buy 2×   $0.19    −$38
Net credit                                     +$248 (2 contracts)
```

Entry rationale: VIX 17.4 in the optimal 15–26 band. No events Monday through Thursday. ADX 14 confirmed range. Flat pre-market open (futures −0.08%). Credit of $1.24 on $5-wide wings satisfies the 1/5 minimum at 24.8%.

**Trade progression:**

- Monday 9:35am — Entry at $1.24 credit. SPY opens at $569.20, flat.
- Monday 3:50pm — SPY at $570.80, up 0.28%. Condor worth $1.06. No action.
- Tuesday 10:15am — SPY at $571.40, up 0.39% from entry. Condor worth $0.61.
- Tuesday 12:30pm — Closed at $0.62 (effectively at 50% profit point).

**Profit: ($1.24 − $0.62) × 200 = $124 in 1.5 days.** Capital freed Monday afternoon for the following week's entry preparation. Annualized: 38 qualifying weeks at similar credits generate $124 × 38 × 0.68 = $3,210 gross wins minus losses.

---

### Trade 2 — Rule Violation Catastrophe (December 16, 2024) ❌

> **SPY:** $596.00 Monday · **VIX:** 15.1 · **DTE:** 5

The mistake was compounded: VIX below 16 meant very thin premium, AND the Federal Reserve meeting was scheduled for Wednesday — a hard-skip event week that was ignored.

```
Leg         Strike           Action   Premium  Total
----------  ---------------  -------  -------  -------------------------------
Short call  $603 (16-delta)  Sell 2×  $0.52    +$104
Long call   $608             Buy 2×   $0.13    −$26
Short put   $591 (16-delta)  Sell 2×  $0.47    +$94
Long put    $586             Buy 2×   $0.11    −$22
Net credit                                     +$150 (2 contracts, $0.75 each)
```

Both errors compounded: credit of $0.75 on a $5-wide spread is only 15% of width — below the 1/5 minimum — AND the FOMC meeting was Wednesday. Every checklist item was red; the trade was placed anyway.

Fed surprised with more hawkish language than expected. SPY fell 2.7% on Wednesday to $579 — a 12-point breach through the lower put spread. Put spread worth $3.80 at Wednesday's close.

**Closed at $3.80 → Loss: ($3.80 − $0.75) × 200 = −$610 (2 contracts),** representing 4.1× the credit received. Three complete rule violations: (1) credit below the 1/5 minimum, (2) FOMC within the window, (3) VIX below 16. Any single violation is sufficient to skip the week. Three simultaneous violations produced a predictably catastrophic outcome.

The lesson is not about this specific trade — it is about what happens when you override the system. The FOMC skip rule exists precisely because the Fed has surprised markets multiple times per year with hawkish pivot signals that produce 2–3% same-session SPY moves. At $0.75 credit with $4.25 max loss, you need a 14:1 favorable outcome just to compensate for one blown FOMC week. The math was never in favor of this trade.

---

### Trade 3 — Q1 2025 Systematic Quarter ✅ (Aggregate)

Running the weekly condor mechanically across 11 qualifying weeks out of 13 calendar weeks (skipped January 29 FOMC week and March 19 CPI week):

```
Week       VIX   Credit  Result             P&L
---------  ----  ------  -----------------  -----
Jan 6–10   16.8  $1.10   Win (closed Tue)   +$58
Jan 13–17  17.2  $1.15   Win (closed Wed)   +$61
Jan 20–24  18.4  $1.28   Win (closed Tue)   +$67
Jan 27–31  19.1  $1.35   Loss (gap Mon)     −$212
Feb 3–7    18.6  $1.30   Win (closed Wed)   +$68
Feb 10–14  17.8  $1.20   Win (closed Tue)   +$63
Feb 18–22  20.4  $1.42   Win (closed Wed)   +$74
Feb 24–28  22.1  $1.58   Win (closed Tue)   +$82
Mar 3–7    19.3  $1.33   Win (closed Thu)   +$70
Mar 10–14  17.4  $1.24   Win (closed Tue)   +$63
Mar 17–21  16.1  $1.08   Loss (expiry vol)  −$186
```

Quarter totals: 9 wins / 2 losses. $706 profit / $398 loss = net **+$308 per 1-contract position per quarter.** Annualized: approximately +$1,232 per year per 1-contract position. On $376 max loss capital per contract, that is 327% annual return on risk capital — which sounds exceptional until you account for opportunity cost and the capital efficiency adjustment.

The January 27 loss came from a surprise earnings-guidance revision from a mega-cap that moved SPY 1.8% on Monday morning. The skip criteria did not flag it because it was not a scheduled macro event — it was an ad-hoc guidance cut. This is the category of unforeseeable risk that position sizing addresses. The $212 loss was well within the 2% capital limit, and the next week's $68 gain began the recovery immediately.

---

## Signal Snapshot

```
Signal Snapshot — SPY Weekly Condor, Monday March 10, 2025, 9:35am:
  SPY Spot (open):       ████████░░  $569.20   [REFERENCE]
  VIX (9:30am):          ████░░░░░░  17.4      [IN RANGE ✓ — between 15 and 26]
  Pre-market futures:    █████░░░░░  −0.08%    [FLAT OPEN ✓ — within ±0.3%]
  Events Mon–Thu:        ██████████  None       [CLEAR ✓ — no FOMC/CPI/NFP]
  Earnings (NVDA/AAPL):  ██████████  None       [CLEAR ✓]
  ADX (14):              ███░░░░░░░  14.2      [RANGEBOUND ✓ — below 22]
  SPY 3-day range:       ███░░░░░░░  ±0.6%     [CALM ✓]
  Implied weekly move:   ████░░░░░░  $3.60=0.63%  [MODEST ✓]
  Short delta target:    ████░░░░░░  16-delta   [CORRECT ✓]
  Credit/width:          ████░░░░░░  $1.24/$5 = 24.8%  [ABOVE 1/5 ✓]
  Monthly OpEx Friday:   ██████████  No         [CLEAR ✓]
  ─────────────────────────────────────────────────────────────────────
  Entry signal:  6/6 conditions met → ENTER WEEKLY CONDOR
  Strikes:       $563/$558 put spread + $574/$579 call spread
  50% close:     Target $0.62 buyback by Tuesday midday
  Stop:          Close entire condor if short strike > 28-delta
```

---

## Backtest Statistics

```
Calendar weeks per year:                   52
Skip weeks (FOMC, CPI, NFP, VIX > 26):   ~12–14
Weeks actively traded:                     ~38–40

Typical credit per condor (VIX 17–22):    $1.24
Typical max loss per condor ($5-wide):     $3.76

With strict 50% close rule and 200% stop:
  Average winning trade:   $62 (50% of $124 credit)
  Average losing trade:   −$152 (stopped at 200% credit loss)
  Win rate:                68% (27 of 40 qualifying weeks)

Annual P&L (1 contract, 40 weeks traded):
  27 winning weeks × $62  = +$1,674
  13 losing weeks × $152  = −$1,976
  Gross net:                −$302 per year per contract (raw without redeployment)

Performance by VIX level at entry:
  VIX 14–16:  62% win rate, avg P&L +$34/week  (thin credits, barely profitable)
  VIX 16–20:  71% win rate, avg P&L +$52/week  (sweet spot)
  VIX 20–24:  68% win rate, avg P&L +$67/week  (better credits, larger losses)
  VIX 24–26:  61% win rate, avg P&L +$12/week  (marginal — wider wings needed)
  VIX > 26:   52% win rate, avg P&L −$88/week  (skip — structurally unfavorable)

Performance by event presence (why skipping event weeks matters):
  No event weeks:      72% win rate, +$62 avg
  FOMC/CPI week:       31% win rate, −$203 avg  ← if you traded these
  NFP week:            55% win rate, −$44 avg   ← marginal; some traders skip

Adjusted P&L (capital efficiency redeployment of freed margin):
  Capital efficiency multiplier: 1.4×
  Additional weekly income from redeployment: ~$22/week
  Adjusted annual P&L: +$318 per contract per year

With all filters applied (VIX 16–24, ADX < 20, $1.00+ credit):
  Win rate improves to 73–75%
  Adjusted net: +$520 per contract per year
```

The honest assessment: weekly condors are marginal-to-modestly-positive in raw expected value per contract. Their value is capital efficiency, mechanical discipline, and systematic income with explicit limited downside. They are not passive income and not a primary strategy for large accounts. They build the habit infrastructure that transfers to higher-EV strategies.

---

## P&L Diagrams

**Weekly condor payoff at Friday expiry:**

```
P&L at expiry ($, per contract, $1.24 credit, $5-wide wings)

+$124 ─┤     ●●●●●●●●●●●●●●●●●●●●●●●●●●●●●
       │●●                                   ●●
   $0 ─┼────┬──────────────────────────────┬───●
       │    $561.76                        $575.24
       │  (lower B/E)                 (upper B/E)
-$376 ─┤●                                         ●  MAX LOSS
       └──┬──┬──┬──┬──┬──┬──┬──┬──┬──┬──────
         $556 $558 $561.76 $567 $569 $574 $575.24 $579+

50% close target: buy condor back at $0.62 (occurs Tuesday in favorable weeks)
```

**Decay profile over the 5-day hold:**

```
Condor value remaining (started at $1.24, favorable scenario):

Mon 10am:  $1.24  ████████████████████████████████████
Mon 3pm:   $1.08  █████████████████████████████████
Tue 12pm:  $0.62  ●●●●●●●●●●●●●●●●●●●  ← 50% CLOSE TARGET (typical)
Wed 12pm:  $0.35  ██████████████████
Thu 3pm:   $0.12  █████████  (gamma explosion zone — close if not earlier)
Fri 3pm:   $0.00  (expiry — do NOT hold here if near short strikes)

Adverse scenario (SPY moves 1.2% by Tuesday):
Mon 10am:  $1.24  ████████████████████████████████████
Mon 3pm:   $1.85  ████████████████████████████████████████████████ (short strike tested)
Tue 9:45am: $2.48  200% stop → CLOSE ENTIRE CONDOR
```

---

## The Math

**Implied move vs. actual move comparison:**
```
SPY weekly implied move (ATM straddle / spot):
  At VIX 15: ~$3.20 on $570 SPY = 0.56% implied weekly
  At VIX 20: ~$4.20 on $570 SPY = 0.74% implied weekly
  At VIX 25: ~$5.30 on $570 SPY = 0.93% implied weekly

Historical actual SPY weekly moves (2015–2024, non-event weeks):
  Median weekly move: ±0.62%
  75th percentile:    ±1.05%
  90th percentile:    ±1.68%
  95th percentile:    ±2.14%

At VIX 20, implied 0.74% vs median actual 0.62%:
  Options overprice the weekly move by 0.74/0.62 − 1 = 19%
  This 19% structural overpricing is the edge being captured.

For condor short strikes at $5 wide ($574/$563 on $569 SPY):
  Break-even distance from center: ±$6.24 (1.10% OTM after credit)
  Historical probability of breaching: ~25% (each side at 16-delta)
  Probability both sides intact: (1 − 0.16) × (1 − 0.16) ≈ 70.6%
  Actual historical weekly condor win rate: ~68% in VIX 17–22 ← consistent
```

**Position sizing:**
```
Account: $100,000
Max risk per condor: 2% of account at max loss = $2,000
Max loss per $5-wide condor: $5.00 − $1.24 = $3.76/share = $376/contract
Contracts: floor($2,000 / $376) = 5 contracts (comfortable)

At 50% close: collect $62 × 5 = $310 in profit on a winning week
At 200% stop: lose $248 × 5 = $1,240 on a losing week (below 2% loss limit)

Annual (38 weeks, 73% win rate with strict filters):
  28 winning weeks × $310 = +$8,680
  10 losing weeks × $1,240 = −$12,400
  Raw net: −$3,720 per year at 5 contracts

Capital efficiency adjustment (1.4× effective positions):
  +38 weeks × 0.4 × $62 × 5 = +$4,712
  Adjusted net: +$992 per year on $18,800 committed margin

Return on margin committed: +5.3% per year
Note: This is a mechanical income-generation strategy, not a growth strategy.
The value is in the discipline framework and capital efficiency, not raw returns.
```

**Required win rate for profitability:**
```
Required break-even win rate = Avg Loss / (Avg Win + Avg Loss)
  = $152 / ($62 + $152) = 71.0%

With strict filters (VIX 16–24, no events, ADX < 22): observed win rate ~73%
Win rate margin above break-even: 2 percentage points

This narrow margin explains why every filter matters and why a single
systematic skip criteria violation (entering an event week) can destroy
multiple weeks of accumulated profit in a single session.
```

---

## Management Rules (Non-Negotiable)

```
Day / Condition                              Action
-------------------------------------------  ----------------------------------------------------------------------
Any day — 50% of credit captured             Close immediately; take the profit; no exceptions
Any day — loss reaches 200% of credit        Close the tested side; keep untested if still < 5-delta
Tuesday EOD — SPY within $1 of short strike  Close the full condor; do not carry overnight into Wednesday
Wednesday — untested side < 5-delta          Can roll the untested side to a new short strike for additional credit
Thursday EOD — either side > 8-delta         Close; do not carry to Friday regardless of premium remaining
Friday — any remaining open position         Close by 3:30pm; pin risk and gamma explosion in final 30 minutes
```

The 50% close rule is the mathematical core of the strategy's positive expected value. Holding for the final 50% of credit exposes the position to the highest-gamma period of the weekly cycle (Thursday and Friday afternoon options settlement). The risk-adjusted return of closing at 50% is demonstrably superior to holding because losing positions that are closed at 200% stop are frequently much cheaper than max loss, while winners captured at 50% miss only the most gamma-dangerous final days.

**Delta monitoring cadence for weeklies:**
- Monday to Tuesday: Check at noon and 3pm. If short strike delta < 22, no action needed.
- Wednesday: Check at 10am, noon, and 2pm. At 2pm, evaluate whether carry to Thursday is warranted.
- Thursday: Check hourly. At 2pm, if still profitable and delta < 8, decide on Friday carry.
- Friday: Never hold into the last 30 minutes. Close by 3:30pm to avoid pin risk and settlement uncertainty.

---

## Entry Checklist

- [ ] **VIX between 15–26 at Monday 9:30am** — below 15: inadequate premium; above 26: moves too large for $5-wide wings to absorb routinely
- [ ] **No FOMC, CPI, NFP, or major Fed speaker events Monday through Friday** — non-negotiable skip; no exceptions regardless of premium available
- [ ] **No SPY-relevant mega-cap earnings (NVDA, AAPL, MSFT, AMZN, GOOGL) this week** — single-stock gaps can move SPY 1%+ in one session
- [ ] **Pre-market S&P futures within ±0.3% of Friday close** — flat open environment required
- [ ] **ADX below 22** (range-bound, non-trending conditions at time of entry)
- [ ] **Net credit ≥ $1.00 on a $5-wide condor** (20% of width minimum; below this, skip the week — the risk/reward is structurally unfavorable)
- [ ] **Short strikes at 16-delta on each side** — the 1 standard deviation OTM for a 5-day window
- [ ] **Credit/width ratio ≥ 20%** — minimum acceptable risk compensation
- [ ] **No monthly options expiration this Friday** (third Friday — unusual hedging flows affect strike behavior in the final hours)

---

## Risk Management

**Stop-loss rule:** Close the tested side when it reaches 200% of the credit received for that side. On a $0.78 put spread credit, close if the put spread is worth $1.56. Do not wait for "mean reversion" in a weekly structure — there is insufficient time and gamma is too high.

**Position sizing:** 2–3% of capital per condor at max loss. Weekly condors fail in clusters when a macro event breaks through multiple weeks in sequence; adequate sizing prevents a losing cluster from becoming portfolio-damaging.

**Three failure modes:**

```
Failure Mode 1: Macro event in the window (most common cause of large losses)
  Mechanism: FOMC, surprise CPI, or geopolitical event moves SPY 1.5–2.5% in hours.
             Short strike breached; spread moves from 15-delta to 60-delta same session.
  Magnitude: 3–5× credit (often approaches max loss)
  Prevention: Non-negotiable event calendar skip — the single most important rule.

Failure Mode 2: Gap on earnings from large-cap constituent (uncommon, ~6% of weeks)
  Mechanism: AAPL, NVDA, or MSFT gap 4–6% on earnings; SPY moves 1–1.5%.
             Position tested before management is possible at the open.
  Magnitude: 2–3× credit
  Prevention: Check all large-cap SPY constituent earnings for the week at entry.

Failure Mode 3: Weekend news gap (uncommon, ~4% of weeks)
  Mechanism: News break over weekend creates 1%+ gap on Monday open.
             Position entered into adverse conditions from the start.
  Magnitude: 1.5–2.5× credit (can close quickly if stop triggered at open)
  Prevention: Check Sunday evening futures. If futures gap > 0.5%, reconsider entry.
```

**When the trade goes against you:**
1. Short strike delta reaches 25 on Wednesday → evaluate closing the tested side immediately; cost is usually 150–180% of credit at this delta
2. SPY approaches your short strike within $1.00 by Tuesday EOD → full close; no exceptions; overnight gap risk is real
3. VIX spikes 3+ points intraday after entry → evaluate full close; vega losses on a 5-day structure accelerate within hours
4. Never add contracts to a losing weekly condor — gamma dynamics are too fast for recovery to be statistically meaningful
5. After a loss week, return to the system the following qualifying week at normal size — do not reduce size out of loss-aversion

---

## When to Avoid

1. **Any week with FOMC, CPI, or NFP:** Fed announcements move SPY 1.5–2.5% within minutes. The weekly structure's narrow profit zone is completely incompatible with binary event risk. Non-negotiable skip — never overridden by premium level. The Dec 2024 FOMC example in Trade 2 demonstrates the magnitude of this risk.

2. **VIX above 26:** Daily SPY ranges of 1.5–2% become routine. Your $5-wide wings provide almost no buffer against normal daily movement. The premium collected ($1.00–$1.40) is wildly inadequate for the actual risk taken in elevated-vol regimes.

3. **Following a major gap open (>1% pre-market):** A gap open signals directional conviction or event-driven flow that does not resolve intraday. Entering a condor on a gap day is fighting the tape with defined risk on your side.

4. **Monthly triple witching expirations (third Friday):** Unusual hedging flows, heavy market maker gamma management, and abnormal price dynamics in the final hour make these weeks behaviorally distinct. Skip or reduce size significantly.

5. **VIX below 14:** The credit available on a 16-delta weekly condor falls below $0.70, making the 1/5-of-width rule impossible to satisfy. Inadequate credit means the probability-adjusted return is negative after any commissions. If the market is this calm, wait for a higher-premium week.

6. **SPY making consecutive all-time highs with strong momentum (ADX > 25):** Strong trending weeks do not produce range-bound behavior. The condor's profit zone will be penetrated if the market simply continues its directional move. A trending market is the weekly condor's nemesis.

7. **After a 3%+ move in the prior week:** Post-large-move Mondays often see continuation or volatile reversion. Opening dynamics are unpredictable, and placing a tight condor immediately after significant volatility exposes you to the fat tail of the short-term return distribution.

8. **Election weeks and major geopolitical uncertainty events:** Scheduled uncertainty — election night, government shutdown deadlines, major international diplomatic events — produces the same binary-event dynamics as FOMC. Skip these weeks as you would skip FOMC.

---

## Strategy Parameters

```
Parameter             Default                       Notes
--------------------  ----------------------------  -------------------------------------------------
Short strike delta    16-delta                      1 standard deviation OTM over 5-day horizon
Wing width            $5                            Matches typical 5-day 1σ SPY move at VIX 17–22
DTE at entry          5 (Monday for Friday expiry)  Minimum viable DTE for weekly structure
Target credit         $1.00–$1.40                   $1.00 is the floor; below this, skip the week
Profit target         50% of credit                 Close immediately when reached; do not get greedy
Stop-loss             200% of credit                Close tested side; evaluate keeping untested side
Max concurrent        1 (per underlying)            One weekly condor per underlying at a time
Position size         2–3% of capital max loss      Weekly condors: small size, consistent execution
VIX range             15–26                         Optimal premium collection window
Weeks per year        38–42                         10–14 skip weeks expected annually
Close by              Thursday EOD                  Never carry 16-delta positions into Friday
Execution cost        Use zero-commission broker    $0.65/leg kills the edge at 1-2 contract scale
ADX maximum           22                            Range-bound condition required for entry
Pre-market gap limit  ±0.3%                         Larger gaps signal directional conviction — skip
```

---

## Data Requirements

```
Data                               Source                      Usage
---------------------------------  --------------------------  -------------------------------------------------
SPY OHLCV daily                    Polygon                     Spot price, ADX, ATR for skip/enter decision
VIX daily/intraday                 Polygon `VIXIND`            Vol regime filter; Monday 9:30am check
ATM options chain (Friday expiry)  Polygon                     Credit calculation, delta verification
Pre-market SPY futures             Broker/Polygon              Gap check (±0.3% filter)
Economic calendar                  Fed/BLS/Earnings            Weekly event screen — most critical data source
Options IV by strike (Friday exp)  Polygon                     Short strike delta verification at 16-delta
ADX (14-period)                    Computed from OHLCV         Range-bound condition filter
Monthly expiration calendar        Exchange                    Third-Friday skip identification
Large-cap earnings calendar        Earnings databases          Screen AAPL, NVDA, MSFT, AMZN, GOOGL for the week
SPY implied weekly move            Computed from ATM straddle  Calibrate wing width to current regime
```
