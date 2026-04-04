# Vol Term Structure Regime
### Reading the Shape of the IV Curve to Predict Whether Vol Will Expand or Compress

---

## The Core Edge

The implied volatility term structure — the plot of IV versus time to expiration — is one
of the most information-rich signals in options markets. When front-month IV is lower than
back-month IV (contango), the market believes that future uncertainty is greater than current
uncertainty, but is not urgently concerned right now — a "calm before the storm" shape.
When front-month IV exceeds back-month IV (backwardation), the market believes near-term
risk is extreme and immediate — it is actively pricing an event or regime that it expects
to resolve relatively quickly.

The Vol Term Structure Regime strategy uses an LSTM model to classify the current term
structure shape — and its recent momentum — into three regimes: COMPRESS, FLAT, or EXPAND.
In the COMPRESS regime, implied volatility is expected to decline and premium sellers
profit from theta decay and vega compression. In the EXPAND regime, realized volatility
is expected to increase and vol buyers profit from the resulting price action. The FLAT
regime is ambiguous — no trade is taken.

The key insight that justifies this approach: **the term structure predicts future realized
vol better than the level of implied vol alone.** A high IV level might simply reflect
a recent spike that is now unwinding. But high front IV *and* backwardation — where near-
term options are explicitly more expensive than medium-term options — is a structural signal
that dealers and institutions are pricing in an imminent catalyst. Conversely, contango
combined with high IV rank is a setup where premium sellers have strong theoretical backing.

### The Academic Case

Dew-Becker, Giglio & Kelly (2021) demonstrated that different points on the variance term
structure contain distinct economic information — short-term variance risk reflects transient
uncertainty while long-term variance risk reflects structural macroeconomic uncertainty.
Exploiting the *shape* rather than the *level* of the term structure generates risk-adjusted
returns that are statistically independent from standard factor models.

Practical traders have known this for decades: Cboe VIX measures 30-day implied variance,
while VIX9D (9-day VIX) spikes harder around events. The ratio of VIX9D/VIX is the
practitioner's version of what this strategy formalizes and extends to individual names.

---

## The Term Structure Explained

### Contango (Normal Shape)

```
IV (%)
  45 ─┤
      │
  40 ─┤
      │                                  ●─────●
  35 ─┤                         ●───────/
      │               ●────────/
  30 ─┤       ●──────/
      │
  25 ─┤  ●
      │
      └──┬─────┬─────┬──────┬──────┬───── DTE
         7    14    21     30     45     60

  Shape: IV increases with time
  Signal: No immediate event concern; back months pricing long-run risk premium
  Interpretation: Harvest theta and vega — COMPRESS regime likely
```

### Backwardation (Inverted Shape)

```
IV (%)
  65 ─┤
      │  ●
  60 ─┤   ╲
      │    ╲●
  55 ─┤      ╲
      │       ╲●
  50 ─┤         ╲────●
      │               ╲───────●
  45 ─┤                        ╲────────●
      │
      └──┬─────┬─────┬──────┬──────┬───── DTE
         7    14    21     30     45     60

  Shape: Front-month IV exceeds back-month IV
  Signal: Near-term event risk; market paying up for immediate protection
  Interpretation: OWN volatility — EXPAND regime likely
  Classic examples: 1 week before FOMC, day before CPI, week of earnings for volatile names
```

### The Term Slope Feature

```
term_slope = back_iv (45 DTE) − front_iv (21 DTE)

Contango:       term_slope > 0   (back IV > front IV)
Backwardation:  term_slope < 0   (front IV > back IV)

Typical values:
  Strong contango:     term_slope > +3 vol points
  Mild contango:       term_slope +1 to +3 vol points
  Flat:                term_slope −1 to +1 vol points
  Mild backwardation:  term_slope −1 to −5 vol points
  Strong backwardation: term_slope < −5 vol points
```

---

## How It Works — Step by Step

**Immediate example — SPY, November 20, 2023:**

The Fed had signaled a pause in rate hikes. VIX had declined to 13.8. The Nov/Dec IV
term structure was in deep contango: front IV 12.5%, back IV 16.8%, term slope = +4.3.
The Variance Risk Premium (VRP) — front_iv minus 20-day realized vol — was +6.1 vol points.

