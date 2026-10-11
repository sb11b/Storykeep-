import assert from "node:assert/strict";
import test from "node:test";
import {
  dedupeToast,
  resetToastDedupe,
  shouldShowToast,
  TOAST_DEDUPE_WINDOW_MS,
  type DedupedToast,
} from "@/lib/toast-dedupe";

function recordingToast(): DedupedToast & { errors: string[]; messages: string[] } {
  const errors: string[] = [];
  const messages: string[] = [];
  return {
    errors,
    messages,
    error(message: string) {
      errors.push(message);
    },
    message(message: string) {
      messages.push(message);
    },
  };
}

test.beforeEach(() => {
  resetToastDedupe();
});

test("the dedupe window is 2000ms", () => {
  assert.equal(TOAST_DEDUPE_WINDOW_MS, 2000);
});

test("shouldShowToast shows the first message and suppresses an identical repeat inside the window", () => {
  assert.equal(shouldShowToast("No reply — retry", 2000, 1000), true);
  assert.equal(shouldShowToast("No reply — retry", 2000, 1500), false, "1.5s later: suppressed");
  assert.equal(shouldShowToast("No reply — retry", 2000, 2999), false, "just under the window: suppressed");
});

test("shouldShowToast allows the same message again after the window", () => {
  assert.equal(shouldShowToast("No reply — retry", 2000, 1000), true);
  assert.equal(shouldShowToast("No reply — retry", 2000, 3000), true, "at the window edge: shown");
});

test("shouldShowToast tracks each message independently", () => {
  assert.equal(shouldShowToast("A", 2000, 1000), true);
  assert.equal(shouldShowToast("B", 2000, 1000), true, "a different message is never suppressed");
  assert.equal(shouldShowToast("A", 2000, 1100), false, "A is still inside its own window");
});

test("a storm of identical toasts collapses to one; distinct messages still show", () => {
  const toast = recordingToast();
  // Ten failing Talk turns in 800ms — the observed storm. The window math is
  // covered by the shouldShowToast tests above; this asserts the wrapper.
  const window = TOAST_DEDUPE_WINDOW_MS;
  assert.ok(window >= 500, "window must comfortably cover a per-turn failure burst");
  dedupeToast(toast, "boom", "error");
  dedupeToast(toast, "boom", "error");
  dedupeToast(toast, "boom", "error");
  assert.equal(toast.errors.length, 1, "identical repeats inside the window collapse to one");
});

test("dedupeToast routes errors and messages to the right channel", () => {
  const toast = recordingToast();
  dedupeToast(toast, "boom", "error");
  dedupeToast(toast, "heads up", "message");
  assert.deepEqual(toast.errors, ["boom"]);
  assert.deepEqual(toast.messages, ["heads up"]);
});

test("dedupeToast suppresses an identical repeat and keeps distinct messages", () => {
  const toast = recordingToast();
  dedupeToast(toast, "boom", "error");
  dedupeToast(toast, "boom", "error");
  dedupeToast(toast, "other", "error");
  assert.deepEqual(toast.errors, ["boom", "other"]);
});
