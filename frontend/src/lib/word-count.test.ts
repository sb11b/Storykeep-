import assert from "node:assert/strict";
import test from "node:test";
import { hasGrammarMarks, stripMarks, wordCount } from "@/lib/word-count";

test("wordCount ignores highlight marks", () => {
  assert.equal(wordCount("one two three"), 3);
  assert.equal(wordCount("well ==known== method"), 3);
  assert.equal(wordCount(""), 0);
});

test("stripMarks and hasGrammarMarks", () => {
  assert.equal(stripMarks("well-==known== and <mark>clear</mark>"), "well-known and clear");
  assert.equal(hasGrammarMarks("well-==known=="), true);
  assert.equal(hasGrammarMarks("clean copy"), false);
});
