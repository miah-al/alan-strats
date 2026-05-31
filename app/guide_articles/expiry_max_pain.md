# OpEx Max Pain Pin
### Defined-Risk Short Iron Butterfly Anchored at the Max-Pain Strike on Monthly Expiration

---

## Detailed Introduction

The OpEx Max Pain Pin strategy systematically harvests a small but persistent microstructure effect that has been documented in academic literature for over thirty years: on monthly equity-index option expirations (the third Friday of each month), the underlying tends to drift toward the strike where aggregate option holders' payouts are minimised — the so-called "max-pain" strike. The mechanism is mechanical, not conspiratorial. Dealers who are net long gamma against retail short-dated short-call/short-put positioning hedge their books continuously; their hedging flows act as a soft mean-reverter pulling spot toward the strike where their cumulative delta is least exposed. Stoll and Whaley (1990, 1991) first systematically documented expiration-week pricing effects in equity index options. Ni, Pearson, and Poteshman (2005), in *Stock price clustering on option expiration dates* (Journal of Financial Economics 78), provide the empirical backbone for this strategy: using a comprehensive dataset of US single-stock options, they show that on monthly expiration Fridays, prices cluster near strikes with high open interest at a rate well above what would be predicted by chance. Hu (2014), in *Optionable Stocks and Mutual Fund Returns*, follows up with cross-sectional evidence that the effect is driven by dealer hedging, not by manipulation, and is strongest where retail option flow is dominant.

The economic magnitude of the pin is small — academic estimates put it at 10–30 basis points on average, with substantial variance — but the effect is consistent enough that a defined-risk premium-selling structure can extract systematic income from it without taking unbounded tail risk. The trade is a short iron butterfly anchored at the max-pain strike, entered Monday or Tuesday of OpEx week (3–5 calendar days to the third-Friday expiration), and held to expiration. The structure profits if the underlying ends near the max-pain strike on Friday close, with bounded losses on either side defined by the wing width.

The required filter set is strict because the edge is small. First, the spot must be at least 0.5% away from the calculated max-pain strike — if spot is already pinned, there is no convergence to capture. Second, spot must be within 3.5% of max pain — beyond that, the pin force is too weak relative to the move required. Third, dealer net gamma must be positive (vol-suppressive) — confirmed via the GEX engine when an IV column is available, with an OI-concentration heuristic (≥ 1.5× median per-strike OI at the pin) as a fallback. Fourth, VIX must be ≤ 25 — high vol regimes break the pin because dealers cannot hedge a runaway move and the gamma profile flattens. The strategy explicitly does not enter on weekly expirations (lower OI, weaker pin), on weeks containing FOMC, CPI, or NFP releases on Friday (these macro events override the pin entirely), and during periods of broken term-structure where front-month vol exceeds longer expiries.

The structural cost of the trade is theta-positive (the writer of the body benefits from time decay) but vega-negative (the writer is short volatility). The largest risk to a max-pain pin is a directional surprise on Friday morning — a hot CPI print, an unexpected geopolitical headline, or a single-stock catalyst that overwhelms the dealer hedging dynamic. The defined wing structure caps the loss at (wing_width × 100 − credit) per contract regardless of how badly the move goes against the structure. Position sizing is calibrated to keep portfolio exposure to a single OpEx Friday at no more than 2% of capital, so even a maximum-loss expiration is a manageable drawdown rather than a portfolio-impairing event.

This is one of the most academically validated short-volatility microstructure strategies in equity options, and it is also one of the most overhyped on retail platforms — most retail "max pain" trades are undefined-risk single-strike bets that produce occasional large wins followed by inevitable catastrophic losses. The discipline of running it as a defined-risk butterfly with strict regime filters is the difference between a long-term edge and a quasi-lottery payoff distribution.

---

## How It Works

### Max-Pain Math

For each candidate expiration price P (we evaluate at every traded strike — the loss function is piecewise-linear in P with breakpoints at strikes, so the minimum is always realised at a strike), compute total intrinsic-value payout to all option holders:

```
payout(P) = Σ_K [ call_OI(K) × max(0, P − K) ]
          + Σ_K [ put_OI(K)  × max(0, K − P) ]

max_pain_strike = argmin_{P ∈ strikes} payout(P)
```

