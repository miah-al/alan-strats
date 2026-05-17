"""
Standalone figure builder for Chapter 0 (Math Refresher).

Run:  python docs/guide/_build_ch0_extra_figs.py

Outputs (under docs/guide/figures/):
    ch00-jensen-chord.png
    ch00-taylor-exp.png
    ch00-normal-lognormal.png
    ch00-cdf-pdf-quantile.png
    ch00-cond-exp-projection.png
    ch00-sigma-refinement.png
    ch00-clt-convergence.png
    ch00-lln-paths.png
    ch00-grad-levelsets.png
    ch00-mode-convergence.png
    ch00-cholesky-2d.png
    ch00-pca-equicorr.png
"""
from __future__ import annotations
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyArrow

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
def fig_jensen_chord():
    """Convex parabola y=x^2 with chord, gap labeled."""
    np.random.seed(0)
    x = np.linspace(-0.5, 2.5, 200)
    y = x ** 2
    fig, ax = plt.subplots(figsize=FIGSIZE)
    ax.plot(x, y, color="#1e3a8a", lw=2.2, label=r"$f(x) = x^2$")
    # Two sample points x1=0, x2=2
    x1, x2 = 0.0, 2.0
    ax.plot([x1, x2], [x1 ** 2, x2 ** 2], color="#c2410c", lw=2.0,
            label="chord")
    # Midpoint
    xm = 0.5 * (x1 + x2)
    f_xm = xm ** 2
    chord_at_xm = 0.5 * (x1 ** 2 + x2 ** 2)
    ax.scatter([x1, x2], [x1 ** 2, x2 ** 2], color="#c2410c", s=60, zorder=5)
    ax.scatter([xm], [f_xm], color="#1e3a8a", s=60, zorder=5)
    ax.scatter([xm], [chord_at_xm], color="#c2410c", s=60, zorder=5)
    # Gap arrow
    ax.annotate("", xy=(xm, chord_at_xm), xytext=(xm, f_xm),
                arrowprops=dict(arrowstyle="<->", color="#7f1d1d", lw=2))
    ax.text(xm + 0.08, 0.5 * (f_xm + chord_at_xm),
            f"Jensen gap = {chord_at_xm - f_xm:.2f}",
            fontsize=11, color="#7f1d1d",
            verticalalignment="center")
    ax.text(xm, chord_at_xm + 0.25,
            r"$\frac{1}{2}[f(x_1)+f(x_2)] = \mathbb{E}[f(X)]$",
            fontsize=10, color="#c2410c", ha="center")
    ax.text(xm, f_xm - 0.45,
            r"$f(\mathbb{E}[X]) = f(\bar x)$",
            fontsize=10, color="#1e3a8a", ha="center")
    ax.set_xlabel(r"$x$")
    ax.set_ylabel(r"$f(x)$")
    ax.set_title("Jensen's inequality: chord lies above the convex curve")
    ax.legend(loc="upper left", frameon=False)
    ax.set_xlim(-0.5, 2.7)
    ax.set_ylim(-1.0, 5.5)
    _save("ch00-jensen-chord.png")


# ---------------------------------------------------------------------
def fig_taylor_exp():
    """Taylor truncations of e^x at orders 1..5."""
    x = np.linspace(-2.5, 2.5, 400)
    fig, ax = plt.subplots(figsize=FIGSIZE)
    ax.plot(x, np.exp(x), color="black", lw=2.5, label=r"$e^x$ (exact)")
    coeffs = [1.0]  # constant term
    factorial = 1.0
    poly = np.ones_like(x)
    colors = ["#dc2626", "#ea580c", "#ca8a04", "#16a34a", "#0891b2"]
    for k in range(1, 6):
        factorial *= k
        poly = poly + x ** k / factorial
        ax.plot(x, poly, color=colors[k - 1], lw=1.5,
                label=fr"order {k}: $\sum_{{j=0}}^{{{k}}} x^j/j!$")
    ax.set_xlabel(r"$x$")
    ax.set_ylabel(r"$f(x)$")
    ax.set_title(r"Taylor series of $e^x$ truncated at orders 1 through 5")
    ax.legend(loc="upper left", frameon=False, fontsize=9)
    ax.set_ylim(-3, 14)
    _save("ch00-taylor-exp.png")


