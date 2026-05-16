# Chapter 6 — Dynamic Hedging I: Self-Financing Strategies and the Black-Scholes PDE

With Ch. 3–5 in hand, we derive the Black–Scholes PDE from first principles. Three acts: build the **self-financing replicating portfolio**, force zero local risk, and read off the **market price of risk** (which is the Girsanov shift from $\mathbb{P}$ to $\mathbb{Q}$ — Ch. 5). Derive the **generalised BS PDE**, specialise to GBM, and read off the closed forms for calls, puts, and digitals; then check the same PDE drops out of a Feynman–Kac martingale argument (Ch. 4). Finally, turn to **discrete rebalancing**: hedge-error distribution, $\sqrt{\Delta t}$ variance scaling, and a move-based alternative.

Notation follows Ch. 3. $W_t$ is $\mathbb{P}$-Brownian; $\widetilde W_t$ is its $\mathbb{Q}$-counterpart after the measure change.

---

## 6.1 Setup — underlying, money market, and two contingent claims

The replication argument needs four objects: an index $X$ (observable, not necessarily traded — VIX, credit spread), a money-market account $M$, a traded claim $g$ on $X$ (the hedge instrument), and a new claim $f$ whose value we want to discover. Hedging requires *tradeable* instruments; "selling temperature" is not allowed.

### 6.1.1 The underlying index

Assume there is some underlying index

$$
X = (X_t)_{0 \le t \le T}, \qquad \text{(not necessarily traded)}
$$

that satisfies, under the physical measure $\mathbb{P}$,

$$
\mathrm{d}X_t \;=\; \underbrace{\mu(t,X_t)}_{\text{drift}}\,\mathrm{d}t
\;+\; \underbrace{\sigma(t,X_t)}_{\text{volatility}}\,\mathrm{d}W_t. \tag{6.1}
$$

$X_t$ is the source of uncertainty — stock, index, spread, variance process. The $(t, X_t)$-dependence accommodates every popular single-factor diffusion: constant vol (GBM), local vol, scheduled-event time-dependent vol. Punchline: the drift $\mu$ is irrelevant for hedging — only $\sigma$ and $r$ feed into the price.

### 6.1.2 The money-market account

The money-market account is traded:

$$
M = (M_t)_{0 \le t \le T},\qquad
\frac{\mathrm{d}M_t}{M_t} \;=\; r(t,X_t)\,\mathrm{d}t. \tag{6.2}
$$

No $\mathrm{d}W_t$ term — cash grows deterministically. The rate may depend on $(t, X_t)$, covering stochastic-rate models; we treat $r$ as constant for closed forms. The mathematical fact that matters: $M$ has finite variation, so $\mathrm d[M, M]_t = 0$ and cash cross-variation terms drop out of the self-financing expansion.

### 6.1.3 A traded contingent claim $g$

Some contingent claim on $X$, call this claim $g$, is traded:

$$
g = (g_t)_{0 \le t \le T}, \qquad g_t = g(t,X_t).
$$

By Itô's lemma (Chapter 3),

$$
\frac{\mathrm{d}g_t}{g_t} \;=\; \mu^g(t,X_t)\,\mathrm{d}t \;+\; \sigma^g(t,X_t)\,\mathrm{d}W_t, \tag{6.3}
$$

and in general

$$
\mathrm{d}g_t \;=\; \Big( \partial_t g(t,X_t) + \partial_x g(t,X_t)\,\mu(t,X_t)
+ \tfrac{1}{2}\,\partial_{xx} g(t,X_t)\,\sigma^2(t,X_t) \Big)\,\mathrm{d}t
\;+\; \partial_x g(t,X_t)\,\sigma(t,X_t)\,\mathrm{d}W_t. \tag{6.4}
$$

$g$ is the hedge workhorse: a tradeable Itô-driven instrument sharing the same Brownian $W$ as $X$, so a linear combination can cancel the $\mathrm dW$ noise. The three drift pieces of (6.4) are: $\partial_t g$ (theta — passage of time), $\partial_x g \cdot \mu$ (directional chain rule), and $\tfrac12 \partial_{xx} g \cdot \sigma^2$ (Itô correction — half gamma times instantaneous variance). The last term is the mathematical seed of every gamma-trading argument later in the guide.

### 6.1.4 Goal — price a new claim $f$

Goal: value a new claim $f = (f_t)_{0 \le t \le T}$ which pays at maturity

$$
f_T \;=\; \varphi(X_T),
$$

where $\varphi$ is the payoff, e.g. $\varphi(x) = (x - K)_+$ for a vanilla
call. Write $f_t = f(t,X_t)$. By Itô's lemma

$$
\frac{\mathrm{d}f_t}{f_t} \;=\; \mu^f(t,X_t)\,\mathrm{d}t \;+\; \sigma^f(t,X_t)\,\mathrm{d}W_t. \tag{6.5}
$$

Itô fixes $\mu^f$ and $\sigma^f$ in terms of partial derivatives of $f$ and the coefficients of $X$. That fact turns the hedging argument into a PDE.

The ansatz $f_t = f(t, X_t)$ works for vanillas; path-dependent payoffs (barriers, lookbacks, Asians) need an augmented state. **Completeness:** one Brownian plus one traded $g$ replicates every $(t, X_t)$-claim. Stoch-vol or extra factors break this and need another option in the hedge basis.

---

## 6.2 The self-financing replicating portfolio

Hold $\alpha_t$ units of $g_t$, $\beta_t$ units of $M_t$, and $-1$ unit of $f_t$. Long the hedge, short the option; pick $(\alpha_t, \beta_t)$ to neutralise the short $f$ at every instant. If replication succeeds, the terminal hedge value equals $\varphi(X_T)$ and the option's value today is the cost of starting the hedge on day zero.

Define the portfolio value

$$
V_t \;=\; \alpha_t\,g_t + \beta_t\,M_t - f_t. \tag{6.6}
$$

Require $V_0 = 0$ — the replicating package costs exactly $f_0$ (otherwise free money). All subsequent moves come from rebalancing between stock and cash; no fresh cash enters.

### 6.2.1 Naïve differentiation vs self-financing

Taking the total differential:

$$
\mathrm{d}V_t \;=\; \mathrm{d}(\alpha_t g_t) + \mathrm{d}(\beta_t M_t) - \mathrm{d}f_t.
$$

Expanding by Itô's product rule (Chapter 3),

$$
\mathrm{d}V_t \;=\; \underbrace{\mathrm{d}\alpha_t\,g_t}_{\text{extra}}
+ \alpha_t\,\mathrm{d}g_t + \underbrace{\mathrm{d}[\alpha,g]_t}_{\text{extra}}
+ \underbrace{\mathrm{d}\beta_t\,M_t}_{\text{extra}}
+ \beta_t\,\mathrm{d}M_t + \underbrace{\mathrm{d}[\beta,M]_t}_{=\,0}
- \mathrm{d}f_t. \tag{6.7}
$$

$\mathrm{d}[\beta,M]_t = 0$ because $M$ has finite variation. The self-financing constraint forces the rebalancing pieces to cancel:

$$
\mathrm{d}\alpha_t\,g_t + \mathrm{d}[\alpha,g]_t + \mathrm{d}\beta_t\,M_t \;=\; 0. \tag{6.8}
$$

Ordinary calculus says $\mathrm{d}(\alpha g) = \alpha\,\mathrm{d}g + g\,\mathrm{d}\alpha$. That is mathematically correct but financially wrong: the $g\,\mathrm{d}\alpha$ term is the dollar cost of buying new shares, which the trader funds from cash — not thin air. (6.8) says the cash leg shrinks by exactly that amount, so the rebalance itself is value-neutral. Only mark-to-market moves the portfolio.

When $\alpha_t = \partial_x f(t, X_t)$ (an Itô process), the cross-variation $\mathrm d[\alpha, g]_t$ is non-zero and lives in the rebalance leg; in the discrete world of §6.11 it is the $(\alpha_{t_n} - \alpha_{t_{n-1}}) X_{t_n}$ piece of the bank recursion.

### 6.2.2 Interpreting self-financing

Between $t$ and $t + \Delta t$ wealth moves only with $\Delta g_t$ and $\Delta M_t$:

$$
\Delta V_t \;=\; \alpha_t\,(\Delta g_t) + \beta_t\,(\Delta M_t) - \Delta f_t. \tag{6.9}
$$

A self-financing portfolio's wealth is pathwise determined by the asset paths and the initial position. If two self-financing portfolios end at the same terminal value on every path, they must have the same value today — otherwise long the cheap, short the expensive: free lunch.

![Self-financing vs violation](figures/ch06-self-financing-violation.png)
*Dropping the rebalance-cost term fabricates PnL — the classic "something
for nothing" that (6.8) forbids.*

### 6.2.3 Applying the self-financing constraint

After cancellation,

$$
\mathrm{d}V_t \;=\; \alpha_t\,\mathrm{d}g_t + \beta_t\,\mathrm{d}M_t - \mathrm{d}f_t. \tag{6.10}
$$

The only surviving terms are the three "mark-to-market" pieces: the P&L
from the $\alpha_t$ shares of $g$ because $g$ moved, the interest accrual
on the bank account, and the change in the liability $f$. There is
*nothing else*.

Substituting (6.2), (6.3), (6.5):

$$
\mathrm{d}V_t \;=\; \alpha_t\big(\mu^g_t g_t\,\mathrm{d}t + \sigma^g_t g_t\,\mathrm{d}W_t\big)
+ \beta_t M_t r_t\,\mathrm{d}t
- \big(\mu^f_t f_t\,\mathrm{d}t + \sigma^f_t f_t\,\mathrm{d}W_t\big). \tag{6.11}
$$

Collecting drift and diffusion,

$$
\boxed{\;\mathrm{d}V_t \;=\; \big(\alpha_t\mu^g_t g_t + \beta_t M_t r_t - \mu^f_t f_t\big)\,\mathrm{d}t
\;+\; \big(\alpha_t\sigma^g_t g_t - \sigma^f_t f_t\big)\,\mathrm{d}W_t\;} \tag{6.12}
$$

Equation (6.12) has the form $\mathrm{d}V_t = \text{drift}\,\mathrm{d}t +
\text{noise}\,\mathrm{d}W_t$, and we have two free knobs — $\alpha_t$ and
$\beta_t$ — to play with. The strategy is exactly what a sensible trader
would do in words: first get rid of the noise (pick $\alpha_t$ to
annihilate the $\mathrm{d}W_t$ coefficient), then inspect what remains and
let economics constrain the rest.

