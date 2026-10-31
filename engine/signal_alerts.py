"""
Signal monitor + WhatsApp alerts for strategies that publish a live signal.

Computes today's verdict for each (strategy, ticker), compares it to the last
seen state on disk, and WhatsApps you ONLY when a signal flips (so you get a
text the day a signal changes, not spam every day).

Which strategies take part is decided by the plugins: any registered strategy
whose ``current_signal(close)`` returns a dict is monitored. The platform
itself names none.

Run on a schedule (cron / Task Scheduler / the app's /schedule), e.g. daily after
the close:
    python -m alan_trader.engine.signal_alerts

Or import and call check_and_alert(...) from a Dash callback / button.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_STATE_PATH = Path(__file__).resolve().parent.parent / "runtime_state" / "signal_state.json"


def _monitored() -> dict:
    """{slug: (strategy, label)} for every strategy that publishes a live signal."""
    from alan_trader.strategy_api.base import BaseStrategy
    from alan_trader.strategy_api.registry import STRATEGY_METADATA, get_strategy
    out = {}
    for slug, meta in STRATEGY_METADATA.items():
        if meta.get("status") != "active":
            continue
        strat = get_strategy(slug)
        # Only strategies that override the hook — the base returns None.
        if type(strat).current_signal is BaseStrategy.current_signal:
            continue
        out[slug] = (strat, meta.get("ui_label") or meta.get("display_name") or slug)
    return out


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
    """{ 'slug|TICKER': signal_dict } for every monitored strategy × ticker."""
    from alan_trader.strategy_api.timing_base import load_close
    strats = _monitored()
    out = {}
    closes = {t: load_close(t) for t in tickers}
    for t in tickers:
        c = closes[t]
        for slug, (strat, label) in strats.items():
            try:
                sig = strat.current_signal(c)
            except Exception as exc:
                logger.warning(f"{slug}: current_signal failed for {t}: {exc}")
                continue
            if not sig:
                continue
            sig = dict(sig)
            sig["label"] = label
            sig["ticker"] = t
            out[f"{slug}|{t}"] = sig
    return out


def format_signal_line(sig: dict) -> str:
    base = f"{sig.get('label')} · {sig.get('ticker')}: {sig.get('signal')} ({sig.get('state','')})"
    detail = sig.get("detail")
    if detail:
        base += f"\n  {detail}"
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
