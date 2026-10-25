"""Restoration estimate (Lane B, MASTER_PLAN Lane B 7.2, A3/A4/A13, N6/N7/N8).

get_restoration(home_id, t, crews, access_blocked, extra_damage, switching) -> dict
shaped like contracts/mocks/restoration*.json.

How it works
------------
* Jobs = the damage on the home's circuit that has been reported by ``t`` and is not
  fixed yet (Lane A's ``feed.known_jobs``, A13), plus ``extra_damage`` synthetic jobs on
  the home's path. If the home is out but no reported job is on its path, one
  "assumed" path job is added (and confidence drops to low).
* Monte Carlo, n = 1000, numpy Generator seeded from MC_SEED. Each sim:
  hours = base_hours x lognormal(0, 0.35) x remaining_frac; access_blocked adds
  uniform(2, 8) h per job; ready_t = max(t, report_t). Jobs are scheduled on ``crews``
  crews (default home_info["circuit_crews"]).
* Scheduler: a private numpy version of greedy list scheduling, vectorised over the
  1000 sims, with the same semantics as Lane A's ``schedule()`` / the prototype
  ``sim.schedule``: the earliest-free crew takes the best (lowest priority, then
  earliest ready, then input order) job that is ready; if none is ready it waits for
  the next one. tests/test_lane_b_restoration.py checks it against the prototype.
* Common random numbers: every random stream (job noise, access delay, each synthetic
  job) has its own seed, so the "what could change this" re-runs differ only by the
  input that changed.
* Restore time = last finish among path jobs (switching on) or among all circuit
  jobs (switching off, N8). Hours are from ``t``.

Without Lane A's ``app.sim`` the function returns the contract mocks (stubs-first rule),
still raising UnknownHome for ids missing from the DB premises table.
"""
from __future__ import annotations

import copy
import importlib
import math
import sqlite3
from functools import lru_cache

import numpy as np

from app.models.common import (
    COMMON_MISSING_DATA, DB_PATH, MC_SEED, OUTAGE_LINK, UnknownHome, get_conn, load_mock,
)

N_SIMS = 1000
SIGMA = 0.35
ACCESS_DELAY_H = (2.0, 8.0)
DEFAULT_PRIMARY_BASE_H = 1.129 * 4.5     # DATA_FACTS 7 (primary wire x ILM), if labor is missing
STEP_MESSAGE = "Repairs happen in steps. Some neighbors may get power back before you."

STAGE_LABELS = {
    "assessing": "The damage affecting you has been reported",
    "crew_assigned": "A crew has been assigned to the damage affecting you",
    "repairing": "A crew is repairing the damage affecting you",
    "restored": "Power is back on",
}

DRIVER_LABELS = {
    "crews_plus_2": "2 more crews on your line",
    "access_blocked": "Roads blocked by ice or trees",
    "extra_damage": "1 more damaged spot found",
    "switching_off": "Crews can't reroute power around damage",
}

# asset_type (lowercase, from ARCOS / DATA_FACTS 7) -> plain-English cause label
CAUSE_LABELS = {
    "pole": "Damaged power pole on the line that feeds your home",
    "primary": "Damaged power line upstream of your street",
    "secondary": "Damaged wire near your street",
    "fuse bank": "Damaged fuse equipment on the line that feeds your home",
    "transformer": "Damaged transformer near your home",
    "step transformer": "Damaged transformer upstream of your street",
    "recloser bank": "Damaged line safety switch upstream of your street",
    "switch": "Damaged switch on the line that feeds your home",
    "capacitor bank": "Damaged equipment on the line that feeds your home",
    "light": "Damaged equipment near your street",
}
CAUSE_DEFAULT = "Damage on the line that feeds your home"
MAJOR_ASSETS = ("pole", "primary", "recloser")

ASSUMPTIONS = [
    "Repair hours come from AEP's labor table, times 4.5 for travel and setup.",
    "Crews come from a shared regional pool of 150.",
    "Only damage reported so far is counted.",
    "Not a promise. The utility's confirmed time may differ.",
]
WHAT_WOULD_CHANGE = [
    "Finding more damage would make this longer.",
    "More crews would make it shorter.",
    "Blocked roads would make it longer.",
]
NO_TOPOLOGY_MESSAGE = ("We can't match your home to the line map yet, so we can't estimate "
                       "when power will be back. Check AEP's outage page for updates.")


