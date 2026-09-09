import assert from "node:assert/strict";
import test from "node:test";
import { matchOffsets } from "./article-find";

test("matchOffsets finds case-insensitive hits", () => {
  const hits = matchOffsets("The GDPR rule and gdpr again.", "gdpr");
  assert.equal(hits.length, 2);
  assert.deepEqual(hits[0], { start: 4, end: 8 });
  assert.deepEqual(hits[1], { start: 18, end: 22 });
});

test("matchOffsets returns empty for blank query", () => {
  assert.deepEqual(matchOffsets("hello", "   "), []);
});
