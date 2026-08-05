# Stock-Bond Vol Rotation

**Slug:** `stock_bond_vol_rotation` · **Type:** AI · **Assets:** SPY ⇄ TLT

## The idea

Two ideas combined into one SPY/TLT options strategy:

1. **Rotate the premium, don't fix the leg.** The variance risk premium exists on
   both SPY and TLT, but its richness rotates between them. Each day the strategy
   forecasts each asset's premium (`VRP_hat = real ATM IV − GBM-forecast realized
   vol`) and sells a **defined-risk iron condor on whichever asset's premium is
   richer**, gated and priced off that asset's own real skew-adjusted IV.

2. **Let the correlation regime set the risk.** The stock-bond correlation governs
   how dangerous a short-vol book is:
   - **Negative correlation** ("bonds hedge stocks", the pre-2020 norm): a vol
     shock in one leg is cushioned by the other → size up.
   - **Positive correlation** (the 2022 inflation regime: stocks *and* bonds sell
     off together) → no hedge → de-risk (smaller size, same premium bar).

   Sizing scales linearly from full at corr ≤ −0.3 to `corr_pos_size_mult` at
   corr ≥ +0.3.

## How it differs from `rates_spy_rotation`

`rates_spy_rotation` is a long-only allocation that switches SPY/TLT/cash weights
by a rate-equity regime. This strategy trades the **relative variance-risk
premium** between equities and bonds with defined-risk option structures, gated by
their realized **correlation**, not by rate direction.

## Mechanics

Inherits the option pricing, the forward-RV regressor, the walk-forward label
purge and the data-hygiene IV gate from [`vrp_premium`](vrp_premium.md). New here:

- Trains a separate RV regressor per asset (each purged on its own calendar).
- Each bar: rank SPY vs TLT by `VRP_hat`, take the richer one that clears the
  gates, size by the 60-day SPY-TLT correlation regime.
- Trade management (50% target / 2× stop / expiry), costs and MTM identical to
  `vrp_premium`.

## Honest performance note — read this

Same ceiling as `vrp_premium`: **the edge is bounded by IV data quality.** Two
further realities from the real-data backtest (2024-2026):

- **The correlation hedge mostly wasn't there.** Over the test window the SPY-TLT
  60-day correlation averaged **+0.11 and was positive ~60% of the time** — the
  post-2022 "no hedge" regime. The strategy correctly de-risked, but the
  protective premise (negative correlation) rarely applied.
- **Rotation collapsed onto SPY.** On the reconstructed IV, SPY's noisier IV
  produced a higher `VRP_hat` more often, so ~90% of trades went to SPY — i.e. it
  reduced to "short SPY vol in a calm window," the same artifact described in the
  `vrp_premium` guide. TLT trades were a small net loss.

**Bottom line:** correct, leak-free, unit-tested code; no validated edge on the
reconstructed-IV data and the benign test window. It becomes interesting only with
(a) a clean IV feed and (b) a sample that includes a genuine negative-correlation,
risk-off regime where the bond hedge actually pays.

## Worked example — one rotation decision

```
Date            2025-05-09
SPY = 580   TLT = 92
60-day SPY-TLT correlation = +0.18  → positive ("no hedge") regime
  size multiplier = blend(-0.3→1.0, +0.3→0.4) at +0.18 ≈ 0.52  → half size

Forecast VRP per asset (real ATM IV − GBM forecast RV):
  SPY:  iv 0.135 − rv_hat 0.092 = +0.043
  TLT:  iv 0.108 − rv_hat 0.101 = +0.007   ← thinner
Pick SPY (richer premium ≥ vrp_min 0.02). Gates pass (VIX 18, IV sane).

Trade: 16Δ SPY iron condor, ~10 DTE, skew-priced.
  Risk budget = 2% × $100k × 0.52 (corr de-risk) = $1,040 → 1 contract.
  Collect ≈ $300 credit; manage at +50% / −2× / DTE≤2.

Had correlation been −0.25 (bonds hedging stocks), the same SPY signal would
size at the full 2% — the TLT book cushions an equity vol shock.
```

## What the backtest actually did (read with the performance note)

Real SPY+TLT data (2024-12 → 2026-03): **54 trades, +21.4%** — but **49 went to
SPY, 5 to TLT**, and the 60-day correlation averaged **+0.11 (positive ~60% of
days)**. So it reduced to "short SPY vol in a calm window" with the bond hedge
mostly absent. **Not a validated edge** on this IV/window.

## Failure modes

- **Positive-correlation crash:** both legs fall together; the "hedge" is absent
  exactly when you need it. The de-risking mult is the only defence.
- **IV data quality / short window:** as for `vrp_premium`.
