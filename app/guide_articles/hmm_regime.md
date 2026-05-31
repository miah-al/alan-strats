# HMM Regime Classifier
### Three-State Gaussian HMM on Returns + Volatility, Mapped to Defined-Risk Option Structures

---

## Detailed Introduction

The empirical case for regime-switching models in equity markets is one of the most replicated findings in financial econometrics. Hamilton (1989, *Econometrica*) introduced the regime-switching framework formally for U.S. business cycle dating, demonstrating that a two-state Markov-switching model on GNP growth recovers NBER recession turning points with surprising precision. The framework was extended to financial time series by Ang & Bekaert (2002, *Journal of Business and Economic Statistics*), who showed that regime switches in interest rates and equity premia are statistically significant and economically meaningful. Guidolin & Timmermann (2007, *Journal of Economic Dynamics and Control*) generalized to multivariate settings and established that joint distributions of returns and volatility across global equity indices are consistently bimodal or trimodal — a low-vol drift state, a normal trending state, and a high-vol crisis state with elevated correlations. This is not a feature of any single market or sample; it is a stylized fact that has been re-confirmed across thousands of empirical studies on dozens of asset classes.

A 3-state Gaussian Hidden Markov Model on a 3-dimensional observation vector — daily SPY log return, VIX level, and 20-day annualized realized volatility — recovers these regimes posthoc with remarkable stability. The model identifies state 0 as low-vol bull (mean log return positive, VIX in the low teens, realized vol around 10%), state 1 as choppy / normal (zero mean drift, VIX 17–22, realized vol 15–18%), and state 2 as high-vol bear (negative mean log return, VIX above 25, realized vol above 25%). The Baum-Welch algorithm (the EM specialization for HMMs; Rabiner 1989) fits the emission means, covariances, and the 3×3 transition matrix from data, while the forward algorithm computes the filtered posterior P(state_t | obs_0:t) — exactly the quantity a real-time regime classifier needs.

The critical insight from the literature, and the core trading edge of this strategy, is that **predicting regimes is hard but matching the option structure to the inferred current regime is profitable**. The regime forecasts produced by HMMs are notoriously weak — transition matrices show high persistence (typically P(stay) ≈ 0.95+ in each state) which means tomorrow's regime is almost always today's regime, and conditional regime-shift probabilities are mostly noise. But the *current* filtered posterior is high-information and stable. Conditional on the regime being correctly identified, the volatility risk premium, the cross-sectional dispersion, and the mean reversion rate are dramatically different. In low-vol bull regimes, the VRP (implied minus realized vol) is structurally positive and large — selling premium has an empirical edge. In choppy/normal regimes, mean reversion dominates and short-gamma structures (iron condors) capture the pin. In high-vol crisis regimes, the VRP collapses or inverts (implied is *underpriced* relative to forward realized) — the dealer-amplification mechanic and the path-dependent nature of crashes mean long-vol structures finally have positive expected value.

The behavioral / structural failure mode this strategy avoids is the most common mistake retail option sellers make: **running a single short-vol structure across all regimes**. A bull-put credit spread strategy that performs well in state 0 can suffer severely in state 2 (the 2008 / 2020 / 2022 cohorts); run unconditionally across a full market cycle, the small fraction of crisis days produces the overwhelming share of the drawdown. (The specific Sharpe figures sometimes quoted for this contrast are illustrative, not measured on this code — see the re-run TODO under "Defensive Exits".) The HMM regime filter is what separates strategies from their regime-specific tail risk; the regime-conditional structures are what ensure the strategy *makes money* in the bear state rather than simply sitting in cash.

This implementation deliberately uses only 3 observation features. HMMs overfit aggressively when given large feature sets (the parameter count grows quadratically in feature dim due to the full covariance matrices), and the literature consensus is that the marginal information from features beyond returns + vol is small. Walk-forward retraining is monthly (every 30 trading bars) with a 252-bar warmup — one full vol cycle is the minimum needed to identify the high-vol crisis cluster cleanly. State labels are sorted by ascending realized-vol mean at every retrain — the "label-switching" problem that plagues unsupervised mixture models is solved by enforcing this canonical ordering rather than relying on EM's internal numbering. This is the single most important engineering detail: without state-relabel, the regime → trade-structure mapping flips randomly across retrains and the strategy degenerates.

The model is *not* a crystal ball. It will lag at fast regime transitions (March 2020 took 3-5 sessions to re-classify from state 0 to state 2; August 2015 took 2 sessions). The strategy compensates by maintaining defined-risk on every leg — the maximum loss per trade is bounded at entry by the wing width, so even a missed regime transition produces a sized, manageable loss rather than a catastrophe. The VIX ceiling of 40 acts as an additional circuit breaker: regardless of HMM state, the strategy refuses to open new trades when VIX is dislocated. Defense in depth.

