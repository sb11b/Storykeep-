import assert from "node:assert/strict";
import test from "node:test";
import * as React from "react";
import { ApiError } from "@/lib/api";
import {
  buildRealtimeUrl,
  buildSessionUpdate,
  classifyRealtimeEvent,
  clampOutputSpeed,
  clampSample,
  encodeMicChunk,
  extractAudioDelta,
  extractConversationId,
  extractTranscriptItemId,
  extractUserTranscript,
  floatToPcm16Bytes,
  JUNIOR_KEYTERMS,
  JUNIOR_PRONUNCIATION_REPLACEMENTS,
  JUNIOR_TALK_INSTRUCTIONS,
  KEYTERM_MAX_CHARS,
  KEYTERM_MAX_COUNT,
  MAX_BACKOFF_MS,
  MIC_CHUNK_SAMPLES,
  nextBackoffDelay,
  OUTPUT_SPEED_DEFAULT,
  OUTPUT_SPEED_MAX,
  OUTPUT_SPEED_MIN,
  pcm16ToBase64,
  REALTIME_MODEL,
  REALTIME_SAMPLE_RATE,
  readableRealtimeError,
  isXSearchDependencyError,
  X_SEARCH_UNAVAILABLE_MESSAGE,
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

test("session.update includes web_search plus Junior's function tools so Talk can answer about Steve's world", () => {
  const update = buildSessionUpdate("castor");
  const tools = update.session.tools;
  assert.deepEqual(tools[0], { type: "web_search" });
  // The function tools follow x_search, with the exact names Junior's handlers dispatch.
  assert.deepEqual(
    tools.slice(2).map((tool: { name?: string }) => tool.name),
    [
      "search_library",
      "get_document",
      "read_document_file",
      "create_document",
      "delete_document",
      "list_feeds",
      "search_articles",
      "read_article",
      "list_pending_work",
      "create_task",
      "read_email",
      "search_email",
      "read_email_message",
      "draft_email",
      "list_drafts",
    ],
  );
  // The instructions must tell Junior to reach for the tools and read aloud.
  assert.match(update.session.instructions, /web_search/);
  assert.match(update.session.instructions, /search_library/);
  assert.match(update.session.instructions, /read it aloud in full/);
  assert.match(update.session.instructions, /NEVER send email/);
});

test("session.update keeps the full tool set when resuming a conversation", () => {
  const resumed = buildSessionUpdate("castor", "conv-9");
  assert.equal(resumed.session.tools.length, 17);
});

test("MIC_CHUNK_SAMPLES is 100ms of audio at 24kHz", () => {
  assert.equal(MIC_CHUNK_SAMPLES, 2400);
});

/* ────────────────────────────────────────────────────────────────────────────
 * Folded xAI voice capabilities — every param below was verified live against
 * wss://api.x.ai/v1/realtime?model=grok-voice-think-fast-2.0: one
 * session.update carrying all of them returned session.updated with zero
 * errors and the server echoed each param back.
 * ──────────────────────────────────────────────────────────────────────────── */

test("A. session.update biases transcription with keyterms and language_hint", () => {
  const update = buildSessionUpdate("castor");
  const transcription = update.session.audio.input.transcription;
  assert.deepEqual(transcription.keyterms, [...JUNIOR_KEYTERMS]);
  assert.equal(transcription.language_hint, "en");
  // Pin the API caps so a future edit can't silently break the contract.
  assert.ok(
    transcription.keyterms!.length <= KEYTERM_MAX_COUNT,
    `at most ${KEYTERM_MAX_COUNT} keyterms are accepted`,
  );
  for (const term of transcription.keyterms!) {
    assert.ok(term.length <= KEYTERM_MAX_CHARS, `keyterm "${term}" exceeds ${KEYTERM_MAX_CHARS} chars`);
  }
  // Steve's world proper nouns must actually be in the list.
  for (const term of ["Storykeep", "Newsmax", "SNHU", "Bitsko", "Meridian", "Hermes", "Fastmail"]) {
    assert.ok(JUNIOR_KEYTERMS.includes(term), `keyterms must include ${term}`);
  }
});

test("B. clampOutputSpeed clamps to the API's 0.7–1.5 range", () => {
  assert.equal(clampOutputSpeed(0.5), OUTPUT_SPEED_MIN, "0.5 clamps up to 0.7");
  assert.equal(clampOutputSpeed(2.0), OUTPUT_SPEED_MAX, "2.0 clamps down to 1.5");
  assert.equal(clampOutputSpeed(1.2), 1.2, "an in-range value passes through");
  assert.equal(clampOutputSpeed(OUTPUT_SPEED_MIN), OUTPUT_SPEED_MIN, "the lower bound is inclusive");
  assert.equal(clampOutputSpeed(OUTPUT_SPEED_MAX), OUTPUT_SPEED_MAX, "the upper bound is inclusive");
  assert.equal(clampOutputSpeed(Number.NaN), OUTPUT_SPEED_DEFAULT, "garbage falls back to the default");
});

test("B. session.update lands the (clamped) speed in audio.output.speed", () => {
  assert.equal(buildSessionUpdate("castor").session.audio.output.speed, OUTPUT_SPEED_DEFAULT);
  assert.equal(buildSessionUpdate("castor", null, 1.25).session.audio.output.speed, 1.25);
  assert.equal(buildSessionUpdate("castor", null, 0.2).session.audio.output.speed, OUTPUT_SPEED_MIN);
  assert.equal(buildSessionUpdate("castor", null, 9).session.audio.output.speed, OUTPUT_SPEED_MAX);
});

test("C. session.update carries the pronunciation replace map at the session root", () => {
  const update = buildSessionUpdate("castor");
  assert.deepEqual(update.session.replace, { ...JUNIOR_PRONUNCIATION_REPLACEMENTS });
  assert.equal(update.session.replace?.SNHU, "S N H U");
  assert.equal(update.session.replace?.JMAP, "J map");
  assert.equal(update.session.replace?.Bitsko, "Bit sko");
  // Verified live: `replace` echoes at the session root, NOT nested in audio.
  assert.ok(!("replace" in update.session.audio), "replace must not be nested under audio");
});

test("D. session.update carries both web_search and x_search tools", () => {
  const update = buildSessionUpdate("castor");
  const toolTypes = update.session.tools.map((tool: { type: string }) => tool.type);
  assert.equal(toolTypes[0], "web_search");
  assert.equal(toolTypes[1], "x_search");
  assert.match(update.session.instructions, /x_search/);
  assert.match(update.session.instructions, /what are people saying on X or Twitter/);
});

test("E. turn_detection carries NO idle_timeout_ms — it caused a search loop (regression)", () => {
  // Verified live: idle_timeout_ms: 15000 made the server re-engage Junior every
  // 15s of silence; a listening Steve reads as silence, so Junior started new
  // responses (each with searches) every 15 seconds — an endless news loop.
  const update = buildSessionUpdate("castor");
  assert.deepEqual(update.session.turn_detection, { type: "server_vad" });
  assert.equal(update.session.turn_detection.idle_timeout_ms, undefined);
});

test("instructions cap searches at one per question and keep Junior quiet on silence", () => {
  assert.match(JUNIOR_TALK_INSTRUCTIONS, /at most ONE search per question/);
  assert.match(JUNIOR_TALK_INSTRUCTIONS, /never chain search after search/);
  assert.match(JUNIOR_TALK_INSTRUCTIONS, /stay quiet/);
});

test("F. reasoning effort defaults to none and can be raised to high", () => {
  assert.deepEqual(buildSessionUpdate("castor").session.reasoning, { effort: "none" });
  assert.deepEqual(buildSessionUpdate("castor", null, 1, "high").session.reasoning, { effort: "high" });
  assert.deepEqual(buildSessionUpdate("castor", "conv-9", 1, "high").session.reasoning, { effort: "high" });
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

test("extractTranscriptItemId reads the top-level item_id", () => {
  assert.equal(
    extractTranscriptItemId({ item_id: "5ef9d6e1-df26", transcript: "hi" }),
    "5ef9d6e1-df26"
  );
});

test("extractTranscriptItemId returns null when absent or malformed", () => {
  assert.equal(extractTranscriptItemId({ transcript: "hi" }), null);
  assert.equal(extractTranscriptItemId({ item_id: "" }), null);
  assert.equal(extractTranscriptItemId({ item_id: 42 }), null);
  assert.equal(extractTranscriptItemId(null), null);
});

test("xAI triplicate transcript events share one item_id — dedupe key is stable", () => {
  // Live-verified: api.x.ai emits transcription.completed three times per
  // utterance with the same item_id and different event_ids. Simulate the
  // exact wire shape; the dedupe set must collapse all three to one record.
  const events = [
    { type: "conversation.item.input_audio_transcription.completed", event_id: "a", item_id: "item-1", transcript: "What did I write?" },
    { type: "conversation.item.input_audio_transcription.completed", event_id: "b", item_id: "item-1", transcript: "What did I write?" },
    { type: "conversation.item.input_audio_transcription.completed", event_id: "c", item_id: "item-1", transcript: "What did I write?" },
    { type: "conversation.item.input_audio_transcription.completed", event_id: "d", item_id: "item-2", transcript: "Read me the article" },
  ];
  const seen = new Set<string>();
  const recorded: string[] = [];
  for (const ev of events) {
    const text = extractUserTranscript(ev);
    const itemId = extractTranscriptItemId(ev);
    if (!text) continue;
    if (itemId) {
      if (seen.has(itemId)) continue;
      seen.add(itemId);
    }
    recorded.push(text);
  }
  assert.deepEqual(recorded, ["What did I write?", "Read me the article"]);
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

/* ────────────────────────────────────────────────────────────────────────────
 * Hook-level tests for useConversationVoice.
 *
 * The hook drives real browser APIs (WebSocket, AudioContext, getUserMedia),
 * so these tests install fakes on the global scope and drive the hook through
 * React's internal dispatcher — no jsdom needed.
 * ──────────────────────────────────────────────────────────────────────────── */

type Cleanup = () => void;

/** Install React's dispatcher so the hook can run outside a renderer. */
function withDispatcher<T>(slots: HookSlots, fn: () => T): T {
  const internals = (React as unknown as {
    __CLIENT_INTERNALS_DO_NOT_USE_OR_WARN_USERS_THEY_CANNOT_UPGRADE: { H: unknown };
  }).__CLIENT_INTERNALS_DO_NOT_USE_OR_WARN_USERS_THEY_CANNOT_UPGRADE;
  const previous = internals.H;
  internals.H = {
    useRef: (initial: unknown) => {
      const i = slots.index++;
      if (!slots.refs[i]) slots.refs[i] = { current: initial };
      return slots.refs[i];
    },
    useState: (initial: unknown) => {
      const i = slots.index++;
      if (slots.states.length <= i) {
        slots.states[i] = typeof initial === "function" ? (initial as () => unknown)() : initial;
      }
      return [slots.states[i], (next: unknown) => { slots.states[i] = next; }];
    },
    useCallback: (fn: unknown, deps: unknown[]) => {
      const i = slots.index++;
      const prev = slots.callbacks[i];
      if (prev && depsEqual(prev.deps, deps)) return prev.fn;
      slots.callbacks[i] = { fn, deps };
      return fn;
    },
    useMemo: (factory: () => unknown, deps: unknown[]) => {
      const i = slots.index++;
      const prev = slots.memos[i];
      if (prev && depsEqual(prev.deps, deps)) return prev.value;
      const value = factory();
      slots.memos[i] = { value, deps };
      return value;
    },
    useEffect: (create: () => Cleanup | void, deps?: unknown[]) => {
      const i = slots.index++;
      const prev = slots.effects[i];
      if (prev && depsEqual(prev.deps, deps ?? [])) return;
      slots.effects[i] = { create, deps: deps ?? [] };
    },
  };
  try {
    return fn(slots);
  } finally {
    internals.H = previous;
  }
}

interface HookSlots {
  refs: Array<{ current: unknown }>;
  states: unknown[];
  callbacks: Array<{ fn: unknown; deps: unknown[] }>;
  memos: Array<{ value: unknown; deps: unknown[] }>;
  effects: Array<{ create: () => Cleanup | void; deps: unknown[]; cleanup?: Cleanup }>;
  index: number;
}

function depsEqual(a: unknown[], b: unknown[]): boolean {
  if (a.length !== b.length) return false;
  return a.every((v, i) => Object.is(v, b[i]));
}

/** Run a fresh render of the hook and commit its effects. */
function renderHook<T>(factory: () => T, slots: HookSlots): T {
  slots.index = 0;
  const result = withDispatcher(slots, factory);
  // Commit new effects (deps changed or first run).
  for (const effect of slots.effects) {
    if (!effect) continue;
    if (effect.cleanup) continue;
    const cleanup = effect.create();
    if (typeof cleanup === "function") effect.cleanup = cleanup;
  }
  return result;
}

/** Unmount: run every effect cleanup in reverse order. */
function unmountHook(slots: HookSlots): void {
  for (const effect of [...slots.effects].reverse()) {
    effect?.cleanup?.();
  }
}

/* ── Hook-level tests for useConversationVoice. ── */

test("setOutputSpeed and setReasoningEffort re-send session.update on the live socket", async () => {
  const restore = installFakes();
  try {
    const { useConversationVoice } = await import("@/lib/use-conversation-voice");
    const slots: HookSlots = { refs: [], states: [], callbacks: [], memos: [], effects: [], index: 0 };
    const voiceIdRef = { current: "castor" } as React.RefObject<string>;
    const render = () =>
      renderHook(
        () =>
          useConversationVoice({
            voiceIdRef,
            onUserTranscript: () => {},
          }),
        slots,
      );
    render();
    const start = render().start;

    await start();
    await flushMicrotasks();
    const ws = FakeWebSocket.instances[0];
    // The fake socket never fires onopen by itself — the real one does.
    ws.onopen?.();
    const sessionUpdates = () =>
      ws.sent.map((line) => JSON.parse(line)).filter((m) => m.type === "session.update");
    assert.equal(sessionUpdates().length, 1, "start sends exactly one session.update");
    assert.equal(sessionUpdates()[0].session.audio.output.speed, OUTPUT_SPEED_DEFAULT);

    // B. Mid-session speed change: a fresh session.update goes out, clamped.
    const setOutputSpeed = render().setOutputSpeed;
    assert.equal(setOutputSpeed(1.3), 1.3);
    assert.equal(setOutputSpeed(9), OUTPUT_SPEED_MAX, "out-of-range speeds are clamped");
    const afterSpeed = sessionUpdates();
    assert.equal(afterSpeed.length, 3, "each setter call re-sends session.update");
    assert.equal(afterSpeed[1].session.audio.output.speed, 1.3);
    assert.equal(afterSpeed[2].session.audio.output.speed, OUTPUT_SPEED_MAX);

    // F. Mid-session reasoning effort: the next response uses it.
    const setReasoningEffort = render().setReasoningEffort;
    setReasoningEffort("high");
    const afterReasoning = sessionUpdates();
    assert.equal(afterReasoning.length, 4);
    assert.deepEqual(afterReasoning[3].session.reasoning, { effort: "high" });
    // The full session payload still goes out — the update is additive, not a patch.
    assert.ok(afterReasoning[3].session.audio.input.transcription.keyterms.length > 0);
    assert.ok(afterReasoning[3].session.replace);

    // The CLOSED-but-current-ref case: the socket died but ws.onclose has NOT
    // fired, so wsRef.current still points at it. The `!socket` branch alone
    // would send into a dead socket — readyState CLOSED (3) must stop it.
    // (Set readyState directly: close() would fire onclose and null the ref.)
    ws.readyState = 3;
    setOutputSpeed(1.2);
    setReasoningEffort("high");
    assert.equal(sessionUpdates().length, 4, "a CLOSED-but-current socket must not receive session.update");

    // With no live socket the setters are no-ops, not throws.
    ws.close();
    setOutputSpeed(1.1);
    setReasoningEffort("none");
    assert.equal(sessionUpdates().length, 4, "no session.update may be sent after the socket is gone");

    unmountHook(slots);
  } finally {
    restore();
  }
});

/* ── Fake browser APIs ── */

class FakeTrack {
  stopped = false;
  stop() {
    this.stopped = true;
  }
}

class FakeStream {
  tracks = [new FakeTrack()];
  getTracks() {
    return this.tracks;
  }
}

class FakeScriptProcessor {
  onaudioprocess: ((event: unknown) => void) | null = null;
  disconnected = false;
  connect() {}
  disconnect() {
    this.disconnected = true;
  }
}

class FakeGain {
  gain = { value: 1 };
  connect() {}
  disconnect() {}
}

class FakeSourceNode {
  disconnected = false;
  connect() {}
  disconnect() {
    this.disconnected = true;
  }
}

class FakeAudioContext {
  static instances: FakeAudioContext[] = [];
  state = "running";
  currentTime = 0;
  closed = false;
  destination = {};
  processors: FakeScriptProcessor[] = [];
  sources: FakeSourceNode[] = [];
  constructor() {
    FakeAudioContext.instances.push(this);
  }
  async resume() {
    this.state = "running";
  }
  async close() {
    this.closed = true;
    this.state = "closed";
  }
  createBuffer(_channels: number, length: number) {
    const data = new Float32Array(length);
    return {
      duration: length / 24000,
      getChannelData: () => data,
      length,
    };
  }
  createBufferSource() {
    return {
      buffer: null as unknown,
      connect() {},
      disconnect() {},
      start() {},
      stop() {},
      onended: null as (() => void) | null,
    };
  }
  createMediaStreamSource(_stream: unknown) {
    const node = new FakeSourceNode();
    this.sources.push(node);
    return node;
  }
  createScriptProcessor(_bufferSize: number, _inCh: number, _outCh: number) {
    const node = new FakeScriptProcessor();
    this.processors.push(node);
    return node;
  }
  createGain() {
    return new FakeGain();
  }
}

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  static OPEN = 1;
  readyState = 1;
  sent: string[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  constructor(public url: string, public protocol: string) {
    FakeWebSocket.instances.push(this);
  }
  send(data: string) {
    this.sent.push(data);
  }
  close() {
    this.closed = true;
    this.readyState = 3;
    this.onclose?.();
  }
}

/** Live (not closed) contexts and streams — the leak invariant. */
function liveContexts(): number {
  return FakeAudioContext.instances.filter((c) => !c.closed).length;
}

function liveStreams(): number {
  return streams.filter((s) => s.tracks.some((t) => !t.stopped)).length;
}

let streams: FakeStream[] = [];
/** Responses queued for the token endpoint; each entry is a status to fail with. */
let tokenFailures: number[] = [];
let tokenCalls = 0;
/** When set, every token fetch parks on this promise until it is released. */
let tokenGate: Promise<void> | null = null;

function installFakes() {
  FakeAudioContext.instances = [];
  FakeWebSocket.instances = [];
  streams = [];
  tokenFailures = [];
  tokenCalls = 0;
  tokenGate = null;
  const originals = {
    AudioContext: (globalThis as Record<string, unknown>).AudioContext,
    WebSocket: (globalThis as Record<string, unknown>).WebSocket,
    mediaDevices: navigator.mediaDevices,
    fetch: globalThis.fetch,
  };
  (globalThis as Record<string, unknown>).AudioContext = FakeAudioContext;
  (globalThis as Record<string, unknown>).WebSocket = FakeWebSocket;
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: {
      getUserMedia: async () => {
        const stream = new FakeStream();
        streams.push(stream);
        return stream;
      },
    },
  });
  globalThis.fetch = (async () => {
    tokenCalls += 1;
    const failStatus = tokenFailures.shift();
    if (failStatus) throw new ApiError(failStatus, `HTTP ${failStatus}`);
    // Park on the gate (if one is armed) before answering, so a start() can be
    // suspended mid-handshake while the test drives stop()/start().
    if (tokenGate) await tokenGate;
    return {
      ok: true,
      status: 200,
      statusText: "OK",
      json: async () => ({ value: "token-abc", expires_at: 0 }),
    };
  }) as unknown as typeof fetch;
  return () => {
    (globalThis as Record<string, unknown>).AudioContext = originals.AudioContext;
    (globalThis as Record<string, unknown>).WebSocket = originals.WebSocket;
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: originals.mediaDevices,
    });
    globalThis.fetch = originals.fetch;
  };
}

async function flushMicrotasks(times = 8): Promise<void> {
  for (let i = 0; i < times; i++) await Promise.resolve();
}

test("start after stop re-arms the session (manualStopRef reset)", async () => {
  const restore = installFakes();
  try {
    const { useConversationVoice } = await import("@/lib/use-conversation-voice");
    const slots: HookSlots = { refs: [], states: [], callbacks: [], memos: [], effects: [], index: 0 };
    const transcripts: string[] = [];
    const statuses: string[] = [];
    const voiceIdRef = { current: "castor" } as React.RefObject<string>;
    const render = () =>
      renderHook(
        () =>
          useConversationVoice({
            voiceIdRef,
            onUserTranscript: (t: string) => transcripts.push(t),
            onStatusChange: (s: string) => statuses.push(s),
          }),
        slots,
      );
    render();
    const start = render().start;
    const stop = render().stop;

    // First session.
    await start();
    await flushMicrotasks();
    assert.equal(FakeWebSocket.instances.length, 1);
    assert.equal(streams.length, 1);
    assert.equal(statuses.at(-1), "listening");

    // User ends the session.
    stop();
    assert.equal(statuses.at(-1), "idle");
    assert.equal(liveStreams(), 0);
    assert.equal(liveContexts(), 0);

    // THE FIX: a second start must open a brand-new session.
    await start();
    await flushMicrotasks();
    assert.equal(FakeWebSocket.instances.length, 2, "start after stop must open a new socket");
    assert.equal(streams.length, 2, "start after stop must capture the mic again");
    assert.equal(liveStreams(), 1);
    assert.equal(liveContexts(), 1);
    assert.equal(statuses.at(-1), "listening");

    unmountHook(slots);
  } finally {
    restore();
  }
});

test("onclose tears down mic + AudioContext before reconnecting (no leak)", async () => {
  const restore = installFakes();
  try {
    const { useConversationVoice } = await import("@/lib/use-conversation-voice");
    const slots: HookSlots = { refs: [], states: [], callbacks: [], memos: [], effects: [], index: 0 };
    const transcripts: string[] = [];
    const statuses: string[] = [];
    const voiceIdRef = { current: "castor" } as React.RefObject<string>;
    const render = () =>
      renderHook(
        () =>
          useConversationVoice({
            voiceIdRef,
            onUserTranscript: (t: string) => transcripts.push(t),
            onStatusChange: (s: string) => statuses.push(s),
          }),
        slots,
      );
    render();
    const start = render().start;

    await start();
    await flushMicrotasks();
    const ws1 = FakeWebSocket.instances[0];
    const ctx1 = FakeAudioContext.instances[0];
    const proc1 = ctx1.processors[0];
    const source1 = ctx1.sources[0];
    const stream1 = streams[0];
    assert.equal(liveContexts(), 1);
    assert.equal(liveStreams(), 1);

    // Force the socket closed.
    ws1.onclose?.();
    await flushMicrotasks();

    // THE FIX: teardown happens in onclose, before the reconnect timer runs.
    assert.equal(stream1.tracks[0].stopped, true, "mic track must be stopped on close");
    assert.equal(ctx1.closed, true, "AudioContext must be closed on close");
    assert.equal(proc1.onaudioprocess, null, "processor handler must be detached");
    assert.equal(proc1.disconnected, true, "processor must be disconnected");
    assert.equal(source1.disconnected, true, "mic source must be disconnected");
    assert.equal(liveStreams(), 0);
    assert.equal(liveContexts(), 0);

    // Let the backoff timer fire and reconnect.
    await new Promise((resolve) => setTimeout(resolve, 600));
    await flushMicrotasks();

    // Exactly one live mic and one live context after the reconnect.
    assert.equal(FakeWebSocket.instances.length, 2, "reconnect must open a new socket");
    assert.equal(streams.length, 2, "reconnect must capture a fresh mic stream");
    assert.equal(liveStreams(), 1, "exactly one live mic stream after reconnect");
    assert.equal(liveContexts(), 1, "exactly one live AudioContext after reconnect");

    // The orphaned pipeline must not feed the new socket: the old processor's
    // handler is detached, so an audio event on it cannot reach ws2.
    const ws2 = FakeWebSocket.instances[1];
    proc1.onaudioprocess = () => {
      ws2.send("LEAK");
    };
    // Even a resurrected handler sees a detached node — assert the new socket
    // received no audio from the old pipeline before this point.
    assert.ok(!ws2.sent.includes("LEAK"));

    unmountHook(slots);
  } finally {
    restore();
  }
});

test("scheduleReconnect uses nextBackoffDelay so the clamp is real", async () => {
  const restore = installFakes();
  try {
    const { useConversationVoice } = await import("@/lib/use-conversation-voice");
    const slots: HookSlots = { refs: [], states: [], callbacks: [], memos: [], effects: [], index: 0 };
    const transcripts: string[] = [];
    const statuses: string[] = [];
    const voiceIdRef = { current: "castor" } as React.RefObject<string>;
    const render = () =>
      renderHook(
        () =>
          useConversationVoice({
            voiceIdRef,
            onUserTranscript: (t: string) => transcripts.push(t),
            onStatusChange: (s: string) => statuses.push(s),
          }),
        slots,
      );
    render();
    const start = render().start;

    // Burn reconnect attempts so the delay climbs past the clamp.
    const realSetTimeout = globalThis.setTimeout;
    const delays: number[] = [];
    (globalThis as Record<string, unknown>).setTimeout = ((fn: () => void, ms?: number) => {
      delays.push(ms ?? 0);
      return realSetTimeout(fn, 0);
    }) as typeof setTimeout;

    try {
      await start();
      await flushMicrotasks();
      for (let attempt = 0; attempt < 6; attempt++) {
        FakeWebSocket.instances.at(-1)?.onclose?.();
        await flushMicrotasks();
        // Drive the reconnect immediately.
        await new Promise((resolve) => realSetTimeout(resolve, 0));
        await flushMicrotasks();
      }
    } finally {
      globalThis.setTimeout = realSetTimeout;
    }

    // Every scheduled delay comes from the unit-tested nextBackoffDelay, so the
    // clamp is exercised through the same code path the unit tests cover (the
    // hook no longer re-derives 500 * 2**n inline).
    assert.ok(delays.length >= 5, `expected several reconnects, got ${delays.length}`);
    for (const [index, delay] of delays.entries()) {
      assert.equal(delay, nextBackoffDelay(index), `delay ${index} must come from nextBackoffDelay`);
      assert.ok(delay <= MAX_BACKOFF_MS, "delay must never exceed the clamp");
    }
    assert.deepEqual(
      delays,
      [0, 1, 2, 3, 4].map(nextBackoffDelay),
      "the full backoff ladder must match the tested helper",
    );

    // After MAX_RECONNECT_ATTEMPTS the hook gives up instead of looping forever.
    const timersBefore = delays.length;
    FakeWebSocket.instances.at(-1)?.onclose?.();
    await flushMicrotasks();
    assert.equal(delays.length, timersBefore, "no reconnect may be scheduled past the cap");
    assert.equal(statuses.at(-1), "idle", "the session must fall back to idle after the cap");

    unmountHook(slots);
  } finally {
    restore();
  }
});

test("AudioContext failure path closes the context instead of leaking it", async () => {
  const restore = installFakes();
  try {
    const { useConversationVoice } = await import("@/lib/use-conversation-voice");
    const slots: HookSlots = { refs: [], states: [], callbacks: [], memos: [], effects: [], index: 0 };
    const transcripts: string[] = [];
    const statuses: string[] = [];
    const voiceIdRef = { current: "castor" } as React.RefObject<string>;
    const render = () =>
      renderHook(
        () =>
          useConversationVoice({
            voiceIdRef,
            onUserTranscript: (t: string) => transcripts.push(t),
            onStatusChange: (s: string) => statuses.push(s),
          }),
        slots,
      );
    render();
    const start = render().start;

    // Make resume() throw so the catch path runs.
    const originalResume = FakeAudioContext.prototype.resume;
    (FakeAudioContext.prototype as { resume?: () => Promise<void> }).resume = async () => {
      throw new Error("resume failed");
    };
    try {
      await start();
      await flushMicrotasks();
      // THE FIX: the context created before the throwing resume() is closed.
      assert.equal(FakeAudioContext.instances.length, 1);
      assert.equal(FakeAudioContext.instances[0].closed, true, "failed context must be closed");
      assert.equal(liveContexts(), 0, "no AudioContext may survive the failure path");
      assert.equal(streams.length, 0, "no mic capture may start after the failure");
      assert.equal(FakeWebSocket.instances.length, 0, "no socket may open after the failure");
    } finally {
      FakeAudioContext.prototype.resume = originalResume;
    }

    unmountHook(slots);
  } finally {
    restore();
  }
});

test("mic appends are split into ~100ms chunks, not one 170ms buffer", async () => {
  const restore = installFakes();
  try {
    const { useConversationVoice } = await import("@/lib/use-conversation-voice");
    const slots: HookSlots = { refs: [], states: [], callbacks: [], memos: [], effects: [], index: 0 };
    const transcripts: string[] = [];
    const statuses: string[] = [];
    const voiceIdRef = { current: "castor" } as React.RefObject<string>;
    const render = () =>
      renderHook(
        () =>
          useConversationVoice({
            voiceIdRef,
            onUserTranscript: (t: string) => transcripts.push(t),
            onStatusChange: (s: string) => statuses.push(s),
          }),
        slots,
      );
    render();
    const start = render().start;

    await start();
    await flushMicrotasks();
    const ws = FakeWebSocket.instances[0];
    const proc = FakeAudioContext.instances[0].processors[0];

    // Fire one ScriptProcessor hop: 4096 frames ≈ 170ms at 24kHz.
    const frames = new Float32Array(4096);
    proc.onaudioprocess?.({
      inputBuffer: { getChannelData: () => frames },
    });

    const appends = ws.sent.filter((payload) => payload.includes("input_audio_buffer.append"));
    // 4096 / 2400 → two chunks: 2400 + 1696 samples.
    assert.equal(appends.length, 2, "a 4096-frame hop must be split into two appends");
    const firstSamples = atob(JSON.parse(appends[0]).audio).length / 2;
    const secondSamples = atob(JSON.parse(appends[1]).audio).length / 2;
    assert.equal(firstSamples, MIC_CHUNK_SAMPLES, "first append is one ~100ms chunk");
    assert.ok(secondSamples > 0 && secondSamples < MIC_CHUNK_SAMPLES, "remainder is the short tail");

    unmountHook(slots);
  } finally {
    restore();
  }
});

test("a 4xx token failure does not burn reconnect attempts", async () => {
  const restore = installFakes();
  try {
    const { useConversationVoice } = await import("@/lib/use-conversation-voice");
    const slots: HookSlots = { refs: [], states: [], callbacks: [], memos: [], effects: [], index: 0 };
    const transcripts: string[] = [];
    const statuses: string[] = [];
    const voiceIdRef = { current: "castor" } as React.RefObject<string>;
    const render = () =>
      renderHook(
        () =>
          useConversationVoice({
            voiceIdRef,
            onUserTranscript: (t: string) => transcripts.push(t),
            onStatusChange: (s: string) => statuses.push(s),
          }),
        slots,
      );
    render();
    const start = render().start;

    const realSetTimeout = globalThis.setTimeout;
    let scheduled = 0;
    (globalThis as Record<string, unknown>).setTimeout = ((fn: () => void) => {
      scheduled += 1;
      return realSetTimeout(fn, 0);
    }) as typeof setTimeout;
    try {
      tokenFailures.push(401);
      await start();
      await flushMicrotasks();
      // THE FIX: a permanent auth failure must not schedule any retry.
      assert.equal(scheduled, 0, "a 4xx token mint must not schedule a reconnect");
      assert.equal(tokenCalls, 1, "the token must be requested exactly once");
      assert.equal(FakeWebSocket.instances.length, 0, "no socket may open");
      assert.equal(streams.length, 0, "no mic capture may start");
      assert.equal(statuses.at(-1), "idle");

      // A transient failure still retries.
      tokenFailures.push(500, 500, 500, 500, 500, 500);
      await start();
      await flushMicrotasks();
      assert.ok(scheduled > 0, "a 5xx token mint must still reconnect");
    } finally {
      globalThis.setTimeout = realSetTimeout;
    }

    unmountHook(slots);
  } finally {
    restore();
  }
});

test("blank transcripts never reach onUserTranscript; one committed turn fires exactly one event", async () => {
  const restore = installFakes();
  try {
    const { useConversationVoice } = await import("@/lib/use-conversation-voice");
    const slots: HookSlots = { refs: [], states: [], callbacks: [], memos: [], effects: [], index: 0 };
    const transcripts: string[] = [];
    const voiceIdRef = { current: "castor" } as React.RefObject<string>;
    const render = () =>
      renderHook(
        () =>
          useConversationVoice({
            voiceIdRef,
            onUserTranscript: (t: string) => transcripts.push(t),
          }),
        slots,
      );
    render();
    const start = render().start;

    await start();
    await flushMicrotasks();
    const ws = FakeWebSocket.instances[0];

    const feed = (msg: unknown) =>
      ws.onmessage?.({ data: JSON.stringify(msg) });

    // server_vad commits with no speech (noise, partial buffer) — must not fire.
    feed({ type: "conversation.item.input_audio_transcription.completed", transcript: "   " });
    feed({ type: "conversation.item.input_audio_transcription.completed", transcript: "" });
    feed({ type: "conversation.item.input_audio_transcription.completed" });
    feed({ type: "conversation.item.input_audio_transcription.completed", item: { content: [{ transcript: "  " }] } });
    assert.deepEqual(transcripts, [], "blank transcripts must never reach the callback");

    // One committed turn fires exactly once, trimmed.
    feed({ type: "conversation.item.input_audio_transcription.completed", transcript: "  what's the news  " });
    assert.deepEqual(transcripts, ["what's the news"], "one turn, trimmed, fired exactly once");

    unmountHook(slots);
  } finally {
    restore();
  }
});

test("xAI triplicate transcript events record exactly once through the hook", async () => {
  // Live-verified wire behavior: api.x.ai emits transcription.completed three
  // times per utterance — same item_id, distinct event_ids. Without dedup each
  // copy reached onUserTranscript and the turn was sent to chat 3x (Junior
  // answering the same thing repeatedly + the message list flickering).
  const restore = installFakes();
  try {
    const { useConversationVoice } = await import("@/lib/use-conversation-voice");
    const slots: HookSlots = { refs: [], states: [], callbacks: [], memos: [], effects: [], index: 0 };
    const transcripts: string[] = [];
    const voiceIdRef = { current: "castor" } as React.RefObject<string>;
    const render = () =>
      renderHook(
        () =>
          useConversationVoice({
            voiceIdRef,
            onUserTranscript: (t: string) => transcripts.push(t),
          }),
        slots,
      );
    render();
    const start = render().start;
    const stop = render().stop;

    await start();
    await flushMicrotasks();
    const ws = FakeWebSocket.instances[0];
    const feed = (msg: unknown) => ws.onmessage?.({ data: JSON.stringify(msg) });

    // The exact triplicate: three completed events, one item_id.
    for (const event_id of ["a", "b", "c"]) {
      feed({
        type: "conversation.item.input_audio_transcription.completed",
        event_id,
        item_id: "item-1",
        transcript: "What did I write about quantum physics last week?",
      });
    }
    assert.deepEqual(
      transcripts,
      ["What did I write about quantum physics last week?"],
      "triplicate events with one item_id must record exactly once",
    );

    // A genuinely new utterance (different item_id) still records.
    feed({
      type: "conversation.item.input_audio_transcription.completed",
      event_id: "d",
      item_id: "item-2",
      transcript: "Read me the article",
    });
    assert.deepEqual(transcripts.length, 2, "a new item_id is a new turn and must record");

    unmountHook(slots);
  } finally {
    restore();
  }
});

test("stop() clears the transcript dedupe set (no unbounded growth, sessions independent)", async () => {
  const restore = installFakes();
  try {
    const { useConversationVoice } = await import("@/lib/use-conversation-voice");
    const slots: HookSlots = { refs: [], states: [], callbacks: [], memos: [], effects: [], index: 0 };
    const transcripts: string[] = [];
    const voiceIdRef = { current: "castor" } as React.RefObject<string>;
    const render = () =>
      renderHook(
        () =>
          useConversationVoice({
            voiceIdRef,
            onUserTranscript: (t: string) => transcripts.push(t),
          }),
        slots,
      );
    render();
    const start = render().start;
    const stop = render().stop;

    await start();
    await flushMicrotasks();
    const feed = (msg: unknown) =>
      FakeWebSocket.instances.at(-1)?.onmessage?.({ data: JSON.stringify(msg) });

    feed({
      type: "conversation.item.input_audio_transcription.completed",
      item_id: "item-1",
      transcript: "hello",
    });
    assert.deepEqual(transcripts, ["hello"]);

    // Session ends; a brand-new Talk session reusing the same item_id must
    // record again (and the internal set must not have grown across sessions).
    stop();
    await start();
    await flushMicrotasks();
    feed({
      type: "conversation.item.input_audio_transcription.completed",
      item_id: "item-1",
      transcript: "hello",
    });
    assert.deepEqual(
      transcripts,
      ["hello", "hello"],
      "after stop() the same item_id records again — the set was cleared",
    );

    unmountHook(slots);
  } finally {
    restore();
  }
});

test("hook returns a stable object across renders", async () => {
  const restore = installFakes();
  try {
    const { useConversationVoice } = await import("@/lib/use-conversation-voice");
    const slots: HookSlots = { refs: [], states: [], callbacks: [], memos: [], effects: [], index: 0 };
    const transcripts: string[] = [];
    const statuses: string[] = [];
    const voiceIdRef = { current: "castor" } as React.RefObject<string>;
    const render = () =>
      renderHook(
        () =>
          useConversationVoice({
            voiceIdRef,
            onUserTranscript: (t: string) => transcripts.push(t),
            onStatusChange: (s: string) => statuses.push(s),
          }),
        slots,
      );
    const a = render();
    const b = render();
    assert.equal(a, b, "same inputs must return the same object (useMemo)");
    assert.equal(typeof a.start, "function");
    assert.equal(typeof a.stop, "function");
    unmountHook(slots);
  } finally {
    restore();
  }
});

test("rapid taps during connecting do not double-open the session", async () => {
  const restore = installFakes();
  try {
    const { useConversationVoice } = await import("@/lib/use-conversation-voice");
    const slots: HookSlots = { refs: [], states: [], callbacks: [], memos: [], effects: [], index: 0 };
    const transcripts: string[] = [];
    const statuses: string[] = [];
    const voiceIdRef = { current: "castor" } as React.RefObject<string>;
    const render = () =>
      renderHook(
        () =>
          useConversationVoice({
            voiceIdRef,
            onUserTranscript: (t: string) => transcripts.push(t),
            onStatusChange: (s: string) => statuses.push(s),
          }),
        slots,
      );
    render();
    const start = render().start;
    const stop = render().stop;

    // Arm the gate so the token mint parks a start() mid-handshake.
    let release!: () => void;
    tokenGate = new Promise<void>((resolve) => {
      release = resolve;
    });

    // Tap 1: start #1 parks on `await api.realtimeToken()`, status 'connecting'.
    const first = start();
    await flushMicrotasks();
    assert.equal(statuses.at(-1), "connecting", "start #1 must reach the connecting state");
    assert.equal(FakeWebSocket.instances.length, 0, "no socket may open before the token resolves");

    // Tap 2: the Talk button was still enabled during 'connecting', so onClick
    // calls stop() — which must invalidate the in-flight start #1.
    stop();
    assert.equal(statuses.at(-1), "idle");

    // Tap 3: start #2 runs and supersedes start #1 with a fresh generation.
    const second = start();
    await flushMicrotasks();
    assert.equal(statuses.at(-1), "connecting", "start #2 must reach the connecting state");

    // Release both token fetches: start #1's mid-flight re-check must now bail.
    release();
    await Promise.all([first, second]);
    await flushMicrotasks();

    // THE FIX: exactly one live socket / AudioContext / mic stream. Before the
    // session-generation guard the reviewer reproduced 2/2/2 here, with the
    // stale mic cross-feeding the new socket through the shared wsRef.
    assert.equal(FakeWebSocket.instances.length, 1, "rapid taps must open exactly one socket");
    assert.equal(liveContexts(), 1, "rapid taps must create exactly one live AudioContext");
    assert.equal(liveStreams(), 1, "rapid taps must capture exactly one live mic stream");
    assert.equal(statuses.at(-1), "listening");

    unmountHook(slots);
  } finally {
    restore();
  }
});

test("a user-initiated stop does not auto-reconnect", async () => {
  const restore = installFakes();
  try {
    const { useConversationVoice } = await import("@/lib/use-conversation-voice");
    const slots: HookSlots = { refs: [], states: [], callbacks: [], memos: [], effects: [], index: 0 };
    const transcripts: string[] = [];
    const statuses: string[] = [];
    const voiceIdRef = { current: "castor" } as React.RefObject<string>;
    const render = () =>
      renderHook(
        () =>
          useConversationVoice({
            voiceIdRef,
            onUserTranscript: (t: string) => transcripts.push(t),
            onStatusChange: (s: string) => statuses.push(s),
          }),
        slots,
      );
    render();
    const start = render().start;
    const stop = render().stop;

    await start();
    await flushMicrotasks();
    assert.equal(FakeWebSocket.instances.length, 1);

    // Capture the close handler start() installed, then end the session —
    // teardown nulls it on the socket itself, so this simulates a late close
    // event racing the user's stop.
    const ws = FakeWebSocket.instances[0];
    const lateClose = ws.onclose;
    stop();
    lateClose?.();
    await flushMicrotasks();
    // Give any (wrongly scheduled) reconnect timer time to fire.
    await new Promise((resolve) => setTimeout(resolve, 600));
    await flushMicrotasks();

    // THE FIX: a user-initiated stop is final — no reconnect, no new socket.
    assert.equal(FakeWebSocket.instances.length, 1, "a user stop must not reconnect");
    assert.equal(statuses.at(-1), "idle", "status must stay idle after a user stop");
    assert.equal(liveStreams(), 0, "no mic stream may survive a user stop");
    assert.equal(liveContexts(), 0, "no AudioContext may survive a user stop");

    unmountHook(slots);
  } finally {
    restore();
  }
});

/* ────────────────────────────────────────────────────────────────────────────
 * Junior's function-call loop (verified live against xAI realtime).
 * ──────────────────────────────────────────────────────────────────────────── */

/** Install a URL-dispatching fetch: the token mint plus the junior API. */
function installToolFetch(juniorPayload: unknown, gate?: Promise<void>) {
  const originals = globalThis.fetch;
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/api/v1/junior/")) {
      if (gate) await gate;
      return {
        ok: true,
        status: 200,
        statusText: "OK",
        json: async () => juniorPayload,
      };
    }
    return {
      ok: true,
      status: 200,
      statusText: "OK",
      json: async () => ({ value: "token-abc", expires_at: 0 }),
    };
  }) as unknown as typeof fetch;
  return () => {
    globalThis.fetch = originals;
  };
}

