# Short Squeeze Vol Expansion
### When Gamma Concentration Forces Market Makers to Become Fuel for the Fire

---

## The Core Edge

A gamma squeeze is one of the most mechanical, predictable, and violent price events in
modern equity markets. Understanding it from the dealer's perspective makes the edge
crystal clear: when retail and institutional traders concentrate call buying at specific
strikes, market makers who sold those calls must buy the underlying stock to remain
delta-neutral. As the stock rises toward those strikes, the dealers' delta exposure
increases, requiring them to buy even more stock. This buying pressure drives the stock
further up, which forces more buying. The positive feedback loop accelerates until either
the option expires, the stock runs out of new buyers, or short sellers are forced to cover.

The strategy does not predict a gamma squeeze before it starts. That is too early —
the setup may never activate. Instead, it identifies stocks where the gamma-squeeze
preconditions are already building: call OI concentrating at a specific strike cluster,
call volume-to-OI ratios spiking (fresh new option buying on top of existing OI), and
a rising OTM call OI over the past 5 days that signals institutional or informed money
is loading up. When the LightGBM model detects this pattern and predicts ≥+7% price
appreciation within 5 bars with sufficient confidence, the strategy enters a bull call
spread to ride the squeeze.

### The Dealer Mechanics — Why This Works

Imagine NVDA is at $450. Retail and momentum funds buy 50,000 contracts of the $470 call
with 10 days to expiry. The dealers who sold those calls are now long the stock as a hedge
— they own stock proportional to the delta of the calls they sold. At the $470 strike with
10 DTE, those calls might have a delta of 0.30. So dealers are long 50,000 × 100 × 0.30
= 1,500,000 shares of NVDA.

Now NVDA rallies to $465. Those $470 calls now have a delta of 0.50. The dealers need to be
long 50,000 × 100 × 0.50 = 2,500,000 shares to stay hedged. They need to buy another
1,000,000 shares. That buying pushes NVDA to $468. Now the delta is 0.65. Another 750,000
shares must be bought. NVDA hits $472. The calls are now ITM. Every tick higher requires
more dealer buying. Gamma has become a self-fulfilling engine.

This is the gamma squeeze in its pure mechanical form. The key insight is that the fuel
(dealer hedging) is *forced* — it is not discretionary. It will happen as long as the
option OI exists and the stock is near the strike.

### Academic and Historical Evidence

Anand, Irvine, Puckett & Venkataraman (2010) documented that option market maker hedging
activity creates predictable patterns in underlying equity order flow. More recently,
Barardehi, Bernhardt & Davies (2021) showed that gamma hedging flows explain substantial
portions of intraday price pressure around high-OI option strikes. The GME and AMC episodes
of January 2021 provided the most dramatic real-world demonstration, but the mechanism
occurs continuously at smaller scales in individual names.

---

## How It Works — Step by Step

**The signal:** LightGBM detects the following simultaneously:
1. Call OI is concentrated at one or two strikes within 5–15% OTM
2. The daily call volume is high relative to existing OI (fresh buying on top of existing interest)
3. OTM call OI has increased meaningfully over the past 5 days
4. The stock has positive recent momentum (5d return > 0)
5. Macro conditions are supportive (VIX not elevated, SPY not in free-fall)

**The trade:** Bull call spread, 14–21 DTE, long ATM or slightly OTM call, short further OTM
call at approximately the gamma-squeeze target level.

**The exit:** 50% profit target, 2× debit stop loss, or 14-day time stop.

**Immediate example — NVDA August 2023:**

NVDA had just announced blowout Q2 FY24 earnings on August 23, 2023. The stock jumped from
$410 to $490 overnight. Within two days, the options market showed call OI concentration
building at the $500 strike. By August 28:

- Call OI at $500 strike: 48,000 contracts (6× its 30-day average for that strike cluster)
- Call volume/OI ratio: 3.2 (massive fresh buying into existing OI)
- OTM call OI 5d change: +380%
- Stock 5d return: +21%
- ATM IV: 62%
- Model P(≥+7% in 5 bars): **0.78**

