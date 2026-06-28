"""
app/pages/strategies/display_rows.py — grid row formatters.

Pure presentation helpers extracted from the strategies page monolith. Each
`_display_row_*` maps a raw scan result dict to the display columns for that
strategy's screener grid. No callbacks, no data access — depends only on the
numeric formatters in format.py and the status-pill renderer.
"""
from __future__ import annotations

from dash import html

from app.pages.strategies.format import (
    _fmt_pct, _fmt2, _fmt_price, _status_pills,
)


def _status_pill_row(rows: list[dict]) -> html.Div:
    return _status_pills(rows)


# ── Format display rows ───────────────────────────────────────────────────────

def _display_row_trend(r: dict) -> dict:
    """Display row for the trend / momentum timing screener."""
    status = "BUY (uptrend)" if r.get("all_pass") else "HOLD (cash)"
    return {
        "Ticker":     r.get("Ticker", ""),
        "Price":      round(r.get("Price", 0), 2),
        "Signal":     r.get("Signal", ""),
        "Reference":  r.get("Reference", ""),
        "Strength %": round(r.get("Strength %", 0), 2),
        "Status":     status,
        "all_pass":   r.get("all_pass", False),
        "n_pass":     r.get("n_pass", 0),
    }


def _display_row_ic(r: dict) -> dict:
    status = "Trade-Ready" if (r.get("all_pass") and r.get("_chain")) else (
        "Partial" if r.get("n_pass", 0) > 0 else "Blocked"
    )
    return {
        "Ticker":      r.get("Ticker", ""),
        "Price":       round(r.get("Price", 0), 2),
        "ATM IV":      _fmt_pct(r.get("ATM IV")),
        "IVR":         _fmt_pct(r.get("IVR")),
        "HV20":        _fmt_pct(r.get("HV20")),
        "VRP":         _fmt_pct(r.get("VRP")),
        "IV/HV":       _fmt2(r.get("IV/HV")),
        "VIX":         round(r.get("VIX", 0), 2),
        "ADX":         round(r.get("ADX", 0), 1),
        "ATR%":        f"{r.get('ATR%', 0):.2%}",
        "Score":       round(r.get("score", 0), 1),
        "Status":      status,
        "all_pass":    r.get("all_pass", False),
        "n_pass":      r.get("n_pass", 0),
        "_chain":      r.get("_chain"),          # real strikes dict or None
        "_chain_err":  r.get("_chain_err"),     # error string if chain fetch failed
        "_atm_iv_raw": r.get("ATM IV"),         # raw float for BS calc
    }


def _display_row_vsf(r: dict) -> dict:
    status = "Trade-Ready" if r.get("all_pass") else (
        "Partial" if r.get("n_pass", 0) > 0 else "Blocked"
    )
    return {
        "Ticker":      r.get("Ticker", ""),
        "Price":       round(r.get("Price", 0), 2),
        "VIX":         round(r.get("VIX", 0), 2),
        "VIX 20d avg": round(r.get("VIX 20d avg", 0), 2),
        "VIX / 20d":   _fmt2(r.get("VIX / 20d")),
        "ATM IV":      _fmt_pct(r.get("ATM IV")),
        "HV20":        _fmt_pct(r.get("HV20")),
        "IVR":         _fmt_pct(r.get("IVR")),
        "ATR%":        f"{r.get('ATR%', 0):.2%}",
        "MA200":       _fmt2(r.get("MA200")),
        "Score":       round(r.get("score", 0), 1),
        "Status":      status,
        "all_pass":    r.get("all_pass", False),
        "n_pass":      r.get("n_pass", 0),
    }


def _display_row_ivr(r: dict) -> dict:
    status = "Trade-Ready" if r.get("all_pass") else (
        "Partial" if r.get("n_pass", 0) > 0 else "Blocked"
    )
    return {
        "Ticker":      r.get("Ticker", ""),
        "Price":       round(r.get("Price", 0), 2),
        "ATM IV":      _fmt_pct(r.get("ATM IV")),
        "IVR":         _fmt_pct(r.get("IVR")),
        "VRP":         _fmt_pct(r.get("VRP")),
        "HV20":        _fmt_pct(r.get("HV20")),
        "IV/HV":       _fmt2(r.get("IV/HV")),
        "VIX":         round(r.get("VIX", 0), 2),
        "ADX":         round(r.get("ADX", 0), 1),
        "ATR%":        f"{r.get('ATR%', 0):.2%}",
        "Trend":       r.get("Trend", "—"),
        "Spread Type": r.get("Spread Type", "—"),
        "Score":       round(r.get("score", 0), 1),
        "Status":      status,
        "all_pass":    r.get("all_pass", False),
        "n_pass":      r.get("n_pass", 0),
    }


