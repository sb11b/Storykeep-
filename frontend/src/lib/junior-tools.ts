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

/**
 * The tool set for session.update — web_search (verified in #168) stays; these
 * function tools give Junior Steve's library, pending work, and business email.
 */
export const JUNIOR_TOOLS: readonly JuniorToolDef[] = [
  {
    type: "function",
    name: "search_library",
    description:
      "Search Steve's Storykeep library — his articles, papers, notes, and school texts — and his recorded Junior conversations. Use when Steve asks about his documents, what he has written, or what he has been working on.",
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
      "Fetch one document from Steve's library by its slug. Returns the FULL text so Junior can READ IT ALOUD when Steve asks ('read me my quantum physics article'). For long documents the text is capped and you can call again with an increased offset to continue reading where you left off — when Steve says 'continue' or 'keep reading', use the offset where the previous chunk ended. A short summary is included for quick 'what's this about' questions.",
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
            "Character offset to start reading from. Omit (or 0) to start at the beginning; pass the length of the previous chunk to continue a long read.",
        },
      },
      required: ["slug"],
    },
  },
  {
    type: "function",
    name: "read_document_file",
    description:
      "Read the extracted text of a file attached to a document (Word .docx, PDF, text, markdown). Returns the FULL text so Junior can read it aloud when Steve asks ('read me that Word doc'). Use after search_library or list_document_files when the content lives in an attached file.",
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
      parts.push(excerptMarker(chunk.length, text.length));
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
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TOOL_TIMEOUT_MS);
  try {
    return await fetch(path, {
      ...init,
      credentials: "include",
      cache: "no-store",
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timer);
  }
}

async function toolJson(path: string, init?: RequestInit): Promise<{ ok: boolean; data: unknown }> {
  const response = await toolFetch(path, init);
  if (!response.ok) return { ok: false, data: null };
  try {
    return { ok: true, data: await response.json() };
  } catch {
    return { ok: false, data: null };
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
