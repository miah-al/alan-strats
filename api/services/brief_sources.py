"""
api/services/brief_sources.py — what the morning brief reads before 10:00 ET, and where each input comes from.

Everything here is best effort: a source that fails answers with a note, never an exception, so the brief is always
written (the rules fallback needs only the market and operations blocks, and even those may be partly empty).

  calendar    the service's calendar (data/macro_calendar.json, the third-Friday rule, db/seed/events/exchange.csv)
              for today and the next session, plus the mega-cap earnings list: db/seed/events/megacap.csv (hand-kept
              from the companies' own notices) and, when asked, yfinance's calendar for the eight names (through the
              request gate, cached a day by api/services/earnings.py)
  official    the Federal Reserve, BEA and SEC press-release RSS feeds: US government publications, public domain, no
              key, no terms beyond the SEC's request for a descriptive User-Agent (ALAN_TRADER_BRIEF_CONTACT). BLS is
              not polled: bls.gov answers a non-browser client with a 403 block page (checked 2026-09-25), and its
              releases (CPI, NFP) are scheduled items on the calendar anyway
  headlines   GDELT 2.0 DOC API (api.gdeltproject.org): free, no key, open data with attribution ("GDELT Project");
              titles, sources and timestamps only, never article text. Polite use: one request at a time, at least
              5 s apart (a 429 is retried once after 6 s), a query under ~120 characters (longer ones are refused as
              "too long"), the answer cached ten minutes
  posts       the CNN-hosted mirror of the open Truth Social archive (ix.cnn.io/data/truth-social/truth_archive.json,
              ~20 MB, regenerated every ~5 min): a HEAD first, the body fetched only when Last-Modified changed, once
              per brief. A third-party mirror that may stop without notice — its absence is a note, not a failure
  market      the market-data hub's quotes (NDX, QQQ, VIX, VXN, VIX3M: last, open, high, low, prev close) — no new
              streamer; the prior closes from yfinance's daily history (one gated call) when the hub lacks a symbol;
              yesterday's NDX bar from the stored daily bars (read only)
  operations  the quote recorder's state, the broker stream, whether the condor is armed, the session type

None of it is a market-data vendor call outside the existing gate, and none of it needs a secret.
"""
from __future__ import annotations

import csv
import datetime as _dt
import html
import json
import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import Callable, Optional
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

logger = logging.getLogger("alan_trader.api.brief.sources")

NY = ZoneInfo("America/New_York")
UTC = _dt.timezone.utc
MEGA_CAPS = ("NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA", "AVGO")
MACRO_KINDS = ("fomc", "cpi", "nfp", "pce", "gdp")

OFFICIAL_FEEDS = (
    ("Fed", "https://www.federalreserve.gov/feeds/press_all.xml"),
    ("BEA", "https://apps.bea.gov/rss/rss.xml"),
    ("SEC", "https://www.sec.gov/news/pressreleases.rss"),
)
GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
GDELT_QUERY = '(tariff OR sanctions OR ceasefire OR airstrike OR nasdaq OR "trading halt" OR outage OR shutdown) sourcelang:english'
GDELT_MIN_GAP_S = 5.0
GDELT_RETRY_S = 20.0      # a 429 says "one every 5 seconds", but in practice a burst needs a longer pause
GDELT_TRIES = 3
GDELT_CACHE_S = 600.0
GDELT_MAX_RECORDS = 75
TRUTH_URL = "https://ix.cnn.io/data/truth-social/truth_archive.json"
MAX_HEADLINES = 20
MAX_POSTS = 30
POST_CHARS = 500
FEED_TIMEOUT_S = 10.0
ARCHIVE_TIMEOUT_S = (10.0, 90.0)

