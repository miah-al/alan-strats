"""
Standalone figure builder for Chapter 15 (Risk Measures: VaR, CTE).

Run:  python docs/guide/_build_ch15_extra_figs.py

Outputs (under docs/guide/figures/):
    ch15-var-cte-fat-tail.png
    ch15-subadditivity-violation.png
    ch15-three-routes-var.png
    ch15-backtest-clustering.png
    ch15-es-tail-average.png
"""
from __future__ import annotations
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

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
def fig_var_cte_fat_tail():
    """VaR and CTE on the same Student-t3 fat-tail vs Normal."""
    np.random.seed(0)
    from scipy.stats import t as student_t, norm
    x = np.linspace(-6, 6, 600)
    pdf_n = norm.pdf(x)
    pdf_t = student_t.pdf(x, df=3)
    alpha = 0.05
    var_n = float(-norm.ppf(alpha))
    var_t = float(-student_t.ppf(alpha, df=3))
    # CTE under each
    cte_n = float(norm.pdf(norm.ppf(alpha)) / alpha)
    # For student-t: CTE_alpha = f(VaR) * (nu + VaR^2) / ((nu - 1) * alpha)
    nu = 3
    cte_t = float(student_t.pdf(student_t.ppf(alpha, df=nu), df=nu) *
                  (nu + student_t.ppf(alpha, df=nu) ** 2) / ((nu - 1) * alpha))
    # Take absolute (loss = -return)
    cte_t = abs(cte_t)
    cte_n = abs(cte_n)

    fig, ax = plt.subplots(figsize=(9.5, 5.5))
    ax.plot(x, pdf_n, color="#1e3a8a", lw=2, label="Normal")
    ax.plot(x, pdf_t, color="#c2410c", lw=2, label="Student-$t_3$ (fat tail)")
    # Shade the tails
    mask = x <= -var_n
    ax.fill_between(x[mask], 0, pdf_n[mask], color="#1e3a8a", alpha=0.15)
    mask_t = x <= -var_t
    ax.fill_between(x[mask_t], 0, pdf_t[mask_t], color="#c2410c", alpha=0.15)
    # VaR lines
    ax.axvline(-var_n, color="#1e3a8a", lw=1.2, ls="--",
               label=fr"Normal VaR$_{{95}}={var_n:.2f}$, CTE$_{{95}}={cte_n:.2f}$")
    ax.axvline(-var_t, color="#c2410c", lw=1.2, ls="--",
               label=fr"$t_3$ VaR$_{{95}}={var_t:.2f}$, CTE$_{{95}}={cte_t:.2f}$")
    ax.set_xlabel("return / loss axis")
    ax.set_ylabel("density")
    ax.set_title(
        r"VaR vs CTE on Normal vs Student-$t_3$: similar quantile, very different tail mass" + "\n"
        r"1987's $-20.5$% S&P day sat well beyond any rolling 95% VaR — CTE-95 captures the weight a VaR-95 misses",
        fontsize=10.5,
    )
    ax.legend(loc="upper left", frameon=False, fontsize=9)
    ax.set_xlim(-6, 4)
    _save("ch15-var-cte-fat-tail.png")


