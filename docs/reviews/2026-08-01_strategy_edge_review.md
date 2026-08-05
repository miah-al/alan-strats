# Strategy Edge Review — 2026-08-01

Can these strategies actually make money? Reviewed against real data on the
rebuilt `AlanStrats` database, through the production backtest path.

Every number here was measured, not estimated. Where a claim could not be
verified it is labelled as such.

---

## The most important finding

**Four strategies do not price options at all.** Their backtest P&L is a
hardcoded constant multiplied by a fabricated credit; the underlying price never
enters the payoff. `grep -c bs_price` returns 0 for each, as does a search for
slippage or commission.

| Strategy | What its "P&L" actually is |
|---|---|
| `broken_wing_butterfly` | `pnl = ±entry_credit × 0.5 or 0.35 × 100` — constant |
| `calendar_spread` | `roi = −stop_loss_pct` or `+profit_target_pct × 0.8` — two constants |
| `wheel_strategy` | `pnl = half_profit × 100` — half the credit, always |
| `earnings_straddle` | `pnl = entry_credit × 0.45 × 100` after 2 bars — unconditional |

In every case the credit itself is invented rather than priced — e.g.
`broken_wing_butterfly.py:161`: `entry_credit = p["min_credit"] + atr_v * 0.1`,
commented `# proxy`.

**Consequence: the ranking rows for these four strategies are not backtest
results and must not be used to allocate capital.** This also explains the
profit-factor-of-infinity anomaly flagged earlier — it was an artifact, and now
the mechanism is known.

There is **no look-ahead bias** in any of the six strategies reviewed (zero
`shift(-n)` or forward-indexing hits). That is not reassuring: there is too
little market data in the P&L for anything to leak from.

---

## Why `broken_wing_butterfly` never loses

Its only loss path is unreachable. The stop is
`wide_breached = abs(spot - wide_k) < 1.0` (`:146`), which requires SPY to close
**within $1 of a level ~10.4% above entry spot** inside a 14-bar window. Only 4
bars out of 1378 in the sample even reach that level. Result: **0 stops in 43
trades**, hence a 100% win rate, PF ∞, and MaxDD 0.00.

Worse, on its own optimistic numbers it still loses to costs. A 1-2-1 butterfly
is 4 contracts opened and closed = 8 leg-fills. At the engine's own
`DEFAULT_COMMISSION_PER_LEG = 0.65` + `DEFAULT_SLIPPAGE_PER_LEG = 0.05`:

```
round-trip friction   8 × $5.65 = $45.20
modelled gross profit             $27.02  per trade
net                              −$18.18  per trade  →  −$781.74 over 43 trades
```

---

## Per-strategy verdicts

### `wheel_strategy` — **FIX** (highest-value fix in this batch)

The mechanism is **real and uncontroversial**: short-put variance risk premium
plus skew premium. Index put sellers are genuinely paid for both. Costs are not
the problem — 2 leg-fills round trip ($11.30) against a ~$800 credit. It is the
only strategy here whose economics would comfortably survive friction.

The implementation is what is broken:

- **Assignment is settled at first touch, not at expiry** (`:165`, `:170-174`).
  `assigned = spot < put_k` is evaluated daily and closes the trade the first
  time SPY closes below the strike — booking a loss of ~$0 by construction. A
  cash-secured put is assigned *at expiry* at the terminal price. Measured
  across all 691 overlapping 28-day touched windows: **mean loss booked $3.18/share
  vs true $6.74/share (2.1× understated); worst booked $30.50 vs true $75.99**.
  Both "assigned" trades in the run came out *positive* — an assignment that
  makes money is the tell.
- **Strike selection is dimensionally wrong** (`:190`):
  `put_k = spot × (1 − put_delta × iv × √(28/252))` treats a delta as a
  multiplier on σ√T. The strike lands **1.81% below spot** where a true 1-σ
  28-day move is **5.02%** — 2.77× too close, i.e. ~40-delta not the documented
  30-delta.
