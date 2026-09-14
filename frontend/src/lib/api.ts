import type {
  Annotation,
  Archive,
  Article,
  ExtractResult,
  Backup,
  Category,
  Feed,
  FeedCandidate,
  OpmlImportResult,
  Page,
  SearchHit,
  Stats,
  Tag,
  TtsPlan,
  SttStatus,
  TtsStatus,
  TtsWord,
  User,
  Profile,
  LoginResult,
  TotpSetup,
  VaultImportResult,
  ChatStatus,
  GrokConversation,
  GrokConversationDetail,
  GrokMessage,
  Correction,
} from "./types";

import { httpErrorFallback, parseErrorPayload } from "@/lib/api-errors";
import { fetchSpeechChunk } from "@/lib/tts-speech-client";
import { formatChatError } from "@/lib/grok-chat-error";
import { readGrokChatStream, type GrokStreamMeta } from "@/lib/grok-stream";

export type NoteMediaUpload = {
  id: string;
  url: string;
  markdown: string;
  filename: string;
  kind: "image" | "file";
  byte_size?: number | null;
};

async function uploadNoteMedia(file: File): Promise<NoteMediaUpload> {
  const body = new FormData();
  body.append("file", file);
  const response = await fetch("/api/v1/media", {
    method: "POST",
    body,
    credentials: "include",
    cache: "no-store",
  });
  if (!response.ok) {
    let detail: string | null = null;
    try {
      detail = parseErrorPayload(await response.json());
    } catch {
      /* ignore */
    }
    throw new ApiError(response.status, detail || httpErrorFallback(response.status));
  }
  return (await response.json()) as NoteMediaUpload;
}