#: the report's morning flags; each one's out-of-sample mean P&L per skipped day = the filter's net cost against the
#: unfiltered condor divided by its skipped days (ai_risk/report.md, section "Verdict": F1 -14,697/12, F2 -5,593/3,
#: F3 -4,452/3, F4 -9,192/7, F5 -9,216/5, F6 -14,716/11, F7 -1,877/1 — the skipped days were WINNERS on average)
FLAGS = (
    ("F1", "scheduled macro day (FOMC, CPI, NFP, PCE, GDP, Jackson Hole)", 1225.0),
    ("F2", "mega-cap earnings reaction day", 1864.0),
    ("F3", "OPEX / quad witching", 1484.0),
    ("F4", "overnight gap beyond 1.35%", 1313.0),
    ("F5", "09:30-10:00 range beyond 1.00%", 1843.0),
    ("F6", "VXN above 25 or VIX above VIX3M", 1338.0),
    ("F7", "yesterday's range beyond 2.38%", 1877.0),
)
GAP_FLAG_PCT, RANGE_FLAG_PCT, VXN_FLAG, YDAY_RANGE_FLAG_PCT = 1.35, 1.00, 25.0, 2.38

_MARKET_TERMS = re.compile(
    r"\b(tariff|tariffs|china|chinese|fed\b|federal reserve|powell|interest rates?|rate cut|rate hike|iran|israel|"
    r"russia|ukraine|war\b|strike|strikes|sanction|sanctions|cease[- ]?fire|blockade|hormuz|oil|opec|markets?|stocks?|"
    r"nasdaq|dow\b|s&p|crypto|bitcoin|shutdown|debt ceiling|emergency|executive order|ban\b|nvidia|chips?|export|"
    r"trade deal|recession|inflation|jobs report|treasury|bonds?|dollar|tax|taxes|invasion|attack|bomb|nuclear)\b", re.I)
_SHOCK_TERMS = re.compile(
    r"\b(war|strikes?|airstrike|invasion|attack|bomb|tariff|tariffs|sanctions?|outage|halt|halted|bank failure|"
    r"collapse|default|emergency|blockade|cease[- ]?fire|shutdown|nuclear)\b", re.I)


def contact_user_agent() -> str:
    contact = os.environ.get("ALAN_TRADER_BRIEF_CONTACT", "").strip()
    return f"alan_trader paper-trading morning brief (personal research; {contact or 'contact not configured'})"


def previous_trading_day(d: _dt.date) -> _dt.date:
    from api.services.gex_recorder import previous_trading_day as p
    return p(d)


def next_trading_day(d: _dt.date) -> _dt.date:
    from api.services.gex_recorder import trading_day
    n = d + _dt.timedelta(days=1)
    while not trading_day(n):
        n += _dt.timedelta(days=1)
    return n


def since_for(day: _dt.date) -> _dt.datetime:
    """16:00 ET on the previous trading day (a Monday brief covers the weekend), tz-aware."""
    return _dt.datetime.combine(previous_trading_day(day), _dt.time(16, 0), tzinfo=NY)


def _et(ts: _dt.datetime) -> str:
    return ts.astimezone(NY).strftime("%Y-%m-%d %H:%M")


