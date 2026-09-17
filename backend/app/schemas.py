from __future__ import annotations

import uuid
from datetime import date, datetime
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
    avatar_media_id: uuid.UUID | None = None
    avatar_url: str | None = None
    birthdate: date | None = None
    preferences: dict[str, Any]
    profile_read_only: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class ProfileOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str | None
    avatar_media_id: uuid.UUID | None = None
    avatar_url: str | None = None
    birthdate: date | None = None
    preferences: dict[str, Any] = Field(default_factory=dict)
    profile_read_only: bool = False
    created_at: datetime
    totp_enabled: bool = False
    email_otp_enabled: bool = False
    email_otp_available: bool = False
    has_backup_codes: bool = False


class ProfilePatchIn(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)
    birthdate: date | None = None
    avatar_media_id: uuid.UUID | None = None


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)
    confirm_password: str = Field(min_length=8)

    @model_validator(mode="after")
    def passwords_match(self) -> "ChangePasswordIn":
        if self.new_password != self.confirm_password:
            raise ValueError("New passwords do not match")
        return self


class ChangeEmailRequestIn(BaseModel):
    new_email: str = Field(min_length=3)


class ChangeEmailConfirmIn(BaseModel):
    code: str = Field(min_length=6, max_length=6)


class TwoFactorStatusOut(BaseModel):
    totp_enabled: bool
    email_otp_enabled: bool
    email_otp_available: bool
    has_backup_codes: bool


class TotpSetupOut(BaseModel):
    secret: str
    otpauth_uri: str
    qr_code_data_url: str


class TotpConfirmIn(BaseModel):
    code: str = Field(min_length=6, max_length=6)


class TotpConfirmOut(BaseModel):
    backup_codes: list[str]


class TwoFactorVerifyIn(BaseModel):
    challenge_id: uuid.UUID
    code: str = Field(min_length=6, max_length=32)
    use_backup_code: bool = False


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


class LoginResponseOut(BaseModel):
    user: UserOut | None = None
    access_token: str | None = None
    token_type: str = "bearer"
    requires_2fa: bool = False
    challenge_id: uuid.UUID | None = None
    totp_available: bool = False
    email_otp_available: bool = False


class RssShelfIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    icon: str | None = None
    color: str | None = None
    sort_order: int = 0


class RssShelfOut(BaseModel):
    id: uuid.UUID
    name: str
    icon: str | None
    color: str | None
    sort_order: int
    feed_count: int = 0
    unread_count: int = 0

    model_config = {"from_attributes": True}


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    color: str | None = None
    sort_order: int = 0
    shelf_id: uuid.UUID | None = None


class CategoryOut(BaseModel):
    id: uuid.UUID
    name: str
    color: str | None
    sort_order: int
    shelf_id: uuid.UUID | None = None
    is_system: bool = False
    feed_count: int = 0
    unread_count: int = 0

    model_config = {"from_attributes": True}


class FeedCreate(BaseModel):
    url: HttpUrl
    title: str | None = None
    shelf_id: uuid.UUID | None = None
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
    shelf_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    is_active: bool | None = None
    fetch_interval_minutes: int | None = Field(default=None, ge=5, le=24 * 60)


class FeedDeleteIn(BaseModel):
    force: bool = False


class FeedRefreshIn(BaseModel):
    feed_id: uuid.UUID | None = None


class FeedOut(BaseModel):
    id: uuid.UUID
    url: str
    title: str | None
    description: str | None
    site_url: str | None
    favicon_url: str | None
    shelf_id: uuid.UUID | None = None
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
    confirm_short: bool = False


class ApplyJuniorReplyIn(BaseModel):
    markdown: str = Field(min_length=1)
    confirm_short: bool = False
    mode: str | None = None
    heading: str | None = Field(default=None, max_length=400)
    offset: int = 0


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


class NoteRevisionOut(BaseModel):
    id: uuid.UUID
    note_id: uuid.UUID
    char_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class DestinationIn(BaseModel):
    destination: str | None = None
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
    type: str
    storage_backend: str
    checksum: str | None
    byte_size: int | None
    created_at: datetime
    download_url: str | None = None

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
    offline_view: str | None = None
    offline_archive_id: uuid.UUID | None = None

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
    destination: str | None = None
    folder_id: uuid.UUID | None = None


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


class RestoreIn(BaseModel):
    archive_id: uuid.UUID


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


class ThemeColorIn(BaseModel):
    preset: str | None = None
    custom: str | None = None


class AppearancePreferencesIn(BaseModel):
    pageBg: ThemeColorIn | None = None
    topBar: ThemeColorIn | None = None
    rail: ThemeColorIn | None = None
    font_family: str | None = None
    base_font_size: str | None = None
    page_preset: str | None = None
    rail_preset: str | None = None
    topbar_preset: str | None = None
    page_custom: str | None = None
    rail_custom: str | None = None
    topbar_custom: str | None = None


class MePatchIn(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)
    birthdate: date | None = None
    avatar_media_id: uuid.UUID | None = None
    appearance: AppearancePreferencesIn | None = None


class CustomNoteShelfIn(BaseModel):
    id: str = Field(min_length=1, max_length=16)
    name: str = Field(min_length=1, max_length=80)


class PreferencesIn(BaseModel):
    theme: str | None = None
    items_per_page: int | None = Field(default=None, ge=10, le=200)
    mark_read_on_open: bool | None = None
    tts_voice_id: str | None = Field(default=None, max_length=64)
    grok_pane_labels: dict[str, str] | None = None
    custom_note_shelves: list[CustomNoteShelfIn] | None = None
    appearance: AppearancePreferencesIn | None = None


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


class ResolveTitleOut(BaseModel):
    id: uuid.UUID
    title: str


class ResolveTitlesIn(BaseModel):
    titles: list[str] = Field(default_factory=list, max_length=50)
    shelf: str | None = None


class ResolvedTitleOut(BaseModel):
    query: str
    id: uuid.UUID | None = None
    title: str | None = None


class ResolveTitlesOut(BaseModel):
    results: list[ResolvedTitleOut]


class NoteTitleOut(BaseModel):
    id: uuid.UUID
    title: str


class NoteTitlesOut(BaseModel):
    items: list[NoteTitleOut]


class VisibleSpeechIn(BaseModel):
    visible_text: str = Field(default="", max_length=65000)
    notes_text: str | None = Field(default=None, max_length=65000)
    include_notes: bool = False
    voice_id: str = Field(default="eve", max_length=64)


class ChatSpeechIn(BaseModel):
    visible_text: str = Field(min_length=1, max_length=65000)
    voice_id: str = Field(default="eve", max_length=64)
    message_id: str = Field(min_length=1, max_length=64)


class GrokConversationOut(BaseModel):
    id: uuid.UUID
    title: str
    pane: str | None = None
    model: str = "auto"
    last_model: str | None = None
    reasoning: str = "auto"
    last_reasoning: str | None = None
    recap_question: bool = False
    saved_note_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GrokMessageFileOut(BaseModel):
    media_id: uuid.UUID
    filename: str
    content_type: str
    kind: str
    url: str
    byte_size: int | None = None
    extract_text: str | None = None


class GrokMessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    created_at: datetime
    files: list[GrokMessageFileOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class GrokConversationDetailOut(GrokConversationOut):
    messages: list[GrokMessageOut] = Field(default_factory=list)


class GrokConversationPatchIn(BaseModel):
    title: str | None = Field(default=None, max_length=80)
    model: str | None = Field(default=None, max_length=64)
    reasoning: str | None = Field(default=None, max_length=16)
    recap_question: bool | None = None
    saved_note_id: uuid.UUID | None = None
