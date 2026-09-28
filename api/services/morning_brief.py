"""
api/services/morning_brief.py — the AI morning brief for the paper NDX 0DTE condor: a decision row, never an order.

At 09:50 ET on trading days (and on demand: POST /api/brief/run) the service gathers what is knowable before the
10:00 entry (api/services/brief_sources.py: today's calendar, official releases overnight, GDELT headline clusters,
the presidential posts, the hub's index and vol levels, the operational checks), decides GO / REDUCE / STAND_ASIDE,
and writes ONE row per day to app.MorningBrief. The paper condor (ledger A) trades every eligible day regardless; the
row only sizes a SHADOW ledger line (B = each closed trade's P&L x that day's size_multiplier), and
GET /api/brief/scorecard compares the two against the calendar gate (C) and the VIX-curve gate (D) and against random
skips of the same weight (api/services/brief_scorecard.py).

The research behind it (scratchpad ai_risk/report.md, Part 1): every calendar or volatility gate COST money on this
condor out of sample, about $15,000 per lot per year for the scheduled-macro and VIX gates, because the 0.16-delta
strikes move out when the morning is wild. So the default is GO; STAND_ASIDE is reserved for a concrete unscheduled
overnight shock or an operational failure; REDUCE (half size) is for two or more stacked soft concerns.

Two deciders, one output:
  llm    when ANTHROPIC_API_KEY is set: the Claude Messages API over plain HTTPS (the ``anthropic`` SDK is not in the
         service venv; api.anthropic.com is not a market-data host, so the request gate lets it through), model
         ALAN_TRADER_BRIEF_MODEL (default claude-opus-5-5), the report's system prompt, a JSON schema on the output
         (``output_config.format``), the reply validated here and passed through the guardrails; ANY failure (network,
         HTTP, refusal, malformed JSON, schema) falls back to the rules and says so in ``source``/``notes``
  rules  otherwise: GO unless a hard line is crossed (gap >= 3%, VIX > 35 with VIX > VIX3M, an early-close session,
         the quote recorder down / the credit gate impossible -> STAND_ASIDE); two or more soft concerns -> REDUCE 0.5

Guardrails outside the model (both deciders): a STAND_ASIDE with no high-weight reason of an unscheduled or operational
kind is downgraded to REDUCE and noted; confidence below 0.6 is treated as GO; size_multiplier follows the decision;
the row is written once and the day's decision stands (POST /api/brief/run replaces it only with ``force``, noted).

Environment: ``ANTHROPIC_API_KEY`` (never logged, never stored, never in a response); ``ALAN_TRADER_BRIEF_MODEL``;
``ALAN_TRADER_BRIEF`` = ``db`` (default) | ``memory`` (the test suite) | ``off``; ``ALAN_TRADER_BRIEF_SCHEDULER`` =
``1`` (default) | ``0`` (on demand only); ``ALAN_TRADER_BRIEF_NETWORK`` = ``1`` | ``0`` (no RSS / GDELT / archive
fetches: calendar, hub and operations only); ``ALAN_TRADER_BRIEF_CONTACT`` (the User-Agent's contact for the feeds).
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import threading
from typing import Callable, Optional
from zoneinfo import ZoneInfo

import pandas as pd

logger = logging.getLogger("alan_trader.api.brief")

NY = ZoneInfo("America/New_York")
UTC = _dt.timezone.utc
STRATEGY = "ndx_0dte_condor"
RUN_AT, RUN_UNTIL = _dt.time(9, 50), _dt.time(10, 30)
RETRY_S = 300.0
TICK_S = 30.0
DEFAULT_MODEL = "claude-opus-5-5"
API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
API_TIMEOUT_S = 150.0
MAX_TOKENS = 16000
PROMPT_VERSION = "2026-09-25.1"

DECISIONS = ("GO", "REDUCE", "STAND_ASIDE")
MULTIPLIER = {"GO": 1.0, "REDUCE": 0.5, "STAND_ASIDE": 0.0}
KINDS = ("calendar", "news", "post", "market", "operational")
WEIGHTS = ("low", "medium", "high")
UNSCHEDULED_KINDS = ("news", "post", "operational", "market")   # a STAND_ASIDE must rest on one of these, weight high
MIN_CONFIDENCE = 0.6
GAP_HARD_PCT, VIX_HARD, CREDIT_MIN = 3.0, 35.0, 12.0

SYSTEM_PROMPT = """You are the morning risk manager for a paper-traded 0DTE NDX iron condor (short 0.16-delta call and put, 100-point
wings, entered at 10:00 ET, held to the 16:00 settlement, one lot). Your job at 09:45 ET is to decide GO, REDUCE
(half size) or STAND_ASIDE for today, and to say why, in JSON only.

