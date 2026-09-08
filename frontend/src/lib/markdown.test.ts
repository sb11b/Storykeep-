import assert from "node:assert/strict";
import test from "node:test";
import { renderMarkdown, wrapHighlight } from "./markdown";

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
