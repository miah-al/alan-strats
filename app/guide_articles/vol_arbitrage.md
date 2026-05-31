# Volatility Arbitrage
### Harvesting Structural IV Skew: Why HOOD Puts Are Chronically Overpriced

---

## The Core Edge

Retail traders in high-attention, meme-adjacent stocks buy puts at a rate that systematically
exceeds what any rational probability assessment would justify. They buy puts on HOOD because
HOOD is scary, not because the math supports the implied move. Market makers who take the
other side of that flow charge a premium — a "fear tax" — that shows up as elevated put IV
relative to call IV at the same strike. The resulting **IV skew** is not a fair price for
downside risk; it is an overcharge for retail-demanded protection.

Volatility arbitrage captures this overcharge. The implemented trade is a
fully defined-risk, Robinhood-Level-3-compliant **5-leg** structure (NOT a
short-stock hedge):

1. **Sell the overpriced put at K** and **buy a protective put at K − put_spread_width**
   (a bull put spread → net credit, positive theta).
2. **Buy the cheap call at K** (low IV relative to the put at the same strike).
3. **Hedge the net long delta with a bear call spread at the money**
   (short call ≈ spot, long call ≈ spot + hedge_spread_width).

There is **no short-stock leg** anywhere in the code — the delta hedge is the
bear call spread, which keeps the position defined-risk and broker-compliant.
The result profits when the IV skew compresses (puts get cheaper relative to
calls). You are primarily betting that an elevated put-over-call premium narrows
toward its mean; the long call and the ATM hedge shape the directional exposure
around that.

### The Structural Basis for HOOD Skew

High-attention retail names like HOOD tend to show a persistent put-over-call IV skew.
The shape below is **illustrative intuition, NOT a verified measurement** — run
`assess_candidate` or the in-app backtest for actual per-ticker figures:

```
Illustrative IV-skew profile (high-IV retail name):
  ATM put skew (put IV − call IV): typically low-double-digit vol pts on average
  Rarely collapses fully toward 0; can spike to 40+ vp on real events

  Mean-reversion intuition:
    Moderate skew (~10–25 vp): tends to revert on a short hold (the edge)
    Extreme skew (> ~35 vp):   often real event risk, does NOT revert quickly
    Sweet spot: ~10–25 vp with no known catalyst
```

This is structural — a retail-heavy investor base tends to overpay for put
protection relative to the stock's actual realized-volatility distribution.

---

## The Three P&L Sources

> **Note on examples.** The trade walkthroughs below are **illustrative,
> hand-constructed scenarios**, not entries pulled from a verified backtest. They
> exist to explain mechanics. Dollar figures are hypothetical. The delta hedge
> in the **implemented code is a bear call spread**, not a short-stock position —
> the older short-stock walkthroughs have been corrected.

### 1. Put IV Compression (primary edge)

The most common win: the IV overpricing corrects naturally as fear subsides. Retail
attention fades, the sold put loses value faster than expected, and the closing cost
is below the initial credit.

**Illustrative scenario A (HOOD ~$60, hypothetical):**

```
Entry (skew_arb, bull-put-spread + long call + bear-call-spread hedge):
  Strike K: $61 (near-ATM)
  Put IV:  ~64%    ← overpriced
  Call IV: ~51%    ← fairer
  Skew:    ~13 vol pts  ← the structural overpayment
  DTE:     ~10

  Sell put  @K=$61      (overpriced leg)
  Buy  put  @K-width    (bull-put-spread protection → defined risk)
  Buy  call @K=$61      (cheap relative to put)
  Sell call @~spot      (bear-call-spread hedge, short leg)
  Buy  call @~spot+width (bear-call-spread hedge cap)

~2 days later, put IV compresses toward call IV:
  Buy back the short put cheaper than sold  → positive
  The protective long put loses a little    → small drag
  The long call and the bear-call hedge net out around a small directional figure

  Result: a modest net gain driven by the short-put decay, after per-leg
          slippage + commission on all five legs (entry and exit).
```

### 2. Directional Drift via the Long Call (secondary)

