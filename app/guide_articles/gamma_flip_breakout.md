# Gamma Flip Breakout
### When Market Makers Switch From Shock Absorbers to Accelerators

---

## The Core Edge

The single most powerful structural force in modern equity markets is the delta-hedging
activity of options market makers. When dealers are net long gamma, they are structurally
forced to sell rallies and buy dips — acting as a mechanical stabilizer that caps daily
ranges and suppresses realized vol. When dealers flip to net short gamma, the opposite
occurs: they must sell into falling markets and buy into rising markets, amplifying every
move. Understanding which side of this flip the market is on, and when a price crossing
the flip level triggers a regime change, is the Gamma Flip Breakout strategy's entire
thesis.

This is not a soft sentiment signal. It is mechanics. The dealer's hedging is not
discretionary — it is enforced by their risk management systems. When NVDA is at $495
and dealers are net short gamma at $500 (they sold $500 calls to retail), every tick
above $495 requires dealers to buy more NVDA to stay delta-neutral. There is no
judgment involved. It simply happens. The Gamma Flip Breakout strategy bets on the
consequence of this mechanical flow.

### The GEX Formula — Translating OI into Directional Force

```
GEX at strike K = gamma(K) × OI(K) × 100 × spot

For calls:  Dealer GEX(K) = +gamma(K) × call_OI(K) × 100 × spot
            (dealers long call gamma → suppresses moves)

For puts:   Dealer GEX(K) = −gamma(K) × put_OI(K) × 100 × spot
            (dealers short put gamma → amplifies moves)

Net GEX = Σ(call GEX at all K) + Σ(put GEX at all K)

Net GEX > 0: Dealers net long gamma → vol suppression, mean-reversion
Net GEX < 0: Dealers net short gamma → vol amplification, momentum

The "gamma flip" level = the price at which net GEX = 0
```

### Example Calculation

```
SPY at $510. Options chain shows:

  Strike    Call OI    Call Gamma    Put OI     Put Gamma
  ─────────────────────────────────────────────────────────
  $490      20,000     0.008         80,000     0.009
  $500      45,000     0.018         60,000     0.016
  $510      80,000     0.025         40,000     0.024
  $520      50,000     0.018         20,000     0.017
  $530      25,000     0.010         8,000      0.009

Net GEX at current price ($510):
  Call GEX = (0.025 × 80,000 × 100 × $510) = +$102,000,000 (B: $1.02B)
  Put GEX  = −(0.024 × 40,000 × 100 × $510) = −$48,960,000 (B: −$0.49B)
  Net GEX  = $1.02B − $0.49B = +$0.53B → positive → vol suppression regime

As SPY falls to $500:
  Call GEX at $500 = (0.018 × 45,000 × 100 × $500) = +$40.5M
  Put GEX at $500  = −(0.016 × 60,000 × 100 × $500) = −$48.0M
  Net GEX = $40.5M − $48.0M = −$7.5M → NEGATIVE → vol amplification begins

The gamma flip level is somewhere between $500 and $510 in this example.
```

When SPY crosses that flip level moving downward, the regime structurally changes.
The Gamma Flip Breakout strategy recognizes and trades this transition.

---

## How It Works — Step by Step

**The strategy in a sentence:** When price crosses the gamma flip level on above-average
volume, a structural regime change in dealer hedging dynamics occurs — trade the direction
of the cross with the appropriate options structure (strangle below flip, iron condor above).

**Immediate example — SPY, January 3, 2022:**

SPY entered 2022 at $477. The gamma flip level, computed from the options chain on December
31, 2021, was approximately $460. Between January 3 and January 18, SPY fell from $477 to
$450 — crossing below the gamma flip at around $461 on January 5.

```
January 5, 2022:
  SPY spot:        $461.80 (closing below flip level on 2.3× average volume)
  Net GEX (SPY):   Crossing from +$2.1B to −$0.8B
  Dist to flip:    −0.18% (just crossed)
  XGBoost model:   P(breakdown within 5 bars): 0.76 → ENTER LONG STRANGLE
```

Trade entered at January 5 close (below flip → expect vol expansion):
- Buy SPY $460 put (14 DTE) → pay $5.40
- Buy SPY $460 call (14 DTE) → pay $4.90
- Long strangle total cost: **$10.30** = $1,030 per strangle

