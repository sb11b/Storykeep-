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

/** Shared fetch for article visible-speech and chat reply TTS chunk requests. */
export async function fetchSpeechChunk(
  url: string,
  init: RequestInit,
  logLabel: "article" | "chat",
): Promise<SpeechChunkPayload> {
  const response = await fetch(url, {
    ...init,
    credentials: "include",
    cache: "no-store",
  });
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
    logTtsFailure(logLabel, response.status, loggedBody);
    throw new ApiError(response.status, detail || httpErrorFallback(response.status));
  }
  const data = (await response.json()) as SpeechChunkJson;
  return parseSpeechChunkJson(data);
}
