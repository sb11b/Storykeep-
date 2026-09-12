import assert from "node:assert/strict";
import test from "node:test";
import { cueAheadOfVoice, timestampsMatchChunk, wordIndexAtTime } from "./tts-cue";
import type { TtsWord } from "./types";

const sampleWords: TtsWord[] = [
  { text: "Hello", start: 0, end: 0.4 },
  { text: "world", start: 0.4, end: 0.9 },
  { text: "again", start: 0.9, end: 1.4 },
];

test("wordIndexAtTime uses start <= time < end", () => {
  assert.equal(wordIndexAtTime(sampleWords, 0), 0);
  assert.equal(wordIndexAtTime(sampleWords, 0.39), 0);
  assert.equal(wordIndexAtTime(sampleWords, 0.4), 1);
  assert.equal(wordIndexAtTime(sampleWords, 0.5), 1);
  assert.equal(wordIndexAtTime(sampleWords, 1.2), 2);
  assert.equal(wordIndexAtTime(sampleWords, 9), 2);
});

test("wordIndexAtTime does not jump early when next start precedes prior end", () => {
  const overlap: TtsWord[] = [
    { text: "One", start: 0, end: 0.6 },
    { text: "Two", start: 0.4, end: 1.0 },
  ];
  assert.equal(wordIndexAtTime(overlap, 0.45), 0);
  assert.equal(wordIndexAtTime(overlap, 0.62), 1);
});

test("wordIndexAtTime returns null before the first word", () => {
  const delayed: TtsWord[] = [{ text: "Late", start: 0.2, end: 0.5 }];
  assert.equal(wordIndexAtTime(delayed, 0.05), null);
});

test("timestampsMatchChunk requires exact word count", () => {
  assert.equal(timestampsMatchChunk(sampleWords, 0, [3]), true);
  assert.equal(timestampsMatchChunk(sampleWords, 0, [2]), false);
  assert.equal(timestampsMatchChunk([], 0, [0]), false);
});

test("cueAheadOfVoice detects highlight running ahead of audio", () => {
  assert.equal(cueAheadOfVoice(sampleWords, 1, 0.35), true);
  assert.equal(cueAheadOfVoice(sampleWords, 1, 0.41), false);
});