- **Phase 2 does not exist.** The covered-call leg — the thing that makes it
  "the Wheel" — is unimplemented; `p["call_delta"]` is never read. On assignment
  the code closes out instead of taking stock and selling calls.
- **The entry gate is self-contradictory**: `IVR ≥ 0.40` (on a *VIX* rank, not
  the underlying's) **and** `spot > MA50` **and** `15 ≤ ADX ≤ 30`. Elevated fear
  and an uptrend are anti-correlated, and SPY's median ADX is 31.3 — which fails
  the band outright. Hence **5 trades in 5.5 years**.

**Fix:** invert BS delta for the strike (reuse `bull_put_spread._short_put_strike_for_delta`,
which already does this correctly); settle assignment at expiry on the terminal
close, then actually hold stock and sell calls; price with `bs_price_skew` and
charge per-leg costs both sides; replace the triple gate with an always-on
28-DTE 30-delta roll gated only on `VIX ≤ 35`. That alone should take it from 5
trades to ~65 and produce a testable series.

### `bull_put_spread` — **KEEP the engine, FIX the gate and sizing**

This is the one properly-built strategy in the batch and should be the template
for the others: real skew-adjusted pricing (`bs_price_skew`), strike by BS-delta
inversion via bisection, **correct and symmetric costs** (entry slippage folded
into the credit, entry commission, exit commission+slippage — $22.60/contract
round trip for 4 leg-fills), daily mark-to-market equity, and a correct
`compute_all_metrics` call.

Its problem is economic, not structural: the `IVR ≥ 0.40 AND spot > MA50` gate
fires only 13 times in 5.5 years, and `position_size_pct` resolves to **1
contract every time**. It is technically correct and economically pointless at
that size.

Minor real defect: `:348` uses `(n - i) > dte_bars` — total series length — to
refuse entries near the end of data, which is not knowable live. Small impact
(suppresses the last ~21 bars) but it is a genuine peek at the future.

**Fix:** loosen to `IVR ≥ 0.25` or drop the MA50 filter (the spread is already
delta-limited) → ~60–80 trades; enter at 45 DTE and exit at 21 DTE so theta
capture roughly triples against the fixed $22.60 friction; size with a 2–3
contract floor.

### `expiry_max_pain` — **DATA-BLOCKED**, plus 3 real defects

The mechanism is real and correctly named (dealer long-gamma hedging pins spot
toward the high-OI strike into monthly OpEx). Costs are correct and complete (8
leg-fills round trip). But **`mkt.OptionSnapshot.OpenInterest` is 100% NULL**, so
max pain cannot be computed at all.

The dangerous part is how that failure presents:

- `compute_max_pain` returns `spot` on zero OI (`:243-244`), so `max_pain == spot`,
  `dist_pct = 0.0000`, and every bar is rejected as *"spot already pinned, no
  convergence to capture"*. **A total data outage is silently disguised as a
  legitimate no-signal.** Anyone reading the log would conclude the edge wasn't
  there. It should raise, or the loader should block.
- The documented volume fallback is **dead code**: `load_option_snapshots` never
  projects `Volume`, so the column can never be found. Projecting it would make
  the strategy runnable today without waiting for an OI backfill.
- `_chain_for_opex` silently falls back to the whole snapshot when no matching
  expiry exists (`:786-787`), mixing expiries — directly against its own
  docstring ("no mixing of expiries").

### `calendar_spread` — **KILL as-is / rewrite**

The real edge is term-structure VRP (front-month IV richer than back per unit
√T). **The code cannot express it**: both legs use the same IV (`iv_v = vix_v/100`,
`:173-174`), and the documented `front_back_iv_min` rule is never read. Both
entry filters are provably tautologies — the price ratio is identically
√(53/25) = 1.456 for every bar, and the debit is always positive. The measured
−1.27% CAGR is just the frequency with which ADX crosses 25.

### `earnings_straddle` — **KILL / rebuild**

**The earnings backtest never looks at earnings.** The slug has no entry in
`LOADERS_BY_SLUG`, so `mkt.Earnings` — which is populated — is never loaded. The
entry condition degenerates to `VIX ≥ 40`, which clears on **4 days out of 1378**
(the April 2025 tariff spike). It is a VIX-panic strategy wearing an earnings
label.

Six of its nine parameters are never read, including three the UI exposes as
sliders that therefore do nothing. And a short straddle — the most convex
short-gamma structure that exists — books +45% of credit unconditionally, with
**no code path that can produce a loss**.

The guide teaches a defined-risk iron condor and states "this is why wings are
non-negotiable"; the code implements a **naked short straddle with no wings**.

### `broken_wing_butterfly` — **KILL**

Covered above. Even on its own fabricated P&L it loses $18.18/trade to costs.

---

## Guide accuracy — systematic inflation

Four guides publish backtest-statistics tables that **no code in this repo
produces**:

| Guide | Claims | Actually measured |
|---|---|---|
| `broken_wing_butterfly.md` | 68 trades, 62% win, PF 1.68, Sharpe 0.58, +6.4%/yr | 43 trades, 100% win, PF ∞, Sharpe 2.12, +0.22%/yr, zero stops |
| `wheel_strategy.md` | 284 cycles, 92.3% win, +18.7%/yr, Sharpe 0.84, worst −$4,820 | 5 trades, 100% win, +0.41%/yr, Sharpe 0.95, no losing trade exists |
| `bull_put_spread.md` | 156 trades, 71.2% win, PF 1.73, Sharpe 0.68, +9.8%/yr | 13 trades, 69.2% win, PF 1.78, Sharpe −0.22, +0.17%/yr |
| `bull_put_spread.md` | 20-delta short put, $10 wings | code uses 30-delta, ~5% of spot (~$19–30 wide) |

`expiry_max_pain.md` is the model the others should copy: it explicitly labels
its P&L figures as illustrative, "NOT recorded live fills or backtest output",
and carries TODOs where real numbers are missing.

---

## Cross-cutting notes

- **No `compute_all_metrics` argument-order bug** in any of the six (a defect
  class that has appeared here before).
- **Sharpe and MaxDD are structurally meaningless** for the four
  no-mark-to-market strategies. `equity.append(capital)` only moves on close, so
  the curve is a step function of realised P&L. `broken_wing_butterfly`'s Sharpe
  of 2.12 is 43 near-identical guaranteed wins divided by their own near-zero
  dispersion.
- **`starting_capital` is silently ignored** by all four constant-P&L
  strategies — it lands in `**kwargs` and is dropped; `capital = 100_000.0` is
  hardcoded.
- **Slippage may be understated for ATM legs.** `DEFAULT_SLIPPAGE_PER_LEG = $0.05/share`
  matches the measured 30-delta half-spread exactly, but ATM half-spreads
  measure ~$0.161 (3.2×). Caveat: the stored quotes look synthetic — the
  half-spread is exactly 1.0% of mid in 32,833 of 40,879 rows — so treat this as
  indicative.

---

## Salvageability ranking

1. `wheel_strategy` — real edge, survives costs, needs correct assignment + strike + a gate that fires
2. `bull_put_spread` — already correct; needs a wider gate and real sizing
3. `expiry_max_pain` — real edge, correct costs, blocked on Open Interest
4. `calendar_spread` — edge exists but is inexpressible in the current code
5. `broken_wing_butterfly` — edge dies to costs even on its own optimistic P&L
6. `earnings_straddle` — does not implement the strategy it is named after

---

# Part 2 — the AI strategies, the vol/tail book, and the data layer

## The single most important result: the ML adds no alpha anywhere

Five AI strategies were ablated by disabling the model (constant stubs and
randomised stubs) and re-running the identical production path. **In none of
them does the ML head earn its keep; in three it is actively negative.**

| Strategy | Shipped | Best ML-OFF ablation | ML contribution |
|---|--:|--:|---|
| covered_call_ai | 16.73% | 16.71% (always 0.30Δ) | **+0.02% — noise** |
| iron_condor_ai | 0.64% | **4.55%** (`iron_condor_rules`, no ML) | **−3.91%** |
| vix_term_structure | 1.26% | **2.31%** (always credit leg) | **−1.05%** |
| yield_curve_regime | 1.09% | 0.86% (always bull-put) | +0.23%, but MaxDD −16.0 vs −5.1 |
| hmm_regime | 0.26% | **1.05%** (always state 0) | **−0.79%** |

A **random coin flip beat `covered_call_ai`'s model on 2 of 3 seeds** (17.04 /
17.31 / 16.63 vs 16.73). All three random seeds beat `hmm_regime`.

