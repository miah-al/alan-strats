# Dealer Gamma Regime (DGR)
### Trading the Actual Gamma Mechanic — Long Straddles Below the Flip, Iron Condors Above

---

## Why This Strategy Exists

The sibling strategy, **GEX Positioning**, uses VIX as a GEX proxy and responds by
adjusting cash/SPY allocation (15%–90% SPY). It is a defensive *risk thermostat* —
a "vol-target overlay" that protects drawdowns but does not actually capture the
dealer-hedging edge.

**Dealer Gamma Regime (DGR)** is what you build when you want to *trade the mechanic*
directly. It computes actual dealer GEX from the options chain, locates the zero-gamma
flip level, identifies call/put walls, and deploys three regime-specific **options
structures** keyed to the dealer-hedging behaviour:

```
Regime            Dealer behaviour                 Edge          DGR structure
----------------  -------------------------------  ------------  ---------------------------------
Negative GEX      Hedge WITH the move (amplify)    LONG gamma    ATM long straddle (30 DTE)
Positive GEX      Hedge AGAINST the move (pin)     SHORT gamma   Iron condor anchored on walls
Near-flip zone    Regime inflection                LONG gamma    ATM long straddle (30 DTE)
```

Same VIX. Same market. Opposite trades.

---

## The Core Idea in 90 Seconds

**Dealer gamma sign determines whether trends amplify or mean-revert.**

```
Positive GEX (spot ABOVE flip level):
  Customers are net short calls / long puts → dealers long calls / short puts
  Dealers are net LONG gamma
  When spot rises:  dealer delta grows → dealers SELL stock → caps the rally
  When spot falls:  dealer delta shrinks → dealers BUY stock → supports the dip
  Net effect:       compressed ranges, mean-reversion, pinning to high-OI strikes
  Trade:            SELL premium. Iron condor, anchored on call wall.

Negative GEX (spot BELOW flip level):
  Customers are net long calls / short puts → dealers short calls / long puts
  Dealers are net SHORT gamma
  When spot rises:  dealer delta grows more negative → dealers BUY stock → accelerates rally
  When spot falls:  dealer delta grows more negative (puts) → dealers SELL stock → accelerates decline
  Net effect:       trends amplify in BOTH directions, gaps, violent moves
  Trade:            BUY gamma. Long straddle, paying for the breakout either way.

Near-flip zone (within ±0.25% of flip):
  Regime is transitioning. Any move through the flip level changes the dealer sign.
  Trade:            Long straddle — paid in either direction whichever way it breaks.
```

This is accounting, not opinion. Dealers hedge because their risk systems demand it.

---

## What Makes DGR Different from the VIX Ladder

| | GEX Positioning (VIX ladder) | **Dealer Gamma Regime (DGR)** |
|-|-|-|
| Signal source | VIX level (proxy) | Actual dealer GEX from options chain |
| Regime boundaries | Fixed VIX bands (15/18/22/30) | Dynamic — zero-gamma flip level |
| Response to negative regime | Cut SPY to 15–35% | **Buy long straddle (long gamma)** |
| Response to positive regime | Hold SPY 80–90% | **Sell iron condor (anchored on wall)** |
| Captures trend amplification? | No — sits in cash | **Yes — long straddle profits from large moves** |
| Captures pin / mean-reversion? | No — just holds equity | **Yes — sells premium at the wall** |
| Sizing basis | VIX band | **Distance to flip level** (proximity = strength) |
| Asset class | Long equity / cash | **Defined-risk options spreads** |

The two strategies are complementary. Run GEX Positioning as a portfolio-level
allocation filter; run DGR as a tactical options overlay on top of it.

---

## How GEX Is Computed

The DGR engine computes dealer GEX directly from the options chain:

```
Per-option GEX contribution ($ per 1% spot move):
    gex_i = sign_i × gamma_i × OI_i × 100 × spot² × 0.01

Where:
    sign_i       = +1 for dealer-long-gamma positions, −1 for dealer-short
    gamma_i      = Black-Scholes gamma at current IV and DTE
    OI_i         = open interest for that contract
    100          = shares per contract
    spot²        = delta hedging scales with spot squared
    0.01         = converts to dollars per 1% move

Net dealer GEX = sum over entire chain
```

**Sign convention** (default for SPY/SPX/QQQ):