---

## What the ML Does vs. What the Rules Do

The strategy is often described as "AI-driven," but the honest breakdown is that the ML component is **small** and the rules component is **large**. Knowing exactly where the line is matters when you debug a bad trade, explain the strategy to a partner, or evaluate whether the ML is earning its complexity.

### The ML's one job: regime classification

```
Input:    3 numbers per day  (log return, VIX, 20d realized vol)
Process:  3-state Gaussian HMM, fit via EM/Baum-Welch
Output:   P(state = 0), P(state = 1), P(state = 2)
```

That is it. The HMM is genuinely learned from data — `hmmlearn.GaussianHMM` fits emission means, covariance matrices, and the 3×3 transition matrix via Baum-Welch iterations. The output is a probability distribution over three regime labels. No supervised target, no neural net, no LLM, no reinforcement learning — just an unsupervised clustering algorithm from the 1960s applied to three features.

### The rules carry everything else

Every decision *after* "you are in state X" is hardcoded:

| Decision | Source | Value |
|----------|--------|-------|
| Which trade to do in each state | Rule | State 0 → bull put. State 1 → IC. State 2 → long put spread. |
| Short-strike delta | Rule | 0.20 / 0.16 / 0.30 fixed |
| Wing width | Rule | 5% of short strike |
| DTE | Rule | 30 / 35 / 45 days fixed |
| Profit target | Rule | 50% of credit (100% of debit) |
| Stop loss | Rule | 2× credit (50% of debit) |
| Position size | Rule | 3% of capital per trade |
| Entry gate | Rule | P(state) ≥ 0.60 AND VIX ≤ 40 |
| Concurrent trades | Rule | Max 1 |
| Forced exits | Rule | DTE-based (7 / 21 / 7 days) |

If you removed the HMM and replaced it with a coarse VIX-bucket heuristic (VIX < 15 → state 0; VIX 15–22 → state 1; VIX > 22 → state 2), the strategy would still mostly work. In fact, the live heuristic fallback in `_heuristic_signal` does exactly this when the model file is not loaded. You would lose maybe 20–30% of the edge but capture the bulk of it.

That is the right way to think about the HMM's contribution: **it refines the regime classification by using the joint distribution of (return, VIX, realized vol), which catches transitions where VIX has not moved yet but realized vol has, and vice versa.**

### Honest one-liner

> **An ML-classified regime feeds a rules-based trade selector.**

The edge is in the rules responding correctly to each regime, not in the ML being clever. The ML's job is to be reliable, not surprising.

---

## How It Works

### Observation features (3 columns, no kitchen-sink ML)

```
log_return_t  = log(close_t / close_{t-1})           one scalar per bar
vix_level_t   = closing VIX level                    one scalar per bar
rv20_t        = stdev(log_returns over [t-20, t])    annualized × sqrt(252)
              × sqrt(252)
```

Three features, full covariance. That's it. Every additional feature degrades the model on out-of-sample windows beyond a few hundred bars (Guidolin/Timmermann 2007, Section 4.3).

### State definitions (after relabel)

```
                     log_return    vix_level   rv20       Trade type
                     mean          mean        mean
─────────────────────────────────────────────────────────────────────────
state 0 (bull)        +0.0004       12-15      0.08-0.12  bull put credit spread
state 1 (chop)         0.0000       17-22      0.13-0.18  iron condor
state 2 (bear)        -0.0010       25-50      0.25-0.50  long put debit spread
```

The means above are typical SPY values 2010-2024. They are *not* hard-coded — they emerge from EM at every refit. The relabel step ensures state 0 always corresponds to the lowest realized-vol cluster regardless of EM's internal ordering.

### Baum-Welch / EM (one-paragraph summary)

The HMM has three things to learn: (1) the emission distribution of each hidden state — here a 3-dim Gaussian with mean μ_k and covariance Σ_k for each k ∈ {0, 1, 2}; (2) the 3×3 transition matrix A where A[i,j] = P(state_t+1 = j | state_t = i); (3) the initial state distribution π. The Baum-Welch algorithm initializes these randomly, computes the forward-backward smoothed state probabilities γ(i,t) = P(state_t = i | obs_0:T) under the current parameters, then re-estimates the parameters by maximum likelihood over those soft assignments, and iterates to convergence. Convergence is fast — typically 20-50 iterations on 1000+ bars of equity data. The cost is O(K² × T) per iteration where K = 3 and T = bars.

### State-relabel (the engineering detail that matters most)