This two-stage procedure — kill noise, then inspect drift — is the
mathematical heart of every replication argument in finance. If the
underlying has $k$ sources of risk instead of one, we need $k$ traded
claims instead of one; we pick $k$ holdings to kill each of the $k$ noise
terms simultaneously; the remaining drift must equal the risk-free rate on
the net cash position. In the Heston stochastic-volatility model, for
example, there are two sources of risk (the stock's diffusion and the
volatility's diffusion), and we need two hedge instruments (the stock and
another option) to kill both.

---

## 6.3 Locally removing the risk — the delta-hedge ratio

Locally remove risk, so set the $\mathrm{d}W_t$ coefficient to zero:

$$
\alpha_t\,\sigma^g_t\,g_t - \sigma^f_t\,f_t \;=\; 0
\;\;\Longrightarrow\;\;
\boxed{\;\alpha_t \;=\; \frac{\sigma^f_t}{\sigma^g_t}\,\frac{f_t}{g_t}\;} \tag{6.13}
$$

This is the delta-hedge ratio in its most general form. Before we unpack
it, note what we have achieved: the instant we pick $\alpha_t$ as above,
the *random* part of $\mathrm{d}V_t$ — the bit that depends on which
direction the Brownian motion happened to move — disappears. Over a small
enough interval, the portfolio is locally riskless.

The formula has a crystalline interpretation: $\alpha_t$ is the ratio of
the dollar-volatilities of $f$ and $g$. If $f$ is twice as volatile in
dollar terms as $g$, we need twice as many units of $g$ to keep up. In
the common case where $g = X$ (the stock itself is traded), we have
$\sigma^g_t g_t = \sigma^x_t$ and $\sigma^f_t f_t = \sigma^x_t\,\partial_x
f$, so the ratio collapses to $\alpha_t = \partial_x f$ — the partial
derivative of the option value with respect to the spot, a.k.a. the
*delta*. The replicating portfolio is the option's Doppelgänger: at each
instant, it holds exactly as much stock as the option's price is sensitive
to the stock — no more, no less.

A concrete numerical illustration. Suppose the stock is trading at \$100
with $\sigma = 20\%$, so the dollar volatility of one share is roughly
$100 \cdot 0.20 = 20$ dollars per unit of $W$. Suppose the option we are
hedging has $\partial_x f = 0.6$, so its dollar volatility is $0.6 \cdot
20 = 12$ dollars per unit of $W$. To neutralise the option's Brownian
motion exposure, we hold $0.6$ shares of stock. If the stock now moves by
1% in a tiny interval, the option's price moves by $0.6 \cdot 1\% \cdot
100 = 0.60$ dollars and the share position moves by $0.6 \cdot 1 = 0.60$
dollars — they cancel to the instant.

A useful edge case. A deep-ITM call has delta approaching 1, so the
hedger holds roughly one full share per option. A deep-OTM call has delta
approaching 0, so the hedger holds almost no stock, and the bank account
is approximately the option's premium invested at the risk-free rate. Again,
gamma is nearly zero, rebalancing is minimal. The hedging problem is
*easy* in both extremes and hardest *at the money*, where the delta is
around 0.5 but the gamma is large and rebalancing is frequent.

One subtlety worth flagging: the formula $\alpha_t = \partial_x f(t, X_t)$
is not a *static* ratio. As time passes and the stock moves, both arguments
of the partial derivative change, and the required hedge ratio changes
too. This is why dynamic hedging is called *dynamic*: the hedge ratio is a
moving target that must be chased.

With this choice,

$$
\mathrm{d}V_t \;=\; \big(\alpha_t \mu^g_t g_t + \beta_t M_t r_t - \mu^f_t f_t\big)\,\mathrm{d}t
\;=\; \mathcal{A}_t\,\mathrm{d}t. \tag{6.14}
$$

After the $\mathrm{d}W_t$ term has been killed, the remaining dynamics are
purely deterministic over an infinitesimal interval. The portfolio earns
some drift $\mathcal{A}_t$ per unit time, and the question becomes: what
does that drift have to be?

### 6.3.1 No-arbitrage forces $\mathcal{A}_t = 0$

- If $\mathcal{A}_t > 0$: profit guaranteed — arbitrage.
- If $\mathcal{A}_t < 0$: reverse the strategy to get profit.

The argument is stark. We have built, by pure bookkeeping, a self-financing
portfolio with zero initial cost ($V_0 = 0$) and zero instantaneous risk.
If its value drifts upward, we are printing money; if it drifts downward,
we swap the signs of all holdings and *then* we are printing money. The
only logical possibility consistent with no free lunches is that the drift
is exactly zero.

Therefore, to avoid arbitrage,

$$
\boxed{\;\mathcal{A}_t \;=\; 0\;}. \tag{6.15}
$$

Combined with $V_0 = 0$, the entire portfolio process satisfies $V_t = 0$
for all $t$, hence

$$
\mathcal{A}_t = 0 \;\Longrightarrow\; V_t = 0 \;\Longrightarrow\;
\alpha_t g_t + \beta_t M_t - f_t = 0
\;\Longrightarrow\; \beta_t M_t \;=\; f_t - \alpha_t g_t. \tag{6.16}
$$

(6.16) is the pricing identity. The unique cash holding that keeps the hedge costless is $f_t - \alpha_t g_t$ — equivalently, the option's value equals the value of the self-financing stock-plus-cash package that replicates it.

Numerical: option \$3.50, delta 0.6, stock \$100. Hold 0.6 shares (\$60) and borrow \$56.50; package value $0.6 \cdot 100 - 56.50 = 3.50$. Stock rises to \$101: shares worth \$60.60, option rises by $0.6 \cdot 1 = \$0.60$ to \$4.10. New delta 0.62 — buy 0.02 shares, fund via borrowing. Repeat every instant.

---

## 6.4 Market price of risk

Unpack the zero-drift consequence as a statement about expected returns. Write out $\mathcal{A}_t = 0$:

$$
\alpha_t \mu^g_t g_t + r_t\,(f_t - \alpha_t g_t) - \mu^f_t f_t \;=\; 0. \tag{6.17}
$$

Rearrange,

$$
\alpha_t\,\mu^g_t\,g_t + r_t f_t - r_t \alpha_t g_t - f_t \mu^f_t \;=\; 0. \tag{6.18}
$$

Recall $\alpha_t = \dfrac{\sigma^f_t}{\sigma^g_t}\dfrac{f_t}{g_t}$.
Substituting and dividing by $f_t$,

$$
\frac{\mu^g_t - r_t}{\sigma^g_t} \;=\; \frac{\mu^f_t - r_t}{\sigma^f_t}
\;=\; \lambda_t \;=\; \lambda(t,X_t). \tag{6.19}
$$

> **Sharpe ratios of all assets on the underlying index are equal.**

Every derivative on $X$ — call, digital, variance swap, structured product — has the same expected excess return per unit of volatility, despite wildly different drifts and vols. $\lambda_t$ is the **market price of risk** — a market property, not an asset-specific quantity:

$$
\boxed{\;\frac{\mu^f_t - r_t}{\sigma^f_t} \;=\; \lambda_t
\;\Longleftrightarrow\;
\mu^f_t - r_t \;=\; \lambda_t\,\sigma^f_t\;}. \tag{6.20}
$$

> **Connection to Girsanov.** Ch. 5 says: a Girsanov shift by $\lambda_t$ makes $\widetilde W_t = W_t + \int_0^t \lambda_s\,\mathrm{d}s$ a $\mathbb{Q}$-Brownian motion, and $X$'s drift becomes $\mu^x_t - \sigma^x_t \lambda_t$. (6.20) picks out *exactly* the shift that neutralises the risk premium: under $\mathbb{Q}$, every traded claim drifts at $r_t$. Market price of risk and Girsanov shift are the same scalar.

Rewriting (6.20) as $\mu^f_t = r_t + \lambda_t \sigma^f_t$: expected return = risk-free rate + vol $\times$ price-per-unit-vol. Under $\mathbb{Q}$ the risk premium is zero (the replicator sees no risk). The shift is drift-only, leaving diffusion measure-invariant — gamma and vega P&L are unchanged. Long-run US equity Sharpe of ~0.4 is the empirical $\lambda$; spikes in crises.

---

## 6.5 The generalised Black-Scholes PDE

The scalar identity $\mu^f - r = \lambda \sigma^f$ becomes a PDE once we substitute the Itô expressions for $\mu^f$ and $\sigma^f$ in terms of partial derivatives of $f(t, x)$. Via Itô's lemma:

$$
\mu^f_t \;=\; \frac{\partial_t f_t + \mu^x_t\,\partial_x f_t
+ \tfrac{1}{2}(\sigma^x_t)^2\,\partial_{xx}f_t}{f_t}, \tag{6.21}
$$

$$
\sigma^f_t \;=\; \frac{\sigma^x_t\,\partial_x f_t}{f_t}. \tag{6.22}
$$

(Here $\mu^x_t,\sigma^x_t$ are the coefficients of $X$ from (6.1).) Plug
into $\mu^f_t - r_t = \lambda_t \sigma^f_t$:

$$
\partial_t f_t + \big(\mu^x_t - \sigma^x_t \lambda_t\big)\,\partial_x f_t
+ \tfrac{1}{2}(\sigma^x_t)^2\,\partial_{xx}f_t \;=\; r_t\,f_t. \tag{6.23}
$$

This has to hold $\forall (t,x)$. Hence:

$$
\boxed{\;\begin{aligned}
&\partial_t f(t,x) + \big(\mu^x(t,x) - \sigma^x(t,x)\,\lambda(t,x)\big)\,\partial_x f(t,x) \\
&\qquad + \tfrac{1}{2}\big(\sigma^x(t,x)\big)^2\,\partial_{xx}f(t,x) \;=\; r(t,x)\,f(t,x), \\
&\qquad\qquad\qquad\qquad\qquad f(T,x) \;=\; \varphi(x).
\end{aligned}\;} \tag{6.24}
$$

**Generalised Black-Scholes PDE.** Backwards parabolic; the terminal $f(T, x) = \varphi(x)$ anchors the payoff shape and the PDE propagates it back. Sharp features (kinks, steps, cliffs) smooth out as time runs backward — diffusion smearing.

The drift coefficient $\mu^x - \sigma^x \lambda$ is the *risk-neutral* drift, not the physical one — exactly the Girsanov shift (Ch. 5). The $\tfrac12 (\sigma^x)^2 \partial_{xx} f$ term is the Itô curvature, independent of drift — which is why option prices do not depend on $\mu$. The RHS $r f$ says the replicator grows at the risk-free rate.

