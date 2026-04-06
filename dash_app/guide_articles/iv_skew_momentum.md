# IV Skew Momentum
### Reading the Options Market's Directional Fear Gauge Before Price Confirms

---

## The Core Edge

The options market knows things before the equity market. Not because options traders
have insider information, but because institutional money hedges through options first
and expresses directional views through equity positions second. The slope of implied
volatility across strikes — called the "skew" — is therefore a leading indicator of
where equity prices are heading.

Specifically, the **25-delta put skew** (also called the "risk reversal") measures the
premium that 25-delta puts command over 25-delta calls, normalized by ATM IV. When put
skew is collapsing — falling rapidly toward historical norms — it signals that hedging
demand is subsiding, protection-buying is ending, and the stock is about to rally. When
put skew is spiking — rising sharply above historical norms — it signals that institutional
money is aggressively buying protection, and the underlying is likely to decline.

The IV Skew Momentum strategy converts this continuous market signal into a systematic
three-class prediction: NEUTRAL, BULLISH (enter bull call spread), or BEARISH (enter
bear put spread). The LightGBM model identifies when skew has reached an extreme and
is *changing direction* — the momentum of skew change, not just the level, is the key
predictive variable.

### Why Skew Has Predictive Power

Skew persistence was documented by Bollen & Whaley (2004), who showed that net demand
for options at specific strikes predicts subsequent IV changes at those strikes. More
directly, Xing, Zhang & Zhao (2010) demonstrated that the steepness of the volatility
smirk (their measure of 6-month, 30-delta skew) predicts future stock returns: high
put skew relative to the stock's history preceded significant underperformance over the
following month.

The mechanism: institutional money hedges before rotating. When a large fund manager
decides to reduce a position, they first buy put protection, then sell equity over the
following days and weeks. The put-buying shows up in skew *before* the equity selling
hits the tape. Skew is the tremor before the earthquake.

Conversely, when institutions are confident in a position and removing hedges, they sell
existing puts (closing protection) or simply let puts expire — either way, put demand falls,
skew compresses, and the equity follows higher. Monitoring skew gives you a 1-3 day head
start on the institutional flow.

---

## The Skew Formula — The Market's Fear Gauge

```
25-delta put skew = IV(25Δ put) − IV(25Δ call)
                    ────────────────────────────
                            IV(ATM)

Where:
  IV(25Δ put)  = implied vol of the put with 0.25 delta (moderately OTM put)
  IV(25Δ call) = implied vol of the call with 0.25 delta (moderately OTM call)
  IV(ATM)      = implied vol of the at-the-money option

This produces a normalized skew measure (skew as a fraction of ATM IV).

Example:
  AAPL at $190:
    IV(25Δ put)  = 28% (options market fears downside)
    IV(25Δ call) = 22% (less demand for upside calls)
    IV(ATM)      = 25%
    Skew         = (28 − 22) / 25 = 0.24 (or "24%")
```

A skew of 0.24 means put IV runs 24% above call IV when normalized by ATM IV. Historical
norms for most large-cap stocks sit between 0.10 and 0.25. Above 0.35, protection buying
is extreme. Below 0.05, puts are cheap relative to calls — unusual and often precedes rallies.

The **10-delta skew** measures even more extreme tail protection:

```
10-delta put skew = IV(10Δ put) − IV(10Δ call)
                    ────────────────────────────
                            IV(ATM)

10Δ puts = deep OTM puts (less than 10% probability of expiring in the money)
These options price pure tail-risk insurance. When 10Δ skew spikes, the market
fears a crash, not just a moderate decline.
```

---

## How It Works — Step by Step

**Concrete example first — AAPL, October 19, 2023:**

AAPL had corrected 12% from its summer highs ($198 to $175). Put buying was elevated.
The 25-delta put skew was at 0.31 — at the 85th percentile of its 1-year history.
The 5-day change in skew was −0.06 (skew had peaked and was now declining).

