"""
Standalone figure builder for Chapter 2 (Multi-Period Binomial and FTAP).

Run:  python docs/guide/_build_ch2_extra_figs.py

Outputs (under docs/guide/figures/):
    ch02-recombining-tree.png
    ch02-backward-induction.png
    ch02-rn-measure-evolution.png
    ch02-numeraire-rebasing.png
    ch02-american-boundary.png
"""
from __future__ import annotations
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrow, Rectangle

FIG = os.path.join(os.path.dirname(__file__), "figures")
os.makedirs(FIG, exist_ok=True)
DPI = 200
FIGSIZE = (8, 5)

plt.rcParams.update({
    "figure.facecolor": "white",
    "axes.grid": True,
    "grid.alpha": 0.3,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "font.size": 11,
})


def _save(name):
    path = os.path.join(FIG, name)
    plt.savefig(path, dpi=DPI, bbox_inches="tight")
    plt.close()
    print(f"  wrote {name}")


# ---------------------------------------------------------------------
def fig_recombining_tree():
    """Side-by-side: non-recombining 2^N tree vs recombining (N+1)-node tree."""
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # Left: non-recombining binary tree, depth 3
    ax = axes[0]
    depth = 3
    # Place nodes
    for n in range(depth + 1):
        n_nodes = 2 ** n
        xs = np.full(n_nodes, n)
        ys = np.linspace(-0.5 * (n_nodes - 1), 0.5 * (n_nodes - 1), n_nodes) if n_nodes > 1 else np.array([0.0])
        ax.scatter(xs, ys, color="#1e3a8a", s=80, zorder=3)
        if n < depth:
            n_next = 2 ** (n + 1)
            ys_next = np.linspace(-0.5 * (n_next - 1), 0.5 * (n_next - 1), n_next)
            for i in range(n_nodes):
                # Each node connects to 2 children
                ax.plot([n, n + 1], [ys[i], ys_next[2 * i]], color="#94a3b8", lw=1.0)
                ax.plot([n, n + 1], [ys[i], ys_next[2 * i + 1]], color="#94a3b8", lw=1.0)
    ax.set_title(r"Non-recombining tree: $2^N$ terminal nodes")
    ax.set_xlabel("time step")
    ax.set_yticks([])
    ax.text(depth + 0.1, 0, f"{2**depth} terminal\nnodes",
            fontsize=10, color="#1e3a8a", verticalalignment="center")
    ax.set_xlim(-0.4, depth + 1.3)
    ax.set_ylim(-5, 5)

    # Right: recombining (N+1) lattice
    ax = axes[1]
    for n in range(depth + 1):
        n_nodes = n + 1
        xs = np.full(n_nodes, n)
        ys = np.linspace(-0.5 * n, 0.5 * n, n_nodes) if n_nodes > 1 else np.array([0.0])
        ax.scatter(xs, ys, color="#c2410c", s=110, zorder=3)
        if n < depth:
            ys_next = np.linspace(-0.5 * (n + 1), 0.5 * (n + 1), n + 2)
            for i in range(n_nodes):
                ax.plot([n, n + 1], [ys[i], ys_next[i]], color="#94a3b8", lw=1.2)      # down
                ax.plot([n, n + 1], [ys[i], ys_next[i + 1]], color="#94a3b8", lw=1.2)  # up
    # Highlight u-d = d-u recombination box
    ax.add_patch(Rectangle((0.9, -0.6), 1.2, 1.2,
                           fill=False, edgecolor="#16a34a", lw=2.0, linestyle="--"))
    ax.text(1.5, 0.85, "ud = du\nrecombination",
            fontsize=9, color="#16a34a", ha="center")
    ax.set_title(r"Recombining tree: $N+1$ terminal nodes")
    ax.set_xlabel("time step")
    ax.set_yticks([])
    ax.text(depth + 0.1, 0, f"{depth + 1} terminal\nnodes",
            fontsize=10, color="#c2410c", verticalalignment="center")
    ax.set_xlim(-0.4, depth + 1.3)
    ax.set_ylim(-2.5, 2.5)

    fig.suptitle(r"Recombination collapses $2^N \to N+1$ — the algorithmic key that makes lattice pricing feasible",
                 fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    _save("ch02-recombining-tree.png")


# ---------------------------------------------------------------------
def fig_backward_induction():
    """Backward induction on a 3-step CRR tree pricing a call."""
    np.random.seed(0)
    S0 = 100.0
    sigma = 0.30
    r = 0.05
    T = 0.5
    N = 3
    dt = T / N
    u = float(np.exp(sigma * np.sqrt(dt)))
    d = 1.0 / u
    q = (np.exp(r * dt) - d) / (u - d)
    K = 100.0

    # Build S grid: S[n, k] = stock at node (n, k), k = number of up moves
    S = np.zeros((N + 1, N + 1))
    for n in range(N + 1):
        for k in range(n + 1):
            S[n, k] = S0 * (u ** k) * (d ** (n - k))

    # Backward induction
    C = np.zeros((N + 1, N + 1))
    C[N, :] = np.maximum(S[N, :] - K, 0.0)
    for n in range(N - 1, -1, -1):
        for k in range(n + 1):
            C[n, k] = np.exp(-r * dt) * (q * C[n + 1, k + 1] + (1 - q) * C[n + 1, k])

    # Plot
    fig, ax = plt.subplots(figsize=(10, 6))
    # Draw edges first (low zorder) so labels can mask them
    for n in range(N):
        for k in range(n + 1):
            y = (k - n / 2.0)
            ax.plot([n, n + 1], [y, y + 0.5], color="#94a3b8", lw=1.0, zorder=1)
            ax.plot([n, n + 1], [y, y - 0.5], color="#94a3b8", lw=1.0, zorder=1)
    # Draw nodes + labels on top with white-background bbox to mask edges underneath
    label_bbox = dict(boxstyle="round,pad=0.18", facecolor="white",
                      edgecolor="#1e3a8a", linewidth=0.8)
    for n in range(N + 1):
        for k in range(n + 1):
            x = n
            y = (k - n / 2.0)
            ax.text(x, y,
                    f"S = {S[n, k]:.1f}\nC = {C[n, k]:.2f}",
                    fontsize=9, ha="center", va="center",
                    color="#1e3a8a",
                    bbox=label_bbox, zorder=5)
    # Backward induction arrow annotations
    ax.annotate("", xy=(0.4, -1.8), xytext=(2.6, -1.8),
                arrowprops=dict(arrowstyle="->", color="#7f1d1d", lw=2))
    ax.text(1.5, -2.0, "backward induction (discount $\\times$ $q$-weighted)",
            fontsize=10, color="#7f1d1d", ha="center")
    ax.set_xlabel("time step $n$")
    ax.set_xticks(range(N + 1))
    ax.set_yticks([])
    ax.set_title(f"3-step CRR backward induction: call $K={K:.0f}$, $\\sigma$={sigma*100:.0f}%, $r$={r*100:.0f}%\n"
                 f"$q={q:.3f}$, root price $C_0 = {C[0, 0]:.2f}$  (CRR 1979 $\\to$ Black–Scholes in the limit)",
                 fontsize=10)
    ax.set_xlim(-0.4, N + 0.6)
    ax.set_ylim(-2.4, 2.2)
    ax.grid(False)
    _save("ch02-backward-induction.png")


# ---------------------------------------------------------------------
def fig_rn_measure_evolution():
    """How the risk-neutral measure assigns mass on terminal nodes as N grows."""
    np.random.seed(0)
    S0 = 100.0
    sigma = 0.25
    r = 0.04
    T = 1.0

    fig, axes = plt.subplots(1, 3, figsize=(13, 4.5))
    Ns = [4, 16, 64]
    for ax, N in zip(axes, Ns):
        dt = T / N
        u = float(np.exp(sigma * np.sqrt(dt)))
        d = 1.0 / u
        q = (np.exp(r * dt) - d) / (u - d)
        ks = np.arange(N + 1)
        # Binomial(N, q) probabilities
        from math import comb
        probs = np.array([comb(N, int(k)) * (q ** k) * ((1 - q) ** (N - k)) for k in ks])
        ST = S0 * (u ** ks) * (d ** (N - ks))
        ax.bar(ST, probs, width=(ST.max() - ST.min()) / max(N, 4) * 0.8,
               color="#1e3a8a", alpha=0.7, edgecolor="white")
        # Overlay lognormal limit
        xs = np.linspace(ST.min() * 0.7, ST.max() * 1.3, 400)
        mu_log = np.log(S0) + (r - 0.5 * sigma ** 2) * T
        sd_log = sigma * np.sqrt(T)
        ln_pdf = np.exp(-0.5 * ((np.log(xs) - mu_log) / sd_log) ** 2) / (
            xs * sd_log * np.sqrt(2 * np.pi))
        # Rescale lognormal to match bar heights at scale
        ln_pdf_scaled = ln_pdf * (ST.max() - ST.min()) / max(N, 4) * 0.8
        ax.plot(xs, ln_pdf_scaled, color="#c2410c", lw=2,
                label="lognormal limit")
        ax.axvline(S0 * np.exp(r * T), color="#16a34a", ls="--", lw=1.2,
                   label=fr"$S_0 e^{{rT}}={S0*np.exp(r*T):.1f}$")
        ax.set_title(f"$N={N}$ steps")
        ax.set_xlabel(r"$S_T$")
        if N == 4:
            ax.set_ylabel(r"$\mathbb{Q}$-probability mass")
        if N == 64:
            ax.legend(loc="upper right", frameon=False, fontsize=9)
    fig.suptitle(r"Risk-neutral binomial mass on $S_T$ converges to the lognormal as $N \to \infty$",
                 fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    _save("ch02-rn-measure-evolution.png")


# ---------------------------------------------------------------------
def fig_numeraire_rebasing():
    """Same price, two numeraires: money-market vs stock-as-numeraire."""
    np.random.seed(0)
    # Simulate a single sample path
    N = 64
    T = 1.0
    dt = T / N
    r = 0.04
    sigma = 0.2
    S0 = 100.0
    Z = np.random.standard_normal(N)
    logS = np.log(S0) + np.cumsum((r - 0.5 * sigma ** 2) * dt + sigma * np.sqrt(dt) * Z)
    S = np.concatenate(([S0], np.exp(logS)))
    B = np.exp(r * np.arange(N + 1) * dt)

    t = np.linspace(0, T, N + 1)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))

    ax = axes[0]
    ax.plot(t, S, color="#1e3a8a", lw=1.8, label=r"$S_t$ (stock)")
    ax.plot(t, B * S0 / B[0], color="#c2410c", lw=1.8,
            label=fr"$B_t = e^{{rt}}\cdot S_0$ (numeraire scaled)")
    ax.set_xlabel("$t$")
    ax.set_ylabel("price")
    ax.set_title(r"Raw prices under $\mathbb{Q}$")
    ax.legend(loc="upper left", frameon=False, fontsize=9)

    ax = axes[1]
    discS = S / B
    ax.plot(t, discS, color="#16a34a", lw=1.8,
            label=r"$\tilde S_t = S_t / B_t$")
    ax.axhline(S0, color="black", ls="--", lw=1, alpha=0.6,
               label=fr"$\mathbb{{E}}^\mathbb{{Q}}[\tilde S_t] = S_0$")
    ax.set_xlabel("$t$")
    ax.set_ylabel(r"$S_t / B_t$")
    ax.set_title(r"Discounted price (numeraire $=B_t$): $\mathbb{Q}$-martingale")
    ax.legend(loc="upper left", frameon=False, fontsize=9)

    fig.suptitle("FTAP: choose the numeraire and discounted prices become martingales — same maths underlies forward measure $T$-pricing",
                 fontsize=10.5)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    _save("ch02-numeraire-rebasing.png")


