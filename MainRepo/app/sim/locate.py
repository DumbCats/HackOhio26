"""Map tap -> an anonymized home in that ~1 km area (contracts/API.md: locate.json)."""
from __future__ import annotations

from functools import lru_cache

from app.sim.feed import get_feed
from app.sim.mapcells import _cells


def area_label(cell_id: str | None) -> str:
    return f"Area {int(cell_id[2:])}" if cell_id and cell_id[2:].isdigit() else "Your area"


@lru_cache(maxsize=1)
def _representatives() -> dict[str, str]:
    """cell_id -> one home in it with a network match (first by hashed id, so it is arbitrary)."""
    f = get_feed()
    rep: dict[str, str] = {}
    for k, c, p in zip(f.keys, f.cell, f.paths):
        if p and c not in rep:
            rep[c] = k
    return rep


def locate(lat: float, lon: float) -> dict:
    """Nearest visible cell to the tap; returns that cell and a home inside it."""
    cells, _ = _cells()
    reps = _representatives()
    best = None
    for c in cells:
        if c["cell_id"] not in reps:
            continue
        (s, w), (n, e) = c["bounds"]
        inside = s <= lat < n and w <= lon < e
        d = 0.0 if inside else (c["center"][0] - lat) ** 2 + ((c["center"][1] - lon) * 0.8) ** 2
        if best is None or d < best[0]:
            best = (d, c["cell_id"])
    if best is None:
        raise KeyError("no area")
    cid = best[1]
    return {"cell_id": cid, "home_id": reps[cid], "area": area_label(cid)}
