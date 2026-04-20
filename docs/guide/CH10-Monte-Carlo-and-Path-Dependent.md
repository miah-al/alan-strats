# Chapter 10 — Monte Carlo, Path-Dependent, and Forward-Starting Options

This chapter is the simulation counterpart to the lattice pricing of Chapter 2 and the PDE-based pricing of Chapter 6. Closed-form formulas like Black–Scholes are beautiful but brittle: they cover a short list of payoffs (European calls, European puts, a handful of digital and barrier variants under continuous monitoring) written on a single-asset geometric Brownian motion with constant volatility. Every realistic trading desk deals daily with claims that lie outside that list — path-dependent payoffs (Asians, lookbacks, cliquets, autocallables), multi-asset baskets, stochastic-volatility models, jump-diffusions, local-volatility surfaces calibrated to a full implied-vol grid. For all of these, the pricing integral remains $V_0 = e^{-rT}\,\mathbb{E}^{\mathbb{Q}}[\varphi]$ but the analytical evaluation fails, and one must turn to numerical methods. Monte-Carlo simulation is the most general of these methods. It works in any dimension, handles arbitrary payoffs, and is embarrassingly parallel; its only costs are statistical noise and the need for careful variance management.

The chapter arc is narrow and deep rather than wide. We begin by motivating Monte Carlo from the perspective of high-dimensional numerical integration, where quadrature breaks down under the curse of dimensionality. The strong law of large numbers (SLLN) provides the mathematical license for sample-average estimation, and the central limit theorem gives the $M^{-1/2}$ error rate that governs how confidence intervals shrink with sample size. We then build the lognormal GBM path generator — properly derived this time, because Chapter 6 has already given us the Itô solution of the GBM SDE — and apply it to three classes of problem: European claims as a warm-up sanity check against Black–Scholes, forward-starting (cliquet) options as a case where iterated conditional expectation gives a closed form, and barrier options as the prototypical path-dependent payoff that forces a Monte-Carlo implementation. Along the way we encounter a characteristic issue of path-dependent MC — discretisation bias on between-grid events — and the Brownian-bridge correction that removes it. We close with variance-reduction techniques (antithetic variates, control variates) that every production pricer uses, as a bridge to the Heston Monte Carlo of Chapter 14.

A word about how this chapter sits in the prerequisite graph. Chapter 2 gave us lattice pricing and the CRR calibration; we will refer back to the lognormal GBM limit of that chapter as the starting point for the simulation engine. Chapter 6 gave us the Itô derivation of GBM, Girsanov's theorem (via Chapter 5) that fixes the drift under $\mathbb{Q}$ at the risk-free rate, and the Black–Scholes formula that we use as a closed-form benchmark. Everything in this chapter is downstream of that material. Nothing here feeds forward to the foundations; the chapter is a self-contained application, and a reader who has mastered through Chapter 6 can read Chapter 10 immediately without touching Chapters 7–9.

A note on scope. We cover the core Monte-Carlo toolkit — path simulation, sample-mean estimation, standard error, discretisation bias, and two of the canonical variance-reduction techniques. Topics we do not cover here include stratified sampling, importance sampling (beyond a conceptual mention), quasi-Monte-Carlo with low-discrepancy sequences, pathwise and likelihood-ratio Greek estimators, and the Longstaff–Schwartz regression-based scheme for American exotics. Those techniques are discussed briefly where they are natural extensions of the material and are otherwise left as pointers into the literature. The focus is on getting a working production-grade European and path-dependent pricer stood up; the reader who has the machinery presented here can read any of the variance-reduction or American-MC literature without further prerequisites.

---

## 10.1 Why Monte Carlo? Quadrature and the Curse of Dimensionality

The pricing formula $V_0 = e^{-rT}\,\mathbb{E}^{\mathbb{Q}}[\varphi(A_T,\{A_t\}_{t\le T})]$ is, at its core, an integral over the sample space of the underlying process. In low dimensions this integral can be evaluated by deterministic quadrature — trapezoidal, Simpson's, Gauss–Legendre, or one of the many higher-order schemes — with error scaling as $O(h^p)$ where $h$ is the mesh size and $p$ is the order of the quadrature. For $p=4$ (Simpson's rule), getting four-significant-figure accuracy on a smooth integrand requires $h\sim 10^{-1}$ or about $10$ grid points in one dimension. Quadrature is fast, deterministic, and the textbook first choice when the state space is small.

In high dimensions quadrature breaks down catastrophically. The number of grid points required scales as $N^d$, where $d$ is the number of independent stochastic factors and $N$ is the number of grid points per factor. For a daily-monitored one-year option on a single underlying, $d = 252$ (one Brownian increment per trading day); even using only $N=2$ grid points per dimension gives $2^{252}\approx 10^{75}$ total points, vastly more than any computer can enumerate. For a daily-monitored option on a basket of ten underlyings, $d = 2520$, and the number becomes utterly astronomical. This is the *curse of dimensionality*: deterministic integration techniques whose per-dimension cost is well-controlled nevertheless collapse in high dimensions because the total cost compounds multiplicatively.

Monte-Carlo integration escapes the curse by a simple statistical observation: the sample-mean estimator's error scales as $M^{-1/2}$, *regardless of the dimension of the state space*. For a fixed error tolerance we need a fixed number of paths, and the cost per path scales only linearly in the dimension — each path-step is an $O(d)$ computation. Total cost: $O(Md)$, compared to $O(N^d)$ for quadrature. The break-even dimension is usually between $d=4$ and $d=6$: below that, quadrature is faster; above it, Monte Carlo wins decisively. Since every realistic derivative-pricing problem with a daily or finer monitoring grid lives well above $d=6$, MC is the method of choice for everything except the cleanest European problems on a single underlying.

The flip side of dimension-insensitivity is that Monte Carlo is *statistical*: it produces random error bars, not deterministic error bounds. A practitioner always reports the MC estimate together with its sample standard error, and any downstream use of the estimate — hedging ratios, risk capital, P&L attribution — must account for the Monte-Carlo uncertainty. Deterministic methods produce exact-to-roundoff answers; MC produces confidence intervals. The gap closes as $M$ grows, but never to zero. For a risk manager, this means MC-based prices carry an intrinsic "simulation vega" that must be bounded below desk risk tolerances; for a trader, it means the first question on seeing an MC price is always "what's the standard error?"

Monte-Carlo simulation has a long intellectual history, pre-dating its application to finance by decades. The key idea — that high-dimensional integrals can be approximated by sample averages — was formalised by Metropolis, Ulam, and von Neumann at Los Alamos in the 1940s for neutron-transport calculations, and has since spread to essentially every quantitative discipline. In finance the method is particularly well-suited to derivatives pricing because every pricing formula under $\mathbb{Q}$ is literally an integral (a discounted expected payoff) and because the underlying state space — paths of a diffusion — is naturally high-dimensional. Once the risk-neutral measure $\mathbb{Q}$ is pinned down (by Girsanov, Chapter 5, and the market-price-of-risk shift of Chapter 6), the pricing problem collapses cleanly to "draw paths from $\mathbb{Q}$, evaluate the payoff on each, and average." The conceptual simplicity is matched by the implementation simplicity: modern Monte-Carlo pricers are some of the shortest useful programs in quantitative finance.

The engineering of a production Monte-Carlo pricer involves four distinct sub-problems:

1. **Path generation under $\mathbb{Q}$.** Given the chosen risk-neutral model — GBM, Heston, local-vol, jump-diffusion, etc. — produce paths whose law matches the specification. For GBM the exact lognormal increment of §10.4 gives a bias-free generator; for general SDEs one falls back on Euler–Maruyama or Milstein schemes with their associated discretisation biases.
2. **Variance reduction.** Reduce the sample variance so that fewer paths suffice to achieve a target confidence-interval width. Antithetic variates, control variates, stratified sampling, importance sampling, and quasi-random sequences each contribute.
3. **Path-dependent payoffs.** Many payoffs depend on the whole path: running maximum (lookback), running average (Asian), barrier-crossing indicator (knock-in/out), basket constraints. Efficient data structures and careful handling of between-grid events (Brownian-bridge correction for barriers) are central.
4. **Sensitivity estimation (Greeks).** Delta, gamma, vega, and other Greeks must come out of the same path sample, ideally with pathwise or likelihood-ratio estimators rather than finite-difference bump-and-reprice. We will touch on this briefly but not in depth.

The present chapter concentrates on items (1), (2), and (3). Item (4) — the art of Greek estimation by Monte Carlo — is an entire subdiscipline and appears as a cross-reference at the end of the chapter and in more detail within Chapter 14.

---

## 10.2 The Strong Law of Large Numbers

The mathematical foundation of Monte-Carlo integration is the strong law of large numbers, which says that sample averages almost surely converge to population expectations.

Let $X$ be a random variable on a probability space $(\Omega,\mathcal{F},\mathbb{P})$ with $\mathbb{E}[|X|] < +\infty$, and let $X^{(1)}, X^{(2)}, \dots, X^{(M)}$ be independent and identically distributed copies of $X$. Then

$$
\lim_{M\to +\infty}\; \frac{X^{(1)} + X^{(2)} + \cdots + X^{(M)}}{M} \;=\; \mathbb{E}[X] \qquad \text{(strong law, a.s.).}
\tag{10.1}
$$

The "almost surely" (a.s.) qualifier means that the set of paths along which convergence fails has $\mathbb{P}$-measure zero; for any actual realised sequence of draws the sample average converges. The strong law is the mathematical license for Monte-Carlo pricing: given enough i.i.d. draws from the payoff distribution under $\mathbb{Q}$, the sample average almost surely converges to $\mathbb{E}^{\mathbb{Q}}[\text{payoff}]$, which (times the discount factor) is the price.

A short philosophical aside on the $\mathbb{E}[|X|]<\infty$ hypothesis. Without finite mean the sample average may not converge at all; it can drift to infinity, oscillate, or behave chaotically. For option-pricing problems this is rarely a concern. Bounded payoffs — European puts are bounded by $K$, digital options by $1$, and European calls can be bounded in practice by truncating at far-OTM regions — automatically satisfy the condition. But for *ratios* of random variables, or for some stochastic-volatility models with heavy-tailed variance processes, the integrability check deserves attention. The canonical pathological example is the Cauchy distribution (a ratio of two independent Gaussians), for which the sample average has the same Cauchy distribution regardless of sample size; the Monte-Carlo method fails completely because the variance is infinite and the mean is not even well-defined in the usual sense.

Higher integrability buys strictly more. $L^2$ integrability (finite variance, $\mathbb{E}[X^2]<\infty$) gives the Central Limit Theorem:

$$
\sqrt{M}\,\bigl(\widehat{m}_M - \mathbb{E}[X]\bigr) \;\xrightarrow{d}\; \mathcal{N}\bigl(0,\;\mathbb{V}[X]\bigr),
\tag{10.2}
$$

where $\widehat{m}_M := (1/M)\sum_m X^{(m)}$ is the sample mean. The CLT is the basis for Monte-Carlo confidence intervals: for large $M$, $\widehat{m}_M$ is approximately normally distributed around $\mathbb{E}[X]$ with standard deviation $\sqrt{\mathbb{V}[X]/M}$, and we can bracket the unknown mean by a conventional $\widehat{m}_M \pm 1.96\,\widehat{\sigma}_{m_1}$ 95% interval. $L^4$ integrability ($\mathbb{E}[X^4]<\infty$) tightens the approximation further via the Berry–Esseen bound, which quantifies the rate at which the CLT distributional approximation becomes good.

In practice the check "does my payoff have finite variance under $\mathbb{Q}$?" is usually done by inspection: polynomially-growing payoffs on a lognormal underlying have finite moments of all orders, so European calls, puts, Asians, lookbacks, and barriers on GBM are all fine. The problem cases — which one should be aware of even if they do not arise in this chapter — are payoffs that involve *reciprocals* or *roots* of the underlying, payoffs on stochastic-volatility models near the Feller-condition boundary (see Chapter 14), and payoffs that are integrated over unbounded time horizons.

---

## 10.3 Sample Mean, Sample Variance, and the Monte-Carlo Standard Error

We estimate $m_1 := \mathbb{E}[X]$ by the finite sample

$$
\widehat{m}_1 \;=\; \frac{1}{M}\,\sum_{m=1}^{M}\, X^{(m)} \qquad \text{(sample mean).}
\tag{10.3}
$$

The sample mean is unbiased ($\mathbb{E}[\widehat{m}_1] = \mathbb{E}[X]$) because expectation is linear, and has variance

$$
\mathbb{V}[\widehat{m}_1] \;=\; \frac{1}{M^2}\sum_{m=1}^M \mathbb{V}[X^{(m)}] \;=\; \frac{\mathbb{V}[X]}{M},
\tag{10.4}
$$

using independence of the draws. The standard deviation of the sample mean is therefore $\sigma_{m_1} = \mathrm{sd}[X]/\sqrt{M}$. Since $\sigma_{m_1}$ depends on the unknown population variance, we estimate it by the sample-variance-based standard error

$$
\widehat{\sigma}_{m_1} \;=\; \frac{1}{\sqrt{M}}\!\left(\,\frac{1}{M-1}\sum_{m=1}^{M}\!\left(X^{(m)} - \widehat{m}_1\right)^2\,\right)^{\!1/2}.
\tag{10.5}
$$

Two small but important points about (10.5). First, the inner bracket is the unbiased sample variance (divisor $M-1$, not $M$); the $M-1$ correction — Bessel's correction — adjusts for the degree of freedom absorbed in estimating the mean. Second, dividing by $\sqrt{M}$ turns the sample standard deviation of the *underlying variable* into the standard deviation of the *sample mean*. The Monte-Carlo error bar is the latter, not the former, and they differ by a factor of $\sqrt{M}$ that is easy to confuse.

The $M^{-1/2}$ convergence rate is universal for i.i.d. Monte Carlo with finite variance. Its immediate operational consequence: *halving the error bar costs four times as many paths*. A trader who wants to move an MC estimate from three significant figures to four needs $100\times$ more paths; from four to five, $10{,}000\times$ more. The law of diminishing returns is brutal, which is exactly why variance reduction matters so much (§10.8).

Let us work through a concrete error budget to build intuition. Suppose we are pricing a one-year ATM European call with Black–Scholes parameters $S_0 = K = 100$, $r = 5\%$, $\sigma = 20\%$, $T = 1$. The closed-form Black–Scholes value (Chapter 6) is $V_0^{\mathrm{BS}}\approx 10.45$. The payoff $X = e^{-rT}(A_T-K)_+$ has standard deviation roughly $\mathrm{sd}(X)\approx 14$ at these parameters — one can read this from direct moment calculation or from the empirical standard deviation of a pilot MC run. A Monte-Carlo estimate with $M = 10{,}000$ paths therefore has a standard error of $14/\sqrt{10{,}000} = 0.14$, so the 95% confidence interval is approximately

$$
10.45 \pm 1.96\cdot 0.14 \;=\; [10.17,\; 10.73].
$$

To push the error below $0.01$ (four-digit accuracy), we need $M = (14/0.01)^2 = 1{,}960{,}000$ paths — of order two million. This is entirely feasible in seconds on modern commodity hardware, but expensive enough that variance reduction pays for itself within the first few million paths.

A pair of useful ballpark facts that a trader should carry in their head:

- A standard-error budget of $0.1$ on an option worth $\sim 10$ is typically acceptable for a trading indication. That is $M\sim 20{,}000$ paths for a vanilla European call at typical parameters.
- A standard-error budget of $0.01$ on a portfolio-level MC risk calculation is typically required for capital numbers. That is $M\sim 2{,}000{,}000$ paths, an order of magnitude more effort.
- Pathwise sensitivities (deltas, gammas) typically have standard deviations $2$–$5\times$ higher than the price itself, so Greek estimation at fixed MC budget is $4\times$–$25\times$ noisier than price estimation at the same budget. Practitioners either run more paths for Greeks or use variance-reduction techniques more aggressively on Greeks than on prices.

The standard error is not a guarantee — it is an estimate of an estimate. The sample variance itself has sampling error, and the 95% CI from a Gaussian approximation is only asymptotic. For small samples ($M \lesssim 100$) one should use a Student-$t$ critical value instead of $1.96$, and for badly non-Gaussian payoff distributions (heavily OTM or knocked-in barriers with few triggering paths) one should look skeptically at any symmetric confidence interval. When in doubt, bootstrap.

---

## 10.4 The Lognormal GBM Path Generator

With the SLLN in hand and the standard-error formula (10.5) at our disposal, the remaining ingredient for a Monte-Carlo pricer is a path generator — a procedure that, on demand, produces sample paths $\{S_{t_n}\}_{n=0}^N$ from the risk-neutral law of the asset. For GBM the generator is *exact*, not approximate; this is one of the two or three SDEs whose discretisation introduces no bias at the grid points. The reason is that Chapter 6 has already solved the GBM SDE in closed form.

### 10.4.1 Exact lognormal increment

From Chapter 6 we know that under $\mathbb{Q}$ the asset price follows

$$
\mathrm{d} S_t \;=\; r\,S_t\,\mathrm{d} t \;+\; \sigma\,S_t\,\mathrm{d} W_t^{\mathbb{Q}},
\tag{10.6}
$$

where $W^{\mathbb{Q}}$ is a $\mathbb{Q}$-Brownian motion (the risk-neutral drift $r$ having been installed by the Girsanov shift of Chapter 5). Applying Itô's lemma to $\ln S_t$ (Chapter 3) gives

$$
\mathrm{d}\ln S_t \;=\; \bigl(r - \tfrac{1}{2}\sigma^2\bigr)\,\mathrm{d} t \;+\; \sigma\,\mathrm{d} W_t^{\mathbb{Q}},
\tag{10.7}
$$

and integrating from $t_{n-1}$ to $t_n$,

$$
\ln S_{t_n} - \ln S_{t_{n-1}} \;=\; \bigl(r - \tfrac{1}{2}\sigma^2\bigr)\,\Delta t_n \;+\; \sigma\,\bigl(W^{\mathbb{Q}}_{t_n} - W^{\mathbb{Q}}_{t_{n-1}}\bigr),
\tag{10.8}
$$

with $\Delta t_n := t_n - t_{n-1}$. The Brownian increment $W^{\mathbb{Q}}_{t_n} - W^{\mathbb{Q}}_{t_{n-1}}$ is exactly Gaussian with mean $0$ and variance $\Delta t_n$, and — crucially — independent of the history up to $t_{n-1}$. Writing the increment as $\sqrt{\Delta t_n}\,Z_n$ with $Z_n\sim\mathcal{N}(0,1)$ and exponentiating gives the multiplicative path-simulation recursion

$$
S_{t_n} \;=\; S_{t_{n-1}}\,\exp\!\Bigl\{\bigl(r - \tfrac{1}{2}\sigma^2\bigr)\,\Delta t_n \;+\; \sigma\sqrt{\Delta t_n}\,Z_n\Bigr\},
\qquad Z_1, Z_2, \dots \stackrel{\text{iid}}{\sim}_{\mathbb{Q}} \mathcal{N}(0,1).
\tag{10.9}
$$

This is the universal GBM path generator. At the grid points $t_0, t_1, \dots, t_N$ the law of $(S_{t_0}, S_{t_1}, \dots, S_{t_N})$ produced by (10.9) is *exactly* the law of a GBM sampled at those points — there is no discretisation bias. Between the grid points the discrete path is a log-linear interpolation, which *is* an approximation, and for payoffs that care about the between-grid behaviour (like barriers) we will see below that a correction is needed.

Contrast this with the general case. For a non-GBM SDE $\mathrm{d} X_t = \mu(X_t)\,\mathrm{d} t + \sigma(X_t)\,\mathrm{d} W_t^{\mathbb{Q}}$ the Itô increment is Gaussian only in the limit $\Delta t\to 0$, and for finite $\Delta t$ the Euler–Maruyama scheme

$$
X_{t_n} \;\approx\; X_{t_{n-1}} + \mu(X_{t_{n-1}})\,\Delta t_n + \sigma(X_{t_{n-1}})\sqrt{\Delta t_n}\,Z_n
$$

introduces a weak error of order $\Delta t$ and a strong error of order $\sqrt{\Delta t}$. Milstein's scheme adds a second-order correction and upgrades the strong error to $\Delta t$. For path-dependent payoffs where individual realisations (not just distributions) matter, the strong-order matters most, and practitioners sometimes pay the price of a higher-order scheme to reduce discretisation bias. For GBM we pay no such price — the exact lognormal increment is available at every grid width.

### 10.4.2 Monte-Carlo estimator for European claims

For a European claim with payoff $\varphi(S_T)$ the MC estimator is the direct sample-average translation of the SLLN:

$$
\widehat{V}_0 \;=\; e^{-rT}\cdot \frac{1}{M}\sum_{m=1}^{M}\, \varphi\!\left(S_0\,e^{(r-\tfrac{1}{2}\sigma^2)T \;+\; \sigma\sqrt{T}\,Z^{(m)}}\right),
\qquad Z^{(m)} \stackrel{\text{iid}}{\sim}_{\mathbb{Q}} \mathcal{N}(0,1).
\tag{10.10}
$$