Facts you must reason from, not against:
- Historically (2024-10 to 2026-09, 170 trades) the condor made +$784 per trade out of sample with 86% wins; the
  average loss was -$4,195 and the worst -$8,737 (the full width).
- Scheduled macro days (FOMC, CPI, NFP, PCE, GDP), mega-cap earnings reaction days, OPEX, large overnight gaps,
  wide first half-hours and high VXN were all BETTER than average for this trade, because the strikes are chosen by
  delta and move out when the morning is volatile. Skipping those days cost about $15,000 per lot per year.
- The losing days were quiet mornings (small gap, small first half-hour, VXN 17-23, nothing scheduled) followed by an
  afternoon trend of 1.5-2%. Nothing visible at 09:45 has identified them so far.
Therefore: a scheduled event, a high VXN or a big gap is NOT by itself a reason to stand aside. STAND_ASIDE requires
a concrete, unscheduled overnight development that the history above does not cover (armed conflict beginning or
escalating overnight, a tariff or sanctions decree of market-wide scope, a systemic financial event, an exchange or
data outage, a gap of 3% or more, VIX above 35 with the term structure inverted), or an operational failure (quote
recorder down, expected credit under 12 points, early-close session). REDUCE is for a stack of two or more soft
concerns none of which alone would justify standing aside. Otherwise GO.
Cite only inputs you were given. Do not infer news from the price action. If a headline is ambiguous, say so and
weigh it at half. Confidence is your probability that the decision is the right one relative to GO, from 0.5 to 1.0.

Output vocabulary (the JSON schema enforces the shape): a reason's kind is calendar (a scheduled item), news (an
overnight headline or official release), post (a presidential post), market (levels, the gap, volatility) or
operational (the recorder, the stream, the credit, the session); its weight is high (decisive on its own), medium
(supporting) or low (noted, not acted on). A STAND_ASIDE must carry at least one high-weight reason of kind news, post
or operational, or of kind market only for the 3% gap / VIX-35-inverted lines; a calendar reason never justifies it.
size_multiplier is 1.0 for GO, 0.5 for REDUCE, 0.0 for STAND_ASIDE. headline is one plain sentence for a trader's
screen. events_seen lists the items you actually weighed. what_would_change_my_mind is the one observation between
now and 10:00 that would flip the decision."""

REPLY_SCHEMA = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": list(DECISIONS)},
        "confidence": {"type": "number"},
        "size_multiplier": {"type": "number"},
        "headline": {"type": "string"},
        "reasons": {"type": "array", "items": {
            "type": "object",
            "properties": {"kind": {"type": "string", "enum": list(KINDS)},
                           "weight": {"type": "string", "enum": list(WEIGHTS)},
                           "text": {"type": "string"}},
            "required": ["kind", "weight", "text"], "additionalProperties": False}},
        "events_seen": {"type": "array", "items": {
            "type": "object",
            "properties": {"time_et": {"type": "string"}, "source": {"type": "string"}, "headline": {"type": "string"},
                           "scope": {"type": "string", "enum": ["market_wide", "sector", "single_name", "none"]},
                           "in_calendar": {"type": "boolean"}},
            "required": ["time_et", "source", "headline", "scope", "in_calendar"], "additionalProperties": False}},
        "flags_fired": {"type": "array", "items": {"type": "string"}},
        "what_would_change_my_mind": {"type": "string"},
    },
    "required": ["decision", "confidence", "size_multiplier", "headline", "reasons", "events_seen", "flags_fired",
                 "what_would_change_my_mind"],
    "additionalProperties": False,
}


class BriefSchemaError(ValueError):
    """The model's reply is not the brief we asked for."""


class BriefLlmError(RuntimeError):
    """The Messages API call failed (network, HTTP status, refusal, no text)."""


# ── the reply: validation and guardrails ──────────────────────────────────────

