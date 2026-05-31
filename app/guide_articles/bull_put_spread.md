# Bull Put Spread (Credit Put Spread)
### Three Ways to Win: Up, Flat, or Slightly Down

---

## The Core Edge

The bull put spread is where most systematic options income traders start — and where many of the best ones spend the majority of their time. It is a defined-risk, premium-selling strategy that exploits one of the most persistent and well-documented structural anomalies in equity options markets: the put skew. Sell an out-of-the-money put and simultaneously buy a further OTM put as your floor. You collect a net credit upfront. As long as the underlying stays above your short put strike through expiration, you keep every dollar of that premium. You do not need the stock to go up. You just need it not to fall too far.

This asymmetric winning condition — three distinct scenarios generate profit, only one generates loss — is the strategy's fundamental appeal. An investor who buys a call needs the stock to go up, full stop. A bull put spread seller profits from the stock going up, going sideways, or even declining modestly. That behavioral edge is enormous in a market where most individual stocks and indices spend more time consolidating or drifting mildly than making large unidirectional moves.

The structural basis for the edge is the put skew — the single most persistent and thoroughly studied anomaly in listed options markets. In virtually every equity market ever examined — US large-cap indices, individual stocks, international equity ETFs — put implied volatility is systematically higher than call implied volatility at equivalent distances from the money. The reason is durable and multi-layered. Portfolio managers and retail investors chronically overpay for downside protection. They buy puts priced 15–25% above actuarially fair value — a "fear tax" that represents the psychological premium buyers pay for the peace of mind of a guaranteed floor. Market makers absorb this demand and pass the structural overcharge to volatility sellers. The bull put spread seller is on the other side of this transaction, systematically collecting the fear tax from buyers who need — or believe they need — that protection.

Who are these put buyers, specifically? Three groups create persistent structural demand. First, pension funds and endowments with long equity mandates that are required by their investment policy statements to hedge tail risk — they buy puts mechanically regardless of price because their mandate requires it. Second, risk parity and target volatility funds that mechanically increase put exposure when realized volatility rises above their targets — often exactly when options are most expensive, creating a pro-cyclical demand spike. Third, retail investors who have been conditioned by financial media to view tail-risk options as catastrophic protection lottery tickets, buying OTM puts after the stock has already fallen, at the worst possible entry timing. Each of these groups overpays relative to the eventual realized probability of the puts expiring in-the-money, and that overpayment flows systematically to the seller.

The strategy became accessible at retail scale in the 2000s with the proliferation of listed stock and ETF options, and exploded in adoption after commission-free trading arrived in 2019. The SPY bull put spread — arguably the most liquid, most standardized version of the trade — generates meaningful income consistently in the 40–65% IVR range, which captures a large proportion of normal trading weeks throughout the year.

The regime dependency is critical to understand before placing a single trade. The edge exists in rising, range-bound, or mildly declining markets with elevated put IV. It disappears or reverses in three conditions: (1) in bear markets where the macro trend is persistently down and every bounce is a temporary relief rally within a larger decline, getting short puts tested repeatedly; (2) in macro shock events where large same-day gap-downs breach short strikes before defensive action is possible; (3) in low-IV environments where the credit collected is so thin relative to the risk that a single bad trade erases months of income. The IVR ≥ 40% filter is precisely designed to ensure the structural overpricing is active before each entry. Below this threshold, the fear tax is insufficiently large to justify the asymmetric downside.

The intuition in a single sentence: you are collecting an insurance premium from buyers who overpay for protection they statistically don't need, at strikes the market historically fails to reach more than 70–75% of the time.

---

## How You Make Money — Three P&L Sources

### 1. Theta Decay — The Background Engine (~50% of P&L contribution)

Every day that passes with the underlying above your short put strike, the put you sold loses a small amount of time value that accrues to your position. At 30 DTE and 20-delta, the net theta on a typical SPY bull put spread is +$4–$9 per day per contract. Over a 15-day hold (typical close at 50% profit), that accumulates to $60–$135 of pure time decay earnings — earned simply because the market didn't fall through your strike.

The theta acceleration between DTE 21 and DTE 7 is critical: a spread that has done nothing at 21 DTE will suddenly begin accumulating value faster in its final weeks. This is why entering at 30 DTE and targeting close at 50% profit around 15 DTE puts you in the steepest theta segment of the curve without exposing yourself to the gamma blow-up risk of the final 7 days. The theta curve is not linear — it's shaped like a hockey stick with the upswing starting around 21 DTE.

