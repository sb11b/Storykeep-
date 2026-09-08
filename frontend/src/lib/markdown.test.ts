import assert from "node:assert/strict";
import test from "node:test";
import { prefixSelectedLines, renderMarkdown, wrapHighlight, wrapInline } from "./markdown";

test("wrapHighlight wraps a textarea selection", () => {
  const result = wrapHighlight("The slope of y", 4, 9);
  assert.equal(result.text, "The ==slope== of y");
  assert.equal(result.selectionStart, 6);
  assert.equal(result.selectionEnd, 11);
});

test("wrapHighlight wraps the word at the caret when nothing is selected", () => {
  const result = wrapHighlight("The slope of y", 6, 6);
  assert.equal(result.text, "The ==slope== of y");
  assert.equal(result.selectionStart, 6);
  assert.equal(result.selectionEnd, 11);
});

test("renderMarkdown turns ==text== into mark", () => {
  const html = renderMarkdown("Keep ==the slope== of y.");
  assert.match(html, /<mark>the slope<\/mark>/);
  assert.equal(html.includes("==the slope=="), false);
});

test("wrapInline and lists", () => {
  const bold = wrapInline("The slope", 4, 9, "**", "**");
  assert.equal(bold.text, "The **slope**");
  const under = wrapInline("The slope", 4, 9, "<u>", "</u>");
  assert.equal(under.text, "The <u>slope</u>");
  const bullets = prefixSelectedLines("one\ntwo", 0, 7, "ul");
  assert.equal(bullets.text, "- one\n- two");
  const numbered = prefixSelectedLines("one\ntwo", 0, 7, "ol");
  assert.equal(numbered.text, "1. one\n2. two");
  const html = renderMarkdown("**bold** *italic*\n<u>under</u>\n- item\n1. first");
  assert.match(html, /<strong>bold<\/strong>/);
  assert.match(html, /<em>italic<\/em>/);
  assert.match(html, /<u>under<\/u>/);
  assert.match(html, /<ul>/);
  assert.match(html, /<ol>/);
});
