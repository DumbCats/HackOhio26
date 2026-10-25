"""chat(req): the single entry point (contracts/API.md section 5).

Input checks and emergency routing run first, in plain code. Then Layer 2 (Gemini, llm.py) answers
if it can and every number in its reply is grounded in tool output; otherwise Layer 1 templates answer.
"""
from app.chat import fallback, guardrails, llm


def chat(req: dict) -> dict:
    guardrails.validate_request(req)
    text = req["messages"][-1]["content"]

    routed = guardrails.safety_route(text)
    if routed:
        reply, flag = routed
        return _response(reply, [], safety_flag=flag)

    ctx = {
        "home_id": req["home_id"],
        "t": req.get("t", 0),
        "needs": [n for n in req.get("needs", []) if n in guardrails.NEEDS],
        "low_power": req.get("low_power", False),
        **{k: req.get(k) for k in ("severity", "crews", "access_blocked", "extra_damage", "switching")},
    }
    try:
        from app.sim.feed import home_info
        home_info(ctx["home_id"])
    except KeyError:
        raise ValueError("unknown home")
    except ImportError:
        pass
    result = llm.answer(ctx, req["messages"])
    if result:
        reply, used, outputs = result
        rag_emergency = any(isinstance(o, dict) and o.get("emergency") for o in outputs)
        if rag_emergency:
            return _response(guardrails.EMERGENCY_REPLY, used, safety_flag=True)
        if guardrails.numbers_grounded(reply, outputs) and not _is_safety_topic(text):
            return _response(reply, used, source="llm")

    reply, used = fallback.answer(ctx, text)
    return _response(reply, used)


def _is_safety_topic(text: str) -> bool:
    """Safety/medical questions are answered only with fixed text (the template layer quotes get_prep)."""
    return fallback.classify(text) in ("generator", "heat", "candles", "meds", "food")


def _response(reply: str, tools_used: list, safety_flag: bool = False, source: str = "fallback") -> dict:
    return {"reply": reply, "tools_used": tools_used, "safety_flag": safety_flag, "source": source}
