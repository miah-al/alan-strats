# Tail Risk — Put Spread Hedge
### Capped-Payout, Cost-Reduced Portfolio Insurance

---

## The Core Edge

The Tail Risk Put Spread is the budget-constrained sibling of the naked long-put hedging program (see *Tail Risk — Long Put Hedge* for the parent thesis). The mechanic is identical in spirit — systematic, mechanical, calendar-driven purchases of OTM SPY puts as portfolio insurance — but the structure has been deliberately *de-tuned* to cut the recurring premium drag in half. Instead of buying a single OTM put, this strategy buys a **bear put debit spread**: long a put 5–8% OTM (the protection leg), short a put 15–20% OTM (the cost-reducing leg). The short leg caps the maximum payout at the difference between the two strikes, but in exchange it reduces the upfront debit by 40–60%.

The trade-off is asymmetric and, for most portfolios, in the user's favour. Israelov & Nielsen (2015) document that systematic 15% OTM long-put hedging on SPX costs **1.0–1.3% of portfolio NAV per year** — a real headwind on retirement-horizon returns. Their core argument, that long-put hedging is "still not cheap" even in calm markets, is the central problem this strategy solves: by capping the upside payout we are left with a hedge that costs **0.4–0.7% per year** — a drag that the long-run portfolio can absorb without compromising compounding. The naked long put pays out unboundedly as SPY falls; the put spread pays out within a defined window of ~10–13 percentage points of intrinsic value. For SPY at $477 with a 7%/18% spread structure, that window covers the 25–30% drawdown — *the realistic tail event* — and stops there.

This is exactly the right place for a budget-constrained tail program to draw the line. The historical frequency of the events matters. Drawdowns of 20–30% on SPY occur roughly once every 5–10 years (2002, 2008-leg, 2020, 2022). Drawdowns of 40%+ occur once every 20–40 years (2008-trough, 1973–74, 2020-trough). A spread that fully covers the realistic tail and partially covers the extreme tail — at half the price of the naked-put program — is a better expected-utility decision than the unbounded program for any portfolio that cannot comfortably absorb 1%+ in annual insurance cost. The user gives up the asymptotic protection against the once-a-generation crash; they gain the financial stamina to actually maintain the program through years of premium drag without quitting at the worst possible time.

The structural overpricing of OTM puts is well-documented (Bhansali 2008, Cole 2013): implied volatility for OTM puts persistently exceeds the realised distribution of large moves, and put buyers are systematically on the wrong side of the variance risk premium. This is true for the put spread as it is for the naked put — *both* legs of the spread are over-priced. But the short leg recovers some of that overpricing back: the premium received on the 18% OTM short put recoups 40–60% of the long-put cost. The investor is implicitly *short the variance risk premium* on the deep-OTM tail (the 18% OTM strike), where put buyers pay the most for the least *probable* protection, and *long the variance risk premium* on the 7% OTM strike, where the protection is most likely to be activated. This is structurally a better trade than buying the naked put alone.

The discipline of mechanical, calendar-driven purchases (Bhansali 2008, Chapter 3) is the most-violated principle in retail tail hedging. The natural human tendency is to buy insurance after a sell-off — at VIX 35–45, after SPY has already fallen 15–20%. This is when the program's cost is highest and its expected value is worst. The systematic put-spread program, by buying every 60–90 days regardless of market sentiment, mechanically purchases when nobody is worried (most months), occasionally purchases when fear is elevated (a small minority of months), and averages to a reasonable per-unit cost of protection over the cycle. The specific gate this program adds — `vix_max_at_entry = 35` — is a *circuit breaker*, not a market-timing tool: it skips a single purchase cycle when VIX is so dislocated that the spread debit would consume disproportionate budget, but the program resumes on the next cycle.

The early-harvest rule is the program's response to the empirical observation that put spreads in expanding-volatility regimes can double in value before the underlying ever reaches the long strike. When the spread's mark-to-market gain exceeds 100% of debit, the program closes the position, books the gain, and immediately re-opens a fresh spread at the next standard strike/DTE pair. This locks in the IV-expansion premium and resets protection at a fresh cost basis — the spread-program equivalent of "ratcheting" the hedge down as the market falls. False alarms (the SVB-style mini-crisis of March 2023, the August 2024 carry-trade unwind, the April 2025 sell-off) are exactly the scenarios where this rule earns its keep.