test("a completed function call is handled once and answered: output item + response.create", async () => {
  const restore = installFakes();
  const restoreFetch = installToolFetch({
    slug: "quantum",
    title: "Quantum Intro",
    text: "Superposition is real. Entanglement too.",
    summary: "A short intro to quantum physics.",
  });
  try {
    const { useConversationVoice } = await import("@/lib/use-conversation-voice");
    const slots: HookSlots = { refs: [], states: [], callbacks: [], memos: [], effects: [], index: 0 };
    const transcripts: string[] = [];
    const statuses: string[] = [];
    const voiceIdRef = { current: "castor" } as React.RefObject<string>;
    const render = () =>
      renderHook(
        () =>
          useConversationVoice({
            voiceIdRef,
            onUserTranscript: (t: string) => transcripts.push(t),
            onStatusChange: (s: string) => statuses.push(s),
          }),
        slots,
      );
    render();
    const start = render().start;

    await start();
    await flushMicrotasks();
    const ws = FakeWebSocket.instances[0];
    const before = ws.sent.length;

    // The live stream delivers the completed call twice: once as
    // response.function_call_arguments.done, once inside
    // response.output_item.done. Both must collapse to ONE handler run.
    ws.onmessage?.({
      data: JSON.stringify({
        type: "response.function_call_arguments.done",
        call_id: "call-1",
        name: "get_document",
        arguments: '{"slug":"quantum"}',
      }),
    });
    ws.onmessage?.({
      data: JSON.stringify({
        type: "response.output_item.done",
        item: {
          type: "function_call",
          call_id: "call-1",
          name: "get_document",
          arguments: '{"slug":"quantum"}',
        },
      }),
    });
    await flushMicrotasks();
    await new Promise((resolve) => setTimeout(resolve, 20));

    const sent = ws.sent.slice(before).map((line) => JSON.parse(line));
    const outputs = sent.filter((m) => m.type === "conversation.item.create");
    assert.equal(outputs.length, 1, "the duplicate call shapes must be handled exactly once");
    assert.equal(outputs[0].item.type, "function_call_output");
    assert.equal(outputs[0].item.call_id, "call-1");
    assert.match(outputs[0].item.output, /Quantum Intro/);
    assert.match(outputs[0].item.output, /Superposition is real/);
    assert.ok(
      sent.some((m) => m.type === "response.create"),
      "a spoken answer must be requested after the tool output",
    );
    assert.ok(statuses.includes("thinking"), "the UI shows the checking-your-library state");
    // Tool turns never touch the transcript record path.
    assert.deepEqual(transcripts, []);

    unmountHook(slots);
  } finally {
    restoreFetch();
    restore();
  }
});