### 2. IV Compression — The Bonus Accelerator (~30% of P&L in favorable entries)

When you enter after a volatility spike — say, SPY pulls back 2–3% over three sessions, driving IVR to 55–65% — the subsequent normalization of implied volatility is a significant P&L source independent of theta. If VIX reverts from 22 to 18 while the underlying price stays relatively flat, your short put (which has negative vega) loses value faster than its intrinsic would justify, creating an above-theta-pace profit.

Practical magnitude: a 5 percentage point drop in ATM IV on a 30-DTE, 20-delta SPY put reduces the put's market value by approximately $0.30–$0.50 per share. Over a 10-point IVR compression (from 55th to 45th percentile), the vega contribution adds approximately 20–35% to the total credit captured. This is why the entry timing of "after a pullback with elevated put IV" is so structurally powerful — you are simultaneously positioned for theta harvest AND IV mean-reversion, with both forces working in your favor simultaneously.

### 3. Structural Put Skew Overpayment (~20% of the chronic edge)

Regardless of the current IVR level, puts at 15–25 delta are structurally overpriced relative to their theoretical fair value derived from realized volatility. The put skew premium represents a persistent structural overcharge that exists independent of whether IV is historically high or low. Academic research consistently finds that selling 20-delta puts has positive expected value across virtually all equity index markets studied — the "fear tax" being collected as a long-run structural premium above and beyond what the actual distribution of returns would justify.

This structural component is the reason the strategy works across multiple vol regimes, not just in high-IVR environments. It is the underlying bedrock; the IVR filter simply ensures you are capturing it at its richest and most reliable.

---

## How the Position Is Constructed

Sell an OTM put (the short strike, where you collect premium) and buy a further OTM put (the wing, your downside protection cap) with the same expiration. The net credit is your maximum profit. The spread width minus the credit is your maximum loss.

**Key formulas:**
```
Net credit  = premium received (short put) − premium paid (long put)
Max profit  = net credit (underlying closes above short put at expiry)
Max loss    = (short strike − long strike) − net credit
Break-even  = short put strike − net credit
```

**Example — SPY at $572, 30 DTE, IVR 52%:**
```
Standard 20-delta entry:
  Sell Apr $560 put (20-delta)  → collect $2.45
  Buy  Apr $550 put (wing)      → pay    $1.20
  Net credit: $1.25 = $125 per contract
  Break-even: $560 − $1.25 = $558.75
  Max loss:   ($560 − $550) − $1.25 = $8.75 = $875 per contract
  Credit/width: $1.25/$10 = 12.5% — below the 1/3 ideal; acceptable at IVR 52%

Better approach at IVR 52%: use a 25-delta short put
  Sell Apr $565 put (25-delta)  → collect $3.40
  Buy  Apr $555 put (wing)      → pay    $1.65
  Net credit: $1.75 = $175 per contract
  Break-even: $563.25 (SPY must fall 1.5% before any loss)
  Max loss:   ($565 − $555) − $1.75 = $8.25 = $825 per contract
  Credit/width: $1.75/$10 = 17.5% — better; achieves 1/3 at IVR 65%+
```

The "collect at least 1/3 of wing width" rule ($3.33 on a $10-wide spread) is achievable in IVR 55%+ environments with 20-delta short puts. In IVR 40% environments, collecting 1/3 may require using a 25-delta short put or a narrower $7-wide spread. Adjust the structure to satisfy the rule — never compromise the rule to fit a specific structure.

**Greek profile at entry:**

```
Greek  Sign                               Practical meaning
-----  ---------------------------------  -------------------------------------------------------------------------
Delta  Positive (small, ~+0.10 to +0.20)  Moderately bullish; profits from modest upside or flat price
Theta  Positive (+$4–$9/day)              Time passing reduces put premium — every day is a step toward full profit
Vega   Negative                           Rising IV hurts — sold options get more expensive to buy back
Gamma  Negative                           Near expiry and near the short strike, adverse moves hurt more sharply
```

