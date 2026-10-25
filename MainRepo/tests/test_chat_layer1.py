import pytest

from app.chat import guardrails
from app.chat.fallback import classify
from app.chat.service import chat

pytestmark = pytest.mark.usefixtures("mock_tools")

HOME = "p_3f9a2c71b04e8d21"


def req(text, t=5, **kw):
    return {"home_id": HOME, "t": t, "needs": kw.pop("needs", []),
            "messages": [{"role": "user", "content": text}], **kw}


def test_insulin_panic_uses_restoration_and_prep():
    r = chat(req("my power just went out and my insulin is in the fridge, what do i do??",
                 needs=["refrigerated_meds"]))
    assert r["source"] == "fallback" and r["safety_flag"] is False
    assert r["tools_used"] == ["get_restoration", "get_prep"]
    assert "Likely back in 6 to 14 hours" in r["reply"]
    assert "28 days" in r["reply"]  # quoted from get_prep, not generated


def test_when_back_quotes_estimate_and_step_note():
    r = chat(req("when will my power be back?"))
    assert "6 to 14 hours" in r["reply"] and "not a promise" in r["reply"]
    assert "Some neighbors may get power back before you" in r["reply"]


def test_not_out_and_restored_states():
    assert "don't see an outage" in chat(req("when is it back", t=-18))["reply"]
    assert "about 14 hours" in chat(req("when is it back", t=19))["reply"]


def test_changes_lists_driver_effects_from_tool():
    r = chat(req("what could change this?"))
    assert "Roads blocked by ice or trees: about 6 hours longer" in r["reply"]
    assert "2 more crews on your line: about 1.5 hours shorter" in r["reply"]


def test_risk_answer_is_a_comparison_not_a_percent():
    r = chat(req("will i lose power in the storm?", t=-18))
    assert "HIGH risk" in r["reply"] and "%" not in r["reply"]


@pytest.mark.parametrize("text", [
    "there's a power line down in my yard", "I smell smoke", "my dad has chest pain",
    "I can't breathe", "should I call 911?",
])
def test_emergency_skips_everything_and_sets_flag(text):
    r = chat(req(text))
    assert r["safety_flag"] is True and r["tools_used"] == []
    assert r["reply"] == guardrails.EMERGENCY_REPLY


def test_medical_device_gets_fixed_text():
    r = chat(req("my oxygen concentrator stopped"))
    assert r["reply"] == guardrails.MEDICAL_DEVICE_REPLY


def test_unknown_question_points_to_official_page_and_says_no_weather():
    r = chat(req("what is the weather tomorrow?"))
    assert "don't have live weather" in r["reply"] and "appalachianpower.com" in r["reply"]


@pytest.mark.parametrize("bad", [
    {"home_id": "123", "messages": [{"role": "user", "content": "hi"}]},
    {"home_id": HOME, "messages": []},
    {"home_id": HOME, "messages": [{"role": "user", "content": "x" * 1001}]},
    {"home_id": HOME, "messages": [{"role": "assistant", "content": "hi"}]},
])
def test_bad_requests_are_rejected(bad):
    with pytest.raises(ValueError):
        chat(bad)


def test_number_check():
    out = [{"estimate": {"p10_h": 5.7, "p90_h": 13.7}, "x": 6.0}]
    assert guardrails.numbers_grounded("About 6 hours, maybe 13.7.", out)
    assert not guardrails.numbers_grounded("About 3 hours.", out)


def test_classify_does_not_match_inside_words():
    assert classify("some details please") == "unknown"
