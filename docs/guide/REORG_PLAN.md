# Reorganization Plan — Quant Course

*Author: senior QF reviewer. Phase A deliverable. No source files have been
edited; this document is a blueprint for Phase B execution.*

---

## 0. Executive summary

The guide contains all the right material, but its topical wiring is wrong in
three specific ways:

1. **Stochastic-calculus is fractured.** Itô's lemma is used extensively from
   CH06 onward but is not *proved* until CH08. CH06 §6.0 hands you a short
   "stochastic integral toolkit" before it is needed; CH08 re-derives it
   properly. CH02 already built a CLT for the binomial and a GBM limit but
   didn't use it to anchor a BM construction.
2. **Measure-change machinery is reinvented four times.** CH03 (general
   Radon-Nikodym + numeraire), CH08 §8.15 (measure change + Girsanov in the
   Feynman-Kac chapter), CH09 §9.4-9.5 (Radon-Nikodym + Girsanov + two-numeraire
   switch — the most complete treatment), CH11 §11.8 (T-forward measure +
   Girsanov again), CH12 §12.3 (T-forward measure yet again). Each treatment
   is slightly different. A reader cannot tell which is canonical.
3. **Vasicek/Hull-White is developed three times in three different registers.**
   CH04 §4.4-4.5 (discrete AR(1) → continuous OU → closed-form bond); CH05
   §5.2-5.11 (full Ho-Lee → Vasicek → HW → swaps → CDS); CH11 §11.1-11.8 (full
   Vasicek → affine → bond options). The course ends up teaching the same
   SDE, the same affine ansatz, and the same closed-form bond price three
   times with different notation.

On top of the redundancies, **CH06 is 4,300 lines** because it was asked to
carry: the stochastic-integral primer, the self-financing apparatus, the
generalised BS PDE, specialisation to GBM, three worked solutions, discrete
hedging P&L, move-based hedging, delta-gamma, vega, dividends, forwards,
futures, and the Black PDE. **CH08 is 3,000 lines** because it was asked to
carry: a full BM construction, total/quadratic variation, Itô integrals, Itô
isometry, Itô's lemma (three forms), Feynman-Kac (plain + discounted +
state-dependent), a second Black-Scholes derivation, Girsanov, forwards vs
futures *again*, and options on futures *again*. CH03 at 311 lines is far too
thin for its conceptual weight. CH09 at 734 lines is actually the cleanest
treatment of Girsanov in the whole guide but is buried in chapter 9.

The fix is structural surgery: **consolidate the stochastic calculus into a
single early block, consolidate measure change into one canonical derivation,
pick *one* Vasicek development, and factor CH06/CH08 into three right-sized
chapters.** The total length stays near 18–19k lines; no substantive content
is dropped.

---

## 1. Diagnosis of current structure

### 1.1 Scattering — topics split across chapters that should live together

| Topic | Appears in | Problem |
|---|---|---|
| Itô's isometry, Itô's lemma, stochastic integrals | CH06 §6.0 (abbreviated toolkit), CH08 §8.3–§8.8, §8.14A (three-form derivation + Itô III) | Used in CH06 before being proved in CH08 — a textbook forward reference. |
| Brownian motion construction, total/quadratic variation, CLT for scaled walk | CH02 §2.11 + §2.8.4 (GBM limit), CH08 §8.1–§8.4 | CH02 takes an informal limit ("default-Bernoulli tree → Black-Scholes") that is made rigorous only in CH08. Reader sees BS before sees BM. |
| Radon-Nikodym derivative | CH03 §3.1, CH08 §8.15, CH09 §9.4, CH11 §11.8, CH12 §12.3 | Reintroduced in four of the five chapters, with slightly different notation and coverage each time. |
| Girsanov's theorem | CH08 §8.15.3 (numeraire-change Brownian shift), CH09 §9.5 (full derivation with density process), CH11 §11.8 (applied to T-forward) | The *best* treatment is buried in CH09 — the chapter labelled "Futures Contracts" — and the weaker treatments in CH08 and CH11 never reference it. |
| T-forward measure | CH03 §3.3 (preview), CH11 §11.8 (worked for Vasicek bond options), CH12 §12.3 (worked for caplets) | Each introduces the T-forward measure from scratch as though it were new. |
| Vasicek short-rate model (SDE + solution + integrated rate + bond) | CH04 §4.4–§4.5, CH05 §5.4, §5.7–§5.9 (for HW), CH11 §11.3–§11.5 | Derived three times. CH04 uses it to motivate calibration; CH05 uses it for IRS/CDS; CH11 uses it for bond options. The derivations repeat; only the applications differ. |
| Ho-Lee | CH04 §4.3 (short-rate lattice with rate calibration), CH05 §5.2–§5.3 (full treatment) | CH04's motivational version duplicates CH05's "real" version. |
| Black-Scholes formula | CH02 §2.8.7 (from default-tree limit), CH06 §6.6–§6.9 (via replication PDE), CH08 §8.14 (via Feynman-Kac) | Three derivations. CH02's is a heuristic CLT limit; CH06's is the classical hedging derivation; CH08's is the modern-textbook martingale derivation. Reader cannot tell which is meant to be canonical. |
| Feynman-Kac | CH07 §7.4–§7.5 (as a separate topic before CH08 proves it), CH08 §8.9–§8.13 (full) | CH07 derives FK without having formally established Itô's lemma — another forward reference. |
| Forwards vs futures, Black PDE | CH06 §6.16–§6.17 (as a dividend/futures extension), CH08 §8.16–§8.18 (forwards/futures/options-on-futures), CH09 (full chapter) | Three places. CH09 is supposed to be the home chapter but its §9.1-§9.3 on Bachelier/OU futures is good; its §9.4-§9.5 is actually the cleanest measure-change derivation. |
| Margrabe / exchange option | CH09 §9.6 | Fine where it is, but it uses Girsanov from §9.5 — which would be a forward reference if a reader jumped to it from the numeraire-change preview in CH03. |
| Delta-gamma hedging | CH06 §6.13, CH07 §7.2 | CH06 introduces delta-gamma as a "two-instrument replication" and CH07 re-does it as a "local quadratic fit." They are the same construction expressed twice. |

