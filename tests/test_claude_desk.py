"""The NDX desk's discipline that is code, not judgment (scripts/claude_desk.py, 2026-09-30): the playbook line for the
gamma regime and the clock, and the trades-per-day cap. No network: nothing here calls the service or a broker."""
from __future__ import annotations

import pandas as pd
import pytest

from scripts import claude_desk as D

NY = "America/New_York"


def at(hm: str) -> pd.Timestamp:
    return pd.Timestamp(f"2026-09-30 {hm}", tz=NY)


def test_the_playbook_follows_the_regime_and_the_clock():
    lv = "OR 30,563/30,415 | gamma: call wall 30,800, put wall 30,400, flip 29,268, max pain 30,350 (positive)"
    assert "no trades" in D.playbook(lv, at("09:50"))                                   # the first 30 minutes
    pos = D.playbook(lv, at("11:00"))
    assert "breaks fail" in pos and "no break trades" in pos and "sell premium" in pos
    neg = D.playbook(lv.replace("(positive)", "(negative)"), at("11:00"))
    assert "never fade" in neg and "block Friend's adds" in neg
    assert "flip" in D.playbook(lv.replace("(positive)", "(near_flip)"), at("11:00"))
    assert "15:50" in D.playbook(lv, at("15:41"))                                       # no short gamma into the imbalances
    assert "no gamma regime" in D.playbook("OR 30,563/30,415", at("11:00"))


def test_trades_a_day_count_opens_not_trims():
    st = {"positions": {"A": {"lots": 2}, "B": {"lots": 1, "trim_of": "A"}, "C": {"lots": 2}}}
    assert D.trades_today(st) == 2
    assert D.trades_today({}) == 0 and D.trades_today({"positions": {}}) == 0


def test_spx_walls_are_shown_in_ndx_points_at_the_live_ratio():
    g = {"spot": 7674.0, "call_wall": 7750.0, "put_wall": 7600.0, "flip": 7694.0, "max_pain": 7700.0, "regime": "negative"}
    line = D.spx_walls_in_ndx(g, 30417.0)                              # ratio 3.9636
    assert line.startswith("SPX gamma in NDX pts: call wall 30,718 (7,750)") and "put wall 30,124 (7,600)" in line
    assert line.endswith("(SPX negative)")
    assert D.spx_walls_in_ndx(g, None) == "" and D.spx_walls_in_ndx({"call_wall": 7750.0}, 30417.0) == ""


def test_premium_only_refuses_a_debit_and_quotes_condors_outside_the_range():
    """premium_only (agreed 2026-10-01): a debit is refused, a credit passes; the menu sells outside the day's range."""
    assert "premium only" in D.premium_refusal({"debit_credit": "debit"}, True)
    assert D.premium_refusal({"debit_credit": "credit"}, True) is None
    assert D.premium_refusal({"debit_credit": "debit"}, False) is None                  # the owner can switch it off
    menu = dict(D.premium_menu(30_540.0, 30_616.0, 30_275.0))
    assert menu["condor"] == [("sell", "C", 30_650.0), ("buy", "C", 30_675.0), ("sell", "P", 30_250.0), ("buy", "P", 30_225.0)]
    assert menu["condor@edges"][0] == ("sell", "C", 30_625.0) and menu["condor@edges"][2] == ("sell", "P", 30_275.0)
    assert menu["call credit"] == [("sell", "C", 30_650.0), ("buy", "C", 30_675.0)]
    assert all(s == "sell" for s, _, _ in [legs[0] for legs in menu.values()])           # every structure opens with a sale
    # no range yet (first minutes) or the spot outside it: the spot bounds the shorts
    assert dict(D.premium_menu(30_540.0, None, None))["condor"][0] == ("sell", "C", 30_575.0)


def test_the_premium_only_limit_is_on_by_default():
    from api.services import limits as LIM
    spec = {s["name"]: s for s in LIM.DESKS["claude_discretionary"]["limits"]}["premium_only"]
    assert spec["default"] == 1 and (spec["min"], spec["max"]) == (0, 1)


# ── the NDX/SPX ratio pair (2026-10-12, the owner: "take over ratio into your desk") ─────────────────────────────

def test_an_spx_leg_is_an_spxw_order_and_ndx_stays_the_default():
    day = pd.Timestamp("2026-10-12").date()
    legs = [{"side": "sell", "cp": "C", "strike": 7835.0}, {"side": "buy", "cp": "C", "strike": 7840.0}]
    b = D.order_body(legs, 2, day, "x", "SPX")
    assert b["underlying"] == "SPX" and [l["symbol"] for l in b["legs"]] == ["SPXW261012C07835000", "SPXW261012C07840000"]
    assert all(l["quantity"] == 2 for l in b["legs"])
    n = D.order_body([{"side": "sell", "cp": "P", "strike": 30650.0}], 1, day, "x")
    assert n["underlying"] == "NDX" and n["legs"][0]["symbol"] == "NDXP261012P30650000"
    assert D.parse_legs("sell:P:30650, buy:P:30625") == [{"side": "sell", "cp": "P", "strike": 30650.0},
                                                       {"side": "buy", "cp": "P", "strike": 30625.0}]
    assert D.crossing_cost(legs, 7812.0, "SPX") == 0.1


def test_a_pair_is_one_trade_and_the_ratio_reads_in_basis_points():
    st = {"positions": {"N": {"lots": 1, "pair": "S"}, "S": {"lots": 2, "pair_of": "N"}, "T": {"lots": 1, "trim_of": "N"}}}
    assert D.trades_today(st) == 1
    idx = pd.date_range("2026-10-12 10:00", periods=60, freq="min")
    hist = pd.Series([3.94 + 0.0001 * (i % 5) for i in range(60)], index=idx)
    rs = D.ratio_stats(30700.0, 7812.0, 30883.15 / 7811.54, 30850.0 / 7813.04, hist)
    assert rs["ratio"] == pytest.approx(30700.0 / 7812.0)
    assert rs["day_bp"] == pytest.approx(((30700.0 / 7812.0) / (30883.15 / 7811.54) - 1) * 1e4)    # about -60 bp
    assert rs["z"] < -5 and rs["hist_n"] == 60                                     # far below a 3.94-3.9404 history
    assert "ratio NDX/SPX 3.9299" in D.ratio_line(rs) and "day -60 bp" in D.ratio_line(rs)
    assert D.ratio_stats(30700.0, 7812.0, None, None, pd.Series(dtype=float)).get("z") is None
    up, down = D.ratio_menu(30707.4, 7812.3)
    assert up == ("ratio up", [("sell", "P", 30700.0), ("buy", "P", 30675.0)], [("sell", "C", 7815.0), ("buy", "C", 7820.0)])
    assert down == ("ratio down", [("sell", "C", 30725.0), ("buy", "C", 30750.0)], [("sell", "P", 7810.0), ("buy", "P", 7805.0)])


