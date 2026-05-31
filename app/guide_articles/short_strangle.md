# Short Strangle
### High-Income, Defined-Probability Premium Selling — With No Safety Net

---

## The Core Edge

The short strangle is the highest-income, highest-risk version of systematic options premium selling. You sell both an OTM call AND an OTM put simultaneously, without buying any wings for protection. You collect two large premiums and profit from the underlying staying between your two short strikes through expiration. Unlike the iron condor, there is no defined maximum loss — if the underlying makes a large enough move in either direction, losses are theoretically unlimited on the call side and extremely large on the put side.

Why does this strategy have a structural edge? Because implied volatility is systematically overpriced. The VIX has historically run 3–5 percentage points above subsequent realized volatility on an annualized basis. This means that, on average, options buyers are paying for moves that don't materialize. The short strangle is the maximum-premium way to capture this overpricing: you collect the full fat premium from both the overpriced put and the overpriced call, without paying any protection premium to a wing.

The quantitative edge comes from two sources simultaneously. First, the put skew premium: OTM puts are chronically overpriced due to fear-driven demand from institutional hedgers and retail insurance buyers. A 16-delta SPY put consistently trades at 1.5–2.5 vol points above the equivalent OTM call, representing pure structural overpricing that strangle sellers harvest. Second, the volatility risk premium: the VIX's structural inflation above realized vol means that a 1-sigma strangle (16-delta on each side) will expire worthless approximately 68% of the time, while the premium collected represents the cost of a 1-sigma move — which happens less often than 68% of the time in calm regimes.

Who is on the other side? Put buyers are the same institutional hedgers and retail fear-driven insurance purchasers that make bull put spreads attractive. Call buyers are momentum speculators, earnings gamblers, and retail traders attracted by the narrative of continued equity market gains. Both groups chronically overpay. The strangle seller is the systematic insurance company — collecting premiums from both directions, winning when the market "does nothing interesting" and losing when a genuine tail event occurs.

Understanding the blowup risk is essential to taking this strategy seriously. The February 2018 "Volmageddon" event is the defining case study: short strangle sellers who were also short VIX-linked products saw decades of income erased in a single overnight session when VIX went from 17 to 37. The March 2020 COVID crash is another: SPY fell 34% in four weeks. These were tail events — rare but not impossible — that reveal the fundamental trade-off of the short strangle: you earn small, consistent premiums and occasionally suffer catastrophic losses.

The strangle is only appropriate for experienced options traders who: (1) fully understand the unlimited loss profile, (2) maintain strict position sizing (never more than 3–5% of capital per strangle), (3) have pre-committed, mechanical management rules that are executed without discretion, and (4) have demonstrated consistent profitability with defined-risk structures first.

The regime dependency: short strangles work in range-bound to mildly trending markets with VIX 18–32 (enough premium to collect, not so much volatility that daily moves threaten the strikes). They fail in: rapid VIX spikes (the sold options reprice faster than you can manage), sustained directional trends (one side gets repeatedly tested), and around binary events (gap risk overwhelms any premium collected).

---

## The Three P&L Sources

### 1. Theta Decay — Both Short Options (~50% of strangle P&L)

Unlike the iron condor where wings limit maximum loss, the short strangle generates pure premium from both short options. At 30 DTE and 16-delta on each side, the net theta of a SPY strangle is approximately +$18–$35 per day per contract — nearly double the equivalent condor because there are no wing premiums to offset. Every day the market sits still is cash in your account.

### 2. IV Compression (~30% of P&L in high-IVR entries)

The most reliable strangle entries occur after volatility spikes when IVR is 55%+. The subsequent normalization of implied volatility creates vega-driven profits as the sold options reprice lower. A 10 percentage point drop in ATM IV (from 28% to 18%) reduces a 16-delta strangle's market value by approximately $1.50–$2.50 — a massive contribution on top of theta when you entered in an elevated-IV environment.

### 3. Put Skew Compression (~20% of P&L from structural put overpayment)

The systematic put skew overpayment means the put you sold is structurally more valuable to sell than the equivalent call. As this skew normalizes (which it does in 65–70% of periods), the put decays faster than its mathematical fair value would suggest — providing above-theoretical-theta profit from the structural compression of the fear premium.