### 1.2 Forward references (topic used in CH N, proved in CH M > N)

- **CH04** writes `dr_t = κ(θ-r_t) dt + σ dW_t`, solves the OU SDE, and computes
  `∫ r_u du` as a Gaussian integral — but Itô's lemma, the Itô isometry, and
  the Fubini-Gaussian identities it uses are not proved until CH08.
- **CH05** uses the Donsker-style continuous limit, the log-normal / Gaussian
  moment-generating-function trick, and the full `∫_0^T r_u du` computation,
  again before CH08.
- **CH06** entire chapter rests on Itô's lemma and the self-financing Itô
  differential. Its §6.0 hands the reader the minimum toolkit but does not
  *derive* it — that is CH08.
- **CH07** §7.4 proves Feynman-Kac independently, and the proof uses an Itô
  martingale decomposition that has not been formally established until CH08.
- **CH10** (Heston) uses two-dimensional Itô, change of measure on a 2D BM, and
  Feller's condition — all of which require machinery that is scattered across
  CH06/CH07/CH08/CH09 and never cleanly collected.

### 1.3 Bloat vs thinness

| Chapter | Lines | Diagnosis |
|---|---|---|
| CH01 | 1,451 | Right-sized for a one-period warm-up. Keep. |
| CH02 | 1,393 | Tries to be CRR + FTAP + default tree + BS limit + MC + forward-starting + barriers. Should be split: one chapter for tree/FTAP, one for MC + path-dependent. |
| CH03 | 311 | Grossly under-sized for the conceptual weight of "measure changes." Should become part of a larger measure-change chapter that *is* the canonical treatment. |
| CH04 | 1,341 | Contains (a) lattice calibration, (b) a stand-alone Vasicek derivation, (c) a practitioners-survey on calibration governance. Item (b) duplicates CH05/CH11; items (a) and (c) belong together. |
| CH05 | 1,893 | Tree warm-up + Ho-Lee + Vasicek + HW + IRS + CDS + callable bonds + yield surface. IRS/CDS/callable should probably split off; short-rate dynamics should fuse with CH11. |
| CH06 | 4,331 | **Single biggest problem.** Must split into three chapters. |
| CH07 | 1,296 | VaR block is solid and thematically self-contained. The Feynman-Kac block is an intruder — it belongs with the stoch-calc block. |
| CH08 | 2,995 | **Second biggest problem.** Trying to be both "BM/Itô foundations" and "FK + BS + Girsanov + futures." Must split. |
| CH09 | 734 | Underweight. §9.4-9.5 (Girsanov) is gold but buried. §9.6 (Margrabe) is one-shot. §9.7 (futures/forwards convexity) belongs with measure change. |
| CH10 | 1,060 | Right-sized as a Heston capstone. Keep. |
| CH11 | 1,102 | Third-time Vasicek. Should absorb CH05's rate-model content and drop the duplicated derivation, keeping only bond options + T-forward. |
| CH12 | 719 | Right-sized as a caps/swaptions capstone. Keep. |

### 1.4 Pedagogical dependency violations

The current order violates the rule *"foundations before applications"* in
four places:

1. CH02 derives a Black-Scholes formula (§2.8.7) from a CLT limit before the
   reader knows what a stochastic integral is.
2. CH03 defines Radon-Nikodym but has no stochastic calculus available, so
   the "preview" of the T-forward measure in §3.3 is essentially a promissory
   note.
3. CH04 / CH05 develop Vasicek in continuous time before Itô has been proved.
4. CH06 requires Itô's lemma and uses it aggressively; the "toolkit" in §6.0
   asks the reader to take it on faith.

---

## 2. Proposed new structure

**User-locked 5-Part grouping** (textbook-standard names, Björk/Shreve convention):

| Part | Chapters | Name |
|---|---|---|
| I | CH01–CH02 | Discrete-Time Models |
| II | CH03–CH05 | Continuous-Time Models |
| III | CH06–CH10 | Equity Derivatives |
| IV | CH11–CH13 | Interest-Rate Models |
| V | CH14–CH15 | Stochastic Vol & Rate Derivatives |

Fifteen chapters (up from twelve). Length hits are taken in CH06 (split into
3) and CH08 (split into 2); one pure consolidation chapter on measure change
absorbs CH03's current content.