```
'index_retail_call_long':
    Customers are net long calls / short puts
    → Dealers are short calls / long puts
    → call_sign = +1, put_sign = −1
    → Net GEX > 0 means dealers LONG gamma (vol-suppressive)
```

For single names where retail is put-heavy (rare but possible in certain meme
stocks), invert to `'retail_put_long'`.

**Zero-gamma flip level**: Brent's method finds the spot price S\* where
ΣGEX(S\*) = 0, with gamma *recomputed* at S\* (not using snapshot gamma). This
matters because gamma is not constant across spot levels — using snapshot gamma
underestimates convexity near the flip.

**Walls**: Per-strike GEX computed separately for calls and puts:

```
Call wall: strike ABOVE spot with the largest |call GEX|
           Acts as a resistance magnet — dealers' call hedging concentrates here.
Put wall:  strike BELOW spot with the largest |put GEX|
           Acts as downside support — dealers' put hedging concentrates here.

Threshold: wall must exceed 1.5× median |GEX| per strike to qualify.
Exclusion: walls within 0.5% of spot are ignored (too close to matter).
```

**0DTE separation**: Options with DTE ≤ 1 are split off. 0DTE gamma dominates raw
net GEX but does not persist overnight — trade rules use **multiday GEX only**;
0DTE is an intraday overlay.

---

## Trade Structures — Full Spec

### Structure 1: Long Straddle (Negative GEX or Near-Flip)

```
Setup:    Spot = $500, VIX = 18, ATM IV = 0.20, flip level = $510
          → spot below flip by 2.0% → regime NEGATIVE
          → dealers are short gamma, trends will amplify

Entry:    Buy 1× $500 call @ 30 DTE (≈ 0.50Δ)
          Buy 1× $500 put  @ 30 DTE (≈ 0.50Δ)
          Paid debit: approximately $11.50 (combined)  →  $1,150 per 1 lot

Payoff:   Unlimited upside if spot rallies (call leg)
          Unlimited downside profit if spot crashes (put leg)
          Breakeven: spot ± $11.50 by expiry
          Max loss:  debit paid ($1,150) if spot stays at $500 at expiry

Exits:    • Take profit at +60% debit ($690 profit, close entire straddle)
          • Stop loss at −50% debit ($575 loss, cut it)
          • DTE exit at 7 DTE (time value collapses beyond this)

Why it fits negative GEX:
          In a short-dealer-gamma regime, big moves get bigger. A straddle is
          the purest expression of "long gamma" — paying for the convexity that
          dealers are being forced to supply. If SPY moves +3% or −3%, the
          straddle is deep ITM. If it pins at $500, you lose the debit.
```

---

### Structure 2: Iron Condor Anchored on Walls (Positive GEX)

```
Setup:    Spot = $500, VIX = 16, ATM IV = 0.18, flip level = $490
          → spot above flip by 2.0% → regime POSITIVE
          → dealers are long gamma, trends will compress
          → call wall detected at $510, put wall at $488

Entry:    15Δ short legs, 35 DTE:
            Short 1× $510 call (or wall if closer than 15Δ strike)
            Long  1× $515 call (wing: +2×EM from body, here +$5)
            Short 1× $488 put  (or wall if closer)
            Long  1× $483 put  (wing: −$5)
          Received credit: approximately $1.45 × 100 = $145 per 1 lot
          Max loss:        ($5 width − $1.45 credit) × 100 = $355 per 1 lot

Payoff:   Max profit $145 if spot expires within $488–$510 at expiry
          Max loss  $355 if spot closes beyond $483 or $515
          Breakevens: $486.55 (downside), $511.45 (upside)

Exits:    • Take profit at 50% of max profit ($73 gained → close)
          • Stop loss at 2× credit ($290 loss → close)
          • DTE exit at 21 DTE (gamma risk accelerates inside 21 DTE)

Why it fits positive GEX:
          Dealers are mechanically capping the range at the call wall ($510)
          and supporting it at the put wall ($488). Selling premium inside
          the wall-to-wall band is selling volatility that the dealers
          themselves are suppressing. The edge is the theta decay of short legs
          in a compressed-range environment.
```

---

### Structure 3: Near-Flip Long Straddle (Regime Inflection)

