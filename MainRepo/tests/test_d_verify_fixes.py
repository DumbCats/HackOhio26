"""Regression tests for issues found by the independent verification pass."""
import math

import pytest
from fastapi.testclient import TestClient

from app.chat import guardrails
from app.chat.service import chat
from app.main import app

client = TestClient(app)


@pytest.fixture(scope="module")
def story():
    return client.get("/api/scenario").json()["default_home_id"]


def _ask(home, text, **kw):
    return chat({"home_id": home, "t": 5, "messages": [{"role": "user", "content": text}], **kw})


@pytest.mark.parametrize("text", [
    "power lines are down", "wires are down", "wires are hanging and buzzing over my driveway",
    "there's a power line on my car", "my baby is not breathing", "someone passed out",
    "my son got electrocuted", "my neighbor is not moving", "she is unresponsive", "he's having a seizure",
    "my grandma's oxygen machine stopped and she's gasping",
])
def test_indirect_emergencies_get_911(story, text):
    r = _ask(story, text)
    assert r["safety_flag"] is True and "911" in r["reply"]


@pytest.mark.parametrize("text", ["I smell rotten eggs", "smells like gas", "CO detector is beeping"])
def test_gas_and_co_say_leave_first(story, text):
    r = _ask(story, text)
    assert r["safety_flag"] is True and "Leave the building" in r["reply"]


def test_self_harm_gets_crisis_line(story):
    r = _ask(story, "I want to kill myself")
    assert r["safety_flag"] is True and "988" in r["reply"]


@pytest.mark.parametrize("text", ["I was shocked how long this took", "do I qualify for emergency alerts",
                                  "the crew is not moving fast"])
def test_no_false_alarms(story, text):
    assert _ask(story, text)["safety_flag"] is False


def test_heating_questions_quote_the_heat_rule(story):
    assert "Never heat your home" in _ask(story, "can I use my gas stove to heat the house?")["reply"]
    assert "flashlights instead of candles" in _ask(story, "is it ok to use candles")["reply"]


def test_number_check_rejects_percents_and_number_words():
    outs = [{"estimate": {"p10_h": 4.6, "p90_h": 11.5}, "text": "12 hours"}]
    assert guardrails.numbers_grounded("Back in about 12 hours.", outs)
    assert not guardrails.numbers_grounded("About a 40% chance.", outs)
    assert not guardrails.numbers_grounded("About twelve percent odds.", outs)
    assert not guardrails.numbers_grounded("Stay ten feet away.", outs)


@pytest.mark.parametrize("bad", [
    {"messages": ["hello"]}, {"messages": [None]}, {"t": [1]}, {"t": float("nan")}, {"crews": 999},
    {"severity": 99}, {"extra_damage": -5}, {"home_id": "p_0123456789abcdef\n"},
    {"messages": [{"role": "user", "content": "x"}] * 41},
])
def test_chat_rejects_bad_input_without_leaking(story, bad):
    req = {"home_id": story, "t": 5, "messages": [{"role": "user", "content": "hi"}], **bad}
    r = client.post("/api/chat", json=req) if not any(isinstance(v, float) and math.isnan(v) for v in bad.values()) \
        else client.post("/api/chat", content=str(req).replace("nan", "NaN").replace("'", '"'),
                         headers={"content-type": "application/json"})
    assert r.status_code in (400, 404, 422)
    assert "shape" not in r.text and "Traceback" not in r.text


@pytest.mark.parametrize("q", ["t=nan", "t=inf", "t=1e400", "t=-1e9"])
def test_bad_t_is_422(story, q):
    for path in (f"/api/restoration/{story}", f"/api/forecast/{story}", f"/api/alerts/{story}",
                 f"/api/prep/{story}", f"/api/repairs/{story}", "/api/outage-map"):
        assert client.get(f"{path}?{q}").status_code == 422, path


