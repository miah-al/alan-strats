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
# Cover page (used by _make_pandoc_pdf.py as the first page)
# ────────────────────────────────────────────────────────────
def cover():
    print("COVER:")
    import matplotlib.patches as mpatches
    from matplotlib.colors import LinearSegmentedColormap

    # Full-page canvas (8.5 x 11 inches — US letter, portrait)
    fig = plt.figure(figsize=(8.5, 11), facecolor="#0a0a2e")
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    ax.grid(False)

    # FULL-PAGE diagonal gradient: deep midnight → electric purple → hot magenta → amber glow
    nx, ny = 600, 800
    X, Y = np.meshgrid(np.linspace(0, 1, nx), np.linspace(0, 1, ny))
    # Diagonal from top-left to bottom-right with a radial warm spot at lower-right
    diag = (X + (1 - Y)) / 2
    radial = np.sqrt((X - 0.75)**2 + (Y - 0.15)**2)
    field = 0.70 * diag + 0.30 * (1 - radial)
    field = (field - field.min()) / (field.max() - field.min())
    grad_cmap = LinearSegmentedColormap.from_list(
        "spicy", ["#1e3a8a", "#4338ca", "#6366f1", "#818cf8", "#c7d2fe"]
    )
    ax.imshow(field, aspect="auto", extent=(0, 1, 0, 1),
              cmap=grad_cmap, zorder=1, origin="lower")

    # Subtle equation watermark across the page
    eqns = [
        r"$\mathrm{d}S_t = \mu S_t\,\mathrm{d}t + \sigma S_t\,\mathrm{d}W_t$",
        r"$\partial_t g + \frac{1}{2}\sigma^2 S^2 \partial_{SS} g + rS\partial_S g = rg$",
        r"$\mathrm{d}r_t = \kappa(\theta - r_t)\,\mathrm{d}t + \sigma\,\mathrm{d}W_t$",
        r"$[W,W]_t = t$",
        r"$\mathbb{E}^{\mathbb{Q}}[X]$",
        r"$\int_0^t g_s\,\mathrm{d}W_s$",
        r"$\mathrm{d}v_t = \kappa(\theta - v_t)\,\mathrm{d}t + \xi\sqrt{v_t}\,\mathrm{d}W_t$",
        r"$\varphi(u) = \mathbb{E}[e^{iuX}]$",
    ]
    rng = np.random.default_rng(7)
    for _ in range(28):
        eq = eqns[rng.integers(len(eqns))]
        x, y = rng.uniform(0.02, 0.98), rng.uniform(0.02, 0.98)
        s = rng.uniform(10, 22)
        a = rng.uniform(0.07, 0.18)
        rot = rng.uniform(-8, 8)
        ax.text(x, y, eq, fontsize=s, color="white", alpha=a,
                ha="center", va="center", rotation=rot, zorder=2)

    # Gold accent bar above title
    ax.add_patch(mpatches.Rectangle((0.20, 0.842), 0.60, 0.004,
                                     facecolor="#fbbf24", zorder=3))

    # Title card (semi-transparent overlay panel for readability)
    ax.add_patch(mpatches.FancyBboxPatch(
        (0.08, 0.54), 0.84, 0.28, boxstyle="round,pad=0.015,rounding_size=0.02",
        facecolor="#000000", alpha=0.35, edgecolor="#fbbf24", lw=1.5, zorder=3))

    # Title
    ax.text(0.5, 0.77, "QUANT COURSE", color="#fbbf24",
            fontsize=14, fontweight="bold", ha="center", va="center",
            family="sans-serif", zorder=4)
    ax.text(0.5, 0.70, "Arbitrage Pricing", color="white",
            fontsize=54, fontweight="bold", ha="center", va="center",
            family="serif", zorder=4)
    ax.text(0.5, 0.635, "& Derivatives", color="white",
            fontsize=54, fontweight="bold", ha="center", va="center",
            family="serif", zorder=4)
    ax.text(0.5, 0.575, "A fifteen-chapter study guide",
            color="#fde68a", fontsize=17, ha="center", va="center",
            style="italic", family="serif", zorder=4)

    # Parts list — inside a dark card
    ax.add_patch(mpatches.FancyBboxPatch(
        (0.08, 0.16), 0.84, 0.32, boxstyle="round,pad=0.015,rounding_size=0.02",
        facecolor="#000000", alpha=0.45, edgecolor="#f472b6", lw=1.2, zorder=3))

    parts = [
        ("I",   "Discrete-Time Models",                 "CH 1–2",   "#60a5fa"),
        ("II",  "Continuous-Time Models",               "CH 3–5",   "#a78bfa"),
        ("III", "Equity Derivatives",                   "CH 6–10",  "#f472b6"),
        ("IV",  "Interest-Rate Models",                 "CH 11–13", "#fb923c"),
        ("V",   "Stochastic Vol & Rate Derivatives",    "CH 14–15", "#fbbf24"),
    ]
    y0 = 0.445
    dy = 0.053
    for i, (num, name, rng_str, col) in enumerate(parts):
        y = y0 - i * dy
        ax.add_patch(mpatches.Rectangle((0.13, y - 0.018), 0.007, 0.036,
                                         facecolor=col, zorder=4))
        ax.text(0.16, y, f"PART {num}", fontsize=12, color=col,
                fontweight="bold", va="center", family="sans-serif",
                zorder=4)
        ax.text(0.30, y, name, fontsize=15, color="white",
                va="center", family="serif", zorder=4)
        ax.text(0.88, y, rng_str, fontsize=11, color="#fde68a",
                va="center", ha="right", family="sans-serif",
                style="italic", zorder=4)

    # Footer
    ax.text(0.5, 0.075, "~215,000 WORDS   ·   ~100 FIGURES   ·   FOUNDATIONS-FIRST",
            fontsize=11, color="#fbbf24", ha="center", va="center",
            family="sans-serif", fontweight="bold", zorder=4)
    ax.text(0.5, 0.038, "A self-study companion for the graduate derivatives canon",
            fontsize=10, color="white", ha="center", va="center",
            family="sans-serif", style="italic", alpha=0.85, zorder=4)

    save("cover.png")


