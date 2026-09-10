import assert from "node:assert/strict";
import test from "node:test";
import { isUsableArticleBody, mergeExtractArticle } from "./format";

const LONG_PARA =
  "Full article paragraph with enough prose to count as readable article text for regression tests. ".repeat(
    8,
  );
const LONG_BODY = {
  content_html: `<p>${LONG_PARA}</p><p>${LONG_PARA}</p><p>${LONG_PARA}</p>`,
  content_text: `${LONG_PARA.trim()}\n\n${LONG_PARA.trim()}\n\n${LONG_PARA.trim()}`,
};

test("mergeExtractArticle grows short-body article when extract succeeds", () => {
  const dek = "These four Naruto characters prove you can surpass Kage-level strength without becoming Hokage.";
  const previous = {
    content_html: `<p>${dek}</p>`,
    content_text: dek,
    image_url: null,
  };
  const merged = mergeExtractArticle(previous, LONG_BODY);
  assert.ok((merged.content_text || "").length > dek.length);
  assert.ok(isUsableArticleBody(merged.content_html, merged.content_text));
});

test("mergeExtractArticle keeps previous body when extract returns worse text", () => {
  const previous = {
    ...LONG_BODY,
    image_url: "https://cdn.example.com/hero.jpg",
  };
  const worse = {
    content_html: "<p>Want to leave a tip?</p>",
    content_text: "Want to leave a tip?",
    image_url: null,
  };
  const merged = mergeExtractArticle(previous, worse);
  assert.equal(merged.content_text, previous.content_text);
  assert.equal(merged.content_html, previous.content_html);
  assert.equal(merged.image_url, previous.image_url);
});
