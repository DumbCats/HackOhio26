"""Lane A routes (contracts/API.md section 3) plus /api/home and /api/repairs."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app import config
from app.sim import home, locate as loc, mapcells, scenario

router = APIRouter()


@router.get("/api/scenario")
def get_scenario():
    return scenario.get_scenario()


@router.get("/api/locate")
def get_locate(lat: float, lon: float):
    try:
        return loc.locate(lat, lon)
    except KeyError:
        raise HTTPException(status_code=404, detail="no area here")


@router.get("/api/outage-map")
def outage_map(t: float = 0, severity: float = Query(config.DEFAULT_SEVERITY, ge=0, le=1)):
    return mapcells.get_outage_map(t, severity)


@router.get("/api/home/{home_id}")
def get_home(home_id: str):
    try:
        return home.get_home(home_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="unknown home")


@router.get("/api/repairs/{home_id}")
def get_repairs(home_id: str, t: float = 0):
    try:
        return home.get_repairs(home_id, t)
    except KeyError:
        raise HTTPException(status_code=404, detail="unknown home")