# ----------------------------------------------------------------------------- imports
def _sim():
    """Lane A modules, imported lazily (tests monkeypatch sys.modules). None if missing."""
    try:
        feed = importlib.import_module("app.sim.feed")
        sched = importlib.import_module("app.sim.schedule")
    except ImportError:
        return None
    try:
        labor = importlib.import_module("app.sim.labor")
    except ImportError:
        labor = None
    return feed, sched, labor


def _home_in_db(home_id: str) -> bool | None:
    """True/False if the premises table answers, None if there is no DB to ask."""
    if not DB_PATH.exists():
        return None
    try:
        conn = get_conn()
        row = conn.execute("SELECT 1 FROM premises WHERE premise_key = ?", (home_id,)).fetchone()
        return row is not None
    except sqlite3.Error:
        return None


# ----------------------------------------------------------------------------- public
def get_restoration(home_id: str, t: float = 0, crews: int | None = None,
                    access_blocked: bool = False, extra_damage: int = 0,
                    switching: bool = True) -> dict:
    """Restoration card for one home at storm hour ``t`` (contracts/API.md 5)."""
    out = _cached(str(home_id), float(t), None if crews is None else int(crews),
                  bool(access_blocked), int(extra_damage), bool(switching))
    return copy.deepcopy(out)


def clear_cache() -> None:
    _cached.cache_clear()


@lru_cache(maxsize=4096)
def _cached(home_id, t, crews, access_blocked, extra_damage, switching) -> dict:
    mods = _sim()
    if mods is None:
        return _stub(home_id, t, crews, access_blocked, extra_damage, switching)
    return _live(mods, home_id, t, crews, access_blocked, extra_damage, switching)


def _num(x):
    return int(x) if float(x).is_integer() else x


def _stub(home_id, t, crews, access_blocked, extra_damage, switching) -> dict:
    if _home_in_db(home_id) is False:
        raise UnknownHome(home_id)
    name = ("restoration_not_out.json" if t < 4.3 else
            "restoration_restored.json" if t >= 18.4 else "restoration.json")
    out = copy.deepcopy(load_mock(name))
    out["home_id"] = home_id
    out["t"] = _num(t)
    out["inputs"] = {"crews": crews if crews is not None else out["inputs"]["crews"],
                     "access_blocked": access_blocked, "extra_damage": extra_damage,
                     "switching": switching}
    return out


# ----------------------------------------------------------------------------- live
def _base(home_id, t, inputs) -> dict:
    """The not-out shape; other states fill it in."""
    return {
        "home_id": home_id, "t": _num(t), "source": "simulated_feed",
        "is_out": False, "out_since_t": None, "restored_at_t": None,
        "status": None, "cause": None, "estimate": None, "utility_etr": None,
        "chance_back_by": [], "step_restoration": None, "drivers": [], "recap": None,
        "inputs": inputs, "assumptions": [], "missing_data": list(COMMON_MISSING_DATA),
        "what_would_change": [], "fallback": None,
    }


def _status(state) -> dict | None:
    stage = state.get("stage")
    if stage not in STAGE_LABELS:
        return None
    return {"stage": stage, "label": STAGE_LABELS[stage], "source": "simulated_feed",
            "updated_t": state.get("stage_updated_t")}


def _live(mods, home_id, t, crews, access_blocked, extra_damage, switching) -> dict:
    feed, sched, labor = mods
    try:
        info = feed.home_info(home_id)
    except KeyError as e:
        raise UnknownHome(home_id) from e
    n_crews = max(1, int(crews if crews is not None else info.get("circuit_crews") or 1))
    inputs = {"crews": n_crews, "access_blocked": access_blocked,
              "extra_damage": extra_damage, "switching": switching}
    out = _base(home_id, t, inputs)
    state = feed.home_state(home_id, t)
    restored_at = state.get("restored_at_t")

    if restored_at is not None and restored_at <= t:            # Power is back card
        out.update(out_since_t=state.get("out_since_t"), restored_at_t=restored_at,
                   status=_status({**state, "stage": "restored",
                                   "stage_updated_t": state.get("stage_updated_t", restored_at)}))
        out["recap"] = _recap(feed, home_id, info, state)
        return out
    if not state.get("is_out"):                                 # Mode 1 (not out)
        return out

    out.update(is_out=True, out_since_t=state.get("out_since_t"), status=_status(state))
    if not info.get("path_device_keys"):                        # A6 fallback, keep the shape
        out["fallback"] = {"reason": "no_topology", "message": NO_TOPOLOGY_MESSAGE,
                           "link": OUTAGE_LINK}
        return out

    jobs = list(feed.known_jobs(info["circuit_id"], t))
    path = set(info["path_device_keys"])
    base = _mc(jobs, path, t, n_crews, access_blocked, extra_damage, switching, labor)
    out["source"] = "model_estimate"
    out["estimate"] = _estimate_block(base)
    out["chance_back_by"] = _curve(base["restore"])
    out["step_restoration"] = base["step"]
    out["cause"] = _cause(jobs, path, base)
    out["drivers"] = _drivers(jobs, path, t, n_crews, access_blocked, extra_damage,
                              switching, labor, base)
    out["assumptions"] = list(ASSUMPTIONS)
    out["what_would_change"] = list(WHAT_WOULD_CHANGE) + (
        ["If crews can't reroute power around damage, it would take longer."] if switching else [])
    return out


