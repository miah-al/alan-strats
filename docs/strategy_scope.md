# Strategy Scope

What each strategy is, the economic mechanism it claims to harvest, what it
actually earned on real data, and whether it is worth deploying.

> **All numbers on this page were measured on this machine** through the
> production backtest path (`app/pages/strategies/backtest_view._run_backtest`,
> replicated headless by `scripts/rank_strategies.py`) against the real
> `AlanStrats` database — real yfinance price bars, real CBOE VIX, real FRED
> macro, real Polygon option data. Nothing here is estimated or illustrative.
> Re-generate at any time with:
>
> ```
> python -m scripts.rank_strategies --markdown docs/strategy_ranking.md
> ```

---

> ### ⚠️ Numbers below are superseded — read this first (2026-08-17)
>
> Two corrections landed after this table was generated. Both change conclusions,
> not just digits.
>
> **1. `iron_condor_rules` was leveraged, not skilled.** Its `max_concurrent`
> cap was resolved from the UI and never read, so it ran up to **21 simultaneous
> condors against a documented cap of 5**. With the cap enforced its CAGR falls
> **4.33% → 2.79%**. It is no longer "the only strategy positive every year"; it
> is a small short-vol carry below the risk-free rate.
>
> **2. Every stored option IV was ~15% too low.** `db/sync.py` inverted
> Black-Scholes with calendar-day DTE over a 252 trading-day year, making T
> 1.45x too large and forcing a correspondingly smaller sigma
> (predicted 0.831, measured 0.851). Every options figure in the table below was
> computed against that surface. The clock is fixed and the surface re-synced;
> the options rows need re-measuring.
>
> **Also retracted:** the claim that strategies "lose to cash". None of them
> credit interest on idle collateral while being scored against a 5% hurdle, and
> they deploy only 0.17%-1.9% of capital. Cash-adjusted they return 5.16%-6.39%
> — above T-bills, not below. The real defect is under-deployment, not a
> negative edge.
>
> What is unchanged: **only `covered_call_ai` beats SPY buy-and-hold**, and the
> ML head adds nothing in any AI strategy tested.

## The bar every strategy has to clear

| Benchmark | CAGR% | TotRet% | MaxDD% | Sharpe |
|---|--:|--:|--:|--:|
| **SPY buy & hold** (2021-01 → 2026-06) | **15.32** | 118.08 | **−24.50** | **0.63** |
| SPY buy & hold (2024-04 → 2026-03) | 13.01 | 27.58 | −18.76 | 0.52 |
| Cash (risk-free) | ~5.00 | — | 0.00 | — |

Two honest consequences:

1. A strategy returning **less than ~5%** while taking real risk is destroying
   value — the money would do better in T-bills.
2. A strategy returning less than **15.32%** must justify itself on *risk*
   (shallower drawdown, lower correlation), not on return.

### How to read Sharpe here

Sharpe previously charged the 5% risk-free hurdle against **every calendar
day**, including days a strategy held no position. That made intermittent
strategies report absurd figures (−58, −159) that described the accounting, not
the risk. It now charges the hurdle **only on days capital was deployed**
(`risk/metrics.py`). Idle days still dilute the ratio — being out of the market
is not free — but they no longer manufacture a loss.

Read Sharpe together with **Expo%** (share of days with capital at risk). A 2.1
Sharpe at 3% exposure is a rounding error dressed as skill; a 0.8 Sharpe at 100%
exposure is a real portfolio.

---

## Measured results — all strategies that produced real numbers

Ranked by CAGR. Windows differ because the *data* differs, and they are **not**
interchangeable: a 2024–26 window is a calmer, up-only tape than 2021–26, which
contains the 2022 bear.

