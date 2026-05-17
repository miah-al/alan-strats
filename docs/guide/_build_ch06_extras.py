"""
Standalone figure builder for Chapter 6 (Dynamic Hedging) extras.

Run:  python docs/guide/_build_ch06_extras.py

Outputs (under docs/guide/figures/):
    ch06-delta-surface.png   (replaces an old broken render)

The right-hand digital-delta surface diverges like 1/(S sigma sqrt(tau))
near the strike as tau -> 0. We clip the z-axis to expose the tent
shape; without clipping the rest of the surface collapses to a flat dark
sheet because the colormap is dominated by a single spike.
"""
from __future__ import annotations
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import cm
from scipy.stats import norm

FIG = os.path.join(os.path.dirname(__file__), "figures")
os.makedirs(FIG, exist_ok=True)
DPI = 200

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


def _d1_d2(S, K, tau, r, sigma):
    """Black-Scholes d1, d2. tau and sigma must be positive."""
    sqrt_tau = np.sqrt(tau)
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * tau) / (sigma * sqrt_tau)
    d2 = d1 - sigma * sqrt_tau
    return d1, d2


def fig_delta_surface():
    """Vanilla call delta vs digital call delta over (S, tau)."""
    K = 100.0
    r = 0.03
    sigma = 0.25

    # Spot range and time-to-expiry range. Floor tau at a small positive
    # number so we never divide by zero; this is the same convention used
    # to render the surface in textbooks.
    S = np.linspace(60, 140, 80)
    tau = np.linspace(0.02, 1.0, 80)
    SS, TT = np.meshgrid(S, tau, indexing="xy")

    d1, d2 = _d1_d2(SS, K, TT, r, sigma)
    vanilla_delta = norm.cdf(d1)
    # Digital call delta: d/dS [ e^{-r tau} N(d2) ] = e^{-r tau} phi(d2) / (S sigma sqrt(tau))
    digital_delta_raw = np.exp(-r * TT) * norm.pdf(d2) / (SS * sigma * np.sqrt(TT))

    # Clip digital delta z-axis to expose the tent shape. The unclipped
    # surface spikes to several hundred at the strike for tau ~ 0.02,
    # which collapses the colormap and the rest of the surface to ~0.
    Z_CLIP = 0.45
    digital_delta = np.minimum(digital_delta_raw, Z_CLIP)

    fig = plt.figure(figsize=(12, 5.2))

    # ---- Left: vanilla delta surface --------------------------------
    ax1 = fig.add_subplot(1, 2, 1, projection="3d")
    ax1.plot_surface(
        SS, TT, vanilla_delta,
        cmap=cm.viridis,
        rcount=60, ccount=60,
        linewidth=0, antialiased=True,
        vmin=0.0, vmax=1.0,
        alpha=0.95,
    )
    ax1.set_xlabel(r"$S$", labelpad=8)
    ax1.set_ylabel(r"$\tau = T - t$", labelpad=8)
    ax1.set_zlabel(r"$\Delta$", labelpad=4)
    ax1.set_title(r"Vanilla-call $\Delta(S, \tau)$", pad=10)
    ax1.set_zlim(0.0, 1.0)
    ax1.view_init(elev=22, azim=-58)
    ax1.grid(True, alpha=0.25)

    # ---- Right: digital delta surface (clipped) ---------------------
    ax2 = fig.add_subplot(1, 2, 2, projection="3d")
    ax2.plot_surface(
        SS, TT, digital_delta,
        cmap=cm.magma,
        rcount=60, ccount=60,
        linewidth=0, antialiased=True,
        vmin=0.0, vmax=Z_CLIP,
        alpha=0.95,
    )
    ax2.set_xlabel(r"$S$", labelpad=8)
    ax2.set_ylabel(r"$\tau = T - t$", labelpad=8)
    ax2.set_zlabel(r"$\Delta_{\mathrm{dig}}$ (clipped)", labelpad=4)
    ax2.set_title(
        r"Digital-call $\Delta(S, \tau)$  (clipped at " + f"{Z_CLIP:.2f}" + r" — tents at $K$ as $\tau\to 0$)",
        pad=10,
    )
    ax2.set_zlim(0.0, Z_CLIP)
    ax2.view_init(elev=22, azim=-58)
    ax2.grid(True, alpha=0.25)

    fig.tight_layout()
    _save("ch06-delta-surface.png")


if __name__ == "__main__":
    fig_delta_surface()
    print("Chapter 6 extras: done")