Direct out-of-sample classifier quality confirms it — every one is worse
calibrated than a constant predicting the base rate, and less accurate than
always predicting the majority class:

| Classifier | OOS AUC | Verdict |
|---|--:|---|
| iron_condor_ai | 0.621 | real rank info, but corr(prob, PnL) = **−0.158** — the label is mis-specified |
| covered_call_ai | 0.547 | ~coin flip |
| vix_term_structure | 0.544 | ~coin flip |
| yield_curve_regime | 0.509 macro | BEAR class AUC **0.432 — anti-predictive** |

Train/test discipline is genuinely **clean** — purge gaps are correct and
load-bearing (removing them moves AUC 0.621 → 0.611; fitting on everything gives
0.879, and that gap does *not* appear). The problem is not leakage. The models
simply have no edge.

**`iron_condor_ai` is beaten roughly 7× by its own non-AI sibling sitting in the
same directory.**

## Bugs fixed in this pass

| Fix | Effect |
|---|---|
| **`db/sync.py` resume key ignored contract type** | Calls are enumerated before puts, so once calls covered every date, *every put contract* was skipped. Produced a **63,010-row, calls-only** surface. Silently breaks every credit-spread, condor and put strategy. |
| **`vix_spike_fade` / `calendar_spread_vix` destroyed the entry debit** | Cash paid the premium; exit credited only the P&L. `vix_spike_fade`: −3.71% CAGR / −18.88% DD → **−0.27% / −1.46%**. |
| **`iron_condor_rules` look-ahead leak** | `(n − i) > dte_tgt` made a trade's existence depend on future data (37 entries appeared only when the sample was extended). Its guide explicitly and falsely claimed "no look-ahead". |
| **`dealer_gamma_regime` unpacked a scalar** | `price, _ = bs_price_skew(...)` — guaranteed `TypeError` on the first trade. |
| **`covered_call_ai` / `vix_term_structure` undercharged slippage 100×** | `$0.70`/leg instead of `$5.65` — slippage is per *share* and needs the 100-share multiplier. Accounts for `vix_term_structure`'s entire reported return (1.26% → ~0). |
| **`iron_condor_ai` guide documented strikes backwards** | Guide said high conviction → 0.20Δ tighter; the code does 0.13Δ **wider**. Anyone trading the guide placed strikes inverted on every entry. |
| **Ranking harness: warm-up contamination** | Feeding only the reporting window left 12-month momentum `NaN`, and `NaN > 0` is `False` → forced flat for a year. Understated `ts_momentum` by ~3pp and `trend_following` by ~3.5pp. |
| **`annualized_return` used row count, not elapsed time** | Sparse equity curves inflated CAGR — `vrp_premium`'s real 14.3% total return reported as **101%/yr**. |
| **Ranking harness mislabelled degenerate runs** | Data errors reported as "ran clean but produced no trades". |

