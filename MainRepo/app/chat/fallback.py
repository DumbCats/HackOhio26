"""Template chat (A11 fallback, Layer 1). No model. Every number and safety line is quoted from tool output."""
import re

from app.chat import guardrails
from app.chat.tools import TOOLS

OUTAGE_PAGE = "https://www.appalachianpower.com/outages/"

# Checked in order; first match wins.
INTENTS = [
    ("alerts", r"alert|notif|qualif|eligib|text me|\bsms\b|message me"),
    ("history", r"how often|past storms?|history|before\b.*(storm|damage)|happened before"),
    ("risk", r"why\b.*\b(risk|higher|high|band|area|lose)"),
    ("explain", r"what is an?\b|what's an?\b|what does .* mean|how does|how do you|explain|privacy|my data"),
    ("candles", r"candles?"),
    ("heat", r"stove|oven|grill|space heater|kerosene|propane heater|heat (the|my|our) (house|home|place|room)|stay warm|keep warm|too cold|freezing in here"),
    ("generator", r"generator"),
    ("meds", r"insulin|medic|prescription|pharmac|refrigerat|fridge|inhaler"),
    ("food", r"food|freezer|spoil|groceries"),
    ("when_back", r"when|how long|back on|restor|\beta\b|\bhours?\b|come back|get (my )?power"),
    ("changes", r"what could change|change this|why (did|has|is) .*(change|longer|different|moved)|update|crews?|roads?"),
    ("risk", r"risk|will i lose|going to lose|storm|likely to|chance of (an )?outage|forecast"),
    ("trust", r"trust|how sure|confiden|accurate|reliable|promise|real data|simulat"),
    ("explain_why", r"\bwhy\b"),
    ("do_now", r"what (do|should) i|what now|help|prepare|prep\b|checklist"),
]
_COMPILED = [(name, re.compile(p, re.I)) for name, p in INTENTS]


def classify(text: str) -> str:
    for name, rx in _COMPILED:
        if rx.search(text):
            return name
    return "unknown"


def answer(ctx: dict, text: str) -> tuple[str, list[str]]:
    """Return (reply, tools_used) for the user's latest message."""
    intent = classify(text)
    used: list[str] = []

    def call(name: str) -> dict:
        used.append(name)
        return TOOLS[name](ctx)

    if intent == "alerts":
        return call("get_alerts")["eligibility_summary"], used

    if intent == "history":
        return _history(ctx, used), used

    if intent in ("explain", "explain_why"):
        return _explain(ctx, text, used), used

    if intent == "generator":
        return _safety_line(call("get_prep"), "s_generator"), used

    if intent == "heat":
        return _safety_line(call("get_prep"), "s_heat"), used

    if intent == "candles":
        return _safety_line(call("get_prep"), "s_candles"), used

    if intent == "meds":
        return _meds(ctx, call), used

    if intent == "food":
        return _action(call("get_prep"), "a_fridge"), used

    if intent == "when_back":
        return _when_back(call("get_restoration")), used

    if intent == "changes":
        return _changes(call("get_restoration")), used

    if intent == "risk":
        return _risk(call("get_forecast")), used

    if intent == "trust":
        return _trust(call("get_restoration"), call("get_forecast")), used

    if intent == "do_now":
        return _do_now(call("get_restoration"), call("get_prep")), used

    return (
        "I can help with when your power is back, what to do while it's out, and why your area "
        f"has its risk level. I don't have live weather. For official outage news, see {OUTAGE_PAGE}"
    ), used


def _history(ctx: dict, used: list) -> str:
    from app.rag.tools import run_tool
    used.append("get_line_history")
    h = run_tool("get_line_history", {}, ctx)
    if "error" in h:
        return "I don't have past storm history for your line."
    return " ".join(h.get("summary", [])[:2]) or "I don't have past storm history for your line."


def _explain(ctx: dict, text: str, used: list) -> str:
    from app.rag.tools import run_tool
    used.append("search_explanations")
    res = run_tool("search_explanations", {"query": text}, ctx)
    hits = res.get("results") or []
    if not hits:
        return ("I can help with when your power is back, what to do while it's out, and why your area "
                f"has its risk level. For official outage news, see {OUTAGE_PAGE}")
    return hits[0]["text"]


def _safety_line(prep: dict, safety_id: str) -> str:
    text = next((s["text"] for s in prep["safety"] if s["id"] == safety_id), prep["emergency_line"])
    return f"{text} {prep['emergency_line']}"


def _action(prep: dict, action_id: str) -> str:
    return next((a["text"] for a in prep["actions"] if a["id"] == action_id), prep["emergency_line"])


def _meds(ctx: dict, call) -> str:
    parts = []
    restoration = call("get_restoration")
    est = restoration.get("estimate")
    if restoration.get("is_out") and est:
        parts.append(f"Your power is out. {est['headline']}. That's an estimate, not a promise.")
    prep = call("get_prep")
    need = next((n["text"] for n in prep.get("needs_actions", []) if n["need"] == "refrigerated_meds"), None)
    if need:
        parts.append(need)
    else:
        parts.append(_action(prep, "a_fridge"))
        parts.append("For medicine, check the label or ask your pharmacist. Add it under your needs and I can tailor this.")
    parts.append("If you have an emergency, call 911.")
    return " ".join(parts)


def _when_back(r: dict) -> str:
    if r.get("restored_at_t") is not None and not r.get("is_out"):
        return (r.get("recap") or {}).get("message") or "Your power is back on."
    if not r.get("is_out"):
        return "We don't see an outage at your home right now."
    est = r["estimate"]
    msg = f"{est['headline']}. That's an estimate, not a promise."
    step = r.get("step_restoration")
    if step:
        msg += f" {step['message']}"
    return msg


def _changes(r: dict) -> str:
    if not r.get("is_out") or not r.get("drivers"):
        return "There's nothing to change right now, since we don't see an outage at your home."
    lines = []
    for d in r["drivers"]:
        h = abs(d["effect_h"])
        if d.get("active"):
            lines.append(f"{d['label']}: already included")
        elif h < 0.5:
            lines.append(f"{d['label']}: little or no change")
        else:
            word = "longer" if d["effect_h"] > 0 else "shorter"
            lines.append(f"{d['label']}: about {h:g} hours {word}")
    return "What could change your estimate: " + "; ".join(lines) + "."


def _risk(f: dict) -> str:
    risk = f["risk"]
    if f.get("fallback"):
        return f"{f['fallback']['message']} {f['fallback']['link']}"
    reasons = "; ".join(x["label"] for x in risk["factors"])
    return f"{risk['headline']}. Why: {reasons}. {risk['rank_note']}"


def _trust(r: dict, f: dict) -> str:
    conf = f["risk"]["confidence_reason"] if not f.get("fallback") else f["fallback"]["message"]
    gaps = "; ".join(r["missing_data"])
    return (
        f"{conf} What we don't have: {gaps}. "
        "Treat times as estimates, not promises."
    )


def _do_now(r: dict, prep: dict) -> str:
    needs = " ".join(n["text"] for n in prep.get("needs_actions", []))
    if not r.get("is_out"):
        steps = " ".join(a["text"] for a in prep["actions"][:3])
        return f"{steps} {needs}".strip()
    steps = " ".join(a["text"] for a in prep["actions"][:2])
    if needs:
        steps = f"{steps} {needs}"
    return f"{steps} {prep['emergency_line']}"