export class ApiError extends Error {
  status: number;
  partial?: boolean;
  constructor(status: number, message: string, extra?: { partial?: boolean }) {
    super(message);
    this.status = status;
    this.partial = extra?.partial;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(path, {
    ...init,
    headers,
    credentials: "include",
    cache: "no-store",
  });
  if (!response.ok) {
    let detail: string | null = null;
    try {
      detail = parseErrorPayload(await response.json());
    } catch {
      /* ignore */
    }
    if (!detail && response.statusText?.trim()) detail = response.statusText.trim();
    throw new ApiError(response.status, detail || httpErrorFallback(response.status));
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export type HealthInfo = { status: string; build: string; built_at: string };

export const api = {
  health: () => request<HealthInfo>("/api/health"),
  me: () => request<Profile>("/api/v1/me"),
  profile: () => request<Profile>("/api/v1/auth/profile"),
  updateMe: (payload: {
    display_name?: string | null;
    birthdate?: string | null;
    avatar_media_id?: string | null;
    appearance?: Record<string, unknown>;
  }) =>
    request<Profile>("/api/v1/me", {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  updateProfile: (payload: {
    display_name?: string | null;
    birthdate?: string | null;
    avatar_media_id?: string | null;
  }) =>
    request<Profile>("/api/v1/auth/profile", {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  getPreferences: () => request<Record<string, unknown>>("/api/v1/preferences"),
  updatePreferences: (payload: Record<string, unknown>) =>
    request<Record<string, unknown>>("/api/v1/preferences", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  ttsVoices: () => request<{ voices: import("@/lib/types").TtsVoice[] }>("/api/v1/tts/voices"),
  changePassword: (payload: { current_password: string; new_password: string; confirm_password: string }) =>
    request<{ ok: boolean }>("/api/v1/auth/change-password", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  requestEmailChange: (new_email: string) =>
    request<{ ok: boolean }>("/api/v1/auth/change-email/request", {
      method: "POST",
      body: JSON.stringify({ new_email }),
    }),
  confirmEmailChange: (code: string) =>
    request<Profile>("/api/v1/auth/change-email/confirm", {
      method: "POST",
      body: JSON.stringify({ code }),
    }),
  twoFactorStatus: () => request<import("@/lib/types").Profile>("/api/v1/auth/2fa"),
  setupTotp: () => request<TotpSetup>("/api/v1/auth/2fa/totp/setup", { method: "POST" }),
  confirmTotp: (code: string) =>
    request<{ backup_codes: string[] }>("/api/v1/auth/2fa/totp/confirm", {
      method: "POST",
      body: JSON.stringify({ code }),
    }),
  disableTotp: (code: string) =>
    request<{ ok: boolean }>("/api/v1/auth/2fa/totp/disable", {
      method: "POST",
      body: JSON.stringify({ code }),
    }),
  enableEmailOtp: () => request<{ ok: boolean }>("/api/v1/auth/2fa/email/enable", { method: "POST" }),
  disableEmailOtp: () => request<{ ok: boolean }>("/api/v1/auth/2fa/email/disable", { method: "POST" }),
  login: (email: string, password: string) =>
    request<LoginResult>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  verifyLogin2fa: (payload: { challenge_id: string; code: string; use_backup_code?: boolean }) =>
    request<LoginResult>("/api/v1/auth/login/2fa", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  register: (email: string, password: string, display_name?: string) =>
    request<{ user: User }>("/api/v1/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, display_name }),
    }),
  logout: () => request<{ ok: boolean }>("/api/v1/auth/logout", { method: "POST" }),
  stats: () => request<Stats>("/api/v1/stats"),
  folders: (shelf?: string) =>
    request<import("@/lib/types").Folder[]>(shelf ? `/api/v1/folders?shelf=${encodeURIComponent(shelf)}` : "/api/v1/folders"),
  createFolder: (shelf: string, name: string) =>
    request<import("@/lib/types").Folder>("/api/v1/folders", {
      method: "POST",
      body: JSON.stringify({ shelf, name }),
    }),
  renameFolder: (folderId: string, shelf: string, name: string) =>
    request<import("@/lib/types").Folder>(`/api/v1/folders/${folderId}`, {
      method: "PATCH",
      body: JSON.stringify({ shelf, name }),
    }),
  deleteFolder: (folderId: string) =>
    request<{ ok: boolean }>(`/api/v1/folders/${folderId}`, { method: "DELETE" }),
  feeds: (opts?: { shelfId?: string; categoryId?: string }) => {
    const search = new URLSearchParams();
    if (opts?.shelfId) search.set("shelf_id", opts.shelfId);
    if (opts?.categoryId) search.set("category_id", opts.categoryId);
    const qs = search.toString();
    return request<Feed[]>(`/api/v1/feeds${qs ? `?${qs}` : ""}`);
  },
  updateFeed: (id: string, body: { title?: string; shelf_id?: string; category_id?: string | null }) =>
    request<Feed>(`/api/v1/feeds/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  addFeed: (
    url: string,
    opts?: { shelfId?: string | null; categoryId?: string | null; title?: string | null },
  ) =>
    request<Feed>("/api/v1/feeds", {
      method: "POST",
      body: JSON.stringify({
        url,
        shelf_id: opts?.shelfId || null,
        category_id: opts?.categoryId || null,
        title: opts?.title || null,
      }),
    }),
  discoverFeeds: (url: string) =>
    request<{ queried_url: string; candidates: FeedCandidate[] }>(
      `/api/v1/feeds/discover?url=${encodeURIComponent(url)}`,
    ),
  importVault: async (file: File) => {
    const body = new FormData();
    body.append("file", file);
    const response = await fetch("/api/v1/sources/obsidian/import", {
      method: "POST",
      body,
      credentials: "include",
      cache: "no-store",
    });
    if (!response.ok) {
      let detail = response.statusText;
      try {
        const data = (await response.json()) as { detail?: string };
        if (typeof data.detail === "string") detail = data.detail;
      } catch {
        /* ignore */
      }
      throw new ApiError(response.status, detail);
    }
    return (await response.json()) as VaultImportResult;
  },
  downloadObsidianPack: async () => {
    const response = await fetch("/api/v1/export/obsidian-pack", { credentials: "include", cache: "no-store" });
    if (!response.ok) throw new ApiError(response.status, "Could not build the Obsidian pack");
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "storykeep-obsidian-pack.zip";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  },
  addStandaloneAddition: (title: string, markdown: string, tags: string[] = []) =>
    request(`/api/v1/storykeep-notes`, {
      method: "POST",
      body: JSON.stringify({ title, markdown, tags }),
    }),
  composeVaultNote: (
    title: string,
    markdown: string,
    tags: string[] = [],
    destination?: string,
    isCorrection?: boolean,
    folderId?: string | null,
  ) =>
    request<Article>("/api/v1/sources/obsidian/notes", {
      method: "POST",
      body: JSON.stringify({
        title,
        markdown,
        tags,
        destination,
        folder_id: folderId ?? null,
        is_correction: Boolean(isCorrection),
      }),
    }),
  updateComposedNote: (
    articleId: string,
    title: string,
    markdown: string,
    destination?: string,
    isCorrection?: boolean,
    folderId?: string | null,
  ) =>
    request<Article>(`/api/v1/articles/${articleId}/storykeep-note`, {
      method: "PATCH",
      body: JSON.stringify({
        title,
        markdown,
        destination,
        folder_id: folderId ?? null,
        is_correction: Boolean(isCorrection),
      }),
    }),
  setNoteDestination: (articleId: string, destination: string, isCorrection?: boolean, folderId?: string | null) =>
    request<Article>(`/api/v1/articles/${articleId}/destination`, {
      method: "PATCH",
      body: JSON.stringify({ destination, folder_id: folderId ?? null, is_correction: isCorrection }),
    }),
  resolveNoteTitle: (title: string, shelf?: string, excludeId?: string) => {
    const params = new URLSearchParams({ title });
    if (shelf) params.set("shelf", shelf);
    if (excludeId) params.set("exclude_id", excludeId);
    return request<{ id: string; title: string } | null>(`/api/v1/articles/resolve-title?${params.toString()}`);
  },
  resolveNoteTitles: (titles: string[], shelf?: string, excludeId?: string) => {
    const params = excludeId ? `?exclude_id=${encodeURIComponent(excludeId)}` : "";
    return request<{ results: Array<{ query: string; id: string | null; title: string | null }> }>(
      `/api/v1/articles/resolve-titles${params}`,
      {
        method: "POST",
        body: JSON.stringify({ titles, shelf: shelf || null }),
      },
    );
  },
  noteTitles: (q?: string, limit = 20) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (q?.trim()) params.set("q", q.trim());
    return request<{ items: Array<{ id: string; title: string }> }>(`/api/v1/articles/note-titles?${params.toString()}`);
  },
  uploadNoteMedia,
  uploadNoteImage: uploadNoteMedia,
  deleteNoteMedia: (id: string) =>
    request<{ ok: boolean; deleted?: boolean }>(`/api/v1/media/${id}`, { method: "DELETE" }),
  uploadDocument: async (file: File, title?: string, tags?: string) => {
    const body = new FormData();
    body.append("file", file);
    if (title?.trim()) body.append("title", title.trim());
    if (tags?.trim()) body.append("tags", tags.trim());
    const response = await fetch("/api/v1/sources/upload", {
      method: "POST",
      body,
      credentials: "include",
      cache: "no-store",
    });
    if (!response.ok) {
      let detail = response.statusText;
      try {
        const data = (await response.json()) as { detail?: string };
        if (typeof data.detail === "string") detail = data.detail;
      } catch {
        /* ignore */
      }
      throw new ApiError(response.status, detail);
    }
    return (await response.json()) as Article;
  },
  addAddition: (
    articleId: string,
    title: string,
    markdown: string,
    destination?: string,
    isCorrection?: boolean,
    folderId?: string | null,
  ) =>
    request(`/api/v1/articles/${articleId}/additions`, {
      method: "POST",
      body: JSON.stringify({
        title,
        markdown,
        destination: destination || "notes",
        folder_id: folderId ?? null,
        is_correction: Boolean(isCorrection),
      }),
    }),
  upsertCorrection: (articleId: string, markdown: string) =>
    request<Correction>(`/api/v1/articles/${articleId}/corrections`, {
      method: "POST",
      body: JSON.stringify({ markdown }),
    }),
  deleteCorrection: (articleId: string) =>
    request<{ ok: boolean }>(`/api/v1/articles/${articleId}/corrections`, { method: "DELETE" }),
  importOpml: async (file: File) => {
    const body = new FormData();
    body.append("file", file);
    const response = await fetch("/api/v1/feeds/import-opml", {
      method: "POST",
      body,
      credentials: "include",
      cache: "no-store",
    });
    if (!response.ok) {
      let detail = response.statusText;
      try {
        const data = (await response.json()) as { detail?: string };
        if (typeof data.detail === "string") detail = data.detail;
      } catch {
        /* ignore */
      }
      throw new ApiError(response.status, detail);
    }
    return (await response.json()) as OpmlImportResult;
  },
  exportOpml: async () => {
    const response = await fetch("/api/v1/feeds/opml", { credentials: "include", cache: "no-store" });
    if (!response.ok) throw new ApiError(response.status, "Could not export OPML");
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "storykeep.opml";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  },
  saveUrl: (url: string) =>
    request<Article>("/api/v1/articles/from-url", {
      method: "POST",
      body: JSON.stringify({ url }),
    }),
  renameTag: (id: string, name: string) =>
    request<Tag>(`/api/v1/tags/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ name }),
    }),
  mergeTag: (id: string, into_tag_id: string) =>
    request<Tag>(`/api/v1/tags/${id}/merge`, {
      method: "POST",
      body: JSON.stringify({ into_tag_id }),
    }),
  refreshFeed: (id: string) =>
    request<Feed>(`/api/v1/feeds/${id}/refresh`, { method: "POST" }),
  refreshAll: () => request<{ created: number }>("/api/v1/feeds/refresh", { method: "POST" }),
  deleteFeed: (id: string, force = false) =>
    request<{ ok: boolean }>(`/api/v1/feeds/${id}?force=${force}`, { method: "DELETE" }),
  categories: (shelfId?: string) => {
    const qs = shelfId ? `?shelf_id=${encodeURIComponent(shelfId)}` : "";
    return request<Category[]>(`/api/v1/categories${qs}`);
  },
  createCategory: (name: string, shelfId: string, color?: string) =>
    request<Category>("/api/v1/categories", {
      method: "POST",
      body: JSON.stringify({ name, shelf_id: shelfId, color }),
    }),
  updateCategory: (id: string, body: { name: string; color?: string | null; sort_order?: number }) =>
    request<Category>(`/api/v1/categories/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  deleteCategory: (id: string) => request<{ ok: boolean }>(`/api/v1/categories/${id}`, { method: "DELETE" }),
  rssShelves: () => request<import("@/lib/types").RssShelf[]>("/api/v1/rss-shelves"),
  createRssShelf: (name: string) =>
    request<import("@/lib/types").RssShelf>("/api/v1/rss-shelves", {
      method: "POST",
      body: JSON.stringify({ name }),
    }),
  updateRssShelf: (id: string, body: { name: string; sort_order?: number }) =>
    request<import("@/lib/types").RssShelf>(`/api/v1/rss-shelves/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  deleteRssShelf: (id: string) => request<{ ok: boolean }>(`/api/v1/rss-shelves/${id}`, { method: "DELETE" }),
  tags: () => request<Tag[]>("/api/v1/tags"),
  articles: (params: Record<string, string | number | boolean | undefined>) => {
    const search = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== "") search.set(key, String(value));
    }
    return request<Page<Article>>(`/api/v1/articles?${search.toString()}`);
  },
  article: (id: string) => request<Article>(`/api/v1/articles/${id}`),
  patchArticle: (
    id: string,
    body: Partial<Pick<Article, "is_read" | "is_saved" | "is_starred" | "destination" | "folder_id">>,
  ) =>
    request<Article>(`/api/v1/articles/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  fileArticle: (articleId: string, destination: string | null, folderId?: string | null) =>
    request<Article>(`/api/v1/articles/${articleId}`, {
      method: "PATCH",
      body: JSON.stringify({ destination, folder_id: folderId ?? null }),
    }),
  deleteArticle: (id: string) =>
    request<{ ok: boolean }>(`/api/v1/articles/${id}`, {
      method: "DELETE",
    }),
  bulkArticles: (ids: string[], body: { is_read?: boolean; is_saved?: boolean }) =>
    request<{ updated: number }>("/api/v1/articles/bulk", {
      method: "POST",
      body: JSON.stringify({ ids, ...body }),
    }),
  markFeedRead: (id: string) =>
    request<{ updated: number }>(`/api/v1/feeds/${id}/mark-read`, { method: "POST" }),
  extract: (id: string) =>
    request<ExtractResult>(`/api/v1/articles/${id}/extract`, { method: "PATCH" }),
  useFeedText: (id: string) =>
    request<Article>(`/api/v1/articles/${id}/use-feed-text`, { method: "PATCH" }),
  attachTag: (id: string, name: string) =>
    request<Tag>(`/api/v1/articles/${id}/tags`, {
      method: "POST",
      body: JSON.stringify({ name }),
    }),
  addNote: (
    id: string,
    body: string,
    extra?: { quote?: string; kind?: "note" | "highlight"; color?: string; prefix?: string; suffix?: string },
  ) =>
    request<Annotation>(`/api/v1/articles/${id}/annotations`, {
      method: "POST",
      body: JSON.stringify({ body, quote: extra?.quote, kind: extra?.kind || "note", color: extra?.color, prefix: extra?.prefix, suffix: extra?.suffix }),
    }),
  deleteNote: (id: string) =>
    request<{ ok: boolean }>(`/api/v1/annotations/${id}`, { method: "DELETE" }),
  notes: (opts?: { limit?: number; offset?: number }) => {
    const search = new URLSearchParams();
    if (opts?.limit != null) search.set("limit", String(opts.limit));
    if (opts?.offset != null) search.set("offset", String(opts.offset));
    const query = search.toString();
    return request<Page<Annotation>>(`/api/v1/annotations${query ? `?${query}` : ""}`);
  },
  archive: (id: string, type: "html" | "pdf" = "html") =>
    request(`/api/v1/articles/${id}/archive`, {
      method: "POST",
      body: JSON.stringify({ type }),
    }),
  archives: (id: string) => request<Archive[]>(`/api/v1/articles/${id}/archives`),
  restore: (id: string, archiveId: string) =>
    request<Article>(`/api/v1/articles/${id}/restore`, {
      method: "POST",
      body: JSON.stringify({ archive_id: archiveId }),
    }),
  search: (q: string, opts?: { saved?: boolean; limit?: number; offset?: number }) => {
    const search = new URLSearchParams({ q });
    if (opts?.saved) search.set("saved", "true");
    if (opts?.limit != null) search.set("limit", String(opts.limit));
    if (opts?.offset != null) search.set("offset", String(opts.offset));
    return request<Page<SearchHit>>(`/api/v1/search?${search.toString()}`);
  },
  backups: () => request<Backup[]>("/api/v1/backups"),
  createBackup: (backup_type: string) =>
    request<Backup>(`/api/v1/backups`, {
      method: "POST",
      body: JSON.stringify({ backup_type }),
    }),
  tts: () => request<TtsStatus>("/api/v1/tts"),
  stt: () => request<SttStatus>("/api/v1/stt"),
  ttsPlan: (id: string, voiceId: string, opts?: { includeNotes?: boolean }) => {
    const search = new URLSearchParams({ voice_id: voiceId });
    if (opts?.includeNotes) search.set("include_notes", "true");
    return request<TtsPlan>(`/api/v1/articles/${id}/tts/plan?${search.toString()}`);
  },
  ttsPlanVisible: (
    id: string,
    body: { visibleText: string; notesText?: string; voiceId: string; includeNotes?: boolean },
  ) =>
    request<TtsPlan>(`/api/v1/articles/${id}/tts/plan`, {
      method: "POST",
      body: JSON.stringify({
        visible_text: body.visibleText,
        notes_text: body.notesText ?? null,
        voice_id: body.voiceId,
        include_notes: Boolean(body.includeNotes),
      }),
    }),
  releaseTtsAudio: (id: string, voiceId: string) =>
    request<{ ok: boolean }>(`/api/v1/articles/${id}/tts/release?voice_id=${encodeURIComponent(voiceId)}`, {
      method: "POST",
    }),
  messageSpeech: async (
    messageId: string,
    voiceId: string,
    chunk: number,
    visibleText: string,
    confirm = false,
    opts?: { signal?: AbortSignal; timeoutMs?: number },
  ) => {
    const search = new URLSearchParams({ chunk: String(chunk) });
    if (confirm) search.set("confirm", "true");
    return fetchSpeechChunk(
      `/api/v1/tts/message?${search.toString()}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message_id: messageId,
          voice_id: voiceId,
          visible_text: visibleText,
        }),
      },
      "chat",
      { signal: opts?.signal, timeoutMs: opts?.timeoutMs, chars: visibleText.length },
    );
  },
  chatStatus: () => request<ChatStatus>("/api/v1/chat"),
  chatHealth: () =>
    request<{
      ok: boolean;
      model: string;
      reasoning: string;
      ttft_ms: number | null;
      xai_status: number | string | null;
      message?: string;
    }>("/api/v1/chat/health"),
  chatImagine: (
    body: { prompt: string; conversation_id?: string | null; media_ids?: string[] },
    signal?: AbortSignal,
  ) =>
    request<{ conversation_id: string; user_message: GrokMessage; assistant_message: GrokMessage }>(
      "/api/v1/chat/imagine",
      { method: "POST", body: JSON.stringify(body), signal },
    ),
  chatConversations: () => request<GrokConversation[]>("/api/v1/chat/conversations"),
  chatConversation: (id: string) => request<GrokConversationDetail>(`/api/v1/chat/conversations/${id}`),
  patchChatConversation: (
    id: string,
    payload: { title?: string; model?: string; reasoning?: string; recap_question?: boolean; saved_note_id?: string | null },
  ) =>
    request<GrokConversation>(`/api/v1/chat/conversations/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  deleteChatConversation: (id: string) =>
    request<{ ok: boolean }>(`/api/v1/chat/conversations/${id}`, { method: "DELETE" }),
  streamChat: async (
    body: {
      message: string;
      conversation_id?: string | null;
      model?: string;
      reasoning_effort?: string;
      article_id: string | null;
      include_article: boolean;
      include_note_id?: string | null;
      recap_question?: boolean;
      retry?: boolean;
      media_ids?: string[];
    },
    onDelta: (text: string) => void,
    onMeta?: (meta: GrokStreamMeta) => void,
    signal?: AbortSignal,
    onOpen?: () => void,
  ) => {
    const response = await fetch("/api/v1/chat", {
      method: "POST",
      credentials: "include",
      cache: "no-store",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify(body),
      signal,
    });
    const contentType = response.headers.get("content-type") || "";
    if (!response.ok || !contentType.includes("text/event-stream")) {
      let detail = response.statusText;
      try {
        const data = (await response.json()) as { detail?: string; message?: string };
        if (typeof data.message === "string" && data.message.trim()) detail = data.message;
        else if (typeof data.detail === "string") detail = data.detail;
      } catch {
        /* ignore */
      }
      throw new ApiError(response.status, formatChatError(response.status, detail));
    }
    onOpen?.();
    await readGrokChatStream(response, { onDelta, onMeta }, signal);
  },
  articleSpeechVisible: async (
    id: string,
    voiceId: string,
    chunk: number,
    body: { visibleText: string; notesText?: string; includeNotes?: boolean },
    opts?: { confirm?: boolean },
  ) => {
    const search = new URLSearchParams({ chunk: String(chunk) });
    if (opts?.confirm) search.set("confirm", "true");
    return fetchSpeechChunk(
      `/api/v1/articles/${id}/tts?${search.toString()}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          visible_text: body.visibleText,
          notes_text: body.notesText ?? null,
          voice_id: voiceId,
          include_notes: Boolean(body.includeNotes),
        }),
      },
      "article",
    );
  },
  articleSpeech: async (
    id: string,
    voiceId: string,
    chunk = 0,
    opts?: { confirm?: boolean; includeNotes?: boolean },
  ) => {
    const search = new URLSearchParams({ voice_id: voiceId, chunk: String(chunk) });
    if (opts?.confirm) search.set("confirm", "true");
    if (opts?.includeNotes) search.set("include_notes", "true");
    return fetchSpeechChunk(`/api/v1/articles/${id}/tts?${search.toString()}`, { method: "GET" }, "article");
  },
  schoolQuiz: (body: { message_id?: string | null; article_id?: string | null; conversation_id?: string | null; persist?: boolean }) =>
    request<{
      questions: Array<{ n: string; q: string; a: string }>;
      questions_md: string;
      key_md: string;
      markdown: string;
      word_count: number;
      assistant_message?: GrokMessage;
    }>("/api/v1/school/quiz", { method: "POST", body: JSON.stringify(body) }),
  schoolApa: (body: { message_id?: string | null; article_id?: string | null; conversation_id?: string | null; persist?: boolean }) =>
    request<{ markdown: string; citations_block: string; word_count: number; assistant_message?: GrokMessage }>(
      "/api/v1/school/apa",
      { method: "POST", body: JSON.stringify(body) },
    ),
  schoolTrim: (body: {
    message_id?: string | null;
    article_id?: string | null;
    conversation_id?: string | null;
    persist?: boolean;
    target: number;
  }) =>
    request<{ markdown: string; word_count: number; target: number; assistant_message?: GrokMessage }>(
      "/api/v1/school/trim",
      { method: "POST", body: JSON.stringify(body) },
    ),
  schoolGrammar: (body: { message_id?: string | null; article_id?: string | null; conversation_id?: string | null; persist?: boolean }) =>
    request<{ markdown: string; clean_markdown: string; word_count: number; assistant_message?: GrokMessage }>(
      "/api/v1/school/grammar",
      { method: "POST", body: JSON.stringify(body) },
    ),
  schoolQuizSave: (body: {
    questions_md: string;
    key_md: string;
    article_id?: string | null;
    destination?: string;
    folder_id?: string | null;
  }) => request<Article>("/api/v1/school/quiz/save", { method: "POST", body: JSON.stringify(body) }),
  juniorJobs: () => request<{ items: JuniorJob[] }>("/api/v1/junior/jobs"),
  createJuniorJob: (body: Partial<JuniorJob> & { title: string; prompt: string }) =>
    request<JuniorJob>("/api/v1/junior/jobs", { method: "POST", body: JSON.stringify(body) }),
  patchJuniorJob: (id: string, body: Partial<JuniorJob>) =>
    request<JuniorJob>(`/api/v1/junior/jobs/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteJuniorJob: (id: string) => request<{ ok: boolean }>(`/api/v1/junior/jobs/${id}`, { method: "DELETE" }),
  runJuniorJob: (id: string) =>
    request<{ job: JuniorJob; conversation_id: string; assistant_message: GrokMessage }>(
      `/api/v1/junior/jobs/${id}/run`,
      { method: "POST" },
    ),
  runChatSnippet: (messageId: string, code: string) =>
    request<{ conversation_id: string; user_message: GrokMessage; assistant_message: GrokMessage }>(
      `/api/v1/chat/messages/${messageId}/run-snippet`,
      { method: "POST", body: JSON.stringify({ code }) },
    ),
};

export type JuniorJob = {
  id: string;
  title: string;
  prompt: string;
  cron: string;
  timezone: string;
  conversation_id: string | null;
  shelf: string | null;
  folder_id: string | null;
  include_article_id: string | null;
  model: string;
  reasoning: string;
  xhigh: boolean;
  enabled: boolean;
  last_run_at: string | null;
  last_status: string | null;
  created_at: string | null;
  updated_at: string | null;
};
