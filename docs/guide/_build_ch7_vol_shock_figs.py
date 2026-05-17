"""
Standalone figure + statistics generator for Chapter 7, Appendix A
("Empirical Proof of the sqrt(30/tau) Vol-Shock Scaling").

Run:  python docs/guide/_build_ch7_vol_shock_figs.py

Outputs (under docs/guide/figures/):
    ch7-vol-shock-scaling-fit.png
    ch7-vol-shock-powerlaw.png
    ch7-vol-shock-regime.png

Also prints the fitted regression slopes beta(tau), the power-law exponent
alpha, the R^2 values, and the rolling-beta summary statistics so the
numbers in the prose of the appendix can be plugged in by hand.

This script is independent of docs/guide/build_figures.py.
"""
from __future__ import annotations
import os
import sys
import warnings

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

try:
    import yfinance as yf
except ImportError:
    sys.stderr.write(
        "ERROR: yfinance not installed. Run `pip install yfinance` first.\n"
    )
    raise

FIG = os.path.join(os.path.dirname(__file__), "figures")
os.makedirs(FIG, exist_ok=True)

DPI = 200
plt.rcParams.update({
    "figure.facecolor": "white",
    "axes.grid": True,
    "grid.alpha": 0.3,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "font.size": 10,
})

# ---- tenor map ----------------------------------------------------------
TICKERS = {
    9:   "^VIX9D",
    30:  "^VIX",
    90:  "^VIX3M",
    180: "^VIX6M",
}


def fetch_vix_term() -> pd.DataFrame:
    """Download Close series for the four CBOE VIX-term tickers."""
    frames = {}
    for tau, sym in TICKERS.items():
        print(f"  downloading {sym} (tau={tau}d) ...", flush=True)
        df = yf.download(
            sym, period="max", interval="1d",
            auto_adjust=False, progress=False, threads=False,
        )
        if df is None or df.empty:
            raise RuntimeError(f"no data returned for {sym}")
        # yfinance may return either a MultiIndex or flat column
        if isinstance(df.columns, pd.MultiIndex):
            s = df["Close"].iloc[:, 0]
        else:
            s = df["Close"]
        s = s.dropna()
        s.name = tau
        frames[tau] = s
    out = pd.concat(frames.values(), axis=1, keys=frames.keys())
    out.columns = list(frames.keys())
    out = out.dropna(how="any").sort_index()
    return out


def fit_beta(d30: np.ndarray, dtau: np.ndarray) -> tuple[float, float, float]:
    """OLS through origin: dtau = beta * d30. Return (beta, beta_se, R^2)."""
    x = d30.astype(float)
    y = dtau.astype(float)
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    n = len(x)
    sxx = float(np.sum(x * x))
    sxy = float(np.sum(x * y))
    beta = sxy / sxx
    resid = y - beta * x
    sigma2 = float(np.sum(resid ** 2)) / max(n - 1, 1)
    beta_se = float(np.sqrt(sigma2 / sxx))
    # R^2 computed against zero-mean baseline (regression-through-origin convention)
    ss_tot = float(np.sum(y * y))
    r2 = 1.0 - float(np.sum(resid ** 2)) / ss_tot
    return beta, beta_se, r2


def fit_powerlaw(taus: list[int], betas: list[float]) -> tuple[float, float, float]:
    """Fit beta(tau) = (30/tau)^alpha by OLS on log-log. Return (alpha, alpha_se, R^2)."""
    x = np.log(30.0 / np.asarray(taus, dtype=float))   # log(30/tau)
    y = np.log(np.asarray(betas, dtype=float))         # log(beta)
    n = len(x)
    # Slope through origin (model: y = alpha * x, since at tau=30 we expect beta=1)
    sxx = float(np.sum(x * x))
    sxy = float(np.sum(x * y))
    alpha = sxy / sxx
    resid = y - alpha * x
    sigma2 = float(np.sum(resid ** 2)) / max(n - 1, 1)
    alpha_se = float(np.sqrt(sigma2 / sxx))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2)) if n > 1 else 1.0
    r2 = 1.0 - float(np.sum(resid ** 2)) / ss_tot if ss_tot > 0 else float("nan")
    return alpha, alpha_se, r2


def rolling_beta(d30: pd.Series, d90: pd.Series, window: int) -> pd.Series:
    """Rolling regression slope: d90_t = beta_t * d30_t, computed window-by-window."""
    num = (d30 * d90).rolling(window).sum()
    den = (d30 * d30).rolling(window).sum()
    return num / den


