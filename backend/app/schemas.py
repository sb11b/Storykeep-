from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field, HttpUrl, model_validator

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str | None
    preferences: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class RegisterIn(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=8)
    display_name: str | None = None


class LoginIn(BaseModel):
    email: str
    password: str


class TokenOut(BaseModel):
    user: UserOut
    access_token: str
    token_type: str = "bearer"


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    color: str | None = None
    sort_order: int = 0


class CategoryOut(BaseModel):
    id: uuid.UUID
    name: str
    color: str | None
    sort_order: int
    feed_count: int = 0

    model_config = {"from_attributes": True}


class FeedCreate(BaseModel):
    url: HttpUrl
    title: str | None = None
    category_id: uuid.UUID | None = None


class FeedCandidate(BaseModel):
    url: str
    title: str | None = None
    kind: str | None = None


class DiscoverOut(BaseModel):
    queried_url: str
    candidates: list[FeedCandidate]


class OpmlImportOut(BaseModel):
    imported: int
    skipped: int
    errors: list[dict[str, str]]


class SaveUrlIn(BaseModel):
    url: HttpUrl


class TagMergeIn(BaseModel):
    into_tag_id: uuid.UUID


class FeedUpdate(BaseModel):
    title: str | None = None
    category_id: uuid.UUID | None = None
    is_active: bool | None = None
    fetch_interval_minutes: int | None = Field(default=None, ge=5, le=24 * 60)


class FeedOut(BaseModel):
    id: uuid.UUID
    url: str
    title: str | None
    description: str | None
    site_url: str | None
    favicon_url: str | None
    category_id: uuid.UUID | None
    last_fetched_at: datetime | None
    last_error: str | None
    is_active: bool
    fetch_interval_minutes: int
    unread_count: int = 0
    saved_count: int = 0
    article_count: int = 0

    model_config = {"from_attributes": True}


class TagOut(BaseModel):
    id: uuid.UUID
    name: str
    color: str | None
    article_count: int = 0

    model_config = {"from_attributes": True}


class TagIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    color: str | None = None


HIGHLIGHT_COLORS = {"yellow", "green", "blue", "pink", "orange"}


class AnnotationIn(BaseModel):
    body: str = ""
    quote: str | None = None
    kind: str = "note"
    color: str | None = None
    prefix: str | None = None
    suffix: str | None = None

    @model_validator(mode="after")
    def validate_kind(self) -> "AnnotationIn":
        kind = (self.kind or "note").strip().lower()
        if kind not in {"note", "highlight"}:
            raise ValueError("Kind must be note or highlight")
        self.kind = kind
        if kind == "note" and not self.body.strip():
            raise ValueError("Note cannot be empty")
        if kind == "highlight":
            quote = (self.quote or "").strip()
            if len(quote) < 2:
                raise ValueError("Select text to highlight")
            color = (self.color or "").strip().lower()
            if color not in HIGHLIGHT_COLORS:
                raise ValueError("Pick yellow, green, blue, pink, or orange")
            self.quote = quote
            self.color = color
            if not self.body.strip():
                self.body = quote
        return self


class AnnotationOut(BaseModel):
    id: uuid.UUID
    article_id: uuid.UUID
    body: str
    quote: str | None
    kind: str = "note"
    color: str | None = None
    prefix: str | None = None
    suffix: str | None = None
    created_at: datetime
    updated_at: datetime
    article_title: str | None = None

    model_config = {"from_attributes": True}


class OverlayHighlightOut(BaseModel):
    id: uuid.UUID
    article_id: uuid.UUID
    quote: str
    note: str | None
    color: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class FolderIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    shelf: str


class FolderOut(BaseModel):
    id: uuid.UUID
    shelf: str
    name: str
    item_count: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


class OverlayAdditionIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    markdown: str = Field(min_length=1)
    tags: list[str] = []
    destination: str | None = None
    folder_id: uuid.UUID | None = None
    is_correction: bool = False
    parent_id: uuid.UUID | None = None


class OverlayAdditionOut(BaseModel):
    id: uuid.UUID
    article_id: uuid.UUID | None
    title: str
    markdown: str
    destination: str = "additions"
    is_correction: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DestinationIn(BaseModel):
    destination: str
    is_correction: bool | None = None
    folder_id: uuid.UUID | None = None


class CorrectionIn(BaseModel):
    markdown: str = Field(min_length=1)


class CorrectionOut(BaseModel):
    id: uuid.UUID
    article_id: uuid.UUID
    markdown: str
    created_at: datetime

    model_config = {"from_attributes": True}


