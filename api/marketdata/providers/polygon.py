"""
api/marketdata/providers/polygon.py — Polygon REST snapshots.

On this account Polygon's options endpoints are the paid tier (chain snapshots with greeks, IV and
open interest) and its stock endpoints the free 5-a-minute tier, where the stock snapshot is not
authorized. So: option quotes and chains come from the options chain snapshot (one request per
underlying and expiry, however many contracts are watched); stock quotes are tried once and, on a
403, switched off for the life of the process. Requests go through ``PolygonClient`` (its own
per-tier limiter and 45 s cache) and the service's request gate.
"""
from __future__ import annotations

import datetime as _dt
import logging
from collections import defaultdict
from datetime import date
from typing import Optional

from api.marketdata import symbols as SYM
from api.marketdata.limits import ProviderLimits
from api.marketdata.providers.base import Provider
from data.request_gate import ProviderUnavailable

logger = logging.getLogger("alan_trader.api.marketdata.polygon")

#: a strike band wide enough to pick N strikes either side of spot from
CHAIN_BAND = 0.15


class PolygonProvider(Provider):
    name = "polygon"
    streaming = False
    poll_interval = 15.0
    capabilities = frozenset({"quotes", "options", "greeks", "chain"})
    #: where this provider ranks per chain field group (api/marketdata/options.py; lower first)
    chain_ranks = {"skeleton": 2, "quotes": 2, "greeks": 1, "sizes": 1}

    def __init__(self, limits: ProviderLimits, api_key: str = ""):
        super().__init__(limits)
        self.api_key = api_key
        self.stock_snapshot: Optional[bool] = None       # None = not probed yet
        #: whether option snapshots carry a two-sided quote on this plan (None = not seen yet). Polygon
        #: serves option *quotes* only once a snapshot has shown one (this account's plan has none):
        #: otherwise it still answers chains, greeks, IV and OI and leaves quotes to the next provider
        self.option_quotes: Optional[bool] = None
        if not api_key:
            limits.disable("no Polygon API key (POLYGON_API_KEY in .env)")

    def _client(self):
        from data.polygon_client import PolygonClient
        return PolygonClient(api_key=self.api_key)

    def supports(self, symbol: str) -> bool:
        if not self.available():
            return False
        if SYM.is_option(symbol):
            return self.option_quotes is True
        if SYM.is_index(symbol):
            return False
        return self.stock_snapshot is not False

    # ── quotes ────────────────────────────────────────────────────────────────
    def poll(self, symbols: list[str]) -> dict[str, dict]:
        out: dict[str, dict] = {}
        opts = [s for s in symbols if SYM.is_option(s)]
        stocks = [s for s in symbols if not SYM.is_option(s) and not SYM.is_index(s)]
        groups: dict[tuple[str, date], list] = defaultdict(list)
        for s in opts:
            o = SYM.parse_option(s)
            groups[(o.underlying, o.expiry)].append(o)
        for (und, exp), legs in groups.items():
            ks = [o.strike for o in legs]
            results = self._snapshot(und, exp, min(ks), max(ks))
            self._note_quotes(results)
            by = {r.get("details", {}).get("ticker", ""): r for r in results}
            for o in legs:
                r = by.get(o.polygon)
                if r is not None:
                    out[o.occ] = self._fields(r)
        if stocks and self.stock_snapshot is not False:
            out.update(self._stocks(stocks))
        return out

    def _stocks(self, stocks: list[str]) -> dict[str, dict]:
        import requests
        try:
            data = self._client()._get("/v2/snapshot/locale/us/markets/stocks/tickers",
                                       {"tickers": ",".join(stocks)}, use_cache=False, max_wait=5)
        except requests.HTTPError as exc:
            if getattr(exc.response, "status_code", None) in (401, 403):
                self.stock_snapshot = False
                self.limits.note("stock snapshots are not in this Polygon plan: options only")
                return {}
            raise
        self.stock_snapshot = True
        out = {}
        for t in data.get("tickers") or []:
            sym = t.get("ticker")
            lq, lt, day, prev = t.get("lastQuote") or {}, t.get("lastTrade") or {}, t.get("day") or {}, t.get("prevDay") or {}
            out[sym] = {"fields": {"bid": lq.get("p"), "ask": lq.get("P"), "last": lt.get("p") or day.get("c"),
                                   "prev_close": prev.get("c"), "volume": day.get("v"), "open": day.get("o"),
                                   "high": day.get("h"), "low": day.get("l")},
                        "time": (t.get("updated") or 0) / 1e9 or None}
        return out

    def _snapshot(self, underlying: str, expiry: date, k_lo: float, k_hi: float) -> list[dict]:
        c = self._client()
        params = {"expiration_date": expiry.isoformat(), "strike_price.gte": k_lo, "strike_price.lte": k_hi,
                  "limit": 250}
        url, results = f"/v3/snapshot/options/{SYM.to_polygon(underlying)}", []
        for _ in range(8):                                   # 2,000 contracts is far more than any band here
            data = c._get(url, params, max_wait=10)
            results.extend(data.get("results") or [])
            nxt = (data.get("next_url") or "").replace(c.BASE, "")
            if not nxt:
                break
            url, params = nxt, {}
        return results

    def _note_quotes(self, results: list[dict]) -> None:
        if not results or self.option_quotes is not None:
            return
        quoted = any((r.get("last_quote") or {}).get("bid") is not None for r in results)
        self.option_quotes = quoted
        if not quoted:
            self.limits.note("option snapshots carry no bid/ask on this plan: chains and greeks only; "
                             "option quotes come from the next provider")

    @staticmethod
    def _fields(r: dict) -> dict:
        lq, lt, day, g = r.get("last_quote") or {}, r.get("last_trade") or {}, r.get("day") or {}, r.get("greeks") or {}
        t = lq.get("last_updated") or lt.get("sip_timestamp") or day.get("last_updated")
        return {"fields": {"bid": lq.get("bid"), "ask": lq.get("ask"), "last": lt.get("price") or day.get("close"),
                           "prev_close": day.get("previous_close"), "volume": day.get("volume"),
                           "open": day.get("open"), "high": day.get("high"), "low": day.get("low"),
                           "iv": r.get("implied_volatility"), "delta": g.get("delta"), "gamma": g.get("gamma"),
                           "theta": g.get("theta"), "vega": g.get("vega"), "oi": r.get("open_interest")},
                "time": (t / 1e9) if t else None}

    # ── the IV surface: one snapshot of the OTM contracts in a band ───────────
    def surface_contracts(self, underlying: str, spot: float, max_dte: int, lo: float, hi: float) -> list[dict]:
        """[{"expiry", "strike", "type", "iv"}] for puts in [lo*S, S] and calls in [S, hi*S] expiring within
        ``max_dte`` days: two paginated snapshot queries (OTM only halves the pages)."""
        c = self._client()
        today = _dt.date.today()
        out: list[dict] = []
        for ctype, k_lo, k_hi in (("put", spot * lo, spot), ("call", spot, spot * hi)):
            params = {"contract_type": ctype, "strike_price.gte": round(k_lo, 2), "strike_price.lte": round(k_hi, 2),
                      "expiration_date.gte": today.isoformat(),
                      "expiration_date.lte": (today + _dt.timedelta(days=int(max_dte))).isoformat(), "limit": 250}
            url = f"/v3/snapshot/options/{SYM.to_polygon(underlying)}"
            for _ in range(60):                               # 15,000 contracts a side is far beyond any band
                data = c._get(url, params, max_wait=30)
                for r in data.get("results") or []:
                    d = r.get("details") or {}
                    if d.get("strike_price") is None or not d.get("expiration_date"):
                        continue
                    out.append({"expiry": _dt.date.fromisoformat(d["expiration_date"]), "strike": float(d["strike_price"]),
                                "type": str(d.get("contract_type") or ctype), "iv": r.get("implied_volatility")})
                nxt = (data.get("next_url") or "").replace(c.BASE, "")
                if not nxt:
                    break
                url, params = nxt, {}
        return out

    # ── chains ────────────────────────────────────────────────────────────────
    def expirations(self, underlying: str, spot: Optional[float] = None) -> list[date]:
        """Every listed expiry, from the contracts reference narrowed to a strike band around spot
        (so each expiry costs a handful of rows, not its whole strike ladder)."""
        c = self._client()
        params = {"underlying_ticker": underlying, "expired": "false", "limit": 1000,
                  "expiration_date.gte": _dt.date.today().isoformat()}
        if spot:
            params.update({"strike_price.gte": round(spot * 0.97, 2), "strike_price.lte": round(spot * 1.03, 2)})
        url, exps = "/v3/reference/options/contracts", set()
        for _ in range(10):
            data = c._get(url, params, max_wait=10)
            for r in data.get("results") or []:
                if r.get("expiration_date"):
                    exps.add(_dt.date.fromisoformat(r["expiration_date"]))
            nxt = (data.get("next_url") or "").replace(c.BASE, "")
            if not nxt:
                break
            url, params = nxt, {}
        return sorted(exps)

    def chain(self, underlying: str, expiry: date, spot: Optional[float], strikes: int) -> Optional[dict]:
        if not spot:
            raise ProviderUnavailable(self.name, f"no spot price for {underlying} to centre the chain on")
        results = self._snapshot(underlying, expiry, round(spot * (1 - CHAIN_BAND), 2), round(spot * (1 + CHAIN_BAND), 2))
        self._note_quotes(results)
        by_k: dict[float, dict] = defaultdict(dict)
        for r in results:
            d = r.get("details") or {}
            if d.get("strike_price") is None or d.get("contract_type") not in ("call", "put"):
                continue
            q = self._fields(r)["fields"]
            q["symbol"] = SYM.normalize(d.get("ticker", ""))
            by_k[float(d["strike_price"])][d["contract_type"]] = q
        if not by_k:
            return None
        return {"rows": pick_strikes(by_k, spot, strikes), "source": self.name}


def pick_strikes(by_k: dict[float, dict], spot: Optional[float], n: int) -> list[dict]:
    """``n`` strikes either side of spot (spot itself counts as below when it is a strike)."""
    ks = sorted(by_k)
    if spot is None:
        mid = len(ks) // 2
    else:
        mid = next((i for i, k in enumerate(ks) if k > spot), len(ks))
    lo, hi = max(0, mid - n), min(len(ks), mid + n)
    return [{"strike": k, "call": by_k[k].get("call"), "put": by_k[k].get("put")} for k in ks[lo:hi]]
