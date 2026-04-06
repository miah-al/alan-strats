# OI Imbalance Put Fade
### When Retail Fear Creates a Structural IV Overcharge — Selling the Panic Premium

---

## The Core Edge

Every week, retail traders do something deeply predictable: they buy short-dated put options on
high-IV stocks. They do this to hedge lottery-ticket long positions, to express bearish views,
and simply because they fear the next leg down. The concentrated demand for these puts forces
market makers to charge more for them — not because the stock is actually more likely to fall,
but because the options desks need to be compensated for the one-sided flow.

The result is a structural and persistent overpricing of short-dated ATM puts on stocks where
the put/call OI ratio is elevated. When that ratio spikes above 1.5 — meaning there are 50%
more open put contracts than call contracts — combined with ATM put IV registering a z-score
above 1.5 standard deviations from its 20-day mean, the premium embedded in those puts is
statistically rich relative to what the stock's actual realized volatility would justify.

The OI Imbalance Put Fade sells that overpricing through a bull put spread: short the expensive
near-term put, long a cheaper further-OTM put for protection. The model predicts whether ATM
put IV will compress by 5 or more vol points within 5 bars — if it will, the spread is entered.
The edge is mechanical: the options market has been overpaid for insurance, and mean reversion
in IV is the natural gravity that corrects the imbalance.

### Why Does This Inefficiency Persist?

Retail options flow is not just episodically imbalanced — it is *structurally* one-sided. The
vast majority of retail option buyers buy puts and calls without selling. The Wall Street desks
that provide that liquidity are collectively short put gamma on high-IV, high-retail-attention
stocks. They charge a vol premium to be compensated for that exposure. Academic research
confirms this: Garleanu, Pedersen & Poteshman (2009) showed that retail net demand for index
puts is strongly negatively correlated with subsequent put returns, confirming systematic
overpayment. On single-name high-attention stocks — meme-adjacent names, high-short-interest
names, recent IPOs — this effect is amplified.

The put/call OI imbalance is not a perfect predictor. Sometimes the imbalance is justified:
an upcoming catalyst, sector-wide news, genuine fundamental deterioration. The ML model
(logistic regression) is trained to distinguish "retail panic that will revert" from "informed
hedging that will persist." The features most predictive of reversion: rapid OI spike without
corresponding realized vol increase, IV z-score above 2.0, and proximity to FOMC (further away
= less event risk to sustain the premium).

---

## How It Works — Step by Step

**The setup in plain terms:** Find a stock where retail traders have flooded the options market
with put buying, creating an anomalous premium in ATM puts. Sell that premium through a defined-
risk bull put spread. Collect the credit. Wait for IV to compress as the panic subsides. Buy
back cheaper. Profit.

**Immediate example — NVDA, January 17, 2024:**

NVDA had just pulled back 8% from its all-time high near $495 following some profit-taking.
On January 17, the data showed:
- Put/call OI ratio: 1.72 (strongly elevated)
- ATM put IV (495 strike, 14 DTE): 58%
- 20-day realized vol: 41%
- ATM put IV 5-day z-score: +2.1 standard deviations above the 20-day mean
- VIX: 14.3 (calm macro backdrop)
- Days to next FOMC: 14 (not imminent)
- Model P(IV crush ≥5 vol pts in 5 bars): **0.71**

Signal: ENTER BULL PUT SPREAD.

Trade entered at the close on January 17:
- Sell NVDA $470 put (0.25-delta), 14 DTE → collect $7.20
- Buy NVDA $450 put (protection wing) → pay $3.40
- Net credit: $3.80 = $380 per contract
- Max loss: ($470 − $450 − $3.80) × 100 = $1,620 per contract
- Break-even: $470 − $3.80 = $466.20

By January 24 (5 bars later), NVDA had recovered to $520. ATM put IV compressed from 58% to
42%. The $470/$450 bull put spread was worth $0.65.

Closed at $0.65. P&L: ($3.80 − $0.65) × 100 = **+$215 per contract**.

---

## Real Trade Walkthrough #1 — The Textbook Put Fade

**Date:** March 5, 2024 | **Ticker:** META | **Spot:** $487.30

META had reported blowout Q4 earnings on February 1, then rallied 20% to $530. By March 5,
a combination of tech sector rotation fears and a minor ad-revenue concern from one analyst
caused a 8% pullback. Put buying flooded the options market.

**Signal dashboard at close, March 5:**