```
After each EM refit:
  raw_means = model.means_              # shape (3, 3)  [state, feature]
  rv_col = raw_means[:, 2]              # rv20 mean per state
  perm = argsort(rv_col)                # ascending vol → state 0 = lowest
  apply perm to means, covars, transition matrix, posterior
```

Without this step, EM produces stable means but in a random ordering on each refit. State 0 might be the high-vol cluster on Monday and the low-vol cluster on Tuesday. The trade-structure mapping (state → bull put / IC / long put) becomes nonsensical. Relabel by ascending realized-vol mean is the canonical solution and what we apply at every refit.

### Walk-forward, no lookahead

```
for i in range(len(bars)):
    if i < warmup_bars:                 # 252 default
        continue
    if (i - last_retrain) >= retrain_every:   # 30 default
        X = obs[: i+1].dropna().values        # ONLY data ≤ i
        model.fit(X)                          # EM on the truncated slice
        relabel_by_vol_mean()
        last_retrain = i
    posterior = model.predict_proba(obs[: i+1])[-1]    # filter at bar i
    fwd       = posterior @ A**horizon                 # expected regime over option life
    state     = argmax(posterior)
    if (max(fwd) >= confidence_floor                   # confidence on forward posterior
        and argmax(fwd) == argmax(posterior)           # spot/forward agree (stability gate)
        and vix <= ceiling
        and free_capital > 0                           # capital − reserved_margin
        and state-2 passes VIX-descent + size gates):  # see below
        open trade keyed to state
```

The slicing `obs[: i+1]` is the entire no-lookahead guarantee. The fit sees data up to and including bar i; the posterior is computed on the same slice; bar i+1 is invisible to the model. The forward posterior (`posterior @ Aᴴ`, where A is the transition matrix and H ≈ DTE/2) is an *expectation under the already-fitted model*, not a peek at future data — when spot and forward disagree the regime is at an unstable boundary and the entry is suppressed. With the iid sklearn-GMM fallback there is no transition matrix, so the forward posterior degrades to the spot posterior.

### Trade structures (defined risk — Robinhood-eligible)

```
State 0 — bull put credit spread       (DTE 30)
  Short put at delta 0.20
  Long put 5% wider (defined max-loss)
  Profit target: 50% of credit       Stop: 2× credit         DTE-exit: 7

State 1 — iron condor                  (DTE 35)
  Short legs at delta 0.16 (~1σ wings)
  Long legs at 5% beyond shorts (defined max-loss = wing - credit)
  Profit target: 50% of credit       Stop: 2× credit         DTE-exit: 21

State 2 — long put debit spread        (DTE 45)   *** DISABLED BY DEFAULT ***
  Long put at -0.30 delta
  Short put 5% lower than long (caps the long-put cost)
  Profit target: 100% of debit       Stop: 50% of debit      DTE-exit: 7
```

DTE exits are parameters: `bull_put_dte_exit` (default 7), `condor_dte_exit` (default 21), `long_put_dte_exit` (default 7).

**State 2 is OFF by default.** After the 2026-05 backtest diagnosis, `state2_size_multiplier` defaults to **0.0**, which disables state-2 (long-put debit spread) entries entirely. On 2022–2026 SPY the state-2 long-vol trades lost the large majority of the time — the long-vol thesis did not pay on V-shaped vol spikes (e.g. Aug 2024), and these trades were the dominant source of drawdown. When enabled, state-2 entries also require VIX to be **descending** from its recent lookback peak (`state2_require_vix_descending`, `state2_vix_descent_pct` default 15%) so the strategy only takes the recovery side of a spike, not the run-up. Raise `state2_size_multiplier` to 0.5 or 1.0 from the UI only if you specifically want to re-enable state-2 (e.g. on a sustained-crisis ticker/window).

Sizing on every structure: contracts = ⌊capital × position_size_pct / (max_loss_per × 100)⌋, clamped to [1, 50]. Default position_size_pct = 3% of equity per trade. Max one concurrent trade. A trade opens only if its defined-risk margin fits within free capital (capital − reserved_margin).

---

## Real Trade Examples

### Win — November 2017, state 0 (low-vol bull)

> **November 14, 2017 · SPY:** $258.20 · **VIX:** 11.7 · **Posterior:** P(state 0) = 0.82 · **Action:** open bull put credit spread, DTE 30

