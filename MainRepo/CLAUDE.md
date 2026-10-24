# Rules for every Claude working in this repo

Read `MASTER_PLAN.md` (the plan) and `contracts/API.md` (API shapes, Python interfaces, DB additions) first.
Lanes A and B: also read `docs/DATA_FACTS.md`. Ignore `docs/plan-archive/` (superseded). Rohit's Phase 1 code in `ingest/` is kept.

1. **Stay in your lane.** Only edit the folders your lane owns (MASTER_PLAN §5). Need a change elsewhere? Tell your human exactly what and why. Exception: any lane may add its own tests as `tests/test_<lane>_*.py`.
2. **The contract is law.** Responses match `contracts/mocks/*.json`; Python functions match `contracts/API.md` §5. Add fields freely, never rename/remove without team agreement. Contract edits update `API.md` and the mock in the same commit.
3. **Stubs first.** In your first hour, commit stubs with the exact signatures that return the mock JSON, so other lanes' imports work.
4. **Numbers come from code.** The LLM never invents or changes a number. Safety and medical text are fixed strings, never generated.
5. **Privacy.** Never output raw premise numbers, addresses, road names, house numbers, coordinates finer than a ~1 km cell, device/circuit ids, crew info, hospital/fire/ambulance locations, or life-support flags (`is_critical_tier`).
6. **Honesty labels.** Every number shown carries a `source`: `model_estimate`, `simulated_feed`, `utility_confirmed`, or `fixed_guidance` (chat: `llm` / `fallback`). Risk is a band, never a percent. Restoration is a range, never a single time.
7. **Deterministic.** Fixed seeds from `app/config.py`. Same shared salt on every machine (`.env`).
8. **Raw data is read-only** (`aep-challenge/` submodule). Never commit raw customer data, the `.db`, or `.env`.
9. **Simple beats clever.** Working end to end first. No new dependencies without need (`requirements.txt` is owned by Lane D).
10. **Claude API (chat):** never send `temperature`/`top_p`/`top_k`, never force `tool_choice` (both return 400). Use `tool_choice: auto`.

Run everything from the repo root:
- Setup: `git submodule update --init` · copy `.env.example` → `.env` · `pip install -r requirements.txt`
- Build DB: `python -m ingest.build_db` → `data/outage_concierge.db`
- Backend: `uvicorn app.main:app --reload --port 8000`
- Tests: `pytest`
- Frontend: `cd frontend && npm install && npm run dev` (http://localhost:5173)