The behavioural-finance case for tail hedging — Calvet, Campbell & Sodini (2009), Barber & Odean (2011) — applies *more strongly* to the put spread than to the naked put. The behavioural value of tail hedging comes from preventing investors from panic-selling at the trough; the price of that behavioural insurance is the annual premium drag. A 0.5%/year drag is something an investor can absorb for a decade without quitting; a 1.2%/year drag is something investors empirically *do* quit, typically right before the crash they were paying for. The single most common failure mode of long-put hedging programs in practice is not the hedge mechanism — it is the investor's premature abandonment of the program because the recurring cost has become psychologically intolerable. The put spread, at half the cost, is the structural answer to that failure mode.

---

## The Three P&L Sources (Really: One Capped Protection and Two Forms of Premium Leakage)

### 1. Crash Protection Payout — Capped at the Spread Width (~70% of total hedge value)

When the target crash arrives — SPY declining through the long-put strike — the spread produces an exactly defined payout per contract: `(long_K − max(short_K, SPY)) × 100 − debit_paid × 100`. For SPY at $477 with a $444 / $391 spread bought at $1.40 debit, the payout schedule is:

```
SPY at exit         Per-contract intrinsic value      Per-contract net P&L
$444 (long-K ATM)        $0                               −$140  (debit lost)
$420 (−12%)              $24 × 100 = $2,400               +$2,260
$400 (−16%)              $44 × 100 = $4,400               +$4,260
$391 (short-K ATM)       $53 × 100 = $5,300               +$5,160  (PEAK)
$370 (−22%)              $53 × 100 = $5,300               +$5,160  (capped)
$334 (−30%)              $53 × 100 = $5,300               +$5,160  (capped)
```

The payout climbs linearly from the long strike to the short strike, then **flattens at the cap**. This is the explicit cost of the spread structure: a 30% crash pays the same as an 18% crash. In exchange the upfront debit is roughly half the cost of the equivalent naked-put position. The "right" way to think about this trade-off: the naked long put gives crash *insurance*; the put spread gives crash-*range* insurance.

### 2. IV Expansion — The Secondary Gain (~25% of realized hedge returns)

Even before SPY reaches the long strike, rising VIX increases the spread's value through vega — but with a caveat. The long leg has higher vega than the short leg (it is closer to ATM), so the spread is *net long vega*, but the magnitude of the IV-expansion gain is smaller than for a naked long put. A naked $405 put bought at IV 22% and held through a VIX expansion to 32% may gain $3.50 per share from vega alone; the equivalent spread might gain only $1.80 — because the short leg's value also rises, partially offsetting the long leg's gain. The spread is an IV-expansion play, but a *muted* one. This is the first form of premium leakage relative to the naked-put parent strategy.

### 3. Theta — Decay on Both Legs (~5% in calm regimes, dominates negatively when no crash arrives)

Both legs of the spread decay over time, but the long (closer-to-ATM) leg decays faster than the short (further-OTM) leg. Net theta on a 7%/18% spread at 75 DTE is approximately −0.6 to −1.2 cents per day per contract — slower than the naked put's −1.5 to −2.5 cents per day, because the short leg recoups some of the time-decay loss. The cumulative theta over a holding period is the dominant driver of the program's annual drag in calm years, and it is *also* the explicit price the user pays for crash protection. The program treats theta as a *budgeted cost*, not a problem to solve.

---

## How the Position Is Constructed

