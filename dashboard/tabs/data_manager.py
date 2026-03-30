"""
Data Manager tab — SQL Server coverage status, Polygon sync controls,
and training data validation.
"""

import streamlit as st
import pandas as pd
from datetime import date, timedelta


def render(api_key: str = ""):
    st.markdown("## Data Manager")

    from alan_trader.db.client import get_engine

    # ── Top controls ───────────────────────────────────────────────────────────
    col1, col2, col3 = st.columns([2, 2, 1])
    ticker = col1.text_input(
        "Ticker", value="", key="dm_ticker",
        placeholder="SPY, TLT, AAPL, HOOD…",
    ).strip().upper()
    from_date = col2.date_input(
        "Backfill from", value=date.today() - timedelta(days=730), key="dm_from_date"
    )
    force_full = col3.checkbox(
        "Force full", key="dm_force_full",
        help="Delete all existing rows for this ticker and re-sync from scratch.",
    )

    if not api_key:
        st.warning("Enter your Polygon API key in the sidebar to enable Polygon sync buttons.")

    # ── Sync All ───────────────────────────────────────────────────────────────
    sync_all_col, opts_col = st.columns([3, 2])
    include_options = opts_col.checkbox(
        "Include Options (slow)", key="dm_sync_all_opts",
        help="Options backfill can take hours — uncheck to skip and run separately",
    )
    if sync_all_col.button("⚡ Sync All", key="dm_sync_all", disabled=not api_key or not ticker,
                           type="primary",
                           help="Run all syncs in sequence for the selected ticker"):
        _all = {"price", "news", "divs", "earnings", "treasury", "vix", "macro", "cpi", "fomc"}
        if include_options:
            _all.add("options")
        st.session_state["_dm_run"] = _all

    st.markdown("---")

    # ── Pre-load coverage for inline captions ──────────────────────────────────
    def _cov_label(mn, mx, cnt) -> str:
        if not cnt:
            return "no data"
        return f"{int(cnt):,} rows · {mn} → {mx}"

    _cv = {}
    try:
        engine = get_engine()
        with engine.connect() as _conn:
            from sqlalchemy import text as _t
            from alan_trader.db.client import get_ticker_id as _gtid
            _tid = _gtid(engine, ticker) if ticker else None

            if _tid:
                r = _conn.execute(_t("SELECT MIN(BarDate),MAX(BarDate),COUNT(*) FROM mkt.PriceBar WHERE TickerId=:tid"), {"tid": _tid}).fetchone()
                _cv["price"] = _cov_label(r[0], r[1], r[2])
                r = _conn.execute(_t("SELECT MIN(PublishedDate),MAX(PublishedDate),COUNT(*) FROM mkt.News WHERE TickerId=:tid"), {"tid": _tid}).fetchone()
                _cv["news"] = _cov_label(r[0], r[1], r[2])
                r = _conn.execute(_t("SELECT MIN(SnapshotDate),MAX(SnapshotDate),COUNT(DISTINCT SnapshotDate) FROM mkt.OptionSnapshot WHERE TickerId=:tid"), {"tid": _tid}).fetchone()
                _cv["options"] = _cov_label(r[0], r[1], r[2])
                r = _conn.execute(_t("SELECT MIN(ExDate),MAX(ExDate),COUNT(*) FROM mkt.Dividend WHERE TickerId=:tid"), {"tid": _tid}).fetchone()
                _cv["divs"] = _cov_label(r[0], r[1], r[2])
                r = _conn.execute(_t("SELECT MIN(PeriodOfReport),MAX(PeriodOfReport),COUNT(*) FROM mkt.Earnings WHERE TickerId=:tid"), {"tid": _tid}).fetchone()
                _cv["earnings"] = _cov_label(r[0], r[1], r[2])

            for key, sql in [
                ("treasury", "SELECT MIN(BarDate),MAX(BarDate),COUNT(*) FROM mkt.TreasuryBar"),
                ("vix",      "SELECT MIN(BarDate),MAX(BarDate),COUNT(*) FROM mkt.VixBar"),
                ("macro",    "SELECT MIN(BarDate),MAX(BarDate),COUNT(*) FROM mkt.MacroBar"),
                ("cpi",      "SELECT MIN(BarDate),MAX(BarDate),COUNT(*) FROM mkt.CpiBar"),
                ("vxfut",    "SELECT MIN(TradeDate),MAX(TradeDate),COUNT(*) FROM mkt.VixFuture"),
                ("fomc",     "SELECT MIN(MeetingDate),MAX(MeetingDate),COUNT(*) FROM mkt.FomcCalendar"),
            ]:
                try:
                    r = _conn.execute(_t(sql)).fetchone()
                    _cv[key] = _cov_label(r[0], r[1], r[2])
                except Exception:
                    _cv[key] = "table missing"
    except Exception:
        pass

    # ── Sync buttons — clicking just queues the sync ───────────────────────────
    # Result placeholders are defined right after each button so that
    # the execution section at the bottom can write progress/results there.
    col_poly, col_free = st.columns(2)

    with col_poly:
        st.markdown("**Polygon** *(API key required)*")

        # Price Bars
        if st.button(f"Sync Price Bars — {ticker or '…'}", key="dm_sync_price",
                     disabled=not api_key or not ticker):
            st.session_state["_dm_run"] = {"price"}
        price_result = st.empty()
        st.caption(f"DB: {_cv.get('price', '—')}")

        # News
        if st.button(f"Sync News — {ticker or '…'}", key="dm_sync_news",
                     disabled=not api_key or not ticker):
            st.session_state["_dm_run"] = {"news"}
        news_result = st.empty()
        st.caption(f"DB: {_cv.get('news', '—')}")

        # Options — progress bar lives above the button so it appears in place
        opts_prog_text = st.empty()
        opts_prog_bar  = st.empty()
        if st.button(f"Sync Options — {ticker or '…'}", key="dm_sync_options",
                     disabled=not api_key or not ticker,
                     help="Fetches real historical IV from per-contract daily OHLC. "
                          "Takes 5-20 min depending on date range."):
            st.session_state["_dm_run"] = {"options"}
        options_result = st.empty()
        st.caption(f"DB: {_cv.get('options', '—')}  ·  real historical IV via per-contract OHLC")

        # Dividends
        if st.button(f"Sync Dividends — {ticker or '…'}", key="dm_sync_divs",
                     disabled=not api_key or not ticker):
            st.session_state["_dm_run"] = {"divs"}
        divs_result = st.empty()
        st.caption(f"DB: {_cv.get('divs', '—')}")

        # Earnings
        if st.button(f"Sync Earnings — {ticker or '…'}", key="dm_sync_earnings",
                     disabled=not api_key or not ticker):
            st.session_state["_dm_run"] = {"earnings"}
        earnings_result = st.empty()
        st.caption(f"DB: {_cv.get('earnings', '—')}")

    with col_free:
        st.markdown("**Free Sources** *(no API key needed)*")

        # Alpha Vantage EPS Estimates
        av_key = st.text_input(
            "Alpha Vantage API key",
            type="password",
            key="dm_av_key",
            placeholder="Get free key at alphavantage.co",
            help="Free tier: 25 req/day. Provides consensus EPS estimates needed by Earnings Post-Drift strategy.",
        )
        if st.button(f"Sync EPS Estimates — {ticker or '…'} (Alpha Vantage)",
                     key="dm_sync_eps_est",
                     disabled=not av_key or not ticker,
                     help="Fetches analyst consensus EPS estimates and writes them into mkt.Earnings.EpsEstimate"):
            st.session_state["_dm_run"] = {"eps_estimates"}
        eps_est_result = st.empty()
        try:
            _eng_eps = get_engine()
            with _eng_eps.connect() as _c_eps:
                from sqlalchemy import text as _t_eps
                from alan_trader.db.client import get_ticker_id as _gtid_eps
                _tid_eps = _gtid_eps(_eng_eps, ticker) if ticker else None
                if _tid_eps:
                    try:
                        _r_eps = _c_eps.execute(_t_eps(
                            "SELECT COUNT(*) FROM mkt.Earnings WHERE TickerId=:tid AND EpsEstimate IS NOT NULL"
                        ), {"tid": _tid_eps}).fetchone()
                        st.caption(f"DB: {int(_r_eps[0]):,} rows with EpsEstimate")
                    except Exception:
                        st.caption("DB: EpsEstimate column not yet created (run sync first)")
                else:
                    st.caption("DB: —")
        except Exception:
            st.caption("DB: —")

        st.markdown("---")

        # Treasury
        if st.button("Sync Treasury Yields — FRED", key="dm_sync_treasury"):
            st.session_state["_dm_run"] = {"treasury"}
        treasury_result = st.empty()
        st.caption(f"DB: {_cv.get('treasury', '—')}")

        # VIX Bars
        if st.button("Sync VIX Bars — CBOE", key="dm_sync_vix"):
            st.session_state["_dm_run"] = {"vix"}
        vix_result = st.empty()
        st.caption(f"DB: {_cv.get('vix', '—')}")

        # Macro
        if st.button("Sync Macro — FRED", key="dm_sync_macro"):
            st.session_state["_dm_run"] = {"macro"}
        macro_result = st.empty()
        st.caption(f"DB: {_cv.get('macro', '—')}")

        # CPI
        if st.button("Sync CPI — FRED", key="dm_sync_cpi"):
            st.session_state["_dm_run"] = {"cpi"}
        cpi_result = st.empty()
        st.caption(f"DB: {_cv.get('cpi', '—')}")

        # FOMC Calendar
        if st.button("Sync FOMC Calendar", key="dm_sync_fomc"):
            st.session_state["_dm_run"] = {"fomc"}
        fomc_result = st.empty()
        st.caption(f"DB: {_cv.get('fomc', '—')}")

    # ══ EXECUTION ═════════════════════════════════════════════════════════════
    # All placeholders above are now in the DOM. Run whatever was queued.
    _run = st.session_state.pop("_dm_run", set())
    if _run:
        import time as _time
        from alan_trader.db.sync import (
            sync_price_bars, sync_news, sync_dividends, sync_earnings,
            sync_option_snapshots, sync_treasury_bars, sync_vix_bars,
            sync_macro_bars, sync_cpi, sync_fomc_calendar,
            sync_eps_estimates,
        )

        def _exec(label, fn, result_el, *args, **kwargs):
            result_el.info(f"Syncing {label}…")
            try:
                r = fn(*args, **kwargs, progress_cb=lambda msg: result_el.info(msg))
                s = r.get("status", "ok")
                rows = r.get("rows", 0)
                if s == "up_to_date":
                    result_el.success(f"{label} — already up to date")
                elif s in ("no_data", "no_calendar"):
                    detail = r.get("detail", "")
                    result_el.warning(f"{label} — no data returned" + (f": {detail}" if detail else ""))
                else:
                    result_el.success(f"{label} — {rows:,} rows inserted")
            except Exception as e:
                result_el.error(f"{label} failed: {e}")

        if "price" in _run:
            if force_full:
                from alan_trader.db.client import get_ticker_id
                from sqlalchemy import text as _t2
                _eng = get_engine()
                _tid2 = get_ticker_id(_eng, ticker)
                if _tid2:
                    with _eng.begin() as c:
                        c.execute(_t2("DELETE FROM mkt.PriceBar WHERE TickerId=:tid"), {"tid": _tid2})
                        c.execute(_t2("DELETE FROM mkt.SyncLog WHERE DataType='PriceBar' AND TickerId=:tid"), {"tid": _tid2})
            _exec("Price Bars", sync_price_bars, price_result, ticker, api_key, from_date=from_date)

        if "news" in _run:
            _exec("News", sync_news, news_result, ticker, api_key, from_date=from_date)

        if "options" in _run:
            opts_prog_text.empty()
            opts_prog_bar.empty()
            if force_full:
                from alan_trader.db.client import get_ticker_id
                from sqlalchemy import text as _t2
                _eng = get_engine()
                _tid2 = get_ticker_id(_eng, ticker)
                if _tid2:
                    with _eng.begin() as c:
                        c.execute(_t2("DELETE FROM mkt.OptionSnapshot WHERE TickerId=:tid"), {"tid": _tid2})
                        c.execute(_t2("DELETE FROM mkt.SyncLog WHERE DataType='OptionSnapshot' AND TickerId=:tid"), {"tid": _tid2})
                    options_result.info("Cleared existing option snapshots — re-fetching from scratch…")
            _start = _time.time()
            def _opts_cb(msg, current, total, rows_so_far=0):
                elapsed = _time.time() - _start
                if current > 0:
                    eta_s = int(elapsed / current * (total - current))
                    eta_str = f"  •  ETA {eta_s//60}m {eta_s%60:02d}s"
                    est = int(rows_so_far / current * total) if rows_so_far > 0 else 0
                    est_str = f"  •  est. {est:,} rows" if est else ""
                else:
                    eta_str = est_str = ""
                elapsed_str = f"{int(elapsed)//60}m {int(elapsed)%60:02d}s"
                opts_prog_text.info(f"{msg}  •  {rows_so_far:,} rows{est_str}  •  {elapsed_str} elapsed{eta_str}")
                if total > 0:
                    opts_prog_bar.progress(current / total)
            try:
                result = sync_option_snapshots(ticker, api_key, from_date=from_date, progress_cb=_opts_cb)
                opts_prog_text.empty()
                opts_prog_bar.empty()
                s = result.get("status", "ok")
                if s == "up_to_date":
                    options_result.success(f"Options — already up to date")
                elif s == "no_calendar":
                    options_result.error(result.get("message", "No calendar"))
                else:
                    rows = result.get("rows", 0)
                    contracts = result.get("contracts", 0)
                    options_result.success(f"Options — {rows:,} rows · {contracts} contracts processed")
                    if result.get("errors"):
                        with st.expander(f"{len(result['errors'])} errors"):
                            for e in result["errors"]:
                                st.caption(e)
            except Exception as e:
                opts_prog_text.empty()
                opts_prog_bar.empty()
                options_result.error(f"Options failed: {e}")

        if "divs" in _run:
            _exec("Dividends", sync_dividends, divs_result, ticker, api_key, from_date=from_date)

        if "earnings" in _run:
            _exec("Earnings", sync_earnings, earnings_result, ticker, api_key, from_date=from_date)

        if "treasury" in _run:
            _exec("Treasury Yields", sync_treasury_bars, treasury_result, from_date=from_date)

        if "vix" in _run:
            _exec("VIX Bars", sync_vix_bars, vix_result, from_date=from_date)

        if "macro" in _run:
            _exec("Macro", sync_macro_bars, macro_result, from_date=from_date)

        if "cpi" in _run:
            _exec("CPI", sync_cpi, cpi_result, from_date=from_date)

        if "fomc" in _run:
            _exec("FOMC Calendar", sync_fomc_calendar, fomc_result)

        if "eps_estimates" in _run:
            av_key_run = st.session_state.get("dm_av_key", "")
            if av_key_run:
                eps_est_result.info(f"Syncing EPS estimates for {ticker}…")
                try:
                    r = sync_eps_estimates(ticker, av_key_run,
                                           progress_cb=lambda msg: eps_est_result.info(msg))
                    eps_est_result.success(
                        f"EPS Estimates — {r.get('updated', 0)} rows updated, "
                        f"{r.get('inserted', 0)} new rows inserted"
                    )
                except Exception as e:
                    eps_est_result.error(f"EPS Estimates failed: {e}")
            else:
                eps_est_result.error("Alpha Vantage API key required.")

        st.rerun()

    st.markdown("---")

    # ── Coverage ────────────────────────────────────────────────────────────────
    st.subheader("Coverage")

    SYMBOLS = ["HOOD", "SPY", "QQQ", "AAPL", "TSLA", "MARA", "TLT"]

    try:
        engine = get_engine()
        with engine.connect() as conn:
            from sqlalchemy import text as _t

            price_rows = conn.execute(_t("""
                SELECT t.Symbol,
                       COUNT(*)         AS PriceBars,
                       MIN(pb.BarDate)  AS [From],
                       MAX(pb.BarDate)  AS [To]
                FROM   mkt.PriceBar pb
                JOIN   mkt.Ticker t ON t.TickerId = pb.TickerId
                WHERE  t.Symbol IN ('HOOD','SPY','QQQ','AAPL','TSLA','MARA','TLT')
                GROUP BY t.Symbol
            """)).fetchall()

            opt_rows = conn.execute(_t("""
                SELECT t.Symbol,
                       COUNT(DISTINCT o.SnapshotDate) AS OptDates,
                       MIN(o.SnapshotDate)            AS [From],
                       MAX(o.SnapshotDate)            AS [To]
                FROM   mkt.OptionSnapshot o
                JOIN   mkt.Ticker t ON t.TickerId = o.TickerId
                WHERE  t.Symbol IN ('HOOD','SPY','QQQ','AAPL','TSLA','MARA','TLT')
                GROUP BY t.Symbol
            """)).fetchall()

            vix_row   = conn.execute(_t("SELECT MIN(BarDate), MAX(BarDate), COUNT(*) FROM mkt.VixBar")).fetchone()
            macro_row = conn.execute(_t("SELECT MIN(BarDate), MAX(BarDate), COUNT(*) FROM mkt.MacroBar")).fetchone()

            try:
                cpi_row = conn.execute(_t("SELECT MIN(BarDate), MAX(BarDate), COUNT(*) FROM mkt.CpiBar")).fetchone()
            except Exception:
                cpi_row = None
            try:
                fomc_row = conn.execute(_t("SELECT MIN(MeetingDate), MAX(MeetingDate), COUNT(*) FROM mkt.FomcCalendar")).fetchone()
            except Exception:
                fomc_row = None
            try:
                vxf_row = conn.execute(_t("SELECT MIN(TradeDate), MAX(TradeDate), COUNT(*) FROM mkt.VixFuture")).fetchone()
            except Exception:
                vxf_row = None
            try:
                tsy_row = conn.execute(_t("SELECT MIN(BarDate), MAX(BarDate), COUNT(*) FROM mkt.TreasuryBar")).fetchone()
            except Exception:
                tsy_row = None

        price_map = {r[0]: r for r in price_rows}
        opt_map   = {r[0]: r for r in opt_rows}
        ticker_rows = []
        for sym in SYMBOLS:
            p = price_map.get(sym)
            o = opt_map.get(sym)
            ticker_rows.append({
                "Ticker":      sym,
                "Price Bars":  f"{int(p[1]):,}" if p else "—",
                "Price From":  str(p[2]) if p else "—",
                "Price To":    str(p[3]) if p else "—",
                "Opt Days":    f"{int(o[1]):,}" if o else "—",
                "Opt From":    str(o[2]) if o else "—",
                "Opt To":      str(o[3]) if o else "—",
            })
        st.dataframe(pd.DataFrame(ticker_rows), hide_index=True, width="stretch")

        def _cov(row, label):
            if row and row[2]:
                return {"Dataset": label, "From": str(row[0]), "To": str(row[1]), "Rows": f"{int(row[2]):,}"}
            return {"Dataset": label, "From": "—", "To": "—", "Rows": "0"}

        global_rows = [
            _cov(tsy_row,   "Treasury Yields"),
            _cov(vix_row,   "VIX Bars"),
            _cov(macro_row, "Macro (FRED)"),
            _cov(cpi_row,   "CPI (FRED)"),
            _cov(vxf_row,   "VIX Futures"),
            _cov(fomc_row,  "FOMC Calendar"),
        ]
        st.dataframe(pd.DataFrame(global_rows), hide_index=True, width="stretch")

    except Exception as e:
        st.error(f"Could not load coverage: {e}")

    st.markdown("---")

    # ── Training Data Validation ───────────────────────────────────────────────
    st.subheader("Training Data Validation")
    val_ticker = st.text_input(
        "Ticker", placeholder="e.g. SPY, TLT…", key="dm_val_ticker"
    ).strip().upper()
    if st.button("Validate", key="dm_validate", disabled=not val_ticker):
        from alan_trader.db.loader import validate_training_data
        with st.spinner("Checking database…"):
            report = validate_training_data(val_ticker)

        if report["issues"]:
            for issue in report["issues"]:
                st.error(f"BLOCKER: {issue}")
        elif report["warnings"]:
            st.warning(f"{val_ticker} price data is ready for training, but some data is missing.")
        else:
            st.success(f"{val_ticker} data is ready for training.")

        for warn in report["warnings"]:
            st.caption(f"⚠ {warn}")

        if report["coverage"]:
            cov_rows = []
            for label, (mn, mx, cnt) in report["coverage"].items():
                rows_str = f"{cnt:,}" if isinstance(cnt, int) and cnt > 0 else str(cnt)
                cov_rows.append({"Data": label, "From": str(mn), "To": str(mx), "Rows": rows_str})
            st.dataframe(pd.DataFrame(cov_rows), hide_index=True, width="stretch")
