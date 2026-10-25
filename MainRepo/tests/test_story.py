"""C9: the demo story (MASTER_PLAN section 2) holds on real data, end to end through the API."""
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture(scope="module")
def scn():
    return client.get("/api/scenario").json()


def _m(scn, key):
    return next(m["t"] for m in scn["moments"] if m["key"] == key)


def _home(scn, role):
    return next(h["home_id"] for h in scn["homes"] if h["role"] == role)


def test_beat1_forecast_high_not_out(scn):
    h = scn["default_home_id"]
    f = client.get(f"/api/forecast/{h}?t=-18").json()
    assert f["risk"]["band"] == "high" and f["fallback"] is None
    assert len(f["risk"]["factors"]) >= 1
    r = client.get(f"/api/restoration/{h}?t=-18").json()
    assert r["is_out"] is False and r["estimate"] is None
    a = client.get(f"/api/alerts/{h}?t=-18").json()
    assert [m["type"] for m in a["timeline"]] == ["pre_storm"]
    p = client.get(f"/api/prep/{h}?t=-18&needs=refrigerated_meds").json()
    assert p["phase"] == "before" and p["needs_actions"][0]["need"] == "refrigerated_meds"


def test_beat2_outage_confirmed(scn):
    h, t = scn["default_home_id"], _m(scn, "outage")
    r = client.get(f"/api/restoration/{h}?t={t}").json()
    assert r["is_out"] and r["estimate"]["p10_h"] < r["estimate"]["p90_h"]
    assert r["source"] == "model_estimate" and r["status"]["source"] == "simulated_feed"
    types = [m["type"] for m in client.get(f"/api/alerts/{h}?t={t}").json()["timeline"]]
    assert "outage_confirmed" in types


def test_beat5_estimate_updated(scn):
    h, t = scn["default_home_id"], _m(scn, "update")
    a = client.get(f"/api/alerts/{h}?t={t}").json()
    assert "estimate_updated" in [m["type"] for m in a["timeline"]]
    assert any(r["rule_id"] == "R3" for r in a["rules_fired"])
    # what-ifs move the estimate, never the feed
    base = client.get(f"/api/restoration/{h}?t={t}").json()
    blocked = client.get(f"/api/restoration/{h}?t={t}&access_blocked=true").json()
    assert blocked["estimate"]["p50_h"] > base["estimate"]["p50_h"]
    assert blocked["is_out"] == base["is_out"] and blocked["out_since_t"] == base["out_since_t"]


def test_beat6_restored_inside_updated_range(scn):
    h, t = scn["default_home_id"], _m(scn, "restored")
    r = client.get(f"/api/restoration/{h}?t={t}").json()
    assert r["is_out"] is False and r["restored_at_t"] is not None and t >= r["restored_at_t"]
    recap = r["recap"]
    assert recap["updated_estimate"]["within_range"] is True
    assert recap["updated_estimate"]["back_by_t_low"] <= recap["restored_at_t"] <= recap["updated_estimate"]["back_by_t_high"]
    assert "restored" in [m["type"] for m in client.get(f"/api/alerts/{h}?t={t}").json()["timeline"]]


def test_beat7_fallback_home(scn):
    f = client.get(f"/api/forecast/{_home(scn, 'fallback')}?t=-18").json()
    assert f["fallback"] is not None and f["risk"]["band"] == "unknown"
    assert f["fallback"]["link"].startswith("https://")


def test_moments_are_in_order(scn):
    ts = [m["t"] for m in scn["moments"]]
    assert ts == sorted(ts) and ts[0] == -18
