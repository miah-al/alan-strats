"""
Figure generator for the quant guide chapters.
Run:  python docs/guide/build_figures.py
Writes all PNGs under docs/guide/figures/.
"""
from __future__ import annotations
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch

FIG = os.path.join(os.path.dirname(__file__), "figures")
os.makedirs(FIG, exist_ok=True)

DPI = 140
plt.rcParams.update({
    "figure.facecolor": "white",
    "axes.grid": True,
    "grid.alpha": 0.3,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "font.size": 11,
})


def save(name: str):
    path = os.path.join(FIG, name)
    plt.savefig(path, dpi=DPI, bbox_inches="tight")
    plt.close()
    print(f"  wrote {name}")


# ────────────────────────────────────────────────────────────
# CH01 — One-Period Binomial
# ────────────────────────────────────────────────────────────
def ch01():
    print("CH01:")
    # (a) one-period binomial tree
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot([0, 1], [0, 1], "o-", color="#2a62a6", lw=2)
    ax.plot([0, 1], [0, -1], "o-", color="#2a62a6", lw=2)
    ax.annotate(r"$S_0$", (0, 0), xytext=(-0.08, 0.05), fontsize=14)
    ax.annotate(r"$S_u = uS_0$", (1, 1), xytext=(1.02, 0.95), fontsize=12, color="#1f7a1f")
    ax.annotate(r"$S_d = dS_0$", (1, -1), xytext=(1.02, -1.05), fontsize=12, color="#a62a2a")
    ax.text(0.45, 0.6, r"$q$", fontsize=13, color="#1f7a1f")
    ax.text(0.45, -0.6, r"$1-q$", fontsize=13, color="#a62a2a")
    ax.set_xticks([]); ax.set_yticks([])
    ax.set_title("One-period binomial tree"); ax.set_xlim(-0.2, 1.5); ax.set_ylim(-1.4, 1.4)
    ax.grid(False)
    save("ch01-tree.png")

    # (b) call/put payoff
    K = 100
    S = np.linspace(60, 140, 200)
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(S, np.maximum(S - K, 0), lw=2, color="#1f7a1f", label="Call payoff $(S-K)^+$")
    ax.plot(S, np.maximum(K - S, 0), lw=2, color="#a62a2a", label="Put payoff $(K-S)^+$")
    ax.axvline(K, ls=":", color="black", alpha=0.5, label=f"Strike K={K}")
    ax.set_xlabel("Spot $S_T$"); ax.set_ylabel("Payoff")
    ax.set_title("European call & put payoffs"); ax.legend()
    save("ch01-payoff.png")

    # (c) no-arbitrage region: d < 1+r < u
    r_grid = np.linspace(0, 0.3, 100)
    u_grid = 1 + r_grid + 0.1
    d_grid = 1 + r_grid - 0.1
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(r_grid, u_grid, label=r"$u = 1+r+0.1$ (upper)", color="#1f7a1f")
    ax.plot(r_grid, d_grid, label=r"$d = 1+r-0.1$ (lower)", color="#a62a2a")
    ax.plot(r_grid, 1 + r_grid, ":", color="black", label=r"$1+r$ (must sit between)")
    ax.fill_between(r_grid, d_grid, u_grid, alpha=0.15, color="#2a62a6", label="No-arbitrage band")
    ax.set_xlabel("risk-free rate $r$"); ax.set_ylabel("tree multipliers")
    ax.set_title(r"No-arbitrage requires $d < 1+r < u$"); ax.legend()
    save("ch01-arbitrage-region.png")


