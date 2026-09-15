from __future__ import annotations

import hmac
import logging
import re
from datetime import datetime, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Article, Feed, JuniorJob, JuniorJobRun, User
from app.services import chat as chat_service
from app.services import grok_conversations as grok_store
from app.services.demo_lock import is_locked, reject_locked
from app.services.destination import normalize_destination
from app.services.folders import resolve_folder_id
from app.services.vault_import import create_composed_note

logger = logging.getLogger(__name__)

JOB_RUN_CAP = 20
SNIPPET_CHAR_CAP = 4_000
CRON_RE = re.compile(r"^(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)$")
DEFAULT_CRON = "0 8 * * *"
DEFAULT_TZ = "America/New_York"
MY_NEWS_RE = re.compile(r"\bmy news\b", re.I)
UNREAD_RE = re.compile(r"\bunread\b", re.I)
FOX_FEED_RE = re.compile(r"\bfox(?:\s+news)?\b", re.I)
NEWSMAX_FEED_RE = re.compile(r"\bnewsmax\b", re.I)
FIVE_NEWEST_RE = re.compile(r"\b(?:five|5)\s+newest\b|\blast\s+(?:five|5)\b", re.I)
SEARCH_FAILED = "search failed"
JOB_SEARCH_SYSTEM = """You are Junior running a scheduled job with web search enabled.
Use web_search for live pages. Quote what you found.
If search does not work, reply with exactly: search failed
Never say you cannot search, cannot browse, or do not have web access.
Prefer StoryKeep Unread titles when they are included for my news.
When Unread items are listed, link each exact title as [title](#article/{article_id}) only. Never use a publisher URL as href.
"""
UNREAD_READER_SYSTEM = """StoryKeep Unread items are attached with article_id, title, and feed.
List the exact titles. Each title must be a markdown link [title](#article/{article_id}).
Never use a publisher URL as the href. Never invent ids. Stay in StoryKeep; do not send the reader to another site.
"""
UNREAD_TITLE_CAP = 40
UNREAD_DEFAULT_LIMIT = 5
PUBLISHER_MD_LINK_RE = re.compile(
    r"\[([^\]]+)\]\(https?://(?:www\.)?(?:foxnews\.com|newsmax\.com)[^)\s]*\)",
    re.I,
)
PUBLISHER_URL_RE = re.compile(r"https?://(?:www\.)?(?:foxnews\.com|newsmax\.com)\S*", re.I)


def parse_cron(expr: str) -> tuple[str, str, str, str, str]:
    raw = " ".join((expr or "").split())
    match = CRON_RE.match(raw)
    if not match:
        raise HTTPException(status_code=400, detail="Cron must be five fields: minute hour day month weekday.")
    minute, hour, day, month, dow = match.groups()
    for token, lo, hi, label in (
        (minute, 0, 59, "minute"),
        (hour, 0, 23, "hour"),
        (day, 1, 31, "day"),
        (month, 1, 12, "month"),
        (dow, 0, 7, "weekday"),
    ):
        _assert_cron_field(token, lo, hi, label)
    return minute, hour, day, month, dow


def _assert_cron_field(token: str, lo: int, hi: int, label: str) -> None:
    for part in token.split(","):
        body, step = (part.split("/", 1) + ["1"])[:2]
        try:
            step_n = int(step)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid cron {label}.") from exc
        if step_n < 1:
            raise HTTPException(status_code=400, detail=f"Invalid cron {label}.")
        if body == "*":
            continue
        if "-" in body:
            start_s, end_s = body.split("-", 1)
            try:
                start, end = int(start_s), int(end_s)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=f"Invalid cron {label}.") from exc
        else:
            try:
                start = end = int(body)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=f"Invalid cron {label}.") from exc
        if start < lo or end > hi or start > end:
            raise HTTPException(status_code=400, detail=f"Invalid cron {label}.")


def _field_matches(token: str, value: int, lo: int, hi: int) -> bool:
    for part in token.split(","):
        body, step_s = (part.split("/", 1) + ["1"])[:2]
        step = int(step_s)
        if body == "*":
            if (value - lo) % step == 0:
                return True
            continue
        if "-" in body:
            start, end = (int(item) for item in body.split("-", 1))
        else:
            start = end = int(body)
        if start <= value <= end and (value - start) % step == 0:
            return True
    return False


