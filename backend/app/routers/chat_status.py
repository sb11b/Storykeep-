from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import require_user
from app.models import User
from app.services import chat as chat_service
from app.services import grok_conversations as grok_store
from app.services import message_crypto
from app.services import web_search as search_tool
from app.services.demo_lock import is_locked

router = APIRouter(tags=["chat"])


class SearchIn(BaseModel):
    query: str = Field(min_length=1, max_length=search_tool.QUERY_CHAR_CAP)


@router.post("/search")
def junior_web_search(payload: SearchIn, user: User = Depends(require_user)) -> dict:
    search_tool.reject_demo(user)
    outcome = search_tool.search(payload.query)
    if outcome.fatal:
        raise HTTPException(status_code=outcome.status_code or 503, detail=outcome.detail)
    return outcome.as_payload()


@router.get("/chat")
def chat_status(
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
    locked = is_locked(user)
    models = chat_service.available_models()
    return {
        "enabled": chat_service.key_configured() and not locked,
        "locked": locked,
        "provider": "xai",
        "model": chat_service.default_full_model(),
        "models": models,
        "default_model": chat_service.default_full_model(),
        "fast_model": chat_service.default_fast_model(),
        "reasoning_efforts": list(chat_service.REASONING_EFFORTS),
        "requests_per_hour": int(settings.chat_requests_per_hour or 120),
        "imagine_requests_per_hour": int(settings.imagine_requests_per_hour or 10),
        "persist": grok_store.should_persist(user),
        "key_configured": chat_service.key_configured(),
        "key_format_ok": chat_service.key_format_ok(),
        "message_crypto": message_crypto.status(db, user),
    }


@router.get("/chat/health")
def chat_health(user: User = Depends(require_user)) -> dict:
    """Ping xAI with a 1-token request. Auth required; does not consume chat quota."""
    if not chat_service.key_configured():
        return {
            "ok": False,
            "model": chat_service.default_full_model(),
            "reasoning": chat_service.DEFAULT_REASONING_EFFORT,
            "ttft_ms": None,
            "xai_status": None,
            "message": "XAI_API_KEY is not set or must start with xai-.",
        }
    return chat_service.ping_xai()