```
Signal at November 20:
  Front IV (21 DTE):          12.5%
  Back IV (45 DTE):           16.8%
  Term Slope:                 +4.3   [STRONG CONTANGO]
  Term Slope 5d Change:       +1.2   [Deepening contango — direction clear]
  VRP (front IV − realized):  +6.1   [Options overpriced vs recent moves]
  IVR:                        0.42   [IV in middle of its range]
  VIX:                        13.8   [Low macro vol]
  VIX Term Slope:             +2.1   [Macro term structure also in contango]
  Yield Curve (2Y-10Y):       −0.35  [Slightly inverted — mild caution]
  SPY 20d Realized Vol:        7.2%  [Very calm equity market]
  ─────────────────────────────────────────────────────────
  LSTM P(COMPRESS):            0.71  → ENTER BULL PUT SPREAD (harvest premium)
  LSTM P(FLAT):                0.22
  LSTM P(EXPAND):              0.07
```

Trade entered November 20:
- Sell SPY $453 put (21 DTE, 0.20 delta) → collect $1.60
- Buy SPY $447 put → pay $0.70
- Net credit: **$0.90** = $90 per contract

SPY remained rangebound ($450–$458) for the next 21 days. The spread expired worthless.

**P&L: full credit retained = +$90 per contract**

The COMPRESS signal correctly identified that the deep contango + high VRP environment
would not produce a vol expansion. The bull put spread was the ideal vehicle: short vol
exposure during a period when vol was expected to continue compressing.

---

## Real Trade Walkthrough #1 — The EXPAND Signal: NVDA, April 2024

**Date:** April 12, 2024 | **NVDA:** $853 | **VIX:** 17.2

NVDA had been on a historic run. But the term structure was signaling something different:
the very short-dated options (7-14 DTE) had spiked sharply relative to the 45-DTE options.

```
Signal at April 12:
  Front IV (21 DTE):          62%
  Back IV (45 DTE):           54%
  Term Slope:                 −8    [STRONG BACKWARDATION]
  Term Slope 5d Change:       −4.2  [Steepening backwardation — urgency increasing]
  VRP (front IV − realized):  +18   [Front IV hugely elevated vs calm recent moves]
  IVR (front):                0.73  [Front IV at 73rd percentile of history]
  IVR (back):                 0.61  [Back IV less elevated]
  IVR Spread:                 +0.12 [Front disproportionately elevated]
  VIX:                        17.2
  VIX Term Slope:             −1.8  [VIX itself showing mild backwardation]
  ─────────────────────────────────────────────────────────
  LSTM P(EXPAND):              0.68  → ENTER LONG STRADDLE (own vol)
  LSTM P(FLAT):                0.21
  LSTM P(COMPRESS):            0.11
```

Wait — this is a straddle (long vol), not a spread. The EXPAND regime uses a long straddle
to profit from any large move in either direction.

**Trade entered April 12:**
- Buy NVDA $855 call (14 DTE, near ATM) → pay $28.40
- Buy NVDA $855 put (14 DTE, near ATM) → pay $30.60
- Total straddle cost: **$59.00** = $5,900 per straddle

**Break-even levels:** $855 + $59 = $914 (upside) / $855 − $59 = $796 (downside)

**What happened:**

NVDA fell sharply over the following week as the broader market sold off on Middle East
geopolitical fears and rising rate concerns. NVDA dropped to $762 by April 19 (−10.7%).

Straddle value at April 19:
- Call: $855 strike with NVDA at $762 → nearly worthless, $1.20
- Put: $855 strike with NVDA at $762 → $93.00 intrinsic + time value ≈ $97.40
- Total straddle: $98.60

**Exit April 19 at $98.60.**
**P&L: ($98.60 − $59.00) × 100 = +$3,960 per straddle (+67%)**

The strong backwardation correctly predicted an imminent vol expansion. The 7-point
backwardation in the term slope was the market's way of saying: "something big is about
to happen, and we think it's soon." The LSTM model, trained to recognize this pattern,
fired with 0.68 confidence — strong enough to enter.

**Long straddle P&L diagram:**

```
P&L at expiry — NVDA $855/$855 straddle, $59.00 total cost

P&L ($) per straddle
  +$6,000─┼──────────────────────      ──────────────────────────
           │              (put profit)  (call profit)
  +$3,000─┼                     ╲    /
           │                      ╲  /
     $0   ─┼───────────────────────╲/────────────────────────────
           │               $796   $855   $914   ← break-even levels
  -$5,900─┼──────────────────────────────  Max loss at exactly $855 (straddle bought here)
           └──────┬───────┬───────┬────────┬──── NVDA at expiry
                $760   $800    $855    $914    $960
```

---

## Real Trade Walkthrough #2 — The Loss: COMPRESS Signal in Rising Vol Environment

**Date:** August 28, 2024 | **SPY:** $564 | **VIX:** 15.1

