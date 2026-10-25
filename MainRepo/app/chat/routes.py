"""POST /api/chat: the only way the frontend reaches the chatbot."""
from fastapi import APIRouter, HTTPException

from app.chat.service import chat

router = APIRouter()


@router.post("/api/chat")
def post_chat(req: dict):
    try:
        return chat(req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