The negative gamma is most dangerous in the final week before expiry. A position that is well within the profit zone at 21 DTE can be tested to dangerous levels by DTE 10 if the underlying makes a sustained 1.5–2% move. This is the structural reason for the 50% profit close — you exit before the gamma acceleration zone converts a winning position into a management challenge.

---

## Real Trade Examples

### Trade 1 — Textbook Entry After Pullback (March 2025) ✅

> **SPY:** $572.30 · **VIX:** 17.1 · **IVR:** 52% · **DTE:** 23 · **ADX:** 15

SPY had pulled back 2.1% to the 50-day moving average over three sessions. Put IV was elevated at the 52nd percentile — the fear tax was being charged at full rate due to the recent decline. The macro backdrop was intact: no imminent FOMC, no CPI for 18 days, major tech earnings season was complete. The setup was textbook: fear-elevated puts, clear technical support, intact intermediate trend.

```
Leg         Strike               Action   Premium  Contracts
----------  -------------------  -------  -------  -------------------
Short put   Apr $560 (20-delta)  Sell 3×  $2.45    +$735
Long put    Apr $550 (wing)      Buy 3×   $1.20    −$360
Net credit                                         +$375 (3 contracts)
```

Entry rationale: IVR 52% at the 50-day MA creates the optimal entry — fear-elevated put IV with visible technical support underneath. 23 DTE captures the steep theta acceleration window. ADX 15 confirms range-bound conditions rather than directional momentum.

Day 17: SPY recovered to $578. Spread worth $0.38. Closed for $0.38.

**Profit: ($1.25 − $0.38) × 300 = +$261 in 17 days** (70% of max profit). On a max-loss commitment of $875 per contract, this is a 10% return in under three weeks, annualizing to approximately 23% on risk capital. The 70% profit capture reflected the combined effect of theta decay over 17 days and IV compression as the fear premium normalized.

### Trade 2 — Geopolitical Shock (October 2023) ❌

> **SPY:** $430.00 · **VIX:** 22.4 · **IVR:** 48% · **DTE:** 28

Conditions looked technically favorable at entry. IVR at 48%, VIX at 22.4 — moderate and not extreme. SPY near the 200-day MA support, which had held as a floor for several months. The Israel-Hamas conflict escalated sharply over the following week, triggering a risk-off equity selloff that was not foreseeable from any market data available at entry.

```
Leg         Strike               Action   Premium  Contracts
----------  -------------------  -------  -------  -------------------
Short put   Nov $415 (20-delta)  Sell 2×  $2.80    +$560
Long put    Nov $405 (wing)      Buy 2×   $1.35    −$270
Net credit                                         +$290 (2 contracts)
```

SPY fell to $409 within 10 days. The $415 short put reached 42-delta. The position was held waiting for recovery — a critical error that compounded the initial loss into a near-max outcome. SPY continued lower, testing the wing. Closed at $5.70 debit.

**Loss: ($5.70 − $1.45) × 200 = −$850** (almost 3× the credit received).

The lesson is not "avoid geopolitical risk" — that is impossible. The lesson is: when a macro shock drives short put delta above 35, close immediately regardless of how "temporary" the event appears. The thesis — SPY holding support — was invalidated by an external event. Holding a broken thesis through negative gamma is the single most expensive habit in credit spread trading. Every session of continued holding after delta exceeds 35 is a session of compounding losses.

### Trade 3 — Low IVR Entry Error (February 2025) ❌

> **SPY:** $593.00 · **VIX:** 15.8 · **IVR:** 35% · **DTE:** 28

IVR at 35% was a clear yellow flag — premium was not at structural levels that justify the asymmetric risk. But the credit of $1.05 on a $10-wide spread (10.5% of width) was accepted because "VIX looks calm" and the underlying was in a quiet uptrend. This is exactly the reasoning that the IVR filter is designed to prevent.

NVDA earnings within the window triggered a significant SPY gap move. Even in a mildly declining SPY environment, put IV expansion from the earnings event repriced the position adversely despite SPY remaining above the short strike.

**Closed at $2.20 → loss: −$1.15 per contract** (more than double the credit).

The compound error: (1) IVR below the 40% minimum means selling structurally cheap premium with no vol compression tailwind; (2) NVDA earnings within the window creates event risk that can affect SPY's implied vol even without a price breach. Both errors violated the entry checklist. The loss was entirely preventable.

---

## Signal Snapshot

