import { ApiError } from "@/lib/api";
import { formatChatError, isSilentEmptyChatDetail } from "@/lib/grok-chat-error";
import { spendChipLabel } from "@/lib/grok-model";

/** Pre-token silence ends the read so the pane can write the fallback sentence. */
class SilentTurn extends Error {
  constructor() {
    super("silent");
    this.name = "SilentTurn";
  }
}

/** Wait for /chat response headers through heavy setup (attachments, working notes). */
export const GROK_STREAM_HEADER_MS = 25_000;
/** Default first-token window; heavy turns extend via first_byte_timeout_ms from the server. */
export const GROK_STREAM_FIRST_BYTE_MS = 60_000;
/** After tokens started, abort only if the stream goes idle this long (server may extend). */
export const GROK_STREAM_IDLE_AFTER_MS = 120_000;
/** Imagine edits/generations regularly take longer than the text-chat idle window. */
export const GROK_STREAM_IMAGE_IDLE_MS = 180_000;
/** Live web_search can sit on Searching… longer than the 8s first-token cut. */
export const GROK_STREAM_SEARCH_IDLE_MS = 45_000;
/** @deprecated first-byte window; kept so older tests still compile. */
export const GROK_STREAM_IDLE_MS = GROK_STREAM_FIRST_BYTE_MS;
/** @deprecated do not hard-kill a stream that is still producing tokens. */
export const GROK_STREAM_HARD_MS = 120_000;

export type GrokStreamMeta = {
  conversation_id?: string;
  user_message_id?: string;
  assistant_message_id?: string;
  media_id?: string;
  model?: string;
  model_choice?: string;
  reasoning_effort?: string;
  pace_note?: string;
  stream_status?: string;
  partial?: boolean;
  include_chip?: string;
  include_label?: string;
  include_chars?: number;
  include_mode?: string;
  include_offset?: number;
  include_has_more?: boolean;
  include_next_offset?: number;
  include_next_heading?: string;
  calendar_proposal?: { title: string; start: string; end: string };
  mail_proposal?: { to: string; subject: string; body: string };
  toast?: string;
  toast_kind?: string;
  search_status?: number;
  first_byte_timeout_ms?: number;
  idle_after_ms?: number;
  max_output_tokens?: number;
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
  media_id?: string;
  model?: string;
  model_choice?: string;
  reasoning_effort?: string;
  pace_note?: string;
  stream_status?: string;
  include_chip?: string;
  include_label?: string;
  include_chars?: number;
  include_mode?: string;
  include_offset?: number;
  include_has_more?: boolean;
  include_next_offset?: number;
  include_next_heading?: string;
  calendar_proposal?: { title: string; start: string; end: string };
  mail_proposal?: { to: string; subject: string; body: string };
  toast?: string;
  toast_kind?: string;
  search_status?: number;
  first_byte_timeout_ms?: number;
  idle_after_ms?: number;
  max_output_tokens?: number;
};

