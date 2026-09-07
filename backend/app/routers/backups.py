from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Backup, User
from app.schemas import BackupCreate, BackupOut
from app.services import backup as backup_service

router = APIRouter(tags=["backups"])


@router.post("/backups", response_model=BackupOut)
def create_backup(
    payload: BackupCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> BackupOut:
    if payload.backup_type == "db_dump":
        row = backup_service.create_db_dump(db, user.id)
    else:
        row = backup_service.create_json_export(db, user)
    return BackupOut.model_validate(row)


@router.get("/backups", response_model=list[BackupOut])
def list_backups(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[BackupOut]:
    rows = db.scalars(select(Backup).where(Backup.user_id == user.id).order_by(Backup.started_at.desc())).all()
    return [BackupOut.model_validate(row) for row in rows]


@router.get("/backups/{backup_id}/download")
def download_backup(backup_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.get(Backup, backup_id)
    if not row or row.user_id != user.id or not row.location:
        raise HTTPException(status_code=404, detail="Backup not found")
    if row.location.startswith("s3://"):
        raise HTTPException(status_code=400, detail="Download this file from S3")
    return FileResponse(row.location, filename=row.location.rsplit("/", 1)[-1])


@router.get("/export")
def export_now(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> BackupOut:
    return BackupOut.model_validate(backup_service.create_json_export(db, user))