def leg(symbol: str, bid: float, ask: float, source: str = "tastytrade") -> dict:
    return {"symbol": symbol, "bid": bid, "ask": ask, "mid": round((bid + ask) / 2, 4), "source": source}


@pytest.fixture
def desk(monkeypatch, tmp_path):
    """The desk with the service stubbed: previews by underlying, orders recorded, a flat book, 13:30 ET."""
    monkeypatch.setattr(D, "STATE_DIR", tmp_path)
    monkeypatch.setattr(D, "now_et", lambda: pd.Timestamp("2026-10-12 13:30", tz=NY))
    monkeypatch.setattr(D, "journal", lambda day, text: None)
    monkeypatch.setattr(D, "day_pnl", lambda day: (0.0, 0.0, []))
    monkeypatch.setattr(D, "ratio_now", lambda: {"ndx": 30700.0, "spx": 7812.0, "ratio": 3.93})
    monkeypatch.setattr(D, "PREMIUM_ONLY", True); monkeypatch.setattr(D, "MAX_RISK", 2500.0)
    monkeypatch.setattr(D, "MAX_TRADES", 3); monkeypatch.setattr(D, "MAX_LOTS", 2)
    monkeypatch.setattr(D, "SETTLE_S", 0.0)
    monkeypatch.setattr(D, "ratio_range_today", lambda: 40.0)          # a mid ratio day at 13:30
    # live spot and at-the-money straddle per index: NDX_UP's short put 30700 sits 100 below (room 75), SPX_UP's short
    # call 7815 sits 15 above (room 10), so the agent's styles pass the far rule
    monkeypatch.setattr(D, "live_straddle", lambda under, day: {"NDX": (30800.0, 50.0), "SPX": (7800.0, 10.0)}[under])
    pv = {"NDX": {"ok": True, "net_mid": -9.0, "debit_credit": "credit", "max_loss": -1600.0,
                  "legs": [leg("NDXP261012P30700000", 20.0, 22.0), leg("NDXP261012P30675000", 11.0, 13.0)]},
          "SPX": {"ok": True, "net_mid": -2.0, "debit_credit": "credit", "max_loss": -600.0,
                  "legs": [leg("SPXW261012C07815000", 4.9, 5.0), leg("SPXW261012C07820000", 2.9, 3.0)]}}
    monkeypatch.setattr(D, "preview", lambda legs, lots, day, under="NDX": dict(pv[under]))
    sent, fills = [], {"NDX": "filled", "SPX": "filled"}

    def api(method, path, body=None, timeout=20.0):
        sent.append((method, path, body))
        if path == "/orders":
            return {"status": fills[body["underlying"]], "trade_group_id": f"TG-{body['underlying']}",
                    "fill_price": -9.0 if body["underlying"] == "NDX" else -2.0}
        return {"status": "filled"}
    monkeypatch.setattr(D, "api", api)
    closed = []
    monkeypatch.setattr(D, "_close_all", lambda day, reason: closed.append(reason) or [f"CLOSED ({reason})"])
    return {"pv": pv, "sent": sent, "fills": fills, "closed": closed, "dir": tmp_path}


NDX_UP = [{"side": "sell", "cp": "P", "strike": 30700.0}, {"side": "buy", "cp": "P", "strike": 30675.0}]
SPX_UP = [{"side": "sell", "cp": "C", "strike": 7815.0}, {"side": "buy", "cp": "C", "strike": 7820.0}]


def test_a_pair_opens_both_spreads_as_one_position(desk):
    rc = D.cmd_pair(NDX_UP, 1, SPX_UP, 2, "ratio -60 bp, turning", "half the credit or 30 min", "ratio makes a new low",
                    stop_bp=40.0)
    assert rc == 0
    orders = [b for m, p, b in desk["sent"] if p == "/orders"]
    assert [o["underlying"] for o in orders] == ["NDX", "SPX"] and orders[1]["legs"][0]["symbol"].startswith("SPXW")
    st = D.load_state(pd.Timestamp("2026-10-12").date())
    assert st["positions"]["TG-NDX"]["pair"] == "TG-SPX" and st["positions"]["TG-SPX"]["pair_of"] == "TG-NDX"
    assert st["positions"]["TG-SPX"]["under"] == "SPX" and D.trades_today(st) == 1


def test_a_pair_over_the_risk_rail_or_with_a_debit_is_refused(desk, capsys):
    desk["pv"]["SPX"]["max_loss"] = -1000.0                                     # 1,600 + 1,000 > 2,500
    assert D.cmd_pair(NDX_UP, 1, SPX_UP, 2, "t", "e", "w", stop_bp=40.0) == 2
    assert "max loss 2,600" in capsys.readouterr().out and not [p for m, p, b in desk["sent"] if p == "/orders"]
    desk["pv"]["SPX"]["max_loss"] = -600.0
    desk["pv"]["NDX"]["debit_credit"] = "debit"
    assert D.cmd_pair(NDX_UP, 1, SPX_UP, 2, "t", "e", "w", stop_bp=40.0) == 2 and "premium only" in capsys.readouterr().out


def test_half_a_pair_is_never_held(desk, capsys):
    desk["fills"]["SPX"] = "rejected"
    assert D.cmd_pair(NDX_UP, 1, SPX_UP, 2, "t", "e", "w", stop_bp=40.0) == 3
    assert desk["closed"] and "never hold half a pair" in desk["closed"][0]


