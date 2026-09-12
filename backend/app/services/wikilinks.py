from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Article, Feed, User

WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:\|([^\]]+))?\]\]")


def parse_wikilink_targets(markdown: str) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for match in WIKILINK_RE.finditer(markdown or ""):
        target = (match.group(1) or "").strip()
        if not target or target in seen:
            continue
        seen.add(target)
        ordered.append(target)
    return ordered


def _prefer_shelf(candidates: list[Article], shelf: str | None) -> Article:
    if shelf:
        for article in candidates:
            if (article.destination or "") == shelf:
                return article
    return candidates[0]


def _user_articles(db: Session, user: User) -> list[Article]:
    return list(
        db.scalars(
            select(Article)
            .join(Feed)
            .where(Feed.user_id == user.id)
            .order_by(Article.updated_at.desc())
        ).all()
    )


def resolve_note_by_title(
    db: Session,
    user: User,
    title: str,
    *,
    shelf: str | None = None,
    exclude_id: str | None = None,
) -> Article | None:
    query = (title or "").strip()
    if not query:
        return None

    articles = _user_articles(db, user)
    if exclude_id:
        articles = [item for item in articles if str(item.id) != exclude_id]

    exact = [item for item in articles if item.title == query]
    if exact:
        return _prefer_shelf(exact, shelf)

    lowered = query.lower()
    ci = [item for item in articles if item.title.lower() == lowered]
    if ci:
        return _prefer_shelf(ci, shelf)

    starts = [item for item in articles if item.title.lower().startswith(lowered)]
    if starts:
        return _prefer_shelf(starts, shelf)

    return None


def resolve_note_titles(
    db: Session,
    user: User,
    titles: list[str],
    *,
    shelf: str | None = None,
    exclude_id: str | None = None,
) -> dict[str, Article | None]:
    unique: list[str] = []
    seen: set[str] = set()
    for raw in titles:
        title = (raw or "").strip()
        if not title or title in seen:
            continue
        seen.add(title)
        unique.append(title)

    resolved: dict[str, Article | None] = {}
    for title in unique:
        resolved[title] = resolve_note_by_title(
            db,
            user,
            title,
            shelf=shelf,
            exclude_id=exclude_id,
        )
    return resolved


def search_note_titles(
    db: Session,
    user: User,
    query: str,
    *,
    limit: int = 20,
) -> list[tuple[str, str]]:
    needle = (query or "").strip().lower()
    articles = _user_articles(db, user)
    if needle:
        articles = [item for item in articles if needle in item.title.lower()]
    else:
        articles = articles[: limit * 2]

    seen: set[str] = set()
    items: list[tuple[str, str]] = []
    for article in articles:
        title = (article.title or "").strip()
        if not title:
            continue
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)
        items.append((str(article.id), title))
        if len(items) >= limit:
            break
    return items
