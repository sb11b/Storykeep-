/**
 * Pure helpers for the xAI Realtime speech-to-speech conversation mode.
 *
 * One WebSocket carries the whole loop: mic PCM16 in, assistant PCM16 out.
 * Everything here is DOM-free so it can run under `node --test`.
 */

/** xAI realtime voice model. */
export const REALTIME_MODEL = "grok-voice-latest";

/** Wire rate for both directions. xAI expects 24kHz PCM16. */
export const REALTIME_SAMPLE_RATE = 24000;

/** ~100ms of mic audio per input_audio_buffer.append. */
export const MIC_CHUNK_MS = 100;

/** Samples per mic chunk (100ms at 24kHz). */
export const MIC_CHUNK_SAMPLES = (REALTIME_SAMPLE_RATE * MIC_CHUNK_MS) / 1000;

/** ScriptProcessor buffer; 4096 frames ≈ 170ms at 24kHz, one hop per append. */
export const MIC_PROCESSOR_BUFFER = 4096;

export const BASE_BACKOFF_MS = 500;
export const MAX_BACKOFF_MS = 8000;
/** Give up reconnecting after this many failed attempts in a row. */
export const MAX_RECONNECT_ATTEMPTS = 5;

/** Realtime transcriptions use grok-transcribe on the same socket. */
export const INPUT_TRANSCRIPTION_MODEL = "grok-transcribe";

/** Junior's persona for conversation mode. */
export const JUNIOR_TALK_INSTRUCTIONS =
  "You are Junior, a friendly school-coding helper for a young student. " +
  "Keep replies short and conversational — one or two sentences unless asked for more. " +
  "Speak plainly, no markdown, no lists, no code unless the student asks for code.";

/** Build the realtime WebSocket URL, resuming a prior conversation when we have its id. */
export function buildRealtimeUrl(conversationId?: string | null): string {
  const base = `wss://api.x.ai/v1/realtime?model=${REALTIME_MODEL}`;
  return conversationId ? `${base}&conversation_id=${encodeURIComponent(conversationId)}` : base;
}

/** The session.update payload: low latency, server VAD, in+out PCM16 at 24kHz. */
export function buildSessionUpdate(voice: string, conversationId?: string | null) {
  return {
    type: "session.update",
    session: {
      voice,
      instructions: JUNIOR_TALK_INSTRUCTIONS,
      // Low latency: skip reasoning for conversational turns.
      reasoning: { effort: "none" },
      // Server-side VAD + natural barge-in; the server commits on speech_stopped.
      turn_detection: { type: "server_vad" },
      audio: {
        input: {
          format: { type: "audio/pcm", rate: REALTIME_SAMPLE_RATE },
          transcription: { model: INPUT_TRANSCRIPTION_MODEL },
        },
        output: { format: { type: "audio/pcm", rate: REALTIME_SAMPLE_RATE } },
      },
      // Resume prior turns on reconnect; the id arrives with conversation.created.
      resumption: { enabled: true, ...(conversationId ? { conversation_id: conversationId } : {}) },
    },
  };
}

/** Exponential backoff, capped. */
export function nextBackoffDelay(attempt: number): number {
  const n = Math.max(0, Math.floor(attempt));
  return Math.min(BASE_BACKOFF_MS * 2 ** n, MAX_BACKOFF_MS);
}

export type RealtimeEventKind =
  | "conversation"
  | "speech-start"
  | "speech-stop"
  | "user-transcript"
  | "assistant-audio"
  | "assistant-done"
  | "session"
  | "error"
  | "other";

/** Buckets every realtime event we care about. */
export function classifyRealtimeEvent(type: unknown): RealtimeEventKind {
  switch (type) {
    case "conversation.created":
      return "conversation";
    case "input_audio_buffer.speech_started":
      return "speech-start";
    case "input_audio_buffer.speech_stopped":
      return "speech-stop";
    case "conversation.item.input_audio_transcription.completed":
      return "user-transcript";
    case "response.output_audio.delta":
    case "response.audio.delta":
      return "assistant-audio";
    case "response.output_audio.done":
    case "response.audio.done":
    case "response.done":
      return "assistant-done";
    case "session.created":
    case "session.updated":
      return "session";
    case "error":
      return "error";
    default:
      return "other";
  }
}

/** User speech text from a transcription.completed event, trimmed; null when blank. */
export function extractUserTranscript(msg: unknown): string | null {
  if (!msg || typeof msg !== "object") return null;
  const m = msg as { transcript?: unknown; item?: { content?: unknown } };
  // Flat shape: { transcript }. Nested shape: { item: { content: [{ transcript }] } }
  // — take the first content part that carries a string transcript.
  if (typeof m.transcript === "string") return m.transcript.trim() || null;
  if (Array.isArray(m.item?.content)) {
    for (const part of m.item.content as Array<{ transcript?: unknown }>) {
      if (typeof part?.transcript === "string") return part.transcript.trim() || null;
    }
  }
  return null;
}

/** Assistant PCM16 base64 delta, or null for other shapes. */
export function extractAudioDelta(msg: unknown): string | null {
  if (!msg || typeof msg !== "object") return null;
  const m = msg as { delta?: unknown; output_audio?: { delta?: unknown } };
  const delta = typeof m.delta === "string" ? m.delta : m.output_audio?.delta;
  return typeof delta === "string" && delta.length > 0 ? delta : null;
}

/** The conversation id carried by conversation.created — needed to resume. */
export function extractConversationId(msg: unknown): string | null {
  if (!msg || typeof msg !== "object") return null;
  const m = msg as { conversation?: { id?: unknown } };
  return typeof m.conversation?.id === "string" && m.conversation.id ? m.conversation.id : null;
}

/** Clamp to [-1, 1] so overflow cannot wrap the int16. */
export function clampSample(value: number): number {
  if (value > 1) return 1;
  if (value < -1) return -1;
  return value;
}

/** Convert a Float32 mic frame to little-endian PCM16 bytes (Uint8Array, byte-pairod). */
export function floatToPcm16Bytes(samples: Float32Array): Uint8Array {
  const out = new Uint8Array(samples.length * 2);
  const view = new DataView(out.buffer);
  for (let i = 0; i < samples.length; i++) {
    const v = clampSample(samples[i]!);
    view.setInt16(i * 2, v < 0 ? v * 0x8000 : v * 0x7fff, true);
  }
  return out;
}

/** Base64-encode PCM16 bytes without Buffer (browser + Node 18+ global). */
export function pcm16ToBase64(bytes: Uint8Array): string {
  let binary = "";
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]!);
  return btoa(binary);
}

/** One input_audio_buffer.append payload for a Float32 mic frame. */
export function encodeMicChunk(samples: Float32Array): string {
  return pcm16ToBase64(floatToPcm16Bytes(samples));
}

/** Split a long Float32 capture into fixed-size append chunks. */
export function splitMicChunks(samples: Float32Array, chunkSamples = MIC_CHUNK_SAMPLES): Float32Array[] {
  if (chunkSamples <= 0) return samples.length ? [samples.slice()] : [];
  const chunks: Float32Array[] = [];
  for (let offset = 0; offset < samples.length; offset += chunkSamples) {
    chunks.push(samples.slice(offset, offset + chunkSamples));
  }
  return chunks;
}
