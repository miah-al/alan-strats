"""
Earnings Post-Drift (SUE) Strategy.

Edge: Markets systematically underreact to large EPS surprises — Standardised Unexpected
Earnings (SUE) effect documented since Bernard & Thomas (1989). After a big beat
(EPS surprise > 10%), the stock drifts 2-4% higher over 2-3 weeks as analysts revise
estimates and slow-moving institutional capital builds positions.

Trade structure:
  - Buy ATM call (nearest ATM strike at or below spot)
  - Sell OTM call at ATM + spread_width_pct * spot   (caps upside = defined risk)

Entry: morning after earnings beat (next open after report)
Exit: after hold_days OR at profit_target OR stop_loss, whichever comes first

Signal filters:
  1. eps_surprise_pct > min_surprise_pct  (magnitude of beat)
  2. gap_pct < max_gap_pct               (don't chase if already gapped hard)
  3. eps_estimate must be non-NULL (events without estimates are skipped)

auxiliary_data contract
-----------------------
  "earnings"     : DataFrame with [date, ticker, eps_actual, eps_estimate]
                   eps_estimate must be present and non-NULL to trade; rows without
                   a valid estimate are skipped (not defaulted to 0).
  "vix"          : VIX price DataFrame (date-indexed, "close" column)
  "rate10y"      : 10-year rates DataFrame (date-indexed, "close" column)
  "stock_prices" : dict of {ticker_symbol: OHLCV_DataFrame} — required per-ticker data.
                   Each DataFrame should be date-indexed with at least "open" and "close" columns.
                   Events with no matching ticker data are skipped.
  "options_chains": dict of {ticker: dict[datetime.date, pd.DataFrame]} — optional.
                   Each chain DataFrame should have an "iv" column. When available,
                   real chain IV replaces the VIX proxy.
"""

import logging
import numpy as np
import pandas as pd

from alan_trader.strategies.base import (
    BaseStrategy, BacktestResult, SignalResult,
    StrategyStatus, StrategyType,
)
from alan_trader.risk.metrics import compute_all_metrics
from alan_trader.backtest.engine import bs_price

logger = logging.getLogger(__name__)