def cron_matches(expr: str, when: datetime) -> bool:
    minute, hour, day, month, dow = parse_cron(expr)
    if not _field_matches(minute, when.minute, 0, 59):
        return False
    if not _field_matches(hour, when.hour, 0, 23):
        return False
    if not _field_matches(day, when.day, 1, 31):
        return False
    if not _field_matches(month, when.month, 1, 12):
        return False
    cron_dow = 0 if when.isoweekday() == 7 else when.isoweekday()
    if _field_matches(dow, cron_dow, 0, 7):
        return True
    if cron_dow == 0 and _field_matches(dow, 7, 0, 7):
        return True
    return False


def resolve_zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo((name or DEFAULT_TZ).strip() or DEFAULT_TZ)
    except Exception:
        return ZoneInfo(DEFAULT_TZ)


def due_this_minute(job: JuniorJob, now: datetime | None = None) -> bool:
    if not job.enabled:
        return False
    zone = resolve_zone(job.timezone)
    stamp = (now or datetime.now(timezone.utc)).astimezone(zone)
    if not cron_matches(job.cron, stamp):
        return False
    if job.last_run_at is None:
        return True
    last = job.last_run_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    last_local = last.astimezone(zone).replace(second=0, microsecond=0)
    now_local = stamp.replace(second=0, microsecond=0)
    return last_local < now_local


def runs_today(db: Session, user_id: UUID, now: datetime | None = None) -> int:
    stamp = now or datetime.now(timezone.utc)
    start = stamp.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return int(
        db.scalar(
            select(func.count()).select_from(JuniorJobRun).where(
                JuniorJobRun.user_id == user_id,
                JuniorJobRun.created_at >= start,
            )
        )
        or 0
    )


def enforce_daily_cap(db: Session, user_id: UUID) -> None:
    if runs_today(db, user_id) >= JOB_RUN_CAP:
        raise HTTPException(
            status_code=429,
            detail=f"Junior job cap is {JOB_RUN_CAP} runs per day. Pause a job or wait until tomorrow.",
        )


def require_cron_secret(request: Request) -> None:
    secret = (settings.junior_cron_secret or "").strip()
    if not secret:
        raise HTTPException(status_code=503, detail="JUNIOR_CRON_SECRET is not set.")
    header = (request.headers.get("x-junior-cron-secret") or "").strip()
    auth = request.headers.get("authorization") or ""
    bearer = auth.split(" ", 1)[1].strip() if auth.lower().startswith("bearer ") else ""
    got = header or bearer
    if not got or not hmac.compare_digest(got, secret):
        raise HTTPException(status_code=401, detail="Bad cron secret.")


def owned_job(db: Session, user: User, job_id: UUID) -> JuniorJob:
    row = db.get(JuniorJob, job_id)
    if not row or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Job not found.")
    return row


def job_reasoning(job: JuniorJob) -> str:
    if job.xhigh:
        return "xhigh"
    cleaned = (job.reasoning or "low").strip().lower()
    return cleaned if cleaned in chat_service.REASONING_EFFORTS else "low"


def job_allows_web_search(job: object) -> bool:
    return bool(getattr(job, "web_search", False))


def tools_for_job(job: object) -> list[dict] | None:
    """xAI search tools only when the job checkbox is on. Never code_interpreter."""
    if not job_allows_web_search(job):
        return None
    return [{"type": "live_search"}]


def prompt_wants_my_news(prompt: str) -> bool:
    return prompt_wants_unread_catalog(prompt)


def prompt_wants_unread_catalog(prompt: str) -> bool:
    text = prompt or ""
    return bool(
        MY_NEWS_RE.search(text)
        or UNREAD_RE.search(text)
        or FOX_FEED_RE.search(text)
        or NEWSMAX_FEED_RE.search(text)
    )


def unread_limit_from_prompt(prompt: str, title: str = "") -> int:
    blob = f"{title}\n{prompt}"
    if FIVE_NEWEST_RE.search(blob) or re.search(r"\btop\s*(?:five|5)\b", blob, re.I):
        return 5
    if prompt_wants_unread_catalog(prompt):
        return UNREAD_DEFAULT_LIMIT
    return UNREAD_TITLE_CAP


def unread_feed_scope(prompt: str) -> str:
    text = prompt or ""
    fox = bool(FOX_FEED_RE.search(text))
    newsmax = bool(NEWSMAX_FEED_RE.search(text))
    if newsmax and not fox:
        return "newsmax"
    if fox and newsmax:
        return "fox_or_newsmax"
    if fox:
        return "fox"
    return "fox_maybe_newsmax"


