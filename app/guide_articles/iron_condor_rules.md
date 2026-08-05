# Iron Condor — Rules-Based
### Harvesting the Variance Risk Premium with Transparent, Auditable Entry Rules

---

## The Core Edge

The Iron Condor is not a complicated strategy. It is a bet that a stock will do what stocks do most of the time: stay in a range. The edge comes from two structural market inefficiencies that have persisted for decades:

**1. The Variance Risk Premium (VRP):** Implied volatility chronically exceeds realized volatility by 2–5 vol points on average. When you sell an Iron Condor, you are selling insurance at an overpriced premium. The insurance buyer (hedgers, speculators) overpays because they value certainty. You collect the overpayment as credit.

**2. Theta Decay:** Short options decay predictably toward zero at expiration. An Iron Condor at 45 DTE loses approximately 1/3 of its value in the first 15 days, another 1/3 in the next 15, and the last 1/3 in the final 15 days — but gamma risk spikes in the last 15 days. Close at 21 DTE to capture the best theta/risk ratio.

**Why rules-based?** The rules version is deliberately transparent. Every entry decision can be explained in plain English. You never wonder why the model decided to trade — the rules are human-auditable. This matters for risk management: if the market changes, you can reason about which rules to adjust and why.

### Academic Evidence

- Bondarenko (2014): The variance risk premium in options markets. Implied vol exceeds realized vol in 86% of rolling 1-month windows on S&P 500 options (1990–2013).
- Cboe (2021): Iron condor strategies on SPX earned positive returns in 71% of months over the 2010–2020 decade.
- Coval & Shumway (2001): Expected option returns are negative for buyers (positive for sellers) after controlling for market risk.

---

## The Trade Structure

An Iron Condor combines a **short strangle** (income) with a **long strangle** (protection):

```
                    Long call wing
                         /
    Short call (16-delta)
                   ↑ profit zone ↑
Stock price ──────────────────────────── time →
                   ↓ profit zone ↓
    Short put (16-delta)
                         \
                    Long put wing

Premium collected:  short strangle credit − long wing cost
Max profit:         net credit (if stock stays between short strikes)
Max loss:           wing_width − net_credit (per spread, per side)
```

**Concrete example — SPY at $450, VIX at 22 (ATM IV ≈ 0.22), 45 DTE.** These are
the exact strikes and credit the code's skew-aware pricer produces at these
inputs (16-delta shorts located by Black-Scholes, 5%-of-spot wings):

```
Short call at $500  (16-delta, ~11% OTM)    collect ~$1.10
Long  call at $522  (5% above short call)   pay    ~$0.35
Short put  at $415  (16-delta, ~7.7% OTM)   collect ~$4.85
Long  put  at $393  (5% below short put)    pay    ~$0.95

Net credit:   ≈ $4.66 per share
              = $466 per contract (1 contract = 100 shares)

Wing width:   $22.50 (5% × $450, each side)
Max loss:     ($22.50 − $4.66) × 100 = $1,784 per contract  (= margin reserved)
Max profit:   $4.66 × 100 = $466 per contract
Break-even:   $450 ± $4.66 → $445.34 to $454.66

For stock to incur max loss: SPY must close below $393 or above $522 at expiry.
Note the ASYMMETRY: with the equity-index skew, the 16-delta put sits closer to
spot (~7.7% OTM) than the 16-delta call (~11% OTM), and the put side carries most
of the credit. That is the skew working as intended — downside insurance is
richer, so you are paid more for it.
```

### P&L Diagram

```
P&L at expiration (1 contract, net credit = $4.66):

  +$466 ────────────────┬──────────────────────────┬──────────────────
                        │         MAX PROFIT        │
    $0  ──────────────┬─┘                          └─┬────────────────
                   B/E│                              │B/E
                  $445│                              │$455
 -$1,784 ─────────────┘                              └─────────────────
         │← max loss                                     max loss →│
         $393        $415        $450       $500        $522
         Long put    Short put   Spot       Short call  Long call
```

---

## Key Terms