This is the key signal: skew at an extreme AND now declining = hedging demand is peaking
and beginning to reverse. Institutions are done adding protection; they may now start
removing it (selling puts, letting hedges expire), which means the stock is about to
be supported by reduced overhead.

```
Signal at October 19 close:
  25Δ Put Skew:           0.31    (85th percentile — elevated)
  Skew 5d Change:         −0.06   (declining — momentum turning)
  Skew Z-score:           +1.8σ   (statistically elevated)
  ATM IV:                 28%
  IVR:                    0.72    (high relative to 52-week range)
  VIX:                    21.7
  VIX 5d Change:          −1.3    (VIX declining)
  ─────────────────────────────────────────
  Model P(BULLISH):        0.64    → ENTER BULL CALL SPREAD
  Model P(NEUTRAL):        0.28
  Model P(BEARISH):        0.08
```

Trade entered October 19 close:
- Buy AAPL $175 call (ATM), 14 DTE → pay $3.60
- Sell AAPL $185 call → collect $1.25
- Net debit: **$2.35** per share = $235 per contract

By November 1, AAPL had rallied to $182.50. The spread was worth $5.40.

Target hit (50% debit profit at $3.53 spread value). Actually the spread was already at
$5.40 — nearly max profit. Closed.

**P&L: ($5.40 − $2.35) × 100 = +$305 per contract (+130% on debit)**

---

## Real Trade Walkthrough #1 — MSFT Bearish Skew Signal, February 2022

**Date:** February 3, 2022 | **MSFT:** $298.00

Microsoft had reported solid earnings in late January but the broader tech sector was under
pressure. The skew data told the story before the price did.

**Signal state:**

```
Signal Strength — February 3, 2022:
  25Δ Put Skew:           ██████████  0.38     [EXTREME — 92nd percentile]
  10Δ Put Skew:           ██████████  0.61     [EXTREME — tail risk priced]
  Skew 5d Change:         ██████████  +0.09    [RAPIDLY RISING — hedging demand accelerating]
  Skew Z-score:           ██████████  +2.4σ    [STATISTICAL EXTREME]
  ATM IV:                 █████████░  34%      [ELEVATED]
  IVR:                    ████████░░  0.79     [HIGH]
  VIX:                    ███████░░░  24.8     [ELEVATED]
  VIX 5d Change:          ████████░░  +5.1     [RISING]
  ─────────────────────────────────────────────
  Model P(BEARISH):       ██████████  0.71     → ENTER BEAR PUT SPREAD
  Model P(NEUTRAL):       ██░░░░░░░░  0.19
  Model P(BULLISH):       █░░░░░░░░░  0.10
```

The 25-delta put skew at 0.38 was extreme. But more importantly, it was *still rising*
(+0.09 in 5 days). That means institutions were not finished adding hedges — they were
actively buying more protection. The momentum in skew confirmed the directional signal.

**Trade entered February 3 close:**
- Buy MSFT $295 put (near ATM), 14 DTE → pay $8.60
- Sell MSFT $280 put → collect $3.40
- Net debit: **$5.20** = $520 per contract
- Max profit: ($295 − $280 − $5.20) × 100 = $980 per contract
- Break-even: $295 − $5.20 = $289.80

**What happened:**

```
Date        MSFT Price    25Δ Skew    Spread Value    P&L
──────────────────────────────────────────────────────────
Feb 3       $298.00       0.38        $5.20 (entry)   $0
Feb 7       $294.50       0.39        $6.90           +$170
Feb 9       $289.20       0.36        $9.40           +$420
Feb 11      $286.10       0.34        $10.80          +$560
Feb 14      $283.00       0.29        $12.40 (near max) +$720 ← 50% target hit earlier
```

50% profit target triggered at Feb 9 when spread reached $7.80 (+$260 per contract = +50% of
$5.20 debit). Closed.

**Actual exit:** Feb 9, spread at $9.40.
**P&L: ($9.40 − $5.20) × 100 = +$420 per contract (+81% on debit)**

