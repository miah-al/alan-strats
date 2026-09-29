"""The stress grid (api/services/risk_stress.py): full Black-Scholes revaluation over underlying moves × IV shocks,
greeks re-computed at each cell, the settlement payoff, aggregation per strategy and portfolio, and GET /api/risk.
Stand-in ledger groups priced off marks made at fixed IVs; no network, no database, no broker."""
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
from api.services import risk_stress as RS  # noqa: E402
from paper import views as PV  # noqa: E402

NY = RS.NY
EXP = _dt.date.today() + _dt.timedelta(days=30)
NOW = pd.Timestamp.now(tz=NY)
S0 = 20000.0


def _grp(legs, exp=EXP, und="NDX", root="NDXP"):
    """legs: (type, strike, side, qty, price) -> ledger rows (Amount = the leg's cash, no commission)."""
    rows = []
    for typ, k, side, qty, px in legs:
        opt = typ != "stock"
        mult = 100 if opt else 1
        rows.append({"Symbol": SYM.make_option(root, exp, typ[0], k).occ if opt else und, "Underlying": und,
                     "SecurityType": "Option" if opt else "Stock", "OptionType": typ.upper() if opt else None,
                     "Strike": k if opt else None, "Expiration": exp if opt else None, "Multiplier": mult,
                     "Direction": side, "Quantity": qty, "TransactionPrice": px,
                     "Amount": (1 if side == "Sell" else -1) * qty * px * mult})
    return pd.DataFrame(rows)


def _position(tgid, strategy, legs, iv=0.20, spot=S0, now=NOW, exp=EXP, und="NDX", root="NDXP", marks=True):
    """A stand-in open position: its legs marked at Black-Scholes on ``iv`` (the grid's own clock), so the IV implied
    back from each mark is ``iv``; its positions row as the Paper page builds it (P&L = net entry + market value)."""
    grp = _grp(legs, exp=exp, und=und, root=root)
    quotes, mv = {}, 0.0
    for nl in RK.net_legs(grp):
        T = RS.years_left(nl.expiry, now)[0]
        mid = RK._bs_price(spot, nl.strike, T, iv, nl.type)
        quotes[nl.symbol] = {"symbol": nl.symbol, "mid": mid, "source": "fake"}
        mv += mid * nl.qty * nl.mult
    entry = PV._net_entry(grp)
    stats = RK.payoff_stats(grp, spot)
    row = {"strategy": strategy, "strategy_label": strategy.replace("_", " ").title(), "underlying": und, "spot": spot,
           "entry_net": entry, "market_value": mv, "pnl": entry + mv, "max_loss": stats["max_loss"],
           "max_profit": stats["max_profit"], "expiry": exp, "contracts": max(abs(l[3]) for l in legs),
           "structure": RK.describe_structure(RK.net_legs(grp)), "priced_by": "fake"}
    return RS.position_inputs(tgid, grp, row, quotes if marks else {}, now), grp


def _call_spread(qty=1):      # 25-wide call debit spread, long the lower strike
    return _position("NDX-A-1", "alpha", [("call", 20000, "Buy", qty, 160.0), ("call", 20025, "Sell", qty, 145.0)])


def _put_spread(qty=2):       # 100-wide put debit spread, long the higher strike
    return _position("NDX-B-2", "beta", [("put", 20000, "Buy", qty, 190.0), ("put", 19900, "Sell", qty, 150.0)])


def _cell(ent, move, vol):
    st = ent["stress"]
    return next(c for row in st["cells"] for c in row if c["move"] == move and c["vol"] == vol)


def _entities(rep):
    return [rep["portfolio"], *rep["by_strategy"], *rep["positions"]]


# ── the grid ──────────────────────────────────────────────────────────────────

def test_legs_carry_the_iv_implied_from_their_marks():
    (p, _g) = _call_spread()
    assert all(l.iv == pytest.approx(0.20, abs=1e-4) and l.iv_source == "implied from its mark" for l in p.legs)
    assert p.priced and p.max_loss == pytest.approx(-1500.0) and not p.max_loss_unbounded