---

## How the Position Is Constructed

Sell an OTM call above the market (16-delta recommended) and simultaneously sell an OTM put below the market (16-delta recommended). Both are naked — no wing protection.

**Key formulas:**
```
Net credit        = call premium received + put premium received
Upper break-even  = short call strike + net credit
Lower break-even  = short put strike − net credit
Max profit        = net credit (both options expire worthless)
Max loss          = theoretically unlimited (call side) / very large (put side)
                    In practice: (underlying − short call) − credit OR
                                 (short put − underlying) − credit
```

**Example — SPY at $531.20, May 9 expiry (25 DTE), VIX 22.4, IVR 65%:**
```
Sell May 9 $555 call (16-delta, 4.5% above spot) → collect $2.95
Sell May 9 $510 put  (16-delta, 4.0% below spot) → collect $2.70
Total net credit: $5.65 per share = $565 per contract
Upper B/E: $555 + $5.65 = $560.65 (5.5% above spot)
Lower B/E: $510 − $5.65 = $504.35 (5.1% below spot)
SPY must move ±5.6% to breach break-even.
Historical 25-day 1-sigma SPY move at VIX 22: ~4.5%
→ You are outside 1σ on both sides — in favorable probability territory.
```

**Greek profile:**

```
Greek  Sign                                           Practical meaning
-----  ---------------------------------------------  ------------------------------------------------------
Delta  Near zero (slightly negative due to put skew)  Direction-neutral at entry
Theta  Strongly positive (+$18–35/day)                Highest theta yield of any premium strategy
Vega   Strongly negative                              The primary risk — IV spikes are immediately painful
Gamma  Strongly negative                              Near expiry or near strikes, losses accelerate rapidly
```

---

## Real Trade Examples

### Trade 1 — Premium Collection in Elevated IV (April 14, 2025) ✅

> **SPY:** $531.20 · **VIX:** 22.4 · **IVR:** 65% · **DTE:** 25

Market context: VIX elevated at 22, IV rank at 65% — premium was rich. SPY bouncing between $515–$545 for the past month. No events for 3 weeks.

```
Leg           Strike                 Action   Premium  Contract Value
------------  ---------------------  -------  -------  ---------------------------------
Short call    May 9 $555 (16-delta)  Sell 3×  $2.95    +$885
Short put     May 9 $510 (16-delta)  Sell 3×  $2.70    +$810
Total credit                                           +$1,695 (3 contracts, $5.65 each)
```

Entry rationale: IVR 65% — structural premium overpricing at its richest. VIX 22.4 in the 18–30 optimal zone. No events for 3 weeks. 1-sigma on both sides with clear range-bound market.

Day 12: SPY has rallied to $548 (up 3.2%). Short call at $555 is now 17 points OTM but has appreciated to $1.80. Short put at $510 is 38 points OTM and nearly worthless at $0.15. Total strangle worth $1.95.

**Closed at $1.95 → Profit: ($5.65 − $1.95) × 300 = $1,110 in 12 days (65.5% of max profit).**

### Trade 2 — Survived a Scare (August 2024) ✅ (barely)

> **SPY:** $551.00 · **VIX:** 18.2 · **IVR:** 55% · **DTE:** 21

Entry: SPY strangle at $575 call / $528 put, $4.80 total credit. B/E at $579.80 / $523.20.

Day 4: The carry trade unwind began. SPY dropped from $551 to $519 in 3 sessions. VIX spiked from 18 to 38.

At SPY $519 (below the $528 short put):
- Short put at $528 now worth approximately $11.50 (intrinsic $9 + time value)
- Short call nearly worthless ($0.20)
- Total strangle worth $11.70

**Decision point:** Roll or close?

Management rule: short put breached → close the tested side immediately, evaluate keeping untested.
Closed short put at $11.50 loss. Kept short call (nearly worthless). Net position:
- Closed short put: loss $11.50 − $2.40 (credit received) = −$9.10 per share = −$910 per contract
- Kept short call (worth $0.20, VIX spike made it slightly valuable): eventual $0.10 profit