def _feed_scope_filter(scope: str):
    fox = or_(
        Feed.title.ilike("%fox%"),
        Feed.url.ilike("%foxnews%"),
        Feed.site_url.ilike("%foxnews%"),
    )
    newsmax = or_(
        Feed.title.ilike("%newsmax%"),
        Feed.url.ilike("%newsmax%"),
        Feed.site_url.ilike("%newsmax%"),
    )
    if scope == "fox":
        return fox
    if scope == "newsmax":
        return newsmax
    if scope in {"fox_or_newsmax", "fox_maybe_newsmax"}:
        return or_(fox, newsmax)
    return None


def _rows_to_unread_items(rows) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for article_id, title, feed_title in rows:
        cleaned = " ".join((title or "").split())
        if not cleaned:
            continue
        items.append(
            {
                "article_id": str(article_id),
                "title": cleaned[:200],
                "feed": " ".join((feed_title or "RSS").split())[:80] or "RSS",
            }
        )
    return items


def fetch_unread(db: Session, user_id: UUID, scope: str, limit: int) -> list[dict[str, str]]:
    stmt = (
        select(Article.id, Article.title, Feed.title)
        .join(Feed, Article.feed_id == Feed.id)
        .where(
            Feed.user_id == user_id,
            Article.is_read.is_(False),
            Article.source_kind == "rss",
        )
        .order_by(Article.published_at.desc().nulls_last(), Article.created_at.desc())
        .limit(limit)
    )
    scope_filter = _feed_scope_filter(scope)
    if scope_filter is not None:
        stmt = stmt.where(scope_filter)
    return _rows_to_unread_items(db.execute(stmt).all())


def unread_items(db: Session, user_id: UUID, prompt: str, title: str = "") -> list[dict[str, str]]:
    limit = unread_limit_from_prompt(prompt, title)
    scope = unread_feed_scope(prompt)
    if scope == "fox_maybe_newsmax":
        fox = fetch_unread(db, user_id, "fox", limit)
        newsmax = fetch_unread(db, user_id, "newsmax", limit)
        if not newsmax:
            return fox[:limit]
        return fetch_unread(db, user_id, "fox_or_newsmax", limit)[:limit]
    return fetch_unread(db, user_id, scope, limit)


def unread_titles(db: Session, user_id: UUID, limit: int = UNREAD_TITLE_CAP) -> list[str]:
    items = unread_items(db, user_id, "")
    return [item["title"] for item in items[:limit]]


def format_unread_news_block(items: list[dict[str, str]]) -> str:
    if not items:
        return "StoryKeep Unread has no titles right now."
    lines = "\n".join(
        f"- article_id: {item['article_id']} · feed: {item['feed']} · "
        f"[{item['title']}](#article/{item['article_id']})"
        for item in items
    )
    return (
        "StoryKeep Unread catalog (open in the StoryKeep reader, never a publisher URL):\n"
        "Each item has article_id, title, and feed. Print exact titles as "
        "[title](#article/{article_id}) only.\n"
        f"{lines}"
    )


def unread_news_block(db: Session, user_id: UUID, prompt: str, title: str = "") -> str | None:
    if not prompt_wants_unread_catalog(prompt):
        return None
    return format_unread_news_block(unread_items(db, user_id, prompt, title))


def reader_list_markdown(items: list[dict[str, str]]) -> str:
    return "\n".join(f"- [{item['title']}](#article/{item['article_id']})" for item in items)


def rewrite_unread_links(text: str, items: list[dict[str, str]]) -> str:
    if not items:
        return text or ""
    by_title = {item["title"].casefold(): item for item in items}

    def replace_publisher(match: re.Match[str]) -> str:
        title = match.group(1) or ""
        item = by_title.get(title.casefold())
        if not item:
            return match.group(0)
        return f"[{item['title']}](#article/{item['article_id']})"

    out = PUBLISHER_MD_LINK_RE.sub(replace_publisher, text or "")
    out = PUBLISHER_URL_RE.sub("", out)
    for item in items:
        linked = f"[{item['title']}](#article/{item['article_id']})"
        if f"#article/{item['article_id']}" in out:
            continue
        pattern = re.compile(rf"(?<!\[){re.escape(item['title'])}(?!\s*\]\()", re.I)
        out, n = pattern.subn(linked, out, count=1)
        if n == 0:
            continue
    return out


def ensure_reader_links(text: str, items: list[dict[str, str]]) -> str:
    if not items:
        return text or ""
    rewritten = rewrite_unread_links(text or "", items)
    missing = [item for item in items if f"#article/{item['article_id']}" not in rewritten]
    if not missing:
        return rewritten
    catalog = reader_list_markdown(items)
    if rewritten.strip() in {"", SEARCH_FAILED}:
        return catalog
    return f"{rewritten.rstrip()}\n\n{catalog}"


