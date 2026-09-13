import { ApiError } from "@/lib/api";
import { httpErrorFallback, parseErrorPayload } from "@/lib/api-errors";
import type { TtsWord } from "@/lib/types";

export type SpeechChunkPayload = {
  blob: Blob;
  chunks: number;
  wordOffset: number;
  chunkWordCounts: number[];
  duration: number | null;
  words: TtsWord[];
  contentHash: string;
  ttsWordCount: number;
};

type SpeechChunkJson = {
  audio: string;
  content_type?: string;
  chunks: number;
  word_offset?: number;
  chunk_word_counts?: number[];
  duration?: number | null;
  words?: TtsWord[];
  content_hash?: string;
  tts_word_count?: number;
};

function parseSpeechChunkJson(data: SpeechChunkJson): SpeechChunkPayload {
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
    contentHash: data.content_hash || "",
    ttsWordCount: Number(data.tts_word_count || 0),
  };
}

function logTtsFailure(label: string, status: number, body: unknown) {
  console.error(`[tts] ${label} failed`, { status, body });
}

export type SpeechChunkOptions = {
  /** Caller abort, e.g. the user pressed Stop. */
  signal?: AbortSignal;
  /** Give up rather than spin forever. */
  timeoutMs?: number;
  /** Script length, for the log line. */
  chars?: number;
};

/** Shared fetch for article visible-speech and chat reply TTS chunk requests. */
export async function fetchSpeechChunk(
  url: string,
  init: RequestInit,
  logLabel: "article" | "chat",
  options: SpeechChunkOptions = {},
): Promise<SpeechChunkPayload> {
  const startedAt = Date.now();
  const controller = new AbortController();
  const abortFromCaller = () => controller.abort();
  if (options.signal?.aborted) controller.abort();
  else options.signal?.addEventListener("abort", abortFromCaller, { once: true });
  let timedOut = false;
  const timer = options.timeoutMs
    ? setTimeout(() => {
        timedOut = true;
        controller.abort();
      }, options.timeoutMs)
    : null;
  let status = 0;

  try {
    const response = await fetch(url, {
      ...init,
      signal: controller.signal,
      credentials: "include",
      cache: "no-store",
    });
    status = response.status;
    if (!response.ok) {
      let detail: string | null = null;
      let loggedBody: unknown = null;
      try {
        const raw = await response.json();
        loggedBody = raw;
        detail = parseErrorPayload(raw);
      } catch {
        try {
          const text = (await response.text()).slice(0, 240);
          loggedBody = text;
        } catch {
          loggedBody = null;
        }
      }
      logTtsFailure(logLabel, status, loggedBody);
      throw new ApiError(status, detail || httpErrorFallback(status));
    }
    const data = (await response.json()) as SpeechChunkJson;
    const payload = parseSpeechChunkJson(data);
    if (!payload.blob.size) {
      throw new ApiError(status, `TTS returned no audio (HTTP ${status} with an empty body).`);
    }
    return payload;
  } catch (error) {
    if (timedOut) {
      const seconds = Math.round((options.timeoutMs ?? 0) / 1000);
      throw new ApiError(
        status || 408,
        `TTS timed out after ${seconds}s (HTTP ${status || "…"} or no body).`,
      );
    }
    throw error;
  } finally {
    if (timer) clearTimeout(timer);
    options.signal?.removeEventListener("abort", abortFromCaller);
    console.log("larry-tts", {
      stage: `${logLabel} /tts`,
      chars: options.chars ?? null,
      ttsStatus: timedOut ? "timeout" : status || "network",
      ms: Date.now() - startedAt,
    });
  }
}