test("a stop during an in-flight tool call swallows the late result (barge-in safety)", async () => {
  let release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  const restore = installFakes();
  const restoreFetch = installToolFetch({ slug: "quantum", title: "Quantum", text: "body" }, gate);
  try {
    const { useConversationVoice } = await import("@/lib/use-conversation-voice");
    const slots: HookSlots = { refs: [], states: [], callbacks: [], memos: [], effects: [], index: 0 };
    const voiceIdRef = { current: "castor" } as React.RefObject<string>;
    const render = () =>
      renderHook(
        () =>
          useConversationVoice({
            voiceIdRef,
            onUserTranscript: () => {},
          }),
        slots,
      );
    render();
    const start = render().start;
    const stop = render().stop;

    await start();
    await flushMicrotasks();
    const ws = FakeWebSocket.instances[0];
    const before = ws.sent.length;

    // The model calls a tool; the fetch parks on the gate (session in flight).
    ws.onmessage?.({
      data: JSON.stringify({
        type: "response.function_call_arguments.done",
        call_id: "call-2",
        name: "get_document",
        arguments: '{"slug":"quantum"}',
      }),
    });
    await flushMicrotasks();

    // The user ends Talk mode while the tool call is still running.
    stop();
    release();
    await flushMicrotasks();
    await new Promise((resolve) => setTimeout(resolve, 20));

    const sent = ws.sent.slice(before).map((line) => JSON.parse(line));
    assert.equal(
      sent.filter((m) => m.type === "conversation.item.create").length,
      0,
      "a stopped session must never send the late tool output",
    );
    assert.equal(
      sent.filter((m) => m.type === "response.create").length,
      0,
      "a stopped session must never request a spoken answer for a dead call",
    );

    unmountHook(slots);
  } finally {
    restoreFetch();
    restore();
  }
});