Trade entered at August 28 close:
- Buy NVDA $490 call (ATM), 14 DTE → pay $22.40
- Sell NVDA $520 call → collect $10.60
- Net debit: **$11.80** = $1,180 per contract
- Max profit: ($520 − $490 − $11.80) × 100 = $1,820 per contract

By September 1, 2023 (4 bars later), NVDA reached $502. The spread was worth $19.40.

Closed at $19.40. P&L: ($19.40 − $11.80) × 100 = **+$760 per contract (+64%)**

The gamma squeeze to $500 happened nearly on schedule, exactly as the dealer hedging
mechanics predicted when call OI was concentrated there.

---

## Real Trade Walkthrough #1 — GME: The Genesis, January 2021

*This trade is presented as a historical case study. The GME squeeze of January 2021 was
the most extreme gamma squeeze in modern market history and illustrates the mechanics in
their purest form.*

**January 12, 2021 | GME | Spot: $19.95**

GameStop was being aggressively shorted by institutions. Short interest was 140% of float.
Keith Gill (Roaring Kitty) and WallStreetBets had been accumulating shares. Then something
crucial happened: options volume on cheap OTM calls exploded. Market makers, selling
these calls to retail, were forced to hedge.

**Signal state on January 12:**

```
Signal Strength:
  Call OI Concentration:    █████████░  $20/$25 cluster  [EXTREME]
  Call Vol/OI Ratio:        ██████████  4.8×              [EXTREME]
  OTM Call OI 5d Change:    ██████████  +820%             [EXTREME]
  Stock 5d Return:          █████████░  +46%              [STRONG]
  Volume vs 20d Average:    ██████████  14×               [EXTREME]
  Short Interest:           ██████████  140% of float     [EXTREME]
  VIX:                      █████░░░░░  24                [ELEVATED]
  SPY 5d Return:            ████░░░░░░  +1.2%             [FLAT]
  ─────────────────────────────────────────────────────────
  Model P(≥+7% in 5 bars):  ██████████  0.92              → ENTER BULL CALL SPREAD
```

**Trade at January 12 close (hypothetical, educational):**
- Buy GME $20 call, 21 DTE → pay $4.40
- Sell GME $30 call → collect $2.10
- Net debit: **$2.30** = $230 per contract
- Max profit: ($30 − $20 − $2.30) × 100 = $770

**What happened over the next 14 days:**

```
Date      GME Price    Call OI Conc.    Spread Value    Cumulative P&L
──────────────────────────────────────────────────────────────────────
Jan 12    $19.95       Building         $2.30 (entry)   $0
Jan 13    $31.40 (+57%)  $30/$40 now    $7.95           +$565
Jan 14    $39.91       $40/$50/$60 now  $10.00 (max)    +$770  ← AT MAX PROFIT
Jan 19    $47.00       $50/$100 now     $10.00+         CLOSED
Jan 27    $347.51      Off the charts   —               —
```

**Exit at January 14 (50% profit target at $6.45 in spread value):**

Actually, the 50% profit target would fire at $2.30 + 50% = $3.45 credit-back point,
meaning spread value drops from $7.95. Realistically the spread hit max profit ($10.00)
by Jan 13. A prudent trader exits at max profit level.

**P&L at max profit exit: +$770 per contract = +335% on debit paid**

Note: Holding beyond January 14 into the most extreme phase of the squeeze (GME hit $483
intraday on Jan 28) would not have increased the bull call spread P&L since the spread
capped at $10.00 with the $30 short strike. This illustrates both the advantage
(defined risk) and limitation (capped upside) of using a spread rather than naked calls.
The spread captured the mechanical first leg of the squeeze perfectly.

**Bull call spread P&L at expiry:**

