# Quant Guide V5 — Reorganization & Trim Plan

**Date:** 2026-05-13
**Author:** Claude (compiled from 6 round-2 quant-review agents + 1 meta chapter-ordering agent + 3 round-1 error-finding agents)
**Scope:** Moderate verbosity trim (~30% reduction) + full reorganization including chapter-ordering changes
**Current size:** ~21,700 lines across 15 chapters
**Target size:** ~15,200 lines across 15 chapters (after reorg)

---

## 0. Decisions you need to confirm

Before I touch anything, please flag any of the following you want changed:

1. **Merge old CH06 + old CH07 into one "Dynamic Hedging" chapter.** Both open with identical orienting prose and share notation; splitting BS-PDE from the Greeks it generates is artificial.
2. ~~Split old CH14 (Heston) into two chapters~~ — **REVISED: keep Heston as one chapter.** After the heavy trim (3,611 → ~2,400 lines), it's still long but tells a unified story (model + calibration); splitting forces a chapter break inside one model's narrative.
3. **Move old CH09 (Risk Measures) to the END as new CH15 (capstone).** Risk uses every prior chapter's Greeks/dynamics; it's a natural cross-cutting close.
4. **Move old CH10 (Monte Carlo) up** to new CH08, so all *pricing methods* finish before risk and applications.
5. **Move old CH10 §10.4.3 (Euler-Maruyama / Milstein) → CH03** since it's SDE-discretisation theory, not MC-specific.
6. **Move old CH11 §11.5 (Governance / sociology) to an appendix** — it's a 50-line editorial that breaks the technical thread.
7. **Cut CH11 §11.0 (Motivation, ~3,500 words) to a 60-word paragraph in §11.1** — triple-redundant with CH02 §2.5 and CH05.
8. **Cut CH01 §10–§14 (multi-period material) and migrate to CH02** — currently duplicates CH02 §2.2–§2.3.

If any of these is a no-go, tell me which and I'll revise. If silent, I'll assume all 8 are green.

---

## 1. New chapter ordering

**Result: 15 → 14 chapters** (CH06+CH07 merge, no Heston split).

| New # | Chapter | Was | Notes |
|---|---|---|---|
| 1 | One-Period Binomial | CH01 | trimmed; §10-14 migrate to new CH02 |
| 2 | Multi-Period Binomial & FTAP | CH02 | absorbs CH01 §10-14 (CRR + CLT) |
| 3 | Stochastic-Calculus Primer | CH03 | absorbs CH10 §10.4.3 (Euler-M / Milstein) |
| 4 | Feynman-Kac | CH04 | trim; fold §4.9 into §4.10 |
| 5 | Measure Changes & Girsanov | CH05 | §5.1 cut 146→55 lines; fix probabilities-vs-state-prices wording |
| 6 | Dynamic Hedging (BS PDE + Greeks) | CH06+CH07 | **merged**; 4 acts: self-financing → BS PDE → closed-form Greeks → discrete/move-based hedging |
| 7 | Forwards, Futures, Black PDE | CH08 | merge §8.5+§8.6 into single Black-PDE derivation; rename ch09-* figures |
| 8 | Monte Carlo & Path-Dependent | CH10 | promoted up; Euler-M moves to CH03 |
| 9 | Heston Stochastic Volatility | CH14 | **single chapter**; heavy trim 3,611 → ~2,400 lines; calibration workflow generic parts → CH10/CH11 |
| 10 | Calibration | CH11 | §11.0 cut; §11.5 → appendix; absorbs Heston calibration workflow generics |
| 11 | Short-Rate Models | CH12 | §12.1 consolidated; §12.7.2.b (negative-rates saga) cut; rename ch04/05/11-* figures |
| 12 | Rate-Derivative Applications | CH13 | §13.9 PDE-vs-MC → new CH08; calibration pipeline → CH11 |
| 13 | Caps, Floors, Swaptions | CH15 | §15.5 Jamshidian collapsed to cross-ref of CH13 |
| 14 | Risk Measures: VaR, CTE, Coherent | CH09 | **moved to capstone**; fix Eq (9.25) factor of 8; fix Eq (9.26) placeholder; fix FRTB hypothetical/risk-theoretical swap |

