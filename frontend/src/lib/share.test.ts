import assert from "node:assert/strict";
import test from "node:test";
import { articleShareHref, shareUrlForArticle } from "./share";

test("shareUrlForArticle prefers the original http link", () => {
  const url = shareUrlForArticle(
    { id: "abc", title: "Story", url: "https://example.com/story" },
    "https://storykeep.example",
  );
  assert.equal(url, "https://example.com/story");
});

test("shareUrlForArticle falls back to a StoryKeep article link", () => {
  const url = shareUrlForArticle(
    { id: "abc-123", title: "Vault note", url: "storykeep://pending" },
    "https://storykeep.example",
  );
  assert.equal(url, "https://storykeep.example/?article=abc-123");
});

test("articleShareHref builds social and message links", () => {
  const article = { id: "1", title: "Hello", url: "https://example.com/a" };
  assert.match(articleShareHref("email", article, "https://app.test"), /^mailto:\?subject=/);
  assert.match(articleShareHref("sms", article, "https://app.test"), /^sms:\?&body=/);
  assert.match(articleShareHref("facebook", article, "https://app.test"), /facebook\.com\/sharer/);
  assert.match(articleShareHref("x", article, "https://app.test"), /twitter\.com\/intent\/tweet/);
  assert.match(articleShareHref("reddit", article, "https://app.test"), /reddit\.com\/submit/);
});
