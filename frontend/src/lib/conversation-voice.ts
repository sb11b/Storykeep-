/**
 * Pure helpers for the xAI Realtime speech-to-speech conversation mode.
 *
 * One WebSocket carries the whole loop: mic PCM16 in, assistant PCM16 out.
 * Everything here is DOM-free so it can run under `node --test`.
 */

import { JUNIOR_TOOLS } from "./junior-tools";

// Junior's function-tool surface is defined in junior-tools.ts; re-exported
// here so the hook keeps a single import source for realtime helpers.
export {
  buildFunctionCallOutput,
  buildResponseCreate,
  extractFunctionCall,
  runJuniorTool,
  type JuniorFunctionCall,
} from "./junior-tools";

/** xAI realtime voice model. Pinned to the versioned flagship (the xAI console's
 * "Grok Voice Think Fast 2.0"); `grok-voice-latest` is its alias — we pin per the
 * xAI docs' production guidance so a future alias move can't shift our voice stack. */
export const REALTIME_MODEL = "grok-voice-think-fast-2.0";

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

/**
 * A. keyterms — ASR bias terms for Steve's world. These proper nouns are the
 * ones transcription currently guesses at (SNHU → "S N H U"-ish garbage,
 * Bitsko → "bit sco"), so we hand the curated list to the server. Hard caps
 * from the xAI API: at most KEYTERM_MAX_COUNT terms, each at most
 * KEYTERM_MAX_CHARS characters. Pinned by tests so a future edit can't
 * silently break the session.update contract.
 */
export const KEYTERM_MAX_COUNT = 100;
export const KEYTERM_MAX_CHARS = 50;

export const JUNIOR_KEYTERMS: readonly string[] = [
  "Storykeep",
  "Newsmax",
  "Fox News",
  "Meridian",
  "Bitsko",
  "SNHU",
  "Junior",
  "Jennifer",
  "Matthew",
  "Andrew",
  "Dayton",
  "Hermes",
  "Grok",
  "Fastmail",
  "Bitsko Group",
];

/**
 * C. replace map — pronunciation fixes the TTS applies when speaking. The
 * spoken audio changes; the written transcript stays correct (the transcript
 * carries the original spelling).
 */
export const JUNIOR_PRONUNCIATION_REPLACEMENTS: Readonly<Record<string, string>> = {
  SNHU: "S N H U",
  JMAP: "J map",
  Bitsko: "Bit sko",
};

/** B. audio.output.speed bounds — the API accepts 0.7–1.5. */
export const OUTPUT_SPEED_MIN = 0.7;
export const OUTPUT_SPEED_MAX = 1.5;
export const OUTPUT_SPEED_DEFAULT = 1.0;

/** Clamp a requested playback speed into the API's accepted range. Pure. */
export function clampOutputSpeed(speed: number): number {
  if (!Number.isFinite(speed)) return OUTPUT_SPEED_DEFAULT;
  return Math.min(OUTPUT_SPEED_MAX, Math.max(OUTPUT_SPEED_MIN, speed));
}

/** E. idle_timeout_ms — if Steve goes quiet after Junior finishes, re-engage. */
export const IDLE_TIMEOUT_MS = 15000;

/** F. Adaptive reasoning effort — "none" for fast chit-chat, "high" on demand. */
export type ReasoningEffort = "none" | "high";
export const DEFAULT_REASONING_EFFORT: ReasoningEffort = "none";

/** Junior's persona for conversation mode. */
export const JUNIOR_TALK_INSTRUCTIONS =
  "You are Junior, a friendly school-coding helper for a young student. " +
  "Keep replies short and conversational — one or two sentences unless asked for more. " +
  "Speak plainly, no markdown, no lists, no code unless the student asks for code. " +
  "TWO SEPARATE systems, do not mix them up: " +
  "(1) his RSS FEEDS — news he follows (Newsmax, Fox News, Medium, blogs): " +
  "use list_feeds to see what he subscribes to, search_articles to find articles " +
  "in those feeds, and read_article to read one aloud; " +
  "(2) his Storykeep LIBRARY documents — articles, papers, notes, and school texts " +
  "he has written or uploaded: use search_library when he asks about his documents " +
  "or what he has been working on, and get_document or read_document_file when he " +
  "wants one of those read to him. " +
  "When Steve says 'my article' or 'my feed', prefer the feed tools; " +
  "when he says 'my document', 'my paper', or 'my text', prefer the library tools. " +
  "Use list_pending_work when he asks what's waiting — documents coming in or approvals going out — " +
  "and create_task when he tells you to queue work for the Hermes team. " +
  "You can also read Steve's business email (thebitskogroup@fastmail.com) with read_email, " +
  "search_email, and read_email_message, list saved drafts with list_drafts, " +
  "and you can draft replies with draft_email — " +
  "but you can NEVER send email: drafts are saved for Steve to review and send himself, " +
  "so never say or imply that an email was sent. " +
  "When Steve asks you to READ something (a feed article, a library document, an email), " +
  "read it aloud in full — do NOT summarize, do NOT shorten, do NOT stop early. " +
  "Summarize ONLY when he asks for a summary or 'what's it about'. " +
  "When reading long content, you may say 'Here's your article on X' first, " +
  "then read the body straight through. " +
  "Long documents and articles come back in chunks: after reading a chunk that hit the cap, " +
  "say 'That's the first part — want me to keep reading?' " +
  "and when he says yes or continue, call the tool again with the offset where the last chunk ended. " +
  "When asked about current events, recent news, or anything time-sensitive, use your web_search tool before answering. " +
  "You can also search X (Twitter) with x_search — use it when Steve asks about reactions, trends, or 'what are people saying on X or Twitter'.";