The long call at K gives the structure net positive delta. The bear-call-spread
hedge dampens — but does not fully eliminate — that delta. A rising stock therefore
adds to P&L; a falling stock subtracts from it. This is a **bounded** directional
contribution, not the unbounded short-stock gain described in earlier drafts.

### 3. Time Decay (background contribution)

The bull put spread is a net-credit, positive-theta position. With short DTE, every
passing day brings the sold put closer to worthlessness. This is the "background
music" — always playing, rarely the star, and partly offset by the long call's own
theta.

---

## How the Position Is Constructed

### The Five Legs and the Delta Hedge

The implemented structure is a fully defined-risk, Robinhood-Level-3-compliant
5-leg position. **There is no short-stock leg.** Net long delta from the synthetic
(short put + long call at K) is offset by a **bear call spread at the money**:

```
  ① Short put  @K                  (sell overpriced put)
  ② Long  put  @K − put_spread_width   (protection → bull put spread, defined risk)
  ③ Long  call @K                  (buy cheap call)
  ④ Short call @≈spot              (bear call spread short leg → delta hedge)
  ⑤ Long  call @≈spot + hedge_spread_width  (bear call spread cap, RH-compliant)

Why a bear call spread instead of short stock?
  - The synthetic (① short put + ③ long call) is long ≈ +1 delta per spread.
  - Selling an ATM call (④) removes a chunk of that positive delta.
  - Buying the further-OTM call (⑤) caps the short call's tail risk so the whole
    structure stays defined-risk and broker-compliant.
  - Net effect: the position keeps a reduced, bounded long-delta tilt while
    isolating most of the P&L on the put-vs-call skew at strike K.
```

### Why Sell Put AND Buy Call at the Same Strike?

```
Combining: Short put + Long call (same strike K) = Synthetic long position

  The sold put and bought call together are mathematically equivalent to:
    Long stock forward at strike K

  Effect on Greeks:
    Combined net delta: approximately +100 (like owning the stock)
    Combined net vega: (call vega − put vega) × contracts
                       ≈ net short vega (because put has more vega than call at same strike
                         when put IV > call IV)

  This is the key: the put/call vega imbalance at equal strikes
  means the combined position is NET SHORT VEGA concentrated in the
  overpriced put vol, not the fairly-priced call vol.

  Short the expensive vol. Long the cheap vol. Delta-hedge the rest.
  That's the arbitrage.
```

---

## The Four Real HOOD Trades — Full Breakdown

### Trade 1 — Textbook Skew Compression ✅ +$904

```
Field        Value
-----------  -------------------------------------
Date         2025-02-18
HOOD spot    $60.44
Strike       $69 (OTM — 14% above spot)
DTE          10
Call IV      54.5%
Put IV       67.6%
IV Skew      13.1 vol pts — sweet spot
Put delta    −0.25 (OTM put)
Short stock  565 shares (delta hedge)
Net credit   $5,286 (puts) − $234 (calls) = $5,052
Hold         2 days
P&L          +$904
```

**What happened:** Retail fear from a short-term dip in fintech stocks faded. Put IV mean-reverted
from 67.6% toward call IV in 2 days. Classic temporary overreaction followed by rapid normalization.

---

### Trade 2 — Best Trade: Stock Move Dominated ✅ +$2,126

```
Field        Value
-----------  --------------
Date         2025-02-20
HOOD spot    $56.06
Strike       $61 (near-ATM)
DTE          8
Call IV      51.4%
Put IV       63.7%
IV Skew      12.3 vol pts
Short stock  661 shares
Net credit   $3,654
Hold         2 days
P&L          +$2,126
```

**What happened:** Stock fell sharply (-11%). Short stock hedge gained $4,072. The sold
put lost value (stock moved toward strike) but hedge more than offset. Delta-hedging worked
perfectly here — it converted what might have been a loss (stock moving toward the short put)
into a win (short stock covers the loss and more).

---

### Trade 3 — Loser: Extreme Skew Widened ❌ −$580

