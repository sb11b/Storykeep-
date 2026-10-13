/**
 * Regression test for the Junior dictation mic.
 *
 * The bug: DictationProvider.startFor() nulled its only local AudioContext
 * binding (`context = null` in dictation.tsx, after handing ownership to
 * audioRef), but processor.onaudioprocess read `context!.sampleRate` through
 * that nulled local. Every audio hop therefore threw a TypeError. The
 * ScriptProcessorNode dispatcher swallows that throw — it surfaces only as an
 * AudioContext "error" event, with no toast, no log and no unhandled
 * rejection — so the WebSocket never received PCM, Junior stayed silent, and
 * the backend's idle watchdog eventually closed the take with no visible
 * reason. The mic button looked alive and did nothing.
 *
 * These tests drive the real provider through the same React-dispatcher
 * harness conversation-voice.test.ts uses (no jsdom), with fake WebSocket /
 * AudioContext / getUserMedia, and assert that the audio callback still runs
 * after the ownership hand-off.
 */

import assert from "node:assert/strict";
import test from "node:test";
import * as React from "react";

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
  connect() {}
  disconnect() {}
  /** Fire one hop, exactly as the audio thread would. */
  hop(): void {
    if (!this.onaudioprocess) return;
    this.onaudioprocess({
      inputBuffer: { getChannelData: () => new Float32Array(4096) },
    });
  }
}

class FakeGain {
  gain = { value: 1 };
  connect() {}
  disconnect() {}
}

class FakeSourceNode {
  connect() {}
  disconnect() {}
}

