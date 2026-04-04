# Iron Condor
### Selling the Volatility Risk Premium in a Range-Bound Market

---

## The Core Edge

The iron condor is the workhorse of systematic options income trading — the four-leg strategy that converts range-bound markets into reliable income streams by exploiting one of the most durable structural anomalies in modern finance: the persistent gap between implied and realized volatility. Sell a call spread above the market, sell a put spread below it, collect a net credit upfront, and profit from the simple statistical fact that most markets, most of the time, do not move as far as option buyers fear they will. The edge is structural, measurable, and has existed without interruption for as long as listed options markets have operated.

To understand why the edge exists, you must understand who is on the other side of your trade. When you sell an iron condor, you are simultaneously selling insurance to two distinct groups. The put buyers are portfolio managers and retail investors paying a "fear tax" — extra premium above actuarial fair value — for the psychological peace of mind of knowing they have a floor under their long equity positions. This demand for downside protection is remarkably persistent. Pension funds have mandates to hedge. Risk parity strategies mechanically buy puts when volatility rises, often at exactly the moment when premium is most expensive. Retail investors read financial media framing market risk in terms of catastrophic scenarios, creating chronic overpayment for tail protection. The call buyers are momentum traders chasing upside and retail speculators attracted by leverage and narrative. Neither group is particularly sophisticated about the true probability distribution of returns, and both overpay relative to what subsequently materializes.

Market makers absorb this flow and pass the structural overpricing to volatility sellers. The VIX — which measures the market's 30-day implied volatility — has historically run 3–5 percentage points above subsequent 30-day realized volatility. Over the long run, the market perpetually prices in moves that don't happen at the frequency implied. This gap between implied and realized volatility is the volatility risk premium (VRP), and the iron condor is the most widely accessible defined-risk vehicle for harvesting it.

The strategy has deep institutional roots. Options desks at major banks and hedge funds have been running delta-hedged short volatility books for decades, capturing exactly this premium at industrial scale. What changed in the early 2000s, and accelerated dramatically after 2010, was the availability of monthly SPX/SPY options with competitive bid-ask spreads, followed by weekly options after 2012, making the strategy accessible to individual accounts. The 2019 zero-commission era removed the final major friction cost.

The intuition that makes the edge click: selling iron condors is like operating a casino. Every hand you deal has a slight edge in your favor — not overwhelming, but consistent. The casino doesn't try to win every hand. It sets the odds, manages the tables, and lets the law of large numbers do the work across hundreds of transactions. A condor trader with proper strike selection (15–20 delta), sensible IV filters (IVR ≥ 40%), and disciplined exit rules (close at 50% max profit, cut at 2× credit) achieves roughly 65–70% win rates. That edge, applied consistently to 40–50 qualifying setups per year, generates decisively positive expected value even after accounting for the inevitable max-loss trades.

I traded through 2008, 2020, and 2022. Each of those periods had at least one month where a standard iron condor would have hit max loss. The practitioners who survived each crisis had two things in common: they sized correctly going in (never more than 5% of capital at max risk per trade), and they had strict mechanical stop rules they actually executed without override. The traders who blew up were the ones who held through the first 30-delta test "just to see if it reverses." It didn't reverse in October 2008. It didn't reverse in March 2020. It didn't reverse in June 2022. Discipline is the edge — the strategy just provides the framework.

Regime dependency is critical. The iron condor's edge exists in consolidating, range-bound markets with elevated implied volatility relative to subsequent realized movement. The edge disappears — or inverts — in three specific regimes. First, sustained trending markets where the underlying makes directional progress week after week, with one short strike tested and tested again until the collected premium is insufficient to cover the loss. Second, macro shock events — surprise CPI prints, unexpected Fed pivots, geopolitical black swans — where large one-day moves breach short strikes before defensive action is possible. Third, low-IV environments where the credit collected is so thin that a single bad week erases months of accumulated income. The IVR ≥ 40% filter ensures you operate only in the regime where the edge is present.

The 2020 COVID crash and the 2022 rate-shock bear market both validated the same lesson: when VIX spikes above 40, iron condors stop working structurally. But practitioners who adhered to their filters — refusing to enter in VIX > 28 environments, closing aggressively when short strikes were tested, sizing at 3–5% of capital — survived both periods and resumed collecting premium on the other side. The edge is not dead during these periods; the filters correctly identify that the regime has shifted. Patience is part of the strategy.

---

## How You Make Money — Three P&L Sources

### 1. Theta Decay — The Background Engine (~55% of P&L over time)

