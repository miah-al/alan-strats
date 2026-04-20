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

    # (d) Brownian-motion sample paths at three time scales
    rng_bm = np.random.default_rng(11)
    fig, ax = plt.subplots(figsize=(7.5, 4))
    palette = ["#2a62a6", "#a62a2a", "#1f7a1f", "#6a3a8a", "#e07a2a"]
    n_steps = 4000; T_bm = 1.0
    t = np.linspace(0.0, T_bm, n_steps + 1)
    for i in range(5):
        incr = rng_bm.standard_normal(n_steps) * np.sqrt(T_bm / n_steps)
        W = np.concatenate([[0.0], np.cumsum(incr)])
        ax.plot(t, W, lw=1.1, alpha=0.85, color=palette[i])
    ax.axhline(0, color="black", lw=0.5)
    ax.set_xlabel("t"); ax.set_ylabel(r"$W_t$")
    ax.set_title(r"Five Brownian-motion sample paths — continuous but nowhere smooth")
    save("ch03-bm-paths.png")

    # (f) Itô's lemma vs classical chain rule on f(W_t) = W_t^2
    # Classical chain rule would predict df = 2 W dW (no drift).
    # Itô's lemma gives df = dt + 2 W dW, so E[f(W_t)] = t not 0.
    rng_it = np.random.default_rng(13)
    T_it = 2.0; n_steps_it = 1000; n_paths_it = 2000
    dt_it = T_it / n_steps_it
    t_it = np.linspace(0.0, T_it, n_steps_it + 1)
    dW_it = rng_it.standard_normal((n_paths_it, n_steps_it)) * np.sqrt(dt_it)
    W_it = np.concatenate([np.zeros((n_paths_it, 1)), np.cumsum(dW_it, axis=1)], axis=1)
    f_samples = W_it ** 2
    mean_f = f_samples.mean(axis=0)
    # Classical "chain rule" prediction (wrong): drift term missing, so E[W^2] would be 0.
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(t_it, mean_f, lw=2, color="#2a62a6", label=r"MC $\mathbb{E}[W_t^2]$")
    ax.plot(t_it, t_it, ls="--", lw=2, color="#1f7a1f",
            label=r"Itô: $\mathbb{E}[W_t^2]=t$")
    ax.plot(t_it, np.zeros_like(t_it), ls=":", lw=2, color="#a62a2a",
            label=r"Classical chain rule would give $0$")
    ax.set_xlabel("t"); ax.set_ylabel(r"$\mathbb{E}[f(W_t)]$ with $f(x)=x^2$")
    ax.set_title(r"Itô vs classical chain rule on $f(W_t)=W_t^2$")
    ax.legend()
    save("ch03-ito-vs-chain.png")

    # (g) OU vs GBM sample paths (side-by-side) — §3.10 SDE catalogue
    rng_og = np.random.default_rng(21)
    T_og = 3.0; n_steps_og = 600; n_paths_og = 6
    dt_og = T_og / n_steps_og
    t_og = np.linspace(0.0, T_og, n_steps_og + 1)
    # GBM with mu=0.08, sigma=0.25
    mu_gbm, sig_gbm, S0 = 0.08, 0.25, 100.0
    S_paths = np.zeros((n_paths_og, n_steps_og + 1)); S_paths[:, 0] = S0
    # OU with kappa=1.2, theta=0.05, sigma=0.015 starting r0=0.02
    kappa_ou, theta_ou, sig_ou, r0_ou = 1.2, 0.05, 0.015, 0.02
    r_paths = np.zeros((n_paths_og, n_steps_og + 1)); r_paths[:, 0] = r0_ou
    palette_og = ["#2a62a6", "#a62a2a", "#1f7a1f", "#6a3a8a", "#e07a2a", "#2a8a8a"]
    for k in range(n_steps_og):
        Z = rng_og.standard_normal(n_paths_og)
        S_paths[:, k+1] = S_paths[:, k] * np.exp(
            (mu_gbm - 0.5 * sig_gbm**2) * dt_og + sig_gbm * np.sqrt(dt_og) * Z
        )
        Z2 = rng_og.standard_normal(n_paths_og)
        r_paths[:, k+1] = r_paths[:, k] + kappa_ou * (theta_ou - r_paths[:, k]) * dt_og + sig_ou * np.sqrt(dt_og) * Z2
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))
    for i in range(n_paths_og):
        ax1.plot(t_og, S_paths[i], lw=1.1, alpha=0.85, color=palette_og[i])
    ax1.plot(t_og, S0 * np.exp(mu_gbm * t_og), ls="--", lw=2, color="black",
             label=r"$\mathbb{E}[S_t]=S_0 e^{\mu t}$")
    ax1.set_xlabel("t"); ax1.set_ylabel(r"$S_t$")
    ax1.set_title("GBM — multiplicative, trending")
    ax1.legend(loc="upper left", fontsize=9)
    for i in range(n_paths_og):
        ax2.plot(t_og, r_paths[i] * 100, lw=1.1, alpha=0.85, color=palette_og[i])
    ax2.axhline(theta_ou * 100, ls="--", lw=2, color="black",
                label=r"$\theta$ (long-run mean)")
    ax2.set_xlabel("t"); ax2.set_ylabel("$r_t$ (%)")
    ax2.set_title("OU / Vasicek — mean-reverting")
    ax2.legend(loc="upper right", fontsize=9)
    plt.tight_layout()
    save("ch03-ou-vs-gbm.png")

    # (h) Doléans-Dade exponential: trajectory with E[·]=1 envelope
    rng_dd = np.random.default_rng(31)
    sigma_dd = 0.9
    T_dd = 2.0; n_steps_dd = 800; n_paths_dd = 6
    dt_dd = T_dd / n_steps_dd
    t_dd = np.linspace(0.0, T_dd, n_steps_dd + 1)
    fig, ax = plt.subplots(figsize=(7, 4))
    palette_dd = ["#2a62a6", "#a62a2a", "#1f7a1f", "#6a3a8a", "#e07a2a", "#2a8a8a"]
    for i in range(n_paths_dd):
        dW = rng_dd.standard_normal(n_steps_dd) * np.sqrt(dt_dd)
        W = np.concatenate([[0.0], np.cumsum(dW)])
        Z = np.exp(sigma_dd * W - 0.5 * sigma_dd**2 * t_dd)
        ax.plot(t_dd, Z, lw=1.1, alpha=0.85, color=palette_dd[i])
    ax.axhline(1.0, ls="--", lw=2, color="black", label=r"$\mathbb{E}[Z_t]=1$")
    ax.set_xlabel("t"); ax.set_ylabel(r"$Z_t=\exp(\sigma W_t - \frac{1}{2}\sigma^2 t)$")
    ax.set_title(r"Doléans-Dade exponential — each path diverges, but mean stays at $1$")
    ax.legend()
    save("ch03-doleans-dade.png")

    # (e) Quadratic-variation convergence to t vs total-variation divergence
    rng_qv = np.random.default_rng(7)
    T_qv = 1.0
    mesh_sizes = np.array([16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192])
    # Use the SAME Brownian path sampled at increasing resolution via refinement.
    # Build a very fine master path, then subsample at each mesh.
    n_master = mesh_sizes.max()
    dt_master = T_qv / n_master
    dW_master = rng_qv.standard_normal(n_master) * np.sqrt(dt_master)
    W_master = np.concatenate([[0.0], np.cumsum(dW_master)])
    qv_vals = []; tv_vals = []
    for N in mesh_sizes:
        stride = n_master // N
        W_sub = W_master[::stride]
        dW = np.diff(W_sub)
        qv_vals.append(np.sum(dW ** 2))
        tv_vals.append(np.sum(np.abs(dW)))
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.5, 4))
    ax1.semilogx(mesh_sizes, qv_vals, "o-", color="#2a62a6", lw=2, label="realised QV")
    ax1.axhline(T_qv, ls=":", color="black", label=r"$t = 1$")
    ax1.set_xlabel("# mesh points N"); ax1.set_ylabel(r"$\sum (\Delta W_k)^2$")
    ax1.set_title("Quadratic variation $\\to t$ as mesh refines")
    ax1.legend()
    ax2.loglog(mesh_sizes, tv_vals, "s-", color="#a62a2a", lw=2, label="realised TV")
    ax2.loglog(mesh_sizes, 0.8 * np.sqrt(mesh_sizes), ls=":", color="black",
               label=r"$\sim \sqrt{N}$ reference")
    ax2.set_xlabel("# mesh points N"); ax2.set_ylabel(r"$\sum |\Delta W_k|$")
    ax2.set_title("Total variation diverges like $\\sqrt{N}$")
    ax2.legend()
    plt.tight_layout()
    save("ch03-qv-convergence.png")


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

    # (c) Delta profile across moneyness for three maturities
    K = 100; r = 0.05; sig = 0.2
    S_grid = np.linspace(60, 140, 200)
    maturities = [(0.10, "#e07a2a", "T=0.10y"),
                  (0.50, "#2a62a6", "T=0.50y"),
                  (2.00, "#6a3a8a", "T=2.00y")]
    fig, ax = plt.subplots(figsize=(7.5, 4))
    for T_v, col, lab in maturities:
        d1 = (np.log(S_grid / K) + (r + 0.5 * sig**2) * T_v) / (sig * np.sqrt(T_v))
        ax.plot(S_grid, norm.cdf(d1), lw=2, color=col, label=lab)
    ax.axvline(K, ls=":", color="black", alpha=0.5, label=f"K={K}")
    ax.axhline(0.5, ls=":", color="black", alpha=0.3)
    ax.set_xlabel("Spot S"); ax.set_ylabel(r"Call delta $\Delta = \Phi(d_+)$")
    ax.set_title("Call delta across moneyness — sharpens as T shrinks")
    ax.legend()
    save("ch07-delta-profile.png")

    # (d) Gamma peaks at ATM, taller for shorter maturities
    fig, ax = plt.subplots(figsize=(7.5, 4))
    for T_v, col, lab in maturities:
        d1 = (np.log(S_grid / K) + (r + 0.5 * sig**2) * T_v) / (sig * np.sqrt(T_v))
        gamma = norm.pdf(d1) / (S_grid * sig * np.sqrt(T_v))
        ax.plot(S_grid, gamma, lw=2, color=col, label=lab)
    ax.axvline(K, ls=":", color="black", alpha=0.5, label=f"K={K}")
    ax.set_xlabel("Spot S"); ax.set_ylabel(r"Gamma $\Gamma = \Phi'(d_+)/(S\sigma\sqrt{T-t})$")
    ax.set_title("Gamma peaks at ATM and grows unboundedly as $T\\downarrow 0$")
    ax.legend()
    save("ch07-gamma-vs-ttm.png")

    # (e1) Call vs put delta across moneyness
    S_cp = np.linspace(60, 140, 200)
    K_cp = 100; r_cp = 0.05; sig_cp = 0.2; T_cp = 0.5
    d1_cp = (np.log(S_cp / K_cp) + (r_cp + 0.5 * sig_cp**2) * T_cp) / (sig_cp * np.sqrt(T_cp))
    delta_call = norm.cdf(d1_cp)
    delta_put = norm.cdf(d1_cp) - 1
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(S_cp, delta_call, lw=2.4, color="#1f7a1f", label=r"Call $\Delta = \Phi(d_+)$")
    ax.plot(S_cp, delta_put, lw=2.4, color="#a62a2a", label=r"Put $\Delta = \Phi(d_+)-1$")
    ax.axvline(K_cp, ls=":", color="black", alpha=0.5, label=f"K={K_cp}")
    ax.axhline(0, color="black", lw=0.5)
    ax.axhline(0.5, ls=":", color="black", alpha=0.3)
    ax.axhline(-0.5, ls=":", color="black", alpha=0.3)
    ax.set_xlabel("Spot S"); ax.set_ylabel(r"Delta")
    ax.set_title("Call vs put delta — differ by $1$ at every spot (put-call parity)")
    ax.legend()
    save("ch07-call-put-delta.png")

    # (e2) Vega decay: vega vs time-to-expiry for ATM options
    T_grid_v = np.linspace(0.01, 2.0, 200)
    S_v = 100; K_v = 100; r_v = 0.05; sig_v = 0.2
    # For ATM (S=K): d1 = (r + 0.5 sig^2) sqrt(T) / sig
    d1_v = (np.log(S_v / K_v) + (r_v + 0.5 * sig_v**2) * T_grid_v) / (sig_v * np.sqrt(T_grid_v))
    vega_v = S_v * np.sqrt(T_grid_v) * norm.pdf(d1_v)
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(T_grid_v, vega_v, lw=2.4, color="#2a62a6")
    ax.set_xlabel("Time to expiry $T-t$ (y)")
    ax.set_ylabel(r"Vega $\mathcal{V}$ (per vol point, S=K=100)")
    ax.set_title(r"Vega decay: ATM vega grows as $\sqrt{T-t}$ and vanishes at expiry")
    # Invert x-axis for intuition: time running forward toward expiry
    ax.invert_xaxis()
    save("ch07-vega-decay.png")

    # (e) Vega heatmap in (S, T) space
    S_grid2 = np.linspace(60, 140, 140)
    T_grid2 = np.linspace(0.05, 2.0, 100)
    SS, TT = np.meshgrid(S_grid2, T_grid2)
    d1v = (np.log(SS / K) + (r + 0.5 * sig**2) * TT) / (sig * np.sqrt(TT))
    vega = SS * np.sqrt(TT) * norm.pdf(d1v)
    fig, ax = plt.subplots(figsize=(7.5, 4))
    im = ax.pcolormesh(SS, TT, vega, cmap="viridis", shading="auto")
    ax.axvline(K, ls=":", color="white", alpha=0.8)
    cbar = plt.colorbar(im, ax=ax)
    cbar.set_label(r"Vega $\mathcal{V} = S\sqrt{T-t}\,\Phi'(d_+)$")
    ax.set_xlabel("Spot S"); ax.set_ylabel("Time to expiry T (y)")
    ax.set_title("Vega heatmap — highest for long-dated, at-the-money options")
    ax.grid(False)
    save("ch07-vega-heatmap.png")

    # (f) Normal vs Student-t3 densities with VaR/CTE cutoffs (for CH09 §9.4)
    from scipy.stats import t as student_t
    x = np.linspace(-5, 5, 600)
    pdf_n = norm.pdf(x)
    pdf_t = student_t.pdf(x, df=3)
    var_n = norm.ppf(0.95)
    var_t = student_t.ppf(0.95, df=3)
    # CTE formulas for symmetric distributions, right-tail (losses) at 95%
    alpha = 0.05
    cte_n = norm.pdf(var_n) / alpha
    cte_t = student_t.pdf(var_t, df=3) * (3 + var_t**2) / ((3 - 1) * alpha)
    fig, ax = plt.subplots(figsize=(7.5, 4))
    ax.plot(x, pdf_n, lw=2, color="#2a62a6", label="Normal")
    ax.plot(x, pdf_t, lw=2, color="#a62a2a", label="Student-$t_3$ (fat tails)")
    ax.fill_between(x, 0, pdf_n, where=(x >= var_n), alpha=0.25, color="#2a62a6")
    ax.fill_between(x, 0, pdf_t, where=(x >= var_t), alpha=0.25, color="#a62a2a")
    ax.axvline(var_n, ls="--", color="#2a62a6", alpha=0.8,
               label=f"VaR$_{{95}}^N$={var_n:.2f}, CTE={cte_n:.2f}")
    ax.axvline(var_t, ls="--", color="#a62a2a", alpha=0.8,
               label=f"VaR$_{{95}}^{{t_3}}$={var_t:.2f}, CTE={cte_t:.2f}")
    ax.set_xlabel("loss $L$"); ax.set_ylabel("density")
    ax.set_title("Fat tails shift VaR modestly but blow up CTE")
    ax.legend(fontsize=9)
    ax.set_ylim(0, 0.45)
    save("ch09-normal-vs-t3.png")

    # (g0) Historical vs parametric vs MC VaR on the same loss distribution
    rng_var = np.random.default_rng(2025)
    # A skewed, mildly fat-tailed loss distribution (mixture)
    n_hist = 1000
    base = rng_var.standard_normal(n_hist) * 0.018
    jump = (rng_var.random(n_hist) < 0.04) * rng_var.standard_normal(n_hist) * 0.05
    losses_sample = -(base + jump - 0.002)  # losses positive
    alpha_lvl = 0.95
    # Historical VaR
    var_hist = np.percentile(losses_sample, alpha_lvl * 100)
    # Parametric (Gaussian fit)
    mu_p = losses_sample.mean(); sd_p = losses_sample.std()
    var_para = mu_p + norm.ppf(alpha_lvl) * sd_p
    # Monte Carlo (many draws from fitted mixture)
    n_mc_var = 200000
    base_mc = rng_var.standard_normal(n_mc_var) * 0.018
    jump_mc = (rng_var.random(n_mc_var) < 0.04) * rng_var.standard_normal(n_mc_var) * 0.05
    losses_mc = -(base_mc + jump_mc - 0.002)
    var_mc = np.percentile(losses_mc, alpha_lvl * 100)
    labels = ["Historical\n(1000 obs)", "Parametric\n(Gaussian fit)", "Monte Carlo\n(200k draws)"]
    vals = [var_hist, var_para, var_mc]
    colors = ["#2a62a6", "#e07a2a", "#1f7a1f"]
    fig, ax = plt.subplots(figsize=(7, 4))
    bars = ax.bar(labels, np.array(vals) * 100, color=colors, alpha=0.85)
    for rect, v in zip(bars, vals):
        ax.text(rect.get_x() + rect.get_width() / 2, rect.get_height() + 0.05,
                f"{v*100:.2f}%", ha="center", fontsize=11)
    ax.set_ylabel("95% VaR (%)")
    ax.set_title("Three routes to VaR on the same loss distribution")
    save("ch09-var-three-routes.png")

    # (g1) Cornish-Fisher adjustment: Normal VaR vs skew/kurt-adjusted
    # Vary skewness s at fixed kurtosis k_ex=3 (heavy excess kurtosis)
    z_a = norm.ppf(0.99)
    skew_grid = np.linspace(-1.5, 1.5, 120)
    kurt_ex = 3.0
    normal_var_line = np.full_like(skew_grid, z_a)
    cf_var = (z_a
              + (1.0 / 6.0) * (z_a**2 - 1) * skew_grid
              + (1.0 / 24.0) * (z_a**3 - 3 * z_a) * kurt_ex
              - (1.0 / 36.0) * (2 * z_a**3 - 5 * z_a) * skew_grid**2)
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(skew_grid, normal_var_line, lw=2, ls="--", color="#2a62a6",
            label=r"Normal quantile $z_{99\%}\approx 2.33$")
    ax.plot(skew_grid, cf_var, lw=2.4, color="#a62a2a",
            label=fr"Cornish-Fisher ($\kappa_{{ex}}={kurt_ex}$)")
    ax.axvline(0, ls=":", color="black", alpha=0.5)
    ax.set_xlabel("skewness $s$")
    ax.set_ylabel(r"quantile multiplier $q_{99\%}$")
    ax.set_title("Cornish-Fisher VaR vs Normal: skew & kurt adjust the multiplier")
    ax.legend()
    save("ch09-cornish-fisher.png")

    # (g2) Kupiec test: exceedance count distribution vs accept/reject band
    # Under H0: X ~ Binomial(n=250, alpha=0.01) for 99% VaR backtest
    from scipy.stats import binom
    n_days = 250; alpha_bt = 0.01
    ks = np.arange(0, 11)
    pmf = binom.pmf(ks, n_days, alpha_bt)
    # Kupiec LR cutoff 3.84 at 5% -> derive acceptance range by inversion
    # For each x compute LR, accept if LR <= 3.84
    def kupiec_lr(x, n, p):
        x = np.asarray(x, dtype=float)
        phat = np.clip(x / n, 1e-9, 1 - 1e-9)
        with np.errstate(divide="ignore", invalid="ignore"):
            ll0 = x * np.log(p) + (n - x) * np.log(1 - p)
            ll1 = x * np.log(phat) + (n - x) * np.log(1 - phat)
        return -2.0 * (ll0 - ll1)
    lrs = kupiec_lr(ks, n_days, alpha_bt)
    accept = lrs <= 3.84
    colors_k = ["#1f7a1f" if a else "#a62a2a" for a in accept]
    fig, ax = plt.subplots(figsize=(7.5, 4))
    ax.bar(ks, pmf, color=colors_k, alpha=0.85, edgecolor="black", lw=0.5)
    ax.axvline(n_days * alpha_bt, ls=":", color="black",
               label=fr"expected $n\alpha = {n_days * alpha_bt:.1f}$")
    # Legend handles for green/red
    from matplotlib.patches import Patch
    handles = [
        Patch(facecolor="#1f7a1f", alpha=0.85, label="Accept (LR ≤ 3.84)"),
        Patch(facecolor="#a62a2a", alpha=0.85, label="Reject (LR > 3.84)"),
    ]
    ax.set_xlabel(f"# exceedances in {n_days} days (99% VaR)")
    ax.set_ylabel("probability")
    ax.set_title("Kupiec POF: Binomial pmf with 5% acceptance band")
    ax.legend(handles=handles + [ax.get_legend_handles_labels()[0][0]]
              if False else handles, loc="upper right")
    ax.set_xticks(ks)
    save("ch09-kupiec-band.png")

    # (g) Sub-additivity failure of VaR on two-loan example (CH09 §9.6.1)
    # Two independent loans, each defaults with p=4%, loss=100; otherwise 0.
    rng_s = np.random.default_rng(99)
    n_mc = 200_000
    p_def = 0.04
    L1 = rng_s.binomial(1, p_def, n_mc) * 100.0
    L2 = rng_s.binomial(1, p_def, n_mc) * 100.0
    L_sum = L1 + L2
    alpha_var = 0.95
    var_L1 = np.percentile(L1, alpha_var * 100)
    var_L2 = np.percentile(L2, alpha_var * 100)
    var_sum = np.percentile(L_sum, alpha_var * 100)
    # CTE as conditional mean above the VaR threshold
    def cte(x, v):
        tail = x[x >= v]
        return tail.mean() if tail.size else 0.0
    cte_L1 = cte(L1, var_L1); cte_L2 = cte(L2, var_L2); cte_sum = cte(L_sum, var_sum)
    labels = ["Loan A", "Loan B", "A+B"]
    var_vals = [var_L1, var_L2, var_sum]
    cte_vals = [cte_L1, cte_L2, cte_sum]
    xpos = np.arange(len(labels)); w = 0.38
    fig, ax = plt.subplots(figsize=(7.5, 4))
    bars_v = ax.bar(xpos - w/2, var_vals, w, color="#e07a2a", label="VaR 95%")
    bars_c = ax.bar(xpos + w/2, cte_vals, w, color="#a62a2a", label="CTE 95%")
    for rect, v in zip(bars_v, var_vals):
        ax.text(rect.get_x() + rect.get_width()/2, rect.get_height() + 0.5,
                f"{v:.1f}", ha="center", fontsize=10)
    for rect, v in zip(bars_c, cte_vals):
        ax.text(rect.get_x() + rect.get_width()/2, rect.get_height() + 0.5,
                f"{v:.1f}", ha="center", fontsize=10)
    ax.set_xticks(xpos); ax.set_xticklabels(labels)
    ax.set_ylabel("Loss units")
    ax.set_title("VaR sub-additivity fails; CTE is coherent (two-loan example)")
    ax.legend()
    save("ch09-subadditivity-failure.png")


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

    # (c) FK Monte-Carlo sanity check across three worked payoffs (linear, quadratic, exponential)
    # Using X_t = Brownian motion; payoffs from sections 4.5-4.7.
    rng_fk = np.random.default_rng(3)
    T_fk = 1.0
    x0 = 0.5
    n_paths = 5000
    n_trials = np.logspace(2, 4.3, 25).astype(int)
    # Closed forms
    #   phi(x)=x           -> f(0,x0) = x0
    #   phi(x)=x^2         -> f(0,x0) = x0^2 + T
    #   phi(x)=exp(a x)    -> f(0,x0) = exp(a x0 + 0.5 a^2 T)
    a_exp = 0.8
    closed = {
        "linear":      x0,
        "quadratic":   x0**2 + T_fk,
        "exponential": np.exp(a_exp * x0 + 0.5 * a_exp**2 * T_fk),
    }
    colors = {"linear": "#2a62a6", "quadratic": "#1f7a1f", "exponential": "#6a3a8a"}
    fig, ax = plt.subplots(figsize=(7.5, 4))
    for name in ["linear", "quadratic", "exponential"]:
        vals = []
        for n in n_trials:
            XT = x0 + np.sqrt(T_fk) * rng_fk.standard_normal(n)
            if name == "linear":
                payoff = XT
            elif name == "quadratic":
                payoff = XT**2
            else:
                payoff = np.exp(a_exp * XT)
            vals.append(np.mean(payoff))
        vals = np.array(vals) / closed[name]
        ax.semilogx(n_trials, vals, "o-", lw=1.5, alpha=0.8, color=colors[name], label=f"{name}")
    ax.axhline(1.0, ls=":", color="black", label="closed form")
    ax.set_xlabel("# Monte-Carlo draws"); ax.set_ylabel("MC estimate / closed form")
    ax.set_title("Feynman-Kac sanity check: MC averages → PDE solutions (§§4.5–4.7)")
    ax.legend()
    save("ch04-fk-mc-check.png")

    # (d) Backward smoothing of a digital payoff under the heat-equation flow
    # f(t, x) = E[ 1{B_T > K} | B_t = x ] = Phi((x - K)/sqrt(T - t))
    x_bs = np.linspace(-2, 2, 300)
    K_bs = 0.0
    fig, ax = plt.subplots(figsize=(7.5, 4))
    T_bs = 1.0
    ttm = [1e-4, 0.05, 0.2, 0.5, 1.0]
    palette_t = ["#a62a2a", "#e07a2a", "#1f7a1f", "#2a62a6", "#6a3a8a"]
    for tau, col in zip(ttm, palette_t):
        if tau < 1e-3:
            y = (x_bs > K_bs).astype(float)
            lab = r"$T-t = 0$ (terminal)"
        else:
            y = norm.cdf((x_bs - K_bs) / np.sqrt(tau))
            lab = fr"$T-t = {tau:.2f}$"
        ax.plot(x_bs, y, lw=2, color=col, label=lab)
    ax.axvline(K_bs, ls=":", color="black", alpha=0.4)
    ax.set_xlabel("state $x$"); ax.set_ylabel(r"$f(t, x) = \mathbb{E}[\mathbf{1}_{X_T>K}\mid X_t=x]$")
    ax.set_title("Heat-equation smoothing: digital payoff diffuses backward in time")
    ax.legend(fontsize=9)
    save("ch04-backward-smoothing.png")

    # (e) FK backward solution curve for a call-like payoff, at several times
    # f(t, x) for phi(x) = max(x, 0) under driftless BM:
    # f(t, x) = E[max(X_T, 0) | X_t = x] with X_T ~ N(x, T-t)
    # Closed form: x * Phi(x / sqrt(T-t)) + sqrt(T-t) * phi_pdf(x / sqrt(T-t))
    x_curve = np.linspace(-3, 3, 400)
    T_curve = 1.0
    ttm_c = [1e-4, 0.1, 0.3, 0.6, 1.0]
    palette_c = ["#a62a2a", "#e07a2a", "#1f7a1f", "#2a62a6", "#6a3a8a"]
    fig, ax = plt.subplots(figsize=(7.5, 4))
    for tau, col in zip(ttm_c, palette_c):
        if tau < 1e-3:
            y = np.maximum(x_curve, 0)
            lab = r"$T-t = 0$ (terminal)"
        else:
            s = np.sqrt(tau)
            y = x_curve * norm.cdf(x_curve / s) + s * norm.pdf(x_curve / s)
            lab = fr"$T-t = {tau:.2f}$"
        ax.plot(x_curve, y, lw=2, color=col, label=lab)
    ax.set_xlabel("state $x$"); ax.set_ylabel(r"$f(t,x)=\mathbb{E}[(X_T)^+\mid X_t=x]$")
    ax.set_title("Feynman-Kac backward solution: call-like kink smooths as time remains")
    ax.legend(fontsize=9)
    save("ch04-fk-backward-curves.png")

    # (f) Heat-equation Green's-function convolution: payoff × Gaussian kernel → price
    # Illustrate f(0, x) = ∫ phi(y) * G(y - x; T) dy for a digital payoff.
    x_plot = np.linspace(-3, 3, 400)
    T_heat = 0.4
    K_heat = 0.0
    phi = (x_plot > K_heat).astype(float)
    # Gaussian kernel centred at x=0 with width sqrt(T)
    kernel = np.exp(-x_plot**2 / (2 * T_heat)) / np.sqrt(2 * np.pi * T_heat)
    # Convolution result == Phi((x - K) / sqrt(T))
    smoothed = norm.cdf((x_plot - K_heat) / np.sqrt(T_heat))
    fig, ax = plt.subplots(figsize=(7.5, 4))
    ax.plot(x_plot, phi, lw=2.2, color="#a62a2a", label=r"payoff $\varphi(y)=\mathbf{1}_{y>K}$")
    ax.plot(x_plot, kernel / kernel.max() * 0.9, lw=2, color="#1f7a1f", ls="--",
            label=r"Gaussian kernel $G(y-x;T)$ (scaled)")
    ax.plot(x_plot, smoothed, lw=2.4, color="#2a62a6",
            label=r"convolution $=f(0,x)$")
    ax.axvline(K_heat, ls=":", color="black", alpha=0.4)
    ax.set_xlabel("$x$"); ax.set_ylabel("value")
    ax.set_title(r"Price = payoff $\ast$ heat kernel — smoothing via Gaussian convolution")
    ax.legend(fontsize=9, loc="upper left")
    save("ch04-green-convolution.png")

    # (g) Quadratic payoff §4.6 — MC sanity check per-x_0 grid
    # Closed form: f(0, x) = x^2 + T
    rng_q = np.random.default_rng(55)
    T_q = 1.0
    x0_grid = np.linspace(-2, 2, 15)
    n_paths_q = 40000
    mc_est = []; closed = []
    for x0 in x0_grid:
        XT = x0 + np.sqrt(T_q) * rng_q.standard_normal(n_paths_q)
        mc_est.append((XT ** 2).mean())
        closed.append(x0 ** 2 + T_q)
    mc_est = np.array(mc_est); closed = np.array(closed)
    fig, ax = plt.subplots(figsize=(7, 4))
    xs_dense = np.linspace(-2, 2, 200)
    ax.plot(xs_dense, xs_dense ** 2 + T_q, lw=2, color="#2a62a6",
            label=r"closed form $x^2 + T$")
    ax.plot(x0_grid, mc_est, "o", ms=7, color="#a62a2a", label=fr"MC ({n_paths_q:,} paths)")
    ax.set_xlabel(r"initial state $x_0$"); ax.set_ylabel(r"$f(0, x_0)=\mathbb{E}[X_T^2\mid X_0=x_0]$")
    ax.set_title("Quadratic payoff: MC vs PDE solution (§4.6)")
    ax.legend()
    save("ch04-quadratic-mc-vs-pde.png")

    # (h) OU exponential payoff Feynman-Kac: closed form vs MC for several x0
    # Under dX = -kappa(X - theta) dt + sigma dW, payoff exp(aX_T), discount r
    # Distribution of X_T | X_0 = x is Gaussian with mean m and variance v:
    #   m = x e^{-kappa T} + theta (1 - e^{-kappa T})
    #   v = sigma^2/(2 kappa) * (1 - e^{-2 kappa T})
    # Then E[e^{a X_T}] = exp(a*m + 0.5 * a^2 * v); discounted price = e^{-rT} * that.
    rng_e = np.random.default_rng(77)
    kappa_e, theta_e, sig_e = 1.0, 0.04, 0.02
    T_e = 1.5; r_e = 0.03; a_e = 2.0
    x0_e = np.linspace(0.0, 0.08, 12)
    n_paths_e = 20000
    n_steps_e = 400
    dt_e = T_e / n_steps_e
    mc_price = []; closed_price = []
    for x0 in x0_e:
        X = np.full(n_paths_e, x0)
        for _ in range(n_steps_e):
            X = X + kappa_e * (theta_e - X) * dt_e + sig_e * np.sqrt(dt_e) * rng_e.standard_normal(n_paths_e)
        mc_price.append(np.exp(-r_e * T_e) * np.exp(a_e * X).mean())
        m = x0 * np.exp(-kappa_e * T_e) + theta_e * (1 - np.exp(-kappa_e * T_e))
        v = sig_e**2 / (2 * kappa_e) * (1 - np.exp(-2 * kappa_e * T_e))
        closed_price.append(np.exp(-r_e * T_e) * np.exp(a_e * m + 0.5 * a_e**2 * v))
    mc_price = np.array(mc_price); closed_price = np.array(closed_price)
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(x0_e, closed_price, lw=2.2, color="#2a62a6",
            label="Gaussian-MGF closed form")
    ax.plot(x0_e, mc_price, "s", ms=7, color="#a62a2a",
            label=fr"MC ({n_paths_e:,} paths, {n_steps_e} steps)")
    ax.set_xlabel(r"initial state $x_0$")
    ax.set_ylabel(r"$f(0,x_0)=e^{-rT}\mathbb{E}[e^{a X_T}]$")
    ax.set_title(r"FK with drift+discount: exp payoff on OU process (§4.8)")
    ax.legend()
    save("ch04-ou-exp-fk.png")


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
# CH10-MC — Monte Carlo & Path-Dependent (distinct from Heston above)
# ────────────────────────────────────────────────────────────
def ch10_mc():
    print("CH10-MC:")
    from scipy.stats import norm

    # (a) GBM sample paths — the lognormal path generator of §10.4
    rng = np.random.default_rng(5)
    S0, r, sig, T = 100.0, 0.05, 0.2, 1.0
    n_paths, n_steps = 30, 250
    dt = T / n_steps
    t = np.linspace(0, T, n_steps + 1)
    S = np.empty((n_paths, n_steps + 1)); S[:, 0] = S0
    for k in range(n_steps):
        Z = rng.standard_normal(n_paths)
        S[:, k+1] = S[:, k] * np.exp((r - 0.5*sig**2)*dt + sig*np.sqrt(dt)*Z)
    fig, ax = plt.subplots(figsize=(7.5, 4))
    for i in range(n_paths):
        ax.plot(t, S[i], lw=0.9, alpha=0.65, color="#2a62a6")
    ax.axhline(S0, ls=":", color="black", alpha=0.6, label=r"$S_0$")
    ax.plot(t, S0 * np.exp(r * t), lw=2.2, color="#a62a2a", label=r"$\mathbb{E}^Q[S_t]=S_0 e^{rt}$")
    ax.set_xlabel("t (y)"); ax.set_ylabel("S")
    ax.set_title("GBM sample paths under $\\mathbb{Q}$ (S_0=100, r=5%, σ=20%)")
    ax.legend()
    save("ch10-gbm-paths.png")

    # (b) Monte-Carlo standard error ~ 1/sqrt(N)
    rng2 = np.random.default_rng(13)
    # Pricing an ATM European call; repeat for growing N.
    K = 100.0
    Ns = np.logspace(1.6, 5, 25).astype(int)
    # Reference price (closed-form BS)
    d1 = (np.log(S0/K) + (r + 0.5*sig**2)*T) / (sig*np.sqrt(T))
    d2 = d1 - sig*np.sqrt(T)
    bs_price = S0*norm.cdf(d1) - K*np.exp(-r*T)*norm.cdf(d2)
    n_reps = 200
    std_errs = []
    for N in Ns:
        ests = []
        for _ in range(n_reps):
            Z = rng2.standard_normal(N)
            ST = S0 * np.exp((r - 0.5*sig**2)*T + sig*np.sqrt(T)*Z)
            ests.append(np.exp(-r*T) * np.mean(np.maximum(ST - K, 0)))
        std_errs.append(np.std(ests))
    std_errs = np.array(std_errs)
    ref = std_errs[0] * np.sqrt(Ns[0]) / np.sqrt(Ns)
    fig, ax = plt.subplots(figsize=(7.5, 4))
    ax.loglog(Ns, std_errs, "o-", color="#2a62a6", lw=2, label="MC std error (200 replications)")
    ax.loglog(Ns, ref, ls=":", color="#a62a2a", lw=2, label=r"$\propto 1/\sqrt{N}$")
    ax.set_xlabel("# Monte-Carlo paths N"); ax.set_ylabel("std error of price estimate")
    ax.set_title(f"MC convergence: halving error costs 4× more paths  (BS price = {bs_price:.3f})")
    ax.legend()
    save("ch10-mc-sqrt-rate.png")

    # (c) Antithetic vs plain MC: empirical std error at fixed compute cost
    rng3 = np.random.default_rng(21)
    Ns_cost = np.array([200, 500, 1000, 2000, 5000, 10000, 20000, 50000])
    n_reps = 150
    plain_stds, ant_stds = [], []
    for N_cost in Ns_cost:
        plain_vals, ant_vals = [], []
        # Plain MC uses N_cost independent draws.
        # Antithetic uses N_cost/2 pairs → also N_cost payoff evaluations.
        N_pair = max(2, N_cost // 2)
        for _ in range(n_reps):
            Z = rng3.standard_normal(N_cost)
            ST = S0 * np.exp((r - 0.5*sig**2)*T + sig*np.sqrt(T)*Z)
            plain_vals.append(np.exp(-r*T) * np.mean(np.maximum(ST - K, 0)))
            Zp = rng3.standard_normal(N_pair)
            ST1 = S0 * np.exp((r - 0.5*sig**2)*T + sig*np.sqrt(T)*Zp)
            ST2 = S0 * np.exp((r - 0.5*sig**2)*T - sig*np.sqrt(T)*Zp)
            payoff_pair = 0.5 * (np.maximum(ST1 - K, 0) + np.maximum(ST2 - K, 0))
            ant_vals.append(np.exp(-r*T) * np.mean(payoff_pair))
        plain_stds.append(np.std(plain_vals))
        ant_stds.append(np.std(ant_vals))
    fig, ax = plt.subplots(figsize=(7.5, 4))
    ax.loglog(Ns_cost, plain_stds, "o-", color="#a62a2a", lw=2, label="Plain MC")
    ax.loglog(Ns_cost, ant_stds, "s-", color="#1f7a1f", lw=2, label="Antithetic MC")
    ax.set_xlabel("payoff evaluations (compute cost)"); ax.set_ylabel("std error of price estimate")
    ax.set_title("Antithetic variates cut MC std error at equal cost (ATM call)")
    ax.legend()
    save("ch10-antithetic-vs-plain.png")


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
# CH11-CAL — Calibration (L-curve, calibrated short-rate tree)
# ────────────────────────────────────────────────────────────
def ch11_cal():
    print("CH11-CAL:")
    rng = np.random.default_rng(4)

    # (a) L-curve: fit residual vs regularisation strength
    # Build a toy linear inverse problem:  y_i = sum_j  K_ij theta_j  +  noise
    # with theta the true parameters (smooth curve) and K a smoothing operator.
    n_obs, n_par = 30, 30
    grid = np.linspace(0, 1, n_par)
    theta_true = 0.3 * np.sin(2 * np.pi * grid) + 0.2 * np.cos(4 * np.pi * grid)
    # Gaussian convolution kernel — mildly ill-conditioned
    xx, yy = np.meshgrid(grid, grid)
    K = np.exp(-((xx - yy) ** 2) / 0.02)
    K /= K.sum(axis=1, keepdims=True)
    y_clean = K @ theta_true
    y_obs = y_clean + 0.015 * rng.standard_normal(n_obs)
    # Tikhonov solution:   theta(lam) = (K'K + lam I)^-1 K' y_obs
    I_ = np.eye(n_par)
    lambdas = np.logspace(-6, 2, 40)
    fit_err = []; sol_norm = []
    for lam in lambdas:
        th = np.linalg.solve(K.T @ K + lam * I_, K.T @ y_obs)
        fit_err.append(np.linalg.norm(K @ th - y_obs))
        sol_norm.append(np.linalg.norm(th))
    fit_err = np.array(fit_err); sol_norm = np.array(sol_norm)
    # Mark an "elbow" heuristic: corner of the log-log curve.
    logf = np.log(fit_err); logs = np.log(sol_norm)
    d1 = np.gradient(logf, np.log(lambdas))
    d2 = np.gradient(logs, np.log(lambdas))
    curvature = (d1 * np.gradient(d2, np.log(lambdas))
                 - d2 * np.gradient(d1, np.log(lambdas))) / (d1 ** 2 + d2 ** 2 + 1e-12) ** 1.5
    elbow = int(np.argmax(curvature[5:-5])) + 5
    fig, ax = plt.subplots(figsize=(7.5, 4))
    ax.loglog(fit_err, sol_norm, "o-", color="#2a62a6", lw=1.6, alpha=0.9)
    ax.plot(fit_err[elbow], sol_norm[elbow], "o", markersize=12,
            markerfacecolor="none", markeredgecolor="#a62a2a", markeredgewidth=2,
            label=fr"suggested $\lambda \approx {lambdas[elbow]:.1e}$")
    # Label a few lambda values on the curve
    for idx, txt in [(2, "low λ\n(overfit)"), (elbow, "elbow"), (len(lambdas)-3, "high λ\n(underfit)")]:
        ax.annotate(txt, (fit_err[idx], sol_norm[idx]),
                    xytext=(10, 10), textcoords="offset points", fontsize=9,
                    color="#444")
    ax.set_xlabel(r"fit residual $\|K\theta - y\|$")
    ax.set_ylabel(r"solution norm $\|\theta\|$")
    ax.set_title("L-curve: the fit-vs-regularisation tradeoff")
    ax.legend()
    save("ch11-lcurve.png")

    # (a1) RN density across states from multinomial calibration
    # Five-state world; market-implied risk-neutral probabilities vs the
    # "physical" uniform prior.  The RN derivative dQ/dP = q_i / p_i.
    states = [r"$\omega_1$", r"$\omega_2$", r"$\omega_3$", r"$\omega_4$", r"$\omega_5$"]
    p_phys = np.array([0.20, 0.20, 0.20, 0.20, 0.20])
    q_rn = np.array([0.08, 0.18, 0.34, 0.28, 0.12])  # sums to 1
    rn = q_rn / p_phys
    x = np.arange(len(states))
    w = 0.38
    fig, ax = plt.subplots(figsize=(7.5, 4))
    ax.bar(x - w/2, p_phys, w, color="#2a62a6", label=r"physical $p_i$")
    ax.bar(x + w/2, q_rn, w, color="#a62a2a", label=r"risk-neutral $q_i$ (calibrated)")
    ax.plot(x, rn * 0.1, "o-", color="#6a3a8a", lw=1.6, markersize=8,
            label=r"$dQ/dP = q_i/p_i$ (right axis)")
    ax.set_xticks(x); ax.set_xticklabels(states)
    ax.set_ylabel("state probability")
    ax.set_title("Radon-Nikodym density from a five-state multinomial calibration")
    ax.legend(loc="upper right", fontsize=9)
    # Show RN values as text annotations
    for xi, rni in zip(x, rn):
        ax.text(xi + w/2 + 0.05, 0.01, f"RN={rni:.2f}", fontsize=8.5, color="#6a3a8a")
    save("ch11-rn-multinomial.png")

    # (a2) Calibration frequency trade-off — stability vs responsiveness
    # Simulate a parameter that drifts smoothly with an abrupt regime shift.
    rng_cf = np.random.default_rng(123)
    n_days = 260
    t_days = np.arange(n_days)
    true_param = 0.20 + 0.02 * np.sin(t_days / 30.0)
    true_param[140:] += 0.04  # abrupt regime shift at day 140
    noise = 0.008 * rng_cf.standard_normal(n_days)
    observed = true_param + noise  # "daily calibration" estimate
    # Monthly recalibration — piecewise-constant at step boundaries
    monthly = observed.copy()
    for k in range(0, n_days, 21):
        monthly[k:k + 21] = observed[k:min(k + 21, n_days)].mean()
    # Weekly recalibration
    weekly = observed.copy()
    for k in range(0, n_days, 5):
        weekly[k:k + 5] = observed[k:min(k + 5, n_days)].mean()
    fig, ax = plt.subplots(figsize=(7.5, 4))
    ax.plot(t_days, true_param, lw=2.2, color="black", label="true parameter", alpha=0.75)
    ax.plot(t_days, observed, lw=1.0, color="#a62a2a", alpha=0.55, label="daily calibration (responsive)")
    ax.plot(t_days, weekly, lw=1.6, color="#e07a2a", label="weekly recalibration")
    ax.plot(t_days, monthly, lw=2.0, color="#2a62a6", label="monthly recalibration (stable)")
    ax.axvline(140, ls=":", color="black", alpha=0.5)
    ax.set_xlabel("trading day"); ax.set_ylabel("calibrated parameter")
    ax.set_title("Calibration frequency: stability vs responsiveness")
    ax.legend(fontsize=9)
    save("ch11-frequency-tradeoff.png")

    # (a3) Out-of-sample validation: training RMSE vs OOS RMSE across lambda
    # Reuse the L-curve setup; split observations into train/test.
    rng_oos = np.random.default_rng(9)
    n_obs_oos, n_par_oos = 40, 40
    grid_o = np.linspace(0, 1, n_par_oos)
    theta_oos = 0.3 * np.sin(2 * np.pi * grid_o) + 0.2 * np.cos(4 * np.pi * grid_o)
    xxo, yyo = np.meshgrid(grid_o, grid_o)
    K_oos = np.exp(-((xxo - yyo) ** 2) / 0.02)
    K_oos /= K_oos.sum(axis=1, keepdims=True)
    y_clean_oos = K_oos @ theta_oos
    y_noisy = y_clean_oos + 0.020 * rng_oos.standard_normal(n_obs_oos)
    # Random train/test split 70/30
    idx = np.arange(n_obs_oos); rng_oos.shuffle(idx)
    tr_idx = idx[: int(0.7 * n_obs_oos)]; te_idx = idx[int(0.7 * n_obs_oos):]
    I_o = np.eye(n_par_oos)
    lams = np.logspace(-5, 1, 30)
    tr_rmse = []; te_rmse = []
    for lam in lams:
        Kt = K_oos[tr_idx]
        th = np.linalg.solve(Kt.T @ Kt + lam * I_o, Kt.T @ y_noisy[tr_idx])
        tr_rmse.append(np.sqrt(np.mean((Kt @ th - y_noisy[tr_idx]) ** 2)))
        Ke = K_oos[te_idx]
        te_rmse.append(np.sqrt(np.mean((Ke @ th - y_noisy[te_idx]) ** 2)))
    tr_rmse = np.array(tr_rmse); te_rmse = np.array(te_rmse)
    elbow_oos = int(np.argmin(te_rmse))
    fig, ax = plt.subplots(figsize=(7.5, 4))
    ax.semilogx(lams, tr_rmse, "o-", color="#2a62a6", lw=1.8, label="training RMSE")
    ax.semilogx(lams, te_rmse, "s-", color="#a62a2a", lw=1.8, label="out-of-sample RMSE")
    ax.axvline(lams[elbow_oos], ls=":", color="black",
               label=fr"OOS min at $\lambda\!\approx\!{lams[elbow_oos]:.1e}$")
    ax.set_xlabel(r"regularisation $\lambda$")
    ax.set_ylabel("RMSE")
    ax.set_title("Training vs out-of-sample error — the U-shape of $\\lambda$")
    ax.legend()
    save("ch11-oos-validation.png")

    # (a4) Bond-price lattice: rates at each node with bond prices
    # Three-step recombining tree. Short rates at each node; at each node
    # we show the one-period bond value 1/(1+r*dt). Display r and P.
    dt_bl = 0.5
    rates_bl = {
        (0, 0): 0.040,
        (1, 0): 0.050, (1, 1): 0.032,
        (2, 0): 0.060, (2, 1): 0.042, (2, 2): 0.028,
        (3, 0): 0.068, (3, 1): 0.052, (3, 2): 0.038, (3, 3): 0.028,
    }
    fig, ax = plt.subplots(figsize=(8.5, 5))
    x_of = lambda k: k * 1.1
    y_of = lambda k, j: (k - 2 * j) * 0.9
    # Edges
    for k in range(3):
        for j in range(k + 1):
            x0, y0 = x_of(k), y_of(k, j)
            x1, y1 = x_of(k + 1), y_of(k + 1, j)
            x2, y2 = x_of(k + 1), y_of(k + 1, j + 1)
            ax.plot([x0, x1], [y0, y1], color="#2a62a6", lw=1.1, alpha=0.55)
            ax.plot([x0, x2], [y0, y2], color="#a62a2a", lw=1.1, alpha=0.55)
    # Nodes with r and P
    for (k, j), r_val in rates_bl.items():
        xn, yn = x_of(k), y_of(k, j)
        P_val = 1.0 / (1.0 + r_val * dt_bl)
        ax.add_patch(plt.Circle((xn, yn), 0.23, facecolor="#fef3c7",
                                 edgecolor="#8a6508", lw=1.2, zorder=3))
        ax.text(xn, yn + 0.05, f"$r$={r_val*100:.2f}%", ha="center", va="center",
                fontsize=8.5, zorder=4)
        ax.text(xn, yn - 0.08, f"$P$={P_val:.4f}", ha="center", va="center",
                fontsize=8.0, color="#444", zorder=4)
    ax.set_xlim(-0.4, 3.9); ax.set_ylim(-3.5, 3.5)
    ax.set_xticks([x_of(k) for k in range(4)]); ax.set_xticklabels([f"$k={k}$" for k in range(4)])
    ax.set_yticks([])
    ax.set_title("Calibrated short-rate tree with one-period bond values $P=1/(1+r\\,\\Delta t)$")
    ax.grid(False)
    for spine in ["left", "right", "top"]:
        ax.spines[spine].set_visible(False)
    save("ch11-bond-lattice.png")

    # (b) Calibrated short-rate tree (3 steps, binomial, recombining) with
    # rates visibly varying across time and nodes — the §11.3 bootstrap result.
    rates = {
        (0, 0): 0.04,
        (1, 0): 0.048, (1, 1): 0.032,
        (2, 0): 0.057, (2, 1): 0.040, (2, 2): 0.028,
        (3, 0): 0.065, (3, 1): 0.050, (3, 2): 0.038, (3, 3): 0.028,
    }
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    x_of = lambda k: k
    y_of = lambda k, j: (k - 2 * j)  # recombining layout
    # Draw edges
    for k in range(3):
        for j in range(k + 1):
            x0, y0 = x_of(k), y_of(k, j)
            x1, y1 = x_of(k + 1), y_of(k + 1, j)      # up child
            x2, y2 = x_of(k + 1), y_of(k + 1, j + 1)  # down child
            ax.plot([x0, x1], [y0, y1], color="#2a62a6", lw=1.2, alpha=0.6)
            ax.plot([x0, x2], [y0, y2], color="#a62a2a", lw=1.2, alpha=0.6)
    # Draw nodes with rate labels
    for (k, j), r_val in rates.items():
        xn, yn = x_of(k), y_of(k, j)
        ax.add_patch(plt.Circle((xn, yn), 0.16, facecolor="#fef3c7",
                                 edgecolor="#8a6508", lw=1.2, zorder=3))
        ax.text(xn, yn, f"{r_val*100:.2f}%", ha="center", va="center",
                fontsize=9.5, zorder=4)
    ax.set_xlim(-0.5, 3.8); ax.set_ylim(-3.5, 3.5)
    ax.set_xticks([0, 1, 2, 3]); ax.set_yticks([])
    ax.set_xlabel("time step $k$")
    ax.set_title("Calibrated short-rate tree — rates fitted to $P_0(1)\\ldots P_0(4)$")
    ax.grid(False)
    for spine in ["left", "right", "top"]:
        ax.spines[spine].set_visible(False)
    save("ch11-calibrated-tree.png")


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
    for fn in (ch01, ch02, ch03, ch04, ch05, ch06, ch07, ch08, ch09, ch10, ch10_mc, ch11, ch11_cal, ch12):
        try:
            fn()
        except Exception as e:
            print(f"  FAILED: {fn.__name__} — {type(e).__name__}: {e}")
    print("\nAll done -> docs/guide/figures/")