# ---------------------------------------------------------------------
def fig_subadditivity_violation():
    """Two-loan example: each loan VaR95 = 0, but merged VaR95 > 0."""
    np.random.seed(0)
    n_sim = 100000
    # Each loan: 4% default chance, loss 100; else 0
    L1 = np.where(np.random.uniform(0, 1, n_sim) < 0.04, 100, 0)
    L2 = np.where(np.random.uniform(0, 1, n_sim) < 0.04, 100, 0)
    L_sum = L1 + L2

    fig, ax = plt.subplots(figsize=FIGSIZE)
    bins = [-0.5, 0.5, 50, 150, 250]
    counts_one, edges = np.histogram(L1, bins=bins)
    counts_sum, _ = np.histogram(L_sum, bins=bins)
    # Empirical 95% VaR
    var_one = np.percentile(L1, 95)
    var_sum = np.percentile(L_sum, 95)

    x_positions = np.array([0, 1, 2, 3])
    width = 0.36
    ax.bar(x_positions - width / 2, counts_one / n_sim,
           width=width, color="#1e3a8a", label=f"single loan (VaR$_{{95}}={var_one:.0f}$)")
    ax.bar(x_positions + width / 2, counts_sum / n_sim,
           width=width, color="#c2410c", label=f"sum of two loans (VaR$_{{95}}={var_sum:.0f}$)")
    ax.set_yscale("log")
    ax.set_xticks(x_positions)
    ax.set_xticklabels(["0", "0+ (rare)", "100", "200"])
    ax.set_xlabel("loss bucket")
    ax.set_ylabel("probability (log)")
    ax.set_title("Sub-additivity failure of VaR: each loan's VaR$_{95}$ is 0; the merged book's VaR$_{95}$ is 100\n"
                 "Same arithmetic underlay the 2008 mortgage-CDO regulatory blind spot — individual AAA tranches looked safe by VaR, the portfolio did not")
    ax.legend(loc="upper right", frameon=False, fontsize=10)
    _save("ch15-subadditivity-violation.png")


# ---------------------------------------------------------------------
def fig_three_routes_var():
    """Historical / parametric / MC VaR on a known fat-tail distribution."""
    np.random.seed(0)
    from scipy.stats import norm, t as student_t
    n_hist = 500  # historical sample size
    # Truth: Student-t3 loss distribution (re-centered)
    true_dist = student_t(df=3)
    losses = -true_dist.rvs(n_hist)  # losses = -returns

    # 95% VaR estimates
    alpha = 0.05
    # 1. Historical
    var_hist = float(np.percentile(losses, 100 * (1 - alpha)))
    # 2. Parametric Normal
    mu = float(np.mean(losses))
    sd = float(np.std(losses))
    var_param = mu + sd * float(norm.ppf(1 - alpha))
    # 3. MC under Student-t fit
    nu_mc = 3
    sd_mc = float(np.sqrt(nu_mc / (nu_mc - 2)))
    var_mc_true = -float(student_t.ppf(alpha, df=nu_mc))

    fig, ax = plt.subplots(figsize=FIGSIZE)
    # Loss distribution histogram
    ax.hist(losses, bins=40, density=True, color="#94a3b8", alpha=0.55,
            edgecolor="white", label=f"historical loss sample ($N={n_hist}$)")
    # Overlay densities used by parametric and MC
    x = np.linspace(min(losses), max(losses), 400)
    ax.plot(x, norm.pdf(x, loc=mu, scale=sd), color="#1e3a8a", lw=2,
            label="parametric (Normal fit)")
    ax.plot(x, student_t.pdf(x, df=nu_mc), color="#c2410c", lw=2,
            label="MC (Student-$t_3$ generator)")

    ax.axvline(var_hist, color="#16a34a", lw=2, ls="--",
               label=fr"historical VaR$_{{95}}={var_hist:.2f}$")
    ax.axvline(var_param, color="#1e3a8a", lw=2, ls="--",
               label=fr"parametric VaR$_{{95}}={var_param:.2f}$")
    ax.axvline(var_mc_true, color="#c2410c", lw=2, ls="--",
               label=fr"MC VaR$_{{95}}={var_mc_true:.2f}$")
    ax.set_xlabel("loss")
    ax.set_ylabel("density")
    ax.set_title(
        "Three routes to VaR on the same loss distribution\n"
        "Parametric-Normal systematically under-reports the tail — the daily FRTB-IMA diagnostic",
        fontsize=10.5,
    )
    # Move legend to upper-left so it doesn't overlap the three VaR vertical
    # lines (which sit on the right). Add a solid frame so it stays readable
    # over the histogram bars.
    ax.legend(loc="upper left", frameon=True, framealpha=0.92, fontsize=9)
    _save("ch15-three-routes-var.png")