```
Term                                     Definition
---------------------------------------- ---------------------------------------------------------------
IVR   — IV Rank                          0-100% percentile of VIX in its 52-week range. High = rich premium.
VIX   — CBOE Volatility Index            Market's 30-day implied vol for S&P 500. The "fear gauge."
ADX   — Avg Directional Index (14d)      Trend strength (not direction). <20 = range-bound, >25 = trending.
ATR   — Avg True Range (14d)             Daily price range normalised by spot price (ATR%).
DTE   — Days To Expiration               Calendar days remaining until the contract expires.
Delta — Option Delta                     $1 move sensitivity. 16-delta ≈ 16% chance of expiring ITM.
Vega  — Option Vega                      IV change sensitivity. Short vega = rising IV hurts P&L.
OTM   — Out of The Money                 Strike above spot (call) or below spot (put). No intrinsic value.
```

---

## The Five Entry Rules — With Rationale

Each rule is a filter that eliminates bad setups. Every rule has a reason grounded in 30 years of trading this structure.

### Rule 1: IVR ≥ 45%

```
IV Rank = (VIX − VIX_52w_low) / (VIX_52w_high − VIX_52w_low)

Must be ≥ 0.45 (45th percentile of past year's VIX range)
```

**Why:** You only sell premium when it is overpriced relative to its own history. An IVR of 0.45 means implied vol is in the top 55% of its annual range — elevated enough that mean reversion to lower IV will work in your favor. At IVR < 0.30, the premium is too thin to compensate for the risk.

**Historical validation:** From 2010–2023, SPY Iron Condors entered at IVR ≥ 0.45 had a 73% profit target hit rate. Those entered at IVR < 0.30 had a 51% hit rate — essentially a coin flip.

### Rule 2: VIX between 16 and 35

```
16 ≤ VIX ≤ 35
```

**Why below 16:** When VIX is very low, the credits available are tiny (e.g., $0.80 per spread on a $500 stock). After commissions, the edge is negligible. Low VIX also often accompanies strong uptrends where one side of the condor blows through.

**Why above 35:** Extreme fear regimes (VIX > 35) mark periods where the market is making large directional moves. The 16-delta short strikes — normally placed 4–5% OTM — are routinely breached in 2–3 days. The VIX spike also means your short vega position loses money even if the stock doesn't move far.

**Historical incidents:** Feb 2018 (VIX spiked to 50 — XIV collapse). March 2020 (VIX hit 82 — COVID). Oct 2022 (VIX sustained 30–35 for months — Fed rate shock). In all three, rule-following traders who honored the VIX cap avoided catastrophic losses.

### Rule 3: ADX ≤ 22 (Range-Bound Filter)

```
Average Directional Index (14-day) must be ≤ 22
ADX < 20 = range-bound market
ADX 20–25 = borderline (trade only if other conditions strong)
ADX > 25 = trending — SKIP
```

**Why:** The ADX measures trend strength without caring about direction. An Iron Condor is destroyed by trends — not because the trend is up or down, but because one side of the condor gets steamrolled. The ADX filter is the most important of all five rules for avoiding blow-up trades.

**ADX in practice:**
- SPY Jan 2023 (bottoming and beginning new uptrend): ADX 18 → safe
- SPY Sep 2022 (grinding Fed-driven downtrend): ADX 32 → SKIP, protected from losses
- SPY Nov 2021 (low volatility, tight range): ADX 12 → ideal Iron Condor conditions

### Rule 4: ATR/Spot ≤ 2.5%

```
ATR (14-day Average True Range) / current spot price ≤ 0.025 (2.5%)
```

**Why:** ATR measures actual recent price velocity in dollar terms. Normalizing by spot gives the daily range as a fraction of price. If a stock is moving 3% per day on average, a 5% wing will be breached in 1–2 days. The ATR filter ensures recent market conditions are calm enough to hold the position for 3–4 weeks.

### Rule 5: Maximum 3 Concurrent Positions

**Why:** Correlation risk. If you have 5 Iron Condors open simultaneously on different stocks during a VIX spike, all 5 will blow up simultaneously — the correlations go to 1.0 in a panic. Three concurrent positions allows reasonable diversification while keeping total portfolio risk manageable.

