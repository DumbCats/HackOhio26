import type { Alerts, ChatMsg, Controls, Forecast, HomeInfo, OutageMap, Prep, Repairs, Restoration, Scenario } from "./types";

const env = import.meta.env.VITE_API_BASE as string | undefined;
export const API_BASE = env ?? (location.port === "5173" ? `${location.protocol}//${location.hostname}:8000` : "");

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const r = await fetch(API_BASE + path, { signal });
  if (!r.ok) throw new Error(`${r.status} ${path}`);
  return r.json() as Promise<T>;
}

function q(params: Record<string, string | number | boolean | null | undefined>): string {
  const s = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== null && v !== undefined && v !== "") s.set(k, String(v));
  return s.toString();
}

export function scenarioParams(c: Controls) {
  return {
    t: c.t, severity: c.severity, crews: c.crews, access_blocked: c.accessBlocked,
    extra_damage: c.extraDamage, switching: c.switching,
  };
}

export const api = {
  scenario: (s?: AbortSignal) => get<Scenario>("/api/scenario", s),
  locate: (lat: number, lon: number) => get<{ cell_id: string; home_id: string; area: string }>(`/api/locate?${q({ lat, lon })}`),
  outageMap: (t: number, severity: number, s?: AbortSignal) => get<OutageMap>(`/api/outage-map?${q({ t, severity })}`, s),
  home: (id: string, s?: AbortSignal) => get<HomeInfo>(`/api/home/${id}`, s),
  repairs: (id: string, t: number, s?: AbortSignal) => get<Repairs>(`/api/repairs/${id}?${q({ t })}`, s),
  forecast: (c: Controls, s?: AbortSignal) => get<Forecast>(`/api/forecast/${c.homeId}?${q({ t: c.t, severity: c.severity })}`, s),
  restoration: (c: Controls, s?: AbortSignal) => get<Restoration>(`/api/restoration/${c.homeId}?${q({ t: c.t, crews: c.crews, access_blocked: c.accessBlocked, extra_damage: c.extraDamage, switching: c.switching })}`, s),
  prep: (c: Controls, s?: AbortSignal) => get<Prep>(`/api/prep/${c.homeId}?${q({ ...scenarioParams(c), needs: c.needs.join(",") })}`, s),
  alerts: (c: Controls, s?: AbortSignal) => get<Alerts>(`/api/alerts/${c.homeId}?${q({ ...scenarioParams(c), needs: c.needs.join(","), low_power: c.lowPower })}`, s),
  chat: async (c: Controls, messages: ChatMsg[]) => {
    const r = await fetch(API_BASE + "/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        home_id: c.homeId, t: c.t, needs: c.needs, severity: c.severity, crews: c.crews,
        access_blocked: c.accessBlocked, extra_damage: c.extraDamage, switching: c.switching,
        low_power: c.lowPower, messages: messages.map(({ role, content }) => ({ role, content })),
      }),
    });
    if (!r.ok) throw new Error(`chat ${r.status}`);
    return r.json() as Promise<{ reply: string; tools_used: string[]; safety_flag: boolean; source: string }>;
  },
};