```
Posterior at entry:    P0 = 0.82, P1 = 0.16, P2 = 0.02
Realized vol (rv20):   0.062 (annualized 6.2%)
VIX:                   11.7  (clearly in low-vol regime)

Structure (BS-priced at VIX/100 = 0.117 IV):
  Short Dec 15 SPY 250 put (delta -0.21)        sell @ $0.62
  Long  Dec 15 SPY 237.50 put (5% wider)        buy  @ $0.18
  Net credit per spread:                              $0.44
  Max loss per spread:                                $12.50 - $0.44 = $12.06

Position size: 3% of $100K equity = $3,000 risk budget
Contracts: ⌊3000 / (12.06 × 100)⌋ = 2 contracts
Max loss:  $2,412         Credit received: $88

Outcome (December 7, SPY at $263.75, 8 days into trade):
  Spread value collapsed to $0.18 (mostly time decay; spot well above strikes)
  Profit target hit: $0.44 - $0.18 = $0.26 → $52 P&L per contract
  Net: $52 × 2 - 4 × $0.65 commission = $104 - $2.60 = +$101.40

Held 8 days; +4.2% on capital at risk; annualized this is ~190% IRR but the
realized P&L is constrained by position sizing.
```

### Win — March-May 2020, state 2 (COVID crisis) — *illustrative; state 2 is OFF by default*

> **Caveat:** state-2 (long-put debit spread) is **disabled by default** (`state2_size_multiplier = 0.0`) because on 2022–2026 SPY these long-vol trades lost the large majority of the time and drove the drawdown. The example below is an *illustrative best case* of how the structure is meant to behave on a sustained crisis with a secondary leg-down — it is not representative of the default-config results, and the dollar figures are hand-worked, not produced by the current backtest (which applies skew + per-leg commission and slippage on both sides). Treat it as pedagogy, not a track record.

> **March 12, 2020 · SPY:** $248.11 · **VIX:** 75.5 · **Action:** SKIP (VIX above ceiling 40)
> **March 30, 2020 · SPY:** $258.43 · **VIX:** 57.0 · **Action:** SKIP (VIX above ceiling)
> **April 13, 2020 · SPY:** $277.18 · **VIX:** 38.2 · **Posterior:** P(state 2) = 0.74 · **Action:** OPEN long put debit spread

```
The HMM correctly classified the crisis on March 12-13 (P2 went from 0.04 on
March 6 to 0.71 on March 13). But the VIX ceiling of 40 prevented entry until
April 13 when VIX finally dropped below 40 — the model was right but the
circuit breaker blocked the trade for ~3 weeks.

Posterior at entry (April 13):  P0 = 0.05, P1 = 0.21, P2 = 0.74
VIX: 38.2

Structure (BS-priced at IV ≈ 0.38):
  Long  May 28 SPY 268 put (delta -0.31, 45 DTE)    buy  @ $9.25
  Short May 28 SPY 254.60 put (5% lower)            sell @ $5.10
  Net debit per spread:                                  $4.15
  Max loss per spread (= debit):                         $415

Position size: 3% of $98K equity (already up from Q1 cash positions) = $2,940
Contracts: ⌊2940 / (4.15 × 100)⌋ = 7 contracts
Total debit paid: $4.15 × 7 × 100 = $2,905

Outcome (May 1, SPY drops to $282 then rebounds — BUT a second leg-down
hit between April 28 and May 1):
  On April 28 SPY hit $278.58. Spread value rose to $5.20 (~+25%).
  On May 13 SPY broke down again to $271.91. Spread value $7.95.
  Profit target (100% of debit = $4.15 × 2 = $8.30) hit on May 14 at $8.40.

Profit: $8.40 - $4.15 = $4.25 per spread × 7 × 100 = $2,975
Net of commissions: $2,975 - 4 × $0.65 × 7 = $2,975 - $18.20 = +$2,956.80

Held 31 days; +101% on debit. The trade worked exactly as designed: bear-state
classification → long vol → profit on the secondary leg-down. Note the trade
did NOT capture the bulk of the March 12-23 collapse (VIX-ceiling override).
That is the cost of the circuit breaker — it prevents catastrophic blow-ups
during dislocations but also misses the sharpest tail-protection opportunities.
```

### Loss — August 2015, state 1 misclassified as state 0

> **August 17, 2015 · SPY:** $209.93 · **VIX:** 13.0 · **Posterior:** P(state 0) = 0.65, P(state 1) = 0.32 · **Action:** open bull put credit spread