# ----------------------------------------------------------------------------- Monte Carlo
def _rank(prios, readys) -> np.ndarray:
    """Dispatch order: lower priority first, then earlier ready, then input order."""
    order = sorted(range(len(prios)), key=lambda i: (prios[i], readys[i], i))
    return np.asarray(order, dtype=int)


def schedule_batch(ready: np.ndarray, dur: np.ndarray, crews: int, t0: float) -> np.ndarray:
    """Greedy list scheduling for many sims at once.

    ready: (J,) ready times, columns ALREADY sorted best-first (dispatch order).
    dur:   (n, J) job hours per sim. Returns finish times (n, J).
    Same rule as app.sim.schedule.schedule: the earliest-free crew takes the best ready
    job; if nothing is ready it waits for the next ready job.
    """
    n, J = dur.shape
    finish = np.empty((n, J))
    if J == 0:
        return finish
    free = np.full((n, max(1, crews)), float(t0))
    done = np.zeros((n, J), dtype=bool)
    rows = np.arange(n)
    ready_row = ready[None, :]
    for _ in range(J):
        ci = free.argmin(axis=1)
        T = free[rows, ci]
        avail = ~done & (ready_row <= T[:, None])
        idle = ~avail.any(axis=1)
        if idle.any():
            nxt = np.where(done, np.inf, ready_row).min(axis=1)
            T = np.where(idle, np.maximum(T, nxt), T)
            avail = ~done & (ready_row <= T[:, None])
        j = avail.argmax(axis=1)                     # first True = best in dispatch order
        f = np.maximum(T, ready[j]) + dur[rows, j]
        finish[rows, j] = f
        done[rows, j] = True
        free[rows, ci] = f
    return finish


def _synthetic_base(jobs, labor) -> np.ndarray:
    pool = [float(j["base_hours"]) for j in jobs if j.get("base_hours")]
    if pool:
        return np.asarray(pool)
    try:
        return np.asarray([float(labor.job_base_hours("primary", False, ""))])
    except Exception:  # labor missing or failing: workbook primary-wire hours
        return np.asarray([DEFAULT_PRIMARY_BASE_H])


def _mc(jobs, path, t, crews, access_blocked, extra_damage, switching, labor, n=N_SIMS) -> dict:
    """One Monte Carlo run. Returns restore hours from t (n,), plus per-job info."""
    on_path = [j.get("device_key") in path for j in jobs]
    assumed = 0 if any(on_path) else 1          # out, but nothing reported on the path yet
    n_syn = extra_damage + assumed
    prios = [j.get("priority", 0) for j in jobs]
    path_prios = [p for p, on in zip(prios, on_path) if on]
    syn_prio = min(path_prios) if path_prios else (min(prios) if prios else 0)
    readys = [max(t, float(j.get("report_t", t) or t)) for j in jobs] + [t] * n_syn
    prios = prios + [syn_prio] * n_syn
    on_path = on_path + [True] * n_syn

    J0 = len(jobs)
    dur = np.empty((n, J0 + n_syn))
    if J0:
        base = np.array([float(j["base_hours"]) for j in jobs])
        frac = np.array([float(j.get("remaining_frac", 1.0)) for j in jobs])
        noise = np.random.default_rng([MC_SEED, 0]).lognormal(0.0, SIGMA, (n, J0))
        dur[:, :J0] = base * noise * frac
        if access_blocked:
            dur[:, :J0] += np.random.default_rng([MC_SEED, 1]).uniform(*ACCESS_DELAY_H, (n, J0))
    syn_pool = _synthetic_base(jobs, labor)
    for e in range(n_syn):                       # each synthetic job has its own stream
        g = np.random.default_rng([MC_SEED, 100 + e])
        d = g.choice(syn_pool, size=n) * g.lognormal(0.0, SIGMA, n)
        if access_blocked:
            d += g.uniform(*ACCESS_DELAY_H, n)
        dur[:, J0 + e] = d

    order = _rank(prios, readys)
    ready = np.asarray(readys, dtype=float)[order]
    fin_sorted = schedule_batch(ready, dur[:, order], crews, t)
    finish = np.empty_like(fin_sorted)
    finish[:, order] = fin_sorted
    mask = np.asarray(on_path) if switching else np.ones(len(on_path), dtype=bool)
    restore = finish[:, mask].max(axis=1) - t
    return {"restore": restore, "finish": finish, "dur": dur, "on_path": np.asarray(on_path),
            "assumed": assumed, "n_jobs": J0 + n_syn, "n_path": int(np.sum(on_path)),
            "step": _steps(finish, dur, np.asarray(on_path), switching, t)}


