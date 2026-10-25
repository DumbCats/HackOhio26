import { useEffect, useState } from "react";
import type { Controls, Forecast, Moment, Prep, Restoration, Scenario, TimelineMsg } from "../types";
import { BAND_TEXT, clockLabel, rangeLabel } from "../format";

const TYPE_TITLE: Record<string, string> = {
  pre_storm: "Storm alert", outage_confirmed: "Outage confirmed", estimate_updated: "Estimate updated", restored: "Power restored",
};

export function Notification({ msg, onOpen, onDismiss }: { msg: TimelineMsg | null; onOpen: () => void; onDismiss: () => void }) {
  useEffect(() => {
    if (!msg) return;
    const id = setTimeout(onDismiss, 7000);
    return () => clearTimeout(id);
  }, [msg, onDismiss]);
  if (!msg) return null;
  return (
    <div className="notif" role="status" aria-live="assertive">
      <button className="notif-body" onClick={onOpen}>
        <span className="notif-icon" aria-hidden>
          <svg viewBox="0 0 24 24" width="16" height="16"><path fill="#fff" d="M13 2 4 14h6l-1 8 9-12h-6z" /></svg>
        </span>
        <span className="notif-text">
          <span className="notif-top"><b>{TYPE_TITLE[msg.type] ?? "Outage Concierge"}</b><small>{msg.channel.toUpperCase()} · now</small></span>
          <span>{msg.text}</span>
        </span>
      </button>
      <button className="notif-x" onClick={onDismiss} aria-label="Dismiss">{"×"}</button>
    </div>
  );
}

export function LowPowerView({ r, f, prep, mode, onExit, onChat, battery }: {
  r: Restoration | null; f: Forecast | null; prep: Prep | null; mode: string; onExit: () => void; onChat: () => void; battery: number;
}) {
  const e = r?.estimate;
  let status = "Power is on.";
  if (mode === "outage") status = `Power has been out since ${r?.out_since_t != null ? clockLabel(r.out_since_t) : "recently"}.`;
  if (mode === "restored") status = "Power is back on.";
  const next = prep?.needs_actions[0]?.text ?? prep?.actions[0]?.text;
  return (
    <main className="lowpower">
      <div className="lp-head">
        <b>Low-power mode</b>
        <span>Battery {battery}%</span>
        <button onClick={onExit}>Exit</button>
      </div>
      <p className="lp-status">{status}</p>
      {mode === "outage" && e && (
        <p>Likely back: <b>{rangeLabel(e.p10_h, e.p90_h)}</b> (our estimate, not a promise). Confidence: {e.confidence}.</p>
      )}
      {mode === "forecast" && f && !f.fallback && <p>Risk: <b>{BAND_TEXT[f.risk.band]}</b> compared with nearby homes. Confidence: {f.risk.confidence}.</p>}
      {mode === "forecast" && f?.fallback && <p>{f.fallback.message}</p>}
      {next && <><p className="lp-k">Next step</p><p>{next}</p></>}
      <p className="lp-k lp-safety">SAFETY</p>
      <p>{prep?.emergency_line}</p>
      <p className="lp-k">Alerts</p>
      <p>We'll text you (SMS) instead of push while your battery is low.</p>
      <button className="lp-chat" onClick={onChat}>Ask a question</button>
    </main>
  );
}

export function DemoPanel({ scn, c, set, battery, setBattery, playing, setPlaying, speed, setSpeed, onClose }: {
  scn: Scenario; c: Controls; set: (p: Partial<Controls>) => void; battery: number; setBattery: (n: number) => void;
  playing: boolean; setPlaying: (b: boolean) => void; speed: number; setSpeed: (n: number) => void; onClose: () => void;
}) {
  const [tLocal, setTLocal] = useState(c.t);
  useEffect(() => setTLocal(c.t), [c.t]);
  return (
    <aside className="demo" aria-label="Demo controls">
      <div className="demo-head"><b>Demo controls</b><button className="link-btn" onClick={onClose}>Hide</button></div>
      <label className="demo-row">
        <span>Location</span>
        <select value={c.homeId} onChange={(e) => set({ homeId: e.target.value })}>
          {scn.homes.map((h) => <option key={h.home_id} value={h.home_id}>{h.label}</option>)}
          {!scn.homes.some((h) => h.home_id === c.homeId) && <option value={c.homeId}>Picked on map</option>}
        </select>
      </label>
      <div className="demo-row col">
        <span>Storm clock: <b>{clockLabel(tLocal)}</b> <small>(t = {tLocal.toFixed(1)} h)</small></span>
        <input type="range" min={scn.t_min} max={scn.t_max} step={0.1} value={tLocal} aria-label="Storm clock"
          onChange={(e) => { setTLocal(+e.target.value); set({ t: +e.target.value }); }} />
        <div className="demo-btns">
          <button onClick={() => setPlaying(!playing)}>{playing ? "Pause" : "Play"}</button>
          <select value={speed} onChange={(e) => setSpeed(+e.target.value)} aria-label="Play speed">
            <option value={0.5}>1 h / 2 s</option><option value={1}>1 h / s</option><option value={3}>3 h / s</option>
          </select>
        </div>
      </div>
      <div className="demo-row col">
        <span>Jump to</span>
        <div className="demo-btns wrap">
          {scn.moments.map((m: Moment) => (
            <button key={m.key} className={Math.abs(c.t - m.t) < 0.05 ? "on" : ""} onClick={() => { setPlaying(false); set({ t: m.t }); }}>{m.label}</button>
          ))}
        </div>
      </div>
      <label className="demo-row col">
        <span>Storm strength (simulated): <b>{Math.round(c.severity * 100) / 100}</b></span>
        <input type="range" min={0.1} max={1} step={0.05} value={c.severity} onChange={(e) => set({ severity: +e.target.value })} />
      </label>
      <label className="demo-row col">
        <span>Phone battery: <b>{battery}%</b> {battery < 20 && <small>(low-power mode)</small>}</span>
        <input type="range" min={1} max={100} step={1} value={battery} onChange={(e) => setBattery(+e.target.value)} />
      </label>
      <div className="demo-row">
        <span>Crews on line</span>
        <select value={c.crews ?? ""} onChange={(e) => set({ crews: e.target.value ? +e.target.value : null })}>
          <option value="">Auto (share of 150)</option>
          {Array.from({ length: 30 }, (_, i) => i + 1).map((n) => <option key={n} value={n}>{n}</option>)}
        </select>
      </div>
      <label className="demo-row"><span>Roads blocked</span><input type="checkbox" checked={c.accessBlocked} onChange={(e) => set({ accessBlocked: e.target.checked })} /></label>
      <label className="demo-row"><span>Switching (reroute power)</span><input type="checkbox" checked={c.switching} onChange={(e) => set({ switching: e.target.checked })} /></label>
      <label className="demo-row"><span>Extra damage on path</span>
        <input type="number" min={0} max={10} value={c.extraDamage} onChange={(e) => set({ extraDamage: Math.max(0, Math.min(10, +e.target.value || 0)) })} />
      </label>
      <label className="demo-row"><span>Low-power mode</span><input type="checkbox" checked={c.lowPower} onChange={(e) => set({ lowPower: e.target.checked })} /></label>
      <p className="demo-foot">Shortcut: press <kbd>D</kbd> or long-press the title. Open with <code>?demo=1</code>.</p>
    </aside>
  );
}