## Remaining critical bugs (found, not yet fixed)

| Sev | Location | Bug |
|---|---|---|
| CRITICAL | `vol_calendar_spread.py:1202` | `max(0.01, …)` floor on credit calendars → **2,173 contracts on $100k** and ≈ −$1.3M fictional P&L. Fires the moment `max_term_slope` is relaxed. |
| CRITICAL | `short_squeeze_detector.py:1088` / `:1009` | Option debit charged twice; a trade that doubles in value still nets a capital loss. |
| CRITICAL | `rs_credit_spread.py:553` vs `:437,:483` | Entry priced at 21/252 yr, every mark at ≤10/252 — an instant unearned theta gift. **This artifact is the entire "frictionless edge"** a prior audit credited it with: corrected, it is −$4,167. |
| CRITICAL | `earnings_pin_risk.py:130-145` | `_ConstantClassifier` returns P = 1.000, so `pin_threshold` can never bind. All four persisted `.pkl` files *are* this stub. |
| HIGH | `short_squeeze_detector.py:232` | Reads `ImpliedVol` but the loader aliases it to `iv` → real IV never read → undisclosed VIX×1.5 proxy on 344/344 dates. |
| HIGH | `rs_credit_spread.py:388-396` | Both "independent" models trained on one arbitrary sector's features **and labels**, then applied to a different sector. The AI layer is noise. |
| HIGH | `vrp_premium` / `stock_bond_vol_rotation` | `**kwargs` accepted and never applied — every UI slider is a no-op. |
| HIGH | 13 of 23 `saved_models/*.pkl` | Unloadable under sklearn 1.9.0 (`No module named '_loss'`). `load_model` raises rather than returning False, so every non-SPY ticker silently scores 0 in the screener. |
| MED | `iron_condor_rules.py:406` | `max_concurrent` is dead code — measured **21 simultaneous open condors** against a documented cap of 5. |
| MED | `backtest()` writes to `saved_models/` | A read-only measurement mutates git-tracked files. |

