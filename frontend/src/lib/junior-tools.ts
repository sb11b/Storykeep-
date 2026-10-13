/**
 * Junior's function tools for Talk mode (xAI realtime speech-to-speech).
 *
 * Tool definitions (the flat `{type: "function", name, description,
 * parameters}` shape) are verified live against xAI realtime: session.update
 * accepts them and the model emits response.function_call_arguments.done
 * events. The function-call loop itself lives in use-conversation-voice.ts;
 * the pure event helpers at the bottom of this file are its unit-tested core.
 *
 * DOM-free: every helper is pure or fetch-based, so it runs under `node --test`.
 */

import { apiUrl, authHeaders } from "@/lib/api-base";

/** One xAI function-tool definition for session.update. */
export interface JuniorToolDef {
  type: "function";
  name: string;
  description: string;
  parameters: {
    type: "object";
    properties: Record<string, unknown>;
    required: string[];
  };
}

/**
 * Read cap for a document read aloud. School texts (textbook chapters, long
 * assigned readings) run 50k–150k+ characters, so this is a long-chapter cap,
 * not an article cap. Content beyond the cap is sliced off with a speakable
 * marker, and get_document takes an `offset` so Junior can fetch the next
 * chunk when Steve says "keep reading".
 */
export const DOC_READ_CHARS = 120_000;

/** Read cap for an attached file (docx/pdf/etc.) read aloud. */
export const FILE_TEXT_CHARS = 30_000;

/** Read cap for one email body. */
export const EMAIL_BODY_CHARS = 8_000;

/** Voice caps for list results — Junior speaks these, so keep them short. */
const MAX_LIST_ITEMS = 8;
const PREVIEW_CHARS = 240;
const SUMMARY_CHARS = 600;

const LIBRARY_UNAVAILABLE = "I couldn't reach your library right now.";
const EMAIL_UNAVAILABLE = "I can't reach your email right now.";
const WORK_UNAVAILABLE = "I couldn't check the work queue right now.";
const DRAFT_FAILED = "I couldn't save that draft right now.";
const TASK_FAILED = "I couldn't queue that task right now.";
const FEEDS_UNAVAILABLE = "I couldn't reach your feeds right now.";
const ARTICLES_UNAVAILABLE = "I couldn't reach your articles right now.";
const DOC_SAVE_FAILED = "I couldn't save that document right now.";
const DOC_DELETE_FAILED = "I couldn't delete that document right now.";

/** Feeds list cap (spec: ~50 entries). */
const MAX_FEED_ITEMS = 50;
/** Article summary cap for search results (spec: ~500 chars). */
const ARTICLE_SUMMARY_CHARS = 500;
/** Default/max articles per search_articles call. */
const ARTICLE_SEARCH_DEFAULT_LIMIT = 20;
const ARTICLE_SEARCH_MAX_LIMIT = 50;
/**
 * The tool set for session.update — web_search (verified in #168) stays; these
 * function tools give Junior Steve's library, pending work, business email,
 * and his RSS feeds (a SEPARATE system from the library: feeds/articles live
 * behind /api/v1/feeds and /api/v1/articles).
 */
