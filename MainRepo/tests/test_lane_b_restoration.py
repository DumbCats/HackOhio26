"""Lane B restoration Monte Carlo, against a FAKE Lane A feed (sys.modules monkeypatch)."""
import heapq
import json
import random
import sys
import time
import types

import numpy as np
import pytest

from app.models import restoration as R
from app.models.common import UnknownHome, load_mock

ASSETS = ["primary", "Pole", "Fuse Bank", "secondary", "Transformer", "Recloser Bank"]
BASE_H = {"primary": 5.08, "Pole": 21.65, "Fuse Bank": 5.58, "secondary": 3.96,
          "Transformer": 14.55, "Recloser Bank": 8.79}


def _make_circuit(cid, n_jobs, seed, report_span=10.0):
    rnd = random.Random(seed)
    jobs = []
    for i in range(n_jobs):
        a = ASSETS[i % len(ASSETS)]
        jobs.append({
            "job_id": f"JOBID{cid}{i:03d}", "device_key": f"DEVKEY{cid}{i:03d}",
            "base_hours": BASE_H[a], "remaining_frac": 1.0, "priority": float(rnd.randint(1, 50)) + i / 100,
            "report_t": round(rnd.uniform(0, report_span), 2), "asset_type": a,
            "fix_t": None,
        })
    return jobs


# circuit A: 30 jobs, story home path = jobs 3 (reported 4.3) and 7 (reported 9.5)
CIRC = {"CIRCAAA": _make_circuit("A", 30, 1), "CIRCBBB": _make_circuit("B", 40, 2, report_span=0.0)}
CIRC["CIRCAAA"][3].update(report_t=4.3, priority=5.0)
CIRC["CIRCAAA"][7].update(report_t=9.5, priority=6.0)
for cid, js in CIRC.items():          # truth fix times (any fixed rule is fine for the fake)
    for i, j in enumerate(js):
        j["fix_t"] = j["report_t"] + 8.0 + 0.3 * i
CIRC["CIRCAAA"][7]["fix_t"] = 18.4
CIRC["CIRCAAA"][3]["fix_t"] = 15.0

HOMES = {
    "h_story": {"circuit_id": "CIRCAAA", "cell_id": "c1", "overhead": True,
                "path_device_keys": ["DEVKEYA003", "DEVKEYA007", "DEVKEYA099"], "circuit_crews": 3},
    "h_big": {"circuit_id": "CIRCBBB", "cell_id": "c2", "overhead": True,
              "path_device_keys": ["DEVKEYB005"], "circuit_crews": 4},
    "h_notopo": {"circuit_id": "CIRCAAA", "cell_id": "c1", "overhead": None,
                 "path_device_keys": [], "circuit_crews": 3},
}


def _known_jobs(circuit_id, t):
    return [{k: v for k, v in j.items() if k != "fix_t"}
            for j in CIRC[circuit_id] if j["report_t"] <= t < j["fix_t"]]


def _home_info(home_id):
    return dict(HOMES[home_id])   # KeyError for unknown, like Lane A


def _home_state(home_id, t):
    info = HOMES[home_id]
    path = set(info["path_device_keys"])
    pj = [j for j in CIRC[info["circuit_id"]] if j["device_key"] in path]
    if home_id == "h_notopo":    # no topology but out (feed knows from elsewhere)
        pj = [CIRC["CIRCAAA"][3]]
    if not pj:
        return {"is_out": False, "out_since_t": None, "restored_at_t": None, "stage": None, "stage_updated_t": None}
    out_since = min(j["report_t"] for j in pj)
    restored = max(j["fix_t"] for j in pj)
    if t < out_since:
        return {"is_out": False, "out_since_t": None, "restored_at_t": None, "stage": None, "stage_updated_t": None}
    if t >= restored:
        return {"is_out": False, "out_since_t": out_since, "restored_at_t": restored,
                "stage": "restored", "stage_updated_t": restored}
    stage = "assessing" if t < out_since + 2 else "repairing"
    return {"is_out": True, "out_since_t": out_since, "restored_at_t": None,
            "stage": stage, "stage_updated_t": out_since if stage == "assessing" else out_since + 2}


def _ref_schedule(jobs, ncrews, t_start):
    """Prototype docs/prototype/sim.py schedule (reference)."""
    order = sorted(range(len(jobs)), key=lambda j: jobs[j]['rel'])
    fin = [None] * len(jobs); avail = []; crews = [t_start] * ncrews; heapq.heapify(crews); p = 0
    left = len(jobs)
    while left:
        T = heapq.heappop(crews)
        while p < len(order) and jobs[order[p]]['rel'] <= T:
            j = order[p]; heapq.heappush(avail, (jobs[j]['pri'], j)); p += 1
        if not avail:
            T = jobs[order[p]]['rel']
            while p < len(order) and jobs[order[p]]['rel'] <= T:
                j = order[p]; heapq.heappush(avail, (jobs[j]['pri'], j)); p += 1
        _, j = heapq.heappop(avail); s = max(T, jobs[j]['rel']); fin[j] = s + jobs[j]['dur']; left -= 1
        heapq.heappush(crews, fin[j])
    return fin


