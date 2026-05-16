# Chapter 2 — Multi-Period Binomial, CRR, and the FTAP

Chapter 1 established risk-neutral pricing for a single-period two-state economy. Here we build the explicit multi-period binomial machinery — backward induction along a recombining tree — and its limit the Cox–Ross–Rubinstein (CRR) model. We present two equivalent CRR parameterisations: the classical $A_n = A_{n-1} e^{c\, x_n}$ Bernoulli lattice, and the "direct-Gaussian increment" lattice with the Itô convexity built into the nodes. We state the Fundamental Theorem of Asset Pricing (FTAP) and confront non-uniqueness of $\mathbb{Q}$ when the tree has more than two states. The chapter closes with the dynamic-programming recursion for American options.

Themes:
- *Completeness vs incompleteness.* Binomial trees are exactly one-step complete. Add a third branch (default, jump, stoch-vol state) and uniqueness fails; pricing becomes a *range* and a risk-preference device selects one representative.
- *Backward induction.* Bellman's dynamic-programming principle handles Americans and any path-dependence captured by finitely many state variables. Monte Carlo is the forward-simulation complement, developed in CH08.
- *Numéraire freedom.* The FTAP is silent on which asset deflates; the choice will be exploited heavily in CH05 (Girsanov) and beyond.

---

## 2.1 One-Period Review: the No-Arbitrage Inequality

Start at $A$ with successors $A_u > A_d$ and a cash account growing at $1+r$. The one-period no-arbitrage inequality is

$$A_d \;<\; A(1 + r) \;<\; A_u \;\iff\; \text{no arb}. \tag{2.1}$$

If $A(1+r) \leq A_d$ then borrowing cash and buying stock yields riskless profit; symmetrically for $A(1+r) \geq A_u$. The forward price must sit strictly between the two post-states.

Equivalently, any claim $C$ with terminal values $C_u, C_d$ admits a unique arbitrage-free price via $\mathbb{Q}$:

$$\exists\, \mathbb{Q} \text{ s.t. } C \;=\; \frac{1}{1+r}\,\mathbb{E}^{\mathbb{Q}}[\,C_1\,] \;\iff\; \text{no arb}, \qquad q = \tfrac{A(1+r)-A_d}{A_u-A_d}. \tag{2.2}$$

Together (2.1)–(2.2) form the one-period FTAP, a microcosm of the general FTAP in §2.5. The weights $q,1-q$ are *not* physical probabilities — they are the unique convex combination making the discounted asset a one-step martingale. The Radon–Nikodym derivative $d\mathbb{Q}/d\mathbb{P}$ is the market's discount of optimism and is the engine of Girsanov's theorem (CH05).

Worked check. $A=100, r=5\%, A_u=120, A_d=90$: forward $= 105 \in (90,120)$, so $q = (105-90)/30 = 1/2$. ATM call ($K=100$): $C = (1/1.05)(0.5\cdot 20) \approx 9.52$. Replicating: $\alpha = 2/3, \beta \approx -57.14$, giving $2/3\cdot 100 - 57.14 \approx 9.52$ ✓.

### Case study: Petrobras ADR vs ordinary arbitrage (PBR / PETR4)

