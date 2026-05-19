# Chapter 1 — The Single-Period Binomial Model

## How to read this chapter

This chapter builds the entire machinery of arbitrage-free option pricing on a model so small you can verify every number with a pocket calculator: one date today, one date tomorrow, one coin toss in between. Everything you will meet later — multi-period trees, risk-neutral measures, dynamic hedging, even Black–Scholes — is a *repeated application of what we do here*. So we will do it slowly, with two recurring numerical worlds:

- **Toy** — $S_0=4$, up factor $u=2$, down factor $d=\tfrac{1}{2}$, one-period interest rate $r=\tfrac{1}{4}$, risk-neutral probability $\tilde p=\tfrac{1}{2}$. Every arithmetic step is hand-verifiable.
- **Realistic (RL)** — $S_0=100$, $u=1.10$, $d=0.90$, $r=0.02$, $\tilde p=0.60$. These numbers feel like a real stock and a real money-market rate. They will also produce the moments we need when we discretize Black–Scholes in Chapter 6.

Each section begins with a one-line **Punchline**, then an **Intuition** paragraph (why is this true before how), then definitions, worked examples, figures, and tables. No calculus appears anywhere. Logarithms and exponentials are functions that obey the arithmetic rules of §0.2. Discounting one period back is multiplication by $1/(1+r)$ — that's it.

The chapter has ten sections, ≥40 numbered examples (Example 1.k.j), fifteen referenced figures, and a dozen tables. By the end you will be able to:

1. Decide whether a one-period market admits arbitrage by checking $d<1+r<u$.
2. Replicate any payoff with a portfolio $(\Delta,B)$ of stock and bond, using a 2×2 linear system from §0.11.
3. Price any payoff two ways — by replication and by risk-neutral expectation — and prove the two are the same number.
4. Recognise *why* the probability that prices the option is *not* the probability the world actually runs on.
5. Walk a dealer's hedge ledger end to end.

We will end with the bridge to Chapter 2, where these single-period nodes get glued into a tree.

---

## §1.1 The market: stock, bond, single coin toss

**Punchline.** A *single-period market* has one date $t=0$ (today, prices known) and one date $t=1$ (one tick of time later, prices unknown except they are one of exactly two values). Two assets trade: a *stock* whose price moves randomly, and a *bond* (or money-market account) whose value grows by a known factor $1+r$.

**Intuition.** Strip a market down to the absolute minimum: one source of randomness — one coin flip. The stock will be either *up* or *down* relative to today, and that's the only thing the market can ever decide. Everything else (rates, payoffs, time) is fixed in advance. This is small enough that you can list every possible future on a napkin, but rich enough that *every* idea in derivatives pricing — replication, no-arbitrage, risk-neutral probability, hedging — already lives inside it. The rest of the book is just gluing many of these one-coin worlds end to end.

### 1.1.1 The two assets

**Stock.** Today the price is $S_0>0$. At $t=1$ it takes one of exactly two values,

$$S_1 \;=\; \begin{cases} uS_0 & \text{(coin = H, an *up* move)}\\ dS_0 & \text{(coin = T, a *down* move)}\end{cases}$$

with $0<d<u$ (the up factor is strictly larger than the down factor). We will *not* assume $u>1>d$ at this stage; that condition turns out to follow from no-arbitrage later, but stating it up front would confuse the logic.

**Bond.** A unit invested in the bond at $t=0$ becomes $1+r$ at $t=1$, with certainty. We allow $r$ to be positive, zero, or even negative. The bond is risk-free in the sense that its $t=1$ value is the same in both states of the coin.

**Sample space.** $\Omega = \{H,T\}$, a two-element set. A random variable on $\Omega$ is just a pair of numbers $(\,X(H), X(T)\,)$. Probability assigns weights $p\in(0,1)$ to $H$ and $1-p$ to $T$. *The real-world probability $p$ does not appear in any pricing formula in this chapter*, a fact that will be the source of much confusion and one great theorem.

### 1.1.2 Trees and notation

The visual object we will draw constantly is a *one-step tree*: a root node labelled $S_0$, branching to two leaves labelled $uS_0$ (up, drawn upward) and $dS_0$ (down, drawn downward).

![One-step tree for the toy: root $S_0=4$ branches to $S_1(H)=8$ and $S_1(T)=2$. Edges colour-coded: green for the up move, red for the down move. This skeleton — root plus two leaves — is the only picture you need to keep in your head for the entire chapter.](figures/ch01-tree-skeleton-st.png)

![Toy ($S_0=4,u=2,d=1/2$) and the Realistic market ($S_0=100,u=1.10,d=0.90$) side by side. The geometry is identical; only the numbers differ. The Toy's $u$ and $d$ multiply to $1$ (a deliberate symmetry); the realistic market's $u\cdot d = 0.99$ is close to $1$ but not exactly.](figures/ch01-tree-side-by-side.png)

**Notation glossary** (we will refer to this throughout):

| Symbol | Meaning |
|:---|:---|
| $S_0$ | stock price at $t=0$ |
| $S_1(\omega)$ | stock at $t=1$, $\omega\in\{H,T\}$ |
| $u,d$ | up/down factors, $0<d<u$ |
| $r$ | one-period interest rate |
| $1+r$ | bond gross return |
| $1/(1+r)$ | discount factor |
| $p,\,1-p$ | real-world prob. of $H,T$ |
| $\tilde p,\,1-\tilde p$ | risk-neutral prob. of $H,T$ |
| $V_1$ | payoff at $t=1$ |
| $V_u,V_d$ | $V_1(H),V_1(T)$ |
| $V_0$ | derivative price at $t=0$ |
| $\Delta,B$ | $\Delta$ shares + $B$ bond |
| $X_1$ | portfolio value at $t=1$ |

*Notes.* $r$ is one-period; in a single period continuous and simple rates coincide. $\tilde p$ is constructed from $u,d,r$ in §1.5.

### 1.1.3 Portfolios and their values

A portfolio is a pair $(\Delta,B)$: hold $\Delta$ shares of stock (can be fractional, can be negative) and put $B$ dollars in the bond (can be negative, meaning *borrow* $|B|$). Time-0 cost:

$$X_0 \;=\; \Delta\, S_0 + B.$$

Time-1 value, in either state:

$$X_1(\omega) \;=\; \Delta\, S_1(\omega) + B(1+r),\qquad \omega\in\{H,T\}.$$

So the random variable $X_1$ is a pair of numbers:

$$X_1(H) = \Delta uS_0 + B(1+r), \qquad X_1(T) = \Delta dS_0 + B(1+r).$$

This is just linear algebra in two variables. The replication problem is going to be: given a target pair $(V_u,V_d)$, find $(\Delta,B)$ that makes $X_1=V$ in both states. That is the 2×2 system from §0.11. We solve it in §1.3.

### 1.1.4 Derivative payoffs: a first menagerie

Before we price anything, list the payoff pairs $(V_u,V_d)$ for the standard derivatives. *A derivative at $t=1$ is a pair of numbers — nothing more.*

| Derivative | $V_u$ | $V_d$ |
|:---|:---|:---|
| Call, $K$ | $(uS_0-K)^+$ | $(dS_0-K)^+$ |
| Put, $K$ | $(K-uS_0)^+$ | $(K-dS_0)^+$ |
| Forward, $K$ | $uS_0-K$ | $dS_0-K$ |
| Cash digital | $\mathbf 1_{uS_0>K}$ | $\mathbf 1_{dS_0>K}$ |
| Asset digital | $uS_0\,\mathbf 1_{uS_0>K}$ | $dS_0\,\mathbf 1_{dS_0>K}$ |
| Straddle, $K$ | $\lvert uS_0-K\rvert$ | $\lvert dS_0-K\rvert$ |
| Power, exp 2 | $(uS_0)^2$ | $(dS_0)^2$ |
| Capped call, $(K,C)$ | $((uS_0-K)^+)\wedge(C-K)$ | $((dS_0-K)^+)\wedge(C-K)$ |
| Custom | $a$ | $b$ |

*Plain-English meanings.* **Call**: right to buy at $K$. **Put**: right to sell at $K$. **Forward**: must buy at $K$ (no optionality). **Cash digital**: \$1 if ITM, else \$0. **Asset digital**: receives the stock if ITM, else nothing. **Straddle**: call + put = absolute distance from $K$. **Power, exp 2**: stock-squared payoff. **Capped call, $(K,C)$**: call but capped at $C-K$. **Custom**: arbitrary pair $(a,b)$.

**Example 1.1.1 (Toy, call $K=5$).** $S_1\in\{8,2\}$, so $V_u=\max(8-5,0)=3$ and $V_d=\max(2-5,0)=0$. The payoff is the pair $(3,0)$. We will price this *seven different ways* in the next ten pages and get $V_0=1.20$ every time.

**Example 1.1.2 (Toy, put $K=5$).** $V_u=\max(5-8,0)=0$, $V_d=\max(5-2,0)=3$. Pair $(0,3)$.

**Example 1.1.3 (Toy, digital $K=5$).** $V_u=\mathbf{1}_{\{8>5\}}=1$, $V_d=0$. Pair $(1,0)$.

**Example 1.1.4 (Toy, forward $K=5$).** $V_u=8-5=3$, $V_d=2-5=-3$. Pair $(3,-3)$. Note the *negative* number — forwards can lose money.

**Example 1.1.5 (RL, call $K=100$).** $S_1\in\{110,90\}$. $V_u=10$, $V_d=0$. Pair $(10,0)$.

**Example 1.1.6 (RL, put $K=100$).** $V_u=0$, $V_d=10$. Pair $(0,10)$.

**Example 1.1.7 (RL, straddle $K=100$).** $V_u=|110-100|=10$, $V_d=|90-100|=10$. Pair $(10,10)$. Constant payoff — *a riskless instrument in disguise*; we will see in §1.5 that its price is just $10/(1+r)=10/1.02=9.804$.

**Example 1.1.8 (RL, power option, exp 2).** $V_u=110^2=12100$, $V_d=90^2=8100$. Pair $(12100,8100)$. These big numbers are fine; pricing is still a 2×2 system.

### 1.1.5 Asset cheat-sheet

| Asset | Time-0 value | Time-1 value ($H$) | Time-1 value ($T$) |
|:---|:---:|:---:|:---:|
| Stock (ST) | $4$ | $8$ | $2$ |
| Stock (RL) | $100$ | $110$ | $90$ |
| Bond, \$1 invested (ST) | $1$ | $1.25$ | $1.25$ |
| Bond, \$1 invested (RL) | $1$ | $1.02$ | $1.02$ |
| ST call, $K=5$ | $V_0=?$ | $3$ | $0$ |
| RL call, $K=100$ | $V_0=?$ | $10$ | $0$ |

The two unknown numbers in the last column are the answers we will compute, six different times each.

### 1.1.6 Exercises

1. In RL, what is the put payoff for $K=95$? **Answer:** $V_u=0$, $V_d=\max(95-90,0)=5$. Pair $(0,5)$.
2. In ST, what is the digital with $K=10$? **Answer:** $\mathbf{1}_{\{8>10\}}=0$, $\mathbf{1}_{\{2>10\}}=0$. Pair $(0,0)$. A worthless option.
3. In ST, what is the straddle with $K=4$? **Answer:** $|8-4|=4$, $|2-4|=2$. Pair $(4,2)$.