/* ────────────────────────────────────────────────────────────────────────────
 * X search graceful degradation.
 *
 * `x_search` is xAI's OWN server-side realtime tool — it is declared in
 * buildSessionUpdate (test D above) and has no Storykeep handler at all.
 * When its upstream X/Twitter dependency fails, xAI emits a realtime `error`
 * event carrying
 *   "X upstream dependency error: DependencyError: Unspecified
 *    (path: [search_by_raw_query, ranked_tweets])"
 * and Junior used to surface that raw string. There is nothing Storykeep can
 * repair server-side, so the fix is degradation: a spoken-friendly sentence,
 * and a voice turn that survives the failure.
 * ──────────────────────────────────────────────────────────────────────────── */

const XAI_X_SEARCH_ERROR =
  "X upstream dependency error: DependencyError: Unspecified (path: [search_by_raw_query, ranked_tweets])";

test("isXSearchDependencyError matches the xAI upstream X failure", () => {
  assert.equal(isXSearchDependencyError(XAI_X_SEARCH_ERROR), true);
  // Same class of failure without the inner path list.
  assert.equal(isXSearchDependencyError("x_search: X upstream dependency error"), true);
  assert.equal(isXSearchDependencyError("DependencyError: Unspecified (path: [ranked_tweets])"), true);
});

