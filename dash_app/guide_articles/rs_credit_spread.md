# RS Credit Spread AI — Cross-Sectional Relative Strength Mean-Reversion
### Sell Premium on the Weakest Sector, Sell Premium on the Strongest Sector. Collect from Both.

---

## The Core Edge

When sector relative strength diverges to extremes, mean-reversion is predictable. The weakest sector over the past 10 days has structurally elevated IV (fear-driven premium expansion) and faces gravity from institutional rebalancing. The strongest sector is attracting momentum buyers who will eventually rotate out. Both extremes create credit spread opportunities.

This strategy runs **two simultaneous credit spread legs every week:**
- A **bear call spread on the weakest sector ETF** — betting the laggard won't surge further above current price
- A **bull put spread on the strongest sector ETF** — betting the leader won't collapse below current price

Both legs are defined-risk. Both legs benefit from IV compression (as extreme sector divergence normalizes). Both legs benefit from time decay (theta).

```
Weekly RS Ranking (11 sector ETFs):

  Rank  ETF    10d Return  Action
  ----  -----  ----------  -----------------------------
  #1    XLE    +8.2%       Leader → sell BULL PUT spread
  #2    XLF    +4.1%       — (middle, no trade)
  ...
  #10   XLK    -5.3%       Laggard → sell BEAR CALL spread
  #11   XLRE   -7.1%       (extreme laggard)
```

---

## Why This Works

**Institutional rebalancing creates predictable mean-reversion.** Pension funds and balanced mutual funds rebalance quarterly. ETF creation/redemption arbitrage continuously pulls sector weights toward their target. Factor rotation funds shift between momentum and value systematically. These flows create a mechanical pull on extreme RS deviations back toward the mean.

**Credit spreads have three ways to win.** Unlike a directional bet, a credit spread profits when: (1) the mean-reversion happens as expected, (2) the sector stays flat (time decay), or (3) the sector moves modestly in the "wrong" direction (within the buffer). You need a sustained, accelerating continuation of the extreme move to lose.

**Sector IV is structurally elevated after RS extremes.** When a sector has moved ±5-8% in 10 days, options market makers price in elevated IV to hedge the remaining uncertainty. This creates richer credit spread premiums exactly when you want to sell them — after the move has already happened.

---

## Sector ETF Universe

```
ETF   Sector
----  ----------------------------------------
XLK   Technology
XLE   Energy
XLF   Financials
XLV   Health Care
XLI   Industrials
XLY   Consumer Discretionary
XLP   Consumer Staples
XLU   Utilities
XLRE  Real Estate
XLB   Materials
XLC   Communication Services
```

All 11 SPDR sector ETFs are required for the full RS ranking. If fewer are available (e.g., missing sector data), the model degrades gracefully but the RS edge is reduced.

---

## The Two Trade Structures

### Bear Call Spread on Laggard (Weakest Sector)

```
Setup: XLK dropped 5.3% over 10 days. Rank = #10 of 11 sectors.
       IVR elevated from the recent decline. IV crush likely.

  XLK spot: $188
  Short call: $188 × (1 + 4%) = ~$195.50 → round to $196
  Long call:  $196 + 5% × $188 = ~$205.40 → round to $205
  DTE: 21 days
  Net credit: short - long premium (max profit if XLK stays below $196)
  Max loss: $9 wing - credit (defined)

Logic: XLK already fell 5.3%. For this spread to lose, it must now RALLY 4%+.
       Against a weakening sector with institutional rotation out, this is unlikely.
```

### Bull Put Spread on Leader (Strongest Sector)

```
Setup: XLE rose +8.2% over 10 days. Rank = #1 of 11 sectors.
       IV elevated from the strong rally. Mean-reversion likely.

  XLE spot: $94
  Short put: $94 × (1 - 4%) = ~$90.24 → round to $90
  Long put:  $90 - 5% × $94 = ~$85.30 → round to $85
  DTE: 21 days
  Net credit: short - long premium (max profit if XLE stays above $90)
  Max loss: $5 wing - credit (defined)

Logic: XLE already rallied 8.2%. For this spread to lose, it must now DROP 4%+.
       A leader with momentum support rarely drops that fast in 10 days.
```

---

## The 10 Model Features

```
Feature                 Rationale
----------------------  -------------------------------------------------------
rs_rank_10d             Current RS rank (0-10) — extremity of position
rs_zscore_60d           How extreme vs trailing 60d history — normalized measure
sector_ivr              Sector's own IVR proxy — premium richness
sector_iv_vs_spy        Sector IV relative to SPY — excess premium indicator
sector_spy_corr_20d     Rolling SPY correlation — higher = safer credit spread
spy_adx_14              SPY trend strength — avoid credit in strongly trending SPY
spy_ret_5d              SPY recent direction — market context
vix_level               Absolute fear level — affects all sector IV
vix_ma_ratio            VIX spike vs trend — regime context
days_to_month_end       Calendar — options expiry clustering
```

**SPY ADX is the primary safety filter.** When SPY is strongly trending (ADX > 30), all sector RS divergences tend to persist and amplify rather than mean-revert. A strongly trending market breaks the mean-reversion thesis. The strategy stays flat when SPY ADX exceeds the threshold.

