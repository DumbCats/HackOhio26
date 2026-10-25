"""Layer 2 (Gemini) with a fake model: no key, no network."""
from types import SimpleNamespace as NS

import pytest

from app import config
from app.chat import llm
from app.chat.service import chat

HOME = "p_3f9a2c71b04e8d21"


def req(text, **kw):
    return {"home_id": HOME, "t": 10, "needs": ["refrigerated_meds"],
            "messages": [{"role": "user", "content": text}], **kw}


def text_resp(text):
    return NS(candidates=[NS(content=NS(parts=[NS(function_call=None, text=text)]))], text=text)


def call_resp(*names):
    parts = [NS(function_call=NS(name=n, args={})) for n in names]
    return NS(candidates=[NS(content=NS(role="model", parts=parts))], text=None)


@pytest.fixture
def fake(monkeypatch):
    """Install a scripted model: each generate call pops the next response."""
    monkeypatch.setattr(config, "GEMINI_API_KEY", "test-key")

    def install(*responses):
        queue, seen = list(responses), []

        def generate(contents, gen_config):
            seen.append(contents)
            r = queue.pop(0)
            if isinstance(r, Exception):
                raise r
            return r
        monkeypatch.setattr(llm, "_generate", generate)
        return seen
    return install


def test_tool_call_then_grounded_answer(fake):
    seen = fake(call_resp("get_restoration"),
                text_resp("Our estimate is 6 to 14 hours, an estimate, not a promise."))
    r = chat(req("when will it be back?"))
    assert r["source"] == "llm" and r["tools_used"] == ["get_restoration"]
    assert "6 to 14" in r["reply"] and r["safety_flag"] is False
    sent = str(seen[1][-1])  # tool result handed back to the model
    assert HOME not in sent and "cell_id" not in sent  # ids are stripped


def test_invented_number_falls_back(fake):
    fake(call_resp("get_restoration"), text_resp("It will be back in 97 hours."))
    r = chat(req("when will my power be back?"))
    assert r["source"] == "fallback" and "97 hours" not in r["reply"]


def test_blocked_or_empty_reply_falls_back(fake):
    fake(NS(candidates=[], text=None))
    assert chat(req("when will my power be back?"))["source"] == "fallback"
    fake(text_resp("   "))
    assert chat(req("when will my power be back?"))["source"] == "fallback"


def test_api_error_falls_back(fake):
    fake(RuntimeError("no internet"))
    assert chat(req("when will my power be back?"))["source"] == "fallback"


def test_missing_key_never_calls_model(monkeypatch):
    def boom(*a):
        raise AssertionError("model called without a key")
    monkeypatch.setattr(llm, "_generate", boom)
    assert chat(req("when will my power be back?"))["source"] == "fallback"


def test_unknown_tool_and_endless_tool_loop_fall_back(fake):
    fake(call_resp("delete_everything"))
    assert chat(req("when will my power be back?"))["source"] == "fallback"
    fake(*[call_resp("get_prep")] * 10)
    assert chat(req("when will my power be back?"))["source"] == "fallback"


def test_emergency_never_reaches_model(fake):
    seen = fake(text_resp("should not be used"))
    r = chat(req("there is a downed power line and sparking"))
    assert r["safety_flag"] is True and r["source"] == "fallback" and seen == []


def test_medical_device_never_reaches_model(fake):
    seen = fake(text_resp("should not be used"))
    chat(req("my oxygen concentrator stopped"))
    assert seen == []
