from __future__ import annotations

from app.models import Annotation, Archive, Article, Feed, Tag
from app.schemas import (
    AnnotationOut,
    ArchiveOut,
    ArticleListItem,
    ArticleOut,
    CorrectionOut,
    FeedOut,
    OverlayAdditionOut,
    OverlayHighlightOut,
    TagOut,
)


def tag_out(tag: Tag, article_count: int = 0) -> TagOut:
    return TagOut(id=tag.id, name=tag.name, color=tag.color, article_count=article_count)


def annotation_out(note: Annotation, article_title: str | None = None) -> AnnotationOut:
    return AnnotationOut(
        id=note.id,
        article_id=note.article_id,
        body=note.body,
        quote=note.quote,
        kind=getattr(note, "kind", None) or "note",
        color=getattr(note, "color", None),
        prefix=getattr(note, "prefix", None),
        suffix=getattr(note, "suffix", None),
        created_at=note.created_at,
        updated_at=note.updated_at,
        article_title=article_title,
    )


def archive_out(row: Archive) -> ArchiveOut:
    return ArchiveOut(
        id=row.id,
        article_id=row.article_id,
        archive_type=row.archive_type,
        storage_backend=row.storage_backend,
        checksum=row.checksum,
        byte_size=row.byte_size,
        created_at=row.created_at,
    )


def article_list_item(article: Article) -> ArticleListItem:
    return ArticleListItem(
        id=article.id,
        feed_id=article.feed_id,
        feed_title=article.feed.title if article.feed else None,
        url=article.url,
        title=article.title,
        author=article.author,
        published_at=article.published_at,
        summary=article.summary,
        image_url=article.image_url,
        is_read=article.is_read,
        is_saved=article.is_saved,
        is_starred=article.is_starred,
        has_full_text=bool(article.content_text),
        source_kind=getattr(article, "source_kind", None) or "rss",
        tags=[tag_out(tag) for tag in article.tags],
    )


def article_out(article: Article) -> ArticleOut:
    return ArticleOut(
        id=article.id,
        feed_id=article.feed_id,
        feed_title=article.feed.title if article.feed else None,
        url=article.url,
        title=article.title,
        author=article.author,
        published_at=article.published_at,
        summary=article.summary,
        content_text=article.content_text,
        content_html=article.content_html,
        image_url=article.image_url,
        is_read=article.is_read,
        is_saved=article.is_saved,
        is_starred=article.is_starred,
        read_at=article.read_at,
        saved_at=article.saved_at,
        fetched_at=article.fetched_at,
        created_at=article.created_at,
        tags=[tag_out(tag) for tag in article.tags],
        annotations=[annotation_out(note) for note in article.annotations],
        archives=[archive_out(row) for row in article.archives],
        has_full_text=bool(article.content_text),
        source_kind=getattr(article, "source_kind", None) or "rss",
        source_ref=getattr(article, "source_ref", None),
        obsidian_path=getattr(article, "obsidian_path", None),
        overlay_highlights=[
            OverlayHighlightOut(
                id=row.id,
                article_id=row.article_id,
                quote=row.quote,
                note=row.note,
                color=row.color,
                created_at=row.created_at,
            )
            for row in getattr(article, "overlay_highlights", []) or []
        ],
        overlay_additions=[
            OverlayAdditionOut(
                id=row.id,
                article_id=row.article_id,
                title=row.title,
                markdown=row.markdown,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in getattr(article, "overlay_additions", []) or []
        ],
        corrections=[
            CorrectionOut(
                id=row.id,
                article_id=row.article_id,
                markdown=row.markdown,
                created_at=row.created_at,
            )
            for row in getattr(article, "corrections", []) or []
        ],
    )


def feed_out(feed: Feed, unread: int = 0, saved: int = 0, total: int = 0) -> FeedOut:
    return FeedOut(
        id=feed.id,
        url=feed.url,
        title=feed.title,
        description=feed.description,
        site_url=feed.site_url,
        favicon_url=feed.favicon_url,
        category_id=feed.category_id,
        last_fetched_at=feed.last_fetched_at,
        last_error=feed.last_error,
        is_active=feed.is_active,
        fetch_interval_minutes=feed.fetch_interval_minutes,
        unread_count=unread,
        saved_count=saved,
        article_count=total,
    )