def _pcts(restore) -> tuple[float, float, float]:
    p10, p50, p90 = np.percentile(restore, [10, 50, 90])
    return round(float(p10), 1), round(float(p50), 1), round(float(p90), 1)


def _headline(p10, p90) -> str:
    lo, hi = math.floor(p10), math.ceil(p90)
    hi = max(hi, lo + 1)
    if hi > 48:
        dlo, dhi = math.floor(p10 / 24), math.ceil(p90 / 24)
        dhi = max(dhi, dlo + 1)
        return f"Likely back within {dhi} days" if dlo == 0 else f"Likely back in {dlo} to {dhi} days"
    return f"Likely back within {hi} hours" if lo == 0 else f"Likely back in {lo} to {hi} hours"


def _confidence(p10, p90, assumed) -> str:
    """low: P90/P10 > 4 or the path damage is assumed (none reported yet); high: < 2."""
    ratio = p90 / max(p10, 0.1)
    if ratio > 4 or assumed:
        return "low"
    return "high" if ratio < 2 else "medium"


def _estimate_block(res) -> dict:
    p10, p50, p90 = _pcts(res["restore"])
    return {"p10_h": p10, "p50_h": p50, "p90_h": p90,
            "confidence": _confidence(p10, p90, res["assumed"]),
            "n_sims": int(res["restore"].size), "headline": _headline(p10, p90),
            "source": "model_estimate"}


def _curve(restore, n_marks=8) -> list[dict]:
    """Cumulative chance back by ~8 whole-hour marks from about P2 to P99.5."""
    lo = max(1, math.floor(float(np.quantile(restore, 0.02))))
    hi = max(lo + 1, math.ceil(float(np.quantile(restore, 0.995))))
    marks = sorted({int(round(x)) for x in np.linspace(lo, hi, n_marks)})
    srt = np.sort(restore)
    return [{"t_from_now_h": m,
             "prob": round(float(np.searchsorted(srt, m, side="right")) / srt.size, 2)}
            for m in marks]


def _steps(finish, dur, on_path, switching, t) -> dict:
    """Step restoration (N6).

    Rule: take the median (over sims) finish time of every open job on the circuit and
    group them into "steps" of length ``wave`` = max(1 h, median job hours, span / 6),
    so there are at most ~7 steps. A step = a window in which a batch of repairs is
    expected to finish. Your step = the step holding the repair that brings you back
    (the path job with the latest median finish; with switching off, the last job on
    the line). your_step = 1 + number of non-empty steps before it.
    """
    if finish.shape[1] == 0:
        return {"your_step": 1, "total_steps": 1, "message": STEP_MESSAGE}
    med = np.median(finish, axis=0) - t
    span = float(med.max())
    wave = max(1.0, float(np.median(dur)), span / 6.0)
    step_of = np.floor(med / wave).astype(int)
    steps = np.unique(step_of)
    mine_job = (int(np.argmax(np.where(on_path, med, -np.inf))) if switching
                else int(np.argmax(med)))
    your_step = int(np.searchsorted(steps, step_of[mine_job])) + 1
    return {"your_step": your_step, "total_steps": int(steps.size), "message": STEP_MESSAGE}


