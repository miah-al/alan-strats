# Chapter 4 — Feynman-Kac and the SDE-PDE Bridge

This chapter uses the Ch. 3 toolkit for its first major payoff: the *Feynman–Kac* theorem, the bidirectional bridge between a linear parabolic PDE and the conditional expectation of a diffusion-driven payoff. Every pricing problem in the rest of the guide — Black–Scholes (Ch. 6), Vasicek bonds (Ch. 12), caplets (Ch. 14) — is one substitution into the same template.

We establish the duality in three forms — zero-drift BM, constant-coefficient drifted BM with discounting, and full state-time-dependent coefficients — and compute three worked examples to see the machinery turn. The Black–Scholes derivation itself is deferred to Ch. 6 (twice: once via hedging, once as a Feynman–Kac corollary); measure change is Ch. 5.

## 4.1 Motivation — Why an SDE-PDE Bridge Matters

Every pricing problem reduces to one of two computations: solve a backward parabolic PDE on a space-time grid, or average a random payoff over diffusion paths. These look like different calculations — finite-difference code on a mesh vs Monte Carlo on trajectories — and Feynman–Kac says they are the same calculation.

Routing is practical. Low-dimensional smooth problems (single-asset vanilla, single-rate caplet) are faster via PDE — a Crank–Nicolson grid converges in milliseconds. High-dimensional or path-dependent problems (baskets, exotics, multi-factor rates) are faster via Monte Carlo — $1/\sqrt{N_{\text{paths}}}$ error independent of state dimension. American features favour PDEs (exercise boundary embeds in the grid); path-dependent features favour MC (track a functional along the path). Feynman–Kac guarantees the answers agree.

Every linear pricing PDE in this guide — Black–Scholes, Vasicek, Hull–White, Heston, the caplet equations of Ch. 14 — is a Feynman–Kac PDE for some SDE and some discount rate. Mastering the bridge in its full state-dependent form gives a single theorem that, properly instantiated, prices every linear problem in the guide.

---

## 4.2 The Zero-Drift Feynman-Kac Theorem

Start with driftless, undiscounted BM and a terminal payoff. Every later version is a decoration of this base case.

Let $X$ be a standard Brownian motion, $T > 0$ a horizon, and $\varphi : \mathbb{R} \to \mathbb{R}$ a payoff with polynomial growth. Consider the backward Cauchy problem

$$
\begin{cases}
\partial_t f(t, x) \;+\; \tfrac{1}{2}\,\partial_{xx} f(t, x) \;=\; 0, & (t, x) \in [0, T) \times \mathbb{R}, \\[2pt]
f(T, x) \;=\; \varphi(x).
\end{cases}
\tag{4.1}
$$

Feynman-Kac asserts that this PDE is *equivalent* to the probabilistic representation

$$
\boxed{\;f(t, x) \;=\; \mathbb{E}_{t, x}\!\left[\,\varphi(X_T)\,\right] \;\equiv\; \mathbb{E}\!\left[\,\varphi(X_T)\,\big|\,X_t = x\,\right].\;}
\tag{4.2}
$$

The biconditional carries both directions. **PDE $\Rightarrow$ expectation:** a classical solution of $(4.1)$ admits the expectation representation $(4.2)$. **Expectation $\Rightarrow$ PDE:** conversely, the function $x \mapsto \mathbb{E}_{t,x}[\varphi(X_T)]$ automatically satisfies $(4.1)$. In practice one direction or the other is the easier computation, and Feynman-Kac lets us freely pick.

![Feynman-Kac duality: the same option price can be computed as the solution of a backward parabolic PDE (left, finite differences) or as a discounted risk-neutral expectation (right, Monte Carlo). Most production vol desks run both — PDE for vanillas, MC for path-dependents — and use one as a sanity check on the other](figures/ch04-pde-vs-expectation.png)

### 4.2.1 What the PDE is

The PDE in $(4.1)$ is the reverse heat equation — the Kolmogorov backward equation for BM. The terminal payoff plays the role of initial heat distribution; the PDE smooths it backward from $T$ to $t$. Every qualitative feature of diffusion — smoothing of discontinuities, exponential decay of modes — translates directly into option-price behaviour.

![Heat-equation analogy](figures/ch04-heat-analogy.png)
*As $t$ moves backward from $T$ toward $0$, the terminal payoff $\varphi$ diffuses and smooths: kinks (vanilla calls) round off, step functions (digitals) bloom into Gaussian-shaped bumps. Every option price is literally a smoothed payoff, where the smoothing kernel is a Gaussian of width $\sqrt{T-t}$.*

![Heat-kernel evolution of a peaked initial profile under $u_t = \tfrac{1}{2} u_{xx}$ at $t = 0.05, 0.2, 0.5, 1.0, 2.0$. Mass spreads as $\sqrt{t}$ — this *is* the Black-Scholes price evolution after the standard log-transform (Ch. 6), and is why a digital option printed sharply at expiry diffuses into a smooth bump as we step back in time](figures/ch04-heat-kernel.png)

### 4.2.2 What the expectation is

The right-hand side of $(4.2)$ averages $\varphi(X_T)$ over Brownian trajectories starting at $(t, x)$. Because BM is Markov, the expectation depends only on $(t, x)$, never on how we got to $x$ — which is why $f$ is a function of two real variables rather than a functional on path space.

### 4.2.3 Path-integral intuition — why the equivalence is not magic

Markov plus local dynamics force $(4.1)$. The scoreboard obeys the tower identity

$$
f(t, x) \;=\; \mathbb{E}\!\left[\,f(t + \mathrm{d}t, \, x + \mathrm{d}W)\,\right].
\tag{4.3}
$$

Taylor-expand the right-hand side, use $\mathbb{E}[\mathrm{d}W] = 0$ and the Itô shorthand $(\mathrm{d}W)^2 = \mathrm{d}t$, divide by $\mathrm{d}t$, and the residual $0 = \partial_t f + \tfrac12 \partial_{xx} f$ is the PDE. The terminal condition is automatic: at $t = T$ the scoreboard reads the payoff directly. The next section turns this sketch into a proof.

---

## 4.3 A Martingale Derivation of the Backward PDE

The clean derivation: $f(s, X_s)$ is a martingale by the tower property, Itô applied to a martingale forces the drift to vanish, and that vanishing drift is the PDE. This three-move template — (i) write the price as a conditional expectation, (ii) apply Itô, (iii) kill the drift — is reused in every pricing PDE derivation in the guide.

### 4.3.1 Setup and the candidate

Fix a horizon $T$ and a payoff $\varphi : \mathbb{R} \to \mathbb{R}$ with polynomial growth. Let $X_t$ be a standard Brownian motion. Define the candidate pricing function