def test_a_pair_never_sells_an_in_the_money_strike(desk, capsys, monkeypatch):
    """2026-10-12: the 30650/30625 put spread sold 22 points in the money lost $334 while NDX sat at 30,625; the
    out-of-the-money 30625/30600 would have made about $317 by 15:24. Fit the rail with fewer SPX lots instead."""
    assert "22 points in the money" in D.itm_short([{"side": "sell", "cp": "P", "strike": 30650.0},
                                                   {"side": "buy", "cp": "P", "strike": 30625.0}], 30628.0, "NDX")
    assert D.itm_short([{"side": "sell", "cp": "P", "strike": 30625.0}, {"side": "buy", "cp": "P", "strike": 30600.0}],
                       30628.0, "NDX") is None                                    # 3 points out of the money
    assert D.itm_short([{"side": "sell", "cp": "P", "strike": 30630.0}], 30628.0, "NDX") is None   # within 5: at the money
    assert D.itm_short([{"side": "sell", "cp": "C", "strike": 7800.0}], 7799.5, "SPX") is None
    assert "in the money" in D.itm_short([{"side": "sell", "cp": "C", "strike": 7795.0}], 7799.5, "SPX")
    assert D.itm_short([{"side": "sell", "cp": "C", "strike": 7795.0}], None, "SPX") is None
    monkeypatch.setattr(D, "quote", lambda t: {"last": 30628.0} if t == "NDX" else {"last": 7799.5})
    itm = [{"side": "sell", "cp": "P", "strike": 30650.0}, {"side": "buy", "cp": "P", "strike": 30625.0}]
    assert D.cmd_pair(itm, 1, SPX_UP, 2, "t", "e", "w", stop_bp=40.0) == 2
    assert "points in the money" in capsys.readouterr().out and not [p for m, p, b in desk["sent"] if p == "/orders"]
    otm = [{"side": "sell", "cp": "P", "strike": 30625.0}, {"side": "buy", "cp": "P", "strike": 30600.0}]
    spx = [{"side": "sell", "cp": "C", "strike": 7800.0}, {"side": "buy", "cp": "C", "strike": 7805.0}]
    assert D.cmd_pair(otm, 1, spx, 2, "t", "e", "w", stop_bp=40.0) == 0


# ── quotes an entry can trust (2026-10-13: a re-subscribed SPXW leg served a minutes-old quote first) ─────────────

def test_quote_problems_catch_stale_and_one_sided_quotes():
    v = [{"side": "sell", "cp": "C", "strike": 7790.0}, {"side": "buy", "cp": "C", "strike": 7795.0}]
    good = {"net_mid": -2.5, "max_loss": -250.0, "max_profit": 250.0,
            "legs": [leg("SPXW261013C07790000", 7.0, 7.1), leg("SPXW261013C07795000", 4.5, 4.6)]}
    assert D.quote_problems(good, good, v, "SPX") == [] and D.shown_net(good, v) == "-2.5"
    # the 11:28 menu: the long leg had no quote, so the 5-wide spread "paid" the short leg's whole 7.05
    one_sided = {"net_mid": -7.05, "max_loss": 205.0, "max_profit": 705.0,
                 "legs": [leg("SPXW261013C07790000", 7.0, 7.1), leg("SPXW261013C07795000", 0.0, 0.0)]}
    why = " | ".join(D.quote_problems(one_sided, one_sided, v, "SPX"))
    assert "no sane two-sided quote" in why and "not between 0 and 5" in why and "no loss" in why
    assert D.shown_net(one_sided, v) == "-7.05 (quotes settling)"
    # 11:30: the first preview served the 7770/7775 calls' old quotes, the next one 3 s later the live ones
    k = [{"side": "sell", "cp": "C", "strike": 7770.0}, {"side": "buy", "cp": "C", "strike": 7775.0}]
    stale = {"net_mid": -4.85, "max_loss": -15.0,
             "legs": [leg("SPXW261013C07770000", 29.0, 29.3), leg("SPXW261013C07775000", 24.2, 24.4)]}
    live = {"net_mid": -4.25, "max_loss": -75.0,
            "legs": [leg("SPXW261013C07770000", 20.4, 20.5), leg("SPXW261013C07775000", 16.1, 16.3)]}
    why = D.quote_problems(stale, live, k, "SPX")
    assert len(why) == 2 and all("still settling" in w for w in why)
    # an NDXP leg's mid wobbles a few points between polls with nothing wrong
    n = [{"side": "sell", "cp": "P", "strike": 30400.0}, {"side": "buy", "cp": "P", "strike": 30375.0}]
    a = {"net_mid": -9.0, "max_loss": -1600.0,
         "legs": [leg("NDXP261013P30400000", 40.0, 46.0), leg("NDXP261013P30375000", 31.0, 37.0)]}
    b = {"net_mid": -8.0, "max_loss": -1700.0,
         "legs": [leg("NDXP261013P30400000", 42.0, 48.0), leg("NDXP261013P30375000", 34.0, 40.0)]}
    assert D.quote_problems(a, b, n, "NDX") == []
    assert D.vertical_width(n) == 25.0 and D.vertical_width(n + n) is None


def test_an_entry_waits_for_settled_quotes(desk, capsys, monkeypatch):
    """pair and open preview twice and refuse while a leg is still jumping or a vertical's net is impossible."""
    calls = []
    stale = {"ok": True, "net_mid": -2.0, "debit_credit": "credit", "max_loss": -600.0,
             "legs": [leg("SPXW261012C07815000", 9.9, 10.0), leg("SPXW261012C07820000", 7.9, 8.0)]}

    def preview(legs, lots, day, under="NDX"):
        calls.append(under)
        return dict(stale if under == "SPX" and calls.count("SPX") == 1 else desk["pv"][under])
    monkeypatch.setattr(D, "preview", preview)
    assert D.cmd_pair(NDX_UP, 1, SPX_UP, 2, "t", "e", "w", stop_bp=40.0) == 2
    out = capsys.readouterr().out
    assert "SPX: SPXW261012C07815000 quote still settling (9.95 -> 4.95" in out
    assert not [p for m, p, b in desk["sent"] if p == "/orders"]
    assert D.cmd_pair(NDX_UP, 1, SPX_UP, 2, "t", "e", "w", stop_bp=40.0) == 0                     # the retry sees live quotes twice
    bad = {"ok": True, "net_mid": -26.0, "debit_credit": "credit", "max_loss": 100.0,
           "legs": [leg("NDXP261012P30700000", 30.0, 32.0), leg("NDXP261012P30675000", 4.0, 6.0)]}
    monkeypatch.setattr(D, "preview", lambda legs, lots, day, under="NDX": dict(bad))
    assert D.cmd_open(NDX_UP, 1, "t", "e", "w") == 2
    out = capsys.readouterr().out
    assert "not between 0 and 25" in out and "no loss" in out