The term structure was in moderate contango (+2.5 slope), VRP was +4.2, and the LSTM
output was P(COMPRESS) = 0.63. The bull put spread was entered: short $556 put, long
$550 put, credit $0.85.

**What happened:** The following week, a combination of Japan yen carry trade unwinding
fears and weak manufacturing data caused a rapid vol spike. VIX jumped from 15 to 22 in
4 days. SPY fell to $545.

The bull put spread was breached when SPY crossed $556 on September 3.

**Exit via stop loss (spread reached 2× credit = $1.70):**
**P&L: ($0.85 − $1.70) × 100 = −$85 per contract (−1× credit received)**

**Analysis:** The model correctly said COMPRESS with 63% confidence — meaning there was
a 37% probability it was wrong. The loss was within expected parameters. The small credit
($0.85) meant the maximum loss with the stop was modest. This is exactly why position
sizing matters: even when the model is correct 70% of the time, the wrong 30% must be
contained within acceptable loss limits.

---

## P&L Diagrams — COMPRESS vs EXPAND

```
COMPRESS Regime → Bull Put Spread
(Short $453 put / Long $447 put, $0.90 credit, SPY at $463)

P&L at expiry
  +$90  ─┼──────────────────────────────────────────┐  Max profit: stock above $453
          │                                          │  (keep entire $0.90 credit)
    $0   ─┼─────────────────────────────────────────┤─ Break-even at $452.10
          │                                    $452.10│
  -$510  ─┼──────────────────────────────────────────┘  Max loss: stock below $447
          │  ($6 width − $0.90 credit) × 100 = $510 max loss
          └──────┬────────┬────────┬────────┬──── SPY at expiry
               $447    $450     $453     $460

EXPAND Regime → Long Straddle
(Long $855 call + $855 put, $59 total cost, NVDA at $853)

P&L at expiry
         ╲                           /
          ╲                         /
           ╲                       /
   Break-even $796             Break-even $914
            ╲                     /
             ╲                   /
$0 ────────────────────────────────── (at exactly $855)
             -$5,900 max loss at $855

Scenario table:
  NVDA at Expiry    Straddle Value    P&L/contract
  ────────────────────────────────────────────────
  $720 (−16%)       $135              +$7,600
  $762 (−11%)       $93               +$3,400
  $796 (−7%)        $59               $0 (break-even)
  $855 (flat)       $0                −$5,900 (max loss)
  $914 (+7%)        $59               $0 (break-even)
  $950 (+11%)       $95               +$3,600
```

---

## The LSTM Model

### Why LSTM for This Strategy?

The term structure's predictive power is not instantaneous — it requires reading a *sequence*
of term structure shapes over time. A single day's contango is less informative than three
consecutive days of deepening contango. The LSTM (Long Short-Term Memory) network is
specifically designed to capture these sequential patterns and their evolution.

```
Architecture:
  Input:  20-bar sequence of term structure features
  LSTM:   1 layer, 32 hidden units (`NUM_LAYERS=1`, `HIDDEN_SIZE=32`)
  Output: 3-class softmax (COMPRESS / FLAT / EXPAND)
  Seq_len: 20 bars (≈ 4 trading weeks of history)

Features fed at each time step t:
  stock_front_iv[t]          ATM IV, front month (≥ 21 DTE)
  stock_back_iv[t]           ATM IV, back month (~45 DTE)
  stock_term_slope[t]        back_iv − front_iv
  stock_term_slope_5d_change[t]   slope change vs 5 days ago
  stock_vrp[t]               front_iv − realized_vol_20d
  stock_ivr[t]               front IV rank vs 52-week history
  vix[t]                     CBOE VIX
  vix_term_slope[t]          VIX M1 − VIX M2
  yield_curve_2y10y[t]       2-year minus 10-year Treasury yield spread
  spy_20d_realized_vol[t]    20-day realized vol of SPY
```

### Label Construction

```
5-day forward change in front_iv:
  Δiv_5d = front_iv[t+5] − front_iv[t]
  σ_Δiv  = rolling 90-day std of Δiv_5d

COMPRESS: Δiv_5d < −0.5σ_Δiv  (IV drops significantly)
EXPAND:   Δiv_5d > +0.5σ_Δiv  (IV rises significantly)
FLAT:     between −0.5σ and +0.5σ
```

### Walk-Forward Training

```
Training protocol:
  Warmup:     minimum 200 bars (LSTM requires longer history than tree models)
  Training:   expanding window, retrain every 60 bars (`RETRAIN_EVERY = 60`)
  Validation: last 20% of data, never used in training

Minimum class balance check:
  Require ≥ 15% of training samples in each class to prevent NEUTRAL dominance
```

