"""
api/services/crypto_flush.py — the crypto liquidation-flush trigger (R0), polled 24/7 from OKX's public API.

Rule R0 (crypto_liq study, pre-registered; out of sample +1.74% at +24 h [+0.82, +2.74], 76% wins, n = 38,
about 10–25 signals a year), per coin (BTC, ETH), every minute:
    price ≤ 95% of its max over the past 240 minutes
    perp open interest ≤ 95% of its max over the past 240 minutes, the OI print ≤ 10 minutes old
    not while OI is still rising into the drop (OI now above OI 30 minutes ago)
    one signal per coin per 24 hours
Entry at the next minute's price + 0.1% slippage, exit at +24 h, no stop.

Data: OKX public REST (no key; Binance fapi / Bybit are geo-blocked from here) — the perpetual's ticker
(``/api/v5/market/ticker``) and open interest (``/api/v5/public/open-interest``, ``oiCcy`` = contracts in coin)
once a minute per coin, the last 240 one-minute candles on start to seed the price window (the OI window
warms up from the live polls: OKX's OI history is in other units). Four small requests a minute in total.

The paper trade is LOG-ONLY: a synthetic micro future (MBT = 0.1 BTC, MET = 0.1 ETH) whose entry and exit
prices are recorded here (app.CryptoFlushSignal); this checkout has no synthetic-future ledger. It is taken
only while ``crypto_flush`` is armed (POST /api/runner/crypto_flush/arm) — never by default; unarmed, the
trigger is still logged and its +1 h / +4 h / +24 h returns back-filled, so the claim is tested forward.

``ALAN_TRADER_CRYPTO_FLUSH``: ``1`` (default) | ``0``. Off as well when the service has no market-data
providers at all (``ALAN_TRADER_PROVIDERS=none``, the test suite), so no test ever polls an exchange.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import threading
import time
from collections import deque
from typing import Callable, Optional

import pandas as pd

logger = logging.getLogger("alan_trader.api.crypto_flush")

NY = "America/New_York"
OKX = "https://www.okx.com"
COINS = {"BTC": {"inst": "BTC-USDT-SWAP", "micro": "MBT", "size": 0.1},
         "ETH": {"inst": "ETH-USDT-SWAP", "micro": "MET", "size": 0.1}}
PARAMS = {"lookback_min": 240, "price_drop": 0.05, "oi_drop": 0.05, "oi_max_age_min": 10.0, "min_oi_samples": 10,
          "oi_rising_min": 30, "oi_rising_tol": 0.0, "cooldown_min": 1440, "slippage": 0.001, "hold_min": 1440,
          "poll_s": 60.0}
KEEP_MIN = 300
SIGNAL_COLS = ("id", "ts", "coin", "price", "max240", "drop_pct", "oi", "oi_max240", "oi_drop_pct", "oi_age_min", "trade",
               "micro", "size", "entry_ts", "entry_price", "exit_ts", "exit_price", "pnl_usd", "ret_pct", "r1h", "r4h",
               "r24h", "created")


def enabled() -> bool:
    if os.environ.get("ALAN_TRADER_CRYPTO_FLUSH", "1").strip().lower() in ("0", "off", "false", "no"):
        return False
    from api.marketdata.service import provider_names
    return bool(provider_names())


def _utcnow() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)


def _et_iso(v) -> Optional[str]:
    if v is None:
        return None
    t = pd.Timestamp(v)
    t = t.tz_localize("UTC") if t.tzinfo is None else t
    return t.tz_convert(NY).isoformat(timespec="seconds")


# ── OKX ───────────────────────────────────────────────────────────────────────

class OkxClient:
    """The three public calls the poller makes. Every request passes the service's request gate (installed
    on ``requests`` by the app)."""

    def __init__(self, base: str = OKX, timeout: float = 10.0):
        self.base = base
        self.timeout = timeout
        self._s = None

    def _get(self, path: str, **params) -> list:
        import requests
        if self._s is None:
            self._s = requests.Session()
            self._s.headers["User-Agent"] = "alan_trader-service/1 (paper research; contact: local)"
        r = self._s.get(self.base + path, params=params, timeout=self.timeout)
        r.raise_for_status()
        j = r.json()
        if str(j.get("code")) not in ("0", "None"):
            raise RuntimeError(f"OKX {path}: code {j.get('code')} {j.get('msg')}")
        return j.get("data") or []

    def ticker(self, inst: str) -> tuple[float, int]:
        d = self._get("/api/v5/market/ticker", instId=inst)
        if not d:
            raise RuntimeError(f"OKX ticker: no data for {inst}")
        return float(d[0]["last"]), int(d[0]["ts"])

    def open_interest(self, inst: str) -> tuple[float, int]:
        d = self._get("/api/v5/public/open-interest", instType="SWAP", instId=inst)
        if not d:
            raise RuntimeError(f"OKX open interest: no data for {inst}")
        return float(d[0].get("oiCcy") or d[0]["oi"]), int(d[0]["ts"])

    def candles(self, inst: str, limit: int = 240) -> list[tuple[int, float]]:
        """(ts ms, close) ascending for the last ``limit`` one-minute candles."""
        d = self._get("/api/v5/market/candles", instId=inst, bar="1m", limit=str(int(limit)))
        rows = [(int(r[0]), float(r[4])) for r in d]
        return sorted(rows)


# ── the rule (pure) ───────────────────────────────────────────────────────────

def evaluate(prices: list[tuple[int, float]], ois: list[tuple[int, float]], now_ms: int,
             last_signal_ms: Optional[int] = None, params: Optional[dict] = None) -> dict:
    """R0 on the windows: ``prices`` / ``ois`` are (ts ms, value) ascending. Returns the numbers the desk shows
    and ``triggered``."""
    p = dict(PARAMS, **(params or {}))
    lb = int(p["lookback_min"]) * 60_000
    win_p = [v for t, v in prices if t >= now_ms - lb]
    win_o = [(t, v) for t, v in ois if t >= now_ms - lb]
    out = {"price": win_p[-1] if win_p else None, "max240": max(win_p) if win_p else None, "drop_pct": None,
           "oi": None, "oi_max240": None, "oi_drop_pct": None, "oi_age_min": None, "oi_rising": None,
           "price_samples": len(win_p), "oi_samples": len(win_o), "cooldown_min_left": None, "triggered": False,
           "reasons": []}
    if len(win_p) >= 2 and out["max240"]:
        out["drop_pct"] = round((out["price"] / out["max240"] - 1) * 100, 3)
    if win_o:
        t_oi, oi = win_o[-1]
        out["oi"] = oi
        out["oi_max240"] = max(v for _, v in win_o)
        out["oi_drop_pct"] = round((oi / out["oi_max240"] - 1) * 100, 3) if out["oi_max240"] else None
        out["oi_age_min"] = round((now_ms - t_oi) / 60_000, 1)
        earlier = [v for t, v in win_o if t <= now_ms - int(p["oi_rising_min"]) * 60_000]
        if earlier:
            out["oi_rising"] = oi > earlier[-1] * (1 + float(p["oi_rising_tol"]))
    if last_signal_ms is not None:
        left = int(p["cooldown_min"]) - (now_ms - last_signal_ms) / 60_000
        out["cooldown_min_left"] = round(left, 1) if left > 0 else None
    r = out["reasons"]
    if out["drop_pct"] is None or len(win_p) < int(p["min_oi_samples"]):
        r.append("price window warming up")
    elif out["drop_pct"] > -float(p["price_drop"]) * 100:
        r.append(f"price {out['drop_pct']:+.2f}% vs its {p['lookback_min']}-min max (needs ≤ −{p['price_drop'] * 100:g}%)")
    if len(win_o) < int(p["min_oi_samples"]):
        r.append(f"OI window warming up ({len(win_o)}/{p['min_oi_samples']} samples)")
    elif out["oi_drop_pct"] is not None and out["oi_drop_pct"] > -float(p["oi_drop"]) * 100:
        r.append(f"OI {out['oi_drop_pct']:+.2f}% vs its max (needs ≤ −{p['oi_drop'] * 100:g}%)")
    if out["oi_age_min"] is not None and out["oi_age_min"] > float(p["oi_max_age_min"]):
        r.append(f"OI print {out['oi_age_min']:.0f} min old (max {p['oi_max_age_min']:g})")
    if out["oi_rising"]:
        r.append("OI still rising into the drop")
    if out["cooldown_min_left"]:
        r.append(f"one signal per {p['cooldown_min'] / 60:g} h: {out['cooldown_min_left']:.0f} min left")
    out["triggered"] = not r
    return out


# ── stores ────────────────────────────────────────────────────────────────────

class MemoryFlushStore:
    def __init__(self):
        self.rows: list[dict] = []
        self._lock = threading.Lock()
        self._next = 1

    def add(self, row: dict) -> dict:
        with self._lock:
            r = {k: None for k in SIGNAL_COLS}
            r.update(row, id=self._next, created=_utcnow())
            self._next += 1
            self.rows.append(r)
            return dict(r)

    def update(self, signal_id: int, **cols) -> Optional[dict]:
        with self._lock:
            r = next((r for r in self.rows if r["id"] == signal_id), None)
            if r is None:
                return None
            r.update(cols)
            return dict(r)

    def since(self, since: _dt.datetime) -> list[dict]:
        with self._lock:
            return sorted((dict(r) for r in self.rows if r["ts"] >= since), key=lambda r: (r["ts"], r["id"]), reverse=True)

    def last(self, coin: str) -> Optional[dict]:
        with self._lock:
            rows = [r for r in self.rows if r["coin"] == coin]
            return dict(rows[-1]) if rows else None

    def pending(self) -> list[dict]:
        """Rows with an outcome or a trade leg still to fill."""
        with self._lock:
            return [dict(r) for r in self.rows if r.get("r24h") is None or (r.get("trade") and r.get("exit_price") is None)]


class DbFlushStore:
    _DB = ("Id", "Ts", "Coin", "Price", "Max240", "DropPct", "Oi", "OiMax240", "OiDropPct", "OiAgeMin", "Trade", "Micro",
           "Size", "EntryTs", "EntryPrice", "ExitTs", "ExitPrice", "PnlUsd", "RetPct", "R1h", "R4h", "R24h", "CreatedAt")
    _MAP = dict(zip(SIGNAL_COLS, _DB))

    def _eng(self):
        from api.services.db import require_db
        return require_db()

    def _row(self, r) -> dict:
        d = dict(zip(SIGNAL_COLS, r))
        if d["trade"] is not None:
            d["trade"] = bool(d["trade"])
        return d

    def add(self, row: dict) -> dict:
        from sqlalchemy import text
        from api.services import appdb
        appdb.ensure("CryptoFlushSignal")
        cols = [k for k in SIGNAL_COLS if k in row and k not in ("id", "created")]
        with self._eng().begin() as c:
            r = c.execute(text(f"INSERT INTO app.CryptoFlushSignal ({', '.join(self._MAP[k] for k in cols)}) OUTPUT INSERTED.Id "
                               f"VALUES ({', '.join(':' + k for k in cols)})"), {k: row[k] for k in cols}).fetchone()
        return self.get(int(r[0]))

    def get(self, signal_id: int) -> Optional[dict]:
        from sqlalchemy import text
        with self._eng().connect() as c:
            r = c.execute(text(f"SELECT {', '.join(self._DB)} FROM app.CryptoFlushSignal WHERE Id = :id"), {"id": int(signal_id)}).fetchone()
        return self._row(r) if r else None

    def update(self, signal_id: int, **cols) -> Optional[dict]:
        from sqlalchemy import text
        sets = ", ".join(f"{self._MAP[k]} = :{k}" for k in cols if k in self._MAP)
        if sets:
            with self._eng().begin() as c:
                c.execute(text(f"UPDATE app.CryptoFlushSignal SET {sets} WHERE Id = :id"), {**cols, "id": int(signal_id)})
        return self.get(signal_id)

    def since(self, since: _dt.datetime) -> list[dict]:
        from sqlalchemy import text
        from api.services import appdb
        if not appdb.exists("CryptoFlushSignal"):
            return []
        with self._eng().connect() as c:
            rows = c.execute(text(f"SELECT {', '.join(self._DB)} FROM app.CryptoFlushSignal WHERE Ts >= :s ORDER BY Ts DESC, Id DESC"),
                             {"s": since}).fetchall()
        return [self._row(r) for r in rows]

    def last(self, coin: str) -> Optional[dict]:
        from sqlalchemy import text
        from api.services import appdb
        if not appdb.exists("CryptoFlushSignal"):
            return None
        with self._eng().connect() as c:
            r = c.execute(text(f"SELECT TOP 1 {', '.join(self._DB)} FROM app.CryptoFlushSignal WHERE Coin = :c ORDER BY Ts DESC"),
                          {"c": coin}).fetchone()
        return self._row(r) if r else None

    def pending(self) -> list[dict]:
        from sqlalchemy import text
        from api.services import appdb
        if not appdb.exists("CryptoFlushSignal"):
            return []
        with self._eng().connect() as c:
            rows = c.execute(text(f"SELECT {', '.join(self._DB)} FROM app.CryptoFlushSignal WHERE R24h IS NULL OR "
                                  f"(Trade = 1 AND ExitPrice IS NULL)")).fetchall()
        return [self._row(r) for r in rows]


def make_store():
    from api.services.arms import enabled_store
    m = enabled_store()
    return MemoryFlushStore() if m == "memory" else (None if m == "off" else DbFlushStore())


def signal_view(r: dict) -> dict:
    d = {k: r.get(k) for k in SIGNAL_COLS}
    for k in ("ts", "entry_ts", "exit_ts", "created"):
        d[k] = _et_iso(d[k])
    d["open"] = bool(d.get("trade")) and d.get("exit_price") is None
    return d


# ── the poller ────────────────────────────────────────────────────────────────

class CryptoFlushPoller:
    def __init__(self, store=None, client: Optional[OkxClient] = None, publish: Optional[Callable[[dict], None]] = None,
                 clock: Optional[Callable[[], pd.Timestamp]] = None, params: Optional[dict] = None,
                 armed: Optional[Callable[[str], bool]] = None, on: Optional[bool] = None):
        self.store = store if store is not None else make_store()
        self.client = client or OkxClient()
        self.publish = publish
        self.clock = clock or (lambda: pd.Timestamp.now(tz=NY))
        self.params = dict(PARAMS, **(params or {}))
        self.armed = armed or (lambda s: False)
        self.on = enabled() if on is None else bool(on)
        self.prices: dict[str, deque] = {c: deque() for c in COINS}
        self.ois: dict[str, deque] = {c: deque() for c in COINS}
        self.seeded: set[str] = set()
        self.last_eval: dict[str, dict] = {}
        self.errors: dict[str, str] = {}
        self.ticks = 0
        self.last_tick: Optional[pd.Timestamp] = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()

    # ── lifecycle ─────────────────────────────────────────────────────────────
    def start(self) -> None:
        if not self.on or self.store is None:
            logger.info("crypto_flush poller off (%s)", "ALAN_TRADER_CRYPTO_FLUSH / no providers" if not self.on else "no store")
            return
        self._thread = threading.Thread(target=self._run, name="crypto-flush", daemon=True)
        self._thread.start()
        logger.info("crypto_flush poller on: %s every %.0fs from OKX", ", ".join(COINS), self.params["poll_s"])

    def stop(self) -> None:
        self._stop.set()

    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive() and not self._stop.is_set()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                logger.exception("crypto_flush tick failed")
            if self._stop.wait(float(self.params["poll_s"])):
                break

    # ── one poll ─────────────────────────────────────────────────────────────
    def _now_ms(self, now: pd.Timestamp) -> int:
        return int(now.tz_convert("UTC").timestamp() * 1000) if now.tzinfo else int(now.timestamp() * 1000)

    def _trim(self, dq: deque, now_ms: int) -> None:
        while dq and dq[0][0] < now_ms - KEEP_MIN * 60_000:
            dq.popleft()

    def tick(self, now: Optional[pd.Timestamp] = None) -> list[dict]:
        """Poll each coin once, evaluate R0, log a trigger; fill the paper legs and outcomes that are due.
        Returns the signal rows created."""
        now = now or self.clock()
        now_ms = self._now_ms(now)
        created = []
        fetched: dict[str, dict] = {}
        for coin, spec in COINS.items():                        # the HTTP calls: outside the lock (status() never waits)
            try:
                seed = None
                if coin not in self.seeded:
                    seed = self.client.candles(spec["inst"], int(self.params["lookback_min"]))
                px, t_px = self.client.ticker(spec["inst"])
                oi, t_oi = self.client.open_interest(spec["inst"])
                fetched[coin] = {"seed": seed, "px": (max(t_px, now_ms - 1), px), "oi": (t_oi, oi)}
            except Exception as exc:  # noqa: BLE001 — the next minute tries again
                fetched[coin] = {"error": f"{type(exc).__name__}: {exc}"[:200]}
                logger.info("crypto_flush %s poll failed: %s", coin, exc)
        with self._lock:
            self.ticks += 1
            self.last_tick = now
            for coin, spec in COINS.items():
                got = fetched.get(coin) or {}
                if got.get("error"):
                    self.errors[coin] = got["error"]
                    continue
                if got.get("seed") is not None:
                    self.prices[coin].extend(got["seed"])
                    self.seeded.add(coin)
                self.prices[coin].append(got["px"])
                self.ois[coin].append(got["oi"])
                self.errors.pop(coin, None)
                self._trim(self.prices[coin], now_ms)
                self._trim(self.ois[coin], now_ms)
                last = self.store.last(coin) if self.store is not None else None
                last_ms = int(pd.Timestamp(last["ts"]).tz_localize("UTC").timestamp() * 1000) if last else None
                ev = evaluate(list(self.prices[coin]), list(self.ois[coin]), now_ms, last_ms, self.params)
                self.last_eval[coin] = dict(ev, at=now.isoformat(timespec="seconds"))
                if ev["triggered"] and self.store is not None:
                    row = self._signal(coin, spec, ev, now)
                    created.append(row)
            self._fill(now, now_ms)
        return created

    def _signal(self, coin: str, spec: dict, ev: dict, now: pd.Timestamp) -> dict:
        take = bool(self.armed("crypto_flush"))
        row = {"ts": now.tz_convert("UTC").to_pydatetime().replace(tzinfo=None), "coin": coin, "price": ev["price"],
               "max240": ev["max240"], "drop_pct": ev["drop_pct"], "oi": ev["oi"], "oi_max240": ev["oi_max240"],
               "oi_drop_pct": ev["oi_drop_pct"], "oi_age_min": ev["oi_age_min"], "trade": take,
               "micro": spec["micro"] if take else None, "size": spec["size"] if take else None}
        r = self.store.add(row)
        logger.info("crypto_flush %s: price %.2f (%+.2f%% vs 4h max), OI %+.2f%%%s", coin, ev["price"], ev["drop_pct"],
                    ev["oi_drop_pct"], " — paper micro future logged" if take else " — logged (not armed)")
        if self.publish is not None:
            try:
                from api.serialize import to_jsonable
                self.publish(to_jsonable({"type": "crypto_flush", "event": "signal", **signal_view(r)}))
            except Exception:
                logger.debug("crypto_flush publish failed", exc_info=True)
        return r

    def _price_now(self, coin: str) -> Optional[float]:
        dq = self.prices.get(coin)
        return float(dq[-1][1]) if dq else None

    def _fill(self, now: pd.Timestamp, now_ms: int) -> None:
        """Entries a minute after the signal, exits at +24 h, and the +1 h / +4 h / +24 h marks."""
        if self.store is None:
            return
        for r in self.store.pending():
            coin = r["coin"]
            px = self._price_now(coin)
            if px is None:
                continue
            t0 = int(pd.Timestamp(r["ts"]).tz_localize("UTC").timestamp() * 1000)
            age = (now_ms - t0) / 60_000
            cols = {}
            if r.get("trade") and r.get("entry_price") is None and age >= 1:
                cols.update(entry_ts=now.tz_convert("UTC").to_pydatetime().replace(tzinfo=None),
                            entry_price=round(px * (1 + float(self.params["slippage"])), 2))
            elif r.get("trade") and r.get("entry_price") is not None and r.get("exit_price") is None:
                t_in = int(pd.Timestamp(r["entry_ts"]).tz_localize("UTC").timestamp() * 1000)
                if now_ms - t_in >= int(self.params["hold_min"]) * 60_000:
                    exit_px = round(px * (1 - float(self.params["slippage"])), 2)
                    cols.update(exit_ts=now.tz_convert("UTC").to_pydatetime().replace(tzinfo=None), exit_price=exit_px,
                                pnl_usd=round((exit_px - float(r["entry_price"])) * float(r["size"] or 0), 2),
                                ret_pct=round((exit_px / float(r["entry_price"]) - 1) * 100, 3))
            for k, mins in (("r1h", 60), ("r4h", 240), ("r24h", 1440)):
                if r.get(k) is None and age >= mins and r.get("price"):
                    cols[k] = round((px / float(r["price"]) - 1) * 100, 3)
            if cols:
                self.store.update(r["id"], **cols)

    # ── the arm's daily run (housekeeping; the poller itself trades) ─────────
    def run(self, variant: str = "", now: Optional[pd.Timestamp] = None) -> dict:
        now = now or self.clock()
        rows = self.signals(2)
        open_ = [r for r in rows if r["open"]]
        return {"date": now.date(), "status": "ran", "summary": f"crypto_flush armed: {len(rows)} signal(s) in 2 days, "
                                                                 f"{len(open_)} paper trade(s) open; the poller takes the trades"}

    # ── reading ───────────────────────────────────────────────────────────────
    def signals(self, days: int = 30) -> list[dict]:
        if self.store is None:
            return []
        since = (self.clock() - pd.Timedelta(days=int(days))).tz_convert("UTC").to_pydatetime().replace(tzinfo=None)
        return [signal_view(r) for r in self.store.since(since)]

    def status(self, variant: str = "") -> dict:
        with self._lock:
            coins = {}
            for c in COINS:
                ev = dict(self.last_eval.get(c) or {})
                ev.pop("triggered", None)
                coins[c] = {**ev, "error": self.errors.get(c), "inst": COINS[c]["inst"], "micro": COINS[c]["micro"]}
            return {"enabled": self.on, "running": self.running(), "ticks": self.ticks,
                    "last_tick": self.last_tick.isoformat(timespec="seconds") if self.last_tick is not None else None,
                    "source": "okx public REST", "params": self.params, "coins": coins,
                    "armed": bool(self.armed("crypto_flush"))}

    def log(self, days: int = 30) -> dict:
        return {"playbook": "crypto_flush", "days": int(days), "signals": self.signals(days)}

    def playbook(self, now: Optional[pd.Timestamp] = None) -> dict:
        now = now or self.clock()
        st = self.status()
        recent = self.signals(2)
        fresh = [r for r in recent if (now - pd.Timestamp(r["ts"])).total_seconds() <= 3600]
        open_ = [r for r in recent if r["open"]]
        checklist, reasons = [], []
        for c, ev in st["coins"].items():
            checklist.append({"label": f"{c}: price ≤ 95% of its 4-h max", "ok": (ev.get("drop_pct") is not None and ev["drop_pct"] <= -5.0) if ev.get("drop_pct") is not None else None,
                              "value": f"{ev['drop_pct']:+.2f}% ({ev.get('price')})" if ev.get("drop_pct") is not None else (ev.get("error") or "warming up")})
            checklist.append({"label": f"{c}: OI ≤ 95% of its 4-h max, print ≤ 10 min old",
                              "ok": (ev["oi_drop_pct"] <= -5.0 and (ev.get("oi_age_min") or 0) <= 10) if ev.get("oi_drop_pct") is not None else None,
                              "value": (f"{ev['oi_drop_pct']:+.2f}%, {ev.get('oi_age_min')} min old" if ev.get("oi_drop_pct") is not None
                                        else f"{ev.get('oi_samples', 0)} OI samples")})
            if ev.get("cooldown_min_left"):
                checklist.append({"label": f"{c}: one signal per 24 h", "ok": False, "value": f"{ev['cooldown_min_left']:.0f} min left"})
        verdict, headline = "none", "No liquidation flush: " + ", ".join(
            f"{c} {ev['drop_pct']:+.1f}%" for c, ev in st["coins"].items() if ev.get("drop_pct") is not None) if st["enabled"] else \
            "crypto_flush poller is off in this service"
        if not st["enabled"]:
            verdict = "none"
        elif fresh:
            verdict = "buy"
            r = fresh[0]
            headline = f"{r['coin']} flush at {r['ts'][11:16]} ET: {r['drop_pct']:+.1f}% vs its 4-h max, OI {r['oi_drop_pct']:+.1f}% — buy, out at +24 h"
            reasons.append("R0 out of sample: +1.74% at +24 h [+0.82, +2.74], 76% wins, n = 38")
            reasons.append("paper leg is log-only (synthetic micro future: no ledger for it in this checkout)" if r["trade"]
                           else "not armed: logged only; arm crypto_flush to record the paper micro-future leg")
        elif open_:
            verdict = "wait"
            headline = f"{len(open_)} paper micro-future(s) open, out at +24 h"
        trade = None
        if fresh or open_:
            r = (fresh or open_)[0]
            spec = COINS[r["coin"]]
            trade = {"structure": "synthetic micro future (log-only)", "legs": f"+1 {spec['micro']} ({spec['size']:g} {r['coin']})",
                     "expiry": None, "est_debit": r.get("entry_price") or r.get("price"), "max_loss": None, "max_profit": None,
                     "hold_rule": "exit at +24 h, no stop; 0.1% slippage each way"}
        return {"id": "crypto_flush", "title": "Crypto liquidation flush (R0)", "verdict": verdict, "headline": headline,
                "reasons": reasons, "checklist": checklist, "trade": trade, "armed": st["armed"], "experimental": False,
                "detail": {"coins": st["coins"], "recent": recent[:5], "open": open_}}