$$
f(t, x) \;\equiv\; \mathbb{E}\!\left[\,\varphi(X_T)\,\big|\,X_t = x\,\right] \;=\; \mathbb{E}_{t,x}[\varphi(X_T)].
\tag{4.4}
$$

The question the proof will answer is: *what PDE does $f$ satisfy as a function of $(t, x)$?* The answer is $(\partial_t + \tfrac12 \partial_{xx})f = 0$ with terminal data $f(T, x) = \varphi(x)$, derivable from (a) iterated expectation and (b) Itô's lemma applied to $f(t, X_t)$.

### 4.3.2 The auxiliary process $\eta_s = f(s, X_s)$

Define a stochastic process indexed by the intermediate time $s \in [t, T]$:

$$
\eta_s \;\equiv\; f(s, X_s) \;=\; \mathbb{E}\!\left[\,\varphi(X_T)\,\big|\,X_s\,\right].
\tag{4.5}
$$

Geometrically, $\eta_s$ is "the best current guess of $\varphi(X_T)$ given everything known up to time $s$." Because $X$ is Markov, conditioning on the full filtration $\mathcal{F}_s$ of the Brownian motion collapses to conditioning on the single random variable $X_s$:

$$
\mathbb{E}\!\left[\varphi(X_T) \,\big|\, \mathcal{F}_s\right] \;=\; \mathbb{E}\!\left[\varphi(X_T) \,\big|\, X_s\right] \;=\; f(s, X_s) \;=\; \eta_s.
\tag{4.6}
$$

The first equality is the Markov property of Brownian motion (independent increments collapse the filtration dependence to the current state); the second is the definition of $f$; the third is notation. This three-step unwinding is worth memorising because it reappears in every measure-change, numeraire-swap, and forward-measure derivation in later chapters.

### 4.3.3 Tower law $\Rightarrow$ $\eta$ is a martingale

Claim. The process $s \mapsto \eta_s$ is a martingale in $s$ under the natural filtration $\{\mathcal{F}_s\}$ of $X$. Concretely, for any $t \le s_1 \le s_2 \le T$,

$$
\mathbb{E}\!\left[\eta_{s_2} \,\big|\, \mathcal{F}_{s_1}\right] \;=\; \eta_{s_1}.
\tag{4.7}
$$

*Proof.* Plug in the definition:

$$
\mathbb{E}[\eta_{s_2} | \mathcal{F}_{s_1}] \;=\; \mathbb{E}\!\left[\,\mathbb{E}[\varphi(X_T) | \mathcal{F}_{s_2}]\,\big|\,\mathcal{F}_{s_1}\right].
$$

The outer expectation is over information up to $s_1$; the inner expectation is over information up to $s_2 \ge s_1$. Apply the tower property of conditional expectations — $\mathbb{E}[\mathbb{E}[A | \mathcal{G}] | \mathcal{H}] = \mathbb{E}[A | \mathcal{H}]$ whenever $\mathcal{H} \subseteq \mathcal{G}$ — with $\mathcal{H} = \mathcal{F}_{s_1}$ and $\mathcal{G} = \mathcal{F}_{s_2}$ (the latter is indeed finer because more time has passed):

$$
\mathbb{E}\!\left[\,\mathbb{E}[\varphi(X_T) | \mathcal{F}_{s_2}]\,\big|\,\mathcal{F}_{s_1}\right] \;=\; \mathbb{E}[\varphi(X_T) | \mathcal{F}_{s_1}] \;=\; \eta_{s_1}.
$$

Therefore $\eta_{s_1} = \mathbb{E}[\eta_{s_2} | \mathcal{F}_{s_1}]$, the martingale property. $\square$

The argument uses only nesting of filtrations plus iterated expectation. *Any* process of the form "conditional expectation of a fixed $\mathcal{F}_T$-measurable random variable" is a martingale (a *Doob martingale*). The payoff $\varphi(X_T)$ is the "closing" random variable; $\eta_s$ is the stream of running conditional expectations.

### 4.3.4 Itô's lemma on $\eta_s = f(s, X_s)$

Having established that $\eta_s$ is a martingale, we now apply Itô's lemma to read off what PDE $f$ must satisfy. Assume $f \in C^{1,2}([0,T) \times \mathbb{R})$ — continuously differentiable in $t$ once, in $x$ twice. This is an a-posteriori regularity result for Feynman-Kac solutions with smooth enough payoffs, and we take it for granted here. Apply Itô's lemma II from Chapter 3 with $X_s = W_s$:

$$
\mathrm{d}\eta_s \;=\; \partial_t f(s, X_s)\,\mathrm{d}s \;+\; \partial_x f(s, X_s)\,\mathrm{d}X_s \;+\; \tfrac12\,\partial_{xx} f(s, X_s)\,(\mathrm{d}X_s)^2.
\tag{4.8}
$$

Using the Itô shorthand $(\mathrm{d}X_s)^2 = \mathrm{d}s$ and grouping the $\mathrm{d}s$ and $\mathrm{d}X_s$ terms,

$$
\mathrm{d}\eta_s \;=\; \underbrace{\left[\,\partial_t f + \tfrac12\,\partial_{xx} f\,\right]}_{\text{drift}}\mathrm{d}s \;+\; \underbrace{\partial_x f}_{\text{diffusion}}\,\mathrm{d}X_s,
\tag{4.9}
$$

with both partial derivatives evaluated at $(s, X_s)$.

### 4.3.5 Drift-killing identity

The diffusion term $\partial_x f\,\mathrm{d}X_s$ integrated against $\mathrm{d}W$ is a pure stochastic integral, hence a martingale by the construction of the Itô integral in Chapter 3. So the difference between $\eta_s$ and the martingale $\int \partial_x f\,\mathrm{d}X$ is the deterministic drift term $\int[\partial_t f + \tfrac12 \partial_{xx} f]\,\mathrm{d}s$. But we proved in §4.3.3 that $\eta_s$ is already a martingale. Subtracting a martingale from a martingale leaves a martingale, so the drift term $\int[\partial_t f + \tfrac12 \partial_{xx} f]\,\mathrm{d}s$ is itself a martingale.

Now the key fact: this drift is a process of *bounded variation* (it is an ordinary Riemann integral in $s$), and the only continuous martingale of finite variation is the zero process. (By the Doob-Meyer decomposition, the finite-variation part of a continuous semimartingale starts at zero and is uniquely identified by the drift; combining "is a martingale" with "finite-variation part starts at zero" forces the integrand to vanish identically.) Therefore the drift vanishes:

$$
\int_t^s\!\left[\partial_t f(u, X_u) + \tfrac12\partial_{xx}f(u, X_u)\right]\mathrm{d}u \;\equiv\; 0 \quad \text{for every } s \in [t, T].
$$

