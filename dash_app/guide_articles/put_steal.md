# Put Steal — Short Stock Interest Arbitrage AI

> **Naming caveat (read first).** The strategy is *named* after the
> put-steal arbitrage of Barraclough & Whaley (2011), but it does not
> directly capture the put-steal flow. The literature trade requires
> selling **ITM** American puts (strike *above* spot); this strategy
> instead sells a defined-risk **OTM** bull put credit spread (strike
> *below* spot) gated by an NII regime signal computed at a hypothetical
> ITM strike. High NII at the hypothetical ITM strike correlates with
> high-rate, low-vol, stable-stock conditions that favor OTM-put-spread
> survival; the NII is therefore used as a covariate, not a source of
> harvested premium. A literal put-steal capture trade — selling deep-ITM
> American puts and waiting for forfeited NII — is a separate, more
> aggressive trade not implemented in this repo.

## What The Paper Found

**Barraclough & Whaley (2011), "Early Exercise of Put Options on Stocks"**

Examining every exchange-traded US stock put from **January 1996 through September 2008**:

| Statistic | Value |
|---|---|
| Total put contracts analyzed | 3.96 million outstanding |
| Puts that *should* have been exercised early but weren't | **3.7% of all outstanding puts** |
| Total dollar cost to retail put holders | **$1.9 billion** in foregone interest |
| Who captured this money | Market makers (47.2%) and proprietary firms (40.8%) |
| Retail customers who exercised correctly | 3.1% — almost none |

The paper documents **short stock interest arbitrage**: market makers systematically buy and sell equal numbers of deep ITM puts to capture the interest forfeited by longs who don't exercise. When an exercise arrives randomly (OCC assigns randomly), the short who gets assigned earns X in cash, earns one day's interest overnight, and re-shorts the put the next morning. By running large books of deep ITM puts, they collect the dominant share of the total $1.9B.

---

## The Early Exercise Decision Rule

For a deep in-the-money American put with strike **X** and time to expiry **T**, immediate exercise is optimal when:

$$NII = X(1 - e^{-rT}) - c(S, X, T, r, \sigma) > 0$$

Where:
- **X(1 − e⁻ʳᵀ)** = present value of interest earned by exercising now and investing the strike at the risk-free rate r
- **c(S, X, T, r, σ)** = Black-Scholes call price ("the caput") — the value of the *right to wait* before exercising

When NII > 0, exercising immediately beats waiting. A rational holder exercises. When they don't — which happens 3.7% of the time — the short captures the NII.

### Table I from the Paper — Net Interest Income Examples

Assuming: strike X = $50, DTE = 30, risk-free rate = 5% (annualised), volatility = 30%