---

## 2. Per-chapter changes (summary)

### New CH01 — One-Period Binomial (1,485 → ~1,000 lines, −33%)

- **Reorder:** §13 (FFT proof) → immediately after §8.4 (one-period FFT statement).
- **Move out:** §10, §10.1–10.2, §11, §11.1–11.4, §12, §14 → **new CH02**.
- **Cuts:** lines 7-9, 13-22, 25-33, 47-51, 63-69, 77-85, 101-107, 121-127, 138-146, 184-196, 213-219, 231-241, 263-273, 281-289, 303-317, 329-335, 363-375, 409-415, 427-435, 451-459, 481-483, 487-497 (whole §5.4, marked "transcription uncertain"), 505-509, 527/535/541, 553-563, 597-601, 613-629, 633, 666-676, 701-717, 731-735, 755-759, 773-781, 797-803, 833-851, 875-877, 895-897, 917-919, 960-966.
- **New:** 5–10 line bridge §9 → §13; closing paragraph after §13 pointing forward to CH02.

### New CH02 — Multi-Period Binomial & FTAP (805 → ~750 after CH01 imports, −30% before imports)

- **Reorder:** §2.5 (FTAP statement) → immediately after §2.1 (one-period review).
- **Imports from CH01:** §10–§14 (multi-period, calibration, CLT proof).
- **Cuts:** lines 5-13, 21/27-29, 35/39, 41/43, 55-57, 63, 67/101-103, 117-121, 131-133, 139-141, 147, 155-157, 169-171, 181, 203-205, 225/229-231, 245-249, 253-255, 275-277, 285-289, 295/301-303, 311-317, 335-339, 408-412, 426-446, 458/460/473/475, 494/496/498, 506-510, 522/524/526, 544-546, 578-582, 622-628, 648-652, 669/689/695-697, 724-739.
- **New:** §2.4.6 reconciling lattice parameterisations I and II (currently buried at line 382); short bridge between §2.7 (default) and §2.8 (American) framing both as "trees with more states than tradables."

### New CH03 — Stochastic-Calculus Primer (1,008 → ~700 lines, −30%)

- **Reorder:** §3.7 (Brownian moment calculations) → immediately before §3.5 (Itô integral). The moments are tooling for §3.5's worked integral and §3.6's isometry.
- **Imports from CH10:** §10.4.3 Euler-Maruyama / Milstein discretisation, as new §3.4A "Numerical schemes."
- **Cuts:** lines 5-9, 35-37, 55, 68, 86, 106, 122-124, 170-186 (compress), 203/215-216, 245-252 (compress), 265-277 (collapse mnemonics), 292/305-307, 318/341-354, 360, 366/436-438, 446-449, 467, 484, 503, 512, 542, 553-555, 602-609, 622/624, 660-662, 683-686, 726-728, 740-741, 779-791 (compress), 823, 839/841, 862-864, 874, 887/911-918, 962, 968-998 (consolidate summary+takeaways).
- **Cross-chapter trim:** §3.10.2 (OU/Vasicek) drastically reduced; integrated-rate moves to CH12; §3.11.1, §3.11.2 (drill problems) → problem-set appendix.
- **New:** §3.4.5 bridge from QV to Itô integral; §3.9.3 worked example for general Itô.

### New CH04 — Feynman-Kac (1,013 → ~670 lines, −34%)

