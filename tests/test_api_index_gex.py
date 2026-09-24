"""Index GEX and NDX / NDXP chains through the market-data hub, with a stubbed broker stream: the spot comes
from the hub's index quote, the chain (OI + greeks) from the merged chain path, and NDXP names the root.
No vendor is called."""
from __future__ import annotations

import datetime as _dt
import math
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
for _p in (str(REPO), str(REPO.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from api.bootstrap import bootstrap  # noqa: E402

bootstrap()

from api.marketdata import symbols as SYM  # noqa: E402
from api.marketdata.limits import ProviderLimits, ProviderPolicy  # noqa: E402
from api.marketdata.providers.base import Provider  # noqa: E402

SPOT = 20000.0


def _exps():
    today = _dt.date.today()
    days = [0, 1, 2, 3, 6]
    fri = today + _dt.timedelta(days=(4 - today.weekday()) % 7 + 7)
    return [today + _dt.timedelta(days=d) for d in days] + [fri, fri + _dt.timedelta(days=7)]


class FakeBroker(Provider):
    """A tastytrade-like stream: NDX index level, NDX (AM) and NDXP (PM) roots, OI and greeks per contract."""
    name = "fakebroker"
    streaming = True
    capabilities = frozenset({"quotes", "options", "greeks", "chain"})
    chain_ranks = {"skeleton": 0, "quotes": 0, "greeks": 0, "sizes": 0}

    def __init__(self):
        super().__init__(ProviderLimits(ProviderPolicy(self.name, per_min=6000, per_day=100000, burst=1000)))
        self.connected = True
        self.subs: set[str] = set()

    def supports(self, s):
        return s == "NDX" or s.startswith("NDX")

    def expirations(self, u, root=None):
        return _exps() if u == "NDX" else []

    def chain_contracts(self, u, expiry, root=None):
        if u != "NDX" or (root not in (None, "NDXP")):
            return []
        out = []
        for i in range(-20, 21):
            k = SPOT + 50 * i
            out.append((k, SYM.make_option("NDXP", expiry, "C", k).occ, SYM.make_option("NDXP", expiry, "P", k).occ))
        return out

    def subscribe(self, syms):
        for s in syms:
            self.subs.add(s)
            if s == "NDX":
                self.emit(s, self.name, time.time(), last=SPOT, bid=SPOT - 20, ask=SPOT + 20)
                continue
            o = SYM.parse_option(s)
            if o is None:
                continue
            dist = (o.strike - SPOT) / 200.0
            gamma = math.exp(-dist * dist) / 1e3
            oi = 1000.0 if o.right == "C" and o.strike >= SPOT else (1500.0 if o.right == "P" and o.strike <= SPOT else 200.0)
            self.emit(s, self.name, time.time(), bid=10.0, ask=10.5, iv=0.2, delta=0.5 if o.right == "C" else -0.5,
                      gamma=gamma, theta=-1.0, vega=2.0, oi=oi)

    def unsubscribe(self, syms):
        self.subs.difference_update(syms)


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from api.app import create_app
    from api.bootstrap import db_guard_installed, uninstall_db_read_only_guard
    had = db_guard_installed()
    app = create_app()
    try:
        with TestClient(app, raise_server_exceptions=False) as c:
            fb = FakeBroker()
            c.app.state.market.add_provider(fb, first=True)
            yield c
    finally:
        if not had:
            uninstall_db_read_only_guard()


def test_symbols_roots():
    assert SYM.underlying_and_root("ndxp") == ("NDX", "NDXP")
    assert SYM.underlying_and_root("SPXW") == ("SPX", "SPXW")
    assert SYM.underlying_and_root("^NDX") == ("NDX", None) and SYM.underlying_and_root("SPY") == ("SPY", None)


def test_index_gex_from_the_hub(client):
    r = client.get("/api/market/gex/NDX?source=hub")
    assert r.status_code == 200, r.text
    g = r.json()
    assert g["spot"] == SPOT and g["source"] == "hub:fakebroker" and g["underlying"] == "NDX"
    assert g["contracts"] > 0 and g["net_gex"] != 0
    assert set(g) >= {"flip", "call_wall", "put_wall", "regime", "table", "by_expiry", "max_pain"}
    exps = {row["expiry"] for row in g["by_expiry"]["rows"]}
    assert len(exps) >= 5                                         # the first week's dailies and the Fridays
    auto = client.get("/api/market/gex/NDXP").json()               # auto: an index goes to the hub's chain
    assert auto["root"] == "NDXP" and auto["source"].startswith("hub:") and auto["spot"] == SPOT


def test_ndx_expirations_and_chain(client):
    e = client.get("/api/options/NDXP/expirations").json()
    assert e["underlying"] == "NDX" and e["root"] == "NDXP" and e["spot"] == SPOT and len(e["expirations"]) == 7
    exp = e["expirations"][2]["expiry"]
    ch = client.get(f"/api/options/NDX/chain?expiry={exp}&strikes=3").json()
    rows = ch["table"]["rows"]
    assert [r["strike"] for r in rows] == [SPOT - 100, SPOT - 50, SPOT, SPOT + 50, SPOT + 100, SPOT + 150]
    assert rows[0]["call_symbol"].startswith("NDXP") and rows[0]["call_mid"] == pytest.approx(10.25)
    assert rows[0]["put_oi"] == 1500.0 and ch["quote_source"] == "fakebroker"


def test_band_sampling_keeps_near_strikes_and_samples_the_wings():
    from api.marketdata.options import _band
    ks = [float(k) for k in range(15000, 25001, 10)]
    got = _band(ks, 20000.0, (0.015, 0.08, 90))
    near = [k for k in ks if abs(k - 20000) <= 300]
    assert set(near) <= got and len(got) <= 90 and min(got) >= 18400 and max(got) <= 21600