## Verdicts

**Deployable (2):**
- `covered_call_ai` — **but delete the ML.** The +1.4%/yr and −6.5pp drawdown vs
  buy-and-hold come entirely from the covered-call overlay (BuyWrite), which the
  model does not create. Ship it as a mechanical 0.30Δ overlay.
- `iron_condor_rules` — the only strategy positive in **every** calendar year
  (5.40 / 2.53 / 4.93 / 4.60 / 1.63 / 3.55). The robust one has no ML.

**Fix (real mechanism, broken implementation):** `wheel_strategy`,
`bull_put_spread` (widen the gate and size properly), `expiry_max_pain`,
`put_steal`, `earnings_vol_crush`, `short_squeeze_detector`,
`vol_calendar_spread`, `dealer_gamma_regime`, `tail_risk_long_put`.

**Kill:** `iron_condor_ai` (dominated 7× by the rules version),
`vix_term_structure` (return was the slippage bug), `hmm_regime` (inert — zero
trades in 2021 and 2022, $1,595 lifetime P&L), `yield_curve_regime` (44% of
lifetime P&L is one 2022 macro call), `rs_credit_spread`,
`momentum_regime_spread`, `calendar_spread_vix`, `calendar_spread`,
`broken_wing_butterfly`, `earnings_straddle`, `vol_arbitrage`,
`news_sentiment_nlp`.

**Keep, data-blocked:** `vrp_premium`, `stock_bond_vol_rotation` (needs TLT options).

## The three things that matter most

1. **Stop pricing entry and exit with the same volatility.** Eight strategies do
   this. Under Black-Scholes it makes the position a fair game by construction —
   expected P&L ≈ 0 before costs — then friction is subtracted. The variance
   risk premium, the only thing a short-premium book earns, is set to exactly
   zero. It is a deterministic bleed, not a bet gone wrong.
2. **Add a `credit ≥ 3 × round-trip friction` gate to every credit strategy.**
   The median `put_steal` trade has a maximum possible profit smaller than its
   own transaction cost.
3. **The `AI_DRIVEN` label is not describing a source of return.** Ship the two
   that work, retire the rest.