| New # | Title | Description (one line) |
|---|---|---|
| 1 | One-Period Binomial: Utility + No-Arbitrage | **Unchanged from old CH01.** Single-period FTAP, replication, indifference pricing. |
| 2 | Multi-Period Binomial, CRR, and the FTAP | **Trimmed old CH02 §§2.1–2.7, §2.9.** Backward induction, CRR parameterisations, FTAP, non-uniqueness, American options. BS limit and Monte-Carlo/path-dependent *move out*. |
| 3 | Stochastic-Calculus Primer: Brownian Motion, Itô, SDE Solutions | **New consolidation chapter.** Absorbs old CH08 §§8.1–§8.8, §8.14A (Itô III), the stochastic-integral fragments from old CH06 §6.0, and the lattice-CLT from old CH02 §2.8.4 / §2.11. BM construction from scaled random walk, total & quadratic variation, Itô integrals, Itô isometry, Itô's lemma in three forms, OU SDE solution, worked integrals. **This is the chapter that makes every forward reference go away.** |
| 4 | Feynman-Kac and the SDE-PDE Bridge | **Absorbs old CH08 §§8.9–§8.13, plus the FK material from old CH07 §§7.4–§7.5.** FK zero-drift, FK with discounting, FK with state- and time-dependent coefficients. No Black-Scholes or measure change here yet. |
| 5 | Measure Changes, Radon-Nikodym, and Girsanov | **Consolidation of old CH03 (entire), CH08 §8.15, CH09 §§9.4–§9.5.** The canonical measure-change chapter. Equivalent measures, RN derivative, state-by-state density on a finite tree, density process & Doléans-Dade exponential, Girsanov's theorem, two-numeraire switching, T-forward measure preview. This is what Chapter 3 *should* have been in the first place. |
| 6 | Dynamic Hedging I: Self-Financing Strategies and the Black-Scholes PDE | **First third of old CH06: §§6.1–§6.10, §6.11 (discrete hedging), §6.12 (move-based).** Self-financing, market price of risk, generalised BS PDE, GBM specialisation, Black-Scholes formula for call/put/digital, greeks. |
| 7 | Dynamic Hedging II: Greeks, Delta-Gamma, Vega, and Dividends | **Second third of old CH06: §§6.13–§6.15, plus old CH07 §§7.2–§7.3, §7.7, §7.7A.** Delta-gamma (merged: one canonical treatment from both old CH06.13 and old CH07.2), vega & volatility risk, options on dividend-paying assets, put-call parity. Delta-gamma as local-quadratic fit (CH07's framing) and as two-instrument replication (CH06's framing) become two angles on one topic in one chapter. |
| 8 | Forwards, Futures, and the Black PDE | **Consolidates old CH06 §§6.16–§6.17, old CH08 §§8.16–§8.18, and old CH09 (entire).** Forward price, futures price & daily settlement, dynamics of the futures price, options on futures (Black PDE), Bachelier/OU futures examples, Margrabe exchange option, futures–forward convexity adjustment. Uses Girsanov from CH05. |
| 9 | Risk Measures: VaR, CTE, and Coherent Risk | **Carved out of old CH07: §§7.1, §7.7A.1–§7.7A.4.** VaR (historical, parametric, MC, Cornish-Fisher), CTE / expected shortfall, coherent risk measures, Basel context, backtesting (Kupiec, Christoffersen), stress testing, risk decomposition, liquidity-adjusted risk, delta-gamma parametric VaR, hedged P&L distribution. **This chapter becomes genuinely self-contained** — no Feynman-Kac material anymore. |
| 10 | Monte Carlo, Path-Dependent, and Forward-Starting Options | **Carved out of old CH02: §§2.11–§2.13.** SLLN, sample mean/SE, lognormal GBM generator, cliquet (forward-starting), up-and-in/barrier pricing. Now sits after CH06 so the lognormal-GBM machinery is already fluent. |
| 11 | Calibration: Lattices, Short Rates, and the Yield Curve | **Old CH04 minus the free-standing Vasicek/bond-price derivation.** Keeps §4.1 (FTAP on lattice), §4.2 (change-of-measure calibration, RN on multinomial, optimisation, regularisation, governance), §4.3 (rate trees + bond bootstrap), and §4.8 (governance). The Vasicek derivation §4.4–§4.5 moves out to CH12. |
| 12 | Short-Rate Models: Vasicek, Ho-Lee, Hull-White, Affine | **Consolidation of old CH04 §§4.4–§4.5 + old CH05 §§5.2–§5.9 + old CH11 §§11.1–§11.7.** One canonical Vasicek derivation (SDE, solution, integrated rate, closed-form bond, affine ansatz, ODE system), one canonical Ho-Lee (discrete + continuous limit), one canonical Hull-White (time-dependent θ calibrated to market curve), plus affine term structure and yield-curve shapes. The *derivation* lives here; applications move to CH13. |
| 13 | Rate-Derivative Applications: Swaps, CDS, Bond Options, Callables | **Consolidation of old CH05 §§5.10–§5.12 + old CH11 §§11.8–§11.9.** IRS, par swap rate, CDS, callable bonds, European bond options (Jamshidian / Vasicek-Black), T-forward measure applied. The T-forward measure is *not* re-derived here — CH05 did it once. |
| 14 | Caps, Floors, Swaptions, and Stochastic Volatility (capstone) | **Old CH10 + old CH12 combined, or kept as two chapters.** Heston as a capstone on equity-side stoch-vol + capture Heston's measure change with CH05's apparatus, then caps / caplets / swaptions as the final fixed-income applications. *If the user prefers to keep them separate, keep them separate — see §5.3 below.* |

**Summary of changes:**
- Old CH08's BM/Itô half → new CH03.
- Old CH08's Feynman-Kac half + old CH07's FK → new CH04.
- Old CH03 + old CH08 §8.15 + old CH09 §§9.4–§9.5 → new CH05 (measure change consolidation).
- Old CH06 (one chapter, 4,331 lines) → new CH06 + CH07 + CH08 (three chapters).
- Old CH09 (Futures) absorbed into new CH08.
- Old CH07's risk-measures half → new CH09; its FK half → new CH04; its delta-gamma half → new CH07.
- Old CH02's MC / cliquet / barrier → new CH10.
- Old CH04/CH05/CH11 short-rate content → new CH11 (calibration) + CH12 (short-rate models) + CH13 (applications).
- Old CH10 and CH12 → new CH14 (or kept as two, see §5).

---

## 3. Chapter-by-chapter migration map

For each new chapter I list (a) sources, (b) new glue material that must be
written to stitch things together, and (c) dependencies.

### CH01 — One-Period Binomial: Utility + No-Arbitrage

- **Source:** old CH01 (entire).
- **Glue:** none. Keep as-is. Possibly soften the final paragraph so it points
  forward to CH02 rather than the current table-of-contents roadmap.