export const JUNIOR_TOOLS: readonly JuniorToolDef[] = [
  {
    type: "function",
    name: "search_library",
    description:
      "Search Steve's Storykeep LIBRARY documents — articles, papers, notes, school texts Steve has written or uploaded — and his recorded Junior conversations. Use when Steve asks about his documents, what he has written, or what he has been working on. This is NOT his news feeds: use search_articles for Newsmax/Fox News/Medium and other feeds he follows.",
    parameters: {
      type: "object",
      properties: {
        query: {
          type: "string",
          description:
            "What to search for, in a few words, e.g. 'quantum physics' or 'Meridian launch brief'.",
        },
      },
      required: ["query"],
    },
  },
  {
    type: "function",
    name: "get_document",
    description:
      "Fetch one Storykeep LIBRARY document Steve has written or uploaded (an article, paper, note, or school text) by its slug. Returns the FULL text so Junior can READ IT ALOUD when Steve asks ('read me my quantum physics article'). For long documents the text is capped and you can call again with an increased offset to continue reading where you left off — when Steve says 'continue' or 'keep reading', use the offset where the previous chunk ended. A short summary is included for quick 'what's this about' questions. This is NOT a news feed article — use read_article for articles from his RSS feeds.",
    parameters: {
      type: "object",
      properties: {
        slug: {
          type: "string",
          description: "The document's slug, exactly as returned by search_library (e.g. 'quantum-intro').",
        },
        offset: {
          type: "integer",
          description:
            "Character offset to start reading from. Omit (or 0) to start at the beginning; when Steve says 'continue' or 'keep reading', use the offset where the previous chunk ended.",
        },
      },
      required: ["slug"],
    },
  },
  {
    type: "function",
    name: "read_document_file",
    description:
      "Read the extracted text of a file attached to a Storykeep LIBRARY document (Word .docx, PDF, text, markdown) — documents Steve has written or uploaded. Returns the FULL text so Junior can read it aloud when Steve asks ('read me that Word doc'). Use after search_library or list_document_files when the content lives in an attached file. This is NOT a news feed article — use read_article for articles from his RSS feeds.",
    parameters: {
      type: "object",
      properties: {
        slug: {
          type: "string",
          description: "The document's slug (e.g. 'school-texts').",
        },
        file_id: {
          type: "string",
          description: "The attached file's id, as listed by the document's files.",
        },
      },
      required: ["slug", "file_id"],
    },
  },
  {
    type: "function",
    name: "create_document",
    description:
      "Create or update a document in Steve's Storykeep library — an article, note, text, doc, or file content — at a shelf/folder location. Storykeep has ONE flat document model: SHELVES and FOLDERS are just path segments inside the document's slug (e.g. a doc at shelf 'insurance', folder 'x-drafts' has slug 'insurance-x-drafts-<name>'), so 'create a folder/shelf' means pick the path prefix for a document and the folder exists implicitly. Use when Steve asks Junior to write, save, file, or draft a document ('save this under my insurance drafts', 'create a note about...'). To read a draft back, use get_document. NEVER claim the document was saved before this tool returns — if it fails, say so.",
    parameters: {
      type: "object",
      properties: {
        slug: {
          type: "string",
          description:
            "The document's own short name, e.g. 'term-life-comparison' or 'insurance-x-drafts-term-life-comparison' if you want to give the full slug including the folder. Combined with path when path is given.",
        },
        path: {
          type: "string",
          description:
            "Shelf/folder path prefix, e.g. 'insurance' or 'hermes/work-bot/insurance/x-drafts'. Each segment becomes part of the document's slug, so this is how shelves/folders are created. Omit for a top-level document.",
        },
        title: {
          type: "string",
          description: "The document's title, e.g. 'Term life comparison — 3 quotes'.",
        },
        content: {
          type: "string",
          description: "The full text/markdown body of the document to save.",
        },
      },
      required: ["slug", "title", "content"],
    },
  },
  {
    type: "function",
    name: "delete_document",
    description:
      "Permanently DELETE one document from Steve's Storykeep library by its exact slug (shelves and folders are path segments inside the slug, so the slug identifies the full location). Use ONLY when Steve explicitly asks to delete or remove a specific document — confirm which document he means before calling. NEVER delete a whole shelf/folder. NEVER claim the document was deleted before this tool returns — if it fails, say so.",
    parameters: {
      type: "object",
      properties: {
        slug: {
          type: "string",
          description:
            "The exact slug of the document to delete, e.g. 'insurance-x-drafts-term-life-comparison' — exactly as returned by search_library or create_document.",
        },
      },
      required: ["slug"],
    },
  },
  {
    type: "function",
    name: "list_feeds",
    description:
      "List the RSS feeds Steve is subscribed to (Newsmax, Fox News, Medium, etc.) with their titles. Use when Steve asks about his feeds, subscriptions, or 'what am I following'. These are his NEWS feeds — separate from his Storykeep library documents.",
    parameters: {
      type: "object",
      properties: {},
      required: [],
    },
  },
  {
    type: "function",
    name: "search_articles",
    description:
      "Search the ARTICLES in Steve's RSS feeds (Newsmax, Fox News, Medium, blogs he follows) — headlines, summaries, full text. This is Steve's news reading, separate from his Storykeep library documents. Use when Steve asks about news, his feeds, articles he's reading or has saved.",
    parameters: {
      type: "object",
      properties: {
        query: {
          type: "string",
          description:
            "Free-text search across article title, summary, and content, e.g. 'Supreme Court' or 'Meridian launch'. Omit to just list the newest articles.",
        },
        feed: {
          type: "string",
          description:
            "Feed TITLE to search only inside one feed, e.g. 'Newsmax' or 'Fox News' — exactly as returned by list_feeds. Omit to search all feeds.",
        },
        saved_only: {
          type: "boolean",
          description: "Only articles Steve has saved (default false).",
        },
        limit: {
          type: "integer",
          description: `How many articles to list (1–${ARTICLE_SEARCH_MAX_LIMIT}, default ${ARTICLE_SEARCH_DEFAULT_LIMIT}).`,
        },
      },
      required: [],
    },
  },
  {
    type: "function",
    name: "read_article",
    description:
      "Read the full extracted text of a feed article by its id (from search_articles or a list of articles in a feed). Returns the full text so Junior can read it aloud when Steve asks ('read me that Newsmax article'). For long articles the text is capped and you can call again with an increased offset to continue reading where you left off — when Steve says 'continue' or 'keep reading', use the offset where the previous chunk ended.",
    parameters: {
      type: "object",
      properties: {
        id: {
          type: "string",
          description: "The article's id, exactly as returned by search_articles or list_feeds results.",
        },
        offset: {
          type: "integer",
          description:
            "Character offset to start reading from. Omit (or 0) to start at the beginning; when Steve says 'continue' or 'keep reading', use the offset where the previous chunk ended.",
        },
      },
      required: ["id"],
    },
  },
  {
    type: "function",
    name: "list_pending_work",
    description:
      "List what is waiting for Steve: pending tasks in the Hermes work channel — documents coming in and approvals going out. Use when Steve asks what's pending, what needs his attention, or what's waiting on approvals.",
    parameters: {
      type: "object",
      properties: {},
      required: [],
    },
  },
  {
    type: "function",
    name: "create_task",
    description:
      "Dispatch work to the Hermes team through the task channel — e.g. when Steve tells Junior to do something for productivity ('remind me to…', 'have Hermes draft…', 'queue a summary of…'). Use only when Steve asks for work to be queued or done.",
    parameters: {
      type: "object",
      properties: {
        kind: {
          type: "string",
          description: "Short snake_case label for the work, e.g. 'hermes_work', 'approval', 'research', 'reminder'.",
        },
        title: {
          type: "string",
          description: "One-line title of the task.",
        },
        instructions: {
          type: "string",
          description: "Full instructions for the work, in Steve's own words as much as possible.",
        },
      },
      required: ["kind", "title", "instructions"],
    },
  },
  {
    type: "function",
    name: "read_email",
    description:
      "Read Steve's business email inbox (thebitskogroup@fastmail.com): recent messages with sender, subject, and preview. Use when Steve asks what's in his inbox or about new email.",
    parameters: {
      type: "object",
      properties: {
        limit: {
          type: "integer",
          description: "How many messages to list (1–50, default 10).",
        },
        folder: {
          type: "string",
          description: "Mailbox role to read, e.g. 'inbox' or 'archive' (default inbox).",
        },
        unread_only: {
          type: "boolean",
          description: "Only unread messages (default false).",
        },
      },
      required: [],
    },
  },
  {
    type: "function",
    name: "search_email",
    description:
      "Search Steve's business email by sender, subject, or body text. Use when Steve asks about email from someone or about a topic ('anything from Jennifer about the invoice').",
    parameters: {
      type: "object",
      properties: {
        query: {
          type: "string",
          description: "What to search for in email, e.g. 'Jennifer' or 'invoice'.",
        },
      },
      required: ["query"],
    },
  },
  {
    type: "function",
    name: "read_email_message",
    description:
      "Fetch one email by its id. Returns the FULL body so Junior can READ IT ALOUD when Steve asks ('read me that email from Jennifer').",
    parameters: {
      type: "object",
      properties: {
        message_id: {
          type: "string",
          description: "The email's id, exactly as returned by read_email or search_email.",
        },
      },
      required: ["message_id"],
    },
  },
  {
    type: "function",
    name: "draft_email",
    description:
      "Creates a draft in Steve's Fastmail Drafts folder from the business identity. NEVER claims or implies the email was sent — after creating a draft, tell Steve it's saved as a draft for him to review and send himself in Fastmail. Use when Steve asks Junior to write or reply to an email.",
    parameters: {
      type: "object",
      properties: {
        to: {
          type: "string",
          description: "Recipient email address.",
        },
        subject: {
          type: "string",
          description: "Subject line for the draft.",
        },
        body: {
          type: "string",
          description: "The full message body.",
        },
        reply_to: {
          type: "string",
          description:
            "Message id of the email being replied to — threads the draft onto the original. Omit for a new email.",
        },
      },
      required: ["to", "subject", "body"],
    },
  },
  {
    type: "function",
    name: "list_drafts",
    description:
      "List the drafts waiting in Steve's Fastmail Drafts folder. Use when Steve asks what drafts are saved or what he still needs to review and send.",
    parameters: {
      type: "object",
      properties: {},
      required: [],
    },
  },
];

