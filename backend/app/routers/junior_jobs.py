from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import JuniorJob, User
from app.routers.articles import _owned_article
from app.schemas import GrokMessageOut
from app.services import grok_conversations as grok_store
from app.services import junior_jobs as jobs
from app.services.demo_lock import reject_locked
from app.services.destination import normalize_destination
from app.services.folders import resolve_folder_id

router = APIRouter(prefix="/junior/jobs", tags=["junior-jobs"])


class JobIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    prompt: str = Field(min_length=1, max_length=8000)
    cron: str = jobs.DEFAULT_CRON
    timezone: str = jobs.DEFAULT_TZ
    conversation_id: UUID | None = None
    shelf: str | None = None
    folder_id: UUID | None = None
    include_article_id: UUID | None = None
    model: str = "grok-4.6"
    reasoning: str = "low"
    xhigh: bool = False
    web_search: bool = False
    enabled: bool = True


class JobPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    prompt: str | None = Field(default=None, min_length=1, max_length=8000)
    cron: str | None = None
    timezone: str | None = None
    conversation_id: UUID | None = None
    shelf: str | None = None
    folder_id: UUID | None = None
    include_article_id: UUID | None = None
    model: str | None = None
    reasoning: str | None = None
    xhigh: bool | None = None
    web_search: bool | None = None
    enabled: bool | None = None


def _job_out(row: JuniorJob) -> dict:
    return {
        "id": str(row.id),
        "title": row.title,
        "prompt": row.prompt,
        "cron": row.cron,
        "timezone": row.timezone,
        "conversation_id": str(row.conversation_id) if row.conversation_id else None,
        "shelf": row.shelf,
        "folder_id": str(row.folder_id) if row.folder_id else None,
        "include_article_id": str(row.include_article_id) if row.include_article_id else None,
        "model": row.model,
        "reasoning": row.reasoning,
        "xhigh": bool(row.xhigh),
        "web_search": bool(getattr(row, "web_search", False)),
        "enabled": bool(row.enabled),
        "last_run_at": row.last_run_at.isoformat() if row.last_run_at else None,
        "last_status": row.last_status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _bind_optional(db: Session, user: User, row: JuniorJob) -> None:
    if row.conversation_id:
        grok_store.owned_conversation(db, user, row.conversation_id)
    if row.include_article_id:
        _owned_article(db, user, row.include_article_id)
    if row.shelf:
        try:
            dest = normalize_destination(row.shelf, user)
            row.shelf = dest
            row.folder_id = resolve_folder_id(db, user, dest, row.folder_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    else:
        row.folder_id = None


def _apply_fields(db: Session, user: User, row: JuniorJob, data: dict) -> None:
    if "cron" in data and data["cron"] is not None:
        jobs.parse_cron(str(data["cron"]))
        row.cron = " ".join(str(data["cron"]).split())
    if "timezone" in data and data["timezone"] is not None:
        zone = jobs.resolve_zone(str(data["timezone"]))
        row.timezone = getattr(zone, "key", None) or str(data["timezone"]).strip() or jobs.DEFAULT_TZ
    skip = {"cron", "timezone"}
    for key, value in data.items():
        if key in skip:
            continue
        if isinstance(value, str) and key in {"title", "prompt", "model", "reasoning", "shelf"}:
            value = value.strip() or None
        setattr(row, key, value)
    if row.model:
        from app.services import chat as chat_service

        row.model = chat_service.rewrite_xai_model(row.model)
    _bind_optional(db, user, row)
    row.updated_at = datetime.now(timezone.utc)


@router.get("")
def list_jobs(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    reject_locked(user)
    rows = db.scalars(select(JuniorJob).where(JuniorJob.user_id == user.id).order_by(JuniorJob.updated_at.desc())).all()
    return {"items": [_job_out(row) for row in rows]}


@router.post("")
def create_job(payload: JobIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    reject_locked(user)
    jobs.parse_cron(payload.cron)
    row = JuniorJob(
        user_id=user.id,
        title=payload.title.strip(),
        prompt=payload.prompt.strip(),
        cron=" ".join(payload.cron.split()),
        timezone=getattr(jobs.resolve_zone(payload.timezone), "key", None) or payload.timezone.strip() or jobs.DEFAULT_TZ,
        conversation_id=payload.conversation_id,
        include_article_id=payload.include_article_id,
        shelf=(payload.shelf or "").strip() or None,
        folder_id=payload.folder_id,
        model=payload.model.strip() or "grok-4.6",
        reasoning=(payload.reasoning or "low").strip() or "low",
        xhigh=payload.xhigh,
        web_search=payload.web_search,
        enabled=payload.enabled,
    )
    _bind_optional(db, user, row)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _job_out(row)


@router.patch("/{job_id}")
def patch_job(
    job_id: UUID,
    payload: JobPatch,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    reject_locked(user)
    row = jobs.owned_job(db, user, job_id)
    data = payload.model_dump(exclude_unset=True)
    _apply_fields(db, user, row, data)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _job_out(row)


@router.delete("/{job_id}")
def delete_job(job_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    reject_locked(user)
    row = jobs.owned_job(db, user, job_id)
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.post("/run")
def cron_run_due(request: Request, db: Session = Depends(get_db)) -> dict:
    jobs.require_cron_secret(request)
    jobs.run_due_jobs()
    return {"ok": True}


@router.post("/{job_id}/run")
def run_now(job_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    reject_locked(user)
    row = jobs.owned_job(db, user, job_id)
    result = jobs.execute_job(db, row, trigger="manual")
    assistant = result["assistant_message"]
    return {
        "job": _job_out(result["job"]),
        "conversation_id": str(result["conversation_id"]),
        "status": result["status"],
        "assistant_message": GrokMessageOut.model_validate(assistant).model_dump(mode="json"),
    }
