# Top-10 Strategy Audit — 2026-07-03

End-to-end audit of the 5 best rule-based + 5 best AI strategies across **five
surfaces** — UI, Backtest, Screening, Test cases, Training (AI) — plus an honest
"can we actually make money" verdict per strategy. Every strategy was run on
**real DB data through the production backtest and screener paths** (no proxies).

**Bottom line up front:** none of the 10 beats buy-and-hold SPY on a risk-adjusted
basis. The honest, defensible value is (a) **drawdown reduction** (trend /
momentum / the covered-call overlay), and (b) **one latent credit-side edge** in
`vix_term_structure` that is currently buried under a losing AI leg. Real
directional alpha is not demonstrated on the available data.

---

## Surface matrix

| Strategy | Type | UI | Backtest | Screening | Tests | Training | Deploy |
|---|---|:--:|:--:|:--:|:--:|:--:|---|
| trend_following | rule | ✅ | ✅ | ✅ | ✅ 13 | n/a | overlay (crash insurance) |
| ts_momentum | rule | ✅ | ✅ | ✅ | ✅ 14 | n/a | overlay (crash insurance) |
| iron_condor_rules | rule | ✅ | ✅ | ✅ | ✅ 14 | n/a | paper only |
| ivr_credit_spread | rule | ✅ | ✅ | ✅ | ✅ 21 | n/a | paper only |
| bull_put_spread | rule | ✅ | ✅ | ✅ | ✅ 22 | n/a | paper only |
| covered_call_ai | ai | ✅ | ✅ | ✅ *(wired)* | ✅ 24 | ✅ leak-free | paper only (overlay) |
| vix_term_structure | ai | ✅ | ✅ | ✅ *(wired)* | ✅ 24 | ✅ leak-free | paper only |
| vrp_premium | ai | ✅ | ✅ | ✅ | ✅ 7 | ✅ leak-free | paper only |
| rs_credit_spread | ai | ✅ | ✅ | ✅ *(wired)* | ✅ 22 | ✅ leak-free | paper only |
| hmm_regime | ai | ✅ | ✅ | ✅ | ✅ 18 | ✅ leak-free | paper only (filter) |

Backtest windows: price strategies 2021-01→2026-06 (SPY); options strategies
2024-04→2026-03 (SPY, where real option IV exists); rs_credit_spread
2021-04→2026-04 (11 SPDR sector ETFs).

---

## Per-strategy verdict

### Rules

**trend_following** — +57.7% / Sharpe 0.39 / −17.9% DD / 17 trades.
Measured on 30y of real SPY: it makes **less** than buy-hold (~1.5 CAGR pts lower)
and the app's **excess-Sharpe is a dead tie (0.36 vs 0.36)** — the only durable
edge is **drawdown (−20% vs −55%)**. Genuine crash-insurance, no return/Sharpe
alpha. *(Guide had fabricated Sharpe/2008 numbers — corrected.)*

**ts_momentum** — +82.2% / Sharpe 0.555 / −19% DD / 2 trades.
Over 2021-26 **and** 2006-26, buy-hold beat it on **both return and Sharpe**; the
only honest edge is shallower drawdown (−34% vs −55%). Buy-hold beta with a crash
filter. *(Guide overstated the edge — corrected.)*

**iron_condor_rules** — +3.4% / Sharpe −0.66 / −5.6% DD / 46 trades / PF 1.49.
No durable edge: +3.4% is **below the ~4.5% risk-free rate**; losers ~2.8×
winners; stop-outs cluster on trend days. Regime-dependent; loses in sustained
trends. *(Guide example strikes were wrong — corrected; dead code removed.)*

**ivr_credit_spread** — +0.78% / 12 trades / 83% win / PF 2.62.
Correctly **dormant in low vol** (IVR cleared 0.50 on only 12 of ~374 bars). The
VRP edge is real but only pays in elevated-IV regimes (2020, 2022). Underperformed
cash this window; not broken, just regime-starved.

**bull_put_spread** — 1 trade / +0.48% (fixed from a broken stub).
The IVR≥40% "fear" gate and the price>MA50 "bullish" gate fight each other, so it
fires **once** on SPY — too few to prove anything. Its honest use is scanning a
**broad optionable universe**, not single-symbol SPY.

### AI

