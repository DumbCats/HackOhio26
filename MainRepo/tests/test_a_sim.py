"""Lane A: labor hours, scheduler, truth feed, map cells, locate (contracts/API.md section 5)."""
import math

import pytest

from app.sim import feed, labor, mapcells
from app.sim.locate import locate
from app.sim.schedule import schedule


def test_job_base_hours_from_workbook():
    assert labor.job_base_hours("Pole", False, "") == pytest.approx(4.812 * 4.5)
    assert labor.job_base_hours("primary", True, "Track Hoe") == pytest.approx((1.129 + 0.5 + 1.312) * 4.5)
    assert labor.job_base_hours("", False, "") == labor.job_base_hours("primary", False, "")


def test_schedule_priority_and_waiting():
    jobs = [{"job_id": "a", "ready_t": 0, "hours": 2, "priority": 2},
            {"job_id": "b", "ready_t": 0, "hours": 1, "priority": 1},
            {"job_id": "c", "ready_t": 10, "hours": 1, "priority": 0}]
    out = schedule(jobs, 1)
    assert out["b"] == (0, 1) and out["a"] == (1, 3) and out["c"] == (10, 11)
    two = schedule(jobs, 2)
    assert two["a"] == (0, 2) and two["b"] == (0, 1)


@pytest.fixture(scope="module")
def story(demo_homes):
    return demo_homes["story"]


def test_feed_contract_shapes(story):
    info = feed.home_info(story)
    assert set(info) == {"circuit_id", "cell_id", "overhead", "path_device_keys", "circuit_crews"}
    assert info["path_device_keys"] and info["circuit_crews"] >= 1
    s = feed.home_state(story, -18)
    assert s == {"is_out": False, "out_since_t": None, "restored_at_t": None, "stage": None, "stage_updated_t": None}
    with pytest.raises(KeyError):
        feed.home_info("p_0000000000000000")


def test_feed_never_leaks_future_restore(story):
    f = feed.get_feed()
    a, b = f.intervals[f.idx(story)][0]
    during = feed.home_state(story, (a + b) / 2)
    assert during["is_out"] and during["restored_at_t"] is None
    assert during["stage"] in ("assessing", "crew_assigned", "repairing")
    after = feed.home_state(story, b + 0.01)
    assert not after["is_out"] and after["restored_at_t"] == math.floor(b * 100 + 1e-9) / 100 and after["stage"] == "restored"


def test_known_jobs_only_reported_and_open(story):
    info = feed.home_info(story)
    for t in (2, 6, 12):
        for j in feed.known_jobs(info["circuit_id"], t):
            assert j["report_t"] <= t and 0 < j["remaining_frac"] <= 1
            assert {"job_id", "device_key", "base_hours", "priority", "report_t", "asset_type"} <= set(j)


def test_outage_map_counts_and_privacy():
    m = mapcells.get_outage_map(10)
    assert m["source"] == "simulated_feed" and m["summary"]["homes_out"] > 0
    for c in m["cells"]:
        assert c["homes"] >= 10 and 0 <= c["homes_out"] <= c["homes"]
        want = "out" if c["homes_out"] * 2 >= c["homes"] and c["homes_out"] else "partial" if c["homes_out"] else "on"
        assert c["status"] == want
    assert mapcells.get_outage_map(-18)["summary"]["homes_out"] == 0


def test_severity_moves_map_bands():
    hi = sum(c["risk_band"] == "high" for c in mapcells.get_outage_map(0, 1.0)["cells"])
    lo = sum(c["risk_band"] == "high" for c in mapcells.get_outage_map(0, 0.3)["cells"])
    assert hi > lo


def test_locate_returns_a_home_in_a_visible_cell():
    r = locate(37.27, -79.94)
    assert r["home_id"].startswith("p_") and r["cell_id"].startswith("c_") and r["area"].startswith("Area")
