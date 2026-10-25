import type { Source } from "./types";

// Storm clock: t = hours since Thu 13 Feb 2025 00:00 (MASTER_PLAN A1). Shown as day + time only.
const DAYS = ["Thu", "Fri", "Sat", "Sun", "Mon", "Tue", "Wed"];

export function clockLabel(t: number): string {
  const total = Math.round(t * 60);
  const dayIdx = Math.floor(total / 1440);
  const mins = ((total % 1440) + 1440) % 1440;
  const h = Math.floor(mins / 60), m = mins % 60;
  const ampm = h < 12 ? "AM" : "PM";
  const h12 = h % 12 === 0 ? 12 : h % 12;
  const day = DAYS[((dayIdx % 7) + 7) % 7];
  return `${day} ${h12}:${String(m).padStart(2, "0")} ${ampm}`;
}

export function hoursLabel(h: number): string {
  if (h < 1) return "under an hour";
  if (h < 48) return `${Math.round(h)} hour${Math.round(h) === 1 ? "" : "s"}`;
  return `${Math.round(h / 24)} days`;
}

export function rangeLabel(p10: number, p90: number): string {
  const lo = Math.floor(p10), hi = Math.max(Math.ceil(p90), lo + 1);
  if (hi > 48) {
    const dlo = Math.floor(p10 / 24), dhi = Math.max(Math.ceil(p90 / 24), dlo + 1);
    return dlo === 0 ? `within ${dhi} days` : `${dlo}–${dhi} days`;
  }
  return lo === 0 ? `within ${hi} hours` : `${lo}–${hi} hours`;
}

export const SOURCE_LABEL: Record<Source, string> = {
  model_estimate: "Our estimate",
  simulated_feed: "Simulated utility feed",
  utility_confirmed: "Utility confirmed",
  fixed_guidance: "Safety guidance",
  llm: "AI answer · numbers from our tools",
  fallback: "Template answer",
  approved_text: "Approved explanation",
};

export const NEED_LABELS: Record<string, string> = {
  medical_device: "I use a medical device that needs power",
  refrigerated_meds: "I keep medicine in the fridge (like insulin)",
  mobility: "I have limited mobility",
  well_water: "My water comes from a well pump",
  critical_facility: "I run a clinic, shelter, or care home",
};

export const BAND_TEXT: Record<string, string> = { high: "High", medium: "Moderate", low: "Lower", unknown: "Unknown" };

export const STAGES = [
  { key: "risk", label: "Risk raised" },
  { key: "assessing", label: "Damage reported" },
  { key: "crew_assigned", label: "Repair scheduled" },
  { key: "repairing", label: "Repairing" },
  { key: "restored", label: "Restored" },
];

export function stageIndex(stage: string | null | undefined, isOut: boolean, restored: boolean): number {
  if (restored) return 4;
  if (!isOut) return 0;
  const i = STAGES.findIndex((s) => s.key === stage);
  return i < 0 ? 1 : i;
}

export const OUTAGE_LINK = "https://www.appalachianpower.com/outages/";
