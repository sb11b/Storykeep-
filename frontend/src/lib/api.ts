import type {
  Annotation,
  Article,
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
  TtsStatus,
  TtsWord,
  User,
  VaultImportResult,
  ChatStatus,
} from "./types";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
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
    let detail = response.statusText;
    try {
      const data = (await response.json()) as { detail?: string };
      if (typeof data.detail === "string") detail = data.detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  me: () => request<User>("/api/v1/auth/me"),
  login: (email: string, password: string) =>
    request<{ user: User }>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  register: (email: string, password: string, display_name?: string) =>
    request<{ user: User }>("/api/v1/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, display_name }),
    }),
  logout: () => request<{ ok: boolean }>("/api/v1/auth/logout", { method: "POST" }),
  stats: () => request<Stats>("/api/v1/stats"),
  feeds: () => request<Feed[]>("/api/v1/feeds"),
  addFeed: (url: string, category_id?: string | null, title?: string | null) =>
    request<Feed>("/api/v1/feeds", {
      method: "POST",
      body: JSON.stringify({ url, category_id: category_id || null, title: title || null }),
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
  composeVaultNote: (title: string, markdown: string, tags: string[] = []) =>
    request<Article>("/api/v1/sources/obsidian/notes", {
      method: "POST",
      body: JSON.stringify({ title, markdown, tags }),
    }),
  updateComposedNote: (articleId: string, title: string, markdown: string) =>
    request<Article>(`/api/v1/articles/${articleId}/storykeep-note`, {
      method: "PATCH",
      body: JSON.stringify({ title, markdown }),
    }),
  uploadNoteImage: async (file: File) => {
    const body = new FormData();
    body.append("file", file);
    const response = await fetch("/api/v1/media", {
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
    return (await response.json()) as { id: string; url: string; markdown: string; filename: string };
  },
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
  addAddition: (articleId: string, title: string, markdown: string) =>
    request(`/api/v1/articles/${articleId}/additions`, {
      method: "POST",
      body: JSON.stringify({ title, markdown }),
    }),
  addCorrection: (articleId: string, markdown: string) =>
    request(`/api/v1/articles/${articleId}/corrections`, {
      method: "POST",
      body: JSON.stringify({ markdown }),
    }),
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
  categories: () => request<Category[]>("/api/v1/categories"),
  createCategory: (name: string, color?: string) =>
    request<Category>("/api/v1/categories", {
      method: "POST",
      body: JSON.stringify({ name, color }),
    }),
  tags: () => request<Tag[]>("/api/v1/tags"),
  articles: (params: Record<string, string | number | boolean | undefined>) => {
    const search = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== "") search.set(key, String(value));
    }
    return request<Page<Article>>(`/api/v1/articles?${search.toString()}`);
  },
  article: (id: string) => request<Article>(`/api/v1/articles/${id}`),
  patchArticle: (id: string, body: Partial<Pick<Article, "is_read" | "is_saved" | "is_starred">>) =>
    request<Article>(`/api/v1/articles/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  bulkArticles: (ids: string[], body: { is_read?: boolean; is_saved?: boolean }) =>
    request<{ updated: number }>("/api/v1/articles/bulk", {
      method: "POST",
      body: JSON.stringify({ ids, ...body }),
    }),
  markFeedRead: (id: string) =>
    request<{ updated: number }>(`/api/v1/feeds/${id}/mark-read`, { method: "POST" }),
  extract: (id: string) =>
    request<Article>(`/api/v1/articles/${id}/extract`, { method: "POST" }),
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
  notes: () => request<Annotation[]>("/api/v1/annotations"),
  archive: (id: string) =>
    request(`/api/v1/articles/${id}/archive`, {
      method: "POST",
      body: JSON.stringify({ type: "html" }),
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
      body: JSON.stringify({ backup_type, destination: "local" }),
    }),
  tts: () => request<TtsStatus>("/api/v1/tts"),
  ttsPlan: (id: string, voiceId: string) =>
    request<TtsPlan>(`/api/v1/articles/${id}/tts/plan?voice_id=${encodeURIComponent(voiceId)}`),
  releaseTtsAudio: (id: string, voiceId: string) =>
    request<{ ok: boolean }>(`/api/v1/articles/${id}/tts/release?voice_id=${encodeURIComponent(voiceId)}`, {
      method: "POST",
    }),
  chatStatus: () => request<ChatStatus>("/api/v1/chat"),
  streamChat: async (
    body: { messages: { role: "user" | "assistant"; content: string }[]; article_id: string | null; include_article: boolean },
    onDelta: (text: string) => void,
  ) => {
    const response = await fetch("/api/v1/chat", {
      method: "POST",
      credentials: "include",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
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
    if (!response.body) throw new ApiError(502, "Chat stream was empty");
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() || "";
      for (const part of parts) {
        const line = part.split("\n").find((item) => item.startsWith("data:"));
        if (!line) continue;
        const data = line.slice(5).trim();
        if (data === "[DONE]") return;
        try {
          const parsed = JSON.parse(data) as { delta?: string; error?: string };
          if (parsed.error) throw new ApiError(502, parsed.error);
          if (parsed.delta) onDelta(parsed.delta);
        } catch (error) {
          if (error instanceof ApiError) throw error;
        }
      }
    }
  },
  articleSpeech: async (
    id: string,
    voiceId: string,
    chunk = 0,
    opts?: { confirm?: boolean; section?: string | null },
  ) => {
    const search = new URLSearchParams({ voice_id: voiceId, chunk: String(chunk) });
    if (opts?.confirm) search.set("confirm", "true");
    if (opts?.section) search.set("section", opts.section);
    const response = await fetch(`/api/v1/articles/${id}/tts?${search.toString()}`, {
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
    const data = (await response.json()) as {
      audio: string;
      content_type?: string;
      chunks: number;
      word_offset?: number;
      chunk_word_counts?: number[];
      duration?: number | null;
      words?: TtsWord[];
    };
    const binary = Uint8Array.from(atob(data.audio), (char) => char.charCodeAt(0));
    const blob = new Blob([binary], { type: data.content_type || "audio/mpeg" });
    const chunks = Number(data.chunks || 1);
    return {
      blob,
      chunks: Number.isFinite(chunks) && chunks > 0 ? chunks : 1,
      wordOffset: Number(data.word_offset || 0),
      chunkWordCounts: Array.isArray(data.chunk_word_counts) ? data.chunk_word_counts : [],
      duration: data.duration ?? null,
      words: Array.isArray(data.words) ? data.words : [],
    };
  },
};
