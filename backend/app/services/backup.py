from __future__ import annotations

import json
import logging
import os
import subprocess
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.database import SessionLocal, parse_database_url
from app.models import Annotation, Article, Backup, Feed, Folder, NoteMedia, Tag, User

logger = logging.getLogger(__name__)


def object_store_ready() -> bool:
    if (settings.b2_bucket or "").strip():
        return bool((settings.b2_key_id or "").strip() and (settings.b2_application_key or "").strip())
    return bool((settings.s3_bucket or "").strip())


def _b2_endpoint_url() -> str:
    endpoint = (settings.b2_endpoint or "").strip()
    if not endpoint and (settings.b2_region or "").strip():
        endpoint = f"s3.{settings.b2_region.strip()}.backblazeb2.com"
    if not endpoint:
        return ""
    if "://" not in endpoint:
        endpoint = f"https://{endpoint}"
    return endpoint


def _object_store_client():
    import boto3
    from botocore.config import Config

    extra: dict[str, str] = {}
    endpoint = _b2_endpoint_url()
    if endpoint:
        extra["endpoint_url"] = endpoint
    kwargs: dict = {
        "config": Config(signature_version="s3v4"),
        "region_name": settings.object_region,
    }
    key_id = (settings.b2_key_id or "").strip()
    app_key = (settings.b2_application_key or "").strip()
    if key_id and app_key:
        kwargs["aws_access_key_id"] = key_id
        kwargs["aws_secret_access_key"] = app_key
    return boto3.client("s3", **kwargs, **extra)


def _redact_backup_error(message: str) -> str:
    text = message or "Backup failed"
    for secret in (
        settings.b2_application_key,
        settings.b2_key_id,
        settings.secret_key,
        os.environ.get("B2_APPLICATION_KEY") or "",
        os.environ.get("DATABASE_URL") or "",
    ):
        if secret:
            text = text.replace(secret, "[redacted]")
    return text[:1000]


def _upload_backup_file(path: Path) -> str:
    bucket = settings.object_bucket
    if not bucket:
        raise RuntimeError("No object-store bucket is configured.")
    key = f"{settings.s3_prefix.strip('/')}/{path.name}"
    _object_store_client().upload_file(str(path), bucket, key)
    return f"s3://{bucket}/{key}"


def _maybe_upload_s3(path: Path) -> str | None:
    if not object_store_ready():
        return None
    return _upload_backup_file(path)


def _dated_stamp(when: datetime) -> str:
    return when.strftime("%Y-%m-%d")


def _dated_backup_name(kind: str, backup_id: UUID, when: datetime, suffix: str) -> str:
    short = str(backup_id).split("-", 1)[0]
    return f"storykeep-{kind}-{_dated_stamp(when)}-{short}{suffix}"