---

## §1.2 Arbitrage and the no-arbitrage condition $d < 1+r < u$

**Punchline.** The single-period market admits *no arbitrage* if and only if $d < 1+r < u$. Break either inequality and a riskless profit can be locked in at $t=0$.

**Intuition.** $1+r$ is the gross return of the bond — *the* benchmark. The stock returns either $u$ or $d$ in gross terms. If the bond beats the stock in *both* states ($1+r \ge u > d$), you should borrow stock (short it), invest in the bond, and you win in both states. If the bond loses to the stock in *both* states ($d \ge 1+r$), you should borrow at the bond rate, buy the stock, and you win in both states. The only way to make the market interesting — i.e. to make the stock genuinely a *risky* alternative — is to sandwich the bond's return strictly between $d$ and $u$.

### 1.2.1 What is arbitrage?

A *portfolio strategy* in our one-period market is a choice of $(\Delta,B)$ at $t=0$. We say it is an **arbitrage** if all three hold:

1. $X_0 = \Delta S_0 + B \le 0$ (you start with non-positive cash — possibly negative, meaning the trade pays you up front).
2. $X_1(\omega) \ge 0$ in both states $\omega\in\{H,T\}$ (you never lose at $t=1$).
3. $X_1(\omega) > 0$ in at least one state (you sometimes win).

The strongest form (which we will mostly use) is $X_0 = 0$ and $X_1 \ge 0$ with strict inequality somewhere. *No money in, never lose, sometimes win.* That is a money-printing machine.

### 1.2.2 The theorem

**Theorem (no-arbitrage).** The one-period binomial market $(S_0,u,d,r)$ admits no arbitrage if and only if $d<1+r<u$.

**Proof, both directions.**

*Suppose $d<1+r<u$ holds (the "good" case).* Take any portfolio $(\Delta,B)$ with $X_0=0$, i.e. $B=-\Delta S_0$. Then

$$X_1(H) = \Delta uS_0 + B(1+r) = \Delta S_0(u - (1+r)),$$
$$X_1(T) = \Delta dS_0 + B(1+r) = \Delta S_0(d - (1+r)).$$

In the good case $u-(1+r)>0$ and $d-(1+r)<0$. So if $\Delta>0$, then $X_1(H)>0$ but $X_1(T)<0$ — not an arbitrage. If $\Delta<0$, then $X_1(H)<0$ and $X_1(T)>0$ — not an arbitrage either. If $\Delta=0$, then $B=0$ and the portfolio is identically zero — not an arbitrage. So *no* zero-cost portfolio can be a "never lose" portfolio. ✓

*Suppose $1+r\ge u$ (the "bond dominates" case).* The portfolio $\Delta=-1, B=S_0$ (short one share, lend $S_0$) has $X_0=0$. Time-1 value:

$$X_1(H) = -uS_0 + S_0(1+r) = S_0(1+r-u) \ge 0,$$
$$X_1(T) = -dS_0 + S_0(1+r) = S_0(1+r-d) > 0$$

(the second is strict because $1+r\ge u>d$). That is an arbitrage. ✓

*Suppose $d\ge 1+r$ (the "stock dominates" case).* The portfolio $\Delta=+1, B=-S_0$ (long one share, borrow $S_0$) has $X_0=0$.

$$X_1(H) = uS_0 - S_0(1+r) = S_0(u-(1+r)) > 0,$$
$$X_1(T) = dS_0 - S_0(1+r) = S_0(d-(1+r)) \ge 0.$$

Again an arbitrage. ✓

So both halves of the iff are proved.

### 1.2.3 Picturing the condition

The condition $d<1+r<u$ is one inequality on three numbers. On the real line: place $1+r$ in the middle, with $d$ to its left and $u$ to its right.

![No-arbitrage zones on the number line. The green segment $(d,u)$ is where $1+r$ must live. Red segments $(-\infty,d]$ and $[u,\infty)$ are arbitrage zones: stock dominates bond, or bond dominates stock. Three markets plotted: Toy ($d=0.5, 1+r=1.25, u=2$) is well-centred; RL ($0.90, 1.02, 1.10$) is also centred; a broken example ($0.95, 1.02, 1.00$) shows $1+r > u$, an arbitrage.](figures/ch01-noarb-zones.png)

### 1.2.4 Worked verifications

**Example 1.2.1 (Toy, no-arb check).** $d=0.5$, $1+r=1.25$, $u=2$. Is $0.5<1.25<2$? Yes. No arbitrage. ✓

**Example 1.2.2 (RL, no-arb check).** $d=0.90$, $1+r=1.02$, $u=1.10$. Is $0.90<1.02<1.10$? Yes. ✓

**Example 1.2.3 (broken: bond dominates).** Let $u=1.01$, $d=0.97$, $r=0.02$ so $1+r=1.02>u=1.01$. The arbitrage: short one share, lend $S_0$. Cash at $t=0$: $0$. Cash at $t=1$:

- $H$: $-1.01 S_0 + 1.02 S_0 = +0.01 S_0$.
- $T$: $-0.97 S_0 + 1.02 S_0 = +0.05 S_0$.

Both strictly positive. *Profit guaranteed*. With $S_0=100$, you make at least $\$1$ per share and as much as $\$5$, for zero up-front cost.

**Example 1.2.4 (broken: stock dominates).** Let $u=1.10$, $d=1.03$, $r=0.02$ so $d=1.03>1.02=1+r$. The arbitrage: long one share, borrow $S_0$. Cash at $t=0$: $0$. Cash at $t=1$:

- $H$: $1.10 S_0 - 1.02 S_0 = +0.08 S_0$.
- $T$: $1.03 S_0 - 1.02 S_0 = +0.01 S_0$.

Both strictly positive.

**Example 1.2.5 (marginal: $1+r = u$).** $u=1.05, d=0.97, r=0.05$. Now $1+r=u$. The "bond dominates" arbitrage still works *weakly* — in $H$ you make exactly zero, in $T$ you make $S_0(1.05-0.97)=0.08 S_0>0$. It is still an arbitrage (the third condition requires strict positivity only in *one* state). So the strict inequality matters: $d<1+r<u$ must hold strictly.

**Example 1.2.6 (marginal: $d=1+r$).** Symmetric to the above; $\Delta=+1, B=-S_0$ gives an arbitrage with strict profit only in $H$.

**Example 1.2.7 (negative rates).** Let $r=-0.01$, $u=1.05$, $d=0.97$, so $1+r=0.99$. Is $0.97<0.99<1.05$? Yes. No arbitrage. Negative rates are fine as long as $d<1+r$ still holds. In the post-2014 European bond market this case was the norm.

**Example 1.2.8 (the bond is just an asset).** If instead of a bond you had a second risky asset that paid $1+r$ in both states, the analysis is identical. The "bond" is a placeholder for "any asset with a deterministic return." Sometimes called the *numéraire*.

### 1.2.5 Arbitrage cashflow diagram

![Cashflow diagram for the broken-up arbitrage in Example 1.2.3 ($u=1.01, d=0.97, 1+r=1.02$). Top bar: $t=0$ position — short one share (+$S_0$ cash) and lend $S_0$ (-$S_0$ cash) — net zero. Bottom-left bar: in state $H$, repurchase share at $1.01 S_0$ (-$1.01 S_0$), bond pays back $1.02 S_0$ (+$1.02 S_0$) — net $+0.01 S_0$. Bottom-right bar: in state $T$, repurchase share at $0.97 S_0$, bond pays $1.02 S_0$ — net $+0.05 S_0$. Both positive — riskless profit.](figures/ch01-arb-cashflow.png)

### 1.2.6 Four-quadrant table

| Case | Condition | Arb portfolio $(\Delta,B)$ |
|:---|:---:|:---:|
| Good market | $d<1+r<u$ | none |
| Bond dominates | $1+r\ge u$ | $(-1,\,+S_0)$ |
| Stock dominates | $d \ge 1+r$ | $(+1,\,-S_0)$ |
| Both fail | impossible since $d<u$ | — |

*Profit signs.* When **bond dominates**, the portfolio $(-1,+S_0)$ pays $\ge 0$ in state $H$ and $>0$ in state $T$ (strictly positive at least once: free money). When **stock dominates**, the portfolio $(+1,-S_0)$ pays $>0$ in $H$ and $\ge 0$ in $T$.

*Blank: no arbitrage portfolio exists or case is vacuous.*

### 1.2.7 Test parameter triples

**Table 1.2.** Eight $(u,d,r)$ triples and whether the market is arbitrage-free.

| $u$ | $d$ | $r$ | $1+r$ | $d<1+r<u$? | Verdict |
|---:|---:|---:|---:|:---:|:---|
| $2.00$ | $0.50$ | $\phantom{-}0.25$ | $1.25$ | Yes | OK |
| $1.10$ | $0.90$ | $\phantom{-}0.02$ | $1.02$ | Yes | OK |
| $1.10$ | $0.90$ | $\phantom{-}0.15$ | $1.15$ | No | Short |
| $1.05$ | $0.95$ | $-0.01$ | $0.99$ | Yes | OK |
| $1.20$ | $1.05$ | $\phantom{-}0.10$ | $1.10$ | Yes | OK |
| $1.50$ | $0.80$ | $\phantom{-}0.05$ | $1.05$ | Yes | OK |
| $1.01$ | $0.99$ | $\phantom{-}0.02$ | $1.02$ | No | Short |
| $1.05$ | $1.03$ | $\phantom{-}0.02$ | $1.02$ | No | Long |
| $1.00$ | $1.00$ | $\phantom{-}0.00$ | $1.00$ | No | Degen |

*Legend.* OK = $d<1+r<u$, no arbitrage. Short = bond dominates ($1+r\ge u$); short the stock, long the bond. Long = stock dominates ($d\ge 1+r$); long the stock, short the bond. Degen = $u=d$, no randomness.

The last row is a market with no randomness; pricing is trivial (everything = bond) and the no-arbitrage *strict* inequality fails because there's nothing to sandwich.

### 1.2.8 Exercises

1. Show that $u=1.30, d=0.85, r=0.10$ is arb-free. **Answer:** $0.85<1.10<1.30$. ✓
2. For $u=1.05, d=1.03, r=0.02$, find the arb. **Answer:** $1+r=1.02<d=1.03$, so the stock dominates. Long one share, borrow $S_0$: $X_0=0$. In $H$, $X_1 = (1.05-1.02)S_0 = 0.03\,S_0 > 0$; in $T$, $X_1 = (1.03-1.02)S_0 = 0.01\,S_0 > 0$. Both strictly positive — guaranteed profit.
3. What is the *symmetric* boundary case ($1+r = \tfrac{1}{2}(u+d)$)? **Answer:** Just a centred market; no special significance for arbitrage as long as the strict inequalities hold.

---

## §1.3 Replicating a derivative payoff

**Punchline.** Given any pair of numbers $(V_u, V_d)$, there is a unique portfolio $(\Delta, B)$ whose time-1 value is $V_u$ in state $H$ and $V_d$ in state $T$. The formulas are

$$\boxed{\Delta \;=\; \frac{V_u - V_d}{(u-d)S_0}, \qquad B \;=\; \frac{uV_d - dV_u}{(u-d)(1+r)}.}$$

The cost of building this portfolio at $t=0$ is $\Delta S_0 + B$ — that is the *replication price* of the derivative.