Only the terminal value $S_T$ enters, so we do not even need a grid — a single Gaussian draw per path suffices. This is the computationally cheapest non-trivial Monte-Carlo pricer and is useful mainly as a sanity check against Black–Scholes and as a warm-up for the path-dependent cases below.

### 10.4.3 Euler–Maruyama and Milstein for non-GBM SDEs

For the stochastic-volatility, local-volatility, and jump-diffusion models that appear later in the guide (Chapter 14 for Heston, in particular) the exact lognormal increment is *not* available, and one falls back on discretisation schemes. The simplest is Euler–Maruyama:

$$
X_{t_n} \;\approx\; X_{t_{n-1}} \;+\; \mu(X_{t_{n-1}})\,\Delta t_n \;+\; \sigma(X_{t_{n-1}})\sqrt{\Delta t_n}\,Z_n.
$$

The scheme approximates the Itô increment by freezing the drift and diffusion coefficients at the left endpoint and using a plain Gaussian increment; it has *weak* convergence rate $O(\Delta t)$ (expectations of smooth functions of the terminal value converge at rate $\Delta t$) and *strong* convergence rate $O(\sqrt{\Delta t})$ (individual path realisations converge at the slower $\sqrt{\Delta t}$ rate). The distinction matters for path-dependent payoffs where individual realisations drive the payoff, not just their distributions.

Milstein's scheme augments Euler with a second-order Itô correction:

$$
X_{t_n} \;\approx\; X_{t_{n-1}} \;+\; \mu\,\Delta t_n \;+\; \sigma\sqrt{\Delta t_n}\,Z_n \;+\; \tfrac{1}{2}\,\sigma\,\sigma'\,(\Delta t_n)\,(Z_n^2 - 1),
$$