- **Reorder:** fold §4.9 (integrating factor) into §4.10 as the proof device for §4.10.4.
- **Move out:** §4.11.1 BS preview → CH06 (Dynamic Hedging); §4.11.2 Vasicek preview → CH12.
- **Cuts:** lines 20-22, 53-63 (4 near-identical figure captions; keep 1), 76-110 (compress §4.2.3), 130/173-175, 214-229 (§4.3.6 micro-local — duplicate), 231-235 (§4.3.7 — restates intro), 247/257-261, 263-267 (§4.4.3 — duplicates §4.8.5), 308-312, 351-365 (merge §4.6.1 + §4.6.2), 438-449 (§4.7.3, §4.7.4), 510-533, 585-617, 621-724 (§4.9 — compress 100+ lines to 15), 759-771, 815/835/855/860-862, 866-906 (§4.11 — collapse to 15 lines), 910-950 (§4.12 — trim 20 takeaways to 10).
- **Fix:** §4.3.5 line 199 "constant + starts at zero" argument needs to invoke Doob-Meyer FV-part-starts-at-zero, not just "starts at zero."

### New CH05 — Measure Changes & Girsanov (1,015 → ~680 lines, −33%)

- **Reorder:** within §5.4, move §5.4.4 (P→Q) to a sidebar after §5.4.1 (canonical reader hook).
- **Cuts (biggest target — §5.1 is 146 lines for one example):**
  - lines 9-15, 22-26 (verbose setup), 42-46, 68-74 (paragraph walk-through of ratio behaviour at ω₁, ω₁₀, ω₇), 81-96 (§5.1.3 entire — "implied r per state" — cut subsection), 113-119 (rewrite §5.1.4 to fix probabilities-vs-state-prices inconsistency), 140-146.
  - 153-170, 181-184, 213-216/232-234, 256/266-268, 290-310 (Itô-product-rule re-derivation), 354-362, 376-388 (Novikov/Kazamaki), 410-412/444-445, 502-505, 562-567, 604-608, 610-619 (§5.5.5 entire — duplicate recap), 705-708/723-725 (merge §5.6.4/5/6), 799-818 (merge §5.7.4/5/6), 821-882 (§5.8 — cut prose subsections, keep §5.8.6 table), 887-902 (trim 13 takeaways to 8).
- **New:** explicit declarative sentence in §5.1.4 — "The three columns are unnormalised Arrow-Debreu state prices, not probability weights" — placed before the table.
- **Fix:** rename `figures/ch03-asset-states.png` and `figures/ch03-rn-density.png` references (CH04/CH05 figures are mis-prefixed `ch03-`); rename `figures/ch08-heat-analogy.png` (CH04 reference, mis-prefixed `ch08-`).

### New CH06 — Dynamic Hedging (MERGED CH06+CH07, total 3,978 → ~2,400 lines, −40% net)

- **Structure:** 4 acts.
  - **Act 1 — Self-financing portfolio** (old §6.1, §6.2, §6.3).
  - **Act 2 — Market price of risk & generalised BS PDE** (old §6.4, §6.5, §6.6).
  - **Act 3 — Closed-form Greeks** (old §6.7, §6.7A, §6.8, §6.9, §6.9A + old CH07 §7.1, §7.3, §7.4 dividends, §7.6 put-call parity).
  - **Act 4 — Discrete & move-based hedging** (old §6.10, §6.11, §6.12 + old CH07 §7.2, §7.5 transaction costs).