# ────────────────────────────────────────────────────────────
# Strategy-guides cover page
# ────────────────────────────────────────────────────────────
def strategy_cover():
    print("STRATEGY COVER:")
    import matplotlib.patches as mpatches
    from matplotlib.colors import LinearSegmentedColormap

    fig = plt.figure(figsize=(8.5, 11), facecolor="#052e16")
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off"); ax.grid(False)

    nx, ny = 600, 800
    X, Y = np.meshgrid(np.linspace(0, 1, nx), np.linspace(0, 1, ny))
    diag = (X + (1 - Y)) / 2
    radial = np.sqrt((X - 0.2) ** 2 + (Y - 0.8) ** 2)
    field = 0.7 * diag + 0.3 * (1 - radial)
    field = (field - field.min()) / (field.max() - field.min())
    grad_cmap = LinearSegmentedColormap.from_list(
        "strat", ["#064e3b", "#065f46", "#047857", "#059669", "#34d399"]
    )
    ax.imshow(field, aspect="auto", extent=(0, 1, 0, 1),
              cmap=grad_cmap, zorder=1, origin="lower")

    # Light watermark tickers
    tickers = ["SPY", "QQQ", "IWM", "VIX", "TLT", "GLD",
               "0DTE", "IC", "CREDIT", "Δ", "Γ", "ν", "Θ", "ρ"]
    rng = np.random.default_rng(11)
    for _ in range(36):
        t = tickers[rng.integers(len(tickers))]
        x, y = rng.uniform(0.02, 0.98), rng.uniform(0.02, 0.98)
        ax.text(x, y, t, fontsize=rng.uniform(10, 22), color="white",
                alpha=rng.uniform(0.06, 0.15),
                ha="center", va="center", rotation=rng.uniform(-8, 8),
                zorder=2, family="sans-serif", fontweight="bold")

    # Gold accent bar
    ax.add_patch(mpatches.Rectangle((0.20, 0.842), 0.60, 0.004,
                                     facecolor="#fbbf24", zorder=3))

    # Title card
    ax.add_patch(mpatches.FancyBboxPatch(
        (0.08, 0.55), 0.84, 0.27,
        boxstyle="round,pad=0.015,rounding_size=0.02",
        facecolor="#000000", alpha=0.35,
        edgecolor="#fbbf24", lw=1.5, zorder=3))

    ax.text(0.5, 0.77, "STRATEGY PLAYBOOK", color="#fbbf24",
            fontsize=13, fontweight="bold", ha="center", va="center",
            family="sans-serif", zorder=4)
    ax.text(0.5, 0.70, "Options & Trading", color="white",
            fontsize=50, fontweight="bold", ha="center", va="center",
            family="serif", zorder=4)
    ax.text(0.5, 0.638, "Strategies", color="white",
            fontsize=50, fontweight="bold", ha="center", va="center",
            family="serif", zorder=4)
    ax.text(0.5, 0.58, "A practitioner's field manual",
            color="#d1fae5", fontsize=16, ha="center", va="center",
            style="italic", family="serif", zorder=4)

    # Subject blocks
    ax.add_patch(mpatches.FancyBboxPatch(
        (0.08, 0.18), 0.84, 0.30,
        boxstyle="round,pad=0.015,rounding_size=0.02",
        facecolor="#000000", alpha=0.40, edgecolor="#34d399", lw=1.2, zorder=3))

    subjects = [
        ("A", "Defined-Risk Credit Spreads",   "IC · IC-AI · Condors · Butterflies",    "#34d399"),
        ("B", "Directional & Event-Driven",    "Bull/Bear · Earnings · FOMC · VIX",     "#fbbf24"),
        ("C", "Volatility & Calendar",          "IV-Rank · Cliquet · Term · Variance",  "#fb923c"),
        ("D", "Regime / Macro / Dealer-GEX",   "GEX · Gamma Regime · Rates · Crypto",   "#f472b6"),
        ("E", "ML & Systematic",                "Ensemble · Transformer · RL · Online", "#60a5fa"),
    ]
    y0 = 0.455
    dy = 0.053
    for i, (tag, name, cats, col) in enumerate(subjects):
        y = y0 - i * dy
        ax.add_patch(mpatches.Rectangle((0.13, y - 0.019), 0.008, 0.038,
                                         facecolor=col, zorder=4))
        ax.text(0.16, y + 0.008, f"Section {tag}",
                fontsize=11, color=col, fontweight="bold",
                va="center", family="sans-serif", zorder=4)
        ax.text(0.16, y - 0.012, cats, fontsize=9, color="#d1fae5",
                va="center", family="sans-serif",
                style="italic", zorder=4)
        ax.text(0.88, y, name, fontsize=13, color="white",
                va="center", ha="right", family="serif", zorder=4)

    # Footer
    ax.text(0.5, 0.075, "89 STRATEGIES   ·   ENTRY / EXIT / RISK   ·   BACKTESTS",
            fontsize=11, color="#fbbf24", ha="center", va="center",
            family="sans-serif", fontweight="bold", zorder=4)
    ax.text(0.5, 0.038, "Companion to the quant course — theory first, execution second",
            fontsize=10, color="white", ha="center", va="center",
            family="sans-serif", style="italic", alpha=0.85, zorder=4)

    save("strategy_cover.png")


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
    ax.set_title("Two-asset state prices (Chapter 3 example)")
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
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.plot(skew_grid, normal_var_line, lw=2, ls="--", color="#2a62a6",
            label=r"Normal quantile $z_{99\%}\approx 2.33$")
    ax.plot(skew_grid, cf_var, lw=2.4, color="#a62a2a",
            label=fr"Cornish-Fisher ($\kappa_{{ex}}={kurt_ex}$)")
    ax.axvline(0, ls=":", color="black", alpha=0.5)
    ax.set_xlabel("skewness $s$")
    ax.set_ylabel(r"quantile multiplier $q_{99\%}$")
    # Shorten title so it fits inside the figure width at 6.25" print size.
    ax.set_title("Cornish-Fisher VaR: skew & kurt adjust the Normal multiplier", fontsize=11)
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
    # Show RN values as text annotations. Place them just above the height
    # of the larger bar (q_rn) so the labels don't collide with the x-axis
    # tick text below, and use a bold weight + small white halo so they read
    # clearly over either bar colour.
    import matplotlib.patheffects as pe
    for xi, rni, q in zip(x, rn, q_rn):
        ax.text(xi, q + 0.012, f"RN={rni:.2f}", fontsize=9,
                color="#6a3a8a", ha="center", weight="semibold",
                path_effects=[pe.withStroke(linewidth=2.2, foreground="white")])
    ax.set_ylim(0, max(q_rn.max(), p_phys.max()) * 1.18)
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
    # Wider canvas + larger node "pills" so the two-line labels fit cleanly
    # without the r and P text colliding inside a small circle.
    fig, ax = plt.subplots(figsize=(9.5, 5.6))
    x_of = lambda k: k * 1.4
    y_of = lambda k, j: (k - 2 * j) * 0.95
    # Edges
    for k in range(3):
        for j in range(k + 1):
            x0, y0 = x_of(k), y_of(k, j)
            x1, y1 = x_of(k + 1), y_of(k + 1, j)
            x2, y2 = x_of(k + 1), y_of(k + 1, j + 1)
            ax.plot([x0, x1], [y0, y1], color="#2a62a6", lw=1.1, alpha=0.55)
            ax.plot([x0, x2], [y0, y2], color="#a62a2a", lw=1.1, alpha=0.55)
    # Nodes with r and P. Use a wider rounded rectangle so the labels fit;
    # stack the two lines with enough vertical separation that they no longer
    # overlap.
    from matplotlib.patches import FancyBboxPatch
    pill_w, pill_h = 0.62, 0.42
    for (k, j), r_val in rates_bl.items():
        xn, yn = x_of(k), y_of(k, j)
        P_val = 1.0 / (1.0 + r_val * dt_bl)
        ax.add_patch(FancyBboxPatch(
            (xn - pill_w / 2, yn - pill_h / 2), pill_w, pill_h,
            boxstyle="round,pad=0.02,rounding_size=0.10",
            facecolor="#fef3c7", edgecolor="#8a6508", lw=1.2, zorder=3,
        ))
        ax.text(xn, yn + 0.10, f"$r$={r_val*100:.2f}%", ha="center", va="center",
                fontsize=9, zorder=4)
        ax.text(xn, yn - 0.10, f"$P$={P_val:.4f}", ha="center", va="center",
                fontsize=9.5, color="#444", zorder=4)
    ax.set_xlim(-0.6, x_of(3) + 0.6); ax.set_ylim(-3.5, 3.5)
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


