import assert from "node:assert/strict";
import test from "node:test";
import { applyBlockStyle, applyComposerStyle, applyInlineSize, detectComposerStyle } from "./note-style";
import { renderMarkdown } from "./markdown";

test("applyBlockStyle sets and clears headings on the current line", () => {
  const h2 = applyBlockStyle("Intro\nTitle here\nTail", 7, 7, "h2");
  assert.equal(h2.text, "Intro\n## Title here\nTail");
  const body = applyBlockStyle("## Title here", 0, 14, "body");
  assert.equal(body.text, "Title here");
});

test("applyInlineSize wraps and unwraps small and large text", () => {
  const large = applyInlineSize("Keep this loud", 5, 9, "large");
  assert.equal(large.text, 'Keep <span class="sk-size-lg">this</span> loud');
  const normal = applyInlineSize(large.text, 5, large.text.length - 5, "normal");
  assert.equal(normal.text, "Keep this loud");
  const small = applyInlineSize("Keep this quiet", 5, 9, "small");
  assert.equal(small.text, 'Keep <span class="sk-size-sm">this</span> quiet');
});

test("applyComposerStyle routes headings and inline sizes", () => {
  const heading = applyComposerStyle("Line", 0, 4, "h1");
  assert.equal(heading.text, "# Line");
  const sized = applyComposerStyle("Line", 0, 4, "large");
  assert.match(sized.text, /sk-size-lg/);
});

test("detectComposerStyle reads headings and inline sizes", () => {
  assert.equal(detectComposerStyle("## Section", 3, 3), "h2");
  assert.equal(detectComposerStyle('<span class="sk-size-sm">tiny</span>', 10, 10), "small");
  assert.equal(detectComposerStyle("Plain body", 3, 3), "body");
});

test("renderMarkdown keeps inline size spans", () => {
  const html = renderMarkdown('Intro with <span class="sk-size-lg">big</span> word');
  assert.match(html, /<span class="sk-size-lg">big<\/span>/);
});
