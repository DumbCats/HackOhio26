# Contract (the law)

Every lane builds against this file and `contracts/mocks/*.json`.
**Changing it?** Update this file **and** the matching mock in one commit, then tell the team. Add fields freely; never rename or remove one without agreement.

## 1. Basics

- Backend `http://localhost:8000`, frontend `http://localhost:5173` (CORS allowed). JSON everywhere.
- **Storm clock `t`**: hours since 2025-02-13 00:00 (MASTER_PLAN A1). Demo range `-24` to `96`.
- Deterministic: replay seed `8`, Monte Carlo seed `42` (in `app/config.py`).
- Unknown `home_id` → HTTP 404 `{"detail": "unknown home"}`.
- `home_id` = Rohit's `premise_key`: `p_` + 16 hex (salted SHA-256 of the premise number, shared salt). `cell_id` = opaque `c_0001` style. Never coordinates finer than a ~1 km cell, never device or circuit ids in any response.

## 2. Query params (shared)

| Param | Type | Default | Meaning |
|---|---|---|---|
| `t` | float | 0 | Storm-clock hour |
| `severity` | float 0-1 | 0.8 | Storm strength (simulated) |
| `crews` | int 1-30 | null → this line's share of 150 regional crews | Crews on your line |
| `access_blocked` | bool | false | Roads blocked by ice/trees |
| `extra_damage` | int 0-10 | 0 | What-if: extra damage on your path |
| `switching` | bool | true | Network assumption: crews can reroute power around damage (off = wait for every repair on your line) |
| `needs` | csv | "" | `medical_device,refrigerated_meds,mobility,well_water,critical_facility` |
| `low_power` | bool | false | Phone in low-power mode (affects channels) |

## 3. Endpoints

| Route | Owner | Python function | Mock(s) |
|---|---|---|---|
| `GET /api/scenario` | A | `app.sim.scenario.get_scenario()` | `scenario.json` |
| `GET /api/locate?lat=&lon=` | A | `app.sim.locate.locate(lat, lon)` | `locate.json` |
| `GET /api/outage-map?t=&severity=` | A | `app.sim.mapcells.get_outage_map(t, severity)` | `outage_map.json` |
| `GET /api/forecast/{home_id}?t=&severity=` | B | `app.models.risk.get_forecast(...)` | `forecast.json`, `forecast_fallback.json` |
| `GET /api/restoration/{home_id}?t=&crews=&access_blocked=&extra_damage=&switching=` | B | `app.models.restoration.get_restoration(...)` | `restoration_not_out.json`, `restoration.json`, `restoration_restored.json` |
| `GET /api/prep/{home_id}?t=&needs=` + scenario params | D | `app.guidance.prep.get_prep(...)` | `prep.json` |
| `GET /api/alerts/{home_id}?t=&needs=&low_power=` + scenario params | D | `app.guidance.alerts.get_alerts(...)` | `alerts.json` |
| `POST /api/chat` | D | `app.chat.service.chat(req)` | `chat_request.json` → `chat_response.json` |
| `GET /api/home/{home_id}` | A | `app.sim.home.get_home(home_id)` | (added at integration) area label, ~1 km cell `center`, `customers_on_line` ("about 900"), `network_match` |
| `GET /api/repairs/{home_id}?t=` | A | `app.sim.home.get_repairs(home_id, t)` | (added at integration) repairs on the home's path known at `t`, in repair order: `{order, label, status: done\|in_progress\|waiting, center, reported_t}` |
| `GET /api/health` | D | | real routers mounted, DB present, LLM key present |

**Which card to show (frontend rule):** call `restoration` first.
1. `restored_at_t != null` and `t >= restored_at_t` → **Power is back** card (with `recap`).
2. Else `is_out` → **Mode 2** "When is it back?".
3. Else → **Mode 1** "Will I lose power?" (`forecast`).

