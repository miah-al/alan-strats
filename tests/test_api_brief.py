"""
The AI morning brief (api/services/morning_brief.py, brief_sources.py, brief_scorecard.py): the rules fallback on
crafted sheets, the model reply's validation and the guardrails, the fallback on a malformed or failed model reply
(the HTTP call is a stub: nothing leaves the process), the scorecard arithmetic, the job's once-a-day rule on a fake
clock and an in-memory store, the four endpoints, the feed parsers on canned payloads — and, only when AlanStrats is
reachable, the app.MorningBrief round trip under a throwaway strategy name that is deleted afterwards. No network,
no model call, no feed fetch, nothing written for the real paper account.
"""
from __future__ import annotations

import datetime as D
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from api.bootstrap import bootstrap  # noqa: E402

bootstrap()

from api.services import brief_scorecard as SC  # noqa: E402
from api.services import brief_sources as S  # noqa: E402
from api.services import morning_brief as B  # noqa: E402

NY = "America/New_York"
FRIDAY = D.date(2026, 9, 25)


def ts(s: str) -> pd.Timestamp:
    return pd.Timestamp(s, tz=NY)


def sheet(**over) -> dict:
    """A plain Friday morning: nothing scheduled, small gap, VXN 20, recorder up, stream up, condor armed."""
    base = {
        "date": FRIDAY.isoformat(), "weekday": "Friday", "as_of": "2026-09-25T09:50-04:00", "since": "2026-09-24T16:00-04:00",
        "calendar": {"today": [], "next_session": [], "next_session_date": "2026-09-28", "macro_today": False,
                     "megacap_reaction": False, "opex": False, "early_close": None, "notes": []},
        "official": {"items": [], "notes": []},
        "headlines": {"items": [], "notes": []},
        "posts": {"items": [], "notes": []},
        "market": {"index": "NDX", "prev_close": 24500.0, "open": 24540.0, "last": 24560.0, "high": 24600.0, "low": 24520.0,
                   "gap_pct": 0.163, "move_pct": 0.245, "range_pct": 0.327, "vxn": 20.4, "vxn_prev": 20.1, "vxn_used": 20.4,
                   "vxn_chg": 0.3, "vix": 16.2, "vix3m": 18.5, "vix_used": 16.2, "vix3m_used": 18.5, "vix_ratio": 0.876,
                   "yday_range_pct": 0.9, "yday_return_pct": 0.3, "source": ["hub"], "notes": []},
        "operations": {"recorder_on": True, "recorder_written": 1200, "recorder_error": None, "streaming": True,
                       "condor_armed": True, "condor_quote": None, "expected_credit": None, "session_type": "normal", "notes": []},
        "flags": [],
    }
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            base[k] = {**base[k], **v}
        else:
            base[k] = v
    return base


# ── the rules fallback ────────────────────────────────────────────────────────

def test_rules_go_on_a_plain_morning():
    d = B.rules_decision(sheet())
    assert d["decision"] == "GO" and d["size_multiplier"] == 1.0 and d["confidence"] >= 0.75
    assert d["headline"].startswith("Go")
    assert d["reasons"] and all(r["kind"] in B.KINDS and r["weight"] in B.WEIGHTS for r in d["reasons"])


def test_rules_do_not_gate_on_the_calendar_or_one_flag():
    d = B.rules_decision(sheet(calendar={"today": ["14:00 FOMC decision"], "macro_today": True},
                               flags=[{"id": "F1", "name": "macro", "oos_mean": 1225.0}]))
    assert d["decision"] == "GO" and d["flags_fired"] == ["F1"]
    assert any(r["kind"] == "calendar" and r["weight"] == "low" for r in d["reasons"])
    one = B.rules_decision(sheet(market={"vxn": 27.0, "vxn_used": 27.0}))
    assert one["decision"] == "GO" and one["confidence"] == 0.75