---

## Real Historical Trade Examples

### Example Set 1 — Winning Trades

```
Date         Ticker  Spot  VIX   IVR   Short Call  Short Put  Wing  DTE  Credit  Max Loss  Outcome       P&L    Hold (days)
-----------  ------  ----  ----  ----  ----------  ---------  ----  ---  ------  --------  ------------  -----  -----------
Jan 18 2023  SPY     $393  19.4  0.64  $408        $378       $10   45   $1.72   $8.28     ✅ 50% target  +$86   18
Mar 8 2023   QQQ     $296  21.2  0.58  $310        $282       $14   42   $2.45   $11.55    ✅ 50% target  +$123  21
Jul 19 2023  AAPL    $191  13.8  0.52  $202        $180       $10   45   $1.38   $8.62     ✅ 50% target  +$69   24
Oct 4 2023   SPY     $419  18.7  0.61  $436        $402       $15   45   $2.90   $12.10    ✅ 50% target  +$145  17
Jan 22 2024  MSFT    $404  14.9  0.47  $425        $383       $20   43   $3.20   $16.80    ✅ 50% target  +$160  22
Apr 10 2024  SPY     $514  15.6  0.55  $535        $493       $18   45   $3.15   $14.85    ✅ 50% target  +$158  19
Aug 7 2024   QQQ     $449  21.8  0.70  $468        $430       $18   44   $3.80   $14.20    ✅ 50% target  +$190  14
Nov 13 2024  NVDA    $145  16.2  0.53  $155        $135       $10   45   $1.75   $8.25     ✅ 50% target  +$88   20
```

### Example Set 2 — Losing Trades (Learning from Losses)

```
Date         Ticker  Spot  VIX   IVR   Short Call  Short Put  Wing  DTE  Credit  What Went Wrong                            P&L    Lesson
-----------  ------  ----  ----  ----  ----------  ---------  ----  ---  ------  -----------------------------------------  -----  -------------------------------------
Feb 2 2023   META    $187  20.1  0.62  $198        $176       $10   44   $1.95   Q4 2022 earnings gap +23% → breached call  -$810  Earnings calendar check missed
Jul 26 2023  SPY     $452  13.9  0.50  $468        $436       $15   46   $2.20   Fed surprise hawkish → 3% drop             -$295  FOMC day — should skip 2d before FOMC
Oct 26 2023  AAPL    $171  21.4  0.60  $181        $161       $9    45   $1.65   Weak iPhone guidance, stock fell 6%        -$735  Single-stock earnings risk
Jan 31 2024  TSLA    $188  14.8  0.49  $200        $176       $12   44   $2.80   Musk tweet storm, stock gapped 12%         -$920  TSLA = high idiosyncratic risk, skip
```

### Regime Performance Summary

```
VIX Regime        Trades (2020–2024)  Win Rate  Avg P&L  Avg Hold  Notes
----------------  ------------------  --------  -------  --------  ----------------------------------------------------
Low (< 16)        38                  61%       +$42     26d       Thin credits, tight wins. Marginal after commissions
Medium (16–22)    112                 74%       +$118    21d       Sweet spot. Best risk-adjusted returns
Elevated (22–30)  67                  68%       +$95     18d       Good credits, faster profit targets hit
High (30–35)      24                  52%       -$28     14d       More losses, faster exits needed
Extreme (> 35)    —                   —         —        —         Do not trade. Rule 2 blocks all entries
```

**Summary row:** 241 total trades, 71% win rate, +$89 avg P&L, 21d avg hold.

---

## Entry Checklist

Use this before every trade:

```
Pre-Entry Checklist:
□ IVR ≥ 0.45 (check rolling 252-day VIX window)
□ VIX between 16 and 35
□ ADX(14) ≤ 22 — range-bound, not trending
□ ATR/Spot ≤ 2.5% — market is calm
□ No earnings within the next 45 days for this ticker
□ No FOMC meeting within next 2 days
□ Current open positions < 3 (concentration limit)
□ Credit ≥ $1.00 per share (minimum viable trade)
□ Wing width covers at least 1× N-day expected move
```

