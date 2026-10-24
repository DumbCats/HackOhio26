# MASTER PLAN: AI Outage Concierge (Hack/OHIO 2026, AEP challenge)

> **Single source of truth.** Old plans in `docs/plan-archive/` are superseded; don't build from them. Rohit's Phase 1 code in `ingest/` is **kept** and extended.
> API shapes + Python interfaces + DB additions: [`contracts/API.md`](contracts/API.md) and [`contracts/mocks/`](contracts/mocks/).
> Verified data facts (field names, joins, traps): [`docs/DATA_FACTS.md`](docs/DATA_FACTS.md).
> Tiers: **CORE** = the story breaks without it · **NEEDED** = the brief requires it or judges will ask · **NICE** = wow, only after CORE + NEEDED work end to end.

---

## 1. The pitch

A storm is coming. Then the lights go out. You grab your phone, worried.
The app takes you from **worry to comfort**: *will I lose power → it's out, when is it back → what do I do → it's back.*
Every number comes from real AEP data run through our code. The AI only talks.

Deliverable: **3-min video** (recorded in a phone-sized browser) + **6-min Q&A** with AEP engineers.

## 2. The story = the demo = the requirements

Persona **Maya**. Her line was hit in the real Feb 2025 storm. She told the app she keeps insulin in the fridge.
Story times come from the data: A picks the home so these beats happen, and `tests/test_story.py` proves it. The planning prototype found a home that does exactly this: out at t≈4.3, a second damage report at t≈9.5 pushes the estimate about 7 h later, back at t≈18.4.

| Beat | `t` | What Maya sees | Proves |
|---|---|---|---|
| 1 Forecast | -18 | Push: "Storm tomorrow. Your area is HIGH risk compared with nearby homes." **Mode 1** card: band, confidence, why. Prep list incl. insulin tip. | Risk band, factors, uncertainty, prep, pre-storm alert |
| 2 Lights out | outage +0.5 | "We know your power is out." **Mode 2**: "Likely back in X-Y h", status tracker, red SAFETY card, map shows her area dark. | Outage message, restoration range, safety |
| 3 Panic chat | +1 | "my insulin is in the fridge, what do I do??" Calm, specific answer. | AI assistant, declared needs |
| 4 Battery 18% | +2 | Low-power mode: dark, text only, essentials. | Accessibility, real outage conditions |
| 5 Estimate moves | 2nd report | New damage found upstream → range jumps → "estimate updated" SMS. She taps **What could change this?**: roads blocked (about +6 h), +2 crews (about −1-2 h), switching off. | Scenario inputs, estimate-updated message |
| 6 Comfort | restored | "Power's back." Recap: our range vs what happened. | Restored message, honesty |
| 7 Honesty | any | "How sure are we?" sheet; a no-history home shows the fallback. | Confidence, assumptions, fallback, privacy |

## 3. Real vs simulated (say it proudly in Q&A)

| Thing | Real? | How |
|---|---|---|
| Past damage: where, what broke, access issues | **Yes** (ARCOS, 1,659 rows) | Direct |
| Homes, circuit, overhead/underground | **Yes** (117,642 premises) | Hashed ids, ~1 km cells, no addresses |
| Equipment feeding each home | **Yes** (`matched_upstream.txt`) | Direct |
| Repair labor hours | **Yes** (workbook, ×4.5) | Direct |
| Live outage feed | **No** | **Simulated**: replay real Feb 2025 damage on a clock through the real network |
| Crew status | **No** (crew fields empty) | Simulated stage only. Never names, locations, ids |
| Weather / forecast | **No** | Severity slider |
| Repair times | **Dates only** | Hours from labor table; dates used to calibrate crews |
| Utility-confirmed restore time | **No** | Slot exists (`utility_etr`), always empty in the demo |

## 4. Assumptions (cite by number)