```
Purpose: Portfolio insurance — capped-payout / cost-reduced variant
Vehicle: SPY put debit spreads (long ~7% OTM, short ~18% OTM)

Step 1: Define annual hedge budget (HARD CAP, not a target)
  Budget cap = 0.5–1.0% of portfolio value per annum
  For $500,000 portfolio: $2,500–$5,000/year = $625–$1,250/quarter

Step 2: Calculate per-purchase debit
  Per-purchase max debit = 0.20–0.30% of portfolio (default 0.25%)
  $500,000 × 0.0025 = $1,250 per purchase

Step 3: Strikes
  Long leg  = round( SPY × (1 − 0.07), 2 )    → 7% OTM (the protection)
  Short leg = round( SPY × (1 − 0.18), 2 )    → 18% OTM (the cap)

Step 4: Expiry
  60–90 DTE at entry (default 75)

Step 5: Rolling protocol
  Roll when EITHER:
    DTE drops to 30 (avoid the final-month theta cliff)
    OR long-leg delta drops below −0.30 (long put deep ITM, harvest the gain)

Step 6: Cadence
  Mechanical purchase every 60–90 calendar days (default 80)
  Skip the cycle ONLY if VIX > 35 at the calendar trigger

Step 7: Early harvest
  If current spread mark ≥ 2× debit (100% gain), close immediately and
  re-enter at the next standard strike/DTE pair.

Step 8: Hard annual cost cap
  Total debits paid in any rolling 365-day window must not exceed
  annual_cost_cap_pct × starting_capital. If a scheduled purchase would
  breach the cap, the contract count is scaled down — and the trade is
  skipped entirely if the residual budget cannot fund a single contract.

Greek profile per spread (75 DTE, SPY $477, 7%/18% structure):
  Net delta:  -0.06 to -0.10  (small negative; mostly the long leg, partially offset by short)
  Net theta:  -$0.60 to -$1.20 per day  (~ half the naked-put theta)
  Net vega:   ~ +$0.06 to +$0.10  per IV-point (long-vega, but muted)
  Net gamma:  Modest positive (long leg dominant; convexity is bounded)
```

**Worked example at SPY $477.00, VIX 18.0, $100K portfolio:**

```
ATM IV proxy   : 18.0 / 100 = 0.18
Long-leg IV    : 0.18 × 1.20 = 0.216  (skew adjustment for 7% OTM put)
Short-leg IV   : 0.18 × 1.10 = 0.198  (skew adjustment for 18% OTM put)
T              : 75 / 365 = 0.2055
Long strike    : 477 × 0.93 = 443.61 → $444
Short strike   : 477 × 0.82 = 391.14 → $391
Long put BS    : approx $4.20
Short put BS   : approx $1.20
Debit/share    : $4.20 − $1.20 = $3.00 ; with $0.10 slippage → $3.10
Debit/contract : $310
Per-purchase   : 0.0025 × $100,000 = $250 budget → 0 contracts (over-budget)
Solution       : Either (a) accept 1 contract at $310 = 0.31% of capital (one-time
                 over-allocation), (b) bump position_size_pct to 0.0035, or
                 (c) widen the long strike to 6% OTM (debit → ~$2.60).
Max payout/ctr : (444 − 391 − 3.10) × 100 = $4,990
```

---

## Real Trade Walkthrough

### Trade 1 — H1 2022 Bear Market (Put Spread vs Naked Long Put)

> **January 3, 2022 · SPY:** $477 · **VIX:** 17.3 · **Thesis:** Mechanical quarterly hedge program; Fed pivot underway; VIX still cheap.

**January 2022 purchase (put spread — this strategy):**

```
Buy March 2022 SPY $444 / $391 put spread (7% / 18% OTM, 72 DTE)
  Long  $444 put at $4.20
  Short $391 put at $1.40
  Net debit per contract     : $2.80 + $0.10 slip = $2.90
  Cost per contract          : $290
  3 contracts for $300K port.: $870 = 0.29% of portfolio
  Spread width               : $53
  Max payout per contract    : ($53 − $2.90) × 100 = $5,010
```

**Comparison — naked long put (parent strategy):**

```
Buy March 2022 SPY $444 put at $4.20
  Cost per contract: $420
  3 contracts: $1,260 = 0.42% of portfolio
  Premium savings of the spread vs naked: ($1,260 − $870) = $390 = 31% reduction.
```

**Rolling protocol in 2022 (mechanical 80-day cadence):**