Because this holds for every path (including paths visiting every real number at arbitrarily chosen times) and the integrand is continuous, the integrand must vanish pointwise:

$$
\boxed{\;\partial_t f(t, x) + \tfrac12\,\partial_{xx} f(t, x) \;=\; 0\;} \qquad \text{for all } (t, x) \in [0, T) \times \mathbb{R}.
\tag{4.10}
$$

This is the Kolmogorov backward equation, and we have just derived it from the martingale property of the Doob-closed process $\eta$. $\square$

---

## 4.4 Boundary Condition and Summary of the Zero-Drift Case

The derivation of §4.3 produced the PDE $(4.10)$ from the martingale property of $\eta$, but we still need to verify the terminal condition $f(T, x) = \varphi(x)$. That is immediate from the definition of $f$: at $s = T$ the conditioning has frozen the Brownian motion at its terminal value, so

$$
\eta_T \;=\; \mathbb{E}[\varphi(X_T) | X_T] \;=\; \varphi(X_T),
$$

and evaluating at $X_T = x$ gives $f(T, x) = \varphi(x)$. The boundary data is *built into* the probabilistic construction.

### 4.4.1 What the zero-drift theorem says

Putting the pieces of §§4.2–4.3 together:

> **Zero-drift Feynman-Kac.** Let $X$ be a standard Brownian motion and let $\varphi : \mathbb{R} \to \mathbb{R}$ have polynomial growth. The function $f(t, x) = \mathbb{E}_{t, x}[\varphi(X_T)]$ is the (unique classical) solution of the backward heat equation $\partial_t f + \tfrac12 \partial_{xx} f = 0$ on $[0, T) \times \mathbb{R}$ with terminal data $f(T, \cdot) = \varphi(\cdot)$.

The three ingredients of the proof — Markov collapse, Doob-martingale of expectations, drift-kill via Itô — will *all* reappear in every subsequent generalisation. The only thing that changes is what one drops into the Itô decomposition.

### 4.4.2 A remark on regularity

The derivation of §4.3 assumed $f \in C^{1,2}$. For discontinuous payoffs (digitals, indicators) standard practice is either to approximate by smooth $\varphi_n \to \varphi$ (Gaussian-kernel smoothing handles the limit) or to invoke viscosity solutions. The $C^{1,2}$ hypothesis is convenient but not essential.

---

## 4.5 Example 1 — Linear Payoff $\varphi(x) = x$

A baseline sanity check. Consider the Cauchy problem

$$
\begin{cases}
\partial_t f + \tfrac12 \partial_{xx} f \;=\; 0, \\
f(T, x) \;=\; x.
\end{cases}
\tag{4.12}
$$

By Feynman-Kac $(4.2)$,

$$
f(t, x) \;=\; \mathbb{E}_{t, x}[X_T],
$$

where $X$ is a standard Brownian motion. Brownian increments are Gaussian,

$$
X_T - X_t \;\sim\; \mathcal{N}(0, T - t), \qquad \text{so} \qquad X_T \stackrel{d}{=} x + \sqrt{T - t}\,Z, \quad Z \sim \mathcal{N}(0, 1).
$$

Therefore

$$
f(t, x) \;=\; \mathbb{E}_{t, x}\!\left[\,x + \sqrt{T - t}\,Z\,\right] \;=\; x \;+\; \sqrt{T - t}\cdot\mathbb{E}[Z] \;=\; x.
\tag{4.13}
$$

**PDE verification.** With $f(t, x) = x$, $\partial_t f = 0$, $\partial_x f = 1$, $\partial_{xx} f = 0$, so $\partial_t f + \tfrac12 \partial_{xx} f = 0$. Terminal condition $f(T, x) = x$ holds by inspection. Both branches agree.

### 4.5.1 Why this answer is natural

Linear payoffs have zero convexity; Jensen is equality and the expectation equals the initial state. A linear payoff is a forward on a driftless underlying — no convexity premium. As soon as the payoff bends, the Itô correction bites.

---

## 4.6 Example 2 — Quadratic Payoff $\varphi(x) = x^2$

The first nontrivial case — and the simplest variance-swap-style replication. Solve

$$
\begin{cases}
\partial_t f + \tfrac12 \partial_{xx} f \;=\; 0, \\
f(T, x) \;=\; x^2.
\end{cases}
\tag{4.14}
$$

Feynman-Kac gives

$$
f(t, x) \;=\; \mathbb{E}_{t, x}[X_T^2] \;=\; \mathbb{E}_{t, x}\!\left[\,\big((X_T - X_t) + X_t\big)^2\,\right],
$$

with $X_T - X_t \sim \mathcal{N}(0, T - t)$ and $X_t = x$ under $\mathbb{E}_{t, x}$. Expanding the square and taking expectations term by term:

$$
f(t, x) \;=\; \mathbb{E}_{t, x}\!\left[\,(X_T - X_t)^2 + 2 X_t (X_T - X_t) + X_t^2\,\right] \;=\; (T - t) \;+\; 0 \;+\; x^2,
$$

where the three contributions come from $\mathbb{E}[(X_T - X_t)^2] = \mathrm{Var}(X_T - X_t) = T - t$, $\mathbb{E}[(X_T - X_t)] = 0$, and $\mathbb{E}[X_t^2 | X_t = x] = x^2$. Hence

$$
\boxed{\;f(t, x) \;=\; x^2 + (T - t)\;}.
\tag{4.15}
$$

**PDE verification.** With $f(t, x) = x^2 + (T - t)$, $\partial_t f = -1$, $\partial_{xx} f = 2$, so $\partial_t f + \tfrac12 \partial_{xx} f = -1 + 1 = 0$. At $t = T$: $f(T, x) = x^2 + 0 = x^2$. Both the PDE and the terminal condition are satisfied.

### 4.6.1 Convexity reading and variance-swap interpretation

The extra $(T - t)$ in $(4.15)$ is the *time-value of convexity*: a convex payoff rewards variance, and Brownian increments supply exactly $\mathrm{Var}(X_T | X_t = x) = T - t$. Equivalently, Itô's lemma applied to $F(x) = x^2$ gives $X_T^2 = X_t^2 + 2\!\int_t^T X_s\,\mathrm{d}X_s + (T - t)$; the middle martingale term vanishes under expectation and recovers $(4.15)$. The same identity prices a variance swap with strike $x^2$ in the driftless, no-discount setting: the fair forward value is $x^2 + (T - t)$.

![Quadratic payoff MC vs PDE solution](figures/ch04-quadratic-mc-vs-pde.png)
*Sanity check of $(4.15)$: Monte-Carlo averages of $X_T^2$ at a grid of initial states $x_0$ (red dots) fall exactly on the PDE closed form $x_0^2 + T$ (blue curve). The $+T$ offset is the "time-value of variance" — the convexity premium that Brownian motion pays out for a quadratic payoff.*

