from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Article, ChangeLog, Feed, SyncDevice, User
from app.schemas import SyncChange, SyncDeltaIn, SyncDeltaOut, SyncPushIn
from app.services import changelog

router = APIRouter(prefix="/sync", tags=["sync"])


@router.post("/delta", response_model=SyncDeltaOut)
def delta(payload: SyncDeltaIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> SyncDeltaOut:
    device = db.scalar(
        select(SyncDevice).where(SyncDevice.user_id == user.id, SyncDevice.device_id == payload.device_id)
    )
    if not device:
        device = SyncDevice(user_id=user.id, device_id=payload.device_id, device_name=payload.device_name)
        db.add(device)
        db.flush()
    elif payload.device_name:
        device.device_name = payload.device_name

    rows = db.scalars(
        select(ChangeLog)
        .where(ChangeLog.user_id == user.id, ChangeLog.id > payload.cursor)
        .order_by(ChangeLog.id.asc())
        .limit(payload.limit + 1)
    ).all()
    has_more = len(rows) > payload.limit
    rows = rows[: payload.limit]
    cursor = rows[-1].id if rows else payload.cursor
    device.cursor = cursor
    device.last_sync_at = datetime.now(timezone.utc)
    db.add(device)
    db.commit()
    return SyncDeltaOut(
        cursor=cursor,
        has_more=has_more,
        changes=[
            SyncChange(
                entity_type=row.entity_type,
                entity_id=row.entity_id,
                action=row.action,
                payload=row.payload,
                changed_at=row.changed_at,
            )
            for row in rows
        ],
    )


@router.post("/push")
def push(payload: SyncPushIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, int]:
    applied = 0
    for mutation in payload.mutations:
        if mutation.entity_type != "article":
            continue
        article = db.scalar(
            select(Article).join(Feed).where(Article.id == mutation.entity_id, Feed.user_id == user.id)
        )
        if not article:
            continue
        for field in ("is_read", "is_saved", "is_starred"):
            if field in mutation.payload:
                setattr(article, field, bool(mutation.payload[field]))
        changelog.record(db, user.id, "article", article.id, "upsert", mutation.payload)
        db.add(article)
        applied += 1
    db.commit()
    return {"applied": applied}