/* ────────────────────────────────────────────────────────────────────────────
 * Pure helpers — unit-tested in junior-tools.test.ts.
 * ──────────────────────────────────────────────────────────────────────────── */

/** Parse a tool-call arguments payload (JSON string or object) → arg object. */
export function parseToolArguments(raw: unknown): Record<string, unknown> {
  if (raw && typeof raw === "object" && !Array.isArray(raw)) return raw as Record<string, unknown>;
  if (typeof raw !== "string" || !raw.trim()) return {};
  try {
    const parsed: unknown = JSON.parse(raw);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : {};
  } catch {
    return {};
  }
}

/** Required string arg — trimmed, or null when missing/blank/non-string. */
export function requiredStringArg(args: Record<string, unknown>, name: string): string | null {
  const value = args[name];
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

/** Optional non-negative integer arg. */
export function optionalIntArg(args: Record<string, unknown>, name: string): number | null {
  const value = args[name];
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  return Math.max(0, Math.floor(value));
}

/**
 * Slice long content for a read-aloud chunk: text[offset : offset + cap].
 * Pure — the round-trip property (chunks concatenate back to the original)
 * is unit-tested.
 */
export function sliceReadChunk(text: string, offset: number, cap: number): string {
  if (!text) return "";
  const start = Math.max(0, Math.min(offset, text.length));
  return text.slice(start, start + cap);
}

/**
 * Speakable truncation marker for a chunked read: tells Junior (and Steve)
 * the content continues and where to pick up.
 */
export function excerptMarker(shown: number, total: number): string {
  return `[excerpt — first ${shown.toLocaleString("en-US")} of ${total.toLocaleString("en-US")} characters; ask me to continue from where I stopped]`;
}

/**
 * Speakable truncation marker for a chunked read, positioned cumulatively:
 * `offset` is where this chunk started, so `offset + chunk.length` is the
 * character the read has reached — "first 240,000 of 300,000", not
 * "first 120,000 of 300,000" for a continuation chunk.
 */
export function chunkExcerptMarker(offset: number, chunkLength: number, total: number): string {
  return excerptMarker(offset + chunkLength, total);
}

/** Format one document read chunk (title + optional summary + capped text). */
export function formatDocumentRead(
  doc: { title?: string; slug?: string; text?: string; summary?: string | null },
  offset = 0,
): string {
  const text = doc.text ?? "";
  const chunk = sliceReadChunk(text, offset, DOC_READ_CHARS);
  const parts = [`"${doc.title ?? doc.slug ?? "document"}"${doc.slug ? ` (slug: ${doc.slug})` : ""}.`];
  if (offset === 0 && doc.summary?.trim()) {
    parts.push(`Summary: ${doc.summary.trim().slice(0, SUMMARY_CHARS)}`);
  }
  if (chunk) {
    parts.push(`Text: ${chunk}`);
    if (offset + chunk.length < text.length) {
      parts.push(chunkExcerptMarker(offset, chunk.length, text.length));
    }
  } else if (!text) {
    parts.push("This document has no text.");
  }
  return parts.join(" ");
}

/** Format document search matches (title + slug + short summary). */
export function formatDocumentMatches(docs: Array<{ title?: string; slug?: string; summary?: string | null }>): string {
  if (!docs.length) return "";
  const lines = docs.slice(0, MAX_LIST_ITEMS).map((doc) => {
    const summary = doc.summary?.trim();
    return `"${doc.title ?? doc.slug ?? "document"}" (slug: ${doc.slug ?? "?"})${
      summary ? ` — ${summary.slice(0, PREVIEW_CHARS)}` : ""
    }`;
  });
  return `Found ${docs.length === 1 ? "1 document" : `${docs.length} documents`}: ${lines.join("; ")}.`;
}

/** Format the subscribed-feeds list for voice (title + url, truncated). */
export function formatFeedList(
  feeds: Array<{ id?: string; title?: string | null; url?: string; description?: string | null; is_active?: boolean; last_error?: string | null }>,
): string {
  if (!feeds.length) return "You're not subscribed to any feeds yet.";
  const shown = feeds.slice(0, MAX_FEED_ITEMS);
  const lines = shown.map((feed) => {
    const title = feed.title?.trim() || feed.url || "untitled feed";
    const url = feed.url?.trim();
    const desc = feed.description?.trim();
    const parts = [`"${title}"`];
    if (url) parts.push(`(${url})`);
    if (desc) parts.push(`— ${desc.slice(0, PREVIEW_CHARS)}`);
    if (feed.is_active === false) parts.push("[paused]");
    if (feed.last_error?.trim()) parts.push("[last refresh failed]");
    return parts.join(" ");
  });
  // Report the count actually shown — saying "You follow 200 feeds" and then
  // listing 50 tells the model about feeds it cannot see.
  return `You follow ${shown.length} feed${shown.length === 1 ? "" : "s"}: ${lines.join("; ")}.`;
}

/** Format article search matches for voice (title, feed, summary). */
export function formatArticleMatches(
  articles: Array<{
    id?: string;
    title?: string;
    feed_title?: string | null;
    url?: string;
    published_at?: string | null;
    summary?: string | null;
    is_saved?: boolean;
    is_read?: boolean;
  }>,
): string {
  if (!articles.length) return "No articles found in your feeds.";
  const shown = articles.slice(0, MAX_LIST_ITEMS);
  const lines = shown.map((article) => {
    const title = article.title?.trim() || "untitled";
    const feed = article.feed_title?.trim();
    const summary = article.summary?.trim();
    const flags = [article.is_saved ? "saved" : null, article.is_read ? "read" : null].filter(Boolean);
    const parts = [`"${title}"`];
    if (feed) parts.push(`from ${feed}`);
    if (summary) parts.push(`— ${summary.slice(0, ARTICLE_SUMMARY_CHARS)}`);
    if (flags.length) parts.push(`[${flags.join(", ")}]`);
    if (article.id) parts.push(`(id: ${article.id})`);
    return parts.join(" ");
  });
  // Report the count actually shown: "Found 8 of 20 articles" when the cap
  // trims the list, so the model never cites articles it cannot see.
  const count =
    shown.length === articles.length
      ? `Found ${articles.length} article${articles.length === 1 ? "" : "s"}`
      : `Found ${shown.length} of ${articles.length} articles`;
  return `${count} in your feeds: ${lines.join("; ")}.`;
}

/** Format one feed-article read chunk — mirrors formatDocumentRead's continuation. */
export function formatArticleRead(
  article: {
    id?: string;
    title?: string;
    feed_title?: string | null;
    url?: string;
    published_at?: string | null;
    summary?: string | null;
    content_text?: string | null;
  },
  offset = 0,
): string {
  const text = article.content_text ?? "";
  const chunk = sliceReadChunk(text, offset, DOC_READ_CHARS);
  const parts = [`"${article.title?.trim() || "article"}"${article.id ? ` (id: ${article.id})` : ""}`];
  if (article.feed_title?.trim()) parts.push(`from ${article.feed_title.trim()}`);
  if (article.url?.trim()) parts.push(`(${article.url.trim()})`);
  parts.push(".");
  if (offset === 0 && article.summary?.trim()) {
    parts.push(`Summary: ${article.summary.trim().slice(0, SUMMARY_CHARS)}`);
  }
  if (chunk) {
    parts.push(`Text: ${chunk}`);
    if (offset + chunk.length < text.length) {
      parts.push(chunkExcerptMarker(offset, chunk.length, text.length));
    }
  } else if (!text) {
    parts.push("That article has no extracted text yet.");
  }
  return parts.join(" ");
}

/** Lowercase query tokens (>= 3 chars) for client-side document matching. */
export function queryTokens(query: string): string[] {
  return query.toLowerCase().split(/[^a-z0-9]+/).filter((token) => token.length >= 3);
}

/** True when any query token appears in the document's title or summary. */
export function documentMatchesQuery(
  doc: { title?: string; summary?: string | null },
  tokens: string[],
): boolean {
  if (!tokens.length) return true;
  const haystack = `${doc.title ?? ""} ${doc.summary ?? ""}`.toLowerCase();
  return tokens.some((token) => haystack.includes(token));
}

/** Format pending tasks for voice. */
export function formatPendingTasks(tasks: Array<{ kind?: string; title?: string; status?: string; payload?: Record<string, unknown> | null }>): string {
  if (!tasks.length) return "Nothing is pending — your queue is clear.";
  const lines = tasks.slice(0, MAX_LIST_ITEMS).map((task) => {
    const docSlug =
      task.payload && typeof task.payload.doc_slug === "string" ? task.payload.doc_slug : null;
    const extra = docSlug ? ` (document: ${docSlug})` : "";
    return `${task.kind ?? "task"} — "${task.title ?? "untitled"}"${extra} [${task.status ?? "open"}]`;
  });
  return `${tasks.length} thing${tasks.length === 1 ? "" : "s"} waiting: ${lines.join("; ")}.`;
}

/** Format a created task for voice. */
export function formatCreatedTask(task: { kind?: string; title?: string }): string {
  return `Queued it as a ${task.kind ?? "task"} task: "${task.title ?? "untitled"}". It's waiting for pickup now.`;
}

/** Format an email list for voice. */
export function formatEmailList(items: Array<{ from_address?: string; subject?: string; unread?: boolean; preview?: string }>): string {
  if (!items.length) return "No email found.";
  const lines = items.slice(0, MAX_LIST_ITEMS).map((item) => {
    const flag = item.unread ? "unread, " : "";
    const preview = item.preview?.trim();
    return `${flag}from ${item.from_address || "unknown"} — "${item.subject || "(no subject)"}"${preview ? `: ${preview.slice(0, PREVIEW_CHARS)}` : ""}`;
  });
  return `${items.length === 1 ? "1 email" : `${items.length} emails`}: ${lines.join("; ")}.`;
}

/** Format one email body for reading aloud (capped, marked when truncated). */
export function formatEmailBody(body: { from_address?: string; subject?: string; date?: string; body?: string; excerpt?: boolean }): string {
  const text = body.body ?? "";
  const parts = [`From ${body.from_address || "unknown"}, "${body.subject || "(no subject)"}"${body.date ? `, ${body.date}` : ""}.`];
  parts.push(`Body: ${text}`);
  if (body.excerpt) parts.push(excerptMarker(text.length, text.length));
  return parts.join(" ");
}

/** Format a created draft — the never-send reminder is part of the result. */
export function formatDraftSaved(draft: { to?: string; subject?: string }): string {
  return `Draft saved in Fastmail for ${draft.to || "the recipient"} about "${draft.subject || "(no subject)".trim()}". It is NOT sent — open Fastmail to review and send it yourself.`;
}

/**
 * Build a document slug from a shelf/folder path prefix and the document's
 * own name, mirroring sk-push's slug convention: the path segments and the
 * name are joined with '-' and slugified (lowercase, non-alphanumerics
 * collapsed to '-'). A path already containing the full slug (name included)
 * still resolves correctly: a trailing segment equal to the slug's own name
 * is not duplicated. Slugs over 64 chars carry a short hash suffix so
 * distinct long names never collide (same trick as sk-push).
 */
export function documentSlugFromPath(path: string | null, slug: string): string {
  const parts = (path ?? "")
    .split("/")
    .map((part) => slugifySegment(part))
    .filter(Boolean);
  const name = slugifySegment(slug);
  if (!name) return "";
  const full = [...(parts[parts.length - 1] === name ? parts.slice(0, -1) : parts), name];
  const joined = full.filter(Boolean).join("-");
  if (joined.length <= 64) return joined;
  const head = joined.slice(0, 57).replace(/-+$/, "");
  let hash = 0;
  for (const char of joined) hash = (Math.imul(hash, 31) + char.charCodeAt(0)) | 0;
  return `${head}-${(hash >>> 0).toString(16).padStart(8, "0").slice(0, 6)}`;
}

function slugifySegment(segment: string): string {
  return segment
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

/** Format a created/updated document for voice — shelf path included. */
export function formatDocumentSaved(doc: { slug?: string; title?: string }): string {
  return `Saved "${doc.title || "your document"}" in your library (slug: ${doc.slug ?? "unknown"}). I can read it back whenever you want.`;
}

/** Format a deleted document for voice — confirms exactly what was deleted. */
export function formatDocumentDeleted(slug: string): string {
  return `Deleted "${slug}" from your library.`;
}

/** Format an attached file's extracted text for reading aloud. */
export function formatFileText(file: { filename?: string; text?: string; excerpt?: boolean }): string {
  const text = file.text ?? "";
  const parts = [`File "${file.filename ?? "attachment"}".`];
  if (text) {
    parts.push(`Text: ${text}`);
    if (file.excerpt) parts.push(excerptMarker(text.length, text.length));
  } else {
    parts.push("That file has no readable text.");
  }
  return parts.join(" ");
}

/* ────────────────────────────────────────────────────────────────────────────
 * Event helpers for the function-call loop (pure — unit-tested).
 * ──────────────────────────────────────────────────────────────────────────── */

export interface JuniorFunctionCall {
  call_id: string;
  name: string;
  arguments: string;
}

function pickFunctionCall(callId: unknown, name: unknown, args: unknown): JuniorFunctionCall | null {
  // Only completed calls: the live stream sends partial `delta` events and
  // in-progress items with empty `arguments` — both must be ignored.
  if (typeof callId !== "string" || !callId) return null;
  if (typeof args !== "string" || !args) return null;
  return { call_id: callId, name: typeof name === "string" ? name : "", arguments: args };
}

/**
 * Extract a completed function call from a realtime event. Live-verified
 * shapes: response.function_call_arguments.done (call fields at top level)
 * and response.output_item.done / conversation.item.done (call fields inside
 * item). Returns null for deltas, in-progress items, and plain messages.
 */
export function extractFunctionCall(msg: unknown): JuniorFunctionCall | null {
  if (!msg || typeof msg !== "object") return null;
  const m = msg as Record<string, unknown>;
  const top = pickFunctionCall(m.call_id, m.name, m.arguments);
  if (top && top.name) return top;
  const item = m.item as { type?: unknown; call_id?: unknown; name?: unknown; arguments?: unknown } | undefined;
  if (item?.type === "function_call") {
    return pickFunctionCall(item.call_id, item.name, item.arguments);
  }
  return null;
}

/** The conversation.item.create payload that returns a tool result to xAI. */
export function buildFunctionCallOutput(callId: string, output: string) {
  return {
    type: "conversation.item.create",
    item: { type: "function_call_output", call_id: callId, output },
  };
}

/** The response.create payload that makes Junior speak the tool answer. */
export function buildResponseCreate() {
  return { type: "response.create" };
}

/* ────────────────────────────────────────────────────────────────────────────
 * Client handlers — call the Storykeep junior API, map to speakable strings.
 * Every handler returns a string and NEVER throws into the socket.
 * ──────────────────────────────────────────────────────────────────────────── */

const TOOL_TIMEOUT_MS = 15_000;

async function toolFetch(path: string, init?: RequestInit): Promise<Response> {
  const headers = new Headers(init?.headers);
  // Desktop app: the SameSite=Lax cookie is not sent cross-site from
  // tauri.localhost, so attach the login access_token as a bearer header —
  // the same fix request() in api.ts carries. The backend checks the header
  // first (backend/app/deps.py) and falls back to the cookie, so the web app
  // (AUTH_TOKEN unset) is unaffected. An explicit header on the caller's
  // init always wins over the derived one.
  for (const [name, value] of Object.entries(authHeaders())) {
    if (!headers.has(name)) headers.set(name, value);
  }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TOOL_TIMEOUT_MS);
  try {
    // apiUrl resolves the app-relative path against the configured API origin
    // (a no-op in dev, where next.config.ts proxies /api/* to the backend).
    // Without it a packaged window fetches the raw path against tauri.localhost
    // and every Junior tool call 404s.
    return await fetch(apiUrl(path), {
      ...init,
      headers,
      credentials: "include",
      cache: "no-store",
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timer);
  }
}

async function toolJson(path: string, init?: RequestInit): Promise<{ ok: boolean; status: number; data: unknown }> {
  const response = await toolFetch(path, init);
  if (!response.ok) return { ok: false, status: response.status, data: null };
  try {
    return { ok: true, status: response.status, data: await response.json() };
  } catch {
    return { ok: false, status: response.status, data: null };
  }
}

interface JuniorDocumentRow {
  slug?: string;
  title?: string;
  text?: string;
  summary?: string | null;
}

interface JuniorTaskRow {
  id?: string;
  kind?: string;
  title?: string;
  detail?: string;
  status?: string;
  payload?: Record<string, unknown> | null;
}

interface JuniorEmailRow {
  id?: string;
  from_address?: string;
  to?: string;
  subject?: string;
  date?: string;
  preview?: string;
  unread?: boolean;
}

interface JuniorEmailBodyRow extends JuniorEmailRow {
  cc?: string;
  body?: string;
  excerpt?: boolean;
}

async function searchLibrary(args: Record<string, unknown>): Promise<string> {
  const query = requiredStringArg(args, "query");
  if (!query) return "Tell me what to search for in your library.";
  try {
    const [hits, docs] = await Promise.all([
      toolJson(`/api/v1/junior/search?q=${encodeURIComponent(query)}&limit=25`),
      toolJson("/api/v1/junior/documents?limit=100"),
    ]);
    if (!hits.ok || !docs.ok) return LIBRARY_UNAVAILABLE;
    const tokens = queryTokens(query);
    const matched = ((docs.data as JuniorDocumentRow[] | null) ?? []).filter((doc) =>
      documentMatchesQuery(doc, tokens),
    );
    const docPart = formatDocumentMatches(matched);
    const hitRows = ((hits.data as Array<{ thread_title?: string; snippet?: string }> | null) ?? []).slice(0, 5);
    const hitPart = hitRows
      .map((hit) => {
        const where = hit.thread_title?.trim();
        const snippet = (hit.snippet ?? "").trim().slice(0, PREVIEW_CHARS);
        return where ? `In "${where}": ${snippet}` : snippet;
      })
      .filter(Boolean)
      .join(" ");
    if (!docPart && !hitPart) return `Nothing in your library matches "${query}".`;
    if (!hitPart) return docPart;
    if (!docPart) return `In your past conversations: ${hitPart}`;
    return `${docPart} Also in your past conversations: ${hitPart}`;
  } catch {
    return LIBRARY_UNAVAILABLE;
  }
}

async function getDocument(args: Record<string, unknown>): Promise<string> {
  const slug = requiredStringArg(args, "slug");
  if (!slug) return "Which document should I pull up?";
  const offset = optionalIntArg(args, "offset") ?? 0;
  try {
    const doc = await toolJson(`/api/v1/junior/documents/${encodeURIComponent(slug)}`);
    if (!doc.ok) return `I couldn't find a document called "${slug}" in your library.`;
    return formatDocumentRead(doc.data as JuniorDocumentRow, offset);
  } catch {
    return LIBRARY_UNAVAILABLE;
  }
}

async function readDocumentFile(args: Record<string, unknown>): Promise<string> {
  const slug = requiredStringArg(args, "slug");
  const fileId = requiredStringArg(args, "file_id");
  if (!slug || !fileId) return "Which document and file should I read?";
  try {
    const file = (await toolJson(
      `/api/v1/junior/documents/${encodeURIComponent(slug)}/files/${encodeURIComponent(fileId)}/text`,
    )) as { ok: boolean; data: unknown };
    if (!file.ok) return `I couldn't read that file.`;
    return formatFileText(file.data as { filename?: string; text?: string; excerpt?: boolean });
  } catch {
    return LIBRARY_UNAVAILABLE;
  }
}

/**
 * Create or update a library document (POST /documents — the existing
 * create_or_update_document route). The shelf/folder `path` is folded into
 * the slug: Storykeep has one flat document model where folders are slug
 * path segments (see documentSlugFromPath). Never claims success before the
 * API confirms.
 */
async function createDocument(args: Record<string, unknown>): Promise<string> {
  const slug = requiredStringArg(args, "slug");
  const title = requiredStringArg(args, "title");
  const content = requiredStringArg(args, "content");
  const path = requiredStringArg(args, "path");
  if (!slug) return "What should I call the document?";
  if (!title) return "What's the title?";
  if (content == null) return "What should the document say?";
  const fullSlug = documentSlugFromPath(path, slug);
  if (!fullSlug) return "What should I call the document?";
  if (fullSlug.length > 64) return "That document name is too long — try a shorter one.";
  try {
    const saved = (await toolJson("/api/v1/junior/documents", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slug: fullSlug, title: title.slice(0, 120), text: content.slice(0, 32_000) }),
    }));
    if (!saved.ok) return DOC_SAVE_FAILED;
    // Confirm from the API's own echo of the saved row, not the request.
    const row = saved.data as JuniorDocumentRow | null;
    return formatDocumentSaved({ slug: row?.slug ?? fullSlug, title: row?.title ?? title });
  } catch {
    return DOC_SAVE_FAILED;
  }
}