def _display_row_va(r: dict) -> dict:
    status = "Trade-Ready" if r.get("all_pass") else (
        "Partial" if r.get("n_pass", 0) > 0 else "Blocked"
    )
    return {
        "Ticker":   r.get("Ticker", ""),
        "Price":    round(r.get("Price", 0), 2),
        "ATM IV":   _fmt_pct(r.get("ATM IV")),
        "HV20":     _fmt_pct(r.get("HV20")),
        "IV/HV":    _fmt2(r.get("IV/HV")),
        "VRP":      _fmt_pct(r.get("VRP")),
        "IVR":      _fmt_pct(r.get("IVR")),
        "VIX":      round(r.get("VIX", 0), 2),
        "ATR%":     f"{r.get('ATR%', 0):.2%}",
        "Score":    round(r.get("score", 0), 1),
        "Status":   status,
        "all_pass": r.get("all_pass", False),
        "n_pass":   r.get("n_pass", 0),
    }


def _display_row_gex(r: dict) -> dict:
    spy_w  = r.get("SPY Weight", 0)
    score  = r.get("score", round(spy_w * 100))   # fallback: SPY weight as score proxy
    status = "Trade-Ready" if spy_w >= 0.75 else ("Partial" if spy_w >= 0.35 else "Blocked")
    return {
        "Ticker":       r.get("Ticker", ""),
        "Price":        round(r.get("Price", 0), 2),
        "VIX":          round(r.get("VIX", 0), 2),
        "Regime":       r.get("Regime", "—"),
        "SPY Weight":   f"{spy_w*100:.0f}%",
        "Signal":       r.get("Signal", "—"),
        "ATR%":         f"{r.get('ATR%', 0)*100:.2f}%",
        "5d Return":    f"{r.get('5d Return', 0)*100:.1f}%",
        "Regime Label": r.get("Regime Label", "—"),
        "Score":        score,
        "Status":       status,
        "all_pass":     spy_w >= 0.75,
        "n_pass":       1 if spy_w > 0 else 0,
    }


def _display_row_bwb(r: dict) -> dict:
    status = "Trade-Ready" if r.get("all_pass") else (
        "Partial" if r.get("n_pass", 0) > 0 else "Blocked"
    )
    return {
        "Ticker":       r.get("Ticker", ""),
        "Price":        round(r.get("Price", 0), 2),
        "ATM IV":       _fmt_pct(r.get("ATM IV")),
        "IVR":          _fmt_pct(r.get("IVR")),
        "VIX":          round(r.get("VIX", 0), 2),
        "ADX":          round(r.get("ADX", 0), 1),
        "Narrow Wing":  _fmt2(r.get("Narrow Wing")),
        "Wide Wing":    _fmt2(r.get("Wide Wing")),
        "Score":        round(r.get("score", 0), 1),
        "Status":       status,
        "all_pass":     r.get("all_pass", False),
        "n_pass":       r.get("n_pass", 0),
    }


def _display_row_cal(r: dict) -> dict:
    status = "Trade-Ready" if r.get("all_pass") else (
        "Partial" if r.get("n_pass", 0) > 0 else "Blocked"
    )
    return {
        "Ticker":   r.get("Ticker", ""),
        "Price":    round(r.get("Price", 0), 2),
        "ATM IV":   _fmt_pct(r.get("ATM IV")),
        "HV20":     _fmt_pct(r.get("HV20")),
        "VRP":      _fmt_pct(r.get("VRP")),
        "IVR":      _fmt_pct(r.get("IVR")),
        "VIX":      round(r.get("VIX", 0), 2),
        "ADX":      round(r.get("ADX", 0), 1),
        "Score":    round(r.get("score", 0), 1),
        "Status":   status,
        "all_pass": r.get("all_pass", False),
        "n_pass":   r.get("n_pass", 0),
    }