# ────────────────────────────────────────────────────────────
# CH02 — Review & Uniqueness
# ────────────────────────────────────────────────────────────
def ch02():
    print("CH02:")
    # (a) trinomial tree — non-uniqueness of Q
    fig, ax = plt.subplots(figsize=(7, 4))
    endpoints = [(1, 1), (1, 0), (1, -1)]
    labels = [r"$S_u$", r"$S_m$", r"$S_d$"]
    colors = ["#1f7a1f", "#2a62a6", "#a62a2a"]
    for (x, y), lab, c in zip(endpoints, labels, colors):
        ax.plot([0, x], [0, y], "o-", color=c, lw=2)
        ax.annotate(lab, (x, y), xytext=(x+0.05, y), fontsize=12, color=c)
    ax.annotate(r"$S_0$", (0, 0), xytext=(-0.1, 0.05), fontsize=13)
    ax.text(0.5, 0.6, r"$q_u$", fontsize=11, color="#1f7a1f")
    ax.text(0.5, 0.05, r"$q_m$", fontsize=11, color="#2a62a6")
    ax.text(0.5, -0.6, r"$q_d$", fontsize=11, color="#a62a2a")
    ax.set_title(r"Trinomial tree — 1-D constraint leaves $Q$ non-unique")
    ax.set_xticks([]); ax.set_yticks([]); ax.grid(False)
    ax.set_xlim(-0.2, 1.5); ax.set_ylim(-1.4, 1.4)
    save("ch02-trinomial.png")

    # (b) Black-Scholes price surface
    S = np.linspace(60, 140, 80); T = np.linspace(0.05, 1.5, 80)
    SS, TT = np.meshgrid(S, T)
    from scipy.stats import norm
    K, r, sig = 100, 0.05, 0.2
    d1 = (np.log(SS/K) + (r + 0.5*sig**2)*TT) / (sig*np.sqrt(TT))
    d2 = d1 - sig*np.sqrt(TT)
    C = SS*norm.cdf(d1) - K*np.exp(-r*TT)*norm.cdf(d2)
    fig = plt.figure(figsize=(8, 5))
    ax = fig.add_subplot(111, projection="3d")
    ax.plot_surface(SS, TT, C, cmap="viridis", alpha=0.85, edgecolor="none")
    ax.set_xlabel("Spot S"); ax.set_ylabel("T (yrs)"); ax.set_zlabel("Call price")
    ax.set_title("Black-Scholes European call: $C(S, T)$")
    save("ch02-bs-surface.png")

    # (c) American vs European exercise region
    fig, ax = plt.subplots(figsize=(7, 4))
    T = np.linspace(0, 1, 100)
    early_boundary = 100 * (0.55 + 0.35 * np.sqrt(T))   # illustrative concave-up
    ax.fill_between(T, 0, early_boundary, alpha=0.25, color="#a62a2a", label="Early-exercise region (American put)")
    ax.plot(T, early_boundary, lw=2, color="#a62a2a")
    ax.axhline(100, ls=":", color="black", label=r"Strike K=100")
    ax.set_xlabel("Time $t$"); ax.set_ylabel("Spot S")
    ax.set_title("American put — early-exercise boundary $S^*(t)$"); ax.legend()
    ax.invert_xaxis()
    save("ch02-american-exercise.png")


