"""Lane D guidance: prep buckets (N9), declared needs (N2), alert rules and channels (N1)."""
from app.guidance import text
from app.guidance.alerts import get_alerts
from app.guidance.prep import bucket_for_hours, get_prep


def test_buckets():
    assert [bucket_for_hours(h) for h in (1, 5, 30, 100)] == ["<4h", "4-24h", "24-72h", "72h+"]


def test_prep_phases_and_fixed_text(demo_homes):
    h = demo_homes["story"]
    before = get_prep(h, -18)
    assert before["phase"] == "before" and before["duration_bucket"] == "24-72h"  # HIGH band
    assert before["safety"] == text.SAFETY and before["emergency_line"] == text.EMERGENCY_LINE
    assert get_prep(h, 96)["phase"] == "after"


def test_needs_only_from_toggles(demo_homes):
    h = demo_homes["story"]
    assert get_prep(h, -18)["needs_actions"] == []
    got = get_prep(h, -18, "well_water,bogus,critical_facility")["needs_actions"]
    assert [n["need"] for n in got] == ["well_water", "critical_facility"]


def test_alert_channels_and_call_offer(demo_homes):
    h = demo_homes["story"]
    from app.sim.scenario import get_scenario
    t_out = next(m["t"] for m in get_scenario()["moments"] if m["key"] == "update")
    plain = get_alerts(h, t_out)
    assert all(m["channel"] == "push" for m in plain["timeline"])
    low = get_alerts(h, t_out, low_power=True)
    assert all(m["channel"] == "sms" for m in low["timeline"])
    for m in plain["timeline"]:
        assert len(m["text"].split()) < 60
    blocked = get_alerts(h, t_out, ["medical_device"], access_blocked=True, extra_damage=3)
    assert any(c["channel"] == "call" for c in blocked["channels"])


def test_fallback_home_has_no_prestorm_alert(demo_homes):
    a = get_alerts(demo_homes["fallback"], 0)
    assert a["eligible"] and not any(m["type"] == "pre_storm" for m in a["timeline"])