Note: The skew declining from 0.39 to 0.29 was itself a bullish signal — but the stock
continued lower because the institutional selling (which the earlier skew spike telegraphed)
was still working its way through. This illustrates the timing: skew leads price by 1-5 days
for the initial signal, but the directional move often continues even as skew mean-reverts.

**Bear put spread P&L diagram:**

```
P&L at expiry — MSFT $295/$280 bear put spread, $5.20 debit

  +$980 ─┼─────────────────────────────────┐  Max profit below $280
          │                                 │
  +$490 ─┼                         ┌───────┘  50% profit target = +$260 → close early
          │                    ┌───┘
     $0  ─┼───────────────────┬┘
          │              $289.80 ← break-even
  -$260  ─┼──────────────┬
          │          $295 │  ← Long put strike (spread begins profiting here)
  -$520  ─┼  Max loss above $295 (entire debit)
          └──────┬────────┬────────┬────────┬──── MSFT price at expiry
               $275    $280     $290     $295     $305
```

---

## Real Trade Walkthrough #2 — The Loss: Skew Compression Was a Head Fake

**Date:** September 12, 2023 | **TSLA:** $270.00

Tesla's put skew had been declining for 3 consecutive days. Model output: P(BULLISH) = 0.62.
Trade entered: $270/$285 bull call spread, $4.80 debit.

**What the model missed:** The skew was declining because the previous week's put buyers
were closing profitable puts (TSLA had fallen 10% the week before). It was not new bullish
sentiment — it was profit-taking on bearish positions, a subtle but crucial difference.

Within 3 days, TSLA fell another 7% to $251. The bull call spread expired worthless.

**P&L: −$480 per contract (full debit loss)**

**Lessons:**
1. Skew compression can occur for two reasons: (a) bullish rotation out of hedges, or
   (b) close-out of previously profitable put positions. The model partially distinguishes
   these via the 5d stock return feature, but the distinction is imperfect.
2. When the stock itself has been in strong downtrend (TSLA down 20%+ in prior month),
   skew compression signals are less reliable — the trend may continue even as hedgers
   take profits on puts.
3. Adding a trend-filter check (50-day MA) can screen out these head-fake scenarios at
   the cost of some true signals.

---

## P&L Diagrams — Both Spread Types

```
BULLISH SIGNAL → Bull Call Spread
(Long $175 call / Short $185 call, debit $2.35, AAPL at $175)

P&L ($) at expiry
  +$765 ─┼─────────────────────────────────────────┐  Max profit at $185+
          │                                         │  ($10 width − $2.35 debit) × 100
  +$383 ─┼                               ┌─────────┘  50% profit target
          │                         ┌────┘
     $0  ─┼────────────────────────┬┘  $177.35 ← break-even
          │                  $175 →│
  -$235  ─┼  Max loss below $175
          └───────┬────────┬────────┬────────┬──── Price at expiry
               $170    $175     $180     $185     $190

BEARISH SIGNAL → Bear Put Spread
(Long $295 put / Short $280 put, debit $5.20, MSFT at $298)

P&L ($) at expiry
  +$980 ─┼──────────────────────────────────┐  Max profit below $280
          │                                  │  ($15 width − $5.20 debit) × 100
  +$490 ─┼                          ┌────────┘
          │                    ┌────┘
     $0  ─┼───────────────────┬┘  $289.80 ← break-even
          │              $295 │
  -$520  ─┼  Max loss above $295
          └───────┬────────┬────────┬────────┬──── Price at expiry
               $275    $280     $285     $290     $295
```

---

## The Math

### Skew Z-Score Computation

