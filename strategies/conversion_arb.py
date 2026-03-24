"""
Conversion/Reversal Dividend Arbitrage Strategy.

True dividend arbitrage using put-call parity:

  Put-Call Parity:  C - P = S - K·e^(-rT) - PV(div)
  Rearranged:       D_implied = S - K·e^(-rT) + P - C

  If D_actual > D_implied → market is underpricing the dividend in options.
  Enter CONVERSION: Long stock + Long put + Short call (same strike, same expiry).
  Position is fully delta-neutral. Edge = D_actual - D_implied.
  Close all three legs after dividend is paid.

  Uses REAL option chain bid/ask from mkt.OptionSnapshot where available.
  Falls back to Black-Scholes pricing when chain data is missing.
"""

import numpy as np
import pandas as pd

from alan_trader.strategies.base import (
    BaseStrategy, BacktestResult, SignalResult, StrategyStatus, StrategyType,
)
from alan_trader.backtest.engine import bs_price
from alan_trader.risk.metrics import compute_all_metrics


def _implied_dividend(S: float, K: float, T: float, r: float,
                      call_price: float, put_price: float) -> float:
    """
    Implied dividend from put-call parity:  D = S - K·e^(-rT) + P - C
    """
    return S - K * np.exp(-r * T) + put_price - call_price


def _get_atm_pair(chain: pd.DataFrame, S: float, ex_date: pd.Timestamp
                  ) -> "tuple[dict|None, dict|None, float, float]":
    """
    From a snapshot chain find the nearest-ATM call+put pair whose expiry is
    AFTER ex_date.  Returns (call_row, put_row, strike, T_years).
    """
    if chain is None or chain.empty:
        return None, None, 0.0, 0.0

    chain = chain.copy()
    chain["expiration"] = pd.to_datetime(chain["expiration"])
    chain["strike"]     = pd.to_numeric(chain["strike"],     errors="coerce")
    chain["bid"]        = pd.to_numeric(chain["bid"],        errors="coerce")
    chain["ask"]        = pd.to_numeric(chain["ask"],        errors="coerce")
    chain["iv"]         = pd.to_numeric(chain["iv"],         errors="coerce")

    # Only use expiries after the ex-date (must capture the dividend)
    valid = chain[chain["expiration"] > ex_date].dropna(subset=["strike", "bid", "ask"])
    if valid.empty:
        return None, None, 0.0, 0.0

    # Pick nearest expiry
    exps       = sorted(valid["expiration"].unique())
    target_exp = exps[0]
    leg        = valid[valid["expiration"] == target_exp]
    T_years    = max((target_exp - ex_date).days + 7, 1) / 252  # rough DTE

    # ATM strike
    strikes    = leg["strike"].unique()
    atm_K      = float(strikes[np.argmin(np.abs(strikes - S))])

    call_rows = leg[(leg["strike"] == atm_K) & (leg["contract_type"].isin(["C", "call"]))]
    put_rows  = leg[(leg["strike"] == atm_K) & (leg["contract_type"].isin(["P", "put"]))]

    if call_rows.empty or put_rows.empty:
        return None, None, 0.0, 0.0

    return call_rows.iloc[0], put_rows.iloc[0], atm_K, T_years