- **Cuts in old CH06:** lines 42-52, 80-99, 118-135, 159-187 (Itô lemma review — CH03), 211-250 (§6.1.5 completeness meditation), 268-304, 332-366, 392-404, 440-449, 480-502, 552-562 (duplicate worked example), 624-679 (§6.4 — keep 2 of 6 commentary paragraphs), 692-698/740-758, 760-845 (§6.5 P&L sidebar appears 3x — keep one canonical), 887-956, 981-991, 1041-1064, 1180-1195, 1212-1242 (§6.8 sanity check — 45→12 lines), 1253-1331 (§6.9 quadratic — 80→30 lines), 1357-1416 (§6.9A — compress Gaussian-density mechanics to footnote), 1431-1523 (§6.10 + §6.10.1 — keep Q-dynamics, cut FTAP repeat), 1538-1606, 1622-1629, 1650-1668, 1685-1776 (§6.11.6 — 90→20 lines; collapse 3 variance-swap framings to 1), 1841-1978.
- **Cuts in old CH07:** lines 767-846 (§7.2.7 — duplicates new CH06 act 4), 848-938 (§7.2.8 gamma-scalping — keep 20 lines as "trading the VRP"), 1014-1021 (§7.2.9 — duplicates §7.1 catalogue), 1196-1210 (§7.3.3 — compress), 1559-1569 (§7.4.7 forward-reformulation — duplicate of CH08 §8.4), 1622-1632, 1684-1712, 1759-1807 (Leland — keep eq 7.69 + magnitude estimate, cut history), 1809-1811 (empty stub §7.5.5), **1979-1985 (empty stubs §7.7-§7.9 — replace with substantive content; see below).**
- **Fixes:**
  - Old CH07 has duplicate eq tags 7.59–7.68 across §7.4 and §7.6 (10 collisions). Renumber the parity block in new "Act 3."
  - Old CH07 line 1420 numerical claim "2 per dollar at 1 hour to expiry" is wrong (≈0.8 by direct calc).
  - Old CH06 §6.13 and §6.14 are empty stubs — fill with 8-bullet Key Takeaways + reference-formulas table.
  - Old CH07 §7.7, §7.8, §7.9 are empty stubs — fold dollar-Greeks into Act 3, fill takeaways + formulas.
- **New:** "Trading the variance risk premium" inset (20 lines) inside Act 4, absorbed from old §7.2.8.

### New CH07 — Forwards, Futures, Black PDE (1,819 → ~1,200 lines, −34%)

- **Reorder:** merge old §8.5 + §8.6 into a single "Black PDE — hedge and Feynman-Kac derivations" section. Collapse old §8.8 (Bachelier) + §8.9 (OU/Samuelson) into one "Closed-form examples" section with two subsections.
- **Cuts:** lines 152-189 (compress forward-value/parity restatements; convert cost-of-carry bullets to 4-row table), 528-537 (§8.5.2 restates §8.5.1), 596-669 (§8.5.5, §8.5.6 — duplicates §8.6), 707-723, 974-1011 (§8.8.3 reading — 37→12 lines), 1098-1118, 1147-1209 (§8.9.5–§8.9.7 — keep one HJM pointer), 1430-1529 (§8.10.7, §8.10.8, §8.10.10 — compress Margrabe analogies), 1638-1706 (§8.11.5, §8.11.7 — convexity-adjustment commentary).
- **Fix:** rename 5 figures with `ch09-*` prefix → `ch08-*` (ch09-forward-term.png, ch09-samuelson-ou.png, ch09-margrabe.png, ch09-margrabe-correlation.png, ch09-fut-fwd-basis.png).

### New CH08 — Monte Carlo & Path-Dependent (675 → ~470 lines, −30%)

- **Reorder:** no change (current §10.1–§10.10 is well-ordered).
- **Move out:** §10.4.3 (Euler-M / Milstein) → new CH03. §10.6.7 Heston simulation-scheme commentary stays.
- **Cuts:** lines 172-201 (§10.4.3 to be moved), 246-250 (compress §10.5 closers), 374-402 (§10.6.7 — repeated framing), 482-490 (compress mixture-variance), 528-534 (cost-matched antithetic comparison), 592-606 (§10.8.4 — compress IS/strat/Sobol/MLMC survey to bulleted "further reading").
- **Fix:** 3 ASCII figure-placeholder comments at lines 228, 400, 494 reference `figures/ch02-*.png` — rename to `figures/ch10-*.png`.

### New CH09 — Heston Stochastic Volatility (single chapter, 3,611 → ~2,400 lines, −34%)