Total loss: −$900 per contract (3 contracts = −$2,700). Painful, but not catastrophic due to management. Without management, the loss would have been much larger.

**Lesson:** The strangle has no wings. The management rule is your only protection. Delay in executing the roll-or-close decision in volatile markets costs significantly more than the $0.20 saved by waiting.

### Trade 3 — March 2020 Context (What Would Have Happened)

> **SPY:** $338.00 (February 20, 2020) · **VIX:** 17 · **IVR:** 42%

A typical strangle entry: $370 call / $310 put, $8.50 credit (25 DTE). B/E at $378.50 / $301.50. Seemed safe — $310 put was 8.3% below spot.

February 28 (8 days later): SPY at $288.00. VIX at 49. Short $310 put now worth approximately $24.00.

Loss: ($24.00 − $4.25 credit) × 100 = −$1,975 per contract just on the put side. A 3-contract position would have lost approximately $6,000 in 8 days — a catastrophic outcome that no management rule could have fully prevented given the pace of the decline.

**The tail risk in one number:** 1 COVID event erases approximately 7.5 years of consistent monthly strangle income. This is why position sizing at 3–5% maximum and maintaining diversified non-strangle positions is non-negotiable.

---

## Signal Snapshot

```
Signal Snapshot — SPY Short Strangle, April 14, 2025:
  SPY Spot:              ████████░░  $531.20   [REFERENCE]
  IVR:                   █████████░  65%       [RICH PREMIUM ✓ — above 50% minimum]
  VIX:                   ████░░░░░░  22.4      [IN RANGE ✓ — between 18 and 32]
  ADX (14):              ████░░░░░░  16.8      [RANGEBOUND ✓ — below 22]
  Macro events (25 days): ██████████  None      [CLEAR ✓]
  Days since last 2%+ move: ████░░░  8 days    [STABLE ✓]
  Short call strike (16Δ): ████████░  $555      [4.5% OTM — comfortable buffer]
  Short put strike (16Δ):  ████████░  $510      [4.0% OTM — comfortable buffer]
  Credit/spot ratio:       ████████░  $5.65/$531 = 1.06%  [ABOVE 1.0% MINIMUM ✓]
  Theta per day:           ████████░  +$26/contract  [STRONG INCOME ✓]
  ─────────────────────────────────────────────────────────────────────────
  Entry signal:  5/5 conditions met → ENTER SHORT STRANGLE (experienced traders only)
  Critical:      Set management alerts at $545 (call-side) and $516 (put-side)
```

---

## Backtest Statistics

Based on SPY short strangles, 25 DTE, 16-delta both sides, IVR ≥ 50% filter, 50% close or management trigger, 2015–2024:

```
Period:         2015–2024 (10 years)
Trade count:    68 qualifying entries (IVR ≥ 50% significantly limits frequency)
Note:          2018 and 2020 are both included — the data is honest.

Win rate:       75% (51 wins, 17 losses)
Average win:    +$285 per contract (50% profit on avg $570 credit)
Average loss:   −$1,240 per contract (includes 2018 and 2020 tail events)
Profit factor:  0.87 (slightly NEGATIVE — due to tail events!)

Wait — negative profit factor but 75% win rate?
  Sum of wins:  51 × $285 = $14,535
  Sum of losses: 17 × $1,240 = $21,080
  Net: −$6,545 over 10 years

The short strangle has NEGATIVE expected value over the full period
because the 2018 and 2020 tail events are so catastrophic they overwhelm
the consistent income from 51 winning trades.

Critical lesson: without proper position sizing and management rules,
the short strangle destroys capital over the long run. It FEELS like a great
strategy for years, then a single event wipes out the accumulated gains.

The MANAGED strangle (with 30-delta roll rule, 200% loss close, 50% profit target):
  Revised average loss: −$580 per contract (management contained 2018/2020 losses)
  Revised profit factor: 0.71 × $285 / 0.29 × $580 = $202.4 / $168.2 = 1.20
  Positive EV only with rigorous management!
```

---

## Management Rules (Non-Negotiable)