# ────────────────────────────────────────────────────────────
# CH03 — Measure Changes
# ────────────────────────────────────────────────────────────
def ch03():
    print("CH03:")
    # (a) two-state asset price table (visual)
    states = ["ω₁", "ω₂", "ω₃", "ω₄", "ω₅"]
    A = [5, 10, 20, 65, 30]
    B = [80, 81, 20, 90, 3]
    x = np.arange(len(states))
    width = 0.35
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(x - width/2, A, width, label="Asset A", color="#2a62a6")
    ax.bar(x + width/2, B, width, label="Asset B", color="#e07a2a")
    ax.set_xticks(x); ax.set_xticklabels(states)
    ax.set_ylabel("Price ($)")
    ax.set_title("Two-asset state prices (Ch 3 example)")
    ax.legend()
    save("ch03-asset-states.png")

    # (b) Radon-Nikodym density across states (ratio B/A as numeraire)
    ratio = np.array(B) / np.array(A)
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(states, ratio, color="#6a3a8a")
    ax.set_ylabel(r"$dQ^{(B)}/dQ^{(A)} \propto B/A$")
    ax.set_title("Radon-Nikodym density: ratio of numeraires across states")
    save("ch03-rn-density.png")

    # (c) Itô isometry — A + B + C matrix decomposition
    #     Visualises the proof in §3.6: the n×n grid of E[g h ΔW_k ΔW_j]
    #     splits into A (lower triangle, k<j), B (upper triangle, j<k),
    #     C (diagonal, k=j).  E[A]=E[B]=0 by independence of fresh increments;
    #     only C survives and gives the isometry.
    n = 6
    fig, ax = plt.subplots(figsize=(7.5, 7.5))
    for i in range(n):
        for j in range(n):
            if i == j:
                color = "#fde68a"      # diagonal C — yellow highlight
                label = "C"
            elif j > i:
                color = "#bfdbfe"      # upper triangle B — light blue
                label = "B"
            else:
                color = "#fecaca"      # lower triangle A — light red
                label = "A"
            ax.add_patch(plt.Rectangle((j, n-1-i), 1, 1,
                                        facecolor=color, edgecolor="black", lw=1.1))
            ax.text(j+0.5, n-1-i+0.5, label, ha="center", va="center",
                    fontsize=13, fontweight="bold", color="#333")
    # Axis labels
    for k in range(n):
        ax.text(k+0.5, -0.35, f"$k={k+1}$", ha="center", va="top", fontsize=11)
        ax.text(-0.25, n-1-k+0.5, f"$j={k+1}$", ha="right", va="center", fontsize=11)
    # Legend-style annotations
    ax.text(n+0.4, n-0.5, r"C (diagonal, $k=j$):", fontsize=11.5, color="#8a6508")
    ax.text(n+0.4, n-1.0, r"$\sum_k g_{k-1} h_{k-1} (\Delta W_k)^2$",
            fontsize=11, color="#8a6508")
    ax.text(n+0.4, n-1.9, r"A (lower, $k<j$):  $\mathbb{E}[A]=0$",
            fontsize=11.5, color="#a33030")
    ax.text(n+0.4, n-2.3, r"via $\mathbb{E}[\Delta W_j]=0$, $j$ future",
            fontsize=10.5, color="#a33030")
    ax.text(n+0.4, n-3.2, r"B (upper, $j<k$):  $\mathbb{E}[B]=0$",
            fontsize=11.5, color="#1e5fa8")
    ax.text(n+0.4, n-3.6, r"via $\mathbb{E}[\Delta W_k]=0$, $k$ future",
            fontsize=10.5, color="#1e5fa8")
    ax.text(n+0.4, n-4.7, r"$\therefore \mathbb{E}\left[\left(\int g\,dW\right)\left(\int h\,dW\right)\right]$",
            fontsize=12, color="black")
    ax.text(n+0.4, n-5.1, r"$= \mathbb{E}\!\int g h\,ds$",
            fontsize=12, color="black")
    ax.set_xlim(-1, n+6.5); ax.set_ylim(-1, n+0.5)
    ax.set_aspect("equal")
    ax.set_xticks([]); ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.grid(False)
    ax.set_title(r"Itô isometry: the A + B + C decomposition of $\sum_{j,k} g_{k-1} h_{j-1}\,\Delta W_k\,\Delta W_j$",
                 fontsize=12, pad=12)
    save("ch03-ito-isometry-proof.png")


# ────────────────────────────────────────────────────────────
# CH04 — Calibration
# ────────────────────────────────────────────────────────────
def ch04():
    print("CH04:")
    # (a) Vasicek yield curve
    kappa, theta, sigma = 0.3, 0.05, 0.015
    r0 = 0.04
    T = np.linspace(0.1, 30, 120)
    def B(t, T, k): return (1 - np.exp(-k*(T-t))) / k
    def A(t, T, k, th, sg):
        Bv = B(t, T, k)
        return np.exp((th - sg**2/(2*k**2)) * (Bv - (T-t)) - sg**2/(4*k) * Bv**2)
    P = A(0, T, kappa, theta, sigma) * np.exp(-B(0, T, kappa) * r0)
    y = -np.log(P) / T
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(T, y*100, lw=2, color="#2a62a6")
    ax.axhline(theta*100, ls=":", color="black", label=r"long-run mean $\theta$")
    ax.set_xlabel("Maturity T (y)"); ax.set_ylabel("Zero rate (%)")
    ax.set_title(r"Vasicek yield curve: $r_0=4\%$, $\theta=5\%$, $\kappa=0.3$")
    ax.legend(); save("ch04-vasicek-yield.png")

    # (b) fit residuals — made up market vs model
    T_mkt = np.array([0.5, 1, 2, 3, 5, 7, 10, 20, 30])
    y_mkt = np.array([4.1, 4.2, 4.35, 4.4, 4.42, 4.45, 4.5, 4.55, 4.55]) / 100
    y_mod = -np.log(A(0, T_mkt, kappa, theta, sigma) * np.exp(-B(0, T_mkt, kappa) * r0)) / T_mkt
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(T_mkt, y_mkt*100, "o-", label="Market", color="#1f7a1f")
    ax.plot(T_mkt, y_mod*100, "s--", label="Vasicek model", color="#a62a2a")
    ax.set_xlabel("Tenor (y)"); ax.set_ylabel("Zero rate (%)")
    ax.set_title("Calibration: market vs Vasicek fit")
    ax.legend()
    save("ch04-calibration-fit.png")


