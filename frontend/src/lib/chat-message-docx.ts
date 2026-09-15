import { ApiError } from "@/lib/api";
import { httpErrorFallback, parseErrorPayload } from "@/lib/api-errors";

const UUID = /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;
const DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
const ILLEGAL_WIN = /[<>:"/\\|?*\x00-\x1f]+/g;

export const EMPTY_WORD_BODY = "That reply has no text to put in Word.";
export const BUILD_WORD_FAIL = "Couldn't build Word";
export const FORBIDDEN_WORD = "Couldn't save Word (not allowed).";

export function isPersistedMessageId(id: string | null | undefined): boolean {
  return UUID.test((id || "").trim());
}

const KEEP_NOTES_LINE =
  /^(?:[-*•]\s+)?(?:please\s+)?(?:use add to notes if you want this kept|if you want this kept,?\s+use add to notes|if you(?:'d| would)? like this kept,?\s+use add to notes|if you want to keep this(?: reply)?,?\s+use add to notes|add to notes if you want this(?: reply)? kept|use add to notes to keep this(?: reply)?|use add to notes)\.?$/i;
const KEEP_NOTES_TAIL =
  /(?:\s+)(?:use add to notes if you want this kept|if you want this kept,?\s+use add to notes|if you(?:'d| would)? like this kept,?\s+use add to notes|add to notes if you want this(?: reply)? kept|use add to notes to keep this(?: reply)?|use add to notes)\.?\s*$/i;

/** Answer body for Copy / clipboard / Markdown / text. Spend chip stays off. */
export function stripKeepNotesCta(content: string): string {
  const text = (content || "").replace(/\r\n/g, "\n");
  const kept = text.split("\n").filter((line) => !KEEP_NOTES_LINE.test(line.trim().replace(/^[*_]+|[*_]+$/g, "").trim()));
  return kept.join("\n").replace(KEEP_NOTES_TAIL, "").replace(/\n{3,}/g, "\n\n").trim();
}

export function replyCopyText(content: string): string {
  return stripKeepNotesCta(content);
}

export function filenameFromContentDisposition(header: string | null, fallback = "junior-note.docx"): string {
  const value = header || "";
  const star = value.match(/filename\*=UTF-8''([^;]+)/i);
  if (star?.[1]) {
    try {
      return decodeURIComponent(star[1].trim());
    } catch {
      /* fall through */
    }
  }
  const quoted = value.match(/filename="([^"]+)"/i);
  if (quoted?.[1]) return quoted[1];
  const plain = value.match(/filename=([^;]+)/i);
  if (plain?.[1]) return plain[1].trim().replace(/^["']|["']$/g, "");
  return fallback;
}

export function windowsSafeStem(value: string): string {
  const cleaned = (value || "").replace(ILLEGAL_WIN, "-").trim().replace(/^[. ]+|[. ]+$/g, "");
  if (!cleaned || cleaned === "." || cleaned === "..") return "junior-note";
  return cleaned.slice(0, 120);
}

export function replyHasWordBody(content: string): boolean {
  let text = stripKeepNotesCta(content || "").replace(/\r\n/g, "\n").trim();
  if (!text) return false;
  text = text.replace(/!\[[^\]]*\]\([^)]*\)/g, "");
  text = text.replace(/```[\s\S]*?```/g, "");
  text = text.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1");
  const compact = text.replace(/\s+/g, " ").trim();
  if (!compact) return false;
  if ((compact.startsWith("{") && compact.endsWith("}")) || (compact.startsWith("[") && compact.endsWith("]"))) {
    try {
      JSON.parse(compact);
      return false;
    } catch {
      /* prose that happens to be wrapped */
    }
  }
  return true;
}

export function wordDownloadToast(error: unknown): string {
  const status = error instanceof ApiError ? error.status : 0;
  const message = error instanceof Error ? error.message.trim() : "";
  if (status === 403) return message || FORBIDDEN_WORD;
  if (status === 401) return message || FORBIDDEN_WORD;
  if (message === EMPTY_WORD_BODY || /no text to put in Word/i.test(message)) return EMPTY_WORD_BODY;
  if (message === BUILD_WORD_FAIL || /couldn['’]?t build word/i.test(message)) return BUILD_WORD_FAIL;
  if (status === 400 && /no text|empty/i.test(message)) return EMPTY_WORD_BODY;
  if (status === 400 || status === 502 || status >= 500) return BUILD_WORD_FAIL;
  return message || BUILD_WORD_FAIL;
}

export async function downloadChatMessageDocx(messageId: string, options?: { clean?: boolean }): Promise<void> {
  const id = (messageId || "").trim();
  if (!isPersistedMessageId(id)) {
    throw new ApiError(400, "Wait for the reply to finish before downloading Word.");
  }
  const search = options?.clean ? "?clean=true" : "";
  const response = await fetch(`/api/v1/chat/messages/${encodeURIComponent(id)}/docx${search}`, {
    method: "POST",
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
  const buffer = new Uint8Array(await response.arrayBuffer());
  const type = (response.headers.get("content-type") || "").split(";")[0].trim().toLowerCase();
  if (!buffer.length || buffer[0] !== 0x50 || buffer[1] !== 0x4b) {
    throw new ApiError(502, BUILD_WORD_FAIL);
  }
  if (type && !type.includes("wordprocessingml") && type !== "application/octet-stream") {
    throw new ApiError(502, BUILD_WORD_FAIL);
  }
  const blob = new Blob([buffer], { type: DOCX_TYPE });
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filenameFromContentDisposition(response.headers.get("content-disposition"));
  link.rel = "noopener";
  document.body.appendChild(link);
  link.click();
  window.setTimeout(() => {
    URL.revokeObjectURL(objectUrl);
    link.remove();
  }, 60_000);
}

export function replyFileStem(content: string): string {
  const lines = stripKeepNotesCta(content || "").replace(/\r\n/g, "\n").split("\n");
  let heading = "";
  let firstLine = "";
  for (const raw of lines) {
    const line = raw.trim();
    if (!line || line.startsWith("```")) continue;
    const marked = line.match(/^#{1,6}\s+(.*)$/);
    const candidate = windowsSafeStem((marked ? marked[1] : line).replace(/[*`]+/g, " "));
    if (!candidate || candidate === "junior-note") continue;
    if (marked && !heading) heading = candidate;
    if (!firstLine) firstLine = candidate;
    if (heading) break;
  }
  return heading || firstLine || "junior-note";
}

export function downloadReplyText(content: string, ext: "md" | "txt"): void {
  const text = stripKeepNotesCta(content || "").replace(/\r\n/g, "\n");
  if (!text.trim()) throw new Error("Nothing to save.");
  const blob = new Blob([text], {
    type: ext === "md" ? "text/markdown;charset=utf-8" : "text/plain;charset=utf-8",
  });
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = `${replyFileStem(text)}.${ext}`;
  link.rel = "noopener";
  document.body.appendChild(link);
  link.click();
  window.setTimeout(() => {
    URL.revokeObjectURL(objectUrl);
    link.remove();
  }, 60_000);
}