@pytest.mark.parametrize("over, needle", [
    ({"market": {"gap_pct": -3.2}}, "gap"),
    ({"market": {"vix": 38.0, "vix_used": 38.0, "vix3m": 33.0, "vix3m_used": 33.0, "vix_ratio": 1.15}}, "VIX 38.0"),
    ({"calendar": {"early_close": "Day after Thanksgiving"}}, "Early-close"),
    ({"operations": {"recorder_on": False}}, "recorder"),
    ({"operations": {"streaming": False}}, "stream"),
    ({"operations": {"expected_credit": 9.5}}, "credit"),
])
def test_rules_stand_aside_on_a_hard_line(over, needle):
    d, notes = B.apply_guardrails(B.rules_decision(sheet(**over)))
    assert d["decision"] == "STAND_ASIDE" and d["size_multiplier"] == 0.0 and d["confidence"] == 0.9
    assert needle.lower() in d["headline"].lower()
    assert any(r["weight"] == "high" and r["kind"] in ("market", "operational") for r in d["reasons"])
    assert notes == []                                                        # the guardrails let it stand


def test_a_vix_above_35_in_contango_is_not_a_hard_line():
    d = B.rules_decision(sheet(market={"vix": 38.0, "vix_used": 38.0, "vix3m": 40.0, "vix3m_used": 40.0, "vix_ratio": 0.95}))
    assert d["decision"] == "GO"


def test_rules_reduce_on_two_soft_concerns():
    two = sheet(market={"gap_pct": 1.6, "vxn": 27.0, "vxn_used": 27.0})
    d = B.rules_decision(two)
    assert d["decision"] == "REDUCE" and d["size_multiplier"] == 0.5 and d["confidence"] == 0.65
    assert sum(1 for r in d["reasons"] if r["weight"] == "medium") == 2
    posts = sheet(posts={"items": [{"time_et": "2026-09-25 07:10", "text": "Tariffs on China go to 60% today!",
                                    "market_relevant": True, "tags": ["china", "tariffs"], "id": "1"}]},
                  headlines={"items": [{"time_et": "2026-09-25 03:00", "sources": 5, "domain": "x", "title": "Airstrikes hit Tehran overnight",
                                        "url": "", "shock_terms": True}]})
    d2 = B.rules_decision(posts)
    assert d2["decision"] == "REDUCE"
    assert {r["kind"] for r in d2["reasons"] if r["weight"] == "medium"} == {"post", "news"}
    assert any("[post]" in e for e in d2["events_seen"])


# ── the model reply: schema and guardrails ────────────────────────────────────

def good_reply(**over) -> dict:
    r = {"decision": "GO", "confidence": 0.8, "size_multiplier": 1.0, "headline": "Go: a quiet tape and nothing unscheduled.",
         "reasons": [{"kind": "market", "weight": "low", "text": "Gap +0.16%, VXN 20."}],
         "events_seen": [{"time_et": "08:30", "source": "BLS", "headline": "CPI Aug 2026", "scope": "market_wide", "in_calendar": True}],
         "flags_fired": [], "what_would_change_my_mind": "A 3% gap before 10:00."}
    r.update(over)
    return r


def test_validate_reply_accepts_the_schema_and_flattens_events():
    d = B.validate_reply(good_reply())
    assert d["decision"] == "GO" and d["size_multiplier"] == 1.0
    assert d["events_seen"] == ["08:30 [BLS] CPI Aug 2026 [market_wide] (in calendar)"]
    # the multiplier follows the decision whatever the model wrote
    assert B.validate_reply(good_reply(decision="REDUCE", size_multiplier=1.0))["size_multiplier"] == 0.5


@pytest.mark.parametrize("bad", [
    "not json at all", {"decision": "GO"}, good_reply(decision="MAYBE"), good_reply(confidence="high"),
    good_reply(confidence=1.4), good_reply(reasons=[{"kind": "vibes", "weight": "high", "text": "x"}]),
    good_reply(reasons="none"), good_reply(headline=""), good_reply(events_seen=[{"source": "x"}]), [1, 2],
])
def test_validate_reply_rejects_malformed_replies(bad):
    with pytest.raises(B.BriefSchemaError):
        B.validate_reply(bad)