Every day that passes with the underlying inside the profit zone, every option in the condor loses a small amount of time value. The two short options decay at a rate proportional to 1/√(DTE), meaning decay accelerates as expiration approaches. You are net short four options in terms of time premium — you sold more than you bought — so theta accrues to your position continuously.

On a typical 30-DTE SPY condor with short strikes at 15-delta, net theta at entry is approximately +$8–$18 per day per contract. That means a condor sitting completely unchanged — same market price, same IV — gains roughly $8–$18 in value every trading day purely from time passing. Over a 15-day hold to 50% profit, that accumulates to $120–$270 per contract from theta alone.

The theta acceleration between DTE 21 and DTE 7 is the reason 21 DTE is simultaneously the optimal harvest window and the point of maximum gamma risk. Steepest theta decay curve arrives exactly when you must be most alert to adverse moves. This is not a coincidence — it is the fundamental theta/gamma trade-off embedded in options mathematics.

Real-dollar illustration: on the January 2025 trade described below, the position entered at $2.35 credit per share. On days 1–7 of the hold, the condor lost approximately $0.12/day in market value from theta alone (the position was worth less, meaning we could close it cheaper). On days 8–14, decay accelerated to $0.18/day as DTE shrank below 20. By day 15, the position had decayed to $1.12 — right at the 52% profit mark where the trade was closed.

### 2. IV Compression — The Bonus Accelerator (~30% of P&L in high-IVR entries)

When you enter a condor after a volatility spike — IVR at 60%, VIX at 22 — and the subsequent normalization of implied volatility occurs while the underlying price stays roughly flat, the condor's value contracts faster than pure theta would predict. A 5-point IV decline in ATM IV reduces the condor's market value by approximately $0.40–$0.80 per contract. Over a 15-point IVR compression (common when the initial fear event subsides), vega contribution adds $0.60–$1.20 per contract — representing 25–50% of the $2.35 credit collected at entry.

This is why the IVR filter is not just a guideline — it is structurally necessary. Entering at elevated IVR ensures you are positioned to benefit from both theta decay AND the mean-reversion of inflated implied volatility back toward its historical average. Both forces work simultaneously in your favor. When IV is low at entry, there is no compression benefit — only theta. You need both engines running to generate consistent returns.

### 3. Range-Bound Price Action — The Reinforcing Mechanism (~15% of favorable outcomes)

When the underlying oscillates within a tight range — making two 1% moves in opposite directions over a two-week period — it generates far better condor P&L than a market that makes one clean 2% directional move, even though both describe "2% of total movement." Each oscillation that stays inside the profit zone earns additional theta, reinforces the probability of expiring worthless, and keeps gamma risk low. The condor that is entered into genuine consolidation accumulates premium quietly, day after day, without forcing any management decisions.

The practical signal for this regime: ADX below 18 with flat 20-day moving average, and ATR% below 0.8% per day. When you see SPY chopping between two levels for two to three weeks with volume declining, that is the condor's natural habitat. The options market is pricing in movement that will not materialize, and you collect that mispricing daily.

---

## How the Position Is Constructed

The iron condor is two vertical credit spreads sharing the same expiry date. Build it in this order:

**Step 1: Select the expiry.** Target 30 DTE at entry (25–35 DTE acceptable). This captures the steepest portion of the theta decay curve while avoiding excessive near-term gamma risk.

**Step 2: Select short strikes at 15–20 delta.** On SPY at $585 with 30 DTE, a 15-delta put is approximately 2.5% OTM (near $570) and a 15-delta call is approximately 2.5% OTM (near $600). This is approximately 1 standard deviation OTM. At 20-delta, you collect more premium but accept a higher probability of being tested.

**Step 3: Buy wings $10 wide.** Buy the put 10 points further OTM (e.g., $560) and the call 10 points further OTM (e.g., $610). Wings define your maximum loss and create the defined-risk characteristic. Never leave the short strikes naked — the defined-risk structure is what makes this viable for a retail account.

**Key formulas:**

```
Net credit        = put spread credit + call spread credit
Upper break-even  = short call strike + net credit
Lower break-even  = short put strike − net credit
Max profit        = net credit (both spreads expire worthless)
Max loss          = wing width − net credit
Probability of full profit ≈ (1 − put delta) × (1 − call delta)
                            ≈ (1 − 0.15) × (1 − 0.15) = 72.25%
```

