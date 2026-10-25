# Frontend (Lane C)

Phone-first React + Vite + TypeScript + Leaflet app built from `docs/design/` (Figma page 5).

```bash
npm install
npm run dev        # http://localhost:5173, talks to the backend on :8000
npm run build      # dist/ -> served by FastAPI at http://localhost:8000/
```

- Demo panel: open with `?demo=1`, press **D**, or long-press the title. Clock scrubber, jump-to-moment,
  play, storm strength, battery level (< 20% switches to low-power mode), crews, roads, switching, extra damage.
- URL params: `?t=4.2` (storm clock), `?home=p_…` (home id), `?demo=1`.
- Map tiles: Esri World Light Gray Base, capped at zoom 14 so no road names show (privacy rule 5).
- Every number carries a source chip (`Our estimate`, `Simulated utility feed`, `Utility confirmed`, `Safety guidance`).
  Red is used only for SAFETY.
