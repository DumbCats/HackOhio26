# app/rag: retrieval tools for the chat (Lane B → Lane D)

Two extra Claude tools that go next to `get_forecast`, `get_restoration`, `get_prep` and `get_alerts`.
Nothing here calls the Claude API.

| Tool | What it returns | `source` |
|---|---|---|
| `search_explanations(query)` | Up to 3 approved passages `{id, title, text}` from `corpus.json` (BM25, deterministic). Safety/medical/emergency questions come back with **no passages** and `use_tool: "get_prep"` (plus `emergency: true` for emergencies). | `approved_text` |
| `get_line_history()` | Past-damage counts for the home's line: by storm, top damage types in plain words, "N of M" access issues, typical repair days, and a "lines like yours" group of 5 similar lines (added together, never named). Only damage reported before the storm-clock `t`. Counts under 3 say "not enough history". | `model_estimate` |

Repair times (dates only, whole days) are given as counts like "4 of 26 within 1 day, ... 22 of 26 took 3 or more days" (the same 0 / 1 / 2 / 3+ day split as MASTER_PLAN A4) plus the middle repair. Under 5 records with repair dates: "not enough history". 5-9 records: counts and the middle repair only. 10 or more: also "8 in 10 took between X and Y days" (P10-P90, never min/max). Every number in the text is also a field in `typical_repair`.

Why it works this way: numbers must come from code and safety text must be fixed strings (CLAUDE.md rules 4 and 5), so the model quotes a small approved corpus instead of writing its own explanations, and history is computed counts, never raw rows. Every number the model could repeat is literally in the tool output, so the N12 number check keeps working.

## Wiring it into the tool loop

```python
import json
import anthropic
from app.rag.tools import TOOLS as RAG_TOOLS, RAG_TOOL_NAMES, run_tool as run_rag_tool

client = anthropic.Anthropic()
tools = YOUR_TOOLS + RAG_TOOLS          # get_forecast, get_restoration, get_prep, get_alerts + ours
ctx = {"home_id": req["home_id"], "t": req.get("t", 0)}   # from the chat request, NOT from the model

messages = list(req["messages"])
while True:
    resp = client.messages.create(
        model="claude-opus-5-5",
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        tools=tools,
        tool_choice={"type": "auto"},     # never "any"/"tool" (400)
        output_config={"effort": "low"},
        messages=messages,
        # never temperature / top_p / top_k (400)
    )
    if resp.stop_reason == "refusal":
        return fallback_answer(...)
    if resp.stop_reason != "tool_use":
        break
    messages.append({"role": "assistant", "content": resp.content})
    results = []
    for block in resp.content:
        if block.type != "tool_use":
            continue
        if block.name in RAG_TOOL_NAMES:
            out = run_rag_tool(block.name, block.input, ctx)   # never raises
        else:
            out = run_your_tool(block.name, block.input, ctx)
        results.append({"type": "tool_result", "tool_use_id": block.id,
                        "content": json.dumps(out), "is_error": "error" in out})
    messages.append({"role": "user", "content": results})   # all results in ONE user message
```

- `ctx` always comes from the request. `get_line_history` has no inputs in its schema, and `run_tool` ignores any `home_id`/`t` the model sends, so the model can't look up another home.
- `run_tool` returns `{"error": "..."}` for an unknown tool, an unknown home, a bad `t`, or a query that is empty or over 500 characters.
- If `search_explanations` returns `use_tool: "get_prep"`, the model should call `get_prep` and quote it. With `emergency: true`, your N12 guard should already have sent the fixed 911 text. Treat the flag as a backup signal.
- For the number check, include the RAG tool outputs in the "tool output" text you compare the reply against.

## Suggested system-prompt lines

```
For "how does this work", "why", "how sure are you" or "is this real" questions, call
search_explanations and answer only from its results. Quote or paraphrase them; never add a
number that is not in a tool result. If it returns use_tool, call that tool instead.
For "how often does my line get damaged / how long did repairs take before", call
get_line_history. Never mention line, equipment or home ids.
```

## Files

- `corpus.json`: 53 passages. Each one has a `basis` field pointing to MASTER_PLAN / DATA_FACTS / API.md. To add one: keep it to 2-4 plain sentences, take the facts from those docs, put no safety or medical advice in it, no ids and no "%", then add a retrieval case in `tests/test_lane_b_rag.py`.
- `retriever.py`: BM25 (k1 1.5, b 0.75) over title, text and tags, with a light stemmer and a customer-phrasing synonym map. Below the score threshold it returns `[]`.
- `history.py`: `get_line_history(home_id, t=0)`. Uses `app.models.common.damage_history()` (corrected circuits). Per-circuit aggregates are cached per cutoff date.
- `tools.py`: `search_explanations`, `get_line_history`, `TOOLS`, `run_tool`, `classify_query`.

Test: `.venv/bin/python -m pytest tests/test_lane_b_rag.py -q`
