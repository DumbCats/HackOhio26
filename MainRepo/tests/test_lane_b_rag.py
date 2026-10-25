"""Lane B RAG: retrieval quality, safety routing, privacy, no-peeking line history."""
from __future__ import annotations

import json
import re

import pytest

from app.models.common import ARCOS_ZIP, DB_PATH, UnknownHome
from app.rag import retriever
from app.rag.tools import (
    MAX_QUERY_CHARS, RAG_TOOL_NAMES, TOOLS, classify_query, run_tool, search_explanations,
)

HAVE_DATA = DB_PATH.exists() and ARCOS_ZIP.exists()
needs_data = pytest.mark.skipif(not HAVE_DATA, reason="DB or raw ARCOS data missing")

# question -> passage id that must be in the top 3
RETRIEVAL_CASES = [
    ("why does it say high risk", "risk_band_meaning"),
    ("how do you know when my power is back", "how_we_know_back"),
    ("why did my estimate change", "estimate_changes"),
    ("is this the real outage map", "simulated_feed_replay"),
    ("do you store my medical info", "declared_needs"),
    ("why can't you predict my area", "fallback_cant_predict"),
    ("will my neighbor get power first", "step_restoration"),
    ("whats the eta", "restoration_range_how"),
    ("how sure are you about this", "confidence_levels"),
    ("what is the chance I lose power", "risk_band_meaning"),
    ("why not just give me a percent", "risk_band_not_percent"),
    ("what does Our estimate mean", "label_our_estimate"),
    ("what does utility confirmed mean", "label_utility_confirmed"),
    ("where does your data come from", "data_sources"),
    ("what is real and what is fake here", "real_vs_simulated"),
    ("what does switching mean", "switching_assumption"),
    ("how many crews are working", "crews_pool"),
    ("what storms are in the data", "storms_in_data"),
    ("how do you know my power is out", "how_we_know_out"),
    ("what would make this better", "what_would_improve"),
    ("is my address shared with anyone", "privacy_never_shown"),
    ("why give a range and not an exact time", "restoration_why_range"),
    ("what happens if roads are blocked", "roads_blocked"),
    ("do you log my chats", "audit_log"),
    ("why is there no official time from the utility", "utility_confirmed_missing"),
]

SAFETY_QUERIES = [
    "how do I keep my insulin cold",
    "is it safe to run a generator in the garage",
    "a power line is down in my yard",
    "my oxygen concentrator needs power",
    "is the food in my fridge still ok",
    "what should I do to prepare",
]
EMERGENCY_QUERIES = [
    "there are sparks and smoke near the pole",
    "my dad can't breathe",
    "this is an emergency",
]
GIBBERISH = ["asdfgh qwerty zxcv", "the", "pizza recipe please", "????", "lorem ipsum dolor"]

ID_RES = [
    re.compile(r"p_[0-9a-f]{16}"),          # home ids
    re.compile(r"(?<!\d)\d{7}(?!\d)"),       # 7-digit circuit ids
    re.compile(r"CIR\s?\d", re.I),           # ARCOS circuit names
    re.compile(r"-?\d{2,3}\.\d{4,}"),        # coordinates
]
FORBIDDEN_KEYS = {"lat", "lon", "latitude", "longitude", "circuit_id", "home_id", "premise_key",
                  "device_key", "is_critical_tier"}


def assert_private(obj):
    s = json.dumps(obj)
    assert "%" not in s, s
    for rx in ID_RES:
        assert not rx.search(s), (rx.pattern, s)

    def walk(o):
        if isinstance(o, dict):
            assert not (FORBIDDEN_KEYS & set(o)), set(o)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(obj)


# --- corpus ------------------------------------------------------------------------

def test_corpus_shape():
    ps = retriever.load_corpus()
    assert 30 <= len(ps) <= 60
    ids = [p["id"] for p in ps]
    assert len(ids) == len(set(ids))
    for p in ps:
        assert p["title"] and p["text"] and p["tags"] and p["basis"]
    assert_private(list(ps))


def test_corpus_has_no_safety_or_medical_instructions():
    bad = re.compile(r"\b(call 911|generator|carbon monoxide|candle|stay away|keep (it|the) "
                     r"(cold|in)|pharmacist|downed)\b", re.I)
    for p in retriever.load_corpus():
        assert not bad.search(p["text"]), p["id"]


# --- retrieval ---------------------------------------------------------------------

@pytest.mark.parametrize("q,expected", RETRIEVAL_CASES)
def test_retrieval_top3(q, expected):
    out = search_explanations(q)
    ids = [r["id"] for r in out["results"]]
    assert expected in ids, (q, ids)
    assert out["source"] == "approved_text"
    assert "use_tool" not in out


