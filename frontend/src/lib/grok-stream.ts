import { ApiError } from "@/lib/api";
import { formatChatError } from "@/lib/grok-chat-error";

/** Client slack over the server's 8s first-byte cut so "xAI silent" can arrive. */
export const GROK_STREAM_FIRST_BYTE_MS = 12_000;
/** After tokens started, abort only if the stream goes idle this long. */
export const GROK_STREAM_IDLE_AFTER_MS = 60_000;
/** @deprecated first-byte window; kept so older tests still compile. */
export const GROK_STREAM_IDLE_MS = GROK_STREAM_FIRST_BYTE_MS;
/** @deprecated do not hard-kill a stream that is still producing tokens. */
export const GROK_STREAM_HARD_MS = 120_000;

export type GrokStreamMeta = {
  conversation_id?: string;
  user_message_id?: string;
  assistant_message_id?: string;
  model?: string;
  model_choice?: string;
  partial?: boolean;
};

export type GrokStreamHandlers = {
  onDelta: (text: string) => void;
  onMeta?: (meta: GrokStreamMeta) => void;
};

type StreamPayload = {
  delta?: string;
  heartbeat?: boolean;
  message?: string;
  error?: string;
  status?: number;
  detail?: string;
  partial?: boolean;
  conversation_id?: string;
  user_message_id?: string;
  assistant_message_id?: string;
  model?: string;
  model_choice?: string;
};

function parseSsePart(part: string, handlers: GrokStreamHandlers, receivedDelta: { value: boolean }) {
  const line = part.split("\n").find((item) => item.startsWith("data:"));
  if (!line) return;
  const data = line.slice(5).trim();
  if (data === "[DONE]") return "done" as const;
  const parsed = JSON.parse(data) as StreamPayload;
  if (parsed.error) {
    const status = typeof parsed.status === "number" ? parsed.status : 502;
    const detail =
      (typeof parsed.message === "string" ? parsed.message : undefined) || parsed.detail || parsed.error;
    throw new ApiError(status, parsed.error || formatChatError(status, detail), {
      partial: Boolean(parsed.partial),
    });
  }
  if (parsed.delta) {
    receivedDelta.value = true;
    handlers.onDelta(parsed.delta);
  }
  if (
    parsed.conversation_id ||
    parsed.user_message_id ||
    parsed.assistant_message_id ||
    parsed.model ||
    parsed.model_choice ||
    parsed.partial
  ) {
    handlers.onMeta?.({
      conversation_id: parsed.conversation_id,
      user_message_id: parsed.user_message_id,
      assistant_message_id: parsed.assistant_message_id,
      model: parsed.model,
      model_choice: parsed.model_choice,
      partial: parsed.partial,
    });
  }
  return "continue" as const;
}

export type GrokStreamTimeoutOptions = {
  firstByteMs?: number;
  idleAfterMs?: number;
  /** Alias for firstByteMs (no tokens yet). */
  idleMs?: number;
  /** Only used before the first token; never cuts a stream that already has words. */
  hardMs?: number;
};

export async function readGrokChatStream(
  response: Response,
  handlers: GrokStreamHandlers,
  signal?: AbortSignal,
  timeouts?: GrokStreamTimeoutOptions,
): Promise<void> {
  if (!response.body) throw new ApiError(502, formatChatError(502, "Chat stream was empty"));

  const firstByteMs = timeouts?.firstByteMs ?? timeouts?.idleMs ?? GROK_STREAM_FIRST_BYTE_MS;
  const idleAfterMs = timeouts?.idleAfterMs ?? GROK_STREAM_IDLE_AFTER_MS;
  const preTokenHardMs = timeouts?.hardMs;

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  const receivedDelta = { value: false };
  const startedAt = Date.now();
  let lastActivityAt = Date.now();
  let firstDeltaAt: number | null = null;

  const throwIfTimedOut = () => {
    const now = Date.now();
    if (!receivedDelta.value) {
      const budget = preTokenHardMs != null ? Math.min(firstByteMs, preTokenHardMs) : firstByteMs;
      if (now - startedAt >= budget) {
        throw new ApiError(504, formatChatError(504, "xAI silent"));
      }
      return;
    }
    if (now - lastActivityAt >= idleAfterMs) {
      throw new ApiError(504, formatChatError(504, `Chat timed out after ${Math.round(idleAfterMs / 1000)}s.`), {
        partial: true,
      });
    }
  };

  const waitForChunk = async () => {
    while (true) {
      throwIfTimedOut();
      if (signal?.aborted) throw new DOMException("Chat aborted", "AbortError");
      const now = Date.now();
      const remaining = receivedDelta.value
        ? idleAfterMs - (now - lastActivityAt)
        : (preTokenHardMs != null ? Math.min(firstByteMs, preTokenHardMs) : firstByteMs) - (now - startedAt);
      const waitMs = Math.max(250, Math.min(remaining, 2000));
      const result = await Promise.race([
        reader.read(),
        new Promise<{ value: undefined; done: false; timedOut: true }>((resolve) =>
          globalThis.setTimeout(
            () => resolve({ value: undefined, done: false, timedOut: true }),
            waitMs,
          ),
        ),
      ]);
      if ("timedOut" in result && result.timedOut) continue;
      return result as ReadableStreamReadResult<Uint8Array>;
    }
  };

  try {
    while (true) {
      const { value, done } = await waitForChunk();
      if (done) break;
      lastActivityAt = Date.now();
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() || "";
      for (const part of parts) {
        if (!part.trim()) continue;
        try {
          const outcome = parseSsePart(part, handlers, receivedDelta);
          if (receivedDelta.value) {
            lastActivityAt = Date.now();
            if (firstDeltaAt == null) firstDeltaAt = lastActivityAt;
          }
          if (outcome === "done") {
            if (!receivedDelta.value) {
              throw new ApiError(504, formatChatError(504, "xAI silent"));
            }
            return;
          }
        } catch (error) {
          if (error instanceof ApiError) throw error;
        }
      }
    }
    if (buffer.trim()) {
      try {
        parseSsePart(buffer, handlers, receivedDelta);
        if (receivedDelta.value && firstDeltaAt == null) firstDeltaAt = Date.now();
      } catch (error) {
        if (error instanceof ApiError) throw error;
      }
    }
    if (!receivedDelta.value) {
      throw new ApiError(504, formatChatError(504, "xAI silent"));
    }
  } finally {
    const ttftMs = firstDeltaAt != null ? firstDeltaAt - startedAt : -1;
    console.info("larry-chat", { ttft_ms: ttftMs, flushed: receivedDelta.value });
    try {
      await reader.cancel();
    } catch {
      /* ignore */
    }
  }
}

/** Skip attaching huge article bodies client-side; server still caps excerpt. */
export const GROK_ARTICLE_INCLUDE_HINT_MAX = 24_000;

export function shouldIncludeArticle(
  includeRequested: boolean,
  articleId: string | null | undefined,
  articleBody: string | null | undefined,
): { include: boolean; skippedHuge: boolean } {
  if (!includeRequested || !articleId) return { include: false, skippedHuge: false };
  const size = (articleBody || "").length;
  if (size > GROK_ARTICLE_INCLUDE_HINT_MAX) {
    return { include: false, skippedHuge: true };
  }
  return { include: true, skippedHuge: false };
}