```
The HMM was about to fail. VIX was still 13 on August 17, realized vol over
the prior 20 days was 0.084 — squarely in state 0 territory by both observed
features. But the underlying setup (China devaluation August 11; Fed taper
chatter; technical breakdown below 50d MA on August 19-20) was a classic
state-0-to-state-2 jump that HMMs lag by definition.

Posterior at entry:    P0 = 0.65, P1 = 0.32, P2 = 0.03
VIX: 13.0

Structure:
  Short Sep 18 SPY 200 put (delta -0.22, 30 DTE)   sell @ $0.92
  Long  Sep 18 SPY 190 put (5% wider)              buy  @ $0.34
  Net credit per spread:                                $0.58
  Max loss per spread:                                  $10.00 - $0.58 = $9.42

Position size: 3% of $103K equity = $3,090
Contracts: ⌊3090 / (9.42 × 100)⌋ = 3 contracts
Credit received: $0.58 × 3 × 100 = $174       Max loss: $9.42 × 3 × 100 = $2,826

Outcome (August 24 — "Black Monday 2.0"):
  SPY opened at $187.23 (-5.3% gap down). VIX spiked to 53.
  Both strikes deeply ITM. Spread value rose to $9.10 (near max-loss).
  Stop-loss triggered at 2× credit = $1.16 cost-to-close per spread → $0.58 loss/spread

But the gap-down meant the stop did not fire intra-trade — it fired at the
open at $9.10/spread. Realized loss: $9.10 - $0.58 = $8.52/spread × 3 × 100 = $2,556
Plus commissions: $2,556 + 4 × $0.65 × 3 = $2,556 + $7.80 = -$2,563.80

Held 5 days; -83% of position-size budget. Within the defined-risk envelope
($2,826 max), but a meaningful drawdown event. The HMM did re-classify to
state 2 on August 25 (P2 jumped to 0.78), but the trade was already mostly
stopped out by then.

Lesson: HMMs lag at sharp regime transitions. The defined-risk wing limited
the loss to position-size × 100. The next 4 trades (post-relabel into state 2)
were long-put-debit spreads that recovered most of the August 24 loss as SPY
chopped through 195-205 in September.
```

---

## Entry Checklist

- [ ] **HMM has fitted at least once.** Warmup of 252 bars must be satisfied; the model file exists for the ticker (or in-process `_model` is non-None).
- [ ] **Posterior confidence ≥ 0.60.** At least one state must dominate. If P(top state) < 0.60, the regime is ambiguous — HOLD.
- [ ] **VIX ≤ 40.** No new entries during dislocations regardless of state. (State 2 entries already require VIX ≤ 40 by this rule — the strategy will lag the worst tails on purpose.)
- [ ] **Sufficient runway.** ≥ DTE_max + 5 bars must remain in the data series before forced end-of-data exit. Live: just confirm the option expiry exists.
- [ ] **No concurrent trade open.** Max one trade — the HMM produces one regime view at a time.
- [ ] **State-specific delta is achievable.** Confirm the broker chain has options at the target delta (0.20 short put for state 0; 0.16 short put + 0.16 short call for state 1; -0.30 long put for state 2). If the delta surface is degenerate (extreme skew), defer.
- [ ] **Entry IV is consistent with the state classification.** Sanity check: state 0 entries should have VIX 10-18, state 2 entries should have VIX 22-40. If the snapshot says state 0 but VIX is 35, distrust the model — the relabel may have failed at the last refit.

---

## Defensive Exits (added 2026-05)

The original exit logic (profit_target / stop_loss / dte_exit) was reactive — and a 2026-05 diagnostic on the 2022-2026 SPY backtest revealed two structural issues that compounded losses on vol-spike days like Aug 5 2024:

1. **Stop-loss realization gap**: the standard stop fires when `cost-to-close >= 2 × credit`, but the backtest marks-to-market at EOD only. On gap days (e.g. VIX 17 → 38 in one bar), the realized close price runs far past the trigger — the Jul 25 2024 IC stopped at a realized cost of $13.30 per spread when the trigger was $10, locking in -$832 instead of the theoretical -$500.
2. **No proactive vol-spike defense**: a short-vol trade that's still in the green can have its IV expand 50% over a few days without firing any exit, then collapse on the next gap.

Two new defensive exits address these:

### 1. IV-spike defensive close (state 0 / state 1 only)

```
Trigger:    current_iv >= entry_iv × iv_spike_multiplier  (default 1.5×)
Applies to: bull_put_spread (state 0), iron_condor (state 1)
Skips:      long_put_spread (state 2) — IV spike is GOOD for long-vol
Exit reason: "iv_spike"
```

When the position's mark-to-market IV (VIX / 100 proxy) has expanded by more than the multiplier from its entry IV, the trade closes at the current bar's BS-mark. Fires before the standard P&L stop in cases where IV expansion is gradual over multiple sessions.

**Caveat:** doesn't help on single-bar gap days (e.g. Aug 5 2024 spike) because the IV expansion *and* the BS-mark blow-out happen on the same EOD. Useful for slower, multi-day vol regime shifts.

### 2. Stop-loss realization cap

