"""
Data Manager tab — SQL Server coverage status, Polygon sync controls,
and training data validation.
"""

import streamlit as st
import pandas as pd
from datetime import date, timedelta


def render(api_key: str = ""):
    st.markdown("## Data Manager")

    if not api_key:
        st.warning("Enter your Polygon API key in the sidebar to use sync features.")

    from alan_trader.db.client import get_engine
    from alan_trader.db.sync   import get_coverage_summary

    SYMBOLS = ["HOOD", "SPY", "QQQ", "AAPL", "TSLA", "MARA"]

    # ── Training Data Validation ───────────────────────────────────────────────
    st.subheader("Training Data Validation")
    val_ticker = st.selectbox("Validate ticker", SYMBOLS, key="dm_val_ticker")
    if st.button("Validate", key="dm_validate"):
        from alan_trader.db.loader import validate_training_data
        with st.spinner("Checking database..."):
            report = validate_training_data(val_ticker)

        if report["issues"]:
            for issue in report["issues"]:
                st.error(f"BLOCKER: {issue}")
        else:
            st.success(f"{val_ticker} data is ready for training.")

        for warn in report["warnings"]:
            st.warning(warn)

        if report["coverage"]:
            cov_rows = []
            for label, (mn, mx, cnt) in report["coverage"].items():
                cov_rows.append({"Data": label, "From": str(mn), "To": str(mx), "Rows": f"{cnt:,}"})
            st.dataframe(pd.DataFrame(cov_rows), width="stretch", hide_index=True)

    st.markdown("---")

    # ── Coverage Table ─────────────────────────────────────────────────────────
    st.subheader("Data Coverage")
    try:
        with st.spinner("Loading coverage..."):
            df_cov = get_coverage_summary(SYMBOLS)
        st.dataframe(df_cov, width="stretch", hide_index=True)
    except Exception as e:
        st.error(f"Could not load coverage: {e}")
        return

    # ── Options Chain Coverage ─────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("Options Chain Coverage (mkt.OptionSnapshot)")
    st.caption("Shows how many option snapshot rows are in the DB per ticker — required for real spread P&L training.")
    try:
        engine = get_engine()
        from sqlalchemy import text as _text
        _placeholders = ", ".join(f":s{i}" for i in range(len(SYMBOLS)))
        _params = {f"s{i}": s for i, s in enumerate(SYMBOLS)}
        with engine.connect() as _conn:
            _res = _conn.execute(_text(f"""
                SELECT t.Symbol,
                       COUNT(*)         AS Rows,
                       MIN(o.SnapshotDate) AS EarliestDate,
                       MAX(o.SnapshotDate) AS LatestDate,
                       COUNT(DISTINCT o.SnapshotDate) AS UniqueDates,
                       COUNT(DISTINCT o.ExpirationDate) AS UniqueExpiries
                FROM mkt.OptionSnapshot o
                JOIN mkt.Ticker t ON t.TickerId = o.TickerId
                WHERE t.Symbol IN ({_placeholders})
                GROUP BY t.Symbol
                ORDER BY Rows DESC
            """), _params)
            _rows = _res.fetchall()
        if _rows:
            opt_cov = pd.DataFrame(_rows, columns=["Ticker", "Rows", "Earliest Date", "Latest Date", "Unique Dates", "Unique Expiries"])
            opt_cov["Rows"] = opt_cov["Rows"].apply(lambda x: f"{int(x):,}")
            opt_cov["Unique Dates"] = opt_cov["Unique Dates"].apply(lambda x: f"{int(x):,}")
            st.dataframe(opt_cov, width="stretch", hide_index=True)
            tickers_with_data = set(opt_cov["Ticker"].tolist())
            missing = [s for s in SYMBOLS if s not in tickers_with_data]
            if missing:
                st.warning(f"No options data found for: **{', '.join(missing)}**. Sync options data for these tickers to enable real spread P&L training.")
        else:
            st.warning("No option snapshot data found in mkt.OptionSnapshot for any tracked ticker. Use the sync controls below to download options data.")
    except Exception as _oe:
        st.error(f"Could not load options coverage: {_oe}")

    st.markdown("---")

    # ── Sync Controls ─────────────────────────────────────────────────────────
    st.subheader("Sync from Polygon")

    col1, col2 = st.columns(2)
    ticker    = col1.selectbox("Ticker", SYMBOLS, key="dm_ticker")
    from_date = col2.date_input("Backfill from", value=date.today() - timedelta(days=730),
                                 key="dm_from_date")

    # ── Price Bars ────────────────────────────────────────────────────────────
    with st.expander("Price Bars", expanded=True):
        st.caption("Daily OHLCV from Polygon. Incremental — only fetches missing dates.")
        if st.button("Sync Price Bars", key="dm_sync_price", disabled=not api_key):
            from alan_trader.db.sync import sync_price_bars
            progress = st.empty()
            try:
                with st.spinner("Syncing price bars..."):
                    result = sync_price_bars(
                        ticker, api_key,
                        from_date=from_date,
                        progress_cb=lambda msg: progress.caption(msg),
                    )
                progress.empty()
                if result["status"] == "up_to_date":
                    st.success(f"{ticker} price bars are already up to date.")
                elif result["status"] == "no_data":
                    st.warning("No data returned from Polygon.")
                else:
                    st.success(f"Done.")
                    st.metric("Rows inserted", f"{result['rows']:,}")
                st.rerun()
            except Exception as e:
                st.error(f"Sync failed: {e}")

    # ── VIX Bars ──────────────────────────────────────────────────────────────
    with st.expander("VIX Bars", expanded=False):
        st.caption("Daily VIX OHLCV from CBOE (free, no API key needed).")
        if st.button("Sync VIX Bars", key="dm_sync_vix"):
            from alan_trader.db.sync import sync_vix_bars
            progress = st.empty()
            try:
                with st.spinner("Syncing VIX from CBOE..."):
                    result = sync_vix_bars(
                        from_date=from_date,
                        progress_cb=lambda msg: progress.caption(msg),
                    )
                progress.empty()
                if result["status"] == "up_to_date":
                    st.success("VIX bars are already up to date.")
                elif result["status"] == "no_data":
                    st.warning(result.get("message", "No VIX data returned."))
                else:
                    st.success("Done.")
                    st.metric("Rows inserted", f"{result['rows']:,}")
                st.rerun()
            except Exception as e:
                st.error(f"Sync failed: {e}")

    # ── Macro Bars (FRED) ─────────────────────────────────────────────────────
    with st.expander("Macro Bars — FRED (free, no API key needed)", expanded=False):
        st.caption("Full yield curve (3M→30Y), SOFR, jobless claims. Fetched free from FRED.")
        if st.button("Sync Macro Bars", key="dm_sync_macro"):
            from alan_trader.db.sync import sync_macro_bars
            progress = st.empty()
            try:
                with st.spinner("Fetching macro data from FRED..."):
                    result = sync_macro_bars(
                        from_date=from_date,
                        progress_cb=lambda msg: progress.caption(msg),
                    )
                progress.empty()
                if result["status"] == "up_to_date":
                    st.success("Macro bars are already up to date.")
                elif result["status"] == "no_data":
                    st.warning(result.get("message", "No data returned from FRED."))
                else:
                    st.success("Done.")
                    st.metric("Rows inserted", f"{result['rows']:,}")
                st.rerun()
            except Exception as e:
                st.error(f"Sync failed: {e}")

    # ── News ──────────────────────────────────────────────────────────────────
    with st.expander("News (Polygon)", expanded=False):
        st.caption("News articles tagged to the ticker. Sentiment scored automatically via VADER.")
        if st.button(f"Sync {ticker} News", key="dm_sync_news", disabled=not api_key):
            from alan_trader.db.sync import sync_news
            progress = st.empty()
            try:
                with st.spinner(f"Fetching {ticker} news..."):
                    result = sync_news(
                        ticker, api_key,
                        from_date=from_date,
                        progress_cb=lambda msg: progress.caption(msg),
                    )
                progress.empty()
                if result["status"] == "up_to_date":
                    st.success(f"{ticker} news is already up to date.")
                elif result["status"] == "no_data":
                    st.warning("No news returned.")
                else:
                    st.success("Done.")
                    st.metric("Articles inserted / updated", f"{result['rows']:,}")
                st.rerun()
            except Exception as e:
                st.error(f"Sync failed: {e}")

    # ── Options Snapshots ─────────────────────────────────────────────────────
    with st.expander("Options Snapshots (EOD)", expanded=False):
        st.caption(
            "Historical EOD options chain — 1 snapshot per trading day. "
            "Requires SPY price bars to already be synced (used as trading calendar). "
            "Can take several minutes for a full backfill."
        )
        st.warning(
            "This loops through each trading day and makes one API call per day. "
            f"A full 2-year backfill for {ticker} is ~500 calls."
        )
        if st.button(f"Sync {ticker} Options", key="dm_sync_options", disabled=not api_key):
            from alan_trader.db.sync import sync_option_snapshots
            progress_text = st.empty()
            progress_bar  = st.progress(0)
            rows_counter  = st.empty()
            try:
                def _cb(msg, current, total, rows_so_far=0):
                    progress_text.caption(msg)
                    progress_bar.progress(current / total)
                    rows_counter.metric("Rows inserted so far", f"{rows_so_far:,}")

                result = sync_option_snapshots(
                    ticker, api_key,
                    from_date=from_date,
                    progress_cb=_cb,
                )

                progress_bar.empty()
                rows_counter.empty()
                progress_text.empty()

                if result["status"] == "up_to_date":
                    st.success(f"{ticker} options are already up to date.")
                elif result["status"] == "no_calendar":
                    st.error(result["message"])
                else:
                    st.success(f"Done.")
                    c1, c2 = st.columns(2)
                    c1.metric("Rows inserted", f"{result['rows']:,}")
                    c2.metric("Trading days", f"{result['dates']}")
                    if result.get("errors"):
                        with st.expander(f"{len(result['errors'])} errors"):
                            for e in result["errors"]:
                                st.caption(e)
                st.rerun()
            except Exception as e:
                st.error(f"Sync failed: {e}")