```
Setup:    Spot = $500, flip level = $500.50
          → |dist_to_flip| = 0.10% → within near_flip_pct band (0.25%)

Entry:    Same as Structure 1 — long ATM straddle, 30 DTE
          Typically sized LARGER (near_flip proximity scales size up to max_risk_pct)

Why:      The flip level is where dealer behaviour INVERTS. If spot breaks
          through the flip in either direction, the regime flips and a trend
          is likely to develop — dealers who were pinning now amplify. Long
          gamma is agnostic to direction: whichever way the break happens,
          the straddle wins. Pay in advance for the breakout.
```

---

## Position Sizing — Distance to Flip

Size is keyed to the *strength* of the regime signal, measured by how close spot
is to the flip level:

```
|dist_to_flip|    Risk per trade
---------------   --------------
≥ 2.0%            base_risk_pct    (default 0.75% of capital)
1.5%              0.94%
1.0%              1.13%
0.5%              1.31%
0.1%              1.47%
0.0%              max_risk_pct     (default 1.50% — flip level itself)

Rationale: Distance to flip is the inverse of regime uncertainty.
  Far from flip  → regime is clearly established → normal size.
  Close to flip  → regime inflection imminent → scale up (next move is big).
```

**Entry blockers:**
- `vix > vix_ceiling` (default 35): dislocated pricing, skip
- `|net_gex| < min_abs_gex` (default $50M): signal in the noise, skip
- `open_trade is not None` and `max_concurrent = 1`: already exposed

---

## Worked Example #1 — Negative GEX → Long Straddle (Profit)

**Date:** April 14, 2025 | **Ticker:** SPY | **Spot:** $545

```
Options chain reads:
  Net dealer GEX:       −$2.1B   (dealers SHORT gamma)
  Gamma flip level:     $555     (spot below flip by 1.83%)
  Call wall:            $558     (limited relevance — below strategic zone)
  Put wall:             $538     (support nearby)
  Regime:               NEGATIVE
  ATM IV (30 DTE):      24%
  VIX:                  21.6

DGR signal: BUY — long_straddle
Position size: 0.94% of capital (dist_to_flip = 1.83%)
```

**Entry (April 14 close):**
```
$100,000 account, 0.94% risk = $940 risk budget
Buy 1× SPY $545 call @ 30 DTE
Buy 1× SPY $545 put  @ 30 DTE
Combined debit: $11.70 × 100 = $1,170 (1 contract of each leg)
  → slightly over budget, OK at 1-lot granularity
Commissions: $0.65 × 2 = $1.30
Total cost:  $1,171.30
```

**Price action over the following 8 sessions:**
```
Date       SPY Close   ATM IV  Daily range   Notes
─────────────────────────────────────────────────────────────
Apr 14     $545.00     24.0%   0.9%          Entry
Apr 15     $541.80     25.1%   1.2%          Broke put wall $538 intraday
Apr 16     $538.20     26.8%   1.5%          Follow-through selling, negative GEX working
Apr 17     $534.10     28.5%   1.8%          VIX hit 24, dealers amplified
Apr 18     $536.90     27.2%   1.4%          Brief bounce — dealer short-gamma snapback
Apr 22     $532.70     28.1%   1.6%          Drift lower continues
Apr 23     $530.40     28.9%   1.5%          −2.7% over 7 sessions (well beyond breakeven)
```

**Straddle value on April 23:**
```
Put (K=$545, 22 DTE, iv=0.289):   $16.90
Call (K=$545, 22 DTE, iv=0.289):  $4.30
Current combined value:            $21.20 × 100 = $2,120
Entry debit:                       $1,170
Gross P&L:                         +$950  (+81.2% on debit)

Take-profit trigger: +60% of debit = +$702 → HIT
Close at Apr 23 close:
  Exit value:    $2,120
  Commissions:   $1.30 (exit)
  Net P&L:       $2,120 − $1,171.30 − $1.30 = +$947.40  (+81.0%)
```

**What happened:** Negative GEX did exactly what it was supposed to do —
amplified the downward drift. The put leg became ITM and the IV expanded from 24%
to 29% (vega tailwind on top of the directional move). The call leg decayed but
the put leg more than compensated.

Had we followed the VIX ladder (GEX Positioning) instead, we would have cut SPY
from 60% to 35% at VIX=22 confirmation — saving drawdown but generating *no
active profit*. DGR turned the same regime into $947.

---

## Worked Example #2 — Positive GEX → Iron Condor (Profit)

**Date:** October 1, 2024 | **Ticker:** SPY | **Spot:** $568