def test_no_move_no_shock_is_zero_and_the_greeks_now_are_that_cell():
    rep = RS.compute([_call_spread()[0], _put_spread()[0]], horizon="now", now=NOW)
    for ent in _entities(rep):
        c = _cell(ent, 0.0, 0.0)
        assert c["pnl"] == pytest.approx(0.0, abs=0.01)
        assert c["pnl_total"] == pytest.approx(ent["pnl"], abs=0.01)
        for k in ("delta", "gamma", "theta", "vega"):
            assert c["greeks"][k] == pytest.approx(ent["greeks"][k], abs=0.02)


def test_a_call_debit_spread_gains_as_the_underlying_rises_and_a_put_debit_spread_falls():
    rep = RS.compute([_call_spread()[0], _put_spread()[0]], horizon="now", now=NOW)
    call, put = rep["positions"]
    for vol in rep["vols"]:
        up = [_cell(call, m, vol)["pnl"] for m in rep["moves"]]
        down = [_cell(put, m, vol)["pnl"] for m in rep["moves"]]
        assert all(b > a for a, b in zip(up, up[1:])), up
        assert all(b < a for a, b in zip(down, down[1:])), down
    assert call["greeks"]["delta"] > 0 > put["greeks"]["delta"]
    assert call["greeks"]["delta_units"] > 0 and rep["positions"][0]["underlyings"] == ["NDX"]


def test_every_cell_is_a_full_revaluation_not_a_taylor_step():
    (p, _g) = _position("NDX-C-3", "gamma_test", [("call", 20000, "Buy", 1, 460.0)])
    rep = RS.compute([p], moves=[-3.0, 0.0, 3.0], vols=[0.0, 5.0], horizon="now", now=NOW)
    pos = rep["positions"][0]
    T = RS.years_left(EXP, NOW)[0]
    ref = RK._bs_price(S0, 20000, T, 0.20, "call")
    for m in (-3.0, 3.0):
        S = S0 * (1 + m / 100)
        for v in (0.0, 5.0):
            want = (RK._bs_price(S, 20000, T, 0.20 + v / 100, "call") - ref) * 100
            assert _cell(pos, m, v)["pnl"] == pytest.approx(want, abs=0.05)
            # the greeks at the cell are Black-Scholes at that spot and vol, not the ones from now
            _px, d, gm, vega, _th, _va = PV._bs_full(S, 20000, T, RK.RISK_FREE, 0.20 + v / 100, "call")
            g = _cell(pos, m, v)["greeks"]
            assert g["delta_units"] == pytest.approx(d * 100, abs=1e-3)
            assert g["delta"] == pytest.approx(d * 100 * S * 0.01, abs=0.01)
            assert g["gamma_units"] == pytest.approx(gm * 100, rel=1e-4)
            assert g["gamma"] == pytest.approx(gm * 100 * (S * 0.01) ** 2, abs=0.01)
            assert g["vega"] == pytest.approx(vega * 100, abs=0.01)
    # a long call's delta rises with the underlying (long gamma): each cell's delta is its own
    deltas = [_cell(pos, m, 0.0)["greeks"]["delta_units"] for m in (-3.0, 0.0, 3.0)]
    assert deltas[0] < deltas[1] < deltas[2]
    # a Taylor step from now (delta·dS + ½gamma·dS²) is not what the grid holds
    g0 = pos["greeks"]
    dS = S0 * 0.03
    taylor = g0["delta_units"] * dS + 0.5 * g0["gamma_units"] * dS * dS
    assert abs(_cell(pos, 3.0, 0.0)["pnl"] - taylor) > 1.0