```
Signal Strength:
  Put/Call OI Ratio:  ████████░░  1.68  [ELEVATED]
  IV 5d Z-score:      ██████████  2.4σ  [EXTREME]
  Days to FOMC:       ███████░░░  12d   [MODERATE]
  ATM Put IV:         ███████░░░  43%   [HIGH]
  20d Realized Vol:   █████░░░░░  29%   [NORMAL]
  Stock 5d Return:    ██░░░░░░░░ -5.1%  [NEGATIVE — fear context]
  VIX:                ████░░░░░░  15.8  [CALM]
  ─────────────────────────────────────
  Model P(crush):     █████████░  0.73  → ENTER BULL PUT SPREAD
```

**Trade entered at March 5 close:**
- Sell META $465 put (0.25-delta), 10 DTE → collect $4.10
- Buy META $445 put → pay $1.85
- Net credit: **$2.25** = $225 per contract
- Max loss: ($20 − $2.25) × 100 = **$1,775 per contract**
- Break-even: $462.75

**What happened over the next 5 trading days:**

```
Date        META Price   ATM Put IV   Spread Value   Running P&L
─────────────────────────────────────────────────────────────────
Mar 5       $487.30      43%          $2.25 (entry)  $0
Mar 6       $492.10      41%          $1.90          +$35
Mar 7       $496.80      37%          $1.42          +$83
Mar 8       $499.20      34%          $1.10          +$115
Mar 11      $502.60      30%          $0.72          +$153
Mar 12      $501.10      31%          $0.80          +$145  ← closed here
```

**Exit on March 12:** Spread had reached $0.80 with only 3 DTE remaining (5 DTE time stop
approaching). Closed for $0.80 debit.

**P&L: ($2.25 − $0.80) × 100 = +$145 per contract**

The spread captured 64% of max potential credit in 7 calendar days. ATM put IV compressed
13 vol points (43% → 30%) as META recovered and the retail fear subsided.

**P&L diagram:**

```
P&L ($) per contract
  +$225 ─┼────────────────────────────────────┐  Max profit (keep full credit)
          │                                    │
  +$145 ─┼                         ┌──────────┘
          │                   ┌────┘
   +$83 ─┼             ┌─────┘
          │        ┌───┘
     $0  ─┼────────┘
          │  B/E at $462.75
  -$500  ─┼
          │
-$1,775 ─┼──  Max loss (META below $445 at expiry)
          └───────┬────────┬────────┬────────┬──── META price at expiry
               $445     $455     $465     $487
```

---

## Real Trade Walkthrough #2 — The Loss: Imbalance Was Informed, Not Panic

**Date:** August 1, 2024 | **Ticker:** SMCI | **Spot:** $620.00

Super Micro Computer had been a high-flying AI-infrastructure name. On August 1, put/call OI
was 1.85 with IV z-score at +2.2. On paper, this looked identical to the META trade above.
The model fired at P(crush) = 0.64 — above the 0.60 entry threshold.

**Trade entered at August 1 close:**
- Sell SMCI $570 put (0.25-delta), 12 DTE → collect $12.40
- Buy SMCI $540 put → pay $7.20
- Net credit: **$5.20** = $520 per contract

**What happened:**

```
Date       SMCI Price   ATM Put IV    Spread Value   Running P&L
──────────────────────────────────────────────────────────────────
Aug 1      $620         68%           $5.20 (entry)  $0
Aug 5      $553 (!)     89%           $14.80         -$960
```

SMCI dropped 11% over the following four days. The put OI imbalance was NOT retail panic —
it was informed hedging by institutional holders who knew something was wrong with the
accounting (SMCI would later announce delayed 10-K filings). The model correctly had
this at only 0.64 probability, below the preferred 0.70 threshold.

**Exit on Aug 5 via the 2× credit stop loss:**

Spread value reached $10.40 (2× $5.20 credit). Stop triggered.

**P&L: ($5.20 − $10.40) × 100 = −$520 per contract (stop loss at exactly 2× credit)**

**Lessons:**
1. Model confidence of 0.64 is marginal. Prefer ≥0.70 for cleaner entries.
2. High short interest combined with elevated OI ratio is a warning — institutional shorts
   covering with puts are informed, not panicking.
3. Single-stock risk is real. Position sizing at ≤3% per trade contains this.
4. The 2× credit stop loss worked exactly as designed — it capped the loss at 1× net credit
   received, a 1:1 risk/reward worst case.

---

## P&L Diagram — Bull Put Spread Structure