# ────────────────────────────────────────────────────────────
# CH05 — Extended Vasicek / Hull-White
# ────────────────────────────────────────────────────────────
def ch05():
    print("CH05:")
    # (a) Radon-Nikodym bell-curve transformation P -> Q
    #     Under P: W_T ~ N(0, T).   Under Q (after Girsanov shift by -theta):
    #     W_T has mean -theta*T.   dQ/dP = exp(theta*W_T - 0.5*theta^2*T).
    T_rn, theta = 1.0, 0.8
    x = np.linspace(-4, 4, 400)
    p_density = np.exp(-0.5 * x**2 / T_rn) / np.sqrt(2*np.pi*T_rn)
    q_density = np.exp(-0.5 * (x + theta*T_rn)**2 / T_rn) / np.sqrt(2*np.pi*T_rn)
    fig, ax = plt.subplots(figsize=(7.5, 4))
    ax.plot(x, p_density, lw=2.2, color="#2a62a6",
            label=r"$P$-density of $W_T$ (mean $0$)")
    ax.plot(x, q_density, lw=2.2, color="#a62a2a",
            label=fr"$Q$-density of $W_T$ (mean $-\theta T = -{theta*T_rn:.2g}$)")
    ax.fill_between(x, p_density, alpha=0.12, color="#2a62a6")
    ax.fill_between(x, q_density, alpha=0.12, color="#a62a2a")
    ax.axvline(0, ls=":", color="#2a62a6", alpha=0.7)
    ax.axvline(-theta*T_rn, ls=":", color="#a62a2a", alpha=0.7)
    ax.annotate("", xy=(-theta*T_rn, 0.1), xytext=(0, 0.1),
                arrowprops=dict(arrowstyle="->", color="black", lw=1.4))
    ax.text(-theta*T_rn/2, 0.115, r"Girsanov shift $-\theta T$",
            ha="center", fontsize=10)
    ax.set_xlabel(r"$W_T$"); ax.set_ylabel("Density")
    ax.set_title(r"Radon-Nikodym $P \to Q$: bell-curve transformation")
    ax.legend(loc="upper right")
    save("ch05-rn-densities.png")

    # (b) The Radon-Nikodym derivative dQ/dP as a function of W_T
    Z = np.exp(theta * x - 0.5 * theta**2 * T_rn)
    fig, ax = plt.subplots(figsize=(7.5, 4))
    ax.plot(x, Z, lw=2.4, color="#6a2ea6")
    ax.axhline(1.0, ls=":", color="black", alpha=0.6)
    ax.fill_between(x, 1.0, Z, where=(Z >= 1), alpha=0.15, color="#2a8a2a",
                    label=r"$dQ/dP > 1$: upweighted under $Q$")
    ax.fill_between(x, Z, 1.0, where=(Z < 1), alpha=0.15, color="#a62a2a",
                    label=r"$dQ/dP < 1$: downweighted under $Q$")
    ax.set_xlabel(r"$W_T$"); ax.set_ylabel(r"$dQ/dP$")
    ax.set_yscale("log")
    ax.set_title(r"Radon-Nikodym derivative $dQ/dP = \exp(\theta W_T - \frac{1}{2}\theta^2 T)$")
    ax.legend(loc="upper left")
    save("ch05-rn-derivative.png")

    # (c) Hull-White simulated short-rate paths
    rng = np.random.default_rng(42)
    n_paths, n_steps, T = 8, 500, 10
    dt = T / n_steps
    kappa, theta_const, sigma = 0.2, 0.05, 0.012
    r = np.zeros((n_paths, n_steps+1)); r[:, 0] = 0.04
    for t in range(n_steps):
        r[:, t+1] = r[:, t] + kappa*(theta_const - r[:, t])*dt + sigma*np.sqrt(dt)*rng.standard_normal(n_paths)
    times = np.linspace(0, T, n_steps+1)
    fig, ax = plt.subplots(figsize=(7, 4))
    for i in range(n_paths):
        ax.plot(times, r[i]*100, alpha=0.7, lw=1)
    ax.axhline(theta_const*100, ls=":", color="black", label=r"$\theta=5\%$")
    ax.set_xlabel("Time (y)"); ax.set_ylabel("Short rate (%)")
    ax.set_title("Hull-White simulated short-rate paths"); ax.legend()
    save("ch05-hw-paths.png")

    # (b) ZCB term structure from HW
    T_grid = np.linspace(0.5, 30, 60)
    B_arr = (1 - np.exp(-kappa*T_grid)) / kappa
    P = np.exp(-B_arr * 0.04)   # simplified
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(T_grid, P, lw=2, color="#2a62a6")
    ax.set_xlabel("Maturity T (y)"); ax.set_ylabel(r"$P(0, T)$")
    ax.set_title("ZCB discount curve from Hull-White")
    save("ch05-zcb-curve.png")


