"""Chat guardrails (MASTER_PLAN N12). Plain code, no model involved.

Safety text lives here as fixed strings so it can be reviewed once.
"""
import math
import re

MAX_CHARS = 1000
MAX_MESSAGES = 40
HOME_ID_RE = re.compile(r"p_[0-9a-f]{16}")
NEEDS = {"medical_device", "refrigerated_meds", "mobility", "well_water", "critical_facility"}

EMERGENCY_REPLY = (
    "Call 911 now if someone is hurt, not breathing, or unresponsive, or if you see a fire or a downed power line. "
    "Stay at least 35 feet away from downed lines and treat every one as live. If a line is on your car, stay "
    "inside unless the car is on fire. Want a call back from the utility? Tell me and I'll note the request."
)

GAS_CO_REPLY = (
    "Leave the building now and get to fresh air. Don't use light switches, phones, or anything that could "
    "spark until you are outside. Then call 911 from outside. If a carbon monoxide alarm is sounding or "
    "people feel dizzy or sick, get everyone out and call 911."
)

SELF_HARM_REPLY = (
    "I'm sorry you're going through this. You don't have to face it alone. Call or text 988 (Suicide and "
    "Crisis Lifeline) any time, or call 911 if you are in danger right now."
)

MEDICAL_DEVICE_REPLY = (
    "If a medical device someone relies on has stopped and they are struggling to breathe or feel unwell, "
    "call 911. Otherwise call the device provider or doctor about backup power. "
    "Tell us in your needs that you use one and we can tailor the guidance."
)

_EMERGENCY_PATTERNS = [
    r"\b911\b", r"(medical|real) emergency", r"this is an emergency",
    r"can'?t breathe", r"cannot breathe", r"(trouble|difficulty|hard time) breathing", r"not breathing",
    r"isn'?t breathing", r"stopped breathing", r"gasping", r"choking", r"chest pains?",
    r"heart attack", r"\bstroke\b", r"seizure", r"unconscious", r"unresponsive", r"passed out", r"fainted",
    r"\b(he|she|they|someone|somebody|person|baby|child|kid|son|daughter|mom|dad|grandma|grandpa|neighbou?r|husband|wife)\b.{0,25}\b(isn'?t|is not|not|stopped) (moving|responding|waking)",
    r"overdose", r"bleeding", r"\bhurt\b", r"\binjur(ed|y)\b",
    r"electrocut\w*", r"(got|been|being) (shocked|zapped)", r"electric(al)? shock",
    r"\bfire\b", r"on fire", r"\bsmoke\b", r"smoking (outlet|wire|panel|meter|pole)", r"burning smell",
    r"smells? (like )?burning", r"something('s| is) burning", r"\bflames?\b",
    r"(power |electric(al)? )?(lines?|wires?|cables?) (is |are )?(down|hanging|on the ground|on (my|the|a) car|buzzing|sparking)",
    r"down(ed)? (power )?(lines?|wires?)", r"fallen (power )?(lines?|wires?)", r"(line|wire)s? (fell|came down)",
    r"sparking", r"\bsparks?\b", r"\barcing\b",
]
_GAS_CO_PATTERNS = [
    r"smell(s|ing)? (of |like )?gas", r"gas (leak|smell)", r"rotten eggs?", r"carbon monoxide",
    r"\bco (alarm|detector)", r"(co|carbon monoxide|smoke) (alarm|detector) (is )?(going off|beeping|sounding)",
]
_SELF_HARM_PATTERNS = [
    r"kill (myself|me)", r"suicid\w*", r"end (my|it) (life|all)", r"want to die", r"hurt myself",
    r"self[- ]harm",
]
_DISTRESS_RE = re.compile(r"gasp|struggl|can'?t breathe|not breathing|unwell|turning blue|dizzy|faint", re.I)
_EMERGENCY_RE = re.compile("|".join(_EMERGENCY_PATTERNS), re.I)
_GAS_CO_RE = re.compile("|".join(_GAS_CO_PATTERNS), re.I)
_SELF_HARM_RE = re.compile("|".join(_SELF_HARM_PATTERNS), re.I)

_MEDICAL_DEVICE_RE = re.compile(
    r"oxygen|cpap|bipap|ventilator|dialysis|nebuli[sz]er|breathing machine|medical device|feeding pump", re.I
)

