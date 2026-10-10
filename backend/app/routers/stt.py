from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, WebSocket, status
from sqlalchemy.orm import Session

from app.auth import decode_access_token
from app.config import settings
from app.database import get_db
from app.deps import get_current_user, require_user
from app.models import User
from app.services.demo_lock import is_locked, reject_authentication
from app.services.stt_clip import key_configured, transcribe_clip
from app.services.stt_stream import run_stt_session

router = APIRouter(tags=["stt"])


def _user_from_socket(websocket: WebSocket, db: Session) -> User:
    token = websocket.cookies.get("sk_access")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    user = db.get(User, decode_access_token(token))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    reject_authentication(user)
    return user


@router.get("/stt")
def stt_status(user: User = Depends(require_user)) -> dict:
    locked = is_locked(user)
    return {
        "enabled": key_configured() and not locked,
        "locked": locked,
        "provider": "xai",
        "mode": "clip",
        "price": "$0.20/hr",
        "sessions_per_hour": int(settings.stt_sessions_per_hour or 60),
    }


@router.post("/stt")
async def stt_clip(
    file: UploadFile = File(...),
    model: str | None = Form(default=None),
    user: User = Depends(require_user),
) -> dict:
    payload = await file.read()
    return transcribe_clip(
        user,
        payload,
        content_type=file.content_type,
        filename=file.filename,
        model=model,
    )


@router.websocket("/stt")
async def stt_stream(websocket: WebSocket, db: Session = Depends(get_db)) -> None:
    await websocket.accept()
    try:
        user = _user_from_socket(websocket, db)
    except HTTPException as exc:
        await websocket.send_json({"type": "error", "message": exc.detail})
        await websocket.close(code=4401)
        return
    key = (settings.xai_api_key or "").strip()
    await run_stt_session(websocket, user, key)
