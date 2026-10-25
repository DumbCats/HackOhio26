import { useState } from "react";
import type { Alerts, Controls, DemoHome, Forecast, Need, Prep, Restoration } from "../types";
import { clockLabel, NEED_LABELS, rangeLabel } from "../format";
import { SourceChip } from "./SourceChip";
import { Sheet } from "./Sheet";

export function SafetyCard({ prep, compact }: { prep: Prep | null; compact?: boolean }) {
  if (!prep) return null;
  return (
    <section className="safety-card" aria-label="Safety">
      <div className="safety-label">SAFETY</div>
      <p className="safety-emergency">{prep.emergency_line}</p>
      {!compact && <ul>{prep.safety.map((s) => <li key={s.id}>{s.text}</li>)}</ul>}
    </section>
  );
}

export function PrepareSheet({ prep, needs, setNeeds, onClose }: {
  prep: Prep | null; needs: Need[]; setNeeds: (n: Need[]) => void; onClose: () => void;
}) {
  const [done, setDone] = useState<Record<string, boolean>>({});
  const toggle = (n: Need) => setNeeds(needs.includes(n) ? needs.filter((x) => x !== n) : [...needs, n]);
  const title = prep?.phase === "after" ? "After the outage" : prep?.phase === "during" ? "What to do now" : "Prepare";
  return (
    <Sheet title={title} onClose={onClose} chip={<SourceChip source="fixed_guidance" />}>
      {prep && <p className="muted">{prep.why} {prep.duration_bucket !== "restored" && <>Planning for an outage of <b>{prep.duration_bucket.replace("h", " hours")}</b>.</>}</p>}
      <SafetyCard prep={prep} />
      <h3 className="mini-h">Checklist</h3>
      <ul className="checklist">
        {prep?.actions.map((a) => (
          <li key={a.id}>
            <label>
              <input type="checkbox" checked={!!done[a.id]} onChange={() => setDone({ ...done, [a.id]: !done[a.id] })} />
              <span>{a.text}</span>
            </label>
          </li>
        ))}
      </ul>
      {prep && prep.needs_actions.length > 0 && (
        <>
          <h3 className="mini-h">For what you told us</h3>
          <ul className="needs-actions">
            {prep.needs_actions.map((n) => <li key={n.need}><b>{NEED_LABELS[n.need]}</b><p>{n.text}</p></li>)}
          </ul>
        </>
      )}
      <h3 className="mini-h">Tell us what applies to you</h3>
      <p className="muted small">Only you can turn these on. We use them to tailor this list and our alerts. They are never stored or logged.</p>
      <div className="toggles">
        {(Object.keys(NEED_LABELS) as Need[]).map((n) => (
          <label key={n} className="toggle">
            <span>{NEED_LABELS[n]}</span>
            <input type="checkbox" role="switch" checked={needs.includes(n)} onChange={() => toggle(n)} />
          </label>
        ))}
      </div>
    </Sheet>
  );
}

const TYPE_LABEL: Record<string, string> = {
  pre_storm: "Pre-storm alert", outage_confirmed: "Outage confirmed", estimate_updated: "Estimate updated", restored: "Power restored",
};

export function AlertsSheet({ alerts, onClose }: { alerts: Alerts | null; onClose: () => void }) {
  return (
    <Sheet title="Alerts" onClose={onClose}>
      {alerts && (
        <>
          <div className="card eligibility">
            <b>Do I qualify for outage alerts?</b>
            <p>{alerts.eligibility_summary}</p>
          </div>
          <h3 className="mini-h">Messages you've received</h3>
          {alerts.timeline.length === 0 && <p className="muted">None yet.</p>}
          <ol className="msgs">
            {alerts.timeline.map((m) => (
              <li key={m.type + m.t} className="msg">
                <div className="msg-meta"><b>{TYPE_LABEL[m.type] ?? m.type}</b><span>{clockLabel(m.t)} · {m.channel.toUpperCase()}</span></div>
                <p>{m.text}</p>
              </li>
            ))}
          </ol>
          <h3 className="mini-h">Alert rules</h3>
          <ul className="rules">
            {alerts.rules.map((r) => (
              <li key={r.rule_id} className={r.fired ? "fired" : ""}>
                <span className="tick" aria-hidden>{r.fired ? "✓" : "–"}</span>{r.name}{!r.fired && r.rule_id === "R1" && alerts.r1_pending ? " (you'll get one at the forecast)" : ""}
                <span className="sr-only">{r.fired ? " (applies to you)" : ""}</span>
              </li>
            ))}
          </ul>
          <h3 className="mini-h">How we reach you</h3>
          <ul className="plain-list">{alerts.channels.map((c) => <li key={c.channel}><b>{c.channel.toUpperCase()}</b> — {c.why}</li>)}</ul>
          <h3 className="mini-h">When we escalate</h3>
          <ul className="plain-list">
            {alerts.escalations.map((e) => (
              <li key={e.trigger} className={e.active ? "active-esc" : ""}>
                {e.active && <span className="pill-active">Active</span>} <b>If</b> {e.trigger.toLowerCase()}: {e.action}
              </li>
            ))}
          </ul>
          <p className="muted small">{alerts.assumptions.join(" ")}</p>
        </>
      )}
    </Sheet>
  );
}