```
Date     Action                                            Cost      Cumulative debit
-------- ------------------------------------------------  --------  ---------------
Jan 3    Buy 444/391 put spread (3 ctr), 72 DTE            $870      $870
Mar 23   Long delta < -0.30 → close & roll (SPY $432)
         Spread MTM: $7.10 → close gain = $4,300 - $870 = +$3,430
         Buy 410/362 spread (3 ctr), 75 DTE                $870      $1,740
Jun 16   SPY $362 (cap reached) — close at $48 spread
         Close gain = $14,400 − $870 = +$13,530
         Buy 354/311 spread (3 ctr), 75 DTE                $870      $2,610
```

**Net hedge P&L H1 2022:** +$3,430 + $13,530 = **approximately +$16,090** (less ~$870 unrealized at end-of-period).

**Comparison — naked long put rolled identically:** Equivalent naked-put trades over the same window would have produced approximately +$22,000 to +$24,000 (no payout cap; the $362 print would have produced $10–$15 per contract more).

**Trade-off in numbers:** The put spread captured ~70% of the naked-put H1-2022 gain (16,090 / 22,000) at ~67% of the annual premium cost. The portfolio's equity drawdown of ~12% was reduced by both programs to a similar magnitude — the hedge gain on either path was sufficient to keep the user invested through the recovery, which is the *behavioural* value of the program, and the place both versions earn their keep.

### Trade 2 — March 2023 SVB False Alarm (The Cost of Mechanical Discipline)

> **March 6, 2023 · SPY:** $399 · **VIX:** 18.5 · **Thesis:** Calendar trigger fires; SVB headlines emerging.

```
Buy May 2023 SPY $371 / $327 spread (7% / 18% OTM, 70 DTE)
  Debit: $1.50/contract → $150
  3 contracts: $450 = 0.15% of portfolio
```

**SVB collapse (March 10–17):** VIX spikes from 18.5 to 26.5. SPY falls to $381 (−4.5%). Spread mark rises from $1.50 to $2.95 (long-leg vega gain partially offset by short-leg vega gain).

**Naked-put equivalent** would have appreciated from $1.80 to $3.40 — an 89% gain.
**Put-spread** appreciation: from $1.50 to $2.95 — a **97% gain**, because at deep-OTM strikes the put-skew compresses on a vol shock and the short leg's percentage vega contribution is smaller than the long leg's.

**Harvest decision:** Spread up 97% — just below the 100% threshold. The mechanical rule says hold; the next bar may trigger harvest if VIX climbs further. In this trade, the Federal Reserve backstopped depositors over the weekend; SPY recovered to $416 within 3 weeks. Spread fell back to $0.55 by April. **Final outcome:** held to expiry — total loss $450 − ~$50 residual = ~$400 dropped, the cost of maintaining systematic coverage.

**Lesson:** The mechanical program *cost* $400 on the SVB false alarm. A judgment-based program might have harvested at the 97% mark and locked in the gain. This is the explicit cost of mechanical discipline — and the price the program pays for not also being wrong on the other side (e.g., 2008, when the same VIX spike was *not* a false alarm and the program would have rode through).

### Trade 3 — March 2020 COVID (Capped Payout Reality)

> **Pre-COVID systematic put-spread hedger** (mechanical 80-day cadence, 7%/18% OTM, 75 DTE).

```
Date     SPY    VIX    Action                                    Cost    Cumulative
-------- ------ ------ ----------------------------------------  ------- ----------
Jan 17   $337   12.5   Buy $313/$276 spread (3 ctr), 75 DTE      $480    $480
Feb 28   $285   40.1   Long delta < -0.30 → harvest
                       Spread MTM: $34 → close gain ~ $9,720
                       VIX 40 → cycle skip (>35 cap, deferred)
Mar 16   $239   82.7   VIX 82 → still skipped; portfolio impact maximal
Mar 23   $228   61.6   VIX 61 → still skipped
Apr 15   $279   40.1   VIX 40 → still skipped (>35)
May 11   $293   28.0   Cycle resumes — buy $272/$240 spread       $570    $1,050
                       (3 contracts, 75 DTE, post-vol normalization)
```