class ConversionArbStrategy(BaseStrategy):
    name                 = "conversion_arb"
    display_name         = "Conversion Arb (Div)"
    strategy_type        = StrategyType.RULE_BASED
    status               = StrategyStatus.ACTIVE
    description          = (
        "True dividend arbitrage via put-call parity. "
        "Enters conversion (long stock + long put + short call) when real "
        "option chain prices imply a dividend below the actual dividend. "
        "Delta-neutral. Edge = actual div − implied div."
    )
    asset_class          = "equities_options"
    typical_holding_days = 5
    target_sharpe        = 1.1

    def __init__(
        self,
        entry_days_before_exdiv: int   = 3,
        min_edge_pct: float            = 5,     # bps — min edge vs stock price
        position_size_pct: float       = 0.15,
        risk_free_rate: float          = 0.045,
        commission_per_share: float    = 0.005,
        option_commission: float       = 0.65,
        slippage_pct: float            = 0.001,
    ):
        self.entry_days   = int(entry_days_before_exdiv)
        self.min_edge_pct = float(min_edge_pct) / 10_000   # bps → decimal
        self.pos_size_pct = float(position_size_pct)
        self.r            = float(risk_free_rate)
        self.comm_share   = float(commission_per_share)
        self.comm_opt     = float(option_commission)
        self.slippage     = float(slippage_pct)

    # ─────────────────────────────────────────────────────────────────────────
    # Signal
    # ─────────────────────────────────────────────────────────────────────────

    def generate_signal(self, market_snapshot: dict) -> SignalResult:
        days_to_ex  = market_snapshot.get("days_to_next_exdiv", 999)
        actual_div  = market_snapshot.get("next_div_per_share", 0.0)
        implied_div = market_snapshot.get("implied_dividend", 0.0)
        spot        = market_snapshot.get("price", 1.0)
        edge        = actual_div - implied_div

        if days_to_ex <= self.entry_days and edge > self.min_edge_pct * spot:
            confidence = min(1.0, edge / (0.005 * spot))
            return SignalResult(
                strategy_name=self.name, signal="BUY",
                confidence=confidence, position_size_pct=self.pos_size_pct,
                metadata={"days_to_exdiv": days_to_ex, "actual_div": actual_div,
                           "implied_div": round(implied_div, 4), "edge": round(edge, 4)},
            )
        return SignalResult(self.name, "HOLD", 0.0, 0.0,
                            metadata={"days_to_exdiv": days_to_ex, "edge": round(edge, 4)})

    # ─────────────────────────────────────────────────────────────────────────
    # Backtest
    # ─────────────────────────────────────────────────────────────────────────

    def backtest(
        self,
        price_data: pd.DataFrame,
        auxiliary_data: dict,
        starting_capital: float = 100_000,
        **kwargs,
    ) -> BacktestResult:

        # ── Apply UI params ───────────────────────────────────────────────────
        if "entry_days_before_exdiv" in kwargs:
            self.entry_days   = int(kwargs["entry_days_before_exdiv"])
        if "min_edge_pct" in kwargs:
            self.min_edge_pct = float(kwargs["min_edge_pct"]) / 10_000

        dividends = auxiliary_data.get("dividends", pd.DataFrame())
        if dividends.empty:
            return self._empty_result(starting_capital)

        price_data = price_data.copy()
        price_data.index = pd.to_datetime(price_data.index)
        all_dates = sorted(price_data.index)

        # ── Risk-free rate lookup (3M T-bill from macro) ──────────────────────
        rate3m_series = pd.Series(dtype=float)
        macro_df = auxiliary_data.get("macro", pd.DataFrame())
        if not macro_df.empty and "rate_3m" in macro_df.columns:
            _mac = macro_df.copy()
            _mac.index = pd.to_datetime(_mac.index)
            rate3m_series = _mac["rate_3m"].dropna() / 100   # % → decimal

        # ── DB engine for option chain lookups ────────────────────────────────
        _engine = None
        _ticker = getattr(self, "_ticker", None) or auxiliary_data.get("ticker")
        try:
            from alan_trader.db.client import get_engine, get_option_snapshots as _get_chain
            _engine = get_engine()
        except Exception:
            _get_chain = None

        capital     = float(starting_capital)
        trades_list = []

        for _, div_row in dividends.iterrows():
            ex_date    = pd.Timestamp(div_row["ex_date"])
            actual_div = float(div_row["div_per_share"])
            if actual_div <= 0:
                continue

            # ── Entry / exit dates ────────────────────────────────────────────
            pre_dates  = [d for d in all_dates if d < ex_date]
            post_dates = [d for d in all_dates if d >= ex_date]
            if len(pre_dates) < self.entry_days or len(post_dates) < 2:
                continue

            entry_date = pre_dates[-self.entry_days]
            exit_date  = post_dates[1]

            S_entry = float(price_data.loc[entry_date, "close"])
            S_exit  = float(price_data.loc[exit_date,  "close"])
            if S_entry <= 0 or S_exit <= 0:
                continue

            # ── Risk-free rate ────────────────────────────────────────────────
            r = self.r
            if len(rate3m_series):
                try:
                    _r = float(rate3m_series.asof(entry_date))
                    if np.isfinite(_r) and 0 < _r < 0.20:
                        r = _r
                except Exception:
                    pass

            # ── Load real option chain for entry date ─────────────────────────
            entry_chain = None
            if _engine is not None and _get_chain is not None and _ticker:
                try:
                    entry_chain = _get_chain(_engine, _ticker, entry_date.date())
                except Exception:
                    pass

            call_entry, put_entry, K, T = _get_atm_pair(entry_chain, S_entry, ex_date)

            if call_entry is None:
                import warnings
                warnings.warn(
                    f"ConversionArb: no option chain data for {_ticker} on {entry_date.date()} "
                    f"(ex-div {ex_date.date()}) — skipping dividend",
                    UserWarning, stacklevel=2,
                )
                continue

            # Entry prices — sell call at bid, buy put at ask
            call_bid_eff = float(call_entry["bid"]) * (1 - self.slippage)
            put_ask_eff  = float(put_entry["ask"])  * (1 + self.slippage)

            # IVs: store as decimal, discard if > 2.0 (200%) — data quality guard
            _civ = call_entry.get("iv"); _piv = put_entry.get("iv")
            iv_call = round(float(_civ), 4) if pd.notna(_civ) and 0 < float(_civ) <= 2.0 else None
            iv_put  = round(float(_piv), 4) if pd.notna(_piv) and 0 < float(_piv) <= 2.0 else None

            # ── Implied dividend from real market prices ───────────────────────
            d_impl = _implied_dividend(S_entry, K, T, r, call_bid_eff, put_ask_eff)
            edge   = actual_div - d_impl

            # ── Position sizing ───────────────────────────────────────────────
            budget      = capital * self.pos_size_pct
            n_shares    = max(100, (int(budget / S_entry) // 100) * 100)
            n_contracts = n_shares // 100

            comm_total = (n_shares * self.comm_share * 2
                          + n_contracts * self.comm_opt * 4)

            if edge * n_shares < comm_total + self.min_edge_pct * S_entry * n_shares:
                continue

            # ── Exit prices ───────────────────────────────────────────────────
            # Try real chain on exit date; fall back to BS
            exit_chain = None
            if _engine is not None and _get_chain is not None and _ticker:
                try:
                    exit_chain = _get_chain(_engine, _ticker, exit_date.date())
                except Exception:
                    pass

            call_exit_r, put_exit_r, _, _ = _get_atm_pair(exit_chain, S_exit, ex_date)

            if call_exit_r is None:
                import warnings
                warnings.warn(
                    f"ConversionArb: no exit chain for {_ticker} on {exit_date.date()} — skipping",
                    UserWarning, stacklevel=2,
                )
                continue
            # Buy back call at ask, sell put at bid
            call_ask_exit = float(call_exit_r["ask"]) * (1 + self.slippage)
            put_bid_exit  = float(put_exit_r["bid"])  * (1 - self.slippage)

            # ── P&L ──────────────────────────────────────────────────────────
            hold_days    = (exit_date - entry_date).days
            carry_cost   = S_entry * r * (hold_days / 365) * n_shares

            stock_pnl    = (S_exit - S_entry) * n_shares
            div_received = actual_div * n_shares
            put_pnl      = (put_bid_exit  - put_ask_eff)  * n_contracts * 100
            call_pnl     = (call_bid_eff  - call_ask_exit) * n_contracts * 100
            net_pnl      = stock_pnl + div_received + put_pnl + call_pnl - carry_cost - comm_total

            # Net capital deployed: long stock + long put - short call premium received
            total_in     = (S_entry * n_shares
                            + put_ask_eff  * n_contracts * 100
                            - call_bid_eff * n_contracts * 100)
            return_pct   = net_pnl / total_in if total_in > 0 else 0.0

            capital += net_pnl

            trades_list.append({
                "entry_date":    entry_date.date(),
                "exit_date":     exit_date.date(),
                "spread_type":   "conversion",
                "strike":        round(K, 2),
                "spot":          round(S_entry, 2),
                "entry_price":   round(S_entry, 2),
                "exit_price":    round(S_exit, 2),
                "dte":           round(T * 252),
                "actual_div":    round(actual_div, 4),
                "implied_div":   round(d_impl, 4),
                "edge":          round(edge, 4),
                "contracts":     n_contracts,
                "iv_call":       round(iv_call, 2) if iv_call else None,
                "iv_put":        round(iv_put,  2) if iv_put  else None,
                "risk_free_rate": round(r * 100, 3),
                "call_entry_px":  round(call_bid_eff, 4),    # received for selling call
                "put_entry_px":   round(put_ask_eff, 4),     # paid for buying put
                "call_exit_px":   round(call_ask_exit, 4),   # paid to close call
                "put_exit_px":    round(put_bid_exit, 4),    # received to close put
                "stock_pnl":     round(stock_pnl, 2),
                "div_received":  round(div_received, 2),
                "put_pnl":       round(put_pnl, 2),
                "call_pnl":      round(call_pnl, 2),
                "carry_cost":    round(carry_cost, 2),
                "commissions":   round(comm_total, 2),
                "total_in":      round(total_in, 2),
                "total_out":     round(total_in + net_pnl, 2),
                "return_pct":    round(return_pct, 4),
                "pnl":           round(net_pnl, 2),
                "exit_reason":   "post_exdiv",
            })

        if not trades_list:
            return self._empty_result(starting_capital)

        trades_df = pd.DataFrame(trades_list)

        # ── Daily equity curve ────────────────────────────────────────────────
        eq = pd.Series(starting_capital, index=all_dates, dtype=float)
        for _, tr in trades_df.iterrows():
            eq[eq.index >= pd.Timestamp(tr["exit_date"])] += tr["pnl"]

        equity    = eq.copy()
        equity.index = pd.to_datetime(equity.index)
        daily_ret = equity.pct_change().dropna()

        vix_df = auxiliary_data.get("vix", pd.DataFrame())
        bench  = None
        if not vix_df.empty:
            bench = price_data["close"].pct_change().dropna()
            bench.index = pd.to_datetime(bench.index)
            bench = bench.reindex(equity.index).dropna()

        metrics = compute_all_metrics(
            equity_curve=equity, trades_df=trades_df, benchmark_returns=bench,
        )
        return BacktestResult(
            strategy_name=self.name, equity_curve=equity,
            daily_returns=daily_ret, trades=trades_df,
            metrics=metrics, params=self.get_params(),
        )

    # ─────────────────────────────────────────────────────────────────────────

    def get_backtest_ui_params(self) -> list:
        return [
            {"key": "entry_days_before_exdiv", "label": "Days before ex-div", "type": "slider",
             "min": 1, "max": 7, "default": 3, "step": 1, "col": 0},
            {"key": "min_edge_pct", "label": "Min edge (bps)", "type": "slider",
             "min": 1, "max": 50, "default": 5, "step": 1, "col": 1},
        ]

    def get_params(self) -> dict:
        return {
            "entry_days_before_exdiv": self.entry_days,
            "min_edge_pct":            self.min_edge_pct * 10_000,
            "position_size_pct":       self.pos_size_pct,
            "risk_free_rate":          self.r,
        }

    def _empty_result(self, capital: float) -> BacktestResult:
        eq = pd.Series([capital], dtype=float)
        return BacktestResult(
            strategy_name=self.name, equity_curve=eq,
            daily_returns=pd.Series(dtype=float), trades=pd.DataFrame(),
            metrics={}, params=self.get_params(),
        )