**Intuition.** A derivative payoff is two numbers. The portfolio has two knobs ($\Delta$ and $B$). The map from knobs to payoff is *linear* (each knob produces a linear contribution to each state). So it is a 2×2 linear system in two unknowns, and §0.11 says that has a unique solution whenever the system isn't degenerate. The only way the system is degenerate is $u=d$ — which we ruled out. Replication is therefore *automatic*: any payoff can be built from stock and bond, full stop.

### 1.3.1 Deriving the formulas

We want $X_1(H) = V_u$ and $X_1(T) = V_d$, i.e.,

$$\Delta\, uS_0 + B(1+r) = V_u,$$
$$\Delta\, dS_0 + B(1+r) = V_d.$$

Subtract the second from the first:

$$\Delta(u - d)S_0 = V_u - V_d \quad\Longrightarrow\quad \Delta = \frac{V_u - V_d}{(u-d)S_0}.$$

This is the *delta* of the derivative — the number of shares you must hold. The formula says **delta is the rise-over-run of the payoff across the two states**, normalised by $S_0$.

Now solve for $B$. Use the second equation:

$$B(1+r) = V_d - \Delta\, dS_0 = V_d - \frac{d(V_u-V_d)}{u-d} = \frac{(u-d)V_d - d(V_u-V_d)}{u-d} = \frac{uV_d - dV_u}{u-d}.$$

Divide by $1+r$ to finish.

The replication price is

$$V_0 \;=\; \Delta\, S_0 + B \;=\; \frac{V_u-V_d}{u-d} + \frac{uV_d - dV_u}{(u-d)(1+r)}.$$

We will simplify this expression in §1.5 and recognise the result as a risk-neutral expectation. For now we just compute it on examples.

### 1.3.2 Worked examples — Toy menagerie

In all of these, $S_0=4$, $u=2$, $d=0.5$, $r=0.25$, so $u-d=1.5$, $(u-d)S_0=6$, $1+r=1.25$, $(u-d)(1+r)=1.875$.

**Example 1.3.1 (ST call, $K=5$).** $V_u=3, V_d=0$.
$$\Delta = \frac{3-0}{6} = 0.5, \qquad B = \frac{2\cdot 0 - 0.5\cdot 3}{1.875} = \frac{-1.5}{1.875} = -0.8.$$
Cost: $V_0 = 0.5\cdot 4 + (-0.8) = 2.0 - 0.8 = \boxed{1.20}$. Hold half a share, borrow $\$0.80$.

*Check.* Time-1 in $H$: $0.5\cdot 8 + (-0.8)\cdot 1.25 = 4 - 1 = 3 = V_u$. ✓ Time-1 in $T$: $0.5\cdot 2 - 1 = 0 = V_d$. ✓

**Example 1.3.2 (ST put, $K=5$).** $V_u=0, V_d=3$.
$$\Delta = \frac{0-3}{6} = -0.5, \qquad B = \frac{2\cdot 3 - 0.5\cdot 0}{1.875} = \frac{6}{1.875} = 3.2.$$
Cost: $V_0 = -0.5\cdot 4 + 3.2 = -2 + 3.2 = \boxed{1.20}$. Same price as the call! (Coincidence in this symmetric toy: see Example 1.9.1 on parity.)

*Check.* Time-1 in $H$: $-0.5\cdot 8 + 3.2\cdot 1.25 = -4 + 4 = 0$. ✓ Time-1 in $T$: $-0.5\cdot 2 + 4 = 3$. ✓

**Example 1.3.3 (ST digital, $K=5$).** $V_u=1, V_d=0$.
$$\Delta = \frac{1}{6}, \qquad B = \frac{-0.5}{1.875} = -\frac{4}{15}.$$
Cost: $\frac{1}{6}\cdot 4 - \frac{4}{15} = \frac{2}{3} - \frac{4}{15} = \frac{10-4}{15} = \frac{6}{15} = 0.40$.

**Example 1.3.4 (ST forward, $K=5$).** $V_u=3, V_d=-3$.
$$\Delta = \frac{3-(-3)}{6} = 1, \qquad B = \frac{2(-3) - 0.5(3)}{1.875} = \frac{-7.5}{1.875} = -4.$$
Cost: $1\cdot 4 - 4 = 0$. A forward struck at $K=5$ costs zero today — meaning the "fair forward price" $F$ is the one that makes the forward cost zero. Solving $S_0 - F/(1+r) = 0$ gives $F = (1+r)S_0 = 5$. ✓

**Example 1.3.5 (ST asset-or-nothing, $K=5$).** $V_u=8, V_d=0$.
$$\Delta = \frac{8}{6} = \tfrac{4}{3}, \qquad B = \frac{-4}{1.875} = -\tfrac{32}{15}.$$
Cost: $\tfrac{4}{3}\cdot 4 - \tfrac{32}{15} = \tfrac{16}{3} - \tfrac{32}{15} = \tfrac{80-32}{15} = \tfrac{48}{15} = 3.20$.

**Example 1.3.6 (ST straddle, $K=4$).** $V_u=4, V_d=2$.
$$\Delta = \frac{2}{6} = \tfrac{1}{3}, \qquad B = \frac{2\cdot 2 - 0.5\cdot 4}{1.875} = \frac{2}{1.875} = \tfrac{16}{15}.$$
Cost: $\tfrac{1}{3}\cdot 4 + \tfrac{16}{15} = \tfrac{4}{3} + \tfrac{16}{15} = \tfrac{20+16}{15} = \tfrac{36}{15} = 2.40$.

**Example 1.3.7 (ST custom payoff $(25,-5)$).** Suppose a structured product pays $\$25$ in $H$ and *charges* $\$5$ in $T$.
$$\Delta = \frac{25-(-5)}{6} = 5, \qquad B = \frac{2(-5) - 0.5(25)}{1.875} = \frac{-22.5}{1.875} = -12.$$
Cost: $5\cdot 4 - 12 = 8.$ *Verification:* time-1 in $H$: $5\cdot 8 -12\cdot 1.25 = 40-15 = 25$. ✓ In $T$: $5\cdot 2 - 12\cdot 1.25 = 10-15 = -5$. ✓

**Example 1.3.8 (ST power option, exp 2).** $V_u=8^2=64$, $V_d=2^2=4$.
$$\Delta = \frac{60}{6} = 10, \qquad B = \frac{2\cdot 4 - 0.5\cdot 64}{1.875} = \frac{-24}{1.875} = -12.8.$$
Cost: $10\cdot 4 - 12.8 = 27.20$.

**Example 1.3.9 (ST capped call, $K=4,C=6$).** Call payoffs $(4,0)$, but capped at $C-K=2$: $V_u=\min(4,2)=2$, $V_d=0$.
$$\Delta = \frac{2}{6} = \tfrac{1}{3}, \qquad B = \frac{-1}{1.875} = -\tfrac{8}{15}.$$
Cost: $\tfrac{1}{3}\cdot 4 - \tfrac{8}{15} = \tfrac{20-8}{15} = \tfrac{12}{15} = 0.80$.

### 1.3.3 Worked examples — Realistic menagerie

Here $S_0=100$, $u=1.10$, $d=0.90$, $r=0.02$, so $u-d=0.20$, $(u-d)S_0 = 20$, $1+r=1.02$, $(u-d)(1+r)=0.204$.

**Example 1.3.10 (RL call, $K=100$).** $V_u=10, V_d=0$.
$$\Delta = \frac{10}{20} = 0.5, \qquad B = \frac{1.10(0) - 0.90(10)}{0.204} = \frac{-9}{0.204} = -44.117647\ldots$$
Cost: $0.5(100) - 44.1176 = 50 - 44.1176 = \boxed{5.8824}$.

**Example 1.3.11 (RL put, $K=100$).** $V_u=0, V_d=10$.
$$\Delta = \frac{-10}{20} = -0.5, \qquad B = \frac{1.10(10) - 0}{0.204} = \frac{11}{0.204} = 53.9216.$$
Cost: $-50 + 53.9216 = \boxed{3.9216}$.

**Example 1.3.12 (RL digital, $K=100$).** $V_u=1, V_d=0$.
$$\Delta = \frac{1}{20} = 0.05, \qquad B = \frac{0 - 0.90}{0.204} = -4.4118.$$
Cost: $0.05(100) - 4.4118 = 5 - 4.4118 = 0.5882$.

**Example 1.3.13 (RL straddle, $K=100$).** $V_u=10, V_d=10$.
$$\Delta = 0, \qquad B = \frac{1.10(10) - 0.90(10)}{0.204} = \frac{2}{0.204} = 9.8039.$$
Cost: $0 + 9.8039 = 9.8039$. *Equal to $10/(1+r)$*, the discounted certain payoff. The portfolio is entirely in the bond, because the payoff is deterministic — no hedge needed.

**Example 1.3.14 (RL forward, $K=100$).** $V_u=10, V_d=-10$.
$$\Delta = \frac{20}{20} = 1, \qquad B = \frac{1.10(-10) - 0.90(10)}{0.204} = \frac{-20}{0.204} = -98.0392.$$
Cost: $100 - 98.0392 = 1.9608$. The forward struck at $100$ costs $\$1.96$ today. The *fair forward price* (the strike that costs zero) is $(1+r)S_0 = 102$.

**Example 1.3.15 (RL forward struck at $102$).** $V_u=8, V_d=-12$.
$$\Delta = 1, \qquad B = \frac{1.10(-12) - 0.90(8)}{0.204} = \frac{-20.4}{0.204} = -100.$$
Cost: $100 - 100 = 0$. ✓

**Example 1.3.16 (RL risk-reversal).** Long call $K=110$, short put $K=90$. Payoffs: call$(110)$ gives $V_u=0, V_d=0$; put$(90)$ gives $V_u=0, V_d=0$. The risk-reversal here is identically zero — useless example with these specific strikes. Try call$(K=100)$ minus put$(K=100)$: payoffs $(10,0)-(0,10) = (10,-10)$ — same as the forward at $K=100$. So this risk-reversal *is* a forward; cost $\$1.96$ as in 1.3.14. The put-call parity in §1.9 will make this exact.

**Example 1.3.17 (RL power option, exp 2).** $V_u=110^2=12100, V_d=90^2=8100$.
$$
\begin{aligned}
\Delta &= \frac{4000}{20} = 200, \\
B &= \frac{1.10(8100) - 0.90(12100)}{0.204}
  = \frac{8910 - 10890}{0.204}
  = \frac{-1980}{0.204}
  = -9705.88.
\end{aligned}
$$
Cost: $200(100) - 9705.88 = 20000 - 9705.88 = 10294.12$.

**Example 1.3.18 (RL capped call, $K=100, C=105$).** Call payoffs are $(10,0)$ capped at $5$: $V_u=5, V_d=0$.
$$\Delta = 0.25, \qquad B = \frac{0 - 0.90(5)}{0.204} = -22.0588.$$
Cost: $25 - 22.0588 = 2.9412$. *Half* the price of the uncapped RL call ($5.8824$).

### 1.3.4 Replication-wheel and 3-D delta plane

