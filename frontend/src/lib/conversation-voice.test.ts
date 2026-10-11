import assert from "node:assert/strict";
import test from "node:test";
import {
  buildRealtimeUrl,
  buildSessionUpdate,
  classifyRealtimeEvent,
  clampSample,
  encodeMicChunk,
  extractAudioDelta,
  extractConversationId,
  extractUserTranscript,
  floatToPcm16Bytes,
  JUNIOR_TALK_INSTRUCTIONS,
  MIC_CHUNK_SAMPLES,
  nextBackoffDelay,
  pcm16ToBase64,
  REALTIME_MODEL,
  REALTIME_SAMPLE_RATE,
  splitMicChunks,
} from "@/lib/conversation-voice";

test("buildRealtimeUrl points at the grok-voice realtime endpoint", () => {
  assert.equal(buildRealtimeUrl(), `wss://api.x.ai/v1/realtime?model=${REALTIME_MODEL}`);
});

test("buildRealtimeUrl appends conversation_id when resuming", () => {
  const url = buildRealtimeUrl("conv-123");
  assert.ok(url.includes(`model=${REALTIME_MODEL}`));
  assert.ok(url.includes("conversation_id=conv-123"));
});

test("buildRealtimeUrl encodes conversation ids", () => {
  assert.ok(buildRealtimeUrl("a b/c").includes("conversation_id=a%20b%2Fc"));
});

test("buildRealtimeUrl omits conversation_id for a fresh session", () => {
  assert.ok(!buildRealtimeUrl(null).includes("conversation_id"));
});

test("session.update carries voice, server VAD, and 24kHz PCM in and out", () => {
  const update = buildSessionUpdate("castor");
  assert.equal(update.type, "session.update");
  const s = update.session;
  assert.equal(s.voice, "castor");
  assert.equal(s.instructions, JUNIOR_TALK_INSTRUCTIONS);
  assert.deepEqual(s.reasoning, { effort: "none" });
  assert.deepEqual(s.turn_detection, { type: "server_vad" });
  assert.deepEqual(s.audio.input.format, { type: "audio/pcm", rate: REALTIME_SAMPLE_RATE });
  assert.equal(s.audio.input.transcription.model, "grok-transcribe");
  assert.deepEqual(s.audio.output.format, { type: "audio/pcm", rate: REALTIME_SAMPLE_RATE });
});

test("session.update enables resumption and carries the id when resuming", () => {
  const fresh = buildSessionUpdate("castor");
  assert.equal(fresh.session.resumption.enabled, true);
  assert.equal(fresh.session.resumption.conversation_id, undefined);

  const resumed = buildSessionUpdate("castor", "conv-9");
  assert.equal(resumed.session.resumption.conversation_id, "conv-9");
});

test("MIC_CHUNK_SAMPLES is 100ms of audio at 24kHz", () => {
  assert.equal(MIC_CHUNK_SAMPLES, 2400);
});

test("nextBackoffDelay doubles and caps", () => {
  assert.equal(nextBackoffDelay(0), 500);
  assert.equal(nextBackoffDelay(1), 1000);
  assert.equal(nextBackoffDelay(2), 2000);
  assert.equal(nextBackoffDelay(10), 8000);
});

test("nextBackoffDelay tolerates negative and fractional attempts", () => {
  assert.equal(nextBackoffDelay(-3), 500);
  assert.equal(nextBackoffDelay(1.7), 1000);
  assert.equal(nextBackoffDelay(2.9), 2000);
});

test("classifyRealtimeEvent buckets the verified xAI events", () => {
  assert.equal(classifyRealtimeEvent("conversation.created"), "conversation");
  assert.equal(classifyRealtimeEvent("input_audio_buffer.speech_started"), "speech-start");
  assert.equal(classifyRealtimeEvent("input_audio_buffer.speech_stopped"), "speech-stop");
  assert.equal(
    classifyRealtimeEvent("conversation.item.input_audio_transcription.completed"),
    "user-transcript",
  );
  assert.equal(classifyRealtimeEvent("response.output_audio.delta"), "assistant-audio");
  assert.equal(classifyRealtimeEvent("response.audio.delta"), "assistant-audio");
  assert.equal(classifyRealtimeEvent("response.output_audio.done"), "assistant-done");
  assert.equal(classifyRealtimeEvent("response.done"), "assistant-done");
  assert.equal(classifyRealtimeEvent("session.created"), "session");
  assert.equal(classifyRealtimeEvent("session.updated"), "session");
  assert.equal(classifyRealtimeEvent("error"), "error");
  assert.equal(classifyRealtimeEvent("ping"), "other");
  assert.equal(classifyRealtimeEvent(undefined), "other");
});

