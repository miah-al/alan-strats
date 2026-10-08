"""The ratio chart and the spread-vs-spread combo chart (api/services/pair_charts.py, GET /api/market/ratio and
/api/runner/{strategy}/combo-chart): the stretch's formulas, aligning two tickers' minutes, the pair runner's trades
as markers, the structure's legs and its one price. No broker, no network: the bars and candles are injected."""
from __future__ import annotations

import datetime as dt
import json
import math

import numpy as np
import pytest

from api.bootstrap import bootstrap

bootstrap()

from api.services import pair_charts as PC  # noqa: E402

DAY = dt.date(2026, 10, 7)


def _frame(day, closes, start="09:30"):
    t0 = dt.datetime.combine(day, dt.time.fromisoformat(start))
    return {"t": [(t0 + dt.timedelta(minutes=i)).isoformat() for i in range(len(closes))], "c": list(closes),
            "source": "fake", "delayed_minutes": 0}


def test_the_lines_are_the_strategys():
    """On NDX/SPX the ratio chart's EMA, lines and z are ndx_spx_ratio's own (live.signal_series)."""
    try:
        from alan_trader_strategies.strategies.ndx_spx_ratio.live import signal_series
        from alan_trader_strategies.strategies.ndx_spx_ratio.params import RatioParams
    except Exception as exc:
        pytest.skip(f"strategy not installed: {exc}")
    rng = np.random.default_rng(3)
    spx = 7800 * np.exp(np.cumsum(rng.normal(0, 0.0004, 390)))
    ndx = 31000 * np.exp(np.cumsum(rng.normal(0, 0.0004, 390)) + rng.normal(0, 0.00005, 390))
    a = PC.ratio_series(list(ndx), list(spx), 15, 60, 3.0)
    b = signal_series(list(ndx), list(spx), RatioParams())
    for k in ("ratio", "ema", "upper", "lower", "z"):
        for x, y in zip(a[k], b[k]):
            assert (x is None and y is None) or x == pytest.approx(y, rel=1e-12, abs=1e-12)


def test_ratio_aligns_two_tickers_and_carries_a_gap():
    a = _frame(DAY, [100.0, 101.0, 102.0, 103.0])
    b = _frame(DAY, [50.0, 50.0, 51.0])
    b["t"] = [b["t"][0], b["t"][1], a["t"][3]]               # no 09:32 print for B: its 09:31 close carries over
    out = PC.ratio("AAA", "BBB", 2, 5, 3.0, intraday_fn=lambda s: a if s == "AAA" else b)
    assert out["times"] == [t[:16] for t in a["t"]]
    assert out["ratio"] == pytest.approx([2.0, 2.02, 2.04, 103 / 51], rel=1e-6)
    assert out["upper"][0] is None and out["upper"][1] is not None
    assert out["a"] == "AAA" and out["session"] == str(DAY) and out["trades"] == []


def test_ratio_refuses_one_ticker_and_says_which_has_no_bars():
    with pytest.raises(ValueError):
        PC.ratio("NDX", "ndx", intraday_fn=lambda s: _frame(DAY, [1.0]))
    with pytest.raises(LookupError, match="BBB"):
        PC.ratio("AAA", "BBB", intraday_fn=lambda s: _frame(DAY, [1.0, 2.0]) if s == "AAA" else {"t": [], "c": []})


def _state(tmp_path, monkeypatch, fills, ndx=(31000.0,), spx=(7800.0,), slug="ndx_spx_ratio"):
    from paper import views
    sd = tmp_path / "state"; sd.mkdir(exist_ok=True)
    monkeypatch.setattr(views, "STATE_DIR", sd)
    monkeypatch.setattr(views, "EXTRA_STATE_DIRS", [])
    (sd / f"{slug}_{DAY.isoformat()}.json").write_text(json.dumps({
        "state": {"fills": fills, "ndx": list(ndx), "spx": list(spx)}, "pair": ["NDX", "SPX"], "provider": "tastytrade"}),
        encoding="utf-8")
    (sd / f"other_{DAY.isoformat()}.json").write_text(json.dumps({"state": {"fills": []}}), encoding="utf-8")
    return sd


FILL_OPEN = {"m": 727, "kind": "open", "direction": "short", "px": 108.26, "z": 4.07, "reason": "z +4.07",
             "verticals": [{"index": "NDX", "kind": "call", "kl": 31090.0, "kh": 31190.0, "qty": 1, "px": 50.1},
                           {"index": "SPX", "kind": "put", "kl": 7795.0, "kh": 7820.0, "qty": 4, "px": 14.54}]}
FILL_CLOSE = dict(FILL_OPEN, m=742, kind="close", px=111.37)


