from __future__ import annotations

import json
import logging
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.database import parse_database_url
from app.models import Annotation, Article, Backup, Feed, Tag, User

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


def create_json_export(db: Session, user: User) -> Backup:
    backup = Backup(
        user_id=user.id,
        backup_type="export_json",
        status="pending",
        destination="s3" if object_store_ready() else "local",
    )
    db.add(backup)
    db.flush()

    feeds = db.scalars(
        select(Feed)
        .where(Feed.user_id == user.id)
        .options(selectinload(Feed.articles).selectinload(Article.tags), selectinload(Feed.articles).selectinload(Article.annotations))
    ).all()
    tags = db.scalars(select(Tag).where(Tag.user_id == user.id)).all()
    notes = db.scalars(select(Annotation).where(Annotation.user_id == user.id)).all()

    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "user": {"id": str(user.id), "email": user.email, "display_name": user.display_name},
        "tags": [{"id": str(tag.id), "name": tag.name, "color": tag.color} for tag in tags],
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

    filename = f"storykeep-{user.id}-{backup.id}.json"
    path = settings.backup_dir / filename
    try:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
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
    backup = Backup(
        user_id=user_id,
        backup_type="db_dump",
        status="pending",
        destination="s3" if object_store_ready() else "local",
    )
    db.add(backup)
    db.flush()
    conn = parse_database_url(settings.database_url)
    filename = f"storykeep-db-{backup.id}.sql"
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