- **Depends on:** nothing.

### CH02 — Multi-Period Binomial, CRR, and the FTAP

- **Source:** old CH02 §§2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.9.
- **Drop from old CH02:** §2.8 (default tree → Black-Scholes limit) is deleted
  as a *derivation* but kept as a one-page "preview" — the full BS derivation
  now lives in CH06. §§2.10–§2.13 (MC + cliquet + barrier) move to new CH10.
- **Glue:** Rewrite §2.8 as a half-page sketch: "the binomial tree converges
  to GBM in the Donsker sense, and the CRR limit produces the Black-Scholes
  formula — we'll prove this in CH06 once Itô is available." Remove the
  current full Bernoulli-to-BS derivation.
- **Depends on:** CH01.

### CH03 — Stochastic-Calculus Primer: Brownian Motion, Itô, SDE Solutions

- **Source:**
  - Old CH02 §2.8.4 (continuous-time limit of default tree) — used as a
    "BM as lattice limit" motivation, then formalised.
  - Old CH08 §§8.1–§8.4 (random walk construction, BM definition, total
    variation, quadratic variation).
  - Old CH08 §§8.5–§8.8 (stochastic integrals, Itô isometry, Brownian
    moments, Itô's lemma for BM, three worked Itô-lemma examples).
  - Old CH08 §8.14A (Itô III — Itô for general Itô processes).
  - Old CH06 §§6.0.1–6.0.4 (Itô isometry statement, OU solution, worked
    stochastic integrals). **Fold the OU solution here** — it is the first
    non-trivial SDE the reader solves.
- **Glue (new writing needed):**
  - A 1–2 page opening section tying the scaled random walk of CH02 to the
    BM construction (bridges the two chapters cleanly).
  - After Itô's lemma III, add a short "SDE catalogue" section naming the
    GBM, OU, and constant-coefficient SDEs the later chapters will solve,
    each solved as a worked Itô-lemma example.
- **Needs renumbering:** every equation from old CH08 §§8.1–§8.8 and §8.14A
  plus old CH06 §§6.0.1–§6.0.4. Mechanical.
- **Content to preserve literally:** the three-step Itô isometry proof, the
  $(\mathrm{d}W)^2 = \mathrm{d}t$ heuristic-then-rigorous sequence, the three
  Itô-lemma forms, the OU solution.
- **Depends on:** CH02 (for the CRR → GBM motivation, scaled random walk
  notation).

### CH04 — Feynman-Kac and the SDE-PDE Bridge

- **Source:**
  - Old CH08 §§8.9, 8.9A, 8.10, 8.11, 8.12, 8.12A (FK statement +
    martingale derivation + worked linear/quadratic/exponential payoffs).
  - Old CH08 §§8.13, 8.13.1, 8.13.2 (FK with drift, diffusion, discounting;
    state-dependent coefficients).
  - Old CH07 §§7.4, 7.5, 7.6 (FK with discounting, integrating factor,
    European call on non-dividend stock).
- **Glue:**
  - Merge old CH07.4 and CH08.9A: both give a martingale derivation of FK.
    Keep old CH08.9A's telescoping proof (it's cleaner) and use old
    CH07.4.2–7.4.3 as the "lettered-h" intuition.
  - Explicitly *defer* Black-Scholes via FK to CH06 — this chapter ends with
    the general FK formula, not with any specific pricing model.
- **Content to move out:** old CH08 §8.14 (BS via FK) moves to CH06 as an
  alternative derivation. Old CH08 §§8.15–§8.18 move to CH05 (measure change)
  and CH08-new (futures).
- **Depends on:** CH03.

### CH05 — Measure Changes, Radon-Nikodym, and Girsanov

- **Source:**
  - Old CH03 (entire — §§3.1, 3.2, 3.3).
  - Old CH08 §§8.15.1, 8.15.2, 8.15.3 (martingale condition for traded assets,
    change of numeraire to A, F/A is a Q^A martingale).
  - Old CH09 §§9.4, 9.5 (Radon-Nikodym, density process, Girsanov,
    two-numeraire switching) — **this is the canonical derivation**; the
    others are trimmed to cross-references.
- **Glue:**
  - Write a new chapter opening: "In CH01-CH02 we introduced Q as *the*
    pricing measure. In this chapter we generalise: every positive tradable
    defines its own measure, and Girsanov's theorem tells us how they're
    related. We'll use this machinery explicitly in CH06 (to justify the
    $\mathbb{Q}$-drift of GBM), CH08 (futures measure), CH12 (T-forward),
    and CH13 (annuity measure)."
  - Structure: (1) two-state / finite-state intuition — take from old CH03
    §3.2 (worked seven-state example); (2) Radon-Nikodym derivative in
    continuous time — from old CH09 §9.4; (3) density process and
    Doléans-Dade — from old CH09 §9.5; (4) Girsanov — from old CH09 §9.5;
    (5) two-numeraire switching — from old CH09 §9.5; (6) T-forward measure
    preview — from old CH03 §3.3.
- **Depends on:** CH03 (needs Itô and SDE solutions), CH04 (FK is used in
  some density-process Itô calculations).

### CH06 — Dynamic Hedging I: Self-Financing Strategies and the Black-Scholes PDE

- **Source:**
  - Old CH06 §§6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 6.10 (self-
    financing, delta hedge, market price of risk, generalised BS PDE, GBM
    specialisation, three worked examples, time-based formula).
  - Old CH06 §§6.11, 6.12 (discrete hedging, move-based).
  - Optionally: a pointer to old CH08 §8.14 as an alternative FK derivation of
    the same BS formula.
