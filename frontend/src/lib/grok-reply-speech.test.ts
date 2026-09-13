import assert from "node:assert/strict";
import test from "node:test";
import { grokReplySpeechScript } from "@/lib/grok-reply-speech";

test("grokReplySpeechScript falls back to markdown when the body is unmounted", () => {
  const result = grokReplySpeechScript(null, "Hello from Grok");
  assert.equal(result.script, "Hello from Grok");
  assert.equal(result.source, "markdown");
  assert.equal(result.visibleWordCount, 3);
});

test("grokReplySpeechScript reports empty only when there is truly no text", () => {
  const result = grokReplySpeechScript(null, "   ");
  assert.equal(result.script, "");
  assert.equal(result.source, "empty");
});

test("grokReplySpeechScript prefers innerText over wrapped word spans", () => {
  const root = {
    innerText: "Hello there from the asparagus",
    textContent: "ignored",
    querySelectorAll: () => [],
    ownerDocument: undefined,
  } as unknown as HTMLElement;
  const result = grokReplySpeechScript(root, "markdown source");
  assert.equal(result.script, "Hello there from the asparagus");
  assert.equal(result.source, "innerText");
});