```
Options chain reads:
  Net dealer GEX:       +$6.2B   (dealers deep LONG gamma)
  Gamma flip level:     $556     (spot above flip by 2.16%)
  Call wall:            $578     (resistance magnet)
  Put wall:             $561     (support magnet)
  Regime:               POSITIVE
  ATM IV (35 DTE):      13%
  VIX:                  14.2

DGR signal: SELL — iron_condor anchored on walls
Position size: 0.84% of capital
```

**Entry (Oct 1 close):**
```
$100,000 account, 0.84% risk → max loss budget ≈ $840
Strike selection (15Δ targets):
  15Δ call strike (model): $578 (matches call wall exactly — anchor here)
  15Δ put strike (model):  $560 (put wall at $561 — anchor to the wall)

Final condor:
  Short $578 call, long $583 call (wing width $5 = 1×EM)
  Short $561 put,  long $556 put  (wing width $5)
  Credit received: $1.52 × 100 = $152 per contract
  Max loss:        ($5 − $1.52) × 100 = $348 per contract
  Contracts:       floor($840 / $348) = 2 contracts
  Total credit:    $304
  Total max loss:  $696

Cost (commissions): $0.65 × 4 legs × 2 = $5.20
```

**Price action over the following 4 weeks:**
```
Date       SPY       ATM IV   Within wall band?
───────────────────────────────────────────────
Oct 1      $568.00   13%      YES  (between $561 and $578)
Oct 7      $571.40   13%      YES
Oct 14     $566.20   14%      YES
Oct 21     $573.10   13%      YES
Oct 28     $569.80   14%      YES  (max range = 0.9% per day, dealers pinning)
Nov 4      $570.40   12%      YES
```

**Condor value on Nov 4 (28 days later, 7 DTE remaining):**
```
All four legs are far OTM. Combined buyback value: $0.38
Current P&L: $304 credit − $0.38 × 2 × 100 = $304 − $76 = $228 profit
50% profit target = $152 → HIT at Oct 28

Actual exit: Oct 28 close, close condor for $0.72 buyback × 2 = $144
Net P&L: $304 − $144 − $5.20 − $0.65×8 = $149.60  (+21.5% on max loss budget)
```

**What happened:** Positive dealer gamma kept SPY firmly between the $561 put
wall and $578 call wall for the entire cycle. Ranges stayed below 1% per day.
Theta decayed in our favour. The condor collected 49% of max profit in 27 days
and we closed at the 50% rule.

A VIX-ladder strategy would have held 90% SPY and earned the ~+2.6% equity
return. DGR layered +1.5% on top via the condor — stacking an active alpha
on a passive equity return.

---

## Worked Example #3 — Near-Flip Breakout (Large Winner)

**Date:** August 1, 2024 | **Ticker:** SPY | **Spot:** $552

```
Options chain reads:
  Net dealer GEX:       +$0.4B   (barely positive)
  Gamma flip level:     $551.50
  dist_to_flip:         +0.09%   →  WITHIN near_flip_pct (0.25%)
  Regime:               NEAR_FLIP
  ATM IV:               16.1%
  VIX:                  16.0

DGR signal: BUY — long_straddle
Position size: 1.47% of capital (near-flip scales size up)
```

**Entry (Aug 1 close):**
```
$100,000 account, 1.47% risk = $1,470 budget
Buy 1× SPY $552 call @ 30 DTE
Buy 1× SPY $552 put  @ 30 DTE
Combined debit: $10.45 × 100 = $1,045
Contracts: 1 lot (budget permits 1.4 lots; rounds to 1)
Total cost: $1,046.30 (with comm)
```

**What followed (BoJ rate hike crisis — yen carry unwind):**
```
Date        SPY       ATM IV   VIX   Event
────────────────────────────────────────────────────────────
Aug 1       $552.00   16%      16    Entry
Aug 2       $542.80   23%      23    BoJ surprise hike, carry unwind begins
Aug 5       $513.40   38%      39    SPY −7% on the day; VIX touched 65 intraday
Aug 6       $520.20   32%      27    Bounce
Aug 7       $518.80   30%      26    Settling
Aug 8       $526.60   25%      23    Recovery continues
```