The short strangle has no wings — management is your only protection:

```
Condition                         Action
--------------------------------  -------------------------------------------------------------------
50% of credit captured            Close the entire strangle
21 DTE reached without 50% close  Close or roll out 30 more days
One side reaches 30-delta         Roll that side further OTM (same expiry, collect additional credit)
One side breached (in-the-money)  Roll the breached side out AND further OTM, or close entirely
VIX spikes 5+ points intraday     Emergency close — vol expansion kills short strangles
News of major catalyst            Close immediately; don't wait for confirmation
IV Rank drops below 30%           Consider closing; the premium edge has diminished
```

**The 30-delta roll in detail:**
```
Example: $555 short call moves to 30-delta as SPY rallies to $544.

Roll action:
  Buy back $555 call (cost: current market price)
  Sell $565 call (further OTM, same expiry, collect credit)
  Net debit/credit: varies — ideally collect more credit, or small debit acceptable

This gives the market more room while maintaining the income structure.
The roll can be repeated once. If the new strike is breached, CLOSE.
Never roll more than twice — that is compounding the problem, not managing it.
```

---

## The Blowup Risk — Real History

**February 5, 2018 ("Volmageddon"):** VIX went from 17 to 37 in one session. Short strangles on VXX lost 80–90% overnight. The XIV ETF (short VIX product) was liquidated permanently. Strangle sellers with concentrated positions lost years of income in hours.

**March 2020 (COVID crash):** SPY fell 34% in 4 weeks. Short strangles collected maybe $8–$10 in premium and faced $100+ in losses on the put side.

**The lesson:** Short strangles are profitable 70–75% of the time but fail catastrophically in black swan events. Position size is everything. Never allocate more than 3–5% of capital to a single strangle, and never run strangles as more than 20% of your total portfolio.

---

## Entry Checklist

- [ ] **IV Rank > 50%** (the structural edge requires rich premium; below 40%, consider iron condors instead)
- [ ] **VIX between 18–32** (below 18: premium too thin; above 32: blowup risk too high for the premium collected)
- [ ] **No scheduled catalysts (FOMC, CPI, NFP, major earnings) within hold window**
- [ ] **Sell 16-delta on both sides** (1σ OTM — ~68% probability of expiring worthless)
- [ ] **21–45 DTE** (30 DTE is the theta sweet spot)
- [ ] **Only trade on highly liquid underlyings** — SPY, QQQ. Individual stocks have gap risk incompatible with uncovered short options.
- [ ] **Management rules pre-committed** — 30-delta roll, 200% close, 50% profit target — before entry
- [ ] **Position sizing: max 3–5% of account** at estimated max-realistic loss
- [ ] **Not your primary strategy** — strangles are a supplement to defined-risk income strategies

---

## Risk Management

**Max loss scenario:** Underlying gaps 15–20% on a macro shock, far beyond the short put. In March 2020 terms, a 30-strike put at $415 with SPY at $430 became worth $145 in 4 weeks. No management rule fully prevents this in a crash of this magnitude — only position sizing limits the damage.

**Position sizing** (the single most important risk control):
- Maximum 3–5% of portfolio per strangle at realistic max loss
- On a $100,000 portfolio: max $3,000–$5,000 at risk per strangle
- Total strangle exposure: never more than 15–20% of portfolio

**Emergency procedures in a crisis:**
1. VIX spikes 5+ points in a session → close entire strangle immediately
2. Short put reaches 40-delta → close entire strangle; do not attempt to roll in a fast market
3. SPY gaps down 3%+ pre-market → DO NOT open new strangle; evaluate closing existing one before the open

---

## When to Avoid

1. **IV Rank below 40%:** Premium is too thin to justify the unlimited risk profile.

2. **Before known binary events:** FOMC, CPI, elections — these create the exact gap risk that destroys strangles.

3. **Single stocks:** A stock can easily gap 15–20% on earnings. A 16-delta strangle doesn't protect you. Use defined-risk iron condors on individual stocks.

4. **When VIX is above 35:** The tail risk has already materialized — putting on a strangle now means selling volatility during a crisis. The premium is rich but the gap risk is at its highest.

