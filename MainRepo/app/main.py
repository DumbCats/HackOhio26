"""FastAPI app: real lane routers first (if they import cleanly), mock router last.

Run from the repo root: uvicorn app.main:app --reload --port 8000
"""
import importlib
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import mock_routes

log = logging.getLogger("uvicorn.error")

# Each lane exposes `router = APIRouter()` in its routes.py (contracts/API.md section 5).
LANE_ROUTERS = [
    "app.sim.routes",
    "app.models.routes",
    "app.guidance.routes",
    "app.chat.routes",
]

app = FastAPI(title="Outage Concierge")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

for module_name in LANE_ROUTERS:
    try:
        app.include_router(importlib.import_module(module_name).router)
        log.info("real routes mounted: %s", module_name)
    except Exception as exc:  # missing or broken lane code must never stop the mocks
        log.warning("using mocks instead of %s (%s: %s)", module_name, type(exc).__name__, exc)

app.include_router(mock_routes.router)