/**
 * Delete one library document by exact slug (DELETE /documents/{slug} — the
 * existing delete_document route). Destructive: the handler only runs with an
 * explicit slug, and the confirmation names exactly what was deleted.
 */
async function deleteDocument(args: Record<string, unknown>): Promise<string> {
  const slug = requiredStringArg(args, "slug");
  if (!slug) return "Which document should I delete? Give me its exact name.";
  try {
    const res = await toolFetch(`/api/v1/junior/documents/${encodeURIComponent(slug)}`, {
      method: "DELETE",
    });
    if (!res.ok) {
      return res.status === 404
        ? `I couldn't find a document called "${slug}" in your library.`
        : DOC_DELETE_FAILED;
    }
    return formatDocumentDeleted(slug);
  } catch {
    return DOC_DELETE_FAILED;
  }
}

interface JuniorFeedRow {
  id?: string;
  title?: string | null;
  url?: string;
  description?: string | null;
  is_active?: boolean;
  last_error?: string | null;
}

interface JuniorArticleRow {
  id?: string;
  title?: string;
  feed_title?: string | null;
  url?: string;
  published_at?: string | null;
  summary?: string | null;
  content_text?: string | null;
  is_read?: boolean;
  is_saved?: boolean;
}

/** Fetch the feed list once — shared by list_feeds and feed-title resolution. */
async function fetchFeeds(): Promise<{ ok: boolean; rows: JuniorFeedRow[] }> {
  const res = await toolJson("/api/v1/feeds");
  return { ok: res.ok, rows: ((res.data as JuniorFeedRow[] | null) ?? []) };
}

