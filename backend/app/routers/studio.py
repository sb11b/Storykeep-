from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import GrokAutomation, GrokAutomationRun, GrokWorkspaceFile, User
from app.services import chat as chat_service
from app.services import studio as studio_service
from app.services.demo_lock import reject_locked

router = APIRouter(prefix="/studio", tags=["studio"])


class AutomationIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    instruction: str = Field(min_length=1, max_length=8000)
    trigger: str = "schedule"
    schedule: str = "daily"
    hour: int = 8
    minute: int = 0
    weekday: int = 0
    monthday: int = 1
    timezone: str = "America/New_York"
    notify: str = "none"
    email_from: str | None = None
    email_to: str | None = None
    email_subject: str | None = None
    enabled: bool = True
    include_unread: bool = False


class AutomationPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    instruction: str | None = Field(default=None, min_length=1, max_length=8000)
    trigger: str | None = None
    schedule: str | None = None
    hour: int | None = None
    minute: int | None = None
    weekday: int | None = None
    monthday: int | None = None
    timezone: str | None = None
    notify: str | None = None
    email_from: str | None = None
    email_to: str | None = None
    email_subject: str | None = None
    enabled: bool | None = None
    include_unread: bool | None = None


class FireEmailIn(BaseModel):
    from_addr: str = Field(default="", max_length=200)
    subject: str = Field(default="", max_length=200)
    body: str = Field(min_length=1, max_length=8000)


class FileIn(BaseModel):
    path: str = Field(min_length=1, max_length=180)
    content: str = Field(default="", max_length=studio_service.FILE_CAP)


