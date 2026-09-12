import assert from "node:assert/strict";
import test from "node:test";
import { timestampsMatchChunk, wordIndexAtTime } from "./tts-cue";
import type { TtsWord } from "./types";

const sampleWords: TtsWord[] = [
  { text: "Hello", start: 0, end: 0.4 },
  { text: "world", start: 0.4, end: 0.9 },
  { text: "again", start: 0.9, end: 1.4 },
];

test("wordIndexAtTime maps playback seconds to one word index", () => {
  assert.equal(wordIndexAtTime(sampleWords, 0), 0);
  assert.equal(wordIndexAtTime(sampleWords, 0.5), 1);
  assert.equal(wordIndexAtTime(sampleWords, 1.2), 2);
  assert.equal(wordIndexAtTime(sampleWords, 9), 2);
});

test("timestampsMatchChunk requires exact word count", () => {
  assert.equal(timestampsMatchChunk(sampleWords, 0, [3]), true);
  assert.equal(timestampsMatchChunk(sampleWords, 0, [2]), false);
  assert.equal(timestampsMatchChunk([], 0, [0]), false);
});
