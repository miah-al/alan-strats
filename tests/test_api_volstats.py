"""vol-stats (api/services/volstats.py): the maths on synthetic chains, and the engine end to end with a
fake chain provider (no vendor is called)."""
from __future__ import annotations

import asyncio
import datetime as _dt
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:      # only the checkout: its parent holds the live alan_trader (conftest binds ours by path)
    sys.path.insert(0, str(REPO))

from api.bootstrap import bootstrap  # noqa: E402

bootstrap()

from api.marketdata import symbols as SYM  # noqa: E402
from api.marketdata.hub import MarketDataHub  # noqa: E402
from api.marketdata.limits import Gate, ProviderLimits, ProviderPolicy  # noqa: E402
from api.marketdata.providers.base import Provider  # noqa: E402
from api.services import volstats as V  # noqa: E402


def _chain(spot, iv_atm, skew, dte, grid=1.0, n=40):
    """Black-Scholes deltas on a smile: IV rises ``skew`` per 1% below spot, flat above; quotes 2% either side."""
    from paper.views import _bs_full
    T = dte / 365
    rows = []
    for i in range(-n, n + 1):
        k = spot + i * grid
        m = (k - spot) / spot * 100
        iv = iv_atm + (-m * skew if m < 0 else 0.0)
        row = {"strike": k}
        for side in ("call", "put"):
            p, d, g, v, th, _ = _bs_full(spot, k, T, 0.045, iv, side)
            row[side] = {"iv": iv, "delta": d, "bid": p * 0.98, "ask": p * 1.02, "oi": 10}
        rows.append(row)
    return rows


def test_atm_iv_skew_and_straddle_on_a_synthetic_chain():
    rows = _chain(100.0, 0.20, 0.005, 30)
    assert V.atm_iv(rows, 100.0) == pytest.approx(0.20)
    put25, call25 = V.delta_iv(rows, "put", -0.25), V.delta_iv(rows, "call", 0.25)
    assert put25 > 0.20 >= call25 - 1e-9                      # puts carry the skew
    s, spread = V.straddle(rows, 100.0)
    assert s == pytest.approx(0.8 * 100 * 0.20 * math.sqrt(30 / 365), rel=0.05)
    assert spread == pytest.approx(4.0, rel=0.02)


def test_interpolations_and_rank():
    assert V.interp_variance([(20, 0.10), (40, 0.20)], 30) == pytest.approx(math.sqrt((0.01 * 20 + 0.04 * 40) / 2 / 30))
    assert V.interp_variance([(20, 0.10)], 25) == 0.10 and V.interp_variance([(20, 0.10)], 90) is None
    h = pd.Series(np.linspace(10, 30, 100))
    rank, pct, n, why = V.rank_and_percentile(h, 25.0)
    assert rank == pytest.approx(75.0) and pct == pytest.approx(75.0) and n == 100 and why is None
    assert V.rank_and_percentile(h.iloc[:30], 25.0)[0] is None and "30 days" in V.rank_and_percentile(h.iloc[:30], 25.0)[3]
    today = _dt.date.today()
    ex = [(today + _dt.timedelta(days=d), d) for d in (1, 5, 14, 28, 35, 63, 91, 182)]
    p = V.pick_expiries(ex)
    assert p["lo30"][1] == 28 and p["hi30"][1] == 35 and p["e90"][1] == 91
    c = pd.Series(100 * np.exp(np.cumsum(np.r_[0, np.tile([0.01, -0.01], 40)])))
    assert V.realised_vol(c, 20) == pytest.approx(0.01 * math.sqrt(252) * math.sqrt(20 / 19), rel=0.01)


