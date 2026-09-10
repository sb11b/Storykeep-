from __future__ import annotations

from app.models import Annotation, Archive, Article, Feed, Tag
from app.schemas import (
    AnnotationOut,
    ArchiveOut,
    ArticleListItem,
    ArticleOut,
    CorrectionOut,
    FeedOut,
    FiledNoteOut,
    OverlayAdditionOut,
    OverlayHighlightOut,
    TagOut,
)
from app.services.destination import DEFAULT_DESTINATION, effective_destination
from app.services.extractor import _feed_body_valid, _html_extract_candidate_valid, _is_dek_only, repair_display_body


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
        destination=effective_destination(article),
        tags=[tag_out(tag) for tag in article.tags],
    )


def filed_note_out(article: Article) -> FiledNoteOut:
    return FiledNoteOut(
        id=article.id,
        title=article.title,
        markdown=article.content_text or "",
        destination=effective_destination(article) or DEFAULT_DESTINATION,
        is_correction=bool(getattr(article, "is_correction", False)),
        parent_id=article.parent_id,
        created_at=article.created_at,
        updated_at=article.updated_at,
    )


def _display_body(article: Article) -> tuple[str | None, str | None]:
    content_text, content_html = repair_display_body(article.content_html, article.content_text)
    stored_bad = _is_dek_only(content_html, content_text) or not _html_extract_candidate_valid(content_html, content_text)
    if stored_bad and (article.feed_html or article.feed_text):
        feed_text, feed_html = repair_display_body(article.feed_html, article.feed_text)
        if feed_text and _feed_body_valid(feed_html, feed_text):
            return feed_text, feed_html
    if stored_bad and article.summary and len((article.summary or "").strip()) > 120:
        feed_text, feed_html = repair_display_body(article.summary, None)
        if feed_text and _feed_body_valid(feed_html, feed_text):
            return feed_text, feed_html
    return content_text, content_html


def article_out(article: Article, filed_notes: list[Article] | None = None) -> ArticleOut:
    content_text, content_html = _display_body(article)
    has_feed_text = bool(article.feed_html) or bool(
        article.summary and len((article.summary or "").strip()) > 120
    )
    return ArticleOut(
        id=article.id,
        feed_id=article.feed_id,
        feed_title=article.feed.title if article.feed else None,
        url=article.url,
        title=article.title,
        author=article.author,
        published_at=article.published_at,
        summary=article.summary,
        content_text=content_text,
        content_html=content_html,
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
        has_full_text=bool(content_text and content_text.strip()),
        has_feed_text=has_feed_text,
        feed_html=article.feed_html,
        guid=article.guid,
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
                destination=getattr(row, "destination", None) or DEFAULT_DESTINATION,
                is_correction=bool(getattr(row, "is_correction", False)),
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
        destination=effective_destination(article),
        is_correction=bool(getattr(article, "is_correction", False)),
        parent_id=article.parent_id,
        filed_notes=[filed_note_out(row) for row in filed_notes or []],
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