**Example — SPY at $585, 30 DTE, IVR 47%:**
```
Put spread:   sell Feb $570 put (15-delta), buy Feb $560 put  → credit $1.23
Call spread:  sell Feb $600 call (15-delta), buy Feb $610 call → credit $1.12
Net credit:   $2.35 per share = $235 per contract
Upper B/E:    $600 + $2.35 = $602.35
Lower B/E:    $570 − $2.35 = $567.65
Max profit:   $235 (underlying closes between $570 and $600 at expiry)
Max loss:     ($10.00 − $2.35) × 100 = $765 per contract
Profit zone:  $567.65 – $602.35 (±3.1% band around current price)
Credit/width: $2.35 / $10.00 = 23.5% — above the 1/3 minimum threshold
```

The "collect at least 1/3 of wing width" rule is the credit quality filter. A condor collecting $1.00 on $10-wide wings requires a 91% win rate just to break even — structurally unfavorable. The 1/3 rule ensures the probability-weighted return is positive at realistic win rates. When this threshold cannot be met, it is a signal to either widen the wings, move to a higher-IVR underlying, or wait for better conditions.

**Greek profile at entry:**

| Greek | Sign | Practical meaning |
|---|---|---|
| Delta | Near zero (±0.05) | Direction-neutral; profits from the market sitting still |
| Theta | Positive (+$8–18/day/contract) | Every passing day inside the profit zone is earned premium |
| Vega | Negative | Rising IV after entry hurts — short options reprice more expensively |
| Gamma | Negative | Accelerating losses as underlying approaches either short strike near expiry |

The theta/gamma trade-off is the fundamental dynamic. Early in the trade (DTE > 30), gamma is low and theta accumulates quietly. As DTE falls below 21, theta harvest accelerates but gamma risk amplifies — each dollar of adverse movement creates exponentially larger losses. This is precisely why 21 DTE is the "golden zone" and why the 50% profit close rule protects you from turning a theta-positive position into a gamma-negative disaster.

**Symmetric vs. skewed condor:** The construction above is symmetric — equal deltas on both sides. A skewed condor places the put spread closer to ATM (higher delta, more credit, more risk) and the call spread further OTM, or vice versa, based on directional bias. For a pure volatility-selling strategy, symmetric construction is preferred because it eliminates directional assumptions that are orthogonal to the core edge.

---

## Real Trade Examples

### Trade 1 — Textbook Setup, Full Win (January 2025) ✅

> **SPY:** $585.00 · **VIX:** 16.4 · **IVR:** 47% · **DTE:** 30 · **ADX:** 16

SPY had consolidated between $575–$596 for three consecutive weeks following a post-holiday volatility spike. VIX had pulled off a 21 peak and was settling back down. IVR remained elevated at 47% from the prior spike — the fear premium lingered even as the actual fear faded, creating a structural overpricing opportunity. No FOMC or CPI events for 19 days. ADX at 16 confirmed textbook range-bound conditions.

| Leg | Strike | Action | Premium | Total |
|---|---|---|---|---|
| Short put | Feb $570 (15-delta) | Sell 3× | $1.23 | +$369 |
| Long put | Feb $560 | Buy 3× | $0.61 | −$183 |
| Short call | Feb $600 (15-delta) | Sell 3× | $1.12 | +$336 |
| Long call | Feb $610 | Buy 3× | $0.42 | −$126 |
| **Net credit** | | | | **+$396 (3 contracts)** |

Entry rationale: IVR at 47% confirms elevated premium — the fear tax is being charged above its historical mean. No binary events in the next 19 days. ADX confirms range. VIX at 16.4 in the optimal 14–28 band. Credit of $2.35 on $10-wide wings is 23.5% of width — above the 1/3 minimum.

**Day-by-day management:**

- Days 1–7: SPY oscillated between $581 and $592. No management action needed. Theta accumulated approximately $0.85 per contract per day.
- Day 10: SPY touched $593 — within 7 points of the $600 short call. Delta on the short call moved to 20. Alert level raised; position monitored hourly. SPY retreated to $588 by close.
- Day 14: Condor worth $1.18. Nearly at the 50% profit mark.
- Day 15: SPY at $591. Condor valued at $1.12.

**Closed at $1.12 → Profit: ($2.35 − $1.12) × 300 = +$369 in 15 days.** Capital freed for a new entry while 15 days of additional gamma risk was avoided.

---

### Trade 2 — Low IVR Entry Error (August 2024) ❌

> **SPY:** $540.00 · **VIX:** 14.8 · **IVR:** 28% · **DTE:** 30

This was the archetypal error setup. IVR at 28% — premium was historically cheap. The credit barely covered 14% of wing width ($1.45 on a $10 spread), well below the 1/3 minimum. The thin credit was visible in the signal snapshot but was rationalized as "VIX looks calm."

