# Build checklist: AI Outage Concierge

Checked against the challenge brief (`aep_challenge.pdf`) and [DESIGN.md](DESIGN.md). Each item is a rule to hold during the build. "Gap" items need adding to the design first.

## A. Brief requirements to hit

| # | Brief requirement | Design section | Build check (done when) |
|---|---|---|---|
| R1 | Accept an anonymized premise, circuit, or map location | 7, 8.1 | Lookup works by premise key, by circuit, and by map click (snaps to nearest premise) |
| R2 | Outage-risk estimate as a band, with confidence | 2 | Every premise response has `band` and `confidence` |
| R3 | Show the top contributing factors | 2, 8.2 | 3 to 5 factors, each in plain words, with direction (raises or lowers risk) |
| R4 | Communicate uncertainty | 2, 8.2 | Confidence is visible on the card, next to the number it qualifies |
| R5 | Restoration as a range, not a promise | 3 | Output is P10 to P90 hours. No single-point time is ever shown. |
| R6 | Update estimate when damage, crew, access change | 3, 8.3 | Changing a slider recomputes the range in under 1 second on the demo data |
| R7 | Network assumptions change the estimate | 3 | **Gap:** design has no network-change input. See G2. |
| R8 | Separate model output from confirmed info | 3, 8.2 | Each number carries a `source` tag: "model estimate" or "utility confirmed". No confirmed values exist in the demo data, so none are ever shown. |
| R9 | Preparation guidance matched to risk and duration | 4 | Checklist changes when band or duration bucket changes (test both) |
| R10 | Safety guidance clearly labeled | 4 | "Safety" heading on every safety item. Emergency line is always visible. |
| R11 | Adapt to declared needs without inferring | 4 | Needs come only from user checkboxes. No data field feeds this. Checked by a test. |
| R12 | Alert eligibility by documented rule | 5 | Eligibility response includes the rule text that fired |
| R13 | Notification timing, channel, escalation triggers | 5 | Each recommendation shows timing, channel, and trigger |
| R14 | Plain-language messages for four scenarios | 5 | Four templates, each under 60 words, each with "estimate, not confirmed" wording |
| R15 | Explain reasons in nontechnical language | 2, 3, 8.2 | Factor and step text contains no field names or codes |
| R16 | Disclose confidence, assumptions, missing data, what would change the answer | 7 (`assumptions`) | Every response lists assumptions and missing inputs. A "what would change this" line appears on the card. **Gap:** not in UI design. See G4. |
| R17 | No raw personal info, employee contacts, precise sensitive locations, internal-only fields | 1, 9 | Privacy check passes on every endpoint. See G1 and G3 for the two leaks the design still allows. |
| R18 | Clear fallback when prediction is unreliable | 2 | Low confidence shows fallback text, not a band |
| R19 | Judges can change at least one scenario input | 8.3 | Severity, crews, and access sliders all work |
| R20 | Minimum demo steps 1 to 6 | 10 | Demo script walks all six steps in order (see section D) |
| R21 | Human escalation path | 5 (partial) | **Gap:** only escalation flags to the operator queue. See G5. |
| R22 | Audit trail | 5 (messages only) | **Gap:** chat answers are not logged. See G5. |
| R23 | Damage-to-material hint from structure diagrams | none | **Gap:** brief lists this use for the diagrams. See G6. |
| R24 | Priority sites: life-support, water, schools | 5 | Partly out of scope. Hospitals, fire, ambulance only, because only those files exist. Say so in the UI. See G7. |

## B. Key values (one config file, never hardcoded)

