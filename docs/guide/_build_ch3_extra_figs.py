"""
Standalone figure builder for Chapter 3 (Stochastic Calculus Primer).

Run:  python docs/guide/_build_ch3_extra_figs.py

Outputs (under docs/guide/figures/):
    ch03-bb-paths.png          (Brownian Bridge sample paths + variance envelope)
    ch03-bb-vs-bm.png          (BM endpoints free vs BB endpoints pinned)
    ch03-ito-multiplication.png
    ch03-sde-correlated.png
"""
from __future__ import annotations
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

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


def _bb_paths(n_paths, n_steps, T, b_endpoint):
    """Simulate Brownian Bridges starting at 0, ending at b_endpoint at time T."""
    dt = T / n_steps
    t = np.linspace(0, T, n_steps + 1)
    paths = np.zeros((n_paths, n_steps + 1))
    for i in range(n_paths):
        Z = np.random.standard_normal(n_steps)
        W = np.concatenate(([0.0], np.cumsum(np.sqrt(dt) * Z)))
        # Bridge transformation: B_t = W_t - (t/T) * W_T + (t/T) * b
        paths[i] = W - (t / T) * W[-1] + (t / T) * b_endpoint
    return t, paths


# ---------------------------------------------------------------------
def fig_bb_paths():
    """Brownian Bridge sample paths with mean line and ±2σ envelope."""
    np.random.seed(0)
    T = 1.0
    b = 0.5
    n_steps = 400
    n_paths = 12
    t, paths = _bb_paths(n_paths, n_steps, T, b)

    fig, ax = plt.subplots(figsize=FIGSIZE)
    for i in range(n_paths):
        ax.plot(t, paths[i], color="#1e3a8a", lw=0.9, alpha=0.5)
    # Mean line t*b/T
    mean = t * b / T
    ax.plot(t, mean, color="black", lw=2.0,
            label=fr"mean $= t b/T$  ($b={b}$)")
    # ±2σ envelope: var = t(T-t)/T
    var = t * (T - t) / T
    sd = np.sqrt(var)
    ax.fill_between(t, mean - 2 * sd, mean + 2 * sd, color="#c2410c", alpha=0.18,
                    label=r"$\pm 2\sigma$ envelope, $\sigma^2 = t(T-t)/T$")
    # Pin points
    ax.scatter([0, T], [0, b], color="#7f1d1d", s=80, zorder=5,
               label=fr"pins $B_0=0,\, B_T={b}$")
    ax.set_xlabel("$t$")
    ax.set_ylabel(r"$B_t$")
    ax.set_title(r"Brownian Bridge on $[0,1]$ pinned at $B_0=0, B_T=0.5$" +
                 "\n12 sample paths, mean $tb/T$, variance envelope $t(T-t)/T$")
    ax.legend(loc="upper left", frameon=False, fontsize=9)
    _save("ch03-bb-paths.png")


# ---------------------------------------------------------------------
def fig_bb_vs_bm():
    """Free Brownian motion endpoints versus pinned Brownian Bridge endpoints."""
    np.random.seed(0)
    T = 1.0
    n_steps = 400
    n_paths = 30
    dt = T / n_steps
    t = np.linspace(0, T, n_steps + 1)

    # Free BM
    free_paths = np.zeros((n_paths, n_steps + 1))
    for i in range(n_paths):
        Z = np.random.standard_normal(n_steps)
        free_paths[i] = np.concatenate(([0.0], np.cumsum(np.sqrt(dt) * Z)))

    # Pinned BB at endpoint b=0.4
    b = 0.4
    _, bridge_paths = _bb_paths(n_paths, n_steps, T, b)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), sharey=True)

    ax = axes[0]
    for i in range(n_paths):
        ax.plot(t, free_paths[i], color="#1e3a8a", lw=0.7, alpha=0.45)
    # Endpoint scatter
    ax.scatter(np.full(n_paths, T), free_paths[:, -1],
               color="#1e3a8a", s=22, alpha=0.7, zorder=5)
    ax.axhline(0, color="black", lw=0.8, alpha=0.5)
    ax.set_xlabel("$t$")
    ax.set_ylabel(r"$W_t$")
    ax.set_title("Free Brownian motion — endpoints scatter")

    ax = axes[1]
    for i in range(n_paths):
        ax.plot(t, bridge_paths[i], color="#c2410c", lw=0.7, alpha=0.45)
    ax.scatter([T], [b], color="#7f1d1d", s=80, zorder=5,
               label=fr"pinned at $B_T = {b}$")
    ax.scatter([0], [0], color="#7f1d1d", s=80, zorder=5)
    ax.axhline(0, color="black", lw=0.8, alpha=0.5)
    ax.set_xlabel("$t$")
    ax.set_title(r"Brownian Bridge — endpoints pinned at $0$ and $b$")
    ax.legend(loc="upper left", frameon=False, fontsize=9)

    fig.suptitle("Brownian Bridge conditions a BM on its endpoints — the distribution between is exactly a bridge, used in MC barrier-option corrections (Ch. 9)",
                 fontsize=10.5)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    _save("ch03-bb-vs-bm.png")