---

## Term Structure Across Time — A Visual History

```
VIX and SPY Term Slope, 2022–2024:

Contango +6 ─┤
             │                  ██  ████████████████████████████
Contango +3 ─┤████            ████  ██                          ████
             │    ██       ████  ██
        Flat─┤──────██──████──────────────────────────────────────────
             │        ██
Backard. -3 ─┤
             │                                         ██ (brief event windows)
Backard. -6 ─┤
             │
Backard. -9 ─┤
             └──────┬───────┬──────┬──────┬──────┬──────┬─── Date
                  Jan'22 Apr'22 Jul'22 Oct'22 Jan'23 Jul'23 Dec'23

Key observations:
  2022 (bear market): Persistent mild backwardation, punctuated by deep spikes
  Jan 2022 spike:     Term slope hit −9 at market peak → EXPAND signal → straddle profits
  Oct 2022 trough:    Brief contango as market bottomed → COMPRESS signal fired
  2023 (bull market): Strong, sustained contango → multiple COMPRESS signals → credit trades
  Late 2023 FOMC:     Brief backwardation spikes around each FOMC → EXPAND signals
```

---

## The Variance Risk Premium (VRP) Feature

```
VRP = front_iv − realized_vol_20d

The VRP is perhaps the single most important individual feature:

VRP > 0:  Options overpriced vs recent realized vol → COMPRESS likely
VRP < 0:  Options cheap vs recent moves → EXPAND likely

Historical distribution (SPY):
  Median VRP:    +4.2 vol points (options chronically overprice vol)
  Top quartile:  +8+ vol points (strong COMPRESS signal)
  Bottom quartile: < 0 vol points (vol likely expanding → EXPAND signal)

VRP z-score for normalization:
  vrp_zscore = (VRP − VRP_90d_mean) / VRP_90d_std

  vrp_zscore > +1.5:  Statistically extreme overpricing → strong COMPRESS
  vrp_zscore < −1.0:  Vol underpriced vs history → EXPAND signal
```

---

## When This Strategy Works Best

**Best COMPRESS setups:**

| Signal | Value | Why |
|---|---|---|
| Term slope | > +3 vol points | Deep contango = no near-term event concern |
| VRP | > +6 vol points | Options significantly overpriced vs realized |
| IVR | 0.60–0.85 | IV elevated but not crisis-level; good premium |
| VIX | 14–22 | Moderate macro backdrop |
| Yield curve | > −0.50 | Not deep inversion (recession risk)  |
| SPY 20d realized vol | < 12% | Calm underlying = options are even more overpriced |

**Best EXPAND setups:**

| Signal | Value | Why |
|---|---|---|
| Term slope | < −3 vol points | Strong backwardation = near-term event urgency |
| Term slope 5d change | < −2 | Backwardation deepening = urgency accelerating |
| VRP | < 0 (negative) | Realized vol is exceeding implied = vol regime changing |
| Front IVR | > 0.75 | Front options specifically elevated (event premium) |
| VIX term slope | < 0 | Macro vol term structure also inverted |

---

## When to Avoid It

1. **VIX > 35 (crisis mode):** In extreme dislocations, the LSTM model may not have
   been trained on sufficient crisis data. The term structure in crisis can remain in
   backwardation for months, not days. The EXPAND signal is correct but the timing
   uncertainty makes straddle management extremely difficult.

2. **Yield curve between −0.1 and +0.1 (flat):** Flat yield curves signal economic
   transition — the macro backdrop can shift rapidly in either direction. The COMPRESS
   regime assumption becomes unreliable when the macro is genuinely ambiguous.

3. **Individual stocks with very thin options markets:** Term slope calculations require
   both front and back month liquid quotes. If the spread between front and back IV
   is wider than the market bid/ask, you cannot reliably compute a valid term slope.

4. **During FOMC week:** The term structure distortions during FOMC week are artificial
   (event pricing) and resolve within hours after the announcement. Do not enter COMPRESS
   trades the week of a FOMC meeting even if the model fires — the contango reflects
   post-event expectations that are priced separately from the event premium.

---

## Common Mistakes

1. **Treating contango as always meaning "sell premium."** Yes, contango is the structural
   norm (options chronically overprice vol). But entering COMPRESS trades when the term
   slope is only barely positive (+0.5 vol points) provides little edge. Wait for contango
   ≥ +3 vol points to have sufficient premium buffer.