![Replication as 2-D vector decomposition. The payoff $(V_u,V_d)=(3,0)$ (ST call) is the sum of $\Delta=0.5$ copies of the stock vector $(uS_0,dS_0)=(8,2)$ — namely $(4,1)$ — and $-0.8$ copies of the bond vector $(1+r,1+r)=(1.25,1.25)$ — namely $(-1,-1)$. Tip-to-tail: $(4,1)+(-1,-1)=(3,0)$. ✓ The stock vector and bond vector span the entire 2-D plane; any payoff can be reached.](figures/ch01-replication-wheel.png)

![3-D plane showing $\Delta=(V_u-V_d)/((u-d)S_0)$ as a linear function of the payoff pair $(V_u,V_d)$. For the ST world the plane has slope $+1/6$ in the $V_u$ direction and $-1/6$ in the $V_d$ direction. Three derivatives plotted on the surface: call $(3,0)\mapsto 0.5$, put $(0,3)\mapsto -0.5$, straddle $(4,2)\mapsto 0.33$.](figures/ch01-delta-plane-3d.png)

![Cost decomposition $V_0 = \Delta S_0 + B$ for six ST derivatives. Each bar is a derivative's price split into the *stock leg* ($\Delta S_0$, blue, can be positive or negative) and the *bond leg* ($B$, orange). For the call: stock leg $+2.0$, bond leg $-0.8$ (you're financing the stock by borrowing); net $1.20$. For the put the legs flip sign.](figures/ch01-cost-decomposition.png)

### 1.3.5 Replication cookbook

**Table 1.3.** Toy ($S_0=4,u=2,d=0.5,r=0.25$).

| Derivative | $(V_u,V_d)$ | $\Delta$ | $B$ | $V_0$ |
|:---|:---|---:|---:|---:|
| Call $K=5$ | $(3,0)$ | $\phantom{-0}0.500$ | $\phantom{+0}-0.800$ | $\phantom{0}1.200$ |
| Put $K=5$ | $(0,3)$ | $\phantom{-0}-0.500$ | $\phantom{00}+3.200$ | $\phantom{0}1.200$ |
| Digital $K=5$ | $(1,0)$ | $\phantom{-0}0.167$ | $\phantom{+0}-0.267$ | $\phantom{0}0.400$ |
| Forward $K=5$ | $(3,-3)$ | $\phantom{-0}1.000$ | $\phantom{+0}-4.000$ | $\phantom{0}0.000$ |
| Asset-digital $K=5$ | $(8,0)$ | $\phantom{-0}1.333$ | $\phantom{+0}-2.133$ | $\phantom{0}3.200$ |
| Straddle $K=4$ | $(4,2)$ | $\phantom{-0}0.333$ | $\phantom{00}+1.067$ | $\phantom{0}2.400$ |
| Power, exp 2 | $(64,4)$ | $10.000$ | $-12.800$ | $27.200$ |
| Capped call $K=4,C=6$ | $(2,0)$ | $\phantom{-0}0.333$ | $\phantom{+0}-0.533$ | $\phantom{0}0.800$ |
| Custom | $(25,-5)$ | $\phantom{-0}5.000$ | $-12.000$ | $\phantom{0}8.000$ |

**Table 1.4.** Realistic market ($S_0=100,u=1.10,d=0.90,r=0.02$).

| Derivative | $(V_u,V_d)$ | $\Delta$ | $B$ | $V_0$ |
|:---|:---:|---:|---:|---:|
| Call $K{=}100$ | $(10,0)$ | $0.500$ | $-44.12$ | $5.88$ |
| Put $K{=}100$ | $(0,10)$ | $-0.500$ | $+53.92$ | $3.92$ |
| Digital $K{=}100$ | $(1,0)$ | $0.050$ | $-4.41$ | $0.59$ |
| Forward $K{=}100$ | $(10,-10)$ | $1.000$ | $-98.04$ | $1.96$ |
| Forward $K{=}102$ | $(8,-12)$ | $1.000$ | $-100.00$ | $0.00$ |
| Straddle $K{=}100$ | $(10,10)$ | $0.000$ | $+9.80$ | $9.80$ |
| Power, exp 2 | $(12100,8100)$ | $200.0$ | $-9705.88$ | $10294.12$ |
| Capped $K{=}100,C{=}105$ | $(5,0)$ | $0.250$ | $-22.06$ | $2.94$ |

### 1.3.6 Exercises

1. In ST, replicate a put with $K=4$. **Answer:** Payoff $(V_u,V_d)=(0,2)$. $\Delta=(0-2)/6=-1/3$. $B=(u V_d-d V_u)/((u-d)(1+r))=(2\cdot 2-0.5\cdot 0)/((1.5)(1.25))=4/1.875=32/15\approx 2.133$. $V_0=\Delta S_0+B=-4/3+32/15=(-20+32)/15=12/15=0.80$.
2. In RL, replicate a put with $K=95$. **Answer:** Payoff $(0,5)$. $\Delta=-0.25$, $B=(1.10\cdot 5)/0.204=26.96$. $V_0=-25+26.96=1.961$.
3. In RL, replicate a "binary range" that pays \$10 only if the stock ends *between* 95 and 105. **Answer:** Payoff $(10,10)$ (both in range). $\Delta=0$, $B=10/1.02=9.804$. Cost $9.804$. Riskless, all bond.

---

## §1.4 Replication price = no-arbitrage price

**Punchline.** In an arbitrage-free market, the only price at which a derivative can trade is its replication cost $V_0=\Delta S_0+B$. If anyone quotes a different number, you can arbitrage them.

**Intuition.** Replication produces a portfolio that pays *exactly* the derivative's payoff in every state of the world. From the market's point of view, the portfolio and the derivative are the *same instrument* — they have identical cash flows at $t=1$. By the no-arbitrage principle, two instruments with identical cash flows must have identical prices. If they didn't, you'd buy the cheap one, sell the expensive one, pocket the difference, and walk away with no further exposure. So the replication price *is* the price.

### 1.4.1 The two-way arbitrage proof

Suppose the market quotes the derivative at $V^{\text{mkt}}_0$, and the replication price is $V_0=\Delta S_0+B$.

**Case A: $V^{\text{mkt}}_0 > V_0$ (overpriced).** Sell the derivative for $V^{\text{mkt}}_0$, build the replicating portfolio for $V_0$, pocket $V^{\text{mkt}}_0-V_0>0$. At $t=1$, your derivative obligation is $V_1$, and your portfolio pays exactly $V_1$ — net zero in both states. *You made $V^{\text{mkt}}_0-V_0$ for free.*

**Case B: $V^{\text{mkt}}_0 < V_0$ (underpriced).** Buy the derivative for $V^{\text{mkt}}_0$ and short the replicating portfolio. To *short* a portfolio $(\Delta,B)$, take the opposite position $(-\Delta,-B)$: this costs $-V_0$ at $t=0$ (i.e. you *receive* $V_0$). Net $t=0$ cash: $V_0 - V^{\text{mkt}}_0 > 0$ — you pocket the spread. At $t=1$: the derivative pays $V_1$ and the short portfolio pays $-V_1$. Net zero in both states.

In both cases, mispricing prints money. So $V^{\text{mkt}}_0$ must equal $V_0$.

### 1.4.2 Worked example: ST call quoted high

**Example 1.4.1 (ST call quoted at 1.50).** True replication price $V_0=1.20$. Market quote $1.50$. Mispriced by $0.30$ — too expensive.

Arbitrage:

- $t=0$: sell call for $1.50$ (+$1.50$); buy $\Delta=0.5$ shares ($-2.00$); borrow $0.80$ (+$0.80$). Net cash: $+1.50 - 2.00 + 0.80 = +0.30$. *Pocket $0.30$.*
- $t=1$, $H$: deliver call payoff $3$ ($-3$); shares now worth $0.5\cdot 8 = 4$ ($+4$); repay loan $0.80\cdot 1.25=1$ ($-1$). Net: $-3+4-1=0$. ✓
- $t=1$, $T$: deliver call payoff $0$; shares worth $0.5\cdot 2=1$ ($+1$); repay loan $1$ ($-1$). Net: $0+1-1=0$. ✓

You walk away with $\$0.30$ and zero residual risk.

**Example 1.4.2 (ST call quoted at 1.00).** Mispriced by $0.20$ — too cheap.

Arbitrage:

- $t=0$: buy call for $1.00$ ($-1.00$); short $0.5$ shares ($+2.00$); lend $0.80$ ($-0.80$). Net cash: $-1.00+2.00-0.80 = +0.20$.
- $t=1$, $H$: receive call payoff $3$ ($+3$); cover short at $8\cdot 0.5=4$ ($-4$); bond pays $1$ ($+1$). Net: $+3-4+1=0$. ✓
- $t=1$, $T$: receive call payoff $0$; cover at $2\cdot 0.5=1$ ($-1$); bond $1$. Net: $0-1+1=0$. ✓

Locked-in $\$0.20$.

**Example 1.4.3 (RL call quoted at 7.00).** True $V_0=5.8824$. Mispriced by $1.1176$ — too high.

- $t=0$: sell call $+7.00$; buy $0.5$ shares $-50.00$; borrow $44.1176$ to fund (+44.1176). Net: $+1.1176$.
- $t=1$ $H$: deliver $10$; shares $55$; repay loan $44.1176\cdot 1.02=45.00$. Net: $-10+55-45=0$. ✓
- $t=1$ $T$: deliver $0$; shares $45$; repay $45$. Net: $0+45-45=0$. ✓

**Example 1.4.4 (RL put quoted at 3.00).** True $V_0=3.9216$. Mispriced by $0.9216$ — too cheap. The put's replicating portfolio is $(\Delta,B)=(-0.5,+53.9216)$. To capture the underpricing, *buy* the cheap put and *short* the replicating portfolio (take position $(+0.5,-53.9216)$, i.e. long $0.5$ shares and borrow $53.9216$).

- $t=0$: buy put $-3.00$; buy $0.5$ shares $-50.00$; borrow $53.9216$ $+53.9216$. Net: $-3.00 - 50.00 + 53.9216 = +0.9216$. *Pocket $0.9216$.*
- $t=1$ $H$: receive put $0$; sell shares $+55.00$; repay loan $53.9216\cdot 1.02 = 55.00$ ($-55.00$). Net: $0+55-55=0$. ✓
- $t=1$ $T$: receive put $+10.00$; sell shares $+45.00$; repay $55.00$ ($-55.00$). Net: $10+45-55=0$. ✓

### 1.4.3 Cashflow ledger

**Table 1.5.** Two-column cashflow for the over-priced ST call ($V^{\text{mkt}}=1.50$, $V_0=1.20$).

| Time | State | Sell call | Long $0.5$ stock | Borrow $0.80$ | Total |
|:---:|:---:|---:|---:|---:|---:|
| $t=0$ | | $+1.50$ | $-2.00$ | $+0.80$ | $+0.30$ |
| $t=1$ | $H$ | $-3.00$ | $+4.00$ | $-1.00$ | $\phantom{+}0.00$ |
| $t=1$ | $T$ | $\phantom{+}0.00$ | $+1.00$ | $-1.00$ | $\phantom{+}0.00$ |

*Blank in "State" column: no state distinction at $t=0$.*

### 1.4.4 Why "law of one price" is the right name

When two instruments have identical payoffs, they must have the same price. That is the *law of one price*. The argument we just gave is the one-period version of it. Every option pricing theorem in finance is, at heart, a law-of-one-price argument: identify a portfolio that replicates the option, and the option's price is the portfolio's cost.

