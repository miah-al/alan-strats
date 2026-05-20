# Strategy Ranking — Honest Assessment

**Audit date:** 2026-05-19
**Auditor:** Claude Opus 4.7 (1M context)
**Scope:** All 38 strategies in `strategies/` (18 AI-driven + 20 rules-based)

---

## Top 10 Overall

> Ranked by *likelihood of making money in production* — combining edge thesis strength, backtest realism, code quality, risk profile, and live-readiness.

| Rank | Strategy | Type | Grade | Why it's here | Trades/yr |
|------|----------|------|-------|---------------|-----------|
| 🥇 **1** | `hmm_regime` | AI | A | Classifies current vol regime (not predicting); matches defined-risk structure to it. Cleanest walk-forward in the codebase. Slippage modeled. | 12–18 |
| 🥇 **2** | `rates_spy_rotation_options` | Rules | A | Four-regime rotation (Growth/Risk-On/Fear/Inflation) on real option chain data. Roll logic sound. Long-only options = capped downside. | 8–12 |
| 🥈 **3** | `vix_spike_fade` | Rules | B+ | VIX mean reversion into 200d MA is one of the most empirically reliable edges; bull call spread caps cost. Minor IV-skew gap. | 8–15 |
| 🥈 **4** | `iron_condor_rules` | Rules | B | Vanilla VRP harvest with three hard gates (IVR / VIX / ADX). 16-delta strikes ≈84% OTM. 50% profit target de-risk heavy. Production-grade simplicity. | 8–15 |
| 🥈 **5** | `fomc_event_straddle` | Rules | B | Calendar-triggered (FOMC dates published, no lookahead). Realized > implied at events is documented (Lucca, Savor). Defined risk = debit. | ~8 |
| 🥈 **6** | `tail_risk_put_spread` | Rules | B | Mechanical quarterly hedge, cost-capped at 1%/yr, put-skew premium on solid empirical footing (Cole 2013). Negative-EV by design but worth it for tail convexity. | ~4 |
| 🥈 **7** | `dealer_gamma_regime` | Rules | B | GEX regime classification into long-straddle (negative GEX, flow regime) vs IC (positive GEX, pinning regime). Sound thesis, well-tested empirically. | 8–12 |
| 🥉 **8** | `earnings_iv_crush` | Rules | B | IV crush post-earnings is real and persistent (20–40% on average); short iron condor 1-day hold captures the bulk. Sized correctly. | 40–60 |
| 🥉 **9** | `earnings_post_drift` | Rules | B | Post-earnings drift (SUE effect) is one of the most-replicated anomalies in academic finance. Bull call spread structure caps risk. | 40–60 |
| 🥉 **10** | `ivr_credit_spread` | Rules | B | Plain vanilla VRP harvest at IVR ≥ 50%. Vertical spreads, 16-delta, 5% wings. Boring is good — proven theta strategy. | 12–18 |

### Honorable mentions (just outside top 10)
- `put_steal` (AI, B) — NII regime signal + GBM survival on bull puts. Solid, marginal data-quality flaws.
- `vix_term_structure` (AI, B) — VIX contango/backwardation regime classifier. Same VIX-as-IV proxy issue as IC_AI.
- `rates_spy_rotation` (Rules, B) — Simpler allocation version of #2; B-grade because it's directional, not optioned.
- `bull_put_spread` (Rules, B-) — IVR-gated bull put. Solid, but delta-approx instead of real BS.

### The bottom (avoid until rewritten)
- `covered_call_ai` (AI, D) — Assignment modeling missing; backtest unreliable.
- `vol_calendar_spread` (AI, D), `vol_term_structure_regime` (AI, D), `oi_imbalance_put_fade` (AI, D), `gamma_flip_breakout` (AI, D) — Incomplete implementations or label-feature tautologies.
- `broken_wing_butterfly`, `calendar_spread`, `earnings_straddle`, `vol_arbitrage`, `gex_positioning`, `calendar_spread_vix` — heavy heuristic approximation; won't be reliable at scale.

---

## Original AI-only deep-dive (3 strategies)

The detailed analysis below covers only the three originally-audited AI strategies (`hmm_regime`, `iron_condor_ai`, `covered_call_ai`). The other 35 strategies were graded via triage above.

---

## TL;DR — Which one actually makes money?

> **`hmm_regime` is the only AI strategy with a credible path to real edge.**
> The other two have known flaws large enough to swamp any ML contribution.

The HMM strategy works because it's *not actually trying to predict the future*. It classifies the **current** vol regime (a well-documented stylized fact since Hamilton 1989, Ang-Bekaert 2002) and matches a defined-risk option structure to it. That's how real vol traders think. The other two strategies use ML to do something ML is bad at (predict direction/range) and then layer cost-modeling errors on top.

---

## Ranking Table