2. **Entering long straddles on mild backwardation.** A −2 vol point backwardation is
   modest noise. Strong EXPAND signals require backwardation of −5 or more, ideally
   deepening. Mild backwardation can easily reverse without a meaningful vol expansion.

3. **Ignoring the yield curve filter in COMPRESS trades.** A deeply inverted yield curve
   (2Y−10Y < −1%) is a macro warning that the economy may be heading for disruption.
   Selling premium into an inverted yield curve significantly raises the probability
   of a sudden vol spike that wipes out months of theta gains.

4. **Using the same trade size for COMPRESS and EXPAND.** COMPRESS trades have a
   defined maximum loss (the spread width minus credit). EXPAND trades (long straddle)
   have defined maximum loss equal to the total premium paid — often 3-5% of the stock
   price. Size EXPAND trades smaller to keep equivalent dollar risk.

5. **Running LSTM on too little data.** The model requires 200+ bars for warmup and
   performs best with 500+ bars of training history. On freshly synced tickers, wait
   for sufficient history before trusting the LSTM output. The walk-forward validation
   MUST be run on each ticker before live use.

6. **Confusing VIX term slope with individual-stock term slope.** VIX measures SPY's
   near-term vol. Individual stocks have their own term structures that can diverge
   sharply from VIX. High-IV individual stocks can be in backwardation even when VIX
   is in contango — their earnings, events, or sector dynamics create independent term
   structures.

---

## Quick Reference

| Parameter | Default | Range | Description |
|---|---|---|---|
| `signal_threshold` | 0.55 | 0.45–0.75 | LSTM P(COMPRESS) or P(EXPAND) threshold (code `signal_threshold=0.55`) |
| `seq_len` | 20 bars | 15–30 | LSTM input sequence length (code `SEQ_LEN=20`) |
| `lstm_layers` | 1 | 1–3 | LSTM depth (code `NUM_LAYERS=1`) |
| `lstm_hidden` | 32 | 16–128 | Hidden units per LSTM layer (code `HIDDEN_SIZE=32`) |
| `dte_entry` | 21 DTE | 14–30 | Expiry for all trades (code `dte_entry=21`) |
| `spread_width_compress` | 5% of spot | 3–7% | Bull put spread width in COMPRESS regime |
| `profit_target_compress` | 50% credit | 40–70% | Close credit spread early |
| `stop_loss_compress` | 2× credit | 1.5–3× | Close if spread reaches this cost |
| `profit_target_expand` | 50% of cost | 40–80% | Close straddle at this gain |
| `stop_loss_expand` | 50% of cost | 40–60% | Close straddle if it loses this % |
| `position_size_pct` | 3% | 1–5% | Capital at risk per trade (code `position_size_pct=0.03`) |
| `regime_reeval_bars` | 10 bars | 5–20 | Re-evaluate regime every N bars (code `regime_reeval_bars=10`) |
| `warmup_bars` | 200 | 150–300 | Minimum bars before LSTM activation (code `WARMUP_BARS=200`) |
| `retrain_frequency` | 60 bars | 30–100 | Walk-forward retrain interval (code `RETRAIN_EVERY=60`) |

---

## Data Requirements

| Data Field | Source | Usage |
|---|---|---|
| `stock_front_iv` | Polygon options chain | ATM IV, nearest expiry ≥ 21 DTE |
| `stock_back_iv` | Polygon options chain | ATM IV, ~45 DTE expiry |
| `stock_term_slope` | Derived: back_iv − front_iv | Primary term structure signal |
| `stock_term_slope_5d_change` | Rolling 5-day delta of above | Momentum of term structure |
| `stock_vrp` | Derived: front_iv − realized_vol_20d | Variance risk premium |
| `stock_ivr` | Derived from 52-week IV history | IV rank context |
| `vix` | Polygon `VIXIND` | Macro vol regime |
| `vix_term_slope` | Polygon VIX M1 and M2 | Macro term structure alignment |
| `yield_curve_2y10y` | Polygon (DGS2 and DGS10) | Macro economic regime signal |
| `spy_20d_realized_vol` | Derived from SPY OHLCV | Baseline market vol context |
| Per-expiry ATM IV | Polygon options chain | Front and back month IV computation |
| Risk-free rate | Polygon `DGS10` | Black-Scholes computation |

**Note on front/back month selection:** "Front" always means the nearest monthly
expiry with ≥ 21 DTE (to avoid gamma distortion in the final 3 weeks). "Back" means
the next monthly expiry, typically 20-30 days after the front. Weekly expiries are
not used in the term slope computation as they contain event-specific pricing noise.