def _event_line(e) -> str:
    if isinstance(e, str):
        return e.strip()
    if not isinstance(e, dict):
        raise BriefSchemaError("events_seen item is neither a string nor an object")
    t, s, h = (str(e.get(k) or "").strip() for k in ("time_et", "source", "headline"))
    if not h:
        raise BriefSchemaError("events_seen item has no headline")
    scope = str(e.get("scope") or "")
    tail = f" [{scope}]" if scope and scope != "none" else ""
    cal = " (in calendar)" if e.get("in_calendar") else ""
    return " ".join(x for x in (t, f"[{s}]" if s else "", h) if x) + tail + cal


def validate_reply(obj) -> dict:
    """The model's JSON as the brief's own decision dict, or BriefSchemaError. Strict on types and enums; lenient on
    the numbers' range (clamped) so a 1.2 confidence is not a fallback but a 'maybe' is."""
    if not isinstance(obj, dict):
        raise BriefSchemaError("reply is not a JSON object")
    missing = [k for k in REPLY_SCHEMA["required"] if k not in obj]
    if missing:
        raise BriefSchemaError(f"reply lacks {', '.join(missing)}")
    decision = obj["decision"]
    if decision not in DECISIONS:
        raise BriefSchemaError(f"decision {decision!r} is not one of {DECISIONS}")
    try:
        confidence = float(obj["confidence"])
    except (TypeError, ValueError):
        raise BriefSchemaError("confidence is not a number")
    if not 0.0 <= confidence <= 1.0:
        raise BriefSchemaError(f"confidence {confidence} is outside 0..1")
    reasons = obj["reasons"]
    if not isinstance(reasons, list):
        raise BriefSchemaError("reasons is not a list")
    out_reasons = []
    for r in reasons:
        if not isinstance(r, dict) or r.get("kind") not in KINDS or r.get("weight") not in WEIGHTS or not str(r.get("text") or "").strip():
            raise BriefSchemaError(f"bad reason {r!r}")
        out_reasons.append({"kind": r["kind"], "weight": r["weight"], "text": str(r["text"]).strip()})
    if not isinstance(obj["events_seen"], list) or not isinstance(obj["flags_fired"], list):
        raise BriefSchemaError("events_seen / flags_fired are not lists")
    events = [_event_line(e) for e in obj["events_seen"]]
    flags = [str(f).strip() for f in obj["flags_fired"] if str(f).strip()]
    headline = str(obj.get("headline") or "").strip()
    change = str(obj.get("what_would_change_my_mind") or "").strip()
    if not headline:
        raise BriefSchemaError("headline is empty")
    return {"decision": decision, "confidence": round(confidence, 3), "size_multiplier": MULTIPLIER[decision],
            "headline": headline, "reasons": out_reasons, "events_seen": events, "flags_fired": flags,
            "what_would_change_my_mind": change}


def apply_guardrails(d: dict) -> tuple[dict, list[str]]:
    """The rules outside the model: a STAND_ASIDE needs a decisive unscheduled / operational reason; low confidence is
    GO; the multiplier follows the decision. Returns the (possibly changed) decision and what was changed."""
    notes: list[str] = []
    d = dict(d)
    if d["decision"] == "STAND_ASIDE":
        ok = any(r["weight"] == "high" and r["kind"] in UNSCHEDULED_KINDS for r in d["reasons"])
        if not ok:
            notes.append("guardrail: STAND_ASIDE without a high-weight unscheduled or operational reason -> REDUCE")
            d["decision"] = "REDUCE"
    if d["decision"] != "GO" and float(d["confidence"]) < MIN_CONFIDENCE:
        notes.append(f"guardrail: confidence {d['confidence']} below {MIN_CONFIDENCE} -> GO")
        d["decision"] = "GO"
    d["size_multiplier"] = MULTIPLIER[d["decision"]]
    return d, notes


# ── the rules fallback ────────────────────────────────────────────────────────