const REAL_VS_SIM: [string, string, "real" | "sim" | "none"][] = [
  ["Past storm damage (where, what broke)", "AEP damage records", "real"],
  ["Homes, lines, and the equipment feeding each home", "AEP network map, anonymized", "real"],
  ["Repair labor hours", "AEP labor table", "real"],
  ["Live outage feed", "replay of the Feb 2025 storm", "sim"],
  ["Crew status", "stage only, no crew details", "sim"],
  ["Weather", "a storm-strength setting", "sim"],
  ["Utility-confirmed restore time", "not in this demo", "none"],
];
const RV_LABEL = { real: "Real", sim: "Simulated", none: "Missing" };

export function TrustSheet({ f, r, onClose }: { f: Forecast | null; r: Restoration | null; onClose: () => void }) {
  const uniq = (xs: string[]) => [...new Set(xs)];
  const assumptions = uniq([...(r?.estimate ? r.assumptions : []), ...(f?.assumptions ?? [])]);
  const missing = uniq([...(f?.missing_data ?? []), ...(r?.missing_data ?? [])]);
  const change = uniq([...(r?.estimate ? r.what_would_change : []), ...(f?.what_would_change ?? [])]);
  return (
    <Sheet title="How sure are we?" onClose={onClose}>
      <div className="card">
        {f && !f.fallback && <p><b>Risk band:</b> {f.risk.confidence} confidence. {f.risk.confidence_reason}</p>}
        {f?.fallback && <p><b>Risk band:</b> {f.fallback.message}</p>}
        {r?.recap && <p><b>Return time:</b> {r.recap.message}</p>}
        {r?.estimate && <p><b>Return time:</b> {r.estimate.confidence} confidence, from {r.estimate.n_sims.toLocaleString()} simulated repair runs. The range {rangeLabel(r.estimate.p10_h, r.estimate.p90_h)} covers the middle 8 in 10 of them.</p>}
        <p className="muted">Risk is a comparison with nearby homes, never a percent chance. Return times are a range, never a promise. Only the utility confirms restoration.</p>
      </div>
      <h3 className="mini-h">What we assume</h3>
      <ul className="plain-list">{assumptions.map((a) => <li key={a}>{a}</li>)}</ul>
      <h3 className="mini-h">What we don't have</h3>
      <ul className="plain-list">{missing.map((a) => <li key={a}>{a}</li>)}</ul>
      <h3 className="mini-h">What would change the answer</h3>
      <ul className="plain-list">{change.map((a) => <li key={a}>{a}</li>)}</ul>
      <h3 className="mini-h">Real vs simulated</h3>
      <table className="rvs">
        <tbody>
          {REAL_VS_SIM.map(([what, how, real]) => (
            <tr key={what}><td>{what}</td><td><span className={`rv ${real}`}>{RV_LABEL[real]}</span> {how}</td></tr>
          ))}
        </tbody>
      </table>
      <h3 className="mini-h">Labels on every number</h3>
      <div className="chip-legend">
        <div><SourceChip source="model_estimate" /> computed by our models</div>
        <div><SourceChip source="simulated_feed" /> our stand-in for the utility's live feed</div>
        <div><SourceChip source="utility_confirmed" /> from the utility (none in this demo)</div>
        <div><SourceChip source="fixed_guidance" /> fixed, reviewed safety text</div>
      </div>
      <h3 className="mini-h">Your privacy</h3>
      <p className="muted">Homes are anonymous ids. The map shows areas about 1 km across, never your address. No equipment, line, or crew details are shown. Needs you tell us are used for this answer only and never stored.</p>
    </Sheet>
  );
}