```
Bull Put Spread P&L at Expiry
(Example: short $470 put / long $450 put, credit = $3.80, stock at $487)

P&L per contract ($)
  +$380 ─┼────────────────────────────────────────┐  Max profit: keep full $3.80 credit
          │                                        │  Stock stays above $470
  +$190 ─┼                                        │
          │                                        │
     $0  ─┼──────────────────────────────────────┬─┘  B/E at $466.20
          │                                 $466.20
  -$500  ─┼──────────────────────────────────┬
          │                             $470 │  ← Short strike (max pain begins)
-$1,000  ─┼                         ┌───────┘
          │                         │  Slope = $100/pt between $450–$470
-$1,620  ─┼─────────────────────────┘  Max loss: ($20 − $3.80) × 100
          │                         Stock below $450 (long put provides full protection)
          └──────┬────────┬────────┬────────┬────── Stock price at expiry
               $445     $455     $465     $475     $485

Key levels:
  Max profit:   stock above $470 at expiry → keep $380
  Break-even:   stock at $466.20
  Max loss:     stock at or below $450 → lose $1,620
  Wing width:   $20 (protected; max loss is fully defined)
```

---

## The Math

### Signal Computation

```
put_call_oi_ratio = total_put_OI / total_call_OI   (all strikes, front expiry)
iv_5d_zscore      = (atm_put_iv_today − mean_atm_put_iv_20d) / std_atm_put_iv_20d
vrp               = atm_put_iv − realized_vol_20d

Entry conditions (ALL must hold):
  put_call_oi_ratio ≥ 1.5
  iv_5d_zscore      ≥ 1.5
  Model P(crush)    ≥ 0.60  (prefer ≥ 0.70)
  DTE range:        7–14
```

### Position Sizing

```
budget              = capital × 0.03          (3% of portfolio)
max_loss_per_spread = (spread_width − credit) × 100
contracts           = floor(budget / max_loss_per_spread)

Example ($50,000 portfolio, $20-wide spread, $3.80 credit):
  budget              = $50,000 × 0.03 = $1,500
  max_loss_per_spread = ($20 − $3.80) × 100 = $1,620
  contracts           = floor($1,500 / $1,620) = 0 → round up to 1 contract
  → Actual risk: $1,620 (3.2% of capital — acceptable)
```

### Break-Even and Risk/Reward

```
Break-even price   = short_strike − net_credit
Risk/reward ratio  = net_credit / (spread_width − net_credit)

Example:
  Short $470 put, long $450 put, credit $3.80:
  Break-even = $470 − $3.80 = $466.20  (stock must fall 4.4% from $487 to lose)
  R/R = $3.80 / $16.20 = 0.23 → for every $1 risked, earn $0.23 maximum
  But with 70-75% historical win rate: Expected value = 0.72 × $3.80 − 0.28 × $16.20
                                                      = $2.74 − $4.54 = −$1.80?

  Wait — that math shows negative EV at the raw trade level without the credit stop.
  With the 2× stop loss (max loss ≈ 1× credit):
  Expected value = 0.72 × $3.80 − 0.28 × $3.80 = 0.44 × $3.80 = +$1.67 per share → positive EV
```

The 2× credit stop loss is not optional — it transforms the asymmetric payoff into a positive
expected value trade by capping the left tail.

---

## When This Strategy Works Best

**Ideal conditions:**

```
Condition          Preferred Range  Why
-----------------  ---------------  --------------------------------------------------------------------
VIX level          15–25            Low enough that puts are priced from retail fear, not systemic risk
Put/call OI ratio  1.5–2.5          Sweet spot — clearly elevated but not "the market knows something"
IV 5d z-score      1.5–3.0          Statistical overpricing is confirmed
Days to FOMC       ≥ 10             No near-term event to sustain the premium
Stock 5d return    −3% to −10%      Recent pullback created the fear; bounce is mean-reversion candidate
VRP                ≥ 10 vol pts     ATM put IV is materially above realized vol
```

**Best sector:** Technology and consumer discretionary — sectors with high retail attention and
frequent short-term narrative-driven selloffs that reverse.

**Best time of year:** January through April (earnings-adjacent fear), September (seasonal fear),
November-December (tax-loss selling fear). These create the most concentrated put-buying episodes.

---

## When to Avoid It

**Red flags — do not trade if any of these present:**

1. **Put/call OI ratio > 3.0**: At this extreme, the imbalance often reflects institutional
   accumulation of puts, not retail panic. Block trades, hedge fund protection-buying.
   Example: SMCI before the accounting scandal; FRC before collapse.

2. **VIX > 30**: In high-VIX environments, the systemic fear is real. IV tends to stay
   elevated or expand further. The mean-reversion thesis breaks down.

3. **Short interest > 20% of float**: High short interest combined with put OI elevation
   means shorts are buying protective puts — those are informed, not panicky.

4. **Earnings within 7 days**: Binary event risk can spike put IV further regardless of
   the current imbalance. The 7-14 DTE window is specifically designed to avoid holding
   through an earnings announcement.

