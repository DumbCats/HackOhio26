import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { Cell, RepairStep } from "../types";

export type Layer = "repairs" | "risk";

const RISK_COLOR: Record<string, string> = { high: "#FF9500", medium: "#FFCC00", low: "#34C759", unknown: "#AEAEB2" };
const STEP_TEXT: Record<string, string> = { in_progress: "In progress", waiting: "Waiting", done: "Done" };

// No-label basemap: the rules forbid road names on the map.
const TILES = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}";

export function MapView({ cells, layer, center, homeCenter, steps, interactive, zoom, onTap, label }: {
  cells: Cell[]; layer: Layer; center: [number, number]; homeCenter: [number, number] | null;
  steps?: RepairStep[]; interactive?: boolean; zoom: number; onTap?: (lat: number, lon: number) => void; label: string;
}) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const cellLayer = useRef<L.LayerGroup | null>(null);
  const overlay = useRef<L.LayerGroup | null>(null);
  const tapRef = useRef(onTap);
  tapRef.current = onTap;

  useEffect(() => {
    if (!el.current) return;
    const m = L.map(el.current, {
      center, zoom, maxZoom: 14, minZoom: 9, zoomControl: false, attributionControl: true,
      dragging: !!interactive, scrollWheelZoom: !!interactive, doubleClickZoom: !!interactive,
      touchZoom: !!interactive, boxZoom: false, keyboard: !!interactive,
    });
    L.tileLayer(TILES, { maxZoom: 14, attribution: "Tiles &copy; Esri" }).addTo(m);
    cellLayer.current = L.layerGroup().addTo(m);
    overlay.current = L.layerGroup().addTo(m);
    m.on("click", (e: L.LeafletMouseEvent) => tapRef.current?.(e.latlng.lat, e.latlng.lng));
    map.current = m;
    const ro = new ResizeObserver(() => m.invalidateSize());
    ro.observe(el.current);
    return () => { ro.disconnect(); m.remove(); map.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    map.current?.setView(homeCenter ?? center, map.current.getZoom(), { animate: false });
  }, [homeCenter?.[0], homeCenter?.[1]]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const g = cellLayer.current;
    if (!g) return;
    g.clearLayers();
    for (const c of cells) {
      let style: L.PathOptions;
      if (layer === "risk") {
        style = { color: RISK_COLOR[c.risk_band], weight: 0, fillColor: RISK_COLOR[c.risk_band], fillOpacity: 0.32 };
      } else {
        if (c.status === "on") continue;
        style = { color: "#3A3A3C", weight: 0, fillColor: "#3A3A3C", fillOpacity: c.status === "out" ? 0.5 : 0.22 };
      }
      const r = L.rectangle(c.bounds, { ...style, interactive: !!interactive });
      if (interactive) {
        const band = { high: "High", medium: "Moderate", low: "Lower", unknown: "Not enough history" }[c.risk_band];
        r.bindTooltip(layer === "risk" ? `Risk: ${band}` : `${c.homes_out} of ${c.homes} homes out`, { sticky: true });
      }
      g.addLayer(r);
    }
  }, [cells, layer, interactive]);

  useEffect(() => {
    const g = overlay.current;
    if (!g) return;
    g.clearLayers();
    if (homeCenter) {
      L.circle(homeCenter, { radius: 700, color: "#007AFF", weight: 1.5, dashArray: "4 5", fillColor: "#007AFF", fillOpacity: 0.08, interactive: false }).addTo(g);
      L.marker(homeCenter, {
        interactive: false, keyboard: false,
        icon: L.divIcon({ className: "pin-wrap", html: `<div class="home-pin" aria-hidden="true"><svg viewBox="0 0 24 24" width="16" height="16"><path fill="#fff" d="M12 4 3 11h2.5v8h5v-5h3v5h5v-8H21z"/></svg></div><div class="pin-label">Your area</div>`, iconSize: [36, 36], iconAnchor: [18, 18] }),
      }).addTo(g);
    }
    if (layer === "repairs" && steps && homeCenter) {
      const pts = steps.filter((s) => s.center && s.status !== "done");
      if (pts.length) {
        L.polyline([...pts.map((s) => s.center!), homeCenter], { color: "#3A3A3C", weight: 3, dashArray: "6 6", opacity: 0.8, interactive: false }).addTo(g);
      }
      steps.forEach((s, i) => {
        if (!s.center) return;
        // Steps sit at ~1 km cell centers; nudge them apart and off the home pin so labels stay readable.
        let jitter: [number, number] = [s.center[0] + 0.0015 * (i % 2 ? 1 : -1), s.center[1] - 0.004 * (i + 1)];
        if (Math.abs(jitter[0] - homeCenter[0]) < 0.004 && Math.abs(jitter[1] - homeCenter[1]) < 0.006) {
          jitter = [homeCenter[0] + 0.005 + 0.002 * i, homeCenter[1] - 0.012];
        }
        L.marker(jitter, {
          interactive: false, keyboard: false,
          icon: L.divIcon({ className: "pin-wrap", html: `<div class="step-pin step-${s.status}">${s.order}</div><div class="step-label"><b>${s.label}</b><span class="st-${s.status}">${STEP_TEXT[s.status]}</span></div>`, iconSize: [28, 28], iconAnchor: [14, 14] }),
        }).addTo(g);
      });
    }
  }, [homeCenter?.[0], homeCenter?.[1], steps, layer]); // eslint-disable-line react-hooks/exhaustive-deps

  return <div className="map" ref={el} role="img" aria-label={label} />;
}