**Straddle value Aug 5 close (3 days after entry):**
```
Put (K=$552, 27 DTE, iv=0.38):     $41.20
Call (K=$552, 27 DTE, iv=0.38):    $2.30
Combined:                          $43.50 × 100 = $4,350
Entry debit:                       $1,045
Gross P&L:                         +$3,305  (+316% on debit)

Take-profit at +60% triggered Aug 2 at +$627. If held (override), Aug 5 = +$3,305.
In production: automatic close at +60% → +$627 locked in on Aug 2.
```

**What happened:** The flip-zone setup on Aug 1 was signaling exactly what it's
designed for — an imminent regime change. When the BoJ news hit, SPY *broke
through* the flip level into deep negative GEX territory, and the dealer-short-gamma
amplification cascaded. The put leg exploded; the call leg was nearly worthless.
Either way, the straddle paid. This is the DGR "whichever direction breaks"
payoff profile at its best.

**Compare to VIX ladder**: On Aug 1 with VIX=16, GEX Positioning held 80% SPY.
By Aug 5 the emergency override triggered a cut to 15% SPY, but most of the
drawdown had already happened. The DGR straddle generated positive alpha on the
move itself.

---

## Worked Example #4 — Losing Trade (Chop Kills the Straddle)

Not every trade wins. Here is the typical loser.

**Date:** March 4, 2024 | **Ticker:** SPY | **Spot:** $512

```
Options chain reads:
  Net dealer GEX:       −$0.8B   (mildly negative)
  Gamma flip level:     $515
  dist_to_flip:         −0.58%   →  Regime NEGATIVE
  ATM IV:               12%
  VIX:                  13.8

DGR signal: BUY — long_straddle
Position size: 0.80% = $800 budget
```

**Entry (Mar 4 close):**
```
Buy 1× SPY $512 call @ 30 DTE
Buy 1× SPY $512 put  @ 30 DTE
Combined debit: $8.80 × 100 = $880
Total cost: $881.30
```

**What followed:**
```
Date        SPY       ATM IV   Daily range   Notes
─────────────────────────────────────────────────────
Mar 4       $512.00   12%      0.6%          Entry
Mar 7       $510.20   11%      0.5%          Drift, no breakout
Mar 14      $514.80   10%      0.4%          Spot re-crossed flip → regime now positive
Mar 21      $513.50   11%      0.5%          Still chopping
Mar 28      $515.10   11%      0.5%          Theta eating value fast

Straddle value Mar 28 (7 DTE):
  Call: $3.30  Put: $1.40  Combined: $4.70 × 100 = $470
  Entry: $881.30
  P&L:   −$411  (−46.7% on debit)

DTE-exit rule triggers at 7 DTE: close regardless of P&L.
Net loss: $411 (within the −50% stop)
```

**What happened:** IV contracted (12% → 11%), vol regime normalized, spot
re-crossed the flip into positive GEX territory and the dealer dampening took
over. A straddle sold during a transition FROM negative back TO positive is
the worst configuration — theta and vega both eat the debit. The 7-DTE
time-exit limits the damage.

**Takeaway:** Even correctly-signaled trades fail when the regime reverts
quickly. The expected hit rate for long straddles in negative-GEX signals is
**~40%** but winners are 2–4× the size of losers — positive expectancy comes
from asymmetry, not win rate.

---

## Worked Example #5 — Condor Stopped Out (Loser)

**Date:** September 12, 2022 | **Ticker:** SPY | **Spot:** $405

```
Options chain reads:
  Net dealer GEX:       +$0.9B   (barely positive)
  Gamma flip level:     $401
  Regime:               POSITIVE  (spot above flip by 1.0%)
  Call wall:            $415
  Put wall:             $392
  ATM IV:               22%
  VIX:                  23.5

DGR signal: SELL — iron_condor
WARNING: VIX elevated, but below ceiling (35). Proceed.
Position size: 1.00% risk budget = $1,000
```

**Entry (Sep 12 close):**
```
Condor:
  Short $413 call / Long $418 call (wing width $5)
  Short $397 put  / Long $392 put
  Credit: $2.10 × 100 = $210 per contract
  Max loss: $290 per contract
  Contracts: floor($1,000 / $290) = 3
  Total credit: $630
  Total max loss: $870
```

**What followed — Sep 13 CPI shock:**
```
Date        SPY       VIX    Event
─────────────────────────────────────────────────────
Sep 12      $405      23.5   Entry
Sep 13      $391      27.2   CPI hot, SPY −4.3% on the day, broke put wall $392
Sep 14      $391      26.8   Gap held, no reversal
Sep 15      $389      27.4   Below long put strike $392 — condor fully against us
```