def rules_decision(inputs: dict) -> dict:
    m, ops, cal = (inputs.get(k) or {} for k in ("market", "operations", "calendar"))
    heads = (inputs.get("headlines") or {}).get("items") or []
    posts = (inputs.get("posts") or {}).get("items") or []
    hard: list[dict] = []
    soft: list[dict] = []

    def f(v):
        return None if v is None else float(v)

    gap, rng, vxn, vix, v3, yr = (f(m.get(k)) for k in ("gap_pct", "range_pct", "vxn_used", "vix_used", "vix3m_used", "yday_range_pct"))
    if gap is not None and abs(gap) >= GAP_HARD_PCT:
        hard.append({"kind": "market", "weight": "high", "text": f"Overnight gap {gap:+.2f}% is at or beyond the 3% line."})
    if vix is not None and v3 is not None and vix > VIX_HARD and vix > v3:
        hard.append({"kind": "market", "weight": "high",
                     "text": f"VIX {vix:.1f} is above 35 with the term structure inverted (VIX3M {v3:.1f})."})
    if cal.get("early_close"):
        hard.append({"kind": "operational", "weight": "high",
                     "text": f"Early-close session ({cal['early_close']}): settlement at 13:00, no trade by the trial plan."})
    if ops.get("recorder_on") is False:
        hard.append({"kind": "operational", "weight": "high",
                     "text": "The quote recorder is not running: the credit gate cannot be checked."})
    elif ops.get("streaming") is False:
        hard.append({"kind": "operational", "weight": "high",
                     "text": "The broker stream is down: no four-leg quote, so the credit gate cannot pass."})
    credit = f(ops.get("expected_credit"))
    if credit is not None and credit < CREDIT_MIN:
        hard.append({"kind": "operational", "weight": "high", "text": f"Expected credit {credit:.1f} pts is under 12."})

    if gap is not None and abs(gap) >= 1.35 and not any("gap" in h["text"].lower() for h in hard):
        soft.append({"kind": "market", "weight": "medium", "text": f"Overnight gap {gap:+.2f}% (F4; historically a better day)."})
    if rng is not None and rng >= 1.0:
        soft.append({"kind": "market", "weight": "medium", "text": f"Session range {rng:.2f}% so far (F5; historically a better day)."})
    if (vxn is not None and vxn > 25.0) or (vix is not None and v3 is not None and vix > v3):
        detail = f"VXN {vxn:.1f}" if vxn is not None else ""
        if vix is not None and v3 is not None and vix > v3:
            detail += (", " if detail else "") + f"VIX {vix:.1f} > VIX3M {v3:.1f}"
        soft.append({"kind": "market", "weight": "medium", "text": f"Volatility flag (F6): {detail}; historically a better day."})
    if yr is not None and yr > 2.38:
        soft.append({"kind": "market", "weight": "medium", "text": f"Yesterday's range {yr:.2f}% (F7)."})
    relevant = [p for p in posts if p.get("market_relevant")]
    if relevant:
        soft.append({"kind": "post", "weight": "medium",
                     "text": f"{len(relevant)} presidential post(s) overnight mention market terms "
                             f"({', '.join(sorted({t for p in relevant for t in p.get('tags', [])})[:6])}); the rules cannot read them."})
    shock = [h for h in heads if h.get("shock_terms") and int(h.get("sources") or 0) >= 3]
    if shock:
        soft.append({"kind": "news", "weight": "medium",
                     "text": f"{len(shock)} multi-source headline cluster(s) with shock terms overnight: \"{shock[0]['title'][:100]}\"."})

    reasons = hard + soft
    if cal.get("today"):
        reasons.append({"kind": "calendar", "weight": "low",
                        "text": "Scheduled today: " + "; ".join(cal["today"][:4]) + ". Scheduled days were better than average; not a reason to stand aside."})
    if ops.get("condor_armed") is False:
        reasons.append({"kind": "operational", "weight": "low", "text": "The condor runner is not armed today (nothing to size)."})
    if hard:
        decision, confidence = "STAND_ASIDE", 0.9
        headline = "Stand aside: " + hard[0]["text"]
    elif len(soft) >= 2:
        decision, confidence = "REDUCE", 0.65
        headline = f"Half size: {len(soft)} soft concerns stack ({'; '.join(s['text'].split(' (')[0] for s in soft[:2])})."
    else:
        decision, confidence = "GO", (0.75 if soft else 0.8)
        headline = "Go: nothing unscheduled overnight and the checklist passes." if not soft else \
            "Go: one soft concern only (" + soft[0]["text"].split(" (")[0] + "); history says trade."
    if not reasons:
        reasons.append({"kind": "market", "weight": "low", "text": "No hard line crossed and no soft concern on the sheet."})
    events = list(cal.get("today") or [])[:6]
    events += [f"{i['time_et']} [{i['source']}] {i['title']}" for i in ((inputs.get("official") or {}).get("items") or [])[:5]]
    events += [f"{h['time_et']} ({h['sources']} sources) {h['title']}" for h in heads[:5]]
    events += [f"{p['time_et']} [post] {p['text'][:120]}" for p in relevant[:5]]
    return {"decision": decision, "confidence": confidence, "size_multiplier": MULTIPLIER[decision], "headline": headline,
            "reasons": reasons, "events_seen": events, "flags_fired": [x["id"] for x in inputs.get("flags") or []],
            "what_would_change_my_mind": "A gap beyond 3%, VIX above 35 with the curve inverted, or the quote recorder "
                                         "stopping before 10:00 would flip this to STAND_ASIDE."}


