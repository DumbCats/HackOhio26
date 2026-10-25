"""Lane D guidance routes: /api/prep and /api/alerts (contracts/API.md section 3)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app import config
from app.guidance import alerts, prep
from app.models.common import UnknownHome

router = APIRouter()


def _scenario(severity, crews, access_blocked, extra_damage, switching) -> dict:
    return {"severity": severity, "crews": crews, "access_blocked": access_blocked,
            "extra_damage": extra_damage, "switching": switching}


@router.get("/api/prep/{home_id}")
def get_prep(home_id: str, t: float = Query(0, ge=-1000, le=1000), needs: str = "",
             severity: float = Query(config.DEFAULT_SEVERITY, ge=0, le=1),
             crews: Optional[int] = Query(None, ge=1, le=30), access_blocked: bool = False,
             extra_damage: int = Query(0, ge=0, le=10), switching: bool = True):
    try:
        return prep.get_prep(home_id, t, needs, **_scenario(severity, crews, access_blocked, extra_damage, switching))
    except (UnknownHome, KeyError):
        raise HTTPException(status_code=404, detail="unknown home")


@router.get("/api/alerts/{home_id}")
def get_alerts(home_id: str, t: float = Query(0, ge=-1000, le=1000), needs: str = "", low_power: bool = False,
               severity: float = Query(config.DEFAULT_SEVERITY, ge=0, le=1),
               crews: Optional[int] = Query(None, ge=1, le=30), access_blocked: bool = False,
               extra_damage: int = Query(0, ge=0, le=10), switching: bool = True):
    try:
        return alerts.get_alerts(home_id, t, needs, low_power,
                                 **_scenario(severity, crews, access_blocked, extra_damage, switching))
    except (UnknownHome, KeyError):
        raise HTTPException(status_code=404, detail="unknown home")