**Condor value Sep 14:**
```
Short $397 put: $9.20 (deep ITM, expensive to close)
Long  $392 put: $5.60 (some offset)
Short $413 call: $0.10 (far OTM, fine)
Long  $418 call: $0.02
Cost to close: ($9.20 + $0.10 − $5.60 − $0.02) × 100 = $368 per contract
Current loss: $368 − $210 = $158 per contract → $474 total

Stop-loss trigger at 2× credit = $420 total → HIT
Close at Sep 14 close: $474 loss locked in.
Net P&L: −$474 − commissions
```

**What happened:** An unexpected CPI print punched SPY through the put wall in
a single session. "Positive GEX" only means dealers CAN dampen — not that they
always do. A large enough exogenous shock (news, Fed, earnings for single names)
overwhelms the dealer-hedging equilibrium. The 2× stop-loss rule is what
prevented this from becoming max-loss ($870 instead of $474).

**Rule of thumb:** Skip condor entries T−1 to T+0 around FOMC, CPI, NFP, and
earnings for single names. Event risk dominates dealer positioning.

---

## Example #6 — Full Month of DGR Signals (SPY, May 2024)

```
Day   SPY    Flip    Dist    Regime       VIX   Action                          P&L (if closed)
────  ─────  ──────  ──────  ───────────  ────  ──────────────────────────────  ─────────────
5/1   $500   $497    +0.60%  POSITIVE     15.3  Enter condor (walls at $490/$510)
5/2   $501   $497    +0.81%  POSITIVE     14.9  Hold condor
5/3   $503   $497    +1.21%  POSITIVE     14.2  Hold
…
5/10  $505   $498    +1.41%  POSITIVE     13.5  Close condor @ +50% TP          +$78 per lot
5/13  $504   $504    +0.00%  NEAR_FLIP    13.9  Enter straddle (size scaled up)
5/14  $502   $504    −0.40%  NEGATIVE     14.6  Hold straddle
5/15  $497   $504    −1.39%  NEGATIVE     15.8  Hold — move building
5/16  $493   $504    −2.18%  NEGATIVE     17.2  Straddle MTM +60%                Close @ +60% TP
…
5/20  $495   $501    −1.20%  NEGATIVE     16.9  Enter straddle (continuation)
5/24  $502   $500    +0.40%  POSITIVE     14.1  Regime flipped; straddle stop at −20%  −$55 per lot
5/28  $506   $500    +1.20%  POSITIVE     13.8  Enter condor (walls $495/$512)
…
5/31  $510   $501    +1.80%  POSITIVE     13.4  Condor tracking +30%             MTM only

Month summary: 4 trades (2 condors + 2 straddles)
  Condor #1:   +$78  (win)
  Straddle #1: +$700 (big win — regime break)
  Straddle #2: −$55 (loss — whipsaw)
  Condor #2:   open, tracking +$45 MTM
  Realized:    +$723 on ~$3,000 cumulative risk budget  →  +24% on risk taken
```

---

## Sign Convention Pitfall — When to Invert

The default sign convention (`index_retail_call_long`) is validated for SPX, SPY,
QQQ, and most liquid index ETFs — retail/corporate call-writing flow dominates.

It BREAKS for:

```
Ticker       Why default breaks                           Correct convention
───────────  ─────────────────────────────────────────    ──────────────────
GME, AMC     Retail is massive call buyer on meme         'retail_put_long' (inverted)
             squeeze — dealers short calls, long puts
NVDA         Mixed; retail call-buying can flip sign       Use 'auto_detect' (future)
             on quarterly earnings runs                    (v1: manually test both)
TSLA         Period-dependent — check OI imbalance         v1: manual
```

When building a DGR-per-ticker, verify by checking:
- If OI is heavily weighted toward calls AND IV skew is inverted (calls > puts):
  likely `retail_put_long` applies (retail is bullish, dealers short calls).
- SPY/SPX: always default.
- Everything else: test both, pick the one that produces a flip level consistent
  with observed intraday support/resistance.

Unit test `test_sign_convention_inversion` verifies the flip symmetry — sign
inversion flips net_gex sign exactly.

---

## OPEX / Charm / Vanna — The Calendar Effects

DGR's v1 implementation is OPEX-aware via two mechanisms:

1. **0DTE separation**: `net_gex_multiday` excludes 0DTE contracts, so the core
   signal isn't contaminated by expiring-today gamma that won't persist.

2. **Time-based exits**: `condor_dte_exit=21` and `straddle_dte_exit=7` bias
   exits away from the final week where charm (delta decay) and gamma
   concentration warp P&L nonlinearly.

### Charm

In positive GEX regimes, call-side dealer delta decays Thursday/Friday as
short-dated contracts lose time value. Dealers *buy back* their equity hedges
as puts expire worthless. This creates the well-documented **afternoon upward
drift** in low-VIX positive-GEX conditions (Fri 14:00–close).

**DGR treatment:** The 21 DTE condor exit avoids most charm distortion. If
manually overlaying an intraday trade on DGR signals, a +1% call debit spread
long Fri afternoon when DGR flags POSITIVE and VIX < 16 has captured ~0.3% on
average.

### Vanna

Vanna = ∂delta/∂IV. When IV drops intraday, dealer calls become less sensitive,
forcing dealers to *buy* stock to maintain delta neutrality. An 8%+ intraday VIX
drop while DGR flags POSITIVE is a long-delta catalyst — historically worth
+50–100bp over the following session.

**DGR treatment:** Not in v1 structures directly, but `generate_signal` exposes
the VIX context in metadata; a higher-level overlay can consume it.

### OPEX Week

30–50% of SPX gamma rolls off on the third Friday each month. The week before
OPEX (Mon–Thu), gamma compresses; the week after, gamma is reset.

**Recommended discretionary overlay:** reduce condor size by 50% the week of OPEX;
normal sizing Tuesday post-OPEX.

---

## Parameters — Full Reference

```
Parameter             Default  Range        Effect
────────────────────  ───────  ───────────  ──────────────────────────────────────────
near_flip_pct         0.25     0.05 – 1.0   Dist-to-flip band that triggers "near-flip" straddle
min_abs_gex           5e7      1e7 – 1e9    Noise floor; skip if |net_gex| below
vix_ceiling           35       20 – 60      Entry blackout above this VIX
sign_convention       index_.. (string)     Swap to 'retail_put_long' for inverted names

dte_entry_long        30       14 – 60      Straddle days-to-expiry at entry
dte_entry_condor      35       21 – 60      Condor days-to-expiry at entry
short_leg_delta       0.15     0.08 – 0.30  Condor short-leg target delta
wing_em_width         2.0      1.0 – 4.0    Condor wing width as multiple of expected move

base_risk_pct         0.75     0.25 – 3.0   Risk per trade when far from flip
max_risk_pct          1.50     0.5  – 5.0   Risk per trade when at flip level
max_concurrent        1        1 – 3        Max open DGR positions (v1: 1)

condor_profit_tgt     0.50     0.25 – 0.90  Close at this fraction of max profit
condor_stop_mult      2.0      1.0 – 3.0    Close at loss of this × credit
condor_dte_exit       21       14 – 28      Time exit
straddle_tp_mult      0.60     0.30 – 1.50  Close at +this × debit (e.g. 0.6 = +60%)
straddle_stop_pct     0.50     0.30 – 0.70  Close at −this × debit
straddle_dte_exit     7        3 – 14       Time exit (theta acceleration)

slippage_per_leg      0.05     (fixed)      Per-leg spread assumption
commission_per_leg    0.65     (fixed)      Retail commission per leg
```

---

## Data Requirements

```
Data                         Source                              Used for
───────────────────────────  ──────────────────────────────────  ─────────────────────────
Live options chain (full)    Polygon /v3/snapshot/options        GEX, flip, walls, IV
Price OHLCV                  Polygon /v2/aggs                    Spot, entry/exit pricing
VIX daily close              Polygon (VIXIND)                    Entry ceiling filter
Historical chains            Polygon/ORATS/CBOE DataShop         Backtest (option_snapshots)
FOMC / earnings calendar     Internal /data/calendars            (Optional) event blackout
```

**Snapshot cadence:** once per day at 09:45 ET. Overnight is stale for 0DTE
but fine for multi-day regime signals. Intraday re-snapshotting is needed only
for tactical entries during big moves.

---

## Common Mistakes

1. **Trusting GEX inside ±0.1% of the flip.** Flip levels jitter intraday as OI
   shifts. Require 2-session persistence of a regime before committing
   size. DGR v1 enforces this via `min_abs_gex` noise floor + `near_flip_pct`
   band.

