"""
Standalone backtest runner for the Dash app.

Exposes a single public function:
    run_backtest(slug, ticker, from_date, to_date, params) -> dict
"""

import datetime
import logging
import warnings

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _trade_to_dict(trade) -> dict:
    """Convert a Trade dataclass (or similar) to a serializable dict."""
    d = vars(trade) if not isinstance(trade, dict) else dict(trade)
    out = {}
    for k, v in d.items():
        if isinstance(v, (datetime.date, datetime.datetime)):
            out[k] = str(v)
        elif isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
            out[k] = None
        else:
            out[k] = v
    return out


def _equity_curve_from_series(eq_series: pd.Series) -> list[dict]:
    """Convert a DatetimeIndex / date-indexed equity Series to list[dict]."""
    result = []
    for idx, val in eq_series.items():
        if isinstance(idx, (datetime.datetime, pd.Timestamp)):
            date_str = str(idx.date())
        elif isinstance(idx, datetime.date):
            date_str = str(idx)
        else:
            date_str = str(idx)
        result.append({"date": date_str, "equity": float(val)})
    return result


def _metrics_from_result(res) -> dict:
    """Extract the standard 7 metrics from a BacktestResult."""
    m = res.metrics if res.metrics else {}
    return {
        "total_return_pct":  float(m.get("total_return_pct",  0.0)),
        "sharpe_ratio":      float(m.get("sharpe_ratio",      0.0)),
        "max_drawdown_pct":  float(m.get("max_drawdown_pct",  0.0)),
        "win_rate_pct":      float(m.get("win_rate_pct",      0.0)),
        "profit_factor":     float(m.get("profit_factor",     0.0)) if m.get("profit_factor") not in (None, float("inf")) else 0.0,
        "num_trades":        int(m.get("num_trades",          0)),
        "final_equity":      float(m.get("final_equity",      0.0)),
    }


