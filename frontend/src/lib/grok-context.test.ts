import assert from "node:assert/strict";
import test from "node:test";
import {
  GROK_CONTEXT_CHAR_CAP,
  GROK_CONTEXT_TOAST,
  PASTE_FIRST_CHUNK_CHARS,
  chatContextOverCap,
  estimateChatContextChars,
  pasteSplitToast,
  splitPasteChunk,
} from "./grok-context";

test("thread-only chats are not blocked client-side", () => {
  const hugeThread = Array.from({ length: 20 }, (_, index) => ({
    role: index % 2 === 0 ? "user" : "assistant",
    content: "x".repeat(8_000),
  }));
  assert.equal(
    chatContextOverCap({
      messages: hugeThread,
      draft: "figure 8.5?",
      workingNoteSliceChars: 80_000,
      pendingExtracts: ["y".repeat(12_000)],
    }),
    false,
  );
});

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

test("a stuffed vault article is counted as one capped slice, not the whole book", () => {
  const huge = "x".repeat(GROK_CONTEXT_CHAR_CAP + 1);
  assert.equal(
    chatContextOverCap({
      messages: [],
      draft: "summarize this",
      includeArticle: true,
      articleBody: huge,
    }),
    false,
  );
  assert.match(GROK_CONTEXT_TOAST, /heading|selection|chunk/i);
});

test("over-cap paste toast names the size and first 12k split", () => {
  assert.match(pasteSplitToast(30_000), /This paste is 30[,.]?000 chars\. Send first 12k or split\./);
});

test("splitPasteChunk keeps the remainder instead of truncating", () => {
  const paste = `${"lesson ".repeat(2_000)} leftover ask`;
  const { first, remainder } = splitPasteChunk(paste);
  assert.ok(first.length <= PASTE_FIRST_CHUNK_CHARS);
  assert.ok(remainder.length > 0);
  assert.equal(`${first} ${remainder}`.replace(/\s+/g, " ").trim(), paste.replace(/\s+/g, " ").trim());
  const small = splitPasteChunk("short leftover ask");
  assert.equal(small.first, "short leftover ask");
  assert.equal(small.remainder, "");
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

test("include mode ignores a long thread when checking the cap", () => {
  const hugeThread = Array.from({ length: 20 }, (_, index) => ({
    role: index % 2 === 0 ? "user" : "assistant",
    content: "x".repeat(8_000),
  }));
  assert.equal(
    chatContextOverCap({
      messages: hugeThread,
      draft: "summarize this heading",
      includeArticle: true,
      articleBody: "y".repeat(12_000),
      includeSliceChars: 12_000,
    }),
    false,
  );
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