def test_open_checks_single_spreads_too(desk, capsys, monkeypatch):
    """The out-of-the-money rule applies to every desk order, not only pairs; clean quotes still open."""
    monkeypatch.setattr(D, "quote", lambda t: {"last": 30628.0})
    itm = [{"side": "sell", "cp": "P", "strike": 30650.0}, {"side": "buy", "cp": "P", "strike": 30625.0}]
    assert D.cmd_open(itm, 1, "t", "e", "w") == 2 and "22 points in the money" in capsys.readouterr().out
    otm = [{"side": "sell", "cp": "P", "strike": 30600.0}, {"side": "buy", "cp": "P", "strike": 30575.0}]
    monkeypatch.setattr(D, "preview", lambda legs, lots, day, under="NDX": pv_for(legs, [30.0, 21.0]))
    assert D.cmd_open(otm, 1, "t", "e", "w", stops=[30450.0]) == 0           # a stop 178 below, priced by the gate
    assert "GATE ok" in capsys.readouterr().out
    assert [b["underlying"] for m, p, b in desk["sent"] if p == "/orders"] == ["NDX"]


# ── the judgment gate (2026-10-13, the owner: "Improve judgement process") ─────────────────────────────────────

DAY13 = pd.Timestamp("2026-10-13").date()


def pv_for(legs, mids, half=1.0, day=DAY13):
    """A settled credit preview whose legs carry the order's own OCC symbols and the given mids."""
    q = [leg(D.occ(l["cp"], l["strike"], day), m - half, m + half) for l, m in zip(legs, mids)]
    net = sum((-m if l["side"] == "sell" else m) for l, m in zip(legs, mids))
    return {"ok": True, "net_mid": round(net, 4), "debit_credit": "credit" if net < 0 else "debit",
            "max_loss": -2000.0, "max_profit": abs(net) * 100, "legs": q}


def test_the_stop_table_reads_like_the_study():
    """743 sessions of NDX minutes: nearer stops and wilder days are touched more often; the safe distance widens."""
    near, far = D.stop_hit_prob("13:30", "up", 40, 150.0), D.stop_hit_prob("13:30", "up", 100, 150.0)
    assert 0 < far < near < 1
    assert D.stop_hit_prob("13:30", "up", 65, 400.0) > D.stop_hit_prob("13:30", "up", 65, 120.0)    # wild vs calm
    assert D.wildness("13:30", 120.0) == "calm" and D.wildness("13:30", 400.0) == "wild"
    assert D.safe_stop("13:30", "up", 400.0) > D.safe_stop("13:30", "up", 120.0)
    assert D.stop_hit_prob("13:30", "up", 5, 150.0) == D.stop_hit_prob("13:30", "up", 20, 150.0)    # nearer than the table
    # past the table's last row (200) the odds keep falling instead of repeating the 200-point row
    p200, p300 = D.stop_hit_prob("11:30", "up", 200, 400.0), D.stop_hit_prob("11:30", "up", 300, 400.0)
    assert 0 < p300 < p200


def test_black_scholes_round_trip():
    t = D.years_left(pd.Timestamp("2026-10-13 13:48", tz=NY))
    px = D.bs_price("C", 30511.0, 30600.0, t, 0.18)
    assert D.implied_vol("C", px, 30511.0, 30600.0, t) == pytest.approx(0.18, abs=1e-4)
    assert D.implied_vol("C", 0.0, 30511.0, 30600.0, t) is None                      # nothing above intrinsic
    assert D.leg_key("NDXP261013C30600000") == ("C", 30600.0)


def test_the_gate_refuses_todays_second_trade():
    """2026-10-13 13:48: the 30600/30625 call spread sold at 1.10 with NDX 30,511 on a 224-point day; its stop at
    30,580 sat where a third of such days reach, for $88 kept against about $500 lost there."""
    legs = [{"side": "sell", "cp": "C", "strike": 30600.0}, {"side": "buy", "cp": "C", "strike": 30625.0}]
    t = pd.Timestamp("2026-10-13 13:48", tz=NY)
    g, why = D.judge_entry(legs, pv_for(legs, [4.0, 2.9]), [30580.0], 30511.0, t, 224.0, 1)
    assert why and g["ev"] < 0 and g["stops"][0]["loss"] > 300
    # the mark stop it really ran on (3.5) sat about 30 points away: inside the noise outright
    g2, why2 = D.judge_entry(legs, pv_for(legs, [4.0, 2.9]), [30540.0], 30511.0, t, 224.0, 1)
    assert any("inside the noise" in w for w in why2)
    assert D.judge_entry(legs, pv_for(legs, [4.0, 2.9]), [], 30511.0, t, 224.0, 1)[1][0].startswith("a credit trade needs")


def test_the_gate_passes_a_wide_stop_on_a_calm_day():
    legs = [{"side": "sell", "cp": "C", "strike": 30600.0}, {"side": "buy", "cp": "C", "strike": 30625.0}]
    t = pd.Timestamp("2026-10-13 14:00", tz=NY)
    g, why = D.judge_entry(legs, pv_for(legs, [3.6, 1.6]), [30700.0], 30500.0, t, 120.0, 1)
    assert why == [] and g["wild"] == "calm" and g["ev"] > 10 and g["stops"][0]["p_hit"] < 0.1
    # a wild day needs the wider stop even when the odds look fine
    g, why = D.judge_entry(legs, pv_for(legs, [3.6, 1.6]), [30620.0], 30500.0, t, 420.0, 1)
    assert any("wild day" in w for w in why)
    # a debit is not the gate's business (premium_only refuses it)
    assert D.judge_entry(legs, {"net_mid": 2.0, "legs": []}, [], 30500.0, t, 120.0, 1) == ({}, [])


