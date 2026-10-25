"""Chat guardrails (MASTER_PLAN N12). Plain code, no model involved.

Safety text lives here as fixed strings so it can be reviewed once.
"""
import re

MAX_CHARS = 1000
HOME_ID_RE = re.compile(r"^p_[0-9a-f]{16}$")

EMERGENCY_REPLY = (
    "If someone is hurt, you smell smoke or gas, or you see a fire or a downed power line, "
    "call 911 now. Stay at least 35 feet away from downed lines and treat every one as live. "
    "To reach the utility about your outage, use its outage page: https://www.appalachianpower.com/outages/"
)

MEDICAL_DEVICE_REPLY = (
    "If a medical device you rely on has stopped and you feel unwell, call 911. "
    "Otherwise call your device provider or doctor about a backup. "
    "Tell us in your needs that you use one and we can tailor the guidance."
)

_EMERGENCY_PATTERNS = [
    r"\b911\b",
    r"can'?t breathe", r"cannot breathe", r"trouble breathing", r"chest pain",
    r"heart attack", r"\bstroke\b", r"unconscious", r"overdose", r"bleeding",
    r"\bhurt\b", r"\binjured\b",
    r"\bfire\b", r"\bsmoke\b", r"smell(s)? gas", r"gas leak", r"carbon monoxide", r"\bco alarm\b",
    r"down(ed)? (power )?line", r"line (is )?down", r"wire (is )?down", r"sparking", r"\bsparks\b",
]
_EMERGENCY_RE = re.compile("|".join(_EMERGENCY_PATTERNS), re.I)

_MEDICAL_DEVICE_RE = re.compile(
    r"oxygen|cpap|ventilator|dialysis|nebuli[sz]er|breathing machine|medical device", re.I
)

_NUM_RE = re.compile(r"\d+(?:\.\d+)?")


def validate_request(req: dict) -> None:
    """Raise ValueError on a bad request. Routes turn this into HTTP 400."""
    if not isinstance(req, dict):
        raise ValueError("request must be an object")
    if not HOME_ID_RE.match(str(req.get("home_id", ""))):
        raise ValueError("bad home_id")
    msgs = req.get("messages")
    if not isinstance(msgs, list) or not msgs:
        raise ValueError("messages required")
    for m in msgs:
        if m.get("role") not in ("user", "assistant") or not isinstance(m.get("content"), str):
            raise ValueError("bad message")
        if len(m["content"]) > MAX_CHARS:
            raise ValueError("message too long")
    if msgs[-1]["role"] != "user":
        raise ValueError("last message must be from the user")


def is_emergency(text: str) -> bool:
    return bool(_EMERGENCY_RE.search(text))


def mentions_medical_device(text: str) -> bool:
    return bool(_MEDICAL_DEVICE_RE.search(text))


def numbers_grounded(reply: str, tool_outputs: list) -> bool:
    """N12 number check: every number in the reply must appear in some tool output.

    Compares numbers as values, so 6.0 in the output grounds a "6" in the reply.
    Used for LLM replies (Layer 2); the template fallback quotes tool text directly.
    """
    allowed = set()
    for out in tool_outputs:
        for n in _NUM_RE.findall(_flatten(out)):
            allowed.add(float(n))
    return all(float(n) in allowed for n in _NUM_RE.findall(reply))


def _flatten(obj) -> str:
    if isinstance(obj, dict):
        return " ".join(_flatten(v) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return " ".join(_flatten(v) for v in obj)
    return str(obj)
