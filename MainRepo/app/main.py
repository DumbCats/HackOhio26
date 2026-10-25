"""FastAPI app: real lane routers first (if they import cleanly), mock router last.

Run from the repo root: uvicorn app.main:app --reload --port 8000
If frontend/dist exists (cd frontend && npm run build), the app is also served at http://localhost:8000/.
"""
import importlib
import json
import logging
import threading

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from app import audit, config, mock_routes

log = logging.getLogger("uvicorn.error")


class _RedactQuery(logging.Filter):
    """A8/N11: access-log lines never carry query strings (declared needs, tap coordinates)."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3 and isinstance(args[2], str) and "?" in args[2]:
            record.args = args[:2] + (args[2].split("?", 1)[0] + "?[redacted]",) + args[3:]
        return True


logging.getLogger("uvicorn.access").addFilter(_RedactQuery())

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
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|\[::1\]|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+)(:\d+)?",
    allow_methods=["*"],
    allow_headers=["*"],
)

REAL_ROUTERS: list[str] = []
for module_name in LANE_ROUTERS:
    try:
        app.include_router(importlib.import_module(module_name).router)
        REAL_ROUTERS.append(module_name)
        log.info("real routes mounted: %s", module_name)
    except Exception as exc:  # missing or broken lane code must never stop the mocks
        log.warning("using mocks instead of %s (%s: %s)", module_name, type(exc).__name__, exc)

app.include_router(mock_routes.router)


@app.middleware("http")
async def audit_log(request: Request, call_next):
    """N11: one line per API response. Chat adds its own line with tools used (app/chat/routes.py)."""
    response = await call_next(request)
    path = request.url.path
    if not path.startswith("/api/") or path == "/api/chat":
        return response
    body = b"".join([chunk async for chunk in response.body_iterator])
    source = None
    if response.headers.get("content-type", "").startswith("application/json") and len(body) < 2_000_000:
        try:
            source = json.loads(body).get("source")
        except (ValueError, AttributeError):
            pass
    audit.write({"endpoint": path, "params": audit.params(dict(request.query_params)),
                 "status": response.status_code, "source": source})
    return Response(content=body, status_code=response.status_code, headers=dict(response.headers),
                    media_type=response.media_type)


@app.get("/api/health")
def health():
    return {"ok": True, "real_routes": REAL_ROUTERS, "db": config.DB_PATH.exists(),
            "llm": bool(config.GEMINI_API_KEY)}


def _warm_up():
    """Build the feed, risk cache and demo homes in the background so the first click is fast."""
    try:
        from app.sim.scenario import get_scenario
        from app.sim.mapcells import get_outage_map
        get_scenario()
        get_outage_map(-18, config.DEFAULT_SEVERITY)
        log.info("warm-up done")
    except Exception as exc:
        log.warning("warm-up skipped (%s: %s)", type(exc).__name__, exc)


@app.on_event("startup")
def _startup():
    threading.Thread(target=_warm_up, daemon=True).start()


# Built frontend (single-command demo). API routes above take precedence.
DIST = config.REPO_ROOT / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            return Response(content='{"detail":"Not Found"}', status_code=404, media_type="application/json")
        f = DIST / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(DIST / "index.html")
