import assert from "node:assert/strict";
import test from "node:test";
import { EMPTY_REPLY_BODY } from "./grok-pane-name.ts";
import { savedReplyFillsEmptyBubble } from "./saved-reply.ts";

test("saved agent text replaces an empty stream", () => {
  const saved = "Cursor Cloud Agent started. Open: https://cursor.com/agents/bc-1";
  assert.equal(savedReplyFillsEmptyBubble("", saved), true);
  assert.equal(savedReplyFillsEmptyBubble(EMPTY_REPLY_BODY, saved), true);
});

test("a real local reply is left alone", () => {
  assert.equal(savedReplyFillsEmptyBubble("Cursor Cloud Agent started.", "older"), false);
});

test("the empty sentence is not treated as a saved reply", () => {
  assert.equal(savedReplyFillsEmptyBubble("", EMPTY_REPLY_BODY), false);
});