# ── the LLM decider (plain HTTPS to the Messages API) ─────────────────────────

def api_key() -> Optional[str]:
    k = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    return k or None


def model_name() -> str:
    return os.environ.get("ALAN_TRADER_BRIEF_MODEL", "").strip() or DEFAULT_MODEL


def request_body(inputs: dict, model: str) -> dict:
    from api.services.brief_sources import render_user_prompt
    return {"model": model, "max_tokens": MAX_TOKENS, "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": render_user_prompt(inputs)}],
            "output_config": {"format": {"type": "json_schema", "schema": REPLY_SCHEMA}}}


def _post(url, **kw):
    import requests
    return requests.post(url, **kw)


def llm_decision(inputs: dict, model: Optional[str] = None, key: Optional[str] = None,
                 post: Optional[Callable] = None) -> tuple[dict, dict]:
    """(the validated decision, usage) or BriefLlmError / BriefSchemaError. The key goes in a header only; nothing
    here logs the request."""
    key = key or api_key()
    if not key:
        raise BriefLlmError("no ANTHROPIC_API_KEY")
    model = model or model_name()
    post = post or _post
    body = request_body(inputs, model)
    headers = {"x-api-key": key, "anthropic-version": API_VERSION, "content-type": "application/json"}
    try:
        r = post(API_URL, headers=headers, data=json.dumps(body), timeout=API_TIMEOUT_S)
    except Exception as exc:  # noqa: BLE001 — every transport failure is one fallback
        raise BriefLlmError(f"request failed: {type(exc).__name__}") from None
    status = getattr(r, "status_code", None)
    if status != 200:
        detail = ""
        try:
            detail = str((r.json() or {}).get("error", {}).get("message") or "")[:160]
        except Exception:  # noqa: BLE001
            pass
        raise BriefLlmError(f"HTTP {status}{': ' + detail if detail else ''}")
    try:
        msg = r.json()
    except Exception:  # noqa: BLE001
        raise BriefLlmError("response is not JSON") from None
    if msg.get("stop_reason") == "refusal":
        raise BriefLlmError("the model declined the request")
    text = next((b.get("text") for b in (msg.get("content") or []) if isinstance(b, dict) and b.get("type") == "text"), None)
    if not text:
        raise BriefLlmError(f"no text block (stop_reason {msg.get('stop_reason')})")
    try:
        parsed = json.loads(text)
    except ValueError as exc:
        raise BriefSchemaError(f"reply is not JSON: {exc}") from None
    usage = msg.get("usage") or {}
    return validate_reply(parsed), {"model": msg.get("model") or model, "input_tokens": usage.get("input_tokens"),
                                    "output_tokens": usage.get("output_tokens"), "stop_reason": msg.get("stop_reason")}


def decide(inputs: dict, *, model: Optional[str] = None, key: Optional[str] = None,
           post: Optional[Callable] = None, llm_enabled: bool = True) -> tuple[dict, str, list[str], dict]:
    """(decision after the guardrails, source, notes, usage)."""
    notes: list[str] = []
    usage: dict = {}
    key = key if key is not None else api_key()
    if llm_enabled and key:
        try:
            d, usage = llm_decision(inputs, model=model, key=key, post=post)
            d, g = apply_guardrails(d)
            return d, f"llm:{usage.get('model') or model or model_name()}", g, usage
        except (BriefLlmError, BriefSchemaError) as exc:
            notes.append(f"llm fallback: {type(exc).__name__}: {exc}")
            logger.warning("morning brief: the model path failed (%s); using the rules", exc)
    elif not llm_enabled:
        notes.append("llm off")
    else:
        notes.append("no ANTHROPIC_API_KEY: rules")
    d, g = apply_guardrails(rules_decision(inputs))
    return d, "rules", notes + g, usage


# ── the stores ────────────────────────────────────────────────────────────────

