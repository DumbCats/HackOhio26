# AI Outage Concierge: full design (pre-build)

Status: planning only. No code written. Builds on [PLAN.md](PLAN.md).

## 0. Principles

- Numbers come from code, never from the LLM. The LLM only phrases structured output.
- Every estimate ships with its inputs, assumptions, and confidence.
- Privacy by allowlist: the API returns only fields on an explicit list. Everything else is dropped.
- Rules before models. A learned model is a later option, only if it beats the rules on held-out storm data.

## 1. Data contracts (what the backend stores)

Stream the large files once into compact tables. Nothing reads the raw dbf at request time.

| Table | Key | Built from | Fields kept |
|---|---|---|---|
| `circuits` | `circuit_id` | Customer_Clip, Fuse_Bank, topology | customer count, premise count, device count, upstream breaker |
| `damage_events` | `outage_num` | ARCOS | circuit_id, asset_type, report time, repair time, status, access issue, special_eq, lat, lon, nearest_asset_id, nearest_dist |
| `assets` | `global_id` | Pole, Transformer, Fuse, Recloser, Switch | type, circuit_id, age (install year), material, lat, lon |
| `premises` | `premise_key` (hashed) | Customer_Clip | circuit_id, transformer_id, is_critical_tier (aggregate only) |
| `topology_edges` | (premise_key, step) | matched_upstream.txt | ordered upstream chain of device IDs ending at a breaker |
| `labor_codes` | `CD_CU` | Install_Labor workbook | install_hours, remove_hours, category, description |
| `travel_multipliers` | category | workbook "Indirect Labor Multiplier" | travel and nonproductive multipliers |
| `priority_sites` | anonymized site ID | hospitals, fire, ambulance shapefiles | type, rounded location (about 1 km) |

Storage: SQLite file for the hackathon. It needs no server, and the file loads in seconds.

Premise key: a salted hash of `premise_nu` (or the customer ID). The salt stays in a local config file that is not shared. The judge UI never receives the raw ID.

## 2. Risk prediction

Output: a band (Low, Moderate, High) and a confidence (Low, Medium, High), plus the top 3 to 5 factors.

Features (per circuit, and per premise through its circuit):
1. Historical damage rate: damage events on the circuit per year (ARCOS).
2. Nearest-damage distance: distance from the premise to the nearest damage event (ARCOS NEAR_DIST, recomputed for the premise).
3. Asset age and material: share of old poles and wood-pole ratio near the premise (Pole_Clip).
4. Protection exposure: number of devices upstream from the premise (topology length).
5. Storm input: a severity value from 0 to 1, set by a slider or taken from a replayed event.

Scoring: a weighted sum, each feature scaled to 0 to 1 by its percentile across circuits. Weights are fixed in one config file and written in the UI. Band cut points are set at the 60th and 85th percentile of the score across circuits.

Confidence rules:
- Low if the circuit has fewer than 3 historical damage events, or if the premise has no topology match.
- Medium if one of the key inputs is missing or the storm input is simulated.
- High otherwise.
- Below Low confidence, show the fallback text instead of a band.

Validation: replay one historical ARCOS storm. Check that the top-ranked circuits match where damage actually happened. Report the hit rate. Do not claim accuracy beyond this.

Known limits to state in the UI: ARCOS covers 1,659 damage events, which is small. There are no customer-outage counts, so the score predicts damage, not customer outages.

## 3. Restoration-time estimate

Output: a range (P10 to P90, in hours) and the factors most likely to move it.

