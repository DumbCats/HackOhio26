# Planning prototype (reference only, not production code)

Stdlib-only scripts written while planning, to prove the storm replay works. Lane A may borrow from them.

- `lib.py`: tiny DBF + point-shapefile reader. `xwalk.py`: derives `ingest/circuit_crosswalk.json`. `map3.py`: damage → device mapping.
- `build.py`: hashed homes + upstream paths + damage → device keys + base hours.
- `sim.py`, `replay.py`, `sweep.py`, `share.py`: scheduler + crew calibration (a regional pool of 150 matches ARCOS).
- `mc.py`, `story.py`, `cands.py`, `final.py`, `ko.py`: Monte Carlo + story-home search.

Paths in the scripts point at a temp folder; adjust before running. The salt in `build.py` is a throwaway.