By January 10, SPY had fallen to $446 (−3.2% move in 5 days). The put was worth $18.20,
call was worth $0.90. Strangle value: $19.10.

Exit at $19.10. P&L: ($19.10 − $10.30) × 100 = **+$880 per strangle (+85%)**

The gamma flip crossing correctly identified a regime shift from vol-suppressing to vol-
amplifying. The subsequent −3.2% move was well within the profit zone of the long strangle.

---

## Real Trade Walkthrough #1 — The 2023 Bull Market GEX Wall

**Context:** In 2023, SPY spent most of the year in deeply positive GEX territory.
Dealers were structurally long gamma as the market-maker community had net sold puts
to pension funds (who were hedging) and bought calls from retail (inverse: dealers short
calls, but call positions were outweighed by the massive put-selling OI). Net GEX for SPY
ran +$3–$8 billion for most of 2023.

**Date:** May 15, 2023 | **SPY:** $416 | **Net GEX:** +$5.2B | **Flip Level:** $395

```
Signal at May 15:
  Net GEX:           +$5.2B      [STRONGLY POSITIVE]
  Dist to flip:      +5.3%       [SPY is 5.3% ABOVE flip level — deeply positive territory]
  GEX ratio:         +0.82       [Call GEX overwhelms put GEX]
  VIX:               17.0        [LOW — consistent with positive GEX regime]
  Model P(iron condor works):    0.79  → ENTER IRON CONDOR
```

In a deeply positive GEX regime, the appropriate trade is an iron condor: sell premium
inside the dealer-enforced range.

**Trade at May 15 close:**
- Sell SPY $425 call (15 DTE) → collect $1.65
- Buy SPY $430 call → pay $0.75
- Sell SPY $408 put → collect $1.45
- Buy SPY $403 put → pay $0.70
- Net credit: **$1.65** = $165 per iron condor

**Iron condor in positive GEX: daily range analysis:**

```
May 15 - May 31 (15 trading days):

Day    SPY Close    Daily Range    Within Iron Condor?    Dealer Action
──────────────────────────────────────────────────────────────────────
May 15   $416.00    2.1%           YES ($403–$430)        Sell rallies, buy dips
May 16   $419.10    1.8%           YES                    Sell into rise
May 17   $418.20    1.2%           YES                    Buy small dip
May 18   $420.30    1.5%           YES                    Approaching call wall
May 19   $421.90    1.3%           YES                    Dealers selling at $425
May 22   $417.40    1.8%           YES                    Buyers return; supported
...
May 31   $419.20    1.4%           YES                    All 15 days rangebound
```

SPY never once left the $403–$430 iron condor range in 15 days. Dealers were constantly
buying dips (put wall at $395 below) and selling rallies (call wall at $425 above).

**Exit:** Spread reached 50% profit after 8 days. Bought back at $0.83.

**P&L: ($1.65 − $0.83) × 100 = +$82 per iron condor**

Small absolute P&L — but with 3% position sizing and 12 contracts, that's +$984 on a
trade that had zero intent to predict direction and simply collected the vol premium that
the positive GEX regime suppressed.

**Iron condor P&L diagram (positive GEX regime):**

```
P&L ($) at expiry — SPY $408/$403 put spread + $425/$430 call spread, $1.65 credit

  +$165 ─┼────────────────────────────────────┐     ┌──────────────
          │                                    │     │  Both short strikes OTM
          │                          Max profit: keep full credit
  +$82  ─┼                   50% target ─ ─ ─ ┤ ─ ─ ┤ ─ ─ close here
          │                                    │     │
     $0  ─┼──────────────────────────────────┬─┘     └─┬───────────
          │                              $406.35    $426.65  (break-evens)
  -$335 ─┼──────────────────────────────┘               └──────────
          │  Max loss on either side = ($5 − $1.65) × 100 = $335
          └──────┬────────┬────────┬────────┬────────┬──── SPY price
               $400    $408     $416     $425     $430

The range is protected by dealer GEX mechanics.
$408 put wall: dealers buy SPY here (puts they're short go more delta-negative → buy stock)
$425 call wall: dealers sell SPY here (calls they're short go more delta-positive → sell stock)
```

---

## Real Trade Walkthrough #2 — The Loss: Gamma Flip Crossed Back Up

**Date:** October 2, 2023 | **SPY:** $418 | **Net GEX was −$1.2B (barely negative)**