- **Reorder:**
  - Move §14.4 (implied vol motivation) above §14.2 (Feller) — empirical "why" before mathematical "when."
  - Consolidate §14.10 + §14.10A + §14.10B + §14.10C into one "Limits, alternatives, extensions" section (drop §14.10C; it's a duplicate summary).
- **Cuts in part 1 (model & pricing):** lines 66-146 (1987 crash preamble), 215-310 (compress "what implied vol means"), 773-851 (Feller commentary), 853-952 (compress QE/Broadie-Kaya to 25 lines), 987-1031 (variance-risk-premium restated 3x), 1068-1138, 1156-1196, 1215-1255, 1296-1342 (3 versions of ρ-skew intuition), 1371-1462 (discretisation bias / pictures), 1480-1518, 1558-1598, 1634-1726 (Riccati narrative), 1754-1845, 1882-2128 (Fourier-inversion history — 150 lines).
- **Cuts in part 2 (calibration & extras):** lines 2143-2316 (calibration narratives), 2336-2386, 2402-2530 (workflow stages — move generics to CH11), 2548-2640 (variance-swap history), 2670-2705, 2746-2822, 2832-2975 (worked example commentary — 145→65), 2981-3152 (3 blind spots — 170→70), 3155-3303 (§14.10A/B — keep tables, cut paragraphs), 3306-3360 (§14.10C summary — **delete entirely**), 3395-3425, **3528-3603 (Appendix B Q&A — delete entirely; duplicate of takeaways)**.
- **Move out:** lines 2387-2532 (generic calibration workflow — L-M, IV-RMS vs price-RMS, SVI prefit) → CH10 (Calibration). Leave a 15-line "Heston-specific calibration notes" subsection here.
- **Net:** stays as ONE chapter but reads as two clean acts (model+pricing → calibration+extras) within it.

### New CH11 — Calibration (525 → ~360 lines, −31%)

- **Reorder:** absorb §11.0 motivation into §11.1's opening (60-word paragraph).
- **Move out:** §11.5 (Governance) → Appendix A "Calibration Governance."
- **Imports:** Heston calibration workflow from new CH10 (~150 lines).
- **Cuts:** lines 3-33 (§11.0 entire — restates FTAP from CH02/CH05; replace with 60-word opener), 13-14, 129-135 (compress §11.1.4 closing 4 paragraphs to 1), 362, 380-429 (§11.5 — move to appendix).
- **Fix:** line 21 says "the long yield identifies the ratio σ²/(2κ)" — should be σ²/κ². Line 438 Takeaway #6 contradicts itself; rewrite.
- **Fix:** rename `figures/ch04-bond-tree-recover.png` → `figures/ch11-bond-tree-recover.png`.

### New CH12 — Short-Rate Models (2,168 → ~1,500 lines, −31%)

- **Reorder:** consolidate §12.1 main + §12.1.1 + §12.1.2 into one tighter sub-flow (the "short rate is not traded" thesis appears 5 times currently — keep one statement).
- **Cuts:** lines 36-108 (§12.1 prose — 70 lines philosophical framing → 15 lines), 110-164 (§12.1.1 — 55-line non-uniqueness derivation that triplicates the same point; replace with 6-line callback to CH11 §11.3), 166-204 (§12.1.2 — cut numeraire-change preview rhetoric), 255-283 (§12.2.1 — 30 lines "continuous time is a tool not ontology" → 5 lines), 446-469 (§12.3 — half-life / negative-rates restated 3 places), **1911-1962 (§12.7.2.b historical-context / negative-rates saga — 52 lines; CUT entirely or compress to 8 lines)**, 1964-1982 (§12.7.3 — duplicates §12.8), 750-852 (§12.3.4 closed-form bond — compress 100→70 lines), 1402-1816 (§12.6 Hull-White — calibration discussion §12.6.4 duplicates CH11 §11.3; trim).
- **CRITICAL FIX:** line 2158 — Vasicek convexity row in §12.9 table says "bounded growth"; correct value is "linear growth" (Cₜ(T) ~ σ²/(2κ²)·(T−t) asymptotically).
- **Fix:** rename 7 mis-prefixed figures:
  - `ch04-vasicek-paths.png` → `ch12-vasicek-paths.png`
  - `ch11-bond-surface.png` → `ch12-bond-surface.png`
  - `ch11-affine-coefficients.png` → `ch12-affine-coefficients.png`
  - `ch11-vasicek-shapes.png` → `ch12-vasicek-shapes.png`
  - `ch05-hw-paths.png` → `ch12-hw-paths.png`
  - `ch05-zcb-curve.png` → `ch12-zcb-curve.png`
  - `ch05-theta-vs-fwd.png` → `ch12-theta-vs-fwd.png`
- **Fix:** line 1620 misleading claim "reasonable κ implies long-bond duration cap 2–10 years"; empirical 30y mod-durations are 15–20y. This is a *model artefact* of Vasicek with constant θ, not an empirical fact.

### New CH13 — Rate-Derivative Applications (1,946 → ~1,300 lines, −33%)

- **Reorder:** 13.1 → 13.2 (swaps) → 13.4 (CDS) → 13.3 (callable bonds) → 13.6 (bond options) → 13.7 (Jamshidian) → 13.8 (multi-factor) → 13.10/11. Pairs "linear / model-light" (swaps + CDS) and "model-dependent" (callable + bond options).
- **Move out:** §13.9 (PDE vs MC) → new CH08; §13.7.5 (calibration pipeline, lines 1403-1423) → CH11; §13.8.5 (SABR-on-rates, lines 1588-1625) → CH14.
- **Cuts:** lines 107-124 (GDP/notional anecdote), 184-217 (verbose worked numbers + OIS digression), 568-610 (Acme example), 720-732, 760-826, 840-867, 897-920, 1006-1036, 1080-1094, 1130-1140, 1185-1240, 1395-1402, 1648-1759 (§13.9 to be moved).

### New CH14 — Caps, Floors, Swaptions (734 → ~520 lines, −29%)

- **Reorder:** move §15.6 (annuity-measure swaption) ahead of §15.5 (Jamshidian/affine); demote §15.5 to a 20-line "historical alternative" subsection inside §15.6.
- **Move out:** §15.5 entire Jamshidian-route swaption pricing (currently duplicates CH13 §13.7.4) → cross-reference CH13.
- **Cuts:** lines 9-16, 89-92, 121-122, 135-148, 207-209, 218-226, 271-275, 312-325, 412-413, 472-478, 565-572, 611-613, 636-639, 651-656, 276-298 (Vasicek-Black bond-put inset duplicates CH13 §13.6).

### New CH15 — Risk Measures (capstone) (814 → ~600 lines, −26%)

- **Reorder:** §9.5 (Coherent framework) → before §9.6 (Basel) — axioms before regulatory implementation. Renumber: Coherent becomes §9.5, Basel becomes §9.6.
- **CRITICAL FIXES (these are math errors, not trim):**
  - **Eq (9.25) line 514:** missing factor of 8. Correct: `m₃ = 8·tr((ΓΣ)³) + 6·δᵀΣΓΣδ`.
  - **Eq (9.26) line 519:** is literally a placeholder "`m₄ = 3 m₃ · m₂ / (m₁ · (something complicated))…`". Replace with the correct closed form: `m₄ = 12·tr((ΓΣ)⁴) + 48·δᵀ(ΣΓ)²Σδ + 3·(σ²_P)²`.
  - **§9.10.1 lines 423-427:** swaps FRTB definitions of "hypothetical" and "risk-theoretical" P&L. Per BCBS d352:
    - *Hypothetical P&L* = front-office full-revaluation of frozen positions under actual market moves.
    - *Risk-theoretical P&L* = risk-engine full-revaluation of frozen positions under the risk model's market data.
    - The Taylor-via-Greeks construct is *Greek-attributed* P&L — not the FRTB risk-theoretical series.
  - **§9.3 line 100 Student-t₃ CTE arithmetic:** the "4.19" CTE figure doesn't match either standard convention (scaled or unscaled t₃). Recompute or pick one convention cleanly.
- **Cuts:** lines 84-88, 100, 130-136, 174-195 (regulatory history → 1 paragraph + 4-row table), 218-219, 239-254 (§9.6.3 convex risk measures — author flags "beyond scope"; cut), 433-441, 463-479, 552-558, 597-605, 609-647 (§9.14 — compress to 15-line checklist).
- **Fix:** rename `figures/ch07-var-cte.png` and `figures/ch07-var-cte-compare.png` (CH09 figures mis-prefixed `ch07-`) → `ch09-var-cte.png` (or `ch15-` after the chapter move).

---

## 3. Critical correctness fixes (must do regardless of reorg)

These are math/logic errors flagged by round-1 reviewers. They will be fixed in the same pass:

| Chapter | Line | Issue | Fix |
|---|---|---|---|
| CH05 | 117 | "three pricing measures" called both probabilities and Arrow-Debreu prices | Pick one (state prices); add explicit declarative sentence |
| CH05 | 555/573 | Eq (5.35) and (5.35b) share the same number | Renumber |
| CH06 | 1420 | Numerical claim "2 per dollar at 1h to expiry" inconsistent with formula | Recompute (≈0.8) |
| CH06 | 1981, 1985 | §6.13 and §6.14 empty stubs | Fill (or remove headers); planned content listed in plan |
| CH07 | 1809-1811 | §7.5.5 empty stub | Remove header |
| CH07 | 1979-1985 | §7.7-§7.9 empty stubs | Fold §7.7 into §7.3; fill §7.8 + §7.9 |
| CH07 | 1545/1821 etc | Eq tags 7.59-7.68 duplicated across §7.4 and §7.6 | Renumber parity block |
| CH09 | 514 | Eq (9.25) missing factor of 8 | `m₃ = 8·tr((ΓΣ)³) + 6·δᵀΣΓΣδ` |
| CH09 | 519 | Eq (9.26) is a placeholder | Replace with closed form |
| CH09 | 423-427 | §9.10.1 swaps FRTB hypothetical vs risk-theoretical | Rewrite per BCBS d352 |
| CH11 | 21 | Says long yield identifies σ²/(2κ); correct is σ²/κ² | Fix |
| CH11 | 438 | Takeaway #6 contradicts itself on identifiability | Rewrite |
| CH12 | 2158 | Vasicek convexity row says "bounded growth" | "linear growth" |
| CH12 | 1620 | Implies real long-bond durations are 2-10y | Clarify model artefact |

Plus 21 mis-prefixed figure filename references (listed in per-chapter sections).

---

## 3a. Real-world examples to add (NEW)

Per-chapter, add 1–2 short "case study" boxes (~40–80 lines each, with one matching figure where natural) tying the math to a real market event. These count *against* the trim budget — but the cuts in §2 already leave headroom (we're targeting 30% reduction; adding ~700 lines of case studies still nets ~26% reduction).

| Chapter | Case study | Why it fits |
|---|---|---|
| CH01 | Buffett's 2007–2026 SPX put sale ($4.5B premium for ~$36B notional) | Live long-dated European put; one-period intuition vs reality |
| CH02 | ADR/ordinary arbitrage on Brazilian Petrobras (PBR vs PETR4) | Concrete violation of FTAP creates a free lunch; tracked daily |
| CH03 | Why volatility scales as √Δt — VIX 1-day vs 1-year quotes | Direct Brownian-scaling check from market data |
| CH04 | Vasicek bond pricing recovered from 2024 Treasury curve | Feynman-Kac formula plugged into actual short-rate history |
| CH05 | FX triangular arbitrage (EUR/USD × USD/JPY vs EUR/JPY) | Measure change as numeraire change; bid-ask edge as RN-density tilt |
| **CH06 Dynamic Hedging** | **(a)** Black Monday 1987 — portfolio-insurance dynamic hedge cascade. **(b)** GameStop Jan 2021 — gamma squeeze as forced delta-hedge by market makers. **(c)** "Volmageddon" Feb 2018 — XIV liquidation via short-vol gamma | Three textbook failure modes of delta hedging: discrete rebalance, gamma blowup, vega/vol-of-vol blowup |
| CH07 Fwd/Fut/Black | Negative WTI oil futures, April 20 2020 — settled at −$37.63 | Bachelier (normal) vs Black-76 (log-normal): only the former is well-defined at negative prices. Live evidence of model choice mattering |
| CH08 Monte Carlo | Asian commodity options & autocallable equity notes | Path-dependent products that *must* be MC-priced; convergence/variance reduction with real numbers |
| CH09 Heston | (a) 1987 crash → birth of vol skew (Rubinstein). (b) March 2020 COVID — vol surface spiking from 12 to 80, smile flattening as panic-driven. (c) Feb 2018 "Volmageddon" mark-to-market on a Heston desk | Origin and stress tests of the model. Skew is *not* a bug |
| CH10 Calibration | SPX daily vol-surface calibration workflow — actual L-M iteration count, RMS residuals, parameter stability across days | What "calibrate at 8am, hedge from 9:30" really means |
| CH11 Short-Rate | (a) Negative Eurozone rates 2014–2022 — why Vasicek (allows negative) vs CIR (doesn't) actually matters. (b) 2023 Fed hiking cycle — Hull-White θ(t) bootstrap from the actual fed funds curve | Model-choice driven by real-world rate regimes |
| CH12 Rate Derivs | (a) Long-Term Capital Management 1998 — swap spreads, off-the-run/on-the-run, leverage. (b) SVB collapse March 2023 — duration mismatch + held-to-maturity accounting | Bond/IRS exposure managed wrong; rate risk that wasn't priced |
| CH13 Caps/Floors/Swaptions | (a) UK LDI / "mini-budget" Sept 2022 — pension swaption book forced unwind as gilt yields spiked. (b) LIBOR → SOFR transition Jun 2023 | Sovereign-rate volatility breaking a hedge book; the largest contract-rewrite in derivatives history |
| **CH14 Risk Measures (capstone)** | (a) LTCM 1998 — VaR understated leverage-amplified tails. (b) Archegos March 2021 — single-name concentration not reflected in cross-margined VaR. (c) 2008 — Basel I VaR missed correlated-default tail; Basel III moves to ES | Three real failures of VaR; motivates coherent measures and the capstone framing |

Format per case study (~50 lines):
- 3-line header "case study" with title and date.
- 1 paragraph context (what happened, in plain English).
- 1 paragraph reading it through the chapter's math (which formula breaks, which Greek explodes, which assumption fails).
- 1 paragraph lesson (what the practitioner takes away).
- Optional figure (1 PNG per study where it helps; not all need one).

**Estimated additional content:** ~700 lines across 14 chapters. Net target after trim+examples: ~15,900 lines (from 21,700 today), i.e. ~27% net reduction.

---

## 4. Things explicitly NOT changed

- **Mathematical content:** every formula, every theorem, every worked example preserved verbatim.
- **Figures (PNGs):** no figures generated or removed; only rename references with wrong chapter prefix.
- **TikZ figures:** the 16 new TikZ figures (replacing old ASCII art) all stay.
- **README.md and the cover/preamble files:** untouched.
- **Strategy / dash_app / db / etc. code:** out of scope.

---

## 5. Execution plan once you approve

1. Create a git branch `guide-v5-reorg` from current `master`.
2. Apply per-chapter cuts/moves in order CH01→CH15 (cut first, then move sections, then renumber).
3. Rename mis-prefixed figure references (search/replace).
4. Apply math fixes from §3.
5. Run `python docs/guide/_make_pandoc_pdf.py` to rebuild.
6. Verify PDF size dropped ~30% and no LaTeX errors.
7. Diff stats per chapter so we see the cuts are roughly on target.
8. Open a PR or commit (your call).

Estimated wall-clock: ~30-60 min of edits if I go sequentially.

---

## 6. Outstanding round-1 reviews

Two round-1 error-finding agents are still running (CH01-03 and CH13-15). When they complete I'll add any new math errors they find to §3 above. The reorg plan in §1-2 doesn't depend on those reviews.