---

## Label Construction

```python
# For laggard (bear call spread survival):
for each earnings event i:
    entry_price = close[i]
    fwd_window  = close[i+1 : i+11]
    max_extension = max(fwd_window) / entry_price - 1

    label_lag[i] = 1 if max_extension < 0.08 else 0
    # 1 = sector stayed below entry + 8% → spread survived

# For leader (bull put spread survival):
    min_extension = 1 - min(fwd_window) / entry_price

    label_lead[i] = 1 if min_extension < 0.08 else 0
    # 1 = sector stayed above entry - 8% → spread survived

# Positive rate: ~65% for both (sector extremes rarely accelerate 8%+ in 10 days)
```

Two separate models are trained: one for laggard containment, one for leader containment. This allows each model to specialize in the asymmetric dynamics of over-sold vs over-bought conditions.

---

## Walk-Forward Architecture

```
Timeline:
  Bar 0──────────────Bar 90──────────────────────────────────────▶
  │  Warmup (no trades) │  First prediction possible
                        │
                        Rebalance every 5 days (weekly)
                        Retrain every 15 bars
                        Two independent GBM models (lag + lead)
```

**Weekly rebalance cadence.** Sector RS dynamics typically play out over 5-15 days. A weekly rebalance captures the mean-reversion while avoiding micromanagement of daily RS fluctuations.

**Two independent models.** The laggard model and leader model are trained separately because the features have different predictive relationships for each direction. Laggard containment is more sensitive to SPY ADX (trending markets accelerate weak sectors further down). Leader containment is more sensitive to momentum acceleration (leaders with accelerating momentum don't mean-revert quickly).

---

## Real Trade Walkthrough

**Date:** November 2023 | **SPY ADX:** 18 (range-bound — ideal for mean-reversion)

10-day RS ranking:
- #1 Leader: **XLE** +7.8% (energy rally on oil price spike)
- #11 Laggard: **XLRE** -6.2% (rate fears hammered REITs)

**Leg 1: Bear call spread on XLRE**
- XLRE spot: $34.50 | Short call: $35.88 | Long call: $37.60
- Net credit: $0.42 | Max loss: $1.30
- Model P(XLRE contained): 0.72 → enter

**Leg 2: Bull put spread on XLE**
- XLE spot: $87.20 | Short put: $83.71 | Long put: $79.36
- Net credit: $0.38 | Max loss: $1.07
- Model P(XLE contained): 0.68 → enter

Outcome (10 days):
- XLRE: $33.80 (fell slightly, well below $35.88 short call) → **Leg 1: +$42/contract**
- XLE: $89.50 (rose slightly, well above $83.71 short put) → **Leg 2: +$38/contract**
- **Combined P&L: +$80 for two spreads requiring ~$650 max risk capital**

---

## Data Requirements

This strategy requires **daily OHLCV data for all 11 sector ETFs** in `auxiliary_data['sectors']`:

```python
auxiliary_data = {
    "vix":     vix_dataframe,
    "sectors": {
        "XLK":  xlk_price_df,
        "XLE":  xle_price_df,
        "XLF":  xlf_price_df,
        # ... all 11 sector ETFs
    }
}
```

These can be synced via the Data Manager → Stocks tab for each sector ETF ticker. If fewer than 3 sectors are available, the backtest degrades to a simplified mode with no RS edge.

---

## Entry Rules Summary

```
Condition                        Value
-------------------------------  ----------------------------------------
SPY ADX                          < adx_max (default 30) — no strong trend
VIX                              ≤ vix_max (default 40)
P(laggard contained)             ≥ min_confidence (default 60%)
P(leader contained)              ≥ min_confidence (default 60%)
Rebalance timing                 Every 5 trading days
Sector data available            ≥ 3 ETFs required for RS ranking
```

---

## Exit Rules Summary

```
Exit Trigger        Per Leg
------------------  ----------------------------------------
Profit target       50% of max credit → close this leg
Stop loss           2× max credit → close this leg
Hold days           10 days → close at market
End of data         Close at market
```

---

## Common Mistakes

**Entering when SPY ADX > 30.** This is the most dangerous regime for this strategy. In trending markets, sector rotation accelerates rather than reverts. The ADX filter is not optional — override it at your own risk.

**Trading thin-market sector ETFs.** XLRE and XLB have lower average daily volume than XLK or XLF. The spread pricing may be less favorable (wide bid-ask on the actual options). The backtest assumes efficient pricing — check real options quotes before entering in thinly-traded sectors.

**Letting both legs run simultaneously into expiry.** The two legs have independent risk profiles. A macro event (e.g., Fed rate decision) can simultaneously spike energy and crush tech — simultaneously losing on both legs. The individual stop-losses per leg (2× credit) limit this damage, but don't treat the dual spread as fully uncorrelated.

**Expecting high trade frequency.** This strategy trades weekly at most. With the SPY ADX filter and minimum confidence requirements, there may be extended periods (2-4 weeks) of no entries. This is correct behavior — patience is part of the edge. Forcing trades in ambiguous regimes destroys the positive expectancy.