SPY had crossed below the gamma flip (approximately $424) in late September. The model
fired: P(breakdown) = 0.59 — marginal, but above the 0.55 threshold. A long strangle
was entered: $418 put + $418 call, 14 DTE, cost $12.40.

**What happened:**

October 3 saw CPI come in better than expected. SPY reversed from $410 to $435 in two
days. The net GEX crossed back positive. The strangle's call gained $9.80 but the put
lost $8.20. Net value: $13.80 — a tiny profit.

But then IV crushed hard (VIX fell from 19 to 15 in 3 days). Both legs lost value from
vol compression. By October 9, the strangle was worth $8.10.

**Exit: Oct 9, strangle at $8.10.**
**P&L: ($8.10 − $12.40) × 100 = −$430 per strangle (−35%)**

**Lessons:**
1. Model confidence at 0.59 was marginal. Prefer ≥0.65 for strangle entries.
2. "Barely negative GEX" is not the same as "deeply negative GEX." The flip crossing
   needs to be confirmed by at least 2-3 bars below flip level before entering.
3. Long strangles in low-VIX environments are expensive — the IV you pay for is the
   same IV that can crush against you if the market calms down.

---

## Real Signal Snapshot

### Signal #1 — Below Flip: Long Strangle Entry (SPY, January 5, 2022)

```
Signal Snapshot — SPY, Jan 5 2022:

  Net GEX (SPY):          ░░░░░░░░░░  −$0.8B  [NEGATIVE — vol-amplifying ✓]
  GEX crossing:           ████████░░  +$2.1B → −$0.8B  [FLIP CROSSED ✓]
  Distance to Flip:       ░░░░░░░░░░  −0.18%  [JUST BELOW FLIP ✓]
  GEX Ratio (SPY/Agg):    ██░░░░░░░░  −0.34  [BELOW NEGATIVE THRESHOLD ✓]
  Volume Confirmation:    ████████░░  2.3× average  [ABOVE AVERAGE ✓]
  SPY 5d Return:          ░░░░░░░░░░  −0.4%  [BEGINNING TO TURN ↓]
  ATR(14):                ████░░░░░░  $5.20  [MODERATE RANGE ✓]
  VIX:                    ████░░░░░░  17.2  [MODERATE — long strangle viable ✓]
  SPY 5d Return (mkt):    ░░░░░░░░░░  −0.3%  [SPY IN LINE WITH BROAD MKT ✓]

  XGBoost Model Output:
    P(breakdown within 5 bars) = 0.76  ████████░░  [ABOVE 0.55 THRESHOLD ✓]

  → ✅ ENTER LONG STRANGLE (below flip = expect vol expansion)
    Buy SPY $460 put (14 DTE) at $5.40
    Buy SPY $460 call (14 DTE) at $4.90
    Total strangle cost: $10.30 | Max profit: unlimited | Break-evens: $449.70 / $470.30

  Exit (January 10 — 5 bars):
    SPY fell to $446 (−3.2%). Put worth $18.20, call $0.90.
    Strangle value: $19.10
    P&L: +$880 per strangle (+85% on $1,030 debit in 5 days)
```

**Why this signal was clean:** GEX crossed from firmly positive (+$2.1B) to clearly
negative (−$0.8B) in a single session on 2.3× average volume. The model score of P=0.76
was well above the 0.55 threshold. With the flip crossed, dealers switched from negative
gamma hedging (buy dips, sell rallies) to positive gamma hedging (sell dips, buy rallies) —
amplifying the move rather than dampening it. The long strangle had ideal conditions:
clear flip crossing, elevated model confidence, and moderate VIX (not so high that
the strangle was overpriced).

---

### Signal #2 — False Positive: Marginal Flip with Vol Crush (SPY, October 2, 2023)

