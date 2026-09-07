from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.routers.articles import _owned_article
from app.services import tts as tts_service

router = APIRouter(tags=["tts"])


@router.get("/tts")
def tts_status(user: User = Depends(get_current_user)) -> dict:
    _ = user
    return {
        "enabled": tts_service.key_configured(),
        "provider": "xai",
        "voices": tts_service.list_voices(),
    }


@router.get("/articles/{article_id}/tts")
def speak_article(
    article_id: UUID,
    voice_id: str = Query(default="eve", max_length=64),
    chunk: int = Query(default=0, ge=0, le=80),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    article = _owned_article(db, user, article_id)
    script = tts_service.article_script(article)
    chunks = tts_service.split_chunks(script)
    if not chunks:
        raise HTTPException(
            status_code=400,
            detail="This story has no stored text to read. Use Re-extract, then try Listen again.",
        )
    if chunk >= len(chunks):
        raise HTTPException(status_code=400, detail="That speech part does not exist.")
    audio = tts_service.synthesize(chunks[chunk], voice_id)
    headers = {
        "X-TTS-Chunk": str(chunk),
        "X-TTS-Chunks": str(len(chunks)),
        "Cache-Control": "no-store",
        "Access-Control-Expose-Headers": "X-TTS-Chunk, X-TTS-Chunks",
    }
    return Response(content=audio, media_type="audio/mpeg", headers=headers)