def test_a_settlement_beyond_is_half_the_touch_and_the_tail_keeps_falling():
    p100 = D.stop_hit_prob("14:00", "up", 100, 400.0)
    assert D.finish_beyond_prob("14:00", "up", 100, 400.0) == pytest.approx(p100 / 2)
    assert 0 < D.finish_beyond_prob("14:00", "up", 400, 400.0) < D.finish_beyond_prob("14:00", "up", 200, 400.0)
    assert D.zone_outcomes("14:00", "up", 100.0, 25.0, 80.0, 400.0) == []         # a stop inside the short strike


def test_the_gate_counts_a_settlement_past_the_short_strike_that_never_touched_the_stop():
    """2026-10-16 13:36, NDX 29,332 on a 595-point day, the stop at VWAP 29,533: the 29400/29425 call spread at 7.55
    printed +$415 because it kept the credit whenever 29,533 held; a 29,400-29,533 settlement costs it (+$146)."""
    legs = [{"side": "sell", "cp": "C", "strike": 29400.0}, {"side": "buy", "cp": "C", "strike": 29425.0}]
    t = pd.Timestamp("2026-10-16 13:36", tz=NY)
    g, _ = D.judge_entry(legs, pv_for(legs, [37.55, 30.0]), [29533.0], 29332.0, t, 595.0, 1)
    old = (1 - g["p_any"]) * g["keep"] - g["p_any"] * g["stops"][0]["loss"]
    assert 0.1 < g["p_zone"] < 0.2 and g["zone_value"] < 0 and 50 < g["ev"] < old - 200
    # a stop inside the short strike leaves nothing between them
    g2, _ = D.judge_entry(legs, pv_for(legs, [37.55, 30.0]), [29390.0], 29332.0, t, 595.0, 1)
    assert g2["p_zone"] == 0


def test_quote_prices_and_gates_each_candidate_without_an_order(desk, capsys, monkeypatch):
    monkeypatch.setattr(D, "market", lambda: {"spot": 30650.0, "high": 30800.0, "low": 30600.0})
    desk["pv"]["NDX"] = {"ok": True, "net_mid": -3.0, "legs": [leg("NDXP261012C30700000", 9.0, 11.0),
                                                              leg("NDXP261012C30725000", 6.0, 8.0)]}
    assert D.main(["quote", "--vertical", "C:30700:30725", "--stop", "30900", "--stop", "30500"]) == 0
    out = capsys.readouterr().out
    assert "credit mid 3.00, natural 1.00" in out and "stop 30,900 (250 up)" in out
    assert "30,500" not in out                                                     # a put-side stop is not a call's
    assert not [s for s in desk["sent"] if s[1] == "/orders"]


def test_open_needs_a_stop_and_the_planned_credit(desk, capsys, monkeypatch):
    monkeypatch.setattr(D, "quote", lambda t: {"last": 30628.0})
    otm = [{"side": "sell", "cp": "P", "strike": 30600.0}, {"side": "buy", "cp": "P", "strike": 30575.0}]
    monkeypatch.setattr(D, "preview", lambda legs, lots, day, under="NDX": pv_for(legs, [30.0, 21.0]))
    assert D.cmd_open(otm, 1, "t", "e", "w") == 2 and "needs --stop" in capsys.readouterr().out
    assert D.cmd_open(otm, 1, "t", "e", "w", stops=[30450.0], min_credit=12.0) == 2
    assert "under the planned 12.00" in capsys.readouterr().out
    assert not [p for m, p, b in desk["sent"] if p == "/orders"]


def test_judge_logs_a_pass(desk, monkeypatch):
    monkeypatch.setattr(D, "market", lambda: {"spot": 30511.0, "high": 30596.0, "low": 30372.0, "range10": 30.0,
                                             "range30": 55.0})
    assert D.cmd_judge("failed bounce", "pass", "only a 14-point dip, not a lower high") == 0
    rows = (desk["dir"] / D.JUDGMENTS).read_text(encoding="utf-8").splitlines()
    assert rows[0].startswith("ts,setup,action") and "failed bounce,pass" in rows[1] and ",mid," in rows[1]


# ── the ratio pair's gate (2026-10-15, the owner chose: the expert trades the ratio by judgment) ─────────────────

def test_the_ratio_table_reads_like_the_study():
    """499 sessions of NDX/SPX minutes: nearer ratio stops and wilder ratio days are touched more often."""
    rt = D.ratio_table()
    near, far = D.stop_hit_prob("11:00", "down", 10, 40.0, rt), D.stop_hit_prob("11:00", "down", 30, 40.0, rt)
    assert 0 < far < near < 1
    assert D.stop_hit_prob("11:00", "up", 20, 80.0, rt) > D.stop_hit_prob("11:00", "up", 20, 20.0, rt)
    assert D.safe_stop("14:30", "up", 30.0, rt) < D.safe_stop("11:00", "up", 30.0, rt)      # later: tighter is fine
    assert D.pair_bet(NDX_UP) == "up" and D.pair_bet([{"side": "sell", "cp": "C", "strike": 1.0}]) == "down"


def test_a_pair_stop_must_clear_the_ratio_noise(desk, capsys):
    """A 5 bp ratio stop at 13:30 is touched most days: refused. The pair's credit must reach the one judged."""
    assert D.cmd_pair(NDX_UP, 1, SPX_UP, 2, "t", "e", "w", stop_bp=5.0) == 2
    assert "sits inside the noise" in capsys.readouterr().out
    assert D.cmd_pair(NDX_UP, 1, SPX_UP, 2, "t", "e", "w", stop_bp=40.0, min_credit_usd=2000.0) == 2
    assert "under the planned $2,000" in capsys.readouterr().out             # 9.00 + 2 x 2.00 = $1,300 of credit
    assert not [p for m, p, b in desk["sent"] if p == "/orders"]
    assert D.cmd_pair(NDX_UP, 1, SPX_UP, 2, "t", "e", "w", stop_bp=40.0, min_credit_usd=1200.0) == 0
    assert "GATE ok: ratio up" in capsys.readouterr().out
    st = D.load_state(pd.Timestamp("2026-10-12").date())
    assert st["positions"]["TG-NDX"]["stop_bp"] == 40.0 and st["positions"]["TG-NDX"]["bet"] == "up"