The intuition: when P moves above a heavy call-OI strike, dealers' aggregate short-call payout grows linearly. When P moves below a heavy put-OI strike, aggregate short-put payout grows. The price level that simultaneously minimises both linear losses sits at the strike where call OI and put OI roughly balance, weighted by their distances from P. Dealer hedging flows are most balanced at this price, so spot tends to drift there as expiration approaches.

### Worked Example

Consider an SPY-style chain on the Monday of an OpEx week with the underlying at $478, expiring Friday:

| Strike | Call OI | Put OI | Payout @ P=475 | Payout @ P=476 | Payout @ P=477 | Payout @ P=478 | Payout @ P=479 |
|-------:|--------:|-------:|---------------:|---------------:|---------------:|---------------:|---------------:|
|  $470  |    8,000 |  6,000 |  $40,000 (calls) +  $0 (puts) = $40k | $48k | $56k | $64k | $72k |
|  $475  |   12,000 | 10,000 |   $0 + $0 = $0 | $12k | $24k | $36k | $48k |
|  $477  |   18,000 | 22,000 |   $0 + $44k = $44k | $22k | $0 | $18k | $36k |
|  $480  |   14,000 | 16,000 |   $0 + $80k = $80k | $64k | $48k | $32k | $16k |
|  $485  |    9,000 |  8,000 |   $0 + $80k = $80k | $72k | $64k | $56k | $48k |
| **TOTAL** | | | **$244k** | **$218k** | **$192k** | **$206k** | **$220k** |

In this stylised example the minimum payout is at P = $477 (= max-pain strike). With spot at $478 and max pain at $477, the spot–pin distance is $1 / $478 = 0.21% — too tight to enter (below the 0.5% minimum). If on Tuesday spot rallies to $481, the distance becomes 0.84%, well within the entry band, and the trade fires.

### Structure Built at Entry

```
Underlying:        SPY, spot = $481.00, Tuesday of OpEx week (3 DTE)
Max-pain strike:   $477  (computed live from chain OI)
Wing width:        wing_width_pct × spot = 0.015 × $481 ≈ $7.20 → use $7

  Long  call wing K = $484         (body + wing, 0.62% above pin)
  Short call body K = $477  ── BODY at max pain
  Short put  body K = $477  ── BODY at max pain
  Long  put  wing  K = $470        (body − wing, 1.44% below pin)

Net credit (BS-priced, IV ≈ 14%):  $5.20 per share = $520 per contract
Max loss per contract:             ($7 wing − $5.20 credit) × 100 = $180
```

### Sizing & Risk Controls

```
Position size cap:        position_size_pct × capital  (default 2%)
Contracts:                floor(risk_budget / max_loss_per_contract)
                          = floor($2,000 / $180) = 11 contracts
Total max loss:           11 × $180 = $1,980  (1.98% of $100k capital)
Total credit collected:   11 × $520 = $5,720
```

### Exit Rules (first trigger wins)

1. **Friday OpEx close** — primary exit. Theta has done its job; close at intrinsic value.
2. **Profit target** — close at +50% of received credit (dealer-pin trades rarely reach max profit early; this saves transaction costs by not chasing the last decile of credit).
3. **Stop loss** — close when current cost-to-close ≥ 2× original credit (a directional shock is breaking the pin; cap the bleed).

---

## Illustrative Trade Walk-Throughs

