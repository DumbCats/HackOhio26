"""POST /api/chat reaches the real chat() and maps bad requests to HTTP 400."""
import copy
import json

from fastapi.testclient import TestClient

from app import config
from app.main import app

client = TestClient(app)
REQ = json.loads((config.REPO_ROOT / "contracts/mocks/chat_request.json").read_text())
RESP_KEYS = set(json.loads((config.REPO_ROOT / "contracts/mocks/chat_response.json").read_text()))


def test_route_calls_chat_not_the_mock(monkeypatch):
    from app.chat import routes
    monkeypatch.setattr(routes, "chat", lambda req: {"marker": req["home_id"]})
    assert client.post("/api/chat", json=REQ).json() == {"marker": REQ["home_id"]}


def test_chat_request_mock_gets_a_response_shaped_reply():
    r = client.post("/api/chat", json=REQ)
    assert r.status_code == 200
    body = r.json()
    assert set(body) == RESP_KEYS
    assert body["source"] == "fallback" and isinstance(body["reply"], str) and body["reply"]


def test_emergency_goes_through_the_route():
    req = copy.deepcopy(REQ)
    req["messages"][-1]["content"] = "there is a downed power line outside"
    body = client.post("/api/chat", json=req).json()
    assert body["safety_flag"] is True and "911" in body["reply"]


def test_bad_requests_are_400():
    bad_id = {**REQ, "home_id": "nope"}
    no_msgs = {**REQ, "messages": []}
    assistant_last = {**REQ, "messages": [{"role": "assistant", "content": "hi"}]}
    too_long = {**REQ, "messages": [{"role": "user", "content": "x" * 1001}]}
    for req in (bad_id, no_msgs, assistant_last, too_long):
        r = client.post("/api/chat", json=req)
        assert r.status_code == 400, req
        assert r.json()["detail"]