> **What happens when $\Delta$ is wrong.** If $\alpha_t \neq \partial_x f$, the $\mathrm{d}W_t$ coefficient is non-zero. Hedge error over $[t, t+\mathrm{d}t]$ is $(\alpha_t \sigma^g_t g_t - \sigma^f_t f_t)\,\mathrm{d}W_t$ — mean-zero noise plus a second-order $\tfrac12 \partial_{xx} f (\mathrm{d}X_t^2 - \sigma^2 X_t^2 \mathrm{d}t)$ that accumulates as realised-minus-implied variance. This is the **P&L attribution**: discretely-hedged short gamma loses money when realised vol exceeds implied. See `ch06-hedge-error.png`.

Equivalently, an option is a position in variance: instantaneous P&L is $\tfrac12 \Gamma S^2 (\sigma_{\text{imp}}^2 - \sigma_{\text{real}}^2)\,\mathrm dt$. The PDE is linear in $f$, so portfolio prices are sums of individual prices.

![BS-PDE coefficients](figures/ch06-pde-coefficients.png)
*Theta pays for gamma: the three LHS terms balance $r f$ exactly — the dotted residual is numerically zero.*

---

## 6.6 Specialising to Black-Scholes (GBM)

Specialise to GBM, where the stock has constant proportional drift and vol and is traded directly ($g = X$):

$$
\mu^x(t,x) \;=\; \mu x, \qquad \sigma^x(t,x) \;=\; \sigma x,
$$

so

$$
\mathrm{d}X_t \;=\; X_t \mu\,\mathrm{d}t + X_t \sigma\,\mathrm{d}W_t. \tag{6.25}
$$

In divided form, $\mathrm{d}S_t/S_t = \mu\,\mathrm{d}t + \sigma\,\mathrm{d}W_t$. Itô on $\ln S_t$ gives

$$
\mathrm{d}(\ln S_t) \;=\; \big(\mu - \tfrac12\sigma^2\big)\,\mathrm{d}t \;+\; \sigma\,\mathrm{d}W_t,
$$

which integrates immediately. Exponentiating,

$$
S_t \;=\; S_0\,\exp\!\Big(\big(\mu - \tfrac12\sigma^2\big)\,t \;+\; \sigma W_t\Big)
\;\stackrel{d}{=}\; S_0\,\exp\!\Big(\big(\mu - \tfrac12\sigma^2\big)\,t \;+\; \sigma\sqrt{t}\,Z\Big),
\qquad Z \sim \mathcal{N}(0,1).
\tag{6.25a}
$$

$S_t$ is log-normal with log-mean $(\mu - \tfrac12\sigma^2)t$ and log-variance $\sigma^2 t$. The $-\tfrac12\sigma^2$ Itô correction is what makes $\mathbb{E}[S_t] = S_0 e^{\mu t}$ exactly.

With $g(t, x) = x$ ($\sigma^g = \sigma$, $\mu^g = \mu$) and constant $r$,

$$
\lambda \;=\; \frac{\mu - r}{\sigma}. \tag{6.26}
$$

In GBM, $\lambda$ is literally the stock's Sharpe ratio — the origin of the name and the motivation for $\mathbb{Q}$ as the measure under which the stock drifts at $r$. Substituting into (6.24):

$$
\partial_t f + \underbrace{(\mu - \sigma\lambda)}_{=\,r}\,x\,\partial_x f
+ \tfrac{1}{2}\sigma^2 x^2\,\partial_{xx}f \;=\; r f.
$$

$$
\boxed{\;\begin{aligned}
&\partial_t f + r\,x\,\partial_x f + \tfrac{1}{2}\sigma^2 x^2\,\partial_{xx} f \;=\; r f, \\
&f(T,x) \;=\; \varphi(x).
\end{aligned}\;} \tag{6.27}
$$

**Black-Scholes PDE.** The stock's physical drift $\mu$ has disappeared completely — absorbed by $\mu - \sigma\lambda = r$. Two stocks with the same $\sigma$ but different $\mu$ produce identical call prices because the hedger replicates state-by-state regardless of drift; cost depends on how hard the replication machine has to work (vol), not on direction. Implied volatility is then the market's $\mathbb{Q}$-measure forecast of root-mean-square log-returns; for liquid equity options the gap to the $\mathbb{P}$-forecast is small.

---

## 6.7 Black-Scholes formulas for call, put, and digital

The closed forms follow from (6.27) by ansatz, by direct $\mathbb{Q}$-expectation under (6.25a), or via Feynman–Kac (Ch. 4). Derivation in §6.7A.

**Vanilla call.** For $\varphi(x) = (x - K)_+$,

$$
\boxed{\;f(t,x) \;=\; x\,\Phi(d_+) \;-\; K\,e^{-r(T-t)}\,\Phi(d_-)\;} \tag{6.28}
$$

with

$$
d_\pm \;=\; \frac{\ln(x/K) + \big(r \pm \tfrac{1}{2}\sigma^2\big)(T-t)}{\sigma\sqrt{T-t}}. \tag{6.29}
$$

**Black–Scholes call.** Two pieces: $x\Phi(d_+)$ is the expected stock payoff conditional on ITM expiry (under the stock-numeraire measure); $Ke^{-r(T-t)}\Phi(d_-)$ is the discounted strike times the $\mathbb{Q}$-probability of ITM expiry. The symmetry $d_+ = d_- + \sigma\sqrt{T-t}$ is the "vol lift" — conditional on finishing ITM the expected log-price sits above its unconditional median.

**Vanilla put** via put-call parity. From $(X_T - K)_+ - (K - X_T)_+ = X_T - K$:

$$
\boxed{\;C(t,x) - P(t,x) \;=\; x - K\,e^{-r(T-t)}\;} \tag{6.30}
$$

Parity is **model-independent**: it follows from the algebraic identity plus existence of $\mathbb{Q}$. Violations are the cleanest arbitrage signal. Solving for $P$:

$$
\boxed{\;P(t,x) \;=\; K\,e^{-r(T-t)}\,\Phi(-d_-) \;-\; x\,\Phi(-d_+)\;} \tag{6.31}
$$

**Digital call.** For $\varphi(x) = \mathbb{1}_{x \ge K}$, the price is the discounted $\mathbb{Q}$-ITM probability:

$$
\boxed{\;f(t,x) \;=\; e^{-r(T-t)}\,\Phi(d_-)\;} \tag{6.32}
$$

since $\{X_T \ge K\} = \{Z \ge -d_-\}$ under GBM.

### 6.7.1 Greeks from the closed form

The **strike-shifting identity** $x\phi(d_+) = Ke^{-r(T-t)}\phi(d_-)$ collapses the algebra:

- **Delta**: $\Delta^C \;=\; \partial_x f \;=\; \Phi(d_+) \in (0,1)$.
- **Gamma**: $\Gamma^C \;=\; \partial_{xx} f \;=\; \dfrac{\phi(d_+)}{x\,\sigma\sqrt{T-t}}$.
- **Vega**: $\mathcal{V}^C \;=\; \partial_\sigma f \;=\; x\,\phi(d_+)\,\sqrt{T-t}$.

For the put, parity gives $\Delta^P = \Delta^C - 1 \in (-1, 0)$ and
$\Gamma^P = \Gamma^C$ (differentiating parity twice in $x$): calls and
puts of the same strike and maturity have *identical* gamma. Vega is
also shared: $\mathcal{V}^P = \mathcal{V}^C$.

The gamma formula exhibits a striking $1/\sqrt{T-t}$ divergence at the
money as $t \to T$: the at-the-money gamma blows up like $1/\sqrt{T-t}$.
This is the *pin gamma* phenomenon — on expiration day a market-maker's
gamma exposure is effectively all in a narrow band around the strike,
which is why gamma books are rebalanced with extra care on expiration
Fridays. Integrated across spot, however, $\int \Gamma^C\,\mathrm{d}x =
\Delta^C(\infty) - \Delta^C(0) = 1 - 0 = 1$: the total gamma "mass" is
conserved across time-to-expiry. What changes is how that mass is
distributed spatially.

**Digital greeks.** The digital call's delta from (6.32) is

$$
\partial_x f^{\mathrm{dig}} \;=\; e^{-r(T-t)}\,\frac{\phi(d_-)}{x\,\sigma\sqrt{T-t}},
\tag{6.33}
$$

which has a *pathological* limit as $T - t \to 0$ at $x = K$: the
numerator $\phi(d_-) \to \phi(0) = 1/\sqrt{2\pi}$ is bounded away from
zero, while the denominator $\sqrt{T-t}$ tends to zero. The delta blows
up without bound at the strike. We will visualise this in §6.11.7 and
discuss the call-spread hedge that practitioners use to tame it.

![BS price and delta curves](figures/ch06-price-delta.png)
*BS price and delta curves.*

---

## 6.7A Dual derivation via Feynman-Kac

The self-financing hedging argument of §§6.2–6.5 is the route by which
Black, Scholes, and Merton originally derived the PDE (6.27). There is a
second, entirely independent route that arrives at *exactly* the same PDE
and the same formulas: the **Feynman-Kac** bridge of Chapter 4. Seeing both
routes is worthwhile because they foreground different pieces of the
machinery and their agreement is the mark of a solid theory.

### 6.7A.1 Setup under the risk-neutral measure

Under the risk-neutral measure $\mathbb{Q}$ constructed in Chapter 5, the
traded asset and bank account satisfy

$$
\frac{\mathrm{d}S_t}{S_t} \;=\; r\,\mathrm{d}t \;+\; \sigma\,\mathrm{d}\widetilde W_t, \qquad
\frac{\mathrm{d}M_t}{M_t} \;=\; r\,\mathrm{d}t, \tag{6.34}
$$

where $\widetilde W_t$ is a $\mathbb{Q}$-Brownian motion. The drift is
$r$, not the real-world $\mu$, because $\mathbb{Q}$ is chosen so that
$S_t/M_t$ is a $\mathbb{Q}$-martingale — and that martingale condition
forces the drift of $\mathrm{d}S/S$ to equal $r$. The physical expected
return $\mu$ never appears in derivative prices; it is *absorbed into the
measure change* via the Radon-Nikodym derivative of Chapter 5, with Girsanov
shift $\lambda = (\mu - r)/\sigma$.

### 6.7A.2 Applying Feynman-Kac

The claim $\xi = (\xi_t)$ with $\xi_T = \varphi(S_T)$ has pricing function
$F_t = f(t, S_t)$. Feynman-Kac (Chapter 4) applied with drift $a(x) = rx$,
diffusion $b(x) = \sigma x$, and discounting $c = r$ yields the
representation