class FakeChains(Provider):
    name = "fakechains"
    streaming = False
    capabilities = frozenset({"quotes", "chain"})
    chain_ranks = {"skeleton": 0, "quotes": 0, "greeks": 0, "sizes": 0}

    def __init__(self):
        super().__init__(ProviderLimits(ProviderPolicy(self.name, per_min=6000, per_day=100000, burst=1000)))
        self.chain_calls = 0

    def supports(self, s):
        return not SYM.is_option(s)

    def poll(self, syms):
        return {s: {"fields": {"last": 100.0}, "time": None} for s in syms}

    def expirations(self, u, spot=None):
        return [_dt.date.today() + _dt.timedelta(days=d) for d in (3, 24, 38, 88, 150)]

    def chain(self, u, expiry, spot, n):
        self.chain_calls += 1
        dte = (expiry - _dt.date.today()).days
        return {"rows": _chain(100.0, 0.18 + dte / 1000.0, 0.005, dte), "source": self.name}


def test_vol_stats_end_to_end(monkeypatch):
    monkeypatch.setattr(V, "record_iv", lambda *a: None)                       # never writes under test
    monkeypatch.setattr(V, "iv_history", lambda s: pd.Series(np.linspace(15, 25, 120)))
    monkeypatch.setattr(V, "closes", lambda s: (pd.Series(100 * np.exp(np.cumsum(np.r_[0, np.tile([0.01, -0.01], 150)])),
                                                          index=pd.bdate_range("2025-06-02", periods=301)), "db"))
    import api.services.earnings as E
    monkeypatch.setattr(E, "next_earnings", lambda s: None)

    async def go():
        fp = FakeChains()
        hub = MarketDataHub(Gate([]), [fp])
        hub.start()
        vs = V.VolStats(hub)
        out = await asyncio.to_thread(vs.get, ["zzv", "ZZV"])
        assert out["pending"] == 0 and [c["field"] for c in out["columns"]][:3] == ["symbol", "status", "spot"]
        r = out["rows"][0]
        assert r["symbol"] == "ZZV" and r["status"] == "ok", r["notes"]
        assert r["iv30"] == pytest.approx(21.0, abs=0.3)                       # 18 + 30/1000 in vol points
        assert r["term_slope"] == pytest.approx(6.0, abs=0.5) and r["iv90"] > r["iv30"]
        assert r["skew_25d"] > 0 and r["em_30d_pct"] > 0 and r["atm_spread_pct"] == pytest.approx(4.0, rel=0.05)
        assert r["iv_rank"] is not None and r["iv_history_days"] == 120 and r["hv20"] > 0 and r["beta_spy"] == 1.0
        assert r["oi_total"] > 0 and r["source"] == "fakechains"
        n = fp.chain_calls
        again = await asyncio.to_thread(vs.get, ["ZZV"])
        assert again["rows"][0]["iv30"] == r["iv30"] and fp.chain_calls == n        # cached
        with pytest.raises(ValueError):
            vs.get([f"S{i}" for i in range(41)])
        with pytest.raises(ValueError):
            vs.get(["SPY261030C00770000"])
        vs.shutdown()
        await hub.stop()
    asyncio.run(go())


def _db_ok() -> bool:
    try:
        from api.services.db import ping
        return ping()[0]
    except Exception:
        return False


@pytest.mark.skipif(not _db_ok(), reason="AlanStrats database unreachable")
def test_iv_history_from_the_stored_option_snapshots():
    """The snapshots store the right as C / P: both sides count (read only)."""
    from sqlalchemy import text
    from api.services.db import engine
    with engine().connect() as c:
        n = c.execute(text("SELECT COUNT(DISTINCT o.SnapshotDate) FROM mkt.OptionSnapshot o JOIN mkt.Ticker t ON "
                           "t.TickerId = o.TickerId WHERE t.Symbol = 'SPY' AND o.SnapshotDate >= :d"),
                      {"d": _dt.date.today() - _dt.timedelta(days=365)}).scalar()
    if not n:
        pytest.skip("no SPY option snapshots in the last year")
    s = V._snapshot_history("SPY")
    assert len(s) >= min(n, 60) * 0.8 and 3 < s.median() < 80                  # vol points