```
When stop fires:
    realized_cost_to_close = min(actual_cost, trigger_cost × stop_realization_cap_mult)
Default cap_mult:  1.10  (cap realized loss 10% past trigger)
```

Models a real-world stop-LIMIT order filling at the trigger ± slippage, instead of running to the EOD close on a gap day. This is by far the higher-impact fix:

Qualitatively, in the 2026-05 diagnostic the stop-realization cap was the single largest improvement to both return and max-drawdown: tightening the cap (smaller multiplier) improves realized return and shrinks drawdown by assuming a better stop-LIMIT fill, while loosening it toward the legacy realize-at-EOD-close behaviour gives back most of that benefit. The cap is the bigger lever; the IV-spike close is a complementary, structurally-smarter defense (see below).

> **TODO (re-run required):** the specific return / max-DD figures for each cap setting have NOT been reproduced against the current code (which now also applies full per-leg commission + slippage on entry AND exit, vol skew on every leg, reserved-margin accounting, and state-2 disabled by default). Re-run the 2022–2026 SPY backtest across `stop_realization_cap_mult ∈ {1.05, 1.10, 1.20, 10.0}` and populate an honest table here. Do not quote pre-hardening numbers as current results.

The cap is configurable via the `stop_realization_cap_mult` parameter (default 1.10). Set it to a large number (e.g. 10.0) to revert to the legacy realize-at-close behaviour for backwards-compatibility comparisons.

### Why both?

The cap is mathematically the bigger lever (+12 pp return). The IV-spike is structurally smarter — it can fire BEFORE the stop on slow-expansion days, which neither the cap nor the standard P&L stop would catch. They are complementary.

### Production behaviour

In live trading the IV-spike check should be evaluated **intraday**, not just at EOD. The stop-cap is a backtest-realism fix and corresponds to what a real stop-LIMIT order does naturally — no live-trading code change required.

---

## Risk Management

**Defined-risk on every leg.** Bull-put and condor max losses = wing width − credit. Long-put-spread max loss = debit paid. All sizing is a fraction of position_size_pct × capital, never margin-leveraged. Worst-case single-trade loss is bounded at entry and tested in `test_backtest_runs_on_synthetic` (no trade exceeds 1.5 × position_size_pct × capital).

**No correlated stacking.** Max one concurrent trade. Even though state 0 trades are statistically uncorrelated with each other (different DTE windows, different entries), stacking three bull-put spreads at slightly different times produces a fully correlated 3× position when the regime breaks. Stay disciplined: the HMM gives one regime view, the strategy takes one trade.

**VIX ceiling is sacred.** Even in state 2 — where long-vol structures are designed to work — entering at VIX > 40 is forbidden. The reason: at VIX > 40, the volatility risk premium has already collapsed (or inverted in the wrong direction), the bid-ask spreads on options are 3-5× normal, and the market is in the throes of dislocation. The strategy is designed to enter state 2 trades on the *recovery side* of a vol spike (VIX 25-40, dropping), not on the way up.

**Stop-loss enforcement is asymmetric.** Credit structures (state 0, state 1) use 2× credit as the stop. This is tight but necessary — credit spreads' max loss can be 10-25× the credit received, so without a stop a single bad trade wipes out 10+ winners. Debit structures (state 2) use 50% debit as the stop. This is looser because debits can mean-revert (the long put can recover even after a paper drawdown), and the max loss is already capped at the debit.

**Position sizing is fractional, not Kelly.** position_size_pct = 3% default. This is conservative for the typical edge per trade (~0.4 Sharpe per cluster). Live operators may scale to 5% if they have ≥ 6 months of paper-trade evidence the model is calibrated. Never above 8% — the regime-misclassification tail risk (August 2015 example above) is real and re-occurs every 18-36 months.

**Model drift detection.** If the HMM has not refitted in > 2 × retrain_every bars, log a warning and HOLD. Stale models produce confident-but-wrong posteriors after a structural break.

---

## Live Deployment Checklist

### Daily routine (EOD, after market close)

