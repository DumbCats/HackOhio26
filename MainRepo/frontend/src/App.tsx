import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api";
import type { Alerts, ChatMsg, Controls, Forecast, HomeInfo, OutageMap, Prep, Repairs, Restoration, Scenario, TimelineMsg } from "./types";
import { BAND_TEXT, clockLabel, OUTAGE_LINK, rangeLabel, STAGES, stageIndex } from "./format";
import { MapView } from "./components/MapView";
import { modeOf, StatusCard } from "./components/StatusCard";
import { AlertsSheet, ChangeSheet, HomeSheet, PrepareSheet, SafetyCard, TrustSheet } from "./components/Sheets";
import { ChatBar, ChatSheet } from "./components/Chat";
import { FullMap } from "./components/FullMap";
import { DemoPanel, LowPowerView, Notification } from "./components/Extras";

type SheetName = "prepare" | "alerts" | "trust" | "change" | "home" | null;

interface Data {
  forecast: Forecast | null; restoration: Restoration | null; prep: Prep | null; alerts: Alerts | null;
  home: HomeInfo | null; repairs: Repairs | null; map: OutageMap | null;
}
const EMPTY: Data = { forecast: null, restoration: null, prep: null, alerts: null, home: null, repairs: null, map: null };

const params = new URLSearchParams(location.search);

const SUGGEST: Record<string, string[]> = {
  forecast: ["Will I lose power?", "What should I do to prepare?", "Do I qualify for outage alerts?", "What is a risk band?"],
  outage: ["When will my power be back?", "My insulin is in the fridge, what do I do?", "What could change this?", "How sure are you?"],
  restored: ["Is my food still safe?", "How long was I out?", "How often has my line been damaged before?"],
};