@pytest.mark.parametrize("q", SAFETY_QUERIES)
def test_safety_routes_to_prep(q):
    out = search_explanations(q)
    assert out["use_tool"] == "get_prep"
    assert out["results"] == []
    assert not out.get("emergency")


@pytest.mark.parametrize("q", EMERGENCY_QUERIES)
def test_emergency_routes_to_911_text(q):
    out = search_explanations(q)
    assert out["use_tool"] == "get_prep" and out["emergency"] is True
    assert "911" in out["note"]


def test_privacy_question_about_medical_info_is_not_medical():
    assert classify_query("do you store my medical info") == "explain"


@pytest.mark.parametrize("q", GIBBERISH)
def test_gibberish_empty(q):
    assert search_explanations(q)["results"] == []


def test_deterministic():
    for q, _ in RETRIEVAL_CASES:
        assert search_explanations(q) == search_explanations(q)
    retriever._index.cache_clear()
    a = [search_explanations(q) for q, _ in RETRIEVAL_CASES]
    retriever._index.cache_clear()
    b = [search_explanations(q) for q, _ in RETRIEVAL_CASES]
    assert a == b


def test_search_outputs_private():
    for q in [c[0] for c in RETRIEVAL_CASES] + SAFETY_QUERIES + EMERGENCY_QUERIES + GIBBERISH:
        assert_private(search_explanations(q))


# --- tool layer --------------------------------------------------------------------

def test_tool_schemas():
    names = [t["name"] for t in TOOLS]
    assert names == ["search_explanations", "get_line_history"]
    assert RAG_TOOL_NAMES == set(names)
    for t in TOOLS:
        assert t["description"] and t["input_schema"]["type"] == "object"
        assert "home_id" not in t["input_schema"]["properties"]
        assert "t" not in t["input_schema"]["properties"]
    assert TOOLS[0]["input_schema"]["required"] == ["query"]


@pytest.mark.parametrize("name,inp", [
    ("search_explanations", {"query": "x" * (MAX_QUERY_CHARS + 1)}),
    ("search_explanations", {"query": ""}),
    ("search_explanations", {"query": 42}),
    ("search_explanations", {}),
    ("search_explanations", None),
    ("search_explanations", "not a dict"),
    ("no_such_tool", {}),
])
def test_run_tool_validates(name, inp):
    out = run_tool(name, inp, {"home_id": "p_0000000000000000", "t": 0})
    assert "error" in out


def test_run_tool_search_ok():
    out = run_tool("search_explanations", {"query": "how sure are you"}, {})
    assert out["results"][0]["id"] == "confidence_levels"


def test_run_tool_history_bad_ctx():
    assert run_tool("get_line_history", {}, {"home_id": "p_0000000000000000"}) == {"error": "unknown home"}
    assert run_tool("get_line_history", {}, {"home_id": "not-an-id"}) == {"error": "unknown home"}
    assert run_tool("get_line_history", {}, {}) == {"error": "unknown home"}
    assert "error" in run_tool("get_line_history", {}, None)


# --- repair-time stats (pure function, no data needed) --------------------------------

def _numbers(s: str) -> set[str]:
    return set(re.findall(r"\d+(?:\.\d+)?", s))


def test_repair_stats_thresholds_and_buckets():
    from app.rag.history import _repair_stats
    assert _repair_stats([0, 1, 2, 40]) is None                      # < 5: not enough history
    five = _repair_stats([0, 0, 1, 2, 75])                           # 5-9: median + buckets, no range
    assert "range_days" not in five and "75" not in five["text"]
    assert five["fixed_by_day"] == {"same_day": 2, "within_1_day": 3, "within_2_days": 4,
                                    "3_or_more_days": 1}
    assert "2 of 5 were fixed the same day" in five["text"]
    assert "4 of 5 within 2 days" in five["text"] and "1 of 5 took 3 or more days" in five["text"]
    days = [0, 0, 0, 1, 1, 1, 1, 2, 3, 5, 9, 200]                    # >= 10: P10-P90 range
    big = _repair_stats(days)
    assert big["range_days"] == {"low": 0, "high": 9}                 # P90, not the max of 200
    assert "200" not in big["text"]
    assert "%" not in big["text"]


def test_repair_stats_numbers_are_literal():
    """N12: every number in the text appears as a value in the structured output."""
    from app.rag.history import _repair_stats
    for days in ([0, 0, 1, 2, 7], [0, 1, 1, 1, 2, 2, 3, 4, 6, 8, 10, 30]):
        rep = _repair_stats(days)
        values = {str(v) for v in json.dumps({k: v for k, v in rep.items() if k != "text"})
                  .replace("{", " ").replace("}", " ").replace(",", " ").replace(":", " ").split()}
        allowed = values | {"1", "2", "3", "8", "10"}   # wording: "within 1 day", "8 in 10", ...
        assert _numbers(rep["text"]) <= allowed, (_numbers(rep["text"]) - allowed)


