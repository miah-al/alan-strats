# Quant Course — Arbitrage Pricing & Derivatives

A fifteen-chapter study guide covering arbitrage pricing, stochastic calculus,
equity derivatives, short-rate models, and rate derivatives. The guide is
written for a self-study reader who is comfortable with undergraduate
probability and real analysis and who wants a single coherent path from the
one-period binomial model through Heston and swaptions. Formulas are typeset
in LaTeX; baseline figures are regenerated from a single Python script and
live inline next to the concepts they illustrate.

---

## Table of Contents

### Part I — Discrete-Time Models

| # | Chapter | Description |
|---|---------|-------------|
| 1 | [One-Period Binomial](CH01-One-Period-Binomial.md) | Single-period FTAP, replication, indifference pricing. |
| 2 | [Multi-Period Binomial and the FTAP](CH02-Multi-Period-Binomial-and-FTAP.md) | Backward induction, CRR parameterisations, FTAP, American options. |

### Part II — Continuous-Time Models

| # | Chapter | Description |
|---|---------|-------------|
| 3 | [Stochastic-Calculus Primer (Brownian Motion, Itô, SDE Solutions)](CH03-Stochastic-Calculus-Primer.md) | BM construction, quadratic variation, Itô integrals, Itô's lemma, OU/GBM SDEs. |
| 4 | [Feynman-Kac and the SDE-PDE Bridge](CH04-Feynman-Kac.md) | FK zero-drift, discounting, state-dependent coefficients; martingale derivation. |
| 5 | [Measure Changes, Radon-Nikodym, and Girsanov](CH05-Measure-Changes-and-Girsanov.md) | RN derivative, density process, Girsanov, two-numeraire switching, T-forward measure. |

### Part III — Equity Derivatives

| # | Chapter | Description |
|---|---------|-------------|
| 6 | [Dynamic Hedging I — Self-Financing + Black-Scholes PDE](CH06-Dynamic-Hedging-I-BS-PDE.md) | Self-financing strategies, market price of risk, BS PDE and formula. |
| 7 | [Dynamic Hedging II — Greeks, Delta-Gamma, Vega, Dividends](CH07-Dynamic-Hedging-II-Greeks.md) | Delta-gamma hedging, vega, dividend-paying assets, put-call parity. |
| 8 | [Forwards, Futures, and the Black PDE](CH08-Forwards-Futures-Black-PDE.md) | Forward/futures pricing, Black PDE, Margrabe, convexity adjustment. |
| 9 | [Risk Measures — VaR, CTE, Coherent Risk](CH09-Risk-Measures-VaR-CTE.md) | VaR (historical/parametric/MC), CTE, coherent risk, Basel, backtesting. |
| 10 | [Monte Carlo and Path-Dependent Options](CH10-Monte-Carlo-and-Path-Dependent.md) | SLLN, GBM generator, forward-starting and barrier options, variance reduction. |

### Part IV — Interest-Rate Models

| # | Chapter | Description |
|---|---------|-------------|
| 11 | [Calibration — Lattices, Short Rates, Yield Curve](CH11-Calibration.md) | FTAP on lattices, RN on multinomial trees, rate-tree bootstrap, governance. |
| 12 | [Short-Rate Models — Vasicek, Ho-Lee, Hull-White, Affine](CH12-Short-Rate-Models.md) | Canonical Vasicek derivation, Ho-Lee, Hull-White, affine term structure. |
| 13 | [Rate-Derivative Applications — Swaps, CDS, Bond Options, Callables](CH13-Rate-Derivative-Applications.md) | IRS, par swap rate, CDS, callable bonds, bond options via T-forward measure. |

### Part V — Stochastic Vol & Rate Derivatives

| # | Chapter | Description |
|---|---------|-------------|
| 14 | [Heston Model (Stochastic Volatility)](CH14-Heston-Model.md) | Heston SDE, characteristic-function pricing, Feller condition, Fourier inversion. |
| 15 | [Caps, Floors, and Swaptions](CH15-Caps-Floors-Swaptions.md) | Caplets under T-forward measure, Black-76, swaptions under annuity measure. |

---

## Course Arc

```
Part I ── Discrete Time ──────────────────────────────────────
  CH01 One-Period Binomial
     │
     ▼
  CH02 Multi-Period Binomial + FTAP
     │
Part II ── Continuous Time ───────────────────────────────────
     ▼
  CH03 Stochastic-Calculus Primer  ◀── foundation for all that follows
     │
     ├────────────┐
     ▼            ▼
  CH04 FK      CH05 Measure Change / Girsanov
     │            │
     └─────┬──────┘
Part III ── Equity Derivatives ───────────────────────────────
           ▼
        CH06 BS PDE (Dynamic Hedging I)
           │
     ┌─────┼──────┬────────────┐
     ▼     ▼      ▼            ▼
  CH07   CH08    CH09         CH10
  Greeks Fut/Fwd Risk/VaR    Monte Carlo
     │
Part IV ── Interest-Rate Models ──────────────────────────────
     ▼
  CH11 Calibration ─▶ CH12 Short-Rate Models ─▶ CH13 Rate Derivatives
                           │
Part V ── Stoch Vol & Rate Derivatives ───────────────────────
                           ▼
                  CH14 Heston   CH15 Caps/Floors/Swaptions
```

CH03 is the single prerequisite spine: every chapter from CH04 onward rests on
its Itô calculus. CH05's Girsanov machinery is cited (not re-derived) by CH06,
CH08, CH12, and CH13. Vasicek is derived once, in CH12, and cross-referenced
elsewhere.

---

## Regenerating the Figures

```bash
pip install matplotlib numpy scipy
python docs/guide/build_figures.py
```

Writes baseline PNGs under `docs/guide/figures/`.
