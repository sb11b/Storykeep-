import assert from "node:assert/strict";
import test from "node:test";
import { lastCommittedSentence, newFinalSegment, normalizeSpoken } from "./stt-buffer";

test("normalizeSpoken collapses whitespace", () => {
  assert.equal(normalizeSpoken("  Hello   there\n"), "Hello there");
});

test("newFinalSegment inserts the first final in full", () => {
  assert.equal(newFinalSegment("The slope is steep.", "", ""), "The slope is steep.");
});

test("newFinalSegment skips a repeat of the committed utterance", () => {
  assert.equal(newFinalSegment("The slope is steep.", "The slope is steep.", "The slope is steep."), "");
});

test("newFinalSegment keeps only the remainder of a cumulative final", () => {
  const have = "The slope is steep.";
  const incoming = "The slope is steep. The derivative is the slope.";
  assert.equal(newFinalSegment(incoming, have, have), "The derivative is the slope.");
});

test("newFinalSegment does not re-insert a prefix already committed", () => {
  const have = "Hello there how are you";
  assert.equal(newFinalSegment("Hello there", have, have), "");
});

test("newFinalSegment uses the last committed sentence as the dedup prefix", () => {
  const have = "Hello there. How are you";
  assert.equal(newFinalSegment("How are you today", have, have), "today");
});

test("lastCommittedSentence splits on punctuation", () => {
  assert.equal(lastCommittedSentence("One. Two! Three"), "Three");
});

test("newFinalSegment skips text already sitting at the end of the field", () => {
  assert.equal(newFinalSegment("curve", "", "The slope of the curve"), "");
});

test("newFinalSegment peels stacked copies of the same paragraph", () => {
  const para =
    "The GDPR requires a lawful basis for processing personal data of EU residents including consent contract legal obligation and legitimate interests.";
  const stacked = `${para} ${para} ${para} And a new clause.`;
  assert.equal(newFinalSegment(stacked, para, para), "And a new clause.");
});

test("newFinalSegment ignores an exact duplicate of the last paragraph", () => {
  const para = "The GDPR requires a lawful basis for processing personal data.";
  assert.equal(newFinalSegment(para, para, para), "");
  assert.equal(newFinalSegment(`${para} ${para}`, para, para), "");
});
