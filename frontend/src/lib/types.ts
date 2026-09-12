export type User = {
  id: string;
  email: string;
  display_name: string | null;
  preferences: Record<string, unknown>;
  created_at: string;
};

export type Category = {
  id: string;
  name: string;
  color: string | null;
  sort_order: number;
  feed_count: number;
};

export type Feed = {
  id: string;
  url: string;
  title: string | null;
  description: string | null;
  site_url: string | null;
  favicon_url: string | null;
  category_id: string | null;
  last_fetched_at: string | null;
  last_error: string | null;
  is_active: boolean;
  unread_count: number;
  saved_count: number;
  article_count: number;
};

export type Tag = {
  id: string;
  name: string;
  color: string | null;
  article_count: number;
};

export type Annotation = {
  id: string;
  article_id: string;
  body: string;
  quote: string | null;
  kind?: "note" | "highlight" | "addition";
  color?: string | null;
  prefix?: string | null;
  suffix?: string | null;
  created_at: string;
  updated_at: string;
  article_title?: string | null;
};

export type Archive = {
  id: string;
  article_id: string;
  archive_type: string;
  storage_backend: string;
  checksum: string | null;
  byte_size: number | null;
  created_at: string;
};

export type OverlayHighlight = {
  id: string;
  article_id: string;
  quote: string;
  note: string | null;
  color?: string | null;
  created_at: string;
};

export type OverlayAddition = {
  id: string;
  article_id: string | null;
  title: string;
  markdown: string;
  destination?: string;
  is_correction?: boolean;
  created_at: string;
  updated_at: string;
};

export type FiledNote = {
  id: string;
  title: string;
  markdown: string;
  destination: string;
  is_correction?: boolean;
  parent_id?: string | null;
  created_at: string;
  updated_at: string;
};

export type Correction = {
  id: string;
  article_id: string;
  markdown: string;
  created_at: string;
};

export type VaultImportResult = {
  imported: number;
  updated: number;
  skipped: number;
  attachments: number;
  errors: string[];
};

export type ArticleListItem = {
  id: string;
  feed_id: string;
  feed_title: string | null;
  url: string;
  title: string;
  author: string | null;
  published_at: string | null;
  summary: string | null;
  image_url: string | null;
  is_read: boolean;
  is_saved: boolean;
  is_starred: boolean;
  has_full_text: boolean;
  source_kind?: string;
  destination?: string | null;
  folder_id?: string | null;
  tags: Tag[];
};

export type ExtractResult = {
  article: Article;
  notice: string | null;
  ok: boolean;
  message: string;
  chars: number;
};

export type Article = ArticleListItem & {
  content_text: string | null;
  content_html: string | null;
  feed_html?: string | null;
  has_feed_text?: boolean;
  read_at: string | null;
  saved_at: string | null;
  fetched_at: string | null;
  created_at: string;
  guid?: string | null;
  annotations: Annotation[];
  archives: Archive[];
  source_ref?: string | null;
  obsidian_path?: string | null;
  overlay_highlights?: OverlayHighlight[];
  overlay_additions?: OverlayAddition[];
  corrections?: Correction[];
  destination?: string | null;
  folder_id?: string | null;
  is_correction?: boolean;
  parent_id?: string | null;
  filed_notes?: FiledNote[];
};

export type Page<T> = {
  items: T[];
  total: number;
  limit: number;
  offset: number;
};

export type SearchHit = {
  article: ArticleListItem;
  rank: number;
  headline: string | null;
};

export type Stats = {
  feed_count: number;
  article_count: number;
  unread_count: number;
  saved_count: number;
  annotation_count: number;
  vault_count?: number;
  additions_count?: number;
  books_count?: number;
  schoolwork_count?: number;
  oldest_saved_at: string | null;
};

export type Backup = {
  id: string;
  backup_type: string;
  status: string;
  destination: string;
  location: string | null;
  size_bytes: number | null;
  error: string | null;
  started_at: string;
  completed_at: string | null;
};

export type TtsVoice = {
  voice_id: string;
  name: string;
};

export type TtsWord = {
  text: string;
  start: number;
  end: number;
};

export type ChatStatus = {
  enabled: boolean;
  locked?: boolean;
  provider: string;
  model: string;
  requests_per_hour: number;
};

export type TtsPlan = {
  enabled: boolean;
  chars: number;
  chunks: number;
  long: boolean;
  content_hash: string;
  cached_chunks: number;
  sections: { id: string; title: string; chars: number }[];
  source_kind?: string;
  include_notes?: boolean;
  note_count?: number;
};

export type TtsStatus = {
  enabled: boolean;
  provider: string;
  voices: TtsVoice[];
};

export type FeedCandidate = {
  url: string;
  title: string | null;
  kind: string | null;
};

export type OpmlImportResult = {
  imported: number;
  skipped: number;
  errors: { url: string; detail: string }[];
};

export type FolderShelfKind = "vault" | "additions" | "books" | "notes" | "schoolwork";

export type Folder = {
  id: string;
  shelf: FolderShelfKind;
  name: string;
  item_count: number;
  created_at: string;
};

export type Shelf =
  | { kind: "inbox" }
  | { kind: "unread" }
  | { kind: "saved" }
  | { kind: "starred" }
  | { kind: "vault"; folderId?: string }
  | { kind: "additions"; folderId?: string }
  | { kind: "books"; folderId?: string }
  | { kind: "notes"; folderId?: string }
  | { kind: "schoolwork"; folderId?: string }
  | { kind: "feed"; id: string }
  | { kind: "category"; id: string }
  | { kind: "tag"; id: string }
  | { kind: "search"; q: string };