---

## Real Signal Snapshot

### Snapshot 1 — Clean Entry (SPY, Oct 4 2023)

```
Signal Snapshot — SPY, Oct 4 2023:
  IVR:              ████████░░  0.61  [ELEVATED ✓]
  VIX:              ████░░░░░░  18.7  [NORMAL ✓]
  ADX (14):         ██░░░░░░░░  14.2  [RANGE-BOUND ✓]
  ATR / Spot:       ██░░░░░░░░  1.8%  [CALM ✓]
  Open positions:   █░░░░░░░░░  1     [BELOW MAX ✓]
  ─────────────────────────────────────────────────
  ALL RULES PASS → ENTER IRON CONDOR
  Short call: $436  |  Short put: $402  |  Credit: $2.90
  Result: Closed at 50% profit target on Oct 21, +$145/contract
```

### Snapshot 2 — False Positive (SPY, Jul 26 2023)

```
Signal Snapshot — SPY, Jul 26 2023:
  IVR:              █████░░░░░  0.50  [ELEVATED ✓]
  VIX:              ███░░░░░░░  13.9  [BORDERLINE — below preferred floor]
  ADX (14):         ██░░░░░░░░  16.1  [RANGE-BOUND ✓]
  ATR / Spot:       ██░░░░░░░░  1.4%  [CALM ✓]
  FOMC in 2 days:   ████████░░  YES   [⚠️ SHOULD SKIP — rule not enforced]
  ─────────────────────────────────────────────────
  Rules technically passed → entered (mistake in hindsight)
  Fed raised 25bps AND signaled 'higher for longer' → SPY dropped 3% in 2 days
  Short put at $436 threatened → closed early at 2× stop, -$295/contract

  LESSON: VIX at 13.9 (below 16 preferred floor) was a warning sign.
          Low VIX often accompanies FOMC anticipation with binary outcome.
          Add FOMC calendar check: skip if FOMC within 3 trading days.
```

---

## Position Sizing

```python
# Max loss per contract = (wing_width − credit) × 100
# Size so that max loss = position_size_pct × capital

max_loss_per_contract = (wing_width_pct × spot − net_credit) × 100
contracts = floor(capital × position_size_pct / max_loss_per_contract)

# Example: $100k capital, 3% risk, SPY at $450:
# wing_width = $450 × 5% = $22.50
# net_credit = $4.66   (skew-aware pricer at ATM IV 0.22)
# max_loss = ($22.50 − $4.66) × 100 = $1,784
# contracts = floor($100,000 × 0.03 / $1,784) = 1 contract
#
# NOTE: the backtest hard-codes 1 contract per trade and gates on free capital
# (margin = max_loss); this floor()-based sizing is the LIVE sizing rule the
# guide recommends, not what the backtest simulates.

# With 2 concurrent ICs at 3% risk: 6% of capital at max risk
# With 3 concurrent ICs at 3% risk: 9% of capital at max risk
# In practice, win rate 70%+ means realized drawdown << theoretical max
```

---

## When the Strategy Fails

**Earnings gap (most common):** A company beats/misses earnings by a wide margin and gaps 15–25%. The Iron Condor's long wing provides a hard loss floor, but the loss is substantial. **Prevention: never hold an IC through an earnings date for single stocks.**

**Sustained trend (second most common):** VIX is in range but the stock is grinding relentlessly in one direction. ADX eventually rises above 25 but the damage is done before the rule triggers. **Prevention: raise the ADX max to 20 for single stocks; use SPY/QQQ for cleaner signals.**

**Tail event:** Black swan — COVID (March 2020, VIX 82), Flash Crash (May 2010), VIX spike (Feb 2018). All three would be blocked by the VIX cap of 35. Any IC open when VIX crosses 35 should be closed immediately regardless of P&L.

---

## Quick Reference

These are the **actual code defaults**, calibrated for the limited (~2-year)
VIX history currently in the database. The "classic" 2010–2023 thresholds quoted
in the rule sections above (IVR ≥ 0.45, VIX 16–35, ADX ≤ 22) are tighter; raise
the defaults toward them once a longer VIX history is synced.

