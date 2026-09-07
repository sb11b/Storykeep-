from __future__ import annotations

import re
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.models import NoteMedia, User
from app.services.vault_paths import windows_safe_component

MAX_IMAGE_BYTES = 8 * 1024 * 1024
ALLOWED = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}
MEDIA_RE = re.compile(r"/api/v1/media/([0-9a-fA-F-]{36})")


def save_note_image(db: Session, user: User, filename: str, payload: bytes, content_type: str | None) -> NoteMedia:
    if not payload:
        raise ValueError("That image is empty.")
    if len(payload) > MAX_IMAGE_BYTES:
        raise ValueError("Images must be 8 MB or smaller.")
    suffix = Path(filename.replace("\\", "/")).suffix.lower()
    if suffix == ".jpeg":
        suffix = ".jpg"
    if suffix not in ALLOWED:
        raise ValueError("Use PNG, JPG, GIF, or WebP.")
    if payload[:8] == b"\x89PNG\r\n\x1a\n":
        suffix = ".png"
    elif payload[:2] == b"\xff\xd8":
        suffix = ".jpg"
    elif payload[:6] in {b"GIF87a", b"GIF89a"}:
        suffix = ".gif"
    elif payload[:4] == b"RIFF" and payload[8:12] == b"WEBP":
        suffix = ".webp"
    media_id = uuid4()
    folder = settings.data_dir / "note-media" / str(user.id)
    folder.mkdir(parents=True, exist_ok=True)
    stored_name = f"{media_id}{suffix}"
    path = folder / stored_name
    path.write_bytes(payload)
    row = NoteMedia(
        id=media_id,
        user_id=user.id,
        filename=windows_safe_component(Path(filename).stem) + suffix,
        content_type=ALLOWED[suffix],
        storage_path=str(path),
        byte_size=len(payload),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def owned_media(db: Session, user: User, media_id: UUID) -> NoteMedia:
    row = db.get(NoteMedia, media_id)
    if not row or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Image not found")
    return row


def markdown_image(row: NoteMedia) -> str:
    alt = Path(row.filename).stem.replace("-", " ")
    return f"![{alt}](/api/v1/media/{row.id})"


def media_ids_in_markdown(markdown: str) -> list[UUID]:
    found: list[UUID] = []
    for match in MEDIA_RE.finditer(markdown or ""):
        try:
            found.append(UUID(match.group(1)))
        except ValueError:
            continue
    return found