| Rank | Strategy | Thesis Strength | Code Quality | ML Value-Add | Risk Profile | Live-Ready | Expected Real Sharpe | Verdict |
|------|----------|-----------------|--------------|--------------|--------------|------------|----------------------|---------|
| 🥇 **1** | `hmm_regime` | ★★★★★ Regime-switching is academically supported (Hamilton, Ang-Bekaert, Guidolin-Timmermann). Strategy classifies *current* regime, doesn't predict. | ★★★★☆ Cleanest walk-forward; state-relabel handles label-switching; slippage modeled; warm-start; forward-posterior gating. Minor: no margin tracking, hardcoded `dte_ex` for 2/3 structures. | ★★★★☆ Genuine — HMM provides information a rules-based IVR/VIX gate doesn't (joint structure on returns × vol). | ★★★★★ All three structures are defined-risk; `max_concurrent=1`. | ★★★★☆ Live signal uses model + heuristic fallback; just needs per-ticker `q` threading. | **0.8–1.4 (post-cost, realistic)** | **DEPLOY (paper-trade first, then small live).** Real edge candidate. |
| 🥈 **2** | `iron_condor_ai` | ★★★☆☆ "Predict range-bound next 45 days" is auto-correlated with IVR/VIX features the model already sees. Marginal info beyond a rules IC. | ★★★☆☆ Already had one leakage fix (RV-as-feature-and-label-normalizer removed; warmup raised to 180). Still: no slippage/bid-ask, VIX as IV for *any* ticker, no `class_weight`, adaptive-delta logic runs backwards from Kelly. | ★★☆☆☆ Self-acknowledged ~0.5–0.9 Sharpe post-leakage-fix vs. rules IC baseline that already does ~0.6–0.8. Marginal lift, possibly negative after fills. | ★★★★☆ Defined-risk IC; `max_concurrent=4`; reserved-margin tracked correctly. | ★★★☆☆ Live signal IVR proxy `(vix-12)/28` disagrees with backtest's 252-bar percentile → live ≠ backtest behavior. | **0.3–0.7 (post-cost)** | **PAPER ONLY.** Fix slippage + per-ticker IV first; otherwise headline Sharpe is fiction once real fills hit. |
| 🥉 **3** | `covered_call_ai` | ★★☆☆☆ Thesis claims (delta × DTE) grid optimization; code is a binary "write yes/no" with two hardcoded delta buckets. Label is trivially "did stock go up enough to keep premium?" | ★☆☆☆☆ **No assignment modeling** — ITM short call at expiry is BS-marked, stock retained, equity double-counts. Fake `days_since_earnings` (any 4% move). No commissions. ML model never used in live (`generate_signal` is pure heuristic). 90-bar warmup is overfit-prone (same issue IC_AI already fixed). | ★☆☆☆☆ The model is predicting "did stock not crash" — a directional/momentum signal in option-selling clothes. Strike "selection" is a 1-bit gate. | ★★★☆☆ Stock + short call ≈ short put payoff; loss-side is path-dependent and partly hidden by the missing assignment logic. | ★☆☆☆☆ Live signal ignores the trained model entirely. | **−0.3 to +0.5 (post-cost, post-assignment fix)** | **DO NOT USE.** Headline backtest numbers are unreliable. Rewrite required before this is honest. |

---

## What "makes money" actually depends on

A strategy makes money in production when **all four** of these hold:

1. **Edge exists in the population** — there's a real, persistent inefficiency. (HMM ✓, IC_AI ~, CC_AI ✗)
2. **The backtest faithfully simulates fills** — no theoretical mid-mark fantasies. (HMM ✓, IC_AI ✗, CC_AI ✗)
3. **The labels measure what the thesis says** — the ML is learning the right thing. (HMM N/A unsupervised, IC_AI ~, CC_AI ✗)
4. **Live = backtest** — same features, same model path. (HMM ✓, IC_AI ✗, CC_AI ✗)

**`hmm_regime` is the only one that passes all four.**

---

## Cross-cutting issues across all three

These hurt every "AI" strategy in the codebase regardless of rank:

- **VIX-as-IV is a SPY-only assumption.** Treating the VIX as the implied vol for *any* ticker's options is fine for SPY/SPX-correlated names, materially wrong for single stocks. The `description` field on each strategy claims ticker-genericity; the implementations don't deliver it.
- **No bid/ask cost component.** Slippage parameters are inconsistent: HMM has `slip=0.05/leg`, IC_AI has 0, CC_AI has 0. A 4-leg IC closed at 50% of credit can be entirely consumed by 3–5¢/leg adverse fills.
- **Final saved model = last walk-forward fit.** All three save the most recent retrain's model. That's typically trained on the most recent 9–12 months only (after the purge), which may be the most regime-anomalous window. Consider refitting on full history before persisting for live use.
- **Tree-based GBM with StandardScaler.** Both `iron_condor_ai` and `covered_call_ai` pipeline a scaler ahead of GBM. Trees are scale-invariant. Harmless but cargo-cult.

---

## Recommended next moves (in order of leverage)

1. **Promote `hmm_regime` to first-class.** Add reserved-margin tracking, thread per-ticker `q`, parameterize the bull-put / long-put `dte_ex` exits. Paper-trade for 60–90 days on SPY before risking capital.
2. **Park `iron_condor_ai` until** you've added bid/ask slippage, threaded per-ticker IV (read from `option_snapshots`), and either fixed or A/B-tested the inverted adaptive-delta logic.
3. **Rewrite `covered_call_ai` before quoting any number from it.** The assignment-modeling gap is a correctness bug, not a refinement. Until then its backtest equity curve is fiction.
4. **Treat the "rules" IC as the honest baseline.** If `iron_condor_ai`'s post-fix Sharpe is 0.5–0.9 and the rules IC already does ~0.6–0.8 (per the IC_AI audit comments), the ML layer is not earning its complexity budget. That's a defensible reason to *remove* the AI variant, not improve it.

---

## Caveats on this ranking

- Scores reflect what I can verify by reading source code on **2026-05-19**, not live performance.
- I haven't run any of the backtests; ratings are about *whether the backtest is trustworthy*, not what its equity curve shows.
- The "Expected Real Sharpe" column is a wide range, not a forecast. It reflects how much I'd haircut the headline backtest after correcting the issues listed.
- An "edge candidate" still needs walk-forward out-of-sample validation, paper trading, and small-size live validation before it earns real capital.