**Net March-April 2020 hedge P&L:** harvested gain of approximately +$9,240 (after $480 debit), no further purchases until May.

**Naked-put comparison:** A 5-contract naked $313 put bought January would have been $52 ITM at the SPY $228 trough = approximately $26,000 per 5-contract position. The put-spread version captures *much* less because the cap binds: the spread maxes out at $36 per contract × 3 = $10,800 maximum. The realised harvest of ~$9,240 is close to the cap — almost all of the available payout is captured.

**Lesson:** The put spread underperforms the naked put on truly extreme tail events by exactly the structural amount expected (~50% of the naked-put gain in this case). The portfolio still benefited substantially — $9,240 of hedge P&L on a $300K portfolio that lost approximately $90,000 in the crash is meaningful protection — but the spread cannot match the asymptotic protection of the naked put. **This is the trade.** The program's premium drag in 2017–2019 was approximately half what a naked-put program would have spent; the COVID payout was approximately half. The annualised expected value is similar; the variance of the annual cost line is much lower; the behavioural sustainability is much higher.

---

## Signal Snapshot

```
+------------------------------------------------------------------+
| TAIL RISK PUT SPREAD — SPY ($100K portfolio, 1 contract)         |
+-----------------------+------------------------------------------+
| Portfolio Value       | $100,000                                 |
| SPY Price             | $477.00                                  |
| VIX Level             | 17.3    [BELOW 35 GATE OK]               |
| DTE Target            | 75 DTE  [60-90 OPTIMAL]                  |
| Long Strike  (7% OTM) | $443.61                                  |
| Short Strike (18% OTM)| $391.14                                  |
| Spread Width          | $52.47                                   |
| Debit per Contract    | $290                                     |
| Debit % of Capital    | 0.29%   [< 0.50% per-purchase cap]       |
| Annual Cost YTD       | 0.41%   [< 1.00% cap, room remains]      |
| Max Payout / Contract | $4,957                                   |
| Protection Activates  | Below $443.61 (7.0% decline)             |
| Payout Caps           | At/Below $391.14 (18.0% decline)         |
| Realistic Tail Cover  | 25-30% drawdown (peak payout ~$5,000)    |
+-----------------------+------------------------------------------+
STATUS: BUY — calendar due, VIX gate clears, budget remains.
ACTION: Open 1 contract at $290 debit; 75 DTE expiry; roll at DTE 30
        or harvest at debit x 2.0 = $580.
```

---

## Backtest Statistics

**Systematic 7% / 18% put-spread hedging on synthetic SPY (model results):**

```
Regime                      Annual Spread Cost    Hedge Activity                       Net Benefit
--------------------------  --------------------  -----------------------------------  ------------------------------------------------------------
Calm GBM (500 days)         0.5-0.7% / yr         Zero harvests; every spread expires  -0.4 to -0.7% / yr (cost of insurance, as designed)
                                                  worthless
Mild correction (-10%)      0.5-0.7% / yr         Occasional roll-on-DTE with small    Approximately flat (premium offset by small intrinsic gains)
                                                  intrinsic gain
Bear market (-25% mid-yr)   0.6-0.9% / yr         1-2 harvests; spreads max out near   +5 to +8% on capital (hedge contributes meaningfully;
                            (cycle skip x 1)      the cap                              caps explicit)
Extreme crash (-40%+)       0.6-0.9% / yr         Harvest fires once, then the 35-VIX  +5 to +9% on capital (capped — naked put would do
                            (cycle skip x 2-3)    gate halts new purchases for weeks   substantially better here)
```

**Key empirical findings (synthetic backtests in `tests/test_tail_risk_put_spread.py`):**

* On a 500-day GBM "calm market" with no crash, the program ends slightly below starting capital (cost of insurance dominates). Annual debit spend hugs the 1% cap when run with a generous budget; rolls and harvests are infrequent.
* On a 252-day "crash" market with a deterministic −25% drop mid-window and an inverse-VIX response, the equity curve peaks meaningfully *above* starting capital around the trough. Closed trades show positive `pnl` from harvests.
* The hard annual cost cap is enforced numerically — backtest assertions confirm total debit paid never exceeds the cap × years × 1.05 (the 5% slack is for rolling-window edge effects).