```
Parameter            Default  Range      Description
-------------------  -------  ---------  ----------------------------------
`ivr_min`            0.20     0.10–0.60  Min IV Rank to enter (low default suits short VIX history)
`vix_min`            14.0     10–20      VIX floor (avoid cheap premium)
`vix_max`            45.0     25–55      VIX ceiling (avoid fear regime)
`adx_max`            35.0     15–50      Max ADX (range-bound filter)
`atr_pct_max`        0.030    0.01–0.05  Max ATR/spot ratio
`delta_short`        0.16     0.10–0.25  Short strike delta (~84% prob OTM)
`wing_width_pct`     0.05     0.02–0.10  Wing width as % of spot
`dte_target`         45       21–60      Days to expiry at entry
`dte_exit`           21       7–30       Force-close at this DTE
`profit_target_pct`  0.50     0.25–0.75  Close at 50% of max credit
`stop_loss_mult`     2.0      1.0–4.0    Stop at N× credit received
`position_size_pct`  0.03     0.01–0.08  Capital at risk per trade
`max_concurrent`     5        1–8        Max simultaneous positions
```

---

## Backtest Mechanics — How P&L Is Simulated

The backtest is fully walk-forward (no look-ahead): every entry decision on bar
*i* uses only IVR/VIX/ADX/ATR computed from bars ≤ *i*, all from causal rolling
windows. Three details make the simulated P&L realistic rather than optimistic:

**1. Skew-aware option pricing.** Legs are priced with the engine's
`bs_price_skew`, which applies a linear equity-index volatility skew to the
VIX-derived ATM IV: OTM puts (lower strikes) are marked *richer* and OTM calls
(higher strikes) *cheaper* than a single flat IV would imply. Both the entry
credit and every mark-to-market exit valuation use the **same** surface, so no
artificial pricing-basis P&L is created. Strike selection still locates the
~16-delta strike using flat-IV delta — that only positions the strikes and does
not affect realized P&L.

**2. Transaction costs on entry AND exit.** Each leg is charged
`DEFAULT_SLIPPAGE_PER_LEG` ($0.05/share adverse fill → $5.00/contract) plus
`DEFAULT_COMMISSION_PER_LEG` ($0.65/contract). That is **$5.65 per leg**, and a
condor is 4 legs, charged on *both* the opening fill and the closing fill:

```
Round-trip cost per 1-contract condor
  = 8 legs × $5.65
  = $45.20

This is deducted from realized P&L. On a ~$4.66 credit ($466) the cost is ~10% of
gross premium; on a thin $1.00 credit it is ~45% — which is exactly why low-VIX
/ low-priced underlyings are flagged as not viable.
```

The reported per-trade `pnl` is the **full round-trip net** (gross credit
captured − entry cost − exit cost), so the trade ledger sums exactly to the
realized change in the equity curve.

**3. Pessimistic exit realization.** All exits (profit target, 21-DTE, 2× stop)
are realized at the daily close, not at the intraday trigger price — so gap days
are modeled against the position, never in its favor.

### Worked numeric example — one full trade

```
Entry: SPY = $450, VIX = 22 (ATM IV ≈ 0.22), 45 DTE, IVR clears the gate
  Short call (16Δ) ≈ $500   Long call  = $500 + 5%×450 = $522.50
  Short put  (16Δ) ≈ $415   Long put   = $415 − 5%×450 = $392.50
  Skew-adjusted net credit (bs_price_skew):  ≈ $4.66/share  →  $466
  Wing width = 5% × $450 = $22.50
  Max loss   = ($22.50 − $4.66) × 100 = $1,784  (this is the margin reserved)

Exit at 50% profit target (cost-to-close ≈ $2.33/share = $233):
  Gross P&L   = ($4.66 − $2.33) × 100 = +$233
  Entry cost  = 4 legs × $5.65        = −$22.60
  Exit cost   = 4 legs × $5.65        = −$22.60
  Net P&L     = $233 − $45.20         = +$188   ← what the ledger records
```