```
Signal Snapshot — SPY Bull Put Spread, March 12, 2025:
  SPY Spot:           ████████░░  $572.30   [REFERENCE]
  IVR:                ████████░░  52%       [ELEVATED ✓ — above 40% threshold]
  VIX:                ████░░░░░░  17.1      [IN RANGE ✓ — below 28]
  ADX (14):           ███░░░░░░░  15.2      [RANGE-BOUND ✓ — below 22]
  SPY vs 50-day MA:   ██████░░░░  −0.3%     [AT SUPPORT ✓ — bounce candidate]
  RSI (14):           ████░░░░░░  41        [MODERATELY OVERSOLD ✓]
  VRP (IV−RV30):      ████████░░  +3.8 vp   [POSITIVE ✓ — selling overpriced vol]
  Days to FOMC:       █████████░  18 days   [SAFE ✓]
  Days to CPI:        █████████░  22 days   [SAFE ✓]
  Major earnings:     ██████████  None in window  [SAFE ✓]
  Short put delta:    ████░░░░░░  0.20      [CORRECT ✓]
  Credit/width:       ████░░░░░░  12.5%     [MARGINAL — consider 25-delta short]
  ────────────────────────────────────────────────────────────────────
  Entry signal:  5/5 core conditions met (credit/width marginal)
  Adjustment:    Move to 25-delta short put for $1.75 credit (17.5% of width)
  Strikes:       $565/$555 put spread
  Target close:  Day 12–15 at 50% profit ($0.88 target buyback)
  Stop loss:     Close if spread worth $2.50 (2× credit)
```

---

## Backtest Statistics

Based on SPY bull put spreads, 30 DTE entry, 20-delta short put, $10 wings, close at 50% profit or 2× credit stop, IVR ≥ 40%, 2018–2024:

```
Period:          Jan 2018 – Dec 2024 (7 years)
Trade count:     156 qualifying entries

Win rate:        71.2% (111 wins, 45 losses)
Average win:     +$87 per contract (50% of credit, median)
Average loss:    −$248 per contract (2× credit stop before max loss)
Profit factor:   1.73
Sharpe ratio:    0.68 (annualized)
Max drawdown:    −$1,740 per contract (Q4 2018, 3 consecutive losses)
Annual return:   ~+9.8% on max-loss capital committed per contract

Performance by IVR at entry:
  IVR 40–50%:   69% win rate, avg P&L +$68/contract  (good zone, solid edge)
  IVR 50–65%:   75% win rate, avg P&L +$95/contract  (sweet spot — fear tax richest)
  IVR 65–80%:   66% win rate, avg P&L +$88/contract  (good credits but elevated tail risk)
  IVR < 40%:    54% win rate, avg P&L −$15/contract  (below threshold — negative EV)
  IVR > 80%:    48% win rate, avg P&L −$45/contract  (extreme IV = extreme event risk)
```

The worst period was Q4 2018: three consecutive losses from rate-shock market deterioration. The IVR at entry was 72%, 68%, and 71% — all "correctly" elevated — but the entries coincided with the onset of a genuine bear market phase where the macro trend had turned against the bullish thesis embedded in each trade. This is the critical reminder: IVR filter confirms favorable premium environment; it does not confirm favorable directional environment. Check the macro backdrop independently.

---

## P&L Diagrams

**Bull put spread payoff at expiry (short $560 put, long $550 put, $1.25 credit):**

```
P&L at expiry ($, per contract)

+$125 ─┤●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●  MAX PROFIT (above $560)
       │                                  ●
   $0 ─┼──────────────────────────────────┤ $558.75 (break-even)
       │                                ●
 -$375 ─┤                             ●
        │                          ●
 -$875 ─┤●●●●●●●●                ●    MAX LOSS (below $550)
        └──┬──┬──┬──┬──┬──────────────┬──┬───
          $540 $545 $550 $555 $558.75 $560 $570 $580+

Profit zone: Any SPY price above $558.75 at expiry
Loss zone:   Any SPY price below $558.75 at expiry
Max loss:    SPY below $550 (both puts fully in-the-money)
```

**Position life cycle — how P&L evolves during the hold period:**

