from __future__ import annotations

import json
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


def _maybe_upload_s3(path: Path) -> str | None:
    if not settings.s3_bucket:
        return None
    try:
        import boto3

        key = f"{settings.s3_prefix}/{path.name}"
        client = boto3.client("s3", region_name=settings.aws_region)
        client.upload_file(str(path), settings.s3_bucket, key)
        return f"s3://{settings.s3_bucket}/{key}"
    except Exception:
        return None


def create_json_export(db: Session, user: User) -> Backup:
    backup = Backup(
        user_id=user.id,
        backup_type="export_json",
        status="pending",
        destination="s3" if settings.s3_bucket else "local",
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
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    remote = _maybe_upload_s3(path)
    backup.location = remote or str(path)
    backup.destination = "s3" if remote else "local"
    backup.size_bytes = path.stat().st_size
    backup.status = "success"
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
        destination="s3" if settings.s3_bucket else "local",
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
            raise RuntimeError(result.stderr or "pg_dump failed")
        remote = _maybe_upload_s3(path)
        backup.location = remote or str(path)
        backup.destination = "s3" if remote else "local"
        backup.size_bytes = path.stat().st_size
        backup.status = "success"
        backup.completed_at = datetime.now(timezone.utc)
    except Exception as exc:
        backup.status = "failed"
        backup.error = str(exc)[:1000]
        backup.completed_at = datetime.now(timezone.utc)
        backup.destination = "local"
    db.add(backup)
    db.commit()
    db.refresh(backup)
    return backup