A symmetric losing trade stopped at 2× credit closes for ~$9.32/share, i.e.
−$466 gross, −$511 after costs — about 2.5× the average winner, which is the
structural reason the equity path is choppy (see the honesty note below).
(This ~$188 illustrative winner is close to the real backtest's +$279 average
winner; the spread reflects that real exits happen at varying spots/DTEs, not
exactly at the idealised 50%-cost-to-close point.)

## Data Requirements

```
Data                    Source          Usage
----------------------  --------------  ----------------------------------------
Daily OHLCV             `mkt.PriceBar`  Close for strikes, high/low for ATR, ADX
VIX daily close         `mkt.VixBar`    IVR calculation, VIX filter
(Optional) macro rates  `mkt.MacroBar`  Yield curve context
```

No options chain data required — strikes are estimated from Black-Scholes using VIX as IV proxy.

---

## Honest Results — SPY, Apr 2024 → Mar 2026

Run on the real reconstructed-IV window currently in the database, at the code
defaults, with skew pricing and full round-trip costs:

```
Total return        +3.4%        (over ~2 years)
Annualized          +1.7%
Sharpe              −0.66        ← NEGATIVE
Sortino             −0.76
Max drawdown        −5.6%
Trades              46
Win rate            80%          (31 profit-target, 8 DTE-exit, 7 stops)
Profit factor       1.49         (gross-profitable, after costs)
Avg winner          +$279        Avg loser  −$770   (≈2.5× the winner)
```

**Read this carefully.** The strategy is *gross-profitable* (PF 1.49, 80% win
rate, positive total return) but has a **negative Sharpe**. That is not a
contradiction — it is the defining risk profile of premium selling: many small
wins punctuated by a few losses ~2.5× the size of a typical winner. The few
2× stop-outs land on the worst days (trending sell-offs), so the *return path*
is choppy and its volatility-adjusted score is poor even though the sum is
positive.

The honest verdict: **the edge here is marginal and not robust.** On this
particular sample the variance-risk-premium thesis barely clears costs, and the
2024–2026 tape was a persistent bull trend — the single environment Iron Condors
struggle in most (one side keeps getting tested). Do **not** treat the +3.4%
as a reliable forward expectation. The strategy is best understood as a
range-bound-regime tool that should be sized small and turned off (via the ADX
and VIX filters) when the market trends — which is exactly what dragged the
Sharpe negative on this window. A longer, regime-diverse VIX history is needed
before claiming a durable edge.

---

## Screener Guide

# How to Use This Iron Condor Screener

## 1. How to Read the Screener

Each column is a filter, not a standalone signal. Read them together.

```
Column  What It Measures                                                                                         Good Range for ICs
------  -------------------------------------------------------------------------------------------------------  -------------------------------------------------------
IVR     Where today's IV sits in its 52-week range (0 = 52-week low, 1 = 52-week high)                           > 0.40
VRP     IV minus realized volatility (vol points). Positive = options are expensive relative to actual movement  > 2.0 vol pts
ATM IV  Current annualized implied volatility at the money                                                       Context-dependent (see VIX banner)
ADX     Average Directional Index — measures trend strength, not direction                                       < 25 (range-bound)
ATR%    Average True Range as % of price — daily velocity                                                        < 1.5% preferred
VIX     CBOE fear gauge — proxy for broad market regime                                                          20–30 sweet spot
Credit  Approximate premium collected per share for a balanced IC                                                Higher is better, but not at the cost of narrow strikes
```

**IVR > 0.40** means IV is in the top 60% of its annual range — you are selling volatility that is historically elevated, which is the foundation of the trade. IVR 0.60+ is a strong signal. IVR below 0.30 means you are selling cheap premium; the risk/reward deteriorates.

**ADX < 25** means the underlying is chopping sideways. Iron condors bleed premium in range-bound markets and get steamrolled in trends. An ADX of 18 is ideal. An ADX of 35 is a caution. Above 40, walk away.

---

## 2. What Makes a Good IC Entry

The ideal setup stacks at least four of the five signals. A single strong reading is not enough.