Steps:
1. Count damage by asset type in the chosen scope (a premise's circuit, or a whole storm).
2. Map each asset type to a labor code category (ARM, ANC, GND, INS, PIN, SWI, XRA, and so on) and sum install and remove hours from `labor_codes`.
3. Apply the travel and nonproductive multiplier from `travel_multipliers`.
4. Divide by crew count to get elapsed hours.
5. Add the access penalty from ARCOS access-issue flags (for example, a fixed extra fraction per flagged event).
6. Step restoration: order the damage by upstream position. Repairing the breaker or recloser closest to the source restores the most customers first. Step 1 restores everything upstream of the next device.
7. P10 and P90: apply a fixed spread (for example, -25% and +40%, asymmetric because delays are more common than speedups). Put the spread in config and state it in the UI.

Updates: any change to crew count, severity, or access recomputes the range. The page shows "model estimate" next to every number.

Confirmed status: the system never shows a confirmed restoration time. A later input field can accept utility-confirmed times, marked as confirmed.

## 4. Preparation guidance

- Templates keyed by risk band and by expected duration bucket (under 4 hours, 4 to 24 hours, over 24 hours).
- Safety items are always shown first and are labeled "Safety". Examples: keep a flashlight and charged phone, use a generator outdoors only, treat any downed line as live.
- Needs-based content (medical equipment, accessibility) comes only from a user-declared option in the UI. Nothing is inferred from data. The option changes which tips appear. It is not stored.
- Emergency path: a fixed line that tells people to call 911 for injuries or fire. This line never gets hidden by other content.

## 5. Alerts and messages

Alert eligibility (documented rules, shown on screen):
- Eligible if the premise is in a Moderate or High band, or if the premise has a critical-tier flag. Eligibility means "may receive proactive alerts". It doesn't mean a notice has been sent.
- Escalation trigger: when a priority site (hospital, fire, ambulance) is within the cut-off distance of an active damage event, flag it to the operator queue.

Notification timing (suggested, all configurable):
- Pre-storm alert: 48 hours before forecast impact, if High band.
- Outage-confirmed: when a damage event on the premise's circuit is recorded.
- Estimate-updated: when the range changes by more than 25%.
- Restoration-complete: when the premise's last upstream device is repaired.

Channel: SMS for High, email for Moderate, app notification as the default. These are recommendations shown in the UI, not real sends.

Message templates: one per scenario, under 60 words, plain language, with the confidence and "estimate, not confirmed" wording built in.

Audit log: each generated message stores the template ID, inputs used (no personal fields), and the time.

## 6. Application layers

Backend (Python, standard library plus one small web framework):
- `ingest/`: one script per source. Reads dbf and txt, writes SQLite. Run once.
- `core/`: pure functions for risk, restoration, alerts, and messages. No I/O. Easy to test.
- `api/`: HTTP endpoints, each returning a fixed allowlisted JSON shape.
- `config/`: weights, percentiles, multipliers, spreads, cut-off distances, templates.

Frontend (small web app, no build step if possible):
- One page, a map on the left and a side panel on the right.
- Chat box in the side panel. Each question maps to a fixed tool call. Free-form text falls back to "I can answer these four questions" plus buttons.

Chat design: the four challenge questions map to four tools (risk, restoration, checklist, alerts). The LLM receives the tool output as JSON and writes the reply. It may not add numbers that are not in the JSON. A check rejects any reply that contains a number not in the input.

## 7. Endpoints

- `GET /api/premise/{key}/risk?severity=`: band, confidence, factors, fallback flag.
- `GET /api/premise/{key}/restoration?severity=&crews=&access=`: range, step order, factors.
- `GET /api/premise/{key}/prepare?needs=`: checklist.
- `GET /api/premise/{key}/alerts`: eligibility and rule text.
- `GET /api/map/circuits?severity=`: circuit scores for the map layer.
- `GET /api/storms`: list of replayable historical events from ARCOS.
- `POST /api/chat`: question in, structured reply out.

Every response includes `assumptions`, `data_as_of`, and `source` (model or confirmed).

## 8. UI screens

1. **Map view.** Circuits colored by band. Click a point to set the premise. Priority sites shown as masked dots.
2. **Premise card.** Band, confidence, top factors, range bar, checklist, alert eligibility, assumptions. Each has an info toggle showing the math.
3. **Scenario panel.** Sliders for severity, crews, access. A storm replay dropdown. Changing any control updates the card live.
4. **Operator queue (second priority).** Ranked damage list with escalation flags.

Accessibility: keyboard navigation, text labels on every color, a table view of the map data, readable at 200% zoom.

## 9. Testing (one runnable check per module, per the ponytail rule)

- Ingest: row counts match the source counts (1,659 damage events; 117,642 customers; 117,599 topology rows).
- Risk: a fixed input gives a fixed band. Weights sum to one.
- Restoration: a known damage list gives a known hour total by hand calculation.
- Privacy: the API output contains none of the raw premise fields. Automated check on every endpoint.
- Chat: the number-check rejects a reply that adds an invented figure.

## 10. Build order once approved

1. Ingest and SQLite schema, with the row-count check.
2. Core risk and restoration functions, with the hand-check.
3. API endpoints and the privacy check.
4. Map and premise card UI.
5. Scenario sliders and storm replay.
6. Alerts and messages.
7. Chat layer, with the number check.

## 11. Decisions still open

1. Which storm to replay as the default demo?
2. Confirm the topology file's first column with the organizers.
3. Confirm the wording and cut-off distance for priority-site escalation.
4. Confirm the restoration spread (-25% and +40%) is acceptable, or supply a source for another value.
5. Whether to read the labor workbook sheet values now. openpyxl is installed in the system Python 3.8, so this is a short step.

Note for the open items: the labor workbook is not yet read. The design above assumes its codes map to damage categories. Step 5 of the open list checks that assumption.