---

## 4.7 Example 3 — Exponential Payoffs $\varphi(x) = e^{ax}$

The log-space analogue of every log-normal pricing problem in the guide: substitute $X = \ln S$ and the answer feeds into Black–Scholes, Black-76, and most rate/credit closed forms.

### 4.7.1 Base case $\varphi(x) = e^{-x}$

Solve

$$
\begin{cases}
\partial_t f + \tfrac12 \partial_{xx} f \;=\; 0, \\
f(T, x) \;=\; e^{-x}.
\end{cases}
\tag{4.16}
$$

Feynman-Kac gives

$$
f(t, x) \;=\; \mathbb{E}_{t, x}[\,e^{-X_T}\,].
$$

Because $X_T | X_t = x$ is $\mathcal{N}(x, T - t)$, apply the Gaussian moment-generating function $\mathbb{E}[e^{\lambda Y}] = e^{\lambda \mu + \tfrac12 \lambda^2 \sigma^2}$ with $\lambda = -1$, $\mu = x$, $\sigma^2 = T - t$:

$$
\boxed{\;f(t, x) \;=\; e^{-x + \tfrac12 (T - t)}\;}.
\tag{4.17}
$$

**PDE verification.** With $f = e^{-x + \tfrac12(T - t)}$: $\partial_t f = -\tfrac12 f$, $\partial_x f = -f$, $\partial_{xx} f = f$. Then $\partial_t f + \tfrac12 \partial_{xx} f = -\tfrac12 f + \tfrac12 f = 0$. Terminal condition $f(T, x) = e^{-x}$ holds.

**Jensen bump.** Notice $f(t, x) = e^{-x} \cdot e^{\tfrac12 (T - t)}$ — the answer exceeds the payoff evaluated at the mean $e^{-x}$ by the factor $e^{\tfrac12(T - t)}$. This is the *convexity premium*. In the log variable this is exactly the $\tfrac12 \sigma^2 t$ Itô correction that will reappear in the Black-Scholes formula. Its sign follows from Jensen's inequality applied to the convex function $e^{-x}$: $\mathbb{E}[e^{-X_T}] \ge e^{-\mathbb{E}[X_T]} = e^{-x}$, with strict inequality whenever $X_T$ has nonzero variance.

### 4.7.2 General exponent $\varphi(x) = e^{ax}$

A one-parameter generalisation that shows the convexity bump scales as $a^2$, not $|a|$. Solve

$$
\begin{cases}
\partial_t f + \tfrac12 \partial_{xx} f \;=\; 0, \\
f(T, x) \;=\; e^{ax},
\end{cases} \qquad a \in \mathbb{R}.
\tag{4.18}
$$

By Feynman-Kac, using $X_T = x + (X_T - X_t)$ with $X_T - X_t \sim \mathcal{N}(0, T - t)$,

$$
f(t, x) \;=\; \mathbb{E}_{t, x}[\,e^{a X_T}\,] \;=\; e^{ax}\cdot \mathbb{E}[\,e^{a (X_T - X_t)}\,] \;=\; e^{ax}\cdot e^{\tfrac12 a^2 (T - t)},
$$

using the Gaussian MGF with $\lambda = a$, $\sigma^2 = T - t$. Compactly,

$$
\boxed{\;f(t, x) \;=\; \exp\!\left\{\,a\,x \;+\; \tfrac12\,a^2\,(T - t)\,\right\}\;}.
\tag{4.19}
$$

**PDE verification.** Let $\gamma = \tfrac12 a^2$. Then $f = e^{ax + \gamma(T - t)}$ gives $\partial_t f = -\gamma f$, $\partial_x f = a f$, $\partial_{xx} f = a^2 f$. Plugging into the PDE:

$$
\partial_t f + \tfrac12 \partial_{xx} f \;=\; -\gamma f + \tfrac12 a^2 f \;=\; -\tfrac12 a^2 f + \tfrac12 a^2 f \;=\; 0. \quad\checkmark
$$

Terminal: $f(T, x) = e^{ax + 0} = e^{ax}$.

![Monte-Carlo sanity check for §§4.5–4.7 closed forms](figures/ch04-fk-mc-check.png)
*For each of the three worked payoffs (linear $x$, quadratic $x^2$, exponential $e^{ax}$ with $a=0.8$), Monte-Carlo averaging over $N$ Brownian endpoints $X_T \sim \mathcal{N}(x_0, T)$ converges at rate $1/\sqrt{N}$ to the Gaussian-MGF closed form from $(4.13)$–$(4.19)$.*