# ────────────────────────────────────────────────────────────
# CH06 — Dynamic Hedging
# ────────────────────────────────────────────────────────────
def ch06():
    print("CH06:")
    # (a) delta-hedge error vs rebalance frequency (MC)
    rng = np.random.default_rng(42)
    S0, K, T, r, sig = 100, 100, 0.25, 0.05, 0.2
    from scipy.stats import norm
    freqs = [5, 10, 25, 50, 100, 200, 500]
    mae = []
    n_paths = 2000
    for n in freqs:
        dt = T / n
        S = np.full(n_paths, S0)
        cash = np.zeros(n_paths)
        # initial delta
        d1 = (np.log(S/K) + (r + 0.5*sig**2)*T) / (sig*np.sqrt(T))
        delta = norm.cdf(d1)
        cash = -delta * S
        for step in range(1, n+1):
            t_rem = T - step * dt
            Z = rng.standard_normal(n_paths)
            S = S * np.exp((r - 0.5*sig**2)*dt + sig*np.sqrt(dt)*Z)
            cash *= np.exp(r*dt)
            if t_rem > 1e-6:
                d1 = (np.log(S/K) + (r + 0.5*sig**2)*t_rem) / (sig*np.sqrt(t_rem))
                new_d = norm.cdf(d1)
                cash -= (new_d - delta) * S
                delta = new_d
        pnl = delta * S + cash - np.maximum(S - K, 0)
        mae.append(np.std(pnl))
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.loglog(freqs, mae, "o-", color="#2a62a6")
    ax.set_xlabel("Rebalances over life"); ax.set_ylabel("Stdev of hedging P&L")
    ax.set_title("Discrete-hedging error shrinks like $\\sqrt{\\Delta t}$")
    save("ch06-hedge-error.png")

    # (b) BS price & delta curves
    S = np.linspace(50, 150, 100)
    d1 = (np.log(S/100) + (0.05 + 0.5*0.04)*0.5) / (0.2*np.sqrt(0.5))
    d2 = d1 - 0.2*np.sqrt(0.5)
    C = S*norm.cdf(d1) - 100*np.exp(-0.05*0.5)*norm.cdf(d2)
    delta = norm.cdf(d1)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))
    ax1.plot(S, C, lw=2, color="#1f7a1f"); ax1.set_xlabel("Spot"); ax1.set_ylabel("Call price"); ax1.set_title("BS call price $C(S)$")
    ax2.plot(S, delta, lw=2, color="#2a62a6"); ax2.set_xlabel("Spot"); ax2.set_ylabel(r"$\Delta = \partial C/\partial S$"); ax2.set_title("Call delta")
    plt.tight_layout()
    save("ch06-price-delta.png")


# ────────────────────────────────────────────────────────────
# CH07 — VaR & Delta-Gamma Hedging
# ────────────────────────────────────────────────────────────
def ch07():
    print("CH07:")
    # (a) loss distribution with VaR & CTE marked
    rng = np.random.default_rng(7)
    losses = rng.standard_normal(50_000) * 0.02 - 0.005
    losses = np.sort(losses)
    var_95 = np.percentile(losses, 95)
    cte_95 = losses[losses >= var_95].mean()
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.hist(losses, bins=80, color="#2a62a6", alpha=0.6)
    ax.axvline(var_95, color="#e07a2a", lw=2, label=f"VaR 95% = {var_95:.3f}")
    ax.axvline(cte_95, color="#a62a2a", lw=2, label=f"CTE 95% = {cte_95:.3f}")
    ax.set_xlabel("1-day return (loss)"); ax.set_ylabel("count")
    ax.set_title("Loss distribution with VaR and CTE"); ax.legend()
    save("ch07-var-cte.png")

    # (b) delta-only vs delta-gamma P&L
    from scipy.stats import norm
    S0, K, T, r, sig = 100, 100, 0.5, 0.05, 0.2
    S_shock = np.linspace(70, 130, 200)
    d1 = (np.log(S0/K) + (r + 0.5*sig**2)*T) / (sig*np.sqrt(T))
    d2 = d1 - sig*np.sqrt(T)
    delta = norm.cdf(d1); gamma = norm.pdf(d1)/(S0*sig*np.sqrt(T))
    C0 = S0*norm.cdf(d1) - K*np.exp(-r*T)*norm.cdf(d2)
    # true new option price
    d1n = (np.log(S_shock/K) + (r + 0.5*sig**2)*T) / (sig*np.sqrt(T))
    d2n = d1n - sig*np.sqrt(T)
    Cn = S_shock*norm.cdf(d1n) - K*np.exp(-r*T)*norm.cdf(d2n)
    dS = S_shock - S0
    pnl_delta = delta*dS - (Cn - C0)
    pnl_dg    = delta*dS + 0.5*gamma*dS**2 - (Cn - C0)
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(S_shock, pnl_delta, lw=2, color="#a62a2a", label="Delta-only hedge error")
    ax.plot(S_shock, pnl_dg,    lw=2, color="#1f7a1f", label="Delta-Gamma hedge error")
    ax.axhline(0, color="black", lw=0.5); ax.axvline(S0, ls=":", color="black", alpha=0.5)
    ax.set_xlabel("Stock price after shock"); ax.set_ylabel("Hedge P&L error")
    ax.set_title("Delta-only vs Delta-Gamma hedge residual"); ax.legend()
    save("ch07-dg-hedge.png")