- **Glue:**
  - Remove old CH06 §6.0 (stoch-integral toolkit) — it's now fully covered
    in CH03.
  - Cross-reference CH05 for the measure-change step (the market-price-of-
    risk argument now explicitly connects $\lambda = (\mu-r)/\sigma$ to the
    Girsanov drift shift that produces $\mathbb{Q}$).
  - At the end of §6.6 (GBM specialisation), add a "dual derivation via
    Feynman-Kac" half-page box pointing to CH04 — the reader now sees the
    same BS PDE arise from two independent routes.
- **Depends on:** CH03, CH04, CH05.

### CH07 — Dynamic Hedging II: Greeks, Delta-Gamma, Vega, and Dividends

- **Source:**
  - Old CH06 §§6.13 (delta-gamma), 6.14 (vega), 6.15 (dividends).
  - Old CH07 §§7.2 (delta-gamma as local quadratic fit), 7.3 (self-financing
    revisited with dividends and transaction costs), 7.7 (put/call/parity
    greeks sketches), 7.7.4.1 (gamma-dollar, vega-dollar).
- **Glue:**
  - Merge old CH06 §6.13 and old CH07 §7.2 into a single delta-gamma
    treatment that gives both framings: "two-instrument replication"
    (structural) and "local quadratic fit" (practical hedging). Keep the
    worked numerical example from old CH07 §7.2.2.1.
  - Merge old CH06 §6.15 (dividends) with old CH07 §7.3.1.1 (self-financing
    with dividends); these cover the same extension.
- **Depends on:** CH06.

### CH08 — Forwards, Futures, and the Black PDE

- **Source:**
  - Old CH06 §§6.16 (forward price), 6.17 (Black PDE for options on futures).
  - Old CH08 §§8.16 (forwards vs futures), 8.17 (hedging with futures), 8.18
    (call on a futures).
  - Old CH09 §§9.1, 9.2, 9.3 (Bachelier futures, OU futures), 9.6 (Margrabe),
    9.7 (futures-vs-forward convexity adjustment).
- **Glue:**
  - The three existing treatments of "options on futures" collapse to one:
    use old CH06 §6.17's PDE derivation as the canonical path, with old CH08
    §§8.17–§8.18 as the Feynman-Kac cross-check.
  - Margrabe (old CH09 §9.6) stays intact — it's the cleanest use of
    two-asset change of measure in the guide.
  - Convexity adjustment (old CH09 §9.7) stays; it previews the convexity
    adjustments that appear in CH13 (rate derivatives).
- **Depends on:** CH05 (Girsanov), CH06 (BS PDE).

### CH09 — Risk Measures: VaR, CTE, and Coherent Risk

- **Source:**
  - Old CH07 §§7.1.1 (VaR), 7.1.2 (CTE), 7.1.3 (thin- vs fat-tail), 7.1.4
    (Basel), 7.1.5 (coherent framework), 7.1.6 (backtesting), 7.1.7 (stress),
    7.1.8 (risk decomposition), 7.1.9 (P&L attribution), 7.1.10 (liquidity).
  - Old CH07 §§7.7A.1–§7.7A.4 (hedged-P&L distribution, delta-gamma VaR,
    hedged CTE, operational integration).
- **Glue:**
  - Make the chapter genuinely self-contained by moving the FK material that
    currently intrudes (§§7.4–§7.6) out to CH04 entirely. The remaining risk
    content reads as a coherent whole.
  - Keep the "delta-gamma parametric VaR" linkage to CH07 (new) via a short
    cross-reference, since it uses greeks defined there.
- **Depends on:** CH06 (needs greeks definitions), CH07 (needs delta-gamma).

### CH10 — Monte Carlo, Path-Dependent, and Forward-Starting Options

- **Source:**
  - Old CH02 §§2.10 (protected put / simulation), 2.11 (MC, SLLN, sample
    SE), 2.12 (forward-starting / cliquet), 2.13 (barrier options).
- **Glue:**
  - Now that the reader knows GBM from CH06, the lognormal-GBM generator in
    old §2.11.3 can be derived properly rather than asserted.
  - Add a short closing section on variance reduction (antithetic variates,
    control variates) as a bridge to the Heston MC pricing that could appear
    in CH14.
- **Depends on:** CH02 (tree), CH06 (GBM).

### CH11 — Calibration: Lattices, Short Rates, and the Yield Curve

- **Source:**
  - Old CH04 §§4.1 (FTAP on lattice), 4.2 (change-of-measure on multinomial,
    RN derivative, optimisation setup, regularisation), 4.3 (short-rate
    bootstrap on a bond lattice), 4.7 (takeaways), 4.8 (governance /
    sociology of calibration).
- **Content moved out of old CH04:** §§4.4–§4.5 (Vasicek derivation + bond
  prices) are deleted here and absorbed into new CH12.
- **Glue:**
  - The new chapter focuses cleanly on *the act of calibration* — finding
    risk-neutral probabilities / drifts from market prices — across three
    settings: single-period lattice, multinomial lattice, interest-rate
    lattice. No continuous-time Vasicek here.
  - End with a roadmap: "the natural continuous-time short-rate models are
    developed in CH12, and the applications in CH13."
- **Depends on:** CH02, CH05.

### CH12 — Short-Rate Models: Vasicek, Ho-Lee, Hull-White, Affine

- **Source:**
  - Old CH04 §§4.4 (Vasicek SDE, AR(1), continuous limit), 4.5 (bond price
    under Vasicek).
  - Old CH05 §§5.1 (rate-tree warm-up + non-uniqueness of Q), 5.2 (Ho-Lee
    discrete), 5.3 (Ho-Lee continuous), 5.4 (Vasicek constant θ), 5.5 (HW
    discrete), 5.6 (summed integral), 5.7 (continuous limit), 5.8 (HW bond
    price), 5.9 (θ(u) calibration).
  - Old CH11 §§11.1 (short rate + AR(1) motivation), 11.2 (P → Q), 11.3
    (explicit Vasicek solution), 11.4 (integrated rate + bond), 11.5 (PDE +
    affine ansatz), 11.6 (matching yield curve), 11.7 (yield shapes).