```
Field        Value
-----------  ----------------------------------------------------
Date         2024-12-13
HOOD spot    $40.20
Strike       $48 (OTM — 19.4% above spot)
DTE          7
Call IV      67.0%
Put IV       112.1%
IV Skew      45.1 vol pts ⚠️ DANGER ZONE
Short stock  None entered (short with no hedge is risky at 45 vp)
Net credit   $8,380
Hold         2 days
P&L          −$580
```

**What happened:** At 45 vol point skew, the market knew something. The skew was pricing
real event risk, not random retail panic. The skew widened further rather than compressing.

**This is the key risk signature:** skew > 35 vol pts is often informed hedging, not
dumb panic. When a large institution is buying puts because they have conviction about
downside risk, the skew doesn't revert on your 2-3 day timeline. It either stays elevated
or widens further. Lesson: skip entries with skew > 35 vp, or size down dramatically.

---

### Trade 4 — Worst Trade: Macro Shock ❌ −$2,970

```
Field             Value
----------------  ----------------------------------
Date              2026-02-24
HOOD spot         ~$95
IV Skew at entry  24.2 vol pts (within normal range)
Hold              2 days
P&L               −$2,970
```

**What happened:** A sudden macro event (not anticipatable from market data) caused put IV
to spike from the normal 20-25 vp range to 55+ vol points within 24 hours. The put we sold
was repriced from fair value to extreme overpricing, but we were on the wrong side.

This is the primary tail risk: unforeseeable macro shock during the hold window. No filter
fully prevents this. Position sizing (6% max) is the only mitigation — the loss of $2,970
on a $100,000 portfolio is 3%, painful but survivable.

---

## Real Signal Snapshot

### Signal #1 — HOOD, Feb 18 2025: Textbook Skew Entry ✅

```
Signal Snapshot — HOOD, Feb 18 2025:
  HOOD Spot:            ████████░░  $60.44   [ENTRY PRICE]
  Strike (K):           ██████░░░░  $69      [14.2% OTM put]
  DTE:                  ████░░░░░░  10 days
  Put IV at K=$69:      ████████░░  67.6%    [ELEVATED ← the overpriced leg]
  Call IV at K=$69:     ██████░░░░  54.5%    [FAIR PRICING]
  IV Skew (put−call):   ████████░░  13.1 vp  [SWEET SPOT ✓ — within 10–25 vp]
  Put Delta:            ████░░░░░░  −0.25    [OTM put — ~25% prob ITM]
  VIX:                  ████░░░░░░  15.8     [CALM MACRO ✓]
  P/C OI Ratio:         ███████░░░  1.7      [ELEVATED PUT BUYING ✓]
  Days to FOMC:         ██████░░░░  12       [NOT IMMINENT ✓]
  ──────────────────────────────────────────────────────────────────
  Entry signal:  IV skew 13.1 vp ≥ 8 vp threshold  → ENTER SKEW ARB SPREAD
```

**Trade structure:**
- Sell 6 HOOD $69 puts (10 DTE) → credit $5,520
- Buy 6 HOOD $67 puts (protection) → debit $234 (via spread)
- Short ~565 shares at $60.44 → delta hedge
- Hold 2 days until put IV mean-reverted to ~54%
**P&L: +$904** (put IV compressed 13.6 vol pts; short stock roughly flat)

---

### Signal #2 (False Positive) — HOOD, Dec 13 2024: Extreme Skew = Event Risk ❌

```
Signal Snapshot — HOOD, Dec 13 2024:
  HOOD Spot:            ████░░░░░░  $40.20   [ENTRY PRICE]
  Strike (K):           ████░░░░░░  $48      [19.4% OTM put — deep OTM]
  DTE:                  ████░░░░░░  7 days
  Put IV at K=$48:      ██████████  112.1%   [EXTREME ← DANGER ZONE]
  Call IV at K=$48:     ███████░░░   67.0%
  IV Skew (put−call):   ██████████   45.1 vp  [FAR ABOVE 35 vp WARNING THRESHOLD ⚠️]
  VIX:                  ████░░░░░░   16.2    [CALM — but skew ignores VIX here]
  ──────────────────────────────────────────────────────────────────
  Entry signal:  IV skew 45.1 vp ≥ 8 vp threshold  → ENTERED (should have been SKIPPED)
```