def test_settlement_is_the_intrinsic_payoff_against_entry():
    (a, ga), (b, gb) = _call_spread(), _put_spread()
    rep = RS.compute([a, b], moves=[-5.0, -1.0, -0.25, 0.0, 0.1, 1.0, 5.0], vols=[-5.0, 0.0, 10.0],
                     horizon="settlement", now=NOW)
    assert rep["horizon"] == "settlement" and rep["settlement_at"] == RS._close(EXP)
    for pos, grp in zip(rep["positions"], (ga, gb)):
        for m in rep["moves"]:
            payoff = PV._expiry_payoff_pnl(grp, S0 * (1 + m / 100))
            for v in rep["vols"]:
                c = _cell(pos, m, v)
                assert c["pnl_total"] == pytest.approx(payoff, abs=0.01)
                assert c["pnl"] == pytest.approx(payoff - pos["pnl"], abs=0.01)
                assert c["greeks"] is None                  # every leg has settled
    port = rep["portfolio"]
    for m in rep["moves"]:
        want = sum(PV._expiry_payoff_pnl(g, S0 * (1 + m / 100)) for g in (ga, gb))
        assert _cell(port, m, 0.0)["pnl_total"] == pytest.approx(want, abs=0.02)


def test_a_debit_spread_never_loses_more_than_it_cost_or_its_width():
    moves = [-30.0, -10.0, -3.0, 0.0, 3.0, 10.0, 30.0]
    for (p, grp), width, qty in ((_call_spread(), 25, 1), (_put_spread(), 100, 2)):
        debit = -PV._net_entry(grp)
        assert p.max_loss == pytest.approx(-debit) and debit < width * 100 * qty
        for horizon in ("now", "1h", "settlement"):
            rep = RS.compute([p], moves=moves, vols=[-5.0, 0.0, 10.0], horizon=horizon, now=NOW)
            pos = rep["positions"][0]
            totals = [c["pnl_total"] for row in pos["stress"]["cells"] for c in row]
            assert min(totals) >= -debit - 0.01
            assert max(totals) <= width * 100 * qty - debit + 0.01
            # the worst cell (ties within 50c go to the smallest move that reaches the loss)
            assert pos["stress"]["worst"]["pnl"] == pytest.approx(min(c["pnl"] for row in pos["stress"]["cells"] for c in row), abs=0.5)
        worst = RS.compute([p], moves=moves, vols=[0.0], horizon="settlement", now=NOW)["positions"][0]["stress"]["worst"]
        # spot sits on the long strike: the spread already expires worthless unchanged, the nearest scenario to the loss
        assert worst["pnl_total"] == pytest.approx(-debit, abs=0.5) and worst["move"] == 0.0
        assert worst["scenario"] == "NDX unch. · IV unch."


def test_strategies_and_the_portfolio_are_the_sums_of_their_positions():
    (a, _), (b, _), (c, _) = _call_spread(), _put_spread(), _position(
        "NDX-A-9", "alpha", [("put", 19800, "Sell", 1, 90.0), ("put", 19775, "Buy", 1, 80.0)])
    rep = RS.compute([a, b, c], horizon="now", now=NOW)
    pos = {p["trade_group_id"]: p for p in rep["positions"]}
    strat = {s["strategy"]: s for s in rep["by_strategy"]}
    assert set(strat) == {"alpha", "beta"} and strat["alpha"]["positions"] == 2
    groups = {"portfolio": (rep["portfolio"], list(pos.values())),
              "alpha": (strat["alpha"], [pos["NDX-A-1"], pos["NDX-A-9"]]), "beta": (strat["beta"], [pos["NDX-B-2"]])}
    for _name, (ent, members) in groups.items():
        assert ent["pnl"] == pytest.approx(sum(m["pnl"] for m in members), abs=0.02)
        assert ent["max_loss"] == pytest.approx(sum(m["max_loss"] for m in members), abs=0.02)
        for k in ("delta", "delta_units", "gamma", "theta", "theta_hour", "vega"):
            assert ent["greeks"][k] == pytest.approx(sum(m["greeks"][k] for m in members), abs=0.05)
        for m_ in rep["moves"]:
            for v in rep["vols"]:
                cell = _cell(ent, m_, v)
                assert cell["pnl"] == pytest.approx(sum(_cell(m, m_, v)["pnl"] for m in members), abs=0.05)
                assert cell["pnl_total"] == pytest.approx(sum(_cell(m, m_, v)["pnl_total"] for m in members), abs=0.05)
                assert cell["greeks"]["delta"] == pytest.approx(sum(_cell(m, m_, v)["greeks"]["delta"] for m in members), abs=0.05)
        worst = min((c for row in ent["stress"]["cells"] for c in row), key=lambda c: c["pnl"])
        assert ent["stress"]["worst"]["pnl"] == pytest.approx(worst["pnl"], abs=0.5)
        assert ent["stress"]["worst"]["scenario"].startswith("NDX ")


