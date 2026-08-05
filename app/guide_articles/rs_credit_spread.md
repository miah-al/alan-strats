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

## Pricing Realism — Skew and Frictions

The backtest does **not** price legs with a single flat VIX-implied IV. Two
corrections are applied so the simulated fills match what a real account would
get; both are essential to an honest result.

**1. Equity-index volatility skew.** Real index/ETF option surfaces are not flat:
OTM puts trade at a *higher* IV than ATM, OTM calls at a *lower* IV (the downside
"smirk"). Each leg is priced through `engine.bs_price_skew` with a skew slope of
**0.15**, applied exactly once. The short leg of a bull put (an OTM put) therefore
carries a richer IV — but so does the long protective put, and the net effect on
the *credit* is smaller than the flat-IV approximation suggests. For the bear
call the OTM short call sits on the cheaper side of the smirk, which *reduces* the
credit relative to flat IV. Net: skew makes the realised credits modestly thinner
than a flat-IV model would print.

**2. Commission + slippage on entry AND exit.**

```
Per leg, per contract:
  Commission   $0.65  (broker, charged on entry and again on exit)
  Slippage     $0.05/share = $5.00/contract  (adverse fill vs mid)

Per spread (2 legs), round trip:
  Entry  : 2 × $0.65                    = $1.30 commission
           2 × $0.05 baked into credit  = $0.10/share = $10/contract
  Exit   : 2 × ($0.65 + $5.00)          = $11.30/contract
  ----------------------------------------------------------------
  Total round-trip friction ≈ $12.60 + $1.30  ≈ $13.90 per contract
```

**Why this matters so much here.** Sector-ETF credit spreads are *cheap* — a
typical net credit is only **$0.40–$1.20/share ($40–$120/contract)**. A round-trip
friction of ~$12–14/contract is therefore **10–35% of the gross credit on every
single trade**, before any market move. This is not a modelling artefact; it is
the real economics of trading low-priced, tight (4%-buffer) spreads weekly.

---

## Worked Numeric Example (with skew + costs)

**Date:** November 2023 | **SPY ADX:** 18 (range-bound — ideal for mean-reversion)

10-day RS ranking:
- #1 Leader: **XLE** +7.8% (energy rally on oil price spike)
- #11 Laggard: **XLRE** -6.2% (rate fears hammered REITs)

**Leg 2: Bull put spread on XLE** (leader)
```
XLE spot S            = $87.20
DTE                   = 21 calendar → T = 21/252 ≈ 0.0833 yr
ATM IV proxy          = VIX/100 ≈ 0.165
Short put strike      = S × (1 − 0.04) = $83.71   (OTM put, m = ln(83.71/87.20) = −0.0408)
Long  put strike      = short − 5%×S  = $79.36

Skew-adjusted IVs (slope 0.15):
  short put IV = 0.165 − 0.15 × (−0.0408) ≈ 0.171   (richer, as puts should be)
  long  put IV = 0.165 − 0.15 × ln(79.36/87.20) ≈ 0.179

Black-Scholes mid premiums:
  short put ≈ $0.46/sh,  long put ≈ $0.10/sh
  credit_mid = 0.46 − 0.10 = $0.36/sh

Entry slippage (2 legs × $0.05):
  net credit  = 0.36 − 0.10 = $0.26/sh   →  entry_value = $0.26

Position size (position_size_pct = 1.5%, capital $100k):
  wing = |83.71 − 79.36| = $4.35
  max loss/contract = (4.35 − 0.26) × 100 = $409
  contracts = floor(100000 × 0.015 / 409) = floor(3.67) = 3
  entry commission = 2 × $0.65 × 3 = $3.90 (deducted from cash)
```

**Outcome after 10 days** — XLE drifts to $89.50 (stays well above the $83.71
short put):
```
Cost to close (skew-priced) ≈ $0.05/sh
Gross P&L = (0.26 − 0.05) × 100 × 3 contracts = $63.00
Exit friction = 2 × ($0.65 + $5.00) × 3       = $33.90
Net P&L (this leg) = 63.00 − 33.90 − 3.90 (entry comm) = $25.20
```

The leg is still a **winner**, but the $37.80 of round-trip friction on 3
contracts has eaten **60% of the $63 gross profit**. On a *losing* trade the same
friction is added to the loss. Multiply this across ~180 trades over five years and
the cumulative friction (~$10k on $100k of capital) is the dominant P&L term — see
the honest backtest finding below.

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