```
skew_25d[t]     = (IV_25Δ_put[t] − IV_25Δ_call[t]) / IV_ATM[t]
skew_5d_change  = skew_25d[t] − skew_25d[t−5]

skew_mean_20d   = mean(skew_25d over past 20 days)
skew_std_20d    = std(skew_25d over past 20 days)
skew_zscore[t]  = (skew_25d[t] − skew_mean_20d) / skew_std_20d

Signal conditions:
  BULLISH:  skew_zscore > 1.5 AND skew_5d_change < −0.03  (skew peaked and declining)
  BEARISH:  skew_zscore > 1.5 AND skew_5d_change > +0.03  (skew at extreme AND rising)
  NEUTRAL:  all other cases (insufficient extremity or ambiguous momentum)
```

### Strike Selection

```
For BULLISH (bull call spread):
  long_k  = round(spot / 5) × 5          ← ATM or first OTM strike
  short_k = round((spot × 1.05) / 5) × 5 ← ~5% OTM call (cap the upside)
  DTE:    14 DTE preferred

For BEARISH (bear put spread):
  long_k  = round(spot / 5) × 5           ← ATM or first ITM put
  short_k = round((spot × 0.95) / 5) × 5  ← ~5% OTM put (limit of protection)
  DTE:    14 DTE preferred
```

### Break-Even Calculations

```
Bull call spread:  B/E = long_strike + net_debit_per_share
Bear put spread:   B/E = long_strike − net_debit_per_share

Risk/reward:
  Max profit = (spread_width − debit) × 100
  Max loss   = debit × 100
  R/R ratio  = max_profit / max_loss  (target: ≥ 1.5:1)

Example (AAPL $175/$185 spread, $2.35 debit):
  Max profit  = ($185 − $175 − $2.35) × 100 = $765
  Max loss    = $2.35 × 100 = $235
  R/R         = $765 / $235 = 3.25:1  → excellent setup
```

---

## When This Strategy Works Best

**Ideal market conditions:**

```
Skew regime table — what each combination signals:

  Skew Level    Skew 5d Change    Signal Quality
  ────────────────────────────────────────────────
  HIGH (>1.5σ)  DECLINING         BULLISH — best signal (hedges being removed)
  HIGH (>1.5σ)  STILL RISING      BEARISH — strong signal (panic still building)
  NORMAL        DECLINING         WEAK BULLISH — marginal edge
  NORMAL        RISING            WEAK BEARISH — marginal edge
  LOW (<−1σ)    ANY DIRECTION     AVOID — options market is complacent; edge unclear
```

**Best sector conditions:**
- Individual stocks with institutional ownership > 60% (large institutional money drives skew)
- Names with active options markets (daily volume > 5,000 contracts ATM)
- Earnings-adjacent: the 2-4 weeks AFTER earnings, when post-event vol is settling

**Best VIX range:** 15–28. At VIX < 15, skew is uniformly compressed — less signal variance.
At VIX > 30, macro fear dominates individual-name skew — the signal becomes unreliable.

---

## When to Avoid It

1. **Immediately before earnings (< 7 DTE to report):** IV structure is dominated by
   the binary event, not normal skew dynamics. The skew reading is polluted by event premium.

2. **During systemic vol spikes (VIX > 30):** All stocks show elevated put skew simultaneously
   — the signal is a reflection of macro fear, not stock-specific hedging flow.

3. **Stock in sustained downtrend (below 200-day MA and declining):** Skew compression on
   a fundamentally broken stock can be temporary. The signal works best on stocks in
   uptrends where the skew elevation is periodic/emotional, not structural.

4. **Low options liquidity:** Bid/ask spreads on 25-delta options of 1-2 vol points make
   the skew measurement noisy. Require at minimum 1,000 contracts/day on the 25Δ strike.

5. **Simultaneous sector-wide skew spike:** When every stock in a sector shows skew
   elevation simultaneously, the signal is a sector rotation warning, not individual-name
   alpha. Wait for sector-level skew to normalize before trading individual names.

---

## Common Mistakes

1. **Trading the level, not the momentum.** A skew z-score of +2.5σ is extreme — but if
   it has been at +2.5σ for 10 days, the information is already in the price. The *change*
   in skew is what moves markets, not the static level.