def test_the_pair_runners_trades_are_the_markers(tmp_path, monkeypatch):
    _state(tmp_path, monkeypatch, [{"m": 726, "kind": "rest"}, FILL_OPEN, FILL_CLOSE])
    st = PC.pair_states(DAY, "spx", "ndx")
    assert [s for s, _ in st] == ["ndx_spx_ratio"]
    m = PC.trade_markers(st, DAY)
    assert [(x["time"], x["kind"], x["px"]) for x in m] == [("2026-10-07T12:07", "open", 108.26), ("2026-10-07T12:22", "close", 111.37)]
    assert PC.pair_states(DAY, "QQQ", "SPY") == []


def test_option_symbols():
    assert PC.option_streamer_symbol("NDXP", DAY, "C", 31120.0) == ".NDXP261007C31120"
    assert PC.option_streamer_symbol("SPXW", DAY, "P", 7812.5) == ".SPXW261007P7812.5"


def test_combo_is_the_structure_as_one_price(tmp_path, monkeypatch):
    """The owner's 10/07 combo from injected candles: 1 x 31120/31220C + 4 x 7825/7800P = 30 + 4 x 20 = 110 at 14:44."""
    _state(tmp_path, monkeypatch, [])
    t = [dt.datetime(2026, 10, 7, 14, 44), dt.datetime(2026, 10, 7, 15, 1)]
    candles = {".NDXP261007C31120": [(t[0], 80.0), (t[1], 70.0)], ".NDXP261007C31220": [(t[0], 50.0), (t[1], 42.0)],
               ".SPXW261007P7825": [(t[0], 30.0), (t[1], 26.0)], ".SPXW261007P7800": [(t[0], 10.0), (t[1], 8.5)]}
    out = PC.combo("ndx_spx_ratio", DAY, [31120.0, 7825.0], closes_fn=lambda syms: {s: candles.get(s, []) for s in syms})
    assert out["combo"] == [110.0, 98.0]
    assert [v["values"] for v in out["verticals"]] == [[30.0, 28.0], [20.0, 17.5]]
    assert out["verticals"][1]["qty"] == 4 and out["why"] == "the strikes asked for"
    assert [l["sign"] for l in out["legs"]] == [1, -1, 1, -1]


def test_combo_defaults_to_the_days_last_trade_and_marks_it(tmp_path, monkeypatch):
    _state(tmp_path, monkeypatch, [FILL_OPEN, FILL_CLOSE])
    seen = {}

    def candles(syms):
        seen["syms"] = list(syms)
        return {s: [(dt.datetime(2026, 10, 7, 12, 7), 10.0)] for s in syms}
    out = PC.combo("ndx_spx_ratio", DAY, None, closes_fn=candles)
    assert out["strikes"] == [31090.0, 7820.0] and out["why"] == "the day's last trade"
    assert seen["syms"] == [".NDXP261007C31090", ".NDXP261007C31190", ".SPXW261007P7820", ".SPXW261007P7795"]
    assert all(m["on_this_combo"] for m in out["trades"])


def test_combo_says_which_leg_has_not_printed(tmp_path, monkeypatch):
    _state(tmp_path, monkeypatch, [])
    with pytest.raises(LookupError, match="SPXW261007P7800"):
        PC.combo("ndx_spx_ratio", DAY, [31120.0, 7825.0],
                 closes_fn=lambda syms: {s: ([] if s.endswith("P7800") else [(dt.datetime(2026, 10, 7, 10, 0), 1.0)]) for s in syms})


def test_the_routes(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from api.app import create_app
    _state(tmp_path, monkeypatch, [FILL_OPEN, FILL_CLOSE])
    frames = {"NDX": _frame(DAY, [31000 + i for i in range(30)]), "SPX": _frame(DAY, [7800 + i / 4 for i in range(30)])}
    from api.services import intraday as I
    monkeypatch.setattr(I, "intraday", lambda s, *a, **k: frames[s.upper()])
    monkeypatch.setattr(PC, "candle_source", lambda: type("C", (), {"closes": staticmethod(
        lambda syms, day: {s: [(dt.datetime(2026, 10, 7, 12, 7), 5.0)] for s in syms})})())
    with TestClient(create_app()) as c:
        r = c.get("/api/market/ratio", params={"a": "NDX", "b": "SPX"})
        assert r.status_code == 200, r.text
        j = r.json()
        assert len(j["ratio"]) == 30 and j["params"] == {"ema": 15, "sd": 60, "z": 3.0} and len(j["trades"]) == 2
        assert c.get("/api/market/ratio", params={"a": "NDX", "b": "NDX"}).status_code == 422
        r = c.get("/api/runner/ndx_spx_ratio/combo-chart", params={"day": DAY.isoformat()})
        assert r.status_code == 200, r.text
        assert r.json()["strikes"] == [31090.0, 7820.0]
        assert c.get("/api/runner/ndx_spx_ratio/combo-chart", params={"day": "x"}).status_code == 422
        assert c.get("/api/runner/nope_nope/combo-chart").status_code == 404