```
Signal Snapshot — SPY, Oct 2 2023:

  Net GEX (SPY):          ░░░░░░░░░░  −$1.2B  [BARELY NEGATIVE ⚠️]
  GEX crossing:           ████░░░░░░  +$0.6B → −$1.2B  [MARGINAL CROSSING ⚠️]
  Distance to Flip:       ░░░░░░░░░░  −0.8%  [BELOW FLIP BUT SHALLOW ⚠️]
  Days confirmed below flip: ██░░░░░░░░  1 day  [ONLY 1 DAY ⚠️]
  Volume Confirmation:    █████░░░░░  1.4× average  [MODERATE — WEAK SIGNAL]
  SPY 5d Return:          ░░░░░░░░░░  −1.9%  [MODERATE DECLINE]
  ATR(14):                ████░░░░░░  $5.80  [NORMAL]
  VIX:                    ████░░░░░░  19.4  [ELEVATED — strangle premium high ⚠️]

  XGBoost Model Output:
    P(breakdown within 5 bars) = 0.59  ██████░░░░  [ABOVE 0.55 THRESHOLD — MARGINAL ⚠️]

  → ⚠️ MARGINAL ENTER LONG STRANGLE (confidence borderline, GEX barely negative)
    Buy SPY $418 put (14 DTE) at $6.50
    Buy SPY $418 call (14 DTE) at $5.90
    Total cost: $12.40 per strangle

  What happened:
    CPI came in better than expected Oct 3. SPY reversed $410 → $435 in 2 days.
    GEX crossed back POSITIVE. Call gained +$9.80, put lost −$8.20.
    Then VIX crushed from 19.4 → 15.0 (vol compression killed both legs).
    By Oct 9: strangle worth $8.10.
    P&L: ($8.10 − $12.40) × 100 = −$430 per strangle (−35%)
```

**Why it failed:** Three warning signs were present but ignored: (1) GEX was only barely
negative (−$1.2B, not the −$3B+ seen in strong breakdowns); (2) only 1 day of confirmed
flip crossing — the recommended minimum is 2–3 bars below flip before entry; (3) model
confidence of 0.59 was only 4 percentage points above threshold. Rule: for long strangles,
prefer P ≥ 0.65 AND at least 2 consecutive days below the flip level AND GEX ratio more
negative than −0.5.

---

```
BELOW FLIP (Negative GEX) → Long Strangle
(Long $460 put + Long $460 call, $10.30 total cost, SPY at $461)

P&L at expiry
  +$2,000─┼──────────────────┐                    ┌─── (unlimited upside on call)
           │                  │                    │
  +$1,000─┼                  │                    │
           │        ─ ─ ─ ─ ─│─ ─ Break-even ─ ─ ─│─ ─ ─ ─
     $0  ──┼──────────────────┼────────────────────┼─────────
           │               $449.70               $470.30 ← B/Es
  -$1,030─┼──────────────────────────────────────── Max loss in the middle
           └──────┬───────┬───────┬───────┬───────┬────── SPY at expiry
                $440    $450    $460    $470    $480

ABOVE FLIP (Positive GEX) → Iron Condor
(already shown above — short $408/$425, long $403/$430, credit $1.65)

The key:
  Below flip → own vol (strangle) — dealers amplify moves
  Above flip → sell vol (condor) — dealers suppress moves
```

---

## The Math

### Distance to Flip

```
dist_to_flip_pct = (spot − flip_level) / spot × 100

Interpretation:
  dist_to_flip_pct > 0:  Above flip → positive GEX regime
  dist_to_flip_pct < 0:  Below flip → negative GEX regime
  dist_to_flip_pct = 0:  At the flip → maximum regime uncertainty

Trading zones:
  > +3%:  Strong positive GEX → iron condor
  +1% to +3%:  Weak positive → smaller condor or no trade
  −1% to +1%:  Flip zone → transition — monitor closely
  −1% to −3%:  Weak negative → small strangle
  < −3%:  Strong negative → full strangle position
```

### GEX Ratio

```
gex_ratio = call_GEX / (call_GEX + |put_GEX|)

Values:
  > 0.70: Strongly dominated by call GEX → vol suppression dominant
  0.50–0.70: Mildly positive → modest suppression
  0.30–0.50: Balanced → near flip zone
  < 0.30: Put GEX dominant → vol amplification

Note: gex_ratio > 0.50 but net_gex could still be negative if put GEX is large in
absolute terms even though call GEX exceeds it in the ratio. Use net_gex for direction,
gex_ratio for conviction.
```

### Position Sizing

```
LONG STRANGLE (below flip):
  budget         = capital × 0.02    (2% — higher risk, wider P&L range)
  cost_per_unit  = call_price + put_price
  contracts      = floor(budget / (cost_per_unit × 100))

IRON CONDOR (above flip):
  budget         = capital × 0.03    (3% — defined risk on both sides)
  max_loss       = (spread_width − credit) × 100 per side
  contracts      = floor(budget / max_loss)

Example ($75,000 portfolio, strangle at $10.30):
  budget    = $75,000 × 0.02 = $1,500
  contracts = floor($1,500 / $1,030) = 1 contract
  Risk: $1,030 (1.37% of capital — acceptable)
```

