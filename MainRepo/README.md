# AI Outage Concierge (Hack/OHIO 2026, AEP challenge)

Start with [MASTER_PLAN.md](MASTER_PLAN.md). API shapes: [contracts/API.md](contracts/API.md). Rules for AI assistants: [CLAUDE.md](CLAUDE.md). Q&A prep: [video/QA.md](video/QA.md).

## Run the demo

```bash
./run_demo.sh                 # builds DB + frontend if missing, serves http://localhost:8000/?demo=1
```

Or step by step (repo root):

```bash
python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
cp .env.example .env           # set CONCIERGE_SALT to the team's shared salt
python -m ingest.build_db      # ~7 s -> data/outage_concierge.db
python -m ingest.find_story_home   # only if your salt differs from the one demo_homes.json was built with
uvicorn app.main:app --port 8000
cd frontend && npm install && npm run dev    # http://localhost:5173/?demo=1  (or npm run build -> served on :8000)
pytest                          # 219 tests
```

Optional: `GEMINI_API_KEY` in `.env` turns on the LLM chat layer. Without it, chat uses template answers built from the same tool outputs.

## Demo script (story home, demo panel "Jump to")

Jump buttons land just after each event; the event times are in parentheses.

| Moment | Clock | What happens |
|---|---|---|
| Storm forecast | Wed 6:00 AM (t = -18) | Storm alert push, HIGH risk, 3 reasons, prep list |
| Your power goes out | Thu 3:48 AM (out at 3:41) | "We know your power is out", back in about 4-12 h (Thu 8 AM to 4 PM), SAFETY line, map dark |
| Estimate updated | Thu 9:36 AM (report at 9:29) | New damage on her line: "about 6 hours longer"; card shows back about Thu 2 PM to 9 PM; "What could change this?": roads blocked +5 h, more damage +7 h, more crews won't help |
| Power restored | Thu 7:24 PM (back at 7:16) | "Power is back" + recap: first range early, updated range caught it |

Also: chat ("my insulin is in the fridge"), battery slider below 20% (low-power mode), "Home with little history" (fallback), map tap to pick any area.

## Who built what

| Lane | Folder | Status |
|---|---|---|
| A Data + feed | `ingest/`, `app/sim/` | Built at integration: crosswalk fix, shared salt, DB enrichment, truth feed, map cells, locate, scenario, demo homes, `/api/home`, `/api/repairs` |
| B Models | `app/models/`, `app/rag/` | lane-b: risk model, restoration Monte Carlo, RAG tools |
| C Frontend | `frontend/` | Built at integration from `docs/design/` |
| D Shell, chat, guidance | `app/main.py`, `app/chat/`, `app/guidance/` | lane-d: shell + chat; prep, alerts, audit, privacy and story tests added at integration |
