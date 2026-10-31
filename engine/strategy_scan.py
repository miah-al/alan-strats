"""
engine/strategy_scan.py — the screener scan pipeline, headless.

Resolves a universe, fetches VIX / OHLCV / IV metrics once, hands a ``ScanContext``
to the strategy's ``StrategyUI.scan`` hook and formats the rows through
``StrategyUI.display_row``. The Strategies page (``app/pages/strategies/scan.py``)
and the service API both run a scan through here; the page adds its own status
pills and banners on top.

Names no strategy: everything strategy-specific comes from the plugin's UI hooks.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable, Optional

import pandas as pd

logger = logging.getLogger(__name__)

#: progress(fraction 0..1, message) — may raise to abort the scan (the API's cancel).
Progress = Optional[Callable[[Optional[float], Optional[str]], None]]


# ── Universe options ──────────────────────────────────────────────────────────

UNIVERSE_TICKERS: dict[str, list[str]] = {
    "ETF Core":  ["SPY", "QQQ", "IWM", "GLD", "TLT", "EEM", "XLF", "XLE", "XLV", "XLK"],
    "Mega Cap":  ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "BRK-B", "JPM", "JNJ"],
    "High IV":   ["TSLA", "NVDA", "AMD", "META", "NFLX", "COIN", "MSTR", "PLTR", "SMCI", "ARM"],
}

DEFAULT_UNIVERSE = "ETF Core"


def _report(progress: Progress, fraction: Optional[float], message: Optional[str]) -> None:
    if progress is not None:
        progress(fraction, message)


# ── Data ──────────────────────────────────────────────────────────────────────

def get_vix_series(api_key: str | None = None):
    """Load VIX close series — DB first, Polygon fallback."""
    # Try DB first
    try:
        from db.client import get_engine, get_vix_bars
        engine = get_engine()
        vix_df = get_vix_bars(engine, date.today() - timedelta(days=400), date.today())
        if not vix_df.empty:
            return vix_df["close"].astype(float)
    except Exception:
        pass

    # Polygon fallback — fetch VIX as a ticker (^VIX / VIXW)
    if api_key:
        try:
            from engine.screener import _fetch_ohlcv
            for sym in ["I:VIX", "VIX"]:
                df = _fetch_ohlcv(sym, api_key, bars=400)
                if not df.empty and "close" in df.columns:
                    return df["close"].astype(float)
        except Exception:
            pass

    return None


def resolve_tickers(universe: str, custom: str | None) -> list[str]:
    # If user typed anything in the custom field, always use it (overrides dropdown)
    if custom and custom.strip():
        return [t.strip().upper() for t in custom.split(",") if t.strip()]
    return UNIVERSE_TICKERS.get(universe, [])


def fetch_scan_data(tickers: list[str], api_key: str, progress: Progress = None):
    """Returns (vix_series, price_dfs, iv_all). Raises on fatal error.

    ``progress`` (optional) is told about each step: VIX, then one OHLCV fetch per
    ticker (0.05 → 0.35), then one IV-metrics fetch per ticker (0.35 → 0.75)."""
    from engine.screener import _fetch_ohlcv
    from engine.iv_metrics import get_iv_metrics_batch

    _report(progress, 0.02, "loading VIX")
    vix_series = get_vix_series(api_key)
    if vix_series is None:
        raise RuntimeError("No VIX data available (DB offline and Polygon VIX fetch failed).")

    price_dfs: dict = {}
    n = max(len(tickers), 1)
    for i, ticker in enumerate(tickers):
        _report(progress, 0.05 + 0.30 * i / n, f"prices {ticker} ({i + 1}/{len(tickers)})")
        df = _fetch_ohlcv(ticker, api_key)
        if not df.empty:
            price_dfs[ticker] = df

    if not price_dfs:
        raise RuntimeError("No price data returned for any ticker. Check API key.")

    iv_errors: list[BaseException] = []

    def _iv_progress(ticker, i, total):
        try:
            _report(progress, 0.35 + 0.40 * i / max(total, 1), f"IV metrics {ticker} ({i + 1}/{total})")
        except BaseException as exc:   # get_iv_metrics_batch swallows Exceptions from on_progress
            iv_errors.append(exc)
            raise

    iv_all = get_iv_metrics_batch(
        tickers=list(price_dfs.keys()),
        api_key=api_key,
        price_dfs=price_dfs,
        on_progress=_iv_progress if progress is not None else None,
    )
    if iv_errors:
        raise iv_errors[0]
    return vix_series, price_dfs, iv_all


# ── The scan ──────────────────────────────────────────────────────────────────

@dataclass
class ScanOutcome:
    slug: str
    tickers: list[str]
    params: dict
    display_rows: list[dict]
    raw_rows: list[dict]
    vix_series: Optional[pd.Series]
    errors: list[str] = field(default_factory=list)

    @property
    def ivr_fallback_count(self) -> int:
        """Rows whose IVR came from the VIX proxy rather than real option quotes."""
        return sum(1 for r in self.raw_rows if str(r.get("ivr_confidence", "")).startswith("low"))


def scan_tickers(slug: str, universe: str, custom: str | None) -> list[str]:
    """The tickers a scan covers: a locked strategy's fixed list, else the custom
    list when given, else the named universe."""
    from alan_trader.strategy_api.registry import get_ui
    ui = get_ui(slug)
    if ui.locked_tickers:
        return list(ui.locked_tickers)
    return resolve_tickers(universe, custom)


def run_strategy_scan(slug: str, tickers: list[str], api_key: str,
                      param_overrides: dict | None = None, progress: Progress = None) -> ScanOutcome:
    """Fetch the data, run the strategy's scan hook, format and sort the rows
    (score descending). Raises on a fatal data error."""
    from alan_trader.strategy_api.registry import get_ui
    from alan_trader.strategy_api.ui import ScanContext

    ui = get_ui(slug)
    vix_series, price_dfs, iv_all = fetch_scan_data(tickers, api_key, progress=progress)
    params = {**(ui.default_params or {}), **(param_overrides or {})}

    ctx = ScanContext(slug=slug, tickers=tickers, price_dfs=price_dfs,
                      vix_series=vix_series, iv_all=iv_all, api_key=api_key,
                      params=params)
    _report(progress, 0.78, f"scoring {len(price_dfs)} tickers")
    raw_rows = list(ui.scan(ctx) or [])
    _report(progress, 0.95, "formatting rows")
    display_rows = [ui.display_row(r) for r in raw_rows]

    # Sort by score descending
    display_rows.sort(
        key=lambda r: (r.get("Score") or 0) if isinstance(r.get("Score"), (int, float)) else 0,
        reverse=True,
    )
    errors = [f"{t}: no price data" for t in tickers if t not in price_dfs]
    return ScanOutcome(slug=slug, tickers=list(tickers), params=params, display_rows=display_rows,
                       raw_rows=raw_rows, vix_series=vix_series, errors=errors)


def vix_summary(vix_series, slug: str) -> Optional[dict]:
    """The numbers behind the screener's VIX banner, plus the strategy's status line
    (``StrategyUI.vix_banner_status``) when it has one."""
    from engine.screener import _vix_ivr, _vix_20d_avg
    from alan_trader.strategy_api.registry import get_ui
    if vix_series is None or len(vix_series) == 0:
        return None
    current_vix = float(vix_series.iloc[-1])
    avg20 = _vix_20d_avg(vix_series)
    try:
        custom = get_ui(slug).vix_banner_status(current_vix, avg20)
    except Exception:
        custom = None
    banner = {"text": str(custom[0]), "tone": str(custom[1])} if custom else None
    try:
        asof = pd.Timestamp(vix_series.index[-1]).date().isoformat()
    except Exception:
        asof = None
    return {"last": current_vix, "avg20": float(avg20), "ivr": float(_vix_ivr(vix_series)),
            "points": int(len(vix_series)), "asof": asof, "banner": banner}