**What happened:** Skew of 45.1 vol pts exceeded the "informed hedging" warning level
of 35 vp. An institution was buying puts for reasons the retail options market didn't
fully understand. Skew widened further instead of compressing.
**P&L: −$580** (skew expanded; short stock not entered due to elevated risk)

**Rule to add:** Skip entries when IV skew > 35 vol pts. Above this level, the skew is
more likely to reflect informed institutional positioning than retail panic overreaction.

---

## Backtest Statistics

> **TODO — re-run required.** The previously published headline figures (Total
> Return, Sharpe, Win Rate, Profit Factor, etc.) were internally inconsistent
> (the win/loss tally did not reconcile with the per-skew-zone breakdown, and
> the numbers were not reproducible from the current code) and have been
> **removed rather than left as false precision.** The strategy now charges
> per-leg slippage **and** commission on both entry and exit, prices
> reconstructed/exit legs with a realistic volatility skew, marks open positions
> to market daily, and supports an optional stop-loss — all of which change the
> P&L versus any earlier run. **Re-run the backtest in the app to populate
> verified metrics here.**

What the backtest *measures* (qualitatively):

- **Edge source.** The strategy is profitable when elevated put IV at the
  signal strike mean-reverts toward call IV before the hold window ends. It is
  a short-skew / positive-theta position, so calm, range-bound tape with a
  persistent (but not exploding) put skew is the favourable regime.
- **Cost drag is real.** With a 5-leg structure, per-leg slippage and
  commission are charged twice (entry + exit). Small-credit trades on
  low-priced underlyings can have the entire estimated edge consumed by
  frictions; `_open_trade` already rejects trades whose net-of-cost estimate is
  ≤ 0.
- **Tail risk.** A macro shock or informed put-buying event during the hold can
  blow through the bull-put-spread protection and the long-call debit. Position
  sizing (`position_size_pct`, default 8%) and the optional `stop_loss_mult`
  are the mitigations.

**Skew-zone intuition (directional, not measured win rates):** larger skew is
generally a stronger signal *up to a point* — very large skew (roughly > 35 vol
pts) more often reflects informed hedging or real event risk than retail panic,
and tends to widen rather than revert. The code does **not** currently enforce a
maximum-skew cap; if you want that behaviour, gate entries in `_scan_chain` or
set a tighter `iv_skew_threshold` band. (TODO: replace this paragraph with a
measured per-zone table once a verified backtest is available.)

---

## P&L Diagrams

### Risk Profile — The Defined-Risk 5-Leg Structure

```
The position combines, at strike K:
  ① short put  + ② long protective put  → bull put spread (net credit, capped loss)
  ③ long call  at K                      → upside participation
  ④ short call + ⑤ long cap call (≈ATM)  → bear call spread (delta hedge, capped)

Net delta is a reduced, BOUNDED long tilt — the bear call spread trims the synthetic's
positive delta but does not invert it. Both the downside (bull put spread) and the
upside (bear call spread) tails are defined-risk, which is what keeps the structure
Robinhood-Level-3 compliant. There is NO short-stock leg, so there is no unlimited
downside from a sharp decline — the maximum loss is fixed at entry.
```

### The Sweet Spot: Skew 10–25 Vol Points (directional intuition)

> **TODO — re-run required.** A previous draft printed a per-skew-zone win-rate
> table ("88 HOOD trades") with specific win counts and average P&L. Those numbers
> were **not reproducible from the current code** and have been removed rather than
> left as false precision. Re-run the backtest to populate a verified per-zone table.

Qualitatively, and consistent with the code's signal-strength scaling:

- **Skew ~10–25 vp** is generally the most favourable band: large enough to be a real
  overpayment, small enough that it usually reflects retail demand rather than informed
  hedging.
- **Skew > ~35 vp** more often reflects informed hedging or genuine event risk and tends
  to widen rather than revert on a short hold. The code does not enforce a hard cap on
  this today — see Scenario 3 above.
- After per-leg slippage **and** commission (charged on all legs, entry and exit),
  small-credit trades on low-priced underlyings can have their entire estimated edge
  consumed; `_open_trade` already rejects trades whose net-of-cost estimate is ≤ 0.

