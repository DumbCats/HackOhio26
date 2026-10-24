# AI Outage Concierge (HackOHI/O 2026)

## What This Is

An AI-powered customer concierge that transforms complex electrical distribution data, geospatial network topologies, historical storm damage records, and operational restoration models into trusted, personalized, and explainable customer answers before, during, and after major storm events.

## Core Value

Empower customers with clear, grounded answers to the four core storm questions ("Will I lose power?", "How long?", "What should I do?", "Do I qualify for alerts?") while maintaining 100% operational realism and zero hallucination of mission-critical facts.

## Requirements

### Validated
(None yet — building towards initial verification)

### Active
- [ ] **REQ-01**: Multi-modal location entry (Anonymized Premise Key, Circuit ID, or Map Click).
- [ ] **REQ-02**: Outage risk prediction band (Low, Moderate, High) with explicit confidence indicator.
- [ ] **REQ-03**: Top contributing factors (3-5 plain-language reasons with directional impact).
- [ ] **REQ-04**: Explicit uncertainty communication and fallback handling for sparse data.
- [ ] **REQ-05**: Restoration time estimate as a credible range (P10 to P90 hours) rather than a false-precision point.
- [ ] **REQ-06**: Dynamic scenario updates when storm severity, crew count, or access constraints change.
- [ ] **REQ-07**: Network topology dependency reasoning (step-restoration order along isolating equipment chains).
- [ ] **REQ-08**: Clear distinction between model estimates and confirmed utility status.
- [ ] **REQ-09**: Personalized preparation checklist keyed to risk band and estimated outage duration.
- [ ] **REQ-10**: Prominent, uncollapsible safety and emergency callout (911 for downed lines/fire/injury).
- [ ] **REQ-11**: Declared-needs customization (medical equipment / accessibility) without inferring sensitive data.
- [ ] **REQ-12**: Transparent, rules-based alert eligibility showing the exact triggering rule.
- [ ] **REQ-13**: Proactive notification recommendations with timing, communication channel, and escalation triggers.
- [ ] **REQ-14**: Four plain-language message templates (<60 words) for key outage lifecycle milestones.
- [ ] **REQ-15**: Explainability without jargon or raw operational asset IDs.
- [ ] **REQ-16**: Assumptions panel disclosing parameters, multipliers, and "what would change this answer".
- [ ] **REQ-17**: Strict privacy boundary (salted SHA-256 premise hashing, allowlisted API fields, 1km rounding for sensitive sites).
- [ ] **REQ-18**: Low-confidence fallback advice path when data is inadequate.
- [ ] **REQ-19**: Interactive scenario controls allowing judges to perturb parameters in real time.
- [ ] **REQ-20**: Historical storm replay demonstrating actual damage patterns (Feb 2025 Winter Storm & Sept 2024 Helene Event).
- [ ] **REQ-21**: Operator escalation queue and human utility contact path.
- [ ] **REQ-22**: Chat turn audit log recording queries, matched tools, and outputs without storing PII.
- [ ] **REQ-23**: Structure drawings and CU labor category mapping (crossarms, poles, brackets, cutouts).
- [ ] **REQ-24**: Anti-hallucination number verification guardrail on LLM chat output.

### Out of Scope
- Real-time live SCADA integration (simulated via historical ARCOS and scenario inputs).
- Live weather radar API feeds (replayed historical storm intensity & severity slider).
- Production authentication / billing systems (hackathon prototype scope).
- Inferring medical or life-support status from energy usage (forbidden by privacy guidelines).

## Context

- **Operational Data Package**:
  - `arcos_prod_damage_09_28_Clip.dbf`: 1,659 damage records with lat/long, repair times, access flags, and circuits (featuring Feb 13-17, 2025 Winter Storm with 1,223 incidents and Sept 27-30, 2024 Event with 173 incidents).
  - `Customer_Clip.dbf`: 117,642 premises with circuit assignments, transformer IDs, and flags.
  - `matched_upstream.txt`: 117,599 records tracing customer premises upstream through transformers and isolating devices (fuses, reclosers, switches) to the circuit breaker.
  - `Install_Labor_HackOHIO.xlsx`: 5 sheets containing CU group definitions, install/removal hours, access adders, and the official Indirect Labor Multiplier (ILM = 4.5).
  - Public Critical Facilities: Hospitals (4), Fire Stations (30), Ambulance Services (8).
- **Environment**: Windows, Python 3.13, SQLite3, FastAPI, Uvicorn, openpyxl, numpy, Pydantic.

## Constraints

- **Strict Privacy**: No raw customer addresses, PII, internal serial IDs, or exact critical site coordinates leave the server.
- **Numbers from Code**: LLM phrasing only. The LLM cannot compute or alter estimates, durations, or weights.
- **Explainability**: Every factor, weight, multiplier, and assumption must be visible and explainable to a non-technical judge.
- **Zero Build Frontend**: Minimalist HTML/JS dashboard using CDN Leaflet and modern CSS for instant loading and zero build complexity.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Premise Anonymization via Salted SHA-256 | Complies with brief R17 privacy rule while maintaining consistent hash join between `Customer_Clip` and `matched_upstream.txt`. | ✓ Resolved |
| SQLite In-Memory / File Database | Instant loading, zero server overhead, cross-table SQL joins across 117k rows in milliseconds. | ✓ Resolved |
| Indirect Labor Multiplier = 4.5 | Directly extracted from workbook sheet 'Indirect Labor Multiplier' for drive time, briefing, and setup. | ✓ Resolved |
| Storm Replay Selection | Replay the Feb 13-17, 2025 Winter Storm (1,223 damage events across CIR2, CIR10, CIR72) as default, with Sept 2024 as secondary. | ✓ Resolved |
| Topology First Column | Verified 100% (1,000/1,000) that column 1 of `matched_upstream.txt` is `premise_nu`. | ✓ Resolved |
| Customer-Facing Topology Labels | Replaced raw equipment serials with descriptive labels ("Upstream Recloser 1", "Circuit Breaker"). | ✓ Resolved (G1) |
| Deterministic LLM Guardrail | Automated regex validator verifies every number in LLM chat response exists in tool JSON output. | ✓ Resolved |

---
*Last updated: 2026-10-24 at GSD Project Initialization*