_COLS = ("id", "date", "created_at", "decision", "confidence", "size_multiplier", "headline", "reasons", "events_seen",
         "flags_fired", "what_would_change_my_mind", "source", "prompt_version", "inputs", "notes", "strategy")


def _utcnow() -> _dt.datetime:
    return _dt.datetime.now(UTC).replace(tzinfo=None)


class MemoryBriefStore:
    def __init__(self):
        self._rows: dict[tuple[str, _dt.date], dict] = {}
        self._lock = threading.Lock()
        self._next = 1

    def get(self, day: _dt.date, strategy: str = STRATEGY) -> Optional[dict]:
        with self._lock:
            r = self._rows.get((strategy, day))
            return dict(r) if r else None

    def put(self, row: dict, replace: bool = False) -> bool:
        key = (row.get("strategy") or STRATEGY, row["date"])
        with self._lock:
            if key in self._rows and not replace:
                return False
            r = dict(row, id=self._next, strategy=key[0], created_at=row.get("created_at") or _utcnow())
            self._rows[key] = r
            self._next += 1
            return True

    def history(self, since: _dt.date, strategy: str = STRATEGY) -> list[dict]:
        with self._lock:
            rows = [dict(r) for (s, d), r in self._rows.items() if s == strategy and d >= since]
        return sorted(rows, key=lambda r: r["date"], reverse=True)


class DbBriefStore:
    """app.MorningBrief (through the service's write guard; the app schema is on its allow-list)."""

    _SELECT = ("SELECT BriefId, BriefDate, CreatedAt, Decision, Confidence, SizeMultiplier, Headline, ReasonsJson, "
               "EventsJson, FlagsJson, ChangeMind, Source, PromptVersion, InputsJson, NotesJson, Strategy FROM app.MorningBrief")

    def _eng(self):
        from api.services.db import require_db
        return require_db()

    @staticmethod
    def _row(r) -> dict:
        d = dict(zip(_COLS, r))
        if isinstance(d["date"], _dt.datetime):
            d["date"] = d["date"].date()
        for k in ("reasons", "events_seen", "flags_fired", "inputs", "notes"):
            try:
                d[k] = json.loads(d[k]) if d[k] else ([] if k != "inputs" else {})
            except ValueError:
                d[k] = [] if k != "inputs" else {}
        return d

    def get(self, day: _dt.date, strategy: str = STRATEGY) -> Optional[dict]:
        from sqlalchemy import text
        from api.services import appdb
        if not appdb.exists("MorningBrief"):
            return None
        with self._eng().connect() as c:
            r = c.execute(text(self._SELECT + " WHERE Strategy = :s AND BriefDate = :d"), {"s": strategy, "d": day}).fetchone()
        return self._row(r) if r else None

    def put(self, row: dict, replace: bool = False) -> bool:
        from sqlalchemy import text
        from sqlalchemy.exc import IntegrityError
        from api.services import appdb
        appdb.ensure("MorningBrief")
        params = {"d": row["date"], "dec": row["decision"], "conf": float(row["confidence"]),
                  "mult": float(row["size_multiplier"]), "head": str(row.get("headline") or "")[:400],
                  "reasons": json.dumps(row.get("reasons") or []), "events": json.dumps(row.get("events_seen") or []),
                  "flags": json.dumps(row.get("flags_fired") or []),
                  "change": str(row.get("what_would_change_my_mind") or "")[:600], "src": str(row["source"])[:60],
                  "pv": str(row.get("prompt_version") or "")[:30], "inputs": json.dumps(row.get("inputs") or {}, default=str),
                  "notes": json.dumps(row.get("notes") or []), "s": row.get("strategy") or STRATEGY}
        insert = text("""
            INSERT INTO app.MorningBrief (BriefDate, Decision, Confidence, SizeMultiplier, Headline, ReasonsJson, EventsJson,
                FlagsJson, ChangeMind, Source, PromptVersion, InputsJson, NotesJson, Strategy)
            VALUES (:d, :dec, :conf, :mult, :head, :reasons, :events, :flags, :change, :src, :pv, :inputs, :notes, :s)""")
        try:
            with self._eng().begin() as c:
                if replace:
                    c.execute(text("DELETE FROM app.MorningBrief WHERE Strategy = :s AND BriefDate = :d"), {"s": params["s"], "d": params["d"]})
                c.execute(insert, params)
            return True
        except IntegrityError:
            return False

    def history(self, since: _dt.date, strategy: str = STRATEGY) -> list[dict]:
        from sqlalchemy import text
        from api.services import appdb
        if not appdb.exists("MorningBrief"):
            return []
        with self._eng().connect() as c:
            rows = c.execute(text(self._SELECT + " WHERE Strategy = :s AND BriefDate >= :d ORDER BY BriefDate DESC"),
                             {"s": strategy, "d": since}).fetchall()
        return [self._row(r) for r in rows]


