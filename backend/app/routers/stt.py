from __future__ import annotations

import asyncio
import json
import logging
import time
from urllib.parse import urlencode

import websockets
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect, status
from sqlalchemy.orm import Session

from app.auth import decode_access_token
from app.config import settings
from app.database import get_db
from app.deps import get_current_user, require_user
from app.models import User
from app.services.demo_lock import is_locked, reject_authentication
from app.services.stt_clip import key_configured, transcribe_clip
from app.services.stt_limits import enforce_stt_rate_limit

logger = logging.getLogger(__name__)

router = APIRouter(tags=["stt"])

XAI_STT_WS = "wss://api.x.ai/v1/stt"
IDLE_SECONDS = 15.0
CONTINUOUS_IDLE_SECONDS = 20.0
MAX_CLIP_SECONDS = 120.0
CONTINUOUS_MAX_SECONDS = 30 * 60.0

_stream_lock = asyncio.Lock()
_active_streams: set[str] = set()


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
    user: User = Depends(require_user),
) -> dict[str, str]:
    payload = await file.read()
    return transcribe_clip(
        user,
        payload,
        content_type=file.content_type,
        filename=file.filename,
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
    if is_locked(user):
        await websocket.send_json({"type": "error", "message": "Demo account closed"})
        await websocket.close(code=4403)
        return
    try:
        enforce_stt_rate_limit(user.id)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else "Dictation limit reached."
        await websocket.send_json({"type": "error", "message": detail})
        await websocket.close(code=4429)
        return
    key = (settings.xai_api_key or "").strip()
    if not key:
        await websocket.send_json({"type": "error", "message": "Dictation is off until XAI_API_KEY is set on the server."})
        await websocket.close(code=4503)
        return

    user_key = str(user.id)
    async with _stream_lock:
        if user_key in _active_streams:
            await websocket.send_json({"type": "error", "message": "Dictation is already running in another tab."})
            await websocket.close(code=4409)
            return
        _active_streams.add(user_key)

    continuous = (websocket.query_params.get("continuous") or "").lower() in {"1", "true", "yes"}
    idle_limit = CONTINUOUS_IDLE_SECONDS if continuous else IDLE_SECONDS
    max_age = CONTINUOUS_MAX_SECONDS if continuous else MAX_CLIP_SECONDS
    query = urlencode(
        {
            "sample_rate": "16000",
            "encoding": "pcm",
            "interim_results": "true",
            "language": "en",
            "endpointing": "800",
        }
    )
    started = time.monotonic()
    last_audio = time.monotonic()
    xai = None
    try:
        xai = await websockets.connect(
            f"{XAI_STT_WS}?{query}",
            additional_headers={"Authorization": f"Bearer {key}"},
            max_size=2_000_000,
            open_timeout=20,
        )
        ready = False
        while not ready:
            raw = await asyncio.wait_for(xai.recv(), timeout=20)
            if isinstance(raw, bytes):
                continue
            msg = json.loads(raw)
            if msg.get("type") == "transcript.created":
                ready = True
            elif msg.get("type") == "error":
                await websocket.send_json({"type": "error", "message": msg.get("message") or "STT failed"})
                return
        await websocket.send_json({"type": "ready", "continuous": continuous})

        async def from_browser() -> None:
            nonlocal last_audio
            while True:
                message = await websocket.receive()
                if message.get("type") == "websocket.disconnect":
                    break
                data = message.get("bytes")
                if data:
                    last_audio = time.monotonic()
                    await xai.send(data)
                    continue
                text = message.get("text")
                if not text:
                    continue
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError:
                    continue
                kind = (payload.get("type") or "").lower()
                if kind == "ping":
                    last_audio = time.monotonic()
                    continue
                if kind in {"stop", "audio.done"}:
                    await xai.send(json.dumps({"type": "audio.done"}))
                    return
                if kind == "finalize":
                    await xai.send(json.dumps({"type": "finalize"}))

        async def from_xai() -> None:
            async for raw in xai:
                if isinstance(raw, bytes):
                    continue
                msg = json.loads(raw)
                kind = msg.get("type")
                if kind == "transcript.partial":
                    await websocket.send_json(
                        {
                            "type": "partial",
                            "text": msg.get("text") or "",
                            "is_final": bool(msg.get("is_final")),
                            "speech_final": bool(msg.get("speech_final")),
                        }
                    )
                elif kind == "transcript.done":
                    await websocket.send_json({"type": "done", "text": msg.get("text") or ""})
                    if not continuous:
                        return
                    last_audio = time.monotonic()
                elif kind == "error":
                    await websocket.send_json({"type": "error", "message": msg.get("message") or "STT failed"})
                    return

        async def watchdog() -> None:
            while True:
                await asyncio.sleep(1)
                now = time.monotonic()
                if now - started > max_age:
                    await websocket.send_json({"type": "timeout", "message": "STT timeout"})
                    try:
                        await xai.send(json.dumps({"type": "audio.done"}))
                    except Exception:
                        pass
                    return
                if now - last_audio > idle_limit:
                    idle_message = "Mic idle, tap to resume" if continuous else "Stopped after silence."
                    await websocket.send_json({"type": "idle", "message": idle_message})
                    try:
                        await xai.send(json.dumps({"type": "audio.done"}))
                    except Exception:
                        pass
                    return

        browser_task = asyncio.create_task(from_browser())
        xai_task = asyncio.create_task(from_xai())
        watchdog_task = asyncio.create_task(watchdog())
        done, pending = await asyncio.wait(
            {browser_task, xai_task, watchdog_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if browser_task in done and not xai_task.done():
            xai_task.cancel()
        for task in (browser_task, xai_task, watchdog_task):
            if not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("STT proxy failed")
        try:
            await websocket.send_json({"type": "error", "message": "Could not reach xAI speech-to-text."})
        except Exception:
            pass
    finally:
        async with _stream_lock:
            _active_streams.discard(user_key)
        if xai is not None:
            try:
                await xai.close()
            except Exception:
                pass
        try:
            await websocket.close()
        except Exception:
            pass
