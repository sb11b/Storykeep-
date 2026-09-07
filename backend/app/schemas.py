from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field, HttpUrl

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
    category_id: uuid.UUID | None = None


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


class AnnotationIn(BaseModel):
    body: str = Field(min_length=1)
    quote: str | None = None


class AnnotationOut(BaseModel):
    id: uuid.UUID
    article_id: uuid.UUID
    body: str
    quote: str | None
    created_at: datetime
    updated_at: datetime
    article_title: str | None = None

    model_config = {"from_attributes": True}


class ArchiveOut(BaseModel):
    id: uuid.UUID
    article_id: uuid.UUID
    archive_type: str
    storage_backend: str
    checksum: str | None
    byte_size: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


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
    oldest_saved_at: datetime | None
