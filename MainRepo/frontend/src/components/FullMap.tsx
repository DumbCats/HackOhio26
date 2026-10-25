import { useState } from "react";
import type { Cell, Repairs } from "../types";
import { MapView, type Layer } from "./MapView";
import { SourceChip } from "./SourceChip";

const PHASES = ["Risk raised", "Damage reported", "Repair scheduled", "Repairs and restore"];
const STATUS = { in_progress: "In progress", waiting: "Waiting", done: "Done" } as const;

export function FullMap({ cells, center, homeCenter, repairs, phase, initialLayer, picking, onPick, onClose }: {
  cells: Cell[]; center: [number, number]; homeCenter: [number, number] | null; repairs: Repairs | null;
  phase: number; initialLayer: Layer; picking: boolean; onPick: (lat: number, lon: number) => void; onClose: () => void;
}) {
  const [layer, setLayer] = useState<Layer>(initialLayer);
  const steps = repairs?.steps ?? [];
  return (
    <div className="fullmap" role="dialog" aria-modal="true" aria-label="Map">
      <MapView cells={cells} layer={layer} center={center} homeCenter={homeCenter} steps={steps} zoom={13} interactive
        onTap={picking ? onPick : undefined} label="Map of outages and risk by area, about 1 km precision" />
      <div className="fm-top">
        <button className="round-btn" onClick={onClose} aria-label="Close map">
          <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden><path d="M9 4v5H4M15 20v-5h5M4 4l5 5M20 20l-5-5" stroke="currentColor" strokeWidth="2.2" fill="none" strokeLinecap="round" /></svg>
        </button>
        <div className="seg" role="tablist" aria-label="Map layer">
          <button role="tab" aria-selected={layer === "repairs"} className={layer === "repairs" ? "on" : ""} onClick={() => setLayer("repairs")}>Repairs</button>
          <button role="tab" aria-selected={layer === "risk"} className={layer === "risk" ? "on" : ""} onClick={() => setLayer("risk")}>Risk bands</button>
        </div>
      </div>
      <div className="fm-legend">
        {layer === "repairs" ? (
          <><span><i className="lg out" />Power out</span><span><i className="lg partial" />Some out</span><span><i className="lg area" />Your area</span></>
        ) : (
          <><span><i className="lg low" />Lower</span><span><i className="lg med" />Moderate</span><span><i className="lg high" />Higher</span><span><i className="lg unk" />Not enough history</span></>
        )}
      </div>
      {picking && <div className="pick-hint" role="status">Tap an area to see its outlook</div>}
      {!picking && (
        <div className="fm-sheet">
          <div className="sheet-grabber" aria-hidden />
          <div className="section-head small"><h2>Repair progress</h2><SourceChip source="simulated_feed" /></div>
          <div className="phase4">
            {PHASES.map((p, i) => (
              <div key={p} className={i <= phase ? "on" : ""}><span /><small className={i === phase ? "cur" : ""}>{p}</small></div>
            ))}
          </div>
          {steps.length === 0 ? (
            <p className="muted">No repairs on the line that feeds you right now.</p>
          ) : (
            <ol className="repair-list">
              {steps.map((s, i) => (
                <li key={s.order}>
                  <span className={`num ${s.status}`}>{s.order}</span>
                  <div><b>Step {s.order}: {s.label.toLowerCase()}</b><small>Repair order: {i === 0 ? "first" : i === steps.length - 1 ? "last" : "next"}</small></div>
                  <span className={`status-pill ${s.status}`}>{STATUS[s.status]}</span>
                </li>
              ))}
            </ol>
          )}
          <p className="muted small center">{repairs?.note ?? "Locations shown at about 1 km precision. Only the utility confirms restoration."}</p>
        </div>
      )}
    </div>
  );
}