def test_a_long_straddle_gains_from_a_vol_rise_and_loses_from_a_fall():
    (p, _g) = _position("NDX-S-4", "straddle", [("call", 20000, "Buy", 1, 460.0), ("put", 20000, "Buy", 1, 440.0)])
    rep = RS.compute([p], horizon="now", now=NOW)
    pos = rep["positions"][0]
    by_vol = [_cell(pos, 0.0, v)["pnl"] for v in rep["vols"]]         # -5, 0, +5, +10
    assert by_vol[0] < 0 < by_vol[2] < by_vol[3]
    assert pos["greeks"]["vega"] > 0 and pos["greeks"]["gamma"] > 0 and pos["greeks"]["theta"] < 0
    # long gamma: a move either way beats standing still
    assert _cell(pos, -3.0, 0.0)["pnl"] > 0 and _cell(pos, 3.0, 0.0)["pnl"] > 0


def test_an_uncovered_short_call_has_no_max_loss_and_neither_does_its_book():
    (p, _g) = _position("NDX-N-5", "naked", [("call", 20500, "Sell", 1, 120.0)])
    assert p.max_loss is None and p.max_loss_unbounded
    rep = RS.compute([p, _call_spread()[0]], horizon="now", now=NOW)
    assert rep["portfolio"]["max_loss"] is None and rep["portfolio"]["max_loss_unbounded"]


def test_underlyings_move_together_and_unit_greeks_do_not_mix():
    (a, _), (b, _) = _call_spread(), _position("SPX-Q-6", "spx", [("call", 6000, "Buy", 1, 80.0)], spot=6000.0,
                                               und="SPX", root="SPXW")
    rep = RS.compute([a, b], horizon="now", now=NOW)
    assert rep["spots"] == {"NDX": S0, "SPX": 6000.0}
    assert any("same percentage" in s for s in rep["assumptions"])
    port = rep["portfolio"]
    assert port["greeks"]["delta_units"] is None and port["greeks"]["delta"] is not None
    assert _cell(port, 2.0, 0.0)["spot"] is None
    spx = next(p for p in rep["positions"] if p["underlying"] == "SPX")
    assert _cell(spx, 2.0, 0.0)["spot"] == pytest.approx(6120.0)
    assert port["stress"]["worst"]["scenario"].startswith("all ")


# ── the clock and the IVs ─────────────────────────────────────────────────────

