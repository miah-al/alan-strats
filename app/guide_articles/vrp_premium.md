# VRP Premium Harvester

**Slug:** `vrp_premium` · **Type:** AI (gradient-boosting regressor) · **Assets:** SPY, TLT

## The idea

Implied volatility is, on average, higher than the volatility that subsequently
*realizes*. That gap — the **variance risk premium (VRP)** — is what option
sellers get paid. But the premium is small and the left tail (a vol explosion
while you are short) is what wrecks short-vol books. So "sell premium" is not an
edge; everyone knows IV > RV. The edge is **timing**:

1. **Forecast realized vol better than the market's implied.** A gradient-boosting
   *regressor* predicts forward `H`-day realized vol from price / IV / macro
   features. The traded signal is the *explicit* premium

   ```
   VRP_hat = ATM_IV_now − forecast_RV_H
   ```

2. **Stand aside when the model expects realized vol to overrun implied.**

When `VRP_hat` is rich enough and risk gates pass, the strategy sells a
**defined-risk iron condor** (short ~16Δ call/put spreads) at the tenor the real
IV surface covers, priced with the equity-index volatility skew.

## How it differs from `iron_condor_ai`

`iron_condor_ai` is a price-*excursion classifier* (will price stay in a band?).
`vrp_premium` forecasts *vol* and trades the IV−RV spread directly, and it prices
off the **real reconstructed ATM IV** supplied in `auxiliary_data["atm_iv"]`.

## Mechanics

- **Features (no look-ahead):** trailing realized vol (5/10/20d), current ATM IV,
  current VRP, 5-day IV change, momentum (5/20d), downside accumulation, ATR%,
  distance to MA20, VIX level/change, 10y-rate change.
- **Label:** forward `H`-day annualized realized vol. The last `H` rows are
  purged from every training window, so a row never trains on its own future.
- **Walk-forward:** warm-up, retrain every `retrain_every` bars on history up to
  `i − H`.
- **Data-hygiene gate:** entries are blocked when `iv_now` is an implausible spike
  versus its own trailing median (a bad OHLC-inversion print), or above an
  absolute cap. Trading corrupt IV manufactures a phantom premium.
- **Exits:** 50% profit target, 2× credit stop, force-close near expiry.
- **Costs:** per-leg slippage + commission on entry *and* exit (4 legs).

## Honest performance note — read this

The edge is **bounded by the quality of the implied-vol input**.

- With a **clean IV measure** (e.g. VIX, which is the actual CBOE 30-day SPX
  implied vol), SPY's realized VRP is a healthy **~+4 vol-points** — a real,
  decades-documented premium this strategy is built to harvest.
- With the project's **reconstructed per-contract IV** (implied vol inverted from
  *closing* prices of illiquid weekly options), the IV series correlates only
  ~0.38 with VIX and the realized VRP collapses to **~+1 vol-point (≈ none)**.

On the reconstructed IV, a SPY backtest over the benign 2024-2026 window prints a
positive return, but inspection shows it is **"sell OTM premium in a calm bull
market"** (high win rate, rare large losses) — *not* a validated VRP edge. TLT,
with fewer glitches, loses outright.

**Bottom line:** the code is correct (leak-free, skew-priced, costed,
hygiene-gated and unit-tested), but a deployable edge requires a clean historical
IV feed. Do not size this off the reconstructed-IV backtest.

## Worked example — one trade

A representative entry (illustrative, ~10-DTE SPY condor):

```
Date            2025-03-14   SPY = 595.00
Real ATM IV     iv_now      = 0.140   (14.0%)
GBM forecast    rv_hat      = 0.095   (9.5% forward realized)
Signal          VRP_hat     = 0.140 − 0.095 = 0.045  (≥ vrp_min 0.02 ✓)
Gates           VIX 17 ≤ 40 ✓ | sentiment +0.05 ≥ −0.55 ✓ | iv_now ≤ 2.5×med ✓

Build a 16Δ iron condor, T = 10/252, skew-priced:
  Sell  595c-side call @ 612   buy wing @ 643      (5% beyond short)
  Sell  595p-side put  @ 578   buy wing @ 549
  Net credit  ≈ 3.40 / share  →  $340 per 1-lot (after entry slippage+comm)

Size: risk 2% of $100k = $2,000.  Max loss/lot = (643−612 − 3.40)×100 ≈ $2,760
      → 1 contract.  Collect $340 now.

Exit (whichever first):
  • +50% of credit  → buy back at ≈ $1.70 → +$170 (most common, hit here)
  • −2× credit stop  → buy back at ≈ $10.20 → −$680
  • DTE ≤ 2          → close at mark
Outcome: price drifted to 600 by 2025-03-24, condor decayed, closed +$168 net.
```

## What the backtest actually did (read with the performance note)

On real SPY chain IV (2024-04 → 2026-03, first trade once the model warms up in
2025-01) the strategy took **34 trades, 79% wins, +12.2%** (Sharpe 1.2, max DD
−2.9%) — *but* `vrp_hat` at entry averaged **6.3 vol-pts** while the realized
premium on this reconstructed IV was **~+1 vol-pt**. The model is over-optimistic;
the gains are OTM premium collected in a calm bull window (24 profit-target exits,
worst single trade **−$2,171**). The hygiene gate already removes the worst
IV-reconstruction glitches. Treat the residual as **un-validated**, not edge.

## Failure modes

- **Vol regime shift / crash:** short premium is short the tail. The defined-risk
  condor caps loss per trade, but a cluster of breaches in a vol spike still hurts.
- **Bad IV data:** mitigated by the hygiene gate, but garbage-in still degrades the
  signal — the headline limitation above.
- **Short, benign test window:** 2024-2026 contains no major equity crash, so
  out-of-sample tail behaviour is untested here.


---

## Audit & money verdict — 2026-07-03

**End-to-end audit (UI · Backtest · Screening · Tests · Training): all surfaces PASS.**

- **Real backtest:** +12.2% · 34 trades · PF 1.07 (SPY 2024-04→2026-03).
- **Money verdict:** **No edge on the reconstructed IV** (corr 0.38 with VIX; realized VRP ≈ +1 vol-pt). The +12% is a calm-window / short-vol artifact (the model over-estimates the premium). Built to harvest the real +4.8 vol-pt premium **with a clean IV feed** (e.g. VIX).
- **Deploy:** Paper only (needs a clean IV feed to have an edge).

_Audited on real DB data via the production backtest + screener paths. Full cross-strategy report: `docs/reviews/2026-07-03_top10_strategy_audit.md`._