def _display_row_earn(r: dict) -> dict:
    status = "Trade-Ready" if r.get("all_pass") else (
        "Partial" if r.get("n_pass", 0) > 0 else "Blocked"
    )
    dte = r.get("Days to Earnings")
    return {
        "Ticker":           r.get("Ticker", ""),
        "Price":            round(r.get("Price", 0), 2),
        "ATM IV":           _fmt_pct(r.get("ATM IV")),
        "IVR":              _fmt_pct(r.get("IVR")),
        "Days to Earnings": str(dte) if dte is not None else "—",
        "Impl. Move":       _fmt_pct(r.get("Impl. Move")),
        "Straddle Credit":  _fmt_price(r.get("Straddle Credit")),
        "VIX":              round(r.get("VIX", 0), 2),
        "Score":            round(r.get("score", 0), 1),
        "Status":           status,
        "all_pass":         r.get("all_pass", False),
        "n_pass":           r.get("n_pass", 0),
    }


def _display_row_wheel(r: dict) -> dict:
    status = "Trade-Ready" if r.get("all_pass") else (
        "Partial" if r.get("n_pass", 0) > 0 else "Blocked"
    )
    return {
        "Ticker":     r.get("Ticker", ""),
        "Price":      round(r.get("Price", 0), 2),
        "MA50":       _fmt2(r.get("MA50")),
        "ATM IV":     _fmt_pct(r.get("ATM IV")),
        "IVR":        _fmt_pct(r.get("IVR")),
        "VIX":        round(r.get("VIX", 0), 2),
        "ADX":        round(r.get("ADX", 0), 1),
        "Put Strike": _fmt2(r.get("Put Strike")),
        "~Premium":   _fmt_price(r.get("~Premium")),
        "Score":      round(r.get("score", 0), 1),
        "Status":     status,
        "all_pass":   r.get("all_pass", False),
        "n_pass":     r.get("n_pass", 0),
    }


def _display_row_bps(r: dict) -> dict:
    status = "Trade-Ready" if r.get("all_pass") else (
        "Partial" if r.get("n_pass", 0) > 0 else "Blocked"
    )
    return {
        "Ticker":       r.get("Ticker", ""),
        "Price":        round(r.get("Price", 0), 2),
        "MA50":         _fmt2(r.get("MA50")),
        "ATM IV":       _fmt_pct(r.get("ATM IV")),
        "IVR":          _fmt_pct(r.get("IVR")),
        "Short Strike": _fmt2(r.get("Short Strike")),
        "Long Strike":  _fmt2(r.get("Long Strike")),
        "Width":        _fmt2(r.get("Width")),
        "~Credit":      _fmt_price(r.get("~Credit")),
        "Credit/Width": _fmt2(r.get("Credit/Width")),
        "Score":        round(r.get("score", 0), 1),
        "Status":       status,
        "all_pass":     r.get("all_pass", False),
        "n_pass":       r.get("n_pass", 0),
    }


def _display_row_put_steal(r: dict) -> dict:
    status = "Trade-Ready" if r.get("all_pass") else (
        "Partial" if r.get("n_pass", 0) > 0 else "Blocked"
    )
    chain = r.get("_chain") or {}
    # Use real Polygon strikes/credit if available, else fall back to BS estimates
    short_k  = chain.get("short_put_k",  r.get("Short Put"))
    long_k   = chain.get("long_put_k",   r.get("Long Put"))
    credit   = chain.get("net_credit",   r.get("~Credit"))
    max_loss = chain.get("max_loss",     None)
    exp      = chain.get("best_exp",     "")
    source   = "Polygon" if chain else "~BS est."
    return {
        "Ticker":    r.get("Ticker", ""),
        "Price":     round(r.get("Price", 0), 2),
        "NII":       f"{r.get('NII', 0):.3f}",
        "Strike X":  _fmt2(r.get("Strike X")),
        "Short Put": _fmt2(short_k),
        "Long Put":  _fmt2(long_k),
        "~Credit":   _fmt_price(credit),
        "Max Loss":  _fmt_price(-max_loss) if max_loss else "—",
        "Expiry":    exp,
        "IV Src":    source,
        "ATM IV":    _fmt_pct(r.get("ATM IV")),
        "IVR":       _fmt_pct(r.get("IVR")),
        "VIX":       round(r.get("VIX", 0), 1),
        "Score":     round(r.get("score", 0), 1),
        "Status":    status,
        "all_pass":  r.get("all_pass", False),
        "n_pass":    r.get("n_pass", 0),
        "_chain":    chain,
        "_chain_err": r.get("_chain_err", ""),
    }


