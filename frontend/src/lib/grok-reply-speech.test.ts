import assert from "node:assert/strict";
import test from "node:test";
import { grokReplySpeechScript } from "@/lib/grok-reply-speech";

test("grokReplySpeechScript falls back to markdown source", () => {
  const { script } = grokReplySpeechScript(null, "Hello from Grok");
  assert.equal(script, "Hello from Grok");
});

test("grokReplySpeechScript never returns whitespace-only script from fallback", () => {
  const { script } = grokReplySpeechScript(null, "   ");
  assert.equal(script, "");
});