- **A1 Clock.** `t` = hours since 2025-02-13 00:00. Replay damage reported Feb 13-18 2025 (about 1,229 rows). Each row gets a seeded random hour within its report day. One fixed replay seed for the whole demo.
- **A2 Outages.** A damaged device knocks out every home whose upstream path contains it, from report until fixed. Mapping (99% of rows map, `DATA_FACTS.md` §4): Fuse/Recloser → nearest same-circuit fuse/recloser; Transformer/secondary → nearest same-circuit transformer; primary/Pole/Switch/other → nearest same-circuit transformer, then its first upstream isolating device. About 26,000 homes go out.
- **A3 Job hours.** Per-asset install + remove hours (`DATA_FACTS.md` §7: Pole 4.8, wire 1.1, Fuse 1.2, …) + adders (access issue +0.5, Backyard Bucket +0.5, Track Hoe/Yard Dog +1.3), all **×4.5** (workbook's Indirect Labor Multiplier). Noise: lognormal σ = 0.35. Wire/capacitor/light hours are proxies (no workbook unit).
- **A4 Crews.** One regional pool, default **150 crews**, split across circuits by expected repair hours (min 1 per circuit). Calibrated: the replay fixes 38/38/16/7% of jobs in 0/1/2/3+ days vs real ARCOS 39/33/18/10%. On each circuit, jobs run in priority order: closest to the substation first, then most homes.
- **A5 Risk band.** Score from damage in storms **before** the replayed one (no peeking at Feb 2025), overhead share, and path length, × severity. Cutoffs fixed once at severity 0.8 (top 15% of homes High, next 25% Medium); then `score × severity` is compared to those cutoffs, so the slider moves the band. Never a percent; always "compared with nearby homes".
- **A6 Confidence.** High: circuit has ≥ 3 past damage rows and a topology match. Low: < 3 rows (band still shown with a "limited history" note). **Fallback** (no band, link to the official outage page): 0 past rows on the circuit, or no topology match.
- **A7 Alerts.** Rules, timing, and channels are our documented assumptions, not AEP policy.
- **A8 Declared needs.** Only from the user's own toggles. Sent with each request to tailor guidance; never stored or logged. Utility life-support flags (`is_critical_tier`) are never used for a person and never shown.
- **A9 Duration stats.** Drop the 76 `Repaired = No` rows and the 138 rows with `Repaired_D = 2024-10-22` (bulk close-out) from duration stats only.
- **A10 Region.** One region (APCO, around Roanoke VA), two big storms. We don't claim more.
- **A11 Chat.** Claude API (needs an API key with credits from console.anthropic.com; Claude Pro does **not** include API access). No key or no internet → canned answers built from the same tool outputs.
- **A12 Circuit ids.** ARCOS `CIRnn` is **not** simply `nn` zero-padded. Convert with `ingest/circuit_crosswalk.json` (7-digit id → `CIRnn`; ids 2-11 and 13-16 differ). Drop the 14 ARCOS rows whose `Circuit` isn't `CIRnn`.
- **A13 Truth vs estimate.** The simulated feed (truth) is one fixed run using **all** damage. The customer's estimate (Monte Carlo) only knows damage **reported by `t`**, and in-progress jobs keep only their remaining time. That gap is what makes "estimate updated" real. Sliders change the estimate, never the feed.

## 5. Stack + repo layout

**Stack:** Python 3.12+, FastAPI, NumPy, SQLite (Rohit's research + Phase 1) · React + Vite + TypeScript + Leaflet, plain CSS · Claude API.

```
MASTER_PLAN.md  CLAUDE.md  .env.example  requirements.txt  pytest.ini   ← D
contracts/  (API.md, mocks/)                    ← D (changes announced to the team)
docs/DATA_FACTS.md, docs/prototype/ (reference) ← A
aep-challenge/   raw data submodule, read-only (git submodule update --init)
ingest/          Rohit's Phase 1 pipeline + circuit_crosswalk.json   ← A
data/outage_concierge.db   built locally by everyone, gitignored
app/main.py, app/config.py, app/db.py, app/mock_routes.py           ← D
app/sim/        labor, schedule, feed, mapcells, scenario, locate   ← A
app/models/     risk, restoration (Monte Carlo)                     ← B
app/guidance/   prep, alerts, messages                              ← D
app/chat/       LLM chat + fallback                                 ← D
tests/          test_ingestion.py (A), test_<lane>_*.py (each lane), test_story.py (D)
frontend/                                                           ← C
video/          script, shot list, QA.md                            ← D (all help)
```

Everything Python runs from the **repo root**: `python -m ingest.build_db`, `uvicorn app.main:app`, `pytest`.

**Golden rules:** only edit your own folders. Build against the mocks. In its first hour, each lane commits **stubs with the exact Python signatures in `contracts/API.md`** that return the mock JSON, so imports never break.

## 6. Feature tiers

### CORE
- [ ] **C1** Pipeline fixes + additions (§7 A) so the DB has correct circuits, device keys, damage → device, cells, overhead flag. *(A)*
- [ ] **C2** Simulated feed: storm clock, scheduler, per-home state, map cells. *(A)*
- [ ] **C3** Mode 1 forecast: band, confidence, 3 plain-English factors. *(B)*
- [ ] **C4** Mode 2 restoration: Monte Carlo P10-P90 + curve + status stage. *(B)*
- [ ] **C5** Phone UI: home picker / map tap, summary card that auto-switches Mode 1 → Mode 2 → "Power is back", map, demo panel (clock scrubber, jump-to-moment, severity, battery). *(C)*
- [ ] **C6** Free-form chat; every number comes from a tool. *(D)*
- [ ] **C7** Fixed SAFETY card + emergency line, always visible during an outage. *(D text, C UI)*
- [ ] **C8** The 4 messages appear as notifications when the clock passes them. *(D, C)*
- [ ] **C9** `tests/test_story.py` passes (§7 D). *(D; A picks the homes)*

### NEEDED
- [ ] **N1** Alert eligibility with the rule that fired, channel, timing, escalation. *(D)*
- [ ] **N2** Declared needs: medical device, refrigerated medicine, mobility, well water, **critical facility** ("I run a clinic, shelter, or care home") → tailored prep + escalation. *(D, C)*
- [ ] **N3** "How sure are we?" sheet: confidence, assumptions, missing data, what would change it. Label chip on every number: `Our estimate` / `Simulated utility feed` / `Utility confirmed` (empty in the demo). *(B data, C UI)*
- [ ] **N4** Fallback home: "We can't predict this reliably" + official outage page link. *(B, C)*
- [ ] **N5** Low-power mode: dark, text only, no map, no animation; shows status, range, confidence, one next step, safety line. *(C)*
- [ ] **N6** Step restoration line: "Repairs happen in steps; some neighbors may get power back before you." *(B)*
- [ ] **N7** Customer-facing **"What could change this?"** card in Mode 2 with crews, roads blocked, switching toggles (the brief wants customers, not just judges, to explore). *(C, B)*
- [ ] **N8** Network assumption: `switching` toggle. On (default) = only your path's repairs matter. Off = you wait for every repair on your line. *(B)*
- [ ] **N9** Prep checklist by duration bucket: < 4 h, 4-24 h, 24-72 h, 72 h+. *(D)*
- [ ] **N10** Privacy test: no endpoint returns raw premise numbers, coordinates finer than a cell, device/circuit ids, crew info, facility locations, or life-support data. *(D)*
- [ ] **N11** Audit log: every API response and chat turn appends to `logs/audit.jsonl` (endpoint, params minus needs, `source`, seed, tools used). No chat text, no needs. *(D)*
- [ ] **N12** Chat guardrails: validate input (home_id format, ≤ 1,000 chars); emergency words → fixed 911 text + "request a call back" offer (`safety_flag = true`); number check (every number in the reply must appear in tool output, else send the template answer). *(D)*
- [ ] **N13** Backtest number for Q&A: rank by pre-Feb damage, score on Feb 2025 (prototype: the High band held about 2.5× its share of later damage). *(B)*

### NICE (in order)
**W1** lock-screen notification animation (C) · **W2** auto low-power when battery < 20% via `navigator.getBattery` (C) · **W3** learned risk model trained on replay outages, checked on Sept 2024 (B) · **W4** "why it changed" estimate timeline (B, C) · **W5** neighborhood pulse counts (A, C) · **W6** emergency-facility awareness: "lines serving emergency services are repaired first", counts only (A) · **W7** "what's being fixed" card from the structure drawings (D) · **W8** Spanish / simple-language toggle (D, C).

### OUT
Operator console, real SMS/push, accounts, live weather, house-level map points, native app.

## 7. Lane specs

One branch per lane (`lane-a` … `lane-d`). Merge to `main` small and often; run `pytest` (repo root) before merging. Setup for everyone: `git submodule update --init`, copy `.env.example` → `.env` with the team's shared salt, `pip install -r requirements.txt`, `python -m ingest.build_db`.

### Lane A: Data + simulated feed (`ingest/`, `app/sim/`, `docs/DATA_FACTS.md`, `tests/test_ingestion.py`)
1. **Read `docs/DATA_FACTS.md`.** Borrow from `docs/prototype/`. Keep Rohit's pipeline; fix and extend it:
   - **Circuit bug:** `normalize_circuit_id('CIR10')` → `'0000010'` is wrong for ids 2-16. Map ARCOS `CIRnn` through `ingest/circuit_crosswalk.json` (A12); drop non-`CIR` rows.
   - **Shared salt:** `PremiseHasher` must read `CONCIERGE_SALT` from `.env` first (same salt on every machine → same home ids in `demo_homes.json`). Hash device keys with it too.
   - **Device keys:** use the topology token's 4th field (**LOC**, = `location_n` in device layers), not the 9-digit id (recloser ids match 0%).
   - **Add** the DB columns/tables in `contracts/API.md` §6: damage → device key (A2), seeded `report_t`, `base_hours` (A3), `priority`, `storm`; premise `overhead` (`kind_of_se`), `cell_id`; `cells`; circuit `past_damage`, `pct_overhead`.
   - Coordinates and `is_critical_tier` may stay in the local DB but **never** leave `app/` in a response.
2. `app/sim/`: `labor.job_base_hours`, `schedule.schedule`, `feed.*`, `mapcells.get_outage_map`, `scenario.get_scenario`, `locate.locate`, with the signatures in `contracts/API.md`. Run the truth feed once at startup with the fixed seed (A1, A3, A4, A13) and cache it.
3. `ingest/find_story_home.py` picks 3 homes: (a) story home: High band at t=-18, out at t≈2-6, a second path job reported a few hours later, back 10-20 h after the outage; (b) a normal second home; (c) a fallback home (0 past rows). Write ids + hand-written labels to `data/demo_homes.json` (**committed**; add a `.gitignore` exception). Story moments in `/api/scenario` are computed from the feed, never typed in.
4. Update `tests/test_ingestion.py` for the new columns + "all ARCOS CIR circuits match a customer circuit".

### Lane B: Models (`app/models/`)
1. `risk.get_forecast` + `risk.get_band` per A5/A6: three plain-English factors, `rank_note`, `fallback` when A6 says so.
2. `restoration.get_restoration`: Monte Carlo, n = 1000, seed 42, < 300 ms.
   - Jobs = damage on the home's circuit reported by `t` and not yet fixed (A13), plus `extra_damage` synthetic jobs on the home's path. In-progress jobs keep only their remaining time.
   - Each sim: sample hours (A3 noise); `access_blocked` adds uniform 2-8 h per job; schedule with A's `schedule()` on `crews` (default = the circuit's share of 150).
   - Restore time = last job on the home's path (`switching = true`) or last job on the circuit (`false`).
   - Return P10/P50/P90 hours from `t`, the `chance_back_by` curve, confidence (Low if P90/P10 > 4 or A6 says Low), `drivers` (re-run with crews+2, access blocked, extra_damage+1, switching off), and step info.
   - Not out: `is_out = false`, `estimate = null`. Restored: `recap` (first estimate vs actual).
3. Sanity check against ARCOS days (A9); N13 backtest; W3 if time allows.

### Lane C: Phone frontend (`frontend/`)
1. Vite React TS. Always calls the backend at `VITE_API_BASE` (default `http://localhost:8000`). D's skeleton serves the mocks from hour 1, so no frontend mock mode is needed.
2. Phone frame (max-width 430 px, centered), big type, high contrast, color + text for every band. Red only for SAFETY.
3. Screens: home picker + map tap → **Summary card** (mode rule in `API.md`) → sheets: Map · Prepare · Alerts · Chat · How sure are we? · What could change this?
4. Every number shows its label chip from `source`.
5. Demo panel (`?demo=1` or long-press the header): clock scrubber, jump-to-moment buttons from `/api/scenario`, severity, battery level (frontend-only state), crews / roads / switching / extra damage. Everything refetches on change.
6. Notifications: when the clock passes a timeline message's `t` (from `/api/alerts`), slide in a banner.
7. Low-power mode (N5) toggle in the header; pass `low_power=true` to alerts and chat.

### Lane D: Shell, guidance, chat, integration, video
1. **Hour 1:** `requirements.txt` (fastapi, uvicorn, numpy, openpyxl, anthropic, python-dotenv, pytest, httpx), `pytest.ini` (`pythonpath = .`), `app/config.py`, `app/db.py`, `app/mock_routes.py` (serves the mocks, picking the restoration/forecast mock by `t` and `home_id`), `app/main.py` (mounts real routers when importable, mock router last; CORS for `http://localhost:5173`). Push immediately.
2. `app/guidance/prep.py`: fixed checklists by bucket (N9) + needs add-ons (N2). Before an outage, the bucket comes from the band (High → 24-72 h, Medium → 4-24 h, Low → < 4 h). Safety text = fixed strings in one file, reviewed once (start from `contracts/mocks/prep.json`).
3. `app/guidance/alerts.py`: R1 pre-storm if band ≥ Medium (at t = -18); R2 outage confirmed when `is_out` starts; R3 estimate updated when the absolute ETA (`t + p50_h`) moves > 3 h or > 25%; R4 restored. Channels: push by default; SMS when `low_power`; offer a call when a medical need or critical facility is declared and P90 > 12 h. The timeline returns only messages with `t ≤ query t`. Messages < 60 words, templated from B's numbers.
4. `app/chat/`: Claude API, model `claude-opus-5-5` (cheaper option: `claude-haiku-5-5`; team's call), `output_config.effort = "low"`, tools `get_forecast`, `get_restoration`, `get_prep`, `get_alerts` calling the same Python functions as the routes. **Don't send `temperature` / `top_p` / `top_k` (400 error) and don't force `tool_choice` (400); use `auto`.** Handle `stop_reason == "refusal"` → fallback answer. System prompt: calm, short, plain words, numbers only from tools, "estimate, not a promise", safety/medical wording quoted from `get_prep`, emergencies → 911, never reveal ids or internal data. N12 guardrails.
5. N10 privacy test, N11 audit log, `tests/test_story.py`:
   - t = -18: story home band High, not out.
   - Outage `t`: `is_out`, outage-confirmed message present.
   - Second-report `t`: R3 fires.
   - Restored `t`: the actual restore time falls inside the updated range (prototype: yes).
   - Fallback home returns `fallback`.
6. Integration: swap mocks for real routes as lanes land; run the full story after every merge. Video + `video/QA.md`.

## 8. Paste this into your Claude

```
Read CLAUDE.md, MASTER_PLAN.md, and contracts/API.md (Lane A/B: also docs/DATA_FACTS.md).
I own Lane __. First commit stubs with the exact Python signatures in contracts/API.md
that return the mock JSON. Then build my CORE items, then NEEDED, then NICE.
Only edit my lane's folders. If the contract must change, tell me exactly what and why
instead of changing it. Run pytest from the repo root before I merge. Show me how to run it.
```

## 9. Video

0:00 hook (dark room, phone glow) → beats 1-6 in the app → 2:30 one slide: real vs simulated + how it works → 2:50 close on comfort. Q&A prep: [`video/QA.md`](video/QA.md).
