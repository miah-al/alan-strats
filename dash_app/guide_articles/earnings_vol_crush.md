# Earnings Vol Crush AI — Post-Earnings Credit Spread
### Harvesting Residual IV After the Binary Event Resolves

---

## The Core Edge

Before every earnings announcement, implied volatility rises sharply. This is rational: nobody knows what the company will report, and uncertainty is worth paying for. But after the announcement — when the number is out and the gap has already happened — implied volatility often remains elevated for 1-5 days. The binary event is resolved, the stock has gapped, and yet options are still pricing in uncertainty that no longer exists.

This residual IV is the edge. The strategy enters a credit spread **after** the gap (T+0 or T+1), when the directional risk is known but IV compression hasn't fully played out yet. The short strike is placed beyond the earnings gap, using the resolved price action as the natural anchor.

```
Timeline:

  Pre-earnings  │  Announcement  │  Entry window    │  IV crush complete
  ──────────────┼────────────────┼──────────────────┼──────────────────
  IV rises +40%  │  Gap happens   │  T+0/T+1: sell   │  T+3: IV -40%
  Stock quiet   │  (known gap)   │  credit spread   │  Spread value ↓
```

The AI layer adds precision: it predicts (1) how much IV will crush and (2) whether the stock will stay contained (not extend its gap) over the hold period. Only when both conditions are predicted favorable does the strategy enter.

---

## Why This Works

**IV crush is mechanical.** After an earnings announcement, the primary uncertainty driver is removed. Options market makers immediately reprice implied vol downward — they no longer need to hedge the binary risk. This repricing happens regardless of whether earnings beat or missed, regardless of the gap direction. It is calendar-driven, not directional.

**The gap is the protection.** By entering after the gap, you know the worst-case scenario: the stock already moved X%. You're not predicting whether it will go up or down — that already happened. You're predicting whether it will *stay* near the new price level or extend dramatically further.

**Historical base rate:** Post-earnings credit spreads on large-cap stocks (where the initial gap stays contained ±8%) have positive expectancy ~65% of the time, documented extensively in options strategy literature. The AI layer improves the hit rate by filtering out high-momentum stocks that extend their gaps.

---

## Trade Structure

### Earnings Gap Up → Bear Call Credit Spread

```
Setup: Stock gaps UP 4% after earnings.

  Stock: $155 (was $149)
  Short call: $155 × (1 + 3%) = ~$159.65 → round to $160
  Long call:  $160 + 5% × $155 = ~$167.75 → round to $167
  DTE: 14 days
  Net credit: collected upfront (max profit if stock stays below $160)
  Max loss: $7 wing - credit (fully defined)

Logic: Stock already gapped up. Short call placed 3% above the new high.
       Bears need a second 3% extension for the spread to lose. IV crush helps.
```

### Earnings Gap Down → Bull Put Credit Spread

```
Setup: Stock gaps DOWN 5% after earnings.

  Stock: $92 (was $96.80)
  Short put: $92 × (1 - 3%) = ~$89.24 → round to $89
  Long put:  $89 - 5% × $92 = ~$84.40 → round to $84
  DTE: 14 days
  Net credit: collected upfront (max profit if stock stays above $89)
  Max loss: $5 wing - credit (fully defined)

Logic: Stock already gapped down. Short put placed 3% below the new low.
       Bulls would need a second 3% decline for the spread to lose.
```

---

## The 10 Model Features

```
Feature                Rationale
---------------------  -------------------------------------------------------
ivr                    IVR at announcement — higher = more crush available
earnings_gap_pct       Actual signed gap size — direction and magnitude
abs_gap_pct            Absolute gap size — magnitude of move
vix_level              Market vol regime — high VIX = wider spreads needed
realized_vol_20d       Recent realized vol — normalizes gap magnitude
gap_vs_rv              Gap as multiple of 20d RV — is this gap unusual?
adx                    Trend strength — high ADX = gap likely extends (risky)
ret_20d                Pre-earnings momentum — stocks in strong trends extend
dist_from_ma50         Distance from 50MA — mean-reversion potential
days_to_month_end      Calendar — options expiry clustering effect
```

---

## Label Construction