### 1.4.5 Exercises

1. ST call quoted at $1.10$ (cheap by $0.10$). Find the arb cashflow. **Answer:** Buy call $-1.10$; short $0.5$ shares $+2.00$; lend $0.80$ $-0.80$; net $+0.10$ today, zero in both states.
2. RL put quoted at $5.00$ (rich; true price $3.9216$). **Answer:** Sell the over-priced put $+5.00$; build (buy) its replicating portfolio $(\Delta,B)=(-0.5,+53.9216)$ — short $0.5$ shares $+50.00$ and lend $53.9216$ $-53.9216$, total cost $-3.9216$. Net cash at $t=0$: $+5.00 - 3.9216 = +1.0784$. The replicating portfolio pays exactly the put payoff at $t=1$, so the obligation to the buyer is matched in both states. *Pocket $1.0784$.*

---

## §1.5 Risk-neutral probability and the second pricing formula

**Punchline.** Define $\tilde p = \dfrac{(1+r)-d}{u-d}$ and $\tilde q = 1-\tilde p$. The no-arbitrage price of any payoff is

$$\boxed{V_0 \;=\; \frac{1}{1+r}\,\bigl[\tilde p\, V_u + \tilde q\, V_d\bigr]\;=\;\frac{1}{1+r}\,\widetilde{\mathbb E}[V_1].}$$

That is: discounted expectation under $\tilde p$. This is the *second route* to the same price we got by replication.

**Intuition.** The number $\tilde p$ is not the "real" probability of an up move in any meaningful sense — it depends only on $u,d,r$ and *not at all* on the actual probability $p$ that the world's coin lands heads. Instead, $\tilde p$ is the unique probability that makes the *stock's expected return equal to the bond's*. Under $\tilde p$, all assets earn $r$. That's why it's called *risk-neutral*: in a world where everyone is indifferent to risk, every asset pays the risk-free rate. Real investors aren't risk-neutral — but the *prices* are still set as if they were.

### 1.5.1 Where does $\tilde p$ come from?

Start with the replication formula

$$V_0 = \frac{V_u-V_d}{u-d} + \frac{uV_d - dV_u}{(u-d)(1+r)}.$$

Put over a common denominator $(u-d)(1+r)$:

$$V_0 = \frac{(1+r)(V_u-V_d) + uV_d - dV_u}{(u-d)(1+r)} = \frac{V_u[(1+r) - d] + V_d[u - (1+r)]}{(u-d)(1+r)}.$$

Factor out $1/(1+r)$:

$$V_0 = \frac{1}{1+r}\cdot \frac{(1+r)-d}{u-d}\cdot V_u + \frac{1}{1+r}\cdot\frac{u-(1+r)}{u-d}\cdot V_d.$$

Define $\tilde p = ((1+r)-d)/(u-d)$. Then $\tilde q = 1 - \tilde p = (u-(1+r))/(u-d)$. So

$$V_0 = \frac{1}{1+r}\bigl[\tilde p\,V_u + \tilde q\,V_d\bigr].$$

That's it. Same algebra, repackaged.

### 1.5.2 $\tilde p\in(0,1)$ iff no-arbitrage

Notice: $\tilde p>0$ iff $1+r>d$, and $\tilde p<1$ iff $1+r<u$. So $\tilde p\in(0,1)$ exactly when $d<1+r<u$. This gives a slick alternative to the no-arbitrage theorem: *the market is arb-free iff the risk-neutral probability lives in $(0,1)$ — i.e., is an honest probability*.

### 1.5.3 Computing $\tilde p$ in the two worlds

**Toy.** $\tilde p = (1.25-0.5)/(2-0.5) = 0.75/1.5 = 0.5$.

**Realistic.** $\tilde p = (1.02-0.90)/(1.10-0.90) = 0.12/0.20 = 0.60$.

Both are honest probabilities, confirming both markets are arb-free.

### 1.5.4 Reprice the menagerie via $\tilde p$

In ST, the discount factor is $1/(1+r)=0.8$ and $\tilde p=\tilde q=0.5$, so $V_0=0.8\cdot 0.5(V_u+V_d) = 0.4(V_u+V_d)$.

**Example 1.5.1 (ST call).** $V_0=0.4(3+0)=1.20$. ✓
**Example 1.5.2 (ST put).** $V_0=0.4(0+3)=1.20$. ✓
**Example 1.5.3 (ST digital).** $V_0=0.4(1+0)=0.40$. ✓
**Example 1.5.4 (ST forward $K=5$).** $V_0=0.4(3-3)=0$. ✓
**Example 1.5.5 (ST asset-digital).** $V_0=0.4(8+0)=3.20$. ✓
**Example 1.5.6 (ST straddle $K=4$).** $V_0=0.4(4+2)=2.40$. ✓
**Example 1.5.7 (ST power exp 2).** $V_0=0.4(64+4)=27.20$. ✓
**Example 1.5.8 (ST capped call $K=4,C=6$).** $V_0=0.4(2+0)=0.80$. ✓

In RL, discount factor $1/1.02$, $\tilde p=0.60$, $\tilde q=0.40$.

**Example 1.5.9 (RL call).** $V_0=(0.6\cdot 10+0.4\cdot 0)/1.02 = 6/1.02 = 5.8824$. ✓
**Example 1.5.10 (RL put).** $V_0=(0.6\cdot 0 + 0.4\cdot 10)/1.02 = 4/1.02 = 3.9216$. ✓
**Example 1.5.11 (RL digital).** $V_0=0.6/1.02=0.5882$. ✓
**Example 1.5.12 (RL forward $K=100$).** $V_0=(0.6\cdot 10+0.4\cdot(-10))/1.02 = 2/1.02 = 1.9608$. ✓
**Example 1.5.13 (RL straddle $K=100$).** $V_0=10/1.02 = 9.8039$. ✓
**Example 1.5.14 (RL power exp 2).** $V_0=(0.6\cdot 12100+0.4\cdot 8100)/1.02 = (7260+3240)/1.02 = 10500/1.02 = 10294.12$. ✓
**Example 1.5.15 (RL capped call).** $V_0=(0.6\cdot 5)/1.02=2.9412$. ✓

Every entry of Tables 1.3 and 1.4 is reproduced. *Two routes, one price.*

### 1.5.5 Sensitivity to $r$ and $u$

**Example 1.5.16 (ST call as $r$ varies).** Keep $u=2, d=0.5, S_0=4, K=5$.

| $r$ | $1+r$ | $\tilde p$ | $V_0$ for call |
|---:|---:|---:|---:|
| $0.10$ | $1.10$ | $0.40$ | $1.0909$ |
| $0.20$ | $1.20$ | $0.4667$ | $1.1667$ |
| $0.25$ | $1.25$ | $0.50$ | $1.20$ |
| $0.30$ | $1.30$ | $0.5333$ | $1.2308$ |
| $0.40$ | $1.40$ | $0.60$ | $1.2857$ |

Call price rises with $r$ — intuitively, higher $r$ means the same upside is *cheaper to borrow toward*.

**Example 1.5.17 (RL call as $u$ varies).** Keep $S_0=100, d=0.90, r=0.02, K=100$.

| $u$ | $V_u$ | $\tilde p$ | $V_0$ for call |
|---:|---:|---:|---:|
| $1.05$ | $5$ | $0.80$ | $3.9216$ |
| $1.10$ | $10$ | $0.60$ | $5.8824$ |
| $1.15$ | $15$ | $0.48$ | $7.0588$ |
| $1.20$ | $20$ | $0.40$ | $7.8431$ |
| $1.30$ | $30$ | $0.30$ | $8.8235$ |

Bigger up-moves raise the call price, despite $\tilde p$ falling — *the payoff grows faster than $\tilde p$ shrinks*.

### 1.5.6 Figures

![Risk-neutral probability $\tilde p$ as a function of $r$, for fixed $u=1.10, d=0.90$. The line crosses $\tilde p=0$ at $r=-0.10$ (= $d-1$) and $\tilde p=1$ at $r=+0.10$ (= $u-1$). Inside this range $\tilde p$ is an honest probability; outside, the market admits arbitrage. Real-world $p=0.55$ is shaded in grey for contrast — *it is not on this curve*.](figures/ch01-tildep-vs-r.png)

![3-D surface of ST call price $V_0$ versus $(u,r)$, with $d=0.5$ and $K=5$ fixed. The surface rises in both directions: bigger $u$ raises payoff, bigger $r$ raises $\tilde p$. The flat colourful contours along the base show the boundary of the no-arbitrage region ($d<1+r<u$, here $r\in(-0.5, u-1)$).](figures/ch01-call-surface-3d.png)

### 1.5.7 $\tilde p$ table

**Table 1.6.** Ten $(u,d,r)$ triples and the resulting $\tilde p$. Broken rows ($\tilde p\notin (0,1)$) are flagged.

| $u$ | $d$ | $r$ | $\tilde p$ | Verdict |
|---:|---:|---:|---:|:---|
| $2.00$ | $0.50$ | $\phantom{-}0.25$ | $0.5000$ | OK |
| $1.10$ | $0.90$ | $\phantom{-}0.02$ | $0.6000$ | OK |
| $1.20$ | $0.80$ | $\phantom{-}0.05$ | $0.6250$ | OK |
| $1.05$ | $0.95$ | $\phantom{-}0.00$ | $0.5000$ | OK |
| $1.30$ | $0.85$ | $\phantom{-}0.10$ | $0.5556$ | OK |
| $1.50$ | $0.80$ | $\phantom{-}0.05$ | $0.3571$ | OK |
| $1.01$ | $0.99$ | $\phantom{-}0.02$ | $1.5000$ | **Broken** |
| $1.20$ | $1.05$ | $\phantom{-}0.10$ | $0.3333$ | OK |
| $1.00$ | $0.95$ | $\phantom{-}0.00$ | $1.0000$ | Boundary |
| $1.10$ | $0.90$ | $\phantom{-}0.15$ | $1.2500$ | **Broken** |

*Legend.* OK = $\tilde p\in(0,1)$ (no arbitrage). **Broken** = $\tilde p\notin(0,1)$; bond dominates ($1+r>u$). Boundary = $d=1+r$ or $1+r=u$ (degenerate). The "OK ($d<1+r<u$)" row at $(u,d,r)=(1.20,1.05,0.10)$ satisfies $1.05<1.10<1.20$.

The two genuinely broken rows give $\tilde p$ outside $(0,1)$ — *not an honest probability*, confirming the no-arbitrage failure.

### 1.5.8 Exercises

1. Compute $\tilde p$ for $u=1.25, d=0.80, r=0.02$. **Answer:** $(1.02-0.80)/(1.25-0.80)=0.22/0.45=0.4889$.
2. Price a digital with $K=4$ in ST. **Answer:** $V_u=1$ (since $8>4$), $V_d=0$ (since $2<4$). $V_0=0.4\cdot 1=0.40$. Same as $K=5$ here — coincidence.
3. Price an option that pays $\$1$ only when the stock goes *down* (RL). **Answer:** $(0,1)$. $V_0=0.4/1.02=0.3922$.

---

## §1.6 Why the two routes give the same number

**Punchline.** Plug the closed-form $(\Delta,B)$ into $\Delta S_0+B$ and you get $(1/(1+r))[\tilde p V_u + \tilde q V_d]$ by pure algebra. The two formulas are *literally the same expression*, written differently.

