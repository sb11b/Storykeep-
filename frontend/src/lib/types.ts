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
  tags: Tag[];
};

export type Article = ArticleListItem & {
  content_text: string | null;
  content_html: string | null;
  read_at: string | null;
  saved_at: string | null;
  fetched_at: string | null;
  created_at: string;
  annotations: Annotation[];
  archives: Archive[];
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

export type TtsStatus = {
  enabled: boolean;
  provider: string;
  voices: TtsVoice[];
};

export type Shelf =
  | { kind: "inbox" }
  | { kind: "unread" }
  | { kind: "saved" }
  | { kind: "starred" }
  | { kind: "notes" }
  | { kind: "feed"; id: string }
  | { kind: "category"; id: string }
  | { kind: "tag"; id: string }
  | { kind: "search"; q: string };
