"""POST /api/chat: the only way the frontend reaches the chatbot."""
from fastapi import APIRouter, HTTPException

from app import audit
from app.chat.service import chat

router = APIRouter()
SAFE_ERRORS = ("bad ", "messages required", "message too long", "too many messages", "last message",
               "request must", "unknown home")


@router.post("/api/chat")
def post_chat(req: dict):
    try:
        out = chat(req)
    except (TypeError, KeyError, AttributeError):
        audit.write({"endpoint": "/api/chat", "status": 400, "error": "bad request"})
        raise HTTPException(status_code=400, detail="bad request")
    except ValueError as exc:
        msg = str(exc)
        if not msg.startswith(SAFE_ERRORS):  # never echo internal error text
            msg = "bad request"
        audit.write({"endpoint": "/api/chat", "status": 400, "error": msg})
        raise HTTPException(status_code=404 if msg == "unknown home" else 400, detail=msg)
    # N11: no chat text, no needs
    audit.write({"endpoint": "/api/chat", "status": 200, "source": out.get("source"), "tools_used": out.get("tools_used"),
                 "safety_flag": out.get("safety_flag"), "params": {"t": req.get("t"), "low_power": req.get("low_power")}})
    return out