## What the Backtest Actually Shows (Honest Verdict)

Run on the real 11 SPDR sector ETFs (mkt.PriceBar, 2021-04 → 2026-04, SPY as the
market context leg):

```
                       Flat IV, no costs    Realistic (skew + costs)
                       (idealised)          (production)
  Total return         +15.7%               −6.7%
  Annualised           +2.9%                −1.4%
  Win rate             93.7%                59.7%
  Profit factor        3.0                  0.52
  Trades               191                  176
  Sharpe (rf=5%)       —                    −6.0
  Sharpe (rf=0, raw)   +2.2                 −1.3
```

**The edge is real but it does not survive transaction costs.** Under idealised
flat-IV, zero-cost pricing the strategy makes +15.7% with a 94% win rate — the
mean-reversion containment thesis genuinely works. But once each leg is priced
with the equity-index skew and charged realistic commission + slippage on entry
**and** exit, the ~$12–14/contract round-trip friction consumes the entire thin
sector-ETF credit and the strategy ends slightly **negative**. The high win rate
(60%) with a sub-1 profit factor (0.52) is the classic credit-spread tail: many
small wins, occasional losses ~3× the size of the wins.

**On the "wildly negative Sharpe."** An earlier version reported a Sharpe near
**−14** while showing a *positive* +4% return. That was an **equity-curve
artifact, not a real result**: the curve recorded only *realised* capital, so it
was a step function that stayed flat on ~89% of days and jumped only on exit days.
That collapses the daily-return standard deviation to a tiny number; dividing a
small (and, after subtracting the 5% risk-free rate, slightly negative) mean
excess return by that tiny std produces an absurd magnitude. The fix is to
**mark every open spread to market on every bar** (now done), which yields a
smooth, economically meaningful equity curve. The Sharpe is still negative — but
now for the *honest* reason that the net strategy loses to its frictions, not
because of a degenerate denominator.

**Practical takeaway.** Do not trade this as-is on the standard sector ETFs with
retail-style frictions. It would need one of: (a) materially cheaper execution
(institutional commissions, mid-or-better fills), (b) wider buffers / longer DTE to
collect larger credits that dwarf the fixed friction, or (c) restriction to the
highest-premium regimes (elevated VIX, wide RS divergence) where the gross edge is
large enough to clear costs. None of those were applied here, because doing so to
chase a positive number would be overfitting.

---

## Common Mistakes

**Entering when SPY ADX > 30.** This is the most dangerous regime for this strategy. In trending markets, sector rotation accelerates rather than reverts. The ADX filter is not optional — override it at your own risk.

**Trading thin-market sector ETFs.** XLRE and XLB have lower average daily volume than XLK or XLF. The spread pricing may be less favorable (wide bid-ask on the actual options). The backtest assumes efficient pricing — check real options quotes before entering in thinly-traded sectors.

**Letting both legs run simultaneously into expiry.** The two legs have independent risk profiles. A macro event (e.g., Fed rate decision) can simultaneously spike energy and crush tech — simultaneously losing on both legs. The individual stop-losses per leg (2× credit) limit this damage, but don't treat the dual spread as fully uncorrelated.

**Expecting high trade frequency.** This strategy trades weekly at most. With the SPY ADX filter and minimum confidence requirements, there may be extended periods (2-4 weeks) of no entries. This is correct behavior — patience is part of the edge. Forcing trades in ambiguous regimes destroys the positive expectancy.


---

## Audit & money verdict — 2026-07-03

**End-to-end audit (UI · Backtest · Screening · Tests · Training): all surfaces PASS.**

- **Real backtest:** frictionless +15.7% → **net −6.7%** · 176 trades (11 SPDR ETFs 2021→2026).
- **Money verdict:** The cross-sectional containment edge is **real frictionless** (94% win, PF 3.0) but does **not survive transaction costs** — sector-ETF credits ($40–120) are too thin vs ~$12–14 round-trip friction. Would need cheaper execution or wider/longer structures.
- **Deploy:** Paper only.

_Audited on real DB data via the production backtest + screener paths. Full cross-strategy report: `docs/reviews/2026-07-03_top10_strategy_audit.md`._