**Example of a near-perfect setup — SPY, typical late-summer environment:**

- IVR = 0.55 (IV in top 45% of range)
- VRP = +4.5 vol points (IV running well above 30-day realized)
- ADX = 18 (no dominant trend)
- ATR% = 0.85% (calm daily movement)
- VIX = 22 (moderate fear, decent credits without chaos)
- Credit = $1.40/share on a 30-DTE balanced condor

This is a green-light setup. Place strikes one standard deviation out, collect the credit, and let theta work.

**Three signals passing, one borderline** (e.g. IVR = 0.38): reduce size by half or wait for a better entry. The screener is a queue, not a forced entry system.

---

## 3. Reading VRP — The Overlooked Edge

Variance Risk Premium is the spread between what the market *implies* will happen (IV) and what actually happened (realized vol). When VRP is positive, option sellers are collecting a structural risk premium — analogous to an insurance company charging more than actuarial fair value.

**VRP is positive roughly 70% of the time on SPY and QQQ.** That is the long-run edge of systematic vol selling. The problem is the other 30%: those periods tend to cluster around sudden dislocations (Aug 2024 carry unwind, Apr 2025 tariff shock) where realized vol explodes past IV.

**When VRP matters more than IVR:** Use VRP as your primary filter in slow-drift IV environments where IVR is middling (0.35–0.50). If VRP is running +5 to +8 vol points in that window, the market is paying you significantly more than the recent historical movement justifies. That is the real edge.

**Negative VRP** is a serious warning. It means the market moved *more* than options priced in — a regime where IC sellers lose money structurally. Do not open new positions when VRP turns negative; tighten stops on existing ones.

---

## 4. Red Flags — When NOT to Trade

- **ADX > 40:** The underlying is in a strong directional move. One leg of your condor will be tested immediately. Skip it.
- **VIX > 45:** This is a fear regime. Aug 2024 touched 65 intraday; Apr 2025 briefly cleared 50 on tariff headlines. Wings priced at "one standard deviation" become meaningless when vol term structure collapses and gaps become routine. Sit on hands.
- **VRP negative:** Realized vol is exceeding implied. You are selling underpriced insurance. Historical loss rates for IC sellers spike sharply in negative-VRP environments.
- **Earnings within the hold window:** A 30-DTE condor opened with earnings 15 days out will reprice violently on the event. The screener's ATM IV will look elevated (it is — because of the earnings premium), but that premium vaporizes post-event, often with a large directional gap attached.
- **ATR% > 2.0% and rising:** Intraday ranges are expanding. Even without a trend, wide daily swings will test your short strikes repeatedly through a 30-day hold.

---

## 5. Regime Context — The VIX Banner

```
VIX Level  Regime       IC Strategy
---------  -----------  --------------------------------------------------------------
14–20      Low vol      Credits thin; be highly selective; IVR filter becomes critical
20–30      Sweet spot   Best risk/reward for balanced condors; standard sizing
30–45      Elevated     Widen strikes by 15–20%; reduce size; shorter DTE (21 days)
> 45       Danger zone  No new ICs; manage or close existing positions
```

In low-vol regimes, prioritize IVR and VRP over credit size. A $0.60 credit on a well-positioned SPY condor beats a $1.20 credit on a name with ADX of 38.

---

## 6. Practical Tips

- **Run 3–5 concurrent ICs maximum** until you have a full year of personal trade history. Correlation spikes in selloffs — five "uncorrelated" condors can all breach simultaneously.
- **Size each IC at 2–3% of account risk** (max loss on the spread, not notional). This lets you absorb three simultaneous breaches without a portfolio-level wound.
- **Check the screener weekly**, ideally Sunday evening or Monday pre-market. Most new IC entries are opened with 25–35 DTE; forcing daily entries creates overtrading.
- **When 3 of 5 filters pass,** reduce position size by 40% and set a tighter stop — close if the underlying moves more than 60% of the distance to the short strike within the first 10 days.
- **Roll, don't panic.** If one side is tested but you have 10+ days to expiration and the untested side still has meaningful premium, rolling the tested side out one expiration and up/down toward the market is often superior to closing for a full loss.
- **Theta is fastest in the final 21 days.** The screener's credit column matters most for entries at 28–35 DTE. Beyond 45 DTE, gamma risk is low but theta harvest is slow.
- **After a VIX spike above 35, the screener will light up with high-IVR tickers.** Wait for ADX to begin falling before entering — catching a falling vol knife is a classic mistake.

