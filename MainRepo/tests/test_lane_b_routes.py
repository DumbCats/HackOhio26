"""Lane B HTTP layer: /api/forecast and /api/restoration match the contract mocks."""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.models.common import DB_PATH, get_conn, load_mock
from app.models.routes import router

pytestmark = pytest.mark.skipif(not DB_PATH.exists(), reason="build the DB first: python -m ingest.build_db")

app = FastAPI()
app.include_router(router)
client = TestClient(app)


@pytest.fixture(scope="module")
def home_id():
    conn = get_conn()
    row = conn.execute("SELECT premise_key FROM premises ORDER BY premise_key LIMIT 1").fetchone()
    return row[0]


def test_unknown_home_is_404():
    for path in ("/api/forecast/p_0000000000000000", "/api/restoration/p_0000000000000000"):
        r = client.get(path)
        assert r.status_code == 404
        assert r.json() == {"detail": "unknown home"}


def test_forecast_keys_match_mock(home_id):
    r = client.get(f"/api/forecast/{home_id}", params={"t": -18, "severity": 0.8})
    assert r.status_code == 200
    body = r.json()
    assert set(load_mock("forecast.json")) <= set(body)
    assert body["risk"]["band"] in {"low", "medium", "high", "unknown"}
    assert "%" not in json.dumps(body)


def test_restoration_keys_match_mock(home_id):
    r = client.get(f"/api/restoration/{home_id}", params={"t": 5})
    assert r.status_code == 200
    assert set(load_mock("restoration_not_out.json")) <= set(r.json())


def test_param_validation():
    assert client.get("/api/forecast/p_x", params={"severity": 2}).status_code == 422
    assert client.get("/api/restoration/p_x", params={"crews": 0}).status_code == 422