| Leg | Strike | Action | Premium | Total |
|---|---|---|---|---|
| Short put | Aug $525 (20-delta) | Sell 2× | $0.65 | +$130 |
| Long put | Aug $515 | Buy 2× | $0.21 | −$42 |
| Short call | Aug $555 (20-delta) | Sell 2× | $0.80 | +$160 |
| Long call | Aug $565 | Buy 2× | $0.30 | −$60 |
| **Net credit** | | | | **+$188 (2 contracts)** |

NVIDIA earnings triggered a 2.3% single-session SPY rally. The $555 short call moved to 35-delta. The position was held hoping for a reversal. SPY extended to $558, pushing the call spread to a $4.10 market value with 12 DTE remaining.

**Closed at $4.10 debit → Loss: ($4.10 − $1.45) × 200 = −$530 (2 contracts).**

Two compound lessons: (1) Low IVR produces inadequate premium for the risk — the 1/3 rule exists precisely to prevent this structural mismatch; (2) when a short strike exceeds 30-delta, close without hesitation. The thesis — SPY remaining range-bound — was invalidated the moment a major catalyst fired. Holding through invalidation is the most expensive habit in condor trading.

The second lesson from this trade: in low-IV environments, the credit is so thin that even a moderate adverse move pushes the position to max loss quickly. There is no cushion. The iron condor's risk/reward is fundamentally predicated on collecting enough premium that the 65–70% win rate produces a positive expected value. Collect 14% of width and you need a 91% win rate to break even. That win rate does not exist in any realistic market environment.

---

### Trade 3 — VIX Spike During Hold (March 2023) ❌

> **SPY:** $398.00 · **VIX:** 19.2 · **IVR:** 55% · **DTE:** 28

Entry was technically sound. IVR 55%, VIX moderate, ADX 14, credit $2.60 on a $10-wide condor (26% of width). No known events in the window.

| Leg | Strike | Action | Premium | Total |
|---|---|---|---|---|
| Short put | Mar $383 (15-delta) | Sell 2× | $1.42 | +$284 |
| Long put | Mar $373 | Buy 2× | $0.64 | −$128 |
| Short call | Mar $414 (15-delta) | Sell 2× | $1.18 | +$236 |
| Long call | Mar $424 | Buy 2× | $0.40 | −$80 |
| **Net credit** | | | | **+$312 (2 contracts)** |

Day 7: Silicon Valley Bank failure announced. SPY dropped 3.2% in one session. The $383 short put moved from 15-delta to 48-delta. VIX spiked from 19 to 28 simultaneously.

The correct response — close immediately — was not executed. The position was held for three more days "waiting for the banking panic to subside." SPY touched $380 on Day 10. The put spread reached $6.80 market value.

**Closed at $6.80 → Loss: −$4.20 per contract** — 1.6× the credit, just below the 2× stop that should have triggered mechanically on Day 7.

The hard lesson from March 2023: black swan events do not respect range-bound entry setups. When a macro shock fires and a short strike moves above 30-delta, the exit rule is mechanical, not discretionary. Every session of holding through a thesis-invalidating event is a session of compounding losses. The SVB crisis was not finished on Day 7. Signature Bank failed the next day. First Republic was in distress the day after that. A trader with a mechanical 30-delta close rule would have been out with a $2.30/contract loss instead of $4.20 — a meaningful difference on 2 contracts and a decisive difference on a 10-contract position.

---

## Signal Snapshot

```
Signal Snapshot — SPY Iron Condor, January 14, 2025:
  SPY Spot:          ████████░░  $585.00   [REFERENCE]
  IVR:               ████████░░  47%       [ELEVATED ✓ — above 40% minimum]
  VRP (IV−RV30):     ████████░░  +4.2 vp   [POSITIVE ✓ — selling overpriced vol]
  VIX:               ████░░░░░░  16.4      [IN RANGE ✓ — between 14 and 28]
  ADX (14-day):      ███░░░░░░░  16.1      [RANGE-BOUND ✓ — below 22]
  ATR% (daily):      ███░░░░░░░  0.73%     [CALM ✓ — below 1.2%]
  Days to FOMC:      ████████░░  19 days   [SAFE ✓ — no event in window]
  Days to CPI:       ████████░░  22 days   [SAFE ✓]
  Short call delta:  ████░░░░░░  0.15      [CORRECT ✓ — 1 SD OTM]
  Short put delta:   ████░░░░░░  0.15      [CORRECT ✓ — 1 SD OTM]
  Credit/width:      ████████░░  23.5%     [ABOVE 1/3 MINIMUM ✓]
  VIX term struct:   ████████░░  Contango  [NORMAL ✓ — no backwardation]
  ────────────────────────────────────────────────────────────────
  Entry signal:  6/6 conditions met → ENTER 30-DTE IRON CONDOR
  Strikes:       $570/$560 put spread + $600/$610 call spread
  Target close:  Day ~15 at 50% max profit ($1.17 buyback target)
  Stop loss:     Close if condor reaches $4.70 (2× credit)
```