function parseSsePart(
  part: string,
  handlers: GrokStreamHandlers,
  receivedDelta: { value: boolean },
  idle?: { ms: number },
  receivedActivity?: { value: boolean },
) {
  const line = part.split("\n").find((item) => item.startsWith("data:"));
  if (!line) return;
  const data = line.slice(5).trim();
  if (data === "[DONE]") return "done" as const;
  const parsed = JSON.parse(data) as StreamPayload;
  if (typeof parsed.idle_after_ms === "number" && idle && parsed.idle_after_ms > idle.ms) {
    idle.ms = parsed.idle_after_ms;
  }
  if (parsed.stream_status === "generating" && idle) {
    idle.ms = Math.max(idle.ms, GROK_STREAM_IMAGE_IDLE_MS);
  }
  if (parsed.stream_status === "searching") {
    receivedActivity && (receivedActivity.value = true);
    if (idle) idle.ms = GROK_STREAM_SEARCH_IDLE_MS;
  }
  if (parsed.heartbeat) {
    receivedActivity && (receivedActivity.value = true);
    handlers.onMeta?.({
      stream_status: parsed.stream_status || "thinking",
    });
  }
  if (parsed.stream_status === "starting_agent" || parsed.stream_status === "deploying") {
    receivedActivity && (receivedActivity.value = true);
    if (idle) idle.ms = Math.max(idle.ms, GROK_STREAM_IDLE_AFTER_MS);
  }
  if (
    parsed.stream_status === "thinking" ||
    parsed.stream_status === "working" ||
    parsed.stream_status === "queued" ||
    parsed.stream_status === "writing" ||
    parsed.stream_status === "generating"
  ) {
    receivedActivity && (receivedActivity.value = true);
  }
  if (parsed.error) {
    const status = typeof parsed.status === "number" ? parsed.status : 502;
    const detail =
      (typeof parsed.message === "string" ? parsed.message : undefined) || parsed.detail || parsed.error;
    const text = typeof detail === "string" ? detail : "";
    if (!parsed.partial && isSilentEmptyChatDetail(text)) return "done" as const;
    throw new ApiError(status, text || formatChatError(status, "Chat failed"), {
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
    parsed.media_id ||
    parsed.model ||
    parsed.model_choice ||
    parsed.reasoning_effort ||
    parsed.pace_note ||
    parsed.stream_status ||
    parsed.partial ||
    parsed.include_chip ||
    parsed.calendar_proposal ||
    parsed.mail_proposal ||
    parsed.toast ||
    parsed.first_byte_timeout_ms ||
    parsed.idle_after_ms ||
    parsed.max_output_tokens
  ) {
    handlers.onMeta?.({
      conversation_id: parsed.conversation_id,
      user_message_id: parsed.user_message_id,
      assistant_message_id: parsed.assistant_message_id,
      media_id: parsed.media_id,
      model: parsed.model,
      model_choice: parsed.model_choice,
      reasoning_effort: parsed.reasoning_effort,
      pace_note: parsed.pace_note,
      stream_status: parsed.stream_status,
      partial: parsed.partial,
      include_chip: parsed.include_chip,
      include_label: parsed.include_label,
      include_chars: parsed.include_chars,
      include_mode: parsed.include_mode,
      include_offset: parsed.include_offset,
      include_has_more: parsed.include_has_more,
      include_next_offset: parsed.include_next_offset,
      include_next_heading: parsed.include_next_heading,
      calendar_proposal: parsed.calendar_proposal,
      mail_proposal: parsed.mail_proposal,
      toast: parsed.toast,
      toast_kind: parsed.toast_kind,
      search_status: parsed.search_status,
      first_byte_timeout_ms: parsed.first_byte_timeout_ms,
      idle_after_ms: parsed.idle_after_ms,
      max_output_tokens: parsed.max_output_tokens,
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

export function mergeAbortSignals(...signals: Array<AbortSignal | undefined>): AbortSignal | undefined {
  const live = signals.filter((item): item is AbortSignal => Boolean(item));
  if (!live.length) return undefined;
  if (live.length === 1) return live[0];
  if (typeof AbortSignal.any === "function") return AbortSignal.any(live);
  const merged = new AbortController();
  for (const item of live) {
    if (item.aborted) {
      merged.abort();
      return merged.signal;
    }
    item.addEventListener("abort", () => merged.abort(), { once: true });
  }
  return merged.signal;
}

export type ChatFirstByteWatchdog = {
  signal: AbortSignal | undefined;
  disarm: () => void;
  remainingFirstByteMs: () => number;
  throwIfSilent: (error: unknown) => never;
  silent: () => boolean;
};

/** Abort hung fetch/stream after 8s with no token. Disarm on the first delta. */
export function startChatFirstByteWatchdog(
  userSignal?: AbortSignal,
  ms: number = GROK_STREAM_FIRST_BYTE_MS,
): ChatFirstByteWatchdog {
  const watchdog = new AbortController();
  const started = Date.now();
  const timer = globalThis.setTimeout(() => watchdog.abort(), ms);
  const disarm = () => globalThis.clearTimeout(timer);
  if (userSignal?.aborted) {
    disarm();
    watchdog.abort();
  } else {
    userSignal?.addEventListener("abort", disarm, { once: true });
  }
  return {
    signal: mergeAbortSignals(userSignal, watchdog.signal),
    disarm,
    remainingFirstByteMs: () => Math.max(250, ms - (Date.now() - started)),
    silent: () => watchdog.signal.aborted && !userSignal?.aborted,
    throwIfSilent: (error: unknown) => {
      if (userSignal?.aborted) {
        throw error instanceof DOMException ? error : new DOMException("Chat aborted", "AbortError");
      }
      if (watchdog.signal.aborted) {
        throw new ApiError(504, formatChatError(504, "xAI silent"));
      }
      throw error;
    },
  };
}

export async function readGrokChatStream(
  response: Response,
  handlers: GrokStreamHandlers,
  signal?: AbortSignal,
  timeouts?: GrokStreamTimeoutOptions,
): Promise<void> {
  if (!response.body) throw new ApiError(502, formatChatError(502, "Chat stream was empty"));

  const firstByteMs = timeouts?.firstByteMs ?? timeouts?.idleMs ?? GROK_STREAM_FIRST_BYTE_MS;
  const idle = { ms: timeouts?.idleAfterMs ?? GROK_STREAM_IDLE_AFTER_MS };
  const preTokenHardMs = timeouts?.hardMs;

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  const receivedDelta = { value: false };
  const receivedActivity = { value: false };
  const startedAt = Date.now();
  let lastActivityAt = Date.now();
  let firstDeltaAt: number | null = null;
  let postedModel: string | undefined;
  let postedReasoning: string | undefined;
  let xaiStatus: number | string | null = null;
  const wrapped: GrokStreamHandlers = {
    onDelta: handlers.onDelta,
    onMeta: (meta) => {
      if (meta.model) postedModel = meta.model;
      if (meta.reasoning_effort) postedReasoning = meta.reasoning_effort;
      handlers.onMeta?.(meta);
    },
  };

  const throwIfAborted = () => {
    if (signal?.aborted) throw new DOMException("Chat aborted", "AbortError");
  };

  if (signal) {
    const onAbort = () => {
      void reader.cancel().catch(() => {
        /* ignore */
      });
    };
    if (signal.aborted) onAbort();
    else signal.addEventListener("abort", onAbort, { once: true });
  }

  const throwIfTimedOut = () => {
    const now = Date.now();
    if (!receivedDelta.value) {
      if (receivedActivity.value) {
        if (now - lastActivityAt >= idle.ms) {
          xaiStatus = "empty";
          throw new SilentTurn();
        }
        return;
      }
      const budget = preTokenHardMs != null ? Math.min(firstByteMs, preTokenHardMs) : firstByteMs;
      if (now - startedAt >= budget) {
        xaiStatus = "empty";
        throw new SilentTurn();
      }
      return;
    }
    if (now - lastActivityAt >= idle.ms) {
      const detail =
        idle.ms > GROK_STREAM_IMAGE_IDLE_MS
          ? "Timed out waiting for the image."
          : idle.ms > GROK_STREAM_IDLE_AFTER_MS
            ? `Timed out after ${Math.round(idle.ms / 1000)}s waiting for the next token.`
            : "Timed out after 60s.";
      xaiStatus = 504;
      throw new ApiError(504, formatChatError(504, detail), {
        partial: true,
      });
    }
  };

  const waitForChunk = async () => {
    while (true) {
      throwIfTimedOut();
      throwIfAborted();
      const now = Date.now();
      const remaining = receivedDelta.value || receivedActivity.value
        ? idle.ms - (now - lastActivityAt)
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
      throwIfAborted();
      const { value, done } = await waitForChunk();
      if (done) break;
      lastActivityAt = Date.now();
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() || "";
      for (const part of parts) {
        if (!part.trim()) continue;
        try {
          const outcome = parseSsePart(part, wrapped, receivedDelta, idle, receivedActivity);
          if (receivedDelta.value) {
            lastActivityAt = Date.now();
            if (firstDeltaAt == null) firstDeltaAt = lastActivityAt;
            if (xaiStatus == null) xaiStatus = 200;
          }
          if (outcome === "done") return;
        } catch (error) {
          if (error instanceof ApiError) {
            xaiStatus = error.status;
            throw error;
          }
        }
      }
    }
    if (buffer.trim()) {
      try {
        parseSsePart(buffer, wrapped, receivedDelta, idle, receivedActivity);
        if (receivedDelta.value && firstDeltaAt == null) firstDeltaAt = Date.now();
      } catch (error) {
        if (error instanceof ApiError) throw error;
      }
    }
  } catch (error) {
    if (!(error instanceof SilentTurn)) throw error;
  } finally {
    const ttftMs = firstDeltaAt != null ? firstDeltaAt - startedAt : -1;
    console.info("xAI", spendChipLabel(postedModel, postedReasoning), {
      ttft_ms: ttftMs,
      model: postedModel || "grok-4.6",
      reasoning: postedReasoning || "low",
      xai_status: xaiStatus,
    });
    try {
      await reader.cancel();
    } catch {
      /* ignore */
    }
  }
}

/** Huge bodies still include, as a heading/selection/chunk rather than the whole vault. */
export const GROK_ARTICLE_INCLUDE_HINT_MAX = 12_000;

export function shouldIncludeArticle(
  includeRequested: boolean,
  articleId: string | null | undefined,
  articleBody: string | null | undefined,
): { include: boolean; skippedHuge: boolean } {
  if (!includeRequested || !articleId) return { include: false, skippedHuge: false };
  const size = (articleBody || "").length;
  if (size > GROK_ARTICLE_INCLUDE_HINT_MAX) {
    return { include: true, skippedHuge: true };
  }
  return { include: true, skippedHuge: false };
}
