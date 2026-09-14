export const GROK_CONTEXT_CHAR_CAP = 24_000;
export const GROK_CONTEXT_TOAST = "Too large — deselect Include or start a new chat.";
export const GROK_CONTEXT_THREAD_WINDOW = 12;

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
    for (const file of row.files || []) {
      total += textLen(file?.extract_text);
    }
  }
  total += textLen(input.draft);
  for (const extract of input.pendingExtracts || []) {
    total += textLen(extract);
  }
  const article = input.includeArticle ? textLen(input.articleBody) : 0;
  total += article;
  if (input.includeNote) {
    const note = textLen(input.noteBody);
    if (note && !(input.includeArticle && input.noteBody === input.articleBody)) {
      total += note;
    }
  }
  return total;
}

export function chatContextOverCap(input: ChatContextInput): boolean {
  return estimateChatContextChars(input) > GROK_CONTEXT_CHAR_CAP;
}