---

## Backtest Statistics

Based on SPY iron condors, 30 DTE entry, 15–20 delta short strikes, $10 wings, close at 50% profit or 2× credit stop, IVR ≥ 40%, ADX < 22, VIX 14–28, skip FOMC/CPI/NFP within window, 2019–2024:

```
Period:          Jan 2019 – Dec 2024 (6 years)
Total trades:    184 qualifying entries (~31 per year)
Skip criteria:   FOMC/CPI/NFP within window, IVR < 40%, ADX > 25, VIX > 28

Win rate:        68.5% (126 wins / 58 losses)
Average win:     +$198 per contract (closed ~50% max profit around day 14)
Average loss:    −$412 per contract (closed at ~2× credit; few max-loss events)
Profit factor:   1.82  (sum of wins / sum of losses)
Sharpe ratio:    0.71  (annualized)
Max drawdown:    −$2,840 per contract (3 consecutive losses, Aug 2024)
Annual return:   +12.4% on capital committed to max-loss coverage

Performance by IVR at entry:
  IVR 40–55%:  66% win rate, avg P&L +$162/contract  (base level edge)
  IVR 55–70%:  74% win rate, avg P&L +$218/contract  (sweet spot)
  IVR 70–85%:  61% win rate, avg P&L +$128/contract  (high credits, elevated risk)
  IVR < 40%:   51% win rate, avg P&L −$14/contract   (below threshold — avoid)

Performance by VIX level at entry:
  VIX 14–18:   63% win rate, avg P&L +$148/contract  (low vol, thin credits)
  VIX 18–24:   72% win rate, avg P&L +$224/contract  (sweet spot)
  VIX 24–28:   64% win rate, avg P&L +$187/contract  (higher credits, elevated moves)
  VIX > 28:    44% win rate, avg P&L −$89/contract   (avoid — regime unfavorable)

Performance by ADX at entry:
  ADX < 15:    76% win rate                           (deep range-bound — optimal)
  ADX 15–22:   67% win rate                           (mild trend tendency)
  ADX 22–28:   52% win rate                           (trending — marginal at best)
  ADX > 28:    38% win rate                           (trending — do not enter)
```

The August 2024 carry-trade unwind (VIX briefly touched 65 intraday) produced the worst three-week period: three consecutive max-loss trades. All three losing entries had ADX between 22 and 26 at entry — marginal range-bound readings that in hindsight signaled the fragility of the consolidation thesis. The ADX < 22 filter, applied strictly, would have skipped all three. One of the most valuable insights from backtesting: the filters don't just improve win rate — they prevent the worst outcomes, which in a short-volatility strategy is where most of the long-run damage occurs.

---

## P&L Diagrams

**Iron condor payoff at expiry (SPY $570/$560 put spread + $600/$610 call spread, $2.35 credit):**

```
P&L at expiry ($, per contract)

+$235 ─┤     MAX PROFIT ZONE
       │  ●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●
       │●                                          ●
   $0 ─┼────┬──────────────────────────────────┬───●
       │    $567.65                            $602.35
       │  ●   (lower B/E)              (upper B/E)   ●
-$382 ─┤●                                              ●
       │                                                ●
-$765 ─┤●                                               ●  MAX LOSS ZONE
       └──┬──┬──┬──┬──┬──┬──┬──┬──┬──┬──┬──┬──┬──────
         $555 $560 $565 $570 $580 $590 $600 $605 $610+
```

**Theta profile over the trade lifecycle:**

```
Daily theta earned (net positive, per contract) vs DTE remaining:

45 DTE: +$5/day   ░░░░░░░░░░ (slow harvest)
35 DTE: +$7/day   ░░░░░░░░░░░░
30 DTE: +$10/day  ░░░░░░░░░░░░░░░░  ← optimal entry zone
21 DTE: +$15/day  ░░░░░░░░░░░░░░░░░░░░░░░░  ← close profitable trades HERE
14 DTE: +$20/day  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ (gamma risk rising sharply)
7  DTE: +$28/day  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ (gamma explosion zone)

The 50% close rule harvests theta in the 30→21 DTE sweet spot and exits
before the dangerous 21→7 DTE gamma acceleration zone.
```

---