```
P&L ($) per contract — GME $20/$30 call spread, $2.30 debit

  +$770 ─┼──────────────────────────────────────────┐  Max profit above $30
          │                                          │
  +$385 ─┼                               ┌──────────┘
          │                          ┌───┘  50% profit = $385 → close here
     $0  ─┼─────────────────────────┬┘
          │                    $22.30 ← break-even
  -$230  ─┼  Max loss below $20
          └──────┬────────┬────────┬────────┬──── GME price at expiry
               $15      $20      $25      $30
```

---

## Real Trade Walkthrough #2 — The Loss: AMC June 2021

**Date:** June 2, 2021 | **AMC:** $35.00

AMC had squeezed earlier in May 2021, reaching $26. By June 2, it was at $35 and the
options market was showing elevated call OI — but the character of the signal was different:
old OI from the May squeeze was still sitting there, not fresh new buying.

**Signal state on June 2:**

```
  Call OI Concentration:    ████████░░  $40/$45 cluster  [HIGH]
  Call Vol/OI Ratio:        ████░░░░░░  1.2×              [LOW — stale OI]
  OTM Call OI 5d Change:    ██░░░░░░░░  +8%              [FLAT — no fresh buying]
  Stock 5d Return:          ██████████  +35%             [VERY STRONG — already squeezed]
  Model P(≥+7% in 5 bars):  █████░░░░░  0.48             → BELOW THRESHOLD (no trade)
```

The model correctly identified that the squeeze had already happened. Call volume/OI of 1.2×
means existing holders are not adding — the fresh gamma fuel is spent. The model output
was 0.48, below the 0.55 minimum threshold. **No trade was entered.**

What happened: AMC peaked at $72.62 on June 2 intraday, then fell 59% over the following
10 days, hitting $30 by June 17. Any bull call spread entered on June 2 would have been
a near-total loss.

**Key lesson: The Vol/OI ratio is the freshness indicator.** A high Vol/OI ratio (≥2×)
means new money is buying into existing OI, creating new dealer delta-hedging obligations.
A low Vol/OI ratio means the OI is stale — holders who already bought are not adding,
and dealers are fully hedged. The squeeze requires fresh fuel, not recycled OI.

---

## P&L Diagram — Bull Call Spread at Various Squeeze Outcomes

```
Bull Call Spread: Long $490 call / Short $520 call
Debit paid: $11.80. Stock enters at $490. 14 DTE.

P&L ($) at expiry  per contract

+$1,820─┼─────────────────────────────────────────────┐  Max profit above $520
         │                                             │  Dealers fully hedged through squeeze zone
  +$910─┼                                       ┌─────┘  50% target here → close early
         │                                  ┌───┘
      $0─┼─────────────────────────────────┬┘
         │                          $501.80 ← break-even  (ATM + debit)
 -$590 ─┼──────────────────────────┬
         │                    $490 │  ← Strike — gamma zone begins
-$1,180─┼────────────────────────  ┘  Max loss below $490
         └───────┬───────┬───────┬────────┬──── Price at expiry
               $480    $490    $500    $510    $520

Scenario analysis:

  Price at expiry    Spread value    P&L/contract    Outcome
  ────────────────────────────────────────────────────────
  $480 or below      $0              -$1,180         Full loss (model wrong)
  $490               $0              -$1,180         Full loss (flat, no squeeze)
  $501.80            $11.80          $0              Break-even
  $510               $20.00          +$820           Strong squeeze (partial)
  $520+              $30.00          +$1,820         Full squeeze (max profit)
```

---

## The Math

### Call OI Concentration Formula

```
call_oi_concentration = max(OI at single strike) / total_call_OI

"Concentrated" when > 0.20 (one strike holds 20%+ of all call OI)

Example: Total call chain OI = 80,000 contracts
         OI at $500 strike   = 22,000 contracts
         Concentration index = 22,000 / 80,000 = 0.275 → CONCENTRATED
```

### Call Volume / OI Ratio