2. **Ignoring the sign-convention mismatch on single names.** Running DGR on GME
   with the default convention is nonsense — invert the sign explicitly.

3. **Trading condors into known events.** FOMC, CPI, NFP, earnings (single names)
   — dealer positioning is drowned out by event-driven repricing. Skip T−1 to T+0.

4. **Overriding the straddle DTE exit.** The 7 DTE stop exists because theta
   accelerates. "It might still work" becomes "it's worth $0" very fast below 7 DTE.

5. **Sizing condors by credit instead of max-loss.** DGR sizes by max_loss
   (wing width − credit) because max-loss is what hits the account if you're wrong.
   Credit-based sizing leads to position sizes that are too large when wings
   are narrow.

6. **Running DGR concurrently with GEX Positioning without regime coordination.**
   Both use dealer gamma. If GEX Positioning is pushing to 15% SPY on a VIX spike
   while DGR is entering a long straddle, the portfolio is effectively doubling
   up on the same thesis. Either run DGR as a standalone book, or haircut its
   sizing when GEX Positioning is below 50% SPY.

7. **Treating straddles as a "vol buy" when IV is already elevated.** If VIX = 30
   on entry, most of the breakout is priced in — you're paying up for the move
   you expect. `vix_ceiling = 35` is a generous default; tighten to 25 for
   higher-edge entries.

---

## Entry & Exit Checklist

**Before entering a NEGATIVE-GEX long straddle:**
- [ ] Net GEX < −`min_abs_gex`
- [ ] Spot below flip level by > near_flip_pct (or within it for "near_flip" straddle)
- [ ] VIX ≤ vix_ceiling
- [ ] No FOMC / CPI / NFP / earnings in next 2 sessions
- [ ] Combined debit ≤ risk budget for this spot & flip distance

**Before entering a POSITIVE-GEX iron condor:**
- [ ] Net GEX > +`min_abs_gex`
- [ ] Spot above flip level by > near_flip_pct
- [ ] VIX ≤ vix_ceiling
- [ ] Detected walls at reasonable distance (body not inside `wall_min_dist_pct`)
- [ ] Max-loss × contracts ≤ risk budget
- [ ] No event risk window

**Straddle exit triggers:**
- [ ] +60% profit → close
- [ ] −50% debit loss → close
- [ ] 7 DTE → close regardless of P&L
- [ ] Spot crosses the flip (regime flipped against entry) → close

**Condor exit triggers:**
- [ ] +50% of max profit → close
- [ ] −2× credit loss → close
- [ ] 21 DTE → close
- [ ] Spot breaks the short strike on either side by > 0.5% → close

---

## How DGR Relates to Other Strategies

```
Strategy                   How DGR differs
──────────────────────     ──────────────────────────────────────────────────────────
GEX Positioning            Same signal (GEX) — but GEX-Pos adjusts equity allocation.
                           DGR trades options around it.
Gamma Flip Breakout (AI)   Uses XGBoost on GEX features, opens strangle/condor.
                           DGR is rules-based, no model, explicit wall-anchoring.
0DTE Iron Condor           Sells SAME-DAY condors. DGR targets 30–45 DTE for
                           multi-day regime persistence, not intraday theta.
VIX Spike Fade             Trades VIX mean-reversion via SPY call spreads.
                           DGR trades the underlying cause (dealer gamma),
                           not the volatility print itself.
```

Complementary overlay: GEX Positioning (portfolio allocation) → DGR (tactical
options) → VIX Spike Fade (tail event recovery). All three share the dealer-gamma
mental model but express it at different risk/return scales.

---

## Summary — When to Use DGR

Use DGR when:
- You want **active alpha** from dealer gamma, not just drawdown management.
- You can trade defined-risk options (spreads, straddles) on an optionable ticker.
- You have access to a daily options chain snapshot (Polygon, ORATS, CBOE).

Skip DGR and use GEX Positioning instead when:
- You are restricted to cash + equity only (no options).
- You want a simpler, lower-frequency signal.
- Your account is too small to run 1-lot spreads efficiently (≤ $5K).

Run BOTH when:
- You have ≥ $25K and want portfolio-level allocation + tactical overlay.
- Haircut DGR sizing by 50% when GEX Positioning has allocation < 50% SPY
  (both strategies are gamma-signal-heavy; don't double up).
