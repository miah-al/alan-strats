# Quant Course — Arbitrage Pricing & Derivatives

A sixteen-chapter study guide (Chapter 0 prerequisites + 15 numbered chapters)
covering arbitrage pricing, stochastic calculus, equity derivatives, short-rate
models, rate derivatives, stochastic volatility, and risk measures. The guide
is written for a self-study reader who is comfortable with undergraduate
probability and real analysis and who wants a single coherent path from a
math refresher to a senior-quant-grade understanding of derivatives pricing
and hedging. Formulas are typeset in LaTeX; baseline figures are regenerated
from a single Python script and live inline next to the concepts they
illustrate.

This is the **V5** edition. Relative to V3:
- **Chapter 0 added** as a prerequisite math refresher (probability, stochastic
  processes, linear algebra, calculus/ODE, Jensen's inequality and the $\sigma$²/2
  drift correction).
- **Utility theory and indifference pricing removed from Chapter 1.** Pricing
  is derived from no-arbitrage and replication only; preferences are a tool
  for incomplete markets, not the spine of derivatives pricing.
- **Greeks split into a dedicated Chapter 7** with a comprehensive visual atlas
  (delta, gamma, theta, vega, rho, vanna, volga, charm, speed, color,
  dollar-gamma, pin risk, gamma-scalping P&L).
- **Risk Measures (Chapter 15) is the capstone**, deliberately positioned at
  the end so it can draw on every prior chapter's machinery.
- **Real-world case studies** added throughout — Buffett's SPX puts, Petrobras
  ADR arb, Black Monday 1987 portfolio insurance, GameStop gamma squeeze,
  Volmageddon, negative WTI oil futures, March 2020 COVID vol-surface,
  LTCM 1998, SVB collapse 2023, Archegos, UK LDI mini-budget 2022, and more.

---

## Table of Contents

### Prerequisites

| # | Chapter | Description |
|---|---------|-------------|
| 0 | [Math Refresher](Chapter-0-Math-Refresher.md) | Probability essentials, Jensen + $\sigma$²/2 drift correction, stochastic-process priming, linear algebra (Cholesky, PSD, spectral), calculus & ODE refresher. |

### Part I — Discrete-Time Models

| # | Chapter | Description |
|---|---------|-------------|
| 1 | [One-Period Binomial: No-Arbitrage and Replication](Chapter-1-One-Period-Binomial.md) | Two-asset model, arbitrage definition, risk-neutral measure $\mathbb{Q}$ from no-arbitrage alone, replication recipe, European call. |
| 2 | [Multi-Period Binomial and the FTAP](Chapter-2-Multi-Period-Binomial-and-FTAP.md) | Backward induction, CRR parameterisations, FTAP, American options. |

### Part II — Continuous-Time Models

| # | Chapter | Description |
|---|---------|-------------|
| 3 | [Stochastic-Calculus Primer](Chapter-3-Stochastic-Calculus-Primer.md) | BM construction, quadratic variation, Itô integrals, Itô's lemma, OU/GBM SDEs, Jensen's gap and the $\sigma$²/2 drift correction (§3.10.1a). |
| 4 | [Feynman-Kac and the SDE-PDE Bridge](Chapter-4-Feynman-Kac.md) | FK zero-drift, discounting, state-dependent coefficients; martingale derivation. |
| 5 | [Measure Changes, Radon-Nikodym, and Girsanov](Chapter-5-Measure-Changes-and-Girsanov.md) | RN derivative, density process, Girsanov, two-numeraire switching, T-forward measure. |

### Part III — Equity Derivatives

| # | Chapter | Description |
|---|---------|-------------|
| 6 | [Dynamic Hedging — Self-Financing + Black-Scholes PDE](Chapter-6-Dynamic-Hedging.md) | Self-financing strategies, market price of risk, BS PDE and formula, discrete hedging, transaction costs. |
| 7 | [Greeks](Chapter-7-Greeks.md) | Delta-gamma hedging, vega, theta, rho, dividend-paying assets, put-call parity. **Greek visual atlas** with vanna/volga/charm/speed/color/dollar-gamma/pin-risk figures. |
| 8 | [Forwards, Futures, and the Black PDE](Chapter-8-Forwards-Futures-Black-PDE.md) | Forward/futures pricing, Black PDE, Margrabe, convexity adjustment, Bachelier vs Black-76 (negative WTI case). |
| 9 | [Monte Carlo and Path-Dependent Options](Chapter-9-Monte-Carlo-and-Path-Dependent.md) | SLLN, GBM generator, forward-starting and barrier options, variance reduction (antithetics, control variates), Asians and autocallables. |

### Part IV — Stochastic Volatility