# ────────────────────────────────────────────────────────────
# CH07 — Greek Visual Atlas (§7.7)
# A second pass at Greek visualisation: theta / rho / vanna / volga /
# charm / speed / colour / dollar-gamma / strike ladder / pin risk /
# vega-vs-skew / gamma-scalping decomposition. All figures share the
# baseline BS world  S0=100, K=100, r=4%, q=0%, sigma=25%.
# ────────────────────────────────────────────────────────────
def ch07_atlas():
    print("CH07 ATLAS:")
    from scipy.stats import norm

    S0, K0 = 100.0, 100.0
    r, q = 0.04, 0.0
    sig = 0.25

    def d1d2(S, K, T, r=r, q=q, sig=sig):
        T = np.maximum(T, 1e-12)
        d1 = (np.log(S / K) + (r - q + 0.5 * sig**2) * T) / (sig * np.sqrt(T))
        d2 = d1 - sig * np.sqrt(T)
        return d1, d2

    def bs_call(S, K, T, r=r, q=q, sig=sig):
        d1, d2 = d1d2(S, K, T, r, q, sig)
        return S * np.exp(-q * T) * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)

    def bs_put(S, K, T, r=r, q=q, sig=sig):
        d1, d2 = d1d2(S, K, T, r, q, sig)
        return K * np.exp(-r * T) * norm.cdf(-d2) - S * np.exp(-q * T) * norm.cdf(-d1)

    def call_delta(S, K, T, r=r, q=q, sig=sig):
        d1, _ = d1d2(S, K, T, r, q, sig)
        return np.exp(-q * T) * norm.cdf(d1)

    def put_delta(S, K, T, r=r, q=q, sig=sig):
        d1, _ = d1d2(S, K, T, r, q, sig)
        return np.exp(-q * T) * (norm.cdf(d1) - 1.0)

    def gamma(S, K, T, r=r, q=q, sig=sig):
        T = np.maximum(T, 1e-12)
        d1, _ = d1d2(S, K, T, r, q, sig)
        return np.exp(-q * T) * norm.pdf(d1) / (S * sig * np.sqrt(T))

    def vega(S, K, T, r=r, q=q, sig=sig):
        T = np.maximum(T, 1e-12)
        d1, _ = d1d2(S, K, T, r, q, sig)
        return S * np.exp(-q * T) * np.sqrt(T) * norm.pdf(d1)  # per 1.00 vol move

    def call_theta(S, K, T, r=r, q=q, sig=sig):
        T = np.maximum(T, 1e-12)
        d1, d2 = d1d2(S, K, T, r, q, sig)
        term1 = -S * np.exp(-q * T) * norm.pdf(d1) * sig / (2.0 * np.sqrt(T))
        term2 = -r * K * np.exp(-r * T) * norm.cdf(d2)
        term3 = +q * S * np.exp(-q * T) * norm.cdf(d1)
        return term1 + term2 + term3

    def put_theta(S, K, T, r=r, q=q, sig=sig):
        T = np.maximum(T, 1e-12)
        d1, d2 = d1d2(S, K, T, r, q, sig)
        term1 = -S * np.exp(-q * T) * norm.pdf(d1) * sig / (2.0 * np.sqrt(T))
        term2 = +r * K * np.exp(-r * T) * norm.cdf(-d2)
        term3 = -q * S * np.exp(-q * T) * norm.cdf(-d1)
        return term1 + term2 + term3

    def call_rho(S, K, T, r=r, q=q, sig=sig):
        _, d2 = d1d2(S, K, T, r, q, sig)
        return K * T * np.exp(-r * T) * norm.cdf(d2)

    def put_rho(S, K, T, r=r, q=q, sig=sig):
        _, d2 = d1d2(S, K, T, r, q, sig)
        return -K * T * np.exp(-r * T) * norm.cdf(-d2)

    def vanna(S, K, T, r=r, q=q, sig=sig):
        # ∂Vega/∂S = -e^{-qT} φ(d1) d2 / σ
        T = np.maximum(T, 1e-12)
        d1, d2 = d1d2(S, K, T, r, q, sig)
        return -np.exp(-q * T) * norm.pdf(d1) * d2 / sig

    def volga(S, K, T, r=r, q=q, sig=sig):
        # Vega · d1·d2 / σ
        return vega(S, K, T, r, q, sig) * (d1d2(S, K, T, r, q, sig)[0]
                                            * d1d2(S, K, T, r, q, sig)[1]) / sig

    def call_charm(S, K, T, r=r, q=q, sig=sig):
        # ∂Δ/∂t  (note: d/dt = -d/dτ).  Garman closed form:
        # charm_call = -e^{-qT}[ φ(d1)(2(r-q)T - d2 σ√T)/(2 T σ√T) + q N(d1) ]·(-1)
        # We want d Delta / d t  (calendar time).  τ = T - t, so dτ/dt = -1.
        T = np.maximum(T, 1e-12)
        d1, d2 = d1d2(S, K, T, r, q, sig)
        sT = sig * np.sqrt(T)
        body = (2.0 * (r - q) * T - d2 * sT) / (2.0 * T * sT)
        # ∂Δ/∂τ = e^{-qT}[ -φ(d1) · body  -  q N(d1) ]
        ddtau = np.exp(-q * T) * (-norm.pdf(d1) * body - q * norm.cdf(d1))
        return -ddtau  # dΔ/dt = -dΔ/dτ

    def put_charm(S, K, T, r=r, q=q, sig=sig):
        T = np.maximum(T, 1e-12)
        d1, d2 = d1d2(S, K, T, r, q, sig)
        sT = sig * np.sqrt(T)
        body = (2.0 * (r - q) * T - d2 * sT) / (2.0 * T * sT)
        ddtau = np.exp(-q * T) * (-norm.pdf(d1) * body + q * norm.cdf(-d1))
        return -ddtau

    def speed(S, K, T, r=r, q=q, sig=sig):
        # ∂Γ/∂S = -Γ/S · (d1/(σ√T) + 1)
        T = np.maximum(T, 1e-12)
        d1, _ = d1d2(S, K, T, r, q, sig)
        g = gamma(S, K, T, r, q, sig)
        return -g / S * (d1 / (sig * np.sqrt(T)) + 1.0)

    def color(S, K, T, r=r, q=q, sig=sig):
        # ∂Γ/∂t.  Closed form (Espen Haug):
        # color = -e^{-qT} φ(d1) / (2 S T σ√T) · [2qT + 1 + (2(r-q)T - d2 σ√T)·d1/(σ√T)]
        # then we want dΓ/dt = -dΓ/dτ
        T = np.maximum(T, 1e-12)
        d1, d2 = d1d2(S, K, T, r, q, sig)
        sT = sig * np.sqrt(T)
        bracket = 2.0 * q * T + 1.0 + (2.0 * (r - q) * T - d2 * sT) * d1 / sT
        dgdtau = -np.exp(-q * T) * norm.pdf(d1) / (2.0 * S * T * sT) * bracket
        return -dgdtau

    # ────────────────────────────────
    # (a) Theta vs Spot — call & put — three TTMs
    # ────────────────────────────────
    S_grid = np.linspace(60, 140, 240)
    ttms = [(1/12, "1m", "#a62a2a"), (3/12, "3m", "#e07a2a"), (1.0, "12m", "#2a62a6")]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True)
    for T_v, lab, col in ttms:
        axes[0].plot(S_grid, call_theta(S_grid, K0, T_v), lw=2, color=col, label=f"T={lab}")
        axes[1].plot(S_grid, put_theta(S_grid, K0, T_v),  lw=2, color=col, label=f"T={lab}")
    for ax, ttl in zip(axes, ["Call $\\Theta$", "Put $\\Theta$"]):
        ax.axvline(K0, ls=":", color="black", alpha=0.5)
        ax.axhline(0, color="black", lw=0.5)
        ax.set_xlabel("Spot $S$"); ax.set_title(ttl)
        ax.legend(fontsize=9, loc="lower right")
    axes[0].set_ylabel(r"$\Theta$  (per year)")
    fig.suptitle(r"Theta vs spot — most negative ATM, asymmetric for puts at low $S$")
    plt.tight_layout()
    save("ch07-theta-vs-spot.png")

    # ────────────────────────────────
    # (b) Rho — call & put — vs spot at fixed T, plus T-scaling sub-panel
    # ────────────────────────────────
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    for T_v, lab, col in ttms:
        axes[0].plot(S_grid, call_rho(S_grid, K0, T_v), lw=2, color=col, label=f"call, T={lab}")
        axes[0].plot(S_grid, put_rho(S_grid,  K0, T_v), lw=2, color=col, ls="--",
                      label=f"put,  T={lab}")
    axes[0].axvline(K0, ls=":", color="black", alpha=0.5)
    axes[0].axhline(0, color="black", lw=0.5)
    axes[0].set_xlabel("Spot $S$"); axes[0].set_ylabel(r"$\rho$  (per 1.00 rate move)")
    axes[0].set_title("Rho vs spot — call positive, put negative")
    axes[0].legend(fontsize=9, ncol=2)

    T_grid = np.linspace(0.02, 3.0, 120)
    axes[1].plot(T_grid, call_rho(K0, K0, T_grid), lw=2.4, color="#1f7a1f", label="ATM call")
    axes[1].plot(T_grid, put_rho(K0, K0, T_grid),  lw=2.4, color="#a62a2a", label="ATM put")
    axes[1].axhline(0, color="black", lw=0.5)
    axes[1].set_xlabel("Time to expiry $T$ (y)")
    axes[1].set_ylabel(r"$\rho_{\text{ATM}}$")
    axes[1].set_title("Rho scales roughly linearly with $T$")
    axes[1].legend(fontsize=9)
    plt.tight_layout()
    save("ch07-rho-call-put.png")

    # ────────────────────────────────
    # (c) Vanna — heatmap over (S, σ) at fixed T, K
    # ────────────────────────────────
    S_grid_v = np.linspace(60, 140, 160)
    sig_grid = np.linspace(0.05, 0.80, 140)
    SS, VV = np.meshgrid(S_grid_v, sig_grid)
    T_v = 0.5
    d1g = (np.log(SS / K0) + (r - q + 0.5 * VV**2) * T_v) / (VV * np.sqrt(T_v))
    d2g = d1g - VV * np.sqrt(T_v)
    vanna_grid = -np.exp(-q * T_v) * norm.pdf(d1g) * d2g / VV
    fig, ax = plt.subplots(figsize=(8.5, 4.5))
    vmax = float(np.nanmax(np.abs(vanna_grid)))
    im = ax.pcolormesh(SS, VV * 100, vanna_grid, cmap="RdBu_r",
                        vmin=-vmax, vmax=vmax, shading="auto")
    ax.contour(SS, VV * 100, vanna_grid, levels=[0.0],
                colors="black", linewidths=1.2, linestyles="--")
    ax.axvline(K0, ls=":", color="white", alpha=0.7)
    cbar = plt.colorbar(im, ax=ax)
    cbar.set_label(r"Vanna $\partial^2 V/\partial S\,\partial\sigma$")
    ax.set_xlabel("Spot $S$"); ax.set_ylabel(r"Volatility $\sigma$ (%)")
    ax.set_title(fr"Vanna heatmap (K={K0:.0f}, T={T_v:.2f}y) — sign change crosses ATM")
    ax.grid(False)
    save("ch07-vanna.png")

    # ────────────────────────────────
    # (d) Volga (vomma) vs spot — bimodal
    # ────────────────────────────────
    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    for T_v, lab, col in [(1/12, "1m", "#a62a2a"), (1.0, "12m", "#2a62a6")]:
        d1, d2 = d1d2(S_grid, K0, T_v)
        v = vega(S_grid, K0, T_v) * d1 * d2 / sig
        ax.plot(S_grid, v, lw=2.4, color=col, label=f"T={lab}")
    ax.axhline(0, color="black", lw=0.5)
    ax.axvline(K0, ls=":", color="black", alpha=0.5)
    ax.set_xlabel("Spot $S$")
    ax.set_ylabel(r"Volga $\partial^2 V/\partial \sigma^2$")
    ax.set_title("Volga (vomma) — twin peaks straddle the ATM zero")
    ax.legend(fontsize=9)
    save("ch07-volga.png")

    # ────────────────────────────────
    # (e) Charm — call & put at TTMs 1w, 1m, 3m
    # ────────────────────────────────
    charm_ttms = [(1/52, "1w", "#a62a2a"), (1/12, "1m", "#e07a2a"),
                   (3/12, "3m", "#2a62a6")]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True)
    for T_v, lab, col in charm_ttms:
        axes[0].plot(S_grid, call_charm(S_grid, K0, T_v), lw=2, color=col, label=f"T={lab}")
        axes[1].plot(S_grid, put_charm(S_grid, K0, T_v),  lw=2, color=col, label=f"T={lab}")
    for ax, ttl in zip(axes, ["Call charm $\\partial\\Delta^C/\\partial t$",
                               "Put charm  $\\partial\\Delta^P/\\partial t$"]):
        ax.axvline(K0, ls=":", color="black", alpha=0.5)
        ax.axhline(0, color="black", lw=0.5)
        ax.set_xlabel("Spot $S$"); ax.set_title(ttl)
        ax.legend(fontsize=9, loc="upper right")
    axes[0].set_ylabel("charm  (Δ-units per year)")
    fig.suptitle("Charm — most extreme ATM, blows up as expiry nears")
    plt.tight_layout()
    save("ch07-charm.png")

    # ────────────────────────────────
    # (f) Speed — vs spot at one TTM
    # ────────────────────────────────
    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    for T_v, lab, col in [(1/12, "1m", "#a62a2a"), (3/12, "3m", "#e07a2a"),
                           (1.0, "12m", "#2a62a6")]:
        ax.plot(S_grid, speed(S_grid, K0, T_v), lw=2, color=col, label=f"T={lab}")
    ax.axhline(0, color="black", lw=0.5)
    ax.axvline(K0, ls=":", color="black", alpha=0.5)
    ax.set_xlabel("Spot $S$"); ax.set_ylabel(r"Speed $\partial\Gamma/\partial S$")
    ax.set_title("Speed — sign flips just above ATM, where the gamma hump rolls over")
    ax.legend(fontsize=9)
    save("ch07-speed.png")

    # ────────────────────────────────
    # (g) Color — ∂Γ/∂t — vs spot, three TTMs
    # ────────────────────────────────
    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    for T_v, lab, col in [(1/52, "1w", "#a62a2a"), (1/12, "1m", "#e07a2a"),
                           (3/12, "3m", "#2a62a6")]:
        ax.plot(S_grid, color(S_grid, K0, T_v), lw=2, color=col, label=f"T={lab}")
    ax.axhline(0, color="black", lw=0.5)
    ax.axvline(K0, ls=":", color="black", alpha=0.5)
    ax.set_xlabel("Spot $S$"); ax.set_ylabel(r"Color $\partial\Gamma/\partial t$")
    ax.set_title("Color — ATM gamma decays (negative); OTM wings can grow gamma")
    ax.legend(fontsize=9)
    save("ch07-color.png")

    # ────────────────────────────────
    # (h) BS price surface — call C(S, T)
    # ────────────────────────────────
    S_surf = np.linspace(60, 140, 80)
    T_surf = np.linspace(0.02, 2.0, 70)
    SSs, TTs = np.meshgrid(S_surf, T_surf)
    Csurf = bs_call(SSs, K0, TTs)
    fig = plt.figure(figsize=(8.5, 5.2))
    ax = fig.add_subplot(111, projection="3d")
    ax.plot_surface(SSs, TTs, Csurf, cmap="viridis", alpha=0.9, edgecolor="none")
    ax.set_xlabel("Spot $S$"); ax.set_ylabel("TTM $T$ (y)")
    ax.set_zlabel("Call price $C$")
    ax.set_title("Black-Scholes call price surface — convexity grows with $T$")
    ax.view_init(elev=22, azim=-58)
    save("ch07-bs-price-surface.png")

    # ────────────────────────────────
    # (i) Dollar-gamma  $Γ = S²·Γ  vs spot, three TTMs
    # ────────────────────────────────
    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    for T_v, lab, col in ttms:
        dg = S_grid**2 * gamma(S_grid, K0, T_v)
        ax.plot(S_grid, dg, lw=2.4, color=col, label=f"T={lab}")
    ax.axvline(K0, ls=":", color="black", alpha=0.5)
    ax.set_xlabel("Spot $S$")
    ax.set_ylabel(r"Dollar-gamma  $\$\Gamma = S^2\,\Gamma$")
    ax.set_title(r"Dollar-gamma — the broker's variance-exposure measure")
    ax.legend(fontsize=9)
    save("ch07-dollar-gamma-vs-spot.png")

    # ────────────────────────────────
    # (j) Strike ladder — table of all Greeks for calls & puts
    # ────────────────────────────────
    strikes = np.array([85, 90, 95, 100, 105, 110, 115], dtype=float)
    T_lad = 0.25
    rows = []
    for K_v in strikes:
        cD = call_delta(S0, K_v, T_lad); pD = put_delta(S0, K_v, T_lad)
        gG = gamma(S0, K_v, T_lad)
        cT = call_theta(S0, K_v, T_lad) / 365.0   # per day
        pT = put_theta(S0, K_v, T_lad) / 365.0
        Vg = vega(S0, K_v, T_lad) / 100.0          # per 1 vol-pt move
        cR = call_rho(S0, K_v, T_lad) / 100.0      # per 1 bp -> per 1% rate
        pR = put_rho(S0, K_v, T_lad) / 100.0
        rows.append([
            f"{K_v:.0f}",
            f"{cD:+.3f}", f"{pD:+.3f}",
            f"{gG:.4f}",
            f"{cT:+.3f}", f"{pT:+.3f}",
            f"{Vg:+.3f}",
            f"{cR:+.3f}", f"{pR:+.3f}",
        ])
    col_labels = ["K", r"$\Delta$ call", r"$\Delta$ put", r"$\Gamma$",
                   r"$\Theta$ call /d", r"$\Theta$ put /d",
                   r"Vega/vol-pt",
                   r"$\rho$ call /pp", r"$\rho$ put /pp"]
    # Slightly wider figure plus explicit colWidths so the "Vega/vol-pt" header
    # (the widest text in the row) is not clipped.
    fig, ax = plt.subplots(figsize=(11.5, 4.5))
    ax.axis("off")
    col_widths = [0.07, 0.10, 0.10, 0.10, 0.12, 0.12, 0.14, 0.12, 0.12]
    tbl = ax.table(cellText=rows, colLabels=col_labels, loc="center",
                    cellLoc="center", colLoc="center", colWidths=col_widths)
    tbl.auto_set_font_size(False); tbl.set_fontsize(10); tbl.scale(1.0, 1.55)
    # Bold header
    for j in range(len(col_labels)):
        tbl[(0, j)].set_facecolor("#1f3a68")
        tbl[(0, j)].set_text_props(color="white", weight="bold")
    # Highlight ATM row
    atm_row = int(np.argmin(np.abs(strikes - S0))) + 1
    for j in range(len(col_labels)):
        tbl[(atm_row, j)].set_facecolor("#fef3c7")
    ax.set_title(f"Strike ladder — Greeks at S={S0:.0f}, T={T_lad:.2f}y, "
                  fr"$\sigma$={sig*100:.0f}%, r={r*100:.0f}%",
                  pad=14)
    save("ch07-greek-table-strike-ladder.png")

    # ────────────────────────────────
    # (k) Pin risk — digital call delta as t → T, S = K
    # ────────────────────────────────
    # Digital call price: e^{-rT} N(d2).  Δ = e^{-rT} φ(d2) / (S σ√T).
    # At S=K with q=0:  d2 = (r - 0.5σ²)√T / σ.
    T_grid_pin = np.linspace(1/365, 0.5, 600)
    d2_pin = (r - q - 0.5 * sig**2) * np.sqrt(T_grid_pin) / sig
    digital_delta = np.exp(-r * T_grid_pin) * norm.pdf(d2_pin) / (S0 * sig * np.sqrt(T_grid_pin))
    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    days_left = T_grid_pin * 365
    ax.plot(days_left, digital_delta, lw=2.4, color="#a62a2a")
    ax.set_xlabel("Days to expiry $\\tau$ (calendar)")
    ax.set_ylabel(r"Digital call $\Delta$  (at $S=K$)")
    ax.set_title(r"Digital call delta blows up like $1/\sqrt{\tau}$ at the strike — pin risk")
    ax.invert_xaxis()
    ax.set_yscale("log")
    save("ch07-pin-risk-digital-delta.png")

    # ────────────────────────────────
    # (l) Vega vs strike across an implied-vol smile
    # ────────────────────────────────
    K_grid = np.linspace(70, 130, 200)
    T_v = 0.25
    log_m = np.log(K_grid / S0)
    # Asymmetric SVI-ish smile:  σ(K) = σ_atm + a·log_m  + b·log_m²  with negative skew
    sig_atm = 0.22
    a, b = -0.35, 1.10
    iv_smile = sig_atm + a * log_m + b * log_m**2
    iv_smile = np.maximum(iv_smile, 0.05)
    iv_flat  = np.full_like(K_grid, sig_atm)

    def vega_K(K, sig_local):
        d1 = (np.log(S0 / K) + (r - q + 0.5 * sig_local**2) * T_v) / (sig_local * np.sqrt(T_v))
        return S0 * np.exp(-q * T_v) * np.sqrt(T_v) * norm.pdf(d1)

    vega_smile = vega_K(K_grid, iv_smile)
    vega_flat  = vega_K(K_grid, iv_flat)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    axes[0].plot(K_grid, iv_smile * 100, lw=2.4, color="#a62a2a", label="IV smile (skewed)")
    axes[0].plot(K_grid, iv_flat * 100,  lw=2.0, color="#2a62a6", ls="--",
                  label=f"flat IV = {sig_atm*100:.0f}%")
    axes[0].axvline(S0, ls=":", color="black", alpha=0.5)
    axes[0].set_xlabel("Strike $K$"); axes[0].set_ylabel("IV (%)")
    axes[0].set_title("Implied-vol smile"); axes[0].legend(fontsize=9)

    axes[1].plot(K_grid, vega_smile, lw=2.4, color="#a62a2a", label="Vega(K) under smile")
    axes[1].plot(K_grid, vega_flat,  lw=2.0, color="#2a62a6", ls="--",
                  label="Vega(K) under flat IV")
    axes[1].axvline(S0, ls=":", color="black", alpha=0.5)
    axes[1].set_xlabel("Strike $K$"); axes[1].set_ylabel("Vega (per 1.00 vol move)")
    axes[1].set_title("Vega across the smile — wing kink moves the bucket")
    axes[1].legend(fontsize=9)
    plt.tight_layout()
    save("ch07-skew-vs-vega.png")

    # ────────────────────────────────
    # (m) Gamma-scalping P&L decomposition over a Monte Carlo path
    # ────────────────────────────────
    rng = np.random.default_rng(2026)
    T_path = 0.25
    n_steps = 250
    dt = T_path / n_steps
    sig_real = 0.30   # realised vol > implied
    sig_imp  = 0.22   # what we priced/hedged at
    mu_drift = r - 0.5 * sig_real**2
    z = rng.standard_normal(n_steps)
    log_S = np.zeros(n_steps + 1)
    log_S[0] = np.log(S0)
    for i in range(n_steps):
        log_S[i + 1] = log_S[i] + mu_drift * dt + sig_real * np.sqrt(dt) * z[i]
    S_path = np.exp(log_S)
    t_grid = np.linspace(0.0, T_path, n_steps + 1)
    tau    = T_path - t_grid                         # τ left

    # Long call hedged with -Δ stock; we track theta-bleed & gamma-rebalance
    theta_bleed = np.zeros(n_steps)
    gamma_pnl   = np.zeros(n_steps)
    for i in range(n_steps):
        S_i = S_path[i]; tau_i = max(tau[i], 1e-9)
        d1_i = (np.log(S_i / K0) + (r - q + 0.5 * sig_imp**2) * tau_i) / (sig_imp * np.sqrt(tau_i))
        gamma_i = np.exp(-q * tau_i) * norm.pdf(d1_i) / (S_i * sig_imp * np.sqrt(tau_i))
        # theta priced from implied vol:
        theta_i = (-S_i * np.exp(-q * tau_i) * norm.pdf(d1_i) * sig_imp / (2.0 * np.sqrt(tau_i))
                    - r * K0 * np.exp(-r * tau_i) * norm.cdf(d1_i - sig_imp * np.sqrt(tau_i))
                    + q * S_i * np.exp(-q * tau_i) * norm.cdf(d1_i))
        dS = S_path[i + 1] - S_i
        gamma_pnl[i]   = 0.5 * gamma_i * dS**2
        theta_bleed[i] = theta_i * dt          # negative

    cum_gamma = np.cumsum(gamma_pnl)
    cum_theta = np.cumsum(theta_bleed)
    cum_total = cum_gamma + cum_theta

    fig, axes = plt.subplots(2, 1, figsize=(8.5, 6.2),
                              gridspec_kw=dict(height_ratios=[1, 1.4]))
    axes[0].plot(t_grid, S_path, lw=1.6, color="#2a62a6")
    axes[0].axhline(K0, ls=":", color="black", alpha=0.5, label=f"K={K0:.0f}")
    axes[0].set_ylabel("$S_t$"); axes[0].set_title(
        fr"GBM path — $\sigma_{{\rm real}}$={sig_real*100:.0f}% vs "
        fr"$\sigma_{{\rm imp}}$={sig_imp*100:.0f}%")
    axes[0].legend(fontsize=9)

    axes[1].plot(t_grid[1:], cum_gamma, lw=2.0, color="#1f7a1f",
                  label="cum. gamma rebalance gains")
    axes[1].plot(t_grid[1:], cum_theta, lw=2.0, color="#a62a2a",
                  label="cum. theta bleed")
    axes[1].plot(t_grid[1:], cum_total, lw=2.4, color="black",
                  label="cum. delta-hedged P&L")
    axes[1].axhline(0, color="black", lw=0.5)
    axes[1].set_xlabel("$t$ (y)"); axes[1].set_ylabel("Cumulative P&L")
    axes[1].set_title(r"Gamma-scalping decomposition: $\frac{1}{2} S^2\Gamma\,(\sigma_r^2-\sigma_i^2)\,dt$ in expectation")
    axes[1].legend(fontsize=9)
    plt.tight_layout()
    save("ch07-gamma-scalping-pnl.png")


