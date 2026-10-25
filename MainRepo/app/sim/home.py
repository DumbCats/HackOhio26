"""Customer-safe home summary and repair progress (frontend status + expanded map).

Additions to the contract (new endpoints, nothing renamed):
  GET /api/home/{home_id}            area label, ~1 km cell center, customers on the line (rounded)
  GET /api/repairs/{home_id}?t=      the repairs on this home's path that are known at t, in
                                     repair order, with generic labels and ~1 km cell centers.
No device/circuit ids, no exact points, no crew info: a step is "in_progress", "waiting" or "done".
"""
from __future__ import annotations

from app.sim.feed import get_feed, path_jobs
from app.sim.locate import area_label
from app.sim.mapcells import cell_center


def _about(n: int) -> str:
    if n < 100:
        return "fewer than 100"
    step = 100 if n < 2000 else 500
    return f"about {int(round(n / step) * step):,}"


def get_home(home_id: str) -> dict:
    f = get_feed()
    i = f.idx(home_id)
    cid = f.cell[i]
    return {
        "home_id": home_id, "cell_id": cid, "area": area_label(cid),
        "center": cell_center(cid), "precision": "about 1 km",
        "customers_on_line": _about(f.circuit_homes[f.circuit[i]]),
        "network_match": bool(f.paths[i]),
        "source": "simulated_feed",
    }


STEP_LABELS = ["Upstream equipment", "Equipment nearer you", "Equipment on your block"]


def get_repairs(home_id: str, t: float = 0) -> dict:
    f = get_feed()
    i = f.idx(home_id)
    jobs = sorted(path_jobs(home_id, float(t)), key=lambda j: (j["priority"], j["report_t"]))
    steps = []
    n = len(jobs)
    for k, j in enumerate(jobs):
        if n == 1:
            label = "Equipment that feeds you"
        elif k == n - 1:
            label = STEP_LABELS[2]
        elif k == 0:
            label = STEP_LABELS[0]
        else:
            label = STEP_LABELS[1]
        steps.append({"order": k + 1, "label": label, "status": j["status"],
                      "center": cell_center(j["cell_id"]) if j.get("cell_id") else None,
                      "reported_t": round(j["report_t"], 1)})
    return {
        "home_id": home_id, "t": float(t), "source": "simulated_feed",
        "home_center": cell_center(f.cell[i]), "steps": steps,
        "note": "Locations shown at about 1 km precision. Only the utility confirms restoration.",
        "assumptions": ["Repair order: equipment closest to the substation first, then the repairs that serve the most homes."],
        "missing_data": ["No real crew data"], "what_would_change": [], "fallback": None,
    }
