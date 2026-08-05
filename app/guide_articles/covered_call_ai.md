# Covered Call Optimizer AI — Adaptive Strike and DTE Selection
### Static 0.30 Delta Is Leaving Premium on the Table (and Capping Your Best Days)

---

## ⚠️ Honest Verdict First: This Is Mostly Beta, Not Alpha

Read this before the marketing copy below. A covered call is **long underlying +
short call**, so the position is structurally ~80% long SPY. An audited
walk-forward backtest on real SPY data (2021-01-04 → 2026-06-01) gives:

```
                       Total return   Sharpe   Sortino   Max DD    Beta
AI Covered Call          +137.7%       0.82     1.15     -18.8%    0.84
Buy-and-hold SPY         +120.9%       0.65     0.91     -25.4%      —
Naive "always 0.30Δ"     +141.7%       0.87       —      ~ -19%    ~0.84
```

Three honest conclusions:

1. **Most of the return is SPY beta.** Measured beta ≈ 0.84. The strategy rises
   and falls with the market; in a 2021–2026 bull run, "long SPY" was always
   going to print a big number. ~121 of the ~138 points are simply SPY.

2. **The covered-call overlay DOES beat buy-and-hold on a risk-adjusted basis**
   — higher Sharpe (0.82 vs 0.65) and a materially smaller drawdown (-18.8% vs
   -25.4%). That is the **well-documented BuyWrite (BXM) premium-harvest effect**,
   not a proprietary edge. Selling calls trades away some upside for a steadier
   ride and a volatility buffer.

3. **The AI model adds NO measurable alpha.** A naive "always sell 0.30 delta"
   rule with the model deleted returns **+141.7% at Sharpe 0.87 — within noise of
   (and slightly ahead of) the AI's +137.7% / 0.82.** The reason is structural:
   the aggressive-vs-conservative outcome the model is asked to predict has a
   ~75% base rate (aggressive usually wins because the bigger premium dominates
   unless the stock rallies *between* the two strikes — a rare, hard-to-forecast
   event). The model mostly predicts the majority class and reproduces the static
   rule. **Treat the "AI" label as decorative; the economic engine is beta +
   covered-call premium.**

If you want this strategy, want it for **drawdown reduction vs holding SPY**, not
for alpha. Do not size it as if the model were generating skill-based returns.

---

## The Core Edge

Covered call writing is the most common retail options strategy — and most retail traders use one of two approaches: (1) "always sell 30 DTE at 0.30 delta" or (2) "sell whatever strike feels right." Both approaches are suboptimal in different ways.

The static 0.30 delta rule:
- **Over-sells in strong uptrends** — you cap your gain at 0.30 delta above spot, then SPY rips through your strike and you miss the upside
- **Under-sells in high-IVR environments** — in 2022 when VIX was 35+, selling 0.30 delta gave you 8% annualized premium. A 0.25 delta would have given you 6% and let you hold the stock through more of the rally

The AI optimizer learns from historical outcomes whether writing a covered call is likely to be profitable in the current regime. In the shipped backtest this is simplified to a **binary strike-mode choice** — aggressive (≈0.30 delta) vs conservative (≈0.15 delta) — at a fixed target DTE, gated by an IVR floor and an earnings-proximity filter. It does **not** search a continuous (delta, DTE) grid; that broader framing is the design thesis, not the implemented behavior. Inputs are IVR, momentum, earnings proximity, and vol-regime features.

```
Static rule:    Always sell 0.30 delta, 30 DTE
                → Miss rallies in bull runs, under-collect in high-IVR

AI optimizer:   IVR high + momentum low  → sell 0.30 delta (aggressive)
                IVR high + momentum high → sell 0.15 delta (conservative)
                IVR low                  → skip (not worth capping upside)
                Earnings near            → skip (gap risk too high)
```

---

## Why This Edge Is Real

The CBOE BuyWrite Index (BXM), which systematically writes ATM covered calls on SPY, has historically outperformed SPY on a **risk-adjusted basis** over most decade-long windows. The risk-adjusted outperformance comes from:

1. **Premium income** reduces portfolio volatility — covered call writing is essentially selling insurance
2. **Systematic discipline** prevents emotional selling at bottoms and overholding at tops

But the BXM uses ATM calls (0.50 delta) — far too aggressive for a retail investor who doesn't want to constantly be called away. The sweet spot for retail covered call writing is 0.15-0.30 delta, where premium income is meaningful but assignment risk is modest.

**The (claimed) ML edge over fixed delta — and why it doesn't hold up:**
- The *thesis* is that a dynamic delta rule keyed off IVR/momentum beats a static
  0.30Δ. Academic studies (McMillan 2012, Whaley 2002) support dynamic > static
  *in principle*.
- **In this implementation, on real SPY data, it does not.** See the honest
  verdict at the top: the trained model returns +137.7% / 0.82 Sharpe, while
  simply deleting the model and always selling 0.30Δ returns +141.7% / 0.87. The
  delta-switching the model performs is a slight *drag*, not an edge.
- The genuinely useful filters here are **not** ML: the **IVR floor** (don't sell
  cheap premium) and the **earnings-proximity proxy** (avoid being called away on
  a gap-up) are deterministic rules that would help any covered-call writer. They
  are the parts of this strategy worth keeping.

---

## The Two Strike Modes

### Aggressive Mode (0.30 delta) — High IVR, Low Momentum

```
Conditions:
  IVR ≥ 40% (premium is rich — worth selling)
  Momentum (ret_20d) ≤ 5% (not in a raging bull run)
  Days since last big gap ≥ 10 (away from earnings window)

Example:
  Stock: $540, VIX: 22, IVR: 0.62
  Target delta: 0.30
  Strike: ~$558 (≈ 3.3% OTM based on IV)
  21 DTE premium: ~$2.10 per share = $210/contract
  Annualized yield: $210 × 17 cycles / $540 = 6.6% on the stock
```

### Conservative Mode (0.15 delta) — Strong Momentum or Low IVR

```
Conditions:
  Stock is in strong uptrend (ret_20d > 8%)
  OR IVR < 40% (premium not worth capping upside)

Example:
  Stock: $540, VIX: 14, IVR: 0.28
  Target delta: 0.15
  Strike: ~$575 (≈ 6.5% OTM)
  21 DTE premium: ~$0.85 per share = $85/contract
  Annualized yield: $85 × 17 cycles / $540 = 2.7% — low but doesn't cap upside much
  
  In this case, AI may recommend SKIP (IVR < min_ivr threshold).
  Sacrificing upside for $85/contract when the stock is trending is bad math.
```

---

## The 10 Model Features

```
Feature                 Rationale
----------------------  -------------------------------------------------------
ivr                     Primary gate — IVR determines if premium is worth selling
vrp                     Vol risk premium — implied minus realized
iv_rv_ratio             Normalized premium richness
ret_20d                 Momentum — strong uptrend → conservative or skip
ret_5d                  Short-term momentum — recent acceleration
dist_from_ma50          Distance from 50MA — mean-reversion potential
vix_level               Absolute vol level — context for strike selection
vix_ma_ratio            VIX vs 20d average — spike vs trend
atr_pct                 Daily range — affects breakeven calculation
days_since_earnings     Earnings proximity proxy (days since last big gap)
```

The `days_since_earnings` feature is the most important safety feature. Most earnings cycles are roughly quarterly (~90 days). If it's been 75+ days since the last large gap, an earnings announcement may be approaching. The model down-weights covered call aggressiveness when this feature is low.

---

## Label Construction

The model's only job is to choose **aggressive (0.30Δ) vs conservative (0.15Δ)**
each cycle, so the label must score *exactly that choice* — not a generic
"did a covered call make money" question. The label compares the realized P&L of
both deltas over the forward window and marks which one would have won:

```python
# For each bar i, simulate BOTH deltas over the next `dte` days:
k_agg   = strike_for_delta(spot[i], VIX[i]/100, dte, 0.30)   # nearer the money
k_cons  = strike_for_delta(spot[i], VIX[i]/100, dte, 0.15)   # further OTM
p_agg   = black_scholes_call(spot[i], k_agg,  dte, VIX[i]/100)
p_cons  = black_scholes_call(spot[i], k_cons, dte, VIX[i]/100)
exit_px = close[i + dte]                                      # forward data only

def cc_pnl(K, prem):
    return prem + (exit_px - spot[i]) if exit_px <= K else prem + (K - spot[i])

label[i] = 1 if cc_pnl(k_agg, p_agg) > cc_pnl(k_cons, p_cons) else 0
#          1 → aggressive was better (bigger premium captured)
#          0 → stock rallied BETWEEN the strikes → conservative kept more upside
```

**Worked numeric example** (real-ish SPY parameters):

```
spot = 400.00,  VIX = 20  →  σ = 0.20,  DTE = 21
  Aggressive 0.30Δ:  strike ≈ 414.54,  premium ≈ $4.27/sh
  Conservative 0.15Δ: strike ≈ 426.97,  premium ≈ $1.75/sh

Outcome A — flat market, exit = 400:
  agg  P&L = 4.27 + (400-400) = +4.27
  cons P&L = 1.75 + (400-400) = +1.75   → label = 1 (aggressive wins on premium)

Outcome B — rally to 420.8 (BETWEEN the two strikes):
  agg  P&L = 4.27 + (414.54-400) = +18.80   (capped at aggressive strike)
  cons P&L = 1.75 + (420.80-400) = +22.55   (still below conservative strike)
                                          → label = 0 (conservative preserves upside)

Outcome C — crash to 280:
  agg  P&L = 4.27 + (280-400) = -115.73
  cons P&L = 1.75 + (280-400) = -118.25  → label = 1 (bigger premium = bigger cushion)
```

> **Why this can't generate alpha:** notice that aggressive wins in A *and* C —
> only the narrow "rally to between the strikes" path (Outcome B) favors
> conservative. On real SPY data that makes the label ~75% positive (982:355 on
> the 2021–2026 window). A high-base-rate, hard-to-forecast target is exactly the
> kind of problem ML *cannot* beat a constant rule on — which is why the ablation
> shows the model ≈ "always 0.30Δ." This label is the **honest** label (it scores
> the real decision), but honesty here means admitting the decision isn't
> learnable.

> **Look-ahead safety:** `exit_px = close[i + dte]` is strictly forward data, so
> the last `dte` rows are left unlabeled (NaN). The walk-forward trainer **purges**
> the trailing `dte` rows from every training slice (`cutoff = i - dte_target`),
> so no label whose forward window overlaps the decision bar can leak into
> training — the same purge discipline as `iron_condor_ai.py`. Features are
> `ffill`-only (never `bfill`), so no future value is ever pulled backward.

> Note on backtest realism: the live backtest charges commission + slippage
> per contract when a call is written and again on a profit-target/stop
> buy-back (calls left to expire worthless incur no closing fee), prices the
> short call with a skew-adjusted IV (`bs_price_skew`, so an OTM call sits
> below the ATM IV implied by VIX — a conservative credit), and marks any open
> short call to market each bar so the equity curve is not a step function.

---

## Walk-Forward Architecture

```
Timeline:
  Bar 0──────────────Bar 90──────────────────────────────────────▶
  │  Warmup (no trades) │  First prediction possible
                        │
                        Model selects delta each cycle
                        Retrain every 15 bars
                        Long stock position held throughout
```

Unlike the other AI strategies, this strategy **always holds the underlying stock**. The AI only controls the covered call overlay — whether to write a call, at which delta, and for which DTE. The stock position runs continuously; the covered call is layered on top.

---

> The two walkthroughs below are **illustrative scenarios**, not audited backtest trades. The premiums shown are flat-IV approximations and exclude commission/slippage; the live backtest applies skew and both legs of friction, so realized credits are somewhat smaller.

## What October 2023 actually did

An earlier version of this guide presented an illustrative October-2023 trade
closing at **+$240**, under the heading "Real Trade Walkthrough". The real
backtest trades in that window, measured through the production path, were:

| Entry | Exit | P&L | Exit reason |
|---|---|--:|---|
| 2023-10-03 | 2023-10-23 | **+$1,052.46** | profit_target |
| 2023-10-23 | 2023-11-14 | **−$2,982.20** | stop_loss |

That is the honest shape of this strategy: a steady run of profit-target wins
punctuated by a much larger stop-out. Across the full run there are **13
stop-loss exits averaging −$2,302, totalling −$29,930** — against 34
profit-targets. Any walkthrough showing only the winning half misrepresents the
distribution you are actually taking on.

**The 2× stop-loss is measurably harmful.** On a *covered* call the short leg's
loss is offset by the stock you own; buying the call back at 2× locks in the
option loss and surrenders that offset. Removing it improves both return and
drawdown.

---

## Real Trade Walkthrough — Conservative Mode (Skip)

**Stock:** SPY | **Date:** July 2023 | **Price:** $451 | **VIX:** 13.1 | **IVR:** 0.22

Model inputs:
- `ivr` = 0.22 → below min_ivr threshold (0.30)
- `ret_20d` = +0.063 → strong uptrend

**Model output: SKIP** → premium too thin + momentum too strong.

SPY rose to $474 over the next 21 days (+5.1%). Had sold a 0.30 delta call at $465, would have been capped at $465, missing $9 per share of upside = $900/contract.

By skipping the covered call, the full $2,300/contract of stock appreciation was captured.

---

## Entry Rules Summary

```
Condition                        Value
-------------------------------  ----------------------------------------
IVR                              ≥ min_ivr (default 30%)
Days since last large gap        ≥ min_days_since_earn (default 10)
Current covered call position    None (only 1 active call per 100 shares)
Model trained (≥ 90 bars)        Required for delta selection
```

---

## Exit Rules Summary

```
Exit Trigger        Action
------------------  -------------------------------------------------------
Profit target       75% of premium collected → buy back short call
Stop loss           Call reaches 2× entry premium → buy back to limit loss
Expiry              Let expire worthless if OTM at DTE → premium fully kept
```

---

## Common Mistakes

**Not owning the stock first.** Covered calls require 100 shares of the underlying per contract. This strategy assumes you hold the stock position. If you're writing covered calls on a stock you don't own, that's a naked call — which is not permitted on Webull at standard options approval levels.

**Writing through earnings.** The single largest covered call loss scenario: sell a covered call, then stock gaps up 8% through earnings, stock is called away, you miss the continuation. The `days_since_earnings` feature specifically mitigates this, but be aware of the earnings calendar independently.

**Forcing covered calls in low-IVR environments.** When VIX is 12 and IVR is 0.20, a 0.30 delta covered call on SPY yields about $0.40/share = $40/contract over 21 days. That's 1% annualized — not worth capping your upside. The min_ivr parameter exists for exactly this reason: don't sell cheap insurance.

**Confusing delta with probability of assignment.** A 0.30 delta call is roughly the probability that the stock closes above the strike at expiration. But that's the terminal probability, not the intraday path. The stock may touch the strike during the holding period (temporary assignment risk at expiration is clear, but ITM calls can be exercised early on dividend-paying stocks).


---

## Audit & money verdict — 2026-07-03

**End-to-end audit (UI · Backtest · Screening · Tests · Training): all surfaces PASS.**

- **Real backtest:** +137.7% · Sharpe 0.82 · −18.8% max DD · β 0.84 · 47 trades (SPY 2021→2026).
- **Money verdict:** **Beta, not alpha.** Most of the return is SPY beta; deleting the AI head and always selling 0.30Δ beats it (+141.7% / Sharpe 0.87). The *overlay* does cut drawdown vs buy-hold (Sharpe 0.87 vs 0.65) — but that is the BuyWrite premium-harvest effect, not the model. Training is leak-free but adds no value (75% majority-class label).
- **Deploy:** Paper only (drawdown-reducing overlay; the ML is decorative).

_Audited on real DB data via the production backtest + screener paths. Full cross-strategy report: `docs/reviews/2026-07-03_top10_strategy_audit.md`._
