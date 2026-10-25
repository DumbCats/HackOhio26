import type { Forecast, HomeInfo, Restoration, TimelineMsg } from "../types";
import { BAND_TEXT, clockLabel, rangeLabel, STAGES, stageIndex, windowLabel } from "../format";
import { SourceChip } from "./SourceChip";
import { ChanceChart } from "./ChanceChart";

export type Mode = "forecast" | "outage" | "restored";

export function modeOf(r: Restoration | null, t: number): Mode {
  if (!r) return "forecast";
  if (r.restored_at_t !== null && t >= r.restored_at_t && !r.is_out) return "restored";
  return r.is_out ? "outage" : "forecast";
}

function Phase({ idx }: { idx: number }) {
  return (
    <div className="phase" aria-label={`Step ${idx + 1} of 5: ${STAGES[idx].label}`}>
      {STAGES.map((s, i) => <span key={s.key} className={i <= idx ? "on" : ""} />)}
    </div>
  );
}

const ICON = {
  bolt: <svg viewBox="0 0 24 24" width="13" height="13" aria-hidden><path fill="currentColor" d="M13 2 4 14h6l-1 8 9-12h-6z" /></svg>,
  search: <svg viewBox="0 0 24 24" width="13" height="13" aria-hidden><circle cx="10" cy="10" r="6" stroke="currentColor" strokeWidth="2.5" fill="none" /><path d="m15 15 6 6" stroke="currentColor" strokeWidth="2.5" /></svg>,
  clock: <svg viewBox="0 0 24 24" width="13" height="13" aria-hidden><circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2.5" fill="none" /><path d="M12 7v5l3 2" stroke="currentColor" strokeWidth="2.5" fill="none" /></svg>,
  steps: <svg viewBox="0 0 24 24" width="13" height="13" aria-hidden><path d="M4 20 20 4" stroke="currentColor" strokeWidth="2.5" /><path d="M8 20h-4v-4" stroke="currentColor" strokeWidth="2.5" fill="none" /></svg>,
};

