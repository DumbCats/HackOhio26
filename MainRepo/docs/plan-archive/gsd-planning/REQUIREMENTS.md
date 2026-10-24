# Scoped Requirements: AI Outage Concierge

All requirements are traceable to the HackOHI/O 2026 Challenge Brief (`HackOHIO_2026_AI_Outage_Concierge_Challenge.docx`), `DESIGN.md`, and `CHECKLIST.md`.

## Core Requirements Matrix

| ID | Category | Requirement Description | Success Metric |
|---|---|---|---|
| **REQ-01** | Input | Accept an anonymized premise key, circuit identifier, or map coordinate click | System resolves context and snaps to nearest valid premise in <500ms |
| **REQ-02** | Risk Model | Produce an outage-risk estimate categorized into a clearly defined band (Low, Moderate, High) with confidence | Every premise query returns `band` and `confidence` score |
| **REQ-03** | Risk Explainability | Surface the top 3-5 contributing factors behind the risk band in plain English | Non-technical factors with directional impact ("Older wood poles nearby", "Circuit history") |
| **REQ-04** | Uncertainty | Explicitly communicate prediction uncertainty, data boundaries, and missing data | UI shows confidence meter and assumptions toggle adjacent to risk badge |
| **REQ-05** | Restoration Range | Output a restoration duration range (P10 to P90 in hours) rather than a single point promise | Range displayed with lower/upper bound and explicit "Model estimate" badge |
| **REQ-06** | Operational Realism | Recompute duration using damage type, quantity, labor hours, Indirect Labor Multiplier (4.5), and crew count | Changing crew slider or access toggle updates hours dynamically in <100ms |
| **REQ-07** | Step Restoration | Model upstream topological dependencies and calculate customer restoration by steps along isolating equipment | Ordered breakdown ("Phase 1: upstream recloser restores 65% of customers...") |
| **REQ-08** | Status Integrity | Strict demarcation between model outputs and confirmed utility restoration info | "Model Estimate" vs "Utility Confirmed" tags attached to every figure |
| **REQ-09** | Prep Guidance | Generate customized preparation actions keyed to predicted risk band and duration bucket (<4h, 4-24h, >24h) | Checklist items shift dynamically when risk or duration moves between buckets |
| **REQ-10** | Safety Priority | Prominent, persistent safety callouts with emergency 911 banner that cannot be hidden or scrolled past | Safety section styled with priority visual hierarchy; 911 contact banner permanently fixed |
| **REQ-11** | Declared Needs | Adapt preparation checklist for user-declared medical equipment or mobility needs without inferring from data | User checkboxes dynamically add medical battery backup & refrigeration tips |
| **REQ-12** | Alert Eligibility | Determine proactive alert qualification based on transparent, documented operational rules | System displays exact rule fired (e.g., "Eligible: Moderate risk band on feeder CIR10") |
| **REQ-13** | Notification Strategy | Recommend proactive communication timing, channel (SMS, email, app), and escalation triggers | Clear schedule shown (48h pre-storm for High risk, estimate change >25%) |
| **REQ-14** | Message Templates | Generate concise (<60 words) plain-language messages for 4 scenarios (Pre-storm, Outage-confirmed, Estimate-updated, Restored) | All 4 templates contain "estimate, not confirmed" wording and no technical jargon |
| **REQ-15** | Accessible Language | Strip internal jargon, raw work codes (ARM, ANC), and equipment IDs from customer-facing text | Human readable terms used exclusively ("Crossarm replacement", "Upstream recloser") |
| **REQ-16** | Sensitivity Analysis | Provide "What would change this answer" sensitivity panel | Lists exact trigger conditions (e.g., "Adding 2 crews saves 3.2 hours; wind >45mph raises risk to High") |
| **REQ-17** | Privacy By Design | Salted SHA-256 hash for premise keys; strict API response allowlist; round sensitive facilities to ~1 km | Zero PII or address fields transmitted; automated privacy test passes |
| **REQ-18** | Graceful Fallback | Standardized safe fallback text for premises with sparse historical data or low confidence | Below Low confidence threshold, displays fallback safety guidance instead of guessing |
| **REQ-19** | Scenario Playground | Real-time interactive controls for storm severity, crew allocation, access difficulty, and network lockout | Judges can drag sliders and toggle switches to inspect live recalculations |
| **REQ-20** | Historical Replay | Replay historical storm events from ARCOS data (Feb 2025 Winter Storm, Sept 2024 Helene Event) | Selector loads actual historical damage incidents on circuits to validate realism |
| **REQ-21** | Human Escalation | Escalation flagging for critical facilities and direct utility contact routing | Operator priority queue displays critical infrastructure proximity flags |
| **REQ-22** | Audit Trail | Log every chat interaction and tool invocation without recording customer PII | Audit log endpoint tracks query timestamp, intent, tool payload, and validation status |
| **REQ-23** | Structure Mapping | Cross-reference damaged asset types with structural drawings and labor categories | Inspection card maps asset damage to physical component descriptions |
| **REQ-24** | Anti-Hallucination | Strict regex validation verifying that every number emitted by LLM chat exists in tool JSON output | LLM responses containing fabricated numbers are caught and rejected |
