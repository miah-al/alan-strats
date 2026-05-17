"""
Standalone figure builder for Chapter 10 Appendix B (VIX vs SPX correlation study).

Downloads ^GSPC and ^VIX from yfinance (period='max'), computes empirical
statistics, and writes three PNGs to docs/guide/figures/.

Run:  python docs/guide/_build_ch10_vix_figs.py

Also prints the empirical statistics that the Chapter 10 Appendix B prose
quotes. Run this script first, then plug values into the markdown.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

try:
    import yfinance as yf
except ImportError:
    print("yfinance not installed. Run: pip install yfinance", file=sys.stderr)
    sys.exit(1)

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


def fetch():
    """Download SPX and VIX from yfinance, return aligned daily DataFrame."""
    print("Downloading ^GSPC and ^VIX (period=max) ...")
    spx = yf.download("^GSPC", period="max", auto_adjust=False, progress=False)
    vix = yf.download("^VIX", period="max", auto_adjust=False, progress=False)

    # yfinance may return MultiIndex columns when ticker list is single — normalize
    def _close(df):
        if isinstance(df.columns, pd.MultiIndex):
            return df["Close"].iloc[:, 0]
        return df["Close"]

    spx_c = _close(spx).rename("SPX")
    vix_c = _close(vix).rename("VIX")
    df = pd.concat([spx_c, vix_c], axis=1).dropna()
    df["dlogSPX"] = np.log(df["SPX"]).diff()
    df["dVIX"] = df["VIX"].diff()
    df["pctSPX"] = df["SPX"].pct_change()
    df = df.dropna()
    print(f"  rows: {len(df):,}  range: {df.index[0].date()} -> {df.index[-1].date()}")
    return df


def compute_stats(df: pd.DataFrame) -> dict:
    """Compute the empirical numbers used in the prose."""
    out = {}
    out["start"] = df.index[0].date().isoformat()
    out["end"] = df.index[-1].date().isoformat()
    out["n_days"] = int(len(df))
    out["corr_dlogspx_dvix"] = float(df["dlogSPX"].corr(df["dVIX"]))
    out["corr_pctspx_dvix"] = float(df["pctSPX"].corr(df["dVIX"]))

    # OLS slope: dVIX = a + b * dlogSPX
    x = df["dlogSPX"].values
    y = df["dVIX"].values
    b, a = np.polyfit(x, y, 1)
    out["ols_slope_dvix_per_dlogspx"] = float(b)
    out["ols_intercept"] = float(a)

    # Asymmetric response: average dVIX on -1% SPX day vs +1% SPX day
    bin_edges = np.array([-np.inf, -0.03, -0.02, -0.01, -0.005,
                          0.005, 0.01, 0.02, 0.03, np.inf])
    labels = ["<-3%", "-3 to -2%", "-2 to -1%", "-1 to -0.5%",
              "-0.5 to +0.5%", "+0.5 to +1%", "+1 to +2%", "+2 to +3%", ">+3%"]
    df = df.copy()
    df["bucket"] = pd.cut(df["pctSPX"], bins=bin_edges, labels=labels)
    bucket_mean = df.groupby("bucket", observed=True)["dVIX"].mean()
    bucket_count = df.groupby("bucket", observed=True)["dVIX"].count()
    out["bucket_mean"] = bucket_mean
    out["bucket_count"] = bucket_count

    # Symmetric comparison: SPX in [-1.5%, -0.5%] vs [+0.5%, +1.5%]
    down_mask = (df["pctSPX"] > -0.015) & (df["pctSPX"] < -0.005)
    up_mask = (df["pctSPX"] > 0.005) & (df["pctSPX"] < 0.015)
    out["mean_dvix_on_down1pct"] = float(df.loc[down_mask, "dVIX"].mean())
    out["mean_dvix_on_up1pct"] = float(df.loc[up_mask, "dVIX"].mean())
    out["n_down1pct"] = int(down_mask.sum())
    out["n_up1pct"] = int(up_mask.sum())

    # Rolling 252-day correlation
    roll = df["dlogSPX"].rolling(252).corr(df["dVIX"])
    out["roll_min"] = float(roll.min())
    out["roll_min_date"] = roll.idxmin().date().isoformat()
    out["roll_max"] = float(roll.max())
    out["roll_max_date"] = roll.idxmax().date().isoformat()
    out["roll_mean"] = float(roll.mean())
    out["roll_median"] = float(roll.median())
    out["roll_series"] = roll

    # Highlight windows
    def _val_at(date_str):
        idx = roll.index.get_indexer([pd.Timestamp(date_str)], method="nearest")[0]
        return float(roll.iloc[idx]), roll.index[idx].date().isoformat()

    out["roll_2008_10"] = _val_at("2008-10-31")
    out["roll_covid"] = _val_at("2020-03-31")
    out["roll_volmageddon"] = _val_at("2018-02-28")

    # Quantile dispersion of dVIX given big SPX drops
    big_drop = df[df["pctSPX"] < -0.03]
    out["n_big_drops"] = int(len(big_drop))
    out["mean_dvix_on_big_drop"] = float(big_drop["dVIX"].mean())
    out["median_dvix_on_big_drop"] = float(big_drop["dVIX"].median())

    return out


def fig_scatter(df: pd.DataFrame, stats: dict):
    """Daily dlogSPX vs dVIX scatter, full history."""
    fig, ax = plt.subplots(figsize=FIGSIZE)
    ax.scatter(df["dlogSPX"] * 100, df["dVIX"], s=4, alpha=0.25,
               color="#1f4eaa", edgecolors="none")

    # OLS line
    x_grid = np.linspace(df["dlogSPX"].min(), df["dlogSPX"].max(), 100)
    y_grid = stats["ols_slope_dvix_per_dlogspx"] * x_grid + stats["ols_intercept"]
    ax.plot(x_grid * 100, y_grid, color="#d62728", lw=2,
            label=fr"OLS: $\Delta$VIX = {stats['ols_slope_dvix_per_dlogspx']:.2f}$\,\Delta\log$SPX")

    ax.axhline(0, color="k", lw=0.5, alpha=0.4)
    ax.axvline(0, color="k", lw=0.5, alpha=0.4)
    ax.set_xlabel(r"$\Delta\log$ SPX  (daily, percent)")
    ax.set_ylabel(r"$\Delta$ VIX  (daily, points)")
    ax.set_title(
        f"SPX log-returns vs VIX daily changes  "
        f"({stats['start']} to {stats['end']}, n={stats['n_days']:,})\n"
        fr"corr($\Delta\log$SPX, $\Delta$VIX) = {stats['corr_dlogspx_dvix']:.3f}"
    )
    ax.legend(loc="upper right", framealpha=0.9)
    ax.set_xlim(-15, 15)
    ax.set_ylim(-20, 25)
    path = os.path.join(FIG, "ch10-vix-spx-scatter.png")
    plt.savefig(path, dpi=DPI, bbox_inches="tight")
    plt.close()
    print(f"  wrote {os.path.basename(path)}")


def fig_rolling(stats: dict):
    """252-day rolling correlation with annotated event markers."""
    roll = stats["roll_series"].dropna()
    fig, ax = plt.subplots(figsize=FIGSIZE)
    ax.plot(roll.index, roll.values, color="#1f4eaa", lw=1.0)
    ax.axhline(-0.7, color="#888", ls="--", lw=0.8,
               label=r"typical Heston $\rho \approx -0.7$")
    ax.axhline(-0.8, color="#888", ls=":", lw=0.8,
               label=r"typical Heston $\rho \approx -0.8$")
    ax.axhline(stats["roll_mean"], color="#d62728", ls="-", lw=1.0,
               alpha=0.6, label=fr"mean = {stats['roll_mean']:.3f}")

    # Event annotations
    events = [
        ("2008-10-15", "2008 GFC", "top"),
        ("2018-02-05", "Volmageddon\nFeb 2018", "bottom"),
        ("2020-03-16", "COVID\nMar 2020", "top"),
    ]
    for date_str, label, side in events:
        ts = pd.Timestamp(date_str)
        if ts < roll.index[0] or ts > roll.index[-1]:
            continue
        idx = roll.index.get_indexer([ts], method="nearest")[0]
        x, y = roll.index[idx], roll.iloc[idx]
        ax.scatter([x], [y], color="#d62728", zorder=5, s=30)
        yoff = 0.12 if side == "top" else -0.18
        ha = "center"
        ax.annotate(label, xy=(x, y), xytext=(x, y + yoff),
                    fontsize=9, ha=ha,
                    arrowprops=dict(arrowstyle="-", color="#d62728", lw=0.6))

    ax.set_xlabel("Date")
    ax.set_ylabel(r"252-day rolling corr($\Delta\log$SPX, $\Delta$VIX)")
    ax.set_title(
        f"Rolling 252-day SPX-VIX correlation  ({stats['start']} to {stats['end']})\n"
        f"range: [{stats['roll_min']:.3f} on {stats['roll_min_date']}, "
        f"{stats['roll_max']:.3f} on {stats['roll_max_date']}]"
    )
    ax.set_ylim(-1.0, 0.1)
    ax.legend(loc="lower left", framealpha=0.9, fontsize=9)
    path = os.path.join(FIG, "ch10-vix-spx-rolling-corr.png")
    plt.savefig(path, dpi=DPI, bbox_inches="tight")
    plt.close()
    print(f"  wrote {os.path.basename(path)}")


def fig_asymmetry(stats: dict):
    """Bucketed mean dVIX by SPX-return decile (signed buckets)."""
    bucket_mean = stats["bucket_mean"]
    bucket_count = stats["bucket_count"]

    fig, ax = plt.subplots(figsize=FIGSIZE)
    x = np.arange(len(bucket_mean))
    colors = ["#8b0000" if v > 0 else "#1a5f1a" for v in bucket_mean.values]
    bars = ax.bar(x, bucket_mean.values, color=colors, edgecolor="k", lw=0.5)

    # Annotate counts above/below each bar
    for xi, v, n in zip(x, bucket_mean.values, bucket_count.values):
        yt = v + (0.15 if v >= 0 else -0.3)
        va = "bottom" if v >= 0 else "top"
        ax.text(xi, yt, f"n={n}", ha="center", va=va, fontsize=9, color="#444")

    ax.axhline(0, color="k", lw=0.7)
    ax.set_xticks(x)
    ax.set_xticklabels([str(lab) for lab in bucket_mean.index],
                       rotation=30, ha="right", fontsize=9)
    ax.set_xlabel("SPX daily return bucket")
    ax.set_ylabel(r"mean $\Delta$ VIX  (points)")
    ax.set_title(
        f"Asymmetric VIX response to SPX moves  ({stats['start']} to {stats['end']})\n"
        fr"mean $\Delta$VIX on $-$1% SPX day = "
        f"{stats['mean_dvix_on_down1pct']:+.2f}   vs   "
        fr"on $+$1% SPX day = "
        f"{stats['mean_dvix_on_up1pct']:+.2f}"
    )
    path = os.path.join(FIG, "ch10-vix-spx-asymmetry.png")
    plt.savefig(path, dpi=DPI, bbox_inches="tight")
    plt.close()
    print(f"  wrote {os.path.basename(path)}")


def print_report(stats: dict):
    print("\n" + "=" * 72)
    print("EMPIRICAL STATISTICS  (use these numbers in the prose)")
    print("=" * 72)
    print(f"Sample:                  {stats['start']} to {stats['end']}  "
          f"(n = {stats['n_days']:,} trading days)")
    print()
    print(f"corr(dlogSPX, dVIX):     {stats['corr_dlogspx_dvix']:+.4f}")
    print(f"corr(pctSPX,  dVIX):     {stats['corr_pctspx_dvix']:+.4f}")
    print(f"OLS slope (dVIX ~ dlogSPX): {stats['ols_slope_dvix_per_dlogspx']:+.3f}")
    print(f"OLS intercept:           {stats['ols_intercept']:+.4f}")
    print()
    print("Asymmetric response:")
    print(f"  mean dVIX | SPX in [-1.5%, -0.5%]: {stats['mean_dvix_on_down1pct']:+.3f}  "
          f"(n={stats['n_down1pct']})")
    print(f"  mean dVIX | SPX in [+0.5%, +1.5%]: {stats['mean_dvix_on_up1pct']:+.3f}  "
          f"(n={stats['n_up1pct']})")
    print(f"  ratio (down magnitude / up magnitude): "
          f"{abs(stats['mean_dvix_on_down1pct']) / max(abs(stats['mean_dvix_on_up1pct']), 1e-9):.2f}x")
    print()
    print(f"Big drops (SPX < -3%):   n={stats['n_big_drops']}, "
          f"mean dVIX = {stats['mean_dvix_on_big_drop']:+.2f}, "
          f"median = {stats['median_dvix_on_big_drop']:+.2f}")
    print()
    print("Rolling 252-day correlation:")
    print(f"  mean / median:         {stats['roll_mean']:+.4f} / {stats['roll_median']:+.4f}")
    print(f"  min:                   {stats['roll_min']:+.4f}  on {stats['roll_min_date']}")
    print(f"  max:                   {stats['roll_max']:+.4f}  on {stats['roll_max_date']}")
    print(f"  near 2008-10:          {stats['roll_2008_10'][0]:+.4f}  ({stats['roll_2008_10'][1]})")
    print(f"  near Volmageddon 2018: {stats['roll_volmageddon'][0]:+.4f}  ({stats['roll_volmageddon'][1]})")
    print(f"  near COVID 2020-03:    {stats['roll_covid'][0]:+.4f}  ({stats['roll_covid'][1]})")
    print()
    print("Bucketed mean dVIX:")
    for lab, m, n in zip(stats["bucket_mean"].index,
                         stats["bucket_mean"].values,
                         stats["bucket_count"].values):
        print(f"  {str(lab):>18s}:  mean dVIX = {m:+.3f}  (n={n})")
    print("=" * 72)


def main():
    df = fetch()
    stats = compute_stats(df)
    fig_scatter(df, stats)
    fig_rolling(stats)
    fig_asymmetry(stats)
    print_report(stats)


if __name__ == "__main__":
    main()
