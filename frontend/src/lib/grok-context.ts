import { INCLUDE_TURN_CHAR_MAX, WORKING_NOTE_CHAR_CAP } from "@/lib/include-chunk";

export const GROK_CONTEXT_CHAR_CAP = 96_000;
export const PASTE_FIRST_CHUNK_CHARS = 12_000;
export const JUNIOR_TEXTAREA_MAX_LENGTH = 1_000_000;
export const GROK_CONTEXT_TOAST =
  "This turn is over the cap. Include a heading, a selection, or the next chunk.";
export const GROK_THREAD_TOAST =
  "Recent messages are too long. Shorten your message or start a new chat.";
export const GROK_CONTEXT_THREAD_WINDOW = 8;

export function pasteSplitToast(chars: number): string {
  return `This paste is ${chars.toLocaleString("en-US")} chars. Send first 12k or split.`;
}

/** First 12k plus remainder — never drop the leftover. */
export function splitPasteChunk(
  text: string,
  chunk = PASTE_FIRST_CHUNK_CHARS,
): { first: string; remainder: string } {
  const source = text || "";
  if (source.length <= chunk) return { first: source, remainder: "" };
  let cut = chunk;
  const space = source.lastIndexOf(" ", chunk);
  if (space > chunk * 0.6) cut = space;
  return { first: source.slice(0, cut).trimEnd(), remainder: source.slice(cut).replace(/^\s+/, "") };
}

export function textareaSelection(el: HTMLTextAreaElement | null | undefined): string {
  if (!el) return "";
  const start = el.selectionStart ?? 0;
  const end = el.selectionEnd ?? 0;
  if (end <= start) return "";
  return el.value.slice(start, end);
}

export type ContextMessage = {
  role?: string;
  content?: string | null;
  waiting?: boolean;
  files?: Array<{ extract_text?: string | null } | null> | null;
};

export type ChatContextInput = {
  messages: ContextMessage[];
  draft?: string;
  includeArticle?: boolean;
  articleBody?: string | null;
  includeNote?: boolean;
  noteBody?: string | null;
  includeSliceChars?: number;
  workingNoteSliceChars?: number;
  pendingExtracts?: Array<string | null | undefined>;
};

function textLen(value: string | null | undefined): number {
  return (value || "").length;
}

/** Chars that would ride this Send: thread window + draft + includes + extracts. */
export function estimateChatContextChars(input: ChatContextInput): number {
  const rows = (input.messages || []).filter((item) => !item.waiting && (item.content || item.files?.length));
  const windowed = rows.slice(-GROK_CONTEXT_THREAD_WINDOW);
  let total = 0;
  for (const row of windowed) {
    total += textLen(row.content);
  }
  const lastUser = [...windowed].reverse().find((row) => row.role === "user");
  for (const file of lastUser?.files || []) {
    total += textLen(file?.extract_text);
  }
  total += textLen(input.draft);
  for (const extract of input.pendingExtracts || []) {
    total += textLen(extract);
  }
  const articleCap = input.includeSliceChars ?? INCLUDE_TURN_CHAR_MAX;
  const article = input.includeArticle ? Math.min(textLen(input.articleBody), articleCap) : 0;
  total += article;
  if (input.includeNote) {
    const note = Math.min(textLen(input.noteBody), articleCap);
    if (note && !(input.includeArticle && input.noteBody === input.articleBody)) {
      total += note;
    }
  }
  if (input.workingNoteSliceChars) {
    total += Math.min(input.workingNoteSliceChars, WORKING_NOTE_CHAR_CAP);
  }
  return total;
}

export function chatContextOverCap(input: ChatContextInput): boolean {
  return estimateChatContextChars(input) > GROK_CONTEXT_CHAR_CAP;
}

export function threadContextToast(input: ChatContextInput): string {
  const hasInclude =
    input.includeArticle ||
    input.includeNote ||
    Boolean(input.workingNoteSliceChars) ||
    Boolean(input.pendingExtracts?.some((item) => textLen(item) > 0));
  if (hasInclude) {
    return GROK_CONTEXT_TOAST;
  }
  return GROK_THREAD_TOAST;
}
