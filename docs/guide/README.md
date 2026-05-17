# Course Overview

A sixteen-chapter study guide (Chapter 0 prerequisites + 15 numbered chapters) covering arbitrage pricing, stochastic calculus, equity derivatives, short-rate models, rate derivatives, stochastic volatility, and risk measures. The guide is written for a self-study reader who is comfortable with undergraduate probability and real analysis and who wants a single coherent path from a math refresher to a senior-quant-grade understanding of derivatives pricing and hedging. Formulas are typeset in LaTeX; baseline figures live inline next to the concepts they illustrate.

This is the V5 edition. Relative to V3:

- Chapter 0 added as a prerequisite math refresher (probability, stochastic processes, linear algebra, calculus/ODE, Jensen's inequality and the $\sigma^2/2$ drift correction).
- Utility theory and indifference pricing removed from Chapter 1. Pricing is derived from no-arbitrage and replication only; preferences are a tool for incomplete markets, not the spine of derivatives pricing.
- Greeks split into a dedicated Chapter 7 with a comprehensive visual atlas (delta, gamma, theta, vega, rho, vanna, volga, charm, speed, color, dollar-gamma, pin risk, gamma-scalping P&L).
- Risk Measures (Chapter 15) is the capstone, deliberately positioned at the end so it can draw on every prior chapter's machinery.
- Real-world case studies added throughout — Buffett's SPX puts, Petrobras ADR arb, Black Monday 1987 portfolio insurance, GameStop gamma squeeze, Volmageddon, negative WTI oil futures, March 2020 COVID vol surface, LTCM 1998, SVB collapse 2023, Archegos, the UK LDI mini-budget of 2022, and more.

---

## Course Map

### Prerequisites

| # | Chapter | Description |
|---|---------|-------------|
| 0 | Math Refresher | Probability essentials, Jensen + $\sigma^2/2$ drift correction, stochastic-process priming, linear algebra (Cholesky, PSD, spectral), calculus and ODE refresher. |

### Part I — Discrete-Time Models

| # | Chapter | Description |
|---|---------|-------------|
| 1 | One-Period Binomial: No-Arbitrage and Replication | Two-asset model, arbitrage definition, risk-neutral measure $\mathbb{Q}$ from no-arbitrage alone, replication recipe, European call. |
| 2 | Multi-Period Binomial and the FTAP | Backward induction, CRR parameterisations, FTAP, American options. |

### Part II — Continuous-Time Models

| # | Chapter | Description |
|---|---------|-------------|
| 3 | Stochastic-Calculus Primer | Brownian construction, quadratic variation, Itô integrals, Itô's lemma, OU/GBM SDEs, the Jensen gap and the $\sigma^2/2$ drift correction (§3.10.1a). |
| 4 | Feynman–Kac and the SDE–PDE Bridge | Feynman–Kac zero-drift, discounting, state-dependent coefficients; martingale derivation. |
| 5 | Measure Changes, Radon–Nikodym, and Girsanov | Radon–Nikodym derivative, density process, Girsanov, two-numeraire switching, T-forward measure. |

### Part III — Equity Derivatives

| # | Chapter | Description |
|---|---------|-------------|
| 6 | Dynamic Hedging — Self-Financing and the Black–Scholes PDE | Self-financing strategies, market price of risk, BS PDE and formula, discrete hedging, transaction costs. |
| 7 | Greeks | Delta-gamma hedging, vega, theta, rho, dividend-paying assets, put-call parity. The Greek visual atlas with vanna/volga/charm/speed/color/dollar-gamma/pin-risk figures. |
| 8 | Forwards, Futures, and the Black PDE | Forward and futures pricing, the Black PDE, Margrabe, convexity adjustment, Bachelier versus Black-76 (negative WTI case). |
| 9 | Monte Carlo and Path-Dependent Options | SLLN, GBM generator, forward-starting and barrier options, variance reduction (antithetics, control variates), Asians and autocallables. |

### Part IV — Stochastic Volatility

| # | Chapter | Description |
|---|---------|-------------|
| 10 | Heston Model (Stochastic Volatility) | The Heston SDE, characteristic-function pricing, the Feller condition, Fourier inversion, smile and skew, calibration. |

### Part V — Calibration and Interest-Rate Models

| # | Chapter | Description |
|---|---------|-------------|
| 11 | Calibration — Lattices, Short Rates, Yield Curve | FTAP on lattices, the risk-neutral measure on multinomial trees, rate-tree bootstrap, regularisation, governance. SPX vol-surface workflow case study. |
| 12 | Short-Rate Models — Vasicek, Ho–Lee, Hull–White, Affine | Canonical Vasicek derivation, Ho–Lee, Hull–White $\theta(t)$, affine term structure. Negative-rate regime case study. |
| 13 | Rate-Derivative Applications — Swaps, CDS, Bond Options, Callables | IRS, par swap rate, CDS, callable bonds, bond options via the T-forward measure. LTCM swap-spread arb and SVB duration case studies. |
| 14 | Caps, Floors, and Swaptions | Caplets under the T-forward measure, Black-76, swaptions under the annuity measure. UK LDI mini-budget and LIBOR-to-SOFR case studies. |

### Part VI — Capstone

| # | Chapter | Description |
|---|---------|-------------|
| 15 | Risk Measures — VaR, CTE, Coherent Risk | VaR (historical, parametric, Monte Carlo), CTE, the coherent risk axioms, the Basel evolution to FRTB ES, backtesting, P&L attribution, delta-gamma parametric VaR via Cornish–Fisher. Three failures of VaR (LTCM, Archegos, 2008). |

---

## Course Arc

```
Chapter 0 — Math Refresher (Jensen, sigma^2/2, MGF, Cholesky, ODE)
                  |  prerequisites only — every later chapter cites it
                  v
Part I — Discrete Time --------------------------------------
   Chapter 1: One-Period Binomial (no-arb, replication)
       |
       v
   Chapter 2: Multi-Period Binomial + FTAP
       |
Part II — Continuous Time -----------------------------------
       v
   Chapter 3: Stochastic-Calculus Primer  <-- foundation
       |
       +--------------+
       v              v
   Chapter 4: FK    Chapter 5: Girsanov / Measure Change
       |              |
       +------+-------+
Part III — Equity Derivatives -------------------------------
              v
       Chapter 6: BS PDE (Dynamic Hedging)
              |
       +------+-------------+
       v      v             v
   Chapter 7  Chapter 8   Chapter 9
   Greeks     Fwd/Fut     Monte Carlo
              Black PDE
                            |
Part IV — Stochastic Vol ------------------------------------
                            v
                    Chapter 10: Heston (smile, skew, calibration)
                            |
Part V — Calibration and Rates ------------------------------
                            v
   Chapter 11: Calibration --> Chapter 12: Short-Rate -->
   Chapter 13: Rate Derivatives --> Chapter 14: Caps/Floors/Swaptions
                            |
Part VI — Capstone ------------------------------------------
                            v
                    Chapter 15: Risk Measures (VaR, ES, FRTB)
                            | — uses every prior chapter's Greeks/dynamics
```

The spine. Chapter 3 is the single prerequisite for every chapter from Chapter 4 onward; its Itô calculus is the language. Chapter 5's Girsanov machinery is cited (not re-derived) by Chapters 6, 8, 12, and 13. Vasicek is derived once, in Chapter 12, and cross-referenced elsewhere. The $\sigma^2/2$ Jensen-gap intuition introduced in Chapter 0 (§0.2) and re-derived from the SDE side in Chapter 3 (§3.10.1a) recurs in every continuous-time chapter — it is the most reused single fact in the guide.
