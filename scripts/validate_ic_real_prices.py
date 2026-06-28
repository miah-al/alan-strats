"""
Real-price iron-condor VALIDATION tool for SPY (diagnostic — not app runtime).

This is a one-off validator, not part of the backtest framework. The in-strategy
backtests price every leg off a FLAT VIX-as-IV Black-Scholes model (no skew, no
real fills), which overstates the edge of short-vol structures. This script
reconstructs the ACTUAL historical option chain from Polygon and prices every leg
off REAL historical contract bars — capturing real volatility skew (short puts
richer) and real premium decay, the things that actually decide whether a condor
makes money. It is what showed the SPY condor has no real edge (~-9.7%, -0.65
Sharpe), which is why the condor strategies are marked "avoid".

It only does iron condors (4 legs hard-coded). Equity strategies (trend /
momentum) need no equivalent — they already backtest on real daily closes inside
their own .backtest(). Only option-leg strategies have the synthetic-pricing gap
this validates.

Usage (from repo root):
    python -m scripts.validate_ic_real_prices                 # default condor gates on SPY
    python -m scripts.validate_ic_real_prices --days 380      # ~1.5y window
    python -m scripts.validate_ic_real_prices --ticker QQQ

Needs POLYGON_API_KEY (in .env) — it fetches real option chains/bars. SPY+VIX
daily come from yfinance (free, no key).

Data path (Polygon Options Starter — no upgrade needed):
  • /v3/reference/options/contracts?as_of=DATE  → strikes/expiries that existed
  • /v2/aggs/ticker/O:...                        → real daily closes per contract

HARD LIMITATION: Options Starter retains ~2 years of history, so real prices are
only available from ~today-2y forward. The 2022 high-vol stress regime CANNOT be
tested on real prices with this plan — only the synthetic model reaches it.

No look-ahead: indicators at bar i use data ≤ i; contracts are pulled as_of the
entry date; leg prices on day d use bars ≤ d only.
"""
from __future__ import annotations

import argparse
import math
import logging
import os
import sys
from pathlib import Path
from typing import Callable, Optional

