"""Truth feed: one fixed replay of the real Feb 2025 damage through the real network.

MASTER_PLAN A1-A4, A13. Computed once (lazily, cached) with the fixed replay seed:
* every Feb 13-18 2025 damage row that maps to a device becomes a repair job, reported at
  its seeded storm-clock hour (ingest/enrich.py) with A3 hours x lognormal(0, 0.35) noise;
* a regional pool of 150 crews is split across circuits by expected repair hours (min 1),
  and each circuit's jobs run in priority order (app.sim.schedule);
* a home is out while any job on its upstream path is reported and not yet fixed.

This is the "simulated utility feed". The customer's estimate (Lane B's Monte Carlo) only
sees what known_jobs() reveals at time t, never the future finish times.
"""
from __future__ import annotations

import threading
from collections import defaultdict
from functools import lru_cache

import numpy as np

from app import config
from app.db import get_conn
from app.sim.schedule import schedule

NOISE_SIGMA = 0.35          # A3
CREW_ASSIGNED_LEAD_H = 2.0  # stage shows "crew assigned" this long before a repair starts

_lock = threading.Lock()


class Feed:
    def __init__(self) -> None:
        conn = get_conn()
        # ---- homes
        rows = conn.execute(
            "SELECT premise_key, circuit_id, cell_id, overhead FROM premises ORDER BY premise_key").fetchall()
        self.keys = [r[0] for r in rows]
        self.index = {k: i for i, k in enumerate(self.keys)}
        self.circuit = [r[1] for r in rows]
        self.cell = [r[2] for r in rows]
        self.overhead = [None if r[3] is None else bool(r[3]) for r in rows]
        self.paths: list[list[str]] = [[] for _ in rows]
        for pk, dk in conn.execute(
                "SELECT premise_key, device_key FROM topology_edges ORDER BY premise_key, step_order"):
            i = self.index.get(pk)
            if i is not None and dk:
                self.paths[i].append(dk)
        homes_on_device: dict[str, list[int]] = defaultdict(list)
        for i, p in enumerate(self.paths):
            for dk in p:
                homes_on_device[dk].append(i)
        self.circuit_homes = defaultdict(int)
        for c in self.circuit:
            self.circuit_homes[c] += 1

        # ---- jobs (Feb 2025 replay rows mapped to a device)
        jrows = conn.execute("""
            SELECT rowid, circuit_id, device_key, report_t, base_hours, priority, asset_type, lat, lon
            FROM damage_events
            WHERE storm = 'feb2025' AND device_key IS NOT NULL AND report_t IS NOT NULL
            ORDER BY rowid""").fetchall()
        cell_of_point = _cell_locator(conn)
        conn.close()

        rng = np.random.default_rng(config.REPLAY_SEED)
        noise = rng.lognormal(0.0, NOISE_SIGMA, len(jrows))
        self.jobs: list[dict] = []
        for r, z in zip(jrows, noise):
            self.jobs.append({
                "job_id": f"j_{r[0]:04d}", "circuit_id": r[1], "device_key": r[2],
                "report_t": float(r[3]), "base_hours": float(r[4]), "hours": float(r[4]) * float(z),
                "priority": float(r[5]), "asset_type": r[6] or "primary",
                "cell_id": cell_of_point(r[7], r[8]),
            })

        # ---- crews: regional pool split by expected repair hours (A4)
        hours_by_c: dict[str, float] = defaultdict(float)
        for j in self.jobs:
            hours_by_c[j["circuit_id"]] += j["base_hours"]
        total = sum(hours_by_c.values()) or 1.0
        self.crews = {c: max(1, round(config.REGIONAL_CREWS * h / total)) for c, h in hours_by_c.items()}

        # ---- schedule each circuit
        by_c: dict[str, list[dict]] = defaultdict(list)
        for j in self.jobs:
            by_c[j["circuit_id"]].append(j)
        for c, js in by_c.items():
            plan = schedule([{"job_id": j["job_id"], "ready_t": j["report_t"], "hours": j["hours"],
                              "priority": j["priority"]} for j in js], self.crews[c])
            for j in js:
                j["start_t"], j["finish_t"] = plan[j["job_id"]]
        self.jobs_by_circuit = dict(by_c)
        self.job_by_id = {j["job_id"]: j for j in self.jobs}

        # ---- per-home outage intervals (merged)
        per_home: dict[int, list[dict]] = defaultdict(list)
        for j in self.jobs:
            for i in homes_on_device.get(j["device_key"], ()):
                per_home[i].append(j)
        self.home_jobs = per_home
        self.intervals: dict[int, list[tuple[float, float]]] = {}
        starts, ends, owner = [], [], []
        for i, js in per_home.items():
            merged: list[list[float]] = []
            for a, b in sorted((j["report_t"], j["finish_t"]) for j in js):
                if merged and a <= merged[-1][1]:
                    merged[-1][1] = max(merged[-1][1], b)
                else:
                    merged.append([a, b])
            self.intervals[i] = [(a, b) for a, b in merged]
            for a, b in merged:
                starts.append(a)
                ends.append(b)
                owner.append(i)
        self._iv_start = np.asarray(starts)
        self._iv_end = np.asarray(ends)
        self._iv_home = np.asarray(owner, dtype=np.int64)
        self._job_report = np.asarray([j["report_t"] for j in self.jobs])
        self._job_finish = np.asarray([j["finish_t"] for j in self.jobs])

    # ------------------------------------------------------------------ queries
    def idx(self, home_id: str) -> int:
        i = self.index.get(home_id)
        if i is None:
            raise KeyError(home_id)
        return i

    def out_mask(self, t: float) -> np.ndarray:
        """Boolean per home (feed order): out at storm hour t."""
        m = np.zeros(len(self.keys), dtype=bool)
        live = (self._iv_start <= t) & (t < self._iv_end)
        m[self._iv_home[live]] = True
        return m

    def active_repairs(self, t: float) -> int:
        return int(((self._job_report <= t) & (t < self._job_finish)).sum())