def store_mode() -> str:
    m = os.environ.get("ALAN_TRADER_BRIEF", "db").strip().lower()
    return m if m in ("db", "memory", "off") else "db"


def scheduler_on() -> bool:
    return os.environ.get("ALAN_TRADER_BRIEF_SCHEDULER", "1").strip().lower() not in ("0", "off", "false", "no")


def network_on() -> bool:
    return os.environ.get("ALAN_TRADER_BRIEF_NETWORK", "1").strip().lower() not in ("0", "off", "false", "no")


def make_store():
    m = store_mode()
    return None if m == "off" else (MemoryBriefStore() if m == "memory" else DbBriefStore())


# ── the job ───────────────────────────────────────────────────────────────────

def to_api(row: Optional[dict], day: _dt.date) -> dict:
    """The contract's shape (GET /api/brief/today). ``row`` None = not yet run today."""
    if row is None:
        return {"date": day.isoformat(), "created_at": None, "decision": None, "confidence": None, "size_multiplier": None,
                "headline": "No brief yet today.", "reasons": [], "events_seen": [], "flags_fired": [],
                "what_would_change_my_mind": None, "source": None, "prompt_version": None, "notes": [], "inputs": None}
    created = row.get("created_at")
    if isinstance(created, _dt.datetime):
        created = (created.replace(tzinfo=UTC) if created.tzinfo is None else created).astimezone(NY).isoformat(timespec="seconds")
    return {"date": row["date"].isoformat() if isinstance(row["date"], _dt.date) else str(row["date"]),
            "created_at": created, "decision": row["decision"], "confidence": row["confidence"],
            "size_multiplier": row["size_multiplier"], "headline": row.get("headline") or "",
            "reasons": row.get("reasons") or [], "events_seen": row.get("events_seen") or [],
            "flags_fired": row.get("flags_fired") or [], "what_would_change_my_mind": row.get("what_would_change_my_mind") or "",
            "source": row["source"], "prompt_version": row.get("prompt_version"), "notes": row.get("notes") or [],
            "inputs": row.get("inputs") or {}}


