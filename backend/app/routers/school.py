from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_user
from app.models import User
from app.routers.articles import _owned_article
from app.routers.chat import _message_out
from app.schemas import ArticleOut
from app.presenters import article_out
from app.services import chat_docx
from app.services import grok_conversations as grok_store
from app.services import school_tools
from app.services.vault_import import create_composed_note

router = APIRouter(tags=["school"])


class SchoolSourceIn(BaseModel):
    message_id: UUID | None = None
    article_id: UUID | None = None
    conversation_id: UUID | None = None
    persist: bool = True

    @model_validator(mode="after")
    def require_source(self) -> "SchoolSourceIn":
        if not self.message_id and not self.article_id:
            raise ValueError("Pick a Junior reply or an open article/note.")
        return self


class TrimIn(SchoolSourceIn):
    target: int = Field(default=500)


class QuizSaveIn(BaseModel):
    questions_md: str = Field(min_length=1, max_length=20_000)
    key_md: str = Field(min_length=1, max_length=20_000)
    article_id: UUID | None = None
    destination: str | None = "schoolwork"
    folder_id: UUID | None = None


def _source_text(db: Session, user: User, payload: SchoolSourceIn) -> str:
    if payload.message_id:
        row = grok_store.owned_assistant_message(db, user, payload.message_id)
        text = (row.content or "").strip()
        if not text:
            raise HTTPException(status_code=400, detail="That reply has no text.")
        return text[: school_tools.SOURCE_CHAR_CAP]
    article = _owned_article(db, user, payload.article_id)
    text = school_tools.source_from_article(article)
    if not text.strip():
        raise HTTPException(status_code=400, detail="That article has no text.")
    return text


def _maybe_persist(db: Session, user: User, payload: SchoolSourceIn, markdown: str):
    if not payload.persist:
        return None
    conversation_id = payload.conversation_id
    if not conversation_id and payload.message_id:
        row = grok_store.owned_assistant_message(db, user, payload.message_id)
        conversation_id = row.conversation_id
    return school_tools.persist_assistant(db, user, conversation_id=conversation_id, content=markdown)


def _out(result: dict, assistant=None) -> dict:
    payload = dict(result)
    if assistant is not None:
        payload["assistant_message"] = _message_out(assistant)
    return payload


@router.post("/school/quiz")
def school_quiz(
    payload: SchoolSourceIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
    source = _source_text(db, user, payload)
    result = school_tools.run_quiz(source)
    assistant = _maybe_persist(db, user, payload, result["questions_md"])
    return _out(result, assistant)


@router.post("/school/apa")
def school_apa(
    payload: SchoolSourceIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
    source = _source_text(db, user, payload)
    result = school_tools.run_apa(source)
    assistant = _maybe_persist(db, user, payload, result["markdown"])
    return _out(result, assistant)


@router.post("/school/trim")
def school_trim(
    payload: TrimIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
    source = _source_text(db, user, payload)
    result = school_tools.run_trim(source, payload.target)
    assistant = _maybe_persist(db, user, payload, result["markdown"])
    return _out(result, assistant)


@router.post("/school/grammar")
def school_grammar(
    payload: SchoolSourceIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
    source = _source_text(db, user, payload)
    result = school_tools.run_grammar(source)
    assistant = _maybe_persist(db, user, payload, result["markdown"])
    return _out(result, assistant)


@router.post("/school/quiz/save")
def school_quiz_save(
    payload: QuizSaveIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> ArticleOut:
    parent_id = None
    dest = payload.destination or "schoolwork"
    folder_id = payload.folder_id
    if payload.article_id:
        parent = _owned_article(db, user, payload.article_id)
        parent_id = parent.id
        dest = payload.destination or getattr(parent, "destination", None) or "schoolwork"
        if folder_id is None:
            folder_id = getattr(parent, "folder_id", None)
    markdown = school_tools.quiz_note_markdown(payload.questions_md, payload.key_md)
    try:
        article = create_composed_note(
            db,
            user,
            "Quiz",
            markdown,
            tags=["quiz"],
            destination=dest,
            folder_id=folder_id,
            parent_id=parent_id,
            is_correction=False,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return article_out(article)


@router.post("/school/docx")
def school_docx(
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    clean: bool = Query(default=True),
) -> Response:
    del db
    markdown = str((payload or {}).get("markdown") or "").strip()
    if not markdown:
        raise HTTPException(status_code=400, detail="Nothing to put in Word.")
    if clean:
        markdown = school_tools.strip_marks(markdown)
    try:
        body = chat_docx.build_message_docx(markdown)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    filename = chat_docx.docx_filename(markdown).replace('"', "")
    return Response(
        content=body,
        media_type=chat_docx.DOCX_MEDIA_TYPE,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
