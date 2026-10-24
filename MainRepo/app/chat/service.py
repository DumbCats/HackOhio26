"""chat(req): the single entry point (contracts/API.md section 5).

Layer 1 only: input checks, emergency routing, then the template answer. Layer 2 will put a model
call between the emergency check and the template, and fall back to the template on any failure.
"""
from app.chat import fallback, guardrails


def chat(req: dict) -> dict:
    guardrails.validate_request(req)
    text = req["messages"][-1]["content"]

    if guardrails.is_emergency(text):
        return _response(guardrails.EMERGENCY_REPLY, [], safety_flag=True)

    if guardrails.mentions_medical_device(text):
        return _response(guardrails.MEDICAL_DEVICE_REPLY, [])

    ctx = {
        "home_id": req["home_id"],
        "t": req.get("t", 0),
        "needs": req.get("needs", []),
        "low_power": req.get("low_power", False),
        **{k: req.get(k) for k in ("severity", "crews", "access_blocked", "extra_damage", "switching")},
    }
    reply, used = fallback.answer(ctx, text)
    return _response(reply, used)


def _response(reply: str, tools_used: list, safety_flag: bool = False) -> dict:
    return {"reply": reply, "tools_used": tools_used, "safety_flag": safety_flag, "source": "fallback"}
