"""Demo scenario: storm clock range, story moments (computed from the feed), demo homes."""
from __future__ import annotations

from functools import lru_cache

from app.sim import story
from app.sim.feed import get_feed
from app.sim.locate import area_label
from app.sim.mapcells import cell_center


@lru_cache(maxsize=1)
def get_scenario() -> dict:
    homes = story.load()
    f = get_feed()
    s = homes["story"]
    moments = [
        {"t": -18, "key": "forecast", "label": "Storm forecast"},
        {"t": story.ceil1(s["out_t"]) + 0.1, "key": "outage", "label": "Your power goes out"},
        {"t": story.ceil1(s["update_t"]) + 0.1, "key": "update", "label": "Estimate updated"},
        {"t": story.ceil1(s["restored_t"]) + 0.1, "key": "restored", "label": "Power restored"},
    ]
    for m in moments:
        m["t"] = round(m["t"], 1)
    out_homes = []
    for key in ("story", "second", "fallback"):
        h = homes.get(key)
        if h:
            cid = f.cell[f.idx(h["home_id"])]
            out_homes.append({"home_id": h["home_id"], "label": h["label"], "cell_id": cid,
                              "area": area_label(cid), "role": key})
    return {
        "storm_name": "Winter storm (replay of real Feb 2025 damage)",
        "simulated": True,
        "t_min": -24, "t_max": 96, "t_now_default": -18,
        "moments": moments,
        "default_home_id": s["home_id"],
        "homes": out_homes,
        "map_center": cell_center(f.cell[f.idx(s["home_id"])]) or [37.25, -79.96],
        "map_zoom": 13,
    }