| Value | Setting | Source in design | Notes |
|---|---|---|---|
| Band cut points | 60th and 85th percentile of scores | 2 | Percentile across circuits |
| Min damage events for High confidence | 3 | 2 | Below this, Low confidence |
| Feature weights | Sum to 1.0, fixed | 2 | Printed on the assumptions panel |
| Storm severity range | 0 to 1 | 2 | Slider default is the replayed event's value |
| Restoration spread | P10 at -25%, P90 at +40% | 3 | Assumed. Flag as assumption in UI. Open decision 4. |
| Duration buckets | under 4 h, 4 to 24 h, over 24 h | 4 | Drives checklist |
| Escalation distance | TBD | 5 | Open decision 3. Do not ship a default without confirming. |
| Priority-site location precision | about 1 km | 5 | Coordinates rounded before any output |
| Estimate-updated trigger | change over 25% | 5 | Message fires only past this |
| Pre-storm lead time | 48 h | 5 | Only for High band |
| Premise key salt | local config, not committed | 1 | Never printed or sent to the browser |
| Ingest row counts (sanity) | 1,659 damage; 117,642 customers; 117,599 topology rows | 9 | Build fails if counts differ |

## C. Hard rules (apply to every line of code)

1. Numbers come from `core/`. The LLM never writes a number that is not in the JSON it received (the number check, design 6).
2. The API returns only allowlisted fields. Adding a field needs a review.
3. No response shows a device ID, circuit name, address, or raw premise number. Use labels such as "upstream switch 2".
4. Every response carries `assumptions`, `data_as_of`, and `source`.
5. Emergency line (call 911 for injury or fire) appears on every guidance view. It is never hidden or collapsed.
6. Safety text is never generated by the LLM. It comes from fixed templates only.
7. Priority-site positions are rounded to about 1 km before leaving the server.
8. A value marked "assumed" in config must be labeled "assumption" wherever it is shown.
9. The sliders and chat must produce the same output for the same inputs.

## D. Demo script (must run end to end)

1. Pick a point on the map. Premise card appears with band, confidence, and factors. (R1, R2, R3, R4)
2. Open restoration. Range shows with model-estimate label and factors. (R5, R8)
3. Move the severity and crew sliders. Range updates. (R6, R19)
4. Read the checklist. Show that changing the band changes it. (R9, R10)
5. Check alert eligibility. Show the rule text. (R12, R13)
6. Generate one proactive message. Show the four-scenario set. (R14)
7. Show the assumptions and "what would change this" panel. (R16)
8. Show the fallback on a premise with too little data. (R18)

## E. Gaps: add to DESIGN.md before building

- **G1. Device IDs in step restoration.** Section 3, step 6 orders "device IDs". Replace with "upstream device 1, 2, 3" labels mapped internally. Brief R17 forbids exposing internal fields.
- **G2. Network changes.** Brief R7 says network assumptions change the estimate. Add a toggle: "assume a named device is out of service" (for example, a recloser stuck open). It removes that device's downstream customers from the restoration step until repaired.
- **G3. Premise key vs topology ID.** Section 1 assumes topology rows use the premise key. Open decision 2 is not yet answered. Hold the topology build until it is.
- **G4. Uncertainty panel in UI.** Add "what would change this answer" to section 8.2 (for example, "if the storm moves inland, the risk band rises").
- **G5. Chat trail and human escalation.** Log each chat turn (question, tool called, output ID; no personal data). Add a "contact the utility" path on High-band cards and on any Low-confidence answer.
- **G6. Structure-diagram hint.** Brief lists the diagrams for "what materials might need to be replaced based on damage type." Add a small lookup: damage type to likely materials. The diagrams are images, so view them manually first and write the mapping as a table.
- **G7. Scope note for priority sites.** Only hospitals, fire, and ambulance are in the data. Say so on screen. Do not claim water-treatment or school coverage.
- **G8. Circuit selection.** R1 names circuits as a valid input. The design only has premise and map click. Add a circuit picker that shows circuit-level risk.

## F. Review of design choices

- Rules before models: consistent with the brief's "explain every prediction" requirement. Keep.
- Premise hashing and allowlisting: meets R17. Keep.
- Percentile-based bands: the bands are relative, not absolute. The UI must say "higher than other circuits" rather than "X% chance of outage". The score is not a probability.
- Restoration spread is a guess. Label it and leave it in config. Open decision 4.
- Validation by storm replay measures damage location, not customer outages. Say so in the UI and in the write-up.