# ---------------------------------------------------------------------
def fig_american_boundary():
    """American put: exercise boundary on CRR tree."""
    np.random.seed(0)
    S0 = 100.0
    K = 100.0
    sigma = 0.30
    r = 0.04
    T = 1.0
    N = 80
    dt = T / N
    u = float(np.exp(sigma * np.sqrt(dt)))
    d = 1.0 / u
    q = (np.exp(r * dt) - d) / (u - d)

    # Stock grid: S[n, k] for k=0..n
    S = [np.array([S0 * (u ** k) * (d ** (n - k)) for k in range(n + 1)])
         for n in range(N + 1)]

    # Backward induction with early exercise
    V_terminal = np.maximum(K - S[N], 0.0)
    V = [None] * (N + 1)
    V[N] = V_terminal
    exercise = [None] * (N + 1)
    exercise[N] = (K - S[N] > 0).astype(int)
    for n in range(N - 1, -1, -1):
        cont = np.exp(-r * dt) * (q * V[n + 1][1:] + (1 - q) * V[n + 1][:-1])
        intrinsic = np.maximum(K - S[n], 0.0)
        V[n] = np.maximum(cont, intrinsic)
        exercise[n] = (intrinsic > cont).astype(int)

    # For each n, find boundary = highest stock price at which exercise is optimal
    boundary = []
    times = []
    for n in range(N + 1):
        exer_mask = exercise[n] == 1
        if np.any(exer_mask):
            # Largest stock value where we exercise
            boundary.append(S[n][exer_mask].max())
        else:
            boundary.append(np.nan)
        times.append(n * dt)

    boundary = np.array(boundary)
    times = np.array(times)

    fig, ax = plt.subplots(figsize=FIGSIZE)
    # Shade exercise region (below boundary)
    valid = ~np.isnan(boundary)
    ax.fill_between(times[valid], 50, boundary[valid], color="#dc2626", alpha=0.18,
                    label="exercise region")
    ax.fill_between(times[valid], boundary[valid], 150, color="#16a34a", alpha=0.10,
                    label="continuation region")
    ax.plot(times, boundary, color="#7f1d1d", lw=2.0, marker=".", ms=4,
            label=r"early-exercise boundary $S^\star(t)$")
    ax.axhline(K, color="black", ls="--", lw=1, alpha=0.6, label=f"strike $K={K:.0f}$")
    ax.set_xlabel("$t$ (years)")
    ax.set_ylabel("$S$")
    ax.set_title(rf"American put early-exercise boundary ($\sigma$={sigma*100:.0f}%, $r$={r*100:.0f}%, $T={T:.0f}$y)" +
                 "\nRising boundary as $t\\to T$: holders exercise sooner when little time-value remains" +
                 " — mirrors mortgage prepayment timing in low-rate refis")
    ax.set_xlim(0, T)
    ax.set_ylim(55, 110)
    ax.legend(loc="lower right", frameon=False, fontsize=9)
    _save("ch02-american-boundary.png")


# ---------------------------------------------------------------------
if __name__ == "__main__":
    fig_recombining_tree()
    fig_backward_induction()
    fig_rn_measure_evolution()
    fig_numeraire_rebasing()
    fig_american_boundary()
    print("Chapter 2 extras: done")