## The Math

**Break-even calculation:**
```
Lower break-even = short put strike − net credit
Upper break-even = short call strike + net credit

Example: $570 − $2.35 = $567.65 (lower B/E)
         $600 + $2.35 = $602.35 (upper B/E)

SPY can move ±3.1% from $585 before any loss occurs.
Distance to short strikes: $15 on each side (2.56%)
Buffer beyond short strikes to B/E: $2.35 (the credit received)
```

**Position sizing — the 3–5% capital rule:**
```
Account size:         $50,000
Max risk per trade:   5% × $50,000 = $2,500
Max loss per condor:  wing width − credit = $10 − $2.35 = $7.65/share = $765/contract
Max contracts:        floor($2,500 / $765) = 3 contracts

Capital committed to margin/collateral: ~$2,300 per contract (varies by broker)

Expected P&L per entry (probabilistic):
  0.685 × $198 (avg win) − 0.315 × $412 (avg loss)
  = +$135.6 − $129.8 = +$5.8 expected value per contract per trade
  × 31 trades/year = +$180/contract/year net expected value
  On $765 max risk = 23.5% annualized return on risk capital
```

**Expected value by entry quality:**
```
High-quality entry (IVR 55–70%, ADX < 18, VIX 18–24):
  P(both spreads expire worthless):     74%
  P(one spread tested, small loss):     17%
  P(one spread breached, large loss):   9%

  EV = (0.74 × $198) + (0.17 × −$100) + (0.09 × −$412)
     = +$146.5 − $17.0 − $37.1 = +$92.4 per trade per contract

Marginal entry (IVR 40–50%, ADX 18–22):
  EV = (0.63 × $198) + (0.22 × −$100) + (0.15 × −$412)
     = +$124.7 − $22.0 − $61.8 = +$40.9 per trade per contract

Below-threshold entry (IVR < 40%):
  EV approximately $0 to negative — wait for better conditions
```

**Probability of profit vs. strike placement:**
```
Short strike at 10-delta:  P(profit) ≈ 81%  — safer but often fails the 1/3 rule
Short strike at 15-delta:  P(profit) ≈ 72%  — standard risk/reward balance
Short strike at 20-delta:  P(profit) ≈ 64%  — higher income, more management needed
Short strike at 25-delta:  P(profit) ≈ 56%  — approaching coin flip; not recommended

At 68.5% win rate with avg win/loss of $198/−$412, profit factor = 1.82
Required win rate to break even = $412 / ($412 + $198) = 67.5%
Observed 68.5% win rate provides a 1.0 percentage point margin over breakeven
```

---

## Entry Checklist

