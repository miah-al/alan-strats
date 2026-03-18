"""
Backtesting engine for SPY options spread strategy.

How it works:
1. Walk-forward through history (avoids look-ahead bias).
2. On each bar, use model signal to optionally enter a spread.
3. Simulate option P&L using Black-Scholes approximation
   (or real historical options data from Polygon if available).
4. Track portfolio equity, drawdown, Sharpe, win rate.
"""

import logging
from dataclasses import dataclass
from datetime import date
from typing import Optional

import numpy as np
import pandas as pd
from scipy.stats import norm

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Black-Scholes option pricing (for simulating option prices in backtest)
# ---------------------------------------------------------------------------

def bs_price(S: float, K: float, T: float, r: float, sigma: float, option_type: str) -> float:
    """Black-Scholes option price. T in years."""
    if T <= 0 or sigma <= 0:
        intrinsic = max(0, S - K) if option_type == "call" else max(0, K - S)
        return intrinsic
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    if option_type == "call":
        return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    else:
        return K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def spread_value(
    S: float,
    long_K: float,
    short_K: float,
    T: float,
    r: float,
    iv: float,
    spread_type: str,
) -> float:
    """Current value of a vertical spread."""
    if spread_type in ("bull_call",):
        return bs_price(S, long_K, T, r, iv, "call") - bs_price(S, short_K, T, r, iv, "call")
    elif spread_type in ("bear_put",):
        return bs_price(S, long_K, T, r, iv, "put") - bs_price(S, short_K, T, r, iv, "put")
    elif spread_type in ("bull_put",):
        # Credit spread: we received net_credit; current value is cost to close
        return bs_price(S, short_K, T, r, iv, "put") - bs_price(S, long_K, T, r, iv, "put")
    elif spread_type in ("bear_call",):
        return bs_price(S, short_K, T, r, iv, "call") - bs_price(S, long_K, T, r, iv, "call")
    return 0.0


# ---------------------------------------------------------------------------
# Backtest trade record
# ---------------------------------------------------------------------------

@dataclass
class Trade:
    entry_date: date
    exit_date: Optional[date]
    spread_type: str
    long_strike: float
    short_strike: float
    expiration: str
    entry_cost: float           # net debit paid (positive) or -net_credit (negative) per share
    long_leg_price: float       # BS price of long leg at entry
    short_leg_price: float      # BS price of short leg at entry
    exit_value: float           # value when closed, per share
    contracts: int
    pnl: float                  # total P&L in dollars
    exit_reason: str            # 'expiry', 'take_profit', 'stop_loss', 'time_exit'
    predicted_spread_price: float = 0.0
    is_credit: bool = False     # True for credit spreads (bull_put, bear_call, iron_condor, short_strangle)
    net_credit: float = 0.0    # net credit received per share (credit spreads only)
    call_short_strike: float = 0.0  # iron_condor: sold call; call_butterfly: mid strike
    call_long_strike: float = 0.0   # iron_condor: bought call; call_butterfly: upper strike


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------