| # | Strategy | Type | CAGR% | MaxDD% | Sharpe | Expo% | PF | Win% | Trades | Window |
|--:|---|---|--:|--:|--:|--:|--:|--:|--:|---|
| 1 | covered_call_ai | ai | 16.78 | −17.98 | 0.81 | 99.9 | 1.61 | 72.9 | 48 | 21→26 |
| 2 | ts_momentum | rule | 12.09 | −18.76 | 0.56 | 99.9 | 9.62 | 50.0 | 2 | 21→26 |
| 3 | trend_following | rule | 9.76 | −17.02 | 0.46 | 99.9 | 2.86 | 37.5 | 16 | 21→26 |
| 4 | gex_positioning | rule | 7.32 | −13.35 | 0.27 | 99.8 | 1.59 | 64.1 | 103 | 21→26 |
| 5 | iron_condor_rules | rule | 3.99 | −8.13 | 0.21 | 57.2 | 2.06 | 81.0 | 290 | 21→26 |
| 6 | vix_term_structure | ai | 1.27 | −3.37 | −1.05 | 81.3 | 1.41 | 78.0 | 123 | 21→26 |
| 7 | yield_curve_regime | ai | 1.09 | −16.02 | −0.30 | 76.8 | 1.20 | 68.6 | 223 | 21→26 |
| 8 | ivr_credit_spread | rule | 0.86 | −1.63 | −0.16 | 22.2 | 1.83 | 79.1 | 158 | 21→26 |
| 9 | tail_risk_long_put | rule | 0.64 | −1.70 | −0.91 | 46.5 | 1.88 | 53.3 | 30 | 21→26 |
| 10 | iron_condor_ai | ai | 0.64 | −5.14 | −0.62 | 53.9 | 1.43 | 74.8 | 147 | 21→26 |
| 11 | wheel_strategy | rule | 0.41 | 0.00 | 0.95 | 0.4 | ∞ | 100.0 | 5 | 21→26 |
| 12 | fomc_event_straddle | rule | 0.38 | −1.74 | 0.04 | 6.8 | 1.58 | 29.2 | 24 | 21→26 |
| 13 | hmm_regime | ai | 0.27 | −1.51 | −1.73 | 35.5 | 1.31 | 65.1 | 63 | 21→26 |
| 14 | tail_risk_put_spread | rule | 0.23 | −0.77 | −0.21 | 7.8 | 3.66 | 50.0 | 4 | 21→26 |
| 15 | broken_wing_butterfly | rule | 0.22 | 0.00 | 2.12 | 3.2 | ∞ | 100.0 | 43 | 21→26 |
| 16 | bull_put_spread | rule | 0.17 | −1.00 | −0.22 | 5.5 | 1.78 | 69.2 | 13 | 21→26 |
| 17 | earnings_straddle | rule | 0.03 | 0.00 | 0.99 | 0.4 | ∞ | 100.0 | 2 | F 24→26 |
| 18 | calendar_spread_vix | rule | 0.00 | 0.00 | — | 0.0 | — | — | 0 | 21→26 |
| 19 | news_sentiment_nlp | ai | 0.00 | 0.00 | — | 0.0 | — | — | 0 | 21→26 |
| 20 | earnings_pin_risk | ai | −0.88 | −1.75 | −0.72 | 0.6 | 0.00 | 0.0 | 1 | F 24→26 |
| 21 | earnings_vol_crush | ai | −1.12 | −2.22 | −1.25 | 1.6 | 0.00 | 0.0 | 2 | F 24→26 |
| 22 | put_steal | ai | −1.25 | −6.25 | −8.31 | 54.7 | 0.35 | 47.7 | 235 | 21→26 |
| 23 | calendar_spread | rule | −1.27 | −7.08 | −1.16 | 1.7 | 0.27 | 31.8 | 22 | 21→26 |
| 24 | rs_credit_spread | ai | −2.06 | −11.64 | −2.90 | 24.8 | 0.34 | 53.1 | 192 | 21→26 |
| 25 | momentum_regime_spread | ai | −2.89 | −18.43 | −1.06 | 29.6 | 0.62 | 30.5 | 59 | 21→26 |
| 26 | vix_spike_fade | rule | −3.71 | −18.88 | −1.50 | 5.1 | 0.84 | 70.0 | 10 | 21→26 |

**The headline: exactly one strategy — `covered_call_ai` — beat SPY buy-and-hold
on both return and drawdown.** Everything below rank 5 returns less than cash.

### ⚠️ Four of these rows are NOT backtest results

Confirmed by code inspection on 2026-08-01 — see
`docs/reviews/2026-08-01_strategy_edge_review.md`:

| Strategy | Why its row is meaningless |
|---|---|
| `broken_wing_butterfly` | P&L is a constant × a fabricated credit; spot never enters the payoff. Its stop is mathematically unreachable, so it books 43 guaranteed wins. |
| `calendar_spread` | P&L is two constants; both legs use the same IV, so the term-structure edge it claims cannot exist in the code. |
| `wheel_strategy` | P&L is always half the credit; assignment settles at first touch instead of expiry, understating losses ~2.1×. |
| `earnings_straddle` | Never loads earnings data at all; degenerates to "VIX ≥ 40". No code path can produce a loss. |

**Do not allocate capital on these four rows.** Their credits are invented
(`entry_credit = min_credit + atr × 0.1`, commented `# proxy`), they charge no
commission or slippage, and they never mark to market — which is why their
MaxDD is 0.00 and their profit factor is ∞. This is the explanation for the
profit-factor anomaly, not a real edge.

### Statistical health warning

Several rows cannot support a conclusion regardless of how good they look:

- `ts_momentum` (2 trades), `earnings_straddle` (2), `wheel_strategy` (5),
  `tail_risk_put_spread` (4), `earnings_pin_risk` (1), `earnings_vol_crush` (2).