# ---------------------------------------------------------------------
def fig_normal_lognormal():
    """Normal vs lognormal density side-by-side."""
    np.random.seed(0)
    mu, sigma = 0.0, 0.4
    x_n = np.linspace(-1.6, 1.6, 400)
    pdf_n = np.exp(-0.5 * ((x_n - mu) / sigma) ** 2) / (sigma * np.sqrt(2 * np.pi))

    x_ln = np.linspace(0.01, 4.0, 400)
    pdf_ln = (np.exp(-0.5 * ((np.log(x_ln) - mu) / sigma) ** 2) /
              (x_ln * sigma * np.sqrt(2 * np.pi)))

    fig, axes = plt.subplots(1, 2, figsize=(10, 4.5))
    ax = axes[0]
    ax.plot(x_n, pdf_n, color="#1e3a8a", lw=2.2, label="density")
    ax.fill_between(x_n, 0, pdf_n, color="#1e3a8a", alpha=0.15)
    ax.axvline(mu, color="#c2410c", ls="--", lw=1.5, label=fr"$\mu = E[X] = {mu:.2f}$")
    ax.set_title(rf"Normal $\mathcal{{N}}({mu}, \,{sigma}^2)$")
    ax.set_xlabel(r"$x$")
    ax.set_ylabel("density")
    ax.legend(loc="upper right", frameon=False, fontsize=9)

    ax = axes[1]
    ax.plot(x_ln, pdf_ln, color="#16a34a", lw=2.2, label="density")
    ax.fill_between(x_ln, 0, pdf_ln, color="#16a34a", alpha=0.15)
    mean_ln = np.exp(mu + 0.5 * sigma ** 2)
    median_ln = np.exp(mu)
    ax.axvline(median_ln, color="#0891b2", ls=":", lw=1.5,
               label=fr"median $= e^\mu = {median_ln:.2f}$")
    ax.axvline(mean_ln, color="#c2410c", ls="--", lw=1.5,
               label=fr"mean $= e^{{\mu+\sigma^2/2}} = {mean_ln:.2f}$")
    ax.set_title(rf"Lognormal with $\log X \sim \mathcal{{N}}({mu},\,{sigma}^2)$")
    ax.set_xlabel(r"$x$")
    ax.set_ylabel("density")
    ax.legend(loc="upper right", frameon=False, fontsize=9)

    fig.suptitle("Normal vs lognormal: the lognormal mean exceeds its median by the Jensen gap",
                 fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    _save("ch00-normal-lognormal.png")


# ---------------------------------------------------------------------
def fig_cdf_pdf_quantile():
    """CDF / PDF / quantile relationship — three panels with one alpha point."""
    np.random.seed(0)
    x = np.linspace(-4, 4, 400)
    from math import erf, sqrt
    pdf = np.exp(-0.5 * x ** 2) / np.sqrt(2 * np.pi)
    cdf = 0.5 * (1 + np.vectorize(lambda t: erf(t / sqrt(2)))(x))
    # Mark VaR at alpha=0.05
    alpha = 0.05
    q = -1.6449  # qnorm(0.05)

    fig, axes = plt.subplots(1, 3, figsize=(12, 4))

    ax = axes[0]
    ax.plot(x, pdf, color="#1e3a8a", lw=2.2)
    mask = x <= q
    ax.fill_between(x[mask], 0, pdf[mask], color="#dc2626", alpha=0.4,
                    label=fr"area $=\alpha={alpha}$")
    ax.axvline(q, color="#dc2626", ls="--", lw=1.5)
    ax.set_title("PDF $f(x)$")
    ax.set_xlabel(r"$x$")
    ax.set_ylabel(r"$f(x)$")
    ax.legend(loc="upper right", frameon=False, fontsize=9)

    ax = axes[1]
    ax.plot(x, cdf, color="#1e3a8a", lw=2.2)
    ax.axhline(alpha, color="#dc2626", ls="--", lw=1.2)
    ax.axvline(q, color="#dc2626", ls="--", lw=1.2)
    ax.scatter([q], [alpha], color="#dc2626", s=60, zorder=5)
    ax.annotate(rf"$(q_\alpha, \,\alpha)$",
                xy=(q, alpha), xytext=(q + 0.5, alpha + 0.15),
                fontsize=10, color="#dc2626",
                arrowprops=dict(arrowstyle="->", color="#dc2626", lw=1))
    ax.set_title(r"CDF $F(x) = \mathbb{P}(X \leq x)$")
    ax.set_xlabel(r"$x$")
    ax.set_ylabel(r"$F(x)$")

    ax = axes[2]
    # Quantile function is F^{-1}
    u = np.linspace(0.001, 0.999, 400)
    from scipy.stats import norm
    Q = norm.ppf(u)
    ax.plot(u, Q, color="#1e3a8a", lw=2.2)
    ax.axvline(alpha, color="#dc2626", ls="--", lw=1.2)
    ax.axhline(q, color="#dc2626", ls="--", lw=1.2)
    ax.scatter([alpha], [q], color="#dc2626", s=60, zorder=5)
    ax.set_title(r"Quantile $F^{-1}(u)$")
    ax.set_xlabel(r"$u$ (probability)")
    ax.set_ylabel(r"$F^{-1}(u)$")

    fig.suptitle("PDF integrates to CDF; CDF inverts to quantile — three faces of the same distribution",
                 fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    _save("ch00-cdf-pdf-quantile.png")


# ---------------------------------------------------------------------
def fig_cond_exp_projection():
    """Conditional expectation as L^2 projection onto sub-sigma-algebra."""
    np.random.seed(0)
    # Hilbert-space picture: X as a vector, E[X|G] as projection on a subspace
    fig, ax = plt.subplots(figsize=FIGSIZE)
    # X = (1.5, 2.5)
    Xv = np.array([1.6, 2.6])
    # G-measurable subspace = horizontal axis
    proj = np.array([Xv[0], 0.0])
    # Plot vectors
    ax.annotate("", xy=Xv, xytext=(0, 0),
                arrowprops=dict(arrowstyle="->", color="#1e3a8a", lw=2.4))
    ax.text(Xv[0] + 0.05, Xv[1] + 0.1, r"$X$", fontsize=14, color="#1e3a8a")
    ax.annotate("", xy=proj, xytext=(0, 0),
                arrowprops=dict(arrowstyle="->", color="#c2410c", lw=2.4))
    ax.text(proj[0] + 0.05, proj[1] - 0.25,
            r"$\mathbb{E}[X \mid \mathcal{G}]$", fontsize=12, color="#c2410c")
    # Residual
    ax.plot([Xv[0], proj[0]], [Xv[1], proj[1]],
            color="#16a34a", lw=2, ls="--")
    ax.text(Xv[0] + 0.08, 0.5 * Xv[1] + 0.1,
            r"residual $X - \mathbb{E}[X\mid\mathcal{G}]$",
            fontsize=10, color="#16a34a")
    # Right-angle marker
    h = 0.18
    ax.plot([proj[0] - h, proj[0] - h, proj[0]],
            [0, h, h], color="black", lw=1)
    # The subspace (G-measurable functions) — horizontal "axis"
    ax.axhline(0, color="#0891b2", lw=1.5)
    ax.text(2.7, -0.2, r"$L^2(\mathcal{G})$  ($\mathcal{G}$-measurable subspace)",
            fontsize=10, color="#0891b2", ha="right")
    # Whole space label
    ax.text(2.7, 2.85, r"$L^2(\mathcal{F})$", fontsize=11, color="black", ha="right")
    ax.set_xlim(-0.4, 2.9)
    ax.set_ylim(-0.7, 3.1)
    ax.set_aspect("equal", adjustable="box")
    ax.set_title(r"$\mathbb{E}[X \mid \mathcal{G}]$ as $L^2$-projection of $X$ onto $\mathcal{G}$-measurable subspace")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.grid(False)
    for spine in ("top", "right", "bottom", "left"):
        ax.spines[spine].set_visible(False)
    _save("ch00-cond-exp-projection.png")


# ---------------------------------------------------------------------
def fig_sigma_refinement():
    """Sigma-algebra refinement: three nested partitions."""
    fig, axes = plt.subplots(1, 3, figsize=(12, 4))

    # Coarsest: 2 sets
    ax = axes[0]
    ax.add_patch(Rectangle((0, 0), 2, 2, facecolor="#dbeafe", edgecolor="black", lw=1.5))
    ax.add_patch(Rectangle((2, 0), 2, 2, facecolor="#fed7aa", edgecolor="black", lw=1.5))
    ax.text(1, 1, r"$A_1$", fontsize=14, ha="center")
    ax.text(3, 1, r"$A_2$", fontsize=14, ha="center")
    ax.set_title(r"$\mathcal{F}_0$  (coarsest)")
    ax.set_xlim(-0.2, 4.2)
    ax.set_ylim(-0.2, 2.2)
    ax.set_aspect("equal")
    ax.grid(False)
    ax.set_xticks([]); ax.set_yticks([])

    # Middle: 4 sets
    ax = axes[1]
    cells = [(0, 1), (0, 0), (2, 1), (2, 0)]
    colors_m = ["#dbeafe", "#bfdbfe", "#fed7aa", "#fdba74"]
    labels_m = ["$A_{11}$", "$A_{12}$", "$A_{21}$", "$A_{22}$"]
    for (x0, y0), c, lab in zip(cells, colors_m, labels_m):
        ax.add_patch(Rectangle((x0, y0), 2, 1, facecolor=c, edgecolor="black", lw=1.5))
        ax.text(x0 + 1, y0 + 0.5, lab, fontsize=12, ha="center")
    ax.set_title(r"$\mathcal{F}_1$  (refines $\mathcal{F}_0$)")
    ax.set_xlim(-0.2, 4.2)
    ax.set_ylim(-0.2, 2.2)
    ax.set_aspect("equal")
    ax.grid(False)
    ax.set_xticks([]); ax.set_yticks([])

    # Finest: 8 sets
    ax = axes[2]
    colors_f = ["#dbeafe", "#bfdbfe", "#93c5fd", "#60a5fa",
                "#fed7aa", "#fdba74", "#fb923c", "#f97316"]
    idx = 0
    for col in range(4):
        for row in (1, 0):
            ax.add_patch(Rectangle((col, row), 1, 1, facecolor=colors_f[idx],
                                   edgecolor="black", lw=1.0))
            idx += 1
    ax.set_title(r"$\mathcal{F}_2$  (refines $\mathcal{F}_1$)")
    ax.set_xlim(-0.2, 4.2)
    ax.set_ylim(-0.2, 2.2)
    ax.set_aspect("equal")
    ax.grid(False)
    ax.set_xticks([]); ax.set_yticks([])

    fig.suptitle(r"Filtration $\mathcal{F}_0 \subseteq \mathcal{F}_1 \subseteq \mathcal{F}_2$ — partitions refine as time passes",
                 fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    _save("ch00-sigma-refinement.png")


# ---------------------------------------------------------------------
def fig_clt_convergence():
    """CLT visualisation — sums of Bernoulli normalized."""
    np.random.seed(0)
    N_repeats = 20000
    # Per-panel y-axis (sharey=False): the n=1 Bernoulli spikes reach density
    # ~10 and visually flatten the n=64 panel under a shared scale.
    fig, axes = plt.subplots(1, 4, figsize=(13, 3.6))
    ns = [1, 4, 16, 64]
    for ax, n in zip(axes, ns):
        # Sum of n Bernoulli(0.5), centered and scaled
        S = np.random.binomial(1, 0.5, (N_repeats, n)).sum(axis=1)
        # Standardize: mean n/2, var n/4
        Z = (S - n / 2) / np.sqrt(n / 4)
        ax.hist(Z, bins=40, density=True, color="#1e3a8a",
                alpha=0.6, edgecolor="white", linewidth=0.3)
        xs = np.linspace(-4, 4, 200)
        ax.plot(xs, np.exp(-0.5 * xs ** 2) / np.sqrt(2 * np.pi),
                color="#c2410c", lw=2, label=r"$\mathcal{N}(0,1)$")
        ax.set_title(f"n = {n}")
        ax.set_xlim(-4, 4)
        ax.set_xlabel(r"$Z_n = (S_n - n/2)/\sqrt{n/4}$")
        if n == 1:
            ax.set_ylabel("density")
        ax.legend(loc="upper right", fontsize=9, frameon=False)
    fig.suptitle(r"CLT in action: standardised sums of i.i.d. Bernoulli$(1/2)$ converge to $\mathcal{N}(0,1)$",
                 fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    _save("ch00-clt-convergence.png")


# ---------------------------------------------------------------------
def fig_lln_paths():
    """Law of large numbers convergence paths."""
    np.random.seed(0)
    N = 5000
    paths = 6
    fig, ax = plt.subplots(figsize=FIGSIZE)
    for p in range(paths):
        X = np.random.standard_normal(N) + 0.5  # mean 0.5
        means = np.cumsum(X) / np.arange(1, N + 1)
        ax.plot(np.arange(1, N + 1), means, lw=1.2, alpha=0.75)
    ax.axhline(0.5, color="black", lw=1.5, ls="--",
               label=r"$\mathbb{E}[X] = 0.5$")
    ax.set_xscale("log")
    ax.set_xlabel(r"$N$ (sample size, log scale)")
    ax.set_ylabel(r"$\bar X_N = (1/N)\sum_{n=1}^N X_n$")
    ax.set_title("Strong Law of Large Numbers: six independent sample-mean paths all converge to $\\mathbb{E}[X]$")
    ax.legend(loc="upper right", frameon=False)
    ax.set_ylim(-0.6, 1.6)
    _save("ch00-lln-paths.png")


# ---------------------------------------------------------------------
def fig_grad_levelsets():
    """Gradient field plus level sets of a 2-D function."""
    x = np.linspace(-2, 2, 200)
    y = np.linspace(-2, 2, 200)
    X, Y = np.meshgrid(x, y)
    Z = 0.5 * X ** 2 + Y ** 2  # ellipsoidal "loss"
    fig, ax = plt.subplots(figsize=FIGSIZE)
    cs = ax.contour(X, Y, Z, levels=[0.2, 0.5, 1.0, 1.8, 2.8],
                    colors="#1e3a8a", linewidths=1.5)
    ax.clabel(cs, fontsize=9, inline=True, fmt="%.1f")
    # Gradient field (downsample)
    xs = np.linspace(-1.8, 1.8, 15)
    ys = np.linspace(-1.8, 1.8, 15)
    Xs, Ys = np.meshgrid(xs, ys)
    Gx, Gy = Xs, 2 * Ys
    norm = np.sqrt(Gx ** 2 + Gy ** 2)
    Gx_n = Gx / (norm + 1e-9) * 0.18
    Gy_n = Gy / (norm + 1e-9) * 0.18
    ax.quiver(Xs, Ys, Gx_n, Gy_n, color="#c2410c", scale=1, scale_units="xy",
              angles="xy", width=0.003, alpha=0.9)
    ax.set_xlabel(r"$x_1$")
    ax.set_ylabel(r"$x_2$")
    ax.set_title(r"Level sets (blue) and gradient field (orange) of $f(x_1,x_2)=\frac{1}{2} x_1^2 + x_2^2$" +
                 "\nGradient points outward, perpendicular to level sets")
    ax.set_aspect("equal")
    _save("ch00-grad-levelsets.png")


# ---------------------------------------------------------------------
def fig_mode_convergence():
    """Modes of convergence — separating example."""
    np.random.seed(0)
    # X_n where P(X_n = n^2)=1/n, P(X_n=0)=1-1/n
    ns = np.arange(1, 200)
    P_nonzero = 1.0 / ns
    means = ns  # E[X_n] = n
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))

    ax = axes[0]
    ax.plot(ns, P_nonzero, color="#1e3a8a", lw=2)
    ax.set_xlabel("n")
    ax.set_ylabel(r"$\mathbb{P}(X_n \neq 0) = 1/n$")
    ax.set_title(r"$X_n \to 0$ in probability ($\,\mathbb{P}(X_n \neq 0) \to 0$)")
    ax.set_xscale("log")
    ax.set_yscale("log")

    ax = axes[1]
    ax.plot(ns, means, color="#c2410c", lw=2)
    ax.set_xlabel("n")
    ax.set_ylabel(r"$\mathbb{E}[X_n] = n$")
    ax.set_title(r"$\mathbb{E}[X_n] = n \to \infty$  (no $L^1$ convergence)")
    ax.set_xscale("log")
    ax.set_yscale("log")

    fig.suptitle(r"Convergence in probability does not imply $L^1$: "
                 r"$\mathbb{P}(X_n = n^2)=1/n$ produces $X_n\!\to_\mathbb{P}\!0$ but $\mathbb{E}[X_n]=n\to\infty$",
                 fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    _save("ch00-mode-convergence.png")


# ---------------------------------------------------------------------
def fig_cholesky_2d():
    """Cholesky factorisation visualised: independent draws -> correlated cloud."""
    np.random.seed(0)
    N = 800
    Z = np.random.standard_normal((2, N))
    rho = -0.7
    L = np.array([[1, 0], [rho, np.sqrt(1 - rho ** 2)]])
    X = L @ Z

    fig, axes = plt.subplots(1, 2, figsize=(11, 5))
    ax = axes[0]
    ax.scatter(Z[0], Z[1], s=6, color="#1e3a8a", alpha=0.45)
    ax.set_title(r"Independent draws $Z \sim \mathcal{N}(0, I)$")
    ax.set_xlabel(r"$Z_1$")
    ax.set_ylabel(r"$Z_2$")
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlim(-3.5, 3.5); ax.set_ylim(-3.5, 3.5)

    ax = axes[1]
    ax.scatter(X[0], X[1], s=6, color="#c2410c", alpha=0.45)
    ax.set_title(rf"$X = L Z$ with $\rho = {rho}$ (target correlation)")
    ax.set_xlabel(r"$X_1$")
    ax.set_ylabel(r"$X_2$")
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlim(-3.5, 3.5); ax.set_ylim(-3.5, 3.5)
    # Annotate empirical correlation
    emp_corr = np.corrcoef(X)[0, 1]
    ax.text(0.05, 0.95,
            f"empirical $\\hat\\rho = {emp_corr:.3f}$",
            transform=ax.transAxes, fontsize=10, verticalalignment="top",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor="gray"))

    fig.suptitle(r"Cholesky $L=[1,0;\rho,\sqrt{1-\rho^2}]$ "
                 r"turns independent $Z$ into correlated $X$",
                 fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.91))
    _save("ch00-cholesky-2d.png")


# ---------------------------------------------------------------------
def fig_pca_equicorr():
    """Spectrum of equicorrelation matrix vs rho."""
    n = 5
    # Avoid the two singularities at rho = -1/(n-1) = -0.25 and rho = 1.
    rho_lo = np.linspace(-0.99 / (n - 1), -0.30, 200)
    rho_hi = np.linspace(-0.20, 0.99, 400)
    rhos = np.concatenate([rho_lo, rho_hi])
    lam_top = 1 + (n - 1) * rhos
    lam_other = 1 - rhos
    # Correct condition number = max(|lam|) / min(|lam|) over the spectrum.
    abs_top = np.abs(lam_top)
    abs_other = np.abs(lam_other)
    lam_max = np.maximum(abs_top, abs_other)
    lam_min = np.minimum(abs_top, abs_other)
    cond = lam_max / lam_min

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    ax = axes[0]
    ax.plot(rhos, lam_top, color="#1e3a8a", lw=2.2,
            label=fr"$\lambda_1 = 1 + (n-1)\rho$  ($n={n}$)")
    ax.plot(rhos, lam_other, color="#c2410c", lw=2.2,
            label=r"$\lambda_2=\dots=\lambda_n = 1 - \rho$")
    ax.axhline(0, color="black", lw=0.5)
    ax.set_xlabel(r"$\rho$  (off-diagonal correlation)")
    ax.set_ylabel("eigenvalues")
    ax.set_title(r"Eigenvalues of the $5\times 5$ equicorrelation matrix")
    ax.legend(loc="upper left", frameon=False, fontsize=9)

    ax = axes[1]
    ax.plot(rhos, cond, color="#16a34a", lw=2.2)
    ax.set_yscale("log")
    ax.set_xlabel(r"$\rho$")
    ax.set_ylabel(r"$\kappa = \lambda_{\max}/\lambda_{\min}$")
    ax.set_title(r"Condition number $\to\infty$ at $\rho = -1/(n-1) = -0.25$ and $\rho \to 1$")
    ax.axhline(1, color="black", lw=0.5)
    ax.axvline(-1 / (n - 1), color="#7f1d1d", ls="--", lw=0.8, alpha=0.7)
    fig.tight_layout()
    _save("ch00-pca-equicorr.png")


# ---------------------------------------------------------------------
if __name__ == "__main__":
    fig_jensen_chord()
    fig_taylor_exp()
    fig_normal_lognormal()
    fig_cdf_pdf_quantile()
    fig_cond_exp_projection()
    fig_sigma_refinement()
    fig_clt_convergence()
    fig_lln_paths()
    fig_grad_levelsets()
    fig_mode_convergence()
    fig_cholesky_2d()
    fig_pca_equicorr()
    print("Chapter 0 extras: done")
