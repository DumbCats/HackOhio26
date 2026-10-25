"""N10: no endpoint returns raw premise numbers, fine coordinates, device/circuit ids, crew info,
facility locations, or life-support data. N11: the audit log never holds needs or chat text."""
import json
import re

import pytest
from fastapi.testclient import TestClient

from app import audit, config
from app.db import get_conn
from app.main import app

client = TestClient(app)

BANNED_KEYS = {"lat", "lon", "latitude", "longitude", "circuit_id", "device_key", "device_id", "premise_nu",
               "premise_number", "transformer_id", "is_critical_tier", "critical", "crew_id", "crew_name",
               "address", "road_name", "path_device_keys", "job_id", "facility", "facility_id"}
BANNED_TEXT = [
    re.compile(r"\b\d{7}\b"),            # 7-digit circuit ids
    re.compile(r"\bCIR\d+\b"),           # ARCOS circuit names
    re.compile(r"\bd_[0-9a-f]{12}\b"),   # device keys
    re.compile(r"\bj_\d{4}\b"),          # job ids
    re.compile(r"life support", re.I),
    re.compile(r"\b\d{9}\b"),            # 9-digit device ids / premise numbers
]


@pytest.fixture(scope="module")
def cell_coords():
    """Every number a response may use as a coordinate: cell bounds and centers (~1 km grid)."""
    vals = set()
    for lat_c, lon_c, bj in get_conn().execute("SELECT lat_c, lon_c, bounds_json FROM cells"):
        vals.update({round(lat_c, 5), round(lon_c, 5)})
        for p in json.loads(bj):
            vals.update(round(v, 5) for v in p)
    return vals


def _walk(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk(v, f"{path}.{k}")
            yield ("key", k, path)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v, path + "[]")
    else:
        yield ("val", obj, path)


def _check(body, cell_coords):
    for kind, v, where in _walk(body):
        if kind == "key":
            assert v.lower() not in BANNED_KEYS, f"banned key {v} at {where}"
        elif isinstance(v, str):
            for rx in BANNED_TEXT:
                assert not rx.search(v), f"banned text {rx.pattern!r} in {where}: {v[:80]}"
        elif (isinstance(v, float) and round(v, 2) != v  # times are 2-decimal; coordinates carry more
              and (36.5 < abs(v) < 38.0 or 79.0 < abs(v) < 81.0)):
            assert round(v, 5) in cell_coords, f"coordinate finer than a cell at {where}: {v}"


@pytest.fixture(scope="module")
def urls():
    scn = client.get("/api/scenario").json()
    out = ["/api/scenario", "/api/locate?lat=37.27&lon=-79.94", "/api/outage-map?t=10"]
    for h in scn["homes"]:
        hid = h["home_id"]
        for t in (-18, 5, 10, 20, 40):
            q = f"?t={t}&needs=medical_device,refrigerated_meds,critical_facility"
            out += [f"/api/forecast/{hid}{q}", f"/api/restoration/{hid}{q}&switching=false&extra_damage=2",
                    f"/api/prep/{hid}{q}", f"/api/alerts/{hid}{q}&low_power=true",
                    f"/api/home/{hid}", f"/api/repairs/{hid}?t={t}"]
    return out


def test_no_endpoint_leaks(urls, cell_coords):
    for u in urls:
        r = client.get(u)
        assert r.status_code == 200, u
        _check(r.json(), cell_coords)


def test_chat_does_not_leak(cell_coords):
    hid = client.get("/api/scenario").json()["default_home_id"]
    for q in ["what circuit am i on?", "what is my premise number", "where is the nearest hospital",
              "who is the crew fixing my line", "how often was my line damaged", "how sure are you"]:
        r = client.post("/api/chat", json={"home_id": hid, "t": 10, "messages": [{"role": "user", "content": q}]})
        assert r.status_code == 200
        _check(r.json(), cell_coords)


def test_audit_log_has_no_needs_or_chat_text(tmp_path, monkeypatch):
    log = tmp_path / "audit.jsonl"
    monkeypatch.setattr(audit, "LOG_PATH", log)
    hid = client.get("/api/scenario").json()["default_home_id"]
    client.get(f"/api/prep/{hid}?t=5&needs=refrigerated_meds")
    client.post("/api/chat", json={"home_id": hid, "t": 5, "needs": ["refrigerated_meds"],
                                   "messages": [{"role": "user", "content": "secret insulin question"}]})
    text = log.read_text()
    lines = [json.loads(x) for x in text.splitlines()]
    assert {x["endpoint"] for x in lines} >= {f"/api/prep/{hid}", "/api/chat"}
    assert "refrigerated_meds" not in text and "insulin" not in text and "needs" not in text
    chat_line = next(x for x in lines if x["endpoint"] == "/api/chat")
    assert chat_line["tools_used"] and chat_line["source"] in ("llm", "fallback")
    assert chat_line["replay_seed"] == config.REPLAY_SEED