$$
f(t, x) \;=\; \mathbb{E}_{t,x}^{\mathbb{Q}}\!\left[\,e^{-r(T-t)}\,\varphi(X_T)\,\right],
\qquad \mathrm{d}X_s = r\,X_s\,\mathrm{d}s + \sigma\,X_s\,\mathrm{d}\widetilde W_s.
\tag{6.35}
$$

By the Chapter 4 FK theorem, $f(t,x)$ satisfies the PDE

$$
\partial_t f + r\,x\,\partial_x f + \tfrac12\sigma^2 x^2\,\partial_{xx} f \;=\; r\,f, \qquad f(T,x) = \varphi(x).
\tag{6.36}
$$

This is *identical* to (6.27). Two independent derivations — the hedging
argument of §6.5 and the FK martingale argument of Chapter 4 — converge on the
same PDE. That convergence is not a coincidence; both are expressing the
same fact in different languages.

### 6.7A.3 Discounted price as a $\mathbb{Q}$-martingale

The clearest way to see the equivalence is via the discounted price. Let
$Y_t := f(t, X_t)/M_t$. Applying Itô's lemma (Chapter 3) and collecting the
$\mathrm{d}t$ terms gives

$$
\mathrm{d}Y_t \;=\; \frac{1}{M_t}\!\left(\partial_t f + r x\,\partial_x f + \tfrac12\sigma^2 x^2 \partial_{xx} f - r f\right)\!\mathrm{d}t \;+\; \frac{\sigma x \,\partial_x f}{M_t}\,\mathrm{d}\widetilde W_t.
\tag{6.37}
$$

By the Black-Scholes PDE (6.36), the $\mathrm{d}t$ bracket vanishes
identically, leaving only the Brownian piece — i.e. $Y$ is a (local)
martingale. **The PDE is exactly the drift-killer**: $\mathbb{Q}$ is
defined so the bracket equals zero.

The BS PDE is "discounted price is a $\mathbb{Q}$-martingale" in Itô language.

> **Martingale $\;\Leftrightarrow\;$ drift is zero $\;\Leftrightarrow\;$ PDE holds.**

### 6.7A.4 Recovering the call formula from the expectation

Integrate $\mathrm{d}X_s/X_s = r\,\mathrm{d}s + \sigma\,\mathrm{d}\widetilde W_s$ from $X_t = x$:

$$
X_T \;=\; x\cdot\exp\!\Big\{(r - \tfrac12\sigma^2)(T - t) + \sigma(\widetilde W_T - \widetilde W_t)\Big\}. \tag{6.38}
$$

Decompose the call payoff as $(X_T - K)_+ = X_T\,\mathbb{1}_{X_T > K} -
K\,\mathbb{1}_{X_T > K}$. The second piece is the discounted digital
times $K$: from (6.32), $K\,e^{-r(T-t)}\,\Phi(d_-)$. The first piece
— the stock-delivery leg — uses the change-of-numeraire trick of Chapter 5.
Under the stock-numeraire measure $\mathbb{Q}^S$ (with $S_t$ as numeraire
rather than the money account $M_t$), the expectation $\mathbb{E}^{\mathbb{Q}^S}[\mathbb{1}_{X_T >
K}]$ equals $\Phi(d_+)$ with $d_+ = d_- + \sigma\sqrt{T-t}$. Translating
back to the $\mathbb{Q}$-expectation via the Radon-Nikodym density
$\mathrm{d}\mathbb{Q}^S/\mathrm{d}\mathbb{Q} = S_T/(S_t\,e^{r(T-t)})$:

$$
\mathbb{E}_{t,x}^{\mathbb{Q}}\!\left[e^{-r(T-t)}\,X_T\,\mathbb{1}_{X_T > K}\right] \;=\; x\cdot\Phi(d_+). \tag{6.39}
$$

Combining the two pieces recovers (6.28). $\Phi(d_-) = \mathbb{Q}(X_T > K)$ is the risk-neutral exercise probability; $\Phi(d_+) = \mathbb{Q}^S(X_T > K)$ is the same under the stock numeraire — they differ by the Girsanov shift $\sigma\sqrt{T-t}$.

### 6.7A.5 Why two derivations

Hedging foregrounds self-financing, market price of risk, no-arbitrage. Feynman–Kac foregrounds the measure change: the PDE is the drift-killer that defines $\mathbb{Q}$. For Gaussian-integrable payoffs (calls, digitals, log-contracts), the expectation route wins; for low-dimensional non-integrable problems with American or barrier features, the PDE route via finite differences wins.

---

## 6.8 Worked Example 1 — Linear payoff $\varphi(x) = x$ (sanity check)

The claim that pays the stock price at maturity must price at $f(t, x) = x$. PDE check:

$$
\partial_t f = 0,\qquad \partial_x f = 1,\qquad \partial_{xx} f = 0,
$$

so the LHS of (6.27) is $0 + rx\cdot 1 + 0 = rx = r f$. ✓

Delta is 1 — replicate by holding one share, no cash. A useful smoke test for any FD scheme.

**Probabilistic.** Under $\mathbb{Q}$,

$$
X_T \;\overset{d}{=}\; X_t\,e^{(r - \tfrac{1}{2}\sigma^2)(T-t) + \sigma\sqrt{T-t}\,Z},
\qquad Z \sim \mathcal{N}(0,1).
$$

Hence

$$
\text{price} \;=\; \mathbb{E}^{\mathbb{Q}}_t\!\left[e^{-r(T-t)}\,X_T\right]
\;=\; X_t\,\mathbb{E}^{\mathbb{Q}}\!\left[e^{-\tfrac{1}{2}\sigma^2(T-t) + \sigma\sqrt{T-t}\,Z}\right] \;=\; X_t. \tag{6.40}
$$

The bracket is a mean-1 log-normal — Feynman–Kac agrees with the PDE.

---

## 6.9 Worked Example 2 — Separable ansatz $f(t, x) = x^2\,\ell(t)$

The squared payoff $\varphi(x) = x^2$ is a building block of variance swaps and log-contract decompositions, and the simplest non-linear payoff in the Itô world. Ansatz $f(t, x) = x^2 \ell(t)$ with $\ell(T) = 1$:

$$
\partial_t f = x^2\,\dot\ell,\qquad \partial_x f = 2 x \ell,\qquad \partial_{xx} f = 2\ell.
$$

Plug into (6.27):

$$
\underbrace{x^2\dot\ell}_{\partial_t f}
+ \underbrace{rx\cdot 2x\ell}_{rx\,\partial_x f}
+ \underbrace{\tfrac{1}{2}\sigma^2 x^2\cdot 2\ell}_{\tfrac{1}{2}\sigma^2 x^2\,\partial_{xx}f}
\;=\; \underbrace{r\,x^2\ell}_{rf}. \tag{6.41}
$$

Divide by $x^2$:

$$
\dot\ell + (r + \sigma^2)\ell \;=\; 0
\;\Longrightarrow\;
\ell(t) \;=\; e^{(r + \sigma^2)(T - t)}. \tag{6.42}
$$

So

$$
\boxed{\;f(t,x) \;=\; x^2\,e^{(r+\sigma^2)(T-t)}\;}. \tag{6.43}
$$

Volatility shows up additively to the rate in the exponent — variance products are exponential in $\sigma^2$ and so deeply vega-heavy. The ansatz collapses a 2-variable PDE to a 1-variable ODE; this trick works for any power-of-$x$ payoff.

Delta $= 2 x \ell(t)$, gamma $= 2 \ell(t)$ (constant). Constant gamma is the cleanest vehicle for harvesting realised variance — the basis of variance-swap replication via the log-contract decomposition.

Numeric: $r = 5\%$, $\sigma = 20\%$, $T - t = 1$ gives $e^{0.09} \approx 1.094$ — a 9.4% premium over the cash-and-carry square. Shock $\sigma$ to 30% and the premium is 15%.

---

## 6.9A Worked Example 3 — Digital call (closed form + PDE verification)

A digital pays \$1 if $S_T \ge K$. The pricing formula is clean ((6.32)), but the discontinuity makes hedging near expiry pathological — see §6.11.7.

**Payoff and closed form.** Recall

$$
\varphi(x) \;=\; \mathbb{1}_{\,x \,\ge\, K}, \qquad
f(t,x) \;=\; e^{-r(T-t)}\,\Phi\!\big(d_-(t,x)\big), \tag{6.44}
$$

with

$$
d_-(t,x) \;=\; \frac{\ln(x/K) + (r - \tfrac{1}{2}\sigma^2)(T-t)}{\sigma\sqrt{T-t}}. \tag{6.45}
$$

Numeric: $S = K = \$100$, $r = 5\%$, $\sigma = 20\%$, $T - t = 0.5$. Then $d_- = 0.015 / 0.1414 \approx 0.106$, $\Phi(0.106) \approx 0.542$, and the price is $e^{-0.025} \cdot 0.542 \approx 0.529$ — 53 cents per dollar at expiry.

### 6.9A.1 PDE verification

Chain-rule the partials of $\Phi(d_-(t, x))$:

$$
\partial_t f \;=\; e^{-r(T-t)}\,\Phi'(d_-(t,x))\,\partial_t d_-
\;+\; r\,f. \tag{6.46}
$$

Space derivatives:

$$
\partial_x f \;=\; e^{-r(T-t)}\,\Phi'(d_-(t,x))\,\partial_x d_-,
\qquad \partial_x d_- \;=\; \frac{1}{x\,\sigma\sqrt{T-t}}, \tag{6.47}
$$