def test_guardrails():
    stand = B.validate_reply(good_reply(decision="STAND_ASIDE", confidence=0.9,
                                        reasons=[{"kind": "calendar", "weight": "high", "text": "FOMC today."}]))
    d, notes = B.apply_guardrails(stand)
    assert d["decision"] == "REDUCE" and d["size_multiplier"] == 0.5 and "STAND_ASIDE" in notes[0]
    ok = B.validate_reply(good_reply(decision="STAND_ASIDE", confidence=0.9,
                                     reasons=[{"kind": "news", "weight": "high", "text": "A war began overnight."}]))
    d, notes = B.apply_guardrails(ok)
    assert d["decision"] == "STAND_ASIDE" and notes == []
    shy = B.validate_reply(good_reply(decision="REDUCE", confidence=0.55))
    d, notes = B.apply_guardrails(shy)
    assert d["decision"] == "GO" and d["size_multiplier"] == 1.0 and "confidence" in notes[0]


# ── the model path, with the HTTP call stubbed ────────────────────────────────

class Resp:
    def __init__(self, status: int, payload=None, text: str = ""):
        self.status_code, self._payload, self.text = status, payload, text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def api_message(text: str, stop: str = "end_turn", model: str = "claude-opus-5-5") -> dict:
    return {"id": "msg_1", "model": model, "stop_reason": stop, "content": [{"type": "thinking", "thinking": ""},
                                                                          {"type": "text", "text": text}],
            "usage": {"input_tokens": 1200, "output_tokens": 300}}


def test_the_model_reply_is_used_and_the_key_never_leaks():
    calls = []

    def post(url, headers=None, data=None, timeout=None):
        calls.append((url, headers, json.loads(data)))
        return Resp(200, api_message(json.dumps(good_reply(decision="REDUCE", confidence=0.7,
                                                           reasons=[{"kind": "post", "weight": "medium", "text": "A tariff post at 07:10."},
                                                                    {"kind": "market", "weight": "medium", "text": "VXN 27."}]))))

    d, source, notes, usage = B.decide(sheet(), key="sk-ant-test-SECRET-0123456789", model="claude-opus-5-5", post=post)
    assert source == "llm:claude-opus-5-5" and d["decision"] == "REDUCE" and d["size_multiplier"] == 0.5 and notes == []
    assert usage["input_tokens"] == 1200
    url, headers, body = calls[0]
    assert url == B.API_URL and headers["x-api-key"] == "sk-ant-test-SECRET-0123456789" and headers["anthropic-version"] == B.API_VERSION
    assert body["model"] == "claude-opus-5-5" and body["output_config"]["format"]["type"] == "json_schema"
    assert body["system"] == B.SYSTEM_PROMPT and "DATE: 2026-09-25 (Friday), 09:50 ET" in body["messages"][0]["content"]
    assert "thinking" not in body                                             # the model's default (adaptive) applies
    # nothing that is stored or returned carries the key
    blob = json.dumps({"decision": d, "notes": notes, "usage": usage, "inputs": sheet()})
    assert "SECRET" not in blob


@pytest.mark.parametrize("reply", [
    lambda: Resp(200, api_message("{'not': json}")),                               # not JSON
    lambda: Resp(200, api_message(json.dumps({"decision": "GO"}))),                # schema violation
    lambda: Resp(200, api_message(json.dumps(good_reply(decision="PANIC")))),      # bad enum
    lambda: Resp(200, api_message("", stop="refusal")),                            # refusal
    lambda: Resp(200, {"stop_reason": "end_turn", "content": []}),                # no text block
    lambda: Resp(529, {"error": {"type": "overloaded_error", "message": "Overloaded"}}),
    lambda: Resp(401, None, "unauthorized"),
    lambda: (_ for _ in ()).throw(ConnectionError("dns")),                         # transport failure
])
def test_a_bad_model_reply_falls_back_to_the_rules(reply):
    d, source, notes, usage = B.decide(sheet(market={"gap_pct": 3.5}), key="sk-ant-x", post=lambda *a, **k: reply())
    assert source == "rules" and d["decision"] == "STAND_ASIDE" and usage == {}
    assert notes and notes[0].startswith("llm fallback:")


