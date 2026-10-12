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
    pv = {"NDX": {"ok": True, "net_mid": -9.0, "debit_credit": "credit", "max_loss": -1600.0,
                  "legs": [{"source": "tastytrade"}, {"source": "tastytrade"}]},
          "SPX": {"ok": True, "net_mid": -2.0, "debit_credit": "credit", "max_loss": -600.0,
                  "legs": [{"source": "tastytrade"}, {"source": "tastytrade"}]}}
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