![FD vs MC error convergence on a 1-D Feynman-Kac benchmark ($\mathbb{E}[X_T^2]$): finite-difference error decays as $N^{-2}$, MC as $M^{-1/2}$. FD dominates in 1-3D; MC's dimension-free constant wins for high-dimensional baskets (the curse-of-dimensionality cliff sits around $d=5$)](figures/ch04-fd-vs-mc.png)

---

## 4.8 Feynman-Kac with Drift, Diffusion, and Discounting

Real pricing needs three extensions: a nonzero drift, an arbitrary diffusion coefficient, and a discount on the payoff. We add all three at once.

### 4.8.1 Statement

Let $a \in \mathbb{R}$, $b > 0$, and $c \in \mathbb{R}$ be constants. Consider the backward Cauchy problem with a lower-order term:

$$
\begin{cases}
\partial_t f(t, x) \;+\; a\,\partial_x f(t, x) \;+\; \tfrac12\,b^2\,\partial_{xx} f(t, x) \;=\; c\,f(t, x), \\[2pt]
f(T, x) \;=\; \varphi(x).
\end{cases}
\tag{4.20}
$$

The probabilistic representation of the solution is

$$
\boxed{\;f(t, x) \;=\; \mathbb{E}_{t, x}\!\left[\,e^{-c(T - t)}\,\varphi(X_T)\,\right],\;}
\tag{4.21}
$$

where $X = (X_s)_{s \ge 0}$ is a drifted Brownian motion solving

$$
\mathrm{d}X_s \;=\; a\,\mathrm{d}s \;+\; b\,\mathrm{d}W_s, \qquad W \text{ a standard BM},
\tag{4.22}
$$

i.e. $X_s = X_0 + a\,s + b\,W_s$ (arithmetic Brownian motion with drift $a$ and volatility $b$).

![Characteristic curves $x = x_0 + at$ of the pure-transport operator $\partial_t f + a\partial_x f = 0$ (blue) and sample paths of the full SDE with diffusion (orange) around one of them. Feynman-Kac sews the deterministic transport to the stochastic spread — the same factorisation that decomposes a corporate-bond return into "forward roll-down" plus "credit shock"](figures/ch04-characteristics.png)

### 4.8.2 Proof sketch

Start from the expectation $f(t, x) = \mathbb{E}_{t, x}[e^{-c(T - t)}\varphi(X_T)]$ and apply Itô's lemma to the auxiliary process

$$
g_s \;\equiv\; e^{-c(s - t)}\,f(s, X_s), \qquad s \in [t, T].
$$

Compute $\mathrm{d}g_s$ using the product rule plus Itô's lemma III applied to $f(s, X_s)$:

$$
\mathrm{d}g_s \;=\; e^{-c(s - t)}\!\left\{-c\,f\,\mathrm{d}s \;+\; \left[\partial_t f + a\,\partial_x f + \tfrac12 b^2 \partial_{xx} f\right]\mathrm{d}s \;+\; b\,\partial_x f\,\mathrm{d}W_s\right\}.
\tag{4.23}
$$

For $g_s$ to be a martingale — which it must be, because $g_T = e^{-c(T - t)}\varphi(X_T)$ and conditional expectations of fixed random variables are martingales — the $\mathrm{d}s$ drift must vanish:

$$
-c\,f + \partial_t f + a\,\partial_x f + \tfrac12 b^2 \partial_{xx} f \;=\; 0,
$$

which is exactly the PDE $(4.20)$. Conversely, if $f$ satisfies the PDE, the drift of $g_s$ is identically zero; $g_s$ is therefore a martingale, and taking $\mathbb{E}_{t, x}$ of $g_t = f(t, x)$ and $g_T = e^{-c(T - t)}\varphi(X_T)$ yields the representation $(4.21)$.

The two-way proof is the essence of Feynman-Kac: the PDE *is* the drift-killing condition for $e^{-c(s - t)} f(s, X_s)$, and any function satisfying that PDE automatically represents an expectation.

### 4.8.3 Role of each coefficient

Each term in $(4.20)$ has a direct counterpart in $(4.21)$:

| PDE term | SDE / expectation counterpart |
|---|---|
| $a\,\partial_x f$ | drift of $X$: each path is pushed by $a\,\mathrm{d}s$ per step. |
| $\tfrac12 b^2\,\partial_{xx} f$ | diffusion of $X$: paths spread with variance $b^2\,\mathrm{d}s$ per step. |
| $-c\,f$ | exponential decay / discount factor $e^{-c(T - t)}$ applied to the payoff. |
| terminal $f(T, x) = \varphi(x)$ | the expectation at $s = T$ is literally $\varphi(X_T)$ with $X_T = x$. |

The dictionary reading of $(4.20) \Leftrightarrow (4.21)$: *"$a$ and $b$ pick the law of $X$; $c$ attaches a per-unit-time discount to every path."*

### 4.8.4 Worked case: exponential payoff with drift, diffusion, and discount

Solve $(4.20)$ with $\varphi(x) = e^{-x}$:

$$
\begin{cases}
\partial_t f + a\,\partial_x f + \tfrac12 b^2 \partial_{xx} f \;=\; c\,f, \\
f(T, x) \;=\; e^{-x}.
\end{cases}
\tag{4.24}
$$

By $(4.21)$,

$$
f(t, x) \;=\; \mathbb{E}_{t, x}\!\left[\,e^{-X_T}\,e^{-c(T - t)}\,\right].
$$

The increment of $X$ under the drifted BM $(4.22)$ is

$$
X_T - X_t \;=\; a(T - t) + b\,(W_T - W_t) \;\stackrel{d}{=}\; a(T - t) + b\sqrt{T - t}\,Z, \qquad Z \sim \mathcal{N}(0, 1),
$$

so $X_T | X_t = x$ is Gaussian with mean $x + a(T - t)$ and variance $b^2 (T - t)$. Substituting,

$$
f(t, x) \;=\; \mathbb{E}\!\left[\,\exp\!\left\{-x - a(T - t) - b\sqrt{T - t}\,Z - c(T - t)\right\}\,\right].
$$

Taking the Gaussian MGF of $-b\sqrt{T - t}\,Z$, which contributes $e^{\tfrac12 b^2 (T - t)}$:

$$
f(t, x) \;=\; \exp\!\left\{-x - a(T - t) + \tfrac12 b^2 (T - t) - c(T - t)\right\}.
$$

Collecting terms with common factor $(T - t)$:

$$
\boxed{\;f(t, x) \;=\; \exp\!\left\{\,-x \;-\; \left(a + c - \tfrac12 b^2\right)(T - t)\,\right\}\;}.
\tag{4.25}
$$

Equivalently, defining $\gamma = a + c - \tfrac12 b^2$ for shorthand,

$$
f(t, x) \;=\; e^{-x - \gamma(T - t)}.
\tag{4.26}
$$

### 4.8.5 Reading formula $(4.25)$ as a ledger

The exponent $-x - (a + c - \tfrac12 b^2)(T - t)$ has four contributions: $-x$ from the payoff base, $-a(T - t)$ from drift, $+\tfrac12 b^2 (T - t)$ from Jensen/convexity, and $-c(T - t)$ from discount. Sanity limits: $a = c = 0$, $b = 1$ recovers $(4.17)$; $b = 0$ recovers pure deterministic evolution with no convexity. A direct PDE check with $\gamma = a + c - \tfrac12 b^2$ and $f = e^{-x - \gamma(T - t)}$ gives $\partial_t f = +\gamma f$, $\partial_x f = -f$, $\partial_{xx} f = f$, and the LHS of $(4.20)$ collapses to $(\gamma - a + \tfrac12 b^2 - c)f = 0$.

---

## 4.9 Feynman-Kac with State- and Time-Dependent Coefficients

Black–Scholes (equity), short-rate models (rates), and most other workhorses need state-dependent $a, b, c$ as functions of $(t, x)$. We state and prove the general theorem, then read off three instantiations.

### 4.9.1 The general theorem

Let $a, b, c : [0, T] \times \mathbb{R} \to \mathbb{R}$ be sufficiently regular functions — continuous with mild growth conditions on $a$ and $b$, and boundedness on $c$; these are the conditions under which the associated SDE has a unique strong solution and the corresponding PDE has a classical solution. Consider the Cauchy problem

$$
\begin{cases}
\partial_t h(t, x) \;+\; a(t, x)\,\partial_x h(t, x) \;+\; \tfrac12\,b^2(t, x)\,\partial_{xx} h(t, x) \;=\; c(t, x)\,h(t, x), \\[2pt]
h(T, x) \;=\; H(x),
\end{cases}
\tag{4.34}
$$

with terminal payoff $H : \mathbb{R} \to \mathbb{R}$ satisfying polynomial growth. Then the solution admits the probabilistic representation

$$
\boxed{\;h(t, x) \;=\; \mathbb{E}\!\left[\,\exp\!\left\{-\!\int_t^T c(u, X_u)\,\mathrm{d}u\right\}\,H(X_T)\,\Big|\,X_t = x\right],\;}
\tag{4.35}
$$

where the process $X$ satisfies the Itô SDE

$$
\mathrm{d}X_s \;=\; a(s, X_s)\,\mathrm{d}s \;+\; b(s, X_s)\,\mathrm{d}W_s, \qquad s \in [t, T].
\tag{4.36}
$$

This is the *complete* Feynman-Kac theorem used in practice. Every linear parabolic pricing PDE in this guide is an instantiation of it, and the dictionary between PDE coefficients and SDE/discount is strict.

### 4.9.2 Three features worth noting

*The drift $a(s, X_s)$ and diffusion $b(s, X_s)$ may depend on both time and the current state.* No constancy assumption is required. The SDE $(4.36)$ is the general Itô diffusion, and Itô's lemma III from Chapter 3 is exactly the tool we need.

*The discount rate $c(s, X_s)$ may itself be stochastic* — a function of the state $X_s$. In this case the integrated discount $\int_t^T c(u, X_u)\,\mathrm{d}u$ is a path-dependent random variable, not a deterministic number $c(T - t)$. The path integral is exactly how stochastic-rate bond pricing works: $c(t, r) = r$ with $X = r_t$ a short-rate process yields bond prices $P(t, T) = \mathbb{E}_t[e^{-\int_t^T r_s\,\mathrm{d}s}]$.

*The payoff $H(X_T)$ is evaluated at the final state only.* We do not allow path-dependent payoffs in the basic statement. Path-dependency — barrier options that knock out if the path touches a level, Asian options that depend on the average price — requires further machinery: auxiliary state variables (e.g. the running minimum becomes a second state), augmented Itô processes, or variational inequalities for American-style features. Each extension preserves the Feynman-Kac spirit but with extra bookkeeping. The basic theorem $(4.34)$–$(4.35)$ covers every European-style payoff on a single state variable.

### 4.9.3 Why the path-dependent discount is necessary

The PDE evaluates $c(t, x)$ locally; the expectation accumulates $\int c(u, X_u)\,\mathrm{d}u$ along each path. For constant $c$ the path integral collapses to $c(T - t)$ and we recover (4.21). For $c = x$ the PDE has a linear zero-order term; the expectation carries $e^{-\int X_u\,\mathrm{d}u}$ — same content, different bookkeeping.

### 4.9.4 Proof (integrating-factor device)

Apply Itô to the discounted candidate

$$
Y_s \;\equiv\; \exp\!\left\{-\!\int_t^s c(u, X_u)\,\mathrm{d}u\right\}\cdot h(s, X_s), \qquad s \in [t, T].
\tag{4.37}
$$

The integrating factor $e^{-\int_t^s c\,\mathrm du}$ has differential $-c(s, X_s)\,e^{-\int_t^s c\,\mathrm du}\,\mathrm ds$ (no $\mathrm dW$ piece, hence no covariation). Combining with Itô III on $h(s, X_s)$,

$$
\mathrm{d}Y_s \;=\; e^{-\int_t^s c\,\mathrm{d}u}\!\left\{\left[-c\,h + \partial_t h + a\,\partial_x h + \tfrac12 b^2\,\partial_{xx} h\right]\mathrm{d}s \;+\; b\,\partial_x h\,\mathrm{d}W_s\right\}.
\tag{4.38}
$$

The $\mathrm{d}s$ coefficient vanishes by the PDE $(4.34)$, leaving a pure stochastic integral. Under the standard integrability hypothesis $\mathbb{E}_{t,x}\!\int_t^T e^{-2\int_t^s c\,\mathrm du}\,b^2\,(\partial_x h)^2\,\mathrm ds < \infty$, $Y$ is a true martingale on $[t, T]$. Taking expectations of $Y_t$ and $Y_T$ and using the terminal condition $h(T, \cdot) = H(\cdot)$,

$$
h(t, x) \;=\; \mathbb{E}_{t, x}[Y_T] \;=\; \mathbb{E}_{t, x}\!\left[e^{-\int_t^T c\,\mathrm{d}u}\,H(X_T)\right]. \quad\square
$$

The integrating factor $e^{-\int_t^s c\,\mathrm du}$ does the same job as the time-$0$-discount move in §4.3.5: it converts what would be a super-martingale candidate into a true martingale by absorbing the spatial discount drift, and is the simplest instance of the change-of-numeraire technique developed in Chapter 5. Two specialisations to flag: $c(t, x) = x$ with $H = 1$ gives the bond-price formula $P(t, x) = \mathbb{E}_{t, x}[e^{-\int_t^T X_u\,\mathrm du}]$ (Chapter 12); $c(t, x) = r + \lambda(t, x)$ gives the survival-probability building block of credit pricing.

### 4.9.5 Reading off the Black-Scholes PDE

Plug $a(t, x) = r x$, $b(t, x) = \sigma x$, $c(t, x) = r$ into $(4.34)$, all state-linear or constant. The PDE becomes

$$
\partial_t h + r x\,\partial_x h + \tfrac12 \sigma^2 x^2\,\partial_{xx} h \;=\; r\,h,
\tag{4.39}
$$

which is the Black-Scholes PDE. The expectation $(4.35)$ becomes

$$
h(t, x) \;=\; \mathbb{E}_{t, x}\!\left[e^{-r(T - t)}\,H(X_T)\right], \qquad \mathrm{d}X_s = r X_s\,\mathrm{d}s + \sigma X_s\,\mathrm{d}W_s,
\tag{4.40}
$$

which is the risk-neutral pricing formula for a claim $H(X_T)$ on a geometric-Brownian-motion underlying. The Black-Scholes formula for a European call or put is therefore literally a corollary of the general Feynman-Kac theorem; Chapter 6 derives it both this way and via the independent hedging argument.

### 4.9.6 Reading off the Vasicek bond price

Plug $a(t, r) = \kappa(\theta - r)$, $b(t, r) = \sigma$, $c(t, r) = r$, and $H(r) = 1$ into $(4.34)$. The PDE becomes the Vasicek bond-price PDE

$$
\partial_t P + \kappa(\theta - r)\,\partial_r P + \tfrac12 \sigma^2\,\partial_{rr} P \;=\; r\,P, \qquad P(T, r) = 1.
\tag{4.41}
$$

The expectation becomes

$$
P(t, r) \;=\; \mathbb{E}_{t, r}\!\left[e^{-\int_t^T r_s\,\mathrm{d}s}\right], \qquad \mathrm{d}r_s = \kappa(\theta - r_s)\,\mathrm{d}s + \sigma\,\mathrm{d}W_s,
\tag{4.42}
$$

the classical fair value of a zero-coupon bond under a Vasicek short rate; Chapter 12 evaluates this expectation to obtain the affine closed form $P(t, r) = e^{A(t, T) - B(t, T) r}$.

### 4.9.7 The unifying observation

Every linear PDE with a drift, a diffusion, and a discount term is a Feynman–Kac PDE for some SDE and some discount rate. Identify the coefficients, write the SDE, read off the expectation. Black–Scholes, Vasicek, Hull–White, caplet, swaption, Heston — all the same theorem with different substitutions. The algebra of solving each is where the later chapters spend their time.

---

## 4.10 Case Study — Vasicek Bond Pricing from the 2024 Treasury Curve

### Case study: Vasicek calibrated to the 2024 US Treasury curve

**Context.** In early 2024 the on-the-run US 10-year Treasury traded near a 4.10% yield, with the 2-year at 4.55% and the 3-month T-bill near 5.40% — a deeply inverted curve produced by the Fed's hiking cycle (5.25%–5.50% policy rate) sitting above market expectations of cuts later in the year. A Vasicek short rate $\mathrm{d}r_t = \kappa(\theta - r_t)\,\mathrm dt + \sigma\,\mathrm dW_t$ fitted to that snapshot yields $\kappa \approx 0.30$, $\theta \approx 0.035$, $\sigma \approx 0.011$ (units: years$^{-1}$, percent, percent yr$^{-1/2}$) — a slow mean-reversion to a long-run rate well below the then-current 4.10% short rate.

**Math mapping.** This is $(4.42)$ in flight. The Vasicek bond price $P(t, r) = \mathbb{E}_{t, r}[e^{-\int_t^T r_s\,\mathrm ds}]$ is the Feynman-Kac formula $(4.35)$ with $a(t, r) = \kappa(\theta - r)$, $b(t, r) = \sigma$, $c(t, r) = r$ (the short rate itself is the discount), and terminal payoff $H = 1$. The affine ansatz $P(t, r) = e^{A(t, T) - B(t, T)r}$ reduces the path integral to two ODEs: $B(t, T) = (1 - e^{-\kappa(T - t)})/\kappa$ and $A$ collecting the variance-of-integrated-rate term. With $T - t = 10$, $B \approx 3.17$, and plugging $r = 0.054$ gives $\ln P \approx A - 3.17 \cdot 0.054$; the convexity adjustment $\sigma^2 B^2(T-t)/(4\kappa)$ shaves about 0.6 bp off the implied yield. The model recovers a 10-year zero yield of $\approx 4.05\%$ — within 5 bp of the on-the-run quote, all of which is the spline-vs-affine fitting residual on a curve with humps that a 1-factor Vasicek cannot match. The bond price is *literally* what falls out of evaluating a Gaussian path integral over the integrated short rate.

**Lesson.** Feynman-Kac is not decorative. The bond desk does this calibration every morning: take the observed short-rate path, fit $(\kappa, \theta, \sigma)$ to a few benchmark maturities, and read off every other point on the curve as a closed-form expectation $(4.42)$. The mismatch in 2024 between the steeply inverted near end and a single-factor Vasicek model is exactly the empirical motivation for the multi-factor and time-dependent-$\theta(t)$ extensions of Chapter 12 — once $\theta$ is allowed to vary, the Hull-White model fits the entire 2024 curve to within 0.5 bp without changing the Feynman-Kac structure of the pricing formula.

---

## 4.11 Key Takeaways

1. **Two-way bridge.** A linear parabolic PDE with terminal data is *equivalent* to a conditional expectation over an associated diffusion; the reader picks whichever side is easier for the problem at hand. Equations $(4.1)$–$(4.2)$ for the base case, $(4.34)$–$(4.35)$ in full generality.

2. **Proof template: three moves.** Every pricing PDE in the guide is derived by (i) writing the price as a conditional expectation, (ii) applying Itô to decompose its increment into drift plus martingale, (iii) demanding the drift vanish. Recurs in Chapters 6, 12, 15.

3. **Doob martingale + drift-kill.** $\eta_s = \mathbb{E}[\varphi(X_T) | \mathcal{F}_s]$ is automatically a martingale by the tower property; a continuous martingale of bounded variation is identically zero, so its Itô drift must vanish — and that vanishing drift *is* the PDE.

4. **Three worked payoffs.** Linear $\varphi(x) = x$: $f = x$ (no convexity). Quadratic $\varphi(x) = x^2$: $f = x^2 + (T - t)$ (variance-swap identity). Exponential $\varphi(x) = e^{ax}$: $f = e^{ax + \tfrac12 a^2 (T - t)}$ (Jensen bump scales as $a^2$). Equations $(4.13)$, $(4.15)$, $(4.19)$.

5. **Constant-coefficient ledger.** For $\varphi = e^{-x}$ with constant $a, b, c$, $f = \exp\{-x - (a + c - \tfrac12 b^2)(T - t)\}$ — drift, discount, convexity each on its own line in the exponent. Equation $(4.25)$.

6. **General theorem.** For state-and-time-dependent $a, b, c$, $h(t, x) = \mathbb{E}_{t, x}[e^{-\int_t^T c(u, X_u)\,\mathrm du}\,H(X_T)]$ with $\mathrm dX_s = a(s, X_s)\,\mathrm ds + b(s, X_s)\,\mathrm dW_s$. The integrating-factor device $(4.37)$–$(4.38)$ proves it in one Itô calculation.

7. **Black-Scholes corollary.** $a = rx$, $b = \sigma x$, $c = r$ recover the BS PDE and the GBM risk-neutral expectation. The closed-form call is the Gaussian integral evaluated; Chapter 6 fills in.

8. **Vasicek corollary.** $a = \kappa(\theta - r)$, $b = \sigma$, $c = r$, $H = 1$ recover the bond-price PDE; $P(t, r) = \mathbb{E}_{t, r}[e^{-\int_t^T r_s\,\mathrm ds}]$ is affine in $r$. The 2024 case study of §4.10 shows this recovering a Treasury yield to within 5 bp.

9. **PDE vs Monte-Carlo routing.** Low-dimensional smooth problems favour PDE; high-dimensional / path-dependent problems favour MC. Feynman-Kac guarantees the two answers agree, enabling cross-validation.

10. **Sign-convention reflex.** Discount appears as $-c\,f$ on the PDE side and as $e^{-c(T - t)}$ inside the expectation; mixing the conventions is the most common bookkeeping bug. Always anchor on the terminal condition first.

---

## 4.12 Reference Formulas

### 4.12.1 Feynman-Kac statements

| Object | Formula | Eq. |
|---|---|---|
| F-K zero-drift PDE | $\partial_t f + \tfrac12\,\partial_{xx} f = 0$, $f(T, x) = \varphi(x)$ | $(4.1)$ |
| F-K zero-drift expectation | $f(t, x) = \mathbb{E}_{t, x}[\varphi(X_T)]$, $X$ a standard BM | $(4.2)$ |
| F-K constant-coefficient PDE | $\partial_t f + a\,\partial_x f + \tfrac12 b^2\,\partial_{xx} f = c\,f$ | $(4.20)$ |
| F-K constant-coefficient expectation | $f(t, x) = \mathbb{E}_{t, x}[e^{-c(T - t)}\varphi(X_T)]$, $\mathrm{d}X = a\,\mathrm{d}s + b\,\mathrm{d}W$ | $(4.21)$ |
| F-K general (state-dep. $a, b, c$) PDE | $\partial_t h + a(t, x)\,\partial_x h + \tfrac12 b^2(t, x)\,\partial_{xx} h = c(t, x)\,h$ | $(4.34)$ |
| F-K general expectation | $h(t, x) = \mathbb{E}_{t, x}[e^{-\int_t^T c(u, X_u)\,\mathrm{d}u}\,H(X_T)]$ | $(4.35)$ |
| SDE for the diffusion $X$ | $\mathrm{d}X_s = a(s, X_s)\,\mathrm{d}s + b(s, X_s)\,\mathrm{d}W_s$ | $(4.36)$ |

### 4.12.2 Derivation internals

| Object | Formula | Eq. |
|---|---|---|
| Local self-consistency (tower) | $f(t, x) = \mathbb{E}[f(t + \mathrm{d}t,\,x + \mathrm{d}W)]$ | $(4.3)$ |
| Candidate pricing function | $f(t, x) = \mathbb{E}[\varphi(X_T) \mid X_t = x]$ | $(4.4)$ |
| Doob martingale | $\eta_s = f(s, X_s) = \mathbb{E}[\varphi(X_T) \mid X_s]$ | $(4.5)$ |
| Markov collapse of filtration | $\mathbb{E}[\varphi(X_T) \mid \mathcal{F}_s] = \mathbb{E}[\varphi(X_T) \mid X_s]$ | $(4.6)$ |
| Martingale property of $\eta$ | $\mathbb{E}[\eta_{s_2} \mid \mathcal{F}_{s_1}] = \eta_{s_1}$ for $s_1 \le s_2$ | $(4.7)$ |
| Itô decomposition of $\eta$ | $\mathrm{d}\eta_s = [\partial_t f + \tfrac12 \partial_{xx} f]\,\mathrm{d}s + \partial_x f\,\mathrm{d}X_s$ | $(4.9)$ |
| Backward PDE (zero-drift) | $\partial_t f + \tfrac12\,\partial_{xx} f = 0$ | $(4.10)$ |
| Discounted candidate (integrating factor) | $Y_s = e^{-\int_t^s c(u, X_u)\,\mathrm{d}u}\,h(s, X_s)$ | $(4.37)$ |
| Drift-killed Itô decomposition | $\mathrm{d}Y_s = e^{-\int_t^s c\,\mathrm{d}u}\,b\,\partial_x h\,\mathrm{d}W_s$ (drift = 0 by PDE) | $(4.38)$ |

### 4.12.3 Worked examples

| Payoff | Solution | Eq. |
|---|---|---|
| Linear $\varphi(x) = x$ | $f(t, x) = x$ | $(4.13)$ |
| Quadratic $\varphi(x) = x^2$ | $f(t, x) = x^2 + (T - t)$ | $(4.15)$ |
| Exponential base $\varphi(x) = e^{-x}$ | $f(t, x) = e^{-x + \tfrac12 (T - t)}$ | $(4.17)$ |
| General exponential $\varphi(x) = e^{a x}$ | $f(t, x) = e^{a x + \tfrac12 a^2 (T - t)}$ | $(4.19)$ |
| Exponential with $a, b, c$ constants | $f(t, x) = \exp\{-x - (a + c - \tfrac12 b^2)(T - t)\}$ | $(4.25)$ |

### 4.12.4 Instantiations

| Model | Coefficients | PDE / expectation |
|---|---|---|
| Black-Scholes (GBM) | $a = r x$, $b = \sigma x$, $c = r$ | $\partial_t h + r x\,\partial_x h + \tfrac12 \sigma^2 x^2\,\partial_{xx} h = r h$ |
| Black-Scholes expectation | as above | $h(t, x) = \mathbb{E}_{t, x}[e^{-r(T - t)}\,H(X_T)]$, $\mathrm{d}X = r X\,\mathrm{d}s + \sigma X\,\mathrm{d}W$ |
| Vasicek bond | $a = \kappa(\theta - r)$, $b = \sigma$, $c = r$, $H = 1$ | $\partial_t P + \kappa(\theta - r)\,\partial_r P + \tfrac12 \sigma^2\,\partial_{rr} P = r P$ |
| Vasicek bond expectation | as above | $P(t, r) = \mathbb{E}_{t, r}[e^{-\int_t^T r_s\,\mathrm{d}s}]$ |
| Hazard-rate survival | $a, b$ arbitrary, $c = \lambda(t, x)$, $H = 1$ | $P_{\text{surv}}(t, x) = \mathbb{E}_{t, x}[e^{-\int_t^T \lambda(u, X_u)\,\mathrm{d}u}]$ |

### 4.12.5 Useful Gaussian identities

| Object | Formula |
|---|---|
| Gaussian MGF | $\mathbb{E}[e^{\lambda Z}] = e^{\tfrac12 \lambda^2}$, $Z \sim \mathcal{N}(0, 1)$ |
| Shifted Gaussian MGF | $\mathbb{E}[e^{\lambda Y}] = e^{\lambda \mu + \tfrac12 \lambda^2 \sigma^2}$, $Y \sim \mathcal{N}(\mu, \sigma^2)$ |
| Brownian increment | $X_T - X_t \sim \mathcal{N}(0, T - t)$, hence $X_T \mid X_t = x \sim \mathcal{N}(x, T - t)$ |
| Drifted BM increment | For $\mathrm{d}X = a\,\mathrm{d}s + b\,\mathrm{d}W$: $X_T \mid X_t = x \sim \mathcal{N}(x + a(T - t),\,b^2 (T - t))$ |
| Integrated Gaussian process | If $X$ is Gaussian with covariance $\mathrm{Cov}(X_s, X_u)$, then $\int_t^T X_u\,\mathrm{d}u$ is Gaussian with computable mean and variance. |