export function ChangeSheet({ r, c, set, onClose }: {
  r: Restoration | null; c: Controls; set: (p: Partial<Controls>) => void; onClose: () => void;
}) {
  const e = r?.estimate;
  const [usual] = useState(() => (c.crews === null ? r?.inputs.crews ?? 1 : c.crews));
  const crews = c.crews ?? r?.inputs.crews ?? usual;
  const delta = crews - usual;
  const crewDriver = r?.drivers.find((d) => d.key === "crews_plus_2");
  const crewsDontHelp = !!crewDriver && Math.abs(crewDriver.effect_h) < 0.5;
  return (
    <Sheet title="What could change this?" onClose={onClose} chip={<SourceChip source="model_estimate" />}>
      <div className="card live-estimate" aria-live="polite">
        {e ? <><div className="big">{rangeLabel(e.p10_h, e.p90_h)}</div><div className="muted">{e.headline} · confidence {e.confidence}</div></>
           : <div className="muted">No outage right now, so there's no return time to change.</div>}
      </div>
      {r && r.drivers.length > 0 && (
        <>
          <h3 className="mini-h">Biggest things that move it</h3>
          <ul className="drivers">
            {r.drivers.map((d) => (
              <li key={d.key}>
                <span>{d.label}</span>
                <b className={d.effect_h > 0.4 ? "longer" : d.effect_h < -0.4 ? "shorter" : ""}>
                  {d.active ? "included" : Math.abs(d.effect_h) < 0.5 ? "little change" : `${d.effect_h > 0 ? "+" : "−"}${Math.abs(d.effect_h).toFixed(1)} h`}
                </b>
              </li>
            ))}
          </ul>
        </>
      )}
      <h3 className="mini-h">Try it</h3>
      <div className="controls">
        <div className="control">
          <span>Crews on your line <small className="muted block">{delta === 0 ? "as planned" : `${delta > 0 ? "+" : "−"}${Math.abs(delta)} vs planned`}</small></span>
          <div className="stepper">
            <button className="icon-btn" aria-label="Fewer crews" onClick={() => set({ crews: Math.max(1, crews - 1) })}>{"−"}</button>
            <b aria-live="polite">{delta === 0 ? "—" : `${delta > 0 ? "+" : "−"}${Math.abs(delta)}`}</b>
            <button className="icon-btn" aria-label="More crews" onClick={() => set({ crews: Math.min(30, crews + 1) })}>+</button>
            {c.crews !== null && <button className="link-btn" onClick={() => set({ crews: null })}>reset</button>}
          </div>
        </div>
        <label className="toggle"><span>Roads blocked by ice or trees</span><input type="checkbox" role="switch" checked={c.accessBlocked} onChange={(ev) => set({ accessBlocked: ev.target.checked })} /></label>
        <label className="toggle"><span>Crews can reroute power around damage</span><input type="checkbox" role="switch" checked={c.switching} onChange={(ev) => set({ switching: ev.target.checked })} /></label>
        <div className="control">
          <span>More damage found on your line</span>
          <div className="stepper">
            <button className="icon-btn" aria-label="Less damage" onClick={() => set({ extraDamage: Math.max(0, c.extraDamage - 1) })}>{"−"}</button>
            <b>{c.extraDamage}</b>
            <button className="icon-btn" aria-label="More damage" onClick={() => set({ extraDamage: Math.min(10, c.extraDamage + 1) })}>+</button>
          </div>
        </div>
      </div>
      {crewsDontHelp && <p className="note">More crews won't speed this up much: the repairs on your line aren't waiting for a crew, they just take time.</p>}
      <p className="muted small">These are what-ifs on our estimate. They don't change what the utility reports.</p>
    </Sheet>
  );
}

export function HomeSheet({ homes, current, onPick, onMap, onClose }: {
  homes: DemoHome[]; current: string; onPick: (id: string) => void; onMap: () => void; onClose: () => void;
}) {
  return (
    <Sheet title="Choose a location" onClose={onClose}>
      <p className="muted">Homes are anonymous. Areas are about 1 km across; we never show addresses.</p>
      <ul className="home-list">
        {homes.map((h) => (
          <li key={h.home_id}>
            <button className={`home-item${h.home_id === current ? " current" : ""}`} onClick={() => onPick(h.home_id)}>
              <b>{h.label}</b><span>{h.area}</span>
            </button>
          </li>
        ))}
      </ul>
      <button className="btn btn-primary wide" onClick={onMap}>Pick an area on the map</button>
    </Sheet>
  );
}