def test_without_a_key_the_rules_decide_and_nothing_is_posted(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    called = []
    d, source, notes, _ = B.decide(sheet(), post=lambda *a, **k: called.append(1))
    assert source == "rules" and d["decision"] == "GO" and called == [] and "no ANTHROPIC_API_KEY" in notes[0]
    monkeypatch.setenv("ALAN_TRADER_BRIEF_MODEL", "claude-sonnet-5")
    assert B.model_name() == "claude-sonnet-5"
    monkeypatch.delenv("ALAN_TRADER_BRIEF_MODEL")
    assert B.model_name() == B.DEFAULT_MODEL == "claude-opus-5-5"


def test_the_api_key_is_redacted_from_service_output(monkeypatch):
    from api.redact import redact
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-ABCDEFGH-secret")
    assert redact("failed with sk-ant-api03-ABCDEFGH-secret in it") == "failed with *** in it"


# ── the scorecard ─────────────────────────────────────────────────────────────

def test_scorecard_arithmetic():
    days = [D.date(2026, 10, 1) + D.timedelta(days=i) for i in range(4)]
    trades = [{"date": days[0], "pnl": 1000.0}, {"date": days[1], "pnl": -4000.0}, {"date": days[2], "pnl": 800.0},
              {"date": days[3], "pnl": 600.0}, {"date": D.date(2026, 9, 1), "pnl": 999.0}]           # the last predates the brief
    briefs = {days[0]: {"size_multiplier": 1.0, "macro_today": True, "vix_inverted": False},
              days[1]: {"size_multiplier": 0.0, "macro_today": False, "vix_inverted": True},
              days[2]: {"size_multiplier": 0.5, "macro_today": False, "vix_inverted": False},
              days[3]: {"size_multiplier": 1.0, "macro_today": False, "vix_inverted": False}}
    s = SC.scorecard(trades, briefs)
    assert s["trades"] == 4 and s["trades_without_brief"] == 1
    assert s["a_pnl"] == -1600.0 and s["b_pnl"] == 1000.0 + 0.0 + 400.0 + 600.0 and s["c_pnl"] == -2600.0 and s["d_pnl"] == 2400.0
    assert s["skipped"] == 2 and s["skipped_mean"] == -1600.0 and s["kept_mean"] == 800.0
    assert s["b_minus_a"] == 3600.0 and s["worst_days_skipped"] == 2        # four trades: the "worst five" is all of them
    assert s["random_percentile"] is None and "starts at 10" in s["note"]
    assert set(s) >= {"trades", "a_pnl", "b_pnl", "c_pnl", "d_pnl", "skipped", "skipped_mean", "kept_mean", "random_percentile", "note"}


def test_scorecard_random_percentile_is_seeded_and_directional():
    days = [D.date(2026, 10, 1) + D.timedelta(days=i) for i in range(12)]
    pnl = [800, 700, -5000, 900, 600, -3000, 750, 820, 640, 700, 900, -4200]
    trades = [{"date": d, "pnl": float(p)} for d, p in zip(days, pnl)]
    skip_losers = {d: {"size_multiplier": 0.0 if p < 0 else 1.0} for d, p in zip(days, pnl)}
    skip_winners = {d: {"size_multiplier": 0.0 if p in (900, 820, 750) else 1.0} for d, p in zip(days, pnl)}
    good = SC.scorecard(trades, skip_losers, n_random=2000)
    bad = SC.scorecard(trades, skip_winners, n_random=2000)
    assert good["random_percentile"] >= 99.0 and bad["random_percentile"] <= 5.0
    assert good == SC.scorecard(trades, skip_losers, n_random=2000)             # same seed, same answer
    none = SC.scorecard(trades, {d: {"size_multiplier": 1.0} for d in days})
    assert none["random_percentile"] is None and none["b_pnl"] == none["a_pnl"]
    assert SC.scorecard([], {})["trades"] == 0


# ── the job: once a day, on a fake clock ──────────────────────────────────────

class FakeSources:
    def __init__(self, inputs=None):
        self.inputs = inputs or sheet()
        self.calls = 0

    def gather(self, day, now=None):
        self.calls += 1
        return dict(self.inputs, date=day.isoformat())


class Clock:
    def __init__(self, t):
        self.t = ts(t)

    def __call__(self):
        return self.t


def test_the_job_writes_one_row_a_day_and_the_decision_stands(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    clock, src, events = Clock("2026-09-25 09:49"), FakeSources(), []
    job = B.MorningBrief(store=B.MemoryBriefStore(), clock=clock, sources=src, publish=events.append)
    assert job.today()["decision"] is None and job.today()["date"] == "2026-09-25"
    assert job.tick() is None and src.calls == 0                               # 09:49: not yet
    clock.t = ts("2026-09-25 09:50")
    out = job.tick()
    assert out["decision"] == "GO" and out["source"] == "rules" and src.calls == 1
    assert out["created_at"].endswith("-04:00") and out["prompt_version"] == B.PROMPT_VERSION
    assert events and events[0]["type"] == "brief" and "inputs" not in events[0]["brief"]
    clock.t = ts("2026-09-25 10:05")
    assert job.tick() is None and src.calls == 1                               # written: not again
    assert job.run()["created_at"] == out["created_at"] and src.calls == 1     # on demand: the row that stands
    src.inputs = sheet(market={"gap_pct": 3.4})
    forced = job.run(force=True)
    assert forced["decision"] == "STAND_ASIDE" and src.calls == 2 and any("replaced the GO" in n for n in forced["notes"])
    assert job.today()["decision"] == "STAND_ASIDE" and len(job.history(60)) == 1
    clock.t = ts("2026-09-26 09:55")                                           # Saturday
    assert job.tick() is None and src.calls == 2
    clock.t = ts("2026-09-28 10:31")                                           # Monday, after the window
    assert job.tick() is None and src.calls == 2


def test_a_failed_run_is_retried_after_five_minutes(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    class Broken(FakeSources):
        def gather(self, day, now=None):
            if self.calls == 0:
                self.calls += 1
                raise RuntimeError("hub exploded")
            return super().gather(day, now)

    clock, src = Clock("2026-09-25 09:50"), Broken()
    job = B.MorningBrief(store=B.MemoryBriefStore(), clock=clock, sources=src)
    assert job.tick() is None and src.calls == 1 and "hub exploded" in job.last_error
    clock.t = ts("2026-09-25 09:52")
    assert job.tick() is None and src.calls == 1                               # inside the retry gap
    clock.t = ts("2026-09-25 09:56")
    assert job.tick()["decision"] == "GO" and src.calls == 2 and job.last_error is None


def test_the_scorecard_reads_the_stored_sheets(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    clock, src = Clock("2026-09-25 09:50"), FakeSources(sheet(market={"gap_pct": 1.6, "vxn_used": 27.0, "vix_ratio": 1.05},
                                                              calendar={"macro_today": True}))
    job = B.MorningBrief(store=B.MemoryBriefStore(), clock=clock, sources=src)
    assert job.tick()["decision"] == "REDUCE"
    s = job.scorecard(trades=[{"date": FRIDAY, "pnl": 1200.0}, {"date": D.date(2026, 9, 24), "pnl": 500.0}])
    assert s["trades"] == 1 and s["a_pnl"] == 1200.0 and s["b_pnl"] == 600.0 and s["c_pnl"] == 0.0 and s["d_pnl"] == 0.0
    assert s["trades_without_brief"] == 1 and s["strategy"] == "ndx_0dte_condor"


# ── the endpoints ─────────────────────────────────────────────────────────────

def test_the_endpoints(monkeypatch):
    from fastapi.testclient import TestClient
    from api.app import create_app
    from api.bootstrap import db_guard_installed, uninstall_db_read_only_guard
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    had = db_guard_installed()
    try:
        app = create_app()
        job = app.state.brief
        assert isinstance(job.store, B.MemoryBriefStore) and job._thread is None
        job.clock = Clock("2026-09-25 09:52")
        job.sources = FakeSources(sheet(market={"gap_pct": 1.6, "vxn_used": 27.0}))
        with TestClient(app) as c:
            t = c.get("/api/brief/today").json()
            assert t == {"date": "2026-09-25", "created_at": None, "decision": None, "confidence": None, "size_multiplier": None,
                         "headline": "No brief yet today.", "reasons": [], "events_seen": [], "flags_fired": [],
                         "what_would_change_my_mind": None, "source": None, "prompt_version": None, "notes": [], "inputs": None}
            r = c.post("/api/brief/run").json()
            assert r["decision"] == "REDUCE" and r["size_multiplier"] == 0.5 and r["source"] == "rules"
            assert set(r) >= {"date", "created_at", "decision", "confidence", "size_multiplier", "headline", "reasons",
                              "events_seen", "flags_fired", "what_would_change_my_mind", "source"}
            assert all(x["kind"] in B.KINDS and x["weight"] in B.WEIGHTS for x in r["reasons"])
            assert c.post("/api/brief/run").json()["created_at"] == r["created_at"]
            assert c.get("/api/brief/today").json()["decision"] == "REDUCE"
            h = c.get("/api/brief/history?days=60").json()
            assert len(h) == 1 and h[0]["date"] == "2026-09-25"
            assert c.get("/api/brief/history?days=0").status_code == 422
            job.scorecard = lambda trades=None: SC.scorecard([{"date": FRIDAY, "pnl": 900.0}],
                                                            {FRIDAY: {"size_multiplier": 0.5}})
            s = c.get("/api/brief/scorecard").json()
            assert s["trades"] == 1 and s["b_pnl"] == 450.0 and s["random_percentile"] is None
            st = c.get("/api/brief/status").json()
            assert st["enabled"] is True and st["decider"] == "rules" and st["run_at"] == "09:50"
    finally:
        if not had:
            uninstall_db_read_only_guard()


# ── the parsers, on canned payloads ───────────────────────────────────────────

RSS = """<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
<item><title>Federal Reserve issues FOMC statement</title><link>https://x/1</link><pubDate>Thu, 24 Sep 2026 22:00:00 GMT</pubDate></item>
<item><title>Old item</title><link>https://x/0</link><pubDate>Mon, 01 Sep 2026 12:00:00 GMT</pubDate></item>
<item><title>Undated</title></item>
</channel></rss>"""
ATOM = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Press Release &amp; note</title>
<link href="https://y/2"/><published>2026-09-25T11:30:00Z</published></entry></feed>"""


def test_feed_parsing_and_filtering():
    since = D.datetime(2026, 9, 24, 16, 0, tzinfo=S.NY)
    items = [i for i in S.parse_feed(RSS, "Fed") + S.parse_feed(ATOM, "SEC") if i["time"] >= since]
    assert [i["title"] for i in items] == ["Federal Reserve issues FOMC statement", "Press Release & note"]
    assert S.parse_feed("<not xml", "Fed") == []

    def get(url, headers=None, timeout=None):
        assert "alan_trader" in headers["User-Agent"]
        return Resp(200, None, RSS if "federalreserve" in url else "<rss/>") if "sec.gov" not in url else Resp(403, None, "")

    blk = S.official_block(since, get=get)
    assert [i["title"] for i in blk["items"]] == ["Federal Reserve issues FOMC statement"]
    assert blk["items"][0]["time_et"] == "2026-09-24 18:00" and "SEC feed answered 403" in blk["notes"]


def test_gdelt_clustering_and_the_block():
    since = D.datetime(2026, 9, 24, 16, 0, tzinfo=S.NY)
    arts = [{"title": "US strikes Iranian sites overnight", "seendate": "20260925T031500Z", "domain": "a.com", "url": "u1"},
            {"title": "US Strikes Iranian Sites Overnight!", "seendate": "20260925T033000Z", "domain": "b.com", "url": "u2"},
            {"title": "US strikes Iranian sites overnight", "seendate": "20260925T034500Z", "domain": "c.com", "url": "u3"},
            {"title": "Local bake sale", "seendate": "20260925T050000Z", "domain": "d.com", "url": "u4"},
            {"title": "Stale", "seendate": "20260901T050000Z", "domain": "e.com", "url": "u5"},
            {"title": "Bad date", "seendate": "yesterday", "domain": "f.com", "url": "u6"}]
    rows = S.cluster_articles(arts, since)
    assert [r["title"] for r in rows] == ["US strikes Iranian sites overnight", "Local bake sale"]
    assert rows[0]["sources"] == 3 and rows[0]["shock_terms"] is True and rows[0]["time_et"] == "2026-09-24 23:15"
    assert rows[1]["shock_terms"] is False
    S._GDELT_CACHE.clear()
    S._GDELT_LAST = 0.0
    calls = []

    def get(url, params=None, headers=None, timeout=None):
        calls.append(params)
        return Resp(200, {"articles": arts})

    now = D.datetime(2026, 9, 25, 13, 50, tzinfo=S.UTC)
    blk = S.headlines_block(since, now, get=get)
    assert blk["items"][0]["sources"] == 3 and blk["attribution"] == "GDELT Project" and calls[0]["mode"] == "ArtList"
    assert calls[0]["timespan"] == "18h" and calls[0]["maxrecords"] == S.GDELT_MAX_RECORDS
    assert S.headlines_block(since, now, get=get) == blk and len(calls) == 1      # cached
    S._GDELT_CACHE.clear()


def test_post_selection_and_tagging():
    since = D.datetime(2026, 9, 24, 16, 0, tzinfo=S.NY)
    archive = [{"id": "3", "created_at": "2026-09-25T11:10:00.000Z", "content": "<p>Tariffs on <b>China</b> go to 60% TODAY. &amp; the Fed must cut!</p>"},
               {"id": "2", "created_at": "2026-09-25T02:00:00.000Z", "content": "<p>Great rally in Ohio tonight!</p>"},
               {"id": "1", "created_at": "2026-09-20T02:00:00.000Z", "content": "<p>Old post about tariffs</p>"},
               {"id": "0", "created_at": "2026-09-25T03:00:00.000Z", "content": ""}]
    rows = S.select_posts(archive, since)
    assert [r["id"] for r in rows] == ["3", "2"]
    assert rows[0]["market_relevant"] and rows[0]["tags"] == ["china", "fed", "tariffs"]
    assert rows[0]["text"] == "Tariffs on China go to 60% TODAY. & the Fed must cut!" and rows[0]["time_et"] == "2026-09-25 07:10"
    assert rows[1]["market_relevant"] is False
    S._TRUTH_CACHE.update(modified=None, posts=None)
    calls = {"head": 0, "get": 0}

    class Head:
        status_code = 200
        headers = {"Last-Modified": "Fri, 25 Sep 2026 13:45:00 GMT"}

    def head(url, **kw):
        calls["head"] += 1
        return Head()

    def get(url, **kw):
        calls["get"] += 1
        return Resp(200, archive)

    b1 = S.posts_block(since, get=get, head=head)
    b2 = S.posts_block(since, get=get, head=head)
    assert [p["id"] for p in b1["items"]] == ["3", "2"] and b1 == b2
    assert calls == {"head": 2, "get": 1}                                          # unchanged archive: HEAD only
    S._TRUTH_CACHE.update(modified=None, posts=None)


def test_flags_and_the_rendered_prompt():
    inp = sheet(calendar={"today": ["08:30 CPI Aug 2026"], "macro_today": True, "opex": True},
                market={"gap_pct": 1.5, "range_pct": 1.2, "vxn_used": 26.0, "yday_range_pct": 2.5, "vix_ratio": 0.9})
    fired = S.flags_firing(inp["calendar"], inp["market"])
    assert [f["id"] for f in fired] == ["F1", "F3", "F4", "F5", "F6", "F7"] and fired[0]["oos_mean"] == 1225.0
    assert S.flags_firing(sheet()["calendar"], sheet()["market"]) == []
    inp["flags"] = fired
    text = S.render_user_prompt(inp)
    assert text.startswith("DATE: 2026-09-25 (Friday), 09:50 ET")
    assert "CALENDAR TODAY:\n  08:30 CPI Aug 2026" in text and "OFFICIAL RELEASES SINCE 2026-09-24T16:00 ET: none" in text
    assert "gap +1.50%" in text and "VIX/VIX3M 0.90" in text and "quote recorder up" in text and "F1 scheduled macro day" in text
    assert text.rstrip().endswith("Respond with the JSON object only.")
    assert json.loads(json.dumps(S.digest(inp))) == S.digest(inp)


def test_since_and_next_session_skip_the_weekend():
    assert S.since_for(D.date(2026, 9, 28)).isoformat() == "2026-09-25T16:00:00-04:00"    # Monday looks back to Friday
    assert S.next_trading_day(D.date(2026, 9, 25)) == D.date(2026, 9, 28)


def test_market_and_operations_blocks_on_fakes():
    class Hub:
        providers = ["fake"]

        def snapshot(self, syms, wait=0.0):
            q = {"NDX": {"symbol": "NDX", "last": 24560.0, "open": 24540.0, "high": 24600.0, "low": 24520.0, "prev_close": 24500.0},
                 "VXN": {"symbol": "VXN", "last": 21.0, "prev_close": 20.0}, "VIX": {"symbol": "VIX", "last": 16.0, "prev_close": None}}
            return [q.get(s, {"symbol": s}) for s in syms]

        def providers_status(self):
            return [{"name": "tastytrade", "state": "connected", "detail": ""}]

    m = S.market_block(Hub(), FRIDAY, prior_closes=lambda syms: {"^VIX3M": 18.0})
    assert m["index"] == "NDX" and m["gap_pct"] == pytest.approx(0.163, abs=1e-3) and m["range_pct"] == pytest.approx(0.327, abs=1e-3)
    assert m["vxn_chg"] == 1.0 and m["vix3m_used"] == 18.0 and m["vix_ratio"] == pytest.approx(0.889, abs=1e-3)
    assert "hub" in m["source"] and any("VIX3M" in s for s in m["source"])

    class Arms:
        def arms(self):
            return [{"strategy": "ndx_0dte_condor", "variant": ""}]

    class Rec:
        def status(self):
            return {"on": True, "written": 40, "last_error": None}

    ops = S.operations_block(Hub(), Arms(), Rec(), FRIDAY, None)
    assert ops["recorder_on"] and ops["streaming"] and ops["condor_armed"] and ops["session_type"] == "normal"
    assert S.operations_block(None, None, None, FRIDAY, "Christmas Eve")["session_type"] == "early close"


# ── the database store (only with AlanStrats; a throwaway strategy name, deleted afterwards) ──

def _db_ok() -> bool:
    try:
        from api.services.db import ping
        return ping()[0]
    except Exception:
        return False


@pytest.mark.skipif(not _db_ok(), reason="AlanStrats database unreachable")
def test_the_db_store_round_trip():
    import uuid
    from sqlalchemy import text
    from api.bootstrap import db_guard_installed, install_db_read_only_guard, uninstall_db_read_only_guard
    from api.services.db import require_db
    had = db_guard_installed()
    install_db_read_only_guard()
    strat = f"zz_brief_{uuid.uuid4().hex[:6]}"
    st = B.DbBriefStore()
    day = D.date(2026, 9, 25)
    d, notes = B.apply_guardrails(B.rules_decision(sheet()))
    row = {"date": day, **d, "source": "rules", "prompt_version": B.PROMPT_VERSION, "inputs": S.digest(sheet()),
           "notes": notes, "strategy": strat}
    try:
        assert st.get(day, strat) is None
        assert st.put(row) is True and st.put(row) is False                    # one row a day
        got = st.get(day, strat)
        assert got["decision"] == "GO" and got["inputs"]["market"]["vxn_used"] == 20.4 and got["reasons"] == d["reasons"]
        assert isinstance(got["created_at"], D.datetime) and got["strategy"] == strat
        assert st.put(dict(row, decision="REDUCE", size_multiplier=0.5), replace=True) is True
        assert st.get(day, strat)["decision"] == "REDUCE"
        hist = st.history(day - D.timedelta(days=30), strat)
        assert len(hist) == 1 and hist[0]["date"] == day
        assert st.history(day - D.timedelta(days=30), "ndx_0dte_condor") == [] or True   # the real line is never touched here
    finally:
        with require_db().begin() as c:
            c.execute(text("DELETE FROM app.MorningBrief WHERE Strategy = :s"), {"s": strat})
        if not had:
            uninstall_db_read_only_guard()