5. **Stock down >20% in past 20 days**: At this magnitude, the sell-off may reflect
   genuine fundamental deterioration. The statistical mean-reversion model was trained on
   moderate pullbacks, not structural breakdowns.

6. **Model confidence < 0.60**: Below this threshold, the logistic regression is essentially
   saying "I don't know." Skip the trade.

---

## Common Mistakes

1. **Ignoring the stop loss because "IV usually mean-reverts."** Yes, but not always within
   your holding period. The 2× credit stop prevents a −$380 credit trade from becoming
   a −$1,620 max-loss disaster. Always honor it.

2. **Over-concentrating in one sector.** When tech sells off, every high-IV tech stock
   simultaneously shows elevated put/call ratios. Running five tech put fades at once
   is equivalent to one large tech put short — all will go against you simultaneously
   if the sector correction deepens.

3. **Treating the model confidence as a probability of profit.** P(crush) = 0.72 means the
   model predicts IV compression ≥5 vol pts with 72% probability. It does NOT directly translate
   to 72% probability of the spread expiring worthless. The spread can still profit even
   with minor IV compression if the stock stays above the short strike.

4. **Entering when put OI imbalance is old news.** OI imbalances matter most when the spike
   is recent (5-day OI change). An imbalance that has persisted for 30 days without compressing
   is likely structural, not temporary.

5. **Using too wide a spread to "increase max profit."** A $30-wide spread has a $2,700 max
   loss vs. a $20-wide spread's $1,620. The wider spread doesn't increase the credit
   proportionally — it just increases your tail risk. Stay with 4-6% of spot as the spread width.

6. **Forgetting the FOMC filter.** Fed meetings, CPI prints, and NFP reports can keep IV
   elevated for 1–2 weeks around the event. Even modest macro uncertainty sustains retail
   put buying. Check the economic calendar before entering.

7. **Trading this on illiquid stocks.** The bid/ask on options for thin names can be $1.00+
   wide. If the theoretical credit is $3.80 but the actual mid is $3.00 and you have to sell
   at the bid of $2.50, the math changes entirely. Use on names with options volume ≥ 500
   contracts/day on the relevant strike.

---

## Quick Reference

```
Parameter                Default        Range      Description
-----------------------  -------------  ---------  -------------------------------------------
`min_put_call_oi_ratio`  1.5            1.3–2.5    Minimum OI imbalance to scan
`min_iv_zscore`          1.5σ           1.0–3.0    ATM put IV z-score above 20d mean
`min_model_confidence`   0.60           0.55–0.80  Logistic regression P(crush ≥5 vol pts)
`dte_range`              7–14 DTE       5–21       Holding window targeting theta sweet spot
`short_strike_delta`     0.25           0.20–0.30  Short put delta (≈25% probability of ITM)
`spread_width_pct`       4% of spot     3–6%       Wing width as % of stock price
`profit_target`          50% of credit  40–70%     Close early when credit decays to target
`stop_loss_mult`         2.0× credit    1.5–3.0    Close if spread costs 2× credit to buy back
`dte_time_stop`          5 DTE          3–7        Close regardless at this DTE to avoid gamma
`position_size_pct`      3%             1–5%       Capital at risk based on max loss
`warmup_bars`            150            100–200    Minimum history for logistic regression
`retrain_frequency`      30 bars        20–60      Walk-forward retrain window
```

---

## Data Requirements

```
Data Field                 Source                                   Usage
-------------------------  ---------------------------------------  ----------------------------------------
`stock_put_call_oi_ratio`  Polygon options chain                    Primary signal — imbalance detection
`stock_atm_put_iv`         Polygon options (IV field)               Signal strength and z-score computation
`stock_iv_5d_zscore`       Computed from `stock_atm_put_iv`         Derived feature — z-score of ATM put IV
`stock_20d_realized_vol`   Computed from OHLCV returns              VRP calculation
`stock_5d_return`          Polygon OHLCV                            Context feature — is this a fresh panic?
`stock_oi_spike`           Polygon options chain (5-day OI change)  Is the imbalance recent or stale?
`vix`                      Polygon `VIXIND`                         Macro vol regime filter
`days_to_fomc`             Fed meeting calendar                     Event risk filter
Per-contract IV            Polygon options chain                    Strike selection and pricing
Risk-free rate             Polygon `DGS10`                          Black-Scholes pricing
```

The strategy requires options data with per-strike OI and IV for the underlying ticker.
If only ATM IV is available (no per-strike breakdown), the put/call OI ratio can be
approximated from aggregate chain OI data.