**covered_call_ai** — +137.7% / Sharpe 0.82 / −18.8% DD / β 0.84.
**Beta, not alpha.** ~121 of 138 pts are just SPY in a bull run; deleting the AI
head and always selling 0.30Δ **beats it** (+141.7% / Sharpe 0.87). The *overlay*
does beat buy-hold risk-adjusted (Sharpe 0.87 vs 0.65, DD −16% vs −25%) — that is
the BuyWrite premium-harvest effect, **not** the model. Training is leak-free but
adds no value (75% majority-class label).

**vix_term_structure** — −2.06% / 40 trades / PF 0.77.
Loses modestly — **but the decomposition is the story**: the credit/contango leg
has a **real edge (+$2,647, 79% win)**, while the AI's backwardation/debit leg is
the money-loser (**−$4,659, 29% win**). **A credit-only version would plausibly
flip it net-positive** — the single most actionable improvement in this set.
Training leak-free, derived from VIX spot (no dependence on the empty futures
table).

**vrp_premium** — +12.2% / 34 trades / PF 1.07.
No edge on this data: the reconstructed ATM IV correlates only **0.38 with VIX**
and its realized VRP ≈ **+1 vol-pt (≈ zero)**; the model over-estimates the
premium (entry `vrp_hat` avg 6.3 vol-pts). The +12% is a calm-window / short-vol
artifact. Built to harvest the real **+4.8 vol-pt** premium **with a clean IV feed
(e.g. VIX)** — not on the noisy reconstructed IV.

**rs_credit_spread** — frictionless +15.7% → **net −6.7%** / 176 trades.
The cross-sectional containment edge is **real frictionless** (94% win, PF 3.0),
but sector-ETF credits ($40–120) are too thin vs ~$12–14 round-trip friction, so
it **does not survive costs**. Leak-free, mark-to-market correct. Would need
materially cheaper execution or wider/longer structures to clear costs.

**hmm_regime** — −0.19% / 32 trades / PF 0.968.
~Flat, no standalone edge (the reported −7 Sharpe is a cash-drag metric artifact;
rf=0 Sharpe ≈ 0). The regime classifier itself is high-quality and **leak-free**
(37 expanding walk-forward refits, filtered — not smoothed — posterior). Its value
is **as a filter/overlay** gating other strategies, not as capital-committing
standalone. Paper-only.

---

## "Can we make money?" — the straight answer

1. **Drawdown reduction is the one robust, real benefit** — trend_following,
   ts_momentum, and the covered-call overlay roughly halve drawdowns at a small
   return cost. No excess-Sharpe alpha, but genuine crash insurance.
2. **`vix_term_structure` credit-only** is the most concrete money lever found: its
   premium-selling leg works; removing the losing AI debit leg would likely turn
   the whole thing positive. Worth building.
3. **A clean IV feed is the biggest unlock** — it converts `vrp_premium` into a
   real ~+4 vol-pt VRP harvester (the reconstructed OHLC-inverted IV is too noisy).
4. Everything else is regime-starved (ivr, bull_put, iron_condor), cost-killed
   (rs_credit_spread), or plain beta (covered_call_ai).

---

## What was fixed in this audit

- **3 screening gaps wired** — `covered_call_ai`, `rs_credit_spread`,
  `vix_term_structure` had scorers in `engine/screener.py` but were never
  dispatched in `scan.py`; now return rows with proper columns.
- **Screener↔backtest gate alignment** — ivr_credit_spread screen gate 0.40→0.50;
  bull_put_spread screen ADX 30→40; `_display_row_trend` now emits a sort key.
- **Column defs** added for `vrp_premium` / `stock_bond_vol_rotation` screeners.
- **Guides corrected** where they overstated edges (trend_following, ts_momentum,
  iron_condor_rules had fabricated/mislabeled numbers) — now match measured reality.
- **Tests** extended across the set (leak/purge/cost/training coverage);
  full suite **594 passing**.

## Open recommendation (not applied — needs sign-off)

`risk/metrics.py` subtracts the 5% risk-free rate on **every** day including
flat-cash days, so any intermittent, mostly-in-cash strategy shows a wildly
negative Sharpe (e.g. hmm_regime's −7 is really ≈ 0). The fix is to compute excess
return over *deployed* days (or credit idle cash at the risk-free rate in the
equity curve). It is the correct change but touches every strategy's headline
metric and several tests, so it is flagged rather than applied.