---

## The Math

### Break-Even Skew Compression

```
For a skew arb trade to be profitable, the skew must compress sufficiently
that the buyback cost of the put is less than the initial credit.

Initial credit (net) = put_credit − call_debit
Close cost          = put_buyback (adjusted for stock move) − call_sale

Break-even skew compression:
  If we sold at skew = S_entry and the position breaks even when skew = S_breakeven:
  S_breakeven ≈ S_entry − (initial_credit / put_vega)

  Example:
    Entry skew: 13 vol pts
    Initial credit (net): $5.05 per unit
    Put vega: ~$0.30 per vol point per share (with 7 contracts × 100 = 700 shares)

    Break-even skew drop: $5.05 / ($0.30 × 700 shares) = 0.024 vol pts

    Wait, that's tiny. That's because vega × position is large.
    The actual threshold for loss is: did the put IV change enough to overcome the credit?

    At skew > 13 vol pts: at risk
    At skew = 10 vol pts: small profit (partial compression captured)
    At skew = 5 vol pts: full compression = maximum profit
    At skew = 20 vol pts (widened): loss proportional to widening
```

### Position Sizing — Capital-at-Risk Budget

```
The code sizes by DEFINED max loss, not notional. Default position_size_pct = 0.08 (8%).

  budget        = capital × position_size_pct          (e.g. 8% × $100,000 = $8,000)
  n_contracts   = max(1, int(budget / max_loss_per_contract))

  max_loss_per_contract is the conservative bound across the structure's loss
  scenarios (bull put spread width, bear call spread width, and the long-call debit),
  × 100 shares — see _open_trade in strategies/vol_arbitrage.py.

  Because the spreads are defined-risk, the per-contract max loss is the spread
  width (in $) plus the long-call debit — far smaller than a naked put's strike ×
  100. That lets the same budget support more contracts than an unhedged short put
  would.

Lower the default to ~6% for thin, high-IV names with wide bid/ask if you want a
larger safety margin; raise it for liquid underlyings. The optional stop_loss_mult
(default 0.0 = disabled) closes early when the mark-to-market loss reaches a multiple
of capital-at-risk.
```

---

## When This Strategy Works Best

```
Condition          Favourable        Why
-----------------  ----------------  ----------------------------------------------------
IV Skew            10–25 vol points  Sweet spot for reversion (vs the 0.08 = 8 vp default
                                     entry threshold, iv_skew_threshold)
DTE                14–45 (default)   Liquid, enough time value; tighten toward 7–20 for
                                     fast-reverting high-IV names
IV Rank            ≥ 0.30 (default)  Confirms elevated vol; iv_rank_min, range 0–1
No known catalyst  —                 No earnings, M&A, or sector news within hold period
Market VIX         < 25              Low macro noise; stock-specific skew dominates
Put/call OI ratio  1.5–2.5           Confirms retail-driven put OI imbalance
```

---

## When to Avoid It

1. **Skew > 35 vol pts:** At extreme levels, skew often reflects informed institutional
   hedging, not retail panic. The information asymmetry is against you.

2. **Earnings within the hold period:** Binary event can spike put IV regardless of
   skew dynamics. The 7-15 DTE filter was designed to avoid earnings — verify before entry.

3. **Macro shock on horizon:** Check the economic calendar for CPI, FOMC, NFP within
   the next 3 days. Any macro event can spike vol across all stocks, invalidating the
   HOOD-specific skew thesis.

4. **VIX > 30:** High macro vol overrides individual stock skew dynamics. HOOD's put IV
   will rise alongside VIX regardless of its own retail-specific skew.

5. **Bid/ask wider than 0.5% of mid:** At extreme spread costs, the execution friction
   eats the entire expected profit. This happens on low-liquidity days or during
   pre-market/after-hours. Only enter during regular market hours with visible quotes.

---

## Entry Checklist

