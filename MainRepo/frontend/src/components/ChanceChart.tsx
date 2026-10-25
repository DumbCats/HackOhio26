import { useState } from "react";
import type { Restoration } from "../types";

// Single series: cumulative chance power is back by each hour mark (Lane B Monte Carlo).
export function ChanceChart({ r }: { r: Restoration }) {
  const pts = r.chance_back_by;
  const [hover, setHover] = useState<number | null>(null);
  if (!pts.length || !r.estimate) return null;
  const W = 320, H = 120, padL = 8, padR = 8, padT = 12, padB = 24;
  const xMax = pts[pts.length - 1].t_from_now_h;
  const all = [{ t_from_now_h: 0, prob: 0 }, ...pts];
  const x = (h: number) => padL + (h / xMax) * (W - padL - padR);
  const y = (p: number) => padT + (1 - p) * (H - padT - padB);
  let d = `M${x(0)},${y(0)}`;
  for (let i = 1; i < all.length; i++) d += ` L${x(all[i].t_from_now_h)},${y(all[i].prob)}`;
  const area = `${d} L${x(xMax)},${y(0)} Z`;
  const e = r.estimate;
  const ticks = [0, Math.round(e.p10_h), Math.round(e.p90_h), xMax].filter((v, i, a) => a.indexOf(v) === i);
  const h = hover !== null ? all[hover] : null;
  return (
    <figure className="chance">
      <figcaption>Chance your power is back, by hours from now</figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img"
        aria-label={`About ${Math.round(e.p10_h)} hours: 1 in 10 chance back. About ${Math.round(e.p90_h)} hours: 9 in 10.`}
        onMouseLeave={() => setHover(null)}>
        <rect x={x(e.p10_h)} y={padT} width={Math.max(0, x(e.p90_h) - x(e.p10_h))} height={H - padT - padB} className="chance-band" rx="4" />
        <line x1={padL} x2={W - padR} y1={y(0)} y2={y(0)} className="chance-axis" />
        <line x1={padL} x2={W - padR} y1={y(0.5)} y2={y(0.5)} className="chance-grid" />
        <path d={area} className="chance-area" />
        <path d={d} className="chance-line" />
        {ticks.map((tk) => (
          <text key={tk} x={x(tk)} y={H - 6} textAnchor="middle" className="chance-tick">{tk}h</text>
        ))}
        {h && (
          <g>
            <line x1={x(h.t_from_now_h)} x2={x(h.t_from_now_h)} y1={padT} y2={y(0)} className="chance-cross" />
            <circle cx={x(h.t_from_now_h)} cy={y(h.prob)} r="5" className="chance-dot" />
          </g>
        )}
        {all.map((p, i) => (
          <rect key={i} x={x(p.t_from_now_h) - 14} y={0} width={28} height={H} fill="transparent"
            onMouseEnter={() => setHover(i)} onTouchStart={() => setHover(i)} />
        ))}
      </svg>
      <div className="chance-read" aria-live="polite">
        {h ? `By ${h.t_from_now_h} h from now: about ${Math.round(h.prob * 10)} in 10 chance it's back`
           : `Shaded: our range (1 in 10 to 9 in 10 chance)`}
      </div>
    </figure>
  );
}