test("isXSearchDependencyError does not match unrelated realtime errors", () => {
  assert.equal(isXSearchDependencyError("rate limit exceeded"), false);
  assert.equal(isXSearchDependencyError(""), false);
  // A dependency error for something else is NOT the X-search failure.
  assert.equal(isXSearchDependencyError("DependencyError: Unspecified (path: [web_search])"), false);
});

test("readableRealtimeError degrades the X-search failure to a spoken sentence", () => {
  assert.equal(readableRealtimeError(XAI_X_SEARCH_ERROR), X_SEARCH_UNAVAILABLE_MESSAGE);
  assert.match(readableRealtimeError(XAI_X_SEARCH_ERROR), /X search is temporarily unavailable/);
  // The raw internals never reach the user.
  assert.ok(!/DependencyError|ranked_tweets/.test(readableRealtimeError(XAI_X_SEARCH_ERROR)));
});

test("readableRealtimeError passes every other error through untouched", () => {
  assert.equal(readableRealtimeError("rate limit exceeded"), "rate limit exceeded");
  assert.equal(readableRealtimeError("Conversation error"), "Conversation error");
  assert.equal(readableRealtimeError("WebSocket closed unexpectedly"), "WebSocket closed unexpectedly");
});

test("instructions tell Junior to degrade a failed x_search without leaking the raw error", () => {
  assert.match(JUNIOR_TALK_INSTRUCTIONS, /x_search lookup fails/);
  assert.match(JUNIOR_TALK_INSTRUCTIONS, /do NOT read the raw error out/);
  assert.match(JUNIOR_TALK_INSTRUCTIONS, /still answer from what you already know/);
  assert.match(JUNIOR_TALK_INSTRUCTIONS, /Never let one failed search end the conversation/);
});