# --- line history (needs the DB + raw ARCOS) ------------------------------------------

@pytest.fixture(scope="module")
def homes():
    if not HAVE_DATA:
        pytest.skip("DB or raw ARCOS data missing")
    from collections import Counter
    from app.models.common import damage_history, get_conn
    rows = damage_history()
    feb = Counter(r["circuit_id"] for r in rows if r["storm"] == "feb2025")
    pre = Counter(r["circuit_id"] for r in rows if r["report_date"] < "2025-02-12")
    conn = get_conn()
    all_circ = [r[0] for r in conn.execute("SELECT DISTINCT circuit_id FROM premises")]
    busy = max((c for c in all_circ if pre[c] >= 3), key=lambda c: (feb[c], c))
    quiet = sorted(c for c in all_circ if pre[c] == 0)[0]

    def home_on(c):
        return conn.execute("SELECT premise_key FROM premises WHERE circuit_id=? "
                            "ORDER BY premise_key LIMIT 1", (c,)).fetchone()[0]
    return {"busy": home_on(busy), "busy_circ": busy, "quiet": home_on(quiet),
            "pre": pre[busy], "rows": rows}


@needs_data
def test_history_no_peeking_before_storm(homes):
    from app.rag.history import get_line_history
    out = get_line_history(homes["busy"], t=-18)
    s = json.dumps(out)
    assert "February 2025" not in s and "this storm" not in s
    assert out["your_line"]["past_damage_total"] == homes["pre"]
    assert out["source"] == "model_estimate"
    assert out["assumptions"] and out["missing_data"]
    assert_private(out)


@needs_data
def test_history_includes_storm_later(homes):
    from app.rag.history import get_line_history
    before = get_line_history(homes["busy"], t=-18)["your_line"]["past_damage_total"]
    out = get_line_history(homes["busy"], t=96)
    labels = [b["storm"] for b in out["your_line"]["by_storm"]]
    assert any("this storm" in x for x in labels)
    expected = sum(1 for r in homes["rows"]
                   if r["circuit_id"] == homes["busy_circ"] and r["report_date"] < "2025-02-17")
    assert out["your_line"]["past_damage_total"] == expected > before
    assert_private(out)


@needs_data
def test_history_numbers_literal_and_counts(homes):
    from app.rag.history import get_line_history
    out = get_line_history(homes["busy"], t=-18)
    yl = out["your_line"]
    assert re.fullmatch(r"\d+ of \d+ past damage records had an access issue noted",
                        yl["access_issues"])
    for ty in yl["common_damage_types"]:
        assert ty["count"] >= 3
    rep = yl["typical_repair"]
    if isinstance(rep, dict):
        assert rep["records_used"] >= 5
        assert ("range_days" in rep) == (rep["records_used"] >= 10)
    summary = " ".join(out["summary"])
    assert str(yl["past_damage_total"]) in summary
    lly = out["lines_like_yours"]
    assert lly["lines_compared"] == 5


@needs_data
def test_history_suppresses_thin_lines(homes):
    from app.rag.history import get_line_history
    out = get_line_history(homes["quiet"], t=-18)
    assert out["your_line"]["enough_history"] is False
    assert out["your_line"]["past_damage_total"] is None
    assert "not enough history" in json.dumps(out)
    assert_private(out)


@needs_data
def test_history_unknown_home():
    from app.rag.history import get_line_history
    with pytest.raises(UnknownHome):
        get_line_history("p_0000000000000000", 0)
    with pytest.raises(UnknownHome):
        get_line_history("'; DROP TABLE premises; --", 0)


@needs_data
def test_run_tool_history_uses_ctx_not_model_input(homes):
    ctx = {"home_id": homes["busy"], "t": -18}
    a = run_tool("get_line_history", {}, ctx)
    b = run_tool("get_line_history", {"home_id": homes["quiet"], "t": 96}, ctx)
    assert a == b and "error" not in a
    assert run_tool("get_line_history", {}, {"home_id": homes["busy"], "t": "abc"}) == {"error": "invalid input"}
    assert run_tool("get_line_history", {}, {"home_id": homes["busy"], "t": float("nan")}) == {"error": "invalid t"}


@needs_data
def test_history_deterministic(homes):
    from app.rag.history import get_line_history
    assert get_line_history(homes["busy"], 4.5) == get_line_history(homes["busy"], 4.5)
