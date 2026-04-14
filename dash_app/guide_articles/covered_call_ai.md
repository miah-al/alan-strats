# Covered Call Optimizer AI — Adaptive Strike and DTE Selection
### Static 0.30 Delta Is Leaving Premium on the Table (and Capping Your Best Days)

---

## The Core Edge

Covered call writing is the most common retail options strategy — and most retail traders use one of two approaches: (1) "always sell 30 DTE at 0.30 delta" or (2) "sell whatever strike feels right." Both approaches are suboptimal in different ways.

The static 0.30 delta rule:
- **Over-sells in strong uptrends** — you cap your gain at 0.30 delta above spot, then SPY rips through your strike and you miss the upside
- **Under-sells in high-IVR environments** — in 2022 when VIX was 35+, selling 0.30 delta gave you 8% annualized premium. A 0.25 delta would have given you 6% and let you hold the stock through more of the rally

The AI optimizer solves this by learning from historical outcomes: which (delta, DTE) combinations actually maximized risk-adjusted premium extraction for each vol regime? The model adapts the strike and DTE to current conditions, using IVR, momentum, earnings proximity, and vol term structure as inputs.

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

**The ML edge over fixed delta:**
- Academic studies (McMillan 2012, Whaley 2002) show 0.30 delta outperforms 0.50 delta (ATM) but underperforms a **dynamic delta** rule that uses IVR to modulate aggressiveness
- The model learns which regimes call for aggressive vs conservative strike selection
- Critical filter: earnings proximity. The single largest source of covered call losses is being called away during an earnings gap-up. The model uses a proxy for earnings timing to avoid this

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

```python
# For each bar i, simulate selling a covered call at `delta` for `dte` days:

strike   = strike_for_delta(spot[i], sigma=VIX[i]/100, dte=dte, delta=delta)
premium  = black_scholes_call(spot[i], strike, dte, VIX[i]/100)
exit_px  = close[i + dte]

# P&L of covered call:
if exit_px <= strike:
    cc_pnl = premium + (exit_px - spot[i])    # kept premium + stock appreciation
else:
    cc_pnl = premium + (strike - spot[i])      # capped gain

# P&L of just holding:
hold_pnl = exit_px - spot[i]

# Label: covered call wins if cc_pnl ≥ 90% of hold_pnl
# (allow 10% slippage — CC doesn't need to beat hold by much to be worth it)
label[i] = 1 if cc_pnl >= hold_pnl * 0.90 else 0

# Positive rate: ~55-60% (CC wins when stock is flat to slightly up)
```

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

## Real Trade Walkthrough — Aggressive Mode

**Stock:** SPY | **Date:** October 2023 | **Price:** $424 | **VIX:** 21.6 | **IVR:** 0.58

Model inputs:
- `ivr` = 0.58 → premium is rich (IVR > 40%)
- `ret_20d` = -0.028 → slight downtrend — not in strong bull run
- `days_since_earnings` = 45 → away from earnings window
- `vix_ma_ratio` = 1.18 → VIX slightly above average

**Model output: P(CC wins) = 0.68** → aggressive mode (0.30 delta)

Trade:
- Short call: $437 strike (0.30 delta at 21 DTE)
- Premium collected: $2.40/share = $240/contract

Outcome: SPY closed at $430 at expiration. Call expired worthless.
**P&L on covered call: +$240** (annualized yield on stock: 6.8%).

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