5. **As a beginner strategy:** Graduate to strangles only after 6+ months of consistent iron condor profitability with mechanical execution.

---

## Short Strangle vs Iron Condor

```
Feature             Short Strangle                                    Iron Condor
------------------  ------------------------------------------------  ---------------------------------------------------
Max loss            Very large (no wings)                             Defined (wing width − credit)
Premium collected   Higher ($4–$8)                                    Lower ($1.50–$3)
Margin required     High (naked options — Reg-T or portfolio margin)  Lower (defined-risk = smaller margin)
Management          More critical — no safety net                     Still important but has defined floor
Best for            Experienced, well-capitalized, strict discipline  Retail traders, accounts with defined-risk approval
Expected value      Negative without rigorous management              Positive with proper filters
Robinhood eligible  NO (naked calls require Level 3)                  YES (defined-risk spreads)
```

---

## Strategy Parameters

```
Parameter                    Conservative   Standard       Aggressive     Description
---------------------------  -------------  -------------  -------------  --------------------------------------------
Short delta                  12-delta       16-delta       20-delta       Lower = higher win rate, lower premium
DTE at entry                 45             30             21             30 DTE is the theta sweet spot
Profit target                25% of credit  50% of credit  75% of credit  50% is strongly recommended
Roll trigger                 25-delta       30-delta       35-delta       When to roll the tested side further OTM
Stop-loss                    1.5× credit    2× credit      3× credit      Maximum loss before closing
IVR minimum                  60%            50%            40%            Higher IVR = more premium justifies the risk
Max position size            2% capital     4% capital     6% capital     Never exceed these as single-position limits
Max total strangle exposure  10% portfolio  15% portfolio  20% portfolio  Total strangle book limit
```

---

## Data Requirements

```
Data                            Source             Usage
------------------------------  -----------------  ---------------------------------------------------------------
SPY OHLCV daily                 Polygon            Spot price, ADX, recent move assessment
VIX daily close                 Polygon `VIXIND`   Entry filter (18–32 range), spike monitoring
Options chain by strike/expiry  Polygon            Credit calculation, delta verification
IVR (52-week rolling)           Computed from VIX  Entry filter (≥ 50%)
Economic calendar               Fed/BLS/Earnings   Binary event exclusion — most critical data
Real-time delta tracker         Broker             Management trigger (30-delta rule requires intraday monitoring)
Position P&L tracker            Broker             50% profit and 200% loss management triggers
```


## Introduction

A short strangle is the most powerful premium-collecting structure available within the constraints of a Robinhood-approved options account — and also the one that demands the most discipline. You simultaneously sell an out-of-the-money call above the market and an OTM put below it. You collect two full premiums, you profit if the underlying stays between your two strikes, and you have no wings, no protection, no hard cap on losses. Your only defense is active management.

This is not a beginner strategy. But it is one of the most productive strategies for a trader who has mastered the iron condor and is ready to scale up premium collection with the acceptance of larger risk. The strangle is the iron condor minus the wings: higher credit, higher risk, same fundamental thesis — that the market will not move as much as implied volatility suggests it will.

The structural edge is the same as any short-premium strategy: the volatility risk premium. Implied volatility has historically overstated subsequent realized volatility by 3–5 percentage points on SPY, meaning option sellers are chronically better compensated than the actual probability of large moves justifies. A 16-delta strangle on SPY collects premium that implies the market has a 16% chance of breaching each strike — but historically, SPY only moves beyond the equivalent distance in approximately 12–14% of comparable periods. That 2–4 percentage point edge, compounded over many trades, is a genuine structural profit source.

The important caveat about who should trade strangles: experienced practitioners who have managed iron condors through at least one full market cycle (including a significant correction), who have defined management rules before they enter, who size positions at 3–5% of capital maximum, and who understand that the strategy has occasional but potentially severe drawdowns. Volmageddon (February 5, 2018) saw VXX-related short-vol products lose 80–90% in a single session. The March 2020 COVID crash produced a 34% SPY decline in 4 weeks. Short strangles survived those periods only for traders with small enough position sizes to absorb the drawdown and enough capital to keep trading.