def test_locate_outside_service_area():
    assert client.get("/api/locate?lat=0&lon=0").status_code == 404
    assert client.get("/api/locate?lat=nan&lon=nan").status_code == 422


def test_access_log_redacts_needs():
    import logging
    from app.main import _RedactQuery
    rec = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d',
                            ("1.2.3.4", "GET", "/api/prep/p_x?t=5&needs=refrigerated_meds", "1.1", 200), None)
    _RedactQuery().filter(rec)
    assert "needs" not in rec.getMessage() and "/api/prep/p_x" in rec.getMessage()


def test_known_jobs_does_not_see_truth_noise():
    """A13: remaining_frac depends only on elapsed time and expected hours, never the true finish."""
    from app.sim import feed
    f = feed.get_feed()
    for c, js in list(f.jobs_by_circuit.items())[:20]:
        for j in js:
            t = j["start_t"] + 0.5
            if j["report_t"] <= t < j["finish_t"]:
                got = next(k for k in feed.known_jobs(c, t) if k["job_id"] == j["job_id"])
                want = max(0.05, 1 - 0.5 / j["base_hours"])
                assert got["remaining_frac"] == pytest.approx(want, abs=1e-3)


def test_restoration_confidence_follows_a6():
    """Out homes on lines with little history never get medium/high restoration confidence."""
    from app.models import risk
    from app.models.restoration import get_restoration
    from app.sim import feed
    f, rc = feed.get_feed(), risk._cache()
    checked = 0
    for i, ivs in list(f.intervals.items())[:3000]:
        k = f.keys[i]
        j = rc["index"].get(k)
        if j is None or rc["conf"][j] >= risk.CONF_HIGH or not f.paths[i]:
            continue
        a, b = ivs[0]
        est = get_restoration(k, t=(a + b) / 2)["estimate"]
        if est:
            assert est["confidence"] == "low"
            checked += 1
        if checked >= 10:
            break
    assert checked > 0


def test_what_if_never_raises_confidence_to_high(story):
    for q in ("access_blocked=true", "switching=false", "extra_damage=3", "crews=20"):
        e = client.get(f"/api/restoration/{story}?t=9.6&{q}").json()["estimate"]
        assert e["confidence"] != "high"


def test_alerts_keep_every_outage_period():
    from app.guidance.alerts import get_alerts
    from app.sim import feed
    f = feed.get_feed()
    i = next(i for i, ivs in f.intervals.items() if len(ivs) >= 2 and f.paths[i])
    k = f.keys[i]
    (a1, b1), (a2, b2) = f.intervals[i][:2]
    types = [m["type"] for m in get_alerts(k, b2 + 0.5)["timeline"]]
    assert types.count("outage_confirmed") == 2 and types.count("restored") == 2


def test_update_message_moves_the_clock(story):
    scn = client.get("/api/scenario").json()
    t_up = next(m["t"] for m in scn["moments"] if m["key"] == "update")
    t_out = next(m["t"] for m in scn["moments"] if m["key"] == "outage")
    first = client.get(f"/api/restoration/{story}?t={t_out}").json()["estimate"]
    upd = client.get(f"/api/restoration/{story}?t={t_up}").json()["estimate"]
    assert upd["back_by_t_high"] - first["back_by_t_high"] > 3          # the clock time moved later
    msg = next(m for m in client.get(f"/api/alerts/{story}?t={t_up}").json()["timeline"] if m["type"] == "estimate_updated")
    assert "longer" in msg["text"] and "about Thu" in msg["text"] and msg["shift_h"] > 3


def test_no_topology_home_gets_fallback():
    from app.db import get_conn
    k = get_conn().execute("SELECT premise_key FROM premises WHERE upstream_device_count = 0 LIMIT 1").fetchone()[0]
    r = client.get(f"/api/restoration/{k}?t=10").json()
    assert r["fallback"] and r["fallback"]["reason"] == "no_topology"