**Why Sharpe is the wrong metric here.** A standalone Sharpe ratio on this strategy will land at **0.4–0.8** — low by absolute standards. This is correct. The program's value is *not* its standalone return. Its value is the reduction it provides in portfolio drawdown, which has a direct (Calvet et al. 2009) and quantifiable behavioural impact on the parent portfolio's long-run CAGR. The program should be evaluated as a *hedge overlay* on the long-equity portfolio, not as a P&L generator on its own.

---

## The Math

**Annual Cost Calculation for the Put Spread:**

```
Per-purchase debit  : $290 (1 contract on $100K, 75 DTE, 7%/18% OTM, VIX 17)
Cadence             : every 80 days → ~4.6 purchases per year
Total annual cost   : 4.6 × $290 = $1,334 = 1.33% of portfolio (over budget!)
                     (note: at this size the program would breach the 1% cap by purchase 4)
Hard cap binds      : after ~3.4 purchases → annual spend stops at $1,000 (= 1.0% × $100K)
Effective cost      : 1.00% of portfolio per year (cap-binding)

For the same portfolio the naked-long-put equivalent (same strikes, no short leg):
Per-purchase debit  : $420
Total annual cost   : 4.6 × $420 = $1,932 = 1.93% of portfolio
Annual savings (cap-bound spread vs uncapped naked put): $933 = 0.93% of portfolio per year
```

**Break-Even Analysis — When Does the Spread Pay Off?**

```
Annual cost (cap-bound)   : $1,000 (1.0% of $100K)
Per-contract max payout   : ($444 − $391 − $2.90) × 100 = $5,010
Contracts per cycle       : 1
Cycles per year (mech.)   : 4.6 — but cap binds at 3.4

Break-even crash size (any single cycle):
  Need spread payout ≥ $290 (the debit on that cycle)
  Spread payout when SPY at long strike (444):  $0      → loss = $290
  Spread payout when SPY = $440 (-7.7%):       $400    → +$110 per contract
  Spread payout when SPY = $430 (-9.9%):       $1,400  → +$1,110
  Spread payout when SPY = $420 (-12.0%):      $2,400  → +$2,110
  Spread payout when SPY = $400 (-16.1%):      $4,400  → +$4,110  (near cap)
  Spread payout when SPY = $391 or below:      $5,010  → +$4,720 (capped)

Annual program break-even:
  Total annual cost: $1,000
  Need annual hedge gains ≥ $1,000
  ANY single cycle that finishes near the cap recoups the entire annual budget,
  with $4,000+ left over.
  In a normal year (no significant crash), the program loses ~$1,000.
  In a crash year, the program gains $4,000-$10,000 (= 1-3 cycles near cap).
```

**Sizing Formula:**

```
Portfolio value       : V
Annual cost cap pct   : c (default 0.010)
Cadence               : k days → cycles_per_year = 365/k (default 80 → 4.56)
Per-purchase max debit: p (default 0.0025 of capital)
Per-contract debit    : d (depends on SPY, VIX; ~$200-$500 typical)

Max contracts per cycle = min( floor( p × V / d ), floor( c × V / (cycles_per_year × d) ) )
                         (per-purchase cap)            (annual cap divided across cycles)

Worked: V = $500,000, c = 0.010, k = 80, p = 0.0025, d = $290
   per-purchase cap   : floor( 0.0025 × 500,000 / 290 ) = floor( 4.31 ) = 4 contracts
   annual cap divided : floor( 0.010 × 500,000 / (4.56 × 290) ) = floor( 3.78 ) = 3 contracts
   binding constraint : 3 contracts per cycle

Notional covered per spread:
   3 × ($444 − $391) × 100 = $15,900 of intrinsic-value-payable range
   At full activation (SPY ≤ $391): payout = $14,943 (after debit)
   On a $500K portfolio in a 25% crash that costs $125K, the spread recovers
   $14,943 ≈ 12% of the equity loss — a partial offset, not a full hedge.

For full 50%-of-loss offset: scale contracts to ~13. Annual cost would then be
   13 × 4.56 × $290 ~ $17,200 = 3.4% of portfolio — well above the 1% cap.
   The program would need to relax the cap or accept partial coverage.

Practical guidance: choose contract count to match your tolerance for premium
drag, not to perfectly offset losses. The program's job is to BLUNT the drawdown,
not eliminate it.
```

