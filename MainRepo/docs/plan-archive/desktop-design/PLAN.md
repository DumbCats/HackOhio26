# AI Outage Concierge: data inventory and feature plan

Source: `aep_challenge.pdf` (challenge brief) and `hackohio/aep_challenge_hack26` (cloned to `C:\Users\thoma\aep_challenge_hack26`; the clone sits outside this folder because the session path is too long for git's pack files).

## 1. Data categories

| # | Category | Source (in repo) | What it holds | Sensitivity | Main use |
|---|---|---|---|---|---|
| 1 | **Damage history** | `Data1.zip` → `arcos_prod_damage_09_28_Clip.dbf` (1,659 records) | Outage number, event, region/district/crew area, substation, circuit, report and repair times, status, asset type, access issues, special equipment, lat/long, nearest-asset ID and distance | Low (no customer fields) | Risk model target, restoration-time targets, spatial clusters |
| 2 | **Customers / premises** | `Data1.zip` → `Customer_Clip` (117,642 records) | Circuit ID, transformer link, premise number, plus address fields and `critical_c` / `special_op` flags | **High (PII and medical or critical flags)** | Premise-to-circuit join only. Hash or drop address fields. Use critical flags only as aggregate tiers. |
| 3 | **Poles and structures** | `Data1.zip` → `Pole_Clip` (107,013 records) | Material, height, class, treatment, install and manufacture dates, owner type | Low | Asset-age and material risk factors |
| 4 | **Protective devices** | `Data1.zip` → `Fuse_Bank_Clip` (7,616); `Data2.zip` → `Recloser_Bank_Clip`, `Switch_Clip` | Device type, circuit, phase settings, SCADA control, normal state, upstream link, mounting, nominal voltage | Medium (internal ops fields) | Step-restoration logic and "which device protects me" |
| 5 | **Distribution network** | `Data1.zip` → `Primary_ExportFeatures`; `Data2.zip` → `Secondary_ExportFeatures` (about 106 MB dbf), `Transformer_Clip` | Line and transformer geometry, attributes | Medium | Proximity signals, map layer |
| 6 | **Topology** | `raw/matched_upstream.zip` → `matched_upstream.txt` (117,599 rows, about 550 MB uncompressed) | Tab-separated chains from a downstream ID up through transformers, isolating equipment (reclosers, switches, fuses) and circuit breakers. Types: `eo_isolating_eqpt_inst` (248k refs), `eo_power_xfrmr_inst` (124k), `eo_circuit` (117k). | Medium | Dependency-aware restoration ("you're behind recloser X, which is down") |
| 7 | **Labor and restoration effort** | `Install_Labor_HackOHIO.xlsx` (5 sheets) | CNC work-code catalog with install and remove hours; "Labor time material related" and "Labor only work" sheets; "Indirect Labor Multiplier" (travel and nonproductive time); "CU Group descriptions" (codes like ARM, ANC, GND, INS, PIN, SWI, XRA with plain-language descriptions) | Low | Duration model: damage type × quantity × labor hours × multiplier ÷ crews |
| 8 | **Priority locations** | `Data1.zip` → hospitals, fire stations, ambulance services (public shapefiles) | Facility locations and attributes | Public, but mask sensitive sites in the UI | Escalation and priority queue |
| 9 | **Reference** | `docs/structure_drawings.pdf`, challenge brief | Sample distribution structures (damage-to-material mapping) | Low | Plain-language explanations of what was damaged |

Caveats I hit while inventorying:
- The workbook values weren't read (no `openpyxl` on this machine). I only saw the sheet names and shared strings. The next step is to install `openpyxl` and dump each sheet.
- The structure drawings are a PDF with no extractable text. Treat them as images.
- The `matched_upstream.txt` column semantics (what the first numeric field is) are inferred from the data. Confirm with the organizers.
- The Secondary and Customer dbf files are large (106 MB and 79 MB), so load them with streaming or a columnar format, not all at once.
- The Customer file is the privacy hotspot. Anything shown to a judge or customer must come from an anonymized key, never a raw address.

## 2. Features, grouped by surface

**Customer experience (what the judge sees)**
1. Location entry: pick an anonymized point on a map, or enter a premise key. Returns a risk card.
2. Risk card: a risk band (low / medium / high) with a confidence level and a "data is limited" fallback.
3. Top factors: the 3 to 5 reasons behind the band (past damage nearby, asset age or material, circuit history, storm input).
4. Restoration range: a P10 to P90 window, not a single number, with the two or three factors most likely to move it.
5. Step-restoration view: "customers behind recloser X come back after step 1; the rest after step 2."
6. Preparation checklist: generated from risk band and expected duration. Safety items are labeled.
7. Chat interface for the four challenge questions ("Will I lose power?", "How long?", "What should I do?", "Do I qualify for alerts?"). Answers come from structured outputs, with the model only phrasing them.
8. Alert eligibility: a rules-based yes/no with the rule shown.
9. Accessibility and critical-need path: adapts guidance for declared needs without inferring them from data.

**Scenario controls (so judges can change an input and see the response)**
10. Storm severity slider and wind-speed or outage-intensity input.
11. Crew count, access constraints, and special-equipment toggles.
12. "Simulate damage at this asset" to see how the range shifts.

**Operator / utility view**
13. Damage heat map and circuit ranking (historical damage per circuit).
14. Restoration queue: which damage to fix first, weighted by critical facilities and customers upstream.
15. Labor calculator: from the workbook, turn damage counts into crew-hours and a duration.
16. Escalation triggers: flags for life-support, hospital, or fire-station proximity.

**Communications**
17. Message templates for pre-storm, outage-confirmed, estimate-updated, and restoration-complete.
18. Timing and channel recommendation per message.
19. Audit log of what was sent, when, and why.

**Responsible-use layer (required by the brief, don't skip)**
20. Privacy filter that strips address fields and internal ops fields from every output.
21. Confidence threshold: below it, show a fallback message instead of a prediction.
22. Assumptions and missing-data panel on every estimate.
23. Model-vs-confirmed badge: estimates are never labeled as utility-confirmed.

## 3. Lazy build order (what to ship first)

Following the brief's minimum viable demonstration, in this order:

1. **Join layer.** ARCOS and topology joined to circuit ID. Stream the big files. Output one clean per-circuit table. Nothing else works without this.
2. **Risk score, rules first.** Historical damage rate per circuit, nearest-damage distance, asset age. A weighted sum with fixed weights. Add a learned model only if time allows and it beats the rules on a held-out storm.
3. **Restoration range, arithmetic first.** Damage count by type × labor hours (workbook) × travel multiplier ÷ crew count, then P10 and P90 from a spread assumption. Step restoration comes from the topology chain.
4. **Customer card and checklist.** Template text filled from the risk band and duration.
5. **Alert rules and two or three messages.** Hard-coded rules. The brief asks for "documented rules or challenge assumptions", so write them down.
6. **Chat layer last.** The LLM only turns the structured output into plain language and answers questions. It never computes the numbers. This keeps answers explainable and avoids made-up figures.

Skip for the hackathon: real-time SCADA, live weather feeds, auth, a production database, and any ML model that can't be explained to a nontechnical judge.

## 4. Decisions to make before building

- Surface: web map plus chat, or chat only? (Default assumption: a web map with a chat side panel.)
- Stack: default assumption is a Python backend that does the joins and scoring, with a small web frontend.
- Storm input: simulated only, or pulled from historical ARCOS events? (Default assumption: replay a historical event from ARCOS, plus manual sliders.)
- Confirm the topology file's first column meaning with the organizers.