def _contract_schedule(jobs, crews):
    fin = _ref_schedule([{"rel": j["ready_t"], "dur": j["hours"], "pri": j["priority"]} for j in jobs],
                        crews, min([j["ready_t"] for j in jobs], default=0))
    return {j["job_id"]: (f - j["hours"], f) for j, f in zip(jobs, fin)}


@pytest.fixture
def fake_sim(monkeypatch):
    pkg = types.ModuleType("app.sim"); pkg.__path__ = []
    feed = types.ModuleType("app.sim.feed")
    feed.home_info, feed.home_state, feed.known_jobs = _home_info, _home_state, _known_jobs
    sched = types.ModuleType("app.sim.schedule"); sched.schedule = _contract_schedule
    labor = types.ModuleType("app.sim.labor"); labor.job_base_hours = lambda a, b, c: 5.08
    pkg.feed, pkg.schedule, pkg.labor = feed, sched, labor
    for name, mod in [("app.sim", pkg), ("app.sim.feed", feed), ("app.sim.schedule", sched),
                      ("app.sim.labor", labor)]:
        monkeypatch.setitem(sys.modules, name, mod)
    R.clear_cache()
    yield
    R.clear_cache()


def _p50(**kw):
    return R.get_restoration("h_story", t=5, **kw)["estimate"]["p50_h"]


# ------------------------------------------------------------------ scheduler
def test_vectorized_scheduler_matches_prototype():
    rnd = random.Random(3)
    for trial in range(30):
        J = rnd.randint(1, 25); crews = rnd.randint(1, 5); t0 = 2.0
        ready = np.array([max(t0, rnd.uniform(0, 15)) for _ in range(J)])
        prio = [rnd.random() for _ in range(J)]
        dur = np.array([[rnd.uniform(0.5, 20) for _ in range(J)] for _ in range(4)])
        order = R._rank(prio, list(ready))
        fin_sorted = R.schedule_batch(ready[order], dur[:, order], crews, t0)
        fin = np.empty_like(fin_sorted); fin[:, order] = fin_sorted
        for s in range(4):
            ref = _ref_schedule([{"rel": ready[i], "dur": dur[s, i], "pri": (prio[i], ready[i], i)}
                                 for i in range(J)], crews, t0)
            assert np.allclose(fin[s], ref), (trial, s)


# ------------------------------------------------------------------ estimate
def test_estimate_shape_and_order(fake_sim):
    out = R.get_restoration("h_story", t=5)
    assert set(load_mock("restoration.json")) <= set(out)
    est = out["estimate"]
    assert set(load_mock("restoration.json")["estimate"]) <= set(est)
    assert 0 < est["p10_h"] <= est["p50_h"] <= est["p90_h"]
    assert est["n_sims"] == 1000 and est["source"] == "model_estimate"
    assert est["confidence"] in {"low", "medium", "high"}
    assert est["headline"].startswith("Likely back")
    assert out["is_out"] and out["source"] == "model_estimate" and out["utility_etr"] is None
    assert out["status"]["source"] == "simulated_feed"
    assert out["status"]["label"] == R.STAGE_LABELS[out["status"]["stage"]]
    assert out["inputs"] == {"crews": 3, "access_blocked": False, "extra_damage": 0, "switching": True}
    assert out["cause"]["repairs_on_your_path"] == 1   # job 7 not reported at t=5
    assert out["cause"]["severity"] in {"major", "minor"}
    sr = out["step_restoration"]
    assert 1 <= sr["your_step"] <= sr["total_steps"]
    assert sr["message"] == "Repairs happen in steps. Some neighbors may get power back before you."
    assert [d["key"] for d in out["drivers"]] == ["crews_plus_2", "access_blocked", "extra_damage", "switching_off"]
    assert [d["label"] for d in out["drivers"]] == [d["label"] for d in load_mock("restoration.json")["drivers"]]
    assert "%" not in json.dumps(out)


def test_curve_monotone(fake_sim):
    curve = R.get_restoration("h_story", t=5)["chance_back_by"]
    assert 5 <= len(curve) <= 8
    hs = [c["t_from_now_h"] for c in curve]; ps = [c["prob"] for c in curve]
    assert hs == sorted(hs) and len(set(hs)) == len(hs) and all(isinstance(h, int) for h in hs)
    assert ps == sorted(ps) and ps[-1] >= 0.98


