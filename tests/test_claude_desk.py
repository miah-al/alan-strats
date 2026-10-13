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
    rc = D.cmd_pair(NDX_UP, 1, SPX_UP, 2, "ratio -60 bp, turning", "half the credit or 30 min", "ratio makes a new low")
    assert rc == 0
    orders = [b for m, p, b in desk["sent"] if p == "/orders"]
    assert [o["underlying"] for o in orders] == ["NDX", "SPX"] and orders[1]["legs"][0]["symbol"].startswith("SPXW")
    st = D.load_state(pd.Timestamp("2026-10-12").date())
    assert st["positions"]["TG-NDX"]["pair"] == "TG-SPX" and st["positions"]["TG-SPX"]["pair_of"] == "TG-NDX"
    assert st["positions"]["TG-SPX"]["under"] == "SPX" and D.trades_today(st) == 1


def test_a_pair_over_the_risk_rail_or_with_a_debit_is_refused(desk, capsys):
    desk["pv"]["SPX"]["max_loss"] = -1000.0                                     # 1,600 + 1,000 > 2,500
    assert D.cmd_pair(NDX_UP, 1, SPX_UP, 2, "t", "e", "w") == 2
    assert "max loss 2,600" in capsys.readouterr().out and not [p for m, p, b in desk["sent"] if p == "/orders"]
    desk["pv"]["SPX"]["max_loss"] = -600.0
    desk["pv"]["NDX"]["debit_credit"] = "debit"
    assert D.cmd_pair(NDX_UP, 1, SPX_UP, 2, "t", "e", "w") == 2 and "premium only" in capsys.readouterr().out


def test_half_a_pair_is_never_held(desk, capsys):
    desk["fills"]["SPX"] = "rejected"
    assert D.cmd_pair(NDX_UP, 1, SPX_UP, 2, "t", "e", "w") == 3
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
    assert D.cmd_pair(itm, 1, SPX_UP, 2, "t", "e", "w") == 2
    assert "points in the money" in capsys.readouterr().out and not [p for m, p, b in desk["sent"] if p == "/orders"]
    otm = [{"side": "sell", "cp": "P", "strike": 30625.0}, {"side": "buy", "cp": "P", "strike": 30600.0}]
    spx = [{"side": "sell", "cp": "C", "strike": 7800.0}, {"side": "buy", "cp": "C", "strike": 7805.0}]
    assert D.cmd_pair(otm, 1, spx, 2, "t", "e", "w") == 0


def test_the_clone_is_a_signal_on_the_desk(tmp_path):
    """The Friend Clone belongs to the desk from 2026-10-13: its shadow runner's calls show in the snapshot, with how
    the premium-only desk would express them."""
    lines = [
        "2026-10-08 13:59:06,659 INFO ndx_0dte_friend_real.rt_switch: AI switch (on) bull entry 30575/30675 at 13:59: TAKE",
        "2026-10-08 13:59:06,679 INFO paper.runner: ALERT 13:58 open bull 30575/30675 @ 67.00 (model | AI TAKE); day +0",
        "2026-10-08 14:01:06,878 INFO paper.runner: ALERT 14:00 add bull 30575/30675 @ 56.70 (add); day +0",
        "2026-10-08 14:02:07,270 INFO paper.runner: ALERT 14:01 close bull 30575/30675 @ 50.30 (cut); day -2,317",
    ]
    ev = D.clone_events(lines)
    assert [(e["at"], e["action"], e["side"], e["k_lo"], e["px"]) for e in ev] == [
        ("13:58", "open", "bull", 30575.0, 67.0), ("14:00", "add", "bull", 30575.0, 56.7), ("14:01", "close", "bull", 30575.0, 50.3)]
    day = pd.Timestamp("2026-10-08").date()
    assert D.clone_line(day, "14:05", tmp_path) == "clone (shadow): not running today"
    (tmp_path / "ndx_0dte_friend_real_2026-10-08_104509.log").write_text("\n".join(lines[:2]), encoding="utf-8")
    line = D.clone_line(day, "14:03", tmp_path)
    assert "13:58 open bull 30575/30675 @ 67.00" in line and "FRESH" in line and "OTM put credit spread below support" in line
    assert "35 min ago" in D.clone_line(day, "14:33", tmp_path)
    (tmp_path / "ndx_0dte_friend_real_2026-10-08_104509.log").write_text("no calls", encoding="utf-8")
    assert D.clone_line(day, "14:03", tmp_path) == "clone (shadow): no call yet today"


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
    assert D.cmd_pair(NDX_UP, 1, SPX_UP, 2, "t", "e", "w") == 2
    out = capsys.readouterr().out
    assert "SPX: SPXW261012C07815000 quote still settling (9.95 -> 4.95" in out
    assert not [p for m, p, b in desk["sent"] if p == "/orders"]
    assert D.cmd_pair(NDX_UP, 1, SPX_UP, 2, "t", "e", "w") == 0                     # the retry sees live quotes twice
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