# ────────────────────────────────────────────────────────────
# CH01 — supplemental tree / number-line diagrams
# ────────────────────────────────────────────────────────────
def _draw_two_state_tree(ax, x0, root_label, up_label, dn_label,
                         color="#2a62a6", up_color="#1f7a1f", dn_color="#a62a2a",
                         span=1.0, half_height=1.0,
                         root_offset=(-0.18, 0.0), up_offset=(0.06, 0.05),
                         dn_offset=(0.06, -0.05),
                         q_label=None, q_color="#1f7a1f", title=None,
                         label_fontsize=13, root_fontsize=13):
    """Draw a single one-period two-state tree on `ax` rooted at (x0, 0)."""
    x_leaf = x0 + span
    # branches
    ax.plot([x0, x_leaf], [0, +half_height], "-", color=color, lw=2.0, zorder=2)
    ax.plot([x0, x_leaf], [0, -half_height], "-", color=color, lw=2.0, zorder=2)
    # nodes
    ax.plot([x0], [0], "o", color="black", ms=7, zorder=3)
    ax.plot([x_leaf], [+half_height], "o", color=up_color, ms=7, zorder=3)
    ax.plot([x_leaf], [-half_height], "o", color=dn_color, ms=7, zorder=3)
    # labels
    ax.annotate(root_label, (x0, 0),
                xytext=(x0 + root_offset[0], root_offset[1]),
                fontsize=root_fontsize, ha="right", va="center")
    ax.annotate(up_label, (x_leaf, +half_height),
                xytext=(x_leaf + up_offset[0], +half_height + up_offset[1]),
                fontsize=label_fontsize, color=up_color, ha="left", va="center")
    ax.annotate(dn_label, (x_leaf, -half_height),
                xytext=(x_leaf + dn_offset[0], -half_height + dn_offset[1]),
                fontsize=label_fontsize, color=dn_color, ha="left", va="center")
    if q_label is not None:
        ax.text(x0 + 0.45 * span, 0.55 * half_height, q_label,
                fontsize=12, color=q_color, ha="center")
    if title is not None:
        ax.text(x0 + 0.5 * span, -1.55 * half_height, title,
                fontsize=11, ha="center", style="italic", color="#444")