@lru_cache(maxsize=1)
def _feed() -> Feed:
    with _lock:
        return Feed()


def get_feed() -> Feed:
    return _feed()


def _cell_locator(conn):
    """(lat, lon) -> cell_id on the ingest grid (ingest/enrich.py), or None outside it."""
    from ingest.enrich import CELL_DLAT, CELL_DLON
    cells = conn.execute("SELECT cell_id, lat_c, lon_c FROM cells").fetchall()
    if not cells:
        return lambda lat, lon: None
    lat0 = min(c[1] for c in cells) - CELL_DLAT / 2
    lon0 = min(c[2] for c in cells) - CELL_DLON / 2
    rc = lambda lat, lon: (int(np.floor((lat - lat0) / CELL_DLAT)), int(np.floor((lon - lon0) / CELL_DLON)))
    grid = {rc(la, lo): cid for cid, la, lo in cells}
    return lambda lat, lon: None if lat is None or lon is None else grid.get(rc(lat, lon))


# ---------------------------------------------------------------------- contract API
def home_info(home_id: str) -> dict:
    f = get_feed()
    i = f.idx(home_id)
    c = f.circuit[i]
    return {"circuit_id": c, "cell_id": f.cell[i], "overhead": f.overhead[i],
            "path_device_keys": list(f.paths[i]), "circuit_crews": int(f.crews.get(c, 1))}


def home_state(home_id: str, t: float) -> dict:
    """{"is_out", "out_since_t", "restored_at_t", "stage", "stage_updated_t"} at storm hour t.

    restored_at_t is only filled once it has happened (the feed never leaks the future)."""
    f = get_feed()
    i = f.idx(home_id)
    t = float(t)
    empty = {"is_out": False, "out_since_t": None, "restored_at_t": None, "stage": None, "stage_updated_t": None}
    ivs = f.intervals.get(i)
    if not ivs:
        return empty
    last_done = None
    for a, b in ivs:
        if a <= t < b:
            stage, upd = _stage(f, i, t, a)
            return {"is_out": True, "out_since_t": round(a, 2), "restored_at_t": None,
                    "stage": stage, "stage_updated_t": round(upd, 2)}
        if b <= t:
            last_done = (a, b)
    if last_done:
        a, b = last_done
        return {"is_out": False, "out_since_t": round(a, 2), "restored_at_t": round(b, 2),
                "stage": "restored", "stage_updated_t": round(b, 2)}
    return empty


def _stage(f: Feed, i: int, t: float, out_since: float) -> tuple[str, float]:
    open_jobs = [j for j in f.home_jobs[i] if j["report_t"] <= t < j["finish_t"]]
    working = [j for j in open_jobs if j["start_t"] <= t]
    if working:
        return "repairing", min(j["start_t"] for j in working)
    soon = [j for j in open_jobs if j["start_t"] - CREW_ASSIGNED_LEAD_H <= t]
    if soon:
        return "crew_assigned", max(min(j["start_t"] for j in soon) - CREW_ASSIGNED_LEAD_H,
                                    min(j["report_t"] for j in soon))
    return "assessing", max([out_since] + [j["report_t"] for j in open_jobs])


def known_jobs(circuit_id: str, t: float) -> list[dict]:
    """Jobs on the circuit reported by t and not fixed by t (what the utility knows at t)."""
    f = get_feed()
    t = float(t)
    out = []
    for j in f.jobs_by_circuit.get(circuit_id, ()):
        if j["report_t"] <= t < j["finish_t"]:
            if j["start_t"] <= t:
                frac = (j["finish_t"] - t) / max(j["finish_t"] - j["start_t"], 1e-9)
            else:
                frac = 1.0
            out.append({"job_id": j["job_id"], "device_key": j["device_key"], "base_hours": j["base_hours"],
                        "remaining_frac": round(frac, 4), "priority": j["priority"],
                        "report_t": j["report_t"], "asset_type": j["asset_type"]})
    return out


def path_jobs(home_id: str, t: float) -> list[dict]:
    """Feed view of the repairs on this home's path that are reported by t (internal use).

    Each: {"job_id", "report_t", "start_t", "finish_t", "status", "depth", "cell_id", "asset_type"}
    status = done | in_progress | waiting. Only past/present facts, no future times leave here
    except through the caller's own filtering."""
    f = get_feed()
    i = f.idx(home_id)
    path = f.paths[i]
    pos = {dk: n for n, dk in enumerate(path)}
    out = []
    for j in f.home_jobs.get(i, ()):
        if j["report_t"] > t:
            continue
        status = "done" if j["finish_t"] <= t else "in_progress" if j["start_t"] <= t else "waiting"
        out.append({**j, "status": status, "depth": len(path) - 1 - pos.get(j["device_key"], 0)})
    return out