# ────────────────────────────────────────────────────────────
# CH08 — Feynman-Kac
# ────────────────────────────────────────────────────────────
def ch08():
    print("CH08:")
    from scipy.stats import norm
    S0, K, T, r, sig = 100, 100, 1.0, 0.05, 0.2
    rng = np.random.default_rng(42)

    # (a) MC expectation → BS price convergence
    n_trials = np.logspace(1, 4, 40).astype(int)
    prices = []
    for n in n_trials:
        z = rng.standard_normal(n)
        ST = S0 * np.exp((r - 0.5*sig**2)*T + sig*np.sqrt(T)*z)
        prices.append(np.mean(np.maximum(ST - K, 0)) * np.exp(-r*T))
    d1 = (np.log(S0/K) + (r + 0.5*sig**2)*T) / (sig*np.sqrt(T))
    d2 = d1 - sig*np.sqrt(T)
    bs = S0*norm.cdf(d1) - K*np.exp(-r*T)*norm.cdf(d2)
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.semilogx(n_trials, prices, "o-", color="#2a62a6", alpha=0.7, label="MC estimate")
    ax.axhline(bs, ls=":", color="#a62a2a", label=f"BS = {bs:.3f}")
    ax.set_xlabel("# MC paths"); ax.set_ylabel("Call price estimate")
    ax.set_title("Feynman-Kac: MC expectation → PDE solution"); ax.legend()
    save("ch08-mc-convergence.png")

    # (b) PDE surface with terminal payoff highlighted
    S = np.linspace(50, 150, 80); T_g = np.linspace(0, 1, 80)
    SS, TT = np.meshgrid(S, T_g)
    d1 = (np.log(SS/K) + (r + 0.5*sig**2)*(1-TT)) / (sig*np.sqrt(np.maximum(1-TT, 1e-6)))
    d2 = d1 - sig*np.sqrt(np.maximum(1-TT, 1e-6))
    C = np.where(TT < 1-1e-6,
                 SS*norm.cdf(d1) - K*np.exp(-r*(1-TT))*norm.cdf(d2),
                 np.maximum(SS - K, 0))
    fig = plt.figure(figsize=(8, 5))
    ax = fig.add_subplot(111, projection="3d")
    ax.plot_surface(SS, TT, C, cmap="viridis", alpha=0.8, edgecolor="none")
    ax.plot(S, np.ones_like(S), np.maximum(S - K, 0), color="#a62a2a", lw=3, label="Terminal payoff")
    ax.set_xlabel("S"); ax.set_ylabel("t"); ax.set_zlabel("V(S,t)")
    ax.set_title("F-K solution $v(t,S)$ with terminal condition"); ax.legend()
    save("ch08-pde-surface.png")