# ── the AI agent's own strategies (2026-10-20, the owner: "i want the AI Agent to trade the clone strategy", "and also
# the ratio strategy", "all decisions on the fly by AI"): the stop tables do not second-guess it, the rails still hold ──

def test_a_clone_trade_sits_far_on_spx_and_skips_the_stop_gate_but_not_the_rails(desk, capsys, monkeypatch):
    """From 2026-10-26 the clone is agent-only (its robot is deleted): the agent's read picks the side, the trade is
    SPX only (NDX far premium lost at NDXP's cost in the 10/25 baselines) and the short must sit at least
    max(20, 1.2 x straddle) below SPX for puts; a near-the-money spread is refused."""
    monkeypatch.setattr(D, "quote", lambda t: {"last": 30628.0 if t == "NDX" else 6560.0})
    monkeypatch.setattr(D, "live_straddle", lambda under, day: (30628.0, 60.0) if under == "NDX" else (6560.0, 29.0))
    monkeypatch.setattr(D, "preview", lambda legs, lots, day, under="NDX": pv_for(legs, [4.0, 3.0]))
    ndx = [{"side": "sell", "cp": "P", "strike": 30550.0}, {"side": "buy", "cp": "P", "strike": 30525.0}]
    assert D.cmd_open(ndx, 1, "t", "e", "w", style="clone") == 2 and "SPX only" in capsys.readouterr().out
    near = [{"side": "sell", "cp": "P", "strike": 6550.0}, {"side": "buy", "cp": "P", "strike": 6530.0}]
    assert D.cmd_open(near, 1, "t", "e", "w", style="clone", under="SPX") == 2
    out = capsys.readouterr().out
    assert "inside the far room 35" in out and "nearest allowed strike is 6525" in out
    far = [{"side": "sell", "cp": "P", "strike": 6525.0}, {"side": "buy", "cp": "P", "strike": 6505.0}]
    assert D.cmd_open(far, 1, "bull read: SPX holding its session average", "held to the close", "a lower low",
                      style="clone", under="SPX") == 0
    assert "STYLE clone" in capsys.readouterr().out
    assert [b["underlying"] for m, p, b in desk["sent"] if p == "/orders"] == ["SPX"]
    st = D.load_state(pd.Timestamp("2026-10-12").date())
    assert [(v["style"], v["under"]) for v in st["positions"].values()] == [("clone", "SPX")]
    # the rails still hold: a debit, a max loss over the rail, a bad style, a condor's 4 legs
    monkeypatch.setattr(D, "preview", lambda legs, lots, day, under="NDX": {**pv_for(legs, [4.0, 3.0]),
                                                                            "debit_credit": "debit"})
    monkeypatch.setattr(D, "day_pnl", lambda day: (0.0, 0.0, []))
    assert D.cmd_open(far, 1, "t", "e", "w", style="clone", under="SPX") == 2 and "premium only" in capsys.readouterr().out
    monkeypatch.setattr(D, "preview", lambda legs, lots, day, under="NDX": {**pv_for(legs, [4.0, 3.0]),
                                                                            "max_loss": -3000.0})
    assert D.cmd_open(far, 1, "t", "e", "w", style="clone", under="SPX") == 2 and "over $2,500" in capsys.readouterr().out
    assert D.cmd_open(far, 1, "t", "e", "w", style="robot", under="SPX") == 2 and "style must be" in capsys.readouterr().out
    assert D.cmd_open(far + far, 1, "t", "e", "w", style="clone", under="SPX") == 2
    assert "one far vertical" in capsys.readouterr().out
    assert len([p for m, p, b in desk["sent"] if p == "/orders"]) == 1


def test_a_ratio_style_pair_skips_the_noise_table_but_not_the_rails(desk, capsys):
    assert D.cmd_pair(NDX_UP, 1, SPX_UP, 2, "t", "e", "w", stop_bp=5.0) == 2               # the noise table refuses
    assert "sits inside the noise" in capsys.readouterr().out
    assert D.cmd_pair(NDX_UP, 1, SPX_UP, 2, "t", "e", "w", stop_bp=40.0, min_credit_usd=2000.0, style="ratio") == 2
    assert "under the planned $2,000" in capsys.readouterr().out                              # its own credit plan holds
    desk["pv"]["SPX"]["max_loss"] = -1000.0
    assert D.cmd_pair(NDX_UP, 1, SPX_UP, 2, "t", "e", "w", style="ratio") == 2
    assert "max loss 2,600" in capsys.readouterr().out                                        # the risk rail holds
    desk["pv"]["SPX"]["max_loss"] = -600.0
    assert not [p for m, p, b in desk["sent"] if p == "/orders"]
    assert D.cmd_pair(NDX_UP, 1, SPX_UP, 2, "ratio overshoot turning on the news", "back to the 30-min mean",
                      "a new ratio low", stop_bp=5.0, style="ratio") == 0                     # its own stop, no table
    assert "STYLE ratio" in capsys.readouterr().out
    st = D.load_state(pd.Timestamp("2026-10-12").date())
    assert st["positions"]["TG-NDX"]["bet"] == "up" and st["positions"]["TG-NDX"]["stop_bp"] == 5.0


# ── two positions at once (2026-10-23, the owner: "2 positions, $2,500 each") ────────────────────────────────────────

def test_the_rail_counts_positions_not_trade_groups():
    """A ratio pair's SPX leg and a trim's offsetting group belong to their parent: five groups, two positions."""
    st = {"positions": {"N": {"pair": "S"}, "S": {"pair_of": "N"}, "T": {"trim_of": "N"}, "C": {}, "U": {"trim_of": "C"}}}
    opened = [{"trade_group_id": g} for g in ("N", "S", "T", "C", "U")]
    assert D.n_positions(opened, st) == 2 and D.n_positions([], st) == 0
    assert D.linked_groups("S", st) == {"N", "S", "T"} and D.linked_groups("N", st) == {"N", "S", "T"}
    assert D.linked_groups("U", st) == {"C", "U"} and D.linked_groups("X", st) == {"X"}