def clean_text(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


# ── calendar ──────────────────────────────────────────────────────────────────

def _megacap_seed() -> list[dict]:
    from api.bootstrap import WORKING_COPY
    path = Path(WORKING_COPY) / "db" / "seed" / "events" / "megacap.csv"
    try:
        with open(path, encoding="utf-8") as fh:
            return [r for r in csv.DictReader(fh) if r.get("date")]
    except OSError:
        return []


def _early_close(day: _dt.date) -> Optional[str]:
    from api.services.calendar_events import _exchange
    for r in _exchange():
        if r.get("date") == day.isoformat() and r.get("kind") == "early_close":
            return r.get("label") or "early close"
    return None


def calendar_block(day: _dt.date, include_earnings: bool = True) -> dict:
    """Today's and the next session's scheduled items, and the flags the calendar alone decides."""
    from api.services.calendar_events import events
    nxt = next_trading_day(day)
    out = {"today": [], "next_session": [], "next_session_date": nxt.isoformat(), "macro_today": False,
           "megacap_reaction": False, "opex": False, "early_close": _early_close(day), "notes": []}
    try:
        evs, warns = events(days=(nxt - day).days, symbols=None, today=day)
        out["notes"] += warns
    except Exception as exc:  # noqa: BLE001
        evs = []
        out["notes"].append(f"calendar unavailable: {exc}")
    for e in evs:
        line = f"{e.get('time') or '--:--'} {e['title']}"
        if e["date"] == day:
            out["today"].append(line)
            if e["kind"] in MACRO_KINDS or "jackson hole" in str(e["title"]).lower():
                out["macro_today"] = True
            if e["kind"] == "opex":
                out["opex"] = True
        elif e["date"] == nxt:
            out["next_session"].append(line)
    prev = previous_trading_day(day)
    for r in _megacap_seed():
        try:
            d = _dt.date.fromisoformat(r["date"])
        except ValueError:
            continue
        label = r.get("label") or r.get("kind") or "mega-cap earnings"
        if d == prev:
            out["today"].append(f"--:-- {label} (reported {d}, after the close): reaction day")
            out["megacap_reaction"] = True
        elif d == day:
            out["today"].append(f"16:00+ {label} (after the close)")
        elif d == nxt:
            out["next_session"].append(f"--:-- {label} reaction day")
    if include_earnings:
        try:
            from api.services.earnings import earnings_dates
            for sym in MEGA_CAPS:
                for d in earnings_dates(sym):
                    if d == day:
                        out["today"].append(f"--:-- {sym} earnings (yfinance; after the close unless noted)")
                    elif d == nxt:
                        out["next_session"].append(f"--:-- {sym} earnings (yfinance)")
        except Exception as exc:  # noqa: BLE001
            out["notes"].append(f"mega-cap earnings dates unavailable: {exc}")
    return out


# ── official releases (RSS) ───────────────────────────────────────────────────

def _parse_rfc_date(s: str) -> Optional[_dt.datetime]:
    if not s:
        return None
    from email.utils import parsedate_to_datetime
    try:
        d = parsedate_to_datetime(s)
    except (TypeError, ValueError):
        try:
            d = _dt.datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def parse_feed(text, source: str) -> list[dict]:
    """RSS 2.0 or Atom items as [{time, source, title, link}] (time tz-aware; items without a date are dropped).
    ``text`` may be bytes (preferred: the parser reads the declaration's encoding itself) or str."""
    if isinstance(text, bytes):
        data = text.lstrip(b"\xef\xbb\xbf \r\n\t")                          # the Fed's feed starts with a BOM
    else:
        data = (text or "").lstrip("﻿ \r\n\t")
        if data.startswith("ï»¿"):                                          # the same BOM read as Latin-1
            data = data[3:].lstrip()
        data = data.encode("utf-8")
        data = re.sub(rb'^(<\?xml[^>]*?)\s+encoding="[^"]*"', rb"\1", data)  # it is UTF-8 now whatever it said
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return []
    out = []
    ns = {"a": "http://www.w3.org/2005/Atom"}
    for item in root.iter("item"):
        title = clean_text(item.findtext("title") or "")
        when = _parse_rfc_date((item.findtext("pubDate") or item.findtext("{http://purl.org/dc/elements/1.1/}date") or "").strip())
        if title and when:
            out.append({"time": when, "source": source, "title": title, "link": (item.findtext("link") or "").strip()})
    for entry in root.iter("{http://www.w3.org/2005/Atom}entry"):
        title = clean_text(entry.findtext("a:title", default="", namespaces=ns))
        when = _parse_rfc_date(entry.findtext("a:published", default="", namespaces=ns) or
                               entry.findtext("a:updated", default="", namespaces=ns))
        link = entry.find("a:link", ns)
        if title and when:
            out.append({"time": when, "source": source, "title": title,
                        "link": (link.get("href") if link is not None else "") or ""})
    return out


def official_block(since: _dt.datetime, get: Optional[Callable] = None) -> dict:
    get = get or _requests_get
    items, notes = [], []
    for name, url in OFFICIAL_FEEDS:
        try:
            r = get(url, headers={"User-Agent": contact_user_agent()}, timeout=FEED_TIMEOUT_S)
            if r.status_code != 200:
                notes.append(f"{name} feed answered {r.status_code}")
                continue
            for it in parse_feed(getattr(r, "content", None) or r.text, name):
                if it["time"] >= since:
                    items.append(it)
        except Exception as exc:  # noqa: BLE001
            notes.append(f"{name} feed unavailable: {type(exc).__name__}")
    items.sort(key=lambda x: x["time"], reverse=True)
    return {"items": [{"time_et": _et(i["time"]), "source": i["source"], "title": i["title"], "link": i["link"]}
                      for i in items[:30]], "notes": notes}


# ── overnight headlines (GDELT) ───────────────────────────────────────────────

_GDELT_LOCK = threading.Lock()
_GDELT_LAST = 0.0
_GDELT_CACHE: dict = {}


def _norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", t.lower())[:80].strip()


def cluster_articles(articles: list[dict], since: _dt.datetime, limit: int = MAX_HEADLINES) -> list[dict]:
    """GDELT ArtList rows -> the top ``limit`` headlines by distinct source count, then recency."""
    groups: dict[str, dict] = {}
    for a in articles:
        title = clean_text(a.get("title") or "")
        seen = str(a.get("seendate") or "")
        try:
            when = _dt.datetime.strptime(seen, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        except ValueError:
            continue
        if not title or when < since:
            continue
        key = _norm_title(title)
        g = groups.setdefault(key, {"title": title, "domains": set(), "first": when, "last": when,
                                    "url": a.get("url") or "", "domain": a.get("domain") or ""})
        g["domains"].add(a.get("domain") or "?")
        g["first"], g["last"] = min(g["first"], when), max(g["last"], when)
    rows = sorted(groups.values(), key=lambda g: (len(g["domains"]), g["last"]), reverse=True)[:limit]
    return [{"time_et": _et(g["first"]), "sources": len(g["domains"]), "domain": g["domain"], "title": g["title"],
             "url": g["url"], "shock_terms": bool(_SHOCK_TERMS.search(g["title"]))} for g in rows]


def headlines_block(since: _dt.datetime, now: Optional[_dt.datetime] = None, get: Optional[Callable] = None) -> dict:
    """The overnight headline clusters from GDELT (one request, rate limited, cached ten minutes)."""
    global _GDELT_LAST
    get = get or _requests_get
    now = now or _dt.datetime.now(UTC)
    hours = max(1, min(96, int((now - since).total_seconds() // 3600) + 1))
    key = (since.isoformat(), hours)
    with _GDELT_LOCK:
        hit = _GDELT_CACHE.get("last")
        if hit and hit[0] == key and time.monotonic() - hit[1] < GDELT_CACHE_S:
            return hit[2]
        out = {"items": [], "notes": ["GDELT: no answer"], "attribution": "GDELT Project"}
        for attempt in range(GDELT_TRIES):
            wait = GDELT_MIN_GAP_S - (time.monotonic() - _GDELT_LAST)
            if wait > 0:
                time.sleep(wait)
            _GDELT_LAST = time.monotonic()
            try:
                r = get(GDELT_URL, params={"query": GDELT_QUERY, "mode": "ArtList", "format": "json",
                                           "timespan": f"{hours}h", "maxrecords": GDELT_MAX_RECORDS, "sort": "DateDesc"},
                        headers={"User-Agent": contact_user_agent()}, timeout=FEED_TIMEOUT_S * 3)
            except Exception as exc:  # noqa: BLE001
                out = {"items": [], "notes": [f"GDELT unavailable: {type(exc).__name__}"], "attribution": "GDELT Project"}
                break
            if r.status_code == 429 and attempt < GDELT_TRIES - 1:
                time.sleep(GDELT_RETRY_S)                       # "one request every 5 seconds": once more, later
                continue
            if r.status_code != 200:
                out = {"items": [], "notes": [f"GDELT answered {r.status_code}"], "attribution": "GDELT Project"}
                break
            try:
                arts = (r.json() or {}).get("articles") or []
            except Exception:  # noqa: BLE001 — a 200 with a plain-text refusal ("query too long")
                out = {"items": [], "notes": [f"GDELT refused the query: {str(r.text)[:80]}"], "attribution": "GDELT Project"}
                break
            out = {"items": cluster_articles(arts, since), "notes": [], "attribution": "GDELT Project", "articles": len(arts),
                   **({"retries": attempt} if attempt else {})}
            break
        _GDELT_CACHE["last"] = (key, time.monotonic(), out)
        return out


# ── presidential posts (the open Truth Social archive's CNN mirror) ───────────

_TRUTH_LOCK = threading.Lock()
_TRUTH_CACHE: dict = {"modified": None, "posts": None, "fetched": 0.0}


def tag_post(text: str) -> list[str]:
    """The market-relevance tag: the distinct market terms a post mentions (empty = not market relevant)."""
    return sorted({m.group(0).lower().strip() for m in _MARKET_TERMS.finditer(text or "")})


def select_posts(archive: list[dict], since: _dt.datetime, limit: int = MAX_POSTS) -> list[dict]:
    rows = []
    for p in archive or []:
        try:
            when = _dt.datetime.fromisoformat(str(p.get("created_at") or "").replace("Z", "+00:00"))
        except ValueError:
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        if when < since:
            continue
        text = clean_text(p.get("content") or "")
        if not text:
            continue
        tags = tag_post(text)
        rows.append({"time_et": _et(when), "text": text[:POST_CHARS], "market_relevant": bool(tags), "tags": tags,
                     "id": str(p.get("id") or "")})
    rows.sort(key=lambda r: r["time_et"], reverse=True)
    relevant = [r for r in rows if r["market_relevant"]]
    rest = [r for r in rows if not r["market_relevant"]]
    return (relevant + rest)[:limit]


def posts_block(since: _dt.datetime, get: Optional[Callable] = None, head: Optional[Callable] = None) -> dict:
    get, head = get or _requests_get, head or _requests_head
    notes: list[str] = []
    ua = {"User-Agent": contact_user_agent()}
    with _TRUTH_LOCK:
        try:
            modified = None
            try:
                h = head(TRUTH_URL, headers=ua, timeout=FEED_TIMEOUT_S, allow_redirects=True)
                modified = h.headers.get("Last-Modified") if h.status_code == 200 else None
            except Exception as exc:  # noqa: BLE001
                notes.append(f"archive HEAD failed: {type(exc).__name__}")
            cached = _TRUTH_CACHE["posts"]
            fresh = cached is not None and modified is not None and modified == _TRUTH_CACHE["modified"]
            if not fresh:
                r = get(TRUTH_URL, headers=ua, timeout=ARCHIVE_TIMEOUT_S)
                if r.status_code != 200:
                    raise RuntimeError(f"archive answered {r.status_code}")
                data = r.json()
                if not isinstance(data, list):
                    raise RuntimeError("archive is not a list")
                cutoff = (since - _dt.timedelta(days=3)).isoformat()
                cached = [p for p in data if str(p.get("created_at") or "") >= cutoff]
                _TRUTH_CACHE.update(modified=modified, posts=cached, fetched=time.monotonic())
            posts = select_posts(cached or [], since)
            return {"items": posts, "notes": notes, "source": "ix.cnn.io truth-social archive mirror",
                    "archive_modified": _TRUTH_CACHE["modified"]}
        except Exception as exc:  # noqa: BLE001
            notes.append(f"posts unavailable: {type(exc).__name__}: {str(exc)[:80]}")
            return {"items": [], "notes": notes, "source": "ix.cnn.io truth-social archive mirror"}


# ── market levels ─────────────────────────────────────────────────────────────

def _pct(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None or not b:
        return None
    return round((a - b) / b * 100.0, 3)


def _prior_closes_yf(symbols: list[str]) -> dict[str, float]:
    from api.services.structure import _closes_yf
    out = {}
    for s, series in _closes_yf(symbols).items():
        if len(series):
            out[s] = float(series.iloc[-1])
    return out


def market_block(hub, day: _dt.date, prior_closes: Optional[Callable[[list[str]], dict]] = None,
                 network: bool = True) -> dict:
    """NDX / QQQ / VIX / VXN / VIX3M as the hub streams them, the gap and the session range so far, yesterday's bar.
    With ``network`` off the yfinance prior-close fallback is skipped (the hub and the stored bars only)."""
    out: dict = {"source": [], "notes": []}
    quotes: dict[str, dict] = {}
    if hub is not None and getattr(hub, "providers", None):
        try:
            for q in hub.snapshot(["NDX", "QQQ", "VIX", "VXN", "VIX3M"], wait=4.0):
                if q.get("last") is not None or q.get("prev_close") is not None:
                    quotes[q["symbol"]] = q
            if quotes:
                out["source"].append("hub")
        except Exception as exc:  # noqa: BLE001
            out["notes"].append(f"hub quotes unavailable: {exc}")
    ndx = quotes.get("NDX") or {}
    proxy = quotes.get("QQQ") or {}
    lvl = ndx if ndx.get("prev_close") else proxy
    out["index"] = "NDX" if lvl is ndx else ("QQQ" if lvl else None)
    out["prev_close"] = lvl.get("prev_close")
    out["open"] = lvl.get("open")
    out["last"] = lvl.get("last")
    out["high"], out["low"] = lvl.get("high"), lvl.get("low")
    out["gap_pct"] = _pct(lvl.get("open"), lvl.get("prev_close"))
    out["move_pct"] = _pct(lvl.get("last"), lvl.get("prev_close"))
    if out["gap_pct"] is None and out["move_pct"] is not None:
        out["gap_pct"], out["gap_note"] = out["move_pct"], "open not streamed: last vs prior close"
    rng = None
    if lvl.get("high") is not None and lvl.get("low") is not None and lvl.get("prev_close"):
        rng = round((float(lvl["high"]) - float(lvl["low"])) / float(lvl["prev_close"]) * 100.0, 3)
    out["range_pct"] = rng
    for name in ("VIX", "VXN", "VIX3M"):
        q = quotes.get(name) or {}
        out[name.lower()] = q.get("last")
        out[name.lower() + "_prev"] = q.get("prev_close")
    need = [n for n in ("VIX", "VXN", "VIX3M") if out.get(n.lower()) is None and out.get(n.lower() + "_prev") is None]
    if need and not network and prior_closes is None:
        out["notes"].append("no prior close for " + ", ".join(need) + " (network sources off)")
        need = []
    if need:
        try:
            fn = prior_closes or _prior_closes_yf
            closes = fn(["^" + n for n in need])
            for n in need:
                if closes.get("^" + n) is not None:
                    out[n.lower() + "_prev"] = closes["^" + n]
            if closes:
                out["source"].append("yfinance prior closes: " + ", ".join(need))
        except Exception as exc:  # noqa: BLE001
            out["notes"].append(f"prior closes unavailable for {', '.join(need)}: {type(exc).__name__}")
    vix = out.get("vix") if out.get("vix") is not None else out.get("vix_prev")
    v3 = out.get("vix3m") if out.get("vix3m") is not None else out.get("vix3m_prev")
    out["vix_used"], out["vix3m_used"] = vix, v3
    out["vix_ratio"] = round(float(vix) / float(v3), 3) if (vix and v3) else None
    vxn = out.get("vxn") if out.get("vxn") is not None else out.get("vxn_prev")
    out["vxn_used"] = vxn
    out["vxn_chg"] = (round(float(out["vxn"]) - float(out["vxn_prev"]), 2)
                      if out.get("vxn") is not None and out.get("vxn_prev") is not None else None)
    out["yday_range_pct"], out["yday_return_pct"] = None, None
    try:
        from api.services.db import require_db
        from db.client import get_price_bars
        prev = previous_trading_day(day)
        df = get_price_bars(require_db(), "NDX", prev - _dt.timedelta(days=10), prev)
        if df is not None and len(df) >= 2:
            y, yy = df.iloc[-1], df.iloc[-2]
            out["yday_range_pct"] = _pct(float(y["high"]), float(yy["close"])) - _pct(float(y["low"]), float(yy["close"]))
            out["yday_range_pct"] = round(out["yday_range_pct"], 3)
            out["yday_return_pct"] = _pct(float(y["close"]), float(yy["close"]))
            out["yday_date"] = str(y["date"])[:10] if "date" in df.columns else None
            out["source"].append("stored NDX daily bars")
    except Exception as exc:  # noqa: BLE001
        out["notes"].append(f"yesterday's NDX bar unavailable: {type(exc).__name__}")
    return out


# ── operations ────────────────────────────────────────────────────────────────

def operations_block(hub, arms, recorder, day: _dt.date, early_close: Optional[str]) -> dict:
    out = {"recorder_on": None, "recorder_written": None, "recorder_error": None, "streaming": None,
           "condor_armed": None, "condor_quote": None, "expected_credit": None,
           "session_type": "early close" if early_close else "normal", "notes": []}
    try:
        st = recorder.status() if recorder is not None else None
        if st is not None:
            out["recorder_on"], out["recorder_written"] = bool(st.get("on")), st.get("written")
            out["recorder_error"] = st.get("last_error")
    except Exception as exc:  # noqa: BLE001
        out["notes"].append(f"recorder status unavailable: {exc}")
    try:
        if hub is not None:
            ps = hub.providers_status()
            tt = next((p for p in ps if p.get("name") == "tastytrade"), None)
            out["streaming"] = bool(tt and str(tt.get("state", "")).lower() in ("connected", "streaming", "on"))
            if tt is None:
                out["notes"].append("no tastytrade provider in this process")
    except Exception as exc:  # noqa: BLE001
        out["notes"].append(f"stream status unavailable: {exc}")
    try:
        if arms is not None:
            rows = arms.arms()
            out["condor_armed"] = any(r.get("strategy") == "ndx_0dte_condor" for r in rows)
    except Exception as exc:  # noqa: BLE001
        out["notes"].append(f"arms unavailable: {exc}")
    out["notes"].append("expected credit is not estimated before 10:00: the runner's own width gate applies at entry")
    return out


# ── flags and the whole sheet ─────────────────────────────────────────────────

def flags_firing(cal: dict, mkt: dict) -> list[dict]:
    fired = []
    checks = {
        "F1": bool(cal.get("macro_today")),
        "F2": bool(cal.get("megacap_reaction")),
        "F3": bool(cal.get("opex")),
        "F4": mkt.get("gap_pct") is not None and abs(float(mkt["gap_pct"])) > GAP_FLAG_PCT,
        "F5": mkt.get("range_pct") is not None and float(mkt["range_pct"]) > RANGE_FLAG_PCT,
        "F6": ((mkt.get("vxn_used") is not None and float(mkt["vxn_used"]) > VXN_FLAG) or
               (mkt.get("vix_ratio") is not None and float(mkt["vix_ratio"]) > 1.0)),
        "F7": mkt.get("yday_range_pct") is not None and float(mkt["yday_range_pct"]) > YDAY_RANGE_FLAG_PCT,
    }
    for fid, name, mean in FLAGS:
        if checks.get(fid):
            fired.append({"id": fid, "name": name, "oos_mean": mean})
    return fired


class Sources:
    """The live sources, bound to the service's hub, arm scheduler and quote recorder."""

    def __init__(self, hub=None, arms=None, recorder=None, *, network: bool = True):
        self.hub, self.arms, self.recorder, self.network = hub, arms, recorder, network

    def gather(self, day: _dt.date, now: Optional[_dt.datetime] = None) -> dict:
        now = now or _dt.datetime.now(NY)
        since = since_for(day)
        cal = calendar_block(day, include_earnings=self.network)
        if self.network:
            official = official_block(since)
            heads = headlines_block(since, now.astimezone(UTC))
            posts = posts_block(since)
        else:
            off = {"items": [], "notes": ["network sources off"]}
            official, heads, posts = dict(off), dict(off), dict(off)
        mkt = market_block(self.hub, day, network=self.network)
        ops = operations_block(self.hub, self.arms, self.recorder, day, cal.get("early_close"))
        return {"date": day.isoformat(), "weekday": day.strftime("%A"), "as_of": now.astimezone(NY).isoformat(timespec="minutes"),
                "since": since.isoformat(timespec="minutes"), "calendar": cal, "official": official,
                "headlines": heads, "posts": posts, "market": mkt, "operations": ops, "flags": flags_firing(cal, mkt)}


def _requests_get(url, **kw):
    import requests
    return requests.get(url, **kw)


def _requests_head(url, **kw):
    import requests
    return requests.head(url, **kw)


def render_user_prompt(inputs: dict) -> str:
    """The report's user template (section 6.3), filled from the sheet."""
    def lines(items, fmt, empty="none"):
        return ("\n  " + "\n  ".join(fmt(i) for i in items)) if items else " " + empty

    cal, off, heads, posts, m, ops = (inputs.get(k) or {} for k in ("calendar", "official", "headlines", "posts", "market", "operations"))

    def num(v, nd=2, suffix=""):
        return "n/a" if v is None else f"{float(v):,.{nd}f}{suffix}"

    def pct(v):
        return "n/a" if v is None else f"{float(v):+.2f}%"

    parts = [
        f"DATE: {inputs.get('date')} ({inputs.get('weekday')}), {str(inputs.get('as_of', ''))[11:16]} ET",
        "CALENDAR TODAY:" + lines(cal.get("today") or [], str),
        f"CALENDAR NEXT SESSION ({cal.get('next_session_date')}):" + lines(cal.get("next_session") or [], str),
        f"OFFICIAL RELEASES SINCE {inputs.get('since', '')[:16]} ET:" +
        lines(off.get("items") or [], lambda i: f"{i['time_et']} [{i['source']}] {i['title']}"),
        "OVERNIGHT HEADLINES (top by source count; titles only, GDELT):" +
        lines(heads.get("items") or [], lambda i: f"{i['time_et']} ({i['sources']} sources, {i['domain']}) {i['title']}"),
        "PRESIDENTIAL POSTS SINCE THEN (verbatim, ET; tag = market terms mentioned, empty = none):" +
        lines(posts.get("items") or [], lambda p: f"{p['time_et']} [{', '.join(p['tags']) or 'not market related'}] {p['text']}"),
        (f"MARKET: {m.get('index') or 'index'} prior close {num(m.get('prev_close'))}; open {num(m.get('open'))} "
         f"(gap {pct(m.get('gap_pct'))}{'; ' + m['gap_note'] if m.get('gap_note') else ''}); session high/low "
         f"{num(m.get('high'))}/{num(m.get('low'))} (range {pct(m.get('range_pct')).lstrip('+')}); now {num(m.get('last'))}; "
         f"VXN {num(m.get('vxn_used'), 1)} (prior close {num(m.get('vxn_prev'), 1)}, chg {num(m.get('vxn_chg'), 1)}); "
         f"VIX {num(m.get('vix_used'), 1)}; VIX3M {num(m.get('vix3m_used'), 1)}; VIX/VIX3M {num(m.get('vix_ratio'), 2)}; "
         f"yesterday's range {pct(m.get('yday_range_pct')).lstrip('+')} and return {pct(m.get('yday_return_pct'))}"),
        (f"OPERATIONS: quote recorder {'up' if ops.get('recorder_on') else 'DOWN' if ops.get('recorder_on') is False else 'unknown'}"
         f" ({ops.get('recorder_written') or 0} rows written today; error: {ops.get('recorder_error') or 'none'}); broker stream "
         f"{'up' if ops.get('streaming') else 'DOWN' if ops.get('streaming') is False else 'unknown'}; condor runner "
         f"{'armed' if ops.get('condor_armed') else 'NOT armed' if ops.get('condor_armed') is False else 'unknown'}; "
         f"four-leg condor quote {ops.get('condor_quote') or 'n/a'}; expected credit {ops.get('expected_credit') or 'n/a'}; "
         f"session type {ops.get('session_type')}"),
        "HISTORICAL FLAGS FIRING TODAY:" +
        lines(inputs.get("flags") or [], lambda f: f"{f['id']} {f['name']}: out-of-sample mean when it fired {f['oos_mean']:+,.0f} $/trade"),
        "Respond with the JSON object only.",
    ]
    notes = [n for blk in (cal, off, heads, posts, m, ops) for n in (blk.get("notes") or [])]
    if notes:
        parts.insert(-1, "SOURCE NOTES: " + "; ".join(notes))
    return "\n".join(parts)


def digest(inputs: dict) -> dict:
    """What is stored with the brief: the sheet as given to the model (no secrets are ever in it), JSON-safe."""
    return json.loads(json.dumps(inputs, default=str))