where $\sigma' = \partial\sigma/\partial X$. The correction upgrades the strong convergence rate to $O(\Delta t)$ and the weak rate remains $O(\Delta t)$. For constant diffusion ($\sigma' = 0$) Milstein and Euler coincide. For GBM ($\sigma(X) = \sigma X$, $\sigma' = \sigma$) Milstein's correction is $\tfrac{1}{2}\sigma^2 X\,(\Delta t)(Z^2 - 1)$, which matches the first-order Taylor expansion of the exact lognormal increment. For the Heston variance process $\mathrm{d} v_t = \kappa(\theta - v_t)\mathrm{d} t + \xi\sqrt{v_t}\mathrm{d} W_t$ the diffusion $\sigma(v) = \xi\sqrt{v}$ is not differentiable at $v=0$, and naive Euler can produce negative variance values; the standard fixes are *full-truncation* (set negative values to zero before using them as the next drift) and the exact *QE scheme* of Andersen. Chapter 14 develops these in detail.

For any SDE whose exact solution is known in closed form, one should always prefer the exact simulator to Euler. GBM and OU are the two canonical examples; CIR, Vasicek (as a special case of OU), and a handful of others also admit exact schemes. For everything else, Euler is the pragmatic default, with Milstein applied when the strong-convergence-rate improvement justifies the extra arithmetic cost.

### 10.4.4 Additive log-space simulation

The exponential-and-multiplicative form of (10.9) is not the only representation. One could instead simulate $\ln S_{t_n}$ additively,

$$
\ln S_{t_n} \;=\; \ln S_{t_{n-1}} + (r - \tfrac{1}{2}\sigma^2)\,\Delta t_n \;+\; \sigma\sqrt{\Delta t_n}\,Z_n,
\tag{10.11}
$$

and exponentiate at the end to recover $S_{t_n}$. Algebraically the two are identical; numerically they differ in edge cases. The multiplicative form can underflow to zero for very long paths at small $S$, while the additive form on $\ln S$ is more numerically stable. Production pricers typically work in log-space for this reason, especially when pricing very-long-dated (decades) structures or when the parameters drive the path into the tail. For everyday pricing at typical maturities (months to a few years) the difference is imperceptible.

### 10.4.5 Correlation of time-slices along a single path

Before using (10.9) to price path-dependent claims, we pause to think carefully about how different time-slices of the same simulated path are correlated. This is both a technical prerequisite for the forward-starting-option derivation of §10.6 and a conceptual anchor for why path-dependent options are fundamentally richer than European options.

For two times $T_1 < T_2$ along the same GBM path, write

$$
\mathbb{C}\!\left[S_{T_1}, S_{T_2}\right] \;=\; \operatorname{Cov}^{\mathbb{Q}}\!\left(S_{T_1}, S_{T_2}\right),
\qquad
\rho\!\left[S_{T_1}, S_{T_2}\right] \;=\; \frac{\mathbb{C}\!\left[S_{T_1}, S_{T_2}\right]}{\bigl(\mathbb{V}[S_{T_1}]\,\mathbb{V}[S_{T_2}]\bigr)^{1/2}}.
\tag{10.12}
$$

Because $S_{T_2} = S_{T_1}\cdot \exp\{(r - \tfrac{1}{2}\sigma^2)(T_2 - T_1) + \sigma\sqrt{T_2 - T_1}\,Z'\}$ with $Z'$ a fresh standard Gaussian independent of $\mathcal{F}_{T_1}$, the two slices $S_{T_1}$ and $S_{T_2}$ are positively correlated but not perfectly correlated — the intervening Brownian shock $Z'$ drives them apart.

For a concrete calculation: under $\mathbb{Q}$, $\ln S_{T_i}$ is Gaussian with mean $(r-\tfrac{1}{2}\sigma^2)T_i$ and variance $\sigma^2 T_i$. The covariance of the *log*-prices is $\sigma^2\,\min(T_1, T_2) = \sigma^2 T_1$ (because $\ln S_{T_1}$ and $\ln S_{T_2}$ differ by a Brownian increment over $[T_1, T_2]$ that is independent of the increment over $[0, T_1]$). The correlation coefficient of the log-prices is therefore

$$
\rho\!\left[\ln S_{T_1}, \ln S_{T_2}\right] \;=\; \frac{\sigma^2 T_1}{\sqrt{\sigma^2 T_1 \cdot \sigma^2 T_2}} \;=\; \sqrt{T_1/T_2}.
$$

At $T_1/T_2 = 1/2$ the correlation is $1/\sqrt{2}\approx 0.707$; at $T_1/T_2 = 0.1$ it is $\sqrt{0.1}\approx 0.316$. Higher correlation between nearby times reflects the strong dependence of consecutive Brownian increments. The *levels* $S_{T_1}$ and $S_{T_2}$ are *log*-normally correlated, not linearly correlated; the two notions differ for skewed distributions, and a practitioner computing correlation of levels from simulated paths should always be clear whether the reported number refers to levels or logs.

The single property that makes path-dependent pricing tractable is *independence of disjoint increments*. The Brownian motion satisfies $W_{T_2} - W_{T_1} \perp \mathcal{F}_{T_1}$; this is the core of the Markov property, and it is what lets us factor joint expectations along time as nested conditional expectations. The next section makes use of this independence in its sharpest form.

<!-- figure placeholder (see figures/ch02-*.png): a simulated path S_t on (t, S) axes with two vertical dashed lines at T_1 and T_2, sampled dots S_{T_1}, S_{T_2}, arrow labelled Z_1 from S_0 to S_{T_1}, arrow labelled Z_3 from S_{T_1} to S_{T_2} — emphasises independence of Z_1 and Z_3. -->

---

## 10.5 Sanity Check: European Call by Monte Carlo

Before tackling path-dependent payoffs we work through the simplest non-trivial MC pricer: a European call on a GBM underlying. The point is purely pedagogical — Black–Scholes gives the exact answer in closed form, so there is no need to simulate anything. But the sanity check is worthwhile because it lets us verify the mechanics of (10.10), calibrate our expectations for the $M^{-1/2}$ convergence rate, and provide a reference against which the path-dependent pricers below can be compared.

Take the reference parameters $S_0 = K = 100$, $r = 5\%$, $\sigma = 20\%$, $T = 1$. Black–Scholes (Chapter 6) gives $V_0^{\mathrm{BS}}\approx 10.45$ with $d_\pm = (r\pm\tfrac{1}{2}\sigma^2)T / (\sigma\sqrt{T}) = \{0.35,\,0.15\}$ and $\Phi(0.35)\approx 0.637$, $\Phi(0.15)\approx 0.560$.

Simulation. Draw $M = 10{,}000$ standard normals $Z^{(m)}$ and compute the payoff on each:

$$
S_T^{(m)} \;=\; 100\cdot e^{0.03 + 0.2\,Z^{(m)}}, \qquad X^{(m)} \;=\; e^{-0.05}\,(S_T^{(m)} - 100)_+.
$$

Average the payoffs: $\widehat{V}_0 = (1/M)\sum_m X^{(m)}\approx 10.43$ (a typical realisation). The sample standard deviation of $X$ is around $14$, so the standard error is $\widehat{\sigma}_{m_1}\approx 14/\sqrt{10{,}000} = 0.14$ and the 95% confidence interval is approximately $[10.15,\,10.71]$ — it comfortably brackets the closed-form value $10.45$. Doubling $M$ to $40{,}000$ halves the standard error to $0.07$, illustrating the $M^{-1/2}$ law. Quadrupling to $160{,}000$ halves it again to $0.035$.

What the sanity check buys us. A successful MC vs BS cross-check gives assurance on three independently-failable components of the pricer simultaneously: the random-number generator is producing genuine independent Gaussians; the GBM drift $r - \tfrac{1}{2}\sigma^2$ is applied with the correct sign and magnitude; and the discount factor $e^{-rT}$ is applied exactly once. Each of these is a source of subtle bugs in production code. In particular, the $-\tfrac{1}{2}\sigma^2$ Itô correction is the single most common bug in home-grown MC pricers — it is easy to forget or get a sign wrong, and in that case the simulation produces a biased estimate whose bias *does not go away with more paths*. The standard-error bars shrink, the estimate converges confidently to a wrong number, and the bug can persist unnoticed for weeks until someone thinks to run a BS sanity check.

The sanity check also gives a cheap calibration of variance-reduction gain. With antithetic variates (§10.8) the standard error at $M=10{,}000$ typically drops from $0.14$ to around $0.10$ on this payoff — a variance reduction of about $2$. A stock-price control variate (whose expectation is known exactly, $\mathbb{E}^{\mathbb{Q}}[S_T] = S_0 e^{rT} = 100 e^{0.05}\approx 105.13$) reduces standard error by another factor of $3$–$5$. Combined, these two techniques can bring the standard error at $M=10{,}000$ down to $0.02$, which would otherwise require $M\approx 500{,}000$ paths without variance reduction. That is a factor-of-$50$ speedup for a handful of extra lines of code.

Finally, the sanity check is where one should worry about edge cases. At extremely low volatility or short maturity, the payoff is nearly deterministic and its variance is nearly zero; MC does not struggle, but the $\widehat{\sigma}_{m_1}$ itself is small and its estimate is noisy, so reported confidence intervals may be misleading. At extremely high volatility or long maturity the payoff has a huge variance, so $M=10{,}000$ paths give a correspondingly large standard error; one must scale up $M$ accordingly. In both regimes, the relative error $\widehat{\sigma}_{m_1}/\widehat{V}_0$ is a better summary than the absolute standard error.

---

## 10.6 Forward-Starting (Cliquet) Options

Forward-starting options occupy a distinctive place in the exotic-options landscape. They are path-dependent — their payoff depends on the underlying at two different times, not just at maturity — but the dependence is structured enough that iterated conditional expectation gives a closed-form price. The derivation that follows is worth its weight several times over: it is the atom of cliquet (ratchet) pricing, it illustrates how Brownian independent-increments repackage a correlated two-dimensional problem into a pair of one-dimensional Black–Scholes integrals, and it foreshadows the conditioning arguments that dominate interest-rate and stochastic-volatility pricing in later chapters.

### 10.6.1 Definition

A forward-starting call is an exotic whose strike is set at an intermediate date $T_1$ as a fraction $\alpha$ of the then-prevailing spot. The payoff at maturity $T_2 > T_1$ is

$$
\varphi \;=\; \bigl(S_{T_2} - \alpha\, S_{T_1}\bigr)_+, \qquad (x)_+ := \max(x, 0).
\tag{10.13}
$$

The strike $\alpha\,S_{T_1}$ is not known at time $0$ — it is stochastic through $S_{T_1}$.

The economic motivation is protection *relative to wherever the market is when protection kicks in*. An investor who wants "a call whose strike is set to whatever the index is six months from now" is buying a forward-starting call with $T_1 = 0.5$ and $\alpha = 1$. An insurance company that writes annual reset put options on a pension liability is effectively writing a sequence of forward-starting puts. Cliquet options chain forward-starts together: a 12-leg monthly cliquet call consists of twelve forward-starting calls with reset dates at the end of each month, each leg paying the monthly reset-to-reset return above zero, and the total payoff being the sum. Some cliquet structures layer on local caps, global floors, or coupon multipliers; we deal only with the atomic forward-starting call here.

Cliquets are ubiquitous in structured-note design. A *locally-capped globally-floored* cliquet caps each reset-to-reset return at (say) $+3\%$ and guarantees a minimum total return of zero over the full life; it is a single-tranche packaging of path-dependent upside, popular with retail insurance customers who want equity-like returns with capital protection. Pricing these involves summing or compounding the atom (10.13) over many reset dates. The deeper reason cliquets are useful in portfolio construction: they hedge *relative* moves rather than *absolute* ones. Because the strikes are not known at trade inception, cliquets are more sensitive to *forward volatility* (vol of vol over future intervals) than vanilla options; they are a natural vehicle for vol-of-vol exposure.

### 10.6.2 Vanilla Black–Scholes recap

We restate the Black–Scholes formula here because the forward-starting price in §10.6.5 will reuse it as a building block. The cliquet calculation is "Black–Scholes inside Black–Scholes" — an inner BS for the conditional payoff given $S_{T_1}$, and an outer BS-like integral for the unconditional price. The vanilla European call with strike $K$ and tenor $T$ has price

$$
V_0 \;=\; e^{-rT}\,\mathbb{E}^{\mathbb{Q}}\bigl[(S_T - K)_+\bigr] \;=\; S_0\,\Phi(d_+) \;-\; K\,e^{-rT}\,\Phi(d_-),
\tag{10.14}
$$

$$
d_\pm \;=\; \frac{\ln(S_0 / K) + \bigl(r \pm \tfrac{1}{2}\sigma^2\bigr)T}{\sigma\sqrt{T}}.
\tag{10.15}
$$

### 10.6.3 Reparameterising on two time-slices

The key manipulation is to rewrite the joint law of $(S_{T_1}, S_{T_2})$ in terms of independent Brownian increments over disjoint intervals. The two slices are correlated (they share a common Brownian path up to $T_1$), but the *increment* $W^{\mathbb{Q}}_{T_2} - W^{\mathbb{Q}}_{T_1}$ is independent of the history $\mathcal{F}_{T_1}$. This decomposition is what allows iterated conditional expectation to factor the pricing integral into a product of one-dimensional integrals.

Under $\mathbb{Q}$, the asset at $T_1$ and $T_2$ admits the direct lognormal representations

$$
S_{T_1} \;=\; S_0\,e^{(r - \tfrac{1}{2}\sigma^2)T_1 \;+\; \sigma\sqrt{T_1}\,Z_1}, \qquad Z_1 \sim_{\mathbb{Q}} \mathcal{N}(0,1),
\tag{10.16}
$$

$$
S_{T_2} \;=\; S_0\,e^{(r - \tfrac{1}{2}\sigma^2)T_2 \;+\; \sigma\sqrt{T_2}\,Z_2}, \qquad Z_2 \sim_{\mathbb{Q}} \mathcal{N}(0,1),
\tag{10.17}
$$

with $(Z_1, Z_2)$ correlated. The equivalent independent-increment factorisation is

$$
S_{T_1} \;\stackrel{d}{=}\; S_0\,e^{(r - \tfrac{1}{2}\sigma^2)T_1 \;+\; \sigma\sqrt{T_1}\,Z_1},
\tag{10.18}
$$

$$
S_{T_2} \;\stackrel{d}{=}\; S_{T_1}\cdot e^{(r - \tfrac{1}{2}\sigma^2)(T_2 - T_1) \;+\; \sigma\sqrt{T_2 - T_1}\,Z_3}, \qquad Z_3 \sim_{\mathbb{Q}} \mathcal{N}(0,1), \quad Z_1 \perp Z_3.
\tag{10.19}
$$

The two Gaussians $Z_1$ and $Z_3$ are now independent — they represent the Brownian increments over the disjoint intervals $[0, T_1]$ and $[T_1, T_2]$. The repackaging trades a two-dimensional correlated Gaussian $(Z_1, Z_2)$ for two one-dimensional independent Gaussians, and that decoupling is what makes the inner and outer expectations below factorise cleanly.

### 10.6.4 Iterated conditional expectation

Starting from the pricing integral and using the tower property $\mathbb{E}[X] = \mathbb{E}[\mathbb{E}[X\mid Y]]$:

$$
V_0 \;=\; e^{-rT_2}\,\mathbb{E}^{\mathbb{Q}}\!\left[\,(S_{T_2} - \alpha\,S_{T_1})_+\,\right] \;=\; e^{-rT_2}\,\mathbb{E}^{\mathbb{Q}}\!\left[\,\mathbb{E}^{\mathbb{Q}}\!\left[\,(S_{T_2} - \alpha\,S_{T_1})_+\,\bigm|\, S_{T_1}\,\right]\,\right].
\tag{10.20}
$$

Separate the two discount factors so that the inner expectation becomes a Black–Scholes pricing problem in its own right, discounted from $T_2$ back to $T_1$:

$$
V_0 \;=\; e^{-rT_1}\,\mathbb{E}^{\mathbb{Q}}\!\left[\,e^{-r(T_2 - T_1)}\,\mathbb{E}^{\mathbb{Q}}\!\left[\,(S_{T_2} - \alpha\,S_{T_1})_+\,\bigm|\, S_{T_1}\,\right]\,\right].
\tag{10.21}
$$

### 10.6.5 Inner expectation — Black–Scholes with strike $\alpha S_{T_1}$

Conditional on $S_{T_1}$, the forward-starting payoff $(S_{T_2} - \alpha\,S_{T_1})_+$ is a standard European call on $S$ with time-to-expiry $T_2 - T_1$ and strike $\alpha\,S_{T_1}$ (treated as a constant given $\mathcal{F}_{T_1}$). The inner conditional expectation is therefore given by the Black–Scholes formula (10.14)–(10.15), with spot $S_{T_1}$ and strike $\alpha\,S_{T_1}$:

$$
e^{-r(T_2 - T_1)}\,\mathbb{E}^{\mathbb{Q}}\!\left[\,(S_{T_2} - \alpha\,S_{T_1})_+\,\bigm|\, S_{T_1}\,\right] \;=\; S_{T_1}\,\Phi(d_+) \;-\; \alpha\,S_{T_1}\,e^{-r(T_2 - T_1)}\,\Phi(d_-),
\tag{10.22}
$$

with

$$
d_\pm \;=\; \frac{\ln\bigl(S_{T_1}/(\alpha\,S_{T_1})\bigr) + \bigl(r \pm \tfrac{1}{2}\sigma^2\bigr)(T_2 - T_1)}{\sigma\sqrt{T_2 - T_1}} \;=\; \frac{\ln(1/\alpha) + \bigl(r \pm \tfrac{1}{2}\sigma^2\bigr)(T_2 - T_1)}{\sigma\sqrt{T_2 - T_1}}.
\tag{10.23}
$$

Notice what happened: the $S_{T_1}$ factors in the moneyness ratio $S_{T_1}/(\alpha S_{T_1}) = 1/\alpha$ *cancelled*, leaving $d_\pm$ as *constants* — not random variables. This is the defining algebraic property of the forward-starting structure and is what makes closed-form pricing possible. The spot and the strike scale identically with $S_{T_1}$, so moneyness is always $1/\alpha$ regardless of where $S_{T_1}$ lands. Every dollar increase in $S_{T_1}$ lifts both the (random) spot and the (random) strike by $\alpha$, leaving the convexity structure invariant.

### 10.6.6 Outer expectation — linearity and pull-out

Collect the inner result as $S_{T_1}\cdot\eta$ with the deterministic constant

$$
\eta \;:=\; \Phi(d_+) \;-\; \alpha\,e^{-r(T_2 - T_1)}\,\Phi(d_-).
\tag{10.24}
$$

Substituting into (10.21),

$$
V_0 \;=\; e^{-rT_1}\,\mathbb{E}^{\mathbb{Q}}\!\left[\,S_{T_1}\cdot\eta\,\right] \;=\; e^{-rT_1}\,\eta\,\mathbb{E}^{\mathbb{Q}}[S_{T_1}] \;=\; e^{-rT_1}\,\eta\cdot S_0\,e^{rT_1} \;=\; \eta\cdot S_0,
\tag{10.25}
$$

where the third equality uses the risk-neutral martingale condition $\mathbb{E}^{\mathbb{Q}}[S_{T_1}] = S_0\,e^{rT_1}$ — a direct consequence of the fact that the discounted spot $e^{-rt}\,S_t$ is a $\mathbb{Q}$-martingale (FTAP from Chapter 2, made rigorous by Girsanov in Chapter 5). The two discount factors $e^{-rT_1}$ and $e^{+rT_1}$ cancel, and the outer expectation collapses to the constant $\eta\,S_0$. The closed-form forward-starting call price is

$$
\boxed{\; V_0 \;=\; S_0\,\Bigl[\,\Phi(d_+) \;-\; \alpha\,e^{-r(T_2 - T_1)}\,\Phi(d_-)\,\Bigr], \qquad d_\pm \;=\; \frac{\ln(1/\alpha) + \bigl(r \pm \tfrac{1}{2}\sigma^2\bigr)(T_2 - T_1)}{\sigma\sqrt{T_2 - T_1}}. \;}
\tag{10.26}
$$

### 10.6.7 Interpretation and a worked example

The forward-starting call price depends on $S_0$ *only through the overall scale* — the moneyness $d_\pm$ is a function of $\alpha$ and the tenor $T_2 - T_1$ alone, not of $S_0$. The price therefore scales linearly in $S_0$, and the whole problem collapses to a Black–Scholes formula with strike-ratio $\alpha$ and effective tenor $T_2 - T_1$. This is why cliquets are sometimes called "relative-moneyness" options: their fair value tracks today's spot rather than any fixed dollar strike, making them natural hedges for wealth held as a percentage of the index.

Worked numerical scenario. Take $S_0 = 100$, $\alpha = 1.0$ (ATM reset), $T_1 = 0.5$, $T_2 = 1.0$, $r = 5\%$, $\sigma = 20\%$. The effective tenor is $T_2 - T_1 = 0.5$. Substituting into (10.26):

$$
d_+ \;=\; \frac{0 + 0.07\cdot 0.5}{0.2\sqrt{0.5}} \;=\; \frac{0.035}{0.1414} \;\approx\; 0.2475,
\qquad
d_- \;=\; \frac{0 + 0.03\cdot 0.5}{0.1414} \;\approx\; 0.1061.
$$

Normal CDFs: $\Phi(0.2475)\approx 0.5977$, $\Phi(0.1061)\approx 0.5422$. Discount factor $e^{-0.025}\approx 0.9753$. Then

$$
\eta \;=\; 0.5977 - 1.0\cdot 0.9753\cdot 0.5422 \;=\; 0.5977 - 0.5289 \;=\; 0.0688,
\qquad
V_0 \;=\; 0.0688\cdot 100 \;=\; 6.88.
$$

Compare to the vanilla ATM European call at $T = 1$ with these parameters: about $10.45$. The forward-starting call is $34\%$ cheaper. Why? Because the first six months of the contract contribute no convexity for the holder — the strike floats with the spot, so the contract is "ATM forever" until the reset. Only the post-reset half-year carries convexity value. A rough rule of thumb: a forward-starting ATM call is worth approximately $\sqrt{(T_2-T_1)/T_2}$ times the equivalent vanilla ATM call. For our parameters this predicts $10.45\cdot\sqrt{0.5}\approx 7.39$ — close to the true $6.88$, with the residual difference reflecting the $-\tfrac{1}{2}\sigma^2$ term that does not scale as $\sqrt{T}$.

The linearity in $S_0$ has two practical implications. First, the *delta* of a forward-starting call is $\eta$ — a constant — rather than the state-dependent $\Phi(d_+)$ of a vanilla. This makes forward-starts easy to delta-hedge: the delta is static, and no rebalancing is required as $S$ moves (at least until the reset date, at which point the contract becomes a vanilla call and the usual state-dependent delta takes over). Second, the *vega* of the forward-start is concentrated on the *forward volatility* between $T_1$ and $T_2$, not on the spot volatility to $T_1$. This is why forward-start options are used to express views on forward vol — the volatility implied by market prices for a future window — rather than spot vol. A trader long forward-starts is long forward vol; a trader short them is short forward vol.

Monte-Carlo verification. With (10.9) and a grid $\{0, T_1, T_2\}$, a simulation of (10.13) at $M = 10{,}000$ paths typically returns an estimate within $0.1$ of the closed-form value $6.88$. The MC simulation is a useful check because it verifies the independence of the $(Z_1, Z_3)$ draws — a subtle bug in which the same $Z$ is used for both increments would give a badly wrong price but no obvious error signal. (This is, in practice, the second most common MC bug after the missing $-\tfrac{1}{2}\sigma^2$ drift correction.)

<!-- figure placeholder (see figures/ch02-*.png): forward-starting call value V_0 vs S_0 (linear line), compared to a vanilla European call V_0 vs S_0 (convex piecewise curve) — illustrates the linearity in S_0 of cliquet structures. -->

---

## 10.7 Barrier Options and the Monte-Carlo Time Grid

Barrier options are the canonical path-dependent structure. Their payoff depends not on the final spot alone but on whether the path touches a pre-specified threshold $U$ at *any* point during the contract's life. This seemingly small change — swapping "at maturity" for "at any time before maturity" — transforms the pricing problem fundamentally: we can no longer rely on the terminal distribution of $S_T$ alone; we need the joint distribution of $S_T$ and the running maximum (or minimum) of the path. In return we get a rich family of structured-note primitives, used heavily in retail derivatives packaging and in institutional structured funding.

### 10.7.1 Taxonomy

Barrier options come in eight canonical flavours: $\{\text{up},\,\text{down}\}\times\{\text{in},\,\text{out}\}\times\{\text{call},\,\text{put}\}$. An *up-and-in* call becomes a plain call if the stock ever crosses above $U$; an *up-and-out* call is a plain call that gets cancelled if the stock ever crosses above $U$. Symmetric definitions hold for down-and-in, down-and-out, and the put versions. A structurally important identity is *in-out parity*:

$$
V^{\text{up-and-in call}} \;+\; V^{\text{up-and-out call}} \;=\; V^{\text{vanilla call}},
\tag{10.27}
$$

since exactly one of the two triggers for every path. In-out parity lets us price one member of the pair in terms of the other; it also serves as a primary source of variance reduction in barrier MC, because the vanilla call price is available in closed form and subtracting a known quantity reduces simulation noise (§10.8).

Barrier options are strictly cheaper than the corresponding vanillas (for knock-out barriers that cancel the contract) or equal-or-cheaper (for knock-ins, which have a chance of never activating and paying zero). They are used extensively in structured products: a "twin-win" note pays the magnitude of index returns unless a down-barrier is breached; a "reverse convertible" pays a coupon unless a down-barrier is breached, in which case the investor is put the stock at a fixed strike. The barrier adds path-dependence to the payoff, preventing closed-form lognormal pricing in general — though the classical Merton reflection-principle formulas *do* give closed forms under continuous monitoring of geometric Brownian motion with constant parameters.

### 10.7.2 Up-and-in call — definition

The up-and-in call pays

$$
\varphi \;=\; (S_T - K)_+\,\mathbf{1}_{\{\,\max_{0\le t\le T} S_t \;\ge\; U\,\}}, \qquad U > S_0,
\tag{10.28}
$$

where the typical parameter ordering is $U > K > S_0$ (barrier above strike above initial spot). The contract becomes a standard European call with strike $K$ at the first time the path crosses the barrier; otherwise the holder receives nothing. The knock-in event is measurable with respect to the path up to $T$, not just $S_T$; this is what makes the payoff path-dependent.

Under continuous monitoring of GBM there is a beautiful closed-form formula (the "reflection-principle" formula). For the up-and-in call with $S_0 < K < U$,

$$
V^{\text{UIC}}_{\text{continuous}} \;=\; S_0\!\left(\tfrac{U}{S_0}\right)^{\!2\lambda}\,\Phi(y_1) \;-\; K\,e^{-rT}\!\left(\tfrac{U}{S_0}\right)^{\!2\lambda-2}\,\Phi(y_1 - \sigma\sqrt{T}),
\tag{10.29}
$$

where $\lambda = (r + \tfrac{1}{2}\sigma^2)/\sigma^2$ and $y_1$ is an explicit log-moneyness expression. We do not derive (10.29) here — the reflection principle for Brownian motion and its Girsanov-shifted counterpart for GBM are a standard but lengthy calculation, covered in every classical derivatives text. We use the formula only as an external benchmark: the *continuous-monitoring* closed form gives us a reference number against which discrete-monitoring MC estimates can be calibrated. Under discrete monitoring (say daily fixings), the barrier is crossed only at the fixing dates, not continuously in between; MC implementations naturally approximate discrete monitoring if the grid is chosen as the monitoring dates.

### 10.7.3 Lattice view

Before moving to Monte Carlo it is worth seeing how a binomial lattice prices barrier options. The lattice view clarifies the discretisation questions that plague the MC implementation and ties the path-dependent pricing back to the backward-induction apparatus of Chapter 2. Propagate known values from the barrier level downward: at any node on or above $U$, the option is (thereafter) a standard European call with strike $K$ whose value $C^{\text{vanilla}}(S_n, t_n; K, T)$ is already known from the BS formula (10.14)–(10.15). Below the barrier the backward induction is the usual discounted $\mathbb{Q}$-expectation, but with the *known* vanilla-call value pasted in at any node that has touched $U$ along the path to that node. The tree effectively shrinks to a triangular wedge bounded by the barrier surface, and the barrier acts as a "known-value boundary" analogous to a Dirichlet condition in PDE language.

In the PDE framework, the Black–Scholes equation for a barrier option carries a Dirichlet boundary condition at $S = U$: for a knock-in, $V(U, t) = $ the vanilla-call value at that time; for a knock-out, $V(U, t) = 0$. The lattice backward-induction is solving this PDE numerically, with a two-child backward expectation playing the role of the finite-difference stencil. Analytical PDE solutions via method of images or Green's functions yield the same reflection-principle formulas mentioned above. Different methods — closed form, PDE, lattice, MC — should all agree to within their respective discretisation and variance errors; cross-validation between methods is a standard sanity check in derivatives implementation.

### 10.7.4 Monte-Carlo pricing with a time grid

The path-simulation recipe (10.9) applies directly. Discretise $[0, T]$ with a grid $t_0 = 0 < t_1 < \cdots < t_N = T$, step sizes $\Delta t_n = t_n - t_{n-1}$, and simulate

$$
S_{t_n} \;=\; S_{t_{n-1}}\,e^{(r - \tfrac{1}{2}\sigma^2)\Delta t_n \;+\; \sigma\sqrt{\Delta t_n}\,Z_n}, \qquad Z_1, Z_2, \dots \stackrel{\text{iid}}{\sim}_{\mathbb{Q}} \mathcal{N}(0,1).
\tag{10.30}
$$

The Monte-Carlo estimator of the up-and-in call price is

$$
\widehat{V}_0 \;=\; e^{-rT}\cdot \frac{1}{M}\,\sum_{m=1}^{M}\,\bigl(S_T^{(m)} - K\bigr)_+\,\mathbf{1}_{\bigl\{\,\max_n\, S_{t_n}^{(m)} \;\ge\; U\,\bigr\}}.
\tag{10.31}
$$

Each simulated path contributes to the average only if its discretely-sampled maximum equals or exceeds $U$; paths that stay below $U$ contribute zero regardless of terminal value.

### 10.7.5 Discretisation bias

The indicator $\mathbf{1}_{\{\,\max_n S_{t_n}\ge U\,\}}$ in (10.31) samples the path only at grid points; the true knock-in event $\{\,\max_{0\le t\le T} S_t \ge U\,\}$ can occur *between* grid points. For a given Brownian path one therefore underestimates the knock-in probability — each grid has some probability of missing a barrier excursion that happened between two of its points. Consequently the barrier-option MC price is *biased downward* at finite $N$, and the bias vanishes only in the limit $\Delta t_n \to 0$. This is the characteristic issue with MC pricing of path-dependent barrier and lookback contracts; the same issue arises for any payoff whose value depends on a supremum, infimum, or first-hitting time of the path.

The bias can be substantial. For an up-and-in call with $S_0 = 100$, $K = 100$, $U = 110$, $\sigma = 20\%$, $r = 5\%$, $T = 1$: the true continuous-monitoring value from (10.29) is around $6.15$. With $N = 50$ monitoring points and $M = 10{,}000$ MC paths, the raw estimate from (10.31) is typically around $5.8$ — a $6\%$ downward bias. Refining the grid to $N = 500$ (factor-of-$10$ more work) without any bias correction gives an estimate near $6.10$ — still a small residual bias. Continuing to refine eventually converges to the true value but at substantial computational cost.

### 10.7.6 Brownian-bridge correction

Between two adjacent grid points $t_{n-1}$ and $t_n$ with known endpoints $S_{t_{n-1}}$ and $S_{t_n}$, the conditional law of the path is a *Brownian bridge* (under log-coordinates with drift). The conditional distribution of the path maximum $\max_{t\in[t_{n-1},t_n]} S_t$ given the endpoints has a closed-form CDF, derived from the reflection principle:

$$
\mathbb{P}\!\left(\,\max_{t\in[t_{n-1},t_n]} S_t \;\ge\; U \;\bigm|\; S_{t_{n-1}}, S_{t_n}\,\right) \;=\; \exp\!\left(-\,\frac{2\,\ln(U/S_{t_{n-1}})\,\ln(U/S_{t_n})}{\sigma^2\,\Delta t_n}\right)
\tag{10.32}
$$

for $U > \max(S_{t_{n-1}}, S_{t_n})$; the probability is $1$ when the barrier is already at or below either endpoint. Formula (10.32) is the continuous-time analogue of "interpolate between grid points and check if the interpolant crossed": it gives the exact conditional crossing probability under Brownian-bridge dynamics, which is the correct interpolation given the two endpoints.

The Brownian-bridge correction uses (10.32) as follows. For each simulated path that was *not* flagged as knock-in by the grid-point check, compute the per-interval bridge probability (10.31), draw a uniform random number $U_{\text{unif}}^{(m,n)}$ on $[0,1]$, and flag the path as knock-in if $U_{\text{unif}}^{(m,n)} < p_{\text{bridge}}^{(m,n)}$ in any interval. Equivalently (and more numerically stable), compute the product of non-crossing probabilities over all intervals and subtract from one to get the corrected knock-in probability for the path; use this as the indicator weight. This reduces the bias from $O(\sqrt{\Delta t})$ to $O(\Delta t^{3/2})$ for typical barrier structures — a dramatic improvement.

Concrete numbers. Returning to the up-and-in call with $S_0 = 100$, $K = 100$, $U = 110$, $\sigma = 20\%$, $r = 5\%$, $T = 1$: at $N = 50$ and $M = 10{,}000$, the raw MC estimate is around $5.8$; with Brownian-bridge correction applied to the same simulation, the estimate rises to about $6.12$, within $0.5\%$ of the true value $6.15$. The bridge correction at $N = 50$ is therefore roughly equivalent in accuracy to brute-force refinement to $N\approx 500$ without correction — a factor-of-$10$ saving in compute. For barriers on high-frequency monitoring the advantage is even more pronounced.

### 10.7.7 Variance of the barrier estimator

A separate concern from bias is variance. The payoff $X = e^{-rT}(S_T - K)_+\,\mathbf{1}_{\{\max S\ge U\}}$ is zero on most paths (those that stay below $U$). When the parameters put the barrier deep out of the money — $U$ far above $S_0$, short maturity, low volatility — only a small fraction of paths knock in, and the MC estimator is dominated by a handful of triggering paths. Its sample variance can be very large relative to its mean.

Quantitatively: if only a fraction $p_{\text{knock}}$ of paths knock in and each contributing path's payoff has standard deviation $\sigma_X$, the overall payoff variance is roughly $p_{\text{knock}}\,\sigma_X^2 + p_{\text{knock}}(1 - p_{\text{knock}})\,\mu_X^2$, and the standard error scales as $\sqrt{(p_{\text{knock}}\,\sigma_X^2)/M}$ — i.e. needing $1/p_{\text{knock}}$ times more paths to achieve the same precision as the vanilla case. For a knock-in probability of $10\%$, we need $10\times$ more paths; for $1\%$, $100\times$ more. Rare-event MC is computationally unforgiving.

Two standard remedies. *Importance sampling* shifts the drift of the simulation to make knock-in more likely, then reweights by the Radon–Nikodym derivative (Chapter 5); a well-tuned IS can reduce variance by factors of $10$–$100$ for deeply out-of-the-barrier options. *Control variates* using the vanilla European call (whose expectation is known exactly from (10.14)–(10.15) and whose payoff correlates strongly with the barrier payoff on paths that do knock in) provide another order of magnitude of variance reduction for mildly-barriered options. In production, combining IS with a vanilla-call control and Brownian-bridge correction can drive barrier-MC run times from hours to seconds.

<!-- figure placeholder (see figures/ch02-*.png): three MC paths on [0, T] with barrier U drawn as a horizontal dashed line. Path A crosses U (circle at first-crossing time), pays (S_T - K)_+ at T; path B never crosses, pays 0; path C has a between-grid excursion above U that the coarse grid misses — illustrates discretisation bias. -->

### 10.7.8 Other path-dependent families

Having priced barriers, we preview the broader landscape of path-dependent options that the Monte-Carlo machinery handles cleanly.

**Asian options.** Payoffs depend on the *average* of the underlying over a window, such as $(\bar{S}_T - K)_+$ where $\bar{S}_T = (1/N)\sum_{n=1}^N S_{t_n}$ (arithmetic average). Arithmetic Asians have no closed form under GBM because the sum of log-normals is not itself log-normal; MC is the standard tool. The corresponding *geometric* average $\bar{S}^{\text{geo}}_T = \prod_{n=1}^N S_{t_n}^{1/N}$ *is* log-normal and admits a closed-form Black–Scholes-style pricer, which makes it a natural control variate for arithmetic Asian MC — typical variance reduction factors of $50$ to $500$. Asian options are popular on commodity markets (oil, gas, metals) because averaging smooths out daily-price noise and resists single-day manipulation of the settlement print.

**Lookback options.** Payoffs depend on the running extremum, such as $(\max_t S_t - K)_+$ (lookback call on running max) or $(S_T - \min_t S_t)_+$ (lookback put on running min). Lookbacks are the most path-sensitive of the classical exotics and carry prices substantially higher than vanilla equivalents — they capture the best achievable entry point, an upper bound on realisable profit. Closed forms exist under continuous-monitoring GBM (again via the reflection principle), making lookbacks a useful benchmark for MC implementations.

**Combinations.** Practitioners layer features routinely — an "Asian barrier call" pays $(\bar{S}_T - K)_+$ but only if the running max stays below some upper barrier; a "cliquet with knock-out" terminates the coupon stream if a down-barrier is hit. These combinations have no closed form and are handled by MC with custom payoff functions that walk each path and assemble the appropriate indicator and averaging structure.

**Autocallables.** Highly structured products that pay coupons on observation dates if the underlying is above a specified trigger, and auto-call (early redemption of principal) once the underlying breaches an upper barrier. Autocallable pricing involves a mix of path-dependence, multiple discrete monitoring dates, and early-termination optionality; MC is the workhorse, typically with quasi-Monte-Carlo low-discrepancy sequences to reduce variance on the discrete fixing dates.

All of these families share the same MC machinery: generate paths under $\mathbb{Q}$, apply the payoff functional to each path, average with discount. The engineering art is in (i) reducing variance through targeted techniques (Asian controls for Asians, bridge corrections for barriers, importance sampling for rare-event payoffs), (ii) handling the exact contractual details correctly (continuous vs. discrete monitoring, fixed vs. floating strikes, local vs. global conditions, business-day conventions), and (iii) extracting Greeks efficiently from the same sample.

---

## 10.8 Variance Reduction: Antithetic and Control Variates

Every production Monte-Carlo pricer uses variance reduction. The $M^{-1/2}$ convergence rate is fixed by the central limit theorem, but the *constant* in front — the standard deviation $\mathrm{sd}(X)$ of the estimator variate — can be driven down by orders of magnitude with modest effort. Two techniques are universal: antithetic variates and control variates. We cover them here as a bridge to the Heston MC of Chapter 14, where they become essential rather than merely convenient.

### 10.8.1 Antithetic variates

The antithetic-variates trick exploits the symmetry of the Gaussian distribution. For each standard-normal draw $Z^{(m)}$, also use $-Z^{(m)}$. The symmetrised payoff is

$$
\widetilde{X}^{(m)} \;=\; \frac{1}{2}\,\bigl[\,X(Z^{(m)}) + X(-Z^{(m)})\,\bigr],
\tag{10.33}
$$

and the antithetic estimator is $\widehat{V}_0^{\text{ant}} = (1/M)\sum_m \widetilde{X}^{(m)}$. The computational cost is $2M$ payoff evaluations, but the effective sample size from the variance-reduction standpoint is *not* $2M$ — the two draws $X(Z)$ and $X(-Z)$ are *negatively* correlated, and the variance of the average is

$$
\mathbb{V}[\widetilde{X}^{(m)}] \;=\; \frac{1}{4}\,\bigl[\,\mathbb{V}[X(Z)] + \mathbb{V}[X(-Z)] + 2\,\mathbb{C}[X(Z), X(-Z)]\,\bigr] \;=\; \frac{1}{2}\,\mathbb{V}[X]\,(1 + \rho),
\tag{10.34}
$$

where $\rho := \operatorname{Corr}(X(Z), X(-Z))$. If $\rho < 0$, the variance is strictly less than $\mathbb{V}[X]/2$, and antithetic sampling outperforms independent sampling even at equal cost.

When does antithetic sampling work? It works best when the payoff $X(Z)$ is *monotone* in $Z$ — calls are, puts are (after sign flip), digitals are, lookbacks almost are. For a monotone increasing $X$, $X(Z)$ and $X(-Z)$ have correlation close to $-1$ in the Gaussian tails, and the variance reduction factor can be substantial. For a European call at typical ATM parameters, antithetic sampling at $M$ pairs typically achieves a variance reduction of about $2$ relative to independent sampling at $M$ pairs (i.e., $2M$ independent draws) — equivalent to halving the standard error for the same number of payoff evaluations.

Antithetic sampling fails when the payoff is *symmetric in $Z$* — for example, a straddle $X(Z) = |S_T - K|$ has $X(Z) = X(-Z)$ at strike $K = S_0 e^{rT}$, and the antithetic pair is perfectly positively correlated, giving $\rho = +1$ and *no* variance reduction (actually an increase relative to a single draw, though not relative to two independent draws). A diagnostic: if antithetic sampling does not improve things, try a pilot run with $M = 1000$ independent vs $M = 500$ antithetic pairs and compare the empirical variances. This takes fifteen minutes and can save a day of debugging.

Antithetic extends naturally to path simulation: use the vector of Gaussians $(Z_1,\dots,Z_N)$ on one path and $(-Z_1,\dots,-Z_N)$ on the antithetic pair. The correlated-path structure preserves monotonicity at each time step, and the technique continues to work. For path-dependent payoffs like barriers and Asians the variance reduction is similar to the European case, typically a factor of $2$–$3$.

### 10.8.2 Control variates

The control-variate trick is more flexible and often more powerful than antithetic sampling. The idea: find an auxiliary variable $Y$ that is strongly correlated with the payoff $X$ and whose expectation $\mathbb{E}[Y]$ is known in closed form. Form the control-variate estimator

$$
\widehat{V}_0^{\text{cv}} \;=\; \widehat{m}_X \;+\; \beta\,\bigl(\mathbb{E}[Y] - \widehat{m}_Y\bigr),
\tag{10.35}
$$

where $\widehat{m}_X$ and $\widehat{m}_Y$ are the sample means of $X$ and $Y$ on the same $M$ paths, and $\beta$ is a constant to be chosen. The estimator is unbiased for any $\beta$ because $\mathbb{E}[\widehat{m}_Y] = \mathbb{E}[Y]$, so the correction term has mean zero; it has variance

$$
\mathbb{V}[\widehat{V}_0^{\text{cv}}] \;=\; \frac{1}{M}\,\bigl[\,\mathbb{V}[X] \;-\; 2\beta\,\mathbb{C}[X, Y] \;+\; \beta^2\,\mathbb{V}[Y]\,\bigr],
\tag{10.36}
$$

which is minimised at

$$
\beta^{\star} \;=\; \frac{\mathbb{C}[X, Y]}{\mathbb{V}[Y]},
\tag{10.37}
$$

giving the minimum variance

$$
\mathbb{V}[\widehat{V}_0^{\text{cv}}]\bigm|_{\beta = \beta^\star} \;=\; \frac{\mathbb{V}[X]}{M}\,\bigl(1 - \rho_{XY}^2\bigr),
\tag{10.38}
$$

where $\rho_{XY} = \operatorname{Corr}(X, Y)$. The variance reduction factor is $1/(1-\rho_{XY}^2)$: for $\rho_{XY} = 0.9$ the reduction is about $5\times$; for $0.99$ it is $50\times$; for $0.999$ it is $500\times$.

Choosing a good control. The essential question is what auxiliary $Y$ is known in closed form *and* strongly correlated with the target payoff. Several standard choices:

- **The underlying's terminal value $Y = S_T$**, with $\mathbb{E}^{\mathbb{Q}}[S_T] = S_0\,e^{rT}$ from the martingale property. Works well for European calls and puts, whose payoffs are monotone in $S_T$; typical correlation at ATM parameters is $\rho\approx 0.95$ for calls, giving about a $10\times$ variance reduction.
- **A vanilla Black–Scholes call on the same underlying**, with $\mathbb{E}[Y]$ given by (10.14)–(10.15). Works extremely well for barriers, digitals, and mildly exotic payoffs whose MC error on the vanilla portion would otherwise dominate; typical $\rho\approx 0.99$ for up-and-in calls, giving $50\times$ or more variance reduction.
- **A geometric-average Asian call** for arithmetic Asian pricing, where the geometric version has a closed-form BS-like formula and the arithmetic version does not. Typical $\rho > 0.99$ because the two averages are near-identical on almost every path; $100$–$500\times$ variance reduction.
- **The terminal value on a drift-shifted GBM** as a control for stochastic-volatility payoffs, linking the Heston case back to the Black–Scholes benchmark with matched $\mathbb{E}[S_T]$ and approximate variance.

Estimating $\beta^\star$. The optimal $\beta^\star$ depends on the unknown covariance structure. In practice one runs a pilot batch of $M_{\text{pilot}} = 1000$ or so paths, estimates $\widehat{\beta} = \widehat{\mathbb{C}}[X,Y]/\widehat{\mathbb{V}}[Y]$ from the pilot, and then runs the full $M$ batch with that $\widehat{\beta}$ plugged into (10.35). The plug-in estimator is no longer strictly unbiased (because $\widehat{\beta}$ and $\widehat{m}_X$, $\widehat{m}_Y$ are all correlated through the data), but the bias is $O(1/M)$ and negligible relative to the statistical error. More sophisticated implementations use a two-sample scheme: estimate $\widehat{\beta}$ from paths $1,\dots,M_1$, use those paths only for the second-stage estimator on paths $M_1+1,\dots,M$, and aggregate.

### 10.8.3 Combining techniques

Antithetic and control variates compose. Apply antithetic sampling to generate the path pairs, evaluate both the target payoff $X$ and the control payoff $Y$ on each antithetic pair, take the antithetic average of each, and then apply the control-variate correction (10.35) to the antithetic averages. The variance reductions multiply roughly (not exactly, because the correlations interact), and for a European call with a stock-price control and antithetic draws one routinely achieves total variance reduction factors of $30$–$50$ at essentially no added compute cost.

Beyond these two techniques the next layers — *stratified sampling* (partitioning the Gaussian space into equal-probability strata and drawing one sample per stratum), *importance sampling* (Radon–Nikodym reweighting of the simulation distribution), *Latin hypercube sampling*, and *quasi-Monte-Carlo with Sobol or Halton low-discrepancy sequences* — each provide additional factors of $2$–$100$ for the right payoff. A production pricer typically stacks two or three of these techniques; a research-grade pricer may stack four or five. The trader's mantra: "MC is universal but wasteful; always be improving the variance."

Variance-reduction techniques are indispensable for Heston Monte Carlo (Chapter 14) where the variance-process simulation itself introduces additional noise on top of the payoff noise, and where the closed-form benchmarks from Black–Scholes are no longer available but *approximate* BS controls based on a matched-moments log-normal still give large reductions. We return to this theme when we take up stochastic volatility.

### 10.8.4 A quick survey of the wider toolkit

For completeness, a brief summary of the other standard techniques a reader will encounter in the variance-reduction literature. We will not use these in the core chapter but they are the natural next layer for anyone building a production pricer.

**Stratified sampling.** Partition the Gaussian space into $k$ equal-probability strata $\{S_1,\dots,S_k\}$ and draw $M/k$ samples uniformly within each stratum, then re-weight each stratum by its probability mass (which is $1/k$ by construction). For a one-dimensional draw, use the inverse normal CDF: stratum $S_j = \{Z : \Phi^{-1}((j-1)/k) \le Z < \Phi^{-1}(j/k)\}$. The estimator is unbiased and its variance is always no worse than plain MC; for smooth payoffs it can be orders of magnitude better. The technique scales poorly with dimension — for $d$-dimensional Gaussian draws, stratifying each dimension into $k$ strata gives $k^d$ strata — so it is typically used only on the *dominant* direction (e.g. the terminal Brownian increment, which drives the bulk of the terminal payoff variance).

**Importance sampling.** Draw samples from an alternative distribution $\widetilde{\mathbb{P}}$ that concentrates probability mass on the region where the payoff is large, then reweight by the Radon–Nikodym derivative $\mathrm{d}\mathbb{P}/\mathrm{d}\widetilde{\mathbb{P}}$ from Chapter 5. The unbiased estimator is $\widehat{V}_0 = (1/M)\sum_m (\mathrm{d}\mathbb{P}/\mathrm{d}\widetilde{\mathbb{P}})(Z^{(m)})\cdot X(Z^{(m)})$ with $Z^{(m)}\sim\widetilde{\mathbb{P}}$. For a deep-OTM call, shifting the drift upward by $\mu_{\text{IS}}$ produces more ITM paths, and the RN weight $\exp(-\mu_{\text{IS}} Z - \tfrac{1}{2}\mu_{\text{IS}}^2 T)$ keeps the estimator unbiased. Optimal $\mu_{\text{IS}}$ is found by minimising the estimator variance — a separate optimisation that is often done offline or with an adaptive scheme. Variance reductions of $10$–$1000$ are common for rare-event payoffs; this is the technique of choice for deep-OTM options, tail-risk calculations, and credit-portfolio stress tests.

**Quasi-Monte-Carlo with low-discrepancy sequences.** Replace i.i.d. Gaussian draws with deterministic low-discrepancy sequences — Sobol, Halton, or Niederreiter — transformed by the inverse normal CDF. Low-discrepancy sequences fill the unit cube more uniformly than random samples, which for smooth integrands gives an error bound of $O((\log M)^d / M)$ rather than the probabilistic $O(M^{-1/2})$ of MC. For moderate dimensions ($d \lesssim 20$) the deterministic error bound is much smaller than the MC standard error at equal $M$. Quasi-MC pairs especially well with scrambling — randomisation of the sequence — to produce error bounds that are both small and unbiased, recovering the best of both worlds.

**Multilevel Monte Carlo.** For problems where the payoff depends on a discretised path with step $\Delta t$, the estimator $\widehat{V}_0 = \mathbb{E}[X_{\Delta t}]$ has bias $O(\Delta t)$ and MC variance $O(\mathrm{Var}[X_{\Delta t}]/M)$. Multilevel MC decomposes $\mathbb{E}[X_{\Delta t_L}] = \mathbb{E}[X_{\Delta t_0}] + \sum_\ell \mathbb{E}[X_{\Delta t_\ell} - X_{\Delta t_{\ell-1}}]$ and estimates each difference on its own grid, distributing the computational budget so that the coarser-grid levels (which are cheaper per path) carry more paths. The overall cost for error $\epsilon$ can be reduced from $O(\epsilon^{-3})$ to $O(\epsilon^{-2}(\log\epsilon)^2)$ or $O(\epsilon^{-2})$ depending on the payoff's regularity. Multilevel MC has become the preferred technique in SDE-discretisation-limited problems and is heavily used in academic and research-grade implementations.

**Longstaff–Schwartz regression.** For American-exercise and Bermudan payoffs, naive MC does not work because the optimal exercise policy depends on the continuation value, which is a conditional expectation that cannot be computed per-path. The Longstaff–Schwartz regression scheme runs MC paths forward, then runs a backward regression of realised continuation values on polynomial basis functions of the state; the fitted regression is used as the proxy continuation-value function. The resulting exercise policy is suboptimal but typically close to optimal, and the MC estimate is a low-biased lower bound on the true price. Combining Longstaff–Schwartz with any of the variance-reduction techniques above is standard practice for exotic American pricing.

A practitioner's rule of thumb. When in doubt, start with antithetic variates (always costs one line of code, typically halves variance). If the payoff has a closed-form correlated cousin, add a control variate (a few more lines, factor of $10$–$100$). If the payoff is deep OTM or rare-event, add importance sampling (non-trivial, factor of $10$–$1000$). If the dimensionality is moderate and the payoff is smooth, use Sobol with scrambling (moderate effort, factor of $2$–$100$). Stack them; each layer commutes approximately with the others.

---

## 10.9 Key Takeaways

1. **Why MC.** Monte-Carlo integration escapes the curse of dimensionality by achieving $O(M^{-1/2})$ error *independent of dimension*; its cost is $O(Md)$ compared to $O(N^d)$ for deterministic quadrature. Break-even dimension is around $d\approx 5$, and every realistic path-dependent pricing problem lives well above it.

2. **Strong Law of Large Numbers.** For i.i.d. draws of a random variable $X$ with $\mathbb{E}[|X|]<\infty$, the sample mean converges almost surely to $\mathbb{E}[X]$. For finite-variance $X$, the Central Limit Theorem gives the $M^{-1/2}$ error rate and the basis for confidence intervals.

3. **Standard error.** The MC estimator's standard error is $\widehat{\sigma}_{m_1} = \widehat{s}/\sqrt{M}$, where $\widehat{s}^2 = (1/(M-1))\sum(X^{(m)} - \widehat{m}_1)^2$ is the unbiased sample variance. Halving the error bar costs $4\times$ more paths.

4. **Exact GBM generator.** Under $\mathbb{Q}$, the lognormal increment $S_{t_n} = S_{t_{n-1}}\,\exp\{(r-\tfrac{1}{2}\sigma^2)\Delta t_n + \sigma\sqrt{\Delta t_n}\,Z_n\}$ with $Z_n \sim \mathcal{N}(0,1)$ i.i.d. is *exact at the grid points* — no discretisation bias. The missing-$\tfrac{1}{2}\sigma^2$ drift correction is the most common bug in home-grown MC pricers.

5. **European MC.** The MC estimator $\widehat{V}_0 = e^{-rT}\cdot (1/M)\sum_m \varphi(S_T^{(m)})$ should cross-check against Black–Scholes as a correctness test. At $M = 10{,}000$ and typical ATM parameters, the standard error is about $0.14$ on a call worth about $10.45$.

6. **Forward-starting (cliquet) atom.** The payoff $(S_{T_2} - \alpha S_{T_1})_+$ admits a closed form via iterated conditional expectation: $V_0 = S_0\,[\Phi(d_+) - \alpha\,e^{-r(T_2-T_1)}\,\Phi(d_-)]$ with $d_\pm = [\ln(1/\alpha) + (r\pm\tfrac{1}{2}\sigma^2)(T_2-T_1)]/(\sigma\sqrt{T_2-T_1})$. The $S_{T_1}$ factor cancels in the moneyness ratio, making $d_\pm$ deterministic and the price linear in $S_0$.

7. **Barrier MC.** The up-and-in call payoff $(S_T - K)_+\,\mathbf{1}_{\{\max_t S_t \ge U\}}$ is priced by simulation on a time grid with $\max_n S_{t_n}$ substituted for $\max_t S_t$. The substitution introduces a *downward* discretisation bias on the order of $\sqrt{\Delta t}$.

8. **Brownian-bridge correction.** Between two grid points with known endpoints, the conditional barrier-crossing probability has a closed form $\exp(-2\,\ln(U/S_{t_{n-1}})\,\ln(U/S_{t_n})/(\sigma^2\Delta t_n))$. Applying the correction reduces barrier MC bias from $O(\sqrt{\Delta t})$ to $O(\Delta t^{3/2})$ — equivalent to a factor-of-$10$ grid refinement.

9. **Rare-event variance.** Barrier payoffs that knock in with small probability give MC estimators with large relative variance. The path count scales inversely with the knock-in probability, making brute-force MC impractical for deeply-barriered structures; importance sampling and control variates are essential.

10. **Antithetic variates.** For each $Z$ draw, also use $-Z$. For monotone payoffs the antithetic pair has strongly negative correlation, and the variance of the average is less than half the variance of a single draw. Typical variance reduction factor $\approx 2$ on ATM European calls.

11. **Control variates.** Given an auxiliary $Y$ with known $\mathbb{E}[Y]$, form $\widehat{V}_0^{\text{cv}} = \widehat{m}_X + \beta(\mathbb{E}[Y] - \widehat{m}_Y)$ with $\beta^\star = \mathbb{C}[X,Y]/\mathbb{V}[Y]$. Variance reduction factor $1/(1 - \rho_{XY}^2)$. For $\rho = 0.99$, $50\times$; for $\rho = 0.999$, $500\times$.

12. **Combining techniques.** Antithetic and control variates compose; production pricers routinely stack two or three techniques for combined variance-reduction factors of $50$–$500$.

13. **Path-dependent families.** Asians, lookbacks, barriers, cliquets, autocallables — all handled by the same MC machinery: generate paths under $\mathbb{Q}$, apply the payoff functional path-by-path, discount and average. The engineering difficulty lies in variance reduction and in handling the exact contractual conventions (continuous vs discrete monitoring, fixed vs floating strikes, business-day conventions).

14. **Bridge to Chapter 14.** Heston Monte Carlo introduces a second simulation dimension (the variance process) and its own set of discretisation biases (the square-root process near zero requires careful handling via the full-truncation Euler or the exact QE scheme of Andersen). The variance-reduction toolkit developed here transfers directly, with BS-based controls replaced by matched-moments lognormal controls.

---

## 10.10 Reference Formulas

Strong law of large numbers.
$$\lim_{M\to+\infty}\,\frac{1}{M}\sum_{m=1}^{M} X^{(m)} \;=\; \mathbb{E}[X] \quad\text{a.s., provided }\mathbb{E}[|X|]<\infty.$$

Central limit theorem (Monte-Carlo confidence interval).
$$\sqrt{M}\,(\widehat{m}_M - \mathbb{E}[X]) \xrightarrow{d} \mathcal{N}(0,\mathbb{V}[X]), \qquad \widehat{m}_M \pm 1.96\,\widehat{\sigma}_{m_1}\ \text{is a 95\% CI}.$$

Sample mean and Monte-Carlo standard error.
$$\widehat{m}_1 = \frac{1}{M}\sum_{m=1}^M X^{(m)}, \qquad \widehat{\sigma}_{m_1} = \frac{1}{\sqrt{M}}\left(\frac{1}{M-1}\sum_{m=1}^M (X^{(m)} - \widehat{m}_1)^2\right)^{\!1/2}.$$

Exact lognormal GBM path simulation.
$$S_{t_n} = S_{t_{n-1}}\,\exp\!\bigl\{(r - \tfrac{1}{2}\sigma^2)\Delta t_n + \sigma\sqrt{\Delta t_n}\,Z_n\bigr\}, \quad Z_n \stackrel{\text{iid}}{\sim}_{\mathbb{Q}}\mathcal{N}(0,1).$$

European MC estimator.
$$\widehat{V}_0 = e^{-rT}\cdot\frac{1}{M}\sum_{m=1}^M \varphi\!\left(S_0\,e^{(r-\tfrac{1}{2}\sigma^2)T + \sigma\sqrt{T}\,Z^{(m)}}\right).$$

Forward-starting (cliquet) call price.
$$V_0 = S_0\,\bigl[\Phi(d_+) - \alpha\,e^{-r(T_2-T_1)}\,\Phi(d_-)\bigr], \qquad d_\pm = \frac{\ln(1/\alpha) + (r\pm\tfrac{1}{2}\sigma^2)(T_2-T_1)}{\sigma\sqrt{T_2-T_1}}.$$

Up-and-in call payoff and MC estimator.
$$\varphi = (S_T - K)_+\,\mathbf{1}_{\{\max_{0\le t\le T} S_t \ge U\}}, \qquad \widehat{V}_0 = e^{-rT}\cdot\frac{1}{M}\sum_{m=1}^M (S_T^{(m)} - K)_+\,\mathbf{1}_{\{\max_n S_{t_n}^{(m)}\ge U\}}.$$

Brownian-bridge crossing probability (continuous barrier correction).
$$\mathbb{P}\!\left(\max_{t\in[t_{n-1},t_n]} S_t \ge U \,\Big|\, S_{t_{n-1}}, S_{t_n}\right) = \exp\!\left(-\,\frac{2\,\ln(U/S_{t_{n-1}})\,\ln(U/S_{t_n})}{\sigma^2\,\Delta t_n}\right)\quad \text{for } U>\max(S_{t_{n-1}}, S_{t_n}).$$

In-out parity.
$$V^{\text{up-and-in call}} + V^{\text{up-and-out call}} = V^{\text{vanilla call}}.$$

Antithetic variate estimator (single draw).
$$\widetilde{X}^{(m)} = \tfrac{1}{2}\bigl[X(Z^{(m)}) + X(-Z^{(m)})\bigr], \qquad \mathbb{V}[\widetilde{X}^{(m)}] = \tfrac{1}{2}\mathbb{V}[X]\,(1+\rho),\ \rho=\mathrm{Corr}(X(Z), X(-Z)).$$

Control variate estimator and optimal coefficient.
$$\widehat{V}_0^{\text{cv}} = \widehat{m}_X + \beta\bigl(\mathbb{E}[Y] - \widehat{m}_Y\bigr), \qquad \beta^\star = \frac{\mathbb{C}[X,Y]}{\mathbb{V}[Y]}, \qquad \mathbb{V}[\widehat{V}_0^{\text{cv}}]\bigm|_{\beta^\star} = \frac{\mathbb{V}[X]}{M}(1-\rho_{XY}^2).$$