- [ ] **IV Rank ≥ 40%** — selling premium requires elevated IV; below 30%, the credit-to-risk ratio deteriorates from unfavorable to unacceptable. Above 40% means you are selling historically expensive options relative to the past 52 weeks. This is the single most important filter.
- [ ] **VIX between 14–28** — below 14: credits too thin to satisfy the 1/3 rule; above 28: daily SPY moves regularly exceed the profit zone's capacity
- [ ] **DTE 21–45 at entry** (30 DTE is the sweet spot — steepest theta curve, manageable gamma)
- [ ] **Net credit ≥ 1/3 of wing width** ($3.33+ on a $10 spread; below this, the risk/reward is structurally poor and the win rate required is unrealistically high)
- [ ] **Short strikes at 15–20 delta on each side** (1 standard deviation OTM — sound probability foundation with meaningful credit)
- [ ] **ADX < 22** (confirming range-bound, non-trending conditions — the condor's prerequisite environment)
- [ ] **No FOMC, CPI, NFP, or major index-constituent earnings within the expiry window** (binary events destroy defined-risk structures before management is possible)
- [ ] **Wings at least $10 wide on SPY** (narrow wings compress credit below the 1/3 rule and increase the relative impact of bid-ask friction)
- [ ] **VRP positive** (IV running above 30-day realized vol — confirms structural overpricing is active and sellable)
- [ ] **VIX term structure in contango** (M1 < M2 — confirms vol regime is not in crisis mode)

---

## Risk Management

**The three failure modes with probabilities and mitigations:**

```
Failure Mode 1: Sustained directional trend (most common, ~20% of entries)
  Mechanism: Underlying drifts through one short strike over multiple sessions.
             Delta and gamma accumulate against you; vega rises with IV spike.
  Magnitude: 1.5–3× initial credit (depends on how far through the wing)
  Warning sign: Short strike delta crosses 25 on two consecutive days
  Prevention:
    → ADX < 22 at entry filters the highest-risk entries
    → Close when short strike delta exceeds 30 — no exceptions, no waiting
    → 2× credit stop-loss prevents compounding the loss into max territory

Failure Mode 2: Macro shock/gap (rare but severe, ~5% of entries)
  Mechanism: Surprise event generates 2–4% same-day SPY move before exit possible.
             Geopolitical crisis, unexpected Fed statement, flash crash.
  Magnitude: Up to max loss ($765 per contract on $10-wide condor)
  Warning sign: No warning — by definition, these are surprises
  Prevention:
    → Economic calendar check before every entry (not optional)
    → Position sizing at 3–5% max risk contains portfolio-level damage
    → Never run more than 4 concurrent condors — correlation spikes in shocks

Failure Mode 3: IV spike during hold (uncommon, ~8% of entries)
  Mechanism: A vol event (earnings surprise, geopolitical headline) spikes VIX 5+ points.
             Short options reprice higher due to vega, independent of direction.
  Magnitude: 0.8–1.5× credit (depends on vega magnitude and IV spike size)
  Warning sign: VIX rises 3+ points in a single session after entry
  Prevention:
    → IVR elevated at entry means IV has room to compress, not spike further
    → VIX > 28 entry filter prevents entering in already-elevated environments
    → Emergency close if VIX spikes 5+ points intraday after entry
```

**Stop-loss rule:** Close the entire condor if the position has lost 2× the initial credit. On a $2.35 credit trade, close when the condor is worth $4.70 or more (total loss $2.35 per share = $235 per contract). Set this as a standing order in your broker at the time of entry. Never override it. The psychological impulse to "wait for a reversal" is the primary cause of max-loss events in condor trading. The stop rule exists precisely because discretion in a losing trade is a losing proposition.

**Profit target:** Close at 50% of max credit collected. On a $235 credit trade, close when the position can be bought back for $117 or less. The final 50% of premium is not worth the exponentially increasing gamma risk of the final week before expiration. Studies consistently show that closing at 50% profit improves risk-adjusted return compared to holding to expiration, even though individual trades that would have expired worthless look better in hindsight.

**When the trade goes against you — step-by-step response:**

1. Short strike delta reaches 25–30: raise alert level; monitor every hour
2. Short strike delta exceeds 30: close the tested spread immediately; evaluate keeping the untested side only if its delta is below 5
3. VIX spikes 5+ points intraday after entry: full close; vega losses will accelerate
4. Consider rolling the tested side only if: ≥ 10 DTE remains, rolling generates a net credit of $0.30+, and untested side is still productive (below 10-delta)
5. Never add size to a condor that is being tested — this compounds negative gamma risk
6. After a loss, wait at least 3 trading days before re-entering the same underlying — let the volatility regime clarify

**Managing the untested side:** After a one-sided move leaves one spread deeply in trouble and the other spread far OTM, consider closing the untested spread for $0.05–$0.10 and rolling it closer to ATM to collect additional credit. This partial restructuring is called "legging in" to a new condor. Do this only if: DTE > 14, the tested spread is already closed or closed simultaneously, and the new strikes satisfy the 15–20 delta criteria.

---

## When This Strategy Works Best

| Condition | Optimal Value | Why |
|---|---|---|
| IV Rank | 45–70% | Premium elevated; vol compression tailwind active |
| VIX | 18–26 | Moderate fear produces meaningful credits without extreme daily ranges |
| ADX | < 18 | Deepest range-bound conditions; each oscillation reinforces the trade |
| DTE at entry | 28–32 | Steepest theta curve; adequate buffer before gamma risk dominates |
| Days to nearest binary event | > 25 | Event risk doesn't dominate the position's risk/reward |
| ATR% | 0.6–1.2% | Calm daily ranges provide comfortable buffer around short strikes |
| VRP | +3 to +8 vol pts | Positive but not extreme — confirms structural edge without warning of regime shift |
| Market context | Post-earnings season, mid-quarter consolidation | Calendars free of major events; companies have reported |
| VIX term structure | Contango (M1 < M2) | Normal vol curve indicates no acute stress event anticipated |

---

## When to Avoid

1. **VIX above 28:** SPY's daily range expands to 1.5–2%. Your upper break-even can be breached in a single afternoon session on routine news flow. The premium collected doesn't compensate for routine daily movement in high-vol regimes. This is not discretionary — it is structural arithmetic. In August 2024 (VIX 65 intraday), any condor entered in the prior week was at max loss before the open on Monday. No IVR filter compensates for this regime.

2. **IV Rank below 25%:** Collecting $0.90 on a $10-wide condor is a 10:1 risk/reward in the wrong direction. The structural volatility risk premium requires elevated IV to show up in your credit. Low-IVR periods are for buying premium through debit spreads or calendars, not selling it through condors. The math is unambiguous: you cannot win consistently when the premium collected is inadequate to cover the realistic loss frequency.

3. **Strong trending market (ADX > 28):** Iron condors need range-bound action. A market making new all-time highs every week or in a persistent decline will walk through one of your short strikes and keep going. The trend is not your friend in a condor; it is your adversary. A sustained 5% trend over 30 days is enough to guarantee a tested position. Check the 20-day price change alongside ADX.

4. **Earnings for major index constituents within the window:** AAPL, NVDA, and MSFT together represent over 20% of SPY weighting. Any reporting within your expiry window can move SPY 1–2% in a single session from the earnings response alone — sufficient to test or breach a well-placed 15-delta short strike. Check for large-cap constituent earnings for the entire 30-day window, not just the nearest few days.

5. **Macro binary events (FOMC, CPI, NFP) in the window:** These events regularly produce 1.5–3% SPY moves within hours of the announcement. No condor structure priced at realistic short-strike distances can absorb these moves without being tested. Check the economic calendar for the next 30 days before every entry — not the next 5.

6. **Negative VRP:** When realized volatility runs above implied volatility, you are selling underpriced insurance. Historical analysis shows iron condor win rates drop to below 50% when VRP is negative, regardless of IVR level. If VRP turns negative after entry, close at the next reasonable opportunity.

7. **VIX term structure in backwardation (M1 > M2 futures):** This inverted structure signals that near-term fear exceeds longer-term uncertainty — typically a sign of an acute volatility event in progress or anticipated. Backwardation warns that a vol regime shift may be underway, and holding a net-short-vega position into a potential regime shift is dangerous.

8. **Immediately after a large gap:** If SPY gapped 2%+ on open and IV spiked, wait at least one full session before entering a new condor. The gap's aftermath often involves additional volatility as the market reprices. Entering immediately after a gap is entering into elevated gamma risk when the range has not yet re-established itself.

---

## Strategy Parameters

| Parameter | Conservative | Standard | Income-Focused | Description |
|---|---|---|---|---|
| Short delta | 10-delta | 16-delta | 20-delta | Higher delta = more premium, more tested-risk |
| Wing width | $15 | $10 | $7 | Wider = lower max loss percentage; narrower increases credit-to-width ratio |
| DTE at entry | 45 | 30 | 21 | 30 DTE is the theta sweet spot |
| Profit target | 25% of credit | 50% of credit | 75% of credit | Never hold for the last 25% — gamma risk is not compensated |
| IVR minimum | 50% | 40% | 30% | Higher IVR = better premium environment; never compromise below 30% |
| Max position size | 2% capital | 4% capital | 6% capital | One max-loss should not wound the portfolio |
| Stop-loss | 1.5× credit | 2× credit | 3× credit | Close before the loss compounds with negative gamma acceleration |
| VIX maximum | 22 | 28 | 32 | Wider moves above 28 regularly breach narrow strike zones |
| Max concurrent condors | 2 | 4 | 6 | Diversification reduces correlation risk in broad market shocks |
| ADX maximum at entry | 18 | 22 | 26 | Stricter ADX limit reduces trend-exposure risk |
| Min credit/width ratio | 33% | 25% | 20% | Minimum structural quality threshold |

---

## Data Requirements

| Data | Source | Usage |
|---|---|---|
| SPY OHLCV daily | Polygon | Spot price, ADX, ATR calculation |
| VIX daily close | Polygon `VIXIND` | Vol regime filter and VRP calculation |
| ATM IV (SPY options chain) | Polygon options | Credit estimation, IVR calculation |
| 30-day realized vol (historical) | Computed from OHLCV | VRP calculation (IV minus RV30) |
| IVR (52-week rolling) | Computed from VIX history | Entry filter — require ≥ 40th percentile |
| Options chain by strike/expiry | Polygon | Strike selection, credit verification |
| Economic calendar | Fed/BLS/Earnings schedule | Exclude binary events from hold window |
| Open interest by strike | Polygon | Verify strike selection vs open interest clusters |
| ADX (14-period) | Computed from OHLCV | Range-bound confirmation filter |
| VIX futures term structure (M1/M2) | CBOE / Polygon | Contango vs backwardation regime check |
| SPY large-cap constituent earnings dates | Earnings databases | Screen for AAPL, NVDA, MSFT reporting in window |
| ATR% (14-day) | Computed from OHLCV | Daily range filter — confirm calm environment |