# ─────────────────────────────────────────────────────────────────────────
# Figure 1 — 4-panel scatter with regression
# ─────────────────────────────────────────────────────────────────────────
def fig_scatter(diffs: pd.DataFrame, results: dict):
    fig, axes = plt.subplots(2, 2, figsize=(10, 7))
    taus = [9, 30, 90, 180]
    d30 = diffs[30].values
    for ax, tau in zip(axes.flat, taus):
        dtau = diffs[tau].values
        beta = results[tau]["beta"]
        se = results[tau]["se"]
        r2 = results[tau]["r2"]
        ax.scatter(d30, dtau, s=4, alpha=0.25, color="#4338ca", rasterized=True)
        xs = np.linspace(np.nanmin(d30), np.nanmax(d30), 100)
        ax.plot(xs, beta * xs, color="#c2410c", lw=1.8,
                label=fr"$\beta={beta:.3f}\;(\pm{se:.3f})$")
        ax.plot(xs, xs, color="0.4", lw=0.8, ls="--", label=r"$\beta=1$ ref")
        ax.set_title(fr"$\tau={tau}$d   ($R^2={r2:.3f}$)", fontsize=10)
        ax.set_xlabel(r"$\Delta \mathrm{VIX}_{30}$ (vol pts)")
        ax.set_ylabel(fr"$\Delta \mathrm{{VIX}}_{{{tau}}}$ (vol pts)")
        ax.legend(loc="upper left", fontsize=9, frameon=False)
        ax.axhline(0, color="0.7", lw=0.5)
        ax.axvline(0, color="0.7", lw=0.5)
    fig.suptitle(
        "Daily co-moves of the VIX term structure  (regression of "
        r"$\Delta\mathrm{VIX}_\tau$ on $\Delta\mathrm{VIX}_{30}$, through origin)",
        fontsize=11,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    out = os.path.join(FIG, "ch7-vol-shock-scaling-fit.png")
    plt.savefig(out, dpi=DPI, bbox_inches="tight")
    plt.close()
    print(f"  wrote {os.path.basename(out)}")


# ─────────────────────────────────────────────────────────────────────────
# Figure 2 — power-law beta(tau) vs tau/30
# ─────────────────────────────────────────────────────────────────────────
def fig_powerlaw(results: dict, alpha: float, alpha_se: float, r2: float):
    taus = np.array([9, 30, 90, 180], dtype=float)
    betas = np.array([results[int(t)]["beta"] for t in taus])
    ses = np.array([results[int(t)]["se"] for t in taus])

    fig, ax = plt.subplots(figsize=(8, 5))
    # x-axis: tau/30 (so 30d sits at 1.0)
    x = taus / 30.0
    ax.errorbar(x, betas, yerr=ses, fmt="o", color="#1e3a8a", ms=7,
                capsize=3, label="empirical β(τ)")

    grid = np.linspace(0.25, 7.0, 200)
    # Empirical fit: beta = (30/tau)^alpha = x^(-alpha)
    fit = grid ** (-alpha)
    ax.plot(grid, fit, color="#c2410c", lw=2.0,
            label=fr"empirical fit $(\,30/\tau\,)^{{{alpha:.3f}}}$")
    # Reference 1/sqrt curve
    ref = grid ** (-0.5)
    ax.plot(grid, ref, color="0.4", lw=1.5, ls="--",
            label=r"reference $(30/\tau)^{1/2}$ (heuristic)")

    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel(r"$\tau / 30$  (tenor in units of one month)")
    ax.set_ylabel(r"$\beta(\tau)$  —  vol-shock transmission")
    ax.set_title(
        fr"Power-law fit of vol-shock transmission: $\alpha={alpha:.3f}\,(\pm{alpha_se:.3f})$,  "
        fr"$R^2={r2:.3f}$"
    )
    ax.legend(loc="upper right", frameon=False, fontsize=9)
    # Annotate each point
    for xi, bi, ti in zip(x, betas, taus.astype(int)):
        ax.annotate(fr"$\tau={ti}$d", (xi, bi),
                    xytext=(6, 6), textcoords="offset points", fontsize=9)
    ax.grid(True, which="both", alpha=0.3)
    fig.tight_layout()
    out = os.path.join(FIG, "ch7-vol-shock-powerlaw.png")
    plt.savefig(out, dpi=DPI, bbox_inches="tight")
    plt.close()
    print(f"  wrote {os.path.basename(out)}")


# ─────────────────────────────────────────────────────────────────────────
# Figure 3 — rolling 60-day beta for 90d-vs-30d
# ─────────────────────────────────────────────────────────────────────────
def fig_regime(diffs: pd.DataFrame, full_beta_90: float):
    d30 = diffs[30]
    d90 = diffs[90]
    roll = rolling_beta(d30, d90, window=60).dropna()
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(roll.index, roll.values, color="#1e3a8a", lw=1.0)
    ax.axhline(full_beta_90, color="#c2410c", lw=1.2, ls="--",
               label=fr"full-sample $\beta(90)={full_beta_90:.3f}$")
    ax.axhline((30.0/90.0) ** 0.5, color="0.4", lw=1.0, ls=":",
               label=r"heuristic $\sqrt{30/90}\approx 0.577$")

    crises = [
        ("2008-09-15", "Lehman / GFC"),
        ("2018-02-05", "Volmageddon"),
        ("2020-03-16", "COVID crash"),
    ]
    for date_str, lab in crises:
        d = pd.Timestamp(date_str)
        if d >= roll.index.min() and d <= roll.index.max():
            ax.axvline(d, color="#dc2626", lw=0.8, alpha=0.7)
            ax.annotate(lab, xy=(d, ax.get_ylim()[1]),
                        xytext=(4, -10), textcoords="offset points",
                        fontsize=9, color="#7f1d1d", rotation=0)

    ax.set_xlabel("date")
    ax.set_ylabel(r"rolling-60d $\beta(90)$ — slope of $\Delta\mathrm{VIX}_{90}$ on $\Delta\mathrm{VIX}_{30}$")
    ax.set_title("Regime dependence: 60-day rolling vol-shock transmission, 3-month tenor")
    ax.legend(loc="lower right", frameon=False, fontsize=9)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    out = os.path.join(FIG, "ch7-vol-shock-regime.png")
    plt.savefig(out, dpi=DPI, bbox_inches="tight")
    plt.close()
    print(f"  wrote {os.path.basename(out)}")
    return roll


# ─────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────
def main():
    print("Fetching VIX-term data from yfinance ...")
    levels = fetch_vix_term()
    print(f"  joined sample: {len(levels)} days, "
          f"{levels.index.min().date()} -> {levels.index.max().date()}")

    diffs = levels.diff().dropna()

    # Per-tenor regressions of dtau on d30
    results: dict[int, dict] = {}
    for tau in [9, 30, 90, 180]:
        beta, se, r2 = fit_beta(diffs[30].values, diffs[tau].values)
        results[tau] = {"beta": beta, "se": se, "r2": r2}
        print(f"  τ={tau:>3}d:  β = {beta:.4f} (±{se:.4f}),  R² = {r2:.4f},  n = {len(diffs)}")

    # Power-law fit
    taus_fit = [9, 90, 180]   # use off-30 tenors (anchor at tau=30 gives beta=1 exactly)
    betas_fit = [results[t]["beta"] for t in taus_fit]
    alpha, alpha_se, r2_pl = fit_powerlaw(taus_fit, betas_fit)
    print(f"\n  Power-law fit β(τ) = (30/τ)^α :")
    print(f"    α = {alpha:.4f}  (±{alpha_se:.4f}),  R² = {r2_pl:.4f}")
    print(f"    heuristic prediction: α = 0.5")
    print(f"    implied β(180) = (30/180)^α = {(30/180)**alpha:.4f}  vs empirical {results[180]['beta']:.4f}")

    # Build figures
    fig_scatter(diffs, results)
    fig_powerlaw(results, alpha, alpha_se, r2_pl)
    roll = fig_regime(diffs, results[90]["beta"])

    # Regime stats
    print("\n  Rolling-60d β(90) summary:")
    print(f"    min  = {roll.min():.3f}  on {roll.idxmin().date()}")
    print(f"    max  = {roll.max():.3f}  on {roll.idxmax().date()}")
    print(f"    mean = {roll.mean():.3f}")
    print(f"    median = {roll.median():.3f}")
    print(f"    p10  = {roll.quantile(0.10):.3f}")
    print(f"    p90  = {roll.quantile(0.90):.3f}")
    print(f"    heuristic √(30/90) ≈ 0.577")

    # Crisis-window beta
    print("\n  β(90) in crisis windows:")
    for date_str, lab in [("2008-09-01", "Lehman ±60d"),
                          ("2018-02-05", "Volmageddon ±60d"),
                          ("2020-03-16", "COVID ±60d")]:
        d = pd.Timestamp(date_str)
        lo = d - pd.Timedelta(days=60)
        hi = d + pd.Timedelta(days=60)
        sub = diffs.loc[(diffs.index >= lo) & (diffs.index <= hi)]
        if len(sub) > 10:
            b, _, _ = fit_beta(sub[30].values, sub[90].values)
            print(f"    {lab:<20}  β = {b:.3f}   (n={len(sub)})")
        else:
            print(f"    {lab:<20}  insufficient data ({len(sub)} pts)")


if __name__ == "__main__":
    main()