/** Resolve a feed TITLE (as the model types it) to a feed id, case-insensitively. */
function matchFeedId(feeds: JuniorFeedRow[], feedTitle: string): string | null {
  const wanted = feedTitle.trim().toLowerCase();
  if (!wanted) return null;
  const exact = feeds.find((feed) => (feed.title ?? "").trim().toLowerCase() === wanted);
  if (exact?.id) return exact.id;
  const partial = feeds.find((feed) => (feed.title ?? "").toLowerCase().includes(wanted));
  return partial?.id ?? null;
}

async function listFeeds(): Promise<string> {
  try {
    const { ok, rows } = await fetchFeeds();
    if (!ok) return FEEDS_UNAVAILABLE;
    return formatFeedList(rows);
  } catch {
    return FEEDS_UNAVAILABLE;
  }
}

async function searchArticles(args: Record<string, unknown>): Promise<string> {
  const query = requiredStringArg(args, "query");
  const feed = requiredStringArg(args, "feed");
  const savedOnly = args.saved_only === true;
  const limit = optionalIntArg(args, "limit");
  try {
    // The feed param is a TITLE — resolve it to a feed_id via the feeds list.
    let feedId: string | null = null;
    if (feed) {
      const { ok, rows } = await fetchFeeds();
      if (!ok) return FEEDS_UNAVAILABLE;
      feedId = matchFeedId(rows, feed);
      if (!feedId) return `You don't have a feed called "${feed}".`;
    }
    const params = new URLSearchParams({
      limit: String(limit ? Math.min(Math.max(limit, 1), ARTICLE_SEARCH_MAX_LIMIT) : ARTICLE_SEARCH_DEFAULT_LIMIT),
      sort: "published_desc",
    });
    if (query) params.set("q", query);
    if (feedId) params.set("feed_id", feedId);
    if (savedOnly) params.set("saved", "true");
    const res = await toolJson(`/api/v1/articles?${params.toString()}`);
    if (!res.ok) return ARTICLES_UNAVAILABLE;
    // The route returns a Page envelope: { items, total, limit, offset }.
    const page = res.data as { items?: JuniorArticleRow[] | null } | null;
    const rows = page?.items ?? (Array.isArray(res.data) ? (res.data as JuniorArticleRow[]) : []);
    return formatArticleMatches(rows);
  } catch {
    return ARTICLES_UNAVAILABLE;
  }
}