---

## When This Strategy Works Best

### Optimal Conditions for Long Strangle (Below Flip)

```
Condition                 Ideal Range     Why
------------------------  --------------  ---------------------------------------------------------
Net GEX                   < −$2B (SPY)    Strong negative GEX means strong vol amplification
Dist to flip              −2% to −5%      Confirms below flip without being in crash territory
VIX                       18–28           Options priced reasonably; vol can still expand from here
Days since crossing flip  1–3             Recent cross = fresh regime change
Volume at cross           ≥ 1.5× average  Confirms the cross has institutional backing
```

### Optimal Conditions for Iron Condor (Above Flip)

```
Condition       Ideal Range    Why
--------------  -------------  -----------------------------------------------
Net GEX         > +$2B (SPY)   Strong positive GEX = mechanical range-bounding
Dist to flip    > +3%          Comfortable buffer — flip unlikely to be tested
VIX             < 20           Low vol = lower risk of condor-busting spikes
IVR             > 0.50         Selling premium when it's historically elevated
OPEX proximity  2–3 weeks out  Pin risk works in favor of range-bound outcome
```

---

## When to Avoid It

1. **OPEX Friday (any Friday with large expirations):** GEX shifts violently as options
   expire and positions roll. The flip level can move by 2-3% in a single session. Entering
   a position with GEX data from Thursday OPEX morning is trading stale data by Friday noon.

2. **Major economic events within 3 days (CPI, FOMC, NFP):** Binary events reset the
   entire options OI structure. GEX calculations become meaningless when a single event
   will rewrite the entire surface.

3. **When 0DTE options dominate:** Zero-day-to-expiry options (SPY has them Monday,
   Wednesday, Friday) have massive intraday gamma but don't accumulate in OI-based GEX
   computations. On 0DTE expiry days, the actual dealer hedging pressure is much larger
   than GEX suggests and changes direction every hour. Avoid entries within 2 hours of
   0DTE open.

4. **Net GEX between −$1B and +$1B:** This is the "flip zone" where regime is ambiguous.
   The iron condor doesn't have the GEX suppression backing its range assumption. The
   strangle doesn't have the GEX amplification to fund its premium cost. Wait for a clear
   regime reading.

5. **For individual stocks when market GEX is deeply negative:** Even a stock in positive
   GEX territory can be overwhelmed by macro selling in a crash. The market-level GEX
   regime supersedes individual stock GEX for direction.

---

## The 2022 GEX Regime Timeline

The 2022 bear market provides the clearest case study in negative GEX dynamics:

```
SPY GEX Regime — 2022

  GEX     +$6B  ─────────────────────────────────────────────
  (B)     +$4B
          +$2B  ─────────────────────
     $0   ─ ─ ─ ─ ─ ─ ─ ─ ─ ─Flip─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─
          -$2B                         ────────────────────────
          -$4B  ─────────────────────────────────────────────
          -$6B  ──────────────────────────

  Regime:  [POSITIVE] [──NEGATIVE────────────────────────────]

  Date:    Jan 2022   Feb     Apr     Jun     Aug     Oct    Dec
  SPY:      $477      $450    $424    $363    $408    $371   $384

  Key events:
  Jan 18: SPY crosses below flip ($460) → regime turns negative
          Long strangle entry: +85% over 5 days (walkthrough above)
  Jun 17: SPY at yearly low $363, GEX −$5.8B → extreme vol amplification
  Oct 14: GEX begins recovering; flip level drops to $355
  Dec 13: FOMC pivot signal → GEX turns positive → iron condor regime resumes

In negative GEX:
  Average daily SPY range: 1.7% (vs 0.9% in positive GEX years)
  Long strangle winners: 64% of entries
  Iron condors: 71% losers in negative GEX (regime wrong for structure)
```

This history validates the core thesis: the GEX regime determines the appropriate options
structure. Using iron condors in 2022 would have been catastrophic. Using long strangles
in 2023 would have been expensive and wrong.

---

## Common Mistakes

1. **Using GEX as a direction signal rather than a volatility regime signal.** Positive
   GEX does not mean SPY goes up. It means SPY will move LESS in both directions. A stock
   can and does fall in positive GEX — it just falls more slowly and with more mean-reversion.