class BacktestEngine:
    """
    Walk-forward backtest. Needs:
    - feature_df:  output of build_feature_matrix (with 'close', 'vix', 'rate_10y', 'fwd_ret')
    - probas:      (N, 3) model predictions aligned to feature_df rows (after seq_len offset)
    - starting_capital: initial portfolio value
    """

    def __init__(
        self,
        starting_capital: float = 100_000,
        position_size_pct: float = 0.05,
        max_loss_pct: float = 0.02,
        take_profit_pct: float = 0.60,   # close at 60% of max profit
        stop_loss_pct: float = 1.0,      # stop at 100% of max loss
        hold_days: int = 5,
        min_confidence: float = 0.45,
        otm_pct: float = 0.0,
        spread_type: str = "bull_call",
        commission_per_contract: float = 0.65,
        bid_ask_slippage: float = 0.05,
    ):
        self.capital = starting_capital
        self.starting_capital = starting_capital
        self.pos_size_pct = position_size_pct
        self.max_loss_pct = max_loss_pct
        self.take_profit_pct = take_profit_pct
        self.stop_loss_pct = stop_loss_pct
        self.hold_days = hold_days
        self.min_conf = min_confidence
        self.otm_pct = otm_pct
        self.spread_type = spread_type
        self.commission = commission_per_contract
        self.slippage = bid_ask_slippage

        self.trades: list[Trade] = []
        self.equity_curve: list[dict] = []
        self.open_trade: Optional[Trade] = None
        self.days_in_trade: int = 0

    def run(
        self,
        feature_df: pd.DataFrame,
        probas: np.ndarray,
        seq_len: int = 30,
        spread_width: float = 5.0,
        price_predictions: np.ndarray = None,
    ) -> pd.DataFrame:
        """
        Run the backtest. Returns equity curve DataFrame.

        feature_df rows are aligned so that row i corresponds to probas[i - seq_len].
        We iterate from seq_len onward.
        """
        # Align: probas[i] predicts forward return starting at feature_df.iloc[seq_len + i]
        idx_start = seq_len
        df = feature_df.iloc[idx_start:].reset_index()

        assert len(probas) == len(df), (
            f"probas length {len(probas)} != df length {len(df)}"
        )

        for i, row in df.iterrows():
            current_date = row["date"] if "date" in row else row.get("index")
            spy = row["close"]
            vix = row.get("vix", 18.0)
            rate = row.get("rate_10y", 0.045)
            proba = probas[i]
            pred_price = float(price_predictions[i]) if price_predictions is not None else 0.0

            # --- Manage open trade ---
            if self.open_trade is not None:
                self.days_in_trade += 1
                pnl = self._mark_trade(self.open_trade, spy, vix, rate, current_date)
                t = self.open_trade
                c = t.contracts
                if t.spread_type in ("bull_call", "bear_put"):
                    max_profit_dollars = (spread_width - t.entry_cost) * c * 100
                    max_loss_dollars   = t.entry_cost * c * 100
                elif t.spread_type == "long_straddle":
                    max_profit_dollars = t.entry_cost * c * 100 * 5  # soft take-profit at 5× cost
                    max_loss_dollars   = t.entry_cost * c * 100
                elif t.spread_type == "call_butterfly":
                    max_profit_dollars = (spread_width - t.entry_cost) * c * 100
                    max_loss_dollars   = t.entry_cost * c * 100
                elif t.spread_type == "short_strangle":
                    max_profit_dollars = t.net_credit * c * 100
                    max_loss_dollars   = t.net_credit * 3 * c * 100
                else:  # credit verticals + iron_condor
                    max_profit_dollars = t.net_credit * c * 100
                    max_loss_dollars   = (spread_width - t.net_credit) * c * 100

                if max_profit_dollars > 0 and pnl >= max_profit_dollars * self.take_profit_pct:
                    self._close_trade(self.open_trade, spy, vix, rate, current_date, "take_profit")
                elif max_loss_dollars > 0 and pnl <= -max_loss_dollars * self.stop_loss_pct:
                    self._close_trade(self.open_trade, spy, vix, rate, current_date, "stop_loss")
                elif self.days_in_trade >= self.hold_days:
                    self._close_trade(self.open_trade, spy, vix, rate, current_date, "time_exit")

            # --- Enter new trade if no open position ---
            if self.open_trade is None:
                signal_class = int(np.argmax(proba))
                confidence = proba[signal_class]

                if confidence >= self.min_conf and signal_class == 2:  # label=2 = ENTER
                    expiry_days = 30
                    T_entry     = expiry_days / 252
                    iv          = vix / 100
                    otm_mult    = self.otm_pct / 100
                    stype       = self.spread_type
                    is_credit   = False
                    net_credit  = 0.0
                    call_short_strike = 0.0
                    call_long_strike  = 0.0
                    long_k = short_k  = 0.0
                    long_leg_price = short_leg_price = 0.0
                    entry_cost = 0.0

                    if stype == "bull_call":
                        long_k  = round(spy * (1 + otm_mult) / 5) * 5
                        short_k = long_k + spread_width
                        el = bs_price(spy, long_k,  T_entry, rate, iv, "call")
                        es = bs_price(spy, short_k, T_entry, rate, iv, "call")
                        entry_cost = el - es + self.slippage
                        long_leg_price, short_leg_price = round(el, 4), round(es, 4)

                    elif stype == "bear_put":
                        long_k  = round(spy * (1 - otm_mult) / 5) * 5
                        short_k = long_k - spread_width
                        el = bs_price(spy, long_k,  T_entry, rate, iv, "put")
                        es = bs_price(spy, short_k, T_entry, rate, iv, "put")
                        entry_cost = el - es + self.slippage
                        long_leg_price, short_leg_price = round(el, 4), round(es, 4)

                    elif stype == "bull_put":
                        # Credit: sell higher put, buy lower put
                        short_k = round(spy * (1 - otm_mult) / 5) * 5
                        long_k  = short_k - spread_width
                        es = bs_price(spy, short_k, T_entry, rate, iv, "put")
                        el = bs_price(spy, long_k,  T_entry, rate, iv, "put")
                        net_credit = es - el - self.slippage
                        entry_cost = -net_credit
                        is_credit  = True
                        long_leg_price, short_leg_price = round(el, 4), round(es, 4)

                    elif stype == "bear_call":
                        # Credit: sell lower call, buy higher call
                        short_k = round(spy * (1 + otm_mult) / 5) * 5
                        long_k  = short_k + spread_width
                        es = bs_price(spy, short_k, T_entry, rate, iv, "call")
                        el = bs_price(spy, long_k,  T_entry, rate, iv, "call")
                        net_credit = es - el - self.slippage
                        entry_cost = -net_credit
                        is_credit  = True
                        long_leg_price, short_leg_price = round(el, 4), round(es, 4)

                    elif stype == "iron_condor":
                        # 4-leg: put credit spread (below) + call credit spread (above)
                        ps_k = round(spy * (1 - otm_mult) / 5) * 5   # sold put
                        pl_k = ps_k - spread_width                     # bought put
                        cs_k = round(spy * (1 + otm_mult) / 5) * 5   # sold call
                        cl_k = cs_k + spread_width                     # bought call
                        pc = (bs_price(spy, ps_k, T_entry, rate, iv, "put")
                              - bs_price(spy, pl_k, T_entry, rate, iv, "put"))
                        cc = (bs_price(spy, cs_k, T_entry, rate, iv, "call")
                              - bs_price(spy, cl_k, T_entry, rate, iv, "call"))
                        net_credit = pc + cc - 2 * self.slippage
                        entry_cost = -net_credit
                        is_credit  = True
                        long_k, short_k = pl_k, ps_k
                        call_short_strike, call_long_strike = cs_k, cl_k
                        long_leg_price  = round(bs_price(spy, pl_k, T_entry, rate, iv, "put"), 4)
                        short_leg_price = round(bs_price(spy, ps_k, T_entry, rate, iv, "put"), 4)

                    elif stype == "long_straddle":
                        # Debit: buy ATM call + ATM put
                        K = round(spy / 5) * 5
                        long_k = short_k = K
                        cp = bs_price(spy, K, T_entry, rate, iv, "call")
                        pp = bs_price(spy, K, T_entry, rate, iv, "put")
                        entry_cost = cp + pp + 2 * self.slippage
                        long_leg_price, short_leg_price = round(cp, 4), round(pp, 4)

                    elif stype == "short_strangle":
                        # Credit: sell OTM put + OTM call
                        put_k  = round(spy * (1 - max(otm_mult, 0.05)) / 5) * 5
                        call_k = round(spy * (1 + max(otm_mult, 0.05)) / 5) * 5
                        pp = bs_price(spy, put_k,  T_entry, rate, iv, "put")
                        cp = bs_price(spy, call_k, T_entry, rate, iv, "call")
                        net_credit = pp + cp - 2 * self.slippage
                        entry_cost = -net_credit
                        is_credit  = True
                        long_k, short_k = put_k, call_k
                        long_leg_price, short_leg_price = round(pp, 4), round(cp, 4)

                    elif stype == "call_butterfly":
                        # Debit: buy lower call + sell 2 mid calls + buy upper call
                        mid_k   = round(spy / 5) * 5
                        lower_k = mid_k - spread_width
                        upper_k = mid_k + spread_width
                        cl = bs_price(spy, lower_k, T_entry, rate, iv, "call")
                        cm = bs_price(spy, mid_k,   T_entry, rate, iv, "call")
                        cu = bs_price(spy, upper_k, T_entry, rate, iv, "call")
                        entry_cost = cl - 2 * cm + cu + self.slippage
                        long_k, short_k = lower_k, mid_k
                        call_long_strike = upper_k
                        long_leg_price, short_leg_price = round(cl, 4), round(cm, 4)

                    else:
                        continue

                    # Validate
                    if is_credit:
                        if net_credit <= 0:
                            continue
                    else:
                        if entry_cost <= 0 or entry_cost > spread_width * 2:
                            continue

                    # Position sizing
                    if is_credit:
                        if stype == "short_strangle":
                            risk_per_contract = net_credit * 3 * 100
                        else:
                            risk_per_contract = max((spread_width - net_credit) * 100, 50.0)
                    else:
                        risk_per_contract = entry_cost * 100

                    budget    = self.capital * self.max_loss_pct
                    contracts = max(1, int(budget / risk_per_contract))

                    if is_credit:
                        net_cash_in = net_credit * contracts * 100 - contracts * self.commission
                        if contracts * self.commission > self.capital:
                            continue
                        self.capital += net_cash_in
                    else:
                        total_cost = contracts * entry_cost * 100 + contracts * self.commission
                        if total_cost > self.capital:
                            continue
                        self.capital -= total_cost

                    expiry_str = str(pd.Timestamp(current_date) + pd.Timedelta(days=expiry_days))[:10]
                    self.open_trade = Trade(
                        entry_date=current_date,
                        exit_date=None,
                        spread_type=stype,
                        long_strike=long_k,
                        short_strike=short_k,
                        expiration=expiry_str,
                        entry_cost=entry_cost,
                        long_leg_price=long_leg_price,
                        short_leg_price=short_leg_price,
                        exit_value=0,
                        contracts=contracts,
                        pnl=0,
                        exit_reason="",
                        predicted_spread_price=pred_price,
                        is_credit=is_credit,
                        net_credit=net_credit,
                        call_short_strike=call_short_strike,
                        call_long_strike=call_long_strike,
                    )
                    self.days_in_trade = 0

            equity = self.capital + self._open_trade_value(spy, vix, rate, current_date)
            self.equity_curve.append({"date": current_date, "equity": equity, "price": spy})

        # Close any open trade at end
        if self.open_trade is not None and self.equity_curve:
            last = self.equity_curve[-1]
            self._close_trade(self.open_trade, last["price"], 18.0, 0.045, last["date"], "end_of_data")

        return pd.DataFrame(self.equity_curve).set_index("date")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _mark_trade(self, trade: Trade, spy: float, vix: float, rate: float, today) -> float:
        """Mark-to-market current P&L of open trade."""
        days_elapsed = (pd.Timestamp(today) - pd.Timestamp(trade.entry_date)).days
        T = max(0, (30 - days_elapsed) / 252)
        iv = vix / 100
        c = trade.contracts

        if trade.spread_type == "iron_condor":
            put_ctc  = spread_value(spy, trade.long_strike, trade.short_strike, T, rate, iv, "bull_put")
            call_ctc = spread_value(spy, trade.call_long_strike, trade.call_short_strike, T, rate, iv, "bear_call")
            return (trade.net_credit - put_ctc - call_ctc) * c * 100
        elif trade.spread_type == "long_straddle":
            val = (bs_price(spy, trade.long_strike, T, rate, iv, "call")
                   + bs_price(spy, trade.long_strike, T, rate, iv, "put"))
            return (val - trade.entry_cost) * c * 100
        elif trade.spread_type == "short_strangle":
            ctc = (bs_price(spy, trade.long_strike,  T, rate, iv, "put")
                   + bs_price(spy, trade.short_strike, T, rate, iv, "call"))
            return (trade.net_credit - ctc) * c * 100
        elif trade.spread_type == "call_butterfly":
            val = (bs_price(spy, trade.long_strike,       T, rate, iv, "call")
                   - 2 * bs_price(spy, trade.short_strike, T, rate, iv, "call")
                   + bs_price(spy, trade.call_long_strike, T, rate, iv, "call"))
            return (val - trade.entry_cost) * c * 100
        elif trade.is_credit:
            ctc = spread_value(spy, trade.long_strike, trade.short_strike, T, rate, iv, trade.spread_type)
            return (trade.net_credit - ctc) * c * 100
        else:
            val = spread_value(spy, trade.long_strike, trade.short_strike, T, rate, iv, trade.spread_type)
            return (val - trade.entry_cost) * c * 100

    def _open_trade_value(self, spy: float, vix: float, rate: float, today) -> float:
        if self.open_trade is None:
            return 0
        t = self.open_trade
        days_elapsed = max(0, (pd.Timestamp(today) - pd.Timestamp(t.entry_date)).days)
        T = max(0, (30 - days_elapsed) / 252)
        iv = vix / 100

        if t.spread_type == "iron_condor":
            put_ctc  = spread_value(spy, t.long_strike, t.short_strike, T, rate, iv, "bull_put")
            call_ctc = spread_value(spy, t.call_long_strike, t.call_short_strike, T, rate, iv, "bear_call")
            return -(put_ctc + call_ctc) * t.contracts * 100
        elif t.spread_type == "long_straddle":
            val = (bs_price(spy, t.long_strike, T, rate, iv, "call")
                   + bs_price(spy, t.long_strike, T, rate, iv, "put"))
            return val * t.contracts * 100
        elif t.spread_type == "short_strangle":
            ctc = (bs_price(spy, t.long_strike,  T, rate, iv, "put")
                   + bs_price(spy, t.short_strike, T, rate, iv, "call"))
            return -ctc * t.contracts * 100
        elif t.spread_type == "call_butterfly":
            val = (bs_price(spy, t.long_strike,       T, rate, iv, "call")
                   - 2 * bs_price(spy, t.short_strike, T, rate, iv, "call")
                   + bs_price(spy, t.call_long_strike, T, rate, iv, "call"))
            return val * t.contracts * 100
        elif t.is_credit:
            ctc = spread_value(spy, t.long_strike, t.short_strike, T, rate, iv, t.spread_type)
            return -ctc * t.contracts * 100
        else:
            val = spread_value(spy, t.long_strike, t.short_strike, T, rate, iv, t.spread_type)
            return val * t.contracts * 100

    def _close_trade(self, trade: Trade, spy: float, vix: float, rate: float, today, reason: str):
        days_elapsed = max(0, (pd.Timestamp(today) - pd.Timestamp(trade.entry_date)).days)
        T = max(0, (30 - days_elapsed) / 252)
        iv = vix / 100
        c = trade.contracts

        if trade.spread_type == "iron_condor":
            put_ctc  = spread_value(spy, trade.long_strike, trade.short_strike, T, rate, iv, "bull_put")
            call_ctc = spread_value(spy, trade.call_long_strike, trade.call_short_strike, T, rate, iv, "bear_call")
            ctc = put_ctc + call_ctc + self.slippage
            pnl = (trade.net_credit - ctc) * c * 100 - c * self.commission
            self.capital -= ctc * c * 100
            trade.exit_value = ctc
        elif trade.spread_type == "long_straddle":
            val = (bs_price(spy, trade.long_strike, T, rate, iv, "call")
                   + bs_price(spy, trade.long_strike, T, rate, iv, "put"))
            exit_val = max(0, val - self.slippage)
            pnl = (exit_val - trade.entry_cost) * c * 100 - c * self.commission
            self.capital += exit_val * c * 100
            trade.exit_value = exit_val
        elif trade.spread_type == "short_strangle":
            ctc = (bs_price(spy, trade.long_strike,  T, rate, iv, "put")
                   + bs_price(spy, trade.short_strike, T, rate, iv, "call") + self.slippage)
            pnl = (trade.net_credit - ctc) * c * 100 - c * self.commission
            self.capital -= ctc * c * 100
            trade.exit_value = ctc
        elif trade.spread_type == "call_butterfly":
            val = (bs_price(spy, trade.long_strike,       T, rate, iv, "call")
                   - 2 * bs_price(spy, trade.short_strike, T, rate, iv, "call")
                   + bs_price(spy, trade.call_long_strike, T, rate, iv, "call"))
            exit_val = max(0, val - self.slippage)
            pnl = (exit_val - trade.entry_cost) * c * 100 - c * self.commission
            self.capital += exit_val * c * 100
            trade.exit_value = exit_val
        elif trade.is_credit:
            ctc = max(0, spread_value(spy, trade.long_strike, trade.short_strike, T, rate, iv, trade.spread_type) + self.slippage)
            pnl = (trade.net_credit - ctc) * c * 100 - c * self.commission
            self.capital -= ctc * c * 100
            trade.exit_value = ctc
        else:
            exit_val = max(0, spread_value(spy, trade.long_strike, trade.short_strike, T, rate, iv, trade.spread_type) - self.slippage)
            pnl = (exit_val - trade.entry_cost) * c * 100 - c * self.commission
            self.capital += exit_val * c * 100
            trade.exit_value = exit_val

        trade.exit_date  = today
        trade.pnl        = pnl
        trade.exit_reason = reason
        self.trades.append(trade)
        self.open_trade   = None
        self.days_in_trade = 0

    # ------------------------------------------------------------------
    # Analytics
    # ------------------------------------------------------------------

    def report(self) -> dict:
        if not self.equity_curve:
            return {}

        eq = pd.DataFrame(self.equity_curve).set_index("date")["equity"]
        rets = eq.pct_change().dropna()

        total_return = (eq.iloc[-1] / self.starting_capital - 1) * 100
        sharpe = (rets.mean() / rets.std()) * np.sqrt(252) if rets.std() > 0 else 0
        max_dd = ((eq / eq.cummax()) - 1).min() * 100

        trades_df = pd.DataFrame([vars(t) for t in self.trades]) if self.trades else pd.DataFrame()
        win_rate = 0.0
        avg_win = avg_loss = 0.0
        if not trades_df.empty:
            wins = trades_df[trades_df["pnl"] > 0]
            losses = trades_df[trades_df["pnl"] <= 0]
            win_rate = len(wins) / len(trades_df) * 100
            avg_win = wins["pnl"].mean() if len(wins) else 0
            avg_loss = losses["pnl"].mean() if len(losses) else 0

        result = {
            "total_return_pct": round(total_return, 2),
            "sharpe_ratio": round(sharpe, 3),
            "max_drawdown_pct": round(max_dd, 2),
            "num_trades": len(self.trades),
            "win_rate_pct": round(win_rate, 2),
            "avg_win_dollars": round(avg_win, 2),
            "avg_loss_dollars": round(avg_loss, 2),
            "profit_factor": round(-avg_win / avg_loss, 3) if avg_loss < 0 else float("inf"),
            "final_equity": round(eq.iloc[-1], 2),
        }

        print("\n" + "=" * 50)
        print("BACKTEST RESULTS")
        print("=" * 50)
        for k, v in result.items():
            print(f"  {k:<25} {v}")
        print("=" * 50 + "\n")

        return result

    def plot_equity(self):
        """Plot equity curve vs SPY buy-and-hold."""
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            logger.warning("matplotlib not installed. pip install matplotlib")
            return

        eq_df = pd.DataFrame(self.equity_curve)
        eq_df["date"] = pd.to_datetime(eq_df["date"])
        eq_df = eq_df.set_index("date")

        bah = self.starting_capital * (eq_df["price"] / eq_df["price"].iloc[0])

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
        ax1.plot(eq_df.index, eq_df["equity"], label="Strategy", color="steelblue")
        ax1.plot(eq_df.index, bah, label="Buy & Hold", color="orange", alpha=0.7)
        ax1.set_title("Options Spread Strategy — Equity Curve")
        ax1.set_ylabel("Portfolio Value ($)")
        ax1.legend()
        ax1.grid(True, alpha=0.3)

        # Drawdown
        rolling_max = eq_df["equity"].cummax()
        drawdown = (eq_df["equity"] / rolling_max - 1) * 100
        ax2.fill_between(eq_df.index, drawdown, 0, color="red", alpha=0.4, label="Drawdown")
        ax2.set_ylabel("Drawdown (%)")
        ax2.set_xlabel("Date")
        ax2.legend()
        ax2.grid(True, alpha=0.3)

        plt.tight_layout()
        plt.savefig("backtest_results.png", dpi=150)
        plt.show()
        logger.info("Saved backtest_results.png")
