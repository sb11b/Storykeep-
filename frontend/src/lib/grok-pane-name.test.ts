import assert from "node:assert/strict";
import test from "node:test";
import {
  DEFAULT_PANE_NAME,
  chatStatusLine,
  closeAssistantTurn,
  defaultGrokPaneName,
  isDefaultPaneName,
  NO_REPLY_TOAST,
  normalizeTurnStatus,
} from "./grok-pane-name";

test("the default pane name is Junior", () => {
  assert.equal(DEFAULT_PANE_NAME, "Junior");
  assert.equal(defaultGrokPaneName(0), "Junior");
  assert.equal(defaultGrokPaneName(1), "Junior 2");
});

test("legacy Grok and Larry labels count as defaults", () => {
  assert.equal(isDefaultPaneName("Grok", 0), true);
  assert.equal(isDefaultPaneName("Grok panel 2", 1), true);
  assert.equal(isDefaultPaneName("Larry", 0), true);
  assert.equal(isDefaultPaneName("Larry (the asparagus)", 0), true);
  assert.equal(isDefaultPaneName("Larry (the asparagus) 2", 1), true);
  assert.equal(isDefaultPaneName("Junior", 0), true);
  assert.equal(isDefaultPaneName("Junior", 3), true);
  assert.equal(isDefaultPaneName("Study buddy", 0), false);
});

test("status lines use Queued / Thinking / Writing / Error", () => {
  assert.equal(chatStatusLine("Junior", "queued"), "Queued…");
  assert.equal(chatStatusLine("Junior", "working"), "Thinking…");
  assert.equal(chatStatusLine("Junior", "thinking"), "Thinking…");
  assert.equal(chatStatusLine("Junior", "writing"), "Writing…");
  assert.equal(chatStatusLine("Junior", "generating"), "Junior is generating…");
  assert.equal(chatStatusLine("Junior", "searching"), "Searching…");
  assert.equal(chatStatusLine("Junior", "error"), "Error");
  assert.equal(chatStatusLine("Junior", "done"), "");
});

test("ChatTurnStatus maps working to thinking and empty close to error", () => {
  assert.equal(normalizeTurnStatus("working"), "thinking");
  assert.equal(normalizeTurnStatus("queued"), "queued");
  assert.deepEqual(closeAssistantTurn("hello"), {
    turnStatus: "done",
    failed: false,
    waiting: false,
    error: null,
  });
  assert.deepEqual(closeAssistantTurn("   "), {
    turnStatus: "error",
    failed: true,
    waiting: false,
    error: NO_REPLY_TOAST,
  });
  assert.equal(closeAssistantTurn("", { aborted: true }).turnStatus, "error");
  assert.equal(closeAssistantTurn("partial", { aborted: true }).failed, true);
});