async function readArticle(args: Record<string, unknown>): Promise<string> {
  const id = requiredStringArg(args, "id");
  if (!id) return "Which article should I read?";
  const offset = optionalIntArg(args, "offset") ?? 0;
  try {
    const res = await toolJson(`/api/v1/articles/${encodeURIComponent(id)}`);
    if (!res.ok) {
      // 404 means the id is wrong; anything else (500, network) is the backend.
      return res.status === 404 ? `I couldn't find an article with that id.` : ARTICLES_UNAVAILABLE;
    }
    return formatArticleRead(res.data as JuniorArticleRow, offset);
  } catch {
    return ARTICLES_UNAVAILABLE;
  }
}

async function listPendingWork(): Promise<string> {
  try {
    const [open, claimed] = await Promise.all([
      toolJson("/api/v1/junior/tasks?status=open&limit=25"),
      toolJson("/api/v1/junior/tasks?status=claimed&limit=25"),
    ]);
    if (!open.ok || !claimed.ok) return WORK_UNAVAILABLE;
    const seen = new Set<string>();
    const merged: JuniorTaskRow[] = [];
    for (const task of [
      ...((claimed.data as JuniorTaskRow[] | null) ?? []),
      ...((open.data as JuniorTaskRow[] | null) ?? []),
    ]) {
      if (!task?.id || seen.has(task.id)) continue;
      seen.add(task.id);
      merged.push(task);
    }
    return formatPendingTasks(merged);
  } catch {
    return WORK_UNAVAILABLE;
  }
}

