"""
Options spread selection logic based on model signal + current market conditions.
Selects strike, expiry, and spread type (bull call, bear put, iron condor, etc.)
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

BEAR = 0
NEUTRAL = 1
BULL = 2


@dataclass
class Spread:
    underlying: str
    spread_type: str          # 'bull_call', 'bear_put', 'iron_condor', 'skip'
    expiration: str
    long_strike: float
    short_strike: float
    long_strike2: Optional[float] = None   # for iron condor put side
    short_strike2: Optional[float] = None
    debit_or_credit: float = 0.0          # net debit(+) or credit(-) per share
    max_profit: float = 0.0
    max_loss: float = 0.0
    breakeven: float = 0.0
    delta: float = 0.0
    probability_profit: float = 0.0
    entry_notes: str = ""


def select_spread(
    signal_proba: np.ndarray,     # [bear_prob, neutral_prob, bull_prob]
    spy_price: float,
    vix: float,
    chain: pd.DataFrame,          # options chain from PolygonClient.get_options_chain
    target_expiration: str,
    portfolio_value: float,
    max_loss_pct: float = 0.02,
    min_confidence: float = 0.45,
    underlying: str = "SPY",
) -> Spread:
    """
    Given model probabilities and current market data, select the best spread.

    Returns Spread with spread_type='skip' if no trade meets criteria.
    """
    bear_p, neutral_p, bull_p = signal_proba
    predicted_class = int(np.argmax(signal_proba))
    confidence = signal_proba[predicted_class]

    logger.info(f"Signal: bear={bear_p:.2f} neutral={neutral_p:.2f} bull={bull_p:.2f} | VIX={vix:.1f}")

    # Skip if model isn't confident enough
    if confidence < min_confidence or predicted_class == NEUTRAL:
        return Spread(
            underlying=underlying,
            spread_type="skip",
            expiration=target_expiration,
            long_strike=0, short_strike=0,
            entry_notes=f"Skipped: confidence={confidence:.2f} class={predicted_class}"
        )

    chain = chain.copy().dropna(subset=["bid", "ask", "strike", "delta"])
    calls = chain[chain["type"] == "call"].sort_values("strike")
    puts = chain[chain["type"] == "put"].sort_values("strike")

    # Budget: max dollar loss per trade
    max_loss_dollars = portfolio_value * max_loss_pct

    # High VIX → prefer credit spreads (sell premium)
    # Low VIX  → prefer debit spreads (buy direction)
    if vix > 25:
        strategy = "credit"
    else:
        strategy = "debit"

    if predicted_class == BULL:
        if strategy == "debit":
            return _bull_call_spread(calls, spy_price, target_expiration, max_loss_dollars, confidence, underlying)
        else:
            return _bull_put_spread(puts, spy_price, target_expiration, max_loss_dollars, confidence, underlying)

    if predicted_class == BEAR:
        if strategy == "debit":
            return _bear_put_spread(puts, spy_price, target_expiration, max_loss_dollars, confidence, underlying)
        else:
            return _bear_call_spread(calls, spy_price, target_expiration, max_loss_dollars, confidence, underlying)

    return Spread(underlying, "skip", target_expiration, 0, 0, entry_notes="No signal")


# ---------------------------------------------------------------------------
# Spread constructors
# ---------------------------------------------------------------------------

def _bull_call_spread(calls: pd.DataFrame, spot: float, expiry: str, max_loss: float, conf: float, underlying: str = "SPY") -> Spread:
    """Buy ATM call, sell OTM call. Debit spread — profit if price rises."""
    atm = calls.iloc[(calls["strike"] - spot).abs().argsort().iloc[0]]
    otm_candidates = calls[calls["strike"] > atm["strike"] + 3]
    if otm_candidates.empty:
        return Spread(underlying, "skip", expiry, 0, 0, entry_notes="No suitable OTM call found")
    otm = otm_candidates.iloc[0]

    mid_long = (atm["bid"] + atm["ask"]) / 2
    mid_short = (otm["bid"] + otm["ask"]) / 2
    net_debit = mid_long - mid_short
    spread_width = otm["strike"] - atm["strike"]
    max_profit = spread_width - net_debit
    max_loss_spread = net_debit  # per share; multiply by 100 for 1 contract

    return Spread(
        underlying=underlying,
        spread_type="bull_call",
        expiration=expiry,
        long_strike=atm["strike"],
        short_strike=otm["strike"],
        debit_or_credit=net_debit,
        max_profit=max_profit,
        max_loss=max_loss_spread,
        breakeven=atm["strike"] + net_debit,
        delta=atm.get("delta", 0.5) - otm.get("delta", 0.3),
        probability_profit=conf,
        entry_notes=f"BullCall {atm['strike']}/{otm['strike']} debit={net_debit:.2f}",
    )


def _bull_put_spread(puts: pd.DataFrame, spot: float, expiry: str, max_loss: float, conf: float, underlying: str = "SPY") -> Spread:
    """Sell OTM put, buy further OTM put. Credit spread — profit if price stays above short strike."""
    otm_short = puts[(puts["strike"] < spot - 5) & (puts["delta"].abs() < 0.35)]
    if otm_short.empty:
        return Spread(underlying, "skip", expiry, 0, 0, entry_notes="No suitable short put found")
    short_put = otm_short.iloc[-1]  # closest to ATM
    long_candidates = puts[puts["strike"] < short_put["strike"] - 3]
    if long_candidates.empty:
        return Spread(underlying, "skip", expiry, 0, 0, entry_notes="No suitable long put found")
    long_put = long_candidates.iloc[-1]

    mid_short = (short_put["bid"] + short_put["ask"]) / 2
    mid_long = (long_put["bid"] + long_put["ask"]) / 2
    net_credit = mid_short - mid_long
    spread_width = short_put["strike"] - long_put["strike"]
    max_loss_spread = spread_width - net_credit

    return Spread(
        underlying=underlying,
        spread_type="bull_put",
        expiration=expiry,
        long_strike=long_put["strike"],
        short_strike=short_put["strike"],
        debit_or_credit=-net_credit,   # negative = credit received
        max_profit=net_credit,
        max_loss=max_loss_spread,
        breakeven=short_put["strike"] - net_credit,
        delta=abs(short_put.get("delta", -0.3)) - abs(long_put.get("delta", -0.15)),
        probability_profit=conf,
        entry_notes=f"BullPut {long_put['strike']}/{short_put['strike']} credit={net_credit:.2f}",
    )


def _bear_put_spread(puts: pd.DataFrame, spot: float, expiry: str, max_loss: float, conf: float, underlying: str = "SPY") -> Spread:
    """Buy ATM put, sell OTM put. Debit spread — profit if price falls."""
    atm = puts.iloc[(puts["strike"] - spot).abs().argsort().iloc[0]]
    otm_candidates = puts[puts["strike"] < atm["strike"] - 3]
    if otm_candidates.empty:
        return Spread(underlying, "skip", expiry, 0, 0, entry_notes="No suitable OTM put found")
    otm = otm_candidates.iloc[-1]

    mid_long = (atm["bid"] + atm["ask"]) / 2
    mid_short = (otm["bid"] + otm["ask"]) / 2
    net_debit = mid_long - mid_short
    spread_width = atm["strike"] - otm["strike"]
    max_profit = spread_width - net_debit

    return Spread(
        underlying=underlying,
        spread_type="bear_put",
        expiration=expiry,
        long_strike=atm["strike"],
        short_strike=otm["strike"],
        debit_or_credit=net_debit,
        max_profit=max_profit,
        max_loss=net_debit,
        breakeven=atm["strike"] - net_debit,
        delta=atm.get("delta", -0.5) - otm.get("delta", -0.3),
        probability_profit=conf,
        entry_notes=f"BearPut {otm['strike']}/{atm['strike']} debit={net_debit:.2f}",
    )


def _bear_call_spread(calls: pd.DataFrame, spot: float, expiry: str, max_loss: float, conf: float, underlying: str = "SPY") -> Spread:
    """Sell OTM call, buy further OTM call. Credit spread — profit if price stays below short strike."""
    otm_short = calls[(calls["strike"] > spot + 5) & (calls["delta"] < 0.35)]
    if otm_short.empty:
        return Spread(underlying, "skip", expiry, 0, 0, entry_notes="No suitable short call found")
    short_call = otm_short.iloc[0]
    long_candidates = calls[calls["strike"] > short_call["strike"] + 3]
    if long_candidates.empty:
        return Spread(underlying, "skip", expiry, 0, 0, entry_notes="No suitable long call found")
    long_call = long_candidates.iloc[0]

    mid_short = (short_call["bid"] + short_call["ask"]) / 2
    mid_long = (long_call["bid"] + long_call["ask"]) / 2
    net_credit = mid_short - mid_long
    spread_width = long_call["strike"] - short_call["strike"]
    max_loss_spread = spread_width - net_credit

    return Spread(
        underlying=underlying,
        spread_type="bear_call",
        expiration=expiry,
        long_strike=long_call["strike"],
        short_strike=short_call["strike"],
        debit_or_credit=-net_credit,
        max_profit=net_credit,
        max_loss=max_loss_spread,
        breakeven=short_call["strike"] + net_credit,
        delta=short_call.get("delta", 0.3) - long_call.get("delta", 0.15),
        probability_profit=conf,
        entry_notes=f"BearCall {short_call['strike']}/{long_call['strike']} credit={net_credit:.2f}",
    )


def contracts_to_trade(spread: Spread, portfolio_value: float, max_loss_pct: float = 0.02) -> int:
    """How many contracts to trade given max loss budget?"""
    if spread.spread_type == "skip" or spread.max_loss <= 0:
        return 0
    budget = portfolio_value * max_loss_pct
    contracts = int(budget / (spread.max_loss * 100))  # 100 shares per contract
    return max(0, contracts)