def test_a_pair_opens_beside_one_position_but_not_beside_two(desk, capsys, monkeypatch):
    """10/22: four clone calls passed only because a premium trade held the single slot. With two slots a ratio pair
    (one position) opens beside it; a third position is refused."""
    day = pd.Timestamp("2026-10-12").date()
    D.save_state(day, {"done": False, "positions": {"TG-HELD": {"lots": 1, "legs": []}}, "closed": []})
    held = {"trade_group_id": "TG-HELD", "pnl": 50.0}
    monkeypatch.setattr(D, "MAX_POSITIONS", 2)
    monkeypatch.setattr(D, "day_pnl", lambda d: (0.0, 50.0, [held]))
    assert D.cmd_pair(NDX_UP, 1, SPX_UP, 2, "t", "e", "w", stop_bp=40.0, style="ratio") == 0
    capsys.readouterr()
    both = [held, {"trade_group_id": "TG-NDX"}, {"trade_group_id": "TG-SPX"}]
    monkeypatch.setattr(D, "day_pnl", lambda d: (0.0, 50.0, both))
    assert D.cmd_pair(NDX_UP, 1, SPX_UP, 2, "t", "e", "w", stop_bp=40.0, style="ratio") == 2
    assert "2 position(s) open, the limit is 2" in capsys.readouterr().out
    monkeypatch.setattr(D, "MAX_POSITIONS", 1)                                   # the old rail still works as before
    monkeypatch.setattr(D, "day_pnl", lambda d: (0.0, 50.0, [held]))
    assert D.cmd_pair(NDX_UP, 1, SPX_UP, 2, "t", "e", "w", stop_bp=40.0, style="ratio") == 2


def _book(monkeypatch, tmp_path, groups: dict):
    monkeypatch.setattr(D, "STATE_DIR", tmp_path)
    monkeypatch.setattr(D, "journal", lambda day, text: None)
    monkeypatch.setattr(D, "now_et", lambda: pd.Timestamp("2026-10-26 13:40", tz=NY))
    day = pd.Timestamp("2026-10-26").date()
    D.save_state(day, {"done": False, "positions": groups, "closed": [], "last_news": None})
    monkeypatch.setattr(D, "my_positions", lambda status="open": [
        {"trade_group_id": g, "structure": g, "contracts": 1, "pnl": 0.0} for g in groups])
    sent = []

    def api(method, path, body=None, timeout=20.0):
        sent.append(path)
        return {"status": "filled", "fill_price": 1.0, "trade_group_id": "TG-TRIM"}
    monkeypatch.setattr(D, "api", api)
    return day, sent


def test_close_can_name_one_position_and_takes_its_pair_leg_with_it(monkeypatch, tmp_path):
    day, sent = _book(monkeypatch, tmp_path, {"P": {"lots": 1}, "N": {"lots": 1, "pair": "S"},
                                              "S": {"lots": 2, "pair_of": "N"}})
    out = D._close_all(day, "the ratio read is done", only="S")
    assert sorted(sent) == ["/paper/positions/N/close", "/paper/positions/S/close"] and len(out) == 2
    sent.clear()
    assert len(D._close_all(day, "flat at 15:55")) == 3 and len(sent) == 3          # unnamed: everything, as the guard


def test_trim_needs_a_name_when_two_positions_are_open(monkeypatch, tmp_path, capsys):
    legs = [{"side": "sell", "cp": "C", "strike": 29100.0}, {"side": "buy", "cp": "C", "strike": 29125.0}]
    day, sent = _book(monkeypatch, tmp_path, {"A": {"lots": 2, "legs": legs}, "B": {"lots": 2, "legs": legs}})
    assert D.cmd_trim(1, "half off", None) == 2 and "name one with --tg" in capsys.readouterr().out
    assert not sent
    assert D.cmd_trim(1, "half off", "B") == 0 and sent == ["/orders"]
    st = D.load_state(day)
    assert st["positions"]["TG-TRIM"]["trim_of"] == "B" and st["positions"]["B"]["trimmed"] == 1


# ── the SPX 13:00 iron condor (2026-10-25, the owner: "Its goes to the desk", "An agent runs it") ───────────────────

CONDOR = [{"side": "sell", "cp": "C", "strike": 7650.0}, {"side": "buy", "cp": "C", "strike": 7660.0},
          {"side": "sell", "cp": "P", "strike": 7615.0}, {"side": "buy", "cp": "P", "strike": 7595.0}]


def test_condor_strikes_scale_with_the_13h_straddle():
    calm = D.condor_strikes(7639.19, 11.0)                     # rooms 10 / 20: the floors
    assert calm["call"] == (7650.0, 7660.0) and calm["put"] == (7615.0, 7595.0)
    wild = D.condor_strikes(6560.0, 29.0)                      # 2026-04-02: rooms 23.2 / 34.8
    assert wild["call"] == (6585.0, 6595.0) and wild["put"] == (6525.0, 6505.0)
    assert wild["call_room"] == pytest.approx(23.2) and wild["put_room"] == pytest.approx(34.8)


def test_month_end_is_the_months_last_business_day():
    d = lambda s: pd.Timestamp(s).date()
    assert D.month_end(d("2026-10-30")) and not D.month_end(d("2026-10-29"))      # Oct 31 is a Saturday
    assert D.month_end(d("2026-04-30")) and not D.month_end(d("2026-05-01"))