test("extractUserTranscript reads the top-level transcript", () => {
  assert.equal(extractUserTranscript({ transcript: "  hello there  " }), "hello there");
});

test("extractUserTranscript reads the nested content array", () => {
  const msg = {
    item: { content: [{ type: "input_audio" }, { type: "input_audio", transcript: "nested words" }] },
  };
  assert.equal(extractUserTranscript(msg), "nested words");
});

test("extractUserTranscript returns null for blank or missing text", () => {
  assert.equal(extractUserTranscript({ transcript: "   " }), null);
  assert.equal(extractUserTranscript({}), null);
  assert.equal(extractUserTranscript(null), null);
  assert.equal(extractUserTranscript("not an object"), null);
});

test("extractAudioDelta reads both delta shapes and rejects empties", () => {
  assert.equal(extractAudioDelta({ delta: "AAAA" }), "AAAA");
  assert.equal(extractAudioDelta({ output_audio: { delta: "BBBB" } }), "BBBB");
  assert.equal(extractAudioDelta({ delta: "" }), null);
  assert.equal(extractAudioDelta({}), null);
  assert.equal(extractAudioDelta(null), null);
});

test("extractConversationId captures the resumption id", () => {
  assert.equal(extractConversationId({ conversation: { id: "conv-42" } }), "conv-42");
  assert.equal(extractConversationId({ conversation: { id: "" } }), null);
  assert.equal(extractConversationId({}), null);
  assert.equal(extractConversationId(null), null);
});

test("clampSample keeps audio in the PCM16 range", () => {
  assert.equal(clampSample(2), 1);
  assert.equal(clampSample(-2), -1);
  assert.equal(clampSample(0.5), 0.5);
});

test("floatToPcm16Bytes writes little-endian pairs matching pcm16ToFloat32", () => {
  const samples = new Float32Array([0, 1, -1, 0.5, -0.5]);
  const bytes = floatToPcm16Bytes(samples);
  assert.equal(bytes.length, samples.length * 2);
  // 0 -> 0x0000; 1 -> 0x7FFF; -1 -> 0x8000 (little-endian byte order);
  // 0.5 truncates to 16383 (0x3FFF); -0.5 is -16384 (0xC000).
  assert.deepEqual(Array.from(bytes.slice(0, 6)), [0x00, 0x00, 0xff, 0x7f, 0x00, 0x80]);
  assert.deepEqual(Array.from(bytes.slice(6, 10)), [0xff, 0x3f, 0x00, 0xc0]);
});

test("floatToPcm16Bytes clamps out-of-range input instead of wrapping", () => {
  const bytes = floatToPcm16Bytes(new Float32Array([4, -4]));
  assert.deepEqual(Array.from(bytes), [0xff, 0x7f, 0x00, 0x80]);
});

test("pcm16ToBase64 round-trips through atob", () => {
  const bytes = new Uint8Array([72, 101, 108, 108, 111]);
  const b64 = pcm16ToBase64(bytes);
  assert.equal(b64, "SGVsbG8=");
  assert.equal(atob(b64).length, 5);
});

test("encodeMicChunk produces base64 that decodes back to PCM16 pairs", () => {
  const b64 = encodeMicChunk(new Float32Array([0.5, -0.5]));
  const binary = atob(b64);
  assert.equal(binary.length, 4);
  // 0.5 -> 16383 (0x3FFF) little-endian, so byte 1 is 0x3F.
  assert.equal(binary.charCodeAt(1), 0x3f);
});

test("splitMicChunks splits into 100ms pieces and keeps the remainder", () => {
  const samples = new Float32Array(MIC_CHUNK_SAMPLES * 2 + 5);
  const chunks = splitMicChunks(samples);
  assert.equal(chunks.length, 3);
  assert.equal(chunks[0].length, MIC_CHUNK_SAMPLES);
  assert.equal(chunks[1].length, MIC_CHUNK_SAMPLES);
  assert.equal(chunks[2].length, 5);
});

test("splitMicChunks returns one chunk when under the chunk size", () => {
  const chunks = splitMicChunks(new Float32Array(10));
  assert.equal(chunks.length, 1);
  assert.equal(chunks[0].length, 10);
});

test("splitMicChunks returns nothing for empty input", () => {
  assert.deepEqual(splitMicChunks(new Float32Array(0)), []);
});
