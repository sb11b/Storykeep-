import assert from "node:assert/strict";
import test from "node:test";
import {
  GROK_CONTEXT_CHAR_CAP,
  GROK_CONTEXT_TOAST,
  chatContextOverCap,
  estimateChatContextChars,
} from "./grok-context";

test("small talk plus a short article stays under the cap", () => {
  const chars = estimateChatContextChars({
    messages: [],
    draft: "hello",
    includeArticle: true,
    articleBody: "A short excerpt.",
  });
  assert.ok(chars < GROK_CONTEXT_CHAR_CAP);
  assert.equal(chatContextOverCap({ messages: [], draft: "hello" }), false);
});

test("a stuffed vault article over cap blocks Send", () => {
  const huge = "x".repeat(GROK_CONTEXT_CHAR_CAP + 1);
  assert.equal(
    chatContextOverCap({
      messages: [],
      draft: "summarize this",
      includeArticle: true,
      articleBody: huge,
    }),
    true,
  );
  assert.equal(GROK_CONTEXT_TOAST, "Too large — deselect Include or start a new chat.");
});

test("thread plus extracts plus include all count", () => {
  const chars = estimateChatContextChars({
    messages: [
      { role: "user", content: "aaaa", files: [{ extract_text: "bbbb" }] },
      { role: "assistant", content: "cccc" },
    ],
    draft: "dddd",
    includeArticle: true,
    articleBody: "eeee",
    includeNote: true,
    noteBody: "ffff",
    pendingExtracts: ["gggg"],
  });
  assert.equal(chars, 4 * 7);
});

test("the same article-as-note is not counted twice", () => {
  const body = "same-note-body";
  assert.equal(
    estimateChatContextChars({
      messages: [],
      draft: "",
      includeArticle: true,
      articleBody: body,
      includeNote: true,
      noteBody: body,
    }),
    body.length,
  );
});
