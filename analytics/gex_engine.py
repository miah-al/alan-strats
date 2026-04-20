"""
GEX Engine — shared dealer gamma analytics.

Computes dealer Gamma Exposure (GEX) from an options chain snapshot and derives:
    • net GEX (multi-day and 0DTE split)
    • zero-gamma flip level (Brent root find on recomputed gamma)
    • put wall / call wall (largest gamma magnets)
    • per-strike GEX contribution

Sign convention for index / large-cap ETFs (SPX, SPY, QQQ):
    customers are net long calls / short puts
    → dealers are short calls / long puts
    → call GEX sign = +1, put GEX sign = -1
    → net_gex > 0 means dealers NET LONG gamma (vol-suppressive)

For single names where retail is net-put-buying, flip the sign convention.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy.stats import norm


_GEX_NOTIONAL_SCALE = 0.01   # convert to $ per 1% spot move


# ── BS gamma (scalar) ───────────────────────────────────────────────────────

def bs_gamma(S: float, K: float, T: float, iv: float, r: float = 0.045) -> float:
    """Black-Scholes gamma. T in years."""
    if T <= 0 or iv <= 0 or S <= 0 or K <= 0:
        return 0.0
    d1 = (math.log(S / K) + (r + 0.5 * iv * iv) * T) / (iv * math.sqrt(T))
    return float(norm.pdf(d1) / (S * iv * math.sqrt(T)))


def _compute_gamma_column(df: pd.DataFrame, cols: dict, spot: float,
                          r: float) -> np.ndarray:
    """Vectorised BS-gamma back-fill when the chain has no gamma column."""
    if cols["iv"] is None:
        return np.zeros(len(df), dtype=float)
    iv = pd.to_numeric(df[cols["iv"]], errors="coerce").fillna(0.0).to_numpy()
    K  = pd.to_numeric(df[cols["strike"]], errors="coerce").fillna(0.0).to_numpy()
    if cols["dte"] is not None:
        dte = pd.to_numeric(df[cols["dte"]], errors="coerce").fillna(0.0).to_numpy()
    elif cols["expiry"] is not None:
        exp = pd.to_datetime(df[cols["expiry"]], errors="coerce")
        today = pd.Timestamp.today().normalize()
        dte = (exp - today).dt.days.fillna(0).to_numpy()
    else:
        dte = np.full(len(df), 30.0)
    T = np.maximum(dte, 0.0) / 365.0
    mask = (iv > 0) & (K > 0) & (T > 0) & (spot > 0)
    gamma_out = np.zeros(len(df), dtype=float)
    if mask.any():
        # d1 vectorised
        d1 = (np.log(spot / np.where(K > 0, K, 1)) + (r + 0.5 * iv * iv) * T) / \
             np.where((iv * np.sqrt(T)) > 0, iv * np.sqrt(T), 1)
        phi = np.exp(-0.5 * d1 * d1) / math.sqrt(2 * math.pi)
        denom = spot * iv * np.sqrt(T)
        gamma_vec = np.where(denom > 0, phi / denom, 0.0)
        gamma_out[mask] = gamma_vec[mask]
    return gamma_out


# ── Column normalisation ────────────────────────────────────────────────────

_GAMMA_COLS  = ("Gamma", "gamma")
_OI_COLS     = ("OpenInterest", "open_interest", "oi")
_VOL_COLS    = ("Volume", "volume", "vol")
_STRIKE_COLS = ("StrikePrice", "strike_price", "strike", "Strike")
_TYPE_COLS   = ("OptionType", "option_type", "type", "contract_type")
_IV_COLS     = ("iv", "IV", "implied_volatility", "ImpliedVolatility", "ImpliedVol")
_DTE_COLS    = ("dte", "DTE", "days_to_expiry")
_EXPIRY_COLS = ("expiry", "Expiry", "expiration_date", "ExpirationDate")


def _first_col(df: pd.DataFrame, names: tuple) -> Optional[str]:
    for n in names:
        if n in df.columns:
            return n
    return None


def _normalize_chain(chain: pd.DataFrame) -> dict:
    """Return dict of column names or raise ValueError if required are missing.

    Gamma and OI are auto-derivable: if gamma column is absent/empty we
    compute via BS from IV; if OI is absent/empty we fall back to Volume.
    Only strike and option_type are hard requirements; IV is required to
    back-fill gamma when gamma is missing.
    """
    cols = {
        "gamma":  _first_col(chain, _GAMMA_COLS),
        "oi":     _first_col(chain, _OI_COLS),
        "volume": _first_col(chain, _VOL_COLS),
        "strike": _first_col(chain, _STRIKE_COLS),
        "type":   _first_col(chain, _TYPE_COLS),
        "iv":     _first_col(chain, _IV_COLS),
        "dte":    _first_col(chain, _DTE_COLS),
        "expiry": _first_col(chain, _EXPIRY_COLS),
    }
    for required in ("strike", "type"):
        if cols[required] is None:
            raise ValueError(
                f"gex_engine: options chain missing required column '{required}'. "
                f"Got: {list(chain.columns)}"
            )
    if cols["gamma"] is None and cols["iv"] is None:
        raise ValueError(
            "gex_engine: need either 'gamma' OR 'iv' to compute GEX — neither present."
        )
    if cols["oi"] is None and cols["volume"] is None:
        raise ValueError(
            "gex_engine: need either 'open_interest' OR 'volume' — neither present."
        )
    return cols


# ── Result container ────────────────────────────────────────────────────────

@dataclass
class GEXSnapshot:
    """Structured output from compute_dealer_gex."""
    spot:              float
    net_gex:           float            # $ per 1% move, dealer-signed
    call_gex:          float            # dealer call GEX ($)
    put_gex:           float            # dealer put GEX ($)
    flip_level:        float            # zero-gamma strike
    dist_to_flip_pct:  float            # (spot - flip) / spot
    call_wall:         Optional[float]  # largest positive-gamma strike above spot
    put_wall:          Optional[float]  # largest negative-gamma strike below spot
    gex_by_strike:     pd.Series        # index=strike, value=dealer $ GEX per 1%
    net_gex_0dte:      float            # 0DTE subset only
    net_gex_multiday:  float            # DTE >= 2
    sign_convention:   str = "index_retail_call_long"
    warnings:          list = field(default_factory=list)


# ── Core calculator ─────────────────────────────────────────────────────────

def compute_dealer_gex(
    chain:             pd.DataFrame,
    spot:              float,
    sign_convention:   str   = "index_retail_call_long",
    wall_threshold:    float = 1.5,
    wall_min_dist_pct: float = 0.005,
    r:                 float = 0.045,
) -> GEXSnapshot:
    """
    Compute dealer GEX structure from a chain snapshot.

    Parameters
    ----------
    chain : DataFrame
        Must have columns: gamma, open_interest, strike, option_type.
        Optional: iv, dte, expiry (improve flip-level accuracy and enable 0DTE split).
    spot : float
        Underlying spot price.
    sign_convention : str
        'index_retail_call_long' (default) — retail long calls / short puts → dealers short calls / long puts.
        'retail_put_long'                  — retail long puts / short calls → dealers long calls / short puts (inverted).
    wall_threshold : float
        Per-strike |GEX| must exceed this × median absolute strike GEX to count as a wall.
    wall_min_dist_pct : float
        Walls within this fractional distance of spot are ignored (too close to matter).
    """
    if chain is None or chain.empty:
        raise ValueError("gex_engine: chain is empty")
    if spot <= 0:
        raise ValueError(f"gex_engine: spot must be positive, got {spot}")

    cols = _normalize_chain(chain)
    df = chain.copy()

    df[cols["strike"]] = pd.to_numeric(df[cols["strike"]], errors="coerce").fillna(0.0)

    # ── Fill gamma: use column if usable, else BS-compute from IV ──────────
    gamma_vals: np.ndarray
    if cols["gamma"] is not None:
        g = pd.to_numeric(df[cols["gamma"]], errors="coerce")
        if g.notna().any() and (g.abs() > 0).any():
            gamma_vals = g.fillna(0.0).to_numpy()
        else:
            gamma_vals = _compute_gamma_column(df, cols, spot, r)
    else:
        gamma_vals = _compute_gamma_column(df, cols, spot, r)

    # ── Fill OI: prefer OpenInterest, fall back to Volume if OI empty ──────
    oi_source = "oi"
    if cols["oi"] is not None:
        oi = pd.to_numeric(df[cols["oi"]], errors="coerce")
        if oi.notna().any() and (oi > 0).any():
            oi_vals = oi.fillna(0.0).to_numpy()
        elif cols["volume"] is not None:
            oi_vals = pd.to_numeric(df[cols["volume"]], errors="coerce").fillna(0.0).to_numpy()
            oi_source = "volume"
        else:
            oi_vals = oi.fillna(0.0).to_numpy()
    else:
        oi_vals = pd.to_numeric(df[cols["volume"]], errors="coerce").fillna(0.0).to_numpy()
        oi_source = "volume"

    is_call = df[cols["type"]].astype(str).str.lower().str.startswith("c")

    # Sign convention
    if sign_convention == "index_retail_call_long":
        sign_call, sign_put = +1.0, -1.0
    elif sign_convention == "retail_put_long":
        sign_call, sign_put = -1.0, +1.0
    else:
        raise ValueError(f"gex_engine: unknown sign_convention {sign_convention!r}")

    # Dealer-signed GEX per contract ($/1% move)
    gex_per = gamma_vals * oi_vals * 100 * spot * spot * _GEX_NOTIONAL_SCALE
    signed  = np.where(is_call, sign_call * gex_per, sign_put * gex_per)

    is_call_arr = is_call.values if hasattr(is_call, "values") else np.asarray(is_call)
    call_gex = float(gex_per[is_call_arr].sum() * sign_call)
    put_gex  = float(gex_per[~is_call_arr].sum() * sign_put)
    net_gex  = float(signed.sum())

    # Per-strike aggregation (net) + call/put breakdown for wall detection
    tmp = pd.DataFrame({
        "strike":   df[cols["strike"]],
        "gex":      signed,
        "is_call":  is_call.values if hasattr(is_call, "values") else is_call,
    })
    tmp = tmp[tmp["strike"] > 0]
    gex_by_strike      = tmp.groupby("strike")["gex"].sum().sort_index()
    call_gex_by_strike = tmp[tmp["is_call"]].groupby("strike")["gex"].sum().sort_index()
    put_gex_by_strike  = tmp[~tmp["is_call"]].groupby("strike")["gex"].sum().sort_index()

    # 0DTE split
    net_gex_0dte, net_gex_multiday = 0.0, net_gex
    if cols["dte"] is not None:
        dte_vals = pd.to_numeric(df[cols["dte"]], errors="coerce").fillna(999)
        mask_0   = dte_vals.to_numpy() <= 1
        net_gex_0dte     = float(signed[mask_0].sum())
        net_gex_multiday = float(signed[~mask_0].sum())
    elif cols["expiry"] is not None:
        try:
            exp = pd.to_datetime(df[cols["expiry"]], errors="coerce")
            today = pd.Timestamp.today().normalize()
            dte_vals = (exp - today).dt.days.fillna(999)
            mask_0 = dte_vals.to_numpy() <= 1
            net_gex_0dte     = float(signed[mask_0].sum())
            net_gex_multiday = float(signed[~mask_0].sum())
        except Exception:
            pass

    # Flip level — with recomputed gamma when IV is present
    flip_level = find_flip_level(
        chain        = df,
        cols         = cols,
        spot         = spot,
        sign_call    = sign_call,
        sign_put     = sign_put,
        r            = r,
        fallback_net = gex_by_strike,
    )
    dist_to_flip_pct = (spot - flip_level) / (spot + 1e-12)

    # Walls — computed from call-only / put-only per-strike GEX
    call_wall, put_wall = detect_walls(
        call_gex_by_strike = call_gex_by_strike,
        put_gex_by_strike  = put_gex_by_strike,
        spot               = spot,
        threshold          = wall_threshold,
        min_dist_pct       = wall_min_dist_pct,
    )

    warnings: list[str] = []
    if abs(net_gex) < 1e5:
        warnings.append("net_gex near zero — regime noise")
    if cols["iv"] is None:
        warnings.append("no IV column — flip level uses snapshot gamma (less accurate)")
    if oi_source == "volume":
        warnings.append("OpenInterest missing — using Volume as proxy (GEX magnitude approximate)")

    return GEXSnapshot(
        spot              = float(spot),
        net_gex           = net_gex,
        call_gex          = call_gex,
        put_gex           = put_gex,
        flip_level        = float(flip_level),
        dist_to_flip_pct  = float(dist_to_flip_pct),
        call_wall         = call_wall,
        put_wall          = put_wall,
        gex_by_strike     = gex_by_strike,
        net_gex_0dte      = net_gex_0dte,
        net_gex_multiday  = net_gex_multiday,
        sign_convention   = sign_convention,
        warnings          = warnings,
    )


# ── Flip level ──────────────────────────────────────────────────────────────

def find_flip_level(
    chain:        pd.DataFrame,
    cols:         dict,
    spot:         float,
    sign_call:    float,
    sign_put:     float,
    r:            float,
    fallback_net: pd.Series,
) -> float:
    """
    Solve for spot S* where ΣGEX(S*) = 0, with gamma RECOMPUTED at S*.
    Falls back to cumulative-sum sign change on snapshot gamma if IV missing.
    """
    iv_col  = cols["iv"]
    dte_col = cols["dte"]

    if iv_col is None or dte_col is None:
        return _flip_from_cum_gex(fallback_net, spot)

    strikes = pd.to_numeric(chain[cols["strike"]], errors="coerce").fillna(0).values
    ivs     = pd.to_numeric(chain[iv_col],        errors="coerce").fillna(0).values
    dtes    = pd.to_numeric(chain[dte_col],       errors="coerce").fillna(0).values
    if cols.get("oi") is not None:
        _oi_series = pd.to_numeric(chain[cols["oi"]], errors="coerce").fillna(0)
        if (_oi_series > 0).any():
            ois = _oi_series.values
        elif cols.get("volume") is not None:
            ois = pd.to_numeric(chain[cols["volume"]], errors="coerce").fillna(0).values
        else:
            ois = _oi_series.values
    elif cols.get("volume") is not None:
        ois = pd.to_numeric(chain[cols["volume"]], errors="coerce").fillna(0).values
    else:
        ois = np.zeros(len(chain))
    is_call = chain[cols["type"]].astype(str).str.lower().str.startswith("c").values

    mask = (strikes > 0) & (ivs > 0) & (dtes > 0) & (ois > 0)
    if mask.sum() < 10:
        return _flip_from_cum_gex(fallback_net, spot)

    strikes, ivs, dtes, ois, is_call = strikes[mask], ivs[mask], dtes[mask], ois[mask], is_call[mask]
    Ts = dtes / 365.0

    def net_gex_at(S):
        total = 0.0
        for k, iv, T, oi, c in zip(strikes, ivs, Ts, ois, is_call):
            g = bs_gamma(S, k, T, iv, r)
            sign = sign_call if c else sign_put
            total += sign * g * oi * 100 * S * S * _GEX_NOTIONAL_SCALE
        return total

    try:
        lo, hi = spot * 0.80, spot * 1.20
        f_lo, f_hi = net_gex_at(lo), net_gex_at(hi)
        if f_lo * f_hi > 0:
            # No sign change in wide bracket → fallback
            return _flip_from_cum_gex(fallback_net, spot)
        return float(brentq(net_gex_at, lo, hi, xtol=0.25, maxiter=50))
    except Exception:
        return _flip_from_cum_gex(fallback_net, spot)


def _flip_from_cum_gex(gex_by_strike: pd.Series, spot: float) -> float:
    """Sign-change strike on cumulative GEX using snapshot gamma. Linear interpolation."""
    if gex_by_strike.empty:
        return spot
    cum = gex_by_strike.sort_index().cumsum()
    prev_k, prev_v = None, None
    for k, v in cum.items():
        if prev_v is not None and prev_v * v < 0:
            frac = abs(prev_v) / (abs(prev_v) + abs(v) + 1e-12)
            return float(prev_k + frac * (k - prev_k))
        prev_k, prev_v = k, v
    return float(spot)


# ── Walls ───────────────────────────────────────────────────────────────────

def detect_walls(
    call_gex_by_strike: pd.Series,
    put_gex_by_strike:  pd.Series,
    spot:               float,
    threshold:          float = 1.5,
    min_dist_pct:       float = 0.005,
) -> tuple[Optional[float], Optional[float]]:
    """
    Return (call_wall, put_wall).

    Call wall: strike ABOVE spot with largest |call GEX| — price magnet where
               dealer call hedging is concentrated.
    Put wall:  strike BELOW spot with largest |put GEX| — downside support
               from dealer long-put positioning.

    A wall must exceed threshold × median |GEX| (within its side of the chain)
    and sit at least min_dist_pct away from spot.
    """
    call_wall: Optional[float] = None
    put_wall:  Optional[float] = None

    # Call wall — look for largest-magnitude call GEX above spot
    if not call_gex_by_strike.empty:
        above = call_gex_by_strike[call_gex_by_strike.index > spot * (1 + min_dist_pct)]
        if not above.empty:
            med_abs = float(call_gex_by_strike.abs().median()) or 0.0
            bar     = threshold * med_abs
            above_big = above[above.abs() > bar]
            if not above_big.empty:
                call_wall = float(above_big.abs().idxmax())

    # Put wall — largest-magnitude put GEX below spot
    if not put_gex_by_strike.empty:
        below = put_gex_by_strike[put_gex_by_strike.index < spot * (1 - min_dist_pct)]
        if not below.empty:
            med_abs = float(put_gex_by_strike.abs().median()) or 0.0
            bar     = threshold * med_abs
            below_big = below[below.abs() > bar]
            if not below_big.empty:
                put_wall = float(below_big.abs().idxmax())

    return call_wall, put_wall


# ── Regime classifier ───────────────────────────────────────────────────────

def classify_regime(snap: GEXSnapshot, near_flip_pct: float = 0.0025) -> str:
    """
    Three-way regime label used by the dealer_gamma_regime strategy.
    Returns: 'positive' | 'negative' | 'near_flip'.
    """
    if abs(snap.dist_to_flip_pct) < near_flip_pct:
        return "near_flip"
    if snap.spot > snap.flip_level:
        return "positive"
    return "negative"


# ── Expected move (used for wing widths) ────────────────────────────────────

def expected_move_pct(iv_atm: float, dte: int) -> float:
    """1-sigma expected move as a fraction of spot."""
    if iv_atm <= 0 or dte <= 0:
        return 0.01
    return float(iv_atm * math.sqrt(max(dte, 1) / 365.0))