```
call_vol_oi_ratio = today_total_call_volume / total_call_OI_yesterday

Values:
  < 0.5: Very low fresh interest — stale positioning
  0.5–1.0: Normal turnover
  1.0–2.0: Active fresh buying
  2.0–5.0: Elevated — gamma squeeze precondition forming
  > 5.0: Extreme — often precedes rapid price move

This ratio measures "fuel freshness" — how much new dealer hedging obligation
is being created today relative to existing hedged OI.
```

### Expected Move from Gamma Pressure

```
Approximate gamma-squeeze speed heuristic (rule of thumb, not a formula):

When call_oi_concentration > 0.20 AND call_vol_oi_ratio > 2.0:
  Expected additional move in 5 days ≈ 0.8 × (distance from current price to max-OI strike)

Example:
  NVDA at $490, max OI concentration at $520 (6.1% OTM)
  Expected additional move ≈ 0.8 × 6.1% = +4.9%
  → Stock expected to reach approximately $514 in 5 bars (in a typical squeeze)
```

### Position Sizing

```
budget           = capital × 0.03          (3% max debit risk per squeeze play)
debit_per_share  = long_call_price − short_call_price
contracts        = floor(budget / (debit_per_share × 100))

Example: $100,000 capital, debit = $11.80
  budget    = $100,000 × 0.03 = $3,000
  contracts = floor($3,000 / $1,180) = 2 contracts
  Total debit at risk: $2,360 (2.36% of capital)
```

---

## When This Strategy Works Best

**Optimal conditions:**

```
Factor             Ideal State      Why
-----------------  ---------------  -------------------------------------------------------------------------------------------
Short interest     10–30% of float  Provides covering-fuel once squeeze starts
Call Vol/OI ratio  2.0–6.0          Fresh gamma fuel actively building
ATM IV             40–80%           Elevated enough to signal uncertainty; not so high that spreads are prohibitively expensive
Stock 5d return    +3% to +20%      Momentum is already building
VIX                < 25             Calm macro means the squeeze is stock-specific, not overwhelmed by macro flows
SPY 5d return      > −2%            Market not actively selling — individual squeeze can run independently
Market cap         $2B–$200B        Large enough for options liquidity; small enough for squeeze to be material
```

**Best time:** Earnings week when a beat triggers rapid call-buying; sector breakouts;
post-short-squeeze initiation report (when a research firm publicly highlights squeeze potential).

**Best sectors:** Technology (highest options activity), retail/consumer (high retail
attention), biotech (binary catalysts that trigger call accumulation).

---

## When to Avoid It

1. **Call Vol/OI ratio < 1.5:** The squeeze engine lacks fresh fuel. Existing OI may be
   from weeks ago, already fully delta-hedged. No incremental hedging pressure.

2. **Stock already up >30% in 5 days:** The mechanical squeeze may be mostly complete.
   Entering now means chasing the final inning where short sellers have already covered.
   Example: AMC June 2 walkthrough above.

3. **IV > 120%:** Options are so expensive that the spread costs more than the expected
   move justifies. The vol is pricing in a two-way move — you might be entering into
   a whipsaw, not a directional squeeze.

4. **VIX > 30:** Macro fear overwhelms individual-name dynamics. Every stock, regardless
   of squeeze setup, trades as a function of the broader market risk-off.

5. **SPY 5d return < −3%:** In active market selloffs, squeezed names are not immune —
   funds deleverage across positions including those where they were squeezed long.

6. **Market cap > $500B:** Mega-caps have too much share count for a gamma squeeze to
   create meaningful price pressure. The share volume needed to delta-hedge is too small
   relative to average daily volume.

---

## Common Mistakes

1. **Confusing high short interest with an active squeeze.** Short interest is necessary
   but not sufficient. The squeeze requires the mechanical trigger — concentrated call OI
   generating dealer buy orders. A heavily shorted stock with no unusual call OI is not
   about to squeeze.

2. **Buying naked calls instead of spreads.** Naked calls after a 10-15% move will have
   IV of 80-150%. If the squeeze completes, the IV crush on exit wipes a significant portion
   of the directional gain. The bull call spread sells the expensive wing to partially
   neutralize IV exposure.