class VaultImportOut(BaseModel):
    imported: int
    updated: int
    skipped: int
    attachments: int
    errors: list[str]


class ArchiveOut(BaseModel):
    id: uuid.UUID
    article_id: uuid.UUID
    archive_type: str
    storage_backend: str
    checksum: str | None
    byte_size: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class FiledNoteOut(BaseModel):
    id: uuid.UUID
    title: str
    markdown: str
    destination: str
    folder_id: uuid.UUID | None = None
    is_correction: bool = False
    parent_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ExtractOut(BaseModel):
    article: "ArticleOut"
    notice: str | None = None
    ok: bool = True
    message: str = ""
    chars: int = 0


class ArticleOut(BaseModel):
    id: uuid.UUID
    feed_id: uuid.UUID
    feed_title: str | None = None
    url: str
    title: str
    author: str | None
    published_at: datetime | None
    summary: str | None
    content_text: str | None = None
    content_html: str | None = None
    image_url: str | None
    is_read: bool
    is_saved: bool
    is_starred: bool
    read_at: datetime | None
    saved_at: datetime | None
    fetched_at: datetime | None
    created_at: datetime
    tags: list[TagOut] = []
    annotations: list[AnnotationOut] = []
    archives: list[ArchiveOut] = []
    has_full_text: bool = False
    has_feed_text: bool = False
    feed_html: str | None = None
    guid: str | None = None
    source_kind: str = "rss"
    source_ref: str | None = None
    obsidian_path: str | None = None
    overlay_highlights: list[OverlayHighlightOut] = []
    overlay_additions: list[OverlayAdditionOut] = []
    corrections: list[CorrectionOut] = []
    destination: str | None = None
    folder_id: uuid.UUID | None = None
    is_correction: bool = False
    parent_id: uuid.UUID | None = None
    filed_notes: list[FiledNoteOut] = []

    model_config = {"from_attributes": True}


class ArticleListItem(BaseModel):
    id: uuid.UUID
    feed_id: uuid.UUID
    feed_title: str | None = None
    url: str
    title: str
    author: str | None
    published_at: datetime | None
    summary: str | None
    image_url: str | None
    is_read: bool
    is_saved: bool
    is_starred: bool
    has_full_text: bool = False
    source_kind: str = "rss"
    destination: str | None = None
    folder_id: uuid.UUID | None = None
    tags: list[TagOut] = []

    model_config = {"from_attributes": True}


class ArticlePatch(BaseModel):
    is_read: bool | None = None
    is_saved: bool | None = None
    is_starred: bool | None = None


class MarkReadIn(BaseModel):
    ids: list[uuid.UUID]
    is_read: bool = True


class ArticleBulkIn(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    is_read: bool | None = None
    is_saved: bool | None = None


class TagIdsIn(BaseModel):
    tag_ids: list[uuid.UUID]


class SearchHit(BaseModel):
    article: ArticleListItem
    rank: float
    headline: str | None = None


class ArchiveCreate(BaseModel):
    type: str = "html"


class SyncDeltaIn(BaseModel):
    device_id: str
    device_name: str | None = None
    cursor: int = 0
    limit: int = Field(default=200, ge=1, le=500)


class SyncChange(BaseModel):
    entity_type: str
    entity_id: uuid.UUID
    action: str
    payload: dict[str, Any] | None = None
    changed_at: datetime | None = None


class SyncDeltaOut(BaseModel):
    cursor: int
    has_more: bool
    changes: list[SyncChange]


class SyncMutation(BaseModel):
    entity_type: str
    entity_id: uuid.UUID
    action: str
    payload: dict[str, Any] = {}


class SyncPushIn(BaseModel):
    device_id: str
    mutations: list[SyncMutation]


class BackupCreate(BaseModel):
    backup_type: str = "export_json"
    destination: str = "local"


class BackupOut(BaseModel):
    id: uuid.UUID
    backup_type: str
    status: str
    destination: str
    location: str | None
    size_bytes: int | None
    error: str | None
    started_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class PreferencesIn(BaseModel):
    theme: str | None = None
    items_per_page: int | None = Field(default=None, ge=10, le=200)
    mark_read_on_open: bool | None = None


class StatsOut(BaseModel):
    feed_count: int
    article_count: int
    unread_count: int
    saved_count: int
    annotation_count: int
    vault_count: int = 0
    additions_count: int = 0
    books_count: int = 0
    schoolwork_count: int = 0
    oldest_saved_at: datetime | None
