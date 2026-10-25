"""Tool layer Lane D registers in the chat's Claude tool loop.

    from app.rag.tools import TOOLS as RAG_TOOLS, run_tool as run_rag_tool, RAG_TOOL_NAMES

- search_explanations: approved plain-language passages (the LLM quotes them).
- get_line_history: privacy-safe past-damage counts for the home's line.
  home_id and t are injected by the server from the chat request (ctx), never chosen
  by the model.

run_tool never raises: bad input or an unknown home comes back as {"error": ...}.
"""
from __future__ import annotations

import math
import re

from app.models.common import UnknownHome
from app.rag import history, retriever

MAX_QUERY_CHARS = 500
NOTE = "Quote or paraphrase these; do not add numbers that are not here."

# --- safety / medical routing -----------------------------------------------------
# Safety and medical wording is Lane D's fixed text (get_prep); the corpus never answers it.

_EMERGENCY = (
    r"emergenc\w*", r"911", r"on fire", r"fire(?! (station|dept|department)s?)", r"smoke", r"smoking", r"spark\w*",
    r"burn\w*", r"hurt", r"injur\w*", r"bleeding", r"unconscious", r"passed out",
    r"not breathing", r"can'?t breathe", r"cannot breathe", r"trouble breathing",
    r"chest pain", r"carbon monoxide", r"co alarm", r"electrocut\w*",
    r"touching (a|the) (power )?(line|wire)", r"dying",
)
_SAFETY = (
    r"safe", r"safety", r"danger\w*", r"generators?", r"downed", r"lines? (is |are )?down",
    r"wires? (is |are )?down", r"power line (is |are )?down", r"fallen (line|wire)s?",
    r"candles?", r"space heaters?", r"heat(er|ing)?", r"stay warm", r"cold", r"freez\w*",
    r"medic\w*", r"insulin", r"oxygen", r"cpap", r"dialysis", r"nebuli[sz]er",
    r"ventilator", r"wheelchair", r"pills?", r"prescription\w*", r"drug\w*", r"fridge",
    r"refrigerat\w*", r"food", r"spoil\w*", r"well water", r"well pump", r"drinking water",
    r"grill", r"stove",
    r"first aid", r"what (should|do) i do", r"prepare", r"prep", r"supplies",
    r"flashlights?", r"evacuat\w*", r"shelter",
)
# "Do you store my medical info?" is a privacy question, not a medical one.
_PRIVACY = (
    r"stor(e|ed|ing)", r"sav(e|ed|ing)", r"log(s|ged|ging)?", r"privacy", r"private",
    r"my data", r"my info\w*", r"(medical|health) (info\w*|data|details)", r"share(d)?",
    r"sell", r"sold",
)


def _matches(patterns, q: str) -> bool:
    return any(re.search(r"(?<![a-z0-9])" + p + r"(?![a-z0-9])", q) for p in patterns)


def classify_query(query: str) -> str:
    """'emergency' | 'safety' | 'explain'."""
    q = query.lower()
    if _matches(_EMERGENCY, q):
        return "emergency"
    if _matches(_SAFETY, q) and not _matches(_PRIVACY, q):
        return "safety"
    return "explain"


# --- tools -----------------------------------------------------------------------

def search_explanations(query: str, k: int = 3) -> dict:
    if not isinstance(query, str) or not query.strip():
        return {"error": "query must be a non-empty string"}
    if len(query) > MAX_QUERY_CHARS:
        return {"error": f"query must be at most {MAX_QUERY_CHARS} characters"}
    try:
        k = max(1, min(int(k), 5))
    except (TypeError, ValueError):
        k = 3
    kind = classify_query(query)
    if kind == "emergency":
        return {
            "results": [], "source": "approved_text", "use_tool": "get_prep",
            "emergency": True,
            "note": ("This may be an emergency. Reply with the chat's fixed 911 text and the "
                     "call-back offer (safety_flag = true). Do not answer from explanations."),
        }
    if kind == "safety":
        return {
            "results": [], "source": "approved_text", "use_tool": "get_prep",
            "note": ("Safety and medical questions are answered only with the fixed text "
                     "from get_prep. Call get_prep and quote it; do not write your own advice."),
        }
    hits = retriever.search(query, k=k)
    out = {
        "results": [{"id": h["id"], "title": h["title"], "text": h["text"]} for h in hits],
        "source": "approved_text",
        "note": NOTE,
    }
    if not hits:
        out["note"] = ("No approved explanation matches. Say you don't have that information, "
                       "or use another tool. " + NOTE)
    return out


def get_line_history(home_id: str, t: float = 0) -> dict:
    return history.get_line_history(home_id, t)


TOOLS: list[dict] = [
    {
        "name": "search_explanations",
        "description": (
            "Search approved plain-language explanations of how this app works: what the risk "
            "band and confidence mean, how the restoration range is estimated and why it can "
            "change, why neighbors may get power back first, the "
            "labels on numbers, data sources, privacy and what data is missing. Use it for "
            "'how does this work', 'why' and 'how sure are you' questions. "
            "Answer only from the returned text and do not add numbers that are not in it. "
            "Not for safety or medical advice: if it returns use_tool, follow it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The customer's question in their own words.",
                    "maxLength": MAX_QUERY_CHARS,
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_line_history",
        "description": (
            "Counts of past storm damage on the power line that serves this customer's home "
            "(by storm, most common damage types, access issues, typical repair days) and the "
            "same counts for a group of similar lines. Only damage reported before the current "
            "storm-clock time. Use it when the customer asks how often their line was damaged, "
            "what usually breaks, or how long repairs took before. The home is chosen by the "
            "server; take no arguments."
        ),
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
]
RAG_TOOL_NAMES = frozenset(t["name"] for t in TOOLS)


def run_tool(name: str, tool_input: dict, ctx: dict) -> dict:
    """Dispatch a tool call. ctx = {"home_id", "t"} from the chat request. Never raises."""
    try:
        tool_input = tool_input if isinstance(tool_input, dict) else {}
        ctx = ctx if isinstance(ctx, dict) else {}
        if name == "search_explanations":
            return search_explanations(tool_input.get("query"))
        if name == "get_line_history":
            t = ctx.get("t", 0)
            t = 0.0 if t is None else float(t)
            if not math.isfinite(t):
                return {"error": "invalid t"}
            return get_line_history(ctx.get("home_id"), t)
        return {"error": f"unknown tool: {name}"}
    except UnknownHome:
        return {"error": "unknown home"}
    except (TypeError, ValueError):
        return {"error": "invalid input"}
    except Exception:  # noqa: BLE001 - the chat must keep going; Lane D logs tool errors
        return {"error": "tool failed"}
