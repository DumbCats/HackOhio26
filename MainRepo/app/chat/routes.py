"""POST /api/chat: the only way the frontend reaches the chatbot."""
from fastapi import APIRouter, HTTPException

from app import audit
from app.chat.service import chat

router = APIRouter()


@router.post("/api/chat")
def post_chat(req: dict):
    try:
        out = chat(req)
    except ValueError as exc:
        audit.write({"endpoint": "/api/chat", "status": 400, "error": str(exc)})
        raise HTTPException(status_code=404 if str(exc) == "unknown home" else 400, detail=str(exc))
    # N11: no chat text, no needs
    audit.write({"endpoint": "/api/chat", "status": 200, "source": out.get("source"), "tools_used": out.get("tools_used"),
                 "safety_flag": out.get("safety_flag"), "params": {"t": req.get("t"), "low_power": req.get("low_power")}})
    return out