def _trades_from_result(res) -> list[dict]:
    """Extract trades list from a BacktestResult."""
    trades_raw = res.trades
    if isinstance(trades_raw, pd.DataFrame):
        if trades_raw.empty:
            return []
        records = trades_raw.to_dict(orient="records")
        return [_trade_to_dict(r) for r in records]
    if isinstance(trades_raw, list):
        return [_trade_to_dict(t) for t in trades_raw]
    return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_backtest(
    slug: str,
    ticker: str,
    from_date: datetime.date,
    to_date: datetime.date,
    params: dict,
) -> dict:
    """
    Run a backtest for *slug* and return a serializable result dict.

    Returns:
        {
            "ok": bool,
            "error": str,           # only when not ok
            "metrics": {...},
            "trades": [...],
            "equity_curve": [{"date": str, "equity": float}, ...],
            "extra": {...},
        }
    """
    warnings.filterwarnings("ignore")

    # Lazy imports so this module can be imported without the full package tree
    # being loaded at Dash startup.
    from alan_trader.strategies.registry import STRATEGY_METADATA, get_strategy

    # ── Convert date range → n_days (trading-day-equivalent) ─────────────────
    n_days = max(60, int((to_date - from_date).days * 252 / 365))

    # ── Load primary price data ────────────────────────────────────────────────
    try:
        from alan_trader.db.loader import load_training_data
        data = load_training_data(ticker=ticker)
    except Exception as exc:
        return {"ok": False, "error": f"Failed to load training data for {ticker}: {exc}"}

    price_data = data["spy"]   # primary ticker — named "spy" for legacy reasons
    vix    = data["vix"]
    r2     = data["rate2y"]
    r10    = data["rate10y"]
    macro  = data["macro"]
    news   = data["news"]

    aux = {
        "vix":     vix,
        "rate2y":  r2,
        "rate10y": r10,
        "macro":   macro,
        "news":    news,
    }

    # ── Dividends ──────────────────────────────────────────────────────────────
    if slug in ("dividend_arb", "conversion_arb"):
        try:
            from alan_trader.db.client import get_engine as _ge_div, get_dividends
            _div_from = datetime.date.today() - datetime.timedelta(days=n_days * 2)
            aux["dividends"] = get_dividends(_ge_div(), ticker, _div_from, datetime.date.today())
            aux["ticker"] = ticker
            logger.info(f"{slug}: loaded {len(aux['dividends'])} dividend rows for {ticker}")
        except Exception as exc:
            logger.warning(f"Could not load dividends for {ticker}: {exc}")
            aux["dividends"] = pd.DataFrame()

    # ── Earnings ───────────────────────────────────────────────────────────────
    if slug in ("earnings_iv_crush", "earnings_post_drift"):
        try:
            from alan_trader.db.client import get_engine as _ge_earn
            from sqlalchemy import text as _earn_text
            _eng_earn  = _ge_earn()
            _earn_from = datetime.date.today() - datetime.timedelta(days=n_days * 2)
            with _eng_earn.connect() as _ec:
                _earn_rows = _ec.execute(_earn_text("""
                    SELECT t.Symbol as ticker,
                           COALESCE(e.FiledDate, e.PeriodOfReport) as date,
                           e.EpsBasic    as eps_actual,
                           e.EpsEstimate as eps_estimate,
                           NULL          as implied_move_pct
                    FROM mkt.Earnings e
                    JOIN mkt.Ticker t ON t.TickerId = e.TickerId
                    WHERE COALESCE(e.FiledDate, e.PeriodOfReport) >= :from_date
                    ORDER BY COALESCE(e.FiledDate, e.PeriodOfReport)
                """), {"from_date": str(_earn_from)}).fetchall()
                _earn_total = _ec.execute(_earn_text(
                    "SELECT COUNT(*), MIN(COALESCE(FiledDate, PeriodOfReport)), "
                    "MAX(COALESCE(FiledDate, PeriodOfReport)) FROM mkt.Earnings"
                )).fetchone()
            _earn_df = pd.DataFrame(
                _earn_rows,
                columns=["ticker", "date", "eps_actual", "eps_estimate", "implied_move_pct"],
            )
            _earn_df["date"] = pd.to_datetime(_earn_df["date"])
            aux["earnings"] = _earn_df
            logger.info(
                f"{slug}: loaded {len(_earn_df)} earnings rows "
                f"(total in DB: {_earn_total[0]}, range: {_earn_total[1]} → {_earn_total[2]})"
            )

            # Per-ticker price bars for the earnings universe
            _earn_tickers   = _earn_df["ticker"].dropna().unique().tolist()
            _stock_prices: dict = {}
            from alan_trader.db.client import get_engine as _ge_sp, get_price_bars as _gpb_sp
            _eng_sp = _ge_sp()
            for _sp_tkr in _earn_tickers:
                try:
                    _sp_df = _gpb_sp(_eng_sp, _sp_tkr, _earn_from, datetime.date.today())
                    if _sp_df is not None and not _sp_df.empty:
                        _sp_df = _sp_df.set_index(pd.to_datetime(_sp_df["date"])).drop(columns=["date"])
                        _stock_prices[_sp_tkr] = _sp_df
                except Exception as _sp_exc:
                    logger.debug(f"Could not load price bars for {_sp_tkr}: {_sp_exc}")
            aux["stock_prices"] = _stock_prices
            logger.info(f"{slug}: loaded price bars for {list(_stock_prices.keys())}")

            if _earn_df.empty:
                try:
                    _diag_msg = (
                        f"DB has {_earn_total[0]} total rows, "
                        f"date range {_earn_total[1]} → {_earn_total[2]}. "
                        f"Backtest window starts {_earn_from}."
                    )
                except Exception:
                    _diag_msg = "Could not read mkt.Earnings count."
                return {
                    "ok": False,
                    "error": (
                        f"mkt.Earnings table returned 0 rows for the selected date range.\n"
                        f"{_diag_msg}\n"
                        "Go to Data Manager → Sync Earnings to populate it."
                    ),
                }
        except Exception as exc:
            logger.warning(f"Could not load earnings data: {exc}")
            aux["earnings"] = pd.DataFrame()

        _earn_check = aux.get("earnings", pd.DataFrame())
        if _earn_check.empty:
            try:
                from alan_trader.db.client import get_engine as _ge_diag
                from sqlalchemy import text as _dt
                _earn_from = datetime.date.today() - datetime.timedelta(days=n_days * 2)
                with _ge_diag().connect() as _dc:
                    _diag = _dc.execute(_dt(
                        "SELECT COUNT(*), MIN(COALESCE(FiledDate,PeriodOfReport)), "
                        "MAX(COALESCE(FiledDate,PeriodOfReport)) FROM mkt.Earnings"
                    )).fetchone()
                _diag_msg = (
                    f"DB has {_diag[0]} total rows, "
                    f"date range {_diag[1]} → {_diag[2]}. "
                    f"Backtest window starts {_earn_from}."
                )
            except Exception as _de:
                _earn_from = datetime.date.today() - datetime.timedelta(days=n_days * 2)
                _diag_msg = f"Could not query mkt.Earnings: {_de}"
            return {
                "ok": False,
                "error": (
                    f"No earnings data found for the backtest window (from {_earn_from}).\n\n"
                    f"{_diag_msg}\n\n"
                    "Sync earnings via Data Manager → Sync → Earnings for tickers like AAPL, MSFT, NVDA."
                ),
            }

    # ── TLT price data ─────────────────────────────────────────────────────────
    meta_for_slug = STRATEGY_METADATA.get(slug, {})
    if "tlt" in meta_for_slug.get("required_data", []):
        try:
            from alan_trader.db.client import get_engine, get_price_bars
            _engine   = get_engine()
            _tlt_from = datetime.date.today() - datetime.timedelta(days=n_days * 2)
            _tlt_df   = get_price_bars(_engine, "TLT", _tlt_from, datetime.date.today())
            if not _tlt_df.empty:
                _tlt_df["date"] = pd.to_datetime(_tlt_df["date"]).dt.date
                _tlt_df = _tlt_df.set_index("date")
            aux["tlt"] = _tlt_df
        except Exception as exc:
            logger.warning(f"Could not load TLT data: {exc}")
            aux["tlt"] = pd.DataFrame()

    # ── Vol Arbitrage: option chains from mkt.OptionSnapshot ─────────────────
    if slug == "vol_arbitrage":
        try:
            from alan_trader.db.options_loader import _load_chain
            from alan_trader.db.client import get_engine as _ge_va, get_ticker_id as _gtid_va
            _eng_va   = _ge_va()
            _opt_from = datetime.date.today() - datetime.timedelta(days=730)
            _opt_to   = datetime.date.today()
            _tid_va   = _gtid_va(_eng_va, ticker) if ticker else None
            if _tid_va:
                _raw = _load_chain(_eng_va, _tid_va, _opt_from, _opt_to, min_dte=7, max_dte=60)
                if not _raw.empty:
                    _raw["dte"] = (_raw["expiration_date"] - _raw["snapshot_date"]).apply(
                        lambda td: td.days if hasattr(td, "days") else int(td)
                    )
                    _raw = _raw.rename(columns={"contract_type": "type"})
                    _raw["type"] = _raw["type"].str.lower().map(
                        {"c": "call", "call": "call", "p": "put", "put": "put"}
                    )

                    from alan_trader.db.client import get_price_bars as _gpb_va
                    from alan_trader.db.sync import bs_price_chain as _bspc
                    _spots_df = _gpb_va(_eng_va, ticker, _opt_from, _opt_to)
                    _spot_map: dict = {}
                    if not _spots_df.empty:
                        for _, _sr in _spots_df.iterrows():
                            _sd = _sr["date"].date() if hasattr(_sr["date"], "date") else _sr["date"]
                            _spot_map[_sd] = float(_sr["close"])

                    _chains_va: dict = {}
                    for snap_date, grp in _raw.groupby("snapshot_date"):
                        import datetime as _dt_mod
                        _key = (
                            snap_date
                            if isinstance(snap_date, _dt_mod.date)
                            else pd.Timestamp(snap_date).date()
                        )
                        _chain = grp[["strike", "type", "bid", "ask", "iv", "delta", "dte"]].reset_index(drop=True)
                        _S = _spot_map.get(_key)
                        if _S:
                            _chain = _bspc(_chain, _S)
                        _chains_va[_key] = _chain

                    aux["options_chains"] = _chains_va

                    try:
                        from alan_trader.strategies.vol_arbitrage import VolArbitrageStrategy as _VAS
                        _va_tmp = _VAS(iv_skew_threshold=0.05)
                        aux["candidate_assessment"] = _va_tmp.assess_candidate(
                            _chains_va, price_data, dte_min=7, dte_max=60,
                        )
                    except Exception as _e_ca:
                        logger.debug(f"Candidate assessment failed: {_e_ca}")

                    # Detect BS-reconstructed vs real bid/ask
                    _bid_filled = _raw["bid"].notna() & (_raw["bid"] > 0)
                    if _bid_filled.any():
                        _bid_std   = _raw.groupby(["strike", "type"])["bid"].std().dropna()
                        _pct_static = (_bid_std < 0.001).sum() / max(len(_bid_std), 1)
                        _is_bs = _pct_static > 0.80
                    else:
                        _is_bs = True
                    aux["option_data_quality"] = "bs_reconstructed" if _is_bs else "real_quotes"
                    logger.info(
                        f"vol_arbitrage: loaded {len(_chains_va)} chain snapshots for {ticker} "
                        f"[{'BS-reconstructed' if _is_bs else 'real bid/ask'}]"
                    )
                else:
                    logger.info(f"vol_arbitrage: no saved option chain for {ticker}")
        except Exception as exc:
            logger.warning(f"vol_arbitrage: could not load option chain from DB: {exc}")

    # ── Rates / SPY rotation options: option chains for SPY + TLT ────────────
    if slug == "rates_spy_rotation_options":
        try:
            from alan_trader.db.options_loader import _load_chain
            from alan_trader.db.client import get_engine as _ge_o, get_ticker_id as _gtid_o
            _eng_o   = _ge_o()
            _opt_from = datetime.date.today() - datetime.timedelta(days=n_days * 2)
            _opt_to   = datetime.date.today()
            _spy_tid  = _gtid_o(_eng_o, "SPY")
            _tlt_tid  = _gtid_o(_eng_o, "TLT")
            aux["spy_options"] = (
                _load_chain(_eng_o, _spy_tid, _opt_from, _opt_to, min_dte=15, max_dte=120)
                if _spy_tid else pd.DataFrame()
            )
            aux["tlt_options"] = (
                _load_chain(_eng_o, _tlt_tid, _opt_from, _opt_to, min_dte=15, max_dte=120)
                if _tlt_tid else pd.DataFrame()
            )
        except Exception as exc:
            logger.warning(f"Could not load options chain data: {exc}")
            aux["spy_options"] = pd.DataFrame()
            aux["tlt_options"] = pd.DataFrame()

    # ── Vol Calendar Spread: chains + VIX + SPY from DB ──────────────────────
    if slug == "vol_calendar_spread":
        try:
            from alan_trader.db.client import (
                get_engine as _ge_vc, get_ticker_id as _gtid_vc,
                get_price_bars as _gpb_vc, get_vix_bars as _gvix_vc,
                get_news as _gnews_vc, get_option_snapshots as _gopt_vc,
            )
            from sqlalchemy import text as _vc_text
            _eng_vc  = _ge_vc()
            _vc_from = datetime.date.today() - datetime.timedelta(days=max(n_days * 2, 600))
            _vc_to   = datetime.date.today()
            _tid_vc  = _gtid_vc(_eng_vc, ticker)

            _px_vc = _gpb_vc(_eng_vc, ticker, _vc_from, _vc_to)
            if _px_vc is not None and not _px_vc.empty:
                _px_vc = _px_vc.set_index(pd.to_datetime(_px_vc["date"])).drop(columns=["date"])
            aux["price_data"] = _px_vc

            try:
                _spy_vc = _gpb_vc(_eng_vc, "SPY", _vc_from, _vc_to)
                if _spy_vc is not None and not _spy_vc.empty:
                    _spy_vc = _spy_vc.set_index(pd.to_datetime(_spy_vc["date"])).drop(columns=["date"])
                aux["spy_data"] = _spy_vc
            except Exception:
                aux["spy_data"] = None

            _vix_vc = _gvix_vc(_eng_vc, _vc_from, _vc_to)
            if not _vix_vc.empty:
                _vix_vc.index = pd.to_datetime(_vix_vc.index)
                _vcol = "close" if "close" in _vix_vc.columns else _vix_vc.columns[0]
                aux["vix_data"] = _vix_vc[_vcol]
            else:
                aux["vix_data"] = None

            try:
                _news_vc = _gnews_vc(_eng_vc, ticker, _vc_from, _vc_to)
                if _news_vc is not None and not _news_vc.empty and "date" in _news_vc.columns:
                    _news_vc = _news_vc.set_index(pd.to_datetime(_news_vc["date"])).drop(columns=["date"])
                aux["news_data"] = _news_vc
            except Exception:
                aux["news_data"] = None

            if _tid_vc:
                with _eng_vc.connect() as _c:
                    _snap_dates_vc = [
                        r[0] for r in _c.execute(_vc_text(
                            "SELECT DISTINCT SnapshotDate FROM mkt.OptionSnapshot "
                            "WHERE TickerId=:tid AND SnapshotDate BETWEEN :f AND :t "
                            "ORDER BY SnapshotDate"
                        ), {"tid": _tid_vc, "f": _vc_from, "t": _vc_to}).fetchall()
                    ]
                _chains_vc: dict = {}
                for _sd in _snap_dates_vc:
                    _ch = _gopt_vc(_eng_vc, ticker, _sd)
                    if _ch is not None and not _ch.empty:
                        _key = _sd if isinstance(_sd, datetime.date) else pd.Timestamp(_sd).date()
                        _chains_vc[_key] = _ch
                aux["chains"] = _chains_vc
                logger.info(f"vol_calendar_spread: loaded {len(_chains_vc)} chain snapshots for {ticker}")
            else:
                aux["chains"] = {}
        except Exception as exc:
            logger.warning(f"vol_calendar_spread: data load failed: {exc}")
            aux.setdefault("chains", {})

    # ── AI Options strategies: raw OptionSnapshot rows ────────────────────────
    _AI_OPT_SLUGS = {
        "oi_imbalance_put_fade",
        "short_squeeze_vol_expansion",
        "iv_skew_momentum",
        "gamma_flip_breakout",
        "vol_term_structure_regime",
    }
    if slug in _AI_OPT_SLUGS:
        _tid_ai = None
        try:
            from alan_trader.db.client import (
                get_engine as _ge_ai, get_ticker_id as _gtid_ai,
                get_price_bars as _gpb_ai,
            )
            from sqlalchemy import text as _ai_text
            _eng_ai  = _ge_ai()
            _ai_from = datetime.date.today() - datetime.timedelta(days=max(n_days * 2, 730))
            _ai_to   = datetime.date.today()
            _tid_ai  = _gtid_ai(_eng_ai, ticker) if ticker else None

            if _tid_ai:
                with _eng_ai.connect() as _c_ai:
                    _snap_rows = _c_ai.execute(_ai_text("""
                        SELECT
                            s.SnapshotDate,
                            s.Strike         AS StrikePrice,
                            s.ContractType   AS OptionType,
                            s.ImpliedVol,
                            s.OpenInterest,
                            s.Delta,
                            s.Gamma,
                            s.Bid,
                            s.Ask,
                            DATEDIFF(day, s.SnapshotDate, s.ExpirationDate) AS DTE,
                            s.ExpirationDate
                        FROM mkt.OptionSnapshot s
                        WHERE s.TickerId = :tid
                          AND s.SnapshotDate BETWEEN :f AND :t
                        ORDER BY s.SnapshotDate, s.ExpirationDate, s.Strike
                    """), {"tid": _tid_ai, "f": _ai_from, "t": _ai_to}).fetchall()
                _snap_cols = [
                    "SnapshotDate", "StrikePrice", "OptionType", "ImpliedVol",
                    "OpenInterest", "Delta", "Gamma", "Bid", "Ask", "DTE", "ExpirationDate",
                ]
                _snap_df = pd.DataFrame(_snap_rows, columns=_snap_cols)
                aux["option_snapshots"] = _snap_df
                logger.info(f"{slug}: loaded {len(_snap_df)} option snapshot rows for {ticker}")
            else:
                aux["option_snapshots"] = pd.DataFrame()
                logger.warning(f"{slug}: ticker {ticker!r} not found in DB — option_snapshots empty")

            try:
                _spy_ai = _gpb_ai(_eng_ai, "SPY", _ai_from, _ai_to)
                if _spy_ai is not None and not _spy_ai.empty:
                    _spy_ai = _spy_ai.set_index(pd.to_datetime(_spy_ai["date"])).drop(columns=["date"])
                aux["spy_price"] = _spy_ai
            except Exception as exc_spy:
                logger.debug(f"{slug}: could not load benchmark price: {exc_spy}")
                aux["spy_price"] = None

        except Exception as exc:
            logger.warning(f"{slug}: option_snapshots load failed: {exc}")
            aux.setdefault("option_snapshots", pd.DataFrame())

        _snaps = aux.get("option_snapshots")
        if _snaps is None or (isinstance(_snaps, pd.DataFrame) and _snaps.empty):
            if not _tid_ai:
                _reason = f"Ticker {ticker!r} not found in DB — sync it first."
            else:
                _ai_from_days = max(n_days * 2, 730)
                _reason = f"No option snapshot rows found for {ticker!r} in the last {_ai_from_days} days."
            return {
                "ok": False,
                "error": (
                    f"{slug} requires options data that is not yet in the database.\n\n"
                    f"{_reason}\n\n"
                    "Go to Data → Sync from Polygon → Options Chain, enter the ticker, "
                    "and run the sync. Then retry the backtest."
                ),
            }

    # ── Resolve + validate strategy ───────────────────────────────────────────
    try:
        strat = get_strategy(slug)
    except Exception as exc:
        return {"ok": False, "error": f"Unknown strategy slug {slug!r}: {exc}"}

    if not strat.is_ready():
        return {"ok": False, "error": f"Strategy {slug!r} is not ready (model not trained?)."}

    # ── Run the backtest ───────────────────────────────────────────────────────
    try:
        extra_params: dict = {}

        # Vol arbitrage always skips parity arb when using DB data
        if slug == "vol_arbitrage":
            extra_params["skip_parity_arb"] = True

        # Vol calendar spread uses a specialised call signature
        if slug == "vol_calendar_spread":
            strat.load_model(ticker)
            res = strat.backtest(
                price_data=aux.get("price_data", price_data),
                ticker=ticker,
                chains=aux.get("chains", {}),
                vix_data=aux.get("vix_data"),
                news_data=aux.get("news_data"),
                spy_data=aux.get("spy_data"),
                **params,
            )
        else:
            res = strat.backtest(
                price_data,
                aux,
                starting_capital=100_000,
                **params,
                **extra_params,
            )

    except Exception as exc:
        logger.exception(f"Backtest failed for {slug}: {exc}")
        return {"ok": False, "error": str(exc)}

    # ── Serialise result ──────────────────────────────────────────────────────
    try:
        metrics    = _metrics_from_result(res)
        trades     = _trades_from_result(res)
        eq_series  = res.equity_curve
        if isinstance(eq_series, pd.DataFrame):
            # Some strategies return a DataFrame — take the first numeric column
            if "equity" in eq_series.columns:
                eq_series = eq_series["equity"]
            else:
                eq_series = eq_series.iloc[:, 0]
        equity_curve = _equity_curve_from_series(eq_series)
        extra        = res.extra if res.extra else {}
    except Exception as exc:
        logger.exception(f"Failed to serialise BacktestResult for {slug}: {exc}")
        return {"ok": False, "error": f"Backtest ran but result serialisation failed: {exc}"}

    return {
        "ok":           True,
        "metrics":      metrics,
        "trades":       trades,
        "equity_curve": equity_curve,
        "extra":        extra,
    }