| # | Chapter | Description |
|---|---------|-------------|
| 10 | [Heston Model (Stochastic Volatility)](Chapter-10-Heston-Model.md) | Heston SDE, characteristic-function pricing, Feller condition, Fourier inversion, smile/skew, calibration. |

### Part V — Calibration and Interest-Rate Models

| # | Chapter | Description |
|---|---------|-------------|
| 11 | [Calibration — Lattices, Short Rates, Yield Curve](Chapter-11-Calibration.md) | FTAP on lattices, RN on multinomial trees, rate-tree bootstrap, regularisation, governance. SPX vol-surface workflow case study. |
| 12 | [Short-Rate Models — Vasicek, Ho-Lee, Hull-White, Affine](Chapter-12-Short-Rate-Models.md) | Canonical Vasicek derivation, Ho-Lee, Hull-White $\theta$(t), affine term structure. Negative-rate regime case study. |
| 13 | [Rate-Derivative Applications — Swaps, CDS, Bond Options, Callables](Chapter-13-Rate-Derivative-Applications.md) | IRS, par swap rate, CDS, callable bonds, bond options via T-forward measure. LTCM swap-spread arb and SVB duration case studies. |
| 14 | [Caps, Floors, and Swaptions](Chapter-14-Caps-Floors-Swaptions.md) | Caplets under T-forward measure, Black-76, swaptions under annuity measure. UK LDI mini-budget and LIBOR$\to$SOFR case studies. |

### Part VI — Capstone

| # | Chapter | Description |
|---|---------|-------------|
| 15 | [Risk Measures — VaR, CTE, Coherent Risk](Chapter-15-Risk-Measures-VaR-CTE.md) | VaR (historical/parametric/MC), CTE, coherent risk axioms, Basel evolution to FRTB ES, backtesting, P&L attribution, delta-gamma parametric VaR via Cornish-Fisher. Three failures of VaR (LTCM, Archegos, 2008). |

---

## Course Arc

```
Chapter 0 ── Math Refresher (Jensen, σ²/2, MGF, Cholesky, ODE)
                  │  prerequisites only — every later chapter cites it
                  ▼
Part I ── Discrete Time ──────────────────────────────────────
   Chapter 1: One-Period Binomial (no-arb, replication)
       │
       ▼
   Chapter 2: Multi-Period Binomial + FTAP
       │
Part II ── Continuous Time ───────────────────────────────────
       ▼
   Chapter 3: Stochastic-Calculus Primer  ◀── foundation
       │
       ├──────────────┐
       ▼              ▼
   Chapter 4: FK    Chapter 5: Girsanov / Measure Change
       │              │
       └──────┬───────┘
Part III ── Equity Derivatives ───────────────────────────────
              ▼
       Chapter 6: BS PDE (Dynamic Hedging)
              │
       ┌──────┼─────────────┐
       ▼      ▼             ▼
   Chapter 7  Chapter 8   Chapter 9
   Greeks     Fwd/Fut     Monte Carlo
              Black PDE
                            │
Part IV ── Stochastic Vol ────────────────────────────────────
                            ▼
                    Chapter 10: Heston (smile, skew, calibration)
                            │
Part V ── Calibration & Rates ────────────────────────────────
                            ▼
   Chapter 11: Calibration ─▶ Chapter 12: Short-Rate ─▶
   Chapter 13: Rate Derivatives ─▶ Chapter 14: Caps/Floors/Swaptions
                            │
Part VI ── Capstone ──────────────────────────────────────────
                            ▼
                    Chapter 15: Risk Measures (VaR, ES, FRTB)
                            │ — uses every prior chapter's Greeks/dynamics
```

**Spine.** Chapter 3 is the single prerequisite for every chapter from Chapter 4
onward; its Itô calculus is the language. Chapter 5's Girsanov machinery is
cited (not re-derived) by Chapters 6, 8, 12, and 13. Vasicek is derived once,
in Chapter 12, and cross-referenced elsewhere. The $\sigma$²/2 Jensen-gap intuition
introduced in Chapter 0 (§0.2) and re-derived from the SDE side in Chapter 3
(§3.10.1a) recurs in every continuous-time chapter — it is the most reused
single fact in the guide.

---

## Regenerating the Figures

```bash
pip install matplotlib numpy scipy
python docs/guide/build_figures.py
```

Writes baseline PNGs under `docs/guide/figures/`.

## Building the Full PDF

```bash
pip install pypandoc_binary
python docs/guide/_make_pandoc_pdf.py
```

Requires a working `xelatex` installation. Concatenates README + Chapter-0
through Chapter-15 in numeric order, runs pandoc $\to$ xelatex, writes
`docs/guide/pdf/Quant-Guide-Full.pdf`.
