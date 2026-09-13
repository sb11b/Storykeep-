import { ApiError } from "@/lib/api";
import { formatChatError } from "@/lib/grok-chat-error";

export const GROK_STREAM_IDLE_MS = 15_000;
export const GROK_STREAM_HARD_MS = 60_000;

export type GrokStreamMeta = {
  conversation_id?: string;
  user_message_id?: string;
  assistant_message_id?: string;
  model?: string;
  model_choice?: string;
};

export type GrokStreamHandlers = {
  onDelta: (text: string) => void;
  onMeta?: (meta: GrokStreamMeta) => void;
};

type StreamPayload = {
  delta?: string;
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
    const detail = parsed.detail || parsed.error;
    throw new ApiError(status, parsed.error || formatChatError(status, detail));
  }
  if (
    parsed.conversation_id ||
    parsed.user_message_id ||
    parsed.assistant_message_id ||
    parsed.model ||
    parsed.model_choice
  ) {
    handlers.onMeta?.({
      conversation_id: parsed.conversation_id,
      user_message_id: parsed.user_message_id,
      assistant_message_id: parsed.assistant_message_id,
      model: parsed.model,
      model_choice: parsed.model_choice,
    });
  }
  if (parsed.delta) {
    receivedDelta.value = true;
    handlers.onDelta(parsed.delta);
  }
  return "continue" as const;
}

export type GrokStreamTimeoutOptions = {
  idleMs?: number;
  hardMs?: number;
};

export async function readGrokChatStream(
  response: Response,
  handlers: GrokStreamHandlers,
  signal?: AbortSignal,
  timeouts?: GrokStreamTimeoutOptions,
): Promise<void> {
  if (!response.body) throw new ApiError(502, formatChatError(502, "Chat stream was empty"));

  const idleMs = timeouts?.idleMs ?? GROK_STREAM_IDLE_MS;
  const hardMs = timeouts?.hardMs ?? GROK_STREAM_HARD_MS;

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  const receivedDelta = { value: false };
  const startedAt = Date.now();
  let streamOpenedAt = Date.now();

  const throwIfTimedOut = () => {
    const now = Date.now();
    if (now - startedAt >= hardMs) {
      throw new ApiError(504, formatChatError(504, "Chat timed out after 60s."));
    }
    if (!receivedDelta.value && now - streamOpenedAt >= idleMs) {
      throw new ApiError(504, formatChatError(504, "No response (timeout)"));
    }
  };

  const waitForChunk = async () => {
    while (true) {
      throwIfTimedOut();
      if (signal?.aborted) throw new DOMException("Chat aborted", "AbortError");
      const remainingHard = hardMs - (Date.now() - startedAt);
      const remainingIdle = receivedDelta.value
        ? remainingHard
        : idleMs - (Date.now() - streamOpenedAt);
      const waitMs = Math.max(250, Math.min(remainingHard, remainingIdle, 2000));
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

  streamOpenedAt = Date.now();
  try {
    while (true) {
      const { value, done } = await waitForChunk();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() || "";
      for (const part of parts) {
        if (!part.trim()) continue;
        try {
          const outcome = parseSsePart(part, handlers, receivedDelta);
          if (outcome === "done") {
            if (!receivedDelta.value) {
              throw new ApiError(504, formatChatError(504, "No response (timeout)"));
            }
            return;
          }
        } catch (error) {
          if (error instanceof ApiError) throw error;
        }
      }
    }
    if (!receivedDelta.value) {
      throw new ApiError(504, formatChatError(504, "No response (timeout)"));
    }
  } finally {
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