- **Glue (this is the biggest merge):**
  - Pick old CH11 as the backbone because it has the cleanest narrative from
    SDE → closed-form bond. Fold in CH05's discrete lattice warm-up (for
    motivation only — CH11 is calibration chapter now), CH05's Ho-Lee +
    continuous-limit (for the `κ → 0` case), and CH04's AR(1) discretisation
    (as the discrete counterpart of Vasicek).
  - **Single canonical Vasicek derivation**: SDE → explicit solution →
    distribution of $r_T$ → distribution of $\int_0^T r_u\,du$ → closed-form
    bond price → affine ODEs. Delete the duplicates.
  - **Single canonical Ho-Lee derivation**: discrete Ho-Lee → Donsker → bond
    bootstrap. Delete the duplicate.
  - **Single canonical Hull-White derivation**: Vasicek with time-dependent
    θ → calibration to the market curve → yield shapes. Delete duplicates.
- **Content renumbering:** virtually everything from old CH04 §§4.4-4.5,
  old CH05 §§5.1-5.9, and old CH11 §§11.1-11.7 needs to be renumbered.
- **Depends on:** CH03 (Itô), CH04 (FK for bond-price formula), CH05
  (Girsanov for P → Q).

### CH13 — Rate-Derivative Applications: Swaps, CDS, Bond Options, Callables

- **Source:**
  - Old CH05 §§5.10 (IRS), 5.10.5 (callable bonds), 5.11 (yield surface),
    5.12 (CDS).
  - Old CH11 §§11.8 (bond options + T-forward measure — use the cross-
    reference to CH05 rather than re-deriving Girsanov), 11.9 (worked
    examples), 11.9A (multi-factor, HJM, LMM, SABR), 11.9B (PDE vs MC).
- **Glue:**
  - Chapter structure: (1) IRS and par swap rate; (2) callable bonds (uses
    HW tree); (3) CDS; (4) bond options and T-forward measure — where the
    T-forward measure is *not* re-derived, it's cited from CH05; (5)
    multi-factor preview.
- **Depends on:** CH05, CH12.

### CH14 — Capstone: Heston (Stochastic Vol) + Caps, Floors, Swaptions

- **Source:**
  - Old CH10 (entire — Heston).
  - Old CH12 (entire — caps, caplets, swaptions).
- **Glue:**
  - Chapter structure: Part A (Heston) = equity-side capstone on stoch-vol;
    Part B (caps/swaptions) = rates-side capstone on the T-forward /
    annuity-measure machinery.
  - Alternative: keep them as two separate chapters (CH14 Heston + CH15
    Caps/Swaptions). I recommend keeping them as two — see §5.3. Numbering in
    this table shows the merged version; the split version is identical in
    content but with one extra chapter.

---

## 4. Dependency graph

Chapters are numbered in the proposed new order; an arrow `A → B` means
"B requires A's content."

```
                              CH01 (one-period)
                                     │
                                     ▼
                              CH02 (CRR + FTAP)
                                     │
                                     ▼
                      CH03 (Stoch-Calc Primer: BM, Itô, SDEs)
                                     │
                       ┌─────────────┼─────────────┐
                       ▼             ▼             ▼
                  CH04 (FK)    CH05 (Measure)   (used later)
                       │             │
                       └──────┬──────┘
                              ▼
                 CH06 (Dyn Hedging I: BS PDE)
                              │
              ┌───────────────┼────────────────┐
              ▼               ▼                ▼
  CH07 (Greeks, DG, Vega)  CH08 (Fwd/Fut/Black)  CH10 (MC + paths)
              │               │
              └──────┬────────┘
                     ▼
             CH09 (Risk: VaR, CTE)
                     │
                     │    (independent branch: rates)
                     │
         CH02 ──▶ CH11 (Calibration)
                     │
                     ▼
         CH12 (Short-rate models: Vas/HL/HW)
            (depends on CH03, CH04, CH05)
                     │
                     ▼
         CH13 (Rate derivatives: IRS/CDS/bond options)
                     │
                     ▼
         CH14 (Heston + Caps/Swaptions capstone)
            (depends on CH05, CH06, CH10, CH12)
```

Key clean dependencies that weren't there before:

- **CH03 is the foundation.** Every chapter CH04+ depends on it; no forward
  references.
- **CH05 (measure change) is used by CH06 (for market price of risk),
  CH08 (Girsanov for futures), CH12 (P → Q), CH13 (T-forward).** All four
  applications cite a single canonical derivation.
- **CH06 is a single chapter pass on BS.** CH04's FK gives one derivation;
  CH06 gives the hedging derivation. Both converge on the same PDE.
- **CH12's Vasicek is the only Vasicek.** CH11 uses it via cross-reference;
  CH13 uses it via cross-reference.
- **Risk (CH09) depends only on greeks from CH06/CH07.** It is a
  self-contained "practical" chapter that a risk manager can read alone.

---

## 5. Trade-offs and judgment calls

### 5.1 Why I split CH06 instead of trimming it

CH06 at 4,300 lines is past the point where "trim" is a realistic intervention.
Three independent pedagogical units live there — the self-financing + BS PDE
derivation (foundational), the greeks/delta-gamma + dividends block (practical),
and the forwards-futures-Black-PDE block (applied). These three units have
different prerequisites (the third needs measure change from CH05; the first
two do not), and they belong logically with different downstream material.
Splitting into CH06/CH07/CH08 makes each a ~1,200–1,500 line chapter — still
substantial but each tractable in one sitting. The alternative (keep CH06
monolithic but trim to ~3,000 lines) would leave the forward-futures block
still trapped inside a chapter that is nominally about equity dynamic hedging,
which is the root cause of the three-place futures treatment.