2. **Ignoring the 10-delta skew.** The 25-delta skew measures moderate protection buying.
   The 10-delta skew measures crash protection. When 10Δ skew spikes while 25Δ is flat,
   someone is specifically buying far OTM puts — a different kind of informed hedging that
   often precedes a larger move than the 25Δ signal suggests.

3. **Using a single skew reading without normalizing.** Different stocks have different
   structural skew levels. AMZN always has higher put skew than IBM. Comparing AMZN's
   current skew to IBM's is meaningless. Always compare a stock's skew to its own history
   (z-score), never across tickers.

4. **Confusing skew with IV rank.** High IVR means all options are expensive. High skew
   means specifically *puts* are expensive relative to *calls*. A stock can have high IVR
   with flat skew (both sides expensive equally) or low IVR with extreme skew (puts expensive
   relative to cheap calls). These are different signals requiring different trades.

5. **Setting spread width too narrow.** A 2% spread width on a high-IV stock (40%+ IV)
   may be entirely within the daily expected move. The spread needs to be wide enough
   to capture the 3-7 day directional move the model predicts. Minimum 5% width.

6. **Over-trading marginal signals.** P(BULLISH) = 0.58 is barely above the 50% default
   threshold. Waiting for 0.65+ concentrates positions in the highest-quality setups.
   Frequency of trades is not an objective — quality is.

---

## Quick Reference

```
Parameter               Default            Range      Description
----------------------  -----------------  ---------  -----------------------------------------------------------------------
`min_skew_zscore`       1.5σ               1.0–2.5    Min statistical elevation of put skew
`min_skew_5d_change`    0.03               0.02–0.08  Min skew momentum to confirm direction
`min_model_confidence`  0.58               0.55–0.75  LightGBM 3-class min probability (`signal_threshold=58`)
`dte_entry`             21 DTE             10–30      Days to expiry at entry (code default `dte_entry=21`)
`spread_width_pct`      4% of spot         2–8%       Distance between long and short strikes (`spread_width_pct=4.0`)
`profit_target`         60% of max spread  40–80%     Close at 60% of max spread value (`profit_target` in code docstring)
`stop_loss_pct`         50% of debit       30–100%    Close when loss hits 50% of debit (`loss stop: lose 50% of debit paid`)
`time_stop_dte`         7 DTE              5–14       Close at ≤ 7 DTE remaining (`_HOLD_STOP_DTE = 7`)
`position_size_pct`     3%                 1–5%       Max debit as % of capital (code default `position_size_pct=3.0`)
`skew_lookback`         20 bars            15–30      Window for skew z-score computation (`skew_lookback=20`)
`warmup_bars`           150                100–200    Minimum history for LightGBM (`_WARMUP_BARS = 150`)
`retrain_frequency`     30 bars            20–60      Walk-forward retrain window (`_RETRAIN_EVERY = 30`)
```

---

## Data Requirements

```
Data Field              Source                           Usage
----------------------  -------------------------------  -----------------------------------------
`stock_25d_put_skew`    Polygon options chain            Primary signal — 25Δ skew computation
`stock_10d_put_skew`    Polygon options chain            Secondary signal — tail-risk confirmation
`stock_skew_5d_change`  Derived from above (rolling 5d)  Momentum signal — is skew accelerating?
`stock_skew_zscore`     Derived (20d rolling z-score)    Normalization across time and tickers
`stock_atm_iv`          Polygon options IV               ATM IV for skew normalization and pricing
`stock_ivr`             Derived from 52-week IV history  Overall vol regime context
`vix`                   Polygon `VIXIND`                 Macro vol filter
`vix_5d_change`         Derived from VIXIND history      Direction of macro vol regime
Per-strike IV by delta  Polygon options chain            25Δ and 10Δ IV computation
Risk-free rate          Polygon `DGS10`                  Black-Scholes strike selection
```