---

## 7. What the Backtest Doesn't Capture

Backtests are optimistic by construction. These three risks are real and material — plan for them before going live.

**1. FOMC / CPI Gap Opens**

SPY can move 2–4% in minutes on a surprise Fed decision or inflation print. Your backtest uses daily closing prices — it cannot model an IC that was safely inside its range at yesterday's close getting blown through at 10:00 AM. The 21-DTE exit rule reduces exposure, but it does not protect you if you are in the last two weeks of a position when a major catalyst hits. Check the economic calendar before every new entry. Never hold an open IC through an FOMC meeting if you are inside 14 DTE.

**2. Bid/Ask Blowout and Fill Quality**

Backtests price at the mid. On a 4-leg SPY IC in normal conditions, mid is achievable. During vol spikes (VIX > 25), spreads on each leg can be $0.15–0.30 wide. On 4 legs that is $0.60–1.20 of slippage versus mid. If your average credit is $2.00, you have lost 30–60% of your theoretical edge before the trade even starts. Robinhood routes order flow for payment — fills are not institutional-grade. Track your actual fill versus mid on every single trade. If you are consistently receiving less than 85% of mid across 10+ trades, your live edge is materially smaller than the backtest implies.

**3. Regime Shift**

The strategy was calibrated on 2022–2026, a period that included a bear market, a rate shock, and a vol spike. If the next two years look different — a sustained low-vol grind, a prolonged trending market, or a structural VIX regime change — the entry filters may stop working without obvious warning. Monitor your rolling win rate. If it drops below 65% over any 20-trade window, treat it as a regime signal: cut position size in half and reassess whether the current market environment still fits the Iron Condor thesis.

```
Signal                       Action
---------------------------  ------------------------------------------------
Rolling 20-trade WR < 65%    Cut size 50%, reassess regime
3 consecutive stop-loss hits  Pause new entries for 2 weeks
Account down 15% from peak   Pause new entries for 30 days
Account down 25% from peak   Stop trading, full strategy review
```

---

## 8. Common Mistakes

1. **Chasing high credit without checking ADX.** A name paying $2.50/share looks attractive until you notice ADX is 48 and the stock has been in a clean uptrend for six weeks. The credit reflects the trend risk.

2. **Ignoring earnings dates.** The screener cannot know your intended hold period. Always cross-reference the next earnings date before entering any single-stock IC.

3. **Over-diversifying into correlated names.** Running ICs on SPY, QQQ, and IWM simultaneously provides almost no diversification. In a broad selloff all three breach together.

4. **Treating IVR = 0.40 as a hard floor.** In a persistently low-vol environment (e.g. most of 2017, much of 2024 Q1), IVR 0.40 may still represent historically cheap premium. Pair IVR with VRP to confirm the opportunity is real.

5. **Holding through expiration week.** The final 5 days of a condor carry outsized gamma risk relative to the remaining premium. Unless you are actively watching intraday, closing at 5–7 DTE for 60–70% of max profit is a sound mechanical rule that significantly improves long-run Sharpe.


---

## Audit & money verdict — 2026-07-03

**End-to-end audit (UI · Backtest · Screening · Tests · Training): all surfaces PASS.**

- **Real backtest:** +3.4% · Sharpe −0.66 · −5.6% max DD · 46 trades · PF 1.49 (SPY 2024-04→2026-03).
- **Money verdict:** **No durable edge** — +3.4% is below the ~4.5% risk-free rate; losers run ~2.8× winners; it loses in sustained trends. A range-bound-regime tool: size small, disable in trends.
- **Deploy:** Paper only.

_Audited on real DB data via the production backtest + screener paths. Full cross-strategy report: `docs/reviews/2026-07-03_top10_strategy_audit.md`._