export default function App() {
  const [scn, setScn] = useState<Scenario | null>(null);
  const [c, setC] = useState<Controls | null>(null);
  const [data, setData] = useState<Data>(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const [sheet, setSheet] = useState<SheetName>(null);
  const [chatOpen, setChatOpen] = useState(false);
  const [mapOpen, setMapOpen] = useState<null | "view" | "pick">(null);
  const [demo, setDemo] = useState(params.get("demo") === "1");
  const [battery, setBattery] = useState(86);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [notif, setNotif] = useState<TimelineMsg | null>(null);
  const [chats, setChats] = useState<Record<string, ChatMsg[]>>({});
  const [busy, setBusy] = useState(false);
  const notifiedUpTo = useRef<number>(-Infinity);
  const lastHome = useRef<string>("");

  const set = useCallback((p: Partial<Controls>) => setC((prev) => (prev ? { ...prev, ...p } : prev)), []);

  // ---- boot
  useEffect(() => {
    api.scenario().then((s) => {
      setScn(s);
      const t = params.get("t");
      setC({
        homeId: params.get("home") ?? s.default_home_id,
        t: t !== null && !Number.isNaN(+t) ? +t : s.t_now_default,
        severity: 0.8, crews: null, accessBlocked: false, extraDamage: 0, switching: true, needs: [], lowPower: false,
      });
    }).catch(() => setError("We can't reach the outage service right now."));
    // Real battery level when the browser exposes it (W2); the demo slider overrides it.
    const nav = navigator as Navigator & { getBattery?: () => Promise<{ level: number }> };
    nav.getBattery?.().then((b) => setBattery(Math.round(b.level * 100))).catch(() => {});
  }, []);

  const lowPower = !!c && (c.lowPower || battery < 20);
  const effective = useMemo(() => (c ? { ...c, lowPower } : null), [c, lowPower]);

  // ---- data (debounced so scrubbing the clock stays smooth)
  useEffect(() => {
    if (!effective) return;
    const ctl = new AbortController();
    const id = setTimeout(async () => {
      try {
        const s = ctl.signal;
        const mapT = Math.round(effective.t * 4) / 4;
        const [forecast, restoration, prep, alerts, home, repairs, map] = await Promise.all([
          api.forecast(effective, s), api.restoration(effective, s), api.prep(effective, s), api.alerts(effective, s),
          api.home(effective.homeId, s), api.repairs(effective.homeId, effective.t, s),
          lowPower ? Promise.resolve(null) : api.outageMap(mapT, effective.severity, s),
        ]);
        setData((d) => ({ forecast, restoration, prep, alerts, home, repairs, map: map ?? d.map }));
        setError(null);
      } catch (e) {
        if ((e as Error).name !== "AbortError") setError("We can't reach the outage service right now.");
      }
    }, 120);
    return () => { clearTimeout(id); ctl.abort(); };
  }, [effective, lowPower]);

  // ---- notifications: a banner when the clock passes a message's time (C8)
  useEffect(() => {
    const a = data.alerts;
    if (!a || !c || a.home_id !== c.homeId) return;
    if (lastHome.current !== c.homeId) {
      notifiedUpTo.current = lastHome.current ? c.t : -Infinity;  // first load shows the current message
      lastHome.current = c.homeId;
    }
    if (c.t < notifiedUpTo.current) { notifiedUpTo.current = c.t; return; }
    const fresh = a.timeline.filter((m) => m.t > notifiedUpTo.current && m.t <= c.t);
    if (fresh.length) setNotif(fresh[fresh.length - 1]);
    notifiedUpTo.current = Math.max(notifiedUpTo.current, a.t);
  }, [data.alerts]); // eslint-disable-line react-hooks/exhaustive-deps

  // ---- clock playback
  useEffect(() => {
    if (!playing || !scn) return;
    const id = setInterval(() => setC((p) => {
      if (!p) return p;
      const t = Math.round((p.t + speed * 0.25) * 100) / 100;
      if (t >= scn.t_max) { setPlaying(false); return { ...p, t: scn.t_max }; }
      return { ...p, t };
    }), 250);
    return () => clearInterval(id);
  }, [playing, speed, scn]);

  // ---- demo shortcuts
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA") return;
      if (e.key === "d" || e.key === "D") setDemo((v) => !v);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  const press = useRef<number | null>(null);
  const startPress = () => { press.current = window.setTimeout(() => setDemo((v) => !v), 600); };
  const endPress = () => { if (press.current) clearTimeout(press.current); press.current = null; };

  const pickHome = (homeId: string) => { set({ homeId, crews: null, extraDamage: 0 }); setSheet(null); };

  if (error && !scn) {
    return (
      <div className="stage"><div className="phone"><main className="screen error-screen">
        <h1>Outage Outlook</h1>
        <div className="fallback-card"><b>{error}</b><p>For outage updates, use the official outage page.</p>
          <a className="btn btn-primary" href={OUTAGE_LINK} target="_blank" rel="noreferrer">Official outage page</a></div>
      </main></div></div>
    );
  }
  if (!scn || !c) return <div className="stage"><div className="phone"><main className="screen loading">Loading your outlook…</main></div></div>;

  const { forecast: f, restoration: r, prep, alerts, home, repairs, map } = data;
  const mode = modeOf(r, c.t);
  const homeLabel = scn.homes.find((h) => h.home_id === c.homeId);
  const center = home?.center ?? scn.map_center;
  const layer = mode === "forecast" ? "risk" : "repairs";
  const idx = stageIndex(r?.status?.stage, !!r?.is_out, mode === "restored");
  const ctxText = mode === "outage" && r?.estimate
    ? `Outage · Step ${idx + 1} of 5 · ${rangeLabel(r.estimate.p10_h, r.estimate.p90_h)} (our estimate)`
    : mode === "restored" ? "Power is back" : f?.fallback ? "Power on · risk can't be predicted" : `Power on · ${BAND_TEXT[f?.risk.band ?? "unknown"]} risk (our estimate)`;
  const messages = chats[c.homeId] ?? [];

  const sendChat = async (text: string) => {
    const next: ChatMsg[] = [...messages, { role: "user", content: text }];
    setChats((m) => ({ ...m, [c.homeId]: next }));
    setBusy(true);
    try {
      const res = await api.chat({ ...c, lowPower }, next);
      setChats((m) => ({ ...m, [c.homeId]: [...next, { role: "assistant", content: res.reply, source: res.source, safety_flag: res.safety_flag, tools_used: res.tools_used }] }));
    } catch {
      setChats((m) => ({ ...m, [c.homeId]: [...next, { role: "assistant", content: `I can't reach the assistant right now. For outage news see ${OUTAGE_LINK}. In an emergency, call 911.`, source: "fallback" }] }));
    } finally {
      setBusy(false);
    }
  };

  const onPickMap = async (lat: number, lon: number) => {
    try {
      const loc = await api.locate(lat, lon);
      setMapOpen(null);
      pickHome(loc.home_id);
    } catch { /* tapped outside the service area */ }
  };

  const chatSheet = chatOpen && (
    <ChatSheet context={ctxText} suggestions={SUGGEST[mode]} messages={messages} busy={busy}
      onSend={sendChat} onClose={() => setChatOpen(false)} />
  );

  return (
    <div className={`stage${demo ? " with-demo" : ""}`}>
      <div className={`phone${lowPower ? " phone-dark" : ""}`}>
        <div className="statusbar" aria-hidden>
          <span>{clockLabel(c.t).split(" ").slice(1).join(" ")}</span>
          <span className="sb-right">
            <span className={`batt${battery < 20 ? " low" : ""}`}><i style={{ width: `${battery}%` }} /></span>
          </span>
        </div>
        {lowPower ? (
          <LowPowerView r={r} f={f} prep={prep} mode={mode} battery={battery} onChat={() => setChatOpen(true)}
            onExit={() => { set({ lowPower: false }); if (battery < 20) setBattery(25); }} />
        ) : (
          <main className="screen">
            <header className="app-head" onPointerDown={startPress} onPointerUp={endPress} onPointerLeave={endPress}>
              <div>
                <h1>Outage Outlook</h1>
                <button className="home-btn" onClick={() => setSheet("home")} aria-haspopup="dialog">
                  {homeLabel ? `${homeLabel.label} · ` : ""}{home?.area ?? "Your area"} (anonymized)
                  <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden><path d="M2 3.5l3 3 3-3" stroke="currentColor" strokeWidth="1.6" fill="none" /></svg>
                </button>
              </div>
              <button className="icon-btn lp-btn" onClick={() => set({ lowPower: true })} aria-label="Switch to low-power mode" title="Low-power mode">
                <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden><rect x="2" y="7" width="18" height="10" rx="2.5" stroke="currentColor" strokeWidth="2" fill="none" /><rect x="4.5" y="9.5" width="5" height="5" rx="1" fill="currentColor" /><path d="M22 10.5v3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg>
              </button>
            </header>
            <div className="clock-strip">
              <span>{clockLabel(c.t)}</span>
              <span className="muted">Simulated storm replay (Feb 2025 damage)</span>
            </div>
            {error && <div className="warn-banner" role="alert">{error} Showing the last update.</div>}

            <div className="map-box">
              {map && <MapView cells={map.cells} layer={layer} center={center} homeCenter={home?.center ?? null}
                steps={repairs?.steps} zoom={12} label={layer === "risk" ? "Risk bands near you" : "Outages near you"} />}
              <button className="map-chip" onClick={() => setMapOpen("view")}>
                <span className={`dot ${mode === "outage" ? "dark" : ""}`} />{layer === "risk" ? "Risk near you" : "Repairs near you"}
                <svg width="8" height="10" viewBox="0 0 8 10" aria-hidden><path d="M2 1l4 4-4 4" stroke="currentColor" strokeWidth="1.8" fill="none" /></svg>
              </button>
              <div className="map-tools">
                <button className="map-tool" onClick={() => setMapOpen("view")} aria-label="Expand map">
                  <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden><path d="M14 4h6v6M10 20H4v-6M20 4l-7 7M4 20l7-7" stroke="currentColor" strokeWidth="2.2" fill="none" strokeLinecap="round" /></svg>
                </button>
                <button className="map-tool" onClick={() => setMapOpen("pick")} aria-label="Pick an area on the map">
                  <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden><path fill="currentColor" d="M21 3 3 10.5l7 2.5 2.5 7z" /></svg>
                </button>
              </div>
              <div className="map-legend">
                {layer === "risk"
                  ? <><span><i className="lg low" />Lower</span><span><i className="lg med" />Moderate</span><span><i className="lg high" />Higher</span></>
                  : <><span><i className="lg out" />Power out</span><span><i className="lg partial" />Some out</span><span>{map ? `${map.summary.homes_out.toLocaleString()} homes out` : ""}</span></>}
              </div>
            </div>

            <StatusCard mode={mode} r={r} f={f} home={home} onChange={() => setSheet("change")} onTrust={() => setSheet("trust")} />

            {mode === "outage" ? <SafetyCard prep={prep} /> : (
              <a className="emergency" href="tel:911">
                <span className="em-icon" aria-hidden><svg viewBox="0 0 24 24" width="14" height="14"><path fill="#fff" d="M6.6 10.8a15 15 0 0 0 6.6 6.6l2.2-2.2c.3-.3.7-.4 1-.2 1.1.4 2.3.6 3.6.6.6 0 1 .4 1 1V20c0 .6-.4 1-1 1A17 17 0 0 1 3 4c0-.6.4-1 1-1h3.5c.6 0 1 .4 1 1 0 1.3.2 2.5.6 3.6.1.3 0 .7-.2 1z" /></svg></span>
                <span><b>Emergency?</b> Call 911 for injury, fire, or a downed line.</span>
              </a>
            )}

            <nav className="tiles" aria-label="More">
              <button onClick={() => setSheet("prepare")}><b>{mode === "outage" ? "What to do now" : mode === "restored" ? "After the outage" : "Prepare"}</b><small>{prep ? `${prep.actions.length} steps${c.needs.length ? " · tailored" : ""}` : ""}</small></button>
              <button onClick={() => setSheet("alerts")}><b>Alerts</b><small>{alerts ? `${alerts.timeline.length} received` : ""}</small></button>
              <button onClick={() => setSheet("trust")}><b>How sure are we?</b><small>Confidence & data</small></button>
              {mode === "outage" && <button onClick={() => setSheet("change")}><b>What could change this?</b><small>Crews, roads</small></button>}
            </nav>
            <p className="foot-note">Demo with anonymized AEP data. Not an official outage service.</p>
            <div className="chat-spacer" />
          </main>
        )}
        {!lowPower && <ChatBar onOpen={() => setChatOpen(true)} />}

        <Notification msg={notif} onDismiss={() => setNotif(null)} onOpen={() => { setNotif(null); setSheet("alerts"); }} />
        {sheet === "prepare" && <PrepareSheet prep={prep} needs={c.needs} setNeeds={(needs) => set({ needs })} onClose={() => setSheet(null)} />}
        {sheet === "alerts" && <AlertsSheet alerts={alerts} onClose={() => setSheet(null)} />}
        {sheet === "trust" && <TrustSheet f={f} r={r} onClose={() => setSheet(null)} />}
        {sheet === "change" && <ChangeSheet r={r} c={c} set={set} onClose={() => setSheet(null)} />}
        {sheet === "home" && <HomeSheet homes={scn.homes} current={c.homeId} onPick={pickHome}
          onMap={() => { setSheet(null); setMapOpen("pick"); }} onClose={() => setSheet(null)} />}
        {mapOpen && map && (
          <FullMap cells={map.cells} center={center} homeCenter={home?.center ?? null} repairs={repairs}
            phase={Math.min(3, idx)} initialLayer={mapOpen === "pick" ? "risk" : layer} picking={mapOpen === "pick"}
            onPick={onPickMap} onClose={() => setMapOpen(null)} />
        )}
        {chatSheet}
      </div>
      {demo && (
        <DemoPanel scn={scn} c={c} set={set} battery={battery} setBattery={setBattery} playing={playing}
          setPlaying={setPlaying} speed={speed} setSpeed={setSpeed} onClose={() => setDemo(false)} />
      )}
      <span className="sr-only" aria-live="polite">{STAGES[idx]?.label}</span>
    </div>
  );
}