| Stock Price | Put Value (exercise now) | American Put Value (wait) | NII (exercise benefit) |
|---|---|---|---|
| $41.50 | $8.50 | $8.50005 | ~$0.00005 (breakeven) |
| $41.00 | $9.00 | $9.00234 | −$0.002 (don't exercise yet) |
| $42.00 | $8.00 | $8.00000 | $0.00 (indifferent) |
| $39.00 | $11.00 | $11.00000 | +$0.00068 (exercise!) |
| $35.00 | $15.00 | $15.00000 | +$0.00685 (exercise!) |
| $30.00 | $20.00 | $20.00000 | +$0.00685 (exercise!) |

**Key insight from Table I:** The critical stock price S* ≈ $42.95 for these parameters — the *highest* stock price at which the put should be exercised. All stock prices *below* $42.95 should be exercised immediately. The maximum daily interest income on a $50 strike at 5% is $0.00685/share ($50 × 0.05/365).

### Maximum Daily NII

$$\text{Max daily NII} = X \times \frac{r}{365} = 50 \times \frac{0.05}{365} = \$0.00685/\text{share}$$

Over 30 days this compounds to: $50 × (1 − e^{−0.05×30/365}) = **$0.20506 per share** of maximum interest income.

---

## Why Retail Holders Don't Exercise

The paper finds exercise is suboptimal or irrational due to:

1. **Unawareness** — retail holders don't know they should exercise
2. **Continuous monitoring** — you must check every day whether NII > 0
3. **Transaction cost perception** — incorrectly believing exercise costs money
4. **Irrationality** — behavioral inertia, not wanting to close a profitable position

**By market participant (July 2001 – Sep 2008):**

| Participant | % of put exercises | % that were optimal |
|---|---|---|
| Market makers | 47.2% | High — systematic arb |
| Proprietary firms | 40.8% | High — systematic arb |
| Retail customers | 3.1% | Low — mostly irrational |
| Hedge funds | remaining | Mixed |

---

## The "Short Stock Interest Arbitrage" Game

Market makers and prop firms run a specific book:

1. Buy a deep ITM put (go long)
2. Simultaneously sell an equal deep ITM put (go short) — same strike, same expiry
3. Net position delta ≈ 0 (hedged)
4. Wait for exercises to be assigned
5. When a long holder fails to exercise → short earns one day's NII
6. When assigned (exercised against) → re-enter the position next morning

By holding large books of deep ITM puts, they are statistically guaranteed to capture the dominant share of total forfeited interest across the market.

**At retail scale** we can't run this exact book (requires combo orders + high-frequency monitoring). Instead we capture the same edge via a bull put spread — defined risk, RH-eligible, with the short put positioned where NII is likely to remain positive.

---

## Trade Structure

**Bull Put Credit Spread** (defined risk, Robinhood-eligible):

| Leg | Action | Strike | Role |
|---|---|---|---|
| Short put | SELL | Spot × (1 − itm_pct) | Captures forfeited premium |
| Long put | BUY | Short strike × (1 − wing_pct) | Defines max loss |

- **DTE target:** 21 days
- **Max profit:** Credit received × 100 (per spread)
- **Max loss:** (Wing width − credit) × 100 (per spread)
- **Breakeven:** Short strike − net credit

> **Costs & pricing.** The backtest charges both commission and slippage on
> every leg, on entry *and* exit, scaled by the number of contracts. Option
> legs are priced with a downside volatility skew (OTM puts carry higher IV),
> not a single flat ATM vol — so collected credits and marks are conservative
> and realistic.

### Example at Current Rates (~4.3%)

| Parameter | Value |
|---|---|
| Stock price (already pulled back) | $90 |
| Strike X (10% ITM) | $99 |
| Interest income (21 DTE) | $99 × (1 − e^{−0.043 × 21/365}) = **$0.246** |
| Caput at σ=20% | ~$0.01 (nearly zero — far OTM call) |
| **NII** | **+$0.236** (exercise immediately!) |
| Short put strike | $85.50 (5% below spot) |
| Long put strike | $82.10 |
| ~Credit | $1.40 |
| Max profit | $140/spread |
| Max loss | $1,260/spread |

---

## AI Filter Layer

The NII gate identifies *when* the structural edge is open. The GBM classifier predicts *whether the spread will survive* (stock stays above short strike for 21 days).

**13 features:**

| Category | Features |
|---|---|
| Interest arb signal | nii_level, nii_ma5, nii_to_cred (NII ÷ put value), call_to_put ratio |
| Rates | risk_free_rate |
| Stock | ret_5d, ret_20d, dist_from_ma50, atr_pct |
| Vol | iv_level, ivr_20d, iv_5d_change |
| Market | vix_level |

**Label:** 1 if stock stays above short strike for all 21 forward days.

---

## Entry Conditions

| Gate | Default | Notes |
|---|---|---|
| NII > threshold | 0.05 | Structural edge is open |
| ATM IV ≤ iv_max | 60% | Avoid panic environments |
| VIX ≤ vix_max | 40 | Avoid systemic stress |
| AI confidence ≥ thresh | 55% | Crash risk is low |

---

## When the Edge Is Strongest

**High NII environment (edge wide open):**
- Rates 4%+ (current environment ✅)
- Stock has pulled back 10–20% (put is deep ITM on the X strike)
- Low vol (caput is small → NII clearly positive)

**Edge closes:**
- Rates near zero (NII ≈ 0 regardless of ITM depth)
- Panic vol spikes (caput balloons → NII goes negative)
- Stock in free-fall (crash risk overwhelms structural edge)

---

## Exit Rules

| Trigger | Action |
|---|---|
| Profit ≥ 50% of max | Close early — capture most of the credit |
| Loss ≥ stop_loss_mult × credit (capped at max loss) | Stop out |
| DTE ≤ 5 | Close — gamma risk near expiry |

> **Note on the stop.** Because a bull put spread is defined-risk, its loss can
> never exceed max loss; a stop set at a multiple *of max loss* could never
> fire. The stop therefore triggers when the loss reaches
> `stop_loss_mult × credit collected`, capped at the spread's max loss.

---

## Walk-Forward Training

| Parameter | Value |
|---|---|
| Warmup | 90 bars |
| Retrain interval | Every 20 bars |
| Model | GradientBoostingClassifier |
| Trees | 60 (default) |
| Max depth | 3 |
| No look-ahead bias | Labels use forward prices only after bar i−DTE |

---

## Risk Profile

| Metric | Value |
|---|---|
| Max loss | Defined at entry: (wing − credit) × 100 per spread |
| Win rate | TODO — re-run backtest; high-probability OTM credit spreads typically win often but with asymmetric (small-win / large-loss) payoff |
| Sharpe | TODO — re-run backtest with current cost/skew model before quoting a figure |
| Holding period | ~21 days (DTE target), exits by DTE ≤ 5 |
| Robinhood eligible | ✅ Bull put spread — no naked legs |

> **Honest performance note.** Earlier versions of this page quoted a fixed win
> rate (~65–70%) and a Sharpe of 1.5. Those figures predate the corrected
> backtest, which now charges commissions **and** slippage per leg on both entry
> and exit, prices the OTM legs with a volatility skew, scales P&L by the number
> of contracts, uses a stop that can actually trigger, and marks open positions
> to market. All of these reduce headline performance versus the old model, so
> the previous numbers are not reliable. Re-run the backtest to obtain honest
> Sharpe / win-rate / return figures (TODO).

> **This is not a directional bet.** You win as long as the stock doesn't crash through the short strike. The edge comes from a structural market microstructure phenomenon — retail non-exercise — not from predicting stock direction.