**Intuition.** Imagine two paths from your house to a friend's. One winds through the woods (replication); the other takes the highway ($\tilde p$). They end at the same friend. The algebra we did in §1.5.1 is exactly the proof that both paths reach the same destination. The replication route is *constructive* — it tells you the hedge. The $\tilde p$ route is *computational* — it just gives you the price. In practice, traders use $\tilde p$ to *quote* prices and $\Delta$ to *hedge*.

### 1.6.1 The algebraic identity, line by line

Recall:

- Replication: $V_0^{\text{rep}} = \Delta S_0 + B$, with $\Delta = (V_u-V_d)/((u-d)S_0)$ and $B = (uV_d-dV_u)/((u-d)(1+r))$.
- Risk-neutral: $V_0^{\text{rn}} = (1/(1+r))[\tilde p V_u + \tilde q V_d]$, with $\tilde p = ((1+r)-d)/(u-d)$ and $\tilde q = (u-(1+r))/(u-d)$.

Step 1. Compute $\Delta S_0$:

$$\Delta S_0 = \frac{V_u - V_d}{u-d}.$$

Step 2. Add $B$:

$$\Delta S_0 + B = \frac{V_u-V_d}{u-d} + \frac{uV_d-dV_u}{(u-d)(1+r)}.$$

Step 3. Common denominator $(u-d)(1+r)$:

$$= \frac{(1+r)(V_u-V_d) + uV_d - dV_u}{(u-d)(1+r)} = \frac{V_u[(1+r)-d] + V_d[u-(1+r)]}{(u-d)(1+r)}.$$

Step 4. Factor out $1/(1+r)$:

$$
\begin{aligned}
&= \frac{1}{1+r}\cdot\Big[V_u\cdot\frac{(1+r)-d}{u-d} + V_d\cdot\frac{u-(1+r)}{u-d}\Big] \\
&= \frac{1}{1+r}[\tilde p V_u + \tilde q V_d] \;=\; V_0^{\text{rn}}.
\end{aligned}
$$

Done.

### 1.6.2 Line-by-line numerical confirmations

**Example 1.6.1 (ST call, $K=5$).** Replication: $\Delta=0.5, B=-0.8$, $V_0=0.5(4)-0.8=1.20$. RN: $(0.5\cdot 3+0.5\cdot 0)/1.25=1.5/1.25=1.20$. ✓

**Example 1.6.2 (RL put, $K=100$).** Replication: $-0.5(100)+53.9216=3.9216$. RN: $(0.6\cdot 0+0.4\cdot 10)/1.02=4/1.02=3.9216$. ✓

**Example 1.6.3 (ST custom $(25,-5)$).** Replication: $5(4)-12=8$. RN: $0.4(25+(-5))=0.4(20)=8$. ✓

**Example 1.6.4 (ST forward $K=5$).** Replication: $1(4)-4=0$. RN: $0.4(3-3)=0$. ✓

**Example 1.6.5 (RL straddle $K=100$).** Replication: $0(100)+9.8039=9.8039$. RN: $(0.6(10)+0.4(10))/1.02=10/1.02=9.8039$. ✓

**Example 1.6.6 (a mistyped formula — counterexample).** Suppose someone writes "$V_0 = (\tilde p V_u + (1-\tilde p)V_d) / r$" — missing the $1+$. For ST call: $0.5(3)/0.25 = 6$. That's wrong (off by a factor of $5$). The point: discount factor is $1/(1+r)$, not $1/r$; the latter would only be correct if $r=1$ (a 100% rate).

### 1.6.3 Commutative diagram

![Commutative diagram of the two pricing routes. Top-left node: payoff $(V_u,V_d)$. Bottom-left: replicating portfolio $(\Delta,B)$ via §0.11. Top-right: discounted RN expectation $(\tilde p V_u + \tilde q V_d)/(1+r)$ via §1.5. Both routes end at $V_0$ (bottom-right). The arrow labels are the §1.3 formulas and the §1.5 formula. The diagram commutes — both compositions yield the same answer.](figures/ch01-commutative-diagram.png)

### 1.6.4 Algebra steps as a table

**Table 1.7.** The four steps of the §1.6.1 identity, applied to the ST call.

| Step | Symbolic | Number |
|:---|:---|---:|
| 1: $\Delta S_0$ | $\tfrac{V_u-V_d}{u-d}$ | $2.000$ |
| 2: $\Delta S_0+B$ | step 1 $+\,\tfrac{uV_d-dV_u}{(u-d)(1+r)}$ | $1.200$ |
| 3: common den. | combine: see line below | $1.200$ |
| 4: factor $\tilde p$ | $\tfrac{1}{1+r}(\tilde p V_u+\tilde q V_d)$ | $1.200$ |

Row 1: $(3-0)/1.5 = 2.0$. Row 2: $2.0 + (2\cdot 0 - 0.5\cdot 3)/1.875 = 2.0 + (-1.5)/1.875 = 2.0 - 0.8 = 1.2$. Row 3 (common denominator $(u-d)(1+r)$): $\tfrac{(1+r)(V_u-V_d) + uV_d - dV_u}{(u-d)(1+r)} = (1.25\cdot 3 - 0.5\cdot 3)/1.875 = 2.25/1.875 = 1.2$. Row 4: $0.8 \cdot (0.5 \cdot 3 + 0.5 \cdot 0) = 0.8 \cdot 1.5 = 1.2$.

### 1.6.5 Exercises

1. Verify Example 1.6.1 by replication line by line on the RL call. **Answer:** $\Delta S_0=0.5(100)=50$. $B=-44.1176$. Sum $=5.8824$.
2. Use $\tilde p$ to price RL forward $K=102$. **Answer:** $(0.6(8)+0.4(-12))/1.02=(4.8-4.8)/1.02=0$. ✓
3. Show that the price of the asset-or-nothing in ST equals $0.4(8) = 3.20$ via $\tilde p$.

---

## §1.7 Why "risk-neutral": expected return = $r$ under $\tilde{\mathbb P}$

**Punchline.** Under the risk-neutral probability $\tilde p$, the stock has expected one-period gross return $1+r$ — *the same as the bond*. Discounted prices are martingales. Under the real probability $p$, by contrast, the stock has expected return *above* $r$ (a "risk premium").

**Intuition.** Asking "what probability would make the stock's expected return equal $r$?" gives you a system of one equation in one unknown — the answer is exactly $\tilde p$. So $\tilde p$ is the unique probability under which buying the stock is no better than buying the bond. In *that* world, no one cares about risk (everything earns $r$). The actual world's probability $p$ may be higher (giving the stock a positive risk premium) or different in some other way; it doesn't matter for pricing.

### 1.7.1 The martingale identity

Compute $\widetilde{\mathbb E}[S_1]$:

$$\widetilde{\mathbb E}[S_1] = \tilde p\, uS_0 + (1-\tilde p)\, dS_0 = S_0[\tilde p u + (1-\tilde p)d].$$

Substitute $\tilde p = ((1+r)-d)/(u-d)$:

$$
\begin{aligned}
\tilde p\, u + (1-\tilde p)\, d
&= \frac{\bigl((1+r) - d\bigr)\,u \;+\; \bigl(u - (1+r)\bigr)\,d}{u-d} \\
&= \frac{u(1+r) - ud + ud - d(1+r)}{u-d} \\
&= \frac{(1+r)(u-d)}{u-d} \\
&= 1+r.
\end{aligned}
$$

So $\widetilde{\mathbb E}[S_1] = (1+r)S_0$. The discounted stock $S_1/(1+r)$ has expectation $S_0$ — a *martingale* (one-step martingale: today's value equals tomorrow's risk-neutral expectation).

### 1.7.2 The real-world return differs

Pick a real-world probability $p$ (different from $\tilde p$ in general). Then

$$\mathbb E[S_1] = puS_0 + (1-p)dS_0 = S_0[pu+(1-p)d].$$

This equals $(1+r)S_0$ iff $p = \tilde p$. For any other $p$, there's a gap.

**Example 1.7.1 (ST, $p=0.7$).** $\mathbb E[S_1]/S_0 = 0.7(2)+0.3(0.5) = 1.55$. So real expected return is $55\%$ — much higher than $r=25\%$. *Risk premium*: $55\%-25\%=30\%$.

