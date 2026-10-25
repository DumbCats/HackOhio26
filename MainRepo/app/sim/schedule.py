"""Crew scheduler (MASTER_PLAN A4): greedy list scheduling, same rule as Lane B's Monte Carlo.

Each time a crew is free it takes the best job that is ready (lowest priority, then earliest
ready, then input order). If nothing is ready it waits for the next job to be reported.
"""
from __future__ import annotations

import heapq


def schedule(jobs: list[dict], crews: int, t_start: float | None = None) -> dict[str, tuple[float, float]]:
    """jobs: {"job_id", "ready_t", "hours", "priority"}. Returns job_id -> (start_t, finish_t)."""
    if not jobs:
        return {}
    n = len(jobs)
    by_ready = sorted(range(n), key=lambda i: (jobs[i]["ready_t"], i))
    t0 = min(j["ready_t"] for j in jobs) if t_start is None else t_start
    free = [float(t0)] * max(1, int(crews))
    heapq.heapify(free)
    avail: list[tuple] = []
    out: dict[str, tuple[float, float]] = {}
    p = 0
    while len(out) < n:
        now = heapq.heappop(free)
        while p < n and jobs[by_ready[p]]["ready_t"] <= now:
            i = by_ready[p]
            heapq.heappush(avail, (jobs[i]["priority"], jobs[i]["ready_t"], i))
            p += 1
        if not avail:  # idle until the next report
            now = jobs[by_ready[p]]["ready_t"]
            while p < n and jobs[by_ready[p]]["ready_t"] <= now:
                i = by_ready[p]
                heapq.heappush(avail, (jobs[i]["priority"], jobs[i]["ready_t"], i))
                p += 1
        _, _, i = heapq.heappop(avail)
        start = max(now, jobs[i]["ready_t"])
        finish = start + jobs[i]["hours"]
        out[jobs[i]["job_id"]] = (start, finish)
        heapq.heappush(free, finish)
    return out