def _display_row_hmm(r: dict) -> dict:
    status = r.get("Status", "—")
    return {
        "Ticker":   r.get("Ticker", ""),
        "Price":    round(r.get("Price", 0), 2),
        "VIX":      round(r.get("VIX", 0), 2),
        "IVR":      _fmt_pct(r.get("IVR")),
        "Regime":   r.get("Regime", "—"),
        "State":    r.get("State", "—"),
        "P(state)": _fmt2(r.get("P(state)")),
        "Trade":    r.get("Trade", "—"),
        "Signal":   r.get("Signal", "—"),
        "5d Ret":   f"{(r.get('5d Ret')  or 0)*100:+.1f}%",
        "20d Ret":  f"{(r.get('20d Ret') or 0)*100:+.1f}%",
        "Mode":     r.get("Mode", "—"),
        "Score":    round(r.get("score", 0), 1),
        "Status":   status,
        "all_pass": r.get("all_pass", False),
        "n_pass":   r.get("n_pass", 0),
    }


def _display_row_emp(r: dict) -> dict:
    return {
        "Ticker":      r.get("Ticker", ""),
        "Price":       round(r.get("Price", 0), 2),
        "VIX":         round(r.get("VIX", 0), 2),
        "ATM IV":      _fmt_pct(r.get("ATM IV")),
        "IVR":         _fmt_pct(r.get("IVR")),
        "OpEx Week":   r.get("OpEx Week", "—"),
        "DTE to OpEx": r.get("DTE to OpEx", "—"),
        "Structure":   r.get("Structure", "—"),
        "Score":       round(r.get("score", 0), 1),
        "Status":      r.get("Status", "—"),
        "all_pass":    r.get("all_pass", False),
        "n_pass":      r.get("n_pass", 0),
    }


def _display_row_ssd(r: dict) -> dict:
    return {
        "Ticker":     r.get("Ticker", ""),
        "Price":      round(r.get("Price", 0), 2),
        "VIX":        round(r.get("VIX", 0), 2),
        "IVR":        _fmt_pct(r.get("IVR")),
        "Vol Ratio":  f"{(r.get('Vol Ratio') or 0):.2f}×",
        "5d Ret":     f"{(r.get('5d Ret')  or 0)*100:+.1f}%",
        "20d Ret":    f"{(r.get('20d Ret') or 0)*100:+.1f}%",
        "P(squeeze)": _fmt2(r.get("P(squeeze)")),
        "Structure":  r.get("Structure", "—"),
        "Mode":       r.get("Mode", "—"),
        "Score":      round(r.get("score", 0), 1),
        "Status":     r.get("Status", "—"),
        "all_pass":   r.get("all_pass", False),
        "n_pass":     r.get("n_pass", 0),
    }


def _display_row_trp(r: dict) -> dict:
    return {
        "Ticker":       r.get("Ticker", ""),
        "Price":        round(r.get("Price", 0), 2),
        "VIX":          round(r.get("VIX", 0), 2),
        "ATM IV":       _fmt_pct(r.get("ATM IV")),
        "IVR":          _fmt_pct(r.get("IVR")),
        "Long Strike":  _fmt2(r.get("Long Strike")),
        "Short Strike": _fmt2(r.get("Short Strike")),
        "Width":        _fmt2(r.get("Width")),
        "DTE":          r.get("DTE", "—"),
        "~Debit":       _fmt_price(r.get("~Debit")),
        "Max Payout":   _fmt_price(r.get("Max Payout")),
        "Structure":    r.get("Structure", "—"),
        "Score":        round(r.get("score", 0), 1),
        "Status":       r.get("Status", "—"),
        "all_pass":     r.get("all_pass", False),
        "n_pass":       r.get("n_pass", 0),
    }


def _display_row_nsn(r: dict) -> dict:
    return {
        "Ticker":     r.get("Ticker", ""),
        "Price":      round(r.get("Price", 0), 2),
        "VIX":        round(r.get("VIX", 0), 2),
        "IVR":        _fmt_pct(r.get("IVR")),
        "1d Ret":     f"{(r.get('1d Ret')  or 0)*100:+.2f}%",
        "5d Ret":     f"{(r.get('5d Ret')  or 0)*100:+.1f}%",
        "z (proxy)":  _fmt2(r.get("z (proxy)")),
        "z thresh":   _fmt2(r.get("z thresh")),
        "Signal":     r.get("Signal", "—"),
        "Structure":  r.get("Structure", "—"),
        "Mode":       r.get("Mode", "—"),
        "Score":      round(r.get("score", 0), 1),
        "Status":     r.get("Status", "—"),
        "all_pass":   r.get("all_pass", False),
        "n_pass":     r.get("n_pass", 0),
    }
