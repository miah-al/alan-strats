"""
api/services/quote_recorder.py — record the same-day NDXP chain's quotes near the money, every 15 seconds of the session.

Why: every NDX 0DTE backtest so far priced spreads from one-minute trade prints. A leg's last print can be minutes old,
so pairing a fresh leg with a stale one invented spread moves that never traded (research/print_synchrony_test.md;
2026-09-24: +$16,384 replayed on stale prints against -$2,392 with both legs printed in the same minute, and -$1,117
live). And whatever edge the tastytrade log had sits inside the bid/ask, which prints don't show
(research/tastytrade_2026-09/DATA_REQUIREMENTS.md: NBBO history is a paid tier). So the service records its own:
bid, ask, their sizes, last and day volume for every contract it watches, from the broker stream it already runs.

What it watches: today's NDXP calls and puts on the 25-point grid within ``QUOTE_BAND`` (400) points of NDX, re-centred
when NDX moves more than a quarter of the band. Only while the tastytrade streamer is connected: streamed quotes cost
no request budget, and with the stream down the hub would fall back to polled providers, which do. Outside 09:29-16:01
ET, on weekends, or with the stream down, nothing is watched and nothing is written.

Where: ``<working copy>/paper_state/quotes/NDXP/<YYYY-MM-DD>.csv.gz``, one row per contract per 15-second snapshot,
appended once a minute (each append is its own gzip member; readers see one file). Columns: ts (ET, ISO), underlying
price, symbol, right, strike, bid, ask, bid_size, ask_size, last, volume, quote_time.

Environment: ``ALAN_TRADER_QUOTE_RECORD`` (``1``; ``0`` off — the test suite's default).
"""
from __future__ import annotations

import csv
import datetime as _dt
import gzip
import io
import logging
import os
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger("alan_trader.api.quote_recorder")

UNDERLYING = "NDX"
ROOT = "NDXP"
STEP = 25.0
QUOTE_BAND = 400.0
EVERY_S = 15.0
FLUSH_EVERY = 4            # snapshots per file append (a minute)
START, END = _dt.time(9, 29), _dt.time(16, 1)
OWNER = "quote-recorder"
COLUMNS = ["ts", "underlying", "symbol", "right", "strike", "bid", "ask", "bid_size", "ask_size", "last", "volume", "quote_time"]


def enabled() -> bool:
    return os.environ.get("ALAN_TRADER_QUOTE_RECORD", "1").strip().lower() not in ("0", "off", "false", "no")


def default_dir() -> Path:
    from api.bootstrap import WORKING_COPY
    return Path(WORKING_COPY) / "paper_state" / "quotes" / ROOT


def _now_et() -> _dt.datetime:
    from zoneinfo import ZoneInfo
    return _dt.datetime.now(ZoneInfo("America/New_York"))