$$
\partial_{xx} f \;=\; e^{-r(T-t)}\Big\{\Phi''(d_-(t,x))\,(\partial_x d_-)^2 + \Phi'(d_-(t,x))\,\partial_{xx} d_-\Big\}, \tag{6.48}
$$

with

$$
\partial_{xx} d_- \;=\; -\,\frac{1}{x^2\,\sigma\sqrt{T-t}},
\qquad \Phi''(x) \;=\; -\,x\,\Phi'(x),\quad \Phi'(x) \;=\; \frac{e^{-\tfrac{1}{2}x^2}}{\sqrt{2\pi}}. \tag{6.49}
$$

Combining (6.46)-(6.49) in (6.27) verifies the PDE: the $rf$ terms
cancel against $\partial_t f$'s $+rf$ piece, and the drift-plus-diffusion
piece cancels thanks to $\Phi'' = -x\Phi'$. ✓

The identity $\Phi'' = -x\Phi'$ collapses the cross-terms at the right moment.

The digital's delta is $\partial_x f = e^{-r(T-t)} \Phi'(d_-) / (x \sigma \sqrt{T-t})$. Off-strike, $d_- \to \pm\infty$ kills $\Phi'(d_-)$ exponentially as $T - t \to 0$. At-strike, $\Phi'(d_-)$ stays bounded and the delta is dominated by the $1/\sqrt{T-t}$ singularity — "infinite delta at the strike in the last instant" (visualised in §6.11.7).

For $K = \$100$, $\sigma = 20\%$: peak delta is $\approx 0.07$/dollar at 1 month, $\approx 0.4$/dollar at 1 day, $\approx 2$/dollar at 1 hour — untradeable. Digital hedging is a race against the clock.

---

## 6.10 Time-based hedging recursion

Any PDE solution rewrites as a discounted $\mathbb{Q}$-expectation by Feynman–Kac. Replication, PDE, and expectation are three statements of the same no-arbitrage fact. Under $\mathbb{Q}$,

$$
f(t,x) \;=\; \mathbb{E}^{\mathbb{Q}}_{t,x}\!\left[\varphi(X_T)\,e^{-\int_t^T r_u\,\mathrm{d}u}\right], \qquad X_t = x. \tag{6.50}
$$

Under $\mathbb{Q}$ the drift of $X$ is shifted by $-\sigma^x \lambda$ — in BS this collapses to $r X_t$. The physical $\mu$ is entirely absent from the pricing machine. The $\mathbb{Q}$-dynamics:

$$
\mathrm{d}X_t \;=\; \underbrace{\big(\mu^x_t - \sigma^x_t\,\lambda_t\big)}_{\,=\,r_t X_t\text{ in BS}}\,\mathrm{d}t
\;+\; \sigma^x_t\,\mathrm{d}\widetilde W_t, \tag{6.51}
$$

where $\widetilde W_t$ is $\mathbb{Q}$-Brownian. Under $\mathbb{Q}$, every discounted traded price is a martingale — which is why (6.50) works.

The **Fundamental Theorem of Asset Pricing** formalises this connection.
It states that, in a market satisfying mild technical conditions, there
is no arbitrage if and only if there exists at least one equivalent
martingale measure $\mathbb{Q}$ under which all discounted traded prices
are martingales. Furthermore, if the market is complete (as in our
single-Brownian-motion setup), the martingale measure is unique. Self-
financing plus no-arbitrage implies the existence of $\mathbb{Q}$; market
completeness implies uniqueness; and the risk-neutral expectation (6.50)
is what you get when you integrate any payoff against this unique
measure.

### 6.10.1 Specialisation to Black-Scholes

$$
\mathrm{d}X_t \;=\; \mu X_t\,\mathrm{d}t + \sigma X_t\,\mathrm{d}W_t
\;=\; r\,X_t\,\mathrm{d}t + \sigma X_t\,\mathrm{d}\widetilde W_t,\qquad r = \text{const}. \tag{6.52}
$$

The call, put, and digital formulas (6.28), (6.31), and (6.32) all
follow from plugging (6.38) into (6.50) and computing the Gaussian
integrals, as sketched in §6.7A.4. The three formulas are the three
canonical closed forms that every option-pricing library implements.

It is worth writing out what the Greeks mean in units. The delta
$\Phi(d_+)$ is dimensionless — it is the number of shares per option.
The gamma $\phi(d_+)/(x\sigma\sqrt{T-t})$ has units of shares per dollar
of stock, which is to say "how fast the delta changes as the stock
moves". The vega $x\phi(d_+)\sqrt{T-t}$ has units of dollars per unit of
volatility; a typical convention is to quote vega per "vol point" (1%
change in $\sigma$), which gives the dollar sensitivity of the option
to a one-percentage-point move in implied volatility. These three
numbers are the core risk measures of the option position; any serious
trading desk watches them in real time.

The curvature features of the vanilla call are specially illuminating.
The gamma peaks at-the-money because that is where the payoff has its
"kink"; further from the strike, the payoff is either essentially linear
(deep ITM) or essentially zero (deep OTM), and a linear payoff has no
curvature. The gamma also grows as expiry approaches for at-the-money
options, because the remaining convexity has to be concentrated into a
shrinking window. Gamma and vega are cousins — both express the option's
exposure to variance — and they are most pronounced where the payoff is
most non-linear.

---

## 6.11 Discrete hedging of a continuous model

The theoretical result is that continuous rebalancing at every instant
produces *exact* replication — $V_t \equiv 0$, every day, every path. In
real life, we rebalance at some discrete frequency: daily, hourly, once
per tick. The replication therefore has tracking error, and the structure
of that error is what we turn to now. We will see that the dominant
source of error scales like $\sqrt{\Delta t}$ per step, and that — importantly
— this error comes from discretisation of the Brownian motion, not from
any model mismatch. Model mismatch is a separate, more insidious source
of error.

The transition from the continuous-time theory to real-world hedging is
where the rubber meets the road. On paper, continuous rebalancing
produces exact replication; in reality, the fastest any trader can
rebalance is tick-by-tick, and even tick-by-tick is at millisecond
intervals, not truly continuous. The gap between "continuous" and "very
frequently" is not just a quantitative small-error question — it has a
specific structure that shapes how traders set up their rebalancing
workflows.

### 6.11.1 Holdings rule

$$
\alpha_t \;=\; \frac{\sigma^f_t\,f_t}{\sigma^g_t\,g_t}
\;=\; \partial_x f(t,X_t)\qquad \text{if } X_t \text{ is traded.} \tag{6.53}
$$

The stock-hedge ratio is the delta — hence "delta hedging." In practice we hold $\partial_x f$ at the last rebalance and let the position drift. Two error sources: path-dependent (stock moves between rebalances, ideal delta shifts) and calendar-dependent ($\partial_x f$ depends on $t$). Geometrically, between trades the held portfolio is an affine tangent to the curved pricing surface; the curvature gap is the gamma residual.

### 6.11.2 At $t_0 = 0$ — sold $f$, get $f_0$

- Buy $\alpha_0$ units of $X$ (costs $\alpha_0 X_0$).
- Bank: $M_0 = f_0 - \alpha_0 X_0$.

Numerical: 3-month ATM call on \$100 stock, 25% vol, 5% rate. Premium $\approx \$5.60$, delta $\approx 0.55$. Buy 0.55 shares for \$55, bank starts at $-\$49.40$ — short calls require borrowing to fund the hedge.

### 6.11.3 At $t_1$

Bank grew at interest, then we rebalance to the new delta:

$$
M_{t_1} \;=\; M_0\,e^{r\,\Delta t} \;-\; (\alpha_{t_1} - \alpha_{t_0})\,X_{t_1}. \tag{6.54}
$$

The rebalance price is the current $X_{t_1}$, not the old one — that is what self-financing enforces vs the naive product rule.

### 6.11.4 At $t_2$

$$
M_{t_2} \;=\; M_{t_1}\,e^{r\,\Delta t} \;-\; (\alpha_{t_2} - \alpha_{t_1})\,X_{t_2}. \tag{6.55}
$$

### 6.11.5 Repeat

$$
\boxed{\;M_{t_n} \;=\; M_{t_{n-1}}\,e^{r\,\Delta t} \;-\; (\alpha_{t_n} - \alpha_{t_{n-1}})\,X_{t_n}\;} \tag{6.56}
$$

No rebalancing between $t_0, t_1, \dots, t_N = T$.

With per-trade transaction cost $\kappa(q)$ on $q$ shares,

$$
M_k \;=\; M_{k-1}\,e^{r\,\Delta t_k} \;-\; (\alpha_k - \alpha_{k-1})\,S_k \;-\; \kappa\!\big(\alpha_k - \alpha_{k-1}\big), \tag{6.57}
$$

and $\sum_k \kappa(\Delta\alpha_k)$ is the slippage bill that turns rebalancing into a genuine optimisation rather than "rebalance as often as possible."

### 6.11.6 Terminal P&L

At $t_N$ we owe the option payoff:

$$
\boxed{\;\mathrm{PnL} \;=\; \Big(M_{t_{N-1}}\,e^{r\,\Delta t} \;+\; \alpha_{t_{N-1}}\,X_{t_N}\Big) \;-\; \varphi(X_{t_N})\;} \tag{6.58}
$$

Exact replication would give PnL $\equiv 0$. In reality, two distinct error sources contribute.

**Discretisation error** ($\sqrt{\Delta t}$ scaling, vanishes as $\Delta t \to 0$). On each step the residual mismatch between the held constant-$\alpha$ position and the ideal-$\partial_x f$ position is $\tfrac12\,\Gamma\,X^2\,\sigma^2\,(Z^2 - 1)\,\Delta t$, with $Z \sim \mathcal N(0,1)$. Summing $N$ independent residuals gives a total standard deviation $\sim \Gamma\,S^2\,\sigma^2\,\sqrt{T\,\Delta t}$. Doubling the rebalance frequency cuts the std-dev by $\sqrt 2$, not by 2.

**Model error** (does *not* shrink with finer rebalancing). If the hedger uses $\sigma_{\text{imp}}$ to compute the delta but the market realises $\sigma_{\text{real}}$, every interval contributes the **gamma · realised-vs-implied identity**

$$
\text{P\&L}_{[t, t+\Delta t]} \;\approx\; \tfrac12\,\Gamma_t\,X_t^2\,\bigl(\sigma_{\text{imp}}^2 - (\Delta X_t / X_t)^2 / \Delta t\bigr)\,\Delta t.
$$

The integral over the option's life is the running gamma-times-vol-mismatch P&L of a delta-hedged short option — a long-gamma position earns money when realised exceeds implied, a short-gamma position loses. A delta-hedged option *is* a variance swap in a convex wrapper. Model error is curable only by trading other options (vega), not by trading more.

**Jump risk** lives outside the Brownian framework: an unhedged jump of size $J$ in the underlying produces a P&L of $f(t, X + J) - f(t, X) - \partial_x f \cdot J$ — second-order surprise (positive for long gamma, unbounded for short gamma). Rebalancing faster cannot help; only option-vs-option hedges can. This jump risk explains the crash-o-phobia skew in equity-index OTM puts.

![Discrete-hedging error vs rebalance frequency](figures/ch06-hedge-error.png)
*Discrete-hedging error vs rebalance frequency.*

![Replicating portfolio value paths](figures/ch06-replicating-path.png)
*Ideal continuous hedging would pin $V_t \equiv 0$; daily rebalancing leaves visible gamma-driven wiggles.*

### 6.11.7 Shape of $\alpha_t$ near expiry — digital call

Near $t = T$, the digital-call delta $\alpha = \partial_x f$ spikes
around the strike $K$. A useful way to watch this evolve is to plot the
delta as a function of spot for three representative time slices:

\begin{figure}[H]
\centering
\begin{tikzpicture}[>=Stealth,scale=1.0]
  \draw[->] (-0.2,0) -- (8.5,0) node[right] {$x$ (spot)};
  \draw[->] (0,-0.2) -- (0,3.4) node[above] {$\alpha(x,t)$};
  \draw[dashed,gray] (0,2.6) -- (8.3,2.6) node[right] {\small $1$};
  \draw[dashed,gray] (4,0) -- (4,3.0); \node[below] at (4,0) {\small $K$};
  % t << T : broad logistic
  \draw[thick,blue] plot[domain=0.3:8,smooth,samples=80] (\x,{2.6/(1+exp(-0.6*(\x-4)))});
  % t ~ T : tight sigmoid
  \draw[thick,orange] plot[domain=0.3:8,smooth,samples=120] (\x,{2.6/(1+exp(-2.2*(\x-4)))});
  % t = T : step
  \draw[thick,red] (0.3,0) -- (4,0);
  \draw[thick,red,dashed] (4,0) -- (4,2.6);
  \draw[thick,red] (4,2.6) -- (8,2.6);
  % labels
  \node[blue,anchor=west,font=\footnotesize] at (6.2,1.6) {$t \ll T$ (broad)};
  \node[orange,anchor=west,font=\footnotesize] at (5.0,2.25) {$t \sim T$ (sharp)};
  \node[red,anchor=west,font=\footnotesize] at (4.3,2.85) {$t = T$ (step)};
\end{tikzpicture}

\textit{As $t \to T^-$ the digital-call delta sharpens from a broad logistic into a step at $K$; gamma is the spatial derivative, so it blows up into a Dirac spike at expiry.}
\end{figure}

- **$t \ll T$ (far from expiry):** the delta is a broad, logistic-looking
  curve rising gently from near $0$ on the far left through roughly
  $\tfrac12$ at $x = K$ to near $1$ on the far right. Gamma is modest
  and the hedge is easy to track.
- **$t \sim T$ (close to expiry):** the logistic tightens into a sharp
  S-curve concentrated near $K$. Gamma grows large in a narrow band;
  outside the band the delta is essentially $0$ or $1$.
- **$t = T$ (at expiry):** the delta jumps from $0$ to $1$ at $K$ — a
  step function — and its derivative (gamma) is a Dirac $\delta$-spike.

As $t \to T^-$ the delta becomes a Dirac at $K$ — hedging digitals near expiry is impossible without discontinuous trades ("delta blow-up"). Standard remedy: replace the digital by a tight call spread (long $K - \epsilon/2$, short $K + \epsilon/2$, scaled by $1/\epsilon$). The spread's delta is bounded by $1/\epsilon$; tighter $\epsilon$ means closer to a digital but harder to hedge.

![Delta surface](figures/ch06-delta-surface.png)
*Left: smooth vanilla delta. Right: digital delta tents at $K$ as
$\tau\to 0$ — the hedger must trade arbitrarily large size around the
strike.*

---

## 6.12 Move-based hedging

Time-based hedging rebalances on the clock; **move-based hedging** rebalances only when the held delta drifts outside a band around the last-hedged value. The trader cares about *delta error*, not elapsed time.

- Set a band $[\alpha^\star - \epsilon,\ \alpha^\star + \epsilon]$.
- Let $\alpha_t$ drift inside the band.
- When $\alpha_t$ exits, re-centre: new $\alpha^\star = \alpha_t$,
  restart.

\begin{figure}[H]
\centering
\begin{tikzpicture}[>=Stealth,scale=1.0]
  \draw[->] (-0.2,0) -- (10,0) node[right] {$t$};
  \draw[->] (0,-0.2) -- (0,4.5) node[above] {$\alpha_t$};
  % band 1
  \draw[dashed,gray] (0.3,2.0) rectangle (3.3,3.4);
  \node[gray,font=\footnotesize] at (1.8,3.7) {band 1 ($\alpha^\star_1$)};
  % band 2 (lower, re-centred after upward exit)
  \draw[dashed,gray] (3.3,1.4) rectangle (6.3,2.8);
  \node[gray,font=\footnotesize] at (4.8,3.1) {band 2 ($\alpha^\star_2$)};
  % band 3 (lower again)
  \draw[dashed,gray] (6.3,0.6) rectangle (9.5,2.0);
  \node[gray,font=\footnotesize] at (7.9,2.3) {band 3 ($\alpha^\star_3$)};
  % delta trajectory
  \draw[thick,blue] plot[domain=0.3:3.3,smooth,samples=40] (\x,{2.7+0.5*sin(2*\x r)});
  \draw[thick,blue] plot[domain=3.3:6.3,smooth,samples=40] (\x,{2.1+0.5*sin(2*\x r+1)});
  \draw[thick,blue] plot[domain=6.3:9.5,smooth,samples=40] (\x,{1.3+0.5*sin(2*\x r+2)});
  % exit markers
  \fill[red] (3.3,3.2) circle (2pt) node[above right,font=\scriptsize,red] {exit $\uparrow$};
  \fill[red] (6.3,1.6) circle (2pt) node[above right,font=\scriptsize,red] {exit $\downarrow$};
\end{tikzpicture}

\textit{The delta drifts inside a band of width $2\epsilon$ around the last-hedged value $\alpha^\star$. On exit, a single trade snaps the position to the current $\alpha_t$, and a fresh band re-centres.}
\end{figure}

Move-based trades fewer times than time-based for the same tracking error on smooth paths, but pays up on rapid gamma swings. The fundamental dial: expected number of trades scales as $1/\epsilon^2$ (Brownian local-time result), tracking error scales linearly in $\epsilon$ — quadratically fewer trades for a linear increase in noise.

A short ATM 3-month call under GBM, 10 bps/share transaction cost, varying band $\epsilon$:

| Band $\epsilon$ | Mean P&L | P&L std |
|---|---|---|
| 0.00625 | -0.39 | 0.705 |
| 0.0125  | -0.35 | 0.710 |
| 0.025   | -0.34 | 0.750 |
| 0.05    | -0.34 | 0.850 |
| 0.10    | -0.32 | 1.290 |
| 0.20    | -0.33 | 2.190 |

Wider bands raise mean P&L (less commission bleed) but inflate std-dev (delta wanders further). The frontier "commission + variance" $\sim a/\epsilon^2 + b\epsilon^2$ has a clean minimum.

Operationally, layer move-based triggers on a clock baseline and hard-code rebalances around known events (open, close, earnings, central-bank meetings) — these are when path continuity breaks. Production systems typically use **delta-dollars** ($\Delta \cdot S$) bands rather than pure delta bands, so limits are comparable across underlyings of different price levels and feed cleanly into the desk's risk-limit
system. Beyond delta-dollars bands, more sophisticated desks layer
**gamma-adjusted** bands — the idea being that a position with high gamma
needs to be rebalanced more often because its delta moves more per unit
of stock move.

In a world with zero transaction costs, continuous rebalancing is
trivially optimal. In a world with finite transaction costs, neither
time-based nor move-based is universally optimal. The modern derivatives
desk uses a hybrid approach, running time-based rebalancing as a
baseline safety net and move-based overlays where they add value. The
chapter's discussion of continuous dynamic hedging is the theoretical
idealisation these practical schemes are trying to approximate.

---

### Case study (a): Black Monday 1987 — portfolio insurance and the dynamic hedge cascade

*Synthetic puts replicated by selling futures into a falling market.*
*The continuous-hedge ideal collided with discrete fills and a 22% gap.*
*The cohort-level short gamma was the systemic short option no one had marked.*

**Context.** Through 1986–87, roughly $60–90 billion of US institutional
equity was running "portfolio insurance" — a strategy popularised by
Leland-O'Brien-Rubinstein Associates (LOR) and Wells Fargo Wilshire
Investment Management. Mechanically the product was a synthetic
protective put: instead of buying listed SPX puts at their (rich) implied
vol, the manager dynamically replicated the put payoff by holding
equities and dynamically shorting S&P 500 futures in proportion to the
put's delta. As the index fell, the put's delta moved toward $-1$, and
the strategy mechanically sold *more* futures to maintain the hedge. The
selling was supposed to be smooth — small adjustments against an
assumed-continuous price path — and benign in normal conditions.

On Friday 16 October 1987 the S&P 500 closed down 5.16%, and Monday's
open was already gapping. Through 19 October, the cash index fell from
282.70 to 224.84 (down 20.5% close-to-close, with intraday lows touching
−22.6%). Portfolio-insurance programs trying to hedge against a 5%
move had to reprice deltas against a 20% move, and the resulting sell
program in the futures pit was estimated at $14B notional in S&P 500 and
MMI futures over Monday — into a market where market makers were on
strike, the NYSE specialists could not open dozens of names, and
futures-cash basis blew out to a 20-handle premium then a 60-handle
discount. The Brady Commission's Report (January 1988) named portfolio
insurance and index arbitrage as the two mechanically-amplifying flows.

**Through the chapter's math.** Three failure modes of the
Black-Scholes hedge framework lined up. (i) The hedge ratio
$\alpha_t = \partial_x f(t, X_t)$ from §6.3 is *continuous* in $S$, but
fills are discrete: when $S$ gaps from 282 to 225 with no quotes
in between, you cannot trade the intermediate deltas — you go straight
to the post-gap delta and book the path-dependent gamma loss in one
print. (ii) The local Itô expansion (6.6) reads
$\mathrm dV_t \approx \alpha_t\,\mathrm dS_t + \tfrac12 \Gamma_t (\mathrm dS_t)^2$
under the assumption $(\mathrm dS_t)^2 = \sigma^2 S_t^2\,\mathrm dt$;
when the realised $(\Delta S)^2 / S^2$ is on the order of 0.05 instead
of $\sigma^2 \cdot \Delta t \approx 0.0001$, the discrete-hedging error
of §6.11.6 is two orders of magnitude past its $\sqrt{\Delta t}$ scaling
estimate. (iii) Each LOR client's program was independently short gamma
to its hedger — but at the *cohort* level the entire $80B of insurance
flow was net short gamma against the same index, and that aggregate
gamma exposure had no second-leg hedger because the synthetic-put issuer
was the market itself. The market's effective short-gamma position
showed up as a price impact term that the dynamic hedge had to chase.

**Lesson.** The "synthetic put" was synthetic until it wasn't. The
chapter's continuous-time replication argument in §6.2–6.3 promises
a perfect hedge under (a) frictionless markets, (b) continuous price
paths, and (c) an outside-counterparty buyer for whatever delta the
hedger needs to trade. October 1987 violated all three at once. The
modern legacy of 1987 is structural: SPX listed put open interest is
materially higher than its 1980s level (insurers buy listed puts now
rather than synthesise them), exchange circuit breakers institutionalise
the gap-discontinuity acknowledgement, and any desk running synthetic
optionality calculates a "if the market gapped 10% before I could
rebalance" stress P&L as a regulatory risk metric. The Brady-Commission
view — that any hedging strategy whose required trades scale with
realised moves can become destabilising at scale — is now baked into
SEC Rule 15c3-5 (market access) and the post-crisis trade-through
controls. Portfolio insurance the product still exists, but is sized
to remain a price-taker, not a price-maker.

---

### Case study (b): GameStop January 2021 — gamma squeeze as forced delta-hedge

*Retail call buying forces market makers into mechanical buying.*
*Positive gamma on the MM short means $\delta' = \Gamma > 0$ in $S$.*
*The "gamma squeeze" headline is just (6.6) read out loud.*

**Context.** Through January 2021, retail call-option buying on GameStop
(GME) intensified through the WallStreetBets community on Reddit. Daily
GME call volume on weekly and front-month expiries reached six- to
ten-times historical norms; on 22 January, GME call open interest
exceeded the entire free-float share count. Market makers — predominantly
Citadel Securities, Susquehanna, Wolverine, and Group One on the option
side — fill these option orders by selling calls and dynamically delta-
hedging the resulting short. The implied vol the MM charged was high
(IV on GME 30-day options jumped from ~80% to over 400% in that two-week
window), but the dynamic-hedge mechanics were exactly what §6.3 describes:
sell call → short delta → buy stock to be flat.

The GME spot ran from $19.94 (4 Jan close) to $325.00 (29 Jan close), a
16× move in twenty trading days, with intraday peaks at $483 on 28
January. Each new call buyer added incremental short-gamma exposure to
the MM book, the MM bought more stock to re-flatten delta, that buying
contributed to the very price rise that pushed the next strike's delta
into the hedger's must-buy zone. Retail brokers (notably Robinhood) at
the peak suspended buy-side orders in GME on 28 January citing
clearinghouse margin requirements, snapping the feedback loop.

**Through the chapter's math.** The market-maker's hedged book is
$V^{\text{MM}}_t = -C(t, S_t) + \alpha_t S_t + \beta_t M_t$ with
$\alpha_t = \partial_S C$ — the call's delta. Itô on $C$ gives
$\mathrm dC = \partial_t C\,\mathrm dt + \partial_S C\,\mathrm dS_t + \tfrac12 \partial_{SS} C \cdot \sigma^2 S_t^2\,\mathrm dt$,
so the MM's short-call $\Gamma$ exposure is
$-\partial_{SS} C = -\Gamma_t < 0$ (short gamma). The required delta
adjustment per move in $S$ is $\mathrm d\alpha_t = \Gamma_t\,\mathrm dS_t$:
$S$ goes up by $\Delta S$, the MM must *buy* $\Gamma_t \cdot \Delta S$
extra shares to remain delta-neutral. With aggregate dealer dollar-gamma
on GME estimated at $200–400M per percentage-point move at the peak, a
1% spot move forced ~$3M in mechanical buying *from the hedge alone*,
on top of underlying retail order flow. The dollar-gamma metric
($\$\Gamma = \Gamma_t \cdot S_t^2 \cdot 0.01$) — the dealer's mechanical
buy/sell pressure per 1% move — is the single number that diagnoses
this dynamic, and is the version of §6.3 that risk managers now publish
on positioning dashboards alongside the SPX itself.

**Lesson.** The "gamma squeeze" is not a market-microstructure exotic
or a coordinated retail attack — it is the §6.3 hedge ratio applied at
scale to a name with thin float and concentrated short-gamma dealer
positioning. The right diagnostic is dollar-gamma at the underlying
level, aggregated across all listed strikes weighted by open interest;
when dollar-gamma exceeds a meaningful fraction of average daily volume,
the dealer hedge becomes price-impacting and the underlying becomes
gamma-driven rather than fundamental-driven. Post-GME, every prime
broker's risk team publishes dealer-positioning estimates by name; SEC
Staff Report on Equity and Options Market Structure Conditions in Early
2021 (October 2021) documents the mechanism in detail and uses exactly
this language. The deeper lesson for the dynamic-hedging chapter:
$\Gamma > 0$ for the long-call holder is what makes the convexity of
options valuable; the same $\Gamma$ on the MM's short side, multiplied
by enough notional, becomes a market-moving exogenous demand curve.

---

### Case study (c): Volmageddon February 5 2018 — XIV liquidation via short-vol gamma

*Short-vol products are short vol-of-vol — a hidden second-order risk.*
*Discrete vega rebalancing fails when the vol regime changes intraday.*
*The hedging-error variance scales with $\sqrt{\Delta t}$ until it doesn't.*

**Context.** Credit Suisse's VelocityShares Daily Inverse VIX Short-Term
ETN (ticker XIV, $1.9B AUM into 5 Feb 2018) and the structurally
related ProShares Short VIX Short-Term Futures ETF (SVXY, $0.8B AUM)
delivered the inverse of the daily return of the S&P 500 VIX Short-Term
Futures Index — i.e., a daily reset short-front-VIX-futures position.
Through 2017 the VIX averaged 11.1 (the lowest annual mean since the
index began in 1990), and XIV had returned over 180% YTD by end-January
2018. The product was popular with risk-parity and yield-pickup
allocators precisely because its drawdowns had been mild for half a
decade.

On Friday 2 February 2018, the SPX closed −2.1% and the VIX closed at
17.16 (up from 13.47). On Monday 5 February the SPX dropped a further
4.10%; the VIX intraday spiked from 17 to 50, with the close at 37.32.
The XIV NAV calculation on the issuer's terms triggered an "acceleration
event" — a same-day liquidation provision tripped when the index lost
more than 80% intraday — and Credit Suisse called the note for
redemption. XIV closed Monday at $7.35, down from $115.55 (down 96.3%),
and was wound down weeks later. The operative dynamic was that the
issuers running short-vol replication books were short VIX futures
delta and short vol-of-vol; as VIX rose, they had to *buy* VIX futures
to maintain the short-vega hedge, and the buying happened in the most
illiquid window of the day (the post-3:30 PM ET VIX-future settlement
print), accelerating the spike.

**Through the chapter's math.** A short-vol position has a P&L of the
form $V_t = -F(\sigma_t)$ where $\sigma_t$ is the relevant vol process
and $F$ is the structure's payoff in vol. The first-order risk is
short-vega: $\partial V/\partial \sigma < 0$. The second-order risk
(volga, $\partial^2 V/\partial \sigma^2$) is what blows up in a vol
regime change — Heston (Chapter 10) parameterises this through the
vol-of-vol parameter $\xi$, and the volga exposure is large precisely
when $\xi$ is large. The discrete-hedging error of §6.11.6, repeated for
the vega leg, gives a tracking error of order $\xi\sqrt{\Delta t}$ per
rebalance interval under stable-regime conditions; the issue is that
when $\xi$ itself jumps (vol-of-vol on VIX rose from ~80% on 2 Feb to
over 250% on 5 Feb implied), the hedge error scales with the new
$\xi^{\text{new}}$ but the hedge ratio is set against $\xi^{\text{old}}$
— the once-a-day vega rebalance bookmarks a vega number that is wrong
within minutes of the next print. The XIV NAV, mechanically defined as
the daily-reset inverse-return, was effectively a margin-style stop that
guaranteed forced covering at the worst possible vol-of-vol level.

**Lesson.** A short-vega book that prices and hedges as if vega is a
constant is, in Heston language, ignoring volga. The §6.11 discrete
hedging analysis told us that BS hedge errors scale with $\sqrt{\Delta t}$
under the *model's own assumption* that $\sigma$ is constant; the
moment $\sigma$ becomes stochastic with non-trivial vol-of-vol, that
$\sqrt{\Delta t}$ scaling is replaced by something proportional to the
realised $\xi$, which can be ten times the calibrated $\xi$ in a regime
change. The lesson is operational and structural: any short-convexity
book must (i) set a hard limit on vega-by-vol-bucket so a single regime
change cannot eat the desk, (ii) hedge volga explicitly via long
out-of-the-money options on the vol underlying, not just vega via
ATM, and (iii) treat the once-a-day rebalance as inadequate for short-
vol books in stressed vol regimes — XIV-style products that mechanically
rebalance once per day at the close are *guaranteed* to underperform a
continuously-hedged equivalent in a vol blow-out, by exactly the
square-root-of-time argument the chapter develops, applied to the
wrong $\xi$. The post-2018 short-vol ETP space halved in AUM and
restructured into products with intraday rebalancing or capped daily
loss; the underlying mathematics was a textbook §6.11 hedging-error
cascade applied to the wrong-order Greek.

---

## 6.13 Key Takeaways

1. **Self-financing constraint.** A portfolio $(\alpha_t, \beta_t)$ in the underlying and bank account is self-financing iff $\mathrm dV_t = \alpha_t\,\mathrm d g_t + \beta_t\,\mathrm d M_t$ with *no* fresh injection of cash. Naïve differentiation would add a $g_t\,\mathrm d\alpha_t + M_t\,\mathrm d\beta_t$ term that has no economic meaning; the missing term is what arbitrage-free pricing forbids.

2. **Delta is $\partial_x f$.** Locally cancelling the Brownian increment in the hedged portfolio forces $\alpha_t = \partial_x f(t, X_t)$ — the hedge ratio is the slope of the pricing function with respect to the underlying, evaluated at the current state. No optimisation is required; it falls out of "set the $\mathrm dW$ coefficient to zero."

3. **Market price of risk = Girsanov shift.** Equating Sharpe ratios across two tradables driven by the same Brownian gives $\lambda = (\mu^f - r)/\sigma^f = (\mu^g - r)/\sigma^g$, the **market price of risk** — universal across hedgeable assets by no-arbitrage. Read through Chapter 5, $\lambda$ is the integrand of the Radon-Nikodym density that takes $\mathbb{P}$ to $\mathbb{Q}$.

4. **Generalised BS PDE (6.24).** For an underlying $\mathrm dX_t = \mu^x\,\mathrm dt + \sigma^x\,\mathrm dW_t$ with state-dependent coefficients, the option price $f(t, x)$ satisfies $\partial_t f + (\mu^x - \sigma^x \lambda)\,\partial_x f + \tfrac12 (\sigma^x)^2\,\partial_{xx} f = r\,f$ with terminal data $f(T, x) = \varphi(x)$. The physical drift $\mu^x$ enters only through the combination $\mu^x - \sigma^x \lambda$.

5. **GBM specialisation (6.27)** and **call formula (6.28).** For GBM $\mathrm dX_t = \mu X_t\,\mathrm dt + \sigma X_t\,\mathrm dW_t$, the PDE collapses to $\partial_t f + r x \partial_x f + \tfrac12 \sigma^2 x^2 \partial_{xx} f = r f$. The European call solution is $f(t, x) = x\,\Phi(d_+) - K e^{-r(T - t)}\,\Phi(d_-)$ with $d_\pm = [\ln(x/K) + (r \pm \tfrac12 \sigma^2)(T - t)]/(\sigma\sqrt{T-t})$. The physical drift $\mu$ is absent — option prices do not depend on the underlying's expected return.

6. **Closed-form vanilla Greeks.** $\Delta^C = \Phi(d_+) \in (0, 1)$, $\Gamma^C = \phi(d_+)/(x\sigma\sqrt{T-t})$, vega $\mathcal{V}^C = x\,\phi(d_+)\,\sqrt{T-t}$. Put-call parity gives $\Delta^P = \Delta^C - 1$, $\Gamma^P = \Gamma^C$, $\mathcal{V}^P = \mathcal{V}^C$.

7. **PDE ⇔ Q-expectation via Feynman-Kac.** The same PDE (6.27) is the Feynman-Kac PDE for the discounted $\mathbb{Q}$-expectation $f(t, x) = \mathbb{E}^{\mathbb{Q}}_{t, x}[e^{-r(T - t)}\,\varphi(X_T)]$, where under $\mathbb{Q}$ the drift of $X$ is shifted from $\mu$ to $r$. Replication, PDE, and risk-neutral expectation are three equivalent statements of the same no-arbitrage fact.

8. **Risk-neutral drift = Girsanov-shifted physical drift.** $\mathrm dX_t = \mu X_t\,\mathrm dt + \sigma X_t\,\mathrm dW_t = r X_t\,\mathrm dt + \sigma X_t\,\mathrm d\widetilde W_t$ with $\widetilde W_t = W_t + \lambda t$ (Eq. 6.51-6.52). The bank-account-deflated price $e^{-rt}\,X_t$ is a $\mathbb{Q}$-martingale, as is $e^{-rt}\,f_t$.

9. **Discrete-hedging recursion (6.56) and $\sqrt{\Delta t}$ tracking error.** With holdings $\alpha_t = \partial_x f$ rebalanced on a grid $\{t_0, \ldots, t_N\}$, the bank balance evolves as $M_{t_n} = M_{t_{n-1}}\,e^{r\,\Delta t} - (\alpha_{t_n} - \alpha_{t_{n-1}})\,X_{t_n}$. Terminal P&L (Eq. 6.58) has mean zero under correct model specification; its standard deviation scales as $\sqrt{\Delta t}$ — doubling rebalance frequency cuts hedging error by $\sqrt 2$, not 2.

10. **Gamma · (realised − implied) P&L identity.** The leading-order single-step P&L from a mis-specified implied volatility is $\tfrac12\,\Gamma\,S^2\,(\sigma_{\text{realised}}^2 - \sigma_{\text{implied}}^2)\,\Delta t$. A long-gamma position earns money when realised variance exceeds the implied number priced into the option; a short-gamma position bleeds the variance risk premium. Every variance-swap and gamma-trading strategy in the guide reduces to this identity.

11. **Digital Greeks blow up like $1/\sqrt{T-t}$.** At-the-money on expiration day, the digital call's delta $e^{-r(T-t)}\phi(d_-)/(x\sigma\sqrt{T-t})$ diverges as $T - t \to 0$ because $\phi(d_-) \to \phi(0) = 1/\sqrt{2\pi}$ stays bounded while $\sqrt{T-t} \to 0$. This is the **pin-risk** phenomenon and is the reason desks tame digital exposures with call-spread replication.

12. **Move-based vs time-based hedging trade-off.** Time-based rebalancing has $\sqrt{\Delta t}$ error and predictable transaction-cost frequency; move-based ("rebalance when $|\Delta(t, S) - \alpha_t| > $ band") concentrates rebalances around the at-the-money region where gamma is large. With finite transaction costs neither is universally optimal; production desks hybridise — time-based safety net plus move-based overlay, both quoted in **delta-dollars** so positions compare across underlyings.

13. **The hedger's price is drift-free.** Two stocks with the same $\sigma$ but different physical drifts $\mu$ have identical call prices. The hedger replicates payoffs state-by-state; the cost depends on how hard the replication machine has to work, which scales with vol, not drift.

14. **Implied volatility is forecast volatility (under $\mathbb{Q}$).** A 20% ATM implied vol is the market's unbiased estimate of the root-mean-square log-return over the option's life *under the risk-neutral measure*. Under $\mathbb{P}$ it can be a touch lower because $\mathbb{Q}$ overweights downside; for liquid equity options the gap is small.

---

## 6.14 Reference Formulas Appendix

### 6.14.1 Setup and SDE coefficients

| Quantity | Symbol / formula |
|---|---|
| Underlying SDE (general) | $\mathrm dX_t = \mu^x(t, X_t)\,\mathrm dt + \sigma^x(t, X_t)\,\mathrm dW_t$ |
| Underlying SDE (GBM specialisation) | $\mathrm dS_t/S_t = \mu\,\mathrm dt + \sigma\,\mathrm dW_t$ |
| Bank account | $\mathrm dM_t/M_t = r_t\,\mathrm dt$, $M_0 = 1$ |
| Self-financing portfolio | $V_t = \alpha_t g_t + \beta_t M_t$, $\mathrm dV_t = \alpha_t\,\mathrm dg_t + \beta_t\,\mathrm dM_t$ |
| Delta-hedge ratio | $\alpha_t = \partial_x f(t, X_t)$ |
| Market price of risk | $\lambda(t, x) = (\mu^f - r)/\sigma^f = (\mu^g - r)/\sigma^g = (\mu^x - r x \cdot \mathbb{1}_{\text{tradable } X})/\sigma^x$ |
| $\mathbb{Q}$-dynamics (Girsanov-shifted) | $\mathrm dX_t = (\mu^x - \sigma^x \lambda)\,\mathrm dt + \sigma^x\,\mathrm d\widetilde W_t$, $\widetilde W_t = W_t + \int_0^t \lambda\,\mathrm du$ |

### 6.14.2 BS PDE — three equivalent forms

| Form | Equation | Eq. |
|---|---|---|
| Generalised BS PDE | $\partial_t f + (\mu^x - \sigma^x \lambda)\,\partial_x f + \tfrac12 (\sigma^x)^2\,\partial_{xx} f = r f$, $f(T, x) = \varphi(x)$ | $(6.24)$ |
| GBM specialisation | $\partial_t f + r x\,\partial_x f + \tfrac12 \sigma^2 x^2\,\partial_{xx} f = r f$, $f(T, x) = \varphi(x)$ | $(6.27)$ |
| $\mathbb{Q}$-expectation (Feynman-Kac) | $f(t, x) = \mathbb{E}^{\mathbb{Q}}_{t, x}[e^{-r(T-t)}\,\varphi(X_T)]$, $\mathrm dX_s = r X_s\,\mathrm ds + \sigma X_s\,\mathrm d\widetilde W_s$ | $(6.50)$ |

### 6.14.3 Closed-form vanilla Greeks ($d_\pm = [\ln(x/K) + (r \pm \tfrac12 \sigma^2)(T-t)]/(\sigma\sqrt{T-t})$)

| Contract | Price | Delta | Gamma | Vega |
|---|---|---|---|---|
| Call $\varphi(x) = (x - K)^+$ | $x\,\Phi(d_+) - K e^{-r(T-t)}\,\Phi(d_-)$ | $\Phi(d_+)$ | $\dfrac{\phi(d_+)}{x\sigma\sqrt{T-t}}$ | $x\,\phi(d_+)\sqrt{T-t}$ |
| Put $\varphi(x) = (K - x)^+$ | $K e^{-r(T-t)}\,\Phi(-d_-) - x\,\Phi(-d_+)$ | $\Phi(d_+) - 1$ | $\dfrac{\phi(d_+)}{x\sigma\sqrt{T-t}}$ | $x\,\phi(d_+)\sqrt{T-t}$ |
| Digital call $\varphi = \mathbf{1}_{\{x > K\}}$ | $e^{-r(T-t)}\,\Phi(d_-)$ | $e^{-r(T-t)}\dfrac{\phi(d_-)}{x\sigma\sqrt{T-t}}$ | $-e^{-r(T-t)}\dfrac{d_+\,\phi(d_-)}{x^2\sigma^2(T-t)}$ | $-e^{-r(T-t)}\dfrac{d_+\,\phi(d_-)}{\sigma}$ |

Strike-shifting identity: $x\,\phi(d_+) = K e^{-r(T-t)}\,\phi(d_-)$. Put-call parity: $C_t - P_t = x - K e^{-r(T-t)}$, hence $\Delta^P = \Delta^C - 1$, $\Gamma^P = \Gamma^C$, $\mathcal V^P = \mathcal V^C$. Pin-risk fingerprint: digital delta $\sim 1/\sqrt{T-t}$ as $t \to T$ at $x = K$.

### 6.14.4 Discrete hedging — recursion and $\sqrt{\Delta t}$ scaling

| Quantity | Formula | Eq. |
|---|---|---|
| Bank-balance recursion | $M_{t_n} = M_{t_{n-1}}\,e^{r\,\Delta t} - (\alpha_{t_n} - \alpha_{t_{n-1}})\,X_{t_n}$ | $(6.56)$ |
| With transaction cost $\kappa$ | $M_k = M_{k-1}\,e^{r\,\Delta t_k} - (\alpha_k - \alpha_{k-1})\,S_k - \kappa(\alpha_k - \alpha_{k-1})$ | $(6.57)$ |
| Terminal P&L (no costs) | $\mathrm{PnL} = (M_{t_{N-1}}\,e^{r\,\Delta t} + \alpha_{t_{N-1}}\,X_{t_N}) - \varphi(X_{t_N})$ | $(6.58)$ |
| Per-step P&L residual | $\tfrac12\,\Gamma\,S^2\,\sigma^2\,(Z^2 - 1)\,\Delta t$, $Z \sim \mathcal N(0, 1)$ |  |
| Tracking-error std-dev scaling | $\mathrm{std}(\mathrm{PnL}) \sim \Gamma\,S^2\,\sigma^2\,\sqrt{T\,\Delta t}$ |  |
| Gamma · realised-vs-implied identity | $\Delta\Pi \approx \tfrac12\,\Gamma\,S^2\,(\sigma_{\mathrm{realised}}^2 - \sigma_{\mathrm{implied}}^2)\,\Delta t$ |  |
