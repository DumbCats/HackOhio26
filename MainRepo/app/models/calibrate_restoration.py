"""Calibrate the restoration Monte Carlo against Lane A's truth feed.

    .venv/bin/python -m app.models.calibrate_restoration [--max-groups 400] [--t-end 336]

1. Coverage: for every home that goes out in the truth feed, the FIRST estimate (made at
   out_since_t, default sliders) is compared with the actual restore time. Homes that share
   circuit + path + outage start get the same estimate, so they are estimated once and
   weighted by home count. Reports: share inside P10-P90, median P10-P90 width, early
   misses (restored after P90) and late misses (restored before P10).
2. ARCOS sanity check (A4/A9): share of truth-feed jobs fixed in 0/1/2/3+ calendar days
   after report (t = hours since 2025-02-13 00:00, A1) vs real ARCOS Feb-2025 rows.
   Fix times are inferred by probing known_jobs on an hourly grid (the contract has no
   "truth jobs" call), so they are good to about 1 h.

Prints a clear message and exits 0 if app.sim is not there yet.
"""
from __future__ import annotations

import argparse
import collections
import random
import sys
import time

import numpy as np

from app.models import restoration as R
from app.models.common import get_conn


def _homes() -> list[str]:
    return [r[0] for r in get_conn().execute("SELECT premise_key FROM premises ORDER BY premise_key")]


def coverage(feed, labor, t_end: float, max_groups: int) -> None:
    groups: dict = {}
    for hid in _homes():
        try:
            info = feed.home_info(hid)
            st = feed.home_state(hid, t_end)
        except KeyError:
            continue
        if st.get("out_since_t") is None or st.get("restored_at_t") is None:
            continue
        if not info.get("path_device_keys"):
            continue
        key = (info["circuit_id"], tuple(sorted(info["path_device_keys"])), st["out_since_t"])
        g = groups.setdefault(key, {"n": 0, "restored": st["restored_at_t"],
                                    "crews": info.get("circuit_crews") or 1})
        g["n"] += 1
    if not groups:
        print("No homes go out in the feed (check t_end).")
        return
    keys = sorted(groups)
    if len(keys) > max_groups:
        keys = sorted(random.Random(42).sample(keys, max_groups))
    print(f"Coverage: {len(groups)} outage groups, estimating {len(keys)} "
          f"({sum(groups[k]['n'] for k in keys)} homes)")
    w = inside = early = late = 0
    widths, rel_err = [], []
    t0 = time.perf_counter()
    for circ, path, t_out in keys:
        g = groups[(circ, path, t_out)]
        jobs = list(feed.known_jobs(circ, t_out))
        res = R._mc(jobs, set(path), t_out, max(1, int(g["crews"])), False, 0, True, labor)
        p10, p50, p90 = R._pcts(res["restore"])
        actual = g["restored"] - t_out
        n = g["n"]; w += n
        if actual > p90:
            early += n
        elif actual < p10:
            late += n
        else:
            inside += n
        widths.append(p90 - p10)
        rel_err.append((actual - p50) / max(actual, 0.5))
    dt = time.perf_counter() - t0
    print(f"  inside P10-P90: {inside / w:.0%}   (target ~80%)")
    print(f"  early miss (back after P90): {early / w:.0%}   late miss (back before P10): {late / w:.0%}")
    print(f"  median P10-P90 width: {np.median(widths):.1f} h   median (actual-P50)/actual: {np.median(rel_err):+.2f}")
    print(f"  {dt / len(keys) * 1000:.1f} ms per estimate (no drivers)")


def arcos_days(feed, t_end: float) -> None:
    circuits = [r[0] for r in get_conn().execute("SELECT DISTINCT circuit_id FROM premises")]
    seen: dict = {}        # (circuit, job_id) -> [report_t, last_seen_t]
    for c in circuits:
        for tp in np.arange(0.0, t_end + 1.0, 1.0):
            try:
                js = feed.known_jobs(c, float(tp))
            except KeyError:
                break
            for j in js:
                k = (c, j["job_id"])
                if k not in seen:
                    seen[k] = [float(j.get("report_t", tp)), float(tp)]
                seen[k][1] = float(tp)
    days = collections.Counter()
    for rep, last in seen.values():
        fix = last + 1.0                         # first probe where it was gone (upper bound)
        days[min(3, int(fix // 24) - int(rep // 24))] += 1
    n = sum(days.values())
    if not n:
        print("ARCOS check: no jobs seen in known_jobs.")
        return
    sim = [days[k] / n for k in range(4)]
    try:
        from app.models.common import damage_history
        real = collections.Counter(min(3, r["repair_days"]) for r in damage_history()
                                   if r["storm"] == "feb2025" and r["repair_days"] is not None)
        rn = sum(real.values())
        arc = [real[k] / rn for k in range(4)]
        src = f"ARCOS Feb-2025 (n={rn})"
    except Exception as e:  # raw data missing: use the plan's numbers (A4)
        arc, src = [0.39, 0.33, 0.18, 0.10], f"ARCOS per MASTER_PLAN A4 ({type(e).__name__})"
    print(f"ARCOS days check ({n} feed jobs):")
    print("            0d    1d    2d    3d+")
    print("  feed   " + "".join(f"{x:6.0%}" for x in sim))
    print(f"  arcos  " + "".join(f"{x:6.0%}" for x in arc) + f"   [{src}]")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--max-groups", type=int, default=400)
    ap.add_argument("--t-end", type=float, default=24 * 14)
    a = ap.parse_args(argv)
    mods = R._sim()
    if mods is None:
        print("app.sim (Lane A feed) is not available yet; nothing to calibrate. Exiting.")
        return 0
    feed, _sched, labor = mods
    coverage(feed, labor, a.t_end, a.max_groups)
    arcos_days(feed, a.t_end)
    return 0


if __name__ == "__main__":
    sys.exit(main())