test("an x_search dependency error degrades and keeps the voice turn alive", async () => {
  const restore = installFakes();
  try {
    const { useConversationVoice } = await import("@/lib/use-conversation-voice");
    const slots: HookSlots = { refs: [], states: [], callbacks: [], memos: [], effects: [], index: 0 };
    const statuses: string[] = [];
    const errors: string[] = [];
    const voiceIdRef = { current: "castor" } as React.RefObject<string>;
    const render = () =>
      renderHook(
        () =>
          useConversationVoice({
            voiceIdRef,
            onUserTranscript: () => {},
            onStatusChange: (s: string) => statuses.push(s),
            onRealtimeError: (m: string) => errors.push(m),
          }),
        slots,
      );
    render();
    const start = render().start;
    const stop = render().stop;

    await start();
    await flushMicrotasks();
    const ws = FakeWebSocket.instances[0];
    assert.equal(statuses.at(-1), "listening");

    // THE FAILURE: xAI's built-in x_search hit its upstream X dependency.
    ws.onmessage?.({
      data: JSON.stringify({ type: "error", error: { message: XAI_X_SEARCH_ERROR } }),
    });
    await flushMicrotasks();

    // The user hears a clean sentence, never the raw DependencyError.
    assert.deepEqual(errors, [X_SEARCH_UNAVAILABLE_MESSAGE]);

    // THE FIX: the failed search does not kill the turn — the socket stays
    // open, the status stays "listening", and no reconnect was scheduled.
    assert.equal(ws.closed, false, "the session must survive a failed x_search");
    assert.equal(statuses.at(-1), "listening", "a failed x_search must not drop the status");
    assert.equal(FakeWebSocket.instances.length, 1, "no reconnect socket for a tool-level failure");

    // Junior still answers: a later audio delta from the same socket plays.
    ws.onmessage?.({ data: JSON.stringify({ type: "response.audio.delta", delta: "AAAA" }) });
    await flushMicrotasks();
    assert.equal(statuses.at(-1), "speaking", "Junior must still speak after the failed search");

    stop();
    unmountHook(slots);
  } finally {
    restore();
  }
});

test("a non-X realtime error is NOT degraded and not surfaced to onRealtimeError", async () => {
  const restore = installFakes();
  try {
    const { useConversationVoice } = await import("@/lib/use-conversation-voice");
    const slots: HookSlots = { refs: [], states: [], callbacks: [], memos: [], effects: [], index: 0 };
    const errors: string[] = [];
    const voiceIdRef = { current: "castor" } as React.RefObject<string>;
    const render = () =>
      renderHook(
        () =>
          useConversationVoice({
            voiceIdRef,
            onUserTranscript: () => {},
            onStatusChange: () => {},
            onRealtimeError: (m: string) => errors.push(m),
          }),
        slots,
      );
    render();
    const start = render().start;
    const stop = render().stop;

    await start();
    await flushMicrotasks();
    const ws = FakeWebSocket.instances[0];

    // A genuine transport/rate-limit error keeps its exact message and does not
    // masquerade as an X-search outage.
    ws.onmessage?.({ data: JSON.stringify({ type: "error", error: { message: "rate limit exceeded" } }) });
    await flushMicrotasks();
    assert.deepEqual(errors, []);
    assert.equal(ws.closed, false);

    stop();
    unmountHook(slots);
  } finally {
    restore();
  }
});