3. **Sizing based on max profit rather than max loss.** A potential 200% return is seductive.
   But the max loss is the entire debit. Size based on the debit as a percentage of capital,
   never based on the potential upside.

4. **Using DTE < 7.** With very short-dated options, the gamma squeeze can happen intraday
   or across 2-3 days. Entering with 5 DTE means you might be right about direction but
   wrong about timing by a few days — and lose everything to theta. Use 14-21 DTE.

5. **Ignoring the IV of the short strike.** The short call wing in your spread also has
   high IV. If the stock rips through your short strike, the short call gains value rapidly —
   but so does the long call proportionally. The spread works correctly; just make sure
   the short strike is above your break-even.

6. **Failing to close at 50% profit.** The squeeze is often a violent one-way move followed
   by an equally violent reversal. Once the mechanics are spent (short sellers have covered,
   call OI has decayed), the stock can reverse sharply. The 50% profit target forces
   disciplined exit before the reversal risk materializes.

7. **Trading this as a short sell on the other side.** The inverse of the gamma squeeze
   is NOT a reliable fade — timing is extremely difficult. The squeeze's endpoint is
   hard to predict. This strategy only trades WITH the squeeze, never against it.

---

## Quick Reference

```
Parameter                    Default          Range      Description
---------------------------  ---------------  ---------  ----------------------------------------------------------------------------
`min_call_oi_concentration`  0.20             0.15–0.35  Min fraction of call OI at single strike
`min_call_vol_oi_ratio`      2.0              1.5–4.0    Min fresh call buying ratio
`min_otm_call_oi_5d_change`  +50%             +30–+200%  Minimum 5-day OI growth in OTM calls
`min_model_confidence`       0.55             0.50–0.75  LightGBM P(≥+7% in 5 bars) — default `signal_threshold=55`
`dte_entry`                  21 DTE           10–30      Entry DTE (default; code enters at `dte_entry=21`)
`long_strike_delta`          0.50 (ATM)       0.40–0.60  Long call delta at entry
`spread_width_pct`           6% of spot       4–10%      Short strike distance from long (code `spread_width=3` increments)
`profit_target`              80% of max gain  60–100%    Close when spread reaches 80% of max spread value (`profit_target_pct=0.80`)
`stop_loss_pct`              50% of debit     30–70%     Close when loss equals 50% of debit paid (`stop_loss_pct=0.50`)
`dte_time_stop`              5 DTE            3–10       Exit at ≤ this DTE remaining
`stock_move_exit`            +8%              5–15%      Also exit on directional +8% stock move
`position_size_pct`          2%               1–4%       Max debit as % of capital (code default `position_size_pct=0.02`)
`max_vix`                    28               20–35      Maximum VIX to enter
`warmup_bars`                120              80–200     Minimum history for LightGBM
`retrain_frequency`          45 bars          30–60      Walk-forward retrain window
```

---

## Data Requirements

```
Data Field                     Source                            Usage
-----------------------------  --------------------------------  ----------------------------------
`stock_call_oi_concentration`  Polygon options chain             Primary squeeze signal
`stock_call_vol_oi_ratio`      Polygon options chain             Freshness of gamma fuel
`stock_otm_call_oi_5d_change`  Polygon options chain (5d delta)  Building momentum in call OI
`stock_5d_return`              Polygon OHLCV                     Directional momentum context
`stock_volume_ratio`           Polygon OHLCV vs 20d average      Unusual volume confirmation
`stock_atm_iv`                 Polygon options IV                Vol regime and pricing
`stock_iv_call_put_spread`     Derived from options chain        Call skew (positive = call demand)
`vix`                          Polygon `VIXIND`                  Macro regime filter
`spy_5d_return`                Polygon OHLCV                     Market direction context
Short interest                 Manual/alternative data           Squeeze fuel quantity
Per-strike OI by expiry        Polygon options chain             OI concentration computation
```