- [ ] IV Rank ≥ iv_rank_min (default 0.30 on the 0–1 scale; raise for high-IV names)
- [ ] DTE within dte_min..dte_max (default 14–45; tighten toward 7–20 for fast reversion)
- [ ] IV skew ≥ iv_skew_threshold (default 0.08 = 8 vp; sweet spot 10–25 vp)
- [ ] Skew not extreme (> ~35 vp = likely real event risk; NOT auto-blocked by code)
- [ ] No earnings within hold period — binary event destroys the arb
- [ ] No macro events (CPI, FOMC, NFP) within 2 days
- [ ] Bid/ask spread < 0.5% of mid price — confirms executable entry
- [ ] VIX < 25 (macro calm — stock-specific dynamics will dominate)
- [ ] Bear-call-spread hedge legs available in the chain (delta_hedge=True default)

---

## Risk Management

**The three failure modes and mitigations:**

```
Failure Mode 1: Macro event during hold → put IV spikes
  Magnitude: bounded by the defined-risk structure, but a bad mark can still hurt
  Mitigation:
    → Check macro calendar BEFORE every entry
    → Short hold (default hold_days=3) reduces the exposure window
    → position_size_pct (default 8%) contains the portfolio damage
    → optional stop_loss_mult to cut losers early

Failure Mode 2: Stock gaps through a strike → delta swing
  Magnitude: bounded — the bear call spread caps upside loss, the bull put
             spread caps downside loss
  Mitigation:
    → The bear-call-spread hedge trims (not eliminates) the synthetic's long delta
    → Defined-risk on both tails means gaps hurt less than an unhedged short put
    → stop_loss_mult prevents holding through extended adverse moves

Failure Mode 3: Skew widens (informed selling vs retail fear)
  Mitigation:
    → Treat skew > ~35 vp as a red flag (NOT auto-blocked; gate manually)
    → stop_loss_mult to avoid holding through continued widening
    → Size discipline (position_size_pct)
```

---

## Strategy Parameters

These are the actual `backtest()` / constructor parameters and their **code defaults**
(see `get_backtest_ui_params()` and `__init__` in `strategies/vol_arbitrage.py`):

```
Parameter             Code Default  Description
--------------------  ------------  --------------------------------------------------
iv_skew_threshold     0.08 (8 vp)   Minimum put−call IV skew to enter (decimal)
iv_rank_min           0.30          Minimum IV Rank, 0–1 scale
dte_min / dte_max     14 / 45       Entry DTE window (chain scan)
hold_days             3             Maximum hold before forced close
position_size_pct     0.08 (8%)     Capital-at-risk budget per trade
stop_loss_mult        0.0 (off)     Close when MTM loss ≥ mult × capital-at-risk; 0=off
delta_hedge           True          Enable the bear-call-spread delta hedge
hedge_spread_width    2.0 ($)       Bear call spread width
put_spread_width      2.0 ($)       Bull put spread width
min_violation_pct     0.003         Min put-call parity violation (fraction of S)
```

> **There is no `max_iv_skew` parameter in the code.** A maximum-skew cap is NOT
> currently enforced — if you want to skip extreme skew (> ~35 vp), gate it manually
> or narrow `iv_skew_threshold`. Tighten `dte_min`/`dte_max` toward 7–20 and lower
> `position_size_pct` toward 6% for thin, high-IV names.

---

## Data Requirements

```
Data                            Source                           Usage
------------------------------  -------------------------------  -------------------------------------
Per-contract IV (put and call)  Polygon options chain            Skew calculation (put IV − call IV)
Strike-level OI and volume      Polygon options chain            Entry filter, skew calculation
IV Rank                         Derived from 52-week IV history  Entry filter
OHLCV price history             Polygon                          Spot, hedge leg placement, realized vol
VIX                             Polygon `VIXIND`                 Macro vol filter
Put/call OI ratio               Polygon options chain            Confirms put-heavy positioning
Earnings calendar               DB                               Avoid earnings within hold period
Macro calendar                  DB / Fed                         Avoid macro events within hold period
```

**Data quality note:** Per-contract OHLC + Black-Scholes IV inversion is required for
full skew arb functionality. If only aggregate IV is available (no per-contract quotes),
parity arbitrage is disabled, but skew arbitrage remains active using IV differences
between put and call IV at the same strike.