### 5.2 Why I split CH08 instead of keeping the "Brownian motion + Feynman-Kac" union

The current CH08 title — "Brownian Motion Foundations & Feynman-Kac" — is a
confession that two different chapters were zipped together. The BM half is a
*prerequisite* chapter (it needs to run before CH06); the FK half is an
*application* chapter (it uses Itô to derive a PDE, then later in the same
chapter redundantly re-derives BS and re-derives Girsanov). Splitting produces
CH03 (the true prerequisite, now placed early) and CH04 (FK as an application
of Itô). This is the single most important move in the whole reorganisation
because it is what lets CH06 honestly depend on a previously proved Itô's
lemma.

### 5.3 Why I recommend keeping Heston and Caps/Swaptions as two chapters (the 15-chapter version)

The merged CH14 above is cleaner for table-of-contents purposes, but in
practice these are two very different chapters. Heston is equity-side
stochastic volatility with its own specialised machinery (characteristic
functions, Fourier inversion, Riccati ODEs), and Caps/Swaptions is a
rates-side numeraire-change application. They share almost no technical
overlap. I would keep them as two chapters (giving a 15-chapter guide) and
accept the slightly larger TOC count in exchange for cleaner chapter
boundaries. **Recommendation: 15 chapters with CH14 = Heston and CH15 = Caps
& Swaptions.**

### 5.4 Where I *did not* consolidate, and why

- **American options on the binomial tree (old CH02 §2.9)** stays in CH02
  even though one could argue it belongs with MC in CH10. American pricing
  is the cleanest non-trivial use of backward induction after European
  pricing, and it belongs in the "here is what trees can do" chapter.

- **Protected put / simulation sketch (old §2.10)** could go either way
  (CH02 or CH10). I put it in CH10 because it's a simulation-based sanity
  check and logically sits with the Monte-Carlo material.

- **Old CH05 §5.1.6 (non-uniqueness of Q in a rate tree)** is a subtle
  point that could live either in CH11 (calibration) or CH12 (rate models).
  I put it in CH12 as the opening motivation, because it is the reason
  Vasicek-family models *need* a free drift parameter and it is more
  compelling once the reader has seen why bonds-not-rates-are-traded.

- **Convexity adjustment (futures vs forward, old CH09 §9.7)** belongs in
  CH08 (futures), not CH13 (rate derivatives), because it is fundamentally a
  measure-change calculation on a single asset's forward, and because it
  comes before the reader has seen Vasicek.

### 5.5 The one thing I'd push back on in the user's framing

The user said "CH08 (Feynman-Kac) now contains full BS derivation + Greeks —
overlap with CH06." I agree that BS and greeks are duplicated — but CH08 §8.14
is actually a *useful* second derivation (Feynman-Kac → PDE via martingale
argument) because it's the modern route every textbook now uses. My proposal
is not to delete it but to move it to CH06 as a sidebar: the "hedging argument
derivation" and the "Feynman-Kac martingale derivation" become two sibling
sections inside a single BS chapter, and the reader explicitly sees that they
give the same PDE by different routes. That is actually a major pedagogical
win and I'd argue the second derivation is worth preserving, not collapsing.

### 5.6 Conservative total-content estimate

Current total: 18,626 lines.
Estimated new total: 17,500 – 18,500 lines.

Net deletions come from redundancy elimination:
- One Vasicek derivation instead of three: ≈ –900 lines.
- One Girsanov instead of four: ≈ –400 lines.
- One T-forward-measure derivation instead of three: ≈ –250 lines.
- One Black-Scholes derivation with two routes (not three parallel): ≈ –300 lines.
- One delta-gamma treatment instead of two: ≈ –200 lines.

Net additions:
- ≈ +400 lines of new glue material (chapter openings, cross-references,
  dependency recaps).
- ≈ +200 lines to make CH03 feel like a complete chapter rather than a merger
  of two halves.

Net change: ≈ –1,500 lines of true substance eliminated, ≈ +600 lines of glue
added → guide shrinks by about 5%, no concepts lost.

---

## 6. Execution notes for Phase B

### 6.1 Suggested order of operations

1. **Stage all new chapter *files*** first (empty stubs with just front-matter
   and section skeletons). This lets you move content in a single pass per
   chapter rather than moving + renumbering in the same commit. Fourteen or
   fifteen stubs.

2. **Execute CH03 first.** This is the foundation — every later chapter
   depends on it. Lift old CH08 §§8.1–§8.8 + §8.14A wholesale. Lift old CH06
   §6.0 and merge. The equation numbers change but the content is almost
   entirely literal.

3. **Execute CH04 next.** Lift old CH08 §§8.9–§8.13 wholesale and merge with
   old CH07 §§7.4–§7.6. Delete the duplicated FK derivation from CH07.

4. **Execute CH05.** Lift old CH09 §§9.4–§9.5 (the best treatment) as the
   backbone; fold in old CH03's finite-state example as §5.1 warm-up; fold in
   old CH08 §8.15 as a short "Girsanov applied to traded assets" section.

5. **Execute CH06, CH07, CH08 (the old-CH06 split).** Split along the existing
   section boundaries: old §§6.1–6.12 → new CH06; §§6.13–6.15 → new CH07 (plus
   old CH07 §7.2 delta-gamma merge); §§6.16–6.17 → new CH08 (plus old CH08
   §§8.16–8.18 and old CH09).

6. **Execute CH09 (risk).** Delete the Feynman-Kac intrusion (§§7.4–§7.6),
   keep everything else from old CH07.

7. **Execute CH10 (MC + path-dependent).** Lift old CH02 §§2.10–§2.13.

