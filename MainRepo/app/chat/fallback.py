"""Template chat (A11 fallback, Layer 1). No model. Every number and safety line is quoted from tool output."""
import re

from app.chat import guardrails
from app.chat.tools import TOOLS

OUTAGE_PAGE = "https://www.appalachianpower.com/outages/"

# Checked in order; first match wins.
INTENTS = [
    ("generator", r"generator|heat(er|ing)?\b|stove|oven|grill|candle"),
    ("meds", r"insulin|medic|prescription|pharmac|refrigerat|fridge|inhaler"),
    ("food", r"food|freezer|spoil|groceries"),
    ("when_back", r"when|how long|back on|restor|\beta\b|\bhours?\b|come back|get (my )?power"),
    ("changes", r"what could change|change this|why (did|has|is) .*(change|longer|different|moved)|update|crews?|roads?"),
    ("risk", r"risk|will i lose|going to lose|storm|likely to|chance of (an )?outage|forecast"),
    ("trust", r"trust|how sure|confiden|accurate|reliable|promise|real data|simulat"),
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

    if intent == "generator":
        return _safety_line(call("get_prep"), "s_generator"), used

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
        "Past damage and homes are real data; the live outage feed and crews are simulated, "
        "so treat times as estimates, not promises."
    )


def _do_now(r: dict, prep: dict) -> str:
    if not r.get("is_out"):
        return "Your power is on. I can walk you through how to prepare. Ask about food, medicine, or what could happen."
    steps = " ".join(a["text"] for a in prep["actions"][:2])
    return f"{steps} {prep['emergency_line']}"