def test_a_same_day_option_runs_on_a_floored_session_clock():
    today = _dt.date.today()
    at = lambda h, m: pd.Timestamp(_dt.datetime.combine(today, _dt.time(h, m)), tz=NY)  # noqa: E731
    assert RS.years_left(today, at(12, 45)) == (pytest.approx(195 / 390 / 252), "session")
    assert RS.years_left(today, at(15, 58))[0] == pytest.approx(RS.MIN_MINUTES / 390 / 252)
    assert RS.years_left(today, at(8, 0))[0] == pytest.approx(1 / 252)       # before the open: one session left
    assert RS.years_left(today, at(16, 1)) is None
    assert RS.years_left(today + _dt.timedelta(days=1), at(16, 0))[0] == pytest.approx(1 / 365)

    late = at(15, 58)
    (p, grp) = _position("NDX-Z-7", "zero", [("call", 20000, "Buy", 1, 30.0), ("call", 20025, "Sell", 1, 20.0)],
                         now=late, exp=today)
    now_rep = RS.compute([p], horizon="now", now=late)
    g = now_rep["positions"][0]["greeks"]
    assert all(math.isfinite(g[k]) for k in ("delta", "gamma", "theta", "theta_hour", "vega"))
    assert g["theta_hour"] == pytest.approx(g["theta"] / 6.5, rel=1e-6)
    hour = RS.compute([p], horizon="+1h", now=late)                     # past the close: settled at intrinsic
    assert hour["horizon"] == "1h"
    for m in hour["moves"]:
        c = _cell(hour["positions"][0], m, 0.0)
        assert c["greeks"] is None
        intrinsic = PV._expiry_payoff_pnl(grp, S0 * (1 + m / 100)) - PV._net_entry(grp)
        assert c["pnl"] == pytest.approx(intrinsic - now_rep["positions"][0]["model_value"], abs=0.02)


def test_legs_without_an_invertible_mark_borrow_the_nearest_strike_or_an_assumed_vol():
    (p, _g) = _call_spread()
    (q, _g2) = _position("NDX-D-8", "deep", [("call", 18000, "Buy", 1, 2000.0)], marks=False)
    (r, _g3) = _position("SPX-U-9", "unquoted", [("call", 6000, "Buy", 1, 80.0)], spot=6000.0, und="SPX",
                         root="SPXW", marks=False)
    assert q.legs[0].iv is None and r.legs[0].iv is None
    notes = RS.fill_missing_ivs([p, q, r], NOW)
    assert q.legs[0].iv == pytest.approx(0.20, abs=1e-4) and q.legs[0].iv_source == "nearest strike's IV (20000)"
    assert r.legs[0].iv == RS.DEFAULT_IV and r.legs[0].iv_source.startswith("assumed")
    assert len(notes) == 1 and "SPX" in notes[0]


def test_parameters_are_parsed_and_checked():
    assert RS.parse_grid(None, RS.DEFAULT_MOVES, "moves", 50, 25) == RS.DEFAULT_MOVES
    assert RS.parse_grid("1, -1,0,1%", (), "moves", 50, 25) == (-1.0, 0.0, 1.0)
    for bad in ("x", "90", ",".join(str(i) for i in range(30))):
        with pytest.raises(ValueError):
            RS.parse_grid(bad, (), "moves", 50, 25)
    assert [RS.normalize_horizon(h) for h in ("now", "+1h", " 1h", "1H", "settle", "Settlement")] == \
           ["now", "1h", "1h", "1h", "settlement", "settlement"]
    with pytest.raises(ValueError):
        RS.normalize_horizon("tomorrow")


# ── the data path: the Paper page's positions, one hub snapshot, cached ────────

class _FakeHub:
    """A market-data hub with fixed quotes: counts the snapshots it serves."""

    def __init__(self, quotes):
        self.providers = ["fake"]
        self.quotes = quotes
        self.snapshots = 0

    def snapshot(self, symbols, wait=0.0):
        self.snapshots += 1
        return [self.quotes.get(s, {"symbol": s}) for s in symbols]