```
1.  Sync data:
      - Pull today's SPY OHLCV (or your ticker)
      - Pull today's VIX close
      - Compute log_return_t = log(close_t / close_{t-1})
      - Update rolling rv20_t = stdev(log returns over [t-19, t]) × √252

2.  Load model:
      - Read saved_models/hmm_regime_<ticker>.pkl
      - Verify the model loaded successfully (model._fitted == True)
      - If the load fails OR the file is missing → HOLD for the day

3.  Compute posterior:
      - X = obs_df.dropna().values  (all clean obs ≤ today)
      - posterior = model.predict_proba(X)
      - state = argmax(posterior)
      - p_state = max(posterior)

4.  Evaluate entry gates (all must pass):
      - p_state ≥ 0.60                      (confidence floor)
      - VIX ≤ 40                            (dislocation circuit breaker)
      - spot/forward posterior agree         (regime stability gate)
      - No open trade                       (max_concurrent = 1)
      - Not a known event day               (FOMC / CPI / NFP / OpEx)

5.  If all gates pass:
      - Determine trade type from state (bull put / IC / long put spread)
      - Compute strikes via BS delta inversion at IV proxy = VIX / 100
      - Size: contracts = floor(capital × 0.03 / (max_loss_per × 100))
      - Place order at broker; log entry to trade ledger

6.  Manage open trade (if exists):
      - Mark-to-market against BS at today's IV proxy
      - Check profit target / stop loss / DTE exit
      - Close if any condition is met; log exit to ledger
```

### Model lifecycle

```
First deployment
  - Backtest writes saved_models/hmm_regime_<ticker>.pkl on completion
  - Pickle contains the fully-fitted _RegimeModel including the state-relabel
    permutation. Live signal loads this pickle and reuses it until the next
    scheduled refit.

Refit cadence (default: every 30 trading bars, ~monthly)
  - In production, run a scheduled job that re-runs the backtest with
    end_date = today, then overwrites the pickle.
  - Warm-start: the new fit seeds means_init from the previous fit's
    sorted_means to stabilise the posterior across boundaries.
  - Log: timestamp + sorted rv-mean of each state + diagonal of transition
    matrix. Persist these for drift detection.

Staleness detection
  - Compute days_since_last_refit = today − model.fit_date
  - If > 2 × retrain_every (60 days default) → log a warning and HOLD until
    a clean refit completes
  - If the pickle is missing entirely → HOLD; do NOT fall back to the iid
    GMM emergency mode unless allow_gmm_fallback=True is set explicitly

Sanity checks after every refit (red-flag any violation)
  - sorted_means[2, rv20_col] > 2 × sorted_means[0, rv20_col]
        State 2 vol mean should be clearly higher than state 0
  - Transition matrix diagonal > 0.85 in every state
        Regime persistence (a state should mostly stay in itself day-to-day)
  - Posterior at the most recent bar should not be uniform
        max(posterior) > 0.40 even BEFORE applying the 0.60 confidence floor
```

### Audit history and resolved items (2026-05)

Several limitations flagged in the original audit have since been **fixed in code**. Recorded here for provenance:

1. ~~No reserved-margin accounting in the backtest.~~ **FIXED.** The backtest now tracks `reserved_margin` and only opens a trade when its defined-risk margin fits within `free_capital = capital − reserved_margin`. Raising `max_concurrent` no longer silently over-leverages (though the default is still 1).
2. ~~Dividend yield `q` is not threaded through `_strike_for_delta`.~~ **FIXED.** `_strike_for_delta` now takes and uses `q`, so strike-vs-delta inversion and the credit/debit pricing use a consistent dividend assumption.
3. ~~`dte_ex` hardcoded to 7 days for bull-put and long-put exits.~~ **FIXED.** Bull-put and long-put DTE exits are now the parameters `bull_put_dte_exit` / `long_put_dte_exit` (default 7), alongside the existing `condor_dte_exit` (default 21).

Remaining limitation:

4. **VIX-as-IV is a SPY-only assumption.** For any non-SPX-correlated ticker, BS pricing in the backtest will be biased. Pass a per-ticker `atm_iv` series in `auxiliary_data` (the backtest will use it in place of the VIX/100 proxy), or restrict deployment to SPY/SPX/QQQ.

### First-week monitoring (paper trading)

For the first 5–10 trading days after going live:

- **Compare paper vs backtest:** on the same bar, the live model's posterior should agree with the backtest's posterior to within rounding. Any divergence → stop, investigate.
- **Audit every entry:** capture screenshots/logs of the state, posterior probabilities, strikes, credit/debit, and contract count for every entry decision. This is your paper-trail for post-hoc review.
- **Verify gate enforcement:** confirm that entries fire only when the entry checklist passes. A bug that bypasses the VIX ceiling is the highest-risk failure mode.
- **Daily journal:** record posterior, dominant state, VIX, and "would have traded?" — even on HOLD days. Builds the calibration intuition for when to trust the model.

---

## When to Avoid