def ch01_two_asset_tree():
    """Two parallel one-period trees for risky A and numeraire B."""
    fig, axes = plt.subplots(1, 2, figsize=(8.5, 3.8))
    for ax in axes:
        ax.set_xlim(-0.5, 1.9); ax.set_ylim(-1.7, 1.7)
        ax.set_xticks([]); ax.set_yticks([])
        ax.grid(False)
        for s in ("top", "right", "bottom", "left"):
            ax.spines[s].set_visible(False)

    _draw_two_state_tree(
        axes[0], x0=0.0,
        root_label=r"$A_0$", up_label=r"$A_u$", dn_label=r"$A_d$",
        q_label=r"same coin $x_1$",
        title=r"risky $A$",
    )
    _draw_two_state_tree(
        axes[1], x0=0.0,
        root_label=r"$B_0$", up_label=r"$B_u$", dn_label=r"$B_d$",
        color="#6b4ea6", up_color="#1f7a1f", dn_color="#a62a2a",
        q_label=r"same coin $x_1$", q_color="#444",
        title=r"numeraire $B$ (bond: $B_u=B_d=B_0(1+r)$)",
    )

    fig.suptitle(r"Two-asset one-period tree — driven by the same Bernoulli coin $x_1$",
                 fontsize=12)
    plt.tight_layout()
    save("ch01-two-asset-tree.png")