**Mock server rule (D's `app/mock_routes.py`):** forecast → `forecast_fallback.json` for the fallback home id, else `forecast.json`. Restoration → `t < 4.3` not_out, `t >= 18.4` restored, else `restoration.json`. Alerts → timeline filtered to `t ≤ query t`.

**Added at integration (fields only, nothing renamed):** `scenario.homes[].role` (`story|second|fallback`) and `.area`; `prep.phase` (`before|during|after`) and `prep.why`; `alerts.eligibility_summary`, `alerts.rules[]` (`rule_id, name, fired`), `alerts.timeline[].rule_id`, `alerts.escalations[].active`; `restoration.drivers[].active`. Chat returns 404 for an unknown home.

## 4. Shared response fields

Every model/guidance response has:
```json
"source": "model_estimate | simulated_feed | utility_confirmed | fixed_guidance",
"assumptions": ["…"],
"missing_data": ["…"],
"what_would_change": ["…"],
"fallback": null | {"reason": "…", "message": "…", "link": "https://www.appalachianpower.com/outages/"}
```
UI labels: `model_estimate` → "Our estimate", `simulated_feed` → "Simulated utility feed", `utility_confirmed` → "Utility confirmed", `fixed_guidance` → "Safety guidance". Chat: `source` = `llm | fallback`.

Field notes: `band` = `low|medium|high|unknown`, never a percent. `confidence` = `low|medium|high`. `estimate.p10_h/p50_h/p90_h` = hours from `t`. `chance_back_by[].prob` = cumulative 0-1 for the curve. `status.stage` = `assessing|crew_assigned|repairing|restored`. `outage_map.cells[].status`: `out` if ≥ 50% of homes out, `partial` if any, else `on`; cells with < 10 homes are omitted. **First estimate** (used by the outage-confirmed alert and the recap) = `get_restoration(home_id, t=out_since_t)`; **updated estimate** = the one at the R3 moment. `chat_response.safety_flag` = true when the user describes an emergency; the reply is then the fixed 911 text + call-back offer.

## 5. Python interfaces (stub these in hour 1, returning mock JSON)

All imports are from the repo root (`pytest.ini`: `pythonpath = .`).

```python
# D  app/config.py
REPO_ROOT: Path
DB_PATH: Path            # env CONCIERGE_DB, default REPO_ROOT/"data/outage_concierge.db"
ANTHROPIC_API_KEY: str | None
REPLAY_SEED = 8; MC_SEED = 42; REGIONAL_CREWS = 150; DEFAULT_SEVERITY = 0.8
# D  app/db.py
def get_conn() -> sqlite3.Connection          # row_factory=sqlite3.Row

# A  app/sim/labor.py
def job_base_hours(asset_type: str, access_issue: bool, special_equipment: str) -> float
    # workbook hours + adders, x4.5, no noise
# A  app/sim/schedule.py
def schedule(jobs: list[dict], crews: int) -> dict[str, tuple[float, float]]
    # jobs: {"job_id", "ready_t", "hours", "priority"}  (lower priority runs first)
    # returns job_id -> (start_t, finish_t). Each free crew takes the best ready job.
# A  app/sim/feed.py  (truth feed, computed once at startup)
def home_info(home_id: str) -> dict
    # {"circuit_id", "cell_id", "overhead": bool|None, "path_device_keys": [..], "circuit_crews": int}
    # path_device_keys == [] means no topology match (A6 fallback)
def home_state(home_id: str, t: float) -> dict
    # {"is_out", "out_since_t", "restored_at_t", "stage", "stage_updated_t"}
def known_jobs(circuit_id: str, t: float) -> list[dict]
    # reported by t, not fixed by t: {"job_id", "device_key", "base_hours",
    #  "remaining_frac" (1.0 if not started), "priority", "report_t"}
# A  app/sim/mapcells.py · scenario.py · locate.py
def get_outage_map(t: float, severity: float = 0.8) -> dict
def get_scenario() -> dict
def locate(lat: float, lon: float) -> dict

# B  app/models/risk.py · restoration.py
def get_forecast(home_id: str, t: float = 0, severity: float = 0.8) -> dict
def get_band(home_id: str, severity: float = 0.8) -> str   # A's map: cell band = most common band of its homes
def get_restoration(home_id: str, t: float = 0, crews: int | None = None,
                    access_blocked: bool = False, extra_damage: int = 0,
                    switching: bool = True) -> dict

# D  app/guidance/prep.py · alerts.py · app/chat/service.py
def get_prep(home_id: str, t: float = 0, needs: list[str] = [], **scenario) -> dict
def get_alerts(home_id: str, t: float = 0, needs: list[str] = [], low_power: bool = False, **scenario) -> dict
def chat(req: dict) -> dict
```
Each package exposes `router = APIRouter()` in `routes.py`. `app/main.py` (D) includes the real routers that import cleanly, then the mock router last.

## 6. Database `data/outage_concierge.db` (A builds; everyone builds locally with `python -m ingest.build_db`)

Base schema: Rohit's `ingest/schema.sql` (`premises`, `topology_edges`, `damage_events`, `circuits`, `labor_codes`, `labor_adders`, `priority_facilities`, `assets`, `metadata`). Lane A **adds**:

```sql
-- premises
ALTER: overhead INTEGER          -- from kind_of_se (1 overhead, 0 underground, NULL unknown)
ALTER: cell_id TEXT              -- ~1 km grid cell
-- topology_edges
ALTER: device_key TEXT           -- salted hash of the token's LOC field (not the 9-digit id)
-- damage_events  (circuit_id now converted via the crosswalk; non-CIR rows dropped)
ALTER: storm TEXT                -- 'feb2025' (Feb 13-18) | 'sep2024' | 'other'
ALTER: device_key TEXT           -- A2 mapping; NULL if unmapped
ALTER: report_t REAL             -- storm-clock hour (seeded hour within report day; feb2025 only)
ALTER: base_hours REAL           -- A3 before noise
ALTER: priority REAL             -- A4: lower = earlier
ALTER: homes_affected INTEGER
-- circuits
ALTER: past_damage INTEGER       -- damage rows before Feb 2025
ALTER: pct_overhead REAL
-- new
CREATE TABLE cells(cell_id TEXT PRIMARY KEY, lat_c REAL, lon_c REAL, bounds_json TEXT,
                   homes INTEGER, visible INTEGER);   -- visible = homes >= 10
```
`circuit_id` (7-digit) and every coordinate stay inside the backend. `data/demo_homes.json` (story/second/fallback ids + labels) is committed.