async function createTask(args: Record<string, unknown>): Promise<string> {
  const kind = requiredStringArg(args, "kind");
  const title = requiredStringArg(args, "title");
  const instructions = requiredStringArg(args, "instructions");
  if (!kind) return "What kind of work is this?";
  if (!title) return "What should the task be called?";
  if (!instructions) return "What exactly should the Hermes team do?";
  try {
    const task = (await toolJson("/api/v1/junior/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind, title, detail: instructions, payload: { source: "junior-voice" } }),
    }));
    if (!task.ok) return TASK_FAILED;
    return formatCreatedTask(task.data as JuniorTaskRow);
  } catch {
    return TASK_FAILED;
  }
}

async function readEmail(args: Record<string, unknown>): Promise<string> {
  const limit = optionalIntArg(args, "limit");
  const folder = requiredStringArg(args, "folder") ?? "inbox";
  const unreadOnly = args.unread_only === true;
  const params = new URLSearchParams({
    limit: String(limit ? Math.min(Math.max(limit, 1), 50) : 10),
    folder,
    unread_only: String(unreadOnly),
  });
  try {
    const items = (await toolJson(`/api/v1/junior/email/inbox?${params.toString()}`));
    if (!items.ok) return EMAIL_UNAVAILABLE;
    return formatEmailList(items.data as JuniorEmailRow[]);
  } catch {
    return EMAIL_UNAVAILABLE;
  }
}