def ch01_no_arb_sandwich():
    """Number line showing A_d < A_0(1+r) < A_u (no-arb sandwich)."""
    fig, ax = plt.subplots(figsize=(7.5, 2.6))
    ax.set_xlim(0, 10); ax.set_ylim(-1.0, 1.4)
    ax.set_xticks([]); ax.set_yticks([])
    ax.grid(False)
    for s in ("top", "right", "bottom", "left"):
        ax.spines[s].set_visible(False)

    # axis line with arrow
    ax.annotate("", xy=(9.6, 0), xytext=(0.4, 0),
                arrowprops=dict(arrowstyle="->", color="black", lw=1.5))
    ax.text(9.7, 0.05, r"future value", fontsize=10, ha="left", va="bottom")

    # three points
    xs = [2.0, 5.0, 8.0]
    labels = [r"$A_d$", r"$A_0(1+r)$", r"$A_u$"]
    colors = ["#a62a2a", "#2a62a6", "#1f7a1f"]
    for x, lab, c in zip(xs, labels, colors):
        ax.plot([x], [0], "o", color=c, ms=10, zorder=3)
        ax.text(x, -0.30, lab, fontsize=13, ha="center", va="top", color=c)

    # shaded no-arb interval
    ax.axvspan(2.0, 8.0, ymin=0.42, ymax=0.58, color="#2a62a6", alpha=0.10)

    # inequality annotation above
    ax.text(5.0, 0.95,
            r"$A_d \;<\; A_0(1+r) \;<\; A_u$",
            fontsize=14, ha="center", va="center",
            bbox=dict(boxstyle="round,pad=0.35", facecolor="#fef9e7",
                      edgecolor="#caa84d", lw=1.0))
    # bracket arrows
    ax.annotate("", xy=(2.05, 0.55), xytext=(4.95, 0.55),
                arrowprops=dict(arrowstyle="<->", color="#444", lw=1.0))
    ax.annotate("", xy=(5.05, 0.55), xytext=(7.95, 0.55),
                arrowprops=dict(arrowstyle="<->", color="#444", lw=1.0))

    ax.set_title(r"No-arbitrage sandwich: forward $A_0(1+r)$ lies strictly inside $[A_d,\,A_u]$",
                 fontsize=11)
    plt.tight_layout()
    save("ch01-no-arb-sandwich.png")


