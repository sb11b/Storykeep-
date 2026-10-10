from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_user
from app.models import User
from app.schemas import (
    JuniorTaskClaimIn,
    JuniorTaskClaimOut,
    JuniorTaskCompleteIn,
    JuniorTaskFailIn,
    JuniorTaskIn,
    JuniorTaskOut,
)
from app.services import junior_shared_tasks

router = APIRouter(tags=["junior-shared-tasks"])


@router.post("/tasks", response_model=JuniorTaskOut, status_code=201)
def create_task(
    payload: JuniorTaskIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorTaskOut:
    row = junior_shared_tasks.create_task(db, user, payload.kind, payload.title, payload.detail, payload.payload)
    return JuniorTaskOut.model_validate(row)


@router.get("/tasks", response_model=list[JuniorTaskOut])
def list_tasks(
    status_filter: Literal["open", "claimed", "done", "failed"] | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=100),
    before_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> list[JuniorTaskOut]:
    rows = junior_shared_tasks.list_tasks(db, user, status_filter=status_filter, limit=limit, before_id=before_id)
    return [JuniorTaskOut.model_validate(r) for r in rows]


@router.get("/tasks/{task_id}", response_model=JuniorTaskOut)
def get_task(
    task_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorTaskOut:
    row = junior_shared_tasks.get_task(db, user, task_id)
    return JuniorTaskOut.model_validate(row)


@router.post("/tasks/{task_id}/claim", response_model=JuniorTaskClaimOut)
def claim_task(
    task_id: uuid.UUID,
    payload: JuniorTaskClaimIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorTaskClaimOut:
    row, claim_id = junior_shared_tasks.claim_task(db, user, task_id, payload.claimed_by)
    return JuniorTaskClaimOut(task=JuniorTaskOut.model_validate(row), claim_id=claim_id, lease_until=row.lease_until)


@router.post("/tasks/{task_id}/complete", response_model=JuniorTaskOut)
def complete_task(
    task_id: uuid.UUID,
    payload: JuniorTaskCompleteIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorTaskOut:
    row = junior_shared_tasks.complete_task(db, user, task_id, payload.claim_id, payload.result)
    return JuniorTaskOut.model_validate(row)


@router.post("/tasks/{task_id}/fail", response_model=JuniorTaskOut)
def fail_task(
    task_id: uuid.UUID,
    payload: JuniorTaskFailIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorTaskOut:
    row = junior_shared_tasks.fail_task(db, user, task_id, payload.claim_id, payload.error, payload.retryable)
    return JuniorTaskOut.model_validate(row)