def strikes_around(spot: float, band: float = QUOTE_BAND, step: float = STEP) -> list[float]:
    lo = (int((spot - band) // step) + 1) * step
    hi = int((spot + band) // step) * step
    return [float(k) for k in range(int(lo), int(hi) + 1, int(step))]


class QuoteRecorder:
    def __init__(self, hub, out_dir: Optional[Path] = None, now=_now_et):
        self.hub = hub
        self.out_dir = out_dir
        self._now = now
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.center: Optional[float] = None
        self.symbols: list[str] = []
        self._meta: dict[str, tuple[str, float]] = {}
        self._rows: list[list] = []
        self._snapshots = 0
        self.written = 0
        self.last_error: Optional[str] = None

    # ── lifecycle ──────────────────────────────────────────────────────────────
    def start(self) -> None:
        if not enabled():
            logger.info("quote recorder off (ALAN_TRADER_QUOTE_RECORD)")
            return
        self._thread = threading.Thread(target=self._run, name="quote-recorder", daemon=True)
        self._thread.start()
        logger.info("quote recorder on: %s %s ±%.0f pts every %.0f s while streaming", UNDERLYING, ROOT, QUOTE_BAND, EVERY_S)

    def stop(self) -> None:
        self._stop.set()
        self._flush()
        self._unwatch()

    def status(self) -> dict:
        return {"on": self._thread is not None, "watching": len(self.symbols), "center": self.center, "written": self.written,
                "last_error": self.last_error}

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception as exc:  # noqa: BLE001 — a bad snapshot must not stop the recorder
                self.last_error = str(exc)[:200]
                logger.warning("quote recorder: %s", exc)
            self._stop.wait(EVERY_S)

    # ── one snapshot ───────────────────────────────────────────────────────────
    def _streaming(self) -> bool:
        p = getattr(self.hub, "by_name", {}).get("tastytrade") if self.hub is not None else None
        return bool(p is not None and getattr(p, "connected", False))

    def tick(self) -> int:
        """Take one snapshot if the session is open and the stream is up; returns rows buffered."""
        now = self._now()
        if now.weekday() >= 5 or not (START <= now.time() < END) or not self._streaming():
            self._flush()
            self._unwatch()
            return 0
        spot = self._spot()
        if spot is None:
            return 0
        self._watch_around(spot, now.date())
        quotes = self.hub.snapshot(self.symbols, wait=0.0)
        ts = now.isoformat(timespec="seconds")
        n = 0
        for q in quotes:
            sym = q.get("symbol")
            if sym not in self._meta or (q.get("bid") is None and q.get("ask") is None):
                continue
            right, strike = self._meta[sym]
            self._rows.append([ts, round(spot, 2), sym, right, strike, q.get("bid"), q.get("ask"), q.get("bid_size"),
                               q.get("ask_size"), q.get("last"), q.get("volume"), q.get("time")])
            n += 1
        self._snapshots += 1
        if self._snapshots % FLUSH_EVERY == 0:
            self._flush(now.date())
        return n

    def _spot(self) -> Optional[float]:
        try:
            q = self.hub.snapshot([UNDERLYING], wait=0.0)[0]
        except Exception:
            return None
        v = q.get("last") or q.get("mid")
        return float(v) if v else None

    def _watch_around(self, spot: float, day: _dt.date) -> None:
        if self.center is not None and abs(spot - self.center) < QUOTE_BAND / 4 and self.symbols:
            return
        from api.marketdata import symbols as SYM
        wanted, meta = [], {}
        for k in strikes_around(spot):
            for right in ("C", "P"):
                s = SYM.make_option(ROOT, day, right, k).occ   # the canonical spelling the hub keys on
                wanted.append(s)
                meta[s] = (right, k)
        stale = [s for s in self.symbols if s not in meta]
        if stale:
            self.hub.unwatch(OWNER, stale)
        self.symbols = self.hub.watch(OWNER, wanted) or wanted
        self._meta = {s: meta[s] for s in self.symbols if s in meta} or meta
        self.center = spot
        logger.info("quote recorder: watching %d %s contracts around %.0f", len(self.symbols), ROOT, spot)

    def _unwatch(self) -> None:
        if self.symbols and self.hub is not None:
            try:
                self.hub.unwatch_all(OWNER)
            except Exception:
                pass
        self.symbols, self._meta, self.center = [], {}, None

    # ── the file ───────────────────────────────────────────────────────────────
    def path_for(self, day: _dt.date) -> Path:
        return (self.out_dir or default_dir()) / f"{day.isoformat()}.csv.gz"

    def _flush(self, day: Optional[_dt.date] = None) -> None:
        if not self._rows:
            return
        day = day or _dt.date.fromisoformat(str(self._rows[0][0])[:10])
        path = self.path_for(day)
        path.parent.mkdir(parents=True, exist_ok=True)
        buf = io.StringIO()
        w = csv.writer(buf)
        if not path.exists():
            w.writerow(COLUMNS)
        w.writerows(self._rows)
        with gzip.open(path, "at", encoding="utf-8", newline="") as f:   # a new gzip member per append
            f.write(buf.getvalue())
        self.written += len(self._rows)
        self._rows = []


def read_day(path: Path):
    """The recorded day as a DataFrame (every appended member read as one file)."""
    import pandas as pd
    return pd.read_csv(path, compression="gzip")