def ch01_three_asset_tree():
    """Three side-by-side one-period trees for A (underlying), B (numeraire), C (claim)."""
    fig, axes = plt.subplots(1, 3, figsize=(9.0, 3.8))
    for ax in axes:
        ax.set_xlim(-0.5, 1.9); ax.set_ylim(-1.7, 1.7)
        ax.set_xticks([]); ax.set_yticks([])
        ax.grid(False)
        for s in ("top", "right", "bottom", "left"):
            ax.spines[s].set_visible(False)

    _draw_two_state_tree(
        axes[0], x0=0.0,
        root_label=r"$A_0$", up_label=r"$A_u$", dn_label=r"$A_d$",
        title=r"underlying $A$",
    )
    _draw_two_state_tree(
        axes[1], x0=0.0,
        root_label=r"$B_0$", up_label=r"$B_u$", dn_label=r"$B_d$",
        color="#6b4ea6",
        title=r"numeraire $B$",
    )
    _draw_two_state_tree(
        axes[2], x0=0.0,
        root_label=r"$C_0$", up_label=r"$C_u$", dn_label=r"$C_d$",
        color="#caa84d",
        title=r"contingent claim $C$",
    )

    fig.suptitle(r"Three assets driven by the same coin — consistency requires $q^{BA}=q^{BC}$",
                 fontsize=12)
    plt.tight_layout()
    save("ch01-three-asset-tree.png")


def ch01_three_asset_numerical():
    """Three-asset tree with numerical leaves showing inconsistent q^{BA} vs q^{BC}."""
    fig, axes = plt.subplots(1, 3, figsize=(9.5, 4.2))
    for ax in axes:
        ax.set_xlim(-0.5, 2.0); ax.set_ylim(-1.9, 1.7)
        ax.set_xticks([]); ax.set_yticks([])
        ax.grid(False)
        for s in ("top", "right", "bottom", "left"):
            ax.spines[s].set_visible(False)

    _draw_two_state_tree(
        axes[0], x0=0.0,
        root_label=r"$A_0=10$", up_label=r"$A_u=20$", dn_label=r"$A_d=5$",
        title=r"(A) underlying",
    )
    _draw_two_state_tree(
        axes[1], x0=0.0,
        root_label=r"$B_0=1$", up_label=r"$B_u=1$", dn_label=r"$B_d=1$",
        color="#6b4ea6",
        title=r"(B) numeraire",
    )
    _draw_two_state_tree(
        axes[2], x0=0.0,
        root_label=r"$C_0=110$", up_label=r"$C_u=120$", dn_label=r"$C_d=100$",
        color="#caa84d",
        title=r"(C, short position)",
    )

    # implied risk-neutral weights below
    axes[0].text(0.55, -1.55, r"$q^{BA} = \frac{10-5}{20-5} = \frac{1}{3}$",
                 fontsize=12, ha="center",
                 bbox=dict(boxstyle="round,pad=0.30", facecolor="#eef5ee",
                           edgecolor="#1f7a1f", lw=0.8))
    axes[2].text(0.55, -1.55, r"$q^{BC} = \frac{110-100}{120-100} = \frac{1}{2}$",
                 fontsize=12, ha="center",
                 bbox=dict(boxstyle="round,pad=0.30", facecolor="#fdecec",
                           edgecolor="#a62a2a", lw=0.8))

    fig.suptitle(r"Numerical example — $q^{BA}=\frac{1}{3}\neq q^{BC}=\frac{1}{2}$ signals arbitrage",
                 fontsize=12)
    plt.tight_layout()
    save("ch01-three-asset-numerical.png")


