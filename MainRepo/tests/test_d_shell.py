"""Lane D shell: config constants, db helper, mock routes (API.md section 3 mock rule), CORS."""
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app import config, db
from app.main import app

client = TestClient(app)

MOCK_HOMES = {h["label"]: h["home_id"] for h in json.loads(
    (config.REPO_ROOT / "contracts/mocks/scenario.json").read_text())["homes"]}
MOCK_STORY = MOCK_HOMES["Maya's home (story)"]

from app.sim.scenario import get_scenario  # noqa: E402  real demo homes
_REAL = {h["role"]: h["home_id"] for h in get_scenario()["homes"]}
STORY = _REAL["story"]
FALLBACK = _REAL["fallback"]


def _mock_client():
    from fastapi import FastAPI
    from app import mock_routes
    shell = FastAPI()
    shell.include_router(mock_routes.router)
    return TestClient(shell)


def test_config_constants():
    assert (config.REPLAY_SEED, config.MC_SEED) == (8, 42)
    assert config.REGIONAL_CREWS == 150
    assert config.DEFAULT_SEVERITY == 0.8
    assert (config.REPO_ROOT / "MASTER_PLAN.md").exists()
    assert config.DB_PATH.name == "outage_concierge.db" or config.DB_PATH.is_absolute()
    assert config.ANTHROPIC_API_KEY is None or isinstance(config.ANTHROPIC_API_KEY, str)


def test_get_conn_uses_row_factory(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.db")
    conn = db.get_conn()
    assert conn.row_factory is sqlite3.Row
    conn.execute("create table x(a int)")
    conn.execute("insert into x values (1)")
    assert conn.execute("select a from x").fetchone()["a"] == 1
    conn.close()


@pytest.mark.parametrize("url", [
    "/api/scenario", "/api/locate?lat=39.9&lon=-82.9", "/api/outage-map?t=5&severity=0.8",
    f"/api/forecast/{STORY}", f"/api/restoration/{STORY}", f"/api/prep/{STORY}",
    f"/api/alerts/{STORY}",
])
def test_every_get_endpoint_has_a_mock(url):
    r = client.get(url)
    assert r.status_code == 200
    assert r.json()


def test_chat_mock():
    """The mock router's chat answer (the real app now overrides it with app.chat.routes)."""
    from fastapi import FastAPI
    from app import mock_routes
    shell = FastAPI()
    shell.include_router(mock_routes.router)
    r = TestClient(shell).post("/api/chat", json={"home_id": STORY, "messages": []})
    assert r.status_code == 200
    assert {"reply", "safety_flag", "source"} <= set(r.json())


def test_forecast_fallback_home():
    assert client.get(f"/api/forecast/{FALLBACK}").json()["fallback"] is not None
    body = client.get(f"/api/forecast/{STORY}").json()
    assert body["fallback"] is None and body["home_id"] == STORY


@pytest.mark.parametrize("t,mock", [
    (0, "restoration_not_out"), (4.29, "restoration_not_out"),
    (4.3, "restoration"), (10, "restoration"), (18.39, "restoration"),
    (18.4, "restoration_restored"), (50, "restoration_restored"),
])
def test_restoration_by_t(t, mock):
    """Mock router rule (the real app now serves Lane B's model)."""
    expected = json.loads((config.REPO_ROOT / f"contracts/mocks/{mock}.json").read_text())
    got = _mock_client().get(f"/api/restoration/{MOCK_STORY}?t={t}").json()
    expected["home_id"] = MOCK_STORY
    assert got == expected


def test_alerts_filtered_by_t():
    def times(t):
        return [m["t"] for m in client.get(f"/api/alerts/{STORY}?t={t}").json()["timeline"]]
    assert times(-24) == []
    assert times(-18) == [-18]
    assert times(10) == sorted(times(10)) and max(times(10)) <= 10
    assert len(times(96)) > len(times(-18))


def test_query_param_validation():
    assert client.get("/api/outage-map?severity=2").status_code == 422
    assert client.get(f"/api/restoration/{STORY}?crews=31").status_code == 422
    assert client.get(f"/api/restoration/{STORY}?extra_damage=11").status_code == 422


def test_cors_only_for_frontend():
    ok = client.get("/api/scenario", headers={"Origin": "http://localhost:5173"})
    assert ok.headers["access-control-allow-origin"] == "http://localhost:5173"
    other = client.get("/api/scenario", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in other.headers


def test_real_router_wins_over_mock(monkeypatch):
    """A lane router mounted before the mocks takes over its route (how Lanes A-C will land)."""
    from fastapi import APIRouter, FastAPI
    from app import mock_routes
    real = APIRouter()

    @real.get("/api/scenario")
    def _real():
        return {"real": True}

    shell = FastAPI()
    shell.include_router(real)
    shell.include_router(mock_routes.router)
    c = TestClient(shell)
    assert c.get("/api/scenario").json() == {"real": True}
    assert c.get(f"/api/prep/{STORY}").status_code == 200  # untouched routes still mocked


def test_broken_lane_router_does_not_stop_startup():
    import app.main as m
    assert m.app.routes  # imported despite missing app.sim / app.models / app.guidance