> **Note:** The two scenarios below are *stylised, hand-constructed illustrations* of how
> the structure behaves — they are NOT recorded live fills or backtest output, and the
> dates/prices are invented for teaching. The dollar figures were computed at a single flat
> IV; the implemented backtest prices each leg with a volatility-skew model (OTM wings priced
> off a skew-adjusted IV via the engine's `bs_price_skew`/`effective_iv`), so realised credits
> and P&L will differ from the numbers shown. Treat these as intuition pumps, not performance
> claims. **TODO:** replace with a real backtest trade log once an options-snapshot history is
> run through the engine.

### Example 1 — Stylised OpEx Win

> **Entry:** Tuesday Mar 12 2024, 14:30 ET · **SPY:** $511.40 · **VIX:** 14.8 · **OpEx Friday:** Mar 15 2024 (3 DTE)
> **Macro calendar:** Quiet — no FOMC/CPI/NFP through expiry

**Chain OI snapshot (top strikes by aggregate OI, Mar 15 expiry):**

```
Strike    Call OI    Put OI    Total OI
$508       42,100    51,800     93,900
$510       38,400    44,200     82,600
$507       28,200    36,400     64,600   ← max-pain strike
$512       45,300    18,800     64,100
$515       58,800     8,400     67,200
```

Calculated max pain: **$507**. SPY spot $511.40, distance = 0.86% — inside the [0.5%, 3.5%] band. GEX positive (dealers net long gamma — confirmed via gex_engine). VIX 14.8 well under 25 ceiling. All filters pass.

**Trade entered:**
```
Long  $515 C / Short $507 C / Short $507 P / Long $499 P (wing width = $8)
Credit per contract: $5.85   Max loss per contract: $215
Contracts: floor(2,000 / 215) = 9    Total credit: $5,265   Max loss: $1,935
```

**Friday Mar 15 close:** SPY $510.92. Settlement value of structure:
- Short call $507 → settles at $3.92 ITM; long call $515 → $0
- Short put  $507 → $0 (OTM); long put $499 → $0
- Net cost to settle = $3.92 per share = $392 per contract
- Per-contract P&L = $585 − $392 = +$193 (35% of max profit)

**Total P&L: 9 × $193 − $23.40 commission ≈ +$1,714 (+1.7% on capital)**

The pin worked as advertised: spot drifted from $511.40 (Tue) to $510.92 (Fri close) toward the $507 max-pain strike. Final spot was $3.92 above the pin — far enough from the body that the short call was ITM, but well inside the long call wing.

### Example 2 — Stylised OpEx Loss (Directional Shock)

> **Entry:** Tuesday Jan 16 2024, 13:45 ET · **SPY:** $475.20 · **VIX:** 13.4 · **OpEx Friday:** Jan 19 2024 (3 DTE)
> **Macro calendar:** No data through expiry — but Wednesday brought an unexpected hawkish Fed speech

**Calculated max pain:** $477 (heavy call OI above and put OI below — mid-chain pin). Spot $475.20, distance = 0.38% — *just below* the 0.5% minimum. In a strict implementation this trade should NOT have fired; the example illustrates what happens when the filter is loosened.

**Trade entered (loose filter set, min_dist_pct lowered to 0.003):**
```
Long  $484 C / Short $477 C / Short $477 P / Long $470 P (wing width = $7)
Credit per contract: $4.95   Max loss per contract: $205
Contracts: 9    Total credit: $4,455   Max loss: $1,845
```

**Wed Jan 17:** Hawkish Powell remarks send SPY down 0.7% to $471.80. Spot below pin by $5.20.
**Thu Jan 18:** Continued selling on tighter financial-conditions narrative; SPY closes $469.40.
**Fri Jan 19 close:** SPY $471.10 — $5.90 below the $477 pin, almost at the long-put wing.

Settlement of structure:
- Short put $477 → settles at $5.90 ITM; long put $470 → $1.10 ITM
- Short call $477 → $0; long call $484 → $0
- Net cost to settle = $5.90 − $1.10 = $4.80 per share = $480 per contract
- Per-contract P&L = $495 − $480 = +$15 — *just barely* positive

**Total P&L: 9 × $15 − $23.40 commission ≈ +$112**

The trade survived only because the long put wing absorbed the move just inside its strike. Had SPY closed $1 lower at $470.10, the per-contract P&L would have been $495 − $590 = −$95 × 9 = −$855, plus commission a ~$880 loss. The lesson: when spot is too close to max pain at entry, the dealer hedging flow is already exhausted and any directional shock dominates. This is exactly why the strategy enforces min_dist_pct ≥ 0.5%.

---

## Entry Checklist

- [ ] Today is in an OpEx week (3rd-Friday-of-month week)
- [ ] DTE to OpEx Friday is in [entry_dte_min, entry_dte_max] = [2, 5] calendar days (defaults → roughly Mon–Wed of OpEx week; Thursday/DTE-1 is excluded by the default min of 2)
- [ ] Computed max-pain strike using full chain expiring on this OpEx Friday only (no future leakage)
- [ ] Spot–pin distance: 0.5% ≤ |spot − K_mp| / spot ≤ 3.5%
- [ ] Net dealer GEX is positive (dealers net long gamma, vol-suppressive) — via gex_engine
- [ ] OR (fallback) OI at max-pain strike ≥ 1.5× median per-strike OI in the chain
- [ ] VIX ≤ 25
- [ ] No FOMC, CPI, NFP, PCE, or major Fed speech scheduled through OpEx Friday close
- [ ] Body strike sits at a real, liquid traded strike (SPY 1-pt grid, NDX 5-pt grid)
- [ ] Wing-width chosen so net credit ≤ wing_width × 100 (no-arb)
- [ ] Max-loss × contracts ≤ position_size_pct × capital (default 2%)

---

## Risk Management

**Defined-risk structure.** Max loss per contract is bounded at (wing_width × 100 − credit). For a $1.50 wing with $0.50 credit, max loss = $100 per contract. This is the worst-case at expiration regardless of how badly the move goes against you.

**Position sizing.** Total max loss (max_loss_per_contract × contracts) must be ≤ position_size_pct × capital. Default 2% per trade caps the per-OpEx drawdown at 2% of equity.

**Stop-loss.** Close when the unrealised loss reaches `stop_loss_mult` × original credit, *clamped to just inside the structure's bounded max loss*. This clamp matters: a defined-risk butterfly can never lose more than (wing − credit) per share, so an un-clamped "2× credit" stop is frequently unreachable (e.g. a $7 wing with a $5 credit caps the loss at $2/share, while 2× credit = $10/share would never trigger). The implementation therefore stops at `min(stop_loss_mult × credit, 0.95 × max_loss_per_share)`, guaranteeing the stop fires before max loss is realised. **TODO:** the fraction of losing trades the stop actually catches, and the average loss-at-stop, should be reported from a real backtest rather than asserted.

**No averaging-down.** If the market moves against the structure, do not add contracts. The pin either holds or it doesn't — adding size to a broken pin is throwing good money after bad.

**Leg-out only as last resort.** If only the call side is in trouble (spot far above pin), buying back just the short call leaves a credit put-wing that pays modestly. This is a manual adjustment for experienced traders only — the systematic version of the strategy closes the entire structure on the stop trigger.

**Concurrent-OpEx limit.** Maximum 1 active max-pain trade at a time. Pin trades are correlated (single OpEx Friday is a single event); stacking concurrent positions on the same expiry concentrates rather than diversifies risk.

---

## When to Avoid

1. **Macro release on OpEx Friday.** A Fed decision, CPI print, NFP report, or PCE release scheduled for the OpEx Friday morning will easily overwhelm the pin. The 8:30am ET print is in the wrong direction perhaps half the time, and even a "soft" print can cause a 0.5–1.0% gap that puts the structure at maximum loss before the pin has any time to operate.

2. **VIX > 25.** High implied vol means dealers' gamma profiles are flatter, the actual realised range is wider, and the pin force is overwhelmed by realised volatility. Note that Ni/Pearson/Poteshman (2005) is a single-stock expiration-clustering study, not a VIX-percentile result — the VIX ceiling used here is a conservative regime filter layered on top of that intuition, not a number taken from the paper. **TODO:** confirm the VIX threshold at which the index-level pin degrades from a backtest.

3. **Earnings concentration in OpEx week.** When 3+ mega-cap names (AAPL, MSFT, AMZN, NVDA, GOOGL, META) report inside the OpEx week, single-stock moves dominate the index; the index-level pin is unreliable.

4. **Quarterly OpEx (Mar/Jun/Sep/Dec) with quad-witching.** While these expirations have the highest aggregate OI, they also see the largest hedge-roll flows and end-of-quarter rebalancing. The pin can either be very strong (largest OI) or very weak (rebalance flow swamps it). Run conservative sizing here.

5. **Holiday-shortened OpEx weeks.** When OpEx Friday is preceded by a market holiday (e.g. Good Friday in some years), the dealer hedging window is compressed and the pin effect is materially weaker. Skip these weeks.

6. **Front-month VIX backwardation.** If VIX9D > VIX1M > VIX3M, the term structure is in stress backwardation and short-vol structures are inappropriate regardless of any pin signal.

7. **Single-stock chains thinner than ~10,000 contracts at the pin strike.** The pin effect is OI-driven; below this threshold the dealer hedging is too small to move a stock noticeably. SPY, QQQ, IWM, and the largest single names (AAPL, NVDA, TSLA) almost always clear this bar; mid-caps usually do not.

---

## Strategy Parameters

| Parameter             | Default | Range       | Rationale                                                              |
| --------------------- | ------: | ----------- | ---------------------------------------------------------------------- |
| min_dist_pct          |  0.005  | 0.001–0.020 | Below 0.5% the pin has no convergence to capture (spot already pinned) |
| max_dist_pct          |  0.035  | 0.010–0.060 | Above 3.5% the pin force is too weak relative to the required move    |
| vix_ceiling           |  25.0   | 14.0–40.0   | Above this, the pin breaks; dealer hedging cannot suppress realised vol |
| wing_width_pct        |  0.015  | 0.005–0.040 | 1.5% of spot per wing — balances credit collected vs defined max loss  |
| entry_dte_min         |  2      | 1–4         | At least 2 DTE so theta has a meaningful contribution                  |
| entry_dte_max         |  5      | 4–7         | At most 5 DTE so we are in OpEx week (Mon → Thu of 3rd-Fri week)       |
| profit_target_pct     |  0.50   | 0.20–0.90   | 50% of credit captures the bulk of theta; reduces gamma risk in last day|
| stop_loss_mult        |  2.0    | 1.0–4.0     | 2× credit stops most losing trades at ≤ 50% of max loss                |
| position_size_pct     |  0.02   | 0.005–0.05  | 2% of capital max per OpEx — caps single-event drawdown                |
| require_positive_gex  | True    | bool        | Hard gate: dealers must be net long gamma for the pin to operate       |
| slippage_per_leg      |  0.05*  | 0.02–0.10   | Per-share per-leg slippage. *Default now inherits the engine-wide `DEFAULT_SLIPPAGE_PER_LEG`; the 0.05 shown is the fallback if the engine does not expose it. Applied on BOTH entry and exit, per leg × contracts. |
| commission_per_leg    |  0.65*  | 0.50–1.00   | Per-leg commission. *Default now inherits the engine-wide `DEFAULT_COMMISSION_PER_LEG` (fallback 0.65). 4 legs at open + 4 at close, scaled by contract count. |

### Example Parameter Profiles

```
                       Conservative      Standard         Aggressive
─────────────────────  ──────────────    ──────────────   ──────────────
min_dist_pct           0.008 (0.8%)      0.005 (0.5%)     0.003 (0.3%)
max_dist_pct           0.025 (2.5%)      0.035 (3.5%)     0.045 (4.5%)
vix_ceiling            20                25               30
wing_width_pct         0.020 (2.0%)      0.015 (1.5%)     0.010 (1.0%)
position_size_pct      0.010 (1%)        0.020 (2%)       0.035 (3.5%)
profit_target_pct      0.40              0.50             0.65
stop_loss_mult         1.5               2.0              2.5
require_positive_gex   True              True             False
```

---

## Data Requirements

**Price data (primary ticker):**
- Daily OHLCV for the underlying (SPY, QQQ, IWM, or large-cap single names with dense option chains)
- At minimum, intraday close for backtesting; intraday-by-the-minute is not required because the trade enters on Mon/Tue close and exits on Friday close

**Options chain snapshots (auxiliary_data["option_snapshots"]):**
- Per-snapshot rows with at least: strike, option_type (call/put), open_interest (or volume as fallback), implied_volatility, expiry, and a SnapshotDate column tagging the chain to a calendar date
- Coverage: every business day in the backtest window, full chain for the upcoming OpEx Friday expiry
- The strategy filters the snapshot down to only the chain expiring on the next 3rd-Friday OpEx — no other expiries are used in the max-pain calculation, eliminating mixed-expiry leakage

**VIX series (auxiliary_data["vix"]):**
- Daily close for the VIX index, indexed by date
- Used solely for the VIX entry filter; if missing, VIX defaults to 20.0 (the long-run mean) and the filter is effectively disabled

**Macro calendar (recommended):**
- A Boolean per-date series flagging FOMC, CPI, PCE, NFP, and major Fed speech days
- The strategy does not yet auto-skip on macro days — this is a manual overlay; future versions will integrate the calendar directly

**No look-ahead.** The chain snapshot used at entry on date T contains only options data observable as of T (open interest, IV, volume from the prior session's settlement). The max-pain strike is computed strictly from this snapshot. Friday close is observed only at exit.