def test_gather_ties_to_the_paper_positions_table_and_is_cached(monkeypatch):
    from api.services import paper as P
    (a, ga), (b, gb) = _call_spread(), _put_spread()
    groups = {"NDX-A-1": ga.assign(TradeGroupId="NDX-A-1", StrategyName="alpha", BusinessDate=_dt.date.today()),
              "NDX-B-2": gb.assign(TradeGroupId="NDX-B-2", StrategyName="beta", BusinessDate=_dt.date.today())}
    quotes = {"NDX": {"symbol": "NDX", "last": S0, "mid": S0, "source": "fake"}, "SPY": {"symbol": "SPY", "last": 600.0}}
    for p in (a, b):
        for l in p.legs:
            quotes[l.symbol] = {"symbol": l.symbol, "mid": l.mark, "source": "fake"}
    hub = _FakeHub(quotes)
    monkeypatch.setattr(P, "load", lambda: (groups, [], pd.concat(groups.values())))
    monkeypatch.setattr(P, "_labels", lambda: {"alpha": "Alpha", "beta": "Beta"})
    monkeypatch.setattr(PV, "_glob_state", lambda pattern: [])            # no runner state: marks from the hub
    monkeypatch.setattr(RK, "beta_spy", lambda s: None)
    RS.clear_cache()
    try:
        table = {r["trade_group_id"]: r for r in P.positions("open", hub=hub)["rows"]}
        before = hub.snapshots
        rep = RS.report(hub)
        assert hub.snapshots == before + 1                                # one snapshot for the whole book
        RS.report(hub, horizon="settlement")
        RS.report(hub, strategy="beta")
        assert hub.snapshots == before + 1                                # inputs reused inside the TTL
        for pos in rep["positions"]:
            row = table[pos["trade_group_id"]]
            assert pos["pnl"] == pytest.approx(row["pnl"], abs=0.01)
            assert pos["max_loss"] == pytest.approx(row["max_loss"], abs=0.01)
            assert pos["strategy_label"] == row["strategy_label"] and pos["structure"] == row["structure"]
            assert all(l["iv"] == pytest.approx(0.20, abs=1e-3) for l in pos["legs"])
            assert _cell(pos, 0.0, 0.0)["pnl"] == pytest.approx(0.0, abs=0.01)
        assert rep["portfolio"]["pnl"] == pytest.approx(sum(r["pnl"] for r in table.values()), abs=0.02)
        only = RS.report(hub, trade_group_id="2")                         # the ledger tail finds NDX-B-2
        assert [p["trade_group_id"] for p in only["positions"]] == ["NDX-B-2"]
    finally:
        RS.clear_cache()


def test_the_endpoint(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.routers import risk as risk_router
    (a, _), (b, _) = _call_spread(), _put_spread()
    monkeypatch.setattr(RS, "cached_inputs", lambda hub: RS.Inputs(at=NOW, positions=[a, b], warnings=["w"]))
    app = FastAPI()
    app.include_router(risk_router.router, prefix="/api")
    with TestClient(app) as c:
        r = c.get("/api/risk", params={"moves": "-1,0,1", "vols": "0,5", "horizon": "+1h"})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["horizon"] == "1h" and j["moves"] == [-1.0, 0.0, 1.0] and j["vols"] == [0.0, 5.0]
        assert [h["key"] for h in j["horizons"]] == ["now", "1h", "settlement"]
        assert len(j["portfolio"]["stress"]["cells"]) == 3 and len(j["portfolio"]["stress"]["cells"][0]) == 2
        assert {s["strategy"] for s in j["by_strategy"]} == {"alpha", "beta"} and len(j["positions"]) == 2
        assert j["warnings"] == ["w"] and j["filter"] == {"strategy": None, "trade_group_id": None}
        assert set(j["portfolio"]["greeks"]) == {"delta", "delta_units", "gamma", "gamma_units", "theta", "theta_hour", "vega"}
        j2 = c.get("/api/risk", params={"strategy": "alpha"}).json()
        assert [p["trade_group_id"] for p in j2["positions"]] == ["NDX-A-1"] and len(j2["portfolio"]["stress"]["cells"]) == 9
        assert c.get("/api/risk", params={"horizon": "tomorrow"}).status_code == 422
        assert c.get("/api/risk", params={"moves": "1,abc"}).status_code == 422
        assert c.get("/api/risk", params={"vols": "500"}).status_code == 422