def attach_unread_catalog(history: list[dict], catalog: str | None) -> list[dict]:
    if not catalog:
        return history
    prepared = list(history)
    for index in range(len(prepared) - 1, -1, -1):
        item = prepared[index]
        if item.get("role") != "user":
            continue
        next_item = dict(item)
        content = next_item.get("content")
        if isinstance(content, str):
            next_item["content"] = f"{content}\n\n{catalog}"
        elif isinstance(content, list):
            parts = list(content)
            for part_i, part in enumerate(parts):
                if isinstance(part, dict) and part.get("type") == "text":
                    parts[part_i] = {**part, "text": f"{part.get('text') or ''}\n\n{catalog}"}
                    break
            else:
                parts.append({"type": "text", "text": catalog})
            next_item["content"] = parts
        else:
            next_item["content"] = catalog
        prepared[index] = next_item
        break
    return prepared


def _search_tool_rejected(exc: HTTPException) -> bool:
    blob = f"{exc.status_code} {exc.detail}".lower()
    if exc.status_code not in {400, 410, 422, 502}:
        return False
    return any(
        token in blob
        for token in (
            "web_search",
            "live_search",
            "search_parameters",
            "invalid tool",
            "unknown tool",
            "422",
            "410",
            "gone",
        )
    )


def _complete_job_turn(
    messages: list[dict],
    *,
    model: str,
    reasoning: str,
    tools: list[dict] | None,
) -> dict[str, str]:
    if not tools:
        return chat_service.complete_once(
            messages,
            model=model,
            reasoning_effort=reasoning,
            max_tokens=900,
        )
    try:
        return chat_service.complete_with_web_search(
            messages,
            model=model,
            reasoning_effort=reasoning,
            max_tokens=900,
            timeout_sec=90.0,
        )
    except HTTPException as exc:
        if str(exc.detail) == SEARCH_FAILED or _search_tool_rejected(exc):
            raise HTTPException(status_code=502, detail=SEARCH_FAILED) from exc
        raise


def _include_excerpt(db: Session, user: User, article_id: UUID | None) -> str | None:
    if not article_id:
        return None
    article = db.scalars(
        select(Article)
        .join(Feed, Article.feed_id == Feed.id)
        .where(Article.id == article_id, Feed.user_id == user.id)
    ).first()
    if not article:
        return None
    excerpt = chat_service.article_excerpt(article)
    return (
        f"article_id: {article.id}\n"
        f"Open in reader: [{article.title or 'Untitled'}](#article/{article.id})\n"
        f"{excerpt}"
    )


