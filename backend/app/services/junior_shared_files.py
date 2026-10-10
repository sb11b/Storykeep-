from __future__ import annotations

import secrets
import uuid
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import JuniorDocumentFile, User
from app.services.junior_shared_common import normalize_slug

MAX_FILE_BYTES = 40 * 1024 * 1024


def _folder(user_id: uuid.UUID, slug: str) -> Path:
    folder = settings.data_dir / "junior-files" / str(user_id) / slug
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def save_file(
    db: Session, user: User, slug: str, filename: str, payload: bytes, content_type: str | None
) -> JuniorDocumentFile:
    slug = normalize_slug(slug)
    if not payload:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="That file is empty.")
    if len(payload) > MAX_FILE_BYTES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="That file is larger than 40 MB.")
    safe_name = "".join(ch for ch in (filename or "file") if ch.isalnum() or ch in ".-_ ").strip() or "file"
    suffix = Path(safe_name).suffix.lower()[:12]
    stored = secrets.token_hex(16) + suffix
    path = _folder(user.id, slug) / stored
    path.write_bytes(payload)
    row = JuniorDocumentFile(
        user_id=user.id,
        document_slug=slug,
        filename=safe_name[:200],
        content_type=(content_type or "application/octet-stream")[:120],
        byte_size=len(payload),
        storage_path=str(path),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_files(db: Session, user: User, slug: str) -> list[JuniorDocumentFile]:
    slug = normalize_slug(slug)
    return list(
        db.scalars(
            select(JuniorDocumentFile)
            .where(JuniorDocumentFile.user_id == user.id, JuniorDocumentFile.document_slug == slug)
            .order_by(JuniorDocumentFile.created_at.desc())
        )
    )


def get_file(db: Session, user: User, file_id: uuid.UUID) -> JuniorDocumentFile:
    row = db.get(JuniorDocumentFile, file_id)
    if not row or row.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    if not Path(row.storage_path).is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File is missing.")
    return row


def delete_file(db: Session, user: User, file_id: uuid.UUID) -> None:
    row = db.get(JuniorDocumentFile, file_id)
    if not row or row.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    path = Path(row.storage_path)
    if path.is_file():
        path.unlink()
    db.delete(row)
    db.commit()