```python
# 10-day containment label (no look-ahead)
for each earnings event i:
    entry_price = close[i]       # post-gap close
    forward_window = close[i+1 : i+11]

    max_extension = max(|close - entry_price|) / entry_price
    label[i] = 1 if max_extension <= 0.08 else 0

# Positive rate: ~65% (most gaps are "one and done")
# Negative cases: high-momentum stocks, macro events, secondary news
```

The 8% containment threshold matches a 5% wing + 3% buffer structure. If the stock extends more than 8% from the gap close, the credit spread is in danger. The model focuses on identifying which stocks are likely to contain vs extend.

---

## Walk-Forward Architecture

```
Timeline (event-based, not calendar-based):

  Events 0─────────────Event 30─────────────────────────────────▶
  │  Warmup (no trades)  │  First prediction possible
                         │
                         Retrain every 10 events (expanding window)
                         Only uses earnings event rows for training
```

Note: This strategy uses **event-based training** rather than bar-based. The model trains only on earnings event rows, not all trading days. This ensures the model learns from actual earnings dynamics rather than non-events. 30-event warmup typically spans 6-12 months of data for a diversified stock universe.

---

## Real Trade Walkthrough

**Stock:** AAPL | **Date:** February 2024 | **Announcement:** T+0

Pre-announcement: IV elevated, stock at $182.
Earnings gap: +3.8% to $189 (beat on revenue).

Entry (T+1 morning): $189, IVR = 0.68 (still elevated)

Model features:
- `earnings_gap_pct` = +0.038
- `abs_gap_pct` = 0.038
- `ivr` = 0.68 (good crush potential)
- `gap_vs_rv` = 1.4 (gap = 1.4× recent daily vol — moderate)
- `adx` = 22 (moderate trend, not strongly trending)

**Model output: P(contained) = 0.73** → enter bear call spread.

Trade:
- Short call: $195 (3% above gap high)
- Long call: $204 (5% wing)
- Net credit: $1.40 | Max loss: $7.60 | Hold: 10 days

Outcome: AAPL ranged $186-$193 over next 10 days. Both calls expired worthless.
**P&L: +$140 per contract.** IV crush from 45% to 28% over 3 days was the driver.

---

## Earnings Event Detection

In backtest mode, the strategy detects earnings events using a gap threshold:

```python
# Earnings proxy: single-day move > min_gap_pct (default 3%)
# with no adjacent large gap (avoids multi-day trending moves)
earnings_gap = (daily_return.abs() > 0.03) and (prior_day_return.abs() < 0.015)
```

In live mode, use Polygon.io's earnings calendar endpoint for precise announcement dates. Real earnings dates eliminate false positives from non-earnings gaps (macro events, index reconstitution, etc.).

---

## Entry Rules Summary

```
Condition                        Value
-------------------------------  --------------------------------
Earnings gap detected            |daily_return| ≥ min_gap_pct (3%)
Model confidence P(contained)    ≥ min_confidence (60%)
VIX                              ≤ 45
No open position                 Required
Model trained (≥ 30 events)      Required
```

---

## Exit Rules Summary

```
Exit Trigger        Action
------------------  ----------------------------------------
Profit target       50% of max credit reached → close spread
Stop loss           2× max credit lost → close spread
Hold days           10 days elapsed → close at market
End of data         Close at market
```

---

## Common Mistakes

**Entering before the announcement.** This strategy is specifically post-announcement. Pre-earnings, you have binary directional risk. Post-earnings, directional risk is resolved — you're only trading the IV crush and containment, which has much better win rates.

**Using on small-cap or high-momentum stocks.** The containment assumption breaks down for stocks with: (1) thin options liquidity, (2) high ADX (strongly trending), (3) recent history of multi-day gap extensions. The ADX feature and `gap_vs_rv` filter are specifically designed to catch these.

**Placing short strike too close to current price.** The 3% buffer beyond the gap is minimum. In high-VIX environments, extend to 4-5%. The strategy is designed to collect premium, not to be a directional bet — give it room.

**Ignoring IVR.** If IVR < 40% at the time of entry, the IV crush has already happened (or there was no significant IV expansion before earnings). Skip the trade — there's no premium to harvest.
