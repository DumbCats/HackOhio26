"""Mock endpoints served from contracts/mocks/*.json (mock rule: contracts/API.md section 3).

main.py mounts this router last, so any real route a lane has landed wins and these only answer
what is still missing.
"""
import json
from typing import Optional

from fastapi import APIRouter, Query

from app import config

MOCKS = config.REPO_ROOT / "contracts" / "mocks"

router = APIRouter()


def _load(name: str) -> dict:
    return json.loads((MOCKS / f"{name}.json").read_text(encoding="utf-8"))


def _fallback_home_id() -> Optional[str]:
    for home in _load("scenario").get("homes", []):
        if "little history" in home.get("label", "").lower():
            return home["home_id"]
    return None


def _with_home(body: dict, home_id: str) -> dict:
    if "home_id" in body:
        body["home_id"] = home_id
    return body


@router.get("/api/scenario")
def scenario():
    return _load("scenario")


@router.get("/api/locate")
def locate(lat: float, lon: float):
    return _load("locate")


@router.get("/api/outage-map")
def outage_map(t: float = 0, severity: float = Query(config.DEFAULT_SEVERITY, ge=0, le=1)):
    return _load("outage_map")


@router.get("/api/forecast/{home_id}")
def forecast(home_id: str, t: float = 0, severity: float = Query(config.DEFAULT_SEVERITY, ge=0, le=1)):
    name = "forecast_fallback" if home_id == _fallback_home_id() else "forecast"
    return _with_home(_load(name), home_id)


@router.get("/api/restoration/{home_id}")
def restoration(
    home_id: str,
    t: float = 0,
    crews: Optional[int] = Query(None, ge=1, le=30),
    access_blocked: bool = False,
    extra_damage: int = Query(0, ge=0, le=10),
    switching: bool = True,
):
    if t < 4.3:
        name = "restoration_not_out"
    elif t >= 18.4:
        name = "restoration_restored"
    else:
        name = "restoration"
    return _with_home(_load(name), home_id)


@router.get("/api/prep/{home_id}")
def prep(home_id: str, t: float = 0, needs: str = ""):
    return _with_home(_load("prep"), home_id)


@router.get("/api/alerts/{home_id}")
def alerts(home_id: str, t: float = 0, needs: str = "", low_power: bool = False):
    body = _with_home(_load("alerts"), home_id)
    body["t"] = t
    body["timeline"] = [m for m in body.get("timeline", []) if m.get("t", 0) <= t]
    return body


@router.post("/api/chat")
def chat(req: dict):
    return _load("chat_response")
