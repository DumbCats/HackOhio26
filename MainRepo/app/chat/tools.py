"""The four chat tools. They call the same Python functions as the REST routes.

Until the other lanes land their real code (contracts/API.md section 5), each tool falls back
to the contract mock, so chat works end to end today. The context (home, time, needs, scenario
params) always comes from the request, never from the user's message.
"""
import json
from pathlib import Path

MOCKS = Path(__file__).resolve().parents[2] / "contracts" / "mocks"

SCENARIO_KEYS = ("severity", "crews", "access_blocked", "extra_damage", "switching")


def _mock(name: str) -> dict:
    return json.loads((MOCKS / name).read_text(encoding="utf-8"))


def _scenario(ctx: dict) -> dict:
    return {k: ctx[k] for k in SCENARIO_KEYS if ctx.get(k) is not None}


def get_forecast(ctx: dict) -> dict:
    try:
        from app.models.risk import get_forecast as real
    except ImportError:
        return _mock("forecast.json")
    sev = ctx.get("severity")
    return real(ctx["home_id"], ctx["t"], 0.8 if sev is None else float(sev))


def get_restoration(ctx: dict) -> dict:
    try:
        from app.models.restoration import get_restoration as real
    except ImportError:
        t = ctx["t"]  # mock rule from contracts/API.md section 3
        if t < 4.3:
            return _mock("restoration_not_out.json")
        return _mock("restoration_restored.json" if t >= 18.4 else "restoration.json")
    return real(ctx["home_id"], ctx["t"], **{k: v for k, v in _scenario(ctx).items() if k != "severity"})


def get_prep(ctx: dict) -> dict:
    try:
        from app.guidance.prep import get_prep as real
    except ImportError:
        return _mock("prep.json")
    return real(ctx["home_id"], ctx["t"], ctx.get("needs", []), **_scenario(ctx))


def get_alerts(ctx: dict) -> dict:
    try:
        from app.guidance.alerts import get_alerts as real
    except ImportError:
        return _mock("alerts.json")
    return real(ctx["home_id"], ctx["t"], ctx.get("needs", []), ctx.get("low_power", False), **_scenario(ctx))


TOOLS = {
    "get_forecast": get_forecast,
    "get_restoration": get_restoration,
    "get_prep": get_prep,
    "get_alerts": get_alerts,
}