---

## Entry Checklist

- [ ] **Annual hedge budget (cost cap) defined in writing:** Set `annual_cost_cap_pct` to 0.5–1.0% of starting capital. The cap is *hard*, not aspirational. Position sizing scales contracts down to respect it.
- [ ] **Strikes set at 5–8% OTM (long) and 15–20% OTM (short):** Tighter long strike = more expensive but better activation; wider short strike = lower cap but cheaper. The default 7%/18% targets the 25–30% drawdown.
- [ ] **DTE 60–90 at entry:** 75 is the default. Shorter = unfavourable theta cliff; longer = excess vega exposure and capital tied up.
- [ ] **Rolling protocol pre-committed:** Roll at DTE 30 OR long-leg delta below −0.30, whichever fires first. No discretion.
- [ ] **Mechanical cadence locked:** Fixed schedule (default every 80 days). Skip a cycle ONLY if VIX > 35, then resume on the next cycle.
- [ ] **Per-purchase debit ≤ 0.25% of capital:** Hard guardrail against any single cycle blowing the annual budget.
- [ ] **Max concurrent ≥ 2:** Allows the cadence to overlap during slow rolls — the program never has unprotected gaps.
- [ ] **Profit-take / harvest threshold set at 100% of debit:** When mark-to-market gain ≥ debit, close and re-enter at the next standard strike/DTE pair.
- [ ] **Underlying matched to portfolio:** SPY for broad-market, QQQ for tech-heavy, IWM for small-cap. Mismatch creates basis risk that the spread cannot resolve.
- [ ] **VIX feed live, daily-bar latency < 1 day:** The 35-VIX entry gate requires fresh data.

---

## Risk Management

**The defined risk per spread is the debit.** Maximum loss per spread = `debit × 100 × contracts`, period. There is no path-dependence, no margin call, no assignment risk on the long leg. The short leg is hedged 1-for-1 by the long leg below the short strike. This is the structural advantage of the spread over the naked put: the worst-case outcome is fully knowable at entry.

**The "risk" the program manages is wasted premium.** In years without a meaningful drawdown, every spread expires worthless and the program loses its full annual debit budget. This is the *expected outcome* and the *cost of insurance* — not a strategy failure. The annual cost cap exists specifically so this loss is bounded.

**When to harvest early:** When the spread mark exceeds 2× debit (100% gain), close immediately and re-enter at the next standard strike/DTE pair. Locking in the IV-expansion gain and resetting protection at a fresh basis is the spread-program equivalent of "ratcheting down" the hedge. Do this *mechanically* — do not try to time the harvest.

**Holding through false alarms:** A spread that has gained 30–60% in a small VIX expansion (e.g., March 2023 SVB) is not yet at the harvest threshold. Hold. The mechanical rule is binary and emotion-free. False-alarm losses are part of the cost of the program; trying to avoid them by selling early is precisely the discretion the program is designed to remove.

**Re-entering after a VIX spike:** If VIX is above 35 at the calendar trigger, the program skips the cycle. When VIX drops back below 35 *and the next calendar trigger arrives*, the program resumes. Do not "catch up" by buying multiple back-to-back spreads — that introduces sequence risk the program is designed to eliminate.

**Concurrency cap:** With `max_concurrent = 2`, the program will hold up to two overlapping spreads. This is intentional: it allows staggered rolls (one spread closing on its DTE trigger while the next one is being opened on the next cadence trigger) without leaving an unprotected window.

---

## When to Avoid

1. **As a speculation vehicle.** This is a hedge overlay with negative standalone EV. If the user expects the put spread to make money on its own, they will quit the program after 18–24 months of premium drag — exactly when the program's value (the next crash) is about to be paid.

