from uuid import UUID
import base64

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Article, User
from app.routers.articles import _owned_article
from app.schemas import ChatSpeechIn, VisibleSpeechIn
from app.services import tts as tts_service
from app.services.demo_lock import reject_locked

router = APIRouter(tags=["tts"])


def _extra_note_scripts(db: Session, article: Article) -> list[tuple[str, str]]:
    """Child overlay notes only. Does not merge into or rewrite the source article."""
    if tts_service.is_composed_note(article):
        return []
    children = db.scalars(
        select(Article).where(Article.parent_id == article.id).order_by(Article.created_at.asc())
    ).all()
    rows: list[tuple[str, str]] = []
    seen: set[str] = set()
    for child in children:
        markdown = tts_service.note_source_markdown(child)
        if not markdown or markdown in seen:
            continue
        seen.add(markdown)
        rows.append((child.title or "Note", markdown))
    if rows:
        return rows
    for addition in getattr(article, "overlay_additions", None) or []:
        markdown = (addition.markdown or "").strip()
        if not markdown or markdown in seen:
            continue
        seen.add(markdown)
        rows.append((addition.title or "Note", markdown))
    return rows


def _speech_script(
    db: Session,
    article: Article,
    *,
    include_notes: bool,
    section: str | None = None,
    visible_text: str | None = None,
    notes_text: str | None = None,
) -> str:
    if visible_text is not None:
        return tts_service.visible_speech_script(
            visible_text,
            include_notes=include_notes,
            notes_text=notes_text,
        )
    extras = _extra_note_scripts(db, article) if include_notes else []
    return tts_service.article_script(article, section_id=section, include_notes=include_notes, extra_notes=extras)


def _speech_response_for_script(
    script: str,
    voice_id: str,
    chunk: int,
    *,
    confirm: bool,
    cache_owner_id: str | UUID,
) -> dict:
    if len(script) > tts_service.LONG_SCRIPT_CHARS and not confirm:
        raise HTTPException(
            status_code=412,
            detail="This text is longer than 20,000 characters. Confirm to listen to the full note.",
        )
    chunks = tts_service.split_chunks(script)
    if not chunks:
        raise HTTPException(status_code=400, detail="There is no text to read aloud.")
    if chunk >= len(chunks):
        raise HTTPException(status_code=400, detail="That speech part does not exist.")
    digest = tts_service.script_digest(script, voice_id)
    offset = sum(tts_service.word_count(part) for part in chunks[:chunk])
    timed = tts_service.synthesize_timed(
        chunks[chunk],
        voice_id,
        article_id=cache_owner_id,
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
        "tts_word_count": tts_service.word_count(script),
    }


def _speech_response(
    article: Article,
    script: str,
    voice_id: str,
    chunk: int,
    *,
    confirm: bool,
) -> dict:
    detail = (
        "This note has no stored text to read."
        if tts_service.is_composed_note(article)
        else "This story has no stored text to read. Open it in the reader, then try Listen again."
    )
    if not script.strip():
        raise HTTPException(status_code=400, detail=detail)
    try:
        return _speech_response_for_script(
            script,
            voice_id,
            chunk,
            confirm=confirm,
            cache_owner_id=article.id,
        )
    except HTTPException as exc:
        if exc.status_code == 400 and exc.detail == "There is no text to read aloud.":
            raise HTTPException(status_code=400, detail=detail) from exc
        raise


def _speech_plan_payload(
    db: Session,
    article: Article,
    script: str,
    voice_id: str,
    *,
    include_notes: bool,
    visible_mode: bool,
) -> dict:
    chunks = tts_service.split_chunks(script)
    digest = tts_service.script_digest(script, voice_id)
    sections = []
    if not visible_mode:
        section_starts = tts_service.section_start_words(article)
        for section in tts_service.body_sections(article):
            spoken = tts_service.speech_plain(section["markdown"])
            sections.append(
                {
                    "id": section["id"],
                    "title": section["title"],
                    "chars": len(spoken),
                    "word_offset": section_starts.get(section["id"], 0),
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
        "include_notes": bool(include_notes),
        "note_count": len(_extra_note_scripts(db, article)) if include_notes else 0,
        "tts_word_count": tts_service.word_count(script),
    }


@router.get("/tts")
def tts_status(user: User = Depends(get_current_user)) -> dict:
    reject_locked(user)
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
    include_notes: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    reject_locked(user)
    article = _owned_article(db, user, article_id)
    script = _speech_script(db, article, include_notes=include_notes)
    return _speech_plan_payload(db, article, script, voice_id, include_notes=include_notes, visible_mode=False)


@router.post("/articles/{article_id}/tts/plan")
def speech_plan_visible(
    article_id: UUID,
    payload: VisibleSpeechIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    reject_locked(user)
    article = _owned_article(db, user, article_id)
    script = _speech_script(
        db,
        article,
        include_notes=payload.include_notes,
        visible_text=payload.visible_text,
        notes_text=payload.notes_text,
    )
    if not script.strip():
        raise HTTPException(status_code=400, detail="There is no visible text to read in the article body.")
    return _speech_plan_payload(
        db,
        article,
        script,
        payload.voice_id,
        include_notes=payload.include_notes,
        visible_mode=True,
    )


@router.post("/articles/{article_id}/tts/release")
def release_speech_audio(
    article_id: UUID,
    voice_id: str = Query(default="eve", max_length=64),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    reject_locked(user)
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
    include_notes: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    reject_locked(user)
    article = _owned_article(db, user, article_id)
    _ = section  # deprecated seek hint; full body is always synthesized
    script = _speech_script(db, article, include_notes=include_notes)
    payload = _speech_response(article, script, voice_id, chunk, confirm=confirm)
    payload["include_notes"] = bool(include_notes)
    return payload


@router.post("/tts/message")
def speak_chat_message(
    payload: ChatSpeechIn,
    chunk: int = Query(default=0, ge=0, le=200),
    confirm: bool = Query(default=False),
    user: User = Depends(get_current_user),
) -> dict:
    reject_locked(user)
    script = tts_service.visible_speech_script(payload.visible_text)
    if not script.strip():
        raise HTTPException(status_code=400, detail="There is no visible reply text to read.")
    cache_owner = f"chat-{user.id}-{payload.message_id}"
    response = _speech_response_for_script(
        script,
        payload.voice_id,
        chunk,
        confirm=confirm,
        cache_owner_id=cache_owner,
    )
    response["message_id"] = payload.message_id
    return response


@router.post("/articles/{article_id}/tts")
def speak_article_visible(
    article_id: UUID,
    payload: VisibleSpeechIn,
    chunk: int = Query(default=0, ge=0, le=200),
    confirm: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    reject_locked(user)
    article = _owned_article(db, user, article_id)
    script = _speech_script(
        db,
        article,
        include_notes=payload.include_notes,
        visible_text=payload.visible_text,
        notes_text=payload.notes_text,
    )
    if not script.strip():
        raise HTTPException(status_code=400, detail="There is no visible text to read in the article body.")
    response = _speech_response(article, script, payload.voice_id, chunk, confirm=confirm)
    response["include_notes"] = bool(payload.include_notes)
    return response