def ch01_mispricing_arb():
    """Three-asset tree (A=100→{120,90}, B≡1, C=6→{20,0}) with arbitrage portfolio annotation."""
    fig, axes = plt.subplots(1, 3, figsize=(9.5, 4.6))
    for ax in axes:
        ax.set_xlim(-0.5, 2.0); ax.set_ylim(-2.1, 1.7)
        ax.set_xticks([]); ax.set_yticks([])
        ax.grid(False)
        for s in ("top", "right", "bottom", "left"):
            ax.spines[s].set_visible(False)

    _draw_two_state_tree(
        axes[0], x0=0.0,
        root_label=r"$A_0=100$", up_label=r"$A_u=120$", dn_label=r"$A_d=90$",
        title=r"(A) underlying",
    )
    _draw_two_state_tree(
        axes[1], x0=0.0,
        root_label=r"$B_0=1$", up_label=r"$B_u=1$", dn_label=r"$B_d=1$",
        color="#6b4ea6",
        title=r"(B) numeraire",
    )
    _draw_two_state_tree(
        axes[2], x0=0.0,
        root_label=r"$C_0=6$", up_label=r"$C_u=20$", dn_label=r"$C_d=0$",
        color="#caa84d",
        title=r"(C, mispriced; fair $=6\frac{2}{3}$)",
    )

    # portfolio annotations
    portfolio = (r"Arbitrage portfolio:  "
                 r"short $\frac{2}{3}A$, long $60\,B$, long $1\,C$"
                 + "\n"
                 + r"$V_0 = -\frac{2}{3}\!\cdot\!100 + 60 + 6 = -\frac{2}{3}$  "
                 r"(receive $+\frac{2}{3}$ today)")
    fig.text(0.5, -0.02, portfolio, fontsize=11, ha="center", va="top",
             bbox=dict(boxstyle="round,pad=0.40", facecolor="#fef9e7",
                       edgecolor="#caa84d", lw=1.0))

    # terminal P&L per state
    axes[0].text(0.55, -1.75, r"up: $-\frac{2}{3}(120)+60+20 = 0$",
                 fontsize=10, ha="center", color="#1f7a1f")
    axes[2].text(0.55, -1.75, r"down: $-\frac{2}{3}(90)+60+0 = 0$",
                 fontsize=10, ha="center", color="#a62a2a")

    fig.suptitle(r"Mispriced $C_0=6$ — exploit via short $\frac{2}{3}A$, long $60B$, long $1C$",
                 fontsize=12)
    plt.tight_layout(rect=(0, 0.05, 1, 1))
    save("ch01-mispricing-arb.png")


def ch01_multi_period_tree():
    """Recombining 2-step binomial tree A_0 -> {A_u, A_d} -> {A_uu, A_ud, A_dd}."""
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    ax.set_xlim(-0.4, 2.6); ax.set_ylim(-2.4, 2.4)
    ax.set_xticks([]); ax.set_yticks([])
    ax.grid(False)
    for s in ("top", "right", "bottom", "left"):
        ax.spines[s].set_visible(False)

    # node coordinates
    nodes = {
        "A0":  (0.0,  0.0),
        "Au":  (1.0,  1.0),
        "Ad":  (1.0, -1.0),
        "Auu": (2.0,  2.0),
        "Aud": (2.0,  0.0),
        "Add": (2.0, -2.0),
    }

    # branches (parent → child)
    branches = [
        ("A0", "Au", "#1f7a1f"),
        ("A0", "Ad", "#a62a2a"),
        ("Au", "Auu", "#1f7a1f"),
        ("Au", "Aud", "#a62a2a"),
        ("Ad", "Aud", "#1f7a1f"),
        ("Ad", "Add", "#a62a2a"),
    ]
    for p, c, col in branches:
        x0, y0 = nodes[p]; x1, y1 = nodes[c]
        ax.plot([x0, x1], [y0, y1], "-", color=col, lw=1.8, zorder=2)

    # node markers
    node_color = {
        "A0":  "black",
        "Au":  "#1f7a1f", "Ad":  "#a62a2a",
        "Auu": "#1f7a1f", "Aud": "#444",  "Add": "#a62a2a",
    }
    for name, (x, y) in nodes.items():
        ax.plot([x], [y], "o", color=node_color[name], ms=8, zorder=3)

    # labels
    label_offsets = {
        "A0":  (-0.18,  0.00, "right", "center", r"$A_0$"),
        "Au":  ( 0.00,  0.20, "center", "bottom", r"$A_u$"),
        "Ad":  ( 0.00, -0.22, "center", "top",    r"$A_d$"),
        "Auu": ( 0.10,  0.00, "left",  "center",  r"$A_{uu}$"),
        "Aud": ( 0.10,  0.00, "left",  "center",  r"$A_{ud}=A_{du}$"),
        "Add": ( 0.10,  0.00, "left",  "center",  r"$A_{dd}$"),
    }
    for name, (dx, dy, ha, va, lab) in label_offsets.items():
        x, y = nodes[name]
        ax.text(x + dx, y + dy, lab, fontsize=12, ha=ha, va=va,
                color=node_color[name])

    # time axis labels
    for x, t_lab in [(0.0, r"$t=0$"), (1.0, r"$t=1$"), (2.0, r"$t=2$")]:
        ax.text(x, -2.30, t_lab, fontsize=11, ha="center", style="italic", color="#444")

    ax.set_title(r"Multi-period recombining binomial tree — $A_{ud}=A_{du}$",
                 fontsize=12)
    plt.tight_layout()
    save("ch01-multi-period-tree.png")


# Drive
if __name__ == "__main__":
    for fn in (ch01, ch02, ch03, ch04, ch05, ch06, ch07, ch07_atlas, ch08, ch09, ch10, ch10_mc, ch11, ch11_cal, ch12,
               ch01_two_asset_tree, ch01_no_arb_sandwich, ch01_three_asset_tree,
               ch01_three_asset_numerical, ch01_mispricing_arb, ch01_multi_period_tree):
        try:
            fn()
        except Exception as e:
            print(f"  FAILED: {fn.__name__} — {type(e).__name__}: {e}")
    print("\nAll done -> docs/guide/figures/")