# ────────────────────────────────────────────────────────────
# CH09 — Futures Contracts
# ────────────────────────────────────────────────────────────
def ch09():
    print("CH09:")
    # (a) forward price term structure (flat carry)
    S0 = 100
    T = np.linspace(0, 2, 60)
    F_low = S0 * np.exp(0.02 * T)   # r-q = 2%
    F_high= S0 * np.exp(0.06 * T)   # r-q = 6%
    F_neg = S0 * np.exp(-0.02* T)   # backwardation
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(T, F_low, label="r-q = 2% (contango)", color="#2a62a6")
    ax.plot(T, F_high, label="r-q = 6%", color="#e07a2a")
    ax.plot(T, F_neg, label="r-q = -2% (backwardation)", color="#a62a2a")
    ax.set_xlabel("T (y)"); ax.set_ylabel("F(0,T)")
    ax.set_title("Forward price term structure")
    ax.legend(); save("ch09-forward-term.png")

    # (b) Margrabe payoff surface max(S1 - S2, 0)
    S1 = np.linspace(60, 140, 80); S2 = np.linspace(60, 140, 80)
    SS1, SS2 = np.meshgrid(S1, S2)
    payoff = np.maximum(SS1 - SS2, 0)
    fig = plt.figure(figsize=(8, 5))
    ax = fig.add_subplot(111, projection="3d")
    ax.plot_surface(SS1, SS2, payoff, cmap="viridis", alpha=0.85, edgecolor="none")
    ax.set_xlabel("$S_1$"); ax.set_ylabel("$S_2$"); ax.set_zlabel("Payoff")
    ax.set_title(r"Margrabe exchange option payoff $(S_1-S_2)^+$")
    save("ch09-margrabe.png")


# ────────────────────────────────────────────────────────────
# CH10 — Heston
# ────────────────────────────────────────────────────────────
def ch10():
    print("CH10:")
    from scipy.stats import norm

    # (a) Heston-vs-BS smile via MC
    rng = np.random.default_rng(42)
    S0, T, r = 100, 1.0, 0.02
    kappa, theta, sigma_v, rho, v0 = 2.0, 0.04, 0.5, -0.7, 0.04
    n_paths, n_steps = 20000, 200
    dt = T / n_steps
    S = np.full(n_paths, S0); v = np.full(n_paths, v0)
    for _ in range(n_steps):
        z1 = rng.standard_normal(n_paths); z2 = rng.standard_normal(n_paths)
        w1 = z1; w2 = rho*z1 + np.sqrt(1-rho**2)*z2
        v_pos = np.maximum(v, 0)
        S = S * np.exp((r - 0.5*v_pos)*dt + np.sqrt(v_pos*dt)*w1)
        v = v + kappa*(theta - v_pos)*dt + sigma_v*np.sqrt(v_pos*dt)*w2
    strikes = np.linspace(70, 140, 15)
    ivs = []
    for K in strikes:
        price = np.exp(-r*T) * np.mean(np.maximum(S - K, 0))
        # invert BS
        def bs_call(sg):
            d1 = (np.log(S0/K)+(r+0.5*sg**2)*T)/(sg*np.sqrt(T))
            d2 = d1 - sg*np.sqrt(T)
            return S0*norm.cdf(d1) - K*np.exp(-r*T)*norm.cdf(d2)
        lo, hi = 0.05, 1.5
        for _ in range(60):
            mid = 0.5*(lo+hi)
            if bs_call(mid) > price: hi = mid
            else: lo = mid
        ivs.append(0.5*(lo+hi))
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(strikes, np.array(ivs)*100, "o-", color="#2a62a6", label="Heston-implied IV")
    ax.axhline(np.sqrt(v0)*100, ls=":", color="#a62a2a", label=r"$\sqrt{v_0}$")
    ax.set_xlabel("Strike K"); ax.set_ylabel("Implied vol (%)")
    ax.set_title(r"Heston smile: $\rho=-0.7$ → put skew")
    ax.legend(); save("ch10-heston-smile.png")

    # (b) sample (S, v) paths
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7, 5), sharex=True)
    t = np.linspace(0, T, n_steps+1)
    rng2 = np.random.default_rng(1)
    for i in range(5):
        S_p = np.zeros(n_steps+1); v_p = np.zeros(n_steps+1)
        S_p[0] = S0; v_p[0] = v0
        for k in range(n_steps):
            z1 = rng2.standard_normal(); z2 = rng2.standard_normal()
            w2 = rho*z1 + np.sqrt(1-rho**2)*z2
            v_pos = max(v_p[k], 0)
            S_p[k+1] = S_p[k] * np.exp((r - 0.5*v_pos)*dt + np.sqrt(v_pos*dt)*z1)
            v_p[k+1] = v_p[k] + kappa*(theta - v_pos)*dt + sigma_v*np.sqrt(v_pos*dt)*w2
        ax1.plot(t, S_p, alpha=0.7, lw=1)
        ax2.plot(t, np.sqrt(np.maximum(v_p, 0))*100, alpha=0.7, lw=1)
    ax1.set_ylabel("S"); ax1.set_title("Heston paths: spot and instantaneous vol")
    ax2.set_xlabel("t (y)"); ax2.set_ylabel(r"$\sqrt{v_t}$ (%)")
    save("ch10-heston-paths.png")