_NUM_RE = re.compile(r"\d+(?:\.\d+)?")
_NUM_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30,
    "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100,
    "dozen": 12, "half": 0.5,
}
_NUM_WORD_RE = re.compile(r"\b(" + "|".join(_NUM_WORDS) + r")\b", re.I)
_PERCENT_RE = re.compile(r"%|\bpercent\b|\bper cent\b", re.I)


def _bounded(req: dict, key: str, lo: float, hi: float, integer: bool = False) -> None:
    v = req.get(key)
    if v is None:
        return
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not lo <= v <= hi:
        raise ValueError(f"bad {key}")
    if integer and int(v) != v:
        raise ValueError(f"bad {key}")


def validate_request(req: dict) -> None:
    """Raise ValueError on a bad request. Routes turn this into HTTP 400."""
    if not isinstance(req, dict):
        raise ValueError("request must be an object")
    if not HOME_ID_RE.fullmatch(str(req.get("home_id", ""))):
        raise ValueError("bad home_id")
    msgs = req.get("messages")
    if not isinstance(msgs, list) or not msgs:
        raise ValueError("messages required")
    if len(msgs) > MAX_MESSAGES:
        raise ValueError("too many messages")
    for m in msgs:
        if not isinstance(m, dict) or m.get("role") not in ("user", "assistant") or not isinstance(m.get("content"), str):
            raise ValueError("bad message")
        if len(m["content"]) > MAX_CHARS:
            raise ValueError("message too long")
    if msgs[-1]["role"] != "user":
        raise ValueError("last message must be from the user")
    _bounded(req, "t", -1e4, 1e4)
    _bounded(req, "severity", 0, 1)
    _bounded(req, "crews", 1, 30, integer=True)
    _bounded(req, "extra_damage", 0, 10, integer=True)
    for key in ("access_blocked", "switching", "low_power"):
        if req.get(key) is not None and not isinstance(req[key], bool):
            raise ValueError(f"bad {key}")
    needs = req.get("needs", [])
    if not isinstance(needs, list) or any(not isinstance(n, str) for n in needs):
        raise ValueError("bad needs")


def safety_route(text: str):
    """(fixed reply, safety_flag) if the message needs a fixed safety answer, else None.

    Checked before any model or template runs. Order matters: self-harm, gas/CO, then
    medical-device-with-distress and general emergencies, then a medical device without distress."""
    if _SELF_HARM_RE.search(text):
        return SELF_HARM_REPLY, True
    if _GAS_CO_RE.search(text):
        return GAS_CO_REPLY, True
    device = bool(_MEDICAL_DEVICE_RE.search(text))
    if device and _DISTRESS_RE.search(text):
        return EMERGENCY_REPLY, True
    if _EMERGENCY_RE.search(text):
        return EMERGENCY_REPLY, True
    if device:
        return MEDICAL_DEVICE_REPLY, False
    return None


def is_emergency(text: str) -> bool:
    r = safety_route(text)
    return bool(r and r[1])


def mentions_medical_device(text: str) -> bool:
    return bool(_MEDICAL_DEVICE_RE.search(text))


def numbers_grounded(reply: str, tool_outputs: list) -> bool:
    """N12 number check: every number in the reply must appear in some tool output.

    Compares numbers as values, so 6.0 in the output grounds a "6" in the reply. Spelled-out
    numbers count as numbers, and any percent is rejected (risk is never a percent).
    Used for LLM replies (Layer 2); the template fallback quotes tool text directly.
    """
    if _PERCENT_RE.search(reply):
        return False
    allowed = set()
    for out in tool_outputs:
        for n in _NUM_RE.findall(_flatten(out)):
            allowed.add(float(n))
    found = [float(n) for n in _NUM_RE.findall(reply)]
    found += [float(_NUM_WORDS[w.lower()]) for w in _NUM_WORD_RE.findall(reply) if w.lower() not in ("one", "half")]
    return all(n in allowed for n in found)


def _flatten(obj) -> str:
    if isinstance(obj, dict):
        return " ".join(_flatten(v) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return " ".join(_flatten(v) for v in obj)
    return str(obj)