# ---------------------------------------------------------------------
def fig_ito_multiplication():
    """Empirical demonstration of (dW)^2 = dt: sums of squared increments converge."""
    np.random.seed(0)
    T = 1.0
    Ns = [50, 200, 1000, 5000]
    fig, ax = plt.subplots(figsize=FIGSIZE)
    for N in Ns:
        dt = T / N
        Z = np.random.standard_normal(N)
        dW = np.sqrt(dt) * Z
        cum_qv = np.cumsum(dW ** 2)
        t = np.linspace(dt, T, N)
        ax.plot(t, cum_qv, lw=1.3, alpha=0.8, label=fr"$N={N}$")
    ax.plot([0, T], [0, T], color="black", lw=2.5, ls="--",
            label=r"theoretical $[W]_t = t$")
    ax.set_xlabel("$t$")
    ax.set_ylabel(r"$\sum_{k:\,t_k \leq t} (\Delta W_k)^2$")
    ax.set_title(r"Empirical quadratic variation $\to t$ at finer mesh — the law $(\mathrm{d}W)^2 = \mathrm{d}t$ at work" +
                 "\nVariance-swap PnL on SPX is the same identity made tradable: integrated realised vol settles deterministically to $\\sigma^2 T$")
    ax.legend(loc="upper left", frameon=False, fontsize=9)
    _save("ch03-ito-multiplication.png")


# ---------------------------------------------------------------------
def fig_sde_correlated():
    """Two correlated Brownian motions via Cholesky."""
    np.random.seed(0)
    T = 1.0
    N = 1000
    dt = T / N
    t = np.linspace(0, T, N + 1)
    rho = -0.6
    L = np.array([[1.0, 0.0], [rho, float(np.sqrt(1 - rho ** 2))]])

    Z = np.random.standard_normal((2, N))
    dW = L @ Z * float(np.sqrt(dt))
    W = np.zeros((2, N + 1))
    W[:, 1:] = np.cumsum(dW, axis=1)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))

    ax = axes[0]
    ax.plot(t, W[0], color="#1e3a8a", lw=1.3, label=r"$W^1_t$")
    ax.plot(t, W[1], color="#c2410c", lw=1.3, label=fr"$W^2_t$  ($\rho={rho}$)")
    ax.set_xlabel("$t$")
    ax.set_ylabel("$W_t$")
    ax.set_title("Two correlated Brownian paths")
    ax.legend(loc="upper left", frameon=False, fontsize=9)

    # Right panel: scatter of increments
    ax = axes[1]
    dW1 = np.diff(W[0])
    dW2 = np.diff(W[1])
    ax.scatter(dW1, dW2, s=4, color="#16a34a", alpha=0.4)
    ax.axhline(0, color="black", lw=0.5)
    ax.axvline(0, color="black", lw=0.5)
    emp = np.corrcoef(dW1, dW2)[0, 1]
    ax.set_xlabel(r"$\mathrm{d}W^1$")
    ax.set_ylabel(r"$\mathrm{d}W^2$")
    ax.set_title(rf"Increment cloud (target $\rho={rho}$, empirical $\hat\rho={emp:.3f}$)")
    ax.set_aspect("equal", adjustable="box")

    fig.suptitle(r"Cholesky-driven correlated Brownians — the noise model for Heston ($\rho^{SPX,VIX} \approx -0.7$)",
                 fontsize=10.5)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    _save("ch03-sde-correlated.png")


# ---------------------------------------------------------------------
if __name__ == "__main__":
    fig_bb_paths()
    fig_bb_vs_bm()
    fig_ito_multiplication()
    fig_sde_correlated()
    print("Chapter 3 extras: done")