def _build_export_payload(db: Session, user: User, exported_at: datetime) -> dict:
    feeds = db.scalars(
        select(Feed)
        .where(Feed.user_id == user.id)
        .options(selectinload(Feed.articles).selectinload(Article.tags), selectinload(Feed.articles).selectinload(Article.annotations))
    ).all()
    tags = db.scalars(select(Tag).where(Tag.user_id == user.id)).all()
    notes = db.scalars(select(Annotation).where(Annotation.user_id == user.id)).all()
    folders = db.scalars(select(Folder).where(Folder.user_id == user.id).order_by(Folder.shelf, Folder.name)).all()
    media_rows = db.scalars(select(NoteMedia).where(NoteMedia.user_id == user.id).order_by(NoteMedia.created_at)).all()

    media_manifest: list[dict] = []
    for row in media_rows:
        src = Path(row.storage_path)
        suffix = src.suffix or Path(row.filename).suffix or ".bin"
        archive_path = f"media/{row.id}{suffix}"
        media_manifest.append(
            {
                "id": str(row.id),
                "filename": row.filename,
                "content_type": row.content_type,
                "byte_size": row.byte_size,
                "archive_path": archive_path,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
        )

    return {
        "format": "storykeep-archive",
        "format_version": 1,
        "exported_at": exported_at.isoformat(),
        "user": {"id": str(user.id), "email": user.email, "display_name": user.display_name},
        "tags": [{"id": str(tag.id), "name": tag.name, "color": tag.color} for tag in tags],
        "folders": [
            {
                "id": str(folder.id),
                "shelf": folder.shelf,
                "name": folder.name,
                "created_at": folder.created_at.isoformat() if folder.created_at else None,
            }
            for folder in folders
        ],
        "media": media_manifest,
        "feeds": [
            {
                "id": str(feed.id),
                "url": feed.url,
                "title": feed.title,
                "category_id": str(feed.category_id) if feed.category_id else None,
                "articles": [
                    {
                        "id": str(article.id),
                        "guid": article.guid,
                        "url": article.url,
                        "title": article.title,
                        "author": article.author,
                        "published_at": article.published_at.isoformat() if article.published_at else None,
                        "summary": article.summary,
                        "content_text": article.content_text,
                        "content_html": article.content_html,
                        "destination": getattr(article, "destination", None),
                        "folder_id": str(article.folder_id) if getattr(article, "folder_id", None) else None,
                        "is_correction": bool(getattr(article, "is_correction", False)),
                        "source_kind": getattr(article, "source_kind", None) or "rss",
                        "obsidian_path": getattr(article, "obsidian_path", None),
                        "is_saved": article.is_saved,
                        "is_starred": article.is_starred,
                        "is_read": article.is_read,
                        "tag_names": [tag.name for tag in article.tags],
                        "notes": [
                            {
                                "body": note.body,
                                "quote": note.quote,
                                "kind": getattr(note, "kind", None) or "note",
                                "color": getattr(note, "color", None),
                            }
                            for note in article.annotations
                        ],
                    }
                    for article in feed.articles
                ],
            }
            for feed in feeds
        ],
        "annotation_count": len(notes),
    }


def _write_export_bundle(path: Path, payload: dict, media_rows: list[NoteMedia]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("archive.json", json.dumps(payload, ensure_ascii=False, indent=2))
        for row in media_rows:
            src = Path(row.storage_path)
            if not src.is_file():
                continue
            suffix = src.suffix or Path(row.filename).suffix or ".bin"
            zf.write(src, f"media/{row.id}{suffix}")


def create_json_export(db: Session, user: User) -> Backup:
    exported_at = datetime.now(timezone.utc)
    backup = Backup(
        user_id=user.id,
        backup_type="export_json",
        status="pending",
        destination="s3" if object_store_ready() else "local",
    )
    db.add(backup)
    db.flush()

    filename = _dated_backup_name("export", backup.id, exported_at, ".zip")
    path = settings.backup_dir / filename
    media_rows = db.scalars(select(NoteMedia).where(NoteMedia.user_id == user.id)).all()
    try:
        payload = _build_export_payload(db, user, exported_at)
        _write_export_bundle(path, payload, media_rows)
        if object_store_ready():
            backup.location = _upload_backup_file(path)
            backup.destination = "s3"
        else:
            backup.location = str(path)
            backup.destination = "local"
        backup.size_bytes = path.stat().st_size
        backup.status = "success"
        backup.error = None
    except Exception as exc:
        logger.warning("JSON backup failed: %s", _redact_backup_error(str(exc)))
        backup.status = "failed"
        backup.error = _redact_backup_error(str(exc))
        backup.destination = "s3" if object_store_ready() else "local"
        backup.location = None
    backup.completed_at = datetime.now(timezone.utc)
    db.add(backup)
    db.commit()
    db.refresh(backup)
    return backup


def create_db_dump(db: Session, user_id: UUID | None) -> Backup:
    started_at = datetime.now(timezone.utc)
    backup = Backup(
        user_id=user_id,
        backup_type="db_dump",
        status="pending",
        destination="s3" if object_store_ready() else "local",
    )
    db.add(backup)
    db.flush()
    conn = parse_database_url(settings.database_url)
    filename = _dated_backup_name("db", backup.id, started_at, ".sql")
    path = settings.backup_dir / filename
    env = {**os.environ, "PGPASSWORD": conn.password}
    if conn.connect_args.get("sslmode"):
        env["PGSSLMODE"] = conn.connect_args["sslmode"]
    try:
        result = subprocess.run(
            [
                "pg_dump",
                "-h",
                conn.host,
                "-p",
                str(conn.port),
                "-U",
                conn.user,
                "-d",
                conn.database,
                "-f",
                str(path),
            ],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        if result.returncode != 0 or not path.exists():
            raise RuntimeError(_redact_backup_error(result.stderr or "pg_dump failed"))
        if object_store_ready():
            backup.location = _upload_backup_file(path)
            backup.destination = "s3"
        else:
            backup.location = str(path)
            backup.destination = "local"
        backup.size_bytes = path.stat().st_size
        backup.status = "success"
        backup.error = None
        backup.completed_at = datetime.now(timezone.utc)
    except Exception as exc:
        logger.warning("Database dump failed: %s", _redact_backup_error(str(exc)))
        backup.status = "failed"
        backup.error = _redact_backup_error(str(exc))
        backup.completed_at = datetime.now(timezone.utc)
        backup.destination = "s3" if object_store_ready() else "local"
        backup.location = None
    db.add(backup)
    db.commit()
    db.refresh(backup)
    return backup


def last_successful_s3_dump_at(db: Session) -> datetime | None:
    row = db.scalars(
        select(Backup)
        .where(
            Backup.backup_type == "db_dump",
            Backup.status == "success",
            Backup.destination == "s3",
        )
        .order_by(Backup.completed_at.desc())
    ).first()
    return row.completed_at if row and row.completed_at else None


def scheduled_s3_dump_due(now: datetime, last: datetime | None, interval_hours: int) -> bool:
    """Phase 3: daily object-store dumps. interval_hours <= 0 disables."""
    if interval_hours <= 0:
        return False
    if last is None:
        return True
    return now - last >= timedelta(hours=interval_hours)


def run_scheduled_s3_dumps() -> None:
    """Hourly tick; uploads a pg_dump to S3/B2 when the interval has elapsed."""
    hours = int(settings.backup_interval_hours or 0)
    if hours <= 0:
        return
    if not object_store_ready():
        logger.info("Scheduled S3 dump skipped: object store is not configured.")
        return
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        last = last_successful_s3_dump_at(db)
        if not scheduled_s3_dump_due(now, last, hours):
            return
        logger.info("Starting scheduled S3 database dump.")
        create_db_dump(db, None)
    except Exception:
        logger.exception("Scheduled S3 dump failed")
    finally:
        db.close()