class EarningsPostDriftStrategy(BaseStrategy):
    name                 = "earnings_post_drift"
    display_name         = "Earnings Post-Drift"
    strategy_type        = StrategyType.RULE_BASED
    status               = StrategyStatus.ACTIVE
    description          = (
        "Buys bull call spreads on the REPORTING STOCK the morning after large EPS beats "
        "(>10% surprise). Captures the SUE effect — markets systematically underreact to "
        "earnings beats, stocks drift 2-4% higher over 2-3 weeks post-announcement."
    )
    asset_class          = "equities_options"
    typical_holding_days = 14
    target_sharpe        = 1.3

    def __init__(
        self,
        min_surprise_pct:   float = 0.10,   # 10% EPS beat threshold
        max_gap_pct:        float = 0.15,   # don't chase if >15% gap-up
        spread_width_pct:   float = 0.05,   # spread width = 5% of spot
        dte_entry:          int   = 21,     # buy 21-DTE calls
        hold_days:          int   = 14,     # max hold = 14 days
        profit_target_pct:  float = 0.50,   # close at 50% of max spread value
        stop_loss_pct:      float = 1.0,    # stop at 100% loss of debit paid
        position_size_pct:  float = 0.03,   # 3% of capital per trade
        commission_per_leg: float = 0.65,
        min_stock_price:    float = 10.0,   # skip penny stocks below this price
        max_stocks:         int   = 20,     # cap universe size to avoid overfitting
    ):
        self.min_surprise_pct  = min_surprise_pct
        self.max_gap_pct       = max_gap_pct
        self.spread_width_pct  = spread_width_pct
        self.dte_entry         = dte_entry
        self.hold_days         = hold_days
        self.profit_target_pct = profit_target_pct
        self.stop_loss_pct     = stop_loss_pct
        self.position_size_pct = position_size_pct
        self.commission_per_leg = commission_per_leg
        self.min_stock_price   = min_stock_price
        self.max_stocks        = max_stocks

    # ── Signal (live) ──────────────────────────────────────────────────────

    def generate_signal(self, market_snapshot: dict) -> SignalResult:
        """
        Live signal from market_snapshot.
        Expects market_snapshot to contain:
          - "earnings": dict with keys "eps_actual", "eps_estimate", "gap_pct", "ticker"
          - "price" or "close": current spot price (legacy "spy_price" also accepted)
          - "vix": current VIX level
        """
        earnings = market_snapshot.get("earnings", {})
        if not earnings:
            return SignalResult(
                strategy_name=self.name,
                signal="HOLD",
                confidence=0.0,
                position_size_pct=0.0,
                metadata={"reason": "no earnings event in snapshot"},
            )

        eps_actual   = earnings.get("eps_actual")
        eps_estimate = earnings.get("eps_estimate")
        gap_pct      = float(earnings.get("gap_pct", 0.0))

        # Require a valid estimate — never default to 0
        if eps_estimate is None or pd.isna(eps_estimate):
            return SignalResult(
                strategy_name=self.name,
                signal="HOLD",
                confidence=0.0,
                position_size_pct=0.0,
                metadata={"reason": "eps_estimate is NULL — cannot compute surprise"},
            )

        eps_actual   = float(eps_actual)
        eps_estimate = float(eps_estimate)

        if eps_estimate == 0:
            return SignalResult(
                strategy_name=self.name,
                signal="HOLD",
                confidence=0.0,
                position_size_pct=0.0,
                metadata={"reason": "eps_estimate is zero — cannot compute surprise"},
            )

        surprise = (eps_actual - eps_estimate) / abs(eps_estimate)

        if surprise < self.min_surprise_pct:
            return SignalResult(
                strategy_name=self.name,
                signal="HOLD",
                confidence=0.0,
                position_size_pct=0.0,
                metadata={
                    "reason": f"surprise {surprise:.1%} < min {self.min_surprise_pct:.1%}",
                    "eps_surprise_pct": round(surprise, 4),
                },
            )

        if gap_pct >= self.max_gap_pct:
            return SignalResult(
                strategy_name=self.name,
                signal="HOLD",
                confidence=0.0,
                position_size_pct=0.0,
                metadata={
                    "reason": f"gap {gap_pct:.1%} >= max {self.max_gap_pct:.1%} — chasing rejected",
                    "gap_pct": round(gap_pct, 4),
                },
            )

        # Confidence scales with both the surprise magnitude and room before gap cap
        gap_headroom = max(0, self.max_gap_pct - gap_pct) / self.max_gap_pct
        surprise_score = min(1.0, (surprise - self.min_surprise_pct) / 0.20)
        confidence = 0.45 + 0.40 * surprise_score + 0.15 * gap_headroom

        return SignalResult(
            strategy_name=self.name,
            signal="BUY",
            confidence=round(min(0.95, confidence), 3),
            position_size_pct=self.position_size_pct,
            metadata={
                "trade":            "bull_call_spread",
                "eps_actual":       eps_actual,
                "eps_estimate":     eps_estimate,
                "eps_surprise_pct": round(surprise, 4),
                "gap_pct":          round(gap_pct, 4),
                "ticker":           earnings.get("ticker"),
            },
        )

    # ── Backtest ───────────────────────────────────────────────────────────

    def backtest(
        self,
        price_data: pd.DataFrame,
        auxiliary_data: dict,
        starting_capital:   float = 100_000,
        min_surprise_pct:   float | None = None,
        max_gap_pct:        float | None = None,
        spread_width_pct:   float | None = None,
        hold_days:          int   | None = None,
        profit_target_pct:  float | None = None,
        stop_loss_pct:      float | None = None,
        position_size_pct:  float | None = None,
        **kwargs,
    ) -> BacktestResult:

        # Resolve params (UI overrides take priority)
        min_surp  = min_surprise_pct  if min_surprise_pct  is not None else self.min_surprise_pct
        max_gap   = max_gap_pct       if max_gap_pct       is not None else self.max_gap_pct
        spr_w     = spread_width_pct  if spread_width_pct  is not None else self.spread_width_pct
        hold      = hold_days         if hold_days         is not None else self.hold_days
        pt_pct    = profit_target_pct if profit_target_pct is not None else self.profit_target_pct
        sl_pct    = stop_loss_pct     if stop_loss_pct     is not None else self.stop_loss_pct
        pos_size  = position_size_pct if position_size_pct is not None else self.position_size_pct
        min_price = self.min_stock_price
        max_stk   = self.max_stocks

        # UI sliders may send values as integers (percentages × 100)
        if min_surp >= 1: min_surp /= 100
        if max_gap  >= 1: max_gap  /= 100
        if spr_w    >= 1: spr_w    /= 100
        if pt_pct   >= 1: pt_pct   /= 100
        if sl_pct   >= 10: sl_pct  /= 100
        if pos_size >= 1: pos_size /= 100

        price_data = price_data.copy()
        price_data.index = pd.to_datetime(price_data.index)

        # ── Data validation ────────────────────────────────────────────────
        earnings_df = auxiliary_data.get("earnings", pd.DataFrame())
        if isinstance(earnings_df, pd.DataFrame) and earnings_df.empty:
            raise ValueError(
                "No earnings data found in auxiliary_data['earnings'].\n\n"
                "This strategy requires a DataFrame with columns: "
                "[date, ticker, eps_actual, eps_estimate].\n"
                "Please sync earnings data from the Data Manager."
            )

        vix_df = auxiliary_data.get("vix", pd.DataFrame())
        if isinstance(vix_df, pd.DataFrame) and not vix_df.empty:
            vix_df = vix_df.copy()
            vix_df.index = pd.to_datetime(vix_df.index)
            vix = vix_df["close"].reindex(price_data.index).ffill().infer_objects(copy=False).fillna(20.0)
        else:
            vix = pd.Series(20.0, index=price_data.index)

        rate_df = auxiliary_data.get("rate10y", pd.DataFrame())
        if isinstance(rate_df, pd.DataFrame) and not rate_df.empty:
            rate_df = rate_df.copy()
            rate_df.index = pd.to_datetime(rate_df.index)
            rate = rate_df["close"].reindex(price_data.index).ffill().infer_objects(copy=False).fillna(0.045)
        else:
            rate = pd.Series(0.045, index=price_data.index)

        # Per-ticker price data: dict of {ticker: OHLCV DataFrame}
        stock_prices: dict = auxiliary_data.get("stock_prices", {}) or {}

        # Options chains: dict of {ticker: dict[datetime.date, pd.DataFrame]}
        options_chains: dict = auxiliary_data.get("options_chains", {}) or {}

        portfolio_close = price_data["close"]
        portfolio_open  = price_data.get("open", portfolio_close)   # use open if available, else close
        trading_dates = list(price_data.index)

        # ── Earnings DataFrame normalisation ───────────────────────────────
        if isinstance(earnings_df, pd.DataFrame):
            edf = earnings_df.copy()
        else:
            raise ValueError("auxiliary_data['earnings'] must be a pandas DataFrame.")

        date_col = None
        for col in ["date", "earnings_date", "report_date"]:
            if col in edf.columns:
                date_col = col
                break
        if date_col is None:
            edf = edf.reset_index().rename(columns={"index": "date"})
            date_col = "date"
        edf[date_col] = pd.to_datetime(edf[date_col])
        edf = edf.sort_values(date_col)

        # Cap universe to max_stocks (first N unique tickers in chronological order)
        if "ticker" in edf.columns:
            unique_tickers = list(dict.fromkeys(edf["ticker"].dropna().tolist()))
            if len(unique_tickers) > max_stk:
                allowed_tickers = set(unique_tickers[:max_stk])
                edf = edf[edf["ticker"].isin(allowed_tickers)]

        # Lookup: earnings_date → row (one per date; last wins on collision)
        earnings_by_date: dict[pd.Timestamp, pd.Series] = {
            row[date_col]: row for _, row in edf.iterrows()
        }

        # Pre-index per-ticker close/open series for O(1) lookup
        ticker_close_cache: dict[str, pd.Series] = {}
        ticker_open_cache:  dict[str, pd.Series] = {}
        for tkr, tkr_df in stock_prices.items():
            try:
                df_copy = tkr_df.copy()
                df_copy.index = pd.to_datetime(df_copy.index)
                key = str(tkr).upper()
                ticker_close_cache[key] = df_copy["close"]
                if "open" in df_copy.columns:
                    ticker_open_cache[key] = df_copy["open"]
                else:
                    ticker_open_cache[key] = df_copy["close"]
            except Exception:
                pass  # skip malformed entries

        # ── Walk-forward simulation ────────────────────────────────────────
        capital      = float(starting_capital)
        equity_list  = []
        trades_list  = []

        # Track open position state (one trade at a time)
        open_trade: dict | None = None

        for i, dt in enumerate(trading_dates):
            # ── Resolve SPY-level iv/rate for MTM of open trade ───────────
            vix_iv = float(vix.iloc[i]) / 100.0
            r      = float(rate.iloc[i])

            # ── Manage open trade ──────────────────────────────────────────
            if open_trade is not None:
                days_held = (dt - open_trade["entry_date"]).days
                T_remain  = max(0, (self.dte_entry - days_held) / 252)

                long_k     = open_trade["long_strike"]
                short_k    = open_trade["short_strike"]
                entry_cost = open_trade["entry_cost"]
                contracts  = open_trade["contracts"]
                ticker_ot  = open_trade["ticker"]

                # Current spot for the stock that was traded
                stock_close_ot = ticker_close_cache.get(ticker_ot, portfolio_close)
                if dt in stock_close_ot.index:
                    spot = float(stock_close_ot.loc[dt])
                else:
                    prior = stock_close_ot[stock_close_ot.index <= dt]
                    spot  = float(prior.iloc[-1]) if not prior.empty else float(portfolio_close.iloc[i])

                # IV for MTM: real options chain if available, else raw VIX
                chain_df_ot = options_chains.get(ticker_ot, {}).get(dt.date())
                if chain_df_ot is not None and not chain_df_ot.empty and "iv" in chain_df_ot.columns:
                    iv = float(chain_df_ot["iv"].dropna().median())
                else:
                    iv = vix_iv

                # Current spread value
                lv = bs_price(spot, long_k,  T_remain, r, iv, "call")
                sv = bs_price(spot, short_k, T_remain, r, iv, "call")
                current_val = max(0, lv - sv)

                unrealised_pnl = (current_val - entry_cost) * contracts * 100

                take_profit = entry_cost * pt_pct * contracts * 100
                stop_loss   = entry_cost * sl_pct * contracts * 100

                exit_reason = None
                if unrealised_pnl >= take_profit:
                    exit_reason = "take_profit"
                elif unrealised_pnl <= -stop_loss:
                    exit_reason = "stop_loss"
                elif days_held >= hold:
                    exit_reason = "time_exit"

                if exit_reason is not None:
                    exit_val  = current_val
                    trade_pnl = (exit_val - entry_cost) * contracts * 100
                    trade_pnl -= contracts * 2 * self.commission_per_leg   # exit commissions
                    capital += trade_pnl

                    trades_list.append({
                        "entry_date":       open_trade["entry_date"].date(),
                        "exit_date":        dt.date(),
                        "spread_type":      "bull_call_spread",
                        "ticker":           open_trade["ticker"],
                        "spot_entry":       round(open_trade["spot_entry"], 2),
                        "spot_exit":        round(spot, 2),
                        "long_strike":      long_k,
                        "short_strike":     short_k,
                        "entry_cost":       round(entry_cost, 4),
                        "exit_value":       round(exit_val, 4),
                        "contracts":        contracts,
                        "eps_surprise_pct": round(open_trade["eps_surprise_pct"], 4),
                        "gap_pct":          round(open_trade["gap_pct"], 4),
                        "days_held":        days_held,
                        "pnl":              round(trade_pnl, 2),
                        "exit_reason":      exit_reason,
                    })
                    open_trade = None

            # ── Check for new entry signal ─────────────────────────────────
            # PEAD entry: earnings are typically filed AFTER market close on day T.
            # We enter at the OPEN of day T+1 (i.e. current dt), so we look up
            # whether the PREVIOUS trading day (prev_dt) had an earnings event.
            prev_dt = trading_dates[i - 1] if i > 0 else None
            if open_trade is None and prev_dt is not None and prev_dt in earnings_by_date:
                row    = earnings_by_date[prev_dt]
                ticker = str(row.get("ticker", "")).upper()

                # Require non-NULL eps_estimate — do NOT default to 0
                eps_estimate_raw = row.get("eps_estimate")
                if eps_estimate_raw is None or (isinstance(eps_estimate_raw, float) and pd.isna(eps_estimate_raw)):
                    equity_list.append(capital)
                    continue
                try:
                    eps_estimate = float(eps_estimate_raw)
                except (TypeError, ValueError):
                    equity_list.append(capital)
                    continue

                if eps_estimate == 0:
                    equity_list.append(capital)
                    continue

                eps_actual_raw = row.get("eps_actual")
                if eps_actual_raw is None or (isinstance(eps_actual_raw, float) and pd.isna(eps_actual_raw)):
                    equity_list.append(capital)
                    continue
                eps_actual = float(eps_actual_raw)

                surprise = (eps_actual - eps_estimate) / abs(eps_estimate)

                # ── Resolve stock price data ───────────────────────────────
                stock_df_check = stock_prices.get(ticker.upper())
                if stock_df_check is None or (hasattr(stock_df_check, "empty") and stock_df_check.empty):
                    logger.debug("earnings_post_drift: no price data for %s — skipping", ticker)
                    equity_list.append(capital)
                    continue

                stock_close = ticker_close_cache.get(ticker)
                stock_open  = ticker_open_cache.get(ticker)
                if stock_close is None:
                    logger.debug("earnings_post_drift: no price data for %s — skipping", ticker)
                    equity_list.append(capital)
                    continue

                # Entry spot: open of the CURRENT day (day after filing)
                if stock_open is not None and dt in stock_open.index:
                    entry_spot = float(stock_open.loc[dt])
                elif dt in stock_close.index:
                    entry_spot = float(stock_close.loc[dt])
                else:
                    logger.debug("earnings_post_drift: no price data for %s on %s — skipping", ticker, dt.date())
                    equity_list.append(capital)
                    continue

                # Gap: entry-day open vs filing-day close (prev_dt close)
                if prev_dt in stock_close.index:
                    filing_day_close = float(stock_close.loc[prev_dt])
                else:
                    prior_closes = stock_close[stock_close.index < prev_dt]
                    filing_day_close = float(prior_closes.iloc[-1]) if not prior_closes.empty else None

                gap_pct = ((entry_spot - filing_day_close) / filing_day_close
                           if filing_day_close and filing_day_close > 0 else 0.0)

                if surprise < min_surp or gap_pct >= max_gap:
                    equity_list.append(capital)
                    continue

                # Skip penny stocks
                if entry_spot < min_price:
                    equity_list.append(capital)
                    continue

                # IV: real options chain if available, else raw VIX
                chain_df_entry = options_chains.get(ticker, {}).get(dt.date())
                if chain_df_entry is not None and not chain_df_entry.empty and "iv" in chain_df_entry.columns:
                    iv = float(chain_df_entry["iv"].dropna().median())
                else:
                    iv = vix_iv
                T_entry = self.dte_entry / 252

                # ATM strike: nearest $1 for stocks ≤$500, nearest $5 for >$500
                if entry_spot <= 500:
                    long_k = round(entry_spot / 1) * 1
                else:
                    long_k = round(entry_spot / 5) * 5

                width   = entry_spot * spr_w
                if entry_spot <= 500:
                    short_k = round((entry_spot + width) / 1) * 1
                else:
                    short_k = round((entry_spot + width) / 5) * 5

                long_leg  = bs_price(entry_spot, long_k,  T_entry, r, iv, "call")
                short_leg = bs_price(entry_spot, short_k, T_entry, r, iv, "call")
                entry_cost = max(0, long_leg - short_leg + 0.05)  # +5¢ slippage

                if entry_cost <= 0:
                    equity_list.append(capital)
                    continue

                budget    = capital * pos_size
                risk_per  = entry_cost * 100   # per contract
                contracts = max(1, int(budget / risk_per))

                total_cost = contracts * entry_cost * 100 + contracts * 2 * self.commission_per_leg
                if total_cost > capital:
                    equity_list.append(capital)
                    continue

                capital -= total_cost

                open_trade = {
                    "entry_date":       dt,
                    "long_strike":      long_k,
                    "short_strike":     short_k,
                    "entry_cost":       entry_cost,
                    "contracts":        contracts,
                    "max_spread_val":   short_k - long_k,
                    "spot_entry":       entry_spot,
                    "eps_surprise_pct": surprise,
                    "gap_pct":          gap_pct,
                    "ticker":           ticker,
                }

            # Mark-to-market: include current value of open bull call spread
            if open_trade is not None:
                days_held_mtm = (dt - open_trade["entry_date"]).days
                T_mtm = max(0.0, (self.dte_entry - days_held_mtm) / 252)

                ticker_mtm  = open_trade["ticker"]
                sc_mtm      = ticker_close_cache.get(ticker_mtm, portfolio_close)
                if dt in sc_mtm.index:
                    spot_mtm = float(sc_mtm.loc[dt])
                else:
                    prior = sc_mtm[sc_mtm.index <= dt]
                    spot_mtm = float(prior.iloc[-1]) if not prior.empty else float(portfolio_close.iloc[i])

                chain_df_mtm = options_chains.get(ticker_mtm, {}).get(dt.date())
                if chain_df_mtm is not None and not chain_df_mtm.empty and "iv" in chain_df_mtm.columns:
                    iv_mtm = float(chain_df_mtm["iv"].dropna().median())
                else:
                    iv_mtm = vix_iv
                lv_mtm = bs_price(spot_mtm, open_trade["long_strike"],  T_mtm, r, iv_mtm, "call")
                sv_mtm = bs_price(spot_mtm, open_trade["short_strike"], T_mtm, r, iv_mtm, "call")
                mtm_val = max(0.0, lv_mtm - sv_mtm)
                equity_list.append(capital + mtm_val * open_trade["contracts"] * 100.0)
            else:
                equity_list.append(capital)

        # Close any remaining open trade at end of data
        if open_trade is not None and equity_list:
            last_dt    = trading_dates[-1]
            last_vix   = float(vix.iloc[-1]) / 100.0
            last_r     = float(rate.iloc[-1])
            days_held  = (last_dt - open_trade["entry_date"]).days
            T_remain   = max(0, (self.dte_entry - days_held) / 252)

            ticker_fin   = open_trade["ticker"]
            chain_df_fin = options_chains.get(ticker_fin, {}).get(last_dt.date())
            if chain_df_fin is not None and not chain_df_fin.empty and "iv" in chain_df_fin.columns:
                last_iv = float(chain_df_fin["iv"].dropna().median())
            else:
                last_iv = last_vix

            sc_fin = ticker_close_cache.get(ticker_fin, portfolio_close)
            if last_dt in sc_fin.index:
                last_spot = float(sc_fin.loc[last_dt])
            else:
                prior = sc_fin[sc_fin.index <= last_dt]
                last_spot = float(prior.iloc[-1]) if not prior.empty else float(portfolio_close.iloc[-1])

            lv = bs_price(last_spot, open_trade["long_strike"],  T_remain, last_r, last_iv, "call")
            sv = bs_price(last_spot, open_trade["short_strike"], T_remain, last_r, last_iv, "call")
            exit_val  = max(0, lv - sv)
            trade_pnl = (exit_val - open_trade["entry_cost"]) * open_trade["contracts"] * 100
            trade_pnl -= open_trade["contracts"] * 2 * self.commission_per_leg
            capital += trade_pnl

            trades_list.append({
                "entry_date":       open_trade["entry_date"].date(),
                "exit_date":        last_dt.date(),
                "spread_type":      "bull_call_spread",
                "ticker":           open_trade["ticker"],
                "spot_entry":       round(open_trade["spot_entry"], 2),
                "spot_exit":        round(last_spot, 2),
                "long_strike":      open_trade["long_strike"],
                "short_strike":     open_trade["short_strike"],
                "entry_cost":       round(open_trade["entry_cost"], 4),
                "exit_value":       round(exit_val, 4),
                "contracts":        open_trade["contracts"],
                "eps_surprise_pct": round(open_trade["eps_surprise_pct"], 4),
                "gap_pct":          round(open_trade["gap_pct"], 4),
                "days_held":        days_held,
                "pnl":              round(trade_pnl, 2),
                "exit_reason":      "end_of_data",
            })
            equity_list[-1] = capital

        # ── Build outputs ──────────────────────────────────────────────────
        equity    = pd.Series(equity_list, index=trading_dates, dtype=float)
        daily_ret = equity.pct_change().dropna()
        bh_ret    = portfolio_close.pct_change().reindex(equity.index).dropna()

        trades_df = pd.DataFrame(trades_list) if trades_list else pd.DataFrame(
            columns=["entry_date", "exit_date", "spread_type", "ticker",
                     "spot_entry", "spot_exit", "long_strike", "short_strike",
                     "entry_cost", "exit_value", "contracts",
                     "eps_surprise_pct", "gap_pct", "days_held", "pnl", "exit_reason"]
        )

        metrics = compute_all_metrics(
            equity_curve=equity,
            trades_df=trades_df,
            benchmark_returns=bh_ret,
        )

        return BacktestResult(
            strategy_name=self.name,
            equity_curve=equity,
            daily_returns=daily_ret,
            trades=trades_df,
            metrics=metrics,
            params={
                **self.get_params(),
                "min_surprise_pct":  min_surp,
                "max_gap_pct":       max_gap,
                "spread_width_pct":  spr_w,
                "hold_days":         hold,
                "profit_target_pct": pt_pct,
                "stop_loss_pct":     sl_pct,
                "position_size_pct": pos_size,
            },
            extra={
                "vix":       vix,
                "rate10y":   rate,
                "portfolio_close": portfolio_close,
            },
        )

    # ── UI params ──────────────────────────────────────────────────────────

    def get_backtest_ui_params(self) -> list:
        return [
            {
                "key": "min_surprise_pct",
                "label": "Min EPS surprise (%)",
                "type": "slider", "min": 5, "max": 30, "default": 10, "step": 5,
                "col": 0, "row": 0,
                "help": "Minimum EPS beat vs estimate (%) needed to enter. Higher = more selective.",
            },
            {
                "key": "max_gap_pct",
                "label": "Max gap-up (%)",
                "type": "slider", "min": 5, "max": 30, "default": 15, "step": 5,
                "col": 1, "row": 0,
                "help": "Don't enter if stock already gapped up more than this. Avoids chasing.",
            },
            {
                "key": "spread_width_pct",
                "label": "Spread width (% of spot)",
                "type": "slider", "min": 2, "max": 10, "default": 5, "step": 1,
                "col": 2, "row": 0,
                "help": "Distance between long and short call strikes as % of spot price.",
            },
            {
                "key": "hold_days",
                "label": "Max hold days",
                "type": "slider", "min": 5, "max": 30, "default": 14, "step": 1,
                "col": 0, "row": 1,
                "help": "Maximum days to hold the spread before forced exit.",
            },
            {
                "key": "profit_target_pct",
                "label": "Profit target (× debit)",
                "type": "slider", "min": 25, "max": 100, "default": 50, "step": 5,
                "col": 1, "row": 1,
                "help": "Close when unrealised gain = this % of debit paid.",
            },
            {
                "key": "position_size_pct",
                "label": "Position size (% of capital)",
                "type": "slider", "min": 1, "max": 10, "default": 3, "step": 1,
                "col": 2, "row": 1,
                "help": "Max capital risked per trade as % of portfolio. Max loss = debit paid.",
            },
            {
                "key": "min_stock_price",
                "label": "Min stock price ($)",
                "type": "slider", "min": 5, "max": 50, "default": 10, "step": 5,
                "col": 0, "row": 2,
                "help": "Skip stocks trading below this price (penny stock filter).",
            },
        ]

    def get_params(self) -> dict:
        return {
            "min_surprise_pct":   self.min_surprise_pct,
            "max_gap_pct":        self.max_gap_pct,
            "spread_width_pct":   self.spread_width_pct,
            "dte_entry":          self.dte_entry,
            "hold_days":          self.hold_days,
            "profit_target_pct":  self.profit_target_pct,
            "stop_loss_pct":      self.stop_loss_pct,
            "position_size_pct":  self.position_size_pct,
            "commission_per_leg": self.commission_per_leg,
            "min_stock_price":    self.min_stock_price,
            "max_stocks":         self.max_stocks,
        }