def test_the_condor_menu_prices_both_sides_from_the_live_straddle(monkeypatch, capsys):
    monkeypatch.setattr(D, "now_et", lambda: pd.Timestamp("2026-04-02 13:00", tz=NY))
    monkeypatch.setattr(D, "quote", lambda t: {"last": 6560.0})
    monkeypatch.setattr(D, "MAX_RISK", 2500.0)

    def preview(legs, lots, d, under="NDX"):
        if all(l["side"] == "buy" for l in legs):              # the straddle: 11.90 + 17.10
            return {"legs": [{"symbol": "c", "mid": 11.9}, {"symbol": "p", "mid": 17.1}]}
        syms = [D.occ(l["cp"], l["strike"], d, "SPXW") for l in legs]
        return {"ok": True, "net_mid": -1.49 if len(legs) == 2 else -2.6,
                "max_loss": -851.0 if len(legs) == 2 else -1740.0,
                "legs": [{"symbol": s, "bid": 1.0, "ask": 1.2, "mid": 1.1} for s in syms]}
    monkeypatch.setattr(D, "preview", preview)
    monkeypatch.setattr(D, "api", lambda *a, **k: {})
    assert D.cmd_condor() == 0
    out = capsys.readouterr().out
    assert "straddle 29.00 at 6560" in out and "sell C6585 / buy C6595" in out and "sell P6525 / buy P6505" in out
    assert "fits 1 lot(s)" in out and "--leg sell:C:6585" in out and "--leg buy:P:6505" in out


def test_the_agent_opens_the_spx_condor_inside_its_window(desk, capsys, monkeypatch):
    day = pd.Timestamp("2026-10-12").date()
    pv = {"ok": True, "net_mid": -2.8, "debit_credit": "credit", "max_loss": -1720.0, "max_profit": 280.0,
          "legs": [leg(D.occ(l["cp"], l["strike"], day, "SPXW"), 1.0, 1.1) for l in CONDOR]}
    monkeypatch.setattr(D, "preview", lambda legs, lots, d, under="NDX": dict(pv) if under == "SPX" else {})
    monkeypatch.setattr(D, "live_straddle", lambda under, d: (7639.19, 11.0))           # rooms 10 above / 20 below
    assert D.cmd_open(CONDOR, 1, "13:00 condor", "hold to the 15:55 flat", "SPX through a short", style="condor",
                      under="SPX") == 0
    assert "STYLE condor" in capsys.readouterr().out
    order = [b for m, p, b in desk["sent"] if p == "/orders"][-1]
    assert order["underlying"] == "SPX" and all(l["symbol"].startswith("SPXW") for l in order["legs"])
    meta = D.load_state(day)["positions"]["TG-SPX"]
    assert meta["style"] == "condor" and meta["under"] == "SPX"


def test_spx_on_the_desk_is_the_clone_or_the_condor_and_the_condor_only_around_13h(desk, capsys, monkeypatch):
    assert D.cmd_open(CONDOR, 1, "t", "e", "w", under="SPX") == 2
    assert "the clone (--style clone) or the 13:00 iron condor" in capsys.readouterr().out
    assert D.cmd_open(CONDOR[:2], 1, "t", "e", "w", style="condor", under="NDX") == 2
    assert "--under SPX" in capsys.readouterr().out
    monkeypatch.setattr(D, "now_et", lambda: pd.Timestamp("2026-10-12 14:05", tz=NY))
    assert D.cmd_open(CONDOR, 1, "t", "e", "w", style="condor", under="SPX") == 2
    assert "12:58-13:30 only" in capsys.readouterr().out
    assert not [p for m, p, b in desk["sent"] if p == "/orders"]


# ── the agent-only clone and ratio, far premium held to the close (2026-10-25: "Rebuild as agent-only") ────────────

def test_far_strikes_scale_with_each_index_straddle():
    spx = D.far_strikes("SPX", 6560.0, 29.0)                   # 2026-04-02: rooms 23.2 / 34.8
    assert (spx["C"]["short"], spx["C"]["long"]) == (6585.0, 6595.0)
    assert (spx["P"]["short"], spx["P"]["long"]) == (6525.0, 6505.0)
    calm = D.far_strikes("NDX", 28957.53, 40.0)                # the floors: 40 above, 75 below; 25-point grid and width
    assert (calm["C"]["short"], calm["C"]["long"]) == (29000.0, 29025.0)
    assert (calm["P"]["short"], calm["P"]["long"]) == (28875.0, 28850.0)


def test_the_far_rule_refuses_a_near_short_and_names_the_nearest_allowed():
    near = [{"side": "sell", "cp": "C", "strike": 6570.0}, {"side": "buy", "cp": "C", "strike": 6580.0}]
    why = D.far_problem(near, "SPX", 6560.0, 29.0)
    assert "inside the far room 23" in why and "nearest allowed strike is 6585" in why
    ok = [{"side": "sell", "cp": "C", "strike": 6585.0}, {"side": "buy", "cp": "C", "strike": 6595.0}]
    assert D.far_problem(ok, "SPX", 6560.0, 29.0) is None
    assert D.far_problem(near, "SPX", 6560.0, None).startswith("no live SPX straddle")


def test_the_far_menu_prices_both_indexes_and_the_ratio_pairs(monkeypatch, capsys):
    monkeypatch.setattr(D, "now_et", lambda: pd.Timestamp("2026-10-26 12:45", tz=NY))
    monkeypatch.setattr(D, "MAX_RISK", 2500.0)
    monkeypatch.setattr(D, "MAX_LOTS", 2)
    monkeypatch.setattr(D, "live_straddle", lambda under, day: {"SPX": (6560.0, 29.0), "NDX": (24000.0, 120.0)}[under])

    def preview(legs, lots, d, under="NDX"):
        return {"ok": True, "net_mid": -1.5, "max_loss": -850.0 if under == "SPX" else -2200.0, "legs": []}
    monkeypatch.setattr(D, "preview", preview)
    monkeypatch.setattr(D, "api", lambda *a, **k: {"c": [6600.0] * 200})          # SPX's session average 6,600
    assert D.cmd_far() == 0
    out = capsys.readouterr().out
    assert "SPX vs its session average 6,600.00: -1.38 straddles" in out and "favours the PUT spread" in out
    assert "NDX clone trades lose at NDXP's cost" in out
    assert "SPX 6,560.00 | straddle 29.00" in out and "sell C6585 / buy C6595" in out and "sell P6525 / buy P6505" in out
    assert "NDX 24,000.00 | straddle 120.00" in out and "sell C24100 / buy C24125" in out
    assert "sell P23850 / buy P23825" in out
    assert "ratio up (NDX puts + SPX calls): 1 NDX lot (max loss 2,200) + 0 SPX lot(s)" in out
