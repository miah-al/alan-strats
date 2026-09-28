"""Position risk (api/services/risk.py): structure names, payoff at expiry, implied vol, greek totals,
the most-tested short and its distance in sigmas. Synthetic ledger rows; no network, no database."""
from __future__ import annotations

import datetime as _dt
import math
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:      # only the checkout: its parent holds the live alan_trader (conftest binds ours by path)
    sys.path.insert(0, str(REPO))

from api.bootstrap import bootstrap  # noqa: E402

bootstrap()

from api.marketdata import symbols as SYM  # noqa: E402
from api.services import risk as RK  # noqa: E402

EXP = _dt.date.today() + _dt.timedelta(days=30)


def _grp(*legs):
    """legs: (type, strike, side, qty, price) -> ledger rows (Amount = the leg's cash, no commission)."""
    rows = []
    for typ, k, side, qty, px in legs:
        opt = typ != "stock"
        mult = 100 if opt else 1
        sym = SYM.make_option("XYZ", EXP, typ[0], k).occ if opt else "XYZ"
        rows.append({"Symbol": sym, "Underlying": "XYZ", "SecurityType": "Option" if opt else "Stock",
                     "OptionType": typ.upper() if opt else None, "Strike": k if opt else None,
                     "Expiration": EXP if opt else None, "Multiplier": mult, "Direction": side,
                     "Quantity": qty, "TransactionPrice": px,
                     "Amount": (1 if side == "Sell" else -1) * qty * px * mult})
    return pd.DataFrame(rows)


@pytest.mark.parametrize("legs,name", [
    ([("put", 750, "Sell", 1, 3), ("put", 745, "Buy", 1, 2)], "put credit spread 750/745"),
    ([("call", 770, "Buy", 2, 5), ("call", 780, "Sell", 2, 2)], "call debit spread 770/780"),
    ([("call", 790, "Sell", 1, 2), ("call", 795, "Buy", 1, 1)], "call credit spread 790/795"),
    ([("put", 740, "Buy", 1, 1), ("put", 745, "Sell", 1, 2), ("call", 790, "Sell", 1, 2), ("call", 795, "Buy", 1, 1)],
     "iron condor 740/745/790/795"),
    ([("put", 760, "Sell", 1, 9), ("call", 760, "Sell", 1, 9)], "short straddle 760"),
    ([("put", 740, "Buy", 1, 3), ("call", 780, "Buy", 1, 3)], "long strangle 740/780"),
    ([("call", 770, "Buy", 3, 5)], "long call 770"),
    ([("put", 750, "Sell", 1, 5)], "short put 750"),
    ([("stock", 0, "Buy", 100, 760), ("call", 780, "Sell", 1, 4)], "covered call 780"),
    ([("call", 760, "Buy", 1, 9), ("call", 770, "Sell", 2, 5), ("call", 780, "Buy", 1, 2)], "long call butterfly 760/770/780"),
    ([("stock", 0, "Buy", 10, 760)], "long stock 10"),
])
def test_structure_names(legs, name):
    assert RK.describe_structure(RK.net_legs(_grp(*legs))) == name


def test_payoff_of_a_put_credit_spread():
    g = _grp(("put", 750, "Sell", 1, 3.0), ("put", 745, "Buy", 1, 2.0))       # credit 1.00
    s = RK.payoff_stats(g, 760.0)
    assert s["max_profit"] == pytest.approx(100.0) and s["max_loss"] == pytest.approx(-400.0)
    assert s["breakevens"] == [pytest.approx(749.0)]
    naked = RK.payoff_stats(_grp(("call", 780, "Sell", 1, 4.0)), 760.0)
    assert naked["max_loss"] is None and naked["max_profit"] == pytest.approx(400.0)


def test_implied_vol_round_trips_black_scholes():
    T = 30 / 365
    px = RK._bs_price(100.0, 105.0, T, 0.25, "call")
    assert RK.implied_vol(px, 100.0, 105.0, T, "call") == pytest.approx(0.25, abs=1e-4)
    assert RK.implied_vol(0.5, 100.0, 90.0, T, "call") is None          # below intrinsic
    tz = "America/New_York"
    noon = pd.Timestamp(_dt.datetime.combine(EXP, _dt.time(12, 45)), tz=tz)
    assert RK.years_to_expiry(EXP, noon) == pytest.approx(195 / 390 / 252)   # expiry day: half a session left
    assert RK.years_to_expiry(EXP, noon - pd.Timedelta(days=10)) == pytest.approx(10 / 365)


def test_position_fields_totals_and_the_most_tested_short():
    g = _grp(("put", 750, "Sell", 2, 3.0), ("put", 745, "Buy", 2, 2.0))
    legs = RK.net_legs(g)
    short, long_ = (legs[0], legs[1]) if legs[0].qty < 0 else (legs[1], legs[0])
    greeks = {short.symbol: {"iv": 0.20, "delta": -0.30, "gamma": 0.02, "theta": -0.10, "vega": 0.50, "source": "t"},
              long_.symbol: {"iv": 0.22, "delta": -0.25, "gamma": 0.015, "theta": -0.08, "vega": 0.45, "source": "t"}}
    f = RK.position_risk_fields(None, g, "XYZ", spot=760.0, spy=700.0, greeks=greeks)
    assert f["structure"] == "put credit spread 750/745" and f["units"] == 2
    assert f["entry_credit_debit"] == pytest.approx(1.0) and f["entry_type"] == "credit"
    assert f["max_profit"] == pytest.approx(200.0) and f["max_loss"] == pytest.approx(-800.0)
    # short 2 x 100 x -0.30 and long 2 x 100 x -0.25: +60 - 50 = +10 shares of delta
    assert f["delta"] == pytest.approx(10.0) and f["theta"] == pytest.approx(4.0) and f["vega"] == pytest.approx(-10.0)
    assert f["short_strikes"] == [750.0] and f["short_delta"] == pytest.approx(-0.30)
    T = RK.years_to_expiry(EXP)
    assert f["sigma_to_short"] == pytest.approx((760 - 750) / (760 * 0.20 * math.sqrt(T)), abs=1e-3)
    assert f["direction"] == "bullish"
    greeks[short.symbol]["delta"] = None                  # a leg without greeks: no partial totals
    f2 = RK.position_risk_fields(None, g, "XYZ", spot=760.0, spy=700.0, greeks=greeks)
    assert f2["delta"] is None and f2["theta"] is None and f2["beta_delta_spy"] is None


def test_leg_greeks_fall_back_to_the_marks_implied_vol():
    g = _grp(("call", 100, "Buy", 1, 3.0))
    legs = RK.net_legs(g)
    q = {legs[0].symbol: {"symbol": legs[0].symbol, "mid": 3.5, "source": "fakefeed"}}
    out = RK.leg_greeks(None, legs, 100.0, quotes=q)[legs[0].symbol]
    assert out["mark"] == 3.5 and out["source"] == "black-scholes on the mark's implied vol"
    assert 0.4 < out["delta"] < 0.7 and out["iv"] > 0 and out["theta"] < 0 < out["vega"]
