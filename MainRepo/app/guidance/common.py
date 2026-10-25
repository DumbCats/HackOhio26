"""Shared helpers for guidance: needs parsing and calls into Lane B with scenario params."""
from __future__ import annotations

from app import config
from app.guidance.text import NEED_KEYS

RESTORATION_KEYS = ("crews", "access_blocked", "extra_damage", "switching")


def parse_needs(needs) -> list[str]:
    """csv string or list -> known need keys only, in a fixed order. Never stored."""
    if not needs:
        return []
    if isinstance(needs, str):
        needs = needs.split(",")
    got = {str(n).strip() for n in needs}
    return [k for k in NEED_KEYS if k in got]


def restoration_for(home_id: str, t: float, scenario: dict | None = None) -> dict:
    from app.models.restoration import get_restoration
    sc = {k: v for k, v in (scenario or {}).items() if k in RESTORATION_KEYS and v is not None}
    return get_restoration(home_id, t=t, **sc)


def forecast_for(home_id: str, t: float, scenario: dict | None = None) -> dict:
    from app.models.risk import get_forecast
    sev = (scenario or {}).get("severity")
    return get_forecast(home_id, t=t, severity=config.DEFAULT_SEVERITY if sev is None else float(sev))
