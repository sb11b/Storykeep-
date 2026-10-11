/**
 * Hook-level tests for useConversationPolling's refreshHistory.
 *
 * The bug: useStreamRunner fires onHistoryChanged() on every stream turn (so
 * on every spoken Talk turn), and refreshHistory used to setHistoryLoading(true)
 * around the fetch unconditionally. The sidebar renders
 * `historyLoading ? <LoaderCircle "Loading…"> : <list>`, so the whole
 * conversation list was replaced by a spinner and repainted on every turn —
 * the left sidebar flickered continuously during Talk. A background refresh
 * must update an already-loaded list silently; only the initial load shows
 * the loading state.
 *
 * The hook is driven through React's internal dispatcher (no jsdom), the same
 * pattern conversation-voice.test.ts uses for useConversationVoice.
 */
import assert from "node:assert/strict";
import test from "node:test";
import * as React from "react";
import { useConversationPolling } from "@/lib/useConversationPolling";

type Cleanup = () => void;

interface HookSlots {
  refs: Array<{ current: unknown }>;
  states: unknown[];
  /** Every useState write, in order: which state slot got which value. */
  writes: Array<{ slot: number; value: unknown }>;
  callbacks: Array<{ fn: unknown; deps: unknown[] }>;
  effects: Array<{ create: () => Cleanup | void; deps: unknown[] }>;
  index: number;
}

function depsEqual(a: unknown[], b: unknown[]): boolean {
  if (a.length !== b.length) return false;
  return a.every((v, i) => Object.is(v, b[i]));
}

function freshSlots(): HookSlots {
  return { refs: [], states: [], writes: [], callbacks: [], effects: [], index: 0 };
}

/** Run one render of the hook with a hand-rolled React dispatcher. */
function renderPolling(slots: HookSlots) {
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
      return [
        slots.states[i],
        (next: unknown) => {
          slots.writes.push({ slot: i, value: next });
          slots.states[i] = next;
        },
      ];
    },
    useCallback: (fn: unknown, deps: unknown[]) => {
      const i = slots.index++;
      const prev = slots.callbacks[i];
      if (prev && depsEqual(prev.deps, deps)) return prev.fn;
      slots.callbacks[i] = { fn, deps };
      return fn;
    },
    useEffect: (create: () => Cleanup | void, deps?: unknown[]) => {
      const i = slots.index++;
      const prev = slots.effects[i];
      if (prev && depsEqual(prev.deps, deps ?? [])) return;
      slots.effects[i] = { create, deps: deps ?? [] };
    },
  };
  try {
    slots.index = 0;
    return withDispatcher(slots, () =>
      useConversationPolling(
        true, // persist
        false, // needsCryptoUnlock
        { current: [] } as React.MutableRefObject<never[]>,
        { current: false } as React.MutableRefObject<boolean>,
        { current: "pane-1" } as React.MutableRefObject<string>,
        { current: new Set<string>() } as React.MutableRefObject<Set<string>>,
        null, // cryptoStatus
        () => {}, // setNoticeCount
        () => {}, // setOpen
        (updater: unknown) => updater, // setPanes (unused by refreshHistory)
        async () => {}, // loadConversation
      ),
    );
  } finally {
    internals.H = previous;
  }
}

/** Install React's dispatcher for the duration of fn (needed to run a hook). */
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
      return [
        slots.states[i],
        (next: unknown) => {
          slots.writes.push({ slot: i, value: next });
          slots.states[i] = next;
        },
      ];
    },
    useCallback: (fn: unknown, deps: unknown[]) => {
      const i = slots.index++;
      const prev = slots.callbacks[i];
      if (prev && depsEqual(prev.deps, deps)) return prev.fn;
      slots.callbacks[i] = { fn, deps };
      return fn;
    },
    useEffect: (create: () => Cleanup | void, deps?: unknown[]) => {
      const i = slots.index++;
      const prev = slots.effects[i];
      if (prev && depsEqual(prev.deps, deps ?? [])) return;
      slots.effects[i] = { create, deps: deps ?? [] };
    },
  };
  try {
    return fn();
  } finally {
    internals.H = previous;
  }
}

/** Stub fetch so api.chatConversations() resolves without a network. */
function stubConversationsFetch(rows: unknown[]) {
  const original = globalThis.fetch;
  globalThis.fetch = (async () => ({
    ok: true,
    status: 200,
    statusText: "OK",
    json: async () => rows,
  })) as unknown as typeof fetch;
  return () => {
    globalThis.fetch = original;
  };
}

async function flushMicrotasks(times = 8): Promise<void> {
  for (let i = 0; i < times; i += 1) await Promise.resolve();
}

const ROW = { id: "conv-1", title: "First chat", updated_at: "2026-01-01T00:00:00Z" };
const ROW_2 = { id: "conv-2", title: "Second chat", updated_at: "2026-01-02T00:00:00Z" };

test("the initial refreshHistory shows the loading state, then clears it", async () => {
  const restore = stubConversationsFetch([ROW]);
  const slots = freshSlots();
  try {
    renderPolling(slots);
    const { refreshHistory } = renderPolling(slots);
    await refreshHistory();
    await flushMicrotasks();
    // Some state slot was flipped true and back to false — the initial load
    // takes the loading state, exactly as the sidebar's spinner expects.
    const flippedTrue = slots.writes.find((w) => w.value === true);
    assert.ok(flippedTrue, "the initial load must set a loading state to true");
    assert.equal(slots.writes.at(-1)?.value, false, "the initial load clears the loading state");
  } finally {
    restore();
  }
});

test("a background refresh with a populated list never flips historyLoading", async () => {
  const restore = stubConversationsFetch([ROW]);
  const slots = freshSlots();
  try {
    renderPolling(slots);
    const first = renderPolling(slots).refreshHistory;
    await first();
    await flushMicrotasks();

    // The list is loaded: capture the slot that carried the loading flag.
    const loadingSlot = slots.writes.find((w) => w.value === true)?.slot;
    assert.ok(loadingSlot !== undefined, "the initial load must have used a loading slot");
    const populatedList = slots.states.find((s) => Array.isArray(s)) as unknown[];
    assert.ok(populatedList.length > 0, "the conversation list must be populated before the refresh");

    // Second refresh — this is what useStreamRunner's onHistoryChanged does on
    // every stream turn. Before the gating fix this setHistoryLoading(true)
    // again, blanking the sidebar list to a spinner for the whole fetch.
    slots.writes.length = 0;
    const second = renderPolling(slots).refreshHistory;
    globalThis.fetch = (async () => ({
      ok: true,
      status: 200,
      statusText: "OK",
      json: async () => [ROW, ROW_2],
    })) as unknown as typeof fetch;
    await second();
    await flushMicrotasks();

    assert.ok(
      !slots.writes.some((w) => w.slot === loadingSlot && w.value === true),
      "a background refresh must never set the loading state true — the sidebar list would blank to a spinner",
    );
    // The new data still lands: the refresh is silent, not skipped.
    const updatedList = slots.states.find((s) => Array.isArray(s)) as unknown[];
    assert.equal(updatedList.length, 2, "the background refresh must still update the list in place");
    assert.ok(
      slots.writes.some((w) => Array.isArray(w.value) && w.value.length === 2),
      "the refreshed conversations must be written through",
    );
  } finally {
    restore();
  }
});