export function StatusCard({ mode, r, f, home, lastUpdate, onChange, onTrust }: {
  mode: Mode; r: Restoration | null; f: Forecast | null; home: HomeInfo | null;
  lastUpdate: TimelineMsg | null; onChange: () => void; onTrust: () => void;
}) {
  if (mode === "forecast") return <ForecastCard f={f} home={home} onTrust={onTrust} />;
  if (mode === "restored" && r) return <RestoredCard r={r} onTrust={onTrust} />;
  if (!r) return null;
  const e = r.estimate;
  const idx = stageIndex(r.status?.stage, r.is_out, false);
  return (
    <section className="card-section" aria-labelledby="status-h">
      <div className="section-head">
        <h2 id="status-h">Current status</h2>
        <SourceChip source="simulated_feed" />
      </div>
      <div className="grid-card">
        <div className="cell">
          <div className="k">{ICON.bolt} STATUS</div>
          <div className="v">Outage</div>
          <div className="s">Since {r.out_since_t !== null ? clockLabel(r.out_since_t) : "recently"}</div>
        </div>
        <div className="cell">
          <div className="k">{ICON.search} CAUSE</div>
          <div className="v v-sm">{r.cause ? r.cause.label.replace(/ on the line that feeds your home| upstream of your street| near your street| near your home/, "") : "Not yet determined"}</div>
          <div className="s">{r.cause ? "Probable cause" : "Being assessed"}</div>
        </div>
        <div className="cell">
          <div className="k">{ICON.clock} EXPECTED TIME</div>
          {e ? <div className="v">{rangeLabel(e.p10_h, e.p90_h)}</div> : <div className="v v-sm">Can't estimate</div>}
          {e?.back_by_t_low != null && e.back_by_t_high != null && (
            <div className="s s-strong">about {windowLabel(e.back_by_t_low, e.back_by_t_high)}</div>
          )}
          <div className="s">Our estimate · not confirmed</div>
        </div>
        <div className="cell">
          <div className="k">{ICON.steps} PHASE</div>
          <div className="v">Step {idx + 1} of 5</div>
          <div className="s">{STAGES[idx].label}</div>
          <Phase idx={idx} />
        </div>
        <div className="row-foot">
          <span>Customers on your line</span><b>{home?.customers_on_line ?? "—"}</b>
        </div>
        <div className="row-foot muted">
          <span>Utility-confirmed time</span>
          <span><SourceChip source="utility_confirmed" muted /> not available in this demo</span>
        </div>
      </div>


      {r.fallback && (
        <div className="fallback-card">
          <b>We can't estimate this reliably.</b>
          <p>{r.fallback.message}</p>
          <a className="btn" href={r.fallback.link} target="_blank" rel="noreferrer">Official outage page</a>
        </div>
      )}

      {e && (
        <div className="card estimate-card">
          <div className="section-head small">
            <h3>{e.headline}</h3>
            <SourceChip source="model_estimate" />
          </div>
          {e.back_by_t_low != null && e.back_by_t_high != null && (
            <p className="back-by">Back by about <b>{windowLabel(e.back_by_t_low, e.back_by_t_high)}</b></p>
          )}
          {lastUpdate?.shift_h != null && r.t - lastUpdate.t < 6 && (
            <p className="update-pill" role="status">
              Updated {clockLabel(lastUpdate.t)}: about {Math.max(1, Math.round(Math.abs(lastUpdate.shift_h)))} hours {lastUpdate.shift_h > 0 ? "later" : "sooner"} than before
            </p>
          )}
          <p className="muted">Confidence: <b>{e.confidence}</b>. An estimate, not a promise.</p>
          <ChanceChart r={r} />
          {r.step_restoration && <p className="step-note">{r.step_restoration.message}</p>}
          <div className="btn-row">
            <button className="btn btn-primary" onClick={onChange}>What could change this?</button>
            <button className="btn" onClick={onTrust}>How sure are we?</button>
          </div>
        </div>
      )}
    </section>
  );
}

function ForecastCard({ f, home, onTrust }: { f: Forecast | null; home: HomeInfo | null; onTrust: () => void }) {
  if (!f) return null;
  const until = f.storm.hours_until_storm;
  if (f.fallback) {
    return (
      <section className="card-section" aria-labelledby="fc-h">
        <div className="section-head"><h2 id="fc-h">Will I lose power?</h2></div>
        <div className="fallback-card">
          <b>We can't predict this reliably</b>
          <p>{f.fallback.message}</p>
          <a className="btn btn-primary" href={f.fallback.link} target="_blank" rel="noreferrer">Official outage page</a>
          <button className="btn" onClick={onTrust}>Why not?</button>
        </div>
      </section>
    );
  }
  const band = f.risk.band;
  return (
    <section className="card-section" aria-labelledby="fc-h">
      <div className="section-head"><h2 id="fc-h">Will I lose power?</h2><SourceChip source="model_estimate" /></div>
      <div className="card">
        <div className="risk-row">
          <span className={`band band-${band}`}>{BAND_TEXT[band]} risk</span>
          <span className="muted">compared with nearby homes</span>
        </div>
        <p className="lead">{until > 0 ? `Winter storm expected in about ${Math.round(until)} hours.` : "The storm is here."} Your power is on.</p>
        {f.risk.rank_note && <p className="muted">{f.risk.rank_note}</p>}
        <h3 className="mini-h">Why</h3>
        <ul className="factors">
          {f.risk.factors.map((x) => (
            <li key={x.label}>
              <span className={`arrow ${x.direction}`} aria-label={x.direction === "up" ? "raises risk" : "lowers risk"}>{x.direction === "up" ? "↑" : "↓"}</span>
              {x.label}
            </li>
          ))}
        </ul>
        <div className="conf-row">
          <span>Confidence: <b>{f.risk.confidence}</b></span>
          <button className="link-btn" onClick={onTrust}>How sure are we?</button>
        </div>
        {f.risk.note && <p className="note">{f.risk.note}</p>}
        {home && <div className="row-foot plain"><span>Customers on your line</span><b>{home.customers_on_line}</b></div>}
      </div>
    </section>
  );
}

function RestoredCard({ r, onTrust }: { r: Restoration; onTrust: () => void }) {
  const rc = r.recap;
  const line = (label: string, x: NonNullable<typeof rc>["first_estimate"]) => x && (
    <li>
      <span className={`tick ${x.within_range ? "ok" : "miss"}`} aria-hidden>{x.within_range ? "✓" : "✗"}</span>
      <span>{label}: back {clockLabel(x.back_by_t_low)} to {clockLabel(x.back_by_t_high)}</span>
      <span className="muted">{x.within_range ? "caught it" : "missed"}</span>
    </li>
  );
  return (
    <section className="card-section" aria-labelledby="rs-h">
      <div className="section-head"><h2 id="rs-h">Power is back</h2><SourceChip source="simulated_feed" /></div>
      <div className="card restored-card">
        <div className="restored-hero">
          <span className="ok-badge" aria-hidden>{"✓"}</span>
          <div>
            <b>Your power came back {r.restored_at_t !== null ? clockLabel(r.restored_at_t) : ""}.</b>
            {rc && <p className="muted">Out for about {Math.max(1, Math.round(rc.actual_h))} hours.</p>}
          </div>
        </div>
        {rc && (
          <>
            <h3 className="mini-h">Our range vs what happened <SourceChip source="model_estimate" /></h3>
            <ul className="recap">
              {line("First estimate", rc.first_estimate)}
              {line("After new damage was found", rc.updated_estimate)}
            </ul>
            <p>{rc.message}</p>
          </>
        )}
        <button className="link-btn" onClick={onTrust}>How sure were we?</button>
      </div>
    </section>
  );
}