def execute_job(db: Session, job: JuniorJob, *, trigger: str) -> dict:
    user = db.get(User, job.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    if is_locked(user):
        raise HTTPException(status_code=403, detail="Demo accounts cannot run Junior jobs.")
    reject_locked(user)
    enforce_daily_cap(db, user.id)
    chat_service.enforce_rate_limit(user.id)
    model = chat_service.rewrite_xai_model(job.model or chat_service.CURRENT_CHAT_MODEL)
    reasoning = job_reasoning(job)
    excerpt = _include_excerpt(db, user, job.include_article_id)
    user_line = f"[Junior job: {job.title}]\n\n{job.prompt.strip()}"
    unread = unread_items(db, user.id, job.prompt, job.title) if prompt_wants_unread_catalog(job.prompt) else []
    news = format_unread_news_block(unread) if prompt_wants_unread_catalog(job.prompt) else None
    if news:
        user_line = f"{user_line}\n\n{news}"
    history: list[dict] = []
    conversation = None
    if job.conversation_id:
        try:
            conversation = grok_store.owned_conversation(db, user, job.conversation_id)
            history = grok_store.conversation_history(db, conversation.id)
        except HTTPException:
            conversation = None
            job.conversation_id = None
    if conversation is None:
        conversation = grok_store.create_conversation(db, user, pane="junior", model=model, reasoning=reasoning)
        conversation.title = job.title[:80]
        job.conversation_id = conversation.id
        db.add(job)
        db.flush()
    tools = tools_for_job(job)
    if tools:
        windowed = chat_service.thread_window([*history, {"role": "user", "content": user_line}])
        system = JOB_SEARCH_SYSTEM
        if news:
            system = f"{system}\n\n{UNREAD_READER_SYSTEM}"
        if excerpt:
            system = f"{system}\n\nIncluded article excerpt:\n{excerpt}"
        messages = [{"role": "system", "content": system}, *windowed]
    else:
        messages = chat_service.build_xai_messages(
            [*history, {"role": "user", "content": user_line}],
            excerpt,
            include_article=bool(excerpt),
        )
        if news:
            messages[0]["content"] = f"{messages[0]['content']}\n\n{UNREAD_READER_SYSTEM}"
    status = "ok"
    output = ""
    error = None
    try:
        result = _complete_job_turn(
            messages,
            model=model,
            reasoning=reasoning,
            tools=tools,
        )
        output = result["text"]
        model = result["model"]
        reasoning = result["reasoning"]
    except HTTPException as exc:
        status = "error"
        if str(exc.detail) == SEARCH_FAILED or (tools and _search_tool_rejected(exc)):
            error = SEARCH_FAILED
            output = SEARCH_FAILED
        else:
            error = str(exc.detail)
            output = error or "Job failed."
    except Exception as exc:
        status = "error"
        error = str(exc)
        output = error
        logger.exception("Junior job failed id=%s", job.id)
    output = ensure_reader_links(output, unread)
    grok_store.append_message(db, conversation, role="user", content=user_line, set_title_from_user=False)
    assistant = grok_store.append_message(db, conversation, role="assistant", content=output)
    conversation.last_model = model
    conversation.last_reasoning = reasoning
    conversation.updated_at = datetime.now(timezone.utc)
    db.add(conversation)
    now = datetime.now(timezone.utc)
    job.last_run_at = now
    job.last_status = status
    job.updated_at = now
    db.add(
        JuniorJobRun(
            user_id=user.id,
            job_id=job.id,
            status=status,
            trigger=trigger,
            error=error,
        )
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    db.refresh(assistant)
    logger.info(
        "junior_job_run job_id=%s status=%s chars=%s",
        job.id,
        status,
        len(assistant.content or ""),
    )
    if status == "ok" and job.shelf:
        try:
            dest = normalize_destination(job.shelf, user)
            folder_id = resolve_folder_id(db, user, dest, job.folder_id)
            create_composed_note(
                db,
                user,
                job.title.strip()[:200],
                f"# {job.title.strip()}\n\n{output}",
                destination=dest,
                folder_id=folder_id,
            )
        except Exception:
            logger.exception("Junior job note failed id=%s", job.id)
    return {
        "job": job,
        "conversation_id": conversation.id,
        "assistant_message": assistant,
        "status": status,
    }


def run_due_jobs() -> None:
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        rows = db.scalars(select(JuniorJob).where(JuniorJob.enabled.is_(True))).all()
        skipped: set[UUID] = set()
        for job in rows:
            if job.user_id in skipped:
                continue
            if not due_this_minute(job, now):
                continue
            try:
                execute_job(db, job, trigger="schedule")
            except HTTPException as exc:
                if exc.status_code == 429:
                    skipped.add(job.user_id)
                    continue
                logger.warning("Due Junior job skipped id=%s detail=%s", job.id, exc.detail)
            except Exception:
                logger.exception("Due Junior job failed id=%s", job.id)
    finally:
        db.close()


def run_snippet(db: Session, user: User, message_id: UUID, code: str) -> dict:
    reject_locked(user)
    snippet = (code or "").strip()
    if not snippet:
        raise HTTPException(status_code=400, detail="Paste a short snippet to run.")
    if len(snippet) > SNIPPET_CHAR_CAP:
        raise HTTPException(status_code=400, detail="That snippet is too long for in-thread Run.")
    row = grok_store.owned_assistant_message(db, user, message_id)
    conversation = grok_store.owned_conversation(db, user, row.conversation_id)
    chat_service.enforce_rate_limit(user.id)
    user_line = f"Run this snippet in-thread only:\n```\n{snippet}\n```"
    history = grok_store.conversation_history(db, conversation.id)
    messages = [
        {
            "role": "system",
            "content": (
                "You are Junior. Use the code_execution tool to run the snippet. "
                "Return a short result in the thread. Do not open a terminal or edit StoryKeep files."
            ),
        },
        *chat_service.thread_window([*history, {"role": "user", "content": user_line}]),
    ]
    result = chat_service.complete_with_code_execution(
        messages,
        model=chat_service.CURRENT_CHAT_MODEL,
        reasoning_effort="low",
        max_tokens=700,
        timeout_sec=60.0,
    )
    user_row = grok_store.append_message(db, conversation, role="user", content=user_line)
    assistant_row = grok_store.append_message(db, conversation, role="assistant", content=result["text"])
    conversation.last_model = result["model"]
    conversation.last_reasoning = result["reasoning"]
    conversation.updated_at = datetime.now(timezone.utc)
    db.add(conversation)
    db.commit()
    db.refresh(user_row)
    db.refresh(assistant_row)
    return {
        "conversation_id": conversation.id,
        "user_message": user_row,
        "assistant_message": assistant_row,
    }
