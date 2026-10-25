export type Source = "model_estimate" | "simulated_feed" | "utility_confirmed" | "fixed_guidance" | "llm" | "fallback" | "approved_text";
export type Band = "low" | "medium" | "high" | "unknown";

export interface Fallback { reason: string; message: string; link: string }
export interface Honesty {
  source: Source;
  assumptions: string[];
  missing_data: string[];
  what_would_change: string[];
  fallback: Fallback | null;
}

export interface Moment { t: number; key: string; label: string }
export interface DemoHome { home_id: string; label: string; cell_id: string; area: string; role: string }
export interface Scenario {
  storm_name: string; t_min: number; t_max: number; t_now_default: number;
  moments: Moment[]; default_home_id: string; homes: DemoHome[];
  map_center: [number, number]; map_zoom: number;
}

export interface Factor { label: string; direction: "up" | "down"; strength: "strong" | "medium" | "weak" }
export interface Forecast extends Honesty {
  home_id: string; t: number;
  storm: { name: string; severity: number; hours_until_storm: number; simulated: boolean };
  risk: { band: Band; headline: string; confidence: "low" | "medium" | "high"; confidence_reason: string;
          factors: Factor[]; rank_note?: string; note?: string };
}

export interface Estimate { p10_h: number; p50_h: number; p90_h: number; confidence: string; n_sims: number; headline: string; source: Source; back_by_t_low?: number; back_by_t_high?: number }
export interface Driver { key: string; label: string; effect_h: number; active?: boolean }
export interface RangeCheck { made_at_t: number; back_by_t_low: number; back_by_t_high: number; within_range: boolean }
export interface Restoration extends Honesty {
  home_id: string; t: number; is_out: boolean; out_since_t: number | null; restored_at_t: number | null;
  status: { stage: string; label: string; source: Source; updated_t: number | null } | null;
  cause: { label: string; severity: string; repairs_on_your_path: number; repairs_on_your_line: number } | null;
  estimate: Estimate | null; utility_etr: number | null;
  chance_back_by: { t_from_now_h: number; prob: number }[];
  step_restoration: { your_step: number; total_steps: number; message: string } | null;
  drivers: Driver[];
  recap: { out_since_t: number; restored_at_t: number; actual_h: number; first_estimate: RangeCheck | null;
           updated_estimate: RangeCheck | null; message: string } | null;
  inputs: { crews: number; access_blocked: boolean; extra_damage: number; switching: boolean };
}

export interface Prep extends Honesty {
  phase: "before" | "during" | "after"; duration_bucket: string; why: string; emergency_line: string;
  safety: { id: string; text: string }[];
  actions: { id: string; text: string; when: string }[];
  needs_actions: { need: string; text: string }[];
}

export interface TimelineMsg { type: string; rule_id: string; t: number; channel: string; text: string; shift_h?: number }
export interface Alerts extends Honesty {
  home_id: string; t: number;
  eligible: boolean; eligibility_summary: string;
  rules: { rule_id: string; name: string; fired: boolean; eligible?: boolean }[];
  r1_pending?: boolean;
  rules_fired: { rule_id: string; text: string }[];
  channels: { channel: string; why: string }[];
  timeline: TimelineMsg[];
  escalations: { trigger: string; action: string; active: boolean }[];
}

export interface Cell { cell_id: string; bounds: [[number, number], [number, number]]; homes: number; homes_out: number; status: "out" | "partial" | "on"; risk_band: Band }
export interface OutageMap extends Honesty { t: number; summary: { homes_total: number; homes_out: number; active_repairs: number }; cells: Cell[] }

export interface HomeInfo { home_id: string; cell_id: string; area: string; center: [number, number] | null; customers_on_line: string; network_match: boolean }
export interface RepairStep { order: number; label: string; status: "done" | "in_progress" | "waiting"; center: [number, number] | null; reported_t: number }
export interface Repairs extends Honesty { steps: RepairStep[]; home_center: [number, number] | null; note: string }

export interface ChatMsg { role: "user" | "assistant"; content: string; source?: string; safety_flag?: boolean; tools_used?: string[] }

export type Need = "medical_device" | "refrigerated_meds" | "mobility" | "well_water" | "critical_facility";

export interface Controls {
  homeId: string;
  t: number;
  severity: number;
  crews: number | null;
  accessBlocked: boolean;
  extraDamage: number;
  switching: boolean;
  needs: Need[];
  lowPower: boolean;
}
