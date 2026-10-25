"""Lane B routes: /api/forecast and /api/restoration (shapes: contracts/API.md)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.models import restoration, risk
from app.models.common import DEFAULT_SEVERITY, UnknownHome

router = APIRouter()


@router.get("/api/forecast/{home_id}")
def forecast(home_id: str, t: float = Query(0, ge=-1000, le=1000), severity: float = Query(DEFAULT_SEVERITY, ge=0, le=1)):
    try:
        return risk.get_forecast(home_id, t=t, severity=severity)
    except UnknownHome:
        raise HTTPException(status_code=404, detail="unknown home")


@router.get("/api/restoration/{home_id}")
def restoration_route(
    home_id: str,
    t: float = Query(0, ge=-1000, le=1000),
    crews: int | None = Query(None, ge=1, le=30),
    access_blocked: bool = False,
    extra_damage: int = Query(0, ge=0, le=10),
    switching: bool = True,
):
    try:
        return restoration.get_restoration(
            home_id, t=t, crews=crews, access_blocked=access_blocked,
            extra_damage=extra_damage, switching=switching,
        )
    except UnknownHome:
        raise HTTPException(status_code=404, detail="unknown home")