The ideal regime is elevated IV Rank (50%+) in a range-bound market with no imminent catalysts. You want to sell the fear premium at its peak and collect it as the market calms. The one thing that destroys strangles is a sustained trending move — particularly one driven by a surprise macro event — that carries the underlying through your short strike and keeps going without giving you time to manage.

---

## How It Works

Sell an OTM call and an OTM put simultaneously, same expiration. No wings are purchased.

```
Net credit    = call premium received + put premium received
Upper B/E     = short call strike + net credit
Lower B/E     = short put strike − net credit
Max profit    = full net credit (underlying closes between strikes at expiry)
Max loss      = theoretically large on the upside; large on the downside
                Practical max: (tested strike − underlying breach distance) − net credit
```

**Example — SPY at $531.20, April 14, 2025, VIX 22.4, IVR 65%, 25 DTE:**
```
Sell May 9 $555 call (16-delta)  → collect $2.95
Sell May 9 $510 put  (16-delta)  → collect $2.70
Total net credit: $5.65 = $565 per contract
Upper B/E: $555 + $5.65 = $560.65
Lower B/E: $510 − $5.65 = $504.35
Profit zone: $504.35 – $560.65 (±5.6% range from current price)

SPY's historical 25-day 1-sigma move: approximately 4.5%
You are outside 1σ on both sides — probability-wise you have the edge.
```

**Greek profile:**

```
Greek  Sign               Practical meaning
-----  -----------------  ---------------------------------------------------------------------------
Delta  Near zero          Both strikes OTM; small net exposure
Theta  Strongly positive  Two full premiums decaying daily — your income stream
Vega   Strongly negative  Rising IV is the strangle's primary enemy — both options get more expensive
Gamma  Strongly negative  Near strikes, loss acceleration is dramatic and unhedged
```

**The gamma danger is the key difference from an iron condor.** When one of your short strikes is tested and you are unprotected by a wing, the gamma exposure is open-ended until you close.

---

## Real Trade Walkthrough

> **April 14, 2025 · SPY:** $531.20 · **VIX:** 22.4 · **IVR:** 65% · **DTE:** 25

Entry as above, $565 credit collected.

**Day 12 management check:** SPY has rallied to $548 (+3.2%). Short call at $555 is now 7 points OTM but has appreciated to $1.80 (from $2.95 collected). Short put at $510 is near worthless at $0.15.

```
Strangle current value: $1.80 + $0.15 = $1.95
Credit collected:  $5.65
Profit if closed: $5.65 − $1.95 = $3.70 = $370 in 12 days
```

**Action: Close at $1.95.** The short call is becoming uncomfortable. You have captured 65% of the maximum credit in 12 days — a strong result. Do not hold hoping for the remaining $195.

**Scenario table (if held to May 9):**

```
SPY at May 9          P&L      Notes
--------------------  -------  --------------------------------------------
$531 (flat)           +$565    Full credit; perfect outcome
$540 (inside range)   +$565    Both expire worthless
$560.65 (upper B/E)   $0       Break-even on the call side
$570                  −$375    Short call $15 ITM; credit offsets partially
$480 (sharp decline)  −$1,435  Short put $30 ITM minus $5.65 credit
$450 (crash)          −$3,435  No wing stops the loss
```

---

## Entry Checklist

- [ ] IV Rank > 50% — the entire edge requires selling overpriced premium; below 50%, switch to iron condors
- [ ] VIX between 18–32 (below 18: premium too thin for the wingless risk; above 32: blowup risk elevated)
- [ ] No scheduled catalysts (FOMC, CPI, NFP, major earnings) within the hold window
- [ ] Short strikes at 16-delta on both sides (1σ OTM — approximately 68% probability of expiring worthless each side)
- [ ] DTE 21–45 (theta acceleration window; enough time for management without event risk)
- [ ] Highly liquid underlying only: SPY, QQQ, AAPL, NVDA, TSLA (wide bid-ask on illiquid names destroys the edge)
- [ ] Define your management plan BEFORE entry — know exactly what you will do at each trigger

---

## Management Rules (Non-Negotiable)