async function searchEmail(args: Record<string, unknown>): Promise<string> {
  const query = requiredStringArg(args, "query");
  if (!query) return "What should I search your email for?";
  try {
    const items = (await toolJson(
      `/api/v1/junior/email/search?q=${encodeURIComponent(query)}&limit=10`,
    ));
    if (!items.ok) return EMAIL_UNAVAILABLE;
    if (!(items.data as JuniorEmailRow[])?.length) return `No email matches "${query}".`;
    return formatEmailList(items.data as JuniorEmailRow[]);
  } catch {
    return EMAIL_UNAVAILABLE;
  }
}

async function readEmailMessage(args: Record<string, unknown>): Promise<string> {
  const messageId = requiredStringArg(args, "message_id");
  if (!messageId) return "Which email should I read?";
  try {
    const body = (await toolJson(
      `/api/v1/junior/email/message/${encodeURIComponent(messageId)}`,
    ));
    if (!body.ok) return `I couldn't find that email.`;
    return formatEmailBody(body.data as JuniorEmailBodyRow);
  } catch {
    return EMAIL_UNAVAILABLE;
  }
}

async function draftEmail(args: Record<string, unknown>): Promise<string> {
  const to = requiredStringArg(args, "to");
  const subject = requiredStringArg(args, "subject") ?? "";
  const body = requiredStringArg(args, "body");
  const replyTo = requiredStringArg(args, "reply_to");
  if (!to) return "Who should the draft go to?";
  if (!body) return "What should the draft say?";
  try {
    const draft = (await toolJson("/api/v1/junior/email/draft", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        to,
        subject,
        body,
        ...(replyTo ? { reply_to_message_id: replyTo } : {}),
      }),
    }));
    if (!draft.ok) return DRAFT_FAILED;
    return formatDraftSaved(draft.data as { to?: string; subject?: string });
  } catch {
    return DRAFT_FAILED;
  }
}

async function listDrafts(): Promise<string> {
  try {
    const items = (await toolJson("/api/v1/junior/email/drafts?limit=10"));
    if (!items.ok) return EMAIL_UNAVAILABLE;
    const rows = items.data as JuniorEmailRow[];
    if (!rows?.length) return "No drafts waiting — your Drafts folder is empty.";
    return `Drafts waiting: ${formatEmailList(rows)}`;
  } catch {
    return EMAIL_UNAVAILABLE;
  }
}

const HANDLERS: Record<string, (args: Record<string, unknown>) => Promise<string>> = {
  search_library: searchLibrary,
  get_document: getDocument,
  read_document_file: readDocumentFile,
  create_document: createDocument,
  delete_document: deleteDocument,
  list_feeds: listFeeds,
  search_articles: searchArticles,
  read_article: readArticle,
  list_pending_work: listPendingWork,
  create_task: createTask,
  read_email: readEmail,
  search_email: searchEmail,
  read_email_message: readEmailMessage,
  draft_email: draftEmail,
  list_drafts: listDrafts,
};

export const JUNIOR_TOOL_NAMES: readonly string[] = Object.keys(HANDLERS);

/**
 * Run one tool call: dispatch by name, never throw. The result string is what
 * xAI sends back as the function_call_output and Junior speaks from.
 */
export async function runJuniorTool(name: string, argsJson: unknown): Promise<string> {
  const handler = HANDLERS[name];
  if (!handler) return `I don't have a tool called ${name}.`;
  try {
    return await handler(parseToolArguments(argsJson));
  } catch {
    return "Something went wrong running that.";
  }
}