def test_levers_direction(fake_sim):
    base = _p50()
    assert _p50(crews=5) <= base
    assert _p50(access_blocked=True) >= base
    assert _p50(switching=False) >= base
    assert _p50(extra_damage=1) >= base
    out = R.get_restoration("h_story", t=5)
    d = {x["key"]: x["effect_h"] for x in out["drivers"]}
    assert d["crews_plus_2"] <= 0 <= d["access_blocked"] and d["extra_damage"] >= 0 and d["switching_off"] >= 0


def test_active_driver_marked(fake_sim):
    out = R.get_restoration("h_story", t=5, access_blocked=True, switching=False)
    d = {x["key"]: x for x in out["drivers"]}
    assert d["access_blocked"]["active"] and d["switching_off"]["active"]


def test_deterministic(fake_sim):
    a = R.get_restoration("h_story", t=5, crews=2)
    R.clear_cache()
    b = R.get_restoration("h_story", t=5, crews=2)
    assert a == b


def test_runtime_40_jobs(fake_sim):
    R.get_restoration("h_big", t=1)  # warm numpy
    R.clear_cache()
    t0 = time.perf_counter()
    out = R.get_restoration("h_big", t=1)
    dt = time.perf_counter() - t0
    assert out["cause"]["repairs_on_your_line"] == 40
    assert dt < 0.3, f"{dt * 1000:.0f} ms"


def test_not_out_shape(fake_sim):
    out = R.get_restoration("h_story", t=1)
    mock = load_mock("restoration_not_out.json")
    assert set(mock) <= set(out)
    assert out["is_out"] is False and out["estimate"] is None and out["chance_back_by"] == []
    assert out["recap"] is None and out["fallback"] is None


def test_restored_shape_and_recap(fake_sim):
    out = R.get_restoration("h_story", t=19)
    mock = load_mock("restoration_restored.json")
    assert set(mock) <= set(out)
    assert out["source"] == "simulated_feed" and out["is_out"] is False
    assert out["restored_at_t"] == 18.4 and out["out_since_t"] == 4.3
    assert out["status"]["stage"] == "restored" and out["status"]["label"] == "Power is back on"
    rc = out["recap"]
    assert set(mock["recap"]) <= set(rc)
    assert rc["actual_h"] == 14.1
    fe = rc["first_estimate"]
    assert set(mock["recap"]["first_estimate"]) <= set(fe)
    assert fe["made_at_t"] == 4.3 and fe["back_by_t_low"] <= fe["back_by_t_high"]
    assert isinstance(fe["within_range"], bool)
    ue = rc["updated_estimate"]
    assert ue is not None and ue["made_at_t"] == 9.5
    assert rc["message"].startswith("You were out about 14 hours.")


def test_no_topology_fallback(fake_sim):
    out = R.get_restoration("h_notopo", t=5)
    assert set(load_mock("restoration.json")) <= set(out)
    assert out["estimate"] is None and out["is_out"] is True
    assert out["fallback"]["reason"] == "no_topology"
    assert out["fallback"]["link"] == "https://www.appalachianpower.com/outages/"


def test_unknown_home(fake_sim):
    with pytest.raises(UnknownHome):
        R.get_restoration("p_nope", t=5)


def test_no_ids_leak(fake_sim):
    for hid, t in [("h_story", 5), ("h_story", 12), ("h_story", 19), ("h_big", 1), ("h_notopo", 5)]:
        s = json.dumps(R.get_restoration(hid, t=t, extra_damage=1))
        for bad in ("DEVKEY", "JOBID", "CIRC"):
            assert bad not in s, (hid, t, bad)


def test_stub_when_sim_missing(monkeypatch):
    for mod in ("app.sim", "app.sim.feed", "app.sim.schedule", "app.sim.labor"):
        monkeypatch.setitem(sys.modules, mod, None)     # import app.sim.* -> ImportError
    monkeypatch.setattr(R, "_home_in_db", lambda h: True)
    R.clear_cache()
    try:
        for t, mock in [(-18, "restoration_not_out.json"), (5, "restoration.json"),
                        (19, "restoration_restored.json")]:
            out = R.get_restoration("p_demo", t=t, crews=4)
            m = load_mock(mock)
            assert set(m) <= set(out)
            assert out["home_id"] == "p_demo" and out["t"] == t
            assert out["inputs"]["crews"] == 4
            assert out["estimate"] == m["estimate"]
        monkeypatch.setattr(R, "_home_in_db", lambda h: False)
        R.clear_cache()
        with pytest.raises(UnknownHome):
            R.get_restoration("p_bad", t=5)
    finally:
        R.clear_cache()
