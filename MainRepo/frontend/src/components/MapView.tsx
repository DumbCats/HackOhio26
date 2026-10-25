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
      center, zoom, maxZoom: 12, minZoom: 9, zoomControl: false, attributionControl: true,
      dragging: !!interactive, scrollWheelZoom: !!interactive, doubleClickZoom: !!interactive,
      touchZoom: !!interactive, boxZoom: false, keyboard: !!interactive,
    });
    L.tileLayer(TILES, { maxZoom: 12, attribution: "Tiles &copy; Esri" }).addTo(m);
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
        const band = { high: "High", medium: "Medium", low: "Low", unknown: "Too little history" }[c.risk_band];
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
      const pos = (i: number): [number, number] => {
        const angle = Math.PI * (0.65 + 0.35 * i);
        return [homeCenter[0] + 0.014 * Math.sin(angle), homeCenter[1] + 0.03 * Math.cos(angle)];
      };
      const open = steps.map((s, i) => [s, i] as const).filter(([s]) => s.center && s.status !== "done");
      if (open.length) {
        L.polyline([...open.map(([, i]) => pos(i)), homeCenter], { color: "#3A3A3C", weight: 3, dashArray: "6 6", opacity: 0.8, interactive: false }).addTo(g);
      }
      steps.forEach((s, i) => {
        if (!s.center) return;
        // Steps sit at ~1 km cell centers. Fan them out on a ring west of the home so pins and
        // labels never sit on the home pin or on each other (positions are illustrative anyway).
        const jitter = pos(i);
        L.marker(jitter, {
          interactive: false, keyboard: false,
          icon: L.divIcon({ className: "pin-wrap", html: `<div class="step-pin step-${s.status}">${s.order}</div>${s.status === "done" ? "" : `<div class="step-label"><b>${s.label}</b><span class="st-${s.status}">${STEP_TEXT[s.status]}</span></div>`}`, iconSize: [28, 28], iconAnchor: [14, 14] }),
        }).addTo(g);
      });
    }
  }, [homeCenter?.[0], homeCenter?.[1], steps, layer]); // eslint-disable-line react-hooks/exhaustive-deps

  return <div className="map" ref={el} role="img" aria-label={label} />;
}