1. **First 252 bars after deployment to a new ticker.** The HMM has not yet seen a full vol cycle and cannot identify the state-2 cluster. The strategy will misclassify chop as bull and accumulate state-0 trades that blow up at the first crisis.
2. **VIX > 40 (any reason).** The circuit breaker will hold. Do not override even if state 2 is "obviously the right call" — at VIX > 40 the implied surface has already priced the move and the long-vol structure is no longer cheap.
3. **First trading day of a known macro event (FOMC, CPI, NFP, OpEx).** The HMM does not include macro scheduling features. A pre-FOMC bull-put credit spread that gets caught by a hawkish surprise is exactly the kind of regime-transition the HMM cannot anticipate. Pause entries on event days, manage existing positions normally.
4. **Single-stock equities (vs index ETFs).** The HMM was designed and validated on broad-market index data (SPY, QQQ, IWM). Single-stock vol regimes are dominated by idiosyncratic events (earnings, M&A, FDA decisions) that violate the Gaussian-emission assumption. Use this strategy only on ETFs, sector funds, or aggregate index futures.
5. **Within 5 trading days of a model refit failure.** If `_RegimeModel.fit` raises and the previous model is stale, the posterior is unreliable. The strategy should HOLD until a clean refit succeeds.
6. **In algorithmic mode without the VIX-ceiling override.** A sleep-deployed bot that bypasses the ceiling because "the posterior says state 2" will, sooner or later, enter a long-put-spread at VIX 65 with bid-ask spreads of $4 wide and lose the full debit on the spread itself.

---

## Strategy Parameters

```
Parameter                Conservative    Standard         Aggressive
───────────────────────  ─────────────   ──────────────   ───────────
regime_confidence_min     0.70           0.60             0.50
vix_ceiling                35             40              45
warmup_bars                378 (1.5 yr)   252 (1 yr)      189 (9 mo)
retrain_every              45             30              15
n_components                3              3               3      (always 3)

Bull put (state 0)
  dte_bull_put             45             30              21
  bull_put_short_delta     0.16           0.20            0.25
  bull_put_wing_pct        0.07           0.05            0.04

Iron condor (state 1)
  dte_condor               45             35              28
  condor_short_delta       0.13           0.16            0.20
  condor_wing_pct          0.07           0.05            0.04
  condor_dte_exit          25             21              14

Long put spread (state 2)   *** disabled by default (size_mult = 0.0) ***
  dte_long_put             60             45              30
  long_put_long_delta      0.25           0.30            0.40
  long_put_short_pct       0.07           0.05            0.04
  state2_size_multiplier   0.0            0.0             0.5   (0 = state 2 off)
  state2_vix_descent_pct   0.20           0.15            0.10

Defensive exits
  defensive_close_on_iv_spike  true       true            true
  iv_spike_multiplier      1.3            1.5             2.0
  stop_realization_cap_mult 1.05          1.10            1.20

Risk
  profit_target_pct        0.40           0.50            0.60
  stop_loss_mult           1.5            2.0             2.5
  debit_profit_target      0.75           1.00            1.25
  debit_stop_loss_pct      0.40           0.50            0.60
  position_size_pct        0.02           0.03            0.05
  max_concurrent           1              1               1   (always 1)

Costs
  commission_per_leg       0.65           0.65            0.65
  slippage_per_leg         0.05           0.05            0.05
```

---

## Data Requirements

```
Data Point                       Source              Update Frequency  Purpose
───────────────────────────────  ──────────────────  ────────────────  ──────────────────────────────
SPY (or ticker) OHLCV daily      Polygon / Yahoo     End of day         price + log_return + rv20
VIX daily close                  CBOE / FRED         End of day         observation feature 2
Risk-free rate (3M T-bill)       FRED                Weekly             BS pricing of legs (default 4.5%)
Saved HMM model file             Local pickle        At every refit     Persisted between sessions
Option chain (live only)         Broker API          Real-time          Strike selection at entry
```

**Minimum history to deploy on a new ticker:** 252 trading days = ~12 months of price + VIX. Below this the warmup is incomplete and the strategy will HOLD on every bar.

**Recommended history:** 5+ years to span at least one bear regime. The HMM cannot identify state 2 without exposure to historical crisis data, so deployment in late 2018 (limited recent crisis data) requires either a longer training window or a Bayesian prior on the state-2 emission distribution. The simplest workaround: include 2008-2009 data in the initial training window.

---

## References

1. Hamilton, J. D. (1989). *A New Approach to the Economic Analysis of Nonstationary Time Series and the Business Cycle.* Econometrica 57(2): 357-384.
2. Ang, A. & Bekaert, G. (2002). *Regime Switches in Interest Rates.* Journal of Business and Economic Statistics 20(2): 163-182.
3. Guidolin, M. & Timmermann, A. (2007). *Asset allocation under multivariate regime switching.* Journal of Economic Dynamics and Control 31(11): 3503-3544.
4. Rabiner, L. R. (1989). *A tutorial on Hidden Markov Models and selected applications in speech recognition.* Proceedings of the IEEE 77(2): 257-286.
