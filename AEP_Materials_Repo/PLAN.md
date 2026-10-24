# AEP Outage Concierge: MVP Plan (Hack/OHIO 2026)

## Goal
Hack/OHIO 2026 build for AEP (utility) using the provided datasets below. Customer-facing storm assistant: risk band, restoration range, prep guidance, alert eligibility, proactive messages. Judges have no formal rubric: aim for wow plus utility fit. Prefer a focused, honest prototype over breadth.

## Data reality (checked)
- **ARCOS damage**: 1,659 records, one region (APCO), 85 circuits, 29 substations. About 85% of rows come from two storms (Feb 2025, Sep 2024). Fields: asset type, damage type, Access_Issue (about 32% yes), special equipment, lat/lon, report date, repaired date (day-granular, median 1 day, long junk tail). Event/District/Crew are empty. No weather, no "no outage" negatives.
- **Customers**: 117,642 premises with circuit_id, overhead/underground flag, 113 life-support flags. Addresses exist and must never be shown.
- **Topology** (`matched_upstream.txt`): premise -> upstream chain (transformer -> reclosers -> fuse -> breaker). Essentially all premises join to customers.
- **GIS**: poles, lines, transformers, fuses, switches, reclosers, hospitals, fire, ambulance.
- **Labor xlsx**: install/remove hours per construction unit, access adders (+0.5h), one Indirect Labor Multiplier = 4.5.
- **Joins**: ARCOS `CIR60` = GIS `aep_circui` `CIR60` = customer `circuit_id` `0000060`. Customers join topology on premise number.

## Honest-modeling rules (say these first in the demo)
- Risk is a **historical damage-density index** shown as a band (Low/Med/High) with confidence. Never show a percent.
- Restoration = labor hours x 4.5 x access delay, Monte Carlo (labor hours from the Labor xlsx, per damage count), shown as a P10-P90 range. Winsorize observed ARCOS repair days at P95 (used to calibrate the access delay). Do not claim "validated".
- Every output is labeled **Model estimate**, never a promise; the outage map layer is also labeled "Simulated" (no real outage data).

## MVP (must work end to end)
1. Pick an anonymized location (map click or dropdown).
2. Risk band + confidence + one-line reason + topology path (You -> Transformer -> Recloser -> Breaker).
3. Restoration range chart, with sliders for damage count, crews, and access blocked. Formula visible.
4. Prep checklist matched to expected duration. Red SAFETY labels. "Declared needs" toggle (user-declared only, never inferred).
5. Alert eligibility (rules table, with reason) + 4 template messages: pre-storm, outage confirmed, estimate updated, restored. Optional LLM "rephrase" button with template fallback.
6. Trust card: confidence, assumptions, missing data, what would change the answer. "Can't predict reliably" fallback demoed on one weak-data circuit.
7. Two map layers only: **Risk band** and **Simulated outage**, aggregated at circuit or hex level (circuit is simpler).

## Wow (build if time allows, in this order)
1. **Blast radius**: click a device to see premises, life-support count, and critical-site count affected (counts only).
2. **Repair-order toggle**: "repair this first vs. that": customers restored vs. hours changes live.
3. Scripted 20-second Feb 2025 replay (not a general crew sim).

## Cut
Operator console, additional map layers (GIS assets, hospitals), live LLM dependence, per-premise display, address display, LLM message validator.

## Privacy and safety
No addresses. No individual premise points on the map. Minimum counts per aggregated cell. Life-support and critical sites shown as counts only. No employee contacts or internal fields. Safety messages visually distinct. Fallback sends users to the official AEP outage page.

## Front end (one page, Python, Streamlit + pydeck/folium)
```
┌──────────────────────────────────────────────────────────────┐
│ AEP Outage Concierge          [Storm severity ▓▓▓░]          │
├───────────────────────────┬──────────────────────────────────┤
│ MAP  [Risk][Simulated out]│ YOUR FORECAST                    │
│ circuit/hex shading       │ Risk: HIGH   Confidence: Med     │
│ click area -> detail      │ "Main line damaged in past       │
│                           │  storms." You>Xfmr>Recloser>Brkr │
│                           │ RESTORATION (model estimate)     │
│                           │ 6-18 hrs [fan chart]             │
│                           │ Damage ▓▓░  Crews ▓░░  Access ░  │
├───────────────────────────┴──────────────────────────────────┤
│ Tabs: What to do | Alerts & Messages | How sure are we?      │
└──────────────────────────────────────────────────────────────┘
Every panel carries a label: CONFIRMED FACT | MODEL ESTIMATE | YOUR ACTIONS
```

## Design choices
- Single page, no navigation. Sliders drive map, range, checklist, and messages together so judges see everything change at once.
- Plain language, large type, high contrast, color plus text for risk (not color alone). Red reserved for SAFETY.
- Ranges, never exact times. "Estimate, not a promise" wording everywhere.
- Code computes all numbers. Templates write messages. The LLM is optional wording only.
- Precompute per-device and per-circuit aggregates offline so the app stays fast (117k premises will lag otherwise).

## Build order (matches MVP items; Wow items last)
1. Preprocess: join circuits, topology chain, per-device premise/life-support counts, per-circuit damage index.
2. Restoration Monte Carlo + sliders.
3. Eligibility table + message templates + checklist.
4. Trust card + fallback.
5. Map layers.
6. Wow items 1-3 (as time allows).

## Closing slide
"What we'd need next": weather feeds, AMI/meter pings, true ETR history, multi-region damage data.
