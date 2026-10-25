"""Layer 2: Gemini tool loop. Returns None whenever anything is off, so the caller uses Layer 1.

The model never sees ids and never picks the home: tools run with the request's own context.
"""
import functools
import logging
from typing import Optional

from app import config
from app.chat.tools import TOOLS
from app.rag.tools import RAG_TOOL_NAMES, run_tool as run_rag_tool

log = logging.getLogger("uvicorn.error")

MAX_ROUNDS = 4
TIMEOUT_MS = 20_000
HIDDEN_KEYS = {"home_id", "cell_id", "circuit_id"}

SYSTEM_PROMPT = """You are the Outage Concierge, helping a customer of a power utility during a storm.
- Be calm and brief: a few short sentences in plain words, no markdown.
- Use the tools to get facts. Every number you state must come from a tool result. Never calculate, round differently, or guess a number.
- Power return times and risk are estimates: say "an estimate, not a promise".
- For safety or medical advice, quote the wording from get_prep. Do not invent safety advice.
- If someone may be in danger, tell them to call 911.
- Never mention ids, internal data, or how the system works inside.
- If the tools cannot answer, say so and point to the utility's outage page.
- For "how does this work", "why" or "how sure are you" questions, call search_explanations and answer only from its results. If it returns use_tool, call that tool instead.
- For "how often does my line get damaged" or "how long did repairs take before", call get_line_history.
- For "do I qualify for alerts" questions, call get_alerts and use its eligibility_summary.
- If the request says the phone is in low-power mode, answer in one or two short sentences."""


def _clean(obj):
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items() if k not in HIDDEN_KEYS}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    return obj


@functools.lru_cache(maxsize=1)
def _client():
    from google import genai
    from google.genai import types
    return genai.Client(api_key=config.GEMINI_API_KEY, http_options=types.HttpOptions(timeout=TIMEOUT_MS))


def _generate(contents, gen_config):
    """The one place the model is called (tests replace this)."""
    return _client().models.generate_content(model=config.GEMINI_MODEL, contents=contents, config=gen_config)


def _tool_config():
    from google.genai import types
    decls = [
        types.FunctionDeclaration(name=name, description=DESCRIPTIONS[name])
        for name in TOOLS
    ]
    decls.append(types.FunctionDeclaration(
        name="search_explanations",
        description=DESCRIPTIONS["search_explanations"],
        parameters=types.Schema(type="OBJECT", properties={
            "query": types.Schema(type="STRING", description="The customer's question in their own words.")},
            required=["query"]),
    ))
    decls.append(types.FunctionDeclaration(name="get_line_history", description=DESCRIPTIONS["get_line_history"]))
    return types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=[types.Tool(function_declarations=decls)],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )


DESCRIPTIONS = {
    "get_forecast": "Risk band, reasons and what would change it for the customer's home, before or during the storm.",
    "get_restoration": "Whether the customer's power is out and the estimated range of hours until it returns.",
    "get_prep": "Fixed safety and preparation guidance for the customer's situation. Quote its wording.",
    "get_alerts": "Whether the customer qualifies for outage alerts, the alerts they have received, channels and escalation.",
    "search_explanations": ("Approved plain-language explanations of how this app works: risk bands, confidence, "
                            "how the restoration range is estimated, privacy, missing data."),
    "get_line_history": "Counts of past storm damage on the customer's line and typical repair days. No arguments.",
}


def answer(ctx: dict, messages: list) -> Optional[tuple[str, list[str], list[dict]]]:
    """Return (reply, tools_used, tool_outputs), or None to make the caller fall back."""
    if not config.GEMINI_API_KEY:
        return None
    try:
        from google.genai import types
        gen_config = _tool_config()
        contents = [
            types.Content(role="model" if m["role"] == "assistant" else "user", parts=[types.Part(text=m["content"])])
            for m in messages[-12:]
        ]
        if ctx.get("low_power"):
            contents[-1].parts.append(types.Part(text="(My phone is in low-power mode.)"))
        used: list[str] = []
        outputs: list[dict] = []
        for _ in range(MAX_ROUNDS + 1):
            resp = _generate(contents, gen_config)
            if not resp.candidates:  # blocked or empty
                return None
            content = resp.candidates[0].content
            calls = [p.function_call for p in (content.parts or []) if p.function_call]
            if not calls:
                text = (resp.text or "").strip()
                return (text, used, outputs) if text else None
            if len(used) >= MAX_ROUNDS * 2:
                return None
            contents.append(content)
            parts = []
            for call in calls:
                if call.name in RAG_TOOL_NAMES:
                    out = _clean(run_rag_tool(call.name, dict(call.args or {}), ctx))
                elif call.name in TOOLS:
                    out = _clean(TOOLS[call.name](ctx))
                else:
                    return None
                used.append(call.name)
                outputs.append(out)
                parts.append(types.Part.from_function_response(name=call.name, response={"result": out}))
            contents.append(types.Content(role="user", parts=parts))
        return None  # still asking for tools after the last round
    except Exception as exc:  # no internet, bad key, quota, refusal: Layer 1 answers instead
        log.warning("Gemini unavailable, using fallback (%s)", type(exc).__name__)
        return None