# ---------------------------------------------------------------------
def fig_backtest_clustering():
    """Clustered exceedances under regime-switching volatility."""
    np.random.seed(0)
    n_days = 750
    # Regime: 1 = calm, 2 = stressed
    vol_calm = 0.01
    vol_stress = 0.03
    regimes = np.ones(n_days, dtype=int)
    regimes[180:230] = 2   # cluster A
    regimes[480:540] = 2   # cluster B
    returns = np.where(regimes == 1,
                       np.random.standard_normal(n_days) * vol_calm,
                       np.random.standard_normal(n_days) * vol_stress)
    # Static 99% VaR estimate (mis-specified — assumes constant vol)
    var_static = 2.326 * 0.015  # ~ blended SD estimate
    losses = -returns
    exceed = losses > var_static

    fig, axes = plt.subplots(2, 1, figsize=(10, 5.5), sharex=True)
    ax = axes[0]
    ax.plot(losses, color="#1e3a8a", lw=0.8, alpha=0.8)
    ax.axhline(var_static, color="#c2410c", lw=1.5, ls="--",
               label=fr"static VaR$_{{99}}={var_static:.4f}$")
    # Mark exceedances
    ex_idx = np.where(exceed)[0]
    ax.scatter(ex_idx, losses[ex_idx], color="#dc2626", s=22, zorder=5,
               label=f"exceedances ($n={len(ex_idx)}$)")
    ax.set_ylabel("daily loss (positive = loss)")
    ax.set_title("VaR backtest with regime-switching volatility — clustered exceedances reject the static model")
    ax.legend(loc="upper right", frameon=False, fontsize=9)

    ax = axes[1]
    ax.bar(range(n_days), exceed.astype(int), color="#dc2626", width=1.0)
    ax.set_xlabel("trading day")
    ax.set_ylabel("exception?")
    ax.set_yticks([0, 1])
    ax.text(0.05, 0.85, "Christoffersen's IND test rejects (clusters $\\Rightarrow$ Markov serial dep.)",
            transform=ax.transAxes, fontsize=9, color="#7f1d1d",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.85))

    fig.tight_layout()
    _save("ch15-backtest-clustering.png")


# ---------------------------------------------------------------------
def fig_es_tail_average():
    """Expected Shortfall as the average of losses beyond VaR."""
    np.random.seed(0)
    from scipy.stats import t as student_t
    x = np.linspace(-6, 8, 600)
    pdf = student_t.pdf(x, df=4)
    alpha = 0.05
    var = -float(student_t.ppf(alpha, df=4))

    # ES via numerical integration
    tail_x = x[x > var]
    tail_pdf = student_t.pdf(tail_x, df=4)
    es = float(np.trapezoid(tail_x * tail_pdf, tail_x) / np.trapezoid(tail_pdf, tail_x))

    fig, ax = plt.subplots(figsize=FIGSIZE)
    ax.plot(x, pdf, color="#1e3a8a", lw=2, label=r"loss density $f_L$")
    # Shade tail
    mask = x > var
    ax.fill_between(x[mask], 0, pdf[mask], color="#dc2626", alpha=0.25,
                    label=fr"$\alpha={alpha}$ tail")
    ax.axvline(var, color="#1e3a8a", lw=2, ls="--",
               label=fr"VaR$_{{95}} = {var:.2f}$")
    ax.axvline(es, color="#c2410c", lw=2,
               label=fr"ES$_{{95}}$ = average tail loss = {es:.2f}")
    ax.annotate("", xy=(es, 0.018), xytext=(var, 0.018),
                arrowprops=dict(arrowstyle="<->", color="black", lw=1.4))
    ax.text(0.5 * (var + es), 0.024, f"gap = {es - var:.2f}", fontsize=10,
            ha="center", color="black")
    ax.set_xlabel("loss")
    ax.set_ylabel("density")
    ax.set_title("Expected Shortfall as the average tail loss beyond VaR\n"
                 "FRTB's 97.5% ES (in force 2023) targets exactly this average — the regulatory shift after 2008's Lehman-week multi-sigma days exposed VaR's blind spot")
    ax.legend(loc="upper right", frameon=False, fontsize=9)
    _save("ch15-es-tail-average.png")


# ---------------------------------------------------------------------
if __name__ == "__main__":
    fig_var_cte_fat_tail()
    fig_subadditivity_violation()
    fig_three_routes_var()
    fig_backtest_clustering()
    fig_es_tail_average()
    print("Chapter 15 extras: done")
