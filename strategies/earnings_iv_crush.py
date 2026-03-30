"""
Earnings IV Crush Strategy.

Edge: Options consistently overprice post-earnings uncertainty. The implied move
(derived from ATM straddle price) exceeds the actual realized move by 20-40% on average.
Selling a defined-risk iron condor 1 day before earnings and closing at the next-day
open captures the IV collapse as pure volatility premium, with wings capping the max loss.

Trade structure:
  - Short ATM call  (ATM strike)
  - Short ATM put   (ATM strike)
  - Long OTM call   (ATM + wing_width_pct * spot)  — caps upside loss
  - Long OTM put    (ATM - wing_width_pct * spot)  — caps downside loss

Entry: 1 trading day before earnings
Exit: open of next trading day (earnings day), after IV crushes

auxiliary_data contract
-----------------------
  "earnings"     : DataFrame with [date, ticker, eps_actual, eps_estimate, implied_move_pct]
  "vix"          : VIX price DataFrame (date-indexed, "close" column)
  "rate10y"      : 10-year rates DataFrame (date-indexed, "close" column)
  "stock_prices" : dict of {ticker_symbol: OHLCV_DataFrame} — required per-ticker data.
                   Each DataFrame should be date-indexed with at least a "close" column.
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


class EarningsIVCrushStrategy(BaseStrategy):
    name                 = "earnings_iv_crush"
    display_name         = "Earnings IV Crush"
    strategy_type        = StrategyType.RULE_BASED
    status               = StrategyStatus.ACTIVE
    description          = (
        "Sells defined-risk iron condors 1 day before earnings on the REPORTING STOCK. "
        "Captures the systematic overpricing of post-earnings uncertainty (implied move "
        "consistently exceeds actual move by 20-40%). Closes at next-day open after IV collapse."
    )
    asset_class          = "equities_options"
    typical_holding_days = 1
    target_sharpe        = 1.7

    def __init__(
        self,
        min_implied_move:     float = 0.04,   # min 4% implied move to trade
        min_iv_ratio:         float = 1.2,    # implied / historical move ratio >= 1.2
        wing_width_pct:       float = 0.08,   # wings at ±8% from ATM
        dte_entry:            int   = 1,      # enter 1 day before earnings
        profit_target_pct:    float = 0.50,   # close at 50% of max credit
        position_size_pct:    float = 0.03,   # 3% of portfolio per trade
        commission_per_leg:   float = 0.65,
        iv_crush_assumed:     float = 0.40,   # 40% IV drop post-earnings for simulation
        min_stock_price:      float = 10.0,   # skip penny stocks below this price
        max_stocks:           int   = 20,     # cap universe size to avoid overfitting
    ):
        self.min_implied_move   = min_implied_move
        self.min_iv_ratio       = min_iv_ratio
        self.wing_width_pct     = wing_width_pct
        self.dte_entry          = dte_entry
        self.profit_target_pct  = profit_target_pct
        self.position_size_pct  = position_size_pct
        self.commission_per_leg = commission_per_leg
        self.iv_crush_assumed   = iv_crush_assumed
        self.min_stock_price    = min_stock_price
        self.max_stocks         = max_stocks

    # ── Signal (live) ──────────────────────────────────────────────────────

    def generate_signal(self, market_snapshot: dict) -> SignalResult:
        """
        Live signal: look for upcoming earnings events in market_snapshot.
        Expects market_snapshot to contain:
          - "earnings": dict with keys "earnings_date", "implied_move_pct", "historical_move_pct"
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
                metadata={"reason": "no upcoming earnings event"},
            )

        implied_move   = float(earnings.get("implied_move_pct", 0.0))
        historical_move = float(earnings.get("historical_move_pct", implied_move / self.min_iv_ratio))
        iv_ratio       = implied_move / historical_move if historical_move > 0 else 0.0

        if implied_move < self.min_implied_move:
            return SignalResult(
                strategy_name=self.name,
                signal="HOLD",
                confidence=0.0,
                position_size_pct=0.0,
                metadata={
                    "reason": f"implied_move {implied_move:.1%} < min {self.min_implied_move:.1%}",
                    "implied_move_pct": implied_move,
                },
            )

        if iv_ratio < self.min_iv_ratio:
            return SignalResult(
                strategy_name=self.name,
                signal="HOLD",
                confidence=0.0,
                position_size_pct=0.0,
                metadata={
                    "reason": f"IV ratio {iv_ratio:.2f} < min {self.min_iv_ratio:.2f}",
                    "iv_ratio": iv_ratio,
                },
            )

        confidence = min(0.95, 0.5 + (iv_ratio - self.min_iv_ratio) * 0.5
                         + (implied_move - self.min_implied_move) * 2.0)

        return SignalResult(
            strategy_name=self.name,
            signal="SELL",   # "SELL" = enter short-premium iron condor
            confidence=round(confidence, 3),
            position_size_pct=self.position_size_pct,
            metadata={
                "trade":            "iron_condor",
                "implied_move_pct": round(implied_move, 4),
                "historical_move_pct": round(historical_move, 4),
                "iv_ratio":         round(iv_ratio, 3),
                "earnings_date":    earnings.get("earnings_date"),
                "ticker":           earnings.get("ticker"),
            },
        )

    # ── Backtest ───────────────────────────────────────────────────────────

    def backtest(
        self,
        price_data: pd.DataFrame,
        auxiliary_data: dict,
        starting_capital:    float = 100_000,
        min_implied_move:    float | None = None,
        min_iv_ratio:        float | None = None,
        wing_width_pct:      float | None = None,
        profit_target_pct:   float | None = None,
        position_size_pct:   float | None = None,
        iv_crush_assumed:    float | None = None,
        **kwargs,
    ) -> BacktestResult:

        # Resolve params (UI overrides take priority)
        min_imp   = min_implied_move  if min_implied_move  is not None else self.min_implied_move
        min_ivr   = min_iv_ratio      if min_iv_ratio      is not None else self.min_iv_ratio
        wing_w    = wing_width_pct    if wing_width_pct    is not None else self.wing_width_pct
        pt_pct    = profit_target_pct if profit_target_pct is not None else self.profit_target_pct
        pos_size  = position_size_pct if position_size_pct is not None else self.position_size_pct
        crush     = iv_crush_assumed  if iv_crush_assumed  is not None else self.iv_crush_assumed
        min_price = self.min_stock_price
        max_stk   = self.max_stocks

        # UI sliders may send values as integers (percentages × 100)
        if min_imp  >= 1: min_imp  /= 100
        if min_ivr  >= 10: min_ivr /= 10
        if wing_w   >= 1: wing_w   /= 100
        if pt_pct   >= 1: pt_pct   /= 100
        if pos_size >= 1: pos_size /= 100
        if crush    >= 1: crush    /= 100

        price_data = price_data.copy()
        price_data.index = pd.to_datetime(price_data.index)

        # ── Data validation ────────────────────────────────────────────────
        earnings_df = auxiliary_data.get("earnings", pd.DataFrame())
        if isinstance(earnings_df, pd.DataFrame) and earnings_df.empty:
            raise ValueError(
                "No earnings data found in auxiliary_data['earnings'].\n\n"
                "This strategy requires a DataFrame with columns: "
                "[date, ticker, eps_actual, eps_estimate, implied_move_pct].\n"
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

        portfolio_close     = price_data["close"]
        trading_dates = list(price_data.index)

        # ── Earnings DataFrame normalisation ───────────────────────────────
        if isinstance(earnings_df, pd.DataFrame):
            edf = earnings_df.copy()
        else:
            raise ValueError("auxiliary_data['earnings'] must be a pandas DataFrame.")

        # Normalise date column
        date_col = None
        for col in ["date", "earnings_date", "report_date"]:
            if col in edf.columns:
                date_col = col
                break
        if date_col is None:
            if not edf.index.name and hasattr(edf.index, "dtype"):
                edf = edf.reset_index().rename(columns={"index": "date"})
                date_col = "date"
            else:
                raise ValueError(
                    "earnings DataFrame must have a 'date' column (or 'earnings_date' / 'report_date')."
                )
        edf[date_col] = pd.to_datetime(edf[date_col])
        edf = edf.sort_values(date_col)

        # Cap universe to max_stocks (first N unique tickers in chronological order)
        if "ticker" in edf.columns:
            unique_tickers = list(dict.fromkeys(edf["ticker"].dropna().tolist()))
            if len(unique_tickers) > max_stk:
                allowed_tickers = set(unique_tickers[:max_stk])
                edf = edf[edf["ticker"].isin(allowed_tickers)]

        # Build a quick lookup: earnings_date → row (one per date; last wins on collision)
        earnings_by_date: dict[pd.Timestamp, pd.Series] = {
            row[date_col]: row for _, row in edf.iterrows()
        }

        # Pre-index per-ticker close series for O(1) lookup
        ticker_close_cache: dict[str, pd.Series] = {}
        for tkr, tkr_df in stock_prices.items():
            try:
                df_copy = tkr_df.copy()
                df_copy.index = pd.to_datetime(df_copy.index)
                ticker_close_cache[str(tkr).upper()] = df_copy["close"]
            except Exception:
                pass  # skip malformed entries

        # ── Historical move calculation helper ─────────────────────────────

        def _historical_move(as_of_date: pd.Timestamp, ticker: str, n_quarters: int = 8) -> float:
            """Rolling 8-quarter average of |post-earnings return| for the stock."""
            past = edf[edf[date_col] < as_of_date]
            if "ticker" in edf.columns:
                past = past[past["ticker"] == ticker]
            past = past.tail(n_quarters)
            if past.empty:
                return 0.03  # 3% fallback

            close_series = ticker_close_cache.get(ticker.upper())
            if close_series is None:
                return 0.03
            stock_returns = close_series.pct_change()

            moves = []
            for _, row in past.iterrows():
                ed = row[date_col]
                future = stock_returns[stock_returns.index > ed]
                if not future.empty:
                    moves.append(abs(float(future.iloc[0])))
            return float(np.mean(moves)) if moves else 0.03

        # ── Walk-forward simulation ────────────────────────────────────────
        capital     = float(starting_capital)
        equity_list = []
        trades_list = []

        # Pre-build date→position mapping for O(1) lookup
        date_to_idx = {d: i for i, d in enumerate(trading_dates)}

        processed_earnings: set = set()   # avoid double-entering same event

        for i, dt in enumerate(trading_dates):
            # Check: is the NEXT trading day an earnings event?
            if i + 1 < len(trading_dates):
                next_dt = trading_dates[i + 1]
                if next_dt in earnings_by_date and next_dt not in processed_earnings:
                    row    = earnings_by_date[next_dt]
                    ticker = str(row.get("ticker", "")).upper()

                    # ── Resolve spot price for this stock ──────────────────
                    stock_df = stock_prices.get(ticker.upper())
                    if stock_df is None or (hasattr(stock_df, "empty") and stock_df.empty):
                        logger.debug("earnings_iv_crush: no price data for %s — skipping", ticker)
                        equity_list.append(capital)
                        continue

                    stock_close = ticker_close_cache.get(ticker)
                    if stock_close is None:
                        logger.debug("earnings_iv_crush: no price data for %s — skipping", ticker)
                        equity_list.append(capital)
                        continue

                    # Get spot on entry day (day i)
                    if dt in stock_close.index:
                        spot = float(stock_close.loc[dt])
                    else:
                        # Nearest prior close
                        prior = stock_close[stock_close.index <= dt]
                        if prior.empty:
                            logger.debug("earnings_iv_crush: no price data for %s on %s — skipping", ticker, dt.date())
                            equity_list.append(capital)
                            continue
                        spot = float(prior.iloc[-1])

                    # Skip penny stocks
                    if spot < min_price:
                        equity_list.append(capital)
                        continue

                    # ── Resolve IV: real options chain preferred, else raw VIX ──
                    r = float(rate.iloc[i])
                    chain_df = options_chains.get(ticker, {}).get(dt.date())
                    if chain_df is not None and not chain_df.empty and "iv" in chain_df.columns:
                        iv_proxy = float(chain_df["iv"].dropna().median())
                    else:
                        iv_proxy = float(vix.iloc[i]) / 100.0

                    # Implied move: use column if available, else straddle approximation
                    if "implied_move_pct" in row and not pd.isna(row["implied_move_pct"]):
                        implied_move = float(row["implied_move_pct"])
                    else:
                        # Approximate from BS: ATM straddle ≈ 0.8 * sigma * sqrt(T)
                        T_1d = 1.0 / 252
                        c_atm = bs_price(spot, spot, T_1d, r, iv_proxy, "call")
                        p_atm = bs_price(spot, spot, T_1d, r, iv_proxy, "put")
                        implied_move = (c_atm + p_atm) / spot

                    hist_move = _historical_move(dt, ticker)
                    iv_ratio  = implied_move / hist_move if hist_move > 0 else 0.0

                    if implied_move >= min_imp and iv_ratio >= min_ivr:
                        processed_earnings.add(next_dt)

                        # ── Price the iron condor at entry ─────────────────
                        # Entry: day i (day before earnings), 1 DTE
                        T_entry = 1.0 / 252

                        # ATM strike: nearest $1 for stocks ≤$500, nearest $5 for >$500
                        if spot <= 500:
                            atm_k = round(spot / 1) * 1
                        else:
                            atm_k = round(spot / 5) * 5

                        wing_pts  = spot * wing_w
                        call_wing = atm_k + wing_pts
                        put_wing  = atm_k - wing_pts

                        # Short strangle credit
                        short_call_price = bs_price(spot, atm_k,    T_entry, r, iv_proxy, "call")
                        short_put_price  = bs_price(spot, atm_k,    T_entry, r, iv_proxy, "put")
                        # Long wing debit
                        long_call_price  = bs_price(spot, call_wing, T_entry, r, iv_proxy, "call")
                        long_put_price   = bs_price(spot, put_wing,  T_entry, r, iv_proxy, "put")

                        net_credit_entry = (short_call_price + short_put_price
                                            - long_call_price  - long_put_price)

                        if net_credit_entry <= 0:
                            equity_list.append(capital)
                            continue  # no credit available — skip

                        # ── Price at exit (next day, after IV crush) ───────
                        stock_close_next = stock_close
                        if next_dt in stock_close_next.index:
                            spot_exit = float(stock_close_next.loc[next_dt])
                        else:
                            spot_exit = spot  # no data — assume unchanged

                        iv_exit = iv_proxy * (1.0 - crush)
                        T_exit  = max(0, 0.5 / 252)   # ~30min after open ≈ half day

                        sc_exit = bs_price(spot_exit, atm_k,    T_exit, r, iv_exit, "call")
                        sp_exit = bs_price(spot_exit, atm_k,    T_exit, r, iv_exit, "put")
                        lc_exit = bs_price(spot_exit, call_wing, T_exit, r, iv_exit, "call")
                        lp_exit = bs_price(spot_exit, put_wing,  T_exit, r, iv_exit, "put")

                        cost_to_close = max(0, sc_exit + sp_exit - lc_exit - lp_exit)

                        # P&L per share
                        pnl_per_share = net_credit_entry - cost_to_close

                        # Position sizing
                        budget    = capital * pos_size
                        max_loss_per_share = max(wing_pts - net_credit_entry, 0.01)
                        contracts = max(1, int(budget / (max_loss_per_share * 100)))

                        commissions = contracts * 4 * self.commission_per_leg * 2  # 4 legs × entry + exit

                        trade_pnl = pnl_per_share * contracts * 100 - commissions

                        capital += trade_pnl

                        trades_list.append({
                            "entry_date":        dt.date(),
                            "exit_date":         next_dt.date(),
                            "spread_type":       "iron_condor",
                            "ticker":            ticker,
                            "spot_entry":        round(spot, 2),
                            "spot_exit":         round(spot_exit, 2),
                            "atm_strike":        round(atm_k, 2),
                            "call_wing":         round(call_wing, 2),
                            "put_wing":          round(put_wing, 2),
                            "net_credit":        round(net_credit_entry, 4),
                            "cost_to_close":     round(cost_to_close, 4),
                            "contracts":         contracts,
                            "implied_move_pct":  round(implied_move, 4),
                            "iv_ratio":          round(iv_ratio, 3),
                            "pnl":               round(trade_pnl, 2),
                            "exit_reason":       "iv_crush_exit",
                        })

            equity_list.append(capital)

        # ── Build outputs ──────────────────────────────────────────────────
        equity    = pd.Series(equity_list, index=trading_dates, dtype=float)
        daily_ret = equity.pct_change().dropna()
        bh_ret    = portfolio_close.pct_change().reindex(equity.index).dropna()

        trades_df = pd.DataFrame(trades_list) if trades_list else pd.DataFrame(
            columns=["entry_date", "exit_date", "spread_type", "ticker",
                     "spot_entry", "spot_exit", "atm_strike", "call_wing", "put_wing",
                     "net_credit", "cost_to_close", "contracts",
                     "implied_move_pct", "iv_ratio", "pnl", "exit_reason"]
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
                "min_implied_move":  min_imp,
                "min_iv_ratio":      min_ivr,
                "wing_width_pct":    wing_w,
                "profit_target_pct": pt_pct,
                "position_size_pct": pos_size,
                "iv_crush_assumed":  crush,
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
                "key": "min_implied_move",
                "label": "Min implied move (%)",
                "type": "slider", "min": 2, "max": 10, "default": 4, "step": 1,
                "col": 0, "row": 0,
                "help": "Minimum ATM straddle-implied move (% of spot) needed to enter. Lower = more trades.",
            },
            {
                "key": "min_iv_ratio",
                "label": "Min implied/historical ratio",
                "type": "select_slider",
                "options": [1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.7, 2.0],
                "default": 1.2,
                "col": 1, "row": 0,
                "help": "Implied move must exceed historical average by this factor. Higher = more selective.",
            },
            {
                "key": "wing_width_pct",
                "label": "Wing width (% of spot)",
                "type": "slider", "min": 4, "max": 15, "default": 8, "step": 1,
                "col": 2, "row": 0,
                "help": "OTM wing distance as % of spot. Wider = more credit but more exposure.",
            },
            {
                "key": "iv_crush_assumed",
                "label": "IV crush assumed (%)",
                "type": "slider", "min": 20, "max": 60, "default": 40, "step": 5,
                "col": 0, "row": 1,
                "help": "Expected % drop in IV at next-day open. Higher = more optimistic P&L simulation.",
            },
            {
                "key": "profit_target_pct",
                "label": "Profit target (% of credit)",
                "type": "slider", "min": 25, "max": 90, "default": 50, "step": 5,
                "col": 1, "row": 1,
                "help": "Close when unrealised gain reaches this fraction of max credit received.",
            },
            {
                "key": "position_size_pct",
                "label": "Position size (% of capital)",
                "type": "slider", "min": 1, "max": 10, "default": 3, "step": 1,
                "col": 2, "row": 1,
                "help": "Capital at risk per trade as % of portfolio. Max loss = wing width − credit.",
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
            "min_implied_move":   self.min_implied_move,
            "min_iv_ratio":       self.min_iv_ratio,
            "wing_width_pct":     self.wing_width_pct,
            "dte_entry":          self.dte_entry,
            "profit_target_pct":  self.profit_target_pct,
            "position_size_pct":  self.position_size_pct,
            "commission_per_leg": self.commission_per_leg,
            "iv_crush_assumed":   self.iv_crush_assumed,
            "min_stock_price":    self.min_stock_price,
            "max_stocks":         self.max_stocks,
        }