- Sharpe and MaxDD are **structurally meaningless** for any strategy that does
  not mark open positions to market: the equity curve is a step function of
  realised P&L, so drawdown cannot appear.

---

## Data-limited — cannot be judged yet

These are **not** broken. The feed they need does not exist on the current data
plan, so they are reported as blocked rather than silently scored zero.

| Strategy | Type | Missing input |
|---|---|---|
| dealer_gamma_regime | rule | per-strike historical Open Interest |
| expiry_max_pain | rule | per-strike historical Open Interest |
| vol_arbitrage | rule | multi-strike call+put IV chain |
| short_squeeze_detector | ai | short-interest feed + option chain |
| vol_calendar_spread | ai | weekly-expiry density |
| vrp_premium | ai | reconstructed ATM IV surface |
| stock_bond_vol_rotation | ai | ATM IV for both SPY and TLT legs |
| news_sentiment_nlp | ai | daily news-sentiment table (runs an explicit degenerate fallback with sentiment = 0 — it cannot produce signal, and must never be read as evidence of NLP alpha) |

The SPY option surface is being rebuilt from Polygon; the option-dependent rows
above will be re-measured once it completes.

---

## Economic mechanism — does an edge plausibly exist?

A strategy with no nameable mechanism is a curve fit. Grouped by what they claim
to harvest:

**Equity risk premium + timing overlay** — `trend_following`, `ts_momentum`,
`covered_call_ai`. These are ~100% long equity when invested. Their return is
mostly SPY beta; the strategy contributes only the timing/overlay decision. Judge
them on drawdown reduction, not CAGR.

**Variance risk premium (short vol)** — `iron_condor_rules`, `iron_condor_ai`,
`ivr_credit_spread`, `bull_put_spread`, `vrp_premium`, `wheel_strategy`,
`broken_wing_butterfly`, `vol_arbitrage`. Implied vol usually exceeds realized;
selling it earns a real premium, paid for by occasional large losses. Genuine
mechanism, but regime-fragile and cost-sensitive — every leg pays commission and
slippage on entry *and* exit.

**Term-structure / carry** — `vix_term_structure`, `calendar_spread`,
`calendar_spread_vix`, `vol_calendar_spread`. Contango carry is real; the debit
legs are usually the drag.

**Dealer positioning / flow** — `gex_positioning`, `dealer_gamma_regime`,
`expiry_max_pain`. Real documented effects, but they need Open Interest data the
current plan does not serve.

**Event premium** — `fomc_event_straddle`, `earnings_straddle`,
`earnings_vol_crush`, `earnings_pin_risk`. Event vol is systematically
overpriced; capturing it needs clean earnings timing and tight fills.

**Insurance (negative-EV by design)** — `tail_risk_long_put`,
`tail_risk_put_spread`. These are *supposed* to bleed slowly and pay off in a
crash. Judge them on carry cost versus crash convexity — never on CAGR.

**Cross-sectional / macro** — `rs_credit_spread`, `yield_curve_regime`,
`momentum_regime_spread`, `stock_bond_vol_rotation`, `put_steal`. The weakest
group empirically; several lose money with enough trades to be statistically
meaningful, which points at absent edge rather than bad luck.

---

## Known systemic caveats

These apply across strategies and bound how much any single number should be
trusted:

- **Exit-price realization.** Short-vol backtests realize stop-outs at the
  end-of-day close rather than the trigger price — pessimistic on gap days,
  optimistic on intraday spikes that revert. Affects every short-vol strategy.
- **Model staleness.** `saved_models/*.pkl` were pickled with scikit-learn
  1.8.0; the environment now runs 1.9.0 and sklearn warns this "might lead to
  breaking code or invalid results". AI-strategy outputs should be treated as
  provisional until the models are retrained.
- **Window sensitivity.** 2024–26 is a calm, rising tape. Strategies measured
  only on that window are flattered relative to those that also absorbed 2022.
- **Costs.** Commission and slippage are applied per leg
  (`DEFAULT_COMMISSION_PER_LEG`, `DEFAULT_SLIPPAGE_PER_LEG` in
  `backtest/engine.py`). Multi-leg structures pay 2× legs round trip, which is
  what kills several otherwise-positive spreads.

---

## Verdict framework

| Verdict | Meaning |
|---|---|
| **KEEP** | Real mechanism, survives costs, earns its risk. Deployable. |
| **FIX** | Real mechanism, implementation or parameters are wrong. Specific change identified. |
| **KILL** | No nameable edge, or a statistically meaningful loss. Retire it. |
| **DATA** | Cannot be judged until the missing feed exists. |

Per-strategy verdicts are produced by the deep review pass and recorded in
`docs/reviews/`. Only strategies marked **KEEP** should ever see real capital,
and only at a size consistent with their measured drawdown.