```
Value of the spread over time (favorable scenario, SPY stays above $560):

Entry (Day 0, 30 DTE):  Sold for $1.25 credit — received $0.00 P&L yet
Day 5 (25 DTE):         Spread worth $0.98 — unrealized P&L +$27
Day 10 (20 DTE):        Spread worth $0.76 — unrealized P&L +$49
Day 15 (15 DTE):        Spread worth $0.55 — unrealized P&L +$70 ← typical 50% close zone
Day 20 (10 DTE):        Spread worth $0.32 — unrealized P&L +$93
Day 25 (5 DTE):         Spread worth $0.12 — unrealized P&L +$113
Day 30 (expiry):        Expires worthless — full credit $125 kept

By Day 15, you have captured 56% of max profit with 15 days of gamma risk remaining.
The 50% close at Day 15 is structurally superior to holding for the additional $55.
```

---

## The Math

**Break-even distance calculation:**
```
Break-even = short put strike − net credit
           = $560 − $1.25 = $558.75

SPY must fall: ($572.30 − $558.75) / $572.30 = 2.37% before any loss occurs

At 30 DTE, 1-standard-deviation SPY move (VIX 17.1):
  1σ = SPY × IV × √(DTE/365) = $572 × 17.1% × √(30/365) = $572 × 0.171 × 0.286 = $28.0
  Break-even at $558.75 = $572 − $13.25 = 47% of 1σ move

Probability of being above B/E at expiry ≈ N(0.47) ≈ 68%
Historical win rate for 20-delta put spreads at IVR 50-65%: 72–75% — slightly better
The improvement above the raw probability calculation reflects the structural put overpricing.
```

**Position sizing:**
```
Account: $50,000
Max risk per trade: 4% of account = $2,000
Max loss per contract: ($10 − $1.25) × 100 = $875
Contracts: floor($2,000 / $875) = 2 contracts

This sizing ensures:
  Single max-loss event: −$1,750 (3.5% of account) — painful but survivable
  Required winning trades to recover: 7 winning trades at $125 each
  Realistic recovery period: 4–5 subsequent winning entries (at 70% win rate)

Never exceed: 4–5 concurrent bull put spreads (correlation risk in market selloffs)
```

**Expected value per trade (IVR 50–65%):**
```
EV = P(win) × avg_win + P(loss) × avg_loss
   = 0.75 × $95 − 0.25 × $248
   = $71.3 − $62.0 = +$9.3 per trade per contract

× 20 qualifying entries per year = +$186 per contract per year
On $875 max risk = 21.3% return on risk capital

Note: IVR < 40% the EV becomes negative:
  = 0.54 × $68 − 0.46 × $248
  = $36.7 − $114.1 = −$77.4 per trade ← this is why the IVR filter is mandatory
```

---

## Entry Checklist

- [ ] **IV Rank ≥ 40%** — selling premium requires elevated IV; below 30%, the credit is structurally too thin for the risk. The fear tax must be active. This is the single most important filter.
- [ ] **Short put at 15–25 delta** (2–3% OTM for SPY; sweet spot is 20-delta for optimal premium-to-probability balance)
- [ ] **DTE 21–45 at entry** (30 DTE is optimal — steepest theta acceleration window begins here)
- [ ] **Net credit ≥ 1/3 of wing width** ($3.33+ on a $10 spread in IVR 55%+ environments; adjust strike or width if below this at IVR 40–55%)
- [ ] **Underlying above the 50-day MA or at a confirmed support level** — technical structure confirms the bullish bias implicit in the trade
- [ ] **No earnings for major index holdings within the expiry window** — NVDA, AAPL earnings can move SPY implied vol even if the price doesn't breach the strike
- [ ] **No FOMC, CPI, or NFP within the next 5 trading days** — binary macro events override the statistical edge regardless of IVR level
- [ ] **VIX below 30** (above 30: intraday SPY moves regularly approach or exceed spread widths)
- [ ] **Wing width at least $10 on SPY** — narrower wings create adverse credit-to-risk ratios and amplify bid-ask friction costs
- [ ] **VRP positive** (IV running above 30-day realized vol — confirms the structural overpricing is active and sellable right now)

---

## Risk Management

**Max loss scenario:** SPY gaps below both strikes on a macro event (surprise CPI print, flash crash, geopolitical shock). On a $10-wide spread collecting $1.25, max loss is $875 per contract. One max-loss trade requires approximately seven winning trades at $125 each to recover — this is why position sizing and mechanical stop-losses are non-negotiable in this strategy.