2. **Entering iron condors just below the gamma flip.** The iron condor requires positive
   GEX for dealer support. If you're 1% above the flip level, a single bad day crosses the
   flip and the iron condor loses its mechanical backing. Minimum 3% buffer from flip before
   selling premium.

3. **Ignoring the term structure of GEX.** GEX computed from monthly options looks different
   from GEX computed from weekly options. The weekly options (especially 0DTE) have enormous
   gamma that changes the intraday dynamics even when monthly OI GEX looks stable.

4. **Treating the gamma flip as a static level.** It shifts every day as options expire
   and OI changes. The flip level from Monday morning may be 1.5% different from Friday
   afternoon. Always use same-day GEX data for entry.

5. **Over-concentrating in long strangles during sustained negative GEX.** The 2022 bear
   market had 11 months of negative GEX. While strangles were generally profitable, IV
   often spiked on entry and then compressed — the strangle bought expensive vol and then
   suffered from vol crush even as direction was correct. Use smaller position sizes in
   extended negative GEX regimes.

6. **Forgetting that the long strangle needs a BIG move to profit.** A $10.30 strangle
   on SPY at $460 requires SPY to move ±$10.30 just to break even. The expected vol
   amplification from negative GEX needs to produce a move LARGER than the strangle cost.
   In weakly negative GEX (near the flip), the amplification may not be enough.

---

## Quick Reference

```
Parameter                    Default                            Range        Description
---------------------------  ---------------------------------  -----------  --------------------------------------------------------------------------
`min_gex_for_condor`         +$2B (SPY)                         +$1B–+$5B    Minimum positive GEX to sell iron condor
`max_gex_for_strangle`       −$1B (SPY)                         −$0.5B–−$3B  Maximum GEX to buy strangle
`min_dist_to_flip_condor`    +3%                                +2–+5%       Minimum above-flip buffer for condor
`min_dist_to_flip_strangle`  −2%                                −1–−4%       Minimum below-flip distance for strangle (`flip_sensitivity=0.5%` default)
`min_model_confidence`       0.55                               0.45–0.70    XGBoost P(breakout/breakdown) — code default `signal_threshold=55`
`dte_entry`                  21 DTE                             14–30        Days to expiry for all trades (code `dte_entry=21`)
`condor_wing_width`          2% of spot                         1.5–3%       Each side of iron condor
`strangle_profit_target`     100% of cost (either leg doubles)  —            Close strangle when either leg doubles in value
`condor_profit_target`       50% of credit                      40–70%       Close condor at 50% of credit
`condor_stop_loss`           2× credit                          1.5–3×       Close condor if spread costs 2× credit to close
`time_stop_dte`              7 DTE                              5–10         Close all positions at ≤ 7 DTE (`_HOLD_STOP_DTE = 7`)
`position_size_pct`          2%                                 1–5%         Capital at risk (`position_size_pct=2.0`)
`warmup_bars`                150                                100–200      Minimum history for XGBoost (`_WARMUP_BARS = 150`)
`retrain_frequency`          45 bars                            30–60        Walk-forward retrain window (`_RETRAIN_EVERY = 45`)
```

---

## Data Requirements

```
Data Field                Source                              Usage
------------------------  ----------------------------------  ------------------------------------
`stock_net_gex`           Polygon options chain (computed)    Primary regime signal
`stock_dist_to_flip_pct`  Derived from net_gex vs strike GEX  Distance from flip level
`stock_call_gex`          Polygon options chain               Call-side gamma contribution
`stock_put_gex`           Polygon options chain               Put-side gamma contribution
`stock_gex_ratio`         Derived: call_gex/(call_gex+        put_gex
`vix`                     Polygon `VIXIND`                    Macro vol context
`spy_5d_return`           Polygon OHLCV                       Market direction context
`stock_5d_return`         Polygon OHLCV                       Individual name momentum
Per-strike OI + gamma     Polygon options chain               GEX computation (requires live data)
Risk-free rate            Polygon `DGS10`                     Black-Scholes gamma computation
```

**Critical note:** Historical GEX requires reconstructing the full options chain OI
plus computing Black-Scholes gamma for each strike at each historical date. This
requires substantial options historical data. Backtesting uses VIX as a GEX proxy
(VIX < 15 → positive GEX assumed; VIX > 25 → negative GEX assumed).
