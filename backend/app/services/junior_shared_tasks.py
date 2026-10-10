from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

from app.models import JuniorTask, User

LEASE_MINUTES = 10


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_task(db: Session, user: User, kind: str, title: str, detail: str | None, payload: dict) -> JuniorTask:
    row = JuniorTask(
        user_id=user.id,
        kind=kind,
        title=title,
        detail=detail or "",
        payload=payload or {},
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_tasks(
    db: Session, user: User, status_filter: str | None = None, limit: int = 50, before_id: uuid.UUID | None = None
) -> list[JuniorTask]:
    stmt = select(JuniorTask).where(JuniorTask.user_id == user.id)
    if status_filter:
        stmt = stmt.where(JuniorTask.status == status_filter)
    if before_id is not None:
        # Anchor MUST be user-scoped — db.get() fetches any user's row.
        anchor = db.scalars(
            select(JuniorTask).where(JuniorTask.id == before_id, JuniorTask.user_id == user.id)
        ).first()
        if anchor is not None:
            stmt = stmt.where(
                (JuniorTask.created_at < anchor.created_at)
                | ((JuniorTask.created_at == anchor.created_at) & (JuniorTask.id < before_id))
            )
    stmt = stmt.order_by(JuniorTask.created_at.desc(), JuniorTask.id.desc()).limit(min(max(limit, 1), 100))
    return list(db.scalars(stmt))


def get_task(db: Session, user: User, task_id: uuid.UUID) -> JuniorTask:
    row = db.get(JuniorTask, task_id)
    if not row or row.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return row


def claim_task(db: Session, user: User, task_id: uuid.UUID, claimed_by: str) -> tuple[JuniorTask, str]:
    """Atomically claim a task: single conditional UPDATE, rowcount == 1 wins.

    CRITICAL (verified in review): a non-atomic check-then-act lets two
    concurrent claims both pass the guards and both receive a claim_id, but
    only the last writer persists — violating the single-owner lease
    contract. The conditional UPDATE makes the database the arbiter:
    exactly one claimer can flip an open (or lease-expired) task to claimed.
    """
    now = _now()
    claim_id = secrets.token_hex(16)
    stmt = (
        update(JuniorTask)
        .where(
            JuniorTask.id == task_id,
            JuniorTask.user_id == user.id,
            or_(
                JuniorTask.status == "open",
                and_(
                    JuniorTask.status == "claimed",
                    or_(JuniorTask.lease_until.is_(None), JuniorTask.lease_until <= now),
                ),
            ),
        )
        .values(
            status="claimed",
            claim_id=claim_id,
            claimed_by=claimed_by,
            lease_until=now + timedelta(minutes=LEASE_MINUTES),
            attempt=JuniorTask.attempt + 1,
            error=None,
            result=None,
            updated_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    if db.execute(stmt).rowcount != 1:
        row = db.get(JuniorTask, task_id)
        if row is None or row.user_id != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        if row.status == "done":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Task already completed")
        if row.status == "failed":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Task already failed")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Task already claimed")
    db.commit()
    return db.get(JuniorTask, task_id), claim_id


def complete_task(db: Session, user: User, task_id: uuid.UUID, claim_id: str, result: dict) -> JuniorTask:
    """Atomic complete: only the current holder of claim_id can flip claimed -> done."""
    now = _now()
    stmt = (
        update(JuniorTask)
        .where(
            JuniorTask.id == task_id,
            JuniorTask.user_id == user.id,
            JuniorTask.status == "claimed",
            JuniorTask.claim_id == claim_id,
        )
        .values(status="done", result=result or {}, error=None, claim_id=None, lease_until=None, updated_at=now)
        .execution_options(synchronize_session=False)
    )
    if db.execute(stmt).rowcount != 1:
        row = db.get(JuniorTask, task_id)
        if row is None or row.user_id != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Claim mismatch")
    db.commit()
    return db.get(JuniorTask, task_id)


def fail_task(db: Session, user: User, task_id: uuid.UUID, claim_id: str, error: str, retryable: bool) -> JuniorTask:
    """Atomic fail: only the current holder of claim_id can fail; retryable reopens the task."""
    now = _now()
    stmt = (
        update(JuniorTask)
        .where(
            JuniorTask.id == task_id,
            JuniorTask.user_id == user.id,
            JuniorTask.status == "claimed",
            JuniorTask.claim_id == claim_id,
        )
        .values(
            status="open" if retryable else "failed",
            error=error,
            claim_id=None,
            lease_until=None,
            claimed_by=None,
            updated_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    if db.execute(stmt).rowcount != 1:
        row = db.get(JuniorTask, task_id)
        if row is None or row.user_id != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Claim mismatch")
    db.commit()
    return db.get(JuniorTask, task_id)