**Example 1.7.2 (RL, $p=0.55$).** $\mathbb E[S_1]/S_0 = 0.55(1.10)+0.45(0.90) = 0.605+0.405=1.01$. Real expected return $1\%$, below the bond's $2\%$! That's a *negative* risk premium — investors would be irrational to hold this stock voluntarily. Either $p$ is wrong, or the stock has some other compensation (e.g., it's a hedge).

**Example 1.7.3 (RL, $p=0.65$).** $\mathbb E[S_1]/S_0 = 0.65(1.10)+0.35(0.90) = 0.715+0.315=1.03$. Real expected return $3\%$, risk premium $1\%$ over the bond.

**Example 1.7.4 (ST under $\tilde p=0.5$).** $\widetilde{\mathbb E}[S_1]/S_0 = 0.5(2)+0.5(0.5)=1.25=1+r$. ✓

**Example 1.7.5 (RL under $\tilde p=0.6$).** $0.6(1.10)+0.4(0.90)=0.66+0.36=1.02=1+r$. ✓

### 1.7.3 The call's risk-neutral expected return

**Example 1.7.6 (ST call expected return under $\tilde p$).** Price today $1.20$. Time-1 payoff: $3$ with prob $\tilde p=0.5$, $0$ with prob $0.5$. Expected payoff $1.5$. Expected gross return $1.5/1.20 = 1.25 = 1+r$. ✓

**Example 1.7.7 (ST call under real $p=0.7$).** Expected payoff $0.7(3) = 2.10$. Expected gross return $2.10/1.20 = 1.75$. *Far higher than the bond*. Calls are levered bets; under any sensible real-world $p$ they earn enormous expected returns. (And lose money most of the time, of course — that's the high-variance side.)

**Example 1.7.8 (bond is a trivial martingale).** Bond pays $1+r$ in both states. $\widetilde{\mathbb E}[\text{bond}_1]/(1+r) = (1+r)/(1+r) = 1 = \text{bond}_0$. ✓

### 1.7.4 Side-by-side trees and bar chart

![Real-world tree (left, $p=0.55$ for RL) and risk-neutral tree (right, $\tilde p=0.6$). The probabilities on the edges differ, but the state values $\{uS_0, dS_0\}$ are the same. Under the real probability the drift is $1.01$; under RN it's $1.02$. The drift adjustment from real to RN is exactly the risk premium subtraction.](figures/ch01-real-vs-rn-trees.png)

![Bar chart of expected one-period gross returns. Under real $p=0.55$, RL stock returns $1.01$, ST stock returns ($p=0.7$) $1.55$. Under RN, both stocks return $1+r$ (= $1.02$ and $1.25$ respectively). Bonds always return $1+r$. The call returns $1+r$ under RN but is wildly higher under real $p$.](figures/ch01-returns-bars.png)

### 1.7.5 Asset returns under $\mathbb P$ vs $\tilde{\mathbb P}$

**Table 1.8.** Expected gross returns in the two probability measures.

| Asset | $\mathbb E[\cdot]$ under $\mathbb P$ | $\widetilde{\mathbb E}[\cdot]$ under $\tilde{\mathbb P}$ |
|:---|---:|---:|
| ST stock | $1.55$ | $1.25$ |
| ST bond | $1.25$ | $1.25$ |
| ST call | $1.75$ | $1.25$ |
| RL stock | $1.01$ | $1.02$ |
| RL bond | $1.02$ | $1.02$ |
| RL call | $0.935$ | $1.02$ |

*Notes.* ST entries use $p=0.7$; RL entries use $p=0.55$. RL call: $\mathbb E[V_1] = 0.55(10) + 0.45(0) = 5.5$; gross return $5.5/5.8824 = 0.935$.

Note the *RL call under $p=0.55$ has expected return below 1!* — under such a low $p$ the call mostly expires worthless. This is consistent with $p<\tilde p=0.6$.

### 1.7.6 Exercises

1. In ST with $p=0.6$, find expected stock return. **Answer:** $0.6(2)+0.4(0.5)=1.40$, so $40\%$.
2. In RL, what $p$ gives the stock a real return of exactly $5\%$? **Answer:** $1.10p+0.90(1-p)=1.05 \Rightarrow 0.20p+0.90=1.05 \Rightarrow p=0.75$.
3. Verify the put's expected return under $\tilde p$ in ST equals $1.25$. **Answer:** $\mathbb E[V_1]=0.5(0)+0.5(3)=1.5$. $V_0=1.20$. Ratio $1.25$. ✓

---

## §1.8 Worked menagerie: a tour of one-period derivatives

**Punchline.** Every "vanilla" derivative reduces to a payoff pair $(V_u,V_d)$ and is priced by the same single formula. This section is a tour through nine derivatives across both markets — call, put, digital cash, digital asset, forward, straddle, risk-reversal, power, capped call.

**Intuition.** Once the machinery is built, the work is just plugging in payoffs and turning a crank. The instruments differ by their *payoff structure*, not by the pricing method. Each one gives a different shape of payoff diagram; understanding those shapes is most of the trader-intuition you need.

### 1.8.1 Payoff diagrams

![Eight payoff diagrams on a single strip: (1) call, (2) put, (3) cash digital, (4) asset digital, (5) forward, (6) straddle, (7) risk-reversal, (8) power option (quadratic). Each is plotted as $V_1$ versus $S_1$ on a continuous axis (even though in our model only two points of that axis are reached). The two binomial outcomes are marked as colourful dots.](figures/ch01-payoff-strip.png)

### 1.8.2 Each derivative priced in both worlds

**Example 1.8.1 (Call, ST).** Already computed: $V_0=1.20$.

**Example 1.8.2 (Call, RL).** Already computed: $V_0=5.8824$.

**Example 1.8.3 (Put, ST).** $1.20$.

**Example 1.8.4 (Put, RL).** $3.9216$.

**Example 1.8.5 (Cash digital, ST, $K=5$).** $V_0=0.40$.

**Example 1.8.6 (Cash digital, RL, $K=100$).** $V_0=0.5882$.

**Example 1.8.7 (Asset digital, ST, $K=5$).** $V_0=3.20$.

**Example 1.8.8 (Asset digital, RL, $K=100$).** $V_u=110$ (since $110>100$), $V_d=0$ (since $90<100$). $V_0=(0.6\cdot 110+0)/1.02=66/1.02=64.706$.

Note: $\text{Asset digital} - K\cdot\text{Cash digital} = $ Call. ($64.706 - 100(0.5882) = 64.706 - 58.82 = 5.88$, matching the call.) ✓

**Example 1.8.9 (Forward, ST, $K=5$).** $V_0=0$. Fair forward $F=(1+r)S_0=5$.

**Example 1.8.10 (Forward, RL, $K=100$).** $V_0=1.9608$. Fair forward $F=102$.

**Example 1.8.11 (Straddle, ST, $K=4$).** $V_0=2.40$.

**Example 1.8.12 (Straddle, RL, $K=100$).** $V_0=9.8039$. Same as discounted certain payoff because the straddle pays $\$10$ in *both* states.

**Example 1.8.13 (Risk-reversal, ST, $K_C=K_P=5$).** Long call, short put: $(V_u,V_d)=(3,0)-(0,3)=(3,-3)$. Same as the forward. $V_0=0$.

**Example 1.8.14 (Risk-reversal, RL, $K_C=K_P=100$).** $(10,0)-(0,10)=(10,-10)$. $V_0=1.9608$ (= forward at $K=100$).

**Example 1.8.15 (Power option, ST, exp 2).** $V_0=27.20$.

**Example 1.8.16 (Power option, RL, exp 2).** $V_0=10294.12$.

**Example 1.8.17 (Capped call, ST, $K=4, C=6$).** $V_0=0.80$.

**Example 1.8.18 (Capped call, RL, $K=100, C=105$).** $V_0=2.9412$.

### 1.8.3 Master menagerie table

**Table 1.9.** Master menagerie — prices in ST and RL.

| Derivative | $V_0$ (ST) | $V_0$ (RL) |
|:---|---:|---:|
| Call ($K=5$ / $K=100$) | $\phantom{00}1.200$ | $\phantom{0000}5.882$ |
| Put (same) | $\phantom{00}1.200$ | $\phantom{0000}3.922$ |
| Cash digital | $\phantom{00}0.400$ | $\phantom{0000}0.588$ |
| Asset digital | $\phantom{00}3.200$ | $\phantom{000}64.706$ |
| Forward (ATM, $K_F=5/100$) | $\phantom{00}0.000$ | $\phantom{0000}1.961$ |
| Straddle (ATM) | $\phantom{00}2.400$ | $\phantom{0000}9.804$ |
| Risk-reversal (ATM) | $\phantom{00}0.000$ | $\phantom{0000}1.961$ |
| Power option (exp 2) | $27.200$ | $10294.120$ |
| Capped call | $\phantom{00}0.800$ | $\phantom{0000}2.941$ |

### 1.8.4 3-D menagerie price plot

![3-D bar plot: derivative type along the $x$-axis, parameter set (ST or RL) along the $y$-axis, price $V_0$ along the $z$-axis (log scale to accommodate the power option's $10000$). Bars are colour-coded by derivative class — calls/puts blue, digitals orange, forwards green, straddles purple, others gold. The ST world is consistently cheaper because $S_0$ is smaller; RL prices scale roughly proportionally to $S_0$.](figures/ch01-menagerie-3d.png)

### 1.8.5 Exercises

1. Price a straddle struck at $K=5$ in ST. **Answer:** $V_u=|8-5|=3, V_d=|2-5|=3$. $V_0=0.4(6)=2.40$. Same as $K=4$ straddle? Indeed: as long as $K$ is between $d S_0$ and $u S_0$, the straddle pays $|S_1-K|$ which moves linearly across $K$ but the sum $V_u+V_d=(uS_0-K)+(K-dS_0)=(u-d)S_0$ is *independent of $K$*. So all straddles with $K\in[dS_0,uS_0]$ cost the same: $0.4(u-d)S_0=0.4(6)=2.40$.
2. Price a capped call in RL with $K=95, C=110$. **Answer:** Call payoff capped at $C-K=15$: $V_u=\min(\max(110-95,0),15)=15$; $V_d=\min(\max(90-95,0),15)=0$. $V_0=(0.6\cdot 15)/1.02=9/1.02=8.824$.
3. Show power option ST exp 3. **Answer:** $V_u=8^3=512, V_d=2^3=8$. $V_0=0.4(520)=208$.

---

## §1.9 Put–call parity

**Punchline.** For European call and put with the same strike $K$ and expiry,

$$\boxed{C_0 - P_0 \;=\; S_0 - \dfrac{K}{1+r}.}$$

This is a *model-free* identity — it doesn't depend on $u, d$, or $\tilde p$, only on no-arbitrage.

**Intuition.** Look at the payoffs at $t=1$:

- Call: $\max(S_1-K,0)$
- Put: $\max(K-S_1,0)$
- Call − Put = $\max(S_1-K,0)-\max(K-S_1,0) = S_1-K$ (always! — quick check: if $S_1\ge K$, call − put $= (S_1-K)-0=S_1-K$; if $S_1<K$, call − put $= 0-(K-S_1)=S_1-K$).

So "long call, short put" is the same payoff as "long forward struck at $K$". Both must cost the same today. The forward struck at $K$ costs $S_0 - K/(1+r)$ (by §1.3.4 logic), giving the parity.

### 1.9.1 Derivation from no-arbitrage

The portfolio "long one share, short $K/(1+r)$ in bonds" has $t=0$ cost $S_0 - K/(1+r)$ and $t=1$ value $S_1 - K$ in either state.

The portfolio "long one call, short one put" has $t=0$ cost $C_0-P_0$ and $t=1$ value $\max(S_1-K,0)-\max(K-S_1,0)=S_1-K$.

Same $t=1$ payoffs, so same $t=0$ prices: $C_0 - P_0 = S_0 - K/(1+r)$. □

### 1.9.2 Worked verifications

**Example 1.9.1 (ST, $K=5$).** $C_0=P_0=1.20$, so $C_0-P_0=0$. $S_0-K/(1+r) = 4 - 5/1.25 = 4 - 4 = 0$. ✓

**Example 1.9.2 (RL, $K=100$).** $C_0=5.8824, P_0=3.9216$. $C_0-P_0=1.9608$. $S_0-K/(1+r) = 100 - 100/1.02 = 100 - 98.0392 = 1.9608$. ✓

**Example 1.9.3 (RL, $K=95$).** $C_u=\max(110-95,0)=15$, $C_d=\max(90-95,0)=0$, $C_0=(0.6\cdot 15)/1.02 = 8.8235$. $P_u=0$, $P_d=\max(95-90,0)=5$, $P_0=(0.4\cdot 5)/1.02 = 1.9608$. $C-P=6.8627$. RHS: $100-95/1.02=100-93.1373=6.8627$. ✓

**Example 1.9.4 (RL, $K=105$).** $C_u=5, C_d=0, C_0=2.9412$. $P_u=0, P_d=15, P_0=5.8824$. $C-P=-2.9412$. RHS: $100-105/1.02=100-102.9412=-2.9412$. ✓

**Example 1.9.5 (Parity arb).** Suppose RL call is $5.50$ (cheap) but put is $3.92$ (correct). Then $C-P=1.58 < 1.96 =$ RHS. Arbitrage: buy call ($-5.50$), sell put ($+3.92$), short stock ($+100$), lend $98.0392$ ($-98.0392$). Net cash: $-5.50+3.92+100-98.0392 = +0.3808$. At $t=1$, call$-$put $=S_1-100$, plus short stock $-S_1$, plus bond $100$ → net zero in both states. *Pocket $0.38$.*

**Example 1.9.6 (Parity arb, other side).** RL call at $6.50$ (rich): $C-P=2.58>1.96$. Sell call, buy put, long stock, borrow. Pocket $0.62$ today.

### 1.9.3 Stacked payoff diagram

![Stacked payoff: long call $\max(S_1-K,0)$ (blue) plus short put $-\max(K-S_1,0)$ (orange) sums to the forward $S_1-K$ (green dashed line) at every $S_1$. The two binomial outcomes for RL ($S_1=90$ and $S_1=110$) are highlighted. The vertical equality at each point is parity in pictures.](figures/ch01-parity-payoff.png)

### 1.9.4 Parity table

**Table 1.10.** Verification of $C_0-P_0=S_0-K/(1+r)$ in the RL market.

| $K$ | $C_0$ | $P_0$ | $C_0-P_0$ | $S_0-K/(1+r)$ |
|---:|---:|---:|---:|---:|
| $90$ | $11.7647$ | $0.0000$ | $11.7647$ | $11.7647$ |
| $95$ | $8.8235$ | $1.9608$ | $6.8627$ | $6.8627$ |
| $100$ | $5.8824$ | $3.9216$ | $1.9608$ | $1.9608$ |
| $102$ | $4.7059$ | $4.7059$ | $0.0000$ | $0.0000$ |
| $105$ | $2.9412$ | $5.8824$ | $-2.9412$ | $-2.9412$ |
| $110$ | $0.0000$ | $7.8431$ | $-7.8431$ | $-7.8431$ |

Note: $K=102$ is the unique strike at which $C_0=P_0$ — namely the forward price.

### 1.9.5 Exercises

1. In ST, what strike makes $C_0=P_0$? **Answer:** $K=(1+r)S_0=5$.
2. Suppose RL parity is violated by $\$0.50$ (call too expensive). What's the arb? **Answer:** Sell call, buy put, long stock, borrow $K/(1+r)$. Pocket $0.50$ today, zero residual.
3. Derive parity using only the $\tilde p$ formula. **Answer:** $C_0-P_0 = (1/(1+r))\tilde{\mathbb E}[(S_1-K)^+ - (K-S_1)^+] = (1/(1+r))\tilde{\mathbb E}[S_1-K] = (1/(1+r))((1+r)S_0 - K) = S_0 - K/(1+r)$. ✓

---

## §1.10 Hedging in practice: the dealer's $\Delta$ position

**Punchline.** A dealer who *sells* a call at the fair price $V_0$ and *immediately* buys $\Delta$ shares (financing the difference $\Delta S_0 - V_0$ by borrowing) has zero net cash at $t=0$ and zero net P/L in both states at $t=1$. That's what hedging *does*.

**Intuition.** Selling an option is taking on a random liability. The market wants the option but doesn't want the random liability — so the dealer takes on the random liability, charges the fair price, and then offsets the randomness with a stock hedge. The hedge is *exactly* the $\Delta$ from §1.3 — that's why $\Delta$ is also called the "hedge ratio." The bond financing makes the books balance at $t=0$. After $t=1$, the dealer is flat (in this single-period model — in multi-period models the hedge must be rebalanced).

### 1.10.1 The dealer's t=0 actions

After agreeing to sell a derivative with payoff $(V_u, V_d)$:

1. Receive $V_0$ in cash from the buyer.
2. Buy $\Delta$ shares at $S_0$ (spend $\Delta S_0$).
3. Borrow or lend the difference in the bond. The amount in the bond is $B = V_0 - \Delta S_0$ (positive if you over-collateralised, negative if you needed to borrow).

The dealer's bond *position* (positive for lending, negative for borrowing) is exactly $B$ — the $B$ from the replication formula. So:

- $t=0$ inflows: $V_0$ (from option sale).
- $t=0$ outflows: $\Delta S_0$ (stock purchase).
- $t=0$ bond entry: $V_0 - \Delta S_0 = B$ (residual cash goes into the bond — positive if it's a deposit, negative if it's a borrow).

Net cash at $t=0$: $V_0 - \Delta S_0 - B = 0$ since $B = V_0 - \Delta S_0$. ✓

At $t=1$:

- Stock position worth $\Delta S_1$.
- Bond position grows to $B(1+r)$.
- Pay out $V_1$ to option buyer.

Net at $t=1$: $\Delta S_1 + B(1+r) - V_1$. By replication this is $V_1 - V_1 = 0$ in both states. *Hedge works perfectly.*

### 1.10.2 ST call dealer ledger

**Example 1.10.1 (ST call, dealer ledger).** Sell call $K=5$ at $V_0=1.20$. Hedge: $\Delta=0.5, B=-0.80$.

| Time | State | Receive | Stock | Bond | Payoff | Total |
|:---:|:---:|---:|---:|---:|---:|---:|
| $t=0$ | | $+1.20$ | $-2.00$ | $+0.80$ | $0.00$ | $\mathbf{0.00}$ |
| $t=1$ | $H$ | | $+4.00$ | $-1.00$ | $-3.00$ | $\mathbf{0.00}$ |
| $t=1$ | $T$ | | $+1.00$ | $-1.00$ | $0.00$ | $\mathbf{0.00}$ |

*Legend.* Bond column: $t=0$ entry is a borrow ($+0.80$ in cash); $t=1$ entry is the repayment. Stock column: $t=0$ entry is the purchase of $\Delta = 0.5$ shares; $t=1$ entry is sale at the realised price. Blank Receive at $t=1$: option premium was received only at $t=0$.

**Example 1.10.2 (RL call, dealer ledger).** Sell call $K=100$ at $V_0=5.8824$. Hedge: $\Delta=0.5, B=-44.1176$.

| Time | State | Receive | Stock | Bond | Payoff | Total |
|:---:|:---:|---:|---:|---:|---:|---:|
| $t=0$ | | $+5.8824$ | $-50.0000$ | $+44.1176$ | $0.0000$ | $\mathbf{0.0000}$ |
| $t=1$ | $H$ | | $+55.0000$ | $-45.0000$ | $-10.0000$ | $\mathbf{0.0000}$ |
| $t=1$ | $T$ | | $+45.0000$ | $-45.0000$ | $0.0000$ | $\mathbf{0.0000}$ |

*Legend.* Same conventions as Example 1.10.1; bond at $t=0$ is a borrow of $44.1176$, repaid at $t=1$ as $-45.0000$.

Perfect hedge.

### 1.10.3 Mispriced sale arbitrage

**Example 1.10.3 (Dealer sells at $V^{\text{mkt}}=6.50$, hedges).** Same $\Delta=0.5$.

- $t=0$: $+6.50 - 50 + 44.1176 = +0.6176$ (pocketed).
- $t=1$, both states: $0$ (hedge works).

The dealer pockets the spread risk-free. (If she could also charge the buyer extra for the privilege, the spread is hers; if a competitor undercuts, the spread collapses to zero — which is why bid-ask spreads in liquid options markets are tight.)

### 1.10.4 Unhedged dealer

**Example 1.10.4 (ST call, dealer unhedged).** Sells call at $V_0=1.20$, does *not* buy stock. Lend the $1.20$ instead.

- $t=0$: $+1.20$ receive, $-1.20$ lend, $= 0$.
- $t=1$, $H$: $+1.50$ (bond), $-3$ (payoff) $= -1.50$. *Loss of $1.50$.*
- $t=1$, $T$: $+1.50$ (bond), $0$ (payoff) $= +1.50$. *Gain of $1.50$.*

Symmetric P/L: dealer wins half the time, loses half the time. The *expected* P/L under $\tilde p$ is zero (since the option was priced fairly), but the *variance* is large. A risk-averse dealer would never run this strategy.

### 1.10.5 Bid-ask collapse

**Example 1.10.5 (Bid-ask).** Two dealers both know the fair price is $5.8824$. Dealer A quotes $5.85$ bid, $5.95$ ask (a $0.10$-wide market). Dealer B quotes $5.86$ bid, $5.94$ ask. Whoever wants to buy goes to B (lower ask); whoever wants to sell goes to B (higher bid). Dealer A loses business and tightens to $5.87/5.93$. The spread keeps tightening until the marginal cost (capital, hedging slippage) equals the spread. In a perfect frictionless market, the spread collapses to *zero*.

### 1.10.6 Mis-hedge basis risk

**Example 1.10.6 (Mis-hedge).** Dealer thinks $\Delta=0.4$ instead of the correct $0.5$. Buys $0.4$ shares, lends $1.20 - 0.4(4) = 1.20 - 1.60 = -0.40$ (i.e., borrows $0.40$).

- $t=0$: $0$. ✓
- $t=1$ $H$: $0.4(8) - 0.4(1.25) - 3 = 3.2 - 0.5 - 3 = -0.3$. Loss.
- $t=1$ $T$: $0.4(2) - 0.5 - 0 = +0.3$. Gain.

Mis-hedge of size $0.1$ in $\Delta$ produces P/L of magnitude $|0.1\cdot (uS_0-dS_0)| = 0.1\cdot 6 = 0.6$, halved between states because the bond absorbed half. That's *delta-hedge slippage*: the cost of getting the hedge ratio wrong.

### 1.10.7 Dealer P/L visualisation

![Two-panel bar chart of dealer P/L. Left: *hedged* — bars at zero in both $H$ and $T$ states. Right: *unhedged* — bars at $-1.50$ in $H$ and $+1.50$ in $T$ (ST call example). The hedged dealer has eliminated all randomness; the unhedged dealer's P/L is fully exposed to the coin.](figures/ch01-dealer-pl.png)

### 1.10.8 Dealer ledger summary

**Table 1.11.** Dealer ledger for RL call sold at fair price $5.8824$, with $\Delta=0.5, B=-44.1176$.

| Line | $t=0$ | $t=1, H$ | $t=1, T$ |
|:---|---:|---:|---:|
| Option sale | $+5.8824$ | $-10.0000$ | $0.0000$ |
| Stock ($\Delta=0.5$) | $-50.0000$ | $+55.0000$ | $+45.0000$ |
| Bond ($B=-44.1176$) | $+44.1176$ | $-45.0000$ | $-45.0000$ |
| **Net** | $\mathbf{0.0000}$ | $\mathbf{0.0000}$ | $\mathbf{0.0000}$ |

Every row tells the same story: the option's randomness is fully absorbed by the stock leg; the bond leg pays for the stock; the option premium funds both. Zero everywhere.

### 1.10.9 Exercises

1. ST put dealer ledger. **Answer:** Receive $1.20$, sell short $0.5$ shares ($+2.00$), lend $3.20$ ($-3.20$): net $0$. At $t=1$ $H$: buy back stock $-4$, bond $+4$, pay $0$: net $0$. ✓ At $t=1$ $T$: buy back $-1$, bond $+4$, pay $3$: net $0$. ✓
2. RL straddle dealer (sold at $9.8039$). **Answer:** $\Delta=0$. Lend the entire premium $9.8039$. At $t=1$: bond pays $10$, pay $10$ to buyer. Net $0$ in both states.
3. Mis-hedged ST put with $\Delta=-0.4$ instead of $-0.5$. **Answer:** Similar to 1.10.6 but for put — P/L oscillates by $0.3$ in each state.

---

## Bridge to Chapter 2

One period was a finger exercise. Real markets last more than one toss, and the *path* the price takes matters as much as where it ends up. Chapter 2 glues single-period nodes into a tree: at each node, the same 2×2 system from §0.11 produces a $(\Delta,B)$ and a price; we just apply it backward from the leaves. Risk-neutral pricing becomes *iterated expectation* via the tower property of §0.5. Replication becomes *dynamic hedging*: rebalance at every node. The Toy will go from $S_0=4$ to a 16-leaf binary tree at $n=4$, and the realistic market will start to converge — over hundreds of periods, with $u$ and $d$ shrinking toward $1$ — to a smooth log-normal world that, in Chapter 6, becomes Black–Scholes.
