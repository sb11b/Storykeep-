import assert from "node:assert/strict";
import test from "node:test";
import { normalizeVisibleSpeechScript } from "./tts-visible";

test("normalizeVisibleSpeechScript strips urls like backend speech script", () => {
  const next = normalizeVisibleSpeechScript("See https://example.com/a for more.");
  assert.equal(next, "See for more.");
});

test("normalizeVisibleSpeechScript collapses whitespace", () => {
  assert.equal(normalizeVisibleSpeechScript("  one   two \n three  "), "one two three");
});