8. **Execute CH11 (calibration).** Lift old CH04 §§4.1–§4.3 + §§4.7–§4.8.
   Delete §§4.4–§4.5 here (they go to CH12).

9. **Execute CH12 (short-rate models)** — this is the biggest merge. I
   recommend starting from old CH11 as the skeleton because it is the
   cleanest narrative, then surgically grafting in CH05's discrete warm-up
   and Ho-Lee, and CH04's AR(1) interpretation. The test for "done" is:
   reader sees Vasicek derived *exactly once*.

10. **Execute CH13 (rate derivatives).** Combine old CH05 §§5.10–§5.12 with
    old CH11 §§11.8–§11.9.

11. **Execute CH14/15 (Heston / Caps-Swaptions).** Largely preserve.
    Update cross-references into CH05 (Girsanov) and CH12 (short-rate).

12. **README rewrite** as the final step. The current README is a
    table-of-contents + course-arc. After the reorg, the course arc becomes
    *dramatically* cleaner and should be rewritten to advertise the new
    foundation-first structure.

### 6.2 What to preserve literally vs re-derive

**Preserve literally (just move + renumber):**
- All worked numerical examples (CH01, CH02, CH04's IRS/CDS tables, CH05's
  hedge-error graphs, CH06's discrete-hedging simulation, CH08's
  Bachelier/OU numerics, CH10's Heston vs BS table, CH12's caplet strip).
- All figures (they are regenerated from `build_figures.py`, so the Python
  code itself does not need to change — only the chapters that embed the
  images).
- The Reference Formulas appendices at the end of each chapter — just
  consolidate per new chapter.

**Re-derive / rewrite:**
- Every chapter opening paragraph. These reference specific earlier chapters
  and must be rewritten to reference the new numbering. Cost: ~400 lines
  total.
- The "Course Arc" in README.md — full rewrite.
- Glue text at section boundaries where a cross-reference was made (e.g.
  "as we derived in §2.3" often has to become "as we derived in §3.4"). Use
  a grep pass for `§\d+\.\d+` and `Chapter \d+` to find them all.

### 6.3 Risks and mitigations

**Risk A: breakage of internal references.**
Every `(3.4)`-style equation tag is local to its chapter, so no cross-chapter
renumbering breaks anything — good. But cross-chapter *prose* references
("in Chapter 8 we prove…") will all go stale. Mitigation: a pre-flight `grep`
pass for "Chapter \d+", "CH\d+", "§\d+\.\d+", and explicit references.

**Risk B: duplicated content surviving the merge.**
The three Vasicek derivations are easy to conflate — each uses slightly
different notation (CH04 uses $(α, β)$ for the AR(1); CH05 uses discrete
$\theta_n$; CH11 uses continuous $\theta(t)$). Mitigation: pick CH11's notation
as canonical, rewrite CH04/CH05's derivations to match it *before* merging,
then merge.

**Risk C: losing the CH02 default-tree → BS derivation.**
That derivation is actually quite nice — it's the Donsker-style route to BS
that the rest of the guide then short-circuits via Itô. I would keep it but
shrink it: old CH02 §2.8 currently runs ~170 lines; a one-page summary
pointing to the Itô-route derivation in CH06 would preserve the intuition
without duplicating the derivation.

**Risk D: reader cross-linking breaks.**
The guide is meant for self-study; if a reader bookmarks "Chapter 8 §8.9 for
Feynman-Kac," that bookmark breaks. Mitigation: add anchor redirects or, at
minimum, a prominent "chapter X became chapter Y" mapping table in the
README's release notes.

### 6.4 Validation checklist for Phase B (per chapter)

For each new chapter N, verify:

- [ ] Every equation number `(N.k)` is unique within the chapter.
- [ ] Every prose reference to "Chapter M" is correct under the new numbering.
- [ ] Every symbol (e.g. `κ`, `θ`, `λ`, `W_t`) is used consistently with its
  prior introduction.
- [ ] No topic is *defined* in chapter N and *used* in chapter M < N.
- [ ] Every figure referenced is still reachable under its existing filename
  (or has been renamed consistently in `build_figures.py`).
- [ ] The chapter's Key Takeaways and Reference Formulas appendix reflect
  only content that appears in *this* chapter (no residual cross-chapter
  formulas left behind).

### 6.5 Estimated effort

- CH03 (stoch-calc merger): 4–6 hours. Largely literal lifts.
- CH04 (FK merger): 3–4 hours.
- CH05 (measure change merger): 4–5 hours. Most delicate integration.
- CH06/CH07/CH08 (split of old CH06): 6–8 hours total.
- CH09 (risk, trim FK intrusion): 2 hours.
- CH10 (MC/paths): 2 hours.
- CH11 (calibration trim): 2 hours.
- CH12 (short-rate merger): 6–8 hours. **Biggest single task.**
- CH13 (rate derivatives): 3 hours.
- CH14/15 (capstone updates): 2 hours.
- README + cross-reference sweep: 2–3 hours.

**Total Phase B budget: ~35–45 hours of focused editing.**

---

## 7. Closing remark

The current guide has excellent content — every chapter I read has careful
derivations, a reader-respecting narrative voice, and genuinely original
pedagogical choices (the dual CRR parameterisations in CH02; the Donsker
argument for Ho-Lee in CH05; the explicit discrete-hedge P&L analysis in
CH06; the Jamshidian cross-reference in CH11). None of that is at risk in
this reorganisation. The problem is purely topological: the chapters were
assembled in the order that the source lecture notes arrived, not the order
a self-studier needs to encounter them.

After the reorganisation, the guide will have a single prerequisite spine
(CH01 → CH02 → CH03 → CH04 → CH05) that the reader can treat as a "first
half" of the course, followed by application chapters (CH06 onward) that
can be read in various orders depending on interest. That is what a
sophisticated self-study guide ought to look like, and it is within reach.