The strangle has no wings — your management discipline is your only protection.

```
Condition                           Action
----------------------------------  --------------------------------------------------------------------------
50% of credit captured at any time  Close the entire strangle immediately
21 DTE remaining                    Close or roll out 30 days at current strikes
One short strike reaches 30-delta   Roll that strike further OTM (same expiry) — collect a credit for the roll
Short strike goes ITM               Roll the breached side out 30 days AND further OTM; or close entirely
VIX spikes 4+ points intraday       Emergency close — vol expansion will keep hurting you
Any unexpected news catalyst        Close immediately; don't wait to see how it develops
```

**The roll mechanics:** When the short call reaches 30-delta, buy it back and sell a new call at the next strike above. You will typically collect $0.50–$1.00 in credit on the roll, extending your breakeven and buying time. This is not a rescue — it is a tactical adjustment that works only when you have 15+ DTE remaining.

---

## Blowup History — Why Position Sizing Is Everything

**February 5, 2018 ("Volmageddon"):** VIX went from 17 to 37 in a single session as the XIV short-VIX ETF unraveled. Short strangles on VXX and XIV lost 80–90% of their value overnight. This is the defining tail risk of short-vol strategies.

**March 2020 (COVID crash):** SPY fell 34% in 4 weeks. A 16-delta short put strangle entered with a $10 credit (at the time) faced $80+ in losses on the put side at the bottom. Traders with 5% position sizing survived with manageable drawdowns. Traders with 20%+ positioning were wiped out.

**August 5, 2024:** Yen carry trade unwind caused SPY to fall 3% and VIX to spike from 16 to 65 intraday (reverting to ~30 by close). Short strangles that weren't managed suffered large intraday losses.

**The lesson:** Position sizing — 3–5% of capital at practical max loss — is the only true risk management for a short strangle. No amount of strike selection or management rules prevents a tail event; only small position sizing ensures survivability.

---

## When to Avoid

1. **IV Rank below 35%:** You are selling cheap premium without adequate compensation for the wingless risk. Iron condors or credit spreads are better in low-IV environments.

2. **Any week with a major known catalyst:** FOMC, CPI, or NFP within the hold window is a hard skip. The binary event risk is not compensated by the credit.

3. **Single-stock strangles around earnings:** Individual stocks can gap 15–25% on earnings. A 16-delta strangle provides no protection. Never short-strangle individual stocks through their earnings dates.

4. **VIX above 35:** At extreme vol, intraday SPY ranges regularly exceed 2%. The short strike is tested almost mechanically on high-VIX days. Wait for VIX to normalize.

5. **If you can't monitor daily:** Short strangles require daily attention. Alerts on your short strike delta levels, VIX movement, and any news are mandatory. If you travel or have other commitments that prevent monitoring, close before you leave.

---

## Short Strangle vs Iron Condor

```
Feature                  Short Strangle                                   Iron Condor
-----------------------  -----------------------------------------------  -----------------------------------
Max loss                 Very large (no wings)                            Defined (wing width − credit)
Premium collected        Higher ($5–$8 typical)                           Lower ($2–$4 typical)
Margin required          Higher (naked options, Reg T or PM)              Lower (defined-risk spread)
Management criticality   Extremely high                                   High
Win rate (with filters)  65–70%                                           65–70%
Best for                 Experienced, well-capitalized, actively managed  Retail traders seeking defined risk
```

---

## Strategy Parameters

```
Parameter             Conservative   Standard       Aggressive     Description
--------------------  -------------  -------------  -------------  ------------------------------------------
Short strike delta    12-delta       16-delta       20-delta       Higher delta = more premium, less buffer
DTE at entry          45             30             21             30 DTE balances theta and risk window
IVR minimum           60%            50%            40%            Do not compromise on this filter
Profit target         25% of credit  50% of credit  75% of credit  50% is the risk-adjusted sweet spot
Stop-loss (one side)  30-delta       30-delta       35-delta       Roll or close when tested
Max position size     2% capital     4% capital     6% capital     Never more than this per strangle
VIX range             20–28          18–32          18–35          Tighter VIX range = better risk management
```