The Brazilian oil major Petrobras has two near-identical equity claims trading in different venues: PETR4 (preferred ordinary shares, traded on Brazil's B3 exchange in BRL) and PBR (American Depositary Receipts, traded on NYSE in USD, each ADR representing one ordinary share). By construction, the no-arbitrage relationship is $\text{PBR}_t = \text{PETR4}_t / \text{FX}_t^{\text{BRL/USD}}$, modulo a small ADR depositary fee. Yet over essentially every trading day from 2018 to 2024, the implied FX rate from $(PETR4, PBR)$ has *deviated* from the actual BRL/USD spot — sometimes by 50 to 200 basis points, occasionally more during Brazilian political stress. The pair is tracked daily by Latin-American equity desks at every major bank precisely because the deviations represent a concrete, observable violation of the law of one price.

Read through the FTAP, the trade is the cleanest possible example of why (2.1)–(2.2) matter. We have three "assets": PETR4, PBR, and the BRL/USD currency forward. Two of them span the same claim — a unit of Petrobras equity at time $T$ — so the relative price between them must equal the FX forward, by the same argument that gives (2.1). Mispricings open because the three venues have different trading hours (B3 closes at 17:00 BRT, NYSE closes at 16:00 EST), different settlement cycles (T+2 in Brazil, T+1 in the US post-2024), and different liquidity profiles. Closing the gap requires simultaneous trades in BRL/USD FX, PETR4 on B3, and PBR on NYSE — operationally demanding, capital-intensive, and exposed to overnight gap risk. The risk-neutral measure $\mathbb{Q}$ implied by PETR4 vs the one implied by PBR are slightly different — exactly the "two-$q$ puzzle" from CH01 §7 in real-world form.

The practitioner lesson is twofold. First, real markets *do* contain detectable FTAP violations — they are not theoretical curiosities. They survive because of trading frictions (FX swap costs, ADR creation/cancellation fees, time-zone overlap risk) that gate the pure-arbitrage trade. Second, the price an arbitrageur can actually realise is the model price *minus* those frictions. When practitioners say "the spread is too narrow to trade," they mean the FTAP gap is real but smaller than the friction cost of closing it. The frictionless model is the *attractor*; the observed deviations measure the round-trip cost of trading.

<!-- figure placeholder: one-period tree A -> {A_u, A_d} with cash 1 -> 1+r, boxed inequality A_d < A(1+r) < A_u; C -> {C_u, C_d} with boxed ∃Q s.t. C = (1/(1+r))E^Q[C_1] -->

---

## 2.2 Multi-Period Binomial Tree — Backward Induction

Extend the one-step construction to $N$ steps. Recombination ($A_{ud} = A_{du}$) reduces $2^N$ terminal nodes to $N+1$, giving $O(N^2)$ pricing complexity. At $N=250$ daily steps, that's $\approx 31{,}000$ node evaluations versus $2^{250} \approx 10^{75}$ without recombination. Multiplicative models recombine because multiplication commutes.

<!-- figure placeholder: two side-by-side trees. Left: general non-recombining 2^N tree. Right: recombining N+1 tree with one node highlighted showing the up-down = down-up recombination box. -->

At every interior node the claim value is $\tfrac{1}{1+r}\mathbb{E}^{\mathbb{Q}}[\text{next-step payoff}]$ with node-local $q$. In simple CRR, $q$ depends only on $(u, d, 1+r)$ and is global; in state-dependent models (local vol, stochastic rates) each node has its own $q$. The backward-induction algorithm is identical either way.

### 2.2.1 Worked example — call struck at 100, maturity $T = 2$

A two-period non-constant-factor lattice:

\begin{figure}[H]
\centering
\begin{tikzpicture}[>=Stealth,scale=0.9,every node/.style={font=\small}]
  \node (S00) at (0,0) {$100$};
  \node (S1u) at (2.5,1.3) {$120$};
  \node (S1d) at (2.5,-1.3) {$90$};
  \node (S2uu) at (5,2.6) {$130$};
  \node (S2ud) at (5,0) {$110$};
  \node (S2dd) at (5,-2.6) {$80$};
  \draw[->,thick] (S00) -- node[above,sloped,font=\scriptsize] {$q_1$} (S1u);
  \draw[->,thick] (S00) -- node[below,sloped,font=\scriptsize] {$1-q_1$} (S1d);
  \draw[->,thick] (S1u) -- node[above,sloped,font=\scriptsize] {$q_2$} (S2uu);
  \draw[->,thick] (S1u) -- node[above,sloped,font=\scriptsize] {$1-q_2$} (S2ud);
  \draw[->,thick] (S1d) -- node[below,sloped,font=\scriptsize] {$q_3$} (S2ud);
  \draw[->,thick] (S1d) -- node[below,sloped,font=\scriptsize] {$1-q_3$} (S2dd);
  \node[below=0.6cm,font=\footnotesize\itshape] at (0,-2.6) {$t = 0$};
  \node[below=0.6cm,font=\footnotesize\itshape] at (2.5,-2.6) {$t = 1$};
  \node[below=0.6cm,font=\footnotesize\itshape] at (5,-2.6) {$t = 2$};
\end{tikzpicture}

\textit{Local risk-neutral weights $q_1, q_2, q_3$ — one per branching node — are pinned down by the one-period FTAP applied at each node.}
\end{figure}
with edge-local interest rates $r_1, r_2, r_3$ on the three time-$0 \to 1 \to 2$ edges. The local risk-neutral probabilities $q_1, q_2, q_3$ are pinned down by matching the parent to the discounted expectation of its children:

$$120 \;=\; \frac{1}{1 + r_?}\!\left(\,130\,q_2 \;+\; 110\,(1 - q_2)\,\right) \;\Longrightarrow\; q_2 = \# \tag{2.3}$$

$$90 \;=\; \frac{1}{1 + r_?}\!\left(\,110\,q_3 \;+\; 80\,(1 - q_3)\,\right) \;\Longrightarrow\; q_3 = \# \tag{2.4}$$

$$100 \;=\; \frac{1}{1 + r_?}\!\left(\,120\,q_1 \;+\; 90\,(1 - q_1)\,\right) \;\Longrightarrow\; q_1 = \# \tag{2.5}$$

Payoff @ $T = 2$. Call struck at $K = 100$: $\max(A_T - K, 0)$. Terminal column $A_T \in \{130, 110, 110, 80\}$, payoffs $\{30, 10, 10, 0\}$. The middle value 110 occurs twice — recombination at work; $\mathbb{Q}$-probability of reaching it is $2q(1-q)$.

Backward step 1 (t = 1 nodes). At the upper intermediate node (stock = 120):

$$C_{1u} \;=\; \frac{1}{1 + r_2}\!\left(\,30\,q_2 \;+\; 10\,(1 - q_2)\,\right) \;=\; \#, \tag{2.7}$$

and at the lower intermediate node (stock = 90, children 110 and 80, payoffs 10 and 0):

$$C_{1d} \;=\; \frac{1}{1 + r_3}\!\left(\,10\,q_3 \;+\; 0\,(1 - q_3)\,\right) \;=\; \#. \tag{2.8}$$

Backward step 2 (t = 0).

$$C_0 \;=\; \frac{1}{1 + r_1}\!\left(\,C_{1u}\,q_1 \;+\; C_{1d}\,(1 - q_1)\,\right) \;=\; \#. \tag{2.9}$$

*Intuition.* Backward induction is the lattice manifestation of the tower property $\mathbb{E}[\mathbb{E}[X|\mathcal{F}_s]|\mathcal{F}_t] = \mathbb{E}[X|\mathcal{F}_t]$ for $t \le s$. Computing step by step (vs the one-shot $C_0 = \mathbb{E}^{\mathbb{Q}}[e^{-rT}C_T]$) lets the same sweep handle path-dependent payoffs (Asians, lookbacks), barriers, and American exercise (§2.8), with $O(N^2)$ complexity in the state variables.

### 2.2.2 Path-weights and the CRR telescoping identity

If $r_1 = r_2 = r_3 = r$ the root price collapses to

$$C_0 \;=\; \frac{1}{(1 + r)^N}\,\mathbb{E}^{\mathbb{Q}}\!\left[\,C_T\,\right] \;=\; (1+r)^{-N}\sum_{k=0}^{N}\binom{N}{k} q^k(1-q)^{N-k}(A_0 u^k d^{N-k}-K)_+. \tag{2.10}$$

As $N\to\infty$ with $u = e^{\sigma\sqrt{\Delta t}}, d = e^{-\sigma\sqrt{\Delta t}}$, the binomial distribution converges to normal (de Moivre–Laplace) and the sum to the Black–Scholes integral. Convergence is $O(1/N)$ with oscillation; Richardson extrapolation accelerates. The distribution of up-moves is Binomial$(N, q)$, giving closed-form moments: $\mathbb{E}^{\mathbb{Q}}[A_T] = A_0(1+r)^N$ (martingale) and $\mathbb{V}^{\mathbb{Q}}[\ln A_T] \to \sigma^2 T$.

---

## 2.3 The Cox–Ross–Rubinstein (CRR) Model — Bernoulli Parameterisation

CRR (1979) showed the binomial lattice converges to Black–Scholes as $\Delta t \to 0$ and gives a tractable pricing tool for Americans and exotics. In step $\Delta t$, replace $1+r$ with $e^{r\Delta t}$ (cleaner algebra; aligns with $B_T = e^{rT}$ in the limit). Up-moves multiply by $e^c$, down-moves by $e^{-c}$ (symmetric $\pm c$ for recombination).

$$A_n \;=\; A_{n-1}\, e^{c\, x_n}, \qquad x_n \stackrel{iid}{\sim} \text{Bernoulli}(\pm 1), \;\; \mathbb{P}(x = +1) = p. \tag{2.12}$$

Symmetric Bernoulli $\pm 1$ is the simplest random variable with two states per step (one-step completeness), symmetric placement (recombination), and iid increments. The choice cleanly separates move size ($c$) from directional bias ($p - \tfrac12$).

<!-- figure placeholder: three-branch schematic A_0 $\to$ {A_0 e^c, A_0, A_0 e^{-c}} labelled with p / (1-p) and a timeline 0 — $\Delta$t — T with $\Delta$t = T/N (number of steps). -->

Iterating $N = T/\Delta t$ steps,

$$A_T \;=\; A_0\,e^{c\,X_N}, \qquad X_N := \sum_{n=1}^{N} x_n. \tag{2.13}$$

### 2.3.1 Moments of the increment sum

Calibrate by moment-matching: two free parameters $(p, c)$ match two empirical moments $(\mu, \sigma^2)$. Linearity plus iid Bernoulli:

$$\mathbb{E}[X_N] \;=\; \sum_{n=1}^{N}\mathbb{E}[x_n] \;=\; N\bigl(\,+1\cdot p + (-1)(1-p)\,\bigr) \;=\; N\,(2p - 1) \;=\; \mu\,\Delta t\, N, \tag{2.14}$$

$$\mathbb{V}[X_N] \;=\; N\,\mathbb{V}[x_1] \;=\; N\!\left(\,\mathbb{E}[x_1^2] - (\mathbb{E}[x_1])^2\,\right) \;=\; N\bigl(1 - (2p - 1)^2\bigr) \;=\; \sigma^2\,\Delta t\, N. \tag{2.15}$$

The data feed in $\mu$ and $\sigma^2$ as annualised log-return mean and variance from a price series via

$$\ln(S_2 / S_1) \;=\; r_1, \quad \ln(S_3 / S_2) \;=\; r_2, \quad \dots \tag{2.16}$$

$$\widehat{\mu\,\Delta t} \;=\; \frac{1}{M}\sum_{m=1}^{M} r_m \quad\text{(annualised return)}, \tag{2.17}$$

$$\widehat{\sigma^2\,\Delta t} \;=\; \frac{1}{M}\sum_{m=1}^{M} (r_m - \widehat{\mu\Delta t})^2 \quad\text{(annualised variance)}. \tag{2.18}$$

### 2.3.2 Solving for the CRR parameters $(p, c)$

Solving (2.14)–(2.15) simultaneously, using $\mathbb{E}[x^2] = c^2$:

$$\mathbb{V}[X_N^{c\text{-scaled}}] \;=\; c^2 N\bigl(1 - (2p - 1)^2\bigr) \;=\; \sigma^2 \Delta t\, N, \tag{2.19}$$

one obtains the Cox–Ross–Rubinstein up-step and physical probability:

$$\boxed{\; c \;=\; \sigma\sqrt{\Delta t} + \cdots, \qquad p \;=\; \tfrac{1}{2}\!\left(\,1 \;+\; \frac{\mu}{\sigma}\,\sqrt{\Delta t}\,\right) + \cdots. \;} \tag{2.20}$$

*Intuition.* Variance match gives $c = \sigma\sqrt{\Delta t}$; mean match gives a small $O(\sqrt{\Delta t})$ bias in $p$. Worked: $\sigma = 20\%, \mu = 10\%, \Delta t = 1/252$ gives $c \approx 0.0126$ (per-step $\pm 1.27\%$ moves) and $p \approx 0.516$. The $\sqrt{\Delta t}$ scaling of $c$ is the universal scaling of Brownian motion — at daily horizon, diffusion ($\sigma\sqrt{\Delta t}$) is $\sim\!16\times$ larger than drift ($\mu\Delta t$), which is why short-horizon returns look like noise.

### 2.3.3 Converting to the $\mathbb{Q}$-probability

The $\mathbb{P}\to\mathbb{Q}$ transformation re-weights probabilities so the expected return matches the riskless rate $r$. Risk-neutral pricing on the $e^{\pm c}$ tree:

$$A \;=\; e^{-r\Delta t}\, \mathbb{E}^{\mathbb{Q}}[\,A_{n}\,] \;=\; e^{-r\Delta t}\!\left(\,q\, A\, e^{\sigma\sqrt{\Delta t}} \;+\; (1 - q)\, A\, e^{-\sigma\sqrt{\Delta t}}\,\right), \tag{2.21}$$

giving

$$\boxed{\; q \;=\; \frac{e^{r\Delta t} - e^{-\sigma\sqrt{\Delta t}}}{e^{+\sigma\sqrt{\Delta t}} - e^{-\sigma\sqrt{\Delta t}}}. \;} \tag{2.22}$$

Small-$\Delta t$ expansion. Using $e^{\pm z} \sim 1 \pm z + \tfrac{1}{2}z^2 + \cdots$ in both numerator and denominator,

$$q \;\sim\; \tfrac{1}{2}\!\left(\,1 \;+\; \frac{r - \tfrac{1}{2}\sigma^2}{\sigma}\,\sqrt{\Delta t}\,\right) + \cdots \tag{2.23}$$

$$p \;\sim\; \tfrac{1}{2}\!\left(\,1 \;+\; \frac{\mu}{\sigma}\,\sqrt{\Delta t}\,\right) + \cdots \qquad\text{(for comparison, under } \mathbb{P}\text{).} \tag{2.24}$$

The boxed formula (2.22) is *exact* at finite $\Delta t$; (2.23) is leading-order. The $\mathbb{P} \to \mathbb{Q}$ shift replaces the log-return drift $\mu$ by $r - \tfrac12\sigma^2$ — the Itô convexity adjustment shows up already at the lattice level, before any stochastic calculus. The deeper reason is the geometric-vs-arithmetic mean gap: $\mathbb{E}[e^X] \ge e^{\mathbb{E}[X]}$. A naïve simulator that uses just $r$ (no $-\tfrac12\sigma^2$) over-prices calls by $\sim e^{\sigma^2 T/2}$ — a 28% bias at $\sigma=50\%, T=2$.

### 2.3.4 Log-moments under $\mathbb{P}$ vs $\mathbb{Q}$

Combining (2.13) with (2.20) / (2.23),

$$\mathbb{E}^{\mathbb{P}}\!\left[\ln(A_T / A_0)\right] \;=\; \mu\, T, \qquad \mathbb{V}^{\mathbb{P}}\!\left[\ln(A_T / A_0)\right] \;=\; \sigma^2\, T, \tag{2.25}$$

$$\mathbb{E}^{\mathbb{Q}}\!\left[\ln(A_T / A_0)\right] \;=\; \bigl(r - \tfrac{1}{2}\sigma^2\bigr)\, T, \qquad \mathbb{V}^{\mathbb{Q}}\!\left[\ln(A_T / A_0)\right] \;=\; \sigma^2\, T. \tag{2.26}$$

> Slogan. "$\mathbb{P}$ and $\mathbb{Q}$ variances are identical" — "$\mathbb{P}$ and $\mathbb{Q}$ means are *not*".

*Intuition.* Girsanov at one line: a change of equivalent measure tilts drifts but *cannot* change volatility — quadratic variation is measure-invariant because it is a pathwise quantity, not a probabilistic one. Implied volatility ($\mathbb{Q}$-world) and realised volatility ($\mathbb{P}$-world) measure the same $\sigma^2$ in principle; their empirical gap is the *variance risk premium*, traded actively via VIX futures vs realised S&P 500 variance.

### 2.3.5 Continuous-time limit — lognormal asset

Apply the CLT to $X_N = \sum x_n$ as $N \to \infty$ with $N\Delta t = T$ fixed:

$$\ln(A_T / A_0) \;=\; X_N \;\xrightarrow[N\to\infty]{d,\ \mathbb{P}}\; \mathcal{N}\!\left(\,\mu T,\; \sigma^2 T\,\right), \tag{2.27}$$

$$\ln(A_T / A_0) \;=\; X_N \;\xrightarrow[N\to\infty]{d,\ \mathbb{Q}}\; \mathcal{N}\!\left(\,(r - \tfrac{1}{2}\sigma^2)T,\; \sigma^2 T\,\right). \tag{2.28}$$

Equivalently, in distribution,

$$A_T \;\stackrel{d}{=}\; A_0\, e^{\mu T \;+\; \sigma\sqrt{T}\, Z_{\mathbb{P}}}, \qquad Z_{\mathbb{P}} \sim \mathcal{N}(0, 1), \tag{2.29}$$

$$A_T \;\stackrel{d}{=}\; A_0\, e^{(r - \tfrac{1}{2}\sigma^2)T \;+\; \sigma\sqrt{T}\, Z_{\mathbb{Q}}}, \qquad Z_{\mathbb{Q}} \sim \mathcal{N}(0, 1). \tag{2.30}$$

In words: asset prices in the limit $N\to\infty$ are lognormal r.v. at a fixed point in time. Verifying the martingale property under $\mathbb{Q}$:

$$\mathbb{E}^{\mathbb{P}}[\,A_T\,] \;=\; A_0\, e^{\mu T}\,\mathbb{E}^{\mathbb{P}}\!\bigl[\,e^{\sigma\sqrt{T}\, Z}\,\bigr] \;=\; A_0\, e^{\mu T}\, e^{\tfrac{1}{2}\sigma^2 T} \;=\; A_0\, e^{(\mu + \tfrac{1}{2}\sigma^2) T}, \tag{2.31}$$

$$\mathbb{E}^{\mathbb{Q}}[\,A_T\,] \;=\; A_0\, e^{(r - \tfrac{1}{2}\sigma^2) T}\, e^{\tfrac{1}{2}\sigma^2 T} \;=\; A_0\, e^{r T}. \tag{2.32}$$

Used: $\mathbb{E}[e^{\alpha Z}] = e^{\alpha^2/2}$. Under $\mathbb{Q}$ the log-return drift is $r - \tfrac12\sigma^2$ but the price grows at $r$ — Jensen on $e^X$. In log-normal markets, the right-tail pulls the mean up by exactly $\tfrac12\sigma^2$ above the median.

### 2.3.6 Calibrating to log-returns vs simple returns — the $\tfrac{1}{2}\sigma^2$ correction

Caveat: if you calibrate $\mu$ from simple returns $(S_{m+1} - S_m)/S_m$ instead of log-returns, you over-state the log-drift by $\tfrac12\sigma^2$ — "volatility drag." For the S&P 500 at $\sigma = 16\%$, the gap between simple-return $\mu = 10\%$ and the compounded growth rate $\approx 8.7\%$ produces a 40% terminal-wealth difference over 30 years. *Always log before averaging:* compute $r_m = \ln(S_{m+1}/S_m)$, then take sample mean and variance.

<!-- figure placeholder: a simulated path A_t with drift line A_0 e^{($\mu$ − $\sigma$²/2)t + $\sigma$$\sqrt{}$t Z} overlaid, axes t (horizontal) vs A_t. The drift curve sits below the sample path on average — illustrates the vol drag. -->

### 2.3.7 Pricing vanilla European claims in the CRR limit

From $C_0/B_0 = \mathbb{E}^{\mathbb{Q}}[C_T/B_T]$ and (2.30):

$$C_0 \;=\; e^{-rT}\, \mathbb{E}^{\mathbb{Q}}\!\left[\,(A_T - K)_+\,\right], \qquad A_T \;\stackrel{d}{=}\; A_0\, e^{(r - \tfrac{1}{2}\sigma^2)T + \sigma\sqrt{T}\, Z}. \tag{2.34}$$

The integral evaluates to the Black–Scholes formula (sketched in §2.9; derived in CH06).

---

## 2.4 The Alternate CRR Parameterisation — Direct-Gaussian Increment Lattice

The classical CRR pushes drift into the probability $p$. An equivalent alternate lattice (essentially Jarrow–Rudd) absorbs the Itô convexity into the *nodes* and keeps $p = \tfrac12$. Many discretisations converge to the same GBM; the choice trades off where the drift information lives.

### 2.4.1 The two parameterisations, side by side

Parameterisation I — symmetric nodes, biased probability (§2.3):

$$A \to \begin{cases} A\, e^{+\sigma\sqrt{\Delta t}} & \text{w.p. } p \\[4pt] A\, e^{-\sigma\sqrt{\Delta t}} & \text{w.p. } 1-p \end{cases}, \quad p = \tfrac{1}{2}[1 + \tfrac{\mu}{\sigma}\sqrt{\Delta t}] + \cdots \tag{2.35}$$

Parameterisation II — drift-shifted nodes, symmetric probability:

$$A \to \begin{cases} A\, e^{(\mu - \tfrac{1}{2}\sigma^2)\Delta t + \sigma\sqrt{\Delta t}} & \text{w.p. } \tfrac{1}{2} \\[4pt] A\, e^{(\mu - \tfrac{1}{2}\sigma^2)\Delta t - \sigma\sqrt{\Delta t}} & \text{w.p. } \tfrac{1}{2} \end{cases} \tag{2.36}$$

*Intuition.* Both converge to the same lognormal GBM. Parameterisation II is the moment-matched Euler–Maruyama scheme for log-GBM: $X_{n+1} = X_n + (r-\tfrac12\sigma^2)\Delta t + \sigma\cdot\pm\sqrt{\Delta t}$. It is nicer for Monte Carlo (fair coin), parameterisation I is closer to the one-step no-arb picture.

### 2.4.2 Verifying parameterisation II matches the first two log-moments

Under $\mathbb{P}$ with $p = \tfrac{1}{2}$ on tree (2.36):

$$\mathbb{E}^{\mathbb{P}}[A_1] \;=\; A\, e^{(\mu - \tfrac{1}{2}\sigma^2)\Delta t}\cdot \tfrac{1}{2}\!\left[\,e^{+\sigma\sqrt{\Delta t}} + e^{-\sigma\sqrt{\Delta t}}\,\right]. \tag{2.37}$$

Expanding $\tfrac{1}{2}[e^{z} + e^{-z}] = 1 + \tfrac{1}{2}z^2 + \cdots$ with $z = \sigma\sqrt{\Delta t}$:

$$\mathbb{E}^{\mathbb{P}}[A_1] \;=\; A\, e^{(\mu - \tfrac{1}{2}\sigma^2)\Delta t}\!\left(1 + \tfrac{1}{2}\sigma^2\Delta t + \cdots\right) \;=\; A\, e^{\mu\Delta t} + \cdots, \tag{2.38}$$

matching the target $\mathbb{E}^{\mathbb{P}}[A_1] = A e^{\mu\Delta t}$ to the relevant order. The log-variance

$$\mathbb{V}^{\mathbb{P}}[\ln(A_1/A)] \;=\; \sigma^2\,\Delta t \tag{2.39}$$

is exact (not just leading-order) because the $\pm\sigma\sqrt{\Delta t}$ Bernoulli has variance $\sigma^2\Delta t$ by construction, and the deterministic drift $(\mu - \tfrac{1}{2}\sigma^2)\Delta t$ drops out of the variance.

### 2.4.3 Risk-neutral probability $q$ under parameterisation II

Applying the martingale condition $A = e^{-r\Delta t}\mathbb{E}^{\mathbb{Q}}[A_1]$ to tree (2.36) with $\mathbb{Q}$-probabilities $(q, 1-q)$:

$$A \;=\; e^{-r\Delta t}\!\left[\,q\, A\, e^{(\mu - \tfrac{1}{2}\sigma^2)\Delta t + \sigma\sqrt{\Delta t}} \;+\; (1-q)\, A\, e^{(\mu - \tfrac{1}{2}\sigma^2)\Delta t - \sigma\sqrt{\Delta t}}\,\right]. \tag{2.40}$$

Solving for $q$:

$$q \;=\; \frac{e^{r\Delta t} - e^{(\mu - \tfrac{1}{2}\sigma^2)\Delta t - \sigma\sqrt{\Delta t}}}{e^{(\mu - \tfrac{1}{2}\sigma^2)\Delta t + \sigma\sqrt{\Delta t}} - e^{(\mu - \tfrac{1}{2}\sigma^2)\Delta t - \sigma\sqrt{\Delta t}}} \;=\; \frac{e^{(r - (\mu - \tfrac{1}{2}\sigma^2))\Delta t} - e^{-\sigma\sqrt{\Delta t}}}{e^{+\sigma\sqrt{\Delta t}} - e^{-\sigma\sqrt{\Delta t}}}. \tag{2.41}$$

Introduce the shorthand $\hat r := r - (\mu - \tfrac{1}{2}\sigma^2)$. Expanding to $O(\sqrt{\Delta t})$:

$$q \;\sim\; \frac{(1 + \hat r\Delta t) - (1 - \sigma\sqrt{\Delta t} + \tfrac{1}{2}\sigma^2\Delta t)}{(1 + \sigma\sqrt{\Delta t} + \tfrac{1}{2}\sigma^2\Delta t) - (1 - \sigma\sqrt{\Delta t} + \tfrac{1}{2}\sigma^2\Delta t)} + \cdots \;=\; \frac{\sigma\sqrt{\Delta t} + (\hat r - \tfrac{1}{2}\sigma^2)\Delta t}{2\sigma\sqrt{\Delta t}} + \cdots, \tag{2.42}$$

$$q \;\sim\; \tfrac{1}{2}\!\left[\,1 + \frac{\hat r - \tfrac{1}{2}\sigma^2}{\sigma}\sqrt{\Delta t}\,\right] + \cdots \;=\; \tfrac{1}{2}\!\left[\,1 + \frac{r - \mu}{\sigma}\sqrt{\Delta t}\,\right] + \cdots, \tag{2.43}$$

where the last step uses $\hat r - \tfrac{1}{2}\sigma^2 = r - (\mu - \tfrac{1}{2}\sigma^2) - \tfrac{1}{2}\sigma^2 = r - \mu$.

Comparison with classical CRR (2.23):

$$q_{\text{CRR}} \;\sim\; \tfrac{1}{2}\!\left[\,1 + \frac{r - \tfrac{1}{2}\sigma^2}{\sigma}\sqrt{\Delta t}\,\right] + \cdots \tag{2.44}$$

The two $q$'s differ at $O(\sqrt{\Delta t})$ by exactly the physical drift term, because parameterisation II has already absorbed the drift $(\mu - \tfrac{1}{2}\sigma^2)$ into the node geometry. In the continuous-time limit both parameterisations yield the same lognormal $A_T$ distribution under $\mathbb{Q}$ — consistent with (2.30).

### 2.4.4 Reconciling parameterisations I and II

By construction of $q$ in (2.40) the martingale relation $\mathbb{E}^{\mathbb{Q}}[A_1] = A e^{r\Delta t}$ is exact, and $\mathbb{V}^{\mathbb{Q}}[\ln(A_1/A)] = \sigma^2\Delta t + O(\Delta t^{3/2})$. A one-parameter family unifies the two: take node geometry $A\,e^{(\alpha - \tfrac12\sigma^2)\Delta t \pm \sigma\sqrt{\Delta t}}$ with probability $p = \tfrac12[1 + (\mu - \alpha)\sqrt{\Delta t}/\sigma] + \cdots$. The choice $\alpha = \mu$ recovers parameterisation II ($p = \tfrac12$); $\alpha = 0$ recovers classical CRR. All choices converge to the same GBM; they only differ in finite-$\Delta t$ convergence constants. When comparing two binomial-tree implementations, always check the parameterisation convention — a 0.5% discrepancy at $N=100$ may just reflect different $\alpha$.

---

## 2.5 The Fundamental Theorem of Asset Pricing

FTAP. No arbitrage $\iff$ there exists $\mathbb{Q} \sim \mathbb{P}$ such that for every traded asset $X$, the discounted price $\tilde{X}_t = X_t/B_t$ is a $\mathbb{Q}$-martingale:

$$\tilde{X}_t \;=\; \mathbb{E}^{\mathbb{Q}}\!\left[\,\tilde{X}_s \mid \mathcal{F}_t\,\right], \qquad s \ge t. \tag{2.48}$$

The physical measure $\mathbb{P}$ describes how the world evolves; $\mathbb{Q}$ re-weights so all tradable risks have zero expected excess return. Equivalence $\mathbb{Q} \sim \mathbb{P}$ means agreement on null sets — essential, else we could win on a $\mathbb{P}$-non-null event the $\mathbb{Q}$-price ignores.

Two flavours: *First FTAP* (no-arb $\Leftrightarrow$ $\mathcal{M}_e \neq \emptyset$) and *Second FTAP* (completeness $\Leftrightarrow$ $|\mathcal{M}_e| = 1$). Binomial trees satisfy both; trinomial trees (or any market with more states than tradables) satisfy only the first and admit a family of $\mathbb{Q}$. The Delbaen–Schachermayer extension to semimartingales replaces "no arbitrage" by "no free lunch with vanishing risk" (NFLVR). The natural numéraire is the money-market account $B_t = e^{rt}$ but any strictly positive traded asset works; this freedom is exploited in CH05.

---

## 2.6 Non-Uniqueness of the Martingale Measure

The binomial tree's completeness is an artefact of the lattice. Real markets have far more states than tradable instruments — jumps, stoch-vol, default, liquidity freezes — and any one of these creates an un-spanned payoff. In the one-step binomial $\mathbb{Q}$ was pinned down by one linear equation in one unknown $q$; once the underlying branches to three or more states, $\mathbb{Q}$ is no longer unique. The FTAP still holds; $\mathcal{M}_e$ is non-empty but not a singleton.

Selecting a single price from the arbitrage-free interval is what the calibration industry does: fitting $\mathbb{Q}$ to liquid benchmark instruments (vanilla options, CDS), utility-based criteria, or robust pricing under ambiguity each pick a representative element of $\mathcal{M}_e$.

Why three post-states destroys uniqueness: each tradable adds one linear constraint $\mathbb{E}^{\mathbb{Q}}[X_1] = X_0 e^{r\Delta t}$, while an $n$-state probability vector has $n-1$ free coordinates. For $n = k$ tradables, the system is exactly determined; for $k < n$, $\mathcal{M}_e$ is $(n-k)$-dimensional. Adding tradables (e.g. index options) restores uniqueness — this is the *calibration-to-market* strategy that dominates quant practice.

We have two martingale equations (for cash and the stock) but three or four unknown probabilities, so

$$\mathbb{Q} \text{ is not unique} \;\Longrightarrow\; C_0 \text{ is not necessarily unique.} \tag{2.50}$$

In incomplete markets the price spans an *arbitrage-free interval*: from the super-replication cost (cheapest dominating portfolio) to the sub-replication value. The market-clearing price within this interval depends on risk preferences, hedging technology, and supply–demand.

![Trinomial tree — non-uniqueness of Q](figures/ch02-trinomial.png)
*Trinomial tree — non-uniqueness of Q*

### 2.6.1 Geometric picture and local risk-minimisation

Tradable assets span a *replicable subspace* of payoff space. A claim in the subspace has a unique price; a claim outside requires a selection criterion. *Local risk-minimisation* projects the claim onto the subspace under $L^2(\mathbb{P})$:

$$C_0 \text{ is unique iff the claim lies in } \operatorname{span}(A_1, B_1), \qquad \min_{(\alpha,\beta)}\,\mathbb{E}^{\mathbb{P}}[(\alpha A_1 + \beta B_1 - C_1)^2]. \tag{2.51–2.52}$$

The foot of the perpendicular is the optimal static hedge; its length is the unhedgeable residual standard deviation. Other rules — minimum-entropy, minimum-variance, Esscher, utility indifference — pick different elements of $\mathcal{M}_e$.

*Worked.* Trinomial $S_0 = 10$, $S_1 \in \{12, 10, 8\}$, $p = (1/3, 1/3, 1/3)$, $r = 0$, call $C_1 = (2, 0, 0)$. Projecting onto $\operatorname{span}(\mathbf{1}, S_1)$: $\beta^\star = (4/3)/(8/3) = 1/2$, $\alpha^\star = -14/3$, residual variance $1/3$. The arbitrage-free interval is $(0, 1)$.

---

## 2.7 Default Model and Incomplete-Market Trees

We build a discrete default model that converges to a diffusion with a jump to zero — our first concrete incomplete-market tree. Default is a *jump process*: rare, catastrophic, discrete. The mathematical framework is a Poisson point process with intensity $\hat\lambda$, the expected rate of jumps per unit time. With three states (up/down/default) and only two tradables (stock, cash), $\mathcal{M}_e$ has dimension one — calibrate $\hat\lambda$ from CDS spreads or corporate bond yields.

The physical intensity $\lambda$ is generally lower than the risk-neutral $\hat\lambda$; the gap is the credit risk premium (for IG issuers, $\hat\lambda$ is 2–5x $\lambda$).

On $[t, t+\Delta t]$:

$$A_n = A_{n-1} \, e^{\sigma \sqrt{\Delta t}\, x_n}, \qquad p = \tfrac12[1 + (\mu - \tfrac12\sigma^2)\sqrt{\Delta t}/\sigma]. \tag{2.53}$$

Lifetime $\tau \sim \text{Exp}(\hat\lambda)$. One-step default probability:

$$\mathbb{P}(\tau \in (t, t+\Delta t] | \tau > t) = 1 - e^{-\hat\lambda\Delta t} \approx \hat\lambda\,\Delta t. \tag{2.54}$$

Memorylessness ($\mathbb{P}(\tau > t+s | \tau > s) = \mathbb{P}(\tau > t)$) is the defining feature of the exponential. Empirically wrong (default intensities cluster in time, firms have age effects), but pedagogically clean — Cox/doubly-stochastic processes generalise. Typical IG corporate intensities: $\hat\lambda \in [0.005, 0.015]$/yr; HY: $[0.05, 0.20]$/yr.

### 2.7.1 Branching tree with default branch

From a pre-default node $A_{n-1}$ the tree has three children:

$$A_{n-1} \longrightarrow \begin{cases} A_{n-1}\, e^{+\sigma\sqrt{\Delta t}} & \text{w.p. } p\,(1 - \hat{\lambda}\Delta t) \\[4pt] A_{n-1}\, e^{-\sigma\sqrt{\Delta t}} & \text{w.p. } (1-p)(1 - \hat{\lambda}\Delta t) \\[4pt] 0 & \text{w.p. } \hat{\lambda}\,\Delta t \end{cases} \tag{2.55}$$

The riskless bond pays $e^{r\Delta t}$ in all three states; the risky asset jumps to $0$ on default — the tree is binomial conditional on survival, with a third ray to zero.

### 2.7.2 Survival law

For $\tau \sim \text{Exp}(\hat\lambda)$: $\mathbb{P}(\tau > T) = e^{-\hat\lambda T}$, density $f_\tau(t) = \hat\lambda e^{-\hat\lambda t}$, mean $1/\hat\lambda$. At $\hat\lambda = 5\%$: 5-yr survival $\approx 77.9\%$, 10-yr $\approx 60.7\%$, mean default time 20 years. Time-varying intensity $\hat\lambda(t)$ generalises to $\exp(-\int_0^T \hat\lambda(s)ds)$.

### 2.7.3 Risk-neutral $q$ — default-free sub-case

Setting $\hat\lambda = 0$ recovers (2.22): $q = (e^{r\Delta t} - e^{-\sigma\sqrt{\Delta t}})/(e^{\sigma\sqrt{\Delta t}} - e^{-\sigma\sqrt{\Delta t}}) \sim \tfrac12[1 + (r-\tfrac12\sigma^2)\sqrt{\Delta t}/\sigma]$ — same as before; $\hat\lambda$ is the $\mathbb{Q}$-hazard rate.

### 2.7.4 Including default into the martingale condition

The three-branch martingale condition:

$$1 \;=\; q\,(1 - \hat{\lambda}\Delta t)\, e^{\sigma\sqrt{\Delta t} - r\Delta t} \;+\; (1-q)(1 - \hat{\lambda}\Delta t)\, e^{-\sigma\sqrt{\Delta t} - r\Delta t} \;+\; 0 \cdot \hat{\lambda}\Delta t. \tag{2.59}$$

Solving for $q$:

$$q \;=\; \frac{e^{(r+\hat{\lambda})\Delta t} - e^{-\sigma\sqrt{\Delta t}}}{e^{+\sigma\sqrt{\Delta t}} - e^{-\sigma\sqrt{\Delta t}}} \;\sim\; \tfrac{1}{2}\!\left(1 + \frac{r + \hat{\lambda} - \tfrac{1}{2}\sigma^2}{\sigma}\sqrt{\Delta t}\right) + o(\sqrt{\Delta t}). \tag{2.60}$$

The effect of adding a default branch is therefore to shift the risk-neutral drift upward by $\hat{\lambda}$: the surviving branch must grow faster to compensate for the chance of being wiped out.

*Intuition.* If a fraction $\hat{\lambda}\Delta t$ of your probability mass leaks to zero every step, the conditional expected growth of the survivors has to be higher just to keep the unconditional expectation at $e^{r\Delta t}$. Credit risk premia in corporate bonds have exactly this structure: the yield-to-maturity exceeds the riskless rate by roughly the expected loss rate $\hat{\lambda}\cdot \text{LGD}$.

A concrete credit-pricing illustration. Consider a zero-recovery one-year zero-coupon bond issued by a firm with default intensity $\hat{\lambda} = 3\%$. Its fair price is $e^{-(r+\hat{\lambda})T} = e^{-(0.05+0.03)\cdot 1} \approx 0.923$, compared to the riskless bond price $e^{-rT}\approx 0.951$. The yield spread is therefore $\hat{\lambda} = 3\%$ — the spread is the risk-neutral default intensity (in the zero-recovery case). With recovery $R$ (so loss-given-default is $1-R$), the bond price is $e^{-rT}(e^{-\hat{\lambda}T} + R(1-e^{-\hat{\lambda}T}))\approx e^{-rT}(1 - (1-R)\hat{\lambda} T)$, and the spread is $\hat{\lambda}(1-R)$ to leading order. This is the "spread $=$ probability $\times$ loss" relationship that sits at the heart of the CDS market. The CDS premium quoted by a market-maker *is* the market-implied $\hat{\lambda}(1-R)$, and working back out the probability requires an LGD assumption (typically $R\approx 40\%$ for senior unsecured corporate, so $1-R=60\%$).

Now bring the stock back into the picture. On our default tree, the stock's surviving-branch growth is $e^{(r+\hat{\lambda})\Delta t}$; its unconditional expectation is $e^{r\Delta t}$ because the $\hat{\lambda}$ leak balances the surviving boost. Stockholders — as residual claimants — bear the full loss on default, so the stock's equity risk premium under $\mathbb{Q}$ is pushed upward by the credit component. Equity traders often combine this with Merton's structural credit model: view the firm's equity as a call option on its assets, with strike at the debt's face value. The equity is thus *naturally* a credit-contingent claim, and the same $\hat{\lambda}$ that shows up in debt pricing also shows up in the equity vol surface (high equity vol goes with high credit spreads). The stylised empirical fact is sometimes called the "credit–equity link".

### 2.7.5 Risk-neutral expectations of survival

Under $\mathbb{Q}$ the asset and its discounted version satisfy

$$\mathbb{E}^{\mathbb{Q}}\!\left[A_T \; \mathbf{1}_{\{\tau > T\}}\right] \;=\; A_0\, e^{(r+\hat{\lambda})T}, \tag{2.61}$$

and for the bond-denominated (default-insensitive) notional,

$$\mathbb{E}^{\mathbb{Q}}\!\left[A_T\right] \;=\; A_0\, e^{rT}. \tag{2.62}$$

*Intuition.* Equation (2.62) is the FTAP itself at the horizon: the unconditional expected terminal asset price grows at $r$. Equation (2.61) says that, *conditional on surviving*, the asset grows at the higher rate $r+\hat{\lambda}$. Taking the product with the survival probability $e^{-\hat{\lambda}T}$ recovers (2.62): $e^{(r+\hat{\lambda})T}\cdot e^{-\hat{\lambda}T} = e^{rT}$.

### 2.7.6 European pricing recursion with default

The backward recursion weights all three branches — up survival, down survival, default — by their risk-neutral probabilities. Let $C_{n,j}$ denote the option value at node $(n, j)$:

$$\frac{C_{n-1,j}}{B_{n-1}} \;=\; \mathbb{E}^{\mathbb{Q}}\!\left[\frac{C_n}{B_n}\right], \tag{2.63}$$

$$C_{n-1, j} \;=\; q\, \frac{e^{-\hat{\lambda}\Delta t}}{e^{r\Delta t}}\, C_{n, j} \;+\; (1-q)\, \frac{e^{-\hat{\lambda}\Delta t}}{e^{r\Delta t}}\, C_{n, j+1} \;+\; (1 - e^{-\hat{\lambda}\Delta t})\cdot C_{n, d}, \tag{2.64}$$

where the default node satisfies

$$C_{n-1, d} \;=\; C_{n, d}\, e^{-r\Delta t}. \tag{2.65}$$

(On default the stock is $0$, so a call has $C_{n,d} \equiv 0$; a put has $C_{n,d} = K$ discounted to today.)

*Intuition.* The recursion is the classical binomial backward sweep with two modifications: each surviving branch is down-weighted by the survival factor $e^{-\hat{\lambda}\Delta t}$, and a third term captures what the option is worth *in* default. For a vanilla call that third term is zero, so credit risk eats value monotonically; for a put it is positive (the put still pays on bankruptcy unless it is a "protected put" that voids on the issuer's own default).

Numerical: vanilla 1-year ATM call, $A_0 = K = 100$, $\sigma = 20\%$, $r = 5\%$, $\hat{\lambda} = 2\%$. Black–Scholes (no default) gives $\approx 10.45$; survival-discounted, $10.45 \cdot e^{-0.02} \approx 10.24$. A constant default intensity scales call prices by $e^{-\hat{\lambda}(T-t)}$ to leading order — the standard parameterisation of jump-to-default models.

---

## 2.8 American Valuation on the Binomial Tree

US single-stock equity options are American; index options (SPX, RUT) are European. American exercise lets the holder choose any stopping time $\tau \le T$ — a random time adapted to the filtration ($\{\tau \le t\} \in \mathcal{F}_t$, no peeking). The set of stopping times is combinatorially vast, but Bellman's principle reduces the problem to a one-line recursion: at each node, take the max of intrinsic value and continuation value. The recursion runs backward in $O(N^2)$, and the exercise boundary is the locus where the max is achieved by exercising.

### 2.8.1 European $\to$ American contrast

European pays $\varphi(A_T)$ at fixed $T$:

$$V_t \;=\; e^{-r(T - t)}\,\mathbb{E}^{\mathbb{Q}}\!\left[\,\varphi(A_T)\,\right] \;\longrightarrow\; V_T \;=\; \varphi(A_T). \tag{2.66}$$

American option lets the holder choose the exercise epoch $\tau$, a stopping time bounded above by $T$, and pays $\varphi(A_\tau)$ at $\tau$ — meaning the holder "receives $\varphi(A_\tau)$ at the moment they decide to stop".

American put, in particular:

$$\varphi(A_\tau) \;=\; (K - A_\tau)_+. \tag{2.67}$$

Let $\mathcal{S}$ denote the set of $\{\mathcal{F}_t\}$-stopping times bounded by $T$. Then

$$\frac{C_0}{B_0} \;=\; \sup_{\tau \in \mathcal{S}}\; \mathbb{E}^{\mathbb{Q}}\!\left[\frac{(K - A_\tau)_+}{B_\tau}\right]. \tag{2.68}$$

*Intuition.* The American price is the Snell envelope of the intrinsic process — the smallest $\mathbb{Q}$-supermartingale dominating immediate exercise. The optimal stopping time is $\tau^* = \inf\{t : V_t = I_t\}$, the first hitting time of the exercise region. On the lattice this collapses to: at each node $V_{n,k} = \max(I_{n,k}, V^h_{n,k})$.

### 2.8.2 Tree diagram — hold vs exercise

At every interior node there are two candidate values:

- $P^h$ — the hold/continuation value (from the one-step backward recursion),
- $P^x \equiv (K - A)_+$ — the immediate-exercise (intrinsic) value.

The actual American value is $P = \max(P^h, P^x)$.

<!-- figure placeholder: wedge-shaped binomial tree with terminal nodes A_{T,1}, A_{T,2}, A_{T,3}, A_{T,4}, ... on the right and payoffs (K − A_{T,k})_+ next to each. An "optimal exercise boundary" curve is drawn cutting diagonally across the wedge; above the curve the node is labelled P^x (exercise), below it P^h (hold). Root node P_0 is shown at the apex. -->

### 2.8.3 Dynamic-programming recursion

On a recombining tree with nodes $(n, k)$, propagate two quantities backward:

- Continuation (holding) value $C^{h}_{n-1, k}$:

$$\frac{C^{h}_{n-1, k}}{B_{n-1, k}} \;=\; q\, \frac{C_{n, k}}{B_{n, k}} \;+\; (1-q)\, \frac{C_{n, k+1}}{B_{n, k+1}} \tag{2.69}$$

$$\Longrightarrow\; C^{h}_{n-1, k} \;=\; e^{-r\Delta t}\,\big(\,q\, C_{n, k} \;+\; (1-q)\, C_{n, k+1}\,\big). \tag{2.70}$$

- Intrinsic (immediate exercise) value $C^{I}_{n-1, k}$:

$$C^{I}_{n-1, k} \;=\; (A_{n-1, k} - K)_+ \quad\text{(call)}, \qquad C^{I}_{n-1, k} \;=\; (K - A_{n-1, k})_+ \quad\text{(put)}. \tag{2.71}$$

- American value — take the larger:

$$\boxed{\; C_{n-1, k} \;=\; \max\!\left(\,C^{I}_{n-1, k},\; C^{h}_{n-1, k}\,\right) \;} \tag{2.72}$$

### 2.8.4 Exercise boundary picture

The exercise boundary is a free boundary: $A^*(t)$ is the underlying value at which the American option equals its intrinsic value, determined implicitly by the recursion. For an American put $A^*(t) < K$ and rises toward $K$ as $t \to T$. For an American call on a dividend-paying stock $A^*(t) > K$ and falls toward $K$ near ex-div.

*Intuition.* For an American put on a non-dividend-payer, early exercise is driven by interest on the cash proceeds: when the stock crashes deep enough, $rK$ outweighs remaining optionality. For an American call on a non-dividend-payer the boundary never bites — early exercise is suboptimal (Merton's theorem). The proof is one inequality: $C_t \ge A_t - K e^{-r(T-t)} > A_t - K$, so selling the call always dominates exercising. The argument fails on a dividend-paying stock around ex-div, where capturing the cum-dividend price can beat the post-dividend hold.

The American-put early-exercise premium (AEP) is the gap between American and European puts. At $S_0 = K = 100$, $\sigma = 20\%$, $r = 5\%$, $T = 1$, AEP is a few cents, growing with moneyness, rate, and maturity. No closed form; binomial or Longstaff–Schwartz regression is standard.

![American put early-exercise boundary](figures/ch02-american-exercise.png)
*American put early-exercise boundary*

---

## 2.9 Bridge to Continuous Time

The CRR lattice converged via the CLT to a lognormal $A_T$:

$$A_T \;\stackrel{d}{=}\; A_0\, e^{(r - \tfrac{1}{2}\sigma^2)T \;+\; \sigma\sqrt{T}\, Z_{\mathbb{Q}}}, \qquad Z_{\mathbb{Q}} \sim \mathcal{N}(0, 1). \tag{2.73}$$

That is the marginal at maturity. To upgrade to a *process*, take the scaled sum of Bernoulli shocks,

$$W^N_t \;:=\; \sqrt{\Delta t}\sum_{n=1}^{\lfloor t/\Delta t\rfloor} x_n, \tag{2.74}$$

which converges in distribution (Donsker's functional CLT) to Brownian motion $W_t$. The asset converges to geometric Brownian motion under $\mathbb{Q}$:

$$A_t \;=\; A_0\, e^{(r - \tfrac{1}{2}\sigma^2)t \;+\; \sigma W_t}, \qquad dA_t \;=\; r\,A_t\,dt \;+\; \sigma\,A_t\,dW_t. \tag{2.75}$$

Rigorous derivation needs Brownian motion, the stochastic integral, and Itô's lemma — all built in Ch. 3.

The European call in the GBM limit is the Black–Scholes formula,

$$C_0 \;=\; A_0\,\Phi(d_+) \;-\; K\,e^{-rT}\,\Phi(d_-), \qquad d_\pm \;=\; \frac{\ln(A_0/K) + (r \pm \tfrac{1}{2}\sigma^2)T}{\sigma\sqrt{T}}, \tag{2.76}$$

derived directly via the measure-change split $(A_T - K)_+ = A_T \mathbf{1}_{\{A_T > K\}} - K \mathbf{1}_{\{A_T > K\}}$, pricing each piece under its natural numéraire (stock vs cash) and reading the exceedance probabilities as Gaussian tails. The same formula drops out of the Ch. 6 hedging argument once Itô is available.

Three takeaways from this chapter:

1. The no-arbitrage price of any European claim is a discounted $\mathbb{Q}$-expectation of its payoff.
2. Backward induction makes the expectation $O(N^2)$ and extends to American exercise.
3. In the limit the tree becomes GBM and vanilla Euros become Black–Scholes — pinned down rigorously in Ch. 3–6.

---

## Key Takeaways

1. The one-period no-arb inequality $A_d < A(1 + r) < A_u$ is equivalent to existence of a risk-neutral measure $\mathbb{Q}$ such that $C = (1+r)^{-1}\mathbb{E}^{\mathbb{Q}}[C_1]$.
2. Multi-period backward induction prices any European payoff via repeated one-step discounted risk-neutral expectations — the tower-property manifestation of $C_0 = \mathbb{E}^{\mathbb{Q}}[e^{-rT}C_T]$.
3. Classical CRR calibration. Match two moments of the log-return: $c = \sigma\sqrt{\Delta t}$, $p = \tfrac{1}{2}(1 + \tfrac{\mu}{\sigma}\sqrt{\Delta t})$; the risk-neutral $q = \tfrac{1}{2}(1 + \tfrac{r - \sigma^2/2}{\sigma}\sqrt{\Delta t})$.
4. Alternate CRR (drift-shifted lattice). Nodes $A\cdot e^{(\mu - \tfrac{1}{2}\sigma^2)\Delta t \pm \sigma\sqrt{\Delta t}}$ with symmetric probability $p = \tfrac{1}{2}$; the Itô correction is baked into the geometry. Under $\mathbb{Q}$, $q \sim \tfrac{1}{2}[1 + \tfrac{r - \mu}{\sigma}\sqrt{\Delta t}]$. Both parameterisations converge to the same lognormal GBM.
5. Measure-invariant variance. $\mathbb{V}^{\mathbb{P}}[\ln A_T] = \mathbb{V}^{\mathbb{Q}}[\ln A_T] = \sigma^2 T$ — Girsanov cannot change volatility, only drift.
6. Simple- vs log-return bias. Fitting to simple returns shifts the drift estimate by $+\tfrac{1}{2}\sigma^2$; always be explicit which object is being fit.
7. FTAP equates no-arbitrage to the existence of an equivalent martingale measure $\mathbb{Q}$ under which all discounted traded assets are $\mathbb{Q}$-martingales.
8. Numéraire freedom. Any strictly positive traded asset $B_t$ can discount — picking $B_t$ is picking a measure. Canonical derivation of the change-of-measure mechanics is deferred to Chapter 5.
9. Non-uniqueness of $\mathbb{Q}$ appears as soon as the number of future states exceeds the number of traded assets: the claim may not lie in $\operatorname{span}(A_1, B_1)$. The set $\mathcal{M}_e$ of equivalent martingale measures has dimension $n-k$ for $n$ states and $k$ tradables.
10. Local risk-minimisation $\min_{\alpha,\beta}\mathbb{E}^{\mathbb{P}}[(\alpha A_1 + \beta B_1 - C_1)^2]$ selects a hedge but leaves residual, unhedgeable variance.
11. Default as a third branch adds the probability mass $\hat{\lambda}\Delta t$ at $0$ and shifts the risk-neutral drift by $+\hat{\lambda}$ — the surviving branch must grow faster to compensate. This is our first concrete incomplete-market tree.
12. Binomial-to-GBM limit. With Bernoulli $\pm 1$ increments under $\mathbb{Q}$, $A_T \xrightarrow{d} A_0\, e^{(r - \tfrac{1}{2}\sigma^2)T + \sigma\sqrt{T} Z}$ — the marginal distribution of geometric Brownian motion.
13. Donsker's functional CLT promotes the scaled random walk of the log-price to a Brownian motion $W_t$ on $[0,T]$, giving GBM $dA_t = rA_t\,dt + \sigma A_t\,dW_t$ — deferred to Chapter 3 for the rigorous construction.
14. Black–Scholes $C_0 = A_0\Phi(d_+) - Ke^{-rT}\Phi(d_-)$ is the CRR-limit pricing formula for a European call. The derivation via measure change and Itô's lemma is given in Chapters 5 and 6.
15. American options require pointwise comparison of intrinsic and holding values at every node; the optimal policy is a stopping time defined by the exercise boundary. American calls on non-dividend-paying stock equal European calls (Merton's theorem); American puts have a strictly positive early-exercise premium.
16. Monte-Carlo simulation and path-dependent options (cliquets, barriers, Asians) are treated in Chapter 9, once the GBM path generator has been placed on rigorous footing in Chapter 3.

---

## Reference Formulas

One-period no-arbitrage.
$$A_d < A(1 + r) < A_u \;\iff\; \exists\,\mathbb{Q}\text{ s.t. } C = \tfrac{1}{1+r}\,\mathbb{E}^{\mathbb{Q}}[C_1].$$

FTAP / discounted martingale.
$$\tilde{X}_t = \frac{X_t}{B_t}, \qquad \tilde{X}_t = \mathbb{E}^{\mathbb{Q}}\!\left[\tilde{X}_s \mid \mathcal{F}_t\right].$$

Classical CRR calibration (moment-matching).
$$c \;\sim\; \sigma\sqrt{\Delta t}, \qquad p \;\sim\; \tfrac{1}{2}\!\left(1 + \tfrac{\mu}{\sigma}\sqrt{\Delta t}\right), \qquad q \;\sim\; \tfrac{1}{2}\!\left(1 + \tfrac{r - \tfrac{1}{2}\sigma^2}{\sigma}\sqrt{\Delta t}\right).$$

Alternate CRR (drift-shifted lattice).
$$A \to A\, e^{(\mu - \tfrac{1}{2}\sigma^2)\Delta t \pm \sigma\sqrt{\Delta t}}, \qquad p = \tfrac{1}{2}, \qquad q \;\sim\; \tfrac{1}{2}\!\left[\,1 + \tfrac{r - \mu}{\sigma}\sqrt{\Delta t}\,\right] + \cdots.$$

Log-moment invariance.
$$\mathbb{E}^{\mathbb{P}}[\ln(A_T/A_0)] = \mu T, \qquad \mathbb{E}^{\mathbb{Q}}[\ln(A_T/A_0)] = (r - \tfrac{1}{2}\sigma^2) T, \qquad \mathbb{V}^{\mathbb{P}}[\ln(A_T/A_0)] = \mathbb{V}^{\mathbb{Q}}[\ln(A_T/A_0)] = \sigma^2 T.$$

Local risk-minimising hedge.
$$\min_{(\alpha,\beta)}\, \mathbb{E}^{\mathbb{P}}\!\left[(\alpha A_1 + \beta B_1 - C_1)^2\right].$$

Default-tree risk-neutral probability.
$$q = \frac{e^{(r+\hat{\lambda})\Delta t} - e^{-\sigma\sqrt{\Delta t}}}{e^{+\sigma\sqrt{\Delta t}} - e^{-\sigma\sqrt{\Delta t}}}, \qquad q \sim \tfrac{1}{2}\!\left(1 + \frac{r + \hat{\lambda} - \tfrac{1}{2}\sigma^2}{\sigma}\sqrt{\Delta t}\right).$$

Survival law.
$$\mathbb{P}(\tau > T) = e^{-\hat{\lambda} T}, \quad \mathbb{P}(\tau \in (t, t+\Delta t]) = e^{-\hat{\lambda} t}(1 - e^{-\hat{\lambda}\Delta t}).$$

European recursion (default tree).
$$C_{n-1, j} = q\,\frac{e^{-\hat{\lambda}\Delta t}}{e^{r\Delta t}}\, C_{n, j} + (1-q)\,\frac{e^{-\hat{\lambda}\Delta t}}{e^{r\Delta t}}\, C_{n, j+1} + (1 - e^{-\hat{\lambda}\Delta t})\, C_{n, d}.$$

American recursion.
$$C^{h}_{n-1, k} = e^{-r\Delta t}\big(q\, C_{n, k} + (1-q)\, C_{n, k+1}\big),$$
$$C^{I}_{n-1, k} = (A_{n-1, k} - K)_+ \text{ (call)},\quad (K - A_{n-1, k})_+ \text{ (put)},$$
$$C_{n-1, k} = \max\!\left(C^{I}_{n-1, k},\; C^{h}_{n-1, k}\right).$$

CRR-limit lognormal distribution.
$$A_T \;\stackrel{d}{=}\; A_0\, e^{(r - \tfrac{1}{2}\sigma^2)T + \sigma\sqrt{T}\, Z}, \qquad Z \sim \mathcal{N}(0,1) \text{ under } \mathbb{Q}.$$

GBM continuous-time limit (Donsker).
$$A_t = A_0\, e^{(r - \tfrac{1}{2}\sigma^2)t + \sigma W_t}, \qquad dA_t = r\,A_t\,dt + \sigma\,A_t\,dW_t, \quad W\text{ a $\mathbb{Q}$-Brownian motion.}$$

Black–Scholes formula (CRR limit, derived in Chapter 6).
$$C_0 = A_0\,\Phi(d_+) - K e^{-rT}\,\Phi(d_-), \qquad d_\pm = \frac{\ln(A_0/K) + (r \pm \tfrac{1}{2}\sigma^2)T}{\sigma\sqrt{T}}.$$