/** Build the realtime WebSocket URL, resuming a prior conversation when we have its id. */
export function buildRealtimeUrl(conversationId?: string | null): string {
  const base = `wss://api.x.ai/v1/realtime?model=${REALTIME_MODEL}`;
  return conversationId ? `${base}&conversation_id=${encodeURIComponent(conversationId)}` : base;
}

/**
 * The session.update payload: low latency, server VAD, 24kHz PCM16 in and
 * out, plus the verified xAI voice capabilities folded in this slice:
 * keyterms + language_hint (ASR accuracy), output speed, a pronunciation
 * replace map, the x_search tool, idle_timeout_ms, and adaptive reasoning.
 * All of these were verified live against
 * wss://api.x.ai/v1/realtime?model=grok-voice-think-fast-2.0 — a single
 * session.update carrying every one returned session.updated with zero
 * errors and the server echoed each param back.
 */
export function buildSessionUpdate(
  voice: string,
  conversationId?: string | null,
  speed: number = OUTPUT_SPEED_DEFAULT,
  reasoningEffort: ReasoningEffort = DEFAULT_REASONING_EFFORT,
) {
  return {
    type: "session.update",
    session: {
      voice,
      instructions: JUNIOR_TALK_INSTRUCTIONS,
      // Low latency: skip reasoning for conversational turns (F — the
      // "high" option is explicit control, never auto-detected).
      reasoning: { effort: reasoningEffort },
      // Server-side VAD + natural barge-in; the server commits on speech_stopped.
      // idle_timeout_ms: if Steve goes quiet after Junior finishes, the server
      // re-engages him instead of sitting in silence (E).
      turn_detection: { type: "server_vad", idle_timeout_ms: IDLE_TIMEOUT_MS },
      audio: {
        input: {
          format: { type: "audio/pcm", rate: REALTIME_SAMPLE_RATE },
          transcription: {
            model: INPUT_TRANSCRIPTION_MODEL,
            // A. Bias the ASR toward Steve's world proper nouns — SNHU, Bitsko,
            // Newsmax, Meridian, etc. — which transcription currently guesses at.
            keyterms: JUNIOR_KEYTERMS,
            language_hint: "en",
          },
        },
        output: {
          format: { type: "audio/pcm", rate: REALTIME_SAMPLE_RATE },
          // B. Playback speed, clamped to the API's 0.7–1.5 range.
          speed: clampOutputSpeed(speed),
        },
      },
      // C. Pronunciation fixes, at the session ROOT (verified live: the server
      // echoes `replace` at the root, not nested under audio).
      replace: JUNIOR_PRONUNCIATION_REPLACEMENTS,
      // Resume prior turns on reconnect; the id arrives with conversation.created.
      resumption: { enabled: true, ...(conversationId ? { conversation_id: conversationId } : {}) },
      // Tools: web search plus x_search (D — verified accepted alongside
      // web_search), then Junior's function tools over Steve's library,
      // feeds, pending work, and business email — verified live: session.update
      // accepts this tools array and the model emits
      // response.function_call_arguments events that produce real spoken
      // answers after the client returns the tool output.
      tools: [{ type: "web_search" }, { type: "x_search" }, ...JUNIOR_TOOLS],
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

/**
 * The item_id carried by a transcription.completed event, or null when absent.
 * xAI emits `conversation.item.input_audio_transcription.completed` THREE times
 * per utterance (same item_id, different event_ids — verified live against
 * api.x.ai). Callers dedupe on this so one spoken turn produces exactly one
 * transcript record.
 */
export function extractTranscriptItemId(msg: unknown): string | null {
  if (!msg || typeof msg !== "object") return null;
  const m = msg as { item_id?: unknown; item?: { id?: unknown } };
  // Top-level shape (verified live): { item_id }. Nested shape fallback —
  // extractUserTranscript also accepts { item: { content: [...] } }, so read
  // the nested item id too; without it a nested-shaped transcript would record
  // but never dedupe, silently reverting to the 3x bug.
  if (typeof m.item_id === "string" && m.item_id.length > 0) return m.item_id;
  if (typeof m.item?.id === "string" && m.item.id.length > 0) return m.item.id;
  return null;
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