class AgentIn(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    mode: str = "plan"


class ApplyIn(BaseModel):
    patches: list[FileIn]


def _automation_out(row: GrokAutomation) -> dict:
    return {
        "id": str(row.id),
        "title": row.title,
        "instruction": row.instruction,
        "trigger": row.trigger,
        "schedule": row.schedule,
        "hour": row.hour,
        "minute": row.minute,
        "weekday": row.weekday,
        "monthday": row.monthday,
        "timezone": row.timezone,
        "notify": row.notify,
        "email_from": row.email_from,
        "email_to": row.email_to,
        "email_subject": row.email_subject,
        "enabled": row.enabled,
        "include_unread": row.include_unread,
        "next_run_at": row.next_run_at.isoformat() if row.next_run_at else None,
        "last_run_at": row.last_run_at.isoformat() if row.last_run_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _run_out(row: GrokAutomationRun) -> dict:
    return {
        "id": str(row.id),
        "automation_id": str(row.automation_id),
        "status": row.status,
        "trigger": row.trigger,
        "email_context": row.email_context,
        "output": row.output,
        "error": row.error,
        "model": row.model,
        "reasoning": row.reasoning,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _file_out(row: GrokWorkspaceFile) -> dict:
    return {
        "id": str(row.id),
        "path": row.path,
        "content": row.content,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _apply_schedule(row: GrokAutomation) -> None:
    if row.trigger not in studio_service.TRIGGERS:
        raise HTTPException(status_code=400, detail="Trigger must be schedule or email.")
    if row.schedule not in studio_service.SCHEDULES:
        raise HTTPException(status_code=400, detail="Unknown schedule.")
    if row.notify not in studio_service.NOTIFIES:
        raise HTTPException(status_code=400, detail="Unknown notify option.")
    row.hour = min(23, max(0, int(row.hour)))
    row.minute = min(59, max(0, int(row.minute)))
    row.next_run_at = studio_service.next_run_at(
        trigger=row.trigger,
        schedule=row.schedule,
        hour=row.hour,
        minute=row.minute,
        weekday=row.weekday,
        monthday=row.monthday,
        tz_name=row.timezone,
    )


@router.get("/templates")
def list_templates(user: User = Depends(get_current_user)) -> dict:
    reject_locked(user)
    return {"items": studio_service.TEMPLATES}


@router.get("/automations")
def list_automations(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    reject_locked(user)
    rows = db.scalars(
        select(GrokAutomation).where(GrokAutomation.user_id == user.id).order_by(GrokAutomation.updated_at.desc())
    ).all()
    return {"items": [_automation_out(row) for row in rows]}


@router.post("/automations")
def create_automation(
    payload: AutomationIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    reject_locked(user)
    row = GrokAutomation(
        user_id=user.id,
        title=payload.title.strip(),
        instruction=payload.instruction.strip(),
        trigger=payload.trigger,
        schedule=payload.schedule,
        hour=payload.hour,
        minute=payload.minute,
        weekday=payload.weekday,
        monthday=payload.monthday,
        timezone=payload.timezone.strip() or "America/New_York",
        notify=payload.notify,
        email_from=(payload.email_from or "").strip() or None,
        email_to=(payload.email_to or "").strip() or None,
        email_subject=(payload.email_subject or "").strip() or None,
        enabled=payload.enabled,
        include_unread=payload.include_unread,
    )
    _apply_schedule(row)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _automation_out(row)


@router.patch("/automations/{automation_id}")
def patch_automation(
    automation_id: UUID,
    payload: AutomationPatch,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    reject_locked(user)
    row = studio_service.owned_automation(db, user, automation_id)
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        if isinstance(value, str):
            value = value.strip() or None if key.startswith("email_") else value.strip()
        setattr(row, key, value)
    row.updated_at = datetime.now(timezone.utc)
    _apply_schedule(row)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _automation_out(row)


@router.delete("/automations/{automation_id}")
def delete_automation(
    automation_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    reject_locked(user)
    row = studio_service.owned_automation(db, user, automation_id)
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.get("/automations/{automation_id}/runs")
def list_runs(
    automation_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    reject_locked(user)
    studio_service.owned_automation(db, user, automation_id)
    rows = db.scalars(
        select(GrokAutomationRun)
        .where(GrokAutomationRun.automation_id == automation_id)
        .order_by(GrokAutomationRun.created_at.desc())
        .limit(40)
    ).all()
    return {"items": [_run_out(row) for row in rows]}


@router.post("/automations/{automation_id}/run")
def run_now(
    automation_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    reject_locked(user)
    row = studio_service.owned_automation(db, user, automation_id)
    run = studio_service.execute_automation(db, row, trigger="manual")
    return {"automation": _automation_out(row), "run": _run_out(run)}


@router.post("/automations/{automation_id}/email")
def fire_email(
    automation_id: UUID,
    payload: FireEmailIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    reject_locked(user)
    row = studio_service.owned_automation(db, user, automation_id)
    if row.trigger != "email":
        raise HTTPException(status_code=400, detail="This automation is not an email trigger.")
    blob = f"From: {payload.from_addr}\nTo: {row.email_to or user.email}\nSubject: {payload.subject}\n\n{payload.body}"
    run = studio_service.execute_automation(db, row, trigger="email", email_context=blob)
    return {"automation": _automation_out(row), "run": _run_out(run)}


@router.get("/workspace")
def list_workspace(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    reject_locked(user)
    rows = studio_service.seed_workspace(db, user)
    rows = sorted(rows, key=lambda item: item.path)
    return {"items": [_file_out(row) for row in rows]}


@router.put("/workspace")
def put_file(
    payload: FileIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    reject_locked(user)
    path = studio_service.sanitize_path(payload.path)
    studio_service.seed_workspace(db, user)
    count = len(db.scalars(select(GrokWorkspaceFile).where(GrokWorkspaceFile.user_id == user.id)).all())
    row = db.scalars(
        select(GrokWorkspaceFile).where(GrokWorkspaceFile.user_id == user.id, GrokWorkspaceFile.path == path)
    ).first()
    if row is None:
        if count >= studio_service.FILE_COUNT_CAP:
            raise HTTPException(status_code=400, detail="This workspace already has 40 files.")
        row = GrokWorkspaceFile(user_id=user.id, path=path, content=payload.content)
    else:
        row.content = payload.content
        row.updated_at = datetime.now(timezone.utc)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _file_out(row)


@router.delete("/workspace")
def delete_file(
    path: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    reject_locked(user)
    cleaned = studio_service.sanitize_path(path)
    row = db.scalars(
        select(GrokWorkspaceFile).where(GrokWorkspaceFile.user_id == user.id, GrokWorkspaceFile.path == cleaned)
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="File not found.")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.post("/workspace/apply")
def apply_patches(
    payload: ApplyIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    reject_locked(user)
    studio_service.seed_workspace(db, user)
    written: list[dict] = []
    for patch in payload.patches:
        path = studio_service.sanitize_path(patch.path)
        row = db.scalars(
            select(GrokWorkspaceFile).where(GrokWorkspaceFile.user_id == user.id, GrokWorkspaceFile.path == path)
        ).first()
        if row is None:
            count = len(db.scalars(select(GrokWorkspaceFile).where(GrokWorkspaceFile.user_id == user.id)).all())
            if count >= studio_service.FILE_COUNT_CAP:
                break
            row = GrokWorkspaceFile(user_id=user.id, path=path, content=patch.content)
        else:
            row.content = patch.content
            row.updated_at = datetime.now(timezone.utc)
        db.add(row)
        db.flush()
        written.append(_file_out(row))
    db.commit()
    return {"items": written}


@router.post("/agent")
def agent_turn(
    payload: AgentIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    reject_locked(user)
    chat_service.enforce_rate_limit(user.id)
    mode = (payload.mode or "plan").strip().lower()
    if mode not in {"plan", "build"}:
        raise HTTPException(status_code=400, detail="Mode must be plan or build.")
    files = studio_service.seed_workspace(db, user)
    listing = "\n\n".join(f"## {item.path}\n```\n{item.content[:6000]}\n```" for item in sorted(files, key=lambda row: row.path))
    system = studio_service.PLAN_SYSTEM if mode == "plan" else studio_service.BUILD_SYSTEM
    result = chat_service.complete_once(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": f"Workspace:\n{listing}\n\nTask:\n{payload.message.strip()}"},
        ],
        reasoning_effort="low" if mode == "plan" else "high",
        max_tokens=1600,
    )
    text = result["text"]
    return {
        "text": text,
        "model": result["model"],
        "reasoning": result["reasoning"],
        "mode": mode,
        "plan": studio_service.parse_plan(text) if mode == "plan" else [],
        "patches": studio_service.parse_patches(text) if mode == "build" else [],
    }