class MorningBrief:
    def __init__(self, hub=None, arms=None, recorder=None, store=None, publish: Optional[Callable[[dict], None]] = None,
                 clock: Optional[Callable[[], pd.Timestamp]] = None, sources=None, post: Optional[Callable] = None,
                 strategy: str = STRATEGY):
        from api.services.brief_sources import Sources
        self.store = store if store is not None else make_store()
        self.publish = publish
        self.clock = clock or (lambda: pd.Timestamp.now(tz=NY))
        self.sources = sources or Sources(hub, arms, recorder, network=network_on())
        self.post = post
        self.strategy = strategy
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._last_attempt: dict[_dt.date, float] = {}
        self.last_error: Optional[str] = None

    # ── lifecycle ─────────────────────────────────────────────────────────────
    def start(self) -> None:
        if self.store is None:
            logger.info("morning brief off (ALAN_TRADER_BRIEF=off)")
            return
        if not scheduler_on():
            logger.info("morning brief scheduler off (ALAN_TRADER_BRIEF_SCHEDULER): on demand only")
            return
        self._thread = threading.Thread(target=self._run, name="morning-brief", daemon=True)
        self._thread.start()
        logger.info("morning brief scheduler on: %s ET on trading days, %s", RUN_AT.strftime("%H:%M"),
                    "llm:" + model_name() if api_key() else "rules (no ANTHROPIC_API_KEY)")

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                logger.exception("morning brief tick failed")
            self._stop.wait(TICK_S)

    def status(self) -> dict:
        return {"enabled": self.store is not None, "scheduler": self._thread is not None, "run_at": RUN_AT.strftime("%H:%M"),
                "decider": ("llm:" + model_name()) if api_key() else "rules", "prompt_version": PROMPT_VERSION,
                "last_error": self.last_error}

    # ── the schedule ──────────────────────────────────────────────────────────
    def due(self, now: pd.Timestamp) -> bool:
        from api.services.gex_recorder import trading_day
        day = now.date()
        if not trading_day(day) or not (RUN_AT <= now.time() < RUN_UNTIL):
            return False
        last = self._last_attempt.get(day)
        return last is None or (now.timestamp() - last) >= RETRY_S

    def tick(self, now: Optional[pd.Timestamp] = None) -> Optional[dict]:
        """Run today's brief when it is due and not yet written; None otherwise."""
        if self.store is None:
            return None
        now = now or self.clock()
        if not self.due(now):
            return None
        day = now.date()
        self._last_attempt[day] = float(now.timestamp())
        if self.store.get(day, self.strategy) is not None:
            return None
        try:
            return self.run(day=day, now=now)
        except Exception as exc:  # noqa: BLE001 — the next tick retries after RETRY_S
            self.last_error = f"{type(exc).__name__}: {exc}"[:200]
            logger.exception("morning brief for %s failed", day)
            return None

    # ── on demand ─────────────────────────────────────────────────────────────
    def today(self) -> dict:
        day = self.clock().date()
        row = self.store.get(day, self.strategy) if self.store is not None else None
        return to_api(row, day)

    def history(self, days: int = 60) -> list[dict]:
        if self.store is None:
            return []
        day = self.clock().date()
        return [to_api(r, day) for r in self.store.history(day - _dt.timedelta(days=int(days)), self.strategy)]

    def run(self, day: Optional[_dt.date] = None, now: Optional[pd.Timestamp] = None, force: bool = False) -> dict:
        """Write today's brief (once: a second call returns the row that stands, unless ``force``)."""
        if self.store is None:
            raise RuntimeError("the morning brief is off (ALAN_TRADER_BRIEF=off)")
        now = now or self.clock()
        day = day or now.date()
        with self._lock:
            existing = self.store.get(day, self.strategy)
            if existing is not None and not force:
                return to_api(existing, day)
            inputs = self.sources.gather(day, now.to_pydatetime() if hasattr(now, "to_pydatetime") else now)
            decision, source, notes, usage = decide(inputs, post=self.post)
            if existing is not None:
                notes.append(f"replaced the {existing['decision']} written at {existing.get('created_at')} (force)")
            from api.services.brief_sources import digest
            row = {"date": day, "created_at": _utcnow(), **decision, "source": source, "prompt_version": PROMPT_VERSION,
                   "inputs": digest(inputs), "notes": notes + ([f"usage: {usage}"] if usage else []), "strategy": self.strategy}
            if not self.store.put(row, replace=force):
                existing = self.store.get(day, self.strategy)          # lost a race to another process: theirs stands
                return to_api(existing, day)
            self.last_error = None
            out = to_api(self.store.get(day, self.strategy) or row, day)
        logger.info("morning brief %s: %s (%s, confidence %.2f) — %s", day, out["decision"], out["source"],
                    out["confidence"] or 0.0, out["headline"])
        if self.publish is not None:
            try:
                self.publish({"type": "brief", "brief": {k: v for k, v in out.items() if k != "inputs"}})
            except Exception:  # noqa: BLE001
                logger.debug("brief event publish failed", exc_info=True)
        return out

    # ── the shadow ledger ─────────────────────────────────────────────────────
    def scorecard(self, trades: Optional[list[dict]] = None) -> dict:
        from api.services.brief_scorecard import condor_trades, scorecard
        if self.store is None:
            return scorecard([], {})
        trades = condor_trades(self.strategy) if trades is None else trades
        since = min((t["date"] for t in trades), default=self.clock().date())
        briefs = {}
        for r in self.store.history(since, self.strategy):
            m = (r.get("inputs") or {}).get("market") or {}
            cal = (r.get("inputs") or {}).get("calendar") or {}
            ratio = m.get("vix_ratio")
            briefs[r["date"]] = {"size_multiplier": r["size_multiplier"], "macro_today": bool(cal.get("macro_today")),
                                 "vix_inverted": (float(ratio) > 1.0) if ratio is not None else False}
        out = scorecard(trades, briefs)
        out["strategy"] = self.strategy
        out["ledgers"] = {"a": "the paper condor as traded", "b": "A x the brief's size multiplier",
                          "c": "A, skipping scheduled macro days (F1)", "d": "A, skipping days with VIX > VIX3M"}
        return out
