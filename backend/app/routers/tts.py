from uuid import UUID
import base64

from fastapi import APIRouter, Depends, HTTPException, Query
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


@router.get("/articles/{article_id}/tts/plan")
def speech_plan(
    article_id: UUID,
    voice_id: str = Query(default="eve", max_length=64),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    article = _owned_article(db, user, article_id)
    script = tts_service.article_script(article)
    chunks = tts_service.split_chunks(script)
    digest = tts_service.script_digest(script, voice_id)
    sections = []
    for section in tts_service.body_sections(article):
        spoken = tts_service.speech_plain(section["markdown"])
        sections.append(
            {
                "id": section["id"],
                "title": section["title"],
                "chars": len(spoken),
            }
        )
    return {
        "enabled": tts_service.key_configured(),
        "chars": len(script),
        "chunks": len(chunks),
        "long": len(script) > tts_service.LONG_SCRIPT_CHARS,
        "content_hash": digest,
        "cached_chunks": tts_service.cached_chunk_count(article.id, digest, voice_id),
        "sections": sections,
        "source_kind": getattr(article, "source_kind", None) or "rss",
    }


@router.post("/articles/{article_id}/tts/release")
def release_speech_audio(
    article_id: UUID,
    voice_id: str = Query(default="eve", max_length=64),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    article = _owned_article(db, user, article_id)
    dropped = tts_service.release_article_audio(article.id, voice_id)
    return {"ok": True, "dropped": dropped}


@router.get("/articles/{article_id}/tts")
def speak_article(
    article_id: UUID,
    voice_id: str = Query(default="eve", max_length=64),
    chunk: int = Query(default=0, ge=0, le=200),
    confirm: bool = Query(default=False),
    section: str | None = Query(default=None, max_length=16),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    article = _owned_article(db, user, article_id)
    script = tts_service.article_script(article, section_id=section)
    if len(script) > tts_service.LONG_SCRIPT_CHARS and not confirm and not section:
        raise HTTPException(
            status_code=412,
            detail="This text is longer than 20,000 characters. Confirm the full listen, or choose one chapter.",
        )
    chunks = tts_service.split_chunks(script)
    if not chunks:
        raise HTTPException(
            status_code=400,
            detail="This story has no stored text to read. Open it in the reader, then try Listen again.",
        )
    if chunk >= len(chunks):
        raise HTTPException(status_code=400, detail="That speech part does not exist.")
    digest = tts_service.script_digest(script, voice_id)
    offset = sum(tts_service.word_count(part) for part in chunks[:chunk])
    timed = tts_service.synthesize_timed(
        chunks[chunk],
        voice_id,
        article_id=article.id,
        chunk_index=chunk,
        digest=digest,
    )
    return {
        "chunk": chunk,
        "chunks": len(chunks),
        "word_offset": offset,
        "chunk_word_counts": [tts_service.word_count(part) for part in chunks],
        "duration": timed.get("duration"),
        "content_type": timed.get("content_type") or "audio/mpeg",
        "audio": base64.b64encode(timed["audio"]).decode("ascii"),
        "words": timed.get("words") or [],
        "content_hash": digest,
    }