def _cause(jobs, path, res) -> dict:
    """Label from the asset type of the main open job on the path (largest median hours)."""
    path_jobs = [(i, j) for i, j in enumerate(jobs) if j.get("device_key") in path]
    asset = ""
    if path_jobs:
        med_h = np.median(res["dur"], axis=0)
        i, main = max(path_jobs, key=lambda ij: med_h[ij[0]])
        asset = str(main.get("asset_type") or "").strip().lower()
    label = CAUSE_LABELS.get(asset, CAUSE_DEFAULT)
    severity = "major" if any(k in asset for k in MAJOR_ASSETS) else "minor"
    return {"label": label, "severity": severity,
            "repairs_on_your_path": res["n_path"], "repairs_on_your_line": res["n_jobs"]}


def _drivers(jobs, path, t, crews, access_blocked, extra_damage, switching, labor, base) -> list:
    """N7: P50 change from one more lever each. Signs are clamped to the lever's
    physical direction (greedy schedules can show tiny anomalies). A lever that is
    already on gets ``active: true`` and effect 0."""
    p50 = _pcts(base["restore"])[1]

    def effect(**kw):
        args = dict(crews=crews, access_blocked=access_blocked,
                    extra_damage=extra_damage, switching=switching)
        args.update(kw)
        res = _mc(jobs, path, t, args["crews"], args["access_blocked"],
                  args["extra_damage"], args["switching"], labor)
        return round(_pcts(res["restore"])[1] - p50, 1)

    out = [{"key": "crews_plus_2", "label": DRIVER_LABELS["crews_plus_2"],
            "effect_h": min(0.0, effect(crews=crews + 2)), "active": False}]
    out.append({"key": "access_blocked", "label": DRIVER_LABELS["access_blocked"],
                "effect_h": 0.0 if access_blocked else max(0.0, effect(access_blocked=True)),
                "active": access_blocked})
    out.append({"key": "extra_damage", "label": DRIVER_LABELS["extra_damage"],
                "effect_h": max(0.0, effect(extra_damage=extra_damage + 1)), "active": False})
    out.append({"key": "switching_off", "label": DRIVER_LABELS["switching_off"],
                "effect_h": 0.0 if not switching else max(0.0, effect(switching=False)),
                "active": not switching})
    return out


# ----------------------------------------------------------------------------- recap
def _range_at(home_id, made_at, restored_at) -> dict | None:
    est = get_restoration(home_id, t=made_at).get("estimate")
    if not est:
        return None
    lo, hi = round(made_at + est["p10_h"], 1), round(made_at + est["p90_h"], 1)
    return {"made_at_t": made_at, "back_by_t_low": lo, "back_by_t_high": hi,
            "within_range": bool(lo <= restored_at <= hi)}


def _updated_time(feed, info, out_since, restored_at) -> float | None:
    """Latest report_t of a path job reported after the outage began (before restore)."""
    path = set(info.get("path_device_keys") or [])
    if not path:
        return None
    probes = list(np.arange(out_since, restored_at, 0.5)) + [restored_at - 1e-6]
    best = None
    for tp in probes:
        for j in feed.known_jobs(info["circuit_id"], float(tp)):
            r = j.get("report_t")
            if j.get("device_key") in path and r is not None and out_since < r < restored_at:
                best = r if best is None else max(best, r)
    return None if best is None else float(best)


def _miss_word(r, actual_t) -> str:
    if r["within_range"]:
        return "caught it"
    gap = actual_t - r["back_by_t_high"] if actual_t > r["back_by_t_high"] else r["back_by_t_low"] - actual_t
    side = "early" if actual_t > r["back_by_t_high"] else "late"
    return f"was {'a little ' if gap <= 3 else ''}{side}"


def _recap(feed, home_id, info, state) -> dict | None:
    out_since, restored_at = state.get("out_since_t"), state.get("restored_at_t")
    if out_since is None or restored_at is None:
        return None
    actual = round(restored_at - out_since, 1)
    first = _range_at(home_id, out_since, restored_at)
    t_up = _updated_time(feed, info, out_since, restored_at)
    updated = _range_at(home_id, t_up, restored_at) if t_up is not None else None

    msg = f"You were out about {max(1, round(actual))} hours."
    if first:
        msg += " Our first range " + ("caught it" if first["within_range"] else _miss_word(first, restored_at))
        if updated:
            msg += ("; after new damage was found, the updated range "
                    + _miss_word(updated, restored_at) + ".")
        else:
            msg += "."
    elif updated:
        msg += " After new damage was found, our updated range " + _miss_word(updated, restored_at) + "."
    return {"out_since_t": out_since, "restored_at_t": restored_at, "actual_h": actual,
            "first_estimate": first, "updated_estimate": updated, "message": msg}