class FakeAudioContext {
  static instances: FakeAudioContext[] = [];
  state = "running";
  closed = false;
  destination = {};
  processors: FakeScriptProcessor[] = [];
  /** The real API's native rate; the downsample path divides by it. */
  sampleRate = 48_000;
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
  createMediaStreamSource() {
    return new FakeSourceNode();
  }
  createScriptProcessor() {
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
  readyState = 0;
  binaryType = "blob";
  /** Binary PCM frames the client actually sent. */
  sent: ArrayBuffer[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: ((event: { code: number }) => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(public url: string) {
    FakeWebSocket.instances.push(this);
  }
  addEventListener() {
    /* never fires "error" in these tests */
  }
  /** Deliver a JSON control frame from the server. */
  deliver(payload: Record<string, unknown>) {
    this.onmessage?.({ data: JSON.stringify(payload) });
  }
  send(data: ArrayBuffer | string) {
    if (typeof data === "string") return;
    this.sent.push(data);
  }
  close() {
    this.readyState = 3;
    this.onclose?.({ code: 1000 });
  }
}

let streams: FakeStream[] = [];

function installFakes() {
  FakeAudioContext.instances = [];
  FakeWebSocket.instances = [];
  streams = [];
  const originals = {
    AudioContext: (globalThis as Record<string, unknown>).AudioContext,
    WebSocket: (globalThis as Record<string, unknown>).WebSocket,
    mediaDevices: navigator.mediaDevices,
    window: (globalThis as Record<string, unknown>).window,
    location: (globalThis as Record<string, unknown>).location,
  };
  (globalThis as Record<string, unknown>).AudioContext = FakeAudioContext;
  (globalThis as Record<string, unknown>).WebSocket = FakeWebSocket;
  // The provider reads window.location.protocol to pick ws vs wss; point window
  // at globalThis so both resolve to this deterministic https origin.
  (globalThis as Record<string, unknown>).window = globalThis;
  (globalThis as Record<string, unknown>).location = { protocol: "https:", host: "localhost" };
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
  return () => {
    (globalThis as Record<string, unknown>).AudioContext = originals.AudioContext;
    (globalThis as Record<string, unknown>).WebSocket = originals.WebSocket;
    (globalThis as Record<string, unknown>).window = originals.window;
    (globalThis as Record<string, unknown>).location = originals.location;
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: originals.mediaDevices,
    });
  };
}

async function flushMicrotasks(times = 12): Promise<void> {
  for (let i = 0; i < times; i += 1) await Promise.resolve();
}

/* ── React dispatcher harness (mirrors conversation-voice.test.ts) ── */

type Cleanup = () => void;

function withDispatcher<T>(slots: HookSlots, fn: () => T): T {
  const internals = (
    React as unknown as {
      __CLIENT_INTERNALS_DO_NOT_USE_OR_WARN_USERS_THEY_CANNOT_UPGRADE: { H: unknown };
    }
  ).__CLIENT_INTERNALS_DO_NOT_USE_OR_WARN_USERS_THEY_CANNOT_UPGRADE;
  const previous = internals.H;
  internals.H = {
    useRef: (initial: unknown) => {
      const i = (slots.index += 1);
      if (!slots.refs[i - 1]) slots.refs[i - 1] = { current: initial };
      return slots.refs[i - 1];
    },
    useState: (initial: unknown) => {
      const i = (slots.index += 1);
      if (slots.states.length < i) {
        slots.states[i - 1] =
          typeof initial === "function" ? (initial as () => unknown)() : initial;
      }
      return [
        slots.states[i - 1],
        (next: unknown) => {
          slots.states[i - 1] = next;
        },
      ];
    },
    useCallback: (fn: unknown, deps: unknown[]) => {
      const i = (slots.index += 1);
      const prev = slots.callbacks[i - 1];
      if (prev && depsEqual(prev.deps, deps)) return prev.fn;
      slots.callbacks[i - 1] = { fn, deps };
      return fn;
    },
    useMemo: (factory: () => unknown, deps: unknown[]) => {
      const i = (slots.index += 1);
      const prev = slots.memos[i - 1];
      if (prev && depsEqual(prev.deps, deps)) return prev.value;
      const value = factory();
      slots.memos[i - 1] = { value, deps };
      return value;
    },
    useEffect: (create: () => Cleanup | void, deps?: unknown[]) => {
      const i = (slots.index += 1);
      const prev = slots.effects[i - 1];
      if (prev && depsEqual(prev.deps, deps ?? [])) return;
      slots.effects[i - 1] = { create, deps: deps ?? [] };
    },
  };
  try {
    return fn();
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

function unmountHook(slots: HookSlots): void {
  for (const effect of [...slots.effects].reverse()) effect?.cleanup?.();
}

type DictationApi = {
  listening: boolean;
  startFor: (field: unknown, options?: unknown) => void;
  stop: () => void;
  abort: () => void;
};

let DictationProvider: (props: { children: React.ReactNode }) => unknown;

/** Fresh provider api object (the value it puts on DictationContext). */
function providerApi(slots: HookSlots): DictationApi {
  const tree = withDispatcher(slots, () =>
    DictationProvider({ children: null as unknown as React.ReactNode }),
  ) as unknown as { props: { value: DictationApi } };
  return tree.props.value;
}

/**
 * Drive startFor() through a full handshake: getUserMedia -> WebSocket open ->
 * the server's ready frame, which is when the provider starts streaming.
 * Returns the socket and the ScriptProcessorNode whose callback runs on every
 * audio hop.
 */
async function startDictation(slots: HookSlots, api: DictationApi) {
  const field = {
    value: "",
    focus() {},
    setSelectionRange() {},
  } as unknown as HTMLTextAreaElement;
  api.startFor(field, { continuous: false });
  await flushMicrotasks();

  const socket = FakeWebSocket.instances[0];
  assert.ok(socket, "startFor must open the STT WebSocket");
  // A real socket is OPEN when onopen fires.
  socket.readyState = FakeWebSocket.OPEN;
  socket.onopen?.();
  await flushMicrotasks();

  const context = FakeAudioContext.instances.find((c) => c.processors.length > 0);
  assert.ok(context, "startFor must build a ScriptProcessorNode once the socket opens");
  return { socket, processor: context.processors[0]! };
}

/* ── The regression ── */

test("the mic streams PCM on the first audio hop after the ownership hand-off", async () => {
  const restore = installFakes();
  try {
    ({ DictationProvider } = await import("@/components/dictation"));
    const slots: HookSlots = { refs: [], states: [], callbacks: [], memos: [], effects: [], index: 0 };
    const api = providerApi(slots);

    const { socket, processor } = await startDictation(slots, api);
    socket.deliver({ type: "ready", continuous: false });
    await flushMicrotasks(6);

    // THE FIX: the callback must still read the AudioContext after
    // `context = null` handed ownership to audioRef.
    let threw: unknown = null;
    try {
      processor.hop();
    } catch (error) {
      threw = error;
    }
    assert.equal(threw, null, "the audio hop must not throw after the ownership hand-off");
    assert.ok(socket.sent.length > 0, "the socket must receive PCM on the first hop");

    // And again on the next hop — a one-frame reprieve would not be a fix.
    const before = socket.sent.length;
    processor.hop();
    assert.ok(socket.sent.length > before, "every hop must keep streaming");

    unmountHook(slots);
  } finally {
    restore();
  }
});

test("audio buffered before ready is flushed, not dropped, once the socket opens", async () => {
  const restore = installFakes();
  try {
    ({ DictationProvider } = await import("@/components/dictation"));
    const slots: HookSlots = { refs: [], states: [], callbacks: [], memos: [], effects: [], index: 0 };
    const api = providerApi(slots);

    const { socket, processor } = await startDictation(slots, api);

    // Hops before the ready frame: the provider buffers them instead of sending.
    processor.hop();
    processor.hop();
    assert.equal(socket.sent.length, 0, "pre-ready audio stays buffered");

    // Ready arrives -> the buffer is flushed in full.
    socket.deliver({ type: "ready", continuous: false });
    await flushMicrotasks(6);
    assert.ok(socket.sent.length >= 2, "buffered audio must be flushed once ready");

    unmountHook(slots);
  } finally {
    restore();
  }
});