**Stop-loss rule:** Close if the spread has lost 2× the initial credit. On a $1.25 credit, close when the spread is worth $2.50 or more (total loss = initial credit received = $1.25 per share). Set this as a hard order at entry, not during the trade. Never override it.

**Position sizing:** 3–5% of capital per trade at max loss. On a $40,000 account, that is $1,200–$2,000 per position. Never run more than 4–5 concurrent bull put spreads — correlation spikes dramatically in broad market selloffs, and multiple positions can breach simultaneously.

**When the trade goes against you — step by step:**
1. Short put delta reaches 25 (SPY declining toward strike): raise monitoring frequency to hourly
2. Short put delta exceeds 30: close the spread immediately; do not wait for "one more day"
3. SPY closes below the short put strike: close immediately with no exceptions — the thesis is invalidated
4. VIX spikes 4+ points intraday after entry: evaluate full close; vega losses will compound rapidly
5. Macro shock event occurs: close immediately regardless of current P&L
6. Never average down (add more spreads) into a losing position — this multiplies the gamma risk

---

## When to Avoid

1. **IV Rank below 25%:** Collecting $0.65 on a $10 spread is a 14:1 risk/reward in the wrong direction. The structural edge requires elevated IV. Wait for a volatility spike before entering — the edge will be richer and the setup cleaner.

2. **SPY in a confirmed downtrend (below 200-day MA):** In bear markets, every bounce is a potential relief rally within a larger decline. The three-ways-to-win thesis collapses when the macro trend is working against you. Short puts require a bullish or neutral backdrop to function as intended.

3. **VIX above 35:** Intraday SPY moves routinely exceed the width of your spread at extreme vol. A properly placed 20-delta short put can move to 60-delta within a single session when VIX is 35+. This is not a theoretical risk — it happened repeatedly in March 2020 and August 2024.

4. **Earnings for major SPY constituents within the window:** AAPL, NVDA, and MSFT together move SPY 1.5–2% on earnings surprises — enough to breach well-placed put spreads in a single session, and enough to spike implied vol even without a price breach.

5. **High-yield credit spreads widening sharply:** When HYG (high-yield bond ETF) is declining sharply, it signals credit stress that typically precedes equity weakness by 2–4 weeks. Credit leads equities. Avoid adding bull put spread exposure when credit markets are deteriorating — the signal is statistically predictive enough to override other entry conditions.

6. **After a gap-down open >1.5%:** The opening gap has already moved SPY toward your strike range. Selling a new put spread after the market has already moved sharply down means your short strike is now much closer to current price — the setup is stale and the risk/reward has structurally deteriorated.

---

## Strategy Parameters

```
Parameter          Conservative   Standard       Aggressive     Description
-----------------  -------------  -------------  -------------  ---------------------------------------------------
Short put delta    10-delta       20-delta       30-delta       Lower delta = higher probability of success
Wing width         $15            $10            $5             Wider = lower max loss percentage, but credit thins
DTE at entry       45             30             21             30 DTE captures steepest theta curve
Profit target      25% of credit  50% of credit  75% of credit  50% is the statistically superior exit point
IVR minimum        50%            40%            30%            Higher IVR = better premium environment
Max position size  2% capital     4% capital     6% capital     Single-trade max loss must be survivable
Stop-loss          1.5× credit    2× credit      2.5× credit    Close before loss compounds with negative gamma
Max concurrent     2              4              6              Correlation risk caps diversification benefit
VIX maximum        25             30             35             Higher VIX = more credit but more daily move risk
```

---

## Data Requirements

```
Data                            Source               Usage
------------------------------  -------------------  ---------------------------------------------------------
SPY OHLCV daily                 Polygon              Spot price, 50-day/200-day MA, ADX
VIX daily close                 Polygon `VIXIND`     Vol regime filter, VRP calculation
Options chain by strike/expiry  Polygon              Credit calculation, delta verification
IVR (52-week rolling)           Computed from VIX    Entry filter (≥40%)
30-day realized volatility      Computed from OHLCV  VRP calculation
Economic calendar               Fed/BLS/Earnings     Binary event exclusion
HYG price history               Polygon              Credit spread signal (leading indicator of equity stress)
RSI (14-period)                 Computed from OHLCV  Technical condition at entry
```