# Force UTF-8 stdout so arrow / em-dash glyphs in the report don't trip cp1252.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# Repo root is the `alan_trader/` dir; put it (and its parent) on sys.path so
# both `strategies.foo` and `alan_trader.strategies.foo` resolve — matching how
# app/app.py and the other scripts bootstrap themselves.
_ROOT   = Path(__file__).resolve().parent.parent
_PARENT = _ROOT.parent
for _p in (_ROOT, _PARENT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

try:
    from dotenv import load_dotenv
    load_dotenv(_ROOT / ".env")
except ImportError:
    pass

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_R         = 0.045                       # risk-free proxy
_SLIP      = 0.05                         # per-share adverse fill per leg
_LEG_COST  = _SLIP * 100.0 + 0.65        # per-leg $ cost (slippage×100 + commission), each side


# ── Polygon real-chain access (cached) ────────────────────────────────────────

class RealChain:
    def __init__(self, api_key: str, underlying: str = "SPY"):
        from data.polygon_client import PolygonClient
        self.c          = PolygonClient(api_key=api_key)
        self.underlying = underlying
        self._bars: dict[str, pd.Series] = {}
        self._ref:  dict[tuple, pd.DataFrame] = {}

    def contracts_asof(self, asof: str, exp_lo: str, exp_hi: str) -> pd.DataFrame:
        key = (asof, exp_lo, exp_hi)
        if key in self._ref:
            return self._ref[key]
        out, url = [], "/v3/reference/options/contracts"
        params = {"underlying_ticker": self.underlying, "as_of": asof,
                  "expiration_date.gte": exp_lo, "expiration_date.lte": exp_hi,
                  "limit": 1000}
        try:
            while url:
                d = self.c._get(url, params)
                out.extend(d.get("results", []) or [])
                url = (d.get("next_url") or "").replace(self.c.BASE, "") or None
                params = {}
        except Exception as e:
            logger.warning(f"contracts_asof {asof} failed: {e}")
        df = pd.DataFrame(out)
        self._ref[key] = df
        return df

    def bars(self, occ: str, frm: str, to: str) -> pd.Series:
        if occ in self._bars:
            return self._bars[occ]
        s = pd.Series(dtype=float)
        try:
            d = self.c._get(f"/v2/aggs/ticker/{occ}/range/1/day/{frm}/{to}",
                            {"adjusted": "true", "sort": "asc", "limit": 5000})
            s = pd.Series({pd.Timestamp(b["t"], unit="ms").normalize(): float(b["c"])
                           for b in (d.get("results", []) or []) if b.get("c") is not None})
        except Exception as e:
            logger.warning(f"bars {occ} failed: {e}")
        self._bars[occ] = s
        return s


# ── Black-Scholes (strike placement + fallback pricing only) ──────────────────

def _bs(S, K, T, iv, otype):
    from scipy.stats import norm
    if T <= 0 or iv <= 0:
        return max(0.0, (S - K) if otype == "call" else (K - S))
    d1 = (math.log(S / K) + (_R + 0.5 * iv ** 2) * T) / (iv * math.sqrt(T))
    d2 = d1 - iv * math.sqrt(T)
    if otype == "call":
        return S * norm.cdf(d1) - K * math.exp(-_R * T) * norm.cdf(d2)
    return K * math.exp(-_R * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def _nearest(df_side: pd.DataFrame, target_k: float):
    """Row of df_side whose strike is nearest target_k. df_side has strike_price, ticker."""
    if df_side.empty:
        return None
    idx = (df_side["strike_price"] - target_k).abs().idxmin()
    return df_side.loc[idx]


# ── The backtest ──────────────────────────────────────────────────────────────

def run_real_ic_backtest(
    price_df: pd.DataFrame,     # SPY daily, indexed by date, with 'close' (and high/low)
    vix_s: pd.Series,           # VIX close, indexed by date
    signal_fn: Callable,        # (i, ctx) -> bool : whether to ENTER on bar i
    api_key: str,
    underlying: str       = "SPY",
    start: Optional[str]  = None,
    starting_capital: float = 10_000.0,
    dte_target: int       = 45,
    dte_exit: int         = 21,
    wing_pct: float       = 0.05,
    short_delta: float    = 0.16,
    profit_target: float  = 0.50,
    stop_mult: float      = 2.0,
    max_concurrent: int   = 1,
) -> dict:
    """One-position-at-a-time (default) real-price condor sim. Returns dict with
    trades DataFrame, equity Series, and summary metrics."""
    chain = RealChain(api_key, underlying)

    px   = price_df.copy()
    px.index = pd.to_datetime(px.index)
    px   = px.sort_index()
    close = px["close"].astype(float)
    high  = px.get("high", close).astype(float)
    low   = px.get("low",  close).astype(float)
    vix   = pd.Series(vix_s.values, index=pd.to_datetime(vix_s.index)).reindex(close.index).ffill().fillna(20.0)

    # indicators for the signal (causal)
    from strategies.iron_condor_rules import _compute_ivr, _compute_adx, _compute_atr
    ivr = _compute_ivr(vix, 252)
    adx = _compute_adx(high, low, close, 14)
    atr = _compute_atr(high, low, close, 14)

    dates = list(close.index)
    n = len(dates)
    start_ts = pd.Timestamp(start) if start else dates[0]

    # ~16-delta short strike ≈ 1 std-dev move (z≈1.0 for 0.16 delta); use VIX for placement only
    z = 1.0

    capital = float(starting_capital)
    open_trades: list[dict] = []
    closed: list[dict] = []
    equity_curve = []

    def leg_price(series: pd.Series, d: pd.Timestamp, K: float, otype: str, spot: float, T: float):
        """Real close on/just before d; BS fallback if no bar exists at all."""
        if series is not None and not series.empty:
            s2 = series[series.index <= d]
            if not s2.empty:
                return float(s2.iloc[-1])
        iv = float(vix.loc[d] / 100.0) if d in vix.index else 0.2
        return _bs(spot, K, max(T, 1e-6), iv, otype)

    for i, d in enumerate(dates):
        spot    = float(close.iloc[i])
        vix_val = float(vix.iloc[i])

        # ── exits (real prices) ────────────────────────────────────────────
        still = []
        for tr in open_trades:
            dte_rem = (tr["expiry"] - d).days
            T_now   = max(dte_rem / 365.0, 1e-6)
            cs = leg_price(tr["bars"]["sc"], d, tr["Ksc"], "call", spot, T_now)
            cl = leg_price(tr["bars"]["lc"], d, tr["Klc"], "call", spot, T_now)
            ps = leg_price(tr["bars"]["sp"], d, tr["Ksp"], "put",  spot, T_now)
            pl = leg_price(tr["bars"]["lp"], d, tr["Klp"], "put",  spot, T_now)
            cur_cost = max((cs - cl) + (ps - pl), 0.0)
            pnl_per  = tr["credit"] - cur_cost

            reason = None
            if pnl_per >= profit_target * tr["credit"]:
                reason = "profit_target"
            elif dte_rem <= dte_exit:
                reason = "dte_exit"
            elif cur_cost >= stop_mult * tr["credit"]:
                reason = "stop_loss"
            elif dte_rem <= 0 or i == n - 1:
                reason = "expiry"

            if reason:
                gross = pnl_per * 100.0
                cost  = 4 * _LEG_COST * 2   # entry + exit, 4 legs
                net   = round(gross - cost, 2)
                capital += net
                closed.append({**{k: tr[k] for k in ("entry_date", "expiry", "credit",
                                  "Ksc", "Klc", "Ksp", "Klp")},
                               "exit_date": d, "exit_reason": reason,
                               "pnl": net, "winner": net > 0,
                               "dte_held": (d - tr["entry_date"]).days})
            else:
                still.append(tr)
        open_trades = still
        equity_curve.append(capital + sum(
            (t["credit"] - max((leg_price(t["bars"]["sc"], d, t["Ksc"], "call", spot, 1)
                                - leg_price(t["bars"]["lc"], d, t["Klc"], "call", spot, 1))
                               + (leg_price(t["bars"]["sp"], d, t["Ksp"], "put", spot, 1)
                                  - leg_price(t["bars"]["lp"], d, t["Klp"], "put", spot, 1)), 0.0)) * 100.0
            for t in open_trades))

        # ── entry ──────────────────────────────────────────────────────────
        if d < start_ts:
            continue
        if len(open_trades) >= max_concurrent:
            continue
        if (n - i) <= dte_target // 7 * 5:   # need room to hold
            continue

        ctx = {"ivr": float(ivr.iloc[i]) if not np.isnan(ivr.iloc[i]) else 0.0,
               "vix": vix_val,
               "adx": float(adx.iloc[i]) if not np.isnan(adx.iloc[i]) else 0.0,
               "atr_pct": (float(atr.iloc[i]) / spot) if (spot > 0 and not np.isnan(atr.iloc[i])) else 0.0,
               "i": i, "spot": spot}
        if not signal_fn(i, ctx):
            continue

        # find real expiry ~dte_target and real strikes
        asof   = d.date().isoformat()
        exp_lo = (d + pd.Timedelta(days=30)).date().isoformat()
        exp_hi = (d + pd.Timedelta(days=60)).date().isoformat()
        cdf = chain.contracts_asof(asof, exp_lo, exp_hi)
        if cdf.empty or "expiration_date" not in cdf.columns:
            continue
        cdf = cdf.copy()
        cdf["dte"] = (pd.to_datetime(cdf["expiration_date"]) - d).dt.days
        # choose expiry with deepest ladder nearest target
        stats = cdf.groupby("expiration_date").agg(
            dte=("dte", "first"), kmin=("strike_price", "min"),
            kmax=("strike_price", "max"), n=("strike_price", "size"))
        wide = stats[(stats.kmin <= spot * 0.90) & (stats.kmax >= spot * 1.10)]
        pool = wide if not wide.empty else stats
        best_exp = (pool["dte"] - dte_target).abs().idxmin()
        g = cdf[cdf["expiration_date"] == best_exp]
        T = max(int(g["dte"].iloc[0]) / 365.0, 1e-6)

        iv_place = max(vix_val / 100.0, 0.05)
        move = spot * iv_place * math.sqrt(T) * z
        wing = round(spot * wing_pct)
        calls = g[g.contract_type == "call"]; puts = g[g.contract_type == "put"]
        if calls.empty or puts.empty:
            continue
        rsc = _nearest(calls, spot + move);       rsp = _nearest(puts, spot - move)
        if rsc is None or rsp is None:
            continue
        rlc = _nearest(calls, rsc["strike_price"] + wing)
        rlp = _nearest(puts,  rsp["strike_price"] - wing)
        if rlc is None or rlp is None:
            continue
        Ksc, Klc = float(rsc["strike_price"]), float(rlc["strike_price"])
        Ksp, Klp = float(rsp["strike_price"]), float(rlp["strike_price"])
        if not (Klp < Ksp < Ksc < Klc):
            continue

        exp_dt = pd.Timestamp(best_exp)
        frm = asof; to = exp_dt.date().isoformat()
        legbars = {"sc": chain.bars(rsc["ticker"], frm, to),
                   "lc": chain.bars(rlc["ticker"], frm, to),
                   "sp": chain.bars(rsp["ticker"], frm, to),
                   "lp": chain.bars(rlp["ticker"], frm, to)}
        cs = leg_price(legbars["sc"], d, Ksc, "call", spot, T)
        cl = leg_price(legbars["lc"], d, Klc, "call", spot, T)
        ps = leg_price(legbars["sp"], d, Ksp, "put",  spot, T)
        pl = leg_price(legbars["lp"], d, Klp, "put",  spot, T)
        credit = (cs - cl) + (ps - pl)
        if credit <= 0.10:
            continue

        open_trades.append({
            "entry_date": d, "expiry": exp_dt, "credit": credit,
            "Ksc": Ksc, "Klc": Klc, "Ksp": Ksp, "Klp": Klp, "bars": legbars,
        })

    eq = pd.Series(equity_curve, index=dates, dtype=float)
    eq = eq[eq.index >= start_ts]
    trades = pd.DataFrame(closed)
    metrics = _summarize(eq, trades, starting_capital)
    return {"trades": trades, "equity": eq, "metrics": metrics}


def _summarize(eq: pd.Series, trades: pd.DataFrame, cap0: float) -> dict:
    if eq.empty:
        return {}
    ret = eq.iloc[-1] / cap0 - 1.0
    dd  = (eq / eq.cummax() - 1.0).min()
    dr  = eq.pct_change().dropna()
    sharpe = float(dr.mean() / dr.std() * math.sqrt(252)) if dr.std() > 0 else 0.0
    n = len(trades); wins = int(trades["winner"].sum()) if n else 0
    return {"final": float(eq.iloc[-1]), "return_pct": round(ret * 100, 1),
            "max_dd_pct": round(dd * 100, 1), "sharpe": round(sharpe, 2),
            "n_trades": n, "win_rate": round(100 * wins / n, 1) if n else 0.0,
            "total_pnl": round(float(trades["pnl"].sum()), 2) if n else 0.0}


# ── Default condor entry gate (mirrors iron_condor_rules) ─────────────────────

def _condor_signal(i: int, ctx: dict) -> bool:
    """Enter a condor when the rules-based gates pass: enough IVR, VIX in a sane
    band, low trend (ADX) and contained range (ATR%)."""
    return (ctx["ivr"] >= 0.20
            and 14.0 <= ctx["vix"] <= 45.0
            and ctx["adx"] <= 35.0
            and ctx["atr_pct"] <= 0.05)


# ── Standalone driver ─────────────────────────────────────────────────────────

def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)-5s %(name)s: %(message)s")
    log = logging.getLogger("validate_ic")

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--ticker", default="SPY")
    ap.add_argument("--days", type=int, default=380,
                    help="Trading days of history (~1.5y default; Polygon Starter caps ~2y)")
    ap.add_argument("--capital", type=float, default=10_000.0)
    args = ap.parse_args()

    api_key = os.environ.get("POLYGON_API_KEY", "").strip()
    if not api_key:
        log.error("POLYGON_API_KEY not set (add it to .env). This validator needs "
                  "real Polygon option chains.")
        return 2

    try:
        import yfinance as yf
    except ImportError:
        log.error("yfinance is required. `pip install yfinance`.")
        return 2

    cal_days = int(args.days * 1.5) + 60
    end   = pd.Timestamp.today().normalize()
    start = end - pd.Timedelta(days=cal_days)
    log.info(f"Fetching {args.ticker} + ^VIX from yfinance ({start.date()} → {end.date()})...")
    spy_raw = yf.download(args.ticker, start=start, end=end, progress=False, auto_adjust=False)
    vix_raw = yf.download("^VIX",       start=start, end=end, progress=False, auto_adjust=False)
    if spy_raw.empty or vix_raw.empty:
        log.error("yfinance returned empty data — check network / ticker.")
        return 2

    def _flatten(df: pd.DataFrame) -> pd.DataFrame:
        if isinstance(df.columns, pd.MultiIndex):
            df = df.droplevel(1, axis=1)
        df = df.rename(columns=str.lower)
        return df[[c for c in ("open", "high", "low", "close", "volume") if c in df.columns]]

    spy = _flatten(spy_raw).tail(args.days)
    vix = _flatten(vix_raw).reindex(spy.index).ffill()
    log.info(f"{args.ticker}: {len(spy)} bars  {spy.index.min().date()} → {spy.index.max().date()}")

    log.info("Running real-price condor backtest (pulls real Polygon chains; slow)...")
    result = run_real_ic_backtest(
        price_df=spy,
        vix_s=vix["close"],
        signal_fn=_condor_signal,
        api_key=api_key,
        underlying=args.ticker,
        starting_capital=args.capital,
    )

    m = result["metrics"] or {}
    print()
    print("=" * 64)
    print(f"REAL-PRICE IRON CONDOR VALIDATION  —  {args.ticker}")
    print("=" * 64)
    if not m:
        print("  No equity curve produced (no bars / no chains). Check key + dates.")
        return 1
    print(f"  Final equity     ${m['final']:>12,.0f}   (start ${args.capital:,.0f})")
    print(f"  Total return     {m['return_pct']:>+12.1f}%")
    print(f"  Max drawdown     {m['max_dd_pct']:>+12.1f}%")
    print(f"  Sharpe           {m['sharpe']:>12.2f}")
    print(f"  Trades           {m['n_trades']:>12}   (win {m['win_rate']:.1f}%)")
    print(f"  Total P&L        ${m['total_pnl']:>+11,.2f}")
    print("=" * 64)
    verdict = "EDGE" if (m["return_pct"] > 0 and m["sharpe"] > 0.3) else "NO EDGE"
    print(f"  Verdict: {verdict} on real prices.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