# ────────────────────────────────────────────────────────────
# CH11 — Short-Rate Models (Vasicek)
# ────────────────────────────────────────────────────────────
def ch11():
    print("CH11:")
    # (a) yield curve shapes
    kappa = 0.3; sigma = 0.015
    T = np.linspace(0.25, 30, 120)
    def B(k, T): return (1 - np.exp(-k*T))/k
    fig, ax = plt.subplots(figsize=(7, 4))
    for r0, theta, label, color in [
        (0.025, 0.05, "r_0 < θ (normal)", "#1f7a1f"),
        (0.05,  0.05, "r_0 = θ (flat-ish)", "#2a62a6"),
        (0.08,  0.05, "r_0 > θ (inverted)", "#a62a2a"),
    ]:
        Bv = B(kappa, T)
        A_ = np.exp((theta - sigma**2/(2*kappa**2))*(Bv - T) - sigma**2/(4*kappa)*Bv**2)
        P = A_ * np.exp(-Bv * r0)
        y = -np.log(P)/T
        ax.plot(T, y*100, lw=2, label=label, color=color)
    ax.set_xlabel("Maturity T (y)"); ax.set_ylabel("Zero rate (%)")
    ax.set_title("Vasicek yield curve shapes")
    ax.legend(); save("ch11-vasicek-shapes.png")

    # (b) P(t,T) bond price surface
    t_grid = np.linspace(0, 5, 60); T_grid = np.linspace(0, 10, 60)
    r0, theta = 0.04, 0.05
    TT, tt = np.meshgrid(T_grid, t_grid)
    dur = np.maximum(TT - tt, 0)
    Bv = B(kappa, dur)
    A_ = np.exp((theta - sigma**2/(2*kappa**2))*(Bv - dur) - sigma**2/(4*kappa)*Bv**2)
    P = A_ * np.exp(-Bv * r0)
    P[TT < tt] = np.nan
    fig = plt.figure(figsize=(8, 5))
    ax = fig.add_subplot(111, projection="3d")
    ax.plot_surface(tt, TT, P, cmap="viridis", alpha=0.85, edgecolor="none")
    ax.set_xlabel("t"); ax.set_ylabel("T"); ax.set_zlabel("P(t,T)")
    ax.set_title("Vasicek bond-price surface")
    save("ch11-bond-surface.png")


# ────────────────────────────────────────────────────────────
# CH12 — Caps and Caplets
# ────────────────────────────────────────────────────────────
def ch12():
    print("CH12:")
    from scipy.stats import norm
    # (a) cap price vs strike under Black
    F = 0.04; T = 2.0; sig = 0.3; delta = 0.25; N = 1.0
    strikes = np.linspace(0.01, 0.08, 60)
    caplet = []
    for K in strikes:
        d1 = (np.log(F/K) + 0.5*sig**2*T)/(sig*np.sqrt(T))
        d2 = d1 - sig*np.sqrt(T)
        caplet.append(delta*N*(F*norm.cdf(d1) - K*norm.cdf(d2)))
    caplet = np.array(caplet)
    cap = caplet * 8   # 8 caplets of the same strike
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(strikes*100, cap*10000, lw=2, color="#2a62a6")
    ax.set_xlabel("Strike (%)"); ax.set_ylabel("Cap price (bp of notional)")
    ax.set_title("Cap price vs strike (Black model)"); save("ch12-cap-price.png")

    # (b) caplet payoff vs reset rate
    L = np.linspace(0, 0.10, 100)
    K_cap = 0.04
    payoff = np.maximum(L - K_cap, 0) * 0.25 * 1.0   # per notional, per delta
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(L*100, payoff*10000, lw=2, color="#e07a2a")
    ax.axvline(K_cap*100, ls=":", color="black", label=f"K={K_cap*100:.1f}%")
    ax.set_xlabel("Reset rate $L$ (%)"); ax.set_ylabel("Payoff (bp)")
    ax.set_title(r"Caplet payoff $\delta(L-K)^+$"); ax.legend()
    save("ch12-caplet-payoff.png")


# Drive
if __name__ == "__main__":
    for fn in (ch01, ch02, ch03, ch04, ch05, ch06, ch07, ch08, ch09, ch10, ch11, ch12):
        try:
            fn()
        except Exception as e:
            print(f"  FAILED: {fn.__name__} — {type(e).__name__}: {e}")
    print("\nAll done → docs/guide/figures/")
