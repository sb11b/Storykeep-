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

test("applyInlineSize wraps and unwraps point sizes", () => {
  const big = applyInlineSize("Keep this loud", 5, 9, "18");
  assert.equal(big.text, 'Keep <span class="sk-size-18">this</span> loud');
  const normal = applyInlineSize(big.text, 5, big.text.length - 5, "normal");
  assert.equal(normal.text, "Keep this loud");
  const small = applyInlineSize("Keep this quiet", 5, 9, "8");
  assert.equal(small.text, 'Keep <span class="sk-size-8">this</span> quiet');
});

test("applyInlineSize replaces a legacy size span with a point size", () => {
  const legacy = 'Keep <span class="sk-size-lg">this</span> loud';
  const sized = applyInlineSize(legacy, 5, legacy.length - 5, "12");
  assert.equal(sized.text, 'Keep <span class="sk-size-12">this</span> loud');
});

test("applyComposerStyle routes headings and point sizes", () => {
  const heading = applyComposerStyle("Line", 0, 4, "h1");
  assert.equal(heading.text, "# Line");
  const sized = applyComposerStyle("Line", 0, 4, "20");
  assert.match(sized.text, /sk-size-20/);
});

test("applyComposerStyle body clears headings and point sizes", () => {
  const fromHeading = applyComposerStyle("## Section", 3, 3, "body");
  assert.equal(fromHeading.text, "Section");
  const fromLarge = applyComposerStyle('<span class="sk-size-18">big</span> here', 0, 45, "body");
  assert.equal(fromLarge.text, "big here");
});

test("detectComposerStyle reads headings and point sizes", () => {
  assert.equal(detectComposerStyle("## Section", 3, 3), "h2");
  assert.equal(detectComposerStyle('<span class="sk-size-12">tiny</span>', 10, 10), "12");
  assert.equal(detectComposerStyle("Plain body", 3, 3), "body");
});

test("detectComposerStyle maps legacy spans to point sizes", () => {
  assert.equal(detectComposerStyle('<span class="sk-size-sm">x</span>', 0, 0), "12");
  assert.equal(detectComposerStyle('<span class="sk-size-lg">x</span>', 0, 0), "18");
});

test("renderMarkdown keeps point-size spans and legacy spans", () => {
  const html = renderMarkdown('Intro with <span class="sk-size-18">big</span> word');
  assert.match(html, /<span class="sk-size-18">big<\/span>/);
  const legacy = renderMarkdown('Intro with <span class="sk-size-sm">tiny</span> word');
  assert.match(legacy, /<span class="sk-size-sm">tiny<\/span>/);
});
