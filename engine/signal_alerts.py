"""
Signal monitor + WhatsApp alerts for the validated trend / momentum strategies.

Computes today's BUY/HOLD verdict for each (strategy, ticker), compares it to the
last seen state on disk, and WhatsApps you ONLY when a signal flips (so you get a
text the day SPY crosses its 200-day average, not spam every day).

Run on a schedule (cron / Task Scheduler / the app's /schedule), e.g. daily after
the close:
    python -m alan_trader.engine.signal_alerts

Or import and call check_and_alert(...) from a Dash callback / button.
"""
from __future__ import annotations

import os
import json
import logging
import datetime as _dt
from pathlib import Path

logger = logging.getLogger(__name__)

_STATE_PATH = Path(__file__).resolve().parent.parent / "saved_models" / "signal_state.json"

# (slug, current_signal_fn, label)
def _strategies():
    from alan_trader.strategies.timing_base import load_close
    from alan_trader.strategies.trend_following import current_trend_signal
    from alan_trader.strategies.ts_momentum import current_tsmom_signal
    return {
        "trend_following": (current_trend_signal, "200-Day Trend"),
        "ts_momentum":     (current_tsmom_signal, "12-Month Momentum"),
    }, load_close


def _load_state() -> dict:
    try:
        return json.loads(_STATE_PATH.read_text())
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    try:
        _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _STATE_PATH.write_text(json.dumps(state, indent=2))
    except Exception as e:
        logger.warning(f"could not save signal state: {e}")


def compute_signals(tickers: list[str]) -> dict:
    """{ 'slug|TICKER': signal_dict } for every strategy × ticker."""
    strats, load_close = _strategies()
    out = {}
    closes = {t: load_close(t) for t in tickers}
    for t in tickers:
        c = closes[t]
        for slug, (fn, label) in strats.items():
            sig = fn(c)
            sig["label"] = label
            sig["ticker"] = t
            out[f"{slug}|{t}"] = sig
    return out


def format_signal_line(sig: dict) -> str:
    base = f"{sig.get('label')} · {sig.get('ticker')}: {sig.get('signal')} ({sig.get('state','')})"
    if "ma" in sig:
        base += f"\n  px {sig['price']} vs {sig['rule']} {sig['ma']} ({sig['pct_vs_ma']:+}%)"
    elif "ret_lookback_pct" in sig:
        base += f"\n  px {sig['price']} · {sig['rule']} = {sig['ret_lookback_pct']:+}%"
    base += f"\n  as of {sig.get('asof')}"
    return base


def check_and_alert(tickers: list[str] | None = None, force: bool = False) -> dict:
    """Compute signals, WhatsApp on any flip (or all, if force=True), persist state.
    Returns {checked, flips:[...], sent:bool, detail}."""
    from alan_trader.engine.notify import send_whatsapp, whatsapp_configured
    tickers = tickers or ["SPY"]
    sigs = compute_signals(tickers)
    prev = _load_state()

    flips = []
    for key, sig in sigs.items():
        cur = sig.get("signal")
        if cur in (None, "UNKNOWN"):
            continue
        old = (prev.get(key) or {}).get("signal")
        if force or (old is not None and old != cur) or (old is None):
            # alert on a genuine flip; on first-ever run (old is None) record silently
            if force or (old is not None and old != cur):
                flips.append((key, sig, old))

    sent, detail = False, "no flips"
    if flips:
        lines = ["📊 Strategy signal change:\n"]
        for key, sig, old in flips:
            arrow = f" (was {old})" if old else ""
            lines.append(format_signal_line(sig) + arrow + "\n")
        msg = "\n".join(lines).strip()
        if whatsapp_configured():
            sent, detail = send_whatsapp(msg)
        else:
            detail = "WhatsApp not configured (set WHATSAPP_PHONE + CALLMEBOT_APIKEY)"

    # persist latest
    _save_state({k: {"signal": v.get("signal"), "asof": v.get("asof")} for k, v in sigs.items()})
    return {"checked": list(sigs.keys()),
            "flips": [f"{k}: {old}→{s.get('signal')}" for k, s, old in flips],
            "sent": sent, "detail": detail,
            "signals": {k: v.get("signal") for k, v in sigs.items()}}


def send_trade_alert(text: str) -> tuple[bool, str]:
    """Manual 'text me this trade' hook (e.g. from a Dash button)."""
    from alan_trader.engine.notify import send_whatsapp, whatsapp_configured
    if not whatsapp_configured():
        return False, "WhatsApp not configured"
    return send_whatsapp(text)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", default="SPY")
    ap.add_argument("--force", action="store_true", help="send current signals even without a flip")
    a = ap.parse_args()
    res = check_and_alert([t.strip().upper() for t in a.tickers.split(",")], force=a.force)
    print(json.dumps(res, indent=2))
