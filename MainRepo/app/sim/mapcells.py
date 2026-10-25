"""Outage map at ~1 km cells (contracts/API.md: outage_map.json). Counts only, no points."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from functools import lru_cache

import numpy as np

from app.db import get_conn
from app.sim.feed import get_feed

MISSING = ["No live weather data", "No crew location data", "Past repair records have dates but no times"]
ASSUMPTIONS = [
    "Outage areas come from reported damage traced through the network map.",
    "Areas are about 1 km across. Areas with fewer than 10 homes are hidden.",
]


@lru_cache(maxsize=1)
def _cells() -> tuple[list[dict], np.ndarray]:
    """Visible cells and, per home (feed order), the index of its visible cell or -1."""
    f = get_feed()
    conn = get_conn()
    rows = conn.execute("SELECT cell_id, bounds_json, homes, lat_c, lon_c FROM cells WHERE visible = 1 "
                        "ORDER BY cell_id").fetchall()
    conn.close()
    cells = [{"cell_id": r[0], "bounds": json.loads(r[1]), "homes": int(r[2]), "center": [r[3], r[4]]}
             for r in rows]
    pos = {c["cell_id"]: n for n, c in enumerate(cells)}
    home_cell = np.asarray([pos.get(c, -1) for c in f.cell], dtype=np.int64)
    return cells, home_cell


def cell_center(cell_id: str) -> list[float] | None:
    for c in _cells()[0]:
        if c["cell_id"] == cell_id:
            return c["center"]
    return None


@lru_cache(maxsize=32)
def _bands(severity: float) -> tuple[str, ...]:
    """Most common risk band per visible cell (fallback homes count as 'unknown')."""
    cells, home_cell = _cells()
    f = get_feed()
    try:
        from app.models import risk
        c = risk._cache()
        cut = risk.load_artifact()["band_cutoffs"]
        idx = np.asarray([c["index"].get(k, -1) for k in f.keys])
        score = np.asarray(c["score"])[np.maximum(idx, 0)] * severity
        conf = np.asarray(c["conf"])[np.maximum(idx, 0)]
        band = np.where(score >= cut["high"], "high", np.where(score >= cut["medium"], "medium", "low"))
        band = np.where((idx < 0) | (conf < risk.CONF_LOW), "unknown", band)
    except Exception:
        band = np.full(len(f.keys), "unknown")
    votes: dict[int, Counter] = defaultdict(Counter)
    for hc, b in zip(home_cell.tolist(), band.tolist()):
        if hc >= 0:
            votes[hc][b] += 1
    return tuple(votes[n].most_common(1)[0][0] if votes[n] else "unknown" for n in range(len(cells)))


def get_outage_map(t: float, severity: float = 0.8) -> dict:
    t = round(float(t), 2)
    severity = round(float(severity), 2)
    return _map(t, severity)


@lru_cache(maxsize=256)
def _map(t: float, severity: float) -> dict:
    f = get_feed()
    cells, home_cell = _cells()
    out = f.out_mask(t)
    out_per_cell = np.bincount(home_cell[out & (home_cell >= 0)], minlength=len(cells))
    bands = _bands(severity)
    body = []
    for n, c in enumerate(cells):
        k = int(out_per_cell[n])
        status = "out" if k * 2 >= c["homes"] and k > 0 else "partial" if k > 0 else "on"
        body.append({"cell_id": c["cell_id"], "bounds": c["bounds"], "homes": c["homes"],
                     "homes_out": k, "status": status, "risk_band": bands[n]})
    return {
        "t": t, "source": "simulated_feed",
        "summary": {"homes_total": len(f.keys), "homes_out": int(out.sum()), "active_repairs": f.active_repairs(t)},
        "cells": body, "assumptions": list(ASSUMPTIONS), "missing_data": list(MISSING),
        "what_would_change": [], "fallback": None,
    }