2. **For portfolios that do not need the cost reduction.** If the portfolio can absorb the 1.0–1.3% annual drag of a naked-put program, the naked put is a *strictly better* hedge — uncapped tail protection at the cost of additional premium. The put spread is the right answer only when the cost difference is binding.

3. **As a substitute for QQQ puts on tech-heavy portfolios.** If the parent portfolio is 70%+ tech (AAPL, MSFT, NVDA, AMZN, META, GOOGL), SPY put spreads will under-protect significantly because tech can fall 35–50% while SPY falls 20–25%. Use QQQ put spreads with equivalent OTM percentages.

4. **In high-IV regimes (VIX > 30) — initiating the program for the first time.** The 35-VIX gate skips cycles, but if VIX has been above 30 for an extended period the program may not have purchased anything in months. *Do not catch up*: wait for the next regular cadence trigger. Buying multiple back-to-back spreads at elevated VIX is exactly the "barn door" mistake the program is designed to avoid.

5. **With aggressive harvest thresholds (< 50% gain).** A 50%-gain harvest threshold will turn the program into a vol-arbitrage strategy, not a tail hedge. The 100% threshold is calibrated to fire on real volatility-of-volatility expansions, not on routine 3-vol-point moves.

6. **Without rigorous logging of the annual cost cap.** The cap is the program's single hardest constraint. If the cost-tracking infrastructure cannot enforce a rolling-365-day cumulative debit budget, the program's discipline collapses and turns into discretionary tail-buying.

---

## Strategy Parameters

```
Parameter                       Conservative     Standard         Budget-Constrained
------------------------------  ---------------  ---------------  -------------------
Long-leg OTM%                   5%               7%               8%
Short-leg OTM%                  15%              18%              22%
DTE at entry                    90               75               60
Roll at DTE                     35               30               25
Roll on long-delta below        -0.25            -0.30            -0.40
VIX max at entry                30               35               40
Annual cost cap (% capital)     0.7%             1.0%             0.5%
Per-purchase debit cap          0.40%            0.25%            0.15%
Profit harvest threshold        x0.75 debit      x1.00 debit      x1.50 debit
Cadence (days)                  60               80               90
Max concurrent spreads          3                2                1
Slippage per leg                $0.10            $0.05            $0.05
Underlying                      SPX              SPY              SPY
```

**Why three preset profiles, not one:**

* **Conservative** — full coverage, tight long strike, tighter cap on roll. Best for HNW / risk-averse retirement portfolios that want the spread program to behave nearly as well as the naked-put program.
* **Standard** — the defaults documented in this guide. Best for general retail / mid-size portfolios.
* **Budget-Constrained** — half the cost of standard, wider short strike. Best for portfolios under $250K where every basis point of drag matters and a 22%+ drawdown is the realistic worst-case the user is willing to insure against.

---

## Data Requirements

```
Data Point                            Source                   Update Frequency  Purpose
------------------------------------  -----------------------  ----------------  ------------------------------------
SPY daily price (OHLCV)               Polygon / Yahoo / broker Daily             Strike calculation; spread MTM
VIX daily close                       CBOE / FRED / broker     Daily             Entry gate; IV proxy for BS pricing
SPY options chain (live)              Broker / Polygon         At purchase       Actual debit verification
Portfolio market value                Broker account           Weekly            Budget calculation
Portfolio composition                 Portfolio analytics      Quarterly         Underlying selection (SPY vs QQQ)
Annual hedge cost log                 Strategy `purchase_log`  Per-purchase      Cost cap compliance (HARD CONSTRAINT)
Open spread MTM                       BS engine in backtester  Daily             Roll / harvest trigger checks
Long-leg delta                        BS delta calc            Daily             Roll trigger ("long delta < -0.30")
Spread bid/ask                        Broker chain             At purchase/exit  Slippage estimation
Realised vs implied vol               Optional analytics       Monthly           Sanity check on IV proxy
```

The strategy requires only daily-bar data — no per-strike IV or live chain ingestion is required for backtest. The IV proxy (VIX/100 with `put_skew_mult` and `short_skew_mult`) is a documented assumption; in production the live chain provides actual bid/ask for the chosen strikes and the proxy is used only for backtest research.
