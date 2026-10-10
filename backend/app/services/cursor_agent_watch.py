"""Poll Cloud Agents started from Junior and post the result in that chat."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CursorAgentWatch
from app.services import cursor_agent_bugbot
from app.services import cursor_agent_tool
from app.services import grok_conversations as grok_store
from app.services.junior_stamp import stamp_assistant_content

logger = logging.getLogger(__name__)

PENDING = "pending"
POSTED = "posted"
BUGBOT = "bugbot"
STALE_AFTER = timedelta(hours=3)
POLL_LIMIT = 20


def record_watch(
    *,
    user_id: UUID,
    conversation_id: UUID,
    agent_id: str,
    agent_url: str,
    run_id: str | None = None,
    starting_branch: str = "main",
) -> None:
    agent = (agent_id or "").strip()
    if not agent:
        return
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        existing = db.scalar(select(CursorAgentWatch).where(CursorAgentWatch.agent_id == agent))
        if existing is not None:
            return
        db.add(
            CursorAgentWatch(
                user_id=user_id,
                conversation_id=conversation_id,
                agent_id=agent,
                run_id=(run_id or "").strip() or None,
                agent_url=(agent_url or "").strip(),
                starting_branch=(starting_branch or "main").strip() or "main",
                status=PENDING,
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Could not record Cursor agent watch agent=%s", agent)
    finally:
        db.close()


def _post_follow_up(db: Session, row: CursorAgentWatch, text: str, *, status: str = POSTED) -> None:
    conversation = grok_store.lookup_owned_conversation(db, SimpleUser(row.user_id), row.conversation_id)
    if conversation is None:
        row.status = POSTED
        row.updated_at = datetime.now(timezone.utc)
        return
    grok_store.append_message(
        db,
        conversation,
        role="assistant",
        content=stamp_assistant_content(text),
    )
    row.status = status
    row.updated_at = datetime.now(timezone.utc)


class SimpleUser:
    def __init__(self, user_id: UUID) -> None:
        self.id = user_id


def _usable_bugbot_text(section: str, done: bool) -> str | None:
    text = (section or "").strip()
    if not done or not text:
        return None
    if "has not finished" in text or "No pull request yet" in text:
        return None
    return text


def _poll_bugbot(db: Session, row: CursorAgentWatch, *, now: datetime, stale: bool) -> None:
    del stale
    snapshot = cursor_agent_tool.fetch_run(row.agent_id, row.run_id)
    if snapshot.run_id and snapshot.run_id != row.run_id:
        row.run_id = snapshot.run_id
    section, done = cursor_agent_bugbot.bugbot_section(snapshot.pr_url)
    usable = _usable_bugbot_text(section, done)
    if usable:
        _post_follow_up(db, row, usable)
        return
    # Bugbot is off. A missing review is not a chat message.
    row.status = POSTED
    row.updated_at = now


def poll_one(db: Session, row: CursorAgentWatch, *, now: datetime | None = None) -> None:
    instant = now or datetime.now(timezone.utc)
    created = row.created_at
    if created is not None and created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    stale = created is not None and instant - created >= STALE_AFTER
    if row.status == BUGBOT:
        _poll_bugbot(db, row, now=instant, stale=stale)
        return
    snapshot = cursor_agent_tool.fetch_run(row.agent_id, row.run_id)
    if snapshot.run_id and snapshot.run_id != row.run_id:
        row.run_id = snapshot.run_id
    base = (row.starting_branch or "main").strip() or "main"
    if (snapshot.status or "").upper() == "FINISHED" and snapshot.branch and snapshot.branch != base and not snapshot.pr_url:
        from dataclasses import replace

        from app.services import github_tool

        opened = github_tool.open_pull_request(
            head=snapshot.branch,
            base=base,
            title=f"Junior: {snapshot.branch}",
            body=(
                "Opened for review. CodeRabbit reviews this pull request. Bugbot is off.\n\n"
                f"Agent: {row.agent_url or ''}"
            ),
        )
        if opened:
            snapshot = replace(snapshot, pr_url=opened)
    if not snapshot.reachable and not stale:
        row.updated_at = instant
        return
    bugbot_text = None
    if (snapshot.status or "").upper() == "FINISHED":
        section, done = cursor_agent_bugbot.bugbot_section(snapshot.pr_url)
        bugbot_text = _usable_bugbot_text(section, done)
    text = cursor_agent_tool.format_follow_up(
        snapshot,
        agent_url=row.agent_url,
        starting_branch=row.starting_branch or "main",
        stale=stale and (snapshot.status or "").upper() not in cursor_agent_tool.TERMINAL_RUN_STATUSES,
        bugbot_text=bugbot_text,
    )
    if text is None:
        row.updated_at = instant
        return
    _post_follow_up(db, row, text, status=POSTED)


def poll_agent_watches() -> None:
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        rows = db.scalars(
            select(CursorAgentWatch).where(CursorAgentWatch.status.in_((PENDING, BUGBOT))).limit(POLL_LIMIT)
        ).all()
        for row in rows:
            try:
                poll_one(db, row)
                db.commit()
            except Exception:
                db.rollback()
                logger.exception("Cursor agent watch failed agent=%s", row.agent_id)
    finally:
        db.close()
